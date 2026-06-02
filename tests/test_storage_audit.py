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

    def test_get_columns(self):
        fake = FakeBusinessNameOverrideStorage()
        import pandas as pd
        df = fake.get_columns("t1")
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["column_name", "data_type", "comment"]


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

    def test_duckdb_list_pending(self, storages):
        _, overrides = storages
        overrides.upsert(ColumnOverride("t", "c", "bn", "def", "alice", "pending_approval"))
        assert len(overrides.list_pending()) == 1

    def test_duckdb_approve(self, storages):
        _, overrides = storages
        overrides.upsert(ColumnOverride("t", "c", "bn", "def", "alice", "pending_approval"))
        overrides.approve("t", "c")
        assert len(overrides.list_pending()) == 0

    def test_duckdb_reject(self, storages):
        _, overrides = storages
        overrides.upsert(ColumnOverride("t", "c", "bn", "def", "alice", "pending_approval"))
        overrides.reject("t", "c")
        assert len(overrides.list_pending()) == 0

    def test_list_pending_returns_empty_when_no_rows(self, storages):
        _, overrides = storages
        assert overrides.list_pending() == []

    def test_list_pending_with_pending_approval(self, storages):
        _, overrides = storages
        overrides.upsert(ColumnOverride("t1", "c1", "bn", "def", "alice", "pending_approval"))
        assert len(overrides.list_pending()) == 1

    def test_duckdb_get_columns(self, storages, monkeypatch):
        _, overrides = storages

        def mock_run_query(query, params):
            import pandas as pd
            return pd.DataFrame([{"column_name": "c1", "data_type": "int", "comment": "test"}])

        monkeypatch.setattr("src.db.queries.run_query", mock_run_query)

        df = overrides.get_columns("t1")
        assert list(df.columns) == ["column_name", "data_type", "comment"]
        assert len(df) == 1


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

class TestGetAuditStorage:
    def test_returns_demo_when_demo_mode(self, monkeypatch):
        monkeypatch.setenv("DEMO_DATA", "true")
        from src.storage import get_audit_storage
        assert type(get_audit_storage()).__name__ == "DemoAuditStorage"

class TestGetBusinessNameOverrideStorage:
    def test_returns_demo_when_demo_mode(self, monkeypatch):
        monkeypatch.setenv("DEMO_DATA", "true")
        from src.storage import get_business_name_override_storage
        assert type(get_business_name_override_storage()).__name__ == "DemoBusinessNameOverrideStorage"

class TestDuckDBAuditExceptions:
    def test_audit_append_exception(self, monkeypatch):
        def mock_get_write_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.audit_storage._get_write_connection", mock_get_write_connection)
        from src.storage.audit_storage import DuckDBAuditStorage
        storage = DuckDBAuditStorage()
        storage.append(_audit_event("e1")) # Should catch and ignore the exception

class TestDemoAuditStorage:
    def test_demo_append(self, monkeypatch):
        import streamlit as st
        st.session_state.clear()
        from src.storage.audit_storage import DemoAuditStorage
        storage = DemoAuditStorage()
        storage.append(_audit_event("e1"))
        assert len(st.session_state["demo_audit_log"]) == 1

