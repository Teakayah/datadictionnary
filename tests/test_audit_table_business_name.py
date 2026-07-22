import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from src.audit import (
    get_table_business_name_override,
    _approve_table_business_name_override,
    _upsert_table_business_name_override,
    list_pending_table_business_names,
    _reject_table_business_name_override,
    _validate_table_business_name_inputs,
    save_table_business_name,
    approve_table_business_name,
    reject_table_business_name,
    TableBusinessNameOverride
)
from src.config import MAX_BUSINESS_NAME_LEN, MAX_DEFINITION_LEN


def test_get_table_business_name_override_demo_mode_hit():
    """Verify get_table_business_name_override in demo mode with a published entry."""
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:

        mock_st.session_state.get.return_value = {
            "catalog.schema.table": {
                "business_name_en": "Table EN",
                "business_name_fr": "Table FR",
                "status": "published"
            }
        }

        result = get_table_business_name_override("catalog.schema.table")
        assert result == {"business_name_en": "Table EN", "business_name_fr": "Table FR"}

def test_get_table_business_name_override_demo_mode_miss():
    """Verify get_table_business_name_override in demo mode without an entry."""
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:

        mock_st.session_state.get.return_value = {}
        result = get_table_business_name_override("catalog.schema.table")
        assert result == {}

def test_get_table_business_name_override_production_hit():
    """Verify get_table_business_name_override fetches from DB."""
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_conn:

        mock_cursor = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame([{
            "business_name_en": "Table EN",
            "business_name_fr": "Table FR",
            "business_definition_en": "Def EN",
            "business_definition_fr": "Def FR",
            "edited_by": "user",
            "edited_at": "now"
        }])

        result = get_table_business_name_override("catalog.schema.table")
        assert result == {
            "business_name_en": "Table EN",
            "business_name_fr": "Table FR",
            "business_definition_en": "Def EN",
            "business_definition_fr": "Def FR",
            "edited_by": "user",
            "edited_at": "now"
        }

def test_get_table_business_name_override_production_empty():
    """Verify get_table_business_name_override handles empty DB results."""
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_conn:

        mock_cursor = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame()

        result = get_table_business_name_override("catalog.schema.table")
        assert result == {}

def test_get_table_business_name_override_production_exception():
    """Verify get_table_business_name_override handles DB exceptions gracefully."""
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection", side_effect=Exception("DB Error")):

        result = get_table_business_name_override("catalog.schema.table")
        assert result == {}

def test_upsert_table_business_name_override_demo_mode_pending():
    """Verify _upsert_table_business_name_override in demo mode sets pending."""
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:

        mock_store = {}
        mock_pending = {}

        mock_st.session_state.setdefault.side_effect = lambda k, d: mock_pending if "pending" in k else mock_store
        mock_st.session_state.setdefault.side_effect = lambda k, d: mock_pending if "pending" in k else mock_store
        mock_st.session_state.get.return_value = "mock_user"

        override = TableBusinessNameOverride(
            table_full_name="catalog.schema.table",
            business_name_en="Table EN",
            business_name_fr="Table FR",
            business_definition_en="Def EN",
            business_definition_fr="Def FR",
            edited_by="user",
            status="pending_approval"
        )

        _upsert_table_business_name_override(override)

        assert "catalog.schema.table" in mock_store
        assert "catalog.schema.table" in mock_pending
        assert mock_pending["catalog.schema.table"]["table_full_name"] == "catalog.schema.table"
        assert mock_store["catalog.schema.table"]["status"] == "pending_approval"

def test_upsert_table_business_name_override_demo_mode_published():
    """Verify _upsert_table_business_name_override in demo mode with published status removes pending."""
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:

        mock_store = {}
        mock_pending = {"catalog.schema.table": {}}

        mock_st.session_state.setdefault.side_effect = lambda k, d: mock_pending if "pending" in k else mock_store
        mock_st.session_state.get.return_value = "mock_user"

        override = TableBusinessNameOverride(
            table_full_name="catalog.schema.table",
            business_name_en="Table EN",
            business_name_fr="Table FR",
            business_definition_en="Def EN",
            business_definition_fr="Def FR",
            edited_by="user",
            status="published"
        )

        _upsert_table_business_name_override(override)

        assert "catalog.schema.table" in mock_store
        assert "catalog.schema.table" not in mock_pending
        assert mock_store["catalog.schema.table"]["status"] == "published"

