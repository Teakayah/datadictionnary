def get_query(sch, tbl):
    query = 'SELECT * FROM "{}". "{}"'.format(sch.replace('"', '""'), tbl.replace('"', '""'))  # nosec B608
    return query

def get_query_2(tbl_name):
    query = 'SELECT * FROM "{}" LIMIT 100'.format(tbl_name.replace('"', '""'))  # nosec B608
    return query
