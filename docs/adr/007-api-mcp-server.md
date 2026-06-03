# ADR 007 — REST API and MCP server

**Status:** Accepted
**Date:** 2026-06-02
**Deciders:** Platform team

---

## Context

The Streamlit Data Dictionary is the only way to query the catalog. Several
use cases now require programmatic access:

- **CI/CD pipelines** that assert expected tables and columns exist before
  deploying a model.
- **BI tools and notebooks** that need to look up table descriptions
  without opening a browser.
- **AI coding assistants** (GitHub Copilot, Claude, VS Code Copilot) that
  need structured data dictionary access via the Model Context Protocol (MCP).

ADR 003 chose Streamlit over FastAPI for the *interactive UI*. That decision
still stands. This ADR adds a FastAPI layer that runs alongside Streamlit as
a separate process, sharing the same codebase and the same permission model.

## Decision

Add two new components that run from the same Docker image:

1. **FastAPI REST API** (`src/api/`) — permission-filtered HTTP API for
   programmatic catalog access. Runs as a second Kubernetes Deployment
   (`dd-api`) on port 8080.

2. **FastMCP server** (`src/mcp_server/`) — MCP Streamable HTTP endpoint
   mounted at `/mcp` inside the FastAPI app. Exposes four tools:
   `search_tables`, `get_table_details`, `list_tables`, `get_lineage`.

3. **Redis cache** (`src/cache/`) — async Redis wrapper shared by both the
   API and MCP layer. Gracefully degrades to no-op when `REDIS_URL` is
   unset, so a missing Redis pod never crashes the API.

### Auth

Both the REST API and the MCP endpoint validate **Microsoft Entra ID Bearer
tokens** using RS256 JWT validation (`python-jose`). The JWKS endpoint is
fetched from Entra's discovery URL and cached for one hour.

The same permission enforcement principle from ADR 002 applies: groups are
extracted from the token (or from Microsoft Graph on overage), and every SQL
query runs the `JOIN permissions_cache` filter. The API layer never fetches
all data and filters in Python.

### MCP auth middleware

Because FastMCP does not natively support per-request Bearer token
validation, we wrap the MCP ASGI sub-app in `_MCPAuthMiddleware` — a thin
ASGI middleware that validates the token before the MCP handler runs. The
validated `AuthenticatedUser` is passed to tools via a `contextvars.ContextVar`
(`_current_user`), which is safe across async boundaries.

### Redis cache design

| Key prefix | TTL | Scope |
|---|---|---|
| `ddic:<hash>` (search) | 300 s | query + groups tuple |
| `ddic:<hash>` (table detail) | 600 s | full_name + groups tuple |
| `ddic:<hash>` (lineage) | 300 s | full_name + depth |
| `ddic:<hash>` (groups overage) | 3600 s | user OID |

Cache keys are SHA-256 hashes of the serialised arguments, namespaced with
`ddic:`. The same Redis instance serves both the API and the MCP server.

## Consequences

**Positive**

- External callers get a stable, versioned REST API without touching
  Streamlit session state.
- AI assistants gain structured access via MCP, enabling natural-language
  catalog queries without scraping the UI.
- Redis cache significantly reduces load on DuckDB and Databricks for
  repeated queries from automated tools.

**Negative / trade-offs**

- One additional Kubernetes Deployment (`dd-api`) and a Redis StatefulSet
  to maintain.
- `python-jose` and `httpx` join the dependency surface for JWT validation
  and async JWKS fetching.
- The `_current_user` ContextVar pattern is implicit; future contributors
  must understand that MCP tools rely on middleware injection.

## Alternatives considered

**Expose the API directly from Streamlit** — Streamlit's server is not
designed as an HTTP API host. Custom HTTP handlers were added in Streamlit
1.45 but are considered experimental. Rejected: adds fragility to the UI
process.

**Single unified FastAPI app replacing Streamlit** — Would require rewriting
all UI components. Rejected: high cost, no clear benefit for the target
users (non-technical business analysts).

**SSE transport instead of Streamable HTTP** — SSE is the older MCP
transport and requires two connections (GET for stream, POST for messages).
Streamable HTTP is the recommended transport for remotely hosted MCP servers
and is simpler to deploy behind a standard reverse proxy. Chosen: Streamable HTTP.
