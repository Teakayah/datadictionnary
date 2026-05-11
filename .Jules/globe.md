## 2026-05-05 - [Interpolation with Custom i18n hook]
**Learning:** The application implements internationalization (i18n) via a custom `t()` function that resolves dot-notation keys against nested JSON dictionaries located in the `locale/` directory. It natively supports `str.format()` style string interpolation via keyword arguments (e.g., `t('common.error_with_details', error=str(e))`), eliminating the need for string concatenation.
**Action:** When translating strings that include variables, always use the built-in interpolation capability of the `t()` function with keyword arguments.
## 2025-05-15 - Strftime Format Strings
**Learning:** To localize `strftime` date formats using the repository's custom `t()` i18n function, store the format string (e.g., `"%b %d, %Y"`) inside the `locale/*.json` dictionaries and pass the localized string directly into the datetime object's formatting method: `dt.strftime(t('namespace.date_format_key'))`.
**Action:** When refactoring hardcoded date representations generated via `strftime`, always move the underlying format string into the translation dictionaries to support locale-specific month/day ordering and structures.
## 2025-05-15 - [Extract Hardcoded "started by" String in Pipelines]
**Learning:** Found a hardcoded string 'started by {user} · {date}' in the pipelines card component (src/ui/cards/pipelines.py:214). This should be extracted into the translation files, using proper i18n placeholders for the user and date to avoid string concatenation issues in other languages.
**Action:** Extract the key 'pipelines.started_by' with value 'started by {user} · {date}' into en.json and fr.json ('lancé par {user} · {date}'). Update src/ui/cards/pipelines.py to use the translation function.
