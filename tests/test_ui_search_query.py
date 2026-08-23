from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import pandas as pd

def test_search_query_unauthorized():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    mock_search_results = pd.DataFrame([{
        "full_name": "main.sales.unauthorized",
        "table_name": "unauthorized",
        "match_type": "Table",
        "catalog_name": "main",
        "schema_name": "sales",
        "description": "Unauthorized table"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search_results), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k), \
         patch("src.pages.search.track_search"):

        at.run()

        # Now set search query to 'orders' which is in the selectbox options
        at.selectbox(key="catalog_search").set_value("orders").run()

        assert not at.exception

        # Click view details button for the unauthorized table
        buttons = at.button
        view_btns = [b for b in buttons if b.key and b.key.startswith("view_")]
        unauth_btn = next((b for b in view_btns if "main.sales.unauthorized" in b.key), None)
        assert unauth_btn is not None

        unauth_btn.click().run()

        # Should show error
        assert len(at.error) > 0
        assert at.error[0].value == "detail.unauthorized"

def test_search_group_filter_more_than_50():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        # Set initial state
        if "group_filter" not in st.session_state:
            st.session_state["group_filter"] = "SELECT_ALL_USERS"

        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    # Create 55 items
    items = []
    for i in range(55):
        items.append({
            "full_name": f"main.sales.table{i}",
            "table_name": f"table{i}",
            "catalog_name": "main",
            "schema_name": "sales"
        })
    mock_tables = pd.DataFrame(items)

    with patch("src.pages.search.get_authorized_tables", return_value=mock_tables), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search._pref_upsert"):

        at.run()

        assert not at.exception

        # Should show info about 50 limit
        assert len(at.info) > 0
        assert any(i.value == "search.showing_first_50" for i in at.info)

def test_search_query_more_than_50():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    # Create 55 items
    items = []
    for i in range(55):
        items.append({
            "full_name": f"main.sales.table{i}",
            "table_name": f"table{i}",
            "catalog_name": "main",
            "schema_name": "sales",
            "match_type": "Table"
        })
    mock_tables = pd.DataFrame(items)

    with patch("src.pages.search.get_authorized_tables", return_value=mock_tables), \
         patch("src.pages.search.search_all_metadata", return_value=mock_tables), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k), \
         patch("src.pages.search.track_search"):

        at.run()
        at.selectbox(key="catalog_search").set_value("table0").run()

        assert not at.exception

        # Should show info about 50 limit
        assert len(at.info) > 0
        assert any(i.value == "search.showing_first_50" for i in at.info)
