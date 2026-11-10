import pytest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

@pytest.fixture(autouse=True)
def mock_t():
    with patch("src.pages.search.t", side_effect=lambda k, **kw: k) as m:
        yield m

def test_comment_form_open_and_cancel():
    def render_form():
        from src.pages.search import _render_comment_form
        _render_comment_form("table1", "steward1", "key1")

    at = AppTest.from_function(render_form)
    at.run()

    assert not at.exception
    assert len(at.button) == 1
    assert at.button[0].label == "comment.leave_a_comment"

    with patch("streamlit.rerun"):
        # Click to open the form
        at.button[0].click().run()

    # Re-run manually since rerun was mocked
    at.run()

    assert not at.exception

    # Form is open, two buttons (Send and Cancel)
    assert len(at.text_area) == 1
    assert len(at.button) == 2
    assert at.button[0].label == "comment.send"
    assert at.button[1].label == "comment.cancel"

    with patch("streamlit.rerun"):
        # Click cancel
        at.button[1].click().run()

    # Re-run manually since rerun was mocked
    at.run()

    assert not at.exception

    # Form is closed
    assert len(at.button) == 1
    assert at.button[0].label == "comment.leave_a_comment"

def test_comment_form_submit_valid():
    def render_form():
        from src.pages.search import _render_comment_form
        _render_comment_form("table1", "steward1", "key1")

    at = AppTest.from_function(render_form)
    at.run()

    with patch("streamlit.rerun"):
        # Open form
        at.button[0].click().run()
    at.run()

    with patch("src.pages.search.save_comment") as mock_save, \
         patch("streamlit.rerun"):
        # Enter text and submit
        at.text_area[0].input("My comment").run()
        at.button[0].click().run()

        mock_save.assert_called_once_with("TABLE", "table1", "My comment", "steward1", parent_comment_id=None)

    # Trigger run because rerun was mocked
    at.run()

    # Form should be closed after submit
    assert len(at.button) == 1
    assert at.button[0].label == "comment.leave_a_comment"

def test_comment_form_submit_empty():
    def render_form():
        from src.pages.search import _render_comment_form
        _render_comment_form("table1", "steward1", "key1")

    at = AppTest.from_function(render_form)
    at.run()

    with patch("streamlit.rerun"):
        # Open form
        at.button[0].click().run()
    at.run()

    with patch("src.pages.search.save_comment") as mock_save:
        # Enter text and submit
        at.text_area[0].input("   ").run()
        at.button[0].click().run()

        mock_save.assert_not_called()

    # Warning should be displayed and form stays open
    assert len(at.warning) == 1
    assert at.warning[0].value == "comment.empty_error"
    assert len(at.button) == 2

def test_comment_form_no_steward_warning():
    """Verify that a warning is shown if no steward is provided."""
    def render_form():
        from src.pages.search import _render_comment_form
        _render_comment_form("table1", "", "key1")

    at = AppTest.from_function(render_form)
    at.run()

    with patch("streamlit.rerun"):
        at.button[0].click().run()
    at.run()

    html = "\n".join([m.value for m in at.markdown])
    assert "dd-comment-no-steward" in html

def test_power_user_edit_buttons():
    """Verify that power users see edit buttons and clicking them works."""
    def render_detail_panel():
        import streamlit as st
        import pandas as pd
        from unittest.mock import patch
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
            "dq_score": 95,
            "steward_email": "test@example.com"
        })
        st.session_state["_live_completeness_main.sales.orders"] = 95
        st.session_state["recent_views"] = []
        # Set up a mock for get_table_comments to return empty list
        with patch("src.pages.search.get_table_comments", return_value=[]), \
             patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
             patch("src.pages.search.get_column_overrides", return_value={}), \
             patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
             patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
             patch("src.pages.search._pref_upsert"), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
             _render_detail_panel(row, "main.sales.orders", tuple())

    at = AppTest.from_function(render_detail_panel)

    with patch("src.pages.search.is_power_user", return_value=True):
        at.run()

    assert not at.exception

    # Check that edit buttons are rendered
    edit_tbl_btn = next((b for b in at.button if "detail.edit_table" in b.label), None)
    assert edit_tbl_btn is not None

    edit_friendly_btn = next((b for b in at.button if "detail.edit_friendly_name" in b.label), None)
    assert edit_friendly_btn is not None

