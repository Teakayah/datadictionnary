"""Disaster-recovery resync — pull recent rows from Databricks back into the
local DuckDB user_data file.

Extracted from src/sync/worker.py so the same code is exercised from the
daemon and from unit tests with a fake connection.

The local connection is injected (`_DuckDBConn` in-process or
`DaemonConn` in the sidecar). The Databricks read is direct — no Streamlit
caching, no demo-mode branching — because the daemon never runs inside a
Streamlit context.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

import pandas as pd

from src.config import CATALOG_CACHE, SCHEMA_CACHE

log = logging.getLogger(__name__)

# Tables we mirror from Databricks back to the local user_data DB.
# (table_name, timestamp_column)
_DR_TABLES: tuple[tuple[str, str], ...] = (
    ("comments", "created_at"),
    ("audit_log", "created_at"),
    ("business_name_overrides", "edited_at"),
)


def _databricks_query(sql: str, params: dict | None = None) -> pd.DataFrame | None:
    """Run a query against Databricks. Returns None if creds are unset.

    DR resync is best-effort — when DATABRICKS_* env vars are missing (e.g.
    a dev environment with no warehouse), the daemon should keep running
    and just skip the resync rather than crash.
    """
    host = os.getenv("DATABRICKS_HOST", "").strip()
    http = os.getenv("DATABRICKS_HTTP_PATH", "").strip()
    tok = os.getenv("DATABRICKS_TOKEN", "").strip()
    if not (host and http and tok):
        return None
    from databricks import sql as dbsql  # local import — keeps test mocking easy

    with dbsql.connect(server_hostname=host, http_path=http, access_token=tok) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            return cur.fetchall_as_pandas()


def _local_max_ts(local_conn, table: str, ts_col: str):
    with local_conn.cursor() as cur:
        cur.execute(f"SELECT MAX({ts_col}) FROM user_data.{table}")
        rows = cur.fetchall()
        return rows[0][0] if rows else None


def _merge_into_local(local_conn, table: str, df: pd.DataFrame) -> None:
    """Insert (or replace) DataFrame rows into user_data.<table>."""
    if df is None or df.empty:
        return
    cols = ", ".join(df.columns)
    placeholders = ", ".join(f"%({c})s" for c in df.columns)
    # Append-only tables (immutable IDs) → IGNORE; override tables → REPLACE.
    verb = "INSERT OR IGNORE" if table in ("comments", "audit_log") else "INSERT OR REPLACE"
    sql = f"{verb} INTO user_data.{table} ({cols}) VALUES ({placeholders})"
    with local_conn.cursor() as cur:
        for row in df.to_dict("records"):
            cur.execute_write(sql, row)


def run_dr_resync(
    local_conn,
    status_setter: Callable[[str], None] | None = None,
) -> str:
    """Pull missing rows from Databricks back into local user_data.

    Returns the final status string ("Up-to-date", "Skipped (no creds)", or
    an error message). Also calls status_setter at each phase so the UI can
    display progress in near real time.
    """

    def _status(s: str) -> str:
        if status_setter:
            status_setter(s)
        log.info("DR resync: %s", s)
        return s

    _status("Checking")
    try:
        for tbl, ts_col in _DR_TABLES:
            local_max = _local_max_ts(local_conn, tbl, ts_col)
            remote_q = f"SELECT * FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.{tbl}"
            params: dict = {}
            if local_max:
                remote_q += f" WHERE {ts_col} > %(local_max)s"
                params["local_max"] = local_max
            df = _databricks_query(remote_q, params)
            if df is None:
                return _status("Skipped (no Databricks creds)")
            if not df.empty:
                _status(f"Syncing {tbl}")
                _merge_into_local(local_conn, tbl, df)
        return _status("Up-to-date")
    except Exception as exc:
        log.error("DR resync failed: %s", exc, exc_info=True)
        return _status(f"Error: {str(exc)[:50]}")
