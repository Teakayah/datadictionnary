import re
import sys

def process(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    new_content = content.replace("get_multi_hop_lineage", "get_lineage")

    with open(filepath, 'w') as f:
        f.write(new_content)
    print("Done", filepath)

process('src/db/queries.py')
process('src/pages/search.py')
process('tests/test_ui_search_downstream.py')
process('tests/test_db_queries.py')
process('tests/test_lineage.py')
process('tests/test_ui_search_query.py')
