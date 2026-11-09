"""Queue and Push logic for Databricks write-back."""
from __future__ import annotations
from typing import Optional

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import _get_write_connection
from src.config import CATALOG_CACHE, SCHEMA_CACHE

_SYNC_MAX_ATTEMPTS = 3
# Mid-range batch size — daemon runs in its own process so there's no UI
# latency budget to protect.
_SYNC_BATCH_SIZE = 25
# Unity Catalog identifier validator.
#
# WHY IT EXISTS:
# We dynamically build SQL strings (e.g., ALTER TABLE, COMMENT ON) using identifiers
# fetched from user input or external databases. Databricks Unity Catalog limits
# valid identifiers strictly to alphanumeric characters, underscores, and hyphens.
# Rather than attempting complex and error-prone backtick-escaping for arbitrary
# strings, we defensively reject any identifier containing disallowed characters.
# By rigorously asserting that an identifier strictly contains alphanumeric
# characters, underscores, or hyphens, we block any malicious payloads
# (like semicolons or quotes) from reaching the Databricks warehouse, acting
# as an absolute safeguard against SQL injection vectors embedded within
# table or column names (e.g., "my_table`; DROP TABLE foo;").
#
# REGEX BREAKDOWN:
# ^                - Enforces matching strictly from the start of the string.
# [A-Za-z0-9_-]+   - Matches one or more allowed characters: letters, digits, _, -.
# \Z               - Enforces matching strictly to the absolute end of the string
#                    (ignoring trailing newlines, unlike $ which can be bypassed).
_IDENT_RE = re.compile(r"^[A-Za-z0-9_-]+\Z")

# Lightweight email syntax validator for the steward tag.
#
# WHY IT EXISTS:
# The "steward" metadata field in Databricks is stored as a Unity Catalog tag,
# which requires f-string interpolation when executing the SET TAGS command.
# If a malicious user supplies an email like "admin'@example.com", the single quote
# could break the SQL string boundary, enabling command injection. By rigorously
# enforcing the structure of a standard email address, we block any string
# containing dangerous payload characters (quotes, semicolons, etc.).
#
# REGEX BREAKDOWN:
# ^                    - Enforces matching strictly from the start of the string.
# [A-Za-z0-9._%+\-]+   - Local part: standard email characters (letters, digits, symbols).
# @                    - Literal @ symbol separating local and domain parts.
# [A-Za-z0-9.\-]+      - Domain part: letters, digits, dots, and hyphens.
# \.                   - Literal dot separating the domain name and TLD.
# [A-Za-z]{2,}         - Top-Level Domain (TLD): at least 2 alphabetic characters.
# \Z                   - Enforces matching strictly to the absolute end of the string.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\Z")


def _safe_ident(part: str) -> str:
    """Return part wrapped in backticks, refusing anything not [A-Za-z0-9_-].

    Args:
        part (str): The identifier part to sanitize and wrap.

    Returns:
        str: The safely backtick-quoted identifier.

    Raises:
        ValueError: If the identifier contains invalid characters, preventing SQL injection.
    """
    if not part or not _IDENT_RE.match(part):
        raise ValueError(f"Refusing to interpolate unsafe identifier: {part!r}")
    return f"`{part}`"


def _split_full_name(table_full_name: str) -> list[str]:
    """Validate and split catalog.schema.table into safely-quoted parts.

    The `table_full_name` strictly corresponds to the Databricks Unity Catalog
    3-level namespace structure. It must contain exactly three parts separated by dots.

    Args:
        table_full_name (str): The full table name in `catalog.schema.table` format.

    Returns:
        list[str]: A list of three validated identifier parts.

    Raises:
        ValueError: If the string does not have exactly three dot-separated parts or contains invalid characters.
    """
    parts = (table_full_name or "").split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected catalog.schema.table, got {table_full_name!r}")
    for part in parts:
        if not part or not _IDENT_RE.match(part):
            raise ValueError(f"Refusing to interpolate unsafe identifier: {part!r}")
    return parts


