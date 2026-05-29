import json
from unittest.mock import patch, MagicMock

import pytest
from streamlit.testing.v1 import AppTest

with open("locale/en.json", "r") as f:
    en_locale = json.load(f)

def create_dialog_app():
    from src.ui.cards.pipelines import _show_pipeline_create_dialog
    _show_pipeline_create_dialog()

def admin_section_app():
    from src.ui.cards.pipelines import _render_admin_pipelines_section
    _render_admin_pipelines_section()

def render_page_app():
    from src.ui.cards.pipelines import render_pipelines_page
    render_pipelines_page()

class TestPipelineCreateDialog:
    @patch("src.ui.cards.pipelines.create_pipeline_def")
    def test_create_pipeline_databricks_missing_title(self, mock_create):
        at = AppTest.from_function(create_dialog_app).run()

        at.text_input(key="pl_create_title").set_value("   ")
        at.button(key="pl_save").click().run()

        mock_create.assert_not_called()
        assert at.error[0].value == en_locale["pipelines"]["error_title"]

    @patch("src.ui.cards.pipelines.create_pipeline_def")
    def test_create_pipeline_databricks_success(self, mock_create):
        at = AppTest.from_function(create_dialog_app).run()

        at.text_input(key="pl_create_title").set_value("My DBX Pipeline")
        at.text_area(key="pl_create_desc").set_value("Test Desc")
        at.radio(key="pl_create_backend").set_value("Databricks")
        at.run()

        at.text_input(key="pl_db_job").set_value("12345")

        # Mock session state for actor
        at.session_state["user_email"] = "test@example.com"

        at.button(key="pl_save").click().run()

        mock_create.assert_called_once_with(
            "My DBX Pipeline", "Test Desc", "databricks",
            "12345", None, None, None, None, None, None, None, "test@example.com"
        )

    @patch("src.ui.cards.pipelines.create_pipeline_def")
    def test_create_pipeline_adf_success(self, mock_create):
        at = AppTest.from_function(create_dialog_app).run()

        at.text_input(key="pl_create_title").set_value("My ADF Pipeline")
        at.radio(key="pl_create_backend").set_value("Azure Data Factory")
        at.run()

        at.text_input(key="pl_adf_sub").set_value("sub1")
        at.text_input(key="pl_adf_rg").set_value("rg1")
        at.text_input(key="pl_adf_fact").set_value("fact1")
        at.text_input(key="pl_adf_pipe").set_value("pipe1")

        at.button(key="pl_save").click().run()

        mock_create.assert_called_once_with(
            "My ADF Pipeline", "", "adf",
            None, "sub1", "rg1", "fact1", "pipe1", None, None, None, "admin"
        )

    @patch("src.ui.cards.pipelines.create_pipeline_def")
    def test_create_pipeline_ado_success(self, mock_create):
        at = AppTest.from_function(create_dialog_app).run()

        at.text_input(key="pl_create_title").set_value("My ADO Pipeline")
        at.radio(key="pl_create_backend").set_value("Azure DevOps")
        at.run()

        at.text_input(key="pl_ado_org").set_value("org1")
        at.text_input(key="pl_ado_proj").set_value("proj1")
        at.text_input(key="pl_ado_pid").set_value("42")

        at.button(key="pl_save").click().run()

        mock_create.assert_called_once_with(
            "My ADO Pipeline", "", "ado",
            None, None, None, None, None, "org1", "proj1", "42", "admin"
        )

    @patch("src.ui.cards.pipelines.create_pipeline_def")
    def test_create_pipeline_cancel(self, mock_create):
        at = AppTest.from_function(create_dialog_app).run()

        at.text_input(key="pl_create_title").set_value("Test Title")
        at.button(key="pl_cancel").click().run()

        mock_create.assert_not_called()

