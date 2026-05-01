"""DB write-connection router.

Chooses between the local DuckDB cache (fast, primary) and the Databricks
SQL Warehouse (authoritative) for write operations.

NOTE — Phase 4b (deferred): run_query(), get_authorized_tables(),
search_all_metadata(), get_column_business_names(), and get_multi_hop_lineage()
still live in app.py because they depend on the _DEMO_* DataFrames that are
defined at app.py module scope.  Extracting them cleanly requires first moving
the demo-data fixtures into a dedicated src/demo.py module so that queries.py
can import from it without triggering a circular re-import of app.py.
"""

from __future__ import annotations

from src.db.duckdb_adapter import _duckdb_available, _DuckDBConn
from src.db.databricks_adapter import _get_databricks_write_connection


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
