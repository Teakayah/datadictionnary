import streamlit as st
import streamlit.components.v1 as components

st.write("Query params:", st.query_params)

components.html("""
<a href="?tab=search&expand=some_node" target="_parent">Click me to expand</a>
""")
