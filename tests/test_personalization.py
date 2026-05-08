"""Tests for src/personalization.py.

The DB plumbing has moved into ``src.storage.preference_storage`` (covered
by ``tests/test_storage_preferences.py``). These tests focus on the
higher-level concerns owned by ``src/personalization.py``:

- ``_user_oid`` resolution order (oid → email → 'anonymous')
- routing the public API through the injected ``PreferenceStorage``
- ``_sync_prefs_to_session`` populates ``st.session_state``
"""

from __future__ import annotations

from unittest.mock import patch

import streamlit as st

from src.personalization import (
    _pref_delete,
    _pref_load,
    _pref_upsert,
    _sync_prefs_to_session,
    _user_oid,
)
from src.storage.preference_storage import FakePreferenceStorage


class TestUserOid:
    def test_user_oid_from_oid(self):
        st.session_state.clear()
        st.session_state["user_oid"] = "123-oid"
        st.session_state["user_email"] = "test@example.com"
        assert _user_oid() == "123-oid"

    def test_user_oid_from_email(self):
        st.session_state.clear()
        st.session_state["user_email"] = "test@example.com"
        assert _user_oid() == "test@example.com"

    def test_user_oid_anonymous(self):
        st.session_state.clear()
        assert _user_oid() == "anonymous"


class TestPrefRouting:
    """The wrapper functions delegate to the injected storage backend."""

    def test_upsert_routes_to_storage(self):
        st.session_state.clear()
        st.session_state["user_oid"] = "u1"
        fake = FakePreferenceStorage()
        with patch("src.personalization.get_preference_storage", return_value=fake):
            _pref_upsert("cat.sch.tbl", "bookmark")
        assert fake.list_by_type("u1", "bookmark") == ["cat.sch.tbl"]

    def test_delete_routes_to_storage(self):
        st.session_state.clear()
        st.session_state["user_oid"] = "u1"
        fake = FakePreferenceStorage()
        fake.upsert("u1", "cat.sch.tbl", "bookmark")
        with patch("src.personalization.get_preference_storage", return_value=fake):
            _pref_delete("cat.sch.tbl", "bookmark")
        assert fake.list_by_type("u1", "bookmark") == []

    def test_load_routes_to_storage(self):
        st.session_state.clear()
        st.session_state["user_oid"] = "u1"
        fake = FakePreferenceStorage()
        fake.upsert("u1", "a.b.c", "bookmark")
        fake.upsert("u1", "d.e.f", "bookmark")
        with patch("src.personalization.get_preference_storage", return_value=fake):
            result = _pref_load("bookmark")
        # Newest-first ordering preserved by FakePreferenceStorage.
        assert result == ["d.e.f", "a.b.c"]

    def test_load_passes_limit(self):
        st.session_state.clear()
        st.session_state["user_oid"] = "u1"
        fake = FakePreferenceStorage()
        for tbl in ("a", "b", "c", "d", "e"):
            fake.upsert("u1", tbl, "recent")
        with patch("src.personalization.get_preference_storage", return_value=fake):
            result = _pref_load("recent", limit=2)
        assert result == ["e", "d"]


class TestSyncPrefsToSession:
    def test_sync_populates_session_state(self):
        st.session_state.clear()
        st.session_state["user_oid"] = "u1"
        fake = FakePreferenceStorage()
        fake.upsert("u1", "table_1", "bookmark")
        fake.upsert("u1", "col_1", "col_bookmark")
        fake.upsert("u1", "table_2", "recent")
        fake.upsert("u1", "table_3", "recent")

        with patch("src.personalization.get_preference_storage", return_value=fake):
            _sync_prefs_to_session()

        assert st.session_state.bookmarks == {"table_1"}
        assert st.session_state.col_bookmarks == {"col_1"}
        # recent_views is a list (recency order), not a set.
        assert st.session_state.recent_views == ["table_3", "table_2"]

from src.personalization import is_editing_enabled, set_editing_enabled, is_power_user

class FakeSiteSettingStorage:
    def __init__(self):
        self._store = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str, actor_email: str) -> None:
        self._store[key] = value

class TestEditingEnabled:
    def test_is_editing_enabled_cached(self):
        st.session_state.clear()
        st.session_state["_editing_enabled_cache"] = False
        fake = FakeSiteSettingStorage()
        fake.set("editing_enabled", "1", "admin")
        with patch("src.personalization.get_site_setting_storage", return_value=fake):
            # Should return cached False, not "1" from fake
            assert is_editing_enabled() is False

    def test_is_editing_enabled_not_cached_db_1(self):
        st.session_state.clear()
        fake = FakeSiteSettingStorage()
        fake.set("editing_enabled", "1", "admin")
        with patch("src.personalization.get_site_setting_storage", return_value=fake):
            assert is_editing_enabled() is True
            assert st.session_state["_editing_enabled_cache"] is True

    def test_is_editing_enabled_not_cached_db_0(self):
        st.session_state.clear()
        fake = FakeSiteSettingStorage()
        fake.set("editing_enabled", "0", "admin")
        with patch("src.personalization.get_site_setting_storage", return_value=fake):
            assert is_editing_enabled() is False
            assert st.session_state["_editing_enabled_cache"] is False

    def test_is_editing_enabled_not_cached_db_none(self):
        st.session_state.clear()
        fake = FakeSiteSettingStorage()
        with patch("src.personalization.get_site_setting_storage", return_value=fake):
            assert is_editing_enabled() is True
            assert st.session_state["_editing_enabled_cache"] is True

class TestSetEditingEnabled:
    def test_set_editing_enabled_true(self):
        st.session_state.clear()
        fake = FakeSiteSettingStorage()
        with patch("src.personalization.is_admin", return_value=True), \
             patch("src.personalization.get_site_setting_storage", return_value=fake):
            set_editing_enabled(True, "admin@example.com")
            assert fake.get("editing_enabled") == "1"
            assert st.session_state["_editing_enabled_cache"] is True

    def test_set_editing_enabled_false(self):
        st.session_state.clear()
        fake = FakeSiteSettingStorage()
        with patch("src.personalization.is_admin", return_value=True), \
             patch("src.personalization.get_site_setting_storage", return_value=fake):
            set_editing_enabled(False, "admin@example.com")
            assert fake.get("editing_enabled") == "0"
            assert st.session_state["_editing_enabled_cache"] is False

class TestPowerUser:
    def test_is_power_user_editing_disabled(self):
        st.session_state.clear()
        st.session_state["_editing_enabled_cache"] = False
        assert is_power_user() is False

    def test_is_power_user_no_editor_groups(self):
        st.session_state.clear()
        st.session_state["_editing_enabled_cache"] = True
        with patch("os.getenv", return_value=""):
            assert is_power_user() is False

    def test_is_power_user_no_matching_groups(self):
        st.session_state.clear()
        st.session_state["_editing_enabled_cache"] = True
        st.session_state["user_groups"] = ["reader", "viewer"]
        with patch("os.getenv", return_value="admin,editor"):
            assert is_power_user() is False

    def test_is_power_user_matching_groups(self):
        st.session_state.clear()
        st.session_state["_editing_enabled_cache"] = True
        st.session_state["user_groups"] = ["reader", "editor"]
        with patch("os.getenv", return_value="admin, editor "):
            assert is_power_user() is True
