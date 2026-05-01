# ADR 002 — Push-down SQL for permission enforcement

**Status:** Accepted  
**Date:** 2026-04-30  
**Deciders:** Platform team, Security team

---

## Context

The catalog contains tables owned by different business units. Users must only see tables they are authorized to access. Authorization is modeled as a set of Entra ID Security Group Object IDs extracted from the `groups` claim in the user's OIDC token.

The sync job extracts every `GRANT` from Unity Catalog and writes one row per (table, principal, privilege) triple into `permissions_cache`. At query time, the app knows the user's group IDs. The question is: where should the permission check happen?

### Option A — Python-side filtering

1. Run the search query without any permission filter, retrieving all matching rows
2. In Python, filter the result set to only include tables where `permissions_cache.principal` overlaps with the user's groups

Problems:
- The full result set is fetched from the database before filtering. For broad queries this means sending potentially thousands of unauthorized rows across the connection.
- If a bug is introduced in the Python filter, unauthorized rows can leak to the user interface. The defense is a single point of failure.
- Pagination and row counts become incorrect (the total count before filtering does not match the count after filtering).
- It is impossible to express "how many results exist for this user" without reading all results first.

### Option B — Push-down SQL JOIN

Enforce permissions by requiring every user-facing query to JOIN `tables_metadata` with `permissions_cache WHERE principal IN ($user_groups)`. The database engine discards unauthorized rows before returning any data.

The sentinel value `SELECT_ALL_USERS` in `permissions_cache.principal` marks tables that are publicly accessible to all authenticated users. A query that includes `SELECT_ALL_USERS` in the `IN` list returns those rows for everyone.

---

## Decision

Use push-down SQL authorization. All queries that return table-level results must include the permissions JOIN. The application layer performs no secondary filtering.

Implementation:

```sql
SELECT
    t.full_name,
    t.description,
    t.table_type
FROM tables_metadata t
JOIN permissions_cache p
    ON p.full_name = t.full_name
WHERE p.principal IN (%(group_1)s, %(group_2)s, 'SELECT_ALL_USERS')
  AND t.full_name ILIKE %(query)s
GROUP BY t.full_name, t.description, t.table_type
```

Parameterized queries are used throughout. The `_to_duckdb_sql()` function translates named parameters (`%(name)s`) to positional parameters (`?`) for DuckDB, preserving the parameterized pattern in both backends and preventing SQL injection via concatenation.

---

## Consequences

**Positive:**
- Unauthorized rows are never returned from the query engine. There is no Python code path that could accidentally expose them.
- Row counts and pagination are correct from the first query.
- The approach is transparent to auditors: every logged SQL statement is self-contained and shows exactly which groups were used.
- Works identically against DuckDB (local) and Databricks SQL Warehouse (production).

**Negative:**
- Every search query must include the permissions JOIN, adding complexity to query construction and making the SQL harder to read in isolation.
- The `IN` clause for group IDs can become long if a user belongs to many groups. DuckDB and Databricks SQL both handle large `IN` lists efficiently, but this is a theoretical concern for organizations with very deep AD group nesting.
- The `SELECT_ALL_USERS` sentinel is a convention, not a database constraint. If the sync job stops writing it for public tables, those tables silently disappear from all user views. This must be guarded by integration tests in the sync job.
- Query logic must not be bypassed. Any new query that returns table metadata must include the JOIN. Code review must enforce this; there is no automated check yet.
