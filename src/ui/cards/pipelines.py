from __future__ import annotations
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
import logging

import streamlit as st
from streamlit_autorefresh import st_autorefresh

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


_BACKEND_COLOR = {
    "databricks": "var(--accent)",
    "adf":        "var(--deepblue)",
    "ado":        "var(--forest)",
}

_STATUS_SUCCESS = frozenset({"SUCCESS", "Succeeded", "succeeded"})
_STATUS_FAILED  = frozenset({"FAILED", "Failed", "failed",
                             "INTERNAL_ERROR", "TIMEDOUT",
                             "CANCELED", "Cancelled", "canceled"})


@st.dialog(t("pipelines.confirm_delete_title"))
def _show_delete_pipeline_dialog(pipeline_id: str):
    st.write(t("pipelines.confirm_delete_prompt"))
    _s, _c = st.columns(2)
    with _s:
        if st.button(t("pipelines.confirm_delete_button"), help=t("help.btn_confirm_delete_pipeline"), type="primary", use_container_width=True):
            with st.spinner(t("common.deleting")):
                delete_pipeline_def(pipeline_id)
            st.rerun()
    with _c:
        if st.button(t("common.cancel"), help=t("help.btn_common_cancel"), use_container_width=True):
            st.rerun()


def _pipeline_status_color(status: str) -> str:
    if status in _STATUS_SUCCESS:
        return "var(--forest)"
    if status in _STATUS_FAILED:
        return "var(--accent)"
    return "var(--ochre)"


