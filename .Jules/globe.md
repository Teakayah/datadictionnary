## 2026-05-05 - [Interpolation with Custom i18n hook]
**Learning:** The application implements internationalization (i18n) via a custom `t()` function that resolves dot-notation keys against nested JSON dictionaries located in the `locale/` directory. It natively supports `str.format()` style string interpolation via keyword arguments (e.g., `t('common.error_with_details', error=str(e))`), eliminating the need for string concatenation.
**Action:** When translating strings that include variables, always use the built-in interpolation capability of the `t()` function with keyword arguments.
