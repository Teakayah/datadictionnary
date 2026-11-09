from __future__ import annotations
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.auth import AuthenticatedUser, validate_token

_bearer = HTTPBearer()


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> AuthenticatedUser:
    """FastAPI dependency to authenticate the current user via Bearer token.

    WHY IT EXISTS:
    This dependency intentionally translates internal validation exceptions
    (`ValueError` and `RuntimeError` from `validate_token`) into standard FastAPI
    `HTTPException`s (401 and 500). This prevents stack trace leakage to the client
    on auth failures and ensures the API always returns well-formed JSON error responses.

    Args:
        creds (HTTPAuthorizationCredentials): The parsed Bearer token credentials injected by FastAPI.

    Returns:
        AuthenticatedUser: The validated user object containing identity and group memberships.

    Raises:
        HTTPException: HTTP 500 if the authentication service is misconfigured (RuntimeError).
        HTTPException: HTTP 401 if the token is invalid, expired, or has an incorrect audience (ValueError).
    """
    try:
        return await validate_token(creds.credentials)
    except RuntimeError as exc:
        # Misconfiguration — surface as 500 so operators see the error in logs,
        # not as a generic 401 that looks like a client problem.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service misconfigured",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
