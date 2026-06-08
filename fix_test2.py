import re

with open("tests/test_ui_discovery.py", "r") as f:
    content = f.read()

# _disc_tab_idx is no longer used since we decoupled the tab IDs from localized labels
content = re.sub(r'        at\.session_state\["_disc_tab_idx"\] = 1\n        at\.run\(\)\n\n        assert at\.session_state\["discovery_active_tab"\] == "bookmarks"', '        at.run()\n        assert at.session_state["discovery_active_tab"] == "notable"', content)

with open("tests/test_ui_discovery.py", "w") as f:
    f.write(content)
