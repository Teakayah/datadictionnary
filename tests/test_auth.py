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
        monkeypatch.setenv("ENABLE_PIPELINES", "true")
        monkeypatch.setenv("PIPELINE_GROUPS", "pipe_group")
        monkeypatch.setattr("src.auth.st.session_state", {"user_groups": ["pipe_group", "other_group"]})
        assert is_pipeline_user() is True

    def test_true_with_multiple_env_groups(self, monkeypatch):
        """is_pipeline_user works with comma-separated PIPELINE_GROUPS."""
        monkeypatch.setenv("ENABLE_PIPELINES", "true")
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

class TestResolveUserGroups:
    def test_inline_groups_returns_list(self):
        from src.auth import _resolve_user_groups
        claims = {"groups": ["g1", "g2"]}
        assert _resolve_user_groups(claims, "token") == ["g1", "g2"]

    @patch("src.auth_graph.has_groups_overage")
    @patch("src.auth_graph.fetch_member_groups")
    def test_overage_fetches_from_graph(self, mock_fetch, mock_has_overage):
        from src.auth import _resolve_user_groups
        mock_has_overage.return_value = True
        mock_fetch.return_value = ["g3", "g4"]
        claims = {"oid": "user123"}

        result = _resolve_user_groups(claims, "token")

        assert result == ["g3", "g4"]
        mock_has_overage.assert_called_once_with(claims)
        mock_fetch.assert_called_once_with("token", "user123")

    @patch("src.auth_graph.has_groups_overage")
    def test_no_groups_claim_and_no_overage_returns_empty(self, mock_has_overage):
        from src.auth import _resolve_user_groups
        mock_has_overage.return_value = False
        claims = {}

        result = _resolve_user_groups(claims, "token")

        assert result == []
        mock_has_overage.assert_called_once_with(claims)


class TestGetCatalogStats:
    @patch("src.config.is_demo_mode")
    def test_demo_mode(self, mock_demo_mode):
        from src.auth import _get_catalog_stats
        mock_demo_mode.return_value = True
        with patch("src.demo.data._DEMO_TABLES") as mock_demo_tables:
            mock_demo_tables.__len__.return_value = 10
            mock_demo_tables.__getitem__.return_value.nunique.return_value = 5

            result = _get_catalog_stats()
            assert result == ("10", "5")

    @patch("src.config.is_demo_mode")
    @patch("src.db.queries.run_query")
    def test_live_mode_success(self, mock_run_query, mock_demo_mode):
        from src.auth import _get_catalog_stats
        mock_demo_mode.return_value = False
        import pandas as pd
        mock_run_query.side_effect = [
            pd.DataFrame({"n": [100]}),
            pd.DataFrame({"n": [20]})
        ]

        result = _get_catalog_stats()
        assert result == ("100", "20")

    @patch("src.config.is_demo_mode")
    @patch("src.db.queries.run_query")
    def test_live_mode_empty_results(self, mock_run_query, mock_demo_mode):
        from src.auth import _get_catalog_stats
        mock_demo_mode.return_value = False
        import pandas as pd
        mock_run_query.side_effect = [
            pd.DataFrame(),
            pd.DataFrame()
        ]

        result = _get_catalog_stats()
        assert result == ("—", "—")

    @patch("src.config.is_demo_mode")
    def test_exception_returns_fallback(self, mock_demo_mode):
        from src.auth import _get_catalog_stats
        mock_demo_mode.side_effect = Exception("DB error")

        result = _get_catalog_stats()
        assert result == ("—", "—")


