import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import streamlit as st
import duckdb
import pandas as pd

from src.storage.analytics_storage import (
    SearchEvent,
    DemoAnalyticsStorage,
    DuckDBAnalyticsStorage,
)

def test_demo_analytics_alerts():
    # Setup st.session_state
    st.session_state.demo_analytics = []
    storage = DemoAnalyticsStorage()

    now = datetime.now(timezone.utc)

    # 1. Search term 1: first search 8 days ago, last 2 days ago (should trigger)
    storage.track_search(SearchEvent("term1", 0, "u1@test.com", now - timedelta(days=8)))
    storage.track_search(SearchEvent("term1", 0, "u1@test.com", now - timedelta(days=2)))

    # 2. Search term 2: first search 2 days ago (should NOT trigger)
    storage.track_search(SearchEvent("term2", 0, "u1@test.com", now - timedelta(days=2)))

    # 3. Search term 3: first search 8 days ago, but has results (should NOT trigger)
    storage.track_search(SearchEvent("term3", 5, "u1@test.com", now - timedelta(days=8)))

    # Run get_zero_result_alerts(7)
    alerts = storage.get_zero_result_alerts(7)

    # Assertions
    assert len(alerts) == 1
    assert alerts[0]["query"] == "term1"
    assert alerts[0]["search_count"] == 2
    assert alerts[0]["first_seen"] == now - timedelta(days=8)
    assert alerts[0]["last_seen"] == now - timedelta(days=2)


def test_duckdb_analytics_alerts():
    # Setup temporary file
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_analytics.duckdb")

    try:
        # Pre-create schema inside a mock/connection structure
        with duckdb.connect(db_path) as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS user_data")
            conn.execute("""
                CREATE TABLE user_data.search_analytics (
                    query           VARCHAR,
                    results_count   INTEGER,
                    user_email      VARCHAR,
                    timestamp       TIMESTAMP
                )
            """)

            # Insert mock data
            # Term 1: zero-result search 8 days ago (should alert)
            conn.execute(
                "INSERT INTO user_data.search_analytics VALUES ('term1', 0, 'u1@test.com', current_timestamp - INTERVAL 8 DAY)"
            )
            # Term 2: zero-result search 2 days ago (should NOT alert)
            conn.execute(
                "INSERT INTO user_data.search_analytics VALUES ('term2', 0, 'u1@test.com', current_timestamp - INTERVAL 2 DAY)"
            )
            # Term 3: search with results 8 days ago (should NOT alert)
            conn.execute(
                "INSERT INTO user_data.search_analytics VALUES ('term3', 10, 'u1@test.com', current_timestamp - INTERVAL 8 DAY)"
            )

        # Instantiate DuckDBAnalyticsStorage
        # We need to mock _DuckDBConn to connect to our temp test file!
        with patch("src.db.duckdb_adapter._DuckDBConn") as mock_conn_class:
            # When _DuckDBConn is instantiated, return a real connection wrapper to our test database!
            class TestDuckDBCursor:
                def __init__(self, con):
                    self.con = con
                    self.rel = None
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    pass
                def execute(self, query, params=None):
                    self.rel = self.con.execute(query, params)
                    return self
                def fetchall_as_pandas(self):
                    if self.rel is None:
                        return pd.DataFrame()
                    return self.rel.df()

            class TestDuckDBConn:
                def __init__(self, *args, **kwargs):
                    self.con = duckdb.connect(db_path)
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    self.con.close()
                @property
                def open(self):
                    return True
                def cursor(self):
                    return TestDuckDBCursor(self.con)
                def execute(self, query, params=None):
                    return TestDuckDBCursor(self.con).execute(query, params)
                def execute_write(self, query, params=None):
                    self.con.execute(query, params)
                    return self
                def fetchall_as_pandas(self, query, params=None):
                    return self.con.execute(query, params).df()
                def cursor(self):
                    from contextlib import contextmanager
                    outer_con = self.con
                    @contextmanager
                    def _cursor_ctx():
                        class _Cur:
                            def __init__(self_):
                                self_._q = None
                                self_._p = None
                            def execute(self_, q, p=None):
                                self_._q = q
                                self_._p = p
                            def fetchall_as_pandas(self_):
                                return outer_con.execute(self_._q, self_._p).df()
                        yield _Cur()
                    return _cursor_ctx()

            mock_conn_class.side_effect = TestDuckDBConn

            storage = DuckDBAnalyticsStorage(db_path)
            alerts = storage.get_zero_result_alerts(7)

            # Assertions
            assert len(alerts) == 1
            assert alerts[0]["query"] == "term1"
            assert alerts[0]["search_count"] == 1
            assert "first_seen" in alerts[0]
            assert "last_seen" in alerts[0]
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)

