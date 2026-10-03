from __future__ import annotations
"""Lineage graph building and rendering components."""


import json

import streamlit as st
import streamlit.components.v1 as components

from src.config import CATALOG_CACHE, SCHEMA_CACHE
from src.i18n import t
from src.ui.css import VIS_WIDE_CSS


def _build_lineage_graph(start_fn: str, start_label: str, query_groups: list, run_query, max_depth: int = 2):
    """BFS multi-hop lineage using WITH RECURSIVE.

    Args:
        start_fn (str): The full name of the starting table entity.
        start_label (str): The label for the starting node.
        query_groups (list): A list of groups the user belongs to for permission filtering.
        run_query (Callable): A function to execute the SQL query.
        max_depth (int, optional): The maximum depth to traverse. Defaults to 2.

    Returns:
        tuple[list, list]: A tuple containing the list of graph nodes and the list of graph links.
    """
    graph_nodes = [{"id": start_fn, "label": start_label, "current": True, "relationship": "Current"}]
    graph_links: list = []

    lin_ph = ", ".join(f"%(lin_g_{i})s" for i in range(len(query_groups))) if query_groups else "''"

    params: dict = {"start_fn": start_fn, "max_depth": max_depth}
    for i, g in enumerate(query_groups):
        params[f"lin_g_{i}"] = g

    # The query uses a recursive CTE to traverse up to max_depth hops.
    # CRITICAL: The JOIN on permissions_cache occurs in BOTH the base case and the recursive step.
    # This enforces push-down RBAC at every hop, ensuring that unauthorized tables are never traversed
    # or revealed to the user, preventing indirect discovery.
    q = f"""
        WITH RECURSIVE lineage_tree AS (
            -- Base case: Immediate upstream/downstream neighbors of the target table.
            SELECT DISTINCT l.table_full_name, l.direction, l.entity_full_name, l.entity_type, 1 AS depth
            FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.lineage_cache l
            JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache p ON l.entity_full_name = p.table_full_name
            WHERE l.table_full_name = %(start_fn)s
            AND (p.principal IN ({lin_ph}) OR p.principal = 'SELECT_ALL_USERS')

            UNION ALL

            -- Recursive step: Neighbors of the tables found in the previous iteration.
            SELECT DISTINCT l.table_full_name, l.direction, l.entity_full_name, l.entity_type, t.depth + 1
            FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.lineage_cache l
            JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache p ON l.entity_full_name = p.table_full_name
            JOIN lineage_tree t ON l.table_full_name = t.entity_full_name
            WHERE t.depth < %(max_depth)s
            AND (p.principal IN ({lin_ph}) OR p.principal = 'SELECT_ALL_USERS')
        )
        SELECT DISTINCT table_full_name, direction, entity_full_name, entity_type, MIN(depth) AS depth
        FROM lineage_tree
        GROUP BY table_full_name, direction, entity_full_name, entity_type
        ORDER BY depth ASC
    """  # nosec B608

    result = run_query(q, params)

    visited: set = {start_fn}

    if result is not None and not result.empty and "direction" in result.columns and "table_full_name" in result.columns:
        # ⚡ Bolt: Replace slow itertuples() and getattr() with fast native dictionary iteration
        for lr in result.to_dict("records"):
            node_fn = str(lr.get("table_full_name", ""))
            efn = str(lr.get("entity_full_name", ""))
            direction = str(lr.get("direction", ""))
            link = {"from": efn, "to": node_fn} if direction == "UPSTREAM" else {"from": node_fn, "to": efn}
            if link not in graph_links:
                graph_links.append(link)

            # Reconstruct node states
            if efn not in visited:
                visited.add(efn)
                graph_nodes.append({"id": efn, "label": efn.split(".")[-1], "current": False, "relationship": direction.capitalize()})
            if node_fn not in visited:
                visited.add(node_fn)
                graph_nodes.append({"id": node_fn, "label": node_fn.split(".")[-1], "current": False, "relationship": "Unknown"})

    return graph_nodes, graph_links


def _lineage_vis_html(graph_nodes: list, graph_links: list, height: int = 350, container_id: str = "mynetwork", spring_length: int = 120) -> str:
    nodes_js = json.dumps(graph_nodes)
    edges_js = json.dumps(graph_links)
    return (
        f'<div id="{container_id}" style="width:100%;height:{height}px;background:#F2EDE1;border-radius:4px;'
        f'border:1px solid #C9C2B4;overflow:hidden;margin-top:16px;"></div>'
        f'<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>'
        f'<script>'
        f'var nodes=new vis.DataSet({nodes_js});'
        f'var edges=new vis.DataSet({edges_js});'
        f'var container=document.getElementById("{container_id}");'
        f'var options={{nodes:{{shape:"box",margin:10,font:{{size:14,face:"sans-serif"}},borderWidth:1,shadow:true,widthConstraint:{{maximum:180}}}},'
        f'edges:{{arrows:"to",color:"#C9C2B4",smooth:{{type:"cubicBezier",forceDirection:"horizontal"}}}},'
        f'physics:{{solver:"repulsion",repulsion:{{nodeDistance:180,centralGravity:0.2,springLength:{spring_length},springConstant:0.05,damping:0.09}},stabilization:{{iterations:100,updateInterval:20}}}},'
        f'interaction:{{hover:false,dragNodes:true,dragView:true,zoomView:true}}}}; '
        f'var upd=[];nodes.forEach(function(n){{'
        f'var bg=n.current?"#B8362A":(n.relationship==="Shared column"?"#DDE4EC":"#FAF7F0");'
        f'var bdr=n.current?"#8C271E":(n.relationship==="Shared column"?"#2B4A6B":"#C9C2B4");'
        f'var txt=n.current?"#FAF7F0":(n.relationship==="Shared column"?"#2B4A6B":"#14110C");'
        f'upd.push({{id:n.id,color:{{background:bg,border:bdr,highlight:{{background:bg,border:bdr}}}},font:{{color:txt}}}});}});'
        f'nodes.update(upd);'
        f'var net=new vis.Network(container,{{nodes:nodes,edges:edges}},options);'
        f'net.once("stabilizationIterationsDone",function(){{net.fit();}});'
        f'</script>'
    )


@st.dialog(t("detail.lineage_graph"), width="large")
def render_lineage_fullscreen(graph_nodes: list, graph_links: list, full_name: str):
    """Renders the lineage graph in a fullscreen dialog.

    Args:
        graph_nodes (list): The list of nodes in the graph.
        graph_links (list): The list of links/edges in the graph.
        full_name (str): The full name of the table being viewed.

    Returns:
        None
    """
    st.markdown(VIS_WIDE_CSS, unsafe_allow_html=True)
    st.markdown(f"**{full_name}** — {t('detail.lineage_graph_subtitle', table=full_name.split('.')[-1])}")
    _graph_h = 1800
    graph_html = _lineage_vis_html(graph_nodes, graph_links, height=_graph_h, container_id="mynetwork_full", spring_length=220)
    components.html(graph_html, height=_graph_h + 20, scrolling=False)
