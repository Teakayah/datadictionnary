"""DB connection router and base query executor.

Provides the write-connection helper and a backend-agnostic run_query()
that dispatches to DuckDB (if available) or Databricks.  Demo-mode
interception (returning _DEMO_* fixtures) lives in app.py's wrapper so
that this module stays importable without triggering a circular re-import
of app.py.

NOTE — Phase 4b (deferred): get_authorized_tables(), search_all_metadata(),
get_column_business_names(), and get_multi_hop_lineage() still live in
app.py because they depend on the _DEMO_* DataFrames defined there.
"""

from __future__ import annotations

import pandas as pd

from src.db.duckdb_adapter import _duckdb_available, _DuckDBConn, _run_duckdb_query
from src.db.databricks_adapter import _get_databricks_write_connection, _run_databricks_query


def _get_write_connection():
    """Return a DB connection for write operations (DuckDB → Databricks fallback)."""
    if _duckdb_available():
        from src.config import DUCKDB_PATH
        return _DuckDBConn(DUCKDB_PATH)
    return _get_databricks_write_connection()

def get_db_connection():
    """Return a DB connection for read queries (DuckDB → Databricks fallback)."""
    if _duckdb_available():
        from src.config import DUCKDB_PATH
        return _DuckDBConn(DUCKDB_PATH)
    from src.db.databricks_adapter import _get_databricks_connection
    return _get_databricks_connection()


def run_query(query: str, params=None) -> pd.DataFrame:
    """Execute a SQL read query against DuckDB (if available) or Databricks.

    This is the backend-only dispatcher — it has no demo-mode logic.
    app.py wraps this with _DEMO_* fixture interception for demo mode.
    ui/cards.py imports this directly for admin/health queries that guard
    the demo branch themselves via is_demo_mode().
    """
    if _duckdb_available():
        return _run_duckdb_query(query, params)
    return _run_databricks_query(query, params)
