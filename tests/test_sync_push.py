"""Tests for src/sync/push.py.

Coverage matches TODO.md #6:
- [x] Identifier whitelist (`_safe_ident`)
- [x] 3-part name parser (`_split_full_name`)
- [x] Per-sync-type dispatch (COLUMN_DEF, TABLE_DESC, STEWARD, AUDIT, COMMENT)
- [x] STEWARD rejects non-email values (`ValueError`)
- [x] Unknown sync_type logs a warning
- [x] Missing credentials raise RuntimeError
- [x] _sync_comments batch processing
- [x] _sync_business_names error handling

The Databricks SQL connector is stubbed at the conftest level
(``sys.modules['databricks.sql']`` is a MagicMock) — so we just call
``_push_to_databricks`` and assert against ``conftest._push_cursor()``,
which returns the same cursor mock the function will see.
"""

from __future__ import annotations

import logging
import sys

from unittest.mock import MagicMock
from src.sync.push import _build_summary, _notify_bookmarkers
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
        "table", "TABLE", "table_1", "Table_1_2", "_underscore", "abc123", "table-name",
    ])
    def test_accepts_valid(self, part):
        from src.sync.push import _safe_ident
        assert _safe_ident(part) == f"`{part}`"

    @pytest.mark.parametrize("bad", [
        "table`drop", "table.column", "table;DROP TABLE x",
        "table name", "tαble", "café",
        "", "   ", " ",
    ])
    def test_rejects_unsafe(self, bad):
        from src.sync.push import _safe_ident
        with pytest.raises(ValueError, match="unsafe identifier"):
            _safe_ident(bad)


