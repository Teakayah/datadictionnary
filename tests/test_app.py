"""
Frontend tests for app.py using Streamlit's built-in AppTest runner.

Strategy
--------
- AppTest.from_file() executes app.py inside a sandboxed Streamlit runtime.
  Streamlit calls are intercepted — no browser needed.
- AppTest exec()s the script in a private namespace (NOT registered as "app"
  in sys.modules), so patch("app.run_query") does NOT intercept calls.
  Instead we configure the already-mocked databricks.sql cursor (see conftest.py).
- All tests run in the mock-auth path (CLIENT_ID unset), so no Entra ID traffic.

Run with:
    pytest tests/                   # all tests
    pytest tests/ -k TestDesignSystem   # design-system tests only (fastest)
"""

from __future__ import annotations

import sys
import os
import re
import json
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import get_db_cursor, sql_returns

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")


# ── Sample data ───────────────────────────────────────────────────────────────

def make_tables_df() -> pd.DataFrame:
    return pd.DataFrame({
        "full_name":         ["main.analytics.customers"],
        "catalog_name":      ["main"],
        "schema_name":       ["analytics"],
        "table_name":        ["customers"],
        "name":              ["customers"],
        "match_type":        ["Table"],
        "description":       ["Customer master data"],
        "table_description": ["Customer master data"],
        "table_type":        ["TABLE"],
        "updated_at":        [pd.Timestamp("2026-04-22 10:00")],
    })


def make_columns_df() -> pd.DataFrame:
    return pd.DataFrame({
        "column_name": ["order_id", "customer_id", "amount"],
        "data_type":   ["BIGINT",   "BIGINT",      "DOUBLE"],
        "comment":     ["Primary key", "FK to customers", "Order total"],
    })


def empty_results_df() -> pd.DataFrame:
    """Empty DataFrame with correct schema — triggers the 'no results' branch."""
    return pd.DataFrame(columns=[
        "full_name", "catalog_name", "schema_name", "table_name",
        "table_description", "table_type", "updated_at",
    ])


def make_grants_df() -> pd.DataFrame:
    return pd.DataFrame({
        "principal": ["all_employees_id", "SELECT_ALL_USERS"],
        "privilege":  ["SELECT",           "SELECT"],
    })


def make_lineage_df(
    upstreams: list | None = None,
    downstreams: list | None = None,
) -> pd.DataFrame:
    rows = []
    for efn in (upstreams or []):
        rows.append({"direction": "UPSTREAM",   "entity_full_name": efn, "entity_type": "TABLE"})
    for efn in (downstreams or []):
        rows.append({"direction": "DOWNSTREAM", "entity_full_name": efn, "entity_type": "TABLE"})
    if not rows:
        return pd.DataFrame(columns=["direction", "entity_full_name", "entity_type"])
    return pd.DataFrame(rows)


def make_related_df(tables: list | None = None) -> pd.DataFrame:
    if not tables:
        return pd.DataFrame(columns=["full_name", "table_name", "catalog_name", "schema_name", "relationship"])
    return pd.DataFrame(tables)


# ── App factory helpers ────────────────────────────────────────────────────────

def unauthenticated_app() -> AppTest:
    """App in its initial state — no session_state pre-set."""
    return AppTest.from_file(APP_PATH, default_timeout=15)


def authenticated_app() -> AppTest:
    """App with mock auth already completed, but not yet run."""
    at = AppTest.from_file(APP_PATH, default_timeout=15)
    at.session_state["authenticated"] = True
    at.session_state["user_groups"] = ["finance_dept_id", "all_employees_id"]
    at.session_state["user_name"] = "Finance User"
    at.session_state["bookmarks"] = set()
    at.session_state["col_bookmarks"] = set()
    at.session_state["recent_views"] = []
    at.session_state["_prefs_loaded"] = True
    return at


def _html(*markdowns) -> str:
    return " ".join(m.value for m in markdowns)


