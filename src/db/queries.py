"""DB connection router and base query executor.

Provides the write-connection helper and a backend-agnostic run_query()
that dispatches to DuckDB (if available) or Databricks.  Demo-mode
interception (returning _DEMO_* fixtures) lives in app.py's wrapper so
that this module stays importable without triggering a circular re-import
of app.py.

NOTE — Phase 4b (deferred): get_authorized_tables(), search_all_metadata(),
get_column_business_names(), and get_multi_hop_lineage() still live in
app.py because they depend on the _DEMO_* DataFrames defined there.
"""

from __future__ import annotations

import csv
import io
import pandas as pd
import streamlit as st
import logging
from src.config import is_demo_mode, CATALOG_CACHE, SCHEMA_CACHE
from src.demo.data import (
    _DEMO_TABLES,
    _DEMO_RELATED,
    _DEMO_LINEAGE,
    _DEMO_COLUMNS,
    _DEMO_GRANTS,
    _DEMO_GLOSSARY,
)


from src.db.duckdb_adapter import _duckdb_available, _DuckDBConn, _run_duckdb_query
from src.db.databricks_adapter import _run_databricks_query


def _get_write_connection():
    """Return a DuckDB connection for write operations.

    Streamlit pods only ever write locally to DuckDB (user_data file).
    The sidecar sync daemon is the sole intentional Databricks writer
    (see ADR 004); pods enqueue into ``user_data.pending_sync`` and the
    daemon drains it. If DuckDB is unavailable, the app cannot accept
    writes — raise instead of silently opening a per-call Databricks
    session.
    """
    if not _duckdb_available():
        raise RuntimeError(
            "DuckDB is unavailable — cannot accept writes. "
            "Set DUCKDB_PATH and ensure the catalog file exists. "
            "Direct Databricks writes were removed in TODO #7; the "
            "sidecar sync daemon is the only intentional Databricks writer."
        )
    from src.config import DUCKDB_PATH
    return _DuckDBConn(DUCKDB_PATH)


def get_db_connection():
    """Return a DB connection for read queries (DuckDB → Databricks fallback)."""
    if _duckdb_available():
        from src.config import DUCKDB_PATH

        return _DuckDBConn(DUCKDB_PATH)
    from src.db.databricks_adapter import _get_databricks_connection

    return _get_databricks_connection()


def _base_run_query(query: str, params=None) -> pd.DataFrame:
    """Execute a SQL read query against DuckDB (if available) or Databricks.

    This is the backend-only dispatcher — it has no demo-mode logic.
    app.py wraps this with _DEMO_* fixture interception for demo mode.
    ui/cards.py imports this directly for admin/health queries that guard
    the demo branch themselves via is_demo_mode().
    """
    if _duckdb_available():
        return _run_duckdb_query(query, params)
    return _run_databricks_query(query, params)


def run_query(query, params=None):
    """Execute a read query against the configured database.

    This is the primary public entry point for data fetching in the application.
    It implements a 3-tier routing architecture:
    1. Demo mode (mock data): Returns static DataFrames without hitting any database.
    2. DuckDB cache: If available, routes the query to the local file for speed.
    3. Databricks SQL Warehouse: Fallback if DuckDB cache is unavailable.

    @param query: The SQL query to execute.
    @param params: Optional dictionary of parameters to substitute into the query.
    @returns: A pandas DataFrame containing the query results.
    """
    # ── Demo mode: return hardcoded DataFrames without hitting any DB ──────────
    if is_demo_mode():
        p = params or {}
        _has_groups = "groups" in p or any(k.startswith("group_") for k in p)
        if "full_name" in p and _has_groups:
            return _DEMO_RELATED.get(
                p["full_name"],
                pd.DataFrame(
                    columns=[
                        "full_name",
                        "table_name",
                        "catalog_name",
                        "schema_name",
                        "relationship",
                    ]
                ),
            )
        if _has_groups:
            return _DEMO_TABLES
        fn = p.get("table_full_name", "")
        if "lineage_cache" in query:
            return _DEMO_LINEAGE.get(
                fn,
                pd.DataFrame(columns=["direction", "entity_full_name", "entity_type"]),
            )
        if "columns_metadata" in query:
            return _DEMO_COLUMNS.get(
                fn, pd.DataFrame(columns=["column_name", "data_type", "comment"])
            )
        return _DEMO_GRANTS.get(fn, pd.DataFrame(columns=["principal", "privilege"]))

    return _base_run_query(query, params)


