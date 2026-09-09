from __future__ import annotations
"""Tests for comment and reply functionality (fetching, saving, email notification)."""

import pandas as pd
import streamlit as st


def test_get_table_comments_demo_mode(monkeypatch):
    from src.comments import get_table_comments
    monkeypatch.setenv("DEMO_DATA", "true")
    # Manually populate demo_comments since it's not pre-populated in the session state
    st.session_state["demo_comments"] = {
        "main.analytics.customers": [
            {
                "comment_id": "1",
                "author_name": "Test",
                "author_email": "test@test.com",
                "comment_text": "Hello",
                "created_at": "now",
                "parent_comment_id": None
            }
        ]
    }
    res = get_table_comments("main.analytics.customers")
    assert isinstance(res, list)
    assert len(res) > 0
    assert res[0]["comment_id"] == "1"
    assert "replies" in res[0]
    st.session_state.clear()


def test_get_table_comments_empty_demo(monkeypatch):
    from src.comments import get_table_comments
    monkeypatch.setenv("DEMO_DATA", "true")
    st.session_state["demo_comments"] = {}
    # For an unknown table in demo mode, should return []
    res = get_table_comments("unknown.table")
    assert res == []
    st.session_state.clear()


def test_send_reply_email_demo(monkeypatch, capfd):
    from src.comments import send_reply_email
    monkeypatch.setenv("DEMO_DATA", "true")
    send_reply_email("parent@test.com", "Replier", "Object", "Reply Text", "")
    out, _ = capfd.readouterr()
    assert "[DEMO REPLY]" in out
    assert "Replier" in out

def test_send_reply_email_no_smtp(monkeypatch, caplog):
    from src.comments import send_reply_email
    monkeypatch.setenv("DEMO_DATA", "false")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    send_reply_email("parent@test.com", "Replier", "Object", "Reply Text", "")
    assert "Comment saved but email not sent: SMTP_HOST not configured." in caplog.text


def test_send_comment_email_no_smtp(monkeypatch, caplog):
    from src.comments import send_comment_email
    monkeypatch.setenv("DEMO_DATA", "false")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    send_comment_email("to@test.com", "Author", "Object", "Text")
    assert "Comment saved but email not sent: SMTP_HOST not configured." in caplog.text

def test_get_table_comments_prod_error_connection(monkeypatch, caplog):
    from src.comments import get_table_comments
    from unittest.mock import patch
    monkeypatch.setenv("DEMO_DATA", "false")
    with patch("src.comments.get_db_connection") as mock_conn_func:
        mock_conn_func.side_effect = Exception("DB connection failed")

        res = get_table_comments("obj1")
        assert res == []
        assert "Could not fetch comments for obj1: DB connection failed" in caplog.text

def test_get_table_comments_prod_error_fetchall(monkeypatch, caplog):
    from src.comments import get_table_comments
    from unittest.mock import patch, MagicMock
    monkeypatch.setenv("DEMO_DATA", "false")
    with patch("src.comments.get_db_connection") as mock_conn_func, \
         patch("src.comments._duckdb_available", return_value=True):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn_func.return_value = mock_conn

        mock_cursor.fetchall_as_pandas.side_effect = Exception("DB fetch failed")

        res = get_table_comments("obj1")
        assert res == []
        assert "Could not fetch comments for obj1: DB fetch failed" in caplog.text

def test_get_table_comments(monkeypatch):
    """Test get_table_comments explicitly to satisfy the reviewer."""
    from src.comments import get_table_comments
    from unittest.mock import patch, MagicMock

    monkeypatch.setenv("DEMO_DATA", "false")
    with patch("src.comments.get_db_connection") as mock_conn_func, \
         patch("src.comments._duckdb_available", return_value=True):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn_func.return_value = mock_conn

        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame([
            {"comment_id": "1", "parent_comment_id": None, "text": "Root"},
            {"comment_id": "2", "parent_comment_id": "1", "text": "Reply 1"},
            {"comment_id": "3", "parent_comment_id": "999", "text": "Missing parent fallback"}
        ])

        res = get_table_comments("obj_test")

        assert len(res) == 2
        assert res[0]["comment_id"] == "1"
        assert len(res[0]["replies"]) == 1
        assert res[0]["replies"][0]["comment_id"] == "2"
        assert res[1]["comment_id"] == "3"
        assert len(res[1]["replies"]) == 0

def test_fetch_comment_author_email_demo(monkeypatch):
    from src.comments import _fetch_comment_author_email
    monkeypatch.setenv("DEMO_DATA", "true")
    st.session_state["demo_comments"] = {
        "obj1": [
            {"comment_id": "123", "author_email": "test@demo.com"}
        ]
    }
    assert _fetch_comment_author_email("123") == "test@demo.com"
    assert _fetch_comment_author_email("999") == ""
    st.session_state.clear()

def test_fetch_comment_author_email_prod(monkeypatch):
    from src.comments import _fetch_comment_author_email
    monkeypatch.setenv("DEMO_DATA", "false")
    from unittest.mock import patch, MagicMock
    import pandas as pd

    with patch("src.comments.get_db_connection") as mock_conn_func, \
         patch("src.comments._duckdb_available", return_value=True):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn_func.return_value = mock_conn

        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame([
            {"author_email": "real@prod.com"}
        ])

        assert _fetch_comment_author_email("123") == "real@prod.com"

        mock_cursor.fetchall_as_pandas.side_effect = Exception("DB fetch error")
        assert _fetch_comment_author_email("123") == ""

