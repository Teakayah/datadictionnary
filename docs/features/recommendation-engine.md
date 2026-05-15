# Feature: Activity-Based Recommendation Engine

## Description
The Recommendation Engine surface's popular and active data assets to users, encouraging the discovery of high-value tables within their authorized scope. It powers the "Recommended" sub-tab in the Discovery interface.

## How it Works
The engine uses a popularity-based heuristic derived from organization-wide activity, rather than complex collaborative filtering. This ensures relevance even with smaller user bases.

### 1. Activity Aggregation
The engine queries the `user_data.audit_log` to identify tables with the highest recent engagement. It specifically tracks:
- **Metadata Edits:** Changes to table descriptions or column business names.
- **Social Signals:** New comments or threaded replies added to a table.

### 2. Personalization & Security
To ensure the recommendations are safe and helpful, the engine applies two layers of filtering:
- **Authorization Filter:** Results are cross-referenced with the `permissions_cache`. A user only ever sees recommendations for tables they are authorized to access.
- **Novelty Filter:** Tables that appear in the user's "Recently Viewed" list (last 5 interactions) are excluded. This prevents the engine from recommending assets the user is already actively using.

### 3. Implementation Logic
The recommendation is performed via a single SQL query against the local DuckDB cache:
```sql
SELECT object_name, COUNT(*) AS engagement_score
FROM user_data.audit_log
WHERE event_type IN ('table_description_change', 'business_name_change', 'comment_added')
GROUP BY object_name 
ORDER BY engagement_score DESC 
LIMIT 30;
```

## Initial Scaffolding
- Implemented `_get_recommended_tables` in `src/ui/cards/discovery.py`.
- Added the "Recommended" tab to the Discovery dashboard.
- Integrated with `st.session_state.recent_views` for the novelty filter.
