from unittest.mock import patch, MagicMock

from src.audit import save_table_metadata

def test_save_table_metadata_duckdb_exception():
    """Verify that if DuckDB CHECKPOINT raises an Exception during metadata save, it is handled gracefully."""
    with patch("src.audit.is_power_user", return_value=True), \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit._get_write_connection"), \
         patch("src.audit._get_shared_duckdb_connection") as mock_get_shared, \
         patch("src.audit.enqueue_sync"), \
         patch("src.audit.log_audit_event"), \
         patch("src.audit.search_all_metadata"), \
         patch("src.audit.get_authorized_tables"), \
         patch("src.audit.st"):

        mock_shared_conn = MagicMock()
        mock_shared_conn.execute.side_effect = Exception("Mock duckdb error")
        mock_get_shared.return_value = mock_shared_conn

        # This should not raise an exception
        save_table_metadata("catalog.schema.table", description="test description")

        mock_shared_conn.execute.assert_called_once_with("CHECKPOINT user_data")
