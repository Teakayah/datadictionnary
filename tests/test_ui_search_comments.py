import pytest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import pandas as pd

@pytest.fixture(autouse=True)
def mock_t():
    with patch("src.pages.search.t", side_effect=lambda k, **kw: k) as m:
        yield m

def test_comment_form_open_and_cancel():
    def render_form():
        from src.pages.search import _render_comment_form
        _render_comment_form("table1", "steward1", "key1")

    at = AppTest.from_function(render_form)
    at.run()

    assert not at.exception
    assert len(at.button) == 1
    assert at.button[0].label == "comment.leave_a_comment"

    with patch("streamlit.rerun"):
        # Click to open the form
        at.button[0].click().run()

    # Re-run manually since rerun was mocked
    at.run()

    assert not at.exception

    # Form is open, two buttons (Send and Cancel)
    assert len(at.text_area) == 1
    assert len(at.button) == 2
    assert at.button[0].label == "comment.send"
    assert at.button[1].label == "comment.cancel"

    with patch("streamlit.rerun"):
        # Click cancel
        at.button[1].click().run()

    # Re-run manually since rerun was mocked
    at.run()

    assert not at.exception

    # Form is closed
    assert len(at.button) == 1
    assert at.button[0].label == "comment.leave_a_comment"

def test_comment_form_submit_valid():
    def render_form():
        from src.pages.search import _render_comment_form
        _render_comment_form("table1", "steward1", "key1")

    at = AppTest.from_function(render_form)
    at.run()

    with patch("streamlit.rerun"):
        # Open form
        at.button[0].click().run()
    at.run()

    with patch("src.pages.search.save_comment") as mock_save, \
         patch("streamlit.rerun"):
        # Enter text and submit
        at.text_area[0].input("My comment").run()
        at.button[0].click().run()

        mock_save.assert_called_once_with("TABLE", "table1", "My comment", "steward1", parent_comment_id=None)

    # Trigger run because rerun was mocked
    at.run()

    # Form should be closed after submit
    assert len(at.button) == 1
    assert at.button[0].label == "comment.leave_a_comment"

def test_comment_form_submit_empty():
    def render_form():
        from src.pages.search import _render_comment_form
        _render_comment_form("table1", "steward1", "key1")

    at = AppTest.from_function(render_form)
    at.run()

    with patch("streamlit.rerun"):
        # Open form
        at.button[0].click().run()
    at.run()

    with patch("src.pages.search.save_comment") as mock_save:
        # Enter text and submit
        at.text_area[0].input("   ").run()
        at.button[0].click().run()

        mock_save.assert_not_called()

    # Warning should be displayed and form stays open
    assert len(at.warning) == 1
    assert at.warning[0].value == "comment.empty_error"
    assert len(at.button) == 2

def test_comment_form_no_steward_warning():
    """Verify that a warning is shown if no steward is provided."""
    def render_form():
        from src.pages.search import _render_comment_form
        _render_comment_form("table1", "", "key1")

    at = AppTest.from_function(render_form)
    at.run()

    with patch("streamlit.rerun") as mock_rerun:
        at.button[0].click().run()
    at.run()

    html = "\n".join([m.value for m in at.markdown])
    assert "dd-comment-no-steward" in html

def test_power_user_edit_buttons():
    """Verify that power users see edit buttons and clicking them works."""
    def render_detail_panel():
        import streamlit as st
        import pandas as pd
        from unittest.mock import patch
        from src.pages.search import _render_detail_panel
        row = pd.Series({
            "catalog_name": "main",
            "schema_name": "sales",
            "table_name": "orders",
            "full_name": "main.sales.orders",
            "business_name_en": "Sales Orders",
            "business_name_fr": "Commandes de vente",
            "business_definition_en": "Sales order data.",
            "business_definition_fr": "Données de commande de vente.",
            "description": "Table containing sales orders.",
            "dq_score": 95,
            "steward_email": "test@example.com"
        })
        st.session_state["_live_completeness_main.sales.orders"] = 95
        st.session_state["recent_views"] = []
        # Set up a mock for get_table_comments to return empty list
        with patch("src.pages.search.get_table_comments", return_value=[]), \
             patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
             patch("src.pages.search.get_column_overrides", return_value={}), \
             patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
             patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
             patch("src.pages.search._pref_upsert"), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
             _render_detail_panel(row, "main.sales.orders", tuple())

    at = AppTest.from_function(render_detail_panel)

    with patch("src.pages.search.is_power_user", return_value=True):
        at.run()

    assert not at.exception

    # Check that edit buttons are rendered
    edit_tbl_btn = next((b for b in at.button if "detail.edit_table" in b.label), None)
    assert edit_tbl_btn is not None

    edit_friendly_btn = next((b for b in at.button if "detail.edit_friendly_name" in b.label), None)
    assert edit_friendly_btn is not None
