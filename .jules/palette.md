## 2024-05-24 - Visual loading feedback for form saves
**Learning:** Some interactive Streamlit elements lack loading feedback for asynchronous/synchronous submissions.
**Action:** Always wrap `if st.button(...):` submission logic inside a `with st.spinner('...'):` context manager for visual feedback.

## 2026-06-19 - Admin action spinners
**Learning:** Admin approval and rejection actions lacked visual feedback during processing.
**Action:** Wrapped admin approval and rejection actions with `st.spinner` to provide visual loading feedback.

## 2024-05-27 - Streamlit state toggle feedback
**Learning:** Bookmarking tables and columns lacked visual feedback, making the interaction feel unresponsive until the page reloaded.
**Action:** Use `st.toast()` immediately before `st.rerun()` when users perform instant state-toggles like adding or removing bookmarks to provide immediate, non-blocking visual feedback.

## 2026-10-25 - Toast feedback for saves and deletions
**Learning:** Users lack immediate visual confirmation when form saves (e.g. comments, column business names) or object deletions (CMS posts, pipelines) complete successfully before the page rerenders.
**Action:** Add `st.toast()` calls immediately preceding `st.rerun()` for all successful create, update, and delete actions.
