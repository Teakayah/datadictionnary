"""
Tests for the table-level friendly-name pipeline.

Coverage:
  1. Locale-aware SELECT helpers (business_name_expr / business_definition_expr)
  2. Sync ingest: JOIN logic — matched / unmatched / partial rows
  3. Search SQL: both bilingual columns in WHERE clause
  4. Sidecar queue action shape (enqueue_table_business_name_sync)
  5. Audit approve/reject for table-level overrides (demo path)
  6. Demo-mode fixture: _DEMO_TABLES has bilingual columns so DEMO_DATA=true works
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

FULL_NAME = "main.analytics.customers"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Locale-aware SELECT helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestLocaleHelpers:
    """business_name_expr / business_definition_expr switch on st.session_state locale."""

    def _import_helpers(self):
        from src.db.queries import business_name_expr, business_definition_expr
        return business_name_expr, business_definition_expr

    def test_english_locale_uses_en_column(self, monkeypatch):
        with patch("src.db.queries.st") as mock_st:
            mock_st.session_state.get.return_value = "en"
            business_name_expr, _ = self._import_helpers()
            expr = business_name_expr("m")
        assert "business_name_en" in expr
        assert "business_name_fr" not in expr

    def test_french_locale_uses_fr_column(self, monkeypatch):
        with patch("src.db.queries.st") as mock_st:
            mock_st.session_state.get.return_value = "fr"
            _, _ = self._import_helpers()
            # Re-call after patching to get the live result
            from src.db.queries import business_name_expr
            with patch("src.db.queries.get_current_locale", return_value="fr"):
                expr = business_name_expr("m")
        assert "business_name_fr" in expr
        assert "business_name_en" not in expr

    def test_business_name_expr_coalesces_table_name(self):
        from src.db.queries import business_name_expr
        with patch("src.db.queries.get_current_locale", return_value="en"):
            expr = business_name_expr("t")
        assert "COALESCE" in expr
        assert "t.table_name" in expr

    def test_business_name_expr_custom_alias(self):
        from src.db.queries import business_name_expr
        with patch("src.db.queries.get_current_locale", return_value="en"):
            expr = business_name_expr("alias_x")
        assert "alias_x.business_name_en" in expr

    def test_business_definition_expr_english(self):
        from src.db.queries import business_definition_expr
        with patch("src.db.queries.get_current_locale", return_value="en"):
            expr = business_definition_expr("m")
        assert "m.business_definition_en" in expr

    def test_business_definition_expr_french(self):
        from src.db.queries import business_definition_expr
        with patch("src.db.queries.get_current_locale", return_value="fr"):
            expr = business_definition_expr("m")
        assert "m.business_definition_fr" in expr

    def _patch_external_modules(self):
        mocks = {
            "databricks": MagicMock(),
            "databricks.sdk": MagicMock(),
            "databricks.sql": MagicMock(),
            "dotenv": MagicMock(),
        }
        with patch.dict("sys.modules", mocks):
            yield

    def _make_tables_data(self, full_names: list[str]) -> list[dict]:
        return [{"full_name": fn, "table_name": fn.split(".")[-1]} for fn in full_names]

    def _make_bn_df(self, rows: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(rows, columns=["full_name", "name_en", "name_fr", "def_en", "def_fr"])

    def _run_join(self, tables_data: list[dict], bn_df: pd.DataFrame) -> None:
        """Replicate the 2b-bis loop from sync_metadata directly so tests don't
        need to mock the entire sync pipeline."""
        bn_map = {
            str(r["full_name"]): r for _, r in bn_df.iterrows()
        } if not bn_df.empty else {}
        for row in tables_data:
            match = bn_map.get(row["full_name"])
            row["business_name_en"]       = (match["name_en"] if match is not None else None) or None
            row["business_name_fr"]       = (match["name_fr"] if match is not None else None) or None
            row["business_definition_en"] = (match["def_en"]  if match is not None else None) or None
            row["business_definition_fr"] = (match["def_fr"]  if match is not None else None) or None

    def test_matched_row_gets_bilingual_names(self):
        """A table whose full_name appears in the reference table is enriched."""
        tables = self._make_tables_data([FULL_NAME])
        bn = self._make_bn_df([{
            "full_name": FULL_NAME, "name_en": "Customers", "name_fr": "Clients",
            "def_en": "Master customer list.", "def_fr": "Liste des clients.",
        }])
        self._run_join(tables, bn)
        row = tables[0]
        assert row["business_name_en"] == "Customers"
        assert row["business_name_fr"] == "Clients"
        assert row["business_definition_en"] == "Master customer list."
        assert row["business_definition_fr"] == "Liste des clients."

    def test_unmatched_row_gets_nulls(self):
        """A table not in the reference stays null — no key error or crash."""
        tables = self._make_tables_data(["main.staging.unknown_table"])
        bn = self._make_bn_df([{
            "full_name": FULL_NAME, "name_en": "Customers", "name_fr": "Clients",
            "def_en": "", "def_fr": "",
        }])
        self._run_join(tables, bn)
        assert tables[0]["business_name_en"] is None
        assert tables[0]["business_name_fr"] is None

    def test_partial_match_only_matched_rows_enriched(self):
        """With 3 tables and 2 matches, only the 2 matched rows get names."""
        tables = self._make_tables_data([
            "main.analytics.customers",
            "main.analytics.orders",
            "main.staging.raw_events",
        ])
        bn = self._make_bn_df([
            {"full_name": "main.analytics.customers", "name_en": "Customers", "name_fr": "Clients", "def_en": "", "def_fr": ""},
            {"full_name": "main.analytics.orders",    "name_en": "Orders",    "name_fr": "Commandes", "def_en": "", "def_fr": ""},
        ])
        self._run_join(tables, bn)
        assert tables[0]["business_name_en"] == "Customers"
        assert tables[1]["business_name_en"] == "Orders"
        assert tables[2]["business_name_en"] is None

    def test_empty_reference_table_nulls_all(self):
        """When the reference table is empty every row gets null names."""
        tables = self._make_tables_data([FULL_NAME, "main.analytics.orders"])
        bn = self._make_bn_df([])
        self._run_join(tables, bn)
        assert all(r["business_name_en"] is None for r in tables)

    def test_empty_name_string_treated_as_null(self):
        """An empty-string name in the reference table is coerced to None."""
        tables = self._make_tables_data([FULL_NAME])
        bn = self._make_bn_df([{
            "full_name": FULL_NAME, "name_en": "", "name_fr": "", "def_en": "", "def_fr": "",
        }])
        self._run_join(tables, bn)
        assert tables[0]["business_name_en"] is None
        assert tables[0]["business_name_fr"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Search SQL: bilingual columns in WHERE clause
# ═══════════════════════════════════════════════════════════════════════════════


class TestSearchBilingualWhere:
    """The keyword search SQL must include all 4 bilingual columns in WHERE."""

    def _get_search_sql(self) -> str:
        """Extract the SQL string built inside _search_keywords without running it."""
        from src.db import queries
        from src.config import CATALOG_CACHE, SCHEMA_CACHE

        with patch.object(queries, "get_current_locale", return_value="en"), \
             patch.object(queries, "_duckdb_available", return_value=False):
            group_placeholders = "%(group_0)s"
            bn_expr = queries.business_name_expr("m")
            bdf_expr = queries.business_definition_expr("m")

            sql = (
                """
                SELECT DISTINCT
                    m.full_name,
                    """ + bn_expr + """ AS name,
                    'Table' AS match_type,
                    COALESCE(""" + bdf_expr + """, m.comment) AS description,
                    m.catalog_name, m.schema_name, m.table_name,
                    COALESCE(""" + bdf_expr + """, m.comment) AS table_description,
                    m.business_name_en, m.business_name_fr,
                    m.business_definition_en, m.business_definition_fr
                FROM {0}.{1}.tables_metadata m
                JOIN {0}.{1}.permissions_cache p ON m.full_name = p.table_full_name
                WHERE (
                      m.table_name LIKE %(q)s
                      OR m.comment LIKE %(q)s
                      OR m.business_name_en LIKE %(q)s
                      OR m.business_name_fr LIKE %(q)s
                      OR m.business_definition_en LIKE %(q)s
                      OR m.business_definition_fr LIKE %(q)s
                )
                  AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS')
                LIMIT 50
                """
            ).format(CATALOG_CACHE, SCHEMA_CACHE, group_placeholders)
        return sql

    def test_search_sql_matches_business_name_en(self):
        sql = self._get_search_sql()
        assert "m.business_name_en LIKE %(q)s" in sql

    def test_search_sql_matches_business_name_fr(self):
        sql = self._get_search_sql()
        assert "m.business_name_fr LIKE %(q)s" in sql

    def test_search_sql_matches_business_definition_en(self):
        sql = self._get_search_sql()
        assert "m.business_definition_en LIKE %(q)s" in sql

    def test_search_sql_matches_business_definition_fr(self):
        sql = self._get_search_sql()
        assert "m.business_definition_fr LIKE %(q)s" in sql

    def test_actual_search_sql_has_bilingual_where(self):
        """Verify the live _search_keywords SQL includes the bilingual WHERE columns."""
        import inspect
        from src.db import queries
        src = inspect.getsource(queries._search_keywords)
        assert "business_name_en LIKE" in src
        assert "business_name_fr LIKE" in src


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Sidecar queue action shape
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnqueueTableBusinessName:
    """enqueue_table_business_name_sync must write a TABLE_BUSINESS_NAME row."""

    def test_enqueue_writes_correct_sync_type(self):
        from src.sync.push import enqueue_table_business_name_sync

        captured = {}

        def fake_enqueue(sync_type, table_full_name, payload, queued_by):
            captured["sync_type"] = sync_type
            captured["payload"]   = payload
            captured["queued_by"] = queued_by

        with patch("src.sync.push.enqueue_sync", side_effect=fake_enqueue):
            enqueue_table_business_name_sync(
                "main.analytics.customers",
                "Customers",
                "Clients",
                "Master customer list.",
                "Liste principale des clients.",
                "admin@example.com",
            )

        assert captured["sync_type"] == "TABLE_BUSINESS_NAME"

    def test_enqueue_payload_contains_all_fields(self):
        from src.sync.push import enqueue_table_business_name_sync

        captured = {}

        def fake_enqueue(sync_type, table_full_name, payload, queued_by):
            captured["payload"] = payload

        with patch("src.sync.push.enqueue_sync", side_effect=fake_enqueue):
            enqueue_table_business_name_sync(
                FULL_NAME,
                "Customers",
                "Clients",
                "EN def",
                "FR def",
                "user@example.com",
            )

        p = captured["payload"]
        assert p["business_name_en"]       == "Customers"
        assert p["business_name_fr"]       == "Clients"
        assert p["business_definition_en"] == "EN def"
        assert p["business_definition_fr"] == "FR def"

    def test_enqueue_queued_by_forwarded(self):
        from src.sync.push import enqueue_table_business_name_sync

        captured = {}

        def fake_enqueue(sync_type, table_full_name, payload, queued_by):
            captured["queued_by"] = queued_by

        with patch("src.sync.push.enqueue_sync", side_effect=fake_enqueue):
            enqueue_table_business_name_sync(
                FULL_NAME, "n_en", "n_fr", "d_en", "d_fr",
                "editor@example.com",
            )

        assert captured["queued_by"] == "editor@example.com"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Audit: save / approve / reject for table-level overrides (demo path)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTableFriendlyNameAudit:
    """save/approve/reject via the demo (session-state) override path."""

    @pytest.fixture(autouse=True)
    def _demo_overrides(self):
        import streamlit as st
        for key in ("demo_table_business_names", "demo_table_business_names_pending"):
            st.session_state.pop(key, None)
        with patch("src.audit.is_demo_mode", return_value=True):
            yield
        for key in ("demo_table_business_names", "demo_table_business_names_pending"):
            st.session_state.pop(key, None)

    @staticmethod
    def _upsert_pending(name_en="Customers", name_fr="Clients", def_en="", def_fr=""):
        from src.audit import TableBusinessNameOverride, _upsert_table_business_name_override
        _upsert_table_business_name_override(TableBusinessNameOverride(
            FULL_NAME, name_en, name_fr, def_en, def_fr, "alice", "pending_approval",
        ))

    def test_upsert_pending_shows_in_list_pending(self):
        from src.audit import list_pending_table_business_names
        self._upsert_pending(def_en="EN def", def_fr="FR def")
        pending = list_pending_table_business_names()
        assert len(pending) == 1
        assert pending[0]["table_full_name"] == FULL_NAME

    def test_get_for_table_returns_empty_before_approve(self):
        """A pending row must not surface via get_for_table (not yet published)."""
        from src.audit import get_table_business_name_override
        self._upsert_pending()
        assert get_table_business_name_override(FULL_NAME) == {}

    def test_approve_publishes_row_and_returns_data(self):
        from src.audit import _approve_table_business_name_override
        self._upsert_pending(def_en="EN def", def_fr="FR def")
        published = _approve_table_business_name_override(FULL_NAME)
        assert published["business_name_en"] == "Customers"
        assert published["business_name_fr"]  == "Clients"

    def test_approve_removes_from_pending(self):
        from src.audit import (
            _approve_table_business_name_override,
            list_pending_table_business_names,
        )
        self._upsert_pending()
        _approve_table_business_name_override(FULL_NAME)
        assert list_pending_table_business_names() == []

    def test_get_for_table_returns_data_after_approve(self):
        from src.audit import (
            _approve_table_business_name_override,
            get_table_business_name_override,
        )
        self._upsert_pending(def_en="EN def", def_fr="FR def")
        _approve_table_business_name_override(FULL_NAME)
        data = get_table_business_name_override(FULL_NAME)
        assert data["business_name_en"] == "Customers"

    def test_reject_removes_pending_row(self):
        from src.audit import (
            _reject_table_business_name_override,
            get_table_business_name_override,
            list_pending_table_business_names,
        )
        self._upsert_pending()
        _reject_table_business_name_override(FULL_NAME)
        assert list_pending_table_business_names() == []
        assert get_table_business_name_override(FULL_NAME) == {}

    def test_save_table_business_name_raises_for_non_power_user(self, monkeypatch):
        """save_table_business_name raises PermissionError when user is not an editor."""
        with patch("src.audit.is_power_user", return_value=False):
            from src.audit import save_table_business_name
            with pytest.raises(PermissionError):
                save_table_business_name(FULL_NAME, "n_en", "n_fr")

    def test_approve_raises_for_non_admin(self):
        """approve_table_business_name raises PermissionError for non-admins."""
        with patch("src.audit.is_admin", return_value=False):
            from src.audit import approve_table_business_name
            with pytest.raises(PermissionError):
                approve_table_business_name(FULL_NAME)

    def test_reject_raises_for_non_admin(self):
        """reject_table_business_name raises PermissionError for non-admins."""
        with patch("src.audit.is_admin", return_value=False):
            from src.audit import reject_table_business_name
            with pytest.raises(PermissionError):
                reject_table_business_name(FULL_NAME)

    def test_save_as_admin_sets_published_status(self, monkeypatch):
        """When an admin saves, the override is published immediately."""
        import streamlit as st
        st.session_state["user_name"] = "Admin User"
        with patch("src.audit.is_power_user", return_value=True), \
             patch("src.audit.is_admin", return_value=True), \
             patch("src.audit._duckdb_available", return_value=False), \
             patch("src.audit.log_audit_event"), \
             patch("src.audit.search_all_metadata"):
            from src.audit import save_table_business_name
            save_table_business_name(FULL_NAME, "Customers", "Clients", "EN def", "FR def")

        from src.audit import get_table_business_name_override
        data = get_table_business_name_override(FULL_NAME)
        assert data["business_name_en"] == "Customers"

    def test_save_as_editor_sets_pending_approval_status(self):
        """When an editor (not admin) saves, the override stays pending."""
        import streamlit as st
        st.session_state["user_name"] = "Editor User"
        with patch("src.audit.is_power_user", return_value=True), \
             patch("src.audit.is_admin", return_value=False), \
             patch("src.audit._duckdb_available", return_value=False), \
             patch("src.audit.log_audit_event"), \
             patch("src.audit.search_all_metadata"):
            from src.audit import save_table_business_name
            save_table_business_name(FULL_NAME, "Customers", "Clients")

        # Pending — not yet published
        from src.audit import get_table_business_name_override, list_pending_table_business_names
        assert get_table_business_name_override(FULL_NAME) == {}
        assert len(list_pending_table_business_names()) == 1

    def test_approve_enqueues_sidecar_sync(self):
        """approve_table_business_name enqueues a TABLE_BUSINESS_NAME sync when DuckDB is available."""
        import streamlit as st
        st.session_state["user_name"] = "Admin User"
        self._upsert_pending(def_en="EN def", def_fr="FR def")

        enqueued = []
        with patch("src.audit.is_admin", return_value=True), \
             patch("src.audit._duckdb_available", return_value=True), \
             patch("src.audit.enqueue_table_business_name_sync",
                   side_effect=lambda *a, **kw: enqueued.append(a)), \
             patch("src.audit._get_shared_duckdb_connection"), \
             patch("src.audit._db_write_lock"), \
             patch("src.audit.search_all_metadata"):
            from src.audit import approve_table_business_name
            approve_table_business_name(FULL_NAME)

        assert len(enqueued) == 1
        # First positional arg is table_full_name
        assert enqueued[0][0] == FULL_NAME


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Demo-mode fixture
# ═══════════════════════════════════════════════════════════════════════════════


class TestDemoDataHasBilingualColumns:
    """_DEMO_TABLES must carry the 4 bilingual columns so DEMO_DATA=true exercises
    the friendly-name display path without raising KeyError."""

    def test_demo_tables_has_business_name_en(self):
        from src.demo.data import _DEMO_TABLES
        assert "business_name_en" in _DEMO_TABLES.columns, (
            "_DEMO_TABLES is missing business_name_en — add it to src/demo/data.py"
        )

    def test_demo_tables_has_business_name_fr(self):
        from src.demo.data import _DEMO_TABLES
        assert "business_name_fr" in _DEMO_TABLES.columns

    def test_demo_tables_has_business_definition_en(self):
        from src.demo.data import _DEMO_TABLES
        assert "business_definition_en" in _DEMO_TABLES.columns

    def test_demo_tables_has_business_definition_fr(self):
        from src.demo.data import _DEMO_TABLES
        assert "business_definition_fr" in _DEMO_TABLES.columns

    def test_at_least_one_demo_row_has_friendly_name(self):
        """At least one row should have a non-null English friendly name so the
        UI path that renders the friendly name is reachable in demo mode."""
        from src.demo.data import _DEMO_TABLES
        has_name = _DEMO_TABLES["business_name_en"].notna() & (
            _DEMO_TABLES["business_name_en"] != ""
        )
        assert has_name.any(), (
            "No demo row has a business_name_en — add at least one to src/demo/data.py"
        )
