"""Tests for the FastAPI REST endpoints (src/api/main.py).

All tests use FastAPI's dependency_overrides to inject a fake authenticated
user, bypassing JWT validation entirely.  The DB layer is patched at the
queries module so no real database connection is required.

Coverage:
  - GET /health                    → 200 + {"status": "ok"}
  - GET /api/v1/tables             → 401 without token, 200 with valid token
  - GET /api/v1/tables             → returns serialised table list
  - GET /api/v1/tables/{c}/{s}/{t} → 404 when table not found
  - GET /api/v1/tables/{c}/{s}/{t} → 200 with column list
  - GET /api/v1/search?q=          → 401 without token, 200 with results
  - GET /api/v1/lineage/{c}/{s}/{t}→ returns edge list
  - Cache: hit path returns cached value, skips queries call
"""

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
        "updated_at": "2026-01-01",
    }
]

FAKE_COLS = pd.DataFrame([
    {"column_name": "id", "data_type": "BIGINT", "description": "Primary key"},
    {"column_name": "amount", "data_type": "DECIMAL", "description": "Order total"},
])

FAKE_SEARCH_RESULTS = [
    {
        "full_name": "cat.schema.orders",
        "name": "orders",
        "match_type": "Table",
        "description": "Order records",
        "catalog_name": "cat",
        "schema_name": "schema",
        "table_name": "orders",
        "dq_score": "A",
    }
]

FAKE_LINEAGE = [
    {
        "table_full_name": "cat.schema.orders",
        "direction": "upstream",
        "entity_full_name": "cat.raw.raw_orders",
        "entity_type": "TABLE",
        "depth": 1,
    }
]


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
        stack.enter_context(patch("src.api.routers.search.redis_cache.get", AsyncMock(return_value=None)))
        stack.enter_context(patch("src.api.routers.search.redis_cache.set", AsyncMock()))
        stack.enter_context(patch("src.api.routers.lineage.redis_cache.get", AsyncMock(return_value=None)))
        stack.enter_context(patch("src.api.routers.lineage.redis_cache.set", AsyncMock()))
        yield


# ── Health ────────────────────────────────────────────────────────────────────

