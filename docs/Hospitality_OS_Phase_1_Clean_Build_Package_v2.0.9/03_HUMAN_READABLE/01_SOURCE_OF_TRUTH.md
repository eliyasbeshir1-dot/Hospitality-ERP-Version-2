# Hospitality OS Phase 1 Source of Truth

**Normative human-readable projection**

- Package: `Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9`
- Canonical source root: `cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96`
- Status: **Package M0 candidate - M0R and implementation are not authorized**

## Authority

The canonical authority is the pinned reconciled source ZIP in `01_CANONICAL_SOURCE`. The JSON files in `02_MACHINE_READABLE` and all Markdown, Excel, Word and PDF files are generated projections. When projections conflict, the pinned canonical JSON controls.

## Package status

- Package M0: candidate for independent Codex review.
- M0R: prohibited until Codex approves or a recorded founder adjudication satisfies FR-GOV-004.
- Database, migration `0001`, routes, workers, screens and application code: prohibited before M1.

## Canonical counts

- Active Requirements: **336**
- Decisions: **120**
- Journey Slices: **16**
- State Machines: **12**
- Events: **80**
- Negative Controls: **44**
- Non Regression Rules: **96**
- Review Questions: **14**
- Original Requirement Dispositions: **500**
- Original Decision Dispositions: **100**
- Amendments: **20**
- Findings: **22**

## Non-negotiable product rules

- Phase 1 is dine-in customer service and outlet execution only.
- English, Amharic and Arabic are the exact customer launch languages; Arabic is true RTL.
- Bill, payment and tip are separate records; no tip is preselected.
- Cash, external-terminal result recording and verified Telebirr/CBE Birr proof confirmation are live pilot paths.
- Direct provider APIs remain simulator-only until contracted; raw card data is prohibited.
- Minimum real receipt printing begins at M4; resilient local print queueing begins at M5a.
- Local authority continuity begins at M5b, not M5a; the cloud is never a writable dine-in fallback.
- The outlet node generates and retains its private key; only a CSR leaves the node.
- Phase 2/3 entities, routes, tables, workers, screens and positive tests are physically absent.

## Milestone sequence

| Gate | Name | Requirements | Exit criterion |
|---|---|---:|---|
| M0 | Package M0 | 2 | Codex independent review of this exact ZIP. |
| M0R | Repository Conformance | 30 | No database, migration, route, worker or UI exists. |
| M1 | Foundation | 77 | Real PostgreSQL and production-role isolation tests pass. |
| M2 | Menu, QR and customer session | 49 | English/Amharic/Arabic customer surfaces and true Arabic RTL pass. |
| M3 | Ordering and service | 75 | The three M3 language journeys pass without billing or local authority. |
| M4 | POS, billing and settlement | 55 | Live pilot payment paths and physical/digital receipts pass. |
| M5a | Outlet execution and resilience | 24 | Restart, retry, deduplication, reconnect and print recovery pass. |
| M5b | Same-QR trust and authority | 12 | Same QR works under supported resolver conditions without split-brain or browser bypass. |
| M6 | Production hardening | 12 | Destructive restore, production roles, full scans and second-tenant evidence pass. |
