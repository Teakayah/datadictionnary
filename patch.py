import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    new_lines = []

    in_markdown_block = False
    block_lines = []

    for line in lines:
        block_lines.append(line)
        if 'st.markdown(' in line or "components.html(" in line or 'st.write(' in line:
            in_markdown_block = True

        if in_markdown_block and 'unsafe_allow_html=True' in line:
            in_markdown_block = False
            # process the whole block
            for j in range(len(block_lines)):
                if '{t(' in block_lines[j] and '_html.escape(t(' not in block_lines[j]:
                    # Match only `{t("something")}` or `{t("something", arg=val)}`
                    block_lines[j] = re.sub(r'\{t\(([^}]+)\)\}', r'{_html.escape(t(\1))}', block_lines[j])
            new_lines.extend(block_lines)
            block_lines = []
        elif in_markdown_block and line.strip().endswith(')') and not line.strip().endswith('unsafe_allow_html=True)'):
            in_markdown_block = False
            new_lines.extend(block_lines)
            block_lines = []
        elif not in_markdown_block:
            new_lines.extend(block_lines)
            block_lines = []

    with open(filepath, 'w') as f:
        f.write(''.join(new_lines))

files = [
    'src/pages/search.py',
    'src/ui/cards/discovery.py',
    'src/ui/cards/admin.py',
    'src/ui/cards/cms_admin.py',
    'src/ui/cards/health.py',
    'src/ui/cards/pipelines.py',
    'src/ui/cards/detail.py'
]

for file in files:
    process_file(file)
