from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.audit import (
    _validate_business_name_inputs,
    save_business_name,
    save_table_metadata,
)
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
         patch("src.audit._upsert_column_override"), \
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
         patch("src.audit._append_audit_event") as mock_append, \
         patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.enqueue_sync") as mock_enqueue:

        mock_st.session_state.get.return_value = "user@example.com"

        from src.audit import log_audit_event
        log_audit_event("TYPE", "OBJ_TYPE", "OBJ_NAME", "OLD", "NEW")

        # Verify event appended to storage
        mock_append.assert_called_once_with({
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
         patch("src.audit._append_audit_event"), \
         patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.enqueue_sync") as mock_enqueue:

        mock_st.session_state.get.return_value = "user@example.com"

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
    with patch("src.audit.get_column_overrides") as mock_overrides:
        # Test when override exists
        mock_overrides.return_value = {
            "col1": {"business_name": "Old Name"}
        }
        from src.audit import _get_old_business_name
        assert _get_old_business_name("catalog.schema.table", "col1") == "Old Name"

        # Test when column not in overrides
        assert _get_old_business_name("catalog.schema.table", "col2") == ""

        # Test when overrides is empty
        mock_overrides.return_value = {}
        assert _get_old_business_name("catalog.schema.table", "col1") == ""

def test_save_business_name_admin():
    """Verify save_business_name enqueues sync for admins."""
    from src.audit import save_business_name
    with patch("src.audit.is_power_user", return_value=True), \
         patch("src.audit.is_admin", return_value=True), \
         patch("src.audit._get_old_business_name", return_value="Old Name"), \
         patch("src.audit._upsert_column_override"), \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit._get_shared_duckdb_connection"), \
         patch("src.audit.enqueue_column_sync") as mock_enqueue, \
         patch("src.audit.log_audit_event"), \
         patch("src.audit.search_all_metadata"), \
         patch("src.audit.st") as mock_st:

        mock_st.session_state.get.return_value = "admin@example.com"
        save_business_name("catalog.schema.table", "col1", "New Name", "New Def")

        mock_enqueue.assert_called_once_with(
            "catalog.schema.table", "col1", "New Def", "admin@example.com"
        )

def test_approve_business_name_success():
    """Verify approve_business_name approves and enqueues sync."""
    from src.audit import approve_business_name
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.list_pending_business_names") as mock_pending, \
         patch("src.audit._approve_column_override") as mock_approve, \
         patch("src.audit._reject_column_override"), \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit._get_shared_duckdb_connection") as mock_get_shared, \
         patch("src.audit.enqueue_column_sync") as mock_enqueue, \
         patch("src.audit.search_all_metadata") as mock_search_all, \
         patch("src.audit.st") as mock_st:

        mock_pending.return_value = [
            {
                "table_full_name": "catalog.schema.table",
                "column_name": "col1",
                "definition": "Pending Def"
            }
        ]
        mock_st.session_state.get.return_value = "admin@example.com"
        mock_shared_conn = MagicMock()
        mock_get_shared.return_value = mock_shared_conn

        approve_business_name("catalog.schema.table", "col1")

        mock_approve.assert_called_once_with("catalog.schema.table", "col1")
        mock_enqueue.assert_called_once_with(
            "catalog.schema.table", "col1", "Pending Def", "admin@example.com"
        )
        mock_shared_conn.execute.assert_called_once_with("CHECKPOINT user_data")
        mock_search_all.clear.assert_called_once()

def test_approve_business_name_missing_item():
    """Verify approve_business_name does nothing if item not found."""
    from src.audit import approve_business_name
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.list_pending_business_names") as mock_pending, \
         patch("src.audit._approve_column_override") as mock_approve, \
         patch("src.audit._reject_column_override"), \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit._get_shared_duckdb_connection"), \
         patch("src.audit.enqueue_column_sync") as mock_enqueue, \
         patch("src.audit.search_all_metadata") as mock_search_all, \
         patch("src.audit.st"):

        mock_pending.return_value = []

        approve_business_name("catalog.schema.table", "col1")

        mock_approve.assert_not_called()
        mock_enqueue.assert_not_called()
        mock_search_all.clear.assert_not_called()

