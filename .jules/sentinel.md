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
