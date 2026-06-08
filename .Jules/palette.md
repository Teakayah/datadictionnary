## 2024-05-24 - Add loading spinners for async actions
**Learning:** Some synchronous or database-heavy actions like submitting a comment or saving a business definition lack visual feedback, making the app feel frozen.
**Action:** Always wrap the execution block immediately following `if st.button(...):` inside a `with st.spinner('...'):` context manager for data mutations.
