import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routers.health import router

def test_health_live():
    # Arrange
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # Act
    response = client.get("/health/live")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@pytest.mark.anyio
async def test_liveness_direct():
    # Arrange
    from src.api.routers.health import liveness

    # Act
    result = await liveness()

    # Assert
    assert result == {"status": "ok"}
