# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| `main` / `0.1.x` | Yes |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, report security issues privately through your organization's security contact or via the repository's private security advisory channel (GitHub **Security → Advisories → Report a vulnerability**). Include:

- A description of the issue and affected component (`dd-app`, `dd-api`, `mcp`, `dd-sync-worker`, or Kubernetes manifests).
- Steps to reproduce or a minimal proof of concept.
- Potential impact (e.g., authorization bypass, injection, token validation, secret exposure).

We aim to acknowledge reports within 2 business days and provide remediation guidance or a patch as quickly as possible.

## Security Architecture Summary

- **Push-down RBAC**: Every catalog query joins `permissions_cache` inside the SQL engine filtered by the caller's Microsoft Entra ID groups (`SELECT_ALL_USERS` sentinel for public tables). Unauthorized rows are never fetched and filtered in Python.
- **API & MCP Authentication**: `dd-api` requires Microsoft Entra ID Bearer JWTs validated with pinned `RS256` (`src/api/auth.py`). MCP authentication is enforced in dedicated ASGI middleware (`_MCPAuthMiddleware`) independent of FastAPI dependency injection.
- **Mock Auth Guard**: `app.py` refuses to start if `ENABLE_MOCK_AUTH=true` is set outside `ENVIRONMENT=development`.
- **Dependency Baseline**: Transitive security floors are pinned in `constraints.txt`. See [`docs/security/ITSG-33-dependency-security-review.md`](docs/security/ITSG-33-dependency-security-review.md) for the full dependency security assessment.
