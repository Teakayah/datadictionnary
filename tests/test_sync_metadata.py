import sys
from unittest.mock import MagicMock, patch
import os
import pytest

def mock_dependencies():
    sys.modules["databricks"] = MagicMock()
    sys.modules["databricks.sdk"] = MagicMock()
    sys.modules["databricks.sql"] = MagicMock()
    sys.modules["dotenv"] = MagicMock()

@pytest.fixture(autouse=True)
def setup_mocks():
    mock_dependencies()
    yield

def test_get_sql_connection():
    env_vars = {
        "DATABRICKS_HOST": "test-host",
        "DATABRICKS_HTTP_PATH": "test-path",
        "DATABRICKS_TOKEN": "test-token"
    }

    with patch.dict(os.environ, env_vars):
        from scripts.sync_metadata import get_sql_connection, sql

        # Call the function
        conn = get_sql_connection()

        # Verify sql.connect was called with correct arguments
        sql.connect.assert_called_once_with(
            server_hostname="test-host",
            http_path="test-path",
            access_token="test-token"
        )

        # Verify it returns what sql.connect returns
        assert conn == sql.connect.return_value

@patch("scripts.sync_metadata.get_sql_connection")
def test_setup_cache_tables(mock_get_sql_connection):
    # Mock connection, cursor, and context managers
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_get_sql_connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    from scripts.sync_metadata import setup_cache_tables, CATALOG_CACHE, SCHEMA_CACHE
    setup_cache_tables()

    # Check that execute was called multiple times
    assert mock_cursor.execute.call_count == 5

    calls = mock_cursor.execute.call_args_list

    # 1. CREATE CATALOG
    assert f"CREATE CATALOG IF NOT EXISTS {CATALOG_CACHE}" in calls[0][0][0]

    # 2. CREATE SCHEMA
    assert f"CREATE SCHEMA IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}" in calls[1][0][0]

    # 3. CREATE TABLE tables_metadata
    assert f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata" in calls[2][0][0]

    # 4. CREATE TABLE columns_metadata
    assert f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata" in calls[3][0][0]

    # 5. CREATE TABLE permissions_cache
    assert f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache" in calls[4][0][0]

@patch("scripts.sync_metadata.WorkspaceClient")
@patch("scripts.sync_metadata.get_sql_connection")
def test_sync(mock_get_sql_connection, mock_workspace_client):
    # Setup sql connection mock
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_sql_connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Setup workspace client mock
    mock_w = MagicMock()
    mock_workspace_client.return_value = mock_w

    # Mock catalogs
    mock_catalog_sys = MagicMock()
    mock_catalog_sys.name = 'system'
    mock_catalog_reg = MagicMock()
    mock_catalog_reg.name = 'my_catalog'
    mock_w.catalogs.list.return_value = [mock_catalog_sys, mock_catalog_reg]

    # Mock schemas
    mock_schema = MagicMock()
    mock_schema.name = 'my_schema'
    mock_w.schemas.list.return_value = [mock_schema]

    # Mock tables
    mock_table = MagicMock()
    mock_table.name = 'my_table'
    mock_table.table_type = 'MANAGED'
    mock_table.comment = 'Table comment'

    # Mock columns
    mock_col = MagicMock()
    mock_col.name = 'my_col'
    mock_col.type_text = 'INT'
    mock_col.comment = 'Col comment'
    mock_table.columns = [mock_col]

    mock_w.tables.list.return_value = [mock_table]

    # Mock grants
    mock_grant = MagicMock()
    mock_assignment = MagicMock()
    mock_assignment.principal = 'user@test.com'
    mock_assignment.privileges = ['SELECT', 'MODIFY']
    mock_grant.privilege_assignments = [mock_assignment]
    mock_w.grants.get.return_value = mock_grant

    from scripts.sync_metadata import sync, CATALOG_CACHE, SCHEMA_CACHE
    sync()

    # Verification
    mock_w.catalogs.list.assert_called_once()
    mock_w.schemas.list.assert_called_once_with(catalog_name='my_catalog')
    mock_w.tables.list.assert_called_once_with(catalog_name='my_catalog', schema_name='my_schema')
    mock_w.grants.get.assert_called_once_with('TABLE', 'my_catalog.my_schema.my_table')

    # Check that cursor execute was called for Truncates and Inserts
    calls = mock_cursor.execute.call_args_list

    # Expecting 3 truncates + 1 table insert + 1 col insert + 2 permission inserts = 7 calls
    assert len(calls) == 7

    # Truncates
    assert f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata" in calls[0][0][0]
    assert f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata" in calls[1][0][0]
    assert f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache" in calls[2][0][0]

    # Table insert
    assert f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata" in calls[3][0][0]
    assert calls[3][0][1] == ('my_catalog.my_schema.my_table', 'my_catalog', 'my_schema', 'my_table', 'MANAGED', 'Table comment')

    # Column insert
    assert f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata" in calls[4][0][0]
    assert calls[4][0][1] == ('my_catalog.my_schema.my_table', 'my_col', 'INT', 'Col comment')

    # Permission inserts
    assert f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache" in calls[5][0][0]
    assert calls[5][0][1] == ('my_catalog.my_schema.my_table', 'user@test.com', 'SELECT')

    assert f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache" in calls[6][0][0]
    assert calls[6][0][1] == ('my_catalog.my_schema.my_table', 'user@test.com', 'MODIFY')
