"""Audit logging and metadata overrides functionality."""

import uuid
import logging
import pandas as pd
import streamlit as st

from src.config import CATALOG_CACHE, SCHEMA_CACHE, MAX_BUSINESS_NAME_LEN, is_demo_mode
from src.db.duckdb_adapter import _duckdb_available, _db_write_lock, _get_shared_duckdb_connection
from src.db.queries import _get_write_connection, get_db_connection, get_column_business_names, search_all_metadata, get_authorized_tables
from src.personalization import is_power_user
from src.sync.push import enqueue_sync, enqueue_column_sync

def log_audit_event(event_type: str, object_type: str, object_name: str, old_value: str, new_value: str) -> None:
    """Record an audit event for admin review and enqueue for Databricks sync."""
    actor_email = st.session_state.get("user_email", "")
    event_id = str(uuid.uuid4())
    payload = {
        "event_id":    event_id,
        "event_type":  event_type,
        "object_type": object_type,
        "object_name": object_name,
        "actor_email": actor_email,
        "old_value":   old_value,
        "new_value":   new_value,
    }
    try:
        if is_demo_mode():
            st.session_state.setdefault("demo_audit_log", []).append({
                **payload,
                "created_at":  pd.Timestamp.now(),
            })
        else:
            conn = _get_write_connection()
            with conn.cursor() as cursor:
                table_name = "user_data.audit_log" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log"
                cursor.execute_write(
                    f"INSERT INTO {table_name} "
                    f"(event_id, event_type, object_type, object_name, actor_email, old_value, new_value, created_at) "
                    f"VALUES (%(event_id)s, %(event_type)s, %(object_type)s, %(object_name)s, "
                    f"%(actor_email)s, %(old_value)s, %(new_value)s, current_localtimestamp())",
                    payload,
                )
            # Enqueue for Databricks sync (Priority 3)
            enqueue_sync("AUDIT", None, payload, actor_email)
    except Exception as e:
        logging.warning("Audit logging failed for %s: %s", event_id, e)


def save_table_metadata(table_full_name: str, description: str = None, steward_email: str = None) -> None:
    """Atomically update table metadata (description/steward) and enqueue for sync."""
    if not is_power_user():
        raise PermissionError("Only power users can update table metadata.")

    user_name = st.session_state.get("user_name", "unknown")
    # Update local cache (DuckDB)
    if _duckdb_available():
        conn = _get_write_connection()
        with conn.cursor() as cursor:
            if description is not None:
                cursor.execute_write(
                    f"UPDATE {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata SET comment = %(desc)s WHERE full_name = %(fn)s",
                    {"desc": description, "fn": table_full_name}
                )
                enqueue_sync("TABLE_DESC", table_full_name, {"definition": description}, user_name)
                log_audit_event("table_description_change", "TABLE", table_full_name, "N/A", description)

            if steward_email is not None:
                # We store steward in properties/tags in Databricks, locally in tables_metadata
                cursor.execute_write(
                    f"UPDATE {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata SET steward_email = %(stew)s WHERE full_name = %(fn)s",
                    {"stew": steward_email, "fn": table_full_name}
                )
                enqueue_sync("STEWARD", table_full_name, {"steward_email": steward_email}, user_name)
                log_audit_event("table_steward_change", "TABLE", table_full_name, "N/A", steward_email)

        try:
            with _db_write_lock:
                _get_shared_duckdb_connection().execute("CHECKPOINT user_data")
        except Exception:
            pass

    search_all_metadata.clear()
    get_authorized_tables.clear()


def save_business_name(table_full_name: str, column_name: str, business_name: str, definition: str = "") -> None:
    """Atomically upsert a column override (business name + definition) using MERGE INTO."""
    if not is_power_user():
        raise PermissionError("Only power users can save business name overrides.")
    if business_name and len(business_name) > MAX_BUSINESS_NAME_LEN:
        raise ValueError(
            f"Business name must be {MAX_BUSINESS_NAME_LEN} characters or fewer "
            f"(got {len(business_name)})."
        )
    if definition and len(definition) > MAX_BUSINESS_NAME_LEN:
        raise ValueError(
            f"Definition must be {MAX_BUSINESS_NAME_LEN} characters or fewer "
            f"(got {len(definition)})."
        )
    user_name = st.session_state.get("user_name", "unknown")
    if is_demo_mode():
        old_override = {}
        if "demo_business_names" in st.session_state and table_full_name in st.session_state["demo_business_names"]:
            old_override = st.session_state["demo_business_names"][table_full_name].get(column_name, {})
    else:
        old_override = get_column_business_names(table_full_name).get(column_name, {})
    old_value = old_override.get("business_name", "")
    if is_demo_mode():
        if "demo_business_names" not in st.session_state:
            st.session_state["demo_business_names"] = {}
        tbl = st.session_state["demo_business_names"].setdefault(table_full_name, {})
        tbl[column_name] = {"business_name": business_name, "definition": definition, "edited_by": user_name, "edited_at": "just now"}
        log_audit_event("business_name_change", "COLUMN", f"{table_full_name}.{column_name}", old_value, business_name)
        return
    # Use DuckDB if available, otherwise Databricks
    conn = _get_write_connection()
    with conn.cursor() as cursor:
        if _duckdb_available():
            cursor.execute_write(
                """
                INSERT INTO user_data.business_name_overrides (
                    table_full_name, column_name, business_name, definition, edited_by, edited_at
                ) VALUES (
                    %(table_full_name)s, %(column_name)s, %(business_name)s, %(definition)s, %(edited_by)s, current_localtimestamp()
                )
                ON CONFLICT (table_full_name, column_name) DO UPDATE SET
                    business_name = excluded.business_name,
                    definition = excluded.definition,
                    edited_by = excluded.edited_by,
                    edited_at = current_localtimestamp()
                """,
                {
                    "table_full_name": table_full_name,
                    "column_name": column_name,
                    "business_name": business_name,
                    "definition": definition,
                    "edited_by": user_name,
                },
            )
        else:
            cursor.execute(
                f"MERGE INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides AS target "
                f"USING (SELECT %(table_full_name)s AS table_full_name, %(column_name)s AS column_name, %(business_name)s AS business_name, %(definition)s AS definition, %(edited_by)s AS edited_by) AS source "
                f"ON target.table_full_name = source.table_full_name AND target.column_name = source.column_name "
                f"WHEN MATCHED THEN UPDATE SET target.business_name = source.business_name, target.definition = source.definition, target.edited_by = source.edited_by, target.edited_at = current_timestamp() "
                f"WHEN NOT MATCHED THEN INSERT (table_full_name, column_name, business_name, definition, edited_by, edited_at) VALUES (source.table_full_name, source.column_name, source.business_name, source.definition, source.edited_by, current_timestamp())",
                {"table_full_name": table_full_name, "column_name": column_name, "business_name": business_name, "definition": definition, "edited_by": user_name},
            )
    # Flush write to disk so it's immediately visible to all sessions sharing the same file.
    if _duckdb_available():
        try:
            with _db_write_lock:
                _get_shared_duckdb_connection().execute("CHECKPOINT user_data")
        except Exception:
            pass
        enqueue_column_sync(table_full_name, column_name, definition, user_name)
    log_audit_event("business_name_change", "COLUMN", f"{table_full_name}.{column_name}", old_value, business_name)
    search_all_metadata.clear()


def get_table_steward(table_full_name: str) -> str:
    """Return the steward_email for a table, or '' if unset."""
    if is_demo_mode():
        return "steward@example.com"
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
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