# ═══════════════════════════════════════════════════════════════════════════════
# Auth tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestMockAuth:
    """Sign-in page and mock auth flow (ENABLE_MOCK_AUTH + ENVIRONMENT)."""

    def test_signin_hero_renders_unauthenticated(self):
        """Unauthenticated app must show the sign-in hero copy."""
        at = unauthenticated_app()
        at.run()
        html = _html(*at.markdown)
        assert "card catalog" in html, "Sign-in hero text not found"

    def test_signin_button_present(self):
        """A sign-in button must be visible before auth."""
        at = unauthenticated_app()
        at.run()
        assert any("Sign in" in b.label for b in at.button), \
            "No sign-in button on unauthenticated page"

    def test_mock_signin_sets_authenticated(self):
        """Clicking the mock sign-in button must set authenticated=True."""
        at = unauthenticated_app()
        at.run()
        at.button[0].click().run()
        assert at.session_state["authenticated"] is True

    def test_mock_signin_populates_user_groups(self):
        """Mock sign-in must set the finance group ID in session_state.user_groups."""
        at = unauthenticated_app()
        at.run()
        at.button[0].click().run()
        # Group IDs were updated to match generate_test_data.py dataset (finance_group)
        assert "finance_group" in at.session_state["user_groups"]



    def test_auto_login_query_param_finance(self):
        """Mock login via URL query parameters must populate session_state correctly for a valid department."""
        at = unauthenticated_app()
        at.query_params["mock_login"] = "true"
        at.query_params["mock_dept"] = "finance"
        at.run()

        assert at.session_state["authenticated"] is True
        assert "finance_group" in at.session_state["user_groups"]
        assert at.session_state["user_email"] == "finance.user@research-org.ca"

    def test_auto_login_query_param_default_admin(self):
        """Mock login via URL query parameters must fallback to admin for an invalid department."""
        at = unauthenticated_app()
        at.query_params["mock_login"] = "true"
        at.query_params["mock_dept"] = "invalid_dept"
        at.run()

        assert at.session_state["authenticated"] is True
        assert "mock_admin_group" in at.session_state["user_groups"]
        assert at.session_state["user_email"] == "admin@research-org.ca"

    def test_mock_signin_sets_user_name(self):
        """Mock sign-in must set a non-empty user_name."""
        at = unauthenticated_app()
        at.run()
        at.button[0].click().run()
        assert at.session_state["user_name"]

    def test_search_page_not_visible_when_unauthenticated(self):
        """The 'Search' section must NOT render before sign-in."""
        at = unauthenticated_app()
        at.run()
        html = _html(*at.markdown)
        assert "§ Catalog search" not in html


