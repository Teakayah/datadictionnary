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

## What NOT to refactor

- **`design_system/`** — design reference artefacts; no Python, no tests; leave as-is
- **`k8s/`** — infra config; no Python; leave as-is
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
```

Phases 1–3 are safe to do on a single PR each (no behavioural change, tests still pass).  
Phases 4–6 require updating `conftest.py` patch targets simultaneously.  
Phases 7–9 are best done one page renderer at a time, each on its own PR.

---

## Metrics to track

| Metric | Now | Target |
|--------|-----|--------|
| `app.py` line count | 4 404 | ≤ 120 |
| Largest single file | 4 404 lines | ≤ 500 lines |
| Test coverage (unit) | ~65% (estimated) | ≥ 80% |
| `pytest` cold-start time | ~8 s | ≤ 3 s |
| Requirements pinned | No | Yes (`pip-compile`) |
