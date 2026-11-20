# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `pyproject.toml`, `constraints.txt`, and `docker-compose.yml` for standardized packaging, transitive dependency security floors, and one-command offline showcasing.
- Standard repository governance files (`CODEOWNERS`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, Dependabot config, and GitHub issue/PR templates).
- Dependency vulnerability audit job (`pip-audit`) in GitHub Actions CI.
- `DUCKDB_EXTENSION_DIRECTORY` configuration support for `readOnlyRootFilesystem` container deployments.

### Fixed
- Aligned `Dockerfile` `appuser` UID/GID (`10001`), set `HOME=/tmp`, pre-installed DuckDB `vss` into `/opt/duckdb_extensions`, and included `.streamlit/config.toml` in the container image.
- Updated `k8s/cronjob.yaml` and documentation to invoke `scripts/sync_metadata.py` and removed the obsolete `scripts/nightly_sync.py` script.
- Removed stray/personal tracked artifacts and synchronized generated HTML documentation.

## [0.1.0] - 2026-11-13

### Added
- **Streamlit Business Data Dictionary UI (`app.py`, `src/pages/`, `src/ui/`)**: Search-first catalog explorer, catalog browser, business glossary, interactive `vis-network` lineage graph, health insights dashboard, and editorial design system (`design_system/`).
- **Push-down RBAC & Entra ID Auth (`src/auth.py`, `src/auth_graph.py`)**: OIDC authentication with Microsoft Graph `getMemberObjects` overage resolution (>150 groups), 1-hour process-level cache with sign-out invalidation and admin flush control, plus development-only mock auth guard.
- **REST API & MCP Server (`src/api/`, `src/mcp_server/`)**: FastAPI endpoints (`/api/v1/tables`, `/search`, `/lineage`) and Streamable HTTP MCP server (`/mcp`) with RS256 Entra ID Bearer JWT validation and Redis response caching (`src/cache/`).
- **Metadata Sync & Sidecar Write-Back (`scripts/sync_metadata.py`, `src/sync/`)**: Atomic DuckDB catalog cache rebuilds (`tables_metadata`, `columns_metadata`, `permissions_cache`, `lineage_cache`, `object_tags`) and standalone sidecar daemon (`python -m src.sync.daemon`) with `/healthz` probe and DR resync.
- **Hybrid Semantic Search (`src/semantic.py`)**: Optional `ENABLE_SEMANTIC_SEARCH` DuckDB VSS + BM25 weighted ranking fusion backed by Databricks Model Serving or deterministic mock embeddings.
- **Bilingual EN/FR Support (`locale/`)**: Full English and French UI localization and bilingual table business names/definitions with steward proposal and admin approval workflows.
- **Admin Tooling (`src/cms.py`, `src/pipelines.py`, `src/audit.py`, `src/analytics.py`)**: CMS discovery announcements, optional Databricks/ADF/ADO pipeline triggers, inline editing toggle, audit log viewer, and search gap analytics.
