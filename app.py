from __future__ import annotations

import logging
import streamlit as st
from databricks import sql
import os
import msal
from dotenv import load_dotenv

load_dotenv()

# Configuration
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_URI = os.getenv("REDIRECT_URI")
SCOPE = ["User.Read", "GroupMember.Read.All"]

CATALOG_CACHE = "data_governance"
SCHEMA_CACHE = "dictionary_cache"

st.set_page_config(
    page_title="Data Dictionary",
    page_icon="assets/logo-mark.svg",
    layout="wide",
)

# ── Design system CSS ──────────────────────────────────────────────────────────
DESIGN_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500;9..144,600&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --paper:        #FAF7F0;
    --paper-deep:   #F2EDE1;
    --paper-ink:    #E8E1D0;
    --ink:          #14110C;
    --ink-90:       #2A2620;
    --ink-80:       #3D3830;
    --ink-60:       #6B645A;
    --ink-40:       #9A9388;
    --ink-20:       #C9C2B4;
    --ink-10:       #DCD6C8;
    --accent:       #B8362A;
    --accent-ink:   #8C271E;
    --accent-wash:  #F3DFD9;
    --forest:       #3F5E3A;
    --ochre:        #9A6D1C;
    --deepblue:     #2B4A6B;
    --font-display: "Fraunces", "Cormorant Garamond", serif;
    --font-sans:    "Manrope", -apple-system, system-ui, sans-serif;
    --font-mono:    "JetBrains Mono", ui-monospace, monospace;
    --ease:         cubic-bezier(0.2, 0, 0, 1);
    --dur-hover:    120ms;
    --dur-state:    180ms;
}

/* ── Hide Streamlit chrome ── */
#MainMenu,
header[data-testid="stHeader"],
footer,
[data-testid="stSidebar"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] {
    display: none !important;
}

/* ── Global surface ── */
html, body, .stApp, [data-testid="stAppViewContainer"] {
    background: var(--paper) !important;
    font-family: var(--font-sans);
    color: var(--ink);
    -webkit-font-smoothing: antialiased;
}

/* Remove default Streamlit top padding so our fixed header sits flush */
[data-testid="stMainBlockContainer"] {
    padding-top: 80px !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    max-width: 100% !important;
}

/* Inner content wrapper — applied via .dd-content divs */
.dd-page {
    max-width: 1200px;
    margin: 0 auto;
    padding: 48px 48px 96px;
}

/* ── Inputs ── */
.stTextInput input {
    border: 1px solid var(--ink) !important;
    border-radius: 2px !important;
    background: var(--paper) !important;
    font-family: var(--font-sans) !important;
    padding: 12px 14px !important;
    font-size: 16px !important;
    color: var(--ink) !important;
    box-shadow: none !important;
    transition: outline var(--dur-hover) var(--ease);
}
.stTextInput input:focus {
    outline: 2px solid var(--accent) !important;
    outline-offset: 3px !important;
}
.stTextInput label {
    font-family: var(--font-sans) !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
    color: var(--ink-60) !important;
}

/* ── Buttons ── */
.stButton > button {
    font-family: var(--font-sans) !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    padding: 10px 18px !important;
    border-radius: 2px !important;
    border: 1px solid var(--ink) !important;
    background: var(--ink) !important;
    color: var(--paper) !important;
    letter-spacing: -0.005em !important;
    transition: background var(--dur-hover) var(--ease) !important;
    box-shadow: none !important;
}
.stButton > button:hover {
    background: var(--ink-90) !important;
    border-color: var(--ink-90) !important;
    color: var(--paper) !important;
}

