"""Pipeline definitions, run tracking, and execution for Databricks / ADF / ADO.

Storage branches on ``is_demo_mode()``: demo keeps definitions in
``st.session_state['_demo_pipelines']`` and runs in ``_demo_run_<pid>``
keys; otherwise rows persist to ``user_data.pipeline_definitions`` /
``user_data.pipeline_runs`` (DuckDB). Execution (HTTP calls to
Databricks/ADF/ADO management APIs) lives below the storage section.
"""
from __future__ import annotations
from typing import Any, Optional


import logging
import uuid
from datetime import datetime, timezone; UTC = timezone.utc

import streamlit as st

from src.auth import is_admin, is_pipeline_user
from src.config import (
    DATABRICKS_HOST_URL,
    PIPELINE_SP_CLIENT_ID,
    PIPELINE_SP_CLIENT_SECRET,
    PIPELINE_SP_TENANT_ID,
    is_demo_mode,
)
from src.db.duckdb_adapter import _db_write_lock
from src.db.queries import _get_write_connection, get_db_connection

_DEMO_DEFS_KEY = "_demo_pipelines"

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


def _demo_run_key(pipeline_id: str) -> str:
    return f"_demo_run_{pipeline_id}"


# ── Auth helpers (defense-in-depth) ──────────────────────────────────────────
# These mirror the UI gates in src/ui/cards/pipelines.py so write functions
# refuse calls from non-admin / non-pipeline users even if a future caller
# bypasses the UI check.

def _check_admin(action: str) -> None:
    if not is_admin():
        raise PermissionError(f"Only admins can {action}.")


def _check_pipeline_user_or_admin(action: str) -> None:
    if not (is_pipeline_user() or is_admin()):
        raise PermissionError(f"Only pipeline users or admins can {action}.")

BACKENDS = ("databricks", "adf", "ado")

# AAD resource IDs
# _RESOURCE_DATABRICKS: The well-known, static 1st-party enterprise application ID for Azure Databricks.
_RESOURCE_DATABRICKS = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
# _RESOURCE_AZURE_MGMT: The static resource URL for the Azure Resource Manager (ARM) API.
_RESOURCE_AZURE_MGMT = "https://management.azure.com/"
# _RESOURCE_ADO: The well-known, static 1st-party enterprise application ID for Azure DevOps.
_RESOURCE_ADO        = "499b84ac-1321-427f-aa17-267ca6975798"

# Map backend lifecycle states → progress %
_DATABRICKS_PROGRESS = {
    "QUEUED": 5, "PENDING": 10, "RUNNING": 55,
    "TERMINATING": 90, "TERMINATED": 100,
    "SKIPPED": 100, "INTERNAL_ERROR": 100,
}
_ADF_PROGRESS = {
    "Queued": 5, "InProgress": 55,
    "Succeeded": 100, "Failed": 100, "Cancelling": 90, "Cancelled": 100,
}
_ADO_PROGRESS = {
    "unknown": 0, "inProgress": 55, "cancelling": 90, "completed": 100,
}

# Terminal states where polling should stop
_TERMINAL_STATUSES = frozenset({
    "TERMINATED", "SKIPPED", "INTERNAL_ERROR",   # Databricks
    "Succeeded", "Failed", "Cancelled",           # ADF
    "completed",                                  # ADO
})


# ── Service principal token ───────────────────────────────────────────────────

def _get_sp_token(resource: str) -> str:
    """Acquire an AAD token for the pipeline service principal."""
    import msal
    if not all((PIPELINE_SP_TENANT_ID, PIPELINE_SP_CLIENT_ID, PIPELINE_SP_CLIENT_SECRET)):
        raise RuntimeError("Pipeline service principal credentials are not configured (PIPELINE_SP_*).")
    authority = f"https://login.microsoftonline.com/{PIPELINE_SP_TENANT_ID}"
    app = msal.ConfidentialClientApplication(
        PIPELINE_SP_CLIENT_ID,
        authority=authority,
        client_credential=PIPELINE_SP_CLIENT_SECRET,
    )
    scope = [f"{resource}/.default"] if not resource.endswith("/") else [f"{resource}.default"]
    result = app.acquire_token_for_client(scopes=scope)
    if "access_token" not in result:
        err = result.get("error_description") or result.get("error") or "unknown"
        raise RuntimeError(f"Failed to acquire pipeline SP token: {err}")
    return result["access_token"]


