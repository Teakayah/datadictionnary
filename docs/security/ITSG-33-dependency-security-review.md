# ITSG-33 dependency security review — Business Data Dictionary

**System:** Business Data Dictionary for Databricks Unity Catalog
**Prepared by:** Nicolas Leclerc
**Date:** 2026-06-25
**Standard:** CSE *IT Security Risk Management: A Lifecycle Approach* (ITSG-33), Annex 3A — Security Control Catalogue (maps to NIST SP 800-53)
**Classification of this document:** To be determined by the Departmental Security Officer / IT Security team

---

## 1. Purpose and scope

This report supports an ITSG-33-aligned security assessment of the **third-party software dependencies** required to build, run, and test the Business Data Dictionary application. It provides:

- A Software Bill of Materials (SBOM) of all production and development dependencies.
- A mapping of the dependency-management posture to the relevant ITSG-33 / NIST 800-53 control families.
- A per-dependency supply-chain and licensing assessment.
- Recommended evidence and actions for the assessor to complete the authorization (security assessment & authorization, **CA** family) activity.

> **Scope note.** This review covers software components (`SA`, `CM`, `SI`, `RA` families). It does **not** by itself constitute the full system security assessment — operational controls (`AC`, `AU`, `IA`, `SC`, `CP`, `IR`, etc.) are implemented in the application and infrastructure and are documented separately. References to those families below indicate *where a dependency contributes to* a control, not that the control is fully evidenced here.

---

## 2. System security categorization (to be confirmed by IT Security)

ITSG-33 risk management begins with categorizing the information system by the expected **injury level** (Low / Medium / High) for each security objective. This drives the applicable control profile (e.g. PBMM — Protected B, Medium integrity, Medium availability).

| Security objective | Preliminary characterization | Rationale |
|---|---|---|
| Confidentiality | **Medium (Protected B candidate)** | Exposes Unity Catalog metadata (table/column names, descriptions, business definitions) filtered by Entra ID group membership. No raw business data is stored by the app; the optional Preview tab reads live rows under the caller's permissions. |
| Integrity | **Medium** | Users with editor rights can write business-friendly names/definitions; all writes are audit-logged and pushed back to Unity Catalog via a controlled sidecar. |
| Availability | **Low–Medium** | Internal reference tool; an outage degrades discovery but does not halt a business-critical transaction path. |

**Recommended profile:** Validate against the **PBMM** (Protected B / Medium / Medium) control profile in ITSG-33 Annex 4A. Confirm with the DSO before finalizing the control selection.

---

## 3. Methodology

1. **Inventory (CM-8).** Enumerate all declared dependencies from `requirements.txt` (runtime) and `requirements-dev.txt` (development/test). Dev dependencies are excluded from the production container image (`Dockerfile`, multi-stage build) and are flagged accordingly.
2. **Provenance (SA-12).** Identify the upstream source and distribution channel (all via PyPI / `pip`).
3. **Licensing (SA-4 / legal).** Record the open-source license for each component.
4. **Vulnerability posture (RA-5 / SI-2).** Identify the scanning tooling and where current results must be attached. *No CVE results are asserted in this document — they are produced by a live scan at assessment time (see §7).*
5. **Control mapping (CA-2).** Map the dependency-management practices to ITSG-33 control families.

---

## 4. Runtime environment

| Component | Version | Source | Notes |
|---|---|---|---|
| Python | 3.11 | `python:3.11-slim` (official Docker image) | Supported release; security-patched by upstream. Pinned in `Dockerfile` and CI (`.github/workflows/deploy.yml`). |
| Container base image | `python:3.11-slim` (Debian slim) | Docker Hub / official image | Multi-stage build; final image runs as **non-root** UID/GID 1000. Build-only toolchain (`gcc`, `g++`, `libffi-dev`) is excluded from the final image. |
| Package installer | `pip` | PyPI | Dependencies pinned to compatible ranges; recommend hash-pinning for High profiles (see §7). |

---

## 5. Software Bill of Materials (SBOM)

### 5.1 Production dependencies (`requirements.txt`)

