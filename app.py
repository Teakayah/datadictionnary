from __future__ import annotations

import logging
import uuid
import threading
import time
import streamlit as st
import streamlit.components.v1 as components
from streamlit_js_eval import streamlit_js_eval
from databricks import sql
import os
import msal
import html as _html
import secrets
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ── Internationalisation (i18n) ───────────────────────────────────────────────
import json            # used in sync queue (json.dumps/loads)
import json as _json   # alias used in render_header and lineage; keep alongside i18n import
from src.i18n import LOCALES, get_locale, _ensure_locale, t, set_locale

# ── Demo data (returned in mock/dev mode instead of hitting Databricks) ────────
_DEMO_TABLES = pd.DataFrame({
    "full_name":         ["main.analytics.customers", "main.analytics.orders",
                          "main.analytics.transactions", "main.staging.raw_events"],
    "catalog_name":      ["main", "main", "main", "main"],
    "schema_name":       ["analytics", "analytics", "analytics", "staging"],
    "table_name":        ["customers", "orders", "transactions", "raw_events"],
    "table_description": [
        "Deduplicated customer master — one row per customer_id.",
        "Orders with customer foreign key reference.",
        "Transaction-level detail enriched with customer data.",
        "Raw event stream ingested from upstream systems.",
    ],
    "table_type":        ["MANAGED", "MANAGED", "EXTERNAL", "EXTERNAL"],
    "updated_at":        [pd.Timestamp.now() - pd.Timedelta(days=1), 
                          pd.Timestamp.now() - pd.Timedelta(hours=5),
                          pd.Timestamp.now() - pd.Timedelta(minutes=30),
                          pd.Timestamp.now() - pd.Timedelta(days=3)],
})

_DEMO_COLUMNS = {
    "main.analytics.customers": pd.DataFrame({
        "column_name": ["customer_id", "email", "segment", "created_at"],
        "data_type":   ["BIGINT", "STRING", "STRING", "TIMESTAMP"],
        "comment":     ["Primary key.", "Customer email address.",
                        "Marketing segment label.", "Account creation timestamp."],
    }),
    "main.analytics.orders": pd.DataFrame({
        "column_name": ["order_id", "customer_id", "amount", "order_date"],
        "data_type":   ["BIGINT", "BIGINT", "DECIMAL(18,2)", "DATE"],
        "comment":     ["Unique order identifier.", "FK to customers.customer_id.",
                        "Order total in USD.", "Date the order was placed."],
    }),
    "main.analytics.transactions": pd.DataFrame({
        "column_name": ["transaction_id", "order_id", "customer_id", "amount", "type"],
        "data_type":   ["BIGINT", "BIGINT", "BIGINT", "DECIMAL(18,2)", "STRING"],
        "comment":     ["Transaction PK.", "FK to orders.", "FK to customers.",
                        "Transaction amount.", "DEBIT or CREDIT."],
    }),
    "main.staging.raw_events": pd.DataFrame({
        "column_name": ["event_id", "customer_id", "event_type", "ts"],
        "data_type":   ["STRING", "BIGINT", "STRING", "TIMESTAMP"],
        "comment":     ["Unique event identifier.", "Customer associated with event.",
                        "Event classification (click, view, purchase).", "Event timestamp."],
    }),
}

_DEMO_GRANTS = {
    "main.analytics.customers": pd.DataFrame({
        "principal": ["finance_dept_id", "all_employees_id", "SELECT_ALL_USERS"],
        "privilege":  ["SELECT",          "SELECT",           "SELECT"],
    }),
    "main.analytics.orders": pd.DataFrame({
        "principal": ["finance_dept_id", "SELECT_ALL_USERS"],
        "privilege":  ["SELECT",          "SELECT"],
    }),
    "main.analytics.transactions": pd.DataFrame({
        "principal": ["finance_dept_id"],
        "privilege":  ["SELECT"],
    }),
    "main.staging.raw_events": pd.DataFrame({
        "principal": ["all_employees_id"],
        "privilege":  ["SELECT"],
    }),
}

_DEMO_LINEAGE = {
    "main.analytics.customers": pd.DataFrame({
        "direction":        ["UPSTREAM", "UPSTREAM",                  "DOWNSTREAM"],
        "entity_full_name": ["main.staging.raw_events",
                             "main.bronze.customer_raw",              # not in authorized set → locked node
                             "main.analytics.orders"],
        "entity_type":      ["TABLE",    "TABLE",                     "TABLE"],
    }),
    "main.analytics.orders": pd.DataFrame({
        "direction":        ["UPSTREAM",                    "DOWNSTREAM"],
        "entity_full_name": ["main.analytics.customers",   "main.analytics.transactions"],
        "entity_type":      ["TABLE",                       "TABLE"],
    }),
    "main.analytics.transactions": pd.DataFrame({
        "direction":        ["UPSTREAM"],
        "entity_full_name": ["main.analytics.orders"],
        "entity_type":      ["TABLE"],
    }),
    "main.staging.raw_events": pd.DataFrame(
        columns=["direction", "entity_full_name", "entity_type"]
    ),
}

_DEMO_RELATED = {
    "main.analytics.customers": pd.DataFrame({
        "full_name":    ["main.analytics.orders",     "main.analytics.transactions"],
        "table_name":   ["orders",                    "transactions"],
        "catalog_name": ["main",                      "main"],
        "schema_name":  ["analytics",                 "analytics"],
        "relationship": ["Same schema",               "Shared column"],
    }),
    "main.analytics.orders": pd.DataFrame({
        "full_name":    ["main.analytics.customers",  "main.analytics.transactions"],
        "table_name":   ["customers",                 "transactions"],
        "catalog_name": ["main",                      "main"],
        "schema_name":  ["analytics",                 "analytics"],
        "relationship": ["Same schema",               "Same schema"],
    }),
    "main.analytics.transactions": pd.DataFrame({
        "full_name":    ["main.analytics.customers",  "main.analytics.orders"],
        "table_name":   ["customers",                 "orders"],
        "catalog_name": ["main",                      "main"],
        "schema_name":  ["analytics",                 "analytics"],
        "relationship": ["Shared column",             "Same schema"],
    }),
    "main.staging.raw_events": pd.DataFrame(
        columns=["full_name", "table_name", "catalog_name", "schema_name", "relationship"]
    ),
}

_DEMO_GLOSSARY = pd.DataFrame({
    "term": ["Churn Rate", "Customer Lifetime Value (CLV)", "Monthly Recurring Revenue (MRR)", "Active User"],
    "definition": [
        "The percentage of customers who stop using your product or service during a given time period.",
        "The total amount of money a customer is expected to spend with your business during their lifetime.",
        "The total amount of predictable revenue that a company expects to receive every month.",
        "A user who has performed at least one meaningful action within the product in the last 30 days."
    ],
    "calculation": [
        "(Customers lost during period / Total customers at start of period) * 100",
        "Average Purchase Value * Average Purchase Frequency * Average Customer Lifespan",
        "Sum of all subscription revenues from active customers in a month",
        "COUNT(DISTINCT user_id) WHERE last_action_ts >= CURRENT_DATE - INTERVAL 30 DAYS"
    ],
    "domain": ["Sales & Marketing", "Finance", "Finance", "Product"],
    "steward": ["Jane Doe (Marketing)", "John Smith (Finance)", "John Smith (Finance)", "Alice Wong (Product)"],
    "related_tables": [
        ["main.analytics.customers", "main.analytics.orders"],
        ["main.analytics.customers", "main.analytics.transactions"],
        ["main.analytics.transactions"],
        ["main.staging.raw_events"]
    ]
})

