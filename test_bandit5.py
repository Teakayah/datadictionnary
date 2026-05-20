def get_query(sch, tbl):
    query = 'SELECT * FROM "{}". "{}"'.format(sch.replace('"', '""'), tbl.replace('"', '""')) # nosec B608
    return query
