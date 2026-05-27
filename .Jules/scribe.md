## 2024-05-24 - [DuckDB Parameterization Insight]
**Learning:** DuckDB requires explicit array operators (`= ANY(...)`) instead of standard `IN (...)` parameter unrolling when passing lists/tuples from Python. This conversion is handled automatically by `_to_duckdb_sql`.
**Action:** Expanded the docstring for `_to_duckdb_sql` to provide clearer context on why this specific regex transformation exists.
## 2024-05-24 - [Semantic Search Scaffolding]
**Learning:** The `semantic_search` function currently acts as a scaffold returning dummy results, awaiting verification of the DuckDB `vss` extension before production enablement.
**Action:** Added a `TODO` and expanded the docstring to clearly document this state and prevent confusion for future maintainers.

## 2024-05-24 - [Pipeline Progress UI]
**Learning:** Pipeline progress percentages are synthetic values used to drive the UI progress bar when precise task completion metrics aren't available.
**Action:** Added an explanatory comment above the progress dictionaries in `src/pipelines.py` to clarify their purpose.