@st.cache_data(ttl="1h", show_spinner=False)
def get_authorized_tables(groups):
    """Retrieve metadata for tables the user is authorized to access.

    Implements row-level access control by joining the tables metadata with
    a permissions cache. A table is returned only if the user's Entra ID groups
    intersect with the table's allowed principals, or if the table is marked
    public with the sentinel value `SELECT_ALL_USERS`.

    @param groups: A list or tuple of Entra ID group object IDs for the user.
    @returns: A pandas DataFrame containing authorized table metadata.
    """
    if is_demo_mode():
        return _DEMO_TABLES
    group_placeholders = (
        ", ".join(f"%(group_{i})s" for i in range(len(groups))) if groups else "''"
    )
    params: dict = {}
    if groups:
        for i, group in enumerate(groups):
            params[f"group_{i}"] = group
    sql_query = (
        """
        SELECT DISTINCT
            m.full_name,
            m.catalog_name,
            m.schema_name,
            m.table_name,
            m.comment as table_description,
            m.table_type,
            m.updated_at,
            COALESCE(dq.dq_score, '') AS dq_score,
            COALESCE(dq.last_run_status, '') AS dq_status
        FROM {0}.{1}.tables_metadata m
        JOIN {0}.{1}.permissions_cache p
          ON m.full_name = p.table_full_name
        LEFT JOIN {0}.{1}.data_quality_cache dq
          ON m.full_name = dq.table_full_name
        WHERE (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS')
    """
    ).format(CATALOG_CACHE, SCHEMA_CACHE, group_placeholders)  # nosec B608
    return run_query(sql_query, params)


@st.cache_data(ttl="1h", show_spinner=False)
def get_multi_hop_lineage(table_full_name: str, depth: int = 1):
    """Fetch lineage edges up to a given depth."""
    sql_query = (
        """
        WITH RECURSIVE lineage_cte AS (
            SELECT
                table_full_name,
                direction,
                entity_full_name,
                entity_type,
                1 AS depth
            FROM {0}.{1}.lineage_cache
            WHERE table_full_name = %(fn)s

            UNION ALL

            SELECT
                lc.table_full_name,
                lc.direction,
                lc.entity_full_name,
                lc.entity_type,
                cte.depth + 1
            FROM {0}.{1}.lineage_cache lc
            JOIN lineage_cte cte
              ON lc.table_full_name = cte.entity_full_name
             AND lc.direction = cte.direction
            WHERE cte.depth < %(depth)s
        )
        SELECT * FROM lineage_cte
    """
    ).format(CATALOG_CACHE, SCHEMA_CACHE)

    return run_query(sql_query, {"fn": table_full_name, "depth": depth})


