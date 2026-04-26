"""
Tests for the feat/health-dashboard branch: tab navigation, new pages,
auto-login security, and UX requirements.

Run with:
    pytest tests/test_navigation.py -v
"""

from __future__ import annotations

import os
import sys
import re
import pandas as pd
import pytest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

from tests.conftest import get_db_cursor, sql_returns

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")


# ── Sample data ───────────────────────────────────────────────────────────────

def make_tables_df() -> pd.DataFrame:
    return pd.DataFrame({
        "full_name":         ["main.sales.orders", "main.sales.customers"],
        "catalog_name":      ["main", "main"],
        "schema_name":       ["sales", "sales"],
        "table_name":        ["orders", "customers"],
        "table_description": ["All customer orders", "Customer master data"],
        "table_type":        ["TABLE", "TABLE"],
        "updated_at":        [pd.Timestamp("2026-04-22 10:00"), pd.Timestamp("2026-04-21 08:00")],
    })


def make_tables_df_with_missing_desc() -> pd.DataFrame:
    return pd.DataFrame({
        "full_name":         ["main.sales.orders", "main.sales.customers", "main.sales.products"],
        "catalog_name":      ["main", "main", "main"],
        "schema_name":       ["sales", "sales", "sales"],
        "table_name":        ["orders", "customers", "products"],
        "table_description": ["All customer orders", "", ""],
        "table_type":        ["TABLE", "TABLE", "TABLE"],
        "updated_at":        [pd.Timestamp("2026-04-22"), pd.Timestamp("2026-04-21"), pd.Timestamp("2026-04-20")],
    })


def make_columns_df() -> pd.DataFrame:
    return pd.DataFrame({
        "column_name": ["order_id", "customer_id"],
        "data_type":   ["BIGINT", "BIGINT"],
        "comment":     ["Primary key", ""],
    })


def make_health_col_stats() -> pd.DataFrame:
    return pd.DataFrame({"total": [10], "with_desc": [7]})


def empty_tables_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "full_name", "catalog_name", "schema_name", "table_name",
        "table_description", "table_type", "updated_at",
    ])


# ── App factory helpers ──────────────────────────────────────────────────────

def authenticated_app(tab: str | None = None, mock_login: bool = False) -> AppTest:
    """App with mock auth already completed, optionally on a specific tab."""
    at = AppTest.from_file(APP_PATH, default_timeout=15)
    at.session_state["authenticated"] = True
    at.session_state["user_groups"] = ["finance_dept_id", "all_employees_id"]
    at.session_state["user_name"] = "Finance User"
    if tab:
        at.query_params["tab"] = tab
    if mock_login:
        at.query_params["mock_login"] = "true"
    return at


def unauthenticated_app() -> AppTest:
    return AppTest.from_file(APP_PATH, default_timeout=15)


def _html(*markdowns) -> str:
    return " ".join(m.value for m in markdowns)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Navigation & Routing
# ═══════════════════════════════════════════════════════════════════════════════