| # | Package | Pinned range | License* | Upstream maintainer | Function in system | Security relevance |
|---|---|---|---|---|---|---|
| 1 | `streamlit` | `>=1.50,<2` | Apache-2.0 | Snowflake / Streamlit | Web UI framework; renders all pages over WebSocket | Network-facing surface (**SC-8**); session management (**AC-12**) |
| 2 | `databricks-sql-connector` | `>=4.2,<5` | Apache-2.0 | Databricks | SQL Warehouse connectivity | Data-in-transit to backend (**SC-8/SC-13**) |
| 3 | `databricks-sdk` | `>=0.100,<1` | Apache-2.0 | Databricks | Unity Catalog metadata crawl | Privileged backend access (**AC-6**) |
| 4 | `msal` | `>=1.30,<2` | MIT | Microsoft | Entra ID OIDC authentication | Core to **IA-2 / IA-8** (identification & authentication) |
| 5 | `pandas` | `>=2.2,<3` | BSD-3-Clause | NumFOCUS / community | In-memory data handling | Processes query results; no direct external surface |
| 6 | `python-dotenv` | `>=1.0,<2` | BSD-3-Clause | community | Loads configuration/secrets from env | Secrets handling (**IA-5 / CM-6**) — ensure `.env` excluded from images/VCS |
| 7 | `duckdb` | `>=1.0,<2` | MIT | DuckDB Foundation | Local metadata cache + VSS search | Local data-at-rest (**SC-28**) |
| 8 | `streamlit-js-eval` | `>=1.0,<2` | MIT | community (single-maintainer) | Reads browser viewport via JS eval | Executes JS in client; **review for lower-trust provenance** (see §6) |
| 9 | `streamlit-autorefresh` | `>=1.0,<2` | MIT | community (single-maintainer) | Non-blocking periodic UI refresh | Client-side timer; low risk; **single-maintainer** flag (§6) |
| 10 | `requests` | `>=2.32,<3` | Apache-2.0 | Python Software Foundation | Outbound HTTP (pipelines integration) | External calls (**SC-7 / AC-4**) |
| 11 | `fastapi` | `>=0.115,<1` | MIT | community (Sebastián Ramírez) | REST API framework | Network-facing API surface (**SC-7/SC-8**) |
| 12 | `uvicorn[standard]` | `>=0.30,<1` | BSD-3-Clause | community (Encode) | ASGI server for the API | Network listener (**SC-7**) |
| 13 | `mcp` | `>=1.9` | MIT | Anthropic / MCP project | MCP server SDK | Network-facing surface; **unbounded upper version — see §7** |
| 14 | `redis` (redis-py) | `>=5.0,<6` | MIT | Redis / community | Cache client (sync + async) | Connection to cache (**SC-8**); ensure auth/TLS on Redis |
| 15 | `python-jose[cryptography]` | `>=3.3,<4` | MIT | community | Entra ID JWT (RS256) validation | **Cryptographic verification of tokens (SC-13 / IA-2)** — security-critical; see §6 |
| 16 | `httpx` | `>=0.27,<1` | BSD-3-Clause | community (Encode) | Async HTTP for JWKS + Graph API | External calls (**SC-7/SC-8**) |

### 5.2 Development & test dependencies (`requirements-dev.txt`) — *not shipped in production image*

| # | Package | Pinned range | License* | Function |
|---|---|---|---|---|
| 17 | `pytest` | `>=8.0` | MIT | Unit/integration test framework |
| 18 | `pytest-cov` | `>=5.0` | MIT | Test coverage reporting |
| 19 | `locust` | `>=2.29` | MIT | Load/performance testing |
| 20 | `faker` | `>=26.0` | MIT | Synthetic test-data generation |
| 21 | `playwright` | `>=1.44` | Apache-2.0 | Browser automation for E2E/accessibility tests |
| 22 | `axe-playwright-python` | `>=0.1.3` | MIT (bundles **axe-core, MPL-2.0**) | WCAG accessibility checks — **note MPL-2.0 sub-component** |
| 23 | `python-pptx` | `>=1.0` | MIT | Generates reporting decks |

\* **Licenses are stated to the best of available knowledge and MUST be independently verified** by an automated license scan (e.g. `pip-licenses`) as part of this assessment. Treat the license column as a starting point, not authoritative legal record. Note in particular: `axe-playwright-python` bundles **axe-core**, which is **MPL-2.0** (weak copyleft) — confirm this is acceptable under departmental open-source policy even though it is dev-only.

---

## 6. Supply-chain risk highlights (SA-12, SA-15)

Items the assessor should weigh during the supply-chain protection review:

