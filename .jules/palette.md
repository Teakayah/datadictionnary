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
## 2024-10-24 - Standardizing Empty States with Shared Component
**Learning:** Using raw HTML blocks with manual CSS styles (like dashed borders and custom paddings) for empty states in different tabs leads to inconsistent visuals and hard-to-maintain code when design tokens update. The application actually has a shared `_render_empty_state` UI utility that properly abstracts these structural tokens.
**Action:** Always verify if a shared structural component exists before rendering generic HTML containers for common patterns like empty states, error fallbacks, or generic lists.
