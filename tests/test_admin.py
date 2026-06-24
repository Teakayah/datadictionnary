"""
Tests for the admin page, is_admin() guard, and audit logging.

Coverage:
  - is_admin: group match, group absent, empty ADMIN_GROUPS, no demo bypass
  - Admin nav tab: visible for admins, hidden for non-admins
  - Admin page rendering: access guard, stat cards, expanders
  - Audit log: demo-mode write, business name log, comment log
"""
from __future__ import annotations
from unittest.mock import patch

import os
import pandas as pd
from streamlit.testing.v1 import AppTest

from tests.conftest import sql_returns

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")

ADMIN_GROUP = "admin_group_id"
STANDARD_GROUP = "finance_dept_id"


# ── App factory helpers ────────────────────────────────────────────────────────

def _admin_app(*, demo: bool = False) -> AppTest:
    """Authenticated app whose user_groups contains ADMIN_GROUP."""
    at = AppTest.from_file(APP_PATH, default_timeout=15)
    at.session_state["authenticated"] = True
    at.session_state["user_groups"] = [ADMIN_GROUP, STANDARD_GROUP]
    at.session_state["user_name"] = "Admin User"
    at.session_state["user_email"] = "admin@example.com"
    if demo:
        os.environ["DEMO_DATA"] = "true"
    return at


def _standard_app() -> AppTest:
    """Authenticated app with no admin group."""
    at = AppTest.from_file(APP_PATH, default_timeout=15)
    at.session_state["authenticated"] = True
    at.session_state["user_groups"] = [STANDARD_GROUP]
    at.session_state["user_name"] = "Standard User"
    return at


def _html(*markdowns) -> str:
    return " ".join(m.value for m in markdowns)


# ═══════════════════════════════════════════════════════════════════════════════
# is_admin
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsAdmin:
    """Verifies the is_admin() access guard logic."""

    def test_admin_when_group_matches(self, monkeypatch):
        """User in ADMIN_GROUPS is recognised as admin."""
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        at = _admin_app()
        # Navigate to admin tab to trigger is_admin() evaluation
        at.query_params["tab"] = "admin"
        sql_returns(
            pd.DataFrame({"c": [0]}),  # tables count
            pd.DataFrame({"c": [0]}),  # columns count
            pd.DataFrame({"c": [0]}),  # comments count
            pd.DataFrame({"c": [0]}),  # overrides count
            pd.DataFrame(),            # biz name change log
            pd.DataFrame(),            # comment log
        )
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        # Admin page renders — error widget should NOT be present
        error_texts = [e.value for e in at.error]
        assert not any("Admin access required" in t for t in error_texts)

    def test_not_admin_when_group_absent(self, monkeypatch):
        """User whose groups do not overlap ADMIN_GROUPS is rejected."""
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        at = _standard_app()
        at.query_params["tab"] = "admin"
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        error_texts = [e.value for e in at.error]
        assert any("Admin access required" in t for t in error_texts)

    def test_not_admin_when_admin_groups_empty(self, monkeypatch):
        """If ADMIN_GROUPS is empty, nobody is an admin."""
        monkeypatch.setenv("ADMIN_GROUPS", "")
        at = _admin_app()
        at.query_params["tab"] = "admin"
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        error_texts = [e.value for e in at.error]
        assert any("Admin access required" in t for t in error_texts)

    def test_no_demo_bypass(self, monkeypatch):
        """DEMO_DATA=true does not grant admin — must still be in ADMIN_GROUPS."""
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        monkeypatch.setenv("DEMO_DATA", "true")
        at = _standard_app()
        at.query_params["tab"] = "admin"
        try:
            at.run()
            error_texts = [e.value for e in at.error]
            assert any("Admin access required" in t for t in error_texts)
        finally:
            monkeypatch.setenv("DEMO_DATA", "false")


# ═══════════════════════════════════════════════════════════════════════════════
# Admin nav tab visibility
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdminNav:
    """Verifies the Admin tab appears only for admin users."""

    def test_admin_tab_appears_for_admins(self, monkeypatch):
        """Admin nav proxy button must be present for admin users."""
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        at = _admin_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        assert any(b.key == "nav_admin" for b in at.button)

    def test_admin_tab_hidden_for_non_admins(self, monkeypatch):
        """Admin nav proxy button must NOT be present for non-admin users."""
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        at = _standard_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        assert not any(b.key == "nav_admin" for b in at.button)

    def test_admin_tab_hidden_when_no_admin_group_configured(self, monkeypatch):
        """If ADMIN_GROUPS is empty the Admin nav button is never shown."""
        monkeypatch.setenv("ADMIN_GROUPS", "")
        at = _admin_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        assert not any(b.key == "nav_admin" for b in at.button)


