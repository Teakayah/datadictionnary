"""UI-side helpers that report on the sidecar sync daemon.

The actual drain loop and DR resync now run in a separate process — see
src/sync/daemon.py. This module exposes:

* read_dr_resync_status() — pulls the latest status string the daemon wrote
  to user_data.site_settings; the admin sync panel renders this.
* read_worker_heartbeat() — last heartbeat timestamp, ISO-8601.

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
    """Read a single key from user_data.site_settings.

    Args:
        key (str): The configuration key to read.
        default (str): The fallback value if the key is not found or DB is unavailable.

    Returns:
        str: The value from the database, or the default value.
    """
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
    """Return the daemon's last DR resync status, or 'Idle' before any run.

    Returns:
        str: The most recent status string reported by the daemon.
    """
    return _read_setting(DR_STATUS_KEY, default="Idle")


def read_worker_heartbeat() -> str:
    """Return the daemon's last heartbeat as an ISO timestamp string, or ''.

    Returns:
        str: An ISO-8601 formatted timestamp string, or an empty string if no heartbeat exists.
    """
    return _read_setting(WORKER_HEARTBEAT_KEY, default="")
