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
## 2026-06-30 - Streamlit AppTest Authentication and Component Execution
**Learning:** Testing interactive components (like buttons) inside Streamlit `AppTest.from_function()` requires the `streamlit` module and the tested components to be imported *inside* the function scope because it runs in an isolated ScriptRunner context. Additionally, full UI tests on components utilizing MSAL authentication require `MOCK_LOGIN="true"` and appropriate group environment variables to bypass actual AAD token requests, which would otherwise crash tests.
**Action:** Always import `streamlit` and target modules inside the `app()` function when using `AppTest.from_function()`. Ensure `MOCK_LOGIN="true"` and relevant groups (e.g., `ADMIN_GROUPS="Data_Admin"`) are set via `monkeypatch` before initializing full-app integration tests that touch UI auth barriers.

## 2026-06-19 - Admin Data Fetchers Coverage
**Learning:** Many read-only utility fetchers (e.g. `get_admin_stats`, `get_business_name_change_log`) located within UI view modules were missing coverage for both demo mode and DuckDB branches. Additionally, Streamlit tests using `AppTest` execute scripts in a separate context, meaning test-level module patches (like `patch`) can leak state into subsequent module-level imports unless the module is explicitly reloaded within the test class or patched cleanly at the correct module-import level (e.g., patching `src.ui.cards.admin.run_query` instead of relying on a global mock cursor that `conftest` handles).
**Action:** Created `TestAdminDataFetchers` class to assert data extraction and fallback conditions for these fetchers under both `is_demo_mode=True` and `_duckdb_available=True`. Explicitly used `importlib.reload(sys.modules["src.ui.cards.admin"])` in the `setup_class` to prevent leaking test patches.

## 2026-07-02 - Mock Test Context Leakage & Missing Standard Library Imports
**Learning:** When patching global connection methods in pytest, locally instantiated test objects (like DuckDBSiteSettingStorage) must be explicitly initialized within the mock's context block, otherwise tests can leak state or throw NameErrors when variables are accessed outside the mock context. Additionally, production components using standard library utilities like 'secrets' must import them locally rather than relying on global namespaces that may hide module absence during certain test initializations.
**Action:** Ensure all explicitly asserted mock result objects are defined within the patched 'with' context, and verify standard library imports explicitly in DB driver/connection wrapper modules.
## 2026-07-06 - CMS Admin Dialog Missing Coverage
**Learning:** When using Streamlit dialogs (like `@st.dialog`), isolating the component in a test function wrapper enables interaction testing through `AppTest.from_function()` without needing to simulate the full page logic. The `_show_delete_cms_dialog` in `src/ui/cards/cms_admin.py` had no test coverage, missing assertions for user interactions like cancel/confirm during post deletion.
**Action:** Always isolate `@st.dialog` components into local wrapper functions inside test files to enable targeted UI interaction coverage via `AppTest.from_function()`.

## 2026-07-18 - Fix failing Streamlit Segmented Control Test Asserts
**Learning:** Testing component rendering inside Streamlit's `st.segmented_control` blocks with AppTest fails because updating `at.session_state` or `at.segmented_control(...).set_value()` does not correctly trigger the internal Streamlit rerender mapping the new active value, especially when the options are tied to dynamic keys like translated strings.
**Action:** When asserting the presence of components that render conditionally on `st.segmented_control` values, bypass the widget behavior by explicitly mocking the output using `with patch('src.ui.cards.admin.st.segmented_control') as mock_sc: mock_sc.return_value = "Quality Insights"` and ensuring the patched value exactly matches the generated option values during runtime rendering.

