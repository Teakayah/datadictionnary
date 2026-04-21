import sys
from unittest.mock import MagicMock, patch, call
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

        conn = get_sql_connection()

        sql.connect.assert_called_once_with(
            server_hostname="test-host",
            http_path="test-path",
            access_token="test-token"
        )
        assert conn == sql.connect.return_value

@patch("scripts.sync_metadata.get_sql_connection")
def test_setup_cache_tables(mock_get_sql_connection):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_get_sql_connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    from scripts.sync_metadata import setup_cache_tables, CATALOG_CACHE, SCHEMA_CACHE
    setup_cache_tables()

    assert mock_cursor.execute.call_count == 5

    calls = mock_cursor.execute.call_args_list
    assert f"CREATE CATALOG IF NOT EXISTS {CATALOG_CACHE}" in calls[0][0][0]
    assert f"CREATE SCHEMA IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}" in calls[1][0][0]
    assert f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata" in calls[2][0][0]
    assert f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata" in calls[3][0][0]
    assert f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache" in calls[4][0][0]

@patch("scripts.sync_metadata.concurrent.futures.ThreadPoolExecutor")
@patch("scripts.sync_metadata.WorkspaceClient")
@patch("scripts.sync_metadata.get_sql_connection")
def test_sync(mock_get_sql_connection, mock_workspace_client, mock_executor_cls):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_sql_connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_w = MagicMock()
    mock_workspace_client.return_value = mock_w

    mock_catalog_sys = MagicMock()
    mock_catalog_sys.name = 'system'
    mock_catalog_reg = MagicMock()
    mock_catalog_reg.name = 'my_catalog'
    mock_w.catalogs.list.return_value = [mock_catalog_sys, mock_catalog_reg]

    mock_schema = MagicMock()
    mock_schema.name = 'my_schema'
    mock_w.schemas.list.return_value = [mock_schema]

    mock_table = MagicMock()
    mock_table.name = 'my_table'
    mock_table.table_type = 'MANAGED'
    mock_table.comment = 'Table comment'

    mock_col = MagicMock()
    mock_col.name = 'my_col'
    mock_col.type_text = 'INT'
    mock_col.comment = 'Col comment'
    mock_table.columns = [mock_col]
    mock_w.tables.list.return_value = [mock_table]

    # Simulate concurrent grant fetching returning one grant
    mock_grant = MagicMock()
    mock_assignment = MagicMock()
    mock_assignment.principal = 'user@test.com'
    mock_assignment.privileges = ['SELECT', 'MODIFY']
    mock_grant.privilege_assignments = [mock_assignment]

    # Mock ThreadPoolExecutor.map to return (full_name, grants) pairs synchronously
    full_name = 'my_catalog.my_schema.my_table'
    mock_executor = MagicMock()
    mock_executor_cls.return_value.__enter__.return_value = mock_executor
    mock_executor.map.return_value = [(full_name, mock_grant)]

    from scripts.sync_metadata import sync, CATALOG_CACHE, SCHEMA_CACHE
    sync()

    mock_w.catalogs.list.assert_called_once()
    mock_w.schemas.list.assert_called_once_with(catalog_name='my_catalog')
    mock_w.tables.list.assert_called_once_with(catalog_name='my_catalog', schema_name='my_schema')

    # 3 truncates via execute
    execute_calls = mock_cursor.execute.call_args_list
    assert len(execute_calls) == 3
    assert f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata" in execute_calls[0][0][0]
    assert f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata" in execute_calls[1][0][0]
    assert f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache" in execute_calls[2][0][0]

    # 3 executemany calls (tables, columns, permissions)
    executemany_calls = mock_cursor.executemany.call_args_list
    assert len(executemany_calls) == 3
    assert f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata VALUES (%(full_name)s, %(catalog_name)s, %(schema_name)s, %(table_name)s, %(table_type)s, %(comment)s, current_timestamp())" in executemany_calls[0][0][0]
    assert f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata VALUES (%(table_full_name)s, %(column_name)s, %(data_type)s, %(comment)s)" in executemany_calls[1][0][0]
    assert f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache VALUES (%(table_full_name)s, %(principal)s, %(privilege)s)" in executemany_calls[2][0][0]

@patch("scripts.sync_metadata.WorkspaceClient")
@patch("scripts.sync_metadata.get_sql_connection")
@patch("builtins.print")
def test_sync_schema_error(mock_print, mock_get_sql_connection, mock_workspace_client):
    mock_w = MagicMock()
    mock_workspace_client.return_value = mock_w

    mock_catalog = MagicMock()
    mock_catalog.name = "test_catalog"
    mock_w.catalogs.list.return_value = [mock_catalog]

    mock_schema1 = MagicMock()
    mock_schema1.name = "schema1"
    mock_schema2 = MagicMock()
    mock_schema2.name = "schema2"
    mock_w.schemas.list.return_value = [mock_schema1, mock_schema2]

    def mock_tables_list(catalog_name, schema_name):
        if schema_name == "schema1":
            raise Exception("Test error")
        return []

    mock_w.tables.list.side_effect = mock_tables_list

    # ThreadPoolExecutor with no tables to process
    from scripts.sync_metadata import sync
    sync()

    mock_print.assert_any_call("  Error processing schema schema1: Test error")
    mock_print.assert_any_call("  Processing schema: schema2")

@patch("scripts.sync_metadata.WorkspaceClient")
@patch("scripts.sync_metadata.get_sql_connection")
@patch("builtins.print")
def test_sync_grants_error(mock_print, mock_get_sql_connection, mock_workspace_client):
    mock_w = MagicMock()
    mock_workspace_client.return_value = mock_w

    mock_catalog = MagicMock()
    mock_catalog.name = "test_catalog"
    mock_w.catalogs.list.return_value = [mock_catalog]

    mock_schema = MagicMock()
    mock_schema.name = "test_schema"
    mock_w.schemas.list.return_value = [mock_schema]

    mock_table = MagicMock()
    mock_table.name = "test_table"
    mock_table.table_type = "MANAGED"
    mock_table.comment = "Table comment"
    mock_table.columns = []
    mock_w.tables.list.return_value = [mock_table]

    # Simulate an error when fetching grants by making side_effect an exception class directly
    mock_w.grants.get.side_effect = Exception("Grants error")

    from scripts.sync_metadata import sync
    sync()

    mock_print.assert_any_call("    Could not fetch grants for test_catalog.test_schema.test_table: Grants error")
