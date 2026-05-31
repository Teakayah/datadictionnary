import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import streamlit as st
import duckdb

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
            class TestDuckDBConn:
                def __init__(self, *args, **kwargs):
                    self.con = duckdb.connect(db_path)
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    self.con.close()
                def execute(self, query, params=None):
                    self.con.execute(query, params)
                    return self
                def execute_write(self, query, params=None):
                    self.con.execute(query, params)
                    return self
                def cursor(self):
                    class MockCursor:
                        def __init__(self, rel):
                            self._rel = rel
                        def execute(self, sql, params=None):
                            self._rel = self._rel.execute(sql, params)
                        def fetchall_as_pandas(self):
                            return self._rel.df()
                        def __enter__(self):
                            return self
                        def __exit__(self, *_):
                            pass
                    return MockCursor(self.con)

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
