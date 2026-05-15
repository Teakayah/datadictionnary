"""Tests for the sidecar sync daemon (src/sync/daemon.py + dr_resync.py).

Coverage:
  - DaemonConn: opens user_data file, initialises schema, can be closed
  - _set_status / _record_heartbeat: round-trip via user_data.site_settings
  - _recover_stale_rows: stuck 'syncing' rows older than threshold flip back
  - _recover_stale_rows: rows newer than threshold are NOT touched
  - _HealthzHandler: returns 200 when heartbeat is fresh, 503 when stale
  - run_dr_resync: skips gracefully when Databricks creds are unset
  - run_dr_resync: pulls deltas via injected fake databricks_query, merges into local
  - run_dr_resync: surfaces errors via status_setter
  - _process_sync_queue: accepts injected conn and drains rows into a fake pusher
  - run(once=True): single cycle with no pending rows still records heartbeat
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone; UTC = timezone.utc
from unittest.mock import patch

import duckdb
import pandas as pd
import pytest


# ── DaemonConn fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def tmp_user_data(tmp_path, monkeypatch):
    """Point USER_DATA_PATH/DUCKDB_PATH at temp files and reload modules.

    Also clears the Streamlit @cache_resource for the shared connection so
    a second test doesn't see the previous test's in-memory file.
    """
    catalog_path = tmp_path / "dict.duckdb"
    user_path = tmp_path / "dict_user_data.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(catalog_path))
    # _duckdb_available() checks os.path.exists(DUCKDB_PATH) — touch an empty
    # DuckDB file so the worker's read shim treats DuckDB as available.
    duckdb.connect(str(catalog_path)).close()
    import importlib
    import src.config
    importlib.reload(src.config)
    import src.db.duckdb_adapter
    importlib.reload(src.db.duckdb_adapter)
    try:
        src.db.duckdb_adapter._get_shared_duckdb_connection.clear()
    except Exception:
        pass
    # Reload anything that captured pre-reload module references.
    import src.db.queries
    importlib.reload(src.db.queries)
    import src.sync.daemon_db
    importlib.reload(src.sync.daemon_db)
    import src.sync.daemon
    importlib.reload(src.sync.daemon)
    import src.sync.dr_resync
    importlib.reload(src.sync.dr_resync)
    import src.sync.push
    importlib.reload(src.sync.push)
    import src.sync.worker
    importlib.reload(src.sync.worker)
    yield {"catalog": catalog_path, "user": user_path}


@pytest.fixture
def daemon_conn(tmp_user_data):
    from src.sync.daemon_db import DaemonConn
    conn = DaemonConn()
    yield conn
    conn.close()


# ── DaemonConn ───────────────────────────────────────────────────────────────

class TestDaemonConn:
    def test_opens_and_initialises_schema(self, daemon_conn):
        # site_settings table should be queryable after init (proxy for "schema applied").
        with daemon_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM user_data.site_settings")
            rows = cur.fetchall()
        assert rows[0][0] == 0

    def test_close_is_idempotent(self, daemon_conn):
        daemon_conn.close()
        daemon_conn.close()  # second close must not raise


# ── Status persistence ──────────────────────────────────────────────────────

class TestStatusPersistence:
    def test_set_status_round_trip(self, daemon_conn):
        from src.sync.daemon import _set_status
        _set_status(daemon_conn, "dr_resync_status", "Up-to-date")
        with daemon_conn.cursor() as cur:
            cur.execute(
                "SELECT value FROM user_data.site_settings WHERE key=%(k)s",
                {"k": "dr_resync_status"},
            )
            rows = cur.fetchall()
        assert rows[0][0] == "Up-to-date"

    def test_set_status_upserts(self, daemon_conn):
        from src.sync.daemon import _set_status
        _set_status(daemon_conn, "dr_resync_status", "Checking")
        _set_status(daemon_conn, "dr_resync_status", "Up-to-date")
        with daemon_conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM user_data.site_settings WHERE key='dr_resync_status'"
            )
            rows = cur.fetchall()
        assert rows[0][0] == 1  # one row, upserted


# ── Stale-row recovery ──────────────────────────────────────────────────────

class TestRecoverStaleRows:
    def _enqueue(self, conn, sync_id, status, last_attempt_at):
        with conn.cursor() as cur:
            cur.execute_write(
                """
                INSERT INTO user_data.pending_sync
                  (sync_id, sync_type, table_full_name, payload_json,
                   queued_by, queued_at, status, attempts, last_attempt_at)
                VALUES (%(id)s, 'COLUMN_DEF', 'a.b.c', '{}',
                        'tester', current_localtimestamp(), %(s)s, 1, %(la)s)
                """,
                {"id": sync_id, "s": status, "la": last_attempt_at},
            )

    def test_stale_rows_flip_back_to_pending(self, daemon_conn):
        from src.sync.daemon import _recover_stale_rows
        old = datetime.now(UTC).replace(tzinfo=None) - pd.Timedelta(minutes=10)
        sid = str(uuid.uuid4())
        self._enqueue(daemon_conn, sid, "syncing", old)

        n = _recover_stale_rows(daemon_conn, timeout_s=300)
        assert n == 1

        with daemon_conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM user_data.pending_sync WHERE sync_id=%(id)s",
                {"id": sid},
            )
            assert cur.fetchall()[0][0] == "pending"

    def test_fresh_rows_not_touched(self, daemon_conn):
        from src.sync.daemon import _recover_stale_rows
        recent = datetime.now(UTC).replace(tzinfo=None)
        sid = str(uuid.uuid4())
        self._enqueue(daemon_conn, sid, "syncing", recent)

        n = _recover_stale_rows(daemon_conn, timeout_s=300)
        assert n == 0

        with daemon_conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM user_data.pending_sync WHERE sync_id=%(id)s",
                {"id": sid},
            )
            assert cur.fetchall()[0][0] == "syncing"

    def test_no_rows_returns_zero(self, daemon_conn):
        from src.sync.daemon import _recover_stale_rows
        assert _recover_stale_rows(daemon_conn) == 0


# ── Healthz ──────────────────────────────────────────────────────────────────

class TestHealthz:
    def _make_handler(self):
        """Build a _HealthzHandler instance bypassing __init__ (which expects
        a real socket). We only test do_GET routing via a mock-driven request."""
        from src.sync import daemon
        return daemon

    def test_returns_200_when_heartbeat_fresh(self, monkeypatch):
        from src.sync import daemon
        monkeypatch.setattr(daemon, "_last_heartbeat", time.time())
        # Drive do_GET via a fake request.
        from io import BytesIO

        class _FakeRequest:
            def makefile(self, *a, **k):
                return BytesIO(b"GET /healthz HTTP/1.0\r\n\r\n")

        class _FakeServer:
            server_address = ("127.0.0.1", 0)

        out = BytesIO()
        with patch("http.server.BaseHTTPRequestHandler.setup", lambda self: None), \
             patch("http.server.BaseHTTPRequestHandler.finish", lambda self: None):
            handler = daemon._HealthzHandler.__new__(daemon._HealthzHandler)
            handler.rfile = BytesIO(b"GET /healthz HTTP/1.0\r\n\r\n")
            handler.wfile = out
            handler.client_address = ("127.0.0.1", 0)
            handler.server = _FakeServer()
            handler.request_version = "HTTP/1.0"
            handler.command = "GET"
            handler.path = "/healthz"
            handler.headers = {}
            handler.requestline = "GET /healthz HTTP/1.0"
            handler.do_GET()
        body = out.getvalue().decode()
        assert "200" in body.split("\r\n")[0]
        assert '"status": "ok"' in body

    def test_returns_503_when_heartbeat_stale(self, monkeypatch):
        from src.sync import daemon
        monkeypatch.setattr(daemon, "_last_heartbeat", time.time() - 999)
        monkeypatch.setattr(daemon, "HEALTHZ_TIMEOUT_S", 60)
        from io import BytesIO

        class _FakeServer:
            server_address = ("127.0.0.1", 0)

        out = BytesIO()
        with patch("http.server.BaseHTTPRequestHandler.setup", lambda self: None), \
             patch("http.server.BaseHTTPRequestHandler.finish", lambda self: None):
            handler = daemon._HealthzHandler.__new__(daemon._HealthzHandler)
            handler.rfile = BytesIO(b"GET /healthz HTTP/1.0\r\n\r\n")
            handler.wfile = out
            handler.client_address = ("127.0.0.1", 0)
            handler.server = _FakeServer()
            handler.request_version = "HTTP/1.0"
            handler.command = "GET"
            handler.path = "/healthz"
            handler.headers = {}
            handler.requestline = "GET /healthz HTTP/1.0"
            handler.do_GET()
        body = out.getvalue().decode()
        assert "503" in body.split("\r\n")[0]
        assert '"status": "stale"' in body


# ── DR resync ────────────────────────────────────────────────────────────────

class TestDrResync:
    def test_skips_when_no_databricks_creds(self, daemon_conn, monkeypatch):
        from src.sync.dr_resync import run_dr_resync
        for k in ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN"):
            monkeypatch.delenv(k, raising=False)
        statuses: list[str] = []
        result = run_dr_resync(daemon_conn, status_setter=statuses.append)
        assert result.startswith("Skipped")
        assert any(s.startswith("Skipped") for s in statuses)

    def test_pulls_deltas_into_local(self, daemon_conn, monkeypatch):
        """Patch _databricks_query so we don't need a real warehouse."""
        from src.sync import dr_resync as drm

        delta = pd.DataFrame([
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "test",
                "object_type": "TABLE",
                "object_name": "a.b.c",
                "actor_email": "tester",
                "old_value": "",
                "new_value": "x",
                "created_at": datetime.now(UTC).replace(tzinfo=None),
            }
        ])

        def fake_query(sql, params=None):
            # Return the delta only for the audit_log table; empty otherwise.
            if "audit_log" in sql:
                return delta
            return pd.DataFrame()

        monkeypatch.setattr(drm, "_databricks_query", fake_query)
        result = drm.run_dr_resync(daemon_conn)
        assert result == "Up-to-date"

        with daemon_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM user_data.audit_log")
            assert cur.fetchall()[0][0] == 1

    def test_returns_error_on_remote_exception(self, daemon_conn, monkeypatch):
        from src.sync import dr_resync as drm

        def boom(*_a, **_k):
            raise RuntimeError("warehouse offline")
        monkeypatch.setattr(drm, "_databricks_query", boom)

        statuses: list[str] = []
        result = drm.run_dr_resync(daemon_conn, status_setter=statuses.append)
        assert result.startswith("Error:")
        assert any(s.startswith("Error:") for s in statuses)


