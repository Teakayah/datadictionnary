## 2024-05-22 - Prevent SQL Injection in Table Previews
**Vulnerability:** SQL Injection via unescaped f-string interpolation for table and schema identifiers.
**Learning:** Direct parameterization is unsupported for dynamic table/schema names in DuckDB/Databricks.
**Prevention:** Always manually escape identifiers with double quotes (e.g., replacing `"` with `""`) before string interpolation.
