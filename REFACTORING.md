# Refactoring Roadmap

Status as of v0.1.0. This document tracks planned structural changes to the codebase ahead of v0.2.0+. Items are ordered by impact and dependency. Nothing here changes runtime behaviour — only internal organisation.

---

## Why this matters

`app.py` is currently **4 404 lines**. It contains the design system CSS (~930 lines), demo data fixtures, auth flow, six page renderers, two DB adapters, a background sync worker, email helpers, personalisation persistence, lineage graph generation, and the Streamlit entry point — all in one file. That makes it:

- **Impossible to test in isolation** — any test that touches a page renderer must stub every global symbol in the file
- **Slow to import** — even AppTest for a single page runs the whole CSS blob through the Python interpreter
- **Hard to review** — a 4 kloc diff in one file is unusable in GitHub
- **Fragile to AI-assisted edits** — context windows force assistants to work blind, leading to the class of bugs we fixed in this session (indentation crash, NameError from renamed params, CSS vars in canvas)

Target: `app.py` becomes a **≤ 120-line entry point** that wires together imports from `src/`.

---

## Phase 1 — Extract constants & config (prerequisite for everything else)

**New file:** `src/config.py`

Move out of `app.py`:
- All `os.getenv(...)` calls at module level (`DUCKDB_PATH`, `USER_DATA_PATH`, `DATABRICKS_HOST`, etc.)
- `CATALOG_CACHE`, `SCHEMA_CACHE`, `MOCK_GROUPS`, `_DEMO_MODE`, `_MOCK_AUTH`
- `APP_VERSION` constant

This is the first step because every other module will need to import from it, and it has zero dependencies of its own. **Estimated: 60 lines extracted. Risk: low.**

---

## Phase 2 — Extract i18n (`src/i18n.py`)

**New file:** `src/i18n.py`

Move out of `app.py` (lines ~20–77):
- `_load_locales()`, `get_locale()`, `_ensure_locale()`, `t()`, `set_locale()`
- The `_LOCALES` dict

All page renderers call `t()` — extracting i18n early unblocks everything downstream.

Dependency: `src/config.py` (for `LOCALE_DIR` path if we parameterise it).  
**Estimated: 60 lines extracted. Risk: low.**

---

## Phase 3 — Extract design system (`src/ui/css.py`)

**New file:** `src/ui/css.py`

The `DESIGN_CSS` string constant spans lines 236–1166 (~930 lines). The `_VIS_WIDE_CSS` dialog-sizing block is a further ~30 lines. Move both into `src/ui/css.py` and expose a `render_css()` function.

Option A (simpler): keep as Python string constants in `src/ui/css.py`.  
Option B (cleaner): move CSS to `assets/design.css` + `assets/vis_dialog.css` and load with `Path(__file__).read_text()`. Enables editor CSS syntax highlighting, linting, and avoids Python string escape gotchas.

**Recommendation: Option B.** The CSS is large enough that file separation pays off.

Dependency: none.  
**Estimated: 960 lines moved to files. Risk: low — CSS is pure data.**

---

## Phase 4 — Extract DB adapters (`src/db/`)

**New directory:** `src/db/`

### `src/db/duckdb.py`
Move:
- `_duckdb_available()`, `_to_duckdb_sql()`, `_get_shared_duckdb_connection()`
- `_DuckDBCursor`, `_DuckDBConn` classes
- `_run_duckdb_query()`, `_get_write_connection()`

### `src/db/databricks.py`
Move:
- `_get_databricks_connection()`, `_get_databricks_write_connection()`
- `_run_databricks_query()`

### `src/db/queries.py`
Move:
- `run_query()` (the unified router)
- `search_all_metadata()` (lines ~2719–2849) — the largest and most tested single function
- `get_authorized_tables()`
- `get_multi_hop_lineage()` (stub, for forward compat)
- `get_column_business_names()`

This is the highest-value extraction because these are the functions most commonly under test. After this, `conftest.py` can mock at the module level instead of patching global symbols in the monolith.

Dependency: `src/config.py`.  
**Estimated: ~400 lines extracted. Risk: medium — many callers inside app.py.**

---

