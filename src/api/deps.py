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
    (RuntimeError, ValueError) into standard HTTPExceptions (500 and 401 respectively).
    This architectural choice prevents internal stack traces from leaking to the client,
    ensures well-formed JSON error responses for the REST API, and provides a clear
    HTTP status code mapping for frontend clients to interpret.

    Extracts the Entra ID token from the Authorization header and validates it.
    If the token is invalid or the server is misconfigured, it raises an appropriate
    HTTPException to reject the request.

    Args:
        creds (HTTPAuthorizationCredentials): The parsed Bearer token credentials injected by FastAPI.

    Returns:
        AuthenticatedUser: The validated user object containing identity and group memberships.

    Raises:
        HTTPException (500): If the authentication service is misconfigured.
        HTTPException (401): If the token is invalid, expired, or has an incorrect audience.
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
