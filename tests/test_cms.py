"""
Tests for the CMS data layer + discovery banner.

Coverage:
  - Storage layer (FakeCMSStorage):
      * create_post writes a post with expected fields
      * create_post with expiry_days=None leaves expires_at None
      * get_active_posts filters expired posts
      * get_active_posts includes never-expiry posts
      * delete_post removes the matching post_id
  - AppTest: discovery banner renders, admin sees delete button.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.storage.cms_storage import FakeCMSStorage

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")
ADMIN_GROUP = "admin_group_id"


# ── Unit tests against FakeCMSStorage via the public src.cms API ─────────────

class TestCreatePost:
    def test_writes_post_with_expected_fields(self):
        """create_post round-trips through the injected storage."""
        fake = FakeCMSStorage()
        with patch("src.cms.get_cms_storage", return_value=fake):
            from src.cms import create_post
            create_post("announcement", "Hello", "Body text", None, "admin@test.com", 2)
        assert len(fake.posts) == 1
        assert fake.posts[0]["title"] == "Hello"
        assert fake.posts[0]["post_type"] == "announcement"
        assert fake.posts[0]["expires_at"] is not None

    def test_never_expiry_sets_none(self):
        """create_post with expiry_days=None leaves expires_at as None."""
        fake = FakeCMSStorage()
        with patch("src.cms.get_cms_storage", return_value=fake):
            from src.cms import create_post
            create_post("guide", "Guide", "", None, "admin@test.com", None)
        assert fake.posts[0]["expires_at"] is None


class TestGetActivePosts:
    def test_filters_expired_posts(self):
        """get_active_posts excludes posts whose expires_at is in the past."""
        now = datetime.now(UTC)
        fake = FakeCMSStorage([
            {"post_id": "1", "post_type": "announcement", "title": "Live",
             "body": "", "table_ref": None, "author_email": "a@b.com",
             "created_at": now, "expires_at": now + timedelta(days=1)},
            {"post_id": "2", "post_type": "announcement", "title": "Expired",
             "body": "", "table_ref": None, "author_email": "a@b.com",
             "created_at": now - timedelta(days=3),
             "expires_at": now - timedelta(days=1)},
        ])
        with patch("src.cms.get_cms_storage", return_value=fake):
            from src.cms import get_active_posts
            posts = get_active_posts()
        titles = [p["title"] for p in posts]
        assert "Live" in titles
        assert "Expired" not in titles

    def test_returns_never_expiry_posts(self):
        """get_active_posts includes posts with expires_at=None."""
        now = datetime.now(UTC)
        fake = FakeCMSStorage([
            {"post_id": "3", "post_type": "guide", "title": "Permanent",
             "body": "", "table_ref": None, "author_email": "a@b.com",
             "created_at": now, "expires_at": None},
        ])
        with patch("src.cms.get_cms_storage", return_value=fake):
            from src.cms import get_active_posts
            posts = get_active_posts()
        assert any(p["title"] == "Permanent" for p in posts)


class TestDeletePost:
    def test_removes_matching_post(self):
        """delete_post drops the matching post_id, leaves others alone."""
        fake = FakeCMSStorage([
            {"post_id": "abc", "title": "Keep", "post_type": "guide",
             "body": "", "table_ref": None, "author_email": "x",
             "created_at": datetime.now(UTC), "expires_at": None},
            {"post_id": "xyz", "title": "Remove", "post_type": "guide",
             "body": "", "table_ref": None, "author_email": "x",
             "created_at": datetime.now(UTC), "expires_at": None},
        ])
        with patch("src.cms.get_cms_storage", return_value=fake):
            from src.cms import delete_post
            delete_post("xyz")
        remaining = [p["post_id"] for p in fake.posts]
        assert "xyz" not in remaining
        assert "abc" in remaining

    def test_missing_post_id_is_noop(self):
        """delete_post on an unknown id leaves storage untouched."""
        fake = FakeCMSStorage([
            {"post_id": "abc", "title": "Keep", "post_type": "guide",
             "body": "", "table_ref": None, "author_email": "x",
             "created_at": datetime.now(UTC), "expires_at": None},
        ])
        with patch("src.cms.get_cms_storage", return_value=fake):
            from src.cms import delete_post
            delete_post("does-not-exist")
        assert [p["post_id"] for p in fake.posts] == ["abc"]


# ── AppTest: discovery tab banner rendering ──────────────────────────────────
# These tests exercise the full app via DEMO_DATA=true, which routes through
# DemoCMSStorage (session-state). They're integration tests, not unit tests,
# so we don't inject FakeCMSStorage here — the goal is to verify the wiring
# all the way from get_cms_storage() to the rendered HTML.

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
