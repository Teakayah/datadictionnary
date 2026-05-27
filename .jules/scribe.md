## 2024-05-24 - [DuckDB Parameterization Insight]
**Learning:** DuckDB requires explicit array operators (`= ANY(...)`) instead of standard `IN (...)` parameter unrolling when passing lists/tuples from Python. This conversion is handled automatically by `_to_duckdb_sql`.
**Action:** Expanded the docstring for `_to_duckdb_sql` to provide clearer context on why this specific regex transformation exists.

## 2024-05-24 - [Complex Regex Documentation]
**Learning:** Hardcoded regular expressions used for security validation (e.g., `_IDENT_RE` and `_EMAIL_RE` in `src/sync/push.py`) are critical for preventing SQL injection and quote-escape bypasses. Without descriptive comments, their precise security purpose and the characters they match are not immediately obvious to new developers.
**Action:** Always add detailed docstrings or inline comments to complex Regex patterns used for security validation. Explain exactly what characters are matched and why the validation is necessary for the specific downstream system (e.g., Databricks Unity Catalog).

## 2024-05-27 - [Docstring Style Consistency]
**Learning:** Python docstrings in this repository should ideally utilize established formats (Sphinx, Google, or NumPy) instead of adopting JS/TS-style `@param` and `@returns` tags, even though `@param` tags were pre-existing in parts of the codebase.
**Action:** When adding or updating Python docstrings, use Python-native style tags to adhere to standard Python ecosystem conventions rather than porting frontend-style conventions.
