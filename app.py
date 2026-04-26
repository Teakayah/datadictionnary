from __future__ import annotations

import logging
import uuid
import threading
import time
import streamlit as st
import streamlit.components.v1 as components
from databricks import sql
import os
import msal
import html as _html
import secrets
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ── Internationalisation (i18n) ───────────────────────────────────────────────
import json as _json

def _load_locales() -> dict:
    base = os.path.join(os.path.dirname(__file__), "locale")
    result = {}
    for lang in ("en", "fr"):
        try:
            with open(os.path.join(base, f"{lang}.json"), encoding="utf-8") as f:
                result[lang] = _json.load(f)
        except Exception:
            result[lang] = {}
    return result

# Loaded once per process start — no caching decorator so restarts always
# pick up locale file changes without needing a cache-clear.
LOCALES: dict = _load_locales()

def get_locale() -> str:
    """Detect preferred locale from the browser Accept-Language header."""
    try:
        header = st.context.headers.get("Accept-Language", "en")
        primary = header.split(",")[0].split(";")[0].split("-")[0].strip().lower()
        return "fr" if primary == "fr" else "en"
    except Exception:
        return "en"

def _ensure_locale() -> None:
    if "locale" not in st.session_state:
        st.session_state["locale"] = get_locale()

def t(key: str, **kwargs) -> str:
    """Look up a dotted key (e.g. 'nav.search') in the active locale.

    Falls back to English if the key is missing in the active locale.
    Supports str.format() style placeholders: t('search.results_count', count=5).
    """
    _ensure_locale()
    lang = st.session_state.get("locale", "en")

    def _lookup(d: dict, parts: list) -> str | None:
        for p in parts:
            if not isinstance(d, dict):
                return None
            d = d.get(p)
        return d if isinstance(d, str) else None

    parts = key.split(".")
    val = _lookup(LOCALES.get(lang, {}), parts) or _lookup(LOCALES.get("en", {}), parts) or key
    try:
        return val.format(**kwargs) if kwargs else val
    except (KeyError, IndexError):
        return val

def set_locale(lang: str) -> None:
    """Persist locale choice; button click already triggers the rerun."""
    st.session_state["locale"] = lang

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

# Configuration
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_URI = os.getenv("REDIRECT_URI")
SCOPE = ["User.Read", "GroupMember.Read.All", "email"]

CATALOG_CACHE = "data_governance"
SCHEMA_CACHE = "dictionary_cache"
MAX_BUSINESS_NAME_LEN = 255

st.set_page_config(
    page_title="Data Dictionary",
    page_icon="assets/favicon.png",
    layout="wide",
)

