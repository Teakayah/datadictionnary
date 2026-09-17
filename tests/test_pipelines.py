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
from datetime import datetime, timezone; UTC = timezone.utc
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

    def test_false_when_feature_disabled(self, monkeypatch):
        """is_pipeline_user returns False when ENABLE_PIPELINES is off, even with matching groups."""
        monkeypatch.delenv("ENABLE_PIPELINES", raising=False)
        monkeypatch.setenv("PIPELINE_GROUPS", PIPELINE_GROUP)
        import streamlit as st
        st.session_state["user_groups"] = [PIPELINE_GROUP]
        from src.auth import is_pipeline_user
        assert is_pipeline_user() is False

    def test_true_when_group_matches(self, monkeypatch):
        """is_pipeline_user returns True when user belongs to PIPELINE_GROUPS."""
        monkeypatch.setenv("ENABLE_PIPELINES", "true")
        monkeypatch.setenv("PIPELINE_GROUPS", PIPELINE_GROUP)
        import streamlit as st
        st.session_state["user_groups"] = [PIPELINE_GROUP, STANDARD_GROUP]
        from src.auth import is_pipeline_user
        assert is_pipeline_user() is True

    def test_true_with_multiple_pipeline_groups(self, monkeypatch):
        """is_pipeline_user works with comma-separated PIPELINE_GROUPS."""
        monkeypatch.setenv("ENABLE_PIPELINES", "true")
        monkeypatch.setenv("PIPELINE_GROUPS", f"other_group,{PIPELINE_GROUP}")
        import streamlit as st
        st.session_state["user_groups"] = [PIPELINE_GROUP]
        from src.auth import is_pipeline_user
        assert is_pipeline_user() is True


@pytest.fixture
def demo_pipelines():
    """Route src.pipelines through the demo (session-state) path, clean slate."""
    import streamlit as st
    stale = [k for k in st.session_state.keys()
             if k == "_demo_pipelines" or str(k).startswith("_demo_run_")]
    for k in stale:
        st.session_state.pop(k, None)
    with patch("src.pipelines.is_demo_mode", return_value=True):
        yield st.session_state
    stale = [k for k in st.session_state.keys()
             if k == "_demo_pipelines" or str(k).startswith("_demo_run_")]
    for k in stale:
        st.session_state.pop(k, None)


