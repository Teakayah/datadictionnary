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

    def test_false_when_env_only_commas(self, monkeypatch):
        """is_admin returns False when ADMIN_GROUPS contains only commas and spaces."""
        monkeypatch.setenv("ADMIN_GROUPS", " , ,, ")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["any_group"]})
        assert is_admin() is False

    def test_case_sensitivity(self, monkeypatch):
        """is_admin is case-sensitive when matching groups."""
        monkeypatch.setenv("ADMIN_GROUPS", "Admin_Group")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["admin_group"]})
        assert is_admin() is False


class TestIsPowerUserAuth:
    """Tests src.personalization.is_power_user.
    """
    def test_false_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("EDITOR_GROUPS", raising=False)
        monkeypatch.setattr("src.personalization.st.session_state", {"user_groups": ["editor_group"]})
        monkeypatch.setattr("src.personalization.is_editing_enabled", lambda: True)
        assert is_power_user() is False

    def test_false_when_env_empty(self, monkeypatch):
        monkeypatch.setenv("EDITOR_GROUPS", "")
        monkeypatch.setattr("src.personalization.st.session_state", {"user_groups": ["editor_group"]})
        monkeypatch.setattr("src.personalization.is_editing_enabled", lambda: True)
        assert is_power_user() is False

    def test_false_when_no_session_groups(self, monkeypatch):
        monkeypatch.setenv("EDITOR_GROUPS", "editor_group")
        monkeypatch.setattr("src.personalization.st.session_state", {})
        monkeypatch.setattr("src.personalization.is_editing_enabled", lambda: True)
        assert is_power_user() is False

    def test_false_when_groups_empty(self, monkeypatch):
        monkeypatch.setenv("EDITOR_GROUPS", "editor_group")
        monkeypatch.setattr("src.personalization.st.session_state", {"user_groups": []})
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

    def test_true_with_multiple_env_groups(self, monkeypatch):
        monkeypatch.setenv("EDITOR_GROUPS", "  editor-group1  ,  editor-group2  ")
        monkeypatch.setattr("src.personalization.st.session_state", {"user_groups": ["editor-group1"]})
        monkeypatch.setattr("src.personalization.is_editing_enabled", lambda: True)
        assert is_power_user() is True


class MockSessionState(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)
    def __setattr__(self, key, value):
        self[key] = value
    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(key)

from unittest.mock import MagicMock, patch

class TestClearAuthSession:
    def test_clears_session_keys(self, monkeypatch):
        from src.auth import _clear_auth_session
        import src.auth as auth_mod

        st_mock = MagicMock()
        monkeypatch.setattr(auth_mod, "st", st_mock)
        session = MockSessionState({
            "auth_token": "token",
            "token_expires_at": 1234,
            "authenticated": True,
            "user_groups": ["group"],
            "user_name": "Name",
            "user_email": "email@test.com",
            "user_oid": "oid123",
            "oauth_state": "state",
            "oauth_nonce": "nonce",
            "_prefs_loaded": True,
            "other_key": "keep_this"
        })
        monkeypatch.setattr("src.auth.st.session_state", session)

        mock_clear = MagicMock()
        monkeypatch.setattr("src.auth_graph.clear_groups_cache", mock_clear)

        _clear_auth_session()

        mock_clear.assert_called_once_with("oid123")
        for key in ("auth_token", "token_expires_at", "authenticated",
                    "user_groups", "user_name", "user_email", "user_oid",
                    "oauth_state", "oauth_nonce", "_prefs_loaded"):
            assert key not in session
        assert session["other_key"] == "keep_this"

    def test_no_oid_no_clear_cache(self, monkeypatch):
        from src.auth import _clear_auth_session

        session = MockSessionState({"auth_token": "token"})
        monkeypatch.setattr("src.auth.st.session_state", session)

        mock_clear = MagicMock()
        monkeypatch.setattr("src.auth_graph.clear_groups_cache", mock_clear)

        _clear_auth_session()

        mock_clear.assert_not_called()
        assert "auth_token" not in session

