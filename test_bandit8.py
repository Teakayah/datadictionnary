def get_query(sch, tbl):
    query = "SELECT * FROM {s}.{t} LIMIT 100".format(s=sch, t=tbl) # nosec B608
    return query
