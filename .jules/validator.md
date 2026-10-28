<<<<<<< HEAD
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
## 2026-06-10 - Coverage Gap: Detail Card Editors
**Coverage Gap:** The business name editors (`render_business_name_editor` and `render_table_business_name_editor`) in `src/ui/cards/detail.py` lacked test coverage for saving overrides, catching exceptions, fetching existing overrides, and authorization errors.
**Learning:** For dialog functions triggered by UI components that depend on external db cursors, we must patch the connection getter correctly (e.g. `_get_write_connection` or `save_table_business_name`) instead of mocking `execute_write` on the raw DB layer directly, especially since `render_table_business_name_editor` abstracts DB queries behind `save_table_business_name`.
**Assertion:** Use Streamlit's `AppTest` to mock standard user flows on these components and `patch` the underlying storage helpers directly to cover valid workflows and exception branches (e.g., `ValueError`, `PermissionError`).
## 2026-06-10 - Streamlit AppTest segmented_control Bug with format_func
**Coverage Gap:** The test suite for `discovery.py` UI routing was tightly coupled to hardcoded English localized strings and would break when testing different locales or decoupling internal IDs from the frontend `format_func`.
**Learning:** In Streamlit `AppTest` (< v1.40), simulating user selection on `st.segmented_control` or `button_group` using `.set_value()` fails if a `format_func` is applied to the widget's options. `AppTest` attempts to map the state using formatted representations rather than internal IDs, which leads to `None` values and failed test routing assertions.
**Assertion:** To robustly test the underlying application routing and logic without being blocked by this `AppTest` framework bug, bypass the widget interaction by patching the component directly in the test suite (e.g., `@patch("src.ui.cards.discovery.st.segmented_control")` and setting `mock.return_value = "internal_option"`).
## 2026-06-18 - i18n Date and Pluralization Coverage
**Coverage Gap:** `src/i18n.py` format functions (`format_date`, `format_number`) and count-based pluralization logic lacked test coverage.
**Learning:** Testing locale-aware date formatting requires explicitly checking the dynamically resolved translation keys (`date.months...`) since `strftime` is bypassed, and pluralization needs tests covering edge cases (`_zero`, `_one`, `_other`) to ensure correct suffix resolution.
**Assertion:** Mock `st.session_state` locally within tests to override the active language and pass different `count` variables to the `t()` function to test pluralization resolution branches.
## 2026-06-18 - Cover MCP Auth Exception Handling
**Coverage Gap:** The `ValueError` and `RuntimeError` exception handlers in the MCP authentication middleware (`_MCPAuthMiddleware.__call__` in `src.api.main`) lacked test coverage, potentially allowing unhandled misconfiguration exceptions to leak.
**Learning:** Testing ASGI middleware exception paths requires patching the imported external async functions (like `validate_token`) directly within the middleware's module space and validating the raw HTTP response payloads and status codes that the middleware returns upon catching those exceptions.
**Assertion:** Use FastAPI's `TestClient` combined with `unittest.mock.patch` returning an `AsyncMock(side_effect=...)` to inject the target exceptions during the middleware execution, and assert on `resp.status_code` and `resp.json()`.
## 2026-06-20 - Coverage Gap: get_sync_queue_stats
**Coverage Gap:** `get_sync_queue_stats` in `src/ui/cards/admin.py` had no unit tests, leaving the `pending_sync` read operations untested.
**Learning:** When testing Streamlit UI components that abstract DB queries behind `_get_write_connection`, mock the connection getter (e.g., `@patch('src.ui.cards.admin._get_write_connection')`) instead of mocking `execute_write` directly on the raw cursor. Ensure the mocked cursor explicitly supports context managers.
**Assertion:** Use `@patch` to mock `_duckdb_available` and `_get_write_connection` and verify that the correct dictionary of sync queue statuses is returned for successful, disconnected, and fallback cases.
## 2026-06-23 - Coverage Gap: Preference Storage
**Coverage Gap:** `src/storage/preference_storage.py` had no unit tests, leaving persistent tracking of user preferences (bookmarks/recent) and site settings untested. Exception fallback paths on db operations were fully uncovered.
**Learning:** Testing DB operations that use `get_db_connection` and `_get_write_connection` requires explicitly mocking these local imports and simulating database exceptions to test the graceful degradation wrap with `try/except Exception`. Context managers inside DB execution paths (`with conn.cursor() as cur:`) require assigning `mock_cursor` to `.return_value.__enter__.return_value`.
**Assertion:** Created `tests/test_storage_preference.py` to instantiate instances of `DuckDBPreferenceStorage`, `FakePreferenceStorage`, `DemoPreferenceStorage`, and Site Settings variants, using `patch` on `get_db_connection` and `_get_write_connection` to cover successful flows and exception branches.
## 2026-06-25 - FastAPI Middleware Exception Paths Coverage Gap
**Coverage Gap:** `src.api.main` lacked coverage for its middleware exception paths (e.g. `_MCPAuthMiddleware` and `_SecurityHeadersMiddleware`), leaving potential regressions in security headers injection and MCP authentication unchecked.
**Learning:** Testing ASGI middlewares directly requires creating mock ASGI apps and explicitly calling the middleware with mock scopes to hit edge-case non-HTTP paths (like `scope["type"] != "http"` or missing authorization handlers) effectively. Moreover, `TestClient` initialization handles lifespan events, which means startup validations (like `_validate_auth_config`) can block client creation if the env is misconfigured during tests.
**Assertion:** When writing tests for FastAPI middleware, mock the lifespan validations to permit client instantiation (`with patch("src.api.main._validate_auth_config"):`), and use `@pytest.mark.anyio` combined with mock ASGI `send`/`receive` callables to test direct scope type branches without spinning up complex app routing logic.
## 2026-06-25 - Cover Preference Storage Exception Handlers
**Coverage Gap:** The `PreferenceStorage` module handles database operations that fail gracefully inside `try/except Exception` blocks, but these blocks lacked coverage.
**Learning:** Database interactions using DuckDB cursors via context managers often hide exceptions if the `__enter__` and `__exit__` methods are not explicitly mocked, causing test suite crashes.
**Assertion:** When writing tests for DuckDB context managers, explicitly patch the target module's DB provider (e.g. `get_db_connection`) and define `__enter__` and `__exit__` on the mocked cursor's return value to ensure exception paths are fully covered.
## 2026-06-26 - PreferenceStorage and SiteSettingStorage Coverage
**Coverage Gap:** `DemoPreferenceStorage`, `DuckDBPreferenceStorage`, `FakePreferenceStorage`, `DemoSiteSettingStorage`, `DuckDBSiteSettingStorage`, and `FakeSiteSettingStorage` in `src/storage/preference_storage.py` had no unit tests, leaving persistent tracking of bookmarks, recent views, and site settings untested.
**Learning:** The application mocks dependencies deeply at the module level in tests (e.g., using a duckdb tmpfile). Exceptions from DB disconnections needed to be validated using pytest's mock framework. Like `NotificationStorage`, testing these duckdb methods requires mock configurations of `get_db_connection` and `_get_write_connection` from `src.storage.preference_storage`.
**Assertion:** Created `test_storage_preferences.py` to instantiate local instances of the various PreferenceStorage and SiteSettingStorage classes, testing CRUD operations and simulating database disconnections using patched dependencies.
## 2024-06-27 - Coverage Gap: Catalog Browser Streamlit Component
**Coverage Gap:** `render_catalog_browser` in `src/pages/catalog.py` had zero direct test coverage, leaving error handling, truncation, and button click routing unverified.
**Learning:** Testing isolated Streamlit UI components using `AppTest.from_function` requires a specific import strategy when the component fetches data or relies on local imports. Because `AppTest.from_function` executes the target in an isolated script runner context that does not inherit the global namespace, you must wrap the target function and perform all necessary module imports *inside* the wrapper's local scope. Otherwise, the isolated runner fails with `NameError`.
**Assertion:** Create a local wrapper function in the test file that imports `streamlit` and the target function (e.g. `render_catalog_browser`), then passes this wrapper to `AppTest.from_function`. Use `@patch` on the component's module (e.g. `src.pages.catalog.get_authorized_tables`) to mock database queries before running assertions on `at.expander`, `at.button`, and click events.
## 2026-06-28 - PipelineStorage Coverage
**Coverage Gap:** `src/storage/pipeline_storage.py` had no test coverage for persistent Pipeline configuration (DuckDBPipelineDefStorage and DuckDBPipelineRunStorage).
**Learning:** Testing DB exception fallbacks for objects created via `with conn.cursor() as cur:` requires explicit mocking of `conn.cursor.side_effect = Exception(...)` instead of mocking `_get_db_connection` directly if the underlying DuckDB cursor initialization fails.
**Assertion:** Wrote `test_storage_pipelines.py` with `@patch` replacing imported `get_db_connection` in the `src.storage.pipeline_storage` module namespace, validating data persistence logic and error fallback handlers.
## 2026-06-30 - Cover PipelineStorage Coverage Gap
**Coverage Gap:** The `PipelineDefStorage` and `PipelineRunStorage` components in `src/storage/pipeline_storage.py` were missing unit tests.
**Learning:** Testing these classes requires mocking DuckDB connection exceptions, as well as thoroughly exercising demo/fake mock classes for isolated testing.
**Assertion:** Add `test_storage_pipeline.py` to cover all execution branches including error catching for duckdb operations.
## 2026-06-30 - Cover PreferenceStorage Coverage Gap
**Coverage Gap:** The `PreferenceStorage` and `SiteSettingStorage` components in `src/storage/preference_storage.py` were missing unit tests.
**Learning:** Mocking DB connection returns combined with testing dummy objects (like fake dicts) is an effective testing strategy for storage backends without actual DB dependencies.
**Assertion:** Add `test_storage_preference.py` to cover all execution branches including error catching for duckdb operations.
## 2024-07-03 - [CRITICAL] DuckDB Cursor Initialization with Context Managers
**Learning:** When testing exception fallbacks for DuckDB database operations that are executed within context managers (like `with conn.cursor() as cur:`), simply patching the connection provider with a `side_effect=Exception(...)` is sometimes insufficient or bypassed if the code actually encounters the exception during the `cursor()` initialization or the `__enter__` phase of the context manager rather than connection acquisition. The test suite revealed issues in `tests/test_storage_preference.py` where patching the DB connection didn't properly handle the exception test case, as the exception was raised during an earlier step or the mock setup itself failed before triggering the target logic. Furthermore, when writing tests using `unittest.mock.patch` as a context manager (`with patch(...)`), you must explicitly instantiate the class being tested (e.g. `DuckDBSiteSettingStorage`) inside the `with patch(...)` block. Otherwise, it might use a non-mocked connection during its `__init__` phase or raise `NameError` if initialized outside the local block context. Finally, standard library modules like `secrets` must be explicitly imported in the target file (e.g., `src/sync/daemon_db.py`) to prevent runtime `NameError`s when tests exercise paths utilizing them.
**Assertion:** To reliably test exception handling for DuckDB context managers, mock the connection provider and configure the exception on the cursor initialization (`mock_conn.cursor.side_effect = Exception(...)`) and always ensure test object instantiation is enclosed within the `patch` context block. Explicitly import all used standard libraries in production code.
## 2026-07-18 - [Fixing flaky AppTest st.segmented_control tests]
**Coverage Gap:** Tests asserting presence of components inside conditional `st.segmented_control` blocks were failing (e.g., test_admin_sections_present).
**Learning:** Updating `at.session_state` to change tabs does not correctly trigger Streamlit's internal rerender mapping for `st.segmented_control` in AppTest, causing false negative failures.
**Assertion:** Bypass the widget behavior by explicitly mocking the output. Prefer Pytest's built-in `monkeypatch` fixture: `monkeypatch.setattr('module.st.segmented_control', lambda *args, **kwargs: "TabName")` to avoid missing imports.
## 2024-07-04 - Cover FastAPI Health Readiness Path Gap
**Coverage Gap:** The `/health/ready` endpoint in `src/api/routers/health.py` was missing test coverage, resulting in 88% coverage on the file.
**Learning:** Testing simple API endpoint routing doesn't require mocking when no external dependencies exist, but simple paths like `readiness` are often overlooked when `liveness` tests already exist.
**Assertion:** Use FastAPI's `TestClient` to make a GET request to `/health/ready` and assert on `resp.status_code == 200` and `resp.json() == {"status": "ok"}`.
## 2024-07-22 - Missing Test Coverage for Query Overrides Resolution
**Coverage Gap:** `src/api/queries._overrides_tables()` lacked tests to cover branches validating metadata table fallback resolutions when `_duckdb_available()` returned true or false.
**Learning:** Adding test coverage involving multiple conditional branches where `patch` context managers handle different states is effective at rapidly pushing unverified conditional paths to 100% coverage.
**Assertion:** I used `unittest.mock.patch` for `_duckdb_available` to test both true and false paths, validating output variables cleanly in `TestOverridesTables`. Ensure imports for new tests are placed at the top of the file to prevent Ruff `E402` linting errors.
## 2024-07-27 - DuckDB Background Thread Testing
Coverage Gap: The offloaded `track_search` logging mechanism running in a background thread was completely untested, masking potential silent catalog or write errors.
Learning: Streamlit's `add_script_run_ctx` and raw `threading.Thread` usage make it hard to test asynchronous I/O natively without polling or race conditions. Also, mocking file databases like DuckDB requires ensuring schemas are explicitly initialized in the temp environment.
Assertion: Mock `threading.Thread` and extract the target function via `mock_thread.call_args[1]["target"]` to run the threaded logic synchronously inside the main test frame. This guarantees predictable database state checks.
## 2024-08-18 - Missing coverage in get_authorized_table_names

