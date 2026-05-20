def get_query_3(sch, tbl):
    query = "SELECT * FROM {s}.{t} LIMIT 100"  # nosec B608
    return query.format(s=sch, t=tbl)
