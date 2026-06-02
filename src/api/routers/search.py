from __future__ import annotations
import asyncio

from fastapi import APIRouter, Depends, Query

from src.api import queries
from src.api.auth import AuthenticatedUser
from src.api.deps import get_current_user
from src.api.models import SearchResult
from src.cache import redis_cache

router = APIRouter(tags=["search"])


@router.get("/search", response_model=list[SearchResult])
async def search(
    q: str = Query(..., min_length=1, max_length=200, description="Free-text search query"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Hybrid keyword search across tables, columns, and glossary terms."""
    groups = tuple(user.groups)
    ck = redis_cache.cache_key("api_search", q, groups)
    if (cached := await redis_cache.get(ck)) is not None:
        return cached

    df = await asyncio.to_thread(queries.search_metadata, q, groups)
    result = df.to_dict(orient="records") if df is not None and not df.empty else []
    await redis_cache.set(ck, result, ttl=300)
    return result