**Coverage Gap:** The `get_authorized_table_names` function in `src/db/queries.py` completely lacks test coverage.
**Learning:** This function is a cached helper that fetches the full authorized tables dataframe and extracts a set of table names, and must handle empty cases correctly.
**Assertion:** We must mock `get_authorized_tables` to return both populated and empty DataFrames, and assert the function returns the correct `set` of `full_name` strings in both scenarios.

## 2026-08-19 - Mocking Streamlit Selectboxes in AppTest
**Coverage Gap:** The search group filtering and analytics exception paths in `src/pages/search.py` were untested because they depended on Streamlit `selectbox` widgets populated by dynamic dataframes.
**Learning:** When testing Streamlit `AppTest` selectboxes with dynamic options populated by a pandas dataframe query (like `get_authorized_tables`), you must ensure the mock DataFrame provides a value that exactly matches what `at.selectbox.set_value()` attempts to set. If the value isn't in the mock's `table_name` column, `AppTest` raises a `ValueError` because the UI widget cannot select an invalid option. Furthermore, to test the "unauthorized table" edge case, you must set the selectbox to a valid authorized table name, but mock the subsequent search query (`search_all_metadata`) to return the unauthorized table.
**Assertion:** Ensure `mock_authorized` DataFrames contain the exact strings you intend to pass to `at.selectbox(...).set_value(...)`, and decouple the `selectbox` valid options from the secondary search results by mocking `search_all_metadata` independently.
## 2024-08-20 - Mocking Lazy Modules in Search Queries
**Coverage Gap:** The `search_all_metadata` and `_search_keywords` functions in `src/db/queries.py` lacked test coverage, specifically for hybrid semantic search logic and column-specific scoring rules.
**Learning:** Mocking lazy imports (like `src.semantic.semantic_search` which is imported conditionally inside the function) requires mocking the imported function explicitly at its source module path (`src.semantic.semantic_search`) rather than in the local module (`src.db.queries`). Additionally, simulating an `ImportError` on a lazy import requires patching `sys.modules` with `None` for the target module.
**Assertion:** Use `patch("src.semantic.semantic_search", ...)` for mocking the conditionally imported function and `patch.dict(sys.modules, {"src.semantic": None})` to test exception handling for missing dependencies in lazy imports.
## 2026-08-27 - [app.py coverage improvements]
**Coverage Gap:** Missing coverage in app.py for mock login URL query parameters, transient state clearance on tab switch, and some routing logic.
**Learning:** `app.py` is the entrypoint to a Streamlit app. For Mock Auth URL querying, we needed to pass the query parameters using `at.query_params["mock_login"] = "true"` and `at.query_params["mock_dept"] = "finance"`. The tab switching clears session states, testing this involves setting transient state in `at.session_state` before a tab change.
**Assertion:** We can test tab switches and URL mocking logic effectively by directly setting properties in `at.query_params` and `at.session_state` prior to `at.run()`.