class TestSplitFullName:
    def test_accepts_three_parts(self):
        from src.sync.push import _split_full_name
        assert _split_full_name("cat.sch.tbl") == ["cat", "sch", "tbl"]

    @pytest.mark.parametrize("bad", [
        "cat.sch",                  # 2 parts
        "cat.sch.tbl.extra",        # 4 parts
        "single",                   # 1 part
        "",                         # empty
        "cat..tbl",                 # empty schema
        "cat.sch. ",                # whitespace
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
        assert "ALTER TABLE IDENTIFIER(%(tbl)s)" in sql
        assert "ALTER COLUMN IDENTIFIER(%(col)s)" in sql
        assert "SET COMMENT %(comment)s" in sql
        assert params["tbl"] == ["cat", "sch", "tbl"]
        assert params["col"] == ["col_a"]
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
        assert "COMMENT ON TABLE IDENTIFIER(%(tbl)s) IS %(comment)s" in sql
        assert params["tbl"] == ["cat", "sch", "tbl"]
        assert params["comment"] == "primary fact table"

    def test_steward_sets_unity_catalog_tag(self, databricks_env):
        from src.sync.push import _push_to_databricks
        _push_to_databricks(
            "STEWARD", "cat.sch.tbl", {"steward_email": "alice@example.com"},
        )
        sql, params = _push_cursor().execute.call_args.args
        assert "ALTER TABLE IDENTIFIER(%(tbl)s) SET TAGS" in sql
        assert "'steward' = %(steward)s" in sql
        assert params["tbl"] == ["cat", "sch", "tbl"]
        assert params["steward"] == "alice@example.com"

    @pytest.mark.parametrize("bad_email", [
        "alice'; DROP TABLE x;--",
        "alice@x",
        "alice.com",
        "alice@ x.com",
        "alice@x.c",
    ])
    def test_steward_rejects_non_email(self, databricks_env, bad_email):
        from src.sync.push import _push_to_databricks
        with pytest.raises(ValueError, match="non-email steward"):
            _push_to_databricks(
                "STEWARD", "cat.sch.tbl",
                {"steward_email": bad_email},
            )

    @pytest.mark.parametrize("empty_val", ["", "   "])
    def test_steward_empty_string_is_allowed(self, databricks_env, empty_val):
        """Clearing the steward (empty string) bypasses the email check."""
        from src.sync.push import _push_to_databricks
        _push_to_databricks(
            "STEWARD", "cat.sch.tbl",
            {"steward_email": empty_val},
        )
        sql, params = _push_cursor().execute.call_args.args
        assert "'steward' = %(steward)s" in sql
        assert params["steward"] == empty_val.strip()

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
        assert bound["actor_email"] == "9293c9abc55b4cebee3c8b7c134f2389e4fcef4d6cb0160997d0f36abd117c51"
        assert bound is not payload

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
        assert bound["author_email"] == "9293c9abc55b4cebee3c8b7c134f2389e4fcef4d6cb0160997d0f36abd117c51"
        assert bound is not payload

    def test_unknown_sync_type_warns_and_skips_execute(self, databricks_env, caplog):
        from src.sync.push import _push_to_databricks
        with caplog.at_level(logging.WARNING):
            _push_to_databricks("WHO_KNOWS", "cat.sch.tbl", {})
        assert any("Unknown sync_type" in rec.message for rec in caplog.records)
        _push_cursor().execute.assert_not_called()

    @pytest.mark.parametrize("missing_var", [
        "DATABRICKS_HOST",
        "DATABRICKS_HTTP_PATH",
        "DATABRICKS_TOKEN",
    ])
    def test_missing_credentials_raises(self, monkeypatch, missing_var):
        # Set all credentials first
        monkeypatch.setenv("DATABRICKS_HOST", "host.example.com")
        monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/abc")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test-token")
        # Then remove the specific one being tested
        monkeypatch.delenv(missing_var, raising=False)
        from src.sync.push import _push_to_databricks
        with pytest.raises(RuntimeError, match="Databricks credentials"):
            _push_to_databricks("COLUMN_DEF", "a.b.c", {})

    def test_network_error_on_connect_bubbles_up(self, databricks_env):
        """Simulate a network timeout or DNS error when connecting to Databricks."""
        import sys
        from src.sync.push import _push_to_databricks
        db_sql_mock = sys.modules["databricks.sql"]
        db_sql_mock.connect.side_effect = Exception("Connection timeout")

        with pytest.raises(Exception, match="Connection timeout"):
            _push_to_databricks("TABLE_DESC", "cat.sch.tbl", {"definition": "x"})

        db_sql_mock.connect.side_effect = None

    def test_network_error_on_execute_bubbles_up(self, databricks_env):
        """Simulate a network error during query execution (e.g., connection lost)."""
        from src.sync.push import _push_to_databricks
        _push_cursor().execute.side_effect = Exception("Network dropped during execute")

        with pytest.raises(Exception, match="Network dropped during execute"):
            _push_to_databricks("AUDIT", None, {"event_id": "e1"})

    def test_column_def_empty_column_name(self, databricks_env):
        """An empty column name should be rejected by the identifier validator."""
        from src.sync.push import _push_to_databricks
        with pytest.raises(ValueError, match="unsafe identifier"):
            _push_to_databricks("COLUMN_DEF", "cat.sch.tbl", {"column_name": "", "definition": "x"})

    def test_column_def_missing_definition_defaults_to_empty(self, databricks_env):
        """If definition is omitted, it should default to empty string."""
        from src.sync.push import _push_to_databricks
        _push_to_databricks("COLUMN_DEF", "cat.sch.tbl", {"column_name": "col_a"})
        sql, params = _push_cursor().execute.call_args.args
        assert params["comment"] == ""

    def test_table_desc_missing_definition_defaults_to_empty(self, databricks_env):
        """If definition is omitted for TABLE_DESC, it should default to empty string."""
        from src.sync.push import _push_to_databricks
        _push_to_databricks("TABLE_DESC", "cat.sch.tbl", {})
        sql, params = _push_cursor().execute.call_args.args
        assert params["comment"] == ""

    @pytest.mark.parametrize("bad_col", [
        "col`; DROP",
        "col name",
        "col.name",
        "c\u03b1fe",
    ])
    def test_column_def_rejects_unsafe_column_name(self, databricks_env, bad_col):
        """Identifier whitelist refuses anything not [A-Za-z0-9_]."""
        from src.sync.push import _push_to_databricks
        with pytest.raises(ValueError, match="unsafe identifier"):
            _push_to_databricks(
                "COLUMN_DEF", "cat.sch.tbl",
                {"column_name": bad_col, "definition": "x"},
            )

    @pytest.mark.parametrize("bad_tbl, err_match", [
        ("cat.sch.tbl.extra", "catalog.schema.table"),
        ("cat.sch", "catalog.schema.table"),
        ("single", "catalog.schema.table"),
        ("", "catalog.schema.table"),
        ("cat..tbl", "unsafe identifier"),
    ])
    def test_table_desc_rejects_invalid_table_part(self, databricks_env, bad_tbl, err_match):
        """A 4-part table_full_name (catalog.schema.tbl.extra) or other invalid shapes are refused."""
        from src.sync.push import _push_to_databricks
        with pytest.raises(ValueError, match=err_match):
            _push_to_databricks("TABLE_DESC", bad_tbl, {"definition": "x"})

# ── Queue processing coverage ──────────────────────────────────────────────────

class TestProcessSyncQueue:
    def test_process_sync_queue_duckdb_unavailable(self, monkeypatch):
        from src.sync import push as push_module
        monkeypatch.setattr(push_module, "_duckdb_available", lambda: False)
        assert push_module._process_sync_queue() == 0

    def test_process_sync_queue_empty(self, monkeypatch):
        from src.sync import push as push_module
        monkeypatch.setattr(push_module, "_duckdb_available", lambda: True)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        monkeypatch.setattr(push_module, "_get_write_connection", lambda: mock_conn)
        assert push_module._process_sync_queue() == 0

    def test_process_sync_queue_db_error(self, monkeypatch):
        from src.sync import push as push_module
        monkeypatch.setattr(push_module, "_duckdb_available", lambda: True)
        mock_conn = MagicMock()
        mock_conn.cursor.side_effect = Exception("db connection error")
        monkeypatch.setattr(push_module, "_get_write_connection", lambda: mock_conn)
        assert push_module._process_sync_queue() == 0

    def test_process_sync_queue_success(self, monkeypatch):
        from src.sync import push as push_module
        import json
        monkeypatch.setattr(push_module, "_duckdb_available", lambda: True)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("sync1", "COLUMN_DEF", "tbl1", json.dumps({"col": "A"}), 0, "actor@x.com")
        ]
        monkeypatch.setattr(push_module, "_get_write_connection", lambda: mock_conn)

        mock_push = MagicMock()
        monkeypatch.setattr(push_module, "_push_to_databricks", mock_push)
        monkeypatch.setattr(push_module, "_notify_bookmarkers", MagicMock())

        assert push_module._process_sync_queue() == 1
        mock_push.assert_called_once_with("COLUMN_DEF", "tbl1", {"col": "A"})

        mock_cursor.execute_write.assert_any_call(
            "UPDATE user_data.pending_sync SET status='syncing', attempts=%(att)s, last_attempt_at=current_localtimestamp() WHERE sync_id=%(id)s",
            {"att": 1, "id": "sync1"}
        )
        mock_cursor.execute_write.assert_any_call(
            "UPDATE user_data.pending_sync SET status='done', completed_at=current_localtimestamp(), last_error=NULL WHERE sync_id=%(id)s",
            {"id": "sync1"}
        )

    def test_process_sync_queue_failure_retry(self, monkeypatch):
        from src.sync import push as push_module
        import json
        monkeypatch.setattr(push_module, "_duckdb_available", lambda: True)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("sync1", "COLUMN_DEF", "tbl1", json.dumps({"col": "A"}), 0, "actor@x.com")
        ]
        monkeypatch.setattr(push_module, "_get_write_connection", lambda: mock_conn)

        mock_push = MagicMock(side_effect=Exception("push error"))
        monkeypatch.setattr(push_module, "_push_to_databricks", mock_push)

        assert push_module._process_sync_queue() == 0
        mock_push.assert_called_once()

        mock_cursor.execute_write.assert_any_call(
            "UPDATE user_data.pending_sync SET status=%(st)s, last_error=%(err)s WHERE sync_id=%(id)s",
            {"st": "pending", "err": "push error", "id": "sync1"}
        )

    def test_process_sync_queue_failure_max_attempts(self, monkeypatch):
        from src.sync import push as push_module
        import json
        monkeypatch.setattr(push_module, "_duckdb_available", lambda: True)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("sync1", "COLUMN_DEF", "tbl1", json.dumps({"col": "A"}), 2, "actor@x.com")  # max attempts is 3
        ]
        monkeypatch.setattr(push_module, "_get_write_connection", lambda: mock_conn)

        mock_push = MagicMock(side_effect=Exception("push error"))
        monkeypatch.setattr(push_module, "_push_to_databricks", mock_push)

        assert push_module._process_sync_queue() == 0

        mock_cursor.execute_write.assert_any_call(
            "UPDATE user_data.pending_sync SET status=%(st)s, last_error=%(err)s WHERE sync_id=%(id)s",
            {"st": "failed", "err": "push error", "id": "sync1"}
        )

