"""
Locust load test for Business Data Dictionary.

Two user classes target different layers:

  DictionaryHTTPUser  — page delivery layer (Streamlit HTTP shell)
  DuckDBQueryUser     — query layer (the actual app bottleneck: DuckDB reads)

The HTTP tests confirm the server stays up; the DuckDB tests reflect real
user actions (search, table detail, export dictionary, related tables).

NOTE: Streamlit's interactive features (button clicks, widget state) are
driven over WebSocket using binary protobuf. Those cannot be exercised with
HTTP GET requests. Use Playwright for full end-to-end interaction testing.
The DuckDBQueryUser here directly exercises the same SQL the app runs,
which is the real performance-sensitive path.

Modes
-----
Full run — both user classes, 300 users:
    locust -f tests/load/locustfile.py --headless -u 300 -r 10 --run-time 2m \\
        --host http://localhost:8501

HTTP only (page-delivery layer):
    locust -f tests/load/locustfile.py --headless -u 300 -r 10 --run-time 2m \\
        --host http://localhost:8501 --tags http

DuckDB query layer only:
    locust -f tests/load/locustfile.py --headless -u 50 -r 5 --run-time 2m \\
        --host http://localhost:8501 --tags duckdb

Smoke test (quick sanity, 10 users, HTTP only):
    locust -f tests/load/locustfile.py --headless -u 10 -r 2 --run-time 30s \\
        --host http://localhost:8501 --tags smoke

With CSV + HTML output:
    locust -f tests/load/locustfile.py --headless -u 300 -r 10 --run-time 2m \\
        --host http://localhost:8501 \\
        --csv tests/load/results/run --html tests/load/results/report.html

Requirements:
    ENABLE_MOCK_AUTH=true ENVIRONMENT=development must be set on the target app.
    DUCKDB_PATH must point to a valid DuckDB file (data/test_data.duckdb).
    Install: pip install --prefer-binary locust
"""
from __future__ import annotations

import csv
import io
import os
import random
import time
import shutil
import tempfile
import duckdb
from locust import HttpUser, task, between, events, User, tag

# ── Bootstrap: load real table names from the test dataset ───────────────────

_DUCKDB_PATH = os.getenv("DUCKDB_PATH") or "data/test_data.duckdb"
_USER_DATA_PATH = (
    _DUCKDB_PATH.replace(".duckdb", "_user_data.duckdb")
    if ".duckdb" in _DUCKDB_PATH
    else _DUCKDB_PATH + "_user_data.duckdb"
)

# ── Lock-free access: use a temporary copy of the database ──────────────────
# This avoids "IO Error: Could not set lock" when the app is running.
_WORKING_DB = tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False).name
if os.path.exists(_DUCKDB_PATH):
    shutil.copy2(_DUCKDB_PATH, _WORKING_DB)
    print(f"[locust] Created working copy: {_WORKING_DB}")
else:
    print(f"[locust] WARNING: {_DUCKDB_PATH} not found, DuckDB queries will fail")

# Ensure temp file is cleaned up on exit
import atexit
def _cleanup():
    try: os.unlink(_WORKING_DB)
    except Exception: pass
atexit.register(_cleanup)

# Department group IDs used by mock auth (mirrors generate_test_data.py)
_DEPT_GROUPS = {
    "finance":  ["finance_group", "all_employees"],
    "research": ["research_group", "all_employees"],
    "hr":       ["hr_group", "all_employees"],
    "it":       ["it_group", "all_employees"],
    "admin":    ["finance_group", "research_group", "hr_group", "it_group", "all_employees"],
}

# Realistic search terms across all four department vocabularies
_SEARCH_TERMS = [
    # broad (high result count)
    "id", "date", "status", "name", "amount", "type", "code",
    # medium
    "budget", "employee", "invoice", "protocol", "grant", "contract",
    "publication", "system", "audit", "report", "pipeline",
    # narrow (few or zero results — tests fast-path)
    "xyzzy_no_match", "subaward", "reagent", "postdoc", "firewall",
]

_CATALOG = "data_governance"
_SCHEMA = "dictionary_cache"  # schema used by generate_test_data.py

