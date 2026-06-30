
from unittest.mock import patch, MagicMock

from src.storage.preference_storage import (
    DemoPreferenceStorage,
    DuckDBPreferenceStorage,
    FakePreferenceStorage,
    DemoSiteSettingStorage,
    DuckDBSiteSettingStorage,
    FakeSiteSettingStorage,
)

def test_demo_preference_storage():
    storage = DemoPreferenceStorage()

    # Test methods return expected defaults without errors
    storage.upsert("user1", "table1", "bookmark")
    storage.delete("user1", "table1", "bookmark")
    assert storage.list_by_type("user1", "bookmark") == []

@patch("src.storage.preference_storage.get_db_connection")
def test_duckdb_preference_storage_upsert(mock_get_db):
    mock_conn = MagicMock()
    mock_get_db.return_value = mock_conn

    storage = DuckDBPreferenceStorage()
    storage.upsert("user1", "table1", "bookmark")

    mock_conn.execute.assert_called_once()
    assert "INSERT INTO user_data.user_preferences" in mock_conn.execute.call_args[0][0]

@patch("src.storage.preference_storage.get_db_connection")
@patch("src.storage.preference_storage.log")
def test_duckdb_preference_storage_upsert_error(mock_log, mock_get_db):
    mock_get_db.side_effect = Exception("DB error")

    storage = DuckDBPreferenceStorage()
    storage.upsert("user1", "table1", "bookmark")

    mock_log.warning.assert_called_once()
    assert "Could not write user preference" in mock_log.warning.call_args[0][0]

@patch("src.storage.preference_storage.get_db_connection")
def test_duckdb_preference_storage_delete(mock_get_db):
    mock_conn = MagicMock()
    mock_get_db.return_value = mock_conn

    storage = DuckDBPreferenceStorage()
    storage.delete("user1", "table1", "bookmark")

    mock_conn.execute.assert_called_once()
    assert "DELETE FROM user_data.user_preferences" in mock_conn.execute.call_args[0][0]

@patch("src.storage.preference_storage.get_db_connection")
@patch("src.storage.preference_storage.log")
def test_duckdb_preference_storage_delete_error(mock_log, mock_get_db):
    mock_get_db.side_effect = Exception("DB error")

    storage = DuckDBPreferenceStorage()
    storage.delete("user1", "table1", "bookmark")

    mock_log.warning.assert_called_once()
    assert "Could not delete user preference" in mock_log.warning.call_args[0][0]

@patch("src.storage.preference_storage.get_db_connection")
def test_duckdb_preference_storage_list_by_type(mock_get_db):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    import pandas as pd
    mock_df = pd.DataFrame({"table_full_name": ["table1", "table2"]})
    mock_cursor.fetchall_as_pandas.return_value = mock_df

    storage = DuckDBPreferenceStorage()
    result = storage.list_by_type("user1", "bookmark")

    assert result == ["table1", "table2"]
    mock_cursor.execute.assert_called_once()
    assert "SELECT table_full_name FROM user_data.user_preferences" in mock_cursor.execute.call_args[0][0]

@patch("src.storage.preference_storage.get_db_connection")
@patch("src.storage.preference_storage.log")
def test_duckdb_preference_storage_list_by_type_error(mock_log, mock_get_db):
    mock_get_db.side_effect = Exception("DB error")

    storage = DuckDBPreferenceStorage()
    result = storage.list_by_type("user1", "bookmark")

    assert result == []
    mock_log.warning.assert_called_once()
    assert "Could not load user preferences" in mock_log.warning.call_args[0][0]


def test_fake_preference_storage():
    storage = FakePreferenceStorage()

    storage.upsert("user1", "table1", "bookmark")
    storage.upsert("user1", "table2", "bookmark")
    storage.upsert("user2", "table3", "bookmark")

    # Order should be reversed (newest first)
    result = storage.list_by_type("user1", "bookmark")
    assert len(result) == 2
    assert result[0] == "table2"
    assert result[1] == "table1"

    # Test limit
    result_limit = storage.list_by_type("user1", "bookmark", limit=1)
    assert len(result_limit) == 1
    assert result_limit[0] == "table2"

    # Test delete
    storage.delete("user1", "table1", "bookmark")
    assert storage.list_by_type("user1", "bookmark") == ["table2"]


def test_demo_site_setting_storage():
    storage = DemoSiteSettingStorage()

    assert storage.get("key1") is None
    storage.set("key1", "value1", "admin")
    assert storage.get("key1") is None


@patch("src.storage.preference_storage.get_db_connection")
def test_duckdb_site_setting_storage_get(mock_get_db):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [("value1",)]

    storage = DuckDBSiteSettingStorage()
    result = storage.get("key1")

    assert result == "value1"
    mock_cursor.execute.assert_called_once()
    assert "SELECT value FROM user_data.site_settings" in mock_cursor.execute.call_args[0][0]

@patch("src.storage.preference_storage.get_db_connection")
@patch("src.storage.preference_storage.log")
def test_duckdb_site_setting_storage_get_error(mock_log, mock_get_db):
    mock_get_db.side_effect = Exception("DB error")

    storage = DuckDBSiteSettingStorage()
    result = storage.get("key1")

    assert result is None
    mock_log.warning.assert_called_once()
    assert "Could not read site_settings" in mock_log.warning.call_args[0][0]

@patch("src.storage.preference_storage._get_write_connection")
def test_duckdb_site_setting_storage_set(mock_get_write):
    mock_conn = MagicMock()
    mock_get_write.return_value = mock_conn

    storage = DuckDBSiteSettingStorage()
    storage.set("key1", "value1", "admin")

    mock_conn.execute.assert_called_once()
    assert "INSERT INTO user_data.site_settings" in mock_conn.execute.call_args[0][0]

@patch("src.storage.preference_storage._get_write_connection")
@patch("src.storage.preference_storage.log")
def test_duckdb_site_setting_storage_set_error(mock_log, mock_get_write):
    mock_get_write.side_effect = Exception("DB error")

    storage = DuckDBSiteSettingStorage()
    storage.set("key1", "value1", "admin")

    mock_log.warning.assert_called_once()
    assert "Could not persist site_settings" in mock_log.warning.call_args[0][0]

def test_fake_site_setting_storage():
    storage = FakeSiteSettingStorage({"key1": "initial_value"})

    assert storage.get("key1") == "initial_value"
    assert storage.get("key2") is None

    storage.set("key2", "value2", "admin")
    assert storage.get("key2") == "value2"