# ── Design system CSS ──────────────────────────────────────────────────────────
DESIGN_CSS = """@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500;9..144,600&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

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

/* Smooth fade-in on rerun to prevent white flash */
@keyframes ddFadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
}
.stApp {
    animation: ddFadeIn 0.25s ease-out;
}

/* Remove default Streamlit top padding so our fixed header sits flush */
[data-testid="stMainBlockContainer"] {
    padding-top: 100px !important;
    padding-left: 48px !important;
    padding-right: 48px !important;
    padding-bottom: 96px !important;
    max-width: 1200px !important;
    margin: 0 auto !important;
}

/* Inner content wrapper — applied via .dd-content divs */
.dd-page {
    /* No longer needed as a wrapper since we constrain stMainBlockContainer, 
       but kept for any inner markdown sections if necessary */
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
.stTextInput label,
[data-testid="stSelectbox"] label {
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
[data-testid="stSelectbox"] > div > div {
    border: 1px solid var(--ink-20) !important;
    border-radius: 2px !important;
    background: var(--paper) !important;
    font-family: var(--font-sans) !important;
    font-size: 16px !important;
    color: var(--ink) !important;
}
[data-testid="stSelectbox"] input {
    color: var(--ink) !important;
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

/* ── Secondary / ghost nav buttons (used in lineage + related sections) ── */
button[data-testid="stBaseButton-secondary"] {
    background: transparent !important;
    color: var(--ink-60) !important;
    border: 1px solid var(--ink-20) !important;
    font-size: 12px !important;
    font-family: var(--font-mono) !important;
    padding: 5px 10px !important;
    letter-spacing: 0 !important;
}
button[data-testid="stBaseButton-secondary"]:hover {
    color: var(--ink) !important;
    border-color: var(--ink) !important;
    background: transparent !important;
}

/* ── Lineage flow ── */
.dd-lineage-dir {
    font-family: var(--font-mono);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--ink-40);
    margin-bottom: 8px;
}
.dd-lineage-node {
    border: 1px solid var(--ink-10);
    padding: 10px 12px;
    margin-bottom: 8px;
    background: var(--paper);
}
.dd-lineage-node.dd-lineage-locked {
    opacity: 0.45;
    background: var(--paper-deep);
}
.dd-lineage-node-name {
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--ink);
}
.dd-lineage-node-schema {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--ink-40);
    margin-top: 2px;
}
.dd-lineage-center {
    border: 2px solid var(--accent);
    padding: 10px 12px;
    margin-bottom: 8px;
    background: var(--paper);
}
.dd-lineage-center-name {
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
}
.dd-lineage-center-schema {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--ink-40);
    margin-top: 2px;
}
.dd-lineage-empty {
    font-family: var(--font-sans);
    font-size: 12px;
    color: var(--ink-40);
    padding: 8px 0;
    font-style: italic;
}

/* ── Related tables cards ── */
.dd-related-card {
    border: 1px solid var(--ink-10);
    padding: 12px;
    background: var(--paper);
    margin-bottom: 4px;
    transition: border-color var(--dur-hover) var(--ease);
}
.dd-related-card:hover { border-color: var(--ink-40); }
.dd-related-badge {
    font-family: var(--font-mono);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--ink-40);
    margin-bottom: 4px;
}
.dd-related-name {
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--ink);
    font-weight: 500;
}
.dd-related-schema {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--ink-40);
    margin-top: 2px;
}

/* ── Detail: section sub-headers (§ columns, § grants, …) ── */
.dd-section-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--ink);
    margin-top: 28px;
    margin-bottom: 0;
}
.dd-section-count {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--ink-40);
}

/* ── Columns list (Streamlit-column-based rows) ── */
.dd-col-name {
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--ink);
    line-height: 1.5;
}
.dd-col-type {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--ink-40);
    line-height: 1.5;
}
.dd-col-desc {
    font-family: var(--font-sans);
    font-size: 13px;
    color: var(--ink-60);
    line-height: 1.4;
}
.dd-col-biz-name {
    font-family: var(--font-sans);
    font-size: 13px;
    color: var(--ink);
    font-weight: 500;
    line-height: 1.4;
    display: block;
}
.dd-col-tech-sub {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--ink-40);
    display: block;
    line-height: 1.3;
    margin-top: 2px;
}
.dd-col-desc-faded {
    font-family: var(--font-sans);
    font-size: 11px;
    color: var(--ink-40);
    display: block;
    line-height: 1.3;
    margin-top: 2px;
}
.dd-col-divider {
    border: none;
    border-top: 1px solid var(--ink-10);
    margin: 2px 0;
}

/* ── Grants list ── */
.dd-grant-row {
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-top: 1px solid var(--ink-10);
    font-family: var(--font-mono);
    font-size: 12px;
}
.dd-grant-who { color: var(--ink); }
.dd-grant-what { color: var(--ink-60); }

/* ── External link (Open in Databricks) ── */
.dd-link-external {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--ink-60);
    text-decoration: none;
    border-bottom: 1px solid var(--ink-20);
    transition: color var(--dur-hover) var(--ease), border-color var(--dur-hover) var(--ease);
    display: inline-block;
    margin-top: 4px;
    margin-bottom: 20px;
}
.dd-link-external:hover { color: var(--ink); border-color: var(--ink); }

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

.dd-nav a.active {
    color: var(--accent) !important;
    font-weight: 600 !important;
}

/* ── Language toggle ── */
.dd-lang-toggle {
    display: inline-flex;
    align-items: center;
    gap: 4px;
}
.dd-lang-opt {
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.08em;
    color: var(--ink-40);
    text-decoration: none;
    transition: color var(--dur-hover) var(--ease);
}
.dd-lang-opt:hover { color: var(--ink); }
.dd-lang-opt.dd-lang-active {
    color: var(--ink) !important;
    font-weight: 600;
}
.dd-lang-sep {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--ink-20);
}

/* Hide the zero-height JS bridge iframe */
iframe[height="0"] { display: none !important; }

/* ── Business name editor ── */
.dd-edit-banner {
    background: var(--ochre);
    color: var(--paper);
    font-family: var(--font-sans);
    font-size: 13px;
    font-weight: 500;
    padding: 10px 14px;
    border-radius: 2px;
    margin-bottom: 16px;
    letter-spacing: -0.005em;
}
.dd-business-name {
    font-family: var(--font-display);
    font-size: 36px;
    font-weight: 500;
    color: var(--ink);
    line-height: 1.1;
    margin: 4px 0 4px 0;
}
.dd-tech-name-sub {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--ink-40);
    margin-bottom: 12px;
}
.dd-biz-audit {
    font-family: var(--font-sans);
    font-size: 11px;
    color: var(--ink-40);
    margin-top: -8px;
    margin-bottom: 12px;
    letter-spacing: -0.003em;
}

/* ── Comments ── */
.dd-comment-row {
    border-top: 1px solid var(--ink-10);
    padding: 10px 0;
}
.dd-comment-author {
    font-family: var(--font-sans);
    font-size: 12px;
    font-weight: 600;
    color: var(--ink);
}
.dd-comment-date {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--ink-40);
}
.dd-comment-text {
    font-family: var(--font-sans);
    font-size: 13px;
    color: var(--ink-60);
    line-height: 1.5;
    margin-top: 4px;
    white-space: pre-wrap;
}
.dd-comment-no-steward {
    font-family: var(--font-sans);
    font-size: 11px;
    color: var(--ink-40);
    font-style: italic;
    margin-top: 4px;
}
.dd-comment-reply {
    border-top: none;
    padding: 6px 0 6px 12px;
    border-left: 2px solid var(--ink-10);
    margin-top: 4px;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    border: 1px solid var(--ink-20) !important;
    border-radius: 2px !important;
    background: var(--paper) !important;
}
[data-testid="stExpander"] details {
    background: var(--paper) !important;
}
[data-testid="stExpander"] details summary {
    background: var(--paper-deep) !important;
    color: var(--ink) !important;
}
[data-testid="stExpander"] details summary:hover {
    background: var(--paper-ink) !important;
    color: var(--ink) !important;
}
/* Target only the label paragraph — NOT span, which carries the Material Icons glyph */
[data-testid="stExpander"] details summary p {
    color: var(--ink) !important;
    font-family: var(--font-sans) !important;
    font-size: 14px !important;
    font-weight: 500 !important;
}

/* ── Dataframe (glide-data-grid) ── */
[data-testid="stDataFrame"] {
    --gdg-bg-cell:        var(--paper) !important;
    --gdg-bg-cell-medium: var(--paper-deep) !important;
    --gdg-bg-header:      var(--paper-deep) !important;
    --gdg-bg-header-has-focus: var(--paper-ink) !important;
    --gdg-text-dark:      var(--ink) !important;
    --gdg-text-medium:    var(--ink-60) !important;
    --gdg-text-light:     var(--ink-40) !important;
    --gdg-border-color:   var(--ink-10) !important;
}
[data-testid="stDataFrame"] > div {
    background: var(--paper) !important;
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

    st.markdown(f'''
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
''', unsafe_allow_html=True)

    # Hidden Streamlit buttons — JS in the component iframe clicks these
    _tabs = ["search", "catalog", "glossary", "discovery", "health"]
    if show_admin:
        _tabs.append("admin")
    for tab_id in _tabs:
        if st.button(t(f"nav.{tab_id}"), key=f"nav_{tab_id}"):
            st.query_params["tab"] = tab_id
            st.query_params["mock_login"] = "true"
            st.rerun()

    # Hidden lang proxy buttons — JS clicks these to trigger locale rerun.
    # on_click fires *before* the script reruns, so render_header() picks up
    # the new locale on that same rerun and builds consistent nav labels + TAB_MAP.
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
            
            // 1. Hide proxy buttons
            allBtns.forEach(btn => {{
                const label = btn.textContent.trim();
                if (NAV_LABELS.includes(label) || label === 'LOCALE_EN' || label === 'LOCALE_FR') {{
                    const wrapper = btn.closest('div[data-testid="stButton"]');
                    if (wrapper) wrapper.style.display = 'none';
                }}
            }});

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
@st.cache_resource
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
            if st.button(f"{MS_LOGO_SVG}  {t('auth.mock_button')}", use_container_width=True):
                st.session_state.authenticated = True
                st.session_state.user_groups = ["finance_dept_id", "all_employees_id"]
                st.session_state.user_name  = "Finance User"
                st.session_state.user_email = "finance.user@example.com"
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
            ">{MS_LOGO_SVG} {t('auth.sign_in_button')}</a>
            <p class="dd-meta" style="margin-top:12px">By signing in you agree to the data access policy.</p>
            """, unsafe_allow_html=True)


def check_auth():
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = None

    if st.session_state.auth_token is None:
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
                st.session_state.auth_token = result
                claims = result.get("id_token_claims", {})
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

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "")
# User data (comments, overrides, audit) lives in a separate persistent file
# that is never swapped by the nightly sync job.
USER_DATA_PATH = (
    DUCKDB_PATH.replace(".duckdb", "_user_data.duckdb")
    if ".duckdb" in DUCKDB_PATH
    else DUCKDB_PATH + "_user_data.duckdb"
) if DUCKDB_PATH else ""

_db_write_lock = threading.Lock()


def _duckdb_available() -> bool:
    return bool(DUCKDB_PATH and os.path.exists(DUCKDB_PATH))


def _to_duckdb_sql(sql: str, params: dict) -> tuple:
    """Convert %(name)s pyformat SQL + dict params to DuckDB $name style.

    Special case: ``IN %(name)s`` where the value is a list/tuple is rewritten
    to ``= ANY($name)`` so the DuckDB array-contains operator is used.
    Returns (converted_sql, converted_params_dict).
    """
    import re
    if not params:
        return sql, {}
    converted = {}
    result = sql
    for name, value in params.items():
        if isinstance(value, (list, tuple)):
            # IN %(name)s  →  = ANY($name)
            result = re.sub(
                rf"\bIN\s+%\({re.escape(name)}\)s",
                f"= ANY(${name})",
                result,
                flags=re.IGNORECASE,
            )
            converted[name] = list(value)
        else:
            converted[name] = value
    # Remaining %(name)s → $name
    result = re.sub(r"%\((\w+)\)s", r"$\1", result)
    return result, converted


