## 2026-06-14 - Fix Streamlit AppTest variable missing in global scope
**Coverage Gap:** Test suite for `tests/test_admin.py` and `tests/test_lineage.py` was failing during collection due to missing `lang` state in `src/i18n.py`.
**Learning:** In Streamlit `AppTest`, simulating variables derived from state (like `st.session_state`) might be missing in test environments if tests bypass standard initialization functions. To prevent `NameError` or `KeyError` crashes, explicitly extract required state locally within functions using safe accessors with fallbacks (e.g., `lang = st.session_state.get("locale", "en")`) rather than relying on implicit global scope.
**Assertion:** Mock test context setup or resolve variables defensively with default values using `st.session_state.get()`.

## 2026-06-14 - Fix Test Execution Failure due to Git Conflict Markers and Scope Isolation
**Coverage Gap:** Test suite was completely failing due to a SyntaxError in `tests/test_ui_discovery.py` caused by raw Git conflict markers (`<<<<<<< HEAD`). Also tests failed to resolve `patch` due to `AppTest.from_function()` isolating execution context.
**Learning:** `AppTest.from_function()` executes the tested function within an isolated Streamlit ScriptRunner context, preventing it from inheriting the global module namespace of the test file. Therefore, all necessary imports (including `patch`) must be explicitly defined inside the function.
**Assertion:** Cleaned up Git conflict markers manually. Moved the import for `unittest.mock.patch` inside the `render_discovery_page_app` function so it can be evaluated during test execution safely.
