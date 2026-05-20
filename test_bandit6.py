def get_query(sch, tbl):
    query = "SELECT * FROM " + sch + "." + tbl + " LIMIT 100"
    return query
