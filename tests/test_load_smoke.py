"""
Load smoke test — 50 concurrent users for 60 seconds.

Asserts that p95 / p99 latencies do not exceed the baselines recorded during
the 300-user reference run (tests/load/sla.json).  Failures at lower
concurrency than the reference run indicate a genuine regression.

Run:
    pytest tests/test_load_smoke.py -v               # requires running app
    pytest tests/test_load_smoke.py -v -m integration

The test is skipped automatically when the Streamlit server is not reachable.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import requests

APP_URL    = os.getenv("LOAD_TEST_HOST", "http://localhost:8501")
LOCUST_F   = Path(__file__).parent / "load" / "locustfile.py"
SLA_FILE   = Path(__file__).parent / "load" / "sla.json"

USERS      = 50
SPAWN_RATE = 5
DURATION   = "60s"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=False)
def require_server():
    """Skip entire module if the Streamlit app is not reachable."""
    try:
        r = requests.get(f"{APP_URL}/healthz", timeout=3)
        if r.status_code != 200:
            pytest.skip(f"App not healthy at {APP_URL} (status {r.status_code})")
    except requests.ConnectionError:
        pytest.skip(f"App not reachable at {APP_URL}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_locust(out_dir: str) -> dict[str, dict]:
    """Run locust headlessly and return parsed per-endpoint stats."""
    cmd = [
        sys.executable, "-m", "locust",
        "-f", str(LOCUST_F),
        "--headless",
        "-u", str(USERS),
        "-r", str(SPAWN_RATE),
        "--run-time", DURATION,
        "--host", APP_URL,
        "--csv", os.path.join(out_dir, "smoke"),
        "--loglevel", "WARNING",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode not in (0, 1):   # locust exits 1 on threshold failures
        raise RuntimeError(f"Locust exited {result.returncode}:\n{result.stderr[-2000:]}")

    stats: dict[str, dict] = {}
    stats_file = os.path.join(out_dir, "smoke_stats.csv")
    with open(stats_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["Type"], row["Name"])
            stats[key] = {k: _num(v) for k, v in row.items()}
    return stats


def _num(v: str) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _load_sla() -> dict:
    with open(SLA_FILE) as f:
        return json.load(f)


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestLoadSmoke:

    @pytest.fixture(autouse=True)
    def _server(self, require_server):
        pass

    def setup_method(self):
        self._sla = _load_sla()
        self._tmpdir = tempfile.mkdtemp()
        self._stats = _run_locust(self._tmpdir)

    # ── Zero failures ─────────────────────────────────────────────────────────

    def test_zero_failures(self):
        """No request must fail under 50 concurrent users."""
        agg = self._stats.get(("", "Aggregated"), {})
        total  = agg.get("Request Count", 0)
        failed = agg.get("Failure Count", 0)
        if total == 0:
            pytest.fail("No requests recorded — locust may not have started properly")
        rate = failed / total * 100
        assert rate <= self._sla["failure_rate_max_pct"], (
            f"Failure rate {rate:.2f}% exceeds SLA {self._sla['failure_rate_max_pct']}% "
            f"({int(failed)} failures out of {int(total)} requests)"
        )

    # ── HTTP page-delivery SLAs ───────────────────────────────────────────────

    @pytest.mark.parametrize("endpoint", [
        "tab: search", "tab: catalog", "tab: glossary",
        "tab: discovery", "tab: health", "tab: admin",
        "tab: search (detail)",
    ])
    def test_http_p95(self, endpoint):
        row = self._stats.get(("GET", endpoint))
        if row is None:
            pytest.skip(f"No data for {endpoint!r} (too few requests in {DURATION})")
        p95 = row.get("95%", 0)
        limit = self._sla["http"]["p95_max_ms"]
        assert p95 <= limit, (
            f"{endpoint} p95={p95:.0f}ms exceeds 300-user baseline {limit}ms"
        )

    @pytest.mark.parametrize("endpoint", [
        "tab: search", "tab: catalog", "tab: glossary",
        "tab: discovery", "tab: health",
    ])
    def test_http_p99(self, endpoint):
        row = self._stats.get(("GET", endpoint))
        if row is None:
            pytest.skip(f"No data for {endpoint!r}")
        p99 = row.get("99%", 0)
        limit = self._sla["http"]["p99_max_ms"]
        assert p99 <= limit, (
            f"{endpoint} p99={p99:.0f}ms exceeds 300-user baseline {limit}ms"
        )

    # ── DuckDB search SLAs ────────────────────────────────────────────────────

    @pytest.mark.parametrize("dept", ["finance", "research", "hr", "it", "admin"])
    def test_duckdb_search_p95(self, dept):
        row = self._stats.get(("DuckDB", f"query: search ({dept})"))
        if row is None:
            pytest.skip(f"No DuckDB search data for dept={dept!r}")
        p95 = row.get("95%", 0)
        limit = self._sla["duckdb_search"]["p95_max_ms"]
        assert p95 <= limit, (
            f"DuckDB search ({dept}) p95={p95:.0f}ms exceeds baseline {limit}ms"
        )

    def test_duckdb_search_p99_aggregate(self):
        """p99 across all DuckDB search tasks must stay within baseline."""
        limit = self._sla["duckdb_search"]["p99_max_ms"]
        for key, row in self._stats.items():
            if key[0] == "DuckDB" and "search" in key[1]:
                p99 = row.get("99%", 0)
                assert p99 <= limit, (
                    f"{key[1]} p99={p99:.0f}ms exceeds 300-user baseline {limit}ms"
                )

    # ── DuckDB simple queries (columns / permissions / export) ────────────────

    @pytest.mark.parametrize("endpoint", [
        "query: columns fetch",
        "query: permissions fetch",
        "query: export dictionary (CSV)",
    ])
    def test_duckdb_simple_p95(self, endpoint):
        row = self._stats.get(("DuckDB", endpoint))
        if row is None:
            pytest.skip(f"No data for {endpoint!r}")
        p95 = row.get("95%", 0)
        limit = self._sla["duckdb_simple"]["p95_max_ms"]
        assert p95 <= limit, (
            f"{endpoint} p95={p95:.0f}ms exceeds baseline {limit}ms"
        )

    # ── DuckDB related-tables (expensive JOIN) ────────────────────────────────

    def test_duckdb_related_tables_p95(self):
        limit = self._sla["duckdb_related"]["p95_max_ms"]
        tested = 0
        for key, row in self._stats.items():
            if key[0] == "DuckDB" and "related tables" in key[1]:
                p95 = row.get("95%", 0)
                assert p95 <= limit, (
                    f"{key[1]} p95={p95:.0f}ms exceeds baseline {limit}ms"
                )
                tested += 1
        if tested == 0:
            pytest.skip("No related-tables data recorded in this run")

    def test_duckdb_related_tables_p99(self):
        limit = self._sla["duckdb_related"]["p99_max_ms"]
        for key, row in self._stats.items():
            if key[0] == "DuckDB" and "related tables" in key[1]:
                p99 = row.get("99%", 0)
                assert p99 <= limit, (
                    f"{key[1]} p99={p99:.0f}ms exceeds baseline {limit}ms"
                )

    # ── Minimum throughput ────────────────────────────────────────────────────

    def test_minimum_requests_recorded(self):
        """Sanity: the run must have generated a meaningful number of requests."""
        agg = self._stats.get(("", "Aggregated"), {})
        total = agg.get("Request Count", 0)
        assert total >= 200, (
            f"Only {int(total)} requests recorded — locust may not have ramped up correctly"
        )
