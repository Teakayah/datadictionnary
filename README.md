# Data Dictionary

Permission-filtered, search-first business data dictionary for Databricks Unity Catalog.

Authenticates against Microsoft Entra ID, reads catalog metadata from a local DuckDB cache rebuilt nightly, and exposes three surfaces: a Streamlit UI for non-technical users, a REST API for programmatic access, and an MCP server for GitHub Copilot / Claude integration — all enforcing the same push-down RBAC so users can never see tables they lack grants on.

---

## Features

- **Search & discovery** — full-text search across catalogs, schemas, tables, columns, and business glossary terms with hybrid BM25 + optional semantic (vector) ranking
- **Push-down RBAC** — every query joins `permissions_cache` filtered by the user's Entra ID groups; unauthorized rows never leave the SQL engine
- **Inline metadata editing** — column business names, table descriptions, stewards; writes queue locally and are pushed to Unity Catalog by a sidecar sync worker
- **Personalisation** — bookmarks and recents per user
- **REST API** — `GET /api/v1/tables`, `/search`, `/lineage`; Entra ID Bearer JWT required
- **MCP server** — Streamable HTTP at `/mcp`; tools for `search_tables`, `get_table_details`, `list_tables`, `get_lineage`; works with GitHub Copilot and Claude Desktop
- **Redis cache** — shared by the REST API and MCP server; gracefully degrades to direct DB when unavailable
- **Admin tooling** — CMS posts, pipeline triggers (Databricks / ADF / ADO), audit log, sync-queue dashboard, group-cache flush

---

## Architecture

```
                        ┌─────────────────────────────────────────┐
                        │          namespace: data-dictionary      │
                        │                                          │
  Browser ──HTTPS──►  Ingress (nginx)                             │
                        │    │                                     │
                        │    ├──:8501──► dd-app  (Streamlit UI)   │
                        │    └──:8080──► dd-api  (REST + MCP)     │
                        │                   │                      │
                        │              dd-redis :6379              │
                        │                                          │
                        │  dd-sync-worker (sidecar, no ingress)   │
                        │         │                                │
                        │    PVC dd-data (DuckDB files)            │
                        └─────────────────────────────────────────┘
                                  │          │
                             :443 HTTPS  :443 HTTPS
                                  │          │
                          Databricks    Entra ID / Graph
                          Unity Catalog
```

Streamlit pods only write locally to DuckDB. The sync worker drains `user_data.pending_sync` to Databricks and pulls late-arriving rows back (DR resync). The REST API and MCP server share a Redis cache and hit Databricks read-only.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for full data-flow diagrams and [`docs/adr/`](docs/adr/) for decision records.

---

## Quick start

### Local development (no Databricks needed)

```bash
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env

ENABLE_MOCK_AUTH=true ENVIRONMENT=development DEMO_DATA=true streamlit run app.py
```

### With real data

```bash
# Fill in DATABRICKS_HOST, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN,
# TENANT_ID, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI in .env
python scripts/nightly_sync.py   # populate local DuckDB cache
streamlit run app.py
```

### REST API + MCP server

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8080
```

Requires `TENANT_ID` and either `CLIENT_ID` or `API_AUDIENCE` in the environment.

#### Connect GitHub Copilot

Add to VS Code `settings.json`:

```json
"github.copilot.chat.mcp.servers": {
  "data-dictionary": {
    "url": "https://datadictionary.internal/mcp",
    "headers": { "Authorization": "Bearer <entra-token>" }
  }
}
```

#### Connect Claude Desktop

```json
{
  "mcpServers": {
    "data-dictionary": {
      "url": "https://datadictionary.internal/mcp",
      "headers": { "Authorization": "Bearer <entra-token>" }
    }
  }
}
```

---

## Testing

```bash
pytest tests/ -q \
  --ignore=tests/test_load_smoke.py \
  --ignore=tests/test_wcag_axe.py \
  --ignore=tests/test_nav_render.py