@st.cache_data(ttl="1h", show_spinner=False)
def search_all_metadata(query: str, groups: tuple):
    """Search across tables, columns, and glossary terms using a UNION query.

    Permission-filtered: results are limited to tables the user's Entra
    groups have grants on (or tables marked ``SELECT_ALL_USERS``).

    Like get_authorized_tables, this enforces row-level access control.
    A table or its columns are returned only if the user's Entra ID groups
    intersect with the table's allowed principals, or if it is public.

    Match domains:
      1. Tables   — name, description.
      2. Columns  — name, comment, business_name override, definition override.
      3. Glossary — term, definition (only present in demo mode today).

    Each result row is scored to drive ordering:
      - Exact match     → 5 (Tables) / 2 (Columns)
      - Prefix match    → 4 (Tables) / 1 (Columns)
      - Substring match → 3 (Tables) / 0 (Columns)
      - Glossary match  → 1

    @param query:  user-entered search string, matched via SQL ``LIKE '%q%'``.
    @param groups: tuple of Entra ID group Object IDs the user belongs to.
    @returns:      pandas DataFrame of combined results, sorted by score desc.
    """
    import logging

    logging.info("GLOBAL SEARCH query=%s groups=%s", query, groups)

    group_placeholders = (
        ", ".join(f"%(group_{i})s" for i in range(len(groups))) if groups else "''"
    )
    params: dict = {f"group_{i}": g for i, g in enumerate(groups)} if groups else {}
    params["q"] = f"%{query}%"

    _overrides_tbl = (
        "user_data.business_name_overrides"
        if _duckdb_available()
        else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides"
    )

    sql_query = (
        """
        SELECT DISTINCT
            m.full_name, m.table_name AS name, 'Table' AS match_type,
            m.comment AS description, m.catalog_name, m.schema_name, m.table_name,
            m.comment AS table_description,
            COALESCE(dq.dq_score, '') AS dq_score
        FROM {0}.{1}.tables_metadata m
        JOIN {0}.{1}.permissions_cache p ON m.full_name = p.table_full_name
        LEFT JOIN {0}.{1}.data_quality_cache dq ON m.full_name = dq.table_full_name
        WHERE (m.table_name LIKE %(q)s OR m.comment LIKE %(q)s)
          AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS')

        UNION ALL

        SELECT DISTINCT
            c.table_full_name AS full_name,
            COALESCE(o.business_name, c.column_name) AS name,
            'Column' AS match_type,
            COALESCE(o.definition, c.comment) AS description,
            t.catalog_name, t.schema_name, t.table_name, t.comment AS table_description,
            COALESCE(dq.dq_score, '') AS dq_score
        FROM {0}.{1}.columns_metadata c
        JOIN {0}.{1}.permissions_cache p ON c.table_full_name = p.table_full_name
        JOIN {0}.{1}.tables_metadata t ON c.table_full_name = t.full_name
        LEFT JOIN {0}.{1}.data_quality_cache dq ON c.table_full_name = dq.table_full_name
        LEFT JOIN {3} o ON o.table_full_name = c.table_full_name AND o.column_name = c.column_name
        WHERE (
            c.column_name LIKE %(q)s OR c.comment LIKE %(q)s
            OR o.business_name LIKE %(q)s OR o.definition LIKE %(q)s
          )
          AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS')

        LIMIT 50
    """
    ).format(CATALOG_CACHE, SCHEMA_CACHE, group_placeholders, _overrides_tbl)  # nosec B608

    sql_results = run_query(sql_query, params)

    if sql_results is not None and not sql_results.empty:
        if "match_type" not in sql_results.columns:
            sql_results = sql_results.assign(match_type="Table")
        if "name" not in sql_results.columns:
            sql_results = sql_results.assign(name=sql_results.get("table_name", ""))
        if "description" not in sql_results.columns:
            _desc_src = (
                sql_results["table_description"]
                if "table_description" in sql_results.columns
                else sql_results.get("comment", "")
            )
            sql_results = sql_results.assign(description=_desc_src)

    term_matches = []
    if _DEMO_GLOSSARY is not None and not _DEMO_GLOSSARY.empty and query:
        _auth_df = get_authorized_tables(groups)
        _allowed_fns = (
            set(_auth_df["full_name"].tolist())
            if _auth_df is not None and not _auth_df.empty
            else set()
        )
        query_lower = query.lower()
        mask = _DEMO_GLOSSARY["term"].str.lower().str.contains(
            query_lower, regex=False, na=False
        ) | _DEMO_GLOSSARY["definition"].str.lower().str.contains(
            query_lower, regex=False, na=False
        )
        glossary_df = _DEMO_GLOSSARY[mask]
        for row in glossary_df.itertuples(index=False):
            related_tables = getattr(row, "related_tables", [])
            target_table = related_tables[0] if related_tables else ""
            if target_table and target_table not in _allowed_fns:
                continue
            parts = target_table.split(".")
            term_matches.append(
                {
                    "full_name": target_table,
                    "name": getattr(row, "term", ""),
                    "match_type": "Glossary",
                    "description": getattr(row, "definition", ""),
                    "table_description": "",
                    "catalog_name": parts[0] if len(parts) == 3 else "",
                    "schema_name": parts[1] if len(parts) == 3 else "",
                    "table_name": parts[2] if len(parts) == 3 else "",
                }
            )

    if term_matches:
        glossary_results = pd.DataFrame(term_matches)
        combined = (
            pd.concat([sql_results, glossary_results], ignore_index=True)
            if sql_results is not None and not sql_results.empty
            else glossary_results
        )
    else:
        combined = sql_results

    if combined is None or combined.empty:
        return combined

    q_lower = query.lower()

    def _score(row):
        name = str(row.get("name") or "").lower()
        mtype = str(row.get("match_type") or "")
        if mtype == "Table":
            if name == q_lower:
                return 5
            if name.startswith(q_lower):
                return 4
            if q_lower in name:
                return 3
            return 2
        if mtype == "Column":
            if name == q_lower:
                return 2
            if name.startswith(q_lower):
                return 1
            return 0
        return 1  # Glossary

    combined = combined.copy()
    combined["_score"] = combined.apply(_score, axis=1)
    return (
        combined.sort_values("_score", ascending=False)
        .drop(columns=["_score"])
        .reset_index(drop=True)
    )


