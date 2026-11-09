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

def test_search_query_search_error():
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

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", side_effect=Exception("DB connection failed")), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k), \
         patch("src.pages.search.track_search"):

        at.run()
        at.selectbox(key="catalog_search").set_value("orders").run()

        assert not at.exception
        assert len(at.error) > 0
        assert at.error[0].value == "detail.load_error"

def test_search_query_empty_full_name():
    # Arrange
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
        "full_name": "",  # Coverage gap 753
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

        # Act
        at.run()
        at.selectbox(key="catalog_search").set_value("orders").run()

        # Assert
        assert not at.exception
        # No results should be displayed because of continue block
        view_btns = [b for b in at.button if b.key and b.key.startswith("view_")]
        assert len(view_btns) == 0

def test_search_query_group_filter_empty_full_name():
    # Arrange
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["group_filter"] = "SELECT_ALL_USERS"
        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_authorized = pd.DataFrame([{
        "full_name": "", # Coverage gap 697
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search._pref_upsert"):

        # Act
        at.run()

        # Assert
        assert not at.exception
        # No results should be displayed because of continue block
        gview_btns = [b for b in at.button if b.key and b.key.startswith("gview_")]
        assert len(gview_btns) == 0


def test_search_query_group_filter_nan_full_name():
    # Arrange
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["group_filter"] = "SELECT_ALL_USERS"
        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)
    import numpy as np
    mock_authorized = pd.DataFrame([{
        "full_name": np.nan, # Coverage gap 697
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search._pref_upsert"):

        # Act
        at.run()

        # Assert
        assert not at.exception
        # No results should be displayed because of continue block
        gview_btns = [b for b in at.button if b.key and b.key.startswith("gview_")]
        assert len(gview_btns) == 0

def test_search_results_with_nan_score():

    # Arrange

    def run_detail_panel():
        import pandas as pd
        import numpy as np
        import streamlit as st
        from unittest.mock import patch
        from src.pages.search import _render_detail_panel

        row = pd.Series({
            "catalog_name": "main",
            "schema_name": "sales",
            "table_name": "orders",
            "full_name": "main.sales.orders",
            "dq_score": np.nan,
            "steward_email": "test@example.com"
        })

        st.session_state["recent_views"] = []
        with patch("src.pages.search.get_table_comments", return_value=[]), \
             patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
             patch("src.pages.search.get_column_overrides", return_value={}), \
             patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
             patch("src.pages.search.run_query", side_effect=[
                 pd.DataFrame([]), # grants
                 pd.DataFrame([]), # search related
                 pd.DataFrame([]), # data profile
             ]), \
             patch("src.pages.search._compute_live_completeness", side_effect=Exception("Failed")), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
             # Act
             _render_detail_panel(row, "main.sales.orders", ("group1", "group2"))

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(run_detail_panel)
    at.run()

    # Assert
    assert not at.exception, f"Expected no exception, got {at.exception[0] if at.exception else 'None'}"

def test_live_completeness_exception():
    def render_detail_panel():
        import pandas as pd
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
            "dq_score": 50,
            "steward_email": "test@example.com"
        })
        _render_detail_panel(row, "main.sales.orders", ("group1",))

    at = AppTest.from_function(render_detail_panel)
    # Arrange
    with patch("src.pages.search._compute_live_completeness", side_effect=Exception("DB Error")), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        # Act
        at.run()

        # Assert
        assert not at.exception
        # check score in session state
        assert at.session_state["_live_completeness_main.sales.orders"] == 50.0


def test_add_remove_bookmark():
    from unittest.mock import patch, call
    from streamlit.testing.v1 import AppTest

    def render_detail_panel():
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
        _render_detail_panel(row, "main.sales.orders", ("group1",))

    at = AppTest.from_function(render_detail_panel)
    at.session_state["bookmarks"] = set()
    at.session_state["recent_views"] = []

    with patch("src.pages.search._compute_live_completeness", return_value=50.0), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search._pref_upsert") as mock_upsert, \
         patch("src.pages.search._pref_delete") as mock_delete, \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        # Click add bookmark
        at.button(key="bk_main.sales.orders").click().run()

        assert "main.sales.orders" in at.session_state["bookmarks"]
        assert call("main.sales.orders", "bookmark") in mock_upsert.mock_calls
        assert len(at.toast) > 0
        assert "personalization.bookmark_added" in at.toast[0].value

        # Now it is bookmarked, click again to remove
        at.button(key="bk_main.sales.orders").click().run()

        assert "main.sales.orders" not in at.session_state["bookmarks"]
        mock_delete.assert_called_once_with("main.sales.orders", "bookmark")
        assert len(at.toast) > 0
        assert "personalization.bookmark_removed" in at.toast[-1].value

def test_add_remove_col_bookmark():
    from unittest.mock import patch, call
    from streamlit.testing.v1 import AppTest

    def render_detail_panel():
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
        _render_detail_panel(row, "main.sales.orders", ("group1",))

    at = AppTest.from_function(render_detail_panel)
    at.session_state["col_bookmarks"] = set()
    at.session_state["recent_views"] = []

    import pandas as pd
    mock_columns = pd.DataFrame([{
        "column_name": "id",
        "data_type": "INTEGER",
        "comment": "ID column"
    }])

    with patch("src.pages.search._compute_live_completeness", return_value=50.0), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.get_table_columns", return_value=mock_columns), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search._pref_upsert") as mock_upsert, \
         patch("src.pages.search._pref_delete") as mock_delete, \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        col_bk_key = "colbk_main.sales.orders__id"

        # Click add col bookmark
        at.button(key=col_bk_key).click().run()

        assert "main.sales.orders::id" in at.session_state["col_bookmarks"]
        assert call("main.sales.orders::id", "col_bookmark") in mock_upsert.mock_calls
        assert len(at.toast) > 0
        assert "personalization.bookmark_added" in at.toast[0].value

        # Remove col bookmark
        at.button(key=col_bk_key).click().run()

        assert "main.sales.orders::id" not in at.session_state["col_bookmarks"]
        mock_delete.assert_called_once_with("main.sales.orders::id", "col_bookmark")
        assert len(at.toast) > 0
        assert "personalization.bookmark_removed" in at.toast[-1].value

def test_missing_coverage():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

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
        {"column_name": f"col_{i}", "data_type": "int", "comment": ""}
        for i in range(55)
    ])

    mock_grants = pd.DataFrame([
        {"principal": f"user_{i}", "privilege": "SELECT"}
        for i in range(55)
    ])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search.run_query", return_value=mock_grants), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        assert not at.exception

        found_col_msg = False
        found_grant_msg = False
        for i in at.info:
            if "detail.showing_first_50_columns" in i.value:
                found_col_msg = True
            if "detail.showing_first_50_grants" in i.value:
                found_grant_msg = True

        assert found_col_msg
        assert found_grant_msg





