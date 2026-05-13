## 2024-05-05 - Documenting Database Routing & Authorization Layers
**Learning:** Found that the dual caching (Demo mode vs. DuckDB vs. Databricks) and row-level access control via Entra ID groups in `src/db/queries.py` are core architectural pieces that lacked docstrings.
**Action:** Always verify docstrings exist for functions serving as critical routing abstractions or access control gates in applications using hybrid mock/production database connectivity.
## 2026-05-12 - [Regex Comment] Learning: Unity Catalog 3-level namespace validation regex logic is r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$", indicating each catalog, schema, and table segment uses only letters, numbers, and underscores, without dashes. Action: Ensure any future DB mocks adhere strictly to this regex logic.
