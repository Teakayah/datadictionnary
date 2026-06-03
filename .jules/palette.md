## 2024-05-28 - Added Tooltips to Save/Cancel/Send Buttons
**Learning:** Tooltips are a critical accessibility feature for buttons. We noticed `st.button`s across multiple components didn't have `help` properties.
**Action:** Always include a `help` property (which translates to `title`/`aria-label`) for actionable buttons like Save, Cancel, Send Comment, etc., using the translation dictionary to ensure localization.

## 2024-05-29 - Adding Loading Spinners to Synchronous Streamlit Saves
**Learning:** While Streamlit operations like fast database inserts (`create_post`, `save_table_metadata`) execute synchronously without native `await` mechanics, user perception of action acknowledgement is drastically improved by wrapping the execution block in `with st.spinner('...'):`. Because of Streamlit's redraw cycle, the spinner correctly renders and halts upon `st.rerun()`. Additionally, ARIA compliance on `st.button` relies entirely on the `help` attribute, not an `aria-label` kwarg.
**Action:** When creating form submission buttons, always wrap the data processing logic in `with st.spinner(t("common.saving")):` and ensure icon-only buttons leverage the `help` kwarg.
