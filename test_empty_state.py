import pytest
from streamlit.testing.v1 import AppTest
import os

def test_admin_empty_state():
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DEMO_DATA"] = "true"
    os.environ["ENABLE_MOCK_AUTH"] = "true"
    os.environ["ADMIN_GROUPS"] = "mock_group"

    at = AppTest.from_file("app.py")
    at.session_state["user"] = {"name": "Test Admin", "groups": ["mock_group"]}
    at.run()

    at.button[0].click().run()

    at.query_params["tab"] = "admin"
    at.run()

    # The issue might be that the empty state is in the admin insights or audit tabs,
    # or that the empty state is rendered correctly for some, but not all lists in admin ops tab.

    print("Has segmented control?", len(at.segmented_control))

    # We want to find cases where empty states are rendered with custom markdown instead of _render_empty_state

    import re
    from src.ui.cards.admin import _render_empty_state

    # Let's inspect src/ui/cards/admin.py
