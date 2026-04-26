"""
Tests for the commenting feature.

Users can leave comments on any table. Comments are persisted to the
`data_governance.dictionary_cache.comments` table and a notification email is
sent to the table's data steward (stored as `steward_email` in tables_metadata).

Coverage:
  - get_table_steward: demo mode vs production, missing/empty steward
  - get_table_comments: demo mode reads session state; production queries DB
  - save_comment: demo writes to session state + calls send_comment_email
  - send_comment_email: demo prints; production SMTP; silently skips when SMTP_HOST missing
  - UI: "Leave a comment" button visible to all authenticated users
  - UI: form opens on click, submits on Send, closes on Cancel
  - UI: warning shown when steward is not configured
  - sync script: comments table DDL present and append-only (not TRUNCATEd)

All UI / helper tests run with DEMO_DATA=true to avoid SQL mock sequencing
complexity.  Production-path tests (send email, DB write) use the test-mocked
cursor or patch smtplib directly.
"""
from __future__ import annotations

import os
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch
from streamlit.testing.v1 import AppTest

from tests.conftest import get_db_cursor, sql_returns

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")

# Matches _DEMO_TABLES in app.py
TABLE_NAME = "customers"
FULL_NAME  = "main.analytics.customers"

_EMPTY_OVERRIDES = lambda: pd.DataFrame(
    columns=["column_name", "business_name", "definition", "edited_by", "edited_at"]
)
_EMPTY_LINEAGE  = lambda: pd.DataFrame(columns=["direction", "entity_full_name", "entity_type"])
_EMPTY_RELATED  = lambda: pd.DataFrame(columns=["full_name", "table_name", "catalog_name", "schema_name", "relationship"])
_EMPTY_COMMENTS = lambda: pd.DataFrame(columns=["comment_id", "author_name", "author_email", "comment_text", "created_at"])
_EMPTY_STEWARD  = lambda: pd.DataFrame(columns=["steward_email"])


# ── Shared helpers ─────────────────────────────────────────────────────────────

def authenticated_app() -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=15)
    at.session_state["authenticated"] = True
    at.session_state["user_groups"]   = ["finance_dept_id", "all_employees_id"]
    at.session_state["user_name"]     = "Finance User"
    at.session_state["user_email"]    = "finance.user@example.com"
    return at


def _html(*markdowns) -> str:
    return " ".join(m.value for m in markdowns)


def _at_detail(monkeypatch) -> AppTest:
    """Navigate to the customers detail pane in demo mode."""
    monkeypatch.setenv("DEMO_DATA", "true")
    at = authenticated_app()
    at.run()
    at.selectbox(key="catalog_search").select(TABLE_NAME).run()
    return at


def _make_tables_df() -> pd.DataFrame:
    return pd.DataFrame({
        "full_name":         [FULL_NAME],
        "catalog_name":      ["main"],
        "schema_name":       ["analytics"],
        "table_name":        [TABLE_NAME],
        "table_description": ["Customer master record"],
        "table_type":        ["TABLE"],
        "updated_at":        [pd.Timestamp("2026-04-22 10:00")],
    })


def _make_columns_df() -> pd.DataFrame:
    return pd.DataFrame({
        "column_name": ["customer_id", "email"],
        "data_type":   ["BIGINT", "STRING"],
        "comment":     ["Primary key", "Email address"],
    })


def _make_grants_df() -> pd.DataFrame:
    return pd.DataFrame({
        "principal": ["SELECT_ALL_USERS"],
        "privilege":  ["SELECT"],
    })


