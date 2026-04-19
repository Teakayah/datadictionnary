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
        "table_description", "table_type",
    ])


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
    """Sign-in page and mock auth flow (CLIENT_ID unset → mock mode)."""

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

    SQL inspection works via the shared databricks.sql MagicMock cursor.
    run_query() calls cursor.execute(sql, params) then cursor.fetchall_as_pandas().
    We configure return values via sql_returns() and inspect calls via
    get_db_cursor().execute.call_args_list.
    """

    def test_empty_state_prompt_shown(self):
        """Before any search, the 'Start typing' prompt must appear."""
        at = authenticated_app()
        at.run()
        html = _html(*at.markdown)
        assert "Start typing" in html

    def test_search_queries_correct_tables(self):
        """A search must JOIN tables_metadata with permissions_cache."""
        sql_returns(make_tables_df(), make_columns_df())
        at = authenticated_app()
        at.run()
        at.text_input[0].set_value("orders").run()
        cursor = get_db_cursor()
        executed = [call[0][0] for call in cursor.execute.call_args_list]
        assert any("tables_metadata" in q for q in executed), \
            f"tables_metadata not found in queries: {executed}"
        assert any("permissions_cache" in q for q in executed), \
            f"permissions_cache not found in queries: {executed}"

    def test_search_term_not_in_sql(self):
        """The search term must NOT appear as a SQL parameter.

        Search filtering is now done locally in pandas (str.contains), not via
        SQL LIKE, so the search term should never reach the database layer.
        This prevents any SQL injection risk from the search input.
        """
        sql_returns(make_tables_df(), make_columns_df())
        at = authenticated_app()
        at.run()
        at.text_input[0].set_value("orders").run()
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
        sql_returns(make_tables_df(), make_columns_df())
        at = authenticated_app()
        at.run()
        at.text_input[0].set_value("orders").run()
        cursor = get_db_cursor()
        first_call_params = cursor.execute.call_args_list[0][0][1]
        assert "finance_dept_id" in first_call_params["groups"], (
            "finance_dept_id not in groups param — permission filter may be bypassable"
        )

    def test_search_results_render_dataframe(self):
        """Results from run_query must produce a visible st.dataframe widget."""
        sql_returns(make_tables_df(), make_columns_df())
        at = authenticated_app()
        at.run()
        at.text_input[0].set_value("orders").run()
        assert len(at.dataframe) >= 1, "No dataframe rendered after search"

    def test_search_empty_results_renders_no_match_message(self):
        """An empty result set must render the 'No matches' message."""
        sql_returns(empty_results_df())
        at = authenticated_app()
        at.run()
        at.text_input[0].set_value("xyznonexistent").run()
        html = _html(*at.markdown)
        assert "No matches" in html

    def test_search_results_show_table_selectbox(self):
        """A selectbox for table detail must appear when results exist."""
        sql_returns(make_tables_df(), make_columns_df())
        at = authenticated_app()
        at.run()
        at.text_input[0].set_value("orders").run()
        assert len(at.selectbox) >= 1, "No table-selection selectbox found in results"

    def test_search_shows_permission_trimmed_label(self):
        """The results count label must show 'permission-trimmed'."""
        sql_returns(make_tables_df(), make_columns_df())
        at = authenticated_app()
        at.run()
        at.text_input[0].set_value("orders").run()
        html = _html(*at.markdown)
        assert "permission-trimmed" in html


# ═══════════════════════════════════════════════════════════════════════════════
# Table detail tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestTableDetail:
    """Column detail view triggered by selecting a table from search results."""

    def test_columns_dataframe_rendered(self):
        """Selecting a table must render a second dataframe for its columns."""
        sql_returns(make_tables_df(), make_columns_df())
        at = authenticated_app()
        at.run()
        at.text_input[0].set_value("orders").run()
        # Two dataframes expected: search results + columns
        assert len(at.dataframe) == 2, \
            f"Expected 2 dataframes (results + columns), got {len(at.dataframe)}"

    def test_column_query_targets_columns_metadata(self):
        """The second SQL call must query the columns_metadata table."""
        sql_returns(make_tables_df(), make_columns_df())
        at = authenticated_app()
        at.run()
        at.text_input[0].set_value("orders").run()
        cursor = get_db_cursor()
        assert len(cursor.execute.call_args_list) == 2, \
            "Expected exactly 2 SQL calls (search + columns)"
        second_sql = cursor.execute.call_args_list[1][0][0]
        assert "columns_metadata" in second_sql

    def test_column_query_uses_three_part_full_name(self):
        """The columns query param must be the 3-part full_name (catalog.schema.table)."""
        sql_returns(make_tables_df(), make_columns_df())
        at = authenticated_app()
        at.run()
        at.text_input[0].set_value("orders").run()
        cursor = get_db_cursor()
        _, col_params = cursor.execute.call_args_list[1][0]
        # params is a tuple: (full_name,)
        full_name = col_params[0] if isinstance(col_params, (tuple, list)) else col_params
        assert full_name == "main.sales.orders", \
            f"Column query got full_name='{full_name}', expected 'main.sales.orders'"


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

    # Product/brand names that are legitimately capitalised in § labels.
    SECTION_PROPER_NOUNS = {
        "Data", "Dictionary", "Business", "Catalog", "Unity", "Entra", "ID",
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

    def test_no_emoji_in_source(self):
        """No emoji characters must appear in the app source."""
        src = _read_app_source()
        emoji_re = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]"
        )
        found = emoji_re.findall(src)
        assert not found, f"Emoji found in app.py: {found}"

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
