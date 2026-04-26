"""
Tests to verify that elements meant to be viewable by end users are actually visible.
"""

from __future__ import annotations

import os
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from tests.conftest import sql_returns

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")

def _signed_in_app() -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=15)
    at.session_state["authenticated"] = True
    at.session_state["user_groups"] = ["finance_dept_id"]
    at.session_state["user_name"] = "Test User"
    at.session_state["user_email"] = "test@example.com"
    return at

class TestVisibility:
    def test_search_tab_elements_visible(self):
        """Test that key elements on the Search tab are visible."""
        at = _signed_in_app()
        at.query_params["tab"] = "search"
        at.run()
        assert not at.exception, f"Exception: {at.exception}"

        # Check that we have the search selectbox or input
        assert len(at.selectbox) > 0 or len(at.text_input) > 0, "No search input found"

        # Check that markdown elements are rendered
        assert len(at.markdown) > 0, "No markdown rendered"

    def test_discovery_tab_elements_visible(self):
        """Test that key elements on the Discovery tab are visible."""
        at = _signed_in_app()
        at.query_params["tab"] = "discovery"
        at.run()
        assert not at.exception, f"Exception: {at.exception}"

        assert len(at.markdown) > 0, "No markdown rendered on Discovery tab"
        assert any("Discovery" in m.value or "coverage" in m.value.lower() for m in at.markdown), "Expected text not visible on Discovery tab"

    def test_health_tab_elements_visible(self):
        """Test that key elements on the Health tab are visible."""
        at = _signed_in_app()
        at.query_params["tab"] = "health"
        at.run()
        assert not at.exception, f"Exception: {at.exception}"

        assert len(at.markdown) > 0, "No markdown rendered on Health tab"

    def test_glossary_tab_elements_visible(self):
        """Test that key elements on the Glossary tab are visible."""
        at = _signed_in_app()
        at.query_params["tab"] = "glossary"
        at.run()
        assert not at.exception, f"Exception: {at.exception}"

        assert len(at.markdown) > 0, "No markdown rendered on Glossary tab"

    def test_header_navigation_visible(self):
        """Test that navigation tabs/links are visible in the header."""
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"

        # The app renders header nav via markdown. We want to ensure 'Search', 'Discovery', etc are there.
        markdown_text = " ".join([m.value for m in at.markdown])
        assert "Search" in markdown_text or "Recherche" in markdown_text, "Search nav link not visible"
        assert "Discovery" in markdown_text or "Découverte" in markdown_text, "Discovery nav link not visible"