def test_approve_business_name_permission_error():
    """Verify approve_business_name raises PermissionError for non-admins."""
    from src.audit import approve_business_name
    with patch("src.audit.is_admin", return_value=False):
        with pytest.raises(PermissionError, match="Only admins can approve metadata changes."):
            approve_business_name("catalog.schema.table", "col1")

def test_approve_business_name_db_exception():
    """Verify approve_business_name gracefully handles DuckDB CHECKPOINT exceptions."""
    from src.audit import approve_business_name
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.list_pending_business_names") as mock_pending, \
         patch("src.audit._approve_column_override"), \
         patch("src.audit._reject_column_override"), \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit._get_shared_duckdb_connection") as mock_get_shared, \
         patch("src.audit.enqueue_column_sync"), \
         patch("src.audit.search_all_metadata"), \
         patch("src.audit.st"):

        mock_pending.return_value = [
            {
                "table_full_name": "catalog.schema.table",
                "column_name": "col1",
                "definition": "Pending Def"
            }
        ]
        mock_shared_conn = MagicMock()
        mock_shared_conn.execute.side_effect = Exception("Mock duckdb error")
        mock_get_shared.return_value = mock_shared_conn

        # Should not raise
        approve_business_name("catalog.schema.table", "col1")

def test_reject_business_name_success():
    """Verify reject_business_name calls reject and clears cache."""
    from src.audit import reject_business_name
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.list_pending_business_names"), \
         patch("src.audit._approve_column_override"), \
         patch("src.audit._reject_column_override") as mock_reject, \
         patch("src.audit.search_all_metadata") as mock_search_all:

        reject_business_name("catalog.schema.table", "col1")

        mock_reject.assert_called_once_with("catalog.schema.table", "col1")
        mock_search_all.clear.assert_called_once()

def test_reject_business_name_permission_error():
    """Verify reject_business_name raises PermissionError for non-admins."""
    from src.audit import reject_business_name
    with patch("src.audit.is_admin", return_value=False):
        with pytest.raises(PermissionError, match="Only admins can reject metadata changes."):
            reject_business_name("catalog.schema.table", "col1")

def test_get_table_steward_local_override():
    """Verify get_table_steward prefers local overrides over catalog."""
    from src.audit import get_table_steward
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_get_conn, \
         patch("src.audit._duckdb_available", return_value=True):

        mock_cursor = MagicMock()
        mock_get_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        # First call (local overrides) returns a result
        mock_cursor.fetchall_as_pandas.side_effect = [
            pd.DataFrame([{"steward_email": "local@example.com"}]),
            pd.DataFrame()  # Should not be reached
        ]

        assert get_table_steward("catalog.schema.table") == "local@example.com"
        # Ensure it didn't fall through to catalog
        assert mock_cursor.execute.call_count == 1
        assert "user_data.table_metadata_overrides" in mock_cursor.execute.call_args_list[0][0][0]

def test__append_audit_event_demo_mode():
    from src.audit import _DEMO_AUDIT_KEY, _append_audit_event
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st, \
         patch("src.audit.pd.Timestamp.now", return_value="now"):
        mock_st.session_state = {}
        _append_audit_event({"event_id": "123"})
        mock_list = mock_st.session_state[_DEMO_AUDIT_KEY]
        assert len(mock_list) == 1
        assert mock_list[0]["event_id"] == "123"
        assert mock_list[0]["created_at"] == "now"

def test__append_audit_event_production():
    from src.audit import _append_audit_event
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit._get_write_connection") as mock_get_write:
        mock_cursor = MagicMock()
        mock_get_write.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        _append_audit_event({"event_id": "123"})
        mock_cursor.execute_write.assert_called_once()
        assert mock_cursor.execute_write.call_args[0][1] == {"event_id": "123"}

def test__append_audit_event_exception():
    from src.audit import _append_audit_event
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit._get_write_connection", side_effect=Exception("DB err")), \
         patch("src.audit.log") as mock_log:
        _append_audit_event({"event_id": "123"})
        mock_log.warning.assert_called_once()
        assert "Audit logging failed" in mock_log.warning.call_args[0][0]

