## 2024-05-22 - Cover fetch_member_groups exception path
Coverage Gap: Missing test for generic Exception handling in fetch_member_groups.
Learning: Need to ensure error paths fail closed explicitly.
Assertion: Test confirms fetch_member_groups returns an empty list and logs a warning on exception.
