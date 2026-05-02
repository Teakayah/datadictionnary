## 2024-05-24 - Streamlit Icon-Only Button Accessibility
**Learning:** In Streamlit applications, `st.button` does not have an explicit `aria-label` parameter. This makes icon-only buttons (like "★" for bookmarks or "✎" for editing) inaccessible to screen readers by default.
**Action:** Use the `help` parameter on `st.button` to provide tooltips for icon-only buttons. The text passed to `help` serves as an accessible description for screen readers while also improving the mouse hover UX.
