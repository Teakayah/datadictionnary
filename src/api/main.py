"""FastAPI application — REST API + MCP server for the Data Dictionary.

Start with:
    uvicorn src.api.main:app --host 0.0.0.0 --port 8080

Endpoints
---------
GET  /health/live                        liveness probe (no auth)
GET  /health/ready                       readiness probe (no auth)
GET  /api/v1/tables                      list authorized tables
GET  /api/v1/tables/{cat}/{schema}/{tbl} table columns + descriptions
GET  /api/v1/search?q=...               hybrid keyword search
GET  /api/v1/lineage/{cat}/{schema}/{tbl} lineage graph
POST /mcp                                MCP Streamable HTTP endpoint
GET  /docs                               OpenAPI UI
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.auth import _validate_auth_config, validate_token
from src.api.routers import health, lineage, search, tables
from src.mcp_server.server import _current_user, mcp

logger = logging.getLogger(__name__)


# ── Security headers ──────────────────────────────────────────────────────────

_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    # Disable legacy XSS filter — modern browsers ignore it and it can cause
    # security issues of its own.
    (b"x-xss-protection", b"0"),
    # API responses must not be cached by proxies or browsers.
    (b"cache-control", b"no-store"),
]

if os.getenv("ENVIRONMENT") == "production":
    _SECURITY_HEADERS.append(
        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
    )


class _SecurityHeadersMiddleware:
    """Inject security headers into every HTTP response."""

    def __init__(self, app) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def _patched_send(message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(_SECURITY_HEADERS)
                message = {**message, "headers": headers}
            await send(message)

        await self._app(scope, receive, _patched_send)


# ── Startup validation ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_auth_config()
    yield


# ── CORS ─────────────────────────────────────────────────────────────────────
# Restrict origins via ALLOWED_ORIGINS env var (comma-separated).
# Defaults to ["*"] for backward-compat; set explicitly in production.
# We never allow credentials here because all auth is via Bearer tokens
# in headers, never cookies.  Mixing credentials=True with "*" is
# forbidden by the CORS spec anyway.

_raw = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw.split(",") if o.strip()] or ["*"]


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Data Dictionary API",
    description=(
        "Permission-filtered REST API and MCP server for the Databricks "
        "Business Data Dictionary. All endpoints require a valid Microsoft "
        "Entra ID Bearer token."
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "meta", "description": "Health checks"},
        {"name": "tables", "description": "Table listings and column details"},
        {"name": "search", "description": "Full-text and hybrid search"},
        {"name": "lineage", "description": "Data lineage traversal"},
    ],
)

# Security headers on every response (registered first so they wrap all others)
app.add_middleware(_SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,          # Bearer token in header, never cookies
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    expose_headers=[],
)

app.include_router(health.router)
app.include_router(tables.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(lineage.router, prefix="/api/v1")


# ── MCP sub-app with auth middleware ──────────────────────────────────────────

class _MCPAuthMiddleware:
    """ASGI middleware that validates Bearer tokens before the MCP handler.

    This is intentionally independent of FastAPI's dependency injection so
    that test-time dependency_overrides cannot bypass MCP authentication.
    """

    def __init__(self, mcp_app) -> None:
        self._app = mcp_app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        auth = headers.get(b"authorization", b"").decode()

        if not auth.startswith("Bearer "):
            await self._reject(send, 401, "Authentication required")
            return

        try:
            user = await validate_token(auth[7:])
        except RuntimeError:
            # Server misconfiguration — do not leak details to caller.
            logger.error("MCP auth: server misconfiguration in validate_token")
            await self._reject(send, 500, "Authentication service misconfigured")
            return
        except ValueError as exc:
            await self._reject(send, 401, str(exc))
            return

        token = _current_user.set(user)
        try:
            await self._app(scope, receive, send)
        finally:
            _current_user.reset(token)

    @staticmethod
    async def _reject(send, status: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode()
        # Security headers are injected by _SecurityHeadersMiddleware (the outer
        # ASGI wrapper) — do not add them here to avoid duplicates.
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b"Bearer"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})


mcp_asgi = mcp.streamable_http_app()
app.mount("/mcp", _MCPAuthMiddleware(mcp_asgi))