def test_duckdb_analytics_zero_result_searches():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_analytics_zero.duckdb")

    try:
        with duckdb.connect(db_path) as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS user_data")
            conn.execute("""
                CREATE TABLE user_data.search_analytics (
                    query           VARCHAR,
                    results_count   INTEGER,
                    user_email      VARCHAR,
                    timestamp       TIMESTAMP
                )
            """)

            conn.execute("INSERT INTO user_data.search_analytics VALUES ('term1', 0, 'u1@test.com', current_timestamp)")
            conn.execute("INSERT INTO user_data.search_analytics VALUES ('term2', 5, 'u1@test.com', current_timestamp)")

        with patch("src.db.duckdb_adapter._DuckDBConn") as mock_conn_class:
            class TestDuckDBCursor:
                def __init__(self, con):
                    self.con = con
                    self.rel = None
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    pass
                def execute(self, query, params=None):
                    self.rel = self.con.execute(query, params)
                    return self
                def fetchall_as_pandas(self):
                    if self.rel is None:
                        return pd.DataFrame()
                    return self.rel.df()

            class TestDuckDBConn:
                def __init__(self, *args, **kwargs):
                    self.con = duckdb.connect(db_path)
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    self.con.close()
                @property
                def open(self):
                    return True
                def cursor(self):
                    return TestDuckDBCursor(self.con)
                def execute(self, query, params=None):
                    return TestDuckDBCursor(self.con).execute(query, params)

            mock_conn_class.side_effect = TestDuckDBConn

            storage = DuckDBAnalyticsStorage(db_path)
            zeros = storage.get_zero_result_searches(limit=10)

            assert len(zeros) == 1
            assert zeros[0]["query"] == "term1"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)

def test_duckdb_analytics_closed_conn():
    # Test that closed connection returns empty lists
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_analytics_closed.duckdb")

    # We don't even need to init DB schema for this test because conn is closed
    with patch("src.db.duckdb_adapter._DuckDBConn") as mock_conn_class:
        class ClosedConn:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_): pass
            @property
            def open(self): return False
            def execute(self, *args): pass
            def cursor(self): pass

        mock_conn_class.side_effect = ClosedConn

        # We need to mock _init_db since it tries to execute during init
        with patch.object(DuckDBAnalyticsStorage, "_init_db"):
            storage = DuckDBAnalyticsStorage(db_path)
            assert storage.get_zero_result_searches() == []
            assert storage.get_zero_result_alerts() == []

def test_duckdb_analytics_empty_results():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_analytics_empty.duckdb")

    try:
        with duckdb.connect(db_path) as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS user_data")
            conn.execute("""
                CREATE TABLE user_data.search_analytics (
                    query           VARCHAR,
                    results_count   INTEGER,
                    user_email      VARCHAR,
                    timestamp       TIMESTAMP
                )
            """)

        with patch("src.db.duckdb_adapter._DuckDBConn") as mock_conn_class:
            class TestDuckDBCursor:
                def __init__(self, con):
                    self.con = con
                    self.rel = None
                def __enter__(self): return self
                def __exit__(self, *_): pass
                def execute(self, query, params=None):
                    self.rel = self.con.execute(query, params)
                    return self
                def fetchall_as_pandas(self):
                    # Return None for alerts to test None case
                    if "HAVING MIN(timestamp)" in self.rel.alias: # Hacky way to check
                        pass # Not robust
                    if self.rel is None:
                        return None
                    return self.rel.df()

            class TestDuckDBConn:
                def __init__(self, *args, **kwargs):
                    self.con = duckdb.connect(db_path)
                def __enter__(self): return self
                def __exit__(self, *_): self.con.close()
                @property
                def open(self): return True
                def cursor(self): return TestDuckDBCursor(self.con)
                def execute(self, query, params=None):
                    class MockRel:
                        def fetchall_as_pandas(self):
                            # Return empty dataframe
                            return pd.DataFrame()
                    return MockRel()

            mock_conn_class.side_effect = TestDuckDBConn

            storage = DuckDBAnalyticsStorage(db_path)
            assert storage.get_zero_result_searches() == []
            assert storage.get_zero_result_alerts() == []
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)

