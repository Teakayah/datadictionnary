# ITSG-33 dependency security review — API gateway (FastAPI + Redis + Entra ID)

**System:** API gateway for an external system (FastAPI gateway, Redis cache, Entra ID authentication — user OIDC + service-principal client-credentials)
**Prepared by:** Nicolas Leclerc
**Date:** 2026-06-25
**Standard:** CSE *IT Security Risk Management: A Lifecycle Approach* (ITSG-33), Annex 3A — Security Control Catalogue (maps to NIST SP 800-53)
**Classification of this document:** To be determined by the Departmental Security Officer / IT Security team

> **Prefill status.** This is a **template prefilled for the stack**, not yet grounded in a live repository scan. Sections §4–§5 list the *expected* dependencies for a FastAPI + Redis + Entra-ID gateway — reconcile each row against the project's actual `requirements.txt` before assessment. Section §7 is a **ready-to-run scan procedure**: the CVE/license findings tables are placeholders to be populated by the live `pip-audit` / `pip-licenses` run. Do **not** treat any version pins or "fix versions" here as authoritative until the scan is executed.

---

## 1. Purpose and scope

This report supports an ITSG-33-aligned security assessment of the **third-party software dependencies** required to build, run, and test the API gateway. It provides:

- A Software Bill of Materials (SBOM) of all production and development dependencies.
- A mapping of the dependency-management posture to the relevant ITSG-33 / NIST 800-53 control families, with emphasis on the **identity/token-validation (IA)** and **boundary-protection (SC)** roles a gateway plays.
- A per-dependency supply-chain and licensing assessment.
- Recommended evidence and actions for the assessor to complete the authorization (security assessment & authorization, **CA** family) activity.

> **Scope note.** This review covers software components (`SA`, `CM`, `SI`, `RA` families). It does **not** by itself constitute the full system security assessment — operational controls (`AC`, `AU`, `IA`, `SC`, `CP`, `IR`, etc.) are implemented in the gateway and infrastructure and are documented separately. References to those families below indicate *where a dependency contributes to* a control, not that the control is fully evidenced here. **A gateway is a security-enforcing component** — its IA/AC/SC controls are central, not peripheral, so the assessor should treat §6/§7A with particular care.

---

## 2. System security categorization (to be confirmed by IT Security)

ITSG-33 risk management begins with categorizing the information system by the expected **injury level** (Low / Medium / High) for each security objective. This drives the applicable control profile (e.g. PBMM — Protected B, Medium integrity, Medium availability).

| Security objective | Preliminary characterization | Rationale |
|---|---|---|
| Confidentiality | **To confirm — likely Medium (Protected B candidate)** | The gateway brokers requests to a backend system and **caches responses in Redis**. Categorization is driven by the sensitivity of the proxied data and of anything cached. Tokens and authorization decisions also pass through. |
| Integrity | **Medium–High** | As a security-enforcing boundary, the gateway's correctness *is* an integrity control: a flaw in token validation or request routing can grant unauthorized access. Cache-poisoning is an integrity risk. |
| Availability | **Medium–High** | A gateway is a **single chokepoint** in front of the backend — its outage takes the protected system offline. Categorize per the most availability-sensitive consumer. |

**Recommended profile:** Validate against the **PBMM** (Protected B / Medium / Medium) control profile in ITSG-33 Annex 4A — consider higher Integrity/Availability given the gateway's enforcement and chokepoint roles. Confirm with the DSO before finalizing the control selection.

---

## 3. Methodology

1. **Inventory (CM-8).** Enumerate all declared dependencies from `requirements.txt` (runtime) and `requirements-dev.txt` (development/test). Dev dependencies are excluded from the production container image and flagged accordingly.
2. **Provenance (SA-12).** Identify the upstream source and distribution channel (all via PyPI / `pip`).
3. **Licensing (SA-4 / legal).** Record the open-source license for each component.
4. **Vulnerability posture (RA-5 / SI-2).** Define the scanning tooling and where current results must be attached. *No CVE results are asserted in this document — they are produced by a live scan at assessment time (see §7).*
5. **Control mapping (CA-2).** Map the dependency-management practices to ITSG-33 control families.

---

## 4. Runtime environment

