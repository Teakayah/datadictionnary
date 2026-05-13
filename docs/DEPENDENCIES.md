# Dependency reference

All dependencies for the Data Dictionary application, with descriptions, justifications, and known trade-offs. Runtime dependencies are pinned to compatible ranges (`>=x.y,<next-major`). Dev-only dependencies do not ship in the production image.

---

## Runtime dependencies (`requirements.txt`)

### `streamlit` — `>=1.50,<2` (installed: 1.57.0)

**What it does.** Streamlit is the web UI framework for the entire application. It renders pages, manages session state, and handles the WebSocket connection between the browser and the Python process. Every tab, card, button, and input in the app is a Streamlit widget. `app.py` is the single entry point; all pages are sub-modules under `src/ui/` and `src/pages/` that Streamlit calls on each interaction.

**Why it was chosen.** The Business Data Dictionary is an internal tool for non-technical business users whose primary interactions are search, browse, and occasional low-frequency writes (bookmarks, comments, metadata edits). The team building it is small with strong Python skills and limited frontend experience. The alternatives considered were:

- **FastAPI + React** — full control over the UI and standard HTTP semantics, but requires maintaining two codebases (Python API + JavaScript frontend), adds React state management and build tooling overhead, and adds weeks to the time-to-first-demo.
- **Dash** — Python-native like Streamlit but oriented toward data visualization dashboards, not search-first catalog UIs. Less community momentum at time of decision.

Streamlit's single-codebase model means the same engineers who write the DuckDB queries write the UI. OIDC authentication, permission enforcement, and search are all expressed in one language. A new tab or feature card is tens of lines of Python rather than coordinated frontend + backend changes. (ADR 003)