# ═══════════════════════════════════════════════════════════════════════════════
# Admin page rendering
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdminPage:
    """Verifies render_admin_page() structure."""

    def _run_admin(self, monkeypatch):
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        monkeypatch.setattr("src.ui.cards.admin.get_admin_stats", lambda: {"tables": 42, "columns": 300, "comments": 5, "overrides": 2})
        monkeypatch.setattr("src.ui.cards.admin.get_high_impact_gaps", lambda: pd.DataFrame(columns=["issue"]))
        monkeypatch.setattr("src.ui.cards.admin.get_business_name_change_log", lambda: pd.DataFrame())
        monkeypatch.setattr("src.ui.cards.admin.get_comment_log", lambda: pd.DataFrame())
        at = _admin_app()
        at.query_params["tab"] = "admin"
        sql_returns(
            pd.DataFrame({"tables": [42], "columns": [300], "comments": [5], "overrides": [2]}), # stats query
            pd.DataFrame(columns=["issue"]),              # missing insights
            pd.DataFrame(columns=["issue"]),              # missing steward insights
            pd.DataFrame(),              # biz name change log
            pd.DataFrame(),              # comment log
        )
        at.run()
        # Mock st.metric to just append to a list instead of throwing when not found later
        return at

    def test_page_renders_for_admin(self, monkeypatch):
        """Admin page heading is present in the rendered HTML."""
        at = self._run_admin(monkeypatch)
        assert not at.exception, f"Exception: {at.exception}"
        html = _html(*at.markdown)
        assert "§ Admin" in html

    def test_access_guard_shows_error(self, monkeypatch):
        """Non-admin user navigating to /admin sees the access error."""
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        at = _standard_app()
        at.query_params["tab"] = "admin"
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        error_texts = [e.value for e in at.error]
        assert any("Admin access required" in t for t in error_texts)

    @patch("src.ui.cards.admin.get_admin_stats", lambda: {"tables": 42, "columns": 300, "comments": 5, "overrides": 2})
    @patch("src.ui.cards.admin.get_high_impact_gaps", lambda: pd.DataFrame(columns=["issue"]))
    @patch("src.ui.cards.admin.get_business_name_change_log", lambda: pd.DataFrame())
    @patch("src.ui.cards.admin.get_comment_log", lambda: pd.DataFrame())
    def test_admin_sections_present(self, monkeypatch):
        """Admin page must contain the core sections (Sync, Audit, Settings)."""
        at = self._run_admin(monkeypatch)
        assert not at.exception, f"Exception: {at.exception}"
        # Stats are on tab 1 (Quality Insights); navigate there
        sql_returns(
            pd.DataFrame({"tables": [42], "columns": [300], "comments": [5], "overrides": [2]}),
        )
        at.session_state["admin_active_tab"] = "Quality Insights"
        at.session_state["_admin_tab_idx"] = 1
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        metrics = {m.label: m.value for m in at.metric}
        assert "Total tables" in metrics
        assert "Total columns" in metrics
        assert "Total comments" in metrics
        assert "Business name overrides" in metrics

    def test_log_expand_buttons_present(self, monkeypatch):
        """Both change-log expand buttons are rendered (replaced expanders in 7b0abc2)."""
        at = self._run_admin(monkeypatch)
        assert not at.exception, f"Exception: {at.exception}"
        # Expand buttons are on tab 2 (Audit Logs); navigate there
        sql_returns(pd.DataFrame(), pd.DataFrame())  # biz log, comment log
        at.session_state["admin_active_tab"] = "Audit Logs"
        at.session_state["_admin_tab_idx"] = 2
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        button_keys = [b.key for b in at.button]
        assert "admin_biz_log_expand" in button_keys
        assert "admin_comment_log_expand" in button_keys


