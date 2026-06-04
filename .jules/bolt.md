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

## 2026-05-26 - Optimize Pandas Timestamp Formatting
**Learning:** Formatting timestamps with pandas `.apply()` running a custom Python function over string/datetime parsing is significantly slower than using vectorized `pd.to_datetime(...).dt.strftime(...)`.
**Action:** Always prefer pandas vectorized `.dt` accessors for datetime manipulation and string formatting instead of scalar Python `.apply()` functions on DataFrames.

## 2024-05-30 - Optimize rendering loop in search page
**Learning:** Rendering UI components (like st.columns) inside a loop over a large, unbounded DataFrame causes severe main-thread blocking and browser freezing in Streamlit applications.
**Action:** Applied a hard cap (.head(50)) before iterating over DataFrames to render repeating UI components to ensure performance and prevent UI blocking.

## 2024-05-30 - Optimize unique extraction on dataframes
**Learning:** Calling .unique().tolist() on pandas DataFrames allocates more memory and is slower than .drop_duplicates().tolist().
**Action:** Replaced .unique().tolist() with .drop_duplicates().tolist() to improve execution speed.

## 2024-06-03 - Optimize set instantiation from DataFrames
**Learning:** Instantiating a set directly from a large Pandas column list (`set(df['col'].tolist())`) is significantly slower than deduping with numpy first (`set(df['col'].unique().tolist())`).
**Action:** Always call `.unique().tolist()` before casting to a `set` to leverage fast C-level CPython/NumPy deduplication.

## 2026-06-03 - Redundant String Manipulation
**Learning:** Reconstructing a string by splitting and joining on the same delimiter (e.g., `s.split('.')[0] + '.' + '.'.join(s.split('.')[1:])`) is an O(N) redundant operation that wastes CPU cycles without changing the output.
**Action:** Remove unnecessary string formatting operations when the target representation already exists.

## 2024-06-04 - Optimize pandas groupby uniqueness aggregation
**Learning:** Computing unique values inside a pandas `groupby()` loop via `.unique().apply(list)` is significantly slower than globally dropping duplicates first (`.drop_duplicates(...)`) and then grouping and applying `.apply(list)`.
**Action:** Always prefer global `.drop_duplicates()` before `.groupby()` when constructing unique mappings from DataFrames to drastically improve execution speed.
