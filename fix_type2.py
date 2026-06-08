import re

with open("src/ui/cards/discovery.py", "r") as f:
    content = f.read()

# Fix the format_func to handle both str and list cases since Streamlit
# element tree seems to pass it a list during testing sometimes
content = content.replace(
    'format_func=lambda x: _disc_tab_labels[x],',
    'format_func=lambda x: _disc_tab_labels[x[0]] if isinstance(x, list) else _disc_tab_labels[x],'
)

with open("src/ui/cards/discovery.py", "w") as f:
    f.write(content)