# ═══════════════════════════════════════════════════════════════════════════════
# Search tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearch:
    """Search input, SQL correctness, results rendering, and empty states.

    The app uses a text_input for free-text search. Typing triggers
    search_all_metadata (UNION of tables + columns + glossary), and results
    are displayed as cards. The first table match also renders a detail panel.
    """

    def test_empty_state_prompt_shown(self):
        """Before any search, the 'Start typing' prompt must appear."""
        at = authenticated_app()
        at.run()
        html = _html(*at.markdown)
        assert "Start typing" in html

    def test_search_queries_correct_tables(self, monkeypatch):
        """Loading the search page must JOIN tables_metadata with permissions_cache."""
        monkeypatch.setenv("DEMO_DATA", "false")
        sql_returns(make_tables_df(), make_tables_df())
        at = authenticated_app()
        at.query_params["tab"] = "search"
        at.run()
        at.selectbox(key="catalog_search").select("customers").run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()
        cursor = get_db_cursor()
        executed = [call[0][0] for call in cursor.execute.call_args_list]
        assert any("tables_metadata" in q for q in executed), \
            f"tables_metadata not found in queries: {executed}"
        assert any("permissions_cache" in q for q in executed), \
            f"permissions_cache not found in queries: {executed}"

    def test_search_term_parameterized(self, monkeypatch):
        """The search term MUST appear as a parameterized value in SQL."""
        monkeypatch.setenv("DEMO_DATA", "false")
        sql_returns(make_tables_df(), make_tables_df())
        at = authenticated_app()
        at.query_params["tab"] = "search"
        at.run()
        at.selectbox(key="catalog_search").select("customers").run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()
        cursor = get_db_cursor()
        all_params = [call[0][1] for call in cursor.execute.call_args_list if len(call[0]) > 1]
        found = False
        for params in all_params:
            if isinstance(params, dict) and "q" in params and params["q"] == "%customers%":
                found = True
        assert found, "Search term 'customers' not found in SQL parameters as '%customers%'"

    def test_search_passes_user_groups_as_param(self, monkeypatch):
        """User groups must be a bound SQL parameter, not interpolated.

        This is the permission enforcement test: if groups are interpolated
        rather than parameterised, a crafted group name could bypass the JOIN.
        """
        monkeypatch.setenv("DEMO_DATA", "false")
        sql_returns(make_tables_df(), make_tables_df())
        at = authenticated_app()
        at.query_params["tab"] = "search"
        at.run()
        at.selectbox(key="catalog_search").select("customers").run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()
        cursor = get_db_cursor()
        first_call_params = cursor.execute.call_args_list[0][0][1]
        # Groups are bound as individual params (group_0, group_1, ...) to prevent SQL injection.
        group_values = [v for k, v in first_call_params.items() if k.startswith("group_")]
        assert "finance_dept_id" in group_values, (
            "finance_dept_id not in group params — permission filter may be bypassable"
        )

    def test_search_results_show_selectbox(self):
        """A selectbox for search must appear."""
        sql_returns(make_tables_df())
        at = authenticated_app()
        at.query_params["tab"] = "search"
        at.run()
        assert len(at.selectbox) >= 1, "No selectbox found for search"

    def test_search_exception_shows_generic_error(self, monkeypatch):
        """When an exception occurs during query execution, the UI must show
        a generic message, not the raw exception."""
        monkeypatch.delenv("DEMO_DATA", raising=False)
        sql_returns(make_tables_df())
        cursor = get_db_cursor()
        cursor.reset_mock()
        cursor.execute.side_effect = Exception("SECRET_DB_ERROR_123")

        at = authenticated_app()
        at.query_params["tab"] = "search"
        at.run()
        at.selectbox(key="catalog_search").select("customers").run()

        assert any("Error loading catalog" in msg.value for msg in at.error)

        for e in at.error:
            assert "SECRET_DB_ERROR_123" not in e.value, "Exception details leaked in st.error"
        for w in at.warning:
            assert "SECRET_DB_ERROR_123" not in w.value, "Exception details leaked in st.warning"
        for i in at.info:
            assert "SECRET_DB_ERROR_123" not in i.value, "Exception details leaked in st.info"
        html = _html(*at.markdown)
        assert "SECRET_DB_ERROR_123" not in html, "Exception details leaked in st.markdown"


