# Migration and Domain Ownership Map — M0R Planning Artifact

**This is a plan. No migration exists at M0R.** Migration `0001` is created at M1, after
Codex approves this gate (FR-DAT-001, FR-GOV-001A).

---

## Ownership principle

One domain owns each migration. No migration spans domains. Ownership follows the gate that
introduces the requirement, so a migration is never written before its governing gate.

---

## Gate distribution of the 336 active requirements

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

---

## Planned migration ownership

| Migration range | Owner domain | Gate | Notes |
|---|---|---|---|
| `0001`–`00xx` | tenancy and identity | M1 | tenants, outlets, roles, memberships, RLS policies |
| next block | configuration and data architecture | M1 | policy store, numbering, audit, money types |
| next block | menu and safety | M2 | menus, variants, modifiers, allergens, translations |
| next block | tables and sessions | M2 | tables, QR tokens, guest sessions, carts |
| next block | orders and fulfillment | M3 | order aggregate, tickets, stations, service requests |
| next block | billing and payments | M4 | checks, payments, tips, receipts, cash shifts |
| next block | outlet edge | M5a | local store, outbox, inbox, sync cursors |
| next block | authority and routing | M5b | authority epoch, lease state, fence evidence |

Exact numbering is assigned at M1. Ranges are not pre-allocated, to avoid gaps.

---

## Hard rules

1. **Forward-only in production.** No editing an applied migration (FR-DAT-016).
2. **Checksum-locked.** An edited migration fails preflight.
3. **No v1.1 inheritance.** The frozen prototype's migration history is never imported.
4. **Production roles only.** Tests run through the actual application roles, never a
   superuser (FR-DAT-017).
5. **Append-only where required.** Audit, financial ledgers and sync evidence are
   append-only or reversal-based (FR-DAT-008).

---

## Forbidden domains — never receive a migration

No table, column, enum value or index may be created for:

storage locations · inventory or stock · accounting or general ledger · payroll or employee
records · purchasing or procurement · supplier or courier · operational recipes or costing ·
loyalty, CRM or campaigns · pickup or delivery fulfilment

These are fenced by 24 M0R requirements and enforced by the forbidden-occurrence registry.
A migration touching any of them is a P0 finding.
