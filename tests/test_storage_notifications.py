"""Tests for src/storage/notification_storage.py — NotificationStorage backends."""

from __future__ import annotations

import duckdb
import pytest
from unittest.mock import patch

from src.storage.notification_storage import (
    DemoNotificationStorage,
    DuckDBNotificationStorage,
    FakeNotificationStorage,
    NotificationStorage,
)

# ── Protocol satisfaction ────────────────────────────────────────────────────

@pytest.mark.parametrize("cls", [
    DemoNotificationStorage, DuckDBNotificationStorage, FakeNotificationStorage,
])
def test_notification_implementations_satisfy_protocol(cls):
    assert isinstance(cls(), NotificationStorage)

# ── Demo behaviour ───────────────────────────────────────────────────────────

class TestDemoNotificationStorage:
    @pytest.fixture(autouse=True)
    def reset_st(self):
        import streamlit as st
        if DemoNotificationStorage._KEY in st.session_state:
            del st.session_state[DemoNotificationStorage._KEY]

    def test_create_and_list_unread(self):
        demo = DemoNotificationStorage()
        demo.create("n1", "u1", "table_1", "TABLE_DESC", "editor@x.com", "Summary 1")
        demo.create("n2", "u1", "table_2", "COLUMN_DEF", "editor@x.com", "Summary 2")
        demo.create("n3", "u2", "table_3", "TABLE_DESC", "editor@x.com", "Summary 3")

        # Newest first.
        unread_u1 = demo.list_unread("u1")
        assert len(unread_u1) == 2
        assert unread_u1[0]["notification_id"] == "n2"
        assert unread_u1[1]["notification_id"] == "n1"

        unread_u2 = demo.list_unread("u2")
        assert len(unread_u2) == 1
        assert unread_u2[0]["notification_id"] == "n3"

    def test_list_unread_limit(self):
        demo = DemoNotificationStorage()
        for i in range(5):
            demo.create(f"n{i}", "u1", "table", "TABLE_DESC", "user", "Summary")

        unread = demo.list_unread("u1", limit=3)
        assert len(unread) == 3
        assert unread[0]["notification_id"] == "n4"
        assert unread[1]["notification_id"] == "n3"
        assert unread[2]["notification_id"] == "n2"

    def test_mark_read(self):
        demo = DemoNotificationStorage()
        demo.create("n1", "u1", "table", "TABLE_DESC", "user", "Summary")
        demo.create("n2", "u1", "table", "TABLE_DESC", "user", "Summary")

        demo.mark_read("n1")
        unread = demo.list_unread("u1")
        assert len(unread) == 1
        assert unread[0]["notification_id"] == "n2"

    def test_mark_all_read(self):
        demo = DemoNotificationStorage()
        demo.create("n1", "u1", "table", "TABLE_DESC", "user", "Summary")
        demo.create("n2", "u1", "table", "TABLE_DESC", "user", "Summary")
        demo.create("n3", "u2", "table", "TABLE_DESC", "user", "Summary")

        demo.mark_all_read("u1")
        assert len(demo.list_unread("u1")) == 0
        assert len(demo.list_unread("u2")) == 1

# ── DuckDB backend smoke test ────────────────────────────────────────────────

