
import duckdb
import os

def check_db(path, name):
    print(f"\n--- Checking {name} ({path}) ---")
    if not os.path.exists(path):
        print("File does not exist.")
        return
    try:
        con = duckdb.connect(path, read_only=True)
        tables = con.execute("SHOW ALL TABLES").df()
        if name == "Main Cache":
            print("\nColumns in tables_metadata:")
            print(con.execute("PRAGMA table_info('dictionary_cache.tables_metadata')").df())
        con.close()
    except Exception as e:
        print(f"Error: {e}")

check_db("data/test_data.duckdb", "Main Cache")
check_db("data/test_data_user_data.duckdb", "User Data")
