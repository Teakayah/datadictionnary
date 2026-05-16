"""Tests for src/storage/preference_storage.py — PreferenceStorage and
SiteSettingStorage backends."""

from __future__ import annotations

import duckdb
import pytest

from src.storage.preference_storage import (
    DemoPreferenceStorage,
    DemoSiteSettingStorage,
    DuckDBPreferenceStorage,
    DuckDBSiteSettingStorage,
    FakePreferenceStorage,
    FakeSiteSettingStorage,
    PreferenceStorage,
    SiteSettingStorage,
)


# ── Protocol satisfaction ────────────────────────────────────────────────────

@pytest.mark.parametrize("cls", [
    DemoPreferenceStorage, DuckDBPreferenceStorage, FakePreferenceStorage,
])
def test_preference_implementations_satisfy_protocol(cls):
    assert isinstance(cls(), PreferenceStorage)


@pytest.mark.parametrize("cls", [
    DemoSiteSettingStorage, DuckDBSiteSettingStorage, FakeSiteSettingStorage,
])
def test_site_setting_implementations_satisfy_protocol(cls):
    assert isinstance(cls(), SiteSettingStorage)


# ── Fake behaviour ───────────────────────────────────────────────────────────

class TestFakePreferenceStorage:
    def test_upsert_then_list(self):
        fake = FakePreferenceStorage()
        fake.upsert("u1", "a.b.c", "bookmark")
        fake.upsert("u1", "d.e.f", "bookmark")
        # Newest first.
        assert fake.list_by_type("u1", "bookmark") == ["d.e.f", "a.b.c"]

    def test_upsert_idempotent_per_key(self):
        """Upserting the same (oid, table, type) twice keeps one row."""
        fake = FakePreferenceStorage()
        fake.upsert("u1", "a.b.c", "bookmark")
        fake.upsert("u1", "a.b.c", "bookmark")
        assert fake.list_by_type("u1", "bookmark") == ["a.b.c"]

    def test_list_filters_by_user_and_type(self):
        fake = FakePreferenceStorage()
        fake.upsert("u1", "tab_1", "bookmark")
        fake.upsert("u2", "tab_2", "bookmark")
        fake.upsert("u1", "tab_1", "recent")
        assert fake.list_by_type("u1", "bookmark") == ["tab_1"]
        assert fake.list_by_type("u2", "bookmark") == ["tab_2"]
        assert fake.list_by_type("u1", "recent")   == ["tab_1"]

    def test_list_respects_limit(self):
        fake = FakePreferenceStorage()
        for tbl in ("a", "b", "c", "d", "e"):
            fake.upsert("u1", tbl, "recent")
        assert fake.list_by_type("u1", "recent", limit=3) == ["e", "d", "c"]

    def test_delete_removes_only_match(self):
        fake = FakePreferenceStorage()
        fake.upsert("u1", "a", "bookmark")
        fake.upsert("u1", "b", "bookmark")
        fake.delete("u1", "a", "bookmark")
        assert fake.list_by_type("u1", "bookmark") == ["b"]


class TestDemoPreferenceStorage:
    def test_all_methods_are_noops(self):
        demo = DemoPreferenceStorage()
        demo.upsert("u1", "a", "bookmark")
        demo.delete("u1", "a", "bookmark")
        assert demo.list_by_type("u1", "bookmark") == []


class TestFakeSiteSettingStorage:
    def test_get_missing_returns_none(self):
        assert FakeSiteSettingStorage().get("editing_enabled") is None

    def test_set_then_get(self):
        fake = FakeSiteSettingStorage()
        fake.set("editing_enabled", "1", "admin@test.com")
        assert fake.get("editing_enabled") == "1"

    def test_set_overwrites(self):
        fake = FakeSiteSettingStorage({"editing_enabled": "1"})
        fake.set("editing_enabled", "0", "admin@test.com")
        assert fake.get("editing_enabled") == "0"