@st.dialog(t("pipelines.create_title"), width="large")
def _show_pipeline_create_dialog():
    backend_opts = [b for b in BACKENDS]
    sel_label = st.radio(
        t("pipelines.backend"), options=backend_opts, format_func=lambda x: t(f"pipelines.backend_{x}"), horizontal=True, key="pl_create_backend",
    )
    backend = sel_label

    title = st.text_input(t("pipelines.field_title"), placeholder=t("pipelines.field_title_placeholder"), max_chars=120, key="pl_create_title")
    desc  = st.text_area(t("pipelines.field_desc"), placeholder=t("pipelines.field_desc_placeholder"), max_chars=300, height=80, key="pl_create_desc")

    db_job_id = adf_sub = adf_rg = adf_fact = adf_pipe = ado_org = ado_proj = ado_pid = None
    if backend == "databricks":
        db_job_id = st.text_input(t("pipelines.field_job_id"), placeholder=t("pipelines.field_job_id_placeholder"), key="pl_db_job")
    elif backend == "adf":
        adf_sub  = st.text_input(t("pipelines.field_adf_sub"),  placeholder=t("pipelines.field_adf_sub_placeholder"), key="pl_adf_sub")
        adf_rg   = st.text_input(t("pipelines.field_adf_rg"),   placeholder=t("pipelines.field_adf_rg_placeholder"), key="pl_adf_rg")
        adf_fact = st.text_input(t("pipelines.field_adf_fact"), placeholder=t("pipelines.field_adf_fact_placeholder"), key="pl_adf_fact")
        adf_pipe = st.text_input(t("pipelines.field_adf_pipe"), placeholder=t("pipelines.field_adf_pipe_placeholder"), key="pl_adf_pipe")
    elif backend == "ado":
        ado_org  = st.text_input(t("pipelines.field_ado_org"),  placeholder=t("pipelines.field_ado_org_placeholder"), key="pl_ado_org")
        ado_proj = st.text_input(t("pipelines.field_ado_proj"), placeholder=t("pipelines.field_ado_proj_placeholder"), key="pl_ado_proj")
        ado_pid  = st.text_input(t("pipelines.field_ado_pid"),  placeholder=t("pipelines.field_ado_pid_placeholder"), key="pl_ado_pid")

    _s, _c = st.columns(2)
    with _s:
        if st.button(t("common.save"), type="primary", use_container_width=True, key="pl_save"):
            with st.spinner(t("common.saving")):
                if not title.strip():
                    st.error(t("pipelines.error_title"))
                    return
                actor = st.session_state.get("user_email", "admin")
                create_pipeline_def(
                    title.strip(), (desc or "").strip(), backend,
                    db_job_id, adf_sub, adf_rg, adf_fact, adf_pipe,
                    ado_org, ado_proj, ado_pid, actor,
                )
                st.toast(t("common.saved"))
                st.rerun()
    with _c:
        if st.button(t("common.cancel"), help=t("help.btn_common_cancel"), use_container_width=True, key="pl_cancel"):
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
        st.markdown(
            f'<div style="padding: 24px; text-align: center; background: var(--paper-deep); border: 1px dashed var(--ink-20); border-radius: 4px;">'
            f'<div style="font-size: 24px; color: var(--ink-40); margin-bottom: 8px;">⚙️</div>'
            f'<div style="font-family: var(--font-sans); font-size: 14px; color: var(--ink-60);">{t("pipelines.no_pipelines")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    for pl in pipelines:
        color = _BACKEND_COLOR.get(pl["backend"], "var(--ink-40)")
        lbl   = t(f"pipelines.backend_{pl['backend']}")
        row_html = (
            f'<div style="border-left:3px solid {color};padding:8px 12px;'
            f'background:var(--paper-deep);border-radius:0 4px 4px 0;">'
            f'<span style="font-family:var(--font-mono);font-size:10px;text-transform:uppercase;'
            f'color:{color};letter-spacing:.08em;">{_html.escape(lbl)}</span>'
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
                _show_delete_pipeline_dialog(pl["pipeline_id"])


def render_pipelines_page():
    from src.config import pipelines_enabled
    if not pipelines_enabled() or (not is_pipeline_user() and not is_admin()):
        st.error(t("pipelines.access_denied"))
        st.stop()

    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("pipelines.eyebrow")}</div>
      <h1>{t("pipelines.hero_title")}</h1>
      <p class="lead">{t("pipelines.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    with st.expander(t("help.pipelines_expander")):
        st.markdown(t("help.pipelines_content"))

    pipelines = get_pipelines()
    if not pipelines:
        st.markdown(
            f'<div style="padding: 32px; text-align: center; background: var(--paper-deep); border: 1px dashed var(--ink-20); border-radius: 4px; margin-top: 24px;">'
            f'<div style="font-size: 32px; color: var(--ink-40); margin-bottom: 12px;">⚡</div>'
            f'<div style="font-family: var(--font-sans); font-size: 15px; color: var(--ink-60);">{t("pipelines.no_pipelines")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    _any_active = False
    actor = st.session_state.get("user_email", "user")

    active_runs = {pl["pipeline_id"]: get_active_run(pl["pipeline_id"]) for pl in pipelines}

    # Pre-poll statuses concurrently for active runs
    runs_to_poll = [(pl, active_runs[pl["pipeline_id"]]) for pl in pipelines if active_runs[pl["pipeline_id"]]]
    polled_results = {}
    if runs_to_poll:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=10) as executor:
            # list of results matches runs_to_poll
            results = list(executor.map(lambda pair: poll_run_status(pair[0], pair[1]), runs_to_poll))
            for (pl, _), res in zip(runs_to_poll, results):
                polled_results[pl["pipeline_id"]] = res

    for pl in pipelines:
        pid    = pl["pipeline_id"]
        color  = _BACKEND_COLOR.get(pl["backend"], "var(--ink-40)")
        blabel = t(f"pipelines.backend_{pl['backend']}")
        run    = active_runs[pid]

        with st.container():
            _pl_desc_html = (
                f'<div style="font-family:var(--font-sans);font-size:13px;'
                f'color:var(--ink-60);margin-top:4px;">{_html.escape(pl["description"])}</div>'
            ) if pl.get("description") else ""
            st.markdown(
                f'<div style="border-left:3px solid {color};padding:12px 16px;'
                f'background:var(--paper-deep);border-radius:0 4px 4px 0;margin-bottom:8px;">'
                f'<span style="font-family:var(--font-mono);font-size:10px;text-transform:uppercase;'
                f'color:{color};letter-spacing:.08em;">{_html.escape(blabel)}</span>'
                f'<div style="font-family:var(--font-display);font-size:20px;color:var(--ink);margin-top:2px;">'
                f'{_html.escape(pl["title"])}</div>'
                f'{_pl_desc_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

            if run:
                _any_active = True
                result = polled_results[pid]
                status   = result["status"]
                progress = result["progress"] / 100.0
                message  = result["message"]
                is_term  = result["is_terminal"]
                st_color = _pipeline_status_color(status)

                st.progress(progress, text="")
                _stat_col, _stop_col = st.columns([8, 2], gap="small")
                with _stat_col:
                    from src.i18n import format_date
                    triggered_str = format_date(run["triggered_at"])
                    _msg_html = (
                        f'<div style="color:var(--ink-60);margin-top:2px;">{_html.escape(message)}</div>'
                    ) if message else ""
                    st.markdown(
                        f'<div style="font-family:var(--font-mono);font-size:11px;">'
                        f'<span style="color:{st_color};">{_html.escape(str(status))}</span>'
                        f'<span style="color:var(--ink-40);margin-left:10px;">'
                        f'{t("pipelines.started_by", user=_html.escape(run.get("triggered_by", "?")), date=_html.escape(triggered_str))}</span>'
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
                        with st.spinner(t("pipelines.stopping")):
                            try:
                                cancel_run(pl, run)
                                st.toast(t("pipelines.stopped"))
                                st.rerun()
                            except Exception as _e:
                                logging.error("Pipeline action failed: %s", _e, exc_info=True)
                                # Security: do not expose internal error details to UI
                                st.error(t("pipelines.stop_error"))

            else:
                if st.button(
                    t("pipelines.start"), key=f"pl_start_{pid}",
                    help=t("pipelines.start_help"),
                    type="primary", use_container_width=False,
                ):
                    with st.spinner(t("pipelines.starting")):
                        try:
                            trigger_pipeline(pl, actor)
                            st.toast(t("pipelines.started"))
                            st.rerun()
                        except Exception as _e:
                            logging.error("Pipeline action failed: %s", _e, exc_info=True)
                            # Security: do not expose internal error details to UI
                            st.error(t("pipelines.start_error"))

            st.markdown("<div style='margin-bottom:16px'></div>", unsafe_allow_html=True)

    # Auto-poll every 3 s while any run is active.
    if _any_active:
        st_autorefresh(interval=3000, limit=None, key="pl_autorefresh")
