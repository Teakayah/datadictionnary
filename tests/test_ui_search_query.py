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
