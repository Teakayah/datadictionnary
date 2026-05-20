def _escape_id(val: str) -> str:
    return '"' + val.replace('"', '""') + '"'

def get_query(sch, tbl):
    return "SELECT * FROM " + _escape_id(sch) + "." + _escape_id(tbl) + " LIMIT 100"

def get_query_2(sch, tbl):
    return f"SELECT * FROM {_escape_id(sch)}.{_escape_id(tbl)} LIMIT 100"

def get_query_3(sch, tbl):
    query = "SELECT * FROM {s}.{t} LIMIT 100"
    return query.format(s=_escape_id(sch), t=_escape_id(tbl))
