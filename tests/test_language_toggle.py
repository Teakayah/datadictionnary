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
        at.button(key="lang_btn_fr").click().run()
        locale = at.session_state["locale"] if "locale" in at.session_state else "en"
        assert locale == "fr"

        # 3. Navigate through pages while in French
        tabs_to_test = ["catalog", "glossary", "discovery", "health", "search"]
        for tab in tabs_to_test:
            at.button(key=f"nav_{tab}").click().run()
            assert at.query_params["tab"] in (tab, [tab])
            locale = at.session_state["locale"] if "locale" in at.session_state else "en"
            assert locale == "fr"

        # 4. Toggle back to English
        at.button(key="lang_btn_en").click().run()
        locale = at.session_state["locale"] if "locale" in at.session_state else "en"
        assert locale == "en"

    def test_navigate_detail_view_subsections(self, monkeypatch):
        st.cache_data.clear()
        monkeypatch.setenv('DEMO_DATA', 'true')

        at = authenticated_app()
        at.query_params["tab"] = "search"
        at.session_state["dd_search_override"] = "orders"
        at.session_state["dd_nav_select"] = "main.sales.orders"
        at.run()

        at.button(key="lang_btn_fr").click().run()
        locale = at.session_state["locale"] if "locale" in at.session_state else "en"
        assert locale == "fr"

        if "rel_main.sales.customers" in [b.key for b in at.button]:
            at.button(key="rel_main.sales.customers").click().run()

        locale = at.session_state["locale"] if "locale" in at.session_state else "en"
        assert locale == "fr"

        at.button(key="lang_btn_en").click().run()
        locale = at.session_state["locale"] if "locale" in at.session_state else "en"
        assert locale == "en"

    def test_navigate_in_admin_page(self, monkeypatch):
        st.cache_data.clear()
        monkeypatch.setenv('DEMO_DATA', 'true')

        with patch.dict(os.environ, {"ADMIN_GROUPS": "admin_group_id"}):
            at = authenticated_app()
            at.session_state["user_groups"].append("admin_group_id")
            at.run()

            at.button(key="lang_btn_fr").click().run()
            locale = at.session_state["locale"] if "locale" in at.session_state else "en"
            assert locale == "fr"

            at.button(key="nav_admin").click().run()
            assert at.query_params["tab"] in ("admin", ["admin"])
            locale = at.session_state["locale"] if "locale" in at.session_state else "en"
            assert locale == "fr"

            if "admin_refresh_cache" in [b.key for b in at.button]:
                at.button(key="admin_refresh_cache").click().run()
                locale = at.session_state["locale"] if "locale" in at.session_state else "en"
                assert locale == "fr"

            at.button(key="lang_btn_en").click().run()
            locale = at.session_state["locale"] if "locale" in at.session_state else "en"
            assert locale == "en"

    def test_navigate_all_toggleable_subsections_in_detail_view(self, monkeypatch):
        st.cache_data.clear()
        monkeypatch.setenv('DEMO_DATA', 'true')

        at = authenticated_app()
        at.query_params["tab"] = "search"
        at.session_state["dd_search_override"] = "orders"
        at.session_state["dd_nav_select"] = "main.sales.orders"
        at.run()

        at.button(key="lang_btn_fr").click().run()

        buttons = [b.key for b in at.button if b.key is not None]

        comment_btns = [key for key in buttons if key.startswith("dd_comment_btn_")]
        if comment_btns:
            at.button(key=comment_btns[0]).click().run()
            locale = at.session_state["locale"] if "locale" in at.session_state else "en"
            assert locale == "fr"

        edit_btns = [key for key in buttons if key.startswith("col_edit_")]
        if edit_btns:
            at.button(key=edit_btns[0]).click().run()
            locale = at.session_state["locale"] if "locale" in at.session_state else "en"
            assert locale == "fr"

        at.button(key="lang_btn_en").click().run()
        locale = at.session_state["locale"] if "locale" in at.session_state else "en"
        assert locale == "en"