def enqueue_sync(sync_type: str, table_full_name: Optional[str], payload: dict, queued_by: str) -> None:
    """Add an action to the Databricks write-back queue.

    For metadata sync types ('COLUMN_DEF', 'TABLE_DESC', 'STEWARD'), this method
    upserts the action by deleting previous pending items for the same target
    to avoid duplicate work.

    Args:
        sync_type (str): The type of metadata to sync (e.g., 'COLUMN_DEF', 'TABLE_DESC', 'STEWARD', 'AUDIT', 'COMMENT').
        table_full_name (str): The Unity Catalog full name of the table (catalog.schema.table), or None if not applicable.
        payload (dict): A dictionary containing the type-specific data for the sync operation.
        queued_by (str): The identifier (e.g., email) of the user who initiated the action.
    """
    if not _duckdb_available():
        return
    sync_id = str(uuid.uuid4())
    conn = _get_write_connection()
    payload_str = json.dumps(payload)
    with conn.cursor() as cursor:
        # For metadata types, we upsert to avoid duplicate pending work for the same object
        if sync_type in ("COLUMN_DEF", "TABLE_DESC", "STEWARD", "TABLE_BUSINESS_NAME"):
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
                # ⚡ Bolt: vectorized deletion using DuckDB JSON extension to fix N+1
                _del_q += " AND payload_json->>'column_name' = %(col)s"
                _params["col"] = _match_val
            cursor.execute_write(_del_q, _params)

        cursor.execute_write(
            "INSERT INTO user_data.pending_sync (sync_id, sync_type, table_full_name, payload_json, queued_by, queued_at) VALUES (%(id)s, %(type)s, %(tbl)s, %(json)s, %(by)s, current_timestamp())",
            {"id": sync_id, "type": sync_type, "tbl": table_full_name, "json": payload_str, "by": queued_by}
        )

def enqueue_column_sync(table_full_name: str, column_name: str, definition: str, queued_by: str) -> None:
    """Legacy wrapper for column definitions."""
    enqueue_sync("COLUMN_DEF", table_full_name, {"column_name": column_name, "definition": definition}, queued_by)


def enqueue_table_business_name_sync(
    table_full_name: str,
    business_name_en: str,
    business_name_fr: str,
    definition_en: str,
    definition_fr: str,
    queued_by: str,
) -> None:
    """Queue a write-back of the bilingual friendly name into the UC reference table.

    The sidecar drains TABLE_BUSINESS_NAME via MERGE against the table
    configured by ``BUSINESS_NAMES_TABLE`` in the environment.
    """
    enqueue_sync(
        "TABLE_BUSINESS_NAME",
        table_full_name,
        {
            "business_name_en":       business_name_en or "",
            "business_name_fr":       business_name_fr or "",
            "business_definition_en": definition_en or "",
            "business_definition_fr": definition_fr or "",
        },
        queued_by,
    )


