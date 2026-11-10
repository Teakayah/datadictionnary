import re

with open("tests/test_sql_inject.py", "r") as f:
    c = f.read()

c = c.replace(
    'evil_path = str(tmp_path / "evil\'; SELECT 1; --path.duckdb")',
    'evil_path = str(tmp_path / "evil$token$path.duckdb")'
)

c = c.replace(
    'str(tmp_path / "evil\'; SELECT 1; --path.duckdb")',
    'str(tmp_path / "evil$token$path.duckdb")'
)

c = c.replace(
    'str(tmp_path / "evil\'; SELECT 1; --path3.duckdb")',
    'str(tmp_path / "evil$token$path3.duckdb")'
)

c = c.replace(
    'str(tmp_path / "evil\'; SELECT 1; --path2.duckdb")',
    'str(tmp_path / "evil$token$path2.duckdb")'
)

with open("tests/test_sql_inject.py", "w") as f:
    f.write(c)
