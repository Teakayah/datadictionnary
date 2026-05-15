"""Tests for src/storage/audit_storage.py."""

from __future__ import annotations

from unittest.mock import patch

import duckdb
import pytest

from src.storage.audit_storage import (
    ColumnOverride,
    AuditStorage,
    BusinessNameOverrideStorage,
    DemoAuditStorage,
    DemoBusinessNameOverrideStorage,
    DuckDBAuditStorage,
    DuckDBBusinessNameOverrideStorage,
    FakeAuditStorage,
    FakeBusinessNameOverrideStorage,
)


# ── Protocol satisfaction ────────────────────────────────────────────────────

@pytest.mark.parametrize("cls", [DemoAuditStorage, DuckDBAuditStorage, FakeAuditStorage])
def test_audit_implementations_satisfy_protocol(cls):
    assert isinstance(cls(), AuditStorage)


@pytest.mark.parametrize("cls", [
    DemoBusinessNameOverrideStorage,
    DuckDBBusinessNameOverrideStorage,
    FakeBusinessNameOverrideStorage,
])
def test_override_implementations_satisfy_protocol(cls):
    assert isinstance(cls(), BusinessNameOverrideStorage)


# ── Fakes ────────────────────────────────────────────────────────────────────

def _audit_event(event_id: str = "e1") -> dict:
    return {
        "event_id":    event_id,
        "event_type":  "test_event",
        "object_type": "TABLE",
        "object_name": "a.b.c",
        "actor_email": "tester@example.com",
        "old_value":   "",
        "new_value":   "x",
    }


class TestFakeAuditStorage:
    def test_append_records_event(self):
        fake = FakeAuditStorage()
        fake.append(_audit_event("e1"))
        fake.append(_audit_event("e2"))
        assert [e["event_id"] for e in fake.events] == ["e1", "e2"]
        # created_at gets stamped on the way in.
        assert all("created_at" in e for e in fake.events)


class TestFakeBusinessNameOverrideStorage:
    def test_upsert_then_get(self):
        fake = FakeBusinessNameOverrideStorage()
        fake.upsert(ColumnOverride("cat.sch.tbl", "col_a", "BizName", "definition", "alice"))
        result = fake.get_for_table("cat.sch.tbl")
        assert result["col_a"]["business_name"] == "BizName"
        assert result["col_a"]["definition"]    == "definition"
        assert result["col_a"]["edited_by"]     == "alice"

    def test_upsert_overwrites(self):
        fake = FakeBusinessNameOverrideStorage()
        fake.upsert(ColumnOverride("t", "c", "old", "old-def", "alice"))
        fake.upsert(ColumnOverride("t", "c", "new", "new-def", "bob"))
        assert fake.get_for_table("t")["c"]["business_name"] == "new"
        assert fake.get_for_table("t")["c"]["edited_by"]     == "bob"

    def test_get_for_unknown_table_returns_empty(self):
        fake = FakeBusinessNameOverrideStorage()
        assert fake.get_for_table("nope") == {}

    def test_isolated_by_table(self):
        fake = FakeBusinessNameOverrideStorage()
        fake.upsert(ColumnOverride("t1", "c", "n1", "d1", "alice"))
        fake.upsert(ColumnOverride("t2", "c", "n2", "d2", "alice"))
        assert fake.get_for_table("t1")["c"]["business_name"] == "n1"
        assert fake.get_for_table("t2")["c"]["business_name"] == "n2"


# ── DuckDB round-trip ────────────────────────────────────────────────────────

class TestDuckDBStorageRoundTrip:
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
        import src.storage.audit_storage
        importlib.reload(src.storage.audit_storage)

        from src.storage.audit_storage import (
    DuckDBAuditStorage, DuckDBBusinessNameOverrideStorage,
        )
        yield DuckDBAuditStorage(), DuckDBBusinessNameOverrideStorage()

        # Teardown: reload modules back to empty DUCKDB_PATH so subsequent
        # tests don't inherit a stale module-level constant pointing at the
        # now-gone tmp_path file (monkeypatch already reverted os.environ).
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
        import src.storage.audit_storage
        importlib.reload(src.storage.audit_storage)

    def test_audit_append_round_trip(self, storages):
        audit, _ = storages
        audit.append(_audit_event("e1"))
        # Verify by querying through the shared connection (a second
        # duckdb.connect to the same file would clash with the attach).
        from src.db.duckdb_adapter import _get_shared_duckdb_connection
        rows = _get_shared_duckdb_connection().execute(
            "SELECT event_id FROM user_data.audit_log WHERE event_id = 'e1'"
        ).fetchall()
        assert rows == [("e1",)]

    def test_business_name_override_round_trip(self, storages):
        _, overrides = storages
        overrides.upsert(ColumnOverride("cat.sch.tbl", "col_a", "BizName", "definition", "alice"))
        result = overrides.get_for_table("cat.sch.tbl")
        assert "col_a" in result
        assert result["col_a"]["business_name"] == "BizName"

        # Upsert again with new values.
        overrides.upsert(ColumnOverride("cat.sch.tbl", "col_a", "NewName", "new-def", "bob"))
        result = overrides.get_for_table("cat.sch.tbl")
        assert result["col_a"]["business_name"] == "NewName"
        assert result["col_a"]["edited_by"]     == "bob"


# ── audit.py routing through storage ─────────────────────────────────────────

class TestAuditRouting:
    """src.audit.log_audit_event delegates to AuditStorage.

    Verifies the storage receives the event, regardless of demo or DuckDB.
    """

    def test_log_audit_event_routes_to_storage(self, monkeypatch):
        import streamlit as st
        st.session_state.clear()
        st.session_state["user_email"] = "alice@test.com"
        monkeypatch.setenv("DEMO_DATA", "true")  # avoid enqueue_sync side effect

        fake = FakeAuditStorage()
        with patch("src.audit.get_audit_storage", return_value=fake):
            from src.audit import log_audit_event
            log_audit_event("test_event", "TABLE", "a.b.c", "old", "new")

        assert len(fake.events) == 1
        e = fake.events[0]
        assert e["event_type"]  == "test_event"
        assert e["object_name"] == "a.b.c"
        assert e["actor_email"] == "alice@test.com"
        assert e["old_value"]   == "old"
        assert e["new_value"]   == "new"

    def test_get_old_business_name_routes_to_storage(self):
        fake = FakeBusinessNameOverrideStorage()
        fake.upsert(ColumnOverride("cat.sch.tbl", "col_a", "BizName", "def", "alice"))
        with patch(
            "src.audit.get_business_name_override_storage", return_value=fake,
        ):
            from src.audit import _get_old_business_name
            assert _get_old_business_name("cat.sch.tbl", "col_a") == "BizName"
            assert _get_old_business_name("cat.sch.tbl", "missing") == ""
