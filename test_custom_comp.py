import streamlit as st
import streamlit.components.v1 as components

vis_network = components.declare_component("vis_network", path="project_utility/vis_network")

st.write("Graph:")
node_id = vis_network(
    nodes=[{"id": 1, "label": "Node 1"}, {"id": 2, "label": "Node 2"}],
    edges=[{"from": 1, "to": 2}],
    options={"physics": {"barnesHut": {"springLength": 100}}},
    key="graph"
)

st.write("Selected Node:", node_id)
