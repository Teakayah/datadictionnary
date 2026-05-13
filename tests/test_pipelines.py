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
from datetime import UTC, datetime
from unittest.mock import patch, MagicMock

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
    def test_returns_empty_when_storage_empty(self):
        """get_pipelines returns [] for an empty storage backend."""
        from src.storage.pipeline_storage import FakePipelineDefStorage
        fake = FakePipelineDefStorage()
        with patch("src.pipelines.get_pipeline_def_storage", return_value=fake):
            from src.pipelines import get_pipelines
            assert get_pipelines() == []

    def test_returns_pipelines_from_storage(self):
        """get_pipelines returns whatever the def storage holds."""
        from src.storage.pipeline_storage import FakePipelineDefStorage
        fake = FakePipelineDefStorage([{
            "pipeline_id": "p1", "title": "My Job", "description": "desc",
            "backend": "databricks", "databricks_job_id": "42",
            "adf_subscription_id": None, "adf_resource_group": None,
            "adf_factory_name": None, "adf_pipeline_name": None,
            "ado_organization": None, "ado_project": None,
            "ado_pipeline_id": None, "created_by": "admin",
            "created_at": datetime.now(UTC),
        }])
        with patch("src.pipelines.get_pipeline_def_storage", return_value=fake):
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

# ── Execution tests ──────────────────────────────────────────────────────────

@pytest.fixture
def pipeline_caller_context():
    """Make is_pipeline_user() return True so trigger/cancel auth checks pass."""
    with patch("src.pipelines.is_pipeline_user", return_value=True), \
         patch("src.pipelines.is_admin", return_value=False):
        yield


@pytest.fixture
def admin_caller_context():
    """Make is_admin() return True so admin-only writes pass."""
    with patch("src.pipelines.is_admin", return_value=True):
        yield




class TestGetSpToken:
    def test_get_sp_token_success(self):
        from src.pipelines import _get_sp_token
        with patch("src.pipelines.PIPELINE_SP_TENANT_ID", "tenant"), \
             patch("src.pipelines.PIPELINE_SP_CLIENT_ID", "client"), \
             patch("src.pipelines.PIPELINE_SP_CLIENT_SECRET", "secret"), \
             patch("msal.ConfidentialClientApplication") as mock_msal:

            mock_app = MagicMock()
            mock_app.acquire_token_for_client.return_value = {"access_token": "fake-token"}
            mock_msal.return_value = mock_app

            token = _get_sp_token("my-resource")
            assert token == "fake-token"
            mock_app.acquire_token_for_client.assert_called_once_with(scopes=["my-resource/.default"])

    def test_get_sp_token_missing_creds(self):
        from src.pipelines import _get_sp_token
        with patch("src.pipelines.PIPELINE_SP_TENANT_ID", ""), \
             patch("src.pipelines.PIPELINE_SP_CLIENT_ID", "client"), \
             patch("src.pipelines.PIPELINE_SP_CLIENT_SECRET", "secret"):
             with pytest.raises(RuntimeError, match="credentials are not configured"):
                 _get_sp_token("res")

    def test_get_sp_token_failure(self):
        from src.pipelines import _get_sp_token
        with patch("src.pipelines.PIPELINE_SP_TENANT_ID", "tenant"), \
             patch("src.pipelines.PIPELINE_SP_CLIENT_ID", "client"), \
             patch("src.pipelines.PIPELINE_SP_CLIENT_SECRET", "secret"), \
             patch("msal.ConfidentialClientApplication") as mock_msal:

            mock_app = MagicMock()
            mock_app.acquire_token_for_client.return_value = {"error_description": "bad credentials"}
            mock_msal.return_value = mock_app

            with pytest.raises(RuntimeError, match="Failed to acquire pipeline SP token: bad credentials"):
                _get_sp_token("res")

    def test_get_sp_token_endswith_slash(self):
        from src.pipelines import _get_sp_token
        with patch("src.pipelines.PIPELINE_SP_TENANT_ID", "tenant"), \
             patch("src.pipelines.PIPELINE_SP_CLIENT_ID", "client"), \
             patch("src.pipelines.PIPELINE_SP_CLIENT_SECRET", "secret"), \
             patch("msal.ConfidentialClientApplication") as mock_msal:

            mock_app = MagicMock()
            mock_app.acquire_token_for_client.return_value = {"access_token": "fake-token"}
            mock_msal.return_value = mock_app

            token = _get_sp_token("my-resource/")
            assert token == "fake-token"
            mock_app.acquire_token_for_client.assert_called_once_with(scopes=["my-resource/.default"])

