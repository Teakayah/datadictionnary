## Janitor Journal

## 2026-05-04 - [Ruff Unused Variable Fixes] **Learning:** Ruff's `--fix` flag for unused variables (F841) might only remove the left-hand variable assignment, leaving the right-hand pure expressions hanging (e.g., set comprehensions, or method calls that return DataFrames). **Action:** Always manually review and delete the entire line when fixing F841 to avoid leaving dead code, or refactor to preserve necessary side effects.

## 2024-05-03 - [Pandas Optimization] Replace iterrows with itertuples
**Learning:** `iterrows` is significantly slower than `itertuples(index=False)` for DataFrame iteration. When replacing, dictionary `.get` lookups on rows must be swapped with `getattr(row, field, default)` to handle NamedTuples appropriately. Similarly, when iteration is meant to construct dictionaries for parameterization (e.g., DuckDB inserts), using `.to_dict('records')` avoids iteration overhead completely. Also, when modifying global components tested in AppTest with heavy mocks like ThreadPoolExecutors, mock the executor `submit`/`as_completed` flows to run synchronously to prevent deadlocks and assertion misses.
**Action:** Always favor `.to_dict('records')` for dictionary construction and `itertuples(index=False)` for general iteration over `iterrows()`. Update row accesses to `getattr` instead of `[]` or `.get()`.

## 2026-05-01 - [Extract Demo Mode Helper] **Learning:** Repeated environment variable checks for DEMO_DATA were scattered across the codebase, making updates error-prone. **Action:** Created `is_demo_mode()` helper to consolidate the check. Future boolean env var checks should use dedicated getters.

## 2024-05-09 - [Remove Duplicated is_power_user] **Learning:** Found a duplicated implementation of `is_power_user()` in `src/auth.py` and `src/personalization.py`. The `src/auth.py` version lacked the critical global `is_editing_enabled()` check. Global utility duplication can lead to security bypasses if developers import from the wrong location. **Action:** Removed the incomplete duplicate from `src/auth.py`. Ensure RBAC functions are strictly centralized and not re-implemented ad-hoc.

## 2026-05-10 - [Ruff Unused Variable Fixes Limitation]
**Learning:** Ruff's `--fix` flag for unused variables (F841) might only remove the left-hand variable assignment, leaving the right-hand pure expressions hanging (e.g., set comprehensions, or method calls). This can lead to SyntaxErrors if the assignment was part of a multiline `with` block patch statement.
**Action:** Always manually review and fix F841 to avoid leaving dead code or invalid syntax, rather than relying solely on `--unsafe-fixes`.

## 2026-05-14 - [Avoid Unstopped Patches] **Learning:** When refactoring tests to use actual storage dependencies and mocking those dependencies, using `unittest.mock.patch("...").start()` without explicitly stopping the mock will cause test pollution. Since pytest fixtures (like `monkeypatch`) do not have `self.addCleanup` like `unittest.TestCase` does, adding cleanup requires setting an explicit teardown mechanism (e.g. `monkeypatch.setattr("pytest.MonkeyPatch", lambda: patcher.stop())` or using a `with` block). **Action:** Always clean up global mocks created via `.start()` inside pytest functions to avoid cascading failures in subsequent tests.

## 2026-05-15 - [Remove src/ui/cards re-export shim]
**Learning:** The `src/ui/cards/__init__.py` re-export shim was kept for backwards compatibility during a refactor. It's better to update the callers to import from specific submodules directly to remove this technical debt.
**Action:** Migrated the remaining callers (`app.py`, `src/pages/catalog.py`, `src/pages/search.py`, `tests/test_admin.py`) off the shim and deleted `src/ui/cards/__init__.py`.

## 2026-05-20 - [Fix Module Docstring Ordering]
**Learning:** In Python, module docstrings must be the very first statement in the file, even before `from __future__ import` statements. Placing `from __future__ import annotations` before the module docstring causes subsequent imports to trigger `E402 Module level import not at top of file` linting errors because the docstring is then parsed as a regular string literal expression occurring after an import.
**Action:** Always place module docstrings at the absolute top of the file (line 1), followed immediately by `__future__` imports, and then standard imports.
