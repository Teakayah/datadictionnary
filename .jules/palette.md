## 2024-05-24 - Visual loading feedback for form saves
**Learning:** Some interactive Streamlit elements lack loading feedback for asynchronous/synchronous submissions.
**Action:** Always wrap `if st.button(...):` submission logic inside a `with st.spinner('...'):` context manager for visual feedback.

## 2026-06-19 - Admin action spinners
**Learning:** Admin approval and rejection actions lacked visual feedback during processing.
**Action:** Wrapped admin approval and rejection actions with `st.spinner` to provide visual loading feedback.

## 2024-05-27 - Streamlit state toggle feedback
**Learning:** Bookmarking tables and columns lacked visual feedback, making the interaction feel unresponsive until the page reloaded.
**Action:** Use `st.toast()` immediately before `st.rerun()` when users perform instant state-toggles like adding or removing bookmarks to provide immediate, non-blocking visual feedback.
## 2026-07-04 - Notification dismiss missing feedback
**Learning:** Users lack immediate visual feedback when dismissing notifications, making the UI feel unresponsive until the page reloads.
**Action:** Use `st.spinner()` or `st.toast()` before `st.rerun()` for instant actions like dismissing notifications.
## 2024-07-23 - Visual feedback for notification dismissal
**Learning:** Users lack immediate visual feedback when dismissing individual notifications or marking all as read, making the UI feel unresponsive until the page reloads.
**Action:** Use `st.toast()` immediately before `st.rerun()` when users perform state toggles like dismissing notifications to provide immediate, non-blocking visual feedback.
## 2024-07-26 - Empty state polish
**Learning:** Generic Streamlit alert blocks like `st.info` do not provide a cohesive, branded empty state experience.
**Action:** Replace `st.info` with custom styled `st.markdown` containers using design tokens for empty state screens. Ensure any corresponding `AppTest` test assertions are updated to check `at.markdown` instead of `at.info`.
## 2024-05-28 - Visual feedback during search
**Learning:** The catalog search selectbox initiates heavy backend queries upon selection but provides no immediate visual feedback, leaving users unsure if their input was registered.
**Action:** Wrap synchronous search execution in `st.spinner(t("common.loading"))` to provide immediate visual loading feedback.
