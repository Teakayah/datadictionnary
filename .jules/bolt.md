- For periodic background polling or auto-refreshing in Streamlit UI components, avoid using `time.sleep()` combined with `st.rerun()`, as it blocks the main execution thread and freezes the entire interface for the duration of the sleep.
- Instead, use non-blocking alternatives like `st_autorefresh` from the `streamlit-autorefresh` package, which schedules UI updates via the browser asynchronously without halting Python execution.
## 2026-05-13 - [Pandas] Vectorized operations vs .apply()
**Learning:** Pandas `.apply()` executes with significant overhead as it loops in Python. Vectorized `.str` operations are dramatically faster.
**Action:** Always prioritize native vectorized methods (e.g., `.fillna()`, `.astype(str)`, `.str.strip()`) over `.apply()` for filtering and string operations in DataFrames.
## 2026-05-15 - [Pandas] Vectorized operations vs .apply() for complex scoring
**Learning:** Pandas `.apply()` executes with significant overhead as it loops in Python. Vectorized `.str` operations and `numpy.select()` for conditional logic are dramatically faster, especially on large datasets like metadata searches.
**Action:** Always prioritize native vectorized methods and `numpy.select()` over `.apply()` for complex row-by-row scoring or conditional logic in DataFrames.
## 2026-05-18 - [Pandas] Vectorized Dictionary Mapping
**Learning:** Pandas `.map()` executes with significant overhead when passed a Python `lambda` function, as it iterates row-by-row in the Python interpreter. Passing a dictionary to `.replace()` leverages vectorized C-level execution for exact-match replacement and naturally leaves unmatched values alone (mimicking `.get(x, x)`), which is much faster.
**Action:** Always replace `.map(lambda x: my_dict.get(x, x))` with `.replace(my_dict)` when applying dictionary lookups to Pandas Series.
