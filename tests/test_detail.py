import json
from unittest.mock import MagicMock, patch

import pandas as pd
from streamlit.testing.v1 import AppTest

# --- Unit Tests (Mocks) ---

def test_render_table_metadata_editor_unit():
    # We need to mock st.dialog before importing the module for unit testing
    # to avoid needing a Streamlit context.
    def noop_dialog(*args, **kwargs):
        return lambda f: f

    with patch("streamlit.dialog", new=noop_dialog):
        import sys
        if "src.ui.cards.detail" in sys.modules:
            del sys.modules["src.ui.cards.detail"]
        from src.ui.cards.detail import render_table_metadata_editor

    with patch("src.ui.cards.detail.st") as mock_st, \
         patch("src.ui.cards.detail.save_table_metadata") as mock_save:

        mock_st.text_area.return_value = "new desc"
        mock_st.text_input.return_value = "new@example.com"

        c1, c2 = MagicMock(), MagicMock()
        mock_st.columns.return_value = [c1, c2]

        def mock_button(*args, **kwargs):
            return kwargs.get("label") == "Save" or (args and args[0] == "Save")

        mock_st.button.side_effect = mock_button
        c1.__enter__.return_value = MagicMock()

        render_table_metadata_editor("cat.sch.tbl", "old desc", "old@example.com")
        mock_save.assert_called_with("cat.sch.tbl", description="new desc", steward_email="new@example.com")

def test_render_data_sample_unauthorized_unit():
    def noop_dialog(*args, **kwargs):
        return lambda f: f

    with patch("streamlit.dialog", new=noop_dialog):
        import sys
        if "src.ui.cards.detail" in sys.modules:
            del sys.modules["src.ui.cards.detail"]
        from src.ui.cards.detail import render_data_sample

    with patch("src.ui.cards.detail.get_authorized_table_names") as mock_get_auth, \
         patch("src.ui.cards.detail.st") as mock_st:
        mock_get_auth.return_value = set()
        mock_st.session_state = {"user_groups": ["group1"]}
        render_data_sample("unauthorized.table")
        mock_st.error.assert_called()


# --- Functional Tests (AppTest) ---

# Get translated strings for exact assertions based on the locale source of truth
with open("locale/en.json", "r") as f:
    en_locale = json.load(f)

# Mocked UI Wrapper for testing dialogs
# Note: AppTest handles st.dialog natively, so we DON'T mock it here.
def table_editor_app(table_name, current_desc, current_steward):
    from src.ui.cards.detail import render_table_metadata_editor
    render_table_metadata_editor(table_name, current_desc, current_steward)

def data_sample_app(table_name):
    from src.ui.cards.detail import render_data_sample
    render_data_sample(table_name)

def table_business_name_editor_app(table_full_name, current_name_en, current_name_fr, current_def_en, current_def_fr):
    from src.ui.cards.detail import render_table_business_name_editor
    render_table_business_name_editor(table_full_name, current_name_en, current_name_fr, current_def_en, current_def_fr)

