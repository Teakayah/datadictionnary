
import os
import sys
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from unittest.mock import patch, MagicMock

# --- BOOTSTRAP MOCKING ---
# We must mock st.session_state before 'app' is ever imported
# because app.py has top-level session_state accesses.
mock_session_state = MagicMock()
mock_session_state.user_groups = []
mock_session_state.get.side_effect = lambda k, default=None: getattr(mock_session_state, k, default)

with patch("streamlit.session_state", mock_session_state):
    # Now we can safely import or patch things in app
    import app

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")

@pytest.mark.security
def test_glossary_search_bypass(monkeypatch):
    """
    CONFIRMATION TEST: Verify that a user can see details of a restricted table
    if a Glossary term points to it, bypassing the search permission filter.
    """
    # 1. Setup environment
    monkeypatch.setenv("ENABLE_MOCK_AUTH", "true")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DEMO_DATA", "false")
    
    at = AppTest.from_file(APP_PATH)
    
    # Initialize session state in the AppTest environment
    at.session_state["authenticated"] = True
    at.session_state["user_groups"] = ["standard_user_group"]
    at.session_state["user_name"] = "Standard User"
    at.session_state["user_email"] = "standard@example.com"
    at.session_state["_prefs_loaded"] = True
    at.session_state["bookmarks"] = set()
    at.session_state["col_bookmarks"] = set()
    at.session_state["recent_views"] = []

    # 2. Mock _DEMO_GLOSSARY to include a term pointing to a secret table
    secret_table = "secret_catalog.secret_schema.secret_table"
    mock_glossary = pd.DataFrame({
        "term": ["Secret Table Term"],
        "definition": ["This term points to a secret table."],
        "calculation": ["None"],
        "domain": ["Security"],
        "steward": ["admin"],
        "related_tables": [[secret_table]]
    })
    
    # 3. Mock run_query to simulate restricted access
    def mock_run_query(query, params=None):
        query_str = str(query).lower()
        # search_all_metadata queries tables_metadata JOIN permissions_cache
        if "permissions_cache" in query_str and "tables_metadata" in query_str:
            return pd.DataFrame(columns=["full_name", "table_name", "catalog_name", "schema_name", "comment", "table_type", "updated_at", "dq_score"])
        
        # Detail view queries columns_metadata (NOT permission filtered)
        if "columns_metadata" in query_str:
            return pd.DataFrame({
                "column_name": ["secret_col"],
                "data_type": ["STRING"],
                "comment": ["This column should be hidden!"]
            })
            
        return pd.DataFrame()

    # Use monkeypatch to override the globals in the already-imported app module
    monkeypatch.setattr("app._DEMO_GLOSSARY", mock_glossary)
    monkeypatch.setattr("app.run_query", mock_run_query)
    
    # Start the app on the search tab
    at.query_params["tab"] = "search"
    at.run()
    
    # 4. Search for the glossary term
    if not at.selectbox(key="catalog_search"):
         # Try finding by index if key fails
         at.selectbox[0].select("Secret Table Term").run()
    else:
         at.selectbox(key="catalog_search").select("Secret Table Term").run()
    
    # 5. Check if the Glossary match card is shown
    html = " ".join(m.value for m in at.markdown)
    assert "Secret Table Term" in html, "Glossary term match not found in search results"
    
    # 6. Find and click "View details" button
    view_details_btn = None
    for btn in at.button:
        if "View details" in btn.label:
            view_details_btn = btn
            break
    
    assert view_details_btn is not None, "View details button not found for Glossary match"
    
    # Click the button and rerun
    view_details_btn.click().run()
    
    # 7. VERIFY BYPASS: Check if table details are shown
    html_after = " ".join(m.value for m in at.markdown)
    
    # If the bypass works, we will see the secret column name
    # and the secret table name header
    assert "secret_col" in html_after, "SECURITY BYPASS FAILED: Table details not shown"
    assert "This column should be hidden!" in html_after, "SECURITY BYPASS FAILED: Secret comment not shown"
    print("\n✅ SECURITY BYPASS CONFIRMED")

if __name__ == "__main__":
    pytest.main([__file__])
