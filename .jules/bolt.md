## 2024-05-21 - Optimizing Catalog Tree Rendering
**Learning:** Calling `groupby()` and `.unique().tolist()` repeatedly inside a Streamlit render loop over large DataFrames acts as a severe performance bottleneck (effectively O(N^2)).
**Action:** Pre-compute relationships by applying `.apply(list).to_dict()` on a global groupby before the render loop, allowing O(1) dictionary lookups for nested data structures.

## 2024-05-22 - [Performance] Optimize pandas dataframe arbitrary list sorting
**Learning:** Using `.map` with an enumerated dictionary to create a temporary sort order column is slower and allocates more memory than using pandas native `Categorical` type.
**Action:** Always use `pd.Categorical(..., categories=target_list, ordered=True)` when sorting a DataFrame based on a specific arbitrary list of items.

## 2026-05-22 - Document false positive cache rationale in health dashboard
**Learning:** When an issue incorrectly identifies a performance problem that conflicts with an architectural constraint (e.g., ADR 002 enforcing SQL push-down vs. Python/Pandas in-memory aggregation), do not force an unnecessary refactor.
**Action:** Documented the false positive via an inline comment using the active persona's format.