| Component | Version | Source | Notes |
|---|---|---|---|
| Python | 3.11 (confirm) | `python:3.11-slim` (official Docker image) | Supported release; security-patched by upstream. Pin in `Dockerfile` and CI. |
| Container base image | `python:3.11-slim` (Debian slim) | Docker Hub / official image | Recommend multi-stage build; final image runs as **non-root**; build toolchain excluded from final image. |
| ASGI server | `uvicorn` (optionally behind `gunicorn`) | PyPI | Network listener (**SC-7**); terminate TLS at ingress/reverse proxy, not the app, in production. |
| Package installer | `pip` | PyPI | Pin to compatible ranges; recommend hash-pinning for Medium/High profiles (§7). |

---

## 5. Software Bill of Materials (SBOM)

> **Reconcile against the real `requirements.txt`.** The rows below are the typical dependency set for a FastAPI + Redis + Entra-ID gateway. Remove rows the project does not use; add any project-specific libraries.

### 5.1 Production dependencies (`requirements.txt`)

| # | Package | Pinned range (suggested) | License* | Upstream maintainer | Function in system | Security relevance |
|---|---|---|---|---|---|---|
| 1 | `fastapi` | `>=0.115,<1` | MIT | community (Sebastián Ramírez) | REST API / gateway framework | Network-facing API surface (**SC-7/SC-8**); dependency-injection auth guards (**AC-3**) |
| 2 | `uvicorn[standard]` | `>=0.30,<1` | BSD-3-Clause | community (Encode) | ASGI server | Network listener (**SC-7**) |
| 3 | `gunicorn` *(if used as process manager)* | `>=22.0,<23` | MIT | community | Prod process manager for uvicorn workers | Process isolation / resource limits (**SC-6**) |
| 4 | `starlette` | (transitive via `fastapi`) | BSD-3-Clause | community (Encode) | ASGI toolkit underlying FastAPI | **Request parsing / form limits** — recurrent CVE target (**SI-10**); pin a current floor (§7) |
| 5 | `redis` (redis-py) | `>=5.0,<6` | MIT | Redis / community | Response/session cache client (sync + async) | Connection to cache (**SC-8**); **require AUTH + TLS**; cache-poisoning surface (**SI-7**) |
| 6 | `msal` | `>=1.30,<2` | MIT | Microsoft | Acquires Entra tokens (e.g. on-behalf-of / downstream calls) | **IA-2 / IA-8** identification & authentication |
| 7 | `PyJWT[crypto]` **or** `python-jose[cryptography]` | `PyJWT>=2.9,<3` *(preferred)* | MIT | community | **Validates Entra ID JWTs (RS256) for both users and service principals** | **Security-critical token verification (SC-13 / IA-2)** — see §6 |
| 8 | `cryptography` | `>=43,<44` *(confirm via scan)* | Apache-2.0 / BSD | PyCA | Underpins JWT signature verification + TLS | Crypto primitives (**SC-13**) — keep patched (bundled OpenSSL advisories) |
| 9 | `httpx` | `>=0.27,<1` | BSD-3-Clause | community (Encode) | Async HTTP: JWKS fetch, Microsoft Graph, **proxying to the backend system** | External calls (**SC-7/SC-8**); SSRF surface if target is user-influenced (**AC-4**) |
| 10 | `pydantic` | `>=2.7,<3` | MIT | community | Request/response model validation | Input validation at the boundary (**SI-10**) |
| 11 | `pydantic-settings` | `>=2.4,<3` | MIT | community | Typed configuration loading | Config/secret handling (**CM-6 / IA-5**) |
| 12 | `python-dotenv` | `>=1.0,<2` | BSD-3-Clause | community | Loads configuration/secrets from env | Secrets handling (**IA-5 / CM-6**) — ensure `.env` excluded from images/VCS |
| 13 | `slowapi` **or** `limits` *(if rate-limiting)* | `slowapi>=0.1.9` | MIT | community | Per-client rate limiting (DoS protection) | **SC-5 (DoS protection)**; backed by Redis |
| 14 | `prometheus-client` *(if metrics)* | `>=0.20,<1` | Apache-2.0 | community | Metrics endpoint | Network-facing metrics (**SC-7**); monitoring (**SI-4**) |

### 5.2 Development & test dependencies (`requirements-dev.txt`) — *not shipped in production image*

