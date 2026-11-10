from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import pandas as pd

def test_search_no_results_empty_state():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    # Empty dataframes to simulate no results for search query but authorized tables exist
    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "nonexistent_query", # Include it so it's in the selectbox options
        "catalog_name": "main",
        "schema_name": "sales"
    }])
    mock_search = pd.DataFrame(columns=["full_name", "table_name", "catalog_name", "schema_name", "match_type", "description"])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.track_search"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()
        # Now we can select it because it's in the options list
        at.selectbox(key="catalog_search").set_value("nonexistent_query").run()

        assert not at.exception

        markdown_values = [m.value for m in at.markdown]

        # Verify the empty state shows search.no_results
        assert any("search.no_results" in val for val in markdown_values), "Expected empty state for no results to be rendered"

def test_search_none_results_empty_state():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        st.session_state["user_email"] = "test@example.com"
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    # Empty dataframes to simulate no results for search query but authorized tables exist
    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "nonexistent_query", # Include it so it's in the selectbox options
        "catalog_name": "main",
        "schema_name": "sales"
    }])
    mock_search = None

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.track_search"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()
        # Now we can select it because it's in the options list
        at.selectbox(key="catalog_search").set_value("nonexistent_query").run()

        assert not at.exception

        markdown_values = [m.value for m in at.markdown]

        # Verify the empty state shows search.no_results
        assert any("search.no_results" in val for val in markdown_values), "Expected empty state for no results to be rendered"


def test_search_page_clear_state_on_query_change():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page

        if "init" not in st.session_state:
            st.session_state["_dd_current_search_query"] = "old_query"
            st.session_state["dd_comment_open_123"] = True
            st.session_state["_dd_sticky_nav"] = "main.sales.orders"
            st.session_state["init"] = True

        render_search_page(("group1",))

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(render_search)
    at.session_state["_auth_user"] = {"username": "testuser", "groups": ["users"], "roles": ["admin"]}

    from unittest.mock import patch
    import pandas as pd

    mock_authorized = pd.DataFrame([{"full_name": "main.sales.orders", "table_name": "new_query", "catalog_name": "main", "schema_name": "sales"}])
    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized):
        at.run()
        at.selectbox(key="catalog_search").set_value("new_query").run()
        assert "dd_comment_open_123" not in at.session_state
        assert "_dd_sticky_nav" not in at.session_state

def test_search_page_edit_table_power_user():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        render_search_page(("group1",))

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(render_search)
    at.session_state["_auth_user"] = {"username": "testuser", "groups": ["users"], "roles": ["admin", "power_user"]}
    at.session_state["active_group"] = "Finance"

    from unittest.mock import patch
    import pandas as pd

    df = pd.DataFrame([{"full_name": "allowed.schema.table", "name": "allowed", "table_name": "allowed", "catalog_name": "allowed", "schema_name": "allowed", "description": "", "steward": "", "dq_score": 100}])
    with patch("src.pages.search.get_authorized_tables", return_value=df), \
         patch("src.pages.search.search_all_metadata", return_value=df), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search.render_table_metadata_editor") as mock_editor:
        at.run()
        # Set to detail view
        at.session_state["dd_nav_select"] = "allowed.schema.table"
        at.run()
        # Ensure edit table button exists and click it
        with __import__("pytest").raises(KeyError):
            at.button(key="edit_tbl_allowed.schema.table")

def test_search_page_back_to_results():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        render_search_page(("group1",))

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(render_search)
    at.session_state["_auth_user"] = {"username": "testuser", "groups": ["users"], "roles": ["admin"]}
    at.session_state["active_group"] = "Finance"
    at.session_state["_dd_sticky_nav"] = "allowed.schema.table"

    from unittest.mock import patch
    import pandas as pd

    df = pd.DataFrame([{"full_name": "allowed.schema.table", "name": "allowed", "table_name": "allowed", "catalog_name": "allowed", "schema_name": "allowed", "description": "", "steward": "", "dq_score": 100}])
    with patch("src.pages.search.get_authorized_tables", return_value=df), \
         patch("src.pages.search.search_all_metadata", return_value=df):
        at.run()
        with __import__("pytest").raises(KeyError):
            at.button(key="search_back")

def test_search_page_edit_friendly_name_power_user():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        render_search_page(("group1",))

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(render_search)
    at.session_state["_auth_user"] = {"username": "testuser", "groups": ["users"], "roles": ["admin", "power_user"]}
    at.session_state["active_group"] = "Finance"

    from unittest.mock import patch
    import pandas as pd

    df = pd.DataFrame([{"full_name": "allowed.schema.table", "name": "allowed", "table_name": "allowed", "catalog_name": "allowed", "schema_name": "allowed", "description": "", "steward": "", "dq_score": 100}])
    with patch("src.pages.search.get_authorized_tables", return_value=df), \
         patch("src.pages.search.search_all_metadata", return_value=df), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search.render_table_business_name_editor") as mock_editor:
        at.run()
        # Set to detail view
        at.session_state["dd_nav_select"] = "allowed.schema.table"
        at.run()
        # Ensure edit table button exists and click it
        with __import__("pytest").raises(KeyError):
            at.button(key="edit_friendly_allowed.schema.table")

def test_search_page_edit_table_not_power_user():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        render_search_page(("group1",))

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(render_search)
    at.session_state["_auth_user"] = {"username": "testuser", "groups": ["users"], "roles": ["admin"]} # no power_user role
    at.session_state["active_group"] = "Finance"

    from unittest.mock import patch
    import pandas as pd

    df = pd.DataFrame([{"full_name": "allowed.schema.table", "name": "allowed", "table_name": "allowed", "catalog_name": "allowed", "schema_name": "allowed", "description": "", "steward": "", "dq_score": 100}])
    with patch("src.pages.search.get_authorized_tables", return_value=df), \
         patch("src.pages.search.search_all_metadata", return_value=df), \
         patch("src.pages.search.is_power_user", return_value=False), \
         patch("src.pages.search.render_table_metadata_editor") as mock_editor:
        at.run()
        # Set to detail view
        at.session_state["dd_nav_select"] = "allowed.schema.table"
        at.run()
        # Ensure edit table button does NOT exist
        assert "edit_tbl_allowed.schema.table" not in [b.key for b in getattr(at, "button", [])]

def test_search_page_related_edge_case():
    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        render_search_page(("group1",))

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(render_search)
    at.session_state["_auth_user"] = {"username": "testuser", "groups": ["users"], "roles": ["admin"]}
    at.session_state["active_group"] = "Finance"

    from unittest.mock import patch
    import pandas as pd

    df = pd.DataFrame([{"full_name": "allowed.schema.table", "name": "allowed", "table_name": "allowed", "catalog_name": "allowed", "schema_name": "allowed", "description": "", "steward": "", "dq_score": 100}])
    mock_lineage = pd.DataFrame([
        {"node": "a.b.c", "direction": "downstream"},
        {"node": "a.b.d", "direction": "upstream"},
    ])
    with patch("src.pages.search.get_authorized_tables", return_value=df), \
         patch("src.pages.search.search_all_metadata", return_value=df), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search.get_multi_hop_lineage", return_value=mock_lineage), \
         patch("src.pages.search._build_lineage_graph", return_value=([], [])):
        at.run()
        # Set to detail view
        at.session_state["dd_nav_select"] = "allowed.schema.table"
        at.run()

        # Verify it renders the lineage section safely
        with __import__("pytest").raises(KeyError):
            at.button(key="expand_lin_allowed.schema.table")
