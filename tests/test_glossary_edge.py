from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import pandas as pd

@patch("src.pages.glossary._cached_get_authorized_table_names", return_value={"catalog.schema.visible"})
def test_glossary_unauthorized_table(mock_auth):
    mock_demo = pd.DataFrame([
        {
            "term": "Test Term",
            "definition": "Definition",
            "business_owner": "owner",
            "technical_steward": "steward",
            "tags": "tag1,tag2",
            "related_tables": ["catalog.schema.visible", "catalog.schema.hidden"],
            "calculation": "calc"
        }
    ])
    with patch("src.pages.glossary._DEMO_GLOSSARY", mock_demo):
        def app():
            import src.pages.glossary as glossary
            glossary.render_glossary(["group1"])

        at = AppTest.from_function(app).run()
        at.selectbox(key="glossary_search").set_value("Test Term").run()

        # "catalog.schema.visible" should be rendered
        buttons = [b for b in at.button if b.label == "→ visible"]
        assert len(buttons) == 1

        # "catalog.schema.hidden" should NOT be rendered
        hidden_buttons = [b for b in at.button if b.label == "→ hidden"]
        assert len(hidden_buttons) == 0

@patch("src.pages.glossary._cached_get_authorized_table_names", return_value={"catalog.schema.visible"})
@patch("src.pages.glossary._pref_upsert")
@patch("src.pages.glossary._pref_delete")
def test_glossary_bookmarks(mock_del, mock_upsert, mock_auth):
    mock_demo = pd.DataFrame([
        {
            "term": "Test Term",
            "definition": "Definition",
            "business_owner": "owner",
            "technical_steward": "steward",
            "tags": "tag1,tag2",
            "related_tables": ["catalog.schema.visible"],
            "calculation": "calc"
        }
    ])
    with patch("src.pages.glossary._DEMO_GLOSSARY", mock_demo):
        def app():
            import streamlit as st
            if "bookmarks" not in st.session_state:
                st.session_state.bookmarks = set()
            import src.pages.glossary as glossary
            glossary.render_glossary(["group1"])

        at = AppTest.from_function(app).run()
        at.selectbox(key="glossary_search").set_value("Test Term").run()

        # Click to add bookmark (label "☆")
        star_btns = [b for b in at.button if b.label == "☆"]
        assert len(star_btns) == 1
        star_btns[0].click().run()

        mock_upsert.assert_called_once_with("catalog.schema.visible", "bookmark")

        # Click to remove bookmark (label "★")
        star_btns = [b for b in at.button if b.label == "★"]
        assert len(star_btns) == 1
        star_btns[0].click().run()

        mock_del.assert_called_once_with("catalog.schema.visible", "bookmark")
