"""Tests for src/db/queries.py."""

from __future__ import annotations
import pytest
import pandas as pd
from unittest.mock import patch
from src.db.queries import (
    _fetch_metadata_for_fns,
    _get_write_connection,
    get_db_connection,
    run_query,
    search_all_metadata,
    _search_keywords,

    _get_override_table_name,
    CATALOG_CACHE,
    SCHEMA_CACHE
)

def test_get_override_table_name_duckdb_available():
    with patch("src.db.queries._duckdb_available", return_value=True):
        assert _get_override_table_name("table_metadata") == "user_data.table_metadata_overrides"

def test_get_override_table_name_duckdb_unavailable():
    with patch("src.db.queries._duckdb_available", return_value=False):
        assert _get_override_table_name("table_metadata") == f"{CATALOG_CACHE}.{SCHEMA_CACHE}.table_metadata_overrides"

def test_fetch_metadata_for_fns_empty():
    df = _fetch_metadata_for_fns([], ("group1",))
    assert df.empty

@patch("src.db.queries.run_query")
def test_fetch_metadata_for_fns_with_groups(mock_run_query):
    mock_run_query.return_value = pd.DataFrame([{"full_name": "c.s.t"}])

    df = _fetch_metadata_for_fns(["c.s.t"], ("group1", "group2"))

    assert not df.empty
    mock_run_query.assert_called_once()
    sql, params = mock_run_query.call_args[0]

    assert "%(group_0)s" in sql
    assert "%(group_1)s" in sql
    assert "SELECT unnest(%(fns)s)" in sql
    assert params["fns"] == ["c.s.t"]
    assert params["group_0"] == "group1"
    assert params["group_1"] == "group2"

@patch("src.db.queries.run_query")
def test_fetch_metadata_for_fns_no_groups(mock_run_query):
    mock_run_query.return_value = pd.DataFrame([{"full_name": "c.s.t"}])

    df = _fetch_metadata_for_fns(["c.s.t"], ())

    assert not df.empty
    mock_run_query.assert_called_once()
    sql, params = mock_run_query.call_args[0]

    assert "''" in sql # group placeholders fallback
    assert "SELECT unnest(%(fns)s)" in sql
    assert params["fns"] == ["c.s.t"]
    assert "group_0" not in params



def test_get_write_connection_no_duckdb():
    with patch("src.db.queries._duckdb_available", return_value=False):
        with pytest.raises(RuntimeError) as exc_info:
            _get_write_connection()
        assert "DuckDB is unavailable" in str(exc_info.value)

def test_get_db_connection_no_duckdb():
    with patch("src.db.queries._duckdb_available", return_value=False):
        with patch("src.db.databricks_adapter._get_databricks_connection") as mock_db:
            mock_db.return_value = "db_conn"
            conn = get_db_connection()
            assert conn == "db_conn"

def test_get_write_connection_duckdb_available():
    with patch("src.db.queries._duckdb_available", return_value=True):
        with patch("src.config.DUCKDB_PATH", "fake_path"):
            conn = _get_write_connection()
            assert conn is not None

def test_base_run_query_duckdb():
    with patch("src.db.queries._duckdb_available", return_value=True):
        with patch("src.db.queries._run_duckdb_query") as mock_run:
            mock_run.return_value = "duckdb_result"
            from src.db.queries import _base_run_query
            assert _base_run_query("query") == "duckdb_result"

def test_base_run_query_databricks():
    with patch("src.db.queries._duckdb_available", return_value=False):
        with patch("src.db.queries._run_databricks_query") as mock_run:
            mock_run.return_value = "databricks_result"
            from src.db.queries import _base_run_query
            assert _base_run_query("query") == "databricks_result"

def test_run_query_demo_mode_tables_metadata():
    with patch("src.db.queries.is_demo_mode", return_value=True):

        res = run_query("tables_metadata", {"fn": "main.analytics.customers"})
        assert isinstance(res, pd.DataFrame)
        assert not res.empty
        assert res.iloc[0]["full_name"] == "main.analytics.customers"