def test_upsert_table_business_name_override_production():
    """Verify _upsert_table_business_name_override writes to DB."""
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit._get_write_connection") as mock_conn:

        mock_cursor = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        override = TableBusinessNameOverride(
            table_full_name="catalog.schema.table",
            business_name_en="Table EN",
            business_name_fr="Table FR",
            business_definition_en="Def EN",
            business_definition_fr="Def FR",
            edited_by="user",
            status="published"
        )

        _upsert_table_business_name_override(override)

        mock_cursor.execute_write.assert_called_once()
        args, kwargs = mock_cursor.execute_write.call_args
        assert "INSERT INTO user_data.table_business_name_overrides" in args[0]
        assert "ON CONFLICT" in args[0]

def test_list_pending_table_business_names_demo_mode():
    """Verify list_pending_table_business_names in demo mode."""
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:

        mock_st.session_state.get.return_value = {
            "catalog.schema.table": {"data": "value"}
        }

        result = list_pending_table_business_names()
        assert result == [{"data": "value"}]

def test_list_pending_table_business_names_production():
    """Verify list_pending_table_business_names queries DB."""
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection") as mock_conn:

        mock_cursor = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        df = pd.DataFrame([{
            "table_full_name": "catalog.schema.table",
            "business_name_en": "Table EN"
        }])
        mock_cursor.fetchall_as_pandas.return_value = df

        result = list_pending_table_business_names()
        assert len(result) == 1
        assert result[0]["table_full_name"] == "catalog.schema.table"

def test_list_pending_table_business_names_production_exception():
    """Verify list_pending_table_business_names handles exceptions."""
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit.get_db_connection", side_effect=Exception("DB Error")):

        result = list_pending_table_business_names()
        assert result == []

def test_approve_table_business_name_override_demo_mode_hit():
    """Verify _approve_table_business_name_override in demo mode with entry."""
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:

        mock_store = {"catalog.schema.table": {"status": "pending_approval", "other": "val"}}
        mock_pending = {"catalog.schema.table": {}}

        mock_st.session_state.get.side_effect = lambda k, d=None: mock_pending if "pending" in k else mock_store
        mock_st.session_state.get.side_effect = lambda k, d=None: mock_pending if "pending" in k else mock_store

        result = _approve_table_business_name_override("catalog.schema.table")

        assert mock_store["catalog.schema.table"]["status"] == "published"
        assert "catalog.schema.table" not in mock_pending
        assert result == {"other": "val"}

def test_approve_table_business_name_override_demo_mode_miss():
    """Verify _approve_table_business_name_override in demo mode without entry."""
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:

        mock_st.session_state.get.return_value = {}

        result = _approve_table_business_name_override("catalog.schema.table")
        assert result == {}

def test_approve_table_business_name_override_production():
    """Verify _approve_table_business_name_override updates DB."""
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit._get_write_connection") as mock_conn, \
         patch("src.audit.get_table_business_name_override", return_value={"mock": "res"}):

        mock_cursor = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        result = _approve_table_business_name_override("catalog.schema.table")

        mock_cursor.execute_write.assert_called_once()
        args, kwargs = mock_cursor.execute_write.call_args
        assert "UPDATE user_data.table_business_name_overrides SET status = 'published'" in args[0]
        assert result == {"mock": "res"}

def test_reject_table_business_name_override_demo_mode():
    """Verify _reject_table_business_name_override in demo mode."""
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:

        mock_store = {"catalog.schema.table": {}}
        mock_pending = {"catalog.schema.table": {}}

        mock_st.session_state.get.side_effect = lambda k, d=None: mock_pending if "pending" in k else mock_store

        _reject_table_business_name_override("catalog.schema.table")

        assert "catalog.schema.table" not in mock_store
        assert "catalog.schema.table" not in mock_pending

def test_reject_table_business_name_override_production():
    """Verify _reject_table_business_name_override in production."""
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit._get_write_connection") as mock_conn:

        mock_cursor = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        _reject_table_business_name_override("catalog.schema.table")

        mock_cursor.execute_write.assert_called_once()
        args, kwargs = mock_cursor.execute_write.call_args
        assert "DELETE FROM user_data.table_business_name_overrides" in args[0]

def test_validate_table_business_name_inputs_success():
    """Verify validation passes for valid inputs."""
    _validate_table_business_name_inputs("en", "fr", "def en", "def fr")

def test_validate_table_business_name_inputs_name_too_long():
    """Verify validation fails for too long names."""
    long_name = "a" * (MAX_BUSINESS_NAME_LEN + 1)
    with pytest.raises(ValueError, match="name_en exceeds"):
        _validate_table_business_name_inputs(long_name, "fr", "def en", "def fr")
    with pytest.raises(ValueError, match="name_fr exceeds"):
        _validate_table_business_name_inputs("en", long_name, "def en", "def fr")

