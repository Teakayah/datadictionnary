## 2024-05-27 - [Fix test_get_embedding_engine_databricks]
**Coverage Gap:** `test_get_embedding_engine_databricks` failed due to incorrect mocking of environment variable derived config constant.
**Learning:** When a configuration constant is derived from an environment variable and imported directly at the module level (e.g., `from src.config import DATABRICKS_EMBEDDING_ENDPOINT`), tests using `@patch.dict(os.environ, ...)` fail because the constant is resolved at import time.
**Action:** Patch the variable directly in the module namespace where it is used (e.g., `@patch('src.semantic.DATABRICKS_EMBEDDING_ENDPOINT', 'my-endpoint')`) to reliably override the value during tests.
## 2026-06-03 - NotificationStorage Coverage
**Coverage Gap:** DemoNotificationStorage and DuckDBNotificationStorage in src/storage/notification_storage.py had no unit tests, leaving persistent tracking of changes untested.
**Learning:** The application mocks dependencies deeply at the module level in tests (e.g., using a duckdb tmpfile). Exceptions from DB disconnections needed to be validated using pytest's mock framework. When using `unittest.mock.patch` to override environment variables across imported modules in Pytest fixtures, `monkeypatch` should be used instead of `importlib.reload()` sequence which could break object identity.
**Assertion:** Created test_storage_notifications.py to instantiate local instances of DuckDBNotificationStorage and DemoNotificationStorage and execute assertions for list limits, mark read, and simulate broken DB connections.
