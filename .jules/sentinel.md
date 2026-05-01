## 2026-05-01 - [XSS in Streamlit Markdown Rendering]
**Vulnerability:** A Cross-Site Scripting (XSS) vulnerability was found in `app.py` where a database-sourced value (`schema_name`) was directly injected into an `st.markdown(..., unsafe_allow_html=True)` call without escaping.
**Learning:** In Streamlit applications using `unsafe_allow_html=True` to render custom UI elements, all dynamically sourced strings (like catalog, schema, or table names) must be explicitly HTML escaped. Relying on the underlying data source to be "safe" is insufficient.
**Prevention:** Always use `html.escape()` (aliased as `_html.escape()`) on user-controlled or database-sourced variables before interpolating them into HTML strings rendered by Streamlit.
