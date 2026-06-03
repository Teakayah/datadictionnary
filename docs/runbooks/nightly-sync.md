# Runbook — Nightly metadata sync

The nightly sync crawls Unity Catalog, computes embeddings, and writes a
fresh DuckDB cache file that all Streamlit app pods read from. It must
run at least once before the app can show any catalog data.

| | |
| -- | -- |
| **Entry point** | `python scripts/sync_metadata.py` |
| **Source** | `scripts/sync_metadata.py` |
| **k8s manifest** | `k8s/cronjob.yaml` (`CronJob dd-sync`, daily at 03:00 UTC) |
| **Output** | `DUCKDB_PATH` file (e.g. `/data/dict.duckdb`) |
| **Databricks target** | `data_governance.dictionary_cache` (tables/columns/permissions/embeddings) |

---

## What it does

```
WorkspaceClient (databricks-sdk)
  └─ list catalogs → schemas → tables → columns
       ├─ extract grants (permissions_cache)
       ├─ extract tags + DQ monitoring rows
       ├─ fetch lineage (optional)
       ├─ generate embeddings (if ENABLE_SEMANTIC_SEARCH=true)
       └─ push business-name overrides from user_data back to Unity Catalog

Truncate-and-reload into data_governance.dictionary_cache:
  tables_metadata, columns_metadata, permissions_cache,
  tags_metadata, lineage_metadata, data_quality_metadata,
  audit_log_metadata, tables_embedding_cache

Write same data into DUCKDB_PATH (local cache for the app pods).
```

The sync is a full truncate-and-reload — partial failures leave the
previous snapshot in place until the next successful run.

---

## Prerequisites

All variables must be set in the environment (or `.env`):

```
DATABRICKS_HOST          # e.g. https://adb-xxx.azuredatabricks.net
DATABRICKS_HTTP_PATH     # /sql/1.0/warehouses/<id>
DATABRICKS_TOKEN         # PAT with CAN_USE on the SQL warehouse
DUCKDB_PATH              # local path where the cache file is written
                         # e.g. /data/dict.duckdb

# Optional — semantic search
ENABLE_SEMANTIC_SEARCH=true
DATABRICKS_EMBEDDING_ENDPOINT   # Model Serving endpoint name
```

The SQL warehouse user needs:
- `USE CATALOG` on every catalog to crawl
- `SELECT` on `information_schema` for each schema
- `SELECT` on `system.access.grants` (for permissions)

---

## Running manually

**First-time setup / local dev:**
```bash
cp .env.example .env
# Fill in DATABRICKS_* and DUCKDB_PATH
python scripts/sync_metadata.py
```

**Generate a local test dataset without Databricks:**
```bash
python scripts/generate_test_data.py          # 800 tables
python scripts/generate_test_data.py --with-data  # + row data for Preview tab
# Then set DUCKDB_PATH=data/test_data.duckdb in .env
```

**Trigger an ad-hoc run in k8s:**
```bash
kubectl -n data-dictionary create job --from=cronjob/dd-sync dd-sync-manual-$(date +%s)
kubectl -n data-dictionary logs -l job-name=dd-sync-manual-<id> -f
```

---

## Monitoring a run

The script logs to stdout. Key milestones:

```
Starting Unity Catalog metadata sync...
  Processing schema: <name>          ← one line per schema
Generating semantic embeddings...    ← only if ENABLE_SEMANTIC_SEARCH=true
Writing DuckDB cache...
Sync complete. X tables, Y columns.
```

Typical runtime: 5–30 minutes depending on catalog size and whether
embeddings are enabled.

In k8s, check the CronJob history:
```bash
kubectl -n data-dictionary get jobs -l app=dd-sync
kubectl -n data-dictionary logs job/dd-sync-<timestamp>
```

---

## Failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| `DATABRICKS_HOST is not set` | Missing env var | Set all required vars |
| `403 Forbidden` on Unity Catalog | PAT lacks permissions | Grant `USE CATALOG` + schema `SELECT` |
| `Error: table not found: data_governance.dictionary_cache.tables_metadata` | `setup_cache_tables()` failed | Run with a PAT that has `CREATE CATALOG` / `CREATE SCHEMA` rights |
| App shows no results after sync | `DUCKDB_PATH` mismatch | Confirm app and sync use the same PVC mount path |
| Embeddings table empty | `ENABLE_SEMANTIC_SEARCH` not set | Set the env var and rerun |

If a run fails mid-way, the previous DuckDB file and Databricks tables are
untouched — the app continues serving the last good snapshot. Rerun the
sync to pick up changes.

---

## Relationship to the sidecar write-back worker

The metadata sync (`sync_metadata.py`) is **read-only from Unity Catalog's
perspective** — it copies catalog metadata into DuckDB. It also calls
`push_business_name_overrides()` to write user-authored column definitions
back to Databricks, but this is a one-shot flush.

The sidecar sync worker (`src/sync/daemon.py`, `k8s/deployment-sync-worker.yaml`)
is the continuous write-back path — it drains `user_data.pending_sync`
in real time as users make edits. See `docs/runbooks/sync-worker.md`.
