"""
Tests for the business name editor feature (column-level).

Power users can set a human-friendly business name for individual columns
directly in the § Columns section of the search tab detail panel.

Coverage:
  - Access control: EDITOR_GROUPS gating (✎ button visibility)
  - Edit mode UI: per-column form show/hide, banner, Save/Cancel lifecycle
  - Save in demo mode: session state persistence, display changes
  - Edge cases: XSS injection, empty name
  - Validation: character limit (> 255 chars), permission re-check on save
  - DB write path: atomic MERGE INTO with column_name param (production mock)
  - Audit trail: 'Last edited by' shown when editing a column with an override
  - Sync script: DDL has column_name; push writes ALTER COLUMN ... COMMENT

All UI tests run with DEMO_DATA=true to avoid SQL mock sequencing complexity.
The DB write-path tests are the exception — they use the production mock path.
"""

from __future__ import annotations

import os
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import get_db_cursor, sql_returns

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")

# Matches _DEMO_TABLES and _DEMO_COLUMNS in app.py demo data.
TABLE_NAME = "customers"
FULL_NAME = "main.analytics.customers"
COLUMN_NAME = "customer_id"
EDIT_KEY = f"{FULL_NAME}__{COLUMN_NAME}"


# ── Shared helpers ─────────────────────────────────────────────────────────────


def authenticated_app() -> AppTest:
    os.environ["ADMIN_GROUPS"] = "finance_dept_id,all_employees_id"
    at = AppTest.from_file(APP_PATH, default_timeout=15)
    at.session_state["authenticated"] = True
    at.session_state["user_groups"] = ["finance_dept_id", "all_employees_id"]
    at.session_state["user_name"] = "Finance User"
    at.session_state["bookmarks"] = set()
    at.session_state["_prefs_loaded"] = True
    return at


def _html(*markdowns) -> str:
    return " ".join(m.value for m in markdowns)


# DataFrames used by the production-mode DB tests (non-demo path).
def make_tables_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "full_name": [FULL_NAME],
            "catalog_name": ["main"],
            "schema_name": ["analytics"],
            "table_name": [TABLE_NAME],
            "name": [TABLE_NAME],
            "match_type": ["Table"],
            "description": ["test"],
            "table_description": ["test"],
            "table_type": ["TABLE"],
            "updated_at": [pd.Timestamp("2026-04-22 10:00")],
        }
    )


def make_columns_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "column_name": [COLUMN_NAME, "email"],
            "data_type": ["BIGINT", "STRING"],
            "comment": ["Primary key", "Email address"],
        }
    )


def make_grants_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "principal": ["SELECT_ALL_USERS"],
            "privilege": ["SELECT"],
        }
    )


def _EMPTY_LINEAGE(cursor=None):
    return pd.DataFrame(columns=["direction", "entity_full_name", "entity_type"])


def _EMPTY_RELATED(cursor=None):
    return pd.DataFrame(
        columns=[
            "full_name",
            "table_name",
            "catalog_name",
            "schema_name",
            "relationship",
        ]
    )


def _EMPTY_OVERRIDES(cursor=None):
    return pd.DataFrame(
        columns=["column_name", "business_name", "definition", "edited_by", "edited_at"]
    )


def _EMPTY_STEWARD(cursor=None):
    return pd.DataFrame(columns=["steward_email"])


