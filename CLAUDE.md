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

**`app.py` — Streamlit Frontend** (~180 lines, just the entry point)
- On startup: refuses to boot with `ENABLE_MOCK_AUTH=true` outside `ENVIRONMENT=development`. If both are set, runs the mock-auth path (department selector); otherwise the real MSAL OIDC flow.
- All business logic lives in `src/`: auth (`src/auth.py`, `src/auth_graph.py`), queries (`src/db/`), storage backends (`src/storage/`), UI components (`src/ui/cards/` package), pages (`src/pages/`), sync (`src/sync/`).
- Search queries always `JOIN tables_metadata` with `permissions_cache` filtered by `p.principal IN (user's groups)` — users mathematically cannot see unauthorized tables.
- Group resolution: inline `groups` claim when present; Microsoft Graph `getMemberObjects` for users in 150+ groups (overage). 1 h process-level cache keyed by user OID; cleared on sign-out so a fresh sign-in always reflects current Entra state.

**`python -m src.sync.daemon` — Sidecar Sync Worker** (separate process)
- Drains `user_data.pending_sync` to Databricks (`ALTER TABLE … COMMENT`, audit-log INSERT, etc.) and runs DR resync.
- Stale-row recovery on every cycle (rows in `'syncing'` for >5 min flip back to `'pending'`).
- HTTP `/healthz` on port 8765; k8s liveness probe goes red if heartbeat is stale (>60 s).
- Replaces the previous in-process daemon thread (`_start_sync_worker_thread`, removed in TODO #1). See `docs/adr/004-sidecar-sync-worker.md` and `docs/runbooks/sync-worker.md`.

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

## Feature reference

### Admin editing toggle (`src/personalization.py`)
- `is_editing_enabled()` — reads `value` from `user_data.site_settings WHERE key='editing_enabled'`; defaults to `True` when DuckDB is unavailable; result cached in `st.session_state["_editing_enabled_cache"]`
- `set_editing_enabled(enabled, actor_email)` — upserts the flag and updates the session cache immediately
- `is_power_user()` gates on `is_editing_enabled()` first — returns `False` instantly when editing is globally off
- Admin page renders a `§ Inline editing` toggle section; toggling calls `set_editing_enabled()` then `st.rerun()`

### CMS discovery banner (`src/cms.py` + `src/storage/cms_storage.py`)
- Admins publish posts that appear as pinned cards above the Discovery sub-tabs
- Post types: `announcement` (red), `featured_table` (blue), `guide` (green)
- Schema: `post_id`, `post_type`, `title`, `body`, `table_ref` (featured_table only), `author_email`, `created_at`, `expires_at`
- Expiry options live in `_EXPIRY_DAYS`: 2 / 7 / 30 days or `None` (never)
- `src/cms.py` is a thin wrapper around `CMSStorage` — see `src/storage/cms_storage.py` for backends (Demo / DuckDB / Fake)
- `render_cms_banner()` in `src/ui/cards/discovery.py` — called from `render_discovery()` between the hero and the sub-tab selector; admin users see a ✕ delete button per card; featured_table cards navigate to the Search tab
- Admin CRUD lives in `_render_admin_cms_section()` / `_show_cms_create_dialog()` in `src/ui/cards/cms_admin.py`
- DB table: `user_data.cms_posts` (created by `_initialize_schema()`)
- Demo-mode fallback: session state key `_demo_cms_posts`
- `create_post` and `delete_post` raise `PermissionError` if the caller is not an admin — defense-in-depth alongside the UI gate

### Pipelines tab (`src/pipelines.py`)
- Visible to `PIPELINE_GROUPS` members and admins (`show_pipelines=is_pipeline_user() or is_admin()`)
- `is_pipeline_user()` in `src/auth.py` checks `PIPELINE_GROUPS` env var (same pattern as `is_admin()`)
- Admins define pipelines in `_render_admin_pipelines_section()` / `_show_pipeline_create_dialog()`
- Backends: `databricks` (Jobs API 2.1), `adf` (Azure Data Factory management API 2018-06-01), `ado` (Azure DevOps Pipelines API 7.0)
- All backends auth via MSAL client-credentials using `PIPELINE_SP_TENANT_ID` / `PIPELINE_SP_CLIENT_ID` / `PIPELINE_SP_CLIENT_SECRET`
- `trigger_pipeline()` starts a run and persists `backend_run_id` to `user_data.pipeline_runs` (one active run per pipeline)
- `poll_run_status()` calls the backend status API, maps lifecycle state → progress %, returns `{status, progress, message, is_terminal}`; clears the run row when terminal
- `cancel_run()` calls the backend cancel API then clears the run row
- `render_pipelines_page()` auto-polls every 3 s (`time.sleep(3); st.rerun()`) while any run is active
- DB tables: `user_data.pipeline_definitions`, `user_data.pipeline_runs`
- New required env vars: `PIPELINE_GROUPS`, `PIPELINE_SP_TENANT_ID`, `PIPELINE_SP_CLIENT_ID`, `PIPELINE_SP_CLIENT_SECRET`

### Mock auth groups (development)
The "Admin" mock department includes `mock_admin_group`. Set the following in `.env` for full admin + pipeline + editor access in local dev:
```
ADMIN_GROUPS=mock_admin_group
PIPELINE_GROUPS=mock_admin_group
EDITOR_GROUPS=mock_admin_group,finance_group,research_group,hr_group,it_group
```

### Local test dataset
```bash
python scripts/generate_test_data.py          # 800 tables → data/test_data.duckdb
python scripts/generate_test_data.py --with-data  # adds row data for Preview tab
```
Set `DUCKDB_PATH=data/test_data.duckdb` in `.env`, then run without `DEMO_DATA=true`.

### Storage abstraction (`src/storage/`)
- Per-entity Protocol-based backends collapsed the demo / DuckDB branching previously duplicated across cms / pipelines / personalization / audit
- Entities: `CMSStorage`, `PipelineDefStorage` + `PipelineRunStorage`, `PreferenceStorage`, `SiteSettingStorage`, `AuditStorage`, `BusinessNameOverrideStorage`
- Each has Demo (session-state) + DuckDB + Fake (in-memory, test-only) implementations. Direct-Databricks variants were deleted in TODO #7 — Streamlit pods only ever write locally
- Factories live in `src/storage/__init__.py` (`get_<entity>_storage()`) and pick the backend at call time based on `is_demo_mode()` / `_duckdb_available()`
- Tests inject `Fake*Storage` via `mock.patch("src.<module>.get_<entity>_storage")` — no more brittle `_duckdb_available` mocking
- Background: ADR 005

### Entra groups overage (`src/auth_graph.py`)
- Detects ID tokens that lack inline `groups` (Entra omits it for >150-group users) and falls back to `POST /v1.0/me/getMemberObjects {"securityEnabledOnly": true}`
- Process-level cache keyed by user OID, 1 h TTL, lock-protected (chosen over `@st.cache_data` because the latter is per-session)
- Failure modes (Graph 4xx/5xx, network) return empty list — fail-closed, never silently grants access
- `clear_groups_cache(user_oid=None)` flushes one user or all; admin page exposes a "Flush groups cache" button; sign-out clears the user's entry so re-auth picks up new groups
- Background: ADR 006

### Sidecar sync worker (`src/sync/daemon.py`)
- Standalone process: `python -m src.sync.daemon [--once] [--healthz-port N]`
- Drains `user_data.pending_sync` and runs DR resync (pulls new audit / comment / override rows back from Databricks every 20 cycles)
- Stale-row recovery: rows in `'syncing'` for >`SYNC_STALE_ROW_S` (default 300s) flip back to `'pending'` at the top of every cycle
- Status keys written to `user_data.site_settings`: `worker_heartbeat`, `dr_resync_status`. Admin sync panel reads via `src.sync.worker.read_dr_resync_status()` / `read_worker_heartbeat()`
- Tunables: `SYNC_POLL_ACTIVE_S` (5), `SYNC_POLL_IDLE_S` (30), `SYNC_DR_EVERY_N` (20), `SYNC_STALE_ROW_S` (300), `SYNC_HEALTHZ_PORT` (8765), `SYNC_HEALTHZ_TIMEOUT_S` (60)
- Background: ADR 004 + `docs/runbooks/sync-worker.md`

### `src/ui/cards/` package layout
The 1083-line `src/ui/cards.py` was split into 7 submodules (TODO #3):

- `_shared.py`     — `_dq_grade`, `_compute_live_completeness`, `_POST_COLOR`
- `discovery.py`   — `render_discovery`, `render_cms_banner`, `_render_table_card`
- `health.py`      — `render_health` + private helpers
- `pipelines.py`   — `render_pipelines_page` + admin pipeline section
- `admin.py`       — `render_admin_page` + audit/sync/editing sections
- `cms_admin.py`   — `_render_admin_cms_section` + create dialog
- `detail.py`      — `render_table_metadata_editor`, `render_data_sample` (used by search page)

`src/ui/cards/__init__.py` has been deleted — all callers import directly from the specific submodule (e.g. `from src.ui.cards.discovery import render_discovery`).

## Roadmap context
- TODO #1–7 (complete): sidecar sync worker, Entra groups overage, cards.py split, storage abstraction, server-side auth checks on writes, src/sync/push.py unit tests, deletion of the Databricks-direct write path.
- Plus: groups-cache flush tool (admin page), sign-out/sign-in cache invalidation.
- Open follow-ups (see `TODO.md`): reuse `BusinessNameOverrideStorage` from `src/pages/search.py`.
