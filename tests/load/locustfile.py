"""
Locust load test for Business Data Dictionary.

Modes
-----
Standard (300 users, 2 min):
    locust -f tests/load/locustfile.py --headless -u 300 -r 10 --run-time 2m \
        --host http://localhost:8501

Benchmark mode (adds CSV + HTML output):
    locust -f tests/load/locustfile.py --headless -u 300 -r 10 --run-time 2m \
        --host http://localhost:8501 \
        --csv tests/load/results/run --html tests/load/results/report.html

Smoke test (quick sanity, 10 users):
    locust -f tests/load/locustfile.py --headless -u 10 -r 2 --run-time 30s \
        --host http://localhost:8501 --tags smoke

Requirements:
    ENABLE_MOCK_AUTH=true ENVIRONMENT=development must be set on the target app.
    Install: pip install --prefer-binary locust
"""
import os
from locust import HttpUser, task, between, tag, events


TARGET_HOST = os.getenv("LOAD_TEST_HOST", "http://localhost:8501")


class DictionaryUser(HttpUser):
    """Simulates a business user browsing the Data Dictionary."""

    wait_time = between(1, 3)

    def on_start(self):
        """Authenticate via mock login before issuing any tab requests."""
        with self.client.get("/?mock_login=true", catch_response=True, name="auth: mock login") as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Mock login failed: {resp.status_code}")

    # ── Core browsing tasks (run in both smoke and full modes) ────────────────

    @tag("smoke")
    @task(40)
    def search_tab(self):
        """Most common entry point — 40% of traffic."""
        self.client.get("/?tab=search", name="tab: search")

    @tag("smoke")
    @task(20)
    def catalog_tab(self):
        self.client.get("/?tab=catalog", name="tab: catalog")

    @tag("smoke")
    @task(15)
    def glossary_tab(self):
        self.client.get("/?tab=glossary", name="tab: glossary")

    # ── Extended tasks (full run only) ────────────────────────────────────────

    @task(10)
    def discovery_tab(self):
        self.client.get("/?tab=discovery", name="tab: discovery")

    @task(10)
    def health_tab(self):
        self.client.get("/?tab=health", name="tab: health")

    @task(5)
    def admin_tab(self):
        self.client.get("/?tab=admin", name="tab: admin")

    @task(10)
    def detail_drilldown(self):
        """Simulate opening a table detail after a search result."""
        self.client.get("/?tab=search&table=example_table", name="tab: search (detail)")


# ── Benchmark summary printed at test end ────────────────────────────────────

@events.quitting.add_listener
def print_benchmark_summary(environment, **kwargs):
    stats = environment.runner.stats
    agg = stats.total
    if agg.num_requests == 0:
        return

    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"  Total requests : {agg.num_requests:,}")
    print(f"  Failures       : {agg.num_failures:,} ({agg.num_failures / agg.num_requests:.2%})")
    print(f"  Throughput     : {agg.current_rps:.1f} req/s  (peak {agg.num_requests / max(stats.last_request_timestamp - stats.start_time, 1):.1f})")
    print(f"  Latency p50    : {agg.get_response_time_percentile(0.50):.0f} ms")
    print(f"  Latency p95    : {agg.get_response_time_percentile(0.95):.0f} ms")
    print(f"  Latency p99    : {agg.get_response_time_percentile(0.99):.0f} ms")
    print(f"  Max latency    : {agg.max_response_time:.0f} ms")
    print("=" * 60 + "\n")


# ── WebSocketUser stub (future WS-level load testing) ────────────────────────
#
# Streamlit's real-time state syncs over WebSocket at /_stcore/stream.
# HTTP tests above only measure page delivery; WS tests would cover
# query execution, session state updates, and widget interactions.
#
# To implement, use websocket-client or websockets inside a Locust task:
#
# from locust import User
# import websocket
#
# class StreamlitWSUser(User):
#     def on_start(self):
#         self.ws = websocket.create_connection(
#             "ws://localhost:8501/_stcore/stream"
#         )
#
#     @task
#     def ping_ws(self):
#         self.ws.send('{"type":"ping"}')
#         self.ws.recv()
#
#     def on_stop(self):
#         self.ws.close()
