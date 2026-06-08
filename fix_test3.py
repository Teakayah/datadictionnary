import re

with open("tests/test_ui_discovery.py", "r") as f:
    content = f.read()

content = content.replace(
    'assert any(en_locale["personalization"]["tab_bookmarks"] in val for val in html)',
    'assert any("My Bookmarks" in val for val in html)'
)

with open("tests/test_ui_discovery.py", "w") as f:
    f.write(content)
