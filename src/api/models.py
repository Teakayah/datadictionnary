from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class TableSummary(BaseModel):
    full_name: str
    catalog_name: str
    schema_name: str
    table_name: str
    table_description: Optional[str] = None
    table_type: Optional[str] = None
    dq_score: Optional[str] = None
    dq_status: Optional[str] = None
    updated_at: Optional[str] = None


class ColumnInfo(BaseModel):
    column_name: str
    data_type: str
    description: Optional[str] = None


class TableDetail(BaseModel):
    full_name: str
    columns: list[ColumnInfo]


class SearchResult(BaseModel):
    full_name: str
    name: str
    match_type: str  # "Table" | "Column" | "Glossary"
    description: Optional[str] = None
    catalog_name: Optional[str] = None
    schema_name: Optional[str] = None
    table_name: Optional[str] = None
    dq_score: Optional[str] = None


class LineageEdge(BaseModel):
    table_full_name: str
    direction: str  # "upstream" | "downstream"
    entity_full_name: str
    entity_type: str
    depth: int
