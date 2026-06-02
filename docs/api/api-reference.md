# API and MCP server reference

## Overview

The Data Dictionary exposes a permission-filtered REST API and an MCP
(Model Context Protocol) server alongside the Streamlit UI. Both run from
the same Docker image as a separate process on port 8080.

Start the server:

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8080
```

Interactive OpenAPI docs are available at `http://localhost:8080/docs`.

## Authentication

All endpoints (REST and MCP) require a Microsoft Entra ID Bearer token.

```bash
Authorization: Bearer <access-token>
```

Acquire a token with the correct audience (defaults to `CLIENT_ID`):

```bash
# Using Azure CLI
az account get-access-token --resource $CLIENT_ID --query accessToken -o tsv
```

Set `API_AUDIENCE` when the API has its own app registration separate from
the Streamlit app.

Groups are extracted from the token. If your account belongs to more than
150 groups (Entra overage), groups are resolved via Microsoft Graph using
the same token — no extra credentials required.

## REST endpoints

### Health

```text
GET /health
```

Returns `{"status": "ok"}`. No auth required. Used by k8s liveness probes.

### List tables

```text
GET /api/v1/tables
Authorization: Bearer <token>
```

Returns all tables the caller is authorized to access. Results are cached
for 10 minutes per (user groups) combination.

**Response** — array of `TableSummary`:

| Field | Type | Description |
|---|---|---|
| full_name | string | Unity Catalog three-part identifier |
| catalog_name | string | Catalog |
| schema_name | string | Schema |
| table_name | string | Table |
| table_description | string? | Business description or system comment |
| table_type | string? | TABLE, VIEW, etc. |
| dq_score | string? | Data quality grade (A–F) |
| updated_at | string? | Last modified timestamp |

### Table detail

```text
GET /api/v1/tables/{catalog}/{schema}/{table}
Authorization: Bearer <token>
```

Returns column metadata for a single table. Returns `404` if the table
does not exist or the caller is not authorized.

**Response** — `TableDetail`:

| Field | Type | Description |
|---|---|---|
| full_name | string | Unity Catalog identifier |
| columns | ColumnInfo[] | Ordered list of columns |

**ColumnInfo**:

| Field | Type | Description |
|---|---|---|
| column_name | string | Column name |
| data_type | string | Databricks SQL type |
| description | string? | Business definition or system comment |

### Search

```text
GET /api/v1/search?q=<query>
Authorization: Bearer <token>
```

Hybrid keyword search across table names, descriptions, column names,
and business name overrides. Returns up to 50 results, sorted by relevance
score. Results cached for 5 minutes per (query, user groups) combination.

**Query parameters**:

| Param | Required | Description |
|---|---|---|
| q | yes | Free-text search string (min 1 character) |

**Response** — array of `SearchResult`:

| Field | Type | Description |
|---|---|---|
| full_name | string | Table Unity Catalog identifier |
| name | string | Matched entity name (table or column) |
| match_type | string | `Table`, `Column`, or `Glossary` |
| description | string? | Matched description |
| dq_score | string? | Data quality grade |

### Lineage

```text
GET /api/v1/lineage/{catalog}/{schema}/{table}?depth=1
Authorization: Bearer <token>
```

Returns upstream and downstream lineage edges for a table. `depth`
controls how many hops to traverse (1–5, default 1).

**Response** — array of `LineageEdge`:

| Field | Type | Description |
|---|---|---|
| table_full_name | string | Source table |
| direction | string | `upstream` or `downstream` |
| entity_full_name | string | Related table/entity |
| entity_type | string | `TABLE`, `VIEW`, etc. |
| depth | integer | Hop count from the source table |

## MCP server

The MCP endpoint is at `POST /mcp` (Streamable HTTP transport). Connect
from any MCP-compatible client by pointing it at:

```text
http://<host>:8080/mcp
```

### Connecting from VS Code Copilot

Add to `.vscode/settings.json` (or workspace settings):

```json
{
  "github.copilot.mcpServers": {
    "data-dictionary": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer ${env:DATA_DICT_TOKEN}"
      }
    }
  }
}
```

Set `DATA_DICT_TOKEN` in your shell environment before launching VS Code.

### Connecting from Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "data-dictionary": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/client-http", "http://localhost:8080/mcp"],
      "env": {
        "MCP_BEARER_TOKEN": "<your-entra-token>"
      }
    }
  }
}
```

### Available tools

#### search_tables

Search for tables, columns, and glossary terms.

| Argument | Type | Required | Description |
|---|---|---|---|
| query | string | yes | Free-text search ("customer orders", "revenue") |

Returns a JSON array of matches (same schema as REST `/search`).

#### get_table_details

Get all columns for a specific table.

| Argument | Type | Required | Description |
|---|---|---|---|
| table_full_name | string | yes | catalog.schema.table |

Returns `{"full_name": "...", "columns": [...]}` or
`{"error": "..."}` if not found.

#### list_tables

List accessible tables, optionally filtered.

| Argument | Type | Required | Description |
|---|---|---|---|
| catalog | string | no | Filter to a specific catalog |
| schema | string | no | Filter to a specific schema (requires catalog) |

#### get_lineage

Get data lineage for a table.

| Argument | Type | Required | Description |
|---|---|---|---|
| table_full_name | string | yes | catalog.schema.table |
| depth | integer | no | Hops to traverse, 1–5 (default 1) |

## Environment variables

| Variable | Default | Description |
|---|---|---|
| REDIS_URL | *(unset)* | Redis connection URL. Omit to run without cache. |
| API_AUDIENCE | `CLIENT_ID` | Expected JWT audience claim. Override when the API has its own app registration. |

Existing Entra ID variables (`TENANT_ID`, `CLIENT_ID`) are also used by
the API for JWKS discovery and audience validation.

## Redis cache

Results are cached in Redis to reduce load on Databricks. The cache key is a
SHA-256 hash of the query arguments and the caller's group set.

If `REDIS_URL` is unset or Redis is unreachable, the API continues to work
without caching — every request hits the database directly.

To deploy Redis in Kubernetes, apply the bundled manifests:

```bash
kubectl apply -f k8s/deployment-redis.yaml -f k8s/service-redis.yaml -f k8s/pvc-redis.yaml
```

Then set `REDIS_URL=redis://dd-redis:6379` in `k8s/configmap.yaml`.
