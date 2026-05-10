from __future__ import annotations
from typing import Any, Callable, Optional, Protocol, runtime_checkable
"""Pipeline storage backends — definitions and runs.

Two distinct entities in one module because they share their backend file:

* ``PipelineDefStorage``  ↔ ``user_data.pipeline_definitions``
* ``PipelineRunStorage``  ↔ ``user_data.pipeline_runs``

Each has Demo (session-state), DuckDB (persistent), and Fake (in-memory
test) implementations. Cross-table cascade behaviour
(``delete_pipeline_def`` should also clear the active run) lives in the
``src.pipelines`` wrapper, not here — each storage object stays cohesive.
"""


import logging
from datetime import datetime, timezone; UTC = timezone.utc

import streamlit as st

from src.db.duckdb_adapter import _db_write_lock
from src.db.queries import _get_write_connection, get_db_connection

log = logging.getLogger(__name__)

_PIPELINE_COLUMNS = (
    "pipeline_id", "title", "description", "backend",
    "databricks_job_id",
    "adf_subscription_id", "adf_resource_group",
    "adf_factory_name", "adf_pipeline_name",
    "ado_organization", "ado_project", "ado_pipeline_id",
    "created_by", "created_at",
)
_RUN_COLUMNS = (
    "backend_run_id", "triggered_by", "triggered_at",
    "status", "last_checked",
)


def _row_to_pipeline(row) -> dict:
    return dict(zip(_PIPELINE_COLUMNS, row))


# ── Pipeline definitions ─────────────────────────────────────────────────────

@runtime_checkable
class PipelineDefStorage(Protocol):
    """CRUD for pipeline definitions (config — not the live runs)."""

    def list_all(self) -> list[dict]: ...
    def create(self, pipeline: dict) -> None: ...
    def delete(self, pipeline_id: str) -> None: ...


class DemoPipelineDefStorage:
    _KEY = "_demo_pipelines"

    def list_all(self) -> list[dict]:
        return list(st.session_state.get(self._KEY, []))

    def create(self, pipeline: dict) -> None:
        st.session_state.setdefault(self._KEY, []).append(dict(pipeline))

    def delete(self, pipeline_id: str) -> None:
        ps = st.session_state.get(self._KEY, [])
        st.session_state[self._KEY] = [
            p for p in ps if p["pipeline_id"] != pipeline_id
        ]


