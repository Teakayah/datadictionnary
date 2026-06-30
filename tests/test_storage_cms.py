from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from src.storage.cms_storage import DemoCMSStorage, FakeCMSStorage
import streamlit as st

from src.storage.cms_storage import (
    DuckDBCMSStorage
)

def test_duckdb_cms_storage_list_active_db_error():
    """Test DuckDBCMSStorage list_active handles DB exceptions safely."""
    storage = DuckDBCMSStorage()
    with patch("src.storage.cms_storage.get_db_connection", side_effect=Exception("DB down")):
        assert storage.list_active() == []

def test_duckdb_cms_storage_list_all_db_error():
    """Test DuckDBCMSStorage list_all handles DB exceptions safely."""
    storage = DuckDBCMSStorage()
    with patch("src.storage.cms_storage.get_db_connection", side_effect=Exception("DB down")):
        assert storage.list_all() == []

def test_duckdb_cms_storage_create():
    """Test DuckDBCMSStorage create."""
    storage = DuckDBCMSStorage()
    mock_conn = MagicMock()
    with patch("src.storage.cms_storage._get_write_connection", return_value=mock_conn):
        storage.create({
            "post_id": "1",
            "post_type": "guide",
            "title": "Test",
            "body": "Body",
            "table_ref": None,
            "author_email": "admin@example.com",
            "created_at": datetime.now(timezone.utc),
            "expires_at": None,
        })
        mock_conn.execute.assert_called_once()

def test_duckdb_cms_storage_delete():
    """Test DuckDBCMSStorage delete."""
    storage = DuckDBCMSStorage()
    mock_conn = MagicMock()
    with patch("src.storage.cms_storage._get_write_connection", return_value=mock_conn):
        storage.delete("1")
        mock_conn.execute.assert_called_once()

def test_duckdb_cms_storage_list_active():
    """Test DuckDBCMSStorage list_active DB fetch."""
    storage = DuckDBCMSStorage()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [("1", "guide", "Test", "Body", None, "admin@example.com", datetime.now(timezone.utc), None)]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("src.storage.cms_storage.get_db_connection", return_value=mock_conn):
        posts = storage.list_active()
        assert len(posts) == 1
        assert posts[0]["post_id"] == "1"

def test_duckdb_cms_storage_list_all():
    """Test DuckDBCMSStorage list_all DB fetch."""
    storage = DuckDBCMSStorage()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [("1", "guide", "Test", "Body", None, "admin@example.com", datetime.now(timezone.utc), None)]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("src.storage.cms_storage.get_db_connection", return_value=mock_conn):
        posts = storage.list_all()
        assert len(posts) == 1
        assert posts[0]["post_id"] == "1"


def test_demo_cms_storage():
    """Test DemoCMSStorage."""
    if "_demo_cms_posts" in st.session_state:
        del st.session_state["_demo_cms_posts"]

    storage = DemoCMSStorage()

    post = {
        "post_id": "1",
        "post_type": "guide",
        "title": "Test",
        "body": "Body",
        "table_ref": None,
        "author_email": "admin@example.com",
        "created_at": datetime.now(timezone.utc),
        "expires_at": None,
    }

    storage.create(post)
    assert len(storage.list_all()) == 1
    assert len(storage.list_active()) == 1

    expired_post = {
        "post_id": "2",
        "post_type": "guide",
        "title": "Test",
        "body": "Body",
        "table_ref": None,
        "author_email": "admin@example.com",
        "created_at": datetime.now(timezone.utc) - timedelta(days=2),
        "expires_at": datetime.now(timezone.utc) - timedelta(days=1),
    }
    storage.create(expired_post)
    assert len(storage.list_all()) == 2
    assert len(storage.list_active()) == 1

    storage.delete("1")
    assert len(storage.list_all()) == 1

def test_fake_cms_storage():
    """Test FakeCMSStorage."""
    storage = FakeCMSStorage()

    post = {
        "post_id": "1",
        "post_type": "guide",
        "title": "Test",
        "body": "Body",
        "table_ref": None,
        "author_email": "admin@example.com",
        "created_at": datetime.now(timezone.utc),
        "expires_at": None,
    }

    storage.create(post)
    assert len(storage.list_all()) == 1
    assert len(storage.list_active()) == 1

    expired_post = {
        "post_id": "2",
        "post_type": "guide",
        "title": "Test",
        "body": "Body",
        "table_ref": None,
        "author_email": "admin@example.com",
        "created_at": datetime.now(timezone.utc) - timedelta(days=2),
        "expires_at": datetime.now(timezone.utc) - timedelta(days=1),
    }
    storage.create(expired_post)
    assert len(storage.list_all()) == 2
    assert len(storage.list_active()) == 1

    storage.delete("1")
    assert len(storage.list_all()) == 1
