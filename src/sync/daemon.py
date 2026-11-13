"""Sidecar sync worker — long-lived process that drains user_data.pending_sync
into Databricks and runs DR resync.

Replaces the in-process daemon thread that was started from app.py. Running
that thread from Streamlit was unsafe: it shared a Streamlit-cached DuckDB
connection with the UI and ran from a thread that has no ScriptRunContext.

Entry points:
    python -m src.sync.daemon                # daemon mode, default
    python -m src.sync.daemon --once         # single cycle, exit (CI / cron)
    python -m src.sync.daemon --healthz-port 0   # disable HTTP healthz

Environment:
    DUCKDB_PATH                — required, catalog cache file (read-only attach)
    DATABRICKS_HOST/HTTP_PATH/TOKEN — required for DR resync + write-back
    SYNC_HEALTHZ_PORT          — default 8765 (the only tunable; port
                                 conflicts are real, timing values are not —
                                 those are module constants below)
"""
from __future__ import annotations
from typing import Optional
import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone; UTC = timezone.utc
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv
import contextlib

# Load .env BEFORE importing src.config so DUCKDB_PATH etc. resolve.
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

log = logging.getLogger("sync_daemon")

# Timing constants. Tests monkeypatch these module attributes directly.
POLL_ACTIVE_S = 5          # sleep after a productive cycle
POLL_IDLE_S = 30           # sleep after an empty cycle
DR_RESYNC_EVERY_N = 20     # run DR resync every N cycles
STALE_ROW_TIMEOUT_S = 300  # rows in 'syncing' >this flip back to 'pending'
HEALTHZ_TIMEOUT_S = 60     # heartbeat age above which /healthz returns 503

_stop_event = threading.Event()
_last_heartbeat: float = 0.0


# ── Status persistence (read by the UI) ──────────────────────────────────────

def _set_status(conn, key: str, value: str) -> None:
    """Upsert a daemon status key into user_data.site_settings."""
    conn.execute(
        """
        INSERT INTO user_data.site_settings (key, value, updated_at, updated_by)
        VALUES (%(k)s, %(v)s, current_localtimestamp(), 'sync-daemon')
        ON CONFLICT (key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at,
            updated_by = excluded.updated_by
        """,
        {"k": key, "v": value},
    )


def _record_heartbeat(conn) -> None:
    global _last_heartbeat
    _last_heartbeat = time.time()
    try:
        _set_status(conn, "worker_heartbeat", datetime.now(UTC).isoformat())
    except Exception as e:
        log.error(f"Failed to write heartbeat: {e}")


# ── Stale-row recovery ───────────────────────────────────────────────────────

def _recover_stale_rows(conn, timeout_s: int = STALE_ROW_TIMEOUT_S) -> int:
    """Reset rows stuck in 'syncing' for >timeout_s back to 'pending'.

    Returns the number of rows recovered. Without this, a daemon crash
    between the optimistic UPDATE and the Databricks push would leave rows
    permanently locked.
    """
    # Compute the cutoff in Python so we don't depend on DuckDB's INTERVAL
    # parameter syntax (which differs between releases).
    from datetime import timedelta
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=timeout_s)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sync_id FROM user_data.pending_sync
             WHERE status = 'syncing'
               AND last_attempt_at IS NOT NULL
               AND last_attempt_at < %(cutoff)s
            """,
            {"cutoff": cutoff},
        )
        stale_ids = [r[0] for r in (cur.fetchall() or [])]
        if not stale_ids:
            return 0
        # ⚡ Bolt: Use a single IN clause bulk update to prevent N+1 query overhead
        cur.execute_write(
            "UPDATE user_data.pending_sync SET status='pending' WHERE sync_id IN %(ids)s",
            {"ids": tuple(stale_ids)},
        )
    log.info("Recovered %d stale 'syncing' row(s).", len(stale_ids))
    return len(stale_ids)


# ── Healthz HTTP listener ────────────────────────────────────────────────────

class _HealthzHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 — stdlib API
        if self.path != "/healthz":
            self.send_response(404)
            self.end_headers()
            return
        age = (time.time() - _last_heartbeat) if _last_heartbeat else None
        if age is not None and age <= HEALTHZ_TIMEOUT_S:
            body = {"status": "ok", "heartbeat_age_s": round(age, 1)}
            code = 200
        else:
            body = {"status": "stale", "heartbeat_age_s": (round(age, 1) if age is not None else None)}
            code = 503
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        # Silence default access logs; we control them via the logger.
        pass


def _start_healthz(port: int) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("0.0.0.0", port), _HealthzHandler)
    threading.Thread(
        target=srv.serve_forever, name="dd-sync-healthz", daemon=True
    ).start()
    return srv


# ── Main loop ────────────────────────────────────────────────────────────────

def _handle_signal(signum, _frame) -> None:
    log.info("Received signal %s; shutting down.", signum)
    _stop_event.set()


def _silence_streamlit_warnings() -> None:
    """Silence the 'No runtime found' warnings emitted by Streamlit's
    @cache_data / @cache_resource decorators at import time. Must be called
    before any src.* import that pulls in Streamlit-decorated functions."""
    # Set the parent logger to ERROR and disable propagation so child loggers
    # that get their own handlers from streamlit init still respect the level.
    sl = logging.getLogger("streamlit")
    sl.setLevel(logging.ERROR)
    for name in (
        "streamlit.runtime.caching.cache_data_api",
        "streamlit.runtime.caching.cache_resource_api",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)


def run(once: bool = False, healthz_port: Optional[int] = None) -> int:
    """Daemon entry point. Returns 0 on graceful shutdown."""
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    _silence_streamlit_warnings()
    # Import these AFTER load_dotenv so DUCKDB_PATH is resolved.
    from src.sync.daemon_db import DaemonConn
    from src.sync.dr_resync import run_dr_resync
    from src.sync.push import _process_sync_queue

    conn = DaemonConn()
    if healthz_port:
        _start_healthz(healthz_port)
        log.info("Healthz listening on :%d", healthz_port)

    cycle = 0
    while not _stop_event.is_set():
        cycle += 1
        drained = 0
        try:
            _recover_stale_rows(conn)
            if cycle == 1 or cycle % DR_RESYNC_EVERY_N == 0:
                run_dr_resync(
                    conn,
                    status_setter=lambda s: _set_status(conn, "dr_resync_status", s),
                )
            drained = _process_sync_queue(conn=conn) or 0
            if drained:
                log.info("Drained %d sync row(s) this cycle.", drained)
            _record_heartbeat(conn)
        except Exception as exc:
            log.error("Daemon cycle error: %s", exc, exc_info=True)
            with contextlib.suppress(Exception):
                _set_status(conn, "dr_resync_status", f"Error: {str(exc)[:50]}")

        if once:
            break

        # Active cadence after a productive cycle, idle cadence otherwise.
        sleep_s = POLL_ACTIVE_S if drained else POLL_IDLE_S
        _stop_event.wait(sleep_s)

    conn.close()
    log.info("Daemon stopped after %d cycle(s).", cycle)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="sync-daemon")
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single cycle and exit (CI / cron mode).",
    )
    parser.add_argument(
        "--healthz-port", type=int,
        default=int(os.getenv("SYNC_HEALTHZ_PORT", "8765")),
        help="HTTP port for /healthz; pass 0 to disable.",
    )
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"))
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _silence_streamlit_warnings()
    return run(once=args.once, healthz_port=(args.healthz_port or None))


if __name__ == "__main__":
    sys.exit(main())
