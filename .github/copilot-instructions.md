# GitHub Copilot Instructions

## Repository overview

This is a Python-native Business Data Dictionary for Databricks Unity Catalog. It provides a searchable, permission-filtered view of catalog metadata to business users.

## CI and testing

- Run the standard checks with `python scripts/auto_ci.py`. This runs the unit suite and verifies generated HTML documentation is synchronized.
- The standard unit suite excludes `tests/load/`, `tests/test_load_smoke.py`, `tests/test_wcag_axe.py`, and `tests/test_nav_render.py`. Accessibility tests require a running app and Chromium and are run by `.github/workflows/accessibility.yml`.
- For local UI tests, use `ENABLE_MOCK_AUTH=true ENVIRONMENT=development DEMO_DATA=true DUCKDB_PATH=:memory:`.
- Update generated documentation with `python scripts/md_to_html.py` whenever source Markdown used by the generator changes.
- `.github/workflows/ci.yml` owns pull-request and main-branch validation. `.github/workflows/deploy.yml` handles image publishing, Kubernetes deployment, and tagged releases.

## Code conventions

- Preserve permission filtering in SQL; do not fetch unauthorized catalog results and filter them in Python.
- Follow existing module patterns, tests, and error handling. Keep demo-mode behavior isolated from production behavior.
- Follow `design_system/README.md` for UI work. Use design-system CSS variables and sentence case; do not hard-code colors or add emoji to UI copy.
- Never commit credentials or real secrets. Keep mock authentication restricted to development and tests.