# ── Push queue with injected conn ───────────────────────────────────────────

class TestProcessSyncQueueInjected:
    def _enqueue(self, conn, payload):
        sync_id = str(uuid.uuid4())
        with conn.cursor() as cur:
            cur.execute_write(
                """
                INSERT INTO user_data.pending_sync
                  (sync_id, sync_type, table_full_name, payload_json,
                   queued_by, queued_at, status, attempts)
                VALUES (%(id)s, %(t)s, %(fn)s, %(p)s,
                        'tester', current_localtimestamp(), 'pending', 0)
                """,
                {
                    "id": sync_id,
                    "t": payload["sync_type"],
                    "fn": payload.get("table_full_name"),
                    "p": json.dumps(payload.get("payload", {})),
                },
            )
        return sync_id

    def test_drains_with_injected_conn(self, daemon_conn, monkeypatch):
        from src.sync import push as push_module
        sid = self._enqueue(
            daemon_conn,
            {
                "sync_type": "COLUMN_DEF",
                "table_full_name": "cat.sch.tbl",
                "payload": {"column_name": "col_a", "definition": "test"},
            },
        )

        # Stub the actual Databricks push so we don't need a live warehouse.
        calls: list[tuple] = []
        monkeypatch.setattr(
            push_module,
            "_push_to_databricks",
            lambda stype, fn, payload: calls.append((stype, fn, payload)),
        )

        n = push_module._process_sync_queue(conn=daemon_conn)
        assert n == 1
        assert calls == [(
            "COLUMN_DEF", "cat.sch.tbl",
            {"column_name": "col_a", "definition": "test"},
        )]

        with daemon_conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM user_data.pending_sync WHERE sync_id=%(id)s",
                {"id": sid},
            )
            assert cur.fetchall()[0][0] == "done"

    def test_failure_marks_pending_with_error(self, daemon_conn, monkeypatch):
        from src.sync import push as push_module
        sid = self._enqueue(
            daemon_conn,
            {
                "sync_type": "COLUMN_DEF",
                "table_full_name": "cat.sch.tbl",
                "payload": {"column_name": "col_a", "definition": "boom"},
            },
        )

        def boom(*_a, **_k):
            raise RuntimeError("warehouse offline")
        monkeypatch.setattr(push_module, "_push_to_databricks", boom)

        push_module._process_sync_queue(conn=daemon_conn)
        with daemon_conn.cursor() as cur:
            cur.execute(
                "SELECT status, attempts, last_error FROM user_data.pending_sync "
                "WHERE sync_id=%(id)s",
                {"id": sid},
            )
            status, attempts, last_error = cur.fetchall()[0]
        assert status == "pending"  # under MAX_ATTEMPTS still retryable
        assert attempts == 1
        assert "warehouse offline" in (last_error or "")


