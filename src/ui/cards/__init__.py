from __future__ import annotations

import html as _html
import logging
import re
import time

import pandas as pd
import streamlit as st

from src.audit import save_table_metadata
from src.auth import is_admin, is_pipeline_user
from src.cms import _EXPIRY_DAYS, create_post, delete_post, get_active_posts, get_all_posts
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

# Shared helpers — keep the public symbols here so callers don't have to
# update their imports during the cards/ split. See src/ui/cards/_shared.py
# for the implementations.
from src.ui.cards._shared import (  # noqa: F401  re-exports
    _DQ_GRADES,
    _dq_grade,
    _compute_live_completeness,
    _POST_COLOR,
)


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
                for row in recent_tables.itertuples(index=False):
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
                for row in bk_df.itertuples(index=False):
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
                for row in rv_df.itertuples(index=False):
                    _render_table_card(row, "rv", pref_delete_fn, pref_upsert_fn)
        except Exception as e:
            logging.error("Error loading recent views: %s", e)
            st.error(t("discovery.load_error"))

from src.ui.cards.health import render_health  # noqa: F401  re-export



# ── Admin page ─────────────────────────────────────────────────────────────────

from src.ui.cards.admin import (  # noqa: F401  re-exports
    get_admin_stats,
    get_business_name_change_log,
    get_comment_log,
    get_sync_queue_stats,
    render_admin_page,
)


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


from src.ui.cards.pipelines import (  # noqa: F401  re-exports
    _render_admin_pipelines_section,
    _show_pipeline_create_dialog,
    render_pipelines_page,
)
