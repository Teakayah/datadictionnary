# ruff: noqa: E402
from __future__ import annotations
"""Audit logging and business-name-override write paths.

Each storage helper branches on ``is_demo_mode()``: demo mode keeps rows in
``st.session_state`` (``demo_audit_log``, ``demo_business_names``,
``demo_table_business_names`` + ``*_pending`` indices), otherwise rows
persist to ``user_data.audit_log`` / ``user_data.business_name_overrides`` /
``user_data.table_business_name_overrides`` in DuckDB. This module owns the
cross-cutting concerns: validation, permission checks, audit-trail emission,
and the side effects on the local search cache.

Note on table-metadata writes (``save_table_metadata``): local durability
is ensured by writing to ``user_data.table_metadata_overrides``. These
overrides are joined back into the core search and catalog queries in
``src.db.queries``, providing immediate feedback for user edits.
"""
from dataclasses import dataclass
from typing import Optional


import logging
import uuid

import pandas as pd
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
    run_query,
    search_all_metadata,
)
from src.personalization import is_power_user
from src.sync.push import enqueue_column_sync, enqueue_sync, enqueue_table_business_name_sync

log = logging.getLogger(__name__)

_DEMO_AUDIT_KEY = "demo_audit_log"
_DEMO_BN_KEY = "demo_business_names"
_DEMO_BN_PENDING_KEY = "demo_business_names_pending"
_DEMO_TBN_KEY = "demo_table_business_names"
_DEMO_TBN_PENDING_KEY = "demo_table_business_names_pending"


@dataclass
class ColumnOverride:
    table_full_name: str
    column_name: str
    business_name: str
    definition: str
    edited_by: str
    status: str = "published"


@dataclass
class TableBusinessNameOverride:
    table_full_name: str
    business_name_en: str
    business_name_fr: str
    business_definition_en: str
    business_definition_fr: str
    edited_by: str
    status: str = "pending_approval"


# ── Audit log storage ────────────────────────────────────────────────────────


def _append_audit_event(event: dict) -> None:
    """Append-only event log. Reads are handled by the admin-page query layer."""
    if is_demo_mode():
        st.session_state.setdefault(_DEMO_AUDIT_KEY, []).append({
            **event,
            "created_at": pd.Timestamp.now(),
        })
        return
    try:
        conn = _get_write_connection()
        with conn.cursor() as cursor:
            cursor.execute_write(
                "INSERT INTO user_data.audit_log "
                "(event_id, event_type, object_type, object_name, "
                " actor_email, old_value, new_value, created_at) "
                "VALUES (%(event_id)s, %(event_type)s, %(object_type)s, "
                " %(object_name)s, %(actor_email)s, %(old_value)s, "
                " %(new_value)s, current_localtimestamp())",
                event,
            )
    except Exception as exc:
        log.warning("Audit logging failed for %s: %s", event.get("event_id"), exc)


