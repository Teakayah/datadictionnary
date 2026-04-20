import sys
import streamlit as st

@st.cache_resource
def get_conn():
    conn = "connection_object"
    yield conn
    print("Closed!")

def main():
    print("returned from cache:", get_conn())

main()