## 2026-07-15 - DuckDB Connection Singleton and Cursor Edge Cases
**Learning:** Testing lock-protected singleton initializations requires careful mocking of initialization steps inside a patched lock to prevent race conditions in tests. `_DuckDBCursor` mock execution tests must simulate context manager operations returning instances of `self` for accurate fetch execution tracking.
**Action:** Backfilled unit tests targeting the `side_effect=Exception` and connection instantiation paths for the DuckDB shared connection logic to reach 100% test coverage on `duckdb_adapter.py`.
## 2026-07-20 - API Endpoint Cache Hit Coverage Gap
**Learning:** API endpoints utilizing cache checks (e.g. `redis_cache.get()`) need dedicated tests simulating cache hits. Without these, the `return cached` lines remain uncovered, and there's no verification that the application correctly bypasses database queries when data is already cached.
**Action:** When adding or auditing API endpoints with caching logic, write tests using `unittest.mock.patch` to return mock data from the cache and assert that the underlying query functions are explicitly `not_called()`.

## 2026-07-22 - Comprehensive testing of table business name audit flows
**Learning:** The audit component uses complex dictionary mutations on Streamlit's `session_state` during demo mode, coupled with Database operations (`_get_write_connection`, `get_db_connection`) during production. The `test_audit.py` coverage for these logic branches was inadequate. The structure in `src/audit.py` specifically uses a complex dictionary of dictionaries (`table_full_name` as top-level keys mapped to properties) along with a `setdefault` pattern for demo mode.
**Action:** Added extensive unit testing covering both `demo_mode` and production paths for fetching, upserting, approving, rejecting, and validating the table-level bilingual business name overrides within `tests/test_audit_table_business_name.py`.
## 2026-07-25 - Pipeline Backend Poll and DB Exception Handling Paths
**Coverage Gap:** `src/pipelines.py` was missing test coverage for the core DuckDB insert/delete/fetch paths for pipeline definitions and active runs (`get_pipelines`, `get_active_run`, `create_pipeline_def`, `_save_run`). Furthermore, the `poll_run_status` function had uncovered execution branches mapping external backend systems (Databricks, ADF, ADO) and their exception recovery blocks.
**Learning:** For external state polling architectures, ensuring `side_effect=Exception` paths in the test suite verifies that UI components handle downstream backend failures gracefully, rather than propagating raw 500 crashes to the front end.
**Action:** Backfilled unit tests in `tests/test_pipelines.py` simulating mock database connections and mocked API responses to validate DB execution and error states, achieving 100% test coverage for `src/pipelines.py`.
## 2026-07-27 - Test Admin Dialogs and Integrity Reports
**Learning:** `AppTest` wrapper assertions fail when attempting to read state related to dialogs (`@st.dialog`) unless the internal logic of the app is cleanly mocked or isolated. Similarly, `AppTest.info` expects components like `st.info` to match exact lengths when testing empty fallback states, which caused test failures when new components were added or removed without updating the assertions in `test_admin.py` for `_render_admin_integrity_report` or dialog wrappers.
**Action:** Always wrap isolated `st.dialog` components inside an internal `app()` wrapper, explicitly checking the components exist, and when validating empty states across multiple fallback queries (like `get_high_impact_gaps`), assert the presence of at least one `st.info` message instead of an exact arbitrary number. Ensure we catch DB exception boundaries using `side_effect=Exception` to test `st.error` fallback handlers in UI actions like `approve_table_business_name` or `reject_business_name`.
## 2023-10-27 - Semantic Search Fallbacks Testing
**Learning:** Edge cases around loading dynamic extensions in DuckDB (e.g. `LOAD vss` throwing an exception and falling back to `INSTALL vss`) are critical failure paths that require multi-stage patching (e.g. tracking `call_count` inside side_effects) to properly test without a real environment.
**Action:** When testing dynamic SQL extension loading logic, always use isolated mock states with custom side_effect functions to simulate first-pass failures and second-pass successes in the same execution flow.