class TestTrySilentRefresh:
    @patch("src.auth.get_msal_app")
    def test_refresh_success(self, mock_get_msal, monkeypatch):
        from src.auth import _try_silent_refresh
        import src.auth as auth_mod

        mock_msal_app = MagicMock()
        mock_get_msal.return_value = mock_msal_app
        mock_msal_app.get_accounts.return_value = ["account1"]
        mock_msal_app.acquire_token_silent.return_value = {"access_token": "new_token", "expires_in": 3600}

        session = MockSessionState({"user_email": "test@test.com"})
        monkeypatch.setattr("src.auth.st.session_state", session)
        monkeypatch.setattr("src.auth.SCOPE", ["User.Read"])

        result = _try_silent_refresh()

        assert result is True
        assert session["auth_token"] == {"access_token": "new_token", "expires_in": 3600}

        mock_msal_app.get_accounts.assert_called_once_with(username="test@test.com")
        mock_msal_app.acquire_token_silent.assert_called_once_with(["User.Read"], account="account1")

    @patch("src.auth.get_msal_app")
    def test_no_accounts(self, mock_get_msal, monkeypatch):
        from src.auth import _try_silent_refresh

        mock_msal_app = MagicMock()
        mock_get_msal.return_value = mock_msal_app
        mock_msal_app.get_accounts.return_value = []

        session = MockSessionState({})
        monkeypatch.setattr("src.auth.st.session_state", session)

        result = _try_silent_refresh()

        assert result is False
        mock_msal_app.get_accounts.assert_called_once_with()
        mock_msal_app.acquire_token_silent.assert_not_called()

    @patch("src.auth.get_msal_app")
    def test_exception_caught(self, mock_get_msal, monkeypatch):
        from src.auth import _try_silent_refresh

        mock_msal_app = MagicMock()
        mock_get_msal.return_value = mock_msal_app
        mock_msal_app.get_accounts.side_effect = Exception("msal error")

        session = MockSessionState({})
        monkeypatch.setattr("src.auth.st.session_state", session)

        result = _try_silent_refresh()

        assert result is False

