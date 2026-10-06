"""Databricks SQL Warehouse adapter — read path only.

Writes from Streamlit pods are no longer made directly to Databricks. Per
ADR 004, the sidecar sync daemon is the sole intentional Databricks
writer; pods enqueue into ``user_data.pending_sync`` (DuckDB-local) and
the daemon drains it. The previous ``_get_databricks_write_connection``
helper was a per-call ``sql.connect()`` and is now removed — its only
callers were the dead ``Databricks*`` storage fallbacks, which were
deleted alongside it.
"""
from __future__ import annotations


import os

import streamlit as st
from databricks import sql


def _get_databricks_connection():
    """Create a new connection to the Databricks SQL Warehouse.

    WHY IT EXISTS:
    We construct a new `databricks.sql.connect` instance for each query rather than
    using a global connection pool because Databricks SQL Warehouse connections can
    time out or become invalidated by server-side scaling. By creating short-lived
    connections per operation, we avoid "connection closed" errors in the Streamlit
    pods while relying on Streamlit's `@st.cache_data` to minimize actual network calls.
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
