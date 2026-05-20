def get_query(sch, tbl):
    query = (
        "SELECT * FROM "
        f"{sch}.{tbl} "
        "LIMIT 100"
    ) # nosec B608
    return query
