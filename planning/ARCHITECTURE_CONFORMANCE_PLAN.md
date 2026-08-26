# Architecture Conformance Plan

**Repository:** `Hospitality-ERP-Version-2`
**Gate:** M0R — Repository Conformance
**Governing requirement:** FR-GOV-001A
**Source of truth:** `docs/Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9/`, pinned at
`b89a2d4211356be5941dc25ff2dc540728c87ed761ffd9894a3f2691ccf5b590`

This document states what this repository is permitted to contain now, and what M1 onward
will build. It builds nothing. Every rule below is drawn from the package under `/docs`;
where a rule is contestable, the package is authoritative, not this file.

---

## What this repository contains today

```
README.md                              gate status, prohibitions, lineage
.gitignore                             caches, dependency dirs, generated validator output
.github/workflows/m0r-conformance.yml  four validator jobs, no application tests
docs/…v2.0.9/                          92 files, byte-identical, 91/91 checksums verified
planning/                              this file and three companions
tools/verify_m0r_skeleton.py           forbidden-surface verification, unmodified
```

There is no database, schema, migration, route, worker, ORM model, UI or application test,
and no `src/`, `app/`, `db/`, `services/`, `web/`, `pwa/` or `ui/` directory. Their absence
is the pass condition of this gate. `tools/verify_m0r_skeleton.py` proves it mechanically.

---

## Phase 1 scope

QR dine-in ordering · English, Amharic and Arabic · waiter service · KDS, bar and expo ·
POS and checks · separate optional tips · payments · receipts · outlet continuity during an
internet outage.

**Not in Phase 1:** inventory, accounting, purchasing, payroll, recipes, costing, loyalty,
CRM, pickup, delivery. These are fenced by 24 of the 30 requirements introduced at this
gate.

Despite the repository name, **this is not an ERP.** The name does not widen the scope.

---

## Planned components

None of these exist yet. Each is created at its own gate, never earlier.

| Component | Gate | Purpose |
|---|---|---|
| Cloud API (Fastify/TypeScript) | M1 | tenancy, identity, configuration, domain services |
| PostgreSQL | M1 | single canonical store, RLS-enforced |
| Customer PWA | M2 | QR menu, cart, ordering, status — three languages |
| Waiter and KDS surfaces | M3 | order entry, ticket flow, expo |
| POS surface | M4 | checks, payments, tips, receipts, cash shifts |
| Outlet Continuity Node | M5a | local API, local PostgreSQL, sync worker, print agent |
| Same-QR routing | M5b | split-horizon DNS, per-outlet TLS, authority lease |

The component each requirement is assigned to is recorded in the package itself, in
`docs/…/02_MACHINE_READABLE/requirements.json` under `component_path`. This repository does
not restate that mapping; it points at it.

---

## Conformance rules carried into every gate

These bind M1 onward. They are stated here because M0R is where the baseline is set.

1. **Gate-local closure** — a gate closes only on behavior provable at that gate. 39 of the
   336 active requirements are dual-gated, with explicit revalidation gates.
2. **Deny by default** — API, database policy, jobs, cache and files fail closed on missing
   tenant, outlet, session or actor context.
3. **Exact money** — fixed-point or integer minor units. Never binary floating point.
4. **Bill and tip are separate** — separate values, separate records, separate reversal. No
   tip is selected by default.
5. **Payment matrix** — live: cash, external terminal recording, verified Telebirr and CBE
   Birr proof. Simulated until contracted: direct provider APIs. Prohibited: raw card data.
6. **One writable authority per outlet** — enforced by a monotonic signed epoch, with fence
   evidence required before replacement.
7. **Real persistence in tests** — production roles, never a superuser.
8. **No dormant future modules** — no route, table, worker or screen for a fenced domain,
   however inert.

---

## The 30 requirements introduced at M0R

Verified against `docs/…/02_MACHINE_READABLE/requirements.json` (`introduced_at == "M0R"`).

**24 are fenced negatives** — obligations to prove something is *absent*:

FR-CFG-002B · FR-CFG-005B · FR-EDG-002B · FR-FUL-016B · FR-MNU-002B · FR-ORD-001C ·
FR-ORD-012B · FR-ORD-016B · FR-ORD-019B · FR-PAY-010B · FR-POS-003C · FR-POS-010B ·
FR-RCP-008B · FR-SEC-010B · FR-SRV-007B · FR-TEN-002B · FR-TEN-009B · FR-TST-004B ·
FR-TST-005B · FR-TST-007B · FR-UX-001B · FR-GOV-002 · FR-GOV-005 · FR-GOV-006

They are satisfied by this repository containing no storage location, no payroll data, no
pickup or delivery domain, no accounting posting, no CRM correlation, no recipe module and
no supplier or courier surface. An empty repository satisfies them trivially — **that is
why M0R exists.** It establishes the clean baseline before anything can leak in.

**Six are positive obligations:**

| ID | Obligation | Where it is met at M0R |
|---|---|---|
| FR-GOV-001A | Empty repository conformance | `tools/verify_m0r_skeleton.py` reports PASS |
| FR-GOV-003 | Controlled reuse process from the frozen prototype | stated below; nothing reused |
| FR-SEC-015 | Pipeline fails on unknown/empty/skipped results | `planning/CI_TEST_MATRIX.md` |
| FR-TST-013 | Mandatory journeys mapped to tests, owner, evidence slots | package: `journeys.json`, 16 slices |
| FR-TST-014 | Active requirements mapped to component and test | package: `requirements.json`, 336/336 |
| FR-TST-019 | Per-milestone audit branch with immutable commands and decision | opens at M1 |

FR-TST-013 and FR-TST-014 are **planning maps, not tests.** Both are already carried in the
pinned package: all 16 mandatory journey slices are enumerated in
`docs/…/02_MACHINE_READABLE/journeys.json`, and all 336 active requirements carry both a
`component_path` and test links in `docs/…/02_MACHINE_READABLE/requirements.json`. The
`Requirements_Traceability_Matrix_v2.0.9.xlsx` workbook projects the same data. Evidence
slots stay empty until each gate populates them. This repository does not duplicate those
maps — duplication would create a second source that can drift from the pinned one.

---

## M1 entry conditions

M1 begins only when **all** of the following hold:

- independent review has approved M0R
- the repository contains no schema, migration or application code
- `/docs` holds the pinned v2.0.9 package, verified 91/91
- the planning artifacts in `planning/` exist
- CI runs the validators and fails closed

Migration `0001` is created at M1, not before.

---

## Reuse from the frozen prototype (FR-GOV-003)

`Hospitality-ERP` is a **frozen** research and architecture prototype. Under FR-GOV-006 no
Phase 1 release is cut from its branches; under FR-DAT-001 its migration history is never
imported.

Nothing has been reused from it in this repository. Any future reuse of a unit from it
requires, **before** inclusion: isolated review, dependency analysis, provenance recording,
and new tests written against the pinned package.

**Default position: write fresh.** The v1.1 codebase was judged unsuitable as a production
foundation at the first independent review.

---

## Change control on this document

This is a planning artifact of the repository, not pinned evidence. It may be revised as
gates close. The package under `/docs` may not — it is pinned, and any modification breaks
the chain back through five review cycles.