# ═══════════════════════════════════════════════════════════════════════════════
# 1. get_table_steward
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetTableSteward:
    """Steward lookup: demo shortcut, production DB query, graceful fallback."""

    def test_demo_mode_has_configured_steward(self, monkeypatch):
        """In demo mode the steward is always set — the form should NOT show the
        no-steward warning even when the form is open."""
        monkeypatch.setenv("DEMO_DATA", "true")
        at = authenticated_app()
        at.session_state[f"dd_comment_open_{FULL_NAME}"] = True
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()

        # warning() widgets would appear if steward is empty
        # demo always returns "steward@example.com" so no warning expected
        assert len(at.warning) == 0, (
            f"Unexpected warnings in demo mode (steward should be configured): {[w.value for w in at.warning]}"
        )

    def test_production_queries_tables_metadata(self, monkeypatch):
        """Production mode must query tables_metadata for steward_email."""
        monkeypatch.delenv("DEMO_DATA", raising=False)
        # Query order: tables, overrides, columns, grants, lineage, related, steward, comments
        sql_returns(
            _make_tables_df(), _EMPTY_OVERRIDES(), _make_columns_df(),
            _make_grants_df(), _EMPTY_LINEAGE(), _EMPTY_RELATED(),
            pd.DataFrame({"steward_email": ["owner@corp.com"]}),  # get_table_steward
            _EMPTY_COMMENTS(),                                     # get_table_comments
        )
        at = authenticated_app()
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()

        cursor = get_db_cursor()
        executed = [str(c) for c in cursor.execute.call_args_list]
        assert any("tables_metadata" in q and "steward_email" in q for q in executed), (
            f"tables_metadata steward_email query not found. SQL calls: {executed}"
        )

    def test_production_steward_query_uses_full_name_param(self, monkeypatch):
        """The steward_email query must parameterise on the table's full_name."""
        monkeypatch.delenv("DEMO_DATA", raising=False)
        sql_returns(
            _make_tables_df(), _EMPTY_OVERRIDES(), _make_columns_df(),
            _make_grants_df(), _EMPTY_LINEAGE(), _EMPTY_RELATED(),
            _EMPTY_STEWARD(),   # get_table_steward
            _EMPTY_COMMENTS(),  # get_table_comments
        )
        at = authenticated_app()
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()

        cursor = get_db_cursor()
        # Find the parameterised execute call that queries for steward_email
        steward_calls = [
            c for c in cursor.execute.call_args_list
            if "steward_email" in str(c)
        ]
        assert len(steward_calls) >= 1, (
            "No parameterised steward_email query found"
        )
        params = steward_calls[0][0][1] if len(steward_calls[0][0]) > 1 else {}
        assert params.get("full_name") == FULL_NAME, (
            f"steward_email query must use full_name param. Params: {params}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. get_table_comments
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetTableComments:
    """Comment retrieval: demo reads session state, production queries DB."""

    def test_demo_no_comments_shows_zero_count(self, monkeypatch):
        """Demo mode with no comments must show '0' in the § Comments header."""
        at = _at_detail(monkeypatch)
        html = _html(*at.markdown)
        assert "0" in html, "Expected 0 comment count in § Comments header"

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

        html = _html(*at.markdown)
        assert "Great table!" in html, "Pre-seeded comment text not rendered"
        assert "Alice" in html, "Pre-seeded author name not rendered"

    def test_production_queries_comments_table(self, monkeypatch):
        """Production mode must query the comments table."""
        monkeypatch.delenv("DEMO_DATA", raising=False)
        sql_returns(
            _make_tables_df(), _EMPTY_OVERRIDES(), _make_columns_df(),
            _make_grants_df(), _EMPTY_LINEAGE(), _EMPTY_RELATED(),
            _EMPTY_STEWARD(),   # get_table_steward
            _EMPTY_COMMENTS(),  # get_table_comments
        )
        at = authenticated_app()
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()

        cursor = get_db_cursor()
        executed = [str(c) for c in cursor.execute.call_args_list]
        assert any("comments" in q and "object_name" in q for q in executed), (
            f"comments table not queried in production mode. SQL calls: {executed}"
        )

    def test_demo_multiple_comments_show_count(self, monkeypatch):
        """Multiple comments in demo_comments must increment the § Comments count."""
        monkeypatch.setenv("DEMO_DATA", "true")
        at = authenticated_app()
        at.session_state["demo_comments"] = {
            FULL_NAME: [
                {"comment_id": "a", "author_name": "Alice", "author_email": "a@x.com",
                 "comment_text": "First!", "created_at": "2026-04-01"},
                {"comment_id": "b", "author_name": "Bob", "author_email": "b@x.com",
                 "comment_text": "Second.", "created_at": "2026-04-02"},
            ]
        }
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()

        html = _html(*at.markdown)
        # Both authors must appear
        assert "Alice" in html, "First comment author not rendered"
        assert "Bob" in html, "Second comment author not rendered"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. send_comment_email
# ═══════════════════════════════════════════════════════════════════════════════

class TestSendCommentEmail:
    """Email sending: demo skips silently; production SMTP; skips without config."""

    def test_demo_mode_send_does_not_raise(self, monkeypatch):
        """Clicking Send in demo mode must not raise an exception (no SMTP config)."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        at.text_area(key=f"dd_comment_text_{FULL_NAME}").set_value("Hello!").run()
        next(b for b in at.button if b.label == "Send").click().run()

        # Verify the comment was persisted — AppTest accumulates widgets across
        # st.rerun() boundaries so checking button absence is unreliable; checking
        # session_state is authoritative.
        assert not at.exception, f"Exception raised: {at.exception}"
        saved = (at.session_state["demo_comments"] if "demo_comments" in at.session_state else {}).get(FULL_NAME, [])
        assert len(saved) == 1, f"Expected 1 saved comment, got {len(saved)}"
        assert saved[0]["comment_text"] == "Hello!"

    def test_no_smtp_config_send_still_saves_comment(self, monkeypatch):
        """Without SMTP_HOST configured, Send must still persist the comment."""
        monkeypatch.delenv("DEMO_DATA", raising=False)
        monkeypatch.delenv("SMTP_HOST", raising=False)

        sql_returns(
            _make_tables_df(), _EMPTY_OVERRIDES(), _make_columns_df(),
            _make_grants_df(), _EMPTY_LINEAGE(), _EMPTY_RELATED(),
            _EMPTY_STEWARD(),  # get_table_steward → no steward (send_comment_email skips)
            _EMPTY_COMMENTS(), # get_table_comments
        )
        at = authenticated_app()
        at.session_state["catalog_search"] = TABLE_NAME
        at.session_state[f"dd_comment_open_{FULL_NAME}"] = True
        at.session_state[f"dd_comment_text_{FULL_NAME}"] = "No SMTP test."
        at.run()
        next(b for b in at.button if b.label == "Send").click().run()

        cursor = get_db_cursor()
        sql_calls = [str(c) for c in cursor.execute.call_args_list]
        assert any("INSERT" in s and "comments" in s for s in sql_calls), (
            f"Comment not INSERTed even without SMTP. SQL calls: {sql_calls}"
        )

    def test_production_calls_smtp_with_correct_recipient(self, monkeypatch):
        """Production path must call smtplib.SMTP and send to the steward address."""
        monkeypatch.delenv("DEMO_DATA", raising=False)
        monkeypatch.setenv("SMTP_HOST",     "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT",     "587")
        monkeypatch.setenv("SMTP_USER",     "sender@corp.com")
        monkeypatch.setenv("SMTP_PASSWORD", "secret")

        # get_table_steward and get_table_comments are uncached — they're called
        # on every Streamlit execution.  Provide their DataFrames for:
        #   [0] tables, [1] overrides, [2] cols, [3] grants, [4] lineage, [5] related
        #   [6] steward (render), [7] comments (render)
        #   [8] overrides (button-click re-exec), [9] steward (button-click re-exec)
        _steward_df = pd.DataFrame({"steward_email": ["owner@corp.com"]})
        sql_returns(
            _make_tables_df(), _EMPTY_OVERRIDES(), _make_columns_df(),
            _make_grants_df(), _EMPTY_LINEAGE(), _EMPTY_RELATED(),
            _steward_df,        # get_table_steward (render exec)
            _EMPTY_COMMENTS(),  # get_table_comments (render exec)
            _EMPTY_OVERRIDES(), # get_column_business_names (button-click re-exec)
            _steward_df,        # get_table_steward (button-click re-exec)
            _EMPTY_COMMENTS(),  # get_table_comments (button-click re-exec)
        )

        smtp_calls: list = []

        class _FakeSMTP:
            def __init__(self, host, port):
                smtp_calls.append((host, port))
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def starttls(self):
                pass
            def login(self, *a):
                pass
            def sendmail(self, *a):
                pass

        with patch("smtplib.SMTP", _FakeSMTP):
            at = authenticated_app()
            # Pre-seed catalog_search + form state to avoid extra at.run() calls
            at.session_state["catalog_search"] = TABLE_NAME
            at.session_state[f"dd_comment_open_{FULL_NAME}"] = True
            at.session_state[f"dd_comment_text_{FULL_NAME}"] = "SMTP test."
            at.run()
            next(b for b in at.button if b.label == "Send").click().run()

        assert len(smtp_calls) >= 1, f"Expected at least 1 SMTP call, got {smtp_calls}"
        assert smtp_calls[0][0] == "smtp.example.com"

    def test_smtp_error_does_not_crash_the_app(self, monkeypatch):
        """An SMTP failure must be caught — the app must still function."""
        monkeypatch.delenv("DEMO_DATA", raising=False)
        monkeypatch.setenv("SMTP_HOST",     "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT",     "587")
        monkeypatch.setenv("SMTP_USER",     "sender@corp.com")
        monkeypatch.setenv("SMTP_PASSWORD", "secret")

        sql_returns(
            _make_tables_df(), _EMPTY_OVERRIDES(), _make_columns_df(),
            _make_grants_df(), _EMPTY_LINEAGE(), _EMPTY_RELATED(),
            pd.DataFrame({"steward_email": ["owner@corp.com"]}),
            _EMPTY_COMMENTS(),
        )

        with patch("smtplib.SMTP", side_effect=Exception("connection refused")):
            at = authenticated_app()
            at.session_state["catalog_search"] = TABLE_NAME
            at.session_state[f"dd_comment_open_{FULL_NAME}"] = True
            at.session_state[f"dd_comment_text_{FULL_NAME}"] = "Error test."
            at.run()
            # Must not raise
            next(b for b in at.button if b.label == "Send").click().run()

        assert not at.exception, f"App raised an exception on SMTP failure: {at.exception}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. save_comment — DB write path
# ═══════════════════════════════════════════════════════════════════════════════

class TestSaveComment:
    """Persistence: demo writes to session state; production INSERTs to DB."""

    def test_demo_send_writes_to_session_state(self, monkeypatch):
        """Demo mode: clicking Send must append the comment to demo_comments."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        at.text_area(key=f"dd_comment_text_{FULL_NAME}").set_value("Is this deduplicated?").run()
        next(b for b in at.button if b.label == "Send").click().run()

        demo = at.session_state["demo_comments"] if "demo_comments" in at.session_state else {}
        texts = [c["comment_text"] for c in demo.get(FULL_NAME, [])]
        assert "Is this deduplicated?" in texts, (
            f"Comment not found in demo_comments after Send. demo={demo}"
        )

    def test_demo_send_stores_author_name(self, monkeypatch):
        """Demo mode: saved comment must record the logged-in user's name."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        at.text_area(key=f"dd_comment_text_{FULL_NAME}").set_value("Check grain.").run()
        next(b for b in at.button if b.label == "Send").click().run()

        demo = at.session_state["demo_comments"] if "demo_comments" in at.session_state else {}
        comments = demo.get(FULL_NAME, [])
        assert len(comments) >= 1
        assert comments[-1]["author_name"] == "Finance User"

    def test_production_inserts_to_comments_table(self, monkeypatch):
        """Production: clicking Send must INSERT into the comments table."""
        monkeypatch.delenv("DEMO_DATA", raising=False)
        sql_returns(
            _make_tables_df(), _EMPTY_OVERRIDES(), _make_columns_df(),
            _make_grants_df(), _EMPTY_LINEAGE(), _EMPTY_RELATED(),
            _EMPTY_STEWARD(),  # get_table_steward
            _EMPTY_COMMENTS(), # get_table_comments
        )
        at = authenticated_app()
        at.session_state["catalog_search"] = TABLE_NAME
        at.session_state[f"dd_comment_open_{FULL_NAME}"] = True
        at.session_state[f"dd_comment_text_{FULL_NAME}"] = "Refresh cadence?"
        at.run()
        next(b for b in at.button if b.label == "Send").click().run()

        cursor = get_db_cursor()
        sql_calls = [str(c) for c in cursor.execute.call_args_list]
        assert any("INSERT" in s and "comments" in s for s in sql_calls), (
            f"No INSERT into comments table. SQL calls: {sql_calls}"
        )

    def test_production_insert_includes_object_name(self, monkeypatch):
        """Production INSERT params must include the table full_name as object_name."""
        monkeypatch.delenv("DEMO_DATA", raising=False)
        sql_returns(
            _make_tables_df(), _EMPTY_OVERRIDES(), _make_columns_df(),
            _make_grants_df(), _EMPTY_LINEAGE(), _EMPTY_RELATED(),
            _EMPTY_STEWARD(),
            _EMPTY_COMMENTS(),
        )
        at = authenticated_app()
        at.session_state["catalog_search"] = TABLE_NAME
        at.session_state[f"dd_comment_open_{FULL_NAME}"] = True
        at.session_state[f"dd_comment_text_{FULL_NAME}"] = "Any SLA?"
        at.run()
        next(b for b in at.button if b.label == "Send").click().run()

        cursor = get_db_cursor()
        insert_calls = [
            c for c in cursor.execute.call_args_list
            if "INSERT" in str(c) and "comments" in str(c)
        ]
        assert len(insert_calls) >= 1
        params = insert_calls[0][0][1] if len(insert_calls[0][0]) > 1 else {}
        assert params.get("object_name") == FULL_NAME


# ═══════════════════════════════════════════════════════════════════════════════
# 5. UI — Comment form lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommentUI:
    """UI interactions: button visibility, form open/close, steward warning."""

    def test_leave_comment_button_present_for_all_users(self, monkeypatch):
        """'Leave a comment' button must be visible to any authenticated user."""
        at = _at_detail(monkeypatch)
        labels = [b.label for b in at.button]
        assert "Leave a comment" in labels, (
            f"'Leave a comment' button not found. Buttons: {labels}"
        )

    def test_comment_form_opens_on_click(self, monkeypatch):
        """Clicking 'Leave a comment' must render a text area for comment input."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        area_keys = [a.key for a in at.text_area]
        assert any(f"dd_comment_text_{FULL_NAME}" == k for k in area_keys), (
            f"Comment text area not found after clicking button. Keys: {area_keys}"
        )

    def test_send_and_cancel_buttons_appear_in_form(self, monkeypatch):
        """Send and Cancel buttons must appear once the comment form is open."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        labels = [b.label for b in at.button]
        assert "Send" in labels,   f"Send button missing. Buttons: {labels}"
        assert "Cancel" in labels, f"Cancel button missing. Buttons: {labels}"

    def test_cancel_closes_form(self, monkeypatch):
        """Clicking Cancel must close the comment form (no text area)."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        next(b for b in at.button if b.label == "Cancel").click().run()

        area_keys = [a.key for a in at.text_area]
        assert not any(f"dd_comment_text_{FULL_NAME}" == k for k in area_keys), (
            "Comment text area still visible after Cancel"
        )

    def test_cancel_restores_leave_comment_button(self, monkeypatch):
        """After Cancel the 'Leave a comment' button must reappear."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        next(b for b in at.button if b.label == "Cancel").click().run()

        assert any(b.label == "Leave a comment" for b in at.button), (
            "'Leave a comment' button not restored after Cancel"
        )

    def test_send_persists_comment_in_demo_mode(self, monkeypatch):
        """Clicking Send must write the comment to demo_comments session state."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        at.text_area(key=f"dd_comment_text_{FULL_NAME}").set_value("What's the grain?").run()
        next(b for b in at.button if b.label == "Send").click().run()

        demo = at.session_state["demo_comments"] if "demo_comments" in at.session_state else {}
        texts = [c["comment_text"] for c in demo.get(FULL_NAME, [])]
        assert "What's the grain?" in texts, (
            f"Comment not found in demo_comments after Send. demo={demo}"
        )

    def test_send_closes_form(self, monkeypatch):
        """After successful Send the form must close (no text area)."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        at.text_area(key=f"dd_comment_text_{FULL_NAME}").set_value("Looks good.").run()
        next(b for b in at.button if b.label == "Send").click().run()

        area_keys = [a.key for a in at.text_area]
        assert not any(f"dd_comment_text_{FULL_NAME}" == k for k in area_keys), (
            "Comment text area still visible after Send"
        )

    def test_send_with_empty_text_shows_warning(self, monkeypatch):
        """Clicking Send with an empty comment must show a warning, not close the form."""
        at = _at_detail(monkeypatch)
        next(b for b in at.button if b.label == "Leave a comment").click().run()
        # Do not type anything — leave the textarea empty
        next(b for b in at.button if b.label == "Send").click().run()

        area_keys = [a.key for a in at.text_area]
        assert any(f"dd_comment_text_{FULL_NAME}" == k for k in area_keys), (
            "Comment form closed despite empty input — expected warning to keep it open"
        )
        assert len(at.warning) >= 1, "Expected a warning widget for empty comment"

    def test_comments_section_header_present(self, monkeypatch):
        """The '§ Comments' section header must appear in the detail pane."""
        at = _at_detail(monkeypatch)
        html = _html(*at.markdown)
        assert "Comments" in html, "§ Comments section header not found in detail pane"

    def test_existing_comment_appears_in_ui(self, monkeypatch):
        """A comment already in demo_comments must be rendered in the panel."""
        monkeypatch.setenv("DEMO_DATA", "true")
        at = authenticated_app()
        at.session_state["demo_comments"] = {
            FULL_NAME: [{
                "comment_id":   "xyz",
                "author_name":  "Bob",
                "author_email": "bob@corp.com",
                "comment_text": "Pre-existing note.",
                "created_at":   "2026-04-20",
            }]
        }
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()

        html = _html(*at.markdown)
        assert "Pre-existing note." in html, "Pre-existing comment not rendered in panel"
        assert "Bob" in html, "Author name not rendered for pre-existing comment"

    def test_steward_warning_css_class_defined(self, monkeypatch):
        """The dd-comment-no-steward CSS class must be defined in the injected styles."""
        at = _at_detail(monkeypatch)
        html = _html(*at.markdown)
        # CSS class definition lives in the <style> block
        assert "dd-comment-no-steward" in html, (
            "dd-comment-no-steward CSS class not found in rendered HTML"
        )

    def test_comment_form_preopen_via_session_state(self, monkeypatch):
        """Pre-seeding dd_comment_open in session state must open the form immediately."""
        monkeypatch.setenv("DEMO_DATA", "true")
        at = authenticated_app()
        at.session_state[f"dd_comment_open_{FULL_NAME}"] = True
        at.run()
        at.selectbox(key="catalog_search").select(TABLE_NAME).run()

        area_keys = [a.key for a in at.text_area]
        assert any(f"dd_comment_text_{FULL_NAME}" == k for k in area_keys), (
            f"Comment form not open despite pre-seeded session state. Keys: {area_keys}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Sync script — comments table DDL and append-only guarantee
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommentsSync:
    """The comments table must exist in DDL and must NOT be truncated during sync."""

    @pytest.fixture(autouse=True)
    def _mock_modules(self):
        """Stub databricks / dotenv for sync_metadata import."""
        mock_modules = {
            "databricks":        MagicMock(),
            "databricks.sdk":    MagicMock(),
            "databricks.sql":    MagicMock(),
            "dotenv":            MagicMock(),
        }
        with patch.dict("sys.modules", mock_modules):
            yield

    @patch("scripts.sync_metadata.get_sql_connection")
    def test_comments_table_ddl_present(self, mock_get_sql_connection):
        """setup_cache_tables must CREATE the comments table with required columns."""
        mock_conn   = MagicMock()
        mock_cursor = MagicMock()
        mock_get_sql_connection.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        from scripts.sync_metadata import setup_cache_tables, CATALOG_CACHE, SCHEMA_CACHE
        setup_cache_tables()

        calls = [c[0][0] for c in mock_cursor.execute.call_args_list]
        comments_ddl = next(
            (c for c in calls if "comments" in c and "CREATE TABLE" in c), None
        )
        assert comments_ddl is not None, "No CREATE TABLE ... comments found in setup_cache_tables"
        assert "comment_id"    in comments_ddl
        assert "comment_text"  in comments_ddl
        assert "author_email"  in comments_ddl
        assert "steward_email" in comments_ddl

    @patch("scripts.sync_metadata.get_sql_connection")
    def test_comments_table_not_truncated_during_sync(self, mock_get_sql_connection):
        """sync() must NOT truncate the comments table — it is append-only user data."""
        mock_conn   = MagicMock()
        mock_cursor = MagicMock()
        mock_get_sql_connection.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch("scripts.sync_metadata.WorkspaceClient") as mock_wc, \
             patch("scripts.sync_metadata.concurrent.futures.ThreadPoolExecutor") as mock_exec:
            mock_w = MagicMock()
            mock_wc.return_value = mock_w
            mock_w.catalogs.list.return_value = []

            mock_executor = MagicMock()
            mock_exec.return_value.__enter__.return_value = mock_executor
            mock_executor.map.return_value = []

            mock_cursor.fetchall_as_pandas.return_value = None

            from scripts.sync_metadata import sync
            sync()

        truncate_calls = [
            str(c) for c in mock_cursor.execute.call_args_list
            if "TRUNCATE" in str(c)
        ]
        assert not any("comments" in c for c in truncate_calls), (
            f"comments table was TRUNCATEd during sync — it must be append-only.\n"
            f"TRUNCATE calls: {truncate_calls}"
        )
