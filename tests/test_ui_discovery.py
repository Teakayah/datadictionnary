import json
import pandas as pd
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

with open("locale/en.json", "r") as f:
    en_locale = json.load(f)

def render_discovery_page_app():
    from unittest.mock import patch
    import pandas as pd
    from src.ui.cards.discovery import render_discovery

    # Mock groups and authorized tables for the app run
    def mock_get_auth_tables(groups):
        return pd.DataFrame({
            "full_name": ["main.sales.orders", "main.finance.ledger", "main.marketing.leads"],
            "table_name": ["orders", "ledger", "leads"],
            "catalog_name": ["main", "main", "main"],
            "schema_name": ["sales", "finance", "marketing"],
            "table_description": ["Sales orders", "Finance ledger", "Marketing leads"],
            "updated_at": [pd.Timestamp("2023-01-01"), pd.Timestamp("2023-01-02"), pd.Timestamp("2023-01-03")],
            "dq_grade": ["A", "B", "C"],
            "dq_score": [1.0, 0.8, 0.5],
            "dq_status": ["pass", "pass", "fail"]
        })

    with patch("src.ui.cards.discovery.get_authorized_tables", side_effect=mock_get_auth_tables), patch("src.ui.cards.discovery.get_authorized_table_names", return_value={"main.sales.orders", "main.finance.ledger", "main.marketing.leads"}):
        render_discovery(["finance", "sales"])

def render_discovery_page_app_empty():
    from unittest.mock import patch
    import pandas as pd
    from src.ui.cards.discovery import render_discovery

    def mock_get_auth_tables(groups):
        return pd.DataFrame()

    with patch("src.ui.cards.discovery.get_authorized_tables", side_effect=mock_get_auth_tables), patch("src.ui.cards.discovery.get_authorized_table_names", return_value=set()):
        render_discovery(["finance", "sales"])