/* Selectbox */
[data-testid="stSelectbox"] label {
    font-family: var(--font-sans) !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
    color: var(--ink-60) !important;
}
[data-testid="stSelectbox"] > div > div {
    border: 1px solid var(--ink-20) !important;
    border-radius: 2px !important;
    background: var(--paper) !important;
    font-family: var(--font-sans) !important;
    font-size: 14px !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border-top: 1px solid var(--ink) !important;
    border-radius: 0 !important;
}
[data-testid="stDataFrame"] th {
    font-family: var(--font-mono) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: var(--ink-60) !important;
    background: var(--paper-deep) !important;
    border-bottom: 1px solid var(--ink-20) !important;
}
[data-testid="stDataFrame"] td {
    font-family: var(--font-mono) !important;
    font-size: 13px !important;
    color: var(--ink-80) !important;
}

/* Alerts */
.stAlert {
    border-radius: 2px !important;
    border-left: 3px solid var(--accent) !important;
    background: var(--paper-deep) !important;
    font-family: var(--font-sans) !important;
}

/* Headings */
h1, h2, h3 {
    font-family: var(--font-display) !important;
    font-weight: 400 !important;
    letter-spacing: -0.02em !important;
    line-height: 1.1 !important;
    color: var(--ink) !important;
}

code, pre, .stCode {
    font-family: var(--font-mono) !important;
    font-size: 13px !important;
}

::selection { background: var(--accent-wash); color: var(--ink); }

/* ── Fixed header ── */
.dd-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1000;
    background: rgba(250, 247, 240, 0.92);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--ink-20);
}
.dd-header-inner {
    max-width: 1200px;
    margin: 0 auto;
    padding: 14px 48px;
    display: flex;
    align-items: center;
    gap: 24px;
}
.dd-logo-link {
    display: flex;
    align-items: center;
    gap: 12px;
    text-decoration: none;
}
.dd-logo-text {
    font-family: var(--font-display);
    font-size: 22px;
    font-weight: 500;
    color: var(--ink);
    letter-spacing: -0.01em;
}
.dd-pill {
    font-family: var(--font-sans);
    font-size: 10px;
    padding: 2px 8px;
    border: 1px solid var(--ink);
    border-radius: 999px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-weight: 600;
    color: var(--ink);
    margin-left: 4px;
}
.dd-nav {
    margin-left: auto;
    display: flex;
    gap: 22px;
    align-items: center;
}
.dd-nav a {
    font-size: 14px;
    color: var(--ink-80);
    text-decoration: none;
    transition: color var(--dur-hover) var(--ease);
}
.dd-nav a:hover { color: var(--accent); }
.dd-nav-sep {
    width: 1px;
    height: 20px;
    background: var(--ink-20);
    display: inline-block;
}
.dd-nav-user {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--ink-40);
}

/* ── Eyebrow ── */
.dd-eyebrow {
    font-family: var(--font-sans);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--ink-60);
    margin-bottom: 18px;
}

/* ── Rule ── */
.dd-rule {
    border: 0;
    border-top: 1px solid var(--ink-20);
    margin: 32px 0;
}
.dd-rule-ink {
    border: 0;
    border-top: 1px solid var(--ink);
    margin-bottom: 10px;
}

/* ── Sign-in page ── */
.dd-signin-grid {
    display: grid;
    grid-template-columns: 1.1fr 0.9fr;
    gap: 64px;
    align-items: center;
    min-height: calc(100vh - 160px);
    padding: 0;
}
.dd-signin-hero h1 {
    font-family: var(--font-display) !important;
    font-size: 64px !important;
    font-weight: 400 !important;
    line-height: 1.1 !important;
    letter-spacing: -0.02em !important;
    margin: 0 0 24px !important;
    color: var(--ink) !important;
}
.dd-signin-hero .lead {
    font-family: var(--font-sans);
    font-size: 18px;
    line-height: 1.5;
    color: var(--ink-80);
    max-width: 46ch;
    margin-bottom: 32px;
}
.dd-stats-row {
    display: flex;
    gap: 48px;
    margin-top: 8px;
}
.dd-stat-n {
    font-family: var(--font-display);
    font-size: 40px;
    font-weight: 500;
    line-height: 1;
    letter-spacing: -0.02em;
    color: var(--ink);
}
.dd-stat-l {
    font-family: var(--font-sans);
    font-size: 12px;
    color: var(--ink-40);
    margin-top: 6px;
}
.dd-signin-card {
    border-top: 1px solid var(--ink);
    padding-top: 32px;
}
.dd-signin-card h3 {
    font-family: var(--font-display) !important;
    font-size: 28px !important;
    font-weight: 500 !important;
    margin: 0 0 12px !important;
    letter-spacing: -0.015em !important;
}
.dd-signin-card .body {
    font-family: var(--font-sans);
    font-size: 15px;
    color: var(--ink-80);
    line-height: 1.5;
    margin-bottom: 28px;
    max-width: 38ch;
}
.dd-meta {
    font-family: var(--font-sans);
    font-size: 12px;
    color: var(--ink-40);
    margin-top: 12px;
}