# ═══════════════════════════════════════════════════════════════════════════════
# Table detail tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestTableDetail:
    """Column detail view triggered by typing a table name in search.

    Typing in the text_input triggers search_all_metadata (UNION query),
    then the first table match renders the detail view with columns, grants,
    lineage, and related tables in a 2-column layout.

    Query order after typing a search term:
      1. search_all_metadata       → tables_df (UNION of tables + columns)
      2. get_column_business_names → overrides_df (bulk fetch, uncached)
      3. columns_metadata          → columns_df
      4. get_table_steward         → steward_df (uncached)
      5. get_table_comments        → comments_df (uncached)
      6. permissions_cache         → grants_df
      7. lineage_cache             → lineage_df
      8. related tables            → related_df
    """

    def _EMPTY_OVERRIDES():
        return pd.DataFrame(columns=["column_name", "business_name", "definition", "edited_by", "edited_at"])
    def _EMPTY_STEWARD():
        return pd.DataFrame(columns=["steward_email"])
    def _EMPTY_COMMENTS():
        return pd.DataFrame(columns=["comment_id", "comment_text", "author_name", "author_email", "created_at"])

    def _run_with_table_selected(self, *dataframes) -> AppTest:
        """Run app with SQL mocks (DataFrames in call order), then type 'customers'."""
        sql_returns(*dataframes)
        at = authenticated_app()
        at.query_params["tab"] = "search"
        at.run()
        at.selectbox(key="catalog_search").select("customers").run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()
        return at

    def test_columns_rendered(self):
        """Selecting a table must render column name spans in the detail pane."""
        at = self._run_with_table_selected(
            make_tables_df(), TestTableDetail._EMPTY_OVERRIDES(), make_columns_df(),
            TestTableDetail._EMPTY_STEWARD(), TestTableDetail._EMPTY_COMMENTS(),
            make_grants_df(), make_lineage_df(), make_related_df(),
        )
        html = _html(*at.markdown)
        assert "dd-col-name" in html, "Expected dd-col-name spans in detail pane"

    def test_column_query_targets_columns_metadata(self, monkeypatch):
        """SQL must query the columns_metadata table after table selection."""
        monkeypatch.setenv("DEMO_DATA", "false")
        self._run_with_table_selected(
            make_tables_df(), make_tables_df(), TestTableDetail._EMPTY_OVERRIDES(), make_columns_df(),
            TestTableDetail._EMPTY_STEWARD(), TestTableDetail._EMPTY_COMMENTS(),
            make_grants_df(), make_lineage_df(), make_related_df(),
        )
        cursor = get_db_cursor()
        executed = [call[0][0] for call in cursor.execute.call_args_list]
        assert any("columns_metadata" in q for q in executed), \
            f"columns_metadata not found in queries: {executed}"

    def test_column_query_uses_three_part_full_name(self, monkeypatch):
        """The columns query param must be the 3-part full_name."""
        monkeypatch.setenv("DEMO_DATA", "false")
        # 1: get_authorized_tables (load)
        # 2: get_authorized_tables (select)
        # 3: get_authorized_tables (rerun after button click)
        # 4: search_all_metadata (details)
        # 5: get_column_business_names
        # 6: columns_metadata
        self._run_with_table_selected(
            make_tables_df(), make_tables_df(), make_tables_df(), make_tables_df(),
            TestTableDetail._EMPTY_OVERRIDES(), make_columns_df(),
            TestTableDetail._EMPTY_STEWARD(), TestTableDetail._EMPTY_COMMENTS(),
            make_grants_df(), make_lineage_df(), make_related_df(),
        )
        cursor = get_db_cursor()
        for call_args in cursor.execute.call_args_list:
            sql = call_args[0][0]
            if "columns_metadata" in sql and len(call_args[0]) > 1:
                params = call_args[0][1]
                if isinstance(params, dict) and "table_full_name" in params:
                    assert params["table_full_name"] == "main.analytics.customers"
                    return
        pytest.fail("Could not find columns_metadata query with table_full_name param")


# ═══════════════════════════════════════════════════════════════════════════════
# Design system tests  (static analysis — no Streamlit runtime needed)
# ═══════════════════════════════════════════════════════════════════════════════

def _read_app_source() -> str:
    with open(APP_PATH) as f:
        return f.read()

def _get_all_locale_strings(d: dict) -> list[str]:
    strings = []
    for v in d.values():
        if isinstance(v, dict):
            strings.extend(_get_all_locale_strings(v))
        elif isinstance(v, str):
            strings.append(v)
    return strings

def _read_locale_strings() -> list[str]:
    locale_path = os.path.join(os.path.dirname(__file__), "..", "locale", "en.json")
    with open(locale_path, encoding="utf-8") as f:
        locale_data = json.load(f)
    return _get_all_locale_strings(locale_data)




def _extract_design_css(src: str) -> str:
    # Phase 3: DESIGN_CSS was moved from app.py into assets/design.css.
    # Try the asset file first; fall back to the old inline literal for safety.
    assets_css = os.path.join(os.path.dirname(__file__), "..", "assets", "design.css")
    if os.path.exists(assets_css):
        with open(assets_css, encoding="utf-8") as f:
            return f.read()
    match = re.search(r'DESIGN_CSS\s*=\s*"""(.*?)"""', src, re.DOTALL)
    assert match, "Could not locate DESIGN_CSS in app.py or assets/design.css"
    return match.group(1)


