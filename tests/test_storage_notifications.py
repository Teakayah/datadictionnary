from unittest.mock import patch, MagicMock
import streamlit as st

from src.storage.notification_storage import (
    DemoNotificationStorage,
    DuckDBNotificationStorage
)

def test_demo_notification_storage():
    st.session_state.clear()
    storage = DemoNotificationStorage()

    storage.create("1", "user1", "main.sales.orders", "schema_change", "admin", "Added column")
    storage.create("2", "user1", "main.sales.customers", "data_update", "system", "Row count increased")
    storage.create("3", "user2", "main.hr.employees", "schema_change", "admin", "Dropped column")

    # Test list_unread limits and filtering
    unread_user1 = storage.list_unread("user1")
    assert len(unread_user1) == 2
    assert unread_user1[0]["notification_id"] == "2" # reversed

    unread_user1_limit = storage.list_unread("user1", limit=1)
    assert len(unread_user1_limit) == 1

    # Test mark_read
    storage.mark_read("1")
    assert len(storage.list_unread("user1")) == 1
    assert storage.list_unread("user1")[0]["notification_id"] == "2"

    # Test mark_all_read
    storage.mark_all_read("user1")
    assert len(storage.list_unread("user1")) == 0
    assert len(storage.list_unread("user2")) == 1

@patch("src.db.queries._get_write_connection")
def test_duckdb_notification_storage_create(mock_get_conn):
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn

    storage = DuckDBNotificationStorage()
    storage.create("1", "user1", "table1", "type1", "admin", "summary")

    mock_conn.execute.assert_called_once()
    assert "INSERT INTO user_data.notifications" in mock_conn.execute.call_args[0][0]

@patch("src.db.queries._get_write_connection")
@patch("src.storage.notification_storage.log")
def test_duckdb_notification_storage_create_error(mock_log, mock_get_conn):
    mock_get_conn.side_effect = Exception("DB error")

    storage = DuckDBNotificationStorage()
    storage.create("1", "user1", "table1", "type1", "admin", "summary")

    mock_log.warning.assert_called_once()
    assert "Could not create notification" in mock_log.warning.call_args[0][0]

@patch("src.db.queries.get_db_connection")
def test_duckdb_notification_storage_list_unread(mock_get_db):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Setup mock return data
    import datetime
    now = datetime.datetime.now()
    mock_cursor.fetchall.return_value = [
        ("1", "table1", "type1", "admin", "summary1", now),
        ("2", "table2", "type2", "system", "summary2", now)
    ]

    storage = DuckDBNotificationStorage()
    unread = storage.list_unread("user1")

    assert len(unread) == 2
    assert unread[0]["notification_id"] == "1"
    assert unread[1]["notification_id"] == "2"
    mock_cursor.execute.assert_called_once()
    assert "SELECT notification_id" in mock_cursor.execute.call_args[0][0]

@patch("src.db.queries.get_db_connection")
@patch("src.storage.notification_storage.log")
def test_duckdb_notification_storage_list_unread_error(mock_log, mock_get_db):
    mock_get_db.side_effect = Exception("DB error")

    storage = DuckDBNotificationStorage()
    unread = storage.list_unread("user1")

    assert len(unread) == 0
    mock_log.warning.assert_called_once()

@patch("src.db.queries._get_write_connection")
def test_duckdb_notification_storage_mark_read(mock_get_conn):
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn

    storage = DuckDBNotificationStorage()
    storage.mark_read("1")

    mock_conn.execute.assert_called_once()
    assert "UPDATE user_data.notifications SET read_at =" in mock_conn.execute.call_args[0][0]

@patch("src.db.queries._get_write_connection")
@patch("src.storage.notification_storage.log")
def test_duckdb_notification_storage_mark_read_error(mock_log, mock_get_conn):
    mock_get_conn.side_effect = Exception("DB error")

    storage = DuckDBNotificationStorage()
    storage.mark_read("1")

    mock_log.warning.assert_called_once()

@patch("src.db.queries._get_write_connection")
def test_duckdb_notification_storage_mark_all_read(mock_get_conn):
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn

    storage = DuckDBNotificationStorage()
    storage.mark_all_read("user1")

    mock_conn.execute.assert_called_once()
    assert "UPDATE user_data.notifications SET read_at =" in mock_conn.execute.call_args[0][0]

@patch("src.db.queries._get_write_connection")
@patch("src.storage.notification_storage.log")
def test_duckdb_notification_storage_mark_all_read_error(mock_log, mock_get_conn):
    mock_get_conn.side_effect = Exception("DB error")

    storage = DuckDBNotificationStorage()
    storage.mark_all_read("user1")

    mock_log.warning.assert_called_once()


from src.storage.notification_storage import FakeNotificationStorage

def test_fake_notification_storage():
    storage = FakeNotificationStorage()

    storage.create("1", "user1", "table1", "type1", "admin", "summary")
    storage.create("2", "user1", "table2", "type2", "system", "summary2")

    unread = storage.list_unread("user1")
    assert len(unread) == 2
    assert unread[0]["notification_id"] == "2" # reversed

    storage.mark_read("1")
    assert len(storage.list_unread("user1")) == 1

    storage.mark_all_read("user1")
    assert len(storage.list_unread("user1")) == 0
