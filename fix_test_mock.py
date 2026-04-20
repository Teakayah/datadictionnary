import sys
from unittest.mock import MagicMock

# We need to simulate the return value of get_database_connection
# If it's a generator, then the mocked connection object itself has to act like the value yielded
# Wait, st.cache_resource executes the generator and caches the *yielded* value.
# But in our tests, `st.cache_resource` is probably bypassed or mocked, so it might be returning the generator itself!

print(type((i for i in [1, 2, 3])))
