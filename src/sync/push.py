"""Queue and Push logic for Databricks write-back."""

import json
import logging
import os
import re
import uuid

from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import _get_write_connection
from src.config import CATALOG_CACHE, SCHEMA_CACHE

_SYNC_MAX_ATTEMPTS = 3
# Mid-range batch size — daemon runs in its own process so there's no UI
# latency budget to protect.
_SYNC_BATCH_SIZE = 25
# Unity Catalog identifier validator. UC permits only [A-Za-z0-9_], so anything
# outside this set in a column or table-name part is either a metadata bug or
# an injection attempt — refuse rather than backtick-escape.
# Matches strings containing only 1 or more alphanumeric characters and underscores.
_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")

# Lightweight email syntax check — used to block quote-escape bypass when
# writing the steward tag value.
# Matches basic email structures (e.g., user@domain.com):
# - Local part: alphanumeric characters, dots, underscores, percents, pluses, and hyphens.
# - Domain part: alphanumeric characters, dots, and hyphens.
# - TLD: at least 2 alphabetic characters.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _safe_ident(part: str) -> str:
    """Return part wrapped in backticks, refusing anything not [A-Za-z0-9_]."""
    if not part or not _IDENT_RE.match(part):
        raise ValueError(f"Refusing to interpolate unsafe identifier: {part!r}")
    return f"`{part}`"


def _split_full_name(table_full_name: str) -> tuple[str, str, str]:
    """Validate and split catalog.schema.table into safely-quoted parts."""
    parts = (table_full_name or "").split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected catalog.schema.table, got {table_full_name!r}")
    return _safe_ident(parts[0]), _safe_ident(parts[1]), _safe_ident(parts[2])


def enqueue_sync(sync_type: str, table_full_name: str | None, payload: dict, queued_by: str) -> None:
    """Add an action to the Databricks write-back queue.

    For metadata sync types ('COLUMN_DEF', 'TABLE_DESC', 'STEWARD'), this method
    upserts the action by deleting previous pending items for the same target
    to avoid duplicate work.

    @param sync_type: The type of metadata to sync (e.g., 'COLUMN_DEF', 'TABLE_DESC', 'STEWARD', 'AUDIT', 'COMMENT').
    @param table_full_name: The Unity Catalog full name of the table (catalog.schema.table), or None if not applicable.
    @param payload: A dictionary containing the type-specific data for the sync operation.
    @param queued_by: The identifier (e.g., email) of the user who initiated the action.
    """
    if not _duckdb_available():
        return
    sync_id = str(uuid.uuid4())
    conn = _get_write_connection()
    payload_str = json.dumps(payload)
    with conn.cursor() as cursor:
        # For metadata types, we upsert to avoid duplicate pending work for the same object
        if sync_type in ("COLUMN_DEF", "TABLE_DESC", "STEWARD"):
            _key_col = "payload_json->>'column_name'" if sync_type == "COLUMN_DEF" else "NULL"
            _match_val = payload.get("column_name") if sync_type == "COLUMN_DEF" else None

            # Simple cleanup of previous pending items for the same target
            # Note: payload_json check is slightly complex in SQL so we target by table and sync_type primarily
            _del_q = "DELETE FROM user_data.pending_sync WHERE sync_type = %(st)s AND status = 'pending'"
            _params = {"st": sync_type}
            if table_full_name:
                _del_q += " AND table_full_name = %(fn)s"
                _params["fn"] = table_full_name

            if _match_val:
                # We fetch and filter in Python for simplicity with DuckDB JSON extensions
                cursor.execute("SELECT sync_id, payload_json FROM user_data.pending_sync WHERE sync_type='COLUMN_DEF' AND status='pending' AND table_full_name=%(fn)s", {"fn": table_full_name})
                for row in cursor.fetchall():
                    try:
                        p = json.loads(row[1])
                        if p.get("column_name") == _match_val:
                            cursor.execute("DELETE FROM user_data.pending_sync WHERE sync_id=%(id)s", {"id": row[0]})
                    except Exception:
                        pass
            else:
                cursor.execute_write(_del_q, _params)

        cursor.execute_write(
            "INSERT INTO user_data.pending_sync (sync_id, sync_type, table_full_name, payload_json, queued_by, queued_at) VALUES (%(id)s, %(type)s, %(tbl)s, %(json)s, %(by)s, current_timestamp())",
            {"id": sync_id, "type": sync_type, "tbl": table_full_name, "json": payload_str, "by": queued_by}
        )

