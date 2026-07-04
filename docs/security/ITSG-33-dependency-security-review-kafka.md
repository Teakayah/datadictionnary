# ITSG-33 dependency security review — Apache Kafka integration service

**System:** Apache Kafka integration / streaming service (Python, `confluent-kafka`)
**Prepared by:** Nicolas Leclerc
**Date:** 2026-06-25
**Standard:** CSE *IT Security Risk Management: A Lifecycle Approach* (ITSG-33), Annex 3A — Security Control Catalogue (maps to NIST SP 800-53)
**Classification of this document:** To be determined by the Departmental Security Officer / IT Security team

> **Prefill status.** This is a **template prefilled for the stack**, not yet grounded in a live repository scan. Sections §4–§5 list the *expected* dependencies for a Python `confluent-kafka` service — reconcile each row against the project's actual `requirements.txt` before assessment. Section §7 is a **ready-to-run scan procedure**: the CVE/license findings tables are placeholders to be populated by the live `pip-audit` / `pip-licenses` run. Do **not** treat any version pins or "fix versions" here as authoritative until the scan is executed.

---

## 1. Purpose and scope

This report supports an ITSG-33-aligned security assessment of the **third-party software dependencies** required to build, run, and test the Apache Kafka integration service. It provides:

- A Software Bill of Materials (SBOM) of all production and development dependencies, **including the native `librdkafka` C library** wrapped by `confluent-kafka`.
- A mapping of the dependency-management posture to the relevant ITSG-33 / NIST 800-53 control families.
- A per-dependency supply-chain and licensing assessment, with particular attention to the native transport/SASL/TLS layer.
- Recommended evidence and actions for the assessor to complete the authorization (security assessment & authorization, **CA** family) activity.

> **Scope note.** This review covers software components (`SA`, `CM`, `SI`, `RA` families). It does **not** by itself constitute the full system security assessment — operational controls (`AC`, `AU`, `IA`, `SC`, `CP`, `IR`, etc.) are implemented in the service and broker infrastructure and are documented separately. References to those families below indicate *where a dependency contributes to* a control, not that the control is fully evidenced here. **Broker-side controls (ACLs, quotas, mTLS between brokers, at-rest encryption of topic logs) are out of scope of this dependency review** and must be assessed against the Kafka cluster's own authorization package.

---

## 2. System security categorization (to be confirmed by IT Security)

ITSG-33 risk management begins with categorizing the information system by the expected **injury level** (Low / Medium / High) for each security objective. This drives the applicable control profile (e.g. PBMM — Protected B, Medium integrity, Medium availability).

| Security objective | Preliminary characterization | Rationale |
|---|---|---|
| Confidentiality | **To confirm — likely Medium (Protected B candidate)** | Message payloads traverse Kafka topics; sensitivity depends on the data carried. If any topic carries personal or Protected B information, the service inherits that categorization end-to-end (producer → broker → consumer). |
| Integrity | **Medium–High** | A streaming service is an integrity-critical path: corrupted, replayed, or out-of-order messages propagate downstream. Schema validation (Schema Registry) and idempotent/exactly-once semantics are integrity controls. |
| Availability | **Medium–High** | If the service is on a real-time ingestion or event-driven transaction path, an outage stalls downstream processing and can cause consumer-lag backpressure. Categorize per the most availability-sensitive consumer. |

**Recommended profile:** Validate against the **PBMM** (Protected B / Medium / Medium) control profile in ITSG-33 Annex 4A — or higher on Integrity/Availability if the stream is transaction-critical. Confirm with the DSO before finalizing the control selection.

---

## 3. Methodology

1. **Inventory (CM-8).** Enumerate all declared dependencies from `requirements.txt` (runtime) and `requirements-dev.txt` (development/test). Dev dependencies are excluded from the production container image and flagged accordingly.
2. **Native-component inventory (CM-8 / SA-22).** `confluent-kafka` bundles a compiled **`librdkafka`** plus its transitive native libraries (OpenSSL, SASL/Cyrus, zlib, zstd, lz4). These are **not** visible to `pip-audit` and must be inventoried separately (see §6, §7.5).
3. **Provenance (SA-12).** Identify the upstream source and distribution channel (PyPI / `pip`; native libs bundled in the `confluent-kafka` wheel).
4. **Licensing (SA-4 / legal).** Record the open-source license for each component.
5. **Vulnerability posture (RA-5 / SI-2).** Define the scanning tooling and where current results must be attached. *No CVE results are asserted in this document — they are produced by a live scan at assessment time (see §7).*
6. **Control mapping (CA-2).** Map the dependency-management practices to ITSG-33 control families.