**Known trade-offs.**
- Streamlit drives interactions over a binary WebSocket protocol (protobuf), not plain HTTP. Conventional HTTP load-testing tools (k6, wrk) cannot exercise real user interactions — only the page-shell delivery endpoint. This is mitigated in `tests/load/locustfile.py` via a `DuckDBQueryUser` class that exercises the actual performance-sensitive path (the DuckDB search query) directly, bypassing the WebSocket layer.
- Streamlit re-runs the entire script top-to-bottom on every interaction. Redundant DuckDB queries are avoided through `st.session_state` caching and by pulling `get_authorized_tables()` once at the top of `render_search_page()`.
- Multi-page routing uses a single `app.py` entry point (not Streamlit's file-based `pages/` directory) because tab visibility is permission-aware — some tabs are only shown to `ADMIN_GROUPS` or `PIPELINE_GROUPS` members, which requires custom routing logic.
- Full end-to-end click-flow testing requires Playwright. `streamlit.testing.v1.AppTest` (used in `tests/test_app.py` and others) covers rendering and session-state assertions but does not simulate real browser WebSocket interactions.

---

### `streamlit-autorefresh` — `>=1.0,<2` (installed: 1.0.1)

**What it does.** Injects a self-refresh trigger into a Streamlit app at a configurable interval without blocking the Python script thread. Unlike `time.sleep()`, which freezes the entire Streamlit process (blocking all other users on the same pod), `streamlit-autorefresh` schedules the rerun client-side and returns control immediately.

**Why it was chosen.** The pipelines tab (`src/ui/cards/pipelines.py`) must poll the backend status API (Databricks Jobs, ADF, ADO) every 3 seconds while a run is in flight to update the progress bar. A blocking `time.sleep(3)` was the initial implementation and was replaced (see the `performance/remove-time-sleep` PR) because it held the Streamlit script-runner thread, preventing other sessions from rendering during the sleep window. `streamlit-autorefresh` is the standard community solution for non-blocking periodic reruns in Streamlit.

**Known trade-offs.** Adds a third-party Streamlit component dependency. The component communicates via Streamlit's component API (iframe + `postMessage`), which adds a small overhead per refresh cycle. Only active when a pipeline run is in flight — the refresh is not triggered unconditionally.

---

### `streamlit-js-eval` — `>=1.0,<2` (installed: 1.0.0)

**What it does.** Evaluates an arbitrary JavaScript expression in the browser from within a Streamlit Python script and returns the result synchronously to Python. Used in `src/ui/lineage.py` to read `window.innerHeight` so the lineage graph component can be sized to fill the visible viewport rather than using a hard-coded pixel height.

**Why it was chosen.** Streamlit does not expose the browser viewport dimensions natively. The lineage graph is rendered as an HTML component via `streamlit.components.v1.html()`; setting its height without knowing the viewport produces either a truncated graph or unnecessary whitespace. `streamlit-js-eval` is the minimal, established solution for reading browser-side values — the alternative would be a custom Streamlit component with a full JS build toolchain.

**Known trade-offs.** Tight dependency on a small, lightly-maintained third-party component. If it breaks on a future Streamlit version, the fallback is a hard-coded default height (already implemented in `_viewport_height(fallback=800)`).

---

### `duckdb` — `>=1.0,<2` (installed: 1.5.2)

**What it does.** DuckDB is an embedded, in-process columnar analytical database. It runs as a library inside the Python process — no server, no network socket, no daemon. The nightly sync job writes the entire catalog snapshot to a local `.duckdb` file; the Streamlit app opens that file read-only and executes all search, filter, and aggregate queries against it. A second file (`dict_user_data.duckdb`) holds user-generated data (bookmarks, comments, business-name overrides, audit log, pipeline definitions). Both files are `ATTACH`ed at startup, enabling cross-file JOINs.

**Why it was chosen.** The alternatives considered were:

- **SQLite** — built into Python, zero dependency, but designed for transactional OLTP workloads. Multi-table GROUP BY and JOIN queries (the core patterns of a search-and-filter catalog UI) are measurably slower on SQLite than on a columnar engine. No native Parquet export.
- **Redis** — excellent for key-value point lookups but does not support SQL JOINs, which are essential for the push-down permission filter (`JOIN permissions_cache WHERE principal IN ($groups)`). Would require moving permission enforcement into Python — a security regression (see ADR 002).
- **Polars in-memory** — very fast analytical queries but no persistence; data must be reloaded from Databricks on every session start (several-second cold start for 800 tables). No SQL interface — queries must be rewritten in the Polars expression API, diverging from the Databricks SQL strings that are tested against both backends.

DuckDB speaks standard SQL, runs in-process (zero infrastructure for local development), and achieves p95 search query latency under 8 ms on the 800-table reference dataset, compared to ~300 ms for a network round-trip to the Databricks SQL Warehouse. The catalog file is replaced atomically by the sync job (`os.replace()`), so readers always see a consistent snapshot with no coordination overhead. (ADR 001)

**Known trade-offs.**
- Single-writer constraint per file. The sync job holds an exclusive write lock while rebuilding the catalog file (30–90 s). Readers fall back to the previous file during this window via the atomic-replace mechanism.
- Not a networked database. Horizontal scaling (multiple Streamlit replicas) requires all pods to share the same PVC mount, which is why `dd-data` uses `ReadWriteMany` access mode.
- A small dialect-translation layer (`_to_duckdb_sql()` in `src/db/duckdb_adapter.py`) converts Databricks SQL named parameters (`%(name)s`) to DuckDB positional parameters (`?`). New query patterns that use Databricks-specific functions must be added to this translator.

---

### `pandas` — `>=2.2,<3` (installed: 2.3.3)

**What it does.** Pandas provides the `DataFrame` abstraction used throughout the application to handle query results from both DuckDB and the Databricks SQL Warehouse. It is used for: building search result sets (`src/pages/search.py`), computing health-dashboard metrics (`src/ui/cards/health.py`), processing lineage graph data (`src/ui/lineage.py`), and constructing schema-export CSVs. Streamlit itself accepts DataFrames natively for rendering tables.

**Why it was chosen.** Both DuckDB and `databricks-sql-connector` return results as Pandas DataFrames by default (`.df()` on DuckDB, `.fetchall_arrow().to_pandas()` on DBSQL). Adopting a different data-frame library (Polars, for example) would require conversion at every query boundary. Pandas is also the standard Streamlit DataFrame type, making rendering trivial. The application's data volumes (at most a few thousand rows per query) are well within Pandas' in-memory comfort zone.

**Known trade-offs.** `iterrows()` was removed throughout the codebase in favour of `itertuples()` and vectorized string operations, because `iterrows()` is significantly slower for row-by-row access. Pandas' eager-loading model means entire result sets are held in memory — acceptable at catalog scale but worth revisiting if row counts grow into the hundreds of thousands.

---

### `databricks-sql-connector` — `>=4.2,<5` (installed: 4.2.6)

**What it does.** The official Databricks SQL Warehouse connector for Python. Provides a DBAPI 2.0-compliant cursor interface to execute SQL against a Databricks SQL Warehouse over HTTPS. Used exclusively by:
- The **nightly sync job** (`scripts/nightly_sync.py`) to write the catalog snapshot (`TRUNCATE` + `INSERT INTO`) to `data_governance.dictionary_cache`.
- The **sidecar sync worker** (`src/sync/push.py`) to push queued metadata changes back to Unity Catalog (`ALTER TABLE … COMMENT`, `INSERT INTO audit_log`).

The Streamlit pods themselves **never** open a connection to the SQL Warehouse — they query DuckDB locally.

**Why it was chosen.** It is the only supported connector for Databricks SQL Warehouses. The alternative (raw HTTP to the Databricks REST API) would require reimplementing connection pooling, retry logic, and the Thrift binary protocol.

**Known trade-offs.** The connector adds significant transitive dependencies (`thrift`, `pyarrow`, `pybreaker`, etc.). A future optimization could replace the connector with direct Unity Catalog REST API calls for the write path, removing this dependency from the production image entirely — but the connector's DBAPI interface makes SQL writes straightforward and is retained for now.

---

### `databricks-sdk` — `>=0.100,<1` (installed: 0.108.0)

**What it does.** The official Databricks Python SDK, providing `WorkspaceClient` — a high-level client for the Databricks REST API. Used exclusively by the **nightly sync job** to crawl the Unity Catalog hierarchy: listing catalogs, schemas, tables, columns, lineage edges, and extracting `GRANT` permissions per table. The SDK handles authentication (PAT token or OAuth), pagination, and retry logic for each API call.

**Why it was chosen.** The alternative is raw `requests` calls to the Unity Catalog REST API endpoints. The SDK abstracts pagination (`list()` returns a generator, not a single page), handles rate-limit retries, and exposes typed Python objects for catalog entities. The metadata crawl touches ~800 tables × 15 columns × multiple API endpoints, so the SDK's built-in pagination and retry behaviour is load-bearing.

**Known trade-offs.** The SDK is marked Beta (`<1`). Breaking API changes between minor versions are possible; the upper bound `<1` is intentional — every SDK update must be tested before adopting.

---

### `msal` — `>=1.30,<2` (installed: 1.36.0)

**What it does.** The Microsoft Authentication Library. Drives the full OAuth 2.0 / OpenID Connect authorization-code flow in `src/auth.py`: constructs the Entra ID authorization URL, exchanges the auth code for tokens, validates the ID token signature, and extracts claims (including the `groups` claim used for RBAC). Also used in `src/pipelines.py` via `ConfidentialClientApplication` for client-credentials token acquisition — the service principal tokens that authorize calls to the Databricks Jobs API, Azure Data Factory, and Azure DevOps.

**Why it was chosen.** MSAL is the Microsoft-maintained, officially supported library for Entra ID authentication. The alternative — implementing the OIDC flow manually with `requests` and a JWT validation library — would require handling token refresh, token caching, and the overage pointer (`_claim_names.groups`) without Microsoft's tested implementations. MSAL is the only reasonable choice for a Microsoft-stack enterprise deployment.

**Known trade-offs.** MSAL's token cache is in-memory and process-local, which is correct for stateless Streamlit pods (each pod handles its own session). The 1-hour groups cache in `src/auth_graph.py` is implemented separately in a process-level dict (not in MSAL's cache) because it needs to survive across sessions on the same pod and be invalidatable on sign-out.

