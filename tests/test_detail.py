import json
import logging
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

# Get translated strings for exact assertions based on the locale source of truth
with open("locale/en.json", "r") as f:
    en_locale = json.load(f)

# Mocked UI Wrapper for testing dialogs
def table_editor_app(table_name, current_desc, current_steward):
    from src.ui.cards.detail import render_table_metadata_editor
    render_table_metadata_editor(table_name, current_desc, current_steward)

def data_sample_app(table_name):
    from src.ui.cards.detail import render_data_sample
    render_data_sample(table_name)


class TestRenderTableMetadataEditor:
    @patch("src.ui.cards.detail.save_table_metadata")
    def test_render_table_metadata_editor_save(self, mock_save):
        at = AppTest.from_function(table_editor_app, args=("cat.sch.tbl", "old desc", "old@steward.com")).run()

        at.text_area[0].set_value("new desc")
        at.text_input[0].set_value("new@steward.com")
        at.button[0].click().run()

        mock_save.assert_called_once_with("cat.sch.tbl", description="new desc", steward_email="new@steward.com")
        assert not at.exception
        assert not at.error

    @patch("src.ui.cards.detail.save_table_metadata")
    def test_render_table_metadata_editor_invalid_email(self, mock_save):
        at = AppTest.from_function(table_editor_app, args=("cat.sch.tbl", "old desc", "old@steward.com")).run()

        at.text_input[0].set_value("invalidemail")
        at.button[0].click().run()

        mock_save.assert_not_called()
        assert at.error[0].value == en_locale["detail"]["invalid_email"]

    @patch("src.ui.cards.detail.save_table_metadata")
    def test_render_table_metadata_editor_exception(self, mock_save):
        mock_save.side_effect = Exception("DB Error")
        at = AppTest.from_function(table_editor_app, args=("cat.sch.tbl", "old desc", "old@steward.com")).run()

        at.button[0].click().run()

        mock_save.assert_called_once()
        expected_error = en_locale["common"]["error_with_details"].replace("{error}", "DB Error")
        assert at.error[0].value == expected_error