| Component(s) | Risk factor | Recommended treatment |
|---|---|---|
| `python-jose` | Performs **security-critical JWT signature validation**. The library has had historical CVEs (algorithm-confusion / DoS class issues in the broader JOSE ecosystem). | Confirm installed version is patched; pin to a known-good version; subscribe to advisories. Consider `PyJWT` as an alternative if the assessor prefers a more actively maintained validator. |
| `streamlit-js-eval`, `streamlit-autorefresh` | **Single-maintainer community components.** Lower bus-factor and slower patch cadence than foundation-backed packages. | Pin exact versions; vendor/mirror to an internal index; document a removal/replacement plan if unmaintained. Both are low-privilege client-side helpers, limiting blast radius. |
| `mcp` | Declared as `>=1.9` with **no upper bound** — a future breaking/compromised release could be pulled in. | Add an upper bound (e.g. `>=1.9,<2`) and hash-pin. |
| `databricks-sdk` | Holds **privileged** Unity Catalog crawl credentials. | Ensure least-privilege service principal (**AC-6**); rotate tokens; scope to read-only catalog metadata where possible. |
| All packages | Installed from public **PyPI**. | For Medium/High profiles, install from a **vetted internal mirror** (Artifactory/Azure Artifacts) and enable `pip install --require-hashes`. |
| Container base image | `python:3.11-slim` pulled from Docker Hub. | Pull from an approved internal registry; scan image (Trivy/Defender for Cloud); pin by digest. |

---

## 7. Vulnerability management (RA-5, SI-2)

### 7.1 Scan executed

A vulnerability scan was run with **`pip-audit` 2.10.1** against the resolved virtual environment (direct **and** transitive packages) on **2026-06-25**. Tooling: `pip-audit` (CVE/GHSA), `pip-licenses` (license inventory).

```bash
pip-audit                 # scans the installed/resolved environment incl. transitive deps
pip-licenses --format=markdown --with-urls
```

**Result: 7 known vulnerabilities across 6 packages. Every finding is in a _transitive_ dependency — none of the 16 directly-pinned production packages in `requirements.txt` carries a known CVE at its installed version.** All findings have a fix version available (no zero-days without a patch).

### 7.2 Findings and remediation

| Vulnerable pkg | Installed | Severity (class) | ID | Pulled in by (direct dep) | Shipped in prod image? | Fix version | Recommended action |
|---|---|---|---|---|---|---|---|
| `starlette` | 1.2.1 | **High** (DoS — urlencoded form limits not enforced) | CVE-2026-54283 | `fastapi`, `mcp`, `streamlit` | Yes | **1.3.1** | Pin `starlette>=1.3.1` (constraints file); re-resolve |
| `starlette` | 1.2.1 | Medium (URL authority parsing / host spoofing) | CVE-2026-54282 | `fastapi`, `mcp`, `streamlit` | Yes | 1.3.0 | Covered by the same `>=1.3.1` pin above |
| `cryptography` | 48.0.0 | Medium (bundled OpenSSL advisory, statically-linked wheels) | GHSA-537c-gmf6-5ccf | `msal`, `google-auth` | Yes | **48.0.1** | Pin `cryptography>=48.0.1`; trivial patch bump |
| `pydantic-settings` | 2.14.1 | Medium (symlink escape → out-of-tree secret read, size-cap bypass) | GHSA-4xgf-cpjx-pc3j | `mcp` | Yes | 2.14.2 | Pin `pydantic-settings>=2.14.2`. **Not exploitable as used** — app does not use `NestedSecretsSettingsSource` with `secrets_nested_subdir`; patch anyway |
| `python-multipart` | 0.0.30 | Low (negative `Content-Length` → unbounded read) | CVE-2026-53540 | `mcp`, `streamlit` | Yes | 0.0.31 | Pin `python-multipart>=0.0.31`. **Not exploitable as used** — advisory confirms Starlette/FastAPI drive the parser directly and are unaffected |
| `msgpack` | 1.1.2 | Low (SEGV/DoS on Unpacker reuse after error) | GHSA-6v7p-g79w-8964 | `locust` (dev), `CacheControl` | **No (dev/build only)** | 1.2.1 | Bump in dev set; not in production image — lower priority |
| `pip` | 26.1.1 | Low (entry-point path traversal on install) | PYSEC-2026-196 | build tooling | **No (not a runtime dep)** | 26.1.2 | Upgrade `pip` in the build image; not shipped |

