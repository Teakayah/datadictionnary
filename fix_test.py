import re

with open("tests/test_ui_discovery.py", "r") as f:
    content = f.read()

# Fix the test failures caused by our refactoring of labels to keys.
# e.g., at.button_group(key="discovery_active_tab").set_value([en_locale["personalization"]["tab_bookmarks"]])
# needs to be at.button_group(key="discovery_active_tab").set_value(["bookmarks"])

replacements = [
    (r'set_value\(\[en_locale\["personalization"\]\["tab_notable"\]\]\)', 'set_value(["notable"])'),
    (r'set_value\(\[en_locale\["personalization"\]\["tab_bookmarks"\]\]\)', 'set_value(["bookmarks"])'),
    (r'set_value\(\[en_locale\["personalization"\]\["tab_recent"\]\]\)', 'set_value(["recent"])'),
    (r'set_value\(\[en_locale\["personalization"\]\["tab_recommended"\]\]\)', 'set_value(["recommended"])'),
    (r'assert at.session_state\["discovery_active_tab"\] == en_locale\["personalization"\]\["tab_bookmarks"\]', 'assert at.session_state["discovery_active_tab"] == "bookmarks"'),
]

for old, new in replacements:
    content = re.sub(old, new, content)

with open("tests/test_ui_discovery.py", "w") as f:
    f.write(content)
