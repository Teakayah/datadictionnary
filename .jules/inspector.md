## 2024-06-24 - Test Argument Ordering with Fixtures
**Learning:** When combining `@patch` decorators with `pytest` fixtures in test function signatures, the mock arguments created by `@patch` must be listed *before* any pytest fixtures in the parameter list. Placing a mock argument after a fixture causes pytest to attempt to inject it as a fixture, resulting in "fixture not found" errors.
**Action:** Always structure test arguments as `(self, mock_1, mock_2, ..., fixture_1, fixture_2)` when mixing both approaches to prevent fixture resolution errors.
## 2024-05-27 - [Fix test_get_embedding_engine_databricks]
**Coverage Gap:** `test_get_embedding_engine_databricks` failed due to incorrect mocking of environment variable derived config constant.
**Learning:** When a configuration constant is derived from an environment variable and imported directly at the module level (e.g., `from src.config import DATABRICKS_EMBEDDING_ENDPOINT`), tests using `@patch.dict(os.environ, ...)` fail because the constant is resolved at import time.
**Action:** Patch the variable directly in the module namespace where it is used (e.g., `@patch('src.semantic.DATABRICKS_EMBEDDING_ENDPOINT', 'my-endpoint')`) to reliably override the value during tests.
## 2026-06-03 - NotificationStorage Coverage
**Coverage Gap:** DemoNotificationStorage and DuckDBNotificationStorage in src/storage/notification_storage.py had no unit tests, leaving persistent tracking of changes untested.
**Learning:** The application mocks dependencies deeply at the module level in tests (e.g., using a duckdb tmpfile). Exceptions from DB disconnections needed to be validated using pytest's mock framework. When using `unittest.mock.patch` to override environment variables across imported modules in Pytest fixtures, `monkeypatch` should be used instead of `importlib.reload()` sequence which could break object identity.
**Assertion:** Created test_storage_notifications.py to instantiate local instances of DuckDBNotificationStorage and DemoNotificationStorage and execute assertions for list limits, mark read, and simulate broken DB connections.
## 2024-06-09 - Coverage Gap: Auth Configuration Edge Cases
**Coverage Gap:** The error branches for missing environment variables (`TENANT_ID`, `CLIENT_ID`/`API_AUDIENCE`) in both the startup check `_validate_auth_config` and the per-request validation `validate_token` were completely untested, as well as the mock authentication pathways.
**Learning:** Testing these edge cases requires careful monkeypatching of the environment variables (e.g. `monkeypatch.delenv`) and overriding `src.api.auth.TENANT_ID`/`CLIENT_ID` which are imported at the module level.
**Assertion:** Use `monkeypatch.setattr` on the specific module variables `src.api.auth.TENANT_ID` and `monkeypatch.delenv` to simulate missing configuration, and `pytest.raises` to ensure `RuntimeError` is correctly thrown to prevent silent bypass of authentication.
## 2024-06-10 - Mocking Streamlit Session State and DuckDB Cursors
**Learning:** When using Streamlit `AppTest` to verify nested UI state reliant on user sessions, the `st.session_state` properties (like `user_oid`) must be mocked and set directly on the `at.session_state` object before `at.run()`. Similarly, when mocking DuckDB connections that utilize context managers returning custom cursors, the mock must replicate the exact nested `__enter__` and `__exit__` pattern for cursors alongside providing methods like `fetchall_as_pandas` to prevent test crashes.
**Action:** Ensure custom database adapters gracefully handle closed connections and empty query results, and properly document UI notification strips when unread notifications are mocked.
## 2026-06-14 - NotificationStorage Coverage
**Learning:** The application mocks dependencies deeply at the module level in tests. Exceptions from DB disconnections needed to be validated using pytest's mock framework. When mocking functions like `_get_write_connection` imported within another module's method scope, we must correctly target the import location in Pytest mock.
**Action:** Created test_storage_notifications.py and test_storage_audit.py to instantiate local instances of DuckDBNotificationStorage, DemoNotificationStorage, DuckDBBusinessNameOverrideStorage, FakeBusinessNameOverrideStorage, DemoAuditStorage, and DuckDBAuditStorage to execute assertions for list limits, mark read, and simulate broken DB connections.
## 2026-06-18 - Mocking DuckDB cursors in notifications
**Learning:** When mocking DuckDB cursors that use context managers (e.g. `with conn.cursor() as cur:`), the mock object must implement `__enter__` and `__exit__` properly alongside `execute` to prevent exceptions in the tests.
**Action:** When mocking DuckDB connection APIs returning cursors or context managers, assign `.return_value.__enter__.return_value` to the mock cursor.
## 2026-06-22 - Improve DaemonConn coverage
**Learning:** Simple wrapper classes often lack line coverage, and patching dependencies directly inside test functions ensures these gaps are covered.
**Action:** When testing wrapper classes around database connections, ensure methods like `cursor()`, `execute()`, and context managers (`__enter__`) are covered using mocked connections to prevent regressions in connection management logic.
## 2024-06-20 - Coverage Gap: FastAPI Dependency Edge Cases
**Coverage Gap:** The `get_current_user` dependency in `src/api/deps.py` missed coverage for its `RuntimeError` and `ValueError` exception paths, meaning error handling for authentication misconfiguration and invalid tokens was completely untested.
**Learning:** Testing exception handling in FastAPI dependencies requires patching the underlying functions that raise the exception (`validate_token`) and asserting the specific `HTTPException` properties (status code, detail, and headers).
**Action:** Created `tests/test_api_deps.py` to mock `validate_token` side-effects and use `pytest.raises(HTTPException)` to verify the correct HTTP status codes and details are returned for invalid tokens and server misconfigurations.
## 2024-06-16 - Exception paths in storage fallback
**Learning:** The application routes per-entity storage operations (like user preferences and site settings) directly to DuckDB via `src.personalization`. These database calls are wrapped in generic `try/except Exception` blocks to prevent missing tables from crashing the UI. However, the exception paths inside `_get_site_setting`, `_set_site_setting`, `_pref_upsert`, and `_pref_delete` were entirely untested, leaving us blind to how the app handles critical database failures.
**Action:** Backfilled unit tests targeting the `side_effect=Exception` paths for these database operations. Next time, always ensure try/except handlers interacting with the DB are explicitly tested to verify silent fallbacks.
## 2026-06-25 - CMSStorage Coverage
**Coverage Gap:** The classes `DemoCMSStorage`, `DuckDBCMSStorage`, and `FakeCMSStorage` in `src/storage/cms_storage.py` had no direct unit test coverage, leaving the actual backend persistence untested.
**Learning:** Adding test coverage for storage protocols requires testing both the demo/in-memory classes and mocking database connections for the persistent DuckDB classes to prevent exception-path regressions.
**Assertion:** Created `tests/test_storage_cms.py` with mock db tests covering DB interactions and fallbacks for `DuckDBCMSStorage` and basic functionality tests for `DemoCMSStorage` and `FakeCMSStorage`.
## 2026-06-26 - Added test coverage for audit missing paths
**Coverage Gap:** src/audit.py had significant missing coverage for `_append_audit_event`, `_upsert_column_override`, and others in demo/production paths.
**Learning:** Testing demo vs production branching requires careful patching of `st.session_state` dict-like structures (e.g. `_DEMO_BN_KEY`) vs `_get_write_connection()`.
**Assertion:** Wrote comprehensive edge cases covering these gaps and improving overall src.audit coverage from 47% to 64%.
## 2024-06-28 - Missing coverage for table friendly name approvals
**Learning:** The UI logic for approving/rejecting table friendly name reviews lacked automated UI test coverage in the admin module, which is a critical workflow for data stewards.
**Action:** Implemented AppTest integration tests for `list_pending_table_business_names`, `approve_table_business_name`, and `reject_table_business_name` and simulated button clicks to improve admin module reliability.
## 2026-06-29 - [Coverage Gap: src/storage/preference_storage.py]
**Learning:** `DuckDBPreferenceStorage`, `DuckDBSiteSettingStorage`, `FakePreferenceStorage`, `FakeSiteSettingStorage`, `DemoPreferenceStorage` and `DemoSiteSettingStorage` lacked unit tests, leaving persistent tracking of preferences untested.
**Action:** Backfilled unit tests in `tests/test_storage_preference.py` for all storage adapters inside `src/storage/preference_storage.py` and validated database interaction and exception fallback scenarios.