def test_validate_table_business_name_inputs_def_too_long():
    """Verify validation fails for too long definitions."""
    long_def = "a" * (MAX_DEFINITION_LEN + 1)
    with pytest.raises(ValueError, match="definition_en exceeds"):
        _validate_table_business_name_inputs("en", "fr", long_def, "def fr")
    with pytest.raises(ValueError, match="definition_fr exceeds"):
        _validate_table_business_name_inputs("en", "fr", "def en", long_def)

def test_save_table_business_name_non_power_user():
    """Verify non-power users cannot save table business names."""
    with patch("src.audit.is_power_user", return_value=False):
        with pytest.raises(PermissionError, match="Only editors can propose table friendly names"):
            save_table_business_name("catalog.schema.table", "en", "fr")

def test_save_table_business_name_admin():
    """Verify admin saves table business name as published."""
    with patch("src.audit.is_power_user", return_value=True), \
         patch("src.audit.is_admin", return_value=True), \
         patch("src.audit._upsert_table_business_name_override") as mock_upsert, \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit.enqueue_table_business_name_sync") as mock_enqueue, \
         patch("src.audit._get_shared_duckdb_connection") as mock_conn, \
         patch("src.audit.log_audit_event") as mock_log, \
         patch("src.audit.search_all_metadata") as mock_search, \
         patch("src.audit.st") as mock_st, \
         patch("src.audit.get_table_business_name_override", return_value={}):

        mock_st.session_state.get.side_effect = lambda k, d=None: "admin_user" if k == "user_name" else {}
        mock_shared_conn = MagicMock()
        mock_conn.return_value = mock_shared_conn

        save_table_business_name("catalog.schema.table", "en", "fr", "def en", "def fr")

        mock_upsert.assert_called_once()
        args, kwargs = mock_upsert.call_args
        override = args[0]
        assert override.status == "published"

        mock_enqueue.assert_called_once_with(
            "catalog.schema.table", "en", "fr", "def en", "def fr", "admin_user"
        )
        mock_shared_conn.execute.assert_called_once_with("CHECKPOINT user_data")
        mock_log.assert_called_once()
        mock_search.clear.assert_called_once()

def test_save_table_business_name_power_user():
    """Verify power user saves table business name as pending."""
    with patch("src.audit.is_power_user", return_value=True), \
         patch("src.audit.is_admin", return_value=False), \
         patch("src.audit._upsert_table_business_name_override") as mock_upsert, \
         patch("src.audit.log_audit_event") as mock_log, \
         patch("src.audit.st") as mock_st, \
         patch("src.audit.get_table_business_name_override", return_value={}):

        mock_st.session_state.get.side_effect = lambda k, d=None: "power_user" if k == "user_name" else {}

        save_table_business_name("catalog.schema.table", "en", "fr", "def en", "def fr")

        mock_upsert.assert_called_once()
        args, kwargs = mock_upsert.call_args
        override = args[0]
        assert override.status == "pending_approval"

        mock_log.assert_called_once()

def test_save_table_business_name_duckdb_exception():
    """Verify save_table_business_name handles duckdb exceptions gracefully."""
    with patch("src.audit.is_power_user", return_value=True), \
         patch("src.audit.is_admin", return_value=True), \
         patch("src.audit._upsert_table_business_name_override"), \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit.enqueue_table_business_name_sync"), \
         patch("src.audit._get_shared_duckdb_connection") as mock_conn, \
         patch("src.audit.log_audit_event"), \
         patch("src.audit.search_all_metadata"), \
         patch("src.audit.st"), \
         patch("src.audit.get_table_business_name_override", return_value={}):

        mock_shared_conn = MagicMock()
        mock_shared_conn.execute.side_effect = Exception("DB Error")
        mock_conn.return_value = mock_shared_conn

        save_table_business_name("catalog.schema.table", "en", "fr")

        mock_shared_conn.execute.assert_called_once()

def test_approve_table_business_name_non_admin():
    """Verify non-admins cannot approve table business names."""
    with patch("src.audit.is_admin", return_value=False):
        with pytest.raises(PermissionError, match="Only admins"):
            approve_table_business_name("catalog.schema.table")

def test_approve_table_business_name_not_found():
    """Verify approve_table_business_name does nothing if pending not found."""
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.list_pending_table_business_names", return_value=[]), \
         patch("src.audit._approve_table_business_name_override") as mock_approve:

        approve_table_business_name("catalog.schema.table")

        mock_approve.assert_not_called()

