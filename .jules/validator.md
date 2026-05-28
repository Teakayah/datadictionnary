## 2024-05-27 - [Fix test_get_embedding_engine_databricks]
**Coverage Gap:** `test_get_embedding_engine_databricks` failed due to incorrect mocking of environment variable derived config constant.
**Learning:** When a configuration constant is derived from an environment variable and imported directly at the module level (e.g., `from src.config import DATABRICKS_EMBEDDING_ENDPOINT`), tests using `@patch.dict(os.environ, ...)` fail because the constant is resolved at import time.
**Action:** Patch the variable directly in the module namespace where it is used (e.g., `@patch('src.semantic.DATABRICKS_EMBEDDING_ENDPOINT', 'my-endpoint')`) to reliably override the value during tests.

## 2024-05-28 - [Fix Streamlit Dialog Testing in AppTest]
**Coverage Gap:** `test_render_with_pipelines_and_delete` in `tests/test_ui_pipelines.py` failed because Streamlit `AppTest` cannot natively trigger or verify events (like button clicks) inside an `@st.dialog` component if they lack explicit `key` parameters, nor can they be simply clicked without iterating.
**Learning:** Testing Streamlit `@st.dialog` components using `AppTest` requires assigning explicit keys to interactive widgets within the dialog. Furthermore, clicking these buttons might require finding them within the main `AppTest.button` list via iteration, as standard index access or direct `at.button(key="...")` can sometimes raise `KeyError` within nested fragment evaluations.
**Assertion:** Add specific keys (e.g., `key="pl_confirm_del_1"`) to dialog buttons and click them iteratively within tests using `for b in at.button: if b.key == "pl_confirm_del_1": b.click().run(); break` to ensure mock validation passes reliably.
