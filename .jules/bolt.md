## 2026-05-22 - Flawed N+1 Rationale
**Learning:** Parameter unrolling (creating `group_0`, `group_1`, etc.) for a single `IN` clause is safe from SQL injection, ensures cross-driver database compatibility, and is not an N+1 query problem. Refactoring this loop actually reduces compatibility without improving performance.
**Action:** Retained the parameter unrolling pattern and added an explicit inline comment explaining the cross-driver compatibility and why the N+1 rationale was flawed.
