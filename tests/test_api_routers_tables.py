from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.auth import AuthenticatedUser
from src.api.deps import get_current_user
from src.api.main import app


# ── Shared fixtures ───────────────────────────────────────────────────────────

FAKE_USER = AuthenticatedUser(
    oid="test-oid",
    email="test@example.com",
    name="Test User",
    groups=["group-a"],
)

FAKE_TABLES = [
    {
        "full_name": "cat.schema.orders",
        "catalog_name": "cat",
        "schema_name": "schema",
        "table_name": "orders",
        "table_description": "Order records",
        "table_type": "TABLE",
        "dq_score": "A",
        "dq_status": "passed",
        "updated_at": "2024-01-01T00:00:00Z",
    }
]

FAKE_COLS = pd.DataFrame([
    {"column_name": "id", "data_type": "BIGINT", "description": "Primary key"},
    {"column_name": "amount", "data_type": "DECIMAL", "description": "Order amount"}
])


@pytest.fixture()
def client():
    """TestClient with auth override injecting FAKE_USER."""
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client_no_auth():
    """TestClient with no dependency overrides — real auth required."""
    app.dependency_overrides.clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@contextmanager
def _no_cache():
    """Context manager that forces Redis cache misses so the DB layer is exercised."""
    with ExitStack() as stack:
        stack.enter_context(patch("src.api.routers.tables.redis_cache.get", AsyncMock(return_value=None)))
        stack.enter_context(patch("src.api.routers.tables.redis_cache.set", AsyncMock()))
        yield

# ── Table list ────────────────────────────────────────────────────────────────

def test_list_tables_requires_auth(client_no_auth):
    # Arrange & Act
    resp = client_no_auth.get("/api/v1/tables")
    # Assert
    assert resp.status_code == 401


def test_list_tables_returns_data(client):
    # Arrange
    expected_df = pd.DataFrame(FAKE_TABLES)
    with patch("src.api.routers.tables.queries.get_authorized_tables", return_value=expected_df), \
         _no_cache():
        # Act
        resp = client.get("/api/v1/tables")
    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["full_name"] == "cat.schema.orders"


def test_list_tables_returns_cache_hit(client):
    """When Redis returns a cached value, the DB layer is not called."""
    # Arrange
    with patch("src.api.routers.tables.redis_cache.get", AsyncMock(return_value=FAKE_TABLES)), \
         patch("src.api.routers.tables.queries.get_authorized_tables") as no_db:
        # Act
        resp = client.get("/api/v1/tables")
    # Assert
    assert resp.status_code == 200
    no_db.assert_not_called()


def test_list_tables_returns_empty_list_when_no_results(client):
    # Arrange
    with patch("src.api.routers.tables.queries.get_authorized_tables", return_value=pd.DataFrame()), \
         _no_cache():
        # Act
        resp = client.get("/api/v1/tables")
    # Assert
    assert resp.status_code == 200
    assert resp.json() == []


# ── Table detail ──────────────────────────────────────────────────────────────

def test_get_table_404_when_not_found(client):
    # Arrange
    with patch("src.api.routers.tables.queries.get_table_details", return_value=None), \
         _no_cache():
        # Act
        resp = client.get("/api/v1/tables/cat/schema/orders")
    # Assert
    assert resp.status_code == 404


def test_get_table_returns_columns(client):
    # Arrange
    with patch("src.api.routers.tables.queries.get_table_details", return_value=FAKE_COLS), \
         _no_cache():
        # Act
        resp = client.get("/api/v1/tables/cat/schema/orders")
    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert data["full_name"] == "cat.schema.orders"
    assert len(data["columns"]) == 2
    assert data["columns"][0]["column_name"] == "id"
    assert data["columns"][0]["data_type"] == "BIGINT"


def test_get_table_returns_cache_hit(client):
    """When Redis returns a cached value, the DB layer is not called."""
    # Arrange
    cached_data = {"full_name": "cat.schema.orders", "columns": [{"column_name": "id", "data_type": "BIGINT", "description": None}]}
    with patch("src.api.routers.tables.redis_cache.get", AsyncMock(return_value=cached_data)), \
         patch("src.api.routers.tables.queries.get_table_details") as no_db:
        # Act
        resp = client.get("/api/v1/tables/cat/schema/orders")
    # Assert
    assert resp.status_code == 200
    no_db.assert_not_called()
    assert resp.json() == cached_data
