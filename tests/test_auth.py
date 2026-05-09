"""Tests for src/auth.py."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from src.auth import is_admin

ADMIN_GROUP = "admin_group_id"
STANDARD_GROUP = "standard_group_id"


class TestIsAdmin:
    def test_false_when_env_unset(self):
        """is_admin returns False when ADMIN_GROUPS is not set."""
        with patch("os.getenv", return_value=""):
            with patch("src.auth.st.session_state", {"user_groups": [ADMIN_GROUP]}):
                assert is_admin() is False

    def test_false_when_group_absent(self):
        """is_admin returns False when user's groups don't overlap."""
        with patch("os.getenv", return_value=ADMIN_GROUP):
            with patch("src.auth.st.session_state", {"user_groups": [STANDARD_GROUP]}):
                assert is_admin() is False

    def test_true_when_group_matches(self):
        """is_admin returns True when user belongs to ADMIN_GROUPS."""
        with patch("os.getenv", return_value=ADMIN_GROUP):
            with patch("src.auth.st.session_state", {"user_groups": [ADMIN_GROUP, STANDARD_GROUP]}):
                assert is_admin() is True

    def test_true_with_multiple_admin_groups(self):
        """is_admin works with comma-separated ADMIN_GROUPS."""
        with patch("os.getenv", return_value=f"other_group,{ADMIN_GROUP}"):
            with patch("src.auth.st.session_state", {"user_groups": [ADMIN_GROUP]}):
                assert is_admin() is True

    def test_false_when_user_groups_empty(self):
        """is_admin returns False when user has no groups."""
        with patch("os.getenv", return_value=ADMIN_GROUP):
            with patch("src.auth.st.session_state", {"user_groups": []}):
                assert is_admin() is False