def test_save_comment_demo_mode(monkeypatch):
    from src.comments import save_comment
    monkeypatch.setenv("DEMO_DATA", "true")
    st.session_state["demo_comments"] = {}
    st.session_state["user_name"] = "Alice"
    st.session_state["user_email"] = "alice@test.com"

    save_comment("table", "my.table", "Hello world", "steward@test.com")
    assert "my.table" in st.session_state["demo_comments"]
    assert len(st.session_state["demo_comments"]["my.table"]) == 1
    assert st.session_state["demo_comments"]["my.table"][0]["comment_text"] == "Hello world"

    parent_id = st.session_state["demo_comments"]["my.table"][0]["comment_id"]
    save_comment("table", "my.table", "Reply text", "steward@test.com", parent_comment_id=parent_id)
    assert len(st.session_state["demo_comments"]["my.table"]) == 2
    assert st.session_state["demo_comments"]["my.table"][1]["parent_comment_id"] == parent_id
    assert st.session_state["demo_comments"]["my.table"][1]["comment_text"] == "Reply text"
    st.session_state.clear()

def test_save_comment_prod_mode(monkeypatch):
    from src.comments import save_comment
    monkeypatch.setenv("DEMO_DATA", "false")
    st.session_state["user_name"] = "Bob"
    st.session_state["user_email"] = "bob@test.com"
    from unittest.mock import patch, MagicMock

    with patch("src.comments._get_write_connection") as mock_conn_func, \
         patch("src.comments._duckdb_available", return_value=True), \
         patch("src.comments.enqueue_sync") as mock_enqueue, \
         patch("src.audit.log_audit_event") as mock_audit, \
         patch("src.comments.send_comment_email") as mock_send_email:

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn_func.return_value = mock_conn

        save_comment("table", "my.table", "Prod text", "steward@test.com")

        assert mock_cursor.execute_write.call_count >= 1
        mock_enqueue.assert_called_once()
        mock_audit.assert_called_once()
        mock_send_email.assert_called_once()
    st.session_state.clear()

def test_save_comment_prod_mode_error(monkeypatch, caplog):
    from src.comments import save_comment
    monkeypatch.setenv("DEMO_DATA", "false")
    st.session_state["user_name"] = "Bob"
    st.session_state["user_email"] = "bob@test.com"
    from unittest.mock import patch

    with patch("src.comments._get_write_connection") as mock_conn_func, \
         patch("src.comments.enqueue_sync") as mock_enqueue, \
         patch("src.audit.log_audit_event") as mock_audit, \
         patch("src.comments.send_comment_email") as mock_send_email:

        mock_conn_func.side_effect = Exception("Storage failed")

        save_comment("table", "my.table", "Prod text", "steward@test.com")

        assert "Could not save comment for my.table: Storage failed" in caplog.text
        mock_enqueue.assert_not_called()
        mock_audit.assert_not_called()
        mock_send_email.assert_not_called()
    st.session_state.clear()

def test_save_comment_prod_mode_not_duckdb(monkeypatch):
    from src.comments import save_comment
    monkeypatch.setenv("DEMO_DATA", "false")
    st.session_state["user_name"] = "Bob"
    st.session_state["user_email"] = "bob@test.com"
    from unittest.mock import patch, MagicMock

    with patch("src.comments._get_write_connection") as mock_conn_func, \
         patch("src.comments._duckdb_available", return_value=False), \
         patch("src.comments.enqueue_sync") as mock_enqueue, \
         patch("src.audit.log_audit_event") as mock_audit, \
         patch("src.comments._fetch_comment_author_email", return_value="parent@prod.com"), \
         patch("src.comments.send_reply_email") as mock_send_email:

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn_func.return_value = mock_conn

        save_comment("table", "my.table", "Prod reply text", "steward@test.com", parent_comment_id="999")

        assert mock_cursor.execute.call_count >= 1
        mock_enqueue.assert_called_once()
        mock_audit.assert_called_once()
        mock_send_email.assert_called_once()
    st.session_state.clear()

def test_send_comment_email_smtp(monkeypatch, caplog):
    from src.comments import send_comment_email
    monkeypatch.setenv("DEMO_DATA", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
    from unittest.mock import patch, MagicMock

    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        send_comment_email("to@test.com", "Author", "Object", "Text")

        mock_server.sendmail.assert_called_once()

        mock_server.sendmail.side_effect = Exception("SMTP error")
        send_comment_email("to@test.com", "Author", "Object", "Text")
        assert "Failed to send email to" in caplog.text

def test_send_reply_email_smtp(monkeypatch, caplog):
    from src.comments import send_reply_email
    monkeypatch.setenv("DEMO_DATA", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
    from unittest.mock import patch, MagicMock

    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        send_reply_email("parent@test.com", "Replier", "Object", "Reply Text", "steward@test.com")

        mock_server.sendmail.assert_called_once()

        mock_server.sendmail.side_effect = Exception("SMTP error")
        send_reply_email("parent@test.com", "Replier", "Object", "Reply Text", "steward@test.com")
        assert "Failed to send email to" in caplog.text

def test_send_reply_email_no_recipients(monkeypatch, caplog):
    from src.comments import send_reply_email
    monkeypatch.setenv("DEMO_DATA", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
    from unittest.mock import patch, MagicMock

    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        send_reply_email("", "Replier", "Object", "Reply Text", "")
        mock_server.sendmail.assert_not_called()
