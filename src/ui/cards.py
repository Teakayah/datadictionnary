from __future__ import annotations

import html as _html
import logging
import re
import threading
import time

import pandas as pd
import streamlit as st

from src.audit import save_table_metadata
from src.auth import is_admin, is_pipeline_user
from src.cms import POST_TYPES, _EXPIRY_DAYS, create_post, delete_post, get_active_posts, get_all_posts
from src.pipelines import (
    BACKENDS, cancel_run, create_pipeline_def, delete_pipeline_def,
    get_active_run, get_pipelines, poll_run_status, trigger_pipeline,
)
from src.config import CATALOG_CACHE, SCHEMA_CACHE, is_demo_mode
from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import _get_write_connection, run_query, get_authorized_tables
from src.i18n import t
from src.personalization import is_editing_enabled, set_editing_enabled
from src.ui.css import VIS_WIDE_CSS
_DQ_GRADES = [
    (90, "A", "dq-a"),
    (75, "B", "dq-b"),
    (60, "C", "dq-c"),
    (0,  "D", "dq-d"),
]


def _dq_grade(score_str) -> tuple:
    """Return (letter, css_class) from a dq_score string or number."""
    try:
        score = float(score_str or 0)
    except (ValueError, TypeError):
        score = 0
    for threshold, letter, cls in _DQ_GRADES:
        if score >= threshold:
            return letter, cls
    return "D", "dq-d"


def _compute_live_completeness(table_full_name: str) -> float:
    """Live column-definition coverage: (metadata comment OR user override) / total cols."""
    bno_tbl = "user_data.business_name_overrides" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides"
    q = (
        "SELECT COUNT(*) AS total, "
        "COUNT(CASE WHEN (cm.comment IS NOT NULL AND cm.comment != '') "
        "           OR  (bno.definition IS NOT NULL AND bno.definition != '') "
        "           THEN 1 END) AS defined "
        "FROM {0}.{1}.columns_metadata cm "
        "LEFT JOIN {2} bno "
        "  ON cm.table_full_name = bno.table_full_name AND cm.column_name = bno.column_name "
        "WHERE cm.table_full_name = %(fn)s"
    ).format(CATALOG_CACHE, SCHEMA_CACHE, bno_tbl)
    try:
        result = run_query(q, {"fn": table_full_name})
        if result is None or result.empty:
            return 0.0
        total = int(result.iloc[0]["total"] or 0)
        defined = int(result.iloc[0]["defined"] or 0)
        return (defined / total * 100) if total > 0 else 0.0
    except Exception:
        return 0.0


def _render_table_card(row, key_prefix: str, _pref_delete_fn=None, _pref_upsert_fn=None) -> None:
    """Discovery card: table name is clickable, star toggles bookmark."""
    _ts = getattr(row, "updated_at", None)
    _time_str = _ts.strftime(t("discovery.date_format")) if isinstance(_ts, pd.Timestamp) else (str(_ts) if _ts else "")
    _full      = str(getattr(row, "full_name", ""))
    _tname     = str(getattr(row, "table_name", ""))
    _is_bk     = _full in st.session_state.get("bookmarks", set())

    st.markdown(f'''
    <div style="background:var(--paper); border:1px solid var(--ink-10); padding:16px 20px 4px; margin-bottom:4px; border-radius:2px;">
        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px;">
            <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em;">{_html.escape(str(getattr(row, "catalog_name", "")))} · {_html.escape(str(getattr(row, "schema_name", "")))}</div>
            <div style="font-family:var(--font-mono); font-size:11px; color:var(--accent);">{t("discovery.updated")} {_time_str}</div>
        </div>
        <p style="font-family:var(--font-sans); font-size:13px; color:var(--ink-60); line-height:1.5; margin:4px 0 8px;">{_html.escape(str(getattr(row, "table_description", "")))}</p>
    </div>
    ''', unsafe_allow_html=True)

    # Table name button (navigates to detail) + star bookmark — flush below the card
    _c_name, _c_star = st.columns([11, 1], gap="small")
    with _c_name:
        if st.button(f"→ {_tname}", key=f"{key_prefix}_open_{_full}", help=t("search.view_details_help"), use_container_width=True, type="secondary"):
            st.query_params["tab"] = "search"
            st.session_state["dd_search_override"] = _tname
            st.session_state["dd_nav_select"] = _full
            st.rerun()
    with _c_star:
        if st.button("★" if _is_bk else "☆", key=f"{key_prefix}_bk_{_full}", help=t("personalization.remove_bookmark") if _is_bk else t("personalization.add_bookmark"), use_container_width=True):
            if _is_bk:
                st.session_state.get("bookmarks", set()).discard(_full)
                if _pref_delete_fn:
                    _pref_delete_fn(_full, "bookmark")
            else:
                st.session_state.get("bookmarks", set()).add(_full)
                if _pref_upsert_fn:
                    _pref_upsert_fn(_full, "bookmark")
            st.rerun()
    st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)


_POST_COLOR = {
    "announcement":  "var(--accent)",
    "featured_table": "var(--deepblue)",
    "guide":         "var(--forest)",
}


