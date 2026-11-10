with open("src/db/duckdb_adapter.py", "r") as f:
    content = f.read()

content = content.replace("import secrets\n", "")
if "import secrets" not in content:
    content = content.replace("from __future__ import annotations", "from __future__ import annotations\nimport secrets")

with open("src/db/duckdb_adapter.py", "w") as f:
    f.write(content)

with open("src/sync/daemon_db.py", "r") as f:
    content = f.read()

content = content.replace("import secrets\n", "")
if "import secrets" not in content:
    content = content.replace("from __future__ import annotations", "from __future__ import annotations\nimport secrets")

with open("src/sync/daemon_db.py", "w") as f:
    f.write(content)
