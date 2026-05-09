"""Tests for src/auth.py role-based access control (RBAC) functions."""

import os
import pytest
import streamlit as st
from unittest.mock import patch

from src.auth import is_pipeline_user, is_admin

class TestIsPipelineUser:
    def test_false_when_env_unset(self, monkeypatch):
        """is_pipeline_user returns False when PIPELINE_GROUPS is not set."""
        monkeypatch.delenv("PIPELINE_GROUPS", raising=False)
        st.session_state["user_groups"] = ["pipeline_group_id"]
        assert is_pipeline_user() is False

    def test_false_when_env_empty(self, monkeypatch):
        """is_pipeline_user returns False when PIPELINE_GROUPS is empty or whitespace."""
        monkeypatch.setenv("PIPELINE_GROUPS", "   ,  ")
        st.session_state["user_groups"] = ["pipeline_group_id"]
        assert is_pipeline_user() is False

    def test_false_when_group_absent(self, monkeypatch):
        """is_pipeline_user returns False when user's groups don't overlap."""
        monkeypatch.setenv("PIPELINE_GROUPS", "pipeline_group_id")
        st.session_state["user_groups"] = ["finance_group"]
        assert is_pipeline_user() is False

    def test_false_when_session_groups_missing(self, monkeypatch):
        """is_pipeline_user returns False when user_groups is missing from session state."""
        monkeypatch.setenv("PIPELINE_GROUPS", "pipeline_group_id")
        if "user_groups" in st.session_state:
            del st.session_state["user_groups"]
        assert is_pipeline_user() is False

    def test_true_when_group_matches(self, monkeypatch):
        """is_pipeline_user returns True when user belongs to PIPELINE_GROUPS."""
        monkeypatch.setenv("PIPELINE_GROUPS", "pipeline_group_id")
        st.session_state["user_groups"] = ["pipeline_group_id", "finance_group"]
        assert is_pipeline_user() is True

    def test_true_with_multiple_pipeline_groups(self, monkeypatch):
        """is_pipeline_user works with comma-separated PIPELINE_GROUPS."""
        monkeypatch.setenv("PIPELINE_GROUPS", "other_group, pipeline_group_id ")
        st.session_state["user_groups"] = ["pipeline_group_id"]
        assert is_pipeline_user() is True

class TestIsAdmin:
    def test_false_when_env_unset(self, monkeypatch):
        """is_admin returns False when ADMIN_GROUPS is not set."""
        monkeypatch.delenv("ADMIN_GROUPS", raising=False)
        st.session_state["user_groups"] = ["admin_group_id"]
        assert is_admin() is False

    def test_false_when_env_empty(self, monkeypatch):
        """is_admin returns False when ADMIN_GROUPS is empty or whitespace."""
        monkeypatch.setenv("ADMIN_GROUPS", "   ,  ")
        st.session_state["user_groups"] = ["admin_group_id"]
        assert is_admin() is False

    def test_false_when_group_absent(self, monkeypatch):
        """is_admin returns False when user's groups don't overlap."""
        monkeypatch.setenv("ADMIN_GROUPS", "admin_group_id")
        st.session_state["user_groups"] = ["finance_group"]
        assert is_admin() is False

    def test_false_when_session_groups_missing(self, monkeypatch):
        """is_admin returns False when user_groups is missing from session state."""
        monkeypatch.setenv("ADMIN_GROUPS", "admin_group_id")
        if "user_groups" in st.session_state:
            del st.session_state["user_groups"]
        assert is_admin() is False

    def test_true_when_group_matches(self, monkeypatch):
        """is_admin returns True when user belongs to ADMIN_GROUPS."""
        monkeypatch.setenv("ADMIN_GROUPS", "admin_group_id")
        st.session_state["user_groups"] = ["admin_group_id", "finance_group"]
        assert is_admin() is True

    def test_true_with_multiple_admin_groups(self, monkeypatch):
        """is_admin works with comma-separated ADMIN_GROUPS."""
        monkeypatch.setenv("ADMIN_GROUPS", "other_group, admin_group_id ")
        st.session_state["user_groups"] = ["admin_group_id"]
        assert is_admin() is True
