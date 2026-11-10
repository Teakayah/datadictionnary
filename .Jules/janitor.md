## 2026-11-01 - Remove unused code and modernize syntax in tests
**Learning:** Running `ruff` to automatically clean up unused variables, redundant `elif` blocks, and unnecessary `open()` mode arguments provides an easy, low-risk way to eliminate technical debt in test files.
**Action:** Use targeted `ruff check <files> --fix` to address common anti-patterns like `UP015` and `RET505` across specific files when maintaining the codebase.