class TestRenderTableBusinessNameEditor:
    @patch("src.ui.cards.detail.save_table_business_name")
    @patch("src.ui.cards.detail.st.rerun")
    def test_render_table_business_name_editor_save(self, mock_rerun, mock_save):
        at = AppTest.from_function(table_business_name_editor_app, args=("cat.sch.tbl", "old en", "old fr", "old def en", "old def fr")).run()
        at.text_input[0].set_value("new en")
        at.text_input[1].set_value("new fr")
        at.text_area[0].set_value("new def en")
        at.text_area[1].set_value("new def fr")
        at.button[0].click().run()

        mock_save.assert_called_once_with("cat.sch.tbl", "new en", "new fr", "new def en", "new def fr")
        mock_rerun.assert_called_once()
        assert not at.exception
        assert not at.error

    @patch("src.ui.cards.detail.save_table_business_name")
    @patch("src.ui.cards.detail.st.rerun")
    def test_render_table_business_name_editor_exception(self, mock_rerun, mock_save):
        mock_save.side_effect = Exception("DB Error")

        at = AppTest.from_function(table_business_name_editor_app, args=("cat.sch.tbl", "old en", "old fr", "old def en", "old def fr")).run()
        at.text_input[0].set_value("new en")
        at.button[0].click().run()

        mock_save.assert_called_once()
        mock_rerun.assert_not_called()
        assert len(at.error) > 0
        assert at.error[0].value == en_locale["common"]["error"]

    @patch("src.ui.cards.detail.save_table_business_name")
    @patch("src.ui.cards.detail.st.rerun")
    def test_render_table_business_name_editor_permission_error(self, mock_rerun, mock_save):
        mock_save.side_effect = PermissionError("Not allowed")

        at = AppTest.from_function(table_business_name_editor_app, args=("cat.sch.tbl", "old en", "old fr", "old def en", "old def fr")).run()
        at.text_input[0].set_value("new en")
        at.button[0].click().run()

        mock_save.assert_called_once()
        mock_rerun.assert_not_called()
        assert len(at.error) > 0
        assert at.error[0].value == en_locale["detail"]["unauthorized"]

    @patch("src.ui.cards.detail.save_table_business_name")
    @patch("src.ui.cards.detail.st.rerun")
    def test_render_table_business_name_editor_value_error(self, mock_rerun, mock_save):
        mock_save.side_effect = ValueError("Invalid input")

        at = AppTest.from_function(table_business_name_editor_app, args=("cat.sch.tbl", "old en", "old fr", "old def en", "old def fr")).run()
        at.text_input[0].set_value("new en")
        at.button[0].click().run()

        mock_save.assert_called_once()
        mock_rerun.assert_not_called()
        assert len(at.error) > 0
        assert at.error[0].value == "An error occurred."

    @patch("src.ui.cards.detail.get_table_business_name_override")
    def test_render_table_business_name_editor_fetch_defaults(self, mock_storage):
        mock_storage.return_value = {
            "business_name_en": "fetched_en",
            "business_name_fr": "fetched_fr",
            "business_definition_en": "fetched_def_en",
            "business_definition_fr": "fetched_def_fr"
        }

        at = AppTest.from_function(table_business_name_editor_app, args=("cat.sch.tbl", "", "", "", "")).run()

        mock_storage.assert_called_once_with("cat.sch.tbl")
        assert at.text_input[0].value == "fetched_en"
        assert at.text_input[1].value == "fetched_fr"
        assert at.text_area[0].value == "fetched_def_en"
        assert at.text_area[1].value == "fetched_def_fr"

    @patch("src.ui.cards.detail.get_table_business_name_override")
    def test_render_table_business_name_editor_fetch_defaults_exception(self, mock_storage):
        mock_storage.side_effect = Exception("Storage error")

        at = AppTest.from_function(table_business_name_editor_app, args=("cat.sch.tbl", "", "", "", "")).run()

        mock_storage.assert_called_once_with("cat.sch.tbl")
        # Should catch the error and log it, then render with empty fields
        assert at.text_input[0].value == ""
        assert at.text_input[1].value == ""

    @patch("src.ui.cards.detail.save_table_business_name")
    @patch("src.ui.cards.detail.st.rerun")
    def test_render_table_business_name_editor_cancel(self, mock_rerun, mock_save):
        at = AppTest.from_function(table_business_name_editor_app, args=("cat.sch.tbl", "old en", "old fr", "old def en", "old def fr")).run()
        at.button[1].click().run()

        mock_save.assert_not_called()
        mock_rerun.assert_called_once()


class TestRenderTableMetadataEditor:
    @patch("src.ui.cards.detail.save_table_metadata")
    def test_render_table_metadata_editor_save(self, mock_save):
        at = AppTest.from_function(table_editor_app, args=("cat.sch.tbl", "old desc", "old@steward.com")).run()

        # The editor renders a markdown title, a text area, a text input, and two buttons
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
        expected_error = en_locale["common"]["error"]
        assert at.error[0].value == expected_error

    @patch("src.ui.cards.detail.save_table_metadata")
    def test_render_table_metadata_editor_cancel(self, mock_save):
        at = AppTest.from_function(table_editor_app, args=("cat.sch.tbl", "old desc", "old@steward.com")).run()

        at.button[1].click().run()

        mock_save.assert_not_called()
        assert not at.exception
        assert not at.error