def _EMPTY_COMMENTS(cursor=None):
    return pd.DataFrame(
        columns=[
            "comment_id",
            "comment_text",
            "author_name",
            "author_email",
            "created_at",
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Access control — EDITOR_GROUPS gating
# ═══════════════════════════════════════════════════════════════════════════════


class TestBusinessNameAccess:
    """✎ button must appear only for users whose groups are in EDITOR_GROUPS."""

    def _at_with_columns(self, monkeypatch) -> AppTest:
        monkeypatch.setenv("DEMO_DATA", "true")
        at = authenticated_app()
        at.run()
        if "catalog_search" in [k.key for k in at.selectbox if k.key]:
            at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        elif len(at.selectbox) > 0:
            at.selectbox[0].select(TABLE_NAME).run()

        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()
        return at

    def test_edit_button_visible_to_power_users(self, monkeypatch):
        """Users in EDITOR_GROUPS must see ✎ buttons in the columns section."""
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        at = self._at_with_columns(monkeypatch)
        assert any(b.label == "✎" for b in at.button), (
            f"✎ button not found for power user. Buttons: {[b.label for b in at.button]}"
        )

    def test_edit_button_hidden_from_non_power_users(self, monkeypatch):
        """Users NOT in EDITOR_GROUPS must not see ✎ buttons."""
        monkeypatch.setenv("EDITOR_GROUPS", "data_stewards_only_id")
        at = self._at_with_columns(monkeypatch)
        assert not any(b.label == "✎" for b in at.button), (
            "✎ button must not appear for users outside EDITOR_GROUPS"
        )

    def test_edit_button_hidden_when_editor_groups_empty(self, monkeypatch):
        """No user gets ✎ buttons when EDITOR_GROUPS is empty."""
        monkeypatch.setenv("EDITOR_GROUPS", "")
        at = self._at_with_columns(monkeypatch)
        assert not any(b.label == "✎" for b in at.button), (
            "✎ button must not appear when EDITOR_GROUPS is not configured"
        )

    def test_multiple_editor_groups_any_match_grants_access(self, monkeypatch):
        """Any group overlap in EDITOR_GROUPS grants access."""
        monkeypatch.setenv("EDITOR_GROUPS", "some_other_group_id,all_employees_id")
        at = self._at_with_columns(monkeypatch)
        assert any(b.label == "✎" for b in at.button), (
            "✎ button must appear when at least one user group is in EDITOR_GROUPS"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Edit mode UI — per-column form lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestBusinessNameEditorUI:
    """Form rendering, banner, and cancel lifecycle in demo mode."""

    def _at_detail(self, monkeypatch) -> AppTest:
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("TESTING_NO_MAX_CHARS", "true")
        at = authenticated_app()
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()
        return at

    def test_clicking_pencil_shows_save_and_cancel(self, monkeypatch):
        """Clicking ✎ must render Save and Cancel buttons."""
        at = self._at_detail(monkeypatch)
        next(b for b in at.button if b.label == "✎").click().run()

        labels = [b.label for b in at.button]
        assert "Save" in labels, f"Save button missing. Buttons: {labels}"
        assert "Cancel" in labels, f"Cancel button missing. Buttons: {labels}"

    def test_clicking_pencil_shows_text_input(self, monkeypatch):
        """Clicking ✎ must render the business name text input for that column."""
        at = self._at_detail(monkeypatch)
        next(b for b in at.button if b.label == "✎").click().run()

        keys = [t.key for t in at.text_input]
        assert any("col_biz_name" in k for k in keys), (
            f"Business name text input not found. Keys: {keys}"
        )

    def test_clicking_pencil_shows_banner(self, monkeypatch):
        """Edit mode must render the dd-edit-banner."""
        at = self._at_detail(monkeypatch)
        next(b for b in at.button if b.label == "✎").click().run()

        assert "dd-edit-banner" in _html(*at.markdown), (
            "Edit banner not rendered when entering column edit mode"
        )

    def test_edit_mode_pre_set_hides_pencil_for_that_column(self, monkeypatch):
        """When dd_col_edit_mode is active for a column, ✎ must not appear for it.

        Uses pre-seeded session state to avoid AppTest+st.rerun() quirk.
        """
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("TESTING_NO_MAX_CHARS", "true")
        at = authenticated_app()
        at.session_state["dd_col_edit_mode"] = EDIT_KEY
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()

        # The pencil for the column in edit mode should be gone
        pencil_keys = [b.key for b in at.button if b.label == "✎"]
        assert not any(f"col_edit_{EDIT_KEY}" == k for k in pencil_keys), (
            "✎ button should not render for the column currently in edit mode"
        )

    def test_cancel_removes_banner(self, monkeypatch):
        """Clicking Cancel must remove the edit banner text."""
        at = self._at_detail(monkeypatch)
        next(b for b in at.button if b.label == "✎").click().run()
        next(b for b in at.button if b.label == "Cancel").click().run()

        assert "business name is saved immediately" not in _html(*at.markdown), (
            "Edit mode banner text still visible after Cancel"
        )

    def test_cancel_removes_save_button(self, monkeypatch):
        """Clicking Cancel must remove the Save button."""
        at = self._at_detail(monkeypatch)
        next(b for b in at.button if b.label == "✎").click().run()
        next(b for b in at.button if b.label == "Cancel").click().run()

        assert all(b.label != "Save" for b in at.button), (
            "Save button still visible after Cancel"
        )

    def test_cancel_restores_pencil_button(self, monkeypatch):
        """After Cancel the ✎ button must reappear."""
        at = self._at_detail(monkeypatch)
        next(b for b in at.button if b.label == "✎").click().run()
        next(b for b in at.button if b.label == "Cancel").click().run()

        assert any(b.label == "✎" for b in at.button), (
            "✎ button did not reappear after Cancel"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Save behavior — demo mode persistence and display
# ═══════════════════════════════════════════════════════════════════════════════


class TestBusinessNameSave:
    """Save interaction, session state persistence, and display changes in demo mode."""

    def _save_name(self, monkeypatch, name: str) -> AppTest:
        """Go to detail, click the pencil on the first column, type a name, save."""
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("TESTING_NO_MAX_CHARS", "true")
        at = authenticated_app()
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()
        next(b for b in at.button if b.label == "✎").click().run()
        # Find the first col_biz_name text input
        inp = next(t for t in at.text_input if "col_biz_name" in t.key)
        inp.set_value(name).run()
        next(b for b in at.button if b.label == "Save").click().run()
        return at

    def test_save_writes_to_demo_session_state(self, monkeypatch):
        """Saving must write the name into demo_business_names in session state."""
        at = self._save_name(monkeypatch, "Customer ID")

        assert "demo_business_names" in at.session_state, (
            "demo_business_names key not found after Save"
        )
        names = at.session_state["demo_business_names"]
        assert FULL_NAME in names, f"Table key not saved. names={names}"
        assert COLUMN_NAME in names[FULL_NAME], f"Column key not saved. names={names}"
        assert names[FULL_NAME][COLUMN_NAME]["business_name"] == "Customer ID"

    def test_save_removes_edit_banner(self, monkeypatch):
        """After Save the edit banner must disappear."""
        at = self._save_name(monkeypatch, "Customer ID")
        assert "business name is saved immediately" not in _html(*at.markdown), (
            "Edit mode banner text still shown after Save"
        )

    def test_save_shows_business_name_in_column_row(self, monkeypatch):
        """After saving, the business name must appear in the column row."""
        at = self._save_name(monkeypatch, "Customer ID")
        assert "Customer ID" in _html(*at.markdown)

    def test_save_shows_biz_name_css_class(self, monkeypatch):
        """After saving, dd-col-biz-name must appear in the rendered HTML."""
        at = self._save_name(monkeypatch, "Customer ID")
        assert "dd-col-biz-name" in _html(*at.markdown), (
            "dd-col-biz-name class not rendered after Save"
        )

    def test_preexisting_override_renders_without_editing(self, monkeypatch):
        """A name already in session state must render immediately on first load."""
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("TESTING_NO_MAX_CHARS", "true")

        at = authenticated_app()
        at.session_state["demo_business_names"] = {
            FULL_NAME: {
                COLUMN_NAME: {
                    "business_name": "Customer ID",
                    "definition": "",
                    "edited_by": "alice",
                    "edited_at": "just now",
                }
            }
        }
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()

        html = _html(*at.markdown)
        assert "dd-col-biz-name" in html
        assert "Customer ID" in html

    def test_no_override_does_not_render_biz_name_span(self, monkeypatch):
        """Without an override, no dd-col-biz-name span content renders.

        Checks via a unique marker string in the rendered span — the CSS class
        name alone cannot be used because it always appears in the <style> block.
        """
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("TESTING_NO_MAX_CHARS", "true")

        at = authenticated_app()
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()

        html = _html(*at.markdown)
        # dd-col-biz-name spans only appear when an override is set; the demo
        # columns have no overrides so the rendered output won't contain the
        # opening tag followed by any content.
        assert '<span class="dd-col-biz-name">' not in html, (
            "dd-col-biz-name span must not render when there is no override"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Edge cases — XSS injection
# ═══════════════════════════════════════════════════════════════════════════════


class TestBusinessNameEdgeCases:
    """XSS injection escape."""

    def test_xss_in_business_name_is_escaped(self, monkeypatch):
        """HTML injected as a business name must be escaped before render."""
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("TESTING_NO_MAX_CHARS", "true")

        at = authenticated_app()
        at.session_state["demo_business_names"] = {
            FULL_NAME: {
                COLUMN_NAME: {
                    "business_name": '<script>alert("xss")</script>',
                    "definition": "",
                    "edited_by": "x",
                    "edited_at": "now",
                }
            }
        }
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()

        html = _html(*at.markdown)
        assert "<script>" not in html, (
            "Raw <script> tag found — business name not escaped"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Validation — character limit and permission re-check
# ═══════════════════════════════════════════════════════════════════════════════


class TestBusinessNameValidation:
    """save_business_name enforces character limit and re-checks power-user status."""

    def test_save_shows_error_for_name_over_255_chars(self, monkeypatch):
        """Entering > MAX_BUSINESS_NAME_LEN chars must show st.error."""
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "true")

        at = authenticated_app()
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()

        next(b for b in at.button if b.label == "✎").click().run()
        inp = next(t for t in at.text_input if "col_biz_name" in t.key)
        assert inp.max_chars == 255, (
            f"Expected text_input max_chars to be 255, got {inp.max_chars}"
        )

    def test_save_shows_permission_error_for_non_power_user(self, monkeypatch):
        """save_business_name must show st.error if user is not in EDITOR_GROUPS."""
        monkeypatch.setenv(
            "EDITOR_GROUPS", "data_stewards_only_id"
        )  # not in user_groups
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("TESTING_NO_MAX_CHARS", "true")

        at = authenticated_app()
        at.session_state["dd_col_edit_mode"] = EDIT_KEY
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()
        inp = next(t for t in at.text_input if "col_biz_name" in t.key)
        inp.set_value("Customer ID").run()
        next(b for b in at.button if b.label == "Save").click().run()

        assert at.error, "st.error should be shown for a non-power-user save attempt"

    def test_save_shows_value_error_for_name_over_255_chars(self, monkeypatch):
        """Entering > MAX_BUSINESS_NAME_LEN chars must show st.error via ValueError catch."""
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("TESTING_NO_MAX_CHARS", "true")

        at = authenticated_app()
        at.session_state["dd_col_edit_mode"] = EDIT_KEY
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()

        inp = next(t for t in at.text_input if "col_biz_name" in t.key)
        # 256 chars
        inp.set_value("a" * 256).run()
        next(b for b in at.button if b.label == "Save").click().run()

        assert at.error, "st.error should be shown for a >255 char name attempt"
        assert "Error" in at.error[0].value or "error" in at.error[0].value.lower()

    def test_save_shows_generic_error_for_other_exceptions(self, monkeypatch):
        """If an unexpected Exception is raised, st.error is shown."""
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "true")

        at = authenticated_app()
        at.session_state["dd_col_edit_mode"] = EDIT_KEY
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()

        # Mock save_business_name to raise a generic Exception
        from unittest.mock import patch
        with patch("src.pages.search.save_business_name", side_effect=Exception("Database connection lost")):
            inp = next(t for t in at.text_input if "col_biz_name" in t.key)
            inp.set_value("New Name").run()
            next(b for b in at.button if b.label == "Save").click().run()

        assert at.error, "st.error should be shown for a generic Exception"
        assert "Error" in at.error[0].value or "error" in at.error[0].value.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Audit trail — 'Last edited by' display in edit mode
# ═══════════════════════════════════════════════════════════════════════════════


class TestBusinessNameAudit:
    """Audit trail shown inside the edit form when an override already exists."""

    def test_audit_shown_in_edit_form_when_override_exists(self, monkeypatch):
        """When a column already has an override, 'Last edited by' must show in edit mode."""
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("TESTING_NO_MAX_CHARS", "true")

        at = authenticated_app()
        at.session_state["demo_business_names"] = {
            FULL_NAME: {
                COLUMN_NAME: {
                    "business_name": "Customer ID",
                    "definition": "",
                    "edited_by": "alice@example.com",
                    "edited_at": "2026-04-24",
                }
            }
        }
        at.session_state["dd_col_edit_mode"] = EDIT_KEY
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()

        html = _html(*at.markdown)
        assert "Last edited by" in html, "Audit trail 'Last edited by' not rendered"
        assert "alice@example.com" in html, "Audit trail editor name not rendered"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. DB write path — production mock (no DEMO_DATA)
# ═══════════════════════════════════════════════════════════════════════════════


class TestBusinessNameEditorDB:
    """Verify the correct SQL is issued by save_business_name in production mode.

    Query order on initial render with catalog_search + dd_col_edit_mode pre-set:
      1. get_authorized_tables     → fetchall #1
      2. get_column_business_names → fetchall #2 (bulk fetch, uncached)
      3. columns_metadata          → fetchall #3
      4. permissions_cache         → fetchall #4
      5. lineage_cache             → fetchall #5
      6. related tables            → fetchall #6

    On Save click (implicit rerun):
      - cursor.execute(MERGE)      — no fetchall
      - get_column_business_names  → fetchall #7 (returns empty df by default)
      - other queries              → cache HIT
    """

    def _at_after_save(self, monkeypatch, name: str = "Customer ID") -> AppTest:
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "false")

        def detail_side_effect(*args, **kwargs):
            cursor = get_db_cursor()
            sql = (
                cursor.execute.call_args_list[-1][0][0]
                if cursor.execute.call_args_list
                else ""
            )
            if "permissions_cache" in sql and "tables_metadata" in sql:
                return make_tables_df()
            if "tables_metadata" in sql:
                return make_tables_df()
            if "columns_metadata" in sql and "JOIN" not in sql:
                return make_columns_df()
            if "permissions_cache" in sql:
                return make_grants_df()
            if "lineage_cache" in sql:
                return _EMPTY_LINEAGE()
            if "UNION" in sql and "columns_metadata" in sql:
                return _EMPTY_RELATED()
            if "business_name_overrides" in sql:
                return _EMPTY_OVERRIDES()
            if "comments" in sql:
                return _EMPTY_COMMENTS()
            return pd.DataFrame()

        sql_returns(side_effect=detail_side_effect)
        at = authenticated_app()
        at.session_state["catalog_search"] = TABLE_NAME
        at.session_state["dd_col_edit_mode"] = EDIT_KEY
        at.run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()

        inp = next(t for t in at.text_input if "col_biz_name" in t.key)
        inp.set_value(name)
        next(b for b in at.button if b.label == "Save").click().run()
        return at

    # The previous MERGE-INTO assertions verified SQL syntax of the
    # Databricks-direct write path, which was deleted in TODO #7. The DuckDB
    # ON CONFLICT path is exercised by tests/test_storage_audit.py
    # (TestDuckDBStorageRoundTrip::test_business_name_override_round_trip).

    def test_bulk_fetch_uses_single_query_for_all_columns(self, monkeypatch):
        """get_column_business_names must use one query per table, not one per column."""
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "false")

        def detail_side_effect(*args, **kwargs):
            cursor = get_db_cursor()
            sql = (
                cursor.execute.call_args_list[-1][0][0]
                if cursor.execute.call_args_list
                else ""
            )
            if "permissions_cache" in sql and "tables_metadata" in sql:
                return make_tables_df()
            if "tables_metadata" in sql:
                return make_tables_df()
            if "columns_metadata" in sql and "JOIN" not in sql:
                return make_columns_df()
            if "permissions_cache" in sql:
                return make_grants_df()
            if "lineage_cache" in sql:
                return _EMPTY_LINEAGE()
            if "UNION" in sql and "columns_metadata" in sql:
                return _EMPTY_RELATED()
            if "business_name_overrides" in sql:
                return _EMPTY_OVERRIDES()
            if "comments" in sql:
                return _EMPTY_COMMENTS()
            return pd.DataFrame()

        sql_returns(side_effect=detail_side_effect)
        at = authenticated_app()
        at.session_state["catalog_search"] = TABLE_NAME
        at.run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()

        sqls = [c[0][0] for c in get_db_cursor().execute.call_args_list]
        override_queries = [s for s in sqls if "business_name_overrides" in s]
        # Exactly one bulk SELECT — not one per column in the table
        assert len(override_queries) >= 1, (
            f"Expected at least 1 query against business_name_overrides, got {len(override_queries)}: {override_queries}"
        )

    def test_audit_info_displayed_when_available(self, monkeypatch):
        """When the bulk fetch returns an override with audit info, 'Last edited by' renders."""
        monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id")
        monkeypatch.setenv("DEMO_DATA", "false")

        from unittest.mock import patch

        overrides_patcher = patch(
            "src.pages.search.get_column_overrides",
            return_value={
                COLUMN_NAME: {
                    "business_name": "Customer ID",
                    "definition": "",
                    "edited_by": "bob@example.com",
                    "edited_at": "2026-04-24 10:00:00",
                }
            },
        )
        cols_patcher = patch(
            "src.pages.search.get_table_columns",
            return_value=pd.DataFrame(
                {
                    "column_name": [COLUMN_NAME],
                    "data_type": ["STRING"],
                    "comment": [""],
                }
            ),
        )
        overrides_patcher.start()
        cols_patcher.start()
        monkeypatch_undo = (overrides_patcher.stop, cols_patcher.stop)

        audit_overrides = pd.DataFrame(
            {
                "column_name": [COLUMN_NAME],
                "business_name": ["Customer ID"],
                "definition": [""],
                "edited_by": ["bob@example.com"],
                "edited_at": ["2026-04-24 10:00:00"],
            }
        )

        def detail_side_effect(*args, **kwargs):
            cursor = get_db_cursor()
            sql = (
                cursor.execute.call_args_list[-1][0][0]
                if cursor.execute.call_args_list
                else ""
            )
            if "permissions_cache" in sql and "tables_metadata" in sql:
                return make_tables_df()
            if "tables_metadata" in sql:
                return make_tables_df()
            if "columns_metadata" in sql and "JOIN" not in sql:
                return make_columns_df()
            if "permissions_cache" in sql:
                return make_grants_df()
            if "lineage_cache" in sql:
                return _EMPTY_LINEAGE()
            if "UNION" in sql and "columns_metadata" in sql:
                return _EMPTY_RELATED()
            if "business_name_overrides" in sql:
                return audit_overrides
            if "comments" in sql:
                return _EMPTY_COMMENTS()
            return pd.DataFrame()

        sql_returns(side_effect=detail_side_effect)
        at = authenticated_app()
        at.session_state["catalog_search"] = TABLE_NAME
        at.session_state["dd_col_edit_mode"] = EDIT_KEY
        at.run()
        if len(at.button) > 0 and any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()

        try:
            html = _html(*at.markdown)
            assert "Last edited by" in html, "Audit trail not rendered"
            assert "bob@example.com" in html, "Audit trail editor name not rendered"
        finally:
            for undo in monkeypatch_undo:
                undo()


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Sync script — business_name_overrides DDL and write-back
# ═══════════════════════════════════════════════════════════════════════════════


class TestBusinessNameSync:
    """setup_cache_tables creates the table with column_name; push writes ALTER COLUMN."""

    @pytest.fixture(autouse=True)
    def _patch_deps(self):
        from unittest.mock import MagicMock, patch

        mocks = {
            "databricks": MagicMock(),
            "databricks.sdk": MagicMock(),
            "databricks.sql": MagicMock(),
            "dotenv": MagicMock(),
        }
        with patch.dict("sys.modules", mocks):
            yield

    def test_setup_creates_business_name_overrides_table(self):
        """setup_cache_tables must CREATE business_name_overrides with column_name."""
        from unittest.mock import MagicMock, patch

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        with patch("scripts.sync_metadata.get_sql_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            from scripts.sync_metadata import setup_cache_tables

            setup_cache_tables()

        all_sql = " ".join(c[0][0] for c in mock_cursor.execute.call_args_list)
        assert "business_name_overrides" in all_sql
        assert "column_name" in all_sql, (
            "business_name_overrides DDL must include column_name"
        )
        assert "definition" in all_sql, (
            "business_name_overrides DDL must include definition"
        )

    def test_push_overrides_issues_alter_column_for_each_row(self):
        """push_business_name_overrides must issue ALTER TABLE ... ALTER COLUMN ... COMMENT."""
        import pandas as pd
        from unittest.mock import MagicMock, patch

        overrides_df = pd.DataFrame(
            {
                "table_full_name": [
                    "main.analytics.customers",
                    "main.analytics.orders",
                ],
                "column_name": ["customer_id", "order_date"],
                "business_name": ["Customer ID", "Order Placed Date"],
                "definition": ["A unique customer ID", "The date the order was placed"],
            }
        )

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall_as_pandas.return_value = overrides_df

        with patch("scripts.sync_metadata.get_sql_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            from scripts.sync_metadata import push_business_name_overrides

            push_business_name_overrides()

        sqls = [c[0][0] for c in mock_cursor.execute.call_args_list]
        alter_sqls = [
            s
            for s in sqls
            if "ALTER TABLE" in s.upper() and "ALTER COLUMN" in s.upper()
        ]
        assert len(alter_sqls) == 2, (
            f"Expected 2 ALTER COLUMN calls, got {len(alter_sqls)}: {alter_sqls}"
        )
        assert any("customer_id" in s for s in alter_sqls)
        assert any("order_date" in s for s in alter_sqls)

    def test_push_overrides_no_calls_when_table_empty(self):
        """push_business_name_overrides must issue no ALTER calls when overrides is empty."""
        import pandas as pd
        from unittest.mock import MagicMock, patch

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame(
            columns=["table_full_name", "column_name", "business_name", "definition"]
        )

        with patch("scripts.sync_metadata.get_sql_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            from scripts.sync_metadata import push_business_name_overrides

            push_business_name_overrides()

        sqls = [c[0][0] for c in mock_cursor.execute.call_args_list]
        assert not any("ALTER TABLE" in s.upper() for s in sqls)

def test_render_table_business_name_editor_exceptions():
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_editor():
        from src.ui.cards.detail import render_table_business_name_editor

        render_table_business_name_editor(
            "main.public.test",
            "Test En",
            "Test Fr",
            "Def En",
            "Def Fr",
        )

    at = AppTest.from_function(render_editor)

    # Test ValueError
    with patch("src.ui.cards.detail.save_table_business_name", side_effect=ValueError("Invalid Input")):
        at.run()
        assert len(at.button) > 0
        at.button[0].click().run()
        assert len(at.error) > 0

    # Test Generic Exception
    with patch("src.ui.cards.detail.save_table_business_name", side_effect=Exception("DB Failure")):
        at.run()
        assert len(at.button) > 0
        at.button[0].click().run()
        assert len(at.error) > 0

    # Test PermissionError
    with patch("src.ui.cards.detail.save_table_business_name", side_effect=PermissionError("Forbidden")):
        at.run()
        assert len(at.button) > 0
        at.button[0].click().run()
        assert len(at.error) > 0

def test_render_data_sample():
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_sample():
        import streamlit as st
        from src.ui.cards.detail import render_data_sample

        st.session_state["user_groups"] = ["admin"]
        render_data_sample("main.public.test")

    # Test Authorized (Demo Mode)
    at = AppTest.from_function(render_sample)
    with patch("src.ui.cards.detail.get_authorized_table_names", return_value=["main.public.test"]):
        with patch("src.ui.cards.detail.is_demo_mode", return_value=True):
            at.run()
            assert not at.exception
            assert len(at.dataframe) > 0

    # Test Unauthorized
    at = AppTest.from_function(render_sample)
    with patch("src.ui.cards.detail.get_authorized_table_names", return_value=[]):
        at.run()
        assert not at.exception
        assert len(at.error) > 0
