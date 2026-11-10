import re

with open("tests/test_ui_search_query.py", "r") as f:
    content = f.read()

new_test = """
def test_search_prev_query_clear_state():
    from unittest.mock import patch
    import pandas as pd
    from streamlit.testing.v1 import AppTest

    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)
    at.session_state["_dd_current_search_query"] = "old_query"
    at.session_state["catalog_search"] = "new_query"
    at.session_state["dd_col_edit_mode"] = "something"
    at.session_state["dd_comment_open_1"] = True
    at.session_state["_dd_sticky_nav"] = "main.sales.orders"

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 100,
        "match_type": "Table",
        "description": "desc"
    }])

    mock_search = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 100,
        "match_type": "Table",
        "description": "desc"
    }])

    mock_cols = pd.DataFrame([
        {"column_name": "col_1", "data_type": "int", "comment": ""}
    ])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \\
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \\
         patch("src.pages.search.get_table_columns", return_value=mock_cols), \\
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \\
         patch("src.pages.search.get_table_comments", return_value=[]), \\
         patch("src.pages.search.get_table_steward", return_value=""), \\
         patch("src.pages.search.get_column_overrides", return_value={}), \\
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        assert "dd_col_edit_mode" not in at.session_state
        assert "dd_comment_open_1" not in at.session_state
        assert "_dd_sticky_nav" not in at.session_state
"""

if "test_search_prev_query_clear_state" not in content:
    with open("tests/test_ui_search_query.py", "a") as f:
        f.write("\n" + new_test)

with open("src/ui/cards/discovery.py", "r") as f:
    disc_content = f.read()

disc_content = disc_content.replace('    else:\n        _render_empty_state("🔒", t("discovery.sign_in_prompt"))\n', "")

with open("src/ui/cards/discovery.py", "w") as f:
    f.write(disc_content)
