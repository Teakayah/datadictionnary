from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import pandas as pd

def test_search_downstream_critical():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_nav_select"] = "main.sales.orders"

        # When `dd_nav_select` is set, it executes:
        # _auth_tables = get_authorized_tables(query_groups)
        # _table_results = search_all_metadata(query_groups, _all_tables, st.session_state["catalog_search"])
        # _table_names = _table_results["table_name"].tolist()
        # _nav_name = _nav_target.split(".")[-1]
        # if _nav_name in _table_names:
        #    _nav_idx = _table_names.index(_nav_name)
        # So we need catalog_search to return the table. Let's provide a default catalog_search.
        if "catalog_search" not in st.session_state:
            st.session_state["catalog_search"] = "orders"

        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 100,
        "match_type": "Table",
        "description": "desc"
    }])

    mock_lineage = pd.DataFrame({
        "direction": ["downstream"],
        "entity_type": ["certified dashboard"],
        "node": ["some_dashboard"]
    })

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_authorized), \
         patch("src.pages.search.get_multi_hop_lineage", return_value=mock_lineage), \
         patch("src.pages.search._build_lineage_graph", return_value=([], [])), \
         patch("src.pages.search.get_table_columns", return_value=pd.DataFrame([{"column_name": "id", "data_type": "int", "comment": ""}])), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame([{"grant_group_0": "group1", "principal": "user", "privilege": "SELECT"}])), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.components.html"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: "CRITICAL_WARNING_MOCK" if k == "detail.downstream_certified_warning" else k):

        at.run()
        assert not at.exception

        found = False
        for md in at.markdown:
            if md.value and "CRITICAL_WARNING_MOCK" in md.value:
                found = True

        assert found is True, f"Critical warning not found. Markdowns: {[m.value for m in at.markdown]}"
import pandas as pd
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

def test_search_downstream_exception():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_nav_select"] = "main.sales.orders"

        if "catalog_search" not in st.session_state:
            st.session_state["catalog_search"] = "orders"

        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 100,
        "match_type": "Table",
        "description": "desc"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_authorized), \
         patch("src.pages.search.get_multi_hop_lineage", side_effect=Exception("Database error")), \
         patch("src.pages.search._build_lineage_graph", return_value=([], [])), \
         patch("src.pages.search.get_table_columns", return_value=pd.DataFrame([{"column_name": "id", "data_type": "int", "comment": ""}])), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame([{"grant_group_0": "group1", "principal": "user", "privilege": "SELECT"}])), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.components.html"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()
        assert not at.exception