class DuckDBPipelineDefStorage:
    def list_all(self) -> list[dict]:
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pipeline_id, title, description, backend,
                           databricks_job_id,
                           adf_subscription_id, adf_resource_group,
                           adf_factory_name, adf_pipeline_name,
                           ado_organization, ado_project, ado_pipeline_id,
                           created_by, created_at
                    FROM user_data.pipeline_definitions
                    ORDER BY created_at ASC
                    """
                )
                return [_row_to_pipeline(r) for r in (cur.fetchall() or [])]
        except Exception as exc:
            log.warning("Could not load pipeline definitions: %s", exc)
            return []

    def create(self, pipeline: dict) -> None:
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                """
                INSERT INTO user_data.pipeline_definitions
                    (pipeline_id, title, description, backend,
                     databricks_job_id,
                     adf_subscription_id, adf_resource_group,
                     adf_factory_name, adf_pipeline_name,
                     ado_organization, ado_project, ado_pipeline_id,
                     created_by, created_at)
                VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?, ?,?)
                """,
                [pipeline[c] for c in _PIPELINE_COLUMNS],
            )

    def delete(self, pipeline_id: str) -> None:
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                "DELETE FROM user_data.pipeline_definitions WHERE pipeline_id = ?",
                [pipeline_id],
            )


class FakePipelineDefStorage:
    def __init__(self, pipelines: Optional[list[dict]] = None) -> None:
        self.pipelines: list[dict] = list(pipelines or [])

    def list_all(self) -> list[dict]:
        return list(self.pipelines)

    def create(self, pipeline: dict) -> None:
        self.pipelines.append(dict(pipeline))

    def delete(self, pipeline_id: str) -> None:
        self.pipelines = [p for p in self.pipelines if p["pipeline_id"] != pipeline_id]


# ── Pipeline runs ────────────────────────────────────────────────────────────

@runtime_checkable
class PipelineRunStorage(Protocol):
    """Persists the live-run state per pipeline (one active run at a time)."""

    def get_active(self, pipeline_id: str) -> Optional[dict]: ...
    def upsert(self, pipeline_id: str, backend_run_id: str, triggered_by: str) -> None: ...
    def update_status(self, pipeline_id: str, status: str) -> None: ...
    def clear(self, pipeline_id: str) -> None: ...


class DemoPipelineRunStorage:
    """Session-state backend. One key per pipeline_id ─ ``_demo_run_<pid>``."""

    @staticmethod
    def _key(pipeline_id: str) -> str:
        return f"_demo_run_{pipeline_id}"

    def get_active(self, pipeline_id: str) -> Optional[dict]:
        return st.session_state.get(self._key(pipeline_id))

    def upsert(self, pipeline_id: str, backend_run_id: str, triggered_by: str) -> None:
        now = datetime.now(UTC)
        st.session_state[self._key(pipeline_id)] = {
            "pipeline_id":    pipeline_id,
            "backend_run_id": backend_run_id,
            "triggered_by":   triggered_by,
            "triggered_at":   now,
            "status":         "started",
            "last_checked":   now,
        }

    def update_status(self, pipeline_id: str, status: str) -> None:
        run = st.session_state.get(self._key(pipeline_id))
        if run:
            run["status"] = status
            run["last_checked"] = datetime.now(UTC)

    def clear(self, pipeline_id: str) -> None:
        st.session_state.pop(self._key(pipeline_id), None)


class DuckDBPipelineRunStorage:
    def get_active(self, pipeline_id: str) -> Optional[dict]:
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT backend_run_id, triggered_by, triggered_at, status, last_checked
                    FROM user_data.pipeline_runs WHERE pipeline_id = ?
                    """,
                    [pipeline_id],
                )
                rows = cur.fetchall()
            if not rows:
                return None
            run = dict(zip(_RUN_COLUMNS, rows[0]))
            run["pipeline_id"] = pipeline_id
            return run
        except Exception as exc:
            log.warning("Could not load active run for %s: %s", pipeline_id, exc)
            return None

    def upsert(self, pipeline_id: str, backend_run_id: str, triggered_by: str) -> None:
        now = datetime.now(UTC)
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                """
                INSERT INTO user_data.pipeline_runs
                    (pipeline_id, backend_run_id, triggered_by, triggered_at, status, last_checked)
                VALUES (?, ?, ?, ?, 'started', ?)
                ON CONFLICT (pipeline_id) DO UPDATE
                    SET backend_run_id = excluded.backend_run_id,
                        triggered_by   = excluded.triggered_by,
                        triggered_at   = excluded.triggered_at,
                        status         = 'started',
                        last_checked   = excluded.last_checked
                """,
                [pipeline_id, backend_run_id, triggered_by, now, now],
            )

    def update_status(self, pipeline_id: str, status: str) -> None:
        now = datetime.now(UTC)
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                "UPDATE user_data.pipeline_runs SET status = ?, last_checked = ? "
                "WHERE pipeline_id = ?",
                [status, now, pipeline_id],
            )

    def clear(self, pipeline_id: str) -> None:
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                "DELETE FROM user_data.pipeline_runs WHERE pipeline_id = ?",
                [pipeline_id],
            )


class FakePipelineRunStorage:
    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}

    def get_active(self, pipeline_id: str) -> Optional[dict]:
        return self.runs.get(pipeline_id)

    def upsert(self, pipeline_id: str, backend_run_id: str, triggered_by: str) -> None:
        now = datetime.now(UTC)
        self.runs[pipeline_id] = {
            "pipeline_id":    pipeline_id,
            "backend_run_id": backend_run_id,
            "triggered_by":   triggered_by,
            "triggered_at":   now,
            "status":         "started",
            "last_checked":   now,
        }

    def update_status(self, pipeline_id: str, status: str) -> None:
        run = self.runs.get(pipeline_id)
        if run:
            run["status"] = status
            run["last_checked"] = datetime.now(UTC)

    def clear(self, pipeline_id: str) -> None:
        self.runs.pop(pipeline_id, None)