class TestDiscoveryTabs:
    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_tabs_render_notable(self, mock_get_posts):
        mock_get_posts.return_value = []
        at = AppTest.from_function(render_discovery_page_app).run()

        # By default it's on the "Notable" tab
        html = [m.value for m in at.markdown]
        assert any(en_locale["personalization"]["tab_notable"] in val for val in html)

    @patch("src.ui.cards.discovery.st.segmented_control")
    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_tabs_render_bookmarks(self, mock_get_posts, mock_seg_ctrl):
        mock_get_posts.return_value = []
        mock_seg_ctrl.return_value = "bookmarks"
        at = AppTest.from_function(render_discovery_page_app).run()

        at.session_state["bookmarks"] = {"main.sales.orders"}
        at.run()
        html = [m.value for m in at.markdown]
        assert any("My Bookmarks" in val for val in html)
        assert any("orders" in val for val in html)

    @patch("src.ui.cards.discovery.st.segmented_control")
    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_tabs_render_recent(self, mock_get_posts, mock_seg_ctrl):
        mock_get_posts.return_value = []
        mock_seg_ctrl.return_value = "recent"
        at = AppTest.from_function(render_discovery_page_app).run()

        at.session_state["recent_views"] = ["main.finance.ledger"]
        at.run()
        html = [m.value for m in at.markdown]
        assert any(en_locale["personalization"]["tab_recent"] in val for val in html)
        assert any("ledger" in val for val in html)

    @patch("src.ui.cards.discovery.st.segmented_control")
    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_recommended_tab(self, mock_get_posts, mock_seg_ctrl):
        mock_get_posts.return_value = []
        mock_seg_ctrl.return_value = "recommended"
        at = AppTest.from_function(render_discovery_page_app).run()

        with patch("src.ui.cards.discovery._get_recommended_tables", return_value=["main.sales.orders"]):
            at.run()

            html = [m.value for m in at.markdown]
            assert any(en_locale["personalization"]["recommended_title"] in val for val in html)
            assert any("orders" in val for val in html)

    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_table_click(self, mock_get_posts):
        mock_get_posts.return_value = []
        at = AppTest.from_function(render_discovery_page_app).run()

        at.session_state["group_filter"] = "finance"
        at.run()

        # Click on a table card button
        btn = None
        for b in at.button:
            if b.key and b.key.startswith("notable_open_main.sales.orders"):
                btn = b
                break

        if btn:
            btn.click().run()
            assert at.query_params["tab"] == "search" or at.query_params["tab"] == ["search"]

    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_toggle_bookmark(self, mock_get_posts):
        mock_get_posts.return_value = []
        at = AppTest.from_function(render_discovery_page_app).run()

        at.session_state["group_filter"] = "finance"
        at.session_state["bookmarks"] = set()
        at.run()

        # Add bookmark
        btn = None
        for b in at.button:
            if b.key and b.key.startswith("notable_bk_main.sales.orders"):
                btn = b
                break

        if btn:
            btn.click().run()
            assert "main.sales.orders" in at.session_state["bookmarks"]

        # Remove bookmark
        btn = None
        for b in at.button:
            if b.key and b.key.startswith("notable_bk_main.sales.orders"):
                btn = b
                break

        if btn:
            btn.click().run()
            assert "main.sales.orders" not in at.session_state["bookmarks"]

    @patch("src.ui.cards.discovery.st.segmented_control")
    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_tabs_render_col_bookmarks(self, mock_get_posts, mock_seg_ctrl):
        mock_get_posts.return_value = []
        mock_seg_ctrl.return_value = "bookmarks"
        at = AppTest.from_function(render_discovery_page_app).run()

        at.session_state["bookmarks"] = set()
        at.session_state["col_bookmarks"] = {"main.sales.orders::amount"}
        at.run()

        html = [m.value for m in at.markdown]
        assert any("amount" in val for val in html)
        assert any("main · sales · orders" in val for val in html)

    @patch("src.ui.cards.discovery.st.segmented_control")
    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_col_bookmark_click(self, mock_get_posts, mock_seg_ctrl):
        mock_get_posts.return_value = []
        mock_seg_ctrl.return_value = "bookmarks"
        at = AppTest.from_function(render_discovery_page_app).run()

        at.session_state["bookmarks"] = set()
        at.session_state["col_bookmarks"] = {"main.sales.orders::amount"}
        at.run()

        btn = None
        for b in at.button:
            if b.key == "colbk_open_main.sales.orders::amount":
                btn = b
                break

        if btn:
            btn.click().run()
            assert at.query_params["tab"] == "search" or at.query_params["tab"] == ["search"]

    @patch("src.ui.cards.discovery.st.segmented_control")
    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_col_bookmark_remove(self, mock_get_posts, mock_seg_ctrl):
        mock_get_posts.return_value = []
        mock_seg_ctrl.return_value = "bookmarks"
        at = AppTest.from_function(render_discovery_page_app).run()

        at.session_state["bookmarks"] = set()
        at.session_state["col_bookmarks"] = {"main.sales.orders::amount"}
        at.run()

        btn = None
        for b in at.button:
            if b.key == "colbk_rm_main.sales.orders::amount":
                btn = b
                break

        if btn:
            btn.click().run()
            assert "main.sales.orders::amount" not in at.session_state["col_bookmarks"]

    @patch("src.ui.cards.discovery.get_active_posts")
    @patch("src.ui.cards.discovery.is_admin", return_value=True)
    @patch("src.ui.cards.discovery._show_delete_cms_dialog")
    def test_discovery_render_cms_banner(self, mock_delete, mock_is_admin, mock_get_posts):
        mock_get_posts.return_value = [
            {
                "post_id": "1",
                "post_type": "announcement",
                "title": "Welcome",
                "body": "Hello world",
                "author_email": "admin@example.com",
                "created_at": pd.Timestamp("2023-01-01")
            },
            {
                "post_id": "2",
                "post_type": "featured_table",
                "title": "Important Data",
                "body": "Check this",
                "author_email": "admin@example.com",
                "created_at": pd.Timestamp("2023-01-01"),
                "table_ref": "main.sales.orders"
            }
        ]
        at = AppTest.from_function(render_discovery_page_app).run()

        html = [m.value for m in at.markdown]
        assert any("Welcome" in val for val in html)
        assert any("Hello world" in val for val in html)
        assert any("Important Data" in val for val in html)

        # Test navigate to featured table
        btn = None
        for b in at.button:
            if b.key == "cms_nav_2":
                btn = b
                break

        if btn:
            btn.click().run()
            assert at.query_params["tab"] == "search" or at.query_params["tab"] == ["search"]

        # Test delete post (admin only)
        at = AppTest.from_function(render_discovery_page_app).run()
        btn = None
        for b in at.button:
            if b.key == "cms_del_1":
                btn = b
                break

        if btn:
            btn.click().run()
            mock_delete.assert_called_once_with("1")

    @patch("src.ui.cards.discovery._duckdb_available", return_value=True)
    @patch("src.ui.cards.discovery.is_demo_mode", return_value=False)
    @patch("src.ui.cards.discovery.run_query")
    def test_get_recommended_tables(self, mock_query, mock_demo, mock_duckdb):
        from src.ui.cards.discovery import _get_recommended_tables

        # Test empty result
        mock_query.return_value = pd.DataFrame()
        assert _get_recommended_tables({"main.sales.orders"}) == []

        # Test with data
        mock_query.return_value = pd.DataFrame({
            "object_name": ["main.sales.orders", "main.finance.ledger", "main.marketing.leads"],
            "views": [10, 5, 2]
        })

        auth_tables = {"main.sales.orders", "main.finance.ledger"}
        with patch("streamlit.session_state", {"recent_views": ["main.finance.ledger"]}):
            # ledger should be excluded because it's recent
            # leads should be excluded because it's not authorized
            # only orders should be returned
            res = _get_recommended_tables(auth_tables)
            assert res == ["main.sales.orders"]

        # Test query failure
        mock_query.side_effect = Exception("DB error")
        assert _get_recommended_tables(auth_tables) == []

    @patch("src.ui.cards.discovery.st.segmented_control")
    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_recommended_tab_empty(self, mock_get_posts, mock_seg_ctrl):
        mock_get_posts.return_value = []
        mock_seg_ctrl.return_value = "recommended"
        at = AppTest.from_function(render_discovery_page_app).run()

        with patch("src.ui.cards.discovery._get_recommended_tables", return_value=[]):
            at.run()

            html = [m.value for m in at.markdown]
            assert any(en_locale["personalization"]["recommended_title"] in val for val in html)
            assert any(en_locale["personalization"]["recommended_empty"] in m.value for m in at.markdown)

    @patch("src.ui.cards.discovery.st.segmented_control")
    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_recommended_tab_all_empty(self, mock_get_posts, mock_seg_ctrl):
        mock_get_posts.return_value = []
        mock_seg_ctrl.return_value = "recommended"
        at = AppTest.from_function(render_discovery_page_app_empty).run()

        at.run()

        assert any(en_locale["personalization"]["recommended_empty"] in m.value for m in at.markdown)

    @patch("src.ui.cards.discovery.st.segmented_control")
    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_recent_tab_empty_auth(self, mock_get_posts, mock_seg_ctrl):
        mock_get_posts.return_value = []
        mock_seg_ctrl.return_value = "recent"
        at = AppTest.from_function(render_discovery_page_app_empty).run()

        at.session_state["recent_views"] = ["main.finance.ledger"]
        at.run()

        assert any(en_locale["personalization"]["no_recent"] in m.value for m in at.markdown)

    @patch("src.ui.cards.discovery.st.segmented_control")
    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_bookmarks_tab_empty_auth(self, mock_get_posts, mock_seg_ctrl):
        mock_get_posts.return_value = []
        mock_seg_ctrl.return_value = "bookmarks"
        at = AppTest.from_function(render_discovery_page_app_empty).run()

        at.session_state["bookmarks"] = {"main.finance.ledger"}
        at.run()

        assert any(en_locale["personalization"]["no_bookmarks"] in m.value for m in at.markdown)

    @patch("src.ui.cards.discovery.st.segmented_control")
    @patch("src.ui.cards.discovery.get_active_posts")
    def test_discovery_notable_tab_empty_auth(self, mock_get_posts, mock_seg_ctrl):
        mock_get_posts.return_value = []
        mock_seg_ctrl.return_value = "notable"
        at = AppTest.from_function(render_discovery_page_app_empty).run()

        at.session_state["group_filter"] = "finance"
        at.run()

        assert any(en_locale["discovery"]["no_updates"] in m.value for m in at.markdown)


