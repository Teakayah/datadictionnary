# Contributing to Data Dictionary

Thank you for contributing. Follow the workflow below so changes remain consistent with the architecture, design system, and CI checks.

## Local Development Setup

### Option 1 — Python virtual environment (fastest for UI/code changes)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -c constraints.txt -r requirements.txt -r requirements-dev.txt
cp .env.example .env

ENABLE_MOCK_AUTH=true ENVIRONMENT=development DEMO_DATA=true streamlit run app.py
```

Optional: generate an offline 800-table DuckDB dataset instead of using in-memory fixture data:

```bash
python scripts/generate_test_data.py --with-data
DUCKDB_PATH=data/test_data.duckdb ENABLE_MOCK_AUTH=true ENVIRONMENT=development streamlit run app.py
```

### Option 2 — Local showcase stack with Docker Compose

```bash
docker compose up --build
```

- Streamlit UI: `http://localhost:8501`
- REST API OpenAPI docs: `http://localhost:8080/docs`

## Running Checks Before Opening a PR

Run the shared CI entrypoint locally:

```bash
python scripts/auto_ci.py
```

This runs:
1. The pytest unit and integration suite (excluding load tests and live-browser Playwright tests).
2. `scripts/md_to_html.py` and checks that all generated `docs/*.html` files are up to date.

If you edit any Markdown document mapped in `scripts/md_to_html.py` (such as `ARCHITECTURE.md`, ADRs, feature docs, or runbooks), run:

```bash
python scripts/md_to_html.py
```

and commit the updated `docs/*.html` files alongside your Markdown changes.

To run Ruff locally:

```bash
ruff check app.py src/ scripts/ tests/
```

## UI & Design System Rules

All Streamlit UI work must follow [`design_system/README.md`](design_system/README.md):

- Use tokens from `design_system/colors_and_type.css` (`--paper`, `--ink`, `--accent`, etc.); avoid hard-coded hex values.
- Use sentence case everywhere, no UI emoji, `§` section headers, and monospace styling for Unity Catalog identifiers.
- Place reusable styles in `src/ui/css.py` / `assets/design.css`.
- Update both `locale/en.json` and `locale/fr.json` for every user-facing string.

## Dependency Management & Internal PyPI Mirrors

Runtime dependencies are declared in `requirements.txt` with security floors in `constraints.txt`. For air-gapped or internal PyPI mirror deployments that require `--require-hashes`:

```bash
pip install pip-tools
pip-compile --generate-hashes --constraint=constraints.txt requirements.txt -o requirements.lock
pip install --require-hashes -r requirements.lock
```

## Pull Request Process

1. Create a feature branch from `main`.
2. Keep changes focused and include unit tests under `tests/`.
3. Verify `python scripts/auto_ci.py` exits `0`.
4. Fill out the PR checklist and request review.
