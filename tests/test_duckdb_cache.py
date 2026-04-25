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
    src_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
    with open(src_path) as f:
        source = f.read()

    # Grab the block from _duckdb_available through _get_databricks_connection
    start = source.find("\ndef _duckdb_available(")
    end   = source.find("\n@st.cache_resource", start)
    block = source[start:end]

    ns = {"os": os, "pd": pd, "re": _re, "MagicMock": MagicMock}
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

    def test_context_manager_closes_connection(self, tmp_path):
        cur = self._cursor(str(tmp_path / "t.duckdb"))
        with cur:
            cur.execute("SELECT 1")
        # Connection closed — next execute should raise
        with pytest.raises(Exception):
            cur.execute("SELECT 1")

    def test_duckconn_cursor_returns_cursor(self, tmp_path):
        db = str(tmp_path / "t.duckdb")
        duckdb.connect(db).close()  # create file
        conn = self.h["_DuckDBConn"](db)
        cur = conn.cursor()
        assert hasattr(cur, "execute")
        assert hasattr(cur, "fetchall_as_pandas")

    def test_duckconn_open_property(self, tmp_path):
        db = str(tmp_path / "t.duckdb")
        conn_absent = self.h["_DuckDBConn"](db)
        assert conn_absent.open is False
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
                    "lineage_cache", "object_tags", "comments", "business_name_overrides"):
            df = con.execute(f"SELECT * FROM {tbl}").df()
            assert isinstance(df, pd.DataFrame), f"{tbl} missing"
        con.close()

    def test_comments_preserved_across_sync(self, tmp_path):
        db = str(tmp_path / "cache.duckdb")
        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb(self._tables(), [], [], [], [])

        # Insert a comment into the existing file
        con = duckdb.connect(db)
        con.execute(
            "INSERT INTO comments VALUES "
            "('id1','TABLE','c.s.t','Hi','Alice','a@x.com',current_timestamp,'st@x.com',NULL)"
        )
        con.close()

        # Second sync — comments must survive
        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb(self._tables(), [], [], [], [])

        con = duckdb.connect(db, read_only=True)
        df = con.execute("SELECT * FROM comments").df()
        con.close()
        assert len(df) == 1 and df.iloc[0]["comment_id"] == "id1"

    def test_overrides_preserved_across_sync(self, tmp_path):
        db = str(tmp_path / "cache.duckdb")
        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb(self._tables(), self._columns(), [], [], [])

        con = duckdb.connect(db)
        con.execute(
            "INSERT INTO business_name_overrides VALUES "
            "('c.s.t','id','Customer ID','PK','alice@x.com',current_timestamp)"
        )
        con.close()

        with patch.dict(os.environ, {"DUCKDB_PATH": db}):
            self.write_duckdb(self._tables(), self._columns(), [], [], [])

        con = duckdb.connect(db, read_only=True)
        df = con.execute("SELECT * FROM business_name_overrides").df()
        con.close()
        assert len(df) == 1
        assert df.iloc[0]["business_name"] == "Customer ID"

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
