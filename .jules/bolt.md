## 2024-05-21 - Optimizing Catalog Tree Rendering
**Learning:** Calling `groupby()` and `.unique().tolist()` repeatedly inside a Streamlit render loop over large DataFrames acts as a severe performance bottleneck (effectively O(N^2)).
**Action:** Pre-compute relationships by applying `.apply(list).to_dict()` on a global groupby before the render loop, allowing O(1) dictionary lookups for nested data structures.

## 2024-05-22 - [Performance] Optimize pandas dataframe arbitrary list sorting
**Learning:** Using `.map` with an enumerated dictionary to create a temporary sort order column is slower and allocates more memory than using pandas native `Categorical` type.
**Action:** Always use `pd.Categorical(..., categories=target_list, ordered=True)` when sorting a DataFrame based on a specific arbitrary list of items.

## 2026-05-22 - Document false positive cache rationale in health dashboard
**Learning:** When an issue incorrectly identifies a performance problem that conflicts with an architectural constraint (e.g., ADR 002 enforcing SQL push-down vs. Python/Pandas in-memory aggregation), do not force an unnecessary refactor.
**Action:** Documented the false positive via an inline comment using the active persona's format.

## 2026-05-22 - Optimize cache hits in glossary
**Learning:** Streamlit caching requires hashable arguments, and passing lists bypasses the cache entirely.
**Action:** Cast query_groups to a tuple when calling get_authorized_table_names to ensure O(1) cache retrieval instead of repeated expensive I/O.

## 2026-05-22 - Flawed N+1 Rationale
**Learning:** Parameter unrolling (creating `group_0`, `group_1`, etc.) for a single `IN` clause is safe from SQL injection, ensures cross-driver database compatibility, and is not an N+1 query problem. Refactoring this loop actually reduces compatibility without improving performance.
**Action:** Retained the parameter unrolling pattern and added an explicit inline comment explaining the cross-driver compatibility and why the N+1 rationale was flawed.

## 2026-05-23 - Optimize DataFrame slicing in nested Streamlit loops
**Learning:** Performing pandas dataframe filtering (e.g., `df[df['col'] == val]`) inside a Streamlit render loop over large datasets causes a severe performance bottleneck.
**Action:** Pre-compute necessary relationships (like grouping items into a dictionary mapping) before entering the render loop to allow O(1) retrieval.
## 2024-05-26 - O(N^2) Loop Optimization for Graph Nodes
**Learning:** Checking for node and link uniqueness within a loop using list comprehensions (`any()`) causes O(N^2) performance degradation as the data size grows.
**Action:** Replaced O(N) list-based iterations with O(1) set-based tracking outside of the loop, significantly accelerating graph building.