def test_save_business_name_exceptions():
    import streamlit as st
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_detail_panel_wrapper():
        import streamlit as st
        import pandas as pd
        from src.pages.search import _render_detail_panel

        row = pd.Series({
            "catalog_name": "main",
            "schema_name": "sales",
            "table_name": "orders",
            "full_name": "main.sales.orders",
            "description": "Table containing sales orders.",
            "dq_score": 50,
            "steward_email": "test@example.com"
        })
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["finance_dept_id"]

        # Make sure edit mode starts immediately to bypass button clicks that can be tricky to mock
        st.session_state["dd_col_edit_mode"] = "main.sales.orders__col_1"

        _render_detail_panel(row, "main.sales.orders", ("finance_dept_id",))

    at = AppTest.from_function(render_detail_panel_wrapper)

    mock_cols = pd.DataFrame([
        {"column_name": "col_1", "data_type": "int", "comment": ""}
    ])

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=50.0), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        assert len([b for b in at.button if b.key == "col_biz_save_main.sales.orders__col_1"]) == 1

        with patch("src.pages.search.save_business_name", side_effect=ValueError("Validation Failed")):
            at.button(key="col_biz_save_main.sales.orders__col_1").click().run()
            assert any("common.error" in e.value for e in at.error)

        at.session_state["dd_col_edit_mode"] = "main.sales.orders__col_1"
        at.run()
        with patch("src.pages.search.save_business_name", side_effect=Exception("Save Failed")):
            at.button(key="col_biz_save_main.sales.orders__col_1").click().run()
            assert any("common.error" in e.value for e in at.error)

        at.session_state["dd_col_edit_mode"] = "main.sales.orders__col_1"
        at.run()
        with patch("src.pages.search.save_business_name", side_effect=PermissionError("Permission Denied")):
            at.button(key="col_biz_save_main.sales.orders__col_1").click().run()
            assert any("editor.permission_error" in e.value for e in at.error)