class TestRenderDataSample:
    @patch("src.ui.cards.detail.get_authorized_table_names")
    def test_render_data_sample_unauthorized(self, mock_auth):
        mock_auth.return_value = {"other.table"}
        at = AppTest.from_function(data_sample_app, args=("cat.sch.tbl",)).run()

        assert at.error[0].value == en_locale["detail"]["unauthorized"]

    @patch("src.ui.cards.detail.get_authorized_table_names")
    @patch("src.ui.cards.detail.is_demo_mode")
    @patch("src.ui.cards.detail._duckdb_available")
    @patch("src.ui.cards.detail.run_query")
    def test_render_data_sample_single_part_name(self, mock_run, mock_duckdb, mock_demo, mock_auth):
        mock_auth.return_value = {"invalid-name"}
        mock_demo.return_value = False
        mock_duckdb.return_value = False
        mock_run.return_value = pd.DataFrame({"col": [1, 2]})

        at = AppTest.from_function(data_sample_app, args=("invalid-name",)).run()

        # It should process correctly and escape the single part name
        mock_run.assert_called_once_with("SELECT * FROM IDENTIFIER(%(p0)s) LIMIT 100", {"p0": "invalid-name"})
        assert len(at.dataframe) == 1

    @patch("src.ui.cards.detail.get_authorized_table_names")
    @patch("src.ui.cards.detail.is_demo_mode")
    def test_render_data_sample_demo_mode(self, mock_demo, mock_auth):
        mock_auth.return_value = {"cat.sch.tbl"}
        mock_demo.return_value = True

        at = AppTest.from_function(data_sample_app, args=("cat.sch.tbl",)).run()

        assert len(at.dataframe) == 1
        df = at.dataframe[0].value
        assert "status" in df.columns
        assert list(df["status"]) == ["NEW", "SHIPPED", "CLOSED"]

    @patch("src.ui.cards.detail.get_authorized_table_names")
    @patch("src.ui.cards.detail.is_demo_mode")
    @patch("src.ui.cards.detail._duckdb_available")
    @patch("src.ui.cards.detail.run_query")
    def test_render_data_sample_duckdb_query(self, mock_run, mock_duckdb, mock_demo, mock_auth):
        mock_auth.return_value = {"cat.sch.tbl"}
        mock_demo.return_value = False
        mock_duckdb.return_value = True
        mock_run.return_value = pd.DataFrame({"col": [1, 2]})

        at = AppTest.from_function(data_sample_app, args=("cat.sch.tbl",)).run()

        mock_run.assert_called_once()
        sql = mock_run.call_args[0][0]
        params = mock_run.call_args[0][1]
        from src.config import CATALOG_CACHE
        assert sql == "SELECT * FROM query_table(%(t)s) LIMIT 100"
        assert params == {"t": f"{CATALOG_CACHE}.sch.tbl"}
        assert len(at.dataframe) == 1

    @patch("src.ui.cards.detail.get_authorized_table_names")
    @patch("src.ui.cards.detail.is_demo_mode")
    @patch("src.ui.cards.detail._duckdb_available")
    @patch("src.ui.cards.detail.run_query")
    def test_render_data_sample_duckdb_query_invalid_parts(self, mock_run, mock_duckdb, mock_demo, mock_auth):
        mock_auth.return_value = {"not_three_parts"}
        mock_demo.return_value = False
        mock_duckdb.return_value = True
        mock_run.return_value = pd.DataFrame({"col": [1, 2]})

        at = AppTest.from_function(data_sample_app, args=("not_three_parts",)).run()

        from src.config import CATALOG_CACHE
        mock_run.assert_called_once_with("SELECT * FROM query_table(%(t)s) LIMIT 100", {"t": f"{CATALOG_CACHE}.not_three_parts"})
        assert len(at.dataframe) == 1

    @patch("src.ui.cards.detail.get_authorized_table_names")
    @patch("src.ui.cards.detail.is_demo_mode")
    @patch("src.ui.cards.detail._duckdb_available")
    @patch("src.ui.cards.detail.run_query")
    def test_render_data_sample_prod_query(self, mock_run, mock_duckdb, mock_demo, mock_auth):
        mock_auth.return_value = {"cat.sch.tbl"}
        mock_demo.return_value = False
        mock_duckdb.return_value = False
        mock_run.return_value = pd.DataFrame({"col": [1, 2]})

        at = AppTest.from_function(data_sample_app, args=("cat.sch.tbl",)).run()

        mock_run.assert_called_once_with("SELECT * FROM IDENTIFIER(%(p0)s).IDENTIFIER(%(p1)s).IDENTIFIER(%(p2)s) LIMIT 100", {"p0": "cat", "p1": "sch", "p2": "tbl"})
        assert len(at.dataframe) == 1

    @patch("src.ui.cards.detail.get_authorized_table_names")
    @patch("src.ui.cards.detail.is_demo_mode")
    @patch("src.ui.cards.detail._duckdb_available")
    @patch("src.ui.cards.detail.run_query")
    def test_render_data_sample_prod_query_no_data(self, mock_run, mock_duckdb, mock_demo, mock_auth):
        mock_auth.return_value = {"cat.sch.tbl"}
        mock_demo.return_value = False
        mock_duckdb.return_value = False
        mock_run.return_value = pd.DataFrame()

        at = AppTest.from_function(data_sample_app, args=("cat.sch.tbl",)).run()

        assert len(at.dataframe) == 0
        assert len(at.markdown) > 0
        assert en_locale["detail"]["preview_needs_data"] in at.markdown[-1].value

    @patch("src.ui.cards.detail.get_authorized_table_names")
    @patch("src.ui.cards.detail.is_demo_mode")
    @patch("src.ui.cards.detail.run_query")
    def test_render_data_sample_exception(self, mock_run, mock_demo, mock_auth):
        mock_auth.return_value = {"cat.sch.tbl"}
        mock_demo.return_value = False
        mock_run.side_effect = Exception("Fetch Error")

        at = AppTest.from_function(data_sample_app, args=("cat.sch.tbl",)).run()

        assert len(at.error) > 0
        assert at.error[0].value == en_locale["detail"]["preview_error"]

