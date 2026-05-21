## 2024-05-21 - [Table Details] Added localized placeholders to text inputs
**Learning:** Hardcoded placeholders inside `st.text_input` and `st.text_area` degrade localization and accessibility, failing to offer helpful hints in the user's selected language. Adding placeholders generally enhances UX for blank fields by explaining expected input formats (e.g. email) or content scope.
**Action:** Always prefer localized placeholders from `locale/*.json` over inline string literals for Streamlit inputs, and actively seek out input fields missing these guiding texts.
