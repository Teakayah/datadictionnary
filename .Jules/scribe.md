## 2024-05-05 - Documenting Database Routing & Authorization Layers
**Learning:** Found that the dual caching (Demo mode vs. DuckDB vs. Databricks) and row-level access control via Entra ID groups in `src/db/queries.py` are core architectural pieces that lacked docstrings.
**Action:** Always verify docstrings exist for functions serving as critical routing abstractions or access control gates in applications using hybrid mock/production database connectivity.

## 2024-05-07 - Dynamic Background Polling for Local Cache
**Learning:** The background sync worker uses dynamic polling (5s when idle, 30s when active) to reduce DuckDB write lock contention during active UI navigation.
**Action:** Always document the *why* behind dynamic polling or rate limiting, especially when it relates to resource contention in single-process local databases like DuckDB.
