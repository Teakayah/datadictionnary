## Janitor Journal

## 2026-05-04 - [Ruff Unused Variable Fixes] **Learning:** Ruff's `--fix` flag for unused variables (F841) might only remove the left-hand variable assignment, leaving the right-hand pure expressions hanging (e.g., set comprehensions, or method calls that return DataFrames). **Action:** Always manually review and delete the entire line when fixing F841 to avoid leaving dead code, or refactor to preserve necessary side effects.
