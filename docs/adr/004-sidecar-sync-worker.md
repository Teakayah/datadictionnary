# ADR 004 — Sidecar sync worker

**Status:** Accepted
**Date:** 2026-05-07
**Deciders:** Platform team

---

## Context

The Streamlit app needs to push column-definition edits, audit events,
comments, and other user-authored changes back to Databricks Unity
Catalog. Until now this was done by an in-process daemon thread started
from `app.py`:

```python
# Old approach — src/sync/worker.py (now removed)
@st.cache_resource(show_spinner=False)
def _start_sync_worker_thread():
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t
```

Three problems with this design surfaced in the May 2026 audit:

1. **Shared DuckDB connection.** `_get_shared_duckdb_connection()` returns
   a single in-memory DuckDB connection cached via `@st.cache_resource`.
   The worker thread, every Streamlit script-runner thread, and the DR
   resync code all called `execute()` on it concurrently. DuckDB
   connections are not safe for concurrent execute calls — only writes
   were guarded by `_db_write_lock`; reads collided freely. Symptoms:
   intermittent `Connection was closed` errors and silently stale reads.

2. **Streamlit cache from a non-Streamlit thread.** The worker thread had
   no `ScriptRunContext`. Calling `@st.cache_resource`-decorated functions
   from a thread without a ScriptRunContext is undefined behaviour and
   varies between Streamlit minor versions.

3. **Two `_LAST_UI_ACTIVITY` state objects.** The same set of helpers
   (`_get_last_ui_activity`, `_mark_ui_activity`, `_get_dr_resync_status`)
   was duplicated in `src/sync/worker.py` and `src/ui/cards.py`, each with
   its own `_worker_state_lock`. `app.py` imported `_mark_ui_activity`
   from both modules; the second import won. Net effect: the UI ticked
   the cards.py copy, the worker read the worker.py copy, so the worker
   was effectively always in idle mode and used the high-throughput
   batch size unconditionally. Subtle but real.

A fourth latent issue: `src/sync/push.py` referenced `last_attempt_at`
in an UPDATE, but the column was never declared in
`_initialize_schema()`. Every optimistic update threw silently and the
queue stalled.

---

## Decision

Move the drain loop and DR resync into a separate process running
`python -m src.sync.daemon`. Streamlit pods only enqueue into
`user_data.pending_sync`; the daemon is the sole pusher.

### Process boundary

| Responsibility | Streamlit pods | Sync worker |
| -- | -- | -- |
| Enqueue into `pending_sync` | ✓ | — |
| Write user overrides (business names, comments, audit) | ✓ | — |
| Drain `pending_sync` → Databricks | — | ✓ |
| DR resync (Databricks → local) | — | ✓ |
| Stale-row recovery | — | ✓ |
| Heartbeat / status to `site_settings` | — | ✓ |

### Connection ownership

- Streamlit pods continue to use `_get_shared_duckdb_connection()`
  (Streamlit-cached, in-memory, ATTACHes the catalog file read-only and
  the user_data file read-write).
- The daemon uses `src.sync.daemon_db.DaemonConn` — a process-local
  DuckDB connection with no Streamlit cache. Same shape as `_DuckDBConn`
  so `_process_sync_queue` and `run_dr_resync` accept either.

### IPC

The `pending_sync` table is the queue — no Redis, no RabbitMQ, no message
broker. The DuckDB OS-level file lock serialises writes from the
Streamlit enqueue path and the daemon's drain updates. The daemon writes
status keys (`worker_heartbeat`, `dr_resync_status`) into
`user_data.site_settings`; the UI reads them via
`src.sync.worker.read_dr_resync_status()`.

### Health and recovery

- HTTP `GET :8765/healthz` returns 200 if a heartbeat was written within
  `SYNC_HEALTHZ_TIMEOUT_S` (default 60s), else 503 — used by the k8s
  liveness probe.
- Stale-row recovery at the top of every cycle: rows in `'syncing'`
  state with `last_attempt_at < now - SYNC_STALE_ROW_S` (default 300s)
  flip back to `'pending'`. A daemon crash mid-push therefore can't lock
  rows permanently.