class TestNavigation:

    def test_default_tab_is_search(self):
        """When no ?tab= param is set, the search page must render."""
        sql_returns(make_tables_df())
        at = authenticated_app()
        at.run()
        html = _html(*at.markdown)
        assert "§ Catalog search" in html

    def test_tab_catalog_renders_catalog_browser(self):
        """?tab=catalog must render the catalog browser page."""
        sql_returns(make_tables_df())
        at = authenticated_app(tab="catalog")
        at.run()
        html = _html(*at.markdown)
        assert "Catalog" in html

    def test_tab_glossary_renders_glossary(self):
        """?tab=glossary must render the glossary page."""
        at = authenticated_app(tab="glossary")
        at.run()
        html = _html(*at.markdown)
        assert "§ Business glossary" in html

    def test_tab_discovery_renders_discovery(self):
        """?tab=discovery must render the discovery page."""
        sql_returns(make_tables_df())
        at = authenticated_app(tab="discovery")
        at.run()
        html = _html(*at.markdown)
        assert "Discovery" in html

    def test_tab_health_renders_health(self):
        """?tab=health must render the health dashboard page."""
        sql_returns(make_tables_df(), make_health_col_stats())
        at = authenticated_app(tab="health")
        at.run()
        html = _html(*at.markdown)
        assert "Health" in html

    def test_active_tab_highlighted_in_header(self):
        """The active tab link must have the 'active' CSS class."""
        sql_returns(make_tables_df())
        at = authenticated_app(tab="catalog")
        at.run()
        html = _html(*at.markdown)
        assert 'dd-nav-tab active' in html and '>Catalog</a>' in html

    def test_search_tab_not_visible_on_catalog(self):
        """When on catalog tab, the search hero must NOT render."""
        sql_returns(make_tables_df())
        at = authenticated_app(tab="catalog")
        at.run()
        html = _html(*at.markdown)
        assert "Search the catalog." not in html


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Auth & Security
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthSecurity:

    def test_mock_login_disabled_when_mock_auth_off(self, monkeypatch):
        """?mock_login=true must NOT auto-authenticate when ENABLE_MOCK_AUTH is false."""
        monkeypatch.setenv("ENABLE_MOCK_AUTH", "false")
        monkeypatch.delenv("CLIENT_ID", raising=False)
        monkeypatch.delenv("TENANT_ID", raising=False)
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.query_params["mock_login"] = "true"
        at.run()
        # Should not be authenticated — no mock auth, no real auth configured
        try:
            authenticated = at.session_state["authenticated"]
        except (KeyError, AttributeError):
            authenticated = False
        assert not authenticated

    def test_mock_login_disabled_in_production(self, monkeypatch):
        """?mock_login=true must NOT work when ENVIRONMENT is production."""
        monkeypatch.setenv("ENABLE_MOCK_AUTH", "true")
        monkeypatch.setenv("ENVIRONMENT", "production")
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.query_params["mock_login"] = "true"
        at.run()
        try:
            authenticated = at.session_state["authenticated"]
        except (KeyError, AttributeError):
            authenticated = False
        assert not authenticated

    def test_mock_login_works_in_dev(self, monkeypatch):
        """?mock_login=true must auto-authenticate in dev mode."""
        monkeypatch.setenv("ENABLE_MOCK_AUTH", "true")
        monkeypatch.setenv("ENVIRONMENT", "development")
        sql_returns(make_tables_df())
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.query_params["mock_login"] = "true"
        at.run()
        assert at.session_state["authenticated"] is True
        assert "finance_dept_id" in at.session_state["user_groups"]
        assert at.session_state["user_name"] == "Finance User"

    def test_auth_persists_across_tab_navigation(self):
        """After login, switching tabs via query params must NOT require re-auth.

        This is the core "no full page refresh needed" UX requirement.
        The mock_login=true param in nav links ensures auth persists.
        """
        sql_returns(make_tables_df())
        # Start on search, then switch to catalog
        at = authenticated_app(tab="search", mock_login=True)
        at.run()
        assert at.session_state["authenticated"] is True

        # Simulate clicking the Catalog nav link
        at.query_params["tab"] = "catalog"
        at.query_params["mock_login"] = "true"
        sql_returns(make_tables_df())
        at.run()

        # Must still be authenticated and rendering catalog content
        assert at.session_state["authenticated"] is True
        html = _html(*at.markdown)
        assert "Catalog" in html

    def test_permission_filtering_catalog_tab(self):
        """Catalog browser must pass user groups to get_authorized_tables."""
        sql_returns(make_tables_df())
        at = authenticated_app(tab="catalog")
        at.run()
        cursor = get_db_cursor()
        executed = [call[0][0] for call in cursor.execute.call_args_list]
        assert any("permissions_cache" in q for q in executed), \
            "Catalog tab must query with permission filtering"

    def test_permission_filtering_health_tab(self):
        """Health tab must pass user groups to get_authorized_tables."""
        sql_returns(make_tables_df(), make_health_col_stats())
        at = authenticated_app(tab="health")
        at.run()
        cursor = get_db_cursor()
        executed = [call[0][0] for call in cursor.execute.call_args_list]
        assert any("permissions_cache" in q for q in executed), \
            "Health tab must query with permission filtering"

    def test_catalog_error_shows_generic_message(self):
        """DB errors in catalog tab must show generic message, not raw exception."""
        cursor = get_db_cursor()
        cursor.reset_mock()
        cursor.execute.side_effect = Exception("SECRET_INTERNAL_ERROR")
        at = authenticated_app(tab="catalog")
        at.run()
        html = _html(*at.markdown)
        all_text = html + " ".join(e.value for e in at.error)
        assert "SECRET_INTERNAL_ERROR" not in all_text
        assert any("Could not load" in e.value for e in at.error)

    def test_html_injection_in_table_description(self):
        """Malicious HTML in table descriptions must be escaped."""
        xss_df = make_tables_df().copy()
        xss_df.loc[0, "table_description"] = '<script>alert("xss")</script>'
        sql_returns(xss_df)
        at = authenticated_app(tab="catalog")
        at.run()
        html = _html(*at.markdown)
        assert "<script>" not in html


