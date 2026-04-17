import streamlit as st
import pandas as pd
from databricks import sql
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page Configuration
st.set_page_config(
    page_title="Business Data Dictionary",
    page_icon="📖",
    layout="wide"
)

# --- Authentication ---
def check_auth():
    # Placeholder for Entra ID authentication logic
    # In a real app, we would use msal to check for a valid session
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        st.title("Welcome to the Data Dictionary")
        st.write("Please sign in with your corporate account to access the catalog.")
        if st.button("Sign In with Entra ID"):
            # Mocking successful login for scaffolding
            st.session_state.authenticated = True
            st.session_state.user_groups = ["finance_all", "marketing_read"] # Mock groups
            st.rerun()
        st.stop()

check_auth()

# --- App Content ---
st.sidebar.title("Data Dictionary")
st.sidebar.info(f"Logged in as User (Groups: {', '.join(st.session_state.user_groups)})")

if st.sidebar.button("Logout"):
    st.session_state.authenticated = False
    st.rerun()

st.title("🔍 Data Dictionary Search")
st.markdown("Find and understand the data available in our Unity Catalog.")

# Search bar
search_query = st.text_input("Search for tables, columns, or business terms...", placeholder="e.g., customer_lifetime_value")

if search_query:
    st.subheader(f"Results for '{search_query}'")
    
    # Placeholder for Databricks SQL Warehouse query
    # In Phase 3, we will replace this with a real filtered query
    st.info("Querying Databricks SQL Warehouse... (Filtered by your permissions)")
    
    # Mock results
    mock_data = pd.DataFrame([
        {"Table": "dim_customers", "Catalog": "main", "Schema": "sales", "Description": "Consolidated customer profile data."},
        {"Table": "fct_orders", "Catalog": "main", "Schema": "sales", "Description": "Granular order transaction records."},
    ])
    st.dataframe(mock_data, use_container_width=True)
else:
    st.write("Start typing above to search for metadata.")

# --- Future Phase Components ---
with st.expander("About this Catalog"):
    st.write("""
    This data dictionary is powered by Databricks Unity Catalog. 
    It is automatically filtered to show only the data you are authorized to see.
    - **Structural Metadata:** Catalogs, Schemas, Tables.
    - **Business Context:** Descriptions and tags.
    - **Freshness:** Synced nightly from Unity Catalog.
    """)
