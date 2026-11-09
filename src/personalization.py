"""User preferences and personalization functions.

Each storage helper branches on ``is_demo_mode()``: demo mode is a no-op
(preferences live only in ``st.session_state``; site settings fall back to
their defaults), otherwise rows persist to ``user_data.user_preferences`` /
``user_data.site_settings`` in DuckDB. This module owns the higher-level
concerns:

- resolving the current user's stable id (oid → email → 'anonymous')
- syncing DB-backed preferences into ``st.session_state`` on first load
- the editing-toggle session cache (avoids a DB hit per render)
- ``is_power_user()`` — combines the toggle with EDITOR_GROUPS membership
"""
from __future__ import annotations
from typing import Optional

import logging
import os

import streamlit as st

from src.auth import is_admin, _parse_groups
from src.config import is_demo_mode
from src.db.duckdb_adapter import _db_write_lock
from src.db.queries import _get_write_connection, get_db_connection

log = logging.getLogger(__name__)


def _user_oid() -> str:
    """Return a stable identifier for the current user (OID or email fallback)."""
    return (
        st.session_state.get("user_oid")
        or st.session_state.get("user_email")
        or "anonymous"
    )


def _pref_upsert(table_full_name: str, pref_type: str) -> None:
    """Write or refresh a bookmark/recent entry.

    Demo mode is a no-op — preferences are kept only in ``st.session_state``
    (managed by the callers); there's nowhere persistent to write to.
    """
    if is_demo_mode():
        return
    try:
        conn = get_db_connection()
        with _db_write_lock:
            conn.execute(
                """
                INSERT INTO user_data.user_preferences
                    (user_oid, table_full_name, pref_type, last_interacted)
                VALUES (?, ?, ?, now())
                ON CONFLICT (user_oid, table_full_name, pref_type) DO UPDATE
                    SET last_interacted = excluded.last_interacted
                """,
                [_user_oid(), table_full_name, pref_type],
            )
    except Exception as exc:
        log.warning("Could not write user preference: %s", exc)


def _pref_delete(table_full_name: str, pref_type: str) -> None:
    """Remove a bookmark entry."""
    if is_demo_mode():
        return
    try:
        conn = get_db_connection()
        with _db_write_lock:
            conn.execute(
                "DELETE FROM user_data.user_preferences "
                "WHERE user_oid=? AND table_full_name=? AND pref_type=?",
                [_user_oid(), table_full_name, pref_type],
            )
    except Exception as exc:
        log.warning("Could not delete user preference: %s", exc)


def _pref_load(pref_type: str, limit: int = 20) -> list[str]:
    """Return table_full_name list for the given pref_type, newest first."""
    if is_demo_mode():
        return []
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_full_name FROM user_data.user_preferences
                WHERE user_oid=%(oid)s AND pref_type=%(type)s
                ORDER BY last_interacted DESC LIMIT %(lim)s
                """,
                {"oid": _user_oid(), "type": pref_type, "lim": limit},
            )
            rows = cur.fetchall_as_pandas()
            if rows is not None and not rows.empty:
                return rows["table_full_name"].tolist()
    except Exception as exc:
        log.warning("Could not load user preferences: %s", exc)
    return []


def _sync_prefs_to_session() -> None:
    """Populate in-memory sets from the storage backend on first load."""
    st.session_state.bookmarks = set(_pref_load("bookmark"))
    st.session_state.col_bookmarks = set(_pref_load("col_bookmark"))
    st.session_state.recent_views = _pref_load("recent", limit=50)


_EDITING_ENABLED_KEY = "editing_enabled"


def _get_site_setting(key: str) -> Optional[str]:
    """Read a global key/value setting; None when unset or in demo mode."""
    if is_demo_mode():
        return None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT value FROM user_data.site_settings WHERE key = ?",
                [key],
            )
            rows = cur.fetchall()
            if rows:
                return str(rows[0][0])
    except Exception as exc:
        log.warning("Could not read site_settings[%s]: %s", key, exc)
    return None


def _set_site_setting(key: str, value: str, actor_email: str) -> None:
    """Upsert a global key/value setting; silently dropped in demo mode."""
    if is_demo_mode():
        return
    try:
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                """
                INSERT INTO user_data.site_settings
                    (key, value, updated_at, updated_by)
                VALUES (?, ?, current_localtimestamp(), ?)
                ON CONFLICT (key) DO UPDATE
                    SET value      = excluded.value,
                        updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by
                """,
                [key, value, actor_email],
            )
    except Exception as exc:
        log.warning("Could not persist site_settings[%s]: %s", key, exc)


def is_editing_enabled() -> bool:
    """Return True if inline metadata editing is globally enabled (admin toggle).

    Result is cached in ``st.session_state`` to avoid a DB hit per render.
    Callers that mutate the flag (``set_editing_enabled``) refresh the
    cache so the toggle feels instant.
    """
    if "_editing_enabled_cache" in st.session_state:
        return st.session_state["_editing_enabled_cache"]

    raw = _get_site_setting(_EDITING_ENABLED_KEY)
    enabled = True if raw is None else raw == "1"  # default: enabled
    st.session_state["_editing_enabled_cache"] = enabled
    return enabled


def set_editing_enabled(enabled: bool, actor_email: str = "admin") -> None:
    """Persist the global editing toggle and invalidate the session cache."""
    if not is_admin():
        raise PermissionError("Only admins can toggle the editing flag.")
    _set_site_setting(_EDITING_ENABLED_KEY, "1" if enabled else "0", actor_email)
    # Always update cache so the toggle feels instant, even when the
    # backend is a no-op (demo mode).
    st.session_state["_editing_enabled_cache"] = enabled


def is_power_user() -> bool:
    """True if editing is globally enabled AND the user belongs to an EDITOR_GROUPS group."""
    if not is_editing_enabled():
        return False
    editor_groups = _parse_groups(os.getenv("EDITOR_GROUPS", ""))
    if not editor_groups:
        return False
    return not editor_groups.isdisjoint(st.session_state.get("user_groups", []))
