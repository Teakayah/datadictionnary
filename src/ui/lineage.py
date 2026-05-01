import streamlit as st
import pandas as pd
import json as _json
import streamlit.components.v1 as components
from src.i18n import t
from src.ui.css import VIS_WIDE_CSS


def _viewport_height(fallback: int = 800) -> int:
    """Read the viewport height injected into session state by streamlit_js_eval."""
    try:
        h = st.session_state.get("_dd_vh", fallback)
        return int(h) if h else fallback
    except (ValueError, TypeError):
        return fallback


def _fetch_lineage_hop(
    node_fn: str, query_groups: list, run_query
) -> "pd.DataFrame | None":
    """Fetch direct lineage neighbors of node_fn, permission-filtered."""
    lin_ph = (
        ", ".join([f"%(lin_g_{i})s" for i in range(len(query_groups))])
        if query_groups
        else "''"
    )
    params: dict = {"table_full_name": node_fn}
    for i, g in enumerate(query_groups):
        params[f"lin_g_{i}"] = g

    q = f"""
        SELECT source_table_full_name, target_table_full_name, relationship_type
        FROM system.access.table_lineage
        WHERE (source_table_full_name = %(table_full_name)s OR target_table_full_name = %(table_full_name)s)
        AND source_table_full_name IN (
            SELECT table_full_name FROM tables_metadata
            WHERE steward_email = 'SELECT_ALL_USERS'
               OR catalog_name IN ({lin_ph})
               OR schema_name IN ({lin_ph})
        )
        AND target_table_full_name IN (
            SELECT table_full_name FROM tables_metadata
            WHERE steward_email = 'SELECT_ALL_USERS'
               OR catalog_name IN ({lin_ph})
               OR schema_name IN ({lin_ph})
        )
    """
    return run_query(q, params)


def _build_lineage_graph(
    start_fn: str, start_label: str, query_groups: list, run_query, max_depth: int = 2
):
    """BFS multi-hop lineage. Returns (graph_nodes, graph_links)."""
    graph_nodes = [
        {
            "id": start_fn,
            "label": start_label,
            "current": True,
            "relationship": "Current",
        }
    ]
    graph_links: list = []
    visited: set = {start_fn}
    frontier = [start_fn]

    _seen_nodes = {start_fn}
    _seen_links = set()

    for _ in range(max_depth):
        if not frontier:
            break
        next_frontier: list = []
        for current_node in frontier:
            hop_df = _fetch_lineage_hop(current_node, query_groups, run_query)
            if hop_df is None or hop_df.empty:
                continue

            for row in hop_df.itertuples(index=False):
                src = getattr(row, "source_table_full_name", None)
                tgt = getattr(row, "target_table_full_name", None)
                rel = getattr(row, "relationship_type", "Lineage")

                if not src or not tgt:
                    continue

                # Add nodes if new
                for n in (src, tgt):
                    if n not in _seen_nodes:
                        lbl = str(n).split(".")[-1]
                        graph_nodes.append(
                            {
                                "id": n,
                                "label": lbl,
                                "current": False,
                                "relationship": "Related",
                            }
                        )
                        _seen_nodes.add(n)
                        if n not in visited:
                            next_frontier.append(n)
                            visited.add(n)

                # Add link if new
                link_id = f"{src}_{tgt}_{rel}"
                if link_id not in _seen_links:
                    graph_links.append({"source": src, "target": tgt, "type": rel})
                    _seen_links.add(link_id)

        frontier = next_frontier

    return graph_nodes, graph_links


def _lineage_vis_html(
    graph_nodes: list,
    graph_links: list,
    height: int = 350,
    container_id: str = "mynetwork",
    spring_length: int = 120,
) -> str:
    nodes_js = _json.dumps(graph_nodes)
    edges_js = _json.dumps(graph_links)
    return (
        f'<div id="{container_id}" style="width:100%;height:{height}px;background:#F2EDE1;border-radius:4px;'
        'border:1px solid #D8D2C4;"></div>'
        f'''
<script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<script type="text/javascript">
  var nodes = new vis.DataSet({nodes_js}.map(n => ({{
      id: n.id,
      label: n.label,
      shape: "box",
      color: n.current ? {{background:"#E2E8F0", border:"#475569"}} : {{background:"#FFFFFF", border:"#94A3B8"}},
      font: {{face: "Inter, sans-serif", size: 14, color: "#1E293B"}}
  }})));
  var edges = new vis.DataSet({edges_js}.map(e => ({{
      from: e.source,
      to: e.target,
      label: e.type,
      font: {{align: "middle", size: 10, color: "#64748B", face: "Inter, sans-serif"}},
      color: {{color: "#CBD5E1", highlight: "#94A3B8"}},
      arrows: "to",
      dashes: e.type !== "Lineage"
  }})));
  var container = document.getElementById("{container_id}");
  var data = {{ nodes: nodes, edges: edges }};
  var options = {{
      physics: {{
          barnesHut: {{ springLength: {spring_length}, springConstant: 0.04, damping: 0.09 }},
          stabilization: {{ iterations: 150 }}
      }},
      interaction: {{ hover: true, tooltipDelay: 200, zoomView: true }},
      layout: {{ improvedLayout: true }}
  }};
  new vis.Network(container, data, options);
</script>
'''
    )


@st.dialog(t("detail.lineage_graph"), width="large")
def render_lineage_fullscreen(
    graph_nodes: list, graph_links: list, full_name: str, run_query
):
    st.markdown(VIS_WIDE_CSS, unsafe_allow_html=True)
    st.markdown(
        f"**{full_name}** — {t('detail.lineage_graph_subtitle').format(table=full_name.split('.')[-1])}"
    )
    # Use a large fixed canvas — CSS in VIS_WIDE_CSS stretches the iframe to
    # calc(95vh - 190px), so the vis.js div just needs to be big enough that
    # the graph isn't clipped before CSS takes over.
    vh = _viewport_height()
    canvas_h = max(600, vh - 200)

    html = _lineage_vis_html(
        graph_nodes,
        graph_links,
        height=canvas_h,
        container_id="fs_network",
        spring_length=200,
    )
    components.html(html, height=canvas_h + 20, scrolling=False)
