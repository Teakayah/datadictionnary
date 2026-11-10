## 2026-11-09 - Consolidate Personalization State Helpers

**Learning:** `st.session_state` sets for bookmarks, col_bookmarks, and recent_views were accessed and updated repetitively using verbose `.get(..., set()).add()` and `.discard()` methods across the UI pages (`src/pages/search.py`, `src/pages/glossary.py`, `src/ui/cards/discovery.py`). This led to error-prone duplication.
**Action:** Created dedicated helper functions (`add_bookmark`, `remove_bookmark`, `is_bookmarked`, etc.) in `src/personalization.py` to encapsulate the session state logic and associated persistent `_pref_upsert` / `_pref_delete` backend calls. Replaced the scattered accesses with these helpers, reducing boilerplate and ensuring consistency.
