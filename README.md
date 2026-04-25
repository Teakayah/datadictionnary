# Business Data Dictionary for Unity Catalog

An enterprise-grade, high-performance metadata browser for Databricks Unity Catalog. Provides business users with a searchable, permission-filtered view of organizational data assets — without requiring direct Databricks access.

---

## Architecture

The solution uses a decoupled, three-component architecture designed for performance and reliability.

**Frontend (`app.py`)** — Streamlit application with a bespoke design system, editorial typography, OIDC authentication, and permission-aware search across five tabs: search, discovery, health, glossary, and admin.

**Metadata sync job (`scripts/sync_metadata.py`)** — Background process that crawls Unity Catalog (catalogs → schemas → tables → columns → grants → lineage) and writes results into both a Databricks SQL Warehouse and a local DuckDB file.

**Two-file DuckDB local cache** — When `DUCKDB_PATH` is set, the app serves all queries from a local DuckDB file instead of going across the network. Two files are used:

| File | Owner | Contents |
|------|-------|----------|
| `DUCKDB_PATH` (e.g. `dict.duckdb`) | Sync job | `tables_metadata`, `columns_metadata`, `permissions_cache`, `lineage_cache`, `object_tags`, `audit_log` — rebuilt atomically on each sync via `os.replace` |
| `USER_DATA_PATH` (auto-derived as `dict_user_data.duckdb`) | App | `user_data.comments`, `user_data.business_name_overrides`, `user_data.audit_log` — append-only, never touched by the sync job |

The app opens the catalog file and `ATTACH`es the user data file as the `user_data` schema, enabling cross-file JOINs. All writes are serialized through a singleton connection and a `threading.Lock`.

---

## Prerequisites

- Python 3.9+
- Databricks workspace with Unity Catalog enabled
- Microsoft Entra ID app registration (for OIDC auth)

---

## Installation

```bash
git clone <repository-url>
cd datadictionnary
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
```

---

## Configuration

| Variable | Description |
|----------|-------------|
| `DATABRICKS_HOST` | Workspace URL (e.g. `adb-xxx.azuredatabricks.net`) |
| `DATABRICKS_HTTP_PATH` | SQL Warehouse HTTP path |
| `DATABRICKS_TOKEN` | Personal access token for the sync job |
| `TENANT_ID` | Entra ID tenant ID |
| `CLIENT_ID` | App registration client ID |
| `CLIENT_SECRET` | App registration client secret |
| `REDIRECT_URI` | Must match app registration (e.g. `http://localhost:8501`) |
| `ENABLE_MOCK_AUTH` | `true` to bypass Entra ID during local development |
| `ENVIRONMENT` | `development` to enable mock auth |
| `DEMO_DATA` | `true` to use built-in sample data (no Databricks connection needed) |
| `EDITOR_GROUPS` | Comma-separated Entra ID group object IDs that may edit business names |
| `ADMIN_GROUPS` | Comma-separated Entra ID group object IDs that may access the admin dashboard |
| `DUCKDB_PATH` | Path to the local catalog cache file (e.g. `dict.duckdb`). Leave blank to always query Databricks directly |
| `SMTP_HOST` / `SMTP_PORT` | SMTP server for comment notification emails |
| `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | SMTP credentials |

---

## Running the app

The sync job must run before the app has any data.

```bash
# 1. Sync metadata from Unity Catalog
python scripts/sync_metadata.py

# 2. Start the frontend
streamlit run app.py
```

The sync job writes to the Databricks cache and, if `DUCKDB_PATH` is set, exports a local DuckDB snapshot. Subsequent syncs atomically replace the catalog file without interrupting in-flight reads.

---

## Development mode

For local UI development without any Databricks or Entra ID dependency:

```bash
# .env
ENABLE_MOCK_AUTH=true
ENVIRONMENT=development
DEMO_DATA=true
EDITOR_GROUPS=finance_dept_id
ADMIN_GROUPS=finance_dept_id
```

Clicking the mock login button sets `user_groups = ["finance_dept_id", "all_employees_id"]`, granting both editor and admin access to all demo data.

---

## Security model

**Authentication** — OIDC via Microsoft Entra ID. The `groups` claim in the ID token is used to determine group membership.

**Authorization** — Every search query JOINs `tables_metadata` with `permissions_cache WHERE principal IN ($user_groups)`. No Python-side filtering is applied — unauthorized rows are never returned from the engine. The sentinel value `SELECT_ALL_USERS` in `permissions_cache.principal` marks publicly accessible tables.

**Feature access** — `EDITOR_GROUPS` controls who can save comments and business name overrides. `ADMIN_GROUPS` controls who can access the admin dashboard and audit logs (no demo bypass).

**Hardening** — User-supplied display names are HTML-escaped before rendering. SMTP headers are sanitized to prevent header injection.

---

## Test suite

```bash
python -m pytest --tb=short -q
```

| File | Coverage |
|------|----------|
| `tests/test_app.py` | Auth flows, search, table detail, design system CSS compliance |
| `tests/test_admin.py` | `is_admin()`, nav visibility, admin page rendering, audit log |
| `tests/test_duckdb_cache.py` | `_to_duckdb_sql`, `_DuckDBCursor`/`_DuckDBConn` adapter, `write_duckdb`, `_duckdb_available` |
| `tests/test_navigation.py` | Tab routing, health dashboard, catalog browser, discovery |
| `tests/test_sync_metadata.py` | `setup_cache_tables` DDL, `sync` orchestration, `fetch_lineage` parsing |

---

## Project structure

```
app.py                    Main Streamlit application and design system CSS
scripts/
  sync_metadata.py        Unity Catalog crawler and DuckDB/SQL exporter
tests/
  conftest.py             Shared fixtures and SQL mock helpers
  test_app.py
  test_admin.py
  test_duckdb_cache.py
  test_navigation.py
  test_sync_metadata.py
design_system/
  colors_and_type.css     Design tokens (CSS variables)
  README.md               Full design system specification
  ui_kits/app/            React JSX prototypes of every screen
assets/
  logo-mark.svg
  logo-wordmark.svg
.env.example              Environment variable reference
requirements.txt
```