---

### `requests` — `>=2.32,<3` (installed: 2.34.0)

**What it does.** Standard Python HTTP client. Used directly in `src/pipelines.py` to call three external REST APIs:
- **Databricks Jobs API 2.1** — trigger, poll, and cancel job runs.
- **Azure Data Factory management API (2018-06-01)** — trigger, poll, and cancel pipeline runs.
- **Azure DevOps Pipelines API (7.0)** — trigger, poll (`GET`), and cancel (`PATCH`) pipeline runs.

Also used transitively by `msal`, `databricks-sdk`, and `databricks-sql-connector`.

**Why it was chosen.** `requests` is the de-facto standard Python HTTP library for REST API calls. The pipeline backends require simple JSON `POST`/`GET`/`PATCH` calls with Bearer token headers — well within `requests`' capabilities without needing an async client (`httpx`, `aiohttp`), since the pipeline status polling runs in a synchronous Streamlit context.

**Known trade-offs.** Synchronous only. If the pipeline control-plane APIs are slow to respond (>several seconds), the Streamlit process blocks. In practice, API calls are fast (<200 ms); the 3-second poll interval provides sufficient slack.

---

### `python-dotenv` — `>=1.0,<2` (installed: 1.2.2)

**What it does.** Reads a `.env` file from the project root and injects its key-value pairs as environment variables at process startup. Invoked in `app.py` and `scripts/nightly_sync.py` via `load_dotenv()`.