## Phase 5 — Extract auth (`src/auth.py`)

**New file:** `src/auth.py`

Move:
- `get_msal_app()`, `check_auth()`, `render_signin_page()`
- Mock auth logic (currently scattered in `check_auth` + the entry-point block)
- `is_power_user()`, `is_admin()` (role checks belong with auth)

Dependency: `src/config.py`, `src/i18n.py`, `src/ui/css.py`.  
**Estimated: ~200 lines extracted. Risk: medium — session state coupling.**

---

## Phase 6 — Extract sync worker (`src/sync/`)

**New directory:** `src/sync/`

### `src/sync/worker.py`
Move:
- `_start_sync_worker_thread()`, `_run_dr_resync()`
- Global state accessors: `_get_last_ui_activity()`, `_get_dr_resync_status()`, `_set_dr_resync_status()`, `_set_dr_resync_progress()`, `_mark_ui_activity()`

### `src/sync/push.py`
Move:
- `enqueue_sync()`, `enqueue_column_sync()`
- `_push_to_databricks()`, `_push_definition_to_databricks()`
- `_process_sync_queue()`

Note: `scripts/sync_worker.py` already exists as a standalone nightly-sync runner. The in-app background worker (`_run_dr_resync`) is a *different* beast — it fills gaps in the DuckDB cache on-demand. Rename the standalone script to `scripts/nightly_sync.py` to eliminate confusion.

Dependency: `src/db/`, `src/config.py`.  
**Estimated: ~200 lines extracted. Risk: medium — threading and global state.**

---

## Phase 7 — Extract personalisation & comments (`src/personalization.py`, `src/comments.py`)

### `src/personalization.py`
Move:
- `_user_oid()`, `_pref_upsert()`, `_pref_delete()`, `_pref_load()`, `_sync_prefs_to_session()`

### `src/comments.py`
Move:
- `get_table_comments()`, `_build_comment_tree()`, `save_comment()`
- `send_comment_email()`, `send_reply_email()`, `_fetch_comment_author_email()`

### `src/audit.py`
Move:
- `log_audit_event()`
- `save_table_metadata()`, `save_business_name()`, `get_table_steward()`

Dependency: `src/db/`, `src/config.py`.  
**Estimated: ~400 lines extracted. Risk: low.**

---

## Phase 8 — Extract UI components (`src/ui/`)

### `src/ui/header.py`
Move:
- `LOGO_MARK_SVG`, `render_header()`, `render_footer()`

### `src/ui/lineage.py`
Move:
- `_lineage_vis_html()`, `_build_lineage_graph()`, `_fetch_lineage_hop()`
- `render_lineage_fullscreen()` dialog decorator

### `src/ui/dialogs.py`
Move:
- `render_data_sample()` dialog decorator
- `render_table_metadata_editor()` dialog decorator
- `_viewport_height()` utility

### `src/ui/cards.py`
Move:
- `_render_table_card()`
- `_dq_grade()`, `_compute_live_completeness()`
- `export_schema_to_csv()`

Dependency: `src/i18n.py`, `src/db/queries.py`, `src/config.py`.  
**Estimated: ~500 lines extracted. Risk: medium — Streamlit dialog decorators are module-scoped.**

---

## Phase 9 — Extract page renderers (`src/pages/`)

**New directory:** `src/pages/`

| File | Renderer | Approx lines |
|------|----------|--------------|
| `src/pages/search.py` | Search + table detail panel | ~800 |
| `src/pages/catalog.py` | `render_catalog_browser()` | ~50 |
| `src/pages/discovery.py` | `render_discovery()` | ~140 |
| `src/pages/health.py` | `render_health()` | ~110 |
| `src/pages/glossary.py` | `render_glossary()` | ~100 |
| `src/pages/admin.py` | `render_admin_page()` + admin queries | ~180 |

Note: this is **not** Streamlit multi-page routing. The app uses custom tab-based navigation inside a single Streamlit page. `src/pages/` is a logical namespace — `app.py` imports from it, it does not trigger Streamlit's file-based page routing.

Dependency: all of the above phases.  
**Estimated: ~1 400 lines redistributed. Risk: high — largest and most interdependent block.**

---

