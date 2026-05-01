## 2026-05-01 - Tooltips for icon-only buttons
**Learning:** Streamlit's `st.button` does not have an explicit `aria-label` parameter, so the best way to make icon-only buttons (like `★`, `☆`, `✎`) accessible is to use the `help` parameter. This adds a visual tooltip on hover and also serves as the accessible description for screen readers.
**Action:** Always check `st.button` calls in Streamlit apps for the `help` parameter if the button content is purely symbolic or an icon. Ensure the tooltip text is correctly localized using the app's `t()` function.
