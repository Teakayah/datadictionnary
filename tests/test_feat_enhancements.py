"""
Tests for recent feature enhancements and bug fixes.
- Navigation state guard (sticky nav persistence)
- Admin Quality Insights tab rendering
- Health tab SQL push-down logic
"""

from __future__ import annotations

import os
import pandas as pd
from streamlit.testing.v1 import AppTest
from tests.conftest import sql_returns, get_db_cursor

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")
ADMIN_GROUP = "admin_group_id"

def authenticated_app(tab: str | None = None) -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=15)
    at.session_state["authenticated"] = True
    at.session_state["user_groups"] = [ADMIN_GROUP]
    at.session_state["user_name"] = "Admin User"
    at.session_state["user_email"] = "admin@example.com"
    at.session_state["_prefs_loaded"] = True
    if tab:
        at.query_params["tab"] = tab
    return at

# ═══════════════════════════════════════════════════════════════════════════════
# 1. Navigation Fix Verification
# ═══════════════════════════════════════════════════════════════════════════════

def test_sticky_nav_persistence_on_override(monkeypatch):
    """Verify that dd_search_override updates current_search_query to prevent wiping sticky nav."""
    monkeypatch.setenv("DEMO_DATA", "false")
    at = authenticated_app(tab="search")
    
    # Simulate a transition from glossary/discovery
    at.session_state["dd_search_override"] = "orders"
    at.session_state["dd_nav_select"] = "main.sales.orders"
    
    # Mock data for authorized tables list (needed by search)
    sql_returns(pd.DataFrame({
        "full_name": ["main.sales.orders"],
        "table_name": ["orders"],
        "table_description": ["Sales orders"]
    }))
    
    at.run()
    
    # Verify sticky nav is set and not cleared
    assert at.session_state["_dd_sticky_nav"] == "main.sales.orders"
    assert at.session_state["_dd_current_search_query"] == "orders"

# ═══════════════════════════════════════════════════════════════════════════════
# 2. Admin Quality Insights Tab
# ═══════════════════════════════════════════════════════════════════════════════

def test_admin_quality_insights_tab_renders(monkeypatch):
    """Verify that the new Quality Insights tab is present and renders its sections."""
    monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
    at = authenticated_app(tab="admin")
    
    # Mock data for stats, audit logs, and the new reports
    sql_returns(
        pd.DataFrame({"tables": [10], "columns": [100], "comments": [5], "overrides": [2]}), # stats
        pd.DataFrame(), # pending reviews
        pd.DataFrame(), # high impact gaps
        pd.DataFrame(), # dq alerts
        pd.DataFrame(), # stewardship gaps
        pd.DataFrame(), # change log
        pd.DataFrame(), # comment log
    )
    
    # Switch to Insights tab
    from src.i18n import t
    at.session_state["admin_active_tab"] = t("admin.tab_insights")
    at.run()
    
    # Render sections inside the insights tab
    html = " ".join(m.value for m in at.markdown)
    assert t("admin.integrity_title") in html

# ═══════════════════════════════════════════════════════════════════════════════
# 3. Health Tab SQL Push-down
# ═══════════════════════════════════════════════════════════════════════════════

def test_health_sql_push_down_queries(monkeypatch):
    """Verify that Health tab metrics use SQL push-down with permission JOINs."""
    monkeypatch.setenv("DEMO_DATA", "false")
    at = authenticated_app(tab="health")
    
    cursor = get_db_cursor()
    cursor.reset_mock()
    
    # Mock returns for the three push-down queries
    sql_returns(
        pd.DataFrame({"schema_name": ["sales"], "total": [10], "described": [8]}), # table stats
        pd.DataFrame({"total": [100], "with_desc": [70]}), # col stats
        pd.DataFrame(), # undocumented priority
    )
    
    at.run()
    
    executed_queries = [call[0][0] for call in cursor.execute.call_args_list]
    
    # Verify permission JOINs are present in the queries
    assert any("JOIN" in q and "permissions_cache" in q for q in executed_queries)
    assert any("GROUP BY m.schema_name" in q for q in executed_queries)
    assert any("SUM(CASE WHEN c.comment" in q for q in executed_queries)