class TestRenderDataSample:
    @patch("src.ui.cards.detail.get_authorized_tables")
    def test_render_data_sample_unauthorized(self, mock_auth):
        mock_auth.return_value = pd.DataFrame({"full_name": ["other.table"]})
        at = AppTest.from_function(data_sample_app, args=("cat.sch.tbl",)).run()

        assert at.error[0].value == en_locale["detail"]["unauthorized"]

    @patch("src.ui.cards.detail.get_authorized_tables")
    def test_render_data_sample_invalid_namespace(self, mock_auth):
        mock_auth.return_value = pd.DataFrame({"full_name": ["invalid-name"]})
        at = AppTest.from_function(data_sample_app, args=("invalid-name",)).run()

        assert at.error[0].value == en_locale["common"]["error"]

    @patch("src.ui.cards.detail.get_authorized_tables")
    @patch("src.ui.cards.detail.is_demo_mode")
    def test_render_data_sample_demo_mode(self, mock_demo, mock_auth):
        mock_auth.return_value = pd.DataFrame({"full_name": ["cat.sch.tbl"]})
        mock_demo.return_value = True

        at = AppTest.from_function(data_sample_app, args=("cat.sch.tbl",)).run()

        assert len(at.dataframe) == 1
        df = at.dataframe[0].value
        assert "status" in df.columns
        assert list(df["status"]) == ["NEW", "SHIPPED", "CLOSED"]

    @patch("src.ui.cards.detail.get_authorized_tables")
    @patch("src.ui.cards.detail.is_demo_mode")
    @patch("src.ui.cards.detail._duckdb_available")
    @patch("src.ui.cards.detail.run_query")
    def test_render_data_sample_duckdb_query(self, mock_run, mock_duckdb, mock_demo, mock_auth):
        mock_auth.return_value = pd.DataFrame({"full_name": ["cat.sch.tbl"]})
        mock_demo.return_value = False
        mock_duckdb.return_value = True
        mock_run.return_value = pd.DataFrame({"col": [1, 2]})

        at = AppTest.from_function(data_sample_app, args=("cat.sch.tbl",)).run()

        mock_run.assert_called_once()
        sql = mock_run.call_args[0][0]
        from src.config import CATALOG_CACHE
        assert f'SELECT * FROM {CATALOG_CACHE}."sch"."tbl" LIMIT 100' in sql
        assert len(at.dataframe) == 1

    @patch("src.ui.cards.detail.get_authorized_tables")
    @patch("src.ui.cards.detail.is_demo_mode")
    @patch("src.ui.cards.detail._duckdb_available")
    @patch("src.ui.cards.detail.run_query")
    def test_render_data_sample_duckdb_query_invalid_parts(self, mock_run, mock_duckdb, mock_demo, mock_auth):
        # We need to authorize the specific invalid table name we are using to get past the auth check
        mock_auth.return_value = pd.DataFrame({"full_name": ["not_three_parts"]})
        mock_demo.return_value = False
        mock_duckdb.return_value = True

        # Bypass regex
        with patch("src.ui.cards.detail.re.match") as mock_match:
            mock_match.return_value = True
            at = AppTest.from_function(data_sample_app, args=("not_three_parts",)).run()

            # Now it should reach the parts logic
            assert len(at.info) > 0
            assert at.info[0].value == en_locale["detail"]["preview_not_available"]
            mock_run.assert_not_called()

    @patch("src.ui.cards.detail.get_authorized_tables")
    @patch("src.ui.cards.detail.is_demo_mode")
    @patch("src.ui.cards.detail._duckdb_available")
    @patch("src.ui.cards.detail.run_query")
    def test_render_data_sample_prod_query(self, mock_run, mock_duckdb, mock_demo, mock_auth):
        mock_auth.return_value = pd.DataFrame({"full_name": ["cat.sch.tbl"]})
        mock_demo.return_value = False
        mock_duckdb.return_value = False
        mock_run.return_value = pd.DataFrame({"col": [1, 2]})

        at = AppTest.from_function(data_sample_app, args=("cat.sch.tbl",)).run()

        mock_run.assert_called_once_with("SELECT * FROM cat.sch.tbl LIMIT 100")
        assert len(at.dataframe) == 1

    @patch("src.ui.cards.detail.get_authorized_tables")
    @patch("src.ui.cards.detail.is_demo_mode")
    @patch("src.ui.cards.detail._duckdb_available")
    @patch("src.ui.cards.detail.run_query")
    def test_render_data_sample_prod_query_no_data(self, mock_run, mock_duckdb, mock_demo, mock_auth):
        mock_auth.return_value = pd.DataFrame({"full_name": ["cat.sch.tbl"]})
        mock_demo.return_value = False
        mock_duckdb.return_value = False
        mock_run.return_value = pd.DataFrame()

        at = AppTest.from_function(data_sample_app, args=("cat.sch.tbl",)).run()

        assert len(at.dataframe) == 0
        assert len(at.info) > 0
        assert at.info[0].value == en_locale["detail"]["preview_needs_data"]

    @patch("src.ui.cards.detail.get_authorized_tables")
    @patch("src.ui.cards.detail.is_demo_mode")
    @patch("src.ui.cards.detail.run_query")
    def test_render_data_sample_exception(self, mock_run, mock_demo, mock_auth):
        mock_auth.return_value = pd.DataFrame({"full_name": ["cat.sch.tbl"]})
        mock_demo.return_value = False
        mock_run.side_effect = Exception("Fetch Error")

        at = AppTest.from_function(data_sample_app, args=("cat.sch.tbl",)).run()

        assert len(at.error) > 0
        assert at.error[0].value == en_locale["detail"]["preview_error"]
