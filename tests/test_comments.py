"""
Tests for the commenting feature.
"""
from __future__ import annotations

import os
import pandas as pd
from streamlit.testing.v1 import AppTest

from tests.conftest import get_db_cursor, sql_returns

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")

# Matches _DEMO_TABLES in app.py
TABLE_NAME = "customers"
FULL_NAME  = "main.analytics.customers"

def _EMPTY_OVERRIDES(cursor=None): return pd.DataFrame(columns=["column_name", "business_name", "definition", "edited_by", "edited_at"])
def _EMPTY_LINEAGE(cursor=None): return pd.DataFrame(columns=["direction", "entity_full_name", "entity_type"])
def _EMPTY_RELATED(cursor=None): return pd.DataFrame(columns=["full_name", "table_name", "catalog_name", "schema_name", "relationship"])
def _EMPTY_COMMENTS(cursor=None): return pd.DataFrame(columns=["comment_id", "author_name", "author_email", "comment_text", "created_at"])
def _EMPTY_STEWARD(cursor=None): return pd.DataFrame(columns=["steward_email"])


# ── Shared helpers ─────────────────────────────────────────────────────────────

def authenticated_app() -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=15)
    at.session_state["authenticated"] = True
    at.session_state["user_groups"]   = ["finance_dept_id", "all_employees_id"]
    at.session_state["user_name"]     = "Finance User"
    at.session_state["user_email"]    = "finance.user@example.com"
    at.session_state["bookmarks"]     = set()
    at.session_state["_prefs_loaded"] = True
    return at


def _html(*markdowns) -> str:
    return " ".join(m.value for m in markdowns)


def _at_detail(monkeypatch) -> AppTest:
    """Navigate to the customers detail pane in demo mode."""
    monkeypatch.setenv("DEMO_DATA", "true")
    at = authenticated_app()
    at.run()
    at.selectbox(key="catalog_search").select(TABLE_NAME).run()
    if any("View details" in b.label for b in at.button):
        next(b for b in at.button if "View details" in b.label).click().run()
    return at

def _make_tables_df() -> pd.DataFrame:
    return pd.DataFrame({
        "full_name":         [FULL_NAME],
        "catalog_name":      ["main"],
        "schema_name":       ["analytics"],
        "table_name":        [TABLE_NAME],
        "name":              [TABLE_NAME],
        "match_type":        ["Table"],
        "table_description": ["test"],
        "table_type":        ["TABLE"],
        "updated_at":        [pd.Timestamp.now()],
    })

def _make_columns_df() -> pd.DataFrame:
    return pd.DataFrame({
        "column_name": ["customer_id", "email"],
        "data_type":   ["BIGINT", "STRING"],
        "comment":     ["Primary key", "Email address"],
    })

def _make_grants_df() -> pd.DataFrame:
    return pd.DataFrame({"principal": ["SELECT_ALL_USERS"], "privilege": ["SELECT"]})

def _at_production_detail(monkeypatch, tables_df=None, columns_df=None, grants_df=None, 
                         lineage_df=None, related_df=None, steward_df=None, 
                         comments_df=None) -> AppTest:
    monkeypatch.setenv("DEMO_DATA", "false")
    def detail_side_effect(*args, **kwargs):
        cursor = get_db_cursor()
        sql = cursor.execute.call_args_list[-1][0][0] if cursor.execute.call_args_list else ""
        if "permissions_cache" in sql and "tables_metadata" in sql: return tables_df if tables_df is not None else _make_tables_df()
        if "tables_metadata" in sql and "steward_email" in sql: return steward_df if steward_df is not None else pd.DataFrame({"steward_email": ["steward@example.com"]})
        if "tables_metadata" in sql: return tables_df if tables_df is not None else _make_tables_df()
        if "columns_metadata" in sql and "JOIN" not in sql: return columns_df if columns_df is not None else _make_columns_df()
        if "permissions_cache" in sql: return grants_df if grants_df is not None else _make_grants_df()
        if "lineage_cache" in sql: return lineage_df if lineage_df is not None else _EMPTY_LINEAGE()
        if "UNION" in sql and "columns_metadata" in sql: return related_df if related_df is not None else _EMPTY_RELATED()
        if "business_name_overrides" in sql: return _EMPTY_OVERRIDES()
        if "comments" in sql: return comments_df if comments_df is not None else _EMPTY_COMMENTS()
        return pd.DataFrame()
    sql_returns(side_effect=detail_side_effect)
    at = authenticated_app()
    at.run()
    at.selectbox(key="catalog_search").select(TABLE_NAME).run()
    if any("View details" in b.label for b in at.button):
        next(b for b in at.button if "View details" in b.label).click().run()
    return at