def test_search_bookmark_actions():
    """Verify that bookmark toggling works."""
    def render_detail_panel():
        import streamlit as st
        import pandas as pd
        from unittest.mock import patch
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
            "dq_score": 95,
            "steward_email": "test@example.com"
        })
        st.session_state["_live_completeness_main.sales.orders"] = 95
        st.session_state["recent_views"] = []


        with patch("src.pages.search.get_table_comments", return_value=[]), \
             patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
             patch("src.pages.search.get_column_overrides", return_value={}), \
             patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
             patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
             patch("src.pages.search._pref_upsert"), \
             patch("src.pages.search._pref_delete"), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
             _render_detail_panel(row, "main.sales.orders", tuple())

    at = AppTest.from_function(render_detail_panel)
    at.session_state["bookmarks"] = {"main.sales.orders"}
    at.run()

    bk_btn = next((b for b in at.button if b.key == "bk_main.sales.orders"), None)
    with patch("streamlit.rerun"):
        bk_btn.click().run()
    assert "main.sales.orders" not in at.session_state["bookmarks"]

def test_search_data_preview_and_export():
    """Verify data preview and dictionary export buttons."""
    def render_detail_panel():
        import streamlit as st
        import pandas as pd
        from unittest.mock import patch
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
            "dq_score": 95,
            "steward_email": "test@example.com"
        })
        st.session_state["_live_completeness_main.sales.orders"] = 95
        st.session_state["recent_views"] = []

        with patch("src.pages.search.get_table_comments", return_value=[]), \
             patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
             patch("src.pages.search.get_column_overrides", return_value={}), \
             patch("src.pages.search.get_table_columns", return_value=pd.DataFrame([{"column_name": "id", "data_type": "integer", "comment": "ID"}])), \
             patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
             patch("src.pages.search.render_data_sample"), \
             patch("src.pages.search._pref_upsert"), \
             patch("src.pages.search.export_schema_to_csv", return_value="id,integer"), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
             _render_detail_panel(row, "main.sales.orders", tuple())

    at = AppTest.from_function(render_detail_panel)
    at.session_state["bookmarks"] = {"main.sales.orders"}
    at.run()

    preview_btn = next((b for b in at.button if b.key == "preview_main.sales.orders"), None)
    assert preview_btn is not None
    preview_btn.click().run()
    assert not at.exception

def test_search_business_name_editor_click():
    """Verify that clicking the 'Edit Business Name' button executes successfully without errors."""
    def render_detail_panel():
        import streamlit as st
        import pandas as pd
        from unittest.mock import patch
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
            "dq_score": 95,
            "steward_email": "test@example.com"
        })
        st.session_state["_live_completeness_main.sales.orders"] = 95
        st.session_state["recent_views"] = []

        with patch("src.pages.search.get_table_comments", return_value=[]), \
             patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
             patch("src.pages.search.get_column_overrides", return_value={}), \
             patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
             patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
             patch("src.pages.search._pref_upsert"), \
             patch("src.pages.search.render_table_business_name_editor"), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
             _render_detail_panel(row, "main.sales.orders", tuple())

    at = AppTest.from_function(render_detail_panel)
    with patch("src.pages.search.is_power_user", return_value=True):
        at.run()

    edit_btn = next((b for b in at.button if "detail.edit_friendly_name" in b.label), None)
    assert edit_btn is not None
    with patch("src.pages.search.is_power_user", return_value=True):
        edit_btn.click().run()
    assert not at.exception