def test__upsert_column_override_demo_mode_pending():
    from src.audit import (
        _DEMO_BN_KEY,
        _DEMO_BN_PENDING_KEY,
        ColumnOverride,
        _upsert_column_override,
    )
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:
        mock_st.session_state = {}
        override = ColumnOverride(
            table_full_name="catalog.schema.table",
            column_name="col1",
            business_name="Name1",
            definition="Def1",
            edited_by="user1",
            status="pending_approval"
        )

        _upsert_column_override(override)

        mock_table_store = mock_st.session_state[_DEMO_BN_KEY]["catalog.schema.table"]
        mock_pending_store = mock_st.session_state[_DEMO_BN_PENDING_KEY]

        assert "col1" in mock_table_store
        assert mock_table_store["col1"]["business_name"] == "Name1"
        assert ("catalog.schema.table", "col1") in mock_pending_store

def test__upsert_column_override_demo_mode_published():
    from src.audit import (
        _DEMO_BN_KEY,
        _DEMO_BN_PENDING_KEY,
        ColumnOverride,
        _upsert_column_override,
    )
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:
        mock_st.session_state = {
            _DEMO_BN_PENDING_KEY: {("catalog.schema.table", "col1"): "pending_info"}
        }

        override = ColumnOverride(
            table_full_name="catalog.schema.table",
            column_name="col1",
            business_name="Name1",
            definition="Def1",
            edited_by="user1",
            status="published"
        )

        _upsert_column_override(override)

        mock_table_store = mock_st.session_state[_DEMO_BN_KEY]["catalog.schema.table"]
        mock_pending_store = mock_st.session_state[_DEMO_BN_PENDING_KEY]

        assert "col1" in mock_table_store
        assert mock_table_store["col1"]["status"] == "published"
        assert ("catalog.schema.table", "col1") not in mock_pending_store

def test__upsert_column_override_production():
    from src.audit import ColumnOverride, _upsert_column_override
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit._get_write_connection") as mock_get_write:
        mock_cursor = MagicMock()
        mock_get_write.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        override = ColumnOverride(
            table_full_name="catalog.schema.table",
            column_name="col1",
            business_name="Name1",
            definition="Def1",
            edited_by="user1",
            status="published"
        )
        _upsert_column_override(override)
        mock_cursor.execute_write.assert_called_once()
        args = mock_cursor.execute_write.call_args[0]
        assert "INSERT INTO user_data.business_name_overrides" in args[0]
        assert args[1]["table_full_name"] == "catalog.schema.table"
        assert args[1]["column_name"] == "col1"

@patch("src.audit.run_query")
def test_get_table_columns(mock_run_query):
    from src.audit import get_table_columns
    mock_run_query.return_value = pd.DataFrame([{"column_name": "col1"}])
    res = get_table_columns("catalog.schema.table")
    assert not res.empty
    mock_run_query.assert_called_once()
    args, kwargs = mock_run_query.call_args
    assert args[1]["table_full_name"] == "catalog.schema.table"

def test_get_column_overrides_demo_mode():
    from src.audit import get_column_overrides
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:
        mock_st.session_state.get.return_value.get.return_value = {
            "col1": {"business_name": "Name1", "status": "published"},
            "col2": {"business_name": "Name2", "status": "pending"}
        }
        res = get_column_overrides("catalog.schema.table")
        assert "col1" in res
        assert "col2" not in res
        assert res["col1"]["business_name"] == "Name1"

def test_get_column_overrides_production():
    from src.audit import get_column_overrides
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_get_db:
        mock_cursor = MagicMock()
        mock_get_db.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame([
            {"column_name": "col1", "business_name": "Name1", "definition": "Def1", "edited_by": "user1", "edited_at": "time1"}
        ])
        res = get_column_overrides("catalog.schema.table")
        assert "col1" in res
        assert res["col1"]["business_name"] == "Name1"
        assert res["col1"]["definition"] == "Def1"

def test_get_column_overrides_exception():
    from src.audit import get_column_overrides
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection", side_effect=Exception("DB Error")), \
         patch("src.audit.log") as mock_log:
        res = get_column_overrides("catalog.schema.table")
        assert res == {}
        mock_log.warning.assert_called_once()

