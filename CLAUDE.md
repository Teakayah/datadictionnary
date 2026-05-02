# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the Streamlit app
streamlit run app.py

# Run the metadata sync job (must be run before the app has any data)
python scripts/nightly_sync.py

# Configure environment
cp .env.example .env
# Then fill in DATABRICKS_HOST, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN, TENANT_ID, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI

# Run tests (excludes load tests and playwright tests which need live infra)
pip install -r requirements-dev.txt
python -m pytest tests/ -q --ignore=tests/test_load_smoke.py --ignore=tests/test_wcag_axe.py --ignore=tests/test_nav_render.py

# Record a demo video (requires the app to be running with mock auth)
ENABLE_MOCK_AUTH=true ENVIRONMENT=development streamlit run app.py &
python scripts/record_video.py
```

## Architecture

This is a **Python-native Business Data Dictionary** for Databricks Unity Catalog. It exposes a searchable, permission-filtered view of catalog metadata to non-technical business users.

### Three-component design

**`scripts/nightly_sync.py` — Metadata Sync Job**
- Uses `databricks-sdk` (`WorkspaceClient`) to crawl Unity Catalog hierarchy (catalogs → schemas → tables → columns)
- Extracts structural metadata, comments/tags, and all `GRANT` permissions per table
- Writes results via truncate-and-reload into three cache tables in `data_governance.dictionary_cache`:
  - `tables_metadata` — one row per table with `full_name`, description, type
  - `columns_metadata` — one row per column with type and description
  - `permissions_cache` — one row per (table, principal, privilege) grant

**`app.py` — Streamlit Frontend** (thin orchestrator, ~725 lines)
- On startup: checks for `ENABLE_MOCK_AUTH` and `ENVIRONMENT` env vars; if true and development, falls back to **Mock Auth** for local dev
- Real auth: MSAL OAuth 2.0 / OIDC flow against Entra ID; user's AD group Object IDs are read from the `groups` claim of the ID token
- All business logic lives in `src/`: auth (`src/auth.py`), queries (`src/db/`), UI components (`src/ui/`), pages (`src/pages/`), sync (`src/sync/`)
- Search queries always `JOIN tables_metadata` with `permissions_cache` filtered by `p.principal IN (user's groups)` — users mathematically cannot see unauthorized tables

### Security model
Permission enforcement is "push-down" SQL: the Streamlit app never fetches all results and filters in Python. The `JOIN` with `permissions_cache` happens inside the SQL Warehouse, so only authorized rows are returned. The sentinel value `SELECT_ALL_USERS` in `permissions_cache.principal` acts as a public-access flag.

### Cache location
All cache tables live in `data_governance.dictionary_cache` (constants `CATALOG_CACHE`/`SCHEMA_CACHE` defined in both files). `setup_cache_tables()` in the sync script creates the catalog, schema, and tables with `IF NOT EXISTS` — safe to run repeatedly.

### Development with Mock Auth
When `ENABLE_MOCK_AUTH=true` and `ENVIRONMENT=development` are set, the app skips Entra ID and renders a department selector with a "Sign in" button. The default department is `Finance` (groups: `["finance_group", "SELECT_ALL_USERS"]`). No Databricks credentials are needed for UI development — use `DEMO_DATA=true` to run fully offline with fixture data.

## Design system

All new UI work must follow the design system defined in `design_system/`. The canonical reference is `design_system/README.md`. Key rules:

**Branch:** All design/UI work lives on `feature/design-system` and must be merged before adding new product features that touch the UI.

**Tokens** (`design_system/colors_and_type.css`): Always use CSS variables (`--paper`, `--ink`, `--accent`, etc.) — never hard-code hex values. The only accent color is oxidized red `#B8362A`.

**Fonts:** Fraunces (display serif, headlines), Manrope (body sans, UI), JetBrains Mono (all identifiers, table/column names, counts, SQL). Load via Google Fonts `@import` already present in `DESIGN_CSS` in `app.py`.

**Tone & copy:** Sentence case everywhere. No emoji in UI. Section headers use `§` prefix (e.g. `§ Catalog search`). Monospace for all Unity Catalog identifiers. See `design_system/README.md` → Content Fundamentals for the full style guide.

**Streamlit CSS injection:** CSS lives in `src/ui/css.py` (`DESIGN_CSS`, `VIS_WIDE_CSS`) and is injected via `st.markdown('<style>...</style>', unsafe_allow_html=True)` at startup via `render_css()`. Add new component styles there, not inline.

**Component reference:** `design_system/ui_kits/app/` contains React JSX prototypes of every screen (SignIn, SearchBar, ResultsList, TableDetail, AppShell). These are the pixel-perfect design targets — use them as spec when building new Streamlit screens.

**Assets:** `assets/` holds the logo SVGs (`logo-mark.svg`, `logo-wordmark.svg`). The logo mark is inlined as a string in `app.py` (`LOGO_MARK_SVG`) to avoid Streamlit static-file serving issues.

## Roadmap context
- Phases 1–10 (complete): Full app.py decomposition into `src/` modules, DuckDB local cache, i18n (EN/FR), personalization, lineage, health dashboard, admin page, sync worker
- Next: Entra ID redirect loop hardening, tooltips on icon-only buttons (accessibility), load test hardening