## 2024-08-24 - Mocking DuckDB Context Managers
Coverage Gap: Missing test coverage for `_notify_bookmarkers` in `src/sync/push.py` resulting in unverified db write paths.
Learning: Mocking DuckDB connection objects for test cases requires explicit mocking of the `__enter__` return value for `conn.cursor()` since it is heavily used as a context manager (`with conn.cursor() as cur:`).
Assertion: Use `cur_mock = MagicMock(); conn.cursor.return_value.__enter__.return_value = cur_mock` to properly intercept and assert against `cur.execute_write`.

## 2024-05-18 - [Add unit tests for get_column_overrides]
**Coverage Gap:** The `get_column_overrides` function in `src.audit` lacked test coverage for both its demo mode and production database paths, leaving potential filtering or SQL fetch regressions uncaught.
**Learning:** Found that mocking nested Streamlit session state operations (e.g. `st.session_state.get().get().items()`) requires explicitly wiring up the mocked `get` returns or setting a side_effect function to handle the chained dictionary lookups correctly when simulating demo mode data structures.
**Assertion:** Wrote isolated unit tests covering `is_demo_mode=True`, production DB fetching via mocked `fetchall_as_pandas`, and DB exception handling, asserting the resulting dictionaries are constructed as expected.

## 2024-05-24 - Search Downstream Critical Lineage Edge Case
**Coverage Gap:** The branch that tests `_has_critical` mapping to rendering a downstream warning in search detail view was previously uncovered.
**Learning:** For testing `st.session_state` flows like `dd_nav_select` triggering the detail view correctly, ensuring dependent API mocks (`get_multi_hop_lineage`, `get_authorized_tables`, `search_all_metadata`) contain the exact schema (e.g. `direction`, `entity_type`) is strictly required.
**Assertion:** Use `AppTest` to verify that `st.markdown` properly interpolates translation keys like `detail.downstream_certified_warning` by asserting against `md.value`.

