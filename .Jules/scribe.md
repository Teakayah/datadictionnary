## 2024-05-05 - Documenting Database Routing & Authorization Layers
**Learning:** Found that the dual caching (Demo mode vs. DuckDB vs. Databricks) and row-level access control via Entra ID groups in `src/db/queries.py` are core architectural pieces that lacked docstrings.
**Action:** Always verify docstrings exist for functions serving as critical routing abstractions or access control gates in applications using hybrid mock/production database connectivity.
## 2026-05-12 - [Regex Comment] Learning: Unity Catalog 3-level namespace validation regex logic is r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$", indicating each catalog, schema, and table segment uses only letters, numbers, and underscores, without dashes. Action: Ensure any future DB mocks adhere strictly to this regex logic.
## 2024-05-15 - Outdated Architectural Notes
**Learning:** Found an outdated architectural note (`NOTE — Phase 4b (deferred)`) in `src/db/queries.py` claiming several core functions (`get_authorized_tables`, `search_all_metadata`, etc.) were still located in `app.py`. These had already been correctly relocated to `src/db/queries.py`, making the note actively misleading to future developers.
**Action:** When working in core routing or abstraction files (like `src/db/queries.py`), always verify that module-level docstrings describing the location of other components are still accurate, and remove them if they have become stale.
## 2024-05-18 - Outdated Architectural Notes
**Learning:** Found an outdated architectural note in `src/db/queries.py` claiming demo-mode interception lived in `app.py`. The interception logic had already been relocated to `run_query` inside `src/db/queries.py`, making the module docstring actively misleading.
**Action:** When working in core routing or abstraction files, always verify that module-level docstrings describing the location of other components are still accurate, and remove or update them if they have become stale.
