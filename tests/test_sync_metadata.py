import sys
from unittest.mock import MagicMock, patch
import os
import pytest


@pytest.fixture(autouse=True)
def setup_mocks():
    mock_modules = {
        "databricks": MagicMock(),
        "databricks.sdk": MagicMock(),
        "databricks.sql": MagicMock(),
        "dotenv": MagicMock(),
    }
    with patch.dict("sys.modules", mock_modules):
        yield


def test_get_sql_connection():
    env_vars = {
        "DATABRICKS_HOST": "test-host",
        "DATABRICKS_HTTP_PATH": "test-path",
        "DATABRICKS_TOKEN": "test-token",
    }

    with patch.dict(os.environ, env_vars):
        from scripts.sync_metadata import get_sql_connection, sql

        conn = get_sql_connection()

        sql.connect.assert_called_once_with(
            server_hostname="test-host",
            http_path="test-path",
            access_token="test-token",
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

    assert mock_cursor.execute.call_count == 11

    calls = mock_cursor.execute.call_args_list
    assert f"CREATE CATALOG IF NOT EXISTS {CATALOG_CACHE}" in calls[0][0][0]
    assert (
        f"CREATE SCHEMA IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}" in calls[1][0][0]
    )
    assert (
        f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata"
        in calls[2][0][0]
    )
    assert (
        f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata"
        in calls[3][0][0]
    )
    assert (
        f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache"
        in calls[4][0][0]
    )
    assert (
        f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.lineage_cache"
        in calls[5][0][0]
    )
    assert (
        f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.object_tags"
        in calls[6][0][0]
    )
    assert (
        f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.comments"
        in calls[7][0][0]
    )
    assert "comment_id" in calls[7][0][0], "comments DDL must include comment_id"
    assert "steward_email" in calls[7][0][0], "comments DDL must include steward_email"
    assert (
        f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides"
        in calls[8][0][0]
    )
    assert "column_name" in calls[8][0][0], (
        "business_name_overrides DDL must include column_name"
    )
    assert "definition" in calls[8][0][0], (
        "business_name_overrides DDL must include definition"
    )
    assert (
        f"CREATE TABLE IF NOT EXISTS {CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log"
        in calls[9][0][0]
    )
    assert "event_type" in calls[9][0][0], "audit_log DDL must include event_type"
    assert "actor_email" in calls[9][0][0], "audit_log DDL must include actor_email"


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
    mock_catalog_sys.name = "system"
    mock_catalog_reg = MagicMock()
    mock_catalog_reg.name = "my_catalog"
    mock_w.catalogs.list.return_value = [mock_catalog_sys, mock_catalog_reg]

    mock_schema = MagicMock()
    mock_schema.name = "my_schema"
    mock_w.schemas.list.return_value = [mock_schema]

    mock_table = MagicMock()
    mock_table.name = "my_table"
    mock_table.table_type = "MANAGED"
    mock_table.comment = "Table comment"
    mock_table.properties = {
        "dq_score": "95",
        "last_run_status": "PASS",
        "freshness": "2 hours",
    }

    mock_col = MagicMock()
    mock_col.name = "my_col"
    mock_col.type_text = "INT"
    mock_col.comment = "Col comment"
    mock_table.columns = [mock_col]
    mock_w.tables.list.return_value = [mock_table]

    import pandas as pd

    grants_df = pd.DataFrame(
        {
            "table_full_name": [
                "my_catalog.my_schema.my_table",
                "my_catalog.my_schema.my_table",
            ],
            "principal": ["user@test.com", "user@test.com"],
            "privilege": ["SELECT", "MODIFY"],
        }
    )
    mock_cursor.fetchall_as_pandas.side_effect = [
        grants_df,      # 1. Grants query (bulk permissions fetch)
        pd.DataFrame(), # 2. DQ enrichment (enrich_dq_from_monitoring → Lakehouse Monitoring)
        pd.DataFrame(), # 3. Audit log fetch for DuckDB export
        pd.DataFrame(), # 4. push_business_name_overrides (no overrides → empty)
    ]

    # Mock ThreadPoolExecutor.map to return empty for lineage (since we aren't testing lineage specifically here)
    mock_executor = MagicMock()
    mock_executor_cls.return_value.__enter__.return_value = mock_executor
    mock_executor.map.return_value = []

    from scripts.sync_metadata import sync, CATALOG_CACHE, SCHEMA_CACHE

    # By default thread pool map just runs things, but since submit mock doesn't run the fetch_schema_metadata logic,
    # the mock_w.tables.list wouldn't be called. Let's patch ThreadPoolExecutor entirely just to run it synchronously
    # without mocking the futures

    def side_effect_submit(fn, *args, **kwargs):
        class FutureMock:
            def result(self):
                return fn(*args, **kwargs)

        return FutureMock()

    mock_executor.submit.side_effect = side_effect_submit

    def mock_as_completed(fs):
        for f in fs:
            yield f

    with patch("concurrent.futures.as_completed", side_effect=mock_as_completed):
        sync()

    mock_w.catalogs.list.assert_called_once()
    mock_w.schemas.list.assert_called_once_with(catalog_name="my_catalog")
    mock_w.tables.list.assert_called_once_with(
        catalog_name="my_catalog", schema_name="my_schema"
    )

    # [0]  SELECT from permissions bulk fetch
    # [1]  SELECT from enrich_dq_from_monitoring (Lakehouse Monitoring)
    # [2-7] 6 TRUNCATEs (tables, columns, permissions, lineage, object_tags, dq_cache)
    # [8]  SELECT audit_log for DuckDB export
    # [9]  SELECT from push_business_name_overrides (no overrides to push → returns empty)
    execute_calls = mock_cursor.execute.call_args_list
    assert len(execute_calls) == 10
    assert "system.information_schema.table_privileges" in execute_calls[0][0][0]
    assert (
        f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata"
        in execute_calls[2][0][0]
    )
    assert (
        f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata"
        in execute_calls[3][0][0]
    )
    assert (
        f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache"
        in execute_calls[4][0][0]
    )
    assert (
        f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.lineage_cache"
        in execute_calls[5][0][0]
    )
    assert (
        f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.object_tags"
        in execute_calls[6][0][0]
    )
    assert (
        f"TRUNCATE TABLE {CATALOG_CACHE}.{SCHEMA_CACHE}.data_quality_cache"
        in execute_calls[7][0][0]
    )
    assert "audit_log" in execute_calls[8][0][0]
    assert "business_name_overrides" in execute_calls[9][0][0]

    # 5 executemany calls: tables, columns, permissions, data_quality, object_tags
    # (object_tags has 1 data row from table tags; dq data comes from mock_table.properties)
    # lineage is empty because we mock the future result for it, so its executemany is skipped.
    executemany_calls = mock_cursor.executemany.call_args_list
    assert len(executemany_calls) == 5
    assert (
        f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata VALUES (%(full_name)s, %(catalog_name)s, %(schema_name)s, %(table_name)s, %(table_type)s, %(comment)s, current_timestamp(), %(steward_email)s)"
        in executemany_calls[0][0][0]
    )
    assert (
        f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata VALUES (%(table_full_name)s, %(column_name)s, %(data_type)s, %(comment)s)"
        in executemany_calls[1][0][0]
    )
    assert (
        f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache VALUES (%(table_full_name)s, %(principal)s, %(privilege)s)"
        in executemany_calls[2][0][0]
    )
    assert (
        f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.object_tags VALUES (%(object_type)s, %(object_full_name)s, %(tag_key)s, %(tag_value)s)"
        in executemany_calls[3][0][0]
    )
    assert (
        f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.data_quality_cache VALUES (%(table_full_name)s, %(dq_score)s, %(last_run_status)s, %(freshness)s)"
        in executemany_calls[4][0][0]
    )

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

    # Simulate an error when fetching grants by throwing on execute
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_sql_connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # We want it to fail on the very first query which is the grants query
    mock_cursor.execute.side_effect = Exception("Grants error")

    from scripts.sync_metadata import sync

    # We wrap in try except since the sync function catches the grant error but later queries like TRUNCATE will fail
    # because side_effect raises on every execute call.
    # Alternatively we can supply a list to side_effect to only fail on the first
    mock_cursor.execute.side_effect = [Exception("Grants error")] + [MagicMock()] * 10

    sync()

    mock_print.assert_any_call("    Could not fetch grants in bulk: Grants error")


def test_main_coverage(setup_mocks):
    # To test the main block reliably without brittle stdout checks,
    # we can mock `sys.argv` and run the script, checking that `WorkspaceClient`
    # from our globally mocked `databricks.sdk` in `sys.modules` was instantiated.
    import runpy

    # Reset call counts just in case
    sys.modules["databricks.sdk"].WorkspaceClient.reset_mock()

    # Run the module
    runpy.run_module("scripts.sync_metadata", run_name="__main__")

    # Verify the global mock was interacted with.
    # The script does `from databricks.sdk import WorkspaceClient`.
    # When `sys.modules["databricks.sdk"]` is a MagicMock, `WorkspaceClient` is an attribute on it.
    assert sys.modules["databricks.sdk"].WorkspaceClient.called


def test_fetch_lineage_success():
    from scripts.sync_metadata import fetch_lineage

    mock_w = MagicMock()

    mock_w.api_client.do.return_value = {
        "upstream_tables": [
            {"name": "up_table_1", "table_type": "MANAGED"},
            {"full_name": "up_table_2", "table_type": "EXTERNAL"},
        ],
        "downstream_tables": [
            {"name": "down_table_1", "table_type": "MANAGED"},
            {"full_name": "down_table_2"},
        ],
    }

    entries = fetch_lineage(mock_w, "my_catalog.my_schema.my_table")

    mock_w.api_client.do.assert_called_once_with(
        "GET",
        "/api/2.0/lineage-tracking/table-lineage",
        query={"table_name": "my_catalog.my_schema.my_table"},
    )

    assert len(entries) == 4
    assert entries[0] == {
        "table_full_name": "my_catalog.my_schema.my_table",
        "direction": "UPSTREAM",
        "entity_full_name": "up_table_1",
        "entity_type": "MANAGED",
    }
    assert entries[1] == {
        "table_full_name": "my_catalog.my_schema.my_table",
        "direction": "UPSTREAM",
        "entity_full_name": "up_table_2",
        "entity_type": "EXTERNAL",
    }
    assert entries[2] == {
        "table_full_name": "my_catalog.my_schema.my_table",
        "direction": "DOWNSTREAM",
        "entity_full_name": "down_table_1",
        "entity_type": "MANAGED",
    }
    assert entries[3] == {
        "table_full_name": "my_catalog.my_schema.my_table",
        "direction": "DOWNSTREAM",
        "entity_full_name": "down_table_2",
        "entity_type": "TABLE",
    }


@patch("builtins.print")
def test_fetch_lineage_exception(mock_print):
    from scripts.sync_metadata import fetch_lineage

    mock_w = MagicMock()

    mock_w.api_client.do.side_effect = Exception("Test exception")

    entries = fetch_lineage(mock_w, "my_catalog.my_schema.my_table")

    mock_w.api_client.do.assert_called_once_with(
        "GET",
        "/api/2.0/lineage-tracking/table-lineage",
        query={"table_name": "my_catalog.my_schema.my_table"},
    )

    assert len(entries) == 0
    mock_print.assert_called_once_with(
        "    Lineage unavailable for my_catalog.my_schema.my_table: Test exception"
    )


def test_fetch_lineage_missing_name():
    from scripts.sync_metadata import fetch_lineage

    mock_w = MagicMock()

    mock_w.api_client.do.return_value = {
        "upstream_tables": [
            {"table_type": "MANAGED"}  # Missing name and full_name
        ],
        "downstream_tables": [
            {"table_type": "EXTERNAL"}  # Missing name and full_name
        ],
    }

    entries = fetch_lineage(mock_w, "my_catalog.my_schema.my_table")

    mock_w.api_client.do.assert_called_once_with(
        "GET",
        "/api/2.0/lineage-tracking/table-lineage",
        query={"table_name": "my_catalog.my_schema.my_table"},
    )

    assert len(entries) == 0