class TestAdminPipelinesSection:
    @patch("src.ui.cards.pipelines.get_pipelines")
    def test_render_empty_pipelines(self, mock_get_pipelines):
        mock_get_pipelines.return_value = []
        at = AppTest.from_function(admin_section_app).run()

        html_contents = [m.value for m in at.markdown]
        assert any(en_locale["pipelines"]["no_pipelines"] in val for val in html_contents)

    @patch("src.ui.cards.pipelines.get_pipelines")
    @patch("src.ui.cards.pipelines._show_delete_pipeline_dialog")
    def test_render_with_pipelines_and_delete(self, mock_show_dialog, mock_get_pipelines):
        mock_get_pipelines.return_value = [
            {
                "pipeline_id": "1",
                "title": "Pipeline 1",
                "backend": "databricks"
            },
            {
                "pipeline_id": "2",
                "title": "Pipeline 2",
                "backend": "adf"
            }
        ]

        at = AppTest.from_function(admin_section_app).run()

        html_contents = [m.value for m in at.markdown]
        assert any("Pipeline 1" in val for val in html_contents)
        assert any("Pipeline 2" in val for val in html_contents)

        delete_btn = at.button(key="pl_del_1")
        assert delete_btn is not None
        # The delete button opens a @st.dialog; AppTest cannot reach inside dialogs.
        # Verify the button wires up to the dialog function instead.
        delete_btn.click().run()

        mock_show_dialog.assert_called_once_with("1")

    @patch("src.ui.cards.pipelines._show_pipeline_create_dialog")
    def test_admin_section_new_pipeline_button(self, mock_show_dialog):
        at = AppTest.from_function(admin_section_app).run()

        new_btn = at.button(key="pl_admin_new")
        assert new_btn is not None
        new_btn.click().run()

        mock_show_dialog.assert_called_once()