| # | Package | Pinned range (suggested) | License* | Function |
|---|---|---|---|---|
| 15 | `pytest` | `>=8.0` | MIT | Unit/integration test framework |
| 16 | `pytest-cov` | `>=5.0` | MIT | Test coverage reporting |
| 17 | `pytest-asyncio` | `>=0.23` | Apache-2.0 | Async test support for FastAPI/httpx |
| 18 | `httpx` *(also test client)* | `>=0.27` | BSD-3-Clause | ASGI test client for endpoint tests |
| 19 | `fakeredis` *(if used)* | `>=2.23` | BSD-3-Clause | In-memory Redis for tests |
| 20 | `locust` *(if load-tested)* | `>=2.29` | MIT | Load/performance testing |

\* **Licenses are stated to the best of available knowledge and MUST be independently verified** by an automated license scan (e.g. `pip-licenses`) as part of this assessment. Treat the license column as a starting point, not authoritative legal record.

---

## 6. Supply-chain risk highlights (SA-12, SA-15)

Items the assessor should weigh during the supply-chain protection review:

| Component(s) | Risk factor | Recommended treatment |
|---|---|---|
| **JWT validator** (`PyJWT` or `python-jose`) | Performs **security-critical signature validation for both user and service-principal tokens**. The JOSE ecosystem has a history of algorithm-confusion / DoS CVEs. `python-jose` is more loosely maintained than `PyJWT`. | **Prefer `PyJWT[crypto]`** (more active maintenance). Pin the accepted algorithm to **`RS256`** and reject `alg=none` / `HS*`. Validate `iss`, `aud`, `exp`, `nbf` on every token, and the **JWKS `kid`**. See §7A-1. |
| **Service-principal vs user token distinction** | A gateway that accepts both user (delegated) and SP (app-only) tokens must **not** confuse them — an app-only token has no user context and different scopes/roles. Confusion can over-grant. | Validate the token type explicitly: check `idtyp`/`appid` and the `roles` (app permissions) vs `scp` (delegated scopes) claims; enforce distinct authorization paths. Validate `aud` matches the gateway's own App ID URI. |
| `starlette` | Underpins FastAPI request/form parsing; **recurrent CVE target** (DoS via form limits, URL/host parsing). | Pin a current floor via the §7.3 constraints file; re-resolve after each `pip-audit`. |
| `redis` (cache) | Caches responses/sessions — a **cache-poisoning or unauthenticated-Redis** exposure can leak data across principals or serve forged responses. | Require **AUTH + TLS**; never expose Redis publicly; key cache entries by **authenticated principal + scope** so one user's cached data can't be served to another; set TTLs; do not cache responses for unauthenticated requests. |
| `httpx` outbound to backend | The gateway makes server-side requests to the backend; if any target URL/host is influenced by client input, it's an **SSRF** vector. | Pin the backend base URL server-side; allowlist hosts; never forward client-controlled URLs; disable redirects to unexpected hosts. |
| All packages | Installed from public **PyPI**. | For Medium/High profiles, install from a **vetted internal mirror** and enable `pip install --require-hashes`. |
| Container base image | `python:3.11-slim` pulled from Docker Hub. | Pull from an approved internal registry; scan image (Trivy/Defender); pin by digest. |

---

## 7. Vulnerability management (RA-5, SI-2)

> **STATUS: NOT YET RUN.** Execute the procedure below against the resolved environment and the built container image, then populate §7.2 with the actual results and date.

### 7.1 Scan procedure to execute

```bash
pip-audit                                   # CVE/GHSA against resolved venv (direct + transitive)
pip-licenses --format=markdown --with-urls  # license inventory
trivy image <image:tag>                     # container/OS-package scan (or grype)
```

### 7.2 Findings and remediation — *to be populated by the live scan*

| Vulnerable pkg | Installed | Severity (class) | ID | Pulled in by | Shipped in prod image? | Fix version | Recommended action |
|---|---|---|---|---|---|---|---|
| _(populate from `pip-audit` — expect `starlette` / `cryptography` floors here)_ | | | | | | | |

> **Likely candidates for this stack** (verify, do not assume): `starlette` (form/host-parsing advisories), `cryptography` (bundled-OpenSSL advisories), `python-multipart` (if form uploads), `pydantic-settings` (if used). The existing dictionary-app review found exactly these as transitive floors — the same FastAPI/Starlette lineage applies here.