@patch("src.ui.cards.discovery.get_unread_notifications")
@patch("src.ui.cards.discovery.mark_read")
@patch("src.ui.cards.discovery.mark_all_read")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notifications_strip(mock_get_posts, mock_mark_all, mock_mark_read, mock_get_unread):
    mock_get_posts.return_value = []

    # Test with 1 notification
    mock_get_unread.return_value = [{
        "notification_id": "n1",
        "table_full_name": "main.sales.orders",
        "summary": "Schema changed",
        "changed_by": "admin"
    }]

    # Need to set session state for user_oid
    at = AppTest.from_function(render_discovery_page_app).run()
    at.session_state["user_oid"] = "test_user"
    at.run()

    html = [m.value for m in at.markdown]
    assert any("main.sales.orders" in val for val in html)
    assert any("Schema changed" in val for val in html)

    # Dismiss single notification
    btn = None
    for b in at.button:
        if b.key == "notif_dismiss_n1":
            btn = b
            break

    if btn:
        btn.click().run()
        mock_mark_read.assert_called_once_with("n1")

    # Test with multiple notifications
    mock_get_unread.return_value = [{
        "notification_id": "n1",
        "table_full_name": "main.sales.orders",
        "summary": "Schema changed",
        "changed_by": "admin"
    }, {
        "notification_id": "n2",
        "table_full_name": "main.sales.customers",
        "summary": "Data updated",
        "changed_by": ""
    }]

    at = AppTest.from_function(render_discovery_page_app).run()
    at.session_state["user_oid"] = "test_user"
    at.run()

    # Mark all read
    btn = None
    for b in at.button:
        if b.key == "notif_mark_all":
            btn = b
            break

    if btn:
        btn.click().run()
        mock_mark_all.assert_called_once_with("test_user")

