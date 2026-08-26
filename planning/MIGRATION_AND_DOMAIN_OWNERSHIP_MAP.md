# Migration and Domain Ownership Map

**Repository:** `Hospitality-ERP-Version-2`
**Gate:** M0R — Repository Conformance
**Governing requirements:** FR-DAT-001, FR-GOV-001A
**Source of truth:** `docs/Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9/`

---

## Current state: no migration exists

This repository contains **no migration, no `.sql` file, no schema and no `migrations/`
directory.** Not even `0001`.

Migration `0001` is created at **M1**, after independent review approves this gate. That
sequencing is the requirement, not a convention — FR-DAT-001 and FR-GOV-001A both bind it.

`tools/verify_m0r_skeleton.py` fails the build on any `.sql` file, any `.prisma` file, any
`migrations/`, `db/`, `database/`, `schema/` or `models/` directory, and on any file
containing SQL DDL. That check runs in CI on every push.

---

## Ownership principle

**One domain owns each migration. No migration spans domains.**

Ownership follows the gate that introduces the requirement, so a migration is never written
before its governing gate. The gate at which each of the 336 active requirements is
introduced is recorded in `docs/…/02_MACHINE_READABLE/requirements.json` under
`introduced_at`; the component each maps to is recorded under `component_path`.

---

## Gate distribution of the 336 active requirements

Counts below are the `gate_counts` block of `docs/…/02_MACHINE_READABLE/requirements.json`,
and were re-derived from `active_requirements` when this document was written.

| Gate | Requirements | Domain focus |
|---|---:|---|
| M0 | 2 | package governance |
| M0R | 30 | repository conformance (24 fenced negatives) |
| M1 | 77 | foundation, security, tenancy, identity, data architecture |
| M2 | 49 | menu, localization, safety, tables, QR, sessions |
| M3 | 75 | orders, waiter, fulfillment, KDS, service requests, notifications |
| M4 | 55 | POS, checks, payments, tips, receipts, cash |
| M5a | 24 | outlet node, sync, local printing |
| M5b | 12 | same-QR DNS/TLS, reachability lease, authority fencing |
| M6 | 12 | deployment, backup, reporting, hardening |
| **Total** | **336** | |

---

## Planned migration ownership

Nothing in this table exists. It records which domain will own which block when migrations
begin at M1.

| Migration block | Owner domain | Gate | Content |
|---|---|---|---|
| `0001`–`00xx` | tenancy and identity | M1 | tenants, outlets, roles, memberships, RLS policies |
| next block | configuration and data architecture | M1 | policy store, numbering, audit, money types |
| next block | menu and safety | M2 | menus, variants, modifiers, allergens, translations |
| next block | tables and sessions | M2 | tables, QR tokens, guest sessions, carts |
| next block | orders and fulfillment | M3 | order aggregate, tickets, stations, service requests |
| next block | billing and payments | M4 | checks, payments, tips, receipts, cash shifts |
| next block | outlet edge | M5a | local store, outbox, inbox, sync cursors |
| next block | authority and routing | M5b | authority epoch, lease state, fence evidence |

**Exact numbering is assigned at M1.** Ranges are deliberately not pre-allocated, because
pre-allocation produces gaps and gaps invite out-of-order application.

---

## Hard rules for every migration, from `0001` onward

1. **Forward-only in production.** An applied migration is never edited (FR-DAT-016).
2. **Checksum-locked.** An edited migration fails preflight.
3. **No v1.1 inheritance.** The frozen prototype's migration history is never imported
   (FR-DAT-001). This repository starts its migration history at `0001`, at M1.
4. **Production roles only.** Tests run through the actual application roles, never a
   superuser (FR-DAT-017).
5. **Append-only where required.** Audit, financial ledgers and sync evidence are
   append-only or reversal-based (FR-DAT-008).
6. **Money is exact.** Fixed-point or integer minor units. Never binary floating point.

---

## Forbidden domains — never receive a migration

No table, column, enum value or index may be created, at any gate, for:

storage locations · inventory or stock · accounting or general ledger · payroll or employee
records · purchasing or procurement · supplier or courier · operational recipes or costing ·
loyalty, CRM or campaigns · pickup or delivery fulfilment

These are fenced by the 24 negative requirements introduced at M0R and enforced by the
forbidden-occurrence registry shipped in the package
(`docs/…/02_MACHINE_READABLE/forbidden_occurrence_registry.json`, validated in CI by
`docs/…/06_TOOLS/frozen_validator/forbidden_occurrence_validator.py`).

**A migration touching any of them is a P0 finding.** This holds even for a table that is
created but unused — rule 8 of the architecture conformance plan admits no dormant module.

---

## A note on the detection boundary

The occurrence registry closes the **authorization** problem: every occurrence of the
controlled vocabulary is explicitly classified. It does not close the **detection** problem.
A prohibited concept phrased in unknown vocabulary may go undetected, so migration review
remains a human obligation and is not discharged by a green pipeline. See
`planning/KNOWN_LIMITATIONS.md`.
