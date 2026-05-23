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

    def get_zero_result_alerts(self, days: int = 7) -> List[dict]:
        """Retrieve search terms returning zero results for more than N days."""
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

    def get_zero_result_alerts(self, days: int = 7) -> List[dict]:
        from src.db.duckdb_adapter import _DuckDBConn
        with _DuckDBConn(self.db_path) as conn:
            # DuckDB-specific query: groups zero-result searches by query,
            # calculates frequency, and flags terms where first search is > N days ago.
            query = """
                SELECT 
                    query, 
                    COUNT(*) as search_count, 
                    MIN(timestamp) as first_seen, 
                    MAX(timestamp) as last_seen 
                FROM user_data.search_analytics 
                WHERE results_count = 0 
                GROUP BY query 
                HAVING MIN(timestamp) < CAST(current_timestamp - INTERVAL '1' DAY * ? AS TIMESTAMP)
                ORDER BY last_seen DESC
            """
            df = conn.fetchall_as_pandas(query, (days,))
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

    def get_zero_result_alerts(self, days: int = 7) -> List[dict]:
        import streamlit as st
        from datetime import datetime, timezone, timedelta
        data = st.session_state.get("demo_analytics", [])
        zeros = [d for d in data if d["results_count"] == 0]
        
        # Group by query
        groups = {}
        for z in zeros:
            q = z["query"]
            ts = z["timestamp"]
            # Ensure ts is a datetime object
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if isinstance(ts, datetime) and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            
            if q not in groups:
                groups[q] = []
            groups[q].append(ts)
        
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)
        
        alerts = []
        for q, times in groups.items():
            first_seen = min(times)
            last_seen = max(times)
            if first_seen < cutoff:
                alerts.append({
                    "query": q,
                    "search_count": len(times),
                    "first_seen": first_seen,
                    "last_seen": last_seen
                })
        
        return sorted(alerts, key=lambda x: x["last_seen"], reverse=True)

