# Engineering TODO

Living backlog from the senior-developer audit (2026-05-07). Each item is
self-contained — pick any one and ask Claude to implement it.

Status legend: `[ ]` open · `[~]` in progress · `[x]` done

---

## Quick wins (done)

- [x] Replace deprecated `datetime.utcnow()` → `datetime.now(UTC)` (commit bc4df2c)
- [x] Pin runtime deps and declare `requests` (commit bc4df2c)
- [x] Refuse to start with `ENABLE_MOCK_AUTH=true` outside `ENVIRONMENT=development` (commit bc4df2c)
- [x] Split `MAX_BUSINESS_NAME_LEN` (255) and `MAX_DEFINITION_LEN` (2000) (commit bc4df2c)
- [x] Stop re-firing the viewport-height JS call after first capture (commit bc4df2c)
- [x] Whitelist identifiers + email-validate steward in `src/sync/push.py` (commit bc4df2c)

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

**Out of scope (still open):** PostgreSQL migration for multi-writer
support. Today the sidecar plus the (multi-replica) Streamlit pods all open
`USER_DATA_PATH` — DuckDB serialises writes via its OS-level file lock,
which is fine at low write volume but will not scale linearly. File a
separate ticket if write contention shows up.

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
  `GroupMember.Read.All` is load-bearing.
- `tests/test_auth_graph.py` — 19 tests covering overage detection,
  pagination, 5xx / 403 / network errors, cache hit/miss, empty-OID path,
  and the three branches of `_resolve_user_groups`.

**Out of scope (still open):** SSO logout / silent re-auth on group
membership change. Group changes are picked up at next token refresh
(≤1h, then ≤1h cache TTL).

### 3. Split `src/ui/cards.py` (was 1,083 lines)

**Status:** done (branch `feat/cards-split`).

Final layout, all files <400 lines:

```
src/ui/cards/
  __init__.py    45  pure re-export shim for backwards compat
  _shared.py     70  _dq_grade, _compute_live_completeness, _POST_COLOR
  detail.py     110  render_table_metadata_editor, render_data_sample
                     (consumed by src/pages/search.py)
  cms_admin.py  148  _render_admin_cms_section + create dialog
                     (peeled out so admin.py stays under 400)
  health.py     155  render_health + private helpers
  pipelines.py  245  render_pipelines_page + admin pipeline section
  admin.py      311  render_admin_page + audit/sync/editing sections
  discovery.py  317  render_discovery + CMS banner + table card
```

Each move is its own commit; tests stay green at 267 throughout.
``cards/__init__.py`` is a re-export shim — historic callers
(`from src.ui.cards import render_health`) keep working unchanged. New
code should import from the specific submodule
(`from src.ui.cards.discovery import render_discovery`).

**Out of scope (deferred):** migrate the four remaining callers
(``app.py``, ``src/pages/catalog.py``, ``src/pages/search.py``,
``tests/test_admin.py``) off the shim and delete
``src/ui/cards/__init__.py``'s re-exports. ~5 minutes of mechanical work
in a follow-up PR.

### 4. Storage abstraction — collapse demo / DuckDB / Databricks branching

**Status:** done (branch `feat/storage-abstraction`). Acceptance bar met:

```
$ git grep "_duckdb_available()" src/cms.py src/pipelines.py src/personalization.py
(no matches)
```

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

Each entity migrated as its own commit, tests stayed green throughout
(289 → 307 → 321 → 336). Protocol-based design lets test code inject
`Fake*Storage` without inheriting; existing callers unchanged.

**Out of scope (deferred):**

- ``src/audit.py::save_table_metadata`` still issues a local UPDATE
  against the read-only-attached catalog cache. The UPDATE silently
  fails in production today; durability comes from ``enqueue_sync`` to
  Databricks. Migrating that to a ``CatalogTableMetadataStorage`` is a
  separate concern — catalog cache is not user_data.
- Re-using ``BusinessNameOverrideStorage.get_for_table`` from
  ``src/pages/search.py`` (currently still calls
  ``src.db.queries.get_column_business_names``). Mechanical follow-up.

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

**Why:** `_get_databricks_write_connection` opens a fresh SQL Warehouse
session per write (`src/db/databricks_adapter.py:23`). Audit-log spam
(every edit) opens a new Spark cluster handshake each time.

**Target:** cache the write connection like the read path with a TTL, or
switch all writes to go through the sidecar worker (Investment #1) and
delete `_get_databricks_write_connection` entirely.

**Note:** prefer the second option once Investment #1 lands.

### 8. Drop `GroupMember.Read.All` scope if not used after Investment #2

**Why:** if Investment #2 is rejected, the scope (`src/config.py:17`) is
unused and broader than needed.

**Target:** remove `"GroupMember.Read.All"` from `SCOPE` and update
`docs/adr/` / `.env.example` if applicable.

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
