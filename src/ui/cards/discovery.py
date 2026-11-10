"""Discovery tab — read-only views over authorized tables.

Three sub-tabs (notable / bookmarks / recent) plus a CMS-banner that pins
admin-authored posts above them. ``_render_table_card`` is the row card
shared across all three sub-tabs.

The banner is read-only for non-admin users; admins also see a delete
button next to each post (the actual create dialog lives in
``cards/admin.py``).
"""
from __future__ import annotations


import html as _html
import logging

import pandas as pd
import streamlit as st

from src.auth import is_admin
from src.cms import get_active_posts
from src.ui.cards.cms_admin import _show_delete_cms_dialog
from src.config import is_demo_mode
from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import run_query, get_authorized_tables, get_authorized_table_names
from src.i18n import t
from src.notifications import get_unread_notifications, mark_all_read, mark_read
from src.ui.cards._shared import _POST_COLOR, _dq_grade, _render_empty_state, _render_info_state
from src.personalization import _pref_delete, _pref_upsert


def _render_dq_badge(dq_score: str, dq_status: str) -> str:
    """Render the data quality badge HTML if a score is present."""
    if not dq_score:
        return ""
    _grade, _gcls = _dq_grade(dq_score)
    _status_color = (
        "var(--accent)"  if dq_status.lower() == "fail"
        else "#2D6A4F"   if dq_status.lower() == "pass"
        else "var(--ink-40)"
    )
    return (
        f'<span class="dd-dq-badge {_gcls}" title="{_html.escape(t("discovery.data_quality_grade", grade=_grade))}">{_grade}</span>'
        f'<span style="font-family:var(--font-mono);font-size:10px;color:{_status_color};'
        f'margin-left:4px;">{_html.escape(dq_status)}</span>'
    )


def _render_navigation_button(table_name: str, full_name: str, key_prefix: str) -> None:
    """Render the navigation button to jump to table search details."""
    if st.button(
        t("discovery.explore_button", name=table_name),
        key=f"{key_prefix}_open_{full_name}",
        help=t("search.view_details_help"),
        use_container_width=True, type="secondary",
    ):
        st.query_params["tab"] = "search"
        st.session_state["dd_search_override"] = table_name
        st.session_state["dd_nav_select"] = full_name
        st.rerun()


def _render_bookmark_button(is_bk: bool, full_name: str, key_prefix: str) -> None:
    """Render the bookmark toggle star button and handle state updates."""
    label = "★" if is_bk else "☆"
    help_text = (
        t("personalization.remove_bookmark") if is_bk
        else t("personalization.add_bookmark")
    )
    if st.button(label, key=f"{key_prefix}_bk_{full_name}", help=help_text, use_container_width=True):
        if is_bk:
            st.session_state.get("bookmarks", set()).discard(full_name)
            _pref_delete(full_name, "bookmark")
            st.toast(t("personalization.bookmark_removed"))
        else:
            st.session_state.get("bookmarks", set()).add(full_name)
            _pref_upsert(full_name, "bookmark")
            st.toast(t("personalization.bookmark_added"))
        st.rerun()


def _render_table_card(row: dict, key_prefix: str) -> None:
    """Discovery card: table name is clickable, star toggles bookmark."""
    from src.i18n import format_date
    _ts = row.get("updated_at")
    _time_str = format_date(_ts)
    _full  = str(row.get("full_name", ""))
    _tname = str(row.get("table_name", ""))
    _is_bk = _full in st.session_state.get("bookmarks", set())

    _dq_score  = str(row.get("dq_score", "") or "")
    _dq_status = str(row.get("dq_status", "") or "")
    _dq_html = _render_dq_badge(_dq_score, _dq_status)

    st.markdown(f'''
    <div style="background:var(--paper); border:1px solid var(--ink-10); padding:16px 20px 4px; margin-bottom:4px; border-radius:2px;">
        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px;">
            <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em;">{_html.escape(str(row.get("catalog_name", "")))} · {_html.escape(str(row.get("schema_name", "")))}</div>
            <div style="display:flex;align-items:center;gap:6px;">
                {_dq_html}
                <span style="font-family:var(--font-mono); font-size:11px; color:var(--accent);">{_html.escape(t("discovery.updated_at", time=_time_str))}</span>
            </div>
        </div>
        <p style="font-family:var(--font-sans); font-size:13px; color:var(--ink-60); line-height:1.5; margin:4px 0 8px;">{_html.escape(str(row.get("table_description", "")))}</p>
    </div>
    ''', unsafe_allow_html=True)

    _c_name, _c_star = st.columns([11, 1], gap="small")
    with _c_name:
        _render_navigation_button(_tname, _full, key_prefix)
    with _c_star:
        _render_bookmark_button(_is_bk, _full, key_prefix)
    st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)


