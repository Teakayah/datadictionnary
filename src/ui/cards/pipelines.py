from __future__ import annotations
from typing import Any, Callable, Optional, Protocol, runtime_checkable
"""Pipelines tab UI — list, run, monitor, cancel pipeline runs.

Three render points:
- ``render_pipelines_page``        — the /pipelines tab itself.
- ``_render_admin_pipelines_section`` — the pipeline-definitions block on the
  admin page (CRUD + create dialog).
- ``_show_pipeline_create_dialog`` — modal used by the admin section.

Backend logic (start / poll / cancel) lives in src/pipelines.py — this
module is rendering only.
"""


import html as _html
import time

import streamlit as st

from src.auth import is_admin, is_pipeline_user
from src.i18n import t
from src.pipelines import (
    BACKENDS,
    cancel_run,
    create_pipeline_def,
    delete_pipeline_def,
    get_active_run,
    get_pipelines,
    poll_run_status,
    trigger_pipeline,
)

_BACKEND_LABEL = {
    "databricks": "Databricks",
    "adf":        "Azure Data Factory",
    "ado":        "Azure DevOps",
}
_BACKEND_COLOR = {
    "databricks": "var(--accent)",
    "adf":        "var(--deepblue)",
    "ado":        "var(--forest)",
}

_STATUS_SUCCESS = frozenset({"SUCCESS", "Succeeded", "succeeded"})
_STATUS_FAILED  = frozenset({"FAILED", "Failed", "failed",
                             "INTERNAL_ERROR", "TIMEDOUT",
                             "CANCELED", "Cancelled", "canceled"})


def _pipeline_status_color(status: str) -> str:
    if status in _STATUS_SUCCESS:
        return "var(--forest)"
    if status in _STATUS_FAILED:
        return "var(--accent)"
    return "var(--ochre)"


@st.dialog(t("pipelines.create_title"), width="large")
def _show_pipeline_create_dialog():
    backend_opts = [_BACKEND_LABEL[b] for b in BACKENDS]
    sel_label = st.radio(
        t("pipelines.backend"), options=backend_opts, horizontal=True, key="pl_create_backend",
    )
    backend = next(b for b in BACKENDS if _BACKEND_LABEL[b] == sel_label)

    title = st.text_input(t("pipelines.field_title"), max_chars=120, key="pl_create_title")
    desc  = st.text_area(t("pipelines.field_desc"),  max_chars=300, height=80, key="pl_create_desc")

    db_job_id = adf_sub = adf_rg = adf_fact = adf_pipe = ado_org = ado_proj = ado_pid = None
    if backend == "databricks":
        db_job_id = st.text_input(t("pipelines.field_job_id"), placeholder="1234", key="pl_db_job")
    elif backend == "adf":
        adf_sub  = st.text_input(t("pipelines.field_adf_sub"),  key="pl_adf_sub")
        adf_rg   = st.text_input(t("pipelines.field_adf_rg"),   key="pl_adf_rg")
        adf_fact = st.text_input(t("pipelines.field_adf_fact"), key="pl_adf_fact")
        adf_pipe = st.text_input(t("pipelines.field_adf_pipe"), key="pl_adf_pipe")
    elif backend == "ado":
        ado_org  = st.text_input(t("pipelines.field_ado_org"),  key="pl_ado_org")
        ado_proj = st.text_input(t("pipelines.field_ado_proj"), key="pl_ado_proj")
        ado_pid  = st.text_input(t("pipelines.field_ado_pid"),  placeholder="42", key="pl_ado_pid")

    _s, _c = st.columns(2)
    with _s:
        if st.button(t("common.save"), type="primary", use_container_width=True, key="pl_save"):
            if not title.strip():
                st.error(t("pipelines.error_title"))
                return
            actor = st.session_state.get("user_email", "admin")
            create_pipeline_def(
                title.strip(), (desc or "").strip(), backend,
                db_job_id, adf_sub, adf_rg, adf_fact, adf_pipe,
                ado_org, ado_proj, ado_pid, actor,
            )
            st.rerun()
    with _c:
        if st.button(t("common.cancel"), use_container_width=True, key="pl_cancel"):
            st.rerun()


