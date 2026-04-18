import sys
from unittest.mock import MagicMock, patch

# Mock modules to allow safe import
sys.modules["databricks"] = MagicMock()
sys.modules["databricks.sdk"] = MagicMock()
sys.modules["databricks.sql"] = MagicMock()
sys.modules["dotenv"] = MagicMock()

from scripts import sync_metadata

@patch("scripts.sync_metadata.WorkspaceClient")
@patch("scripts.sync_metadata.get_sql_connection")
@patch("builtins.print")
def test_sync_schema_error(mock_print, mock_get_sql_connection, mock_workspace_client):
    # Setup mocks
    mock_w = MagicMock()
    mock_workspace_client.return_value = mock_w

    # Mock catalogs
    mock_catalog = MagicMock()
    mock_catalog.name = "test_catalog"
    mock_w.catalogs.list.return_value = [mock_catalog]

    # Mock schemas
    mock_schema1 = MagicMock()
    mock_schema1.name = "schema1"
    mock_schema2 = MagicMock()
    mock_schema2.name = "schema2"
    mock_w.schemas.list.return_value = [mock_schema1, mock_schema2]

    # Mock table list to raise exception for first schema and return normally for second
    def mock_tables_list(catalog_name, schema_name):
        if schema_name == "schema1":
            raise Exception("Test error")
        return []

    mock_w.tables.list.side_effect = mock_tables_list

    # Execute sync
    sync_metadata.sync()

    # Verify print calls
    mock_print.assert_any_call("  Error processing schema schema1: Test error")
    mock_print.assert_any_call("  Processing schema: schema2")
