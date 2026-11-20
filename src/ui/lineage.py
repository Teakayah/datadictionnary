from __future__ import annotations
"""Lineage graph building and rendering components."""


import functools
import json
import re
import weakref
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from src.config import CATALOG_CACHE, SCHEMA_CACHE
from src.i18n import t
from src.ui.css import VIS_WIDE_CSS

_VIS_VENDOR_PATH = Path(__file__).resolve().parents[2] / "assets" / "vendor" / "vis-network.min.js"


@functools.lru_cache(maxsize=1)
def _load_vis_network_js() -> str:
    """Load the vendored vis-network UMD bundle for offline lineage rendering."""
    return _VIS_VENDOR_PATH.read_text(encoding="utf-8")


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
    nodes_js = json.dumps(graph_nodes).replace("</", "<\\/")
    edges_js = json.dumps(graph_links).replace("</", "<\\/")
    """Generate the HTML payload to render a vis.js network graph.

    WHY IT EXISTS:
    Streamlit lacks a native network graph component. This function bridges that gap by
    injecting the raw vis.js library and a configuration script directly into an HTML
    iframe via `components.html()`. It maps Python node/edge dictionaries into JavaScript
    DataSets to render the interactive lineage visualization on the client side.

    Args:
        graph_nodes (list): A list of dictionaries representing the graph nodes (must contain 'id' and 'label').
        graph_links (list): A list of dictionaries representing the directed edges (must contain 'from' and 'to').
        height (int, optional): The pixel height of the rendered iframe container. Defaults to 350.
        container_id (str, optional): The DOM ID for the vis.js injection target. Defaults to "mynetwork".
        spring_length (int, optional): The physics configuration for edge length. Defaults to 120.

    Returns:
        str: A complete HTML snippet containing the container `div`, the vis.js library script tag,
             and the initialization script to render the graph.
    """
    min_scale = 0.8 if height < 600 else 0.75
    vis_js = re.sub(r"</script", r"<\\/script", _load_vis_network_js(), flags=re.IGNORECASE)
    return (
        f'<div id="{container_id}" style="width:100%;height:{height}px;background:#F2EDE1;border-radius:4px;'
        f'border:1px solid #C9C2B4;overflow:hidden;margin-top:16px;"></div>'
        f'<script>{vis_js}</script>'
        f'<script>'
        f'var nodes=new vis.DataSet({nodes_js});'
        f'var edges=new vis.DataSet({edges_js});'
        f'var container=document.getElementById("{container_id}");'
        f'var options={{nodes:{{shape:"box",margin:10,font:{{size:14,face:"sans-serif"}},borderWidth:1,shadow:true,widthConstraint:{{maximum:220}}}},'
        f'edges:{{arrows:"to",color:"#C9C2B4",smooth:{{type:"cubicBezier",forceDirection:"horizontal"}}}},'
        f'physics:{{solver:"barnesHut",barnesHut:{{gravitationalConstant:-3500,centralGravity:0.35,springLength:{spring_length},springConstant:0.04,damping:0.09,avoidOverlap:0.85}},stabilization:{{iterations:120,updateInterval:20}}}},'
        f'interaction:{{hover:false,dragNodes:true,dragView:true,zoomView:true}}}}; '
        f'var upd=[];nodes.forEach(function(n){{'
        f'var bg=n.current?"#B8362A":(n.relationship==="Shared column"?"#DDE4EC":"#FAF7F0");'
        f'var bdr=n.current?"#8C271E":(n.relationship==="Shared column"?"#2B4A6B":"#C9C2B4");'
        f'var txt=n.current?"#FAF7F0":(n.relationship==="Shared column"?"#2B4A6B":"#14110C");'
        f'upd.push({{id:n.id,color:{{background:bg,border:bdr,highlight:{{background:bg,border:bdr}}}},font:{{color:txt}}}});}});'
        f'nodes.update(upd);'
        f'var net=new vis.Network(container,{{nodes:nodes,edges:edges}},options);'
        f'net.once("stabilizationIterationsDone",function(){{'
        f'net.fit({{animation:false}});'
        f'var sc=net.getScale();'
        f'if(sc<{min_scale}){{'
        f'var cur=nodes.get({{filter:function(n){{return n.current;}}}});'
        f'var pos=cur.length?net.getPositions([cur[0].id])[cur[0].id]:net.getViewPosition();'
        f'net.moveTo({{position:pos||net.getViewPosition(),scale:{min_scale}}});'
        f'}}else if(sc>1.15){{'
        f'net.moveTo({{position:net.getViewPosition(),scale:1.15}});'
        f'}}}});'
        f'net.on("doubleClick",function(params){{'
        f'if(!params.nodes||params.nodes.length!==1)return;'
        f'var nid=params.nodes[0];'
        f'var nobj=nodes.get(nid);'
        f'if(!nobj||nobj.current)return;'
        f'var hex=Array.from(new TextEncoder().encode(String(nid))).map(function(b){{return b.toString(16).padStart(2,"0");}}).join("");'
        f'var lbl="LINNAV-"+hex;'
        f'var btns=Array.from(window.parent.document.querySelectorAll("button"));'
        f'var btn=btns.find(function(b){{return b.textContent.trim()===lbl;}});'
        f'if(btn)btn.click();'
        f'}});'
        f'</script>'
    )


