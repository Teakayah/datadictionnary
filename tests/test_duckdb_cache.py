"""
Tests for the DuckDB local-cache layer.

Coverage:
  - _to_duckdb_sql: pyformat → $name translation, IN → = ANY rewrite
  - _DuckDBCursor / _DuckDBConn: adapter round-trip against a real DuckDB file
  - write_duckdb: creates tables, atomic swap, preserves append-only data
  - _duckdb_available: path absent / present
"""
from __future__ import annotations

import os
import sys
import re as _re
import textwrap
import pandas as pd
import pytest
import duckdb
from unittest.mock import MagicMock, patch

# ── Fixture: stubs needed by sync_metadata ────────────────────────────────────

@pytest.fixture()
def sync_mocks():
    """Stub Databricks SDK + dotenv so sync_metadata can be imported."""
    mocks = {
        "databricks": MagicMock(),
        "databricks.sdk": MagicMock(),
        "databricks.sql": MagicMock(),
        "dotenv": MagicMock(),
    }
    with patch.dict("sys.modules", mocks):
        # Force re-import so the module picks up the mocked sys.modules
        sys.modules.pop("scripts.sync_metadata", None)
        yield mocks


# ── Helper: extract & exec pure-Python helpers from app.py ───────────────────

def _load_duckdb_helpers():
    """Extract _to_duckdb_sql, _DuckDBCursor, _DuckDBConn, _duckdb_available
    from app.py by exec-ing the relevant source block in a minimal namespace.
    No Streamlit or Databricks imports needed.
    """
    import types
    import threading as _threading
    import duckdb as _duckdb_module

    src_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
    with open(src_path) as f:
        source = f.read()

    # Grab the block from _duckdb_available up to (but not including) the
    # Databricks @st.cache_resource(ttl=...) so we capture _DuckDBCursor and
    # _DuckDBConn which now live after _get_shared_duckdb_connection.
    start = source.find("\ndef _duckdb_available(")
    end   = source.find("\n@st.cache_resource(ttl=", start)
    block = source[start:end]

    # Mock st so @st.cache_resource decorator doesn't require a running Streamlit
    mock_st = types.SimpleNamespace()
    def _mock_cache_resource(*args, **kwargs):
        # @st.cache_resource          → called with the function directly
        # @st.cache_resource(...)     → called with kwargs, returns a decorator
        if args and callable(args[0]):
            return args[0]
        return lambda f: f
    mock_st.cache_resource = _mock_cache_resource

    # Phase 1 src/config.py extraction: CATALOG_CACHE and SCHEMA_CACHE moved out
    # of the inline duckdb block into src/config.py. Provide them here so the
    # exec'd slice still resolves those names. logging is always a stdlib import
    # but was previously available as a module-level name in the app — add it too.
    import logging as _logging_mod
    from src.config import CATALOG_CACHE as _CATALOG_CACHE, SCHEMA_CACHE as _SCHEMA_CACHE

    ns = {
        "os": os,
        "pd": pd,
        "re": _re,
        "MagicMock": MagicMock,
        "st": mock_st,
        "duckdb": _duckdb_module,
        "threading": _threading,
        "logging": _logging_mod,
        # Default values so _duckdb_available() and _get_shared_duckdb_connection()
        # don't raise NameError; individual tests override as needed.
        "DUCKDB_PATH": "",
        "USER_DATA_PATH": "",
        "_db_write_lock": _threading.Lock(),
        "CATALOG_CACHE": _CATALOG_CACHE,
        "SCHEMA_CACHE": _SCHEMA_CACHE,
    }
    exec(textwrap.dedent(block), ns)
    return ns


# ═══════════════════════════════════════════════════════════════════════════════
# _to_duckdb_sql
# ═══════════════════════════════════════════════════════════════════════════════

