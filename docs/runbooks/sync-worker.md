# Runbook — Sync worker (sidecar)

The sync worker is a long-lived process that drains
`user_data.pending_sync` to Databricks Unity Catalog and runs DR resync
(pulls late-arriving rows from Databricks back into the local user_data
file). It runs in its own pod, separate from the Streamlit app.

| | |
| -- | -- |
| **Entry point** | `python -m src.sync.daemon` |
| **Source** | `src/sync/daemon.py`, `src/sync/daemon_db.py`, `src/sync/dr_resync.py`, `src/sync/push.py` |
| **k8s manifest** | `k8s/deployment-sync-worker.yaml` (`Deployment dd-sync-worker`, `replicas: 1`, `Recreate`) |
| **Image** | Same image as `dd-app`; `command:` is overridden in the manifest. |
| **Healthz** | `GET :8765/healthz` — 200 if heartbeat is fresh, 503 if stale. |
| **State** | `user_data.pending_sync` (queue) + `user_data.site_settings` (status keys). |

---

## Architecture in one diagram

```
┌────────────────────┐            ┌────────────────────┐         ┌──────────────┐
│  dd-app pods       │            │  dd-sync-worker    │         │  Databricks  │
│  (HPA: 2–10)       │            │  (replicas: 1)     │         │  SQL Wh / UC │
│                    │  enqueue   │                    │  push   │              │
│  Streamlit UI      │ ────────▶  │  python -m         │ ──────▶ │              │
│  + DuckDB attach   │            │  src.sync.daemon   │ ◀────── │              │
│                    │            │                    │  pull   │              │
│                    │            │                    │  (DR)   │              │
└──────────┬─────────┘            └─────────┬──────────┘         └──────────────┘
           │                                │
           └────────────  PVC dd-data  ─────┘
                  /data/dict.duckdb              (catalog cache, written by nightly_sync)
                  /data/dict_user_data.duckdb    (queue + overrides + audit log + comments)
                       ↑ daemon writes worker_heartbeat + dr_resync_status here;
                         Streamlit reads them back via user_data.site_settings
```

Streamlit pods only **enqueue** into `pending_sync` and write user
overrides directly. The sync worker is the only process that pushes to
Databricks. The pending_sync table is the IPC bus — no message broker,
no extra infrastructure.

---

## Operational basics

### Find the pod

```bash
kubectl -n data-dictionary get pods -l app=dd-sync-worker
kubectl -n data-dictionary logs -l app=dd-sync-worker -f
```

Logs use `name=sync_daemon` for daemon-level events and
`name=src.sync.dr_resync` / `name=src.sync.push` for module-level events.

### Probe healthz

From inside the cluster:

```bash
kubectl -n data-dictionary port-forward deploy/dd-sync-worker 8765:8765
curl -s localhost:8765/healthz | jq
# {"status": "ok", "heartbeat_age_s": 4.2}
```

A heartbeat older than `HEALTHZ_TIMEOUT_S` (60s, constant in `src/sync/daemon.py`) returns 503
and the liveness probe will restart the pod.

### Inspect queue state

```bash
kubectl -n data-dictionary exec -it deploy/dd-sync-worker -- \
  python -c "
import duckdb, os
con = duckdb.connect(os.getenv('DUCKDB_PATH').replace('.duckdb', '_user_data.duckdb'))
print(con.execute('''
  SELECT status, count(*) FROM user_data.pending_sync GROUP BY 1 ORDER BY 1
''').fetchall())
print(con.execute('''
  SELECT key, value, updated_at FROM user_data.site_settings
  WHERE key IN ('dr_resync_status', 'worker_heartbeat')
''').fetchall())
"
```

### Run a single cycle (one-shot mode)

Useful for CI, post-deploy flush, or to debug a specific cycle:

```bash
kubectl -n data-dictionary exec -it deploy/dd-sync-worker -- \
  python -m src.sync.daemon --once --healthz-port 0
```

`--healthz-port 0` disables the HTTP listener (avoids port collision when
running ad hoc).

---

## Configuration

All configuration is via environment variables (set in `k8s/configmap.yaml`
or per-pod env). Defaults are sensible — only override if you have a reason.

