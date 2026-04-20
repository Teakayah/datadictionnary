from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py")
at.run()
print("hasattr get?", hasattr(at.session_state, "get"))
