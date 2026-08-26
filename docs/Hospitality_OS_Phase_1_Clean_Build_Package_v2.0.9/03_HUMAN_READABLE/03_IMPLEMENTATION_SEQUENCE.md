# Implementation Sequence and Gate Closures

- Package: `Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9`
- Canonical source root: `cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96`
- Status: **Package M0 candidate - M0R and implementation are not authorized**

A milestone closes only on behavior executable with approved predecessors. Later capabilities may revalidate an earlier mechanism but cannot be used to close an earlier gate.

## M0 - Package M0

**Purpose.** Pin product, architecture, requirements, evidence and review package.

**Depends on.** None

**Requirements introduced.** 2

**Mandatory journeys.** None

**Exit criterion.** Codex independent review of this exact ZIP.

## M0R - Repository Conformance

**Purpose.** Create an empty documentation-only repository and CI/scanner plans.

**Depends on.** M0

**Requirements introduced.** 30

**Mandatory journeys.** None

**Exit criterion.** No database, migration, route, worker or UI exists.

## M1 - Foundation

**Purpose.** Create tenancy, identity, security, configuration, data architecture and migration 0001.

**Depends on.** M0R

**Requirements introduced.** 77

**Mandatory journeys.** None

**Exit criterion.** Real PostgreSQL and production-role isolation tests pass.

## M2 - Menu, QR and customer session

**Purpose.** Create multilingual menu, QR, tables, guest sessions and safety content.

**Depends on.** M1

**Requirements introduced.** 49

**Mandatory journeys.** None

**Exit criterion.** English/Amharic/Arabic customer surfaces and true Arabic RTL pass.

## M3 - Ordering and service

**Purpose.** Create customer/waiter orders, service requests, KDS and fulfillment.

**Depends on.** M2

**Requirements introduced.** 75

**Mandatory journeys.** GJ-01A, GJ-02, GJ-03A, GJ-04, GJ-05

**Exit criterion.** The three M3 language journeys pass without billing or local authority.

## M4 - POS, billing and settlement

**Purpose.** Create checks, separate tips, payments, cash shifts, receipts and minimum real printing.

**Depends on.** M3

**Requirements introduced.** 55

**Mandatory journeys.** GJ-01B, GJ-02B, GJ-03B, GJ-06, GJ-07

**Exit criterion.** Live pilot payment paths and physical/digital receipts pass.

## M5a - Outlet execution and resilience

**Purpose.** Create local node services, durable persistence, synchronization and resilient printing.

**Depends on.** M4

**Requirements introduced.** 24

**Mandatory journeys.** GJ-10

**Exit criterion.** Restart, retry, deduplication, reconnect and print recovery pass.

## M5b - Same-QR trust and authority

**Purpose.** Create DNS/TLS, bidirectional lease, authority sequence and fencing.

**Depends on.** M5a

**Requirements introduced.** 12

**Mandatory journeys.** GJ-08, GJ-09

**Exit criterion.** Same QR works under supported resolver conditions without split-brain or browser bypass.

## M6 - Production hardening

**Purpose.** Create production images, backup/restore, deployment, observability and final evidence.

**Depends on.** M5b

**Requirements introduced.** 12

**Mandatory journeys.** GJ-11, GJ-12, GJ-13

**Exit criterion.** Destructive restore, production roles, full scans and second-tenant evidence pass.