def test_search_related_open_button_click():
    """Verify that clicking the 'Open' button on a related table updates session state and reruns."""
    def render_detail_panel():
        import streamlit as st
        import pandas as pd
        from unittest.mock import patch
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
            "dq_score": 95,
            "steward_email": "test@example.com"
        })
        st.session_state["_live_completeness_main.sales.orders"] = 95
        st.session_state["recent_views"] = []

        with patch("src.pages.search.get_table_comments", return_value=[]), \
             patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
             patch("src.pages.search.get_column_overrides", return_value={}), \
             patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
             patch("src.pages.search.run_query", return_value=pd.DataFrame([
                 {"full_name": "main.sales.customers", "table_name": "customers", "schema_name": "sales", "catalog_name": "main", "relationship": "Same schema", "dq_score": 88}
             ])), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
             _render_detail_panel(row, "main.sales.orders", tuple())

    at = AppTest.from_function(render_detail_panel)
    at.session_state["bookmarks"] = {"main.sales.orders"}
    at.run()

    rel_btn = next((b for b in at.button if b.key == "rel_main.sales.customers"), None)
    assert rel_btn is not None
    with patch("streamlit.rerun"):
        rel_btn.click().run()
    assert at.session_state["dd_search_override"] == "customers"

def test_search_page_hero_and_load_error():
    """Verify that the search page renders the hero, and handles get_authorized_tables exception."""
    def app_wrapper():
        from unittest.mock import patch
        from src.pages.search import render_search_page
        with patch("src.pages.search.get_authorized_tables", side_effect=Exception("DB connection error")), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
            render_search_page(tuple())

    at = AppTest.from_function(app_wrapper)
    at.run()
    assert len(at.error) > 0
    assert at.error[0].value == "search.load_error"

def test_search_page_grants_rendered_with_query_groups():
    """Verify that the search page renders the grants correctly when query groups are provided."""
    def render_detail_panel():
        import streamlit as st
        import pandas as pd
        from unittest.mock import patch
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
            "dq_score": 95,
            "steward_email": "test@example.com"
        })
        st.session_state["_live_completeness_main.sales.orders"] = 95
        st.session_state["recent_views"] = []

        with patch("src.pages.search.get_table_comments", return_value=[]), \
             patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
             patch("src.pages.search.get_column_overrides", return_value={}), \
             patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
             patch("src.pages.search.run_query", side_effect=[
                 pd.DataFrame([{"principal": "sales_team", "privilege": "SELECT"}]), # for grants
                 pd.DataFrame([]), # for search related
                 pd.DataFrame([]), # for data profile
             ]), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
             _render_detail_panel(row, "main.sales.orders", ("group1", "group2"))

    at = AppTest.from_function(render_detail_panel)
    at.session_state["bookmarks"] = {"main.sales.orders"}
    at.run()

    assert not at.exception
    grant_btn = next((b for b in at.button if b.key and "sales_team" in b.key), None)
    assert grant_btn is not None
    grant_btn.click().run()
    assert at.session_state["group_filter"] == "sales_team"

def test_search_page_no_access():
    """Verify that the search page handles empty authorized tables."""
    def app_wrapper():
        import pandas as pd
        from unittest.mock import patch
        from src.pages.search import render_search_page
        with patch("src.pages.search.get_authorized_tables", return_value=pd.DataFrame()), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
            render_search_page(tuple())

    at = AppTest.from_function(app_wrapper)
    at.run()
    assert len(at.markdown) > 0
    assert any("search.no_access" in md.value for md in at.markdown)

def test_search_page_active_group():
    """Verify that the search page renders the correct info and handles group filters."""
    def app_wrapper():
        import pandas as pd
        from unittest.mock import patch
        from src.pages.search import render_search_page
        with patch("src.pages.search.get_authorized_tables", return_value=pd.DataFrame({"full_name": ["main.sales.orders"], "table_name": ["orders"], "catalog_name": ["main"], "schema_name": ["sales"], "dq_score": [95]})), \
             patch("src.pages.search.search_all_metadata", return_value=pd.DataFrame({"full_name": ["main.sales.orders"], "table_name": ["orders"], "catalog_name": ["main"], "schema_name": ["sales"], "dq_score": [95], "match_type": ["Table"]})), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
            render_search_page(tuple())

    at = AppTest.from_function(app_wrapper)
    at.session_state["group_filter"] = "finance"
    at.run()

    back_btn = next((b for b in at.button if "common.back" in b.label), None)
    assert back_btn is not None
    with patch("streamlit.rerun"):
        back_btn.click().run()
    assert "group_filter" not in at.session_state

