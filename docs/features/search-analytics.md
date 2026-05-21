# Feature: Search Analytics & Gap Analysis

## Description
Search Analytics provides Data Stewards with visibility into the "Search Gaps" of the catalog — specific terms or concepts that users are looking for but returning zero results. This allows stewards to prioritize documentation updates and add business terminology that users naturally use.

## How it Works
The analytics engine is designed to be lightweight, privacy-preserving, and integrated directly into the local storage layer.

### 1. Instrumentation
Every search query entered in the **Search** tab is intercepted and tracked. We record:
- **Query String:** The raw text the user typed.
- **Result Count:** How many assets were returned by the keyword/semantic engine.
- **User Context:** The email of the searcher (for optional follow-up by stewards).
- **Timestamp:** When the search occurred.

### 2. Storage
Analytics events are stored in a dedicated `user_data.search_analytics` table in the DuckDB cache. This table is append-only and distinct from the system audit log.

### 3. Gap Analysis UI
Admins and Stewards can access the **Search Gaps** report in the Admin dashboard. This report filters the analytics for searches where `results_count = 0`, sorted by most recent.

## Implementation Details
- **Protocol:** `AnalyticsStorage` defines the interface for tracking and retrieval.
- **Integration:** Hooked into `src/pages/search.py` immediately following the hybrid search execution.
- **Privacy:** Only records searches from authenticated users; search text is stored as-is without further processing.

## Initial Scaffolding
- Implemented `src/storage/analytics_storage.py` with DuckDB, Demo, and Fake backends.
- Updated `src/pages/search.py` to track all search events.
- Added "Search gaps" section to the Admin dashboard Insights tab.