# ── Global connection to be shared by all users ──────────────────────────────
# DuckDB allows sharing a connection object across threads if using cursors.
try:
    _GLOBAL_CON = duckdb.connect(":memory:")
    safe_working_db = _WORKING_DB.replace("'", "''")
    _GLOBAL_CON.execute(f"ATTACH '{safe_working_db}' AS {_CATALOG} (READ_ONLY)")
    # Attach a private in-memory DB as 'user_data' for overrides fallback
    _GLOBAL_CON.execute("ATTACH ':memory:' AS user_data")
    _GLOBAL_CON.execute("""
        CREATE TABLE user_data.business_name_overrides (
            table_full_name VARCHAR,
            column_name     VARCHAR,
            business_name   VARCHAR,
            definition      VARCHAR,
            edited_by       VARCHAR,
            edited_at       TIMESTAMP,
            PRIMARY KEY (table_full_name, column_name)
        )
    """)
except Exception as exc:
    print(f"[locust] FATAL: could not initialize global DuckDB connection: {exc}")
    _GLOBAL_CON = None


def _open_con(read_only: bool = True, attach_user_data: bool = True) -> duckdb.DuckDBPyConnection:
    """Return a thread-local cursor from the global connection."""
    if _GLOBAL_CON is None:
        return None
    try:
        # Each thread (Locust user) gets its own cursor
        con = _GLOBAL_CON.cursor()
        con.execute(f"USE {_CATALOG}.{_SCHEMA}")
        return con
    except Exception as exc:
        print(f"[locust] ERROR: could not create cursor: {exc}")
        return None



def _load_table_names() -> list[str]:
    """Read all table full_names from the dataset at startup."""
    try:
        # Use the global connection to avoid lock contention
        con = _open_con(attach_user_data=False)
        if con is None: return ["research_org.finance.invoices"]
        rows = con.execute("SELECT full_name FROM tables_metadata").fetchall()
        # DO NOT close the connection, just let the cursor go out of scope
        return [r[0] for r in rows]
    except Exception as exc:
        print(f"[locust] WARNING: could not load table names from {_DUCKDB_PATH}: {exc}")
        return ["research_org.finance.invoices", "research_org.hr.employees"]


_ALL_TABLES: list[str] = _load_table_names()
print(f"[locust] Loaded {len(_ALL_TABLES)} table names from {_DUCKDB_PATH}")


# ── DuckDB query helpers (mirror the actual SQL in app.py) ───────────────────

# Tables are referenced without schema prefix — search_path is set to
# dictionary_cache on every connection via _open_con().
# Positional params use ? with a list (DuckDB Python API).

def _search_sql(term: str, groups: list[str]) -> tuple[str, list]:
    """Mirror src.db.queries.search_all_metadata.

    Includes the LEFT JOINs the production query has (data_quality_cache and
    business_name_overrides) so the load test exercises the same plan
    Databricks/DuckDB will execute in production. Without these joins the
    test underestimates query cost.
    """
    ph = ", ".join("?" for _ in groups)
    like = f"%{term}%"
    params = [like, like, *groups, like, like, like, like, *groups]
    sql = f"""
        SELECT DISTINCT m.full_name, m.table_name, 'Table' AS match_type
        FROM tables_metadata m
        JOIN permissions_cache p ON m.full_name = p.table_full_name
        LEFT JOIN data_quality_cache dq ON m.full_name = dq.table_full_name
        WHERE (m.table_name LIKE ? OR m.comment LIKE ?)
          AND (p.principal IN ({ph}) OR p.principal = 'SELECT_ALL_USERS')

        UNION ALL

        SELECT DISTINCT c.table_full_name AS full_name,
               COALESCE(o.business_name, c.column_name) AS table_name,
               'Column' AS match_type
        FROM columns_metadata c
        JOIN permissions_cache p ON c.table_full_name = p.table_full_name
        JOIN tables_metadata t ON c.table_full_name = t.full_name
        LEFT JOIN data_quality_cache dq ON c.table_full_name = dq.table_full_name
        LEFT JOIN user_data.business_name_overrides o
               ON o.table_full_name = c.table_full_name AND o.column_name = c.column_name
        WHERE (
            c.column_name LIKE ? OR c.comment LIKE ?
            OR o.business_name LIKE ? OR o.definition LIKE ?
          )
          AND (p.principal IN ({ph}) OR p.principal = 'SELECT_ALL_USERS')

        LIMIT 50
    """
    return sql, params


def _columns_sql(table_full_name: str) -> tuple[str, list]:
    """Mirror the columns fetch in the table detail view."""
    sql = """
        SELECT column_name, data_type, comment
        FROM columns_metadata
        WHERE table_full_name = ?
        ORDER BY column_name
    """
    return sql, [table_full_name]


