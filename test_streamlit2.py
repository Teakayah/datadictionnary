from streamlit.testing.v1 import AppTest
import app

def test_cache_yield():
    at = AppTest.from_file("app.py")
    at.run()
    print("exception:", at.exception)

test_cache_yield()
