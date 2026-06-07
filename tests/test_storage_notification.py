import os
import shutil
import tempfile
from unittest.mock import patch
import duckdb
import pytest

from src.storage.notification_storage import DuckDBNotificationStorage

def test_duckdb_notification_storage():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_notifications.duckdb")

    try:
        with duckdb.connect(db_path) as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS user_data")
            conn.execute("""
                CREATE TABLE user_data.notifications (
                    notification_id VARCHAR,
                    user_oid        VARCHAR,
                    table_full_name VARCHAR,
                    change_type     VARCHAR,
                    changed_by      VARCHAR,
                    summary         VARCHAR,
                    created_at      TIMESTAMP,
                    read_at         TIMESTAMP
                )
            """)

        with patch("src.db.duckdb_adapter._DuckDBConn") as mock_conn_class, \
             patch("src.db.queries.get_db_connection") as mock_get_conn, \
             patch("src.db.queries._get_write_connection") as mock_get_write_conn, \
             patch("src.db.duckdb_adapter._db_write_lock", __import__("threading").Lock()):

            class TestDuckDBCursor:
                def __init__(self, con):
                    self.con = con
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    pass
                def execute(self, query, params=None):
                    self.con.execute(query, params)
                    return self
                def fetchall(self):
                    return self.con.fetchall()

            class TestDuckDBConn:
                def __init__(self, *args, **kwargs):
                    self.con = duckdb.connect(db_path)
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    # Do not close the connection so it can be reused by the same test instance
                    pass
                @property
                def open(self):
                    return True
                def cursor(self):
                    return TestDuckDBCursor(self.con)
                def execute(self, query, params=None):
                    self.con.execute(query, params)
                    return TestDuckDBCursor(self.con)
                def execute_write(self, query, params=None):
                    self.con.execute(query, params)
                    return TestDuckDBCursor(self.con)

            # Use side_effect to return a new connection instance each time
            mock_get_conn.side_effect = TestDuckDBConn
            mock_get_write_conn.side_effect = TestDuckDBConn

            storage = DuckDBNotificationStorage()

            # Test create
            storage.create("n1", "user1", "table1", "UPDATE", "admin", "updated table1")

            # Test list_unread
            unread = storage.list_unread("user1")
            assert len(unread) == 1
            assert unread[0]["notification_id"] == "n1"
            assert unread[0]["table_full_name"] == "table1"

            # Test mark_read
            storage.mark_read("n1")
            unread = storage.list_unread("user1")
            assert len(unread) == 0

            # Test mark_all_read
            storage.create("n2", "user1", "table2", "UPDATE", "admin", "updated table2")
            storage.create("n3", "user1", "table3", "UPDATE", "admin", "updated table3")
            assert len(storage.list_unread("user1")) == 2
            storage.mark_all_read("user1")
            assert len(storage.list_unread("user1")) == 0

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_duckdb_notification_storage_exceptions(caplog):
    import logging
    caplog.set_level(logging.WARNING)

    # Missing database connection should trigger exceptions
    storage = DuckDBNotificationStorage()

    with patch("src.db.queries._get_write_connection", side_effect=Exception("DB connection failed")):
        storage.create("n_err", "user1", "table1", "UPDATE", "admin", "updated table1")
        assert "Could not create notification n_err: DB connection failed" in caplog.text

    with patch("src.db.queries.get_db_connection", side_effect=Exception("DB connection failed")):
        unread = storage.list_unread("user1")
        assert unread == []
        assert "Could not list notifications for user1: DB connection failed" in caplog.text

    with patch("src.db.queries._get_write_connection", side_effect=Exception("DB connection failed")):
        storage.mark_read("n_err")
        assert "Could not mark notification n_err read: DB connection failed" in caplog.text

    with patch("src.db.queries._get_write_connection", side_effect=Exception("DB connection failed")):
        storage.mark_all_read("user1")
        assert "Could not mark all notifications read for user1: DB connection failed" in caplog.text

def test_demo_notification_storage():
    import streamlit as st
    from src.storage.notification_storage import DemoNotificationStorage

    st.session_state.clear()
    storage = DemoNotificationStorage()

    # Test create
    storage.create("n1", "user1", "table1", "UPDATE", "admin", "updated table1")
    assert "_demo_notifications" in st.session_state

    # Test list_unread
    unread = storage.list_unread("user1")
    assert len(unread) == 1
    assert unread[0]["notification_id"] == "n1"

    # Test list_unread for different user
    assert len(storage.list_unread("user2")) == 0

    # Test mark_read
    storage.mark_read("n1")
    assert len(storage.list_unread("user1")) == 0

    # Test mark_all_read
    storage.create("n2", "user1", "table2", "UPDATE", "admin", "updated table2")
    storage.create("n3", "user1", "table3", "UPDATE", "admin", "updated table3")
    assert len(storage.list_unread("user1")) == 2

    storage.mark_all_read("user1")
    assert len(storage.list_unread("user1")) == 0

    # Test mark_read for non-existent notification does not throw error
    storage.mark_read("n_nonexistent")
