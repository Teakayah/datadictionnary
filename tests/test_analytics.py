"""Tests for src/analytics.py — search-event tracking and zero-result gaps.

Covers both branches:
  - demo (session-state) path: track_search + the 7-day alert cutoff logic
  - DuckDB path: alerts and zero-result listing against a temp database
"""

import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import duckdb
import pandas as pd
import streamlit as st

from src.analytics import (
    SearchEvent,
    get_zero_result_alerts,
    get_zero_result_searches,
    track_search,
)


def test_demo_analytics_alerts():
    st.session_state.demo_analytics = []
    now = datetime.now(timezone.utc)

    with patch("src.analytics._use_demo_backend", return_value=True):
        # 1. term1: first search 8 days ago, last 2 days ago (should trigger)
        track_search(SearchEvent("term1", 0, "u1@test.com", now - timedelta(days=8)))
        track_search(SearchEvent("term1", 0, "u1@test.com", now - timedelta(days=2)))

        # 2. term2: first search 2 days ago (should NOT trigger)
        track_search(SearchEvent("term2", 0, "u1@test.com", now - timedelta(days=2)))

        # 3. term3: first search 8 days ago, but has results (should NOT trigger)
        track_search(SearchEvent("term3", 5, "u1@test.com", now - timedelta(days=8)))

        alerts = get_zero_result_alerts(7)

    assert len(alerts) == 1
    assert alerts[0]["query"] == "term1"
    assert alerts[0]["search_count"] == 2
    assert alerts[0]["first_seen"] == now - timedelta(days=8)
    assert alerts[0]["last_seen"] == now - timedelta(days=2)

    st.session_state.pop("demo_analytics", None)


class _TestDuckDBCursor:
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

    def execute_write(self, query, params=None):
        self.con.execute(query, params)
        return self

    def fetchall_as_pandas(self):
        if self.rel is None:
            return pd.DataFrame()
        return self.rel.df()


def _make_test_conn_class(db_path):
    class _TestDuckDBConn:
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
            return _TestDuckDBCursor(self.con)

        def execute(self, query, params=None):
            return _TestDuckDBCursor(self.con).execute(query, params)

    return _TestDuckDBConn


def _seed_analytics_db(db_path, rows):
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
        for row in rows:
            conn.execute(f"INSERT INTO user_data.search_analytics VALUES {row}")


def test_duckdb_analytics_alerts():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_analytics.duckdb")
    try:
        _seed_analytics_db(db_path, [
            # term1: zero-result search 8 days ago (should alert)
            "('term1', 0, 'u1@test.com', current_timestamp - INTERVAL 8 DAY)",
            # term2: zero-result search 2 days ago (should NOT alert)
            "('term2', 0, 'u1@test.com', current_timestamp - INTERVAL 2 DAY)",
            # term3: search with results 8 days ago (should NOT alert)
            "('term3', 10, 'u1@test.com', current_timestamp - INTERVAL 8 DAY)",
        ])

        with patch("src.analytics._use_demo_backend", return_value=False), \
             patch("src.db.duckdb_adapter._DuckDBConn",
                   side_effect=_make_test_conn_class(db_path)):
            alerts = get_zero_result_alerts(7)

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
        _seed_analytics_db(db_path, [
            "('term1', 0, 'u1@test.com', current_timestamp)",
            "('term2', 5, 'u1@test.com', current_timestamp)",
        ])

        with patch("src.analytics._use_demo_backend", return_value=False), \
             patch("src.db.duckdb_adapter._DuckDBConn",
                   side_effect=_make_test_conn_class(db_path)):
            zeros = get_zero_result_searches(limit=10)

        assert len(zeros) == 1
        assert zeros[0]["query"] == "term1"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)

def test_track_search_duckdb_path():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_analytics_track.duckdb")
    try:
        # Ensure the schema exists
        with duckdb.connect(db_path) as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS user_data")

        now = datetime.now(timezone.utc)
        event = SearchEvent("new_term", 10, "u1@test.com", now)

        with patch("src.analytics._use_demo_backend", return_value=False), \
             patch("src.db.duckdb_adapter._DuckDBConn", side_effect=_make_test_conn_class(db_path)), \
             patch("src.analytics._analytics_conn", side_effect=_make_test_conn_class(db_path)), \
             patch("src.analytics.threading.Thread") as mock_thread, \
             patch("streamlit.runtime.scriptrunner.add_script_run_ctx"):

            track_search(event)

            # Extract the background function and run it synchronously
            assert mock_thread.call_count == 1
            target_func = mock_thread.call_args[1]["target"]
            target_func()

        with duckdb.connect(db_path) as conn:
            res = conn.execute("SELECT query, results_count, user_email FROM user_data.search_analytics").fetchall()
            assert len(res) == 1
            assert res[0] == ("new_term", 10, "u1@test.com")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)

