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
