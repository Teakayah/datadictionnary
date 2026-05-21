from __future__ import annotations
from typing import Protocol, List, Optional
from datetime import datetime, timezone

class SearchEvent:
    def __init__(
        self,
        query: str,
        results_count: int,
        user_email: str,
        timestamp: Optional[datetime] = None
    ):
        self.query = query
        self.results_count = results_count
        self.user_email = user_email
        self.timestamp = timestamp or datetime.now(timezone.utc)

class AnalyticsStorage(Protocol):
    """Protocol for tracking UI events and search performance."""
    
    def track_search(self, event: SearchEvent) -> None:
        """Record a search event."""
        ...

    def get_zero_result_searches(self, limit: int = 50) -> List[dict]:
        """Retrieve most recent searches that returned no results."""
        ...

class DuckDBAnalyticsStorage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        from src.db.duckdb_adapter import _DuckDBConn
        with _DuckDBConn(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_data.search_analytics (
                    query           VARCHAR,
                    results_count   INTEGER,
                    user_email      VARCHAR,
                    timestamp       TIMESTAMP DEFAULT current_timestamp
                )
            """)

    def track_search(self, event: SearchEvent) -> None:
        from src.db.duckdb_adapter import _DuckDBConn
        with _DuckDBConn(self.db_path) as conn:
            conn.execute_write(
                "INSERT INTO user_data.search_analytics (query, results_count, user_email, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (event.query, event.results_count, event.user_email, event.timestamp)
            )

    def get_zero_result_searches(self, limit: int = 50) -> List[dict]:
        from src.db.duckdb_adapter import _DuckDBConn
        with _DuckDBConn(self.db_path) as conn:
            df = conn.fetchall_as_pandas(
                "SELECT query, user_email, timestamp FROM user_data.search_analytics "
                "WHERE results_count = 0 ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            return df.to_dict('records') if df is not None else []

class DemoAnalyticsStorage:
    def track_search(self, event: SearchEvent) -> None:
        import streamlit as st
        if "demo_analytics" not in st.session_state:
            st.session_state.demo_analytics = []
        st.session_state.demo_analytics.append({
            "query": event.query,
            "results_count": event.results_count,
            "user_email": event.user_email,
            "timestamp": event.timestamp
        })

    def get_zero_result_searches(self, limit: int = 50) -> List[dict]:
        import streamlit as st
        data = st.session_state.get("demo_analytics", [])
        zeros = [d for d in data if d["results_count"] == 0]
        return sorted(zeros, key=lambda x: x["timestamp"], reverse=True)[:limit]

class FakeAnalyticsStorage:
    def __init__(self):
        self.events = []
    
    def track_search(self, event: SearchEvent) -> None:
        self.events.append(event)

    def get_zero_result_searches(self, limit: int = 50) -> List[dict]:
        zeros = [vars(e) for e in self.events if e.results_count == 0]
        return sorted(zeros, key=lambda x: x["timestamp"], reverse=True)[:limit]