def test_search_catalog_semantic_search_empty():

    with patch.dict("os.environ", {"ENABLE_SEMANTIC_SEARCH": "true"}):
        with patch("src.db.queries._search_keywords", return_value=pd.DataFrame()):
            with patch("src.semantic.semantic_search", return_value=[]):
                res = search_all_metadata("query", ("group1",))
                assert res is None or res.empty

def test_search_catalog_semantic_search_no_keyword_hits():

    with patch.dict("os.environ", {"ENABLE_SEMANTIC_SEARCH": "true"}):
        with patch("src.db.queries._search_keywords", return_value=pd.DataFrame()):
            with patch("src.semantic.semantic_search", return_value=["table1", "table2"]):
                with patch("src.db.queries._fetch_metadata_for_fns") as mock_fetch:
                    mock_fetch.return_value = pd.DataFrame({"full_name": ["table2", "table1"], "name": ["T2", "T1"]})
                    res = search_all_metadata("query", ("group1",))
                    assert not res.empty
                    assert "_hybrid_score" not in res.columns # it's dropped by _drop_score_cols
                    assert len(res) == 2
                    assert res.iloc[0]["full_name"] == "table1"
                    assert res.iloc[1]["full_name"] == "table2"

def test_search_keywords_scoring_columns_only():

    with patch("src.db.queries._base_run_query") as mock_run:
        mock_run.return_value = pd.DataFrame({
            "full_name": ["cat.schema.tab1.col1", "cat.schema.tab1.col2", "cat.schema.tab1.col3"],
            "name": ["my_column", "exact_match", "other_col"],
            "match_type": ["Column", "Column", "Column"],
            "description": ["", "", ""],
            "table_description": ["", "", ""],
            "catalog_name": ["cat"] * 3,
            "schema_name": ["schema"] * 3,
            "table_name": ["tab1", "tab1", "tab1"]
        })

        with patch("src.db.queries.is_demo_mode", return_value=False):
            res = _search_keywords("my_col", ("group1",))
            assert not res.empty

            # my_column is prefix but not exact
            assert res.loc[res["name"] == "my_column", "_score"].iloc[0] == 1
            assert res.loc[res["name"] == "other_col", "_score"].iloc[0] == 0

            res_exact = _search_keywords("exact_match", ("group1",))
            assert res_exact.loc[res_exact["name"] == "exact_match", "_score"].iloc[0] == 2


def test_search_all_metadata_semantic_search_empty_results_from_fetch():

    with patch.dict("os.environ", {"ENABLE_SEMANTIC_SEARCH": "true"}):
        with patch("src.db.queries._search_keywords", return_value=pd.DataFrame()):
            with patch("src.semantic.semantic_search", return_value=["table1", "table2"]):
                with patch("src.db.queries._fetch_metadata_for_fns") as mock_fetch:
                    mock_fetch.return_value = pd.DataFrame()
                    res = search_all_metadata("query", ("group1",))
                    assert res is not None
                    assert res.empty

def test_search_all_metadata_semantic_search_import_error():

    import sys

    with patch.dict("os.environ", {"ENABLE_SEMANTIC_SEARCH": "true"}):
        with patch("src.db.queries._search_keywords", return_value=pd.DataFrame()):
            # Mock the import to fail
            with patch.dict(sys.modules, {"src.semantic": None}):
                res = search_all_metadata("query", ("group1",))
                assert res is not None
                assert res.empty


