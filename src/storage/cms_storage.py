from __future__ import annotations
from typing import Optional, Protocol, runtime_checkable
"""CMS storage backends.

Three implementations against the same Protocol:

* ``DemoCMSStorage``   — Streamlit session-state-backed, used when DuckDB
                         is unavailable (demo mode or no ``DUCKDB_PATH``).
* ``DuckDBCMSStorage`` — production backend, persists to
                         ``user_data.cms_posts``.
* ``FakeCMSStorage``   — test-only in-memory backend that doesn't depend
                         on Streamlit. Inject via ``mock.patch`` of
                         ``src.cms.get_cms_storage``.

The Protocol is structural — any class that implements the four methods
satisfies it. ``runtime_checkable`` lets ``isinstance(x, CMSStorage)``
work in tests.
"""


import logging
from datetime import datetime, timezone; UTC = timezone.utc

import streamlit as st

from src.db.duckdb_adapter import _db_write_lock
from src.db.queries import _get_write_connection, get_db_connection

log = logging.getLogger(__name__)

# Single source of truth for the post column order, used by DuckDB row-tuple
# unpacking and by clients that need to know the dict shape.
_POST_COLUMNS = (
    "post_id", "post_type", "title", "body", "table_ref",
    "author_email", "created_at", "expires_at",
)


def _row_to_post(row) -> dict:
    """Convert a DuckDB row tuple to a post dict using ``_POST_COLUMNS``."""
    return dict(zip(_POST_COLUMNS, row))


@runtime_checkable
class CMSStorage(Protocol):
    """Backend protocol for CMS posts."""

    def list_active(self) -> list[dict]:
        """Return all non-expired posts, newest first."""
        ...

    def list_all(self) -> list[dict]:
        """Return every post (including expired), newest first."""
        ...

    def create(self, post: dict) -> None:
        """Persist a new post. Caller is responsible for ``post_id`` /
        ``created_at`` / ``expires_at``."""
        ...

    def delete(self, post_id: str) -> None:
        """Remove a post by id. Idempotent — missing ids are a no-op."""
        ...


# ── Session-state backend (demo mode, no DuckDB) ─────────────────────────────

class DemoCMSStorage:
    """Streamlit session-state-backed CMS storage.

    Posts live in ``st.session_state['_demo_cms_posts']``. State is
    per-session, so each browser tab sees its own set of posts —
    appropriate for demo / local dev, not for multi-user production.
    """

    _KEY = "_demo_cms_posts"

    def list_active(self) -> list[dict]:
        now = datetime.now(UTC)
        return [
            p for p in st.session_state.get(self._KEY, [])
            if p.get("expires_at") is None or p["expires_at"] > now
        ]

    def list_all(self) -> list[dict]:
        return list(st.session_state.get(self._KEY, []))

    def create(self, post: dict) -> None:
        st.session_state.setdefault(self._KEY, []).insert(0, dict(post))

    def delete(self, post_id: str) -> None:
        posts = st.session_state.get(self._KEY, [])
        st.session_state[self._KEY] = [p for p in posts if p["post_id"] != post_id]


# ── DuckDB backend ───────────────────────────────────────────────────────────

class DuckDBCMSStorage:
    """Persistent CMS storage backed by ``user_data.cms_posts``."""

    def list_active(self) -> list[dict]:
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT post_id, post_type, title, body, table_ref,
                           author_email, created_at, expires_at
                    FROM user_data.cms_posts
                    WHERE expires_at IS NULL OR expires_at > current_localtimestamp()
                    ORDER BY created_at DESC
                    """
                )
                return [_row_to_post(r) for r in (cur.fetchall() or [])]
        except Exception as exc:
            log.warning("Could not load CMS posts: %s", exc)
            return []

    def list_all(self) -> list[dict]:
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT post_id, post_type, title, body, table_ref,
                           author_email, created_at, expires_at
                    FROM user_data.cms_posts
                    ORDER BY created_at DESC
                    """
                )
                return [_row_to_post(r) for r in (cur.fetchall() or [])]
        except Exception as exc:
            log.warning("Could not load CMS posts (admin): %s", exc)
            return []

    def create(self, post: dict) -> None:
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                """
                INSERT INTO user_data.cms_posts
                    (post_id, post_type, title, body, table_ref,
                     author_email, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [post["post_id"], post["post_type"], post["title"],
                 post["body"] or None, post["table_ref"] or None,
                 post["author_email"], post["created_at"], post["expires_at"]],
            )

    def delete(self, post_id: str) -> None:
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                "DELETE FROM user_data.cms_posts WHERE post_id = ?",
                [post_id],
            )


# ── Test-only backend ────────────────────────────────────────────────────────

class FakeCMSStorage:
    """In-memory CMS storage for unit tests.

    Identical semantics to ``DemoCMSStorage`` but uses an instance dict
    instead of Streamlit session state, so tests don't need a Streamlit
    runtime to exercise the storage protocol.
    """

    def __init__(self, posts: Optional[list[dict]] = None) -> None:
        self.posts: list[dict] = list(posts or [])

    def list_active(self) -> list[dict]:
        now = datetime.now(UTC)
        return [
            p for p in self.posts
            if p.get("expires_at") is None or p["expires_at"] > now
        ]

    def list_all(self) -> list[dict]:
        return list(self.posts)

    def create(self, post: dict) -> None:
        self.posts.insert(0, dict(post))

    def delete(self, post_id: str) -> None:
        self.posts = [p for p in self.posts if p["post_id"] != post_id]
