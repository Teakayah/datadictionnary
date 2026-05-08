import duckdb
import pandas as pd
import time
import os

db_path = "test.duckdb"
if os.path.exists(db_path):
    os.remove(db_path)

con = duckdb.connect(db_path)
con.execute("CREATE TABLE test (id INT PRIMARY KEY, val VARCHAR)")

# Generate sample data
data = [{'id': i, 'val': f'val_{i}'} for i in range(100000)]
df = pd.DataFrame(data)

start = time.time()
con.execute("INSERT OR REPLACE INTO test SELECT * FROM df")
print(f"direct df insert: {time.time() - start:.4f}s")