_LINEAGE_V2_JS = """
export default function(component) {
    const { data, parentElement, setTriggerValue } = component;
    const cfg = data || {};
    const h = Number(cfg.height || 350);
    const minScale = Number(cfg.minScale || 0.8);
    const springLength = Number(cfg.springLength || 120);

    parentElement.innerHTML = "";
    const box = document.createElement("div");
    box.className = "dd-lineage-box";
    box.style.cssText =
        "width:100%;height:" + h + "px;background:#F2EDE1;border-radius:4px;" +
        "border:1px solid #C9C2B4;overflow:hidden;margin-top:16px;position:relative;";
    parentElement.appendChild(box);

    let net = null;
    let destroyed = false;

    function loadVis() {
        if (window.vis && window.vis.Network) {
            return Promise.resolve(window.vis);
        }
        if (typeof __DD_VIS_SRC__ !== "string" || !__DD_VIS_SRC__) {
            return Promise.reject(new Error("vendored vis-network source missing"));
        }
        const existing = document.querySelector('script[data-dd-vis="1"]');
        if (!existing) {
            const s = document.createElement("script");
            s.dataset.ddVis = "1";
            s.textContent = __DD_VIS_SRC__;
            document.head.appendChild(s);
            s.dataset.ddLoaded = "1";
        }
        return window.vis && window.vis.Network
            ? Promise.resolve(window.vis)
            : Promise.reject(new Error("vis load failed"));
    }

    loadVis().then((vis) => {
        if (destroyed || !vis || !vis.Network) return;
        const nodes = new vis.DataSet(cfg.nodes || []);
        const edges = new vis.DataSet(cfg.links || []);
        const upd = [];
        nodes.forEach((n) => {
            const bg = n.current ? "#B8362A" : (n.relationship === "Shared column" ? "#DDE4EC" : "#FAF7F0");
            const bdr = n.current ? "#8C271E" : (n.relationship === "Shared column" ? "#2B4A6B" : "#C9C2B4");
            const txt = n.current ? "#FAF7F0" : (n.relationship === "Shared column" ? "#2B4A6B" : "#14110C");
            upd.push({
                id: n.id,
                color: { background: bg, border: bdr, highlight: { background: bg, border: bdr } },
                font: { color: txt },
            });
        });
        nodes.update(upd);

        const options = {
            nodes: {
                shape: "box",
                margin: 10,
                font: { size: 14, face: "sans-serif" },
                borderWidth: 1,
                shadow: true,
                widthConstraint: { maximum: 220 },
            },
            edges: {
                arrows: "to",
                color: "#C9C2B4",
                smooth: { type: "cubicBezier", forceDirection: "horizontal" },
            },
            physics: {
                solver: "barnesHut",
                barnesHut: {
                    gravitationalConstant: -3500,
                    centralGravity: 0.35,
                    springLength: springLength,
                    springConstant: 0.04,
                    damping: 0.09,
                    avoidOverlap: 0.85,
                },
                stabilization: { iterations: 120, updateInterval: 20 },
            },
            interaction: { hover: true, dragNodes: true, dragView: true, zoomView: true },
        };

        net = new vis.Network(box, { nodes, edges }, options);
        box._ddNet = net;

        net.once("stabilizationIterationsDone", () => {
            if (destroyed || !net) return;
            net.fit({ animation: false });
            const sc = net.getScale();
            if (sc < minScale) {
                const cur = nodes.get({ filter: (n) => n.current });
                const pos = cur.length ? net.getPositions([cur[0].id])[cur[0].id] : net.getViewPosition();
                net.moveTo({ position: pos || net.getViewPosition(), scale: minScale });
            } else if (sc > 1.15) {
                net.moveTo({ position: net.getViewPosition(), scale: 1.15 });
            }
        });

        net.on("hoverNode", (params) => {
            const nobj = nodes.get(params.node);
            box.style.cursor = nobj && !nobj.current ? "pointer" : "grab";
        });
        net.on("blurNode", () => {
            box.style.cursor = "grab";
        });

        let lastNavAt = 0;
        function navigateNode(nid) {
            if (!nid) return;
            const nobj = nodes.get(nid);
            if (!nobj || nobj.current) return;
            const now = Date.now();
            if (now - lastNavAt < 500) return;
            lastNavAt = now;
            setTriggerValue("nav", String(nid));
        }

        net.on("doubleClick", (params) => {
            if (!params.nodes || params.nodes.length !== 1) return;
            navigateNode(params.nodes[0]);
        });

        box.addEventListener("dblclick", (e) => {
            if (destroyed || !net) return;
            const canvas = box.querySelector("canvas");
            if (!canvas) return;
            const rect = canvas.getBoundingClientRect();
            const nid = net.getNodeAt({ x: e.clientX - rect.left, y: e.clientY - rect.top });
            navigateNode(nid);
        });

        requestAnimationFrame(() => {
            if (net && !destroyed) net.redraw();
        });
    }).catch(() => {});

    return () => {
        destroyed = true;
        if (net) {
            net.destroy();
            net = null;
        }
    };
}
"""


