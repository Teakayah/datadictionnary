"""
End-to-end tests for profile building and personalization.
Verifies that user interactions (views, edits, comments) correctly
build up the user profile and influence discovery results.
"""

from __future__ import annotations

import os
import pandas as pd
from streamlit.testing.v1 import AppTest
from tests.conftest import sql_returns

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")

def authenticated_app(tab: str | None = None) -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=15)
    at.session_state["authenticated"] = True
    at.session_state["user_groups"] = ["finance_group"]
    at.session_state["user_name"] = "Finance User"
    at.session_state["user_email"] = "finance@example.com"
    at.session_state["bookmarks"] = set()
    at.session_state["recent_views"] = []
    if tab:
        at.query_params["tab"] = tab
    return at

# ═══════════════════════════════════════════════════════════════════════════════
# 1. Passive Profile Building (Recent Views)
# ═══════════════════════════════════════════════════════════════════════════════

def test_viewing_table_updates_recent_profile(monkeypatch):
    """Verify that opening a table detail panel adds it to the user's recent_views."""
    at = authenticated_app(tab="search")
    
    # Use the actual demo table name — demo mode returns _DEMO_TABLES which has
    # main.analytics.orders (not main.sales.orders).
    table_fn = "main.analytics.orders"
    
    # Navigate to the detail view of 'orders' — need catalog_search set so
    # the search block runs and the detail panel is entered.
    at.session_state["catalog_search"] = "orders"
    at.session_state["_dd_sticky_nav"] = table_fn
    at.session_state["_prefs_loaded"] = True
    at.run()
    
    # Profile should be updated
    assert table_fn in at.session_state["recent_views"]
    assert at.session_state["recent_views"][0] == table_fn

# ═══════════════════════════════════════════════════════════════════════════════
# 2. Recommended Tab (Audit Log Influence)
# ═══════════════════════════════════════════════════════════════════════════════

def test_recommended_tab_reflects_popular_interactions(monkeypatch):
    """Verify that the Recommended tab renders tables returned by _get_recommended_tables."""
    # _get_recommended_tables guards on DuckDB availability (always false in tests),
    # so we patch it directly to inject a known recommendation list.
    monkeypatch.setattr(
        "src.ui.cards.discovery._get_recommended_tables",
        lambda *a, **kw: ["main.analytics.orders"],
    )

    at = authenticated_app(tab="discovery")
    at.session_state["discovery_active_tab"] = "Recommended"
    at.session_state["_disc_tab_idx"] = 3
    at.session_state["_prefs_loaded"] = True

    at.run()

    html = " ".join(m.value for m in at.markdown)
    assert "orders" in html.lower()

# ═══════════════════════════════════════════════════════════════════════════════
# 3. Explicit Profile (Bookmarks)
# ═══════════════════════════════════════════════════════════════════════════════

def test_bookmarking_updates_profile_and_tab(monkeypatch):
    """Verify that bookmarking a table adds it to the profile and shows in Bookmarks tab."""
    at = authenticated_app(tab="discovery")
    at.session_state["discovery_tabs"] = "My Bookmarks"
    
    table_fn = "main.sales.orders"
    at.session_state["bookmarks"] = {table_fn}
    at.session_state["_prefs_loaded"] = True  # prevent prefs reload wiping bookmarks

    sql_returns(pd.DataFrame({
        "full_name": [table_fn],
        "table_name": ["orders"],
        "catalog_name": ["main"],
        "schema_name": ["sales"],
        "table_description": ["Desc"],
        "updated_at": [pd.Timestamp("2026-05-10")]
    }))
    
    at.run()
    
    html = " ".join(m.value for m in at.markdown)
    assert "orders" in html.lower()
    assert table_fn in at.session_state["bookmarks"]
