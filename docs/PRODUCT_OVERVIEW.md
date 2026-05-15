# Data Dictionary — Product Overview

> A business-language, permission-trimmed data catalog for Databricks Unity Catalog.
> This document covers **what** the product is, **why** it exists, **how** it is built, and **when** it runs.

---

## Table of contents

1. [What it is](#1-what-it-is)
2. [Why it exists](#2-why-it-exists)
3. [Who uses it](#3-who-uses-it)
4. [Feature map](#4-feature-map)
5. [How it is built — architecture](#5-how-it-is-built--architecture)
6. [Security model](#6-security-model)
7. [When things run — operational cadence](#7-when-things-run--operational-cadence)
8. [Deployment topology](#8-deployment-topology)
9. [Key architectural decisions](#9-key-architectural-decisions)
10. [Non-functional properties](#10-non-functional-properties)
11. [Out of scope](#11-out-of-scope)
12. [Success metrics](#12-success-metrics)

---

## 1. What it is

Data Dictionary is an internal web application that gives non-technical business users a **searchable, business-language view** of the data assets available to them in Databricks Unity Catalog.

Users sign in with their Microsoft Entra ID account and immediately see only the tables and columns they are already authorized to access — no new permission model, no IT tickets. They can search across thousands of tables in milliseconds, read and write business definitions, preview data samples, monitor pipeline runs, and receive curated announcements from data stewards, all from a single browser tab.

**Core proposition in one sentence:** replace a daily tax of Slack threads and shadow spreadsheets with a 2-minute self-service lookup.

---

## 2. Why it exists

### The problem

Non-technical staff at the organisation cannot reliably find or understand the data assets they have access to in Databricks Unity Catalog. The native Unity Catalog UI is engineering-oriented: it exposes physical schema, internal IDs, and admin-flavored surfaces that make routine business questions ("which table holds approved invoices?", "who is the steward of this column?") expensive to answer.

The result is a measurable daily cost:

- Repeated `#ask-data` Slack threads directed at data engineers
- Duplicated reports built from different, incompatible source tables
- Shadow data dictionaries maintained in spreadsheets that drift from reality

### The goal

A single, **search-first, business-language** view of the catalog that:

1. Exposes only the data the user is **already entitled to see** (Entra ID groups + Unity Catalog grants) — no new permission model.
2. Lets non-technical users discover, understand, and reference tables and columns without writing SQL or talking to data engineering.
3. Lets data stewards keep business definitions current without raising a ticket against the data platform team.

---

## 3. Who uses it

| Persona | Profile | Primary needs |
|---|---|---|
| **Business analyst** | Finance / HR / Research / IT operations. SQL-aware but rarely writes it. Owns reports and dashboards. | Find the right table fast; understand columns in business terms; preview a sample of rows; export schema for a brief. |
| **Data steward** | Domain SME (e.g. Finance Controller). Owns the business meaning of the data. Not a developer. | Curate business names, definitions, comments. See what's been changed and by whom. |
| **Data engineer / platform admin** | Maintains the catalog and the pipelines that feed it. | Trigger / monitor pipelines; check sync queue; flush group caches; audit edits. |
| **Compliance / audit** | Reads the audit log. Cares about who saw or edited what. | Trustworthy, tamper-resistant audit trail. |
| **Read-only consumer** | Most logged-in users. May only see the discovery and search tabs. | Discover relevant tables; bookmark; receive announcements. |

---

## 4. Feature map

### F1 — Search and discovery
Full-text search across catalogs, schemas, table names, column names, descriptions, and business-glossary terms. Results are returned in under 500 ms (p95) and are permission-filtered — the user only sees what they are authorized to access.

The Discovery tab has four sub-tabs:
- **Recommended** — tables ranked by recent edit and comment activity across the organisation, excluding tables the user has already viewed (surfaces genuinely new assets)
- **Notable** — recently updated tables scoped to the user's primary group
- **My bookmarks** — tables and columns the user has starred
- **Recently viewed** — chronological navigation history

A CMS banner above the sub-tabs allows admins to publish pinned announcements, featured tables, and guides with configurable expiry (2 / 7 / 30 days or never).

### F2 — Permission-trimmed visibility
Every result-returning SQL query `JOIN`s the permissions cache, so unauthorized rows are excluded **inside the database engine** before any data leaves the SQL layer. Users with more than 150 Entra group memberships (the "overage" case) are handled transparently via a Microsoft Graph API fallback — they see the same results as any other user, with no manual intervention required.

The sentinel principal `SELECT_ALL_USERS` marks tables that are publicly accessible to all authenticated users.

### F3 — Table detail view
Per-table page showing:
- Catalog / schema / table identifier (monospace)
- Description, steward, table type, freshness
- Full column list with data type, Unity Catalog comment, business name override, and definition override
- Grant list (who can access the table and with what privilege)
- Multi-hop lineage (upstream / downstream tables) — powered by a single recursive SQL CTE, replacing a previous N+1 hop-by-hop query pattern
- **Downstream impact summary** — count of downstream assets in the blast radius, with a warning when certified or production tables are affected
- Data quality grade badge (A–F) when DQ data is available (sourced from Lakehouse Monitoring or Unity Catalog tags)
- Data sample — top 100 rows, shown only if the user has `SELECT` on the table
- CSV export of the schema including business names and definitions

### F4 — Inline metadata editing with approval workflow
Power users (members of `EDITOR_GROUPS`) can edit:
- Table description and steward — written immediately to a local overrides table (`user_data.table_metadata_overrides`) and pushed to Unity Catalog by the sidecar
- Column business name (max 255 chars) and definition (max 2000 chars)

**Approval workflow for column overrides:** admins publish directly and changes sync to Databricks immediately. Non-admin power users create a `pending_approval` proposal that appears in the admin review queue. Admins approve or reject from the Admin dashboard; only approved changes are pushed to Unity Catalog. Every edit (and every approval / rejection) produces an audit-log entry with actor email, timestamp, and before/after values.

Admins can globally disable editing (e.g., during a data migration) without redeploying.

### F5 — Comments
Any authenticated user can leave a question or flag on any table or column (max 1000 chars), with one level of threaded replies. New comments trigger an email notification to the table steward when SMTP is configured; email failures do not block the comment from being saved.

### F6 — Health dashboard
Catalog-wide documentation coverage metrics:
- Percentage of tables with a description
- Percentage of columns with a description
- Freshness grade per schema
- "Priority actions" panel listing up to 5 undocumented tables, deep-linkable to their detail view

### F7 — Pipelines
Members of `PIPELINE_GROUPS` (and admins) can trigger, monitor, and cancel named pipeline runs. Three backends are supported:
- **Databricks Jobs** (Jobs API 2.1)
- **Azure Data Factory** (management API 2018-06-01)
- **Azure DevOps Pipelines** (API 7.0)

One active run is allowed per pipeline at a time. The status panel auto-polls every 3 seconds while a run is in flight, showing live progress percentage and lifecycle state. Start and stop actions show toast notifications; the Save and Send buttons use primary styling for visual prominence.

### F8 — Admin dashboard
Admin-only panel (members of `ADMIN_GROUPS`) with two tabs:

**Operations tab:**
- Catalog statistics
- Sync-queue status and daemon heartbeat
- Pending metadata approvals — column override proposals submitted by non-admin editors, with approve / reject actions
- Full audit log
- Comment log
- CMS post CRUD (create / publish / delete announcements)
- Pipeline-definition CRUD (register / remove named pipelines)
- Global editing toggle
- Group-permissions cache flush

**Quality Insights tab:**
- High-impact gaps — popular tables (by audit-log activity) that are missing a description or steward
- Stewardship gaps — full list of tables without an assigned steward
- DQ alerts — tables with a failing data-quality check (sourced from `data_quality_cache`)

All write functions re-check authorization at the function boundary — defense-in-depth beyond the UI gate.

### F9 — Internationalisation
The UI is available in English and French. Locale is auto-detected from the `Accept-Language` header and can be toggled per session with the `EN / FR` control in the header. All UI strings are stored in `locale/en.json` and `locale/fr.json`; French falls back to English for any key not yet translated. The sign-in page is fully internationalised (11 locale keys covering stats, card copy, mock-auth prompts, and policy text).

### F10 — Personalisation
Per-user bookmarks (tables and columns) and recently viewed tables, persisted across sessions, keyed by Entra ID Object ID (`oid`). Preferences load at session start and write back immediately on user action.

The **Recommended** feed (Discovery tab) is derived from the audit log: tables with recent edit or comment activity are ranked by popularity, with tables the current user has already viewed removed from the list to encourage discovery of genuinely new assets.

### F11 — Accessibility
WCAG 2.0 Level AA compliance on every public page, measured by axe-core. Two known Streamlit-framework violations are explicitly tracked as accepted exceptions; no new violations are permitted on any release.

---

## 5. How it is built — architecture

### Three-component design

```
┌─────────────────┐      ┌──────────────────┐      ┌──────────────┐
│ Streamlit pods  │      │  Sync worker     │      │  Databricks  │
│ (read + enqueue)│      │  (drain + push)  │      │  Unity Cat.  │
│                 │ enq. │                  │ push │              │
│  DuckDB local ◄─┼──────┤   DuckDB local ──┼──────┼─►            │
│   ATTACH RO     │      │   user_data RW   │ pull │              │
└────────┬────────┘      └─────────┬────────┘ ◄────┼──────────────┘
         │                         │   DR resync
         └────  PVC dd-data  ───────┘
              dict.duckdb           (catalog cache, rebuilt nightly)
              dict_user_data.duckdb (overrides, queue, audit, comments)
```

**Component 1 — Nightly sync job (`scripts/nightly_sync.py`)**

Runs as a Kubernetes CronJob every night at 03:00 UTC. Uses the `databricks-sdk` (`WorkspaceClient`) to crawl the Unity Catalog hierarchy (catalogs → schemas → tables → columns → grants → lineage). Writes the results via truncate-and-reload into five cache tables in the local DuckDB file and into `data_governance.dictionary_cache` on Databricks. The local file is replaced atomically (`os.replace`) so in-flight reads are never interrupted.

Cache tables:

| Table | Grain | Purpose |
|---|---|---|
| `tables_metadata` | One row per table | Full-text search, detail view |
| `columns_metadata` | One row per column | Column search, detail view |
| `permissions_cache` | One row per (table, principal, privilege) | Row-level security join |
| `lineage_cache` | One row per lineage edge | Multi-hop lineage panel |
| `object_tags` | One row per (object, tag key) | Glossary domain/steward/calculation |

**Component 2 — Streamlit frontend (`app.py` + `src/`)**

~180-line entry point (`app.py`). All business logic lives in `src/`:

| Module | Responsibility |
|---|---|
| `src/auth.py`, `src/auth_graph.py` | MSAL OIDC flow, group resolution, Graph overage handling |
| `src/db/` | DuckDB adapter, query layer, dialect translation |
| `src/storage/` | Per-entity Protocol-based storage backends (Demo / DuckDB / Fake) |
| `src/ui/cards/` | 7-module UI component package (discovery, health, pipelines, admin, CMS, detail, shared) |
| `src/pages/` | Search page, catalog page |
| `src/sync/` | Sync daemon, push logic, DR resync, worker status helpers |
| `src/personalization.py` | Bookmarks, recents, editing toggle |
| `src/cms.py` | CMS post logic (thin wrapper over `CMSStorage`) |
| `src/pipelines.py` | Pipeline trigger / poll / cancel |

At startup the app:
1. Validates environment (refuses `ENABLE_MOCK_AUTH` outside `ENVIRONMENT=development`)
2. Runs the MSAL OIDC redirect or the mock-auth path
3. Resolves the user's Entra groups (inline claim or Graph fallback)
4. Opens the DuckDB catalog cache and attaches the user-data file
5. Renders the tab-based navigation shell

**Component 3 — Sidecar sync worker (`python -m src.sync.daemon`)**

A standalone process (`dd-sync-worker`, `replicas: 1`, `strategy: Recreate`) that:
- Drains `user_data.pending_sync` — applies each queued metadata change to Unity Catalog (`ALTER TABLE … COMMENT`, audit-log `INSERT`, etc.)
- Runs DR resync every 20 cycles — pulls late-arriving audit and comment rows from Databricks back into the local user_data file
- Recovers stale rows — rows stuck in `'syncing'` for more than 5 minutes flip back to `'pending'`
- Exposes `/healthz` on port 8765 — returns 503 when the heartbeat is more than 60 seconds old; the Kubernetes liveness probe goes red automatically
- Writes its heartbeat timestamp and DR resync status to `user_data.site_settings` so the admin sync panel can display them

The sidecar replaces the previous in-process daemon thread, which corrupted the Streamlit-cached DuckDB connection and ran without a `ScriptRunContext`.

### Storage abstraction layer

`src/storage/` collapses the demo / DuckDB branching that used to be duplicated across four modules into a single, consistent pattern. Each entity has:
- A `Protocol` defining its read/write surface
- A `Demo*Storage` (session state — used in `DEMO_DATA=true` mode)
- A `DuckDB*Storage` (production)
- A `Fake*Storage` (in-memory — used only by unit tests)
- A factory function in `src/storage/__init__.py` that picks the backend at call time

Entities covered: `CMSStorage`, `PipelineDefStorage`, `PipelineRunStorage`, `PreferenceStorage`, `SiteSettingStorage`, `AuditStorage`, `BusinessNameOverrideStorage`.

### Design system

All UI components follow the design system defined in `design_system/README.md`:
- **Colors:** warm paper (`#FAF7F0`), near-black ink (`#14110C`), one accent — oxidized red (`#B8362A`). No hard-coded hex values in code; only CSS variables.
- **Fonts:** Fraunces (headlines), Manrope (body), JetBrains Mono (all Unity Catalog identifiers, counts, SQL).
- **Tone:** sentence case throughout; `§` prefix on section headers; no emoji in the UI.
- **CSS:** injected via `st.markdown('<style>…</style>')` at startup from `src/ui/css.py`. No inline styles.

React JSX prototypes of every screen live in `design_system/ui_kits/app/` and serve as pixel-perfect design targets.

---

## 6. Security model

### Push-down SQL authorization

**No Python-side filtering.** Every query that returns table-level results uses this pattern:

```sql
SELECT t.full_name, t.description, t.table_type
FROM tables_metadata t
JOIN permissions_cache p ON p.full_name = t.full_name
WHERE p.principal IN (%(group_1)s, %(group_2)s, 'SELECT_ALL_USERS')
  AND t.full_name ILIKE %(query)s
GROUP BY t.full_name, t.description, t.table_type
```

Unauthorized rows are discarded by the database engine before any data reaches the application. A bug in Python cannot accidentally expose unauthorized rows. Pagination and row counts are correct from the first query. Every logged SQL statement is self-contained and shows exactly which groups were evaluated — fully auditable. (ADR 002)

### Feature-level access control (three tiers)

| Env var | Grants access to |
|---|---|
| `EDITOR_GROUPS` | Save business name overrides, column definitions, table descriptions |
| `PIPELINE_GROUPS` | Trigger, monitor, and cancel pipeline runs |
| `ADMIN_GROUPS` | Admin dashboard, audit log, CMS management, pipeline definition management, editing toggle, group-cache flush |

Every write function raises `PermissionError` at the function boundary — independent of the UI gate.

### Entra ID groups overage

Microsoft Entra omits the `groups` claim in the ID token when a user belongs to more than ~150 security groups. Without handling, those users see zero tables and receive no error message — a silent production failure.

The app detects this shape (`_claim_names.groups` present, `groups` absent) and calls `POST /v1.0/me/getMemberObjects {"securityEnabledOnly": true}` to retrieve the full transitive list via Microsoft Graph. Results are cached per user OID for 1 hour in a process-level lock-protected dict (not `@st.cache_data`, which is session-scoped and would defeat the purpose). On any Graph failure — network, 4xx, 5xx — the app returns an empty group list and the user sees no tables. We never silently grant access on failure. (ADR 006)

Admins can flush the entire group cache from the admin page. Sign-out clears the individual user's entry so "sign out and sign back in" always reflects current Entra state.

### Additional hardening

- User-supplied display values are HTML-escaped before rendering
- SMTP headers are sanitized to prevent header injection in comment notification emails
- Parameterized queries throughout; `_to_duckdb_sql()` preserves the parameterized pattern across both backends (no string concatenation)
- Kubernetes `NetworkPolicy` restricts egress to HTTPS only and ingress to the ingress controller namespace

---

## 7. When things run — operational cadence

| What | When | Where |
|---|---|---|
| **Catalog rebuild** | Every night at 03:00 UTC | Kubernetes `CronJob` (`dd-sync`); retries up to 2× on failure |
| **Write-back to Databricks** | Every 5 s (active queue) / 30 s (idle) | Sidecar daemon (`dd-sync-worker`), continuous |
| **DR resync (pull)** | Every 20 drain cycles (~100 s active / 600 s idle) | Sidecar daemon, continuous |
| **Stale-row recovery** | Top of every drain cycle | Sidecar daemon; rows in `'syncing'` for >5 min flip back to `'pending'` |
| **Daemon heartbeat** | Every drain cycle | Written to `user_data.site_settings`; liveness probe fails if >60 s stale |
| **Group cache TTL** | 1 hour per user OID | Process-level dict; cleared on sign-out or admin flush |
| **Write retry limit** | 3 attempts per row | Rows that exhaust retries are marked `'failed'`; visible in admin sync panel |

---

## 8. Deployment topology

All components run in the `data-dictionary` Kubernetes namespace.

| Resource | Kind | Notes |
|---|---|---|
| `dd-app` | `Deployment` | Streamlit UI; HPA manages replicas; `PodDisruptionBudget minAvailable: 1`; probes target `/_stcore/health:8501`; `readOnlyRootFilesystem: true` with `/tmp` emptyDir for runtime writes |
| `dd-sync-worker` | `Deployment` | Sidecar daemon; `replicas: 1`, `strategy: Recreate` (single writer); probes target `/healthz:8765`; `readOnlyRootFilesystem: true` with `/tmp` emptyDir |
| `dd-sync` | `CronJob` | Nightly catalog rebuild at 03:00 UTC; `concurrencyPolicy: Forbid`; `backoffLimit: 2` |
| `dd-data` | `PersistentVolumeClaim` | `ReadWriteMany`; mounted at `/data` by all three above; holds both DuckDB files |
| `dd-config` | `ConfigMap` | Non-secret env vars (`DATABRICKS_HOST`, etc.) |
| `dd-secrets` | `Secret` | Credentials (`DATABRICKS_TOKEN`, `CLIENT_SECRET`, etc.) |
| `NetworkPolicy` | `NetworkPolicy` | Ingress from ingress-controller namespace only; egress HTTPS only |
| `ResourceQuota` | `ResourceQuota` | Namespace ceiling: 8 CPU / 8 Gi memory (limits) |

**Local development** — no Kubernetes or Databricks credentials required:
```bash
ENABLE_MOCK_AUTH=true ENVIRONMENT=development DEMO_DATA=true streamlit run app.py
```

The mock-auth path renders a department selector. `DEMO_DATA=true` uses fixture data entirely in memory — no DuckDB file required.

---

## 9. Key architectural decisions

The full rationale for each is in `docs/adr/`.

### ADR 001 — DuckDB as the local metadata cache

**Decision:** Serve all read queries from an embedded DuckDB file rather than routing every request to the Databricks SQL Warehouse over the network.

**Why:** The catalog (~800 tables, ~15 columns each, ~3 000 permission rows) fits comfortably on local disk. DuckDB runs in-process with no server, speaks SQL, and handles the analytical join patterns (GROUP BY, multi-table JOIN, UNION) the app needs. Search queries hit p95 < 8 ms locally versus ~300 ms over the network.

**Trade-off:** Requires a shared `ReadWriteMany` PVC when running multiple Streamlit replicas. The catalog file is replaced atomically by the sync job, so readers always see a consistent snapshot; during the swap window (30–90 s) they continue reading the previous file.

### ADR 002 — Push-down SQL authorization

**Decision:** Enforce permissions via a `JOIN` inside the SQL engine, not by fetching all results and filtering in Python.

**Why:** A Python filter is a single point of failure — one bug exposes unauthorized rows. Push-down SQL means unauthorized rows are mathematically impossible to return. Row counts and pagination are correct from the first query without reading all results first.

### ADR 003 — Streamlit, not FastAPI

**Decision:** Build the UI with Streamlit rather than a separate React/FastAPI stack.

**Why:** The target user base needs a read-mostly, form-driven catalog browser — not a real-time collaborative editor. Streamlit delivers that in one Python process with no client–server API boundary. The trade-off (limited UI flexibility, no server-sent events) is acceptable given the use case. Engineers familiar with Python can maintain the UI without learning a JavaScript framework.

### ADR 004 — Sidecar sync worker

**Decision:** Move the write-back loop out of the Streamlit process into a separate sidecar process.

**Why:** The previous in-process daemon thread shared a Streamlit-cached DuckDB connection with the UI (corrupting concurrent reads), ran without a Streamlit `ScriptRunContext` (undefined behaviour), and tracked UI activity in two diverging state objects. A separate process with its own DuckDB connection and a clear queue-based interface eliminates all three problems. The Streamlit pods are now read-only from Databricks' perspective; the sidecar is the sole intentional writer.

### ADR 005 — Per-entity storage abstraction

**Decision:** Replace ~13 duplicated three-way switches (`demo / DuckDB / Databricks`) across four modules with per-entity Protocol-based backends and factory functions.

**Why:** Each entity had a slightly different exception-handling shape, so a fix to one didn't reach the others. Tests were brittle because they mocked `_duckdb_available` directly. The Protocol pattern makes adding a new entity mechanical (define → implement Demo/DuckDB/Fake → add factory), and tests now inject `Fake*Storage` directly without touching routing internals.

### ADR 006 — Entra ID groups overage handling

**Decision:** Detect the `_claim_names.groups` pointer in the ID token and call Microsoft Graph `getMemberObjects` when the inline `groups` claim is absent.

**Why:** Entra omits the inline groups claim for users with >150 group memberships. Without this handling, those users see zero tables with no error — a silent, invisible production failure that only affects enterprise users (IT admins, partner teams). The Graph fallback is cached per-user for 1 hour, fail-closed on any error, and clears on sign-out.

---

## 10. Non-functional properties

| Property | Target |
|---|---|
| Search latency | p95 < 8 ms (DuckDB local cache, 800-table dataset) |
| Page shell latency | p95 HTTP < 20 ms |
| Concurrent users | 300 authenticated users, no failures, within latency targets (load-tested baseline) |
| Authentication | Microsoft Entra ID OIDC only. No local accounts. No password storage. |
| Data at rest | DuckDB files on a PVC; user-data file holds personalisation, audit log, comments, overrides, pipeline definitions |
| Databricks down | Reads continue from local cache; writes queue locally and retry when connectivity returns |
| SMTP down | Comments still save; only the notification email is lost |
| Graph API down | Users with overage tokens see no tables (fail-closed — never silently grants access) |
| Audit retention | Audit log is append-only; no hard delete from the UI |
| Languages | English and French at parity; other locales are not in scope |
| Compliance | No PII stored beyond what Entra (name, email, OID) and Unity Catalog (steward email) already provide. Every metadata change carries actor, timestamp, and before/after values; the daemon mirrors entries to Databricks for tamper resistance. |

---

## 11. Out of scope

- DDL changes or `GRANT` modifications to Unity Catalog from this app — metadata editing only.
- Replacement for the data-engineering Databricks UX — engineers use Databricks for schema work, lineage debugging, cluster config.
- Self-service permission requests — access requests go through the existing IT-ticketing flow.
- Free-form SQL execution — the data preview is a fixed top-100 read.
- Data quality enforcement — the health dashboard surfaces metrics from other systems; it does not run checks itself.
- Real-time collaborative editing — no live cursors, no row-level locking.
- Mobile web layout — target is desktop / large tablet.
- Multi-tenant deployment — one install per environment, one Entra tenant.

---

## 12. Success metrics

| Metric | Target |
|---|---|
| Search adoption | ≥ 70 % of authenticated weekly users execute at least one search per session (90-day rolling) |
| Steward edits | ≥ 10 business-name overrides created per week across all stewards |
| Mean time to find a table | < 2 minutes from sign-in to detail view (replaces the ~hours "ask a data engineer in Slack" baseline) |
| Audit completeness | 100 % of catalog edits map to an audit-log row produced by this app (sampled monthly) |
| Accessibility | Zero new WCAG 2.0 AA violations beyond the two known Streamlit framework issues, on every release |

---

*Generated from the codebase, ADRs, and business requirements document using the knowledge-base + Gemini digest workflow — 2026-05-13.*