# ── Pipeline definitions CRUD ─────────────────────────────────────────────────

def get_pipelines() -> list[dict]:
    """Return all pipeline definitions, oldest-first."""
    if is_demo_mode():
        return list(st.session_state.get(_DEMO_DEFS_KEY, []))
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
            return [dict(zip(_PIPELINE_COLUMNS, r)) for r in (cur.fetchall() or [])]
    except Exception as exc:
        logging.warning("Could not load pipeline definitions: %s", exc)
        return []


def create_pipeline_def(
    title: str,
    description: str,
    backend: str,
    databricks_job_id: Optional[str],
    adf_subscription_id: Optional[str],
    adf_resource_group: Optional[str],
    adf_factory_name: Optional[str],
    adf_pipeline_name: Optional[str],
    ado_organization: Optional[str],
    ado_project: Optional[str],
    ado_pipeline_id: Optional[str],
    created_by: str,
) -> None:
    """Persist a new pipeline definition to the configured backend."""
    _check_admin("create pipeline definitions")
    pipeline = {
        "pipeline_id":         str(uuid.uuid4()),
        "title":               title,
        "description":         description or None,
        "backend":             backend,
        "databricks_job_id":   databricks_job_id or None,
        "adf_subscription_id": adf_subscription_id or None,
        "adf_resource_group":  adf_resource_group or None,
        "adf_factory_name":    adf_factory_name or None,
        "adf_pipeline_name":   adf_pipeline_name or None,
        "ado_organization":    ado_organization or None,
        "ado_project":         ado_project or None,
        "ado_pipeline_id":     ado_pipeline_id or None,
        "created_by":          created_by,
        "created_at":          datetime.now(UTC),
    }
    if is_demo_mode():
        st.session_state.setdefault(_DEMO_DEFS_KEY, []).append(pipeline)
        return
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


def delete_pipeline_def(pipeline_id: str) -> None:
    """Delete a pipeline definition. Cascades: also clears any active run."""
    _check_admin("delete pipeline definitions")
    if is_demo_mode():
        ps = st.session_state.get(_DEMO_DEFS_KEY, [])
        st.session_state[_DEMO_DEFS_KEY] = [
            p for p in ps if p["pipeline_id"] != pipeline_id
        ]
    else:
        conn = _get_write_connection()
        with _db_write_lock:
            conn.execute(
                "DELETE FROM user_data.pipeline_definitions WHERE pipeline_id = ?",
                [pipeline_id],
            )
    _clear_run(pipeline_id)


# ── Run state persistence ─────────────────────────────────────────────────────

def get_active_run(pipeline_id: str) -> Optional[dict]:
    """Return the active run for a pipeline, or None if no run is in flight."""
    if is_demo_mode():
        return st.session_state.get(_demo_run_key(pipeline_id))
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
        logging.warning("Could not load active run for %s: %s", pipeline_id, exc)
        return None


def _save_run(pipeline_id: str, backend_run_id: str, triggered_by: str) -> None:
    """Upsert a freshly-triggered run (status = 'started')."""
    now = datetime.now(UTC)
    if is_demo_mode():
        st.session_state[_demo_run_key(pipeline_id)] = {
            "pipeline_id":    pipeline_id,
            "backend_run_id": backend_run_id,
            "triggered_by":   triggered_by,
            "triggered_at":   now,
            "status":         "started",
            "last_checked":   now,
        }
        return
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


def _update_run(pipeline_id: str, status: str) -> None:
    """Update the status of the active run for ``pipeline_id``."""
    if is_demo_mode():
        run = st.session_state.get(_demo_run_key(pipeline_id))
        if run:
            run["status"] = status
            run["last_checked"] = datetime.now(UTC)
        return
    conn = _get_write_connection()
    with _db_write_lock:
        conn.execute(
            "UPDATE user_data.pipeline_runs SET status = ?, last_checked = ? "
            "WHERE pipeline_id = ?",
            [status, datetime.now(UTC), pipeline_id],
        )


