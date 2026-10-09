import pytest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import pandas as pd

def test_search_no_results_empty_state():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    # Empty dataframes to simulate no results for search query but authorized tables exist
    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "nonexistent_query", # Include it so it's in the selectbox options
        "catalog_name": "main",
        "schema_name": "sales"
    }])
    mock_search = pd.DataFrame(columns=["full_name", "table_name", "catalog_name", "schema_name", "match_type", "description"])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.track_search"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()
        # Now we can select it because it's in the options list
        at.selectbox(key="catalog_search").set_value("nonexistent_query").run()

        assert not at.exception

        markdown_values = [m.value for m in at.markdown]

        # Verify the empty state shows search.no_results
        assert any("search.no_results" in val for val in markdown_values), "Expected empty state for no results to be rendered"

def test_search_none_results_empty_state():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    # Empty dataframes to simulate no results for search query but authorized tables exist
    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "nonexistent_query", # Include it so it's in the selectbox options
        "catalog_name": "main",
        "schema_name": "sales"
    }])
    mock_search = None

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.track_search"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()
        # Now we can select it because it's in the options list
        at.selectbox(key="catalog_search").set_value("nonexistent_query").run()

        assert not at.exception

        markdown_values = [m.value for m in at.markdown]

        # Verify the empty state shows search.no_results
        assert any("search.no_results" in val for val in markdown_values), "Expected empty state for no results to be rendered"
