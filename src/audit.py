# ruff: noqa: E402
from __future__ import annotations
"""Audit logging and business-name-override write paths.

Storage delegated to ``src.storage`` — see ``AuditStorage`` and
``BusinessNameOverrideStorage``. This module owns the cross-cutting
concerns: validation, permission checks, audit-trail emission, and the
side effects on the local search cache.

Note on table-metadata writes (``save_table_metadata``): the local UPDATE
against ``data_governance.dictionary_cache.tables_metadata`` writes to
the read-only-attached catalog file in production and silently raises;
the durable change is the ``enqueue_sync`` to Databricks. Migration of
that path is deferred — see TODO.md (out-of-scope follow-ups).
"""
from typing import Optional


import logging
import uuid

import streamlit as st

from src.auth import is_admin
from src.config import (
    CATALOG_CACHE,
    MAX_BUSINESS_NAME_LEN,
    MAX_DEFINITION_LEN,
    SCHEMA_CACHE,
    is_demo_mode,
)
from src.db.duckdb_adapter import (
    _db_write_lock,
    _duckdb_available,
    _get_shared_duckdb_connection,
)
from src.db.queries import (
    _get_write_connection,
    get_authorized_tables,
    get_db_connection,
    search_all_metadata,
)
from src.personalization import is_power_user
from src.storage import get_audit_storage, get_business_name_override_storage
from src.storage.audit_storage import ColumnOverride
from src.sync.push import enqueue_column_sync, enqueue_sync


def log_audit_event(
    event_type: str,
    object_type: str,
    object_name: str,
    old_value: str,
    new_value: str,
) -> None:
    """Record an audit event and enqueue it for Databricks sync.

    Local persistence routes through ``AuditStorage``; Databricks sync
    happens via the sidecar daemon (``enqueue_sync``).
    """
    actor_email = st.session_state.get("user_email", "")
    event = {
        "event_id":    str(uuid.uuid4()),
        "event_type":  event_type,
        "object_type": object_type,
        "object_name": object_name,
        "actor_email": actor_email,
        "old_value":   old_value,
        "new_value":   new_value,
    }
    get_audit_storage().append(event)
    if not is_demo_mode():
        enqueue_sync("AUDIT", None, event, actor_email)


def save_table_metadata(
    table_full_name: str,
    description: Optional[str] = None,
    steward_email: Optional[str] = None,
) -> None:
    """Persist table description/steward locally and enqueue for Databricks sync.

    Local durability: writes to user_data.table_metadata_overrides (readable
    immediately). Catalog cache (read-only) is left untouched — it refreshes
    nightly via the sync job.
    """
    if not is_power_user():
        raise PermissionError("Only power users can update table metadata.")

    user_name = st.session_state.get("user_name", "unknown")

    if _duckdb_available():
        conn = _get_write_connection()
        with conn.cursor() as cursor:
            cursor.execute_write(
                """
                INSERT INTO user_data.table_metadata_overrides
                    (table_full_name, description, steward_email, updated_by, updated_at)
                VALUES (%(fn)s, %(desc)s, %(stew)s, %(by)s, current_localtimestamp())
                ON CONFLICT (table_full_name) DO UPDATE SET
                    description   = COALESCE(excluded.description,   user_data.table_metadata_overrides.description),
                    steward_email = COALESCE(excluded.steward_email, user_data.table_metadata_overrides.steward_email),
                    updated_by    = excluded.updated_by,
                    updated_at    = current_localtimestamp()
                """,
                {
                    "fn":   table_full_name,
                    "desc": description,
                    "stew": steward_email,
                    "by":   user_name,
                },
            )

        if description is not None:
            enqueue_sync("TABLE_DESC", table_full_name, {"definition": description}, user_name)
            log_audit_event("table_description_change", "TABLE", table_full_name, "N/A", description)

        if steward_email is not None:
            enqueue_sync("STEWARD", table_full_name, {"steward_email": steward_email}, user_name)
            log_audit_event("table_steward_change", "TABLE", table_full_name, "N/A", steward_email)

        try:
            with _db_write_lock:
                _get_shared_duckdb_connection().execute("CHECKPOINT user_data")
        except Exception:
            pass

    search_all_metadata.clear()
    get_authorized_tables.clear()


