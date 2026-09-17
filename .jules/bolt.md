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
**Learning:** Calling .unique().tolist() on pandas DataFrames is significantly faster and allocates less memory than .drop_duplicates().tolist() due to utilizing optimized C-level NumPy arrays.
**Action:** Always prefer .unique().tolist() over .drop_duplicates().tolist() to improve execution speed.

## 2024-06-03 - Optimize set instantiation from DataFrames
**Learning:** Instantiating a set directly from a large Pandas column list (`set(df['col'].tolist())`) is significantly slower than deduping with numpy first (`set(df['col'].unique().tolist())`).
**Action:** Always call `.unique().tolist()` before casting to a `set` to leverage fast C-level CPython/NumPy deduplication.

## 2026-06-03 - Redundant String Manipulation
**Learning:** Reconstructing a string by splitting and joining on the same delimiter (e.g., `s.split('.')[0] + '.' + '.'.join(s.split('.')[1:])`) is an O(N) redundant operation that wastes CPU cycles without changing the output.
**Action:** Remove unnecessary string formatting operations when the target representation already exists.

## 2024-06-06 - Optimize unique mapping construction in Pandas DataFrames
**Learning:** In pandas, when constructing unique mappings via `groupby()`, computing uniqueness inside the loop via `.unique().apply(list)` is significantly slower than globally dropping duplicates first (`.drop_duplicates(...)`) and then grouping and applying `.apply(list)`.
**Action:** Replaced `.groupby(...)[...].unique().apply(list)` with `.drop_duplicates(subset=[...]).groupby(...)[...].apply(list)` to improve execution speed.
## 2026-06-10 - Limit Unbounded Admin Iterations
**Learning:** Rendering complex UI components (like `st.columns`, `st.button`) inside unbounded loops over a potentially large list of items (e.g. pending reviews in admin panels) causes severe Streamlit main-thread blocking and browser freezes.
**Action:** Added hard caps (e.g., `[:50]`) and UI truncation notices when rendering repeating components from potentially unbounded queries to guarantee performance without freezing the browser.

## 2024-06-28 - Optimize Pandas .map() execution
**Learning:** Using Python `lambda` functions inside pandas `.map()` (e.g. `.map(lambda fn: ...)`) iteration is significantly slower than preparing a pre-computed dictionary and passing it to `.map(dict).fillna()`.
**Action:** Always replace `.map(lambda)` operations over DataFrames with pre-computed dictionary mappings and `.fillna()` to prevent slow, row-by-row Python iteration over Pandas Series.
## 2025-06-30 - Import Placement Rule
**Learning:** When appending or adding new imports to a Python file, placing them between `__future__` imports and the module docstring turns the docstring into a regular string literal, breaking the `__doc__` attribute and triggering E402 errors for all subsequent imports.
**Action:** Always ensure new imports are added strictly after the module docstring to preserve structural integrity and pass linting.
## 2026-07-15 - Redundant Pandas Dictionary Mappings
**Learning:** In Pandas, declaring multiple redundant dictionaries and iterating over the same column multiple times with `.map()` and `.copy()` is significantly slower than calculating the single final dictionary mapping required to achieve the desired value assignments in one pass.
**Action:** Always collapse consecutive, redundant `.map()` logic over Pandas Series into a single optimized mapping operation to drastically decrease overhead execution time and limit memory re-allocations.
## 2026-07-22 - Optimize pandas list scoring logic
**Learning:** Pandas `.map(dictionary).fillna()` dictionary lookups create temporary Series and allocate large amounts of memory, especially in search loops. Vectorization using `pd.Categorical` avoids this overhead.
**Action:** Replace `.map()` lookups for list scoring with vectorized `pd.Categorical(..., categories=list).codes` arrays.
## 2024-07-26 - Optimize analytics tracking I/O
**Learning:** Synchronous DuckDB disk I/O operations (like `track_search`) placed inside the main Streamlit rendering loop block the main thread, causing noticeable UI freezing during frequent user actions (like typing in a search bar).
**Action:** Offload non-critical I/O operations (like analytics tracking) to background threads using `threading.Thread(target=..., daemon=True).start()` to allow the UI to remain responsive.
## 2024-07-26 - Streamlit Threading Context
**Learning:** Streamlit heavily relies on a thread-local `ScriptRunContext` for its core features (like caching, connection state, etc.). Spawning a raw `threading.Thread` without attaching this context will cause Streamlit functions to throw a `RuntimeError`, which, if caught in a broad `try...except`, results in silent failure.
**Action:** Always inject the Streamlit context into newly spawned background threads using `from streamlit.runtime.scriptrunner import add_script_run_ctx; add_script_run_ctx(thread)`.
## 2024-08-14 - Optimize Pandas Groupby List Aggregation
**Learning:** In pandas DataFrame operations, prefer `groupby().agg(list)` over `groupby().apply(list)` when aggregating grouped items into a list. `agg(list)` uses optimized reduction pathways and is significantly faster, whereas `apply(list)` incurs heavy overhead from flexible row-by-row evaluation.
**Action:** Replace `apply(list)` with `agg(list)` after pandas `groupby` when constructing lists.
## 2024-09-12 - Optimize intersection of frozenset and list
**Learning:** Using `bool(frozenset_obj & set(list_obj))` is slow as it allocates memory to convert the list to a set and evaluate intersection. Using `not frozenset_obj.isdisjoint(list_obj)` is much faster since it leverages optimized C-level short-circuiting and avoids unnecessary memory allocation.
**Action:** Always prefer `not my_set.isdisjoint(my_list)` over `bool(my_set & set(my_list))` to check for intersection between a set and a list.

## 2024-08-26 - Optimize boolean array indexing
**Learning:** When assigning values to an array or pandas Series based on multiple conditions, using sequential boolean mask indexing (e.g., `arr[mask] = val`) creates slower row-by-row mapping bottlenecks and unnecessary intermediate array creation.
**Action:** Always prefer a single nested `np.where(cond1, val1, np.where(cond2, val2, default))` expression over sequential boolean mask indexing for better vectorization performance.
## 2024-05-24 - Combine schema initialization queries to prevent N+1
**Learning:** When executing multiple DDL statements (like `CREATE TABLE` during schema initialization), looping and calling `.execute()` sequentially incurs unnecessary overhead for each statement. Joining them into a single SQL script string and executing it once provides a measurable performance improvement.
**Action:** Combined `_SCHEMA_STATEMENTS` into a single execute call in `src/db/duckdb_adapter.py`, improving schema init performance from ~7.3s to ~6.2s for 1000 iterations (~15% speedup).

## 2024-05-13 - Replace loop row-by-row queries with executemany
**Learning:** Using `executemany` over row-by-row iterations for DuckDB write adapters significantly speeds up bulk insertion operations and resolves N+1 loop performance bottlenecks, while maintaining thread safety via a shared lock.
**Action:** Added `executemany` and `executemany_write` to `_DuckDBCursor` and modified `dr_resync` to leverage it for bulk insertion instead of `for row in df.itertuples(...)` with `execute_write`.

