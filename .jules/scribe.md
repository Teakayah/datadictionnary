## 2024-05-08 - Documenting Global Search Metadata
**Learning:** Found that `search_all_metadata` in `src/db/queries.py` had a minimal docstring despite containing complex UNION SQL logic and a custom multi-domain scoring algorithm (Tables, Columns, Glossaries).
**Action:** Always ensure that core search functionality containing custom weighting and cross-domain data aggregation logic has detailed documentation explaining the scoring mechanism and what domains are covered.
