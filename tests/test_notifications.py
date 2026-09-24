"""Tests for the bookmark-change notification feature.

Coverage:
  - _build_summary: correct strings for all three notifiable sync types
  - _notify_bookmarkers: skips the actor, inserts one row per other bookmarker
  - _notify_bookmarkers: no-op when no bookmarks exist
  - _notify_bookmarkers: swallows DB errors (never raises)
  - _process_sync_queue: calls _notify_bookmarkers on successful notifiable push
  - _process_sync_queue: does NOT call _notify_bookmarkers for AUDIT/COMMENT
  - get_unread_notifications / mark_read / mark_all_read (public API, demo path)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.sync.push import _build_summary, _notify_bookmarkers


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
        assert cursor.executemany_write.call_count == 1
        args = cursor.executemany_write.call_args[0][1][0]
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
        assert cursor.executemany_write.call_count == 1

    def test_swallows_db_errors(self):
        conn = MagicMock()
        conn.cursor.side_effect = RuntimeError("DB is down")
        # Must not raise
        _notify_bookmarkers(conn, "cat.s.t", "TABLE_DESC", {}, changed_by="actor")

    def test_summary_embedded_in_inserted_row(self):
        conn, cursor = _make_conn([("user-b",)])
        payload = {"column_name": "amount"}
        _notify_bookmarkers(conn, "cat.s.t", "COLUMN_DEF", payload, changed_by="actor")
        args = cursor.executemany_write.call_args[0][1][0]
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


# ── Public API (src.notifications, demo path) ────────────────────────────────

class TestNotificationsAPI:
    """Exercise the demo (session-state) path of the public API."""

    @pytest.fixture(autouse=True)
    def _demo_notifications(self):
        import streamlit as st
        st.session_state.pop("_demo_notifications", None)
        with patch("src.notifications.is_demo_mode", return_value=True):
            yield
        st.session_state.pop("_demo_notifications", None)

    @staticmethod
    def _seed(notification_id, user_oid, table_full_name, change_type, changed_by, summary):
        import streamlit as st
        st.session_state.setdefault("_demo_notifications", {})[notification_id] = {
            "notification_id": notification_id,
            "user_oid": user_oid,
            "table_full_name": table_full_name,
            "change_type": change_type,
            "changed_by": changed_by,
            "summary": summary,
            "created_at": datetime.now(),
            "read_at": None,
        }

    def _make(self):
        self._seed("n1", "user-a", "cat.s.t", "TABLE_DESC", "editor@x.com", "Description updated")
        self._seed("n2", "user-b", "cat.s.t", "COLUMN_DEF", "editor@x.com", "Column 'id' updated")
        self._seed("n3", "user-a", "cat.s.t2", "STEWARD", "admin@x.com", "Steward changed")

    def test_list_unread_filters_by_user(self):
        from src.notifications import get_unread_notifications
        self._make()
        items = get_unread_notifications("user-a")
        assert len(items) == 2
        assert all("user_oid" not in i for i in items)  # user_oid stripped from output

    def test_list_unread_newest_first(self):
        from src.notifications import get_unread_notifications
        self._make()
        items = get_unread_notifications("user-a")
        # n3 was inserted after n1, so it comes first
        assert items[0]["notification_id"] == "n3"

    def test_mark_read_hides_from_list(self):
        from src.notifications import get_unread_notifications, mark_read
        self._make()
        mark_read("n1")
        ids = [i["notification_id"] for i in get_unread_notifications("user-a")]
        assert "n1" not in ids
        assert "n3" in ids

    def test_mark_read_unknown_id(self):
        from src.notifications import mark_read
        self._make()
        # Should return silently from demo mode branch without raising
        mark_read("unknown-id")

    def test_mark_all_read_empties_list(self):
        from src.notifications import get_unread_notifications, mark_all_read
        self._make()
        mark_all_read("user-a")
        assert get_unread_notifications("user-a") == []

    def test_mark_all_read_does_not_affect_other_users(self):
        from src.notifications import get_unread_notifications, mark_all_read
        self._make()
        mark_all_read("user-a")
        assert len(get_unread_notifications("user-b")) == 1

    def test_empty_when_no_notifications(self):
        from src.notifications import get_unread_notifications
        assert get_unread_notifications("unknown-user") == []

# ── Database Path API (src.notifications, non-demo path) ─────────────────────

class TestNotificationsDatabaseAPI:
    """Exercise the database (non-demo) path of the public API."""

    @patch("src.notifications.is_demo_mode", return_value=False)
    @patch("src.db.queries.get_db_connection")
    def test_get_unread_notifications_success(self, mock_get_conn, mock_is_demo):
        from src.notifications import get_unread_notifications

        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # Setup context manager for cursor
        mock_cursor.__enter__.return_value = mock_cursor
        mock_cursor.__exit__.return_value = False

        # Mock database rows returned
        now = datetime.now()
        mock_cursor.fetchall.return_value = [
            ("n1", "cat.s.t", "TABLE_DESC", "editor@x.com", "Summary", now)
        ]

        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        items = get_unread_notifications("user-a")

        assert mock_get_conn.called
        assert mock_conn.cursor.called
        assert mock_cursor.execute.call_count == 1

        # Check query arguments
        query, params = mock_cursor.execute.call_args[0]
        assert "SELECT" in query
        assert params == ["user-a", 20]

        # Check returned data
        assert len(items) == 1
        assert items[0] == {
            "notification_id": "n1",
            "table_full_name": "cat.s.t",
            "change_type": "TABLE_DESC",
            "changed_by": "editor@x.com",
            "summary": "Summary",
            "created_at": now,
        }

    @patch("src.notifications.log")
    @patch("src.notifications.is_demo_mode", return_value=False)
    @patch("src.db.queries.get_db_connection")
    def test_get_unread_notifications_exception(self, mock_get_conn, mock_is_demo, mock_log):
        from src.notifications import get_unread_notifications

        # Make the connection throw an exception to trigger the try/except block
        mock_get_conn.side_effect = Exception("DB error")

        items = get_unread_notifications("user-a")

        # Function should catch error and return empty list
        assert items == []
        mock_log.warning.assert_called_once_with("Could not list notifications for %s: %s", "user-a", mock_get_conn.side_effect)

    @patch("src.notifications.is_demo_mode", return_value=False)
    @patch("src.db.queries._get_write_connection")
    @patch("src.db.duckdb_adapter._db_write_lock")
    @patch("src.notifications._now")
    def test_mark_read_success(self, mock_now, mock_lock, mock_get_write_conn, mock_is_demo):
        from src.notifications import mark_read

        mock_conn = MagicMock()
        mock_get_write_conn.return_value = mock_conn

        now = datetime.now()
        mock_now.return_value = now

        mark_read("n1")

        # Verify db write connection was called
        assert mock_get_write_conn.called
        assert mock_lock.__enter__.called  # verify context manager lock

        # Verify execute
        assert mock_conn.execute.call_count == 1
        query, params = mock_conn.execute.call_args[0]
        assert "UPDATE user_data.notifications SET read_at = ?" in query
        assert params == [now, "n1"]

    @patch("src.notifications.log")
    @patch("src.notifications.is_demo_mode", return_value=False)
    @patch("src.db.queries._get_write_connection")
    def test_mark_read_exception(self, mock_get_write_conn, mock_is_demo, mock_log):
        from src.notifications import mark_read

        # Trigger exception
        mock_get_write_conn.side_effect = Exception("DB error")

        mark_read("n1")

        # Verify error handled
        mock_log.warning.assert_called_once_with("Could not mark notification %s read: %s", "n1", mock_get_write_conn.side_effect)

    @patch("src.notifications.is_demo_mode", return_value=False)
    @patch("src.db.queries._get_write_connection")
    @patch("src.db.duckdb_adapter._db_write_lock")
    @patch("src.notifications._now")
    def test_mark_all_read_success(self, mock_now, mock_lock, mock_get_write_conn, mock_is_demo):
        from src.notifications import mark_all_read

        mock_conn = MagicMock()
        mock_get_write_conn.return_value = mock_conn

        now = datetime.now()
        mock_now.return_value = now

        mark_all_read("user-a")

        # Verify db write connection was called
        assert mock_get_write_conn.called
        assert mock_lock.__enter__.called  # verify context manager lock

        # Verify execute
        assert mock_conn.execute.call_count == 1
        query, params = mock_conn.execute.call_args[0]
        assert "UPDATE user_data.notifications SET read_at = ?" in query
        assert params == [now, "user-a"]

    @patch("src.notifications.log")
    @patch("src.notifications.is_demo_mode", return_value=False)
    @patch("src.db.queries._get_write_connection")
    def test_mark_all_read_exception(self, mock_get_write_conn, mock_is_demo, mock_log):
        from src.notifications import mark_all_read

        # Trigger exception
        mock_get_write_conn.side_effect = Exception("DB error")

        mark_all_read("user-a")

        # Verify error handled
        mock_log.warning.assert_called_once_with("Could not mark all notifications read for %s: %s", "user-a", mock_get_write_conn.side_effect)

    @patch("src.notifications.is_demo_mode", return_value=True)
    def test_mark_read_demo_mode_not_found(self, mock_is_demo):
        from src.notifications import mark_read
        import streamlit as st
        # Create an empty demo store
        st.session_state["_demo_notifications"] = {}
        mark_read("n1")
        # Ensure it safely returns early
        assert st.session_state["_demo_notifications"] == {}


class TestNotificationsAPIDuckDB:
    """Exercise the DuckDB (persistent) path of the public API."""

    @pytest.fixture(autouse=True)
    def _mock_demo_mode(self):
        with patch("src.notifications.is_demo_mode", return_value=False):
            yield

    @patch("src.db.queries.get_db_connection")
    def test_get_unread_notifications_success(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        now = datetime.now()
        mock_cursor.fetchall.return_value = [
            ("n1", "cat.s.t", "TABLE_DESC", "admin", "summary", now)
        ]

        from src.notifications import get_unread_notifications
        items = get_unread_notifications("user-a", limit=5)

        assert len(items) == 1
        assert items[0]["notification_id"] == "n1"

        mock_cursor.execute.assert_called_once()
        query = mock_cursor.execute.call_args[0][0]
        args = mock_cursor.execute.call_args[0][1]
        assert "SELECT notification_id" in query
        assert args == ["user-a", 5]

    @patch("src.db.queries.get_db_connection")
    @patch("src.notifications.log")
    def test_get_unread_notifications_error(self, mock_log, mock_get_conn):
        mock_get_conn.side_effect = Exception("DB error")

        from src.notifications import get_unread_notifications
        items = get_unread_notifications("user-a")

        assert items == []
        mock_log.warning.assert_called_once()
        assert mock_log.warning.call_args[0][0] == "Could not list notifications for %s: %s"
        assert mock_log.warning.call_args[0][1] == "user-a"

    @patch("src.db.duckdb_adapter._db_write_lock")
    @patch("src.db.queries._get_write_connection")
    def test_mark_read_success(self, mock_get_write, mock_lock):
        mock_conn = MagicMock()
        mock_get_write.return_value = mock_conn
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=None)

        from src.notifications import mark_read
        mark_read("n1")

        mock_conn.execute.assert_called_once()
        query = mock_conn.execute.call_args[0][0]
        args = mock_conn.execute.call_args[0][1]
        assert "UPDATE user_data.notifications SET read_at = ?" in query
        assert args[1] == "n1"

    @patch("src.db.duckdb_adapter._db_write_lock")
    @patch("src.db.queries._get_write_connection")
    @patch("src.notifications.log")
    def test_mark_read_error(self, mock_log, mock_get_write, mock_lock):
        mock_get_write.side_effect = Exception("DB error")

        from src.notifications import mark_read
        mark_read("n1")

        mock_log.warning.assert_called_once()
        assert mock_log.warning.call_args[0][0] == "Could not mark notification %s read: %s"
        assert mock_log.warning.call_args[0][1] == "n1"

    @patch("src.db.duckdb_adapter._db_write_lock")
    @patch("src.db.queries._get_write_connection")
    def test_mark_all_read_success(self, mock_get_write, mock_lock):
        mock_conn = MagicMock()
        mock_get_write.return_value = mock_conn
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=None)

        from src.notifications import mark_all_read
        mark_all_read("user-a")

        mock_conn.execute.assert_called_once()
        query = mock_conn.execute.call_args[0][0]
        args = mock_conn.execute.call_args[0][1]
        assert "UPDATE user_data.notifications SET read_at = ?" in query
        assert args[1] == "user-a"

    @patch("src.db.duckdb_adapter._db_write_lock")
    @patch("src.db.queries._get_write_connection")
    @patch("src.notifications.log")
    def test_mark_all_read_error(self, mock_log, mock_get_write, mock_lock):
        mock_get_write.side_effect = Exception("DB error")

        from src.notifications import mark_all_read
        mark_all_read("user-a")

        mock_log.warning.assert_called_once()
        assert mock_log.warning.call_args[0][0] == "Could not mark all notifications read for %s: %s"
        assert mock_log.warning.call_args[0][1] == "user-a"