class TestDuckDBNotificationStorage:
    @pytest.fixture
    def storage(self, tmp_path):
        catalog_path = tmp_path / "dict.duckdb"

        # Init duckdb with user_data schema and notifications table
        conn = duckdb.connect(str(catalog_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS user_data")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_data.notifications (
                notification_id VARCHAR PRIMARY KEY,
                user_oid VARCHAR,
                table_full_name VARCHAR,
                change_type VARCHAR,
                changed_by VARCHAR,
                summary VARCHAR,
                created_at TIMESTAMP,
                read_at TIMESTAMP
            )
        """)
        conn.close()

        def _mock_get_write_conn():
            return duckdb.connect(str(catalog_path))

        def _mock_get_db_conn():
            return duckdb.connect(str(catalog_path))

        with patch("src.db.queries._get_write_connection", side_effect=_mock_get_write_conn), \
             patch("src.db.queries.get_db_connection", side_effect=_mock_get_db_conn):

            yield DuckDBNotificationStorage()

    def test_create_and_list_unread(self, storage):
        storage.create("n1", "u1", "table_1", "TABLE_DESC", "editor@x.com", "Summary 1")
        storage.create("n2", "u1", "table_2", "COLUMN_DEF", "editor@x.com", "Summary 2")
        storage.create("n3", "u2", "table_3", "TABLE_DESC", "editor@x.com", "Summary 3")

        # Newest first.
        unread_u1 = storage.list_unread("u1")
        assert len(unread_u1) == 2
        assert unread_u1[0]["notification_id"] == "n2"
        assert unread_u1[1]["notification_id"] == "n1"

        unread_u2 = storage.list_unread("u2")
        assert len(unread_u2) == 1
        assert unread_u2[0]["notification_id"] == "n3"

    def test_list_unread_limit(self, storage):
        import time
        for i in range(5):
            storage.create(f"n{i}", "u1", "table", "TABLE_DESC", "user", "Summary")
            time.sleep(0.01) # to ensure different created_at

        unread = storage.list_unread("u1", limit=3)
        assert len(unread) == 3
        assert unread[0]["notification_id"] == "n4"
        assert unread[1]["notification_id"] == "n3"
        assert unread[2]["notification_id"] == "n2"

    def test_mark_read(self, storage):
        storage.create("n1", "u1", "table", "TABLE_DESC", "user", "Summary")
        storage.create("n2", "u1", "table", "TABLE_DESC", "user", "Summary")

        storage.mark_read("n1")
        unread = storage.list_unread("u1")
        assert len(unread) == 1
        assert unread[0]["notification_id"] == "n2"

    def test_mark_all_read(self, storage):
        storage.create("n1", "u1", "table", "TABLE_DESC", "user", "Summary")
        storage.create("n2", "u1", "table", "TABLE_DESC", "user", "Summary")
        storage.create("n3", "u2", "table", "TABLE_DESC", "user", "Summary")

        storage.mark_all_read("u1")
        assert len(storage.list_unread("u1")) == 0
        assert len(storage.list_unread("u2")) == 1

class TestDuckDBNotificationStorageExceptions:
    def test_create_exception(self):
        storage = DuckDBNotificationStorage()
        with patch('src.db.queries._get_write_connection', side_effect=Exception("DB error")):
            storage.create("n1", "u1", "table", "TABLE_DESC", "user", "Summary") # should catch

    def test_list_unread_exception(self):
        storage = DuckDBNotificationStorage()
        with patch('src.db.queries.get_db_connection', side_effect=Exception("DB error")):
            assert storage.list_unread("u1") == []

    def test_mark_read_exception(self):
        storage = DuckDBNotificationStorage()
        with patch('src.db.queries._get_write_connection', side_effect=Exception("DB error")):
            storage.mark_read("n1") # should catch

    def test_mark_all_read_exception(self):
        storage = DuckDBNotificationStorage()
        with patch('src.db.queries._get_write_connection', side_effect=Exception("DB error")):
            storage.mark_all_read("u1") # should catch

class TestFakeNotificationStorage:
    def test_create_and_list_unread(self):
        fake = FakeNotificationStorage()
        fake.create("n1", "u1", "table_1", "TABLE_DESC", "editor@x.com", "Summary 1")
        fake.create("n2", "u1", "table_2", "COLUMN_DEF", "editor@x.com", "Summary 2")
        fake.create("n3", "u2", "table_3", "TABLE_DESC", "editor@x.com", "Summary 3")

        # Newest first.
        unread_u1 = fake.list_unread("u1")
        assert len(unread_u1) == 2
        assert unread_u1[0]["notification_id"] == "n2"
        assert unread_u1[1]["notification_id"] == "n1"

        unread_u2 = fake.list_unread("u2")
        assert len(unread_u2) == 1
        assert unread_u2[0]["notification_id"] == "n3"

    def test_list_unread_limit(self):
        fake = FakeNotificationStorage()
        for i in range(5):
            fake.create(f"n{i}", "u1", "table", "TABLE_DESC", "user", "Summary")

        unread = fake.list_unread("u1", limit=3)
        assert len(unread) == 3
        assert unread[0]["notification_id"] == "n4"
        assert unread[1]["notification_id"] == "n3"
        assert unread[2]["notification_id"] == "n2"

    def test_mark_read(self):
        fake = FakeNotificationStorage()
        fake.create("n1", "u1", "table", "TABLE_DESC", "user", "Summary")
        fake.create("n2", "u1", "table", "TABLE_DESC", "user", "Summary")

        fake.mark_read("n1")
        unread = fake.list_unread("u1")
        assert len(unread) == 1
        assert unread[0]["notification_id"] == "n2"

    def test_mark_all_read(self):
        fake = FakeNotificationStorage()
        fake.create("n1", "u1", "table", "TABLE_DESC", "user", "Summary")
        fake.create("n2", "u1", "table", "TABLE_DESC", "user", "Summary")
        fake.create("n3", "u2", "table", "TABLE_DESC", "user", "Summary")

        fake.mark_all_read("u1")
        assert len(fake.list_unread("u1")) == 0
        assert len(fake.list_unread("u2")) == 1
