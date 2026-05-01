"""Databricks SQL Warehouse adapter.

Cached read connection + uncached write connection. Writes must always reach
the Databricks SQL Warehouse — never the local DuckDB read-only cache.
"""

from __future__ import annotations

import os

import streamlit as st
from databricks import sql


def _get_databricks_connection():
    return sql.connect(
        server_hostname=os.getenv("DATABRICKS_HOST"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_TOKEN"),
    )


def _get_databricks_write_connection():
    """Return a fresh (uncached) Databricks connection for write operations.

    Write operations (INSERT, MERGE INTO) must always target the Databricks SQL
    Warehouse — never the local DuckDB file, which is a read-only cache that is
    rebuilt from Databricks on each sync and would silently discard any local
    writes.  This function bypasses the read-path DuckDB check intentionally.
    """
    return sql.connect(
        server_hostname=os.getenv("DATABRICKS_HOST"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_TOKEN"),
    )


@st.cache_data(ttl="1h", show_spinner=False)
def _run_databricks_query(query, params=None):
    """Cached Databricks query — 1 h TTL to amortise network latency."""
    conn = _get_databricks_connection()
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall_as_pandas()
