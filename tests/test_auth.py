"""
Tests for role-based access control (RBAC) functions in auth.py.

Coverage:
  - is_admin: False when ADMIN_GROUPS unset
  - is_admin: False when user's groups don't match
  - is_admin: True when user's group matches ADMIN_GROUPS
  - is_admin: True with comma-separated ADMIN_GROUPS
"""
from __future__ import annotations

from src.auth import is_admin

ADMIN_GROUP = "admin_group_id"
STANDARD_GROUP = "finance_group"


class TestIsAdmin:
    def test_false_when_env_unset(self, monkeypatch):
        """is_admin returns False when ADMIN_GROUPS is not set."""
        monkeypatch.delenv("ADMIN_GROUPS", raising=False)
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": [ADMIN_GROUP]})
        assert is_admin() is False

    def test_false_when_group_absent(self, monkeypatch):
        """is_admin returns False when user's groups don't overlap."""
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": [STANDARD_GROUP]})
        assert is_admin() is False

    def test_true_when_group_matches(self, monkeypatch):
        """is_admin returns True when user belongs to ADMIN_GROUPS."""
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": [ADMIN_GROUP, STANDARD_GROUP]})
        assert is_admin() is True

    def test_true_with_multiple_admin_groups(self, monkeypatch):
        """is_admin works with comma-separated ADMIN_GROUPS."""
        monkeypatch.setenv("ADMIN_GROUPS", f"other_group,{ADMIN_GROUP}")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": [ADMIN_GROUP]})
        assert is_admin() is True
