## 2026-05-05 - [Interpolation with Custom i18n hook]
**Learning:** The application implements internationalization (i18n) via a custom `t()` function that resolves dot-notation keys against nested JSON dictionaries located in the `locale/` directory. It natively supports `str.format()` style string interpolation via keyword arguments (e.g., `t('common.error_with_details', error=str(e))`), eliminating the need for string concatenation.
**Action:** When translating strings that include variables, always use the built-in interpolation capability of the `t()` function with keyword arguments.
## 2025-05-15 - Strftime Format Strings
**Learning:** To localize `strftime` date formats using the repository's custom `t()` i18n function, store the format string (e.g., `"%b %d, %Y"`) inside the `locale/*.json` dictionaries and pass the localized string directly into the datetime object's formatting method: `dt.strftime(t('namespace.date_format_key'))`.
**Action:** When refactoring hardcoded date representations generated via `strftime`, always move the underlying format string into the translation dictionaries to support locale-specific month/day ordering and structures.
## 2024-05-12 - [Extracted Sign-in Strings]
**Learning:** The authentication page (`src/auth.py`) contained multiple hardcoded strings directly in the Streamlit UI components and f-strings. These string literals must be wrapped in `t('auth.*')` calls using standard translation methods. Streamlit f-strings should interpolate translations directly.
**Action:** Before implementing localization, always ensure strings inside HTML block interpolations or selectboxes inside `src/auth.py` and other files are fully wrapped using the `t` function to maintain compatibility.