/* ── Search page ── */
.dd-search-hero h1 {
    font-family: var(--font-display) !important;
    font-size: 64px !important;
    font-weight: 400 !important;
    line-height: 1.1 !important;
    letter-spacing: -0.02em !important;
    margin: 0 0 10px !important;
}
.dd-search-hero .lead {
    font-family: var(--font-sans);
    font-size: 18px;
    line-height: 1.5;
    color: var(--ink-80);
    margin-bottom: 32px;
}

/* ── Results section ── */
.dd-results-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--ink);
    margin-bottom: 0;
    margin-top: 40px;
}
.dd-results-count {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--ink-40);
    margin-left: 12px;
}

/* ── Detail section ── */
.dd-detail-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--ink);
    margin-top: 32px;
    margin-bottom: 16px;
}
.dd-detail-table-name {
    font-family: var(--font-mono) !important;
    font-size: 28px !important;
    font-weight: 500 !important;
    margin: 0 0 6px !important;
    letter-spacing: -0.01em !important;
    color: var(--ink) !important;
}
.dd-detail-desc {
    font-family: var(--font-sans);
    font-size: 15px;
    color: var(--ink-80);
    margin-bottom: 20px;
    line-height: 1.5;
}

/* ── Footer ── */
.dd-footer {
    border-top: 1px solid var(--ink-10);
    padding: 32px 48px;
    margin-top: 96px;
}
.dd-footer-inner {
    max-width: 1200px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--ink-40);
}
"""

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


def render_css():
    st.markdown(f"<style>{DESIGN_CSS}</style>", unsafe_allow_html=True)


def render_header(user_name: str | None = None):
    user_section = ""
    if user_name:
        user_section = f"""
        <span class="dd-nav-sep"></span>
        <span class="dd-nav-user">{user_name}</span>
        """
    st.markdown(f"""
    <div class="dd-header">
      <div class="dd-header-inner">
        <a href="#" class="dd-logo-link">
          {LOGO_MARK_SVG}
          <span class="dd-logo-text">Data Dictionary</span>
          <span class="dd-pill">Beta</span>
        </a>
        <nav class="dd-nav">
          <a href="#">Catalog</a>
          <a href="#">Glossary</a>
          <a href="#">Lineage</a>
          {user_section}
        </nav>
      </div>
    </div>
    """, unsafe_allow_html=True)


def render_footer():
    st.markdown("""
    <div class="dd-footer">
      <div class="dd-footer-inner">
        <span>Data Dictionary · v0.1.0 · synced nightly from Unity Catalog</span>
        <span>main.data_governance.dictionary_cache</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Authentication helpers ─────────────────────────────────────────────────────
@st.cache_resource
def get_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )


def render_signin_page(auth_url: str | None = None, mock: bool = False):
    """Render the editorial two-column sign-in layout."""
    col_hero, col_card = st.columns([1.1, 0.9], gap="large")

    with col_hero:
        st.markdown("""
        <div class="dd-signin-hero">
          <div class="dd-eyebrow">§ Business Data Dictionary</div>
          <h1>A card catalog<br>for your warehouse.</h1>
          <p class="lead">Search tables, columns, and business terms across Unity Catalog —
          filtered to what you have permission to see.</p>
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
            if st.button(f"{MS_LOGO_SVG}  Sign in with Entra ID (mock)", use_container_width=True):
                st.session_state.authenticated = True
                st.session_state.user_groups = ["finance_dept_id", "all_employees_id"]
                st.session_state.user_name = "Finance User"
                st.rerun()
            st.markdown(
                '<p class="dd-meta">Mock authentication active — '
                'set TENANT_ID, CLIENT_ID, CLIENT_SECRET for production.</p>',
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
            ">{MS_LOGO_SVG} Sign in with Entra ID</a>
            <p class="dd-meta" style="margin-top:12px">By signing in you agree to the data access policy.</p>
            """, unsafe_allow_html=True)


def check_auth():
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = None

    if st.session_state.auth_token is None:
        msal_app = get_msal_app()
        auth_url = msal_app.get_authorization_request_url(SCOPE, redirect_uri=REDIRECT_URI)

        render_signin_page(auth_url=auth_url, mock=False)
        render_footer()

        query_params = st.query_params
        if "code" in query_params:
            result = msal_app.acquire_token_by_authorization_code(
                query_params["code"], scopes=SCOPE, redirect_uri=REDIRECT_URI
            )
            if "access_token" in result:
                st.session_state.auth_token = result
                st.session_state.user_groups = result.get("id_token_claims", {}).get("groups", [])
                st.session_state.user_name = result.get("id_token_claims", {}).get("name")
                st.rerun()
        st.stop()