class TestTriggerBackends:
    @patch("requests.post")
    @patch("src.pipelines._get_sp_token")
    @patch("src.pipelines._save_run")
    def test_trigger_databricks_success(self, mock_save_run, mock_get_token, mock_post):
        from src.pipelines import _trigger_databricks
        mock_get_token.return_value = "fake-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"run_id": 12345}
        mock_post.return_value = mock_resp

        pipeline = {
            "pipeline_id": "pipe1",
            "databricks_job_id": "42"
        }

        _trigger_databricks(pipeline, "user1")

        mock_get_token.assert_called_once()
        mock_post.assert_called_once()
        mock_resp.raise_for_status.assert_called_once()
        mock_save_run.assert_called_once_with("pipe1", "12345", "user1")

    @patch("requests.post")
    @patch("src.pipelines._get_sp_token")
    @patch("src.pipelines._save_run")
    def test_trigger_adf_success(self, mock_save_run, mock_get_token, mock_post):
        from src.pipelines import _trigger_adf
        mock_get_token.return_value = "fake-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"runId": "adf-run-123"}
        mock_post.return_value = mock_resp

        pipeline = {
            "pipeline_id": "pipe2",
            "adf_subscription_id": "sub1",
            "adf_resource_group": "rg1",
            "adf_factory_name": "fact1",
            "adf_pipeline_name": "pipe_name_1"
        }

        _trigger_adf(pipeline, "user2")

        mock_get_token.assert_called_once()
        mock_post.assert_called_once()
        mock_resp.raise_for_status.assert_called_once()
        mock_save_run.assert_called_once_with("pipe2", "adf-run-123", "user2")

    @patch("requests.post")
    @patch("src.pipelines._get_sp_token")
    @patch("src.pipelines._save_run")
    def test_trigger_ado_success(self, mock_save_run, mock_get_token, mock_post):
        from src.pipelines import _trigger_ado
        mock_get_token.return_value = "fake-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 999}
        mock_post.return_value = mock_resp

        pipeline = {
            "pipeline_id": "pipe3",
            "ado_organization": "org1",
            "ado_project": "proj1",
            "ado_pipeline_id": "111"
        }

        _trigger_ado(pipeline, "user3")

        mock_get_token.assert_called_once()
        mock_post.assert_called_once()
        mock_resp.raise_for_status.assert_called_once()
        mock_save_run.assert_called_once_with("pipe3", "999", "user3")

