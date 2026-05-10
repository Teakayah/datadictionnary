"""Admin page — composition of admin-only sections.

Sections, in render order:
1. Stats               — four metric cards (tables / columns / comments / overrides)
2. CMS                 — list + create/delete posts (pinned banner content)
3. Pipelines           — definitions CRUD; live runs render on /pipelines tab
4. Inline editing toggle
5. Sync queue + DR resync status (read from user_data.site_settings)
6. Business name change log (last 200, with expand-to-dialog)
7. Comment log (last 200, with expand-to-dialog)

This module owns all write surfaces visible to admins (CMS create/delete,
pipeline create/delete, editing toggle). Read-only data fetchers
(get_admin_stats, get_business_name_change_log, get_comment_log,
get_sync_queue_stats) are kept here too because their only callers are
the renderers below — moving them out would be premature.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from src.auth import is_admin
from src.config import CATALOG_CACHE, SCHEMA_CACHE, is_demo_mode
from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import _get_write_connection, run_query
from src.i18n import t
from src.personalization import is_editing_enabled, set_editing_enabled
from src.ui.cards.cms_admin import _render_admin_cms_section, _show_cms_create_dialog  # noqa: F401
from src.ui.cards.pipelines import _render_admin_pipelines_section
from src.ui.css import VIS_WIDE_CSS


# ── Read-only fetchers ──────────────────────────────────────────────────────

def get_admin_stats() -> dict:
    """Return four catalog-wide counts for the admin dashboard."""
    if is_demo_mode():
        return {
            "tables":    0,
            "columns":   0,
            "comments":  sum(len(v) for v in st.session_state.get("demo_comments", {}).values()),
            "overrides": sum(len(v) for v in st.session_state.get("demo_business_names", {}).values()),
        }
    try:
        _ud = _duckdb_available()
        comments_tbl  = "user_data.comments" if _ud else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.comments"
        overrides_tbl = (
            "user_data.business_name_overrides"
            if _ud
            else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides"
        )
        tables_tbl    = f"{CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata"
        columns_tbl   = f"{CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata"

        # Bolt ⚡: Consolidate 4 queries into 1 to reduce DuckDB connection overhead
        # and pandas DataFrame instantiation time (~50% faster).
        query = f"""
            SELECT
                (SELECT COUNT(*) FROM {tables_tbl}) AS tables,
                (SELECT COUNT(*) FROM {columns_tbl}) AS columns,
                (SELECT COUNT(*) FROM {comments_tbl}) AS comments,
                (SELECT COUNT(*) FROM {overrides_tbl}) AS overrides
        """
        df = run_query(query)

        return {
            "tables": int(df.iloc[0]["tables"]),
            "columns": int(df.iloc[0]["columns"]),
            "comments": int(df.iloc[0]["comments"]),
            "overrides": int(df.iloc[0]["overrides"]),
        }
    except Exception as e:
        logging.warning("Failed to fetch admin stats: %s", e)
        return {"tables": 0, "columns": 0, "comments": 0, "overrides": 0}


def get_business_name_change_log() -> pd.DataFrame:
    """Return the last 200 business name change events for the admin log."""
    if is_demo_mode():
        logs = [
            log for log in st.session_state.get("demo_audit_log", [])
            if log["event_type"] == "business_name_change"
        ]
        if not logs:
            return pd.DataFrame(columns=[
                "event_id", "object_name", "old_value", "new_value",
                "actor_email", "created_at",
            ])
        return pd.DataFrame(logs).sort_values("created_at", ascending=False).head(200)
    audit_tbl = (
        "user_data.audit_log"
        if _duckdb_available()
        else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log"
    )
    return run_query(
        f"SELECT event_id, object_name, old_value, new_value, actor_email, created_at "
        f"FROM {audit_tbl} "
        f"WHERE event_type = 'business_name_change' "
        f"ORDER BY created_at DESC LIMIT 200"
    )


def get_comment_log() -> pd.DataFrame:
    """Return the last 200 comment/reply events for the admin log."""
    if is_demo_mode():
        logs = [
            log for log in st.session_state.get("demo_audit_log", [])
            if log["event_type"] in ("comment_added", "comment_reply")
        ]
        if not logs:
            return pd.DataFrame(columns=[
                "event_id", "object_name", "comment_preview",
                "actor_email", "created_at",
            ])
        df = pd.DataFrame(logs).rename(columns={"new_value": "comment_preview"})
        return df.sort_values("created_at", ascending=False).head(200)
    audit_tbl = (
        "user_data.audit_log"
        if _duckdb_available()
        else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log"
    )
    return run_query(
        f"SELECT event_id, object_name, new_value AS comment_preview, "
        f"       actor_email, created_at "
        f"FROM {audit_tbl} "
        f"WHERE event_type IN ('comment_added', 'comment_reply') "
        f"ORDER BY created_at DESC LIMIT 200"
    )


def get_sync_queue_stats() -> dict:
    """Return counts of pending_sync items by status."""
    if not _duckdb_available():
        return {}
    try:
        conn = _get_write_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT status, COUNT(*) FROM user_data.pending_sync GROUP BY status"
            )
            rows = cursor.fetchall()
            stats = {row[0]: row[1] for row in rows}
            for s in ("pending", "processing", "done", "failed"):
                stats.setdefault(s, 0)
            return stats
    except Exception:
        return {"pending": 0, "processing": 0, "done": 0, "failed": 0}


# ── Audit / sync sections ────────────────────────────────────────────────────

@st.dialog(t("admin.biz_log_title"), width="large")
def _show_biz_log_dialog():
    st.markdown(VIS_WIDE_CSS, unsafe_allow_html=True)
    biz_log = get_business_name_change_log()
    st.dataframe(
        biz_log,
        column_config={
            "object_name": st.column_config.TextColumn("Object"),
            "old_value":   st.column_config.TextColumn("Old name"),
            "new_value":   st.column_config.TextColumn("New name"),
            "actor_email": st.column_config.TextColumn("Changed by"),
            "created_at":  st.column_config.TextColumn("Changed at"),
        },
        hide_index=True,
        use_container_width=True,
    )


@st.dialog(t("admin.comment_log_title"), width="large")
def _show_comment_log_dialog():
    st.markdown(VIS_WIDE_CSS, unsafe_allow_html=True)
    comment_log = get_comment_log()
    st.dataframe(
        comment_log,
        column_config={
            "object_name":     st.column_config.TextColumn("Object"),
            "comment_preview": st.column_config.TextColumn("Comment preview"),
            "actor_email":     st.column_config.TextColumn("Author"),
            "created_at":      st.column_config.TextColumn("Posted at"),
        },
        hide_index=True,
        use_container_width=True,
    )


def _render_admin_stats_section():
    stats = get_admin_stats()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(t("admin.stats_tables"), f"{stats.get('tables', 0):,}")
    with c2:
        st.metric(t("admin.stats_columns"), f"{stats.get('columns', 0):,}")
    with c3:
        st.metric(t("admin.stats_comments"), f"{stats.get('comments', 0):,}")
    with c4:
        st.metric(t("admin.stats_overrides"), f"{stats.get('overrides', 0):,}")


def _render_admin_sync_section():
    st.markdown(
        f'<div class="dd-section-header" style="margin-top:32px;">'
        f'<span class="dd-eyebrow">§ {t("admin.sync_title")}</span></div>',
        unsafe_allow_html=True,
    )

    sync_stats = get_sync_queue_stats()
    total_jobs = sum(sync_stats.values())
    done_jobs = sync_stats.get("done", 0)
    pct_complete = (done_jobs / total_jobs * 100) if total_jobs > 0 else 100.0

    sc1, sc2 = st.columns([7, 3], gap="large")
    with sc1:
        st.progress(pct_complete / 100.0, text=f"{pct_complete:.1f}% synced with Databricks")
        bc1, bc2, bc3, bc4 = st.columns(4)
        bc1.caption(f"Pending: {sync_stats.get('pending', 0)}")
        bc2.caption(f"Processing: {sync_stats.get('processing', 0)}")
        bc3.caption(f"Done: {sync_stats.get('done', 0)}")
        bc4.caption(f"Failed: {sync_stats.get('failed', 0)}")

    with sc2:
        # Sidecar daemon status, written into user_data.site_settings.
        from src.sync.worker import read_dr_resync_status, read_worker_heartbeat
        dr_status = read_dr_resync_status()
        heartbeat = read_worker_heartbeat() or "—"
        accent = "var(--accent-ink)" if dr_status.startswith("Error") else "var(--deepblue)"

        st.markdown(
            f'<div style="background:var(--paper-deep); padding:12px; border-radius:4px; '
            f'border-left:4px solid {accent};">'
            f'<div style="font-family:var(--font-mono); font-size:10px; color:var(--ink-40); '
            f'text-transform:uppercase;">Self-Healing (DR)</div>'
            f'<div style="font-family:var(--font-sans); font-size:14px; font-weight:600; '
            f'color:var(--ink);">{dr_status}</div>'
            f'<div style="margin-top:12px; font-family:var(--font-mono); font-size:10px; '
            f'color:var(--ink-40); text-transform:uppercase;">Worker heartbeat</div>'
            f'<div style="font-family:var(--font-mono); font-size:11px; '
            f'color:var(--ink-60);">{heartbeat}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div style="margin-top:32px;"></div>', unsafe_allow_html=True)


def _render_admin_biz_log_section():
    _biz_h, _biz_btn = st.columns([9, 1], gap="small")
    with _biz_h:
        st.markdown(
            f'<div class="dd-section-header"><span class="dd-eyebrow">§ {t("admin.biz_log_title")}</span></div>',
            unsafe_allow_html=True,
        )
    with _biz_btn:
        if st.button("⤢", key="admin_biz_log_expand", help=t("admin.expand_log"), use_container_width=True):
            _show_biz_log_dialog()
    st.markdown('<div style="margin-top:24px;"></div>', unsafe_allow_html=True)


def _render_admin_comment_log_section():
    _cmt_h, _cmt_btn = st.columns([9, 1], gap="small")
    with _cmt_h:
        st.markdown(
            f'<div class="dd-section-header"><span class="dd-eyebrow">§ {t("admin.comment_log_title")}</span></div>',
            unsafe_allow_html=True,
        )
    with _cmt_btn:
        if st.button("⤢", key="admin_comment_log_expand", help=t("admin.expand_log"), use_container_width=True):
            _show_comment_log_dialog()


def _render_admin_editing_section():
    st.markdown(
        f'<div class="dd-section-header" style="margin-top:32px;">'
        f'<span class="dd-eyebrow">§ {t("admin.editing_title")}</span></div>',
        unsafe_allow_html=True,
    )
    enabled = is_editing_enabled()
    new_val = st.toggle(
        t("admin.editing_toggle"),
        value=enabled,
        key="admin_editing_toggle",
        help=t("admin.editing_help"),
    )
    if new_val != enabled:
        actor = st.session_state.get("user_email", "admin")
        set_editing_enabled(new_val, actor)
        st.rerun()

    status_color = "var(--accent)" if enabled else "var(--ink-40)"
    status_label = t("admin.editing_enabled") if enabled else t("admin.editing_disabled")
    st.markdown(
        f'<p style="font-family:var(--font-mono); font-size:11px; color:{status_color}; '
        f'margin-top:4px;">{status_label}</p>',
        unsafe_allow_html=True,
    )


def _render_admin_groups_cache_section():
    """Admin tool: flush every user's cached Entra group membership.

    After granting a user a new Entra group, click this to drop the
    process-level groups cache so the next render of every active
    session re-fetches via Graph (for overage users) or the inline
    claim. Without this, group changes can take up to 1h to propagate
    (the cache TTL).
    """
    st.markdown(
        f'<div class="dd-section-header" style="margin-top:32px;">'
        f'<span class="dd-eyebrow">§ {t("admin.groups_cache_title")}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="font-family:var(--font-sans); font-size:13px; '
        f'color:var(--ink-60); line-height:1.5; margin:8px 0 12px;">'
        f'{t("admin.groups_cache_subtitle")}</p>',
        unsafe_allow_html=True,
    )
    if st.button(
        t("admin.groups_cache_flush"),
        key="admin_groups_cache_flush",
        type="secondary",
    ):
        from src.auth_graph import clear_groups_cache  # noqa: PLC0415
        n = clear_groups_cache()
        st.success(t("admin.groups_cache_flushed", n=n))


def render_admin_page():
    if not is_admin():
        st.error(t("admin.access_denied"))
        st.stop()

    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("admin.title")}</div>
      <h1>Administration.</h1>
      <p class="lead">{t("admin.subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    _render_admin_stats_section()
    _render_admin_cms_section()
    _render_admin_pipelines_section()
    _render_admin_editing_section()
    _render_admin_groups_cache_section()
    _render_admin_sync_section()
    _render_admin_biz_log_section()
    _render_admin_comment_log_section()
