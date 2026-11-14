# Interactive Multi-hop Lineage

## Overview
The table detail view (`src/pages/search.py`) renders an interactive multi-hop lineage graph (`src/ui/lineage.py`) built with `vis-network` (`barnesHut` layout with `avoidOverlap: 0.85`). Users can drag to pan, scroll to zoom, open an expanded fullscreen modal (`render_lineage_fullscreen`), and **double-click any non-current table node** to jump directly to that table's detail view.

## Implementation
1. **Multi-hop graph assembly (`_build_lineage_graph`):** Recursively traverses `WITH RECURSIVE` lineage edges up to `max_depth=2` (permission-filtered by `query_groups`), highlighting the active table in accent red (`#B8362A`) and related tables by relationship type.
2. **Readable initial zoom:** After stabilization, `net.fit()` is clamped between `min_scale` (`0.8` inline, `0.75` fullscreen) and `1.15`, centering on the current table node when the graph is large so labels remain legible.
3. **Bidirectional double-click navigation (`dd_lineage_vis`):** Mounted via `st.components.v2.component` (`render_lineage_graph`, cached per Streamlit runtime via `_get_lineage_component()`). Both `vis.Network` `"doubleClick"` and native DOM `"dblclick"` (`net.getNodeAt(...)`, 500 ms debounce) call `setTriggerValue("nav", nodeId)` so `_trigger_lineage_navigation()` updates `dd_search_override` + `dd_nav_select` and reruns into the target table.
