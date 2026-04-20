import streamlit as st

@st.cache_resource
def get_db():
    conn = "connection"
    yield conn
    print("teardown")

print("first:", get_db())
print("second:", get_db())
