from src.db.duckdb_adapter import _db_write_lock
import duckdb
import pandas as pd
import time
import os

db_path = "test.duckdb"
if os.path.exists(db_path):
    os.remove(db_path)

con = duckdb.connect(db_path)
con.execute("CREATE TABLE test (id INT PRIMARY KEY, val VARCHAR)")

data = [{'id': i, 'val': f'val_{i}'} for i in range(1000)]
df = pd.DataFrame(data)

def wrapper_execute(sql, params=None):
    with _db_write_lock:
        if params is not None and "df" in params:
            # register manually? or rely on local scope
            # we can't rely on local scope if we pass from a wrapper
            # wait, if we register on con, it works.
            con.register("tmp_df", params["df"])
            con.execute(sql)
            con.unregister("tmp_df")
            return

wrapper_execute("INSERT OR REPLACE INTO test SELECT * FROM tmp_df", {"df": df})
print(con.execute("SELECT count(*) FROM test").fetchall())
