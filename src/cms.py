"""CMS data layer — admin-authored posts shown as a banner on the Discovery tab.

Thin wrappers over a ``CMSStorage`` backend; the backend is picked at call
time by ``src.storage.get_cms_storage()`` based on demo mode and DuckDB
availability. Public function signatures are preserved so callers
(``src/ui/cards/cms_admin.py``, ``src/ui/cards/discovery.py``) don't change.

Adding a new CMS field: update the ``post`` dict in ``create_post`` and
``_POST_COLUMNS`` in ``src.storage.cms_storage``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from src.storage import get_cms_storage

POST_TYPES = ("announcement", "featured_table", "guide")

_EXPIRY_DAYS: dict[str, int | None] = {
    "2 days":  2,
    "7 days":  7,
    "30 days": 30,
    "Never":   None,
}


def get_active_posts() -> list[dict]:
    """Return all non-expired CMS posts, newest first."""
    return get_cms_storage().list_active()


def get_all_posts() -> list[dict]:
    """Return all CMS posts (including expired), newest first — for admin view."""
    return get_cms_storage().list_all()


def create_post(
    post_type: str,
    title: str,
    body: str,
    table_ref: str | None,
    author_email: str,
    expiry_days: int | None,
) -> None:
    """Persist a new CMS post.

    Storage backend chooses how to durable-ify it (DuckDB row vs session
    state). Errors propagate so the caller can show a Streamlit error.
    """
    now = datetime.now(UTC)
    post = {
        "post_id":      str(uuid.uuid4()),
        "post_type":    post_type,
        "title":        title,
        "body":         body or None,
        "table_ref":    table_ref or None,
        "author_email": author_email,
        "created_at":   now,
        "expires_at":   (
            now + timedelta(days=expiry_days)
            if expiry_days is not None
            else None
        ),
    }
    try:
        get_cms_storage().create(post)
    except Exception as exc:
        logging.error("Could not create CMS post: %s", exc)
        raise


def delete_post(post_id: str) -> None:
    """Remove a CMS post by id. Errors propagate."""
    try:
        get_cms_storage().delete(post_id)
    except Exception as exc:
        logging.error("Could not delete CMS post: %s", exc)
        raise