def test_approve_table_business_name_success():
    """Verify approve_table_business_name updates and enqueues sync."""
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.list_pending_table_business_names") as mock_list, \
         patch("src.audit._approve_table_business_name_override") as mock_approve, \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit.enqueue_table_business_name_sync") as mock_enqueue, \
         patch("src.audit._get_shared_duckdb_connection") as mock_conn, \
         patch("src.audit.search_all_metadata") as mock_search, \
         patch("src.audit.st") as mock_st:

        mock_list.return_value = [{"table_full_name": "catalog.schema.table"}]
        mock_approve.return_value = {
            "business_name_en": "en",
            "business_name_fr": "fr",
            "business_definition_en": "def en",
            "business_definition_fr": "def fr"
        }
        mock_st.session_state.get.return_value = "admin_user"

        mock_shared_conn = MagicMock()
        mock_conn.return_value = mock_shared_conn

        approve_table_business_name("catalog.schema.table")

        mock_approve.assert_called_once_with("catalog.schema.table")
        mock_enqueue.assert_called_once_with(
            "catalog.schema.table", "en", "fr", "def en", "def fr", "admin_user"
        )
        mock_shared_conn.execute.assert_called_once_with("CHECKPOINT user_data")
        mock_search.clear.assert_called_once()

def test_approve_table_business_name_duckdb_exception():
    """Verify approve_table_business_name handles duckdb exceptions gracefully."""
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit.list_pending_table_business_names") as mock_list, \
         patch("src.audit._approve_table_business_name_override") as mock_approve, \
         patch("src.audit._duckdb_available", return_value=True), \
         patch("src.audit.enqueue_table_business_name_sync"), \
         patch("src.audit._get_shared_duckdb_connection") as mock_conn, \
         patch("src.audit.search_all_metadata"), \
         patch("src.audit.st"):

        mock_list.return_value = [{"table_full_name": "catalog.schema.table"}]
        mock_approve.return_value = {}

        mock_shared_conn = MagicMock()
        mock_shared_conn.execute.side_effect = Exception("DB Error")
        mock_conn.return_value = mock_shared_conn

        approve_table_business_name("catalog.schema.table")

        mock_shared_conn.execute.assert_called_once()

def test_reject_table_business_name_non_admin():
    """Verify non-admins cannot reject table business names."""
    with patch("src.audit.is_admin", return_value=False):
        with pytest.raises(PermissionError, match="Only admins"):
            reject_table_business_name("catalog.schema.table")

def test_reject_table_business_name_success():
    """Verify reject_table_business_name calls inner function and clears search cache."""
    with patch("src.audit.is_admin", return_value=True), \
         patch("src.audit._reject_table_business_name_override") as mock_reject, \
         patch("src.audit.search_all_metadata") as mock_search:

        reject_table_business_name("catalog.schema.table")

        mock_reject.assert_called_once_with("catalog.schema.table")
        mock_search.clear.assert_called_once()


def test_approve_column_override_demo_mode_hit():
    """Verify _approve_column_override in demo mode with entry."""
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:

        mock_store = {"catalog.schema.table": {"col_name": {"status": "pending_approval", "other": "val"}}}
        mock_pending = {("catalog.schema.table", "col_name"): {}}

        def mock_get(key, default=None):
            if "pending" in key.lower():
                return mock_pending
            return mock_store

        mock_st.session_state.get.side_effect = mock_get

        from src.audit import _approve_column_override
        _approve_column_override("catalog.schema.table", "col_name")

        assert mock_store["catalog.schema.table"]["col_name"]["status"] == "published"
        assert ("catalog.schema.table", "col_name") not in mock_pending

def test_approve_column_override_demo_mode_miss():
    """Verify _approve_column_override in demo mode without entry."""
    with patch("src.audit.is_demo_mode", return_value=True), \
         patch("src.audit.st") as mock_st:

        mock_st.session_state.get.return_value = {}

        from src.audit import _approve_column_override
        _approve_column_override("catalog.schema.table", "col_name")
        # Should not raise exception

def test_approve_column_override_production():
    """Verify _approve_column_override in production updates DB."""
    with patch("src.audit.is_demo_mode", return_value=False), \
         patch("src.audit._get_write_connection") as mock_conn:

        mock_cursor = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        from src.audit import _approve_column_override
        _approve_column_override("catalog.schema.table", "col_name")

        mock_cursor.execute_write.assert_called_once()
        args, kwargs = mock_cursor.execute_write.call_args
        assert "UPDATE user_data.business_name_overrides SET status = 'published'" in args[0]
        assert args[1]["fn"] == "catalog.schema.table"
        assert args[1]["col"] == "col_name"
