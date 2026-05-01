# Tests

This directory contains the pytest suite and load test tooling for Business Data Dictionary.

---

## Running unit and integration tests

```bash
# From the repository root
python -m pytest --tb=short -q
```

For verbose output with full tracebacks:

```bash
python -m pytest -v
```

To run a single test file:

```bash
python -m pytest tests/test_duckdb_cache.py -v
```

To run tests matching a keyword:

```bash
python -m pytest -k "search" -v
```

There is no coverage gate enforced in CI yet. A `.coveragerc` is not present; add `--cov=app --cov-report=term-missing` to `pytest` if you want a coverage report.

---

## Test files

| File | What it covers |
|------|---------------|
| `test_app.py` | Auth flows, search rendering, table detail panel, design system CSS compliance |
| `test_admin.py` | `is_admin()` role check, nav visibility, admin page rendering, audit log display |
| `test_duckdb_cache.py` | `_to_duckdb_sql` dialect translation, `_DuckDBCursor`/`_DuckDBConn` adapter, `write_duckdb`, `_duckdb_available` |
| `test_navigation.py` | Tab routing, health dashboard, catalog browser, discovery feed |
| `test_sync_metadata.py` | `setup_cache_tables` DDL, `sync` orchestration, `fetch_lineage` parsing |
| `test_business_name_editor.py` | Business name override saving, loading, and display |
| `test_comments.py` | Comment creation, threading, email notification stubs |
| `test_language_toggle.py` | `t()` key lookup, locale switching, fallback to English |
| `test_accessibility.py` | WCAG-level accessibility checks via axe-core |
| `test_nav_render.py` | Navigation rendering across permission levels |
| `test_all_pages_no_errors.py` | Smoke test — all tabs render without Python exceptions |
| `test_load_smoke.py` | In-process DuckDB query latency smoke assertions |
| `test_wcag_axe.py` | Automated WCAG 2.1 AA audit via Playwright + axe |

---

## conftest.py — what is mocked and why

`tests/conftest.py` injects lightweight stubs into `sys.modules` before any test module is imported. This is necessary because `AppTest` runs `app.py` via `exec()` in a fresh module namespace — patching symbols inside `app.py` after the fact does not work for packages imported at module level.

### Stubs installed

**`databricks` / `databricks.sql`**
The real package would attempt to open a TCP connection to a Databricks SQL Warehouse. Tests run offline. The stub is a `MagicMock` chain that the `conftest.py` `get_db_cursor()` helper exposes, letting individual tests configure `cursor.fetchall_as_pandas.return_value` to return a specific `pd.DataFrame`.

**`msal`**
Used only in the production OIDC auth path. Tests run with `ENABLE_MOCK_AUTH=true`, so `msal` is never called. The stub prevents an `ImportError` in environments where the package is not installed.

**`dotenv`**
`load_dotenv()` is no-oped. Test environment variables are set directly in `conftest.py` via `os.environ.setdefault`.

### Environment flags set by conftest

```python
ENABLE_MOCK_AUTH=true
ENVIRONMENT=development
DEMO_DATA=true
```

These flags ensure the app starts in mock-auth + demo-data mode without any external service dependencies.

### The `sql_returns()` helper

```python
from tests.conftest import sql_returns
import pandas as pd

def test_something(reset_sql_mock):
    sql_returns(
        pd.DataFrame({"full_name": ["cat.schema.my_table"], "description": ["A table"]}),
    )
    # ... run AppTest, assert UI contains "my_table"
```

`sql_returns(*dataframes)` configures the mock cursor to return the given DataFrames in sequence, one per `fetchall_as_pandas()` call. Use it to simulate any query result without a real database.

---

## Regenerating the test dataset

The integration tests and load tests rely on a pre-generated DuckDB file. Regenerate it from a fixed seed to get a deterministic 800-table dataset:

```bash
python scripts/generate_test_data.py --seed 42 --out data/test_data.duckdb
```

Add `--with-data` to include sample row data (enables the data preview dialog in tests and manual exploration):

```bash
python scripts/generate_test_data.py --seed 42 --with-data --out data/test_data.duckdb
```

The generated file contains four departments (finance, research, hr, it), each with tables accessible to their department group and to the `all_employees_id` group. Public tables (marked `SELECT_ALL_USERS`) are visible to all authenticated users.

---

## Load tests

Load tests live in `tests/load/` and use [Locust](https://locust.io/). Install Locust:

```bash
pip install --prefer-binary locust
```

The target app must be running with:

```bash
ENABLE_MOCK_AUTH=true ENVIRONMENT=development DUCKDB_PATH=data/test_data.duckdb streamlit run app.py
```

### Run modes

**Full run — both user classes, 300 concurrent users, 2 minutes:**

```bash
locust -f tests/load/locustfile.py --headless -u 300 -r 10 --run-time 2m \
    --host http://localhost:8501
```

**HTTP layer only (page-shell delivery):**

```bash
locust -f tests/load/locustfile.py --headless -u 300 -r 10 --run-time 2m \
    --host http://localhost:8501 --tags http
```

**DuckDB query layer only (the actual performance-sensitive path):**

```bash
locust -f tests/load/locustfile.py --headless -u 50 -r 5 --run-time 2m \
    --host http://localhost:8501 --tags duckdb
```

**Smoke test (10 users, 30 seconds, HTTP only):**

```bash
locust -f tests/load/locustfile.py --headless -u 10 -r 2 --run-time 30s \
    --host http://localhost:8501 --tags smoke
```

**With CSV and HTML output:**

```bash
locust -f tests/load/locustfile.py --headless -u 300 -r 10 --run-time 2m \
    --host http://localhost:8501 \
    --csv tests/load/results/run --html tests/load/results/report.html
```

Note: Streamlit's interactive features (button clicks, widget state) are driven over a binary WebSocket protocol. HTTP GET requests can only exercise the page-shell. The `DuckDBQueryUser` class in `locustfile.py` directly runs the same SQL queries the app would execute, which is the real performance-sensitive path. Use Playwright for full end-to-end interaction testing.

### SLA targets

Performance targets are defined in `tests/load/sla.json`. The baseline was established from a 300-user, 2-minute run against the seed=42, 800-table dataset on 2026-04-29.

| Metric | p95 max | p99 max |
|--------|---------|---------|
| HTTP page delivery | 20 ms | 35 ms |
| DuckDB search (broad or narrow) | 8 ms | 15 ms |
| DuckDB simple queries (columns, permissions, CSV export) | 5 ms | 10 ms |
| DuckDB related-tables UNION JOIN | 15 ms | 20 ms |

A failure rate above 1% is also a SLA breach (the 1% tolerance covers transient auth-session setup failures in dev environments).