@st.cache_resource(validate=lambda c: c is not None)
def _get_shared_duckdb_connection():
    """Singleton connection shared across all Streamlit sessions/threads."""
    if not _duckdb_available():
        return None

    import duckdb
    con = duckdb.connect(DUCKDB_PATH)

    # Attach the persistent user data database
    con.execute(f"ATTACH IF NOT EXISTS '{USER_DATA_PATH}' AS user_data")

    # Initialize user data tables with primary keys (if they don't exist)
    with _db_write_lock:
        con.execute("""
            CREATE TABLE IF NOT EXISTS user_data.comments (
                comment_id        VARCHAR PRIMARY KEY,
                object_type       VARCHAR,
                object_name       VARCHAR,
                comment_text      VARCHAR,
                author_name       VARCHAR,
                author_email      VARCHAR,
                created_at        TIMESTAMP,
                steward_email     VARCHAR,
                parent_comment_id VARCHAR
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS user_data.business_name_overrides (
                table_full_name VARCHAR,
                column_name     VARCHAR,
                business_name   VARCHAR,
                definition      VARCHAR,
                edited_by       VARCHAR,
                edited_at       TIMESTAMP,
                PRIMARY KEY (table_full_name, column_name)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS user_data.audit_log (
                event_id        VARCHAR PRIMARY KEY,
                event_type      VARCHAR,
                object_type     VARCHAR,
                object_name     VARCHAR,
                actor_email     VARCHAR,
                old_value       VARCHAR,
                new_value       VARCHAR,
                created_at      TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS user_data.user_preferences (
                user_oid        VARCHAR NOT NULL,
                table_full_name VARCHAR NOT NULL,
                pref_type       VARCHAR NOT NULL,
                last_interacted TIMESTAMP NOT NULL,
                PRIMARY KEY (user_oid, table_full_name, pref_type)
            )
        """)
    return con


class _DuckDBCursor:
    """Cursor-like wrapper around a shared DuckDB connection."""

    def __init__(self, con):
        self._con = con
        self._rel = None

    def execute(self, sql: str, params=None):
        if params is None:
            self._rel = self._con.execute(sql)
        elif isinstance(params, dict):
            converted_sql, converted_params = _to_duckdb_sql(sql, params)
            self._rel = self._con.execute(converted_sql, converted_params)
        else:
            self._rel = self._con.execute(sql, params)

    def execute_write(self, sql: str, params=None):
        """Thread-safe write execution wrapped in a lock."""
        with _db_write_lock:
            self.execute(sql, params)

    def fetchall_as_pandas(self):
        if self._rel is None:
            return pd.DataFrame()
        return self._rel.df()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        # We do NOT close the shared connection!
        pass


class _DuckDBConn:
    """Connection-like wrapper that uses the shared singleton connection."""

    def __init__(self, path: str):
        self._con = _get_shared_duckdb_connection()

    def cursor(self):
        return _DuckDBCursor(self._con)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    @property
    def open(self):
        return self._con is not None


