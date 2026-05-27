## 2026-05-27 - Localized Python String Formatters
**Learning:** Found that metrics components like `st.metric` were relying on the Python format specifier `:,` to add thousand separators. This is inherently un-localizable since it hardcodes US commas and breaks in French locales which use spaces.
**Action:** Always replace hardcoded `f"{val:,}"` formats with a locale-aware helper function (like `format_number` in `src.i18n.py`) that checks `st.session_state.locale` to decide the separator logic.
