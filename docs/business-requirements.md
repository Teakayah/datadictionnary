# Business requirements

The "what" and the "why" of the Data Dictionary, distinct from the
"how" that's covered in [`ARCHITECTURE.md`](../ARCHITECTURE.md) and the
ADRs. Update this document whenever a stakeholder conversation
reframes scope, success criteria, or non-goals.

---

## Problem statement

Non-technical staff at the organisation cannot reliably find or
understand the data assets they have access to in Databricks Unity
Catalog. The native Unity Catalog UI is engineering-oriented: it
exposes physical schema, internal IDs, and admin-flavoured surfaces
that make routine business questions ("which table holds approved
invoices?", "who is the steward of this column?") expensive to
answer. The result today is a tax of repeated #ask-data Slack
threads, duplicated reports, and shadow data dictionaries
maintained in spreadsheets.

We need a single, search-first, **business-language** view of the
catalog that:

1. Exposes only the data the user is **already entitled to see**
   (Entra ID + Unity Catalog grants). No new permission model.
2. Lets non-technical users discover, understand, and reference
   tables and columns without writing SQL or talking to data
   engineering.
3. Lets data stewards keep business definitions current
   without raising a ticket against the data platform team.

---

## Personas

| Persona | Profile | Primary needs |
| -- | -- | -- |
| **Business analyst** | Finance / HR / Research / IT operations. SQL-aware but rarely writes it. Owns reports and dashboards. | Find the right table fast; understand columns in business terms; preview a sample of rows; export schema for a brief. |
| **Data steward** | Domain SME (e.g. Finance Controller). Owns the business meaning of the data; not a developer. | Curate business names, definitions, comments. See what's been changed and by whom. |
| **Data engineer / platform admin** | Maintains the catalog and the pipelines that feed it. | Trigger / monitor pipelines; check sync queue; flush group caches; audit edits. |
| **Compliance / audit** | Reads the audit log. Cares about who saw or edited what. | Trustworthy, tamper-resistant audit trail. |
| **Read-only consumer** | Most logged-in users. May only see the discovery and search tabs. | Discover relevant tables; bookmark; receive announcements. |

---

## Functional requirements

### F1 — Search & discovery
- **F1.1** Full-text search across catalogs, schemas, table names,
  column names, table descriptions, column descriptions, and
  business-glossary terms, returning ranked results in <500 ms p95
  on the production dataset.
- **F1.2** Discovery tab with three sub-tabs: notable (recent updates
  scoped to the user's primary group), bookmarks, recents.
- **F1.3** CMS banner: admin-authored announcements / featured tables
  / guides that appear above the discovery sub-tabs and expire
  after a chosen window (2 days / 7 days / 30 days / never).

### F2 — Permission-trimmed visibility
- **F2.1** A user must see only catalogs / schemas / tables their
  Entra ID groups are granted on (via Unity Catalog `GRANT` rows in
  `permissions_cache`).
- **F2.2** The sentinel principal `SELECT_ALL_USERS` marks
  publicly-accessible tables; these appear for every authenticated
  user.
- **F2.3** Permission filtering happens **inside** the SQL engine, not
  in Python. (Architectural — see ADR 002.)
- **F2.4** Group membership is taken from the ID token's `groups`
  claim. For users in 150+ groups (Entra overage), it's resolved
  via Microsoft Graph — see ADR 006.

### F3 — Table detail
- **F3.1** Per-table view showing: catalog/schema/table identifier
  (monospace), description, steward, columns (name + type + comment
  + business name override + definition override), grants, lineage
  (multi-hop), data-quality grade if available, and bookmarked-
  column ★ toggle.
- **F3.2** Sample data preview (top 100 rows) for tables the user
  has SELECT on. Skipped silently otherwise.
- **F3.3** Schema export to CSV (filename
  `{catalog}_{schema}_{table}_schema.csv`) including business
  names + definitions when present.

### F4 — Inline editing
- **F4.1** Power users (members of `EDITOR_GROUPS`) can edit:
  table description, table steward, column business name, column
  definition. Length caps: 255 chars for names, 2000 chars for
  definitions.
- **F4.2** Edits are written locally immediately and queued for
  push to Unity Catalog by the sidecar sync worker. The user must
  not have to wait for the Databricks round-trip.
- **F4.3** Every edit produces an audit-log entry attributable to
  the actor. The full log is visible to admins.
- **F4.4** Editing can be globally turned off by an admin (e.g.
  during a data migration or audit) without redeploying.

### F5 — Comments
- **F5.1** Any authenticated user can leave a question / flag on a
  table or column (≤1000 chars). Replies are threaded one level
  deep.
- **F5.2** New comments and replies trigger an email notification
  (when SMTP is configured) to the table steward; failure to
  send must not block the comment from being saved.

### F6 — Health dashboard
- **F6.1** Catalog-wide coverage metrics: % tables with
  description, % columns with description, freshness grade, and a
  per-schema breakdown.
- **F6.2** "Priority actions" panel listing up to 5 undocumented
  tables, deep-linkable to the detail view.

### F7 — Pipelines
- **F7.1** Members of `PIPELINE_GROUPS` (and admins) can trigger,
  monitor, and cancel parameter-less runs of named pipelines. Three
  backends supported today: Databricks Jobs, Azure Data Factory,
  Azure DevOps Pipelines.
- **F7.2** One active run per pipeline at a time. Live progress
  while the run is in flight.

### F8 — Admin
- **F8.1** Admin-only dashboard listing catalog stats, sync-queue
  status, audit log, comment log, CMS post CRUD, pipeline-
  definition CRUD, editing toggle, group-cache flush.
- **F8.2** Server-side authorisation re-check on every write
  (defence-in-depth alongside the UI gate).

### F9 — Internationalisation
- **F9.1** UI in English and French. Auto-detect from
  `Accept-Language`; user can override via header toggle. Persists
  for the session.

### F10 — Personalisation
- **F10.1** Per-user bookmarks (tables + columns) and recently
  viewed tables, persisted across sessions, keyed by Entra ID OID.

### F11 — Accessibility
- **F11.1** WCAG 2.0 Level AA compliance on every public page,
  measured by axe-core. Documented exceptions (today: two known
  Streamlit-framework violations) are explicitly tracked.

---

## Non-functional requirements

| | |
| -- | -- |
| **Latency** | p95 search query <8 ms on the local DuckDB cache (800-table dataset). p95 page-shell HTTP <20 ms. |
| **Concurrency** | 300 concurrent authenticated users with no failures and within the latency targets above (load-tested baseline). |
| **Auth** | Microsoft Entra ID OIDC. No local accounts. No password storage. |
| **Data-at-rest** | DuckDB cache files live on a PersistentVolumeClaim; user-data file holds personalisation, audit log, comments, overrides, pipeline definitions. |
| **Sync cadence** | Catalog rebuild nightly. Write-back to Databricks via sidecar daemon, drained every 5–30 s. |
| **Failure modes** | Databricks down → reads continue from local cache; writes queue up and retry. SMTP down → comments still save. Graph down → users with overage tokens see no tables (fail-closed). |
| **Audit retention** | Audit log is append-only. No hard delete from the UI. Operators can purge from the database directly if compliance requires. |
| **Languages** | English and French at parity. Other locales are not in scope. |

---

## Out of scope

- Catalog **editing** in Unity Catalog beyond the metadata fields
  listed in F4 (no DDL, no GRANT changes from this app).
- Replacement for the data-engineering catalog UX. Engineers should
  continue to use Databricks for schema work, lineage debugging,
  cluster config, etc.
- Self-service permission requests. The user sees what their groups
  allow; requests for more access happen in the existing IT-ticketing
  flow.
- Free-form SQL execution. The "data preview" is a fixed top-100
  read; arbitrary queries are not supported.
- Data quality enforcement. The health dashboard surfaces metrics
  produced by other systems; it does not run quality checks itself.
- Real-time collaboration on edits (no live cursors, no row-level
  locking).
- Mobile web layout. Target is desktop / large tablet.

---

## Success metrics

| | |
| -- | -- |
| **Search adoption** | ≥70 % of authenticated weekly users execute at least one search per session (90-day rolling). |
| **Steward edits** | ≥10 business-name overrides created per week across all stewards. |
| **Mean time to find a table** | <2 minutes from sign-in to detail view (instrumented). Replaces the prior "ask a data engineer in Slack" baseline of ~hours. |
| **Audit completeness** | 100 % of edits in the catalog map to an audit-log row produced by this app (sampled monthly). |
| **Accessibility** | Zero new WCAG 2.0 AA violations beyond the two known Streamlit framework issues, on every release. |

---

## Constraints & assumptions

- Entra ID is the source of truth for identity. Users without an
  Entra account cannot use the app.
- Unity Catalog grants are the source of truth for authorisation.
  This app reflects them; it does not amend them.
- The DuckDB local-cache architecture (ADR 001) presumes the
  catalog fits comfortably on local disk. The 800-table reference
  dataset is well under 100 MB. Catalogs in the 100k+ table range
  would force a re-evaluation.
- Sync to Databricks is best-effort with retries (3 attempts
  before parking a row as `failed`). A persistent Databricks
  outage means edits queue locally; users see them, but the
  upstream catalog is stale until the daemon recovers.
- Single-tenant deployment per environment. Multi-tenant (one
  install serving multiple business units with isolated data) is
  not in scope.

---

## Compliance posture

- **Data minimisation** — the app stores no PII it didn't already
  receive from Entra (name, email, OID) or Unity Catalog (steward
  email).
- **Auditability** — every metadata change carries actor email,
  timestamp, before/after values; the daemon mirrors the entry to
  the Databricks `audit_log` for tamper resistance and long-term
  retention.
- **Least privilege** — three layered group sets: `EDITOR_GROUPS`,
  `PIPELINE_GROUPS`, `ADMIN_GROUPS`. No demo bypass for admin.
- **Network segmentation** — the Streamlit pods and the sync-worker
  pod are restricted by NetworkPolicy to talking to the ingress
  controller, the SQL Warehouse, the Graph API, and the pipeline
  control planes.

---

## Change log

| Date | Change | Driver |
| -- | -- | -- |
| 2026-05-08 | Initial document | Stakeholder request: "what were the business requirements?" |