def test_list_pending_business_names_demo_mode():
    from src.audit import list_pending_business_names
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:
        mock_st.session_state.get.return_value.values.return_value = [{"col1": "pending"}]
        res = list_pending_business_names()
        assert res == [{"col1": "pending"}]

def test_list_pending_business_names_production():
    from src.audit import list_pending_business_names
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_get_db:
        mock_cursor = MagicMock()
        mock_get_db.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame([
            {"table_full_name": "catalog.schema.table", "column_name": "col1"}
        ])
        res = list_pending_business_names()
        assert len(res) == 1
        assert res[0]["column_name"] == "col1"

def test_list_pending_business_names_exception():
    from src.audit import list_pending_business_names
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection", side_effect=Exception("DB Error")), \
         patch("src.audit.log") as mock_log:
        res = list_pending_business_names()
        assert res == []
        mock_log.warning.assert_called_once()

def test__reject_column_override_demo_mode():
    from src.audit import _reject_column_override
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:
        mock_store = MagicMock()
        mock_pending_store = MagicMock()
        mock_st.session_state.get.side_effect = [mock_store, mock_pending_store]
        mock_table_store = MagicMock()
        mock_store.get.return_value = mock_table_store

        _reject_column_override("catalog.schema.table", "col1")
        mock_table_store.pop.assert_called_once_with("col1", None)
        mock_pending_store.pop.assert_called_once_with(("catalog.schema.table", "col1"), None)

def test__reject_column_override_production():
    from src.audit import _reject_column_override
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit._get_write_connection") as mock_get_write:
        mock_cursor = MagicMock()
        mock_get_write.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        _reject_column_override("catalog.schema.table", "col1")
        mock_cursor.execute_write.assert_called_once()

def test_list_pending_table_business_names_demo_mode():
    from src.audit import list_pending_table_business_names
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:
        mock_st.session_state.get.return_value.values.return_value = [{"table_full_name": "t1"}]
        res = list_pending_table_business_names()
        assert res == [{"table_full_name": "t1"}]

def test_list_pending_table_business_names_production():
    from src.audit import list_pending_table_business_names
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_get_db:
        mock_cursor = MagicMock()
        mock_get_db.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame([
            {"table_full_name": "t1"}
        ])
        res = list_pending_table_business_names()
        assert len(res) == 1
        assert res[0]["table_full_name"] == "t1"

def test_list_pending_table_business_names_exception():
    from src.audit import list_pending_table_business_names
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection", side_effect=Exception("DB Error")), \
         patch("src.audit.log") as mock_log:
        res = list_pending_table_business_names()
        assert res == []
        mock_log.warning.assert_called_once()

def test__upsert_table_business_name_override_production():
    from src.audit import (
        TableBusinessNameOverride,
        _upsert_table_business_name_override,
    )
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit._get_write_connection") as mock_get_write:
        mock_cursor = MagicMock()
        mock_get_write.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        override = TableBusinessNameOverride(
            table_full_name="catalog.schema.table",
            business_name_en="EN Name",
            business_name_fr="FR Name",
            business_definition_en="EN Def",
            business_definition_fr="FR Def",
            edited_by="user1",
            status="published"
        )

        _upsert_table_business_name_override(override)

        mock_cursor.execute_write.assert_called_once()
        args = mock_cursor.execute_write.call_args[0]
        assert "INSERT INTO user_data.table_business_name_overrides" in args[0]
        assert args[1]["fn"] == "catalog.schema.table"
        assert args[1]["name_en"] == "EN Name"
        assert args[1]["status"] == "published"

@patch("src.audit._duckdb_available", return_value=True)
@patch("src.audit._get_shared_duckdb_connection")
@patch("src.audit.enqueue_table_business_name_sync")
@patch("src.audit.log_audit_event")
@patch("src.audit.search_all_metadata")
@patch("src.audit.is_admin", return_value=True)
@patch("src.audit.is_power_user", return_value=True)
def test_save_table_business_name_duckdb_admin(mock_power, mock_admin, mock_search, mock_log, mock_enqueue, mock_get_conn, mock_duck_avail):
    from src.audit import save_table_business_name
    with patch("src.audit.st") as mock_st, \
         patch("src.audit.get_table_business_name_override", return_value={"business_name_en": "Old EN", "business_name_fr": "Old FR"}), \
         patch("src.audit._validate_table_business_name_inputs"), \
         patch("src.audit._upsert_table_business_name_override"):

        mock_st.session_state.get.return_value = "admin_user"

        save_table_business_name(
            "catalog.schema.table", "New EN", "New FR", "Def EN", "Def FR"
        )

        mock_get_conn.return_value.execute.assert_called_once_with("CHECKPOINT user_data")
        mock_enqueue.assert_called_once_with(
            "catalog.schema.table", "New EN", "New FR", "Def EN", "Def FR", "admin_user"
        )

