# Feature 4: Metadata Export

## Description
This feature allows business users to export table definitions, column schemas, and descriptions into portable formats (CSV/Excel) for documentation or offline review.

## Implementation Strategy
1. **Utility:** Create a helper function `export_schema_to_csv` that takes a table's column metadata and converts it to a CSV string.
2. **UI:** Add an "Export Dictionary (CSV)" button using `st.download_button` in the Table Detail header.
3. **Naming:** Standardize export filenames as `{catalog}_{schema}_{table}_schema.csv`.

## Initial Scaffolding
- Added `st.download_button` to the table detail view in `app.py`.
