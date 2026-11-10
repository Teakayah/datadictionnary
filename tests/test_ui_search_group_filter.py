from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import pandas as pd

def test_search_group_filter_browse():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        # Set initial state
        if "group_filter" not in st.session_state:
            st.session_state["group_filter"] = "SELECT_ALL_USERS"

        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_tables = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "description": "Sales orders table",
        "dq_score": 90,
        "catalog_name": "main",
        "schema_name": "sales"
    }, {
        "full_name": "main.sales.unauthorized",
        "table_name": "unauthorized",
        "description": "Unauthorized table",
        "dq_score": 80,
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_tables), \
         patch("src.pages.search.search_all_metadata", return_value=mock_tables), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.personalization._pref_upsert"):

        at.run()

        assert not at.exception

        # The group filter section should render the tables
        # Check buttons with keys starting with "gview_"
        buttons = at.button
        view_btns = [b for b in buttons if b.key and b.key.startswith("gview_")]

        # Click the view button for the authorized table
        auth_btn = next((b for b in view_btns if "main.sales.orders" in b.key), None)
        assert auth_btn is not None

        # Click the button
        with patch("streamlit.rerun"):
            # main.sales.orders should be in _auth_full_names, which is derived from get_authorized_tables
            auth_btn.click().run()

        assert "dd_search_override" in at.session_state
        assert at.session_state["dd_nav_select"] == "main.sales.orders"


def test_search_analytics_track_success():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_tables = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "match_type": "Table",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_tables), \
         patch("src.pages.search.search_all_metadata", return_value=mock_tables), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k), \
         patch("src.pages.search.track_search") as mock_track:

        at.run()

        # Now set search query
        at.selectbox(key="catalog_search").set_value("orders").run()

        mock_track.assert_called_once()
        args = mock_track.call_args[0][0]
        assert args.query == "orders"
        assert args.results_count == 1
        assert args.user_email == "test@example.com"

def test_search_analytics_track_exception():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_tables = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "match_type": "Table",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_tables), \
         patch("src.pages.search.search_all_metadata", return_value=mock_tables), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k), \
         patch("src.pages.search.track_search", side_effect=Exception("Analytics failed")):

        at.run()

        # Now set search query
        at.selectbox(key="catalog_search").set_value("orders").run()

        # Should not crash the app
        assert not at.exception
