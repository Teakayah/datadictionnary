# Feature 2: User Personalization

## Description
This feature enables users to customize their experience by marking data assets as "Favorites" and keeping track of their recently viewed tables.

## Implementation Strategy
1. **Persistence (Local-First):** 
   - Store user preferences (bookmarks and recent activity) in a local **DuckDB** database (`.user_prefs.db`) for immediate responsiveness.
   - Implement a sync process to periodically push these local updates back to the `user_preferences` table in Databricks SQL Warehouse.
2. **Discovery UI:**
   - Transform the "Discovery" tab into a multi-tab view containing:
     - **New & Notable:** The existing feed of recently updated tables.
     - **My Bookmarks:** A personalized list of the user's favorited assets.
     - **Recently Viewed:** A chronological history of the user's navigation.
3. **Data Model:** 
   - A `user_preferences` table mapping `user_oid` to `table_full_name`, `pref_type` ('bookmark' or 'recent'), and a `last_interacted` timestamp.

## Initial Scaffolding
- Initialized `bookmarks` and `recent_views` in `st.session_state`.
- Added a placeholder for the Bookmark button in `app.py`.
