"""Tests for the bookmark-change notification feature.

Coverage:
  - _build_summary: correct strings for all three notifiable sync types
  - _notify_bookmarkers: skips the actor, inserts one row per other bookmarker
  - _notify_bookmarkers: no-op when no bookmarks exist
  - _notify_bookmarkers: swallows DB errors (never raises)
  - _process_sync_queue: calls _notify_bookmarkers on successful notifiable push
  - _process_sync_queue: does NOT call _notify_bookmarkers for AUDIT/COMMENT
  - FakeNotificationStorage: list_unread, mark_read, mark_all_read
  - get_unread_notifications / mark_read / mark_all_read (public API)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

from src.storage.notification_storage import FakeNotificationStorage
from src.sync.push import _build_summary, _notify_bookmarkers, _NOTIFIABLE_TYPES


# ── _build_summary ────────────────────────────────────────────────────────────

class TestBuildSummary:
    def test_table_desc(self):
        assert _build_summary("TABLE_DESC", {}) == "Description updated"

    def test_column_def_with_name(self):
        s = _build_summary("COLUMN_DEF", {"column_name": "revenue"})
        assert "revenue" in s

    def test_column_def_without_name(self):
        s = _build_summary("COLUMN_DEF", {})
        assert "Column" in s

    def test_steward_with_email(self):
        s = _build_summary("STEWARD", {"steward_email": "owner@example.com"})
        assert "owner@example.com" in s

    def test_steward_without_email(self):
        s = _build_summary("STEWARD", {})
        assert "Steward" in s


# ── _notify_bookmarkers ───────────────────────────────────────────────────────

def _make_conn(bookmark_rows):
    """Return a minimal fake DaemonConn whose cursor returns bookmark_rows."""
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchall.return_value = bookmark_rows
    cursor.execute_write = MagicMock()

    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


class TestNotifyBookmarkers:
    def test_inserts_one_row_per_other_bookmarker(self):
        conn, cursor = _make_conn([("user-a",), ("user-b",)])
        _notify_bookmarkers(conn, "cat.s.t", "TABLE_DESC", {}, changed_by="user-a")
        # user-a is the actor — only user-b gets a notification
        assert cursor.execute_write.call_count == 1
        args = cursor.execute_write.call_args[0][1]
        assert args[1] == "user-b"          # user_oid
        assert args[2] == "cat.s.t"         # table_full_name
        assert args[3] == "TABLE_DESC"       # change_type
        assert args[4] == "user-a"           # changed_by

    def test_no_op_when_no_bookmarks(self):
        conn, cursor = _make_conn([])
        _notify_bookmarkers(conn, "cat.s.t", "TABLE_DESC", {}, changed_by="actor")
        cursor.execute_write.assert_not_called()

    def test_inserts_for_all_bookmarkers_when_actor_not_in_list(self):
        conn, cursor = _make_conn([("user-x",), ("user-y",)])
        _notify_bookmarkers(conn, "cat.s.t", "COLUMN_DEF", {"column_name": "id"}, changed_by="someone-else")
        assert cursor.execute_write.call_count == 2

    def test_swallows_db_errors(self):
        conn = MagicMock()
        conn.cursor.side_effect = RuntimeError("DB is down")
        # Must not raise
        _notify_bookmarkers(conn, "cat.s.t", "TABLE_DESC", {}, changed_by="actor")

    def test_summary_embedded_in_inserted_row(self):
        conn, cursor = _make_conn([("user-b",)])
        payload = {"column_name": "amount"}
        _notify_bookmarkers(conn, "cat.s.t", "COLUMN_DEF", payload, changed_by="actor")
        args = cursor.execute_write.call_args[0][1]
        summary = args[5]
        assert "amount" in summary


# ── _process_sync_queue integration ──────────────────────────────────────────

class TestProcessSyncQueueNotifications:
    """Verify that _process_sync_queue wires _notify_bookmarkers correctly."""

    def _make_queue_conn(self, rows):
        """Minimal conn whose cursor returns rows on the first SELECT."""
        cursor = MagicMock()
        cursor.__enter__ = lambda s: s
        cursor.__exit__ = MagicMock(return_value=False)
        cursor.fetchall.return_value = rows
        cursor.execute_write = MagicMock()

        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def _sync_row(self, sync_type, table_fn="cat.s.t", payload=None):
        import json
        return (str(uuid.uuid4()), sync_type, table_fn, json.dumps(payload or {}), 0, "actor@example.com")

    @pytest.mark.parametrize("sync_type", ["TABLE_DESC", "COLUMN_DEF", "STEWARD"])
    def test_notifiable_type_triggers_notify(self, sync_type):
        conn = self._make_queue_conn([self._sync_row(sync_type)])
        with patch("src.sync.push._push_to_databricks"), \
             patch("src.sync.push._notify_bookmarkers") as mock_notify:
            from src.sync.push import _process_sync_queue
            _process_sync_queue(conn=conn)
        mock_notify.assert_called_once()

    @pytest.mark.parametrize("sync_type", ["AUDIT", "COMMENT"])
    def test_non_notifiable_type_skips_notify(self, sync_type):
        conn = self._make_queue_conn([self._sync_row(sync_type, table_fn=None)])
        with patch("src.sync.push._push_to_databricks"), \
             patch("src.sync.push._notify_bookmarkers") as mock_notify:
            from src.sync.push import _process_sync_queue
            _process_sync_queue(conn=conn)
        mock_notify.assert_not_called()

    def test_failed_push_skips_notify(self):
        conn = self._make_queue_conn([self._sync_row("TABLE_DESC")])
        with patch("src.sync.push._push_to_databricks", side_effect=RuntimeError("fail")), \
             patch("src.sync.push._notify_bookmarkers") as mock_notify:
            from src.sync.push import _process_sync_queue
            _process_sync_queue(conn=conn)
        mock_notify.assert_not_called()


# ── FakeNotificationStorage ───────────────────────────────────────────────────

class TestFakeNotificationStorage:
    def _make(self):
        store = FakeNotificationStorage()
        store.create("n1", "user-a", "cat.s.t", "TABLE_DESC", "editor@x.com", "Description updated")
        store.create("n2", "user-b", "cat.s.t", "COLUMN_DEF", "editor@x.com", "Column 'id' updated")
        store.create("n3", "user-a", "cat.s.t2", "STEWARD", "admin@x.com", "Steward changed")
        return store

    def test_list_unread_filters_by_user(self):
        store = self._make()
        items = store.list_unread("user-a")
        assert len(items) == 2
        assert all("user_oid" not in i for i in items)  # user_oid stripped from output

    def test_list_unread_newest_first(self):
        store = self._make()
        items = store.list_unread("user-a")
        # n3 was inserted after n1, so it comes first
        assert items[0]["notification_id"] == "n3"

    def test_mark_read_hides_from_list(self):
        store = self._make()
        store.mark_read("n1")
        ids = [i["notification_id"] for i in store.list_unread("user-a")]
        assert "n1" not in ids
        assert "n3" in ids

    def test_mark_all_read_empties_list(self):
        store = self._make()
        store.mark_all_read("user-a")
        assert store.list_unread("user-a") == []

    def test_mark_all_read_does_not_affect_other_users(self):
        store = self._make()
        store.mark_all_read("user-a")
        assert len(store.list_unread("user-b")) == 1

    def test_empty_when_no_notifications(self):
        store = FakeNotificationStorage()
        assert store.list_unread("unknown-user") == []


# ── Public API (src.notifications) ───────────────────────────────────────────

class TestPublicNotificationsAPI:
    def test_get_unread_delegates_to_storage(self):
        fake = FakeNotificationStorage()
        fake.create("n1", "u1", "a.b.c", "TABLE_DESC", "e@x.com", "Updated")
        with patch("src.notifications.get_notification_storage", return_value=fake):
            from src.notifications import get_unread_notifications
            result = get_unread_notifications("u1")
        assert len(result) == 1
        assert result[0]["notification_id"] == "n1"

    def test_mark_read_delegates_to_storage(self):
        fake = FakeNotificationStorage()
        fake.create("n1", "u1", "a.b.c", "TABLE_DESC", "e@x.com", "Updated")
        with patch("src.notifications.get_notification_storage", return_value=fake):
            from src.notifications import mark_read
            mark_read("n1")
        assert fake.list_unread("u1") == []

    def test_mark_all_read_delegates_to_storage(self):
        fake = FakeNotificationStorage()
        fake.create("n1", "u1", "a.b.c", "TABLE_DESC", "e@x.com", "A")
        fake.create("n2", "u1", "a.b.d", "COLUMN_DEF", "e@x.com", "B")
        with patch("src.notifications.get_notification_storage", return_value=fake):
            from src.notifications import mark_all_read
            mark_all_read("u1")
        assert fake.list_unread("u1") == []
