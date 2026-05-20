- For periodic background polling or auto-refreshing in Streamlit UI components, avoid using `time.sleep()` combined with `st.rerun()`, as it blocks the main execution thread and freezes the entire interface for the duration of the sleep.
- Instead, use non-blocking alternatives like `st_autorefresh` from the `streamlit-autorefresh` package, which schedules UI updates via the browser asynchronously without halting Python execution.
## 2026-05-13 - [Pandas] Vectorized operations vs .apply()
**Learning:** Pandas `.apply()` executes with significant overhead as it loops in Python. Vectorized `.str` operations are dramatically faster.
**Action:** Always prioritize native vectorized methods (e.g., `.fillna()`, `.astype(str)`, `.str.strip()`) over `.apply()` for filtering and string operations in DataFrames.
## 2026-05-15 - [Pandas] Vectorized operations vs .apply() for complex scoring
**Learning:** Pandas `.apply()` executes with significant overhead as it loops in Python. Vectorized `.str` operations and `numpy.select()` for conditional logic are dramatically faster, especially on large datasets like metadata searches.
**Action:** Always prioritize native vectorized methods and `numpy.select()` over `.apply()` for complex row-by-row scoring or conditional logic in DataFrames.
## 2024-05-18 - Optimize N+1 query in pending sync cleanup
**Learning:** Python-level fetching and filtering of JSON columns out of DuckDB creates massive N+1 query overhead.
**Action:** Replaced the Python `SELECT`, loop, and individual `DELETE`s with a single vectorized DuckDB SQL statement leveraging `json_extract_string(payload_json, '$.column_name')`.

## 2024-05-20 - Cache authorized tables set transformation
**Learning:** Even when a database query function is cached by Streamlit, repeatedly transforming its returned Pandas DataFrame into a Python set using `.tolist()` and `set()` on every re-run incurs measurable CPU overhead, especially as the number of tables grows.
**Action:** Created a dedicated Streamlit-cached helper function that performs the set transformation internally, caching the final `set` object instead of forcing the frontend code to rebuild it from the cached DataFrame on every interaction.

## 2025-02-20 - [Pandas Mapping]
**Learning:** Using `.map(lambda x: my_dict.get(x, x))` executes row-by-row in a slow Python loop and should be avoided in Pandas.
**Action:** Use vectorized `.replace(my_dict)` or `.map(my_dict).fillna(df["column"])` for much faster performance when mapping string columns with dictionary lookups and default fallbacks.

## 2026-05-18 - [Pandas] Vectorized Dictionary Mapping
**Learning:** Pandas `.map()` executes with significant overhead when passed a Python `lambda` function, as it iterates row-by-row in the Python interpreter. Passing a dictionary to `.replace()` leverages vectorized C-level execution for exact-match replacement and naturally leaves unmatched values alone (mimicking `.get(x, x)`), which is much faster.
**Action:** Always replace `.map(lambda x: my_dict.get(x, x))` with `.replace(my_dict)` when applying dictionary lookups to Pandas Series.

## 2026-05-20 - [Performance] Cache full names subset for get_authorized_tables
**Learning:** Streamlit's `@st.cache_data` heavily deep-copies large DataFrames, leading to high CPU/memory deserialization overhead even when cached. When only a subset of the data (like a `set` of names) is required, extracting that logic into its own `@st.cache_data` function that returns the minimal primitive type drastically avoids this deserialization overhead.
**Action:** Introduced `get_authorized_table_names` helper which returns a cached `set` rather than filtering/converting the full `DataFrame` repeatedly, reducing table access control checks from ~0.087s to ~0.028s per 100 calls.
