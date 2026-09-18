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


# ── Helper: return src.db.duckdb_adapter symbols in a mutable namespace dict ──
# Phase 4: functions moved from app.py into src/db/duckdb_adapter.py.
# We expose them via a dict so all existing tests keep the same h["name"] access
# pattern without changes to the test bodies.

def _load_duckdb_helpers():
    """Return a dict with _to_duckdb_sql, _DuckDBCursor, _DuckDBConn, etc.

    Phase 4 rewrite: imports directly from src.db.duckdb_adapter instead of
    exec-slicing app.py.  The dict also exposes DUCKDB_PATH / USER_DATA_PATH
    as mutable keys so individual tests can patch them without touching the
    module (which caches them from src.config at import time).
    """
    import src.db.duckdb_adapter as _adapter
    from src.config import CATALOG_CACHE, SCHEMA_CACHE

    ns = {
        # Core adapter functions & classes
        "_to_duckdb_sql":                _adapter._to_duckdb_sql,
        "_duckdb_available":             _adapter._duckdb_available,
        "_get_shared_duckdb_connection": _adapter._get_shared_duckdb_connection,
        "_DuckDBCursor":                 _adapter._DuckDBCursor,
        "_DuckDBConn":                   _adapter._DuckDBConn,
        "_run_duckdb_query":             _adapter._run_duckdb_query,
        "_db_write_lock":                _adapter._db_write_lock,
        # Config constants (informational — adapter reads from src.config directly)
        "CATALOG_CACHE":  CATALOG_CACHE,
        "SCHEMA_CACHE":   SCHEMA_CACHE,
        # Path overrides: tests set these on the ns dict; use patch.object on the
        # adapter module to make _duckdb_available() pick up the new value.
        "DUCKDB_PATH":    _adapter.DUCKDB_PATH,
        "USER_DATA_PATH": _adapter.USER_DATA_PATH,
        # Reference to the module itself so tests can patch attributes directly
        "_module": _adapter,
    }
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

    def test_current_timestamp_replacement(self):
        sql, params = self._convert(
            "SELECT current_timestamp() as ts WHERE id = %(id)s",
            {"id": 1}
        )
        assert "current_localtimestamp()" in sql
        assert "current_timestamp()" not in sql
        assert params["id"] == 1

    def test_list_parameter_without_in(self):
        sql, params = self._convert(
            "SELECT %(val)s",
            {"val": [1, 2]}
        )
        assert "$val" in sql
        assert "= ANY" not in sql
        assert params["val"] == [1, 2]

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
        # Phase 4: _get_shared_duckdb_connection is now a module-level
        # @st.cache_resource singleton shared across all tests. Clear it before
        # each test so path-patching tests (test_duckconn_open_property) don't
        # see a stale connection from a previous test.
        import src.db.duckdb_adapter as _adapter
        _adapter._get_shared_duckdb_connection.clear()
        yield
        _adapter._get_shared_duckdb_connection.clear()

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
        # Patch the module-level DUCKDB_PATH so _duckdb_available() sees the file
        _mod = self.h["_module"]
        with patch.object(_mod, "DUCKDB_PATH", db), \
             patch.object(_mod, "USER_DATA_PATH", user_db):
            conn = self.h["_DuckDBConn"](db)
            cur = conn.cursor()
            assert hasattr(cur, "execute")
            assert hasattr(cur, "fetchall_as_pandas")

    def test_shared_connection_exception_logging(self, tmp_path):
        import src.db.duckdb_adapter as _adapter
        _adapter._clear_shared_duckdb_connection()
        db = str(tmp_path / "cache.duckdb")
        duckdb.connect(db).close()

        with patch.object(_adapter, "DUCKDB_PATH", db):
            with patch("duckdb.connect", side_effect=Exception("mocked initialization error")):
                with patch("logging.error") as mock_logging:
                    assert _adapter._get_shared_duckdb_connection() is None
                    mock_logging.assert_called_once()
                    assert "mocked initialization error" in str(mock_logging.call_args)
        _adapter._clear_shared_duckdb_connection()
    def test_shared_connection_reuses_instance(self, tmp_path):
        import src.db.duckdb_adapter as _adapter
        _adapter._clear_shared_duckdb_connection()
        # Mock DUCKDB_PATH temporarily so _duckdb_available is True
        db = str(tmp_path / "cache.duckdb")
        duckdb.connect(db).close()
        with patch.object(_adapter, "DUCKDB_PATH", db):
            con1 = _adapter._get_shared_duckdb_connection()
            assert con1 is not None
            con2 = _adapter._get_shared_duckdb_connection()
            assert con1 is con2
            _adapter._clear_shared_duckdb_connection()

    def test_shared_connection_double_check_locking(self, tmp_path):
        import src.db.duckdb_adapter as _adapter
        _adapter._clear_shared_duckdb_connection()
        db = str(tmp_path / "cache.duckdb")
        duckdb.connect(db).close()

        with patch.object(_adapter, "DUCKDB_PATH", db):
            class MockLock:
                def __enter__(self):
                    _adapter._shared_connection = "mocked_lock_connection"
                    return self
                def __exit__(self, *args):
                    pass
            with patch.object(_adapter, "_db_write_lock", MockLock()):
                assert _adapter._get_shared_duckdb_connection() == "mocked_lock_connection"

        _adapter._clear_shared_duckdb_connection()
    def test_cursor_execute_none_con(self):
        import src.db.duckdb_adapter as _adapter
        cur = _adapter._DuckDBCursor(None)
        cur.execute("SELECT 1")
        assert cur._rel is None
        assert cur.fetchall() == []
        df = cur.fetchall_as_pandas()
        assert df.empty

    def test_cursor_execute_list_params(self, tmp_path):
        import src.db.duckdb_adapter as _adapter
        con = duckdb.connect(str(tmp_path / "cache.duckdb"))
        cur = _adapter._DuckDBCursor(con)
        cur.execute("CREATE TABLE test (a INTEGER)")
        cur.execute("INSERT INTO test VALUES (?)", [2])
        cur.execute("SELECT * FROM test")
        assert cur.fetchall() == [(2,)]
        cur.execute("SELECT * FROM test") # re-execute because fetchall consumes the relation
        df = cur.fetchall_as_pandas()
        assert len(df) == 1
        assert df.iloc[0]["a"] == 2

    def test_cursor_execute_write(self, tmp_path):
        import src.db.duckdb_adapter as _adapter
        con = duckdb.connect(str(tmp_path / "cache.duckdb"))
        cur = _adapter._DuckDBCursor(con)
        cur.execute("CREATE TABLE test (a INTEGER)")
        cur.execute_write("INSERT INTO test VALUES (3)")
        cur.execute("SELECT * FROM test")
        df = cur.fetchall_as_pandas()
        assert len(df) == 1
        assert df.iloc[0]["a"] == 3

    def test_cursor_executemany(self, tmp_path):
        cur = self._cursor(str(tmp_path / "t.duckdb"))
        cur.execute("CREATE TABLE test (a INTEGER, b VARCHAR)")

        # Test executemany with params
        cur.executemany("INSERT INTO test VALUES (?, ?)", [[1, 'a'], [2, 'b']])
        cur.execute("SELECT * FROM test")
        df = cur.fetchall_as_pandas()
        assert len(df) == 2
        assert df.iloc[0]["a"] == 1
        assert df.iloc[1]["b"] == 'b'

        # Test executemany without params
        # DuckDB's executemany requires params, so we will use pytest.raises to assert the exception
        cur.execute("CREATE TABLE test2 (a INTEGER)")
        with pytest.raises(duckdb.InvalidInputException):
            cur.executemany("INSERT INTO test2 VALUES (42)")

    def test_cursor_executemany_write(self, tmp_path):
        cur = self._cursor(str(tmp_path / "t.duckdb"))
        cur.execute("CREATE TABLE test (a INTEGER, b VARCHAR)")

        cur.executemany_write("INSERT INTO test VALUES (?, ?)", [[1, 'a'], [2, 'b']])
        cur.execute("SELECT * FROM test")
        df = cur.fetchall_as_pandas()
        assert len(df) == 2
        assert df.iloc[0]["a"] == 1

    def test_cursor_executemany_none_con(self):
        # h helper dict correctly retrieves _DuckDBCursor loaded in setup helpers
        cur = self.h["_DuckDBCursor"](None)
        cur.executemany("INSERT INTO test VALUES (?, ?)", [[1, 'a']])
        assert cur._rel is None

    def test_duckconn_execute(self, tmp_path):
        import src.db.duckdb_adapter as _adapter
        db_path = str(tmp_path / "cache.duckdb")
        con = duckdb.connect(db_path)
        con.execute("CREATE TABLE test (a INTEGER)")
        con.execute("INSERT INTO test VALUES (1)")
        with patch.object(_adapter, "_get_shared_duckdb_connection", return_value=con):
            conn = _adapter._DuckDBConn(db_path)
            cur = conn.execute("SELECT * FROM test")
            assert isinstance(cur, _adapter._DuckDBCursor)
            df = cur.fetchall_as_pandas()
            assert len(df) == 1
            assert df.iloc[0]["a"] == 1

    def test_duckconn_context_manager(self, tmp_path):
        import src.db.duckdb_adapter as _adapter
        db_path = str(tmp_path / "cache.duckdb")
        con = duckdb.connect(db_path)
        with patch.object(_adapter, "_get_shared_duckdb_connection", return_value=con):
            conn = _adapter._DuckDBConn(db_path)
            with conn as ctx_conn:
                assert ctx_conn is conn

    def test_run_duckdb_query(self, tmp_path):
        import src.db.duckdb_adapter as _adapter
        db_path = str(tmp_path / "cache.duckdb")
        con = duckdb.connect(db_path)
        con.execute("CREATE TABLE query_test (msg VARCHAR)")
        con.execute("INSERT INTO query_test VALUES ('hello')")
        with patch.object(_adapter, "_get_shared_duckdb_connection", return_value=con):
            with patch("src.db.duckdb_adapter.DUCKDB_PATH", db_path):
                df = _adapter._run_duckdb_query("SELECT * FROM query_test")
                assert len(df) == 1
                assert df.iloc[0]["msg"] == 'hello'
    def test_duckconn_open_property(self, tmp_path):
        db = str(tmp_path / "t.duckdb")
        user_db = str(tmp_path / "user.duckdb")
        _mod = self.h["_module"]
        # File absent → singleton returns None → open is False
        with patch.object(_mod, "DUCKDB_PATH", db), \
             patch.object(_mod, "USER_DATA_PATH", user_db):
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
    """Phase 4: tests now patch src.db.duckdb_adapter.DUCKDB_PATH directly."""

    def _available(self, path):
        import src.db.duckdb_adapter as _adapter
        with patch.object(_adapter, "DUCKDB_PATH", path):
            return _adapter._duckdb_available()

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
        # write_duckdb stores tables under the dictionary_cache schema so that
        # the 3-part SQL (data_governance.dictionary_cache.table) resolves when
        # the file is ATTACHed AS data_governance.
        df = con.execute("SELECT * FROM dictionary_cache.tables_metadata").df()
        con.close()
        assert len(df) == 1
        assert df.iloc[0]["full_name"] == "c.s.t"

    def test_permissions_cache_populated(self, tmp_path):
        db = str(tmp_path / "cache.duckdb")
        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb([], [], self._permissions(), [], [])
        con = duckdb.connect(db, read_only=True)
        df = con.execute("SELECT * FROM dictionary_cache.permissions_cache").df()
        con.close()
        assert df.iloc[0]["principal"] == "grp"

    def test_empty_input_creates_all_tables(self, tmp_path):
        db = str(tmp_path / "cache.duckdb")
        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb([], [], [], [], [])
        con = duckdb.connect(db, read_only=True)
        for tbl in ("tables_metadata", "columns_metadata", "permissions_cache",
                    "lineage_cache", "object_tags", "audit_log"):
            df = con.execute(f"SELECT * FROM dictionary_cache.{tbl}").df()
            assert isinstance(df, pd.DataFrame), f"dictionary_cache.{tbl} missing"
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