class TestToDuckdbSql:
    """Unit tests for pyformat → DuckDB $name SQL translation."""

    @pytest.fixture(autouse=True)
    def helpers(self):
        self.h = _load_duckdb_helpers()

    def _convert(self, sql, params):
        return self.h["_to_duckdb_sql"](sql, params)

    def test_simple_scalar(self):
        sql, params = self._convert("SELECT * FROM t WHERE x = %(x)s", {"x": 42})
        assert "$x" in sql
        assert "%(x)s" not in sql
        assert params["x"] == 42

    def test_multiple_scalars(self):
        sql, params = self._convert(
            "SELECT * FROM t WHERE a = %(a)s AND b = %(b)s",
            {"a": "hello", "b": 99}
        )
        assert "$a" in sql and "$b" in sql
        assert params == {"a": "hello", "b": 99}

    def test_in_tuple_rewritten_to_any(self):
        sql, params = self._convert(
            "WHERE p.principal IN %(groups)s",
            {"groups": ("finance_id", "all_id")}
        )
        assert "= ANY($groups)" in sql
        assert "IN" not in sql
        assert params["groups"] == ["finance_id", "all_id"]

    def test_in_rewrite_case_insensitive(self):
        sql, params = self._convert(
            "WHERE p.principal in %(groups)s",
            {"groups": ("a",)}
        )
        assert "= ANY($groups)" in sql

    def test_mixed_scalar_and_list(self):
        sql, params = self._convert(
            "WHERE name = %(name)s AND tag IN %(tags)s",
            {"name": "foo", "tags": ["x", "y"]}
        )
        assert "$name" in sql
        assert "= ANY($tags)" in sql
        assert params["name"] == "foo"
        assert params["tags"] == ["x", "y"]

    def test_empty_params_returns_original_sql(self):
        original = "SELECT 1"
        sql, params = self._convert(original, {})
        assert sql == original
        assert params == {}

    def test_none_params_returns_original_sql(self):
        sql, params = self.h["_to_duckdb_sql"]("SELECT 1", None)
        assert sql == "SELECT 1"
        assert params == {}


# ═══════════════════════════════════════════════════════════════════════════════
# _DuckDBCursor / _DuckDBConn adapter
# ═══════════════════════════════════════════════════════════════════════════════

class TestDuckDBAdapter:
    """Integration tests for the cursor adapter against a real DuckDB file."""

    @pytest.fixture(autouse=True)
    def helpers(self):
        self.h = _load_duckdb_helpers()

    def _cursor(self, db_path: str):
        con = duckdb.connect(db_path)
        return self.h["_DuckDBCursor"](con)

    def test_execute_simple_query(self, tmp_path):
        cur = self._cursor(str(tmp_path / "t.duckdb"))
        cur.execute("SELECT 42 AS answer")
        df = cur.fetchall_as_pandas()
        assert df.iloc[0]["answer"] == 42

    def test_scalar_dict_param(self, tmp_path):
        cur = self._cursor(str(tmp_path / "t.duckdb"))
        cur.execute("SELECT %(val)s AS v", {"val": "hello"})
        df = cur.fetchall_as_pandas()
        assert df.iloc[0]["v"] == "hello"

    def test_in_list_param_round_trip(self, tmp_path):
        db = str(tmp_path / "t.duckdb")
        # Seed table
        con = duckdb.connect(db)
        con.execute("CREATE TABLE grp (principal VARCHAR)")
        con.execute("INSERT INTO grp VALUES ('a'), ('b'), ('c')")
        con.close()
        # Query via adapter
        cur = self._cursor(db)
        cur.execute(
            "SELECT principal FROM grp WHERE principal IN %(groups)s",
            {"groups": ("a", "c")}
        )
        df = cur.fetchall_as_pandas()
        assert set(df["principal"]) == {"a", "c"}

    def test_fetchall_before_execute_returns_empty(self, tmp_path):
        cur = self._cursor(str(tmp_path / "t.duckdb"))
        df = cur.fetchall_as_pandas()
        assert isinstance(df, pd.DataFrame) and df.empty

    def test_context_manager_does_not_close_shared_connection(self, tmp_path):
        # __exit__ is intentionally a no-op — the singleton must stay open
        cur = self._cursor(str(tmp_path / "t.duckdb"))
        with cur:
            cur.execute("SELECT 1")
        # Cursor must still be usable after the context manager exits
        cur.execute("SELECT 2")
        df = cur.fetchall_as_pandas()
        assert df.iloc[0].iloc[0] == 2

    def test_duckconn_cursor_returns_cursor(self, tmp_path):
        db = str(tmp_path / "t.duckdb")
        user_db = str(tmp_path / "user.duckdb")
        duckdb.connect(db).close()  # create catalog file
        # _DuckDBConn routes through the singleton — patch the module-level paths
        self.h["DUCKDB_PATH"] = db
        self.h["USER_DATA_PATH"] = user_db
        conn = self.h["_DuckDBConn"](db)
        cur = conn.cursor()
        assert hasattr(cur, "execute")
        assert hasattr(cur, "fetchall_as_pandas")

    def test_duckconn_open_property(self, tmp_path):
        db = str(tmp_path / "t.duckdb")
        # File absent → singleton returns None → open is False
        self.h["DUCKDB_PATH"] = db
        self.h["USER_DATA_PATH"] = str(tmp_path / "user.duckdb")
        conn_absent = self.h["_DuckDBConn"](db)
        assert conn_absent.open is False
        # File present → singleton succeeds → open is True
        duckdb.connect(db).close()
        conn_present = self.h["_DuckDBConn"](db)
        assert conn_present.open is True


# ═══════════════════════════════════════════════════════════════════════════════
# _duckdb_available
# ═══════════════════════════════════════════════════════════════════════════════