## 2024-09-01 - Mocking Streamlit layout elements
**Coverage Gap:** Testing complex UI rendering logic involving `st.columns()` nested layout.
**Learning:** When using Streamlit column layouts, assertions directly on the column mock (e.g. `mock_cols[0].markdown.assert_called()`) can be brittle or behave unexpectedly due to how Streamlit binds these to the global state.
**Assertion:** It is more reliable to assert on the length of `mock_calls` array for the target mock object (e.g., `assert len(mock_cols[0].mock_calls) > 0`) when validating the rendered elements inside the `with c1:` block.
## 2024-05-24 - Handle empty full_name correctly when rendering search results
**Coverage Gap:** Lines 697 and 753 in src/pages/search.py were not covered. If the database somehow returns a `null` full_name, it gets converted to `"None"` or `"nan"` when we cast it via `str(getattr(row, "full_name", ""))`. Our if condition checking `if not _fn` didn't catch these cases, allowing invalid string representations to proceed in the UI logic.
**Learning:** In Streamlit `AppTest`, passing `np.nan` or `None` in the mock DataFrame requires explicit handling during str conversions in our UI code. `str(None)` is `"None"` and `str(np.nan)` is `"nan"`, so `if not _fn:` evaluation doesn't work correctly. We must also check for `"None"` and `"nan"` strings, or use pandas `isna()`.
**Assertion:** Added unit tests simulating empty, `None`, and `np.nan` for `full_name` in search results and group filters. We check that `len(gview_btns) == 0` for group filter search and `len(view_btns) == 0` for the direct search query to assert the continue blocks executed correctly.
## 2024-05-14 - Fix NaN missing value handling leading to ValueError
**Coverage Gap:** Data quality score missingness caused a `ValueError: cannot convert float NaN to integer` during render when `dq_score=NaN` was cast to float then int.
**Learning:** Missing values (`np.nan` or `None`) when cast to a string via `str()` evaluate to the literal strings `"nan"` and `"None"`. Standard falsy checks (`val or 0`) will not catch these representations, breaking downstream logic.
**Assertion:** Explicitly use `pd.isna()` or string comparisons (`val == "nan"`) to correctly handle missing data, especially from pandas Series. Added a direct test of the render panel with a `np.nan` score.