def render_notification_strip() -> None:
    """Render unread bookmark-change notifications for the current user.

    Shown as a collapsible strip above the CMS banner. Each item has a
    dismiss button; a "Mark all read" shortcut clears the list in one click.
    """
    user_oid = (
        st.session_state.get("user_oid")
        or st.session_state.get("user_email")
        or "anonymous"
    )
    if user_oid == "anonymous":
        return

    notifications = get_unread_notifications(user_oid)
    if not notifications:
        return

    count = len(notifications)
    label = t("notifications.strip_label", count=count)

    with st.expander(f"🔔 {label}", expanded=True):
        for n in notifications:
            tbl = _html.escape(n["table_full_name"])
            summary = _html.escape(n["summary"])
            by = _html.escape(n.get("changed_by") or "")
            by_str = t("discovery.by_user", user=by) if by else ""
            card_html = (
                f'<div style="font-family:var(--font-sans);font-size:13px;'
                f'color:var(--ink);padding:6px 0;border-bottom:1px solid var(--ink-10);">'
                f'<span style="font-family:var(--font-mono);color:var(--ink-60);">{tbl}</span>'
                f' — {summary}'
                f'<span style="color:var(--ink-40);font-size:11px;">{by_str}</span>'
                f'</div>'
            )
            col_card, col_btn = st.columns([11, 1], gap="small")
            with col_card:
                st.markdown(card_html, unsafe_allow_html=True)
            with col_btn:
                if st.button(
                    "✕",
                    key=f"notif_dismiss_{n['notification_id']}",
                    help=t("notifications.dismiss"),
                    use_container_width=True,
                ):
                    with st.spinner(t("common.loading")):
                        mark_read(n["notification_id"])
                    st.toast(t("notifications.dismissed_toast"))
                    st.rerun()

        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        if st.button(t("notifications.mark_all_read"), key="notif_mark_all"):
            with st.spinner(t("common.loading")):
                mark_all_read(user_oid)
            st.toast(t("notifications.all_read_toast"))
            st.rerun()


def render_cms_banner() -> None:
    """Render pinned CMS posts above the Discovery sub-tabs."""
    posts = get_active_posts()
    if not posts:
        return

    for post in posts:
        color      = _POST_COLOR.get(post["post_type"], "var(--ink-40)")
        type_key   = f"cms.type_{post['post_type']}"
        from src.i18n import format_date
        lbl        = t(type_key)
        created    = post["created_at"]
        date_str   = format_date(created, format_type="short")
        body_safe  = _html.escape(post["body"] or "")
        title_safe = _html.escape(post["title"])
        body_html = (
            f'<div style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);'
            f'margin-top:4px;line-height:var(--lh-body);">{body_safe}</div>'
        ) if body_safe else ""

        author_date = _html.escape(t("cms.author_date", author=post["author_email"], date=date_str))
        card_html = (
            f'<div style="border-left:3px solid {color};padding:12px 16px;'
            f'background:var(--paper-deep);border-radius:0 4px 4px 0;margin-bottom:4px;">'
            f'<span style="font-family:var(--font-mono);font-size:10px;text-transform:uppercase;'
            f'color:{color};letter-spacing:.08em;">{_html.escape(lbl)}</span>'
            f'<div style="font-family:var(--font-display);font-size:18px;color:var(--ink);'
            f'margin-top:2px;">{title_safe}</div>'
            f'{body_html}'
            f'<div style="font-family:var(--font-mono);font-size:11px;color:var(--ink-40);'
            f'margin-top:8px;">{author_date}</div>'
            f'</div>'
        )

        if is_admin():
            _post_col, _del_col = st.columns([11, 1], gap="small")
            with _post_col:
                st.markdown(card_html, unsafe_allow_html=True)
            with _del_col:
                st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
                if st.button(
                    "✕", key=f"cms_del_{post['post_id']}",
                    help=t("cms.delete_post"), use_container_width=True,
                ):
                    _show_delete_cms_dialog(post["post_id"])
        else:
            st.markdown(card_html, unsafe_allow_html=True)

        if post["post_type"] == "featured_table" and post.get("table_ref"):
            _tref = post["table_ref"]
            if st.button(t("discovery.explore_button", name=_tref), key=f"cms_nav_{post['post_id']}", help=t("search.view_details_help"), type="secondary"):
                st.query_params["tab"] = "search"
                st.session_state["dd_search_override"] = _tref.split(".")[-1]
                st.session_state["dd_nav_select"] = _tref
                st.rerun()

    st.markdown("<div style='margin-bottom:16px'></div>", unsafe_allow_html=True)


