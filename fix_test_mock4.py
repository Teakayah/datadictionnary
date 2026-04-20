import pytest
from unittest.mock import MagicMock

# In Streamlit, when you use yield inside @st.cache_resource, Streamlit runs the generator
# to get the yielded value, caches it, and returns the VALUE (not the generator).
# However, in our tests, `st.cache_data` and `st.cache_resource` are cleared using `st.cache_data.clear()`, but we don't clear `st.cache_resource`? Wait, they don't use real Streamlit, they use a mock? No, conftest.py uses the real Streamlit `cache_data.clear()`. But Streamlit executes the generator and caches the yield.
# Wait, why did we get "generator object has no attribute 'cursor'" in the tests?
# Because `get_database_connection()` returned a generator in the test.
# Why? Because in "test mode", Streamlit might not be active, but earlier my script printed `generator object` because my dummy script didn't set up the Streamlit app fully.
# Actually, the exception we got in `pytest tests/` was:
# AttributeError: 'generator' object has no attribute 'cursor'