def test_search_keywords_glossary_unauthorized_table():

    with patch("src.db.queries._base_run_query") as mock_run:
        mock_run.return_value = pd.DataFrame(columns=["full_name", "name", "match_type", "description", "table_description", "catalog_name", "schema_name", "table_name"])

        with patch("src.db.queries._DEMO_GLOSSARY", pd.DataFrame({
            "term": ["test term"],
            "definition": ["test definition"],
            "related_tables": [["cat.schema.tab"]]
        })):
            # Mock authorized tables to be empty (user not authorized for cat.schema.tab)
            with patch("src.db.queries.get_authorized_table_names", return_value=set()):
                with patch("src.db.queries.is_demo_mode", return_value=False):
                    res = _search_keywords("test", ("group1",))
                    # Shouldn't include the glossary result
                    assert res is None or res.empty


def test_search_keywords_glossary_authorized_table_populates_name_and_description():
    with patch("src.db.queries._base_run_query") as mock_run:
        mock_run.return_value = pd.DataFrame(columns=["full_name", "name", "match_type", "description", "table_description", "catalog_name", "schema_name", "table_name"])

        with patch("src.db.queries._DEMO_GLOSSARY", pd.DataFrame({
            "term": ["Churn Rate"],
            "definition": ["Percentage of customers lost over a period"],
            "related_tables": [["cat.schema.tab"]]
        })):
            with patch("src.db.queries.get_authorized_table_names", return_value={"cat.schema.tab"}):
                with patch("src.db.queries.is_demo_mode", return_value=False):
                    res = _search_keywords("churn", ("group1",))
                    assert res is not None and not res.empty
                    row = res.iloc[0]
                    assert row["match_type"] == "Glossary"
                    assert row["name"] == "Churn Rate"
                    assert row["description"] == "Percentage of customers lost over a period"

@patch("src.db.queries.get_authorized_tables")
def test_get_authorized_table_names(mock_get_authorized_tables):
    # Arrange
    mock_get_authorized_tables.return_value = pd.DataFrame([{"full_name": "t1"}, {"full_name": "t2"}, {"full_name": "t1"}])
    from src.db.queries import get_authorized_table_names

    # Act
    res = get_authorized_table_names(("group1",))

    # Assert
    assert res == {"t1", "t2"}

@patch("src.db.queries.get_authorized_tables")
def test_get_authorized_table_names_empty(mock_get_authorized_tables):
    # Arrange
    mock_get_authorized_tables.return_value = pd.DataFrame()
    from src.db.queries import get_authorized_table_names

    # Act
    res = get_authorized_table_names(("group1",))

    # Assert
    assert res == set()

@patch("src.db.queries.get_authorized_tables")
def test_get_authorized_table_names_none(mock_get_authorized_tables):
    # Arrange
    mock_get_authorized_tables.return_value = None
    from src.db.queries import get_authorized_table_names

    # Act
    res = get_authorized_table_names(("group1",))

    # Assert
    assert res == set()

@patch("src.db.queries.is_demo_mode", return_value=True)
@patch("src.db.queries._DEMO_TABLES", pd.DataFrame([{"full_name": "t1"}]))
def test_get_authorized_tables_demo_mode(mock_demo_mode):
    # Arrange
    from src.db.queries import get_authorized_tables

    # Act
    res = get_authorized_tables(("group1",))

    # Assert
    assert not res.empty
    assert res.iloc[0]["full_name"] == "t1"

@patch("src.db.queries.is_demo_mode", return_value=False)
@patch("src.db.queries._build_auth_filters", return_value=("%(group_0)s", {"group_0": "group1"}))
@patch("src.db.queries._get_override_table_name", return_value="override_table")
@patch("src.db.queries.run_query")
def test_get_authorized_tables_db_mode(mock_run_query, mock_get_override_table_name, mock_build_auth_filters, mock_is_demo_mode):
    # Arrange
    mock_run_query.return_value = pd.DataFrame([{"full_name": "t1"}])
    from src.db.queries import get_authorized_tables

    # Act
    res = get_authorized_tables(("group1",))

    # Assert
    assert not res.empty
    assert res.iloc[0]["full_name"] == "t1"
    mock_run_query.assert_called_once()