def _validate_business_name_inputs(business_name: str, definition: str) -> None:
    if not is_power_user():
        raise PermissionError("Only power users can save business name overrides.")
    if business_name and len(business_name) > MAX_BUSINESS_NAME_LEN:
        raise ValueError(
            f"Business name must be {MAX_BUSINESS_NAME_LEN} characters or fewer "
            f"(got {len(business_name)})."
        )
    if definition and len(definition) > MAX_DEFINITION_LEN:
        raise ValueError(
            f"Definition must be {MAX_DEFINITION_LEN} characters or fewer "
            f"(got {len(definition)})."
        )


def _get_old_business_name(table_full_name: str, column_name: str) -> str:
    """Look up the existing business name for an audit-trail diff."""
    overrides = get_business_name_override_storage().get_for_table(table_full_name)
    return overrides.get(column_name, {}).get("business_name", "")


def save_business_name(
    table_full_name: str,
    column_name: str,
    business_name: str,
    definition: str = "",
) -> None:
    """Upsert a column override and emit an audit event.

    Admins publish immediately (status='published') and enqueue sync.
    Non-admin power users create a pending proposal (status='pending_approval')
    that requires admin approval before syncing to Databricks.
    """
    _validate_business_name_inputs(business_name, definition)
    user_name = st.session_state.get("user_name", "unknown")
    old_value = _get_old_business_name(table_full_name, column_name)

    _admin = is_admin()
    _status = "published" if _admin else "pending_approval"

    override = ColumnOverride(
        table_full_name=table_full_name,
        column_name=column_name,
        business_name=business_name,
        definition=definition,
        edited_by=user_name,
        status=_status,
    )
    get_business_name_override_storage().upsert(override)

    if _duckdb_available():
        try:
            with _db_write_lock:
                _get_shared_duckdb_connection().execute("CHECKPOINT user_data")
        except Exception:
            pass
        if _admin:
            enqueue_column_sync(table_full_name, column_name, definition, user_name)

    log_audit_event(
        "business_name_change", "COLUMN", f"{table_full_name}.{column_name}",
        old_value, business_name,
    )
    search_all_metadata.clear()


def approve_business_name(table_full_name: str, column_name: str) -> None:
    """Approve a pending column override: publish it and enqueue Databricks sync."""
    if not is_admin():
        raise PermissionError("Only admins can approve metadata changes.")
    storage = get_business_name_override_storage()
    pending = {
        r["column_name"]: r
        for r in storage.list_pending()
        if r["table_full_name"] == table_full_name
    }
    item = pending.get(column_name)
    if item is None:
        return
    storage.approve(table_full_name, column_name)
    user_name = st.session_state.get("user_name", "unknown")
    if _duckdb_available():
        enqueue_column_sync(table_full_name, column_name, item.get("definition", ""), user_name)
        try:
            with _db_write_lock:
                _get_shared_duckdb_connection().execute("CHECKPOINT user_data")
        except Exception:
            pass
    search_all_metadata.clear()


def reject_business_name(table_full_name: str, column_name: str) -> None:
    """Reject and discard a pending column override."""
    if not is_admin():
        raise PermissionError("Only admins can reject metadata changes.")
    get_business_name_override_storage().reject(table_full_name, column_name)
    search_all_metadata.clear()


def get_table_steward(table_full_name: str) -> str:
    """Return steward_email: checks local overrides first, then catalog cache."""
    if is_demo_mode():
        return "steward@example.com"
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Local overrides take precedence (immediately after save_table_metadata)
            if _duckdb_available():
                cursor.execute(
                    "SELECT steward_email FROM user_data.table_metadata_overrides "
                    "WHERE table_full_name = %(fn)s LIMIT 1",
                    {"fn": table_full_name},
                )
                row = cursor.fetchall_as_pandas()
                if row is not None and not row.empty:
                    val = str(row.iloc[0].get("steward_email", "") or "")
                    if val:
                        return val
            cursor.execute(
                f"SELECT steward_email FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata "
                f"WHERE full_name = %(full_name)s LIMIT 1",
                {"full_name": table_full_name},
            )
            row = cursor.fetchall_as_pandas()
            if row is not None and not row.empty:
                return str(row.iloc[0]["steward_email"] or "")
    except Exception as e:
        logging.warning("Could not fetch steward for %s: %s", table_full_name, e)
    return ""
