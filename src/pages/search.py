from __future__ import annotations
from typing import Any, Callable, Optional, Protocol, runtime_checkable
"""Search tab — result cards and table detail panel."""


import html as _html
import logging
import os
import urllib.parse

import pandas as _pd
import streamlit as st
import streamlit.components.v1 as components

from src.config import CATALOG_CACHE, SCHEMA_CACHE, MAX_BUSINESS_NAME_LEN
from src.i18n import t
from src.db.queries import (
    get_authorized_tables, search_all_metadata,
    get_column_business_names, run_query, export_schema_to_csv,
)
from src.personalization import _pref_upsert, _pref_delete, is_power_user
from src.comments import get_table_comments, save_comment
from src.audit import save_business_name, get_table_steward
from src.ui.cards import (
    _dq_grade, _compute_live_completeness,
    render_table_metadata_editor, render_data_sample,
)
from src.ui.lineage import _build_lineage_graph, _lineage_vis_html, render_lineage_fullscreen


def _render_comment_form(
    full_name: str,
    steward: str,
    key_suffix: str,
    parent_comment_id: str = None,
) -> None:
    """Render a text-area + Send/Cancel for a new comment or reply."""
    _open_key = f"dd_comment_open_{key_suffix}"
    if not st.session_state.get(_open_key):
        _label = t("comment.reply") if parent_comment_id else t("comment.leave_a_comment")
        if st.button(_label, key=f"dd_comment_btn_{key_suffix}"):
            st.session_state[_open_key] = True
            st.rerun()
    else:
        _placeholder = t("comment.placeholder_reply") if parent_comment_id else t("comment.placeholder_new")
        _inp = st.text_area(
            t("comment.your_comment") if not parent_comment_id else t("comment.your_reply"),
            placeholder=_placeholder,
            max_chars=1000,
            label_visibility="collapsed",
            help=t("comment.max_chars"),
            key=f"dd_comment_text_{key_suffix}",
        )
        _cs, _cc, _ = st.columns([2, 2, 4], gap="small")
        with _cs:
            if st.button(t("comment.send"), key=f"dd_comment_send_{key_suffix}", use_container_width=True):
                if _inp.strip():
                    save_comment(
                        "TABLE", full_name, _inp.strip(), steward,
                        parent_comment_id=parent_comment_id,
                    )
                    st.session_state.pop(_open_key, None)
                    st.rerun()
                else:
                    st.warning(t("comment.empty_error"))
        with _cc:
            if st.button(t("comment.cancel"), key=f"dd_comment_cancel_{key_suffix}", use_container_width=True):
                st.session_state.pop(_open_key, None)
                st.rerun()
        if not steward and not parent_comment_id:
            st.markdown(
                f'<p class="dd-comment-no-steward">{t("comment.no_steward")}</p>',
                unsafe_allow_html=True,
            )


def _render_result_card(full_name: str, name: str, desc: str, match_type: str, dq_score: str) -> None:
    """Render a single search result card (without the action button)."""
    _grade, _gcls = _dq_grade(dq_score)
    st.markdown(f'''
    <div style="background:var(--paper); border:1px solid var(--ink-10); border-radius:4px; padding:14px 18px; height:100%;">
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
            <span class="dd-dq-badge {_gcls}" title="Completeness grade {_grade}">{_grade}</span>
            <span style="font-family:var(--font-mono); font-size:11px; color:var(--ink-60); text-transform:uppercase; letter-spacing:0.08em;">{_html.escape(match_type)}</span>
        </div>
        <div style="font-family:var(--font-sans); font-size:15px; font-weight:600; color:var(--ink); margin-bottom:2px;">{_html.escape(name)}</div>
        <div style="font-family:var(--font-mono); font-size:11px; color:var(--ink-60); margin-bottom:6px;">{_html.escape(full_name)}</div>
        <p style="font-family:var(--font-sans); font-size:13px; color:var(--ink-60); line-height:1.5; margin:0;">{_html.escape(desc)}</p>
    </div>''', unsafe_allow_html=True)


