## 2024-05-24 - Python Docstring Standard Violation
**Learning:** Python files in this repository incorrectly use JSDoc/TSDoc style docstrings (@param, @returns) instead of standard Google style (Args:, Returns:).
**Action:** Ensure all new and refactored Python docstrings strictly follow the Google Style Guide.
## 2024-07-01 - Missing environment variable documentation in .env.example
**Learning:** The semantic search feature requires specific environment variables (`ENABLE_SEMANTIC_SEARCH` and `DATABRICKS_EMBEDDING_ENDPOINT`) to function, but these were missing from the provided `.env.example` file.
**Action:** Always ensure that new features introducing environment variables have those variables properly documented and included in example configuration files to assist developers in setting up their environments correctly.
## 2024-07-13 - Python Module Docstring and Future Imports
**Learning:** In Python, the module-level docstring must always be the very first statement in a file. Placing `from __future__ import annotations` or other `__future__` imports before the docstring converts the intended docstring into a regular string expression. This causes all subsequent imports to fail Ruff's `E402` (Module level import not at top of file) check because Ruff considers the string expression as executable code preceding the imports.
**Action:** Always ensure the precise order: 1) Module docstring, 2) `__future__` imports, 3) Standard imports. When adding docstrings to files, verify that `__future__` imports are correctly positioned below the new docstring.
## 2024-08-17 - Module Docstring Position
**Learning:** In Python files, module-level docstrings (`"""..."""`) must be placed as the absolute first statement in the file, preceding all imports (including `from __future__ import annotations`). Placing imports before the module docstring demotes it to a regular string expression and triggers Ruff `E402` (Module level import not at top of file) errors.
**Action:** Ensure the module docstring is always the first statement in a file when creating or refactoring files.