## Phase 10 — Thin entry point

After all phases above, `app.py` becomes:

```python
"""Data Dictionary — entry point."""
from src.config import configure_env
from src.ui.css import render_css
from src.auth import check_auth
from src.db.duckdb import _start_sync_worker_thread
from src.pages import search, catalog, discovery, health, glossary, admin
# ... routing logic, ~80 lines total
```

---

## Non-extraction improvements (parallel track)

These can be done at any time and are independent of the module split:

### Testing
- **Replace `conftest.py` monolith stubs with module-level mocks** once the DB layer is extracted — each test file can mock `src.db.queries` cleanly
- **Add `pytest-cov` gate** to CI: enforce ≥ 80% coverage on `src/` modules
- **Property-based tests** for `t()` (all keys resolve, no KeyError) and `_to_duckdb_sql()` (param count matches `?` count)
- Move `tests/load/results/` to `.gitignore`-only output; add a `make load-test` Makefile target

### CSS externalization (Phase 3 follow-up)
- Editor tooling (Prettier, stylelint) can then run on `assets/*.css`
- Design tokens from `design_system/colors_and_type.css` and `app.py`'s `:root` block are currently **duplicated** — consolidate into a single `assets/tokens.css` that both the design system previews and the app import

### Dependency hardening
- Pin exact versions in `requirements.txt` (currently unpinned — risky for production)
- Add `requirements.lock` generated by `pip-compile` (pip-tools)
- Move `faker`, `locust`, `python-pptx`, `playwright` to `requirements-dev.txt` only (done ✓)
- Consider replacing raw pip with `pyproject.toml` + `hatch` for proper package metadata

### Rename `scripts/sync_worker.py` → `scripts/nightly_sync.py`
The file is the standalone nightly Databricks → DuckDB syncer. Its name collides conceptually with the in-app background worker. A one-line rename + CLAUDE.md update removes a persistent source of confusion.

### Observability
- Add structured logging (Python `logging` with JSON formatter) to replace scattered `print()` calls in the sync worker and background thread
- Expose a `GET /healthz` endpoint (Streamlit supports custom HTTP routes via `st.server`) that returns sync worker status — enables k8s liveness probes without polling the UI

---

## Phase 11 — Kubernetes deployment hardening

The current `k8s/` manifests are a solid first draft but have several gaps before they are production-safe.

### 11a — Rename sync script reference
`k8s/cronjob.yaml` runs `python scripts/sync_metadata.py`. Once `scripts/sync_worker.py` is renamed to `scripts/nightly_sync.py` (see Phase 6 note), update the CronJob command to match.

### 11b — Liveness and readiness probes
The `k8s/deployment.yaml` currently has no probes. Streamlit exposes `GET /healthz` at its built-in health endpoint. Add:

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8501
  initialDelaySeconds: 30
  periodSeconds: 15
  failureThreshold: 3
readinessProbe:
  httpGet:
    path: /healthz
    port: 8501
  initialDelaySeconds: 10
  periodSeconds: 5