**Why it was chosen.** Local development requires setting ~10 environment variables (`DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `TENANT_ID`, etc.). Typing them into every terminal session is impractical; a `.env` file is the universal convention. In Kubernetes, the `.env` file is not used — env vars are injected from `ConfigMap` and `Secret` at pod level. `python-dotenv` is a no-op when no `.env` file is present, making it safe to include in the production image without risk.

**Known trade-offs.** None meaningful. It is a single-purpose, zero-dependency utility library.

---

## Development dependencies (`requirements-dev.txt`)

These are installed alongside runtime deps for local development and CI. They are **not** present in the production Docker image.

---

### `pytest` — `>=8.0` (installed: 9.0.3)

**What it does.** The test runner. Discovers and executes all test files under `tests/`, applies fixtures (`conftest.py`), and reports pass/fail. Used via `python -m pytest tests/ -q --ignore=...` for the standard suite (475 tests at time of writing) and separately for load and accessibility suites.

**Why it was chosen.** Pytest is the dominant Python test framework. Streamlit ships a first-party `AppTest` integration (`streamlit.testing.v1`) that runs natively inside pytest. The `mock.patch` pattern used extensively in the storage tests (`mock.patch("src.cms.get_cms_storage", return_value=FakeCMSStorage())`) is pytest-compatible without extra plugins.

---

### `pytest-cov` — `>=5.0` (installed: 7.1.0)

**What it does.** Coverage measurement plugin for pytest. Records which lines and branches are executed during the test run and reports coverage percentages. Run with `--cov=src` to scope coverage to the application source.

**Why it was chosen.** Standard companion to pytest. Required for CI coverage gates and for identifying untested paths — particularly important given the three-backend storage abstraction where Demo, DuckDB, and Fake implementations must all be exercised.

---

### `locust` — `>=2.29` (installed: 2.44.0)

**What it does.** Load-testing framework. Simulates concurrent users executing defined task sequences against the application. The load test file (`tests/load/locustfile.py`) defines two user classes:
- `DictionaryHTTPUser` — exercises the HTTP page-shell endpoint (`/_stcore/health`, `/`) to measure raw request throughput and p95 latency.
- `DuckDBQueryUser` — connects directly to the DuckDB cache file and executes parameterized search queries, measuring the actual query latency that a real user would experience (p95 target: <8 ms).

**Why it was chosen.** As noted in ADR 003, Streamlit's WebSocket interaction model means conventional HTTP load testers cannot exercise real user interactions — only page delivery. The `DuckDBQueryUser` approach fills this gap by targeting the performance-critical path (the DuckDB search query) directly. Locust was chosen over k6 or Gatling because its user classes are defined in Python, allowing the same SQL query strings used in `src/db/queries.py` to be reused in the load test without reimplementing them in a different language.

**Why it is dev-only.** Load tests require a live running app and a populated DuckDB file. They are excluded from the standard `pytest` run and wired up separately in CI against a staging environment.

---

### `faker` — `>=26.0` (installed: 40.15.0)

**What it does.** Generates realistic fake data — names, email addresses, company names, sentences, paragraphs. Used in `scripts/generate_test_data.py` to populate the local test dataset (`data/test_data.duckdb`) with 800 synthetic tables, ~15 columns each, realistic descriptions, steward emails, and permission rows.

**Why it was chosen.** The application's search and filter behaviour depends on having a realistic volume of data to query against. Hard-coding 800 table names would be impractical to maintain and would not stress-test full-text search properly. Faker produces varied, human-readable values that surface edge cases (long descriptions, unicode characters, special characters in names) that uniform synthetic data would miss.

**Why it is dev-only.** Only needed to generate the local test dataset once (or when the schema changes). Never required at runtime.

---

### `playwright` — `>=1.44` (installed: 1.59.0)

**What it does.** Browser automation library for Chromium, Firefox, and WebKit. Drives real browser sessions for tests that require JavaScript execution — specifically, the WCAG accessibility tests (`tests/test_wcag_axe.py`) and the navigation-render smoke tests (`tests/test_nav_render.py`). Requires a separate browser binary installation: `playwright install chromium`.

**Why it was chosen.** Streamlit's `AppTest` runs tests by simulating Streamlit's execution model in Python, without a real browser. WCAG compliance can only be measured against a rendered DOM — axe-core must evaluate the actual HTML, CSS, and JavaScript that the browser produces. Playwright is the maintained, officially supported tool for this in the Python ecosystem and is the dependency required by `axe-playwright-python`.

**Why it is dev-only.** Requires a live running app and browser binaries (~200 MB download). Excluded from the standard `pytest` run and run separately in CI.

---

### `axe-playwright-python` — `>=0.1.3` (installed: 0.1.7)

**What it does.** Wraps the `axe-core` JavaScript accessibility engine for use from Python via Playwright. In `tests/test_wcag_axe.py`, it navigates to each page of the running app, injects `axe-core` into the page, runs the WCAG 2.0 Level AA ruleset, and asserts zero new violations beyond two known, accepted Streamlit framework violations.

**Why it was chosen.** WCAG 2.0 Level AA compliance is a non-functional requirement (F11). Accessibility cannot be reliably verified by reading source code — it requires the rendered DOM. `axe-core` is the industry-standard engine (used by Deque, included in browser DevTools, and referenced by WCAG tooling guides). `axe-playwright-python` is the minimal wrapper that brings it into the Python + Playwright test stack.

**Why it is dev-only.** Same constraints as `playwright` — requires a live app and browser binaries.

---

### `python-pptx` — `>=1.0` (installed: 1.0.2)

**What it does.** Creates and modifies PowerPoint `.pptx` files programmatically. Used in `scripts/build_deck.py` and `scripts/generate_reports.py` to produce slide-deck reports from catalog health metrics (documentation coverage percentages, undocumented table counts, steward activity).

**Why it was chosen.** Stakeholder reporting is a recurring operational task. Generating slide decks from live data programmatically eliminates manual copy-paste from the health dashboard into a presentation. `python-pptx` is the only mature, actively maintained Python library for `.pptx` generation.

**Why it is dev-only.** Report generation is a script-level operation run on demand by operators, not a runtime application feature. Including it in the production image would add unnecessary size.

---

## Python version requirement

The application requires **Python 3.11 or later**. The `datetime.UTC` singleton (introduced in Python 3.11) is used in `src/sync/daemon.py` and several test files. Running with Python 3.9 or 3.10 raises `ImportError: cannot import name 'UTC' from 'datetime'` at collection time.

The production Docker image pins to a Python 3.11 base image. Local development must invoke the correct interpreter explicitly:

```bash
python3.11 -m pytest tests/ -q \
  --ignore=tests/test_load_smoke.py \
  --ignore=tests/test_wcag_axe.py \
  --ignore=tests/test_nav_render.py
```

---

## Version pinning rationale

Runtime dependencies use `>=x.y,<next-major`. The comment on each line records the last-known-good version:

```text
streamlit>=1.50,<2   # 1.56.0
duckdb>=1.0,<2       # 1.5.2
```

**Why `<next-major` and not a pinned exact version.** Exact pins (`==1.57.0`) cause `pip` conflicts when transitive dependencies update. Compatible ranges allow minor and patch updates — which typically carry bug fixes and security patches — while blocking major-version jumps that may carry breaking API changes. Each time the installed version drifts beyond the comment, the comment should be updated and the test suite re-run to confirm compatibility.

**Dev dependencies use only a lower bound** (`>=x.y`) because they never ship to production and the risk of a minor-version regression is low relative to the cost of keeping them pinned.
