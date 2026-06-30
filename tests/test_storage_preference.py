from unittest.mock import patch, MagicMock
import pandas as pd

from src.storage.preference_storage import (
    DuckDBPreferenceStorage,
    FakePreferenceStorage,
    DuckDBSiteSettingStorage,
    FakeSiteSettingStorage,
    DemoPreferenceStorage,
    DemoSiteSettingStorage,
)

def test_duckdb_preference_upsert_success():
    storage = DuckDBPreferenceStorage()
    mock_conn = MagicMock()
    with patch("src.storage.preference_storage.get_db_connection", return_value=mock_conn):
        storage.upsert("u1", "table_1", "bookmark")

    mock_conn.execute.assert_called_once()
    sql, params = mock_conn.execute.call_args[0]
    assert "INSERT INTO user_data.user_preferences" in sql
    assert params == ["u1", "table_1", "bookmark"]

def test_duckdb_preference_upsert_failure():
    storage = DuckDBPreferenceStorage()
    with patch("src.storage.preference_storage.get_db_connection", side_effect=Exception("DB Error")), \
         patch("src.storage.preference_storage.log.warning") as mock_log:
        storage.upsert("u1", "table_1", "bookmark")
    mock_log.assert_called_once()
    assert "Could not write user preference:" in mock_log.call_args[0][0]

def test_duckdb_preference_delete_success():
    storage = DuckDBPreferenceStorage()
    mock_conn = MagicMock()
    with patch("src.storage.preference_storage.get_db_connection", return_value=mock_conn):
        storage.delete("u1", "table_1", "bookmark")

    mock_conn.execute.assert_called_once()
    sql, params = mock_conn.execute.call_args[0]
    assert "DELETE FROM user_data.user_preferences" in sql
    assert params == ["u1", "table_1", "bookmark"]

def test_duckdb_preference_delete_failure():
    storage = DuckDBPreferenceStorage()
    with patch("src.storage.preference_storage.get_db_connection", side_effect=Exception("DB Error")), \
         patch("src.storage.preference_storage.log.warning") as mock_log:
        storage.delete("u1", "table_1", "bookmark")
    mock_log.assert_called_once()
    assert "Could not delete user preference:" in mock_log.call_args[0][0]

def test_duckdb_preference_list_by_type_success():
    storage = DuckDBPreferenceStorage()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    df = pd.DataFrame({"table_full_name": ["table_1", "table_2"]})
    mock_cursor.fetchall_as_pandas.return_value = df

    with patch("src.storage.preference_storage.get_db_connection", return_value=mock_conn):
        result = storage.list_by_type("u1", "bookmark", limit=5)

    assert result == ["table_1", "table_2"]
    mock_cursor.execute.assert_called_once()
    sql, params = mock_cursor.execute.call_args[0]
    assert "SELECT table_full_name FROM user_data.user_preferences" in sql
    assert params == {"oid": "u1", "type": "bookmark", "lim": 5}

def test_duckdb_preference_list_by_type_empty():
    storage = DuckDBPreferenceStorage()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame()

    with patch("src.storage.preference_storage.get_db_connection", return_value=mock_conn):
        result = storage.list_by_type("u1", "bookmark", limit=5)

    assert result == []

def test_duckdb_preference_list_by_type_none():
    storage = DuckDBPreferenceStorage()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall_as_pandas.return_value = None

    with patch("src.storage.preference_storage.get_db_connection", return_value=mock_conn):
        result = storage.list_by_type("u1", "bookmark", limit=5)

    assert result == []

def test_duckdb_preference_list_by_type_failure():
    storage = DuckDBPreferenceStorage()
    with patch("src.storage.preference_storage.get_db_connection", side_effect=Exception("DB Error")), \
         patch("src.storage.preference_storage.log.warning") as mock_log:
        result = storage.list_by_type("u1", "bookmark")

    assert result == []
    mock_log.assert_called_once()
    assert "Could not load user preferences:" in mock_log.call_args[0][0]

def test_duckdb_site_setting_get_success():
    storage = DuckDBSiteSettingStorage()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [("my_val",)]

    with patch("src.storage.preference_storage.get_db_connection", return_value=mock_conn):
        result = storage.get("key1")

    assert result == "my_val"
    mock_cursor.execute.assert_called_once_with(
        "SELECT value FROM user_data.site_settings WHERE key = ?", ["key1"]
    )

def test_duckdb_site_setting_get_empty():
    storage = DuckDBSiteSettingStorage()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = []

    with patch("src.storage.preference_storage.get_db_connection", return_value=mock_conn):
        result = storage.get("key1")

    assert result is None

def test_duckdb_site_setting_get_failure():
    storage = DuckDBSiteSettingStorage()
    with patch("src.storage.preference_storage.get_db_connection", side_effect=Exception("DB Error")), \
         patch("src.storage.preference_storage.log.warning") as mock_log:
        result = storage.get("key1")

    assert result is None
    mock_log.assert_called_once()
    assert mock_log.call_args[0][1] == "key1"

def test_duckdb_site_setting_set_success():
    storage = DuckDBSiteSettingStorage()
    mock_conn = MagicMock()

    with patch("src.storage.preference_storage._get_write_connection", return_value=mock_conn):
        storage.set("key1", "val1", "admin@test.com")

    mock_conn.execute.assert_called_once()
    sql, params = mock_conn.execute.call_args[0]
    assert "INSERT INTO user_data.site_settings" in sql
    assert params == ["key1", "val1", "admin@test.com"]

def test_duckdb_site_setting_set_failure():
    storage = DuckDBSiteSettingStorage()
    with patch("src.storage.preference_storage._get_write_connection", side_effect=Exception("DB Error")), \
         patch("src.storage.preference_storage.log.warning") as mock_log:
        storage.set("key1", "val1", "admin@test.com")

    mock_log.assert_called_once()
    assert mock_log.call_args[0][1] == "key1"

def test_fake_preference_storage():
    storage = FakePreferenceStorage()
    storage.upsert("u1", "table_1", "bookmark")
    storage.upsert("u1", "table_2", "bookmark")

    res = storage.list_by_type("u1", "bookmark")
    assert res == ["table_2", "table_1"]  # newest first

    storage.upsert("u1", "table_1", "bookmark")  # move table_1 to top
    res = storage.list_by_type("u1", "bookmark")
    assert res == ["table_1", "table_2"]

    storage.delete("u1", "table_1", "bookmark")
    res = storage.list_by_type("u1", "bookmark")
    assert res == ["table_2"]

def test_fake_site_setting_storage():
    storage = FakeSiteSettingStorage(initial={"k1": "v1"})
    assert storage.get("k1") == "v1"
    assert storage.get("k2") is None

    storage.set("k2", "v2", "actor")
    assert storage.get("k2") == "v2"

def test_demo_preference_storage():
    storage = DemoPreferenceStorage()
    storage.upsert("u1", "t1", "recent")  # no-op
    storage.delete("u1", "t1", "recent")  # no-op
    assert storage.list_by_type("u1", "recent") == []

def test_demo_site_setting_storage():
    storage = DemoSiteSettingStorage()
    assert storage.get("k1") is None
    storage.set("k1", "v1", "actor")  # no-op
    assert storage.get("k1") is None
