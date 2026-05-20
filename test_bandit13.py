def _escape_id(val: str) -> str:
    return '"' + val.replace('"', '""') + '"'

def get_query(CATALOG_CACHE, _sch, _tbl):
    _sample_query = f"SELECT * FROM {_escape_id(CATALOG_CACHE)}.{_escape_id(_sch)}.{_escape_id(_tbl)} LIMIT 100"  # nosec B608
    return _sample_query

def get_query_2(table_full_name):
    parts = table_full_name.split(".")
    query = f"SELECT * FROM {_escape_id(parts[0])}.{_escape_id(parts[1])}.{_escape_id(parts[2])} LIMIT 100"  # nosec B608
    return query
