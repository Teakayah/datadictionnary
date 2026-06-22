## 2026-06-03 - Extract Hardcoded Expiry Labels
**Learning:** The CMS post expiration dropdown uses an internal dictionary (`_EXPIRY_DAYS`) where the keys were originally displayed directly in the UI. By converting these keys to internal identifiers (e.g., '2_days') and utilizing `format_func=lambda x: t(f"cms.expiry_{x}")` in `st.selectbox`, we can decouple the internal data structure from the localized user-facing strings.
**Action:** When a UI component derives its display labels directly from a data structure's keys, convert those keys to localization tokens and use the component's formatting properties (like Streamlit's `format_func`) to resolve them at render time.

## 2026-06-03 - Extracting Formatting Information
**Learning:** Hardcoded f-strings embedding `len(df)` inside `st.info` (e.g. `f"Showing first 50 priority actions out of {len(undocumented)} for performance."`) limit translatability. They should be extracted into translation tokens that accept interpolation arguments, such as `t("health.showing_first_50", count=len(undocumented))`.
**Action:** Always extract hardcoded UI informational messages into localization dictionaries and leverage keyword interpolation rather than python f-strings.

## 2026-06-06 - Fixing Translation Dictionary Git Conflicts
**Learning:** Hardcoding English fallbacks directly into a target language's JSON file (like French) when attempting to resolve a git conflict breaks translation dictionary symmetry, often breaks type-checkers, and defeats the purpose of an i18n library's automatic fallback mechanisms.
**Action:** When resolving broken locales or missing keys, always use English strings specifically mapping to keys across both primary and secondary translation files. Avoid dumping unmatched strings randomly into the JSON to satisfy test runners; properly align keys across dictionaries instead.

## 2026-06-07 - Extracting truncation messages with count placeholders
**Learning:** Hardcoded truncation indicators like "...and 42 more tables" embed English grammar and sentence structure directly in the UI components, breaking localization efforts.
**Action:** Always extract dynamic truncation messages into the translation dictionary using named placeholders (e.g., `{count}`) and formatting the dynamic numeric parameters natively.

## 2026-06-14 - Refactoring Ternary Pluralization
**Learning:** Hardcoding English-centric ternary pluralization logic (e.g. `t(...) if count == 1 else t(...)`) directly in UI components prevents correct grammar tokenization for languages with different plural rules.
**Action:** Replace manual ternary pluralization logic with native `count`-based tokens that resolve the appropriate suffix (e.g. `_one`, `_other`) directly through the i18n library.

## 2024-06-10 - Locale-aware strftime Date Formatting
**Learning:** Standard library `strftime` uses the system's locale, which doesn't dynamically map to application `st.session_state` locales without thread-unsafe `locale.setlocale` calls. This causes components to render English month strings (e.g. `%b` -> `Jan`) in French views on Unix servers.
**Action:** Always extract hardcoded `strftime` components and resolve them dynamically via the `t()` dictionary keys (e.g., adding `date.months.1`, etc. and replacing `%b` with the looked-up string) to ensure thread-safe, native translation formatting.
