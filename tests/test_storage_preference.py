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
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from src.storage.preference_storage import (
    DemoPreferenceStorage,
    DuckDBPreferenceStorage,
    FakePreferenceStorage,
    DemoSiteSettingStorage,
    DuckDBSiteSettingStorage,
    FakeSiteSettingStorage,
)

class TestDemoPreferenceStorage:
    def test_upsert_delete_list(self):
        storage = DemoPreferenceStorage()
        assert storage.upsert("u1", "t1", "bookmark") is None
        assert storage.delete("u1", "t1", "bookmark") is None
        assert storage.list_by_type("u1", "bookmark") == []

class TestFakePreferenceStorage:
    def test_upsert_delete_list(self):
        storage = FakePreferenceStorage()
        storage.upsert("u1", "t1", "bookmark")
        storage.upsert("u1", "t2", "bookmark")

        res = storage.list_by_type("u1", "bookmark")
        assert res == ["t2", "t1"]

        storage.delete("u1", "t1", "bookmark")
        assert storage.list_by_type("u1", "bookmark") == ["t2"]

class TestDuckDBPreferenceStorage:
    @patch("src.storage.preference_storage.get_db_connection")
    def test_upsert_success(self, mock_get_conn):
        storage = DuckDBPreferenceStorage()
        storage.upsert("u1", "t1", "bookmark")
        mock_get_conn.return_value.execute.assert_called_once()

    @patch("src.storage.preference_storage.get_db_connection")
    def test_upsert_exception(self, mock_get_conn):
        mock_get_conn.side_effect = Exception("DB error")
        storage = DuckDBPreferenceStorage()
        storage.upsert("u1", "t1", "bookmark") # Should not raise

    @patch("src.storage.preference_storage.get_db_connection")
    def test_delete_success(self, mock_get_conn):
        storage = DuckDBPreferenceStorage()
        storage.delete("u1", "t1", "bookmark")
        mock_get_conn.return_value.execute.assert_called_once()

    @patch("src.storage.preference_storage.get_db_connection")
    def test_delete_exception(self, mock_get_conn):
        mock_get_conn.side_effect = Exception("DB error")
        storage = DuckDBPreferenceStorage()
        storage.delete("u1", "t1", "bookmark") # Should not raise

    @patch("src.storage.preference_storage.get_db_connection")
    def test_list_by_type_success(self, mock_get_conn):
        storage = DuckDBPreferenceStorage()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame([{"table_full_name": "t1"}])

        assert storage.list_by_type("u1", "bookmark") == ["t1"]

    @patch("src.storage.preference_storage.get_db_connection")
    def test_list_by_type_empty(self, mock_get_conn):
        storage = DuckDBPreferenceStorage()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame()

        assert storage.list_by_type("u1", "bookmark") == []

    @patch("src.storage.preference_storage.get_db_connection")
    def test_list_by_type_exception(self, mock_get_conn):
        mock_get_conn.side_effect = Exception("DB error")
        storage = DuckDBPreferenceStorage()
        assert storage.list_by_type("u1", "bookmark") == []

class TestDemoSiteSettingStorage:
    def test_get_set(self):
        storage = DemoSiteSettingStorage()
        assert storage.get("k1") is None
        assert storage.set("k1", "v1", "u1") is None

class TestFakeSiteSettingStorage:
    def test_get_set(self):
        storage = FakeSiteSettingStorage({"init": "val"})
        assert storage.get("init") == "val"
        storage.set("k1", "v1", "u1")
        assert storage.get("k1") == "v1"

class TestDuckDBSiteSettingStorage:
    @patch("src.storage.preference_storage._get_write_connection")
    def test_set_success(self, mock_write_conn):
        storage = DuckDBSiteSettingStorage()
        storage.set("k1", "v1", "u1")
        mock_write_conn.return_value.execute.assert_called_once()

    @patch("src.storage.preference_storage._get_write_connection")
    def test_set_exception(self, mock_write_conn):
        mock_write_conn.side_effect = Exception("DB error")
        storage = DuckDBSiteSettingStorage()
        storage.set("k1", "v1", "u1") # Should not raise

    @patch("src.storage.preference_storage.get_db_connection")
    def test_get_success(self, mock_get_conn):
        storage = DuckDBSiteSettingStorage()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [["v1"]]

        assert storage.get("k1") == "v1"

    @patch("src.storage.preference_storage.get_db_connection")
    def test_get_empty(self, mock_get_conn):
        storage = DuckDBSiteSettingStorage()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        assert storage.get("k1") is None

    @patch("src.storage.preference_storage.get_db_connection")
    def test_get_exception(self, mock_get_conn):
        mock_get_conn.side_effect = Exception("DB error")
        storage = DuckDBSiteSettingStorage()
        assert storage.get("k1") is None