class TestTriggerPipeline:
    @patch("src.pipelines._trigger_databricks")
    def test_trigger_pipeline_routes_to_databricks(self, mock_trigger, pipeline_caller_context):
        from src.pipelines import trigger_pipeline
        pipeline = {"backend": "databricks"}
        trigger_pipeline(pipeline, "user1")
        mock_trigger.assert_called_once_with(pipeline, "user1")

    @patch("src.pipelines._trigger_adf")
    def test_trigger_pipeline_routes_to_adf(self, mock_trigger, pipeline_caller_context):
        from src.pipelines import trigger_pipeline
        pipeline = {"backend": "adf"}
        trigger_pipeline(pipeline, "user2")
        mock_trigger.assert_called_once_with(pipeline, "user2")

    @patch("src.pipelines._trigger_ado")
    def test_trigger_pipeline_routes_to_ado(self, mock_trigger, pipeline_caller_context):
        from src.pipelines import trigger_pipeline
        pipeline = {"backend": "ado"}
        trigger_pipeline(pipeline, "user3")
        mock_trigger.assert_called_once_with(pipeline, "user3")

    def test_trigger_pipeline_raises_value_error_for_unknown_backend(self, pipeline_caller_context):
        from src.pipelines import trigger_pipeline
        with pytest.raises(ValueError, match="Unknown backend: unknown"):
            trigger_pipeline({"backend": "unknown"}, "user")

    def test_trigger_pipeline_rejects_non_pipeline_user(self):
        """Non-admin, non-pipeline user gets PermissionError before any backend call."""
        from src.pipelines import trigger_pipeline
        with patch("src.pipelines.is_pipeline_user", return_value=False), \
             patch("src.pipelines.is_admin", return_value=False), \
             patch("src.pipelines._trigger_databricks") as mock_trigger:
            with pytest.raises(PermissionError, match="pipeline users or admins"):
                trigger_pipeline({"backend": "databricks"}, "u")
        mock_trigger.assert_not_called()

class TestPollRunStatus:
    @patch("src.pipelines._status_databricks")
    @patch("src.pipelines._update_run")
    def test_poll_run_status_routes_to_databricks(self, mock_update, mock_status):
        from src.pipelines import poll_run_status
        pipeline = {"backend": "databricks", "pipeline_id": "p1"}
        run = {"backend_run_id": "r1"}
        mock_status.return_value = {"status": "success", "progress": 100, "message": "", "is_terminal": True}

        with patch("src.pipelines._clear_run") as mock_clear:
            result = poll_run_status(pipeline, run)

        mock_status.assert_called_once_with("r1")
        mock_update.assert_called_once_with("p1", "success")
        mock_clear.assert_called_once_with("p1")
        assert result["status"] == "success"

    @patch("src.pipelines._status_databricks")
    @patch("src.pipelines._update_run")
    def test_poll_run_status_handles_exception(self, mock_update, mock_status):
        from src.pipelines import poll_run_status
        pipeline = {"backend": "databricks", "pipeline_id": "p1"}
        run = {"backend_run_id": "r1", "status": "running"}
        mock_status.side_effect = Exception("Network timeout")

        result = poll_run_status(pipeline, run)

        mock_status.assert_called_once_with("r1")
        mock_update.assert_not_called()
        assert result["status"] == "running"
        assert result["message"] == "Network timeout"
        assert result["is_terminal"] is False

class TestCancelRun:
    @patch("src.pipelines._cancel_databricks")
    @patch("src.pipelines._clear_run")
    def test_cancel_run_routes_to_databricks(self, mock_clear, mock_cancel, pipeline_caller_context):
        from src.pipelines import cancel_run
        pipeline = {"backend": "databricks", "pipeline_id": "p1"}
        run = {"backend_run_id": "r1"}

        cancel_run(pipeline, run)

        mock_cancel.assert_called_once_with("r1")
        mock_clear.assert_called_once_with("p1")

    @patch("src.pipelines._cancel_databricks")
    @patch("src.pipelines._clear_run")
    def test_cancel_run_clears_even_on_exception(self, mock_clear, mock_cancel, pipeline_caller_context):
        from src.pipelines import cancel_run
        pipeline = {"backend": "databricks", "pipeline_id": "p1"}
        run = {"backend_run_id": "r1"}
        mock_cancel.side_effect = Exception("Failed")

        with pytest.raises(Exception, match="Failed"):
            cancel_run(pipeline, run)

        mock_cancel.assert_called_once_with("r1")
        mock_clear.assert_called_once_with("p1")

    def test_cancel_run_rejects_non_pipeline_user(self):
        """Non-admin, non-pipeline user can't cancel — backend never called."""
        from src.pipelines import cancel_run
        with patch("src.pipelines.is_pipeline_user", return_value=False), \
             patch("src.pipelines.is_admin", return_value=False), \
             patch("src.pipelines._cancel_databricks") as mock_cancel, \
             patch("src.pipelines._clear_run") as mock_clear:
            with pytest.raises(PermissionError, match="pipeline users or admins"):
                cancel_run({"backend": "databricks", "pipeline_id": "p1"},
                           {"backend_run_id": "r1"})
        mock_cancel.assert_not_called()
        mock_clear.assert_not_called()


