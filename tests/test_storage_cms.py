"""Tests for src/storage/cms_storage.py.

Verifies that the three concrete CMS backends (Demo, DuckDB, Fake) satisfy
the same Protocol and behave identically on the read/write surface.

DuckDBCMSStorage is exercised against a tmp_path-backed in-memory DuckDB
connection so the test suite has no infra dependencies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone; UTC = timezone.utc

import duckdb
import pytest

from src.storage.cms_storage import (
    CMSStorage,
    DemoCMSStorage,
    DuckDBCMSStorage,
    FakeCMSStorage,
)


def _make_post(title: str, *, expires_in_days: int | None = None) -> dict:
    now = datetime.now(UTC)
    return {
        "post_id":      str(uuid.uuid4()),
        "post_type":    "announcement",
        "title":        title,
        "body":         "body",
        "table_ref":    None,
        "author_email": "tester@example.com",
        "created_at":   now,
        "expires_at":   (
            now + timedelta(days=expires_in_days)
            if expires_in_days is not None
            else None
        ),
    }


# ── Protocol satisfaction ────────────────────────────────────────────────────

@pytest.mark.parametrize("cls", [DemoCMSStorage, DuckDBCMSStorage, FakeCMSStorage])
def test_implementations_satisfy_protocol(cls):
    """All concrete classes implement the CMSStorage Protocol.

    runtime_checkable Protocols verify by attribute presence — this is a
    smoke test that none of the four methods are accidentally renamed.
    """
    instance = cls() if cls is not DuckDBCMSStorage else cls()
    assert isinstance(instance, CMSStorage)


# ── Behavioural parity (Fake covers Demo too — same logic) ───────────────────

class TestFakeCMSStorage:
    def test_create_then_list_all(self):
        fake = FakeCMSStorage()
        fake.create(_make_post("first"))
        fake.create(_make_post("second"))
        # Newest first.
        assert [p["title"] for p in fake.list_all()] == ["second", "first"]

    def test_list_active_filters_expired(self):
        fake = FakeCMSStorage([
            _make_post("future", expires_in_days=1),
            _make_post("past",   expires_in_days=-1),
            _make_post("never"),  # no expiry
        ])
        titles = [p["title"] for p in fake.list_active()]
        assert "future" in titles
        assert "never"  in titles
        assert "past" not in titles

    def test_delete_idempotent(self):
        post = _make_post("only")
        fake = FakeCMSStorage([post])
        fake.delete(post["post_id"])
        fake.delete(post["post_id"])  # twice — must not raise
        assert fake.list_all() == []

    def test_init_with_initial_posts(self):
        fake = FakeCMSStorage([_make_post("seed")])
        assert len(fake.list_all()) == 1


# ── DuckDB backend smoke test ────────────────────────────────────────────────

class TestDuckDBCMSStorage:
    """Round-trip a post through a real DuckDB connection.

    Uses a tmp_path-backed file + the same _initialize_schema entry point
    the production daemon uses — so this test catches schema drift between
    duckdb_adapter and cms_storage.
    """

    @pytest.fixture
    def storage(self, tmp_path, monkeypatch):
        catalog_path = tmp_path / "dict.duckdb"

        monkeypatch.setenv("DUCKDB_PATH", str(catalog_path))
        # Create the catalog file so _duckdb_available() is True.
        duckdb.connect(str(catalog_path)).close()

        # Reload modules that capture DUCKDB_PATH at import time.
        import importlib
        import src.config
        importlib.reload(src.config)
        import src.db.duckdb_adapter
        importlib.reload(src.db.duckdb_adapter)
        try:
            src.db.duckdb_adapter._get_shared_duckdb_connection.clear()
        except Exception:
            pass
        import src.db.queries
        importlib.reload(src.db.queries)
        import src.storage.cms_storage
        importlib.reload(src.storage.cms_storage)

        from src.storage.cms_storage import DuckDBCMSStorage
        return DuckDBCMSStorage()

    def test_create_then_list_active(self, storage):
        post = _make_post("hello-duckdb", expires_in_days=1)
        storage.create(post)
        active = storage.list_active()
        assert len(active) == 1
        assert active[0]["title"] == "hello-duckdb"

    def test_create_then_delete(self, storage):
        post = _make_post("to-delete")
        storage.create(post)
        storage.delete(post["post_id"])
        assert storage.list_all() == []

    def test_list_all_includes_expired(self, storage):
        storage.create(_make_post("expired", expires_in_days=-1))
        storage.create(_make_post("active",  expires_in_days=1))
        all_titles = [p["title"] for p in storage.list_all()]
        active_titles = [p["title"] for p in storage.list_active()]
        assert "expired" in all_titles
        assert "expired" not in active_titles

    def test_list_active_handles_exception(self, storage, monkeypatch):
        def mock_get_db_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.cms_storage.get_db_connection", mock_get_db_connection)
        assert storage.list_active() == []

    def test_list_all_handles_exception(self, storage, monkeypatch):
        def mock_get_db_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.cms_storage.get_db_connection", mock_get_db_connection)
        assert storage.list_all() == []


# ── Factory routing ──────────────────────────────────────────────────────────

class TestGetCmsStorage:
    """Module-reload-resilient: checks via ``type(x).__name__`` rather than
    ``isinstance``, because reloading ``src.storage`` to pick up new env
    creates a fresh class object that wouldn't satisfy isinstance against
    the test module's earlier import."""

    def test_returns_demo_when_no_duckdb(self, monkeypatch):
        monkeypatch.delenv("DUCKDB_PATH", raising=False)
        import importlib
        import src.config
        importlib.reload(src.config)
        import src.db.duckdb_adapter
        importlib.reload(src.db.duckdb_adapter)
        import src.storage
        importlib.reload(src.storage)
        assert type(src.storage.get_cms_storage()).__name__ == "DemoCMSStorage"

    def test_returns_demo_when_demo_mode(self, monkeypatch):
        monkeypatch.setenv("DEMO_DATA", "true")
        # is_demo_mode() reads env at call time, so no reload needed.
        from src.storage import get_cms_storage
        assert type(get_cms_storage()).__name__ == "DemoCMSStorage"

    def test_returns_duckdb_when_available(self, tmp_path, monkeypatch):
        catalog_path = tmp_path / "dict.duckdb"
        duckdb.connect(str(catalog_path)).close()
        monkeypatch.setenv("DUCKDB_PATH", str(catalog_path))
        monkeypatch.delenv("DEMO_DATA", raising=False)
        import importlib
        import src.config
        importlib.reload(src.config)
        import src.db.duckdb_adapter
        importlib.reload(src.db.duckdb_adapter)
        import src.storage
        importlib.reload(src.storage)
        assert type(src.storage.get_cms_storage()).__name__ == "DuckDBCMSStorage"

class TestDemoCMSStorage:
    def test_demo_create(self):
        import streamlit as st
        st.session_state.clear()
        from src.storage.cms_storage import DemoCMSStorage
        storage = DemoCMSStorage()
        storage.create(_make_post("first", expires_in_days=1))
        assert len(storage.list_all()) == 1

    def test_demo_delete(self):
        import streamlit as st
        st.session_state.clear()
        from src.storage.cms_storage import DemoCMSStorage
        storage = DemoCMSStorage()
        p = _make_post("first")
        storage.create(p)
        storage.delete(p["post_id"])
        assert len(storage.list_all()) == 0

    def test_demo_list_active(self):
        import streamlit as st
        st.session_state.clear()
        from src.storage.cms_storage import DemoCMSStorage
        storage = DemoCMSStorage()
        storage.create(_make_post("active", expires_in_days=1))
        storage.create(_make_post("expired", expires_in_days=-1))
        assert len(storage.list_active()) == 1