def test_health_returns_200(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_no_auth_required(client_no_auth):
    resp = client_no_auth.get("/health/live")
    assert resp.status_code == 200

def test_health_ready_returns_200(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

# ── Search ────────────────────────────────────────────────────────────────────

def test_search_requires_auth(client_no_auth):
    resp = client_no_auth.get("/api/v1/search?q=orders")
    assert resp.status_code == 401


def test_search_requires_q_param(client):
    resp = client.get("/api/v1/search")
    assert resp.status_code == 422  # FastAPI validation error


def test_search_returns_results(client):
    expected_df = pd.DataFrame(FAKE_SEARCH_RESULTS)
    with patch("src.api.routers.search.queries.search_metadata", return_value=expected_df), \
         _no_cache():
        resp = client.get("/api/v1/search?q=orders")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["match_type"] == "Table"


def test_search_returns_cache_hit(client):
    """When Redis returns a cached value, the DB layer is not called."""
    with patch("src.api.routers.search.redis_cache.get", AsyncMock(return_value=FAKE_SEARCH_RESULTS)), \
         patch("src.api.routers.search.queries.search_metadata") as no_db:
        resp = client.get("/api/v1/search?q=orders")
    assert resp.status_code == 200
    no_db.assert_not_called()
    assert resp.json() == FAKE_SEARCH_RESULTS


def test_search_passes_query_to_db(client):
    with patch("src.api.routers.search.queries.search_metadata", return_value=pd.DataFrame()) as mock_q, \
         _no_cache():
        client.get("/api/v1/search?q=revenue")
    mock_q.assert_called_once()
    args, _ = mock_q.call_args
    assert args[0] == "revenue"


# ── Lineage ───────────────────────────────────────────────────────────────────

def test_lineage_returns_edges(client):
    expected_df = pd.DataFrame(FAKE_LINEAGE)
    with patch("src.api.routers.lineage.queries.get_lineage", return_value=expected_df), \
         _no_cache():
        resp = client.get("/api/v1/lineage/cat/schema/orders")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["direction"] == "upstream"


def test_lineage_returns_cache_hit(client):
    """When Redis returns a cached value, the DB layer is not called."""
    with patch("src.api.routers.lineage.redis_cache.get", AsyncMock(return_value=FAKE_LINEAGE)), \
         patch("src.api.routers.lineage.queries.get_lineage") as no_db:
        resp = client.get("/api/v1/lineage/cat/schema/orders")
    assert resp.status_code == 200
    no_db.assert_not_called()
    assert resp.json() == FAKE_LINEAGE


def test_lineage_default_depth_is_1(client):
    with patch("src.api.routers.lineage.queries.get_lineage", return_value=pd.DataFrame()) as mock_q, \
         _no_cache():
        client.get("/api/v1/lineage/cat/schema/orders")
    _, kwargs = mock_q.call_args
    assert kwargs.get("depth", mock_q.call_args[0][1] if len(mock_q.call_args[0]) > 1 else 1) == 1


def test_lineage_rejects_depth_above_5(client):
    with patch("src.api.routers.lineage.queries.get_lineage", return_value=pd.DataFrame()), \
         _no_cache():
        resp = client.get("/api/v1/lineage/cat/schema/orders?depth=10")
    assert resp.status_code == 422


def test_lineage_accepts_depth_5(client):
    with patch("src.api.routers.lineage.queries.get_lineage", return_value=pd.DataFrame()), \
         _no_cache():
        resp = client.get("/api/v1/lineage/cat/schema/orders?depth=5")
    assert resp.status_code == 200


# ── Coverage gaps ─────────────────────────────────────────────────────────────

def test_mcp_auth_no_token(client):
    resp = client.post("/mcp")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Authentication required"}

def test_mcp_auth_value_error(client):
    with patch("src.api.main.validate_token", AsyncMock(side_effect=ValueError("Invalid token"))):
        resp = client.post("/mcp", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid token"}

def test_mcp_auth_runtime_error(client):
    with patch("src.api.main.validate_token", AsyncMock(side_effect=RuntimeError("Misconfig"))):
        resp = client.post("/mcp", headers={"Authorization": "Bearer some-token"})
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Authentication service misconfigured"}

def test_mcp_auth_success(client):
    with patch("src.api.main.validate_token", AsyncMock(return_value={"sub": "user123"})):
        resp = client.post("/mcp", headers={"Authorization": "Bearer good-token"}, json={})
    # Since MCP sub-app handler is mounted, it returns a 404 because
    # the streamable_http_app() has no route for basic POST /, only standard MCP.
    # We assert it's NOT a 401.
    assert resp.status_code != 401

@pytest.mark.anyio
async def test_mcp_auth_middleware_lifespan():
    from src.api.main import _MCPAuthMiddleware
    app_mock = AsyncMock()
    middleware = _MCPAuthMiddleware(app_mock)

    send_mock = AsyncMock()
    await middleware({"type": "lifespan"}, None, send_mock)
    app_mock.assert_called_once()

@pytest.mark.anyio
async def test_security_headers_middleware_lifespan():
    from src.api.main import _SecurityHeadersMiddleware
    app_mock = AsyncMock()
    middleware = _SecurityHeadersMiddleware(app_mock)
    send_mock = AsyncMock()
    await middleware({"type": "lifespan"}, None, send_mock)
    app_mock.assert_called_once()

@pytest.mark.anyio
async def test_lifespan():
    from src.api.main import lifespan, app
    with patch("src.api.main._validate_auth_config") as mock_validate:
        async with lifespan(app):
            pass
        mock_validate.assert_called_once()