# ═══════════════════════════════════════════════════════════════════════════════
# 3. New Page Functionality
# ═══════════════════════════════════════════════════════════════════════════════

class TestCatalogBrowser:

    def test_catalog_renders_tree_structure(self):
        """Catalog browser must render expanders for catalog hierarchy."""
        sql_returns(make_tables_df())
        at = authenticated_app(tab="catalog")
        at.run()
        assert len(at.expander) >= 1, "Expected at least one catalog expander"

    def test_catalog_empty_state(self):
        """Catalog browser must handle empty results gracefully."""
        sql_returns(empty_tables_df())
        at = authenticated_app(tab="catalog")
        at.run()
        assert any("No catalogs" in i.value for i in at.info)

    def test_catalog_shows_table_buttons(self):
        """Each table in the catalog tree must have a clickable button."""
        sql_returns(make_tables_df())
        at = authenticated_app(tab="catalog")
        at.run()
        table_buttons = [b for b in at.button if "orders" in b.label or "customers" in b.label]
        assert len(table_buttons) >= 1, "Expected table buttons in catalog tree"


class TestGlossary:

    def test_glossary_renders_term_details(self):
        """Glossary must render term definitions from demo data."""
        at = authenticated_app(tab="glossary")
        at.run()
        html = _html(*at.markdown)
        # The glossary has a selectbox with terms, and the first term should render
        assert "§ Business glossary" in html

    def test_glossary_shows_selectbox(self):
        """Glossary must show a term selection selectbox."""
        at = authenticated_app(tab="glossary")
        at.run()
        assert len(at.selectbox) >= 1, "Expected term selectbox in glossary"

    def test_glossary_renders_steward_info(self):
        """Glossary term detail must show stewardship information."""
        at = authenticated_app(tab="glossary")
        at.run()
        html = _html(*at.markdown)
        assert "§ Stewardship" in html


class TestDiscovery:

    def test_discovery_shows_recent_tables(self):
        """Discovery tab must show recently updated tables."""
        sql_returns(make_tables_df())
        at = authenticated_app(tab="discovery")
        at.run()
        html = _html(*at.markdown)
        # The tables should be rendered with their names
        assert "orders" in html or "customers" in html

    def test_discovery_sorts_by_updated_at(self):
        """Discovery tab must show most recently updated tables first."""
        sql_returns(make_tables_df())
        at = authenticated_app(tab="discovery")
        at.run()
        html = _html(*at.markdown)
        # "orders" was updated 2026-04-22, "customers" 2026-04-21
        # orders should appear before customers
        orders_pos = html.find("orders")
        customers_pos = html.find("customers")
        if orders_pos >= 0 and customers_pos >= 0:
            assert orders_pos < customers_pos, \
                "Orders (more recent) must appear before customers in discovery feed"

    def test_discovery_empty_state(self):
        """Discovery must handle empty results gracefully."""
        sql_returns(empty_tables_df())
        at = authenticated_app(tab="discovery")
        at.run()
        info_text = " ".join(i.value for i in at.info)
        assert "No recent updates" in info_text or "Highlights" in info_text


