import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture(autouse=True)
def mock_st_dialog():
    # Mock st.dialog so it just returns the function without wrapping it
    # We must patch it before it is imported in src.ui.cards.detail
    def noop_dialog(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    with patch("streamlit.dialog", new=noop_dialog):
        import sys
        if "src.ui.cards.detail" in sys.modules:
            del sys.modules["src.ui.cards.detail"]
        yield

def test_render_table_metadata_editor():
    from src.ui.cards.detail import render_table_metadata_editor

    with patch("src.ui.cards.detail.st") as mock_st, \
         patch("src.ui.cards.detail.save_table_metadata") as mock_save:

        mock_st.text_area.return_value = "new desc"
        mock_st.text_input.return_value = "new@example.com"

        c1, c2 = MagicMock(), MagicMock()
        mock_st.columns.return_value = [c1, c2]

        # Mock button click on Save
        def mock_button(*args, **kwargs):
            return kwargs.get("label") == "Save" or (args and args[0] == "Save")

        mock_st.button.side_effect = mock_button
        c1.__enter__.return_value = MagicMock()

        # When context manager is active
        # This is tricky because st.columns returns mock objects and we need st.button to trigger
        # We can just patch st.button directly if it uses it directly without c1.button

        render_table_metadata_editor("cat.sch.tbl", "old desc", "old@example.com")

        mock_save.assert_called_with("cat.sch.tbl", description="new desc", steward_email="new@example.com")

def test_render_data_sample_unauthorized():
    from src.ui.cards.detail import render_data_sample

    with patch("src.ui.cards.detail.get_authorized_tables") as mock_get_auth, \
         patch("src.ui.cards.detail.st") as mock_st:

        import pandas as pd
        mock_get_auth.return_value = pd.DataFrame(columns=["full_name"])
        mock_st.session_state = {"user_groups": ["group1"]}

        render_data_sample("unauthorized.table")

        mock_st.error.assert_called()

def test_render_data_sample_authorized_demo():
    from src.ui.cards.detail import render_data_sample

    with patch("src.ui.cards.detail.get_authorized_tables") as mock_get_auth, \
         patch("src.ui.cards.detail.is_demo_mode", return_value=True), \
         patch("src.ui.cards.detail.re.match", return_value=True), \
         patch("src.ui.cards.detail.st") as mock_st:

        import pandas as pd
        mock_get_auth.return_value = pd.DataFrame({"full_name": ["cat.sch.tbl"]})
        mock_st.session_state = {"user_groups": ["group1"]}

        render_data_sample("cat.sch.tbl")

        mock_st.dataframe.assert_called_once()

def test_render_data_sample_duckdb():
    from src.ui.cards.detail import render_data_sample

    with patch("src.ui.cards.detail.get_authorized_tables") as mock_get_auth, \
         patch("src.ui.cards.detail.is_demo_mode", return_value=False), \
         patch("src.ui.cards.detail._duckdb_available", return_value=True), \
         patch("src.ui.cards.detail.run_query") as mock_run_query, \
         patch("src.ui.cards.detail.re.match", return_value=True), \
         patch("src.ui.cards.detail.st") as mock_st:

        import pandas as pd
        mock_get_auth.return_value = pd.DataFrame({"full_name": ["cat.sch.tbl"]})
        mock_st.session_state = {"user_groups": ["group1"]}
        mock_run_query.return_value = pd.DataFrame({"col": [1, 2]})

        render_data_sample("cat.sch.tbl")

        mock_st.dataframe.assert_called_once()
        mock_run_query.assert_called_once()

def test_render_data_sample_databricks():
    from src.ui.cards.detail import render_data_sample

    with patch("src.ui.cards.detail.get_authorized_tables") as mock_get_auth, \
         patch("src.ui.cards.detail.is_demo_mode", return_value=False), \
         patch("src.ui.cards.detail._duckdb_available", return_value=False), \
         patch("src.ui.cards.detail.run_query") as mock_run_query, \
         patch("src.ui.cards.detail.re.match", return_value=True), \
         patch("src.ui.cards.detail.st") as mock_st:

        import pandas as pd
        mock_get_auth.return_value = pd.DataFrame({"full_name": ["cat.sch.tbl"]})
        mock_st.session_state = {"user_groups": ["group1"]}
        mock_run_query.return_value = pd.DataFrame({"col": [1, 2]})

        render_data_sample("cat.sch.tbl")

        mock_st.dataframe.assert_called_once()
        mock_run_query.assert_called_once()

def test_render_table_metadata_editor_invalid_email():
    from src.ui.cards.detail import render_table_metadata_editor
    with patch("src.ui.cards.detail.st") as mock_st:
        mock_st.text_area.return_value = "desc"
        mock_st.text_input.return_value = "invalid-email"

        c1, c2 = MagicMock(), MagicMock()
        mock_st.columns.return_value = [c1, c2]

        def mock_button(*args, **kwargs):
            return kwargs.get("label") == "Save" or (args and args[0] == "Save")
            return kwargs.get("label") == "Save" or (args and args[0] == "Save")
        mock_st.button.side_effect = mock_button

        render_table_metadata_editor("cat.sch.tbl", "desc", "email")
        mock_st.error.assert_called()

def test_render_table_metadata_editor_save_exception():
    from src.ui.cards.detail import render_table_metadata_editor
    with patch("src.ui.cards.detail.st") as mock_st, \
         patch("src.ui.cards.detail.save_table_metadata", side_effect=Exception("Save failed")):

        mock_st.text_area.return_value = "desc"
        mock_st.text_input.return_value = "valid@example.com"

        c1, c2 = MagicMock(), MagicMock()
        mock_st.columns.return_value = [c1, c2]

        def mock_button(*args, **kwargs):
            return args[0] == "Save"
        mock_st.button.side_effect = mock_button

        render_table_metadata_editor("cat.sch.tbl", "desc", "email")
        mock_st.error.assert_called()

def test_render_table_metadata_editor_cancel():
    from src.ui.cards.detail import render_table_metadata_editor
    with patch("src.ui.cards.detail.st") as mock_st:
        c1, c2 = MagicMock(), MagicMock()
        mock_st.columns.return_value = [c1, c2]

        def mock_button(*args, **kwargs):
            return kwargs.get("label") == "Cancel" or (args and args[0] == "Cancel")
        mock_st.button.side_effect = mock_button

        render_table_metadata_editor("cat.sch.tbl", "desc", "email")
        mock_st.rerun.assert_called_once()

def test_render_data_sample_regex_fail():
    from src.ui.cards.detail import render_data_sample
    with patch("src.ui.cards.detail.get_authorized_tables") as mock_get_auth, \
         patch("src.ui.cards.detail.st") as mock_st:

        import pandas as pd
        mock_get_auth.return_value = pd.DataFrame({"full_name": ["invalid_format"]})

        render_data_sample("invalid_format")
        mock_st.error.assert_called()

def test_render_data_sample_empty_df():
    from src.ui.cards.detail import render_data_sample
    with patch("src.ui.cards.detail.get_authorized_tables") as mock_get_auth, \
         patch("src.ui.cards.detail.is_demo_mode", return_value=False), \
         patch("src.ui.cards.detail._duckdb_available", return_value=False), \
         patch("src.ui.cards.detail.run_query") as mock_run_query, \
         patch("src.ui.cards.detail.st") as mock_st:

        import pandas as pd
        mock_get_auth.return_value = pd.DataFrame({"full_name": ["cat.sch.tbl"]})
        mock_run_query.return_value = pd.DataFrame()

        render_data_sample("cat.sch.tbl")
        mock_st.info.assert_called()

def test_render_data_sample_exception():
    from src.ui.cards.detail import render_data_sample
    with patch("src.ui.cards.detail.get_authorized_tables") as mock_get_auth, \
         patch("src.ui.cards.detail.is_demo_mode", return_value=False), \
         patch("src.ui.cards.detail._duckdb_available", return_value=False), \
         patch("src.ui.cards.detail.run_query", side_effect=Exception("Query failed")), \
         patch("src.ui.cards.detail.st") as mock_st:

        import pandas as pd
        mock_get_auth.return_value = pd.DataFrame({"full_name": ["cat.sch.tbl"]})

        render_data_sample("cat.sch.tbl")
        mock_st.error.assert_called()

def test_render_data_sample_duckdb_invalid_len_parts():
    from src.ui.cards.detail import render_data_sample
    with patch("src.ui.cards.detail.get_authorized_tables") as mock_get_auth, \
         patch("src.ui.cards.detail.is_demo_mode", return_value=False), \
         patch("src.ui.cards.detail._duckdb_available", return_value=True), \
         patch("src.ui.cards.detail.re.match", return_value=True), \
         patch("src.ui.cards.detail.st") as mock_st:

        import pandas as pd
        mock_get_auth.return_value = pd.DataFrame({"full_name": ["a.b"]})

        render_data_sample("a.b")
        mock_st.info.assert_called()
