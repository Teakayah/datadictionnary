import streamlit as st
import streamlit.components.v1 as components

st.write("Query param:", st.query_params)

components.html("""
<button onclick="
    window.parent.history.pushState(null, '', '?tab=search&expand=some_node');
    window.parent.dispatchEvent(new Event('popstate'));
">Click me</button>
""")