### 7.3 Remediation approach (recommended)

Because all findings are transitive, the cleanest fix is a **constraints file** that floors the vulnerable sub-dependencies without disturbing the curated top-level pins in `requirements.txt`:

```text
# constraints.txt — security floors for transitive dependencies (ITSG-33 SI-2)
starlette>=1.3.1
cryptography>=48.0.1
pydantic-settings>=2.14.2
python-multipart>=0.0.31
msgpack>=1.2.1
```

```bash
pip install -r requirements.txt -c constraints.txt
pip install --upgrade pip          # build image → pip>=26.1.2
pip-audit                          # re-run: expect 0 findings in the production set
```

After applying, re-run `pip-audit` and attach the clean result as the **SI-2 closure evidence**.

### 7.4 License scan result (SA-4 / legal)

`pip-licenses` confirmed the §5 inventory with two items requiring follow-up:

- **`streamlit-autorefresh` and `streamlit-js-eval` publish no license metadata** (`License: UNKNOWN`). Both are MIT per their GitHub `LICENSE` files, but the package metadata does not assert it. **Action:** confirm the license from each repository's `LICENSE` file and record it manually; do not rely on metadata.
- **MPL-2.0 (weak copyleft) components present:** `certifi` and `bidict` (both transitive, ubiquitous, MPL-2.0), plus **`axe-core`** bundled inside the dev-only `axe-playwright-python`. No GPL/LGPL/AGPL components were found. **Action:** confirm MPL-2.0 is acceptable under the departmental open-source policy (it generally is for unmodified library use); none are modified or statically combined.

### 7.5 Ongoing controls to evidence

- **SI-2 (Flaw remediation):** enable Dependabot / Renovate on the repo; define a patch SLA (e.g. Critical ≤ 7 days, High ≤ 30 days).
- **RA-5 (Vulnerability scanning):** wire `pip-audit` + a container image scan (Trivy/Defender for Cloud) into CI (`.github/workflows/`); fail the build on Critical/High.
- **CM-2 / CM-6 (Baseline):** keep top-level pins; add the §7.3 constraints file; for Medium/High profiles add `--require-hashes` + an internal PyPI mirror.
- **SA-22 (Unsupported components):** no end-of-life components found; Python 3.11 is supported.
- **Records:** generate a CycloneDX SBOM for the authorization package: `cyclonedx-py requirements -i requirements.txt -o sbom.json`.

---

## 7A. Mitigation plan for design / supply-chain risks (§6)

These are the structural risks from §6 (not CVEs). Each has a concrete mitigation and the ITSG-33 control it satisfies.

| # | Risk | Mitigation | Control |
|---|---|---|---|
| 1 | **`python-jose` performs security-critical JWT validation** and the JOSE ecosystem has a CVE history. | (a) Keep pinned to a patched version (installed 3.5.0 — currently clean per §7). (b) **Explicitly pin the accepted algorithm to `RS256`** in the verify call and reject `alg=none`/HS\* to defeat algorithm-confusion. (c) Validate `iss`, `aud`, `exp` on every token. (d) Track an exit option to `PyJWT` (more active maintenance) and record the decision. | IA-2, SC-13 |
| 2 | **`mcp` pinned `>=1.9` with no upper bound** — a future bad release could be pulled. | Change the pin to `mcp>=1.9,<2` (or pin the exact tested version) and add hash-pinning. | CM-2, SA-12 |
| 3 | **Single-maintainer components** (`streamlit-js-eval`, `streamlit-autorefresh`) with no license metadata and low bus-factor. | (a) Pin exact versions. (b) Mirror/vendor to the internal package index so availability does not depend on the upstream account. (c) Confirm + record license from repo. (d) Both are low-privilege client-side helpers — document a removal path (the viewport read and the refresh timer can be replaced with native Streamlit features if either goes unmaintained). | SA-12, SA-15, CM-7 |
| 4 | **`databricks-sdk` holds privileged Unity Catalog crawl credentials.** | (a) Use a dedicated service principal scoped to **read-only** catalog/metadata (`USE CATALOG`/`USE SCHEMA`/`SELECT` on metadata only), not workspace admin. (b) Store the token in a secret store (Key Vault), not `.env`, in production. (c) Rotate on a schedule; audit usage. | AC-6, IA-5 |
| 5 | **All packages installed from public PyPI.** | For the target profile, install from a **vetted internal mirror** (Azure Artifacts/Artifactory) and enable `pip install --require-hashes` with a generated hash lockfile. | SA-12, CM-6 |
| 6 | **Base image pulled from Docker Hub.** | Mirror `python:3.11-slim` to an approved internal registry, **pin by digest** (not just tag), and scan on every build. | CM-2, SA-12, RA-5 |
| 7 | **Secrets via `.env` / `python-dotenv`.** | `.env` is for local dev only — ensure it is git-ignored and excluded from the image (verify `.dockerignore`). In production, inject secrets from Key Vault / orchestrator secrets, not a file. | IA-5, CM-6 |
| 8 | **Redis cache connection** (`redis-py`). | Require **AUTH + TLS** on the Redis endpoint; do not expose it publicly; segment on a private subnet. The app already supports running cache-less if Redis is unavailable (fail-safe). | SC-8, SC-7 |