---

## 4. Runtime environment

| Component | Version | Source | Notes |
|---|---|---|---|
| Python | 3.11 (confirm) | `python:3.11-slim` (official Docker image) | Supported release; security-patched by upstream. Pin in `Dockerfile` and CI. |
| Container base image | `python:3.11-slim` (Debian slim) | Docker Hub / official image | Recommend multi-stage build; final image runs as **non-root**. Note: `confluent-kafka` wheels are manylinux — confirm no build toolchain is left in the final image. |
| **`librdkafka` (native)** | bundled in the `confluent-kafka` wheel (confirm version) | Confluent (compiled into the wheel) | **Security-critical native transport layer** — implements TLS, SASL (SCRAM/GSSAPI/OAUTHBEARER), compression. Tracks its own CVE stream (**SA-22 / SI-2**). |
| Package installer | `pip` | PyPI | Pin to compatible ranges; recommend hash-pinning for Medium/High profiles (§7). |

---

## 5. Software Bill of Materials (SBOM)

> **Reconcile against the real `requirements.txt`.** The rows below are the typical dependency set for a Python `confluent-kafka` integration service. Remove rows the project does not use; add any project-specific libraries.

### 5.1 Production dependencies (`requirements.txt`)

| # | Package | Pinned range (suggested) | License* | Upstream maintainer | Function in system | Security relevance |
|---|---|---|---|---|---|---|
| 1 | `confluent-kafka` | `>=2.5,<3` | Apache-2.0 | Confluent | Kafka producer/consumer client (wraps `librdkafka`) | **Core transport, TLS, SASL/OAUTHBEARER** (**SC-8 / IA-2**); bundles native libs (**SA-22**) |
| 2 | `fastavro` *(if Avro)* | `>=1.9,<2` | MIT | community | Avro serialization/deserialization | Deserialization surface (**SI-10** input validation) |
| 3 | `confluent-kafka[avro]` / `schema-registry-client` *(if used)* | `>=2.5,<3` | Apache-2.0 | Confluent | Schema Registry integration | Outbound HTTP to registry (**SC-7/SC-8**); auth to registry (**IA-2**) |
| 4 | `pydantic` | `>=2.7,<3` | MIT | community | Message-model validation | Enforces message schema/structure (**SI-10**) |
| 5 | `azure-identity` *(if Entra OAUTHBEARER to brokers)* | `>=1.17,<2` | MIT | Microsoft | Acquires Entra tokens for SASL/OAUTHBEARER broker auth | **IA-2 / IA-9** broker authentication; secret/token handling (**IA-5**) |
| 6 | `tenacity` | `>=8.4,<9` | Apache-2.0 | community | Retry/backoff on transient broker errors | Availability/resilience (**SC-5 / CP-10**) |
| 7 | `python-dotenv` | `>=1.0,<2` | BSD-3-Clause | community | Loads configuration/secrets from env | Secrets handling (**IA-5 / CM-6**) — ensure `.env` excluded from images/VCS |
| 8 | `structlog` *(or stdlib logging)* | `>=24.1` | Apache-2.0 / MIT | community | Structured application logging | Feeds audit/event logs (**AU-2/AU-3**) |
| 9 | `prometheus-client` *(if metrics)* | `>=0.20,<1` | Apache-2.0 | community | Exposes consumer-lag / throughput metrics | Metrics endpoint is network-facing (**SC-7**); monitoring (**SI-4**) |
| 10 | `requests` **or** `httpx` *(if HTTP to registry/sidecar)* | `requests>=2.32,<3` / `httpx>=0.27,<1` | Apache-2.0 / BSD-3-Clause | PSF / Encode | Outbound HTTP | External calls (**SC-7 / AC-4**) |

### 5.2 Development & test dependencies (`requirements-dev.txt`) — *not shipped in production image*