def render_cms_banner() -> None:
    """Render pinned CMS posts above the Discovery sub-tabs."""
    posts = get_active_posts()
    if not posts:
        return

    for post in posts:
        color     = _POST_COLOR.get(post["post_type"], "var(--ink-40)")
        type_key  = f"cms.type_{post['post_type']}"
        lbl       = t(type_key)
        created   = post["created_at"]
        date_str  = created.strftime("%b %d") if hasattr(created, "strftime") else str(created)[:10]
        body_safe = _html.escape(post["body"] or "")
        title_safe = _html.escape(post["title"])
        body_html = (
            f'<div style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);'
            f'margin-top:4px;line-height:var(--lh-body);">{body_safe}</div>'
        ) if body_safe else ""

        card_html = (
            f'<div style="border-left:3px solid {color};padding:12px 16px;'
            f'background:var(--paper-deep);border-radius:0 4px 4px 0;margin-bottom:4px;">'
            f'<span style="font-family:var(--font-mono);font-size:10px;text-transform:uppercase;'
            f'color:{color};letter-spacing:.08em;">{lbl}</span>'
            f'<div style="font-family:var(--font-display);font-size:18px;color:var(--ink);margin-top:2px;">'
            f'{title_safe}</div>'
            f'{body_html}'
            f'<div style="font-family:var(--font-mono);font-size:11px;color:var(--ink-40);margin-top:8px;">'
            f'{_html.escape(post["author_email"])} · {date_str}</div>'
            f'</div>'
        )

        if is_admin():
            _post_col, _del_col = st.columns([11, 1], gap="small")
            with _post_col:
                st.markdown(card_html, unsafe_allow_html=True)
            with _del_col:
                st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
                if st.button("✕", key=f"cms_del_{post['post_id']}", help=t("cms.delete_post"), use_container_width=True):
                    delete_post(post["post_id"])
                    st.rerun()
        else:
            st.markdown(card_html, unsafe_allow_html=True)

        if post["post_type"] == "featured_table" and post.get("table_ref"):
            _tref = post["table_ref"]
            if st.button(f"→ {_tref}", key=f"cms_nav_{post['post_id']}", type="secondary"):
                st.query_params["tab"] = "search"
                st.session_state["dd_search_override"] = _tref.split(".")[-1]
                st.session_state["dd_nav_select"] = _tref
                st.rerun()

    st.markdown("<div style='margin-bottom:16px'></div>", unsafe_allow_html=True)


@st.dialog(t("cms.create_title"), width="large")
def _show_cms_create_dialog():
    type_labels = {
        "announcement":  t("cms.type_announcement"),
        "featured_table": t("cms.type_featured"),
        "guide":         t("cms.type_guide"),
    }
    sel_type = st.radio(
        t("cms.post_type"),
        options=list(type_labels.values()),
        horizontal=True,
        key="cms_create_type",
    )
    post_type = next(k for k, v in type_labels.items() if v == sel_type)

    title = st.text_input(t("cms.post_title"), max_chars=120, key="cms_create_title")
    body  = st.text_area(t("cms.post_body"),  max_chars=500, height=100, key="cms_create_body")

    table_ref = None
    if post_type == "featured_table":
        table_ref = st.text_input(
            t("cms.post_table_ref"),
            placeholder="catalog.schema.table_name",
            key="cms_create_tableref",
        )

    expiry_label = st.selectbox(
        t("cms.post_expiry"),
        options=list(_EXPIRY_DAYS.keys()),
        index=0,
        key="cms_create_expiry",
    )
    expiry_days = _EXPIRY_DAYS[expiry_label]

    _save, _cancel = st.columns([1, 1], gap="small")
    with _save:
        if st.button(t("common.save"), type="primary", use_container_width=True, key="cms_save_btn"):
            if not title.strip():
                st.error(t("cms.error_title_required"))
                return
            if post_type == "featured_table" and not (table_ref or "").strip():
                st.error(t("cms.error_table_ref_required"))
                return
            actor = st.session_state.get("user_email", "admin")
            create_post(post_type, title.strip(), body.strip(), (table_ref or "").strip() or None, actor, expiry_days)
            st.rerun()
    with _cancel:
        if st.button(t("common.cancel"), use_container_width=True, key="cms_cancel_btn"):
            st.rerun()


