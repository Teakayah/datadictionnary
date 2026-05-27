## 2025-05-21 - Mocking dimension bug in Embeddings
**Learning:** Found a bug in MockEmbeddingEngine where small strings generated vectors < 384 dimensions. This can lead to flaky tests if other components implicitly expect fixed sizes for embeddings.
**Action:** Always ensure mocks for vector databases or embedding engines strictly conform to the expected dimensional constraints of the real service.

## 2026-05-22 - Missing tests for CMS admin component
**Learning:** The CMS admin creation dialog and post rendering (`src/ui/cards/cms_admin.py`) are largely untested and suffer from extremely poor line coverage (14%). These dialogs contain validation and submission logic that could break if refactored.
**Action:** Adding comprehensive UI component tests (`AppTest`) for `_show_cms_create_dialog` and `_render_admin_cms_section` handling the creation flow, input validation, expired state rendering, and delete functionality.
## 2025-05-26 - Fix flaky tests with module-level patching
**Learning:** Constants imported from `src.config` must be patched in the module they are imported into (like `src.semantic.DATABRICKS_EMBEDDING_ENDPOINT`), rather than patching `os.environ`, because the constant is evaluated at import time.
**Action:** Use `@patch("src.module.CONSTANT", "value")` instead of `@patch.dict(os.environ, ...)` when testing code that relies on environment-derived constants.
