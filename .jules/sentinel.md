## 2024-05-22 - [Information Disclosure]
**Vulnerability:** Leaking stack traces or internal exception details in UI error messages.
**Learning:** Returning `str(exc)` or `str(e)` in `st.error()` can expose sensitive internal data or traceback context to end users.
**Prevention:** Always log exceptions internally using `logging.error(..., exc_info=True)` and return generic, safe error messages to the UI.

## 2024-05-22 - Fix SQL Injection in details preview
**Vulnerability:** SQL Injection in detail.py during data sampling via f-strings.
**Learning:** Table identifiers cannot be parameterized, but they must still be escaped with double quotes.
**Prevention:** Always manually escape table/schema identifiers with `.replace('"', '""')` and wrap them in double quotes before interpolating.

## 2025-05-26 - Fix SQL Injection in table preview
**Vulnerability:** SQL Injection via improperly escaped table identifiers that bypass strict tuple unpacking and newline regex bypass.
**Learning:** The previous implementation strictly enforced a 3-part namespace logic via `re.match` which was both bypassable with a newline anchor (`$`) and functionally brittle. It did not properly escape varying length tables.
**Prevention:** Use dynamic list comprehensions to explicitly escape all identifier parts: `['"' + p.replace('"', '""') + '"' for p in name.split(".")]` to safely support names of any length and strictly prevent SQL injections.