def _push_to_databricks(sync_type: str, table_full_name: Optional[str], payload: dict) -> None:
    """Generalized dispatcher to push different types of changes to Databricks.

    Executes the appropriate SQL command against the Databricks SQL Warehouse
    based on the sync_type. Supports updating column definitions, table descriptions,
    steward tags, and inserting audit logs or comments.

    Args:
        sync_type (str): The type of metadata change to push (e.g., 'COLUMN_DEF', 'TABLE_DESC', 'STEWARD', 'AUDIT', 'COMMENT').
        table_full_name (str): The Unity Catalog full name of the table (catalog.schema.table), or None if not applicable.
        payload (dict): A dictionary containing the data to push, matching the sync_type requirements.
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
                tbl_parts = _split_full_name(table_full_name)
                # Ensure column name is validated
                if not payload["column_name"] or not _IDENT_RE.match(payload["column_name"]):
                    raise ValueError(f"Refusing to interpolate unsafe identifier: {payload['column_name']!r}")

                cur.execute(
                    "ALTER TABLE IDENTIFIER(%(tbl)s) ALTER COLUMN IDENTIFIER(%(col)s) SET COMMENT %(comment)s",
                    {
                        "tbl": tbl_parts,
                        "col": [payload["column_name"]],
                        "comment": payload.get("definition") or "",
                    },
                )

            elif sync_type == "TABLE_DESC":
                tbl_parts = _split_full_name(table_full_name)
                cur.execute(
                    "COMMENT ON TABLE IDENTIFIER(%(tbl)s) IS %(comment)s",
                    {"tbl": tbl_parts, "comment": payload.get("definition") or ""},
                )

            elif sync_type == "STEWARD":
                # Steward is stored as a Unity Catalog tag. Reject anything that
                # is not a syntactically valid email so the f-string can't be
                # broken out of by a crafted value.
                steward = (payload.get("steward_email") or "").strip()
                if steward and not _EMAIL_RE.match(steward):
                    raise ValueError(f"Refusing to set non-email steward value: {steward!r}")
                tbl_parts = _split_full_name(table_full_name)
                try:
                    cur.execute(
                        "ALTER TABLE IDENTIFIER(%(tbl)s) SET TAGS ('steward' = %(steward)s)",
                        {"tbl": tbl_parts, "steward": steward},
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

            elif sync_type == "TABLE_BUSINESS_NAME":
                # MERGE the bilingual friendly name into the configured UC
                # reference table. Column names are configurable via env vars
                # so the source can move/rename without a code change — we
                # still validate every identifier through _IDENT_RE before
                # interpolation to prevent SQL injection from a malicious .env.
                from src.config import (  # noqa: PLC0415
                    BUSINESS_NAMES_TABLE,
                    BUSINESS_NAMES_COL_FULL_NAME,
                    BUSINESS_NAMES_COL_NAME_EN,
                    BUSINESS_NAMES_COL_NAME_FR,
                    BUSINESS_NAMES_COL_DEF_EN,
                    BUSINESS_NAMES_COL_DEF_FR,
                )
                # Validate the table name (must be catalog.schema.table) and
                # every column identifier — defense in depth against a
                # tampered .env. Backtick-quote on use.
                _tbl_parts_target = _split_full_name(BUSINESS_NAMES_TABLE)
                _quoted_tbl = ".".join(f"`{p}`" for p in _tbl_parts_target)
                _quoted = {
                    "fn":      _safe_ident(BUSINESS_NAMES_COL_FULL_NAME),
                    "name_en": _safe_ident(BUSINESS_NAMES_COL_NAME_EN),
                    "name_fr": _safe_ident(BUSINESS_NAMES_COL_NAME_FR),
                    "def_en":  _safe_ident(BUSINESS_NAMES_COL_DEF_EN),
                    "def_fr":  _safe_ident(BUSINESS_NAMES_COL_DEF_FR),
                }
                cur.execute(
                    f"MERGE INTO {_quoted_tbl} AS t "
                    f"USING (SELECT %(full_name)s AS full_name, "
                    f"              %(name_en)s  AS name_en, "
                    f"              %(name_fr)s  AS name_fr, "
                    f"              %(def_en)s   AS def_en, "
                    f"              %(def_fr)s   AS def_fr) AS s "
                    f"ON t.{_quoted['fn']} = s.full_name "
                    f"WHEN MATCHED THEN UPDATE SET "
                    f"  t.{_quoted['name_en']} = s.name_en, "
                    f"  t.{_quoted['name_fr']} = s.name_fr, "
                    f"  t.{_quoted['def_en']}  = s.def_en, "
                    f"  t.{_quoted['def_fr']}  = s.def_fr "
                    f"WHEN NOT MATCHED THEN INSERT "
                    f"  ({_quoted['fn']}, {_quoted['name_en']}, {_quoted['name_fr']}, "
                    f"   {_quoted['def_en']}, {_quoted['def_fr']}) "
                    f"  VALUES (s.full_name, s.name_en, s.name_fr, s.def_en, s.def_fr)",
                    {
                        "full_name": table_full_name,
                        "name_en":   payload.get("business_name_en", ""),
                        "name_fr":   payload.get("business_name_fr", ""),
                        "def_en":    payload.get("business_definition_en", ""),
                        "def_fr":    payload.get("business_definition_fr", ""),
                    },
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


# ── Bookmark notifications ────────────────────────────────────────────────────

_NOTIFIABLE_TYPES = frozenset({"TABLE_DESC", "COLUMN_DEF", "STEWARD"})


def _build_summary(sync_type: str, payload: dict) -> str:
    """Generate a human-readable summary of the metadata change for notifications.

    Args:
        sync_type (str): The type of metadata that was synced (e.g., 'TABLE_DESC', 'COLUMN_DEF', 'STEWARD').
        payload (dict): The dictionary containing the specific data updated, such as column names or steward emails.

    Returns:
        str: A short, descriptive string indicating what changed (e.g., 'Column "id" definition updated').
    """
    if sync_type == "TABLE_DESC":
        return "Description updated"
    if sync_type == "COLUMN_DEF":
        col = payload.get("column_name", "")
        return f"Column '{col}' definition updated" if col else "Column definition updated"
    if sync_type == "STEWARD":
        steward = payload.get("steward_email", "")
        return f"Steward changed to {steward}" if steward else "Steward updated"
    return "Table updated"


def _notify_bookmarkers(conn, table_full_name: str, sync_type: str, payload: dict, changed_by: str) -> None:
    """Insert an unread notification for every user who bookmarked table_full_name.

    Skips the user who made the change so authors don't get self-notifications.
    Failures are logged and swallowed — notification delivery must never block
    or fail a sync cycle.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_oid FROM user_data.user_preferences "
                "WHERE table_full_name = ? AND pref_type = 'bookmark'",
                [table_full_name],
            )
            rows = cur.fetchall() or []

        if not rows:
            return

        summary = _build_summary(sync_type, payload)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        params_list = []
        for (user_oid,) in rows:
            if user_oid == changed_by:
                continue
            nid = str(uuid.uuid4())
            params_list.append([nid, user_oid, table_full_name, sync_type, changed_by, summary, now])

        if params_list:
            with conn.cursor() as cur:
                cur.executemany_write(
                    """
                    INSERT INTO user_data.notifications
                        (notification_id, user_oid, table_full_name, change_type,
                         changed_by, summary, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    params_list,
                )
    except Exception as exc:
        logging.warning(
            "Could not notify bookmarkers of %s (%s): %s", table_full_name, sync_type, exc
        )


def _process_sync_queue(conn=None) -> int:
    """Drain pending sync items → Databricks. Returns number of items attempted.

    Args:
        conn (Optional): Optional injected connection (used by the sidecar daemon
            with its own DuckDB handle). When None, falls back to the
            Streamlit-cached _get_write_connection.

    Returns:
        int: The number of sync items that were processed (either successful or failed).

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
                    WHEN sync_type IN ('COLUMN_DEF', 'TABLE_DESC', 'TABLE_BUSINESS_NAME') THEN 1
                    WHEN sync_type IN ('STEWARD', 'TAG', 'COMMENT') THEN 2
                    ELSE 3
                END
            """
            cursor.execute(
                f"SELECT sync_id, sync_type, table_full_name, payload_json, attempts, queued_by "
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
            sync_id, stype, table_fn, payload_str, attempts, queued_by = row
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

                if table_fn and stype in _NOTIFIABLE_TYPES:
                    _notify_bookmarkers(conn, table_fn, stype, payload, queued_by or "")

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