def log_audit_event(
    event_type: str,
    object_type: str,
    object_name: str,
    old_value: str,
    new_value: str,
) -> None:
    """Record an audit event and enqueue it for Databricks sync.

    Local persistence is demo session state or ``user_data.audit_log``;
    Databricks sync happens via the sidecar daemon (``enqueue_sync``).
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
    _append_audit_event(event)
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


# ── Column business-name override storage ────────────────────────────────────


def get_table_columns(table_full_name: str) -> pd.DataFrame:
    """Return the columns_metadata rows for a table (demo-aware via run_query)."""
    cols_query = (
        "SELECT column_name, data_type, comment "
        "FROM {0}.{1}.columns_metadata "
        "WHERE table_full_name = %(table_full_name)s ORDER BY column_name"
    ).format(CATALOG_CACHE, SCHEMA_CACHE)
    return run_query(cols_query, {"table_full_name": table_full_name})


def get_column_overrides(table_full_name: str) -> dict:
    """Return published column overrides for a table, keyed by column name."""
    if is_demo_mode():
        return {
            col: {k: v for k, v in data.items() if k != "status"}
            for col, data in st.session_state.get(_DEMO_BN_KEY, {}).get(table_full_name, {}).items()
            if data.get("status", "published") == "published"
        }
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT column_name, business_name, definition, edited_by, edited_at "
                "FROM user_data.business_name_overrides "
                "WHERE table_full_name = %(table_full_name)s AND status = 'published'",
                {"table_full_name": table_full_name},
            )
            rows = cursor.fetchall_as_pandas()
            if rows is not None and not rows.empty:
                return {
                    str(getattr(r, "column_name", "")): {
                        "business_name": str(getattr(r, "business_name", "") or ""),
                        "definition":    str(getattr(r, "definition", "") or ""),
                        "edited_by":     str(getattr(r, "edited_by", "")),
                        "edited_at":     str(getattr(r, "edited_at", "")),
                    }
                    for r in rows.itertuples(index=False)
                }
    except Exception as exc:
        log.warning(
            "Could not fetch column business names for %s: %s",
            table_full_name, exc,
        )
    return {}


def _upsert_column_override_demo(override: ColumnOverride) -> None:
    store = st.session_state.setdefault(_DEMO_BN_KEY, {}).setdefault(override.table_full_name, {})
    pending_store = st.session_state.setdefault(_DEMO_BN_PENDING_KEY, {})

    item = {
        "business_name": override.business_name,
        "definition":    override.definition,
        "edited_by":     override.edited_by,
        "edited_at":     "just now",
        "status":        override.status,
    }
    store[override.column_name] = item

    # Pending items live in a flat dict for O(1) list_pending lookups.
    key = (override.table_full_name, override.column_name)
    if override.status == "pending_approval":
        pending_store[key] = {
            "table_full_name": override.table_full_name,
            "column_name":     override.column_name,
            "business_name":   item.get("business_name", ""),
            "definition":      item.get("definition", ""),
            "edited_by":       item.get("edited_by", ""),
            "edited_at":       item.get("edited_at", ""),
        }
    else:
        pending_store.pop(key, None)

def _upsert_column_override_db(override: ColumnOverride) -> None:
    conn = _get_write_connection()
    with conn.cursor() as cursor:
        cursor.execute_write(
            """
            INSERT INTO user_data.business_name_overrides (
                table_full_name, column_name, business_name,
                definition, edited_by, edited_at, status
            ) VALUES (
                %(table_full_name)s, %(column_name)s, %(business_name)s,
                %(definition)s, %(edited_by)s, current_localtimestamp(), %(status)s
            )
            ON CONFLICT (table_full_name, column_name) DO UPDATE SET
                business_name = excluded.business_name,
                definition    = excluded.definition,
                edited_by     = excluded.edited_by,
                edited_at     = current_localtimestamp(),
                status        = excluded.status
            """,
            {
                "table_full_name": override.table_full_name,
                "column_name":     override.column_name,
                "business_name":   override.business_name,
                "definition":      override.definition,
                "edited_by":       override.edited_by,
                "status":          override.status,
            },
        )

def _upsert_column_override(override: ColumnOverride) -> None:
    if is_demo_mode():
        _upsert_column_override_demo(override)
    else:
        _upsert_column_override_db(override)


def list_pending_business_names() -> list:
    """Return all column overrides awaiting admin approval."""
    if is_demo_mode():
        return list(st.session_state.get(_DEMO_BN_PENDING_KEY, {}).values())
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT table_full_name, column_name, business_name, definition, edited_by, edited_at "
                "FROM user_data.business_name_overrides "
                "WHERE status = 'pending_approval' "
                "ORDER BY edited_at DESC",
            )
            rows = cursor.fetchall_as_pandas()
            if rows is not None and not rows.empty:
                return rows.to_dict(orient="records")
    except Exception as exc:
        log.warning("Could not fetch pending overrides: %s", exc)
    return []


def _approve_column_override(table_full_name: str, column_name: str) -> None:
    if is_demo_mode():
        store = st.session_state.get(_DEMO_BN_KEY, {}).get(table_full_name, {})
        if column_name in store:
            store[column_name]["status"] = "published"
            pending_store = st.session_state.get(_DEMO_BN_PENDING_KEY, {})
            pending_store.pop((table_full_name, column_name), None)
        return
    conn = _get_write_connection()
    with conn.cursor() as cursor:
        cursor.execute_write(
            "UPDATE user_data.business_name_overrides SET status = 'published' "
            "WHERE table_full_name = %(fn)s AND column_name = %(col)s",
            {"fn": table_full_name, "col": column_name},
        )


def _reject_column_override(table_full_name: str, column_name: str) -> None:
    if is_demo_mode():
        store = st.session_state.get(_DEMO_BN_KEY, {}).get(table_full_name, {})
        store.pop(column_name, None)
        pending_store = st.session_state.get(_DEMO_BN_PENDING_KEY, {})
        pending_store.pop((table_full_name, column_name), None)
        return
    conn = _get_write_connection()
    with conn.cursor() as cursor:
        cursor.execute_write(
            "DELETE FROM user_data.business_name_overrides "
            "WHERE table_full_name = %(fn)s AND column_name = %(col)s "
            "AND status = 'pending_approval'",
            {"fn": table_full_name, "col": column_name},
        )


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
    overrides = get_column_overrides(table_full_name)
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
    _upsert_column_override(override)

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
    pending = {
        r["column_name"]: r
        for r in list_pending_business_names()
        if r["table_full_name"] == table_full_name
    }
    item = pending.get(column_name)
    if item is None:
        return
    _approve_column_override(table_full_name, column_name)
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
    _reject_column_override(table_full_name, column_name)
    search_all_metadata.clear()


# ── Table-level friendly-name overrides (bilingual, admin-approved) ──────────


def get_table_business_name_override(table_full_name: str) -> dict:
    """Return the published bilingual friendly-name override for a table."""
    if is_demo_mode():
        entry = st.session_state.get(_DEMO_TBN_KEY, {}).get(table_full_name)
        if not entry or entry.get("status", "published") != "published":
            return {}
        return {k: v for k, v in entry.items() if k != "status"}
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT business_name_en, business_name_fr, "
                "business_definition_en, business_definition_fr, edited_by, edited_at "
                "FROM user_data.table_business_name_overrides "
                "WHERE table_full_name = %(fn)s AND status = 'published'",
                {"fn": table_full_name},
            )
            rows = cursor.fetchall_as_pandas()
            if rows is None or rows.empty:
                return {}
            r = rows.iloc[0]
            return {
                "business_name_en":       str(r.get("business_name_en") or ""),
                "business_name_fr":       str(r.get("business_name_fr") or ""),
                "business_definition_en": str(r.get("business_definition_en") or ""),
                "business_definition_fr": str(r.get("business_definition_fr") or ""),
                "edited_by":              str(r.get("edited_by") or ""),
                "edited_at":              str(r.get("edited_at") or ""),
            }
    except Exception as exc:
        log.warning("Could not fetch table friendly name for %s: %s", table_full_name, exc)
    return {}


def _upsert_table_business_name_override_demo(override: TableBusinessNameOverride) -> None:
    store = st.session_state.setdefault(_DEMO_TBN_KEY, {})
    pending_store = st.session_state.setdefault(_DEMO_TBN_PENDING_KEY, {})
    item = {
        "business_name_en":       override.business_name_en,
        "business_name_fr":       override.business_name_fr,
        "business_definition_en": override.business_definition_en,
        "business_definition_fr": override.business_definition_fr,
        "edited_by":              override.edited_by,
        "edited_at":              "just now",
        "status":                 override.status,
    }
    store[override.table_full_name] = item
    if override.status == "pending_approval":
        pending_store[override.table_full_name] = {
            "table_full_name": override.table_full_name,
            **{k: v for k, v in item.items() if k != "status"},
        }
    else:
        pending_store.pop(override.table_full_name, None)

def _upsert_table_business_name_override_db(override: TableBusinessNameOverride) -> None:
    conn = _get_write_connection()
    with conn.cursor() as cursor:
        cursor.execute_write(
            """
            INSERT INTO user_data.table_business_name_overrides (
                table_full_name, business_name_en, business_name_fr,
                business_definition_en, business_definition_fr,
                edited_by, edited_at, status
            ) VALUES (
                %(fn)s, %(name_en)s, %(name_fr)s,
                %(def_en)s, %(def_fr)s,
                %(by)s, current_localtimestamp(), %(status)s
            )
            ON CONFLICT (table_full_name) DO UPDATE SET
                business_name_en       = excluded.business_name_en,
                business_name_fr       = excluded.business_name_fr,
                business_definition_en = excluded.business_definition_en,
                business_definition_fr = excluded.business_definition_fr,
                edited_by              = excluded.edited_by,
                edited_at              = current_localtimestamp(),
                status                 = excluded.status
            """,
            {
                "fn":      override.table_full_name,
                "name_en": override.business_name_en,
                "name_fr": override.business_name_fr,
                "def_en":  override.business_definition_en,
                "def_fr":  override.business_definition_fr,
                "by":      override.edited_by,
                "status":  override.status,
            },
        )

def _upsert_table_business_name_override(override: TableBusinessNameOverride) -> None:
    if is_demo_mode():
        _upsert_table_business_name_override_demo(override)
    else:
        _upsert_table_business_name_override_db(override)


def list_pending_table_business_names() -> list:
    """Return all table friendly-name overrides awaiting admin approval."""
    if is_demo_mode():
        return list(st.session_state.get(_DEMO_TBN_PENDING_KEY, {}).values())
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT table_full_name, business_name_en, business_name_fr, "
                "business_definition_en, business_definition_fr, edited_by, edited_at "
                "FROM user_data.table_business_name_overrides "
                "WHERE status = 'pending_approval' "
                "ORDER BY edited_at DESC"
            )
            rows = cursor.fetchall_as_pandas()
            if rows is not None and not rows.empty:
                return rows.to_dict(orient="records")
    except Exception as exc:
        log.warning("Could not fetch pending table friendly names: %s", exc)
    return []


def _approve_table_business_name_override(table_full_name: str) -> dict:
    """Publish a pending row and return it so the caller can enqueue the push."""
    if is_demo_mode():
        entry = st.session_state.get(_DEMO_TBN_KEY, {}).get(table_full_name)
        if entry:
            entry["status"] = "published"
            st.session_state.get(_DEMO_TBN_PENDING_KEY, {}).pop(table_full_name, None)
            return {k: v for k, v in entry.items() if k != "status"}
        return {}
    conn = _get_write_connection()
    with conn.cursor() as cursor:
        cursor.execute_write(
            "UPDATE user_data.table_business_name_overrides SET status = 'published' "
            "WHERE table_full_name = %(fn)s",
            {"fn": table_full_name},
        )
    return get_table_business_name_override(table_full_name)


def _reject_table_business_name_override(table_full_name: str) -> None:
    if is_demo_mode():
        st.session_state.get(_DEMO_TBN_KEY, {}).pop(table_full_name, None)
        st.session_state.get(_DEMO_TBN_PENDING_KEY, {}).pop(table_full_name, None)
        return
    conn = _get_write_connection()
    with conn.cursor() as cursor:
        cursor.execute_write(
            "DELETE FROM user_data.table_business_name_overrides "
            "WHERE table_full_name = %(fn)s AND status = 'pending_approval'",
            {"fn": table_full_name},
        )


def _validate_table_business_name_inputs(
    name_en: str, name_fr: str, def_en: str, def_fr: str,
) -> None:
    """Apply the same length limits as the column-level fields."""
    for fld, val in (("name_en", name_en), ("name_fr", name_fr)):
        if val and len(val) > MAX_BUSINESS_NAME_LEN:
            raise ValueError(
                f"{fld} exceeds the {MAX_BUSINESS_NAME_LEN}-char limit "
                f"(got {len(val)})."
            )
    for fld, val in (("definition_en", def_en), ("definition_fr", def_fr)):
        if val and len(val) > MAX_DEFINITION_LEN:
            raise ValueError(
                f"{fld} exceeds the {MAX_DEFINITION_LEN}-char limit "
                f"(got {len(val)})."
            )


def save_table_business_name(
    table_full_name: str,
    business_name_en: str,
    business_name_fr: str,
    definition_en: str = "",
    definition_fr: str = "",
) -> None:
    """Propose (or, for admins, publish) a bilingual table friendly name.

    Editors (``is_power_user()``) submit pending proposals. Admins publish
    immediately AND enqueue the sidecar write-back into the UC reference
    table. Viewers cannot reach this code path — callers gate at the UI.
    """
    if not is_power_user():
        raise PermissionError("Only editors can propose table friendly names.")
    _validate_table_business_name_inputs(
        business_name_en, business_name_fr, definition_en, definition_fr,
    )
    user_name = st.session_state.get("user_name", "unknown")
    old = get_table_business_name_override(table_full_name)
    old_value = "|".join((
        old.get("business_name_en", ""),
        old.get("business_name_fr", ""),
    ))
    new_value = "|".join((business_name_en, business_name_fr))

    _admin = is_admin()
    _status = "published" if _admin else "pending_approval"

    override = TableBusinessNameOverride(
        table_full_name=table_full_name,
        business_name_en=business_name_en,
        business_name_fr=business_name_fr,
        business_definition_en=definition_en,
        business_definition_fr=definition_fr,
        edited_by=user_name,
        status=_status,
    )
    _upsert_table_business_name_override(override)

    if _duckdb_available():
        try:
            with _db_write_lock:
                _get_shared_duckdb_connection().execute("CHECKPOINT user_data")
        except Exception:
            pass
        if _admin:
            enqueue_table_business_name_sync(
                table_full_name,
                override,
                user_name,
            )

    log_audit_event(
        "table_friendly_name_change", "TABLE", table_full_name,
        old_value, new_value,
    )
    search_all_metadata.clear()


def approve_table_business_name(table_full_name: str) -> None:
    """Publish a pending table friendly-name override and enqueue sidecar push."""
    if not is_admin():
        raise PermissionError("Only admins can approve metadata changes.")
    pending = next(
        (r for r in list_pending_table_business_names()
         if r["table_full_name"] == table_full_name),
        None,
    )
    if pending is None:
        return
    published = _approve_table_business_name_override(table_full_name)
    user_name = st.session_state.get("user_name", "unknown")
    if _duckdb_available():
        override = TableBusinessNameOverride(
            table_full_name=table_full_name,
            business_name_en=published.get("business_name_en", ""),
            business_name_fr=published.get("business_name_fr", ""),
            business_definition_en=published.get("business_definition_en", ""),
            business_definition_fr=published.get("business_definition_fr", ""),
            edited_by=published.get("edited_by", user_name),
            status=published.get("status", "published"),
        )
        enqueue_table_business_name_sync(
            table_full_name,
            override,
            user_name,
        )
        try:
            with _db_write_lock:
                _get_shared_duckdb_connection().execute("CHECKPOINT user_data")
        except Exception:
            pass
    search_all_metadata.clear()


def reject_table_business_name(table_full_name: str) -> None:
    """Reject and discard a pending table friendly-name override."""
    if not is_admin():
        raise PermissionError("Only admins can reject metadata changes.")
    _reject_table_business_name_override(table_full_name)
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