def test__approve_column_override_demo_mode():
    from src.audit import _DEMO_BN_KEY, _approve_column_override
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:
        mock_table_store = {"col1": {"status": "pending"}}
        mock_store = {"catalog.schema.table": mock_table_store}
        mock_pending_store = {("catalog.schema.table", "col1"): "some_info"}

        mock_st.session_state.get.side_effect = lambda k, d={}: mock_store if k == _DEMO_BN_KEY else mock_pending_store

        _approve_column_override("catalog.schema.table", "col1")

        assert mock_table_store["col1"]["status"] == "published"
        assert ("catalog.schema.table", "col1") not in mock_pending_store

def test__approve_column_override_production():
    from src.audit import _approve_column_override
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit._get_write_connection") as mock_get_write:
        mock_cursor = MagicMock()
        mock_get_write.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        _approve_column_override("catalog.schema.table", "col1")

        mock_cursor.execute_write.assert_called_once()
        args = mock_cursor.execute_write.call_args[0]
        assert "UPDATE user_data.business_name_overrides SET status = 'published'" in args[0]
        assert args[1] == {"fn": "catalog.schema.table", "col": "col1"}

def test_get_table_business_name_override_demo_mode():
    from src.audit import get_table_business_name_override
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:
        mock_st.session_state.get.return_value.get.return_value = {
            "business_name_en": "Name EN",
            "business_name_fr": "Name FR",
            "business_definition_en": "Def EN",
            "business_definition_fr": "Def FR",
            "edited_by": "user1",
            "edited_at": "time1"
        }

        res = get_table_business_name_override("catalog.schema.table")
        assert res["business_name_en"] == "Name EN"
        assert res["business_name_fr"] == "Name FR"
        assert res["business_definition_en"] == "Def EN"
        assert res["business_definition_fr"] == "Def FR"
        assert res["edited_by"] == "user1"
        assert res["edited_at"] == "time1"

def test_get_table_business_name_override_production_success():
    from src.audit import get_table_business_name_override
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_get_db:
        mock_cursor = MagicMock()
        mock_get_db.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame([
            {
                "business_name_en": "Name EN DB",
                "business_name_fr": "Name FR DB",
                "business_definition_en": "Def EN DB",
                "business_definition_fr": "Def FR DB",
                "edited_by": "user DB",
                "edited_at": "time DB"
            }
        ])

        res = get_table_business_name_override("catalog.schema.table")

        assert res["business_name_en"] == "Name EN DB"
        assert res["business_name_fr"] == "Name FR DB"
        assert res["business_definition_en"] == "Def EN DB"
        assert res["business_definition_fr"] == "Def FR DB"
        assert res["edited_by"] == "user DB"
        assert res["edited_at"] == "time DB"

def test_get_table_business_name_override_production_empty():
    from src.audit import get_table_business_name_override
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_get_db:
        mock_cursor = MagicMock()
        mock_get_db.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame()

        res = get_table_business_name_override("catalog.schema.table")
        assert res == {}

def test_get_table_business_name_override_production_exception():
    from src.audit import get_table_business_name_override
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection", side_effect=Exception("DB Error")), \
         patch("src.audit.log") as mock_log:
        res = get_table_business_name_override("catalog.schema.table")
        assert res == {}
        mock_log.warning.assert_called_once()
        assert "Could not fetch table friendly name" in mock_log.warning.call_args[0][0]

