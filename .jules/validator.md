## 2023-10-27 - Detail validator mock fix
Coverage Gap: `src.ui.cards.detail.render_table_metadata_editor` cancel logic was untested.
Learning: `AppTest` automatically patches streamlit components, so mocking UI interactions like clicks using `st.button` side effects fails when used with `AppTest`.
Assertion: Always use `AppTest` to test `st.dialog` rather than manual patching, and use `at.button[0].click().run()` to simulate clicks.
