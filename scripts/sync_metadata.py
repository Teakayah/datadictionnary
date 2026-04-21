import os
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
                    full_name STRING,
                    catalog_name STRING,
                    schema_name STRING,
                    table_name STRING,
                    table_type STRING,
                    comment STRING,
                    updated_at TIMESTAMP
                )
            """)
            
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

def fetch_lineage(w, full_name):
    """Returns 1-hop upstream/downstream lineage edges for *full_name*.

    Uses the Databricks REST lineage-tracking API directly because the SDK
    wrapper is not uniformly available across workspace tiers.  Silently
    returns an empty list if the feature is disabled or the table type is
    unsupported (e.g. external tables without Delta lineage enabled).
    """
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

    # 1. Iterate through catalogs (skipping system/internal ones if needed)
    table_full_names = []
    for catalog in w.catalogs.list():
        if catalog.name in ['system', '__databricks_internal']:
            continue

        print(f"Processing catalog: {catalog.name}")
        
        # Extract Catalog Tags
        if catalog.properties:
            for k, v in catalog.properties.items():
                tags_data.append({"object_type": "CATALOG", "object_full_name": catalog.name, "tag_key": k, "tag_value": str(v)})

        for schema in w.schemas.list(catalog_name=catalog.name):
            print(f"  Processing schema: {schema.name}")
            schema_full_name = f"{catalog.name}.{schema.name}"
            
            # Extract Schema Tags
            if schema.properties:
                for k, v in schema.properties.items():
                    tags_data.append({"object_type": "SCHEMA", "object_full_name": schema_full_name, "tag_key": k, "tag_value": str(v)})

            try:
                for table in w.tables.list(catalog_name=catalog.name, schema_name=schema.name):
                    full_name = f"{catalog.name}.{schema.name}.{table.name}"
                    table_full_names.append(full_name)

                    # Store table metadata
                    tables_data.append({
                        "full_name": full_name,
                        "catalog_name": catalog.name,
                        "schema_name": schema.name,
                        "table_name": table.name,
                        "table_type": str(table.table_type),
                        "comment": table.comment or "",
                    })
                    
                    # Extract Table Tags
                    if table.properties:
                        for k, v in table.properties.items():
                            tags_data.append({"object_type": "TABLE", "object_full_name": full_name, "tag_key": k, "tag_value": str(v)})

                    # Store column metadata
                    for col in table.columns:
                        columns_data.append({
                            "table_full_name": full_name,
                            "column_name": col.name,
                            "data_type": col.type_text,
                            "comment": col.comment or ""
                        })
            except Exception as e:
                print(f"  Error processing schema {schema.name}: {e}")

    # 2. Fetch permission grants and lineage concurrently
    print("🔐 Fetching permission grants...")

    def fetch_grants(full_name):
        try:
            return full_name, w.grants.get('TABLE', full_name)
        except Exception as e:
            print(f"    Could not fetch grants for {full_name}: {e}")
            return full_name, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for full_name, grants in executor.map(fetch_grants, table_full_names):
            if grants and grants.privilege_assignments:
                for assignment in grants.privilege_assignments:
                    for priv in assignment.privileges:
                        permissions_data.append({
                            "table_full_name": full_name,
                            "principal": assignment.principal,
                            "privilege": str(priv)
                        })

    print("🔗 Fetching lineage...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for entries in executor.map(lambda fn: fetch_lineage(w, fn), table_full_names):
            lineage_data.extend(entries)

    # 3. Load into Databricks SQL Warehouse
    print("📂 Loading data into SQL Warehouse...")
    with get_sql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata")
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata")
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache")
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.lineage_cache")
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.object_tags")

            if tables_data:
                cursor.executemany(
                    f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata VALUES (%(full_name)s, %(catalog_name)s, %(schema_name)s, %(table_name)s, %(table_type)s, %(comment)s, current_timestamp())",
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

    print("✅ Sync completed successfully.")

if __name__ == "__main__":
    setup_cache_tables()
    sync()