```

### 11c — Resource limits
Add CPU/memory requests and limits to both the app container and the sync CronJob container. Baseline:
- App: `requests: {cpu: 250m, memory: 512Mi}`, `limits: {cpu: 1000m, memory: 1Gi}`
- Sync job: `requests: {cpu: 100m, memory: 256Mi}`, `limits: {cpu: 500m, memory: 512Mi}`

### 11d — HPA min/max alignment
`k8s/hpa.yaml` should reference the actual Deployment name (`dd-app`) and have `minReplicas: 2` for HA. Currently the min is not set explicitly.

### 11e — PVC storage class annotation
`k8s/pvc.yaml` doesn't specify a `storageClassName`. Add an annotation block with a comment pointing operators to set this for their cluster (e.g., `standard`, `premium-rwo`, `gp3`).

### 11f — Secret rotation runbook
`k8s/secret.yaml` contains placeholder values only (good). Add a `docs/runbooks/secret-rotation.md` explaining how to rotate the Databricks token, Entra ID client secret, and GHCR pull secret without downtime.

### 11g — Network policy
Add `k8s/networkpolicy.yaml` restricting ingress to the app pod to only the ingress controller, and egress to only the Databricks workspace CIDR and Entra ID endpoints. This is a security baseline for production.

### 11h — Namespace resource quota
Add `k8s/resourcequota.yaml` to cap total namespace CPU/memory, preventing a runaway pod from starving cluster neighbours.

**Estimated effort: 1–2 days. Risk: low for probes/resources; medium for network policy (cluster-specific).**

---

## Phase 12 — Documentation overhaul

The existing docs (`README.md`, `ARCHITECTURE.md`, `DEPLOYMENT.md`, `docs/features/`) were written during the v0.1.0 sprint and are now partially stale. A full documentation pass is needed before any external handoff.

### 12a — `ARCHITECTURE.md` — bring current

Gaps to fix:
- Mermaid diagram shows only one compute layer; add the **DuckDB local cache** layer and the **background DR resync worker** that fills it
- Add the **personalisation persistence** path (`USER_DATA_PATH` → user preferences DuckDB file)
- Update security model section: describe the `SELECT_ALL_USERS` sentinel and how `_to_duckdb_sql()` translates named-param Databricks SQL to positional-param DuckDB SQL
- Add an **i18n** section describing locale loading and the `t()` call convention
- Replace emoji headings (`🏗️`, `🌟`) with plain sentence-case text per the design system's tone rules

### 12b — `DEPLOYMENT.md` — bring current

Gaps to fix:
- Add a **local development quickstart** section covering `generate_test_data.py`, `DUCKDB_PATH`, and the 4-department mock auth buttons
- Add the **environment variable reference table** (all `os.getenv()` calls in `app.py` with their defaults and required/optional status)
- Add a **smoke test checklist** (matches the load test smoke tag: login, search, catalog, glossary tabs all return 200)
- Update the k8s apply order after Phase 11 changes (new `networkpolicy.yaml`, `resourcequota.yaml` steps)
- Add a **rollback procedure** (image tag pinning, `kubectl rollout undo`)

### 12c — `README.md` — sharpen for external audience

The README is the first thing a new engineer or evaluator sees. Improvements:
- Add a **one-paragraph product description** at the very top (before any technical details)
- Add a **screenshots section** pointing to `screenshots/latest/` (3–4 key screens)
- Shorten the "Architecture" section to 3 bullet points + link to `ARCHITECTURE.md`
- Add a **"Contributing"** section with branch naming convention, commit message style, and `pytest` gate
- Add **badges**: Python version, license, CI status

### 12d — Per-module docstrings (after Phase 1–9 extraction)

Once `app.py` is broken into modules, each new file needs a module-level docstring covering:
- **Purpose**: one sentence on what this module owns
- **Public API**: list of exported functions/classes
- **Dependencies**: which other `src/` modules it imports
- **Thread safety**: note if any function touches shared mutable state

### 12e — Function-level docstrings audit

Audit all public functions in `app.py` for missing or stale docstrings. Priority targets:
- `search_all_metadata()` — documents the UNION ALL SQL, param order, and permission join semantics
- `_to_duckdb_sql()` — documents the named→positional param translation and its limitations
- `_run_dr_resync()` — documents when it runs, what it fills, and thread safety contract
- `check_auth()` — documents the mock vs real auth branching and session state keys it sets
- `render_table_detail()` (the large search detail panel) — documents session state keys and widget key namespacing

### 12f — `docs/` structure

Extend `docs/` from its current `features/` folder to a proper docs tree:

```
docs/
  features/          # existing feature specs (keep)
  runbooks/
    secret-rotation.md   (Phase 11f)
    incident-response.md
    scaling.md
  api/
    queries.md       # SQL query reference (search, lineage, permissions)
    locale-keys.md   # all i18n keys with EN/FR values
  adr/
    001-duckdb-local-cache.md     # why DuckDB over SQLite or Redis
    002-streamlit-not-fastapi.md  # trade-offs
    003-push-down-sql-auth.md     # security model rationale
