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
## 2025-02-27 - [Suppressing Linter Warnings for Dynamic Imports]
**Learning:** When resolving linter warnings for unused imports, running `ruff check . --fix` can aggressively remove seemingly "unused" local imports (e.g., `import streamlit as st` inside test wrapper functions) that are actually required for dynamic execution or framework wrappers like `AppTest`.
**Action:** Do not use `--fix` blindly on test files, or ensure you manually restore required local imports with `# noqa: F401` to prevent test suite regressions while satisfying the linter.

## 2026-08-24 - Unnecessary complex operation over DataFrame for set extraction
**Learning:** Found `set(get_authorized_tables(groups)["full_name"].unique().tolist())` which unnecessarily downloads all table columns into a pandas dataframe then does a complex transformation, when a simpler optimized `get_authorized_table_names(groups)` which returns the set directly is available.
**Action:** Replaced the unoptimized extraction with the optimized `get_authorized_table_names(groups)` in `src/ui/cards/discovery.py`.
## 2026-09-17 - Consolidate Locale State Fetching
**Learning:** The application retrieved locale state across multiple files (`src/db/queries.py`, `src/pages/search.py`, `src/ui/header.py`, `src/i18n.py`) directly from `st.session_state.get("locale", "en")`. This approach leads to repeated code and risks missed initialization if `_ensure_locale()` isn't called prior.
**Action:** Always create a unified getter method (`get_current_locale()`) to encapsulate `session_state` access and ensure prerequisites (like `_ensure_locale()`) are satisfied.
## 2024-05-24 - Remove unused imports and variables
**Learning:** Found multiple unused variables (`F841`) and unused imports (`F401`) throughout the tests using Ruff. Streamlit imports (`import streamlit as st`) are frequently imported inside functions without actually being used. Unused variable assignments (`mock_md`, `mock_markdown`, `calls`, `row`) are also common in testing files.
**Action:** Use `ruff check . --select F401,F841 --fix` (with `--unsafe-fixes` where safe, like simple assignments) to aggressively clean up unused variables and unused imports, particularly those hidden inside function scopes in tests.
## 2026-10-24 - Unnecessary complex operation over DataFrame for set extraction
**Learning:** Found `set(all_tables["full_name"].unique().tolist())` which unnecessarily downloads all table columns into a pandas dataframe then does a complex transformation, when a simpler optimized `get_authorized_table_names(groups)` which returns the set directly is available.
**Action:** Replaced the unoptimized extraction with the optimized `get_authorized_table_names(groups)` in `src/ui/cards/discovery.py`.
## 2025-02-27 - [Suppressing Linter Warnings for Dynamic Imports]
**Learning:** When resolving linter warnings for unused imports, running `ruff check . --fix` can aggressively remove seemingly "unused" local imports (e.g., `import streamlit as st` inside test wrapper functions) that are actually required for dynamic execution or framework wrappers like `AppTest`.
**Action:** Do not use `--fix` blindly on test files, or ensure you manually restore required local imports with `# noqa: F401` to prevent test suite regressions while satisfying the linter.
## 2025-02-20 - Removed Duplicate Streamlit Cache Wrapper
**Learning:** Found a redundant local wrapper `_cached_get_authorized_table_names` around `get_authorized_table_names` in `src/pages/glossary.py`. The base function `get_authorized_table_names` in `src/db/queries.py` is already wrapped with `@st.cache_data`. This extra wrapper caused duplicate caching layers and unnecessary memory overhead.
**Action:** Removed the duplicate wrapper in `src/pages/glossary.py` and updated all callers to import and use the base function directly from `src/db/queries.py`.
