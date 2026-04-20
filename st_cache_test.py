import sys
import unittest.mock as mock

class st:
    def cache_resource(*args, **kwargs):
        def wrapper(func):
            return func
        return wrapper

@st.cache_resource()
def get_db():
    yield 'conn'

print(get_db())
