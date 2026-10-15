from __future__ import annotations
"""Search tab — result cards and table detail panel."""


import html as _html
import logging
import os
from urllib.parse import quote

import pandas as _pd
import streamlit as st
import streamlit.components.v1 as components

from src.config import CATALOG_CACHE, SCHEMA_CACHE, MAX_BUSINESS_NAME_LEN
from src.i18n import t, get_current_locale
from src.db.queries import (
    get_authorized_tables, search_all_metadata,
    get_multi_hop_lineage, run_query, export_schema_to_csv,
)
from src.analytics import SearchEvent, track_search
from src.audit import get_column_overrides, get_table_columns
from src.personalization import _pref_upsert, _pref_delete, is_power_user
from src.auth import is_admin
from src.comments import get_table_comments, save_comment
from src.audit import save_business_name, get_table_steward
from src.ui.cards._shared import _dq_grade, _compute_live_completeness
from src.ui.cards.detail import (
    render_data_sample,
    render_table_business_name_editor,
    render_table_metadata_editor,
)
from src.ui.lineage import _build_lineage_graph, _lineage_vis_html, render_lineage_fullscreen
from src.ui.cards._shared import _render_empty_state



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
        if st.button(_label, key=f"dd_comment_btn_{key_suffix}", help=t("help.btn_leave_comment"), type="primary"):
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
            if st.button(t("comment.send"), key=f"dd_comment_send_{key_suffix}", help=t("help.btn_send_comment"), use_container_width=True, type="primary"):
                with st.spinner(t("common.saving")):
                    if _inp.strip():
                        try:
                            save_comment(
                                "TABLE", full_name, _inp.strip(), steward,
                                parent_comment_id=parent_comment_id,
                            )
                            st.session_state.pop(_open_key, None)
                            st.toast(t("common.saved"))
                            st.rerun()
                        except Exception as exc:
                            logging.error("Failed to save comment for %s: %s", full_name, exc, exc_info=True)
                            st.error(t("common.error"))
                    else:
                        st.warning(t("comment.empty_error"))
        with _cc:
            if st.button(t("comment.cancel"), key=f"dd_comment_cancel_{key_suffix}", help=t("help.btn_cancel_comment"), use_container_width=True):
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
            <span class="dd-dq-badge {_gcls}" title="{t("catalog.completeness_grade", grade=_grade)}">{_grade}</span>
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
        # Friendly name and definition come from the bilingual UC reference
        # table populated at sync time. Locale switches at runtime are picked
        # up by reading st.session_state on every render.
        _locale = get_current_locale()
        _bn_col = "business_name_fr" if _locale == "fr" else "business_name_en"
        _bd_col = "business_definition_fr" if _locale == "fr" else "business_definition_en"
        _friendly = row.get(_bn_col) if hasattr(row, "get") else None
        _friendly = str(_friendly).strip() if _friendly else ""
        _bdef = row.get(_bd_col) if hasattr(row, "get") else None
        _bdef = str(_bdef).strip() if _bdef else ""
        _raw_desc = row.get("table_description", "")
        # Prefer the friendly definition when present; the technical comment
        # stays the fallback so the description rail is never blank.
        _display_desc = _bdef or (str(_raw_desc) if isinstance(_raw_desc, str) else "")
        _desc = _html.escape(_display_desc)

        _host = _html.escape(os.getenv("DATABRICKS_HOST", "").strip())
        _url_cat = quote(str(row["catalog_name"]))
        _url_sch = quote(str(row["schema_name"]))
        _url_tbl = quote(str(row["table_name"]))
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
            _raw_score = row.get("dq_score")
            if _pd.isna(_raw_score):
                _fallback = 0.0
            else:
                _score_str = str(_raw_score).strip()
                _fallback = float(_score_str) if _score_str and _score_str != "nan" else 0.0
            try:
                st.session_state[_live_key] = _compute_live_completeness(full_name) or _fallback
            except Exception:
                st.session_state[_live_key] = _fallback
        _score = float(st.session_state[_live_key])
        _grade, _gcls = _dq_grade(_score)

        _steward = _html.escape(str(row.get("steward_email", "")))
        # When a friendly name is present we promote it to the H1 in the
        # display font and demote the technical table name to a mono sub-line.
        # When absent we keep the original H1 = table_name and skip the
        # sub-line entirely so layout doesn't shift.
        _h1 = _html.escape(_friendly) if _friendly else _html.escape(_tbl)
        _sub = (
            f'<div class="dd-tech-name-sub" style="margin-top:4px;margin-bottom:8px;">'
            f'{_html.escape(_tbl)}</div>'
            if _friendly else ""
        )
        st.markdown(
            f'<div class="dd-eyebrow" style="margin-bottom:4px">{_html.escape(_cat)} · {_html.escape(_sch)}</div>'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0;">'
            f'<div class="dd-detail-table-name" style="margin-bottom:0">{_h1}</div>'
            f'<div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">'
            f'<span class="dd-dq-badge {_gcls}" style="width:32px;height:32px;font-size:14px;" '
            f'title="{t("catalog.completeness_score", score=int(_score))}">{_grade}</span>'
            f'<span style="font-family:var(--font-mono);font-size:13px;color:var(--ink-60);">{_score:.0f}%</span>'
            f'</div>'
            f'</div>'
            f'{_sub}'
            f'<p class="dd-detail-desc">{_desc}</p>{_ext_link}',
            unsafe_allow_html=True,
        )

        if is_power_user():
            _c_em, _c_efn = st.columns([1, 1], gap="small")
            with _c_em:
                if st.button(t('detail.edit_table_btn'), key=f"edit_tbl_{full_name}", help=t("detail.edit_table_help"), type="secondary", use_container_width=True):
                    render_table_metadata_editor(full_name, _raw_desc, _steward)
            with _c_efn:
                if st.button(t('detail.edit_friendly_name_btn'), key=f"edit_friendly_{full_name}", help=t("detail.edit_friendly_name_help"), type="secondary", use_container_width=True):
                    render_table_business_name_editor(
                        full_name,
                        current_name_en=str(row.get("business_name_en", "") or ""),
                        current_name_fr=str(row.get("business_name_fr", "") or ""),
                        current_def_en=str(row.get("business_definition_en", "") or ""),
                        current_def_fr=str(row.get("business_definition_fr", "") or ""),
                    )

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
                    st.toast(t("personalization.bookmark_removed"))
                else:
                    st.session_state.get("bookmarks", set()).add(full_name)
                    _pref_upsert(full_name, "bookmark")
                    st.toast(t("personalization.bookmark_added"))
                st.rerun()

        # Record recently viewed
        _rv = st.session_state.get("recent_views", [])
        if not _rv or _rv[0] != full_name:
            st.session_state.recent_views = [full_name] + [x for x in _rv if x != full_name][:49]
            _pref_upsert(full_name, "recent")

        # Columns section
        col_overrides = get_column_overrides(full_name)
        cols = get_table_columns(full_name)
        n_cols = len(cols) if cols is not None and not cols.empty else 0

        _c_preview, _c_export = st.columns(2, gap="small")
        with _c_preview:
            if st.button(t("detail.preview_data"), key=f"preview_{full_name}", help=t("help.btn_preview_data"), use_container_width=True):
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
                    help=t("detail.export_dictionary_help"),
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
            if n_cols > 50:
                st.info(t("detail.showing_first_50_columns", count=n_cols))
                cols = cols.head(50)
            _cnames = cols["column_name"].tolist() if "column_name" in cols else [""] * len(cols)
            _ctypes = cols["data_type"].tolist() if "data_type" in cols else [""] * len(cols)
            _ccomments = cols["comment"].tolist() if "comment" in cols else [""] * len(cols)

            for _cname_raw, _ctype_raw, _ccomment_raw in zip(_cnames, _ctypes, _ccomments):
                _cname = str(_cname_raw)
                _ctype = str(_ctype_raw)
                _ccomment = str(_ccomment_raw or "")
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
                        st.toast(t("personalization.bookmark_removed"))
                    else:
                        st.session_state.get("col_bookmarks", set()).add(_col_bk_id)
                        _pref_upsert(_col_bk_id, "col_bookmark")
                        st.toast(t("personalization.bookmark_added"))
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
                        if st.button(t("editor.save"), key=f"col_biz_save_{_edit_key}", help=t("help.btn_editor_save"), use_container_width=True, type="primary"):
                            with st.spinner(t("common.saving")):
                                try:
                                    save_business_name(full_name, _cname, _inp_name.strip(), _inp_def.strip())
                                    st.session_state.pop("dd_col_edit_mode", None)
                                    st.session_state.pop(f"_live_completeness_{full_name}", None)
                                    st.toast(t("common.saved"))
                                    st.rerun()
                                except PermissionError:
                                    st.error(t("editor.permission_error"))
                                except ValueError as exc:
                                    logging.error("Validation failed for %s.%s: %s", full_name, _cname, exc, exc_info=True)
                                    st.error(t("common.error"))
                                except Exception as exc:
                                    logging.error("Save failed for %s.%s: %s", full_name, _cname, exc, exc_info=True)
                                    # Security: do not expose internal error details to UI
                                    st.error(t("common.error"))
                    with _cc:
                        if st.button(t("editor.cancel"), key=f"col_biz_cancel_{_edit_key}", help=t("help.btn_editor_cancel"), use_container_width=True):
                            st.session_state.pop("dd_col_edit_mode", None)
                            st.rerun()
                    if _override.get("edited_by"):
                        from src.i18n import format_date
                        st.markdown(
                            f'<div class="dd-biz-audit">{_html.escape(t("editor.last_edited_by", user=_override["edited_by"], date=format_date(_override.get("edited_at"))))}</div>',
                            unsafe_allow_html=True,
                        )
        else:
            st.markdown(
                f'<p style="font-size:13px;color:var(--ink-40);padding:12px 0">{_html.escape(t("detail.no_columns"))}</p>',
                unsafe_allow_html=True,
            )

        # Comments section
        _steward_email = get_table_steward(full_name)
        _comments      = get_table_comments(full_name)
        _n_comments    = sum(1 + len(_c.get("replies", [])) for _c in _comments)
        from src.i18n import format_number
        st.markdown(
            f'<div class="dd-section-header">'
            f'<span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_comments")}</span>'
            f'<span class="dd-section-count">{format_number(_n_comments)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        from src.i18n import format_date
        for _c in _comments:
            _cid    = str(_c.get("comment_id", ""))
            st.markdown(
                f'<div class="dd-comment-row">'
                f'<span class="dd-comment-author">{_html.escape(str(_c.get("author_name", "")))}</span>'
                f'<span class="dd-comment-date"> · {_html.escape(format_date(_c.get("created_at")))}</span>'
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
                        f'<span class="dd-comment-date"> · {_html.escape(format_date(_r.get("created_at")))}</span>'
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
            if n_grants > 50:
                st.info(t("detail.showing_first_50_grants", count=n_grants))
                grants = grants.head(50)
            # ⚡ Bolt: Replace slow itertuples() and getattr() with fast native dictionary iteration
            for g in grants.to_dict("records"):
                principal = str(g.get("principal", ""))
                privilege = str(g.get("privilege", ""))
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
            st.markdown(f'<p style="font-size:13px;color:var(--ink-40);padding:12px 0">{_html.escape(t("detail.no_grants"))}</p>', unsafe_allow_html=True)

        # Downstream impact
        try:
            _downstream = get_multi_hop_lineage(full_name, depth=2)
            _ds_rows = (
                # ⚡ Bolt: Use .to_numpy() to skip index alignment overhead
                _downstream[_downstream["direction"].to_numpy() == "downstream"]
                if _downstream is not None and not _downstream.empty and "direction" in _downstream.columns
                else None
            )
            _n_downstream = len(_ds_rows) if _ds_rows is not None else 0
            _has_critical = (
                _ds_rows["entity_type"].str.lower().str.contains("certified|production", na=False).any()
                if _n_downstream > 0 and "entity_type" in _ds_rows.columns
                else False
            )
        except Exception:
            _n_downstream = 0
            _has_critical = False

        st.markdown(
            f'<div class="dd-section-header">'
            f'<span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_downstream")}</span>'
            f'<span class="dd-section-count">{format_number(_n_downstream)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if _n_downstream == 0:
            st.markdown(
                f'<p style="font-size:13px;color:var(--ink-40);padding:4px 0 12px">'
                f'{_html.escape(t("detail.downstream_none"))}</p>',
                unsafe_allow_html=True,
            )
        else:
            if _has_critical:
                st.markdown(
                    f'<p style="font-family:var(--font-sans);font-size:12px;color:var(--accent);'
                    f'padding:4px 0 8px;">{t("detail.downstream_certified_warning")}</p>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                f'<p style="font-family:var(--font-mono);font-size:12px;color:var(--ink-60);'
                f'padding:0 0 12px;">{_html.escape(t("detail.downstream_count", n=_n_downstream))}</p>',
                unsafe_allow_html=True,
            )

        # Lineage + related tables
        graph_nodes, graph_links = _build_lineage_graph(
            full_name, str(row["table_name"]), query_groups, run_query, max_depth=2,
        )

        # ⚡ Bolt: No N+1 query exists here. The loop safely constructs a parameter dictionary
        # for a single parameterized IN clause execution (preventing injection).
        # Parameter unrolling is required for cross-driver compatibility (e.g. DuckDB and Databricks SQL Connector).
        # It does not execute a query per group.
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
            # ⚡ Bolt: Use set-based tracking for O(1) membership checks instead of O(N) any() over lists
            existing_node_ids = {n["id"] for n in graph_nodes}
            existing_links = {
                (lnk["from"], lnk["to"]) if lnk["from"] < lnk["to"] else (lnk["to"], lnk["from"])
                for lnk in graph_links
            }
            # ⚡ Bolt: Replace slow itertuples() and getattr() with fast native dictionary iteration
            for rel in related.to_dict("records"):
                _rel_full      = str(rel.get("full_name", ""))
                _rel_name      = _html.escape(str(rel.get("table_name", "")))
                _rel_raw_badge = str(rel.get("relationship", ""))
                _rel_badge = (
                    t("detail.same_schema") if _rel_raw_badge == "Same schema"
                    else t("detail.shared_column") if _rel_raw_badge == "Shared column"
                    else _html.escape(_rel_raw_badge)
                )
                if _rel_full not in existing_node_ids:
                    existing_node_ids.add(_rel_full)
                    graph_nodes.append({"id": _rel_full, "label": _rel_name, "current": False, "relationship": _rel_badge})

                link_pair = (full_name, _rel_full) if full_name < _rel_full else (_rel_full, full_name)
                if link_pair not in existing_links:
                    existing_links.add(link_pair)
                    graph_links.append({"from": full_name, "to": _rel_full})

        _lin_hdr_col, _lin_btn_col = st.columns([11, 1])
        with _lin_hdr_col:
            st.markdown(
                f'<div class="dd-section-header">'
                f'<span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_lineage")} & {t("detail.section_related")}</span>'
                f'<span class="dd-section-count">{t("detail.related_count", formatted_count=format_number(n_related))}</span>'
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
            # ⚡ Bolt: Replace slow itertuples() and getattr() with fast native dictionary iteration
            for i, rel in enumerate(related.to_dict("records")):
                with _cols[i % 3]:
                    _rel_full      = str(rel.get("full_name", ""))
                    _rel_name      = _html.escape(str(rel.get("table_name", "")))
                    _rel_sch       = _html.escape(f"{rel.get('catalog_name', '')}.{rel.get('schema_name', '')}")
                    _rel_raw_badge = str(rel.get("relationship", ""))
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

    try:
        _all_tables = get_authorized_tables(query_groups)
        _auth_full_names = set(_all_tables["full_name"].unique()) if _all_tables is not None and not _all_tables.empty else set()
    except Exception as e:
        logging.error("Error querying authorized tables: %s", e, exc_info=True)
        _all_tables = None
        _auth_full_names = set()

    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t('search.eyebrow')}</div>
      <h1>{t('search.hero_title')}</h1>
      <p class="lead">{t('search.hero_subtitle')}</p>
    </div>
    ''', unsafe_allow_html=True)

    with st.expander(t("help.search_expander")):
        _help = t("help.search_content")
        if is_power_user():
            _help += "\n\n" + t("help.search_extra_editor")
        if is_admin():
            _help += "\n\n" + t("help.search_extra_admin")
        st.markdown(_help)

    if "dd_search_override" in st.session_state:
        _over_q = st.session_state.pop("dd_search_override")
        st.session_state["catalog_search"] = _over_q
        st.session_state["_dd_current_search_query"] = _over_q
    if "dd_nav_select" in st.session_state:
        _nav_candidate = st.session_state.pop("dd_nav_select")
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
            if st.button(t('common.back_btn'), help=t("help.btn_common_back"), use_container_width=True, type="secondary"):
                st.session_state.pop("group_filter", None)
                st.rerun()

    if _all_tables is None:
        st.error(t("search.load_error"))
        _table_options = []
    elif _all_tables.empty:
        _render_empty_state("🔒", t("search.no_access"))
        _table_options = []
    else:
        _table_options = (
            sorted(_all_tables["table_name"].unique())
            if "table_name" in _all_tables.columns
            else []
        )

    search_query = st.selectbox(
        t("common.search"),
        options=_table_options,
        index=None,
        placeholder=t("search.placeholder"),
        label_visibility="collapsed",
        key="catalog_search",
        help=t("search.start_typing"),
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
        _results_to_show = _gr
        if len(_gr) > 50:
            st.info(t("search.showing_first_50", count=len(_gr)))
            _results_to_show = _gr.head(50)

        st.markdown(
            f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);margin-bottom:12px">'
            f'{t("search.results_count", count=len(_gr))}</p>',
            unsafe_allow_html=True,
        )
        # ⚡ Bolt: Replace slow itertuples() and getattr() with fast native dictionary iteration over pre-computed list of dicts
        for _i, _row in enumerate(_results_to_show.to_dict('records')):
            _fn = str(_row.get("full_name", ""))
            if not _fn or _fn == "nan" or _fn == "None":
                continue
            _gc, _gb = st.columns([5, 1], gap="small", vertical_alignment="top")
            with _gc:
                _render_result_card(_fn, str(_row.get("name") or _row.get("table_name", "")), str(_row.get("description") or ""), "Table", str(_row.get("dq_score") or ""))
            with _gb:
                if st.button(t('search.view_details_btn'), key=f"gview_{_fn}_{_i}", help=t("search.view_details_help"), use_container_width=True):
                    if _fn in _auth_full_names:
                        st.session_state["dd_search_override"] = str(_row.get("name") or _row.get("table_name", ""))
                        st.session_state["dd_nav_select"] = _fn
                        st.rerun()
                    else:
                        st.error(t("detail.unauthorized"))
            st.markdown('<div style="margin-bottom:8px;"></div>', unsafe_allow_html=True)

    if search_query:
        try:
            with st.spinner(t("common.loading")):
                results = search_all_metadata(search_query, query_groups)
            
            # Analytics: Track the search event
            try:
                res_count = len(results) if results is not None else 0
                track_search(SearchEvent(
                    query=search_query,
                    results_count=res_count,
                    user_email=st.session_state.get("user_email", "unknown")
                ))
            except Exception as ae:
                logging.warning("Failed to track search analytics: %s", ae)

            if results is not None and not results.empty:
                # ⚡ Bolt: Use .to_numpy() to skip index alignment overhead
                _table_results = results[results["match_type"].to_numpy() == "Table"] if "match_type" in results.columns else results
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
                    _results_to_show = results
                    if len(results) > 50:
                        st.info(t("search.showing_first_50", count=len(results)))
                        _results_to_show = results.head(50)

                    st.markdown(
                        f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);margin-bottom:12px">'
                        f'{t("search.results_count", count=len(results))}</p>',
                        unsafe_allow_html=True,
                    )
                    # ⚡ Bolt: Replace slow itertuples() and getattr() with fast native dictionary iteration over pre-computed list of dicts
                    for _sr_i, _sr in enumerate(_results_to_show.to_dict('records')):
                        _fn = _s(_sr.get("full_name"))
                        if not _fn or _fn == "nan" or _fn == "None":
                            continue
                        _card_col, _btn_col = st.columns([5, 1], gap="small", vertical_alignment="top")
                        with _card_col:
                            _render_result_card(_fn, _s(_sr.get("name")), _s(_sr.get("description")), _s(_sr.get("match_type")), _s(_sr.get("dq_score", "")))
                        with _btn_col:
                            if st.button(t('search.view_details_btn'), key=f"view_{_fn}_{_sr_i}", help=t("search.view_details_help"), use_container_width=True):
                                if _fn in _auth_full_names:
                                    st.session_state["_dd_sticky_nav"] = _fn
                                    st.rerun()
                                else:
                                    st.error(t("detail.unauthorized"))
                        st.markdown('<div style="margin-bottom:8px;"></div>', unsafe_allow_html=True)

                if _nav_idx is not None:
                    # ⚡ Bolt: Use .to_numpy() to skip index alignment overhead
                    _row     = _table_results[_table_results["table_name"].to_numpy() == _table_names[_nav_idx]].iloc[0]
                    full_name = f"{_row['catalog_name']}.{_row['schema_name']}.{_row['table_name']}"
                    if st.button(t('search.back_to_results_btn'), key="search_back", help=t("search.back_to_results_help")):
                        st.session_state.pop("_dd_sticky_nav", None)
                        st.rerun()
                    _render_detail_panel(_row, full_name, query_groups)
            else:
                _render_empty_state("🔍", t("search.no_results", query=search_query))

        except Exception as e:
            logging.error("Error displaying search results: %s", e, exc_info=True)
            st.error(t("detail.load_error"))
    else:
        st.markdown(
            f'<p style="font-family:var(--font-sans);font-size:15px;color:var(--ink-60);margin-top:8px">'
            f'{t("search.start_typing")}</p>',
            unsafe_allow_html=True,
        )