class TestEnqueueSync:
    def test_enqueue_sync_duckdb_not_available(self, monkeypatch):
        from src.sync import push as push_module
        monkeypatch.setattr(push_module, "_duckdb_available", lambda: False)
        assert push_module.enqueue_sync("COLUMN_DEF", "cat.sch.tbl", {}, "user") is None

    def test_enqueue_column_sync_calls_enqueue_sync(self, monkeypatch):
        from src.sync import push as push_module
        calls = []
        monkeypatch.setattr(push_module, "enqueue_sync", lambda *args: calls.append(args))
        push_module.enqueue_column_sync("cat.sch.tbl", "col", "def", "user")
        assert calls == [("COLUMN_DEF", "cat.sch.tbl", {"column_name": "col", "definition": "def"}, "user")]

    def test_enqueue_sync_column_def(self, monkeypatch):
        from src.sync import push as push_module
        monkeypatch.setattr(push_module, "_duckdb_available", lambda: True)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        monkeypatch.setattr(push_module, "_get_write_connection", lambda: mock_conn)

        push_module.enqueue_sync("COLUMN_DEF", "cat.sch.tbl", {"column_name": "col_a", "definition": "test"}, "user")

        assert mock_cursor.execute_write.call_count == 2
        delete_call_args = mock_cursor.execute_write.call_args_list[0][0]
        assert "DELETE FROM user_data.pending_sync WHERE sync_type = %(st)s" in delete_call_args[0]
        assert "payload_json->>'column_name' = %(col)s" in delete_call_args[0]
        assert delete_call_args[1] == {"st": "COLUMN_DEF", "fn": "cat.sch.tbl", "col": "col_a"}


    def test_enqueue_sync_table_desc(self, monkeypatch):
        from src.sync import push as push_module
        monkeypatch.setattr(push_module, "_duckdb_available", lambda: True)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        monkeypatch.setattr(push_module, "_get_write_connection", lambda: mock_conn)

        push_module.enqueue_sync("TABLE_DESC", "cat.sch.tbl", {"definition": "test"}, "user")

        mock_cursor.execute_write.assert_any_call(
            "DELETE FROM user_data.pending_sync WHERE sync_type = %(st)s AND status = 'pending' AND table_full_name = %(fn)s",
            {"st": "TABLE_DESC", "fn": "cat.sch.tbl"}
        )

    def test_steward_sets_tag_error(self, monkeypatch, caplog):
        from tests.test_sync_push import _push_cursor
        mock_cursor = _push_cursor()
        mock_cursor.execute.side_effect = Exception("Databricks offline")

        import logging
        caplog.set_level(logging.WARNING)

        from src.sync import push as push_module
        monkeypatch.setenv("DATABRICKS_HOST", "host.example.com")
        monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/abc")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test-token")

        push_module._push_to_databricks("STEWARD", "cat.sch.tbl", {"steward_email": "alice@x.com"})

        assert any("Could not set steward tag on cat.sch.tbl" in record.message for record in caplog.records)