class TestPipelineDefAdminGuards:
    """create_pipeline_def and delete_pipeline_def are admin-only."""

    def test_create_pipeline_def_rejects_non_admin(self):
        from src.pipelines import create_pipeline_def
        with patch("src.pipelines.is_admin", return_value=False), \
             patch("src.pipelines.get_pipeline_def_storage") as mock_storage:
            with pytest.raises(PermissionError, match="admins"):
                create_pipeline_def(
                    "title", "desc", "databricks", "42", None, None, None, None,
                    None, None, None, "u",
                )
        mock_storage.assert_not_called()

    def test_create_pipeline_def_admin_succeeds(self, admin_caller_context):
        from src.pipelines import create_pipeline_def
        from src.storage.pipeline_storage import FakePipelineDefStorage
        fake = FakePipelineDefStorage()
        with patch("src.pipelines.get_pipeline_def_storage", return_value=fake):
            create_pipeline_def(
                "My Pipe", "desc", "databricks", "42", None, None, None, None,
                None, None, None, "admin",
            )
        assert len(fake.list_all()) == 1
        assert fake.list_all()[0]["title"] == "My Pipe"

    def test_delete_pipeline_def_rejects_non_admin(self):
        from src.pipelines import delete_pipeline_def
        with patch("src.pipelines.is_admin", return_value=False), \
             patch("src.pipelines.get_pipeline_def_storage") as mock_def, \
             patch("src.pipelines.get_pipeline_run_storage") as mock_run:
            with pytest.raises(PermissionError, match="admins"):
                delete_pipeline_def("p1")
        mock_def.assert_not_called()
        mock_run.assert_not_called()

class TestGetSpToken:
    @patch("src.pipelines.PIPELINE_SP_TENANT_ID", "tenant")
    @patch("src.pipelines.PIPELINE_SP_CLIENT_ID", "client")
    @patch("src.pipelines.PIPELINE_SP_CLIENT_SECRET", "secret")
    @patch("msal.ConfidentialClientApplication")
    def test_get_sp_token_success(self, mock_msal):
        from src.pipelines import _get_sp_token

        mock_app = MagicMock()
        mock_msal.return_value = mock_app
        mock_app.acquire_token_for_client.return_value = {"access_token": "valid-token"}

        token = _get_sp_token("https://myresource")

        assert token == "valid-token"
        mock_msal.assert_called_once_with(
            "client",
            authority="https://login.microsoftonline.com/tenant",
            client_credential="secret"
        )
        mock_app.acquire_token_for_client.assert_called_once_with(scopes=["https://myresource/.default"])

    @patch("src.pipelines.PIPELINE_SP_TENANT_ID", "tenant")
    @patch("src.pipelines.PIPELINE_SP_CLIENT_ID", "client")
    @patch("src.pipelines.PIPELINE_SP_CLIENT_SECRET", "secret")
    @patch("msal.ConfidentialClientApplication")
    def test_get_sp_token_success_with_trailing_slash(self, mock_msal):
        from src.pipelines import _get_sp_token

        mock_app = MagicMock()
        mock_msal.return_value = mock_app
        mock_app.acquire_token_for_client.return_value = {"access_token": "valid-token"}

        token = _get_sp_token("https://myresource/")

        assert token == "valid-token"
        mock_app.acquire_token_for_client.assert_called_once_with(scopes=["https://myresource/.default"])

    @patch("src.pipelines.PIPELINE_SP_TENANT_ID", "")
    def test_get_sp_token_missing_config(self):
        from src.pipelines import _get_sp_token
        with pytest.raises(RuntimeError, match="Pipeline service principal credentials are not configured"):
            _get_sp_token("res")

    @patch("src.pipelines.PIPELINE_SP_TENANT_ID", "tenant")
    @patch("src.pipelines.PIPELINE_SP_CLIENT_ID", "client")
    @patch("src.pipelines.PIPELINE_SP_CLIENT_SECRET", "secret")
    @patch("msal.ConfidentialClientApplication")
    def test_get_sp_token_failure(self, mock_msal):
        from src.pipelines import _get_sp_token

        mock_app = MagicMock()
        mock_msal.return_value = mock_app
        mock_app.acquire_token_for_client.return_value = {"error": "invalid_client"}

        with pytest.raises(RuntimeError, match="Failed to acquire pipeline SP token: invalid_client"):
            _get_sp_token("res")


