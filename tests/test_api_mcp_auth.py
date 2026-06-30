import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from src.api.main import app, _MCPAuthMiddleware

@pytest.fixture
def client():
    with patch("src.api.main._validate_auth_config"):
        with TestClient(app) as client:
            yield client

def test_mcp_auth_middleware_no_auth(client):
    response = client.post("/mcp")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"

def test_mcp_auth_middleware_invalid_token(client):
    with patch("src.api.main.validate_token", AsyncMock(side_effect=ValueError("Invalid token signature"))):
        response = client.post("/mcp", headers={"Authorization": "Bearer invalid_token"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid token signature"

def test_mcp_auth_middleware_server_error(client):
    with patch("src.api.main.validate_token", AsyncMock(side_effect=RuntimeError("Misconfigured"))):
        response = client.post("/mcp", headers={"Authorization": "Bearer some_token"})
        assert response.status_code == 500
        assert response.json()["detail"] == "Authentication service misconfigured"

@pytest.mark.anyio
async def test_mcp_auth_middleware_not_http_or_ws():
    mock_app = AsyncMock()
    middleware = _MCPAuthMiddleware(mock_app)

    scope = {"type": "lifespan"}
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(scope, receive, send)
    mock_app.assert_called_once_with(scope, receive, send)

@pytest.mark.anyio
async def test_mcp_auth_middleware_success_direct():
    mock_app = AsyncMock()
    middleware = _MCPAuthMiddleware(mock_app)

    scope = {
        "type": "http",
        "headers": [(b"authorization", b"Bearer valid_token")]
    }
    receive = AsyncMock()
    send = AsyncMock()

    with patch("src.api.main.validate_token", AsyncMock(return_value={"sub": "user_id"})) as mock_validate:
        await middleware(scope, receive, send)
        mock_validate.assert_called_once_with("valid_token")
        mock_app.assert_called_once_with(scope, receive, send)
