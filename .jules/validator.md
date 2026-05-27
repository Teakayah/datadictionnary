## 2024-05-27 - [Fix test_get_embedding_engine_databricks]
Coverage Gap: test_get_embedding_engine_databricks failed due to incorrect mocking of environment variable derived config constant.
Learning: When a configuration constant is derived from an environment variable and imported directly at the module level, tests using `@patch.dict(os.environ, ...)` fail because the constant is resolved at import time.
Assertion: Patch the variable directly in the module namespace where it is used (e.g., `@patch('src.semantic.DATABRICKS_EMBEDDING_ENDPOINT', 'my-endpoint')`).