def test_save_table_metadata_exception():
    import streamlit as st
    import pandas as pd
    from streamlit.testing.v1 import AppTest
    from unittest.mock import patch

    def render_editor():
        import streamlit as st
        from src.ui.cards.detail import render_table_metadata_editor

        st.session_state["user_email"] = "test@example.com"
        render_table_metadata_editor("main.sales.orders", "Current description", "steward@example.com")

    at = AppTest.from_function(render_editor)

    with patch("src.ui.cards.detail.save_table_metadata", side_effect=Exception("Save Exception")), \
         patch("src.ui.cards.detail.t", side_effect=lambda k, **kw: k), \
         patch("src.auth.is_admin", return_value=True):

        at.run()

        save_button = [b for b in at.button if b.label == "common.save"][0]
        save_button.click().run()

        assert not at.exception
        assert len(at.error) > 0
        assert at.error[0].value == "common.error"

def test_save_table_business_name_exception():
    import streamlit as st
    import pandas as pd
    from streamlit.testing.v1 import AppTest
    from unittest.mock import patch

    def render_editor():
        import streamlit as st
        from src.ui.cards.detail import render_table_business_name_editor

        st.session_state["user_email"] = "test@example.com"
        render_table_business_name_editor("main.sales.orders", "En Name", "Fr Name", "En Def", "Fr Def")

    at = AppTest.from_function(render_editor)

    with patch("src.ui.cards.detail.save_table_business_name", side_effect=Exception("Save Exception")), \
         patch("src.ui.cards.detail.t", side_effect=lambda k, **kw: k), \
         patch("src.auth.is_admin", return_value=True):

        at.run()

        save_button = [b for b in at.button if b.label == "common.save"][0]
        save_button.click().run()

        assert not at.exception
        assert len(at.error) > 0
        assert at.error[0].value == "common.error"
