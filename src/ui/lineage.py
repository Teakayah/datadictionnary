"""Lineage graph building and rendering components."""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from src.config import CATALOG_CACHE, SCHEMA_CACHE
from src.i18n import t
from src.ui.css import VIS_WIDE_CSS


def _viewport_height(fallback: int = 800) -> int:
    """Return the user's viewport height in px, falling back if not yet captured."""
    return int(st.session_state.get("viewport_height", fallback))


def _fetch_lineage_hop(node_fn: str, query_groups: list, run_query) -> "pd.DataFrame | None":
    """Fetch direct lineage neighbors of node_fn, permission-filtered."""
    lin_ph = ", ".join([f"%(lin_g_{i})s" for i in range(len(query_groups))]) if query_groups else "''"
    params: dict = {"table_full_name": node_fn}
    for i, g in enumerate(query_groups):
        params[f"lin_g_{i}"] = g
    q = (
        "SELECT DISTINCT l.direction, l.entity_full_name, l.entity_type "
        "FROM {0}.{1}.lineage_cache l "
        "JOIN {0}.{1}.permissions_cache p ON l.entity_full_name = p.table_full_name "
        "WHERE l.table_full_name = %(table_full_name)s "
        "AND (p.principal IN ({2}) OR p.principal = 'SELECT_ALL_USERS') "
        "ORDER BY l.direction, l.entity_full_name"
    ).format(CATALOG_CACHE, SCHEMA_CACHE, lin_ph)  # nosec B608
    return run_query(q, params)


def _build_lineage_graph(start_fn: str, start_label: str, query_groups: list, run_query, max_depth: int = 2):
    """BFS multi-hop lineage. Returns (graph_nodes, graph_links)."""
    graph_nodes = [{"id": start_fn, "label": start_label, "current": True, "relationship": "Current"}]
    graph_links: list = []
    visited: set = {start_fn}
    frontier = [start_fn]

    for _ in range(max_depth):
        if not frontier:
            break
        next_frontier: list = []
        for node_fn in frontier:
            result = _fetch_lineage_hop(node_fn, query_groups, run_query)
            if result is None or result.empty or "direction" not in result.columns:
                continue
            for lr in result.itertuples(index=False):
                efn = str(getattr(lr, "entity_full_name", ""))
                direction = str(getattr(lr, "direction", ""))
                link = {"from": efn, "to": node_fn} if direction == "UPSTREAM" else {"from": node_fn, "to": efn}
                if link not in graph_links:
                    graph_links.append(link)
                if efn not in visited:
                    visited.add(efn)
                    next_frontier.append(efn)
                    graph_nodes.append({"id": efn, "label": efn.split(".")[-1], "current": False, "relationship": direction.capitalize()})
        frontier = next_frontier

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
        f'var options={{nodes:{{shape:"box",margin:10,font:{{size:14,face:"sans-serif"}},borderWidth:1,shadow:true}},'
        f'edges:{{arrows:"to",color:"#C9C2B4",smooth:{{type:"cubicBezier",forceDirection:"horizontal"}}}},'
        f'physics:{{barnesHut:{{springLength:{spring_length},springConstant:0.04}},minVelocity:0.75}},'
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
    st.markdown(VIS_WIDE_CSS, unsafe_allow_html=True)
    st.markdown(f"**{full_name}** — {t('detail.lineage_graph_subtitle').format(table=full_name.split('.')[-1])}")
    _graph_h = 1800
    graph_html = _lineage_vis_html(graph_nodes, graph_links, height=_graph_h, container_id="mynetwork_full", spring_length=220)
    components.html(graph_html, height=_graph_h + 20, scrolling=False)