def _render_detail_panel(row: "_pd.Series", full_name: str, query_groups: tuple) -> None:
    """Render the two-column table detail panel (main + side)."""
    col_main, col_side = st.columns([7, 5], gap="large")

    with col_main:
        _cat  = str(row["catalog_name"])
        _sch  = str(row["schema_name"])
        _tbl  = str(row["table_name"])
        _raw_desc = row.get("table_description", "")
        _desc = _html.escape(str(_raw_desc) if isinstance(_raw_desc, str) else "")

        _host = _html.escape(os.getenv("DATABRICKS_HOST", "").strip())
        _url_cat = urllib.parse.quote(str(row["catalog_name"]))
        _url_sch = urllib.parse.quote(str(row["schema_name"]))
        _url_tbl = urllib.parse.quote(str(row["table_name"]))
        _ext_text = _html.escape(str(t("table.open_in_databricks")))
        _ext_link = (
            f'<a href="https://{_host}/explore/data/{_url_cat}/{_url_sch}/{_url_tbl}" '
            f'target="_blank" class="dd-link-external">{_ext_text} ↗</a>'
            if _host else ""
        )

        st.markdown(
            f'<div class="dd-detail-header" style="margin-top: 0;">'
            f'<span class="dd-eyebrow" style="margin-bottom:0">{t("detail.title")}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Live completeness score
        _live_key = f"_live_completeness_{full_name}"
        if _live_key not in st.session_state:
            _fallback = float(str(row.get("dq_score", "") or 0) or 0)
            try:
                st.session_state[_live_key] = _compute_live_completeness(full_name) or _fallback
            except Exception:
                st.session_state[_live_key] = _fallback
        _score = float(st.session_state[_live_key])
        _grade, _gcls = _dq_grade(_score)

        _steward = _html.escape(str(row.get("steward_email", "")))
        st.markdown(
            f'<div class="dd-eyebrow" style="margin-bottom:4px">{_html.escape(_cat)} · {_html.escape(_sch)}</div>'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
            f'<div class="dd-detail-table-name" style="margin-bottom:0">{_html.escape(_tbl)}</div>'
            f'<div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">'
            f'<span class="dd-dq-badge {_gcls}" style="width:32px;height:32px;font-size:14px;" '
            f'title="Completeness {_score:.0f}/100">{_grade}</span>'
            f'<span style="font-family:var(--font-mono);font-size:13px;color:var(--ink-60);">{_score:.0f}%</span>'
            f'</div>'
            f'</div>'
            f'<p class="dd-detail-desc">{_desc}</p>{_ext_link}',
            unsafe_allow_html=True,
        )

        if is_power_user():
            if st.button(f"✎ {t('detail.edit_table')}", key=f"edit_tbl_{full_name}", help=t("detail.edit_table_help"), type="secondary"):
                render_table_metadata_editor(full_name, _raw_desc, _steward)

        # Bookmark + full_name row
        _is_bk = full_name in st.session_state.get("bookmarks", set())
        _c_code, _c_bk = st.columns([11, 1], gap="small")
        with _c_code:
            st.code(full_name, language=None)
        with _c_bk:
            if st.button(
                "★" if _is_bk else "☆",
                key=f"bk_{full_name}",
                help=t("personalization.remove_bookmark") if _is_bk else t("personalization.add_bookmark"),
                use_container_width=True,
            ):
                if _is_bk:
                    st.session_state.get("bookmarks", set()).discard(full_name)
                    _pref_delete(full_name, "bookmark")
                else:
                    st.session_state.get("bookmarks", set()).add(full_name)
                    _pref_upsert(full_name, "bookmark")
                st.rerun()

        # Record recently viewed
        _rv = st.session_state.get("recent_views", [])
        if not _rv or _rv[0] != full_name:
            st.session_state.recent_views = [full_name] + [x for x in _rv if x != full_name][:49]
            _pref_upsert(full_name, "recent")

        # Columns section
        col_overrides = get_column_business_names(full_name)
        cols_query = (
            "SELECT column_name, data_type, comment "
            "FROM {0}.{1}.columns_metadata "
            "WHERE table_full_name = %(table_full_name)s ORDER BY column_name"
        ).format(CATALOG_CACHE, SCHEMA_CACHE)
        cols = run_query(cols_query, {"table_full_name": full_name})
        n_cols = len(cols) if cols is not None and not cols.empty else 0

        _c_preview, _c_export = st.columns(2, gap="small")
        with _c_preview:
            if st.button(t("detail.preview_data"), key=f"preview_{full_name}", use_container_width=True):
                render_data_sample(full_name)
        with _c_export:
            if n_cols > 0:
                st.download_button(
                    label=t("detail.export_dictionary"),
                    data=export_schema_to_csv(cols, col_overrides),
                    file_name=f"{row['catalog_name']}_{row['schema_name']}_{row['table_name']}_schema.csv",
                    mime="text/csv",
                    key=f"export_{full_name}",
                    use_container_width=True,
                )

        st.markdown(
            f'<div class="dd-section-header">'
            f'<span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_columns")}</span>'
            f'<span class="dd-section-count">{n_cols}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        _power    = is_power_user()
        _col_edit = st.session_state.get("dd_col_edit_mode", "")

        if n_cols > 0:
            for c in cols.itertuples(index=False):
                _cname    = str(getattr(c, "column_name", ""))
                _ctype    = str(getattr(c, "data_type", ""))
                _ccomment = str(getattr(c, "comment", "") or "")
                _edit_key = f"{full_name}__{_cname}"
                _override = col_overrides.get(_cname, {})
                _col_biz  = _override.get("business_name", "")
                _col_def  = _override.get("definition", "")

                st.markdown('<hr class="dd-col-divider">', unsafe_allow_html=True)
                _r_name, _r_type, _r_desc, _r_btn, _r_star = st.columns([3, 2, 4, 1, 1], gap="small")

                if _col_biz:
                    _r_name.markdown(
                        f'<span class="dd-col-biz-name">{_html.escape(_col_biz)}</span>'
                        f'<span class="dd-col-tech-sub">{_html.escape(_cname)}</span>',
                        unsafe_allow_html=True,
                    )
                else:
                    _r_name.markdown(f'<span class="dd-col-name">{_html.escape(_cname)}</span>', unsafe_allow_html=True)

                _r_type.markdown(f'<span class="dd-col-type">{_html.escape(_ctype)}</span>', unsafe_allow_html=True)

                if _col_def:
                    _r_desc.markdown(
                        f'<span class="dd-col-desc">{_html.escape(_col_def)}</span>'
                        f'<span class="dd-col-desc-faded">{_html.escape(_ccomment)}</span>',
                        unsafe_allow_html=True,
                    )
                else:
                    _r_desc.markdown(f'<span class="dd-col-desc">{_html.escape(_ccomment)}</span>', unsafe_allow_html=True)

                if _power and _col_edit != _edit_key:
                    if _r_btn.button("✎", key=f"col_edit_{_edit_key}", help=t("common.edit"), use_container_width=True):
                        st.session_state["dd_col_edit_mode"] = _edit_key
                        st.rerun()

                _col_bk_id = f"{full_name}::{_cname}"
                _is_col_bk = _col_bk_id in st.session_state.get("col_bookmarks", set())
                if _r_star.button("★" if _is_col_bk else "☆", key=f"colbk_{_edit_key}", help=t("personalization.remove_bookmark") if _is_col_bk else t("personalization.add_bookmark"), use_container_width=True):
                    if _is_col_bk:
                        st.session_state.get("col_bookmarks", set()).discard(_col_bk_id)
                        _pref_delete(_col_bk_id, "col_bookmark")
                    else:
                        st.session_state.get("col_bookmarks", set()).add(_col_bk_id)
                        _pref_upsert(_col_bk_id, "col_bookmark")
                    st.rerun()

                if _col_edit == _edit_key:
                    st.markdown(
                        f'<div class="dd-edit-banner">{t("editor.edit_mode_banner")}</div>',
                        unsafe_allow_html=True,
                    )
                    _inp_name = st.text_input(
                        t("editor.business_name_label"),
                        value=_col_biz,
                        placeholder=t("editor.placeholder_biz_name"),
                        max_chars=None if os.getenv("TESTING_NO_MAX_CHARS") else MAX_BUSINESS_NAME_LEN,
                        key=f"col_biz_name_{_edit_key}",
                    )
                    _inp_def = st.text_input(
                        t("editor.definition_label"),
                        value=_col_def,
                        placeholder=t("editor.placeholder_biz_def"),
                        max_chars=None if os.getenv("TESTING_NO_MAX_CHARS") else MAX_BUSINESS_NAME_LEN,
                        key=f"col_biz_def_{_edit_key}",
                    )
                    _sc, _cc, _ = st.columns([2, 2, 4], gap="small")
                    with _sc:
                        if st.button(t("editor.save"), key=f"col_biz_save_{_edit_key}", use_container_width=True):
                            try:
                                save_business_name(full_name, _cname, _inp_name.strip(), _inp_def.strip())
                                st.session_state.pop("dd_col_edit_mode", None)
                                st.session_state.pop(f"_live_completeness_{full_name}", None)
                                st.rerun()
                            except PermissionError:
                                st.error(t("editor.permission_error"))
                            except ValueError as exc:
                                st.error(str(exc))
                            except Exception as exc:
                                logging.error("Save failed for %s.%s: %s", full_name, _cname, exc, exc_info=True)
                                st.error(t("common.error_with_details", error=str(exc)))
                    with _cc:
                        if st.button(t("editor.cancel"), key=f"col_biz_cancel_{_edit_key}", use_container_width=True):
                            st.session_state.pop("dd_col_edit_mode", None)
                            st.rerun()
                    if _override.get("edited_by"):
                        st.markdown(
                            f'<div class="dd-biz-audit">{t("editor.last_edited_by", user=_html.escape(_override["edited_by"]), date=_html.escape(str(_override.get("edited_at", ""))))}</div>',
                            unsafe_allow_html=True,
                        )
        else:
            st.markdown(
                f'<p style="font-size:13px;color:var(--ink-40);padding:12px 0">{t("detail.no_columns")}</p>',
                unsafe_allow_html=True,
            )

        # Comments section
        _steward_email = get_table_steward(full_name)
        _comments      = get_table_comments(full_name)
        _n_comments    = sum(1 + len(_c.get("replies", [])) for _c in _comments)
        st.markdown(
            f'<div class="dd-section-header">'
            f'<span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_comments")}</span>'
            f'<span class="dd-section-count">{_n_comments}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        for _c in _comments:
            _cid    = str(_c.get("comment_id", ""))
            _cemail = str(_c.get("author_email", ""))
            st.markdown(
                f'<div class="dd-comment-row">'
                f'<span class="dd-comment-author">{_html.escape(str(_c.get("author_name", "")))}</span>'
                f'<span class="dd-comment-date"> · {_html.escape(str(_c.get("created_at", "")))}</span>'
                f'<div class="dd-comment-text">{_html.escape(str(_c.get("comment_text", "")))}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            for _r in _c.get("replies", []):
                _, _reply_col = st.columns([1, 11])
                with _reply_col:
                    st.markdown(
                        f'<div class="dd-comment-row dd-comment-reply">'
                        f'<span class="dd-comment-author">{_html.escape(str(_r.get("author_name", "")))}</span>'
                        f'<span class="dd-comment-date"> · {_html.escape(str(_r.get("created_at", "")))}</span>'
                        f'<div class="dd-comment-text">{_html.escape(str(_r.get("comment_text", "")))}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            _, _reply_form_col = st.columns([1, 11])
            with _reply_form_col:
                _render_comment_form(full_name, _steward_email, f"{full_name}_{_cid}", _cid)

        _render_comment_form(full_name, _steward_email, full_name)

    with col_side:
        # Grants section
        _placeholders = ", ".join(f"%(grant_group_{i})s" for i in range(len(query_groups))) if query_groups else "''"
        grants_params: dict = {"table_full_name": full_name}
        for _i, _g in enumerate(query_groups):
            grants_params[f"grant_group_{_i}"] = _g
        grants_query = (
            "SELECT DISTINCT principal, privilege FROM {0}.{1}.permissions_cache "
            "WHERE table_full_name = %(table_full_name)s "
            "AND (principal IN ({2}) OR principal = 'SELECT_ALL_USERS') "
            "ORDER BY principal"
        ).format(CATALOG_CACHE, SCHEMA_CACHE, _placeholders)  # nosec B608
        grants   = run_query(grants_query, grants_params)
        n_grants = len(grants) if grants is not None and not grants.empty else 0
        st.markdown(
            f'<div class="dd-section-header" style="margin-top:0">'
            f'<span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_grants")}</span>'
            f'<span class="dd-section-count">{n_grants}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if n_grants > 0:
            for g in grants.itertuples(index=False):
                principal = str(getattr(g, "principal", ""))
                privilege = str(getattr(g, "privilege", ""))
                st.markdown('<div style="border-top: 1px solid var(--ink-10); margin: 8px 0 4px 0;"></div>', unsafe_allow_html=True)
                if principal == "SELECT_ALL_USERS":
                    if st.button(t("detail.browse_public_tables", privilege=privilege), key=f"grant_{full_name}_public_{privilege}", use_container_width=True):
                        st.session_state["group_filter"] = "SELECT_ALL_USERS"
                        st.session_state.pop("catalog_search", None)
                        st.session_state.pop("dd_nav_select", None)
                        st.rerun()
                else:
                    if st.button(t("detail.search_tables_accessible", principal=principal, privilege=privilege), key=f"grant_{full_name}_{principal}_{privilege}", use_container_width=True):
                        st.session_state["group_filter"] = principal
                        st.session_state.pop("catalog_search", None)
                        st.session_state.pop("dd_nav_select", None)
                        st.rerun()
        else:
            st.markdown(f'<p style="font-size:13px;color:var(--ink-40);padding:12px 0">{t("detail.no_grants")}</p>', unsafe_allow_html=True)

        # Lineage + related tables
        graph_nodes, graph_links = _build_lineage_graph(
            full_name, str(row["table_name"]), query_groups, run_query, max_depth=2,
        )

        rel_placeholders = ", ".join(f"%(group_{i})s" for i in range(len(query_groups))) if query_groups else "''"
        rel_params = {"catalog_name": row["catalog_name"], "schema_name": row["schema_name"], "full_name": full_name}
        for i, group in enumerate(query_groups):
            rel_params[f"group_{i}"] = group
        related_query = (
            "SELECT t.full_name, t.table_name, t.catalog_name, t.schema_name, 'Same schema' AS relationship "
            "FROM {0}.{1}.tables_metadata t JOIN {0}.{1}.permissions_cache p ON t.full_name = p.table_full_name "
            "WHERE t.catalog_name = %(catalog_name)s AND t.schema_name = %(schema_name)s "
            "AND t.full_name != %(full_name)s AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS') "
            "UNION "
            "SELECT DISTINCT t.full_name, t.table_name, t.catalog_name, t.schema_name, 'Shared column' AS relationship "
            "FROM {0}.{1}.columns_metadata c1 JOIN {0}.{1}.columns_metadata c2 ON c1.column_name = c2.column_name "
            "JOIN {0}.{1}.tables_metadata t ON c2.table_full_name = t.full_name "
            "JOIN {0}.{1}.permissions_cache p ON t.full_name = p.table_full_name "
            "WHERE c1.table_full_name = %(full_name)s AND c2.table_full_name != %(full_name)s "
            "AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS') LIMIT 12"
        ).format(CATALOG_CACHE, SCHEMA_CACHE, rel_placeholders)  # nosec B608
        related  = run_query(related_query, rel_params)
        n_related = len(related) if related is not None and not related.empty else 0

        if n_related > 0:
            for rel in related.itertuples(index=False):
                _rel_full      = str(getattr(rel, "full_name", ""))
                _rel_name      = _html.escape(str(getattr(rel, "table_name", "")))
                _rel_raw_badge = str(getattr(rel, "relationship", ""))
                _rel_badge = (
                    t("detail.same_schema") if _rel_raw_badge == "Same schema"
                    else t("detail.shared_column") if _rel_raw_badge == "Shared column"
                    else _html.escape(_rel_raw_badge)
                )
                if not any(n["id"] == _rel_full for n in graph_nodes):
                    graph_nodes.append({"id": _rel_full, "label": _rel_name, "current": False, "relationship": _rel_badge})
                if not any((lnk["from"] == full_name and lnk["to"] == _rel_full) or (lnk["from"] == _rel_full and lnk["to"] == full_name) for lnk in graph_links):
                    graph_links.append({"from": full_name, "to": _rel_full})

        _lin_hdr_col, _lin_btn_col = st.columns([11, 1])
        with _lin_hdr_col:
            st.markdown(
                f'<div class="dd-section-header">'
                f'<span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_lineage")} & {t("detail.section_related")}</span>'
                f'<span class="dd-section-count">{n_related} {t("detail.related_count")}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with _lin_btn_col:
            if st.button("⤢", key=f"expand_lin_{full_name}", help=t("detail.expand_lineage"), use_container_width=True):
                render_lineage_fullscreen(graph_nodes, graph_links, full_name)

        components.html(_lineage_vis_html(graph_nodes, graph_links, height=350), height=380)

        if n_related > 0:
            st.markdown('<div style="margin-top: 16px;"></div>', unsafe_allow_html=True)
            _cols = st.columns(min(3, n_related), gap="small")
            for i, rel in enumerate(related.itertuples(index=False)):
                with _cols[i % 3]:
                    _rel_full      = str(getattr(rel, "full_name", ""))
                    _rel_name      = _html.escape(str(getattr(rel, "table_name", "")))
                    _rel_sch       = _html.escape(f"{getattr(rel, 'catalog_name', '')}.{getattr(rel, 'schema_name', '')}")
                    _rel_raw_badge = str(getattr(rel, "relationship", ""))
                    _rel_badge = (
                        t("detail.same_schema") if _rel_raw_badge == "Same schema"
                        else t("detail.shared_column") if _rel_raw_badge == "Shared column"
                        else _html.escape(_rel_raw_badge)
                    )
                    st.markdown(
                        f'<div class="dd-related-card">'
                        f'<div class="dd-related-badge">{_rel_badge}</div>'
                        f'<div class="dd-related-name">{_rel_name}</div>'
                        f'<div class="dd-related-schema">{_rel_sch}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button(t("detail.open_related"), key=f"rel_{_rel_full}", type="secondary", use_container_width=True):
                        st.session_state["dd_search_override"] = str(rel.get("table_name", ""))
                        st.session_state["dd_nav_select"] = _rel_full
                        st.rerun()


def render_search_page(query_groups: tuple) -> None:
    """Render the search tab: hero, search box, result cards, and table detail panel."""
    active_group = st.session_state.get("group_filter")

    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t('search.eyebrow')}</div>
      <h1>{t('search.hero_title')}</h1>
      <p class="lead">{t('search.hero_subtitle')}</p>
    </div>
    ''', unsafe_allow_html=True)

    if "dd_search_override" in st.session_state:
        st.session_state["catalog_search"] = st.session_state.pop("dd_search_override")
    if "dd_nav_select" in st.session_state:
        _nav_candidate = st.session_state.pop("dd_nav_select")
        try:
            _auth_df       = get_authorized_tables(query_groups)
            _auth_full_names = set(_auth_df["full_name"].tolist()) if _auth_df is not None and not _auth_df.empty else set()
        except Exception:
            _auth_full_names = set()
        if _nav_candidate in _auth_full_names:
            st.session_state["_dd_sticky_nav"] = _nav_candidate
        else:
            st.session_state.pop("_dd_sticky_nav", None)

    if active_group:
        c1, c2 = st.columns([8, 2], gap="small", vertical_alignment="center")
        with c1:
            if active_group == "SELECT_ALL_USERS":
                st.info(t("search.public_tables_filter"))
            else:
                st.info(t("search.group_filter_active", group=active_group))
        with c2:
            if st.button(f"← {t('common.back')}", use_container_width=True, type="secondary"):
                st.session_state.pop("group_filter", None)
                st.rerun()

    try:
        _all_tables = get_authorized_tables(query_groups)
        _table_options = (
            sorted(_all_tables["table_name"].unique().tolist())
            if _all_tables is not None and not _all_tables.empty and "table_name" in _all_tables.columns
            else []
        )
    except Exception as e:
        logging.error("Error querying data: %s", e, exc_info=True)
        st.error(t("search.load_error"))
        _all_tables    = None
        _table_options = []

    search_query = st.selectbox(
        t("common.search"),
        options=_table_options,
        index=None,
        placeholder=t("search.placeholder"),
        label_visibility="collapsed",
        key="catalog_search",
        help=t("search.placeholder"),
    )

    _prev_query = st.session_state.get("_dd_current_search_query")
    if _prev_query is not None and _prev_query != search_query:
        st.session_state.pop("dd_col_edit_mode", None)
        for k in [k for k in st.session_state if str(k).startswith("dd_comment_open_")]:
            del st.session_state[k]
        st.session_state.pop("_dd_sticky_nav", None)
    st.session_state["_dd_current_search_query"] = search_query

    # Group-filter browse: show all authorized tables when filter is active
    if active_group and not search_query and _all_tables is not None and not _all_tables.empty:
        _gr = _all_tables.copy()
        if "match_type" not in _gr.columns:
            _gr["match_type"] = "Table"
        if "name" not in _gr.columns:
            _gr["name"] = _gr["table_name"]
        if "description"  not in _gr.columns:
            _desc_col = next((c for c in ("table_description", "comment") if c in _gr.columns), None)
            _gr["description"] = _gr[_desc_col] if _desc_col else ""
        st.markdown(
            f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);margin-bottom:12px">'
            f'{t("search.results_count", count=len(_gr))}</p>',
            unsafe_allow_html=True,
        )
        for _i, _row in enumerate(_gr.itertuples(index=False)):
            _fn = str(getattr(_row, "full_name", ""))
            if not _fn:
                continue
            _gc, _gb = st.columns([5, 1], gap="small", vertical_alignment="top")
            with _gc:
                _render_result_card(_fn, str(getattr(_row, "name", "") or getattr(_row, "table_name", "")), str(getattr(_row, "description", "") or ""), "Table", str(getattr(_row, "dq_score", "") or ""))
            with _gb:
                if st.button(f"{t('search.view_details')} →", key=f"gview_{_fn}_{_i}", help=t("search.view_details_help"), use_container_width=True):
                    _auth_df = get_authorized_tables(query_groups)
                    _allowed = set(_auth_df["full_name"].tolist()) if _auth_df is not None and not _auth_df.empty else set()
                    if _fn in _allowed:
                        st.session_state["dd_search_override"] = str(_row.get("name") or _row.get("table_name", ""))
                        st.session_state["dd_nav_select"] = _fn
                        st.rerun()
                    else:
                        st.error(t("detail.unauthorized"))
            st.markdown('<div style="margin-bottom:8px;"></div>', unsafe_allow_html=True)

    if search_query:
        try:
            results = search_all_metadata(search_query, query_groups)
            if results is not None and not results.empty:
                _table_results = results[results["match_type"] == "Table"] if "match_type" in results.columns else results
                _table_names   = _table_results["table_name"].tolist()
                _nav_target    = st.session_state.get("_dd_sticky_nav")
                _nav_idx       = None
                if _nav_target:
                    _nav_name = _nav_target.split(".")[-1]
                    if _nav_name in _table_names:
                        _nav_idx = _table_names.index(_nav_name)

                if _nav_idx is None:
                    def _s(v):
                        return "" if _pd.isna(v) else str(v)
                    st.markdown(
                        f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);margin-bottom:12px">'
                        f'{t("search.results_count", count=len(results))}</p>',
                        unsafe_allow_html=True,
                    )
                    for _sr_i, _sr in enumerate(results.itertuples(index=False)):
                        _fn = _s(getattr(_sr, "full_name", None))
                        if not _fn:
                            continue
                        _card_col, _btn_col = st.columns([5, 1], gap="small", vertical_alignment="top")
                        with _card_col:
                            _render_result_card(_fn, _s(getattr(_sr, "name", None)), _s(getattr(_sr, "description", None)), _s(getattr(_sr, "match_type", None)), _s(getattr(_sr, "dq_score", "")))
                        with _btn_col:
                            if st.button(f"{t('search.view_details')} →", key=f"view_{_fn}_{_sr_i}", help=t("search.view_details_help"), use_container_width=True):
                                _auth_df = get_authorized_tables(query_groups)
                                _allowed = set(_auth_df["full_name"].tolist()) if _auth_df is not None and not _auth_df.empty else set()
                                if _fn in _allowed:
                                    st.session_state["_dd_sticky_nav"] = _fn
                                    st.rerun()
                                else:
                                    st.error(t("detail.unauthorized"))
                        st.markdown('<div style="margin-bottom:8px;"></div>', unsafe_allow_html=True)

                if _nav_idx is not None:
                    _row     = _table_results[_table_results["table_name"] == _table_names[_nav_idx]].iloc[0]
                    full_name = f"{_row['catalog_name']}.{_row['schema_name']}.{_row['table_name']}"
                    if st.button(f"← {t('search.back_to_results')}", key="search_back", help=t("search.back_to_results_help")):
                        st.session_state.pop("_dd_sticky_nav", None)
                        st.rerun()
                    _render_detail_panel(_row, full_name, query_groups)

        except Exception as e:
            logging.error("Error displaying search results: %s", e, exc_info=True)
            st.error(t("detail.load_error"))
    else:
        st.markdown(
            f'<p style="font-family:var(--font-sans);font-size:15px;color:var(--ink-60);margin-top:8px">'
            f'{t("search.start_typing")}</p>',
            unsafe_allow_html=True,
        )
