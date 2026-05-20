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
When mitigating XSS in Streamlit using `st.markdown(..., unsafe_allow_html=True)`, apply `_html.escape()` directly inline within the f-string interpolation rather than escaping the variable at its definition. This prevents double-escaping bugs when that same variable is later passed to standard Streamlit components like `st.text_input` which automatically escape their inputs. Additionally, for URL path variables, use `urllib.parse.quote()` instead of `html.escape()` to prevent URL injection and broken links.

## 2025-05-19 - Reflected XSS in Admin Sync Section
**Vulnerability:** A Cross-Site Scripting (XSS) vulnerability was found in the `src/ui/cards/admin.py`'s `_render_admin_sync_section` function. The operational status strings `dr_status` and `heartbeat` were dynamically injected into an `st.markdown(..., unsafe_allow_html=True)` block without sanitization.
**Learning:** Operational status messages and system metrics that flow from external worker processes (e.g. `read_dr_resync_status()`) into the UI via `unsafe_allow_html=True` can become XSS vectors if those messages contain unescaped content or error strings.
**Prevention:** Apply `_html.escape()` inline within f-string interpolations for all dynamic content rendered via `st.markdown(..., unsafe_allow_html=True)`, including internal system state and error messages.
## 2024-05-20 - Fix SQL injection in DuckDB ATTACH statement
**Vulnerability:** The `USER_DATA_PATH` and `DUCKDB_PATH` environment variables were directly interpolated into DuckDB `ATTACH` SQL queries using f-strings. This allowed for potential SQL injection if an attacker could control the file path to contain single quotes and execute arbitrary SQL commands.
**Learning:** When constructing DuckDB DDL statements (such as `ATTACH`) where parameterized queries are unsupported, manually escape single quotes in string variables using `.replace("'", "''")` prior to f-string interpolation.
**Prevention:** Always sanitize inputs that are directly interpolated into SQL strings, particularly for database driver methods that do not support parameterization.
