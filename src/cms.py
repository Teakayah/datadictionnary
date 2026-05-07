"""CMS data layer — admin-authored posts shown as a banner on the Discovery tab."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import streamlit as st

from src.db.duckdb_adapter import _duckdb_available, _db_write_lock
from src.db.queries import get_db_connection, _get_write_connection

POST_TYPES = ("announcement", "featured_table", "guide")

_EXPIRY_DAYS: dict[str, int | None] = {
    "2 days":  2,
    "7 days":  7,
    "30 days": 30,
    "Never":   None,
}


def get_active_posts() -> list[dict]:
    """Return all non-expired CMS posts, newest first."""
    if not _duckdb_available():
        now = datetime.now(UTC)
        return [
            p for p in st.session_state.get("_demo_cms_posts", [])
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
            rows = cur.fetchall()
            return [
                {
                    "post_id":      r[0],
                    "post_type":    r[1],
                    "title":        r[2],
                    "body":         r[3],
                    "table_ref":    r[4],
                    "author_email": r[5],
                    "created_at":   r[6],
                    "expires_at":   r[7],
                }
                for r in (rows or [])
            ]
    except Exception as _e:
        logging.warning("Could not load CMS posts: %s", _e)
        return []


def get_all_posts() -> list[dict]:
    """Return all CMS posts (including expired), newest first — for admin view."""
    if not _duckdb_available():
        return st.session_state.get("_demo_cms_posts", [])
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
            rows = cur.fetchall()
            return [
                {
                    "post_id":      r[0],
                    "post_type":    r[1],
                    "title":        r[2],
                    "body":         r[3],
                    "table_ref":    r[4],
                    "author_email": r[5],
                    "created_at":   r[6],
                    "expires_at":   r[7],
                }
                for r in (rows or [])
            ]
    except Exception as _e:
        logging.warning("Could not load CMS posts (admin): %s", _e)
        return []


def create_post(
    post_type: str,
    title: str,
    body: str,
    table_ref: str | None,
    author_email: str,
    expiry_days: int | None,
) -> None:
    post_id   = str(uuid.uuid4())
    now       = datetime.now(UTC)
    expires   = (now + timedelta(days=expiry_days)) if expiry_days is not None else None

    if not _duckdb_available():
        posts = st.session_state.setdefault("_demo_cms_posts", [])
        posts.insert(0, {
            "post_id":      post_id,
            "post_type":    post_type,
            "title":        title,
            "body":         body,
            "table_ref":    table_ref or None,
            "author_email": author_email,
            "created_at":   now,
            "expires_at":   expires,
        })
        return

    try:
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                """
                INSERT INTO user_data.cms_posts
                    (post_id, post_type, title, body, table_ref,
                     author_email, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [post_id, post_type, title, body or None,
                 table_ref or None, author_email, now, expires],
            )
    except Exception as _e:
        logging.error("Could not create CMS post: %s", _e)
        raise


def delete_post(post_id: str) -> None:
    if not _duckdb_available():
        posts = st.session_state.get("_demo_cms_posts", [])
        st.session_state["_demo_cms_posts"] = [p for p in posts if p["post_id"] != post_id]
        return
    try:
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                "DELETE FROM user_data.cms_posts WHERE post_id = ?",
                [post_id],
            )
    except Exception as _e:
        logging.error("Could not delete CMS post: %s", _e)
        raise
