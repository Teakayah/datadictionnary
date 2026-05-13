# Dependency reference

All dependencies for the Data Dictionary application. Runtime dependencies are pinned to compatible ranges (`>=x.y,<next-major`) so a clean install always produces the same tested behaviour. Dev-only dependencies are unpinned beyond a lower bound — they do not ship in the production image.

---

## Runtime dependencies (`requirements.txt`)

These are installed in the production Docker image and required at runtime.

### Application framework

| Package | Range | Installed | Role |
|---|---|---|---|
| `streamlit` | `>=1.50,<2` | 1.57.0 | Web UI framework. Renders all pages, manages session state, handles HTTP. The entire frontend is Python — no separate JS build step. |
| `streamlit-autorefresh` | `>=1.0,<2` | 1.0.1 | Triggers periodic Streamlit reruns without blocking the script. Used in `src/ui/cards/pipelines.py` to poll live pipeline run status every 3 s while a run is active. |
| `streamlit-js-eval` | `>=1.0,<2` | 1.0.0 | Evaluates arbitrary JavaScript expressions from within a Streamlit app. Used to read `window.innerHeight` for responsive lineage graph sizing. |

### Data layer

| Package | Range | Installed | Role |
|---|---|---|---|
| `duckdb` | `>=1.0,<2` | 1.5.2 | Embedded, in-process columnar analytical database. Serves all search and detail queries from the local cache file (`dict.duckdb`). Zero server required — single binary wheel with no system dependencies. p95 search latency <8 ms on the 800-table reference dataset. |
| `pandas` | `>=2.2,<3` | 2.3.3 | DataFrame library. Used to process query results from DuckDB and Databricks SQL Warehouse, build health-dashboard metrics, and manage lineage graph data. Vectorized operations used throughout; `iterrows()` replaced with `itertuples()` for performance. |

### Databricks integration

| Package | Range | Installed | Role |
|---|---|---|---|
| `databricks-sql-connector` | `>=4.2,<5` | 4.2.6 | Official Databricks SQL Warehouse connector. Used by the **nightly sync job** to run `TRUNCATE` + `INSERT` and `ALTER TABLE … COMMENT` statements against the production SQL Warehouse. Not used by the Streamlit pods (they query DuckDB locally). |
| `databricks-sdk` | `>=0.100,<1` | 0.108.0 | Official Databricks Python SDK (`WorkspaceClient`). Used by the nightly sync job to crawl the Unity Catalog hierarchy (catalogs → schemas → tables → columns → grants → lineage) via the Unity Catalog REST API. |

### Authentication

| Package | Range | Installed | Role |
|---|---|---|---|
| `msal` | `>=1.30,<2` | 1.36.0 | Microsoft Authentication Library. Drives the full OIDC / OAuth 2.0 authorization-code flow against Microsoft Entra ID. Also used for client-credentials token acquisition (`ConfidentialClientApplication`) for pipeline service principals (ADF, ADO, Databricks Jobs). |

### HTTP client

| Package | Range | Installed | Role |
|---|---|---|---|
| `requests` | `>=2.32,<3` | 2.34.0 | Used directly in `src/pipelines.py` to call the Databricks Jobs API, Azure Data Factory management API, and Azure DevOps Pipelines API. Also used transitively by `msal`, `databricks-sdk`, and `databricks-sql-connector`. |

### Configuration

| Package | Range | Installed | Role |
|---|---|---|---|
| `python-dotenv` | `>=1.0,<2` | 1.2.2 | Loads environment variables from a `.env` file at startup. Used only in local development — Kubernetes injects env vars from `ConfigMap` and `Secret` at pod level. |

---

## Development dependencies (`requirements-dev.txt`)

Install alongside runtime deps for local development and CI:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

These are **not** present in the production Docker image.

### Test framework

| Package | Lower bound | Installed | Role |
|---|---|---|---|
| `pytest` | `>=8.0` | 9.0.3 | Test runner. Discovers and executes all tests under `tests/`. Run with `python -m pytest tests/ -q --ignore=tests/test_load_smoke.py --ignore=tests/test_wcag_axe.py --ignore=tests/test_nav_render.py`. |
| `pytest-cov` | `>=5.0` | 7.1.0 | Coverage reporting plugin for pytest. Measures line and branch coverage during test runs. |

### Load and accessibility testing

| Package | Lower bound | Installed | Role |
|---|---|---|---|
| `locust` | `>=2.29` | 2.44.0 | Load testing framework. Used in `tests/test_load_smoke.py` to simulate 300 concurrent users against a live app instance. Excluded from the standard `pytest` run — requires a running app. |
| `playwright` | `>=1.44` | 1.59.0 | Browser automation library (Chromium). Required by the WCAG accessibility tests and the navigation-render smoke tests. Install browser binaries separately with `playwright install chromium`. |
| `axe-playwright-python` | `>=0.1.3` | 0.1.7 | Wraps the `axe-core` accessibility engine for use with Playwright. Drives `tests/test_wcag_axe.py` — asserts WCAG 2.0 Level AA compliance on every rendered page. Excluded from the standard run — requires a live app and Playwright browsers. |

### Test data and reporting

| Package | Lower bound | Installed | Role |
|---|---|---|---|
| `faker` | `>=26.0` | 40.15.0 | Generates realistic fake data (names, emails, descriptions). Used in `scripts/generate_test_data.py` to produce the 800-table local test dataset (`data/test_data.duckdb`). |
| `python-pptx` | `>=1.0` | 1.0.2 | Creates and modifies PowerPoint `.pptx` files. Used by reporting scripts to produce slide-deck outputs from catalog health metrics. |

---

## Version pinning strategy

Runtime dependencies use `>=x.y,<next-major` ranges. The comment on each line records the last-known-good version used during development:

```text
streamlit>=1.50,<2   # 1.56.0
duckdb>=1.0,<2       # 1.5.2
```

This means:
- `pip install` always resolves to a compatible, tested minor version.
- Major version bumps (which may carry breaking API changes) require an explicit review and `requirements.txt` update.
- Dev dependencies use only a lower bound (`>=x.y`) — they never ship to production so the risk of a minor-version regression is low.

---

## Python version

The application targets **Python 3.11+**. The `datetime.UTC` constant (used in `src/sync/daemon.py` and tests) was introduced in Python 3.11 and is not available on 3.9 or 3.10. The production Docker image pins to a 3.11 base. Local development should use `python3.11` explicitly when running tests:

```bash
python3.11 -m pytest tests/ -q --ignore=tests/test_load_smoke.py \
                                --ignore=tests/test_wcag_axe.py \
                                --ignore=tests/test_nav_render.py
```

---

## Excluded from production image

The following dev packages are **not installed** in the Docker production image and must never be added to `requirements.txt`:

- `locust` — load-testing tool, not needed at runtime
- `playwright` / `axe-playwright-python` — browser automation, not needed at runtime
- `faker` — test data generator, not needed at runtime
- `python-pptx` — reporting tool, runtime usage is optional and currently only invoked by scripts
- `pytest` / `pytest-cov` — test framework, not needed at runtime
