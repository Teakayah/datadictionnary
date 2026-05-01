# Architecture overview

Business Data Dictionary for Databricks Unity Catalog. This document describes the system design, component responsibilities, data flows, and key architectural decisions.

---

## System architecture

The solution has four layers: identity, compute/UI, local cache, and the Databricks Unity Catalog source of truth.

```mermaid
graph TD
    subgraph "Identity layer (Azure)"
        A[Business user] -->|OIDC login| B[Microsoft Entra ID]
        B -->|JWT token + group claims| C[Streamlit application]
    end

    subgraph "Compute and UI layer"
        C -->|Permission-filtered SQL| D[DuckDB local cache]
        C -->|Fallback| E[Databricks SQL Warehouse]
    end

    subgraph "Local cache layer"
        D -->|Atomic file replace on sync| F[(dict.duckdb — catalog file)]
        G[(dict_user_data.duckdb — user file)] -->|ATTACHed at startup| D
    end

    subgraph "Background workers"
        H[Nightly sync job] -->|Writes catalog file| F
        I[DR resync worker thread] -->|Fills gaps on demand| F
    end

    subgraph "Unity Catalog (source of truth)"
        H -->|Crawl metadata and ACLs| J[Catalogs / schemas / tables]
    end
```

---

## Core components

### Identity and security layer

Authentication uses the OAuth 2.0 / OpenID Connect flow against Microsoft Entra ID. The app extracts Security Group Object IDs from the `groups` claim in the ID token. No additional database lookup is needed to resolve group membership — the signed token is the proof.

In local development, setting `ENABLE_MOCK_AUTH=true` and `ENVIRONMENT=development` replaces the Entra ID redirect with department-specific mock login buttons (finance, research, hr, it).

### Metadata sync job

`scripts/sync_metadata.py` uses the `databricks-sdk` (`WorkspaceClient`) to crawl the Unity Catalog hierarchy: catalogs → schemas → tables → columns → grants → lineage edges.

Output is written to:

- The Databricks `data_governance.dictionary_cache` schema (truncate-and-reload via SQL Warehouse)
- A local DuckDB file at `DUCKDB_PATH` (atomic swap via `os.replace` so in-flight reads are never interrupted)

A separate script, `scripts/nightly_sync.py`, is the entry point for the CronJob container. The in-app DR resync worker is a different, lighter process (see below).

### DuckDB local cache layer

When `DUCKDB_PATH` is set, the app serves all read queries from a local DuckDB file instead of routing them across the network to the SQL Warehouse. This reduces median query latency from ~300 ms (network round-trip) to under 5 ms for typical search queries on the 800-table reference dataset.

Two files are used:

| File | Owner | Contents |
|------|-------|----------|
| `DUCKDB_PATH` (e.g. `dict.duckdb`) | Sync job | `tables_metadata`, `columns_metadata`, `permissions_cache`, `lineage_cache`, `object_tags`, `audit_log` — rebuilt atomically on each sync |
| `USER_DATA_PATH` (auto-derived as `dict_user_data.duckdb`) | App | `user_data.comments`, `user_data.business_name_overrides`, `user_data.audit_log` — append-only, never touched by the sync job |

At startup the app opens the catalog file and `ATTACH`es the user data file as the `user_data` schema. This enables cross-file JOINs (e.g. joining `tables_metadata` with `user_data.business_name_overrides`). All writes are serialized through a singleton connection and a `threading.Lock`.

The `_to_duckdb_sql()` function translates Databricks SQL dialect to DuckDB SQL (parameter style `%s` → `?`, function aliases, etc.) so the same query strings work against both backends.

### Background DR resync worker

A daemon thread (`_run_dr_resync`) runs inside the Streamlit process and monitors the DuckDB cache for staleness. When it detects that a table's metadata is missing or out of date — and the nightly sync has not yet run — it fetches the missing records from the SQL Warehouse and writes them into the local cache. This is a best-effort gap-filler, not a replacement for the nightly sync job.

UI activity is tracked via `_mark_ui_activity()`. The worker backs off during active user sessions to avoid competing for DuckDB write locks.

### Streamlit frontend

`app.py` is the Streamlit entry point. It implements five tabs (search, catalog, discovery, health, glossary) and an admin panel, all within a single-page layout using custom tab-based navigation.

The design system CSS is injected via `st.markdown('<style>...</style>')` at startup. All Unity Catalog identifiers (`catalog.schema.table`) are rendered in `JetBrains Mono`. The only accent color is oxidized red `#B8362A` (CSS variable `--accent`).

