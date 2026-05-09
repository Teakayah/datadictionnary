# Security Sentinel Log

## 2025-05-01 - Reflected XSS in Glossary Markdown
**Vulnerability:** Cross-Site Scripting (XSS) vulnerability was found in the `app.py`'s `render_glossary` function. Specifically, dynamic variables like glossary `term_row["term"]`, `term_row["definition"]`, `term_row["calculation"]`, `term_row["domain"]`, and `term_row["steward"]` were interpolated directly into a multi-line `st.markdown(..., unsafe_allow_html=True)` block without prior HTML sanitization.
**Learning:** `unsafe_allow_html=True` allows direct rendering of HTML strings to enable complex layout styles, but it makes any unescaped string injection highly vulnerable to XSS if those values can be tampered with or contain unescaped entities (e.g. from user input or databases). Although `_DEMO_GLOSSARY` currently acts as the source, the mechanism presents a risk for future enhancements relying on external sources.
**Prevention:** Always use `html.escape()` around any dynamic string variables that are being interpolated into an `st.markdown(..., unsafe_allow_html=True)` call.

## 2025-05-03 - Invalid DDL parameterization bypassing security checks
**Vulnerability:** Incorrect extraction of a dictionary key (`steward` vs `steward_email`) resulted in a bug bypassing the security check enforcing that Unity Catalog steward tags must be correctly-formed email addresses. This was fixed without needing to refactor the Databricks SQL Connector parameters.
**Learning:** DDL queries (`ALTER TABLE`, `COMMENT ON TABLE`) to Databricks can not use native parameterized DBAPI arguments natively, but must be escaped manually and string formatted (`.replace("'", "''")` inside an f-string) before sending.
**Prevention:** Continue to use parameterized queries (`%(key)s`) for DML calls, and manual string escaping (`replace("'", "''")`) for DDL calls. Ensure dictionary key lookups align with payload construction.

## 2025-05-08 - SQL Injection in Databricks DDL Statements
**Vulnerability:** SQL Injection vulnerabilities were found in `src/sync/push.py`, `scripts/nightly_sync.py`, and `scripts/sync_metadata.py`. Malicious input (e.g., comments or business names) was being directly interpolated into `ALTER TABLE` and `COMMENT ON` SQL statements.
**Learning:** Even though Databricks SQL DDL might seem safe if some manual escaping is present (like `.replace("'", "''")`), it is still vulnerable and non-idiomatic. Modern versions of the `databricks-sql-connector` (3.0.0+) support native parameterization for literal values in many DDL statements.
**Prevention:** Use parameterized queries (`%(param)s`) for all literal values in SQL statements, including DDL comments. For identifiers like table and column names that cannot be parameterized, use strict validation (regex) and/or proper identifier escaping (wrapping in backticks and doubling internal backticks).
