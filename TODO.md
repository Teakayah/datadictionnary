# Engineering TODO

Living backlog from the senior-developer audit (2026-05-07). Each item is
self-contained — pick any one and ask Claude to implement it.

Status legend: `[ ]` open · `[~]` in progress · `[x]` done

---

## Next steps (open)

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

- [ ] **`DuckDBQueryUser` never runs real queries.** `_open_con()` returns `None`
      for all users because `SET search_path = 'dictionary_cache'` fails on a
      direct DuckDB connection — that schema only exists when the file is
      `ATTACH`ed under that name. Every DuckDB task reports a 0ms failure
      instantly (100% failure rate confirmed in the 150-user full-load run).
      Fix: open the working copy as `:memory:` + `ATTACH` (matching the main
      app's connection pattern in `duckdb_adapter.py`) rather than connecting
      directly, so `dictionary_cache.*` is resolvable.

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
