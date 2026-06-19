## 2024-05-24 - Visual loading feedback for form saves
**Learning:** Some interactive Streamlit elements lack loading feedback for asynchronous/synchronous submissions.
**Action:** Always wrap `if st.button(...):` submission logic inside a `with st.spinner('...'):` context manager for visual feedback.

## 2026-06-19 - Admin action spinners
**Learning:** Admin approval and rejection actions lacked visual feedback during processing.
**Action:** Wrapped admin approval and rejection actions with `st.spinner` to provide visual loading feedback.
