"""Search analytics — tracks query events and surfaces zero-result gaps.

Demo mode (or no DuckDB) keeps events in
``st.session_state['demo_analytics']``; otherwise rows persist to
``user_data.search_analytics`` in a dedicated DuckDB connection against
``USER_DATA_PATH`` (analytics writes shouldn't contend with the shared
read connection).
"""

from __future__ import annotations
from datetime import datetime, timedelta, UTC
import threading
import logging


class SearchEvent:
    def __init__(
        self,
        query: str,
        results_count: int,
        user_email: str,
        timestamp: datetime | None = None
    ):
        self.query = query
        self.results_count = results_count
        self.user_email = user_email
        self.timestamp = timestamp or datetime.now(UTC)


def _use_demo_backend() -> bool:
    from src.config import is_demo_mode
    from src.db.duckdb_adapter import _duckdb_available
    return is_demo_mode() or not _duckdb_available()


def _analytics_conn():
    from src.config import USER_DATA_PATH
    from src.db.duckdb_adapter import _DuckDBConn
    return _DuckDBConn(USER_DATA_PATH)


def _ensure_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_data.search_analytics (
            query           VARCHAR,
            results_count   INTEGER,
            user_email      VARCHAR,
            timestamp       TIMESTAMP DEFAULT current_timestamp
        )
    """)


def track_search(event: SearchEvent) -> None:
    """Record a search event."""
    if _use_demo_backend():
        import streamlit as st
        if "demo_analytics" not in st.session_state:
            st.session_state.demo_analytics = []
        st.session_state.demo_analytics.append({
            "query": event.query,
            "results_count": event.results_count,
            "user_email": event.user_email,
            "timestamp": event.timestamp
        })
        return
    # ⚡ Bolt: Offload DuckDB analytics insert to a background thread to prevent disk I/O from blocking the main Streamlit render thread.
    def _write_db():
        try:
            with _analytics_conn() as conn:
                _ensure_table(conn)
                with conn.cursor() as cur:
                    cur.execute_write(
                        "INSERT INTO user_data.search_analytics (query, results_count, user_email, timestamp) "
                        "VALUES (?, ?, ?, ?)",
                        (event.query, event.results_count, event.user_email, event.timestamp)
                    )
        except Exception as e:
            logging.warning("Background analytics tracking failed: %s", e)

    from streamlit.runtime.scriptrunner import add_script_run_ctx
    t = threading.Thread(target=_write_db, daemon=True)
    add_script_run_ctx(t)
    t.start()


def get_zero_result_searches(limit: int = 50) -> list[dict]:
    """Retrieve most recent searches that returned no results."""
    if _use_demo_backend():
        import streamlit as st
        data = st.session_state.get("demo_analytics", [])
        zeros = [d for d in data if d["results_count"] == 0]
        return sorted(zeros, key=lambda x: x["timestamp"], reverse=True)[:limit]
    with _analytics_conn() as conn:
        if not conn.open:
            return []
        _ensure_table(conn)
        df = conn.execute(
            "SELECT query, user_email, timestamp FROM user_data.search_analytics "
            "WHERE results_count = 0 ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall_as_pandas()
    return df.to_dict('records') if df is not None and not df.empty else []


def _get_demo_zero_result_alerts(days: int) -> list[dict]:
    import streamlit as st
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
            ts = ts.replace(tzinfo=UTC)

        if q not in groups:
            groups[q] = []
        groups[q].append(ts)

    now = datetime.now(UTC)
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


def get_zero_result_alerts(days: int = 7) -> list[dict]:
    """Retrieve search terms returning zero results for more than N days."""
    if _use_demo_backend():
        return _get_demo_zero_result_alerts(days)
    with _analytics_conn() as conn:
        if not conn.open:
            return []
        _ensure_table(conn)
        df = conn.execute(
            """
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
            """,
            (days,),
        ).fetchall_as_pandas()
    return df.to_dict('records') if df is not None and not df.empty else []