def enqueue_column_sync(table_full_name: str, column_name: str, definition: str, queued_by: str) -> None:
    """Legacy wrapper for column definitions."""
    enqueue_sync("COLUMN_DEF", table_full_name, {"column_name": column_name, "definition": definition}, queued_by)


def _push_to_databricks(sync_type: str, table_full_name: str | None, payload: dict) -> None:
    """Generalized dispatcher to push different types of changes to Databricks.

    Executes the appropriate SQL command against the Databricks SQL Warehouse
    based on the sync_type. Supports updating column definitions, table descriptions,
    steward tags, and inserting audit logs or comments.

    @param sync_type: The type of metadata change to push (e.g., 'COLUMN_DEF', 'TABLE_DESC', 'STEWARD', 'AUDIT', 'COMMENT').
    @param table_full_name: The Unity Catalog full name of the table (catalog.schema.table), or None if not applicable.
    @param payload: A dictionary containing the data to push, matching the sync_type requirements.
    """
    host = os.getenv("DATABRICKS_HOST", "").strip()
    http_path = os.getenv("DATABRICKS_HTTP_PATH", "").strip()
    token = os.getenv("DATABRICKS_TOKEN", "").strip()
    if not (host and http_path and token):
        raise RuntimeError("Databricks credentials not configured.")

    from databricks import sql as dbsql

    with dbsql.connect(server_hostname=host, http_path=http_path, access_token=token) as db_conn:
        with db_conn.cursor() as cur:
            if sync_type == "COLUMN_DEF":
                col = _safe_ident(payload["column_name"])
                cat, sch, tbl = _split_full_name(table_full_name)
                cur.execute(
                    f"ALTER TABLE {cat}.{sch}.{tbl} ALTER COLUMN {col} SET COMMENT %(comment)s",
                    {"comment": payload.get("definition") or ""},
                )

            elif sync_type == "TABLE_DESC":
                cat, sch, tbl = _split_full_name(table_full_name)
                cur.execute(
                    f"COMMENT ON TABLE {cat}.{sch}.{tbl} IS %(comment)s",
                    {"comment": payload.get("definition") or ""},
                )

            elif sync_type == "STEWARD":
                # Steward is stored as a Unity Catalog tag. Reject anything that
                # is not a syntactically valid email so the f-string can't be
                # broken out of by a crafted value.
                steward = (payload.get("steward_email") or "").strip()
                if steward and not _EMAIL_RE.match(steward):
                    raise ValueError(f"Refusing to set non-email steward value: {steward!r}")
                cat, sch, tbl = _split_full_name(table_full_name)
                try:
                    cur.execute(
                        f"ALTER TABLE {cat}.{sch}.{tbl} SET TAGS ('steward' = %(steward)s)",
                        {"steward": steward},
                    )
                except Exception as e:
                    logging.warning("Could not set steward tag on %s: %s", table_full_name, e)

            elif sync_type == "AUDIT":
                audit_tbl = f"{CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log"
                cur.execute(
                    f"INSERT INTO {audit_tbl} (event_id, event_type, object_type, object_name, actor_email, old_value, new_value, created_at) "
                    f"VALUES (%(event_id)s, %(event_type)s, %(object_type)s, %(object_name)s, %(actor_email)s, %(old_value)s, %(new_value)s, current_timestamp())",
                    payload
                )

            elif sync_type == "COMMENT":
                comm_tbl = f"{CATALOG_CACHE}.{SCHEMA_CACHE}.comments"
                cur.execute(
                    f"INSERT INTO {comm_tbl} (comment_id, object_type, object_name, comment_text, author_name, author_email, created_at, steward_email, parent_comment_id) "
                    f"VALUES (%(comment_id)s, %(object_type)s, %(object_name)s, %(comment_text)s, %(author_name)s, %(author_email)s, current_timestamp(), %(steward_email)s, %(parent_comment_id)s)",
                    payload
                )

            else:
                # Unknown sync_type: do nothing but log loudly so a typo in
                # the queue doesn't silently mark rows 'done'.
                logging.warning(
                    "Unknown sync_type %r — no Databricks push performed.",
                    sync_type,
                )


