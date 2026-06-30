import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from src.api.main import app

@pytest.fixture
def client():
    # Provide the test client with a valid lifespan hook context
    with patch("src.api.main._validate_auth_config"):
        with TestClient(app) as client:
            yield client

def test_security_headers_middleware(client):
    response = client.get("/health/live")
    assert response.status_code == 200

    # Check headers
    headers = response.headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert headers["x-xss-protection"] == "0"
    assert headers["cache-control"] == "no-store"

@pytest.mark.anyio
async def test_security_headers_middleware_not_http_direct():
    from src.api.main import _SecurityHeadersMiddleware

    mock_app = AsyncMock()
    middleware = _SecurityHeadersMiddleware(mock_app)

    scope = {"type": "websocket"}
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(scope, receive, send)
    mock_app.assert_called_once_with(scope, receive, send)

def test_production_environment_header():
    import os

    original_env = os.environ.get("ENVIRONMENT")

    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        import importlib
        import src.api.main

        # Test reloading the module strictly, but we must restore it to avoid breaking others
        # Use a try/finally block to ensure the state is always restored
        try:
            importlib.reload(src.api.main)
            assert any(h[0] == b"strict-transport-security" for h in src.api.main._SECURITY_HEADERS)
        finally:
            # Crucially, restore the module state to the non-production env for subsequent tests!
            restore_env = {"ENVIRONMENT": original_env} if original_env is not None else {}
            # If the variable wasn't set, patch.dict isn't great at un-setting, but it's okay,
            # setting it to "test" is fine as a fallback
            if original_env is None:
                restore_env = {"ENVIRONMENT": "test"}

            with patch.dict(os.environ, restore_env):
                importlib.reload(src.api.main)
