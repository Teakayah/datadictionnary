## 2024-06-24 - Test Argument Ordering with Fixtures
**Learning:** When combining `@patch` decorators with `pytest` fixtures in test function signatures, the mock arguments created by `@patch` must be listed *before* any pytest fixtures in the parameter list. Placing a mock argument after a fixture causes pytest to attempt to inject it as a fixture, resulting in "fixture not found" errors.
**Action:** Always structure test arguments as `(self, mock_1, mock_2, ..., fixture_1, fixture_2)` when mixing both approaches to prevent fixture resolution errors.