def _push_definition_to_databricks(table_full_name: str, column_name: str, definition: str) -> None:
    """Legacy wrapper for backward compatibility."""
    _push_to_databricks("COLUMN_DEF", table_full_name, {"column_name": column_name, "definition": definition})


def _process_sync_queue(conn=None) -> int:
    """Drain pending sync items → Databricks. Returns number of items attempted.

    @param conn: Optional injected connection (used by the sidecar daemon
                 with its own DuckDB handle). When None, falls back to the
                 Streamlit-cached _get_write_connection.

    Priority ordering (weight ASC, queued_at ASC):
        1. Metadata    — COLUMN_DEF, TABLE_DESC
        2. Tags/comms  — STEWARD, TAG, COMMENT
        3. Audit log   — AUDIT
    """
    if conn is None:
        if not _duckdb_available():
            return 0
        conn = _get_write_connection()
    batch_size = _SYNC_BATCH_SIZE
    try:
        with conn.cursor() as cursor:
            # Multi-tier priority: order by sync_type weight, then by age
            # Weights: COLUMN_DEF/TABLE_DESC=1, STEWARD/TAG/COMMENT=2, AUDIT=3
            priority_sql = """
                CASE
                    WHEN sync_type IN ('COLUMN_DEF', 'TABLE_DESC') THEN 1
                    WHEN sync_type IN ('STEWARD', 'TAG', 'COMMENT') THEN 2
                    ELSE 3
                END
            """
            cursor.execute(
                f"SELECT sync_id, sync_type, table_full_name, payload_json, attempts "
                f"FROM user_data.pending_sync "
                f"WHERE status = 'pending' AND attempts < %(max)s "
                f"ORDER BY {priority_sql} ASC, queued_at ASC LIMIT %(limit)s",
                {"max": _SYNC_MAX_ATTEMPTS, "limit": batch_size},
            )
            rows = cursor.fetchall()

        if not rows:
            return 0

        processed = 0
        for row in rows:
            sync_id, stype, table_fn, payload_str, attempts = row
            payload = json.loads(payload_str)
            new_attempts = attempts + 1

            # Optimistic update: mark syncing
            with conn.cursor() as cursor:
                cursor.execute_write(
                    "UPDATE user_data.pending_sync SET status='syncing', attempts=%(att)s, last_attempt_at=current_localtimestamp() WHERE sync_id=%(id)s",
                    {"att": new_attempts, "id": sync_id},
                )

            try:
                _push_to_databricks(stype, table_fn, payload)

                with conn.cursor() as cursor:
                    cursor.execute_write(
                        "UPDATE user_data.pending_sync SET status='done', completed_at=current_localtimestamp(), last_error=NULL WHERE sync_id=%(id)s",
                        {"id": sync_id},
                    )
                processed += 1
            except Exception as exc:
                err = str(exc)[:500]
                new_status = "failed" if new_attempts >= _SYNC_MAX_ATTEMPTS else "pending"
                with conn.cursor() as cursor:
                    cursor.execute_write(
                        "UPDATE user_data.pending_sync SET status=%(st)s, last_error=%(err)s WHERE sync_id=%(id)s",
                        {"st": new_status, "err": err, "id": sync_id},
                    )
                logging.warning("Sync %s (%s) failed: %s", sync_id[:8], stype, err)

        return processed
    except Exception as e:
        logging.error("Error processing sync queue: %s", e)
        return 0