## 2024-11-20 - Fix Flaky AppTest Render Re-runs and Fallbacks
**Learning:** Testing UI fallback components (e.g. error rendering) in Streamlit `AppTest.from_function()` using patched exception raising components requires you to wrap the test component in a localized test function that also wraps the mock `patch` context rather than placing the patch externally. Furthermore, UI interactions producing transient messages (e.g. `st.error`) prior to `st.rerun()` wipe out testable messages from `AppTest.error` because the rerun causes the app test context tree to flush the error node instantly.
**Action:** Always mock target exception paths from within the wrapper function supplied to `AppTest.from_function()` when writing tests for exceptions, and never call `st.rerun()` in the exception handling block after rendering a transient message (like `st.error()`).
## 2026-08-18 - AppTest Isolation for Streamlit Navigation/Search Complex UI
**Learning:** Testing complex Streamlit components (like search result pages and related table expansion) requires explicitly isolating `AppTest.from_function()` by overriding session state immediately before or after `.run()`, and stubbing out all backend DB queries (`search_all_metadata`, `get_authorized_tables`, `run_query`). AppTest fails with attribute errors internally if patched components are leaked between test scopes.
**Action:** When creating tests for heavy frontend search logic, define an inner wrapper function that patches necessary methods inside the context manager instead of the file-level scope, to avoid leaking or overwriting globally imported methods.

## 2024-05-24 - Cover missing _fetch_metadata_for_fns in DB Queries
**Learning:** The `_fetch_metadata_for_fns` utility, which is heavily relied upon by the semantic search fallback mechanism (Hybrid Fusion), was completely mocked out in all semantic tests (`test_semantic.py`). This left a critical SQL construction point and logic gap untested, which could silently break semantic search.
**Action:** Added dedicated unit tests for DB layer utilities in `tests/test_db_queries.py` to ensure raw SQL construction for fetching metadata is validated without being obscured by higher-level mocks.
## 2026-08-22 - Graceful Error Handling for Streamlit Components
**Learning:** In Streamlit, unhandled exceptions inside button callback logic (such as saving to a database in `save_comment`) will crash the entire application via a runtime `Exception`. This degrades reliability significantly since typical user actions can bring down the UI.
**Action:** When wrapping backend operations in UI components, always encapsulate risky calls (like DB saves) within a `try/except` block, log the stack trace using `logging.error`, and display a localized, safe warning to the user using `st.error()` so the interface remains stable and functional.

## 2026-08-26 - Streamlit AppTest rerun handling in UI button tests
**Learning:** Mocking `streamlit.rerun` using `with patch("streamlit.rerun")` when interacting with buttons in `AppTest` is an anti-pattern. `AppTest` natively handles the `st.rerun()` control flow execution loop. Mocking it suppresses this behavior and can leave test state assertions incomplete or break execution flow.
**Action:** When writing tests that trigger a component rerun (e.g. `at.button(...).click().run()`), never patch `streamlit.rerun`. Let `AppTest` handle the reruns natively and assert state immediately following the `.run()` block.

## 2026-09-03 - Mocking Missing Standard Libraries in Streamlit AppTest
**Learning:** When using `AppTest.from_function()` to test a module that conditionally imports functions not available directly in the file context (such as lazy imports of `format_date` and `format_number` from `src.i18n`), standard patching using `patch("module.function")` will fail with an `AttributeError` because the mock machinery cannot find the function to replace.
**Action:** When mocking functions imported lazily or unavailable on the parent module during testing, explicitly pass `create=True` to the `patch()` call. This allows `unittest.mock` to forcefully inject the mock object and prevent `AttributeError` during execution within Streamlit `AppTest`.

## 2024-03-22 - Missing Exception Handling Tests for Live Completeness Score
**Learning:** Found a missing test scenario in `src.pages.search._render_detail_panel` where `_compute_live_completeness` can raise an exception. The application handles this exception by falling back to the `dq_score` from the row, but this was previously completely untested.
**Action:** When working with Streamlit session state and functions that can throw exceptions, explicitly add test cases to simulate those exceptions and verify the fallback logic correctly populates session state.
## 2026-09-13 - Streamlit session state get set default mutation
**Learning:** Testing UI flows that rely on `st.session_state.get('key', set()).add(...)` without the key being initialized reveals that modifying the returned default set does not implicitly write back to the Streamlit `session_state` during tests (or runtime), and standard asserts will fail because `st.session_state` was not populated. Furthermore, missing `.get()` default behaviors in tests obscure bugs where UI interacts with uninitialized state keys.
**Action:** When adding tests for UI actions that push or discard from session state collections (like bookmarks), ensure the session state is initialized appropriately (`at.session_state["key"] = set()`) before simulating the interaction, and assert against the initialized key instead of calling `.get()` blindly.