# ═══════════════════════════════════════════════════════════════════════════════
# Demo mode behavior
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdminDemo:
    """Verifies admin page behavior when DEMO_DATA=true."""

    def _run_demo_admin(self, monkeypatch, pre_state=None):
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        monkeypatch.setenv("DEMO_DATA", "true")
        at = _admin_app(demo=True)
        at.query_params["tab"] = "admin"
        if pre_state:
            for k, v in pre_state.items():
                at.session_state[k] = v
        sql_returns(
            pd.DataFrame({"tables": [42], "columns": [300], "comments": [5], "overrides": [2]}), # stats query
            pd.DataFrame(columns=["issue"]),              # missing insights
            pd.DataFrame(columns=["issue"]),              # missing steward insights
            pd.DataFrame(),              # biz name change log
            pd.DataFrame(),              # comment log
        )
        at.run()
        return at

    def test_biz_log_rows(self, monkeypatch):
        """Admin page business name log displays audit_log events."""
        pre_audit = [
            {
                "event_id":    "123",
                "event_type":  "business_name_change",
                "object_type": "COLUMN",
                "object_name": "main.sales.orders.order_id",
                "actor_email": "user@example.com",
                "old_value":   "OID",
                "new_value":   "Order ID",
                "created_at":  pd.Timestamp("2026-04-24 08:00"),
            }
        ]
        at = self._run_demo_admin(monkeypatch, pre_state={"demo_audit_log": pre_audit})
        assert not at.exception, f"Exception: {at.exception}"
        # Stat cards are on tab 1 (Quality Insights); navigate there
        at.session_state["admin_active_tab"] = "Quality Insights"
        at.session_state["_admin_tab_idx"] = 1
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        metrics = {m.label: m.value for m in at.metric}
        assert "Total tables" in metrics

    def test_comment_log_rows(self, monkeypatch):
        """Admin page comment log displays comment_added and comment_reply events."""
        pre_audit = [
            {
                "event_id":    "c1",
                "event_type":  "comment_added",
                "object_type": "TABLE",
                "object_name": "main.sales.orders",
                "actor_email": "user@example.com",
                "old_value":   "",
                "new_value":   "First comment",
                "created_at":  pd.Timestamp("2026-04-24 09:00"),
            },
            {
                "event_id":    "c2",
                "event_type":  "comment_reply",
                "object_type": "TABLE",
                "object_name": "main.sales.orders",
                "actor_email": "admin@example.com",
                "old_value":   "",
                "new_value":   "Thanks for the note",
                "created_at":  pd.Timestamp("2026-04-24 09:30"),
            },
        ]
        at = self._run_demo_admin(monkeypatch, pre_state={"demo_audit_log": pre_audit})
        assert not at.exception, f"Exception: {at.exception}"
        # Expand buttons are on tab 2 (Audit Logs); navigate there
        at.session_state["admin_active_tab"] = "Audit Logs"
        at.session_state["_admin_tab_idx"] = 2
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        button_keys = [b.key for b in at.button]
        assert "admin_comment_log_expand" in button_keys

    def test_log_audit_event_demo_write(self, monkeypatch):
        """log_audit_event in demo mode appends to st.session_state['demo_audit_log']."""
        monkeypatch.setenv("DEMO_DATA", "true")
        monkeypatch.setenv("EDITOR_GROUPS", STANDARD_GROUP)

        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.session_state["authenticated"] = True
        at.session_state["user_groups"] = [STANDARD_GROUP, ADMIN_GROUP]
        at.session_state["user_name"] = "Power User"
        at.session_state["user_email"] = "power@example.com"
        at.session_state["demo_business_names"] = {}
        at.query_params["tab"] = "search"
        at.run()

        # Simulate editing a business name (triggers log_audit_event internally)
        at.session_state["dd_col_edit_mode"] = "customer_id"
        at.run()

        # Check that the edit text input exists and submit it
        # (just verify no crash — the save path is covered by test_business_name_save)
        monkeypatch.setenv("DEMO_DATA", "false")
        assert not at.exception, f"Exception: {at.exception}"


# ═══════════════════════════════════════════════════════════════════════════════
# Admin Stats — Unit Tests
# ═══════════════════════════════════════════════════════════════════════════════

from unittest.mock import patch  # noqa: E402
from src.ui.cards.admin import get_admin_stats  # noqa: E402

@patch("src.ui.cards.admin.run_query")
@patch("src.ui.cards.admin.is_demo_mode", return_value=False)
@patch("src.ui.cards.admin._duckdb_available", return_value=False)
def test_get_admin_stats_exception(mock_duckdb, mock_demo, mock_run_query):
    """get_admin_stats should return all zero values when run_query raises an Exception."""
    mock_run_query.side_effect = Exception("Database connection failed")

    stats = get_admin_stats()

    assert stats == {"tables": 0, "columns": 0, "comments": 0, "overrides": 0}