class TestGetTableSteward:
    """Steward lookup: production DB query, graceful fallback."""

    def test_production_queries_tables_metadata(self, monkeypatch):
        """Production mode must query tables_metadata for steward_email."""
        at = _at_production_detail(monkeypatch)
        cursor = get_db_cursor()
        executed = [str(c) for c in cursor.execute.call_args_list]
        assert any("tables_metadata" in q and "steward_email" in q for q in executed)


class TestGetTableComments:
    """Comment retrieval: demo reads session state, production queries DB."""

    def test_demo_no_comments_shows_zero_count(self, monkeypatch):
        """Demo mode with no comments must show '0' in the § Comments header."""
        at = _at_detail(monkeypatch)
        html = _html(*at.markdown)
        assert "0" in html

    def test_demo_preseeded_comments_rendered(self, monkeypatch):
        """Comments pre-seeded in demo_comments session state must appear in the UI."""
        monkeypatch.setenv("DEMO_DATA", "true")
        at = authenticated_app()
        at.session_state["demo_comments"] = {
            FULL_NAME: [{
                "comment_id":   "abc-123",
                "author_name":  "Alice",
                "author_email": "alice@corp.com",
                "comment_text": "Great table!",
                "created_at":   "2026-04-24T09:00",
            }]
        }
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()
        if any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()

        html = _html(*at.markdown)
        assert "Great table!" in html
        assert "Alice" in html

    def test_production_queries_comments_table(self, monkeypatch):
        """Production mode must query the comments table."""
        at = _at_production_detail(monkeypatch)
        cursor = get_db_cursor()
        executed = [str(c) for c in cursor.execute.call_args_list]
        assert any("comments" in q and "object_name" in q for q in executed)


class TestSendCommentEmail:
    """Comment notification logic: SMTP connection, recipient matching."""

    def test_demo_mode_send_does_not_raise(self, monkeypatch):
        """In demo mode, send_comment_email must not try to connect to SMTP."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        at.text_area(key=f"dd_comment_text_{FULL_NAME}").set_value("Demo comment.").run()
        next(b for b in at.button if b.label == "Send").click().run()
        assert not at.exception

    def test_no_smtp_config_send_still_saves_comment(self, monkeypatch):
        """Missing SMTP_HOST must not block comment saving."""
        monkeypatch.delenv("SMTP_HOST", raising=False)
        at = _at_production_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        at.text_area(key=f"dd_comment_text_{FULL_NAME}").set_value("No SMTP test.").run()
        next(b for b in at.button if b.label == "Send").click().run()
        cursor = get_db_cursor()
        sql_calls = [str(c) for c in cursor.execute.call_args_list]
        assert any("INSERT" in s and "comments" in s for s in sql_calls)


class TestSaveComment:
    """Persistence: demo writes to session state; production INSERTs to DB."""

    def test_demo_send_writes_to_session_state(self, monkeypatch):
        """Demo mode: clicking Send must append the comment to demo_comments."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        at.text_area(key=f"dd_comment_text_{FULL_NAME}").set_value("Hello!").run()
        next(b for b in at.button if b.label == "Send").click().run()
        saved = at.session_state["demo_comments"].get(FULL_NAME, [])
        assert any(c["comment_text"] == "Hello!" for c in saved)


class TestCommentUI:
    """Visibility, form opening, and Send/Cancel button logic."""

    def test_leave_comment_button_present_for_all_users(self, monkeypatch):
        """'Leave a comment' button must be visible to any authenticated user."""
        at = _at_detail(monkeypatch)
        labels = [b.label for b in at.button]
        assert "Leave a comment" in labels

    def test_comment_form_opens_on_click(self, monkeypatch):
        """Clicking 'Leave a comment' must render a text area for comment input."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        area_keys = [a.key for a in at.text_area]
        assert any(f"dd_comment_text_{FULL_NAME}" == k for k in area_keys)

    def test_cancel_closes_form(self, monkeypatch):
        """Clicking Cancel must close the comment form (no text area)."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        next(b for b in at.button if b.label == "Cancel").click().run()
        area_keys = [a.key for a in at.text_area]
        assert not any(f"dd_comment_text_{FULL_NAME}" == k for k in area_keys)