class TestRenderSigninPage:
    @patch("src.auth.st.columns")
    @patch("src.auth.st.markdown")
    @patch("src.auth._get_catalog_stats")
    @patch("src.auth.t", lambda k: k)
    def test_render_signin_page_live(self, mock_get_stats, mock_markdown, mock_columns):
        from src.auth import render_signin_page
        col_hero = MagicMock()
        col_card = MagicMock()
        mock_columns.return_value = [col_hero, col_card]
        mock_get_stats.return_value = ("100", "10")

        # We need to simulate the "with" context manager
        col_hero.__enter__ = MagicMock(return_value=col_hero)
        col_hero.__exit__ = MagicMock(return_value=None)
        col_card.__enter__ = MagicMock(return_value=col_card)
        col_card.__exit__ = MagicMock(return_value=None)

        render_signin_page(auth_url="https://auth.example.com", mock=False)

        mock_columns.assert_called_once_with([1.1, 0.9], gap="large")
        mock_get_stats.assert_called_once()
        assert mock_markdown.call_count == 5

    @patch("src.auth.st.columns")
    @patch("src.auth.st.markdown")
    @patch("src.auth.st.selectbox")
    @patch("src.auth.st.button")
    @patch("src.auth.st.rerun")
    @patch("src.auth._get_catalog_stats")
    @patch("src.auth.st.session_state", new_callable=MockSessionState)
    @patch("src.auth.t", lambda k: k)
    def test_render_signin_page_mock_mode_submit(self, mock_session, mock_get_stats, mock_rerun, mock_button, mock_selectbox, mock_markdown, mock_columns):
        from src.auth import render_signin_page
        col_hero = MagicMock()
        col_card = MagicMock()
        mock_columns.return_value = [col_hero, col_card]
        mock_get_stats.return_value = ("100", "10")

        col_hero.__enter__ = MagicMock(return_value=col_hero)
        col_hero.__exit__ = MagicMock(return_value=None)
        col_card.__enter__ = MagicMock(return_value=col_card)
        col_card.__exit__ = MagicMock(return_value=None)

        mock_selectbox.return_value = "Finance"
        mock_button.return_value = True

        render_signin_page(mock=True)

        mock_selectbox.assert_called_once()
        mock_button.assert_called_once()
        assert mock_session["authenticated"] is True
        assert mock_session["user_groups"] == ["finance_group", "SELECT_ALL_USERS"]
        assert mock_session["user_name"] == "Finance User"
        assert mock_session["user_email"] == "finance.user@research-org.ca"
        mock_rerun.assert_called_once()


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
    @patch("src.auth.st.rerun")
    @patch("src.auth.st.query_params")
    def test_expired_session_silent_refresh_fail(self, mock_qp, mock_rerun, mock_clear, mock_refresh, mock_time, monkeypatch):
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
    @patch("src.auth.get_msal_app")
    @patch("src.auth.st.rerun")
    @patch("src.auth.st.query_params")
    def test_oidc_callback_success(self, mock_qp, mock_rerun, mock_get_msal, mock_resolve_groups, mock_time, mock_clear_cache, monkeypatch):
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

        with patch("src.personalization._sync_prefs_to_session") as sync_prefs_mock:
            check_auth()

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
    @patch("src.auth.st.error")
    @patch("src.auth.st.query_params")
    def test_oidc_callback_state_mismatch(self, mock_qp, mock_error, mock_get_msal, monkeypatch):
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
    @patch("src.auth.st.error")
    @patch("src.auth.st.query_params")
    def test_oidc_callback_failed_token(self, mock_qp, mock_error, mock_get_msal, monkeypatch):
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

    @patch("src.auth.get_msal_app")
    @patch("src.auth.st.error")
    @patch("src.auth.st.query_params")
    def test_oidc_callback_nonce_mismatch(self, mock_qp, mock_error, mock_get_msal, monkeypatch):
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
        mock_msal_app.acquire_token_by_authorization_code.return_value = {
            "access_token": "token",
            "id_token_claims": {
                "nonce": "wrong_nonce"
            }
        }

        with pytest.raises(Exception, match="StopIteration"):
            check_auth()

        mock_error.assert_called_once()

class TestParseGroups:
    def test_empty_string(self):
        """_parse_groups returns empty frozenset for empty string."""
        from src.auth import _parse_groups
        assert _parse_groups("") == frozenset()

    def test_none_value(self):
        """_parse_groups returns empty frozenset for None."""
        from src.auth import _parse_groups
        assert _parse_groups(None) == frozenset()

    def test_single_group(self):
        """_parse_groups parses a single group correctly."""
        from src.auth import _parse_groups
        assert _parse_groups("admin_group") == frozenset({"admin_group"})

    def test_multiple_groups(self):
        """_parse_groups parses multiple comma-separated groups."""
        from src.auth import _parse_groups
        assert _parse_groups("admin,user,editor") == frozenset({"admin", "user", "editor"})

    def test_whitespace_handling(self):
        """_parse_groups strips leading and trailing whitespace."""
        from src.auth import _parse_groups
        assert _parse_groups(" admin , user  ,  editor ") == frozenset({"admin", "user", "editor"})

    def test_empty_items(self):
        """_parse_groups ignores empty items between commas."""
        from src.auth import _parse_groups
        assert _parse_groups("admin,,user, ,editor,") == frozenset({"admin", "user", "editor"})
