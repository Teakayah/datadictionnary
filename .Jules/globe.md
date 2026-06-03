## 2026-06-03 - Extract Hardcoded Expiry Labels
**Learning:** The CMS post expiration dropdown uses an internal dictionary (`_EXPIRY_DAYS`) where the keys were originally displayed directly in the UI. By converting these keys to internal identifiers (e.g., '2_days') and utilizing `format_func=lambda x: t(f"cms.expiry_{x}")` in `st.selectbox`, we can decouple the internal data structure from the localized user-facing strings.
**Action:** When a UI component derives its display labels directly from a data structure's keys, convert those keys to localization tokens and use the component's formatting properties (like Streamlit's `format_func`) to resolve them at render time.

## 2026-06-03 - Extracting Formatting Information
**Learning:** Hardcoded f-strings embedding `len(df)` inside `st.info` (e.g. `f"Showing first 50 priority actions out of {len(undocumented)} for performance."`) limit translatability. They should be extracted into translation tokens that accept interpolation arguments, such as `t("health.showing_first_50", count=len(undocumented))`.
**Action:** Always extract hardcoded UI informational messages into localization dictionaries and leverage keyword interpolation rather than python f-strings.
