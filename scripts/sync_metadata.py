import os
import sys
import concurrent.futures
from databricks.sdk import WorkspaceClient
from databricks import sql
from dotenv import load_dotenv

load_dotenv()

# Configuration
CATALOG_CACHE = "data_governance"
SCHEMA_CACHE = "dictionary_cache"

def get_sql_connection():
    return sql.connect(
        server_hostname=os.getenv("DATABRICKS_HOST"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_TOKEN")
    )

def setup_cache_tables():
    """Ensures the target schema and tables exist in the SQL Warehouse."""
    print(f"Setting up cache tables in {CATALOG_CACHE}.{SCHEMA_CACHE}...")
    with get_sql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE CATALOG IF NOT EXISTS {CATALOG_CACHE}")
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}")
            
            # Table for structural metadata
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata (
                    full_name              STRING,
                    catalog_name           STRING,
                    schema_name            STRING,
                    table_name             STRING,
                    table_type             STRING,
                    comment                STRING,
                    updated_at             TIMESTAMP,
                    steward_email          STRING,
                    business_name_en       STRING,
                    business_name_fr       STRING,
                    business_definition_en STRING,
                    business_definition_fr STRING
                )
            """)
            # Forward-compatibility migrations for caches created before the
            # business-name columns existed. ADD COLUMN IF NOT EXISTS is a
            # Databricks Runtime 14.0+ feature; the four NOOPs on a fresh
            # CREATE above are cheap.
            for _col in (
                "business_name_en", "business_name_fr",
                "business_definition_en", "business_definition_fr",
            ):
                cursor.execute(
                    f"ALTER TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata "
                    f"ADD COLUMN IF NOT EXISTS {_col} STRING"
                )
            
            # Table for column details
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata (
                    table_full_name STRING,
                    column_name STRING,
                    data_type STRING,
                    comment STRING
                )
            """)
            
            # Table for permission mapping
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache (
                    table_full_name STRING,
                    principal STRING,
                    privilege STRING
                )
            """)

            # Table for lineage edges (1-hop upstream / downstream)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.lineage_cache (
                    table_full_name  STRING,
                    direction        STRING,
                    entity_full_name STRING,
                    entity_type      STRING
                )
            """)

            # Table for tags (Glossary / Discovery metadata)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.object_tags (
                    object_type      STRING,
                    object_full_name STRING,
                    tag_key          STRING,
                    tag_value        STRING
                )
            """)

            # Table for user comments (append-only — never truncated by sync)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.comments (
                    comment_id        STRING,
                    object_type       STRING,
                    object_name       STRING,
                    comment_text      STRING,
                    author_name       STRING,
                    author_email      STRING,
                    created_at        TIMESTAMP,
                    steward_email     STRING,
                    parent_comment_id STRING
                )
            """)

            # Table for human-friendly business name overrides (power-user edits)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides (
                    table_full_name STRING,
                    column_name     STRING,
                    business_name   STRING,
                    definition      STRING,
                    edited_by       STRING,
                    edited_at       TIMESTAMP
                )
            """)

            # Table for audit events (business name changes, comments)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log (
                    event_id        STRING,
                    event_type      STRING,
                    object_type     STRING,
                    object_name     STRING,
                    actor_email     STRING,
                    old_value       STRING,
                    new_value       STRING,
                    created_at      TIMESTAMP
                )
            """)

            # Table for data quality scorecard cache
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.data_quality_cache (
                    table_full_name STRING,
                    dq_score        STRING,
                    last_run_status STRING,
                    freshness       STRING
                )
            """)

            # Table for semantic search embeddings (Phase 2 Scaffolding)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_embedding_cache (
                    table_full_name STRING,
                    embedding       ARRAY<FLOAT>
                )
            """)

