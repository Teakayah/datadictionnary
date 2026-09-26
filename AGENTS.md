# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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

### CMS discovery banner (`src/cms.py`)
- Admins publish posts that appear as pinned cards above the Discovery sub-tabs
- Post types: `announcement` (red), `featured_table` (blue), `guide` (green)
- Schema: `post_id`, `post_type`, `title`, `body`, `table_ref` (featured_table only), `author_email`, `created_at`, `expires_at`
- Expiry options live in `_EXPIRY_DAYS`: 2 / 7 / 30 days or `None` (never)
- Each function in `src/cms.py` branches on `is_demo_mode()` — demo posts live in session state, otherwise DuckDB
- `render_cms_banner()` in `src/ui/cards/discovery.py` — called from `render_discovery()` between the hero and the sub-tab selector; admin users see a ✕ delete button per card; featured_table cards navigate to the Search tab
- Admin CRUD lives in `_render_admin_cms_section()` / `_show_cms_create_dialog()` in `src/ui/cards/cms_admin.py`
- DB table: `user_data.cms_posts` (created by `_initialize_schema()`)
- Demo-mode fallback: session state key `_demo_cms_posts`
- `create_post` and `delete_post` raise `PermissionError` if the caller is not an admin — defense-in-depth alongside the UI gate

### Pipelines tab (`src/pipelines.py`)
- Disabled by default. Set `ENABLE_PIPELINES=true` to activate (`pipelines_enabled()` in `src/config.py`).
- When enabled, visible to `PIPELINE_GROUPS` members and admins (`show_pipelines=pipelines_enabled() and (is_pipeline_user() or is_admin())`)
- `is_pipeline_user()` in `src/auth.py` checks `PIPELINE_GROUPS` env var (same pattern as `is_admin()`); short-circuits to `False` when the feature is off
- Admins define pipelines in `_render_admin_pipelines_section()` / `_show_pipeline_create_dialog()`
- Backends: `databricks` (Jobs API 2.1), `adf` (Azure Data Factory management API 2018-06-01), `ado` (Azure DevOps Pipelines API 7.0)
- All backends auth via MSAL client-credentials using `PIPELINE_SP_TENANT_ID` / `PIPELINE_SP_CLIENT_ID` / `PIPELINE_SP_CLIENT_SECRET`
- `trigger_pipeline()` starts a run and persists `backend_run_id` to `user_data.pipeline_runs` (one active run per pipeline)
- `poll_run_status()` calls the backend status API, maps lifecycle state → progress %, returns `{status, progress, message, is_terminal}`; clears the run row when terminal
- `cancel_run()` calls the backend cancel API then clears the run row
- `render_pipelines_page()` auto-polls every 3 s (`time.sleep(3); st.rerun()`) while any run is active
- DB tables: `user_data.pipeline_definitions`, `user_data.pipeline_runs`
- Env vars (only needed when `ENABLE_PIPELINES=true`): `PIPELINE_GROUPS`, `PIPELINE_SP_TENANT_ID`, `PIPELINE_SP_CLIENT_ID`, `PIPELINE_SP_CLIENT_SECRET`

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

### Storage pattern (inline `is_demo_mode()` branching)
- The Protocol-based `src/storage/` layer (ADR 005) was collapsed in the 2026-06 over-engineering audit (TODO OE-1) — the abstraction tripled the code per entity
- Each data-layer module branches inline: demo mode reads/writes `st.session_state`, otherwise DuckDB (`user_data.*` tables)
- Modules: `src/cms.py`, `src/pipelines.py`, `src/personalization.py`, `src/audit.py` (incl. column + table business-name overrides), `src/notifications.py`, `src/analytics.py`
- Direct-Databricks write variants were deleted in TODO #7 — Streamlit pods only ever write locally; the sidecar daemon is the sole Databricks writer
- Tests patch `is_demo_mode` (e.g. `mock.patch("src.cms.is_demo_mode", return_value=True)`) and seed/assert the session-state keys directly