def test_track_search_duckdb_path_error():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_analytics_track.duckdb")
    try:
        now = datetime.now(timezone.utc)
        event = SearchEvent("new_term", 10, "u1@test.com", now)

        with patch("src.analytics._use_demo_backend", return_value=False), \
             patch("src.db.duckdb_adapter._DuckDBConn", side_effect=Exception("DB connection error")), \
             patch("src.analytics._analytics_conn", side_effect=Exception("DB connection error")), \
             patch("src.analytics.threading.Thread") as mock_thread, \
             patch("streamlit.runtime.scriptrunner.add_script_run_ctx"), \
             patch("src.analytics.logging") as mock_logging:

            track_search(event)

            # Extract the background function and run it synchronously
            assert mock_thread.call_count == 1
            target_func = mock_thread.call_args[1]["target"]
            target_func()

            assert mock_logging.warning.call_count == 1
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)

def test_demo_zero_result_searches():
    st.session_state.demo_analytics = [
        {"query": "term1", "results_count": 0, "user_email": "u@test.com", "timestamp": datetime.now(timezone.utc) - timedelta(days=1)},
        {"query": "term2", "results_count": 5, "user_email": "u@test.com", "timestamp": datetime.now(timezone.utc)}
    ]
    with patch("src.analytics._use_demo_backend", return_value=True):
        zeros = get_zero_result_searches(limit=10)
        assert len(zeros) == 1
        assert zeros[0]["query"] == "term1"
    st.session_state.pop("demo_analytics", None)

def test_demo_track_search():
    st.session_state.pop("demo_analytics", None)
    now = datetime.now(timezone.utc)
    event = SearchEvent("new_term", 10, "u1@test.com", now)

    with patch("src.analytics._use_demo_backend", return_value=True):
        track_search(event)
        assert len(st.session_state.demo_analytics) == 1
        assert st.session_state.demo_analytics[0]["query"] == "new_term"

    st.session_state.pop("demo_analytics", None)

from unittest.mock import MagicMock

def test_duckdb_analytics_alerts_connection_closed():
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.open = False

    with patch("src.analytics._use_demo_backend", return_value=False), \
         patch("src.analytics._analytics_conn", return_value=mock_conn):
        alerts = get_zero_result_alerts(7)
        assert alerts == []

def test_duckdb_analytics_zero_searches_connection_closed():
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.open = False

    with patch("src.analytics._use_demo_backend", return_value=False), \
         patch("src.analytics._analytics_conn", return_value=mock_conn):
        zeros = get_zero_result_searches(10)
        assert zeros == []

def test_demo_analytics_alerts_date_parsing():
    now_utc = datetime.now(timezone.utc)
    st.session_state.demo_analytics = [
        {"query": "term_str", "results_count": 0, "user_email": "u@test.com", "timestamp": (now_utc - timedelta(days=8)).isoformat()},
        {"query": "term_naive", "results_count": 0, "user_email": "u@test.com", "timestamp": (now_utc - timedelta(days=8)).replace(tzinfo=None)},
    ]
    try:
        with patch("src.analytics._use_demo_backend", return_value=True):
            alerts = get_zero_result_alerts(7)
            queries = [a["query"] for a in alerts]
            assert "term_str" in queries
            assert "term_naive" in queries
    finally:
        st.session_state.pop("demo_analytics", None)

def test_use_demo_backend():
    from src.analytics import _use_demo_backend
    with patch("src.config.is_demo_mode", return_value=True), \
         patch("src.db.duckdb_adapter._duckdb_available", return_value=True):
        assert _use_demo_backend() == True

    with patch("src.config.is_demo_mode", return_value=False), \
         patch("src.db.duckdb_adapter._duckdb_available", return_value=False):
        assert _use_demo_backend() == True

    with patch("src.config.is_demo_mode", return_value=False), \
         patch("src.db.duckdb_adapter._duckdb_available", return_value=True):
        assert _use_demo_backend() == False