---

## Security model

### Push-down SQL authorization

Permission enforcement happens inside the SQL engine, not in Python. Every user-facing query that returns tables JOINs `tables_metadata` with `permissions_cache WHERE principal IN ($user_groups)`. Rows for tables the user is not authorized to see are excluded before they reach the application layer.

The sentinel value `SELECT_ALL_USERS` in `permissions_cache.principal` marks publicly accessible tables. These rows appear in search results for all authenticated users regardless of group membership.

The `_to_duckdb_sql()` function ensures parameter substitution is correctly translated between backends. Named parameters in Databricks SQL (`%(name)s`) are converted to positional parameters (`?`) for DuckDB, preserving the parameterized-query pattern in both modes and avoiding SQL injection via concatenation.

### Feature-level access control

- `EDITOR_GROUPS`: comma-separated group IDs allowed to save business name overrides and comments.
- `ADMIN_GROUPS`: comma-separated group IDs allowed to access the admin dashboard and audit logs. There is no demo bypass for admin access.

User-supplied display names are HTML-escaped before rendering. SMTP headers are sanitized to prevent header injection in comment notification emails.

---

## Personalisation persistence

User personalisation data (bookmarks, recently viewed tables, column bookmarks) is stored in a separate DuckDB file (`USER_DATA_PATH`). This file is append-only from the app's perspective and is never modified by the sync job.

The user is identified by their Entra ID Object ID (`oid` claim), stored as `user_oid` on every preference row. Preferences are loaded into `st.session_state` at session start via `_sync_prefs_to_session()` and written back immediately on user action through `_pref_upsert()` / `_pref_delete()`.

---

## Internationalisation (i18n)

The app supports English and French. Locale files live in `locale/`:

```
locale/
  en.json    English strings (default)
  fr.json    French strings
```

The active locale is stored in `st.session_state.locale` and defaults to `"en"`. Users toggle it with the `EN / FR` control in the header.

All user-visible strings are retrieved through the `t(key)` function:

```python
# Dot-separated key addressing nested JSON structure
label = t("search.placeholder")           # "Search tables or columns..."
msg   = t("search.results_count", count=n) # "{count} results" → "42 results"
```

`t()` looks up the key in the active locale dict, falls back to English if the key is missing in the French file, and performs `str.format_map()` substitution for `{placeholder}` tokens. See `docs/api/locale-keys.md` for the full key reference with EN and FR values side by side.

---

## Glossary and business semantics

The business glossary is generated dynamically from Unity Catalog metadata properties:

| Glossary field | Unity Catalog source | Cache table |
|---------------|---------------------|-------------|
| Term name | Table or column name | `tables_metadata` |
| Definition | Primary `COMMENT` | `tables_metadata` |
| Calculation | Tag with key `calculation` | `object_tags` |
| Domain | Schema tag with key `domain` | `object_tags` |
| Steward | Table tag with key `steward` | `object_tags` |
| Linked tables | Table lineage edges | `lineage_cache` |

---

## Cache tables reference

All tables live in `data_governance.dictionary_cache` on Databricks and in the root schema of the DuckDB file.

| Table | Grain | Key columns |
|-------|-------|-------------|
| `tables_metadata` | One row per table | `full_name`, `description`, `table_type` |
| `columns_metadata` | One row per column | `full_name`, `column_name`, `data_type`, `description` |
| `permissions_cache` | One row per (table, principal, privilege) | `full_name`, `principal`, `privilege` |
| `lineage_cache` | One row per lineage edge | `source_table`, `target_table`, `hop` |
| `object_tags` | One row per (object, tag key) | `full_name`, `tag_key`, `tag_value` |

`setup_cache_tables()` in `scripts/sync_metadata.py` creates all tables with `IF NOT EXISTS`. It is safe to run repeatedly and is called at the start of every sync.

---

## Deployment topology

In Kubernetes the solution runs as:

- A `Deployment` (`dd-app`) with 2–10 replicas managed by an HPA. Probes target `/_stcore/health` on port 8501.
- A `CronJob` (`dd-sync`) that runs `scripts/sync_metadata.py` nightly at 03:00 UTC.
- A `PersistentVolumeClaim` (`dd-data`) mounted at `/data` in both the app and the sync job, sharing the DuckDB cache files.
- A `NetworkPolicy` restricting ingress to the ingress controller namespace and egress to HTTPS only.

See `DEPLOYMENT.md` for the full operations runbook and `docs/runbooks/secret-rotation.md` for credential rotation procedures.