## 2026-09-12 - [Mocking Streamlit Query Params in AppTest]
**Coverage Gap:** The non-admin path in `render_cms_banner` was uncovered, particularly testing navigation clicks where `st.query_params` updates.
**Learning:** Checking query parameters after clicking a navigation button in an AppTest can result in either a string or list of strings being returned depending on Streamlit versions/mocks. Also, `st.markdown` needs to be validated properly by asserting against generated raw HTML blocks using `any()`.
**Assertion:** Always check for substring inclusion (e.g., `"search" in at.query_params["tab"]`) instead of exact list equality when testing Streamlit query param updates in `AppTest`, and verify raw output with `[m.value for m in at.markdown]`.

## 2023-10-25 - [Title] Discovery UI Unreachable Dead Code
Coverage Gap: The else branch inside `_render_notable_tab` prompting for user sign in was unreachable since an earlier statement would return early if `primary_group` was falsey.
Learning: When addressing test coverage gaps involving missing lines, if analysis reveals the un-covered lines are logically unreachable dead code (e.g., statements following a branch with a guaranteed early-return), remove the dead code to satisfy the coverage metric instead of attempting to mock impossible test states.
Assertion: Tested normal empty states and removed the unreachable dead code block.
## 2024-05-18 - Missing coverage in get_authorized_table_names and get_authorized_tables
Coverage Gap: The `get_authorized_table_names` and `get_authorized_tables` functions in `src/db/queries.py` lacked complete coverage, particularly for empty state handling and the demo mode branch logic, leading to missing assertions for authorization edge cases.
Learning: Unmocked external cached responses in DB query tests can cause assertions to randomly fail if the shared cached singleton has expired or holds unexpected data. Furthermore, complex functions querying external data warehouses are notoriously flaky.
Assertion: Ensure mocking targets explicitly return isolated, clean mock Pandas DataFrames to properly assert functionality strictly inside the target functions without touching backend databases or caches.
## 2024-09-24 - Cover DuckDB Dictionary Parameter Conversion
Coverage Gap: The parameter conversion logic for pyformat dictionaries in DuckDB's `executemany` method lacked testing, posing a risk to batch insert operations.
Learning: Testing database adapter logic requires simulating the exact payload shapes (list of dictionaries with pyformat SQL strings) that the adapter is designed to intercept and transform into native dialect parameters.
Assertion: Always supply the exact, expected upstream payload structure (e.g., `[{"col1": val1}, ...]`) alongside pyformat SQL (e.g., `%(col1)s`) to reliably test custom adapter parameter transformations.

