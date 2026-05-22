## 2024-05-24 - SQL Injection in DuckDB ATTACH
**Vulnerability:** SQL Injection in `ATTACH` statement due to unescaped identifier interpolation (`CATALOG_CACHE`).
**Learning:** Dynamic identifiers (like database names, schemas, catalogs) cannot be parameterized with `?` in DuckDB and must be explicitly escaped with double quotes (`"`) and internal double quotes doubled (`""`) before being inserted into queries via f-strings.
**Prevention:** Always escape dynamic identifiers (using `'"' + val.replace('"', '""') + '"'`) before interpolation in SQL queries.
