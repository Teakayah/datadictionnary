# Feature 3: Interactive Data Quality Dashboard

## Description
This feature provides visibility into the health and reliability of data assets by surfacing Data Quality (DQ) metrics directly in the dictionary.

## Implementation Strategy
1. **Data Source:** Integrate with Databricks Lakehouse Monitoring or custom DQ frameworks (like Great Expectations) by reading dedicated tags or audit tables.
2. **Backend:** Update `sync_metadata.py` to extract `dq_score`, `last_run_status`, and `freshness` metrics.
3. **UI:** Add a "Data Health" scorecard to the Table Detail sidebar with color-coded status indicators (Pass/Fail/Warning).

## Initial Scaffolding
- Added `data_quality_cache` table definition in `sync_metadata.py`.
- Added a placeholder DQ scorecard in `app.py`.
