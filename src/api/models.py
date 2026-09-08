"""Pydantic models defining the JSON payloads for the REST API.

These models ensure consistent serialization and OpenAPI schema generation
across the FastAPI endpoints for search, lineage, and table discovery.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class TableSummary(BaseModel):
    """Summary of a table returned by the list endpoint.

    Contains basic metadata and health scores, omitting column details.
    """
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
    """Column metadata including data type and business description."""
    column_name: str
    data_type: str
    description: Optional[str] = None


class TableDetail(BaseModel):
    """Detailed table metadata including a comprehensive list of its columns."""
    full_name: str
    columns: list[ColumnInfo]


class SearchResult(BaseModel):
    """A single match returned from the hybrid keyword/semantic search endpoint."""
    full_name: str
    name: str
    match_type: str  # "Table" | "Column" | "Glossary"
    description: Optional[str] = None
    catalog_name: Optional[str] = None
    schema_name: Optional[str] = None
    table_name: Optional[str] = None
    dq_score: Optional[str] = None


class LineageEdge(BaseModel):
    """A directional edge representing data lineage between two entities."""
    table_full_name: str
    direction: str  # "upstream" | "downstream"
    entity_full_name: str
    entity_type: str
    depth: int
