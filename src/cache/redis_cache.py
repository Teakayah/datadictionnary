from __future__ import annotations
"""Async Redis cache with graceful degradation.

All public functions silently swallow Redis errors so a missing or
unavailable Redis instance never breaks the API or MCP server.
"""

import hashlib
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_client: Optional[Any] = None


def _get_client() -> Optional[Any]:
    """Return an async Redis client, or None if REDIS_URL is unset / unavailable."""
    global _client
    if _client is not None:
        return _client
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis.asyncio as aioredis
        _client = aioredis.from_url(url, decode_responses=True)
        logger.info("Redis client initialised: %s", url.split("@")[-1])
    except Exception as exc:  # pragma: no cover
        logger.warning("Redis init failed (%s) — running without cache", exc)
        _client = None
    return _client


def cache_key(*parts: Any) -> str:
    """Stable, namespaced cache key derived from arbitrary args.

    WHY IT EXISTS:
    We generate cache keys by hashing the query parameters and the user groups.
    This ensures that cache hits are securely isolated by permission boundary.
    If a user searches for the same query as an admin, they will get a different
    cache hit containing only the subset of tables they are authorized to access,
    because the user groups array is part of the hash input.

    Args:
        *parts (Any): Arbitrary arguments to serialize and hash.

    Returns:
        str: A stable, namespaced cache key string.
    """
    raw = json.dumps(parts, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return f"ddic:{digest}"


async def get(key: str) -> Optional[Any]:
    """Return a cached value or None.

    Args:
        key (str): The cache key to retrieve.

    Returns:
        Optional[Any]: The deserialized cached value, or None if not found or on error.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        value = await client.get(key)
        return json.loads(value) if value is not None else None
    except Exception as exc:
        logger.debug("Redis GET error: %s", exc)
        return None


async def set(key: str, value: Any, ttl: int = 300) -> None:
    """Store a value with a TTL in seconds.

    Args:
        key (str): The cache key to store.
        value (Any): The value to cache.
        ttl (int, optional): Time-to-live in seconds. Defaults to 300.
    """
    client = _get_client()
    if client is None:
        return
    try:
        await client.setex(key, ttl, json.dumps(value, default=str))
    except Exception as exc:
        import redis
        if isinstance(exc, redis.RedisError):
            print(f"Redis set error for {key}: {exc}")
        else:
            logger.debug("Redis SET error: %s", exc)


async def delete(key: str) -> None:
    """Delete a key from the cache.

    Args:
        key (str): The cache key to delete.
    """
    client = _get_client()
    if client is None:
        return
    try:
        await client.delete(key)
    except Exception as exc:
        logger.debug("Redis DELETE error: %s", exc)