# ── Daemon run() integration ─────────────────────────────────────────────────

class TestDaemonRun:
    def test_run_once_records_heartbeat(self, tmp_user_data, monkeypatch):
        """run(once=True) executes a full cycle and writes a heartbeat even
        when there's nothing to drain."""
        # No Databricks creds so DR resync short-circuits to 'Skipped'.
        for k in ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN"):
            monkeypatch.delenv(k, raising=False)

        from src.sync import daemon
        rc = daemon.run(once=True, healthz_port=None)
        assert rc == 0

        # Verify heartbeat made it into the file.
        from src.sync.daemon_db import DaemonConn
        c = DaemonConn()
        with c.cursor() as cur:
            cur.execute(
                "SELECT value FROM user_data.site_settings WHERE key='worker_heartbeat'"
            )
            rows = cur.fetchall()
        c.close()
        assert rows and rows[0][0]  # ISO timestamp string


# ── Worker UI shim ───────────────────────────────────────────────────────────

class TestWorkerShim:
    def test_read_dr_resync_status_falls_back_to_idle(self, tmp_user_data):
        from src.sync.worker import read_dr_resync_status
        # No row written yet — should return 'Idle'.
        assert read_dr_resync_status() == "Idle"

    def test_read_dr_resync_status_picks_up_daemon_write(self, tmp_user_data):
        from src.sync.daemon import _set_status
        from src.sync.daemon_db import DaemonConn
        from src.sync.worker import read_dr_resync_status

        c = DaemonConn()
        _set_status(c, "dr_resync_status", "Up-to-date")
        c.close()

        assert read_dr_resync_status() == "Up-to-date"

    def test_legacy_shims_are_noops(self):
        from src.sync.worker import (
            _mark_ui_activity, _get_last_ui_activity,
            _start_sync_worker_thread,
        )
        assert _mark_ui_activity() is None
        assert _get_last_ui_activity() == 0.0
        assert _start_sync_worker_thread() is None