@st.cache_resource(ttl="2h", validate=lambda conn: conn.open)
def _get_databricks_connection():
    return sql.connect(
        server_hostname=os.getenv("DATABRICKS_HOST"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_TOKEN"),
    )


def _get_write_connection():
    """Return a DB connection for write operations (DuckDB primary)."""
    if _duckdb_available():
        return _DuckDBConn(DUCKDB_PATH)
    return _get_databricks_write_connection()


def _get_databricks_write_connection():
    """Return a fresh (uncached) Databricks connection for write operations.

    Write operations (INSERT, MERGE INTO) must always target the Databricks SQL
    Warehouse — never the local DuckDB file, which is a read-only cache that is
    rebuilt from Databricks on each sync and would silently discard any local
    writes.  This function bypasses the read-path DuckDB check intentionally.
    """
    return sql.connect(
        server_hostname=os.getenv("DATABRICKS_HOST"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_TOKEN"),
    )


def get_db_connection():
    """Return a DB connection for read queries.

    Returns a DuckDB-backed connection when DUCKDB_PATH points to an existing
    file (fast, local, no network).  Falls back to the cached Databricks SQL
    Warehouse connection otherwise.

    Do NOT use this for write operations — use _get_databricks_write_connection()
    instead so writes always reach Databricks regardless of cache state.
    """
    if _duckdb_available():
        return _DuckDBConn(DUCKDB_PATH)
    return _get_databricks_connection()


@st.cache_data(ttl="1h")
def _run_databricks_query(query, params=None):
    """Cached Databricks query — 1 h TTL to amortise network latency."""
    conn = _get_databricks_connection()
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall_as_pandas()


def _run_duckdb_query(query, params=None):
    """Uncached DuckDB query — local file is fast enough that caching adds
    overhead rather than benefit, and skipping the cache means the app
    always sees the freshest file after the nightly sync."""
    conn = _DuckDBConn(DUCKDB_PATH)
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall_as_pandas()


# ── Personalization persistence helpers ───────────────────────────────────────

def _user_oid() -> str:
    """Return a stable identifier for the current user (OID or email fallback)."""
    return st.session_state.get("user_oid") or st.session_state.get("user_email") or "anonymous"


def _pref_upsert(table_full_name: str, pref_type: str) -> None:
    """Write or refresh a bookmark/recent entry in user_data.user_preferences."""
    if not _duckdb_available():
        return
    try:
        con = get_db_connection()
        with _db_write_lock:
            con.execute(
                """
                INSERT INTO user_data.user_preferences (user_oid, table_full_name, pref_type, last_interacted)
                VALUES (?, ?, ?, now())
                ON CONFLICT (user_oid, table_full_name, pref_type) DO UPDATE
                    SET last_interacted = excluded.last_interacted
                """,
                [_user_oid(), table_full_name, pref_type],
            )
    except Exception as _e:
        logging.warning("Could not write user preference: %s", _e)


def _pref_delete(table_full_name: str, pref_type: str) -> None:
    """Remove a bookmark entry from user_data.user_preferences."""
    if not _duckdb_available():
        return
    try:
        con = get_db_connection()
        with _db_write_lock:
            con.execute(
                "DELETE FROM user_data.user_preferences WHERE user_oid=? AND table_full_name=? AND pref_type=?",
                [_user_oid(), table_full_name, pref_type],
            )
    except Exception as _e:
        logging.warning("Could not delete user preference: %s", _e)


def _pref_load(pref_type: str, limit: int = 20) -> list[str]:
    """Return table_full_name list for the given pref_type, newest first."""
    if not _duckdb_available():
        return []
    try:
        con = get_db_connection()
        rows = con.execute(
            """
            SELECT table_full_name FROM user_data.user_preferences
            WHERE user_oid=? AND pref_type=?
            ORDER BY last_interacted DESC LIMIT ?
            """,
            [_user_oid(), pref_type, limit],
        ).fetchall()
        return [r[0] for r in rows]
    except Exception as _e:
        logging.warning("Could not load user preferences: %s", _e)
        return []


def _sync_prefs_to_session() -> None:
    """Populate in-memory sets from DuckDB on first load (or after rerun)."""
    bookmarks = _pref_load("bookmark")
    st.session_state.bookmarks = set(bookmarks)
    recent = _pref_load("recent", limit=50)
    st.session_state.recent_views = recent


def run_query(query, params=None):
    # ── Demo mode: return hardcoded DataFrames without hitting any DB ──────────
    if os.getenv("DEMO_DATA", "false").lower() == "true":
        p = params or {}
        if "full_name" in p and "groups" in p:
            return _DEMO_RELATED.get(p["full_name"], pd.DataFrame(
                columns=["full_name", "table_name", "catalog_name", "schema_name", "relationship"]))
        if "groups" in p:
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



def is_power_user() -> bool:
    """True if the current user belongs to at least one EDITOR_GROUPS group."""
    editor_groups = {g.strip() for g in os.getenv("EDITOR_GROUPS", "").split(",") if g.strip()}
    if not editor_groups:
        return False
    return bool(editor_groups & set(st.session_state.get("user_groups", [])))


def is_admin() -> bool:
    """True if the current user belongs to at least one ADMIN_GROUPS group.

    No demo-mode bypass — admins must be in the real Entra group even in
    demo/development mode, unlike is_power_user() which has a mock shortcut.
    """
    admin_groups = {g.strip() for g in os.getenv("ADMIN_GROUPS", "").split(",") if g.strip()}
    if not admin_groups:
        return False
    return bool(admin_groups & set(st.session_state.get("user_groups", [])))


def get_column_business_names(table_full_name: str) -> dict:
    """Return all column business name overrides for a table as a dict.

    Returns: {column_name: {"business_name": str, "edited_by": str, "edited_at": str}}
    One bulk query — not N per-column queries.
    In demo mode reads from session state instead of Databricks.
    """
    if os.getenv("DEMO_DATA", "false").lower() == "true":
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


def log_audit_event(event_type: str, object_type: str, object_name: str, old_value: str, new_value: str) -> None:
    """Record an audit event for admin review.  Never raises — failures are logged and swallowed."""
    actor_email = st.session_state.get("user_email", "")
    event_id = str(uuid.uuid4())
    try:
        if os.getenv("DEMO_DATA", "false").lower() == "true":
            st.session_state.setdefault("demo_audit_log", []).append({
                "event_id":    event_id,
                "event_type":  event_type,
                "object_type": object_type,
                "object_name": object_name,
                "actor_email": actor_email,
                "old_value":   old_value,
                "new_value":   new_value,
                "created_at":  pd.Timestamp.now(),
            })
        else:
            conn = _get_write_connection()
            with conn.cursor() as cursor:
                table_name = "user_data.audit_log" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log"
                cursor.execute_write(
                    f"INSERT INTO {table_name} "
                    f"(event_id, event_type, object_type, object_name, actor_email, old_value, new_value, created_at) "
                    f"VALUES (%(event_id)s, %(event_type)s, %(object_type)s, %(object_name)s, "
                    f"%(actor_email)s, %(old_value)s, %(new_value)s, current_timestamp())",
                    {
                        "event_id":    event_id,
                        "event_type":  event_type,
                        "object_type": object_type,
                        "object_name": object_name,
                        "actor_email": actor_email,
                        "old_value":   old_value,
                        "new_value":   new_value,
                    },
                )
    except Exception as e:
        logging.warning("Audit logging failed for %s: %s", event_id, e)


def save_business_name(table_full_name: str, column_name: str, business_name: str, definition: str = "") -> None:
    """Atomically upsert a column override (business name + definition) using MERGE INTO.

    Raises:
        PermissionError: if the current session user is not a power user.
        ValueError: if business_name or definition exceeds MAX_BUSINESS_NAME_LEN characters.

    In demo mode writes to session state (ephemeral, lost on browser close).
    Demo mode structure: {table_full_name: {column_name: {business_name, definition, ...}}}
    """
    if not is_power_user():
        raise PermissionError("Only power users can save business name overrides.")
    if len(business_name) > MAX_BUSINESS_NAME_LEN:
        raise ValueError(
            f"Business name must be {MAX_BUSINESS_NAME_LEN} characters or fewer "
            f"(got {len(business_name)})."
        )
    if len(definition) > MAX_BUSINESS_NAME_LEN:
        raise ValueError(
            f"Definition must be {MAX_BUSINESS_NAME_LEN} characters or fewer "
            f"(got {len(definition)})."
        )
    user_name = st.session_state.get("user_name", "unknown")
    old_override = get_column_business_names(table_full_name).get(column_name, {})
    old_value = old_override.get("business_name", "")
    if os.getenv("DEMO_DATA", "false").lower() == "true":
        if "demo_business_names" not in st.session_state:
            st.session_state["demo_business_names"] = {}
        tbl = st.session_state["demo_business_names"].setdefault(table_full_name, {})
        tbl[column_name] = {"business_name": business_name, "definition": definition, "edited_by": user_name, "edited_at": "just now"}
        log_audit_event("business_name_change", "COLUMN", f"{table_full_name}.{column_name}", old_value, business_name)
        return
    # Use DuckDB if available, otherwise Databricks
    conn = _get_write_connection()
    with conn.cursor() as cursor:
        if _duckdb_available():
            cursor.execute_write(
                """
                INSERT INTO user_data.business_name_overrides (
                    table_full_name, column_name, business_name, definition, edited_by, edited_at
                ) VALUES (
                    %(table_full_name)s, %(column_name)s, %(business_name)s, %(definition)s, %(edited_by)s, current_timestamp()
                )
                ON CONFLICT (table_full_name, column_name) DO UPDATE SET
                    business_name = excluded.business_name,
                    definition = excluded.definition,
                    edited_by = excluded.edited_by,
                    edited_at = excluded.edited_at
                """,
                {
                    "table_full_name": table_full_name,
                    "column_name": column_name,
                    "business_name": business_name,
                    "definition": definition,
                    "edited_by": user_name,
                },
            )
        else:
            cursor.execute(
                f"MERGE INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides AS target "
                f"USING (SELECT %(table_full_name)s AS table_full_name, %(column_name)s AS column_name, %(business_name)s AS business_name, %(definition)s AS definition, %(edited_by)s AS edited_by) AS source "
                f"ON target.table_full_name = source.table_full_name AND target.column_name = source.column_name "
                f"WHEN MATCHED THEN UPDATE SET target.business_name = source.business_name, target.definition = source.definition, target.edited_by = source.edited_by, target.edited_at = current_timestamp() "
                f"WHEN NOT MATCHED THEN INSERT (table_full_name, column_name, business_name, definition, edited_by, edited_at) VALUES (source.table_full_name, source.column_name, source.business_name, source.definition, source.edited_by, current_timestamp())",
                {"table_full_name": table_full_name, "column_name": column_name, "business_name": business_name, "definition": definition, "edited_by": user_name},
            )
    log_audit_event("business_name_change", "COLUMN", f"{table_full_name}.{column_name}", old_value, business_name)


def get_table_steward(table_full_name: str) -> str:
    """Return the steward_email for a table, or '' if unset.

    In demo mode returns a fixed placeholder address so email flow can be tested.
    Not cached — always fresh so steward changes are reflected without restart.
    """
    if os.getenv("DEMO_DATA", "false").lower() == "true":
        return "steward@example.com"
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT steward_email FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata "
                f"WHERE full_name = %(full_name)s LIMIT 1",
                {"full_name": table_full_name},
            )
            row = cursor.fetchall_as_pandas()
            if row is not None and not row.empty:
                return str(row.iloc[0]["steward_email"] or "")
    except Exception as e:
        logging.warning("Could not fetch steward for %s: %s", table_full_name, e)
    return ""


def get_table_comments(object_name: str) -> list:
    """Fetch all comments for an object, returned as a tree (parent comments
    with a ``replies`` list each).

    In demo mode reads from st.session_state["demo_comments"].
    Not cached — always fresh so new comments appear immediately.
    """
    if os.getenv("DEMO_DATA", "false").lower() == "true":
        flat = st.session_state.get("demo_comments", {}).get(object_name, [])
        return _build_comment_tree(flat)
    try:
        conn = get_db_connection()
        tbl = "user_data.comments" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.comments"
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT comment_id, author_name, author_email, comment_text, created_at, parent_comment_id "
                f"FROM {tbl} "
                f"WHERE object_name = %(object_name)s ORDER BY created_at ASC",
                {"object_name": object_name},
            )
            rows = cursor.fetchall_as_pandas()
            if rows is not None and not rows.empty:
                return _build_comment_tree(rows.to_dict(orient="records"))
    except Exception as e:
        logging.warning("Could not fetch comments for %s: %s", object_name, e)
    return []