def test__approve_table_business_name_override_demo_mode_found():
    from src.audit import (
        _DEMO_TBN_KEY,
        _approve_table_business_name_override,
    )
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:
        mock_tbn_store = {"catalog.schema.table": {"status": "pending", "name_en": "Table EN"}}
        mock_pending_store = {"catalog.schema.table": "pending_info"}

        mock_st.session_state.get.side_effect = lambda k, d={}: mock_tbn_store if k == _DEMO_TBN_KEY else mock_pending_store

        res = _approve_table_business_name_override("catalog.schema.table")

        assert mock_tbn_store["catalog.schema.table"]["status"] == "published"
        assert "catalog.schema.table" not in mock_pending_store
        assert res == {"name_en": "Table EN"}

def test__approve_table_business_name_override_demo_mode_not_found():
    from src.audit import _approve_table_business_name_override
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:
        mock_st.session_state.get.return_value.get.return_value = None
        res = _approve_table_business_name_override("catalog.schema.table")
        assert res == {}

@patch("src.audit.get_table_business_name_override")
def test__approve_table_business_name_override_production(mock_get_override):
    from src.audit import _approve_table_business_name_override
    mock_get_override.return_value = {"name_en": "Published EN"}
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit._get_write_connection") as mock_get_write:
        mock_cursor = MagicMock()
        mock_get_write.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        res = _approve_table_business_name_override("catalog.schema.table")

        mock_cursor.execute_write.assert_called_once()
        args = mock_cursor.execute_write.call_args[0]
        assert "UPDATE user_data.table_business_name_overrides SET status = 'published'" in args[0]
        assert args[1] == {"fn": "catalog.schema.table"}
        mock_get_override.assert_called_once_with("catalog.schema.table")
        assert res == {"name_en": "Published EN"}

def test__reject_table_business_name_override_demo_mode():
    from src.audit import (
        _reject_table_business_name_override,
    )
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:
        mock_tbn_store = MagicMock()
        mock_pending_store = MagicMock()
        mock_st.session_state.get.side_effect = [mock_tbn_store, mock_pending_store]

        _reject_table_business_name_override("catalog.schema.table")
        mock_tbn_store.pop.assert_called_once_with("catalog.schema.table", None)
        mock_pending_store.pop.assert_called_once_with("catalog.schema.table", None)

def test__reject_table_business_name_override_production():
    from src.audit import _reject_table_business_name_override
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit._get_write_connection") as mock_get_write:
        mock_cursor = MagicMock()
        mock_get_write.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        _reject_table_business_name_override("catalog.schema.table")

        mock_cursor.execute_write.assert_called_once()
        args = mock_cursor.execute_write.call_args[0]
        assert "DELETE FROM user_data.table_business_name_overrides" in args[0]
        assert args[1] == {"fn": "catalog.schema.table"}

def test__validate_table_business_name_inputs_success():
    from src.audit import _validate_table_business_name_inputs
    _validate_table_business_name_inputs("Valid Name EN", "Valid Name FR", "Valid Def EN", "Valid Def FR")

def test__validate_table_business_name_inputs_name_exceeds():
    from src.audit import MAX_BUSINESS_NAME_LEN, _validate_table_business_name_inputs
    with pytest.raises(ValueError) as exc:
        _validate_table_business_name_inputs("A" * (MAX_BUSINESS_NAME_LEN + 1), "", "", "")
    assert f"name_en exceeds the {MAX_BUSINESS_NAME_LEN}-char limit" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        _validate_table_business_name_inputs("", "B" * (MAX_BUSINESS_NAME_LEN + 1), "", "")
    assert f"name_fr exceeds the {MAX_BUSINESS_NAME_LEN}-char limit" in str(exc.value)

def test__validate_table_business_name_inputs_def_exceeds():
    from src.audit import MAX_DEFINITION_LEN, _validate_table_business_name_inputs
    with pytest.raises(ValueError) as exc:
        _validate_table_business_name_inputs("", "", "C" * (MAX_DEFINITION_LEN + 1), "")
    assert f"definition_en exceeds the {MAX_DEFINITION_LEN}-char limit" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        _validate_table_business_name_inputs("", "", "", "D" * (MAX_DEFINITION_LEN + 1))
    assert f"definition_fr exceeds the {MAX_DEFINITION_LEN}-char limit" in str(exc.value)

