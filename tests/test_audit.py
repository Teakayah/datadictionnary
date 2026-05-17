import pytest
from unittest.mock import patch, MagicMock
from src.audit import approve_business_name, reject_business_name

from src.audit import save_table_metadata, _validate_business_name_inputs, save_business_name
from src.config import MAX_BUSINESS_NAME_LEN, MAX_DEFINITION_LEN

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

def test_validate_business_name_inputs_length():
    """Verify that business names and definitions exceeding length limits raise ValueError."""
    with patch("src.audit.is_power_user", return_value=True):

        long_business_name = "a" * (MAX_BUSINESS_NAME_LEN + 1)
        with pytest.raises(ValueError, match=f"Business name must be {MAX_BUSINESS_NAME_LEN} characters or fewer"):
            _validate_business_name_inputs(long_business_name, "")

        long_definition = "b" * (MAX_DEFINITION_LEN + 1)
        with pytest.raises(ValueError, match=f"Definition must be {MAX_DEFINITION_LEN} characters or fewer"):
            _validate_business_name_inputs("Valid Name", long_definition)

def test_save_business_name_duckdb_exception():
    """Verify that if DuckDB CHECKPOINT raises an Exception during save_business_name, it is handled gracefully."""
    with patch("src.audit.is_power_user", return_value=True), \
         patch("src.audit._get_old_business_name", return_value="Old Name"), \
         patch("src.audit.get_business_name_override_storage"), \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit._get_shared_duckdb_connection") as mock_get_shared, \
         patch("src.audit.enqueue_column_sync"), \
         patch("src.audit.log_audit_event"), \
         patch("src.audit.search_all_metadata"), \
         patch("src.audit.st"):

        mock_shared_conn = MagicMock()
        mock_shared_conn.execute.side_effect = Exception("Mock duckdb error")
        mock_get_shared.return_value = mock_shared_conn

        # This should not raise an exception
        save_business_name("catalog.schema.table", "col1", "New Name", "New Def")

        mock_shared_conn.execute.assert_called_once_with("CHECKPOINT user_data")


def test_save_table_metadata_permission_error():
    """Verify that save_table_metadata raises PermissionError for non-power users."""
    with patch("src.audit.is_power_user", return_value=False):
        with pytest.raises(PermissionError, match="Only power users can update table metadata."):
            save_table_metadata("catalog.schema.table", description="test")

def test_save_table_metadata_steward_email_only():
    """Verify that save_table_metadata writes to table_metadata_overrides and enqueues for steward."""
    with patch("src.audit.is_power_user", return_value=True), \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit._get_write_connection") as mock_get_write, \
         patch("src.audit._get_shared_duckdb_connection"), \
         patch("src.audit.enqueue_sync") as mock_enqueue, \
         patch("src.audit.log_audit_event") as mock_log, \
         patch("src.audit.search_all_metadata"), \
         patch("src.audit.get_authorized_tables"), \
         patch("src.audit.st"):

        mock_cursor = MagicMock()
        mock_get_write.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        save_table_metadata("catalog.schema.table", steward_email="steward@example.com")

        # Verify execute_write was called once (single upsert into table_metadata_overrides)
        assert mock_cursor.execute_write.call_count == 1
        call_args = mock_cursor.execute_write.call_args[0]
        assert "table_metadata_overrides" in call_args[0]
        assert call_args[1]["fn"] == "catalog.schema.table"
        assert call_args[1]["stew"] == "steward@example.com"

        # Verify enqueue_sync and log_audit_event were called for STEWARD
        mock_enqueue.assert_called_once()
        assert mock_enqueue.call_args[0][0] == "STEWARD"
        assert mock_enqueue.call_args[0][2] == {"steward_email": "steward@example.com"}

        mock_log.assert_called_once()
        assert mock_log.call_args[0][0] == "table_steward_change"

def test_get_table_steward_demo_mode():
    """Verify get_table_steward returns demo steward in demo mode."""
    with patch("src.audit.is_demo_mode", return_value=True):
        from src.audit import get_table_steward
        assert get_table_steward("catalog.schema.table") == "steward@example.com"

