def get_query(sch, tbl):
    query = 'SELECT * FROM "{}". "{}"'.format(sch.replace('"', '""'), tbl.replace('"', '""'))
    return query
