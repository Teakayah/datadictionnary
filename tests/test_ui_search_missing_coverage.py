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

def test_missing_business_branches():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_detail_panel_wrapper():
        import streamlit as st
        import pandas as pd
        from src.pages.search import _render_detail_panel

        st.session_state["user_email"] = "test@example.com"

        row = pd.Series({
            "catalog_name": "main",
            "schema_name": "sales",
            "table_name": "orders",
            "full_name": "main.sales.orders",
            "description": "Table containing sales orders.",
            "dq_score": 50,
            "steward_email": "test@example.com"
        })

        _render_detail_panel(row, "main.sales.orders", ("finance_dept_id",))

    at = AppTest.from_function(render_detail_panel_wrapper)

    mock_cols = pd.DataFrame([
        {"column_name": "col_2", "data_type": "int", "comment": "Original Comment 2"}
    ])

    mock_overrides = {
        "col_2": {
            "business_name": "Business Name 2",
        }
    }

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=50.0), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value=mock_overrides), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k), \
         patch("src.pages.search.is_power_user", return_value=False):

        at.run()

        assert not at.exception