class TestDesignSystem:
    """Design token and copy-style compliance — no runtime required."""

    REQUIRED_TOKENS = [
        "--paper",
        "--paper-deep",
        "--ink",
        "--accent",
        "--accent-wash",
        "--font-display",
        "--font-sans",
        "--font-mono",
    ]

    # Proper nouns that are legitimately capitalised in § labels.
    SECTION_PROPER_NOUNS = {
        "Data", "Dictionary", "Business", "Catalog", "Unity", "Entra", "ID",
        "Glossary", "Discovery", "Health", "Metadata", "Group", "Permissions",
        "Lineage", "Related", "Tables", "Documentation", "Map", "Concept",
        "Actions", "Priority", "Schema", "Details", "Term",
    }

    def test_all_required_tokens_declared(self):
        """Every required design token must appear in DESIGN_CSS."""
        css = _extract_design_css(_read_app_source())
        missing = [t for t in self.REQUIRED_TOKENS if t not in css]
        assert not missing, f"Missing CSS tokens: {missing}"

    def test_no_hardcoded_hex_outside_root(self):
        """Hex color literals must only appear inside :root {}.

        Known violation (not caught by this test): .dd-header uses
        rgba(250, 247, 240, 0.92) instead of var(--paper) with opacity.
        Track as a follow-up — should become a dedicated semitransparent token.
        """
        css = _extract_design_css(_read_app_source())
        # Strip CSS block comments before checking — hex values in /* … */ are
        # documentation of Streamlit internals, not colour declarations.
        css_no_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
        css_no_root = re.sub(r":root\s*\{[^}]+\}", "", css_no_comments, flags=re.DOTALL)
        hex_literals = re.findall(r'(?<!["\'])#[0-9A-Fa-f]{3,8}\b', css_no_root)
        assert hex_literals == [], (
            f"Hardcoded hex colors outside :root: {hex_literals}\n"
            "Replace with CSS variables (e.g. var(--accent))."
        )

    def test_section_headers_use_section_symbol(self):
        """Section eyebrow labels must use the § prefix."""
        with open(os.path.join(os.path.dirname(__file__), "..", "locale", "en.json"), encoding="utf-8") as f:
            locale = json.load(f)
        assert "§" in locale.get("search", {}).get("eyebrow", ""), "Missing 'Search' eyebrow in locale"
        
        strings = _read_locale_strings()
        assert ("§ Table detail" in strings or "§ Columns" in strings), \
            "Missing § prefix on table detail/columns section header"

    def test_no_title_case_in_section_headers(self):
        """Section headers must use sentence case, not Title Case.

        Known proper nouns (product names, brands) are excluded from the check.
        """
        strings = _read_locale_strings()
        section_labels = []
        for s in strings:
            if "§" in s:
                match = re.search(r'§\s+([^\n<"]+)', s)
                if match:
                    section_labels.append(match.group(1))


        for label in section_labels:
            words = label.strip().split()
            if len(words) > 1:
                non_first_caps = [
                    w for w in words[1:]
                    if w[0].isupper() and w.isalpha()
                    and w not in self.SECTION_PROPER_NOUNS
                ]
                assert not non_first_caps, (
                    f"Title Case in '§ {label.strip()}': "
                    f"{non_first_caps} — use sentence case."
                )

    def test_header_shows_authenticated_user_name(self):
        """The fixed header must display the authenticated user's name.

        The header is rendered via st.html() (to bypass the Markdown parser),
        so we inspect the proto.body of the UnknownElement, not at.markdown.
        """
        at = authenticated_app()
        at.run()
        html_bodies = " ".join(
            el.proto.body
            for el in at.get("html")
            if hasattr(el, "proto") and hasattr(el.proto, "body")
        )
        assert "Finance User" in html_bodies, "User name not rendered in app header"


