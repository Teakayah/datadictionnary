from __future__ import annotations

import logging
import streamlit as st
import streamlit.components.v1 as components
from streamlit_js_eval import streamlit_js_eval
import os
import html as _html
from dotenv import load_dotenv
load_dotenv()  # must run before any src.* import so os.getenv() reads .env values

from src.auth import check_auth, is_power_user, is_admin, render_signin_page
from src.ui.header import render_header, render_footer, LOGO_MARK_SVG

# ── Internationalisation (i18n) ───────────────────────────────────────────────
from src.i18n import t



from src.config import (
    CATALOG_CACHE, SCHEMA_CACHE, MAX_BUSINESS_NAME_LEN,
    MOCK_DEPT,
)
# Runtime flags kept as inline reads so per-test env overrides are picked up
# on every AppTest execution without hitting the src.config module cache.
ENABLE_MOCK_AUTH = os.getenv("ENABLE_MOCK_AUTH", "false").lower() == "true"
ENVIRONMENT      = os.getenv("ENVIRONMENT", "production").lower()

st.set_page_config(
    page_title="Data Dictionary",
    page_icon="assets/favicon.png",
    layout="wide",
)

# ── Design system CSS ──────────────────────────────────────────────────────────
from src.ui.css import render_css
render_css()  # inject design-system CSS on every render
from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import (
    _get_write_connection, get_db_connection,
    run_query, get_authorized_tables, search_all_metadata,
    get_column_business_names, get_multi_hop_lineage,
    export_schema_to_csv,
)
from src.config import is_demo_mode
from src.personalization import (
    _pref_upsert, _pref_delete, _sync_prefs_to_session, is_power_user
)
from src.comments import (
    get_table_comments, save_comment
)
from src.audit import (
    save_table_metadata, save_business_name, get_table_steward
)

# render_header, render_footer imported from src.ui.header

# ── Databricks query helper ────────────────────────────────────────────────────
# ── DuckDB local-cache adapter ────────────────────────────────────────────────
# When DUCKDB_PATH points to an existing file (written by the sync job), all
# read queries and app writes are served locally — no network round-trip.
# The adapter translates the existing %(name)s pyformat SQL into DuckDB's
# $name named-parameter style so no query code needs to change.


# _user_oid, _pref_*, _sync_prefs_to_session imported from src.personalization (Phase 7)
# is_admin imported from src.auth (Phase 5)


# export_schema_to_csv imported from src.db.queries


from src.sync.worker import _start_sync_worker_thread, _get_dr_resync_status, _get_last_ui_activity, _set_dr_resync_status, _set_dr_resync_progress, _mark_ui_activity, _run_dr_resync
from src.sync.push import enqueue_sync, enqueue_column_sync, _push_to_databricks, _push_definition_to_databricks, _process_sync_queue
from src.ui.lineage import _build_lineage_graph, _lineage_vis_html, render_lineage_fullscreen



from src.ui.cards import (
    _dq_grade, _compute_live_completeness, render_discovery, render_health, render_admin_page,
    _mark_ui_activity, render_table_metadata_editor, render_data_sample,
)
from src.pages.catalog import render_catalog_browser
from src.pages.glossary import render_glossary


# ── Per-render startup tasks ──────────────────────────────────────────────────
_mark_ui_activity()  # track UI activity for background-worker idle detection

# Start the write-back worker once (daemon thread, no-ops without DuckDB).
if _duckdb_available():
    _start_sync_worker_thread()

# Capture viewport height once per session via JS (returns None on first render).
if "viewport_height" not in st.session_state:
    _vh = streamlit_js_eval(js_expressions="window.innerHeight", key="_dd_vh")
    if _vh:
        st.session_state["viewport_height"] = int(_vh)
else:
    streamlit_js_eval(js_expressions="window.innerHeight", key="_dd_vh")

