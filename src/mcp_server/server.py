from __future__ import annotations
"""FastMCP server exposing the data dictionary to AI assistants (Copilot, Claude, etc.).

User identity is injected by MCPAuthMiddleware (in src/api/main.py) via the
_current_user ContextVar before each request reaches these tools.
"""

import asyncio
import json
import logging
from contextvars import ContextVar
from typing import Optional

from mcp.server.fastmcp import FastMCP

from src.api import queries
from src.api.auth import AuthenticatedUser
from src.cache import redis_cache

logger = logging.getLogger(__name__)

# Populated by MCPAuthMiddleware before each MCP request
_current_user: ContextVar[Optional[AuthenticatedUser]] = ContextVar(
    "mcp_user", default=None
)


def _require_user() -> AuthenticatedUser:
    user = _current_user.get()
    if user is None:
        raise RuntimeError("No authenticated user in MCP context")
    return user


mcp = FastMCP(
    "Data Dictionary",
    instructions=(
        "You have access to a Databricks Unity Catalog data dictionary. "
        "All results are automatically filtered to your permission level — "
        "you will only see tables your identity is authorized to access. "
        "Use search_tables first to discover relevant datasets, then "
        "get_table_details to explore columns and data types."
    ),
)


@mcp.tool()
async def search_tables(query: str) -> str:
    """Search for tables, columns, and business glossary terms.

    Args:
        query (str): Free-text search (e.g. "customer orders", "revenue by region").

    Returns:
        str: JSON array of matches — each has full_name, name, match_type
        (Table|Column|Glossary), description, catalog, schema, and dq_score.
    """
    user = _require_user()
    groups = tuple(user.groups)
    ck = redis_cache.cache_key("mcp_search", query, groups)
    if (cached := await redis_cache.get(ck)) is not None:
        return json.dumps(cached)

    df = await asyncio.to_thread(queries.search_metadata, query, groups)
    results = df.to_dict(orient="records") if df is not None and not df.empty else []
    await redis_cache.set(ck, results, ttl=300)
    return json.dumps(results, default=str)


@mcp.tool()
async def get_table_details(table_full_name: str) -> str:
    """Get all columns for a table, including data types and business descriptions.

    Args:
        table_full_name (str): Unity Catalog identifier in catalog.schema.table form
                         (e.g. "main.sales.orders").

    Returns:
        str: JSON object with full_name and a columns array (column_name, data_type,
        description). Returns {"error": "..."} if not found or access is denied.
    """
    user = _require_user()
    groups = tuple(user.groups)
    ck = redis_cache.cache_key("mcp_table_detail", table_full_name, groups)
    if (cached := await redis_cache.get(ck)) is not None:
        return json.dumps(cached)

    cols_df = await asyncio.to_thread(queries.get_table_details, table_full_name, groups)
    if cols_df is None:
        return json.dumps(
            {"error": f"Table '{table_full_name}' not found or access denied."}
        )

    result = {
        "full_name": table_full_name,
        "columns": cols_df.to_dict(orient="records"),
    }
    await redis_cache.set(ck, result, ttl=600)
    return json.dumps(result, default=str)


@mcp.tool()
async def list_tables(
    catalog: Optional[str] = None,
    schema: Optional[str] = None,
) -> str:
    """List all tables you are authorized to access, optionally filtered.

    Args:
        catalog (Optional[str], optional): Filter to a specific catalog (e.g. "main"). Optional.
        schema (Optional[str], optional): Filter to a specific schema (e.g. "sales"). Requires catalog.

    Returns:
        str: JSON array of table summaries — each has full_name, catalog_name,
        schema_name, table_name, table_description, table_type, dq_score.
    """
    user = _require_user()
    groups = tuple(user.groups)
    ck = redis_cache.cache_key("mcp_list_tables", groups, catalog, schema)
    if (cached := await redis_cache.get(ck)) is not None:
        return json.dumps(cached)

    df = await asyncio.to_thread(queries.get_authorized_tables, groups)
    if df is None or df.empty:
        return json.dumps([])

    if catalog:
        # ⚡ Bolt: Use .to_numpy() to skip index alignment overhead
        df = df[df["catalog_name"].to_numpy() == catalog]
    if schema:
        # ⚡ Bolt: Use .to_numpy() to skip index alignment overhead
        df = df[df["schema_name"].to_numpy() == schema]

    results = df.to_dict(orient="records")
    await redis_cache.set(ck, results, ttl=600)
    return json.dumps(results, default=str)


@mcp.tool()
async def get_lineage(table_full_name: str, depth: int = 1) -> str:
    """Get data lineage for a table — upstream sources and downstream consumers.

    Args:
        table_full_name (str): Unity Catalog identifier (catalog.schema.table).
        depth (int, optional): How many hops to traverse (1–5). Default 1.

    Returns:
        str: JSON array of lineage edges with direction (upstream|downstream),
        entity_full_name, entity_type, and depth.
    """
    depth = max(1, min(depth, 5))
    ck = redis_cache.cache_key("mcp_lineage", table_full_name, depth)
    if (cached := await redis_cache.get(ck)) is not None:
        return json.dumps(cached)

    df = await asyncio.to_thread(queries.get_lineage, table_full_name, depth)
    results = df.to_dict(orient="records") if df is not None and not df.empty else []
    await redis_cache.set(ck, results, ttl=300)
    return json.dumps(results, default=str)