def test_approve_table_business_name_not_admin():
    from src.audit import approve_table_business_name
    with patch("src.audit.is_admin", return_value=False):
        with pytest.raises(PermissionError) as exc:
            approve_table_business_name("catalog.schema.table")
        assert "Only admins can approve metadata changes." in str(exc.value)

@patch("src.audit.list_pending_table_business_names")
def test_approve_table_business_name_not_pending(mock_list):
    from src.audit import approve_table_business_name
    mock_list.return_value = []
    with patch("src.audit.is_admin", return_value=True):
        assert approve_table_business_name("catalog.schema.table") is None

@patch("src.audit.list_pending_table_business_names")
@patch("src.audit._approve_table_business_name_override")
@patch("src.audit.enqueue_table_business_name_sync")
@patch("src.audit._duckdb_available", return_value=True)
@patch("src.audit.search_all_metadata")
def test_approve_table_business_name_success(mock_search_cache, mock_duckdb, mock_enqueue, mock_approve, mock_list):
    from src.audit import approve_table_business_name
    mock_list.return_value = [{"table_full_name": "catalog.schema.table"}]
    mock_approve.return_value = {
        "business_name_en": "EN", "business_name_fr": "FR",
        "business_definition_en": "Def EN", "business_definition_fr": "Def FR"
    }
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.st") as mock_st, \
         patch("src.audit._get_shared_duckdb_connection"):
        mock_st.session_state.get.return_value = "admin_user"
        approve_table_business_name("catalog.schema.table")

        mock_approve.assert_called_once_with("catalog.schema.table")
        mock_enqueue.assert_called_once_with("catalog.schema.table", "EN", "FR", "Def EN", "Def FR", "admin_user")
        mock_search_cache.clear.assert_called_once()

@patch("src.audit.list_pending_table_business_names")
@patch("src.audit._approve_table_business_name_override")
@patch("src.audit._duckdb_available", return_value=True)
def test_approve_table_business_name_checkpoint_exception(mock_duckdb, mock_approve, mock_list):
    from src.audit import approve_table_business_name
    mock_list.return_value = [{"table_full_name": "catalog.schema.table"}]
    mock_approve.return_value = {}
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.st"), \
         patch("src.audit.enqueue_table_business_name_sync"), \
         patch("src.audit._get_shared_duckdb_connection", side_effect=Exception("DB err")):
        approve_table_business_name("catalog.schema.table")

def test_reject_table_business_name_not_admin():
    from src.audit import reject_table_business_name
    with patch("src.audit.is_admin", return_value=False):
        with pytest.raises(PermissionError) as exc:
            reject_table_business_name("catalog.schema.table")
        assert "Only admins can reject metadata changes." in str(exc.value)

@patch("src.audit._reject_table_business_name_override")
@patch("src.audit.search_all_metadata")
def test_reject_table_business_name_success(mock_search_cache, mock_reject):
    from src.audit import reject_table_business_name
    with patch("src.audit.is_admin", return_value=True):
        reject_table_business_name("catalog.schema.table")
        mock_reject.assert_called_once_with("catalog.schema.table")

@patch("src.audit._duckdb_available", return_value=True)
@patch("src.audit._get_shared_duckdb_connection", side_effect=Exception("Checkpoint Error"))
@patch("src.audit.enqueue_table_business_name_sync")
@patch("src.audit.log_audit_event")
@patch("src.audit.search_all_metadata")
@patch("src.audit.is_admin", return_value=True)
@patch("src.audit.is_power_user", return_value=True)
def test_save_table_business_name_duckdb_admin_checkpoint_exception(mock_power, mock_admin, mock_search, mock_log, mock_enqueue, mock_get_conn, mock_duck_avail):
    from src.audit import save_table_business_name
    with patch("src.audit.st") as mock_st, \
         patch("src.audit.get_table_business_name_override", return_value={"business_name_en": "Old EN", "business_name_fr": "Old FR"}), \
         patch("src.audit._validate_table_business_name_inputs"), \
         patch("src.audit._upsert_table_business_name_override"):

        mock_st.session_state.get.return_value = "admin_user"

        save_table_business_name(
            "catalog.schema.table", "New EN", "New FR", "Def EN", "Def FR"
        )
        # Should catch exception and proceed to enqueue
        mock_enqueue.assert_called_once()
