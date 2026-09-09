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

import html as _html
import logging

import pandas as pd
import streamlit as st

from src.audit import (
    approve_business_name,
    approve_table_business_name,
    reject_business_name,
    reject_table_business_name,
)
from src.auth import is_admin
from src.config import CATALOG_CACHE, SCHEMA_CACHE, is_demo_mode
from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import _get_write_connection, run_query
from src.analytics import get_zero_result_searches
from src.audit import (
    list_pending_business_names,
    list_pending_table_business_names,
)
from src.i18n import t, format_number, format_date
from src.personalization import is_editing_enabled, set_editing_enabled
from src.ui.cards.cms_admin import _render_admin_cms_section
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


def get_search_analytics() -> pd.DataFrame:
    """Return the last 50 zero-result searches."""
    data = get_zero_result_searches(50)
    if not data:
        return pd.DataFrame(columns=["query", "user_email", "timestamp"])
    return pd.DataFrame(data)


def get_high_impact_gaps() -> pd.DataFrame:
    """Identify popular tables missing descriptions or stewards."""
    if is_demo_mode() or not _duckdb_available():
        return pd.DataFrame()
    
    query = f"""
        WITH usage AS (
            SELECT object_name, COUNT(*) as interactions
            FROM user_data.audit_log
            GROUP BY object_name
        )
        SELECT 
            u.object_name as full_name,
            u.interactions,
            CASE 
                WHEN (m.comment IS NULL OR m.comment = '') THEN 'Missing description'
                WHEN (m.steward_email IS NULL OR m.steward_email = '') THEN 'Missing steward'
                ELSE 'Other'
            END as issue
        FROM usage u
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata m ON u.object_name = m.full_name
        WHERE (m.comment IS NULL OR m.comment = '' OR m.steward_email IS NULL OR m.steward_email = '')
        ORDER BY u.interactions DESC
        LIMIT 20
    """
    return run_query(query)


def get_stewardship_gaps() -> pd.DataFrame:
    """List tables without assigned stewards."""
    if is_demo_mode() or not _duckdb_available():
        return pd.DataFrame()
    
    query = f"""
        SELECT full_name, table_name, catalog_name, schema_name
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata
        WHERE steward_email IS NULL OR steward_email = ''
        LIMIT 100
    """
    return run_query(query)


def get_dq_alerts() -> pd.DataFrame:
    """List tables with failing DQ status."""
    if is_demo_mode() or not _duckdb_available():
        return pd.DataFrame()
    
    query = f"""
        SELECT m.full_name, m.table_name, dq.dq_score, dq.last_run_status
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata m
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.data_quality_cache dq ON m.full_name = dq.table_full_name
        WHERE dq.last_run_status = 'FAIL'
        ORDER BY dq.dq_score ASC
        LIMIT 100
    """
    return run_query(query)


# ── Audit / sync sections ────────────────────────────────────────────────────

@st.dialog(t("admin.biz_log_title"), width="large")
def _show_biz_log_dialog():
    st.markdown(VIS_WIDE_CSS, unsafe_allow_html=True)
    biz_log = get_business_name_change_log()
    st.dataframe(
        biz_log,
        column_config={
            "object_name": st.column_config.TextColumn(t("admin.col_object")),
            "old_value":   st.column_config.TextColumn(t("admin.col_old_name")),
            "new_value":   st.column_config.TextColumn(t("admin.col_new_name")),
            "actor_email": st.column_config.TextColumn(t("admin.col_changed_by")),
            "created_at":  st.column_config.TextColumn(t("admin.col_changed_at")),
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
            "object_name":     st.column_config.TextColumn(t("admin.col_object")),
            "comment_preview": st.column_config.TextColumn(t("admin.col_comment_preview")),
            "actor_email":     st.column_config.TextColumn(t("admin.col_author")),
            "created_at":      st.column_config.TextColumn(t("admin.col_posted_at")),
        },
        hide_index=True,
        use_container_width=True,
    )


