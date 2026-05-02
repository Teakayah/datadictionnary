"""Authentication and authorization logic.

Handles Microsoft Entra ID (OIDC) via MSAL, mock authentication for development,
and role-based access control (RBAC) checks.

Public API:
    get_msal_app()         — cached MSAL ConfidentialClientApplication singleton
    render_signin_page()   — two-column editorial sign-in layout
    check_auth()           — main auth gate (OIDC flow + session init)
    is_power_user()        — True if user is in EDITOR_GROUPS
    is_admin()             — True if user is in ADMIN_GROUPS

Dependencies: msal, streamlit, src.config, src.i18n, src.ui.header
ENABLE_MOCK_AUTH and ENVIRONMENT are NOT imported here — they are inline
os.getenv() reads in app.py so per-test env overrides work correctly.
"""

from __future__ import annotations

import logging
import os
import secrets

import msal
import streamlit as st

from src.config import (
    CLIENT_ID, AUTHORITY, CLIENT_SECRET, SCOPE, REDIRECT_URI, MOCK_DEPT,
)
from src.i18n import t
from src.ui.header import render_footer, MS_LOGO_SVG


@st.cache_resource(show_spinner=False)
def get_msal_app():
    """Initialize the MSAL ConfidentialClientApplication singleton."""
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
                "Admin":    (
                    ["finance_group", "research_group", "hr_group", "it_group",
                     "SELECT_ALL_USERS", "finance_dept_id", "all_employees_id"],
                    "admin@research-org.ca",
                ),
            }
            _default_dept = MOCK_DEPT
            _dept_opts = list(_MOCK_DEPTS.keys())
            _dept_sel = st.selectbox(
                "Department",
                _dept_opts,
                index=_dept_opts.index(_default_dept) if _default_dept in _dept_opts else 0,
                label_visibility="collapsed",
            )
            if st.button(t("auth.sign_in"), use_container_width=True, type="primary"):
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


def check_auth(sync_prefs_callback: callable | None = None):
    """Main authentication gate. Handles OIDC flow and session initialisation.

    Args:
        sync_prefs_callback: Optional callable to seed personalisation data on
                             first login (usually _sync_prefs_to_session).
    """
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = None

    if st.session_state.get("auth_token") is None:
        msal_app = get_msal_app()
        query_params = st.query_params

        if "code" in query_params:
            state = query_params.get("state")
            expected_state = st.session_state.get("oauth_state")

            if not state or not expected_state or state != expected_state:
                logging.error("OAuth state mismatch or missing.")
                st.error("Authentication failed: Security verification (state mismatch). Please try again.")
                for key in ("oauth_state", "oauth_nonce"):
                    st.session_state.pop(key, None)
                st.stop()

            expected_nonce = st.session_state.get("oauth_nonce")
            result = msal_app.acquire_token_by_authorization_code(
                query_params["code"], scopes=SCOPE,
                redirect_uri=REDIRECT_URI, nonce=expected_nonce,
            )

            for key in ("oauth_state", "oauth_nonce"):
                st.session_state.pop(key, None)

            if "access_token" in result:
                claims = result.get("id_token_claims", {})
                if expected_nonce and claims.get("nonce") != expected_nonce:
                    logging.error("OAuth nonce mismatch or missing.")
                    st.error("Authentication failed: Security verification (nonce mismatch).")
                    st.stop()

                st.session_state.auth_token  = result
                st.session_state.user_groups = claims.get("groups", [])
                st.session_state.user_name   = claims.get("name")
                st.session_state.user_email  = claims.get("email") or claims.get("preferred_username", "")
                st.session_state.user_oid    = claims.get("oid", "")

                if sync_prefs_callback:
                    sync_prefs_callback()
                st.session_state["_prefs_loaded"] = True

                st.query_params.clear()
                st.rerun()
            else:
                logging.error("Failed to acquire token: %s", result.get("error_description", "Unknown"))
                st.error("Authentication failed. Please try again.")
                st.stop()

        if "oauth_state" not in st.session_state:
            st.session_state.oauth_state = secrets.token_urlsafe(16)
        if "oauth_nonce" not in st.session_state:
            st.session_state.oauth_nonce = secrets.token_urlsafe(16)

        auth_url = msal_app.get_authorization_request_url(
            SCOPE,
            redirect_uri=REDIRECT_URI,
            state=st.session_state.oauth_state,
            nonce=st.session_state.oauth_nonce,
        )

        render_signin_page(auth_url=auth_url, mock=False)
        render_footer()
        st.stop()


def is_power_user() -> bool:
    """True if the current user belongs to at least one EDITOR_GROUPS group."""
    editor_groups = {g.strip() for g in os.getenv("EDITOR_GROUPS", "").split(",") if g.strip()}
    if not editor_groups:
        return False
    return bool(editor_groups & set(st.session_state.get("user_groups", [])))


def is_admin() -> bool:
    """True if the current user belongs to at least one ADMIN_GROUPS group.

    No demo-mode bypass — admins must be in the real Entra group even in
    demo/development mode, unlike is_power_user() which may have a mock shortcut.
    """
    admin_groups = {g.strip() for g in os.getenv("ADMIN_GROUPS", "").split(",") if g.strip()}
    if not admin_groups:
        return False
    return bool(admin_groups & set(st.session_state.get("user_groups", [])))
