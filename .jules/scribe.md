## 2024-05-24 - [DuckDB Parameterization Insight]
**Learning:** DuckDB requires explicit array operators (`= ANY(...)`) instead of standard `IN (...)` parameter unrolling when passing lists/tuples from Python. This conversion is handled automatically by `_to_duckdb_sql`.
**Action:** Expanded the docstring for `_to_duckdb_sql` to provide clearer context on why this specific regex transformation exists.