def _clear_run(pipeline_id: str) -> None:
    """Remove the active-run record for ``pipeline_id`` (idempotent)."""
    if is_demo_mode():
        st.session_state.pop(_demo_run_key(pipeline_id), None)
        return
    conn = _get_write_connection()
    with _db_write_lock:
        conn.execute(
            "DELETE FROM user_data.pipeline_runs WHERE pipeline_id = ?",
            [pipeline_id],
        )


# ── Execution — trigger ───────────────────────────────────────────────────────

def trigger_pipeline(pipeline: dict, triggered_by: str) -> None:
    """Start a pipeline run and persist the run ID."""
    _check_pipeline_user_or_admin("trigger pipelines")
    backend = pipeline["backend"]
    if backend == "databricks":
        _trigger_databricks(pipeline, triggered_by)
    elif backend == "adf":
        _trigger_adf(pipeline, triggered_by)
    elif backend == "ado":
        _trigger_ado(pipeline, triggered_by)
    else:
        raise ValueError(f"Unknown backend: {backend}")


def _trigger_databricks(pipeline: dict, triggered_by: str) -> None:
    import requests
    job_id = pipeline["databricks_job_id"]
    host   = DATABRICKS_HOST_URL.rstrip("/")
    token  = _get_sp_token(_RESOURCE_DATABRICKS)
    resp = requests.post(
        f"https://{host}/api/2.1/jobs/run-now",
        json={"job_id": int(job_id)},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    run_id = str(resp.json()["run_id"])
    _save_run(pipeline["pipeline_id"], run_id, triggered_by)


def _trigger_adf(pipeline: dict, triggered_by: str) -> None:
    import requests
    sub  = pipeline["adf_subscription_id"]
    rg   = pipeline["adf_resource_group"]
    fact = pipeline["adf_factory_name"]
    pipe = pipeline["adf_pipeline_name"]
    token = _get_sp_token(_RESOURCE_AZURE_MGMT)
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.DataFactory/factories/{fact}"
        f"/pipelines/{pipe}/createRun?api-version=2018-06-01"
    )
    resp = requests.post(url, json={}, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    run_id = resp.json()["runId"]
    _save_run(pipeline["pipeline_id"], run_id, triggered_by)


def _trigger_ado(pipeline: dict, triggered_by: str) -> None:
    import requests
    org  = pipeline["ado_organization"]
    proj = pipeline["ado_project"]
    pid  = pipeline["ado_pipeline_id"]
    token = _get_sp_token(_RESOURCE_ADO)
    url = (
        f"https://dev.azure.com/{org}/{proj}"
        f"/_apis/pipelines/{pid}/runs?api-version=7.0"
    )
    resp = requests.post(url, json={}, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    run_id = str(resp.json()["id"])
    _save_run(pipeline["pipeline_id"], run_id, triggered_by)


# ── Execution — status ────────────────────────────────────────────────────────

def poll_run_status(pipeline: dict, run: dict) -> dict[str, Any]:
    """Return {status, progress, message, is_terminal}.
    Also updates the persisted run status."""
    backend = pipeline["backend"]
    try:
        if backend == "databricks":
            result = _status_databricks(run["backend_run_id"])
        elif backend == "adf":
            result = _status_adf(pipeline, run["backend_run_id"])
        elif backend == "ado":
            result = _status_ado(pipeline, run["backend_run_id"])
        else:
            result = {"status": "unknown", "progress": 0, "message": "", "is_terminal": False}
    except Exception as _e:
        logging.warning("Could not poll %s run status: %s", backend, _e)
        return {"status": run.get("status", "unknown"), "progress": 0,
                "message": str(_e), "is_terminal": False}

    _update_run(pipeline["pipeline_id"], result["status"])
    if result["is_terminal"]:
        _clear_run(pipeline["pipeline_id"])
    return result


def _status_databricks(run_id: str) -> dict:
    import requests
    host  = DATABRICKS_HOST_URL.rstrip("/")
    token = _get_sp_token(_RESOURCE_DATABRICKS)
    resp  = requests.get(
        f"https://{host}/api/2.1/jobs/runs/get",
        params={"run_id": run_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    resp.raise_for_status()
    data    = resp.json()
    state   = data.get("state", {})
    lcs     = state.get("life_cycle_state", "PENDING")
    rs      = state.get("result_state", "")
    msg     = state.get("state_message", "")
    prog    = _DATABRICKS_PROGRESS.get(lcs, 20)
    is_term = lcs in _TERMINAL_STATUSES
    # Refine progress using task count when running
    tasks = data.get("tasks", [])
    if tasks and lcs == "RUNNING":
        done  = sum(1 for t in tasks if t.get("state", {}).get("life_cycle_state") == "TERMINATED")
        prog  = max(10, int(done / len(tasks) * 90))
    status = rs if rs else lcs
    return {"status": status, "progress": prog, "message": msg, "is_terminal": is_term}


def _status_adf(pipeline: dict, run_id: str) -> dict:
    import requests
    sub  = pipeline["adf_subscription_id"]
    rg   = pipeline["adf_resource_group"]
    fact = pipeline["adf_factory_name"]
    token = _get_sp_token(_RESOURCE_AZURE_MGMT)
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.DataFactory/factories/{fact}"
        f"/pipelineruns/{run_id}?api-version=2018-06-01"
    )
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
    resp.raise_for_status()
    data    = resp.json()
    status  = data.get("status", "Queued")
    msg     = data.get("message", "")
    prog    = _ADF_PROGRESS.get(status, 20)
    is_term = status in _TERMINAL_STATUSES
    return {"status": status, "progress": prog, "message": msg, "is_terminal": is_term}


def _status_ado(pipeline: dict, run_id: str) -> dict:
    import requests
    org  = pipeline["ado_organization"]
    proj = pipeline["ado_project"]
    pid  = pipeline["ado_pipeline_id"]
    token = _get_sp_token(_RESOURCE_ADO)
    url = (
        f"https://dev.azure.com/{org}/{proj}"
        f"/_apis/pipelines/{pid}/runs/{run_id}?api-version=7.0"
    )
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
    resp.raise_for_status()
    data    = resp.json()
    state   = data.get("state", "inProgress")
    result  = data.get("result", "")
    prog    = _ADO_PROGRESS.get(state, 20)
    is_term = state in _TERMINAL_STATUSES
    status  = result if result else state
    return {"status": status, "progress": prog, "message": "", "is_terminal": is_term}


# ── Execution — cancel ────────────────────────────────────────────────────────

def cancel_run(pipeline: dict, run: dict) -> None:
    """Hard-cancel the active run and clear it from persistence."""
    _check_pipeline_user_or_admin("cancel pipeline runs")
    backend = pipeline["backend"]
    try:
        if backend == "databricks":
            _cancel_databricks(run["backend_run_id"])
        elif backend == "adf":
            _cancel_adf(pipeline, run["backend_run_id"])
        elif backend == "ado":
            _cancel_ado(pipeline, run["backend_run_id"])
    except Exception as _e:
        logging.error("Could not cancel %s run: %s", backend, _e)
        raise
    finally:
        _clear_run(pipeline["pipeline_id"])


def _cancel_databricks(run_id: str) -> None:
    import requests
    host  = DATABRICKS_HOST_URL.rstrip("/")
    token = _get_sp_token(_RESOURCE_DATABRICKS)
    resp  = requests.post(
        f"https://{host}/api/2.1/jobs/runs/cancel",
        json={"run_id": int(run_id)},
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    resp.raise_for_status()


def _cancel_adf(pipeline: dict, run_id: str) -> None:
    import requests
    sub  = pipeline["adf_subscription_id"]
    rg   = pipeline["adf_resource_group"]
    fact = pipeline["adf_factory_name"]
    token = _get_sp_token(_RESOURCE_AZURE_MGMT)
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.DataFactory/factories/{fact}"
        f"/pipelineruns/{run_id}/cancel?api-version=2018-06-01"
    )
    resp = requests.post(url, json={}, headers={"Authorization": f"Bearer {token}"}, timeout=20)
    resp.raise_for_status()


def _cancel_ado(pipeline: dict, run_id: str) -> None:
    import requests
    org  = pipeline["ado_organization"]
    proj = pipeline["ado_project"]
    token = _get_sp_token(_RESOURCE_ADO)
    # ADO cancel goes through the Build API
    url = (
        f"https://dev.azure.com/{org}/{proj}"
        f"/_apis/build/builds/{run_id}?api-version=7.0"
    )
    resp = requests.patch(
        url,
        json={"status": "cancelling"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
