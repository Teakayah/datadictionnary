## 2024-05-27 - [Fix test_get_embedding_engine_databricks]
**Coverage Gap:** `test_get_embedding_engine_databricks` failed due to incorrect mocking of environment variable derived config constant.
**Learning:** When a configuration constant is derived from an environment variable and imported directly at the module level (e.g., `from src.config import DATABRICKS_EMBEDDING_ENDPOINT`), tests using `@patch.dict(os.environ, ...)` fail because the constant is resolved at import time.
**Action:** Patch the variable directly in the module namespace where it is used (e.g., `@patch('src.semantic.DATABRICKS_EMBEDDING_ENDPOINT', 'my-endpoint')`) to reliably override the value during tests.
## 2026-06-01 - [Fix Streamlit Segmented Control and Dialog Testing]
**Coverage Gap:** Tests failed or didn't execute properly for Streamlit `segmented_control` tab switching and `@st.dialog` popups.
**Learning:**
1. In `AppTest`, Streamlit segmented control selections might require directly setting both the bound session state variable AND internal variables like `_admin_tab_idx` to guarantee the proper block of conditional code runs during `at.run()`. Checking properties like `at.metric` might be empty or unreliable if the conditional logic didn't perfectly re-render in the test harness without those internal keys.
2. For testing `@st.dialog` functionality originating from button clicks in parent components, you must `patch` the dialog function itself in the parent test module (e.g. `@patch("src.ui.cards.pipelines._show_delete_pipeline_dialog")`) to verify the interaction, rather than patching internal implementations like `delete_pipeline_def` that the dialog *would* call.
3. With DuckDB adapters that return a context manager `__enter__` yielding itself, mocking requires correctly implementing `__enter__`, `__exit__`, and nested classes for cursor operations.
**Assertion:** Use `at.session_state["<key>"] = <val>` coupled with `at.run()` to trigger conditional tab rendering. Patch dialog rendering functions at the call site for parent verification.
