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

## 2026-06-18 - Extract Hardcoded Input Placeholders
**Learning:** Hardcoded strings embedded directly as `placeholder` values inside input UI components (e.g., `st.text_input(..., placeholder="e.g., Customer Loyalty ID")`) are not naturally extracted by external i18n scanners and require manual refactoring into translation dictionaries.
## 2026-06-24 - Date Formatting & ARIA Labels
**Learning:** Python `strftime` defaults to system locales and hardcodes English strings (e.g. month names), which bypasses localization. Furthermore, raw strings passed to UI components often need to be parsed to ISO datetimes first to enable proper i18n formatting without relying on manual string slicing.
**Action:** When working on UI components that render dates, do not use `.strftime()` directly. Instead, leverage the central `src.i18n.format_date()` function and update it to accept raw ISO strings if necessary to prevent format string fragmentation.
## 2026-07-11 - Streamlit AppTest vs st.segmented_control mocking
**Learning:** Testing component rendering inside Streamlit's `st.segmented_control` blocks with AppTest often fails because updating `at.session_state` or `at.segmented_control(...).set_value()` does not correctly trigger the internal Streamlit rerender mapping the new active value. When the segmented_control values use translated strings (`t()`), this can cause test failures.
**Action:** When asserting the presence of components that render conditionally on `st.segmented_control` values, bypass the widget behavior by explicitly mocking the output using `with patch('module.st.segmented_control') as mock_sc: mock_sc.return_value = "TabName"`. Be aware this assumes the patch module is correctly imported in the target test file.

## 2025-07-30 - Localizing Streamlit st.column_config
**Learning:** When localizing Streamlit `st.dataframe`, do not forget that column headers inside `column_config` support translated strings directly, but any HTML headers inside `st.markdown()` blocks need f-string interpolation with the translation function.
**Action:** Ensure both markdown and `st.dataframe` headers are translated together for a cohesive localized UI.
## 2025-02-27 - Extract hardcoded time formatting
**Learning:** Python's `dt.strftime("%H:%M")` was hardcoded in `src/i18n.py`, enforcing a 24-hour clock across all locales.
**Action:** Extract format string to locale dictionaries (e.g. `t("date.time_format")`) to support native formatting styles like `%I:%M %p` (12-hour AM/PM) for US English and `%H:%M` for French.

## 2026-08-22 - Extract Hardcoded Backend Labels in Pipelines
**Learning:** Hardcoded dictionary values for backend labels in UI components (like `_BACKEND_LABEL = {"databricks": "Databricks", ...}`) prevent translation of these labels. By refactoring to use translation keys directly via `format_func` (e.g., `format_func=lambda x: t(f"pipelines.backend_{x}")`), the UI can dynamically resolve the localized strings while keeping internal state keys clean.
**Action:** When a UI component uses a dictionary to map internal keys to display labels, extract the display labels to the translation file and use `format_func` with `t()` to localize the options instead. Tests may need to be updated to select the internal key (e.g., `"databricks"`) instead of the hardcoded display label (e.g., `"Databricks"`).
## 2024-08-24 - Extracted missing search layout localization keys
**Learning:** Found dynamically formatted strings missing from the translation files that caused hardcoded language strings to appear or silent fallbacks.
**Action:** Always ensure that interpolated text or variants inside application source code exist in the respective `locale` dictionary to keep it dynamic.

## 2024-08-31 - Extracting Hardcoded Formatted Tooltips
**Learning:** Hardcoded f-strings within UI components, specifically inside HTML attributes like `title="Completeness grade {grade}"`, prevent translation. When formatting is nested inside HTML generation, you must extract the entire formatted string as a translation token that accepts interpolation.
**Action:** Extract hardcoded hover tooltips and `title` attributes into the translation dictionary using named placeholders, and use `t('key', param=value)` to inject the string before escaping it for HTML.
## 2026-09-12 - Extract Missing Fallback Keys
**Learning:** The i18n module gracefully falls back to the dotted key (e.g. `admin.sync_progress`) if a key is missing from the translation files, hiding the missing key problem by appearing as technical text. However, dynamically formatted fallback keys, especially those containing interpolated values, break completely because the template (`{pct}`) expects format strings which are absent in the raw fallback token.
**Action:** Always ensure that dynamically formatted strings or any variants inside application source code actually exist in the respective `locale` dictionary to keep it correctly translatable and dynamic.
## 2024-08-25 - Extracted missing search.showing_first_50 localization key
**Learning:** Found a dynamically formatted string `search.showing_first_50` missing from the translation files that caused hardcoded language strings to appear or silent fallbacks. The key was requested by `src/pages/search.py` via `t("search.showing_first_50")` and `src/ui/cards/admin.py` but was not present in the locale dictionaries, despite a similar `showing_first_50` key existing under `health`.
**Action:** Always ensure that interpolated text or variants inside application source code exist in the respective `locale` dictionary to keep it dynamic.

## 2026-10-25 - Missing dynamically formatted fallback keys
**Learning:** Dynamically formatted keys (e.g. `t("admin.reviews_approved_toast", col=col)`) must exist in the locale dictionaries. If they are missing, the i18n module falls back to the dotted key name. However, since the fallback token does not contain format string placeholders (like `{col}`), the string formatting step crashes or drops the dynamic value.
**Action:** Always ensure that dynamically formatted strings exist in the respective `locale` dictionary to keep it correctly translatable and dynamic.