def test_get_table_steward_empty_result():
    """Verify get_table_steward returns empty string if no result is found."""
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_get_conn:

        mock_cursor = MagicMock()
        mock_get_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall_as_pandas.return_value = MagicMock(empty=True)

        from src.audit import get_table_steward
        assert get_table_steward("catalog.schema.table") == ""

def test_get_table_steward_with_result():
    """Verify get_table_steward returns the steward email from the DB."""
    import pandas as pd
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_get_conn:

        mock_cursor = MagicMock()
        mock_get_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame([{"steward_email": "real@example.com"}])

        from src.audit import get_table_steward
        assert get_table_steward("catalog.schema.table") == "real@example.com"

def test_get_table_steward_exception():
    """Verify get_table_steward handles DB exceptions gracefully and returns empty string."""
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_get_conn, \
         patch("src.audit.logging.warning") as mock_warning:

        mock_get_conn.side_effect = Exception("DB error")

        from src.audit import get_table_steward
        assert get_table_steward("catalog.schema.table") == ""
        mock_warning.assert_called_once()

def test_log_audit_event_demo_mode():
    """Verify log_audit_event in demo mode appends to storage but does not enqueue sync."""
    with patch("src.audit.st") as mock_st, \
         patch("src.audit.uuid.uuid4", return_value="1234-uuid"), \
         patch("src.audit.get_audit_storage") as mock_get_storage, \
         patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.enqueue_sync") as mock_enqueue:

        mock_st.session_state.get.return_value = "user@example.com"
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        from src.audit import log_audit_event
        log_audit_event("TYPE", "OBJ_TYPE", "OBJ_NAME", "OLD", "NEW")

        # Verify event appended to storage
        mock_storage.append.assert_called_once_with({
            "event_id": "1234-uuid",
            "event_type": "TYPE",
            "object_type": "OBJ_TYPE",
            "object_name": "OBJ_NAME",
            "actor_email": "user@example.com",
            "old_value": "OLD",
            "new_value": "NEW"
        })

        # Verify sync not enqueued in demo mode
        mock_enqueue.assert_not_called()

def test_log_audit_event_production_mode():
    """Verify log_audit_event in production mode appends to storage and enqueues sync."""
    with patch("src.audit.st") as mock_st, \
         patch("src.audit.uuid.uuid4", return_value="1234-uuid"), \
         patch("src.audit.get_audit_storage") as mock_get_storage, \
         patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.enqueue_sync") as mock_enqueue:

        mock_st.session_state.get.return_value = "user@example.com"
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        from src.audit import log_audit_event
        log_audit_event("TYPE", "OBJ_TYPE", "OBJ_NAME", "OLD", "NEW")

        expected_event = {
            "event_id": "1234-uuid",
            "event_type": "TYPE",
            "object_type": "OBJ_TYPE",
            "object_name": "OBJ_NAME",
            "actor_email": "user@example.com",
            "old_value": "OLD",
            "new_value": "NEW"
        }

        # Verify sync enqueued in production mode
        mock_enqueue.assert_called_once_with("AUDIT", None, expected_event, "user@example.com")

def test_validate_business_name_inputs_permission_error():
    """Verify that save_business_name raises PermissionError for non-power users."""
    with patch("src.audit.is_power_user", return_value=False):
        with pytest.raises(PermissionError, match="Only power users can save business name overrides."):
            _validate_business_name_inputs("name", "desc")

def test_get_old_business_name():
    """Verify _get_old_business_name retrieves the correct business name."""
    with patch("src.audit.get_business_name_override_storage") as mock_get_storage:
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        # Test when override exists
        mock_storage.get_for_table.return_value = {
            "col1": {"business_name": "Old Name"}
        }
        from src.audit import _get_old_business_name
        assert _get_old_business_name("catalog.schema.table", "col1") == "Old Name"

        # Test when column not in overrides
        assert _get_old_business_name("catalog.schema.table", "col2") == ""

        # Test when overrides is empty
        mock_storage.get_for_table.return_value = {}
        assert _get_old_business_name("catalog.schema.table", "col1") == ""

def test_approve_business_name_permission_error():
    with patch("src.audit.is_admin", return_value=False):
        with pytest.raises(PermissionError, match="Only admins can approve metadata changes."):
            approve_business_name("catalog.schema.table", "col1")