if ENABLE_MOCK_AUTH and ENVIRONMENT == "development":
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "bookmarks" not in st.session_state:
        st.session_state.bookmarks = set()
    if "col_bookmarks" not in st.session_state:
        st.session_state.col_bookmarks = set()
    if "recent_views" not in st.session_state:
        st.session_state.recent_views = []
    if not st.session_state.get("_prefs_loaded"):
        _sync_prefs_to_session()
        st.session_state["_prefs_loaded"] = True

    # Auto-login from a URL param — used by screenshot scripts and load tests
    if st.query_params.get("mock_login") == "true" and not st.session_state.authenticated:
        _ql_dept = st.query_params.get("mock_dept", MOCK_DEPT).lower()
        _dept_group_map = {
            "finance":  (["finance_group",  "SELECT_ALL_USERS"], "Finance User",  "finance.user@research-org.ca"),
            "research": (["research_group", "SELECT_ALL_USERS"], "Research User", "research.user@research-org.ca"),
            "hr":       (["hr_group",       "SELECT_ALL_USERS"], "HR User",       "hr.user@research-org.ca"),
            "it":       (["it_group",       "SELECT_ALL_USERS"], "IT User",       "it.user@research-org.ca"),
        }
        if _ql_dept in _dept_group_map:
            _ql_groups, _ql_name, _ql_email = _dept_group_map[_ql_dept]
        else:
            _ql_groups = ["finance_group", "research_group", "hr_group", "it_group",
                          "SELECT_ALL_USERS", "finance_dept_id", "all_employees_id"]
            _ql_name, _ql_email = "Admin User", "admin@research-org.ca"
        st.session_state.authenticated = True
        st.session_state.user_groups   = _ql_groups
        st.session_state.user_name     = _ql_name
        st.session_state.user_email    = _ql_email

    if not st.session_state.get("authenticated"):
        st.html(f'''
<div class="dd-header">
  <div class="dd-header-inner">
    <span class="dd-logo-link">
      {LOGO_MARK_SVG}
      <span class="dd-logo-text">Data Dictionary</span>
      <span class="dd-pill">Beta</span>
    </span>
  </div>
</div>
''')
        st.markdown('<div class="dd-page" role="main" aria-live="polite">', unsafe_allow_html=True)
        render_signin_page(mock=True)
        st.markdown("</div>", unsafe_allow_html=True)
        render_footer()
        st.stop()
else:
    check_auth(sync_prefs_callback=_sync_prefs_to_session)

# ── Authenticated: header with user ───────────────────────────────────────────
current_tab = st.query_params.get("tab", "search")
render_header(user_name=st.session_state.get("user_name", ""), active_tab=current_tab, show_admin=is_admin())
st.markdown('<div class="dd-page" role="main" aria-live="polite">', unsafe_allow_html=True)

groups = tuple(st.session_state.get("user_groups", [])) if st.session_state.get("user_groups") else ("none",)
active_group = st.session_state.get("group_filter")
query_groups = (active_group,) if active_group else groups


# Detect tab change — clear transient state so edits don't bleed across tabs
_prev_tab = st.session_state.get("_dd_current_tab")
if _prev_tab is not None and _prev_tab != current_tab:
    st.session_state.pop("dd_col_edit_mode", None)
    for k in [k for k in st.session_state if str(k).startswith("dd_comment_open_")]:
        del st.session_state[k]
st.session_state["_dd_current_tab"] = current_tab

