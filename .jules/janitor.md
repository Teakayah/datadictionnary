## 2025-02-28 - [Cleanup] Unused redefined class in test_pipelines.py
**Learning:** Found a redefinition of the `TestGetPipelines` class in `tests/test_pipelines.py`. Redefining a test class name can lead to test suppression, as the second definition completely overrides the first.
**Action:** Always rename test classes to be unique if they test different aspects of the same functionality.

## 2025-05-27 - Ruff Unused Imports Cleanup
**Learning:** Found several unused imports in the codebase. Ruff identifies these cleanly, but tests may fail if the module directly patches `os.environ` to update constants imported directly from `config.py`.
**Action:** Patch the module-level attribute directly instead of `os.environ` for imported constants.

## 2025-02-28 - [Cleanup] Dead code and shadowing functions in tests
**Learning:** Found an unused `_read_locale_source` function and a duplicate `_read_locale_strings` function in `tests/test_app.py`. Duplicate function definitions can shadow previous ones and cause subtle logic bugs.
**Action:** Scan for duplicate function names during refactors. Removing shadow definitions restores the original signature and eliminates logic masking bugs.
