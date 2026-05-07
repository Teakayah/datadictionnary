"""UI-side helpers that report on the sidecar sync daemon.

The actual drain loop and DR resync now run in a separate process — see
src/sync/daemon.py. This module exposes:

* read_dr_resync_status() — pulls the latest status string the daemon wrote
  to user_data.site_settings; the admin sync panel renders this.
* read_worker_heartbeat() — last heartbeat timestamp, ISO-8601.
* _mark_ui_activity() — kept as a no-op so legacy callers in app.py and
  src/ui/cards.py still work; the daemon no longer cares about UI activity.

The previous in-process daemon thread (_start_sync_worker_thread) has been
removed; running it from a Streamlit thread without a ScriptRunContext is
undefined behaviour, and sharing a single DuckDB connection across the UI
and the worker corrupted concurrent reads.
"""

from __future__ import annotations

import logging

from src.db.duckdb_adapter import _duckdb_available

log = logging.getLogger(__name__)

# Public status keys (also written by src/sync/daemon.py).
DR_STATUS_KEY = "dr_resync_status"
WORKER_HEARTBEAT_KEY = "worker_heartbeat"


def _read_setting(key: str, default: str = "") -> str:
    """Read a single key from user_data.site_settings."""
    if not _duckdb_available():
        return default
    try:
        from src.db.queries import get_db_connection  # local — avoids import cycle
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT value FROM user_data.site_settings WHERE key = %(k)s",
                {"k": key},
            )
            rows = cur.fetchall()
            if rows:
                return str(rows[0][0])
    except Exception as exc:
        log.warning("Could not read site_settings[%s]: %s", key, exc)
    return default


def read_dr_resync_status() -> str:
    """Return the daemon's last DR resync status, or 'Idle' before any run."""
    return _read_setting(DR_STATUS_KEY, default="Idle")


def read_worker_heartbeat() -> str:
    """Return the daemon's last heartbeat as an ISO timestamp string, or ''."""
    return _read_setting(WORKER_HEARTBEAT_KEY, default="")


# ── Legacy shims ─────────────────────────────────────────────────────────────
# Kept so the existing import sites in app.py and src/ui/cards.py keep working
# during the migration. Both are no-ops in the sidecar architecture.

def _mark_ui_activity() -> None:
    """No-op. The sidecar daemon doesn't track UI activity any more."""
    return None


def _get_last_ui_activity() -> float:
    """Legacy shim. Returns 0 so any old idle-check evaluates to 'idle'."""
    return 0.0


def _get_dr_resync_status() -> str:
    """Legacy alias for read_dr_resync_status()."""
    return read_dr_resync_status()


def _start_sync_worker_thread():
    """Legacy shim. The in-process daemon thread has been removed; the sync
    worker now runs in its own process (see k8s/deployment-sync-worker.yaml
    and src/sync/daemon.py). Calling this is a no-op."""
    log.debug("_start_sync_worker_thread() called — no-op in sidecar architecture.")
    return None
