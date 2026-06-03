## 2026-05-30 - Testing Streamlit @st.dialog
**Learning:** When testing a parent component that triggers an `@st.dialog` component in Streamlit, AppTest does not natively expose the nested dialog state.
**Action:** Mock the dialog function itself in parent tests to verify it was called, and test the inner dialog logic in a separate isolated AppTest using a dedicated wrapper function.