## 2026-09-25 - Mocking duckdb.InvalidInputException and testing executemany parameter conversion
Coverage Gap: `_DuckDBCursor.executemany` in `src/db/duckdb_adapter.py` had zero coverage for its dictionary parameter conversion and `duckdb.InvalidInputException` handling.
Learning: Testing `executemany` edge cases requires directly instantiating the internal `_DuckDBCursor` class with a mocked connection, rather than using the public `DuckDBAdapter` class which hides these implementation details. To test the `duckdb.InvalidInputException` triggered by passing an empty parameter list to `executemany`, the mock must be explicitly configured with `con_mock.executemany.side_effect = duckdb.InvalidInputException("executemany requires a non-empty list of parameter sets to be provided")` because MagicMock doesn't emulate external C library validations automatically.
Assertion: Use `cursor = _DuckDBCursor(MagicMock())` to isolate and test cursor logic, and manually set `side_effect=duckdb.InvalidInputException(...)` on the connection mock to verify exception handling for empty parameter arrays.

## 2026-09-26 - Mocking conditionally available DuckDB cursor methods
Coverage Gap: The fallback loop inside `_merge_into_local` when `executemany_write` is unavailable on the cursor lacked test coverage (lines 100-101).
Learning: By default, `MagicMock` returns true for `hasattr(mock, 'any_attribute')` because it dynamically creates attributes on access. To test branches that check `if hasattr(mock, 'some_method'):`, we must explicitly delete the attribute from the mock using `del mock_cur.some_method` before it is accessed.
Assertion: Use `del mock_cur.executemany_write` to simulate older DuckDB adapters that lack the `executemany_write` method and verify the fallback iteration executes `execute_write` multiple times.

