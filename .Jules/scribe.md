## 2024-05-05 - Documenting Database Routing & Authorization Layers
**Learning:** Found that the dual caching (Demo mode vs. DuckDB vs. Databricks) and row-level access control via Entra ID groups in `src/db/queries.py` are core architectural pieces that lacked docstrings.
**Action:** Always verify docstrings exist for functions serving as critical routing abstractions or access control gates in applications using hybrid mock/production database connectivity.
