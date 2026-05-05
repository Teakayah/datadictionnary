"""DuckDB local-cache adapter.

When DUCKDB_PATH points to an existing file (written by the sync job), all
read queries and app writes are served locally — no network round-trip.
The adapter translates the existing %(name)s pyformat SQL into DuckDB's
$name named-parameter style so no query code needs to change.
"""

from __future__ import annotations

import os
import re
import logging
import threading

import pandas as pd
import streamlit as st

from src.config import DUCKDB_PATH, USER_DATA_PATH, CATALOG_CACHE


_db_write_lock = threading.Lock()


def _duckdb_available() -> bool:
    return bool(DUCKDB_PATH and os.path.exists(DUCKDB_PATH))


def _to_duckdb_sql(sql: str, params: dict) -> tuple:
    """Convert %(name)s pyformat SQL + dict params to DuckDB $name style.

    Special case: ``IN %(name)s`` where the value is a list/tuple is rewritten
    to ``= ANY($name)`` so the DuckDB array-contains operator is used.
    Returns (converted_sql, converted_params_dict).
    """
    if not params:
        return sql, {}
    converted = {}
    result = sql
    for name, value in params.items():
        if isinstance(value, (list, tuple)):
            # IN %(name)s  →  = ANY($name)
            result = re.sub(
                rf"\bIN\s+%\({re.escape(name)}\)s",
                f"= ANY(${name})",
                result,
                flags=re.IGNORECASE,
            )
            converted[name] = list(value)
        else:
            converted[name] = value
    # Remaining %(name)s → $name
    result = re.sub(r"%\((\w+)\)s", r"$\1", result)
    # DuckDB compatibility: current_timestamp() → current_localtimestamp()
    result = result.replace("current_timestamp()", "current_localtimestamp()")
    return result, converted


def _initialize_schema(con):
    """Initialize user data tables with primary keys (if they don't exist)."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_data.comments (
            comment_id        VARCHAR PRIMARY KEY,
            object_type       VARCHAR,
            object_name       VARCHAR,
            comment_text      VARCHAR,
            author_name       VARCHAR,
            author_email      VARCHAR,
            created_at        TIMESTAMP,
            steward_email     VARCHAR,
            parent_comment_id VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_data.business_name_overrides (
            table_full_name VARCHAR,
            column_name     VARCHAR,
            business_name   VARCHAR,
            definition      VARCHAR,
            edited_by       VARCHAR,
            edited_at       TIMESTAMP,
            PRIMARY KEY (table_full_name, column_name)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_data.audit_log (
            event_id        VARCHAR PRIMARY KEY,
            event_type      VARCHAR,
            object_type     VARCHAR,
            object_name     VARCHAR,
            actor_email     VARCHAR,
            old_value       VARCHAR,
            new_value       VARCHAR,
            created_at      TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_data.user_preferences (
            user_oid        VARCHAR NOT NULL,
            table_full_name VARCHAR NOT NULL,
            pref_type       VARCHAR NOT NULL,
            last_interacted TIMESTAMP NOT NULL,
            PRIMARY KEY (user_oid, table_full_name, pref_type)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_data.pending_sync (
            sync_id         VARCHAR PRIMARY KEY,
            sync_type       VARCHAR NOT NULL, -- COLUMN_DEF, TABLE_DESC, AUDIT, COMMENT, TAG, STEWARD
            table_full_name VARCHAR,
            payload_json    VARCHAR, -- Store type-specific data (e.g., tag key/value, comment author)
            queued_by       VARCHAR,
            queued_at       TIMESTAMP NOT NULL,
            status          VARCHAR NOT NULL DEFAULT 'pending',
            attempts        INTEGER  NOT NULL DEFAULT 0,
            last_error      VARCHAR,
            completed_at    TIMESTAMP
        )
    """)


@st.cache_resource(show_spinner=False, validate=lambda c: c is not None)
def _get_shared_duckdb_connection():
    """Singleton connection shared across all Streamlit sessions/threads."""
    if not _duckdb_available():
        return None

    with _db_write_lock:
        import duckdb
        try:
            # Use an in-memory connection as the primary
            con = duckdb.connect(":memory:")
            # Attach the main read-only cache
            con.execute(f"ATTACH '{DUCKDB_PATH}' AS {CATALOG_CACHE} (READ_ONLY)")
            # Attach the persistent user data database
            con.execute(f"ATTACH IF NOT EXISTS '{USER_DATA_PATH}' AS user_data")

            # Initialize user data tables with primary keys (if they don't exist)
            _initialize_schema(con)

            return con
        except Exception as e:
            logging.error("Failed to initialize shared DuckDB connection: %s", e)
            return None



class _DuckDBCursor:
    """Cursor-like wrapper around a shared DuckDB connection."""

    def __init__(self, con):
        self._con = con
        self._rel = None

    def execute(self, sql: str, params=None):
        if params is None:
            self._rel = self._con.execute(sql)
        elif isinstance(params, dict):
            converted_sql, converted_params = _to_duckdb_sql(sql, params)
            self._rel = self._con.execute(converted_sql, converted_params)
        else:
            self._rel = self._con.execute(sql, params)

    def execute_write(self, sql: str, params=None):
        """Thread-safe write execution wrapped in a lock."""
        with _db_write_lock:
            self.execute(sql, params)

    def fetchall(self):
        if self._rel is None:
            return []
        return self._rel.fetchall()

    def fetchall_as_pandas(self):
        if self._rel is None:
            return pd.DataFrame()
        return self._rel.df()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        # We do NOT close the shared connection!
        pass


class _DuckDBConn:
    """Connection-like wrapper that uses the shared singleton connection."""

    def __init__(self, path: str):
        self._con = _get_shared_duckdb_connection()

    def cursor(self):
        return _DuckDBCursor(self._con)

    def execute(self, sql: str, params=None):
        cur = _DuckDBCursor(self._con)
        cur.execute(sql, params)
        return cur

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    @property
    def open(self):
        return self._con is not None


def _run_duckdb_query(query, params=None):
    """Uncached DuckDB query — local file is fast enough that caching adds
    overhead rather than benefit, and skipping the cache means the app
    always sees the freshest file after the nightly sync."""
    with _db_write_lock:
        conn = _DuckDBConn(DUCKDB_PATH)
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall_as_pandas()
