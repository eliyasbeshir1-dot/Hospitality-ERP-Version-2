# Architecture, Security and Continuity Constraints

- Package: `Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9`
- Canonical source root: `cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96`
- Status: **Package M0 candidate - M0R and implementation are not authorized**

## Core architecture

- multi-tenant and outlet-isolated by default
- modular monolith with strict domain boundaries
- versioned APIs and reliable events
- exact money arithmetic
- append-only or reversal-based commerce records
- node-generated private keys and CSR-only certificate issuance
- cloud is never a writable dine-in fallback
- Phase 2/3 surfaces are physically absent from Phase 1 artifacts

## Tenant and outlet isolation

- Missing tenant/outlet context must return zero rows and permit zero writes.
- Use populated owner-side fixtures so zero-row tests cannot pass vacuously.
- Test sibling outlets inside the same tenant, not only different tenants.
- Test SELECT, INSERT, UPDATE and DELETE.
- Policies must contain both `USING` and `WITH CHECK` where applicable.
- Adding `outlet_id` later must automatically strengthen existing policies.
- API, jobs, files, caches, reports and sync paths are part of the isolation boundary.
- Production services reject owner, superuser, BYPASSRLS and maintenance database roles.

## Money and audit

- Do not use binary floating-point for money, percentages or quantity outcomes.
- Accepted orders, issued bills, payments, tips and cash movements are immutable or reversal-based.
- No tip is selected by default.
- Bill allocation and tip allocation are separate.
- A tip cannot hide an unpaid bill balance.
- Refunds and reversals require purpose-specific step-up, permission, reason and audit.
- Quick PIN cannot authorize sensitive financial actions.
- Split bill participants may choose different tips.

## M4/M5a printing boundary

M4 owns the minimum real printer path needed to issue a physical customer receipt. M5a adds durable local queueing, bounded retry, restart recovery, deduplication, printer health, outage continuity and reconciliation.

## M5a/M5b authority boundary

M5a provides focused local services but does not claim local authority. M5b adds same-QR DNS/TLS, bidirectional lease, authority sequence and fencing. The cloud remains a control plane/forwarder and is never a writable dine-in fallback.

## Certificate custody

The outlet node generates and retains the private key, submits only a certificate signing request, receives only the certificate chain, renews through DNS-01 automation and never exports the private key.
