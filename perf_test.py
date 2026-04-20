import time
import os
import streamlit as st
import pandas as pd
from unittest.mock import patch, MagicMock

os.environ["ENABLE_MOCK_AUTH"] = "true"
os.environ["ENVIRONMENT"] = "development"

import databricks.sql as sql

def mock_connect(*args, **kwargs):
    time.sleep(0.5) # Simulate expensive connection
    class MockCursor:
        def execute(self, *a, **k): pass
        def fetchall_as_pandas(self): return pd.DataFrame([{"a": 1}])
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class MockConn:
        def cursor(self): return MockCursor()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    return MockConn()

sql.connect = mock_connect

with patch('streamlit.stop'), patch('streamlit.rerun'), patch('streamlit.warning'), patch('streamlit.markdown'):
    import app

def run_performance_test():
    start = time.time()
    for i in range(5):
        # We use a different query each time so it skips the `run_query` cache
        # and we can measure the connection time overhead
        app.run_query(f"SELECT {i}", None)
    duration = time.time() - start
    print(f"Time taken for 5 queries: {duration:.2f} seconds")

run_performance_test()