if current_tab == "search":
    # --- START SEARCH PAGE --- eyebrow: § Catalog search
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
        # Permission gate: only promote to sticky nav if the user is authorized for this table.
        # get_authorized_tables is @st.cache_data so this call is free (already cached).
        try:
            _auth_df = get_authorized_tables(query_groups)
            _auth_full_names = set(_auth_df["full_name"].tolist()) if _auth_df is not None and not _auth_df.empty else set()
        except Exception:
            _auth_full_names = set()
        if _nav_candidate in _auth_full_names:
            # Promote to sticky so locale changes and star clicks don't lose the full-name anchor
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
            if st.button(t("common.back"), use_container_width=True):
                st.session_state.pop("group_filter", None)
                st.rerun()

    try:
        _all_tables = get_authorized_tables(query_groups)
        if _all_tables is not None and not _all_tables.empty and 'table_name' in _all_tables.columns:
            _table_options = sorted(_all_tables['table_name'].unique().tolist())
        else:
            _table_options = []
    except Exception as e:
        import logging
        logging.error("Error querying data: %s", e, exc_info=True)
        st.error(t("search.load_error"))
        _all_tables = None
        _table_options = []

    search_query = st.selectbox(
        t("common.search"),
        options=_table_options,
        index=None,
        placeholder=t("search.placeholder"),
        label_visibility="collapsed",
        key="catalog_search",
    )

    # Detect selection change — clear transient state and sticky nav anchor
    _prev_query = st.session_state.get("_dd_current_search_query")
    if _prev_query is not None and _prev_query != search_query:
        st.session_state.pop("dd_col_edit_mode", None)
        for k in [k for k in st.session_state if str(k).startswith("dd_comment_open_")]:
            del st.session_state[k]
        st.session_state.pop("_dd_sticky_nav", None)
    st.session_state["_dd_current_search_query"] = search_query

    # When a group filter is active but no search term, show all tables for that group
    if active_group and not search_query and _all_tables is not None and not _all_tables.empty:
        _group_results = _all_tables.copy()
        if "match_type" not in _group_results.columns:
            _group_results["match_type"] = "Table"
        if "name" not in _group_results.columns:
            _group_results["name"] = _group_results["table_name"]
        if "description" not in _group_results.columns:
            _desc_col = "table_description" if "table_description" in _group_results.columns else "comment" if "comment" in _group_results.columns else None
            _group_results["description"] = _group_results[_desc_col] if _desc_col else ""
        st.markdown(f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);margin-bottom:12px">{len(_group_results)} {t("search.results_count") if len(_group_results) != 1 else "table"}</p>', unsafe_allow_html=True)
        for _gr_i, (_, _gr) in enumerate(_group_results.iterrows()):
            _gr_name = str(_gr.get("name") or _gr.get("table_name", ""))
            _gr_full = str(_gr.get("full_name", ""))
            _gr_desc = str(_gr.get("description", "") or "")
            if not _gr_full:
                continue
            _gr_dq_score = str(_gr.get("dq_score", "") or "")
            _gr_grade, _gr_gcls = _dq_grade(_gr_dq_score)
            _gc, _gb = st.columns([5, 1], gap="small", vertical_alignment="top")
            with _gc:
                st.markdown(f'''
                <div style="background:var(--paper); border:1px solid var(--ink-10); border-radius:4px; padding:14px 18px;">
                    <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
                        <span class="dd-dq-badge {_gr_gcls}" title="Completeness grade {_gr_grade}">{_gr_grade}</span>
                        <span style="font-family:var(--font-mono); font-size:11px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.08em;">Table</span>
                    </div>
                    <div style="font-family:var(--font-sans); font-size:15px; font-weight:600; color:var(--ink); margin-bottom:2px;">{_html.escape(_gr_name)}</div>
                    <div style="font-family:var(--font-mono); font-size:11px; color:var(--ink-60); margin-bottom:6px;">{_html.escape(_gr_full)}</div>
                    <p style="font-family:var(--font-sans); font-size:13px; color:var(--ink-60); line-height:1.5; margin:0;">{_html.escape(_gr_desc)}</p>
                </div>''', unsafe_allow_html=True)
            with _gb:
                if st.button(f"{t('search.view_details')} →", key=f"gview_{_gr_full}_{_gr_i}", use_container_width=True):
                    # Permission gate: verify access before setting sticky nav
                    _auth_df = get_authorized_tables(query_groups)
                    _allowed = set(_auth_df["full_name"].tolist()) if _auth_df is not None and not _auth_df.empty else set()
                    if _gr_full in _allowed:
                        st.session_state["dd_search_override"] = _gr_name
                        st.session_state["dd_nav_select"] = _gr_full
                        st.rerun()
                    else:
                        st.error(t("detail.unauthorized"))
            st.markdown('<div style="margin-bottom:8px;"></div>', unsafe_allow_html=True)

    if search_query:
        try:
            results = search_all_metadata(search_query, query_groups)
            if results is not None and not results.empty:
                # Show table detail panel for table-type matches
                _table_results = results[results["match_type"] == "Table"] if "match_type" in results.columns else results
                _table_names = _table_results["table_name"].tolist()
                # Use sticky nav (persists across locale/star reruns); cleared on manual search change
                _nav_target  = st.session_state.get("_dd_sticky_nav")
                _nav_idx = None
                if _nav_target:
                    _nav_name = _nav_target.split(".")[-1]
                    if _nav_name in _table_names:
                        _nav_idx = _table_names.index(_nav_name)

                if _nav_idx is None:
                    import pandas as _pd
                    def _s(v):
                        return "" if _pd.isna(v) else str(v)
                    # No selection yet — show clickable result cards
                    st.markdown(f'<p style="font-family:var(--font-sans);font-size:13px;color:var(--ink-60);margin-bottom:12px">{len(results)} matches</p>', unsafe_allow_html=True)
                    for _sr_i, (_, _sr) in enumerate(results.iterrows()):
                        _sr_type = _s(_sr.get("match_type"))
                        _sr_name = _s(_sr.get("name"))
                        _sr_full = _s(_sr.get("full_name"))
                        _sr_desc = _s(_sr.get("description"))
                        _sr_dq   = _s(_sr.get("dq_score", ""))
                        if not _sr_full:
                            continue
                        _sr_grade, _sr_gcls = _dq_grade(_sr_dq)
                        _card_col, _btn_col = st.columns([5, 1], gap="small", vertical_alignment="top")
                        with _card_col:
                            st.markdown(f'''
                            <div style="background:var(--paper); border:1px solid var(--ink-10); border-radius:4px; padding:14px 18px; height:100%;">
                                <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
                                    <span class="dd-dq-badge {_sr_gcls}" title="Completeness grade {_sr_grade}">{_sr_grade}</span>
                                    <span style="font-family:var(--font-mono); font-size:11px; color:var(--ink-60); text-transform:uppercase; letter-spacing:0.08em;">{_html.escape(_sr_type)}</span>
                                </div>
                                <div style="font-family:var(--font-sans); font-size:15px; font-weight:600; color:var(--ink); margin-bottom:2px;">{_html.escape(_sr_name)}</div>
                                <div style="font-family:var(--font-mono); font-size:11px; color:var(--ink-60); margin-bottom:6px;">{_html.escape(_sr_full)}</div>
                                <p style="font-family:var(--font-sans); font-size:13px; color:var(--ink-60); line-height:1.5; margin:0;">{_html.escape(_sr_desc)}</p>
                            </div>
                            ''', unsafe_allow_html=True)
                        with _btn_col:
                            if st.button(f"{t('search.view_details')} →", key=f"view_{_sr_full}_{_sr_i}", use_container_width=True):
                                # Permission gate
                                _auth_df = get_authorized_tables(query_groups)
                                _allowed = set(_auth_df["full_name"].tolist()) if _auth_df is not None and not _auth_df.empty else set()
                                if _sr_full in _allowed:
                                    st.session_state["_dd_sticky_nav"] = _sr_full
                                    st.rerun()
                                else:
                                    st.error(t("detail.unauthorized"))
                        st.markdown('<div style="margin-bottom:8px;"></div>', unsafe_allow_html=True)

                if _nav_idx is not None:
                    selected_table = _table_names[_nav_idx]
                    # Make sure we use an exact match
                    row = _table_results[_table_results["table_name"] == selected_table].iloc[0]
                    full_name = f"{row['catalog_name']}.{row['schema_name']}.{row['table_name']}"
                    if st.button(f"← {t('search.back_to_results')}", key="search_back"):
                        st.session_state.pop("_dd_sticky_nav", None)
                        st.rerun()
                    col_main_detail, col_side_detail = st.columns([7, 5], gap="large")
                    with col_main_detail:
                        _cat, _sch, _tbl = _html.escape(str(row['catalog_name'])), _html.escape(str(row['schema_name'])), _html.escape(str(row['table_name']))
                        _raw_desc = row.get('table_description', '')
                        _desc = _html.escape(str(_raw_desc) if isinstance(_raw_desc, str) else '')
                        _host = os.getenv("DATABRICKS_HOST", "").strip()
                        _ext_link = f'<a href="https://{_host}/explore/data/{_cat}/{_sch}/{_tbl}" target="_blank" class="dd-link-external">{t("table.open_in_databricks")} ↗</a>' if _host else ''

                        # Section header
                        st.markdown(f'<div class="dd-detail-header" style="margin-top: 0;"><span class="dd-eyebrow" style="margin-bottom:0">{t("detail.title")}</span></div>', unsafe_allow_html=True)

                        # --- § Completeness grade (computed before identity block) ---
                        # Live score: session_state cache keyed by table, invalidated on column Save.
                        _live_score_key = f"_live_completeness_{full_name}"
                        if _live_score_key not in st.session_state:
                            _fallback = float(str(row.get("dq_score", "") or 0) or 0)
                            try:
                                st.session_state[_live_score_key] = _compute_live_completeness(full_name) or _fallback
                            except Exception:
                                st.session_state[_live_score_key] = _fallback
                        _detail_score_num = float(st.session_state[_live_score_key])
                        _detail_grade, _detail_gcls = _dq_grade(_detail_score_num)

                        # Table identity block — grade badge floated far-right on table name line
                        _steward = str(row.get("steward_email", ""))
                        st.markdown(
                            f'<div class="dd-eyebrow" style="margin-bottom:4px">{_cat} · {_sch}</div>'
                            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                            f'<div class="dd-detail-table-name" style="margin-bottom:0">{_tbl}</div>'
                            f'<div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">'
                            f'<span class="dd-dq-badge {_detail_gcls}" style="width:32px;height:32px;font-size:14px;" title="Completeness {_detail_score_num:.0f}/100">{_detail_grade}</span>'
                            f'<span style="font-family:var(--font-mono);font-size:13px;color:var(--ink-60);">{_detail_score_num:.0f}%</span>'
                            f'</div>'
                            f'</div>'
                            f'<p class="dd-detail-desc">{_desc}</p>{_ext_link}',
                            unsafe_allow_html=True,
                        )

                        if is_power_user():
                           if st.button(f"✎ {t('detail.edit_table')}", key=f"edit_tbl_{full_name}", type="secondary"):
                               render_table_metadata_editor(full_name, _raw_desc, _steward)

                        # --- § Bookmark (star) + full_name — side by side ---
                        _is_bookmarked = full_name in st.session_state.get("bookmarks", set())
                        _c_code, _c_bk = st.columns([11, 1], gap="small")
                        with _c_code:
                            st.code(full_name, language=None)
                        with _c_bk:
                            if st.button("★" if _is_bookmarked else "☆", key=f"bk_{full_name}", use_container_width=True):
                                if _is_bookmarked:
                                    st.session_state.get("bookmarks", set()).discard(full_name)
                                    _pref_delete(full_name, "bookmark")
                                else:
                                    st.session_state.get("bookmarks", set()).add(full_name)
                                    _pref_upsert(full_name, "bookmark")
                                st.rerun()

                        # Record this table as recently viewed
                        _rv = st.session_state.get("recent_views", [])
                        if not _rv or _rv[0] != full_name:
                            _rv = [full_name] + [x for x in _rv if x != full_name][:49]
                            st.session_state.recent_views = _rv
                            _pref_upsert(full_name, "recent")

                        # --- § Data preview + export dictionary ---
                        # Bulk-fetch overrides first (one query for all columns)
                        col_overrides = get_column_business_names(full_name)

                        cols_query = ("SELECT column_name, data_type, comment FROM {0}.{1}.columns_metadata WHERE table_full_name = %(table_full_name)s ORDER BY column_name").format(CATALOG_CACHE, SCHEMA_CACHE)
                        cols = run_query(cols_query, {"table_full_name": full_name})
                        n_cols = len(cols) if cols is not None and not cols.empty else 0

                        _c_preview, _c_export = st.columns(2, gap="small")
                        with _c_preview:
                            if st.button(t("detail.preview_data"), key=f"preview_{full_name}", use_container_width=True):
                                render_data_sample(full_name)
                        with _c_export:
                            if n_cols > 0:
                                csv_data = export_schema_to_csv(cols, col_overrides)
                                st.download_button(
                                    label=t("detail.export_dictionary"),
                                    data=csv_data,
                                    file_name=f"{row['catalog_name']}_{row['schema_name']}_{row['table_name']}_schema.csv",
                                    mime="text/csv",
                                    key=f"export_{full_name}",
                                    use_container_width=True,
                                )

                        # --- § Columns ---
                        st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_columns")}</span><span class="dd-section-count">{n_cols}</span></div>', unsafe_allow_html=True)


                        _power = is_power_user()
                        _col_edit = st.session_state.get("dd_col_edit_mode", "")

                        if n_cols > 0:
                            for _, c in cols.iterrows():
                                _cname    = str(c.get("column_name", ""))
                                _ctype    = str(c.get("data_type", ""))
                                _ccomment = str(c.get("comment") or "")
                                _edit_key = f"{full_name}__{_cname}"
                                _override   = col_overrides.get(_cname, {})
                                _col_biz    = _override.get("business_name", "")
                                _col_def    = _override.get("definition", "")

                                st.markdown('<hr class="dd-col-divider">', unsafe_allow_html=True)
                                _r_name, _r_type, _r_desc, _r_btn, _r_star = st.columns([3, 2, 4, 1, 1], gap="small")

                                # Name cell: business name above, technical name faded below
                                if _col_biz:
                                    _r_name.markdown(
                                        f'<span class="dd-col-biz-name">{_html.escape(_col_biz)}</span>'
                                        f'<span class="dd-col-tech-sub">{_html.escape(_cname)}</span>',
                                        unsafe_allow_html=True,
                                    )
                                else:
                                    _r_name.markdown(f'<span class="dd-col-name">{_html.escape(_cname)}</span>', unsafe_allow_html=True)

                                _r_type.markdown(f'<span class="dd-col-type">{_html.escape(_ctype)}</span>', unsafe_allow_html=True)

                                # Desc cell: business definition above, system comment faded below
                                if _col_def:
                                    _r_desc.markdown(
                                        f'<span class="dd-col-desc">{_html.escape(_col_def)}</span>'
                                        f'<span class="dd-col-desc-faded">{_html.escape(_ccomment)}</span>',
                                        unsafe_allow_html=True,
                                    )
                                else:
                                    _r_desc.markdown(f'<span class="dd-col-desc">{_html.escape(_ccomment)}</span>', unsafe_allow_html=True)

                                if _power and _col_edit != _edit_key:
                                    if _r_btn.button("✎", key=f"col_edit_{_edit_key}", use_container_width=True):
                                        st.session_state["dd_col_edit_mode"] = _edit_key
                                        st.rerun()

                                # Column bookmark star
                                _col_bk_id = f"{full_name}::{_cname}"
                                _is_col_bk = _col_bk_id in st.session_state.get("col_bookmarks", set())
                                if _r_star.button("★" if _is_col_bk else "☆", key=f"colbk_{_edit_key}", use_container_width=True):
                                    if _is_col_bk:
                                        st.session_state.get("col_bookmarks", set()).discard(_col_bk_id)
                                        _pref_delete(_col_bk_id, "col_bookmark")
                                    else:
                                        st.session_state.get("col_bookmarks", set()).add(_col_bk_id)
                                        _pref_upsert(_col_bk_id, "col_bookmark")
                                    st.rerun()

                                if _col_edit == _edit_key:
                                    st.markdown('<div class="dd-edit-banner">Edit mode — changes are saved immediately and visible to all users.</div>', unsafe_allow_html=True)
                                    _inp_name = st.text_input(
                                        "Business name",
                                        value=_col_biz,
                                        placeholder="e.g. Customer ID",
                                        max_chars=None if os.getenv("TESTING_NO_MAX_CHARS") else MAX_BUSINESS_NAME_LEN,
                                        key=f"col_biz_name_{_edit_key}",
                                    )
                                    _inp_def = st.text_input(
                                        "Definition",
                                        value=_col_def,
                                        placeholder="e.g. Unique identifier assigned to each customer at registration.",
                                        max_chars=None if os.getenv("TESTING_NO_MAX_CHARS") else MAX_BUSINESS_NAME_LEN,
                                        key=f"col_biz_def_{_edit_key}",
                                    )
                                    _sc, _cc, _ = st.columns([2, 2, 4], gap="small")
                                    with _sc:
                                        if st.button("Save", key=f"col_biz_save_{_edit_key}", use_container_width=True):
                                            try:
                                                save_business_name(full_name, _cname, _inp_name.strip(), _inp_def.strip())
                                                st.session_state.pop("dd_col_edit_mode", None)
                                                # Invalidate live completeness so badge recomputes on next render
                                                st.session_state.pop(f"_live_completeness_{full_name}", None)
                                                st.rerun()
                                            except PermissionError:
                                                st.error("You do not have permission to edit business names.")
                                            except ValueError as exc:
                                                st.error(str(exc))
                                            except Exception as exc:
                                                logging.error("Save failed for %s.%s: %s", full_name, _cname, exc, exc_info=True)
                                                st.error(f"Save failed: {exc}")
                                    with _cc:
                                        if st.button("Cancel", key=f"col_biz_cancel_{_edit_key}", use_container_width=True):
                                            st.session_state.pop("dd_col_edit_mode", None)
                                            st.rerun()
                                    if _override.get("edited_by"):
                                        st.markdown(
                                            f'<div class="dd-biz-audit">Last edited by {_html.escape(_override["edited_by"])} · {_html.escape(str(_override.get("edited_at", "")))}</div>',
                                            unsafe_allow_html=True,
                                        )
                        else:
                            st.markdown('<p style="font-size:13px;color:var(--ink-40);padding:12px 0">No columns recorded.</p>', unsafe_allow_html=True)

                        # --- § Comments ---
                        _steward      = get_table_steward(full_name)
                        _comments     = get_table_comments(full_name)
                        _n_comments   = sum(1 + len(_c.get("replies", [])) for _c in _comments)
                        _comment_open = f"dd_comment_open_{full_name}"
                        # --- § Comments ---
                        st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_comments")}</span><span class="dd-section-count">{_n_comments}</span></div>', unsafe_allow_html=True)

                        def _render_comment_form(key_suffix: str, parent_comment_id: str = None, parent_author_email: str = "") -> None:
                            """Render a text-area + Send/Cancel for a new comment or reply."""
                            _open_key = f"dd_comment_open_{key_suffix}"
                            if not st.session_state.get(_open_key):
                                _label = t("comment.reply") if parent_comment_id else t("comment.leave_a_comment")
                                if st.button(_label, key=f"dd_comment_btn_{key_suffix}"):
                                    st.session_state[_open_key] = True
                                    st.rerun()
                            else:
                                _placeholder = "Write a reply…" if parent_comment_id else "Ask a question or flag an issue about this table."
                                _inp = st.text_area(
                                    "Your comment" if not parent_comment_id else "Your reply",
                                    placeholder=_placeholder,
                                    max_chars=1000,
                                    key=f"dd_comment_text_{key_suffix}",
                                )
                                _cs, _cc, _ = st.columns([2, 2, 4], gap="small")
                                with _cs:
                                    if st.button("Send", key=f"dd_comment_send_{key_suffix}", use_container_width=True):
                                        if _inp.strip():
                                            save_comment(
                                                "TABLE", full_name, _inp.strip(), _steward,
                                                parent_comment_id=parent_comment_id,
                                                parent_author_email=parent_author_email,
                                            )
                                            st.session_state.pop(_open_key, None)
                                            st.rerun()
                                        else:
                                            st.warning("Comment cannot be empty.")
                                with _cc:
                                    if st.button("Cancel", key=f"dd_comment_cancel_{key_suffix}", use_container_width=True):
                                        st.session_state.pop(_open_key, None)
                                        st.rerun()
                                if not _steward and not parent_comment_id:
                                    st.markdown('<p class="dd-comment-no-steward">No steward configured — comment will be saved but not emailed.</p>', unsafe_allow_html=True)

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
                            # Render replies nested under parent
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
                            # Reply button/form for this parent comment
                            _, _reply_form_col = st.columns([1, 11])
                            with _reply_form_col:
                                _render_comment_form(
                                    key_suffix=f"{full_name}_{_cid}",
                                    parent_comment_id=_cid,
                                    parent_author_email=_cemail,
                                )

                        # Top-level new comment form
                        _render_comment_form(key_suffix=full_name)

                    with col_side_detail:
                        # --- § Group Permissions ---
                        # Only show grant rows for groups the viewer belongs to (or public).
                        # Leaking other groups' access to a Finance user reveals org-wide ACL structure.
                        grants_group_placeholders = ", ".join([f"%(grant_group_{i})s" for i in range(len(query_groups))]) if query_groups else "''"
                        grants_params: dict = {"table_full_name": full_name}
                        for _i, _g in enumerate(query_groups):
                            grants_params[f"grant_group_{_i}"] = _g
                        grants_query = (
                            "SELECT DISTINCT principal, privilege FROM {0}.{1}.permissions_cache "
                            "WHERE table_full_name = %(table_full_name)s "
                            "AND (principal IN ({2}) OR principal = 'SELECT_ALL_USERS') "
                            "ORDER BY principal"
                        ).format(CATALOG_CACHE, SCHEMA_CACHE, grants_group_placeholders)  # nosec B608
                        grants = run_query(grants_query, grants_params)
                        n_grants = len(grants) if grants is not None and not grants.empty else 0
                        st.markdown(f'<div class="dd-section-header" style="margin-top:0"><span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_grants")}</span><span class="dd-section-count">{n_grants}</span></div>', unsafe_allow_html=True)
                        if n_grants > 0:
                            for _, g in grants.iterrows():
                                principal, privilege = str(g.get("principal", "")), str(g.get("privilege", ""))
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
                            st.markdown('<p style="font-size:13px;color:var(--ink-40);padding:12px 0">No grants recorded.</p>', unsafe_allow_html=True)

                        # --- § Lineage (multi-hop BFS, permission-filtered) ---
                        graph_nodes, graph_links = _build_lineage_graph(full_name, _tbl, query_groups, run_query, max_depth=2)

                        # --- § Related tables ---
                        rel_group_placeholders = ", ".join([f"%(group_{i})s" for i in range(len(query_groups))]) if query_groups else "''"
                        rel_params = {"catalog_name": row["catalog_name"], "schema_name": row["schema_name"], "full_name": full_name}
                        if query_groups:
                            for i, group in enumerate(query_groups):
                                rel_params[f"group_{i}"] = group

                        related_query = ("SELECT t.full_name, t.table_name, t.catalog_name, t.schema_name, 'Same schema' AS relationship FROM {0}.{1}.tables_metadata t JOIN {0}.{1}.permissions_cache p ON t.full_name = p.table_full_name WHERE t.catalog_name = %(catalog_name)s AND t.schema_name = %(schema_name)s AND t.full_name != %(full_name)s AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS') UNION SELECT DISTINCT t.full_name, t.table_name, t.catalog_name, t.schema_name, 'Shared column' AS relationship FROM {0}.{1}.columns_metadata c1 JOIN {0}.{1}.columns_metadata c2 ON c1.column_name = c2.column_name JOIN {0}.{1}.tables_metadata t ON c2.table_full_name = t.full_name JOIN {0}.{1}.permissions_cache p ON t.full_name = p.table_full_name WHERE c1.table_full_name = %(full_name)s AND c2.table_full_name != %(full_name)s AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS') LIMIT 12").format(CATALOG_CACHE, SCHEMA_CACHE, rel_group_placeholders)  # nosec B608
                        related = run_query(related_query, rel_params)
                        n_related = len(related) if related is not None and not related.empty else 0

                        # Merge related tables into graph
                        if n_related > 0:
                            for _, rel in related.iterrows():
                                _rel_full = str(rel.get("full_name", ""))
                                _rel_name = _html.escape(str(rel.get("table_name", "")))
                                _rel_raw_badge = str(rel.get("relationship", ""))
                                _rel_badge = t("detail.same_schema") if _rel_raw_badge == "Same schema" else (t("detail.shared_column") if _rel_raw_badge == "Shared column" else _html.escape(_rel_raw_badge))
                                if not any(n["id"] == _rel_full for n in graph_nodes):
                                    graph_nodes.append({"id": _rel_full, "label": _rel_name, "current": False, "relationship": _rel_badge})
                                if not any((l["from"] == full_name and l["to"] == _rel_full) or (l["from"] == _rel_full and l["to"] == full_name) for l in graph_links):
                                    graph_links.append({"from": full_name, "to": _rel_full})

                        # Section header + expand button
                        _lin_hdr_col, _lin_btn_col = st.columns([11, 1])
                        with _lin_hdr_col:
                            st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_lineage")} & {t("detail.section_related")}</span><span class="dd-section-count">{n_related} {t("detail.related_count")}</span></div>', unsafe_allow_html=True)
                        with _lin_btn_col:
                            if st.button("⤢", key=f"expand_lin_{full_name}", help="Expand lineage graph", use_container_width=True):
                                render_lineage_fullscreen(graph_nodes, graph_links, full_name)

                        graph_html = _lineage_vis_html(graph_nodes, graph_links, height=350)
                        components.html(graph_html, height=380)

                        if n_related > 0:
                            st.markdown('<div style="margin-top: 16px;"></div>', unsafe_allow_html=True)
                            _cols = st.columns(min(3, n_related), gap="small")
                            for i, (_, rel) in enumerate(related.iterrows()):
                                with _cols[i % 3]:
                                    _rel_full, _rel_name, _rel_sch, _rel_raw_badge = str(rel.get("full_name", "")), _html.escape(str(rel.get("table_name", ""))), _html.escape(f"{rel.get('catalog_name','')}.{rel.get('schema_name','')}"), str(rel.get("relationship", ""))
                                    _rel_badge = t("detail.same_schema") if _rel_raw_badge == "Same schema" else (t("detail.shared_column") if _rel_raw_badge == "Shared column" else _html.escape(_rel_raw_badge))
                                    st.markdown(f'<div class="dd-related-card"><div class="dd-related-badge">{_rel_badge}</div><div class="dd-related-name">{_rel_name}</div><div class="dd-related-schema">{_rel_sch}</div></div>', unsafe_allow_html=True)
                                    if st.button(t("detail.open_related"), key=f"rel_{_rel_full}", type="secondary", use_container_width=True):
                                        st.session_state["dd_search_override"] = str(rel.get("table_name", ""))
                                        st.session_state["dd_nav_select"] = _rel_full
                                        st.rerun()

        except Exception as e:
            logging.error("Error displaying search results: %s", e, exc_info=True)
            st.error(t("detail.load_error"))
    else:
        st.markdown('<p style="font-family:var(--font-sans);font-size:15px;color:var(--ink-60);margin-top:8px">Start typing to search the catalog.</p>', unsafe_allow_html=True)
    # --- END SEARCH PAGE ---

elif current_tab == "catalog":
    render_catalog_browser(query_groups, get_authorized_tables)
elif current_tab == "glossary":
    render_glossary(query_groups)
elif current_tab == "discovery":
    render_discovery(query_groups, get_authorized_tables, _pref_delete, _pref_upsert)
elif current_tab == "health":
    render_health(query_groups, get_authorized_tables)
elif current_tab == "admin":
    render_admin_page()

st.markdown("</div>", unsafe_allow_html=True)
render_footer()
