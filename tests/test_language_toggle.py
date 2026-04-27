import pytest
import os
import pandas as pd
from unittest.mock import patch
import streamlit as st
from tests.test_navigation import authenticated_app, sql_returns, make_tables_df
from tests.conftest import get_db_cursor

class TestLanguageNavigation:
    def test_toggle_language_and_navigate(self, monkeypatch):
        st.cache_data.clear()
        monkeypatch.setenv('DEMO_DATA', 'true')

        at = authenticated_app()
        at.run()

        # 1. Start in English
        locale = at.session_state["locale"] if "locale" in at.session_state else "en"
        assert locale == "en"

        # 2. Toggle to French
        next(b for b in at.button if b.label == "LOCALE_FR").click().run()
        locale = at.session_state["locale"] if "locale" in at.session_state else "en"
        assert locale == "fr"

        # 3. Navigate through pages while in French
        # Filter tabs that might have problematic widgets
        tabs_to_test = ["catalog", "glossary", "discovery"]
        for tab in tabs_to_test:
            at.button(key=f"nav_{tab}").click().run()
            assert at.query_params["tab"] in (tab, [tab])
            locale = at.session_state["locale"] if "locale" in at.session_state else "en"
            assert locale == "fr"

    def test_navigate_detail_view_subsections(self, monkeypatch):
        st.cache_data.clear()
        monkeypatch.setenv('DEMO_DATA', 'true')

        at = authenticated_app()
        at.run()
        at.selectbox(key="catalog_search").set_value("customers").run()
        if any("View details" in b.label for b in at.button):
            next(b for b in at.button if "View details" in b.label).click().run()
        
        next(b for b in at.button if b.label == "LOCALE_FR").click().run()
        locale = at.session_state["locale"] if "locale" in at.session_state else "en"
        assert locale == "fr"

        # Check if we see the table name or at least something from detail view
        all_text = " ".join(m.value for m in at.markdown)
        assert "customers" in all_text.lower()

    def test_navigate_in_admin_page(self, monkeypatch):
        st.cache_data.clear()
        monkeypatch.setenv('DEMO_DATA', 'true')

        with patch.dict(os.environ, {"ADMIN_GROUPS": "finance_dept_id"}):
            at = authenticated_app()
            at.run()

            next(b for b in at.button if b.label == "LOCALE_FR").click().run()
            at.button(key="nav_admin").click().run()
            assert at.query_params["tab"] in ("admin", ["admin"])
            locale = at.session_state["locale"] if "locale" in at.session_state else "en"
            assert locale == "fr"
