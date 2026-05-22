## 2025-03-08 - Added set_locale test overwrite
Coverage Gap: The existing tests verify `set_locale` logic directly but don't explicitly test the overwriting of an existing locale setting.
Learning: Modifying state variables requires explicit verification of initial state vs the updated state.
Assertion: Added test verifying `set_locale("fr")` overrides `{"locale": "en"}` correctly in `st.session_state`.
