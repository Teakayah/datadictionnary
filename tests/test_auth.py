"""
Tests for src/auth.py RBAC functions.

This module provides focused unit tests for is_pipeline_user(), is_admin(),
and is_power_user().
"""

from __future__ import annotations

import pytest

from src.auth import is_pipeline_user, is_admin
from src.personalization import is_power_user

@pytest.fixture(autouse=True)
def mock_session_state(monkeypatch):
    """Ensure st.session_state is clean for each test and mocked safely."""
    monkeypatch.setattr("src.auth.st.session_state", {})
    monkeypatch.setattr("src.personalization.st.session_state", {})

class TestIsPipelineUser:
    def test_false_when_env_unset(self, monkeypatch):
        """is_pipeline_user returns False when PIPELINE_GROUPS is not set."""
        monkeypatch.delenv("PIPELINE_GROUPS", raising=False)
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["any_group"]})
        assert is_pipeline_user() is False

    def test_false_when_env_empty(self, monkeypatch):
        """is_pipeline_user returns False when PIPELINE_GROUPS is empty string."""
        monkeypatch.setenv("PIPELINE_GROUPS", "")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["any_group"]})
        assert is_pipeline_user() is False

    def test_false_when_no_session_groups(self, monkeypatch):
        """is_pipeline_user returns False when user_groups is missing from session."""
        monkeypatch.setenv("PIPELINE_GROUPS", "pipe_group")
        monkeypatch.setattr("src.auth.st.session_state", {})
        assert is_pipeline_user() is False

    def test_false_when_groups_empty(self, monkeypatch):
        """is_pipeline_user returns False when user_groups is an empty list."""
        monkeypatch.setenv("PIPELINE_GROUPS", "pipe_group")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": []})
        assert is_pipeline_user() is False

    def test_false_when_no_matching_groups(self, monkeypatch):
        """is_pipeline_user returns False when user's groups don't overlap with PIPELINE_GROUPS."""
        monkeypatch.setenv("PIPELINE_GROUPS", "pipe_group")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["standard_user_group"]})
        assert is_pipeline_user() is False

    def test_false_when_user_groups_is_none(self, monkeypatch):
        """is_pipeline_user returns False when user_groups in session state is explicitly None."""
        monkeypatch.setenv("PIPELINE_GROUPS", "pipe_group")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": None})
        assert is_pipeline_user() is False

    def test_true_when_group_matches(self, monkeypatch):
        """is_pipeline_user returns True when user belongs to PIPELINE_GROUPS."""
        monkeypatch.setenv("PIPELINE_GROUPS", "pipe_group")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["pipe_group", "other_group"]})
        assert is_pipeline_user() is True

    def test_true_with_multiple_env_groups(self, monkeypatch):
        """is_pipeline_user works with comma-separated PIPELINE_GROUPS."""
        monkeypatch.setenv("PIPELINE_GROUPS", "other_group, pipe_group ")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["pipe_group"]})
        assert is_pipeline_user() is True


class TestIsAdmin:
    def test_false_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("ADMIN_GROUPS", raising=False)
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["admin_group"]})
        assert is_admin() is False

    def test_false_when_env_empty(self, monkeypatch):
        """is_admin returns False when ADMIN_GROUPS is empty string."""
        monkeypatch.setenv("ADMIN_GROUPS", "")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["any_group"]})
        assert is_admin() is False

    def test_false_when_no_session_groups(self, monkeypatch):
        """is_admin returns False when user_groups is missing from session."""
        monkeypatch.setenv("ADMIN_GROUPS", "admin_group")
        monkeypatch.setattr("src.auth.st.session_state", {})
        assert is_admin() is False

    def test_false_when_groups_empty(self, monkeypatch):
        """is_admin returns False when user_groups is an empty list."""
        monkeypatch.setenv("ADMIN_GROUPS", "admin_group")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": []})
        assert is_admin() is False

    def test_false_when_no_match(self, monkeypatch):
        monkeypatch.setenv("ADMIN_GROUPS", "admin_group")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["other_group"]})
        assert is_admin() is False

    def test_true_when_group_matches(self, monkeypatch):
        monkeypatch.setenv("ADMIN_GROUPS", "admin_group")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["admin_group"]})
        assert is_admin() is True

    def test_true_with_multiple_admin_groups(self, monkeypatch):
        """is_admin works with comma-separated ADMIN_GROUPS."""
        monkeypatch.setenv("ADMIN_GROUPS", "  admin-group1  ,  admin-group2  ")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["admin-group1"]})
        assert is_admin() is True


class TestIsPowerUserAuth:
    """Tests src.personalization.is_power_user.
    """
    def test_false_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("EDITOR_GROUPS", raising=False)
        monkeypatch.setattr("src.personalization.st.session_state", {"user_groups": ["editor_group"]})
        monkeypatch.setattr("src.personalization.is_editing_enabled", lambda: True)
        assert is_power_user() is False

    def test_false_when_no_match(self, monkeypatch):
        monkeypatch.setenv("EDITOR_GROUPS", "editor_group")
        monkeypatch.setattr("src.personalization.st.session_state", {"user_groups": ["other_group"]})
        monkeypatch.setattr("src.personalization.is_editing_enabled", lambda: True)
        assert is_power_user() is False

    def test_false_when_editing_disabled(self, monkeypatch):
        monkeypatch.setenv("EDITOR_GROUPS", "editor_group")
        monkeypatch.setattr("src.personalization.st.session_state", {"user_groups": ["editor_group"]})
        monkeypatch.setattr("src.personalization.is_editing_enabled", lambda: False)
        assert is_power_user() is False

    def test_true_when_group_matches_and_editing_enabled(self, monkeypatch):
        monkeypatch.setenv("EDITOR_GROUPS", "editor_group")
        monkeypatch.setattr("src.personalization.st.session_state", {"user_groups": ["editor_group"]})
        monkeypatch.setattr("src.personalization.is_editing_enabled", lambda: True)
        assert is_power_user() is True