```

The ADR (Architecture Decision Records) format is especially useful here: the project made several non-obvious choices (DuckDB over SQLite, push-down SQL auth, vis.js over Plotly for lineage) that future maintainers will question. Recording the reasoning prevents re-litigating settled decisions.

### 12g — Test documentation

Add `tests/README.md` covering:
- How to run the full test suite (`pytest`)
- How to run load tests (`locust ...` commands from `tests/load/locustfile.py` header)
- How to regenerate the test dataset (`scripts/generate_test_data.py --seed 42`)
- What `conftest.py` stubs and why (so a new contributor doesn't try to add real Databricks creds)
- SLA targets from `tests/load/sla.json` and how to read the Locust CSV output

**Estimated effort: 3–5 days. Can be parallelised across team members — each subsection is independent.**

---

## What NOT to refactor

- **`design_system/`** — design reference artefacts; no Python, no tests; leave as-is
- **`locale/`** — two JSON files; no refactoring needed
- **`scripts/generate_test_data.py`** — standalone tool, 1 011 lines, self-contained; document it but don't split it
- **`tests/` structure** — currently flat + `tests/load/`; once modules are extracted the test files will grow but the directory layout is correct

---

## Suggested sequence for implementation

```
Phase 1 (config)  →  Phase 2 (i18n)  →  Phase 3 (CSS)
                                              ↓
Phase 4 (DB)  →  Phase 5 (auth)  →  Phase 6 (sync)
                                              ↓
Phase 7 (prefs/comments)  →  Phase 8 (UI)  →  Phase 9 (pages)
                                              ↓
                                       Phase 10 (entry point)

Parallel track (can start immediately, independent of code split):
  Phase 11 (k8s hardening)  +  Phase 12 (docs overhaul)
```

Phases 1–3 are safe to do on a single PR each (no behavioural change, tests still pass).  
Phases 4–6 require updating `conftest.py` patch targets simultaneously.  
Phases 7–9 are best done one page renderer at a time, each on its own PR.  
Phases 11 and 12 are **parallel** — no code changes, no test risk, can be done on a dedicated branch (`feature/docs-and-k8s`).

---

## Metrics to track

| Metric | Now | Target |
|--------|-----|--------|
| `app.py` line count | 4 404 | ≤ 120 |
| Largest single file | 4 404 lines | ≤ 500 lines |
| Test coverage (unit) | ~65% (estimated) | ≥ 80% |
| `pytest` cold-start time | ~8 s | ≤ 3 s |
| Requirements pinned | No | Yes (`pip-compile`) |
| k8s probes configured | No | Yes (liveness + readiness) |
| k8s resource limits set | No | Yes (app + sync job) |
| Public functions with docstrings | ~40% | ≥ 90% |
| ADRs recorded | 0 | ≥ 3 (DuckDB, Streamlit, push-down auth) |
| `tests/README.md` exists | No | Yes |

---

## Migration lessons learned — Phases 1–3

> Written after completing Phases 1–3 on `feature/src-split-phase1-3`. Keep this
> section updated as later phases complete. The goal is to make the next engineer's
> (or AI agent's) extraction session predictably safe.

---

### Lesson 1 — `sys.modules` caching freezes `os.getenv()` at import time

**What happened:** We moved `ENABLE_MOCK_AUTH`, `ENVIRONMENT`, and `DEMO_DATA` into
`src/config.py`. All three are evaluated once when `src.config` is first imported.
Tests that use `monkeypatch.setenv("ENVIRONMENT", "production")` saw the old cached
value — causing 25 silent failures.

**Rule:** Any env var that a test suite needs to override per-test **must** stay as an
inline `os.getenv()` call inside the function or module that uses it (in our case, the
`app.py` entry point). Only truly static, process-lifetime values belong in
`src/config.py`.

**Pattern to check during every extraction:** search the candidate block for
`os.getenv()`. For each one, ask: "Does any test override this env var?" If yes, leave
it inline.

---

### Lesson 2 — `exec()` test helpers need explicit namespaces

**What happened:** `tests/test_duckdb_cache.py::_load_duckdb_helpers()` extracts a
slice of `app.py` with `exec()`. After Phase 1, `CATALOG_CACHE`, `SCHEMA_CACHE`, and
`logging` were no longer module-level globals in the extracted slice — they had moved to
`src/config.py` and a stdlib import block. The exec'd code resolved them against the
exec namespace dict, found nothing, and raised `NameError`.

**Rule:** Before each extraction, grep for every name that the exec'd slice resolves from
module-level scope. Add them explicitly to the `ns = {...}` dict:

```python
from src.config import CATALOG_CACHE as _CC, SCHEMA_CACHE as _SC
import logging as _logging_mod
ns = {
    ...,
    "CATALOG_CACHE": _CC,
    "SCHEMA_CACHE":  _SC,
    "logging":       _logging_mod,
}
```

**Broader note:** `exec()` based test helpers are fragile by design. Once Phase 4
extracts `_DuckDBCursor` etc. into `src/db/duckdb.py`, rewrite those tests to import
directly rather than exec-slice.

---

### Lesson 3 — Never use multi-line regex to remove string literals

**What happened:** The first attempt to remove the 930-line `DESIGN_CSS = """..."""`
block used `re.sub(r'DESIGN_CSS\s*=\s*""".*?"""', ..., src, flags=re.DOTALL)`. The
regex silently matched a partial block (ending at the first `"""` inside a CSS string
value) and the replacement left a dangling orphan body, producing an
`IndentationError: unexpected indent` at runtime.

**Rule:** For removing or relocating large multi-line literals, use line-number-based
slicing, not regex:

```python
lines = source.splitlines(keepends=True)
# Find start/end by searching for known anchor strings
start_idx = next(i for i, l in enumerate(lines) if 'DESIGN_CSS = """' in l)
end_idx   = next(i for i, l in enumerate(lines[start_idx:], start_idx)
                 if l.strip() == '"""') + 1
