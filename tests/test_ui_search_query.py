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


def test_search_sticky_nav_persistence():
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
        "schema_name": "sales",
        "steward": "steward@example.com"
    }])

    mock_search = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "match_type": "Table",
        "catalog_name": "main",
        "schema_name": "sales",
        "description": "Sales orders",
        "dq_score": 100,
        "name": "orders"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search._render_detail_panel") as mock_detail:

        # Run 1: initial render (search_query = None)
        at.run()

        # Run 2: Set search to "orders"
        at.selectbox(key="catalog_search").set_value("orders").run()

        # Check that we have a button called "view_main.sales.orders_0"
        view_btn = [b for b in at.button if b.key == "view_main.sales.orders_0"]
        assert len(view_btn) == 1

        # Run 3: Click "View Details"
        view_btn[0].click().run()

        # Verify we are on details page (back button is visible)
        back_btn = [b for b in at.button if b.key == "search_back"]
        assert len(back_btn) == 1

        # Run 4: Force a rerun by changing some unrelated state, e.g., a dummy checkbox
        # Streamlit sometimes reruns just because we interact with other things.
        # But wait, what if we simulate a rerun just directly?
        at.run()

        # In a real app, _dd_sticky_nav would persist across reruns.
        # Is it still here?
        back_btn_after = [b for b in at.button if b.key == "search_back"]
        assert len(back_btn_after) == 1

        # Now what happens if we click back?
        back_btn_after[0].click().run()
        assert "_dd_sticky_nav" not in at.session_state

def test_search_nav_select_unauthorized():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_nav_select"] = "unauthorized.table.name"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
        "steward": "steward@example.com"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search._render_detail_panel") as mock_detail:

        at.run()

        assert "_dd_sticky_nav" not in at.session_state

def test_search_sticky_nav_missing_coverage():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_nav_select"] = "main.sales.orders"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
        "steward": "steward@example.com"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search._render_detail_panel") as mock_detail:

        at.run()

        # Test dd_nav_select hits lines 638-640
        assert at.session_state["_dd_sticky_nav"] == "main.sales.orders"

def test_search_search_override():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_search_override"] = "my_table"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.my_table",
        "table_name": "my_table",
        "catalog_name": "main",
        "schema_name": "sales",
        "steward": "steward@example.com"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search._render_detail_panel") as mock_detail:

        at.run()

        assert "dd_search_override" not in at.session_state
        assert at.session_state["_dd_current_search_query"] == "my_table"
        assert at.session_state["catalog_search"] == "my_table"


def test_search_group_filter_back_button():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        if "group_filter" not in st.session_state:
            st.session_state["group_filter"] = "finance"

        render_search_page(("finance",))

    at = AppTest.from_function(render_search)

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.my_table",
        "table_name": "my_table",
        "catalog_name": "main",
        "schema_name": "sales",
        "steward": "steward@example.com"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search._render_detail_panel") as mock_detail:

        at.run()

        back_btn = [b for b in at.button if not str(b.key).startswith("gview_") and not str(b.key).startswith("view_")]

        assert len(back_btn) == 1
        back_btn[0].click().run()

        # Verify the group filter info is now gone instead of checking dict
        assert not any(i.value == "search.group_filter_active" for i in at.info)


def test_search_all_tables_none_or_empty():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    # Test 1: _all_tables is None (Exception in get_authorized_tables)
    with patch("src.pages.search.get_authorized_tables", side_effect=Exception("DB Error")), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: f"mocked_{k}"):
        at.run()
        # Verify the error message using our mocked translation
        assert any(e.value == "mocked_search.load_error" for e in at.error)

    # Test 2: _all_tables is empty
    empty_df = pd.DataFrame(columns=["full_name", "table_name"])
    with patch("src.pages.search.get_authorized_tables", return_value=empty_df), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: f"mocked_{k}"):
        at.run()
        # Empty state renders with "mocked_search.no_access"
        assert any("mocked_search.no_access" in getattr(m, "value", "") for m in at.markdown)

def test_search_group_filter_view_details():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        if "group_filter" not in st.session_state:
            st.session_state["group_filter"] = "finance"

        render_search_page(("finance",))

    at = AppTest.from_function(render_search)

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.my_table",
        "table_name": "my_table",
        "catalog_name": "main",
        "schema_name": "sales",
        "steward": "steward@example.com"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search._render_detail_panel") as mock_detail:

        at.run()

        # In group filter view, results are just a list of tables. They have a "View Details" button.
        view_btns = [b for b in at.button if str(b.key).startswith("gview_")]
        assert len(view_btns) == 1

        view_btns[0].click().run()

        assert at.session_state["_dd_current_search_query"] == "my_table"
        assert at.session_state["catalog_search"] == "my_table"
        assert at.session_state["_dd_sticky_nav"] == "main.sales.my_table"

