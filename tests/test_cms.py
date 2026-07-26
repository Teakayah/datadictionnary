"""
Tests for the CMS data layer + discovery banner.

Coverage:
  - Data layer (demo path, ``st.session_state['_demo_cms_posts']``):
      * create_post writes a post with expected fields
      * create_post with expiry_days=None leaves expires_at None
      * get_active_posts filters expired posts
      * get_active_posts includes never-expiry posts
      * delete_post removes the matching post_id
  - AppTest: discovery banner renders, admin sees delete button.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone; UTC = timezone.utc
from unittest.mock import patch

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")
ADMIN_GROUP = "admin_group_id"
_DEMO_KEY = "_demo_cms_posts"


@pytest.fixture
def admin_context():
    """Make is_admin() return True inside the test, then restore."""
    with patch("src.cms.is_admin", return_value=True):
        yield


@pytest.fixture
def demo_posts():
    """Route src.cms through the demo (session-state) path with a clean slate.

    Yields the session-state proxy; tests seed ``st.session_state[_DEMO_KEY]``
    and assert against it after calling the public API.
    """
    st.session_state.pop(_DEMO_KEY, None)
    with patch("src.cms.is_demo_mode", return_value=True):
        yield st.session_state
    st.session_state.pop(_DEMO_KEY, None)


def _make_post(post_id, title, *, created_at=None, expires_at=None):
    return {
        "post_id": post_id, "post_type": "guide", "title": title,
        "body": "", "table_ref": None, "author_email": "a@b.com",
        "created_at": created_at or datetime.now(UTC), "expires_at": expires_at,
    }


# ── Unit tests against the demo path via the public src.cms API ──────────────

class TestCreatePost:
    def test_writes_post_with_expected_fields(self, admin_context, demo_posts):
        """create_post round-trips through the demo session-state path."""
        from src.cms import PostParams, create_post
        create_post(PostParams("announcement", "Hello", "Body text", None, "admin@test.com", 2))
        posts = demo_posts[_DEMO_KEY]
        assert len(posts) == 1
        assert posts[0]["title"] == "Hello"
        assert posts[0]["post_type"] == "announcement"
        assert posts[0]["expires_at"] is not None

    def test_never_expiry_sets_none(self, admin_context, demo_posts):
        """create_post with expiry_days=None leaves expires_at as None."""
        from src.cms import PostParams, create_post
        create_post(PostParams("guide", "Guide", "", None, "admin@test.com", None))
        assert demo_posts[_DEMO_KEY][0]["expires_at"] is None

    def test_rejects_non_admin(self, demo_posts):
        """create_post raises PermissionError when caller is not admin."""
        from src.cms import PostParams, create_post
        with patch("src.cms.is_admin", return_value=False):
            with pytest.raises(PermissionError, match="admins"):
                create_post(PostParams("announcement", "Hello", "", None, "u@x.com", 2))
        # Storage was not touched.
        assert demo_posts.get(_DEMO_KEY) in (None, [])

    def test_create_post_storage_error_is_logged_and_propagated(self, admin_context, caplog):
        """create_post catches storage exceptions, logs them, and re-raises."""
        import logging
        with patch("src.cms.is_demo_mode", return_value=False), \
             patch("src.cms._get_write_connection", side_effect=Exception("Storage offline")):
            from src.cms import PostParams, create_post
            with caplog.at_level(logging.ERROR):
                with pytest.raises(Exception, match="Storage offline") as exc_info:
                    create_post(PostParams("guide", "Guide", "", None, "admin@test.com", None))
                assert str(exc_info.value) == "Storage offline"

        assert "Could not create CMS post: Storage offline" in caplog.text


class TestGetActivePosts:
    def test_empty_storage_returns_empty_list(self, demo_posts):
        """get_active_posts returns an empty list when no posts exist."""
        from src.cms import get_active_posts
        assert get_active_posts() == []

    def test_filters_expired_posts(self, demo_posts):
        """get_active_posts excludes posts whose expires_at is in the past."""
        now = datetime.now(UTC)
        demo_posts[_DEMO_KEY] = [
            _make_post("1", "Live", expires_at=now + timedelta(days=1)),
            _make_post("2", "Expired", created_at=now - timedelta(days=3),
                       expires_at=now - timedelta(days=1)),
        ]
        from src.cms import get_active_posts
        titles = [p["title"] for p in get_active_posts()]
        assert "Live" in titles
        assert "Expired" not in titles

    def test_returns_never_expiry_posts(self, demo_posts):
        """get_active_posts includes posts with expires_at=None."""
        demo_posts[_DEMO_KEY] = [_make_post("3", "Permanent")]
        from src.cms import get_active_posts
        assert any(p["title"] == "Permanent" for p in get_active_posts())


class TestGetAllPosts:
    def test_returns_all_posts_including_expired(self, demo_posts):
        """get_all_posts returns all posts regardless of expiry."""
        now = datetime.now(UTC)
        demo_posts[_DEMO_KEY] = [
            _make_post("1", "Live", expires_at=now + timedelta(days=1)),
            _make_post("2", "Expired", created_at=now - timedelta(days=3),
                       expires_at=now - timedelta(days=1)),
        ]
        from src.cms import get_all_posts
        titles = [p["title"] for p in get_all_posts()]
        assert "Live" in titles
        assert "Expired" in titles

    def test_empty_storage_returns_empty_list(self, demo_posts):
        """get_all_posts returns an empty list when no posts exist."""
        from src.cms import get_all_posts
        assert get_all_posts() == []


class TestDeletePost:
    def test_removes_matching_post(self, admin_context, demo_posts):
        """delete_post drops the matching post_id, leaves others alone."""
        demo_posts[_DEMO_KEY] = [_make_post("abc", "Keep"), _make_post("xyz", "Remove")]
        from src.cms import delete_post
        delete_post("xyz")
        remaining = [p["post_id"] for p in demo_posts[_DEMO_KEY]]
        assert "xyz" not in remaining
        assert "abc" in remaining

    def test_missing_post_id_is_noop(self, admin_context, demo_posts):
        """delete_post on an unknown id leaves storage untouched."""
        demo_posts[_DEMO_KEY] = [_make_post("abc", "Keep")]
        from src.cms import delete_post
        delete_post("does-not-exist")
        assert [p["post_id"] for p in demo_posts[_DEMO_KEY]] == ["abc"]

    def test_rejects_non_admin(self, demo_posts):
        """delete_post raises PermissionError when caller is not admin."""
        demo_posts[_DEMO_KEY] = [_make_post("abc", "Keep")]
        from src.cms import delete_post
        with patch("src.cms.is_admin", return_value=False):
            with pytest.raises(PermissionError, match="admins"):
                delete_post("abc")
        # Storage was not touched.
        assert len(demo_posts[_DEMO_KEY]) == 1

    def test_delete_post_storage_error_is_logged_and_propagated(self, admin_context, caplog):
        """delete_post catches storage exceptions, logs them, and re-raises."""
        import logging
        with patch("src.cms.is_demo_mode", return_value=False), \
             patch("src.cms._get_write_connection", side_effect=Exception("Storage offline")):
            from src.cms import delete_post
            with caplog.at_level(logging.ERROR):
                with pytest.raises(Exception, match="Storage offline") as exc_info:
                    delete_post("abc")

                assert str(exc_info.value) == "Storage offline"

        assert "Could not delete CMS post: Storage offline" in caplog.text


# ── Unit tests against DuckDB backend paths ──────────────────────────────────

class TestDuckDBBackend:
    @patch("src.cms.is_demo_mode", return_value=False)
    @patch("src.cms.get_db_connection")
    def test_get_active_posts(self, mock_conn, mock_is_demo):
        """get_active_posts constructs expected query and unpacks DuckDB rows."""
        from src.cms import get_active_posts

        mock_cur = mock_conn.return_value.cursor.return_value.__enter__.return_value
        mock_cur.fetchall.return_value = [
            ("1", "guide", "Active", "Body", "Ref", "a@b.com", "time", "time")
        ]

        res = get_active_posts()
        assert len(res) == 1
        assert res[0]["post_id"] == "1"
        assert res[0]["title"] == "Active"

        # Verify the query executed
        mock_cur.execute.assert_called_once()
        query = mock_cur.execute.call_args[0][0]
        assert "SELECT post_id, post_type, title" in query
        assert "WHERE expires_at IS NULL OR expires_at > current_localtimestamp()" in query

    @patch("src.cms.is_demo_mode", return_value=False)
    @patch("src.cms.get_db_connection")
    def test_get_all_posts(self, mock_conn, mock_is_demo):
        """get_all_posts executes query without expiry filter and unpacks rows."""
        from src.cms import get_all_posts

        mock_cur = mock_conn.return_value.cursor.return_value.__enter__.return_value
        mock_cur.fetchall.return_value = [
            ("2", "announcement", "All", "Body", "Ref", "a@b.com", "time", "time")
        ]

        res = get_all_posts()
        assert len(res) == 1
        assert res[0]["post_id"] == "2"
        assert res[0]["title"] == "All"

        # Verify the query executed
        mock_cur.execute.assert_called_once()
        query = mock_cur.execute.call_args[0][0]
        assert "SELECT post_id, post_type, title" in query
        assert "WHERE expires_at" not in query # No filter applied

    @patch("src.cms._get_write_connection")
    @patch("src.cms.is_demo_mode", return_value=False)
    def test_create_post(self, mock_is_demo, mock_write_conn, admin_context):
        """create_post executes INSERT with correctly extracted params."""
        from src.cms import PostParams, create_post

        create_post(PostParams("guide", "Title", "Body", "table.ref", "admin@test.com", None))

        mock_write_conn.return_value.execute.assert_called_once()
        query = mock_write_conn.return_value.execute.call_args[0][0]
        params = mock_write_conn.return_value.execute.call_args[0][1]

        assert "INSERT INTO user_data.cms_posts" in query
        assert len(params) == 8
        assert params[1] == "guide"
        assert params[2] == "Title"
        assert params[4] == "table.ref"
        assert params[5] == "admin@test.com"

    @patch("src.cms._get_write_connection")
    @patch("src.cms.is_demo_mode", return_value=False)
    def test_delete_post(self, mock_is_demo, mock_write_conn, admin_context):
        """delete_post executes DELETE query for matching post_id."""
        from src.cms import delete_post

        delete_post("xyz-123")

        mock_write_conn.return_value.execute.assert_called_once()
        query = mock_write_conn.return_value.execute.call_args[0][0]
        params = mock_write_conn.return_value.execute.call_args[0][1]

        assert "DELETE FROM user_data.cms_posts WHERE post_id = ?" in query
        assert params == ["xyz-123"]


# ── AppTest: discovery tab banner rendering ──────────────────────────────────
# These tests exercise the full app via DEMO_DATA=true, which routes through
# the demo (session-state) path. They're integration tests, not unit tests —
# the goal is to verify the wiring all the way to the rendered HTML.

class TestCmsBannerUI:
    def _discovery_app(self, groups, *, with_post=False):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.session_state["authenticated"] = True
        at.session_state["user_groups"] = groups
        at.session_state["user_name"] = "Test User"
        at.session_state["user_email"] = "user@test.com"
        if with_post:
            now = datetime.now(UTC)
            at.session_state["_demo_cms_posts"] = [{
                "post_id": "test-post",
                "post_type": "announcement",
                "title": "Test Announcement",
                "body": "Body here",
                "table_ref": None,
                "author_email": "admin@test.com",
                "created_at": now,
                "expires_at": now + timedelta(days=2),
            }]
        at.query_params["tab"] = "discovery"
        return at

    def test_banner_empty_when_no_posts(self, monkeypatch):
        """Discovery tab renders without error when no CMS posts exist."""
        monkeypatch.setenv("DEMO_DATA", "true")
        at = self._discovery_app(["finance_group", "SELECT_ALL_USERS"], with_post=False)
        at.run()
        assert not at.exception, f"Exception: {at.exception}"

    def test_banner_shows_post_title(self, monkeypatch):
        """Active CMS post title appears on the discovery tab."""
        monkeypatch.setenv("DEMO_DATA", "true")
        at = self._discovery_app(["finance_group", "SELECT_ALL_USERS"], with_post=True)
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        all_md = " ".join(m.value for m in at.markdown)
        assert "Test Announcement" in all_md

    def test_admin_sees_delete_button(self, monkeypatch):
        """Admin user sees the ✕ delete button alongside a CMS post."""
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        at = self._discovery_app([ADMIN_GROUP, "finance_group"], with_post=True)
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        delete_btns = [b for b in at.button if b.label == "✕"]
        assert len(delete_btns) >= 1, "Admin should see ✕ delete button for CMS post"

def test_get_active_posts_exception(caplog):
    """get_active_posts catches exceptions, logs them, and returns an empty list."""
    import logging
    from unittest.mock import patch
    with patch("src.cms.is_demo_mode", return_value=False), \
         patch("src.cms.get_db_connection") as mock_conn:
        mock_cur = mock_conn.return_value.cursor.return_value.__enter__.return_value
        mock_cur.execute.side_effect = Exception("Storage offline")

        from src.cms import get_active_posts

        with caplog.at_level(logging.WARNING):
            posts = get_active_posts()

        assert posts == []
        assert "Could not load CMS posts: Storage offline" in caplog.text

def test_get_all_posts_exception(caplog):
    """get_all_posts catches exceptions, logs them, and returns an empty list."""
    import logging
    from unittest.mock import patch
    with patch("src.cms.is_demo_mode", return_value=False), \
         patch("src.cms.get_db_connection") as mock_conn:
        mock_cur = mock_conn.return_value.cursor.return_value.__enter__.return_value
        mock_cur.execute.side_effect = Exception("Storage offline")

        from src.cms import get_all_posts

        with caplog.at_level(logging.WARNING):
            posts = get_all_posts()

        assert posts == []
        assert "Could not load CMS posts (admin): Storage offline" in caplog.text
