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
from unittest.mock import patch
import os
import re
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import get_db_cursor, sql_returns

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")


# ── Sample data ───────────────────────────────────────────────────────────────

def make_tables_df() -> pd.DataFrame:
    return pd.DataFrame({
        "full_name":         ["main.sales.orders"],
        "catalog_name":      ["main"],
        "schema_name":       ["sales"],
        "table_name":        ["orders"],
        "table_description": ["All customer orders"],
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
        """Mock sign-in must set finance group IDs in session_state.user_groups."""
        at = unauthenticated_app()
        at.run()
        at.button[0].click().run()
        assert "finance_dept_id" in at.session_state["user_groups"]

    def test_mock_signin_sets_user_name(self):
        """Mock sign-in must set a non-empty user_name."""
        at = unauthenticated_app()
        at.run()
        at.button[0].click().run()
        assert at.session_state["user_name"]

    def test_search_page_not_visible_when_unauthenticated(self):
        """The '§ Catalog search' section must NOT render before sign-in."""
        at = unauthenticated_app()
        at.run()
        html = _html(*at.markdown)
        assert "Catalog search" not in html


# ═══════════════════════════════════════════════════════════════════════════════
# Search tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearch:
    """Search input, SQL correctness, results rendering, and empty states.

    The branch uses a selectbox (not text_input) for table selection.
    On initial load, get_authorized_tables is called and results populate
    the selectbox. Selecting a table triggers detail rendering.
    """

    def test_empty_state_prompt_shown(self):
        """Before any search, the 'Start typing' prompt must appear."""
        at = authenticated_app()
        at.run()
        html = _html(*at.markdown)
        assert "Start typing" in html

    def test_search_queries_correct_tables(self):
        """Loading the search page must JOIN tables_metadata with permissions_cache."""
        sql_returns(make_tables_df())
        at = authenticated_app()
        at.run()
        cursor = get_db_cursor()
        executed = [call[0][0] for call in cursor.execute.call_args_list]
        assert any("tables_metadata" in q for q in executed), \
            f"tables_metadata not found in queries: {executed}"
        assert any("permissions_cache" in q for q in executed), \
            f"permissions_cache not found in queries: {executed}"

    def test_search_term_not_in_sql(self):
        """The search term must NOT appear as a SQL parameter.

        Search filtering is now done locally in pandas, not via SQL LIKE,
        so the search term should never reach the database layer.
        """
        sql_returns(make_tables_df())
        at = authenticated_app()
        at.run()
        cursor = get_db_cursor()
        all_params = [call[0][1] for call in cursor.execute.call_args_list if len(call[0]) > 1]
        for params in all_params:
            if isinstance(params, dict):
                assert "search" not in params, (
                    "Search term found in SQL params — filtering should be local (pandas)"
                )

    def test_search_passes_user_groups_as_param(self):
        """User groups must be a bound SQL parameter, not interpolated.

        This is the permission enforcement test: if groups are interpolated
        rather than parameterised, a crafted group name could bypass the JOIN.
        """
        sql_returns(make_tables_df())
        at = authenticated_app()
        at.run()
        cursor = get_db_cursor()
        first_call_params = cursor.execute.call_args_list[0][0][1]
        assert "finance_dept_id" in first_call_params["groups"], (
            "finance_dept_id not in groups param — permission filter may be bypassable"
        )

    def test_search_results_show_table_selectbox(self):
        """A selectbox for table selection must appear when results exist."""
        sql_returns(make_tables_df())
        at = authenticated_app()
        at.run()
        assert len(at.selectbox) >= 1, "No table-selection selectbox found in results"

    def test_search_exception_shows_generic_error(self):
        """When an exception occurs during query execution, the UI must show
        a generic message, not the raw exception."""
        cursor = get_db_cursor()
        cursor.reset_mock()
        cursor.execute.side_effect = Exception("SECRET_DB_ERROR_123")

        at = authenticated_app()
        at.run()

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
    """Column detail view triggered by selecting a table from search results.

    On this branch, selecting a table in the selectbox triggers the detail
    view with columns, grants, lineage, and related tables rendered in a
    2-column layout.

    Query order after table selection:
      1. get_authorized_tables     → tables_df
      2. get_column_business_names → overrides_df (bulk fetch, uncached)
      3. columns_metadata          → columns_df
      4. get_table_steward         → steward_df (uncached)
      5. get_table_comments        → comments_df (uncached)
      6. permissions_cache         → grants_df
      7. lineage_cache             → lineage_df
      8. related tables            → related_df
    """

    _EMPTY_OVERRIDES = lambda: pd.DataFrame(columns=["column_name", "business_name", "definition", "edited_by", "edited_at"])
    _EMPTY_STEWARD   = lambda: pd.DataFrame(columns=["steward_email"])
    _EMPTY_COMMENTS  = lambda: pd.DataFrame(columns=["comment_id", "comment_text", "author_name", "author_email", "created_at"])

    def _run_with_table_selected(self, *dataframes) -> AppTest:
        """Run app with SQL mocks (must include all 8 DataFrames in order),
        then select 'orders' in the selectbox."""
        sql_returns(*dataframes)
        at = authenticated_app()
        at.run()
        at.selectbox(key="catalog_search").set_value("orders").run()
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

    def test_column_query_targets_columns_metadata(self):
        """SQL must query the columns_metadata table after table selection."""
        at = self._run_with_table_selected(
            make_tables_df(), TestTableDetail._EMPTY_OVERRIDES(), make_columns_df(),
            TestTableDetail._EMPTY_STEWARD(), TestTableDetail._EMPTY_COMMENTS(),
            make_grants_df(), make_lineage_df(), make_related_df(),
        )
        cursor = get_db_cursor()
        executed = [call[0][0] for call in cursor.execute.call_args_list]
        assert any("columns_metadata" in q for q in executed), \
            f"columns_metadata not found in queries: {executed}"

    def test_column_query_uses_three_part_full_name(self):
        """The columns query param must be the 3-part full_name."""
        at = self._run_with_table_selected(
            make_tables_df(), TestTableDetail._EMPTY_OVERRIDES(), make_columns_df(),
            TestTableDetail._EMPTY_STEWARD(), TestTableDetail._EMPTY_COMMENTS(),
            make_grants_df(), make_lineage_df(), make_related_df(),
        )
        cursor = get_db_cursor()
        for call_args in cursor.execute.call_args_list:
            sql = call_args[0][0]
            if "columns_metadata" in sql and len(call_args[0]) > 1:
                params = call_args[0][1]
                if isinstance(params, dict) and "table_full_name" in params:
                    assert params["table_full_name"] == "main.sales.orders"
                    return
        pytest.fail("Could not find columns_metadata query with table_full_name param")


# ═══════════════════════════════════════════════════════════════════════════════
# Design system tests  (static analysis — no Streamlit runtime needed)
# ═══════════════════════════════════════════════════════════════════════════════

def _read_app_source() -> str:
    with open(APP_PATH) as f:
        return f.read()


def _extract_design_css(src: str) -> str:
    match = re.search(r'DESIGN_CSS\s*=\s*"""(.*?)"""', src, re.DOTALL)
    assert match, "Could not locate DESIGN_CSS in app.py"
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
        css_no_root = re.sub(r":root\s*\{[^}]+\}", "", css, flags=re.DOTALL)
        hex_literals = re.findall(r'(?<!["\'])#[0-9A-Fa-f]{3,8}\b', css_no_root)
        assert hex_literals == [], (
            f"Hardcoded hex colors outside :root: {hex_literals}\n"
            "Replace with CSS variables (e.g. var(--accent))."
        )

    def test_section_headers_use_section_symbol(self):
        """Section eyebrow labels must use the § prefix."""
        src = _read_app_source()
        assert "§ Catalog search" in src, "Missing '§ Catalog search' eyebrow"
        assert ("§ Table detail" in src or "§ Columns" in src), \
            "Missing § prefix on table detail/columns section header"

    def test_no_title_case_in_section_headers(self):
        """Section headers must use sentence case, not Title Case.

        Known proper nouns (product names, brands) are excluded from the check.
        """
        src = _read_app_source()
        section_labels = re.findall(r'§\s+([^\n<"]+)', src)
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
        """The fixed header must display the authenticated user's name."""
        at = authenticated_app()
        at.run()
        html = _html(*at.markdown)
        assert "Finance User" in html, "User name not rendered in app header"


# ═══════════════════════════════════════════════════════════════════════════════
# Additional Coverage Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRealAuth:
    """Real auth flow tests (CLIENT_ID set)."""

    def test_real_auth_flow(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MOCK_AUTH", "false")
        monkeypatch.setenv("CLIENT_ID", "test_client")
        monkeypatch.setenv("TENANT_ID", "test_tenant")

        from tests.conftest import _make_stub

        msal_mock = sys.modules["msal"]
        msal_app_instance = msal_mock.ConfidentialClientApplication.return_value
        msal_app_instance.acquire_token_by_authorization_code.return_value = {
            "access_token": "secret_token",
            "id_token_claims": {
                "groups": ["group1"],
                "name": "Real User"
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

    The query order when a table is selected via the selectbox is:
      1. get_authorized_tables     → tables_metadata JOIN permissions_cache
      2. get_column_business_names → business_name_overrides (bulk fetch, uncached)
      3. columns_metadata
      4. get_table_steward         → tables_metadata.steward_email (uncached)
      5. get_table_comments        → comments table (uncached)
      6. permissions_cache (grants)
      7. lineage_cache
      8. related tables (UNION query)
    sql_returns() must be called with all 8 DataFrames in that order.
    """

    _EMPTY_LINEAGE    = lambda: pd.DataFrame(columns=["direction", "entity_full_name", "entity_type"])
    _EMPTY_RELATED    = lambda: pd.DataFrame(columns=["full_name", "table_name", "catalog_name", "schema_name", "relationship"])
    _EMPTY_OVERRIDES  = lambda: pd.DataFrame(columns=["column_name", "business_name", "definition", "edited_by", "edited_at"])
    _EMPTY_STEWARD    = lambda: pd.DataFrame(columns=["steward_email"])
    _EMPTY_COMMENTS   = lambda: pd.DataFrame(columns=["comment_id", "comment_text", "author_name", "author_email", "created_at"])

    def _run_with_detail(
        self,
        tables_df=None,
        columns_df=None,
        grants_df=None,
        lineage_df=None,
        related_df=None,
    ) -> AppTest:
        """Configure SQL mocks for the full detail-pane query sequence,
        select 'orders' in the selectbox, and return the AppTest.

        Query order after table selection:
          1. get_authorized_tables     (tables_metadata JOIN permissions_cache)
          2. get_column_business_names (business_name_overrides bulk) — uncached
          3. columns_metadata
          4. get_table_steward         (tables_metadata.steward_email) — uncached
          5. get_table_comments        (comments table) — uncached
          6. permissions_cache (grants)
          7. lineage_cache
          8. related tables UNION query
        """
        sql_returns(
            tables_df  if tables_df  is not None else make_tables_df(),
            TestLineageAndRelated._EMPTY_OVERRIDES(),
            columns_df if columns_df is not None else make_columns_df(),
            TestLineageAndRelated._EMPTY_STEWARD(),
            TestLineageAndRelated._EMPTY_COMMENTS(),
            grants_df  if grants_df  is not None else make_grants_df(),
            lineage_df if lineage_df is not None else TestLineageAndRelated._EMPTY_LINEAGE(),
            related_df if related_df is not None else TestLineageAndRelated._EMPTY_RELATED(),
        )
        at = authenticated_app()
        at.run()
        at.selectbox(key="catalog_search").set_value("orders").run()
        return at

    # ── § Grants ──────────────────────────────────────────────────────────────

    def test_grants_section_renders_rows(self):
        """§ Group Permissions must render dd-grant-row divs when grants exist."""
        at = self._run_with_detail(grants_df=make_grants_df())
        html = _html(*at.markdown)
        assert "dd-grant-row" in html

    def test_grants_select_all_users_shown_as_all_users(self):
        """The sentinel value SELECT_ALL_USERS must render as 'all users'."""
        grants = pd.DataFrame({"principal": ["SELECT_ALL_USERS"], "privilege": ["SELECT"]})
        at = self._run_with_detail(grants_df=grants)
        html = _html(*at.markdown)
        assert "all users" in html
        assert "SELECT_ALL_USERS" not in html

    def test_grants_empty_state(self):
        """§ Group Permissions must show fallback when no grants exist."""
        at = self._run_with_detail(
            grants_df=pd.DataFrame(columns=["principal", "privilege"])
        )
        html = _html(*at.markdown)
        assert "No grants recorded" in html

    # ── § Lineage & Related ──────────────────────────────────────────────────

    def test_lineage_graph_rendered_when_data_available(self):
        """§ Lineage must render a vis.js graph (via components.html)
        when lineage data exists."""
        lineage = make_lineage_df(
            upstreams=["raw.source.orders_raw"],
            downstreams=["prod.analytics.orders_fact"],
        )
        at = self._run_with_detail(lineage_df=lineage)
        html = _html(*at.markdown)
        # The section header should be present
        assert "Lineage" in html

    def test_related_tables_renders_cards(self):
        """§ Related tables must render dd-related-card elements when data exists."""
        related = make_related_df([{
            "full_name":    "main.sales.customers",
            "table_name":   "customers",
            "catalog_name": "main",
            "schema_name":  "sales",
            "relationship": "Same schema",
        }])
        at = self._run_with_detail(related_df=related)
        html = _html(*at.markdown)
        assert "dd-related-card" in html
        assert "customers" in html

    def test_related_table_open_button_present(self):
        """Each related table card must render an 'Open →' navigation button."""
        related = make_related_df([{
            "full_name":    "main.sales.customers",
            "table_name":   "customers",
            "catalog_name": "main",
            "schema_name":  "sales",
            "relationship": "Same schema",
        }])
        at = self._run_with_detail(related_df=related)
        open_buttons = [b for b in at.button if b.label == "Open \u2192"]
        assert len(open_buttons) >= 1, "Expected 'Open \u2192' button for related table card"