## 2026-09-29 - [Cover ValueError and Exception handling in search UI]
Coverage Gap: Missing test coverage for ValueError and generic Exception fallbacks when calling save_business_name in src.pages.search.
Learning: To test try/except fallback logic properly, we must use unittest.mock.patch to target the specific function that raises the exception (e.g. src.pages.search.save_business_name) directly with a side_effect of the exception. Failure to mock the exact source function leaves the except blocks untested.
Assertion: Use @patch("src.pages.search.save_business_name", side_effect=Exception("Error")) and assert that at.error is populated after the button click event.
## 2026-10-03 - [Cover ValueError and Exception handling in detail UI]
Coverage Gap: Missing test coverage for ValueError, PermissionError and generic Exception fallbacks when calling save_table_business_name in src.ui.cards.detail, as well as render_data_sample authorization checks.
Learning: To test try/except fallback logic properly in Streamlit components, we must use unittest.mock.patch to target the specific function that raises the exception (e.g. src.ui.cards.detail.save_table_business_name) directly with a side_effect of the exception. Failure to mock the exact source function leaves the except blocks untested.
Assertion: Use @patch("src.ui.cards.detail.save_table_business_name", side_effect=ValueError("Invalid Input")) and assert that at.error is populated after the button click event.

## 2026-10-02 - UI Search Pagination Edge Cases
Coverage Gap: The warning messages indicating that only the first 50 columns or grants are shown in the data catalog detail panel were completely untested.
Learning: Testing Streamlit applications requires accurately simulating complex session states (like `_dd_sticky_nav`) directly before evaluating the specific UI components (like `st.info`) that are rendered.
Assertion: When adding logic that conditionally limits or modifies the rendering loop of elements based on length, explicitly supply a mock array that exceeds that limit and verify the presence of the corresponding UI banner or message using `at.info` or similar selectors.
## 2026-10-02 - Cover Search Pagination Message Edge Cases
Coverage Gap: The explicit warnings that detail tables will truncate lists greater than 50 (like `showing_first_50_columns` and `showing_first_50_grants`) in `src/pages/search.py` lacked test coverage, leaving the >50 bounds logic untested.
Learning: Testing Streamlit message outputs in truncated or conditionally visible views requires explicitly supplying mock datasets that breach the exact array length boundaries so that UI warning components like `st.info` are rendered and queryable inside AppTest. Also, always make sure to encapsulate standard framework imports (like pandas) correctly inside the test method when writing AppTest mocks to avoid global scope contamination that breaks adjacent tests.
Assertion: When testing >50 truncation paths, verify `at.info` presence containing the specific truncation message substrings alongside a mock array initialization of size 55.
## 2026-10-07 - [Cover ValueError and Exception handling in save_business_name]
**Coverage Gap:** The `try...except ValueError` and generic `except Exception` blocks in `src.pages.search._render_detail_panel` during the column business name save operation were completely uncovered.
**Learning:** Testing exception fallbacks in Streamlit `AppTest` for logic triggered by a button click (which typically issues a `st.rerun()`) requires patching `streamlit.rerun` if the exception blocks do not call rerun themselves, or simulating edit modes carefully to ensure the form components render before interaction. Directly setting `at.session_state` to match the expected form context and verifying the widget existence before clicking ensures the `AppTest` environment correctly dispatches the mock side effects without raising generic missing key errors.
**Assertion:** Use `@patch("src.pages.search.save_business_name", side_effect=ValueError("Validation Failed"))` directly on the function being targeted during the button click, and verify the `st.error` fallback is rendered (`assert any("common.error" in e.value for e in at.error)`).