| # | Package | Pinned range (suggested) | License* | Function |
|---|---|---|---|---|
| 11 | `pytest` | `>=8.0` | MIT | Unit/integration test framework |
| 12 | `pytest-cov` | `>=5.0` | MIT | Test coverage reporting |
| 13 | `testcontainers[kafka]` *(if used)* | `>=4.0` | Apache-2.0 | Spins ephemeral Kafka/Redpanda for integration tests |
| 14 | `faker` | `>=26.0` | MIT | Synthetic test-message generation |

\* **Licenses are stated to the best of available knowledge and MUST be independently verified** by an automated license scan (e.g. `pip-licenses`) as part of this assessment. Treat the license column as a starting point, not authoritative legal record. **The native `librdkafka` and its bundled libraries (OpenSSL, Cyrus SASL, zlib, zstd, lz4) carry their own licenses (BSD-2/Apache-2.0/zlib/BSD) and their own CVEs** — they are not covered by `pip-licenses`/`pip-audit` and must be inventoried from the wheel (§7.5).

---

## 6. Supply-chain risk highlights (SA-12, SA-15)

Items the assessor should weigh during the supply-chain protection review:

| Component(s) | Risk factor | Recommended treatment |
|---|---|---|
| `confluent-kafka` → **`librdkafka` (native)** | The wheel **statically bundles a compiled C transport stack** (librdkafka + OpenSSL + SASL + compression). `pip-audit` **cannot see these** — a vulnerable bundled OpenSSL or librdkafka is invisible to Python-level scanning. This is the single highest supply-chain risk in this stack. | (a) Record the exact `confluent-kafka` version and the `librdkafka` version it bundles (`Producer.list_topics`/version introspection or `confluent_kafka.libversion()`). (b) Subscribe to librdkafka + OpenSSL advisories. (c) Scan the **container image** (Trivy/Grype/Defender) which *does* inspect native libs. (d) Pin `confluent-kafka` to a version whose bundled OpenSSL is current. |
| Broker authentication via **SASL/OAUTHBEARER + `azure-identity`** | Token acquisition for broker auth; misconfiguration can leak credentials or fail open. | Use a dedicated **service principal / managed identity** scoped to the required topics only (**AC-6**); never embed client secrets in `.env` in production — use Key Vault / workload identity. Validate token audience for the Kafka resource. |
| Deserialization (`fastavro`, `pydantic`, or JSON) | **Untrusted message payloads are a deserialization attack surface.** Malformed Avro/JSON or schema poisoning can crash or exploit consumers. | Validate every message against a registered schema before processing (**SI-10**); reject on schema mismatch; never use `pickle`/`eval` on message bodies; fuzz-test the deserializer. |
| Schema Registry client | If present, the registry is a **trusted dependency for message integrity** — a compromised or spoofed registry undermines validation. | Require TLS + auth to the registry; pin the registry URL; cache schemas with integrity checks. |
| All packages | Installed from public **PyPI**; native libs from the Confluent-built wheel. | For Medium/High profiles, install from a **vetted internal mirror** and enable `pip install --require-hashes`. Verify the `confluent-kafka` wheel hash. |
| Container base image | `python:3.11-slim` pulled from Docker Hub. | Pull from an approved internal registry; scan image (Trivy/Defender); pin by digest. |

---

## 7. Vulnerability management (RA-5, SI-2)

> **STATUS: NOT YET RUN.** Execute the procedure below against the resolved environment and the built container image, then populate §7.2 and §7.5 with the actual results and date.

### 7.1 Scan procedure to execute

```bash
# Python-level (direct + transitive)
pip-audit                                   # CVE/GHSA against resolved venv
pip-licenses --format=markdown --with-urls  # license inventory

# Native libs bundled in the confluent-kafka wheel (NOT seen by pip-audit):
python -c "import confluent_kafka as c; print('confluent-kafka', c.version()); print('librdkafka', c.libversion())"

# Container image scan — this is what catches the bundled OpenSSL/librdkafka/zlib CVEs:
trivy image <image:tag>                     # or: grype <image:tag>
```

### 7.2 Findings and remediation — *to be populated by the live scan*

| Vulnerable pkg | Installed | Severity (class) | ID | Pulled in by | Shipped in prod image? | Fix version | Recommended action |
|---|---|---|---|---|---|---|---|
| _(populate from `pip-audit`)_ | | | | | | | |
| _(populate native libs from `trivy image`)_ | | | | | | | |