def push_business_name_overrides():
    """Write column business name overrides back to Unity Catalog as column comments."""
    print("📝 Pushing business name overrides to Unity Catalog...")
    with get_sql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT table_full_name, column_name, business_name, definition "
                f"FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides"
            )
            overrides = cursor.fetchall_as_pandas()

    if overrides is None or overrides.empty:
        print("  No overrides to push.")
        return

    with get_sql_connection() as conn:
        with conn.cursor() as cursor:
            for row in overrides.itertuples(index=False):
                raw_full_name = str(getattr(row, "table_full_name", ""))
                raw_col_name  = str(getattr(row, "column_name", ""))
                raw_biz_name  = str(getattr(row, "business_name", ""))
                full_name_q = ".".join(
                    f"`{p.replace('`', '``')}`" for p in raw_full_name.split(".")
                )
                col_name_q = f"`{raw_col_name.replace('`', '``')}`"
                try:
                    cursor.execute(
                        f"ALTER TABLE {full_name_q} "
                        f"ALTER COLUMN {col_name_q} SET COMMENT %(comment)s",
                        {"comment": raw_biz_name},
                    )
                    print(f"  ✓ {raw_full_name}.{raw_col_name}")
                except Exception as e:
                    print(f"  ✗ {raw_full_name}.{raw_col_name}: {e}")


def enrich_dq_from_monitoring(cursor, table_full_names: list, tag_dq: list) -> list:
    """Attempt to enrich DQ data from Lakehouse Monitoring system tables.

    Primary source: system.lakeformation.quality_monitors_statistics (if available).
    Falls back to tag-based DQ already collected during schema traversal.
    Returns a merged list deduplicated by table_full_name (monitoring wins).
    """
    monitoring_dq: dict[str, dict] = {}
    try:
        placeholders = ", ".join(f"'{n}'" for n in table_full_names[:200])  # cap for IN clause
        cursor.execute(f"""
            SELECT table_name,
                   AVG(CASE WHEN status = 'PASS' THEN 100 WHEN status = 'FAIL' THEN 0 ELSE 50 END) AS dq_score,
                   MAX(status) AS last_run_status,
                   MAX(run_timestamp) AS freshness
            FROM system.lakeformation.quality_monitors_statistics
            WHERE table_name IN ({placeholders})
            GROUP BY table_name
        """)
        for row in cursor.fetchall_as_pandas().itertuples(index=False):
            monitoring_dq[str(row.table_name)] = {
                "table_full_name": str(row.table_name),
                "dq_score":        str(int(round(float(row.dq_score or 0)))),
                "last_run_status": str(row.last_run_status or ""),
                "freshness":       str(row.freshness or ""),
            }
    except Exception as e:
        print(f"  Lakehouse Monitoring unavailable, using tag-based DQ: {e}")

    # Merge: monitoring wins, fall back to tag-based for tables not in monitoring
    tag_dq_map = {r["table_full_name"]: r for r in (tag_dq or [])}
    merged = {**tag_dq_map, **monitoring_dq}
    return list(merged.values())


def fetch_lineage(w, full_name):
    """Returns 1-hop upstream/downstream lineage edges for *full_name*."""
    entries = []
    try:
        result = w.api_client.do(
            "GET",
            "/api/2.0/lineage-tracking/table-lineage",
            query={"table_name": full_name},
        )
        for up in result.get("upstream_tables", []):
            name = up.get("name") or up.get("full_name")
            if name:
                entries.append({
                    "table_full_name":  full_name,
                    "direction":        "UPSTREAM",
                    "entity_full_name": name,
                    "entity_type":      up.get("table_type", "TABLE"),
                })
        for down in result.get("downstream_tables", []):
            name = down.get("name") or down.get("full_name")
            if name:
                entries.append({
                    "table_full_name":  full_name,
                    "direction":        "DOWNSTREAM",
                    "entity_full_name": name,
                    "entity_type":      down.get("table_type", "TABLE"),
                })
    except Exception as e:
        print(f"    Lineage unavailable for {full_name}: {e}")
    return entries


