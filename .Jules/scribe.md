## 2024-05-05 - Documenting Database Routing & Authorization Layers
**Learning:** Found that the dual caching (Demo mode vs. DuckDB vs. Databricks) and row-level access control via Entra ID groups in `src/db/queries.py` are core architectural pieces that lacked docstrings.
**Action:** Always verify docstrings exist for functions serving as critical routing abstractions or access control gates in applications using hybrid mock/production database connectivity.

## 2026-05-10 - Documenting Regexes in Sync Worker
**Learning:** Found that complex regular expressions, such as `_IDENT_RE` and `_EMAIL_RE` used for identifier and steward validation in Databricks push operations (`src/sync/push.py`), lacked explanations of what they actually match and why. These validation regexes are critical for security to prevent injection attacks and ensure data integrity in Unity Catalog.
**Action:** Always add clear, inline documentation breaking down the matching criteria (e.g., allowed characters, required structure) for critical validation regular expressions.