class TestGetPipelines:
    def test_returns_empty_when_storage_empty(self, demo_pipelines):
        """get_pipelines returns [] when no pipelines exist."""
        from src.pipelines import get_pipelines
        assert get_pipelines() == []

    def test_returns_pipelines_from_storage(self, demo_pipelines):
        """get_pipelines returns whatever the demo store holds."""
        demo_pipelines["_demo_pipelines"] = [{
            "pipeline_id": "p1", "title": "My Job", "description": "desc",
            "backend": "databricks", "databricks_job_id": "42",
            "adf_subscription_id": None, "adf_resource_group": None,
            "adf_factory_name": None, "adf_pipeline_name": None,
            "ado_organization": None, "ado_project": None,
            "ado_pipeline_id": None, "created_by": "admin",
            "created_at": datetime.now(UTC),
        }]
        from src.pipelines import get_pipelines
        result = get_pipelines()
        assert len(result) == 1
        assert result[0]["title"] == "My Job"

    def test_returns_empty_on_db_error(self):
        """get_pipelines swallows DB errors and returns []."""
        with patch("src.pipelines.is_demo_mode", return_value=False), \
             patch("src.pipelines.get_db_connection", side_effect=Exception("DB down")):
            from src.pipelines import get_pipelines
            assert get_pipelines() == []


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
        monkeypatch.setenv("ENABLE_PIPELINES", "true")
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
        monkeypatch.setenv("ENABLE_PIPELINES", "true")
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
        monkeypatch.setenv("ENABLE_PIPELINES", "true")
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

    def test_create_pipeline_def_rejects_non_admin(self, demo_pipelines):
        from src.pipelines import PipelineDefParams, create_pipeline_def
        with patch("src.pipelines.is_admin", return_value=False):
            with pytest.raises(PermissionError, match="admins"):
                create_pipeline_def(PipelineDefParams(
                    title="title", description="desc", backend="databricks", databricks_job_id="42",
                    created_by="u",
                ))
        # Storage was not touched.
        assert demo_pipelines.get("_demo_pipelines") in (None, [])

    def test_create_pipeline_def_admin_succeeds(self, admin_caller_context, demo_pipelines):
        from src.pipelines import PipelineDefParams, create_pipeline_def
        create_pipeline_def(PipelineDefParams(
            title="My Pipe", description="desc", backend="databricks", databricks_job_id="42",
            created_by="admin",
        ))
        pipelines = demo_pipelines["_demo_pipelines"]
        assert len(pipelines) == 1
        assert pipelines[0]["title"] == "My Pipe"

    def test_delete_pipeline_def_admin_succeeds(self, admin_caller_context, demo_pipelines):
        from src.pipelines import delete_pipeline_def
        demo_pipelines["_demo_pipelines"] = [{"pipeline_id": "p1", "title": "Gone"}]
        demo_pipelines["_demo_run_p1"] = {"backend_run_id": "r1"}

        delete_pipeline_def("p1")

        assert demo_pipelines["_demo_pipelines"] == []
        assert "_demo_run_p1" not in demo_pipelines

    def test_delete_pipeline_def_rejects_non_admin(self, demo_pipelines):
        from src.pipelines import delete_pipeline_def
        demo_pipelines["_demo_pipelines"] = [{"pipeline_id": "p1", "title": "Stays"}]
        with patch("src.pipelines.is_admin", return_value=False):
            with pytest.raises(PermissionError, match="admins"):
                delete_pipeline_def("p1")
        assert len(demo_pipelines["_demo_pipelines"]) == 1

    def test_delete_pipeline_def_cascades(self, admin_caller_context, demo_pipelines):
        """Deleting a definition also clears its active run, leaving others."""
        from src.pipelines import delete_pipeline_def
        demo_pipelines["_demo_pipelines"] = [
            {"pipeline_id": "p_cascade", "title": "Target"},
            {"pipeline_id": "p_other", "title": "Other"},
        ]
        demo_pipelines["_demo_run_p_cascade"] = {"backend_run_id": "r1"}
        demo_pipelines["_demo_run_p_other"] = {"backend_run_id": "r2"}

        delete_pipeline_def("p_cascade")

        remaining = [p["pipeline_id"] for p in demo_pipelines["_demo_pipelines"]]
        assert remaining == ["p_other"]
        assert "_demo_run_p_cascade" not in demo_pipelines
        assert "_demo_run_p_other" in demo_pipelines

    def test_delete_pipeline_def_storage_error(self, admin_caller_context):
        """A failing definition delete propagates and skips the run cascade."""
        from src.pipelines import delete_pipeline_def
        with patch("src.pipelines.is_demo_mode", return_value=False), \
             patch("src.pipelines._get_write_connection",
                   side_effect=Exception("Storage error")), \
             patch("src.pipelines._clear_run") as mock_clear:
            with pytest.raises(Exception, match="Storage error"):
                delete_pipeline_def("error_pipeline_id")
            mock_clear.assert_not_called()


