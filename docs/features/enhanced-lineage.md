# Feature 6: Enhanced Multi-hop Lineage

## Description
This feature transforms the static 1-hop lineage view into an interactive exploration tool, allowing users to trace data dependencies across the entire organization by expanding nodes on click.

## Implementation Strategy
1. **Interactive Visualization:** Update the `vis-network` JavaScript configuration to enable `selectNode` events.
2. **Dynamic Loading:** Implement a Streamlit callback (via `st.query_params` or a custom component event) that triggers a fetch for the next level of lineage when a node is selected.
3. **Graph Persistence:** Maintain a local graph state (nodes and edges) that grows as the user explores.

## Initial Scaffolding
- Added documentation in `FEATURE_PLAN.md` regarding the `vis-network` event integration.
- Added a placeholder for the multi-hop lineage retrieval logic in `app.py`.
