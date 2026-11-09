"""Public API for in-app bookmark-change notifications.

The sync daemon writes notification rows when a bookmarked table is
modified (TABLE_DESC, COLUMN_DEF, or STEWARD sync succeeds — see
``src/sync/push.py::_notify_bookmarkers``). This module exposes the
read/dismiss surface used by the Streamlit UI.

Demo mode keeps notifications in ``st.session_state['_demo_notifications']``
(no persistence across reloads); otherwise rows live in
``user_data.notifications`` (DuckDB).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.config import is_demo_mode

log = logging.getLogger(__name__)

_DEMO_KEY = "_demo_notifications"


def _demo_store() -> dict[str, dict]:
    import streamlit as st
    if _DEMO_KEY not in st.session_state:
        st.session_state[_DEMO_KEY] = {}
    return st.session_state[_DEMO_KEY]


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_unread_notifications(user_oid: str, limit: int = 20) -> list[dict]:
    """Return unread notifications for user_oid, newest first.

    Each dict has: notification_id, table_full_name, change_type,
    changed_by, summary, created_at.
    """
    if is_demo_mode():
        return [
            {k: v for k, v in n.items() if k not in ("user_oid", "read_at")}
            for n in reversed(list(_demo_store().values()))
            if n["user_oid"] == user_oid and n["read_at"] is None
        ][:limit]
    try:
        from src.db.queries import get_db_connection
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT notification_id, table_full_name, change_type,
                       changed_by, summary, created_at
                FROM user_data.notifications
                WHERE user_oid = ? AND read_at IS NULL
                ORDER BY created_at DESC
                LIMIT ?
                """,
                [user_oid, limit],
            )
            rows = cur.fetchall()
        return [
            {
                "notification_id": r[0],
                "table_full_name": r[1],
                "change_type": r[2],
                "changed_by": r[3],
                "summary": r[4],
                "created_at": r[5],
            }
            for r in (rows or [])
        ]
    except Exception as exc:
        log.warning("Could not list notifications for %s: %s", user_oid, exc)
        return []


def mark_read(notification_id: str) -> None:
    """Dismiss a single notification."""
    if is_demo_mode():
        store = _demo_store()
        if notification_id in store:
            store[notification_id]["read_at"] = _now()
        return
    try:
        from src.db.duckdb_adapter import _db_write_lock
        from src.db.queries import _get_write_connection
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                "UPDATE user_data.notifications SET read_at = ? WHERE notification_id = ?",
                [_now(), notification_id],
            )
    except Exception as exc:
        log.warning("Could not mark notification %s read: %s", notification_id, exc)


def mark_all_read(user_oid: str) -> None:
    """Dismiss all unread notifications for a user."""
    if is_demo_mode():
        now = _now()
        for n in _demo_store().values():
            if n["user_oid"] == user_oid and n["read_at"] is None:
                n["read_at"] = now
        return
    try:
        from src.db.duckdb_adapter import _db_write_lock
        from src.db.queries import _get_write_connection
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                "UPDATE user_data.notifications SET read_at = ? "
                "WHERE user_oid = ? AND read_at IS NULL",
                [_now(), user_oid],
            )
    except Exception as exc:
        log.warning("Could not mark all notifications read for %s: %s", user_oid, exc)
