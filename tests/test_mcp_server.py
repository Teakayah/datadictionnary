"""Tests for src/mcp_server/server.py (FastMCP tools).

Each tool is called directly as an async function — the MCP protocol
layer is not exercised. User identity is injected via the _current_user
ContextVar, mirroring what _MCPAuthMiddleware does in production.

Coverage:
  - search_tables: raises RuntimeError when no user in context
  - search_tables: returns JSON array on cache miss
  - search_tables: returns cached JSON on cache hit (no DB call)
  - search_tables: returns empty JSON array when DB returns nothing
  - get_table_details: returns error JSON when table not found
  - get_table_details: returns columns JSON when authorized
  - list_tables: returns all tables when no filters given
  - list_tables: filters by catalog
  - list_tables: filters by schema
  - get_lineage: returns edge list
  - get_lineage: clamps depth to [1, 5]
"""

from __future__ import annotations

import asyncio
import json
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from src.api.auth import AuthenticatedUser
from src.mcp_server.server import (
    _current_user,
    get_lineage,
    get_table_details,
    list_tables,
    search_tables,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

FAKE_USER = AuthenticatedUser(
    oid="u1", email="u@example.com", name="User", groups=["g1"]
)


def _run_with_user(coro, user=FAKE_USER):
    """Run a coroutine with a user injected into the MCP context."""
    async def _inner():
        token = _current_user.set(user)
        try:
            return await coro
        finally:
            _current_user.reset(token)
    return asyncio.run(_inner())


def _run_no_user(coro):
    """Run a coroutine without setting the MCP user context."""
    return asyncio.run(coro)


@contextmanager
def _no_cache():
    with ExitStack() as stack:
        stack.enter_context(patch("src.mcp_server.server.redis_cache.get", AsyncMock(return_value=None)))
        stack.enter_context(patch("src.mcp_server.server.redis_cache.set", AsyncMock()))
        yield


# ── search_tables ─────────────────────────────────────────────────────────────

class TestSearchTables:
    def test_raises_without_user_in_context(self):
        with pytest.raises(RuntimeError, match="No authenticated user"):
            _run_no_user(search_tables("revenue"))

    def test_returns_json_array_on_db_results(self):
        df = pd.DataFrame([{
            "full_name": "cat.s.orders",
            "name": "orders",
            "match_type": "Table",
            "description": "Order data",
            "catalog_name": "cat",
            "schema_name": "s",
            "table_name": "orders",
            "dq_score": "A",
        }])
        with patch("src.mcp_server.server.queries.search_metadata", return_value=df), \
             _no_cache():
            result = _run_with_user(search_tables("order"))
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["full_name"] == "cat.s.orders"

    def test_returns_cached_json_without_db_call(self):
        cached = [{"full_name": "cached.s.t", "name": "t", "match_type": "Table"}]
        with patch("src.mcp_server.server.redis_cache.get", AsyncMock(return_value=cached)), \
             patch("src.mcp_server.server.queries.search_metadata") as no_db:
            result = _run_with_user(search_tables("order"))
        no_db.assert_not_called()
        assert json.loads(result) == cached

    def test_returns_empty_array_when_no_results(self):
        with patch("src.mcp_server.server.queries.search_metadata", return_value=pd.DataFrame()), \
             _no_cache():
            result = _run_with_user(search_tables("xyzzy"))
        assert json.loads(result) == []


# ── get_table_details ─────────────────────────────────────────────────────────

class TestGetTableDetails:
    def test_returns_error_json_when_not_found(self):
        with patch("src.mcp_server.server.queries.get_table_details", return_value=None), \
             _no_cache():
            result = _run_with_user(get_table_details("cat.s.missing"))
        data = json.loads(result)
        assert "error" in data
        assert "cat.s.missing" in data["error"]

    def test_returns_columns_when_found(self):
        cols = pd.DataFrame([
            {"column_name": "id", "data_type": "BIGINT", "description": "PK"},
            {"column_name": "name", "data_type": "STRING", "description": "Name"},
        ])
        with patch("src.mcp_server.server.queries.get_table_details", return_value=cols), \
             _no_cache():
            result = _run_with_user(get_table_details("cat.s.customers"))
        data = json.loads(result)
        assert data["full_name"] == "cat.s.customers"
        assert len(data["columns"]) == 2
        assert data["columns"][0]["column_name"] == "id"

    def test_passes_groups_from_context_user(self):
        user = AuthenticatedUser(oid="u2", email="e@e.com", name="U", groups=["grp-x"])
        with patch("src.mcp_server.server.queries.get_table_details", return_value=None) as mock_q, \
             _no_cache():
            _run_with_user(get_table_details("c.s.t"), user=user)
        mock_q.assert_called_once()
        _, groups = mock_q.call_args[0]
        assert "grp-x" in groups


# ── list_tables ───────────────────────────────────────────────────────────────

MULTI_CATALOG_DF = pd.DataFrame([
    {"full_name": "prod.sales.orders",   "catalog_name": "prod", "schema_name": "sales",  "table_name": "orders"},
    {"full_name": "prod.hr.employees",   "catalog_name": "prod", "schema_name": "hr",     "table_name": "employees"},
    {"full_name": "dev.sales.test_tbl",  "catalog_name": "dev",  "schema_name": "sales",  "table_name": "test_tbl"},
])


class TestListTables:
    def test_returns_all_when_no_filters(self):
        with patch("src.mcp_server.server.queries.get_authorized_tables", return_value=MULTI_CATALOG_DF), \
             _no_cache():
            result = _run_with_user(list_tables())
        data = json.loads(result)
        assert len(data) == 3

    def test_filters_by_catalog(self):
        with patch("src.mcp_server.server.queries.get_authorized_tables", return_value=MULTI_CATALOG_DF), \
             _no_cache():
            result = _run_with_user(list_tables(catalog="prod"))
        data = json.loads(result)
        assert all(r["catalog_name"] == "prod" for r in data)
        assert len(data) == 2

    def test_filters_by_schema(self):
        with patch("src.mcp_server.server.queries.get_authorized_tables", return_value=MULTI_CATALOG_DF), \
             _no_cache():
            result = _run_with_user(list_tables(schema="sales"))
        data = json.loads(result)
        assert all(r["schema_name"] == "sales" for r in data)
        assert len(data) == 2

    def test_filters_by_catalog_and_schema(self):
        with patch("src.mcp_server.server.queries.get_authorized_tables", return_value=MULTI_CATALOG_DF), \
             _no_cache():
            result = _run_with_user(list_tables(catalog="prod", schema="sales"))
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["full_name"] == "prod.sales.orders"

    def test_returns_empty_list_when_no_tables(self):
        with patch("src.mcp_server.server.queries.get_authorized_tables", return_value=pd.DataFrame()), \
             _no_cache():
            result = _run_with_user(list_tables())
        assert json.loads(result) == []


# ── get_lineage ───────────────────────────────────────────────────────────────

class TestGetLineage:
    def test_returns_lineage_edges(self):
        df = pd.DataFrame([{
            "table_full_name": "c.s.t",
            "direction": "upstream",
            "entity_full_name": "c.raw.r",
            "entity_type": "TABLE",
            "depth": 1,
        }])
        with patch("src.mcp_server.server.queries.get_lineage", return_value=df), \
             _no_cache():
            result = _run_with_user(get_lineage("c.s.t"))
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["direction"] == "upstream"

    def test_returns_empty_list_when_no_lineage(self):
        with patch("src.mcp_server.server.queries.get_lineage", return_value=pd.DataFrame()), \
             _no_cache():
            result = _run_with_user(get_lineage("c.s.t"))
        assert json.loads(result) == []

    def test_clamps_depth_minimum_to_1(self):
        with patch("src.mcp_server.server.queries.get_lineage", return_value=pd.DataFrame()) as mock_q, \
             _no_cache():
            _run_with_user(get_lineage("c.s.t", depth=0))
        _, kwargs_or_args = mock_q.call_args
        # depth is passed as second positional arg
        passed_depth = mock_q.call_args[0][1] if len(mock_q.call_args[0]) > 1 else 1
        assert passed_depth >= 1

    def test_clamps_depth_maximum_to_5(self):
        with patch("src.mcp_server.server.queries.get_lineage", return_value=pd.DataFrame()) as mock_q, \
             _no_cache():
            _run_with_user(get_lineage("c.s.t", depth=99))
        passed_depth = mock_q.call_args[0][1] if len(mock_q.call_args[0]) > 1 else 1
        assert passed_depth <= 5

class TestGetTableDetailsCache:
    def test_returns_cached_json_without_db_call(self):
        cached = {"full_name": "cached.s.t", "columns": [{"column_name": "c1", "data_type": "STRING", "description": "desc"}]}
        with patch("src.mcp_server.server.redis_cache.get", AsyncMock(return_value=cached)), \
             patch("src.mcp_server.server.queries.get_table_details") as no_db:
            result = _run_with_user(get_table_details("cached.s.t"))
        no_db.assert_not_called()
        assert json.loads(result) == cached

class TestListTablesCache:
    def test_returns_cached_json_without_db_call(self):
        cached = [{"full_name": "cached.s.t", "catalog_name": "c", "schema_name": "s", "table_name": "t"}]
        with patch("src.mcp_server.server.redis_cache.get", AsyncMock(return_value=cached)), \
             patch("src.mcp_server.server.queries.get_authorized_tables") as no_db:
            result = _run_with_user(list_tables())
        no_db.assert_not_called()
        assert json.loads(result) == cached

class TestGetLineageCache:
    def test_returns_cached_json_without_db_call(self):
        cached = [{"direction": "upstream", "entity_full_name": "c.s.t", "entity_type": "TABLE", "depth": 1}]
        with patch("src.mcp_server.server.redis_cache.get", AsyncMock(return_value=cached)), \
             patch("src.mcp_server.server.queries.get_lineage") as no_db:
            result = _run_with_user(get_lineage("cached.s.t"))
        no_db.assert_not_called()
        assert json.loads(result) == cached
