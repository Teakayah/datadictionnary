## 2024-05-24 - Python Docstring Standard Violation
**Learning:** Python files in this repository incorrectly use JSDoc/TSDoc style docstrings (@param, @returns) instead of standard Google style (Args:, Returns:).
**Action:** Ensure all new and refactored Python docstrings strictly follow the Google Style Guide.
## 2024-07-01 - Missing environment variable documentation in .env.example
**Learning:** The semantic search feature requires specific environment variables (`ENABLE_SEMANTIC_SEARCH` and `DATABRICKS_EMBEDDING_ENDPOINT`) to function, but these were missing from the provided `.env.example` file.
**Action:** Always ensure that new features introducing environment variables have those variables properly documented and included in example configuration files to assist developers in setting up their environments correctly.
