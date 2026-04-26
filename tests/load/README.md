# Load Testing with Locust

This directory contains a load testing suite for the Business Data Dictionary app using [Locust](https://locust.io/).

## Prerequisites

- Python 3.9+
- The application must be running in development mode with mock authentication enabled.

## Installation

```bash
pip install --prefer-binary locust
```

> `--prefer-binary` avoids compiling `gevent` from source, which fails on some macOS setups.

## Configuration

Ensure the target application is running with the following environment variables:

```bash
export ENABLE_MOCK_AUTH=true
export ENVIRONMENT=development
# export DUCKDB_PATH=data/local.db  # recommended: use DuckDB for local load tests
```

Then start the app:

```bash
streamlit run app.py
```

## Running the Load Test

### Standard mode (300 users, 2 min)

```bash
locust -f tests/load/locustfile.py \
  --headless \
  -u 300 -r 10 \
  --run-time 2m \
  --host http://localhost:8501
```

### Benchmark mode — saves CSV results

Adds `--csv` output so results are written to `tests/load/results/`:

```bash
mkdir -p tests/load/results
locust -f tests/load/locustfile.py \
  --headless \
  -u 300 -r 10 \
  --run-time 2m \
  --host http://localhost:8501 \
  --csv tests/load/results/run \
  --html tests/load/results/report.html
```

This produces:
- `results/run_stats.csv` — per-endpoint request counts and latency
- `results/run_stats_history.csv` — time-series throughput
- `results/run_failures.csv` — failure log (empty on a clean run)
- `results/report.html` — full HTML report with charts

### Web UI mode (live monitoring)

```bash
locust -f tests/load/locustfile.py --host http://localhost:8501
```

Open [http://localhost:8089](http://localhost:8089) to configure and watch live.

### Smoke test (10 users, 30 sec)

Quick sanity check before a full run:

```bash
locust -f tests/load/locustfile.py \
  --headless \
  -u 10 -r 2 \
  --run-time 30s \
  --host http://localhost:8501
```

## Baseline benchmark — 2026-04-25

Measured locally against DuckDB backend with mock auth.

| Metric | Value |
|--------|-------|
| Users | 300 concurrent |
| Ramp-up | 10 users/sec (30 s to full load) |
| Duration | 2 minutes |
| Total requests | 15,831 |
| **Error rate** | **0.00%** |
| **Throughput** | **134.8 req/s** |
| **p50 latency** | **3 ms** |
| **p95 latency** | **10 ms** |
| **p99 latency** | **17 ms** |
| Max latency | 51 ms |

Per-endpoint latency (p50 / p95 / p99):

| Endpoint | Requests | p50 | p95 | p99 |
|----------|----------|-----|-----|-----|
| `/?mock_login=true` (auth) | 300 | 14 ms | 21 ms | 25 ms |
| `/?tab=search` | 5,684 | 3 ms | 9 ms | 14 ms |
| `/?tab=catalog` | 2,796 | 3 ms | 9 ms | 15 ms |
| `/?tab=glossary` | 2,109 | 3 ms | 10 ms | 15 ms |
| `/?tab=health` | 1,485 | 3 ms | 10 ms | 16 ms |
| `/?tab=discovery` | 1,418 | 3 ms | 9 ms | 16 ms |
| `/?tab=admin` | 682 | 3 ms | 9 ms | 16 ms |
| `/?tab=search&table=…` (detail) | 1,357 | 3 ms | 9 ms | 15 ms |

## Notes

- **Mock auth**: uses `?mock_login=true` — requires `ENABLE_MOCK_AUTH=true` and `ENVIRONMENT=development` on the server.
- **Backend**: DuckDB is recommended for local load tests. Databricks SQL Warehouse will incur real query costs and is slower to respond at scale.
- **WebSockets**: this suite tests HTTP page delivery only. Streamlit's actual state updates travel over WebSocket at `/_stcore/stream`. See the commented-out `WebSocketUser` stub in `locustfile.py` for a starting point on WS-level load testing.
- **CI usage**: run the smoke test (10 users, 30 s) as a post-deploy gate; reserve the full 300-user run for manual perf audits.