new_source = "".join(lines[:start_idx] + replacement_lines + lines[end_idx:])
```

Always verify with `python -c "import py_compile; py_compile.compile('app.py')"` before
running tests.

---

### Lesson 4 — Check which tests grep the source file text

**What happened:** `TestDesignSystem` in `tests/test_app.py` validates CSS tokens by
regex-searching `app.py` for the `DESIGN_CSS = """..."""` literal. After we moved CSS
to `assets/design.css` the regex returned `None` and the entire test class was
asserting against an empty string.

**Rule:** Before any extraction, run `grep -r "app.py\|read_app_source\|open.*app" tests/`
to find tests that read the source file as text. These must be updated to look in the
new location. The safest upgrade is a two-step fallback: try the new file path first,
fall back to the old regex for backward compatibility.

---

### Lesson 5 — Implicit alias dependencies travel with the removed block

**What happened:** The i18n block contained `import json as _json`. That alias was also
used at six other locations in `app.py` (lineage graph, render_header, queue
serialisation). Removing the block removed the alias — causing `NameError: name '_json'
is not defined` in the middle of rendering.

**Rule:** Before removing any block, run this pipeline:

```bash
# 1. List every name defined in the block (import aliases, constants, top-level defs)
# 2. Search the REST of app.py for those names
grep -n "_json\|json\." app.py
```

Any name used outside the block must be re-declared explicitly after the `from src.x
import ...` line.

---

### Lesson 6 — Verify imported names don't shadow each other

When replacing a block with `from src.module import name`, check that:
1. No existing `import name` statement further down will shadow it.
2. No `name = ...` assignment exists that would override the import.

Use `grep -n "^import\|^from\|^DESIGN_CSS\|^_json" app.py` to audit quickly.

---

### Lesson 7 — Commit scope per phase, test before every commit

Each phase should be a single atomic commit with:
- The new `src/` file(s)
- The `app.py` modifications
- Updated tests

Run `pytest` before committing. The 4 pre-existing failures in `test_navigation.py` are
the known baseline — any additional failure introduced by the extraction means the phase
is not done.

---

### Lesson 8 — Agent-assisted extraction needs a tighter brief

Both AI agent runs in this session got stuck: one couldn't commit (no git credentials),
the other confused the project's source files with internal files. For future agent
handoffs, the brief must include:
- **Exact line numbers** to remove (run `grep -n` first and paste the output)
- **Exact import line** to add as replacement
- **Which tests to run** as acceptance check
- **The 4 known failing tests** so the agent doesn't try to fix them

Keep the scope to one phase per agent call.
