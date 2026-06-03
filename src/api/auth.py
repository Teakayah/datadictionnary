from __future__ import annotations
"""Entra ID JWT validation for the FastAPI / MCP layer.

Validates RS256-signed tokens from Microsoft Entra ID, extracts identity
claims, and resolves groups (including overage via Microsoft Graph).
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from jose import JWTError, jwt

from src.cache.redis_cache import cache_key, get as rcache_get, set as rcache_set
from src.config import CLIENT_ID, TENANT_ID

logger = logging.getLogger(__name__)

_JWKS_TTL = 3600
_jwks_cache: dict = {}
_jwks_fetched_at: float = 0.0

JWKS_URL = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
ISSUER = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"

# Groups mirroring generate_test_data.py / locustfile.py — used by mock auth only.
_MOCK_DEPT_GROUPS: dict[str, list[str]] = {
    "finance":  ["finance_group", "all_employees"],
    "research": ["research_group", "all_employees"],
    "hr":       ["hr_group", "all_employees"],
    "it":       ["it_group", "all_employees"],
    "admin":    ["finance_group", "research_group", "hr_group", "it_group", "all_employees"],
}


def _is_mock_auth() -> bool:
    return (
        os.getenv("ENABLE_MOCK_AUTH", "").lower() == "true"
        and os.getenv("ENVIRONMENT", "production") == "development"
    )


def _validate_auth_config() -> None:
    """Raise RuntimeError at startup if required auth env vars are not set.

    Called from the FastAPI lifespan so misconfiguration is caught before
    the first request, not silently during token validation.

    The critical failure mode we guard against: when CLIENT_ID and API_AUDIENCE
    are both unset, python-jose receives audience=None and skips the audience
    check entirely — any valid Entra ID token from any app would be accepted.
    """
    if _is_mock_auth():
        logger.warning("Mock auth enabled — Entra ID validation is DISABLED. Development only.")
        return
    if not TENANT_ID:
        raise RuntimeError(
            "TENANT_ID env var must be set — required for Entra ID JWT issuer "
            "and JWKS endpoint construction"
        )
    audience = os.getenv("API_AUDIENCE") or CLIENT_ID
    if not audience:
        raise RuntimeError(
            "CLIENT_ID or API_AUDIENCE env var must be set. "
            "Without a configured audience, jwt.decode() skips the aud claim "
            "check and any Entra ID token would be accepted."
        )


@dataclass
class AuthenticatedUser:
    oid: str
    email: str
    name: str
    groups: list[str] = field(default_factory=list)


async def _get_jwks() -> dict:
    global _jwks_cache, _jwks_fetched_at
    now = time.monotonic()
    if _jwks_cache and now - _jwks_fetched_at < _JWKS_TTL:
        return _jwks_cache
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(JWKS_URL)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = now
        logger.debug("JWKS refreshed from Entra ID")
    return _jwks_cache


async def validate_token(token: str) -> AuthenticatedUser:
    """Validate an Entra ID Bearer token and return the authenticated user.

    Audience defaults to CLIENT_ID; override with API_AUDIENCE env var when
    the API has its own app registration.

    In development with ENABLE_MOCK_AUTH=true, accepts sentinel tokens of the
    form "mock-<dept>" (e.g. "mock-finance") and returns a synthetic user with
    the corresponding group memberships. Never active in production.

    Raises:
        RuntimeError: server is misconfigured (TENANT_ID or audience missing).
                      Callers must convert this to HTTP 500, not 401.
        ValueError:   token is invalid (expired, wrong audience, bad signature).
                      Callers should return HTTP 401.
    """
    if _is_mock_auth() and token.startswith("mock-"):
        dept = token[5:]
        groups = _MOCK_DEPT_GROUPS.get(dept, ["all_employees"])
        return AuthenticatedUser(
            oid=f"mock-oid-{dept}",
            email=f"{dept}@mock.test",
            name=dept.title(),
            groups=groups,
        )

    # Re-read at call time so tests can monkeypatch the env.
    audience = os.getenv("API_AUDIENCE") or CLIENT_ID
    if not audience:
        raise RuntimeError(
            "Server misconfiguration: CLIENT_ID or API_AUDIENCE must be set"
        )
    if not TENANT_ID:
        raise RuntimeError("Server misconfiguration: TENANT_ID must be set")

    jwks = await _get_jwks()

    try:
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=audience,
            issuer=ISSUER,
        )
    except JWTError as exc:
        logger.warning("JWT validation failed (possible attack or expiry): %s", exc)
        raise ValueError(f"Invalid token: {exc}") from exc

    oid = claims.get("oid", "")
    email = (
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("upn", "")
    )
    name = claims.get("name", "")

    # Groups inline in token (< ~150 groups)
    groups: list[str] = claims.get("groups", [])

    # Overage: Entra omits the groups claim and signals via _claim_names
    if not groups and "groups" in claims.get("_claim_names", {}):
        groups = await _fetch_groups_graph(token, oid)

    return AuthenticatedUser(oid=oid, email=email, name=name, groups=groups)


async def _fetch_groups_graph(access_token: str, user_oid: str) -> list[str]:
    """Resolve group memberships via Microsoft Graph (groups overage path)."""
    ck = cache_key("api_groups", user_oid)
    cached = await rcache_get(ck)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://graph.microsoft.com/v1.0/me/getMemberObjects",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"securityEnabledOnly": True},
            )
            resp.raise_for_status()
            groups: list[str] = resp.json().get("value", [])
    except Exception as exc:
        logger.warning("Graph API group fetch failed for OID %s: %s", user_oid, exc)
        groups = []

    await rcache_set(ck, groups, ttl=3600)
    return groups