def sync():
    print("🚀 Starting Unity Catalog metadata sync...")
    w = WorkspaceClient()
    
    # Initialize lists to hold our extracted data
    tables_data = []
    columns_data = []
    permissions_data = []
    lineage_data = []
    tags_data = []
    data_quality_data = []

    def fetch_schema_metadata(catalog_name, schema_name, schema_properties):
        print(f"  Processing schema: {schema_name}")
        local_tables = []
        local_columns = []
        local_table_names = []
        local_tags = []
        local_dq = []

        schema_full_name = f"{catalog_name}.{schema_name}"
        if schema_properties:
            for k, v in schema_properties.items():
                local_tags.append({"object_type": "SCHEMA", "object_full_name": schema_full_name, "tag_key": k, "tag_value": str(v)})

        try:
            for table in w.tables.list(catalog_name=catalog_name, schema_name=schema_name):
                full_name = f"{catalog_name}.{schema_name}.{table.name}"
                local_table_names.append(full_name)

                # Store table metadata
                local_tables.append({
                    "full_name":     full_name,
                    "catalog_name":  catalog_name,
                    "schema_name":   schema_name,
                    "table_name":    table.name,
                    "table_type":    str(table.table_type),
                    "comment":       table.comment or "",
                    "steward_email": (table.properties or {}).get("steward_email", ""),
                })

                # Extract Table Tags and DQ properties
                if table.properties:
                    dq_score, dq_last_run_status, dq_freshness = None, None, None
                    for k, v in table.properties.items():
                        local_tags.append({"object_type": "TABLE", "object_full_name": full_name, "tag_key": k, "tag_value": str(v)})
                        if k.lower() == "dq_score":
                            dq_score = str(v)
                        elif k.lower() in ("last_run_status", "dq_last_run_status"):
                            dq_last_run_status = str(v)
                        elif k.lower() in ("freshness", "dq_freshness"):
                            dq_freshness = str(v)

                    if dq_score or dq_last_run_status or dq_freshness:
                        local_dq.append({
                            "table_full_name": full_name,
                            "dq_score": dq_score or "",
                            "last_run_status": dq_last_run_status or "",
                            "freshness": dq_freshness or "",
                        })

                # Store column metadata
                for col in table.columns:
                    local_columns.append({
                        "table_full_name": full_name,
                        "column_name": col.name,
                        "data_type": col.type_text,
                        "comment": col.comment or ""
                    })
        except Exception as e:
            print(f"  Error processing schema {schema_name}: {e}")

        return local_tables, local_columns, local_table_names, local_tags, local_dq

    # 1. Iterate through catalogs and build schema tasks
    schema_tasks = []
    for catalog in w.catalogs.list():
        if catalog.name in ['system', '__databricks_internal']:
            continue

        print(f"Processing catalog: {catalog.name}")
        
        # Extract Catalog Tags
        if catalog.properties:
            for k, v in catalog.properties.items():
                tags_data.append({"object_type": "CATALOG", "object_full_name": catalog.name, "tag_key": k, "tag_value": str(v)})

        for schema in w.schemas.list(catalog_name=catalog.name):
            schema_tasks.append((catalog.name, schema.name, schema.properties))

    # Fetch tables concurrently
    print(f"📦 Fetching tables for {len(schema_tasks)} schemas concurrently...")
    table_full_names = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_schema_metadata, cat_name, sch_name, sch_props) for cat_name, sch_name, sch_props in schema_tasks]
        for future in concurrent.futures.as_completed(futures):
            loc_tables, loc_columns, loc_full_names, loc_tags, loc_dq = future.result()
            tables_data.extend(loc_tables)
            columns_data.extend(loc_columns)
            table_full_names.extend(loc_full_names)
            tags_data.extend(loc_tags)
            data_quality_data.extend(loc_dq)

    # 2. Fetch permission grants and lineage concurrently
    print("🔐 Fetching permission grants...")
    table_full_names_set = set(table_full_names)
    try:
        with get_sql_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT table_catalog || '.' || table_schema || '.' || table_name as table_full_name,
                           grantee as principal,
                           privilege_type as privilege
                    FROM system.information_schema.table_privileges
                """)
                df = cursor.fetchall_as_pandas()
                if not df.empty:
                    df_filtered = df.loc[df['table_full_name'].isin(table_full_names_set), ['table_full_name', 'principal', 'privilege']]
                    permissions_data.extend(df_filtered.to_dict('records'))
    except Exception as e:
        print(f"    Could not fetch grants in bulk: {e}")

    print("🔗 Fetching lineage...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for entries in executor.map(lambda fn: fetch_lineage(w, fn), table_full_names):
            lineage_data.extend(entries)

    # 2b. Enrich DQ data from Lakehouse Monitoring (overwrites tag-based where available)
    print("📊 Enriching data quality metrics from Lakehouse Monitoring...")
    try:
        with get_sql_connection() as conn:
            with conn.cursor() as cursor:
                data_quality_data = enrich_dq_from_monitoring(cursor, table_full_names, data_quality_data)
    except Exception as e:
        print(f"  ⚠  DQ enrichment step failed: {e}")

    # 2b-bis. Enrich tables_data with bilingual friendly names + definitions
    # from the configured Unity Catalog reference table. Missing matches stay
    # null. A missing/renamed source table logs a warning and skips the step
    # — the rest of the sync continues so a one-off governance outage doesn't
    # blank-out the catalog.
    print("📛 Joining friendly names from business-names reference table...")
    try:
        if os.path.dirname(__file__) not in sys.path:
            sys.path.append(os.path.dirname(os.path.dirname(__file__)))
        from src.config import (  # noqa: PLC0415
            BUSINESS_NAMES_TABLE,
            BUSINESS_NAMES_COL_FULL_NAME,
            BUSINESS_NAMES_COL_NAME_EN,
            BUSINESS_NAMES_COL_NAME_FR,
            BUSINESS_NAMES_COL_DEF_EN,
            BUSINESS_NAMES_COL_DEF_FR,
        )
        with get_sql_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT {BUSINESS_NAMES_COL_FULL_NAME} AS full_name, "
                    f"       {BUSINESS_NAMES_COL_NAME_EN} AS name_en, "
                    f"       {BUSINESS_NAMES_COL_NAME_FR} AS name_fr, "
                    f"       {BUSINESS_NAMES_COL_DEF_EN}  AS def_en, "
                    f"       {BUSINESS_NAMES_COL_DEF_FR}  AS def_fr "
                    f"FROM {BUSINESS_NAMES_TABLE}"
                )
                bn_df = cursor.fetchall_as_pandas()
        bn_map = {
            str(r["full_name"]): r for r in bn_df.to_dict("records")
        } if bn_df is not None and not bn_df.empty else {}
        for row in tables_data:
            match = bn_map.get(row["full_name"])
            row["business_name_en"]       = (match["name_en"] if match is not None else None) or None
            row["business_name_fr"]       = (match["name_fr"] if match is not None else None) or None
            row["business_definition_en"] = (match["def_en"]  if match is not None else None) or None
            row["business_definition_fr"] = (match["def_fr"]  if match is not None else None) or None
        print(f"  matched {sum(1 for r in tables_data if r['business_name_en'] or r['business_name_fr'])} / {len(tables_data)} tables")
    except Exception as e:
        print(f"  ⚠  Friendly-name join failed ({e}); writing nulls for all rows")
        for row in tables_data:
            row.setdefault("business_name_en",       None)
            row.setdefault("business_name_fr",       None)
            row.setdefault("business_definition_en", None)
            row.setdefault("business_definition_fr", None)

    # 2c. Generate semantic embeddings for search (Phase 2)
    print("🧠 Generating semantic embeddings for search...")
    embeddings_data = []
    try:
        # sys.path adjustment to allow importing from src
        if os.path.dirname(__file__) not in sys.path:
            sys.path.append(os.path.dirname(os.path.dirname(__file__)))
        from src.semantic import generate_table_embeddings
        embeddings_data = generate_table_embeddings(tables_data)
    except Exception as e:
        print(f"  ⚠  Embedding generation failed: {e}")

    # 3. Load into Databricks SQL Warehouse
    print("📂 Loading data into SQL Warehouse...")
    with get_sql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata")
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata")
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache")
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.lineage_cache")
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.object_tags")
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.data_quality_cache")
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_embedding_cache")

            if tables_data:
                cursor.executemany(
                    f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata "
                    "VALUES (%(full_name)s, %(catalog_name)s, %(schema_name)s, "
                    "%(table_name)s, %(table_type)s, %(comment)s, current_timestamp(), "
                    "%(steward_email)s, %(business_name_en)s, %(business_name_fr)s, "
                    "%(business_definition_en)s, %(business_definition_fr)s)",
                    tables_data
                )
            if columns_data:
                cursor.executemany(
                    f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata VALUES (%(table_full_name)s, %(column_name)s, %(data_type)s, %(comment)s)",
                    columns_data
                )
            if permissions_data:
                cursor.executemany(
                    f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache VALUES (%(table_full_name)s, %(principal)s, %(privilege)s)",
                    permissions_data
                )
            if lineage_data:
                cursor.executemany(
                    f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.lineage_cache VALUES (%(table_full_name)s, %(direction)s, %(entity_full_name)s, %(entity_type)s)",
                    lineage_data
                )
            if tags_data:
                cursor.executemany(
                    f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.object_tags VALUES (%(object_type)s, %(object_full_name)s, %(tag_key)s, %(tag_value)s)",
                    tags_data
                )
            if data_quality_data:
                cursor.executemany(
                    f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.data_quality_cache VALUES (%(table_full_name)s, %(dq_score)s, %(last_run_status)s, %(freshness)s)",
                    data_quality_data
                )
            if embeddings_data:
                cursor.executemany(
                    f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_embedding_cache VALUES (%(table_full_name)s, %(embedding)s)",
                    embeddings_data
                )

    # Fetch audit_log for DuckDB export (rebuild from Databricks each sync)
    audit_log_data = []
    try:
        with get_sql_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT * FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log")
                audit_df = cursor.fetchall_as_pandas()
                if audit_df is not None and not audit_df.empty:
                    audit_log_data = audit_df.to_dict(orient="records")
    except Exception as e:
        print(f"  ⚠  Could not fetch audit_log for DuckDB: {e}")

    print("✅ Sync completed successfully.")
    push_business_name_overrides()
    write_duckdb(tables_data, columns_data, permissions_data, lineage_data, tags_data, data_quality_data, audit_log_data, embeddings_data)


def write_duckdb(
    tables_data: list,
    columns_data: list,
    permissions_data: list,
    lineage_data: list,
    tags_data: list,
    data_quality_data: list = None,
    audit_log_data: list = None,
    embeddings_data: list = None,
) -> None:
    """Export sync data to a local DuckDB file for fast local queries."""
    duckdb_path = os.getenv("DUCKDB_PATH", "")
    if not duckdb_path:
        return

    try:
        import duckdb
        import pandas as pd
    except ImportError:
        print("  ⚠  duckdb not installed — skipping local cache export.")
        return

    tmp_path = duckdb_path + ".tmp"
    print(f"📦 Exporting to DuckDB: {duckdb_path} ...")

    def _empty(cols):
        return pd.DataFrame({c: pd.Series(dtype=str) for c in cols})

    # --- Truncate-reload tables (rebuilt entirely on each sync) ---
    reload_frames = {
        "tables_metadata": pd.DataFrame(tables_data) if tables_data else _empty(
            ["full_name", "catalog_name", "schema_name", "table_name",
             "table_type", "comment", "updated_at", "steward_email"]),
        "columns_metadata": pd.DataFrame(columns_data) if columns_data else _empty(
            ["table_full_name", "column_name", "data_type", "comment"]),
        "permissions_cache": pd.DataFrame(permissions_data) if permissions_data else _empty(
            ["table_full_name", "principal", "privilege"]),
        "lineage_cache": pd.DataFrame(lineage_data) if lineage_data else _empty(
            ["table_full_name", "direction", "entity_full_name", "entity_type"]),
        "object_tags": pd.DataFrame(tags_data) if tags_data else _empty(
            ["object_type", "object_full_name", "tag_key", "tag_value"]),
        "data_quality_cache": pd.DataFrame(data_quality_data) if data_quality_data else _empty(
            ["table_full_name", "dq_score", "last_run_status", "freshness"]),
        "tables_embedding_cache": pd.DataFrame(embeddings_data) if embeddings_data else _empty(
            ["table_full_name", "embedding"]),
        "audit_log": pd.DataFrame(audit_log_data) if audit_log_data else _empty(
            ["event_id", "event_type", "object_type", "object_name",
             "actor_email", "old_value", "new_value", "created_at"]),
    }

    # --- Write to tmp, then atomic swap ---
    # Tables are written into the "dictionary_cache" schema so that the app's
    # 3-part SQL (data_governance.dictionary_cache.table) resolves when the file
    # is ATTACHed AS data_governance — same layout as the Databricks catalog.
    SCHEMA = SCHEMA_CACHE
    try:
        con = duckdb.connect(tmp_path)
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        for tbl, df in reload_frames.items():
            if df.empty:
                col_defs = ", ".join(f'"{c}" VARCHAR' for c in df.columns)
                con.execute(f"CREATE OR REPLACE TABLE {SCHEMA}.{tbl} ({col_defs})")
            else:
                con.execute(f"CREATE OR REPLACE TABLE {SCHEMA}.{tbl} AS SELECT * FROM df")
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_perm_principal ON {SCHEMA}.permissions_cache (principal)")
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_perm_table ON {SCHEMA}.permissions_cache (table_full_name)")
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_cols_table ON {SCHEMA}.columns_metadata (table_full_name)")
        con.close()
        os.replace(tmp_path, duckdb_path)
        print(f"  ✓ DuckDB written ({duckdb_path})")
    except Exception as e:
        print(f"  ✗ DuckDB export failed: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    setup_cache_tables()
    sync()