from unittest.mock import patch

def test_enqueue_table_business_name_sync():
    with patch("src.sync.push.enqueue_sync") as mock_enqueue:
        from src.sync.push import enqueue_table_business_name_sync
        enqueue_table_business_name_sync("c.s.t", "en", "fr", "def_en", "def_fr", "user")
        mock_enqueue.assert_called_once_with(
            "TABLE_BUSINESS_NAME",
            "c.s.t",
            {
                "business_name_en": "en",
                "business_name_fr": "fr",
                "business_definition_en": "def_en",
                "business_definition_fr": "def_fr"
            },
            "user"
        )


def test_push_to_databricks_table_business_name(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "host")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "path")
    monkeypatch.setenv("DATABRICKS_TOKEN", "token")

    class MockConn:
        def __init__(self):
            self.cursor_mock = type('obj', (object,), {'execute': lambda self, *args: None, '__enter__': lambda self: self, '__exit__': lambda *args: None})()
            self.cursor_mock.execute = __import__('unittest').mock.MagicMock()
        def cursor(self):
            return self.cursor_mock
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    mock_conn = MockConn()
    monkeypatch.setattr("databricks.sql.connect", lambda **kwargs: mock_conn)

    mock_cursor = mock_conn.cursor_mock
    from src.sync.push import _push_to_databricks
    _push_to_databricks("TABLE_BUSINESS_NAME", "c.s.t", {
        "business_name_en": "en",
        "business_name_fr": "fr",
        "business_definition_en": "def_en",
        "business_definition_fr": "def_fr"
    })
    mock_cursor.execute.assert_called_once()
    args = mock_cursor.execute.call_args[0]
    assert "MERGE INTO" in args[0]
    assert args[1]["full_name"] == "c.s.t"

