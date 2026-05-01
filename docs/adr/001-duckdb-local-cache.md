# ADR 001 — DuckDB as the local metadata cache

**Status:** Accepted  
**Date:** 2026-04-30  
**Deciders:** Platform team

---

## Context

The nightly sync job crawls Unity Catalog and must store the results somewhere the Streamlit app can query quickly. The catalog has approximately 800 tables; each table has on average 15 columns. The `permissions_cache` table contains roughly 3 000 rows (one per table-group-privilege triple). Total dataset size is small (well under 100 MB uncompressed).

The query patterns are:

- Full-text search across `tables_metadata` and `columns_metadata` with a `JOIN` to `permissions_cache` to enforce row-level security
- Point lookups by `full_name` for the table detail panel
- Aggregate queries for the health dashboard (count of documented tables, column coverage percentage)
- Occasional `UNION` queries for related-table discovery

The app is read-heavy. A single sync job is the only writer; the app never modifies catalog data (only the user data file). Concurrent read access from multiple Streamlit processes must work without coordination.

### Alternatives considered

**SQLite**
- Built into Python, no additional dependency
- Familiar to most contributors
- Analytical queries (aggregates, multi-table JOINs) are notably slower than columnar engines on this workload
- No native Parquet or CSV export
- Not designed for analytical access patterns

**Redis**
- Excellent for key-value lookups (e.g. point lookups by `full_name`)
- Requires a running server, adding operational complexity for local development
- Does not support SQL JOINs natively — permission enforcement would have to move into Python, breaking the push-down security model
- Overkill for an 800-table catalog; memory overhead is significant

**Polars in-memory**
- Very fast for analytical queries
- No persistence — data must be reloaded on every Streamlit session start (cold start penalty of several seconds for 800 tables)
- No SQL interface — queries must be rewritten in the Polars expression API, diverging from the Databricks SQL strings already tested

---

## Decision

Use DuckDB as the local metadata cache.

DuckDB is an embedded, columnar analytical database that runs in-process (no server required). It speaks SQL, supports parameterized queries, and can read and write Parquet files natively. The `duckdb` Python package is a single binary wheel with no system dependencies.

Key properties that make it the right fit:

- Analytical queries with GROUP BY, multi-table JOINs, and UNION run in single-digit milliseconds on the ~800-table dataset (p95 < 8 ms in load testing at 300 concurrent users)
- The same SQL strings used against the Databricks SQL Warehouse work against DuckDB after minor dialect translation (handled by `_to_duckdb_sql()`)
- The catalog file is a single `.duckdb` file that the sync job replaces atomically with `os.replace()`. Readers that have the old file open continue to see a consistent snapshot; new readers pick up the replacement on next open
- The user data file (`dict_user_data.duckdb`) is `ATTACH`ed at runtime, enabling cross-file JOINs without any server coordination
- Local development requires no infrastructure: set `DUCKDB_PATH` and `DEMO_DATA=true`, run `streamlit run app.py`

---

## Consequences

**Positive:**
- Sub-10 ms search queries in the read path, regardless of Databricks SQL Warehouse availability
- Zero infrastructure dependency for local development and CI
- Single-file portability: the entire catalog snapshot can be copied, backed up, or inspected with any DuckDB client

**Negative:**
- DuckDB enforces a single-writer constraint per file. The sync job holds an exclusive write lock while rebuilding the catalog file. During a sync (typically 30–90 seconds) the app falls back to the previous file via the atomic-replace mechanism. The transition window is safe but operators should be aware of it.
- The `_to_duckdb_sql()` dialect translator adds a small maintenance surface. New query patterns that use Databricks-specific functions must be added to the translator when DuckDB support is needed.
- DuckDB is not a networked database. Horizontal scaling (multiple app replicas) requires that all replicas share the same PVC mount point. This is the reason the PVC uses `ReadWriteMany` access mode. On clusters without a shared filesystem, this constraint must be addressed at the storage layer.
