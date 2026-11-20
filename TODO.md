# Engineering TODO

Living backlog from the senior-developer audit (2026-05-07). Each item is
self-contained — pick any one and ask Claude to implement it.

Status legend: `[ ]` open · `[~]` in progress · `[x]` done

---

## Next steps (open)

### Before live Entra ID + Unity Catalog production

- [ ] **Make mutable storage safe before enabling HA replicas (also fixes DuckDB single-writer lock contention).**
  The retained HA proposal scales Streamlit over shared writable DuckDB files, and `dd-app`
  ([`src/db/duckdb_adapter.py`](src/db/duckdb_adapter.py)) plus `dd-sync-worker`
  ([`src/sync/daemon_db.py`](src/sync/daemon_db.py)) both currently hold long-lived read-write
  DuckDB connections to `user_data` on the shared RWX PVC. Move mutable `user_data` to a
  multi-process-safe store (for example PostgreSQL), migrate all affected writes and the sync
  worker, and test concurrent writes, failure recovery, and rollout before scaling `dd-app`
  beyond 1 replica. Do not merge the HA proposal as-is; read-only mode alone would disable
  existing writes.

- [ ] **Partition MSAL token cache per session (`src/auth.py`).**
  `get_msal_app()` caches a single `ConfidentialClientApplication` (with an in-memory shared
  token cache) via `@st.cache_resource`, and `_try_silent_refresh()` falls back to
  `msal_app.get_accounts()[0]` when `user_email` is empty while skipping group re-resolution.
  Store a per-session `msal.SerializableTokenCache` in `st.session_state`, look up accounts
  strictly by `home_account_id` / `oid` (no `accounts[0]` fallback), and re-resolve user
  groups on silent refresh.

- [ ] **Reconcile Entra Group OIDs with Unity Catalog grants and inherited privileges (`scripts/sync_metadata.py`).**
  `permissions_cache` currently ingests raw `grantee` strings from
  `system.information_schema.table_privileges` (display names/emails, direct table grants only),
  while Entra ID claims and Graph `getMemberObjects` return Group Object IDs (GUIDs). Map
  Entra Group OIDs to Unity Catalog principals during sync, union inherited
  `catalog_privileges` and `schema_privileges` with `table_privileges`, and map Databricks
  `account users` to `SELECT_ALL_USERS`.

- [ ] **Harden Data Preview against privilege & row-filter/column-mask bypass (`src/ui/cards/detail.py`).**
  `render_data_sample()` runs `SELECT * LIMIT 100` using the shared `DATABRICKS_TOKEN` PAT
  after checking only cached membership in `permissions_cache` (without checking
  `privilege = 'SELECT'`, risking metadata-only `BROWSE` escalation and bypassing Unity Catalog
  row filters / column masks). Execute preview using the caller's OBO Databricks token, or gate
  preview behind an explicit `ENABLE_DATA_PREVIEW` flag restricted to `SELECT` grants on
  unmasked/unfiltered tables.

- [ ] **Fix live API/MCP Entra groups overage and JWKS rotation (`src/api/auth.py`).**
  `_fetch_groups_graph()` currently sends the API-audience JWT directly to
  `graph.microsoft.com/v1.0/me/getMemberObjects` (Entra rejects wrong-audience tokens),
  does not follow `@odata.nextLink` pagination, and caches failed `[]` responses in Redis for
  1 hour. Switch Graph lookup to On-Behalf-Of (OBO) or app-only client credentials, add
  pagination matching `src/auth_graph.py`, never cache transient errors in Redis, and force a
  `_get_jwks()` refresh when a token `kid` is missing from cached keys.

### Security hardening before ITSG-33 / production sign-off

- [ ] **Tighten API CORS and Redis transport/auth defaults.**
  Replace the `ALLOWED_ORIGINS = ["*"]` fallback in [`src/api/main.py`](src/api/main.py)
  with explicit environment origins (already set in `values-prod.yaml`), and configure Redis
  with authentication (`--requirepass` / Secret) and TLS in Kubernetes/Helm.

- [ ] **Enforce permission filtering on downstream lineage counts and write-path target tables.**
  `get_multi_hop_lineage()` ([`src/db/queries.py`](src/db/queries.py)) called by
  [`src/pages/search.py`](src/pages/search.py) omits the `permissions_cache` join (disclosing
  counts/certified flags of unauthorized downstream tables), and `save_table_metadata()`
  ([`src/audit.py`](src/audit.py)) checks `is_power_user()` globally without checking access to
  `table_full_name`. Add group filtering to `get_multi_hop_lineage()` and verify table-level
  authorization on writes.

- [ ] **Harden Graph pagination, pipeline URL parameters, and API override table routing.**
  Validate `next_url.startswith("https://graph.microsoft.com/")` before sending the Bearer
  token in [`src/auth_graph.py`](src/auth_graph.py); URL-encode/validate ADF & ADO path
  segments in [`src/pipelines.py`](src/pipelines.py); and replace hardcoded
  `user_data.business_name_overrides` in [`src/api/queries.py`](src/api/queries.py)
  (`get_table_details`) with `_overrides_tables()`.

