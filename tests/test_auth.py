"""
Tests for src/auth.py RBAC functions.

This module provides focused unit tests for is_pipeline_user(), is_admin(),
and is_power_user().
"""

from __future__ import annotations

import os
import streamlit as st
import pytest

from src.auth import is_pipeline_user, is_admin, is_power_user

@pytest.fixture(autouse=True)
def clear_session_state():
    """Ensure st.session_state is clean for each test."""
    st.session_state.clear()
    yield
    st.session_state.clear()

class TestIsPipelineUser:
    def test_false_when_env_unset(self, monkeypatch):
        """is_pipeline_user returns False when PIPELINE_GROUPS is not set."""
        monkeypatch.delenv("PIPELINE_GROUPS", raising=False)
        st.session_state["user_groups"] = ["any_group"]
        assert is_pipeline_user() is False

    def test_false_when_env_empty(self, monkeypatch):
        """is_pipeline_user returns False when PIPELINE_GROUPS is empty string."""
        monkeypatch.setenv("PIPELINE_GROUPS", "")
        st.session_state["user_groups"] = ["any_group"]
        assert is_pipeline_user() is False

    def test_false_when_no_session_groups(self, monkeypatch):
        """is_pipeline_user returns False when user_groups is missing from session."""
        monkeypatch.setenv("PIPELINE_GROUPS", "pipe_group")
        # st.session_state.clear() via fixture
        assert is_pipeline_user() is False

    def test_false_when_groups_empty(self, monkeypatch):
        """is_pipeline_user returns False when user_groups is an empty list."""
        monkeypatch.setenv("PIPELINE_GROUPS", "pipe_group")
        st.session_state["user_groups"] = []
        assert is_pipeline_user() is False

    def test_false_when_no_matching_groups(self, monkeypatch):
        """is_pipeline_user returns False when user's groups don't overlap with PIPELINE_GROUPS."""
        monkeypatch.setenv("PIPELINE_GROUPS", "pipe_group")
        st.session_state["user_groups"] = ["standard_user_group"]
        assert is_pipeline_user() is False

    def test_true_when_group_matches(self, monkeypatch):
        """is_pipeline_user returns True when user belongs to PIPELINE_GROUPS."""
        monkeypatch.setenv("PIPELINE_GROUPS", "pipe_group")
        st.session_state["user_groups"] = ["pipe_group", "other_group"]
        assert is_pipeline_user() is True

    def test_true_with_multiple_env_groups(self, monkeypatch):
        """is_pipeline_user works with comma-separated PIPELINE_GROUPS."""
        monkeypatch.setenv("PIPELINE_GROUPS", "other_group, pipe_group ")
        st.session_state["user_groups"] = ["pipe_group"]
        assert is_pipeline_user() is True


class TestIsAdmin:
    def test_false_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("ADMIN_GROUPS", raising=False)
        st.session_state["user_groups"] = ["admin_group"]
        assert is_admin() is False

    def test_false_when_no_match(self, monkeypatch):
        monkeypatch.setenv("ADMIN_GROUPS", "admin_group")
        st.session_state["user_groups"] = ["other_group"]
        assert is_admin() is False

    def test_true_when_group_matches(self, monkeypatch):
        monkeypatch.setenv("ADMIN_GROUPS", "admin_group")
        st.session_state["user_groups"] = ["admin_group"]
        assert is_admin() is True


class TestIsPowerUserAuth:
    """Note: This tests src.auth.is_power_user, which does NOT check the global toggle.
    The toggled version is in src.personalization.py.
    """
    def test_false_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("EDITOR_GROUPS", raising=False)
        st.session_state["user_groups"] = ["editor_group"]
        assert is_power_user() is False

    def test_false_when_no_match(self, monkeypatch):
        monkeypatch.setenv("EDITOR_GROUPS", "editor_group")
        st.session_state["user_groups"] = ["other_group"]
        assert is_power_user() is False

    def test_true_when_group_matches(self, monkeypatch):
        monkeypatch.setenv("EDITOR_GROUPS", "editor_group")
        st.session_state["user_groups"] = ["editor_group"]
        assert is_power_user() is True