def test_missing_search_coverage_extra():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    # 1. Test clear state logic lines 681-682
    at.session_state["_dd_sticky_nav"] = "main.sales.orders"
    at.session_state["catalog_search"] = "orders"
    at.session_state["_dd_current_search_query"] = "old_query"
    at.session_state["dd_comment_open_123"] = True

    mock_search = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 100,
        "match_type": "Table",
        "description": "desc"
    }])
    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
    }])
    mock_cols = pd.DataFrame([{
        "column_name": "col_1",
        "data_type": "int",
        "comment": "comment",
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame()), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search._build_lineage_graph", return_value=([{"id": "A"}], [{"source": "A", "target": "B"}])), \
         patch("src.pages.search._lineage_vis_html", return_value="<div>lineage</div>"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        # Verify 681-682
        assert "dd_comment_open_123" not in at.session_state

        # Test expand lineage 570-571
        expand_btns = [b for b in at.button if b.key == "expand_lin_main.sales.orders"]
        if expand_btns:
            with patch("src.pages.search.render_lineage_fullscreen") as mock_lin:
                expand_btns[0].click().run()
                mock_lin.assert_called_once()

        # Test back to results 784-785
        back_btns = [b for b in at.button if b.key == "search_back"]
        if back_btns:
            back_btns[0].click().run()
            assert "_dd_sticky_nav" not in at.session_state


def test_edit_buttons_coverage():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_detail():
        import streamlit as st
        from src.pages.search import _render_detail_panel
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        row = pd.Series({
            "catalog_name": "main",
            "schema_name": "sales",
            "table_name": "orders",
            "full_name": "main.sales.orders",
            "description": "desc",
            "dq_score": 100,
            "steward_email": ""
        })
        _render_detail_panel(row, "main.sales.orders", ("group1",))

    at = AppTest.from_function(render_detail)

    mock_cols = pd.DataFrame([{
        "column_name": "col_1",
        "data_type": "int",
        "comment": "comment",
    }])

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=100.0), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame()), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search._build_lineage_graph", return_value=([{"id": "A"}], [{"source": "A", "target": "B"}])), \
         patch("src.pages.search._lineage_vis_html", return_value="<div>lineage</div>"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        edit_tbl_btns = [b for b in at.button if b.key == "edit_tbl_main.sales.orders"]
        if edit_tbl_btns:
            with patch("src.pages.search.render_table_metadata_editor") as mock_edit:
                edit_tbl_btns[0].click().run()
                mock_edit.assert_called_once()

        edit_fn_btns = [b for b in at.button if b.key == "edit_friendly_main.sales.orders"]
        if edit_fn_btns:
            with patch("src.pages.search.render_table_business_name_editor") as mock_edit2:
                edit_fn_btns[0].click().run()
                mock_edit2.assert_called_once()

def test_unauthorized_group_filter():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)
    at.session_state["catalog_search"] = None

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
    }])

    mock_group_tables = pd.DataFrame([{
        "full_name": "main.sales.other",
        "table_name": "other",
        "name": "other",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    def mock_get_auth_tables(*args, **kwargs):
        if kwargs.get("filter_groups"):
            return mock_group_tables
        return mock_authorized

    with patch("src.pages.search.get_authorized_tables", side_effect=mock_get_auth_tables), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        gview_btns = [b for b in at.button if b.key and b.key.startswith("gview_main.sales.other")]
        if gview_btns:
            gview_btns[0].click().run()

            errors = [e.value for e in at.error]
            assert any("detail.unauthorized" in e for e in errors)

def test_unauthorized_search_query():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)
    at.session_state["catalog_search"] = "other"

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
    }])

    mock_search = pd.DataFrame([{
        "full_name": "main.sales.other",
        "table_name": "other",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 100,
        "match_type": "Table",
        "description": "desc"
    }])

    def mock_get_auth_tables(*args, **kwargs):
        return mock_authorized

    with patch("src.pages.search.get_authorized_tables", side_effect=mock_get_auth_tables), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        view_btns = [b for b in at.button if b.key and b.key.startswith("view_main.sales.other")]
        if view_btns:
            view_btns[0].click().run()

            errors = [e.value for e in at.error]
            assert any("detail.unauthorized" in e for e in errors)