def _build_comment_tree(flat: list) -> list:
    """Group a flat list of comment dicts into a parent/replies tree."""
    by_id = {c["comment_id"]: {**c, "replies": []} for c in flat}
    roots = []
    for c in by_id.values():
        pid = c.get("parent_comment_id")
        if pid and pid in by_id:
            by_id[pid]["replies"].append(c)
        else:
            roots.append(c)
    return roots


def send_comment_email(to_email: str, author_name: str, object_name: str, comment_text: str) -> None:
    """Send a comment notification email to the data steward.

    In demo mode logs to console instead of sending. Silently skips if
    SMTP_HOST or to_email is not configured rather than raising.
    """
    import smtplib
    from email.mime.text import MIMEText

    if os.getenv("DEMO_DATA", "false").lower() == "true":
        print(f"[DEMO EMAIL] To: {to_email} | Object: {object_name} | From: {author_name}\n{comment_text}")
        return
    smtp_host = os.getenv("SMTP_HOST", "")
    if not smtp_host or not to_email:
        logging.warning("Comment saved but email not sent: SMTP_HOST or steward_email not configured.")
        return
    # Strip newlines from header fields to prevent SMTP header injection.
    safe_object_name = object_name.replace("\r", "").replace("\n", "")
    safe_author_name = author_name.replace("\r", "").replace("\n", "")
    msg = MIMEText(f"{safe_author_name} left a comment on {safe_object_name}:\n\n{comment_text}", "plain")
    msg["Subject"] = f"[Data Dictionary] Comment on {safe_object_name}"
    msg["From"]    = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", ""))
    msg["To"]      = to_email
    try:
        with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", "587"))) as s:
            s.starttls()
            s.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
            s.sendmail(msg["From"], [to_email], msg.as_string())
        logging.info("Comment email sent to %s", to_email)
    except Exception as e:
        logging.error("Failed to send comment email to %s: %s", to_email, e)


def send_reply_email(
    parent_author_email: str,
    reply_author_name: str,
    object_name: str,
    reply_text: str,
    steward_email: str,
) -> None:
    """Notify the original commenter (and the steward if different) of a reply.

    In demo mode logs to console. Silently skips if SMTP_HOST is not configured.
    """
    import smtplib
    from email.mime.text import MIMEText

    recipients = list({e for e in [parent_author_email, steward_email] if e})
    if not recipients:
        return

    if os.getenv("DEMO_DATA", "false").lower() == "true":
        print(f"[DEMO REPLY] To: {recipients} | Object: {object_name} | From: {reply_author_name}\n{reply_text}")
        return

    smtp_host = os.getenv("SMTP_HOST", "")
    if not smtp_host:
        logging.warning("Reply saved but email not sent: SMTP_HOST not configured.")
        return

    # Strip newlines from header fields to prevent SMTP header injection.
    safe_object_name  = object_name.replace("\r", "").replace("\n", "")
    safe_reply_author = reply_author_name.replace("\r", "").replace("\n", "")
    msg = MIMEText(
        f"{safe_reply_author} replied to a comment on {safe_object_name}:\n\n{reply_text}",
        "plain",
    )
    msg["Subject"] = f"[Data Dictionary] Reply on {safe_object_name}"
    msg["From"]    = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", ""))
    msg["To"]      = ", ".join(recipients)
    try:
        with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", "587"))) as s:
            s.starttls()
            s.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
            s.sendmail(msg["From"], recipients, msg.as_string())
        logging.info("Reply email sent to %s", recipients)
    except Exception as e:
        logging.error("Failed to send reply email to %s: %s", recipients, e)


def _fetch_comment_author_email(comment_id: str) -> str:
    """Look up the author_email of a comment from the DB.

    Used by save_comment to resolve the reply recipient server-side rather
    than trusting the value passed in from the UI (open-relay mitigation).
    Returns '' if the comment is not found or on error.
    """
    try:
        conn = get_db_connection()
        tbl = "user_data.comments" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.comments"
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT author_email FROM {tbl} "
                f"WHERE comment_id = %(comment_id)s LIMIT 1",
                {"comment_id": comment_id},
            )
            row = cursor.fetchall_as_pandas()
            if row is not None and not row.empty:
                return str(row.iloc[0]["author_email"] or "")
    except Exception as e:
        logging.warning("Could not fetch author_email for comment %s: %s", comment_id, e)
    return ""


