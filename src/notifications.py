from __future__ import annotations
"""Public API for in-app bookmark-change notifications.

The sync daemon writes notification rows when a bookmarked table is
modified (TABLE_DESC, COLUMN_DEF, or STEWARD sync succeeds). This module
exposes the read/dismiss surface used by the Streamlit UI.
"""

from src.storage import get_notification_storage


def get_unread_notifications(user_oid: str, limit: int = 20) -> list[dict]:
    """Return unread notifications for user_oid, newest first.

    Each dict has: notification_id, table_full_name, change_type,
    changed_by, summary, created_at.
    """
    return get_notification_storage().list_unread(user_oid, limit=limit)


def mark_read(notification_id: str) -> None:
    """Dismiss a single notification."""
    get_notification_storage().mark_read(notification_id)


def mark_all_read(user_oid: str) -> None:
    """Dismiss all unread notifications for a user."""
    get_notification_storage().mark_all_read(user_oid)