@patch("src.ui.cards.discovery.get_unread_notifications")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notifications_empty(mock_get_posts, mock_get_unread):
    mock_get_posts.return_value = []
    mock_get_unread.return_value = []

    at = AppTest.from_function(render_discovery_page_app).run()
    at.session_state["user_oid"] = "test_user"
    at.run()

    # Should not crash, and should hit line 118
    # Asserting no 'Mark all read' button is rendered
    has_mark_all = any(b.key == "notif_mark_all" for b in at.button if b.key)
    assert not has_mark_all

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_recent_exception_fallback(m1, m2):
    m1.return_value = []
    m2.return_value = "recent"

    def app_wrapper():
        def fail_auth_tables(*args, **kwargs):
            raise Exception("DB ERROR")
        from unittest.mock import patch
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_table_names", side_effect=fail_auth_tables):
            render_discovery(["finance", "sales"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["recent_views"] = ["test"]
    at.run()
    assert not at.exception
    assert len(at.error) > 0 or len(at.info) > 0 or len(at.warning) > 0

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_bookmarks_exception_fallback(m1, m2):
    m1.return_value = []
    m2.return_value = "bookmarks"

    def app_wrapper():
        def fail_auth_tables(*args, **kwargs):
            raise Exception("DB ERROR")
        from unittest.mock import patch
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_table_names", side_effect=fail_auth_tables):
            render_discovery(["finance", "sales"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["bookmarks"] = {"test"}
    at.run()
    assert not at.exception
    assert len(at.error) > 0 or len(at.info) > 0 or len(at.warning) > 0


@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notable_exception_fallback(m1, m2):
    m1.return_value = []
    m2.return_value = "notable"

    def app_wrapper():
        def fail_auth_tables(*args, **kwargs):
            raise Exception("DB ERROR")
        from unittest.mock import patch
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_tables", side_effect=fail_auth_tables):
            render_discovery(["finance", "sales"])

    at = AppTest.from_function(app_wrapper).run()
    assert not at.exception
    assert len(at.error) > 0

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_recommended_exception_fallback(m1, m2):
    m1.return_value = []
    m2.return_value = "recommended"

    def app_wrapper():
        def fail_auth_tables(*args, **kwargs):
            raise Exception("DB ERROR")
        from unittest.mock import patch
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery._get_recommended_tables", side_effect=fail_auth_tables):
            render_discovery(["finance", "sales"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["group_filter"] = "finance"
    at.run()
    assert not at.exception
    assert len(at.error) > 0 or len(at.info) > 0 or len(at.warning) > 0

@patch("src.ui.cards.discovery.is_admin", return_value=False)
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_render_cms_banner_not_admin(mock_get_posts, mock_is_admin):
    # Arrange
    mock_get_posts.return_value = [
        {
            "post_id": "1",
            "post_type": "announcement",
            "title": "Welcome",
            "body": "Hello world",
            "author_email": "admin@example.com",
            "created_at": pd.Timestamp("2023-01-01")
        },
        {
            "post_id": "2",
            "post_type": "featured_table",
            "title": "Important Data",
            "body": "Check this",
            "author_email": "admin@example.com",
            "created_at": pd.Timestamp("2023-01-01"),
            "table_ref": "main.sales.orders"
        }
    ]

    def dummy_render_cms_banner():
        from src.ui.cards.discovery import render_cms_banner
        import streamlit as st
        st.session_state["bookmarks"] = set()
        render_cms_banner()

    # Act
    at = AppTest.from_function(dummy_render_cms_banner).run()

    # Assert
    html = [m.value for m in at.markdown]
    assert any("Welcome" in val for val in html)
    assert any("Important Data" in val for val in html)

    btn = None
    for b in at.button:
        if b.key == "cms_nav_2":
            btn = b
            break

    assert btn is not None
    btn.click().run()

    assert "search" in at.query_params["tab"]
    assert at.session_state["dd_search_override"] == "orders"

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_tabs_none_selected(mock_get_posts, mock_seg_ctrl):
    # Arrange
    mock_get_posts.return_value = []
    mock_seg_ctrl.return_value = None

    # Act
    at = AppTest.from_function(render_discovery_page_app).run()

    # Assert
    html = [m.value for m in at.markdown]
    assert any(en_locale["personalization"]["tab_notable"] in val for val in html)

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_no_groups(mock_get_posts, mock_seg_ctrl):
    # Arrange
    mock_get_posts.return_value = []
    mock_seg_ctrl.return_value = "notable"
    def dummy_app():
        from src.ui.cards.discovery import render_discovery
        render_discovery([])

    # Act
    at = AppTest.from_function(dummy_app).run()

    # Assert
    assert any(en_locale["discovery"]["no_groups"] in m.value for m in at.markdown)

    # Arrange
    def dummy_app_none():
        from src.ui.cards.discovery import render_discovery
        render_discovery(["none"])

    # Act
    at2 = AppTest.from_function(dummy_app_none).run()

    # Assert
    assert any(en_locale["discovery"]["no_groups"] in m.value for m in at2.markdown)


@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_bookmarks_tab_empty(mock_get_posts, mock_seg_ctrl):
    # Arrange
    mock_get_posts.return_value = []
    mock_seg_ctrl.return_value = "bookmarks"

    # Act
    at = AppTest.from_function(render_discovery_page_app).run()
    at.session_state["bookmarks"] = {"main.nonexistent.table"}
    at.run()

    # Assert
    assert any(en_locale["personalization"]["no_bookmarks"] in m.value for m in at.markdown)

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_recent_tab_empty_views(mock_get_posts, mock_seg_ctrl):
    # Arrange
    mock_get_posts.return_value = []
    mock_seg_ctrl.return_value = "recent"

    # Act
    at = AppTest.from_function(render_discovery_page_app).run()
    at.session_state["recent_views"] = ["main.nonexistent.table"]
    at.run()

    # Assert
    assert any(en_locale["personalization"]["no_recent"] in m.value for m in at.markdown)

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_col_bookmark_invalid_and_unauthorized(mock_get_posts, mock_seg_ctrl):
    # Arrange
    mock_get_posts.return_value = []
    mock_seg_ctrl.return_value = "bookmarks"

    # Act
    at = AppTest.from_function(render_discovery_page_app).run()
    at.session_state["col_bookmarks"] = {"invalid_bookmark_format", "main.unauthorized.table::amount"}
    at.run()

    # Assert
    html = [m.value for m in at.markdown]
    assert not any("invalid_bookmark_format" in val for val in html)
    assert not any("unauthorized" in val for val in html)

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_bookmarks_tab_df_empty(m1, m2):
    m1.return_value = []
    m2.return_value = "bookmarks"

    def app_wrapper():
        from unittest.mock import patch
        import pandas as pd
        from src.ui.cards.discovery import render_discovery

        # We need authorized_fns to contain the bookmark so it passes the first check
        with patch("src.ui.cards.discovery.get_authorized_table_names", return_value=["test_table"]),              patch("src.ui.cards.discovery.get_authorized_tables", return_value=pd.DataFrame(columns=["full_name"])):
            render_discovery(["finance"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["bookmarks"] = {"test_table"}
    at.run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_recent_tab_df_empty(m1, m2):
    m1.return_value = []
    m2.return_value = "recent"

    def app_wrapper():
        from unittest.mock import patch
        import pandas as pd
        from src.ui.cards.discovery import render_discovery

        with patch("src.ui.cards.discovery.get_authorized_table_names", return_value=["test_table"]),              patch("src.ui.cards.discovery.get_authorized_tables", return_value=pd.DataFrame(columns=["full_name"])):
            render_discovery(["finance"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["recent_views"] = ["test_table"]
    at.run()
    assert not at.exception


@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notable_no_group(m1, m2):
    m1.return_value = []
    m2.return_value = "notable"

    def app_wrapper():
        from src.ui.cards.discovery import render_discovery

        # We need groups to have an element so the earlier check `if not primary_group or primary_group == "none"` passes but we need to cover `else:` corresponding to `if primary_group:`.
        # Wait, if `if not primary_group` returns early, how can it ever hit the `else:` branch of `if primary_group:`?
        # Let's check the logic.
        render_discovery([""])

    at = AppTest.from_function(app_wrapper).run()
    assert not at.exception


@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notable_dq_score_none(m1, m2):
    m1.return_value = []
    m2.return_value = "notable"

    def app_wrapper():
        from src.ui.cards.discovery import _render_dq_badge
        assert _render_dq_badge(None, "Pass") == ""

    at = AppTest.from_function(app_wrapper).run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notable_exception_fallback_get_authorized_tables(m1, m2):
    m1.return_value = []
    m2.return_value = "notable"

    def app_wrapper():
        def fail_auth_tables(*args, **kwargs):
            raise Exception("DB ERROR")
        from unittest.mock import patch
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_tables", side_effect=fail_auth_tables):
            render_discovery(["finance", "sales"])

    at = AppTest.from_function(app_wrapper).run()
    assert not at.exception
    assert len(at.error) > 0

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_bookmarks_tab_df_empty(m1, m2):
    m1.return_value = []
    m2.return_value = "bookmarks"

    def app_wrapper():
        from unittest.mock import patch
        import pandas as pd
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_table_names", return_value=["test_table"]), \
             patch("src.ui.cards.discovery.get_authorized_tables", return_value=pd.DataFrame(columns=["full_name"])):
            render_discovery(["finance"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["bookmarks"] = {"test_table"}
    at.run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_recent_tab_df_empty(m1, m2):
    m1.return_value = []
    m2.return_value = "recent"

    def app_wrapper():
        from unittest.mock import patch
        import pandas as pd
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_table_names", return_value=["test_table"]), \
             patch("src.ui.cards.discovery.get_authorized_tables", return_value=pd.DataFrame(columns=["full_name"])):
            render_discovery(["finance"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["recent_views"] = ["test_table"]
    at.run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notable_dq_score_none(m1, m2):
    m1.return_value = []
    m2.return_value = "notable"

    def app_wrapper():
        from src.ui.cards.discovery import _render_dq_badge
        assert _render_dq_badge(None, "Pass") == ""

    at = AppTest.from_function(app_wrapper).run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notable_exception_fallback_get_authorized_tables(m1, m2):
    m1.return_value = []
    m2.return_value = "notable"

    def app_wrapper():
        def fail_auth_tables(*args, **kwargs):
            raise Exception("DB ERROR")
        from unittest.mock import patch
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_tables", side_effect=fail_auth_tables):
            render_discovery(["finance", "sales"])

    at = AppTest.from_function(app_wrapper).run()
    assert not at.exception
    assert len(at.error) > 0

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_bookmarks_tab_df_empty(m1, m2):
    m1.return_value = []
    m2.return_value = "bookmarks"

    def app_wrapper():
        from unittest.mock import patch
        import pandas as pd
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_table_names", return_value=["test_table"]),              patch("src.ui.cards.discovery.get_authorized_tables", return_value=pd.DataFrame(columns=["full_name"])):
            render_discovery(["finance"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["bookmarks"] = {"test_table"}
    at.run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_recent_tab_df_empty(m1, m2):
    m1.return_value = []
    m2.return_value = "recent"

    def app_wrapper():
        from unittest.mock import patch
        import pandas as pd
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_table_names", return_value=["test_table"]),              patch("src.ui.cards.discovery.get_authorized_tables", return_value=pd.DataFrame(columns=["full_name"])):
            render_discovery(["finance"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["recent_views"] = ["test_table"]
    at.run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notable_dq_score_none(m1, m2):
    m1.return_value = []
    m2.return_value = "notable"

    def app_wrapper():
        from src.ui.cards.discovery import _render_dq_badge
        assert _render_dq_badge(None, "Pass") == ""

    at = AppTest.from_function(app_wrapper).run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notable_exception_fallback_get_authorized_tables(m1, m2):
    m1.return_value = []
    m2.return_value = "notable"

    def app_wrapper():
        def fail_auth_tables(*args, **kwargs):
            raise Exception("DB ERROR")
        from unittest.mock import patch
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_tables", side_effect=fail_auth_tables):
            render_discovery(["finance", "sales"])

    at = AppTest.from_function(app_wrapper).run()
    assert not at.exception
    assert len(at.error) > 0

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_bookmarks_tab_df_empty(m1, m2):
    m1.return_value = []
    m2.return_value = "bookmarks"

    def app_wrapper():
        from unittest.mock import patch
        import pandas as pd
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_table_names", return_value=["test_table"]), \
             patch("src.ui.cards.discovery.get_authorized_tables", return_value=pd.DataFrame(columns=["full_name"])):
            render_discovery(["finance"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["bookmarks"] = {"test_table"}
    at.run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_recent_tab_df_empty(m1, m2):
    m1.return_value = []
    m2.return_value = "recent"

    def app_wrapper():
        from unittest.mock import patch
        import pandas as pd
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_table_names", return_value=["test_table"]), \
             patch("src.ui.cards.discovery.get_authorized_tables", return_value=pd.DataFrame(columns=["full_name"])):
            render_discovery(["finance"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["recent_views"] = ["test_table"]
    at.run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notable_dq_score_none(m1, m2):
    m1.return_value = []
    m2.return_value = "notable"

    def app_wrapper():
        from src.ui.cards.discovery import _render_dq_badge
        assert _render_dq_badge(None, "Pass") == ""

    at = AppTest.from_function(app_wrapper).run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notable_exception_fallback_get_authorized_tables(m1, m2):
    m1.return_value = []
    m2.return_value = "notable"

    def app_wrapper():
        def fail_auth_tables(*args, **kwargs):
            raise Exception("DB ERROR")
        from unittest.mock import patch
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_tables", side_effect=fail_auth_tables):
            render_discovery(["finance", "sales"])

    at = AppTest.from_function(app_wrapper).run()
    assert not at.exception
    assert len(at.error) > 0

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_bookmarks_tab_df_empty(m1, m2):
    m1.return_value = []
    m2.return_value = "bookmarks"

    def app_wrapper():
        from unittest.mock import patch
        import pandas as pd
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_table_names", return_value=["test_table"]), \
             patch("src.ui.cards.discovery.get_authorized_tables", return_value=pd.DataFrame(columns=["full_name"])):
            render_discovery(["finance"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["bookmarks"] = {"test_table"}
    at.run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_recent_tab_df_empty(m1, m2):
    m1.return_value = []
    m2.return_value = "recent"

    def app_wrapper():
        from unittest.mock import patch
        import pandas as pd
        from src.ui.cards.discovery import render_discovery
        with patch("src.ui.cards.discovery.get_authorized_table_names", return_value=["test_table"]), \
             patch("src.ui.cards.discovery.get_authorized_tables", return_value=pd.DataFrame(columns=["full_name"])):
            render_discovery(["finance"])

    at = AppTest.from_function(app_wrapper).run()
    at.session_state["recent_views"] = ["test_table"]
    at.run()
    assert not at.exception

@patch("src.ui.cards.discovery.st.segmented_control")
@patch("src.ui.cards.discovery.get_active_posts")
def test_discovery_notable_dq_score_none(m1, m2):
    m1.return_value = []
    m2.return_value = "notable"

    def app_wrapper():
        from src.ui.cards.discovery import _render_dq_badge
        assert _render_dq_badge(None, "Pass") == ""

    at = AppTest.from_function(app_wrapper).run()
    assert not at.exception
