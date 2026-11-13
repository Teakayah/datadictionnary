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

def test_related_tables_rendering_multiple_unique_keys():
    from streamlit.testing.v1 import AppTest
    from unittest.mock import patch

    def run_detail_panel():
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

    at = AppTest.from_function(run_detail_panel)

    import pandas as pd
    mock_cols = pd.DataFrame([])

    def mock_run_query(query, params=None):
        if "permissions_cache" in query and "columns_metadata" not in query:
            return pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])
        else:
            # We mock related tables where the table_full_name is the SAME (e.g. duplicate relationships found)
            # This exercises the unique key suffix addition logic for `rel_main.sales.related1_0`
            return pd.DataFrame([
             {"full_name": "main.sales.related1", "table_name": "related1", "catalog_name": "main", "schema_name": "sales", "relationship": "Same schema"},
             {"full_name": "main.sales.related1", "table_name": "related1", "catalog_name": "main", "schema_name": "sales", "relationship": "Shared column"}
         ])

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=50.0), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.run_query", side_effect=mock_run_query), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k), \
         patch("src.pages.search.get_multi_hop_lineage", return_value=([], [])):

        at.run()

        # Test that duplicate keys don't throw an error and buttons render correctly
        assert not at.exception

        at.button(key="rel_main.sales.related1_0").click().run()
        assert at.session_state["dd_search_override"] == "related1"
        assert at.session_state["dd_nav_select"] == "main.sales.related1"
def test_uncovered_lines_search():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def app_wrapper():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(app_wrapper)

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
        {"column_name": "col_1", "data_type": "int", "comment": "col 1 comment"}
    ])

    mock_lineage = pd.DataFrame([{
        "source": "main.sales.orders",
        "target": "main.sales.summary",
        "direction": "downstream",
        "full_name": "main.sales.summary",
        "catalog_name": "main",
        "schema_name": "sales",
        "table_name": "summary",
        "relationship": "Shared column"
    }])

    def mock_run_query(query, params=None, **kwargs):
        if "privilege" in query.lower():
            return pd.DataFrame([{"principal": "user_1", "privilege": "SELECT", "grant_group_0": "finance"}])
        return pd.DataFrame([{
            "full_name": "main.sales.summary",
            "table_name": "summary",
            "catalog_name": "main",
            "schema_name": "sales",
            "relationship": "Shared column"
        }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search.run_query", side_effect=mock_run_query), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={"col_1": {"definition": "custom def"}}), \
         patch("src.pages.search.get_multi_hop_lineage", return_value=mock_lineage), \
         patch("src.pages.search._build_lineage_graph", return_value=([{"id": "main.sales.summary", "label": "summary"}], [{"source": "main.sales.orders", "target": "main.sales.summary"}])), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        # Test back button (line 784-785)
        at.session_state["_dd_sticky_nav"] = "main.sales.orders"
        at.session_state["catalog_search"] = "orders"
        at.run()

        # Click back button
        at.button(key="search_back").click().run()
        assert "_dd_sticky_nav" not in at.session_state

        # Now test unauthorized related table click (line 721)
        at.session_state["_dd_sticky_nav"] = "main.sales.orders"
        at.session_state["catalog_search"] = "orders"
        at.run()

        # Look for the rel_ button and click it to trigger unauthorized error
        for btn in at.button:
            if btn.key and btn.key.startswith("rel_"):
                btn.click().run()
                break

        # Test fullscreen lineage button (line 571)
        at.session_state["_dd_sticky_nav"] = "main.sales.orders"
        at.run()

        for btn in at.button:
            if btn.key and btn.key.startswith("expand_lin_"):
                btn.click().run()
                break

        assert not at.exception
