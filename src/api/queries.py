"""DB queries for the API/MCP layer.

These call _base_run_query directly, bypassing @st.cache_data.
Caching is handled by Redis at the endpoint/tool level instead.
"""

from __future__ import annotations

import pandas as pd

from src.config import CATALOG_CACHE, SCHEMA_CACHE
from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import _base_run_query


def _group_clause(groups: tuple[str, ...]) -> tuple[str, dict]:
    """Return (SQL IN clause, params dict) for a groups tuple.

    Creates a dynamic number of pyformat parameter placeholders (e.g., `%(group_0)s`)
    and maps them to the provided AD groups.

    WHY IT EXISTS:
    This allows secure, parameterized filtering of Unity Catalog metadata against
    the user's group memberships in SQL queries, preventing SQL injection vulnerabilities.

    Args:
        groups (tuple[str, ...]): A tuple of string group IDs the user belongs to.

    Returns:
        tuple[str, dict]: A tuple containing:
            1. The comma-separated pyformat placeholders string
            2. A dictionary mapping placeholder names to group string values
    """
    if not groups:
        return "'__no_match__'", {}
    placeholders = ", ".join(f"%(group_{i})s" for i in range(len(groups)))
    params = {f"group_{i}": g for i, g in enumerate(groups)}
    return placeholders, params


def _overrides_tables() -> tuple[str, str]:
    """Return (table_metadata_overrides, business_name_overrides) fully-qualified names."""
    if _duckdb_available():
        return "user_data.table_metadata_overrides", "user_data.business_name_overrides"
    return (
        f"{CATALOG_CACHE}.{SCHEMA_CACHE}.table_metadata_overrides",
        f"{CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides",
    )


def get_authorized_tables(groups: tuple[str, ...]) -> pd.DataFrame:
    """Fetch all tables the user is authorized to view.

    Implements row-level access control by joining the tables metadata with
    the permissions cache, filtering by the provided Entra ID groups.

    Args:
        groups (tuple[str, ...]): A tuple of Entra ID group object IDs for the user.

    Returns:
        pd.DataFrame: A pandas DataFrame containing authorized table metadata.
    """
    ph, params = _group_clause(groups)
    tbl_ovr, _ = _overrides_tables()
    sql = f"""
        SELECT DISTINCT
            m.full_name, m.catalog_name, m.schema_name, m.table_name,
            COALESCE(o.description, m.comment) AS table_description,
            m.table_type, m.updated_at,
            COALESCE(dq.dq_score, '') AS dq_score,
            COALESCE(dq.last_run_status, '') AS dq_status
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata m
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache p ON m.full_name = p.table_full_name
        LEFT JOIN {tbl_ovr} o ON m.full_name = o.table_full_name
        LEFT JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.data_quality_cache dq ON m.full_name = dq.table_full_name
        WHERE (p.principal IN ({ph}) OR p.principal = 'SELECT_ALL_USERS')
    """  # nosec B608
    return _base_run_query(sql, params)


def get_table_details(full_name: str, groups: tuple[str, ...]) -> pd.DataFrame | None:
    """Return column metadata for a table, or None if not found / not authorized."""
    ph, params = _group_clause(groups)
    params["fn"] = full_name

    # Permission check
    sql_check = f"""
        SELECT COUNT(*) AS n
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata m
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache p ON m.full_name = p.table_full_name
        WHERE m.full_name = %(fn)s
          AND (p.principal IN ({ph}) OR p.principal = 'SELECT_ALL_USERS')
    """  # nosec B608
    check = _base_run_query(sql_check, params)
    if check.empty or int(check.iloc[0]["n"]) == 0:
        return None

    sql_cols = f"""
        SELECT c.column_name, c.data_type,
               COALESCE(ob.definition, c.comment) AS description
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata c
        LEFT JOIN user_data.business_name_overrides ob
          ON ob.table_full_name = c.table_full_name AND ob.column_name = c.column_name
        WHERE c.table_full_name = %(fn)s
        ORDER BY c.column_name
    """  # nosec B608
    return _base_run_query(sql_cols, {"fn": full_name})


