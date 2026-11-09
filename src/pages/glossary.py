"""Glossary page renderer."""
from __future__ import annotations


import html as _html
import json

import streamlit as st
import streamlit.components.v1 as components

from src.db.queries import get_authorized_table_names
from src.demo.data import _DEMO_GLOSSARY
from src.i18n import t
from src.personalization import _pref_upsert, _pref_delete, get_bookmarks



def _render_hero_and_help() -> None:
    """Renders the hero section and help expander."""
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("glossary.title")}</div>
      <h1>{t("glossary.hero_title")}</h1>
      <p class="lead">{t("glossary.subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    with st.expander(t("help.glossary_expander")):
        st.markdown(t("help.glossary_content"))

def _render_term_details(term_row, _authorized_fns: set) -> None:
    """Renders the detailed definition and linked tables for a term."""
    st.markdown(f'''
    <div class="dd-detail-header" style="margin-top: 0;">
      <span class="dd-eyebrow" style="margin-bottom:0">{t("glossary.term_details")}</span>
    </div>
    <div class="dd-detail-table-name">{_html.escape(str(term_row["term"]))}</div>
    <div style="font-family:var(--font-sans); font-size:14px; font-weight:600; color:var(--ink-40); margin-bottom:8px; text-transform:uppercase; letter-spacing:0.05em;">{t("glossary.definition")}</div>
    <p class="dd-detail-desc" style="font-size:18px;">{_html.escape(str(term_row["definition"]))}</p>

    <div style="font-family:var(--font-sans); font-size:14px; font-weight:600; color:var(--ink-40); margin-top:24px; margin-bottom:8px; text-transform:uppercase; letter-spacing:0.05em;">{t("glossary.logic_calculation")}</div>
    <div style="background:var(--paper-deep); padding:16px; border-radius:2px; font-family:var(--font-mono); font-size:14px; color:var(--ink); border-left:3px solid var(--accent); line-height:1.5;">
      {_html.escape(str(term_row["calculation"]))}
    </div>

    <div style="font-family:var(--font-sans); font-size:14px; font-weight:600; color:var(--ink-40); margin-top:32px; margin-bottom:12px; text-transform:uppercase; letter-spacing:0.05em;">{t("glossary.linked_tables")}</div>
    ''', unsafe_allow_html=True)

    for table_fn in term_row["related_tables"]:
        if table_fn not in _authorized_fns:
            continue  # hide tables the current user cannot access
        _gloss_bk = table_fn in get_bookmarks()
        _c_tbl, _c_star = st.columns([11, 1], gap="small")
        with _c_tbl:
            if st.button(t("discovery.explore_button", name=table_fn.split('.')[-1]), key=f"gloss_link_{table_fn}", help=t("search.view_details_help"), use_container_width=True, type="secondary"):
                st.query_params["tab"] = "search"
                st.session_state["dd_search_override"] = table_fn.split(".")[-1]
                st.session_state["dd_nav_select"] = table_fn
                st.rerun()
        with _c_star:
            if st.button("★" if _gloss_bk else "☆", key=f"gloss_bk_{table_fn}", help=t("personalization.remove_bookmark") if _gloss_bk else t("personalization.add_bookmark"), use_container_width=True):
                if _gloss_bk:
                    get_bookmarks().discard(table_fn)
                    _pref_delete(table_fn, "bookmark")
                    st.toast(t("personalization.bookmark_removed"))
                else:
                    get_bookmarks().add(table_fn)
                    _pref_upsert(table_fn, "bookmark")
                    st.toast(t("personalization.bookmark_added"))
                st.rerun()

def _render_stewardship(term_row) -> None:
    """Renders the stewardship information for a term."""
    st.markdown(f'''
    <div class="dd-section-header">
      <span class="dd-eyebrow" style="margin-bottom:0">{t("glossary.stewardship")}</span>
    </div>
    <div style="margin-top:16px;">
      <div style="font-family:var(--font-sans); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em;">{t("glossary.business_domain")}</div>
      <div style="font-family:var(--font-sans); font-size:16px; font-weight:600; color:var(--ink); margin-top:4px;">{_html.escape(str(term_row["domain"]))}</div>
    </div>
    <div style="margin-top:20px;">
      <div style="font-family:var(--font-sans); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em;">{t("glossary.data_steward")}</div>
      <div style="font-family:var(--font-sans); font-size:16px; font-weight:600; color:var(--ink); margin-top:4px;">{_html.escape(str(term_row["steward"]))}</div>
    </div>
    ''', unsafe_allow_html=True)

def _render_concept_map(selected_term: str, term_row) -> None:
    """Renders the interactive concept map for a term and its linked tables."""
    st.markdown(f'''
    <div class="dd-section-header" style="margin-top:32px;">
      <span class="dd-eyebrow" style="margin-bottom:0">{t("glossary.concept_map")}</span>
    </div>
    ''', unsafe_allow_html=True)

    graph_nodes = [{"id": "TERM", "label": selected_term, "current": True, "relationship": "Current"}]
    graph_links = []
    for table_fn in term_row["related_tables"]:
        t_label = table_fn.split(".")[-1]
        graph_nodes.append({"id": table_fn, "label": t_label, "current": False, "relationship": "Table"})
        graph_links.append({"from": "TERM", "to": table_fn})

    graph_html = (
        f'<div id="mynetwork_glossary" style="width: 100%; height: 300px; background: #F2EDE1; '
        f'border-radius: 4px; border: 1px solid #C9C2B4; overflow: hidden; margin-top: 16px;"></div>'
        f'<script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>'
        f'<script type="text/javascript">'
        f'var nodes = new vis.DataSet({json.dumps(graph_nodes)}); '
        f'var edges = new vis.DataSet({json.dumps(graph_links)}); '
        f'var container = document.getElementById("mynetwork_glossary"); '
        f'var data = {{ nodes: nodes, edges: edges }}; '
        f'var options = {{ '
        f'  nodes: {{ shape: "box", margin: 10, font: {{ size: 14, face: "sans-serif" }}, borderWidth: 1, shadow: true, widthConstraint: {{ maximum: 160 }} }}, '
        f'  edges: {{ arrows: "to", color: "#C9C2B4", smooth: {{ type: "cubicBezier", forceDirection: "horizontal" }} }}, '
        f'  physics: {{ solver: "repulsion", repulsion: {{ nodeDistance: 160, centralGravity: 0.2, springLength: 120, springConstant: 0.05, damping: 0.09 }}, stabilization: {{ iterations: 50 }} }}, '
        f'  interaction: {{ hover: false, dragNodes: true, dragView: true, zoomView: true }} '
        f'}}; '
        f'var updatedNodes = []; '
        f'nodes.forEach(function(node) {{ '
        f'var bg = node.current ? "#B8362A" : "#FAF7F0"; '
        f'var border = node.current ? "#8C271E" : "#C9C2B4"; '
        f'var text = node.current ? "#FAF7F0" : "#14110C"; '
        f'updatedNodes.push({{ id: node.id, color: {{ background: bg, border: border, highlight: {{ background: bg, border: border }} }}, font: {{ color: text }} }}); '
        f'}}); '
        f'nodes.update(updatedNodes); '
        f'var network = new vis.Network(container, data, options); '
        f'network.once("stabilizationIterationsDone", function() {{ network.fit(); }});'
        f'</script>'
    )
    components.html(graph_html, height=330)

def render_glossary(query_groups) -> None:
    # ⚡ Bolt: Cache authorized table metadata locally and ensure it executes exactly once before the rendering loop
    _authorized_fns = get_authorized_table_names(tuple(query_groups or []))

    _render_hero_and_help()

    # Term Selection (Autocomplete)
    all_terms = _DEMO_GLOSSARY["term"].to_numpy().tolist()
    selected_term = st.selectbox(
        t("glossary.search_placeholder"),
        options=all_terms,
        index=None,
        placeholder=t("glossary.search_placeholder"),
        label_visibility="collapsed",
        key="glossary_search",
        help=t("glossary.search_placeholder"),
    )

    if selected_term:
        # ⚡ Bolt: Use .to_numpy() to skip index alignment overhead
        term_row = _DEMO_GLOSSARY[_DEMO_GLOSSARY["term"].to_numpy() == selected_term].iloc[0]

        col_main, col_side = st.columns([7, 5], gap="large")

        with col_main:
            _render_term_details(term_row, _authorized_fns)

        with col_side:
            _render_stewardship(term_row)
            _render_concept_map(selected_term, term_row)
