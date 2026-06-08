import re

with open("src/ui/cards/discovery.py", "r") as f:
    content = f.read()

# Fix the format_func to handle empty list gracefully
content = content.replace(
    'format_func=lambda x: _disc_tab_labels[x[0]] if isinstance(x, list) else _disc_tab_labels[x],',
    'format_func=lambda x: _disc_tab_labels[x[0]] if isinstance(x, list) and len(x) > 0 else _disc_tab_labels.get(x, "") if not isinstance(x, list) else "",'
)

with open("src/ui/cards/discovery.py", "w") as f:
    f.write(content)