---

## 8. ITSG-33 control family mapping (summary)

| Family | Control(s) | How the dependency posture contributes | Status / evidence needed |
|---|---|---|---|
| **CM — Configuration Management** | CM-2, CM-6, CM-7, CM-8, CM-10, CM-11 | Pinned `requirements*.txt`; multi-stage Dockerfile enforces least functionality (build tools excluded); SBOM in §5 | Attach generated SBOM; add hash-pinning |
| **SA — System & Services Acquisition** | SA-4, SA-12, SA-15, SA-22 | Provenance (PyPI), licensing (§5), supply-chain notes (§6) | Internal mirror; supply-chain sign-off |
| **RA — Risk Assessment** | RA-5 | Scan tooling defined (§7) | Attach `pip-audit` + image scan output |
| **SI — System & Information Integrity** | SI-2, SI-3, SI-7 | Patch process; container scanning | Evidence of CI scanning + patch SLA |
| **IA — Identification & Authentication** | IA-2, IA-5, IA-8 | `msal`, `python-jose` implement Entra ID OIDC/JWT | Verify token-validation config & secret handling |
| **SC — System & Communications Protection** | SC-7, SC-8, SC-13, SC-28 | TLS to Databricks/Redis/Graph; local DuckDB at rest | Confirm TLS enforced; Redis auth/TLS; disk encryption |
| **AC — Access Control** | AC-4, AC-6, AC-12 | Push-down SQL permission filter; least-privilege SP | Reference app security model (ADR 002) |
| **AU — Audit & Accountability** | AU-2, AU-3 | Application audit log of metadata edits | Reference app audit design |

---

## 9. Assessor checklist

- [ ] Confirm system security categorization / control profile (§2).
- [x] Run `pip-audit` against the resolved environment — **done 2026-06-25: 7 findings, all transitive, all with fixes (§7.2)**.
- [ ] Apply the §7.3 constraints file and re-run `pip-audit`; attach the clean result as SI-2 closure evidence.
- [ ] Run and attach container image scan (base image + OS packages).
- [x] Validate license inventory with `pip-licenses` — **done (§7.4)**; confirm MPL-2.0 acceptance and resolve the two `UNKNOWN` license-metadata packages from their repos.
- [ ] Decide on internal PyPI mirror + hash-pinning for the target profile (§7A-5).
- [ ] Add upper version bound to `mcp` and exact pins for single-maintainer components (§7A-2/3).
- [ ] Pin JWT algorithm to `RS256` and review `python-jose` vs `PyJWT` (§7A-1).
- [ ] Confirm least-privilege service principal scope for `databricks-sdk` crawl (§7A-4).
- [ ] Record residual risks and obtain authorization decision (CA-6).

---

## 10. Statement of accuracy

The dependency inventory (§4–§5) is drawn directly from the repository's `requirements.txt`, `requirements-dev.txt`, and `Dockerfile` as of the date above and is factual. The vulnerability findings in §7.2 are the **actual output of `pip-audit` 2.10.1** run against the resolved virtual environment on 2026-06-25; the license results in §7.4 are the actual output of `pip-licenses`. Severity *class* labels are the assessor's characterization for prioritization and should be reconciled against the official CVSS scores in each advisory. The container image scan (§7.5) has **not** yet been run and must be produced before authorization.