def render_discovery(groups):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("discovery.title")}</div>
      <h1>{t("discovery.hero_title")}</h1>
      <p class="lead">{t("discovery.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    render_notification_strip()
    render_cms_banner()

    with st.expander(t("help.discovery_expander")):
        st.markdown(t("help.discovery_content"))

    # Decouple internal tab identifiers from localized labels.
    _disc_tabs = ["notable", "bookmarks", "recent", "recommended"]
    _disc_tab_labels = {
        "notable": t("personalization.tab_notable"),
        "bookmarks": t("personalization.tab_bookmarks"),
        "recent": t("personalization.tab_recent"),
        "recommended": t("personalization.tab_recommended"),
    }

    if st.session_state.get("discovery_active_tab") not in _disc_tabs:
        st.session_state["discovery_active_tab"] = _disc_tabs[0]

    _disc_active = st.segmented_control(
        "discovery_tabs",
        options=_disc_tabs,
        format_func=lambda x: _disc_tab_labels[x[0]] if isinstance(x, list) and len(x) > 0 else _disc_tab_labels.get(x, "") if not isinstance(x, list) else "",
        key="discovery_active_tab",
        label_visibility="collapsed",
        selection_mode="single",
    )

    # Prevent deselecting all tabs (forces at least one to be active).
    if _disc_active is None:
        _disc_active = "notable"

    if _disc_active == "notable":
        _render_notable_tab(groups)
    elif _disc_active == "bookmarks":
        _render_bookmarks_tab(groups)
    elif _disc_active == "recent":
        _render_recent_tab(groups)
    elif _disc_active == "recommended":
        _render_recommended_tab(groups)


def _render_notable_tab(groups):
    st.markdown(
        f'<div class="dd-section-header"><span class="dd-eyebrow" '
        f'style="margin-bottom:0;color:#14110C">{t("personalization.tab_notable")}</span></div>',
        unsafe_allow_html=True,
    )
    primary_group = st.session_state.get("group_filter")
    if not primary_group and groups:
        primary_group = groups[0]

    # "none" is the sentinel app.py uses when user_groups is empty
    if not primary_group or primary_group == "none":
        _render_empty_state("👥", t("discovery.no_groups"))
        return

    if primary_group:
        _render_info_state("ℹ️", t("discovery.group_highlights", group=primary_group))
        try:
            all_authorized = get_authorized_tables((primary_group,))
            if not all_authorized.empty and "updated_at" in all_authorized.columns:
                recent_tables = all_authorized.sort_values(by="updated_at", ascending=False).head(10)
                # ⚡ Bolt: Replace slow itertuples() and getattr() with fast native dictionary iteration
                for row_dict in recent_tables.to_dict("records"):
                    _render_table_card(row_dict, "notable")
            else:
                _render_empty_state("✨", t("discovery.no_updates"))
        except Exception as e:
            logging.error("Error in discovery tab: %s", e)
            st.error(t("discovery.load_error"))


def _render_bookmarks_tab(groups):
    st.markdown(
        f'<div class="dd-section-header"><span class="dd-eyebrow" '
        f'style="margin-bottom:0;color:#14110C">{t("personalization.tab_bookmarks")}</span></div>',
        unsafe_allow_html=True,
    )
    bookmarks = st.session_state.get("bookmarks", set())
    if not bookmarks:
        _render_empty_state("★", t("personalization.no_bookmarks"))
    else:
        try:
            authorized_fns = get_authorized_table_names(groups)
            if not authorized_fns:
                _render_empty_state("★", t("personalization.no_bookmarks"))
            else:
                valid_bookmarks = [bk for bk in bookmarks if bk in authorized_fns]
                if not valid_bookmarks:
                    _render_empty_state("★", t("personalization.no_bookmarks"))
                    return
                all_tables = get_authorized_tables(groups)
                bk_df = all_tables[all_tables["full_name"].isin(valid_bookmarks)]
                if bk_df.empty:
                    _render_empty_state("★", t("personalization.no_bookmarks"))
                else:
                    # ⚡ Bolt: Replace slow itertuples() and getattr() with fast native dictionary iteration
                    for row_dict in bk_df.to_dict("records"):
                        _render_table_card(row_dict, "bk")
        except Exception as e:
            logging.error("Error loading bookmarks: %s", e)
            st.error(t("discovery.load_error"))

    col_bookmarks = st.session_state.get("col_bookmarks", set())
    st.markdown(
        f'<div class="dd-section-header" style="margin-top:32px">'
        f'<span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">'
        f'{t("personalization.bookmarked_columns")}</span></div>',
        unsafe_allow_html=True,
    )
    if not col_bookmarks:
        _render_empty_state("🔖", t("personalization.no_col_bookmarks"))
    else:
        _col_bk_auth_fns = (
            get_authorized_table_names(groups)
            if groups else set()
        )
        for _bk_id in sorted(col_bookmarks):
            if "::" not in _bk_id:
                continue
            _bk_table, _bk_col = _bk_id.split("::", 1)
            if _bk_table not in _col_bk_auth_fns:
                continue  # parent table no longer authorized — hide silently
            _bk_tbl_parts = _bk_table.split(".")
            _bk_tbl_label = _bk_tbl_parts[-1] if _bk_tbl_parts else _bk_table
            _bk_path = " · ".join(_bk_tbl_parts[:-1]) if len(_bk_tbl_parts) > 1 else ""
            _c_col, _c_star = st.columns([11, 1], gap="small")
            with _c_col:
                st.markdown(
                    f'<div style="background:var(--paper);border:1px solid var(--ink-10);'
                    f'padding:10px 16px;border-radius:2px;margin-bottom:4px;">'
                    f'<div style="font-family:var(--font-mono);font-size:11px;'
                    f'color:var(--ink-40);margin-bottom:4px;">'
                    f'{_html.escape(_bk_path)} · {_html.escape(_bk_tbl_label)}</div>'
                    f'<div style="font-family:var(--font-mono);font-size:14px;'
                    f'color:var(--ink);">{_html.escape(_bk_col)}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    t("discovery.explore_button", name=_bk_tbl_label), key=f"colbk_open_{_bk_id}",
                    help=t("search.view_details_help"),
                    use_container_width=True, type="secondary",
                ):
                    st.query_params["tab"] = "search"
                    st.session_state["dd_search_override"] = _bk_tbl_label
                    st.session_state["dd_nav_select"] = _bk_table
                    st.rerun()
            with _c_star:
                if st.button(
                    "★", key=f"colbk_rm_{_bk_id}",
                    help=t("personalization.remove_bookmark"),
                    use_container_width=True,
                ):
                    st.session_state.col_bookmarks.discard(_bk_id)
                    _pref_delete(_bk_id, "col_bookmark")
                    st.toast(t("personalization.bookmark_removed"))
                    st.rerun()


def _get_recommended_tables(authorized_full_names: set, top_n: int = 10) -> list[str]:
    """Return full_names of popular tables in the user's groups, from audit_log."""
    if is_demo_mode() or not _duckdb_available():
        return []
    try:
        result = run_query(
            "SELECT object_name, COUNT(*) AS views "
            "FROM user_data.audit_log "
            "WHERE event_type IN ('table_description_change', 'business_name_change', 'comment_added') "
            "GROUP BY object_name ORDER BY views DESC LIMIT %(n)s",
            {"n": top_n * 3},
        )
        if result is None or result.empty:
            return []
        # Filter to only authorized tables the user hasn't recently viewed
        recent = set(st.session_state.get("recent_views", [])[:5])
        # ⚡ Bolt: Removed redundant and slow string split/join operations on object_name
        return [
            str(r.get("object_name", ""))
            for r in result.to_dict("records")
            if str(r.get("object_name", "")) in authorized_full_names
            and str(r.get("object_name", "")) not in recent
            ][:top_n]
    except Exception as exc:
        logging.warning("Recommended tab query failed: %s", exc)
        return []


def _render_recommended_tab(groups):
    st.markdown(
        f'<div class="dd-section-header"><span class="dd-eyebrow" '
        f'style="margin-bottom:0;color:#14110C">{t("personalization.recommended_title")}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);'
        f'margin-bottom:12px;">{t("personalization.recommended_subtitle")}</p>',
        unsafe_allow_html=True,
    )
    try:
        authorized_fns = get_authorized_table_names(groups)
        if not authorized_fns:
            _render_empty_state("💡", t("personalization.recommended_empty"))
            return
        recommended_fns = _get_recommended_tables(authorized_fns)
        if not recommended_fns:
            _render_empty_state("💡", t("personalization.recommended_empty"))
            return
        all_tables = get_authorized_tables(groups)
        rec_df = all_tables[all_tables["full_name"].isin(recommended_fns)].copy()
        # ⚡ Bolt: Replace .map() ordering with pd.Categorical for faster sorting and to avoid creating/dropping temp columns
        rec_df["full_name"] = pd.Categorical(rec_df["full_name"], categories=recommended_fns, ordered=True)
        rec_df = rec_df.sort_values("full_name")
        if rec_df.empty:
            _render_empty_state("💡", t("personalization.recommended_empty"))
        else:
            # ⚡ Bolt: Replace slow itertuples() and getattr() with fast native dictionary iteration
            for row_dict in rec_df.to_dict("records"):
                _render_table_card(row_dict, "rec")
    except Exception as e:
        logging.error("Error loading recommendations: %s", e)
        st.error(t("discovery.load_error"))


def _render_recent_tab(groups):
    st.markdown(
        f'<div class="dd-section-header"><span class="dd-eyebrow" '
        f'style="margin-bottom:0;color:#14110C">{t("personalization.tab_recent")}</span></div>',
        unsafe_allow_html=True,
    )
    recent_views = st.session_state.get("recent_views", [])
    if not recent_views:
        _render_empty_state("⏱", t("personalization.no_recent"))
    else:
        try:
            authorized_fns = get_authorized_table_names(groups)
            if not authorized_fns:
                _render_empty_state("⏱", t("personalization.no_recent"))
                return
            valid_recent = [rv for rv in recent_views if rv in authorized_fns]
            if not valid_recent:
                _render_empty_state("⏱", t("personalization.no_recent"))
                return
            all_tables = get_authorized_tables(groups)
            rv_df = all_tables[all_tables["full_name"].isin(valid_recent)].copy()
            # ⚡ Bolt: Replace .map() ordering with pd.Categorical for faster sorting and to avoid creating/dropping temp columns
            rv_df["full_name"] = pd.Categorical(rv_df["full_name"], categories=recent_views, ordered=True)
            rv_df = rv_df.sort_values("full_name")
            if rv_df.empty:
                _render_empty_state("⏱", t("personalization.no_recent"))
            else:
                # ⚡ Bolt: Replace slow itertuples() and getattr() with fast native dictionary iteration
                for row_dict in rv_df.to_dict("records"):
                    _render_table_card(row_dict, "rv")
        except Exception as e:
            logging.error("Error loading recent views: %s", e)
            st.error(t("discovery.load_error"))
