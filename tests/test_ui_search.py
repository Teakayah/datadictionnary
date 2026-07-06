import pandas as pd
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
# We have to import the file directly to get coverage on it!

def wrapper():
    from src.pages.search import render_search_page
    render_search_page(query_groups=("test_group",))

def test_search_page_empty():
    with patch("src.pages.search.get_authorized_tables", return_value=pd.DataFrame()):
        at = AppTest.from_function(wrapper)
        at.run()
        assert not at.exception
        assert len(at.info) > 0
        assert "access" in at.info[0].value.lower()

def test_search_page_with_tables():
    mock_df = pd.DataFrame({
        "full_name": ["db.schema.table1", "db.schema.table2"],
        "table_name": ["table1", "table2"],
        "schema_name": ["schema", "schema"],
        "catalog_name": ["db", "db"],
        "description": ["desc1", "desc2"],
        "dq_score": [100, 90]
    })

    with patch("src.pages.search.get_authorized_tables", return_value=mock_df):
        at = AppTest.from_function(wrapper)
        at.run()
        assert not at.exception
        assert len(at.selectbox) == 1

def test_search_page_with_query():
    mock_df = pd.DataFrame({
        "full_name": ["db.schema.table1"],
        "table_name": ["table1"],
        "schema_name": ["schema"],
        "catalog_name": ["db"],
        "description": ["desc1"],
        "dq_score": [100]
    })

    mock_search_df = pd.DataFrame({
        "full_name": ["db.schema.table1"],
        "table_name": ["table1"],
        "schema_name": ["schema"],
        "catalog_name": ["db"],
        "description": ["desc1"],
        "dq_score": [100],
        "match_type": ["Table"]
    })

    with patch("src.pages.search.get_authorized_tables", return_value=mock_df), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search_df), \
         patch("src.pages.search.track_search") as mock_track:
        at = AppTest.from_function(wrapper)
        at.run()
        at.selectbox[0].select("table1").run()
        assert not at.exception
        mock_track.assert_called_once()

def test_search_page_exception():
    with patch("src.pages.search.get_authorized_tables", side_effect=Exception("DB Error")):
        at = AppTest.from_function(wrapper)
        at.run()
        assert not at.exception
        assert len(at.error) > 0
        assert any("error" in i.value.lower() for i in at.error)

def test_search_page_search_exception():
    mock_df = pd.DataFrame({
        "full_name": ["db.schema.table1"],
        "table_name": ["table1"],
        "schema_name": ["schema"],
        "catalog_name": ["db"],
        "description": ["desc1"],
        "dq_score": [100]
    })

    with patch("src.pages.search.get_authorized_tables", return_value=mock_df), \
         patch("src.pages.search.search_all_metadata", side_effect=Exception("Search Error")):
        at = AppTest.from_function(wrapper)
        at.run()
        at.selectbox[0].select("table1").run()
        assert not at.exception
        assert len(at.error) > 0
        assert any("error" in i.value.lower() for i in at.error)
