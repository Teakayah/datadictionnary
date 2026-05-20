import re

def render_data_sample(table_full_name: str, _sch: str, _tbl: str, CATALOG_CACHE: str):
    if not re.match(r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$", table_full_name):
        return
    query = "SELECT * FROM " + table_full_name + " LIMIT 100"

    _sample_query = "SELECT * FROM " + CATALOG_CACHE + '."' + _sch + '"."' + _tbl + '" LIMIT 100'
    return query, _sample_query
