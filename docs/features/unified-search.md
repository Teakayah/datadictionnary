# Feature 1: Unified Global Search

## Description
This feature replaces the current table-specific dropdown with a global search bar that queries across multiple metadata dimensions:
- Table Names
- Column Names
- Descriptions (Table & Column)
- Glossary Terms

## Implementation Strategy
1. **SQL Update:** Create a new query function `search_all_metadata` that uses `UNION` or a dedicated search index table to find matches across `tables_metadata`, `columns_metadata`, and `glossary`.
2. **UI Update:** Replace the `st.selectbox` in the Search tab with a text input.
3. **Filtering:** Apply `permissions_cache` to all search results to ensure security.

## Initial Scaffolding
- Added `global_search_metadata` placeholder in `app.py`.
