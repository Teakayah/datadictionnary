"""Tests for src/cache/redis_cache.py.

Coverage:
  - cache_key: stable namespaced key, different args → different key
  - get: returns None when REDIS_URL unset / Redis unavailable
  - get: returns deserialized value on cache hit
  - get: returns None and swallows on Redis GET error
  - set: no-ops silently when Redis unavailable
  - set: serializes and calls setex with correct TTL
  - set: swallows Redis SET error
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch


import src.cache.redis_cache as rc


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def _fresh_module():
    """Force-reset the module-level _client back to None between tests."""
    rc._client = None


class TestGetClient:
    def setup_method(self):
        _fresh_module()

    def test_returns_existing_client_if_already_initialized(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        mock_client = AsyncMock()
        with patch("redis.asyncio.from_url", return_value=mock_client):
            client1 = rc._get_client()
            client2 = rc._get_client()
        assert client1 is client2

# ── cache_key ─────────────────────────────────────────────────────────────────

class TestCacheKey:
    def test_stable(self):
        assert rc.cache_key("a", 1, ["b"]) == rc.cache_key("a", 1, ["b"])

    def test_different_args_differ(self):
        assert rc.cache_key("search", ("g1",)) != rc.cache_key("search", ("g2",))

    def test_namespaced(self):
        assert rc.cache_key("x").startswith("ddic:")

    def test_different_types_differ(self):
        assert rc.cache_key(1) != rc.cache_key("1")


# ── get ───────────────────────────────────────────────────────────────────────

class TestGet:
    def setup_method(self):
        _fresh_module()

    def test_returns_none_when_redis_url_unset(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        result = _run(rc.get("any-key"))
        assert result is None

    def test_returns_deserialized_value_on_hit(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=json.dumps({"x": 1}))
        with patch("redis.asyncio.from_url", return_value=mock_client):
            result = _run(rc.get("key"))
        assert result == {"x": 1}

    def test_returns_none_on_cache_miss(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        with patch("redis.asyncio.from_url", return_value=mock_client):
            result = _run(rc.get("key"))
        assert result is None

    def test_swallows_redis_error(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
        with patch("redis.asyncio.from_url", return_value=mock_client):
            result = _run(rc.get("key"))
        assert result is None


# ── set ───────────────────────────────────────────────────────────────────────

class TestSet:
    def setup_method(self):
        _fresh_module()

    def test_noop_when_redis_url_unset(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        _run(rc.set("key", {"a": 1}))  # should not raise

    def test_calls_setex_with_ttl(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        mock_client = AsyncMock()
        mock_client.setex = AsyncMock()
        with patch("redis.asyncio.from_url", return_value=mock_client):
            _run(rc.set("key", [1, 2, 3], ttl=120))
        mock_client.setex.assert_awaited_once()
        args = mock_client.setex.call_args
        assert args[0][0] == "key"
        assert args[0][1] == 120
        assert json.loads(args[0][2]) == [1, 2, 3]

    def test_swallows_redis_error(self, monkeypatch):
        # Arrange
        import redis
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        mock_client = AsyncMock()
        error = redis.RedisError("timeout")
        mock_client.setex = AsyncMock(side_effect=error)

        # Act
        with patch("redis.asyncio.from_url", return_value=mock_client):
            with patch("builtins.print") as mock_print:
                _run(rc.set("key", {"x": 1}))

        # Assert
        mock_print.assert_called_once_with("Redis set error for key: timeout")


# ── delete ────────────────────────────────────────────────────────────────────

class TestDelete:
    def setup_method(self):
        _fresh_module()

    def test_noop_when_redis_url_unset(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        _run(rc.delete("key"))  # should not raise

    def test_calls_delete_with_key(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        mock_client = AsyncMock()
        mock_client.delete = AsyncMock()
        with patch("redis.asyncio.from_url", return_value=mock_client):
            _run(rc.delete("key"))
        mock_client.delete.assert_awaited_once_with("key")

    def test_swallows_redis_error(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        mock_client = AsyncMock()
        mock_client.delete = AsyncMock(side_effect=Exception("connection refused"))
        with patch("redis.asyncio.from_url", return_value=mock_client):
            _run(rc.delete("key"))  # should not raise