class TestRunStatePersistence:
    def test_get_active_run(self, demo_pipelines):
        from src.pipelines import get_active_run
        demo_pipelines["_demo_run_pipe1"] = {"status": "running"}

        assert get_active_run("pipe1") == {"status": "running"}
        assert get_active_run("missing") is None

    def test_save_run(self, demo_pipelines):
        from src.pipelines import _save_run

        _save_run("pipe1", "run1", "user1")

        run = demo_pipelines["_demo_run_pipe1"]
        assert run["backend_run_id"] == "run1"
        assert run["triggered_by"] == "user1"
        assert run["status"] == "started"

    def test_update_run(self, demo_pipelines):
        from src.pipelines import _save_run, _update_run

        _save_run("pipe1", "run1", "user1")
        _update_run("pipe1", "success")

        assert demo_pipelines["_demo_run_pipe1"]["status"] == "success"

    def test_clear_run(self, demo_pipelines):
        from src.pipelines import _clear_run, _save_run

        _save_run("pipe1", "run1", "user1")
        _clear_run("pipe1")

        assert "_demo_run_pipe1" not in demo_pipelines
        # Idempotent — clearing again is a no-op.
        _clear_run("pipe1")


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

    @patch("src.pipelines._status_databricks", side_effect=Exception("API failure"))
    @patch("src.pipelines._update_run")
    def test_poll_run_status_exception_handling(self, mock_update, mock_status):
        from src.pipelines import poll_run_status
        pipeline = {"backend": "databricks", "pipeline_id": "p1"}
        run = {"backend_run_id": "r1", "status": "running"}

        result = poll_run_status(pipeline, run)

        mock_update.assert_not_called()
        assert result["status"] == "running"
        assert result["progress"] == 0
        assert "API failure" in result["message"]
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

    @patch("requests.get")
    @patch("src.pipelines._get_sp_token")
    def test_status_adf(self, mock_get_token, mock_get):
        from src.pipelines import _status_adf
        mock_get_token.return_value = "fake-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": "Succeeded",
            "message": "Done"
        }
        mock_get.return_value = mock_resp

        pipeline = {
            "adf_subscription_id": "sub1",
            "adf_resource_group": "rg1",
            "adf_factory_name": "fact1"
        }
        result = _status_adf(pipeline, "run-123")

        assert result["status"] == "Succeeded"
        assert result["progress"] == 100
        assert result["message"] == "Done"
        assert result["is_terminal"] is True

    @patch("requests.get")
    @patch("src.pipelines._get_sp_token")
    def test_status_ado(self, mock_get_token, mock_get):
        from src.pipelines import _status_ado
        mock_get_token.return_value = "fake-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "state": "completed",
            "result": "succeeded"
        }
        mock_get.return_value = mock_resp

        pipeline = {
            "ado_organization": "org1",
            "ado_project": "proj1",
            "ado_pipeline_id": "12"
        }
        result = _status_ado(pipeline, "run-123")

        assert result["status"] == "succeeded"
        assert result["progress"] == 100
        assert result["message"] == ""
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

# --- Inspector Coverage Addition ---
from unittest.mock import patch

class MockCursor:
    def __init__(self, fetch_result=None):
        self.fetch_result = fetch_result

    def execute(self, *args, **kwargs):
        pass

    def fetchall(self):
        return self.fetch_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

class MockConnection:
    def __init__(self, cursor_result=None):
        self.cursor_result = cursor_result

    def cursor(self):
        return MockCursor(self.cursor_result)

    def execute(self, *args, **kwargs):
        pass

def test_pipeline_def_db_paths():
    """Coverage for save_pipeline_def and delete_pipeline_def via DuckDB."""
    with patch("src.pipelines.is_demo_mode", return_value=False), \
         patch("src.pipelines._get_write_connection") as mock_conn, \
         patch("src.pipelines._db_write_lock", MagicMock()), \
         patch("src.pipelines._check_admin"):

        mock_conn_inst = MockConnection()
        mock_conn.return_value = mock_conn_inst

        from src.pipelines import PipelineDefParams, create_pipeline_def, delete_pipeline_def

        create_pipeline_def(PipelineDefParams(
            title="My DB Pipe",
            description="desc",
            backend="databricks",
            created_by="me",
            databricks_job_id="123",
            adf_subscription_id=None,
            adf_resource_group=None,
            adf_factory_name=None,
            adf_pipeline_name=None,
            ado_organization=None,
            ado_project=None,
            ado_pipeline_id=None
        ))

        delete_pipeline_def("test_id")

def test_pipeline_run_db_paths():
    """Coverage for get_active_run, _save_run, _update_run, and _clear_run via DuckDB."""
    with patch("src.pipelines.is_demo_mode", return_value=False), \
         patch("src.pipelines.get_db_connection") as mock_conn, \
         patch("src.pipelines._get_write_connection") as mock_wconn, \
         patch("src.pipelines._db_write_lock", MagicMock()):

        mock_conn_inst = MockConnection(cursor_result=[("run_123", "me", "time", "started", "time")])
        mock_conn.return_value = mock_conn_inst

        mock_wconn_inst = MockConnection()
        mock_wconn.return_value = mock_wconn_inst

        from src.pipelines import get_active_run, _save_run, _update_run, _clear_run

        run = get_active_run("test_id")
        assert run is not None
        assert run["backend_run_id"] == "run_123"

        _save_run("test_id", "run_123", "me")
        _update_run("test_id", "completed")
        _clear_run("test_id")

