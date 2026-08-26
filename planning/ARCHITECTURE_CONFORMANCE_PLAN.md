# Architecture Conformance Plan — M0R Planning Artifact

Describes what M1 onward will build. **Builds nothing.**

---

## Phase 1 scope

QR dine-in ordering · English, Amharic and Arabic · waiter service · KDS, bar, expo ·
POS and checks · separate optional tips · payments · receipts · outlet continuity during
internet outage.

**Not in Phase 1:** inventory, accounting, purchasing, payroll, recipes, costing, loyalty,
CRM, pickup, delivery. These are fenced by 24 M0R requirements.

Despite the repository name, **this is not an ERP**.

---

## Planned components

| Component | Gate | Purpose |
|---|---|---|
| Cloud API (Fastify/TypeScript) | M1 | tenancy, identity, configuration, domain services |
| PostgreSQL | M1 | single canonical store, RLS-enforced |
| Customer PWA | M2 | QR menu, cart, ordering, status — three languages |
| Waiter and KDS surfaces | M3 | order entry, ticket flow, expo |
| POS surface | M4 | checks, payments, tips, receipts, cash shifts |
| Outlet Continuity Node | M5a | local API, local PostgreSQL, sync worker, print agent |
| Same-QR routing | M5b | split-horizon DNS, per-outlet TLS, authority lease |

---

## Conformance rules carried into every gate

1. **Gate-local closure** — a gate closes only on behavior provable at that gate. 39 of the
   336 requirements are dual-gated with explicit revalidation gates.
2. **Deny by default** — API, database policy, jobs, cache and files fail closed on missing
   tenant, outlet, session or actor context.
3. **Exact money** — fixed-point or integer minor units. Never binary floating point.
4. **Bill and tip are separate** — separate values, separate records, separate reversal.
   No tip is selected by default.
5. **Payment matrix** — live: cash, external terminal recording, verified Telebirr and CBE
   Birr proof. Simulated until contracted: direct provider APIs. Prohibited: raw card data.
6. **One writable authority per outlet** — enforced by monotonic signed epoch with fence
   evidence before replacement.
7. **Real persistence in tests** — production roles, never a superuser.
8. **No dormant future modules** — no route, table, worker or screen for a fenced domain.

---

## M1 entry conditions

M1 begins only when **all** hold:

- Codex has approved M0R
- the skeleton contains no schema, migration or application code
- `/docs` holds the pinned v2.0.9 package, verified
- the three planning artifacts exist
- CI runs the validators and fails closed

---

## Reuse from the frozen prototype (FR-GOV-003)

Any unit reused from `Hospitality-ERP` requires, before inclusion: isolated review,
dependency analysis, provenance recording, and new tests written against this package.

Default position: **write fresh**. The v1.1 codebase was judged unsuitable as a production
foundation at the first independent review.