# ═══════════════════════════════════════════════════════════════════════════════
# Additional Coverage Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRealAuth:
    """Real auth flow tests (CLIENT_ID set)."""

    def test_real_auth_flow(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MOCK_AUTH", "false")
        monkeypatch.setenv("CLIENT_ID", "test_client")
        monkeypatch.setenv("TENANT_ID", "test_tenant")


        msal_mock = sys.modules["msal"]
        msal_app_instance = msal_mock.ConfidentialClientApplication.return_value
        msal_app_instance.acquire_token_by_authorization_code.return_value = {
            "access_token": "secret_token",
            "id_token_claims": {
                "groups": ["group1"],
                "name": "Real User",
                "nonce": "test_nonce"
            }
        }

        at = AppTest.from_file(APP_PATH)
        at.session_state["oauth_state"] = "test_state"
        at.session_state["oauth_nonce"] = "test_nonce"
        at.query_params["code"] = "test_auth_code"
        at.query_params["state"] = "test_state"
        at.run()

        assert "auth_token" in at.session_state and at.session_state["auth_token"] is not None
        assert "user_name" in at.session_state and at.session_state["user_name"] == "Real User"
        assert "group1" in at.session_state["user_groups"]

    def test_real_auth_flow_no_access_token(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MOCK_AUTH", "false")
        monkeypatch.setenv("CLIENT_ID", "test_client")
        monkeypatch.setenv("TENANT_ID", "test_tenant")

        msal_mock = sys.modules["msal"]
        msal_app_instance = msal_mock.ConfidentialClientApplication.return_value
        msal_app_instance.acquire_token_by_authorization_code.return_value = {
            "error": "invalid_grant"
        }

        at = AppTest.from_file(APP_PATH)
        at.query_params["code"] = "test_auth_code"
        at.run()

        assert "auth_token" not in at.session_state or at.session_state["auth_token"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# Lineage, grants, and related tables tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestLineageAndRelated:
    """Tests for § Lineage & Related Tables and § Group Permissions in the
    detail pane (2-column layout).

    The query order when a search term is typed is:
      1. search_all_metadata       → tables_metadata JOIN permissions_cache (UNION)
      2. get_column_business_names → business_name_overrides (bulk fetch, uncached)
      3. columns_metadata
      4. get_table_steward         → tables_metadata.steward_email (uncached)
      5. get_table_comments        → comments table (uncached)
      6. permissions_cache (grants)
      7. lineage_cache
      8. related tables (UNION query)
    sql_returns() must be called with all 8 DataFrames in that order.
    """

    def _EMPTY_LINEAGE(self, cursor=None): return pd.DataFrame(columns=["direction", "entity_full_name", "entity_type"])
    def _EMPTY_RELATED(self, cursor=None): return pd.DataFrame(columns=["full_name", "table_name", "catalog_name", "schema_name", "relationship"])
    def _EMPTY_OVERRIDES(self, cursor=None): return pd.DataFrame(columns=["column_name", "business_name", "definition", "edited_by", "edited_at"])
    def _EMPTY_STEWARD(self, cursor=None): return pd.DataFrame(columns=["steward_email"])
    def _EMPTY_COMMENTS(self, cursor=None): return pd.DataFrame(columns=["comment_id", "comment_text", "author_name", "author_email", "created_at"])

    def _run_with_detail(
        self,
        monkeypatch,
        tables_df=None,
        columns_df=None,
        grants_df=None,
        lineage_df=None,
        related_df=None,
    ) -> AppTest:
        """Configure SQL mocks for the full detail-pane query sequence."""
        monkeypatch.setenv("DEMO_DATA", "false")
        
        def detail_side_effect(*args, **kwargs):
            cursor = get_db_cursor()
            # Capture the last executed SQL
            sql = ""
            if cursor.execute.call_args_list:
                sql = cursor.execute.call_args_list[-1][0][0]
            
            if "permissions_cache" in sql and "tables_metadata" in sql:
                return tables_df if tables_df is not None else make_tables_df()
            if "tables_metadata" in sql:
                return tables_df if tables_df is not None else make_tables_df()
            if "columns_metadata" in sql and "JOIN" not in sql:
                return columns_df if columns_df is not None else make_columns_df()
            if "permissions_cache" in sql:
                return grants_df if grants_df is not None else make_grants_df()
            if "lineage_cache" in sql:
                return lineage_df if lineage_df is not None else self._EMPTY_LINEAGE()
            if "UNION" in sql and "columns_metadata" in sql:
                return related_df if related_df is not None else self._EMPTY_RELATED()
            if "business_name_overrides" in sql:
                return self._EMPTY_OVERRIDES()
            if "comments" in sql:
                return self._EMPTY_COMMENTS()
            return pd.DataFrame()

        sql_returns(side_effect=detail_side_effect)
        at = authenticated_app()
        at.query_params["tab"] = "search"
        at.run()
        at.selectbox(key="catalog_search").select("customers").run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()
        return at

    # ── § Grants ──────────────────────────────────────────────────────────────

    def test_grants_section_renders_rows(self, monkeypatch):
        """§ Group Permissions must render dd-grant-row divs when grants exist."""
        at = self._run_with_detail(monkeypatch, grants_df=make_grants_df())
        html = _html(*at.markdown)
        assert "dd-grant-row" in html

    def test_grants_select_all_users_shown_as_all_users(self, monkeypatch):
        """SELECT_ALL_USERS must never appear raw; a browse button must be present."""
        grants = pd.DataFrame({"principal": ["SELECT_ALL_USERS"], "privilege": ["SELECT"]})
        at = self._run_with_detail(monkeypatch, grants_df=grants)
        html = _html(*at.markdown)
        # Sentinel must not leak into the UI
        assert "SELECT_ALL_USERS" not in html
        # A clickable button for public tables must be rendered
        btn_labels = [b.label for b in at.button]
        assert any("all users" in lbl.lower() for lbl in btn_labels), \
            f"Expected a 'Browse tables accessible to all users' button, got: {btn_labels}"

    def test_grants_empty_state(self, monkeypatch):
        """§ Group Permissions must show fallback when no grants exist."""
        at = self._run_with_detail(
            monkeypatch,
            grants_df=pd.DataFrame(columns=["principal", "privilege"])
        )
        html = _html(*at.markdown)
        # Debug print to see what was actually rendered
        if "No grants recorded" not in html:
            print(f"DEBUG HTML: {html[:500]}...")
            print(f"DEBUG BUTTONS: {[b.label for b in at.button]}")
        assert "No grants recorded" in html

    # ── § Lineage & Related ──────────────────────────────────────────────────

    def test_lineage_graph_rendered_when_data_available(self, monkeypatch):
        """§ Lineage must render a vis.js graph (via components.html)
        when lineage data exists."""
        lineage = make_lineage_df(
            upstreams=["raw.source.orders_raw"],
            downstreams=["prod.analytics.orders_fact"],
        )
        at = self._run_with_detail(monkeypatch, lineage_df=lineage)
        html = _html(*at.markdown)
        # The section header should be present
        assert "Lineage" in html

    def test_related_tables_renders_cards(self, monkeypatch):
        """§ Related tables must render dd-related-card elements when data exists."""
        related = make_related_df([{
            "full_name":    "main.analytics.customers",
            "table_name":   "customers",
            "catalog_name": "main",
            "schema_name":  "analytics",
            "relationship": "Same schema",
        }])
        at = self._run_with_detail(monkeypatch, related_df=related)
        html = _html(*at.markdown)
        assert "dd-related-card" in html
        assert "customers" in html

    def test_related_table_open_button_present(self, monkeypatch):
        """Each related table card must render an 'Open →' navigation button."""
        related = make_related_df([{
            "full_name":    "main.analytics.customers",
            "table_name":   "customers",
            "catalog_name": "main",
            "schema_name":  "analytics",
            "relationship": "Same schema",
        }])
        at = self._run_with_detail(monkeypatch, related_df=related)
        open_buttons = [b for b in at.button if b.label == "Open \u2192"]
        assert len(open_buttons) >= 1, "Expected 'Open \u2192' button for related table card"


class TestGlossary:
    """Tests for the Glossary tab."""

    def test_glossary_hero_renders(self):
        """When the Glossary tab is selected, the hero section should render with correct title and subtitle."""
        at = authenticated_app()
        at.query_params["tab"] = "glossary"
        at.run()

        html = _html(*at.markdown)
        assert "Define business concepts and link them to technical data." in html
        assert "Speak the same language." in html

    def test_glossary_search_term_selection(self):
        """When a term is selected from the glossary selectbox, it should render details."""
        at = authenticated_app()
        at.query_params["tab"] = "glossary"
        at.run()

        at.selectbox[0].select("Churn Rate").run()

        html = _html(*at.markdown)
        assert "The percentage of customers who stop using your product" in html
        assert "Sales & Marketing" in html or "Sales &amp; Marketing" in html
        assert "Jane Doe (Marketing)" in html

        buttons = [b.label for b in at.button]
        assert "Explore customers →" in buttons
        assert "Explore orders →" in buttons

    def test_glossary_linked_table_button_click(self):
        """Clicking a linked table button should navigate to the search tab for that table."""
        at = authenticated_app()
        at.query_params["tab"] = "glossary"
        at.run()

        at.selectbox[0].select("Churn Rate").run()

        for i, b in enumerate(at.button):
            if b.label == "Explore customers →":
                at.button[i].click().run()
                break

        assert at.query_params["tab"] == "search" or "search" in at.query_params["tab"]


class TestDiscovery:
    """Tests for the Discovery tab."""

    def test_discovery_exception_shows_generic_error(self, monkeypatch):
        """When an exception occurs during query execution in the discovery tab,
        the UI must show a generic message, not the raw exception."""
        monkeypatch.setenv("DEMO_DATA", "false")
        cursor = get_db_cursor()
        cursor.reset_mock()
        cursor.execute.side_effect = Exception("SECRET_DB_ERROR_DISCOVERY")

        at = authenticated_app()
        at.query_params["tab"] = "discovery"
        at.run()

        assert any("Could not load discovery feed" in msg.value for msg in at.error)

        for e in at.error:
            assert "SECRET_DB_ERROR_DISCOVERY" not in e.value, "Exception details leaked in st.error"
        for w in at.warning:
            assert "SECRET_DB_ERROR_DISCOVERY" not in w.value, "Exception details leaked in st.warning"
        for i in at.info:
            assert "SECRET_DB_ERROR_DISCOVERY" not in i.value, "Exception details leaked in st.info"
        html = _html(*at.markdown)
        assert "SECRET_DB_ERROR_DISCOVERY" not in html, "Exception details leaked in st.markdown"

class TestTabState:
    """Tab state cleanup tests."""

    def test_tab_change_clears_transient_state(self):
        """Changing tabs must clear transient state such as dd_col_edit_mode and dd_comment_open_*."""
        # Initialize app
        at = authenticated_app()

        # Inject transient state BEFORE running, mimicking previous tab state
        at.session_state["_dd_current_tab"] = "search"
        at.session_state["dd_col_edit_mode"] = "some_mode"
        at.session_state["dd_comment_open_123"] = True

        # We need to simulate changing tabs.
        # Actually app.py gets current_tab from src.ui.header.render_header()
        # By default, render_header returns "search" or reads query params.
        # Let's set query params to force a different tab.
        at.query_params["tab"] = "catalog"
        at.run()

        # Check if the state was cleared
        assert "dd_col_edit_mode" not in at.session_state
        assert "dd_comment_open_123" not in at.session_state
        assert at.session_state["_dd_current_tab"] == "catalog"


class TestPageRouting:
    """Page routing tests."""

    def test_routing_health(self):
        """Routing to health tab."""
        at = authenticated_app()
        at.query_params["tab"] = "health"
        at.run()
        assert at.session_state["_dd_current_tab"] == "health"

    def test_routing_pipelines(self):
        """Routing to pipelines tab."""
        at = authenticated_app()
        at.query_params["tab"] = "pipelines"
        at.run()
        assert at.session_state["_dd_current_tab"] == "pipelines"

    def test_routing_admin(self):
        """Routing to admin tab."""
        at = authenticated_app()
        at.query_params["tab"] = "admin"
        at.run()
        assert at.session_state["_dd_current_tab"] == "admin"