def _render_admin_cms_section():
    _cms_h, _cms_btn = st.columns([9, 1], gap="small")
    with _cms_h:
        st.markdown(
            f'<div class="dd-section-header" style="margin-top:32px;">'
            f'<span class="dd-eyebrow">§ {t("cms.section_title")}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with _cms_btn:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        if st.button("＋", key="cms_new_post", help=t("cms.new_post"), use_container_width=True):
            _show_cms_create_dialog()

    posts = get_all_posts()
    if not posts:
        st.caption(t("cms.no_posts"))
        return

    type_labels = {
        "announcement":  t("cms.type_announcement"),
        "featured_table": t("cms.type_featured"),
        "guide":         t("cms.type_guide"),
    }

    for post in posts:
        color    = _POST_COLOR.get(post["post_type"], "var(--ink-40)")
        lbl      = type_labels.get(post["post_type"], post["post_type"])
        created  = post["created_at"]
        expires  = post["expires_at"]
        date_str = created.strftime("%b %d, %Y") if hasattr(created, "strftime") else str(created)[:10]
        exp_str  = (
            expires.strftime("%b %d, %Y") if hasattr(expires, "strftime")
            else str(expires)[:10] if expires else t("cms.no_expiry")
        )
        from datetime import datetime
        is_expired = expires is not None and (expires < datetime.utcnow() if hasattr(expires, "utcnow") else False)

        row_html = (
            f'<div style="border-left:3px solid {color};padding:8px 12px;'
            f'background:var(--paper-deep);border-radius:0 4px 4px 0;opacity:{"0.5" if is_expired else "1"};">'
            f'<span style="font-family:var(--font-mono);font-size:10px;text-transform:uppercase;'
            f'color:{color};letter-spacing:.08em;">{lbl}</span>'
            f'<span style="font-family:var(--font-sans);font-size:14px;color:var(--ink);margin-left:10px;">'
            f'{_html.escape(post["title"])}</span>'
            f'<span style="font-family:var(--font-mono);font-size:11px;color:var(--ink-40);margin-left:10px;">'
            f'{date_str} → {t("cms.expires")} {exp_str}</span>'
            f'</div>'
        )

        _row_col, _del_col = st.columns([11, 1], gap="small")
        with _row_col:
            st.markdown(row_html, unsafe_allow_html=True)
        with _del_col:
            st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
            if st.button("✕", key=f"cms_admin_del_{post['post_id']}", help=t("cms.delete_post"), use_container_width=True):
                delete_post(post["post_id"])
                st.rerun()

    st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)