### 7.3 Remediation approach (recommended)

For Python-level transitive findings, use a **constraints file** that floors vulnerable sub-dependencies without disturbing the curated top-level pins:

```text
# constraints.txt — security floors for transitive dependencies (ITSG-33 SI-2)
# (populate from the pip-audit run, e.g.)
# cryptography>=<fixed>
# certifi>=<fixed>
```

```bash
pip install -r requirements.txt -c constraints.txt
pip-audit                          # re-run: expect 0 findings in the production set
```

For **native** findings (bundled OpenSSL/librdkafka), the fix is to **upgrade `confluent-kafka`** to a wheel built against the patched native libs (a constraints file cannot fix a statically-bundled C library). Re-run `trivy image` to confirm closure.

### 7.4 License scan result (SA-4 / legal) — *to be populated*

Run `pip-licenses` and record results here. Pre-flag: confirm acceptance of any MPL-2.0 (weak copyleft) transitive components; confirm the `librdkafka`/OpenSSL/zlib/zstd/lz4 native licenses (all permissive) are inventoried for the authorization package.

### 7.5 Native dependency closure (SA-22) — *required, do not skip*

- Record `confluent_kafka.version()` **and** `confluent_kafka.libversion()` (the bundled librdkafka).
- Attach the `trivy image` (or Grype) output as the **native-library SI-2 evidence** — this is the only artifact that proves the bundled OpenSSL/zlib/SASL libs are patched.
- Confirm no end-of-life native components (e.g. an OpenSSL 1.x line that is EOL).

### 7.6 Ongoing controls to evidence

- **SI-2 (Flaw remediation):** enable Dependabot / Renovate **and** a container-image scanner in CI; define a patch SLA (Critical ≤ 7 days, High ≤ 30 days). Critically — track `confluent-kafka`/librdkafka releases for native CVEs.
- **RA-5 (Vulnerability scanning):** wire `pip-audit` **+ `trivy image`** into CI; fail the build on Critical/High.
- **CM-2 / CM-6 (Baseline):** keep top-level pins; add the §7.3 constraints file; for Medium/High profiles add `--require-hashes` + an internal PyPI mirror.
- **SA-22 (Unsupported components):** verify Python 3.11 and the bundled OpenSSL line are both supported.
- **Records:** generate a CycloneDX SBOM: `cyclonedx-py requirements -i requirements.txt -o sbom.json`, and append the native-lib versions from §7.5.

---

## 7A. Mitigation plan for design / supply-chain risks (§6)

These are the structural risks from §6 (not CVEs). Each has a concrete mitigation and the ITSG-33 control it satisfies.

| # | Risk | Mitigation | Control |
|---|---|---|---|
| 1 | **`confluent-kafka` bundles a native transport stack (librdkafka + OpenSSL) invisible to `pip-audit`.** | (a) Pin `confluent-kafka` exact; record `libversion()`. (b) Add a **container image scan** (Trivy) to CI as the authoritative native-CVE check. (c) Subscribe to librdkafka + OpenSSL advisories; treat a librdkafka release as a security event. | SA-22, SI-2, RA-5 |
| 2 | **Broker auth secrets (SASL) in `.env`.** | Use **Entra OAUTHBEARER + managed identity / workload identity** where the broker supports it; otherwise store SASL credentials in Key Vault, not `.env`. Scope the principal to the specific topics (**AC-6**). Rotate. | IA-5, AC-6, IA-9 |
| 3 | **Untrusted message payload deserialization.** | Validate every message against a registered schema (Avro/JSON Schema) **before** processing; reject on mismatch; never `pickle`/`eval`; add malformed-message fuzz tests; route poison messages to a dead-letter topic. | SI-10, SI-3 |
| 4 | **In-transit confidentiality to brokers.** | Require **TLS** for all producer/consumer connections (`security.protocol=SASL_SSL`); verify broker certificate; disable plaintext listeners on the client config. | SC-8, SC-13 |
| 5 | **Schema Registry trust.** | Require TLS + auth to the registry; pin the URL; reject unverified schema sources. | IA-2, SI-10 |
| 6 | **All packages from public PyPI; wheel integrity.** | Install from a vetted internal mirror; `pip install --require-hashes`; verify the `confluent-kafka` wheel hash. | SA-12, CM-6 |
| 7 | **Base image from Docker Hub.** | Mirror `python:3.11-slim` to an approved registry, **pin by digest**, scan every build. | CM-2, SA-12, RA-5 |
| 8 | **Consumer-lag / availability risk.** | Configure idempotent producers + appropriate `acks`; monitor consumer lag (Prometheus); use `tenacity` backoff; define a DLQ + replay runbook. | SC-5, CP-10, SI-4 |

