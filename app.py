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
from src.pages.search import render_search_page


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
    render_search_page(query_groups)
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
