"""User preferences and personalization functions."""

import os
import logging
import streamlit as st
from src.db.duckdb_adapter import _duckdb_available, _db_write_lock
from src.db.queries import get_db_connection

def _user_oid() -> str:
    """Return a stable identifier for the current user (OID or email fallback)."""
    return st.session_state.get("user_oid") or st.session_state.get("user_email") or "anonymous"


def _pref_upsert(table_full_name: str, pref_type: str) -> None:
    """Write or refresh a bookmark/recent entry in user_data.user_preferences."""
    if not _duckdb_available():
        return
    try:
        con = get_db_connection()
        with _db_write_lock:
            con.execute(
                """
                INSERT INTO user_data.user_preferences (user_oid, table_full_name, pref_type, last_interacted)
                VALUES (?, ?, ?, now())
                ON CONFLICT (user_oid, table_full_name, pref_type) DO UPDATE
                    SET last_interacted = excluded.last_interacted
                """,
                [_user_oid(), table_full_name, pref_type],
            )
    except Exception as _e:
        logging.warning("Could not write user preference: %s", _e)


def _pref_delete(table_full_name: str, pref_type: str) -> None:
    """Remove a bookmark entry from user_data.user_preferences."""
    if not _duckdb_available():
        return
    try:
        con = get_db_connection()
        with _db_write_lock:
            con.execute(
                "DELETE FROM user_data.user_preferences WHERE user_oid=? AND table_full_name=? AND pref_type=?",
                [_user_oid(), table_full_name, pref_type],
            )
    except Exception as _e:
        logging.warning("Could not delete user preference: %s", _e)


def _pref_load(pref_type: str, limit: int = 20) -> list[str]:
    """Return table_full_name list for the given pref_type, newest first."""
    if not _duckdb_available():
        return []
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_full_name FROM user_data.user_preferences
                WHERE user_oid=%(oid)s AND pref_type=%(type)s
                ORDER BY last_interacted DESC LIMIT %(lim)s
                """,
                {"oid": _user_oid(), "type": pref_type, "lim": limit},
            )
            rows = cursor.fetchall_as_pandas()
            if rows is not None and not rows.empty:
                return rows["table_full_name"].tolist()
    except Exception as _e:
        logging.warning("Could not load user preferences: %s", _e)
    return []


def _sync_prefs_to_session() -> None:
    """Populate in-memory sets from DuckDB on first load (or after rerun)."""
    bookmarks = _pref_load("bookmark")
    st.session_state.bookmarks = set(bookmarks)
    col_bookmarks = _pref_load("col_bookmark")
    st.session_state.col_bookmarks = set(col_bookmarks)
    recent = _pref_load("recent", limit=50)
    st.session_state.recent_views = recent


def is_power_user() -> bool:
    """True if the current user belongs to at least one EDITOR_GROUPS group."""
    editor_groups = {g.strip() for g in os.getenv("EDITOR_GROUPS", "").split(",") if g.strip()}
    if not editor_groups:
        return False
    return bool(editor_groups & set(st.session_state.get("user_groups", [])))
