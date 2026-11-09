"""DB connection router and base query executor.

Provides the write-connection helper and a backend-agnostic run_query()
that dispatches to DuckDB (if available) or Databricks. Demo-mode
interception (returning _DEMO_* fixtures) lives directly within the
run_query() function to ensure this module handles the 3-tier routing
architecture (Demo -> DuckDB -> Databricks) transparently for callers.
"""
from __future__ import annotations


import csv
import io
import os
import pandas as pd
import numpy as np
import streamlit as st
from src.i18n import get_current_locale
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





def business_name_expr(table_alias: str = "m") -> str:
    """Locale-aware SQL expression for the user-facing table name.

    Returns ``COALESCE(<alias>.business_name_<locale>, <alias>.table_name)``
    so every read surfaces the friendly name when present and the technical
    name otherwise. Use as a SELECT expression — caller adds the column alias.
    """
    col = "business_name_fr" if get_current_locale() == "fr" else "business_name_en"
    return f"COALESCE({table_alias}.{col}, {table_alias}.table_name)"


def business_definition_expr(table_alias: str = "m") -> str:
    """Locale-aware SQL expression for the friendly definition (no fallback —
    callers chain their own COALESCE if they also want the technical comment).
    """
    col = "business_definition_fr" if get_current_locale() == "fr" else "business_definition_en"
    return f"{table_alias}.{col}"



def _build_auth_filters(groups: list | tuple) -> tuple[str, dict]:
    """Helper to build authorization SQL and params for queries.

    WHY IT EXISTS:
    Acts as a fundamental security/authorization filter. This creates a dynamic
    number of pyformat parameter placeholders (e.g., `%(group_0)s`) and maps
    them to the provided AD groups. This allows secure, parameterized filtering
    of Unity Catalog metadata against the user's group memberships while preventing
    SQL injection.

    Args:
        groups (list | tuple): A list or tuple of string group IDs the user belongs to.

    Returns:
        tuple[str, dict]: A tuple containing:
            1. The comma-separated pyformat placeholders string
            2. A dictionary mapping placeholder names to group string values
    """
    if not groups:
        return "''", {}

    group_placeholders = ", ".join(f"%(group_{i})s" for i in range(len(groups)))
    params = {f"group_{i}": group for i, group in enumerate(groups)}

    return group_placeholders, params


def _get_override_table_name(table_type: str = "table_metadata") -> str:
    """Helper to resolve the override table name based on DuckDB availability."""
    if _duckdb_available():
        return f"user_data.{table_type}_overrides"
    return f"{CATALOG_CACHE}.{SCHEMA_CACHE}.{table_type}_overrides"


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
            "Direct Databricks writes were removed; the "
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
    It is used by run_query() after demo-mode interception, and directly by
    admin/health queries that guard the demo branch themselves.
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

    Args:
        query (str): The SQL query to execute.
        params (dict, optional): Optional dictionary of parameters to substitute into the query.

    Returns:
        pd.DataFrame: A pandas DataFrame containing the query results.
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
        fn = p.get("table_full_name") or p.get("full_name") or p.get("fn", "")
        if "lineage_cache" in query:
            return _DEMO_LINEAGE.get(
                fn,
                pd.DataFrame(columns=["direction", "entity_full_name", "entity_type"]),
            )
        if "columns_metadata" in query:
            return _DEMO_COLUMNS.get(
                fn, pd.DataFrame(columns=["column_name", "data_type", "comment"])
            )
        if "tables_metadata" in query:
            return _DEMO_TABLES[_DEMO_TABLES["full_name"] == fn]

        return _DEMO_GRANTS.get(fn, pd.DataFrame(columns=["principal", "privilege"]))

    return _base_run_query(query, params)


@st.cache_data(ttl="1h", show_spinner=False)
def get_authorized_table_names(groups):
    """Retrieve a set of full names for tables the user is authorized to access."""
    df = get_authorized_tables(groups)
    return set(df["full_name"]) if df is not None and not df.empty else set()


