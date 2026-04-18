import streamlit as st
from databricks import sql
import os
import msal
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_URI = os.getenv("REDIRECT_URI")
SCOPE = ["User.Read", "GroupMember.Read.All"] # Adjust scopes as needed

# Databricks Config
CATALOG_CACHE = "data_governance"
SCHEMA_CACHE = "dictionary_cache"

# Page Configuration
st.set_page_config(
    page_title="Business Data Dictionary",
    page_icon="📖",
    layout="wide"
)

# --- Authentication Helpers ---
def get_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )

def check_auth():
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = None
    
    if st.session_state.auth_token is None:
        msal_app = get_msal_app()
        auth_url = msal_app.get_authorization_request_url(SCOPE, redirect_uri=REDIRECT_URI)
        
        st.title("Welcome to the Data Dictionary")
        st.write("Please sign in with your corporate account to access the catalog.")
        
        # In a real Streamlit app, you would handle the redirect back
        # This is a simplified representation of the flow
        st.markdown(f'[Sign In with Entra ID]({auth_url})')
        
        # Check for code in URL (simplified for scaffolding)
        query_params = st.query_params
        if "code" in query_params:
            result = msal_app.acquire_token_by_authorization_code(
                query_params["code"], scopes=SCOPE, redirect_uri=REDIRECT_URI
            )
            if "access_token" in result:
                st.session_state.auth_token = result
                # Extract groups from claims (requires 'groups' claim configured in Entra ID)
                st.session_state.user_groups = result.get("id_token_claims", {}).get("groups", [])
                st.session_state.user_name = result.get("id_token_claims", {}).get("name")
                st.rerun()
        st.stop()

# For local development/scaffolding without a real redirect loop
# We'll use a "Mock Auth" toggle ONLY if explicitly enabled via environment variable
# AND we are explicitly in a development environment to prevent accidental activation in production
_mock_auth_flag = os.getenv("ENABLE_MOCK_AUTH", "false").lower() == "true"
_is_dev_env = os.getenv("ENVIRONMENT", "production").lower() == "development"
ENABLE_MOCK_AUTH = _mock_auth_flag and _is_dev_env

if ENABLE_MOCK_AUTH:
    st.warning("⚠️ Mock Authentication is ENABLED.")
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        if st.button("Mock Login (Finance Group)"):
            st.session_state.authenticated = True
            st.session_state.user_groups = ["finance_dept_id", "all_employees_id"]
            st.session_state.user_name = "Finance User"
            st.rerun()
        st.stop()
else:
    check_auth()

# --- Databricks Query Helper ---
@st.cache_data(ttl="1h")
def run_query(query, params=None):
    with sql.connect(
        server_hostname=os.getenv("DATABRICKS_HOST"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_TOKEN")
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall_as_pandas()

# --- App Content ---
st.sidebar.title("Data Dictionary")
st.sidebar.info(f"Logged in as: {st.session_state.user_name}")

if st.sidebar.button("Logout"):
    st.session_state.clear()
    st.rerun()

st.title("🔍 Data Dictionary Search")
st.markdown("Find data authorized for your team.")

# Search bar
search_query = st.text_input("Search for tables or business terms...", placeholder="e.g., customer")

if search_query:
    st.subheader(f"Results for '{search_query}'")
    
    # PERMISSION FILTERING LOGIC
    # We join the metadata with the permissions cache and filter by the user's AD groups
    # Note: We also include 'ANY FILE' or public groups if applicable
    sql_query = f"""
        SELECT DISTINCT 
            m.catalog_name, 
            m.schema_name, 
            m.table_name, 
            m.comment as table_description,
            m.table_type
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata m
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache p 
          ON m.full_name = p.table_full_name
        WHERE (m.full_name LIKE %(search)s OR m.comment LIKE %(search)s)
          AND (p.principal IN %(groups)s OR p.principal = 'SELECT_ALL_USERS')
    """
    
    # Ensure groups is a tuple for the SQL IN clause
    groups = tuple(st.session_state.user_groups) if st.session_state.user_groups else ('none',)
    
    try:
        results = run_query(sql_query, {"search": f"%{search_query}%", "groups": groups})
        
        if not results.empty:
            st.dataframe(results, use_container_width=True)
            
            # Allow clicking on a table to see columns
            selected_table = st.selectbox("Select a table to view details:", results['table_name'])
            if selected_table:
                # Find the full name for the selected table
                row = results[results['table_name'] == selected_table].iloc[0]
                full_name = f"{row['catalog_name']}.{row['schema_name']}.{row['table_name']}"
                
                st.write(f"### Columns for `{full_name}`")
                cols_query = f"SELECT column_name, data_type, comment FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata WHERE table_full_name = %s"
                cols = run_query(cols_query, (full_name,))
                st.table(cols)
        else:
            st.warning("No authorized results found matching your search.")
    except Exception as e:
        st.error(f"Error querying data: {e}")
        st.info("Ensure the sync job has been run and environment variables are correct.")

else:
    st.write("Start typing to search the dictionary.")