### 7.3 Remediation approach (recommended)

Because findings are typically transitive, use a **constraints file** that floors vulnerable sub-dependencies without disturbing the curated top-level pins:

```text
# constraints.txt — security floors for transitive dependencies (ITSG-33 SI-2)
# populate exact floors from the pip-audit run, e.g.:
# starlette>=<fixed>
# cryptography>=<fixed>
# python-multipart>=<fixed>
```

```bash
pip install -r requirements.txt -c constraints.txt
pip-audit                          # re-run: expect 0 findings in the production set
```

After applying, re-run `pip-audit` and attach the clean result as the **SI-2 closure evidence**.

### 7.4 License scan result (SA-4 / legal) — *to be populated*

Run `pip-licenses` and record results here. Pre-flag: confirm acceptance of any MPL-2.0 (weak copyleft) transitive components (e.g. `certifi`); resolve any `UNKNOWN` license-metadata packages from their repos.

### 7.5 Ongoing controls to evidence

- **SI-2 (Flaw remediation):** enable Dependabot / Renovate + a container scanner in CI; define a patch SLA (Critical ≤ 7 days, High ≤ 30 days).
- **RA-5 (Vulnerability scanning):** wire `pip-audit` + `trivy image` into CI; fail the build on Critical/High.
- **CM-2 / CM-6 (Baseline):** keep top-level pins; add the §7.3 constraints file; for Medium/High profiles add `--require-hashes` + an internal PyPI mirror.
- **SA-22 (Unsupported components):** verify Python 3.11 and all components are supported (no EOL).
- **Records:** generate a CycloneDX SBOM: `cyclonedx-py requirements -i requirements.txt -o sbom.json`.

---

## 7A. Mitigation plan for design / supply-chain risks (§6)

These are the structural risks from §6 (not CVEs). Each has a concrete mitigation and the ITSG-33 control it satisfies.

| # | Risk | Mitigation | Control |
|---|---|---|---|
| 1 | **JWT validation is security-critical** and the JOSE ecosystem has a CVE history. | (a) Prefer **`PyJWT[crypto]`** over `python-jose`. (b) **Pin the accepted algorithm to `RS256`**; reject `alg=none`/`HS*` to defeat algorithm-confusion. (c) Validate `iss`, `aud`, `exp`, `nbf`, and `kid` against the Entra JWKS on every request. (d) Cache JWKS with rotation handling; fail closed on validation error. | IA-2, SC-13 |
| 2 | **User vs service-principal token confusion.** | Distinguish token types explicitly: enforce **`roles` (app permissions)** for SP/app-only tokens and **`scp` (delegated scopes)** for user tokens; check `idtyp`/`appid`; verify `aud` equals the gateway's App ID URI. Maintain separate authorization paths and least-privilege app roles. | IA-2, IA-9, AC-3, AC-6 |
| 3 | **Redis cache poisoning / cross-principal leakage.** | Key cache entries by **authenticated principal + scope**; never serve cached data across identities; require **Redis AUTH + TLS**; private subnet only; set TTLs; do not cache unauthenticated responses. The gateway should degrade gracefully (cache-miss path) if Redis is unavailable. | SI-7, SC-8, SC-28 |
| 4 | **SSRF via outbound `httpx` to the backend.** | Pin the backend base URL server-side; **allowlist** target hosts; never proxy client-supplied URLs; disable cross-host redirects; set timeouts. | AC-4, SC-7 |
| 5 | **DoS against the gateway chokepoint.** | Enforce **rate limiting** (`slowapi`/`limits`, Redis-backed) per principal/IP; set request size + timeout limits; run multiple uvicorn workers behind `gunicorn`; place behind an ingress/WAF. | SC-5, SC-6 |
| 6 | **`starlette` request-parsing CVEs.** | Pin a current floor (§7.3); set explicit form/body size limits; keep `python-multipart` patched if uploads are accepted. | SI-10, SI-2 |
| 7 | **Secrets via `.env` / `python-dotenv`.** | `.env` is local-dev only — git-ignore it and exclude from the image (verify `.dockerignore`). In production inject SP client secret / Redis password from **Key Vault** (or use a managed identity / workload identity, no secret at all). | IA-5, CM-6 |
| 8 | **TLS termination.** | Enforce TLS in transit to clients, to Redis, to the JWKS/Graph endpoints, and to the backend; terminate client TLS at a hardened ingress/reverse proxy; verify certificates on all outbound calls. | SC-8, SC-13 |

