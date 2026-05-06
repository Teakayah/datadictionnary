"""
Tests for the pipelines tab and pipeline management.

Coverage:
  - is_pipeline_user: False when PIPELINE_GROUPS unset
  - is_pipeline_user: False when user's groups don't match
  - is_pipeline_user: True when user's group matches PIPELINE_GROUPS
  - get_pipelines: returns empty list when DuckDB unavailable
  - get_pipelines: returns demo session state pipelines
  - render_pipelines_page: access denied for non-pipeline, non-admin user
  - render_pipelines_page: renders for pipeline user
  - render_pipelines_page: admin can see pipelines tab
  - Nav: pipelines tab visible for pipeline user, hidden for standard user
"""
from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")
PIPELINE_GROUP = "pipeline_group_id"
ADMIN_GROUP    = "admin_group_id"
STANDARD_GROUP = "finance_group"


# ── Unit tests ────────────────────────────────────────────────────────────────

class TestIsPipelineUser:
    def test_false_when_env_unset(self, monkeypatch):
        """is_pipeline_user returns False when PIPELINE_GROUPS is not set."""
        monkeypatch.delenv("PIPELINE_GROUPS", raising=False)
        import streamlit as st
        st.session_state["user_groups"] = [PIPELINE_GROUP]
        from src.auth import is_pipeline_user
        assert is_pipeline_user() is False

    def test_false_when_group_absent(self, monkeypatch):
        """is_pipeline_user returns False when user's groups don't overlap."""
        monkeypatch.setenv("PIPELINE_GROUPS", PIPELINE_GROUP)
        import streamlit as st
        st.session_state["user_groups"] = [STANDARD_GROUP]
        from src.auth import is_pipeline_user
        assert is_pipeline_user() is False

    def test_true_when_group_matches(self, monkeypatch):
        """is_pipeline_user returns True when user belongs to PIPELINE_GROUPS."""
        monkeypatch.setenv("PIPELINE_GROUPS", PIPELINE_GROUP)
        import streamlit as st
        st.session_state["user_groups"] = [PIPELINE_GROUP, STANDARD_GROUP]
        from src.auth import is_pipeline_user
        assert is_pipeline_user() is True

    def test_true_with_multiple_pipeline_groups(self, monkeypatch):
        """is_pipeline_user works with comma-separated PIPELINE_GROUPS."""
        monkeypatch.setenv("PIPELINE_GROUPS", f"other_group,{PIPELINE_GROUP}")
        import streamlit as st
        st.session_state["user_groups"] = [PIPELINE_GROUP]
        from src.auth import is_pipeline_user
        assert is_pipeline_user() is True


class TestGetPipelines:
    def test_returns_empty_without_duckdb(self):
        """get_pipelines returns [] when DuckDB is unavailable and no demo data."""
        import streamlit as st
        st.session_state.pop("_demo_pipelines", None)
        with patch("src.pipelines._duckdb_available", return_value=False):
            from src.pipelines import get_pipelines
            result = get_pipelines()
        assert result == []

    def test_returns_demo_session_state(self):
        """get_pipelines returns _demo_pipelines from session state."""
        import streamlit as st
        fake = [{"pipeline_id": "p1", "title": "My Job", "description": "desc",
                 "backend": "databricks", "databricks_job_id": "42",
                 "adf_subscription_id": None, "adf_resource_group": None,
                 "adf_factory_name": None, "adf_pipeline_name": None,
                 "ado_organization": None, "ado_project": None,
                 "ado_pipeline_id": None, "created_by": "admin",
                 "created_at": datetime.utcnow()}]
        st.session_state["_demo_pipelines"] = fake
        with patch("src.pipelines._duckdb_available", return_value=False):
            from src.pipelines import get_pipelines
            result = get_pipelines()
        assert len(result) == 1
        assert result[0]["title"] == "My Job"


# ── AppTest: pipelines page rendering ─────────────────────────────────────────

class TestPipelinesPageUI:
    def _make_app(self, groups, *, tab="pipelines"):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.session_state["authenticated"] = True
        at.session_state["user_groups"] = groups
        at.session_state["user_name"] = "Test User"
        at.session_state["user_email"] = "test@test.com"
        at.query_params["tab"] = tab
        return at

    def test_access_denied_for_standard_user(self, monkeypatch):
        """Standard user with no pipeline group sees access denied."""
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("PIPELINE_GROUPS", PIPELINE_GROUP)
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        at = self._make_app([STANDARD_GROUP])
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        error_texts = [e.value for e in at.error]
        assert any("Pipeline access required" in t for t in error_texts)

    def test_pipeline_user_can_access(self, monkeypatch):
        """Pipeline user sees the pipelines page without access denied."""
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("PIPELINE_GROUPS", PIPELINE_GROUP)
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        at = self._make_app([PIPELINE_GROUP])
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        error_texts = [e.value for e in at.error]
        assert not any("Pipeline access required" in t for t in error_texts)

    def test_admin_can_access_pipelines(self, monkeypatch):
        """Admin user can access the pipelines page even without PIPELINE_GROUPS."""
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("PIPELINE_GROUPS", PIPELINE_GROUP)
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        at = self._make_app([ADMIN_GROUP])
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        error_texts = [e.value for e in at.error]
        assert not any("Pipeline access required" in t for t in error_texts)

    def test_pipelines_tab_visible_for_pipeline_user(self, monkeypatch):
        """Pipelines nav button is rendered for pipeline group members."""
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("PIPELINE_GROUPS", PIPELINE_GROUP)
        at = self._make_app([PIPELINE_GROUP], tab="search")
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        nav_btn_labels = [b.label for b in at.button]
        assert "Pipelines" in nav_btn_labels

    def test_pipelines_tab_hidden_for_standard_user(self, monkeypatch):
        """Pipelines nav button is not rendered for standard users."""
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("PIPELINE_GROUPS", PIPELINE_GROUP)
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        at = self._make_app([STANDARD_GROUP], tab="search")
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        nav_btn_labels = [b.label for b in at.button]
        assert "Pipelines" not in nav_btn_labels
