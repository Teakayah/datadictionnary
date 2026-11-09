from __future__ import annotations
"""CMS data layer — admin-authored posts shown as a banner on the Discovery tab.

Each function branches on ``is_demo_mode()``: demo mode keeps posts in
``st.session_state['_demo_cms_posts']`` (per-session, appropriate for demo /
local dev), otherwise rows persist to ``user_data.cms_posts`` in DuckDB.
Public function signatures are preserved so callers
(``src/ui/cards/cms_admin.py``, ``src/ui/cards/discovery.py``) don't change.

Adding a new CMS field: update the ``post`` dict in ``create_post`` and
``_POST_COLUMNS`` below.
"""


import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC; UTC = UTC

import streamlit as st

from src.auth import is_admin
from src.config import is_demo_mode
from src.db.duckdb_adapter import _db_write_lock
from src.db.queries import _get_write_connection, get_db_connection

_EXPIRY_DAYS: dict[str, int | None] = {
    "2_days":  2,
    "7_days":  7,
    "30_days": 30,
    "never":   None,
}

_DEMO_KEY = "_demo_cms_posts"

# Single source of truth for the post column order, used by DuckDB row-tuple
# unpacking and by clients that need to know the dict shape.
_POST_COLUMNS = (
    "post_id", "post_type", "title", "body", "table_ref",
    "author_email", "created_at", "expires_at",
)


def get_active_posts() -> list[dict]:
    """Return all non-expired CMS posts, newest first."""
    if is_demo_mode():
        now = datetime.now(UTC)
        return [
            p for p in st.session_state.get(_DEMO_KEY, [])
            if p.get("expires_at") is None or p["expires_at"] > now
        ]
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
            return [dict(zip(_POST_COLUMNS, r)) for r in (cur.fetchall() or [])]
    except Exception as exc:
        logging.warning("Could not load CMS posts: %s", exc)
        return []


def get_all_posts() -> list[dict]:
    """Return all CMS posts (including expired), newest first — for admin view."""
    if is_demo_mode():
        return list(st.session_state.get(_DEMO_KEY, []))
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
            return [dict(zip(_POST_COLUMNS, r)) for r in (cur.fetchall() or [])]
    except Exception as exc:
        logging.warning("Could not load CMS posts (admin): %s", exc)
        return []



@dataclass
class PostParams:
    post_type: str
    title: str
    body: str
    table_ref: str | None
    author_email: str
    expiry_days: int | None

def create_post(params: PostParams) -> None:
    """Persist a new CMS post.

    Demo mode keeps it in session state; otherwise a DuckDB row. Errors
    propagate so the caller can show a Streamlit error.
    """
    if not is_admin():
        raise PermissionError("Only admins can create CMS posts.")
    now = datetime.now(UTC)
    post = {
        "post_id":      str(uuid.uuid4()),
        "post_type":    params.post_type,
        "title":        params.title,
        "body":         params.body or None,
        "table_ref":    params.table_ref or None,
        "author_email": params.author_email,
        "created_at":   now,
        "expires_at":   (
            now + timedelta(days=params.expiry_days)
            if params.expiry_days is not None
            else None
        ),
    }
    try:
        if is_demo_mode():
            st.session_state.setdefault(_DEMO_KEY, []).insert(0, post)
            return
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
                 post["body"], post["table_ref"],
                 post["author_email"], post["created_at"], post["expires_at"]],
            )
    except Exception as exc:
        logging.error("Could not create CMS post: %s", exc)
        raise


def delete_post(post_id: str) -> None:
    """Remove a CMS post by id. Idempotent — missing ids are a no-op. Errors propagate."""
    if not is_admin():
        raise PermissionError("Only admins can delete CMS posts.")
    try:
        if is_demo_mode():
            posts = st.session_state.get(_DEMO_KEY, [])
            st.session_state[_DEMO_KEY] = [
                p for p in posts if p["post_id"] != post_id
            ]
            return
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                "DELETE FROM user_data.cms_posts WHERE post_id = ?",
                [post_id],
            )
    except Exception as exc:
        logging.error("Could not delete CMS post: %s", exc)
        raise
