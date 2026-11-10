import re

with open("src/db/duckdb_adapter.py", "r") as f:
    content = f.read()

# Make sure we don't double replace
if "$tok$" not in content:
    content = content.replace(
        'con.execute(f\'ATTACH IF NOT EXISTS \\\'{safe_user_data_path}\\\' AS "user_data" (READ_ONLY)\')',
        'con.execute(f\'ATTACH IF NOT EXISTS ${tok}${safe_user_data_path}${tok}$ AS "user_data" (READ_ONLY)\')'
    )
    content = content.replace(
        'con.execute(f\'ATTACH IF NOT EXISTS \\\'{safe_user_data_path}\\\' AS "user_data"\')',
        'con.execute(f\'ATTACH IF NOT EXISTS ${tok}${safe_user_data_path}${tok}$ AS "user_data"\')'
    )
    content = content.replace(
        'con.execute(f"ATTACH \'{safe_duckdb_path}\' AS {_escape_id(CATALOG_CACHE)} (READ_ONLY)")',
        'con.execute(f"ATTACH ${tok}${safe_duckdb_path}${tok}$ AS {_escape_id(CATALOG_CACHE)} (READ_ONLY)")'
    )

    content = content.replace(
        'safe_duckdb_path = DUCKDB_PATH.replace("\\x00", "").replace("\'", "\'\'") if DUCKDB_PATH else ""',
        'tok = "t" + secrets.token_hex(8)\n            safe_duckdb_path = DUCKDB_PATH.replace("\\x00", "") if DUCKDB_PATH else ""'
    )
    content = content.replace(
        'safe_user_data_path = USER_DATA_PATH.replace("\\x00", "").replace("\'", "\'\'") if USER_DATA_PATH else ""',
        'safe_user_data_path = USER_DATA_PATH.replace("\\x00", "") if USER_DATA_PATH else ""'
    )

    content = content.replace(
        'def _ensure_user_data_attached(con, safe_user_data_path: str, read_only: bool = False) -> None:',
        'def _ensure_user_data_attached(con, safe_user_data_path: str, read_only: bool = False) -> None:\n    tok = "t" + secrets.token_hex(8)'
    )

with open("src/db/duckdb_adapter.py", "w") as f:
    f.write(content)

with open("src/sync/daemon_db.py", "r") as f:
    content = f.read()

if "$tok$" not in content:
    content = content.replace(
        'f"ATTACH \'{safe_duckdb_path}\' AS \\"{safe_catalog_cache}\\" (READ_ONLY)"',
        'f"ATTACH ${tok}${safe_duckdb_path}${tok}$ AS \\"{safe_catalog_cache}\\" (READ_ONLY)"'
    )
    content = content.replace(
        'f"ATTACH IF NOT EXISTS \'{safe_user_data_path}\' AS \\"user_data\\""',
        'f"ATTACH IF NOT EXISTS ${tok}${safe_user_data_path}${tok}$ AS \\"user_data\\""'
    )
    content = content.replace(
        'safe_duckdb_path = DUCKDB_PATH.replace("\\x00", "").replace("\'", "\'\'") if DUCKDB_PATH else ""',
        'tok = "t" + secrets.token_hex(8)\n        safe_duckdb_path = DUCKDB_PATH.replace("\\x00", "") if DUCKDB_PATH else ""'
    )
    content = content.replace(
        'safe_user_data_path = USER_DATA_PATH.replace("\\x00", "").replace("\'", "\'\'") if USER_DATA_PATH else ""',
        'safe_user_data_path = USER_DATA_PATH.replace("\\x00", "") if USER_DATA_PATH else ""'
    )


with open("src/sync/daemon_db.py", "w") as f:
    f.write(content)
