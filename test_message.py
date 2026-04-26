import streamlit as st
import streamlit.components.v1 as components

query = st.query_params
st.write("Query param:", query)

components.html("""
<script>
setTimeout(() => {
    window.parent.postMessage({
        type: "streamlit:setQueryParams",
        queryParams: { expand: "new_node_123" }
    }, "*");
}, 2000);
</script>
<p>Sending message in 2s...</p>
""")