from src.config import (
    TENANT_ID, CLIENT_ID, CLIENT_SECRET, AUTHORITY, REDIRECT_URI, SCOPE,
    CATALOG_CACHE, SCHEMA_CACHE, MAX_BUSINESS_NAME_LEN,
    DUCKDB_PATH, USER_DATA_PATH,
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
from src.ui.css import DESIGN_CSS, VIS_WIDE_CSS, render_css
from src.db.duckdb_adapter import (
    _duckdb_available, _to_duckdb_sql, _get_shared_duckdb_connection,
    _DuckDBCursor, _DuckDBConn, _run_duckdb_query, _db_write_lock,
)
from src.db.databricks_adapter import (
    _get_databricks_connection, _get_databricks_write_connection,
    _run_databricks_query,
)
from src.db.queries import _get_write_connection, get_db_connection

from src.config import is_demo_mode
from src.personalization import (
    _user_oid, _pref_upsert, _pref_delete, _pref_load,
    _sync_prefs_to_session, is_power_user
)
from src.comments import (
    get_table_comments, _build_comment_tree, save_comment,
    send_comment_email, send_reply_email, _fetch_comment_author_email
)
from src.audit import (
    log_audit_event, save_table_metadata, save_business_name, get_table_steward
)

# run_query, get_authorized_tables, search_all_metadata, get_column_business_names,
# get_multi_hop_lineage — defined below in app.py (Phase 4b: deferred until
# _DEMO_* fixtures are moved to src/demo.py to avoid circular re-import)

# ── Logo SVG (inlined) ─────────────────────────────────────────────────────────
LOGO_MARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" height="30">
  <rect x="4.5" y="6.5" width="55" height="51" rx="1" fill="#FAF7F0" stroke="#14110C" stroke-width="1.5"/>
  <line x1="4.5" y1="19" x2="59.5" y2="19" stroke="#14110C" stroke-width="1.25"/>
  <circle cx="11" cy="12.75" r="2.5" fill="#B8362A"/>
  <line x1="10" y1="28" x2="54" y2="28" stroke="#C9C2B4" stroke-width="1.25"/>
  <line x1="10" y1="36" x2="54" y2="36" stroke="#C9C2B4" stroke-width="1.25"/>
  <line x1="10" y1="44" x2="40" y2="44" stroke="#C9C2B4" stroke-width="1.25"/>
</svg>"""

MS_LOGO_SVG = """<svg width="16" height="16" viewBox="0 0 23 23" fill="none">
  <rect x="1" y="1" width="10" height="10" fill="#F25022"/>
  <rect x="12" y="1" width="10" height="10" fill="#7FBA00"/>
  <rect x="1" y="12" width="10" height="10" fill="#00A4EF"/>
  <rect x="12" y="12" width="10" height="10" fill="#FFB900"/>
</svg>"""

SEARCH_ICON_SVG = """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#6B645A" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>
</svg>"""




def render_header(user_name: str | None = None, active_tab: str = "search", show_admin: bool = False):
    _ensure_locale()
    locale = st.session_state.get("locale", "en")

    user_section = ""
    if user_name:
        user_section = f'<span class="dd-nav-sep"></span><span class="dd-nav-user">{_html.escape(user_name)}</span>'

    def link(label, tab_id):
        active = "active" if active_tab == tab_id else ""
        return f'<a href="#" data-tab="{tab_id}" class="dd-nav-tab {active}">{label}</a>'

    admin_link = link(t("nav.admin"), "admin") if show_admin else ""

    en_active = "dd-lang-active" if locale == "en" else ""
    fr_active  = "dd-lang-active" if locale == "fr" else ""
    title_en = t("language.switch_to_en")
    title_fr = t("language.switch_to_fr")
    lang_toggle = f'<span class="dd-nav-sep"></span><span class="dd-lang-toggle" aria-label="Language selector"><a href="#" data-lang="en" class="dd-lang-opt {en_active}" title="{title_en}">EN</a><span class="dd-lang-sep">/</span><a href="#" data-lang="fr" class="dd-lang-opt {fr_active}" title="{title_fr}">FR</a></span>'

    st.html(f'''
<div class="dd-header" lang="{locale}">
  <div class="dd-header-inner">
    <a href="#" data-tab="search" class="dd-logo-link">
      {LOGO_MARK_SVG}
      <span class="dd-logo-text">Data Dictionary</span>
      <span class="dd-pill">Beta</span>
    </a>
    <nav class="dd-nav" role="navigation" aria-label="Main navigation">
      {link(t("nav.search"), "search")}
      {link(t("nav.catalog"), "catalog")}
      {link(t("nav.glossary"), "glossary")}
      {link(t("nav.discovery"), "discovery")}
      {link(t("nav.health"), "health")}
      {admin_link}
      {lang_toggle}
      {user_section}
    </nav>
  </div>
</div>
''')

    # Hidden Streamlit nav/lang proxy buttons — JS clicks these; the container is
    # hidden immediately via CSS :has(#dd-proxy-anchor) so they never flash.
    _tabs = ["search", "catalog", "glossary", "discovery", "health"]
    if show_admin:
        _tabs.append("admin")
    _is_mock = ENABLE_MOCK_AUTH
    with st.container():
        st.markdown('<div id="dd-proxy-anchor"></div>', unsafe_allow_html=True)
        for tab_id in _tabs:
            if st.button(t(f"nav.{tab_id}"), key=f"nav_{tab_id}"):
                st.query_params["tab"] = tab_id
                st.rerun()
        # on_click fires before rerun so render_header() picks up the new locale.
        st.button("LOCALE_EN", key="lang_btn_en", on_click=set_locale, args=("en",))
        st.button("LOCALE_FR", key="lang_btn_fr", on_click=set_locale, args=("fr",))

    # Zero-height iframe: wires nav clicks → hidden Streamlit buttons,
    # and wires language toggle clicks → hidden lang proxy buttons.
    _tab_map = {tid: t(f"nav.{tid}") for tid in _tabs}
    _tab_map_js = _json.dumps(_tab_map)
    _nav_labels_js = _json.dumps(list(_tab_map.values()))

    components.html(f"""
    <div style="display:none;">
    <script>
    (function() {{
        const parentDoc = window.parent.document;
        const NAV_LABELS = {_nav_labels_js};
        const TAB_MAP = {_tab_map_js};
        const iframeId = Math.random().toString(36);

        function wire() {{
            const allBtns = Array.from(parentDoc.querySelectorAll('button'));
            
            // 1. The proxy container is already hidden via CSS (visibility:hidden).
            //    Nothing to do here — btn.click() works on visibility:hidden elements.

            // 2. Wire Navigation
            parentDoc.querySelectorAll('a.dd-nav-tab[data-tab], a.dd-logo-link[data-tab]').forEach(link => {{
                if (link._wired === iframeId) return;
                link._wired = iframeId;
                link.addEventListener('click', function(e) {{
                    e.preventDefault();
                    const tabId = this.getAttribute('data-tab');
                    const localizedLabel = TAB_MAP[tabId];
                    const currentBtns = Array.from(parentDoc.querySelectorAll('button'));
                    const btn = currentBtns.find(b => b.textContent.trim() === localizedLabel);
                    if (btn) btn.click();
                }});
            }});

            // 3. Wire Language
            parentDoc.querySelectorAll('a.dd-lang-opt[data-lang]').forEach(link => {{
                if (link._wired === iframeId) return;
                link._wired = iframeId;
                link.addEventListener('click', function(e) {{
                    e.preventDefault();
                    const lang = this.getAttribute('data-lang').toUpperCase();
                    const currentBtns = Array.from(parentDoc.querySelectorAll('button'));
                    const btn = currentBtns.find(b => b.textContent.trim() === 'LOCALE_' + lang);
                    if (btn) btn.click();
                }});
            }});
        }}

        // Initial wire
        setTimeout(wire, 150);

        // Continuous monitoring for Streamlit rerenders
        const observer = new MutationObserver(() => {{ wire(); }});
        observer.observe(parentDoc.body, {{childList: true, subtree: true}});
    }})();
    </script>
    </div>
    """, height=0)


def render_footer():
    st.markdown(f"""
    <div class="dd-footer">
      <div class="dd-footer-inner">
        <span>{t('footer.built_with')}</span>
        <span>main.data_governance.dictionary_cache</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Authentication helpers ─────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )


