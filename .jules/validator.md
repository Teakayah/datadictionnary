## 2023-10-27 - Detail validator mock fix
Coverage Gap: `src.ui.cards.detail.render_table_metadata_editor` cancel logic was untested.
Learning: `AppTest` automatically patches streamlit components, so mocking UI interactions like clicks using `st.button` side effects fails when used with `AppTest`.
Assertion: Always use `AppTest` to test `st.dialog` rather than manual patching, and use `at.button[0].click().run()` to simulate clicks.

## 2024-05-22 - Detail Modal Coverage Gap
**Coverage Gap:** The table detail components (`render_table_metadata_editor` and `render_data_sample`) in `src/ui/cards/detail.py` were missing test coverage for their cancel button interaction and the fallback path for invalid namespaces under DuckDB execution.
**Learning:** Testing secondary modal actions like cancel requires explicitly simulating index-based button clicks in `AppTest` (e.g. `at.button[1]`). The data sample method also contained an unreachable fallback branch because the preceding regex validation strictly ensured valid name formatting. Mocking the regex result allowed verifying the fallback branch behavior.
**Assertion:** Use index-based widget lookup to assert on secondary buttons when not explicitly labeled with unique keys, and apply targeted mocking to `re.match` to test defensive fallbacks hidden behind early validation.