## 2024-11-20 - Testing dynamic nested component bookmarks
**Learning:** The nested column bookmarking logic in the UI iterates over dynamically generated `_col_bk_id` keys in `_render_detail_panel`. Tests were missing for this specific flow. It is important to explicitly seed and verify `at.session_state["col_bookmarks"]` sets when simulating interaction with these iterated buttons in `AppTest` because global bookmarks behave differently than localized column ones.
**Action:** When adding tests for nested/iterated components, ensure their underlying data structures and session state variables are correctly seeded as sets before invoking `AppTest.run()` to prevent `KeyError` or missing test coverage.

## 2026-09-17 - FastAPI Application Setup Coverage
**Learning:** The root `src/api/main.py` FastAPI file lacked top-level testing for routing inclusion and CORS setup, leaving middleware and API routing configuration untested. Even simple router integrations in FastAPI applications should be explicitly tested to catch silent failures during app initialization.
**Action:** Added `test_app_routing_and_cors` in `tests/test_api_main.py` to assert the app starts up with the correct lifespan context, explicitly tests CORS headers on an `OPTIONS` request, and verifies that the `live` health check router responds to `GET` requests.

## 2025-02-23 - Fix short-circuit logic treating empty dict as falsy in auto_ci
**Learning:** Using `base_env or os.environ` in `scripts/auto_ci.py` treats an empty dictionary `{}` as falsy, which causes the CI to unexpectedly fallback to system environment variables even when explicitly given an empty dict (such as in tests). This leads to tests like `test_build_environment_sets_ci_defaults` unexpectedly reading system variables (like `TENANT_ID="test-tenant-id"`) and failing.
**Action:** When short-circuiting optional dictionary arguments where `{}` is a valid and distinct state, always use explicit `is not None` checks like `base_env if base_env is not None else os.environ`.
## 2024-12-05 - Fix FastAPI dependency_overrides mutating global state in tests
**Learning:** When using `app.dependency_overrides` at the module level in FastAPI test files, it acts on the global application state. This causes intermittent 401 test failures when tests run concurrently or in batches, because other test files might call `app.dependency_overrides.clear()`, wiping out the required authentication overrides.
**Action:** Always scope FastAPI `dependency_overrides` to a localized `pytest.fixture` (e.g., using `autouse=True` or explicitly yielding the client) that sets the override before testing and clears it afterward.
## 2024-12-06 - Missing DuckDB Adapter Exception Testing
**Learning:** `duckdb.InvalidInputException` is a C-extension exception thrown by DuckDB when `executemany` is called with an empty list. The mock `MagicMock` does not emulate this behavior natively, so the application code handles this without test coverage. To properly test this exception path without the real database backend, it must be explicitly configured as the `side_effect` on the mock `executemany` call. Furthermore, queries constructed using non-pyformat standard parameters (like `?`) inside `duckdb_adapter` must also be explicitly covered in the tests.
**Action:** When testing DuckDB adapter methods like `executemany`, always configure `MagicMock.executemany.side_effect` with `duckdb.InvalidInputException` to test the empty parameter list fallback handling path. Add explicit parameter binding tests for both pyformat (`%(param)s`) and standard question marks (`?`).
## 2024-12-06 - Missing DB Queries Exception Coverage
**Learning:** Utilities in `src/db/queries.py` such as `_current_locale` and `_get_override_table_name` contain `try/except` and `if/else` fallback paths for missing session states or unavailable duckdb dependencies. These lines were missed in coverage because `test_table_friendly_names.py` tested the locale wrapper instead of the direct db helper, and duckdb override path tests were completely missing in `test_db_queries.py`.
**Action:** When adding or maintaining db utilities in `src/db/queries.py`, always ensure `test_db_queries.py` includes patched exception and toggle tests (e.g., patching `get_current_locale` to throw exceptions and patching `_duckdb_available` to return `False`) to fully test fallback mechanisms.

