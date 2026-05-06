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
    def test_defaults_true_without_duckdb(self):
        """Returns True when DuckDB is unavailable (no DB file)."""
        with patch("src.personalization._duckdb_available", return_value=False):
            import streamlit as st
            with patch.object(type(st.session_state), "__contains__", return_value=False):
                from src.personalization import is_editing_enabled
                # Clear any cached value
                for key in list(st.session_state.keys()):
                    if key == "_editing_enabled_cache":
                        del st.session_state[key]
                result = is_editing_enabled()
        assert result is True

    def test_returns_cached_value(self):
        """Returns cached session state value without hitting DB."""
        import streamlit as st
        from src.personalization import is_editing_enabled
        st.session_state["_editing_enabled_cache"] = False
        assert is_editing_enabled() is False
        st.session_state["_editing_enabled_cache"] = True
        assert is_editing_enabled() is True

    def test_set_editing_enabled_updates_cache(self):
        """set_editing_enabled updates the session state cache immediately."""
        import streamlit as st
        from src.personalization import set_editing_enabled
        with patch("src.personalization._duckdb_available", return_value=False):
            set_editing_enabled(False, "admin@test.com")
            assert st.session_state.get("_editing_enabled_cache") is False
            set_editing_enabled(True, "admin@test.com")
            assert st.session_state.get("_editing_enabled_cache") is True


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
