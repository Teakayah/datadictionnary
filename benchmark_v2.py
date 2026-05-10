import time
import pandas as pd
from unittest.mock import patch
from src.pages.search import render_search_page
import streamlit as st

def get_authorized_tables_mock(groups):
    # Simulate an I/O delay or computational cost associated with fetching from the DB
    time.sleep(0.01) # 10ms
    return pd.DataFrame({"full_name": [f"catalog.schema.table_{i}" for i in range(100)], "table_name": [f"table_{i}" for i in range(100)], "name": [f"table_{i}" for i in range(100)], "match_type": ["Table" for _ in range(100)], "description": ["desc" for _ in range(100)]})

def search_all_metadata_mock(query, groups):
    return pd.DataFrame({"full_name": [f"catalog.schema.table_{i}" for i in range(50)], "table_name": [f"table_{i}" for i in range(50)], "name": [f"table_{i}" for i in range(50)], "match_type": ["Table" for _ in range(50)], "description": ["desc" for _ in range(50)]})

@patch("src.pages.search.get_authorized_tables", side_effect=get_authorized_tables_mock)
@patch("src.pages.search.search_all_metadata", side_effect=search_all_metadata_mock)
@patch("streamlit.selectbox", return_value="test_query")
@patch("streamlit.columns", return_value=(patch("streamlit.container").start(), patch("streamlit.container").start()))
def run_benchmark(mock_cols, mock_selectbox, mock_search, mock_auth):
    # Setup mock session state
    st.session_state.clear()

    start_time = time.time()
    render_search_page(("group1",))
    end_time = time.time()

    print(f"Time taken for rendering search page with 50 results: {end_time - start_time:.4f} seconds")

run_benchmark()