### Entra groups overage (`src/auth_graph.py`)
- Detects ID tokens that lack inline `groups` (Entra omits it for >150-group users) and falls back to `POST /v1.0/me/getMemberObjects {"securityEnabledOnly": true}`
- Process-level cache keyed by user OID, 1 h TTL, lock-protected (chosen over `@st.cache_data` because the latter is per-session)
- Failure modes (Graph 4xx/5xx, network) return empty list — fail-closed, never silently grants access
- `clear_groups_cache(user_oid=None)` flushes one user or all; admin page exposes a "Flush groups cache" button; sign-out clears the user's entry so re-auth picks up new groups
- Background: ADR 006

### Hybrid semantic search (`src/semantic.py`)
- Controlled by `ENABLE_SEMANTIC_SEARCH=true` (defaults off; existing BM25 search path unchanged when off)
- `EmbeddingEngine` Protocol — `embed_text(text) -> List[float]`, `embed_batch(texts) -> List[List[float]]`
- `DatabricksEmbeddingEngine` — calls Databricks Model Serving endpoint named by `DATABRICKS_EMBEDDING_ENDPOINT`; falls back to zero-vectors on error so a failing endpoint never breaks the nightly sync
- `MockEmbeddingEngine` — deterministic 384-dim vectors from character ordinals; used when `DATABRICKS_EMBEDDING_ENDPOINT` is unset
- `get_embedding_engine()` — factory: returns `DatabricksEmbeddingEngine` if endpoint configured, else `MockEmbeddingEngine`
- `generate_table_embeddings(tables)` — called by `scripts/sync_metadata.py` during the nightly crawl to populate `tables_embedding_cache`
- `semantic_search(query, top_n=10)` — embeds the query, runs cosine similarity via DuckDB VSS extension, returns a list of `table_full_name` strings; called from `src/db/queries.py::search_all_metadata` for hybrid fusion with BM25 results
- Fusion: weighted sum of the normalized keyword score (0.7) and a rank-decayed semantic score (0.3); semantic hits missing from keyword results are fetched permission-filtered and appended
- Requires DuckDB VSS extension (`INSTALL vss; LOAD vss`) — loaded automatically when semantic search is enabled

### Comments and discussions (`src/comments.py`)
- `get_table_comments(object_name)` — returns a tree of comment dicts with nested `replies`; reads from `user_data.comments` (DuckDB) or `st.session_state["demo_comments"]` (demo mode)
- `save_comment(object_name, author_name, author_email, text, steward_email, parent_comment_id=None)` — writes to DuckDB and enqueues a `COMMENT` sync row via `src/sync/push.enqueue_sync`
- Comment tree is built by `_build_comment_tree(flat)` — groups a flat list by `parent_comment_id`
- DB table: `user_data.comments` (created by `_initialize_schema()`)
- `src/comments.py` uses the same inline demo/DuckDB routing pattern as the other data-layer modules

### Sidecar sync worker (`src/sync/daemon.py`)
- Standalone process: `python -m src.sync.daemon [--once] [--healthz-port N]`
- Drains `user_data.pending_sync` and runs DR resync (pulls new audit / comment / override rows back from Databricks every 20 cycles)
- Stale-row recovery: rows in `'syncing'` for >`STALE_ROW_TIMEOUT_S` (300s, module constant) flip back to `'pending'` at the top of every cycle
- Status keys written to `user_data.site_settings`: `worker_heartbeat`, `dr_resync_status`. Admin sync panel reads via `src.sync.worker.read_dr_resync_status()` / `read_worker_heartbeat()`
- Timing values (poll intervals, DR cadence, stale-row + heartbeat timeouts) are module constants in `src/sync/daemon.py`; the only env tunable is `SYNC_HEALTHZ_PORT` (8765)
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
- All major follow-ups complete. Open UI items tracked in `TODO.md` (help-tooltip bilingualism, pipelines/admin nav visibility, segmented-control visual alignment).
