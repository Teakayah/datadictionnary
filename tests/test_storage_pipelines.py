"""Tests for src/storage/pipeline_storage.py.

Same shape as tests/test_storage_cms.py — protocol satisfaction, fake
behaviour, DuckDB round-trip, factory routing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone; UTC = timezone.utc
from unittest.mock import patch

import duckdb
import pytest

from src.storage.pipeline_storage import (
    DemoPipelineDefStorage,
    DemoPipelineRunStorage,
    DuckDBPipelineDefStorage,
    DuckDBPipelineRunStorage,
    FakePipelineDefStorage,
    FakePipelineRunStorage,
    PipelineDefStorage,
    PipelineRunStorage,
)


def _make_pipeline(title: str = "My Job") -> dict:
    return {
        "pipeline_id":         str(uuid.uuid4()),
        "title":               title,
        "description":         "desc",
        "backend":             "databricks",
        "databricks_job_id":   "42",
        "adf_subscription_id": None,
        "adf_resource_group":  None,
        "adf_factory_name":    None,
        "adf_pipeline_name":   None,
        "ado_organization":    None,
        "ado_project":         None,
        "ado_pipeline_id":     None,
        "created_by":          "admin",
        "created_at":          datetime.now(UTC),
    }


# ── Protocol satisfaction ────────────────────────────────────────────────────

@pytest.mark.parametrize("cls", [
    DemoPipelineDefStorage, DuckDBPipelineDefStorage, FakePipelineDefStorage,
])
def test_def_implementations_satisfy_protocol(cls):
    assert isinstance(cls(), PipelineDefStorage)


@pytest.mark.parametrize("cls", [
    DemoPipelineRunStorage, DuckDBPipelineRunStorage, FakePipelineRunStorage,
])
def test_run_implementations_satisfy_protocol(cls):
    assert isinstance(cls(), PipelineRunStorage)


# ── Fake behaviour ───────────────────────────────────────────────────────────

class TestFakePipelineDefStorage:
    def test_create_then_list(self):
        fake = FakePipelineDefStorage()
        fake.create(_make_pipeline("first"))
        fake.create(_make_pipeline("second"))
        titles = [p["title"] for p in fake.list_all()]
        assert titles == ["first", "second"]  # insertion order

    def test_delete_idempotent(self):
        p = _make_pipeline()
        fake = FakePipelineDefStorage([p])
        fake.delete(p["pipeline_id"])
        fake.delete(p["pipeline_id"])
        assert fake.list_all() == []


class TestFakePipelineRunStorage:
    def test_upsert_then_get_active(self):
        fake = FakePipelineRunStorage()
        fake.upsert("p1", "run-123", "alice")
        run = fake.get_active("p1")
        assert run is not None
        assert run["backend_run_id"] == "run-123"
        assert run["status"] == "started"

    def test_update_status(self):
        fake = FakePipelineRunStorage()
        fake.upsert("p1", "r1", "alice")
        fake.update_status("p1", "RUNNING")
        assert fake.get_active("p1")["status"] == "RUNNING"

    def test_update_status_on_missing_run_is_noop(self):
        fake = FakePipelineRunStorage()
        fake.update_status("nonexistent", "RUNNING")  # must not raise
        assert fake.get_active("nonexistent") is None

    def test_clear(self):
        fake = FakePipelineRunStorage()
        fake.upsert("p1", "r1", "alice")
        fake.clear("p1")
        assert fake.get_active("p1") is None

    def test_upsert_overwrites(self):
        fake = FakePipelineRunStorage()
        fake.upsert("p1", "r1", "alice")
        fake.upsert("p1", "r2", "bob")
        run = fake.get_active("p1")
        assert run["backend_run_id"] == "r2"
        assert run["triggered_by"] == "bob"


# ── DuckDB backend smoke test ────────────────────────────────────────────────

class TestDuckDBPipelineStorage:
    """Round-trip through real DuckDB. Verifies the schema (via
    _initialize_schema) matches the storage SQL."""

    @pytest.fixture
    def storages(self, tmp_path, monkeypatch):
        catalog_path = tmp_path / "dict.duckdb"
        monkeypatch.setenv("DUCKDB_PATH", str(catalog_path))
        duckdb.connect(str(catalog_path)).close()

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
        import src.storage.pipeline_storage
        importlib.reload(src.storage.pipeline_storage)

        from src.storage.pipeline_storage import (
            DuckDBPipelineDefStorage,
            DuckDBPipelineRunStorage,
        )
        return DuckDBPipelineDefStorage(), DuckDBPipelineRunStorage()

    def test_def_create_list_delete(self, storages):
        defs, _runs = storages
        p = _make_pipeline()
        defs.create(p)
        listed = defs.list_all()
        assert len(listed) == 1
        assert listed[0]["title"] == "My Job"
        defs.delete(p["pipeline_id"])
        assert defs.list_all() == []

    def test_run_lifecycle(self, storages):
        _defs, runs = storages
        runs.upsert("p1", "run-xyz", "alice")
        active = runs.get_active("p1")
        assert active["status"] == "started"
        runs.update_status("p1", "RUNNING")
        assert runs.get_active("p1")["status"] == "RUNNING"
        runs.clear("p1")
        assert runs.get_active("p1") is None


# ── Factory routing ──────────────────────────────────────────────────────────

class TestPipelineFactories:
    @pytest.mark.parametrize("is_demo, expected_def_cls, expected_run_cls", [
        (True, "DemoPipelineDefStorage", "DemoPipelineRunStorage"),
        (False, "DuckDBPipelineDefStorage", "DuckDBPipelineRunStorage"),
    ])
    def test_factories_routing(self, monkeypatch, is_demo, expected_def_cls, expected_run_cls):
        monkeypatch.setattr("src.storage._use_demo_backend", lambda: is_demo)
        import src.storage

        def_storage = src.storage.get_pipeline_def_storage()
        assert type(def_storage).__name__ == expected_def_cls

        run_storage = src.storage.get_pipeline_run_storage()
        assert type(run_storage).__name__ == expected_run_cls


# ── Cascade behaviour in src.pipelines.delete_pipeline_def ──────────────────

class TestDeleteCascade:
    """delete_pipeline_def should delete the def AND clear any active run.

    Cascade lives in src.pipelines (the wrapper), not in the def storage.
    """

    def test_cascade_clears_active_run(self):
        from src.storage.pipeline_storage import (
            FakePipelineDefStorage,
            FakePipelineRunStorage,
        )
        defs = FakePipelineDefStorage([_make_pipeline()])
        runs = FakePipelineRunStorage()
        pid = defs.list_all()[0]["pipeline_id"]
        runs.upsert(pid, "run-1", "alice")

        # delete_pipeline_def is admin-only — patch the auth check too.
        with patch("src.pipelines.is_admin", return_value=True), \
             patch("src.pipelines.get_pipeline_def_storage", return_value=defs), \
             patch("src.pipelines.get_pipeline_run_storage", return_value=runs):
            from src.pipelines import delete_pipeline_def
            delete_pipeline_def(pid)

        assert defs.list_all() == []
        assert runs.get_active(pid) is None

class TestDemoPipelineRunStorage:
    def test_demo_pipeline_run(self):
        import streamlit as st
        st.session_state.clear()
        from src.storage.pipeline_storage import DemoPipelineRunStorage
        storage = DemoPipelineRunStorage()
        storage.upsert("p1", "r1", "alice")
        assert storage.get_active("p1")["backend_run_id"] == "r1"
        storage.update_status("p1", "success")
        assert storage.get_active("p1")["status"] == "success"
        storage.clear("p1")
        assert storage.get_active("p1") is None

class TestDuckDBPipelineStorageExceptions:
    def test_def_list_all_exception(self, monkeypatch):
        def mock_get_db_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.pipeline_storage.get_db_connection", mock_get_db_connection)
        from src.storage.pipeline_storage import DuckDBPipelineDefStorage
        assert DuckDBPipelineDefStorage().list_all() == []

    def test_run_get_active_exception(self, monkeypatch):
        def mock_get_db_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.pipeline_storage.get_db_connection", mock_get_db_connection)
        from src.storage.pipeline_storage import DuckDBPipelineRunStorage
        assert DuckDBPipelineRunStorage().get_active("p1") is None

class TestDemoPipelineDefStorage:
    def test_demo_create(self):
        import streamlit as st
        st.session_state.clear()
        from src.storage.pipeline_storage import DemoPipelineDefStorage
        storage = DemoPipelineDefStorage()
        storage.create(_make_pipeline())
        assert len(storage.list_all()) == 1

    def test_demo_delete(self):
        import streamlit as st
        st.session_state.clear()
        from src.storage.pipeline_storage import DemoPipelineDefStorage
        storage = DemoPipelineDefStorage()
        p = _make_pipeline()
        storage.create(p)
        storage.delete(p["pipeline_id"])
        assert len(storage.list_all()) == 0
