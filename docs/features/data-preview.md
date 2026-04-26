# Feature 5: Sample Data Preview

## Description
This feature provides users with a safe, read-only preview of the data (first 10 rows) to help them understand the content and structure of a table before they request access or start developing.

## Implementation Strategy
1. **Security:** Only attempt to fetch data if the user has `SELECT` privileges in the `permissions_cache`.
2. **Execution:** Use the `databricks-sql-connector` to run a `SELECT * FROM {table} LIMIT 10` query.
3. **UI:** Add a "Data Preview" tab to the detail page. Handle sensitive data by truncating long strings.

## Initial Scaffolding
- Added a "Data Preview" tab to the table detail view in `app.py`.
- Added a placeholder query function.
