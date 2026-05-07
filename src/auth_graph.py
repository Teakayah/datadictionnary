"""Microsoft Graph helpers for Entra ID groups overage.

When a user is a member of more than ~150 security groups, Entra ID omits
the inline ``groups`` claim from the ID token and instead returns a
``_claim_names.groups`` pointer to the Graph API. Without explicit handling
the app treats the user as having zero groups — they see zero tables.

This module implements the overage path: detect the claim shape, then call
``POST /v1.0/me/getMemberObjects`` to fetch the transitive
security-group memberships using the access token MSAL already produced.

Used from src.auth.check_auth after token acquisition.

Required scope: ``GroupMember.Read.All`` — already in src.config.SCOPE.

Caching: per-user-OID, process-level, 1h TTL. Streamlit's @cache_data is
session-scoped (per-tab) which would defeat the cache; a process-level
dict survives across sessions.

Failure mode: any error (network, 4xx, 5xx) returns ``[]`` and logs a
warning. We deliberately fail closed — returning the empty list makes the
user see no tables, which is the right default. We do NOT silently grant
access by returning a wider set.
"""

from __future__ import annotations

import logging
import threading
import time

import requests

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GROUPS_TTL_S = 3600
_GRAPH_TIMEOUT_S = 15

# Process-level cache keyed by user OID. Lock-protected because Streamlit
# script-runner threads can call into here concurrently.
_GROUPS_CACHE: dict[str, tuple[float, list[str]]] = {}
_CACHE_LOCK = threading.Lock()


def has_groups_overage(claims: dict) -> bool:
    """Return True iff the ID token claims indicate a groups overage.

    Entra signals overage by omitting the inline ``groups`` claim AND
    populating ``_claim_names.groups`` with a Graph-source pointer. Both
    conditions matter — a token with both inline groups and a claim_names
    entry should still use the inline list.
    """
    return (
        "groups" not in claims
        and "groups" in (claims.get("_claim_names") or {})
    )


def fetch_member_groups(access_token: str, user_oid: str) -> list[str]:
    """Return transitive security-group object IDs for the current user.

    Caches per OID for ``GROUPS_TTL_S``. On any error returns ``[]`` and
    logs a warning — never silently grants access.

    @param access_token: bearer token with GroupMember.Read.All scope
    @param user_oid:    Entra ID user OID, used as the cache key
    """
    if not user_oid:
        log.warning("fetch_member_groups called without user_oid; skipping cache.")
    now = time.time()
    if user_oid:
        with _CACHE_LOCK:
            cached = _GROUPS_CACHE.get(user_oid)
            if cached and (now - cached[0]) < GROUPS_TTL_S:
                log.debug("Graph groups cache hit for %s (%d groups)", user_oid, len(cached[1]))
                return list(cached[1])

    try:
        groups = _call_get_member_objects(access_token)
    except Exception as exc:
        log.warning(
            "Failed to fetch groups from Graph for %s: %s — failing closed (empty list).",
            user_oid or "<no oid>", exc,
        )
        return []

    if user_oid:
        with _CACHE_LOCK:
            _GROUPS_CACHE[user_oid] = (now, list(groups))
    log.info("Fetched %d transitive groups for %s.", len(groups), user_oid or "<no oid>")
    return groups


def _call_get_member_objects(access_token: str) -> list[str]:
    """Call POST /me/getMemberObjects, following @odata.nextLink pages.

    First page is POST with the {"securityEnabledOnly": true} body.
    Subsequent pages are GETs against the absolute URL Graph returns.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    body = {"securityEnabledOnly": True}

    # First page: POST.
    resp = requests.post(
        f"{GRAPH_BASE}/me/getMemberObjects",
        headers=headers, json=body, timeout=_GRAPH_TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json()
    out: list[str] = list(data.get("value", []))
    next_url = data.get("@odata.nextLink") or ""

    # Subsequent pages: GET against the URL Graph returned. Cap iterations
    # so a buggy server can't loop us forever.
    for _ in range(50):
        if not next_url:
            break
        resp = requests.get(next_url, headers=headers, timeout=_GRAPH_TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
        out.extend(data.get("value", []))
        next_url = data.get("@odata.nextLink") or ""
    else:
        log.warning("getMemberObjects pagination exceeded 50 pages — truncating.")

    return out


def _clear_cache() -> None:
    """Test helper — drop all cached entries."""
    with _CACHE_LOCK:
        _GROUPS_CACHE.clear()