def test_build_summary():
    assert _build_summary("TABLE_DESC", {}) == "Description updated"
    assert _build_summary("COLUMN_DEF", {"column_name": "foo"}) == "Column 'foo' definition updated"
    assert _build_summary("COLUMN_DEF", {}) == "Column definition updated"
    assert _build_summary("STEWARD", {"steward_email": "a@b.c"}) == "Steward changed to a@b.c"
    assert _build_summary("STEWARD", {}) == "Steward updated"
    assert _build_summary("UNKNOWN", {}) == "Table updated"

def test_notify_bookmarkers_success():
    conn = MagicMock()
    cur_mock = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur_mock

    # 2 rows returned, one is the author, one is another user
    cur_mock.fetchall.return_value = [("user_other",), ("user_author",)]

    _notify_bookmarkers(conn, "test.schema.tbl", "TABLE_DESC", {}, "user_author")

    # Check that we fetched bookmarkers
    cur_mock.execute.assert_called_once()
    assert "user_data.user_preferences" in cur_mock.execute.call_args[0][0]

    # Check that we only inserted one notification for the other user
    assert cur_mock.executemany_write.call_count == 1
    call_args = cur_mock.executemany_write.call_args[0]
    assert call_args[1][0][1] == "user_other"

def test_notify_bookmarkers_empty():
    conn = MagicMock()
    cur_mock = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur_mock
    cur_mock.fetchall.return_value = []

    _notify_bookmarkers(conn, "test.schema.tbl", "TABLE_DESC", {}, "user_author")

    cur_mock.execute_write.assert_not_called()

def test_notify_bookmarkers_exception():
    conn = MagicMock()
    conn.cursor.side_effect = Exception("db error")

    # Should not raise exception (fail gracefully)
    _notify_bookmarkers(conn, "test.schema.tbl", "TABLE_DESC", {}, "user_author")
