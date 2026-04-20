import sys
from unittest.mock import MagicMock
import streamlit as st
import os

os.environ["ENABLE_MOCK_AUTH"] = "true"

from streamlit.runtime.scriptrunner import add_script_run_ctx
import threading
add_script_run_ctx(threading.current_thread())

@st.cache_resource
def get_conn():
    conn = "connection_object"
    yield conn
    print("Closed!")

def main():
    print("returned from cache:", get_conn())

main()
