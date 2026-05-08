"""Audit log + business-name-override storage backends.

Two entities, one module — both are write-heavy and share the same set of
runtime backends (demo / DuckDB / Databricks).

* ``AuditStorage`` writes audit events. Reads are NOT in this protocol;
  the admin page uses the catalog query layer
  (``src/ui/cards/admin.py``) and remains untouched here.

* ``BusinessNameOverrideStorage`` reads + writes column overrides
  (business name + definition). Replaces the inline branches in
  ``src/audit.py`` and the legacy ``src/db/queries.get_column_business_names``.

Note on Databricks fallback: when DuckDB is absent but Databricks is
configured, audit events go to ``data_governance.dictionary_cache.audit_log``
and overrides are MERGE'd into the same catalog. This module preserves
that behaviour — but in practice the daemon also pushes a copy of every
audit event via ``enqueue_sync('AUDIT', …)``, making the direct
Databricks path mostly redundant. Cleaning that up is a follow-up.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import pandas as pd
import streamlit as st

from src.config import CATALOG_CACHE, SCHEMA_CACHE
from src.db.duckdb_adapter import _db_write_lock
from src.db.queries import _get_write_connection, get_db_connection

log = logging.getLogger(__name__)


# ── Audit log ────────────────────────────────────────────────────────────────

@runtime_checkable
class AuditStorage(Protocol):
    """Append-only event log. Reads are handled by the admin-page query layer."""

    def append(self, event: dict) -> None: ...


class DemoAuditStorage:
    """Writes events into ``st.session_state['demo_audit_log']``."""

    _KEY = "demo_audit_log"

    def append(self, event: dict) -> None:
        st.session_state.setdefault(self._KEY, []).append({
            **event,
            "created_at": pd.Timestamp.now(),
        })


class DuckDBAuditStorage:
    """Writes events to ``user_data.audit_log``."""

    def append(self, event: dict) -> None:
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


class DatabricksAuditStorage:
    """Writes events directly to the catalog audit_log on Databricks.

    Used when DuckDB is unavailable AND Databricks credentials are
    configured. The much more common path in production is the sidecar
    daemon, which also pushes audit events via ``enqueue_sync``.
    """

    def append(self, event: dict) -> None:
        try:
            conn = _get_write_connection()
            with conn.cursor() as cursor:
                cursor.execute_write(
                    f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log "
                    f"(event_id, event_type, object_type, object_name, "
                    f" actor_email, old_value, new_value, created_at) "
                    f"VALUES (%(event_id)s, %(event_type)s, %(object_type)s, "
                    f" %(object_name)s, %(actor_email)s, %(old_value)s, "
                    f" %(new_value)s, current_localtimestamp())",
                    event,
                )
        except Exception as exc:
            log.warning("Audit logging failed for %s: %s", event.get("event_id"), exc)


class FakeAuditStorage:
    """In-memory backend for unit tests."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def append(self, event: dict) -> None:
        self.events.append({**event, "created_at": pd.Timestamp.now()})


# ── Business name overrides ──────────────────────────────────────────────────

@runtime_checkable
class BusinessNameOverrideStorage(Protocol):
    """Read + write column-level business name + definition overrides."""

    def get_for_table(self, table_full_name: str) -> dict: ...
    def upsert(
        self,
        table_full_name: str,
        column_name: str,
        business_name: str,
        definition: str,
        edited_by: str,
    ) -> None: ...


class DemoBusinessNameOverrideStorage:
    """Backs to ``st.session_state['demo_business_names']`` (nested dict)."""

    _KEY = "demo_business_names"

    def get_for_table(self, table_full_name: str) -> dict:
        return st.session_state.get(self._KEY, {}).get(table_full_name, {})

    def upsert(
        self, table_full_name, column_name, business_name, definition, edited_by,
    ) -> None:
        store = st.session_state.setdefault(self._KEY, {}).setdefault(table_full_name, {})
        store[column_name] = {
            "business_name": business_name,
            "definition":    definition,
            "edited_by":     edited_by,
            "edited_at":     "just now",
        }


class DuckDBBusinessNameOverrideStorage:
    def get_for_table(self, table_full_name: str) -> dict:
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT column_name, business_name, definition, edited_by, edited_at "
                    "FROM user_data.business_name_overrides "
                    "WHERE table_full_name = %(table_full_name)s",
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

    def upsert(
        self, table_full_name, column_name, business_name, definition, edited_by,
    ) -> None:
        conn = _get_write_connection()
        with conn.cursor() as cursor:
            cursor.execute_write(
                """
                INSERT INTO user_data.business_name_overrides (
                    table_full_name, column_name, business_name,
                    definition, edited_by, edited_at
                ) VALUES (
                    %(table_full_name)s, %(column_name)s, %(business_name)s,
                    %(definition)s, %(edited_by)s, current_localtimestamp()
                )
                ON CONFLICT (table_full_name, column_name) DO UPDATE SET
                    business_name = excluded.business_name,
                    definition    = excluded.definition,
                    edited_by     = excluded.edited_by,
                    edited_at     = current_localtimestamp()
                """,
                {
                    "table_full_name": table_full_name,
                    "column_name":     column_name,
                    "business_name":   business_name,
                    "definition":      definition,
                    "edited_by":       edited_by,
                },
            )


class DatabricksBusinessNameOverrideStorage:
    def get_for_table(self, table_full_name: str) -> dict:
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT column_name, business_name, definition, edited_by, edited_at "
                    f"FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides "
                    f"WHERE table_full_name = %(table_full_name)s",
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

    def upsert(
        self, table_full_name, column_name, business_name, definition, edited_by,
    ) -> None:
        conn = _get_write_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                f"MERGE INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides AS target "
                f"USING (SELECT %(table_full_name)s AS table_full_name, "
                f"              %(column_name)s     AS column_name, "
                f"              %(business_name)s   AS business_name, "
                f"              %(definition)s      AS definition, "
                f"              %(edited_by)s       AS edited_by) AS source "
                f"ON target.table_full_name = source.table_full_name "
                f"AND target.column_name   = source.column_name "
                f"WHEN MATCHED THEN UPDATE SET "
                f"  target.business_name = source.business_name, "
                f"  target.definition    = source.definition, "
                f"  target.edited_by     = source.edited_by, "
                f"  target.edited_at     = current_timestamp() "
                f"WHEN NOT MATCHED THEN INSERT "
                f"  (table_full_name, column_name, business_name, definition, edited_by, edited_at) "
                f"VALUES (source.table_full_name, source.column_name, source.business_name, "
                f"        source.definition, source.edited_by, current_timestamp())",
                {
                    "table_full_name": table_full_name,
                    "column_name":     column_name,
                    "business_name":   business_name,
                    "definition":      definition,
                    "edited_by":       edited_by,
                },
            )


class FakeBusinessNameOverrideStorage:
    def __init__(self) -> None:
        # {table_full_name: {column_name: override_dict}}
        self.data: dict[str, dict[str, dict]] = {}

    def get_for_table(self, table_full_name: str) -> dict:
        return dict(self.data.get(table_full_name, {}))

    def upsert(
        self, table_full_name, column_name, business_name, definition, edited_by,
    ) -> None:
        self.data.setdefault(table_full_name, {})[column_name] = {
            "business_name": business_name,
            "definition":    definition,
            "edited_by":     edited_by,
            "edited_at":     "just now",
        }