def test_search_page_search_query_execution():
    """Verify that search query executes and shows results."""
    def app_wrapper():
        import pandas as pd
        from unittest.mock import patch
        from src.pages.search import render_search_page
        with patch("src.pages.search.get_authorized_tables", return_value=pd.DataFrame({"full_name": ["main.sales.orders"], "table_name": ["orders"], "catalog_name": ["main"], "schema_name": ["sales"], "dq_score": [95]})), \
             patch("src.pages.search.search_all_metadata", return_value=pd.DataFrame({"full_name": ["main.sales.orders"], "table_name": ["orders"], "catalog_name": ["main"], "schema_name": ["sales"], "dq_score": [95], "match_type": ["Table"]})), \
             patch("src.pages.search.track_search"), \
             patch("src.pages.search._render_detail_panel"), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
            render_search_page(tuple())

    at = AppTest.from_function(app_wrapper)
    at.session_state["_dd_current_search_query"] = "orders"
    at.session_state["catalog_search"] = "orders"
    at.run()

    view_btn = next((b for b in at.button if "search.view_details" in b.label), None)
    assert view_btn is not None
    with patch("streamlit.rerun"):
        view_btn.click().run()

    assert at.session_state["_dd_sticky_nav"] == "main.sales.orders"

def test_comment_form_submit_error():
    """Verify that an error is shown if saving the comment fails."""
    def run_with_error():
        from src.pages.search import _render_comment_form
        from unittest.mock import patch

        with patch("src.pages.search.t", side_effect=lambda k, **kw: k):
            with patch("src.pages.search.save_comment", side_effect=Exception("DB Error")):
                _render_comment_form("table1", "steward1", "key1")

    at2 = AppTest.from_function(run_with_error)
    at2.session_state["dd_comment_open_key1"] = True
    at2.run()

    text_area = at2.text_area[0]
    text_area.set_value("My comment").run()

    send_btn = next(b for b in at2.button if b.label == "comment.send")
    send_btn.click().run()

    assert len(at2.error) > 0
    assert at2.error[0].value == "common.error"


def test_search_page_grants_rendered_with_query_groups_public():
    """Verify that the search page renders the grants correctly when query groups are provided."""
    def render_detail_panel():
        import streamlit as st
        import pandas as pd
        from unittest.mock import patch
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
            "dq_score": 95,
            "steward_email": "test@example.com"
        })
        st.session_state["_live_completeness_main.sales.orders"] = 95
        st.session_state["recent_views"] = []

        with patch("src.pages.search.get_table_comments", return_value=[]), \
             patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
             patch("src.pages.search.get_column_overrides", return_value={}), \
             patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
             patch("src.pages.search.run_query", side_effect=[
                 pd.DataFrame([{"principal": "SELECT_ALL_USERS", "privilege": "SELECT"}]), # for grants
                 pd.DataFrame([]), # for search related
                 pd.DataFrame([]), # for data profile
             ]), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
             _render_detail_panel(row, "main.sales.orders", ("group1", "group2"))

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(render_detail_panel)
    at.session_state["bookmarks"] = {"main.sales.orders"}
    at.run()

    assert not at.exception
    grant_btn = next((b for b in at.button if b.key and "public" in b.key), None)
    assert grant_btn is not None

    grant_btn.click().run()
    assert at.session_state["group_filter"] == "SELECT_ALL_USERS"


def test_search_comments_rendering():
    """Verify that comments and replies are rendered properly and reply form opens."""
    def render_detail_panel():
        import streamlit as st
        import pandas as pd
        from unittest.mock import patch
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
            "dq_score": 95,
            "steward_email": "test@example.com"
        })
        st.session_state["_live_completeness_main.sales.orders"] = 95
        st.session_state["recent_views"] = []

        mock_comments = [
            {
                "comment_id": "c1",
                "author_name": "Alice",
                "comment_text": "First comment",
                "created_at": "2023-01-01T12:00:00Z",
                "replies": [
                    {
                        "comment_id": "r1",
                        "author_name": "Bob",
                        "comment_text": "Reply to first comment",
                        "created_at": "2023-01-02T12:00:00Z"
                    }
                ]
            }
        ]

        with patch("src.pages.search.get_table_comments", return_value=mock_comments), \
             patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
             patch("src.pages.search.get_column_overrides", return_value={}), \
             patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
             patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
             patch("src.pages.search._pref_upsert"), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k), \
             patch("src.pages.search.format_date", return_value="formatted date", create=True), \
             patch("src.pages.search.format_number", return_value="2", create=True):
             _render_detail_panel(row, "main.sales.orders", tuple())

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(render_detail_panel)
    at.session_state["bookmarks"] = {"main.sales.orders"}
    at.run()

    # Verify rendering by ensuring no exceptions and that the reply button is present
    assert not at.exception

    # Try to open reply form
    reply_btn = next((b for b in at.button if b.key == "dd_comment_btn_main.sales.orders_c1"), None)
    assert reply_btn is not None

    with patch("streamlit.rerun"):
        reply_btn.click().run()

    assert at.session_state["dd_comment_open_main.sales.orders_c1"] is True


