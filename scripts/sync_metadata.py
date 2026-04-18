import os
import pandas as pd
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

def sync():
    print("🚀 Starting Unity Catalog metadata sync...")
    w = WorkspaceClient()
    
    # Initialize lists to hold our extracted data
    tables_data = []
    columns_data = []
    permissions_data = []

    # 1. Iterate through catalogs (skipping system/internal ones if needed)
    for catalog in w.catalogs.list():
        if catalog.name in ['system', '__databricks_internal']:
            continue
            
        print(f"Processing catalog: {catalog.name}")
        for schema in w.schemas.list(catalog_name=catalog.name):
            print(f"  Processing schema: {schema.name}")
            
            try:
                for table in w.tables.list(catalog_name=catalog.name, schema_name=schema.name):
                    full_name = f"{catalog.name}.{schema.name}.{table.name}"
                    
                    # Store table metadata
                    tables_data.append({
                        "full_name": full_name,
                        "catalog_name": catalog.name,
                        "schema_name": schema.name,
                        "table_name": table.name,
                        "table_type": str(table.table_type),
                        "comment": table.comment or "",
                    })
                    
                    # Store column metadata
                    for col in table.columns:
                        columns_data.append({
                            "table_full_name": full_name,
                            "column_name": col.name,
                            "data_type": col.type_text,
                            "comment": col.comment or ""
                        })
                    
                    # 2. Extract permission grants
                    # In a real-world scenario, you might want to handle errors if permissions can't be read
                    try:
                        grants = w.grants.get('TABLE', full_name)
                        if grants.privilege_assignments:
                            for assignment in grants.privilege_assignments:
                                for priv in assignment.privileges:
                                    permissions_data.append({
                                        "table_full_name": full_name,
                                        "principal": assignment.principal,
                                        "privilege": str(priv)
                                    })
                    except Exception as e:
                        print(f"    Could not fetch grants for {full_name}: {e}")
            except Exception as e:
                print(f"  Error processing schema {schema.name}: {e}")

    # 3. Load into Databricks SQL Warehouse
    print("📂 Loading data into SQL Warehouse...")
    
    # Convert to DataFrames for easier loading (or use direct SQL)
    # Note: For production, use MERGE INTO or TRUNCATE/INSERT for freshness
    with get_sql_connection() as conn:
        with conn.cursor() as cursor:
            # Simple Truncate and Reload for the scaffolding
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata")
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata")
            cursor.execute(f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache")
            
            # Batch inserts (In production, consider using COPY INTO or temporary views for speed)
            for t in tables_data:
                cursor.execute(f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata VALUES (%s, %s, %s, %s, %s, %s, current_timestamp())", 
                               (t['full_name'], t['catalog_name'], t['schema_name'], t['table_name'], t['table_type'], t['comment']))
            
            for c in columns_data:
                cursor.execute(f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata VALUES (%s, %s, %s, %s)", 
                               (c['table_full_name'], c['column_name'], c['data_type'], c['comment']))
                               
            for p in permissions_data:
                cursor.execute(f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache VALUES (%s, %s, %s)", 
                               (p['table_full_name'], p['principal'], p['privilege']))

    print("✅ Sync completed successfully.")

if __name__ == "__main__":
    setup_cache_tables()
    sync()
