## 2024-05-22 - [Information Disclosure]
**Vulnerability:** Leaking stack traces or internal exception details in UI error messages.
**Learning:** Returning `str(exc)` or `str(e)` in `st.error()` can expose sensitive internal data or traceback context to end users.
**Prevention:** Always log exceptions internally using `logging.error(..., exc_info=True)` and return generic, safe error messages to the UI.

## 2024-05-22 - Fix SQL Injection in details preview
**Vulnerability:** SQL Injection in detail.py during data sampling via f-strings.
**Learning:** Table identifiers cannot be parameterized, but they must still be escaped with double quotes.
**Prevention:** Always manually escape table/schema identifiers with `.replace('"', '""')` and wrap them in double quotes before interpolating.
## 2026-05-27 - [Fix XSS vulnerability in catalog rendering]
**Vulnerability:** Potential XSS via unsafe_allow_html by interpolating unescaped inputs into HTML tags.
**Learning:** Using f-strings to inject untrusted database values directly into HTML passed to Streamlit's st.html() or unsafe_allow_html=True creates an XSS vulnerability, even when escaping is attempted manually.
**Prevention:** Always use a templating engine like Jinja2 with `autoescape=True` to securely construct dynamic HTML blocks in Python apps where native UI components do not suffice.