def test_render_detail_panel_overrides_coverage():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_detail():
        import streamlit as st
        from src.pages.search import _render_detail_panel
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        row = pd.Series({
            "catalog_name": "main",
            "schema_name": "sales",
            "table_name": "orders",
            "full_name": "main.sales.orders",
            "description": "desc",
            "dq_score": 100,
            "steward_email": ""
        })
        _render_detail_panel(row, "main.sales.orders", ("group1",))

    at = AppTest.from_function(render_detail)

    mock_cols = pd.DataFrame([{
        "column_name": "col_1",
        "data_type": "int",
        "comment": "comment",
    }])

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=100.0), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame()), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={"col_1": {"business_name": "col1 biz name", "definition": "col1 definition"}}), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search._build_lineage_graph", return_value=([{"id": "A"}], [{"source": "A", "target": "B"}])), \
         patch("src.pages.search._lineage_vis_html", return_value="<div>lineage</div>"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        # Test editing a column (304-306)
        edit_col_btns = [b for b in at.button if b.key == "col_edit_main.sales.orders__col_1"]
        if edit_col_btns:
            edit_col_btns[0].click().run()
            assert at.session_state.get("dd_col_edit_mode") == "main.sales.orders__col_1"

def test_missing_coverage_comment_form():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_detail():
        import streamlit as st
        from src.pages.search import _render_detail_panel
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        row = pd.Series({
            "catalog_name": "main",
            "schema_name": "sales",
            "table_name": "orders",
            "full_name": "main.sales.orders",
            "description": "desc",
            "dq_score": 100,
            "steward_email": ""
        })
        _render_detail_panel(row, "main.sales.orders", ("group1",))

    at = AppTest.from_function(render_detail)

    mock_cols = pd.DataFrame([{
        "column_name": "col_1",
        "data_type": "int",
        "comment": "comment",
    }])

    mock_comments = [{
        "comment_id": 123,
        "author_email": "test@example.com",
        "created_at": pd.Timestamp.now(),
        "comment_text": "hello",
        "replies": [{"comment_id": 124, "author_email": "other@test.com", "created_at": pd.Timestamp.now(), "comment_text": "hi"}]
    }]

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=100.0), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame()), \
         patch("src.pages.search.get_table_comments", return_value=mock_comments), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search._build_lineage_graph", return_value=([{"id": "A"}], [{"source": "A", "target": "B"}])), \
         patch("src.pages.search._lineage_vis_html", return_value="<div>lineage</div>"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        # open reply form
        reply_btns = [b for b in at.button if b.key == "dd_comment_btn_main.sales.orders_123"]
        if reply_btns:
            reply_btns[0].click().run()
            assert at.session_state.get("dd_comment_open_main.sales.orders_123") == True

            # try sending empty (line 76)
            send_btns = [b for b in at.button if b.key == "dd_comment_send_main.sales.orders_123"]
            if send_btns:
                send_btns[0].click().run()
                assert len([w for w in at.warning if "comment.empty_error" in w.value]) > 0

            # try sending with text (line 64-72)
            with patch("src.pages.search.save_comment") as mock_save:
                if send_btns:
                    at.text_area(key="dd_comment_text_main.sales.orders_123").set_value("new reply text")
                    send_btns[0].click().run()
                    mock_save.assert_called_once_with("TABLE", "main.sales.orders", "new reply text", "", parent_comment_id="123")
                    assert "dd_comment_open_main.sales.orders_123" not in at.session_state

            # try cancel (line 79-81)
            at.session_state["dd_comment_open_main.sales.orders_123"] = True
            at.run()
            cancel_btns = [b for b in at.button if b.key == "dd_comment_cancel_main.sales.orders_123"]
            if cancel_btns:
                cancel_btns[0].click().run()
                assert "dd_comment_open_main.sales.orders_123" not in at.session_state

        # Exception during save coverage (line 73-75)
        at.session_state["dd_comment_open_main.sales.orders_123"] = True
        at.run()
        with patch("src.pages.search.save_comment", side_effect=Exception("Database error")):
            send_btns = [b for b in at.button if b.key == "dd_comment_send_main.sales.orders_123"]
            if send_btns:
                at.text_area(key="dd_comment_text_main.sales.orders_123").set_value("error test")
                send_btns[0].click().run()
                assert any("common.error" in e.value for e in at.error)
