# Data Dictionary

Permission-trimmed, search-first business data dictionary for Databricks
Unity Catalog. Authenticates against Microsoft Entra ID, reads catalog
metadata from a local DuckDB cache (rebuilt nightly), and exposes a
Streamlit UI that lets non-technical users discover only the tables they
have grants on.

## What it does

- **Search & discovery** across catalogs, schemas, tables, and columns —
  with full-text matching on names, descriptions, and business glossary
  terms.
- **Push-down RBAC** — every result-returning query joins
  `permissions_cache` so unauthorized rows never leave the SQL engine.
  Built on Entra ID security-group claims, with overage handling for
  users in 150+ groups.
- **Inline metadata editing** for power users — column business names,
  table descriptions, stewards. Writes are queued locally and pushed to
  Unity Catalog by a sidecar sync worker.
- **Personalisation** — bookmarks, recents, and column bookmarks per user.
- **Admin tooling** — CMS posts on the discovery tab, pipeline runs
  (Databricks / ADF / ADO), audit log, sync-queue dashboard, group-cache
  flush.

## Quick start

```bash
# Install runtime + dev deps (lock files at versions tested)
pip install -r requirements.txt -r requirements-dev.txt

# Configure
cp .env.example .env
# Fill in DATABRICKS_*, TENANT_ID/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI

# First-time data load
python scripts/nightly_sync.py

# Run the app
streamlit run app.py
```

For local UI work without Databricks credentials:

```bash
ENABLE_MOCK_AUTH=true ENVIRONMENT=development DEMO_DATA=true streamlit run app.py
```

## Test

```bash
pytest tests/ -q --ignore=tests/test_load_smoke.py \
                 --ignore=tests/test_wcag_axe.py \
                 --ignore=tests/test_nav_render.py
```

The three excluded suites need a live app or Playwright browsers
(`playwright install chromium`) and are wired up in CI separately.

## Architecture at a glance

```
┌─────────────────┐      ┌──────────────────┐      ┌──────────────┐
│ Streamlit pods  │      │  Sync worker     │      │  Databricks  │
│ (read + enqueue)│      │  (drain + push)  │      │  Unity Cat.  │
│                 │ enq. │                  │ push │              │
│  DuckDB local ←─┼──────┤   DuckDB local ──┼──────┼─►            │
│   ATTACH RO     │      │   user_data RW   │ pull │              │
└────────┬────────┘      └─────────┬────────┘ ◄────┼──────────────┘
         │                         │   DR resync
         └────  PVC dd-data  ──────┘
              dict.duckdb (catalog cache, nightly)
              dict_user_data.duckdb (overrides + queue + audit)
```

Streamlit pods only ever write locally to DuckDB. The sidecar daemon
(`python -m src.sync.daemon`) drains `user_data.pending_sync` to
Databricks and pulls late-arriving rows back via DR resync. See
[`docs/adr/004-sidecar-sync-worker.md`](docs/adr/004-sidecar-sync-worker.md)
for the design.

## Deeper reading

| | |
| -- | -- |
| [`docs/business-requirements.md`](docs/business-requirements.md) | What the app is for — personas, functional + non-functional reqs, scope, success metrics |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System design, components, data flows |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Kubernetes setup runbook |
| [`docs/adr/`](docs/adr) | Architecture decision records |
| [`docs/runbooks/`](docs/runbooks) | Sync-worker ops + secret rotation |
| [`docs/api/locale-keys.md`](docs/api/locale-keys.md) | EN/FR string reference |
| [`design_system/README.md`](design_system/README.md) | UI design system |
| [`TODO.md`](TODO.md) | Engineering backlog |
| [`CLAUDE.md`](CLAUDE.md) | Codebase notes for Claude Code sessions |

## License

See [`LICENSE`](LICENSE).