class TestRunStatePersistence:
    @patch("src.pipelines.get_pipeline_run_storage")
    def test_get_active_run(self, mock_get_storage):
        from src.pipelines import get_active_run
        mock_storage = MagicMock()
        mock_storage.get_active.return_value = {"status": "running"}
        mock_get_storage.return_value = mock_storage

        result = get_active_run("pipe1")

        mock_storage.get_active.assert_called_once_with("pipe1")
        assert result == {"status": "running"}

    @patch("src.pipelines.get_pipeline_run_storage")
    def test_save_run(self, mock_get_storage):
        from src.pipelines import _save_run
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        _save_run("pipe1", "run1", "user1")

        mock_storage.upsert.assert_called_once_with("pipe1", "run1", "user1")

    @patch("src.pipelines.get_pipeline_run_storage")
    def test_update_run(self, mock_get_storage):
        from src.pipelines import _update_run
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        _update_run("pipe1", "success")

        mock_storage.update_status.assert_called_once_with("pipe1", "success")

    @patch("src.pipelines.get_pipeline_run_storage")
    def test_clear_run(self, mock_get_storage):
        from src.pipelines import _clear_run
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        _clear_run("pipe1")

        mock_storage.clear.assert_called_once_with("pipe1")


class TestPollRunStatusUnknownBackend:
    @patch("src.pipelines._update_run")
    def test_poll_run_status_unknown_backend(self, mock_update):
        from src.pipelines import poll_run_status
        pipeline = {"backend": "unknown", "pipeline_id": "p1"}
        run = {"backend_run_id": "r1"}

        result = poll_run_status(pipeline, run)

        mock_update.assert_called_once_with("p1", "unknown")
        assert result["status"] == "unknown"
        assert result["progress"] == 0
        assert result["is_terminal"] is False


class TestStatusDatabricks:
    @patch("requests.get")
    @patch("src.pipelines._get_sp_token")
    def test_status_databricks_pending(self, mock_get_token, mock_get):
        from src.pipelines import _status_databricks
        mock_get_token.return_value = "fake-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "state": {
                "life_cycle_state": "PENDING",
                "state_message": "Waiting for resources"
            }
        }
        mock_get.return_value = mock_resp

        result = _status_databricks("run-123")
        assert result["status"] == "PENDING"
        assert result["progress"] == 10
        assert result["message"] == "Waiting for resources"
        assert result["is_terminal"] is False

    @patch("requests.get")
    @patch("src.pipelines._get_sp_token")
    def test_status_databricks_running_with_tasks(self, mock_get_token, mock_get):
        from src.pipelines import _status_databricks
        mock_get_token.return_value = "fake-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "state": {"life_cycle_state": "RUNNING"},
            "tasks": [
                {"state": {"life_cycle_state": "TERMINATED"}},
                {"state": {"life_cycle_state": "RUNNING"}},
                {"state": {"life_cycle_state": "PENDING"}},
                {"state": {"life_cycle_state": "TERMINATED"}}
            ]
        }
        mock_get.return_value = mock_resp

        result = _status_databricks("run-123")
        assert result["status"] == "RUNNING"
        # 2 out of 4 tasks TERMINATED -> 50% * 90 = 45 progress
        assert result["progress"] == 45
        assert result["is_terminal"] is False

    @patch("requests.get")
    @patch("src.pipelines._get_sp_token")
    def test_status_databricks_terminated(self, mock_get_token, mock_get):
        from src.pipelines import _status_databricks
        mock_get_token.return_value = "fake-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "state": {
                "life_cycle_state": "TERMINATED",
                "result_state": "SUCCESS"
            }
        }
        mock_get.return_value = mock_resp

        result = _status_databricks("run-123")
        assert result["status"] == "SUCCESS"
        assert result["progress"] == 100
        assert result["is_terminal"] is True