class TestRenderPipelinesPage:
    @patch("src.ui.cards.pipelines.is_admin", return_value=False)
    @patch("src.ui.cards.pipelines.is_pipeline_user", return_value=False)
    def test_render_page_access_denied(self, mock_user, mock_admin):
        at = AppTest.from_function(render_page_app).run()

        assert at.error[0].value == en_locale["pipelines"]["access_denied"]

    @patch("src.ui.cards.pipelines.is_admin", return_value=True)
    @patch("src.ui.cards.pipelines.get_pipelines")
    def test_render_page_empty(self, mock_get_pipelines, mock_admin):
        mock_get_pipelines.return_value = []
        at = AppTest.from_function(render_page_app).run()

        html_contents = [m.value for m in at.markdown]
        assert any(en_locale["pipelines"]["no_pipelines"] in val for val in html_contents)

    @patch("src.ui.cards.pipelines.is_admin", return_value=True)
    @patch("src.ui.cards.pipelines.get_pipelines")
    @patch("src.ui.cards.pipelines.get_active_run")
    @patch("src.ui.cards.pipelines.poll_run_status")
    @patch("src.ui.cards.pipelines.trigger_pipeline")
    def test_render_page_start_pipeline(self, mock_trigger, mock_poll, mock_get_run, mock_get_pipelines, mock_admin):
        mock_get_pipelines.return_value = [
            {
                "pipeline_id": "1",
                "title": "Pipeline 1",
                "description": "Desc 1",
                "backend": "databricks"
            }
        ]
        mock_get_run.return_value = None

        at = AppTest.from_function(render_page_app).run()

        start_btn = at.button(key="pl_start_1")
        assert start_btn is not None
        start_btn.click().run()

        mock_trigger.assert_called_once()

    @patch("src.ui.cards.pipelines.is_admin", return_value=True)
    @patch("src.ui.cards.pipelines.get_pipelines")
    @patch("src.ui.cards.pipelines.get_active_run")
    @patch("src.ui.cards.pipelines.poll_run_status")
    @patch("src.ui.cards.pipelines.trigger_pipeline", side_effect=Exception("Start failed"))
    def test_render_page_start_pipeline_error(self, mock_trigger, mock_poll, mock_get_run, mock_get_pipelines, mock_admin):
        mock_get_pipelines.return_value = [
            {
                "pipeline_id": "1",
                "title": "Pipeline 1",
                "description": "Desc 1",
                "backend": "databricks"
            }
        ]
        mock_get_run.return_value = None

        at = AppTest.from_function(render_page_app).run()

        start_btn = at.button(key="pl_start_1")
        start_btn.click().run()

        assert len(at.error) > 0
        assert at.error[0].value == en_locale["pipelines"]["start_error"]

    @patch("src.ui.cards.pipelines.is_admin", return_value=True)
    @patch("src.ui.cards.pipelines.get_pipelines")
    @patch("src.ui.cards.pipelines.get_active_run")
    @patch("src.ui.cards.pipelines.poll_run_status")
    @patch("src.ui.cards.pipelines.cancel_run")
    def test_render_page_stop_pipeline(self, mock_cancel, mock_poll, mock_get_run, mock_get_pipelines, mock_admin):
        pipeline = {
            "pipeline_id": "1",
            "title": "Pipeline 1",
            "description": "Desc 1",
            "backend": "databricks"
        }
        mock_get_pipelines.return_value = [pipeline]

        run = {
            "backend_run_id": "r1",
            "triggered_by": "user1",
            "triggered_at": "2023-01-01"
        }
        mock_get_run.return_value = run

        mock_poll.return_value = {
            "status": "RUNNING",
            "progress": 50,
            "message": "Working",
            "is_terminal": False
        }

        at = AppTest.from_function(render_page_app).run()

        stop_btn = at.button(key="pl_stop_1")
        assert stop_btn is not None
        stop_btn.click().run()

        mock_cancel.assert_called_once_with(pipeline, run)

    @patch("src.ui.cards.pipelines.is_admin", return_value=True)
    @patch("src.ui.cards.pipelines.get_pipelines")
    @patch("src.ui.cards.pipelines.get_active_run")
    @patch("src.ui.cards.pipelines.poll_run_status")
    @patch("src.ui.cards.pipelines.cancel_run", side_effect=Exception("Cancel failed"))
    def test_render_page_stop_pipeline_error(self, mock_cancel, mock_poll, mock_get_run, mock_get_pipelines, mock_admin):
        pipeline = {
            "pipeline_id": "1",
            "title": "Pipeline 1",
            "description": "Desc 1",
            "backend": "databricks"
        }
        mock_get_pipelines.return_value = [pipeline]

        run = {
            "backend_run_id": "r1",
            "triggered_by": "user1",
            "triggered_at": "2023-01-01"
        }
        mock_get_run.return_value = run

        mock_poll.return_value = {
            "status": "RUNNING",
            "progress": 50,
            "message": "Working",
            "is_terminal": False
        }

        at = AppTest.from_function(render_page_app).run()

        stop_btn = at.button(key="pl_stop_1")
        stop_btn.click().run()

        assert len(at.error) > 0
        assert at.error[0].value == en_locale["pipelines"]["stop_error"]

    @patch("src.ui.cards.pipelines.is_admin", return_value=True)
    @patch("src.ui.cards.pipelines.get_pipelines")
    @patch("src.ui.cards.pipelines.get_active_run")
    @patch("src.ui.cards.pipelines.poll_run_status")
    def test_render_page_active_run_display(self, mock_poll, mock_get_run, mock_get_pipelines, mock_admin):
        mock_get_pipelines.return_value = [
            {
                "pipeline_id": "1",
                "title": "Pipeline 1",
                "description": "Desc 1",
                "backend": "databricks"
            }
        ]

        mock_get_run.return_value = {
            "backend_run_id": "r1",
            "triggered_by": "user1",
            "triggered_at": "2023-01-01"
        }

        mock_poll.return_value = {
            "status": "RUNNING",
            "progress": 50,
            "message": "Working",
            "is_terminal": False
        }

        at = AppTest.from_function(render_page_app).run()

        html_contents = [m.value for m in at.markdown]
        assert any("RUNNING" in val for val in html_contents)

    @patch("src.ui.cards.pipelines.is_admin", return_value=True)
    @patch("src.ui.cards.pipelines.get_pipelines")
    @patch("src.ui.cards.pipelines.get_active_run")
    @patch("src.ui.cards.pipelines.poll_run_status")
    def test_render_page_active_run_display_colors(self, mock_poll, mock_get_run, mock_get_pipelines, mock_admin):
        mock_get_pipelines.return_value = [
            {
                "pipeline_id": "1",
                "title": "Pipeline 1",
                "description": "Desc 1",
                "backend": "databricks"
            },
            {
                "pipeline_id": "2",
                "title": "Pipeline 2",
                "description": "Desc 2",
                "backend": "adf"
            }
        ]

        def mock_get_active_run(pid):
            if pid == "1":
                return {
                    "backend_run_id": "r1",
                    "triggered_by": "user1",
                    "triggered_at": "2023-01-01"
                }
            elif pid == "2":
                return {
                    "backend_run_id": "r2",
                    "triggered_by": "user2",
                    "triggered_at": "2023-01-02"
                }
            return None

        mock_get_run.side_effect = mock_get_active_run

        def mock_poll_status(pipeline, run):
            if pipeline["pipeline_id"] == "1":
                return {
                    "status": "SUCCESS",
                    "progress": 100,
                    "message": "Done",
                    "is_terminal": True
                }
            elif pipeline["pipeline_id"] == "2":
                return {
                    "status": "FAILED",
                    "progress": 100,
                    "message": "Error",
                    "is_terminal": True
                }
            return None

        mock_poll.side_effect = mock_poll_status

        at = AppTest.from_function(render_page_app).run()

        html_contents = [m.value for m in at.markdown]

        assert any("SUCCESS" in val for val in html_contents)
        assert any("FAILED" in val for val in html_contents)