@st.cache_data(ttl="1h", show_spinner=False)
def get_authorized_tables(groups):
    """Retrieve metadata for tables the user is authorized to access.

    Implements row-level access control by joining the tables metadata with
    a permissions cache. A table is returned only if the user's Entra ID groups
    intersect with the table's allowed principals, or if the table is marked
    public with the sentinel value `SELECT_ALL_USERS`.

    Args:
        groups (list or tuple): A list or tuple of Entra ID group object IDs for the user.

    Returns:
        pd.DataFrame: A pandas DataFrame containing authorized table metadata.
    """
    if is_demo_mode():
        return _DEMO_TABLES
    group_placeholders, params = _build_auth_filters(groups)
    _table_overrides_tbl = _get_override_table_name("table_metadata")

    sql_query = (
        """
        SELECT DISTINCT
            m.full_name,
            m.catalog_name,
            m.schema_name,
            m.table_name,
            COALESCE(o.description, m.comment) as table_description,
            m.table_type,
            m.updated_at,
            COALESCE(dq.dq_score, '') AS dq_score,
            COALESCE(dq.last_run_status, '') AS dq_status
        FROM {0}.{1}.tables_metadata m
        JOIN {0}.{1}.permissions_cache p
          ON m.full_name = p.table_full_name
        LEFT JOIN {3} o
          ON m.full_name = o.table_full_name
        LEFT JOIN {0}.{1}.data_quality_cache dq
          ON m.full_name = dq.table_full_name
        WHERE (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS')
    """
    ).format(CATALOG_CACHE, SCHEMA_CACHE, group_placeholders, _table_overrides_tbl)  # nosec B608
    return run_query(sql_query, params)


@st.cache_data(ttl="1h", show_spinner=False)
def get_multi_hop_lineage(table_full_name: str, depth: int = 1):
    """Fetch lineage edges up to a given depth.

    Args:
        table_full_name (str): The Unity Catalog full name of the table to trace.
        depth (int): The maximum number of hops to traverse up/downstream. Defaults to 1.

    Returns:
        pd.DataFrame: A pandas DataFrame containing lineage edges with columns for direction, entity name, entity type, and depth.
    """
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
    ).format(CATALOG_CACHE, SCHEMA_CACHE)  # nosec B608

    return run_query(sql_query, {"fn": table_full_name, "depth": depth})


# Hybrid fusion weights: keyword (BM25-style 0-5 score) vs semantic rank.
_HYBRID_KEYWORD_WEIGHT = 0.7
_HYBRID_SEMANTIC_WEIGHT = 0.3