def test_search_comments_replies_render():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    import pandas as pd
    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    mock_search_results = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "match_type": "Table",
        "catalog_name": "main",
        "schema_name": "sales",
        "description": "Sales orders"
    }])

    mock_comments = [{
        "comment_id": "c1",
        "author_name": "John Doe",
        "created_at": "2023-01-01T10:00:00Z",
        "comment_text": "This is a comment",
        "replies": [{
            "author_name": "Jane Doe",
            "created_at": "2023-01-01T11:00:00Z",
            "comment_text": "This is a reply"
        }]
    }]

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search_results), \
         patch("src.pages.search.get_table_steward", return_value="steward@example.com"), \
         patch("src.pages.search.get_table_comments", return_value=mock_comments), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.get_table_columns", return_value=pd.DataFrame(columns=["column_name", "data_type", "comment"])), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
         patch("src.pages.search.track_search"):

        at.run()
        at.selectbox(key="catalog_search").set_value("orders").run()

        # Click view details
        buttons = at.button
        view_btns = [b for b in buttons if b.key and b.key.startswith("view_")]
        view_btns[0].click().run()

        # Check that we can see comment rendering elements
        markdown_values = [m.value for m in at.markdown]

        has_comment = any("This is a comment" in val for val in markdown_values)
        has_reply = any("This is a reply" in val for val in markdown_values)

        assert has_comment, "Comment not rendered"
        assert has_reply, "Reply not rendered"


def test_search_column_bookmark_actions():
    """Verify that column bookmark toggling works."""
    from streamlit.testing.v1 import AppTest
    def render_detail_panel():
        import streamlit as st
        import pandas as pd
        from unittest.mock import patch
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
            "dq_score": 95,
            "steward_email": "test@example.com"
        })
        st.session_state["_live_completeness_main.sales.orders"] = 95
        st.session_state["recent_views"] = []

        with patch("src.pages.search.get_table_comments", return_value=[]), \
             patch("src.pages.search.get_table_steward", return_value="test@example.com"), \
             patch("src.pages.search.get_column_overrides", return_value={}), \
             patch("src.pages.search.get_table_columns", return_value=pd.DataFrame([{"column_name": "amount", "data_type": "DOUBLE", "comment": "Order amount"}])), \
             patch("src.pages.search.run_query", return_value=pd.DataFrame(columns=["grant_group_0", "principal", "privilege"])), \
             patch("src.pages.search._pref_upsert"), \
             patch("src.pages.search._pref_delete"), \
             patch("src.pages.search.t", side_effect=lambda k, **kw: k):
             _render_detail_panel(row, "main.sales.orders", tuple())

    at = AppTest.from_function(render_detail_panel)
    at.session_state["col_bookmarks"] = {"main.sales.orders::amount"}
    at.run()

    # Find the button and remove the bookmark
    bk_btn = next((b for b in at.button if b.key == "colbk_main.sales.orders__amount"), None)

    from unittest.mock import patch
    with patch("streamlit.rerun"):
        bk_btn.click().run()

    assert "main.sales.orders::amount" not in at.session_state["col_bookmarks"]

    # Now test adding a bookmark
    at = AppTest.from_function(render_detail_panel)
    at.session_state["col_bookmarks"] = set()
    at.run()

    bk_btn = next((b for b in at.button if b.key == "colbk_main.sales.orders__amount"), None)
    with patch("streamlit.rerun"):
        bk_btn.click().run()

    assert "main.sales.orders::amount" in at.session_state["col_bookmarks"]