_LINEAGE_COMPONENT_CACHE: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _build_lineage_v2_js() -> str:
    """Return the v2 component module JS with the vendored vis-network bundle inlined."""
    vis_src_js = json.dumps(_load_vis_network_js()).replace("</", "<\\/")
    return f"const __DD_VIS_SRC__ = {vis_src_js};\n{_LINEAGE_V2_JS}"


def _get_lineage_component():
    """Return the v2 lineage component registered on the active Streamlit runtime."""
    if not (hasattr(st, "components") and hasattr(st.components, "v2")):
        return None
    mgr = st.components.v2.get_bidi_component_manager()
    comp = _LINEAGE_COMPONENT_CACHE.get(mgr)
    if comp is None:
        comp = st.components.v2.component(
            "dd_lineage_vis",
            js=_build_lineage_v2_js(),
            isolate_styles=False,
        )
        _LINEAGE_COMPONENT_CACHE[mgr] = comp
    return comp


def _trigger_lineage_navigation(target_fn: str | None, current_fn: str) -> None:
    """Navigate the Search page to ``target_fn`` when a non-current node is double-clicked."""
    if not target_fn or target_fn == current_fn:
        return
    st.session_state["dd_search_override"] = str(target_fn).split(".")[-1]
    st.session_state["dd_nav_select"] = str(target_fn)
    st.rerun()


def render_lineage_graph(
    graph_nodes: list,
    graph_links: list,
    *,
    height: int = 350,
    spring_length: int = 120,
    key: str = "dd_lineage_vis",
) -> str | None:
    """Render the interactive vis-network lineage graph and return any double-clicked node ID."""
    min_scale = 0.8 if height < 600 else 0.75
    comp = _get_lineage_component()
    if comp is not None:
        res = comp(
            data={
                "nodes": graph_nodes,
                "links": graph_links,
                "height": height,
                "minScale": min_scale,
                "springLength": spring_length,
            },
            key=key,
            on_nav_change=lambda: None,
        )
        nav = getattr(res, "nav", None)
        return str(nav) if nav else None

    components.html(
        _lineage_vis_html(graph_nodes, graph_links, height=height, spring_length=spring_length),
        height=height + 30,
    )
    return None


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
    _graph_h = 700
    _nav_target = render_lineage_graph(
        graph_nodes,
        graph_links,
        height=_graph_h,
        spring_length=180,
        key=f"lin_vis_full_{full_name}",
    )
    _trigger_lineage_navigation(_nav_target, full_name)