def test_reject_business_name_permission_error():
    with patch("src.audit.is_admin", return_value=False):
        with pytest.raises(PermissionError, match="Only admins can reject metadata changes."):
            reject_business_name("catalog.schema.table", "col1")

def test_approve_business_name_success():
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.get_business_name_override_storage") as mock_get_storage, \
         patch("src.audit.st") as mock_st, \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit.enqueue_column_sync") as mock_enqueue, \
         patch("src.audit._get_shared_duckdb_connection") as mock_get_shared, \
         patch("src.audit.search_all_metadata") as mock_search_clear:

        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        mock_storage.list_pending.return_value = [
            {"table_full_name": "catalog.schema.table", "column_name": "col1", "definition": "def1"}
        ]

        mock_st.session_state.get.return_value = "admin_user"

        mock_shared_conn = MagicMock()
        mock_get_shared.return_value = mock_shared_conn

        approve_business_name("catalog.schema.table", "col1")

        mock_storage.approve.assert_called_once_with("catalog.schema.table", "col1")
        mock_enqueue.assert_called_once_with("catalog.schema.table", "col1", "def1", "admin_user")
        mock_shared_conn.execute.assert_called_once_with("CHECKPOINT user_data")
        mock_search_clear.clear.assert_called_once()

def test_approve_business_name_not_found():
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.get_business_name_override_storage") as mock_get_storage:

        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        mock_storage.list_pending.return_value = []

        approve_business_name("catalog.schema.table", "col1")

        mock_storage.approve.assert_not_called()

def test_reject_business_name_success():
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.get_business_name_override_storage") as mock_get_storage, \
         patch("src.audit.search_all_metadata") as mock_search_clear:

        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        reject_business_name("catalog.schema.table", "col1")

        mock_storage.reject.assert_called_once_with("catalog.schema.table", "col1")
        mock_search_clear.clear.assert_called_once()

def test_get_table_steward_local_override_found():
    import pandas as pd
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_get_conn, \
         patch("src.audit._duckdb_available", return_value=True):

        mock_cursor = MagicMock()
        mock_get_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        def mock_fetchall():
            call_args = mock_cursor.execute.call_args[0][0]
            if "table_metadata_overrides" in call_args:
                return pd.DataFrame([{"steward_email": "local@example.com"}])
            return pd.DataFrame()

        mock_cursor.fetchall_as_pandas.side_effect = mock_fetchall

        from src.audit import get_table_steward
        assert get_table_steward("catalog.schema.table") == "local@example.com"
def test_approve_business_name_exception():
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.get_business_name_override_storage") as mock_get_storage, \
         patch("src.audit.st") as mock_st, \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit.enqueue_column_sync") as mock_enqueue, \
         patch("src.audit._get_shared_duckdb_connection") as mock_get_shared, \
         patch("src.audit.search_all_metadata") as mock_search_clear:

        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        mock_storage.list_pending.return_value = [
            {"table_full_name": "catalog.schema.table", "column_name": "col1", "definition": "def1"}
        ]

        mock_st.session_state.get.return_value = "admin_user"

        mock_shared_conn = MagicMock()
        mock_shared_conn.execute.side_effect = Exception("Mock duckdb error")
        mock_get_shared.return_value = mock_shared_conn

        # This should not raise an exception
        approve_business_name("catalog.schema.table", "col1")

        mock_shared_conn.execute.assert_called_once_with("CHECKPOINT user_data")

def test_save_business_name_admin():
    with patch("src.audit.is_power_user", return_value=True), \
         patch("src.audit.is_admin", return_value=True), \
         patch("src.audit._get_old_business_name", return_value="Old Name"), \
         patch("src.audit.get_business_name_override_storage"), \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit._get_shared_duckdb_connection") as mock_get_shared, \
         patch("src.audit.enqueue_column_sync") as mock_enqueue, \
         patch("src.audit.log_audit_event"), \
         patch("src.audit.search_all_metadata"), \
         patch("src.audit.st") as mock_st:

        mock_st.session_state.get.return_value = "admin_user"

        mock_shared_conn = MagicMock()
        mock_get_shared.return_value = mock_shared_conn

        from src.audit import save_business_name
        save_business_name("catalog.schema.table", "col1", "New Name", "New Def")

        mock_enqueue.assert_called_once_with("catalog.schema.table", "col1", "New Def", "admin_user")
