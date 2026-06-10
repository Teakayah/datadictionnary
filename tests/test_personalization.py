"""Tests for src/personalization.py.

Covers the concerns owned by ``src/personalization.py``:

- ``_user_oid`` resolution order (oid → email → 'anonymous')
- demo mode short-circuits (no DB access)
- the DuckDB read path for ``_pref_load``
- ``_sync_prefs_to_session`` populates ``st.session_state``
- editing-toggle caching + admin gate
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import streamlit as st

from src.personalization import (
    _pref_delete,
    _pref_load,
    _pref_upsert,
    _sync_prefs_to_session,
    _user_oid,
    is_editing_enabled,
    is_power_user,
    set_editing_enabled,
)


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


def _mock_read_conn(rows_df):
    """Build a get_db_connection() mock whose cursor returns ``rows_df``."""
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall_as_pandas.return_value = rows_df
    return conn


class TestPrefDemoMode:
    """Demo mode is a no-op — preferences never touch the database."""

    def test_upsert_skips_db(self):
        st.session_state.clear()
        with patch("src.personalization.is_demo_mode", return_value=True), \
             patch("src.personalization.get_db_connection") as mock_conn:
            _pref_upsert("cat.sch.tbl", "bookmark")
        mock_conn.assert_not_called()

    def test_delete_skips_db(self):
        st.session_state.clear()
        with patch("src.personalization.is_demo_mode", return_value=True), \
             patch("src.personalization.get_db_connection") as mock_conn:
            _pref_delete("cat.sch.tbl", "bookmark")
        mock_conn.assert_not_called()

    def test_load_returns_empty(self):
        st.session_state.clear()
        with patch("src.personalization.is_demo_mode", return_value=True), \
             patch("src.personalization.get_db_connection") as mock_conn:
            assert _pref_load("bookmark") == []
        mock_conn.assert_not_called()


class TestPrefDuckDBPath:
    def test_upsert_writes_row(self):
        st.session_state.clear()
        st.session_state["user_oid"] = "u1"
        conn = MagicMock()
        with patch("src.personalization.is_demo_mode", return_value=False), \
             patch("src.personalization.get_db_connection", return_value=conn):
            _pref_upsert("cat.sch.tbl", "bookmark")
        sql, params = conn.execute.call_args[0]
        assert "INSERT INTO user_data.user_preferences" in sql
        assert params == ["u1", "cat.sch.tbl", "bookmark"]

    def test_delete_removes_row(self):
        st.session_state.clear()
        st.session_state["user_oid"] = "u1"
        conn = MagicMock()
        with patch("src.personalization.is_demo_mode", return_value=False), \
             patch("src.personalization.get_db_connection", return_value=conn):
            _pref_delete("cat.sch.tbl", "bookmark")
        sql, params = conn.execute.call_args[0]
        assert "DELETE FROM user_data.user_preferences" in sql
        assert params == ["u1", "cat.sch.tbl", "bookmark"]

    def test_load_returns_names_and_passes_limit(self):
        st.session_state.clear()
        st.session_state["user_oid"] = "u1"
        conn = _mock_read_conn(pd.DataFrame({"table_full_name": ["e", "d"]}))
        with patch("src.personalization.is_demo_mode", return_value=False), \
             patch("src.personalization.get_db_connection", return_value=conn):
            result = _pref_load("recent", limit=2)
        assert result == ["e", "d"]
        cur = conn.cursor.return_value.__enter__.return_value
        _, params = cur.execute.call_args[0]
        assert params == {"oid": "u1", "type": "recent", "lim": 2}

    def test_load_swallows_db_error(self):
        st.session_state.clear()
        with patch("src.personalization.is_demo_mode", return_value=False), \
             patch("src.personalization.get_db_connection",
                   side_effect=Exception("DB down")):
            assert _pref_load("bookmark") == []


class TestSyncPrefsToSession:
    def test_sync_populates_session_state(self):
        st.session_state.clear()

        def fake_load(pref_type, limit=20):
            return {
                "bookmark": ["table_1"],
                "col_bookmark": ["col_1"],
                "recent": ["table_3", "table_2"],
            }[pref_type]

        with patch("src.personalization._pref_load", side_effect=fake_load):
            _sync_prefs_to_session()

        assert st.session_state.bookmarks == {"table_1"}
        assert st.session_state.col_bookmarks == {"col_1"}
        # recent_views is a list (recency order), not a set.
        assert st.session_state.recent_views == ["table_3", "table_2"]


class TestEditingEnabled:
    def test_is_editing_enabled_cached(self):
        st.session_state.pop("_editing_enabled_cache", None)
        st.session_state["_editing_enabled_cache"] = False
        with patch("src.personalization._get_site_setting", return_value="1"):
            # Should return cached False, not "1" from the backend
            assert is_editing_enabled() is False

    def test_is_editing_enabled_not_cached_db_1(self):
        st.session_state.pop("_editing_enabled_cache", None)
        with patch("src.personalization._get_site_setting", return_value="1"):
            assert is_editing_enabled() is True
            assert st.session_state["_editing_enabled_cache"] is True

    def test_is_editing_enabled_not_cached_db_0(self):
        st.session_state.pop("_editing_enabled_cache", None)
        with patch("src.personalization._get_site_setting", return_value="0"):
            assert is_editing_enabled() is False
            assert st.session_state["_editing_enabled_cache"] is False

    def test_is_editing_enabled_not_cached_db_none(self):
        st.session_state.pop("_editing_enabled_cache", None)
        with patch("src.personalization._get_site_setting", return_value=None):
            assert is_editing_enabled() is True
            assert st.session_state["_editing_enabled_cache"] is True

    def test_is_editing_enabled_not_cached_db_invalid(self):
        st.session_state.pop("_editing_enabled_cache", None)
        with patch("src.personalization._get_site_setting", return_value="invalid"):
            assert is_editing_enabled() is False
            assert st.session_state["_editing_enabled_cache"] is False

    def test_demo_mode_defaults_to_enabled(self):
        st.session_state.pop("_editing_enabled_cache", None)
        with patch("src.personalization.is_demo_mode", return_value=True):
            assert is_editing_enabled() is True


class TestSetEditingEnabled:
    def test_set_editing_enabled_not_admin(self):
        st.session_state.clear()
        with patch("src.personalization.is_admin", return_value=False):
            with pytest.raises(PermissionError, match="Only admins can toggle the editing flag."):
                set_editing_enabled(True, "user@example.com")

    def test_set_editing_enabled_true(self):
        st.session_state.clear()
        with patch("src.personalization.is_admin", return_value=True), \
             patch("src.personalization._set_site_setting") as mock_set:
            set_editing_enabled(True, "admin@example.com")
        mock_set.assert_called_once_with("editing_enabled", "1", "admin@example.com")
        assert st.session_state["_editing_enabled_cache"] is True

    def test_set_editing_enabled_false(self):
        st.session_state.clear()
        with patch("src.personalization.is_admin", return_value=True), \
             patch("src.personalization._set_site_setting") as mock_set:
            set_editing_enabled(False, "admin@example.com")
        mock_set.assert_called_once_with("editing_enabled", "0", "admin@example.com")
        assert st.session_state["_editing_enabled_cache"] is False

    def test_set_editing_enabled_demo_mode_updates_cache(self):
        """Demo mode: the persist step is a no-op but the cache still flips."""
        st.session_state.clear()
        with patch("src.personalization.is_admin", return_value=True), \
             patch("src.personalization.is_demo_mode", return_value=True):
            set_editing_enabled(False, "admin@example.com")
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

    def test_is_power_user_missing_user_groups_in_session(self):
        st.session_state.clear()
        st.session_state["_editing_enabled_cache"] = True
        # user_groups is missing entirely from session state
        with patch("os.getenv", return_value="admin,editor"):
            assert is_power_user() is False

    def test_is_power_user_empty_user_groups(self):
        st.session_state.clear()
        st.session_state["_editing_enabled_cache"] = True
        st.session_state["user_groups"] = []
        with patch("os.getenv", return_value="admin,editor"):
            assert is_power_user() is False