class TestCancelDatabricks:
    @patch("requests.post")
    @patch("src.pipelines._get_sp_token")
    def test_cancel_databricks_success(self, mock_get_token, mock_post):
        from src.pipelines import _cancel_databricks
        mock_get_token.return_value = "fake-token"
        mock_resp = MagicMock()
        mock_post.return_value = mock_resp

        _cancel_databricks("12345")

        mock_get_token.assert_called_once()
        mock_post.assert_called_once()
        mock_resp.raise_for_status.assert_called_once()

        args, kwargs = mock_post.call_args
        assert kwargs["json"] == {"run_id": 12345}
        assert "Authorization" in kwargs["headers"]
        assert kwargs["headers"]["Authorization"] == "Bearer fake-token"


class TestCancellationFunctions:
    @patch("requests.post")
    @patch("src.pipelines._get_sp_token", return_value="token")
    def test_cancel_adf(self, mock_get_token, mock_post):
        from src.pipelines import _cancel_adf
        mock_resp = MagicMock()
        mock_post.return_value = mock_resp

        pipeline = {
            "adf_subscription_id": "sub1",
            "adf_resource_group": "rg1",
            "adf_factory_name": "fact1"
        }
        _cancel_adf(pipeline, "run1")

        mock_post.assert_called_once()
        mock_resp.raise_for_status.assert_called_once()

    @patch("requests.patch")
    @patch("src.pipelines._get_sp_token", return_value="token")
    def test_cancel_ado(self, mock_get_token, mock_patch):
        from src.pipelines import _cancel_ado
        mock_resp = MagicMock()
        mock_patch.return_value = mock_resp

        pipeline = {
            "ado_organization": "org1",
            "ado_project": "proj1"
        }
        _cancel_ado(pipeline, "run1")

        mock_patch.assert_called_once()
        args, kwargs = mock_patch.call_args
        assert kwargs["json"] == {"status": "cancelling"}
        mock_resp.raise_for_status.assert_called_once()

    @patch("src.pipelines._cancel_adf")
    @patch("src.pipelines._clear_run")
    def test_cancel_run_routes_to_adf(self, mock_clear, mock_cancel, pipeline_caller_context):
        from src.pipelines import cancel_run
        pipeline = {"backend": "adf", "pipeline_id": "p1"}
        run = {"backend_run_id": "r1"}

        cancel_run(pipeline, run)

        mock_cancel.assert_called_once_with(pipeline, "r1")
        mock_clear.assert_called_once_with("p1")

    @patch("src.pipelines._cancel_ado")
    @patch("src.pipelines._clear_run")
    def test_cancel_run_routes_to_ado(self, mock_clear, mock_cancel, pipeline_caller_context):
        from src.pipelines import cancel_run
        pipeline = {"backend": "ado", "pipeline_id": "p1"}
        run = {"backend_run_id": "r1"}

        cancel_run(pipeline, run)

        mock_cancel.assert_called_once_with(pipeline, "r1")
        mock_clear.assert_called_once_with("p1")
