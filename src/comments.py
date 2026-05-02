"""Comments and discussions functionality."""

import os
import logging
import uuid
import streamlit as st

from src.config import CATALOG_CACHE, SCHEMA_CACHE, is_demo_mode
from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import _get_write_connection, get_db_connection
from src.sync.push import enqueue_sync

def get_table_comments(object_name: str) -> list:
    """Fetch all comments for an object, returned as a tree (parent comments
    with a ``replies`` list each).

    In demo mode reads from st.session_state["demo_comments"].
    Not cached — always fresh so new comments appear immediately.
    """
    if is_demo_mode():
        flat = st.session_state.get("demo_comments", {}).get(object_name, [])
        return _build_comment_tree(flat)
    try:
        conn = get_db_connection()
        tbl = "user_data.comments" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.comments"
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT comment_id, author_name, author_email, comment_text, created_at, parent_comment_id "
                f"FROM {tbl} "
                f"WHERE object_name = %(object_name)s ORDER BY created_at ASC",
                {"object_name": object_name},
            )
            rows = cursor.fetchall_as_pandas()
            if rows is not None and not rows.empty:
                return _build_comment_tree(rows.to_dict(orient="records"))
    except Exception as e:
        logging.warning("Could not fetch comments for %s: %s", object_name, e)
    return []


def _build_comment_tree(flat: list) -> list:
    """Group a flat list of comment dicts into a parent/replies tree."""
    by_id = {c["comment_id"]: {**c, "replies": []} for c in flat}
    roots = []
    for c in by_id.values():
        pid = c.get("parent_comment_id")
        if pid and pid in by_id:
            by_id[pid]["replies"].append(c)
        else:
            roots.append(c)
    return roots


def send_comment_email(to_email: str, author_name: str, object_name: str, comment_text: str) -> None:
    """Send a comment notification email to the data steward.

    In demo mode logs to console instead of sending. Silently skips if
    SMTP_HOST or to_email is not configured rather than raising.
    """
    import smtplib
    from email.mime.text import MIMEText

    if is_demo_mode():
        print(f"[DEMO EMAIL] To: {to_email} | Object: {object_name} | From: {author_name}\n{comment_text}")
        return
    smtp_host = os.getenv("SMTP_HOST", "")
    if not smtp_host or not to_email:
        logging.warning("Comment saved but email not sent: SMTP_HOST or steward_email not configured.")
        return
    # Strip newlines from header fields to prevent SMTP header injection.
    safe_object_name = object_name.replace("\r", "").replace("\n", "")
    safe_author_name = author_name.replace("\r", "").replace("\n", "")
    msg = MIMEText(f"{safe_author_name} left a comment on {safe_object_name}:\n\n{comment_text}", "plain")
    msg["Subject"] = f"[Data Dictionary] Comment on {safe_object_name}"
    msg["From"]    = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", ""))
    msg["To"]      = to_email
    try:
        with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", "587"))) as s:
            s.starttls()
            s.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
            s.sendmail(msg["From"], [to_email], msg.as_string())
        logging.info("Comment email sent to %s", to_email)
    except Exception as e:
        logging.error("Failed to send comment email to %s: %s", to_email, e)


def send_reply_email(
    parent_author_email: str,
    reply_author_name: str,
    object_name: str,
    reply_text: str,
    steward_email: str,
) -> None:
    """Notify the original commenter (and the steward if different) of a reply.

    In demo mode logs to console. Silently skips if SMTP_HOST is not configured.
    """
    import smtplib
    from email.mime.text import MIMEText

    recipients = list({e for e in [parent_author_email, steward_email] if e})
    if not recipients:
        return

    if is_demo_mode():
        print(f"[DEMO REPLY] To: {recipients} | Object: {object_name} | From: {reply_author_name}\n{reply_text}")
        return

    smtp_host = os.getenv("SMTP_HOST", "")
    if not smtp_host:
        logging.warning("Reply saved but email not sent: SMTP_HOST not configured.")
        return

    # Strip newlines from header fields to prevent SMTP header injection.
    safe_object_name  = object_name.replace("\r", "").replace("\n", "")
    safe_reply_author = reply_author_name.replace("\r", "").replace("\n", "")
    msg = MIMEText(
        f"{safe_reply_author} replied to a comment on {safe_object_name}:\n\n{reply_text}",
        "plain",
    )
    msg["Subject"] = f"[Data Dictionary] Reply on {safe_object_name}"
    msg["From"]    = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", ""))
    msg["To"]      = ", ".join(recipients)
    try:
        with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", "587"))) as s:
            s.starttls()
            s.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
            s.sendmail(msg["From"], recipients, msg.as_string())
        logging.info("Reply email sent to %s", recipients)
    except Exception as e:
        logging.error("Failed to send reply email to %s: %s", recipients, e)


