import duckdb

conn = duckdb.connect()
conn.execute("CREATE TABLE my_table (a INTEGER)")
conn.execute("INSERT INTO my_table VALUES (1)")
conn.execute("INSERT INTO my_table VALUES (2)")

try:
    print(conn.execute("SELECT * FROM ?", ["my_table"]).fetchall())
except Exception as e:
    print(e)
