from __future__ import annotations
import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from src.api import queries
from src.api.auth import AuthenticatedUser
from src.api.deps import get_current_user
from src.api.models import ColumnInfo, TableDetail, TableSummary
from src.cache import redis_cache

router = APIRouter(prefix="/tables", tags=["tables"])


@router.get("", response_model=list[TableSummary])
async def list_tables(user: AuthenticatedUser = Depends(get_current_user)):
    """List all tables the caller is authorized to access."""
    groups = tuple(user.groups)
    ck = redis_cache.cache_key("api_tables", groups)
    if (cached := await redis_cache.get(ck)) is not None:
        return cached

    df = await asyncio.to_thread(queries.get_authorized_tables, groups)
    result = df.to_dict(orient="records") if df is not None and not df.empty else []
    await redis_cache.set(ck, result, ttl=600)
    return result


@router.get("/{catalog}/{schema}/{table}", response_model=TableDetail)
async def get_table(
    catalog: str,
    schema: str,
    table: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Return column metadata for a specific table (404 if not found or access denied)."""
    full_name = f"{catalog}.{schema}.{table}"
    groups = tuple(user.groups)
    ck = redis_cache.cache_key("api_table_detail", full_name, groups)
    if (cached := await redis_cache.get(ck)) is not None:
        return cached

    cols_df = await asyncio.to_thread(queries.get_table_details, full_name, groups)
    if cols_df is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{full_name}' not found or access denied.",
        )

    columns = [
        ColumnInfo(
            column_name=row["column_name"],
            data_type=row["data_type"],
            description=row.get("description"),
        )
        for row in cols_df.to_dict(orient="records")
    ]
    result = TableDetail(full_name=full_name, columns=columns).model_dump()
    await redis_cache.set(ck, result, ttl=600)
    return result
