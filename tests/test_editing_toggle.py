"""
Tests for the global editing toggle.

Coverage:
  - is_editing_enabled: defaults True when DuckDB unavailable
  - is_editing_enabled: reads cached value from session state
  - set_editing_enabled: updates session cache
  - is_power_user: returns False when editing disabled, True when enabled + group matches
  - Admin page: toggle section renders for admin user
"""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")
ADMIN_GROUP = "admin_group_id"
EDITOR_GROUP = "editor_group_id"


# ── Unit tests for is_editing_enabled / set_editing_enabled ──────────────────

class TestIsEditingEnabled:
    def test_defaults_true_when_storage_returns_none(self):
        """Returns True when the site-settings backend has no row yet."""
        import streamlit as st
        from src.personalization import is_editing_enabled
        from src.storage.preference_storage import FakeSiteSettingStorage
        st.session_state.pop("_editing_enabled_cache", None)
        with patch(
            "src.personalization.get_site_setting_storage",
            return_value=FakeSiteSettingStorage(),
        ):
            assert is_editing_enabled() is True

    def test_reads_disabled_from_storage(self):
        """Returns False when site_settings holds value='0'."""
        import streamlit as st
        from src.personalization import is_editing_enabled
        from src.storage.preference_storage import FakeSiteSettingStorage
        st.session_state.pop("_editing_enabled_cache", None)
        with patch(
            "src.personalization.get_site_setting_storage",
            return_value=FakeSiteSettingStorage({"editing_enabled": "0"}),
        ):
            assert is_editing_enabled() is False

    def test_returns_cached_value(self):
        """Returns cached session state value without hitting the backend."""
        import streamlit as st
        from src.personalization import is_editing_enabled
        st.session_state["_editing_enabled_cache"] = False
        assert is_editing_enabled() is False
        st.session_state["_editing_enabled_cache"] = True
        assert is_editing_enabled() is True

    def test_set_editing_enabled_updates_cache_and_storage(self):
        """set_editing_enabled writes to both the storage and the session cache."""
        import streamlit as st
        from src.personalization import set_editing_enabled
        from src.storage.preference_storage import FakeSiteSettingStorage
        fake = FakeSiteSettingStorage()
        with patch("src.personalization.is_admin", return_value=True), \
             patch(
                 "src.personalization.get_site_setting_storage", return_value=fake,
             ):
            set_editing_enabled(False, "admin@test.com")
            assert st.session_state.get("_editing_enabled_cache") is False
            assert fake.values["editing_enabled"] == "0"
            set_editing_enabled(True, "admin@test.com")
            assert st.session_state.get("_editing_enabled_cache") is True
            assert fake.values["editing_enabled"] == "1"

    def test_set_editing_enabled_rejects_non_admin(self):
        """Non-admin caller gets PermissionError; storage unchanged."""
        from src.personalization import set_editing_enabled
        from src.storage.preference_storage import FakeSiteSettingStorage
        fake = FakeSiteSettingStorage()
        with patch("src.personalization.is_admin", return_value=False), \
             patch(
                 "src.personalization.get_site_setting_storage", return_value=fake,
             ):
            with pytest.raises(PermissionError, match="admins"):
                set_editing_enabled(False, "rando@test.com")
        assert fake.values == {}


class TestIsPowerUserGate:
    def test_power_user_false_when_editing_disabled(self, monkeypatch):
        """is_power_user returns False when editing is globally off."""
        monkeypatch.setenv("EDITOR_GROUPS", EDITOR_GROUP)
        import streamlit as st
        st.session_state["user_groups"] = [EDITOR_GROUP]
        st.session_state["_editing_enabled_cache"] = False
        from src.personalization import is_power_user
        assert is_power_user() is False

    def test_power_user_true_when_editing_enabled_and_group_matches(self, monkeypatch):
        """is_power_user returns True when editing on and user is in EDITOR_GROUPS."""
        monkeypatch.setenv("EDITOR_GROUPS", EDITOR_GROUP)
        import streamlit as st
        st.session_state["user_groups"] = [EDITOR_GROUP]
        st.session_state["_editing_enabled_cache"] = True
        from src.personalization import is_power_user
        assert is_power_user() is True

    def test_power_user_false_when_group_absent(self, monkeypatch):
        """is_power_user returns False when user's groups don't match EDITOR_GROUPS."""
        monkeypatch.setenv("EDITOR_GROUPS", EDITOR_GROUP)
        import streamlit as st
        st.session_state["user_groups"] = ["other_group"]
        st.session_state["_editing_enabled_cache"] = True
        from src.personalization import is_power_user
        assert is_power_user() is False


# ── AppTest: admin page renders editing toggle section ────────────────────────

class TestAdminEditingToggleUI:
    def test_admin_page_has_editing_section(self, monkeypatch):
        """Admin page renders the inline editing toggle."""
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        monkeypatch.setenv("DEMO_DATA", "true")
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.session_state["authenticated"] = True
        at.session_state["user_groups"] = [ADMIN_GROUP]
        at.session_state["user_name"] = "Admin"
        at.session_state["user_email"] = "admin@test.com"
        at.query_params["tab"] = "admin"
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        # Toggle widget should be present
        assert any(t.label == "Allow power users to edit metadata" for t in at.toggle), \
            "Editing toggle not found on admin page"