def _permissions_sql(table_full_name: str) -> tuple[str, list]:
    sql = """
        SELECT DISTINCT principal, privilege
        FROM permissions_cache
        WHERE table_full_name = ?
        ORDER BY principal
    """
    return sql, [table_full_name]


def _related_tables_sql(table_full_name: str, schema_name: str, catalog_name: str, groups: list[str]) -> tuple[str, list]:
    """Mirror the related-tables UNION query from app.py (the most expensive query)."""
    ph = ", ".join("?" for _ in groups)
    params = [catalog_name, schema_name, table_full_name, *groups,
              table_full_name, table_full_name, *groups]
    sql = f"""
        SELECT t.full_name, t.table_name, 'Same schema' AS relationship
        FROM tables_metadata t
        JOIN permissions_cache p ON t.full_name = p.table_full_name
        WHERE t.catalog_name = ?
          AND t.schema_name  = ?
          AND t.full_name   != ?
          AND (p.principal IN ({ph}) OR p.principal = 'SELECT_ALL_USERS')

        UNION

        SELECT DISTINCT t.full_name, t.table_name, 'Shared column' AS relationship
        FROM columns_metadata c1
        JOIN columns_metadata c2 ON c1.column_name = c2.column_name
        JOIN tables_metadata  t  ON c2.table_full_name = t.full_name
        JOIN permissions_cache p  ON t.full_name = p.table_full_name
        WHERE c1.table_full_name = ?
          AND c2.table_full_name != ?
          AND (p.principal IN ({ph}) OR p.principal = 'SELECT_ALL_USERS')
        LIMIT 12
    """
    return sql, params


# ── DuckDBQueryUser ───────────────────────────────────────────────────────────

@tag("duckdb")
class DuckDBQueryUser(User):
    """
    Fires the actual SQL queries the app executes, measured as Locust requests.

    Each virtual user holds its own read-only DuckDB connection (mirrors
    Streamlit's per-session connection pattern). Results are reported via
    events.request.fire() so they appear in Locust stats alongside HTTP tasks.
    """

    wait_time = between(1, 4)

    # Pick a random department so users have realistic permission scopes
    _dept: str = "finance"
    _groups: list[str] = []
    _con: duckdb.DuckDBPyConnection | None = None

    def on_start(self):
        self._dept = random.choice(list(_DEPT_GROUPS.keys()))
        self._groups = _DEPT_GROUPS[self._dept]
        try:
            self._con = _open_con()
        except Exception as exc:
            print(f"[DuckDBQueryUser] Could not open DuckDB: {exc}")
            self._con = None

    def on_stop(self):
        if self._con:
            try:
                self._con.close()
            except Exception:
                pass

    def _run_query(self, name: str, sql: str, params: list):
        """Execute a DuckDB query and report timing to Locust."""
        if not self._con:
            # Report as failure if connection is missing so we see it in stats
            events.request.fire(
                request_type="DuckDB",
                name=name,
                response_time=0,
                response_length=0,
                exception=RuntimeError("DuckDB connection not initialized"),
            )
            return
        start = time.perf_counter()
        exc_instance = None
        row_count = 0
        try:
            result = self._con.execute(sql, params).fetchall()
            row_count = len(result)
        except Exception as e:
            exc_instance = e
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        events.request.fire(
            request_type="DuckDB",
            name=name,
            response_time=elapsed_ms,
            response_length=row_count,
            exception=exc_instance,
        )

    @task(40)
    def search_broad(self):
        """High-traffic search: common terms return many results."""
        term = random.choice(_SEARCH_TERMS[:7])   # broad terms
        sql, params = _search_sql(term, self._groups)
        self._run_query(f"query: search ({self._dept})", sql, params)

    @task(15)
    def search_narrow(self):
        """Low-result or zero-result search — tests fast-path exit."""
        term = random.choice(_SEARCH_TERMS[7:])   # narrow / no-match terms
        sql, params = _search_sql(term, self._groups)
        self._run_query(f"query: search narrow ({self._dept})", sql, params)

    @task(25)
    def fetch_columns(self):
        """Table detail view: fetch all columns for a random table."""
        table = random.choice(_ALL_TABLES)
        sql, params = _columns_sql(table)
        self._run_query("query: columns fetch", sql, params)

    @task(10)
    def export_dictionary(self):
        """
        Export dictionary: fetch columns then serialize to CSV.
        Mirrors export_schema_to_csv() — measures both query + serialization.
        """
        if not self._con:
            events.request.fire(
                request_type="DuckDB",
                name="query: export dictionary (CSV)",
                response_time=0,
                response_length=0,
                exception=RuntimeError("DuckDB connection not initialized"),
            )
            return
        table = random.choice(_ALL_TABLES)
        sql, params = _columns_sql(table)
        start = time.perf_counter()
        exc_instance = None
        byte_count = 0
        try:
            rows = self._con.execute(sql, params).fetchall()  # params is a list
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(["Column Name", "Business Name", "Data Type", "System Description", "Business Definition"])
            for row in rows:
                col_name, data_type, comment = row[0], row[1], row[2] or ""
                writer.writerow([col_name, "", data_type, comment, ""])
            byte_count = len(out.getvalue().encode())
        except Exception as e:
            exc_instance = e
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        events.request.fire(
            request_type="DuckDB",
            name="query: export dictionary (CSV)",
            response_time=elapsed_ms,
            response_length=byte_count,
            exception=exc_instance,
        )

    @task(5)
    def fetch_permissions(self):
        """Permission panel: who has access to a random table."""
        table = random.choice(_ALL_TABLES)
        sql, params = _permissions_sql(table)
        self._run_query("query: permissions fetch", sql, params)

    @task(5)
    def fetch_related_tables(self):
        """
        Related tables panel — the most expensive query (two-level JOIN on columns).
        Weighted low because it appears only when a user opens a detail panel.
        """
        if not self._con:
            events.request.fire(
                request_type="DuckDB",
                name="query: related tables",
                response_time=0,
                response_length=0,
                exception=RuntimeError("DuckDB connection not initialized"),
            )
            return
        table = random.choice(_ALL_TABLES)
        parts = table.split(".")           # catalog.schema.table
        catalog, schema = parts[0], parts[1]
        sql, params = _related_tables_sql(table, schema, catalog, self._groups)
        self._run_query(f"query: related tables ({self._dept})", sql, params)


