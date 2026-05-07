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

**Why:** `_get_shared_duckdb_connection` returns a single in-memory DuckDB
connection (`src/db/duckdb_adapter.py:177`) shared across the Streamlit
script-runner threads and the daemon worker. Reads are unsynchronised and
the daemon is a `@st.cache_resource` callable from a thread with no
`ScriptRunContext`. Latent crash under any real concurrency.

**Target shape:** Streamlit pods enqueue into `user_data.pending_sync` only.
A separate `python -m src.sync.daemon` process drains the queue and runs DR
resync. The `pending_sync` table is the IPC bus — no new infra.

**Acceptance:**
- `_start_sync_worker_thread` deleted from `src/sync/worker.py` and `app.py`.
- `src/sync/daemon.py` runs standalone with `--once` and `--daemon` flags,
  uses its own `duckdb.connect(USER_DATA_PATH)`, no Streamlit imports.
- New k8s `Deployment` (`replicas: 1`) under `k8s/` mounting the same PVC.
- `tests/test_sync_metadata.py` extended to cover the daemon's drain loop
  with a fake Databricks cursor.
- DR resync recovery: `attempts < MAX_ATTEMPTS` AND
  `last_attempt_at < now - 5m` brings stuck rows back to `pending`.
- Worker exposes `/healthz` returning 200 when its DuckDB handle is open.

**Out of scope:** PostgreSQL migration for multi-writer support (file a
separate ticket if more than one Streamlit replica needs to write
`user_data.*`).

### 2. Entra ID groups overage handling

**Why:** `claims.get("groups", [])` (`src/auth.py:274`) silently returns
`[]` when Entra ships a `_claim_names`/`_claim_sources` pointer instead of
inline groups (>~150 groups). Affected users see zero tables. Invisible in
dev, hard production failure for enterprise tenants.

**Target shape:**
- New `src/auth_graph.py` with `fetch_member_groups(access_token)` calling
  `POST graph.microsoft.com/v1.0/me/getMemberObjects`
  `{"securityEnabledOnly": true}`.
- `@st.cache_data(ttl="1h")` keyed on user OID.
- In `check_auth` after token acquisition: if `groups` is missing AND
  `_claim_names.groups` is present, call the Graph helper.

**Acceptance:**
- `tests/test_auth_graph.py` covers: inline groups path, overage path, Graph
  5xx (degrade to empty groups + warning, do not silently grant access),
  cache hit on second call within TTL.
- `SCOPE` in `src/config.py` documented with a comment that
  `GroupMember.Read.All` is required by the overage path.

**Out of scope:** SSO logout / silent re-auth on group membership change.
Group changes will be picked up at next token refresh (≤1h).

### 3. Split `src/ui/cards.py` (1,178 lines)

**Why:** mixes 5 unrelated concerns (discovery, admin, CMS, pipelines,
health). Imports admin/CMS/pipeline write APIs alongside read-only
discovery rendering. Audit surface for "what can a write touch" is the
whole file.

**Target layout:**
```
src/ui/cards/
  __init__.py     # re-exports for backwards compat during migration
  _shared.py      # _dq_grade, _compute_live_completeness, _POST_COLOR
  discovery.py    # render_discovery, _render_table_card, render_cms_banner
  health.py       # render_health
  admin.py        # render_admin_page + admin sub-renderers
  pipelines.py    # render_pipelines_page (UI; logic stays in src/pipelines.py)
```

**Acceptance:**
- `wc -l src/ui/cards/*.py` shows no file >400 lines.
- Test suite passes unchanged at every step (each move is its own commit).
- After the migration: `git grep "from src.ui.cards import"` returns only
  the new submodule paths; the `cards/__init__.py` shim can be deleted in a
  follow-up PR.

**Migration order (each step keeps tests green):**
1. Create `_shared.py` with helpers + re-exports.
2. Move `render_health` → `cards/health.py`.
3. Move `render_pipelines_page` → `cards/pipelines.py`.
4. Move `render_admin_page` and admin sub-renderers → `cards/admin.py`.
5. Move discovery + CMS banner → `cards/discovery.py`.
6. Replace `src/ui/cards.py` with `cards/__init__.py` re-exports.
7. (Follow-up PR) delete the shim once callers migrated.

### 4. Storage abstraction — collapse demo / DuckDB / Databricks branching

**Why:** the `if not _duckdb_available(): … session_state demo path … else:
… duckdb path` triple is duplicated ~13 times across `src/cms.py`,
`src/pipelines.py`, `src/personalization.py`, `src/audit.py`. Adding a new
entity means writing the same three-way switch again.

**Target shape:**
```python
# src/storage/base.py
class CMSStorage(Protocol):
    def list_active(self) -> list[Post]: ...
    def list_all(self) -> list[Post]: ...
    def create(self, post: Post) -> None: ...
    def delete(self, post_id: str) -> None: ...
# Same pattern for PipelineDefStorage, PipelineRunStorage, PreferenceStorage.

# src/storage/__init__.py
@st.cache_resource
def get_cms_storage() -> CMSStorage:
    if is_demo_mode():     return DemoCMSStorage()
    if _duckdb_available(): return DuckDBCMSStorage()
    return DatabricksCMSStorage()
```

**Acceptance:**
- One entity migrated per PR (CMS first — smallest surface).
- Public function names (`get_active_posts`, `create_post`, etc.) preserved
  as thin wrappers so callers don't change.
- New tests inject `FakeCMSStorage` instead of mocking `_duckdb_available`.
- After all four entities migrated: `git grep "_duckdb_available()" src/cms.py
  src/pipelines.py src/personalization.py` returns nothing.

**Migration order (one PR each):**
1. CMS (3 functions).
2. Pipelines — split into `PipelineDefStorage` + `PipelineRunStorage`.
3. Preferences + site settings.
4. Audit / business name overrides (most entangled — last, possibly behind a
   feature flag).

---

## Smaller follow-ups (open)

### 5. Defense-in-depth: server-side auth checks on write paths

**Why:** today only the UI gates these. If `is_admin()` regresses or a new
caller bypasses the UI, the cost is real (pipeline runs, admin posts).

**Target:** apply the `src/audit.py:52` pattern (`if not is_admin(): raise
PermissionError`) to:
- `src/pipelines.py`: `trigger_pipeline`, `cancel_run`, `delete_pipeline_def`,
  `create_pipeline_def`.
- `src/cms.py`: `create_post`, `delete_post`.
- `src/personalization.py`: `set_editing_enabled`.

**Acceptance:** each function rejects with `PermissionError` when the caller
is not admin / pipeline user. Tests cover the rejection path.

### 6. Unit tests for `src/sync/push.py`

**Why:** `_push_to_databricks` dispatches 5 sync types and silently falls
through on unknown types. Easy to break without noticing.

**Target:** new `tests/test_sync_push.py` with a fake cursor:
- One test per sync type (COLUMN_DEF, TABLE_DESC, STEWARD, AUDIT, COMMENT).
- Unknown sync_type emits a warning and does not call cursor.execute.
- `_safe_ident` rejects backticks, dots, semicolons, and non-ASCII.
- `_split_full_name` rejects 2-part and 4-part names.
- `STEWARD` with non-email value raises `ValueError`.

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
