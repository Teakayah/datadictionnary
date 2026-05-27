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
    """Convert pyformat SQL (%(name)s) and parameter dictionary to DuckDB named parameters ($name).

    DuckDB does not natively unroll Python lists passed to an `IN` clause parameter marker
    (unlike some other DB-APIs). This function intercepts list/tuple parameters targeting an
    `IN %(name)s` clause and rewrites the SQL to use DuckDB's native `= ANY($name)` array
    operator instead, ensuring cross-driver compatibility.

    @param sql - The SQL query string using pyformat placeholders.
    @param params - A dictionary of parameters to interpolate.
    @returns A tuple containing the converted SQL string and the converted parameters dictionary.
    """
    if not params:
        return sql, {}
    converted = {}
    result = sql
    for name, value in params.items():
        if isinstance(value, (list, tuple)):
            # Explain the regex:
            # \b         - Word boundary to ensure we match 'IN' as a whole word
            # IN\s+      - Matches 'IN' followed by one or more whitespace characters
            # %\(        - Matches the literal string '%('
            # {name}     - Interpolates the parameter name
            # \)s        - Matches the literal string ')s'
            #
            # Example translation: "IN %(groups)s" -> "= ANY($groups)"
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
            status          VARCHAR DEFAULT 'published',
            PRIMARY KEY (table_full_name, column_name)
        )
    """)
    con.execute("""
        ALTER TABLE user_data.business_name_overrides
        ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'published'
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_data.table_metadata_overrides (
            table_full_name VARCHAR PRIMARY KEY,
            description     VARCHAR,
            steward_email   VARCHAR,
            updated_by      VARCHAR,
            updated_at      TIMESTAMP
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
        CREATE TABLE IF NOT EXISTS user_data.pipeline_definitions (
            pipeline_id         VARCHAR PRIMARY KEY,
            title               VARCHAR NOT NULL,
            description         VARCHAR,
            backend             VARCHAR NOT NULL,
            databricks_job_id   VARCHAR,
            adf_subscription_id VARCHAR,
            adf_resource_group  VARCHAR,
            adf_factory_name    VARCHAR,
            adf_pipeline_name   VARCHAR,
            ado_organization    VARCHAR,
            ado_project         VARCHAR,
            ado_pipeline_id     VARCHAR,
            created_by          VARCHAR,
            created_at          TIMESTAMP NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_data.pipeline_runs (
            pipeline_id    VARCHAR PRIMARY KEY,
            backend_run_id VARCHAR NOT NULL,
            triggered_by   VARCHAR,
            triggered_at   TIMESTAMP NOT NULL,
            status         VARCHAR,
            last_checked   TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_data.cms_posts (
            post_id      VARCHAR PRIMARY KEY,
            post_type    VARCHAR NOT NULL,
            title        VARCHAR NOT NULL,
            body         VARCHAR,
            table_ref    VARCHAR,
            author_email VARCHAR NOT NULL,
            created_at   TIMESTAMP NOT NULL,
            expires_at   TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_data.site_settings (
            key        VARCHAR PRIMARY KEY,
            value      VARCHAR NOT NULL,
            updated_at TIMESTAMP,
            updated_by VARCHAR
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
            last_attempt_at TIMESTAMP,
            completed_at    TIMESTAMP
        )
    """)
    # Migration for pre-existing user_data files that pre-date last_attempt_at.
    # DuckDB's ALTER TABLE ADD COLUMN IF NOT EXISTS is supported >=0.10.
    con.execute("""
        ALTER TABLE user_data.pending_sync
        ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMP
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

            def _escape_id(val: str) -> str:
                return '"' + val.replace('"', '""') + '"'

            def _escape_string(val: str) -> str:
                return "'" + val.replace("'", "''") + "'"

            duckdb_path_str = DUCKDB_PATH if DUCKDB_PATH else ""
            user_data_path_str = USER_DATA_PATH if USER_DATA_PATH else ""

            # Attach the main read-only cache
            con.execute(f"ATTACH {_escape_string(duckdb_path_str)} AS {_escape_id(CATALOG_CACHE)} (READ_ONLY)")
            # Attach the persistent user data database
            con.execute(f"ATTACH IF NOT EXISTS {_escape_string(user_data_path_str)} AS {_escape_id('user_data')}")

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
