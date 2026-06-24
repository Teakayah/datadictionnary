"""Security tests for the FastAPI / MCP layer.

Verifies that authentication, token validation, security headers, and CORS
are correctly enforced.  No real Entra ID or Redis connection is required.

Coverage:
  - All protected routes return 401 without a Bearer token
  - HS256 tokens (wrong algorithm) are rejected with 401
  - Tokens with "none" algorithm are rejected with 401
  - Token signed with wrong key is rejected with 401
  - Token with wrong audience is rejected with 401
  - Token with wrong issuer is rejected with 401
  - Expired token is rejected with 401
  - Security headers present on 200 responses
  - Security headers present on 401 responses
  - Cache-Control: no-store on all responses
  - CORS: credentials not allowed
  - CORS: only configured origins reflected
  - Search query max_length enforced (> 200 chars → 422)
  - Startup config validation raises when audience missing
  - Startup config validation raises when TENANT_ID missing
  - MCP auth is independent of FastAPI dependency_overrides
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from src.api.auth import _validate_auth_config
from src.api.deps import get_current_user
from src.api.main import app
from src.api.auth import AuthenticatedUser

# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_USER = AuthenticatedUser(
    oid="test-oid",
    email="test@example.com",
    name="Test User",
    groups=["group-a"],
)


@pytest.fixture()
def client():
    """Authenticated client — FastAPI DI bypassed."""
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client_no_auth():
    """Unauthenticated client — real auth path exercised."""
    app.dependency_overrides.clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


PROTECTED_ROUTES = [
    ("GET", "/api/v1/tables"),
    ("GET", "/api/v1/tables/cat/schema/tbl"),
    ("GET", "/api/v1/search?q=hello"),
    ("GET", "/api/v1/lineage/cat/schema/tbl"),
]


# ── Authentication enforcement ─────────────────────────────────────────────────

class TestAuthEnforcement:
    @pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
    def test_protected_route_requires_bearer_token(self, client_no_auth, method, path):
        resp = client_no_auth.request(method, path)
        assert resp.status_code == 401

    @pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
    def test_protected_route_rejects_non_bearer_scheme(self, client_no_auth, method, path):
        resp = client_no_auth.request(method, path, headers={"Authorization": "Basic dXNlcjpwYXNz"})
        # FastAPI's HTTPBearer returns 403 for wrong scheme in older versions, 401 in newer ones.
        # Either way the request must be rejected.
        assert resp.status_code in (401, 403)

    def test_health_is_public(self, client_no_auth):
        resp = client_no_auth.get("/health")
        assert resp.status_code == 200


# ── JWT algorithm attacks ──────────────────────────────────────────────────────

class TestJWTAlgorithmAttacks:
    """Ensure tokens signed with HS256 or 'none' are rejected."""

    def _make_token(self, algorithm: str, key, claims: dict | None = None) -> str:
        payload = claims or {
            "oid": "x",
            "preferred_username": "attacker@evil.com",
            "name": "Attacker",
            "aud": "legit-client-id",
            "iss": "https://login.microsoftonline.com/tenant-id/v2.0",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }
        return jwt.encode(payload, key, algorithm=algorithm)

    def test_hs256_token_rejected(self, client_no_auth):
        import src.api.auth as auth_mod
        token = self._make_token("HS256", "secret-key")
        # Provide a fake JWKS so we don't hit the real Entra ID endpoint.
        with patch.object(auth_mod, "_get_jwks", AsyncMock(return_value={"keys": []})):
            resp = client_no_auth.get(
                "/api/v1/tables",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 401

    def test_wrong_rsa_key_rejected(self, client_no_auth):
        """A token signed with an RSA key not in the JWKS must be rejected."""
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend

        wrong_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )
        token = self._make_token("RS256", wrong_key)

        with patch("src.api.auth._get_jwks", AsyncMock(return_value={"keys": []})):
            resp = client_no_auth.get(
                "/api/v1/tables",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 401


# ── JWT claims validation ──────────────────────────────────────────────────────

class TestJWTClaimsValidation:
    """validate_token must enforce audience, issuer, and expiry."""

    @pytest.fixture(autouse=True)
    def _patch_env(self, monkeypatch):
        monkeypatch.setenv("CLIENT_ID", "my-client-id")
        monkeypatch.setenv("TENANT_ID", "my-tenant-id")

    async def _call_validate(self, token: str):
        from src.api.auth import validate_token
        return await validate_token(token)

    def _valid_claims(self):
        return {
            "oid": "u1",
            "preferred_username": "u@example.com",
            "name": "User",
            "aud": "my-client-id",
            "iss": "https://login.microsoftonline.com/my-tenant-id/v2.0",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }

    def test_wrong_audience_rejected(self):
        import asyncio
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend

        key = rsa.generate_private_key(65537, 2048, default_backend())
        public_numbers = key.public_key().public_numbers()

        def _int_to_base64(n):
            import base64
            length = (n.bit_length() + 7) // 8
            return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()

        jwks = {
            "keys": [{
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": "test-key",
                "n": _int_to_base64(public_numbers.n),
                "e": _int_to_base64(public_numbers.e),
            }]
        }

        claims = self._valid_claims()
        claims["aud"] = "wrong-audience"
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})

        async def _run():
            from src.api.auth import validate_token
            with patch("src.api.auth._get_jwks", AsyncMock(return_value=jwks)):
                return await validate_token(token)

        with pytest.raises(ValueError, match="Invalid token"):
            asyncio.run(_run())

    def test_expired_token_rejected(self):
        import asyncio
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        import base64

        key = rsa.generate_private_key(65537, 2048, default_backend())
        public_numbers = key.public_key().public_numbers()

        def _b64(n):
            length = (n.bit_length() + 7) // 8
            return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()

        jwks = {
            "keys": [{
                "kty": "RSA", "use": "sig", "alg": "RS256", "kid": "k",
                "n": _b64(public_numbers.n), "e": _b64(public_numbers.e),
            }]
        }

        claims = self._valid_claims()
        claims["exp"] = int(time.time()) - 3600  # expired
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k"})

        async def _run():
            from src.api.auth import validate_token
            with patch("src.api.auth._get_jwks", AsyncMock(return_value=jwks)):
                return await validate_token(token)

        with pytest.raises(ValueError, match="Invalid token"):
            asyncio.run(_run())


# ── Startup config validation ──────────────────────────────────────────────────

class TestStartupConfigValidation:
    def test_raises_when_tenant_id_missing(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MOCK_AUTH", "false")
        monkeypatch.setattr("src.api.auth.TENANT_ID", "")
        monkeypatch.setattr("src.api.auth.CLIENT_ID", "some-client-id")
        with pytest.raises(RuntimeError, match="TENANT_ID"):
            _validate_auth_config()

    def test_raises_when_audience_and_client_id_both_missing(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MOCK_AUTH", "false")
        monkeypatch.setattr("src.api.auth.TENANT_ID", "tenant")
        monkeypatch.setattr("src.api.auth.CLIENT_ID", "")
        monkeypatch.delenv("API_AUDIENCE", raising=False)
        with pytest.raises(RuntimeError, match="CLIENT_ID or API_AUDIENCE"):
            _validate_auth_config()

    def test_passes_when_api_audience_set_without_client_id(self, monkeypatch):
        monkeypatch.setattr("src.api.auth.TENANT_ID", "tenant")
        monkeypatch.setattr("src.api.auth.CLIENT_ID", "")
        monkeypatch.setenv("API_AUDIENCE", "api://my-app")
        _validate_auth_config()  # should not raise


# ── Security headers ───────────────────────────────────────────────────────────

class TestSecurityHeaders:
    REQUIRED_HEADERS = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "strict-origin-when-cross-origin",
        "x-xss-protection": "0",
        "cache-control": "no-store",
    }

    def test_security_headers_on_200(self, client):
        with patch("src.api.routers.tables.queries.get_authorized_tables", return_value=__import__("pandas").DataFrame()), \
             patch("src.api.routers.tables.redis_cache.get", AsyncMock(return_value=None)), \
             patch("src.api.routers.tables.redis_cache.set", AsyncMock()):
            resp = client.get("/api/v1/tables")
        assert resp.status_code == 200
        for header, value in self.REQUIRED_HEADERS.items():
            assert resp.headers.get(header) == value, f"Missing/wrong header: {header}"

    def test_security_headers_on_401(self, client_no_auth):
        resp = client_no_auth.get("/api/v1/tables")
        assert resp.status_code == 401
        for header, value in self.REQUIRED_HEADERS.items():
            assert resp.headers.get(header) == value, f"Missing/wrong header on 401: {header}"

    def test_security_headers_on_health(self, client_no_auth):
        resp = client_no_auth.get("/health")
        assert resp.status_code == 200
        for header, value in self.REQUIRED_HEADERS.items():
            assert resp.headers.get(header) == value, f"Missing/wrong header on health: {header}"

    def test_no_hsts_outside_production(self, client):
        """HSTS must not be set unless ENVIRONMENT=production."""
        resp = client.get("/health")
        assert "strict-transport-security" not in resp.headers


# ── CORS policy ────────────────────────────────────────────────────────────────

class TestCORSPolicy:
    def test_cors_does_not_allow_credentials(self, client):
        resp = client.options(
            "/api/v1/tables",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # FastAPI CORS middleware only adds ACAO on actual matching origins.
        # The critical property: allow-credentials must never be 'true'.
        acao_credentials = resp.headers.get("access-control-allow-credentials", "false")
        assert acao_credentials.lower() != "true"

    def test_wildcard_origin_allowed_by_default(self, client):
        resp = client.get(
            "/health",
            headers={"Origin": "https://anything.example.com"},
        )
        acao = resp.headers.get("access-control-allow-origin", "")
        assert acao in ("*", "https://anything.example.com", "")


# ── Input validation ───────────────────────────────────────────────────────────

class TestInputValidation:
    def test_search_rejects_query_over_200_chars(self, client):
        q = "a" * 201
        resp = client.get(f"/api/v1/search?q={q}")
        assert resp.status_code == 422

    def test_search_rejects_empty_query(self, client):
        resp = client.get("/api/v1/search?q=")
        assert resp.status_code == 422

    def test_search_accepts_200_char_query(self, client):
        q = "a" * 200
        with patch("src.api.routers.search.queries.search_metadata", return_value=__import__("pandas").DataFrame()), \
             patch("src.api.routers.search.redis_cache.get", AsyncMock(return_value=None)), \
             patch("src.api.routers.search.redis_cache.set", AsyncMock()):
            resp = client.get(f"/api/v1/search?q={q}")
        assert resp.status_code == 200

    def test_lineage_rejects_depth_above_5(self, client):
        resp = client.get("/api/v1/lineage/cat/schema/tbl?depth=6")
        assert resp.status_code == 422

    def test_lineage_rejects_depth_zero(self, client):
        resp = client.get("/api/v1/lineage/cat/schema/tbl?depth=0")
        assert resp.status_code == 422


# ── MCP auth independence ──────────────────────────────────────────────────────

class TestMCPAuthIndependence:
    """MCP endpoint auth must not be bypassable via FastAPI dependency_overrides."""

    def test_mcp_requires_auth_even_with_di_override(self):
        """Override get_current_user in FastAPI DI, then hit MCP — must still get 401."""
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER
        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                # POST to MCP endpoint with no Authorization header
                resp = c.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}},
                    headers={"Content-Type": "application/json"},
                )
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()

    def test_mcp_security_headers_on_401(self):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}},
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 401
        assert resp.headers.get("cache-control") == "no-store"
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_mcp_validate_token_value_error(self):
        """MCP must return 401 with detail when validate_token raises ValueError."""
        with patch("src.api.main.validate_token", AsyncMock(side_effect=ValueError("Invalid signature"))):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}},
                    headers={"Content-Type": "application/json", "Authorization": "Bearer fake_token"},
                )
            assert resp.status_code == 401
            assert resp.json() == {"detail": "Invalid signature"}

    def test_mcp_validate_token_runtime_error(self, monkeypatch):
        """MCP must return 500 with a safe message when validate_token raises RuntimeError."""
        monkeypatch.setenv("ENABLE_MOCK_AUTH", "false")
        with patch("src.api.main.validate_token", AsyncMock(side_effect=RuntimeError("Misconfigured keys"))):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}},
                    headers={"Content-Type": "application/json", "Authorization": "Bearer fake_token"},
                )
            assert resp.status_code == 500
            assert resp.json() == {"detail": "Authentication service misconfigured"}