def _render_admin_stats_section():
    stats = get_admin_stats()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(t("admin.stats_tables"), format_number(stats.get('tables', 0)))
    with c2:
        st.metric(t("admin.stats_columns"), format_number(stats.get('columns', 0)))
    with c3:
        st.metric(t("admin.stats_comments"), format_number(stats.get('comments', 0)))
    with c4:
        st.metric(t("admin.stats_overrides"), format_number(stats.get('overrides', 0)))


def _render_admin_integrity_report():
    """Admin section: Data Integrity Insights."""
    st.markdown(
        f'<div class="dd-section-header" style="margin-top:16px;">'
        f'<span class="dd-eyebrow">§ {t("admin.integrity_title")}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);'
        f'line-height:1.5;margin:8px 0 24px;">{t("admin.integrity_subtitle")}</p>',
        unsafe_allow_html=True,
    )

    col_l, col_r = st.columns(2, gap="large")

    with col_l:
        st.markdown(f"**{t('admin.integrity_impact_title')}**")
        st.caption(t("admin.integrity_impact_subtitle"))
        gaps = get_high_impact_gaps()
        if not gaps.empty:
            # Map issues to localized strings
            _issue_map = {
                "Missing description": t("admin.integrity_missing_desc"),
                "Missing steward": t("admin.integrity_missing_steward"),
            }
            # ⚡ Bolt: Replace .map(lambda) with vectorized .replace() for faster execution
            gaps["issue"] = gaps["issue"].replace(_issue_map)
            
            st.dataframe(
                gaps,
                column_config={
                    "full_name": t("admin.integrity_table"),
                    "interactions": st.column_config.NumberColumn(t("admin.integrity_popularity"), format="%d"),
                    "issue": t("admin.integrity_issue"),
                },
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info(t("common.empty"))

    with col_r:
        st.markdown(f"**{t('admin.integrity_dq_alerts_title')}**")
        st.caption(t("admin.integrity_dq_alerts_subtitle"))
        alerts = get_dq_alerts()
        if not alerts.empty:
            st.dataframe(
                alerts,
                column_config={
                    "full_name": t("admin.integrity_table"),
                    "dq_score": st.column_config.ProgressColumn(t("admin.col_score"), format="%.0f%%", min_value=0, max_value=100),
                    "last_run_status": t("admin.col_status"),
                },
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.success(t("admin.integrity_no_dq_failures"))

    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
    with st.expander(t("admin.integrity_stewardship_title")):
        st.caption(t("admin.integrity_stewardship_subtitle"))
        stew_gaps = get_stewardship_gaps()
        if not stew_gaps.empty:
            st.dataframe(stew_gaps, use_container_width=True, hide_index=True)
        else:
            st.success(t("admin.integrity_all_stewards_assigned"))


def _render_admin_search_analytics_section():
    """Render the zero-results search analytics table."""
    st.markdown(
        f'<div class="dd-section-header" style="margin-top:32px;">'
        f'<span class="dd-eyebrow">§ {t("admin.section_search_analytics")}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);'
        f'line-height:1.5;margin:8px 0 12px;">{t("admin.search_analytics_subtitle")}</p>',
        unsafe_allow_html=True,
    )
    df = get_search_analytics()
    if df.empty:
        st.info(t("admin.search_analytics_empty"))
    else:
        st.dataframe(
            df,
            column_config={
                "query": t("admin.search_analytics_query"),
                "user_email": t("admin.search_analytics_user"),
                "timestamp": st.column_config.DatetimeColumn(t("admin.search_analytics_time")),
            },
            use_container_width=True,
            hide_index=True,
        )


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
        st.progress(pct_complete / 100.0, text=t("admin.sync_progress", pct=f"{pct_complete:.1f}"))
        bc1, bc2, bc3, bc4 = st.columns(4)
        bc1.caption(t("admin.sync_pending", count=sync_stats.get("pending", 0)))
        bc2.caption(t("admin.sync_processing", count=sync_stats.get("processing", 0)))
        bc3.caption(t("admin.sync_done", count=sync_stats.get("done", 0)))
        bc4.caption(t("admin.sync_failed", count=sync_stats.get("failed", 0)))

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
            f'text-transform:uppercase;">{t("admin.sync_self_healing")}</div>'
            f'<div style="font-family:var(--font-sans); font-size:14px; font-weight:600; '
            f'color:var(--ink);">{_html.escape(str(dr_status))}</div>'
            f'<div style="margin-top:12px; font-family:var(--font-mono); font-size:10px; '
            f'color:var(--ink-40); text-transform:uppercase;">{t("admin.sync_worker_heartbeat")}</div>'
            f'<div style="font-family:var(--font-mono); font-size:11px; '
            f'color:var(--ink-60);">{_html.escape(str(heartbeat))}</div>'
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
        st.toast(t("common.saved"))
        st.rerun()

    status_color = "var(--accent)" if enabled else "var(--ink-40)"
    status_label = t("admin.editing_enabled") if enabled else t("admin.editing_disabled")
    st.markdown(
        f'<p style="font-family:var(--font-mono); font-size:11px; color:{status_color}; '
        f'margin-top:4px;">{status_label}</p>',
        unsafe_allow_html=True,
    )


def _render_admin_groups_cache_section():
    """Admin tool: flush every user's cached Entra group membership."""
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
        with st.spinner(t("admin.groups_cache_flushing")):
            from src.auth_graph import clear_groups_cache  # noqa: PLC0415
            n = clear_groups_cache()
        st.success(t("admin.groups_cache_flushed", n=n))


def _render_pending_reviews_section():
    """Admin section: list pending column-override proposals and approve/reject them."""
    import html as _html
    st.markdown(
        f'<div class="dd-section-header" style="margin-top:32px;">'
        f'<span class="dd-eyebrow">§ {t("admin.reviews_title")}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);'
        f'line-height:1.5;margin:8px 0 12px;">{t("admin.reviews_subtitle")}</p>',
        unsafe_allow_html=True,
    )
    try:
        pending = list_pending_business_names()
    except Exception as exc:
        logging.warning("Could not load pending reviews: %s", exc)
        pending = []

    if not pending:
        st.markdown(
            f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-40);">'
            f'{t("admin.reviews_empty")}</p>',
            unsafe_allow_html=True,
        )
        return

    if len(pending) > 50:
        st.info(t("search.showing_first_50", count=len(pending)))
        pending = pending[:50]

    for item in pending:
        tbl  = str(item.get("table_full_name", ""))
        col  = str(item.get("column_name", ""))
        biz  = str(item.get("business_name", "") or "")
        defn = str(item.get("definition", "") or "")
        by   = str(item.get("edited_by", ""))
        _raw_at = item.get("edited_at")
        at   = format_date(_raw_at)
        st.markdown(
            f'<div style="background:var(--paper);border:1px solid var(--ink-10);'
            f'border-radius:4px;padding:12px 16px;margin-bottom:8px;">'
            f'<div style="font-family:var(--font-mono);font-size:11px;color:var(--ink-40);'
            f'text-transform:uppercase;margin-bottom:4px;">'
            f'{_html.escape(tbl)} · {_html.escape(col)}</div>'
            f'<div style="display:flex;gap:24px;margin:6px 0;">'
            f'<div><span style="font-family:var(--font-mono);font-size:10px;color:var(--ink-40);">'
            f'{_html.escape(t("admin.reviews_new_value"))}</span>'
            f'<div style="font-family:var(--font-sans);font-size:13px;color:var(--ink);">'
            f'{_html.escape(biz)}</div>'
            f'<div style="font-family:var(--font-sans);font-size:12px;color:var(--ink-60);">'
            f'{_html.escape(defn)}</div></div>'
            f'</div>'
            f'<div style="font-family:var(--font-mono);font-size:11px;color:var(--ink-40);'
            f'margin-top:4px;">'
            f'{_html.escape(t("admin.reviews_proposed_by", user=by, date=at))}'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        _c_approve, _c_reject, _ = st.columns([2, 2, 8], gap="small")
        with _c_approve:
            if st.button(
                t("admin.reviews_approve"),
                key=f"rev_approve_{tbl}_{col}",
                type="primary",
                use_container_width=True,
                help=t("help.btn_approve"),
            ):
                try:
                    with st.spinner(t("common.saving")):
                        approve_business_name(tbl, col)
                    st.toast(t("admin.reviews_approved_toast", col=col))
                    st.rerun()
                except Exception as exc:
                    logging.error("Failed to approve: %s", exc, exc_info=True)
                    # Security: do not expose internal error details to UI
                    st.error(t("common.error"))
        with _c_reject:
            if st.button(
                t("admin.reviews_reject"),
                key=f"rev_reject_{tbl}_{col}",
                use_container_width=True,
                help=t("help.btn_reject"),
            ):
                try:
                    with st.spinner(t("common.saving")):
                        reject_business_name(tbl, col)
                    st.toast(t("admin.reviews_rejected_toast", col=col))
                    st.rerun()
                except Exception as exc:
                    logging.error("Failed to reject: %s", exc, exc_info=True)
                    # Security: do not expose internal error details to UI
                    st.error(t("common.error"))


def _render_pending_table_friendly_names_section():
    """Admin section: approve/reject pending table-level friendly-name proposals.

    Approval here is what enqueues the sidecar write-back to the configured UC
    business-names table; rejection drops the proposal without touching UC.
    """
    import html as _html
    st.markdown(
        f'<div class="dd-section-header" style="margin-top:32px;">'
        f'<span class="dd-eyebrow">§ {t("admin.table_friendly_reviews_title")}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);'
        f'line-height:1.5;margin:8px 0 12px;">{t("admin.table_friendly_reviews_subtitle")}</p>',
        unsafe_allow_html=True,
    )
    try:
        pending = list_pending_table_business_names()
    except Exception as exc:
        logging.warning("Could not load pending table friendly names: %s", exc)
        pending = []

    if not pending:
        st.markdown(
            f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-40);">'
            f'{t("admin.reviews_empty")}</p>',
            unsafe_allow_html=True,
        )
        return

    if len(pending) > 50:
        st.info(t("search.showing_first_50", count=len(pending)))
        pending = pending[:50]

    from src.i18n import format_date
    for item in pending:
        tbl     = str(item.get("table_full_name", ""))
        name_en = str(item.get("business_name_en", "") or "")
        name_fr = str(item.get("business_name_fr", "") or "")
        def_en  = str(item.get("business_definition_en", "") or "")
        def_fr  = str(item.get("business_definition_fr", "") or "")
        by      = str(item.get("edited_by", ""))
        _raw_at = item.get("edited_at")
        at      = format_date(_raw_at)
        st.markdown(
            f'<div style="background:var(--paper);border:1px solid var(--ink-10);'
            f'border-radius:4px;padding:12px 16px;margin-bottom:8px;">'
            f'<div style="font-family:var(--font-mono);font-size:11px;color:var(--ink-40);'
            f'text-transform:uppercase;margin-bottom:6px;">{_html.escape(tbl)}</div>'
            f'<div style="display:flex;gap:24px;margin:6px 0;flex-wrap:wrap;">'
            f'<div style="flex:1;min-width:240px;">'
            f'<span style="font-family:var(--font-mono);font-size:10px;color:var(--ink-40);">{_html.escape(t("language.en"))}</span>'
            f'<div style="font-family:var(--font-sans);font-size:14px;font-weight:500;color:var(--ink);">{_html.escape(name_en)}</div>'
            f'<div style="font-family:var(--font-sans);font-size:12px;color:var(--ink-60);">{_html.escape(def_en)}</div>'
            f'</div>'
            f'<div style="flex:1;min-width:240px;">'
            f'<span style="font-family:var(--font-mono);font-size:10px;color:var(--ink-40);">{_html.escape(t("language.fr"))}</span>'
            f'<div style="font-family:var(--font-sans);font-size:14px;font-weight:500;color:var(--ink);">{_html.escape(name_fr)}</div>'
            f'<div style="font-family:var(--font-sans);font-size:12px;color:var(--ink-60);">{_html.escape(def_fr)}</div>'
            f'</div>'
            f'</div>'
            f'<div style="font-family:var(--font-mono);font-size:11px;color:var(--ink-40);margin-top:6px;">'
            f'{_html.escape(t("admin.reviews_proposed_by", user=by, date=at))}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        _c_approve, _c_reject, _ = st.columns([2, 2, 8], gap="small")
        with _c_approve:
            if st.button(
                t("admin.reviews_approve"),
                key=f"tfn_approve_{tbl}",
                type="primary", use_container_width=True,
                help=t("help.btn_approve"),
            ):
                try:
                    with st.spinner(t("common.saving")):
                        approve_table_business_name(tbl)
                    st.toast(t("admin.table_friendly_approved_toast", table=tbl))
                    st.rerun()
                except Exception as exc:
                    logging.error("Failed to approve table friendly name: %s", exc, exc_info=True)
                    st.error(t("common.error"))
        with _c_reject:
            if st.button(
                t("admin.reviews_reject"),
                key=f"tfn_reject_{tbl}",
                use_container_width=True,
                help=t("help.btn_reject"),
            ):
                try:
                    with st.spinner(t("common.saving")):
                        reject_table_business_name(tbl)
                    st.toast(t("admin.table_friendly_rejected_toast", table=tbl))
                    st.rerun()
                except Exception as exc:
                    logging.error("Failed to reject table friendly name: %s", exc, exc_info=True)
                    st.error(t("common.error"))


def render_admin_page():
    if not is_admin():
        st.error(t("admin.access_denied"))
        st.stop()

    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("admin.title")}</div>
      <h1>{t("admin.hero_title")}</h1>
      <p class="lead">{t("admin.subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    _admin_tabs = ["ops", "insights", "audit"]
    _admin_tab_labels = {
        "ops": t("admin.tab_ops"),
        "insights": t("admin.tab_insights"),
        "audit": t("admin.tab_audit"),
    }

    if st.session_state.get("admin_active_tab") not in _admin_tabs:
        st.session_state["admin_active_tab"] = _admin_tabs[0]

    _admin_active = st.segmented_control(
        "admin_tabs",
        options=_admin_tabs,
        format_func=lambda x: _admin_tab_labels[x[0]] if isinstance(x, list) and len(x) > 0 else _admin_tab_labels.get(x, "") if not isinstance(x, list) else "",
        key="admin_active_tab",
        label_visibility="collapsed",
        selection_mode="single",
    )
    if _admin_active is None:
        _admin_active = "ops"

    if _admin_active == "ops":
        with st.expander(t("help.admin_ops_expander")):
            st.markdown(t("help.admin_ops_content"))
        _render_pending_reviews_section()
        _render_pending_table_friendly_names_section()
        _render_admin_cms_section()
        _render_admin_pipelines_section()
        _render_admin_editing_section()
        _render_admin_groups_cache_section()
        _render_admin_sync_section()
    elif _admin_active == "insights":
        with st.expander(t("help.admin_insights_expander")):
            st.markdown(t("help.admin_insights_content"))
        _render_admin_stats_section()
        _render_admin_search_analytics_section()
        _render_admin_integrity_report()
    else:
        with st.expander(t("help.admin_audit_expander")):
            st.markdown(t("help.admin_audit_content"))
        _render_admin_biz_log_section()
        _render_admin_comment_log_section()
