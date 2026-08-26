# Build Control Plan

- Package: `Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9`
- Canonical source root: `cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96`
- Status: **Package M0 candidate - M0R and implementation are not authorized**

## Control principles

1. Build one milestone at a time.
2. Do not start a later milestone before the current gate is approved or adjudicated under FR-GOV-004.
3. Every route, table, worker, screen and test maps to an active requirement and gate.
4. Phase 2/3 surfaces are physically absent.
5. Reused prototype code is reviewed as third-party code.
6. Production-role tests, not owner/superuser tests, prove isolation.
7. Generated projections are rebuilt from canonical sources; manual edits are prohibited.

## Repository start rule

M0R creates an empty repository containing only the approved Package M0 documents, conformance plans and CI/scanner design. No database, schema, executable migration, application route, worker or UI is permitted.

## Migration start rule

PostgreSQL and migration `0001` begin at M1 after M0R approval or adjudication. No v1.1 migration is imported.

## Requirement ownership by gate

- **M0:** 2 requirements - Platform & Security: 1; Quality Engineering: 1
- **M0R:** 30 requirements - Platform & Security: 11; Service Execution: 6; Quality Engineering: 6; Customer Experience: 4; Edge & Operations: 1; Commerce & Payments: 1; Platform Engineering: 1
- **M1:** 77 requirements - Platform & Security: 57; Edge & Operations: 9; Quality Engineering: 9; Customer Experience: 2
- **M2:** 49 requirements - Customer Experience: 37; Platform Engineering: 9; Platform & Security: 2; Quality Engineering: 1
- **M3:** 75 requirements - Service Execution: 41; Customer Experience: 18; Platform Engineering: 9; Edge & Operations: 3; Platform & Security: 2; Quality Engineering: 2
- **M4:** 55 requirements - Commerce & Payments: 19; Platform Engineering: 16; Quality Engineering: 8; Customer Experience: 4; Platform & Security: 3; Edge & Operations: 2; Service Execution: 2; Billing & Payments: 1
- **M5a:** 24 requirements - Edge & Operations: 18; Platform & Security: 3; Outlet Edge & Operations: 1; Customer Experience: 1; Quality Engineering: 1
- **M5b:** 12 requirements - Edge & Operations: 11; Edge & Continuity: 1
- **M6:** 12 requirements - Edge & Operations: 7; Quality Engineering: 3; Platform & Security: 2