---

## 8. ITSG-33 control family mapping (summary)

| Family | Control(s) | How the dependency posture contributes | Status / evidence needed |
|---|---|---|---|
| **CM — Configuration Management** | CM-2, CM-6, CM-7, CM-8, CM-10, CM-11 | Pinned `requirements*.txt`; multi-stage Dockerfile; SBOM in §5 | Attach SBOM; add hash-pinning |
| **SA — System & Services Acquisition** | SA-4, SA-12, SA-15, SA-22 | Provenance (PyPI), licensing (§5), supply-chain notes (§6) | Internal mirror; supply-chain sign-off |
| **RA — Risk Assessment** | RA-5 | Scan tooling defined (§7) | Attach `pip-audit` + image scan output |
| **SI — System & Information Integrity** | SI-2, SI-4, SI-7, SI-10 | Patch process; input validation; cache integrity | Evidence of CI scanning + boundary validation |
| **IA — Identification & Authentication** | IA-2, IA-5, IA-8, IA-9 | `msal` + JWT validator implement Entra ID OIDC/JWT for users **and** SPs | **Verify token-validation config (alg pin, aud, roles vs scp) & secret handling** |
| **SC — System & Communications Protection** | SC-5, SC-6, SC-7, SC-8, SC-13, SC-28 | TLS to clients/Redis/Graph/backend; rate limiting; boundary protection | Confirm TLS enforced; Redis auth/TLS; rate limits active |
| **AC — Access Control** | AC-3, AC-4, AC-6 | DI auth guards; SSRF allowlisting; least-privilege app roles/scopes | Reference gateway authz design |
| **AU — Audit & Accountability** | AU-2, AU-3 | Access log of authenticated requests + authz decisions | Reference logging design |

---

## 9. Assessor checklist

- [ ] Confirm system security categorization / control profile (§2).
- [ ] Reconcile §5 SBOM against the project's actual `requirements.txt` / `requirements-dev.txt`.
- [ ] Run `pip-audit` against the resolved environment; populate §7.2.
- [ ] Run `trivy image` (or Grype) against the built container image; attach output.
- [ ] Apply the §7.3 constraints file and re-run `pip-audit`; attach the clean result as SI-2 closure evidence.
- [ ] Validate license inventory with `pip-licenses`; resolve any `UNKNOWN` (§7.4).
- [ ] **Confirm JWT validation pins `RS256`, validates `iss`/`aud`/`exp`/`kid`, and prefers `PyJWT` (§7A-1).**
- [ ] **Confirm user vs SP token handling: `scp` vs `roles`, `aud` = gateway App ID URI (§7A-2).**
- [ ] Confirm Redis AUTH + TLS, principal-scoped cache keys, private networking (§7A-3).
- [ ] Confirm outbound SSRF allowlisting to the backend (§7A-4).
- [ ] Confirm rate limiting / request-size limits active (§7A-5).
- [ ] Confirm secrets sourced from Key Vault / managed identity, not `.env`, in production (§7A-7).
- [ ] Decide on internal PyPI mirror + hash-pinning for the target profile.
- [ ] Record residual risks and obtain authorization decision (CA-6).

---

## 10. Statement of accuracy

This document is a **prefilled template** for a FastAPI + Redis + Entra-ID API gateway. The dependency inventory (§4–§5) reflects the **typical** dependency set for this stack and **must be reconciled** against the repository's actual `requirements.txt`, `requirements-dev.txt`, and `Dockerfile` before assessment. **No vulnerability findings are asserted** — §7.2 is a placeholder to be populated by the live `pip-audit` and `trivy image` runs. Severity *class* labels, once added, are the assessor's characterization for prioritization and should be reconciled against the official CVSS scores in each advisory. Because this is a security-enforcing gateway, the assessor should give the identity controls (§7A-1/-2) and the cache/SSRF/DoS controls (§7A-3/-4/-5) priority over generic dependency hygiene.