def save_comment(
    object_type: str,
    object_name: str,
    comment_text: str,
    steward_email: str,
    parent_comment_id: str = None,
    parent_author_email: str = "",
) -> None:
    """Persist a comment (or reply) and trigger notification emails.

    For a top-level comment, notifies the steward.
    For a reply (parent_comment_id set), notifies the original commenter and steward.

    The reply recipient email is re-fetched from the database rather than
    trusting the caller-supplied parent_author_email, preventing an
    authenticated user from using the SMTP relay to spam arbitrary addresses.
    parent_author_email is used only in demo mode (no DB available).

    In demo mode writes to st.session_state["demo_comments"] dict.
    object_name for table comments is the full_name; for column comments
    it is "{full_name}::{column_name}".
    """
    import uuid
    comment_id   = str(uuid.uuid4())
    author_name  = st.session_state.get("user_name", "unknown")
    author_email = (st.session_state.get("user_email", "") or "").lower().strip()

    _event_type = "comment_reply" if parent_comment_id else "comment_added"

    if os.getenv("DEMO_DATA", "false").lower() == "true":
        demo = st.session_state.setdefault("demo_comments", {})
        demo.setdefault(object_name, []).append({
            "comment_id":        comment_id,
            "author_name":       author_name,
            "author_email":      author_email,
            "comment_text":      comment_text,
            "created_at":        "just now",
            "parent_comment_id": parent_comment_id,
        })
        if parent_comment_id:
            send_reply_email(parent_author_email, author_name, object_name, comment_text, steward_email)
        else:
            send_comment_email(steward_email, author_name, object_name, comment_text)
        log_audit_event(_event_type, object_type, object_name, "", comment_text)
        return

    conn = _get_write_connection()
    with conn.cursor() as cursor:
        if _duckdb_available():
            cursor.execute_write(
                "INSERT INTO user_data.comments "
                "(comment_id, object_type, object_name, comment_text, author_name, author_email, "
                "created_at, steward_email, parent_comment_id) "
                "VALUES (%(comment_id)s, %(object_type)s, %(object_name)s, %(comment_text)s, "
                "%(author_name)s, %(author_email)s, current_timestamp(), %(steward_email)s, %(parent_comment_id)s)",
                {
                    "comment_id":        comment_id,
                    "object_type":       object_type,
                    "object_name":       object_name,
                    "comment_text":      comment_text,
                    "author_name":       author_name,
                    "author_email":      author_email,
                    "steward_email":     steward_email,
                    "parent_comment_id": parent_comment_id,
                },
            )
        else:
            cursor.execute(
                f"INSERT INTO {CATALOG_CACHE}.{SCHEMA_CACHE}.comments "
                f"(comment_id, object_type, object_name, comment_text, author_name, author_email, "
                f"created_at, steward_email, parent_comment_id) "
                f"VALUES (%(comment_id)s, %(object_type)s, %(object_name)s, %(comment_text)s, "
                f"%(author_name)s, %(author_email)s, current_timestamp(), %(steward_email)s, %(parent_comment_id)s)",
                {
                    "comment_id":        comment_id,
                    "object_type":       object_type,
                    "object_name":       object_name,
                    "comment_text":      comment_text,
                    "author_name":       author_name,
                    "author_email":      author_email,
                    "steward_email":     steward_email,
                    "parent_comment_id": parent_comment_id,
                },
            )
    if parent_comment_id:
        # Re-fetch the parent author's email from the DB — do NOT trust the
        # UI-supplied parent_author_email to prevent open-relay abuse.
        verified_parent_email = _fetch_comment_author_email(parent_comment_id)
        send_reply_email(verified_parent_email, author_name, object_name, comment_text, steward_email)
    else:
        send_comment_email(steward_email, author_name, object_name, comment_text)
    log_audit_event(_event_type, object_type, object_name, "", comment_text)


