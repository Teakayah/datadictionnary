import streamlit as st
import os

from databricks import sql

@st.cache_resource(ttl="2h")
def get_database_connection():
    conn = sql.connect(
        server_hostname=os.getenv("DATABRICKS_HOST"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_TOKEN"),
    )
    yield conn
    conn.close()

def run_query(query, params=None):
    conn = get_database_connection()
    with conn.cursor() as cursor:
        pass