# ── DictionaryHTTPUser ────────────────────────────────────────────────────────

@tag("http")
class DictionaryHTTPUser(HttpUser):
    """
    Measures Streamlit's HTTP page-delivery layer.

    What this tests: static page shell, session cookie issuance, and Streamlit's
    built-in caching headers. It does NOT trigger DuckDB queries — those happen
    over WebSocket after the page loads. Use DuckDBQueryUser for query load.
    """

    wait_time = between(1, 3)

    def on_start(self):
        """Authenticate via mock login."""
        dept = random.choice(["finance", "research", "hr", "it"])
        with self.client.get(
            f"/?mock_login=true&mock_dept={dept}",
            catch_response=True,
            name="auth: mock login",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Mock login failed: {resp.status_code}")

    @tag("smoke")
    @task(40)
    def search_tab(self):
        self.client.get("/?tab=search", name="tab: search")

    @tag("smoke")
    @task(20)
    def catalog_tab(self):
        self.client.get("/?tab=catalog", name="tab: catalog")

    @tag("smoke")
    @task(15)
    def glossary_tab(self):
        self.client.get("/?tab=glossary", name="tab: glossary")

    @task(10)
    def discovery_tab(self):
        self.client.get("/?tab=discovery", name="tab: discovery")

    @task(10)
    def health_tab(self):
        self.client.get("/?tab=health", name="tab: health")

    @task(5)
    def admin_tab(self):
        self.client.get("/?tab=admin", name="tab: admin")

    @task(5)
    def pipelines_tab(self):
        """Pipeline runner tab — visible to PIPELINE_GROUPS members and admins."""
        self.client.get("/?tab=pipelines", name="tab: pipelines")

    @task(10)
    def detail_drilldown(self):
        """Open a real table — exercises the search-tab page-shell path that
        the table-detail panel renders inside. The actual table-selection
        happens via session_state (``dd_search_override`` + ``dd_nav_select``)
        and isn't reachable over HTTP, so we only measure the page shell here.
        Use a Playwright-driven test for end-to-end detail measurement."""
        random.choice(_ALL_TABLES)  # keep the random pick to mirror real cardinality
        self.client.get("/?tab=search", name="tab: search (detail)")


# ── APIQueryUser ─────────────────────────────────────────────────────────────

_API_HOST = os.getenv("API_HOST", "http://localhost:8080")


@tag("api")
class APIQueryUser(HttpUser):
    """
    Exercises the FastAPI + MCP REST layer (port 8080 by default).

    Models realistic AI-assistant usage: mostly searches and table drilldowns,
    occasional list-all and lineage traversal. Each virtual user picks a random
    department on start and holds it for its lifetime — this exercises the
    permission-filtered query paths under different group scopes.

    Auth: requires the API server to run with ENABLE_MOCK_AUTH=true and
    ENVIRONMENT=development. Sends "Bearer mock-<dept>" tokens which the API
    accepts as synthetic identities without hitting Entra ID.

    Run API load only:
        API_HOST=http://localhost:8080 \\
        locust -f tests/load/locustfile.py --headless -u 50 -r 5 --run-time 60s \\
            --host http://localhost:8501 --tags api
    """

    host = _API_HOST
    wait_time = between(1, 4)

    _dept: str = "finance"
    _auth_header: dict = {}

    def on_start(self):
        self._dept = random.choice(list(_DEPT_GROUPS.keys()))
        self._auth_header = {"Authorization": f"Bearer mock-{self._dept}"}

    @task(40)
    def api_search(self):
        """Search — the primary AI-assistant entry point."""
        term = random.choice(_SEARCH_TERMS)
        self.client.get(
            f"/api/v1/search?q={term}",
            headers=self._auth_header,
            name=f"api: search ({self._dept})",
        )

    @task(30)
    def api_table_detail(self):
        """Table detail — drill into a specific table after a search."""
        table = random.choice(_ALL_TABLES)
        parts = table.split(".")
        if len(parts) != 3:
            return
        catalog, schema, tbl = parts
        self.client.get(
            f"/api/v1/tables/{catalog}/{schema}/{tbl}",
            headers=self._auth_header,
            name=f"api: table detail ({self._dept})",
        )

    @task(15)
    def api_list_tables(self):
        """List all authorized tables — used when browsing or building context."""
        self.client.get(
            "/api/v1/tables",
            headers=self._auth_header,
            name=f"api: list tables ({self._dept})",
        )

    @task(10)
    def api_lineage(self):
        """Lineage traversal — occasional, only when an AI needs data provenance."""
        table = random.choice(_ALL_TABLES)
        parts = table.split(".")
        if len(parts) != 3:
            return
        catalog, schema, tbl = parts
        depth = random.choice([1, 2])
        self.client.get(
            f"/api/v1/lineage/{catalog}/{schema}/{tbl}?depth={depth}",
            headers=self._auth_header,
            name="api: lineage",
        )

    @task(5)
    def api_health(self):
        """Liveness probe — no auth, very cheap."""
        self.client.get("/health", name="api: health")


# ── Benchmark summary ─────────────────────────────────────────────────────────

@events.quitting.add_listener
def print_benchmark_summary(environment, **kwargs):
    stats = environment.runner.stats
    agg = stats.total
    if agg.num_requests == 0:
        return

    duration = max(
        (stats.last_request_timestamp or 0) - (stats.start_time or 0), 1
    )

    print("\n" + "=" * 64)
    print("BENCHMARK SUMMARY")
    print("=" * 64)
    print(f"  Total requests : {agg.num_requests:,}")
    print(f"  Failures       : {agg.num_failures:,} ({agg.num_failures / agg.num_requests:.2%})")
    print(f"  Throughput     : {agg.num_requests / duration:.1f} req/s")
    print(f"  Latency p50    : {agg.get_response_time_percentile(0.50):.0f} ms")
    print(f"  Latency p95    : {agg.get_response_time_percentile(0.95):.0f} ms")
    print(f"  Latency p99    : {agg.get_response_time_percentile(0.99):.0f} ms")
    print(f"  Max latency    : {agg.max_response_time:.0f} ms")
    print("=" * 64)

    # Per-type breakdown
    http_reqs = duckdb_reqs = 0
    for entry in stats.entries.values():
        if entry.method == "DuckDB":
            duckdb_reqs += entry.num_requests
        else:
            http_reqs += entry.num_requests
    if http_reqs or duckdb_reqs:
        print(f"\n  HTTP requests  : {http_reqs:,}")
        print(f"  DuckDB queries : {duckdb_reqs:,}")
        print("=" * 64 + "\n")

    if stats.errors:
        print("\nError report")
        print(f"{'# occurrences':<18} Error")
        print("-" * 18 + "|" + "-" * 64)
        for error_key, error in stats.errors.items():
            print(f"{error.occurrences:<18} {error_key}")
        environment.process_exit_code = 1