class TestDuckdbAvailable:

    def _available(self, path):
        h = _load_duckdb_helpers()
        h["DUCKDB_PATH"] = path
        # Re-exec so the closure picks up the patched DUCKDB_PATH
        src_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
        with open(src_path) as f:
            source = f.read()
        start = source.find("\ndef _duckdb_available(")
        end   = source.find("\n\ndef _to_duckdb_sql(", start)
        ns = {"os": os, "pd": pd, "DUCKDB_PATH": path}
        exec(source[start:end], ns)
        return ns["_duckdb_available"]()

    def test_false_when_path_empty(self):
        assert self._available("") is False

    def test_false_when_file_missing(self, tmp_path):
        assert self._available(str(tmp_path / "no.duckdb")) is False

    def test_true_when_file_exists(self, tmp_path):
        db = str(tmp_path / "yes.duckdb")
        duckdb.connect(db).close()
        assert self._available(db) is True


# ═══════════════════════════════════════════════════════════════════════════════
# write_duckdb (sync_metadata.py)
# ═══════════════════════════════════════════════════════════════════════════════

class TestWriteDuckdb:
    """Tests for the sync-job DuckDB export function."""

    @pytest.fixture(autouse=True)
    def _import(self, sync_mocks):
        from scripts.sync_metadata import write_duckdb
        self.write_duckdb = write_duckdb

    def _tables(self):
        return [{"full_name": "c.s.t", "catalog_name": "c", "schema_name": "s",
                 "table_name": "t", "table_type": "MANAGED", "comment": "",
                 "steward_email": ""}]

    def _columns(self):
        return [{"table_full_name": "c.s.t", "column_name": "id",
                 "data_type": "INT", "comment": ""}]

    def _permissions(self):
        return [{"table_full_name": "c.s.t", "principal": "grp", "privilege": "SELECT"}]

    def test_creates_file(self, tmp_path):
        db = str(tmp_path / "cache.duckdb")
        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb(self._tables(), [], [], [], [])
        assert os.path.exists(db)

    def test_no_tmp_file_after_swap(self, tmp_path):
        db = str(tmp_path / "cache.duckdb")
        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb(self._tables(), [], [], [], [])
        assert not os.path.exists(db + ".tmp")

    def test_tables_metadata_populated(self, tmp_path):
        db = str(tmp_path / "cache.duckdb")
        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb(self._tables(), [], [], [], [])
        con = duckdb.connect(db, read_only=True)
        df = con.execute("SELECT * FROM tables_metadata").df()
        con.close()
        assert len(df) == 1
        assert df.iloc[0]["full_name"] == "c.s.t"

    def test_permissions_cache_populated(self, tmp_path):
        db = str(tmp_path / "cache.duckdb")
        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb([], [], self._permissions(), [], [])
        con = duckdb.connect(db, read_only=True)
        df = con.execute("SELECT * FROM permissions_cache").df()
        con.close()
        assert df.iloc[0]["principal"] == "grp"

    def test_empty_input_creates_all_tables(self, tmp_path):
        db = str(tmp_path / "cache.duckdb")
        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb([], [], [], [], [])
        con = duckdb.connect(db, read_only=True)
        for tbl in ("tables_metadata", "columns_metadata", "permissions_cache",
                    "lineage_cache", "object_tags", "audit_log"):
            df = con.execute(f"SELECT * FROM {tbl}").df()
            assert isinstance(df, pd.DataFrame), f"{tbl} missing"
        con.close()

    def test_user_data_tables_absent_from_catalog_file(self, tmp_path):
        """comments and business_name_overrides must NOT exist in the catalog file.

        They now live in the separate user_data file (USER_DATA_PATH) which the
        sync job never touches — so they are never written by write_duckdb.
        """
        db = str(tmp_path / "cache.duckdb")
        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb(self._tables(), self._columns(), [], [], [])
        con = duckdb.connect(db, read_only=True)
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).df()["table_name"].tolist()
        con.close()
        assert "comments" not in tables
        assert "business_name_overrides" not in tables

    def test_skipped_when_path_empty(self, tmp_path):
        """write_duckdb is a no-op when DUCKDB_PATH is unset."""
        with patch.dict(os.environ, {"DUCKDB_PATH": ""}):
            self.write_duckdb(self._tables(), [], [], [], [])
        assert list(tmp_path.iterdir()) == []

    def test_indexes_created(self, tmp_path):
        db = str(tmp_path / "cache.duckdb")
        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb([], [], self._permissions(), [], [])
        con = duckdb.connect(db, read_only=True)
        idx = con.execute(
            "SELECT index_name FROM duckdb_indexes() "
            "WHERE table_name IN ('permissions_cache','columns_metadata')"
        ).df()
        con.close()
        assert len(idx) >= 2, f"Expected indexes not found: {idx}"