def test_search_group_filter_view_details_unauthorized_really():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        if "group_filter" not in st.session_state:
            st.session_state["group_filter"] = "finance"

        render_search_page(("finance",))

    at = AppTest.from_function(render_search)

    mock_all_tables = pd.DataFrame([{
        "full_name": 123.0,
        "table_name": "my_table",
        "catalog_name": "main",
        "schema_name": "sales",
        "steward": "steward@example.com"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_all_tables), \
         patch("src.pages.search._render_detail_panel") as mock_detail, \
         patch("src.pages.search.t", side_effect=lambda k, **kw: f"mocked_{k}"):

        at.run()

        view_btns = [b for b in at.button if str(b.key).startswith("gview_")]
        assert len(view_btns) == 1

        view_btns[0].click().run()

        assert any(e.value == "mocked_detail.unauthorized" for e in at.error)

def test_search_help_admin_power_user():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.authorized",
        "table_name": "authorized",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search.is_admin", return_value=True), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: f"mocked_{k}"):

        at.run()

        found_editor = False
        found_admin = False
        for mk in at.markdown:
            if "mocked_help.search_extra_editor" in getattr(mk, "value", ""):
                found_editor = True
            if "mocked_help.search_extra_admin" in getattr(mk, "value", ""):
                found_admin = True

        assert found_editor
        assert found_admin

def test_search_track_analytics_failure():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_search_override"] = "authorized"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.authorized",
        "table_name": "authorized",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.track_search", side_effect=Exception("Analytics DB down")), \
         patch("src.pages.search._render_detail_panel") as mock_detail:

        at.run()

        assert not at.exception

def test_search_edit_table_metadata_real():
    def render_search():
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
            "steward_email": "test@example.com",
            "comment": "foo",
            "business_name_en": "Orders"
        })
        _render_detail_panel(row, "main.sales.orders", ("finance_dept_id",))

    at = AppTest.from_function(render_search)

    mock_cols = pd.DataFrame([
        {"column_name": "col_1", "data_type": "int", "comment": ""}
    ])

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=50.0), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search.render_table_metadata_editor") as mock_edit_meta, \
         patch("src.pages.search.render_table_business_name_editor") as mock_edit_biz:

        at.run()

        edit_tbl_btn = [b for b in at.button if b.key == "edit_tbl_main.sales.orders"]
        edit_friendly_btn = [b for b in at.button if b.key == "edit_friendly_main.sales.orders"]

        assert len(edit_tbl_btn) == 1
        assert len(edit_friendly_btn) == 1

        edit_tbl_btn[0].click().run()
        mock_edit_meta.assert_called_once()

        edit_friendly_btn = [b for b in at.button if b.key == "edit_friendly_main.sales.orders"]
        edit_friendly_btn[0].click().run()
        mock_edit_biz.assert_called_once()

def test_search_column_biz_and_def():
    def render_search():
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
            "steward_email": "test@example.com",
            "comment": "foo",
            "business_name_en": "Orders"
        })
        _render_detail_panel(row, "main.sales.orders", ("finance_dept_id",))

    at = AppTest.from_function(render_search)

    mock_cols = pd.DataFrame([
        {
            "column_name": "col_1",
            "data_type": "int",
            "comment": "tech comment"
        }
    ])

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=50.0), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={
             "col_1": {
                 "business_name_en": "Business Name",
                 "business_name": "Business Name",
                 "definition_en": "Business Definition",
                 "definition": "Business Definition",
                 "business_definition": "Business Definition"
             }
         }), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search.is_power_user", return_value=True):

        at.run()

        found_biz = False
        found_def = False
        for mk in at.markdown:
            val = getattr(mk, "value", "")
            if "Business Name" in val:
                found_biz = True
            if "Business Definition" in val:
                found_def = True

        assert found_biz
        assert found_def

def test_search_column_edit_buttons():
    def render_search():
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
            "steward_email": "test@example.com",
            "comment": "foo",
            "business_name_en": "Orders"
        })
        _render_detail_panel(row, "main.sales.orders", ("finance_dept_id",))

    at = AppTest.from_function(render_search)

    mock_cols = pd.DataFrame([
        {
            "column_name": "col_1",
            "data_type": "int",
            "comment": "tech comment"
        }
    ])

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=50.0), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={
             "col_1": {
                 "business_name_en": "Business Name",
                 "business_definition_en": "Business Definition",
                 "edited_by": "test@example.com",
                 "edited_at": "2023-01-01"
             }
         }), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search.is_power_user", return_value=True):

        at.run()

        edit_col_btn = [b for b in at.button if b.key == "col_edit_main.sales.orders__col_1"]
        assert len(edit_col_btn) == 1

        edit_col_btn[0].click().run()

        assert at.session_state["dd_col_edit_mode"] == "main.sales.orders__col_1"


