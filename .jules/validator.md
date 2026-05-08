## 2026-05-06 - [Coverage Gap] Missing test coverage for src/personalization.py
Coverage Gap: The user preferences and personalization logic (e.g., `_pref_upsert`, `_pref_load`) lacked test coverage, running the risk of unnoticed regressions in database interactions.
Learning: Functions heavily relying on global `st.session_state` and DuckDB singletons require careful isolation via mock patches for both the Streamlit state and the database cursor objects to avoid contaminating other test suites or failing due to missing DB files.
Assertion: Use `unittest.mock.patch` on the DuckDB availability checks and connection functions, explicitly mocking `fetchall_as_pandas` and `execute` on the connection objects. Always clear `st.session_state` before/after tests mutating it.
## 2026-05-06 - [Coverage Gap] Missing test coverage for `is_editing_enabled`, `set_editing_enabled`, and `is_power_user`
Coverage Gap: The user preferences and personalization logic (specifically the `is_editing_enabled`, `set_editing_enabled`, and `is_power_user` functions) lacked test coverage, posing a risk of unnoticed regressions related to user permissions and cache state.
Learning: Testing modules that heavily rely on Streamlit's `st.session_state` and external configurations (like `os.getenv` or DB calls) requires explicit state management to avoid cross-test contamination and state leakage.
Assertion: Use `unittest.mock.patch` to mock external storage classes and environment variables. Always explicitly call `st.session_state.clear()` before each test to guarantee an isolated test environment.