| Variable | Default | Purpose |
| -- | -- | -- |
| `DUCKDB_PATH` | — (required) | Catalog cache file. The worker derives `USER_DATA_PATH` by replacing `.duckdb` with `_user_data.duckdb`. |
| `DATABRICKS_HOST` / `_HTTP_PATH` / `_TOKEN` | — | Required for write-back AND DR resync. If unset the daemon still runs (drains nothing, DR resync logs `Skipped`). |
| `SYNC_HEALTHZ_PORT` | `8765` | HTTP port for `/healthz`. Set to `0` to disable. |
| `LOG_LEVEL` | `INFO` | Stdlib logging level. `DEBUG` enables verbose cycle logs. |

Timing values (poll intervals, DR resync cadence, stale-row timeout, healthz
heartbeat timeout) are module constants in `src/sync/daemon.py` — they never
needed per-deployment overrides. Change them in code if a deployment truly
requires different cadence.

---

## State written to user_data.site_settings

The daemon writes two keys the UI reads back:

| Key | Value | Owner |
| -- | -- | -- |
| `worker_heartbeat` | ISO-8601 timestamp, refreshed every cycle | sync_daemon |
| `dr_resync_status` | `Idle` / `Checking` / `Syncing <table>` / `Up-to-date` / `Skipped (no Databricks creds)` / `Error: <msg>` | sync_daemon |

The admin "§ Synchronization status" panel reads these via
`src.sync.worker.read_dr_resync_status()` and `read_worker_heartbeat()`.

---

## Common operations

### Restart after a config change

`Recreate` rollout strategy (single writer, no overlap):

```bash
kubectl -n data-dictionary rollout restart deploy/dd-sync-worker
kubectl -n data-dictionary rollout status deploy/dd-sync-worker --timeout=60s
```

### Drain the queue manually

If the worker is failing repeatedly and the queue is backing up, you can
mark all pending rows as `failed` to stop the retry storm and inspect them
out of band:

```sql
UPDATE user_data.pending_sync
   SET status = 'failed',
       last_error = 'manually drained'
 WHERE status IN ('pending', 'syncing');
```

Then fix the underlying issue, re-enqueue from the audit log, and let the
daemon resume.

### Force a DR resync

Either bounce the pod (the first cycle always runs DR resync), or set the
counter to a multiple of `DR_RESYNC_EVERY_N` (constant in `src/sync/daemon.py`)
by waiting it out.

---

## Failure modes

### `/healthz` returns 503 with `heartbeat_age_s: null`

The daemon never wrote a heartbeat. Almost always a startup error —
`DUCKDB_PATH` unset, file permissions on `/data`, or a parse error in the
schema migration. Check the pod logs.

### `/healthz` returns 503 with `heartbeat_age_s: 9999`

The daemon is alive but stuck. Check logs for the most recent
`Daemon cycle error:` entry. If `_recover_stale_rows` is failing the whole
cycle aborts. Common causes: catalog file corruption (rare; check
PVC), or a Databricks auth failure that throws inside DR resync (the
loop catches this but logs ERROR — confirm token freshness).

### `dr_resync_status` stuck on `Error: …`

Read the full error from logs. If transient (network blip), the next
cycle will retry. If persistent (auth, schema mismatch), the daemon is
otherwise healthy — pending_sync drain still happens on every cycle.

### Pending queue grows unbounded

Indicates one of:

1. Databricks creds are wrong or expired → all pushes fail, attempts
   counter increments. After `_SYNC_MAX_ATTEMPTS` (3) rows go to
   `'failed'` and stop retrying.
2. The daemon is crashing every cycle → check liveness probe events.
3. The schema in Databricks doesn't match what the push expects → look at
   `last_error` on a stuck row.

```sql
SELECT sync_type, count(*), max(last_error)
  FROM user_data.pending_sync
 WHERE status IN ('pending', 'failed')
 GROUP BY sync_type;
```

### Two writers contention (DuckDB OS lock)

Multiple processes write to `USER_DATA_PATH`: the sync worker and the
Streamlit pods (which enqueue and write user overrides). DuckDB serialises
them via an OS-level file lock. At low write volume (typical for this
app) you'll never notice. If write contention shows up under load the
fix is migrating `user_data` to PostgreSQL — tracked in TODO.md.

---

## Related runbooks / ADRs

- ADR 001 — DuckDB as local metadata cache (`docs/adr/001-duckdb-local-cache.md`)
- ADR 002 — Push-down SQL auth (`docs/adr/002-push-down-sql-auth.md`)
- ADR 004 — Sidecar sync worker (`docs/adr/004-sidecar-sync-worker.md`)
- Runbook — Secret rotation (`docs/runbooks/secret-rotation.md`)