class TestDemoSiteSettingStorage:
    def test_get_returns_none(self):
        assert DemoSiteSettingStorage().get("any") is None

    def test_set_is_noop(self):
        demo = DemoSiteSettingStorage()
        demo.set("any", "1", "admin")
        assert demo.get("any") is None


# ── DuckDB backend smoke test ────────────────────────────────────────────────

class TestDuckDBStoragesRoundTrip:
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
        import src.storage.preference_storage
        importlib.reload(src.storage.preference_storage)

        from src.storage.preference_storage import (
            DuckDBPreferenceStorage,
            DuckDBSiteSettingStorage,
        )
        return DuckDBPreferenceStorage(), DuckDBSiteSettingStorage()

    def test_preference_round_trip(self, storages):
        prefs, _ = storages
        prefs.upsert("u1", "a.b.c", "bookmark")
        prefs.upsert("u1", "d.e.f", "bookmark")
        # Newest first → d.e.f then a.b.c.
        result = prefs.list_by_type("u1", "bookmark")
        assert set(result) == {"a.b.c", "d.e.f"}
        prefs.delete("u1", "a.b.c", "bookmark")
        assert prefs.list_by_type("u1", "bookmark") == ["d.e.f"]

    def test_site_setting_round_trip(self, storages):
        _, settings = storages
        assert settings.get("editing_enabled") is None
        settings.set("editing_enabled", "1", "admin@test.com")
        assert settings.get("editing_enabled") == "1"
        settings.set("editing_enabled", "0", "admin@test.com")
        assert settings.get("editing_enabled") == "0"

class TestDuckDBPreferenceStorageExceptions:
    def test_upsert_exception(self, monkeypatch):
        def mock_get_db_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.preference_storage.get_db_connection", mock_get_db_connection)
        from src.storage.preference_storage import DuckDBPreferenceStorage
        storage = DuckDBPreferenceStorage()
        storage.upsert("oid", "tbl", "fav") # should catch

    def test_delete_exception(self, monkeypatch):
        def mock_get_db_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.preference_storage.get_db_connection", mock_get_db_connection)
        from src.storage.preference_storage import DuckDBPreferenceStorage
        storage = DuckDBPreferenceStorage()
        storage.delete("oid", "tbl", "fav") # should catch

    def test_list_by_type_exception(self, monkeypatch):
        def mock_get_db_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.preference_storage.get_db_connection", mock_get_db_connection)
        from src.storage.preference_storage import DuckDBPreferenceStorage
        storage = DuckDBPreferenceStorage()
        assert storage.list_by_type("oid", "fav") == []

class TestDuckDBSiteSettingStorageExceptions:
    def test_get_exception(self, monkeypatch):
        def mock_get_db_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.preference_storage.get_db_connection", mock_get_db_connection)
        from src.storage.preference_storage import DuckDBSiteSettingStorage
        storage = DuckDBSiteSettingStorage()
        assert storage.get("key") is None

    def test_set_exception(self, monkeypatch):
        def mock_get_db_connection():
            raise Exception("DB error")
        monkeypatch.setattr("src.storage.preference_storage._get_write_connection", mock_get_db_connection)
        from src.storage.preference_storage import DuckDBSiteSettingStorage
        storage = DuckDBSiteSettingStorage()
        storage.set("key", "val", "alice") # should catch

class TestGetSiteSettingStorage:
    def test_returns_demo_when_demo_mode(self, monkeypatch):
        monkeypatch.setenv("DEMO_DATA", "true")
        from src.storage import get_site_setting_storage
        assert type(get_site_setting_storage()).__name__ == "DemoSiteSettingStorage"

class TestGetPreferenceStorage:
    def test_returns_demo_when_demo_mode(self, monkeypatch):
        monkeypatch.setenv("DEMO_DATA", "true")
        from src.storage import get_preference_storage
        assert type(get_preference_storage()).__name__ == "DemoPreferenceStorage"