## 2023-10-31 - Coverage of error UI components requires dedicated mock tests
**Learning:** Testing UI exception paths in Streamlit apps (like triggering `st.error` on a failed database write) requires specific mocking of the write function to simulate the error. Without it, the exception handling branch in the UI is not covered, and regressions could silently hide internal error stacks from users.
**Action:** When adding or modifying UI components that perform state-altering operations (like saves), always add a companion test that uses `@patch` with `side_effect=Exception(...)` on the target logic function to verify the UI fails gracefully.
## 2026-10-03 - Streamlit query_params API Change
Coverage Gap: `st.query_params` returns a string or list of strings depending on the Streamlit version and how it's used. In newer versions, it acts more like a dictionary returning a string.
Learning: When testing Streamlit's `at.query_params`, use `in` operator (e.g. `assert at.query_params["tab"] in ("search", ["search"])` or `assert "search" in at.query_params["tab"]`) or just check for the string if we are setting it directly. We should be robust to both single string and list of strings.
Assertion: `assert "search" in at.query_params["tab"]` or `assert at.query_params["tab"] == "search"`
## 2023-10-24 - Handle Streamlit Empty Search State Exception Fallbacks

**Learning:** When writing tests for UI components that conditionally render based on edge cases (like empty `pandas` DataFrames, or `None` returned from mocked database queries), it's crucial to explicitly simulate both structural edges (e.g. empty frames with required columns) and true `None` return values. Also, when an external API might return a raw boolean or a missing structure instead of a proper object in the UI template, we can face trace errors (e.g., `AttributeError` when using `results.empty` instead of checking `results is None or results.empty`).

**Action:** Ensure that conditionally rendered empty states have test coverage by injecting completely empty DataFrame objects (`pd.DataFrame(columns=[...])`) as well as null objects (`None`) through dependency mocking. I created tests that trigger the empty state rendering and strictly validated the output via Streamlit's `AppTest` API.

## 2026-10-15 - Streamlit AppTest _html element type extraction
**Learning:** When extracting HTML from `st.html()` elements in Streamlit tests using `AppTest.main`, the component structure can vary. Previously, it might have been an `UnknownElement`, but as of recent Streamlit versions it is now represented as an `Html` element. Thus, relying solely on `type(el).__name__ == "UnknownElement"` to extract the HTML proto body fails and silently ignores HTML injections, leading to `AssertionError` in accessibility tests that verify markup (like language toggles, nav bars, etc).
**Action:** When extracting custom injected HTML from an `AppTest` wrapper in Streamlit tests, check for both `Html` and `UnknownElement` types, and safely use `getattr(el, "type", "")` instead of a direct attribute access to avoid `AttributeError` on elements without a type field.
## 2026-10-17 - tests/test_ui_search_missing_coverage.py
**Learning:** `AppTest` requires that the lineage mock actually returns multiple nodes (`len(graph_nodes) > 1`) for the expand lineage button to render. Also column overrides map directly from the column name (e.g., `id`) to `business_name` and `definition`, not from `full_name__column_name`.
**Action:** Wrote a test to mock these values and simulate button clicks to trigger the UI paths, hitting previously missed coverage lines.
## 2024-05-18 - [DuckDB Singleton Edge Case]
**Learning:** Testing methods of classes that handle DuckDB singletons requires explicitly mocking out the shared connection state at the module level before instantiation.
**Action:** When adding tests for `_ensure_user_data_attached` (lines 415-418), wrap the instantiation of `_DuckDBConn` in a mock for `_get_shared_duckdb_connection`.