# ── Databricks query helper ────────────────────────────────────────────────────
@st.cache_resource(ttl="2h")
def get_database_connection():
    conn = sql.connect(
        server_hostname=os.getenv("DATABRICKS_HOST"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_TOKEN"),
    )
    yield conn
    conn.close()

@st.cache_data(ttl="1h")
def run_query(query, params=None):
    conn = get_database_connection()
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall_as_pandas()


# ── App entry point ────────────────────────────────────────────────────────────
render_css()

# ── Auth gate ─────────────────────────────────────────────────────────────────
ENABLE_MOCK_AUTH = os.getenv("ENABLE_MOCK_AUTH", "false").lower() == "true"

if ENABLE_MOCK_AUTH:
    st.warning("⚠️ Mock Authentication is ENABLED.")
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        render_header()
        st.markdown('<div class="dd-page">', unsafe_allow_html=True)
        render_signin_page(mock=True)
        st.markdown("</div>", unsafe_allow_html=True)
        render_footer()
        st.stop()
else:
    check_auth()

# ── Authenticated: header with user ───────────────────────────────────────────
render_header(user_name=st.session_state.get("user_name", ""))
st.markdown('<div class="dd-page">', unsafe_allow_html=True)

@st.cache_data(ttl="1h")
def get_authorized_tables(groups):
    sql_query = f"""
        SELECT DISTINCT
            m.full_name,
            m.catalog_name,
            m.schema_name,
            m.table_name,
            m.comment as table_description,
            m.table_type
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata m
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache p
          ON m.full_name = p.table_full_name
        WHERE (p.principal IN %(groups)s OR p.principal = 'SELECT_ALL_USERS')
    """
    return run_query(sql_query, {"groups": groups})

# Sign-out (hidden Streamlit widget used for state management)
with st.sidebar:
    if st.button("Sign out"):
        st.session_state.clear()
        st.rerun()

# ── Search page ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="dd-search-hero">
  <div class="dd-eyebrow">§ Catalog search</div>
  <h1>Find your data.</h1>
  <p class="lead">Search tables, columns, and business terms across Unity Catalog —
  filtered to what you can access.</p>
</div>
""", unsafe_allow_html=True)

search_query = st.text_input(
    "Search the catalog",
    placeholder="e.g. customer_lifetime_value",
    label_visibility="collapsed",
)

if search_query:
    groups = tuple(st.session_state.user_groups) if st.session_state.user_groups else ("none",)

    try:
        # Fetch all authorized tables for the user's groups (cached)
        all_results = get_authorized_tables(groups)

        # Apply local search filter using pandas
        search_lower = search_query.lower()
        full_name_match = all_results['full_name'].fillna('').str.lower().str.contains(search_lower, regex=False)
        comment_match = all_results['table_description'].fillna('').str.lower().str.contains(search_lower, regex=False)
        results = all_results[full_name_match | comment_match]

        if not results.empty:
            n = len(results)
            st.markdown(f"""
            <div class="dd-results-header">
              <span class="dd-eyebrow" style="margin-bottom:0">Results</span>
              <span class="dd-results-count">{n} table{'s' if n != 1 else ''} · permission-trimmed</span>
            </div>
            """, unsafe_allow_html=True)

            display_results = results.drop(columns=['full_name'])
            st.dataframe(
                display_results,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "catalog_name": st.column_config.TextColumn("Catalog"),
                    "schema_name": st.column_config.TextColumn("Schema"),
                    "table_name": st.column_config.TextColumn("Table"),
                    "table_description": st.column_config.TextColumn("Description"),
                    "table_type": st.column_config.TextColumn("Type"),
                },
            )

            st.markdown("""
            <div class="dd-detail-header">
              <span class="dd-eyebrow" style="margin-bottom:0">§ Table detail</span>
            </div>
            """, unsafe_allow_html=True)

            selected_table = st.selectbox(
                "Select a table",
                results["table_name"].tolist(),
                label_visibility="collapsed",
            )

            if selected_table:
                row = results[results["table_name"] == selected_table].iloc[0]
                full_name = f"{row['catalog_name']}.{row['schema_name']}.{row['table_name']}"
                st.markdown(f"""
                <div class="dd-eyebrow" style="margin-bottom:4px">{row['catalog_name']} · {row['schema_name']}</div>
                <div class="dd-detail-table-name">{row['table_name']}</div>
                <p class="dd-detail-desc">{row.get('table_description', '')}</p>
                """, unsafe_allow_html=True)

                st.markdown("""
                <div class="dd-rule-ink" style="margin:24px 0 0"></div>
                <div class="dd-eyebrow" style="margin:12px 0">§ Columns</div>
                """, unsafe_allow_html=True)

                # nosec B608 - False positive: table_full_name is correctly parameterized via %s
                cols_query = (
                    f"SELECT column_name, data_type, comment "
                    f"FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata "
                    f"WHERE table_full_name = %(table_full_name)s"
                )
                cols = run_query(cols_query, {"table_full_name": full_name})
                st.dataframe(
                    cols,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "column_name": st.column_config.TextColumn("Column"),
                        "data_type": st.column_config.TextColumn("Type"),
                        "comment": st.column_config.TextColumn("Description"),
                    },
                )
        else:
            st.markdown(f"""
            <div style="padding:64px 8px;border-top:1px solid var(--ink-10);text-align:center">
              <div style="font-family:var(--font-display);font-size:22px;margin-bottom:8px;letter-spacing:-0.01em">
                No matches for &ldquo;{search_query}&rdquo;.
              </div>
              <p style="font-family:var(--font-sans);font-size:15px;color:var(--ink-60);max-width:44ch;margin:0 auto">
                Try a shorter term, or request access to a catalog you don't yet see.
              </p>
            </div>
            """, unsafe_allow_html=True)

    except Exception as e:
        logging.error("Error querying data: %s", e, exc_info=True)
        st.error("An error occurred while querying the data. Please try again later or contact support.")
        st.info("Ensure the sync job has been run and environment variables are correct.")

else:
    st.markdown("""
    <p style="font-family:var(--font-sans);font-size:15px;color:var(--ink-60);margin-top:8px">
      Start typing to search the catalog.
    </p>
    """, unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)
render_footer()
