"""Tests for src/sync/push.py.

Coverage matches TODO.md #6:
  - One test per sync type (COLUMN_DEF, TABLE_DESC, STEWARD, AUDIT, COMMENT).
  - Unknown sync_type emits a warning and does not call cursor.execute.
  - _safe_ident rejects backticks, dots, semicolons, non-ASCII.
  - _split_full_name rejects 2-part and 4-part names.
  - STEWARD with non-email value raises ValueError.

The Databricks SQL connector is stubbed at the conftest level
(``sys.modules['databricks.sql']`` is a MagicMock) — so we just call
``_push_to_databricks`` and assert against ``conftest._push_cursor()``,
which returns the same cursor mock the function will see.
"""

from __future__ import annotations

import logging
import sys

import pytest


def _push_cursor():
    """Return the cursor mock that ``_push_to_databricks`` will execute against.

    push.py uses ``with dbsql.connect(...) as conn: with conn.cursor() as cur``,
    so the path through the conftest's ``sys.modules['databricks.sql']``
    MagicMock is two ``__enter__``s deep. tests/conftest.py's
    ``_push_cursor()`` walks a different (one-``__enter__``) path used by
    the read query layer, so it doesn't apply here.
    """
    return (
        sys.modules["databricks.sql"]
        .connect.return_value.__enter__.return_value
        .cursor.return_value.__enter__.return_value
    )


@pytest.fixture(autouse=True)
def reset_push_cursor():
    """Reset the with-block cursor mock between tests."""
    cur = _push_cursor()
    cur.reset_mock()
    cur.execute.side_effect = None
    yield
    cur.reset_mock()


@pytest.fixture
def databricks_env(monkeypatch):
    """Provide DATABRICKS_* env vars so _push_to_databricks gets past the creds check."""
    monkeypatch.setenv("DATABRICKS_HOST", "host.example.com")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/abc")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test-token")


# ── Identifier whitelist helpers ─────────────────────────────────────────────

class TestSafeIdent:
    @pytest.mark.parametrize("part", [
        "table", "TABLE", "table_1", "Table_1_2", "_underscore", "abc123",
    ])
    def test_accepts_valid(self, part):
        from src.sync.push import _safe_ident
        assert _safe_ident(part) == f"`{part}`"

    @pytest.mark.parametrize("bad", [
        "table`drop", "table.column", "table;DROP TABLE x",
        "table-name", "table name", "tαble", "café",
        "", "   ",
    ])
    def test_rejects_unsafe(self, bad):
        from src.sync.push import _safe_ident
        with pytest.raises(ValueError, match="unsafe identifier"):
            _safe_ident(bad)


class TestSplitFullName:
    def test_accepts_three_parts(self):
        from src.sync.push import _split_full_name
        assert _split_full_name("cat.sch.tbl") == ("`cat`", "`sch`", "`tbl`")

    @pytest.mark.parametrize("bad", [
        "cat.sch",                  # 2 parts
        "cat.sch.tbl.extra",        # 4 parts
        "single",                   # 1 part
        "",                         # empty
        "cat..tbl",                 # empty schema
    ])
    def test_rejects_wrong_part_count(self, bad):
        from src.sync.push import _split_full_name
        with pytest.raises(ValueError):
            _split_full_name(bad)


# ── Per-sync-type dispatch ───────────────────────────────────────────────────