def render_signin_page(auth_url: str | None = None, mock: bool = False):
    """Render the editorial two-column sign-in layout."""
    col_hero, col_card = st.columns([1.1, 0.9], gap="large")

    with col_hero:
        st.markdown(f"""
        <div class="dd-signin-hero">
          <div class="dd-eyebrow">§ Business Data Dictionary</div>
          <h1>{t('auth.title')}</h1>
          <p class="lead">{t('auth.subtitle')}</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('<hr class="dd-rule"/>', unsafe_allow_html=True)
        st.markdown("""
        <div class="dd-stats-row">
          <div>
            <div class="dd-stat-n">—</div>
            <div class="dd-stat-l">tables indexed</div>
          </div>
          <div>
            <div class="dd-stat-n">—</div>
            <div class="dd-stat-l">schemas</div>
          </div>
          <div>
            <div class="dd-stat-n">nightly</div>
            <div class="dd-stat-l">sync cadence</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    with col_card:
        st.markdown("""
        <div class="dd-signin-card">
          <div class="dd-eyebrow">Sign in</div>
          <h3>Use your corporate account</h3>
          <p class="body">The catalog is permission-trimmed by Microsoft Entra ID —
          you'll only see data your Unity Catalog grants allow.</p>
        </div>
        """, unsafe_allow_html=True)

        if mock:
            _MOCK_DEPTS = {
                "Finance":  (["finance_group",  "SELECT_ALL_USERS"], "finance.user@research-org.ca"),
                "Research": (["research_group", "SELECT_ALL_USERS"], "research.user@research-org.ca"),
                "HR":       (["hr_group",        "SELECT_ALL_USERS"], "hr.user@research-org.ca"),
                "IT":       (["it_group",        "SELECT_ALL_USERS"], "it.user@research-org.ca"),
                "Admin":    (["finance_group", "research_group", "hr_group", "it_group",
                              "SELECT_ALL_USERS", "finance_dept_id", "all_employees_id"],
                             "admin@research-org.ca"),
            }
            _default_dept = MOCK_DEPT
            _dept_opts = list(_MOCK_DEPTS.keys())
            _dept_sel = st.selectbox(
                "Department",
                _dept_opts,
                index=_dept_opts.index(_default_dept) if _default_dept in _dept_opts else 0,
                label_visibility="collapsed",
            )
            if st.button("Sign in", use_container_width=True, type="primary"):
                _groups, _email = _MOCK_DEPTS[_dept_sel]
                st.session_state.authenticated = True
                st.session_state.user_groups   = _groups
                st.session_state.user_name     = f"{_dept_sel} User"
                st.session_state.user_email    = _email
                st.rerun()
            st.markdown(
                '<p class="dd-meta">Mock authentication — select a department to filter by its grants.</p>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"""
            <a href="{auth_url}" style="
              display:flex;align-items:center;justify-content:center;gap:10px;
              width:100%;padding:14px 18px;font-size:15px;
              background:var(--ink);color:var(--paper);
              border:1px solid var(--ink);border-radius:2px;
              font-family:var(--font-sans);font-weight:500;
              text-decoration:none;box-sizing:border-box;
              transition:background 120ms var(--ease);
            ">{MS_LOGO_SVG} {t('auth.sign_in_button')}</a>
            <p class="dd-meta" style="margin-top:12px">By signing in you agree to the data access policy.</p>
            """, unsafe_allow_html=True)


def check_auth():
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = None

    if st.session_state.get("auth_token") is None:
        msal_app = get_msal_app()
        query_params = st.query_params

        # If a code is present, handle the callback logic first
        if "code" in query_params:
            # Verify the state matches what we expect
            state = query_params.get("state")
            expected_state = st.session_state.get("oauth_state")

            if not state or not expected_state or state != expected_state:
                logging.error("OAuth state mismatch or missing.")
                st.error("Authentication failed: Security verification (state mismatch). Please try again.")
                # Clear the potentially compromised state
                if "oauth_state" in st.session_state:
                    del st.session_state["oauth_state"]
                if "oauth_nonce" in st.session_state:
                    del st.session_state["oauth_nonce"]
                st.stop()

            # The state is valid; proceed with exchanging the code
            expected_nonce = st.session_state.get("oauth_nonce")
            result = msal_app.acquire_token_by_authorization_code(
                query_params["code"], scopes=SCOPE, redirect_uri=REDIRECT_URI, nonce=expected_nonce
            )

            # Clear the state and nonce once it's used
            if "oauth_state" in st.session_state:
                del st.session_state["oauth_state"]
            if "oauth_nonce" in st.session_state:
                del st.session_state["oauth_nonce"]

            if "access_token" in result:
                claims = result.get("id_token_claims", {})
                if expected_nonce and claims.get("nonce") != expected_nonce:
                    logging.error("OAuth nonce mismatch or missing.")
                    st.error("Authentication failed: Security verification (nonce mismatch).")
                    st.stop()

                st.session_state.auth_token = result
                st.session_state.user_groups = claims.get("groups", [])
                st.session_state.user_name   = claims.get("name")
                st.session_state.user_email  = claims.get("email") or claims.get("preferred_username", "")
                st.session_state.user_oid    = claims.get("oid", "")
                # Seed personalization from DuckDB on first real login
                _sync_prefs_to_session()
                st.session_state["_prefs_loaded"] = True
                # Clear query params and rerun
                st.query_params.clear()
                st.rerun()
            else:
                logging.error(f"Failed to acquire token: {result.get('error_description', 'Unknown error')}")
                st.error("Authentication failed. Please try again.")
                st.stop()

        # If no code is present, we need to generate auth URL and render the signin page
        # Generate a new state and nonce and save them in session
        if "oauth_state" not in st.session_state:
            st.session_state.oauth_state = secrets.token_urlsafe(16)
        if "oauth_nonce" not in st.session_state:
            st.session_state.oauth_nonce = secrets.token_urlsafe(16)

        auth_url = msal_app.get_authorization_request_url(
            SCOPE,
            redirect_uri=REDIRECT_URI,
            state=st.session_state.oauth_state,
            nonce=st.session_state.oauth_nonce
        )

        render_signin_page(auth_url=auth_url, mock=False)
        render_footer()
        st.stop()

# ── Databricks query helper ────────────────────────────────────────────────────
# ── DuckDB local-cache adapter ────────────────────────────────────────────────
# When DUCKDB_PATH points to an existing file (written by the sync job), all
# read queries and app writes are served locally — no network round-trip.
# The adapter translates the existing %(name)s pyformat SQL into DuckDB's
# $name named-parameter style so no query code needs to change.


# ── Query helpers (Phase 4b deferred — _DEMO_* coupling prevents extraction) ──



def run_query(query, params=None):
    # ── Demo mode: return hardcoded DataFrames without hitting any DB ──────────
    if is_demo_mode():
        p = params or {}
        _has_groups = "groups" in p or any(k.startswith("group_") for k in p)
        if "full_name" in p and _has_groups:
            return _DEMO_RELATED.get(p["full_name"], pd.DataFrame(
                columns=["full_name", "table_name", "catalog_name", "schema_name", "relationship"]))
        if _has_groups:
            return _DEMO_TABLES
        fn = p.get("table_full_name", "")
        if "lineage_cache" in query:
            return _DEMO_LINEAGE.get(fn, pd.DataFrame(
                columns=["direction", "entity_full_name", "entity_type"]))
        if "columns_metadata" in query:
            return _DEMO_COLUMNS.get(fn, pd.DataFrame(
                columns=["column_name", "data_type", "comment"]))
        return _DEMO_GRANTS.get(fn, pd.DataFrame(columns=["principal", "privilege"]))

    if _duckdb_available():
        return _run_duckdb_query(query, params)
    return _run_databricks_query(query, params)


@st.cache_data(ttl="1h", show_spinner=False)
def get_authorized_tables(groups):
    if is_demo_mode():
        return _DEMO_TABLES
    group_placeholders = ", ".join([f"%(group_{i})s" for i in range(len(groups))]) if groups else "''"
    params: dict = {}
    if groups:
        for i, group in enumerate(groups):
            params[f"group_{i}"] = group
    sql_query = ("""
        SELECT DISTINCT
            m.full_name,
            m.catalog_name,
            m.schema_name,
            m.table_name,
            m.comment as table_description,
            m.table_type,
            m.updated_at,
            COALESCE(dq.dq_score, '') AS dq_score,
            COALESCE(dq.last_run_status, '') AS dq_status
        FROM {0}.{1}.tables_metadata m
        JOIN {0}.{1}.permissions_cache p
          ON m.full_name = p.table_full_name
        LEFT JOIN {0}.{1}.data_quality_cache dq
          ON m.full_name = dq.table_full_name
        WHERE (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS')
    """).format(CATALOG_CACHE, SCHEMA_CACHE, group_placeholders)  # nosec B608
    return run_query(sql_query, params)


@st.cache_data(ttl="1h", show_spinner=False)
def get_multi_hop_lineage(table_full_name: str, depth: int = 1):
    """Fetch lineage edges up to a given depth.

    TODO (feature/enhanced-lineage): Implement recursive traversal.
    """
    return run_query(
        ("SELECT * FROM {0}.{1}.lineage_cache WHERE table_full_name = %(fn)s").format(
            CATALOG_CACHE, SCHEMA_CACHE
        ),
        {"fn": table_full_name},
    )


@st.cache_data(ttl="1h", show_spinner=False)
def search_all_metadata(query: str, groups: tuple):
    """Search across tables, columns, and descriptions using UNION."""
    import logging
    logging.info("GLOBAL SEARCH query=%s groups=%s", query, groups)

    group_placeholders = ", ".join([f"%(group_{i})s" for i in range(len(groups))]) if groups else "''"
    params: dict = {f"group_{i}": g for i, g in enumerate(groups)} if groups else {}
    params["q"] = f"%{query}%"

    _overrides_tbl = "user_data.business_name_overrides" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides"

    sql_query = ("""
        SELECT DISTINCT
            m.full_name, m.table_name AS name, 'Table' AS match_type,
            m.comment AS description, m.catalog_name, m.schema_name, m.table_name,
            m.comment AS table_description,
            COALESCE(dq.dq_score, '') AS dq_score
        FROM {0}.{1}.tables_metadata m
        JOIN {0}.{1}.permissions_cache p ON m.full_name = p.table_full_name
        LEFT JOIN {0}.{1}.data_quality_cache dq ON m.full_name = dq.table_full_name
        WHERE (m.table_name LIKE %(q)s OR m.comment LIKE %(q)s)
          AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS')

        UNION ALL

        SELECT DISTINCT
            c.table_full_name AS full_name,
            COALESCE(o.business_name, c.column_name) AS name,
            'Column' AS match_type,
            COALESCE(o.definition, c.comment) AS description,
            t.catalog_name, t.schema_name, t.table_name, t.comment AS table_description,
            COALESCE(dq.dq_score, '') AS dq_score
        FROM {0}.{1}.columns_metadata c
        JOIN {0}.{1}.permissions_cache p ON c.table_full_name = p.table_full_name
        JOIN {0}.{1}.tables_metadata t ON c.table_full_name = t.full_name
        LEFT JOIN {0}.{1}.data_quality_cache dq ON c.table_full_name = dq.table_full_name
        LEFT JOIN {3} o ON o.table_full_name = c.table_full_name AND o.column_name = c.column_name
        WHERE (
            c.column_name LIKE %(q)s OR c.comment LIKE %(q)s
            OR o.business_name LIKE %(q)s OR o.definition LIKE %(q)s
          )
          AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS')

        LIMIT 50
    """).format(CATALOG_CACHE, SCHEMA_CACHE, group_placeholders, _overrides_tbl)  # nosec B608

    sql_results = run_query(sql_query, params)

    if sql_results is not None and not sql_results.empty:
        if "match_type" not in sql_results.columns:
            sql_results = sql_results.assign(match_type="Table")
        if "name" not in sql_results.columns:
            sql_results = sql_results.assign(name=sql_results.get("table_name", ""))
        if "description" not in sql_results.columns:
            _desc_src = sql_results["table_description"] if "table_description" in sql_results.columns else sql_results.get("comment", "")
            sql_results = sql_results.assign(description=_desc_src)

    term_matches = []
    if _DEMO_GLOSSARY is not None and not _DEMO_GLOSSARY.empty and query:
        _auth_df = get_authorized_tables(groups)
        _allowed_fns = set(_auth_df["full_name"].tolist()) if _auth_df is not None and not _auth_df.empty else set()
        query_lower = query.lower()
        mask = (
            _DEMO_GLOSSARY['term'].str.lower().str.contains(query_lower, regex=False, na=False) |
            _DEMO_GLOSSARY['definition'].str.lower().str.contains(query_lower, regex=False, na=False)
        )
        glossary_df = _DEMO_GLOSSARY[mask]
        for row in glossary_df.itertuples(index=False):
            related_tables = getattr(row, 'related_tables', [])
            target_table = related_tables[0] if related_tables else ""
            if target_table and target_table not in _allowed_fns:
                continue
            parts = target_table.split('.')
            term_matches.append({
                "full_name": target_table,
                "name": getattr(row, 'term', ''),
                "match_type": "Glossary",
                "description": getattr(row, 'definition', ''),
                "table_description": "",
                "catalog_name": parts[0] if len(parts) == 3 else "",
                "schema_name": parts[1] if len(parts) == 3 else "",
                "table_name": parts[2] if len(parts) == 3 else "",
            })

    if term_matches:
        glossary_results = pd.DataFrame(term_matches)
        combined = pd.concat([sql_results, glossary_results], ignore_index=True) if sql_results is not None and not sql_results.empty else glossary_results
    else:
        combined = sql_results

    if combined is None or combined.empty:
        return combined

    q_lower = query.lower()
    def _score(row):
        name = str(row.get("name") or "").lower()
        mtype = str(row.get("match_type") or "")
        if mtype == "Table":
            if name == q_lower: return 5
            if name.startswith(q_lower): return 4
            if q_lower in name: return 3
            return 2
        if mtype == "Column":
            if name == q_lower: return 2
            if name.startswith(q_lower): return 1
            return 0
        return 1  # Glossary

    combined = combined.copy()
    combined["_score"] = combined.apply(_score, axis=1)
    return combined.sort_values("_score", ascending=False).drop(columns=["_score"]).reset_index(drop=True)


def get_column_business_names(table_full_name: str) -> dict:
    """Return column business name overrides for a table as a dict."""
    if is_demo_mode():
        return st.session_state.get("demo_business_names", {}).get(table_full_name, {})
    try:
        conn = get_db_connection()
        tbl = "user_data.business_name_overrides" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides"
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT column_name, business_name, definition, edited_by, edited_at "
                f"FROM {tbl} "
                f"WHERE table_full_name = %(table_full_name)s",
                {"table_full_name": table_full_name},
            )
            rows = cursor.fetchall_as_pandas()
            if rows is not None and not rows.empty:
                return {
                    str(r["column_name"]): {
                        "business_name": str(r["business_name"]) if r["business_name"] else "",
                        "definition":    str(r["definition"])    if r["definition"]    else "",
                        "edited_by":     str(r["edited_by"]),
                        "edited_at":     str(r["edited_at"]),
                    }
                    for _, r in rows.iterrows()
                }
    except Exception as e:
        logging.warning("Could not fetch column business names for %s: %s", table_full_name, e)
    return {}



def is_admin() -> bool:
    """True if the current user belongs to at least one ADMIN_GROUPS group.

    No demo-mode bypass — admins must be in the real Entra group even in
    demo/development mode, unlike is_power_user() which has a mock shortcut.
    """
    admin_groups = {g.strip() for g in os.getenv("ADMIN_GROUPS", "").split(",") if g.strip()}
    if not admin_groups:
        return False
    return bool(admin_groups & set(st.session_state.get("user_groups", [])))


import csv
import io


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


def export_schema_to_csv(cols: pd.DataFrame, col_overrides: dict) -> str:
    """Export table column metadata to a CSV string.

    Includes business name and definition overrides if present.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Column Name", "Business Name", "Data Type", "System Description", "Business Definition"])

    if cols is not None and not cols.empty:
        for _, c in cols.iterrows():
            cname = str(c.get("column_name", ""))
            ctype = str(c.get("data_type", ""))
            ccomment = str(c.get("comment") or "")

            override = col_overrides.get(cname, {})
            biz_name = override.get("business_name", "")
            biz_def = override.get("definition", "")

            writer.writerow([cname, biz_name, ctype, ccomment, biz_def])

    return output.getvalue()


def enqueue_sync(sync_type: str, table_full_name: str | None, payload: dict, queued_by: str) -> None:
    """Add an action to the Databricks write-back queue."""
    if not _duckdb_available():
        return
    import json
    sync_id = str(uuid.uuid4())
    conn = _get_write_connection()
    payload_str = json.dumps(payload)
    with conn.cursor() as cursor:
        # For metadata types, we upsert to avoid duplicate pending work for the same object
        if sync_type in ("COLUMN_DEF", "TABLE_DESC", "STEWARD"):
            _key_col = "payload_json->>'column_name'" if sync_type == "COLUMN_DEF" else "NULL"
            _match_val = payload.get("column_name") if sync_type == "COLUMN_DEF" else None
            
            # Simple cleanup of previous pending items for the same target
            # Note: payload_json check is slightly complex in SQL so we target by table and sync_type primarily
            _del_q = "DELETE FROM user_data.pending_sync WHERE sync_type = %(st)s AND status = 'pending'"
            _params = {"st": sync_type}
            if table_full_name:
                _del_q += " AND table_full_name = %(fn)s"
                _params["fn"] = table_full_name
            
            # For column defs, we must match the specific column
            if sync_type == "COLUMN_DEF" and _match_val:
                _del_q += " AND payload_json LIKE %(match)s"
                _params["match"] = f'%"{_match_val}"%'
                
            cursor.execute_write(_del_q, _params)

        cursor.execute_write(
            "INSERT INTO user_data.pending_sync "
            "(sync_id, sync_type, table_full_name, payload_json, queued_by, queued_at, status, attempts) "
            "VALUES (%(id)s, %(st)s, %(fn)s, %(pay)s, %(by)s, current_localtimestamp(), 'pending', 0)",
            {
                "id":  sync_id,
                "st":  sync_type,
                "fn":  table_full_name,
                "pay": payload_str,
                "by":  queued_by,
            },
        )


def enqueue_column_sync(table_full_name: str, column_name: str, definition: str, queued_by: str) -> None:
    """Legacy wrapper for column definitions."""
    enqueue_sync("COLUMN_DEF", table_full_name, {"column_name": column_name, "definition": definition}, queued_by)


def _push_to_databricks(sync_type: str, table_full_name: str | None, payload: dict) -> None:
    """Generalized dispatcher to push different types of changes to Databricks."""
    host = os.getenv("DATABRICKS_HOST", "").strip()
    http_path = os.getenv("DATABRICKS_HTTP_PATH", "").strip()
    token = os.getenv("DATABRICKS_TOKEN", "").strip()
    if not (host and http_path and token):
        raise RuntimeError("Databricks credentials not configured.")

    from databricks import sql as dbsql
    
    with dbsql.connect(server_hostname=host, http_path=http_path, access_token=token) as db_conn:
        with db_conn.cursor() as cur:
            if sync_type == "COLUMN_DEF":
                col = payload["column_name"]
                dfn = (payload.get("definition") or "").replace("'", "''")
                parts = table_full_name.split(".")
                cat, sch, tbl = [f"`{p}`" for p in parts]
                cur.execute(f"ALTER TABLE {cat}.{sch}.{tbl} ALTER COLUMN `{col}` COMMENT '{dfn}'")
                
            elif sync_type == "TABLE_DESC":
                dfn = (payload.get("definition") or "").replace("'", "''")
                parts = table_full_name.split(".")
                cat, sch, tbl = [f"`{p}`" for p in parts]
                cur.execute(f"ALTER TABLE {cat}.{sch}.{tbl} SET TBLPROPERTIES ('comment' = '{dfn}')")
                
            elif sync_type == "STEWARD":
                stew = (payload.get("steward_email") or "").replace("'", "''")
                parts = table_full_name.split(".")
                cat, sch, tbl = [f"`{p}`" for p in parts]
                cur.execute(f"ALTER TABLE {cat}.{sch}.{tbl} SET TBLPROPERTIES ('steward' = '{stew}')")

            elif sync_type == "TAG":
                import re
                key = payload["tag_key"]
                if not re.match(r"^[A-Za-z0-9_]+$", key):
                    raise ValueError(f"Invalid tag key: {key}")
                val = payload["tag_value"].replace("'", "''")
                parts = table_full_name.split(".")
                cat, sch, tbl = [f"`{p}`" for p in parts]
                cur.execute(f"ALTER TABLE {cat}.{sch}.{tbl} SET TAGS ('{key}' = '{val}')")

            elif sync_type == "AUDIT":
                audit_tbl = f"{CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log"
                cur.execute(
                    f"INSERT INTO {audit_tbl} (event_id, event_type, object_type, object_name, actor_email, old_value, new_value, created_at) "
                    f"VALUES (%(event_id)s, %(event_type)s, %(object_type)s, %(object_name)s, %(actor_email)s, %(old_value)s, %(new_value)s, current_timestamp())",
                    payload
                )

            elif sync_type == "COMMENT":
                comm_tbl = f"{CATALOG_CACHE}.{SCHEMA_CACHE}.comments"
                cur.execute(
                    f"INSERT INTO {comm_tbl} (comment_id, object_type, object_name, comment_text, author_name, author_email, created_at, steward_email, parent_comment_id) "
                    f"VALUES (%(comment_id)s, %(object_type)s, %(object_name)s, %(comment_text)s, %(author_name)s, %(author_email)s, current_timestamp(), %(steward_email)s, %(parent_comment_id)s)",
                    payload
                )


def _push_definition_to_databricks(table_full_name: str, column_name: str, definition: str) -> None:
    """Legacy wrapper for backward compatibility."""
    _push_to_databricks("COLUMN_DEF", table_full_name, {"column_name": column_name, "definition": definition})


def _process_sync_queue() -> int:
    """Drain pending sync items → Databricks. Returns number of items attempted.

    Uses dynamic batching and priority-aware processing:
    1. Metadata (COLUMN_DEF, TABLE_DESC, STEWARD)
    2. Tags and Comments
    3. Audit logs (Lowest priority)
    """
    if not _duckdb_available():
        return 0
    
    # Determine mode: Idle if no UI activity for 5 minutes
    is_idle = (time.time() - _get_last_ui_activity()) > 300
    batch_size = 50 if is_idle else 5
    
    conn = _get_write_connection()
    import json
    try:
        with conn.cursor() as cursor:
            # Multi-tier priority: order by sync_type weight, then by age
            # Weights: COLUMN_DEF/TABLE_DESC=1, STEWARD/TAG/COMMENT=2, AUDIT=3
            priority_sql = """
                CASE 
                    WHEN sync_type IN ('COLUMN_DEF', 'TABLE_DESC') THEN 1
                    WHEN sync_type IN ('STEWARD', 'TAG', 'COMMENT') THEN 2
                    ELSE 3
                END
            """
            cursor.execute(
                f"SELECT sync_id, sync_type, table_full_name, payload_json, attempts "
                f"FROM user_data.pending_sync "
                f"WHERE status = 'pending' AND attempts < %(max)s "
                f"ORDER BY {priority_sql} ASC, queued_at ASC LIMIT %(limit)s",
                {"max": _SYNC_MAX_ATTEMPTS, "limit": batch_size},
            )
            rows = cursor.fetchall()
        
        if not rows:
            return 0

        processed = 0
        for sync_id, stype, table_fn, pay_json, attempts in rows:
            time.sleep(0.01 if is_idle else 0.1)
            new_attempts = attempts + 1
            payload = json.loads(pay_json) if pay_json else {}
            
            with conn.cursor() as cursor:
                cursor.execute_write(
                    "UPDATE user_data.pending_sync SET status='processing', attempts=%(att)s WHERE sync_id=%(id)s",
                    {"att": new_attempts, "id": sync_id},
                )
            
            try:
                _push_to_databricks(stype, table_fn, payload)
                
                with conn.cursor() as cursor:
                    cursor.execute_write(
                        "UPDATE user_data.pending_sync SET status='done', completed_at=current_localtimestamp(), last_error=NULL WHERE sync_id=%(id)s",
                        {"id": sync_id},
                    )
                processed += 1
            except Exception as exc:
                err = str(exc)[:500]
                new_status = "failed" if new_attempts >= _SYNC_MAX_ATTEMPTS else "pending"
                with conn.cursor() as cursor:
                    cursor.execute_write(
                        "UPDATE user_data.pending_sync SET status=%(st)s, last_error=%(err)s WHERE sync_id=%(id)s",
                        {"st": new_status, "err": err, "id": sync_id},
                    )
                logging.warning("Sync %s (%s) failed: %s", sync_id[:8], stype, err)
        
        return processed
    except Exception as e:
        logging.error("Error processing sync queue: %s", e)
        return 0


@st.cache_resource(show_spinner=False)
def _start_sync_worker_thread():
    """Singleton background thread that drains pending_sync every 15 s."""
    import threading

    def _loop():
        _count = 0
        while True:
            try:
                # Every 20 cycles (~10 mins in Active mode, ~1.6 mins in Idle mode), run DR resync
                if _count % 20 == 0:
                    _run_dr_resync()
                _count += 1

                n = _process_sync_queue()
                if n:
                    logging.info("Sync worker: pushed %d column definition(s) to Databricks.", n)
            except Exception as exc:
                logging.error("Sync worker loop error: %s", exc, exc_info=True)
            
            # Dynamic poll: 5s if idle, 30s if active
            is_idle = (time.time() - _get_last_ui_activity()) > 300
            time.sleep(5 if is_idle else 30)

    t = threading.Thread(target=_loop, name="dd-sync-worker", daemon=True)
    t.start()
    return t



def _viewport_height(fallback: int = 800) -> int:
    """Return the user's viewport height in px, falling back if not yet captured."""
    return int(st.session_state.get("viewport_height", fallback))


# VIS_WIDE_CSS imported from src.ui.css (assets/vis_dialog.css)

def _fetch_lineage_hop(node_fn: str, query_groups: list) -> "pd.DataFrame | None":
    """Fetch direct lineage neighbors of node_fn, permission-filtered."""
    lin_ph = ", ".join([f"%(lin_g_{i})s" for i in range(len(query_groups))]) if query_groups else "''"
    params: dict = {"table_full_name": node_fn}
    for i, g in enumerate(query_groups):
        params[f"lin_g_{i}"] = g
    q = (
        "SELECT DISTINCT l.direction, l.entity_full_name, l.entity_type "
        "FROM {0}.{1}.lineage_cache l "
        "JOIN {0}.{1}.permissions_cache p ON l.entity_full_name = p.table_full_name "
        "WHERE l.table_full_name = %(table_full_name)s "
        "AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS') "
        "ORDER BY l.direction, l.entity_full_name"
    ).format(CATALOG_CACHE, SCHEMA_CACHE, lin_ph)  # nosec B608
    return run_query(q, params)


def _build_lineage_graph(start_fn: str, start_label: str, query_groups: list, max_depth: int = 2):
    """BFS multi-hop lineage. Returns (graph_nodes, graph_links)."""
    graph_nodes = [{"id": start_fn, "label": start_label, "current": True, "relationship": "Current"}]
    graph_links: list = []
    visited: set = {start_fn}
    frontier = [start_fn]

    for _ in range(max_depth):
        if not frontier:
            break
        next_frontier: list = []
        for node_fn in frontier:
            result = _fetch_lineage_hop(node_fn, query_groups)
            if result is None or result.empty or "direction" not in result.columns:
                continue
            for _, lr in result.iterrows():
                efn = str(lr["entity_full_name"])
                direction = str(lr["direction"])
                link = {"from": efn, "to": node_fn} if direction == "UPSTREAM" else {"from": node_fn, "to": efn}
                if link not in graph_links:
                    graph_links.append(link)
                if efn not in visited:
                    visited.add(efn)
                    next_frontier.append(efn)
                    graph_nodes.append({"id": efn, "label": efn.split(".")[-1], "current": False, "relationship": direction.capitalize()})
        frontier = next_frontier

    return graph_nodes, graph_links


def _lineage_vis_html(graph_nodes: list, graph_links: list, height: int = 350, container_id: str = "mynetwork", spring_length: int = 120) -> str:
    import json as _json
    nodes_js = _json.dumps(graph_nodes)
    edges_js = _json.dumps(graph_links)
    return (
        f'<div id="{container_id}" style="width:100%;height:{height}px;background:#F2EDE1;border-radius:4px;'
        f'border:1px solid #C9C2B4;overflow:hidden;margin-top:16px;"></div>'
        f'<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>'
        f'<script>'
        f'var nodes=new vis.DataSet({nodes_js});'
        f'var edges=new vis.DataSet({edges_js});'
        f'var container=document.getElementById("{container_id}");'
        f'var options={{nodes:{{shape:"box",margin:10,font:{{size:14,face:"sans-serif"}},borderWidth:1,shadow:true}},'
        f'edges:{{arrows:"to",color:"#C9C2B4",smooth:{{type:"cubicBezier",forceDirection:"horizontal"}}}},'
        f'physics:{{barnesHut:{{springLength:{spring_length},springConstant:0.04}},minVelocity:0.75}},'
        f'interaction:{{hover:false,dragNodes:true,dragView:true,zoomView:true}}}}; '
        f'var upd=[];nodes.forEach(function(n){{'
        f'var bg=n.current?"#B8362A":(n.relationship==="Shared column"?"#DDE4EC":"#FAF7F0");'
        f'var bdr=n.current?"#8C271E":(n.relationship==="Shared column"?"#2B4A6B":"#C9C2B4");'
        f'var txt=n.current?"#FAF7F0":(n.relationship==="Shared column"?"#2B4A6B":"#14110C");'
        f'upd.push({{id:n.id,color:{{background:bg,border:bdr,highlight:{{background:bg,border:bdr}}}},font:{{color:txt}}}});}});'
        f'nodes.update(upd);'
        f'var net=new vis.Network(container,{{nodes:nodes,edges:edges}},options);'
        f'net.once("stabilizationIterationsDone",function(){{net.fit();}});'
        f'</script>'
    )


@st.dialog(t("detail.lineage_graph"), width="large")
def render_lineage_fullscreen(graph_nodes: list, graph_links: list, full_name: str):
    st.markdown(VIS_WIDE_CSS, unsafe_allow_html=True)
    st.markdown(f"**{full_name}** — {t('detail.lineage_graph_subtitle').format(table=full_name.split('.')[-1])}")
    # Use a large fixed canvas — CSS in VIS_WIDE_CSS stretches the iframe to
    # calc(95vh - 190px), so the vis.js div just needs to be big enough that
    # the graph isn't clipped before CSS takes over.
    _graph_h = 1800
    graph_html = _lineage_vis_html(graph_nodes, graph_links, height=_graph_h, container_id="mynetwork_full", spring_length=220)
    components.html(graph_html, height=_graph_h + 20, scrolling=False)


@st.dialog(t("detail.edit_table"), width="large")
def render_table_metadata_editor(table_full_name: str, current_desc: str, current_steward: str):
    """Editor for table-level metadata (description, steward)."""
    st.markdown(f"**{table_full_name}**")
    
    new_desc = st.text_area(t("detail.table_description"), value=current_desc, height=150)
    new_stew = st.text_input(t("detail.steward_email"), value=current_steward)
    
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button(t("common.save"), type="primary", use_container_width=True):
            try:
                save_table_metadata(table_full_name, description=new_desc, steward_email=new_stew)
                st.success(t("common.saved"))
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
    with c2:
        if st.button(t("common.cancel"), use_container_width=True):
            st.rerun()


@st.dialog(t("detail.data_sample"), width="large")
def render_data_sample(table_full_name: str):
    import re
    import logging
    import pandas as pd
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
        if not re.match(r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$", table_full_name):
            st.error(t("common.error"))
            return
        if is_demo_mode():
            df = pd.DataFrame({"id": [1, 2, 3], "status": ["NEW", "SHIPPED", "CLOSED"]})
        elif _duckdb_available():
            # DuckDB file is ATTACHed as CATALOG_CACHE; actual row data lives at
            # CATALOG_CACHE.<schema>.<table> — strip the Databricks Unity Catalog prefix.
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
            # Height is controlled by VIS_WIDE_CSS (calc(95vh - 190px)) so
            # the grid always fills the dialog regardless of viewport size.
            # Pass a generous fixed height so Streamlit allocates enough iframe
            # space; CSS then stretches it to the actual available area.
            st.dataframe(df, use_container_width=True, height=2000)
        else:
            st.info(t("detail.preview_needs_data"))
    except Exception as e:
        logging.error("Error fetching data sample for %s: %s", table_full_name, e, exc_info=True)
        st.error(t("detail.preview_error"))


# ── Page renderers ─────────────────────────────────────────────────────────────

def render_catalog_browser(groups):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("catalog.eyebrow")}</div>
      <h1>{t("catalog.hero_title")}</h1>
      <p class="lead">{t("catalog.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    try:
        all_data = get_authorized_tables(groups)
        if all_data is None or all_data.empty or 'catalog_name' not in all_data.columns:
            st.info(t("catalog.no_catalogs"))
            return
            
        catalogs = sorted(all_data['catalog_name'].unique().tolist())
        
        # Simple Tree Implementation using Streamlit expanders
        for cat in catalogs:
            with st.expander(f"📁 {cat}", expanded=False):
                cat_data = all_data[all_data['catalog_name'] == cat]
                # Group by schema_name to avoid O(N^2) dataframe filtering
                for sch, sch_data in cat_data.groupby('schema_name'):
                    st.markdown(f'<div style="margin-left: 20px; font-weight: 500; color: var(--ink-60); margin-top: 10px; margin-bottom: 5px;">📂 {sch}</div>', unsafe_allow_html=True)
                    _dq_lookup = dict(zip(sch_data["table_name"], sch_data["dq_score"])) if "dq_score" in sch_data.columns else {}
                    tables = sorted(sch_data['table_name'].unique().tolist())

                    # Columns for tables to make it more compact
                    t_cols = st.columns(3)
                    for i, tbl in enumerate(tables):
                        with t_cols[i % 3]:
                            full_n = f"{cat}.{sch}.{tbl}"
                            _grade, _gcls = _dq_grade(_dq_lookup.get(tbl, ""))
                            # Show grade badge above the button via markdown, then the clickable button
                            st.markdown(
                                f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">'
                                f'<span class="dd-dq-badge {_gcls}" title="Completeness grade {_grade}">{_grade}</span>'
                                f'<span style="font-family:var(--font-mono);font-size:12px;color:var(--ink-60);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{_html.escape(tbl)}</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                            if st.button("Open →", key=f"tree_{full_n}", use_container_width=True):
                                st.query_params["tab"] = "search"
                                st.session_state["dd_search_override"] = tbl
                                st.session_state["dd_nav_select"] = full_n
                                st.rerun()
    except Exception as e:
        logging.error("Error in catalog browser: %s", e)
        st.error(t("catalog.load_error"))

def render_glossary(query_groups):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("glossary.title")}</div>
      <h1>{t("glossary.hero_title")}</h1>
      <p class="lead">{t("glossary.subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)
    
    # Term Selection (Autocomplete)
    all_terms = _DEMO_GLOSSARY["term"].tolist()
    selected_term = st.selectbox(
        t("glossary.search_placeholder"),
        options=all_terms,
        placeholder="Select or type a business term...",
        label_visibility="collapsed",
        key="glossary_search",
    )
    
    if selected_term:
        term_row = _DEMO_GLOSSARY[_DEMO_GLOSSARY["term"] == selected_term].iloc[0]
        
        col_main, col_side = st.columns([7, 5], gap="large")
        
        with col_main:
            st.markdown(f'''
            <div class="dd-detail-header" style="margin-top: 0;">
              <span class="dd-eyebrow" style="margin-bottom:0">{t("glossary.term_details")}</span>
            </div>
            <div class="dd-detail-table-name">{term_row["term"]}</div>
            <div style="font-family:var(--font-sans); font-size:14px; font-weight:600; color:var(--ink-40); margin-bottom:8px; text-transform:uppercase; letter-spacing:0.05em;">{t("glossary.definition")}</div>
            <p class="dd-detail-desc" style="font-size:18px;">{term_row["definition"]}</p>
            
            <div style="font-family:var(--font-sans); font-size:14px; font-weight:600; color:var(--ink-40); margin-top:24px; margin-bottom:8px; text-transform:uppercase; letter-spacing:0.05em;">{t("glossary.logic_calculation")}</div>
            <div style="background:var(--paper-deep); padding:16px; border-radius:2px; font-family:var(--font-mono); font-size:14px; color:var(--ink); border-left:3px solid var(--accent); line-height:1.5;">
              {term_row["calculation"]}
            </div>
            
            <div style="font-family:var(--font-sans); font-size:14px; font-weight:600; color:var(--ink-40); margin-top:32px; margin-bottom:12px; text-transform:uppercase; letter-spacing:0.05em;">{t("glossary.linked_tables")}</div>
            ''', unsafe_allow_html=True)
            
            _authorized_fns = set(get_authorized_tables(query_groups)["full_name"].tolist()) if query_groups else set()
            for table_fn in term_row["related_tables"]:
                if table_fn not in _authorized_fns:
                    continue  # hide tables the current user cannot access
                _gloss_bk = table_fn in st.session_state.get("bookmarks", set())
                _c_tbl, _c_star = st.columns([11, 1], gap="small")
                with _c_tbl:
                    if st.button(f"→ {table_fn.split('.')[-1]}", key=f"gloss_link_{table_fn}", use_container_width=True, type="secondary"):
                        st.query_params["tab"] = "search"
                        st.session_state["dd_search_override"] = table_fn.split(".")[-1]
                        st.session_state["dd_nav_select"] = table_fn
                        st.rerun()
                with _c_star:
                    if st.button("★" if _gloss_bk else "☆", key=f"gloss_bk_{table_fn}", use_container_width=True):
                        if _gloss_bk:
                            st.session_state.get("bookmarks", set()).discard(table_fn)
                            _pref_delete(table_fn, "bookmark")
                        else:
                            st.session_state.get("bookmarks", set()).add(table_fn)
                            _pref_upsert(table_fn, "bookmark")
                        st.rerun()

        with col_side:
            # Stewardship Section
            st.markdown(f'''
            <div class="dd-section-header">
              <span class="dd-eyebrow" style="margin-bottom:0">{t("glossary.stewardship")}</span>
            </div>
            <div style="margin-top:16px;">
              <div style="font-family:var(--font-sans); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em;">{t("glossary.business_domain")}</div>
              <div style="font-family:var(--font-sans); font-size:16px; font-weight:600; color:var(--ink); margin-top:4px;">{term_row["domain"]}</div>
            </div>
            <div style="margin-top:20px;">
              <div style="font-family:var(--font-sans); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em;">{t("glossary.data_steward")}</div>
              <div style="font-family:var(--font-sans); font-size:16px; font-weight:600; color:var(--ink); margin-top:4px;">{term_row["steward"]}</div>
            </div>
            ''', unsafe_allow_html=True)
            
            # Concept Map (Graph)
            st.markdown(f'''
            <div class="dd-section-header" style="margin-top:32px;">
              <span class="dd-eyebrow" style="margin-bottom:0">{t("glossary.concept_map")}</span>
            </div>
            ''', unsafe_allow_html=True)
            
            # Simple Graph: Term -> Tables
            graph_nodes = [{"id": "TERM", "label": selected_term, "current": True, "relationship": "Current"}]
            graph_links = []
            for table_fn in term_row["related_tables"]:
                t_label = table_fn.split(".")[-1]
                graph_nodes.append({"id": table_fn, "label": t_label, "current": False, "relationship": "Table"})
                graph_links.append({"from": "TERM", "to": table_fn})
            
            import json
            graph_html = f'''<div id="mynetwork_glossary" style="width: 100%; height: 300px; background: #F2EDE1; border-radius: 4px; border: 1px solid #C9C2B4; overflow: hidden; margin-top: 16px;"></div><script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script><script type="text/javascript">var nodes = new vis.DataSet({json.dumps(graph_nodes)}); var edges = new vis.DataSet({json.dumps(graph_links)}); var container = document.getElementById('mynetwork_glossary'); var data = {{ nodes: nodes, edges: edges }}; var options = {{ nodes: {{ shape: 'box', margin: 10, font: {{ size: 14, face: 'sans-serif' }}, borderWidth: 1, shadow: true }}, edges: {{ arrows: 'to', color: '#C9C2B4', smooth: {{ type: 'cubicBezier', forceDirection: 'horizontal' }} }}, physics: {{ barnesHut: {{ springLength: 100, springConstant: 0.04 }}, minVelocity: 0.75 }}, interaction: {{ hover: false, dragNodes: true, dragView: true, zoomView: true }} }}; var updatedNodes = []; nodes.forEach(function(node) {{ var isCurrent = node.current; var bg = isCurrent ? '#B8362A' : '#FAF7F0'; var border = isCurrent ? '#8C271E' : '#C9C2B4'; var text = isCurrent ? '#FAF7F0' : '#14110C'; updatedNodes.push({{ id: node.id, color: {{ background: bg, border: border, highlight: {{ background: bg, border: border }} }}, font: {{ color: text }} }}); }}); nodes.update(updatedNodes); var network = new vis.Network(container, data, options); network.once("stabilizationIterationsDone", function() {{ network.fit(); }});</script>'''
            components.html(graph_html, height=330)

def _render_table_card(row: "pd.Series", key_prefix: str) -> None:
    """Discovery card: table name is clickable, star toggles bookmark."""
    _ts = row.get("updated_at")
    _time_str = _ts.strftime(t("discovery.date_format")) if isinstance(_ts, pd.Timestamp) else (str(_ts) if _ts else "")
    _full      = str(row.get("full_name", ""))
    _tname     = str(row.get("table_name", ""))
    _is_bk     = _full in st.session_state.get("bookmarks", set())

    st.markdown(f'''
    <div style="background:var(--paper); border:1px solid var(--ink-10); padding:16px 20px 4px; margin-bottom:4px; border-radius:2px;">
        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px;">
            <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em;">{_html.escape(str(row.get("catalog_name","")))} · {_html.escape(str(row.get("schema_name","")))}</div>
            <div style="font-family:var(--font-mono); font-size:11px; color:var(--accent);">{t("discovery.updated")} {_time_str}</div>
        </div>
        <p style="font-family:var(--font-sans); font-size:13px; color:var(--ink-60); line-height:1.5; margin:4px 0 8px;">{_html.escape(str(row.get("table_description","")))}</p>
    </div>
    ''', unsafe_allow_html=True)

    # Table name button (navigates to detail) + star bookmark — flush below the card
    _c_name, _c_star = st.columns([11, 1], gap="small")
    with _c_name:
        if st.button(f"→ {_tname}", key=f"{key_prefix}_open_{_full}", use_container_width=True, type="secondary"):
            st.query_params["tab"] = "search"
            st.session_state["dd_search_override"] = _tname
            st.session_state["dd_nav_select"] = _full
            st.rerun()
    with _c_star:
        if st.button("★" if _is_bk else "☆", key=f"{key_prefix}_bk_{_full}", use_container_width=True):
            if _is_bk:
                st.session_state.get("bookmarks", set()).discard(_full)
                _pref_delete(_full, "bookmark")
            else:
                st.session_state.get("bookmarks", set()).add(_full)
                _pref_upsert(_full, "bookmark")
            st.rerun()
    st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)


def render_discovery(groups):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("discovery.title")}</div>
      <h1>{t("discovery.hero_title")}</h1>
      <p class="lead">{t("discovery.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

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
        st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">{t("personalization.tab_notable")}</span></div>', unsafe_allow_html=True)
        primary_group = st.session_state.get("group_filter")
        if not primary_group and groups:
            primary_group = groups[0]

        if primary_group:
            st.info(t("discovery.group_highlights", group=primary_group))
            try:
                all_authorized = get_authorized_tables((primary_group,))
                if not all_authorized.empty and "updated_at" in all_authorized.columns:
                    recent_tables = all_authorized.sort_values(by="updated_at", ascending=False).head(10)
                    for _, row in recent_tables.iterrows():
                        _render_table_card(row, "notable")
                else:
                    st.info(t("discovery.no_updates"))
            except Exception as e:
                logging.error("Error in discovery tab: %s", e)
                st.error(t("discovery.load_error"))
        else:
            st.warning(t("discovery.sign_in_prompt"))

    # ── My Bookmarks ─────────────────────────────────────────────────────────────
    elif _disc_active == _disc_tab_labels[1]:
        st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">{t("personalization.tab_bookmarks")}</span></div>', unsafe_allow_html=True)
        bookmarks = st.session_state.get("bookmarks", set())
        if not bookmarks:
            st.info(t("personalization.no_bookmarks"))
        else:
            try:
                all_tables = get_authorized_tables(groups)
                bk_df = all_tables[all_tables["full_name"].isin(bookmarks)]
                if bk_df.empty:
                    st.info(t("personalization.no_bookmarks"))
                else:
                    for _, row in bk_df.iterrows():
                        _render_table_card(row, "bk")
            except Exception as e:
                logging.error("Error loading bookmarks: %s", e)
                st.error(t("discovery.load_error"))

        # ── Bookmarked columns ────────────────────────────────────────────────
        col_bookmarks = st.session_state.get("col_bookmarks", set())
        st.markdown(f'<div class="dd-section-header" style="margin-top:32px"><span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">{t("personalization.bookmarked_columns")}</span></div>', unsafe_allow_html=True)
        if not col_bookmarks:
            st.info(t("personalization.no_col_bookmarks"))
        else:
            _col_bk_auth_fns = set(get_authorized_tables(groups)["full_name"].tolist()) if groups else set()
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
                    if st.button("★", key=f"colbk_rm_{_bk_id}", use_container_width=True):
                        st.session_state.col_bookmarks.discard(_bk_id)
                        _pref_delete(_bk_id, "col_bookmark")
                        st.rerun()

    # ── Recently Viewed ──────────────────────────────────────────────────────────
    elif _disc_active == _disc_tab_labels[2]:
        st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">{t("personalization.tab_recent")}</span></div>', unsafe_allow_html=True)
        recent_views = st.session_state.get("recent_views", [])
        if not recent_views:
            st.info(t("personalization.no_recent"))
        else:
            try:
                all_tables = get_authorized_tables(groups)
                # Preserve recency order
                rv_df = all_tables[all_tables["full_name"].isin(recent_views)].copy()
                rv_df["_order"] = rv_df["full_name"].map({fn: i for i, fn in enumerate(recent_views)})
                rv_df = rv_df.sort_values("_order").drop(columns=["_order"])
                if rv_df.empty:
                    st.info(t("personalization.no_recent"))
                else:
                    for _, row in rv_df.iterrows():
                        _render_table_card(row, "rv")
            except Exception as e:
                logging.error("Error loading recent views: %s", e)
                st.error(t("discovery.load_error"))

def render_health(groups):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("health.title")}</div>
      <h1>{t("health.hero_title")}</h1>
      <p class="lead">{t("health.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    try:
        all_data = get_authorized_tables(groups)
        if all_data.empty:
            st.info(t("health.no_data"))
            return

        # 1. Calculation Logic
        n_tables = len(all_data)
        n_desc = (all_data['table_description'].str.strip().str.len() > 0).sum()
        table_coverage = (n_desc / n_tables * 100) if n_tables > 0 else 0

        # For columns, we need to query the cache (or use mock)
        if is_demo_mode():
            # Aggregate columns from _DEMO_COLUMNS
            all_cols_list = []
            for df in _DEMO_COLUMNS.values():
                all_cols_list.append(df)
            all_cols_df = pd.concat(all_cols_list)
            n_cols = len(all_cols_df)
            n_col_desc = all_cols_df['comment'].apply(lambda x: len(str(x).strip()) > 0).sum()
        else:
            cols_stats_query = f"SELECT count(*) as total, count(comment) as with_desc FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata"
            stats = run_query(cols_stats_query)
            n_cols = stats.iloc[0]['total']
            n_col_desc = stats.iloc[0]['with_desc']
        
        col_coverage = (n_col_desc / n_cols * 100) if n_cols > 0 else 0

        # 2. Hero Metrics
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

        st.markdown('<div style="margin-top:48px;"></div>', unsafe_allow_html=True)

        # 3. Bottom breakdown
        col_left, col_right = st.columns([6, 4], gap="large")
        
        with col_left:
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

        with col_right:
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

    except Exception as e:
        logging.error("Error in health dashboard: %s", e)
        st.error(t("health.load_error"))



# ── Admin page ─────────────────────────────────────────────────────────────────

def get_admin_stats() -> dict:
    """Return four catalog-wide counts for the admin dashboard."""
    if is_demo_mode():
        return {
            "tables":    len(_DEMO_TABLES),
            "columns":   sum(len(df) for df in _DEMO_COLUMNS.values()),
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
        logs = [l for l in st.session_state.get("demo_audit_log", []) if l["event_type"] == "business_name_change"]
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
        logs = [l for l in st.session_state.get("demo_audit_log", [])
                if l["event_type"] in ("comment_added", "comment_reply")]
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

    with st.expander(t("admin.biz_log_title"), expanded=True):
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

    with st.expander(t("admin.comment_log_title"), expanded=True):
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
        
        for tbl, ts_col, pk in tables_to_check:
            # Get max local timestamp
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT MAX({ts_col}) FROM user_data.{tbl}")
                local_max = cursor.fetchall()[0][0]
            
            # Query Databricks for any records AFTER local_max
            # Note: run_query handles the Databricks connection
            remote_q = f"SELECT * FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.{tbl}"
            params = {}
            if local_max:
                remote_q += f" WHERE {ts_col} > %(local_max)s"
                params["local_max"] = local_max

            delta_df = run_query(remote_q, params)            
            if delta_df is not None and not delta_df.empty:
                _set_dr_resync_status(f"Syncing {tbl}")
                # Merge into DuckDB
                with conn.cursor() as cursor:
                    for _, row in delta_df.iterrows():
                        # Simple append for logs/comments (guaranteed unique IDs)
                        if tbl in ("comments", "audit_log"):
                            cols = ", ".join(delta_df.columns)
                            placeholders = ", ".join([f"%({c})s" for c in delta_df.columns])
                            cursor.execute_write(
                                f"INSERT OR IGNORE INTO user_data.{tbl} ({cols}) VALUES ({placeholders})",
                                row.to_dict()
                            )
                        else:
                            # Merge for overrides
                            cursor.execute_write(
                                f"INSERT OR REPLACE INTO user_data.{tbl} ({', '.join(delta_df.columns)}) "
                                f"VALUES ({', '.join([f'%({c})s' for c in delta_df.columns])})",
                                row.to_dict()
                            )
        
        _set_dr_resync_status("Up-to-date")
        _set_dr_resync_progress(100.0)
    except Exception as e:
        logging.error("DR Resync failed: %s", e)
        _set_dr_resync_status(f"Error: {str(e)[:50]}")



# ── App entry point ────────────────────────────────────────────────────────────
render_css()
_mark_ui_activity()

# Start the Databricks write-back worker (singleton daemon thread, no-ops in pure local mode).
if _duckdb_available():
    _start_sync_worker_thread()

# Capture viewport height once per session; returns None on first render (before JS runs).
if "viewport_height" not in st.session_state:
    _vh = streamlit_js_eval(js_expressions="window.innerHeight", key="_dd_vh")
    if _vh:
        st.session_state["viewport_height"] = int(_vh)
else:
    # Keep the component alive so it runs on browsers that re-register after reload
    streamlit_js_eval(js_expressions="window.innerHeight", key="_dd_vh")

# ── Auth gate ─────────────────────────────────────────────────────────────────
if ENABLE_MOCK_AUTH and ENVIRONMENT == "development":
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    # Personalization state — seed from DuckDB, fall back to empty
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
    # that navigate directly to a URL without an existing session.
    # Only fires when the user is NOT already authenticated so that a nav click
    # (which re-adds mock_login=true to the URL) cannot overwrite the session.
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
            # Default: all groups (admin view — used by screenshot script & load tests)
            _ql_groups = ["finance_group", "research_group", "hr_group", "it_group",
                          "SELECT_ALL_USERS", "finance_dept_id", "all_employees_id"]
            _ql_name, _ql_email = "Admin User", "admin@research-org.ca"
        st.session_state.authenticated = True
        st.session_state.user_groups   = _ql_groups
        st.session_state.user_name     = _ql_name
        st.session_state.user_email    = _ql_email
    if not st.session_state.get("authenticated"):
        # Slim logo-only header for the sign-in page — avoids nav JS wiring on unauthenticated renders
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
    check_auth()

# ── Authenticated: header with user ───────────────────────────────────────────
current_tab = st.query_params.get("tab", "search")
render_header(user_name=st.session_state.get("user_name", ""), active_tab=current_tab, show_admin=is_admin())
st.markdown('<div class="dd-page" role="main" aria-live="polite">', unsafe_allow_html=True)

groups = tuple(st.session_state.get("user_groups", [])) if st.session_state.get("user_groups") else ("none",)
active_group = st.session_state.get("group_filter")
query_groups = (active_group,) if active_group else groups


def _clear_transient_edit_state() -> None:
    """Discard any in-progress column edits or open comment forms.

    Called whenever the user navigates to a different table or a different tab
    so a half-filled form from one context never bleeds into another.
    """
    st.session_state.pop("dd_col_edit_mode", None)
    stale_keys = [k for k in st.session_state if str(k).startswith("dd_comment_open_")]
    for k in stale_keys:
        del st.session_state[k]


# Detect tab change — clear transient state so edits don't bleed across tabs
_prev_tab = st.session_state.get("_dd_current_tab")
if _prev_tab is not None and _prev_tab != current_tab:
    _clear_transient_edit_state()
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
        _clear_transient_edit_state()
        st.session_state.pop("_dd_sticky_nav", None)
    st.session_state["_dd_current_search_query"] = search_query

    # When a group filter is active but no search term, show all tables for that group
    if active_group and not search_query and _all_tables is not None and not _all_tables.empty:
        import pandas as _pd2
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
                        graph_nodes, graph_links = _build_lineage_graph(full_name, _tbl, query_groups, max_depth=2)

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
    render_catalog_browser(query_groups)
elif current_tab == "glossary":
    render_glossary(query_groups)
elif current_tab == "discovery":
    render_discovery(query_groups)
elif current_tab == "health":
    render_health(query_groups)
elif current_tab == "admin":
    render_admin_page()

st.markdown("</div>", unsafe_allow_html=True)
render_footer()
