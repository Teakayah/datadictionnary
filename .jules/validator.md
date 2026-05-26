## 2025-02-27 - Fixing DatabricksEmbeddingEngine mock failing due to import location
Coverage Gap: `test_get_embedding_engine_databricks` was failing because the test attempted to mock `os.environ` to control `DATABRICKS_EMBEDDING_ENDPOINT`.
Learning: Because `src.semantic` imported `DATABRICKS_EMBEDDING_ENDPOINT` directly from `src.config` (`from src.config import DATABRICKS_EMBEDDING_ENDPOINT`), mocking `os.environ` was ineffective since the constant had already been resolved at import time.
Assertion: To reliably test code relying on directly imported configuration constants, patch the constant in the module where it is used (e.g., `@patch("src.semantic.DATABRICKS_EMBEDDING_ENDPOINT", "my-endpoint")`) instead of patching `os.environ`.
