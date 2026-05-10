## 2026-05-06 - [Coverage Gap] Missing test coverage for src/personalization.py
Coverage Gap: The user preferences and personalization logic (e.g., `_pref_upsert`, `_pref_load`) lacked test coverage, running the risk of unnoticed regressions in database interactions.
Learning: Functions heavily relying on global `st.session_state` and DuckDB singletons require careful isolation via mock patches for both the Streamlit state and the database cursor objects to avoid contaminating other test suites or failing due to missing DB files.
Assertion: Use `unittest.mock.patch` on the DuckDB availability checks and connection functions, explicitly mocking `fetchall_as_pandas` and `execute` on the connection objects. Always clear `st.session_state` before/after tests mutating it.
## 2026-05-06 - [Coverage Gap] Missing test coverage for `is_editing_enabled`, `set_editing_enabled`, and `is_power_user`
Coverage Gap: The user preferences and personalization logic (specifically the `is_editing_enabled`, `set_editing_enabled`, and `is_power_user` functions) lacked test coverage, posing a risk of unnoticed regressions related to user permissions and cache state.
Learning: Testing modules that heavily rely on Streamlit's `st.session_state` and external configurations (like `os.getenv` or DB calls) requires explicit state management to avoid cross-test contamination and state leakage.
Assertion: Use `unittest.mock.patch` to mock external storage classes and environment variables. Always explicitly call `st.session_state.clear()` before each test to guarantee an isolated test environment.
## 2026-05-09 - Pipeline Trigger Coverage Gap

Coverage Gap: `src.pipelines.py` trigger functions (`_trigger_databricks`, `_trigger_adf`, `_trigger_ado`) had 0% coverage and lacked testing for their HTTP requests.
Learning: Local dependency imports (e.g., `import requests` inside a function body) require patching the global module (e.g., `@patch('requests.post')`) rather than patching the module namespace (`@patch('src.pipelines.requests.post')`), otherwise it raises an AttributeError.
Assertion: Ensure tests correctly patch the globally resolved module rather than attempting to resolve it in the target namespace when it's imported locally.
## 2026-05-10 - [Coverage Gap] Missing tests for is_pipeline_user
Coverage Gap: `is_pipeline_user` lacked a robust defensive test for explicit `None` assignment to `user_groups` inside `st.session_state`.
Learning: When reading arrays/lists from `session_state`, explicitly check or default to `[]` when the value is explicitly `None` (e.g. `user_groups = st.session_state.get("user_groups") or []`) to prevent `TypeError: 'NoneType' object is not iterable` during set operations.
Assertion: Ensure tests correctly handle explicit `None` mocking using `monkeypatch.setattr('src.auth.st.session_state', {"user_groups": None})` to prevent test contamination.