def test_search_column_edit_save():
    def render_search():
        import streamlit as st
        import pandas as pd
        from src.pages.search import _render_detail_panel

        st.session_state["user_email"] = "test@example.com"

        # Streamlit AppTest doesn't always clear keys popped during the app run if they were
        # initially set in the wrapper dict. So we won't assert it's missing, we just assert
        # mock_save was called.
        if "dd_col_edit_mode" not in st.session_state:
            st.session_state["dd_col_edit_mode"] = "main.sales.orders__col_1"

        row = pd.Series({
            "catalog_name": "main",
            "schema_name": "sales",
            "table_name": "orders",
            "full_name": "main.sales.orders",
            "description": "Table containing sales orders.",
            "dq_score": 50,
            "steward_email": "test@example.com",
            "comment": "foo",
            "business_name_en": "Orders"
        })
        _render_detail_panel(row, "main.sales.orders", ("finance_dept_id",))

    at = AppTest.from_function(render_search)

    mock_cols = pd.DataFrame([
        {
            "column_name": "col_1",
            "data_type": "int",
            "comment": "tech comment"
        }
    ])

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=50.0), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search.save_business_name") as mock_save:

        at.run()

        save_btn = [b for b in at.button if b.key == "col_biz_save_main.sales.orders__col_1"]
        assert len(save_btn) == 1

        save_btn[0].click().run()

        mock_save.assert_called_once()

def test_search_column_edit_cancel():
    def render_search():
        import streamlit as st
        import pandas as pd
        from src.pages.search import _render_detail_panel

        st.session_state["user_email"] = "test@example.com"
        if "dd_col_edit_mode" not in st.session_state:
            st.session_state["dd_col_edit_mode"] = "main.sales.orders__col_1"
        row = pd.Series({
            "catalog_name": "main",
            "schema_name": "sales",
            "table_name": "orders",
            "full_name": "main.sales.orders",
            "description": "Table containing sales orders.",
            "dq_score": 50,
            "steward_email": "test@example.com",
            "comment": "foo",
            "business_name_en": "Orders"
        })
        _render_detail_panel(row, "main.sales.orders", ("finance_dept_id",))

    at = AppTest.from_function(render_search)

    mock_cols = pd.DataFrame([
        {
            "column_name": "col_1",
            "data_type": "int",
            "comment": "tech comment"
        }
    ])

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=50.0), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search.is_power_user", return_value=True):

        at.run()

        cancel_btn = [b for b in at.button if b.key == "col_biz_cancel_main.sales.orders__col_1"]
        assert len(cancel_btn) == 1

        cancel_btn[0].click().run()


def test_search_query_change_clears_state():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.my_table",
        "table_name": "my_table",
        "catalog_name": "main",
        "schema_name": "sales",
        "steward": "steward@example.com"
    }, {
        "full_name": "main.sales.other_table",
        "table_name": "other_table",
        "catalog_name": "main",
        "schema_name": "sales",
        "steward": "steward@example.com"
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search._render_detail_panel") as mock_detail:

        at.run()

        # Initial search query is set
        at.selectbox(key="catalog_search").set_value("my_table").run()

        # Set some state variables that should be cleared
        # We need to set them via at.session_state, then trigger another run
        at.session_state["dd_col_edit_mode"] = "some_col"
        at.session_state["dd_comment_open_1"] = True
        at.session_state["dd_comment_open_2"] = False
        at.session_state["_dd_sticky_nav"] = "some_nav"

        # Change the search query
        at.selectbox(key="catalog_search").set_value("other_table").run()

        assert "dd_col_edit_mode" not in at.session_state
        assert "dd_comment_open_1" not in at.session_state
        assert "dd_comment_open_2" not in at.session_state
        assert "_dd_sticky_nav" not in at.session_state

def test_search_comments_render():
    def render_search():
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
            "steward_email": "test@example.com",
            "comment": "foo",
            "business_name_en": "Orders"
        })
        _render_detail_panel(row, "main.sales.orders", ("finance_dept_id",))

    at = AppTest.from_function(render_search)

    mock_cols = pd.DataFrame([
        {
            "column_name": "col_1",
            "data_type": "int",
            "comment": "tech comment"
        }
    ])

    mock_comments = [
        {
            "comment_id": "c1",
            "author_name": "Alice",
            "created_at": "2023-01-01T00:00:00Z",
            "comment_text": "First comment",
            "replies": [
                {
                    "author_name": "Bob",
                    "created_at": "2023-01-02T00:00:00Z",
                    "comment_text": "First reply"
                }
            ]
        }
    ]

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=50.0), \
         patch("src.pages.search.get_table_comments", return_value=mock_comments), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search.is_power_user", return_value=True):

        at.run()

        found_comment = False
        found_reply = False
        for mk in at.markdown:
            val = getattr(mk, "value", "")
            if "First comment" in val and "Alice" in val:
                found_comment = True
            if "First reply" in val and "Bob" in val:
                found_reply = True

        assert found_comment
        assert found_reply
