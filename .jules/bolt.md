## 2026-05-22 - Document false positive cache rationale in health dashboard
**Learning:** When an issue incorrectly identifies a performance problem that conflicts with an architectural constraint (e.g., ADR 002 enforcing SQL push-down vs. Python/Pandas in-memory aggregation), do not force an unnecessary refactor.
**Action:** Documented the false positive via an inline comment using the active persona's format.
