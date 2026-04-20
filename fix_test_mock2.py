from unittest.mock import MagicMock
import pytest

# How does Streamlit cache_resource handle mocks when the user changes it to a generator?
# The problem is that when Streamlit runs the generator in test mode, the return value of `sql.connect`
# is a MagicMock. A yield returns that MagicMock.
# Oh wait, `st.cache_resource` when caching a generator doesn't just return the generator... wait!
# If it's returning a generator when we call get_database_connection(), it means the caching framework isn't handling the generator unwrapping!
# Let's check streamlit docs or caching source.
