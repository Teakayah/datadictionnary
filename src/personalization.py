from __future__ import annotations
"""User preferences and personalization functions.

Storage is delegated to ``src.storage`` — see ``PreferenceStorage`` and
``SiteSettingStorage``. This module owns the higher-level concerns:

- resolving the current user's stable id (oid → email → 'anonymous')
- syncing DB-backed preferences into ``st.session_state`` on first load
- the editing-toggle session cache (avoids a DB hit per render)
- ``is_power_user()`` — combines the toggle with EDITOR_GROUPS membership
"""

import logging
import os

import streamlit as st

from src.auth import is_admin, _parse_groups
from src.storage import get_preference_storage, get_site_setting_storage

log = logging.getLogger(__name__)


def _user_oid() -> str:
    """Return a stable identifier for the current user (OID or email fallback)."""
    return (
        st.session_state.get("user_oid")
        or st.session_state.get("user_email")
        or "anonymous"
    )


def _pref_upsert(table_full_name: str, pref_type: str) -> None:
    """Write or refresh a bookmark/recent entry."""
    get_preference_storage().upsert(_user_oid(), table_full_name, pref_type)


def _pref_delete(table_full_name: str, pref_type: str) -> None:
    """Remove a bookmark entry."""
    get_preference_storage().delete(_user_oid(), table_full_name, pref_type)


def _pref_load(pref_type: str, limit: int = 20) -> list[str]:
    """Return table_full_name list for the given pref_type, newest first."""
    return get_preference_storage().list_by_type(_user_oid(), pref_type, limit=limit)


def _sync_prefs_to_session() -> None:
    """Populate in-memory sets from the storage backend on first load."""
    st.session_state.bookmarks = set(_pref_load("bookmark"))
    st.session_state.col_bookmarks = set(_pref_load("col_bookmark"))
    st.session_state.recent_views = _pref_load("recent", limit=50)


_EDITING_ENABLED_KEY = "editing_enabled"


def is_editing_enabled() -> bool:
    """Return True if inline metadata editing is globally enabled (admin toggle).

    Result is cached in ``st.session_state`` to avoid a DB hit per render.
    Callers that mutate the flag (``set_editing_enabled``) refresh the
    cache so the toggle feels instant.
    """
    if "_editing_enabled_cache" in st.session_state:
        return st.session_state["_editing_enabled_cache"]

    raw = get_site_setting_storage().get(_EDITING_ENABLED_KEY)
    enabled = True if raw is None else raw == "1"  # default: enabled
    st.session_state["_editing_enabled_cache"] = enabled
    return enabled


def set_editing_enabled(enabled: bool, actor_email: str = "admin") -> None:
    """Persist the global editing toggle and invalidate the session cache."""
    if not is_admin():
        raise PermissionError("Only admins can toggle the editing flag.")
    get_site_setting_storage().set(
        _EDITING_ENABLED_KEY, "1" if enabled else "0", actor_email,
    )
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
    return bool(editor_groups & set(st.session_state.get("user_groups", [])))