def render_discovery(groups, get_authorized_tables_fn, pref_delete_fn=None, pref_upsert_fn=None):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("discovery.title")}</div>
      <h1>{t("discovery.hero_title")}</h1>
      <p class="lead">{t("discovery.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    render_cms_banner()

    _disc_tab_labels = [
        t("personalization.tab_notable"),
        t("personalization.tab_bookmarks"),
        t("personalization.tab_recent"),
    ]

    # Initialize the key in session state to avoid changing 'default' parameter
    if "discovery_active_tab" not in st.session_state:
        _disc_idx = st.session_state.get("_disc_tab_idx", 0)
        st.session_state["discovery_active_tab"] = _disc_tab_labels[_disc_idx] if 0 <= _disc_idx < len(_disc_tab_labels) else _disc_tab_labels[0]

    _disc_active = st.segmented_control(
        "discovery_tabs",
        options=_disc_tab_labels,
        key="discovery_active_tab",
        label_visibility="collapsed",
        selection_mode="single",
    )

    # Prevent deselecting all tabs (forces at least one to be active)
    if _disc_active is None:
        _disc_active = _disc_tab_labels[st.session_state.get("_disc_tab_idx", 0)]

    # Keep index in sync so the next rerun (e.g. locale switch) restores correctly
    if _disc_active in _disc_tab_labels:
        st.session_state["_disc_tab_idx"] = _disc_tab_labels.index(_disc_active)

    # ── New & Notable ────────────────────────────────────────────────────────────
    if _disc_active == _disc_tab_labels[0]:
        _render_notable_tab(groups, get_authorized_tables_fn, pref_delete_fn, pref_upsert_fn)
    # ── My Bookmarks ─────────────────────────────────────────────────────────────
    elif _disc_active == _disc_tab_labels[1]:
        _render_bookmarks_tab(groups, get_authorized_tables_fn, pref_delete_fn, pref_upsert_fn)
    # ── Recently Viewed ──────────────────────────────────────────────────────────
    elif _disc_active == _disc_tab_labels[2]:
        _render_recent_tab(groups, get_authorized_tables_fn, pref_delete_fn, pref_upsert_fn)


def _render_notable_tab(groups, get_authorized_tables_fn, pref_delete_fn=None, pref_upsert_fn=None):
    st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">{t("personalization.tab_notable")}</span></div>', unsafe_allow_html=True)
    primary_group = st.session_state.get("group_filter")
    if not primary_group and groups:
        primary_group = groups[0]

    if primary_group:
        st.info(t("discovery.group_highlights", group=primary_group))
        try:
            all_authorized = get_authorized_tables_fn((primary_group,))
            if not all_authorized.empty and "updated_at" in all_authorized.columns:
                recent_tables = all_authorized.sort_values(by="updated_at", ascending=False).head(10)
                for _, row in recent_tables.iterrows():
                    _render_table_card(row, "notable", pref_delete_fn, pref_upsert_fn)
            else:
                st.info(t("discovery.no_updates"))
        except Exception as e:
            logging.error("Error in discovery tab: %s", e)
            st.error(t("discovery.load_error"))
    else:
        st.warning(t("discovery.sign_in_prompt"))


def _render_bookmarks_tab(groups, get_authorized_tables_fn, pref_delete_fn=None, pref_upsert_fn=None):
    st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">{t("personalization.tab_bookmarks")}</span></div>', unsafe_allow_html=True)
    bookmarks = st.session_state.get("bookmarks", set())
    if not bookmarks:
        st.info(t("personalization.no_bookmarks"))
    else:
        try:
            all_tables = get_authorized_tables_fn(groups)
            bk_df = all_tables[all_tables["full_name"].isin(bookmarks)]
            if bk_df.empty:
                st.info(t("personalization.no_bookmarks"))
            else:
                for _, row in bk_df.iterrows():
                    _render_table_card(row, "bk", pref_delete_fn, pref_upsert_fn)
        except Exception as e:
            logging.error("Error loading bookmarks: %s", e)
            st.error(t("discovery.load_error"))

    # ── Bookmarked columns ────────────────────────────────────────────────
    col_bookmarks = st.session_state.get("col_bookmarks", set())
    st.markdown(f'<div class="dd-section-header" style="margin-top:32px"><span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">{t("personalization.bookmarked_columns")}</span></div>', unsafe_allow_html=True)
    if not col_bookmarks:
        st.info(t("personalization.no_col_bookmarks"))
    else:
        _col_bk_auth_fns = set(get_authorized_tables_fn(groups)["full_name"].tolist()) if groups else set()
        for _bk_id in sorted(col_bookmarks):
            if "::" not in _bk_id:
                continue
            _bk_table, _bk_col = _bk_id.split("::", 1)
            if _bk_table not in _col_bk_auth_fns:
                continue  # column's parent table no longer authorized — hide silently
            _bk_tbl_parts = _bk_table.split(".")
            _bk_tbl_label = _bk_tbl_parts[-1] if _bk_tbl_parts else _bk_table
            _bk_path = " · ".join(_bk_tbl_parts[:-1]) if len(_bk_tbl_parts) > 1 else ""
            _c_col, _c_star = st.columns([11, 1], gap="small")
            with _c_col:
                st.markdown(
                    f'<div style="background:var(--paper);border:1px solid var(--ink-10);padding:10px 16px;border-radius:2px;margin-bottom:4px;">'
                    f'<div style="font-family:var(--font-mono);font-size:11px;color:var(--ink-40);margin-bottom:4px;">{_html.escape(_bk_path)} · {_html.escape(_bk_tbl_label)}</div>'
                    f'<div style="font-family:var(--font-mono);font-size:14px;color:var(--ink);">{_html.escape(_bk_col)}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button(f"→ {_bk_tbl_label}", key=f"colbk_open_{_bk_id}", use_container_width=True, type="secondary"):
                    st.query_params["tab"] = "search"
                    st.session_state["dd_search_override"] = _bk_tbl_label
                    st.session_state["dd_nav_select"] = _bk_table
                    st.rerun()
            with _c_star:
                if st.button("★", key=f"colbk_rm_{_bk_id}", help=t("personalization.remove_bookmark"), use_container_width=True):
                    st.session_state.col_bookmarks.discard(_bk_id)
                    if pref_delete_fn:
                        pref_delete_fn(_bk_id, "col_bookmark")
                    st.rerun()


def _render_recent_tab(groups, get_authorized_tables_fn, pref_delete_fn=None, pref_upsert_fn=None):
    st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">{t("personalization.tab_recent")}</span></div>', unsafe_allow_html=True)
    recent_views = st.session_state.get("recent_views", [])
    if not recent_views:
        st.info(t("personalization.no_recent"))
    else:
        try:
            all_tables = get_authorized_tables_fn(groups)
            # Preserve recency order
            rv_df = all_tables[all_tables["full_name"].isin(recent_views)].copy()
            rv_df["_order"] = rv_df["full_name"].map({fn: i for i, fn in enumerate(recent_views)})
            rv_df = rv_df.sort_values("_order").drop(columns=["_order"])
            if rv_df.empty:
                st.info(t("personalization.no_recent"))
            else:
                for _, row in rv_df.iterrows():
                    _render_table_card(row, "rv", pref_delete_fn, pref_upsert_fn)
        except Exception as e:
            logging.error("Error loading recent views: %s", e)
            st.error(t("discovery.load_error"))

def _calculate_health_metrics(all_data):
    n_tables = len(all_data)
    n_desc = (all_data['table_description'].str.strip().str.len() > 0).sum()
    table_coverage = (n_desc / n_tables * 100) if n_tables > 0 else 0

    if is_demo_mode():
        n_cols = 0
        n_col_desc = 0
    else:
        cols_stats_query = f"SELECT count(*) as total, count(comment) as with_desc FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata"
        stats = run_query(cols_stats_query)
        n_cols = stats.iloc[0]['total']
        n_col_desc = stats.iloc[0]['with_desc']

    col_coverage = (n_col_desc / n_cols * 100) if n_cols > 0 else 0
    return table_coverage, n_desc, n_tables, col_coverage, n_col_desc, n_cols

def _render_health_hero_metrics(table_coverage, n_desc, n_tables, col_coverage, n_col_desc, n_cols):
    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        st.markdown(f'''
        <div style="background:var(--paper); border-top:3px solid var(--accent); padding:24px; border-radius:2px; box-shadow:0 2px 4px rgba(0,0,0,0.05);">
            <div style="font-family:var(--font-sans); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;">{t("health.table_coverage")}</div>
            <div style="font-family:var(--font-display); font-size:48px; color:var(--ink);">{table_coverage:.0f}%</div>
            <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-60); margin-top:8px;">{t("health.tables_described", n_desc=n_desc, n_tables=n_tables)}</div>
        </div>
        ''', unsafe_allow_html=True)
    with c2:
        st.markdown(f'''
        <div style="background:var(--paper); border-top:3px solid var(--deepblue); padding:24px; border-radius:2px; box-shadow:0 2px 4px rgba(0,0,0,0.05);">
            <div style="font-family:var(--font-sans); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;">{t("health.column_coverage")}</div>
            <div style="font-family:var(--font-display); font-size:48px; color:var(--ink);">{col_coverage:.0f}%</div>
            <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-60); margin-top:8px;">{t("health.columns_defined", n_col_desc=n_col_desc, n_cols=n_cols)}</div>
        </div>
        ''', unsafe_allow_html=True)
    with c3:
        st.markdown(f'''
        <div style="background:var(--paper); border-top:3px solid var(--ochre); padding:24px; border-radius:2px; box-shadow:0 2px 4px rgba(0,0,0,0.05);">
            <div style="font-family:var(--font-sans); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;">{t("health.freshness_index")}</div>
            <div style="font-family:var(--font-display); font-size:48px; color:var(--ink);">A</div>
            <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-60); margin-top:8px;">{t("health.last_sync")}</div>
        </div>
        ''', unsafe_allow_html=True)

def _render_schema_coverage(all_data):
    st.markdown('<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0">§ Coverage by Schema</span></div>', unsafe_allow_html=True)
    schema_stats = all_data.groupby('schema_name').agg(
        total=('table_name', 'count'),
        described=('table_description', lambda x: x.apply(lambda y: len(str(y).strip()) > 0).sum())
    ).reset_index()
    schema_stats['coverage'] = (schema_stats['described'] / schema_stats['total'] * 100).round(0)

    st.dataframe(
        schema_stats.sort_values(by='coverage', ascending=False),
        column_config={
            "schema_name": "Schema",
            "total": "Tables",
            "described": "With Desc",
            "coverage": st.column_config.ProgressColumn("Coverage", format="%d%%", min_value=0, max_value=100)
        },
        use_container_width=True,
        hide_index=True
    )

def _render_priority_actions(all_data):
    st.markdown('<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0">§ Priority Actions</span></div>', unsafe_allow_html=True)
    undocumented = all_data[all_data['table_description'].apply(lambda x: len(str(x).strip()) == 0)].head(5)

    if not undocumented.empty:
        st.warning(t("health.missing_descriptions"))
        for _, row in undocumented.iterrows():
            if st.button(f"📄 {row['table_name']}", key=f"health_fix_{row['full_name']}", use_container_width=True):
                st.query_params["tab"] = "search"
                st.session_state["dd_search_override"] = row["table_name"]
                st.session_state["dd_nav_select"] = row["full_name"]
                st.rerun()
    else:
        st.success(t("health.all_documented"))


def render_health(groups, get_authorized_tables_fn):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("health.title")}</div>
      <h1>{t("health.hero_title")}</h1>
      <p class="lead">{t("health.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    try:
        all_data = get_authorized_tables_fn(groups)
        if all_data.empty:
            st.info(t("health.no_data"))
            return

        table_coverage, n_desc, n_tables, col_coverage, n_col_desc, n_cols = _calculate_health_metrics(all_data)

        _render_health_hero_metrics(table_coverage, n_desc, n_tables, col_coverage, n_col_desc, n_cols)

        st.markdown('<div style="margin-top:48px;"></div>', unsafe_allow_html=True)

        col_left, col_right = st.columns([6, 4], gap="large")

        with col_left:
            _render_schema_coverage(all_data)

        with col_right:
            _render_priority_actions(all_data)

    except Exception as e:
        logging.error("Error in health dashboard: %s", e)
        st.error(t("health.load_error"))



# ── Admin page ─────────────────────────────────────────────────────────────────

def get_admin_stats() -> dict:
    """Return four catalog-wide counts for the admin dashboard."""
    if is_demo_mode():
        # Demo data lives in app.py until Phase 4b — return session-state counts only
        return {
            "tables":    0,
            "columns":   0,
            "comments":  sum(len(v) for v in st.session_state.get("demo_comments", {}).values()),
            "overrides": sum(len(v) for v in st.session_state.get("demo_business_names", {}).values()),
        }
    try:
        _ud = _duckdb_available()
        comments_tbl  = "user_data.comments"                if _ud else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.comments"
        overrides_tbl = "user_data.business_name_overrides" if _ud else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides"
        tables_tbl    = f"{CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata"
        columns_tbl   = f"{CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata"
        tables_cnt    = run_query(f"SELECT COUNT(*) AS c FROM {tables_tbl}").iloc[0]["c"]
        columns_cnt   = run_query(f"SELECT COUNT(*) AS c FROM {columns_tbl}").iloc[0]["c"]
        comments_cnt  = run_query(f"SELECT COUNT(*) AS c FROM {comments_tbl}").iloc[0]["c"]
        overrides_cnt = run_query(f"SELECT COUNT(*) AS c FROM {overrides_tbl}").iloc[0]["c"]
        return {"tables": tables_cnt, "columns": columns_cnt, "comments": comments_cnt, "overrides": overrides_cnt}
    except Exception as e:
        logging.warning("Failed to fetch admin stats: %s", e)
        return {"tables": 0, "columns": 0, "comments": 0, "overrides": 0}


def get_business_name_change_log() -> pd.DataFrame:
    """Return the last 200 business name change events for the admin log."""
    if is_demo_mode():
        logs = [log for log in st.session_state.get("demo_audit_log", []) if log["event_type"] == "business_name_change"]
        if not logs:
            return pd.DataFrame(columns=["event_id", "object_name", "old_value", "new_value", "actor_email", "created_at"])
        return pd.DataFrame(logs).sort_values("created_at", ascending=False).head(200)
    audit_tbl = "user_data.audit_log" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log"
    return run_query(
        f"SELECT event_id, object_name, old_value, new_value, actor_email, created_at "
        f"FROM {audit_tbl} "
        f"WHERE event_type = 'business_name_change' "
        f"ORDER BY created_at DESC LIMIT 200"
    )


def get_comment_log() -> pd.DataFrame:
    """Return the last 200 comment/reply events for the admin log."""
    if is_demo_mode():
        logs = [log for log in st.session_state.get("demo_audit_log", [])
                if log["event_type"] in ("comment_added", "comment_reply")]
        if not logs:
            return pd.DataFrame(columns=["event_id", "object_name", "comment_preview", "actor_email", "created_at"])
        df = pd.DataFrame(logs).rename(columns={"new_value": "comment_preview"})
        return df.sort_values("created_at", ascending=False).head(200)
    audit_tbl = "user_data.audit_log" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log"
    return run_query(
        f"SELECT event_id, object_name, new_value AS comment_preview, actor_email, created_at "
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
            # Ensure all statuses are present
            for s in ("pending", "processing", "done", "failed"):
                stats.setdefault(s, 0)
            return stats
    except Exception:
        return {"pending": 0, "processing": 0, "done": 0, "failed": 0}


@st.dialog(t("admin.biz_log_title"), width="large")
def _show_biz_log_dialog():
    from src.ui.css import VIS_WIDE_CSS
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
    from src.ui.css import VIS_WIDE_CSS
    st.markdown(VIS_WIDE_CSS, unsafe_allow_html=True)
    comment_log = get_comment_log()
    st.dataframe(
        comment_log,
        column_config={
            "object_name":      st.column_config.TextColumn("Object"),
            "comment_preview":  st.column_config.TextColumn("Comment preview"),
            "actor_email":      st.column_config.TextColumn("Author"),
            "created_at":       st.column_config.TextColumn("Posted at"),
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
    # --- § Synchronization status ---
    st.markdown(f'<div class="dd-section-header" style="margin-top:32px;"><span class="dd-eyebrow">§ {t("admin.sync_title")}</span></div>', unsafe_allow_html=True)

    sync_stats = get_sync_queue_stats()
    total_jobs = sum(sync_stats.values())
    done_jobs = sync_stats.get("done", 0)
    pct_complete = (done_jobs / total_jobs * 100) if total_jobs > 0 else 100.0

    sc1, sc2 = st.columns([7, 3], gap="large")
    with sc1:
        st.progress(pct_complete / 100.0, text=f"{pct_complete:.1f}% synced with Databricks")

        # Detailed breakdown
        bc1, bc2, bc3, bc4 = st.columns(4)
        bc1.caption(f"Pending: {sync_stats.get('pending', 0)}")
        bc2.caption(f"Processing: {sync_stats.get('processing', 0)}")
        bc3.caption(f"Done: {sync_stats.get('done', 0)}")
        bc4.caption(f"Failed: {sync_stats.get('failed', 0)}")

    with sc2:
        # Current Mode & DR Status
        is_idle = (time.time() - _get_last_ui_activity()) > 300
        mode_label = "Idle (High Throughput)" if is_idle else "Active (Low Impact)"
        mode_color = "var(--deepblue)" if is_idle else "var(--accent-ink)" # Deep blue vs Accent red

        st.markdown(
            f'<div style="background:var(--paper-deep); padding:12px; border-radius:4px; border-left:4px solid {mode_color};">'
            f'<div style="font-family:var(--font-mono); font-size:10px; color:var(--ink-40); text-transform:uppercase;">Sync Mode</div>'
            f'<div style="font-family:var(--font-sans); font-size:14px; font-weight:600; color:var(--ink);">{mode_label}</div>'
            f'<div style="margin-top:12px; font-family:var(--font-mono); font-size:10px; color:var(--ink-40); text-transform:uppercase;">Self-Healing (DR)</div>'
            f'<div style="font-family:var(--font-sans); font-size:13px; color:var(--ink-60);">{_get_dr_resync_status()}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown('<div style="margin-top:32px;"></div>', unsafe_allow_html=True)

def _render_admin_biz_log_section():
    # --- § Business name change log ---
    _biz_h, _biz_btn = st.columns([9, 1], gap="small")
    with _biz_h:
        st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow">§ {t("admin.biz_log_title")}</span></div>', unsafe_allow_html=True)
    with _biz_btn:
        if st.button("⤢", key="admin_biz_log_expand", help=t("admin.expand_log"), use_container_width=True):
            _show_biz_log_dialog()

    st.markdown('<div style="margin-top:24px;"></div>', unsafe_allow_html=True)

def _render_admin_comment_log_section():
    # --- § Comment log ---
    _cmt_h, _cmt_btn = st.columns([9, 1], gap="small")
    with _cmt_h:
        st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow">§ {t("admin.comment_log_title")}</span></div>', unsafe_allow_html=True)
    with _cmt_btn:
        if st.button("⤢", key="admin_comment_log_expand", help=t("admin.expand_log"), use_container_width=True):
            _show_comment_log_dialog()


def _render_admin_editing_section():
    st.markdown(
        f'<div class="dd-section-header" style="margin-top:32px;">'
        f'<span class="dd-eyebrow">§ {t("admin.editing_title")}</span>'
        f'</div>',
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
        f'<p style="font-family:var(--font-mono); font-size:11px; color:{status_color}; margin-top:4px;">'
        f'{status_label}</p>',
        unsafe_allow_html=True,
    )


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
    _render_admin_sync_section()
    _render_admin_biz_log_section()
    _render_admin_comment_log_section()


# ── Global State for Background Workers ──────────────────────────────────────
_worker_state_lock = threading.Lock()
_LAST_UI_ACTIVITY = time.time()
_DR_RESYNC_STATUS = "Idle" # Idle, Checking, Syncing, Up-to-date, Error
_DR_RESYNC_PROGRESS = 0.0

def _get_last_ui_activity():
    with _worker_state_lock:
        return _LAST_UI_ACTIVITY

def _get_dr_resync_status():
    with _worker_state_lock:
        return _DR_RESYNC_STATUS

def _set_dr_resync_status(status):
    global _DR_RESYNC_STATUS
    with _worker_state_lock:
        _DR_RESYNC_STATUS = status

def _set_dr_resync_progress(progress):
    global _DR_RESYNC_PROGRESS
    with _worker_state_lock:
        _DR_RESYNC_PROGRESS = progress

def _mark_ui_activity():
    global _LAST_UI_ACTIVITY
    with _worker_state_lock:
        _LAST_UI_ACTIVITY = time.time()


def _get_max_local_timestamp(conn, tbl: str, ts_col: str):
    """Fetch the max timestamp for a table locally."""
    with conn.cursor() as cursor:
        cursor.execute(f"SELECT MAX({ts_col}) FROM user_data.{tbl}")
        return cursor.fetchall()[0][0]

def _fetch_remote_delta(tbl: str, ts_col: str, local_max):
    """Query Databricks for any records AFTER local_max."""
    remote_q = f"SELECT * FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.{tbl}"
    params = {}
    if local_max:
        remote_q += f" WHERE {ts_col} > %(local_max)s"
        params["local_max"] = local_max
    return run_query(remote_q, params)

def _merge_delta_into_local(conn, tbl: str, delta_df: pd.DataFrame):
    """Merge delta DataFrame records into DuckDB."""
    with conn.cursor() as cursor:
        for row_dict in delta_df.to_dict("records"):
            # Simple append for logs/comments (guaranteed unique IDs)
            if tbl in ("comments", "audit_log"):
                cols = ", ".join(delta_df.columns)
                placeholders = ", ".join([f"%({c})s" for c in delta_df.columns])
                cursor.execute_write(
                    f"INSERT OR IGNORE INTO user_data.{tbl} ({cols}) VALUES ({placeholders})",
                    row_dict
                )
            else:
                # Merge for overrides
                cursor.execute_write(
                    f"INSERT OR REPLACE INTO user_data.{tbl} ({', '.join(delta_df.columns)}) "
                    f"VALUES ({', '.join([f'%({c})s' for c in delta_df.columns])})",
                    row_dict
                )


def _run_dr_resync():
    """Background task to pull missing records from Databricks to DuckDB."""
    if not _duckdb_available():
        return

    _set_dr_resync_status("Checking")
    try:
        conn = _get_write_connection()
        # 1. Check for newest records in Databricks vs Local
        # We check comments, audit_log, and overrides
        tables_to_check = [
            ("comments", "created_at", "comment_id"),
            ("audit_log", "created_at", "event_id"),
            ("business_name_overrides", "edited_at", "table_full_name, column_name")
        ]

        # Get all max local timestamps in a single query
        with conn.cursor() as cursor:
            union_query = " UNION ALL ".join(
                [f"SELECT '{tbl}' as tbl, MAX({ts_col}) as max_ts FROM user_data.{tbl}" for tbl, ts_col, _ in tables_to_check]
            )
            cursor.execute(union_query)
            max_ts_results = cursor.fetchall()
            max_ts_map = {row[0]: row[1] for row in max_ts_results}

        for tbl, ts_col, pk in tables_to_check:
            local_max = max_ts_map.get(tbl)
            delta_df = _fetch_remote_delta(tbl, ts_col, local_max)

            if delta_df is not None and not delta_df.empty:
                _set_dr_resync_status(f"Syncing {tbl}")
                _merge_delta_into_local(conn, tbl, delta_df)

        _set_dr_resync_status("Up-to-date")
        _set_dr_resync_progress(100.0)
    except Exception as e:
        logging.error("DR Resync failed: %s", e)
        _set_dr_resync_status(f"Error: {str(e)[:50]}")



@st.dialog(t("detail.edit_table"), width="large")
def render_table_metadata_editor(table_full_name: str, current_desc: str, current_steward: str):
    """Editor for table-level metadata (description, steward)."""
    st.markdown(f"**{table_full_name}**")

    new_desc = st.text_area(t("detail.table_description"), value=current_desc, height=150)
    new_stew = st.text_input(t("detail.steward_email"), value=current_steward, placeholder="e.g. data.steward@example.com")

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button(t("common.save"), type="primary", use_container_width=True):
            if new_stew.strip() and "@" not in new_stew:
                st.error(t("detail.invalid_email"))
            else:
                try:
                    save_table_metadata(table_full_name, description=new_desc, steward_email=new_stew)
                    st.success(t("common.saved"))
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(t("common.error_with_details", error=str(e)))
    with c2:
        if st.button(t("common.cancel"), use_container_width=True):
            st.rerun()


@st.dialog(t("detail.data_sample"), width="large")
def render_data_sample(table_full_name: str):
    import logging
    st.markdown(VIS_WIDE_CSS, unsafe_allow_html=True)
    st.markdown(f"**{table_full_name}**")

    # Security: check permission even though UI usually prevents this call
    groups = tuple(st.session_state.get("user_groups", [])) if st.session_state.get("user_groups") else ("none",)
    active_group = st.session_state.get("group_filter")
    query_groups = (active_group,) if active_group else groups
    _auth_df = get_authorized_tables(query_groups)
    _allowed = set(_auth_df["full_name"].tolist()) if _auth_df is not None and not _auth_df.empty else set()
    if table_full_name not in _allowed:
        st.error(t("detail.unauthorized"))
        return

    try:
        # Validate Unity Catalog 3-level namespace format (catalog.schema.table) to prevent SQL injection
        if not re.match(r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$", table_full_name):
            st.error(t("common.error"))
            return
        if is_demo_mode():
            df = pd.DataFrame({"id": [1, 2, 3], "status": ["NEW", "SHIPPED", "CLOSED"]})
        elif _duckdb_available():
            _parts = table_full_name.split(".")
            if len(_parts) == 3:
                _, _sch, _tbl = _parts
                _sample_query = f'SELECT * FROM {CATALOG_CACHE}."{_sch}"."{_tbl}" LIMIT 100'  # nosec B608
                df = run_query(_sample_query)
            else:
                st.info(t("detail.preview_not_available"))
                return
        else:
            query = f"SELECT * FROM {table_full_name} LIMIT 100"  # nosec B608
            df = run_query(query)
        if df is not None and not df.empty:
            st.dataframe(df, use_container_width=True, height=2000)
        else:
            st.info(t("detail.preview_needs_data"))
    except Exception as e:
        logging.error("Error fetching data sample for %s: %s", table_full_name, e, exc_info=True)
        st.error(t("detail.preview_error"))


# ── Pipelines ─────────────────────────────────────────────────────────────────

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
                              "INTERNAL_ERROR", "TIMEDOUT", "CANCELED", "Cancelled", "canceled"})


def _pipeline_status_color(status: str) -> str:
    if status in _STATUS_SUCCESS:
        return "var(--forest)"
    if status in _STATUS_FAILED:
        return "var(--accent)"
    return "var(--ochre)"


@st.dialog(t("pipelines.create_title"), width="large")
def _show_pipeline_create_dialog():
    backend_opts = [_BACKEND_LABEL[b] for b in BACKENDS]
    sel_label = st.radio(t("pipelines.backend"), options=backend_opts, horizontal=True, key="pl_create_backend")
    backend = next(b for b in BACKENDS if _BACKEND_LABEL[b] == sel_label)

    title = st.text_input(t("pipelines.field_title"), max_chars=120, key="pl_create_title")
    desc  = st.text_area(t("pipelines.field_desc"),  max_chars=300, height=80, key="pl_create_desc")

    db_job_id = adf_sub = adf_rg = adf_fact = adf_pipe = ado_org = ado_proj = ado_pid = None
    if backend == "databricks":
        db_job_id = st.text_input(t("pipelines.field_job_id"), placeholder="1234", key="pl_db_job")
    elif backend == "adf":
        adf_sub  = st.text_input(t("pipelines.field_adf_sub"),  key="pl_adf_sub")
        adf_rg   = st.text_input(t("pipelines.field_adf_rg"),   key="pl_adf_rg")
        adf_fact = st.text_input(t("pipelines.field_adf_fact"),  key="pl_adf_fact")
        adf_pipe = st.text_input(t("pipelines.field_adf_pipe"),  key="pl_adf_pipe")
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
            if st.button("✕", key=f"pl_del_{pl['pipeline_id']}", help=t("pipelines.delete"), use_container_width=True):
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
            # Card header
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
                # Poll the live status
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
                        type="primary", use_container_width=True,
                    ):
                        try:
                            cancel_run(pl, run)
                            st.success(t("pipelines.stopped"))
                        except Exception as _e:
                            st.error(f"{t('pipelines.stop_error')}: {_e}")
                        st.rerun()

            else:
                # No active run — show Start button
                if st.button(
                    t("pipelines.start"), key=f"pl_start_{pid}",
                    type="secondary", use_container_width=False,
                ):
                    try:
                        trigger_pipeline(pl, actor)
                        st.rerun()
                    except Exception as _e:
                        st.error(f"{t('pipelines.start_error')}: {_e}")

            st.markdown("<div style='margin-bottom:16px'></div>", unsafe_allow_html=True)

    # Auto-poll every 3 s while any run is active
    if _any_active:
        import time
        time.sleep(3)
        st.rerun()