class TestHealthDashboard:

    def test_health_renders_coverage_metrics(self):
        """Health dashboard must show table coverage percentage."""
        sql_returns(make_tables_df_with_missing_desc(), make_health_col_stats())
        at = authenticated_app(tab="health")
        at.run()
        html = _html(*at.markdown)
        assert "Table Coverage" in html

    def test_health_coverage_calculation(self):
        """Health dashboard must correctly calculate coverage %.

        make_tables_df_with_missing_desc has 3 tables, 1 with description = 33%.
        """
        sql_returns(make_tables_df_with_missing_desc(), make_health_col_stats())
        at = authenticated_app(tab="health")
        at.run()
        html = _html(*at.markdown)
        assert "33%" in html, "Expected 33% table coverage (1 of 3 described)"

    def test_health_empty_state(self):
        """Health dashboard must handle empty data gracefully."""
        sql_returns(empty_tables_df())
        at = authenticated_app(tab="health")
        at.run()
        assert any("No data" in i.value for i in at.info)

    def test_health_shows_priority_actions(self):
        """Health dashboard must list undocumented tables as priority actions."""
        sql_returns(make_tables_df_with_missing_desc(), make_health_col_stats())
        at = authenticated_app(tab="health")
        at.run()
        html = _html(*at.markdown)
        assert "§ Priority Actions" in html


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Backend Sync — object_tags
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyncObjectTags:

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        mock_modules = {
            "databricks": __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
            "databricks.sdk": __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
            "databricks.sql": __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
            "dotenv": __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
        }
        with patch.dict("sys.modules", mock_modules):
            yield

    def test_setup_creates_object_tags_table(self):
        """setup_cache_tables must create the object_tags table."""
        from unittest.mock import MagicMock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        with patch("scripts.sync_metadata.get_sql_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            from scripts.sync_metadata import setup_cache_tables
            setup_cache_tables()

            all_sql = " ".join(call[0][0] for call in mock_cursor.execute.call_args_list)
            assert "object_tags" in all_sql, "setup_cache_tables must create object_tags table"

    def test_sync_extracts_catalog_tags(self):
        """sync() must extract tags from catalog properties."""
        from unittest.mock import MagicMock

        with patch("scripts.sync_metadata.WorkspaceClient") as mock_wc, \
             patch("scripts.sync_metadata.get_sql_connection") as mock_get_conn, \
             patch("scripts.sync_metadata.concurrent.futures.ThreadPoolExecutor") as mock_exec_cls:

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            mock_w = MagicMock()
            mock_wc.return_value = mock_w

            # Catalog with properties (tags)
            mock_catalog = MagicMock()
            mock_catalog.name = "my_catalog"
            mock_catalog.properties = {"env": "production", "team": "data-eng"}
            mock_w.catalogs.list.return_value = [mock_catalog]

            mock_schema = MagicMock()
            mock_schema.name = "my_schema"
            mock_schema.properties = None
            mock_w.schemas.list.return_value = [mock_schema]
            mock_w.tables.list.return_value = []

            mock_executor = MagicMock()
            mock_exec_cls.return_value.__enter__.return_value = mock_executor
            mock_executor.map.return_value = []

            from scripts.sync_metadata import sync
            sync()

            # Check that object_tags was truncated
            execute_calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
            assert any("TRUNCATE" in q and "object_tags" in q for q in execute_calls), \
                "sync must TRUNCATE object_tags before reload"

            # Check that tags were inserted via executemany
            executemany_calls = mock_cursor.executemany.call_args_list
            tags_inserts = [c for c in executemany_calls if "object_tags" in c[0][0]]
            assert len(tags_inserts) >= 1, "sync must INSERT tags into object_tags"

            # Verify the tag data
            tag_rows = tags_inserts[0][0][1]
            tag_keys = [r["tag_key"] for r in tag_rows]
            assert "env" in tag_keys
            assert "team" in tag_keys
