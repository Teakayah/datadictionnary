## 2024-05-22 - [Information Disclosure]
**Vulnerability:** Leaking stack traces or internal exception details in UI error messages.
**Learning:** Returning `str(exc)` or `str(e)` in `st.error()` can expose sensitive internal data or traceback context to end users.
**Prevention:** Always log exceptions internally using `logging.error(..., exc_info=True)` and return generic, safe error messages to the UI.

## 2024-05-22 - Fix SQL Injection in details preview
**Vulnerability:** SQL Injection in detail.py during data sampling via f-strings.
**Learning:** Table identifiers cannot be parameterized, but they must still be escaped with double quotes.
**Prevention:** Always manually escape table/schema identifiers with `.replace('"', '""')` and wrap them in double quotes before interpolating.

## 2026-05-27 - Streamlit unsafe_allow_html XSS
**Vulnerability:** User-controlled strings (like labels and dates derived from database values) were interpolated directly into `st.markdown` calls with `unsafe_allow_html=True` in UI cards, creating XSS vulnerabilities.
**Learning:** Even internal formatting values fetched from a dictionary or database need to be explicitly escaped if they are ultimately injected into raw HTML rendered by Streamlit.
**Prevention:** Always wrap dynamically interpolated variables with `html.escape()` before injecting them into HTML strings when `unsafe_allow_html=True` is used.

## 2025-05-26 - Fix SQL Injection in table preview
**Vulnerability:** SQL Injection via improperly escaped table identifiers that bypass strict tuple unpacking and newline regex bypass.
**Learning:** The previous implementation strictly enforced a 3-part namespace logic via `re.match` which was both bypassable with a newline anchor (`$`) and functionally brittle. It did not properly escape varying length tables.
**Prevention:** Use dynamic list comprehensions to explicitly escape all identifier parts: `['"' + p.replace('"', '""') + '"' for p in name.split(".")]` to safely support names of any length and strictly prevent SQL injections.

## 2024-05-23 - [Information Disclosure]
**Vulnerability:** Leaking exception details to UI via `st.error(str(exc))`
**Learning:** Returning `str(exc)` in `st.error()` can expose sensitive internal data or traceback context to end users.
**Prevention:** Always log exceptions internally using `logging.error(..., exc_info=True)` and return generic, safe error messages to the UI.

## 2024-05-24 - Fix SQL Injection in DuckDB ATTACH
**Vulnerability:** SQL Injection via f-strings in DuckDB `ATTACH` DDL statements.
**Learning:** DuckDB does not support parameterized bindings for DDL commands like `ATTACH`. Dollar quoting provides a safe alternative for string interpolation, but requires care.
**Prevention:** To securely interpolate dynamic paths into DDL queries using f-strings, strip null bytes (`\x00`) to prevent C-string truncation, and enclose the string using dollar-quoting with a randomized alphabetic-prefixed token (e.g., `tok = 't' + secrets.token_hex(8)` then `f'ATTACH ${tok}${path}${tok}$ ...'`).

## 2026-06-01 - Prevent SQL Injection in DuckDB ATTACH Commands
**Vulnerability:** SQL Injection in DuckDB `ATTACH` statements caused by unsafe f-string formatting and insufficient path sanitization.
**Learning:** DuckDB does not support parameterized query bindings for DDL commands like `ATTACH`. Attempting to escape quotes manually is prone to failure or evasion. DuckDB dollar quoting is required for safe injection.
**Prevention:** Use dollar-quoting with a uniquely generated token (e.g., `$token$path$token$`) combined with null-byte stripping (``) to prevent parser truncation and securely interpolate dynamic paths.
## 2024-05-31 - Information disclosure via raw exceptions
**Vulnerability:** Raw Python exceptions were passed directly to `st.error(str(e))` in Streamlit applications.
**Learning:** Exposing raw exception details (like `ValueError` messages which might contain user inputs, schema paths, or variable values) to the UI is a security vulnerability (information disclosure). Even "safe-looking" validation errors should be abstracted behind generic localized strings.
**Prevention:** Always log exceptions internally using `logging.error(..., exc_info=True)` and present generic, translated error messages to the user like `st.error(t("common.error"))`.

## 2026-08-07 - Fix SQL Injection in dr_resync
**Vulnerability:** Second-order SQL injection in DuckDB due to unescaped column names returned from Databricks queries.
**Learning:** Column names fetched from an external source (Databricks) and injected into an f-string or string joined DuckDB query without escaping could execute arbitrary SQL on the backend database running in the daemon.
**Prevention:** Add a `_escape_id` function to properly escape column names (` '"' + str(val).replace('"', '""') + '"' `), and use positional parameter placeholders `?` in the fallback logic.
## 2024-05-24 - Do not leak internal exception details to client
**Vulnerability:** Leaking internal `JWTError` exception details via HTTP 401 response in `/mcp` endpoints.
**Learning:** FastAPI's HTTPException and ValueError passing strings directly to `str(exc)` in dependencies can inadvertently expose underlying library stack traces or exception strings.
**Prevention:** Sanitize or hardcode error strings returned to the client on authentication failures, ensuring no underlying library strings are leaked.

## 2024-05-27 - Streamlit unsafe_allow_html XSS in UI cards
**Vulnerability:** Cross-Site Scripting (XSS) via unescaped localized strings from `t()` in Streamlit `unsafe_allow_html` blocks.
**Learning:** Even if inner interpolation variables are escaped, the translated strings themselves may contain unescaped characters (like apostrophes) that can introduce XSS or break HTML when injected into raw HTML blocks via `st.markdown(..., unsafe_allow_html=True)`.
**Prevention:** Always wrap the entire translation output in `_html.escape(t(...))` before injecting it into HTML strings when `unsafe_allow_html=True` is used.
## 2024-05-24 - SQL Injection in DuckDB ATTACH Commands
**Vulnerability:** SQL Injection via path breakout in DuckDB `ATTACH` queries using `$token$` quoting.
**Learning:** DuckDB does not support standard parameterized queries (like `?`) for `ATTACH` statements. When using f-strings to format user-provided paths, dollar-quoting (`$token$`) is insecure if the token itself can be injected by the user to break out of the string literal.
**Prevention:** Always use single quotes for string literals in dynamically constructed `ATTACH` statements and sanitize paths by doubling up single quotes (`replace("'", "''")`) to prevent string breakout.
## 2025-03-05 - Fix XSS in Admin UI Unsafe HTML
**Vulnerability:** Localized strings were injected directly into Streamlit's `st.markdown(..., unsafe_allow_html=True)` without escaping, leading to potential Cross-Site Scripting (XSS).
**Learning:** Even if inner interpolation variables are escaped, the translated strings themselves may contain characters that can introduce XSS or break HTML when injected into raw HTML blocks.
**Prevention:** Always wrap the entire translation output in `_html.escape(t(...))` before injecting it into HTML strings when `unsafe_allow_html=True` is used.
## 2025-03-05 - Fix XSS in Admin UI Unsafe HTML
**Vulnerability:** Localized strings were injected directly into Streamlit's `st.markdown(..., unsafe_allow_html=True)` without escaping, leading to potential Cross-Site Scripting (XSS).
**Learning:** Even if inner interpolation variables are escaped, the translated strings themselves may contain characters that can introduce XSS or break HTML when injected into raw HTML blocks.
**Prevention:** Always wrap the entire translation output in `_html.escape(t(...))` before injecting it into HTML strings when `unsafe_allow_html=True` is used.