@st.cache_data(ttl="1h")
def get_authorized_tables(groups):
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
            m.updated_at
        FROM {0}.{1}.tables_metadata m
        JOIN {0}.{1}.permissions_cache p
          ON m.full_name = p.table_full_name
        WHERE (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS')
    """).format(CATALOG_CACHE, SCHEMA_CACHE, group_placeholders)  # nosec B608

    return run_query(sql_query, params)


# ── Feature scaffolds (stubs — to be implemented) ─────────────────────────────

@st.cache_data(ttl="1h")
def get_multi_hop_lineage(table_full_name: str, depth: int = 1):
    """Fetch lineage edges up to a given depth.

    TODO (feature/enhanced-lineage): Implement recursive traversal of
    lineage_cache to support multi-hop exploration with vis-network node events.
    """
    return run_query(
        ("SELECT * FROM {0}.{1}.lineage_cache WHERE table_full_name = %(fn)s").format(
            CATALOG_CACHE, SCHEMA_CACHE
        ),
        {"fn": table_full_name},
    )


@st.cache_data(ttl="1h")
def global_search_metadata(query: str, groups: tuple):
    """Search across tables, columns, and descriptions.

    TODO (feature/unified-search): Replace placeholder UNION query with a
    full multi-table search across tables_metadata, columns_metadata, and
    glossary, returning ranked results with match_type labels.
    """
    import logging
    logging.info("GLOBAL SEARCH query=%s groups=%s", query, groups)
    group_placeholders = ", ".join([f"%(group_{i})s" for i in range(len(groups))]) if groups else "''"
    params: dict = {f"group_{i}": g for i, g in enumerate(groups)} if groups else {}
    params["q"] = f"%{query}%"
    sql_query = ("""
        SELECT DISTINCT m.full_name, m.table_name, 'Table' as match_type
        FROM {0}.{1}.tables_metadata m
        JOIN {0}.{1}.permissions_cache p ON m.full_name = p.table_full_name
        WHERE m.table_name LIKE %(q)s
          AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS')
        LIMIT 20
    """).format(CATALOG_CACHE, SCHEMA_CACHE, group_placeholders)  # nosec B608
    return run_query(sql_query, params)


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
        if all_data.empty:
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
                    tables = sorted(sch_data['table_name'].unique().tolist())
                    
                    # Columns for tables to make it more compact
                    t_cols = st.columns(3)
                    for i, tbl in enumerate(tables):
                        with t_cols[i % 3]:
                            full_n = f"{cat}.{sch}.{tbl}"
                            if st.button(f"📄 {tbl}", key=f"tree_{full_n}", use_container_width=True):
                                st.query_params["tab"] = "search"
                                st.session_state["dd_search_override"] = tbl
                                st.session_state["dd_nav_select"] = full_n
                                st.rerun()
    except Exception as e:
        logging.error("Error in catalog browser: %s", e)
        st.error(t("catalog.load_error"))

def render_glossary():
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
        "Search for a term",
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
            
            for table_fn in term_row["related_tables"]:
                if st.button(f"📄 {table_fn}", key=f"gloss_link_{table_fn}", use_container_width=True):
                    st.query_params["tab"] = "search"
                    st.session_state["dd_search_override"] = table_fn.split(".")[-1]
                    st.session_state["dd_nav_select"] = table_fn
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
    """Shared card layout used in New & Notable and My Bookmarks."""
    _ts = row.get("updated_at")
    if isinstance(_ts, pd.Timestamp):
        _time_str = _ts.strftime(t("discovery.date_format"))
    else:
        _time_str = str(_ts) if _ts else ""

    _full = str(row.get("full_name", ""))
    _is_bk = _full in st.session_state.get("bookmarks", set())
    _bk_icon = "★" if _is_bk else "☆"

    st.markdown(f'''
    <div style="background:var(--paper); border:1px solid var(--ink-10); padding:20px; margin-bottom:16px; border-radius:2px;">
        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px;">
            <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em;">{_html.escape(str(row.get("catalog_name","")))} · {_html.escape(str(row.get("schema_name","")))}</div>
            <div style="font-family:var(--font-mono); font-size:11px; color:var(--accent);">{t("discovery.updated")} {_time_str}</div>
        </div>
        <div style="font-family:var(--font-mono); font-size:18px; font-weight:600; color:var(--ink); margin-bottom:8px;">{_html.escape(str(row.get("table_name","")))}</div>
        <p style="font-family:var(--font-sans); font-size:14px; color:var(--ink-60); line-height:1.5; margin-bottom:16px;">{_html.escape(str(row.get("table_description","")))}</p>
    </div>
    ''', unsafe_allow_html=True)

    c1, c2 = st.columns([3, 1])
    with c1:
        if st.button(t("discovery.explore_button", name=row.get("table_name", "")), key=f"{key_prefix}_exp_{_full}", type="secondary"):
            st.query_params["tab"] = "search"
            st.session_state["dd_search_override"] = row.get("table_name", "")
            st.session_state["dd_nav_select"] = _full
            st.rerun()
    with c2:
        _bk_label = t("personalization.remove_bookmark") if _is_bk else t("personalization.add_bookmark")
        if st.button(f"{_bk_icon} {_bk_label}", key=f"{key_prefix}_bk_{_full}"):
            if _is_bk:
                st.session_state.bookmarks.discard(_full)
                _pref_delete(_full, "bookmark")
            else:
                st.session_state.bookmarks.add(_full)
                _pref_upsert(_full, "bookmark")
            st.rerun()


def render_discovery(groups):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("discovery.title")}</div>
      <h1>{t("discovery.hero_title")}</h1>
      <p class="lead">{t("discovery.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    tab_notable, tab_bookmarks, tab_recent = st.tabs([
        t("personalization.tab_notable"),
        t("personalization.tab_bookmarks"),
        t("personalization.tab_recent"),
    ])

    # ── New & Notable ────────────────────────────────────────────────────────────
    with tab_notable:
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
    with tab_bookmarks:
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

    # ── Recently Viewed ──────────────────────────────────────────────────────────
    with tab_recent:
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
        if os.getenv("DEMO_DATA", "false").lower() == "true":
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
    if os.getenv("DEMO_DATA", "false").lower() == "true":
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
        tables_tbl    = "tables_metadata"                   if _ud else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata"
        columns_tbl   = "columns_metadata"                  if _ud else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata"
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
    if os.getenv("DEMO_DATA", "false").lower() == "true":
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
    if os.getenv("DEMO_DATA", "false").lower() == "true":
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


def render_admin_page():
    if not is_admin():
        st.error(t("admin.access_denied"))
        st.stop()

    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("admin.title")}</div>
      <h1>Administration.</h1>
      <p class="lead">{t("health.subtitle")}</p>
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


# ── App entry point ────────────────────────────────────────────────────────────
render_css()

# ── Auth gate ─────────────────────────────────────────────────────────────────
ENABLE_MOCK_AUTH = os.getenv("ENABLE_MOCK_AUTH", "false").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()

if ENABLE_MOCK_AUTH and ENVIRONMENT == "development":
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    # Personalization state — seed from DuckDB, fall back to empty
    if "bookmarks" not in st.session_state:
        st.session_state.bookmarks = set()
    if "recent_views" not in st.session_state:
        st.session_state.recent_views = []
    if not st.session_state.get("_prefs_loaded"):
        _sync_prefs_to_session()
        st.session_state["_prefs_loaded"] = True
    
    # Auto-login if returning from a nav link
    if st.query_params.get("mock_login") == "true":
        st.session_state.authenticated = True
        st.session_state.user_groups = ["finance_dept_id", "all_employees_id"]
        st.session_state.user_name  = "Finance User"
        st.session_state.user_email = "finance.user@example.com"
    if not st.session_state.authenticated:
        render_header()
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

groups = tuple(st.session_state.user_groups) if st.session_state.user_groups else ("none",)
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
        all_results = get_authorized_tables(query_groups)
        table_options = sorted(all_results['table_name'].unique().tolist())
    except Exception as e:
        logging.error("Error querying data: %s", e, exc_info=True)
        st.error(t("search.load_error"))
        all_results = None
        table_options = []

    search_query = st.selectbox(
        t("common.search"),
        options=table_options,
        index=table_options.index(st.session_state.get("catalog_search")) if st.session_state.get("catalog_search") in table_options else None,
        placeholder=t("search.placeholder"),
        label_visibility="collapsed",
        key="catalog_search",
    )

    # Detect table change — clear transient state so edits don't bleed across tables
    _prev_table = st.session_state.get("_dd_current_table")
    if _prev_table is not None and _prev_table != search_query:
        _clear_transient_edit_state()
    st.session_state["_dd_current_table"] = search_query

    if search_query and all_results is not None:
        try:
            results = all_results[all_results['table_name'] == search_query]
            if not results.empty:
                col_main_detail, col_side_detail = st.columns([7, 5], gap="large")
                _table_names = results["table_name"].tolist()
                _nav_target  = st.session_state.pop("dd_nav_select", None)
                _nav_idx = 0 if len(_table_names) > 0 else None
                if _nav_target:
                    _nav_name = _nav_target.split(".")[-1]
                    if _nav_name in _table_names:
                        _nav_idx = _table_names.index(_nav_name)

                if _nav_idx is not None:
                    selected_table = _table_names[_nav_idx]
                    row = results[results["table_name"] == selected_table].iloc[0]
                    full_name = f"{row['catalog_name']}.{row['schema_name']}.{row['table_name']}"
                    with col_main_detail:
                        _cat, _sch, _tbl = _html.escape(str(row['catalog_name'])), _html.escape(str(row['schema_name'])), _html.escape(str(row['table_name']))
                        _raw_desc = row.get('table_description', '')
                        _desc = _html.escape(str(_raw_desc) if isinstance(_raw_desc, str) else '')
                        _host = os.getenv("DATABRICKS_HOST", "").strip()
                        _ext_link = f'<a href="https://{_host}/explore/data/{_cat}/{_sch}/{_tbl}" target="_blank" class="dd-link-external">{t("table.open_in_databricks")} ↗</a>' if _host else ''

                        # Section header
                        st.markdown(f'<div class="dd-detail-header" style="margin-top: 0;"><span class="dd-eyebrow" style="margin-bottom:0">{t("detail.title")}</span></div>', unsafe_allow_html=True)

                        # Table identity block
                        st.markdown(
                            f'<div class="dd-eyebrow" style="margin-bottom:4px">{_cat} · {_sch}</div>'
                            f'<div class="dd-detail-table-name">{_tbl}</div>'
                            f'<p class="dd-detail-desc">{_desc}</p>{_ext_link}',
                            unsafe_allow_html=True,
                        )
                        st.code(full_name, language=None)

                        # --- § Bookmark + recent-view tracking ---
                        _is_bookmarked = full_name in st.session_state.get("bookmarks", set())
                        _bk_label = t("personalization.remove_bookmark") if _is_bookmarked else t("personalization.add_bookmark")
                        if st.button(_bk_label, key=f"bk_{full_name}", type="secondary"):
                            if _is_bookmarked:
                                st.session_state.bookmarks.discard(full_name)
                                _pref_delete(full_name, "bookmark")
                            else:
                                st.session_state.bookmarks.add(full_name)
                                _pref_upsert(full_name, "bookmark")
                            st.rerun()

                        # Record this table as recently viewed
                        _rv = st.session_state.get("recent_views", [])
                        if not _rv or _rv[0] != full_name:
                            _rv = [full_name] + [x for x in _rv if x != full_name][:49]
                            st.session_state.recent_views = _rv
                            _pref_upsert(full_name, "recent")

                        # --- § Columns ---
                        # Bulk-fetch overrides first (one query for all columns)
                        col_overrides = get_column_business_names(full_name)

                        cols_query = ("SELECT column_name, data_type, comment FROM {0}.{1}.columns_metadata WHERE table_full_name = %(table_full_name)s ORDER BY column_name").format(CATALOG_CACHE, SCHEMA_CACHE)
                        cols = run_query(cols_query, {"table_full_name": full_name})
                        n_cols = len(cols) if cols is not None and not cols.empty else 0
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
                                _r_name, _r_type, _r_desc, _r_btn = st.columns([3, 2, 5, 1], gap="small")

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

                                if _col_edit == _edit_key:
                                    st.markdown('<div class="dd-edit-banner">Edit mode — changes are saved immediately and visible to all users.</div>', unsafe_allow_html=True)
                                    _inp_name = st.text_input(
                                        "Business name",
                                        value=_col_biz,
                                        placeholder="e.g. Customer ID",
                                        max_chars=MAX_BUSINESS_NAME_LEN,
                                        key=f"col_biz_name_{_edit_key}",
                                    )
                                    _inp_def = st.text_input(
                                        "Definition",
                                        value=_col_def,
                                        placeholder="e.g. Unique identifier assigned to each customer at registration.",
                                        max_chars=MAX_BUSINESS_NAME_LEN,
                                        key=f"col_biz_def_{_edit_key}",
                                    )
                                    _sc, _cc, _ = st.columns([2, 2, 4], gap="small")
                                    with _sc:
                                        if st.button("Save", key=f"col_biz_save_{_edit_key}", use_container_width=True):
                                            try:
                                                save_business_name(full_name, _cname, _inp_name.strip(), _inp_def.strip())
                                                st.session_state.pop("dd_col_edit_mode", None)
                                                st.rerun()
                                            except PermissionError:
                                                st.error("You do not have permission to edit business names.")
                                            except ValueError as exc:
                                                st.error(str(exc))
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
                        grants_query = ("SELECT DISTINCT principal, privilege FROM {0}.{1}.permissions_cache WHERE table_full_name = %(table_full_name)s ORDER BY principal").format(CATALOG_CACHE, SCHEMA_CACHE)
                        grants = run_query(grants_query, {"table_full_name": full_name})
                        n_grants = len(grants) if grants is not None and not grants.empty else 0
                        st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_grants")}</span><span class="dd-section-count">{n_grants}</span></div>', unsafe_allow_html=True)
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

                        # --- § Lineage ---
                        lineage_query = ("SELECT direction, entity_full_name, entity_type FROM {0}.{1}.lineage_cache WHERE table_full_name = %(table_full_name)s ORDER BY direction, entity_full_name").format(CATALOG_CACHE, SCHEMA_CACHE)
                        lineage = run_query(lineage_query, {"table_full_name": full_name})
                        has_lineage = lineage is not None and not lineage.empty
                        
                        # --- § Related tables ---
                        rel_group_placeholders = ", ".join([f"%(group_{i})s" for i in range(len(query_groups))]) if query_groups else "''"
                        rel_params = {"catalog_name": row["catalog_name"], "schema_name": row["schema_name"], "full_name": full_name}
                        if query_groups:
                            for i, group in enumerate(query_groups):
                                rel_params[f"group_{i}"] = group

                        related_query = ("SELECT t.full_name, t.table_name, t.catalog_name, t.schema_name, 'Same schema' AS relationship FROM {0}.{1}.tables_metadata t JOIN {0}.{1}.permissions_cache p ON t.full_name = p.table_full_name WHERE t.catalog_name = %(catalog_name)s AND t.schema_name = %(schema_name)s AND t.full_name != %(full_name)s AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS') UNION SELECT DISTINCT t.full_name, t.table_name, t.catalog_name, t.schema_name, 'Shared column' AS relationship FROM {0}.{1}.columns_metadata c1 JOIN {0}.{1}.columns_metadata c2 ON c1.column_name = c2.column_name JOIN {0}.{1}.tables_metadata t ON c2.table_full_name = t.full_name JOIN {0}.{1}.permissions_cache p ON t.full_name = p.table_full_name WHERE c1.table_full_name = %(full_name)s AND c2.table_full_name != %(full_name)s AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS') LIMIT 12").format(CATALOG_CACHE, SCHEMA_CACHE, rel_group_placeholders)  # nosec B608
                        related = run_query(related_query, rel_params)
                        n_related = len(related) if related is not None and not related.empty else 0
                        
                        st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0">{t("detail.section_lineage")} & {t("detail.section_related")}</span><span class="dd-section-count">{n_related} {t("detail.related_count")}</span></div>', unsafe_allow_html=True)
                        
                        graph_nodes = [{"id": full_name, "label": _tbl, "current": True, "relationship": "Current"}]
                        graph_links = []
                        if has_lineage:
                            upstreams = lineage[lineage["direction"] == "UPSTREAM"]["entity_full_name"].tolist()
                            downstreams = lineage[lineage["direction"] == "DOWNSTREAM"]["entity_full_name"].tolist()
                            for efn in upstreams:
                                graph_nodes.append({"id": efn, "label": efn.split(".")[-1], "current": False, "relationship": "Upstream"})
                                graph_links.append({"from": efn, "to": full_name})
                            for efn in downstreams:
                                graph_nodes.append({"id": efn, "label": efn.split(".")[-1], "current": False, "relationship": "Downstream"})
                                graph_links.append({"from": full_name, "to": efn})
                        if n_related > 0:
                            for _, rel in related.iterrows():
                                _rel_full, _rel_name, _rel_raw_badge = str(rel.get("full_name", "")), _html.escape(str(rel.get("table_name", ""))), str(rel.get("relationship", ""))
                                _rel_badge = t("detail.same_schema") if _rel_raw_badge == "Same schema" else (t("detail.shared_column") if _rel_raw_badge == "Shared column" else _html.escape(_rel_raw_badge))
                                if not any(n["id"] == _rel_full for n in graph_nodes): graph_nodes.append({"id": _rel_full, "label": _rel_name, "current": False, "relationship": _rel_badge})
                                if not any((l["from"] == full_name and l["to"] == _rel_full) or (l["from"] == _rel_full and l["to"] == full_name) for l in graph_links): graph_links.append({"from": full_name, "to": _rel_full})
                        
                        import json
                        graph_html = f'''<div id="mynetwork" style="width: 100%; height: 350px; background: #F2EDE1; border-radius: 4px; border: 1px solid #C9C2B4; overflow: hidden; margin-top: 16px;"></div><script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script><script type="text/javascript">var nodes = new vis.DataSet({json.dumps(graph_nodes)}); var edges = new vis.DataSet({json.dumps(graph_links)}); var container = document.getElementById('mynetwork'); var data = {{ nodes: nodes, edges: edges }}; var options = {{ nodes: {{ shape: 'box', margin: 10, font: {{ size: 14, face: 'sans-serif' }}, borderWidth: 1, shadow: true }}, edges: {{ arrows: 'to', color: '#C9C2B4', smooth: {{ type: 'cubicBezier', forceDirection: 'horizontal' }} }}, physics: {{ barnesHut: {{ springLength: 100, springConstant: 0.04 }}, minVelocity: 0.75 }}, interaction: {{ hover: false, dragNodes: true, dragView: true, zoomView: true }} }}; var updatedNodes = []; nodes.forEach(function(node) {{ var isCurrent = node.current; var rel = node.relationship; var bg = isCurrent ? '#B8362A' : (rel === 'Shared column' ? '#DDE4EC' : '#FAF7F0'); var border = isCurrent ? '#8C271E' : (rel === 'Shared column' ? '#2B4A6B' : '#C9C2B4'); var text = isCurrent ? '#FAF7F0' : (rel === 'Shared column' ? '#2B4A6B' : '#14110C'); updatedNodes.push({{ id: node.id, color: {{ background: bg, border: border, highlight: {{ background: bg, border: border }} }}, font: {{ color: text }} }}); }}); nodes.update(updatedNodes); var network = new vis.Network(container, data, options); network.once("stabilizationIterationsDone", function() {{ network.fit(); }});</script>'''
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
    render_glossary()
elif current_tab == "discovery":
    render_discovery(query_groups)
elif current_tab == "health":
    render_health(query_groups)
elif current_tab == "admin":
    render_admin_page()

st.markdown("</div>", unsafe_allow_html=True)
render_footer()
