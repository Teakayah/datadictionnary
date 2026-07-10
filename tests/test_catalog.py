import pandas as pd
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

# We must wrap the function to be tested and import inside the function scope
# because AppTest.from_function executes the script in an isolated context
# that does not inherit the global namespace.
def _render_catalog_wrapper(*args, **kwargs):
    # Ensure streamlit is imported in the isolated context
    from src.pages.catalog import render_catalog_browser

    render_catalog_browser(*args, **kwargs)

@patch("src.pages.catalog.get_authorized_tables")
def test_catalog_browser_normal(mock_get_tables):
    # Arrange
    df = pd.DataFrame({
        "catalog_name": ["main", "main", "analytics"],
        "schema_name": ["public", "internal", "public"],
        "table_name": ["users", "settings", "events"],
        "dq_score": ["A", "B", "C"]
    })
    mock_get_tables.return_value = df

    # Act
    at = AppTest.from_function(_render_catalog_wrapper, args=(["admin"],))
    at.run()

    # Assert
    assert not at.exception
    # Check expanders for catalogs
    expander_labels = [e.label for e in at.expander]
    assert "📁 main" in expander_labels
    assert "📁 analytics" in expander_labels

    # Check buttons for tables
    button_labels = [b.label for b in at.button]
    assert "📄 users" in button_labels
    assert "📄 settings" in button_labels
    assert "📄 events" in button_labels

@patch("src.pages.catalog.get_authorized_tables")
def test_catalog_browser_empty(mock_get_tables):
    # Arrange: empty dataframe
    mock_get_tables.return_value = pd.DataFrame()

    # Act
    at = AppTest.from_function(_render_catalog_wrapper, args=(["admin"],))
    at.run()

    # Assert
    assert not at.exception
    assert len(at.info) > 0
    assert at.info[0].value == "No catalogs accessible."

@patch("src.pages.catalog.get_authorized_tables")
def test_catalog_browser_none(mock_get_tables):
    # Arrange: None returned
    mock_get_tables.return_value = None

    # Act
    at = AppTest.from_function(_render_catalog_wrapper, args=(["admin"],))
    at.run()

    # Assert
    assert not at.exception
    assert len(at.info) > 0
    assert at.info[0].value == "No catalogs accessible."

@patch("src.pages.catalog.get_authorized_tables")
def test_catalog_browser_truncation(mock_get_tables):
    # Arrange: > 50 tables in one schema
    num_tables = 55
    df = pd.DataFrame({
        "catalog_name": ["main"] * num_tables,
        "schema_name": ["public"] * num_tables,
        "table_name": [f"table_{i}" for i in range(num_tables)],
        "dq_score": ["A"] * num_tables
    })
    mock_get_tables.return_value = df

    # Act
    at = AppTest.from_function(_render_catalog_wrapper, args=(["admin"],))
    at.run()

    # Assert
    assert not at.exception
    # Ensure exactly 50 buttons are rendered, even though there are 55 tables
    assert len(at.button) == 50
    # Ensure the truncation message is shown in markdown
    markdown_values = [m.value for m in at.markdown]
    assert any("and 5 more tables" in m or "...and 5 more tables" in m for m in markdown_values)

@patch("src.pages.catalog.get_authorized_tables")
def test_catalog_browser_error_handling(mock_get_tables):
    # Arrange: Mock to throw Exception
    mock_get_tables.side_effect = Exception("Database connection failed")

    # Act
    at = AppTest.from_function(_render_catalog_wrapper, args=(["admin"],))
    at.run()

    # Assert
    assert not at.exception
    assert len(at.error) > 0
    assert at.error[0].value == "Could not load catalog hierarchy."

@patch("src.pages.catalog.get_authorized_tables")
def test_catalog_browser_button_click(mock_get_tables):
    # Arrange
    df = pd.DataFrame({
        "catalog_name": ["main"],
        "schema_name": ["public"],
        "table_name": ["users"],
        "dq_score": ["A"]
    })
    mock_get_tables.return_value = df

    at = AppTest.from_function(_render_catalog_wrapper, args=(["admin"],))
    at.run()

    # Ensure button exists
    assert len(at.button) == 1
    assert at.button[0].label == "📄 users"

    # Act: Click the button
    at.button[0].click().run()

    # Assert: Session state and query params are updated
    assert at.session_state["dd_search_override"] == "users"
    assert at.session_state["dd_nav_select"] == "main.public.users"
    assert at.query_params["tab"] == ["search"]