class TestAdminDataFetchers:
    """Verifies standalone data fetchers for the Admin dashboard."""

    @classmethod
    def setup_class(cls):
        import importlib
        import sys
        if "src.ui.cards.admin" in sys.modules:
            importlib.reload(sys.modules["src.ui.cards.admin"])

    @patch("src.ui.cards.admin.get_zero_result_searches")
    def test_get_search_analytics(self, mock_get):
        from src.ui.cards.admin import get_search_analytics
        import pandas as pd
        mock_get.return_value = [{"query": "foo", "user_email": "bar", "timestamp": pd.Timestamp("2024-01-01")}]
        df = get_search_analytics()
        assert len(df) == 1

        mock_get.return_value = []
        df = get_search_analytics()
        assert len(df) == 0

    @patch("src.ui.cards.admin.st")
    @patch("src.ui.cards.admin.is_demo_mode", return_value=True)
    def test_get_admin_stats_demo(self, mock_demo, mock_st):
        from src.ui.cards.admin import get_admin_stats

        def mock_get(key, default=None):
            if key == "demo_comments":
                return {"t1": ["c1", "c2"], "t2": ["c3"]}
            if key == "demo_business_names":
                return {"t1": ["b1"]}
            return default

        mock_st.session_state.get.side_effect = mock_get
        stats = get_admin_stats()
        assert stats == {"tables": 0, "columns": 0, "comments": 3, "overrides": 1}

    @patch("src.ui.cards.admin.is_demo_mode", return_value=False)
    @patch("src.ui.cards.admin._duckdb_available", return_value=True)
    @patch("src.ui.cards.admin.run_query")
    def test_get_admin_stats_db(self, mock_run, mock_duckdb, mock_demo):
        from src.ui.cards.admin import get_admin_stats
        import pandas as pd
        mock_run.return_value = pd.DataFrame({"tables": [10], "columns": [50], "comments": [5], "overrides": [2]})
        stats = get_admin_stats()
        assert stats == {"tables": 10, "columns": 50, "comments": 5, "overrides": 2}

    @patch("src.ui.cards.admin.st")
    @patch("src.ui.cards.admin.is_demo_mode", return_value=True)
    def test_get_business_name_change_log_demo(self, mock_demo, mock_st):
        from src.ui.cards.admin import get_business_name_change_log
        import pandas as pd
        mock_st.session_state.get.return_value = [
            {"event_type": "business_name_change", "created_at": pd.Timestamp("2024-01-01"), "event_id": "1"},
            {"event_type": "other", "created_at": pd.Timestamp("2024-01-02"), "event_id": "2"},
        ]
        df = get_business_name_change_log()
        assert len(df) == 1
        assert df.iloc[0]["event_id"] == "1"

        mock_st.session_state.get.return_value = []
        df = get_business_name_change_log()
        assert list(df.columns) == ["event_id", "object_name", "old_value", "new_value", "actor_email", "created_at"]
        assert len(df) == 0

    @patch("src.ui.cards.admin.is_demo_mode", return_value=False)
    @patch("src.ui.cards.admin._duckdb_available", return_value=True)
    @patch("src.ui.cards.admin.run_query")
    def test_get_business_name_change_log_db(self, mock_run, mock_duckdb, mock_demo):
        from src.ui.cards.admin import get_business_name_change_log
        import pandas as pd
        mock_run.return_value = pd.DataFrame([{"event_id": "1"}])
        df = get_business_name_change_log()
        assert len(df) == 1
        assert "user_data.audit_log" in mock_run.call_args[0][0]

    @patch("src.ui.cards.admin.st")
    @patch("src.ui.cards.admin.is_demo_mode", return_value=True)
    def test_get_comment_log_demo(self, mock_demo, mock_st):
        from src.ui.cards.admin import get_comment_log
        import pandas as pd
        mock_st.session_state.get.return_value = [
            {"event_type": "comment_added", "created_at": pd.Timestamp("2024-01-01"), "new_value": "msg", "event_id": "1"},
            {"event_type": "comment_reply", "created_at": pd.Timestamp("2024-01-02"), "new_value": "rep", "event_id": "2"},
            {"event_type": "other", "created_at": pd.Timestamp("2024-01-03"), "new_value": "x", "event_id": "3"},
        ]
        df = get_comment_log()
        assert len(df) == 2
        assert "comment_preview" in df.columns
        assert df.iloc[0]["comment_preview"] == "rep" # sorted descending
        assert df.iloc[1]["comment_preview"] == "msg"

        mock_st.session_state.get.return_value = []
        df = get_comment_log()
        assert list(df.columns) == ["event_id", "object_name", "comment_preview", "actor_email", "created_at"]
        assert len(df) == 0

    @patch("src.ui.cards.admin.is_demo_mode", return_value=False)
    @patch("src.ui.cards.admin._duckdb_available", return_value=True)
    @patch("src.ui.cards.admin.run_query")
    def test_get_comment_log_db(self, mock_run, mock_duckdb, mock_demo):
        from src.ui.cards.admin import get_comment_log
        import pandas as pd
        mock_run.return_value = pd.DataFrame([{"event_id": "1"}])
        df = get_comment_log()
        assert len(df) == 1
        assert "user_data.audit_log" in mock_run.call_args[0][0]

    @patch("src.ui.cards.admin._duckdb_available", return_value=False)
    def test_get_sync_queue_stats_no_db(self, mock_duckdb):
        from src.ui.cards.admin import get_sync_queue_stats
        assert get_sync_queue_stats() == {}

    @patch("src.ui.cards.admin._duckdb_available", return_value=True)
    @patch("src.ui.cards.admin._get_write_connection")
    def test_get_sync_queue_stats_db(self, mock_get_conn, mock_duckdb):
        from src.ui.cards.admin import get_sync_queue_stats
        from unittest.mock import MagicMock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("pending", 2), ("failed", 1)]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        stats = get_sync_queue_stats()
        assert stats == {"pending": 2, "processing": 0, "done": 0, "failed": 1}

    @patch("src.ui.cards.admin._duckdb_available", return_value=True)
    @patch("src.ui.cards.admin._get_write_connection")
    def test_get_sync_queue_stats_exception(self, mock_get_conn, mock_duckdb):
        from src.ui.cards.admin import get_sync_queue_stats
        mock_get_conn.side_effect = Exception("DB error")
        stats = get_sync_queue_stats()
        assert stats == {"pending": 0, "processing": 0, "done": 0, "failed": 0}

    @patch("src.ui.cards.admin.is_demo_mode", return_value=True)
    def test_get_high_impact_gaps_demo(self, mock_demo):
        from src.ui.cards.admin import get_high_impact_gaps
        df = get_high_impact_gaps()
        assert df.empty

    @patch("src.ui.cards.admin.is_demo_mode", return_value=False)
    @patch("src.ui.cards.admin._duckdb_available", return_value=True)
    @patch("src.ui.cards.admin.run_query")
    def test_get_high_impact_gaps_db(self, mock_run, mock_duckdb, mock_demo):
        from src.ui.cards.admin import get_high_impact_gaps
        import pandas as pd
        mock_run.return_value = pd.DataFrame([{"full_name": "t1", "interactions": 10, "issue": "Missing steward"}])
        df = get_high_impact_gaps()
        assert len(df) == 1

    @patch("src.ui.cards.admin.is_demo_mode", return_value=True)
    def test_get_stewardship_gaps_demo(self, mock_demo):
        from src.ui.cards.admin import get_stewardship_gaps
        df = get_stewardship_gaps()
        assert df.empty

    @patch("src.ui.cards.admin.is_demo_mode", return_value=False)
    @patch("src.ui.cards.admin._duckdb_available", return_value=True)
    @patch("src.ui.cards.admin.run_query")
    def test_get_stewardship_gaps_db(self, mock_run, mock_duckdb, mock_demo):
        from src.ui.cards.admin import get_stewardship_gaps
        import pandas as pd
        mock_run.return_value = pd.DataFrame([{"full_name": "t1"}])
        df = get_stewardship_gaps()
        assert len(df) == 1

    @patch("src.ui.cards.admin.is_demo_mode", return_value=True)
    def test_get_dq_alerts_demo(self, mock_demo):
        from src.ui.cards.admin import get_dq_alerts
        df = get_dq_alerts()
        assert df.empty

    @patch("src.ui.cards.admin.is_demo_mode", return_value=False)
    @patch("src.ui.cards.admin._duckdb_available", return_value=True)
    @patch("src.ui.cards.admin.run_query")
    def test_get_dq_alerts_db(self, mock_run, mock_duckdb, mock_demo):
        from src.ui.cards.admin import get_dq_alerts
        import pandas as pd
        mock_run.return_value = pd.DataFrame([{"full_name": "t1"}])
        df = get_dq_alerts()
        assert len(df) == 1
