from __future__ import annotations
from typing import Any, Callable, Optional, Protocol, runtime_checkable
"""User preferences and site-settings storage backends.

Two related entities, one module:

* ``PreferenceStorage``  ↔ ``user_data.user_preferences``  (per-user bookmarks
                          + recent-views; rows scoped by ``user_oid``).
* ``SiteSettingStorage`` ↔ ``user_data.site_settings``     (global key/value;
                          editing toggle, daemon heartbeat, etc.).

Demo backends are deliberate no-ops — current behaviour pre-refactor was
that demo mode silently lost preferences on session restart and silently
fell back to defaults for site settings. The Fake variants are
session-free in-memory dicts for unit tests.
"""


import logging

from src.db.duckdb_adapter import _db_write_lock
from src.db.queries import _get_write_connection, get_db_connection

log = logging.getLogger(__name__)


# ── User preferences ─────────────────────────────────────────────────────────

@runtime_checkable
class PreferenceStorage(Protocol):
    """CRUD for per-user bookmarks / recent-views.

    pref_type is one of ``"bookmark"``, ``"col_bookmark"``, ``"recent"``.
    """

    def upsert(self, user_oid: str, table_full_name: str, pref_type: str) -> None: ...
    def delete(self, user_oid: str, table_full_name: str, pref_type: str) -> None: ...
    def list_by_type(self, user_oid: str, pref_type: str, limit: int = 20) -> list[str]: ...


class DemoPreferenceStorage:
    """No-op preference storage used when DuckDB is unavailable.

    Matches pre-refactor behaviour: in demo mode preferences are kept only
    in ``st.session_state`` (managed by ``src.personalization``); this
    backend doesn't need to do anything because there's nowhere persistent
    to write to.
    """

    def upsert(self, user_oid: str, table_full_name: str, pref_type: str) -> None:
        return None

    def delete(self, user_oid: str, table_full_name: str, pref_type: str) -> None:
        return None

    def list_by_type(self, user_oid: str, pref_type: str, limit: int = 20) -> list[str]:
        return []


class DuckDBPreferenceStorage:
    def upsert(self, user_oid: str, table_full_name: str, pref_type: str) -> None:
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
                    [user_oid, table_full_name, pref_type],
                )
        except Exception as exc:
            log.warning("Could not write user preference: %s", exc)

    def delete(self, user_oid: str, table_full_name: str, pref_type: str) -> None:
        try:
            conn = get_db_connection()
            with _db_write_lock:
                conn.execute(
                    "DELETE FROM user_data.user_preferences "
                    "WHERE user_oid=? AND table_full_name=? AND pref_type=?",
                    [user_oid, table_full_name, pref_type],
                )
        except Exception as exc:
            log.warning("Could not delete user preference: %s", exc)

    def list_by_type(self, user_oid: str, pref_type: str, limit: int = 20) -> list[str]:
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_full_name FROM user_data.user_preferences
                    WHERE user_oid=%(oid)s AND pref_type=%(type)s
                    ORDER BY last_interacted DESC LIMIT %(lim)s
                    """,
                    {"oid": user_oid, "type": pref_type, "lim": limit},
                )
                rows = cur.fetchall_as_pandas()
                if rows is not None and not rows.empty:
                    return rows["table_full_name"].tolist()
        except Exception as exc:
            log.warning("Could not load user preferences: %s", exc)
        return []


class FakePreferenceStorage:
    """In-memory backend for unit tests."""

    def __init__(self) -> None:
        # (user_oid, pref_type) → list[(table_full_name, ts)]
        # Not a dict-of-dicts; stored as ordered list so list_by_type can
        # iterate deterministically.
        self._items: list[dict] = []

    def upsert(self, user_oid: str, table_full_name: str, pref_type: str) -> None:
        # Drop any existing entry for the same key, then append (newest last).
        self._items = [
            i for i in self._items
            if not (i["user_oid"] == user_oid
                    and i["table_full_name"] == table_full_name
                    and i["pref_type"] == pref_type)
        ]
        self._items.append({
            "user_oid": user_oid,
            "table_full_name": table_full_name,
            "pref_type": pref_type,
        })

    def delete(self, user_oid: str, table_full_name: str, pref_type: str) -> None:
        self._items = [
            i for i in self._items
            if not (i["user_oid"] == user_oid
                    and i["table_full_name"] == table_full_name
                    and i["pref_type"] == pref_type)
        ]

    def list_by_type(self, user_oid: str, pref_type: str, limit: int = 20) -> list[str]:
        # Newest first → reverse insertion order.
        matching = [
            i["table_full_name"] for i in self._items
            if i["user_oid"] == user_oid and i["pref_type"] == pref_type
        ]
        return list(reversed(matching))[:limit]


# ── Site settings (global key/value) ─────────────────────────────────────────

@runtime_checkable
class SiteSettingStorage(Protocol):
    """Global key/value store. Today: editing_enabled flag, daemon
    heartbeat, dr_resync_status."""

    def get(self, key: str) -> Optional[str]: ...
    def set(self, key: str, value: str, actor_email: str) -> None: ...


class DemoSiteSettingStorage:
    """No-op site-settings storage used when DuckDB is unavailable.

    ``get`` always returns ``None`` so callers fall back to their default;
    ``set`` is silently dropped. This preserves pre-refactor behaviour
    where in-process state (``st.session_state`` cache) was the only
    runtime-mutable knob without DuckDB.
    """

    def get(self, key: str) -> Optional[str]:
        return None

    def set(self, key: str, value: str, actor_email: str) -> None:
        return None


class DuckDBSiteSettingStorage:
    def get(self, key: str) -> Optional[str]:
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

    def set(self, key: str, value: str, actor_email: str) -> None:
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


class FakeSiteSettingStorage:
    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self.values: dict[str, str] = dict(initial or {})

    def get(self, key: str) -> Optional[str]:
        return self.values.get(key)

    def set(self, key: str, value: str, actor_email: str) -> None:
        self.values[key] = value