def search_metadata(query: str, groups: tuple[str, ...]) -> pd.DataFrame:
    """Search across tables and columns for a given query string.

    Performs a full-text search against table names, column names, comments,
    and business overrides, returning matches that the user's groups permit viewing.

    Args:
        query (str): The search string to match against metadata.
        groups (tuple[str, ...]): A tuple of Entra ID group object IDs for the user.

    Returns:
        pd.DataFrame: A pandas DataFrame containing search results with match details.
    """
    ph, params = _group_clause(groups)
    params["q"] = f"%{query}%"
    tbl_ovr, col_ovr = _overrides_tables()
    sql = f"""
        SELECT DISTINCT
            m.full_name, m.table_name AS name, 'Table' AS match_type,
            COALESCE(o.description, m.comment) AS description,
            m.catalog_name, m.schema_name, m.table_name,
            COALESCE(dq.dq_score, '') AS dq_score
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata m
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache p ON m.full_name = p.table_full_name
        LEFT JOIN {tbl_ovr} o ON m.full_name = o.table_full_name
        LEFT JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.data_quality_cache dq ON m.full_name = dq.table_full_name
        WHERE (m.table_name LIKE %(q)s OR m.comment LIKE %(q)s OR o.description LIKE %(q)s)
          AND (p.principal IN ({ph}) OR p.principal = 'SELECT_ALL_USERS')

        UNION ALL

        SELECT DISTINCT
            c.table_full_name AS full_name,
            COALESCE(ob.business_name, c.column_name) AS name,
            'Column' AS match_type,
            COALESCE(ob.definition, c.comment) AS description,
            t.catalog_name, t.schema_name, t.table_name,
            COALESCE(dq.dq_score, '') AS dq_score
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata c
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache p ON c.table_full_name = p.table_full_name
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata t ON c.table_full_name = t.full_name
        LEFT JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.data_quality_cache dq ON c.table_full_name = dq.table_full_name
        LEFT JOIN {col_ovr} ob ON ob.table_full_name = c.table_full_name AND ob.column_name = c.column_name
        WHERE (c.column_name LIKE %(q)s OR c.comment LIKE %(q)s
               OR ob.business_name LIKE %(q)s OR ob.definition LIKE %(q)s)
          AND (p.principal IN ({ph}) OR p.principal = 'SELECT_ALL_USERS')

        LIMIT 50
    """  # nosec B608
    return _base_run_query(sql, params)


def get_lineage(table_full_name: str, depth: int = 1) -> pd.DataFrame:
    """Fetch multi-hop lineage edges up to a given depth.

    Uses a recursive CTE to traverse upstream and downstream lineage edges
    starting from the specified table.

    Args:
        table_full_name (str): The Unity Catalog full name of the table to trace.
        depth (int, optional): The maximum number of hops to traverse. Defaults to 1.

    Returns:
        pd.DataFrame: A pandas DataFrame containing lineage edges.
    """
    sql = f"""
        WITH RECURSIVE lineage_cte AS (
            SELECT table_full_name, direction, entity_full_name, entity_type, 1 AS depth
            FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.lineage_cache
            WHERE table_full_name = %(fn)s

            UNION ALL

            SELECT lc.table_full_name, lc.direction, lc.entity_full_name, lc.entity_type,
                   cte.depth + 1
            FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.lineage_cache lc
            JOIN lineage_cte cte
              ON lc.table_full_name = cte.entity_full_name
             AND lc.direction = cte.direction
            WHERE cte.depth < %(depth)s
        )
        SELECT * FROM lineage_cte
    """  # nosec B608
    return _base_run_query(sql, {"fn": table_full_name, "depth": depth})
