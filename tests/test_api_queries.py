"""Tests for src/api/queries.py.

Coverage:
  - _group_clause: empty tuple produces no-match placeholder
  - _group_clause: builds correct IN placeholders and params dict
  - get_authorized_tables: returns DataFrame from _base_run_query
  - get_table_details: returns None when access check finds 0 rows
  - get_table_details: returns columns DataFrame when access is granted
  - search_metadata: passes LIKE param and returns combined results
  - get_lineage: passes fn and depth params
"""

from __future__ import annotations

from unittest.mock import call, patch

import pandas as pd
import pytest

from src.api.queries import (
    _group_clause,
    get_authorized_tables,
    get_lineage,
    get_table_details,
    search_metadata,
)


# ── _group_clause ─────────────────────────────────────────────────────────────

class TestGroupClause:
    def test_empty_groups_returns_no_match_placeholder(self):
        ph, params = _group_clause(())
        assert ph == "'__no_match__'"
        assert params == {}

    def test_single_group(self):
        ph, params = _group_clause(("g1",))
        assert "%(group_0)s" in ph
        assert params == {"group_0": "g1"}

    def test_multiple_groups(self):
        ph, params = _group_clause(("g1", "g2", "g3"))
        assert ph.count("%(group_") == 3
        assert params == {"group_0": "g1", "group_1": "g2", "group_2": "g3"}


# ── get_authorized_tables ─────────────────────────────────────────────────────

class TestGetAuthorizedTables:
    def test_returns_dataframe_from_query(self):
        expected = pd.DataFrame([{"full_name": "c.s.t", "catalog_name": "c"}])
        with patch("src.api.queries._base_run_query", return_value=expected) as mock_q:
            result = get_authorized_tables(("g1", "g2"))
        assert mock_q.call_count == 1
        sql, params = mock_q.call_args[0]
        assert "tables_metadata" in sql
        assert "SELECT_ALL_USERS" in sql
        assert params["group_0"] == "g1"
        pd.testing.assert_frame_equal(result, expected)

    def test_empty_groups_uses_no_match_placeholder(self):
        with patch("src.api.queries._base_run_query", return_value=pd.DataFrame()) as mock_q:
            get_authorized_tables(())
        sql, params = mock_q.call_args[0]
        assert "__no_match__" in sql
        assert params == {}


# ── get_table_details ─────────────────────────────────────────────────────────

class TestGetTableDetails:
    def test_returns_none_when_not_authorized(self):
        access_denied = pd.DataFrame([{"n": 0}])
        with patch("src.api.queries._base_run_query", return_value=access_denied):
            result = get_table_details("c.s.t", ("g1",))
        assert result is None

    def test_returns_none_when_access_check_empty(self):
        with patch("src.api.queries._base_run_query", return_value=pd.DataFrame()):
            result = get_table_details("c.s.t", ("g1",))
        assert result is None

    def test_returns_columns_when_authorized(self):
        access_ok = pd.DataFrame([{"n": 1}])
        cols = pd.DataFrame([
            {"column_name": "id", "data_type": "BIGINT", "description": "PK"},
        ])
        call_count = 0

        def _side_effect(sql, params):
            nonlocal call_count
            call_count += 1
            return access_ok if call_count == 1 else cols

        with patch("src.api.queries._base_run_query", side_effect=_side_effect):
            result = get_table_details("c.s.t", ("g1",))

        assert result is not None
        assert list(result["column_name"]) == ["id"]

    def test_second_query_passes_full_name(self):
        access_ok = pd.DataFrame([{"n": 1}])
        cols = pd.DataFrame([{"column_name": "x", "data_type": "INT", "description": ""}])
        calls = []

        def _side_effect(sql, params):
            calls.append(params)
            return access_ok if len(calls) == 1 else cols

        with patch("src.api.queries._base_run_query", side_effect=_side_effect):
            get_table_details("cat.schema.tbl", ("g1",))

        assert calls[1] == {"fn": "cat.schema.tbl"}


# ── search_metadata ───────────────────────────────────────────────────────────

class TestSearchMetadata:
    def test_passes_like_param(self):
        with patch("src.api.queries._base_run_query", return_value=pd.DataFrame()) as mock_q:
            search_metadata("revenue", ("g1",))
        _, params = mock_q.call_args[0]
        assert params["q"] == "%revenue%"

    def test_returns_results_dataframe(self):
        expected = pd.DataFrame([
            {"full_name": "a.b.c", "name": "revenue_table", "match_type": "Table"}
        ])
        with patch("src.api.queries._base_run_query", return_value=expected):
            result = search_metadata("revenue", ("g1",))
        pd.testing.assert_frame_equal(result, expected)

    def test_sql_contains_union_for_columns(self):
        with patch("src.api.queries._base_run_query", return_value=pd.DataFrame()) as mock_q:
            search_metadata("col", ("g1",))
        sql, _ = mock_q.call_args[0]
        assert "UNION ALL" in sql
        assert "columns_metadata" in sql


# ── get_lineage ───────────────────────────────────────────────────────────────

class TestGetLineage:
    def test_passes_fn_and_depth(self):
        with patch("src.api.queries._base_run_query", return_value=pd.DataFrame()) as mock_q:
            get_lineage("c.s.t", depth=3)
        _, params = mock_q.call_args[0]
        assert params["fn"] == "c.s.t"
        assert params["depth"] == 3

    def test_sql_contains_recursive_cte(self):
        with patch("src.api.queries._base_run_query", return_value=pd.DataFrame()) as mock_q:
            get_lineage("c.s.t")
        sql, _ = mock_q.call_args[0]
        assert "RECURSIVE" in sql
        assert "lineage_cache" in sql

    def test_default_depth_is_one(self):
        with patch("src.api.queries._base_run_query", return_value=pd.DataFrame()) as mock_q:
            get_lineage("c.s.t")
        _, params = mock_q.call_args[0]
        assert params["depth"] == 1