---

## 8. ITSG-33 control family mapping (summary)

| Family | Control(s) | How the dependency posture contributes | Status / evidence needed |
|---|---|---|---|
| **CM — Configuration Management** | CM-2, CM-6, CM-7, CM-8, CM-10, CM-11 | Pinned `requirements*.txt`; multi-stage Dockerfile; SBOM in §5 **+ native-lib inventory** | Attach SBOM + librdkafka/OpenSSL versions; add hash-pinning |
| **SA — System & Services Acquisition** | SA-4, SA-12, SA-15, **SA-22** | Provenance (PyPI + bundled wheel), licensing (§5), supply-chain notes (§6) | Internal mirror; **native-lib supportability sign-off** |
| **RA — Risk Assessment** | RA-5 | Scan tooling defined (§7) incl. image scan | Attach `pip-audit` **+ `trivy image`** output |
| **SI — System & Information Integrity** | SI-2, SI-3, SI-4, SI-10 | Patch process; schema validation of messages; lag monitoring | Evidence of CI scanning + schema-validation enforcement |
| **IA — Identification & Authentication** | IA-2, IA-5, IA-9 | `azure-identity` / SASL broker auth | Verify SASL/OAUTHBEARER config & secret handling |
| **SC — System & Communications Protection** | SC-5, SC-7, SC-8, SC-13 | TLS (`SASL_SSL`) to brokers/registry; metrics endpoint exposure | Confirm TLS enforced; restrict metrics endpoint |
| **AC — Access Control** | AC-4, AC-6 | Least-privilege topic ACLs via scoped principal | Reference broker ACL design |
| **AU — Audit & Accountability** | AU-2, AU-3 | Structured logs of produce/consume + DLQ events | Reference logging design |
| **CP — Contingency Planning** | CP-10 | Retry/backoff + DLQ + replay | Reference replay runbook |

---

## 9. Assessor checklist

- [ ] Confirm system security categorization / control profile (§2).
- [ ] Reconcile §5 SBOM against the project's actual `requirements.txt` / `requirements-dev.txt`.
- [ ] Run `pip-audit` against the resolved environment; populate §7.2.
- [ ] **Run `trivy image` (or Grype) against the built container image; populate §7.2/§7.5** — required to cover bundled OpenSSL/librdkafka.
- [ ] Record `confluent_kafka.version()` and `confluent_kafka.libversion()` (§7.5).
- [ ] Validate license inventory with `pip-licenses`; resolve any `UNKNOWN`; confirm native-lib licenses (§7.4).
- [ ] Confirm **TLS (`SASL_SSL`)** enforced on all broker connections (§7A-4).
- [ ] Confirm schema validation rejects malformed messages + DLQ exists (§7A-3).
- [ ] Confirm least-privilege, topic-scoped broker principal; secrets in Key Vault not `.env` (§7A-2).
- [ ] Decide on internal PyPI mirror + hash-pinning + wheel-hash verification (§7A-6).
- [ ] Record residual risks and obtain authorization decision (CA-6).

---

## 10. Statement of accuracy

This document is a **prefilled template** for a Python `confluent-kafka` integration service. The dependency inventory (§4–§5) reflects the **typical** dependency set for this stack and **must be reconciled** against the repository's actual `requirements.txt`, `requirements-dev.txt`, and `Dockerfile` before assessment. **No vulnerability findings are asserted** — §7.2/§7.5 are placeholders to be populated by the live `pip-audit` and `trivy image` runs. Severity *class* labels, once added, are the assessor's characterization for prioritization and should be reconciled against the official CVSS scores in each advisory. The container image scan and native-library inventory (§7.5) have **not** yet been run and must be produced before authorization — they are especially important here because `pip-audit` alone does not see the bundled native transport stack.
