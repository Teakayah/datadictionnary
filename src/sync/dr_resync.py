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
from collections.abc import Callable


import logging
import os
import uuid

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


def _get_all_local_max_ts(local_conn) -> dict[str, str | None]:
    """Fetch the max timestamp for all DR tables in a single query."""
    queries = [
        f"SELECT '{tbl}' as tbl, MAX({ts_col}) as max_ts FROM user_data.{tbl}"
        for tbl, ts_col in _DR_TABLES
    ]
    sql = " UNION ALL ".join(queries)

    with local_conn.cursor() as cur:
        cur.execute(sql)
        # Returns a dict of {table_name: max_timestamp}
        return {row[0]: row[1] for row in cur.fetchall()}


def _merge_into_local(local_conn, table: str, df: pd.DataFrame) -> None:
    """Insert (or replace) DataFrame rows into user_data.<table>."""
    if df is None or df.empty:
        return
    # Append-only tables (immutable IDs) → IGNORE; override tables → REPLACE.
    verb = "INSERT OR IGNORE" if table in ("comments", "audit_log") else "INSERT OR REPLACE"

    def _escape_id(val: str) -> str:
        return '"' + str(val).replace('"', '""') + '"'

    with local_conn.cursor() as cur:
        # Use DuckDB's native fast dataframe loading if available, else fallback to loop
        cols = ", ".join(_escape_id(c) for c in df.columns)
        if hasattr(cur, '_con') and hasattr(cur._con, 'register'):
            tmp_name = f"_dr_tmp_df_{uuid.uuid4().hex}"
            sql = f"{verb} INTO user_data.{table} ({cols}) SELECT * FROM {_escape_id(tmp_name)}"
            cur._con.register(tmp_name, df)
            try:
                cur.execute_write(sql)
            finally:
                cur._con.unregister(tmp_name)
        else:
            placeholders = ", ".join("?" for _ in df.columns)
            sql = f"{verb} INTO user_data.{table} ({cols}) VALUES ({placeholders})"
            # Use executemany for bulk insertion which is significantly faster than a Python loop
            # ⚡ Bolt: Use df.to_numpy().tolist() for faster conversion instead of itertuples generator
            # to_numpy().tolist() leverages optimized C-level arrays
            params = [tuple(x) for x in df.to_numpy().tolist()]

            # Since mock objects in tests might not have executemany_write yet, we check
            if hasattr(cur, 'executemany_write'):
                cur.executemany_write(sql, params)
            else:
                for row in params:
                    cur.execute_write(sql, list(row))


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
        # Fetch all local max timestamps in a single query to avoid N+1 problem
        local_maxes = _get_all_local_max_ts(local_conn)

        for tbl, ts_col in _DR_TABLES:
            local_max = local_maxes.get(tbl)
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