def _fetch_comment_author_email(comment_id: str) -> str:
    """Look up the author_email of a comment from the DB."""
    try:
        conn = get_db_connection()
        tbl = "user_data.comments" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.comments"
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT author_email FROM {tbl} "
                f"WHERE comment_id = %(comment_id)s LIMIT 1",
                {"comment_id": comment_id},
            )
            row = cursor.fetchall_as_pandas()
            if row is not None and not row.empty:
                return str(row.iloc[0]["author_email"] or "")
    except Exception as e:
        logging.warning("Could not fetch author_email for comment %s: %s", comment_id, e)
    return ""


def save_comment(
    object_type: str,
    object_name: str,
    comment_text: str,
    steward_email: str,
    parent_comment_id: str = None,
    parent_author_email: str = "",
) -> None:
    """Persist a comment (or reply) and trigger notification emails."""
    comment_id   = str(uuid.uuid4())
    author_name  = st.session_state.get("user_name", "unknown")
    author_email = (st.session_state.get("user_email", "") or "").lower().strip()

    _event_type = "comment_reply" if parent_comment_id else "comment_added"

    from src.audit import log_audit_event

    if is_demo_mode():
        demo = st.session_state.setdefault("demo_comments", {})
        demo.setdefault(object_name, []).append({
            "comment_id":        comment_id,
            "author_name":       author_name,
            "author_email":      author_email,
            "comment_text":      comment_text,
            "created_at":        "just now",
            "parent_comment_id": parent_comment_id,
        })
        if parent_comment_id:
            send_reply_email(parent_author_email, author_name, object_name, comment_text, steward_email)
        else:
            send_comment_email(steward_email, author_name, object_name, comment_text)
        log_audit_event(_event_type, object_type, object_name, "", comment_text)
        return

    conn = _get_write_connection()
    with conn.cursor() as cursor:
        if _duckdb_available():
            cursor.execute_write(
                "INSERT INTO user_data.comments "
                "(comment_id, object_type, object_name, comment_text, author_name, author_email, "
                "created_at, steward_email, parent_comment_id) "
                "VALUES (%(comment_id)s, %(object_type)s, %(object_name)s, %(comment_text)s, "
                "%(author_name)s, %(author_email)s, current_localtimestamp(), %(steward_email)s, %(parent_comment_id)s)",
                {
                    "comment_id":        comment_id,
                    "object_type":       object_type,
                    "object_name":       object_name,
                    "comment_text":      comment_text,
                    "author_name":       author_name,
                    "author_email":      author_email,
                    "steward_email":     steward_email,
                    "parent_comment_id": parent_comment_id,
                },
            )
        else:
            cursor.execute(
                f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.comments "
                f"(comment_id, object_type, object_name, comment_text, author_name, author_email, "
                f"created_at, steward_email, parent_comment_id) "
                f"VALUES (%(comment_id)s, %(object_type)s, %(object_name)s, %(comment_text)s, "
                f"%(author_name)s, %(author_email)s, current_timestamp(), %(steward_email)s, %(parent_comment_id)s)",
                {
                    "comment_id":        comment_id,
                    "object_type":       object_type,
                    "object_name":       object_name,
                    "comment_text":      comment_text,
                    "author_name":       author_name,
                    "author_email":      author_email,
                    "steward_email":     steward_email,
                    "parent_comment_id": parent_comment_id,
                },
            )

    enqueue_sync("COMMENT", object_name, {
        "comment_id":        comment_id,
        "object_type":       object_type,
        "object_name":       object_name,
        "comment_text":      comment_text,
        "author_name":       author_name,
        "author_email":      author_email,
        "steward_email":     steward_email,
        "parent_comment_id": parent_comment_id,
    }, author_email)

    if parent_comment_id:
        verified_parent_email = _fetch_comment_author_email(parent_comment_id)
        send_reply_email(verified_parent_email, author_name, object_name, comment_text, steward_email)
    else:
        send_comment_email(steward_email, author_name, object_name, comment_text)
    log_audit_event(_event_type, object_type, object_name, "", comment_text)
