## 2024-06-02 - Unused Parameter in `render_health`
**Learning:** I found an unused parameter in `render_health` (`_unused_fn`) which was passed `get_authorized_tables` in `app.py`. This unused parameter is confusing and we can safely remove it from `src/ui/cards/health.py` and `app.py`
**Action:** Remove `_unused_fn` from `render_health`.
## 2026-06-10 - Prop Drilling Removal in UI Components
**Learning:** Functions like `get_authorized_tables` that are needed by deep UI components (like `render_discovery` or `render_catalog_browser`) were being passed down as parameters all the way from `app.py` (prop drilling). This added unnecessary complexity to the function signatures and bloated the top-level app configuration.
**Action:** Removed prop drilling of `get_authorized_tables`. Directly import it into the specific UI components (`src/ui/cards/discovery.py`, `src/pages/catalog.py`) where it is actually used, simplifying `app.py` and making the component signatures cleaner. Tests should be updated to use `@patch` on the specific module's import space instead of passing mock functions.
## 2026-07-03 - Prop Drilling Removal in UI Components
**Learning:** Functions like `get_authorized_tables` or `_pref_delete`/`_pref_upsert` that are needed by deep UI components (like `render_discovery` or `render_catalog_browser`) were being passed down as parameters all the way from `app.py` (prop drilling). This added unnecessary complexity to the function signatures and bloated the top-level app configuration.
**Action:** Removed prop drilling. Directly import them into the specific UI components (`src/ui/cards/discovery.py`) where it is actually used, simplifying `app.py` and making the component signatures cleaner. Tests should be updated to use `@patch` on the specific module's import space instead of passing mock functions.

## 2026-06-24 - Removed orphaned src/storage directory
**Learning:** The `src/storage` abstraction layers for DuckDB vs Session State were decoupled from caller files and completely removed since they were mostly refactored away and only a single usage in the codebase remained (OE-1). This removes 7 completely unused files, 3 test files, and reduces codebase complexity.
**Action:** Removed orphaned `src/storage/` files along with related storage-specific test files `tests/test_storage_*.py`. Refactored the remaining usage in `src/ui/cards/detail.py`.

## 2026-08-24 - Unnecessary complex operation over DataFrame for set extraction
**Learning:** Found `set(get_authorized_tables(groups)["full_name"].unique().tolist())` which unnecessarily downloads all table columns into a pandas dataframe then does a complex transformation, when a simpler optimized `get_authorized_table_names(groups)` which returns the set directly is available.
**Action:** Replaced the unoptimized extraction with the optimized `get_authorized_table_names(groups)` in `src/ui/cards/discovery.py`.
