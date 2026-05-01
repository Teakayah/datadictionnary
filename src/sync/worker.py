"""Background worker thread and DR resync logic for Databricks write-back."""

import logging
import threading
import time

import streamlit as st
import pandas as pd

from src.config import CATALOG_CACHE, SCHEMA_CACHE
from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import _get_write_connection

_worker_state_lock = threading.Lock()
_LAST_UI_ACTIVITY = time.time()
_DR_RESYNC_STATUS = "Idle" # Idle, Checking, Syncing, Up-to-date, Error
_DR_RESYNC_PROGRESS = 0.0

def _get_last_ui_activity():
    with _worker_state_lock:
        return _LAST_UI_ACTIVITY

def _get_dr_resync_status():
    with _worker_state_lock:
        return _DR_RESYNC_STATUS

def _set_dr_resync_status(status):
    global _DR_RESYNC_STATUS
    with _worker_state_lock:
        _DR_RESYNC_STATUS = status

def _set_dr_resync_progress(progress):
    global _DR_RESYNC_PROGRESS
    with _worker_state_lock:
        _DR_RESYNC_PROGRESS = progress

def _mark_ui_activity():
    global _LAST_UI_ACTIVITY
    with _worker_state_lock:
        _LAST_UI_ACTIVITY = time.time()


def _run_dr_resync():
    """Background task to pull missing records from Databricks to DuckDB."""
    if not _duckdb_available():
        return

    _set_dr_resync_status("Checking")
    try:
        conn = _get_write_connection()
        # 1. Check for newest records in Databricks vs Local
        # We check comments, audit_log, and overrides
        from app import run_query

        tables_to_check = [
            ("comments", "created_at", "comment_id"),
            ("audit_log", "created_at", "event_id"),
            ("business_name_overrides", "edited_at", "table_full_name, column_name")
        ]

        for tbl, ts_col, pk in tables_to_check:
            # Get max local timestamp
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT MAX({ts_col}) FROM user_data.{tbl}")
                local_max = cursor.fetchall()[0][0]

            # Query Databricks for any records AFTER local_max
            # Note: run_query handles the Databricks connection
            remote_q = f"SELECT * FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.{tbl}"
            params = {}
            if local_max:
                remote_q += f" WHERE {ts_col} > %(local_max)s"
                params["local_max"] = local_max

            delta_df = run_query(remote_q, params)
            if delta_df is not None and not delta_df.empty:
                _set_dr_resync_status(f"Syncing {tbl}")
                # Merge into DuckDB
                with conn.cursor() as cursor:
                    for _, row in delta_df.iterrows():
                        # Simple append for logs/comments (guaranteed unique IDs)
                        if tbl in ("comments", "audit_log"):
                            cols = ", ".join(delta_df.columns)
                            placeholders = ", ".join([f"%({c})s" for c in delta_df.columns])
                            cursor.execute_write(
                                f"INSERT OR IGNORE INTO user_data.{tbl} ({cols}) VALUES ({placeholders})",
                                row.to_dict()
                            )
                        else:
                            # Merge for overrides
                            cursor.execute_write(
                                f"INSERT OR REPLACE INTO user_data.{tbl} ({', '.join(delta_df.columns)}) "
                                f"VALUES ({', '.join([f'%({c})s' for c in delta_df.columns])})",
                                row.to_dict()
                            )

        _set_dr_resync_status("Up-to-date")
        _set_dr_resync_progress(100.0)
    except Exception as e:
        logging.error("DR Resync failed: %s", e)
        _set_dr_resync_status(f"Error: {str(e)[:50]}")

@st.cache_resource(show_spinner=False)
def _start_sync_worker_thread():
    """Singleton background thread that drains pending_sync every 15 s."""
    import threading

    def _loop():
        _count = 0
        from src.sync.push import _process_sync_queue
        while True:
            try:
                # Every 20 cycles (~10 mins in Active mode, ~1.6 mins in Idle mode), run DR resync
                if _count % 20 == 0:
                    _run_dr_resync()
                _count += 1

                n = _process_sync_queue()
                if n:
                    logging.info("Sync worker: pushed %d column definition(s) to Databricks.", n)
            except Exception as exc:
                logging.error("Sync worker loop error: %s", exc, exc_info=True)

            # Dynamic poll: 5s if idle, 30s if active
            is_idle = (time.time() - _get_last_ui_activity()) > 300
            time.sleep(5 if is_idle else 30)

    t = threading.Thread(target=_loop, name="dd-sync-worker", daemon=True)
    t.start()
    return t