def _render_admin_pipelines_section():
    _h, _btn = st.columns([9, 1], gap="small")
    with _h:
        st.markdown(
            f'<div class="dd-section-header" style="margin-top:32px;">'
            f'<span class="dd-eyebrow">§ {t("pipelines.admin_title")}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with _btn:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        if st.button("＋", key="pl_admin_new", help=t("pipelines.new_pipeline"), use_container_width=True):
            _show_pipeline_create_dialog()

    pipelines = get_pipelines()
    if not pipelines:
        st.caption(t("pipelines.no_pipelines"))
        return

    for pl in pipelines:
        color = _BACKEND_COLOR.get(pl["backend"], "var(--ink-40)")
        lbl   = _BACKEND_LABEL.get(pl["backend"], pl["backend"])
        row_html = (
            f'<div style="border-left:3px solid {color};padding:8px 12px;'
            f'background:var(--paper-deep);border-radius:0 4px 4px 0;">'
            f'<span style="font-family:var(--font-mono);font-size:10px;text-transform:uppercase;'
            f'color:{color};letter-spacing:.08em;">{lbl}</span>'
            f'<span style="font-family:var(--font-sans);font-size:14px;color:var(--ink);margin-left:10px;">'
            f'{_html.escape(pl["title"])}</span>'
            f'</div>'
        )
        _row, _del = st.columns([11, 1], gap="small")
        with _row:
            st.markdown(row_html, unsafe_allow_html=True)
        with _del:
            st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
            if st.button(
                "✕", key=f"pl_del_{pl['pipeline_id']}",
                help=t("pipelines.delete"), use_container_width=True,
            ):
                delete_pipeline_def(pl["pipeline_id"])
                st.rerun()


def render_pipelines_page():
    if not is_pipeline_user() and not is_admin():
        st.error(t("pipelines.access_denied"))
        st.stop()

    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("pipelines.eyebrow")}</div>
      <h1>{t("pipelines.hero_title")}</h1>
      <p class="lead">{t("pipelines.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    pipelines = get_pipelines()
    if not pipelines:
        st.info(t("pipelines.no_pipelines"))
        return

    _any_active = False
    actor = st.session_state.get("user_email", "user")

    for pl in pipelines:
        pid    = pl["pipeline_id"]
        color  = _BACKEND_COLOR.get(pl["backend"], "var(--ink-40)")
        blabel = _BACKEND_LABEL.get(pl["backend"], pl["backend"])
        run    = get_active_run(pid)

        with st.container():
            _pl_desc_html = (
                f'<div style="font-family:var(--font-sans);font-size:13px;'
                f'color:var(--ink-60);margin-top:4px;">{_html.escape(pl["description"])}</div>'
            ) if pl.get("description") else ""
            st.markdown(
                f'<div style="border-left:3px solid {color};padding:12px 16px;'
                f'background:var(--paper-deep);border-radius:0 4px 4px 0;margin-bottom:8px;">'
                f'<span style="font-family:var(--font-mono);font-size:10px;text-transform:uppercase;'
                f'color:{color};letter-spacing:.08em;">{blabel}</span>'
                f'<div style="font-family:var(--font-display);font-size:20px;color:var(--ink);margin-top:2px;">'
                f'{_html.escape(pl["title"])}</div>'
                f'{_pl_desc_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

            if run:
                _any_active = True
                result = poll_run_status(pl, run)
                status   = result["status"]
                progress = result["progress"] / 100.0
                message  = result["message"]
                is_term  = result["is_terminal"]
                st_color = _pipeline_status_color(status)

                st.progress(progress, text="")
                _stat_col, _stop_col = st.columns([8, 2], gap="small")
                with _stat_col:
                    triggered_str = (
                        run["triggered_at"].strftime("%b %d %H:%M UTC")
                        if hasattr(run.get("triggered_at"), "strftime")
                        else str(run.get("triggered_at", ""))[:16]
                    )
                    _msg_html = (
                        f'<div style="color:var(--ink-60);margin-top:2px;">{_html.escape(message)}</div>'
                    ) if message else ""
                    st.markdown(
                        f'<div style="font-family:var(--font-mono);font-size:11px;">'
                        f'<span style="color:{st_color};">{status}</span>'
                        f'<span style="color:var(--ink-40);margin-left:10px;">'
                        f'started by {_html.escape(run.get("triggered_by","?"))} · {triggered_str}</span>'
                        f'{_msg_html}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with _stop_col:
                    if not is_term and st.button(
                        t("pipelines.stop"), key=f"pl_stop_{pid}",
                        help=t("pipelines.stop_help"),
                        type="primary", use_container_width=True,
                    ):
                        try:
                            cancel_run(pl, run)
                            st.success(t("pipelines.stopped"))
                        except Exception as _e:
                            st.error(f"{t('pipelines.stop_error')}: {_e}")
                        st.rerun()

            else:
                if st.button(
                    t("pipelines.start"), key=f"pl_start_{pid}",
                    help=t("pipelines.start_help"),
                    type="secondary", use_container_width=False,
                ):
                    try:
                        trigger_pipeline(pl, actor)
                        st.rerun()
                    except Exception as _e:
                        st.error(f"{t('pipelines.start_error')}: {_e}")

            st.markdown("<div style='margin-bottom:16px'></div>", unsafe_allow_html=True)

    # Auto-poll every 3 s while any run is active.
    if _any_active:
        time.sleep(3)
        st.rerun()