def test_get_active_run_exception_path():
    """Coverage for Exception fallback in get_active_run."""
    with patch("src.pipelines.is_demo_mode", return_value=False), \
         patch("src.pipelines.get_db_connection") as mock_conn:
        mock_conn.side_effect = Exception("DB failed")
        from src.pipelines import get_active_run
        assert get_active_run("test_id") is None

def test_trigger_bad_backend():
    """Coverage for unknown backend branch in trigger_pipeline."""
    from src.pipelines import trigger_pipeline
    with patch("src.pipelines._check_pipeline_user_or_admin"):
        with pytest.raises(ValueError, match="Unknown backend"):
            trigger_pipeline({"backend": "unknown"}, "user1")

def test_pipeline_poll_databricks():
    """Coverage for Databricks branch in poll_run_status."""
    with patch("src.pipelines._status_databricks", return_value={"status": "pending", "is_terminal": False, "progress": 0, "message": ""}), \
         patch("src.pipelines._update_run"):
        from src.pipelines import poll_run_status
        pipeline = {"backend": "databricks", "pipeline_id": "test_id"}
        run = {"backend_run_id": "123"}
        res = poll_run_status(pipeline, run)
        assert res["status"] == "pending"

def test_pipeline_poll_adf():
    """Coverage for ADF branch in poll_run_status."""
    with patch("src.pipelines._status_adf", return_value={"status": "completed", "is_terminal": True, "progress": 100, "message": ""}), \
         patch("src.pipelines._update_run"), \
         patch("src.pipelines._clear_run"):
        from src.pipelines import poll_run_status
        pipeline = {"backend": "adf", "pipeline_id": "test_id"}
        run = {"backend_run_id": "123"}
        res = poll_run_status(pipeline, run)
        assert res["status"] == "completed"

def test_pipeline_poll_ado():
    """Coverage for ADO branch in poll_run_status."""
    with patch("src.pipelines._status_ado", return_value={"status": "running", "is_terminal": False, "progress": 50, "message": ""}), \
         patch("src.pipelines._update_run"):
        from src.pipelines import poll_run_status
        pipeline = {"backend": "ado", "pipeline_id": "test_id"}
        run = {"backend_run_id": "123"}
        res = poll_run_status(pipeline, run)
        assert res["status"] == "running"

def test_pipeline_poll_unknown_backend():
    """Coverage for unknown backend branch in poll_run_status."""
    with patch("src.pipelines._update_run"):
        from src.pipelines import poll_run_status
        pipeline = {"backend": "unknown", "pipeline_id": "test_id"}
        run = {"backend_run_id": "123"}
        res = poll_run_status(pipeline, run)
        assert res["status"] == "unknown"

def test_pipeline_poll_exception_handled():
    """Coverage for Exception fallback in poll_run_status."""
    with patch("src.pipelines._status_databricks", side_effect=Exception("API limit")):
        from src.pipelines import poll_run_status
        pipeline = {"backend": "databricks", "pipeline_id": "test_id"}
        run = {"backend_run_id": "123", "status": "started"}
        res = poll_run_status(pipeline, run)

        # Ensures exception branch runs
        assert res["status"] == "started"
        assert res["message"] == "API limit"
        assert res["is_terminal"] is False

def test_get_pipelines_db_paths():
    """Coverage for get_pipelines duckdb flow and exception path."""
    with patch("src.pipelines.is_demo_mode", return_value=False), \
         patch("src.pipelines.get_db_connection") as mock_conn:

        # Successful flow
        mock_conn_inst = MockConnection(cursor_result=[
            ("test_id", "title", "desc", "databricks", "123", None, None, None, None, None, None, None, "me", "time")
        ])
        mock_conn.return_value = mock_conn_inst
        from src.pipelines import get_pipelines
        res = get_pipelines()
        assert len(res) == 1
        assert res[0]["pipeline_id"] == "test_id"

        # Exception flow
        mock_conn.side_effect = Exception("DB failure")
        res2 = get_pipelines()
        assert res2 == []

def test_get_active_run_empty_db_paths():
    """Coverage for empty list response in get_active_run duckdb flow."""
    with patch("src.pipelines.is_demo_mode", return_value=False), \
         patch("src.pipelines.get_db_connection") as mock_conn:

        mock_conn_inst = MockConnection(cursor_result=[])
        mock_conn.return_value = mock_conn_inst

        from src.pipelines import get_active_run
        run = get_active_run("test_id")
        assert run is None
