import sys
from streamlit.testing.v1 import AppTest

def test_truncation():
    at = AppTest.from_string("""
import streamlit as st
inp = st.text_input("test", max_chars=255)
st.write(len(inp))
""")
    at.run()
    at.text_input[0].set_value("A" * 256).run()
    print("Value length:", len(at.text_input[0].value))

test_truncation()