```

The three excluded suites require a live app or Playwright (`playwright install chromium`) and run in CI separately.

Key test files:

| File | What it covers |
|---|---|
| `tests/test_security.py` | Auth enforcement, JWT algorithm attacks, security headers, CORS, input limits, MCP auth independence |
| `tests/test_api_endpoints.py` | REST endpoint contract, cache hit/miss, 401/404/422 responses |
| `tests/test_api_auth.py` | JWT validation, JWKS caching, groups overage via Graph |
| `tests/test_mcp_server.py` | MCP tools directly, ContextVar injection, depth clamping |
| `tests/test_cache.py` | Redis wrapper, graceful degradation, key stability |

---

## Deployment (Azure DevOps → AKS)

CI/CD is defined in [`azure-pipelines.yml`](azure-pipelines.yml) — three stages:

1. **Test** — `pytest` with JUnit output
2. **Build** — multi-stage Docker build, push to ACR
3. **Deploy** — `kubectl apply` across all k8s manifests, waits for rollout of `dd-app`, `dd-api`, `dd-sync-worker`

### First-time cluster setup

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secret.yaml        # fill placeholders first
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/                   # apply everything else
```

### Workloads and autoscaling

| Deployment | Min pods | Max pods | Scale trigger |
|---|---|---|---|
| `dd-app` (Streamlit) | 2 | 10 | CPU > 70% or memory > 80% |
| `dd-api` (FastAPI) | 2 | 8 | CPU > 65% or memory > 80% |
| `dd-sync-worker` | 1 | 1 (singleton) | — |
| `dd-redis` | 1 | 1 (cache, not HA) | — |

### Network policy summary

| Pod | Inbound allowed from | Outbound allowed to |
|---|---|---|
| `dd-app` | `ingress-nginx` namespace only | `:443` + DNS |
| `dd-api` | `ingress-nginx` + intra-namespace pods | `:443`, `dd-redis:6379`, DNS |
| `dd-sync-worker` | none | `:443` + DNS |
| `dd-redis` | intra-namespace pods only | none |

---

## Environment variables

See [`.env.example`](.env.example) for the full reference. Key variables:

| Variable | Required | Description |
|---|---|---|
| `DATABRICKS_HOST` | yes | Databricks workspace URL |
| `DATABRICKS_HTTP_PATH` | yes | SQL Warehouse HTTP path |
| `DATABRICKS_TOKEN` | yes | PAT for nightly sync |
| `TENANT_ID` | yes | Entra ID tenant |
| `CLIENT_ID` | yes | App registration client ID |
| `CLIENT_SECRET` | yes | App registration secret |
| `REDIRECT_URI` | yes | OIDC callback URL |
| `REDIS_URL` | no | `redis://host:6379` — omit to disable cache |
| `API_AUDIENCE` | no | Override JWT audience (defaults to `CLIENT_ID`) |
| `ADMIN_GROUPS` | no | Comma-separated Entra group names for admin access |
| `ENABLE_MOCK_AUTH` | dev only | Skip Entra ID (requires `ENVIRONMENT=development`) |
| `DEMO_DATA` | dev only | Run fully offline with fixture data |

---

## Repository layout

```
app.py                   Streamlit entry point
src/
  api/                   FastAPI app (REST + MCP)
    main.py              ASGI app, security middleware
    auth.py              Entra ID JWT validation
    routers/             health, tables, search, lineage
  mcp_server/server.py   FastMCP tools
  cache/redis_cache.py   Async Redis wrapper with graceful degradation
  db/                    DuckDB query layer (Streamlit)
  ui/                    Streamlit UI components
  sync/                  Sidecar daemon + push queue
k8s/                     Kubernetes manifests
tests/                   ~800 unit + integration tests
docs/
  adr/                   Architecture decision records (001–007)
  api/                   API reference
  runbooks/              Ops runbooks
scripts/                 Nightly sync, test data generation, doc builder
azure-pipelines.yml      CI/CD pipeline (Test → Build → Deploy)
Dockerfile               Multi-stage build
```

---

## Documentation

| | |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System design, data flows, component responsibilities |
| [`docs/adr/`](docs/adr/) | Architecture decision records |
| [`docs/api/api-reference.md`](docs/api/api-reference.md) | REST + MCP API reference |
| [`docs/runbooks/`](docs/runbooks/) | Sync-worker ops, secret rotation |
| [`design_system/README.md`](design_system/README.md) | UI design system and tokens |
| [`CLAUDE.md`](CLAUDE.md) | Codebase guide for Claude Code sessions |

---

## License

See [`LICENSE`](LICENSE).
