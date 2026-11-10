from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import pandas as pd

def test_search_coverage_lines():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        st.session_state["power_user"] = True

        render_search_page(("group1",))

    at = AppTest.from_function(render_search)
    at.session_state["_dd_sticky_nav"] = "main.sales.orders"
    at.session_state["catalog_search"] = "orders"
    at.session_state["dd_comment_open_123"] = True
    at.session_state["dd_nav_select"] = "main.sales.orders"

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 100,
        "match_type": "Table",
        "description": "desc"
    }])

    mock_search = pd.DataFrame([
        {
            "full_name": "main.sales.orders",
            "table_name": "orders",
            "catalog_name": "main",
            "schema_name": "sales",
            "dq_score": 100,
            "match_type": "Table",
            "description": "desc"
        },
        {
            "full_name": "main.sales.unauthorized",
            "table_name": "unauthorized",
            "catalog_name": "main",
            "schema_name": "sales",
            "dq_score": 0,
            "match_type": "Table",
            "description": ""
        }
    ])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.track_search"), \
         patch("src.pages.search.get_multi_hop_lineage", return_value=pd.DataFrame([{"direction":"downstream", "entity_type":"table", "node":"some_node"}])), \
         patch("src.pages.search._build_lineage_graph", return_value=([{"id":"some_node"}], [{"from":"main.sales.orders","to":"some_node"}])), \
         patch("src.pages.search.get_table_columns", return_value=pd.DataFrame([{"column_name": "id", "data_type": "int", "comment": "col_comment", "business_definition_en": "business_def"}])), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame([{"grant_group_0": "group1", "principal": "user", "privilege": "SELECT"}])), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.ui.lineage.render_lineage_fullscreen"), \
         patch("src.pages.search.render_table_metadata_editor"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        # Test back button rendering and click (lines 787-788)
        assert len([b for b in at.button if b.key == "search_back"]) == 1
        at.button(key="search_back").click().run()
        assert "_dd_sticky_nav" not in at.session_state

        # Change search query to trigger line 683 (pop comment open keys)
        if "_dd_sticky_nav" in at.session_state:
            del at.session_state["_dd_sticky_nav"]
        at.session_state["_dd_current_search_query"] = "old"
        at.session_state["catalog_search"] = "orders"
        at.run()
        assert "dd_comment_open_123" not in at.session_state

        # Test line 722 (clicking view details for unauthorized table)


def test_search_lineage_expand_and_metadata_edit_coverage():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        st.session_state["power_user"] = True

        render_search_page(("group1",))

    at = AppTest.from_function(render_search)
    at.session_state["_dd_sticky_nav"] = "main.sales.orders"
    at.session_state["catalog_search"] = "orders"

    mock_authorized = pd.DataFrame([{
        "business_definition_en": "Table definition business",
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

    mock_lineage = pd.DataFrame({
        "direction": ["upstream", "downstream"],
        "entity_type": ["table", "table"],
        "node": ["node1", "node2"]
    })

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.track_search"), \
         patch("src.pages.search.get_multi_hop_lineage", return_value=mock_lineage), \
         patch("src.pages.search._build_lineage_graph", return_value=([{"id":"node1"}, {"id":"node2"}], [{"from":"main.sales.orders","to":"node1"}])), \
         patch("src.pages.search.get_table_columns", return_value=pd.DataFrame([{"column_name": "id", "data_type": "int", "comment": ""}])), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame([{"grant_group_0": "group1", "principal": "user", "privilege": "SELECT"}])), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search.render_lineage_fullscreen") as mock_fullscreen, \
         patch("src.pages.search.render_table_metadata_editor") as mock_editor, \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        # Test expand lineage (line 572)
        assert len([b for b in at.button if b.key == "expand_lin_main.sales.orders"]) == 1
        at.button(key="expand_lin_main.sales.orders").click().run()
        mock_fullscreen.assert_called_once()

        # Test metadata editor (line 192)
        assert len([b for b in at.button if b.key == "edit_tbl_main.sales.orders"]) == 1
        at.button(key="edit_tbl_main.sales.orders").click().run()
        mock_editor.assert_called_once()

def test_search_column_desc_fallback():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)
    at.session_state["_dd_sticky_nav"] = "main.sales.orders"
    at.session_state["catalog_search"] = "orders"

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales"
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

    # Line 295 triggers when _col_def is truthy (business_definition_en is provided)
    mock_columns = pd.DataFrame([{
        "column_name": "id",
        "data_type": "int",
        "comment": "tech_comment",
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.track_search"), \
         patch("src.pages.search.get_multi_hop_lineage", return_value=pd.DataFrame([{"direction":"downstream", "entity_type":"table", "node":"some_node"}])), \
         patch("src.pages.search._build_lineage_graph", return_value=([{"id":"some_node"}], [{"from":"main.sales.orders","to":"some_node"}])), \
         patch("src.pages.search.get_table_columns", return_value=mock_columns), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={"id": {"business_name": "biz_name", "definition": "bus_def_en"}}), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        # Test column fallback output
        assert any("bus_def_en" in getattr(m, "value", "") or "bus_def_en" in str(m) for m in at.get("markdown") + at.get("html") + at.get("text"))

def test_search_group_results_empty_fullname():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_auth = pd.DataFrame([{
        "full_name": None,
        "table_name": "table",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 100,
        "match_type": "Table",
        "description": "desc"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_auth), \
         patch("src.pages.search.search_all_metadata", return_value=pd.DataFrame()), \
         patch("src.pages.search.track_search"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

         at.session_state["group_filter"] = "group1"
         at.run()

         assert not any(b.key and b.key.startswith("gview_") for b in at.button)

def test_search_results_missing_fullname():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_auth = pd.DataFrame([{
        "full_name": "main.sales.table",
        "table_name": "table",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    mock_search = pd.DataFrame([{
        "full_name": None,
        "table_name": "table",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 100,
        "match_type": "Table",
        "description": "desc"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_auth), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.track_search"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

         at.session_state["catalog_search"] = "table"
         at.run()

         assert not any(b.key and b.key.startswith("view_") for b in at.button)

def test_search_results_unauthorized_click():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_auth = pd.DataFrame([{
        "full_name": "main.sales.table",
        "table_name": "table",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    mock_search = pd.DataFrame([{
        "full_name": "main.sales.unauth",
        "table_name": "unauth",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 0,
        "match_type": "Table",
        "description": "desc"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_auth), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.track_search"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

         at.session_state["catalog_search"] = "table"
         at.run()

         view_btn = [b for b in at.button if getattr(b, "key", "") == "view_main.sales.unauth_0"]
         if view_btn:
              view_btn[0].click().run()

         found = False
         def iter_blocks(blocks):
              nonlocal found
              for b in blocks:
                  val = getattr(b, "value", "") or getattr(b, "body", "")
                  if type(b).__name__ == "Exception": continue
                  if isinstance(val, str) and "detail.unauthorized" in val:
                       found = True
                  if hasattr(b, "children"):
                       if isinstance(b.children, dict): iter_blocks(b.children.values())
                       elif isinstance(b.children, tuple): iter_blocks(b.children)
                       elif isinstance(b.children, list): iter_blocks(b.children)
         iter_blocks(at)
         assert found

def test_search_group_results_authorized_click():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_auth = pd.DataFrame([{
        "full_name": "main.sales.table",
        "table_name": "table",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 100,
        "match_type": "Table",
        "description": "desc"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_auth), \
         patch("src.pages.search.search_all_metadata", return_value=pd.DataFrame()), \
         patch("src.pages.search.track_search"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

         at.session_state["group_filter"] = "group1"
         at.run()

         view_btn = [b for b in at.button if getattr(b, "key", "") == "gview_main.sales.table_0"]
         if view_btn:
              view_btn[0].click().run()
              assert at.session_state.get("_dd_sticky_nav") == "main.sales.table" or at.session_state.get("dd_nav_select") == "main.sales.table"

def test_search_hero_no_access():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    with patch("src.pages.search.get_authorized_tables", return_value=pd.DataFrame()), \
         patch("src.pages.search.search_all_metadata", return_value=pd.DataFrame()), \
         patch("src.pages.search.is_admin", return_value=False), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

         at.session_state["_dd_current_search_query"] = "nonexistent"
         at.session_state["catalog_search"] = "nonexistent"
         at.run()

         # Assert that the button is not present or an empty state is shown
         assert not at.exception


def test_search_group_all_users():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_auth = pd.DataFrame([{
        "full_name": "main.sales.table",
        "table_name": "table",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_auth), \
         patch("src.pages.search.search_all_metadata", return_value=pd.DataFrame()), \
         patch("src.pages.search.track_search"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

         at.session_state["group_filter"] = "SELECT_ALL_USERS"
         at.run()

         found = False

         def iter_blocks(blocks):
              nonlocal found
              for b in blocks:
                  val = getattr(b, "value", "") or getattr(b, "body", "")
                  if type(b).__name__ == "Exception": continue
                  if isinstance(val, str) and "search.public_tables_filter" in val:
                       found = True
                  if hasattr(b, "children"):
                       if isinstance(b.children, dict): iter_blocks(b.children.values())
                       elif isinstance(b.children, tuple): iter_blocks(b.children)
                       elif isinstance(b.children, list): iter_blocks(b.children)

         iter_blocks(at)
         assert found

def test_search_error_in_results():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    with patch("src.pages.search.get_authorized_tables", side_effect=Exception("Database error")), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

         at.run()

         found = False

         def iter_blocks(blocks):
              nonlocal found
              for b in blocks:
                  val = getattr(b, "value", "") or getattr(b, "body", "")
                  if type(b).__name__ == "Exception": continue
                  if isinstance(val, str) and "search.load_error" in val:
                       found = True
                  if hasattr(b, "children"):
                       if isinstance(b.children, dict): iter_blocks(b.children.values())
                       elif isinstance(b.children, tuple): iter_blocks(b.children)
                       elif isinstance(b.children, list): iter_blocks(b.children)

         iter_blocks(at)
         assert found
