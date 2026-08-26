# Implementation Brief - Locked Until Package M0 Approval

## Current instruction

Do not create a repository, database, migration, application route, worker, screen or UI.

## After Package M0 approval

1. Create M0R as an empty documentation-only repository.
2. Add the approved package, conformance plans and CI/scanner design.
3. Prove the forbidden-surface scanner and traceability controls.
4. Submit M0R for independent approval.
5. Only after M0R approval, begin M1 with PostgreSQL and migration `0001`.

## Build order

- **M0 Package M0:** Pin product, architecture, requirements, evidence and review package.
- **M0R Repository Conformance:** Create an empty documentation-only repository and CI/scanner plans.
- **M1 Foundation:** Create tenancy, identity, security, configuration, data architecture and migration 0001.
- **M2 Menu, QR and customer session:** Create multilingual menu, QR, tables, guest sessions and safety content.
- **M3 Ordering and service:** Create customer/waiter orders, service requests, KDS and fulfillment.
- **M4 POS, billing and settlement:** Create checks, separate tips, payments, cash shifts, receipts and minimum real printing.
- **M5a Outlet execution and resilience:** Create local node services, durable persistence, synchronization and resilient printing.
- **M5b Same-QR trust and authority:** Create DNS/TLS, bidirectional lease, authority sequence and fencing.
- **M6 Production hardening:** Create production images, backup/restore, deployment, observability and final evidence.
