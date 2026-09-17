from __future__ import annotations

from unittest.mock import AsyncMock, patch
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.auth import AuthenticatedUser
from src.api.deps import get_current_user

# Mock dependency for authentication
def override_get_current_user():
    return AuthenticatedUser(oid="test-oid", email="test@test.com", name="Test User", groups=["test_group"])

app.dependency_overrides[get_current_user] = override_get_current_user

client = TestClient(app)

def test_search_endpoint_success():
    # Arrange
    mock_data = pd.DataFrame([
        {
            "full_name": "cat.schema.test_table",
            "name": "test_table",
            "match_type": "Table",
            "description": "A test table",
            "catalog_name": "cat",
            "schema_name": "schema",
            "table_name": "test_table",
            "dq_score": "95.5"
        }
    ])

    with patch("src.api.routers.search.queries.search_metadata", return_value=mock_data), \
         patch("src.api.routers.search.redis_cache.get", AsyncMock(return_value=None)), \
         patch("src.api.routers.search.redis_cache.set", AsyncMock()):
        # Act
        response = client.get("/api/v1/search?q=test")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "test_table"
        assert data[0]["full_name"] == "cat.schema.test_table"

def test_search_endpoint_cache_hit():
    # Arrange
    cached_data = [{
        "full_name": "cached.schema.table",
        "name": "cached_table",
        "match_type": "Table",
        "description": "cached",
        "catalog_name": "cached",
        "schema_name": "schema",
        "table_name": "table",
        "dq_score": None
    }]

    with patch("src.api.routers.search.redis_cache.get", AsyncMock(return_value=cached_data)):
        # Act
        response = client.get("/api/v1/search?q=cached")

        # Assert
        assert response.status_code == 200
        assert response.json() == cached_data

def test_search_endpoint_missing_query():
    # Act
    response = client.get("/api/v1/search")

    # Assert
    assert response.status_code == 422

def test_search_endpoint_empty_results():
    # Arrange
    empty_data = pd.DataFrame()

    with patch("src.api.routers.search.queries.search_metadata", return_value=empty_data), \
         patch("src.api.routers.search.redis_cache.get", AsyncMock(return_value=None)), \
         patch("src.api.routers.search.redis_cache.set", AsyncMock()):
        # Act
        response = client.get("/api/v1/search?q=nothing")

        # Assert
        assert response.status_code == 200
        assert response.json() == []

def test_search_endpoint_none_results():
    # Arrange
    with patch("src.api.routers.search.queries.search_metadata", return_value=None), \
         patch("src.api.routers.search.redis_cache.get", AsyncMock(return_value=None)), \
         patch("src.api.routers.search.redis_cache.set", AsyncMock()):
        # Act
        response = client.get("/api/v1/search?q=nothing")

        # Assert
        assert response.status_code == 200
        assert response.json() == []

def test_search_query_too_short():
    # Act
    response = client.get("/api/v1/search?q=")

    # Assert
    assert response.status_code == 422
    assert "String should have at least 1 character" in response.text