## 2025-02-09 - Discovery UI Empty DataFrame Edge Cases
**Coverage Gap:** Data-driven UI components that depend on pandas DataFrames were missing coverage for structural edge cases, specifically when mocked dependencies return an empty DataFrame (e.g., `pd.DataFrame(columns=["full_name"])`) while valid authorization names are still present.
**Learning:** Testing logic paths like empty DataFrames in discovery tabs requires precise test setup, returning not just primitive data types but properly structured empty DataFrames to exercise `df.empty` branches securely without triggering `KeyError`.
**Assertion:** We explicitly mock the internal `get_authorized_tables` call to return an empty DataFrame (e.g., `pd.DataFrame(columns=["full_name"])`) when there are seemingly valid bookmark/recent view names in session state, verifying the UI appropriately falls back to an empty state prompt without throwing exceptions.
## 2026-10-12 - [Discovery UI Unreachable Dead Code]
**Coverage Gap:** The else branch inside `_render_notable_tab` prompting for user sign in was unreachable since an earlier statement would return early if `primary_group` was falsey.
**Learning:** When addressing test coverage gaps involving missing lines, if analysis reveals the un-covered lines are logically unreachable dead code (e.g., statements following a branch with a guaranteed early-return), remove the dead code to satisfy the coverage metric instead of attempting to mock impossible test states.
**Assertion:** Removed the unreachable dead code block.
## 2026-10-24 - Discovery Recommended UI Empty DataFrame Edge Cases
**Coverage Gap:** Data-driven UI components in the discovery recommended tab were missing coverage for structural edge cases, specifically when mocked dependencies return an empty DataFrame (e.g., `pd.DataFrame(columns=["full_name"])`) while valid authorization names are still present.
**Learning:** Testing logic paths like empty DataFrames in discovery tabs requires precise test setup, returning not just primitive data types but properly structured empty DataFrames to exercise `df.empty` branches securely without triggering `KeyError`.
**Assertion:** We explicitly mock the internal `get_authorized_tables` call to return an empty DataFrame (e.g., `pd.DataFrame(columns=["full_name"])`) when there are seemingly valid bookmark/recent view names in session state, verifying the UI appropriately falls back to an empty state prompt without throwing exceptions.
## 2023-10-28 - Test coverage missing for error state handling in UI component
**Coverage Gap:** Line 722 in `src/pages/search.py` (clicking an unauthorized table) and early exit / error states in `src/db/duckdb_adapter.py`.
**Learning:** When using Streamlit `AppTest` to locate dynamically generated elements, we should use a fallback locator logic, as older Streamlit versions can make it challenging to find specific elements inside layout columns via key alone.
**Assertion:** Use a combination of exact key matches and fuzzy logic fallbacks when asserting against UI components rendered conditionally within layout loops.
