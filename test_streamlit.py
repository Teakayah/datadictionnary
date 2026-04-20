from streamlit.testing.v1 import AppTest

def test_cache_yield():
    at = AppTest.from_file("run_benchmark6.py")
    at.run()
    print("logs:", at.log)
    print("exception:", at.exception)

test_cache_yield()