def _drop_score_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Remove internal scoring columns from search results before returning.

    Search queries generate intermediate `_score` (keyword relevance) and
    `_hybrid_score` (combined keyword + semantic relevance) columns for sorting.
    This helper cleans up the DataFrame to prevent leaking internal metrics
    to the UI and breaking structural assumptions in downstream rendering components.

    Args:
        df (pd.DataFrame): The search results DataFrame potentially containing score columns.

    Returns:
        pd.DataFrame: A cleaned DataFrame with score columns removed and index reset.
    """
    cols = [c for c in ("_score", "_hybrid_score") if c in df.columns]
    return df.drop(columns=cols).reset_index(drop=True) if cols else df


@st.cache_data(ttl="1h", show_spinner=False)
def search_all_metadata(query: str, groups: tuple):
    """Hybrid search: keyword-based (BM25) + semantic vector similarity."""
    # 1. Keyword search (carries a 0-5 `_score` column)
    keyword_results = _search_keywords(query, groups)

    # 2. Semantic search — lazy import avoids circular dep
    semantic_fns = []
    if os.getenv("ENABLE_SEMANTIC_SEARCH") == "true":
        try:
            from src.semantic import semantic_search  # noqa: PLC0415
            semantic_fns = semantic_search(query)
        except Exception:
            pass

    if not semantic_fns:
        if keyword_results is None or keyword_results.empty:
            return keyword_results
        return _drop_score_cols(keyword_results)

    if keyword_results is None or keyword_results.empty:
        # Keyword search found nothing: return semantic hits in rank order.
        results = _fetch_metadata_for_fns(semantic_fns, groups)
        if results is None or results.empty:
            return results
        n = len(semantic_fns)
        # ⚡ Bolt: Replace .map() with pd.Categorical and np.where for faster, vectorised arbitrary list scoring
        cats = pd.Categorical(results["full_name"], categories=semantic_fns, ordered=True)
        results = results.copy()
        results["_hybrid_score"] = np.where(cats.codes != -1, -cats.codes, -n)
        return _drop_score_cols(
            results.sort_values("_hybrid_score", ascending=False, kind="stable")
        )

    # 3. Weighted fusion. Keyword `_score` is normalized to [0, 1]; the
    # semantic contribution decays linearly with rank in `semantic_fns`.
    combined = keyword_results.copy()
    # ⚡ Bolt: Replace .unique().tolist() with just .unique() for faster set construction
    known_fns = set(combined["full_name"])
    missing_fns = [fn for fn in semantic_fns if fn not in known_fns]
    if missing_fns:
        extra = _fetch_metadata_for_fns(missing_fns, groups)
        if extra is not None and not extra.empty:
            extra = extra.copy()
            extra["_score"] = 0  # no keyword relevance
            combined = pd.concat([combined, extra], ignore_index=True)

    if "_score" in combined.columns:
        kw_score = (
            pd.to_numeric(combined["_score"], errors="coerce").fillna(0.0) / 5.0
        )
    else:
        kw_score = 0.0
    n = len(semantic_fns)
    # ⚡ Bolt: Replace .map() with pd.Categorical and np.where for faster, vectorised arbitrary list scoring
    safe_n = max(n, 1)
    cats = pd.Categorical(combined["full_name"], categories=semantic_fns, ordered=True)
    sem_score = np.where(cats.codes != -1, (n - cats.codes) / safe_n, 0.0)
    combined["_hybrid_score"] = (
        _HYBRID_KEYWORD_WEIGHT * kw_score + _HYBRID_SEMANTIC_WEIGHT * sem_score
    )
    return _drop_score_cols(
        combined.sort_values("_hybrid_score", ascending=False, kind="stable")
    )


def _fetch_metadata_for_fns(full_names: list[str], groups: tuple) -> pd.DataFrame:
    """Fetch basic table metadata for a list of full names."""
    if not full_names:
        return pd.DataFrame()
    
    group_placeholders, params = _build_auth_filters(groups)
    params["fns"] = full_names

    sql = f"""
        SELECT DISTINCT
            m.full_name, m.table_name AS name, 'Table' AS match_type,
            m.comment AS description, m.catalog_name, m.schema_name, m.table_name,
            m.comment AS table_description,
            COALESCE(dq.dq_score, '') AS dq_score,
            1 AS _score
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata m
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache p ON m.full_name = p.table_full_name
        LEFT JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.data_quality_cache dq ON m.full_name = dq.table_full_name
        WHERE m.full_name IN (SELECT unnest(%(fns)s))
          AND (p.principal IN ({group_placeholders}) OR p.principal = 'SELECT_ALL_USERS')
    """
    return run_query(sql, params)


def _search_keywords(query: str, groups: tuple):
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

    Args:
        query (str): user-entered search string, matched via SQL ``LIKE '%q%'``.
        groups (tuple): tuple of Entra ID group Object IDs the user belongs to.

    Returns:
        pd.DataFrame: pandas DataFrame of combined results, sorted by score desc.
    """

    logging.info("GLOBAL SEARCH query=%s groups=%s", query, groups)

    group_placeholders, params = _build_auth_filters(groups)
    params["q"] = f"%{query}%"

    _overrides_tbl = _get_override_table_name("business_name")
    _table_overrides_tbl = _get_override_table_name("table_metadata")

    _bn_expr  = business_name_expr("m")
    _bdf_expr = business_definition_expr("m")

    sql_query = (
        """
        SELECT DISTINCT
            m.full_name,
            """ + _bn_expr + """ AS name,
            'Table' AS match_type,
            COALESCE(""" + _bdf_expr + """, o.description, m.comment) AS description,
            m.catalog_name, m.schema_name, m.table_name,
            COALESCE(""" + _bdf_expr + """, o.description, m.comment) AS table_description,
            COALESCE(dq.dq_score, '') AS dq_score,
            m.business_name_en, m.business_name_fr,
            m.business_definition_en, m.business_definition_fr
        FROM {0}.{1}.tables_metadata m
        JOIN {0}.{1}.permissions_cache p ON m.full_name = p.table_full_name
        LEFT JOIN {3} o ON m.full_name = o.table_full_name
        LEFT JOIN {0}.{1}.data_quality_cache dq ON m.full_name = dq.table_full_name
        WHERE (
              m.table_name LIKE %(q)s
              OR m.comment LIKE %(q)s
              OR o.description LIKE %(q)s
              OR m.business_name_en LIKE %(q)s
              OR m.business_name_fr LIKE %(q)s
              OR m.business_definition_en LIKE %(q)s
              OR m.business_definition_fr LIKE %(q)s
        )
          AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS')

        UNION ALL

        SELECT DISTINCT
            c.table_full_name AS full_name,
            COALESCE(ob.business_name, c.column_name) AS name,
            'Column' AS match_type,
            COALESCE(ob.definition, c.comment) AS description,
            t.catalog_name, t.schema_name, t.table_name,
            COALESCE(ot.description, t.comment) AS table_description,
            COALESCE(dq.dq_score, '') AS dq_score,
            t.business_name_en, t.business_name_fr,
            t.business_definition_en, t.business_definition_fr
        FROM {0}.{1}.columns_metadata c
        JOIN {0}.{1}.permissions_cache p ON c.table_full_name = p.table_full_name
        JOIN {0}.{1}.tables_metadata t ON c.table_full_name = t.full_name
        LEFT JOIN {3} ot ON c.table_full_name = ot.table_full_name
        LEFT JOIN {0}.{1}.data_quality_cache dq ON c.table_full_name = dq.table_full_name
        LEFT JOIN {4} ob ON ob.table_full_name = c.table_full_name AND ob.column_name = c.column_name
        WHERE (
            c.column_name LIKE %(q)s OR c.comment LIKE %(q)s
            OR ob.business_name LIKE %(q)s OR ob.definition LIKE %(q)s
          )
          AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS')

        LIMIT 50
    """
    ).format(CATALOG_CACHE, SCHEMA_CACHE, group_placeholders, _table_overrides_tbl, _overrides_tbl)  # nosec B608

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
        _allowed_fns = get_authorized_table_names(groups)
        query_lower = query.lower()
        mask = _DEMO_GLOSSARY["term"].str.lower().str.contains(
            query_lower, regex=False, na=False
        ) | _DEMO_GLOSSARY["definition"].str.lower().str.contains(
            query_lower, regex=False, na=False
        )
        glossary_df = _DEMO_GLOSSARY[mask]
        # ⚡ Bolt: Replace slow itertuples() and getattr() with fast native dictionary iteration
        for row in glossary_df.to_dict("records"):
            related_tables = row.get("related_tables", [])
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

    # ⚡ Bolt: Replace .apply() with vectorized scoring for faster performance
    combined = combined.copy()

    # Safely convert to string and lower
    # ⚡ Bolt: Use .to_numpy() array casting before boolean evaluation to avoid Pandas index alignment overhead
    names = combined["name"].fillna("").astype(str).str.lower().to_numpy()
    mtypes = combined["match_type"].fillna("").astype(str).to_numpy()

    # Initialize scores with default Glossary value
    scores = np.where(mtypes == "Glossary", 1, 0)

    # ⚡ Bolt: Replace sequential boolean mask indexing with vectorized np.where for faster array assignments
    # Table masks
    table_mask = mtypes == "Table"
    if table_mask.any():
        table_names = names[table_mask]
        scores[table_mask] = np.where(
            table_names == q_lower, 5,
            np.where(
                np.char.startswith(table_names.astype(str), q_lower), 4,
                np.where(np.char.find(table_names.astype(str), q_lower) != -1, 3, 2)
            )
        )

    # Column masks
    col_mask = mtypes == "Column"
    if col_mask.any():
        col_names = names[col_mask]
        scores[col_mask] = np.where(
            col_names == q_lower, 2,
            np.where(np.char.startswith(col_names.astype(str), q_lower), 1, 0)
        )

    combined["_score"] = scores
    return (
        combined.sort_values("_score", ascending=False)
        .reset_index(drop=True)
    )





def export_schema_to_csv(cols: pd.DataFrame, col_overrides: dict) -> str:
    """Export table column metadata to a CSV string.

    Includes business name and definition overrides if present.

    Args:
        cols (pd.DataFrame): A DataFrame containing the columns_metadata.
        col_overrides (dict): A dictionary mapping column names to override dictionaries.

    Returns:
        str: A CSV-formatted string of the table metadata.
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
        cnames = cols["column_name"].tolist() if "column_name" in cols else [""] * len(cols)
        ctypes = cols["data_type"].tolist() if "data_type" in cols else [""] * len(cols)
        ccomments = cols["comment"].tolist() if "comment" in cols else [""] * len(cols)

        for cname_raw, ctype_raw, ccomment_raw in zip(cnames, ctypes, ccomments):
            cname = str(cname_raw)
            ctype = str(ctype_raw)
            ccomment = str(ccomment_raw or "")

            override = col_overrides.get(cname, {})
            biz_name = override.get("business_name", "")
            biz_def = override.get("definition", "")

            writer.writerow([cname, biz_name, ctype, ccomment, biz_def])

    return output.getvalue()
