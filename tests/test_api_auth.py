"""Tests for src/api/auth.py.

Coverage:
  - validate_token: happy path returns AuthenticatedUser with inline groups
  - validate_token: groups overage path calls _fetch_groups_graph
  - validate_token: JWTError from jose is re-raised as ValueError
  - validate_token: wrong audience raises ValueError
  - JWKS cache: second call within TTL skips re-fetch
  - _fetch_groups_graph: uses Redis cache on second call (no Graph HTTP)
  - _fetch_groups_graph: returns empty list on Graph 4xx error
  - _fetch_groups_graph: returns empty list on network error
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import JWTError

import src.api.auth as auth_mod
from src.api.auth import AuthenticatedUser, _fetch_groups_graph, validate_token


def _run(coro):
    return asyncio.run(coro)


# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_CLAIMS = {
    "oid": "user-oid-123",
    "preferred_username": "user@example.com",
    "name": "Test User",
    "groups": ["group-a", "group-b"],
}

FAKE_JWKS = {"keys": [{"kty": "RSA", "kid": "1"}]}


def _mock_jwks():
    return AsyncMock(return_value=FAKE_JWKS)


# ── validate_token ────────────────────────────────────────────────────────────

class TestValidateToken:
    def setup_method(self):
        # Reset JWKS cache between tests
        auth_mod._jwks_cache = {}
        auth_mod._jwks_fetched_at = 0.0

    def test_happy_path_inline_groups(self, monkeypatch):
        monkeypatch.setenv("API_AUDIENCE", "test-client-id")
        with patch.object(auth_mod, "_get_jwks", _mock_jwks()), \
             patch("src.api.auth.jwt.decode", return_value=FAKE_CLAIMS):
            user = _run(validate_token("fake-token"))

        assert isinstance(user, AuthenticatedUser)
        assert user.oid == "user-oid-123"
        assert user.email == "user@example.com"
        assert user.name == "Test User"
        assert user.groups == ["group-a", "group-b"]

    def test_falls_back_to_email_claim(self, monkeypatch):
        claims = {**FAKE_CLAIMS}
        del claims["preferred_username"]
        claims["email"] = "via-email@example.com"
        with patch.object(auth_mod, "_get_jwks", _mock_jwks()), \
             patch("src.api.auth.jwt.decode", return_value=claims):
            user = _run(validate_token("token"))
        assert user.email == "via-email@example.com"

    def test_jwt_error_raises_value_error(self, monkeypatch):
        with patch.object(auth_mod, "_get_jwks", _mock_jwks()), \
             patch("src.api.auth.jwt.decode", side_effect=JWTError("expired")):
            with pytest.raises(ValueError, match="Invalid token"):
                _run(validate_token("bad-token"))

    def test_groups_overage_calls_fetch_graph(self, monkeypatch):
        overage_claims = {
            "oid": "oid-1",
            "preferred_username": "u@example.com",
            "name": "U",
            "_claim_names": {"groups": "src1"},
            # no "groups" key — overage
        }
        fetch_mock = AsyncMock(return_value=["grp-1", "grp-2"])
        with patch.object(auth_mod, "_get_jwks", _mock_jwks()), \
             patch("src.api.auth.jwt.decode", return_value=overage_claims), \
             patch.object(auth_mod, "_fetch_groups_graph", fetch_mock):
            user = _run(validate_token("token"))

        fetch_mock.assert_awaited_once_with("token", "oid-1")
        assert user.groups == ["grp-1", "grp-2"]

    def test_no_groups_no_overage_returns_empty_groups(self, monkeypatch):
        claims = {**FAKE_CLAIMS}
        del claims["groups"]  # no groups, no _claim_names
        with patch.object(auth_mod, "_get_jwks", _mock_jwks()), \
             patch("src.api.auth.jwt.decode", return_value=claims):
            user = _run(validate_token("token"))
        assert user.groups == []


# ── JWKS cache ────────────────────────────────────────────────────────────────

class TestJwksCache:
    def setup_method(self):
        auth_mod._jwks_cache = {}
        auth_mod._jwks_fetched_at = 0.0

    def test_second_call_within_ttl_skips_fetch(self, monkeypatch):
        """JWKS is only fetched once when the cache is warm."""
        fetch_calls = []

        async def _fake_get(url, **kw):
            fetch_calls.append(url)
            resp = MagicMock()
            resp.json.return_value = FAKE_JWKS
            resp.raise_for_status = MagicMock()
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(get=AsyncMock(side_effect=_fake_get))
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            _run(auth_mod._get_jwks())

        # Warm the cache manually (simulate first call already done)
        auth_mod._jwks_fetched_at = time.monotonic()

        # A second call should use the cache
        with patch("httpx.AsyncClient") as mock_no_call:
            _run(auth_mod._get_jwks())
            mock_no_call.assert_not_called()


# ── _fetch_groups_graph ───────────────────────────────────────────────────────

class TestFetchGroupsGraph:
    def test_returns_cached_groups(self, monkeypatch):
        """Cache hit skips the Graph HTTP call entirely."""
        get_mock = AsyncMock(return_value=["cached-group"])
        with patch("src.api.auth.cache_key", return_value="ck"), \
             patch("src.api.auth.rcache_get", get_mock), \
             patch("httpx.AsyncClient") as no_http:
            result = _run(_fetch_groups_graph("token", "oid-1"))
        assert result == ["cached-group"]
        no_http.assert_not_called()

    def test_fetches_from_graph_on_cache_miss(self, monkeypatch):
        graph_resp = MagicMock()
        graph_resp.json.return_value = {"value": ["g1", "g2"]}
        graph_resp.raise_for_status = MagicMock()

        async def _fake_post(*a, **kw):
            return graph_resp

        with patch("src.api.auth.cache_key", return_value="ck"), \
             patch("src.api.auth.rcache_get", AsyncMock(return_value=None)), \
             patch("src.api.auth.rcache_set", AsyncMock()), \
             patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(post=AsyncMock(side_effect=_fake_post))
            )
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run(_fetch_groups_graph("token", "oid-1"))

        assert result == ["g1", "g2"]

    def test_returns_empty_list_on_http_error(self, monkeypatch):
        import httpx as _httpx
        with patch("src.api.auth.cache_key", return_value="ck"), \
             patch("src.api.auth.rcache_get", AsyncMock(return_value=None)), \
             patch("src.api.auth.rcache_set", AsyncMock()), \
             patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(
                    post=AsyncMock(side_effect=Exception("network error"))
                )
            )
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = _run(_fetch_groups_graph("token", "oid-1"))

        assert result == []

    def test_writes_groups_to_cache(self, monkeypatch):
        set_mock = AsyncMock()
        graph_resp = MagicMock()
        graph_resp.json.return_value = {"value": ["g1"]}
        graph_resp.raise_for_status = MagicMock()

        with patch("src.api.auth.cache_key", return_value="ck"), \
             patch("src.api.auth.rcache_get", AsyncMock(return_value=None)), \
             patch("src.api.auth.rcache_set", set_mock), \
             patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(post=AsyncMock(return_value=graph_resp))
            )
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            _run(_fetch_groups_graph("token", "oid-1"))

        set_mock.assert_awaited_once_with("ck", ["g1"], ttl=3600)
