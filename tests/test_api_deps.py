import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from src.api.deps import get_current_user
from src.api.auth import AuthenticatedUser

@pytest.mark.anyio
async def test_get_current_user_success():
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid_token")
    mock_user = AuthenticatedUser(oid="123", email="test@test.com", name="Test", groups=[])

    with patch("src.api.deps.validate_token", AsyncMock(return_value=mock_user)):
        user = await get_current_user(creds)
        assert user == mock_user

@pytest.mark.anyio
async def test_get_current_user_runtime_error():
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    with patch("src.api.deps.validate_token", AsyncMock(side_effect=RuntimeError("Misconfigured"))):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(creds)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Authentication service misconfigured"

@pytest.mark.anyio
async def test_get_current_user_value_error():
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid_token")

    with patch("src.api.deps.validate_token", AsyncMock(side_effect=ValueError("Invalid token"))):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(creds)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Invalid token"
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}