- [ ] **Normalize Redis cache keys and invalidate API/MCP cache on metadata writes.**
  Sort `user.groups` before hashing cache keys in [`src/mcp_server/server.py`](src/mcp_server/server.py)
  and API routers so group ordering differences don't fragment the cache, and invalidate/bump
  cache namespaces when Streamlit edits are approved or saved.

- [ ] **Promote CI `pip-audit` to blocking and deploy via Helm.**
  Set `continue-on-error: false` on `dependency-audit` in [`.github/workflows/ci.yml`](.github/workflows/ci.yml),
  and update [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) /
  [`azure-pipelines.yml`](azure-pipelines.yml) to deploy `charts/data-dictionary/` with
  externally managed Secrets instead of applying placeholder `k8s/secret.yaml`.

### Remaining UX & product enhancements

- [ ] **Shareable deep-link URLs (`?tab=search&table=...`).**
  Persist the selected `full_name` in `st.query_params` in [`src/pages/search.py`](src/pages/search.py)
  so table detail views survive refreshes and can be shared with colleagues.

- [ ] **Unify metadata + friendly-name editing and surface field-level validation errors.**
  Consolidate *Edit table* and *Edit friendly name* into a single clear editorial workflow,
  pass the unescaped `steward_email` rather than HTML-escaped `_steward` into
  `render_table_metadata_editor()` ([`src/pages/search.py`](src/pages/search.py#L197)), and
  render actionable validation errors in [`src/ui/cards/detail.py`](src/ui/cards/detail.py).

- [ ] **Back business glossary search with a real UC/DuckDB table.**
  Replace `_DEMO_GLOSSARY` dependency in [`src/db/queries.py`](src/db/queries.py) with a
  synced glossary table (or UC tags/table) so glossary search works in non-demo environments.

- [ ] **Search pagination and catalog/schema/DQ facet filters.**
  Replace the hard `50`-row cap in [`src/pages/search.py`](src/pages/search.py) with pagination
  plus catalog, schema, and completeness-grade facets.

- [ ] **UI polish & air-gapped font hosting.**
  Clean up per-rerun `MutationObserver` registration in [`src/ui/header.py`](src/ui/header.py),
  render `f"{CATALOG_CACHE}.{SCHEMA_CACHE}"` dynamically in the footer, remove remaining UI
  emojis in [`src/pages/catalog.py`](src/pages/catalog.py), [`src/pages/search.py`](src/pages/search.py),
  [`src/ui/cards/discovery.py`](src/ui/cards/discovery.py), and [`src/ui/cards/detail.py`](src/ui/cards/detail.py),
  and vendor fonts locally for air-gapped networks.

### Completed items

- [x] **Docs bundle rebuild**: `docs/data-dictionary-docs.html` (SPA bundle) and `docs/data-dictionary-docs.pdf` are rebuilt (commit 2c36fb9).
- [x] **Semantic search production hardening**: Wired `DATABRICKS_EMBEDDING_ENDPOINT`, added `ENABLE_SEMANTIC_SEARCH` env gate, and validated DuckDB VSS (commit 564614d).
- [x] **Search analytics alerts**: Enqueued a Health-dashboard notification for zero-result queries that persist for > 7 days (Localized in commit fb38cf8).
- [x] **Review**: Perform a detailed technical and editorial review of the [Recommendation Engine](docs/feature-recommendation-engine.html) documentation and implementation.
- [x] **Deployment**: Deploy the updated Kubernetes manifests to apply new security labels and hardened configurations. (Automated via CI/CD on push to main)

---

## Recent fixes (2026-05-20)

- [x] **Circular import** (`src/db/queries.py` ↔ `src/semantic.py`): Phase 2 scaffold added a module-level `from src.semantic import semantic_search` in `queries.py` while `semantic.py` already imported `run_query` from `queries.py`. Broke import collection for 10 test files. Fixed by making the import lazy (inside `search_all_metadata`).
- [x] **Analytics storage crash on admin page**: `get_analytics_storage()` was missing the `_duckdb_available()` guard present on all other storage factories — called `DuckDBAnalyticsStorage` with an empty `USER_DATA_PATH` in test/demo environments. Fixed by adding `or not _duckdb_available()` to the factory condition.
- [x] **Test count drift** (`test_sync_metadata`): Phase 2 added `tables_embedding_cache` (1 new TRUNCATE, 1 new `executemany` from `MockEmbeddingEngine`). Updated execute count 10→11, executemany count 5→6, setup_cache_tables DDL count 11→12.
- [x] **Mermaid diagrams overwritten**: The Phase 2 scaffold commit (`67ee293`) overwrote `docs/architecture.html` and `docs/runbook-sync-worker.html`, stripping the rendered system-architecture, daemon-cycle flowchart, and pod-topology diagrams. Restored from commit `afd0f5a`.
- [x] **Discovery tab locale reset**: Switching EN↔FR was silently resetting the active Discovery sub-tab to "New & Notable" because `discovery_active_tab` stored a translated label string that no longer matched after locale change. Fixed by remapping via the locale-independent `_disc_tab_idx` index.

---

## Quick wins (done)

- [x] Replace deprecated `datetime.utcnow()` → `datetime.now(UTC)` (commit bc4df2c)
- [x] Pin runtime deps and declare `requests` (commit bc4df2c)
- [x] Refuse to start with `ENABLE_MOCK_AUTH=true` outside `ENVIRONMENT=development` (commit bc4df2c)
- [x] Split `MAX_BUSINESS_NAME_LEN` (255) and `MAX_DEFINITION_LEN` (2000) (commit bc4df2c)
- [x] Stop re-firing the viewport-height JS call after first capture (commit bc4df2c)
- [x] Whitelist identifiers + email-validate steward in `src/sync/push.py` (commit bc4df2c)

---

## Phase 2: Advanced Features & Automation

### E1. Hybrid Semantic Search
- [x] **Embedding Engine**: Implement a real embedding backend (using Databricks Model Serving).
- [x] **Indexing**: Update `scripts/sync_metadata.py` to calculate embeddings during nightly crawl.
- [x] **VSS Search**: Implement `semantic_search` logic in `src/semantic.py`.
- [x] **Hybrid Fusion**: Update `src/db/queries.py` to a hybrid execution structure.

### E2. Documentation Automation
- [x] **CI Enforcement**: Finalize CI step to ensure `md_to_html.py` has been run.
- [x] **Incremental Updates**: MD5-based incremental updates in `md_to_html.py`.

### E3. Search Analytics & Gap Analysis
- [x] **Admin Dashboard Integration**: Real-time "Search Gaps" table in the Admin Insights tab.
- [x] **Automated Alerts**: Enqueue a notification in the Health dashboard for persistent gaps.
- [ ] **Email Digest (Optional)**: Weekly summary to stewards of the most common unresolved searches.

---

## Bigger investments (open)

### 1. Sidecar sync worker — kills DuckDB shared-connection concurrency bugs

**Status:** done (branch `feat/sidecar-sync-worker`).

- `src/sync/daemon.py` runs standalone (`python -m src.sync.daemon`) with
  `--once`, `--healthz-port`, `--log-level` flags.
- `src/sync/daemon_db.py::DaemonConn` opens a process-local DuckDB
  connection. The shared `@st.cache_resource` singleton is no longer used
  outside Streamlit.
- DR resync extracted into `src/sync/dr_resync.run_dr_resync(conn,
  status_setter)` so it can be unit-tested with a fake conn and a patched
  `_databricks_query`.
- Stale-row recovery: rows in `'syncing'` for >`SYNC_STALE_ROW_S` (default
  300s) are flipped back to `'pending'` at the top of every cycle.
- `/healthz` HTTP listener (default port 8765) returns 200 if a heartbeat
  was written within `SYNC_HEALTHZ_TIMEOUT_S`, else 503.
- New `k8s/deployment-sync-worker.yaml` (`replicas: 1`, `Recreate` strategy)
  shares the `dd-data` PVC with `dd-app`.
- `Dockerfile` now copies `src/` (was missing — separate latent bug fixed
  inline) and exposes 8765.
- `_start_sync_worker_thread` and the duplicate state in `src/ui/cards.py`
  are gone; the admin sync panel reads status via
  `src.sync.worker.read_dr_resync_status()`.
- `tests/test_sync_daemon.py` adds 18 tests covering DaemonConn, status
  upsert, stale-row recovery, healthz 200/503, DR resync (skip / pull /
  error), injected-conn drain, single-cycle integration.
- Schema fix: `user_data.pending_sync.last_attempt_at` was referenced in
  push.py but never created — `_initialize_schema` now declares it AND
  runs `ALTER TABLE … ADD COLUMN IF NOT EXISTS` for migration.

### 2. Entra ID groups overage handling

**Status:** done (branch `feat/entra-groups-overage`).

- `src/auth_graph.py` — `has_groups_overage(claims)` and
  `fetch_member_groups(access_token, user_oid)` calling
  `POST /v1.0/me/getMemberObjects {"securityEnabledOnly": true}`. Follows
  `@odata.nextLink` pagination, capped at 50 pages.
- Process-level cache keyed on user OID, 1h TTL, lock-protected. Chosen
  over `@st.cache_data` because the latter is session-scoped (one Graph
  call per browser tab).
- `src/auth.py::_resolve_user_groups` is the single decision point: inline
  groups → use them; overage → fetch via Graph; neither → `[]` (logged
  INFO so a tenant misconfig is visible).
- Failure mode: any error (5xx, 403, network) returns `[]` and logs a
  WARNING. Fail-closed — never silently grants wider access.
- `src/config.py::SCOPE` documented inline so future readers know
  `User.Read` is load-bearing.
- `tests/test_auth_graph.py` — 19 tests covering overage detection,
  pagination, 5xx / 403 / network errors, cache hit/miss, empty-OID path,
  and the three branches of `_resolve_user_groups`.

**Out of scope (still open):** ~~SSO logout / silent re-auth on group
membership change.~~ Done — see follow-up below.

**Follow-up: group-cache refresh tool** (done):
- ``src.auth_graph.clear_groups_cache(user_oid=None)`` — drops one or
  every cached entry.
- ``src.auth._clear_auth_session`` clears the user's cache entry, so
  signing out then back in actually picks up new Entra group changes
  (was previously stale for up to 1h).
- ``check_auth`` busts the cache for the new user_oid on every fresh
  OIDC code-exchange before resolving groups.
- Admin page has a "§ Group permissions cache → Flush groups cache"
  section (locale strings: ``admin.groups_cache_*``). Flushes
  process-wide; every active user re-fetches on their next render.

### 3. Split `src/ui/cards.py` (was 1,083 lines)

**Status:** done (branch `feat/cards-split`).

Final layout, all files <400 lines. New code should import from the specific submodule (e.g. `from src.ui.cards.discovery import render_discovery`).

**Out of scope (deferred):** DONE. All callers (``app.py``, ``src/pages/catalog.py``, ``src/pages/search.py``, ``tests/test_admin.py``) migrated to direct submodule imports and the compatibility shim was removed (commit 6565a44).

### 4. Storage abstraction — collapse demo / DuckDB / Databricks branching

**Status:** done.

- Per-entity storage backends live under `src/storage/` and collapse the
  demo / DuckDB branching that used to be duplicated across `cms.py`,
  `pipelines.py`, `personalization.py`, and `audit.py`.
- `table_metadata_overrides` integrated into core search and catalog
  queries in `src/db/queries.py`, providing immediate feedback for
  user-authored descriptions and steward updates.
- `src/pages/search.py` migrated to `BusinessNameOverrideStorage`.

Layout:
```
src/storage/
  __init__.py             factories: get_<entity>_storage()
  cms_storage.py          CMSStorage + 3 concretes (Demo / DuckDB / Fake)
  pipeline_storage.py     PipelineDefStorage + PipelineRunStorage
                          (each with 3 concretes)
  preference_storage.py   PreferenceStorage + SiteSettingStorage
                          (each with 3 concretes)
  audit_storage.py        AuditStorage + BusinessNameOverrideStorage
                          (each with 4 concretes — adds Databricks fallback)
```

Each entity migrated as its own commit, tests stayed green throughout.
Protocol-based design lets test code inject `Fake*Storage` without
inheriting; existing callers unchanged.

---

## Smaller follow-ups (open)

### 5. Defense-in-depth: server-side auth checks on write paths

**Status:** done (branch `feat/auth-checks-and-push-tests`).

- `src/cms.py`            — `create_post`, `delete_post`                 (admin)
- `src/pipelines.py`      — `create_pipeline_def`, `delete_pipeline_def` (admin)
                           — `trigger_pipeline`, `cancel_run`            (pipeline user or admin)
- `src/personalization.py` — `set_editing_enabled`                       (admin)

Each function now raises `PermissionError` at its boundary if the caller
fails the check. Tests verify both: existing call sites set up admin /
pipeline-user context via `patch("src.X.is_admin")`; new rejection-path
tests assert that the underlying storage / backend was never touched
when the check fails.

### 6. Unit tests for `src/sync/push.py`

**Status:** done (branch `feat/auth-checks-and-push-tests`).

`tests/test_sync_push.py` (33 tests):

- **Identifier whitelist** (`_safe_ident`): accepts `[A-Za-z0-9_]+`,
  rejects backticks, dots, semicolons, hyphens, spaces, non-ASCII,
  empty / whitespace-only.
- **3-part name parser** (`_split_full_name`): accepts exactly
  `cat.sch.tbl`, rejects 1 / 2 / 4 / empty parts.
- **Per-sync-type dispatch**: COLUMN_DEF (ALTER COLUMN COMMENT),
  TABLE_DESC (COMMENT ON TABLE), STEWARD (SET TAGS), AUDIT, COMMENT.
- **STEWARD** rejects non-email values (`ValueError`).
- **Unknown sync_type** logs a warning and does not call
  `cursor.execute`. Required adding an explicit `else:` branch in
  `_push_to_databricks` — previously unknown types fell through silently
  and the queue marked rows `done`.
- **Missing credentials** raise `RuntimeError` before any HTTP attempt.

Tests run against the conftest's `databricks.sql` MagicMock via a small
local helper that walks the `with`-block chain
(``connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value``)
since the conftest's `get_db_cursor()` is wired for the read-query path.

### 7. Connection pooling for Databricks writes

**Status:** done by removing the path entirely. After #1 (sidecar
daemon) the only intentional Databricks writer is the daemon, which
opens its own ``dbsql.connect`` per cycle. The Streamlit-pod fallback
(``_get_databricks_write_connection`` + ``Databricks*Storage`` classes)
was dead code and was deleted along with the 3 tests that asserted on
its MERGE INTO syntax.

If daemon-side per-cycle reconnection becomes a hotspot, pool there.
That's a separate, smaller change.

- [x] **Drop `GroupMember.Read.All` scope**: Audit confirmed `User.Read` is sufficient for the overage path. Scope removed from `src/config.py` and documented in ADR 006 (commit cb4873e).

---

## Possible explorations (not yet scoped)

### E1. Semantic / hybrid search

**Motivation:** Full-text search fails when business terminology diverges from technical column
names (e.g. searching "revenue" doesn't surface `fct_gross_sales_v2`). Both Gemini and Ollama
independently identified this as the highest-recall enhancement for non-technical users.

**Proposed approach:**
- During nightly sync (`scripts/sync_metadata.py`), generate embeddings for table/column
  descriptions using the Databricks Foundation Models API (`databricks-embeddings-v2`) or
  locally via `all-MiniLM-L6-v2` (sentence-transformers).
- Store vectors in a new `tables_embedding_cache(table_full_name, embedding FLOAT[])` table in
  the catalog DuckDB file using the `vss` extension (`INSTALL vss; LOAD vss`).
- In `src/db/queries.py::search_all_metadata`, run hybrid search: BM25 (current) +
  cosine similarity via `array_cosine_similarity`. Combine scores with a weighted sum.
- Add a `_to_duckdb_sql` translation for the `array_cosine_similarity` call.
- The query-time embedding call (`embed(user_query)`) needs to be fast — consider caching
  the query embedding in `st.session_state` per unique query string.

**Prerequisites / risks:**
- DuckDB `vss` extension is in beta; test against the pinned DuckDB version before committing.
- Embedding generation adds ~5–30 min to the nightly sync depending on table count and model.
- Foundation Models API requires a PAT with `CAN_USE` on a serving endpoint — add to `.env`.
- The 384-dim MiniLM vectors add ~1.5 MB per 1000 tables; acceptable at 800-table scale.

**Acceptance (when this is picked up):**
- [ ] `scripts/sync_metadata.py` generates and stores embeddings; controllable via
      `ENABLE_SEMANTIC_SEARCH=true` env flag.
- [ ] Hybrid search ranks "revenue" above non-matching tables when `fct_gross_sales` has
      "gross revenue" in its description.
- [ ] Search p95 latency stays under 200 ms with vectors enabled (load-test at 300 users).
- [ ] `ENABLE_SEMANTIC_SEARCH` defaults to `false`; existing search path unchanged when off.

---

## Friendly table names (2026-05-29)

Integrate `governance.dictionary.business_names` (bilingual friendly names +
definitions) into the dictionary. UC table is the source of truth; the app
reads on every sync and writes approved edits back via the sidecar.

Configurable via `.env` (table name **and** column names — the source table
will move/rename in the future):

```
BUSINESS_NAMES_TABLE=governance.dictionary.business_names
BUSINESS_NAMES_COL_FULL_NAME=full_name
BUSINESS_NAMES_COL_NAME_EN=friendly_name_eng
BUSINESS_NAMES_COL_NAME_FR=friendly_name_fr
BUSINESS_NAMES_COL_DEF_EN=field_definition_eng
BUSINESS_NAMES_COL_DEF_FR=field_definition_fr
```

- [x] **Env config**: add the six vars above to `.env` / `.env.example` and
      expose them as constants in `src/config.py`.
- [x] **Cache schema**: add `business_name_en`, `business_name_fr`,
      `business_definition_en`, `business_definition_fr` (nullable TEXT) to
      `data_governance.dictionary_cache.tables_metadata`.
      `setup_cache_tables()` adds `ADD COLUMN IF NOT EXISTS` migration.
- [x] **Sync ingest**: in `scripts/sync_metadata.py`, step 2b-bis reads the
      configured UC table and enriches `tables_data` rows on `full_name`.
      Guard against the source table being missing.
- [x] **Locale-aware SELECT helper**: `business_name_expr()` /
      `business_definition_expr()` in `src/db/queries.py` yield
      `COALESCE(business_name_<locale>, table_name)` for the active locale.
- [x] **Search match**: WHERE clause LIKE-matches all four bilingual columns;
      `COALESCE` ensures the friendly name is used as the display name.
- [x] **Table-pane H1**: friendly name renders as H1 with `full_name` as
      mono sub-line; definition shown above technical description.
      Falls back to `full_name` when null.
- [x] **Result cards**: friendly name surfaced on search-result cards;
      technical `full_name` stays the nav key.
- [x] **Edit + admin approval** (two-stage gate):
      - **Propose** — `is_power_user()` gate; non-admins land as
        `pending_approval`.
      - **Approve / reject** — `is_admin()` gate; approval enqueues sidecar
        write-back; rejection discards the override.
      - `save_table_business_name` / `approve_table_business_name` /
        `reject_table_business_name` in `src/audit.py`; admin queue in
        `src/ui/cards/admin.py`; edit dialog in `src/ui/cards/detail.py`.
- [x] **Sidecar write-back**: `TABLE_BUSINESS_NAME` action in
      `src/sync/push.py` runs MERGE INTO the configured UC table using
      env-validated identifiers. Idempotent.
- [x] **Tests**: `tests/test_table_friendly_names.py` — 37 tests covering
      locale helpers, sync JOIN (matched / unmatched / partial / empty
      reference), bilingual WHERE clause, queue action shape, and
      approve/reject lifecycle via `FakeTableBusinessNameOverrideStorage`.
      `src/demo/data.py` `_DEMO_TABLES` gains bilingual columns so
      `DEMO_DATA=true` exercises the friendly-name display path.

**Invariant:** `full_name` stays the only stable identifier. Bookmarks,
permissions, lineage, and audit references never use the friendly name.

---

## Load test follow-ups (2026-06-03)

- [x] **`DuckDBQueryUser` never runs real queries.** `_open_con()` returns `None`
      for all users because `SET search_path = 'dictionary_cache'` fails on a
      direct DuckDB connection — that schema only exists when the file is
      `ATTACH`ed under that name. Fixed: open the working copy as `:memory:` + `ATTACH`
      (matching the main app's connection pattern in `duckdb_adapter.py`) and set
      `USE data_governance.dictionary_cache` on thread cursors so queries resolve.


---

## UI follow-ups (2026-05-29)

- [x] **Discovery tab help tooltip is not bilingual.** `help.discovery_content`
      translated into French in commit b514823; both `locale/en.json` and
      `locale/fr.json` now carry the key. Code already uses `t(...)`.
- [x] **Pipelines and Admin tabs are visible to all users in the top nav.**
      `render_header()` in `src/ui/header.py` already gates both the HTML
      `<a>` links (lines 55–56) and the proxy `st.button` elements (lines
      90–93) on `show_admin` / `show_pipelines`. Confirmed correct.
- [x] **Admin tab crashes** with
      `AttributeError: '_DuckDBConn' object has no attribute 'fetchall_as_pandas'`
      at `src/storage/analytics_storage.py:62`. Fixed: added None guard to
      `_DuckDBCursor.execute()` and routed analytics storage via
      `conn.execute(...).fetchall_as_pandas()` with `conn.open` guard (commit 85b3679).
- [x] **Pipelines and Admin pages are missing the help-tooltip pattern**
      Discovery uses on its controls. Pipelines page has
      `with st.expander(t("help.pipelines_expander"))` (commit b514823);
      admin has per-sub-tab expanders at `help.admin_*_expander` keys.
- [x] **Segmented-control pills elsewhere don't match Discovery's sub-tab
      visual language.** Admin page switched from `st.tabs` to
      `st.segmented_control` in commit b514823; CSS in `assets/design.css`
      applies the pill theme uniformly via `[data-testid="stButtonGroup"]`.

---

## Architecture simplification (over-engineering audit, 2026-06-09)

Six items from a full-codebase complexity audit. Each addresses a pattern
where the implementation cost exceeds the problem being solved. Items are
ordered by impact; OE-6 depends on OE-1.

---

### OE-1. Collapse the storage abstraction layer

- [x] **Collapse storage abstraction** — done. `src/storage/` deleted (1,769 lines); demo/DuckDB branching inlined into `src/cms.py`, `src/pipelines.py`, `src/personalization.py`, `src/audit.py`, `src/notifications.py`, and new `src/analytics.py`. Tests patch `is_demo_mode()` and assert against session state; all `Fake*Storage` classes removed.

  **What to do:**
  - Delete `src/storage/cms_storage.py`, `pipeline_storage.py`, `preference_storage.py`, `audit_storage.py`, `analytics_storage.py`, `notification_storage.py`
  - Simplify `src/storage/__init__.py`: replace the 9 factory functions with the 2 helper lines they delegate to (`_use_demo_backend()`, `_duckdb_available()`), or remove the file entirely and inline the branching in each caller
  - In each caller (`src/cms.py`, `src/pipelines.py`, `src/personalization.py`, `src/audit.py`), replace `get_<entity>_storage()` calls with direct conditional logic:
    ```python
    if is_demo_mode():
        # read/write st.session_state
    else:
        # run DuckDB query
    ```
  - In tests, patch `is_demo_mode()` (or `src.cms.is_demo_mode`) instead of patching `get_cms_storage`. Update all 6 `test_storage_*.py` files accordingly (or defer to OE-6)
  - Delete the 8 `Fake*Storage` classes; tests that use them should instead call the real demo-mode path with `DEMO_DATA=true` or mock `is_demo_mode` directly

  **Why this is safe:** The Protocol-based design was introduced to avoid brittle `_duckdb_available` mocking in tests (ADR 005). That problem is real, but the cure tripled the code per entity. Patching `is_demo_mode()` achieves the same test-isolation goal with no new abstraction.

  **Acceptance:**
  - `src/storage/` is empty or deleted; `src/storage/__init__.py` may remain as a thin compatibility shim during migration but should ultimately disappear
  - `grep -r "Protocol" src/storage/` returns nothing
  - `grep -r "Fake.*Storage" src/ tests/` returns nothing (or only test helpers, not production imports)
  - `python -m pytest tests/ -q --ignore=tests/test_load_smoke.py --ignore=tests/test_wcag_axe.py --ignore=tests/test_nav_render.py` passes green

---

### OE-2. Complete or remove the hybrid semantic search scaffold

- [x] **Resolve semantic search dead code** — finished (Option A): weighted fusion (0.7 keyword / 0.3 semantic) implemented in `search_all_metadata`; semantic-only hits are fetched permission-filtered and appended; tests in `tests/test_semantic.py` assert semantic results change ranking

  **Current state:** `src/db/queries.py::search_all_metadata` (around line 290) ends with:
  ```python
  # For now, we just ensure semantic results are present in the list
  # Future: Implement proper RRF (Reciprocal Rank Fusion)
  return keyword_results
  ```
  `ENABLE_SEMANTIC_SEARCH=true` is wired but the hybrid step always returns the keyword-only results unchanged.

  **What to do — choose one:**

  *Option A — Finish it:* Implement real RRF in `search_all_metadata`. Embed the user query via `get_embedding_engine().embed_text(query)`, run `array_cosine_similarity` against `tables_embedding_cache`, merge with BM25 scores using a weighted sum (start 0.7 BM25 / 0.3 semantic), sort by combined score. Remove the `# Future` comment. Add a test asserting that semantic results influence ranking.

  *Option B — Remove it:* Delete `src/semantic.py`. Remove the `semantic_fns` block and lazy import from `search_all_metadata` in `src/db/queries.py`. Remove `ENABLE_SEMANTIC_SEARCH` from `src/config.py`, `.env.example`, and `k8s/deployment.yaml`. Remove embedding generation from `scripts/nightly_sync.py`. Move to a `feat/semantic-search` branch for future pickup.

  **Acceptance (either option):**
  - No `# Future: Implement proper RRF` comment exists in `main`
  - With Option A: `ENABLE_SEMANTIC_SEARCH=true` causes `search_all_metadata` to return a different-ordered result set than BM25 alone (verifiable with a test using `MockEmbeddingEngine`)
  - With Option B: `grep -r "semantic" src/ scripts/` returns nothing; `ENABLE_SEMANTIC_SEARCH` is gone from all config/env files
  - All tests pass

---

### OE-3. Gate the pipelines feature behind an explicit env flag

- [x] **Make pipelines opt-in** — done. `pipelines_enabled()` in `src/config.py` (reads `ENABLE_PIPELINES`, default false, at call time so tests can monkeypatch); gates `show_pipelines` in `app.py`, `is_pipeline_user()` in `src/auth.py`, and `render_pipelines_page()`. `PIPELINE_*` vars moved to a commented-out optional section in `.env.example`; `networkpolicy-api.yaml` kept (it serves the REST API pod, not pipeline egress).

  **What to do:**
  - Add `ENABLE_PIPELINES: bool = os.getenv("ENABLE_PIPELINES", "false").lower() == "true"` to `src/config.py`
  - In `app.py`, change the `show_pipelines` check from `is_pipeline_user() or is_admin()` to `ENABLE_PIPELINES and (is_pipeline_user() or is_admin())`
  - In `src/auth.py::is_pipeline_user()`, short-circuit: `if not ENABLE_PIPELINES: return False`
  - In `.env.example`, move all `PIPELINE_*` vars to an `# Optional: pipelines feature` section and comment them out
  - Add a note to `CLAUDE.md` under "Pipelines tab": "Disabled by default. Set `ENABLE_PIPELINES=true` to activate."
  - Remove `networkpolicy-api.yaml` if it was added solely for pipeline-backend egress (check annotations)

  **Acceptance:**
  - With `ENABLE_PIPELINES` unset or `false`, the Pipelines tab is invisible regardless of group membership
  - `PIPELINE_SP_TENANT_ID`, `PIPELINE_SP_CLIENT_ID`, `PIPELINE_SP_CLIENT_SECRET` are not required for `streamlit run app.py` to start
  - Existing pipeline tests still pass (they should set `ENABLE_PIPELINES=true` explicitly via mock or env)

---

### OE-4. Consolidate the four Kubernetes NetworkPolicy files

- [x] **Merge NetworkPolicies into one file** — done. `k8s/networkpolicies.yaml` holds all 4 specs (distinct podSelectors verified: dd-app, dd-api, dd-sync, dd-redis); originals deleted; `azure-pipelines.yml` manifest list updated.

  **Files to merge:**
  - `k8s/networkpolicy.yaml` (app pod)
  - `k8s/networkpolicy-api.yaml` (API pod)
  - `k8s/networkpolicy-sync.yaml` (sync worker pod)
  - `k8s/networkpolicy-redis.yaml` (Redis pod)

  **What to do:**
  - Read all 4 files; verify each has a distinct `spec.podSelector`
  - Create `k8s/networkpolicies.yaml` concatenating all 4 specs separated by `---`
  - Delete the 4 original files
  - If `azure-pipelines.yml` or any CI script references the individual files by name, update those references to `networkpolicies.yaml`

  **Acceptance:**
  - `ls k8s/networkpolicy*.yaml` returns only `networkpolicies.yaml`
  - `kubectl apply --dry-run=client -f k8s/networkpolicies.yaml` exits 0 (or `yamllint k8s/networkpolicies.yaml` if kubectl is unavailable)
  - All 4 NetworkPolicy specs are present in the merged file with their original `spec.podSelector` values unchanged

---

### OE-5. Hard-code sync daemon timing constants; keep only port configurable

- [x] **Reduce sync daemon env var surface** — done. The 5 timing values are module constants in `src/sync/daemon.py`; only `SYNC_HEALTHZ_PORT` remains env-configurable. `.env.example`, runbook, and CLAUDE.md updated.

  **Current env vars in `src/sync/daemon.py` (or `src/config.py`):**
  ```
  SYNC_POLL_ACTIVE_S      → keep as constant: 5
  SYNC_POLL_IDLE_S        → keep as constant: 30
  SYNC_DR_EVERY_N         → keep as constant: 20
  SYNC_STALE_ROW_S        → keep as constant: 300
  SYNC_HEALTHZ_PORT       → keep configurable (port conflicts are real)
  SYNC_HEALTHZ_TIMEOUT_S  → keep as constant: 60
  ```

  **What to do:**
  - In `src/sync/daemon.py`, replace the five `int(os.getenv("SYNC_POLL_ACTIVE_S", "5"))` style reads with module-level constants (`_POLL_ACTIVE_S = 5`, etc.)
  - Keep `SYNC_HEALTHZ_PORT = int(os.getenv("SYNC_HEALTHZ_PORT", "8765"))`
  - Remove the 5 timing vars from `src/config.py` if exported there
  - Remove them from `.env.example`
  - In `docs/runbooks/sync-worker.md`, update the "Tunables" section to list only `SYNC_HEALTHZ_PORT`

  **Acceptance:**
  - `grep -r "SYNC_POLL_ACTIVE_S\|SYNC_POLL_IDLE_S\|SYNC_DR_EVERY_N\|SYNC_STALE_ROW_S\|SYNC_HEALTHZ_TIMEOUT_S" src/ .env.example` returns nothing
  - `SYNC_HEALTHZ_PORT` still works (verify the daemon binds to a custom port when the env var is set)
  - `python -m pytest tests/test_sync_daemon.py -q` passes green

---

### OE-6. Delete per-backend storage test files (depends on OE-1)

- [x] **Remove redundant storage test files** — done alongside OE-1. All 7 `tests/test_storage_*.py` files deleted; the zero-result alert cutoff behavior (the only uncovered application-level logic) was ported to `tests/test_analytics.py`.

  **Files to delete:**
  - `tests/test_storage_cms.py`
  - `tests/test_storage_audit.py`
  - `tests/test_storage_analytics.py`
  - `tests/test_storage_notification.py`
  - `tests/test_storage_pipelines.py`
  - `tests/test_storage_preferences.py`

  **Before deleting:** For each file, scan for any test cases that assert application-level behavior (e.g. "expired CMS posts are excluded," "DuckDB preference upsert is idempotent"). If any such cases exist and aren't covered by the higher-level test files (`test_cms.py`, `test_pipelines.py`, `test_admin.py`), port them there first.

  **What to do:**
  - Run `python -m pytest tests/ -q` before and after deletion to confirm no regressions
  - Delete the 6 files
  - Remove any `conftest.py` fixtures used exclusively by these files

  **Acceptance:**
  - All 6 files are gone
  - `python -m pytest tests/ -q --ignore=tests/test_load_smoke.py --ignore=tests/test_wcag_axe.py --ignore=tests/test_nav_render.py` passes with the same or fewer test failures as before
  - No remaining test file imports from `src.storage.cms_storage`, `src.storage.audit_storage`, etc.

---

## How to use this file with Claude

> "Read TODO.md and complete item #3" — picks up the cards.py split.
>
> "Read TODO.md and complete the next open item" — picks the lowest-numbered
> open item.
>
> "Read TODO.md, run the test suite, then complete items #5 and #6 in one PR" —
> bundles the small follow-ups.

Each item's **Acceptance** section is the contract; if Claude can't satisfy
every bullet, it should stop and ask before merging.
