## Janitor Journal

## 2026-05-04 - [Ruff Unused Variable Fixes] **Learning:** Ruff's `--fix` flag for unused variables (F841) might only remove the left-hand variable assignment, leaving the right-hand pure expressions hanging (e.g., set comprehensions, or method calls that return DataFrames). **Action:** Always manually review and delete the entire line when fixing F841 to avoid leaving dead code, or refactor to preserve necessary side effects.

## 2024-05-03 - [Pandas Optimization] Replace iterrows with itertuples
**Learning:** `iterrows` is significantly slower than `itertuples(index=False)` for DataFrame iteration. When replacing, dictionary `.get` lookups on rows must be swapped with `getattr(row, field, default)` to handle NamedTuples appropriately. Similarly, when iteration is meant to construct dictionaries for parameterization (e.g., DuckDB inserts), using `.to_dict('records')` avoids iteration overhead completely. Also, when modifying global components tested in AppTest with heavy mocks like ThreadPoolExecutors, mock the executor `submit`/`as_completed` flows to run synchronously to prevent deadlocks and assertion misses.
**Action:** Always favor `.to_dict('records')` for dictionary construction and `itertuples(index=False)` for general iteration over `iterrows()`. Update row accesses to `getattr` instead of `[]` or `.get()`.