class TestDemoBusinessNameOverrideStorage:
    def test_demo_get_columns(self, monkeypatch):
        import streamlit as st
        st.session_state.clear()

        # Mock run_query since Demo uses it
        from src.db.queries import run_query

        def mock_run_query(query, params):
            import pandas as pd
            return pd.DataFrame([{"column_name": "c1", "data_type": "int", "comment": "test"}])

        monkeypatch.setattr("src.db.queries.run_query", mock_run_query)

        from src.storage.audit_storage import DemoBusinessNameOverrideStorage
        storage = DemoBusinessNameOverrideStorage()
        df = storage.get_columns("t1")
        assert list(df.columns) == ["column_name", "data_type", "comment"]
        assert len(df) == 1

    def test_demo_upsert_get(self, monkeypatch):
        import streamlit as st
        st.session_state.clear()
        from src.storage.audit_storage import DemoBusinessNameOverrideStorage, ColumnOverride
        storage = DemoBusinessNameOverrideStorage()
        storage.upsert(ColumnOverride("t1", "c1", "bn", "def", "alice", "published"))
        res = storage.get_for_table("t1")
        assert res["c1"]["business_name"] == "bn"

    def test_demo_list_pending(self, monkeypatch):
        import streamlit as st
        st.session_state.clear()
        from src.storage.audit_storage import DemoBusinessNameOverrideStorage, ColumnOverride
        storage = DemoBusinessNameOverrideStorage()
        storage.upsert(ColumnOverride("t1", "c1", "bn", "def", "alice", "pending_approval"))
        assert len(storage.list_pending()) == 1

    def test_demo_approve(self, monkeypatch):
        import streamlit as st
        st.session_state.clear()
        from src.storage.audit_storage import DemoBusinessNameOverrideStorage, ColumnOverride
        storage = DemoBusinessNameOverrideStorage()
        storage.upsert(ColumnOverride("t1", "c1", "bn", "def", "alice", "pending_approval"))
        storage.approve("t1", "c1")
        assert storage.list_pending() == []

    def test_demo_reject(self, monkeypatch):
        import streamlit as st
        st.session_state.clear()
        from src.storage.audit_storage import DemoBusinessNameOverrideStorage, ColumnOverride
        storage = DemoBusinessNameOverrideStorage()
        storage.upsert(ColumnOverride("t1", "c1", "bn", "def", "alice", "pending_approval"))
        storage.reject("t1", "c1")
        assert storage.list_pending() == []

class TestDuckDBExceptions:
    def test_get_for_table_exception(self, monkeypatch):
        def mock_get_db_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.audit_storage.get_db_connection", mock_get_db_connection)
        from src.storage.audit_storage import DuckDBBusinessNameOverrideStorage
        storage = DuckDBBusinessNameOverrideStorage()
        assert storage.get_for_table("t") == {}

    def test_list_pending_exception(self, monkeypatch):
        def mock_get_db_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.audit_storage.get_db_connection", mock_get_db_connection)
        from src.storage.audit_storage import DuckDBBusinessNameOverrideStorage
        storage = DuckDBBusinessNameOverrideStorage()
        assert storage.list_pending() == []

class TestDuckDBBusinessNameOverrideExceptions:
    def test_approve_exception(self, monkeypatch):
        def mock_get_write_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.audit_storage._get_write_connection", mock_get_write_connection)
        from src.storage.audit_storage import DuckDBBusinessNameOverrideStorage
        storage = DuckDBBusinessNameOverrideStorage()
        import pytest
        with pytest.raises(Exception):
            storage.approve("tbl", "col")

    def test_reject_exception(self, monkeypatch):
        def mock_get_write_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.audit_storage._get_write_connection", mock_get_write_connection)
        from src.storage.audit_storage import DuckDBBusinessNameOverrideStorage
        storage = DuckDBBusinessNameOverrideStorage()
        import pytest
        with pytest.raises(Exception):
            storage.reject("tbl", "col")

    def test_upsert_exception(self, monkeypatch):
        def mock_get_write_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.audit_storage._get_write_connection", mock_get_write_connection)
        from src.storage.audit_storage import DuckDBBusinessNameOverrideStorage, ColumnOverride
        storage = DuckDBBusinessNameOverrideStorage()
        import pytest
        with pytest.raises(Exception):
            storage.upsert(ColumnOverride("tbl", "col", "bn", "def", "alice"))

class TestFakeBusinessNameOverrideStorageExceptions:
    def test_list_pending(self):
        from src.storage.audit_storage import FakeBusinessNameOverrideStorage, ColumnOverride
        fake = FakeBusinessNameOverrideStorage()
        fake.upsert(ColumnOverride("t", "c", "bn", "def", "alice", "pending_approval"))
        assert len(fake.list_pending()) == 1

    def test_approve(self):
        from src.storage.audit_storage import FakeBusinessNameOverrideStorage, ColumnOverride
        fake = FakeBusinessNameOverrideStorage()
        fake.upsert(ColumnOverride("t", "c", "bn", "def", "alice", "pending_approval"))
        fake.approve("t", "c")
        assert len(fake.list_pending()) == 0

    def test_reject(self):
        from src.storage.audit_storage import FakeBusinessNameOverrideStorage, ColumnOverride
        fake = FakeBusinessNameOverrideStorage()
        fake.upsert(ColumnOverride("t", "c", "bn", "def", "alice", "pending_approval"))
        fake.reject("t", "c")
        assert len(fake.list_pending()) == 0
