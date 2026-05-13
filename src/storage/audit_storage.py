# ruff: noqa: E402
from __future__ import annotations
"""Audit log + business-name-override storage backends.

Two entities, one module — both write-heavy. Backends:

* ``AuditStorage`` writes audit events to ``user_data.audit_log`` (DuckDB)
  or ``st.session_state['demo_audit_log']`` (demo). Reads are NOT in this
  protocol; the admin page uses the catalog query layer
  (``src/ui/cards/admin.py``) and remains untouched here.

* ``BusinessNameOverrideStorage`` reads + writes column overrides
  (business name + definition).

The Databricks-direct ``Databricks*Storage`` variants were deleted in
TODO #7 — Streamlit pods now only ever write locally to DuckDB; the
sidecar sync daemon (ADR 004) is the sole intentional Databricks
writer, pushing audit events / column comments via
``enqueue_sync(...)``.
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


import logging

import pandas as pd
import streamlit as st

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


class FakeAuditStorage:
    """In-memory backend for unit tests."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def append(self, event: dict) -> None:
        self.events.append({**event, "created_at": pd.Timestamp.now()})


# ── Business name overrides ──────────────────────────────────────────────────


@dataclass
class ColumnOverride:
    table_full_name: str
    column_name: str
    business_name: str
    definition: str
    edited_by: str
    status: str = "published"


@runtime_checkable
class BusinessNameOverrideStorage(Protocol):
    """Read + write column-level business name + definition overrides."""

    def get_for_table(self, table_full_name: str) -> dict: ...
    def upsert(self, override: ColumnOverride) -> None: ...
    def list_pending(self) -> list: ...
    def approve(self, table_full_name: str, column_name: str) -> None: ...
    def reject(self, table_full_name: str, column_name: str) -> None: ...


class DemoBusinessNameOverrideStorage:
    """Backs to ``st.session_state['demo_business_names']`` (nested dict)."""

    _KEY = "demo_business_names"

    def get_for_table(self, table_full_name: str) -> dict:
        return {
            col: {k: v for k, v in data.items() if k != "status"}
            for col, data in st.session_state.get(self._KEY, {}).get(table_full_name, {}).items()
            if data.get("status", "published") == "published"
        }

    def upsert(self, override: ColumnOverride) -> None:
        store = st.session_state.setdefault(self._KEY, {}).setdefault(override.table_full_name, {})
        store[override.column_name] = {
            "business_name": override.business_name,
            "definition":    override.definition,
            "edited_by":     override.edited_by,
            "edited_at":     "just now",
            "status":        override.status,
        }

    def list_pending(self) -> list:
        results = []
        for tbl_name, cols in st.session_state.get(self._KEY, {}).items():
            for col_name, data in cols.items():
                if data.get("status") == "pending_approval":
                    results.append({
                        "table_full_name": tbl_name,
                        "column_name":     col_name,
                        "business_name":   data.get("business_name", ""),
                        "definition":      data.get("definition", ""),
                        "edited_by":       data.get("edited_by", ""),
                        "edited_at":       data.get("edited_at", ""),
                    })
        return results

    def approve(self, table_full_name: str, column_name: str) -> None:
        store = st.session_state.get(self._KEY, {}).get(table_full_name, {})
        if column_name in store:
            store[column_name]["status"] = "published"

    def reject(self, table_full_name: str, column_name: str) -> None:
        store = st.session_state.get(self._KEY, {}).get(table_full_name, {})
        store.pop(column_name, None)


class DuckDBBusinessNameOverrideStorage:
    def get_for_table(self, table_full_name: str) -> dict:
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

    def upsert(self, override: ColumnOverride) -> None:
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

    def list_pending(self) -> list:
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

    def approve(self, table_full_name: str, column_name: str) -> None:
        conn = _get_write_connection()
        with conn.cursor() as cursor:
            cursor.execute_write(
                "UPDATE user_data.business_name_overrides SET status = 'published' "
                "WHERE table_full_name = %(fn)s AND column_name = %(col)s",
                {"fn": table_full_name, "col": column_name},
            )

    def reject(self, table_full_name: str, column_name: str) -> None:
        conn = _get_write_connection()
        with conn.cursor() as cursor:
            cursor.execute_write(
                "DELETE FROM user_data.business_name_overrides "
                "WHERE table_full_name = %(fn)s AND column_name = %(col)s "
                "AND status = 'pending_approval'",
                {"fn": table_full_name, "col": column_name},
            )


class FakeBusinessNameOverrideStorage:
    def __init__(self) -> None:
        # {table_full_name: {column_name: override_dict}}
        self.data: dict[str, dict[str, dict]] = {}

    def get_for_table(self, table_full_name: str) -> dict:
        return {
            col: {k: v for k, v in d.items() if k != "status"}
            for col, d in self.data.get(table_full_name, {}).items()
            if d.get("status", "published") == "published"
        }

    def upsert(self, override: ColumnOverride) -> None:
        self.data.setdefault(override.table_full_name, {})[override.column_name] = {
            "business_name": override.business_name,
            "definition":    override.definition,
            "edited_by":     override.edited_by,
            "edited_at":     "just now",
            "status":        override.status,
        }

    def list_pending(self) -> list:
        return [
            {
                "table_full_name": tbl,
                "column_name":     col,
                "business_name":   d.get("business_name", ""),
                "definition":      d.get("definition", ""),
                "edited_by":       d.get("edited_by", ""),
                "edited_at":       d.get("edited_at", ""),
            }
            for tbl, cols in self.data.items()
            for col, d in cols.items()
            if d.get("status") == "pending_approval"
        ]

    def approve(self, table_full_name: str, column_name: str) -> None:
        entry = self.data.get(table_full_name, {}).get(column_name)
        if entry:
            entry["status"] = "published"

    def reject(self, table_full_name: str, column_name: str) -> None:
        self.data.get(table_full_name, {}).pop(column_name, None)