def get_column_business_names(table_full_name: str) -> dict:
    """Return column business name overrides for a table as a dict."""
    if is_demo_mode():
        return st.session_state.get("demo_business_names", {}).get(table_full_name, {})
    try:
        conn = get_db_connection()
        tbl = (
            "user_data.business_name_overrides"
            if _duckdb_available()
            else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides"
        )
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT column_name, business_name, definition, edited_by, edited_at "
                f"FROM {tbl} "
                f"WHERE table_full_name = %(table_full_name)s",
                {"table_full_name": table_full_name},
            )
            rows = cursor.fetchall_as_pandas()
            if rows is not None and not rows.empty:
                return {
                    str(getattr(r, "column_name", "")): {
                        "business_name": str(getattr(r, "business_name", ""))
                        if getattr(r, "business_name", None)
                        else "",
                        "definition": str(getattr(r, "definition", ""))
                        if getattr(r, "definition", None)
                        else "",
                        "edited_by": str(getattr(r, "edited_by", "")),
                        "edited_at": str(getattr(r, "edited_at", "")),
                    }
                    for r in rows.itertuples(index=False)
                }
    except Exception as e:
        logging.warning(
            "Could not fetch column business names for %s: %s", table_full_name, e
        )
    return {}


def export_schema_to_csv(cols: pd.DataFrame, col_overrides: dict) -> str:
    """Export table column metadata to a CSV string.

    Includes business name and definition overrides if present.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Column Name",
            "Business Name",
            "Data Type",
            "System Description",
            "Business Definition",
        ]
    )

    if cols is not None and not cols.empty:
        for c in cols.itertuples(index=False):
            cname = str(getattr(c, "column_name", ""))
            ctype = str(getattr(c, "data_type", ""))
            ccomment = str(getattr(c, "comment", "") or "")

            override = col_overrides.get(cname, {})
            biz_name = override.get("business_name", "")
            biz_def = override.get("definition", "")

            writer.writerow([cname, biz_name, ctype, ccomment, biz_def])

    return output.getvalue()