class TestCheckAuth:
    @patch("src.auth.time")
    @patch("src.auth.st.rerun")
    def test_existing_valid_session(self, mock_rerun, mock_time, monkeypatch):
        from src.auth import check_auth

        session = MockSessionState({"auth_token": "token", "token_expires_at": 2000})
        monkeypatch.setattr("src.auth.st.session_state", session)
        monkeypatch.setattr("src.auth.TOKEN_REFRESH_BUFFER_S", 300)

        mock_time.time.return_value = 1000

        result = check_auth()
        assert result is None
        mock_rerun.assert_not_called()

    @patch("src.auth.time")
    @patch("src.auth._try_silent_refresh")
    @patch("src.auth.st.rerun")
    def test_expired_session_silent_refresh_success(self, mock_rerun, mock_refresh, mock_time, monkeypatch):
        from src.auth import check_auth

        session = MockSessionState({"auth_token": "token", "token_expires_at": 1000})
        monkeypatch.setattr("src.auth.st.session_state", session)
        monkeypatch.setattr("src.auth.TOKEN_REFRESH_BUFFER_S", 300)

        mock_time.time.return_value = 2000
        mock_refresh.return_value = True

        result = check_auth()
        assert result is None
        mock_rerun.assert_not_called()

    @patch("src.auth.time")
    @patch("src.auth._try_silent_refresh")
    @patch("src.auth._clear_auth_session")
    @patch("src.auth.render_signin_page")
    @patch("src.auth.st.rerun")
    @patch("src.auth.st.query_params")
    def test_expired_session_silent_refresh_fail(self, mock_qp, mock_rerun, mock_render, mock_clear, mock_refresh, mock_time, monkeypatch):
        from src.auth import check_auth

        session = MockSessionState({"auth_token": "token", "token_expires_at": 1000})
        monkeypatch.setattr("src.auth.st.session_state", session)
        monkeypatch.setattr("src.auth.TOKEN_REFRESH_BUFFER_S", 300)

        mock_time.time.return_value = 2000
        mock_refresh.return_value = False

        check_auth()

        mock_clear.assert_called_once()
        mock_qp.clear.assert_called_once()
        mock_rerun.assert_called_once()

    @patch("src.auth_graph.clear_groups_cache")
    @patch("src.auth.time")
    @patch("src.auth._resolve_user_groups")
    @patch("src.auth.render_signin_page")
    @patch("src.auth.get_msal_app")
    @patch("src.auth.st.rerun")
    @patch("src.auth.st.query_params")
    def test_oidc_callback_success(self, mock_qp, mock_rerun, mock_get_msal, mock_render, mock_resolve_groups, mock_time, mock_clear_cache, monkeypatch):
        from src.auth import check_auth

        session = MockSessionState({
            "oauth_state": "expected_state",
            "oauth_nonce": "expected_nonce"
        })
        monkeypatch.setattr("src.auth.st.session_state", session)

        mock_qp.__contains__.return_value = True
        mock_qp.get.side_effect = lambda k, d=None: {"code": "auth_code", "state": "expected_state"}.get(k, d)

        mock_msal_app = MagicMock()
        mock_get_msal.return_value = mock_msal_app
        mock_msal_app.acquire_token_by_authorization_code.return_value = {
            "access_token": "token123",
            "expires_in": 3600,
            "id_token_claims": {
                "nonce": "expected_nonce",
                "oid": "user_oid",
                "name": "Test User",
                "email": "test@test.com"
            }
        }

        mock_time.time.return_value = 1000
        mock_resolve_groups.return_value = ["group1"]
        sync_prefs_mock = MagicMock()

        check_auth(sync_prefs_callback=sync_prefs_mock)

        mock_qp.clear.assert_called_once()
        mock_msal_app.acquire_token_by_authorization_code.assert_called_once()
        mock_clear_cache.assert_called_once_with("user_oid")

        assert session["auth_token"] == {"access_token": "token123", "expires_in": 3600, "id_token_claims": {"nonce": "expected_nonce", "oid": "user_oid", "name": "Test User", "email": "test@test.com"}}
        assert session["token_expires_at"] == 4600
        assert session["authenticated"] is True
        assert session["user_groups"] == ["group1"]
        assert session["user_name"] == "Test User"
        assert session["user_email"] == "test@test.com"
        assert session["user_oid"] == "user_oid"
        assert session["_prefs_loaded"] is True

        sync_prefs_mock.assert_called_once()
        mock_rerun.assert_called_once()

    @patch("src.auth.get_msal_app")
    @patch("src.auth.render_signin_page")
    @patch("src.auth.st.error")
    @patch("src.auth.st.query_params")
    def test_oidc_callback_state_mismatch(self, mock_qp, mock_error, mock_render, mock_get_msal, monkeypatch):
        from src.auth import check_auth
        import pytest

        session = MockSessionState({
            "oauth_state": "expected_state",
            "oauth_nonce": "expected_nonce"
        })
        monkeypatch.setattr("src.auth.st.session_state", session)
        monkeypatch.setattr("src.auth.t", lambda k: k)

        def mock_stop(): raise Exception("StopIteration")
        monkeypatch.setattr("src.auth.st.stop", mock_stop)

        mock_qp.__contains__.return_value = True
        mock_qp.get.side_effect = lambda k, d=None: {"code": "auth_code", "state": "wrong_state"}.get(k, d)

        with pytest.raises(Exception, match="StopIteration"):
            check_auth()

        mock_error.assert_called_once()

    @patch("src.auth.get_msal_app")
    @patch("src.auth.render_signin_page")
    @patch("src.auth.st.error")
    @patch("src.auth.st.query_params")
    def test_oidc_callback_failed_token(self, mock_qp, mock_error, mock_render, mock_get_msal, monkeypatch):
        from src.auth import check_auth
        import pytest

        session = MockSessionState({
            "oauth_state": "expected_state",
            "oauth_nonce": "expected_nonce"
        })
        monkeypatch.setattr("src.auth.st.session_state", session)
        monkeypatch.setattr("src.auth.t", lambda k: k)

        def mock_stop(): raise Exception("StopIteration")
        monkeypatch.setattr("src.auth.st.stop", mock_stop)

        mock_qp.__contains__.return_value = True
        mock_qp.get.side_effect = lambda k, d=None: {"code": "auth_code", "state": "expected_state"}.get(k, d)

        mock_msal_app = MagicMock()
        mock_get_msal.return_value = mock_msal_app
        mock_msal_app.acquire_token_by_authorization_code.return_value = {"error": "invalid_grant"}

        with pytest.raises(Exception, match="StopIteration"):
            check_auth()

        mock_error.assert_called_once()
