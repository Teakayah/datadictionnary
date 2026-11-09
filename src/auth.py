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

Redirect-loop hardening
-----------------------
Three failure modes are guarded against:

1. Stale ?code in URL — query params are cleared on EVERY code-processing
   attempt (success or failure) so a second render never retries a spent code.

2. Token expiry — on each render the stored access token's expiry is checked.
   If it is within TOKEN_REFRESH_BUFFER_S of expiry, acquire_token_silent() is
   attempted first; if that fails the session is cleared for a clean re-auth.

3. State/nonce mismatch on session loss — the error path now clears params
   before stopping so the user lands on a clean sign-in page rather than an
   error loop.
"""
from __future__ import annotations
from typing import Optional



import logging
import functools
import os
import secrets
import time

import msal
import streamlit as st

from src.config import (
    CLIENT_ID, AUTHORITY, CLIENT_SECRET, SCOPE, REDIRECT_URI, MOCK_DEPT,
)
from src.i18n import t
from src.ui.header import render_footer, MS_LOGO_SVG

# Trigger a silent token refresh this many seconds before actual expiry.
TOKEN_REFRESH_BUFFER_S = 300  # 5 minutes


@st.cache_resource(show_spinner=False)
def get_msal_app():
    """Initialize the MSAL ConfidentialClientApplication singleton."""
    return msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )


def _clear_auth_session() -> None:
    """Wipe all auth-related session keys so the next render starts clean.

    Also drops the user's entry from the Graph groups cache so a fresh
    sign-in re-fetches their group membership instead of reading a stale
    1h-cached list. This is the piece that makes "sign out, sign back in"
    actually pick up new Entra group assignments.
    """
    user_oid = st.session_state.get("user_oid", "")
    if user_oid:
        from src.auth_graph import clear_groups_cache  # noqa: PLC0415
        clear_groups_cache(user_oid)
    for key in ("auth_token", "token_expires_at", "authenticated",
                "user_groups", "user_name", "user_email", "user_oid",
                "oauth_state", "oauth_nonce", "_prefs_loaded"):
        st.session_state.pop(key, None)


def _resolve_user_groups(claims: dict, access_token: str) -> list[str]:
    """Return the user's security-group membership list.

    Three branches:
      1. ID token has inline ``groups`` claim → use it (the common case).
      2. ID token signals overage (``_claim_names.groups`` set, no inline
         list) → fetch via Graph getMemberObjects. Affects users in
         >~150 groups; without this they would see zero tables.
      3. Neither → empty list. Logged once at INFO so a tenant misconfig
         (no groups at all) is visible in logs.
    """
    inline = claims.get("groups")
    if inline is not None:
        return list(inline)

    from src.auth_graph import fetch_member_groups, has_groups_overage  # noqa: PLC0415
    if has_groups_overage(claims):
        oid = claims.get("oid", "")
        logging.info("Groups overage detected for %s; fetching from Graph.", oid or "<no oid>")
        return fetch_member_groups(access_token, oid)

    logging.info("ID token contained no groups claim and no overage indicator.")
    return []


def _try_silent_refresh() -> bool:
    """Attempt a silent token refresh using MSAL's cached account.

    Args:
        None

    Returns:
        bool: True if a fresh token was successfully retrieved and stored, False otherwise.
    """
    try:
        msal_app = get_msal_app()
        email = st.session_state.get("user_email", "")
        accounts = msal_app.get_accounts(username=email) if email else msal_app.get_accounts()
        if not accounts:
            return False
        result = msal_app.acquire_token_silent(SCOPE, account=accounts[0])
        if result and "access_token" in result:
            st.session_state.auth_token = result
            st.session_state.token_expires_at = time.time() + result.get("expires_in", 3600)
            logging.info("Silent token refresh succeeded for %s", email)
            return True
    except Exception as exc:
        logging.warning("Silent token refresh failed: %s", exc)
    return False


def _get_catalog_stats() -> tuple[str, str]:
    """Return (n_tables, n_schemas) as strings for the sign-in hero stats row.

    Works in demo mode and with a live DuckDB/Databricks cache. Falls back to
    '—' on any error so the sign-in page always renders.
    """
    try:
        from src.config import is_demo_mode, CATALOG_CACHE, SCHEMA_CACHE  # noqa: PLC0415
        if is_demo_mode():
            from src.demo.data import _DEMO_TABLES  # noqa: PLC0415
            return str(len(_DEMO_TABLES)), str(_DEMO_TABLES["schema_name"].nunique())
        from src.db.queries import run_query  # noqa: PLC0415
        _t = run_query(
            f"SELECT COUNT(*) AS n FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata", {}
        )
        _s = run_query(
            f"SELECT COUNT(DISTINCT schema_name) AS n FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata", {}
        )
        n_t = str(int(_t.iloc[0]["n"])) if _t is not None and not _t.empty else "—"
        n_s = str(int(_s.iloc[0]["n"])) if _s is not None and not _s.empty else "—"
        return n_t, n_s
    except Exception:
        return "—", "—"


def render_signin_page(auth_url: Optional[str] = None, mock: bool = False):
    """Render the editorial two-column sign-in layout."""
    col_hero, col_card = st.columns([1.1, 0.9], gap="large")

    with col_hero:
        st.markdown(f"""
        <div class="dd-signin-hero">
          <div class="dd-eyebrow">§ {t('auth.hero_eyebrow')}</div>
          <h1>{t('auth.title')}</h1>
          <p class="lead">{t('auth.subtitle')}</p>
        </div>
        """, unsafe_allow_html=True)
        _n_tables, _n_schemas = _get_catalog_stats()
        st.markdown('<hr class="dd-rule"/>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="dd-stats-row">
          <div>
            <div class="dd-stat-n">{_n_tables}</div>
            <div class="dd-stat-l">{t('auth.stats_tables')}</div>
          </div>
          <div>
            <div class="dd-stat-n">{_n_schemas}</div>
            <div class="dd-stat-l">{t('auth.stats_schemas')}</div>
          </div>
          <div>
            <div class="dd-stat-n">{t('auth.stats_cadence_val')}</div>
            <div class="dd-stat-l">{t('auth.stats_cadence')}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    with col_card:
        st.markdown(f"""
        <div class="dd-signin-card">
          <div class="dd-eyebrow">{t('auth.card_eyebrow')}</div>
          <h3>{t('auth.card_title')}</h3>
          <p class="body">{t('auth.card_body')}</p>
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
                     "SELECT_ALL_USERS", "finance_dept_id", "all_employees_id",
                     "mock_admin_group"],
                    "admin@research-org.ca",
                ),
            }
            _default_dept = MOCK_DEPT
            _dept_opts = list(_MOCK_DEPTS.keys())
            _dept_sel = st.selectbox(
                t("auth.mock_department"),
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
                f'<p class="dd-meta">{t("auth.mock_prompt")}</p>',
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
            <p class="dd-meta" style="margin-top:12px">{t("auth.policy_agreement")}</p>
            """, unsafe_allow_html=True)


def check_auth(sync_prefs_callback: Optional[callable] = None):
    """Main authentication gate. Handles OIDC flow and session initialisation.

    Args:
        sync_prefs_callback (Optional[callable]): Optional callable to seed personalisation data on
                             first login (usually _sync_prefs_to_session).

    Returns:
        None

    Flow:
        1. If a valid, non-expired token is in session → return immediately.
        2. If the token is close to expiry → try silent refresh; clear + re-auth
           if that fails.
        3. If ?code= is in the URL → process the OIDC callback. Query params are
           cleared regardless of outcome so a stale code never causes a loop.
        4. Otherwise → generate state/nonce, build auth URL, render sign-in page.
    """
    # ── Step 1 & 2: existing session ─────────────────────────────────────────
    if st.session_state.get("auth_token") is not None:
        expires_at = st.session_state.get("token_expires_at", 0)
        if expires_at and time.time() < expires_at - TOKEN_REFRESH_BUFFER_S:
            # Token is still fresh — nothing to do.
            return
        # Token is expired or expiry unknown — try silent refresh first.
        if _try_silent_refresh():
            return
        # Silent refresh failed — force a clean re-auth.
        logging.info("Token expired and silent refresh failed; clearing session for re-auth.")
        _clear_auth_session()
        st.query_params.clear()
        st.rerun()

    # ── Step 3: OIDC callback (?code= present) ────────────────────────────────
    msal_app = get_msal_app()
    query_params = st.query_params

    if "code" in query_params:
        # Capture all values before clearing — st.query_params.clear() makes
        # them inaccessible and must happen before any st.stop() call.
        code           = query_params.get("code", "")
        state          = query_params.get("state")
        expected_state = st.session_state.get("oauth_state")
        expected_nonce = st.session_state.get("oauth_nonce")

        # Always clear the code from the URL first — prevents retry loops.
        st.query_params.clear()

        if not state or not expected_state or state != expected_state:
            logging.error("OAuth state mismatch (got %s, expected %s).", state, expected_state)
            for key in ("oauth_state", "oauth_nonce"):
                st.session_state.pop(key, None)
            st.error(t("auth.signin_failed_security"))
            st.stop()

        result = msal_app.acquire_token_by_authorization_code(
            code, scopes=SCOPE,
            redirect_uri=REDIRECT_URI, nonce=expected_nonce,
        )

        for key in ("oauth_state", "oauth_nonce"):
            st.session_state.pop(key, None)

        if "access_token" in result:
            claims = result.get("id_token_claims", {})
            if expected_nonce and claims.get("nonce") != expected_nonce:
                logging.error("OAuth nonce mismatch.")
                st.error(t("auth.signin_failed_security"))
                st.stop()

            from src.auth_graph import clear_groups_cache  # noqa: PLC0415
            new_oid = claims.get("oid", "")
            if new_oid:
                clear_groups_cache(new_oid)

            st.session_state.auth_token       = result
            st.session_state.token_expires_at = time.time() + result.get("expires_in", 3600)
            st.session_state.authenticated    = True
            st.session_state.user_groups      = _resolve_user_groups(claims, result["access_token"])
            st.session_state.user_name        = claims.get("name")
            st.session_state.user_email       = (claims.get("email")
                                                  or claims.get("preferred_username", ""))
            st.session_state.user_oid         = claims.get("oid", "")

            if sync_prefs_callback:
                sync_prefs_callback()
            st.session_state["_prefs_loaded"] = True

            st.rerun()
        else:
            err = result.get("error_description") or result.get("error") or "unknown error"
            logging.error("Failed to acquire token: %s", err)
            st.error(t("auth.signin_failed"))
            st.stop()

    # ── Step 4: no session, no code → show sign-in page ──────────────────────
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




@functools.lru_cache(maxsize=128)
def _parse_groups(env_val: str) -> frozenset[str]:
    """Parse comma-separated groups from an environment variable."""
    if not env_val:
        return frozenset()
    return frozenset(g.strip() for g in env_val.split(",") if g.strip())


def is_pipeline_user() -> bool:
    """True if the current user belongs to at least one PIPELINE_GROUPS group.

    Always False when the pipelines feature is disabled (``ENABLE_PIPELINES``).
    """
    from src.config import pipelines_enabled
    if not pipelines_enabled():
        return False
    pipeline_groups = _parse_groups(os.getenv("PIPELINE_GROUPS", ""))
    if not pipeline_groups:
        return False
    user_groups = st.session_state.get("user_groups") or []
    return not pipeline_groups.isdisjoint(user_groups)


def is_admin() -> bool:
    """True if the current user belongs to at least one ADMIN_GROUPS group.

    No demo-mode bypass — admins must be in the real Entra group even in
    demo/development mode, unlike is_power_user() which may have a mock shortcut.
    """
    admin_groups = _parse_groups(os.getenv("ADMIN_GROUPS", ""))
    if not admin_groups:
        return False
    return not admin_groups.isdisjoint(st.session_state.get("user_groups", []))
