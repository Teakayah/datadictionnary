from __future__ import annotations
import asyncio

from fastapi import APIRouter, Depends, Query

from src.api import queries
from src.api.auth import AuthenticatedUser
from src.api.deps import get_current_user
from src.api.models import LineageEdge
from src.cache import redis_cache

router = APIRouter(prefix="/lineage", tags=["lineage"])


@router.get("/{catalog}/{schema}/{table}", response_model=list[LineageEdge])
async def get_lineage(
    catalog: str,
    schema: str,
    table: str,
    depth: int = Query(default=1, ge=1, le=5, description="Lineage hops (1–5)"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Return upstream and downstream lineage edges for a table."""
    full_name = f"{catalog}.{schema}.{table}"
    groups = tuple(user.groups)
    ck = redis_cache.cache_key("api_lineage", full_name, depth, groups)
    if (cached := await redis_cache.get(ck)) is not None:
        return cached

    df = await asyncio.to_thread(queries.get_lineage, full_name, depth, groups)
    result = df.to_dict(orient="records") if df is not None and not df.empty else []
    await redis_cache.set(ck, result, ttl=300)
    return result