class TestPushToDatabricks:
    def test_column_def_alters_column_comment(self, databricks_env):
        from src.sync.push import _push_to_databricks
        _push_to_databricks(
            "COLUMN_DEF", "cat.sch.tbl",
            {"column_name": "col_a", "definition": "hello"},
        )
        sql, params = _push_cursor().execute.call_args.args
        assert "ALTER TABLE `cat`.`sch`.`tbl`" in sql
        assert "ALTER COLUMN `col_a`" in sql
        assert "SET COMMENT %(comment)s" in sql
        assert params["comment"] == "hello"

    def test_column_def_uses_parameters_for_definition(self, databricks_env):
        from src.sync.push import _push_to_databricks
        _push_to_databricks(
            "COLUMN_DEF", "cat.sch.tbl",
            {"column_name": "col_a", "definition": "it's tricky"},
        )
        sql, params = _push_cursor().execute.call_args.args
        assert params["comment"] == "it's tricky"

    def test_table_desc_emits_comment_on_table(self, databricks_env):
        from src.sync.push import _push_to_databricks
        _push_to_databricks(
            "TABLE_DESC", "cat.sch.tbl", {"definition": "primary fact table"},
        )
        sql, params = _push_cursor().execute.call_args.args
        assert "COMMENT ON TABLE `cat`.`sch`.`tbl` IS %(comment)s" in sql
        assert params["comment"] == "primary fact table"

    def test_steward_sets_unity_catalog_tag(self, databricks_env):
        from src.sync.push import _push_to_databricks
        _push_to_databricks(
            "STEWARD", "cat.sch.tbl", {"steward_email": "alice@example.com"},
        )
        sql, params = _push_cursor().execute.call_args.args
        assert "ALTER TABLE `cat`.`sch`.`tbl` SET TAGS" in sql
        assert "'steward' = %(steward)s" in sql
        assert params["steward"] == "alice@example.com"

    def test_steward_rejects_non_email(self, databricks_env):
        from src.sync.push import _push_to_databricks
        with pytest.raises(ValueError, match="non-email steward"):
            _push_to_databricks(
                "STEWARD", "cat.sch.tbl",
                {"steward_email": "alice'; DROP TABLE x;--"},
            )

    def test_steward_empty_string_is_allowed(self, databricks_env):
        """Clearing the steward (empty string) bypasses the email check."""
        from src.sync.push import _push_to_databricks
        _push_to_databricks("STEWARD", "cat.sch.tbl", {"steward_email": ""})
        sql = _push_cursor().execute.call_args.args[0]
        assert "'steward' = %(steward)s" in sql

    def test_audit_inserts_into_catalog_audit_log(self, databricks_env):
        from src.sync.push import _push_to_databricks
        payload = {
            "event_id": "e1", "event_type": "test_event",
            "object_type": "TABLE", "object_name": "cat.sch.tbl",
            "actor_email": "alice@x.com", "old_value": "", "new_value": "x",
        }
        _push_to_databricks("AUDIT", None, payload)
        sql, bound = _push_cursor().execute.call_args.args
        assert "INSERT INTO data_governance.dictionary_cache.audit_log" in sql
        assert bound is payload

    def test_comment_inserts_into_catalog_comments(self, databricks_env):
        from src.sync.push import _push_to_databricks
        payload = {
            "comment_id": "c1", "object_type": "TABLE", "object_name": "cat.sch.tbl",
            "comment_text": "useful note", "author_name": "Alice",
            "author_email": "alice@x.com", "steward_email": None,
            "parent_comment_id": None,
        }
        _push_to_databricks("COMMENT", None, payload)
        sql, bound = _push_cursor().execute.call_args.args
        assert "INSERT INTO data_governance.dictionary_cache.comments" in sql
        assert bound is payload

    def test_unknown_sync_type_warns_and_skips_execute(self, databricks_env, caplog):
        from src.sync.push import _push_to_databricks
        with caplog.at_level(logging.WARNING):
            _push_to_databricks("WHO_KNOWS", "cat.sch.tbl", {})
        assert any("Unknown sync_type" in rec.message for rec in caplog.records)
        _push_cursor().execute.assert_not_called()

    def test_missing_credentials_raises(self, monkeypatch):
        for var in ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        from src.sync.push import _push_to_databricks
        with pytest.raises(RuntimeError, match="Databricks credentials"):
            _push_to_databricks("COLUMN_DEF", "a.b.c", {})

    def test_column_def_rejects_backtick_in_column_name(self, databricks_env):
        """Identifier whitelist refuses anything not [A-Za-z0-9_]."""
        from src.sync.push import _push_to_databricks
        with pytest.raises(ValueError, match="unsafe identifier"):
            _push_to_databricks(
                "COLUMN_DEF", "cat.sch.tbl",
                {"column_name": "col`; DROP", "definition": "x"},
            )

    def test_table_desc_rejects_dotted_table_part(self, databricks_env):
        """A 4-part table_full_name (catalog.schema.tbl.extra) is refused."""
        from src.sync.push import _push_to_databricks
        with pytest.raises(ValueError, match="catalog.schema.table"):
            _push_to_databricks("TABLE_DESC", "cat.sch.tbl.extra", {"definition": "x"})