- `SIGTERM` sets `_stop_event`; the current cycle finishes (max ~30s
  with `terminationGracePeriodSeconds: 60`) and the daemon exits cleanly.

### Deployment

Singleton — `replicas: 1` with `strategy: Recreate`. Sharing `dd-data`
PVC with `dd-app`. Runs the same image with `command:` overridden.

---

## Alternatives considered

### Keep the in-process daemon

- Cheapest in lines of code.
- Fails the concurrency review: shared DuckDB connection across threads
  is undefined; Streamlit's threading guarantees don't extend to caches
  used from non-script-runner threads.
- Hides the failure: most edits succeed, occasional ones throw silently,
  the queue accumulates, nobody notices until the queue table is
  large.

### Per-replica writer

Run a sync thread inside each Streamlit replica. Each opens its own
DuckDB connection and competes for the OS lock.

- Doesn't solve the Streamlit-context-from-thread problem.
- N replicas all drain the same queue → race conditions on the
  `'pending' → 'syncing'` transition unless we add row-level claiming.
- Hard to reason about which replica is doing what.
- No clear separation between "user-facing pod" and "background work".

### External queue (Redis Streams / RabbitMQ / Azure Service Bus)

Replace `pending_sync` with a managed queue.

- Best long-term option — provides at-least-once delivery, retry
  backoff, observability.
- Operational overhead: another moving part to deploy, monitor, secure,
  rotate credentials for.
- Out of proportion for current write volume (≤100 ops/min).
- Adds latency for the visible "edit applied" feedback loop in the UI.
- Revisit if the team is already running Redis or Service Bus for other
  reasons.

### Cron-style one-shot pod

Replace the long-lived daemon with a CronJob running
`python -m src.sync.daemon --once` every minute.

- Simpler deployment shape.
- Cold-start cost on every run (DuckDB connection setup, Databricks
  auth) — at 1 run/min, ≥30% of the cycle is overhead.
- DR resync cadence becomes locked to the cron interval; the long-lived
  daemon can run DR resync on a different cadence (every Nth cycle).
- Stale-row recovery is harder when each invocation is independent —
  who owns the lifecycle of a row stuck in `'syncing'`?

The CronJob shape is reasonable for environments where running
long-lived pods is forbidden. We may add it as an alternate deployment
mode if needed; for now the long-lived Deployment wins.

---

## Consequences

**Positive:**

- DuckDB shared-connection concurrency bugs are gone — Streamlit and
  the daemon never touch the same Python connection object.
- The daemon is now testable in isolation. `tests/test_sync_daemon.py`
  exercises the loop, stale-row recovery, healthz, and DR resync with a
  fake `_databricks_query`. Previously the loop was a `while True`
  inside a thread inside a `@st.cache_resource` — effectively impossible
  to unit-test.
- One source of truth for sync status. The UI reads from
  `user_data.site_settings`; the daemon writes there. No more
  duplicated `_LAST_UI_ACTIVITY` state.
- Streamlit pods become stateless w.r.t. background work. Restarting
  `dd-app` no longer restarts the sync worker; rolling out a new image
  doesn't restart drains in flight.

**Negative:**

- Two Deployments to operate instead of one. Documented in
  `docs/runbooks/sync-worker.md`.
- DuckDB still has multiple writers (Streamlit pods + daemon). Today
  the OS file lock serialises them and write volume is low enough that
  it doesn't matter. If write contention surfaces under load, migrate
  `user_data` to PostgreSQL — tracked in TODO.md.
- The UI no longer shows "Active vs Idle mode" because the daemon
  doesn't track UI activity any more. We replaced that panel with
  "Worker heartbeat" + "Self-Healing (DR)" — more accurate, less
  decorative.

**Out of scope:**

- Multi-writer support beyond DuckDB's lock-serialised default.
- Replacing `pending_sync` with a managed queue.
- Replacing the long-lived Deployment with a CronJob.