def test_demo_analytics_str_timestamps():
    st.session_state.demo_analytics = []
    storage = DemoAnalyticsStorage()

    # Insert str timestamp without timezone
    st.session_state.demo_analytics.append({
        "query": "term_str",
        "results_count": 0,
        "user_email": "u@t.com",
        "timestamp": "2023-01-01T12:00:00"
    })

    # Should not crash and should parse
    alerts = storage.get_zero_result_alerts(7)
    assert len(alerts) == 1
    assert alerts[0]["query"] == "term_str"
    assert alerts[0]["first_seen"].tzinfo is not None

def test_duckdb_analytics_track_search():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_analytics_track.duckdb")

    try:
        with duckdb.connect(db_path) as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS user_data")
            conn.execute("""
                CREATE TABLE user_data.search_analytics (
                    query           VARCHAR,
                    results_count   INTEGER,
                    user_email      VARCHAR,
                    timestamp       TIMESTAMP
                )
            """)

        with patch("src.db.duckdb_adapter._DuckDBConn") as mock_conn_class:
            class TestDuckDBCursor:
                def __init__(self, con):
                    self.con = con
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    pass
                def execute(self, query, params=None):
                    self.con.execute(query, params)
                    return self
                def execute_write(self, query, params=None):
                    self.con.execute(query, params)
                    return self

            class TestDuckDBConn:
                def __init__(self, *args, **kwargs):
                    self.con = duckdb.connect(db_path)
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    self.con.close()
                @property
                def open(self):
                    return True
                def cursor(self):
                    return TestDuckDBCursor(self.con)
                def execute(self, query, params=None):
                    return TestDuckDBCursor(self.con).execute(query, params)

            mock_conn_class.side_effect = TestDuckDBConn

            storage = DuckDBAnalyticsStorage(db_path)
            now = datetime.now(timezone.utc)
            storage.track_search(SearchEvent("new_term", 0, "u1@test.com", now))

            # Verify it was written
            with duckdb.connect(db_path) as conn:
                res = conn.execute("SELECT query FROM user_data.search_analytics").fetchall()
                assert len(res) == 1
                assert res[0][0] == "new_term"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)

def test_demo_analytics_empty_state_init():
    import streamlit as st
    # Clear session state if demo_analytics exists
    if "demo_analytics" in st.session_state:
        del st.session_state["demo_analytics"]

    storage = DemoAnalyticsStorage()
    # This should initialize st.session_state.demo_analytics
    storage.track_search(SearchEvent("new_term", 0, "u1@test.com", datetime.now(timezone.utc)))

    assert "demo_analytics" in st.session_state
    assert len(st.session_state.demo_analytics) == 1

def test_demo_analytics_get_zero_results():
    import streamlit as st
    st.session_state.demo_analytics = []
    storage = DemoAnalyticsStorage()

    now = datetime.now(timezone.utc)
    # 0 result searches
    storage.track_search(SearchEvent("term0_1", 0, "u1@test.com", now - timedelta(hours=1)))
    storage.track_search(SearchEvent("term0_2", 0, "u1@test.com", now))

    # >0 result searches
    storage.track_search(SearchEvent("term1_1", 5, "u1@test.com", now - timedelta(hours=2)))

    zeros = storage.get_zero_result_searches(limit=10)
    assert len(zeros) == 2
    # Should be sorted by timestamp desc, so term0_2 first
    assert zeros[0]["query"] == "term0_2"
    assert zeros[1]["query"] == "term0_1"
