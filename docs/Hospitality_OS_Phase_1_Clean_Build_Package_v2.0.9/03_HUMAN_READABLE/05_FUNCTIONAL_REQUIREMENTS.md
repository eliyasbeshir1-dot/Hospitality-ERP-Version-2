# Functional Requirements Register

**336 active requirements**

- Package: `Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9`
- Canonical source root: `cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96`
- Status: **Package M0 candidate - M0R and implementation are not authorized**

Requirements are ordered by introducing gate, domain and ID. Each entry states its executable gate-local behavior and later revalidation ownership.

# Gate M0

## Build Governance

### FR-GOV-004 - Milestone review and adjudication

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M0  
**Revalidated:** M0R, M1, M2, M3, M4, M5a, M5b, M6  
**Required behavior:** Do not begin a later milestone while any P0 remains unresolved, or while any P1 affects product scope, security, money, authority, milestone executability, acceptance completeness or canonical correctness. A P1 limited to publication, projection, wording, identifier or validator coverage may proceed only through recorded founder adjudication when canonical behavior is correct, runtime behavior cannot change, the defect remains visible and repair is scheduled. An adverse independent verdict pauses progression until the builder response, reviewer rebuttal and founder decision are recorded. Overrides name the affected requirement or rule and are re-examined at the next audit.

**Gate-local behavior:** Apply the blocker and adjudication rule to Package M0 and record the decision, affected requirement and scheduled repair.

**Later behavior:** Apply the rule at every later gate and re-examine each override at the next audit.

**Prerequisites:** None  
**Journeys:** None  
**Acceptance tests:** TST-M0-FR-GOV-004, TST-M0R-FR-GOV-004, TST-M1-FR-GOV-004, TST-M2-FR-GOV-004, TST-M3-FR-GOV-004, TST-M4-FR-GOV-004, TST-M5a-FR-GOV-004, TST-M5b-FR-GOV-004, TST-M6-FR-GOV-004

## Testing and Evidence

### FR-TST-017 - Anti-false-green and frozen negative controls

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M0  
**Revalidated:** M0R, M6  
**Required behavior:** Package M0 enumerates every critical planted negative control by milestone, protected property, deliberate break, expected failing test and expected failure signature. Zero tests, skipped tests, empty scans, stale artifacts and unsupported coverage fail. The registry is frozen before M0R and changes require review.

**Gate-local behavior:** The registry enumerates every control with all five attributes and is frozen before the repository exists.

**Later behavior:** The controls are planted in CI at M0R and re-proven against the production artifact at M6.

**Prerequisites:** None  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M0-FR-TST-017, TST-M0R-FR-TST-017, TST-M6-FR-TST-017

# Gate M0R

## Build Governance

### FR-GOV-001A - Empty repository conformance

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-GOV-001`  
**Introduced:** M0R  
**Revalidated:** None  
**Required behavior:** The repository contains only the approved package and conformance plans; a scan proves no schema, migration, route, worker or UI file exists.

**Gate-local behavior:** The repository contains only the approved package and conformance plans; a scan proves no schema, migration, route, worker or UI file exists.

**Later behavior:** None beyond M0R for this clause.

**Prerequisites:** FR-GOV-006  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-GOV-001A

### FR-GOV-002 - No dormant future modules

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M0R  
**Revalidated:** M1, M2, M3, M4, M5a, M5b, M6  
**Required behavior:** At Repository Conformance M0R and every later gate, prove the deployable Phase 1 surface contains no purchasing, inventory, accounting, HR, recipe, intelligence, supplier, loyalty, pickup or delivery routes, tables, workers, tests or screens.

**Gate-local behavior:** Scanner runs over the repository plan with one planted fixture per excluded domain and fails on each.

**Later behavior:** Every later gate adds deployable surface that must be rescanned.

**Prerequisites:** None  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M0R-FR-GOV-002, TST-M1-FR-GOV-002, TST-M2-FR-GOV-002, TST-M3-FR-GOV-002, TST-M4-FR-GOV-002, TST-M5a-FR-GOV-002, TST-M5b-FR-GOV-002, TST-M6-FR-GOV-002

### FR-GOV-003 - Controlled code reuse

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M0R  
**Revalidated:** M6  
**Required behavior:** Any reused unit from the frozen repository requires isolated review, dependency analysis, provenance recording and new tests written against this package before inclusion.

**Gate-local behavior:** A provenance register exists and the review/dependency-analysis process is proven on any unit proposed for reuse in the M0R plan.

**Later behavior:** Reuse decisions recur whenever code is written; the complete provenance audit is only possible against the final artifact.

**Prerequisites:** FR-GOV-006  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-GOV-003, TST-M6-FR-GOV-003

### FR-GOV-005 - Traceability authority

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M0R  
**Revalidated:** M1, M2, M3, M4, M5a, M5b, M6  
**Required behavior:** Every implemented route, table, worker, screen and test maps to an active requirement and gate in this package. Deferred requirements cannot appear in production artifacts.

**Gate-local behavior:** The migration/domain ownership map maps every planned unit to an active requirement and gate; no deferred requirement appears.

**Later behavior:** Traceability must be re-proven as each gate implements real routes, tables, workers, screens and tests.

**Prerequisites:** FR-GOV-001A  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M0R-FR-GOV-005, TST-M1-FR-GOV-005, TST-M2-FR-GOV-005, TST-M3-FR-GOV-005, TST-M4-FR-GOV-005, TST-M5a-FR-GOV-005, TST-M5b-FR-GOV-005, TST-M6-FR-GOV-005

### FR-GOV-006 - Frozen prototype

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M0R  
**Revalidated:** None  
**Required behavior:** Mark the v1.1 repository as a frozen research and architecture prototype; no Phase 1 release is cut from its branches.

**Gate-local behavior:** The v1.1 repository is marked frozen and the new repository is established as the only release source.

**Later behavior:** None beyond M0R for this clause.

**Prerequisites:** None  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-GOV-006

## Carts and Orders

### FR-ORD-001C - No pickup or delivery order domain

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-ORD-001`  
**Introduced:** M0R  
**Revalidated:** M3, M6  
**Required behavior:** Scanner proves no pickup or delivery policy, fulfillment field, route or screen exists.

**Gate-local behavior:** Scanner proves no pickup or delivery policy, fulfillment field, route or screen exists.

**Later behavior:** Absence holds as the order surface grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-ORD-001C, TST-M3-FR-ORD-001C, TST-M6-FR-ORD-001C

### FR-ORD-012B - No stock or accounting reversal

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-ORD-012`  
**Introduced:** M0R  
**Revalidated:** M4, M6  
**Required behavior:** Scanner proves no stock or general-ledger posting path exists.

**Gate-local behavior:** Scanner proves no stock or general-ledger posting path exists.

**Later behavior:** Absence holds as the void and refund surfaces grow.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-ORD-012B, TST-M4-FR-ORD-012B, TST-M6-FR-ORD-012B

### FR-ORD-016B - No delivery, inventory or accounting events

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-ORD-016`  
**Introduced:** M0R  
**Revalidated:** M3, M6  
**Required behavior:** Scanner proves no delivery, inventory or accounting event type exists in the timeline model.

**Gate-local behavior:** Scanner proves no delivery, inventory or accounting event type exists in the timeline model.

**Later behavior:** Absence holds as event catalog grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-ORD-016B, TST-M3-FR-ORD-016B, TST-M6-FR-ORD-016B

### FR-ORD-019B - No campaign or CRM correlation

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-ORD-019`  
**Introduced:** M0R  
**Revalidated:** M3, M6  
**Required behavior:** Scanner proves no campaign or CRM correlation field, route or screen exists, including morphological variants of "campaign".

**Gate-local behavior:** Scanner proves no campaign or CRM correlation field, route or screen exists, including morphological variants of "campaign".

**Later behavior:** Absence holds as the correlation model grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-ORD-019B, TST-M3-FR-ORD-019B, TST-M6-FR-ORD-019B

## Configuration and Setup

### FR-CFG-002B - No deferred policy categories

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-CFG-002`  
**Introduced:** M0R  
**Revalidated:** M1, M6  
**Required behavior:** Scanner proves no Phase 2/3 policy category is present in the plan and schema.

**Gate-local behavior:** Scanner proves no Phase 2/3 policy category is present in the plan and schema.

**Later behavior:** Absence holds as configuration surface grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-CFG-002B, TST-M1-FR-CFG-002B, TST-M6-FR-CFG-002B

### FR-CFG-005B - No deferred feature surface

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-CFG-005`  
**Introduced:** M0R  
**Revalidated:** M1, M6  
**Required behavior:** The Phase 1 artifact contains no deferred Phase 2/3 route, worker, table or screen, regardless of entitlement configuration.

**Gate-local behavior:** The scanner fails on a planted deferred route, worker, table and screen and confirms their absence from the repository plan.

**Later behavior:** Re-scan the first executable artifact at M1 and the complete production artifact at M6.

**Prerequisites:** FR-GOV-002  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M0R-FR-CFG-005B, TST-M1-FR-CFG-005B, TST-M6-FR-CFG-005B

## Kitchen/Bar/Expo Fulfillment

### FR-FUL-016B - No inventory or recipe-consumption posting

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-FUL-016`  
**Introduced:** M0R  
**Revalidated:** M3, M6  
**Required behavior:** Scanner proves no inventory or recipe-consumption entry is produced by waste recording.

**Gate-local behavior:** Scanner proves no inventory or recipe-consumption entry is produced by waste recording.

**Later behavior:** Absence holds as the waste surface grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-FUL-016B, TST-M3-FR-FUL-016B, TST-M6-FR-FUL-016B

## Menu and Pricing

### FR-MNU-002B - No customer-segment targeting

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-MNU-002`  
**Introduced:** M0R  
**Revalidated:** M2, M6  
**Required behavior:** Scanner proves no customer-segment field, assignment rule or screen exists.

**Gate-local behavior:** Scanner proves no customer-segment field, assignment rule or screen exists.

**Later behavior:** Absence holds as the menu surface grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-MNU-002B, TST-M2-FR-MNU-002B, TST-M6-FR-MNU-002B

## Outlet Edge and Synchronization

### FR-EDG-002B - No deferred local modules

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** split_successor from `FR-EDG-002`  
**Introduced:** M0R  
**Revalidated:** M5a, M6  
**Required behavior:** Scanner proves no ERP or intelligence module is present in the node plan or image manifest.

**Gate-local behavior:** Scanner proves no ERP or intelligence module is present in the node plan or image manifest.

**Later behavior:** Absence holds as the node image is built and shipped.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-EDG-002B, TST-M5a-FR-EDG-002B, TST-M6-FR-EDG-002B

## Payments

### FR-PAY-010B - No accounting journal posting

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** split_successor from `FR-PAY-010`  
**Introduced:** M0R  
**Revalidated:** M4, M6  
**Required behavior:** Scanner proves no journal entry, ledger posting, accounting entity, field, route, screen or positive accounting test exists, including singular and plural morphological variants.

**Gate-local behavior:** Scanner proves no journal entry, ledger posting, accounting entity, field, route, screen or positive accounting test exists, including singular and plural morphological variants.

**Later behavior:** Absence holds as the payment surface grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-PAY-010B, TST-M4-FR-PAY-010B, TST-M6-FR-PAY-010B

## Recipes and Costing

### FR-RCP-008B - No operational recipe module

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** split_successor from `FR-RCP-008`  
**Introduced:** M0R  
**Revalidated:** M2, M6  
**Required behavior:** Scanner proves no recipe module, table or route exists.

**Gate-local behavior:** Scanner proves no recipe module, table or route exists.

**Later behavior:** Absence holds as schema grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-RCP-008B, TST-M2-FR-RCP-008B, TST-M6-FR-RCP-008B

## Security and Data Protection

### FR-SEC-010B - No employee or payroll data

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-SEC-010`  
**Introduced:** M0R  
**Revalidated:** M1, M6  
**Required behavior:** Scanner proves no employee or payroll field, table or test exists.

**Gate-local behavior:** Scanner proves no employee or payroll field, table or test exists.

**Later behavior:** Absence holds as schema grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-SEC-010B, TST-M1-FR-SEC-010B, TST-M6-FR-SEC-010B

### FR-SEC-015 - Vulnerability pipeline

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M0R  
**Revalidated:** M1, M6  
**Required behavior:** The vulnerability pipeline fails on unknown, empty, skipped or unsupported coverage and tests the actual production artifacts with planted negative controls.

**Gate-local behavior:** CI design proves the pipeline fails closed on unknown/empty/skipped/unsupported results, verified with planted controls in the CI plan.

**Later behavior:** Testing the actual production artifacts requires those artifacts to exist.

**Prerequisites:** FR-GOV-002  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M0R-FR-SEC-015, TST-M1-FR-SEC-015, TST-M6-FR-SEC-015

## Service Requests

### FR-SRV-007B - No workforce or attendance record

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-SRV-007`  
**Introduced:** M0R  
**Revalidated:** M3, M6  
**Required behavior:** Scanner proves no roster, shift, break, attendance, timekeeping, payroll or employment-history field or table exists, and presence records carry a retention bound.

**Gate-local behavior:** Scanner proves no roster, shift, break, attendance, timekeeping, payroll or employment-history field or table exists, and presence records carry a retention bound.

**Later behavior:** Absence holds as the staff surface grows.

**Prerequisites:** FR-GOV-002, FR-SEC-010B  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-SRV-007B, TST-M3-FR-SRV-007B, TST-M6-FR-SRV-007B

## Staff POS and Outlet UX

### FR-POS-003C - No pickup or delivery ordering

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-POS-003`  
**Introduced:** M0R  
**Revalidated:** M3, M4, M6  
**Required behavior:** Scanner proves no pickup or delivery order-creation path, field or screen exists.

**Gate-local behavior:** Scanner proves no pickup or delivery order-creation path, field or screen exists.

**Later behavior:** Absence holds as the staff ordering surface grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-POS-003C, TST-M3-FR-POS-003C, TST-M4-FR-POS-003C, TST-M6-FR-POS-003C

### FR-POS-010B - No pickup or delivery search

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-POS-010`  
**Introduced:** M0R  
**Revalidated:** M4, M6  
**Required behavior:** Scanner proves no pickup-code or delivery search field, index or screen exists.

**Gate-local behavior:** Scanner proves no pickup-code or delivery search field, index or screen exists.

**Later behavior:** Absence holds as the search surface grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-POS-010B, TST-M4-FR-POS-010B, TST-M6-FR-POS-010B

## Tenant and Commercial Control

### FR-TEN-002B - No storage-location entity

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-TEN-002`  
**Introduced:** M0R  
**Revalidated:** M1, M6  
**Required behavior:** Scanner proves absence of any storage-location entity in the repository plan and, from M1, in schema and code.

**Gate-local behavior:** Scanner proves absence of any storage-location entity in the repository plan and, from M1, in schema and code.

**Later behavior:** Absence must hold as schema and application surface grow.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-TEN-002B, TST-M1-FR-TEN-002B, TST-M6-FR-TEN-002B

### FR-TEN-009B - No later-domain registry entries

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-TEN-009`  
**Introduced:** M0R  
**Revalidated:** M1, M6  
**Required behavior:** Scanner proves no excluded-domain enumeration value or registry entry exists.

**Gate-local behavior:** Scanner proves no excluded-domain enumeration value or registry entry exists.

**Later behavior:** Absence holds as configuration surface grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-TEN-009B, TST-M1-FR-TEN-009B, TST-M6-FR-TEN-009B

## Testing and Evidence

### FR-TST-004B - No supplier or courier contract tests

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** split_successor from `FR-TST-004`  
**Introduced:** M0R  
**Revalidated:** M4, M6  
**Required behavior:** Scanner proves no supplier or courier port, simulator or contract test exists.

**Gate-local behavior:** Scanner proves no supplier or courier port, simulator or contract test exists.

**Later behavior:** Absence holds as the port set grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-TST-004B, TST-M4-FR-TST-004B, TST-M6-FR-TST-004B

### FR-TST-005B - No later-channel or supplier journeys

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** split_successor from `FR-TST-005`  
**Introduced:** M0R  
**Revalidated:** M6  
**Required behavior:** Scanner proves no pickup, delivery, supplier or Phase 2 back-office journey or test exists.

**Gate-local behavior:** Scanner proves no pickup, delivery, supplier or Phase 2 back-office journey or test exists.

**Later behavior:** Absence holds as the journey set grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-TST-005B, TST-M6-FR-TST-005B

### FR-TST-007B - No stock, supplier or delivery races

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** split_successor from `FR-TST-007`  
**Introduced:** M0R  
**Revalidated:** M6  
**Required behavior:** Scanner proves no stock, supplier or delivery concurrency test exists.

**Gate-local behavior:** Scanner proves no stock, supplier or delivery concurrency test exists.

**Later behavior:** Absence holds as the concurrency suite grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-TST-007B, TST-M6-FR-TST-007B

### FR-TST-013 - Golden journeys

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M0R  
**Revalidated:** M3, M4, M5a, M5b, M6  
**Required behavior:** Map every mandatory journey to test IDs, evidence, owner and defect status.

**Gate-local behavior:** Every mandatory journey slice is mapped to planned test IDs, owner and evidence slots before coding begins.

**Later behavior:** Evidence and defect status accrue as each gate executes its journeys.

**Prerequisites:** FR-GOV-005  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M0R-FR-TST-013, TST-M3-FR-TST-013, TST-M4-FR-TST-013, TST-M5a-FR-TST-013, TST-M5b-FR-TST-013, TST-M6-FR-TST-013

### FR-TST-014 - Traceability

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M0R  
**Revalidated:** M1, M2, M3, M4, M5a, M5b, M6  
**Required behavior:** Map every P0/P1 requirement to implementation component, automated/manual test and acceptance evidence.

**Gate-local behavior:** Every active requirement maps to a planned component and test before coding begins.

**Later behavior:** Each implementing gate populates real components, tests and evidence.

**Prerequisites:** FR-GOV-005  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M0R-FR-TST-014, TST-M1-FR-TST-014, TST-M2-FR-TST-014, TST-M3-FR-TST-014, TST-M4-FR-TST-014, TST-M5a-FR-TST-014, TST-M5b-FR-TST-014, TST-M6-FR-TST-014

### FR-TST-019 - Independent milestone audit

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M0R  
**Revalidated:** M1, M2, M3, M4, M5a, M5b, M6  
**Required behavior:** Each milestone has a Codex audit branch containing immutable commands, evidence, defects and a merge/no-merge decision against the exact commit.

**Gate-local behavior:** The audit branch structure exists and the M0R review itself produces immutable commands, evidence and a decision against an exact commit.

**Later behavior:** Every subsequent gate produces its own audit branch and decision.

**Prerequisites:** FR-GOV-004  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-TST-019, TST-M1-FR-TST-019, TST-M2-FR-TST-019, TST-M3-FR-TST-019, TST-M4-FR-TST-019, TST-M5a-FR-TST-019, TST-M5b-FR-TST-019, TST-M6-FR-TST-019

## UX and Accessibility

### FR-UX-001B - No pickup or delivery UX

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-UX-001`  
**Introduced:** M0R  
**Revalidated:** M2, M6  
**Required behavior:** Scanner proves no pickup or delivery screen or journey exists.

**Gate-local behavior:** Scanner proves no pickup or delivery screen or journey exists.

**Later behavior:** Absence holds as customer UX grows.

**Prerequisites:** FR-GOV-002  
**Journeys:** None  
**Acceptance tests:** TST-M0R-FR-UX-001B, TST-M2-FR-UX-001B, TST-M6-FR-UX-001B

# Gate M1

## Build Governance

### FR-GOV-001B - Database and migration start

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-GOV-001`  
**Introduced:** M1  
**Revalidated:** None  
**Required behavior:** Migration 0001 is created and applied at M1 only, with M0R approval recorded as its precondition.

**Gate-local behavior:** Migration 0001 is created and applied at M1 only, with M0R approval recorded as its precondition.

**Later behavior:** None beyond M1 for this clause.

**Prerequisites:** FR-GOV-001A, FR-DAT-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-GOV-001B

## Commercial Multi-tenant Product

### FR-COM-002 - White labeling

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4, M5b  
**Required behavior:** Support tenant brand/domain/templates while retaining optional platform attribution by contract.

**Gate-local behavior:** Brand and template selection resolve per tenant with configurable platform attribution.

**Later behavior:** Receipt templates render at M4; per-outlet public domains take effect at M5b.

**Prerequisites:** FR-CFG-006  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-COM-002, TST-M4-FR-COM-002, TST-M5b-FR-COM-002

### FR-COM-007 - Configuration templates

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M2, M4  
**Required behavior:** Offer reusable industry templates without hard-coding one tenant’s menu, tax, workflow or language.

**Gate-local behavior:** Templates exist as data with no tenant-specific constant in code.

**Later behavior:** Menu and language templates become substantive at M2; tax and workflow templates at M3/M4.

**Prerequisites:** FR-TEN-003  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-COM-007, TST-M2-FR-COM-007, TST-M4-FR-COM-007

### FR-COM-009 - Version support

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M5a, M5b  
**Required behavior:** Track supported application, schema, edge and connector versions per tenant/deployment.

**Gate-local behavior:** Application and schema versions are tracked per tenant/deployment.

**Later behavior:** Edge and connector versions exist only once the node and connectors exist; compatibility posture is part of the M5b lease.

**Prerequisites:** FR-TEN-003  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-COM-009, TST-M5a-FR-COM-009, TST-M5b-FR-COM-009

### FR-COM-010 - Commercial neutrality

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M2, M4, M6  
**Required behavior:** No product screen or API assumes the first internal tenant, Horeca Addis or a specific payment provider.

**Gate-local behavior:** No hard-coded tenant identifier or provider name in the M1 API surface.

**Later behavior:** Customer screens at M2, payment provider surfaces at M4, and the full production artifact at M6.

**Prerequisites:** FR-COM-007  
**Journeys:** GJ-13  
**Acceptance tests:** TST-M1-FR-COM-010, TST-M2-FR-COM-010, TST-M4-FR-COM-010, TST-M6-FR-COM-010

## Configuration and Setup

### FR-CFG-001A - Organizational setup

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-CFG-001`  
**Introduced:** M1  
**Revalidated:** None  
**Required behavior:** A guided setup creates the tenant, brand/legal entity, first outlet and initial administrator.

**Gate-local behavior:** Complete the organizational setup and verify that the new administrator can access only the created tenant and outlet.

**Later behavior:** 

**Prerequisites:** FR-TEN-002A, FR-AUTH-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-CFG-001A

### FR-CFG-002A - Phase 1 policy engine

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-CFG-002`  
**Introduced:** M1  
**Revalidated:** M3, M4, M5a  
**Required behavior:** Policy records for the named Phase 1 categories exist with validation and effective dating.

**Gate-local behavior:** Policy records for the named Phase 1 categories exist with validation and effective dating.

**Later behavior:** Policy enforcement is provable only where the governed behavior exists: ordering/service/cancellation at M3, discount/refund/tip/cash/approval at M4, local continuity at M5a.

**Prerequisites:** FR-TEN-003  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-CFG-002A, TST-M3-FR-CFG-002A, TST-M4-FR-CFG-002A, TST-M5a-FR-CFG-002A

### FR-CFG-003 - Reason codes

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M4, M5a  
**Required behavior:** Manage localized reason-code sets for order cancellation, void, refund, discount, complimentary item, payment reversal, tip correction, service failure, printer failure and manager override.

**Gate-local behavior:** Localized reason-code sets are managed as configuration data with the Phase 1 category list.

**Later behavior:** Each code is exercised only where its action exists: cancellation and service failure at M3, void/refund/discount/complimentary/reversal/tip correction/override at M4, printer failure at M5a.

**Prerequisites:** FR-TEN-003  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-CFG-003, TST-M3-FR-CFG-003, TST-M4-FR-CFG-003, TST-M5a-FR-CFG-003

### FR-CFG-004 - Numbering

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4  
**Required behavior:** Generate collision-safe human document numbers by tenant/legal entity/outlet/document type and fiscal period.

**Gate-local behavior:** Numbering service issues collision-safe numbers under concurrency for the document types defined at M1.

**Later behavior:** Bill and receipt document types are numbered when they exist.

**Prerequisites:** FR-DAT-003  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-CFG-004, TST-M4-FR-CFG-004

### FR-CFG-005A - Deny-by-default entitlements

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-CFG-005`  
**Introduced:** M1  
**Revalidated:** None  
**Required behavior:** Feature entitlements resolve deny-by-default at tenant, legal-entity and outlet scope.

**Gate-local behavior:** Unknown, absent or disabled entitlement values deny the feature and expose no route or operation.

**Later behavior:** 

**Prerequisites:** FR-TEN-004  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-CFG-005A

### FR-CFG-006 - Branding

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4, M5b  
**Required behavior:** Configure logos, colors, receipt/footer text, contact data and public-domain mappings without application forks.

**Gate-local behavior:** Branding attributes are configurable per tenant and consumed from configuration rather than build-time constants.

**Later behavior:** Receipt/footer text is only rendered on a real receipt at M4; public-domain mapping only takes effect with per-outlet hostname routing at M5b.

**Prerequisites:** FR-TEN-003  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-CFG-006, TST-M4-FR-CFG-006, TST-M5b-FR-CFG-006

### FR-CFG-007A - Non-production demo fixtures

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-CFG-007`  
**Introduced:** M1  
**Revalidated:** None  
**Required behavior:** Demo fixtures are explicitly marked and reset works only in non-production environments.

**Gate-local behavior:** Demo fixtures are explicitly marked and reset works only in non-production environments.

**Later behavior:** None beyond M1 for this clause.

**Prerequisites:** FR-DAT-013  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-CFG-007A

## Data Architecture

### FR-DAT-001 - SQL-first migrations

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M6  
**Required behavior:** Use a new ordered SQL migration history beginning at 0001. Build from an empty PostgreSQL database and test upgrades only from approved baselines of this package; never import the v1.1 migration history.

**Gate-local behavior:** Migration 0001 applies to an empty database; ordered history builds cleanly; no v1.1 migration is present.

**Later behavior:** Upgrade from a prior approved baseline is exercised with a populated schema.

**Prerequisites:** FR-GOV-001A  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M1-FR-DAT-001, TST-M6-FR-DAT-001

### FR-DAT-002 - Constraints

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M4  
**Required behavior:** Enforce tenant keys, foreign keys, uniqueness, money/quantity checks and valid state relationships in the database where practical.

**Gate-local behavior:** Constraints exist and reject invalid rows for the M1 schema.

**Later behavior:** Order and fulfillment state relationships at M3; financial state relationships at M4.

**Prerequisites:** FR-DAT-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-DAT-002, TST-M3-FR-DAT-002, TST-M4-FR-DAT-002

### FR-DAT-003 - Identifiers

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** None  
**Required behavior:** Use opaque UUID/ULID identifiers and separate human numbers; never rely on mutable external IDs.

**Gate-local behavior:** All primary identifiers are opaque; human numbers are separate columns.

**Later behavior:** None beyond M1.

**Prerequisites:** FR-DAT-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-DAT-003

### FR-DAT-004 - Timestamps

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4, M5a  
**Required behavior:** Store UTC instants plus outlet timezone context and use database/server time for authoritative events.

**Gate-local behavior:** Timestamps are UTC with outlet timezone context; authoritative events use server time.

**Later behavior:** Cash-shift and fiscal-period boundaries make timezone correctness financially material at M4; outlet-local event time under outage at M5a.

**Prerequisites:** FR-TEN-002A  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-DAT-004, TST-M4-FR-DAT-004, TST-M5a-FR-DAT-004

### FR-DAT-005 - Money

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4  
**Required behavior:** Represent money with exact fixed-point decimal or integer-minor-unit types and explicit currency. JavaScript binary floating point cannot determine financial outcomes.

**Gate-local behavior:** Money columns use exact types with explicit currency; no float path exists in the M1 code.

**Later behavior:** Actual financial computation (bill, tax, service charge, tip, allocation) occurs at M4.

**Prerequisites:** FR-DAT-001  
**Journeys:** GJ-06  
**Acceptance tests:** TST-M1-FR-DAT-005, TST-M4-FR-DAT-005

### FR-DAT-006 - Quantity

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4  
**Required behavior:** Represent quantities and percentages with explicit precision, rounding and validation. Tips and bill totals use deterministic exact arithmetic.

**Gate-local behavior:** Quantity/percentage precision, rounding mode and validation are defined and enforced.

**Later behavior:** Tip and bill total arithmetic exists only at M4.

**Prerequisites:** FR-DAT-005  
**Journeys:** GJ-06  
**Acceptance tests:** TST-M1-FR-DAT-006, TST-M4-FR-DAT-006

### FR-DAT-007 - Optimistic concurrency

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M4  
**Required behavior:** Require expected version for mutable aggregates and return explicit conflict outcomes.

**Gate-local behavior:** Mutable aggregates carry a version and concurrent writes return an explicit conflict.

**Later behavior:** Order and check aggregates are the operationally contended ones.

**Prerequisites:** FR-DAT-002  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-DAT-007, TST-M3-FR-DAT-007, TST-M4-FR-DAT-007

### FR-DAT-009 - Soft lifecycle

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M2, M3  
**Required behavior:** Deactivate/archive master data while preserving referenced historical versions.

**Gate-local behavior:** Master records deactivate/archive without breaking references; historical versions remain readable.

**Later behavior:** Menu items and prices are the first heavily versioned master data; order snapshots reference them.

**Prerequisites:** FR-DAT-002  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-DAT-009, TST-M2-FR-DAT-009, TST-M3-FR-DAT-009

### FR-DAT-013 - Seed data

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M2  
**Required behavior:** Seed two differently branded tenants and at least two outlets in one tenant with English, Amharic and Arabic content to prove neutrality and outlet isolation.

**Gate-local behavior:** Two branded tenants and two outlets are seeded and isolation is provable at the M1 surface.

**Later behavior:** Three-language content requires the localization and menu surfaces.

**Prerequisites:** FR-TEN-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-DAT-013, TST-M2-FR-DAT-013

### FR-DAT-015 - Schema documentation

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4, M6  
**Required behavior:** Generate a current schema/domain catalog and relationship diagrams from the implemented model.

**Gate-local behavior:** Catalog and diagrams generate from the live schema and match it.

**Later behavior:** The catalog must remain current as the schema grows.

**Prerequisites:** FR-DAT-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-DAT-015, TST-M4-FR-DAT-015, TST-M6-FR-DAT-015

### FR-DAT-016 - Migration rollback

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M6  
**Required behavior:** Migrations are forward-only in production with checksum locking, preflight, backup and tested recovery; do not edit an applied migration.

**Gate-local behavior:** Checksum locking and preflight reject edited migrations; forward-only policy enforced.

**Later behavior:** Backup-and-tested-recovery around a production migration requires production backup capability.

**Prerequisites:** FR-DAT-001  
**Journeys:** GJ-11  
**Acceptance tests:** TST-M1-FR-DAT-016, TST-M6-FR-DAT-016

### FR-DAT-017 - Test realism

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4, M5a  
**Required behavior:** Run integration, migration, RLS, synchronization and financial tests against real PostgreSQL and the actual application roles.

**Gate-local behavior:** Integration, migration and RLS tests execute against real PostgreSQL using production roles, not a superuser.

**Later behavior:** Financial tests exist at M4; synchronization tests at M5a.

**Prerequisites:** FR-DAT-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-DAT-017, TST-M4-FR-DAT-017, TST-M5a-FR-DAT-017

### FR-DAT-018 - Retention

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4, M5a  
**Required behavior:** Apply configurable retention/archive policies without breaking ledger/audit integrity.

**Gate-local behavior:** Retention/archive policy is configurable and cannot delete append-only ledger or audit rows.

**Later behavior:** Financial ledgers exist at M4; archived synchronization evidence at M5a.

**Prerequisites:** FR-DAT-002, FR-SEC-009  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-DAT-018, TST-M4-FR-DAT-018, TST-M5a-FR-DAT-018

## Deployment and Operations

### FR-OPS-001 - Environment validation

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M5a, M6  
**Required behavior:** Validate required environment, role, URLs, certificates, paths, binaries and outlet identity before the process's first healthy/startup claim. Reject owner, superuser, BYPASSRLS and maintenance credentials.

**Gate-local behavior:** The cloud process refuses to report healthy under owner, superuser, BYPASSRLS or maintenance credentials and validates environment, paths and binaries first.

**Later behavior:** The outlet node is a second process with its own identity and certificate checks; the production artifact is the final subject.

**Prerequisites:** FR-DAT-017, FR-SEC-001  
**Journeys:** GJ-10, GJ-12  
**Acceptance tests:** TST-M1-FR-OPS-001, TST-M5a-FR-OPS-001, TST-M6-FR-OPS-001

### FR-OPS-002 - Health endpoints

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M5a, M6  
**Required behavior:** Health and readiness endpoints truthfully verify database migrations, production-role access, outlet authority, required jobs, local storage, printer status and synchronization dependencies appropriate to each service.

**Gate-local behavior:** Cloud health truthfully verifies migrations, production-role access and required jobs, and reports unhealthy when any is unavailable.

**Later behavior:** Outlet authority, local storage, printer status and synchronization dependencies exist on the node.

**Prerequisites:** FR-OPS-001  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M1-FR-OPS-002, TST-M5a-FR-OPS-002, TST-M6-FR-OPS-002

### FR-OPS-003 - Structured logs

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M5a  
**Required behavior:** Log correlation, tenant/outlet, actor/service, event and error classification with redaction.

**Gate-local behavior:** Cloud logs carry correlation, tenant/outlet, actor, event and error classification with sensitive values redacted.

**Later behavior:** The node emits its own log stream that must satisfy the same contract.

**Prerequisites:** FR-DAT-004, FR-SEC-007  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M1-FR-OPS-003, TST-M5a-FR-OPS-003

### FR-OPS-004 - Metrics/tracing

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M6  
**Required behavior:** Measure request/job/integration latency, error, queue and domain SLA using replaceable observability providers.

**Gate-local behavior:** Latency, error and queue metrics emit through a replaceable provider interface.

**Later behavior:** Domain SLA measures and production thresholds are confirmed on the deployed artifact.

**Prerequisites:** FR-OPS-003  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-OPS-004, TST-M6-FR-OPS-004

### FR-OPS-005 - Background jobs

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M5a  
**Required behavior:** Only Phase 1 background jobs are included and advertised. Readiness is unhealthy when an advertised job cannot perform real work.

**Gate-local behavior:** Only Phase 1 jobs are registered and readiness turns unhealthy when an advertised job cannot do real work.

**Later behavior:** Notification jobs arrive at M3 and synchronization jobs at M5a; each must satisfy the same rule.

**Prerequisites:** FR-OPS-002, FR-GOV-002  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M1-FR-OPS-005, TST-M3-FR-OPS-005, TST-M5a-FR-OPS-005

### FR-OPS-008 - Deployment automation

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M5a, M6  
**Required behavior:** Build deterministic cloud and outlet production artifacts from clean source; route/module checks run immediately after the canonical build without a second hidden profile build.

**Gate-local behavior:** The cloud artifact builds deterministically from clean source and route/module checks run against that same build with no second profile build.

**Later behavior:** The outlet node artifact is built at M5a; both production artifacts are confirmed at M6.

**Prerequisites:** FR-GOV-002  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M1-FR-OPS-008, TST-M5a-FR-OPS-008, TST-M6-FR-OPS-008

### FR-OPS-020 - Production-role readiness

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M5a, M6  
**Required behavior:** API, outlet node, workers, backup and restore pass readiness using exact least-privileged production identities; owner, superuser or maintenance fallback is forbidden.

**Gate-local behavior:** API and workers pass readiness under exact least-privileged production identities with no fallback path.

**Later behavior:** The outlet node is a further identity at M5a; backup and restore identities are exercised at M6.

**Prerequisites:** FR-OPS-001, FR-DAT-017  
**Journeys:** GJ-11  
**Acceptance tests:** TST-M1-FR-OPS-020, TST-M5a-FR-OPS-020, TST-M6-FR-OPS-020

### FR-OPS-021 - Ordinary cross-platform commands

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M6  
**Required behavior:** The documented ordinary Windows and Linux commands discover required tools or fail clearly; acceptance cannot depend on CI-only PATH or environment injection.

**Gate-local behavior:** The documented commands run on both platforms from a clean shell and fail clearly when a tool is missing.

**Later behavior:** The complete command set including node and backup operations is confirmed at M6.

**Prerequisites:** FR-OPS-008  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M1-FR-OPS-021, TST-M6-FR-OPS-021

## Identity and Authentication

### FR-AUTH-001 - Staff login

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** None  
**Required behavior:** Support verified phone or email login, secure password or OTP flows and provider-adapter replacement.

**Gate-local behavior:** Staff authenticate by verified phone or email with password or OTP; the provider adapter is replaceable behind an interface.

**Later behavior:** None beyond M1 for this clause.

**Prerequisites:** FR-DAT-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-AUTH-001

### FR-AUTH-004 - Session management

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M5a  
**Required behavior:** List and revoke sessions/devices; rotate tokens; invalidate on security events and role removal.

**Gate-local behavior:** Sessions and devices are listable and revocable; tokens rotate; role removal invalidates access immediately.

**Later behavior:** Edge-node and print-agent principals become revocable subjects when they exist.

**Prerequisites:** FR-AUTH-001, FR-AUTH-008  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-AUTH-004, TST-M5a-FR-AUTH-004

### FR-AUTH-005 - Quick PIN

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4  
**Required behavior:** Trusted outlet terminals may use staff quick PIN for low-risk re-entry only; refunds, voids, high discounts, configuration and other sensitive actions require step-up authentication.

**Gate-local behavior:** Quick PIN re-entry works only on registered trusted terminals and only for low-risk actions. | Configuration changes at M1 require step-up; the sensitive-action list is enforced for actions that exist.

**Later behavior:** None beyond M1 for this clause. | Refunds, voids and high discounts exist only at M4 and must be proven to demand step-up there.

**Prerequisites:** FR-AUTH-001, FR-SEC-014, FR-AUTH-006  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M1-FR-AUTH-005A, TST-M1-FR-AUTH-005B, TST-M4-FR-AUTH-005B

### FR-AUTH-006 - Step-up authentication

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4, M6  
**Required behavior:** Require recent stronger authentication for refunds, reversals, payout, role changes, exports and other configured sensitive actions.

**Gate-local behavior:** Step-up challenge with recency window enforced for role changes and configuration at M1.

**Later behavior:** Refunds, reversals and payout exist at M4; export actions at M6.

**Prerequisites:** FR-AUTH-001  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M1-FR-AUTH-006, TST-M4-FR-AUTH-006, TST-M6-FR-AUTH-006

### FR-AUTH-007 - Password/OTP security

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M6  
**Required behavior:** Apply rate limits, lockout and secure credential/OTP handling for the identity methods active in Phase 1. CI and simulators do not count as distributed production rate limiting.

**Gate-local behavior:** Authentication and OTP endpoints enforce rate limits and lockout with secure credential handling.

**Later behavior:** Distributed production enforcement is only demonstrable on the deployed artifact.

**Prerequisites:** FR-AUTH-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-AUTH-007, TST-M6-FR-AUTH-007

### FR-AUTH-008 - Memberships

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M4, M5a  
**Required behavior:** Staff access is derived from explicit tenant/outlet memberships and role assignments; missing tenant or outlet context fails closed.

**Gate-local behavior:** Access resolves only through membership records; absent tenant/outlet context returns no data and permits no write.

**Later behavior:** New authorized surfaces must continue to fail closed.

**Prerequisites:** FR-TEN-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-AUTH-008, TST-M3-FR-AUTH-008, TST-M4-FR-AUTH-008, TST-M5a-FR-AUTH-008

### FR-AUTH-009 - Service accounts

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M5a  
**Required behavior:** Use scoped service principals for workers, edge nodes, print agents and integrations with rotation and revocation.

**Gate-local behavior:** Cloud workers and integrations authenticate as scoped service principals with rotation and revocation.

**Later behavior:** Edge node and print agent principals exist only at M5a.

**Prerequisites:** FR-AUTH-004  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M1-FR-AUTH-009, TST-M5a-FR-AUTH-009

### FR-AUTH-010 - Recovery

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** None  
**Required behavior:** Provide a documented administrator-controlled recovery process for lost credentials or factors, with identity verification, revocation and audit. Self-service advanced recovery may follow later.

**Gate-local behavior:** Administrator-controlled recovery executes with identity verification, revocation of old factors and an audit record.

**Later behavior:** None beyond M1 for this clause.

**Prerequisites:** FR-AUTH-001, FR-SEC-009  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-AUTH-010

## Integration Runtime

### FR-INT-010 - Credential isolation

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4, M5a  
**Required behavior:** Store cloud, outlet-node, printer and payment-adapter credentials separately by tenant/outlet/environment; never include real secrets in source, images or fixtures.

**Gate-local behavior:** Cloud credentials are stored per tenant/outlet/environment and no real secret appears in source, images or fixtures.

**Later behavior:** Payment-adapter credentials exist at M4; outlet-node and printer credentials at M5a.

**Prerequisites:** FR-SEC-007  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M1-FR-INT-010, TST-M4-FR-INT-010, TST-M5a-FR-INT-010

## Internationalization and Localization

### FR-I18N-007 - Staff and back-office language

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M4  
**Required behavior:** Waiter, POS, KDS and administration launch in English. Their architecture remains translation-ready, but no non-English staff UI is acceptance-critical in Phase 1.

**Gate-local behavior:** The administration surface launches in English on a translation-ready framework.

**Later behavior:** Waiter and KDS surfaces exist at M3; POS at M4. Each must launch in English on the same framework.

**Prerequisites:** FR-CFG-006  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-I18N-007, TST-M3-FR-I18N-007, TST-M4-FR-I18N-007

## Security and Data Protection

### FR-SEC-001 - Deny by default

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M2, M3, M4, M5a  
**Required behavior:** Every API, database policy, job, cache, file and local/cloud synchronization path is deny-by-default. Missing tenant, outlet, session or actor context returns no data and permits no write.

**Gate-local behavior:** All M1 API routes, policies, jobs, cache and file paths deny without full context.

**Later behavior:** Each later gate adds new paths; the synchronization path clause is only executable when sync exists.

**Prerequisites:** FR-TEN-001, FR-AUTH-008  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-SEC-001, TST-M2-FR-SEC-001, TST-M3-FR-SEC-001, TST-M4-FR-SEC-001, TST-M5a-FR-SEC-001

### FR-SEC-002A - Cloud IDOR defense

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-SEC-002`  
**Introduced:** M1  
**Revalidated:** M3, M4, M6  
**Required behavior:** Populated foreign-tenant and sibling-outlet fixtures fail closed for all four verbs on cloud routes.

**Gate-local behavior:** Populated foreign-tenant and sibling-outlet fixtures fail closed for all four verbs on cloud routes.

**Later behavior:** New cloud resources at later gates must be covered; the complete production surface is revalidated at M6.

**Prerequisites:** FR-TEN-001, FR-SEC-001  
**Journeys:** GJ-13  
**Acceptance tests:** TST-M1-FR-SEC-002A, TST-M3-FR-SEC-002A, TST-M4-FR-SEC-002A, TST-M6-FR-SEC-002A

### FR-SEC-003 - Input validation

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M4, M6  
**Required behavior:** Validate request schemas, lengths, enumerations, money, quantity, dates, files and URLs before domain execution.

**Gate-local behavior:** Enforced across every route, template and data access path existing at M1.

**Later behavior:** Later gates add routes and rendering surfaces subject to the same rule.

**Prerequisites:** FR-DAT-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-SEC-003, TST-M3-FR-SEC-003, TST-M4-FR-SEC-003, TST-M6-FR-SEC-003

### FR-SEC-004 - Injection defense

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M4, M6  
**Required behavior:** Use parameterized data access, output escaping, CSP and safe template/file handling.

**Gate-local behavior:** Enforced across every route, template and data access path existing at M1.

**Later behavior:** Later gates add routes and rendering surfaces subject to the same rule.

**Prerequisites:** FR-DAT-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-SEC-004, TST-M3-FR-SEC-004, TST-M4-FR-SEC-004, TST-M6-FR-SEC-004

### FR-SEC-005 - CSRF/session

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M4, M6  
**Required behavior:** Protect cookie-based actions against CSRF and use secure, httpOnly, same-site cookies where applicable.

**Gate-local behavior:** Enforced across every route, template and data access path existing at M1.

**Later behavior:** Later gates add routes and rendering surfaces subject to the same rule.

**Prerequisites:** FR-DAT-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-SEC-005, TST-M3-FR-SEC-005, TST-M4-FR-SEC-005, TST-M6-FR-SEC-005

### FR-SEC-006 - Rate limiting

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M2, M3, M4, M6  
**Required behavior:** Apply contextual rate limits to auth, QR resolution, ordering, payment, search, exports and webhooks.

**Gate-local behavior:** Contextual limits enforced on the authentication and search surfaces existing at M1.

**Later behavior:** QR resolution at M2, ordering at M3, payment and webhooks at M4, exports at M6.

**Prerequisites:** FR-AUTH-007  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-SEC-006, TST-M2-FR-SEC-006, TST-M3-FR-SEC-006, TST-M4-FR-SEC-006, TST-M6-FR-SEC-006

### FR-SEC-007 - Secret management

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M4, M6  
**Required behavior:** Keep keys, passwords and tokens out of source, database plaintext, logs, screenshots and reports.

**Gate-local behavior:** Enforced across every route, template and data access path existing at M1.

**Later behavior:** Later gates add routes and rendering surfaces subject to the same rule.

**Prerequisites:** FR-DAT-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-SEC-007, TST-M3-FR-SEC-007, TST-M4-FR-SEC-007, TST-M6-FR-SEC-007

### FR-SEC-008 - Encryption

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M5b, M6  
**Required behavior:** Use TLS in transit and provider/platform encryption at rest; encrypt selected high-risk fields or backups.

**Gate-local behavior:** Cloud transport uses TLS and data at rest is encrypted; selected high-risk fields are encrypted.

**Later behavior:** Per-outlet public-trust TLS on the local node is an M5b concern; backup encryption is proven with backup/restore.

**Prerequisites:** FR-DAT-001  
**Journeys:** GJ-11  
**Acceptance tests:** TST-M1-FR-SEC-008, TST-M5b-FR-SEC-008, TST-M6-FR-SEC-008

### FR-SEC-009 - Audit separation

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4, M5a  
**Required behavior:** Security audit storage and operational audit storage are append-only and cannot be changed by ordinary application roles.

**Gate-local behavior:** Application roles cannot UPDATE or DELETE audit rows; append-only enforced at database level.

**Later behavior:** Later gates write new audit categories under the same constraint.

**Prerequisites:** FR-DAT-002, FR-DAT-017  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-SEC-009, TST-M4-FR-SEC-009, TST-M5a-FR-SEC-009

### FR-SEC-010A - Customer PII classification

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-SEC-010`  
**Introduced:** M1  
**Revalidated:** M3  
**Required behavior:** Data classification exists and customer contact/complaint fields are restricted by role.

**Gate-local behavior:** Data classification exists and customer contact/complaint fields are restricted by role.

**Later behavior:** Complaint and service-failure data is generated at M3; restriction is revalidated once real records exist.

**Prerequisites:** FR-AUTH-008  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-SEC-010A, TST-M3-FR-SEC-010A

### FR-SEC-011 - Payment boundary

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4  
**Required behavior:** Prohibit storage/logging of raw PAN, CVV and sensitive authentication data.

**Gate-local behavior:** No schema field or log sink accepts PAN/CVV; scanner and log assertions prove absence.

**Later behavior:** The payment surface where such data could appear exists at M4; external terminal recording at M4 and proof images must be re-proven.

**Prerequisites:** FR-SEC-007  
**Journeys:** GJ-01B  
**Acceptance tests:** TST-M1-FR-SEC-011, TST-M4-FR-SEC-011

### FR-SEC-012 - File security

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4  
**Required behavior:** Validate, scan, hash, authorize, sign and expire access to private files.

**Gate-local behavior:** Uploads are validated, scanned, hashed and served through signed expiring authorized URLs.

**Later behavior:** The first real private-file class is the Telebirr/CBE payment proof at M4.

**Prerequisites:** FR-SEC-003  
**Journeys:** GJ-02B  
**Acceptance tests:** TST-M1-FR-SEC-012, TST-M4-FR-SEC-012

### FR-SEC-013 - MFA

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4  
**Required behavior:** Support step-up MFA for high-risk staff actions. Phase 1 may use an administrator-controlled enrolment/recovery process, but cannot falsely claim every role is forced to enrol.

**Gate-local behavior:** Step-up MFA is available for high-risk actions with administrator-controlled enrolment; documentation states the true enrolment posture.

**Later behavior:** High-risk financial actions appear at M4.

**Prerequisites:** FR-AUTH-006, FR-AUTH-010  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-SEC-013, TST-M4-FR-SEC-013

### FR-SEC-014 - Device security

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M5a  
**Required behavior:** Register, name, revoke and monitor staff devices/terminals/edge nodes.

**Gate-local behavior:** Staff devices and terminals are registered, named, revocable and monitored.

**Later behavior:** Edge nodes are registrable subjects only once they exist.

**Prerequisites:** FR-AUTH-004  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M1-FR-SEC-014, TST-M5a-FR-SEC-014

### FR-SEC-016 - Security headers

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M2, M5b  
**Required behavior:** Set CSP, HSTS, frame, referrer, permissions and content-type protections appropriate to each app.

**Gate-local behavior:** Security headers are set correctly for each application surface existing at M1.

**Later behavior:** Customer PWA at M2 and the locally served same-QR surface at M5b are additional apps with their own header posture.

**Prerequisites:** FR-SEC-004  
**Journeys:** GJ-08  
**Acceptance tests:** TST-M1-FR-SEC-016, TST-M2-FR-SEC-016, TST-M5b-FR-SEC-016

### FR-SEC-018 - Data deletion

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4, M6  
**Required behavior:** Use retention-aware anonymization/erasure workflows and legal holds.

**Gate-local behavior:** Anonymization/erasure workflow and legal hold flags exist and respect ledger integrity for M1 data.

**Later behavior:** Customer session and order data subject to erasure exist from M2 and M3; ledger-protected financial records at M4.

**Prerequisites:** FR-DAT-018  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-SEC-018, TST-M4-FR-SEC-018, TST-M6-FR-SEC-018

### FR-SEC-020 - Incident response

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M6  
**Required behavior:** Provide detection, containment, credential rotation, tenant notification and evidence-preservation runbook.

**Gate-local behavior:** Runbook exists and credential rotation, containment and evidence preservation are executable against M1 capability.

**Later behavior:** Detection depends on production monitoring; tenant notification on the deployed multi-tenant artifact.

**Prerequisites:** FR-AUTH-004, FR-SEC-009  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-SEC-020, TST-M6-FR-SEC-020

## Tenant and Commercial Control

### FR-TEN-001 - Tenant isolation

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M2, M3, M4, M5a, M6  
**Required behavior:** Every tenant-owned record and operation is scoped to a tenant; cross-tenant reads/writes are denied in API, database policy, jobs, cache, files and exports.

**Gate-local behavior:** Deny cross-tenant SELECT/INSERT/UPDATE/DELETE on the tables existing at M1 through production roles, with populated foreign-tenant fixtures.

**Later behavior:** Each later gate adds new tenant-owned records and new access paths that the same rule must cover.

**Prerequisites:** FR-DAT-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-TEN-001, TST-M2-FR-TEN-001, TST-M3-FR-TEN-001, TST-M4-FR-TEN-001, TST-M5a-FR-TEN-001, TST-M6-FR-TEN-001

### FR-TEN-002A - Phase 1 organizational hierarchy

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-TEN-002`  
**Introduced:** M1  
**Revalidated:** M2, M5a  
**Required behavior:** Brand, legal entity, outlet, service area, preparation station and device entities exist with configurable depth; no fixed-level assumption in schema or queries.

**Gate-local behavior:** Brand, legal entity, outlet, service area, preparation station and device entities exist with configurable depth; no fixed-level assumption in schema or queries.

**Later behavior:** Table entity becomes operationally exercised when QR/table sessions exist; device registration extends to outlet nodes and print agents.

**Prerequisites:** FR-DAT-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-TEN-002A, TST-M2-FR-TEN-002A, TST-M5a-FR-TEN-002A

### FR-TEN-003 - Tenant configuration

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4, M5a  
**Required behavior:** Store versioned branding, locale, currency, timezone, tax, calendar, numbering, payment, service, feature and connector configuration.

**Gate-local behavior:** Versioned configuration records exist and are readable/writable per tenant with effective dating for the categories above.

**Later behavior:** Payment and connector configuration values are only exercised once payment execution (M4) and outlet connectors (M5a) exist.

**Prerequisites:** FR-DAT-001, FR-TEN-010  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-TEN-003, TST-M4-FR-TEN-003, TST-M5a-FR-TEN-003

### FR-TEN-004 - Module entitlements

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M6  
**Required behavior:** Enable or disable modules and features by tenant and optionally legal entity/outlet without code forks.

**Gate-local behavior:** Entitlement records resolve per tenant/entity/outlet and gate feature availability at runtime with no forked build.

**Later behavior:** Entitlement effect on later feature surfaces is confirmed as those surfaces appear.

**Prerequisites:** FR-TEN-003  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-TEN-004, TST-M6-FR-TEN-004

### FR-TEN-005 - Second tenant

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M2, M4, M6  
**Required behavior:** Seed and test a second tenant with different branding, language defaults, tax settings and module entitlements.

**Gate-local behavior:** A second tenant is seeded with distinct branding and entitlements and proven isolated at the M1 surface.

**Later behavior:** Different language defaults require the localization surface; tax settings require billing; full commercial isolation is proven by the M6 second-tenant journey.

**Prerequisites:** FR-TEN-001, FR-DAT-013  
**Journeys:** GJ-13  
**Acceptance tests:** TST-M1-FR-TEN-005, TST-M2-FR-TEN-005, TST-M4-FR-TEN-005, TST-M6-FR-TEN-005

### FR-TEN-009A - Phase 1 system-of-record registry

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-TEN-009`  
**Introduced:** M1  
**Revalidated:** M4  
**Required behavior:** A system-of-record registry entry exists per tenant/legal entity with the Phase 1 enumeration only.

**Gate-local behavior:** A system-of-record registry entry exists per tenant/legal entity with the Phase 1 enumeration only.

**Later behavior:** The registry governs actual fiscal document and payment behavior once those exist.

**Prerequisites:** FR-TEN-003  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-TEN-009A, TST-M4-FR-TEN-009A

### FR-TEN-010 - Configuration history

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M4  
**Required behavior:** Version and audit policy changes, including effective dates and the actor who approved them.

**Gate-local behavior:** Each configuration change writes an append-only audit record with actor, approval and effective date.

**Later behavior:** Policy categories introduced later produce the same audit evidence.

**Prerequisites:** FR-AUTH-008, FR-SEC-009  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-TEN-010, TST-M4-FR-TEN-010

## Testing and Evidence

### FR-TST-001 - Unit tests

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M2, M3, M4  
**Required behavior:** Test pure domain policies, calculations, state machines, money, sellable-item quantity units (portion, each and sold-by-weight presentation), translations and permissions. Operational inventory or recipe units of measure are outside Phase 1 and have no test obligation.

**Gate-local behavior:** Unit tests cover M1 domain policies, money types and permissions with meaningful assertions.

**Later behavior:** State machines and translations mature at M2 and M3; money calculations become substantive at M4.

**Prerequisites:** FR-DAT-005, FR-AUTH-008  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-TST-001, TST-M2-FR-TST-001, TST-M3-FR-TST-001, TST-M4-FR-TST-001

### FR-TST-002 - Database integration

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M4, M5a  
**Required behavior:** Test constraints, transactions, locks, tenant/outlet RLS, later-added outlet columns, append-only rules and migrations on real PostgreSQL using raw production-role pools.

**Gate-local behavior:** Constraints, transactions, locks, RLS and migrations are tested on real PostgreSQL through raw production-role pools.

**Later behavior:** Order and financial state relationships at M3 and M4; the local database at M5a.

**Prerequisites:** FR-DAT-017, FR-SEC-002A  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M1-FR-TST-002, TST-M3-FR-TST-002, TST-M4-FR-TST-002, TST-M5a-FR-TST-002

### FR-TST-003 - API tests

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M4  
**Required behavior:** Test validation, auth, idempotency, concurrency, error contracts and pagination.

**Gate-local behavior:** API tests cover validation, auth, idempotency, concurrency, error contracts and pagination for M1 routes.

**Later behavior:** Each later gate adds substantial route surface subject to the same suite.

**Prerequisites:** FR-DAT-001, FR-AUTH-001  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-TST-003, TST-M3-FR-TST-003, TST-M4-FR-TST-003

### FR-TST-004A - Phase 1 adapter contract tests

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** split_successor from `FR-TST-004`  
**Introduced:** M1  
**Revalidated:** M4, M5a  
**Required behavior:** Messaging and storage ports are tested against production-equivalent simulators.

**Gate-local behavior:** Messaging and storage ports are tested against production-equivalent simulators.

**Later behavior:** Payment and fiscal ports exist at M4; outlet-node, synchronization and print ports at M5a.

**Prerequisites:** FR-AUTH-001, FR-SEC-012  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M1-FR-TST-004A, TST-M4-FR-TST-004A, TST-M5a-FR-TST-004A

### FR-TST-006 - Security tests

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M3, M4, M5a, M6  
**Required behavior:** Include non-vacuous security tests with owner-confirmed populated fixtures, absent/malformed context, sibling-outlet attempts and deliberately weakened policies.

**Gate-local behavior:** Security tests run against owner-confirmed populated fixtures and fail when a policy is deliberately weakened.

**Later behavior:** Each gate adds new policy surface that must be tested the same way; the complete production surface is revalidated at M6.

**Prerequisites:** FR-SEC-002A, FR-TST-017  
**Journeys:** GJ-13  
**Acceptance tests:** TST-M1-FR-TST-006, TST-M3-FR-TST-006, TST-M4-FR-TST-006, TST-M5a-FR-TST-006, TST-M6-FR-TST-006

### FR-TST-012 - Migration and cross-platform upgrade

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M6  
**Required behavior:** Test a fresh migration from this package baseline and a supported upgrade from a prior approved baseline of this package, checksum lock, line endings and ordinary Windows/Linux tool invocation.

**Gate-local behavior:** A fresh migration applies cleanly with checksum lock and correct line endings under ordinary Windows and Linux invocation.

**Later behavior:** The supported upgrade path from a prior baseline is exercised against the production schema.

**Prerequisites:** FR-DAT-001, FR-DAT-016  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M1-FR-TST-012, TST-M6-FR-TST-012

### FR-TST-015 - Defect gates

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M6  
**Required behavior:** Every confirmed defect receives an unchanged regression gate plus an independent stronger negative control when the original assertion could be vacuous or self-invalidating.

**Gate-local behavior:** Each confirmed defect produces an unchanged regression gate and, where the assertion could be vacuous, an independent stronger negative control.

**Later behavior:** The complete defect and control set is audited against the final artifact.

**Prerequisites:** FR-TST-017  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-TST-015, TST-M6-FR-TST-015

### FR-TST-016 - Evidence report

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M6  
**Required behavior:** Produce commit, versions, migration list, test results, screenshots/artifacts, known nonblocking limitations and deployment commands.

**Gate-local behavior:** Each gate produces an evidence report containing all seven named elements.

**Later behavior:** The consolidated pilot evidence report is produced at handover.

**Prerequisites:** FR-GOV-004  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M1-FR-TST-016, TST-M6-FR-TST-016

### FR-TST-020 - Order-independent validation

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M6  
**Required behavior:** Clean build and test results are identical regardless of prior command order; stale dist, .next, test databases and generated artifacts cannot influence a pass.

**Gate-local behavior:** Results are identical from a clean checkout regardless of command order and stale artifacts cannot influence a pass.

**Later behavior:** Order independence is re-proven across the full production build including the node artifact.

**Prerequisites:** FR-OPS-008  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M1-FR-TST-020, TST-M6-FR-TST-020

## UX and Accessibility

### FR-UX-003 - Back office desktop first

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M1  
**Revalidated:** M6  
**Required behavior:** Use dense but responsive information architecture, filters, saved views and keyboard support.

**Gate-local behavior:** The administration surface supports dense responsive layout, filters, saved views and keyboard navigation.

**Later behavior:** The reporting and back-office surfaces extend this at M6.

**Prerequisites:** FR-I18N-007  
**Journeys:** None  
**Acceptance tests:** TST-M1-FR-UX-003, TST-M6-FR-UX-003

# Gate M2

## Allergens and Dietary Safety

### FR-SAF-001 - Allergen catalog

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Provide a tenant/jurisdiction-configurable allergen catalog with translated customer text, approved universal supporting icons and English kitchen codes. Icons supplement but never replace written warnings.

**Gate-local behavior:** The catalog is configurable per tenant/jurisdiction with translated text, icons and English kitchen codes, and no icon-only warning path exists.

**Later behavior:** English kitchen codes are consumed by kitchen tickets at M3.

**Prerequisites:** FR-I18N-003  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M2-FR-SAF-001, TST-M3-FR-SAF-001

### FR-SAF-002 - Item allergen declaration

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Record contains, may-contain and cross-contact warnings by item/variant/modifier and effective version.

**Gate-local behavior:** All three warning classes record per item/variant/modifier with effective versioning.

**Later behavior:** Declarations are propagated to order and kitchen surfaces at M3.

**Prerequisites:** FR-SAF-001, FR-MNU-005  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-SAF-002, TST-M3-FR-SAF-002

### FR-SAF-003 - Allergy customer input

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Allow a customer or waiter to flag an allergy concern for an order/table with explicit acknowledgement text.

**Gate-local behavior:** A table-level allergy flag is recorded with explicit acknowledgement text on the session.

**Later behavior:** The order-level flag and waiter-initiated flagging require the M3 order and waiter surfaces.

**Prerequisites:** FR-TAB-003, FR-SAF-001  
**Journeys:** GJ-01A, GJ-05  
**Acceptance tests:** TST-M2-FR-SAF-003, TST-M3-FR-SAF-003

### FR-SAF-005 - Change detection

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Re-evaluate allergen/dietary declarations when modifiers or substitutions alter ingredients.

**Gate-local behavior:** Selecting a modifier that alters ingredients re-evaluates the declaration in the menu/cart surface.

**Later behavior:** Substitutions during an accepted order are an M3 behavior.

**Prerequisites:** FR-SAF-002, FR-MNU-006  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M2-FR-SAF-005, TST-M3-FR-SAF-005

### FR-SAF-006 - Dietary claims

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Manage vegetarian, vegan, fasting, halal and other claims with definitions, evidence owner, review date and outlet applicability.

**Gate-local behavior:** Dietary claims carry definitions, evidence owner, review date and outlet applicability.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-SAF-001, FR-TEN-002A  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-SAF-006

### FR-SAF-007 - Publication block

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Block publication when required safety translation or allergen review is incomplete.

**Gate-local behavior:** Publication is blocked when safety translation or allergen review is incomplete, in all three locales.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-MNU-003, FR-SAF-002  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-SAF-007

### FR-SAF-008 - Audit

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Record who created, reviewed, approved and published safety-critical content.

**Gate-local behavior:** Every safety-content state transition records actor and timestamp in append-only audit.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-SEC-009, FR-MNU-003  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-SAF-008

### FR-SAF-009 - Disclaimer

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M4  
**Required behavior:** Display tenant-approved wording that information supports informed choice but cannot eliminate all cross-contact risk.

**Gate-local behavior:** The tenant-approved disclaimer renders on the customer menu surface in all three locales.

**Later behavior:** The disclaimer must also appear on the printed and digital receipt where the tenant requires it.

**Prerequisites:** FR-SAF-001, FR-CFG-006  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-SAF-009, TST-M4-FR-SAF-009

## Configuration and Setup

### FR-CFG-001B - Locale, table and QR setup

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-CFG-001`  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** The guided setup configures the three customer locales, currency, timezone, preparation stations, tables and opaque QR codes.

**Gate-local behavior:** Complete locale, currency, timezone, station, table and QR setup and prove that the generated QR resolves to the configured outlet and table.

**Later behavior:** 

**Prerequisites:** FR-I18N-001A, FR-TAB-001  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-CFG-001B

## Customer, Privacy and Consent

### FR-CST-002 - Guest privacy

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M6  
**Required behavior:** Create guest profiles only when operationally necessary and expire/anonymize optional data according to policy.

**Gate-local behavior:** A guest profile is created only where operationally required by the session, and optional data carries an expiry/anonymization policy.

**Later behavior:** Retention execution over accumulated customer data is proven with the retention workflow.

**Prerequisites:** FR-AUTH-003  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-CST-002, TST-M6-FR-CST-002

## Identity and Authentication

### FR-AUTH-003 - Guest session

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Allow a customer to create a privacy-minimized guest session for QR ordering without phone, email or loyalty registration.

**Gate-local behavior:** Scanning a table QR creates a guest session holding no phone, email or account identifier.

**Later behavior:** The M3 dine-in ordering journey revalidates that the privacy-minimized session remains anonymous when it submits an order.

**Prerequisites:** FR-TAB-001, FR-TAB-003  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M2-FR-AUTH-003, TST-M3-FR-AUTH-003

## Internationalization and Localization

### FR-I18N-001A - Customer menu and QR languages

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-I18N-001`  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Exactly three customer locales are offered and menu content plus the QR/session surface renders completely in the selected language.

**Gate-local behavior:** Exactly three customer locales are offered and menu content plus the QR/session surface renders completely in the selected language.

**Later behavior:** Service text, bills and receipts do not exist at M2.

**Prerequisites:** FR-I18N-011, FR-MNU-004  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-I18N-001A

### FR-I18N-002 - Arabic RTL

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3, M4  
**Required behavior:** Arabic uses true right-to-left layout, mirrored navigation where appropriate, correct number/currency rendering and mixed-script handling without breaking prices, modifiers or status timelines.

**Gate-local behavior:** Menu, modifier and price surfaces render true RTL with correct ETB and numeral formatting and mixed Arabic/Latin strings.

**Later behavior:** Status timelines exist at M3; bill and receipt layouts at M4.

**Prerequisites:** FR-I18N-001A, FR-MNU-006  
**Journeys:** GJ-03A, GJ-03B  
**Acceptance tests:** TST-M2-FR-I18N-002, TST-M3-FR-I18N-002, TST-M4-FR-I18N-002

### FR-I18N-003 - Customer translation records

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3, M4  
**Required behavior:** Store human-approved customer translations separately from canonical records for menu, modifier, allergen, dietary, service, order-status, bill, tip and receipt content.

**Gate-local behavior:** Translation records exist separately from canonical records and are populated and approved for menu, modifier, allergen and dietary content.

**Later behavior:** Service and order-status content types exist at M3; bill, tip and receipt content types at M4.

**Prerequisites:** FR-DAT-009  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-I18N-003, TST-M3-FR-I18N-003, TST-M4-FR-I18N-003

### FR-I18N-004 - Language selection and fallback

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Offer English, Amharic and Arabic explicitly. Browser language is a suggestion only; remember the customer's choice for the table session and permit switching without losing the cart.

**Gate-local behavior:** Explicit three-language selection persists on the table session and switching preserves cart contents.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-TAB-003, FR-TAB-005  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-I18N-004

### FR-I18N-005 - Locale formatting and order snapshot

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3, M4  
**Required behavior:** Localize dates, times, numbers, currencies and plural forms while storing canonical values, and snapshot the customer-selected locale on the table session/order for communications, receipts, analytics and support evidence.

**Gate-local behavior:** Formatting is locale-correct with canonical storage, and the selected locale is snapshotted on the table session.

**Later behavior:** The order-level snapshot exists at M3; receipt consumption of the snapshot at M4.

**Prerequisites:** FR-DAT-004, FR-TAB-003  
**Journeys:** GJ-02B  
**Acceptance tests:** TST-M2-FR-I18N-005, TST-M3-FR-I18N-005, TST-M4-FR-I18N-005

### FR-I18N-006 - Completeness and safety approval

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Block publication when required English/Amharic/Arabic customer or safety translations are incomplete. No live runtime machine translation may fill missing safety content.

**Gate-local behavior:** Publication is blocked when any of the three locales lacks required customer or safety text, and no runtime translation path exists.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-MNU-003, FR-SAF-007  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-I18N-006

### FR-I18N-010 - Machine assistance boundary

**Priority:** P1  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Permit AI/machine-assisted draft translation with provenance and human review, but prohibit live runtime customer translation and automatic publication of safety-critical text.

**Gate-local behavior:** Draft translations carry provenance and require human approval; no runtime translation path and no automatic safety publication exists.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-I18N-003, FR-I18N-006  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-I18N-010

### FR-I18N-011 - Exact launch locale set

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3, M4  
**Required behavior:** The customer launch locale set is exactly English (en), Amharic (am) and Arabic (ar); staff and administration launch in English; Arabic renders true RTL.

**Gate-local behavior:** The locale registry contains exactly en, am and ar for customers, and Arabic renders true RTL on the customer surface.

**Later behavior:** The staff-English clause is revalidated wherever a staff surface is introduced.

**Prerequisites:** None  
**Journeys:** GJ-03A  
**Acceptance tests:** TST-M2-FR-I18N-011, TST-M3-FR-I18N-011, TST-M4-FR-I18N-011

## Menu and Pricing

### FR-MNU-001 - Menu hierarchy

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Manage menus, categories, groups, sellable items and variants independently of recipe and inventory identities.

**Gate-local behavior:** The menu hierarchy exists and carries no recipe or inventory identity reference.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-DAT-009  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-MNU-001

### FR-MNU-002A - Menu assignment

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-MNU-002`  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Menu assignment resolves correctly by outlet, service area, channel, daypart and date range.

**Gate-local behavior:** Menu assignment resolves correctly by outlet, service area, channel, daypart and date range.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-MNU-001, FR-TEN-002A  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-MNU-002A

### FR-MNU-003 - Menu publishing

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Use draft, review, scheduled, published, paused and archived states with immutable publication snapshots.

**Gate-local behavior:** All six publication states and transitions work, and published snapshots are immutable.

**Later behavior:** Order-time price/content snapshots reference these publication snapshots.

**Prerequisites:** FR-MNU-001, FR-DAT-009  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-MNU-003, TST-M3-FR-MNU-003

### FR-MNU-004 - Item content

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Store translated name, short/long description, customer-visible ingredients, images, preparation time and display order.

**Gate-local behavior:** All named content fields store and render per locale.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-MNU-001, FR-I18N-003  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-MNU-004

### FR-MNU-005 - Variants

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Support size, portion, temperature, preparation style and other sellable variants with independent prices and availability.

**Gate-local behavior:** Variants carry independent prices and availability states.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-MNU-001  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-MNU-005

### FR-MNU-006 - Modifier sets

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Support required/optional groups, min/max selection, defaults, included quantity, price deltas and incompatibilities.

**Gate-local behavior:** Modifier group rules, price deltas and incompatibility constraints validate correctly.

**Later behavior:** Modifier selection is exercised against real submitted orders at M3.

**Prerequisites:** FR-MNU-005  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M2-FR-MNU-006, TST-M3-FR-MNU-006

### FR-MNU-007 - Availability

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Publish available, limited, temporarily unavailable, scheduled later and hidden states without exposing exact stock.

**Gate-local behavior:** All five availability states publish correctly and no exact stock quantity is exposed anywhere.

**Later behavior:** Availability revalidation at order submission occurs at M3.

**Prerequisites:** FR-MNU-001  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M2-FR-MNU-007, TST-M3-FR-MNU-007

### FR-MNU-008 - Sold-out action

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Allow authorized station/outlet staff to pause an item/variant/modifier with reason and optional expected return.

**Gate-local behavior:** Authorized staff pause an item/variant/modifier with a reason code and optional expected return time.

**Later behavior:** Station-initiated sold-out during service is exercised with the kitchen surface.

**Prerequisites:** FR-MNU-007, FR-CFG-003  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M2-FR-MNU-008, TST-M3-FR-MNU-008

### FR-MNU-009 - Price versions

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Store effective-dated prices by outlet/channel/variant/currency/tax context and preserve price snapshots on orders.

**Gate-local behavior:** Effective-dated prices resolve correctly across outlet, channel, variant, currency and tax context.

**Later behavior:** Price snapshots on orders require orders to exist.

**Prerequisites:** FR-MNU-005, FR-DAT-005  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M2-FR-MNU-009, TST-M3-FR-MNU-009

### FR-MNU-010 - Daypart scheduling

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Activate breakfast, lunch, dinner, late-night and tenant-defined windows using outlet-local time.

**Gate-local behavior:** Daypart windows activate and deactivate menus using outlet-local time including boundary cases.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-MNU-002A, FR-DAT-004  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-MNU-010

### FR-MNU-011 - Images

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Support optimized responsive images, alt text, focal crop and private source asset management.

**Gate-local behavior:** Responsive derivatives, alt text and focal crop work; source assets remain private and authorized.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-MNU-004, FR-SEC-012  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-MNU-011

### FR-MNU-012 - Search and filtering

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Search translated names/descriptions and filter by category, dietary tags, allergens, availability, price and preparation time.

**Gate-local behavior:** Search returns correct results across all three locales including mixed-script queries, and every named filter works.

**Later behavior:** The M3 Arabic ordering journey revalidates mixed-script search against the live order-entry surface.

**Prerequisites:** FR-MNU-004, FR-SAF-002  
**Journeys:** GJ-03A  
**Acceptance tests:** TST-M2-FR-MNU-012, TST-M3-FR-MNU-012

## Recipes and Costing

### FR-RCP-008A - Customer ingredient and allergen content

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** split_successor from `FR-RCP-008`  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Customer-visible ingredient text and allergen declarations are stored as customer content with no operational recipe linkage.

**Gate-local behavior:** Customer-visible ingredient text and allergen declarations are stored as customer content with no operational recipe linkage.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-MNU-004, FR-SAF-002  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-RCP-008A

## Tables and Sessions

### FR-TAB-001 - QR resolution

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M5b  
**Required behavior:** Resolve a signed QR into tenant, outlet, service area and table without exposing internal IDs.

**Gate-local behavior:** A signed opaque QR resolves to the correct tenant/outlet/service area/table with no internal identifier in the URL or payload.

**Later behavior:** The same QR must also resolve locally during outage under split-horizon DNS.

**Prerequisites:** FR-TEN-002A, FR-DAT-003  
**Journeys:** GJ-08  
**Acceptance tests:** TST-M2-FR-TAB-001, TST-M5b-FR-TAB-001

### FR-TAB-002 - QR rotation

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Rotate/revoke table QR tokens and keep printable version history.

**Gate-local behavior:** Tokens rotate and revoke; revoked tokens fail resolution; printable version history is retained.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-TAB-001  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-TAB-002

### FR-TAB-003 - Table session creation

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Create a table session with occupancy state, opening source, host staff, participants and timestamps.

**Gate-local behavior:** A table session is created with all named attributes and correct UTC/outlet-time handling.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-TAB-001, FR-DAT-004  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-TAB-003

### FR-TAB-004 - Participant joining

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Allow multiple devices/guests to join a session using the same active QR under configured visibility rules.

**Gate-local behavior:** Multiple devices join one session under the configured visibility rule and see only permitted content.

**Later behavior:** Multi-participant behavior under real ordering and service requests is proven operationally at M3.

**Prerequisites:** FR-TAB-003  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M2-FR-TAB-004, TST-M3-FR-TAB-004

### FR-TAB-005 - Personal and shared carts

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Support personal baskets, shared baskets and transfer of items before submission.

**Gate-local behavior:** Personal and shared baskets exist and items transfer between them prior to submission.

**Later behavior:** Submission boundary behavior is exercised when orders exist.

**Prerequisites:** FR-TAB-004, FR-MNU-005  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M2-FR-TAB-005, TST-M3-FR-TAB-005

### FR-TAB-006 - Table ownership

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3  
**Required behavior:** Assign primary waiter/section and allow acknowledged transfer or supervisor reassignment.

**Gate-local behavior:** A primary waiter/section is assignable to a table session with the ownership record stored.

**Later behavior:** Acknowledged transfer and supervisor reassignment are service operations exercised with real waiter workflow.

**Prerequisites:** FR-AUTH-008, FR-TAB-003  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M2-FR-TAB-006, TST-M3-FR-TAB-006

### FR-TAB-010 - Stale QR protection

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** None  
**Required behavior:** Prevent a historic or photographed QR session from silently joining a later occupied table without configured verification.

**Gate-local behavior:** A QR captured from an earlier occupancy cannot silently join a new session; configured verification is required.

**Later behavior:** None beyond M2 for this clause.

**Prerequisites:** FR-TAB-001, FR-TAB-004  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-TAB-010

## Testing and Evidence

### FR-TST-011 - Accessibility

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3, M6  
**Required behavior:** Automate common checks and perform manual keyboard/screen-reader/RTL reviews.

**Gate-local behavior:** Automated accessibility checks and manual keyboard, screen-reader and RTL reviews run on the customer surface.

**Later behavior:** Staff surfaces and the final production artifact are reviewed the same way.

**Prerequisites:** FR-UX-011, FR-I18N-002  
**Journeys:** GJ-03A  
**Acceptance tests:** TST-M2-FR-TST-011, TST-M3-FR-TST-011, TST-M6-FR-TST-011

## UX and Accessibility

### FR-UX-001A - Customer dine-in mobile experience

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-UX-001`  
**Introduced:** M2  
**Revalidated:** M3, M4  
**Required behavior:** The QR entry and menu journey is one-handed, fast to first content and free of unnecessary mandatory fields.

**Gate-local behavior:** The QR entry and menu journey is one-handed, fast to first content and free of unnecessary mandatory fields.

**Later behavior:** Service-request journeys exist at M3; bill, tip and payment-request journeys at M4.

**Prerequisites:** FR-TAB-001, FR-MNU-004  
**Journeys:** GJ-01A, GJ-01B  
**Acceptance tests:** TST-M2-FR-UX-001A, TST-M3-FR-UX-001A, TST-M4-FR-UX-001A

### FR-UX-005 - Status clarity

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3, M4, M5a  
**Required behavior:** Display text/icon status and timestamps; never communicate critical state by color alone.

**Gate-local behavior:** Customer status uses text and icon with timestamps, never colour alone.

**Later behavior:** Kitchen allergy salience at M3, payment state at M4, and connectivity state at M5a are all critical-state surfaces.

**Prerequisites:** FR-I18N-001A, FR-TAB-003  
**Journeys:** GJ-05, GJ-10  
**Acceptance tests:** TST-M2-FR-UX-005, TST-M3-FR-UX-005, TST-M4-FR-UX-005, TST-M5a-FR-UX-005

### FR-UX-006 - Error recovery

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3, M4  
**Required behavior:** Preserve entered work, explain the issue and offer safe retry/correction without duplicate commitment.

**Gate-local behavior:** A failure preserves cart contents, explains the issue and offers safe retry without duplicating anything.

**Later behavior:** Duplicate commitment becomes materially harmful once orders and payments exist.

**Prerequisites:** FR-TAB-005  
**Journeys:** GJ-01A, GJ-01B  
**Acceptance tests:** TST-M2-FR-UX-006, TST-M3-FR-UX-006, TST-M4-FR-UX-006

### FR-UX-007 - Loading/offline

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M5a  
**Required behavior:** Distinguish loading, locally saved, queued, synchronized, stale, failed and blocked states.

**Gate-local behavior:** Loading, stale and failed states are distinguishable on the customer surface.

**Later behavior:** Locally saved, queued and synchronized states are produced by the synchronization subsystem.

**Prerequisites:** FR-UX-006  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M2-FR-UX-007, TST-M5a-FR-UX-007

### FR-UX-011 - Accessibility

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3, M4, M6  
**Required behavior:** Meet WCAG-aligned keyboard, focus, labels, contrast, zoom and screen-reader essentials.

**Gate-local behavior:** The customer surface meets WCAG-aligned keyboard, focus, label, contrast, zoom and screen-reader essentials in all three locales.

**Later behavior:** Staff surfaces at M3 and M4, and the reporting surface at M6, must meet the same standard.

**Prerequisites:** FR-UX-005  
**Journeys:** GJ-03A  
**Acceptance tests:** TST-M2-FR-UX-011, TST-M3-FR-UX-011, TST-M4-FR-UX-011, TST-M6-FR-UX-011

### FR-UX-012 - Performance budgets

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3, M6  
**Required behavior:** Define and test key-page load, interaction and queue update budgets under realistic devices/network.

**Gate-local behavior:** Menu and QR entry pages meet defined budgets on realistic devices and networks.

**Later behavior:** Queue update budgets require the KDS realtime surface; production thresholds are confirmed on the deployment.

**Prerequisites:** FR-UX-001A  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M2-FR-UX-012, TST-M3-FR-UX-012, TST-M6-FR-UX-012

### FR-UX-013 - Localization fit

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M4  
**Required behavior:** Allow longer French/Amharic text and Arabic RTL without clipping or hard-coded widths.

**Gate-local behavior:** Longer Amharic strings and Arabic RTL render without clipping or hard-coded widths on the menu surface.

**Later behavior:** Bill, tip and receipt layouts are the tightest constrained surfaces.

**Prerequisites:** FR-I18N-002  
**Journeys:** GJ-02B, GJ-03B  
**Acceptance tests:** TST-M2-FR-UX-013, TST-M4-FR-UX-013

### FR-UX-014 - Empty states

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M6  
**Required behavior:** Use instructive empty/error states and never display fabricated analytics.

**Gate-local behavior:** Empty and error states are instructive and no placeholder or fabricated figure is displayed.

**Later behavior:** The no-fabricated-analytics rule bites hardest on the reporting surface.

**Prerequisites:** FR-UX-006  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M2-FR-UX-014, TST-M6-FR-UX-014

### FR-UX-020 - Consistent design system

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M2  
**Revalidated:** M3, M4  
**Required behavior:** Use a shared component/token system across customer and staff apps while allowing tenant branding boundaries.

**Gate-local behavior:** A shared token and component system drives the customer surface with tenant branding applied through configuration.

**Later behavior:** Staff surfaces at M3 and M4 consume the same system.

**Prerequisites:** FR-CFG-006  
**Journeys:** None  
**Acceptance tests:** TST-M2-FR-UX-020, TST-M3-FR-UX-020, TST-M4-FR-UX-020

# Gate M3

## Allergens and Dietary Safety

### FR-SAF-004 - Prominent routing

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Display allergy flags prominently on confirmation, kitchen tickets, KDS, expo and service handoff.

**Gate-local behavior:** Allergy flags render prominently on the order confirmation, kitchen ticket, KDS, expo and service handoff surfaces.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-SAF-003, FR-FUL-001  
**Journeys:** GJ-01A, GJ-05  
**Acceptance tests:** TST-M3-FR-SAF-004

## Carts and Orders

### FR-ORD-001A - Dine-in order aggregate

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-ORD-001`  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** A single order aggregate serves both QR dine-in and waiter-entered dine-in with channel-specific policy fields.

**Gate-local behavior:** A single order aggregate serves both QR dine-in and waiter-entered dine-in with channel-specific policy fields.

**Later behavior:** The counter POS channel does not exist until the POS surface is built.

**Prerequisites:** FR-TAB-005, FR-MNU-009  
**Journeys:** GJ-01A, GJ-05  
**Acceptance tests:** TST-M3-FR-ORD-001A

### FR-ORD-002 - Draft cart

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Maintain draft carts without reserving stock or creating financial commitment.

**Gate-local behavior:** Draft carts persist with no reservation record and no financial obligation created.

**Later behavior:** The no-financial-commitment claim is re-proven once checks and payments exist.

**Prerequisites:** FR-TAB-005  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M3-FR-ORD-002, TST-M4-FR-ORD-002

### FR-ORD-003 - Order preview

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Return a server-calculated preview with line prices, modifiers, tax, fees, discounts, availability, timing and policy warnings.

**Gate-local behavior:** Preview is calculated server-side and returns every named component with no client-side price authority.

**Later behavior:** Tax, fee and discount figures become financially binding when they flow into a check.

**Prerequisites:** FR-MNU-009, FR-MNU-007  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M3-FR-ORD-003, TST-M4-FR-ORD-003

### FR-ORD-004 - Submit idempotency

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M5a  
**Required behavior:** Require idempotency key for submission and return the original outcome for safe retries.

**Gate-local behavior:** Duplicate submission with the same key returns the original outcome and creates no second order.

**Later behavior:** The same guarantee must hold when submissions are replayed through the outlet outbox after an outage.

**Prerequisites:** FR-DAT-007  
**Journeys:** GJ-01A, GJ-10  
**Acceptance tests:** TST-M3-FR-ORD-004, TST-M5a-FR-ORD-004

### FR-ORD-005 - Commercial and language snapshot

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Persist item, modifier, discount, tax, fee and total snapshots used at acceptance together with the customer-selected locale used for communications and receipt evidence.

**Gate-local behavior:** Acceptance snapshots persist for every named component with the locale recorded on the order.

**Later behavior:** The receipt evidence use of these snapshots exists only at M4.

**Prerequisites:** FR-MNU-009, FR-I18N-005  
**Journeys:** GJ-01A, GJ-02B  
**Acceptance tests:** TST-M3-FR-ORD-005, TST-M4-FR-ORD-005

### FR-ORD-006 - Availability revalidation

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Revalidate item/modifier availability, hours, channel, quantity and capacity at submission.

**Gate-local behavior:** Submission re-checks availability, hours, channel, quantity and station capacity and rejects stale carts.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-MNU-007, FR-FUL-013  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M3-FR-ORD-006

### FR-ORD-007A - Order acceptance

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-ORD-007`  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Automatic and staff-confirmed acceptance resolve per channel and outlet policy.

**Gate-local behavior:** Automatic and staff-confirmed acceptance resolve per channel and outlet policy.

**Later behavior:** Payment-dependent acceptance requires payment authorization to exist.

**Prerequisites:** FR-CFG-002A  
**Journeys:** GJ-01A, GJ-05  
**Acceptance tests:** TST-M3-FR-ORD-007A

### FR-ORD-008 - Line ownership

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Optionally associate lines with table participants without requiring every guest to register.

**Gate-local behavior:** Lines optionally carry a participant reference and unregistered guests can still order.

**Later behavior:** Participant attribution becomes financially material when bills are split per payer.

**Prerequisites:** FR-TAB-004, FR-ORD-001A  
**Journeys:** GJ-04, GJ-06  
**Acceptance tests:** TST-M3-FR-ORD-008, TST-M4-FR-ORD-008

### FR-ORD-009 - Add-on orders

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Allow additional orders in the same table session while preserving separate timestamps and fulfillment.

**Gate-local behavior:** Add-on orders create distinct orders and tickets in one session with independent timestamps.

**Later behavior:** Add-on orders must consolidate correctly onto one check.

**Prerequisites:** FR-ORD-001A, FR-FUL-002  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M3-FR-ORD-009, TST-M4-FR-ORD-009

### FR-ORD-010 - Amendment

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Use explicit amendment events for allowed pre-preparation changes and retain before/after details.

**Gate-local behavior:** Pre-preparation amendments emit explicit events retaining before/after detail; post-preparation changes are refused.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-DAT-008A, FR-FUL-003  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M3-FR-ORD-010

### FR-ORD-011 - Cancellation

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Apply item/order cancellation policy by state, channel, reason, payment and preparation progress.

**Gate-local behavior:** Cancellation is permitted or refused per state, channel, reason and preparation progress.

**Later behavior:** The payment dimension of the policy requires payments to exist.

**Prerequisites:** FR-CFG-002A, FR-CFG-003  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M3-FR-ORD-011, TST-M4-FR-ORD-011

### FR-ORD-012A - Operational void

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-ORD-012`  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Authorized void after acceptance records reason and immutable audit for an unpaid order.

**Gate-local behavior:** Authorized void after acceptance records reason and immutable audit for an unpaid order.

**Later behavior:** Linked payment and tip correction cannot be proven before payments and tips exist.

**Prerequisites:** FR-AUTH-006, FR-DAT-008A  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M3-FR-ORD-012A, TST-M4-FR-ORD-012A

### FR-ORD-013 - Notes

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Separate customer notes, allergy declarations, kitchen instructions and private staff notes.

**Gate-local behavior:** Four note classes are stored separately with correct audience filtering; private staff notes never reach the customer surface.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-SAF-003, FR-AUTH-008  
**Journeys:** GJ-01A, GJ-05  
**Acceptance tests:** TST-M3-FR-ORD-013

### FR-ORD-016A - Dine-in order timeline

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-ORD-016`  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Timeline renders order, station and service events chronologically with audience filtering.

**Gate-local behavior:** Timeline renders order, station and service events chronologically with audience filtering.

**Later behavior:** Check and payment events do not exist until M4.

**Prerequisites:** FR-DAT-010, FR-ORD-013  
**Journeys:** GJ-01A, GJ-01B  
**Acceptance tests:** TST-M3-FR-ORD-016A, TST-M4-FR-ORD-016A

### FR-ORD-017 - Duplicate detection

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M5a  
**Required behavior:** Detect suspicious duplicate orders while allowing intentional repeat/add-on orders.

**Gate-local behavior:** Suspicious duplicates are flagged while deliberate repeat and add-on orders pass unimpeded.

**Later behavior:** Detection must not produce false positives when orders replay through the outlet outbox.

**Prerequisites:** FR-ORD-004, FR-ORD-009  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M3-FR-ORD-017, TST-M5a-FR-ORD-017

### FR-ORD-019A - Operational source attribution

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-ORD-019`  
**Introduced:** M3  
**Revalidated:** M4, M5a  
**Required behavior:** A stable correlation chain links all six named artifacts and survives projection rebuild.

**Gate-local behavior:** A stable correlation chain links all six named artifacts and survives projection rebuild.

**Later behavior:** Correlation extends to check and payment records once they exist, and across the sync boundary.

**Prerequisites:** FR-DAT-003, FR-FUL-002  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M3-FR-ORD-019A, TST-M4-FR-ORD-019A, TST-M5a-FR-ORD-019A

## Data Architecture

### FR-DAT-008A - Accepted-order ledger

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-DAT-008`  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Accepted orders are append-only or reversal-based; no destructive edit path exists.

**Gate-local behavior:** Accepted orders are append-only or reversal-based; no destructive edit path exists.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-DAT-002, FR-SEC-009  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M3-FR-DAT-008A

### FR-DAT-010 - Projection rebuild

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4, M5a  
**Required behavior:** Rebuild key projections from authoritative events/ledgers and compare deterministically.

**Gate-local behavior:** Order projections rebuild from authoritative events and compare byte-deterministically.

**Later behavior:** Financial projections at M4; projections rebuilt after outage replay at M5a.

**Prerequisites:** FR-DAT-008A  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M3-FR-DAT-010, TST-M4-FR-DAT-010, TST-M5a-FR-DAT-010

## Integration Runtime

### FR-INT-005 - Idempotency

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4, M5a  
**Required behavior:** Every externally repeated Phase 1 command and event has an idempotency key and returns the original outcome without duplicate commercial effect.

**Gate-local behavior:** Repeated M3 commands return the original outcome with no duplicate order or ticket.

**Later behavior:** Payment and tip commands carry commercial effect from M4; replayed sync events from M5a.

**Prerequisites:** FR-ORD-004  
**Journeys:** GJ-01A, GJ-10  
**Acceptance tests:** TST-M3-FR-INT-005, TST-M4-FR-INT-005, TST-M5a-FR-INT-005

### FR-INT-007 - Dead letter

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4, M5a  
**Required behavior:** Move repeatedly failing Phase 1 integration or synchronization work to an operator-visible dead-letter queue with reason and safe replay controls.

**Gate-local behavior:** Repeatedly failing notification jobs move to an operator-visible dead-letter queue with reason and safe replay.

**Later behavior:** Payment-adapter failures at M4 and synchronization work at M5a use the same queue.

**Prerequisites:** FR-NOT-001  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M3-FR-INT-007, TST-M4-FR-INT-007, TST-M5a-FR-INT-007

### FR-INT-014 - Correlation

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4, M5a  
**Required behavior:** Propagate correlation IDs across customer command, outlet persistence, kitchen ticket, bill, payment, tip, sync and audit records.

**Gate-local behavior:** Correlation IDs propagate from customer command through persistence, kitchen ticket and audit records.

**Later behavior:** Bill, payment and tip records exist at M4; outlet persistence and sync records at M5a.

**Prerequisites:** FR-ORD-019A  
**Journeys:** GJ-01A, GJ-10  
**Acceptance tests:** TST-M3-FR-INT-014, TST-M4-FR-INT-014, TST-M5a-FR-INT-014

## Internationalization and Localization

### FR-I18N-001B - Customer service languages

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-I18N-001`  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Order status and service text render in the session language across the ordering and service journeys.

**Gate-local behavior:** Order status and service text render in the session language across the ordering and service journeys.

**Later behavior:** Bills and receipts remain outside this clause.

**Prerequisites:** FR-I18N-001A, FR-ORD-016A  
**Journeys:** GJ-01A, GJ-02, GJ-03A  
**Acceptance tests:** TST-M3-FR-I18N-001B

### FR-I18N-008 - Customer communications

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Customer status, service and receipt communications use the language snapshotted on the table session or order, with approved fallback rules.

**Gate-local behavior:** Status and service communications render in the snapshotted language with approved fallback.

**Later behavior:** Receipt communications exist at M4.

**Prerequisites:** FR-I18N-005, FR-NOT-001  
**Journeys:** GJ-02, GJ-02B  
**Acceptance tests:** TST-M3-FR-I18N-008, TST-M4-FR-I18N-008

## Kitchen/Bar/Expo Fulfillment

### FR-FUL-001 - Station routing

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M5a  
**Required behavior:** Route accepted line units to kitchen, bar, coffee, bakery, dessert, expo or configured stations using versioned rules.

**Gate-local behavior:** Accepted line units route to the correct station by versioned rule, including multi-station orders.

**Later behavior:** Routing must continue to function on the outlet node during an outage.

**Prerequisites:** FR-TEN-002A, FR-ORD-001A  
**Journeys:** GJ-01A, GJ-05  
**Acceptance tests:** TST-M3-FR-FUL-001, TST-M5a-FR-FUL-001

### FR-FUL-002 - Ticket identity

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Create fulfillment tickets separate from the commercial order and support multiple stations per order.

**Gate-local behavior:** Tickets exist as records distinct from the order and one order fans out to multiple station tickets.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-FUL-001  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M3-FR-FUL-002

### FR-FUL-003 - KDS queue

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M5a  
**Required behavior:** Show new, acknowledged, preparing, held, ready, completed and exception tickets with elapsed/SLA time.

**Gate-local behavior:** All seven ticket states render on KDS with correct elapsed and SLA time.

**Later behavior:** The same KDS must operate from the local node during an outage.

**Prerequisites:** FR-FUL-002  
**Journeys:** GJ-01A, GJ-05, GJ-10  
**Acceptance tests:** TST-M3-FR-FUL-003, TST-M5a-FR-FUL-003

### FR-FUL-004 - Line-level progress

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Track quantities and statuses at line-unit level so partial preparation and partial readiness are visible.

**Gate-local behavior:** Line-unit quantities and statuses support partial preparation and partial readiness.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-FUL-003  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M3-FR-FUL-004

### FR-FUL-005 - Accept/recall

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Allow station acceptance and controlled recall of recently completed tickets with audit.

**Gate-local behavior:** Stations accept tickets and recall recently completed ones within policy, with immutable audit.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-FUL-003, FR-DAT-008A  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M3-FR-FUL-005

### FR-FUL-006 - Course firing

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Support held courses and authorized fire commands from waiter/expo or configured timing.

**Gate-local behavior:** Courses hold and fire on authorized command or configured timing.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-FUL-003  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M3-FR-FUL-006

### FR-FUL-007 - Priority

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Apply ordinary, rush and accessibility/service priority using authorized reason and visible attribution.

**Gate-local behavior:** Three priority levels apply with authorized reason and visible attribution on KDS.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-FUL-003, FR-CFG-003  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M3-FR-FUL-007

### FR-FUL-008 - Allergy emphasis

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M5a  
**Required behavior:** Render allergy concerns in high-salience non-color-only form and require acknowledgement where configured.

**Gate-local behavior:** Allergy concerns render with non-color-only salience and require station acknowledgement where configured.

**Later behavior:** The same salience must survive the printed station ticket.

**Prerequisites:** FR-SAF-004  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M3-FR-FUL-008, TST-M5a-FR-FUL-008

### FR-FUL-009 - Expo coordination

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Provide an expo view combining station readiness and blocking incomplete sets before service.

**Gate-local behavior:** Expo view aggregates station readiness and blocks service of incomplete sets.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-FUL-003, FR-FUL-004  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M3-FR-FUL-009

### FR-FUL-010 - Ready notification

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M5a  
**Required behavior:** Notify assigned waiter/runner when all or selected items are ready and escalate uncollected items.

**Gate-local behavior:** Ready notifications reach the assigned waiter and uncollected items escalate per policy.

**Later behavior:** Notification delivery must continue from the local node during an outage.

**Prerequisites:** FR-NOT-001, FR-FUL-009  
**Journeys:** GJ-01A, GJ-10  
**Acceptance tests:** TST-M3-FR-FUL-010, TST-M5a-FR-FUL-010

### FR-FUL-011 - Serve confirmation

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Record who collected and served items and allow missing/wrong item exception.

**Gate-local behavior:** Collection and service are recorded with actor identity and missing/wrong-item exceptions are capturable.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-FUL-009, FR-AUTH-008  
**Journeys:** GJ-01A, GJ-05  
**Acceptance tests:** TST-M3-FR-FUL-011

### FR-FUL-012 - Preparation timer

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M6  
**Required behavior:** Calculate prep and wait times per station/item/order for live operations and later analytics.

**Gate-local behavior:** Prep and wait times compute correctly per station, item and order for live operational use.

**Later behavior:** Analytical consumption of these measures belongs to operational reporting.

**Prerequisites:** FR-FUL-003, FR-DAT-004  
**Journeys:** None  
**Acceptance tests:** TST-M3-FR-FUL-012, TST-M6-FR-FUL-012

### FR-FUL-013 - Capacity controls

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Allow configurable throttling or promise-time adjustment when station workload exceeds thresholds.

**Gate-local behavior:** Throttling or promise-time adjustment triggers when configured workload thresholds are exceeded.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-FUL-012, FR-CFG-002A  
**Journeys:** GJ-01A  
**Acceptance tests:** TST-M3-FR-FUL-013

### FR-FUL-014 - Printer fallback

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M5a  
**Required behavior:** Generate deduplicated station tickets when KDS is unavailable or policy requires paper.

**Gate-local behavior:** Station ticket documents render with deduplication logic and correct content when KDS is unavailable or policy requires paper.

**Later behavior:** Physical printing, print-agent delivery and print-job deduplication across restart belong to the local print path.

**Prerequisites:** FR-FUL-002  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M3-FR-FUL-014, TST-M5a-FR-FUL-014

### FR-FUL-015 - Station transfer

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M5a  
**Required behavior:** Allow authorized rerouting if a station/device is unavailable without duplicating work.

**Gate-local behavior:** Authorized reroute moves a ticket to another station without duplicating line units.

**Later behavior:** Rerouting must behave correctly when the outlet node is authoritative during an outage.

**Prerequisites:** FR-FUL-001  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M3-FR-FUL-015, TST-M5a-FR-FUL-015

### FR-FUL-016A - Waste and rework operations

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-FUL-016`  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Rework, remake and service-waste events record reason, actor and the linked order/ticket.

**Gate-local behavior:** Rework, remake and service-waste events record reason, actor and the linked order/ticket.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-CFG-003, FR-FUL-002  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M3-FR-FUL-016A

## Notifications

### FR-NOT-001 - Event-driven notifications

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4, M5a, M5b  
**Required behavior:** Generate event-driven local/in-app notifications for order, kitchen, service request, bill, payment, tip, outage and synchronization events.

**Gate-local behavior:** Order, kitchen and service-request events generate in-app notifications to the correct recipients.

**Later behavior:** Bill, payment and tip events exist at M4; outage and synchronization events at M5a and M5b.

**Prerequisites:** FR-ORD-016A, FR-FUL-003  
**Journeys:** GJ-01A, GJ-04  
**Acceptance tests:** TST-M3-FR-NOT-001, TST-M4-FR-NOT-001, TST-M5a-FR-NOT-001, TST-M5b-FR-NOT-001

### FR-NOT-003 - Templates

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Store human-approved English, Amharic and Arabic customer notification templates plus English staff templates for Phase 1.

**Gate-local behavior:** Approved templates exist in three customer languages plus English staff templates and render for M3 events.

**Later behavior:** Bill, payment and tip templates are added when those events exist.

**Prerequisites:** FR-I18N-003, FR-NOT-001  
**Journeys:** GJ-02  
**Acceptance tests:** TST-M3-FR-NOT-003, TST-M4-FR-NOT-003

### FR-NOT-005 - Critical alerts

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4, M5a  
**Required behavior:** Route critical operational alerts for payment mismatch, printer failure, local-node failure, sync conflict and security events to accountable staff.

**Gate-local behavior:** Security and operational alerts existing at M3 route to accountable staff with correct escalation.

**Later behavior:** Payment mismatch requires payments; printer failure, local-node failure and sync conflict require the outlet node.

**Prerequisites:** FR-NOT-001, FR-AUTH-008  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M3-FR-NOT-005, TST-M4-FR-NOT-005, TST-M5a-FR-NOT-005

### FR-NOT-007 - Deduplication

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M5a  
**Required behavior:** Deduplicate repeated notifications by event and recipient while allowing deliberate repeated service requests.

**Gate-local behavior:** Repeated notifications for one event and recipient collapse while deliberate repeat requests still notify.

**Later behavior:** Deduplication must hold when notifications replay after reconnection.

**Prerequisites:** FR-NOT-001  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M3-FR-NOT-007, TST-M5a-FR-NOT-007

### FR-NOT-009 - Deep links

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M5a  
**Required behavior:** Notification links open the correct local or cloud screen for the authorized outlet/session.

**Gate-local behavior:** Notification links open the correct cloud screen and enforce outlet/session authorization.

**Later behavior:** The local screen target does not exist until the outlet node serves screens.

**Prerequisites:** FR-NOT-001, FR-AUTH-008  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M3-FR-NOT-009, TST-M5a-FR-NOT-009

### FR-NOT-010 - No sensitive leakage

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4, M5a  
**Required behavior:** Do not include sensitive customer, payment or authentication data in notification payloads or logs.

**Gate-local behavior:** Notification payloads and logs contain no sensitive customer or authentication data for M3 event classes.

**Later behavior:** Payment data does not exist in any payload until payments exist.

**Prerequisites:** FR-SEC-011, FR-NOT-001  
**Journeys:** None  
**Acceptance tests:** TST-M3-FR-NOT-010, TST-M4-FR-NOT-010, TST-M5a-FR-NOT-010

### FR-NOT-011 - Escalation

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M5a  
**Required behavior:** Escalate unacknowledged service and operational alerts according to outlet policy.

**Gate-local behavior:** Unacknowledged service and operational alerts escalate per outlet policy with recorded escalation events.

**Later behavior:** Operational alert classes originating at the outlet node escalate through the same policy.

**Prerequisites:** FR-NOT-005, FR-SRV-004  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M3-FR-NOT-011, TST-M5a-FR-NOT-011

### FR-NOT-012 - Notification center

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Provide an English staff notification center and localized customer status timeline for Phase 1.

**Gate-local behavior:** Staff notification center renders in English and the customer status timeline renders in the session language.

**Later behavior:** The customer timeline gains check and payment entries at M4.

**Prerequisites:** FR-NOT-001, FR-ORD-016A  
**Journeys:** GJ-02  
**Acceptance tests:** TST-M3-FR-NOT-012, TST-M4-FR-NOT-012

## Service Requests

### FR-SRV-001 - Request types

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Configure translated customer requests such as call waiter, water, cutlery, assistance, missing item, packaging and bill.

**Gate-local behavior:** The translated request catalog exists and every named request type can be raised from a table session.

**Later behavior:** The bill request only produces a check once billing exists.

**Prerequisites:** FR-I18N-003, FR-TAB-003  
**Journeys:** GJ-04, GJ-01B  
**Acceptance tests:** TST-M3-FR-SRV-001, TST-M4-FR-SRV-001

### FR-SRV-002 - Routing

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Route requests by table assignment, service area, role and availability.

**Gate-local behavior:** Requests route to the correct staff by table assignment, service area, role and current presence.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-TAB-006, FR-SRV-007A  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M3-FR-SRV-002

### FR-SRV-003 - Acknowledgement

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Allow an employee to accept a request and show customer-visible received/being-handled status.

**Gate-local behavior:** Acceptance transitions the request and the customer sees received/being-handled status in the session language.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-SRV-002  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M3-FR-SRV-003

### FR-SRV-004 - SLA timer

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Track response deadline, reminders and escalation to supervisor/alternate staff.

**Gate-local behavior:** Deadlines, reminders and escalation to supervisor or alternate staff fire correctly.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-SRV-003  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M3-FR-SRV-004

### FR-SRV-005 - Completion

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Require completion status and optional result/reason for exceptions.

**Gate-local behavior:** A request cannot close without completion status; exceptions capture result and reason.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-SRV-003, FR-CFG-003  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M3-FR-SRV-005

### FR-SRV-006 - Deduplication

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Avoid accidental repeated taps creating uncontrolled duplicate alerts while preserving deliberate repeats.

**Gate-local behavior:** Rapid repeated taps collapse into one alert while a deliberate later repeat still raises a new request.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-SRV-001  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M3-FR-SRV-006

### FR-SRV-007A - Ephemeral waiter availability

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-SRV-007`  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Three presence states drive request routing and are discarded per operational-session retention.

**Gate-local behavior:** Three presence states drive request routing and are discarded per operational-session retention.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-AUTH-008  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M3-FR-SRV-007A

### FR-SRV-008 - Internal tasks

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Allow staff-generated service tasks linked to table/order/customer issue.

**Gate-local behavior:** Staff create tasks linked to a table, order or customer issue with correct correlation.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-SRV-001, FR-ORD-019A  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M3-FR-SRV-008

### FR-SRV-009 - Customer messaging

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Provide limited translated status messages without exposing staff identity unless configured.

**Gate-local behavior:** Customer status messages render translated and omit staff identity unless configuration permits it.

**Later behavior:** None beyond M3 for this clause.

**Prerequisites:** FR-I18N-008, FR-SRV-003  
**Journeys:** GJ-02  
**Acceptance tests:** TST-M3-FR-SRV-009

## Staff POS and Outlet UX

### FR-POS-001 - Terminal registration

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Register POS/waiter/KDS devices to a tenant/outlet/device profile and revoke compromised terminals.

**Gate-local behavior:** Waiter and KDS devices register to a tenant/outlet/device profile and revocation immediately blocks them.

**Later behavior:** POS terminals are a further device class introduced with the POS surface.

**Prerequisites:** FR-SEC-014, FR-TEN-002A  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M3-FR-POS-001, TST-M4-FR-POS-001

### FR-POS-002 - Role home

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Present role-specific queues and next actions rather than generic CRUD menus.

**Gate-local behavior:** Waiter and kitchen roles land on task queues with next actions, not generic menus.

**Later behavior:** Cashier and manager role homes exist with the POS surface.

**Prerequisites:** FR-AUTH-008, FR-FUL-003  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M3-FR-POS-002, TST-M4-FR-POS-002

### FR-POS-003A - Waiter dine-in ordering

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-POS-003`  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Waiter-entered dine-in orders apply identical menu, modifier, price, safety and authorization rules as QR ordering.

**Gate-local behavior:** Waiter-entered dine-in orders apply identical menu, modifier, price, safety and authorization rules as QR ordering.

**Later behavior:** The tax rule comparison is only fully provable once tax reaches a bill; counter orders need POS.

**Prerequisites:** FR-ORD-001A, FR-MNU-006  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M3-FR-POS-003A, TST-M4-FR-POS-003A

### FR-POS-004 - Table view

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Show floor/list occupancy, assigned waiter, open requests, order progress, unpaid balance and attention flags.

**Gate-local behavior:** Occupancy, assigned waiter, open requests, order progress and attention flags render correctly.

**Later behavior:** Unpaid balance requires checks to exist.

**Prerequisites:** FR-TAB-006, FR-SRV-003  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M3-FR-POS-004, TST-M4-FR-POS-004

### FR-POS-005 - Fast item entry

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Support touch search, categories, favorites, barcode where appropriate and keyboard shortcuts.

**Gate-local behavior:** Fast item entry works on the waiter surface with search, categories, favorites and shortcuts.

**Later behavior:** The same entry affordances are required on the POS terminal.

**Prerequisites:** FR-MNU-012, FR-POS-003A  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M3-FR-POS-005, TST-M4-FR-POS-005

### FR-POS-006 - Manager override

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Request and record supervisor approval without sharing credentials or bypassing audit.

**Gate-local behavior:** Supervisor approval for M3 overrides (void, priority, reroute) is recorded without credential sharing.

**Later behavior:** Financial overrides such as discount, refund and tip correction exist at M4.

**Prerequisites:** FR-AUTH-006, FR-ORD-012A  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M3-FR-POS-006, TST-M4-FR-POS-006

### FR-POS-007 - Shift handover

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Transfer responsibility for open tables/tasks/cash only through explicit handover workflow.

**Gate-local behavior:** Open tables and tasks transfer only through an explicit acknowledged handover.

**Later behavior:** Cash responsibility handover requires cash shifts.

**Prerequisites:** FR-TAB-006, FR-SRV-008  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M3-FR-POS-007, TST-M4-FR-POS-007

### FR-POS-009 - Accessibility mode

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Support larger targets/text and reduced-motion/high-contrast preferences where configured.

**Gate-local behavior:** Accessibility preferences apply on the waiter and KDS surfaces.

**Later behavior:** The POS terminal surface must honour the same preferences.

**Prerequisites:** FR-POS-002  
**Journeys:** None  
**Acceptance tests:** TST-M3-FR-POS-009, TST-M4-FR-POS-009

### FR-POS-010A - Operational search

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-POS-010`  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Order and table search works with tenant/outlet and role filtering and no cross-tenant leakage.

**Gate-local behavior:** Order and table search works with tenant/outlet and role filtering and no cross-tenant leakage.

**Later behavior:** Check, receipt and payment/reference identifiers do not exist until M4.

**Prerequisites:** FR-AUTH-008, FR-ORD-019A  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M3-FR-POS-010A, TST-M4-FR-POS-010A

## Tables and Sessions

### FR-TAB-007A - Merge tables for service

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-TAB-007`  
**Introduced:** M3  
**Revalidated:** None  
**Required behavior:** Two physical tables merge into one service session with orders and requests correctly consolidated and audited.

**Gate-local behavior:** Two physical tables merge into one service session with orders and requests correctly consolidated and audited.

**Later behavior:** The check-splitting half of this row belongs to billing.

**Prerequisites:** FR-TAB-003, FR-TAB-006  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M3-FR-TAB-007A

### FR-TAB-008 - Move session

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Transfer an open session between tables without losing orders, requests or checks.

**Gate-local behavior:** An open session moves between tables preserving session identity, orders and service requests.

**Later behavior:** Preservation of checks can only be proven once checks exist.

**Prerequisites:** FR-TAB-003, FR-ORD-001A  
**Journeys:** GJ-04  
**Acceptance tests:** TST-M3-FR-TAB-008, TST-M4-FR-TAB-008

### FR-TAB-009 - Session closure

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Close only after service and financial conditions are met or an authorized exception is recorded.

**Gate-local behavior:** A session cannot close with outstanding service obligations unless an authorized exception is recorded.

**Later behavior:** The financial condition is unprovable before checks and settlement exist.

**Prerequisites:** FR-TAB-003, FR-FUL-001  
**Journeys:** GJ-01B  
**Acceptance tests:** TST-M3-FR-TAB-009, TST-M4-FR-TAB-009

## Testing and Evidence

### FR-TST-005A - Phase 1 end-to-end journeys

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** split_successor from `FR-TST-005`  
**Introduced:** M3  
**Revalidated:** M4, M5a, M5b, M6  
**Required behavior:** Customer, waiter and KDS journeys run in browser/device automation against real persistence.

**Gate-local behavior:** Customer, waiter and KDS journeys run in browser/device automation against real persistence.

**Later behavior:** Cashier journeys at M4, outlet-continuity journeys at M5a and M5b, manager and administration journeys at M6.

**Prerequisites:** FR-TST-013  
**Journeys:** GJ-01A, GJ-01B, GJ-08, GJ-10, GJ-12  
**Acceptance tests:** TST-M3-FR-TST-005A, TST-M4-FR-TST-005A, TST-M5a-FR-TST-005A, TST-M5b-FR-TST-005A, TST-M6-FR-TST-005A

### FR-TST-007A - Phase 1 concurrency tests

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** split_successor from `FR-TST-007`  
**Introduced:** M3  
**Revalidated:** M4, M5a, M5b  
**Required behavior:** Duplicate order submit races are exercised and produce no duplicate commercial effect.

**Gate-local behavior:** Duplicate order submit races are exercised and produce no duplicate commercial effect.

**Later behavior:** Payment, proof, tip, split and cash races at M4; synchronization replay at M5a; authority-lease races at M5b.

**Prerequisites:** FR-ORD-004, FR-ORD-017  
**Journeys:** GJ-06, GJ-09, GJ-10  
**Acceptance tests:** TST-M3-FR-TST-007A, TST-M4-FR-TST-007A, TST-M5a-FR-TST-007A, TST-M5b-FR-TST-007A

## UX and Accessibility

### FR-UX-002 - Staff touch first

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Design waiter/POS/KDS controls for quick touch use, large targets and readable distance.

**Gate-local behavior:** Waiter and KDS controls use large touch targets readable at working distance.

**Later behavior:** The POS terminal surface must meet the same standard.

**Prerequisites:** FR-POS-002  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M3-FR-UX-002, TST-M4-FR-UX-002

### FR-UX-004 - Next action

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4, M6  
**Required behavior:** Every operational screen prioritizes the next required action, active exception and elapsed time.

**Gate-local behavior:** Waiter and KDS screens lead with next action, active exception and elapsed time.

**Later behavior:** POS and cashier screens at M4; operator screens at M6.

**Prerequisites:** FR-POS-002, FR-FUL-003  
**Journeys:** GJ-05  
**Acceptance tests:** TST-M3-FR-UX-004, TST-M4-FR-UX-004, TST-M6-FR-UX-004

### FR-UX-008 - Confirmation friction

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Use low friction for ordinary service and deliberate friction for allergy, cancellation, refund, override and payment.

**Gate-local behavior:** Allergy declaration and cancellation carry deliberate confirmation friction while ordinary service does not.

**Later behavior:** Refund, override and payment confirmations exist at M4.

**Prerequisites:** FR-SAF-003, FR-ORD-011  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M3-FR-UX-008, TST-M4-FR-UX-008

### FR-UX-015 - Destructive actions

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M3  
**Revalidated:** M4  
**Required behavior:** Require explicit confirmation and reason where action cannot be trivially undone.

**Gate-local behavior:** Irreversible M3 actions require explicit confirmation and a reason code.

**Later behavior:** Financial irreversible actions exist at M4.

**Prerequisites:** FR-ORD-012A, FR-CFG-003  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M3-FR-UX-015, TST-M4-FR-UX-015

# Gate M4

## Carts and Orders

### FR-ORD-001B - Counter order aggregate

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-ORD-001`  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** The counter POS channel uses the same aggregate and policy model as the dine-in channels with no divergent order path.

**Gate-local behavior:** The counter POS channel uses the same aggregate and policy model as the dine-in channels with no divergent order path.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-ORD-001A, FR-MNU-006  
**Journeys:** GJ-06  
**Acceptance tests:** TST-M4-FR-ORD-001B

### FR-ORD-007B - Financial acceptance revalidation

**Priority:** P0  
**Owner:** Service Execution  
**Lineage:** split_successor from `FR-ORD-007`  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** An order configured for payment-dependent acceptance is accepted only after a verified payment outcome.

**Gate-local behavior:** An order configured for payment-dependent acceptance is accepted only after a verified payment outcome.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-ORD-007A, FR-PAY-015  
**Journeys:** GJ-01B  
**Acceptance tests:** TST-M4-FR-ORD-007B

## Cash Management

### FR-CSH-001 - Cash shift open

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Open a cashier/drawer session with counted float, assigned terminal and approval policy.

**Gate-local behavior:** A cash shift opens with counted float, assigned terminal and configured approval policy.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-POS-001, FR-CFG-002A  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-CSH-001

### FR-CSH-002 - Cash movements

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Record sales receipts, refunds, payouts, drops, float adjustments and transfers as distinct movements.

**Gate-local behavior:** All six movement types record as distinct append-only entries.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-CSH-001, FR-DAT-008B  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-CSH-002

### FR-CSH-003 - Cash count

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Capture denomination count, expected total, actual total and variance.

**Gate-local behavior:** Denomination counting produces expected, actual and variance figures with exact arithmetic.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-CSH-002, FR-DAT-005  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-CSH-003

### FR-CSH-004 - Close approval

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Require cashier submission and optional manager verification; lock finalized shifts.

**Gate-local behavior:** Close requires cashier submission, optional manager verification, and a finalized shift is locked against further movement.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-CSH-003, FR-AUTH-006  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-CSH-004

### FR-CSH-007 - Safe transfer

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Record sealed bag/reference and custody when cash moves to safe or bank.

**Gate-local behavior:** Safe and bank transfers record sealed bag reference and custody chain.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-CSH-002  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-CSH-007

### FR-CSH-008 - Exception report

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M6  
**Required behavior:** Report missing close, excessive variance, unusual refunds/payouts and late settlement.

**Gate-local behavior:** Exception conditions are detected and reported to accountable staff.

**Later behavior:** Presentation within the operational reporting surface with source and freshness labelling.

**Prerequisites:** FR-CSH-004, FR-NOT-005  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-CSH-008, TST-M6-FR-CSH-008

## Checks, Bills and Receipts

### FR-BIL-001 - Check creation

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Create one or more checks from accepted/served order lines without changing order ownership or history.

**Gate-local behavior:** Checks are created from accepted/served lines with order ownership and history unchanged.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-ORD-005, FR-FUL-011  
**Journeys:** GJ-01B, GJ-06  
**Acceptance tests:** TST-M4-FR-BIL-001

### FR-BIL-002 - Check line allocation

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Allocate whole or partial line quantities to a check and prevent double billing.

**Gate-local behavior:** Whole and partial line quantities allocate to checks and a line unit can never be billed twice.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-BIL-001  
**Journeys:** GJ-06  
**Acceptance tests:** TST-M4-FR-BIL-002

### FR-BIL-003 - Split modes

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Split by item, participant, equal share, custom amount or separate orders with deterministic rounding.

**Gate-local behavior:** All five split modes produce deterministic exact results with configured rounding and no lost or duplicated minor units.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-BIL-002, FR-DAT-006  
**Journeys:** GJ-06  
**Acceptance tests:** TST-M4-FR-BIL-003

### FR-BIL-004 - Merge checks

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Merge eligible open checks with audit and preserve original source relationships.

**Gate-local behavior:** Eligible open checks merge with full audit and original source relationships preserved.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-BIL-001, FR-TAB-007B  
**Journeys:** GJ-06  
**Acceptance tests:** TST-M4-FR-BIL-004

### FR-BIL-005 - Tax/service calculation

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Calculate item subtotal, discounts, tax, service charge and other bill components exactly. Optional tip is not part of the bill balance and is calculated and recorded separately.

**Gate-local behavior:** Every bill component computes exactly with fixed-point arithmetic, and tip is excluded from the bill balance entirely.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-DAT-005, FR-MNU-009  
**Journeys:** GJ-01B, GJ-06  
**Acceptance tests:** TST-M4-FR-BIL-005

### FR-BIL-006 - Rounding

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Apply configured currency precision and rounding at defined line/document stages and persist the calculation version.

**Gate-local behavior:** Rounding applies at the configured stages and the calculation version is persisted on the document.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-BIL-005, FR-DAT-006  
**Journeys:** GJ-06  
**Acceptance tests:** TST-M4-FR-BIL-006

### FR-BIL-007 - Bill preview

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Present a translated bill summary showing items, discounts, tax, service charge and bill total. Display the separate optional Tip box only after or beside the bill summary, never mixed into it.

**Gate-local behavior:** The bill summary renders in the session language with the tip box visually separate in all three locales including RTL.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-BIL-005, FR-I18N-001C  
**Journeys:** GJ-01B, GJ-02B, GJ-03B  
**Acceptance tests:** TST-M4-FR-BIL-007

### FR-BIL-008 - Finalize

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Finalize the bill only when its bill balance is settled or an authorized disposition exists. Tip completion is recorded separately and cannot hide an unpaid bill balance.

**Gate-local behavior:** Finalization is refused while the bill balance is outstanding, regardless of tip state, unless an authorized disposition is recorded.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-BIL-005, FR-PAY-017  
**Journeys:** GJ-01B, GJ-07  
**Acceptance tests:** TST-M4-FR-BIL-008

### FR-BIL-009 - Credit/void

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Correct issued bills through authorized void/credit/reissue rather than deletion.

**Gate-local behavior:** Issued bills are correctable only by authorized void, credit or reissue; no delete path exists.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-DAT-008B, FR-AUTH-006  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-BIL-009

### FR-BIL-010 - Digital receipt

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M5a  
**Required behavior:** Generate digital receipts in the customer's selected language showing bill total, optional tip and total paid as separate lines.

**Gate-local behavior:** Digital receipts render in the snapshotted locale with bill total, tip and total paid on separate lines.

**Later behavior:** The physical printed receipt is produced through the local print path.

**Prerequisites:** FR-I18N-005, FR-BIL-005  
**Journeys:** GJ-01B, GJ-02B, GJ-03B  
**Acceptance tests:** TST-M4-FR-BIL-010, TST-M5a-FR-BIL-010

### FR-BIL-011 - Reprint

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M5a  
**Required behavior:** Mark and audit receipt/bill reprints with operator and reason where required.

**Gate-local behavior:** Reprints are marked as reprints and record operator and reason.

**Later behavior:** Physical reprint through the local print path must carry the same marking.

**Prerequisites:** FR-BIL-010, FR-CFG-003  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-BIL-011, TST-M5a-FR-BIL-011

### FR-BIL-012 - Fiscal adapter

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Expose fiscal-document port and reconciliation status without embedding one provider’s schema.

**Gate-local behavior:** The fiscal port exposes documents and reconciliation status against a simulator with no provider-specific schema in the domain model.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-TEN-009A, FR-BIL-010  
**Journeys:** GJ-01B  
**Acceptance tests:** TST-M4-FR-BIL-012

### FR-BIL-013 - Separate tip box

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** The payment experience presents an optional Tip box visibly separate from the bill summary, with no tip selected by default.

**Gate-local behavior:** The tip box is visually separate with no preselected amount or percentage in any locale.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-BIL-007  
**Journeys:** GJ-01B, GJ-02B, GJ-03B  
**Acceptance tests:** TST-M4-FR-BIL-013

### FR-BIL-014 - Bill-tip separation

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Bill balance, service charge, tax, tip and total tendered are separate values and records. A tip never changes order lines or bill allocation.

**Gate-local behavior:** All five values are separately stored and a recorded tip provably leaves order lines and bill allocation unchanged.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-BIL-005, FR-DAT-005  
**Journeys:** GJ-06, GJ-07  
**Acceptance tests:** TST-M4-FR-BIL-014

### FR-BIL-015 - Per-payer tip

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** In split or partial settlement, each payer may choose a separate optional tip attached to that payer's payment, without reallocating bill lines.

**Gate-local behavior:** Each payer in a split settlement records an independent tip attached to their own payment with no bill line reallocation.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-BIL-003  
**Journeys:** GJ-06  
**Acceptance tests:** TST-M4-FR-BIL-015

### FR-BIL-016 - Tip receipt and correction

**Priority:** P0  
**Owner:** Platform Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Receipts display bill and tip separately. Tip refunds, reversals and corrections are separate auditable records linked to the original tip.

**Gate-local behavior:** Receipts separate bill and tip, and tip corrections create linked auditable records without touching the bill.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-BIL-010, FR-PAY-009  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-BIL-016

### FR-BIL-017 - Minimum physical receipt printing

**Priority:** P0  
**Owner:** Billing & Payments  
**Lineage:** new_audit_requirement  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** At M4, a completed settlement produces a real physical customer receipt through a supported minimum production printer path. The receipt uses the customer language and shows bill total, optional tip, total paid and actual payment method separately.

**Gate-local behavior:** Configure one supported cashier-connected receipt printer and physically print the M4 settlement receipt once with correct language, exact values, unique receipt number and actual payment method.

**Later behavior:** M5a adds durable local queueing, retry, restart recovery, deduplication, printer health, outage continuity and reconciliation.

**Prerequisites:** FR-BIL-010, FR-BIL-016, FR-CFG-001D  
**Journeys:** GJ-01B, GJ-02B, GJ-03B, GJ-06, GJ-07  
**Acceptance tests:** TST-M4-FR-BIL-017

## Configuration and Setup

### FR-CFG-001C - Billing and payment setup

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-CFG-001`  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** The guided setup configures taxes, service charges, separate optional-tip settings and the permitted payment methods, and those settings drive a real bill.

**Gate-local behavior:** Create a bill using the configured tax, service-charge, tip and payment settings and verify exact values and the actual permitted payment method.

**Later behavior:** 

**Prerequisites:** FR-PAY-015, FR-BIL-001  
**Journeys:** GJ-01B  
**Acceptance tests:** TST-M4-FR-CFG-001C

### FR-CFG-001D - Minimum receipt-printer setup

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-CFG-001`  
**Introduced:** M4  
**Revalidated:** M5a  
**Required behavior:** At M4 the guided setup registers and tests the minimum production receipt printer used by the cashier for a real physical customer receipt.

**Gate-local behavior:** Register one supported receipt printer, print a test page and print a settlement receipt without relying on the M5a local print queue.

**Later behavior:** M5a adds durable local queueing, retry, restart recovery, deduplication, health and outage continuity.

**Prerequisites:** FR-BIL-010  
**Journeys:** GJ-02B, GJ-03B, GJ-06  
**Acceptance tests:** TST-M4-FR-CFG-001D, TST-M5a-FR-CFG-001D

## Data Architecture

### FR-DAT-008B - Financial and cash ledgers

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-DAT-008`  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Bills, receipts, payments, tips and cash movements are append-only or reversal-based with no destructive correction.

**Gate-local behavior:** Bills, receipts, payments, tips and cash movements are append-only or reversal-based with no destructive correction.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-DAT-008A, FR-DAT-005  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-DAT-008B

## Integration Runtime

### FR-INT-011 - Health

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M5a  
**Required behavior:** Expose truthful health for the narrow Phase 1 integration surface, including outlet-node connectivity, sync lag, printer status and active payment adapters.

**Gate-local behavior:** Health truthfully reports active payment adapters, including that a simulated adapter is reported as simulated.

**Later behavior:** Outlet-node connectivity, sync lag and printer status require the node and print agent.

**Prerequisites:** FR-PAY-015  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M4-FR-INT-011, TST-M5a-FR-INT-011

### FR-INT-013 - Schema version

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M5a, M5b  
**Required behavior:** Version local/cloud protocols and Phase 1 adapter messages; incompatible peers stop safely instead of silently accepting unknown shapes.

**Gate-local behavior:** Adapter messages carry a version and an unknown shape is refused rather than silently accepted.

**Later behavior:** The local/cloud protocol version exists at M5a; agreement on compatibility is part of the reachability proof at M5b.

**Prerequisites:** FR-COM-009  
**Journeys:** GJ-10, GJ-09  
**Acceptance tests:** TST-M4-FR-INT-013, TST-M5a-FR-INT-013, TST-M5b-FR-INT-013

## Internationalization and Localization

### FR-I18N-001C - Bill and receipt languages

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-I18N-001`  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Bill and receipt render completely in the session language for all three locales, including Ethiopic and RTL scripts.

**Gate-local behavior:** Bill and receipt render completely in the session language for all three locales, including Ethiopic and RTL scripts.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-I18N-001A, FR-BIL-010, FR-BIL-017  
**Journeys:** GJ-01B, GJ-02B, GJ-03B  
**Acceptance tests:** TST-M4-FR-I18N-001C

## Payments

### FR-PAY-001 - Payment intent

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Create a payment intent for a specific check balance and payer, with separate optional tip allocation, expiry, idempotency and permitted tender methods.

**Gate-local behavior:** Payment intents bind to a check and payer with separate tip allocation, expiry, idempotency key and permitted methods.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-BIL-001, FR-ORD-004  
**Journeys:** GJ-01B  
**Acceptance tests:** TST-M4-FR-PAY-001

### FR-PAY-002 - Cash payment

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M5a  
**Required behavior:** Record cash settlement locally with exact bill allocation, separate optional tip, amount tendered and change. Cash service continues during internet outage.

**Gate-local behavior:** Cash settlement records exact bill allocation, separate tip, tendered amount and change.

**Later behavior:** Continuation of cash service while the internet is down requires the outlet node to be authoritative.

**Prerequisites:** FR-PAY-001, FR-BIL-005  
**Journeys:** GJ-01B  
**Acceptance tests:** TST-M4-FR-PAY-002, TST-M5a-FR-PAY-002

### FR-PAY-003 - External card terminal

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M5a  
**Required behavior:** Record an external card-terminal result without storing card data. During outage, the method remains available only when the terminal itself can complete payment; otherwise staff must choose another method.

**Gate-local behavior:** External terminal results are recorded with no card data stored anywhere.

**Later behavior:** Availability of the method during outage depends on outlet-node operation and staff guidance.

**Prerequisites:** FR-PAY-001, FR-SEC-011  
**Journeys:** GJ-01B  
**Acceptance tests:** TST-M4-FR-PAY-003, TST-M5a-FR-PAY-003

### FR-PAY-006 - Mixed tender

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Support permitted mixed tender while preserving separate allocations to bill balance and optional tip for each payment.

**Gate-local behavior:** Mixed tender settles one check across methods with each payment carrying its own bill and tip allocation.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-PAY-017, FR-BIL-014  
**Journeys:** GJ-06  
**Acceptance tests:** TST-M4-FR-PAY-006

### FR-PAY-007 - Partial payment

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Support partial settlement and split bills without modifying the original order history; each payer may add a separate tip.

**Gate-local behavior:** Partial settlement and split bills leave order history untouched and each payer tip is independent.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-BIL-003, FR-BIL-015  
**Journeys:** GJ-06  
**Acceptance tests:** TST-M4-FR-PAY-007

### FR-PAY-009 - Refund

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Refund bill payments and tip payments through separate linked reversal records, permissions, reason codes and approval thresholds.

**Gate-local behavior:** Bill and tip refunds create separate linked reversal records under permissions, reason codes and approval thresholds.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-AUTH-006, FR-PAY-017  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-PAY-009

### FR-PAY-010A - Payment reversal

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** split_successor from `FR-PAY-010`  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Payment and tip events are emitted in a documented shape that a future accounting consumer could subscribe to, with no consumer in Phase 1.

**Gate-local behavior:** Payment and tip events are emitted in a documented shape that a future accounting consumer could subscribe to, with no consumer in Phase 1.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-PAY-017  
**Journeys:** GJ-01B  
**Acceptance tests:** TST-M4-FR-PAY-010A

### FR-PAY-012 - Payment failure

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Present retry/alternate method without duplicating the order or payment.

**Gate-local behavior:** A failed payment offers retry or an alternate method with no duplicate order or payment created.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-PAY-001, FR-ORD-004  
**Journeys:** GJ-01B  
**Acceptance tests:** TST-M4-FR-PAY-012

### FR-PAY-013 - Reconciliation

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M5a  
**Required behavior:** Reconcile bill allocations, tip allocations, tender totals, cash shifts and provider references without merging tips into sales revenue.

**Gate-local behavior:** Reconciliation balances all named totals and tips never appear inside sales revenue.

**Later behavior:** Post-outage reconciliation of locally captured payments occurs after synchronization.

**Prerequisites:** FR-PAY-017, FR-CSH-003  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-PAY-013, TST-M5a-FR-PAY-013

### FR-PAY-014 - Payment collection and proof confirmation

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M5a  
**Required behavior:** A customer may request cash, external-terminal collection or proof-based manual mobile-money confirmation. For Telebirr and CBE Birr, staff verifies receipt in the provider application, records the actual provider and masked/reference identifier, and leaves unverified proof pending rather than paid.

**Gate-local behavior:** Proof-based confirmation records provider and masked reference, and an unverified proof remains pending and can never reach captured.

**Later behavior:** Local verification and recording of proof during outage occurs on the outlet node.

**Prerequisites:** FR-PAY-001, FR-SEC-012  
**Journeys:** GJ-02B  
**Acceptance tests:** TST-M4-FR-PAY-014, TST-M5a-FR-PAY-014

### FR-PAY-015 - Offline payment and adapter boundary

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M5a  
**Required behavior:** During internet outage, cash, locally recorded external-terminal payments and locally verified Telebirr/CBE Birr proof confirmation may continue only when staff can verify the provider result. Direct online-provider APIs remain simulated until contracted and credentialed, are unavailable or queued during outage, and cannot support a live pilot-readiness claim. Receipts always state the actual method.

**Gate-local behavior:** The live/simulated/prohibited matrix is enforced: simulated results are labelled and cannot be presented as live, and receipts state the actual method and provider.

**Later behavior:** Continuation and queuing behavior during a real outage is exercised on the outlet node.

**Prerequisites:** FR-PAY-014, FR-BIL-010  
**Journeys:** GJ-01B, GJ-02B  
**Acceptance tests:** TST-M4-FR-PAY-015, TST-M5a-FR-PAY-015

### FR-PAY-016 - PCI boundary

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M6  
**Required behavior:** Keep raw PAN/CVV/card cryptograms outside platform storage, logs and analytics.

**Gate-local behavior:** No PAN, CVV or cryptogram appears in storage, logs or analytics on any payment path.

**Later behavior:** The prohibition is re-proven against the full production artifact and its logs.

**Prerequisites:** FR-SEC-011, FR-PAY-003  
**Journeys:** GJ-01B  
**Acceptance tests:** TST-M4-FR-PAY-016, TST-M6-FR-PAY-016

### FR-PAY-017 - Dual payment allocation

**Priority:** P0  
**Owner:** Commerce & Payments  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** A payment transaction records separate allocations to bill balance and optional tip, with exact arithmetic, independent reversal and no hidden recomputation.

**Gate-local behavior:** Every payment carries two explicit allocations that reverse independently with exact arithmetic and no recomputation on read.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-DAT-005, FR-BIL-014  
**Journeys:** GJ-06, GJ-07  
**Acceptance tests:** TST-M4-FR-PAY-017

## Reporting and Intelligence

### FR-RPT-001 - Role dashboards

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M5a  
**Required behavior:** Provide role-specific Phase 1 dashboards for outlet manager, waiter, cashier, kitchen/expo and technical operator without exposing deferred modules.

**Gate-local behavior:** Provide role-specific dashboards for outlet manager, waiter, cashier and kitchen/expo using only active Phase 1 data and without deferred modules.

**Later behavior:** At M5a add the technical-operator local-node, synchronization and printer dashboard.

**Prerequisites:** FR-RPT-015, FR-AUTH-008  
**Journeys:** GJ-01B, GJ-10  
**Acceptance tests:** TST-M4-FR-RPT-001, TST-M5a-FR-RPT-001

### FR-RPT-002 - Freshness

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M5a  
**Required behavior:** Label operational metrics with source and freshness; local and cloud views must clearly show synchronization status.

**Gate-local behavior:** Label every operational metric with its source and freshness in the cloud reporting view.

**Later behavior:** At M5a show local versus cloud source, synchronization status and staleness explicitly.

**Prerequisites:** FR-RPT-015, FR-DAT-004  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M4-FR-RPT-002, TST-M5a-FR-RPT-002

### FR-RPT-003 - Sales

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Report orders, item sales, discounts, service charges, taxes, bill payments and tips as separately classified values.

**Gate-local behavior:** Report orders, item sales, discounts, service charges, taxes, bill payments and tips as separately classified exact values.

**Later behavior:** 

**Prerequisites:** FR-RPT-015, FR-DAT-005  
**Journeys:** GJ-02B, GJ-03B  
**Acceptance tests:** TST-M4-FR-RPT-003

### FR-RPT-004 - Service

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Report service requests, acknowledgement/completion times, table-session duration and unresolved exceptions.

**Gate-local behavior:** Report service requests, acknowledgement and completion times, table-session duration and unresolved exceptions.

**Later behavior:** 

**Prerequisites:** FR-RPT-015, FR-SRV-001  
**Journeys:** None  
**Acceptance tests:** TST-M4-FR-RPT-004

### FR-RPT-005 - Kitchen

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Report kitchen/bar/expo queue, preparation time, ready-to-serve time, rework and exceptions.

**Gate-local behavior:** Report kitchen, bar and expo queue state, preparation time, ready-to-serve time, rework and exceptions.

**Later behavior:** 

**Prerequisites:** FR-RPT-015, FR-FUL-001  
**Journeys:** None  
**Acceptance tests:** TST-M4-FR-RPT-005

### FR-RPT-013 - Exports

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M6  
**Required behavior:** Export authorized Phase 1 operational data in documented formats with tenant/outlet scoping.

**Gate-local behavior:** Export authorized Phase 1 operational data in documented formats with tenant and outlet scoping.

**Later behavior:** At M6 repeat the export through production roles and the final built artifact.

**Prerequisites:** FR-RPT-015, FR-AUTH-008  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M4-FR-RPT-013, TST-M6-FR-RPT-013

### FR-RPT-014 - Snapshots

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M6  
**Required behavior:** Snapshot operational metrics used for shift close and later audit; a recomputation cannot silently rewrite a signed-off shift result.

**Gate-local behavior:** Shift close writes an immutable metric snapshot that later recomputation cannot alter.

**Later behavior:** The audit consumption of these snapshots occurs in the reporting surface.

**Prerequisites:** FR-CSH-004, FR-DAT-008B  
**Journeys:** GJ-07  
**Acceptance tests:** TST-M4-FR-RPT-014, TST-M6-FR-RPT-014

### FR-RPT-015 - Metric catalog

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M6  
**Required behavior:** Define each Phase 1 metric, formula, timezone, currency, inclusion rule and data source in a versioned catalog.

**Gate-local behavior:** Publish a versioned metric catalog defining each Phase 1 formula, timezone, currency, inclusion rule and data source.

**Later behavior:** At M6 verify the catalog against the complete production reporting surface.

**Prerequisites:** FR-DAT-004, FR-DAT-005  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M4-FR-RPT-015, TST-M6-FR-RPT-015

## Staff POS and Outlet UX

### FR-POS-003B - Counter POS ordering

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-POS-003`  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** Counter orders are created at the POS terminal under the same rules as QR and waiter ordering.

**Gate-local behavior:** Counter orders are created at the POS terminal under the same rules as QR and waiter ordering.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-POS-003A, FR-ORD-001B  
**Journeys:** GJ-06  
**Acceptance tests:** TST-M4-FR-POS-003B

## Tables and Sessions

### FR-TAB-007B - Split session and check

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** split_successor from `FR-TAB-007`  
**Introduced:** M4  
**Revalidated:** None  
**Required behavior:** A merged session splits into separate checks with correct allocation and a complete audit trail.

**Gate-local behavior:** A merged session splits into separate checks with correct allocation and a complete audit trail.

**Later behavior:** None beyond M4 for this clause.

**Prerequisites:** FR-TAB-007A, FR-BIL-003  
**Journeys:** GJ-06  
**Acceptance tests:** TST-M4-FR-TAB-007B

## UX and Accessibility

### FR-UX-018 - Print preview

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M4  
**Revalidated:** M5a  
**Required behavior:** Preview receipt, kitchen, label and operational documents before configuration publication.

**Gate-local behavior:** Receipt and document templates preview accurately before publication.

**Later behavior:** Physical print output must match the preview on the actual printer.

**Prerequisites:** FR-BIL-010  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M4-FR-UX-018, TST-M5a-FR-UX-018

# Gate M5a

## Configuration and Setup

### FR-CFG-001E - Continuity-node setup

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-CFG-001`  
**Introduced:** M5a  
**Revalidated:** M5b  
**Required behavior:** The guided setup registers the outlet continuity node and applies its approved outlet, synchronization, authority and local-service configuration.

**Gate-local behavior:** Register the node, bind it to one tenant and outlet, apply configuration and prove it starts only with the correct outlet identity.

**Later behavior:** M5b activates the same-QR DNS/TLS and authority-lease configuration.

**Prerequisites:** FR-EDG-002A  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-CFG-001E, TST-M5b-FR-CFG-001E

## Data Architecture

### FR-DAT-008C - Synchronization evidence ledger

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-DAT-008`  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** Synchronization evidence records are append-only across replay and restart.

**Gate-local behavior:** Synchronization evidence records are append-only across replay and restart.

**Later behavior:** None beyond M5a for this clause.

**Prerequisites:** FR-DAT-008A, FR-EDG-001  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-DAT-008C

## Deployment and Operations

### FR-OPS-010 - Update rollback

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** M6  
**Required behavior:** Support signed application/node updates, database compatibility checks, staged rollout and rollback without corrupting local queues.

**Gate-local behavior:** Signed node updates apply with database compatibility checks and roll back without corrupting the outbox or inbox.

**Later behavior:** Staged rollout across outlets is a production deployment concern.

**Prerequisites:** FR-EDG-018, FR-INT-003  
**Journeys:** GJ-10, GJ-12  
**Acceptance tests:** TST-M5a-FR-OPS-010, TST-M6-FR-OPS-010

### FR-OPS-018 - Printer/device inventory

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** M6  
**Required behavior:** Maintain an outlet inventory of continuity node, routers, access points, POS terminals, KDS devices and printers with assigned location and support owner.

**Gate-local behavior:** The outlet asset register lists all six device classes with location and support owner.

**Later behavior:** The register is confirmed against the deployed pilot outlet.

**Prerequisites:** FR-POS-001, FR-EDG-001  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M5a-FR-OPS-018, TST-M6-FR-OPS-018

## Integration Runtime

### FR-INT-003 - Outbox

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** Use a transactional outbox for local-to-cloud operational events, payment-provider events and notification jobs required by Phase 1 only.

**Gate-local behavior:** Operational events, payment-provider events and notification jobs enqueue transactionally with the originating write and survive process restart.

**Later behavior:** None beyond M5a for this clause.

**Prerequisites:** FR-EDG-001, FR-DAT-008C  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-INT-003

### FR-INT-004 - Inbox

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** Use an idempotent inbox for cloud-to-outlet configuration and command delivery required by Phase 1 only.

**Gate-local behavior:** Cloud-to-outlet configuration and commands apply exactly once under repeated delivery.

**Later behavior:** None beyond M5a for this clause.

**Prerequisites:** FR-INT-003, FR-INT-005  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-INT-004

## Outlet Edge and Synchronization

### FR-EDG-001 - Deployment profiles

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** M6  
**Required behavior:** Every production Phase 1 outlet runs the focused Outlet Continuity Node. Cloud-only mode is permitted only for development, demonstration or explicitly non-production evaluation.

**Gate-local behavior:** A production outlet profile requires the continuity node and cloud-only mode is refused outside non-production environments.

**Later behavior:** The profile constraint is re-proven against the production deployment artifact.

**Prerequisites:** FR-GOV-001B, FR-OPS-001  
**Journeys:** GJ-10, GJ-12  
**Acceptance tests:** TST-M5a-FR-EDG-001, TST-M6-FR-EDG-001

### FR-EDG-002A - Phase 1 local services

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** split_successor from `FR-EDG-002`  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** The node image contains exactly the five named services and starts them under least privilege.

**Gate-local behavior:** The node image contains exactly the five named services and starts them under least privilege.

**Later behavior:** None beyond M5a for this clause.

**Prerequisites:** FR-EDG-001  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-EDG-002A

### FR-EDG-004A - Outlet-network application serving

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** split_successor from `FR-EDG-004`  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** All four screen families are served from the outlet node over the LAN at its configured endpoint.

**Gate-local behavior:** All four screen families are served from the outlet node over the LAN at its configured endpoint.

**Later behavior:** Reaching those screens through the same public table QR requires split-horizon DNS and public-trust TLS.

**Prerequisites:** FR-EDG-002A  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-EDG-004A

### FR-EDG-005 - Outbox/inbox sync

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** Synchronize through durable outbox/inbox events, ordered cursors, dependency rules and idempotency. Direct database replication is not the business synchronization mechanism.

**Gate-local behavior:** Synchronization uses durable events with ordered cursors and dependency rules; no database replication path exists for business data.

**Later behavior:** None beyond M5a for this clause.

**Prerequisites:** FR-INT-003, FR-INT-004  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-EDG-005

### FR-EDG-008 - Conflict policy

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** Resolve conflicts through explicit domain policy and operator evidence; never use silent last-write-wins for orders, bills, payments, tips, cash or permissions.

**Gate-local behavior:** Conflicts on all six named domains surface to an operator with evidence; no silent overwrite path exists.

**Later behavior:** None beyond M5a for this clause.

**Prerequisites:** FR-EDG-005, FR-DAT-007  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-EDG-008

### FR-EDG-009 - Offline UI

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** M5b  
**Required behavior:** Show customer and staff whether the outlet is cloud-connected, local-continuity or reconciling, without blocking ordinary local service.

**Gate-local behavior:** All three connectivity states display to staff and to customers on the locally served surface without blocking service.

**Later behavior:** The customer-facing display during a genuine same-QR outage session is proven with the M5b routing.

**Prerequisites:** FR-EDG-001, FR-EDG-002A  
**Journeys:** GJ-10, GJ-08  
**Acceptance tests:** TST-M5a-FR-EDG-009, TST-M5b-FR-EDG-009

### FR-EDG-010 - External-action blocking

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** Block or queue actions requiring external authority and explain the restriction; cash, locally supported card-terminal recording and ordinary service continue.

**Gate-local behavior:** Actions needing external authority are blocked or queued with a translated explanation while cash, terminal recording and ordinary service continue.

**Later behavior:** None beyond M5a for this clause.

**Prerequisites:** FR-EDG-001, FR-CFG-002A  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-EDG-010

### FR-EDG-012 - Protocol compatibility

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** M5b  
**Required behavior:** Check cloud, node, API and event-protocol compatibility before synchronization; incompatible versions pause safely and remain locally operable where safe.

**Gate-local behavior:** An incompatible peer pauses synchronization safely while local service continues.

**Later behavior:** Compatibility agreement becomes a field of the bidirectional reachability proof.

**Prerequisites:** FR-INT-013  
**Journeys:** GJ-10, GJ-09  
**Acceptance tests:** TST-M5a-FR-EDG-012, TST-M5b-FR-EDG-012

### FR-EDG-015A - Staff and transaction outage continuity

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** split_successor from `FR-EDG-015`  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** With the internet cut, staff complete waiter entry, KDS preparation, bills, separate tips, cash settlement and local printing through the node.

**Gate-local behavior:** With the internet cut, staff complete waiter entry, KDS preparation, bills, separate tips, cash settlement and local printing through the node.

**Later behavior:** Customer-side local Wi-Fi QR ordering depends on same-QR routing.

**Prerequisites:** FR-EDG-001, FR-EDG-002A, FR-EDG-029  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-EDG-015A

### FR-EDG-016 - Reconnection

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** On reconnection, upload local operations in dependency order, resume cloud reads, reconcile conflicts and prove no duplicate orders, payments or tips.

**Gate-local behavior:** Reconnection uploads in dependency order, resumes cloud reads, reconciles conflicts and produces no duplicate order, payment or tip.

**Later behavior:** None beyond M5a for this clause.

**Prerequisites:** FR-EDG-005, FR-EDG-008  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-EDG-016

### FR-EDG-017 - Edge health

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** M5b  
**Required behavior:** Expose local node, database, worker, print, storage, certificate and synchronization health to the outlet and cloud operator.

**Gate-local behavior:** Node, database, worker, print, storage and synchronization health are exposed truthfully to outlet and cloud operators.

**Later behavior:** Certificate health depends on the per-outlet certificate lifecycle.

**Prerequisites:** FR-INT-011, FR-EDG-002A  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-EDG-017, TST-M5b-FR-EDG-017

### FR-EDG-018 - Edge security

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** M6  
**Required behavior:** Protect the outlet node with device identity, least-privileged services, encrypted secrets, signed updates, host hardening and audited administrative access.

**Gate-local behavior:** The node runs with device identity, least-privileged services, encrypted secrets, signed updates, hardened host and audited admin access.

**Later behavior:** Host hardening and update signing are re-proven against the shipped production node image.

**Prerequisites:** FR-SEC-014, FR-INT-010  
**Journeys:** GJ-10, GJ-12  
**Acceptance tests:** TST-M5a-FR-EDG-018, TST-M6-FR-EDG-018

### FR-EDG-025 - Local readiness dataset

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** Before service, the outlet node stores the active menu, three approved translations, allergens, prices, taxes, service/tip settings, tables, staff access, stations, printers and open sessions.

**Gate-local behavior:** The node holds a complete readiness dataset covering all eleven named element types before service begins.

**Later behavior:** None beyond M5a for this clause.

**Prerequisites:** FR-EDG-002A, FR-MNU-003  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-EDG-025

### FR-EDG-027 - Reconnection reconciliation

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** After reconnection, local events synchronize in dependency order, preserve original IDs and timestamps, reject duplicates and expose conflicts instead of silently overwriting.

**Gate-local behavior:** Replayed events preserve original IDs and timestamps, duplicates are rejected and conflicts surface rather than overwrite.

**Later behavior:** None beyond M5a for this clause.

**Prerequisites:** FR-EDG-016, FR-EDG-008  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-EDG-027

### FR-EDG-029 - Resilient local receipt printing

**Priority:** P0  
**Owner:** Outlet Edge & Operations  
**Lineage:** new_audit_requirement  
**Introduced:** M5a  
**Revalidated:** M6  
**Required behavior:** At M5a, customer receipt printing uses a durable local queue with idempotent job identity, bounded retry, restart recovery, deduplication, printer-health visibility, internet-outage continuity and cloud reconciliation without duplicate physical output.

**Gate-local behavior:** Lose internet, restart the print service and reconnect while a receipt is queued; exactly one physical receipt prints and the job reconciles with complete status evidence.

**Later behavior:** Repeat in the production-equivalent staging environment.

**Prerequisites:** FR-BIL-017, FR-EDG-002A, FR-INT-005  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-EDG-029, TST-M6-FR-EDG-029

## Security and Data Protection

### FR-SEC-002B - Local-node IDOR defense

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-SEC-002`  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** The local node denies cross-tenant and sibling-outlet access for all four verbs against populated fixtures.

**Gate-local behavior:** The local node denies cross-tenant and sibling-outlet access for all four verbs against populated fixtures.

**Later behavior:** None beyond M5a for this clause.

**Prerequisites:** FR-EDG-001, FR-SEC-002A  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-SEC-002B

## Staff POS and Outlet UX

### FR-POS-008 - Offline indicator

**Priority:** P0  
**Owner:** Customer Experience  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** None  
**Required behavior:** Show locally saved, queued, synchronized, conflict and blocked states in plain language.

**Gate-local behavior:** All five synchronization states render in plain language on the staff surface during and after an outage.

**Later behavior:** None beyond M5a for this clause.

**Prerequisites:** FR-EDG-001, FR-INT-003  
**Journeys:** GJ-10  
**Acceptance tests:** TST-M5a-FR-POS-008

## Testing and Evidence

### FR-TST-008 - Offline tests

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M5a  
**Revalidated:** M5b  
**Required behavior:** Run customer, waiter, POS, KDS, billing, tip, payment, printing and reconnection journeys through a real cloud/outlet pair with internet loss and local Wi-Fi continuity.

**Gate-local behavior:** Staff-side outage journeys including billing, tip, payment, printing and reconnection run against a real cloud/outlet pair.

**Later behavior:** Customer local Wi-Fi continuity requires same-QR routing.

**Prerequisites:** FR-EDG-015A, FR-EDG-016  
**Journeys:** GJ-10, GJ-08  
**Acceptance tests:** TST-M5a-FR-TST-008, TST-M5b-FR-TST-008

# Gate M5b

## Deployment and Operations

### FR-OPS-017 - Per-outlet public hostname and certificate

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5b  
**Revalidated:** M6  
**Required behavior:** Use a managed per-outlet public hostname, split-horizon DNS and a public-CA DNS-01 certificate for cloud and local routing. Provision and rotate the per-outlet key securely. Raw local IP URLs, shared cross-outlet wildcard private keys, self-signed certificates and ignored warnings are prohibited.

**Gate-local behavior:** The managed per-outlet hostname, split DNS and public-CA certificate operate with secure per-outlet key provisioning and rotation, and none of the four prohibited patterns exists.

**Later behavior:** The operational rotation procedure runs against the production deployment.

**Prerequisites:** FR-EDG-022A  
**Journeys:** GJ-08  
**Acceptance tests:** TST-M5b-FR-OPS-017, TST-M6-FR-OPS-017

## Outlet Continuity and Edge

### FR-EDG-028 - Same-QR client resolution acceptance

**Priority:** P0  
**Owner:** Edge & Continuity  
**Lineage:** retained  
**Introduced:** M5b  
**Revalidated:** None  
**Required behavior:** Same-QR routing is accepted against real client behavior: a device joining outlet Wi-Fi while holding a cached public DNS answer reaches a correct and trusted endpoint within the documented TTL window; encrypted DNS (Android Private DNS, DNS-over-HTTPS) that bypasses outlet split DNS is detected and handled with a documented supported-network configuration and translated staff guidance; IPv4 and IPv6 answers are consistent so a dual-stack device cannot reach a stale or untrusted endpoint; and resolver-cache flush and TTL behavior during the cloud-to-LAN transition is specified and tested. Every unsupported client configuration fails safe to a clear instruction, never to a certificate warning or a bypass prompt.

**Gate-local behavior:** Cached-answer, encrypted-DNS and dual-stack devices each reach a trusted endpoint or fail safe to translated guidance, never to a certificate warning or bypass prompt.

**Later behavior:** None beyond M5b for this clause.

**Prerequisites:** FR-EDG-022A, FR-EDG-021  
**Journeys:** GJ-08  
**Acceptance tests:** TST-M5b-FR-EDG-028

## Outlet Edge and Synchronization

### FR-EDG-003 - Local domain authority

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5b  
**Revalidated:** M6  
**Required behavior:** The outlet node is the authoritative writer for active dine-in table sessions, orders, fulfillment, service requests, checks, payments, tips and cash shifts for its outlet. Cloud access forwards commands to that authority while connected.

**Gate-local behavior:** When the bidirectional lease permits local authority, the outlet node is the sole authoritative writer for active dine-in operations and connected cloud access forwards commands to that outlet authority.

**Later behavior:** Repeat the authority and forwarding proof in staging with production-equivalent fencing and monitoring.

**Prerequisites:** FR-EDG-021, FR-EDG-018  
**Journeys:** GJ-09  
**Acceptance tests:** TST-M5b-FR-EDG-003, TST-M6-FR-EDG-003

### FR-EDG-004B - Same-QR outage access

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** split_successor from `FR-EDG-004`  
**Introduced:** M5b  
**Revalidated:** None  
**Required behavior:** The same public table QR resolves to the node with a trusted certificate and no browser warning during outage.

**Gate-local behavior:** The same public table QR resolves to the node with a trusted certificate and no browser warning during outage.

**Later behavior:** None beyond M5b for this clause.

**Prerequisites:** FR-EDG-004A, FR-EDG-022A  
**Journeys:** GJ-08  
**Acceptance tests:** TST-M5b-FR-EDG-004B

### FR-EDG-015B - Customer same-QR outage continuity

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** split_successor from `FR-EDG-015`  
**Introduced:** M5b  
**Revalidated:** None  
**Required behavior:** A customer on outlet Wi-Fi orders through the same QR while the internet is down.

**Gate-local behavior:** A customer on outlet Wi-Fi orders through the same QR while the internet is down.

**Later behavior:** None beyond M5b for this clause.

**Prerequisites:** FR-EDG-015A, FR-EDG-022A, FR-EDG-025  
**Journeys:** GJ-08  
**Acceptance tests:** TST-M5b-FR-EDG-015B

### FR-EDG-021 - Customer local Wi-Fi continuity

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5b  
**Revalidated:** None  
**Required behavior:** During internet outage, a customer connected to the restaurant Wi-Fi can use the same QR journey to browse the cached menu, order, call staff, request the bill, tip and settle using available local methods.

**Gate-local behavior:** A customer on outlet Wi-Fi completes the full same-QR journey during outage: cached menu, order, staff call, bill request, tip and settlement by an available local method.

**Later behavior:** None beyond M5b for this clause.

**Prerequisites:** FR-EDG-022A, FR-EDG-025  
**Journeys:** GJ-08  
**Acceptance tests:** TST-M5b-FR-EDG-021

### FR-EDG-022A - Same-QR routing and node-key custody

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** split_successor from `FR-EDG-022`  
**Introduced:** M5b  
**Revalidated:** M6  
**Required behavior:** The same opaque table QR uses a per-outlet public hostname. Public DNS routes to cloud and outlet split-horizon DNS routes to the LAN node. The node generates and retains its private key, submits only a CSR, and receives the public-CA certificate chain from central DNS-01 automation; the private key is never exported.

**Gate-local behavior:** The same QR reaches a trusted cloud endpoint normally and a trusted LAN endpoint during supported outlet routing; certificate issuance completes from a node-generated CSR with no private-key export.

**Later behavior:** Production issuance and rotation evidence is rechecked during staging.

**Prerequisites:** FR-EDG-004A, FR-TAB-001  
**Journeys:** GJ-08  
**Acceptance tests:** TST-M5b-FR-EDG-022A, TST-M6-FR-EDG-022A

### FR-EDG-022B - Certificate lifecycle

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** split_successor from `FR-EDG-022`  
**Introduced:** M5b  
**Revalidated:** M6  
**Required behavior:** The per-outlet certificate lifecycle begins renewal 30 days before expiry, uses bounded retry, alerts at 14 and 7 days, records LAN-served fingerprint and expiry before completion, supports compromise revocation and re-issuance, and fails safely to the cloud-served journey with translated guidance.

**Gate-local behavior:** Exercise renewal, retry, alert, installation verification, revocation and failed-renewal fallback without a browser warning.

**Later behavior:** Repeat against the production-equivalent outlet environment.

**Prerequisites:** FR-EDG-022A  
**Journeys:** GJ-08, GJ-12  
**Acceptance tests:** TST-M5b-FR-EDG-022B, TST-M6-FR-EDG-022B

### FR-EDG-022C - TLS and URL prohibitions

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** split_successor from `FR-EDG-022`  
**Introduced:** M5b  
**Revalidated:** M6  
**Required behavior:** Shared cross-outlet wildcard private keys, raw local-IP customer URLs, self-signed certificate warnings and manual browser bypass are prohibited.

**Gate-local behavior:** Scanner and client tests prove that no prohibited key, URL, certificate or bypass path exists.

**Later behavior:** Re-scan the final production artifacts.

**Prerequisites:** FR-EDG-022A  
**Journeys:** GJ-08, GJ-12  
**Acceptance tests:** TST-M5b-FR-EDG-022C, TST-M6-FR-EDG-022C

### FR-EDG-023 - Bidirectional cloud reachability lease

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5b  
**Revalidated:** None  
**Required behavior:** Use a signed bidirectional challenge/acknowledgement every 5 seconds by default. A valid proof confirms cloud-to-node reachability, node-to-cloud reachability, the same monotonic authority sequence, protocol compatibility and cursor posture. Mark degraded after 10 seconds and expire the cloud forwarding lease after 20 seconds. Resume only after compatibility checks and three consecutive valid proofs.

**Gate-local behavior:** Signed bidirectional proofs run at 5s, degrade at 10s and expire the forwarding lease at 20s; a one-way failure in either direction also expires it; recovery requires three consecutive valid proofs.

**Later behavior:** None beyond M5b for this clause.

**Prerequisites:** FR-EDG-003, FR-EDG-012  
**Journeys:** GJ-09  
**Acceptance tests:** TST-M5b-FR-EDG-023

### FR-EDG-024 - Monotonic authority replacement and fencing

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5b  
**Revalidated:** None  
**Required behavior:** Emergency replacement uses the next durable monotonic signed authority sequence. Before a standby node or standby outlet node becomes writable, record step-up, independent approval, old-node power-off or router/firewall/switch-port/VLAN isolation, and an automated LAN-unreachability probe. Every writer persists the highest accepted sequence and rejects rollback. Direct LAN writes to the old node must fail; stale events are quarantined.

**Gate-local behavior:** A replacement becomes writable only after recorded fence evidence and independent approval; the old node rejects direct LAN writes and its stale events quarantine; rollback is refused.

**Later behavior:** None beyond M5b for this clause.

**Prerequisites:** FR-EDG-023, FR-AUTH-006  
**Journeys:** GJ-09  
**Acceptance tests:** TST-M5b-FR-EDG-024

### FR-EDG-026 - Session continuity

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M5b  
**Revalidated:** None  
**Required behavior:** An active table session and its participant tokens remain valid when a customer moves from cloud access to local Wi-Fi, without duplicate orders or loss of cart ownership.

**Gate-local behavior:** A session started on cellular continues on outlet Wi-Fi with participant tokens intact, no duplicate order and cart ownership preserved.

**Later behavior:** None beyond M5b for this clause.

**Prerequisites:** FR-EDG-021, FR-TAB-004  
**Journeys:** GJ-08  
**Acceptance tests:** TST-M5b-FR-EDG-026

# Gate M6

## Configuration and Setup

### FR-CFG-007B - No production reset capability

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** split_successor from `FR-CFG-007`  
**Introduced:** M6  
**Revalidated:** None  
**Required behavior:** Scan of the built production image and database proves no demo-reset route, job or script is present.

**Gate-local behavior:** Scan of the built production image and database proves no demo-reset route, job or script is present.

**Later behavior:** None; terminal claim.

**Prerequisites:** FR-OPS-001  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M6-FR-CFG-007B

## Deployment and Operations

### FR-OPS-006 - Backup schedule

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M6  
**Revalidated:** None  
**Required behavior:** Back up cloud and outlet databases, configuration and required files on a documented schedule using tools present inside the production artifact.

**Gate-local behavior:** Scheduled backups of cloud and outlet databases run using only tools present inside the built production artifact.

**Later behavior:** None beyond M6.

**Prerequisites:** FR-OPS-019, FR-EDG-001  
**Journeys:** GJ-11  
**Acceptance tests:** TST-M6-FR-OPS-006

### FR-OPS-007 - Restore drill

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M6  
**Revalidated:** None  
**Required behavior:** Restore into clean cloud and outlet environments, start with least-privileged production roles, run the Phase 1 golden journeys and measure recovery time.

**Gate-local behavior:** A destructive restore into clean cloud and outlet environments starts under production roles, passes the golden journeys and records recovery time.

**Later behavior:** None beyond M6.

**Prerequisites:** FR-OPS-006, FR-OPS-020  
**Journeys:** GJ-11  
**Acceptance tests:** TST-M6-FR-OPS-007

### FR-OPS-011 - Runbooks

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M6  
**Revalidated:** None  
**Required behavior:** Provide operator runbooks for installation, menu publish, table QR issue, printer setup, outage, reconnection, backup, restore, update, incident and pilot cutover.

**Gate-local behavior:** All eleven runbooks exist and each has been executed at least once against the real system.

**Later behavior:** None beyond M6.

**Prerequisites:** FR-OPS-007, FR-OPS-015  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M6-FR-OPS-011

### FR-OPS-012 - Monitoring ownership

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M6  
**Revalidated:** None  
**Required behavior:** Assign alert severity, owner, acknowledgement and escalation; avoid unowned dashboards.

**Gate-local behavior:** Every alert and dashboard has a named owner, severity, acknowledgement path and escalation.

**Later behavior:** None beyond M6.

**Prerequisites:** FR-NOT-011, FR-OPS-004  
**Journeys:** None  
**Acceptance tests:** TST-M6-FR-OPS-012

### FR-OPS-015 - Go-live cutover

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M6  
**Revalidated:** None  
**Required behavior:** Use a controlled go-live checklist, pilot tenant/outlet, rollback plan, data owner and named operator. No direct production cutover from an unaudited branch.

**Gate-local behavior:** Go-live runs from an audited branch with checklist, pilot outlet, rollback plan, data owner and named operator recorded.

**Later behavior:** None beyond M6.

**Prerequisites:** FR-GOV-004, FR-TST-019  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M6-FR-OPS-015

### FR-OPS-016 - Disaster recovery

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M6  
**Revalidated:** None  
**Required behavior:** Define cloud and outlet recovery objectives, replacement-node procedure and reconciliation after prolonged outage.

**Gate-local behavior:** Recovery objectives, the replacement-node procedure and prolonged-outage reconciliation are defined and exercised.

**Later behavior:** None beyond M6.

**Prerequisites:** FR-EDG-024, FR-OPS-007  
**Journeys:** GJ-11  
**Acceptance tests:** TST-M6-FR-OPS-016

### FR-OPS-019 - Built artifact completeness

**Priority:** P0  
**Owner:** Edge & Operations  
**Lineage:** retained  
**Introduced:** M6  
**Revalidated:** None  
**Required behavior:** Every advertised runtime job, script, database client and configuration file exists and executes inside the built production image without host development mounts.

**Gate-local behavior:** Every advertised job, script, database client and config file executes inside the image with no host mount.

**Later behavior:** None beyond M6.

**Prerequisites:** FR-OPS-005, FR-OPS-008  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M6-FR-OPS-019

## Security and Data Protection

### FR-SEC-019 - Backups

**Priority:** P0  
**Owner:** Platform & Security  
**Lineage:** retained  
**Introduced:** M6  
**Revalidated:** None  
**Required behavior:** Encrypt backups, verify them, retain off-site copies and restore through the exact production roles and built artifacts.

**Gate-local behavior:** Encrypted backup is taken, verified, stored off-site and destructively restored using only built artifacts and production roles.

**Later behavior:** None; terminal claim.

**Prerequisites:** FR-OPS-001, FR-DAT-017  
**Journeys:** GJ-11  
**Acceptance tests:** TST-M6-FR-SEC-019

## Testing and Evidence

### FR-TST-009 - Backup restore

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M6  
**Revalidated:** None  
**Required behavior:** Back up and destructively restore clean cloud and outlet environments, then run production-role table/order/KDS/bill/tip/payment/sync journeys.

**Gate-local behavior:** A destructive restore is followed by successful production-role journeys across all named domains.

**Later behavior:** None beyond M6.

**Prerequisites:** FR-OPS-007  
**Journeys:** GJ-11  
**Acceptance tests:** TST-M6-FR-TST-009

### FR-TST-010 - Performance

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M6  
**Revalidated:** None  
**Required behavior:** Load test peak ordering/KDS/realtime, menu search, reporting and integration bursts with recorded thresholds.

**Gate-local behavior:** Load tests record thresholds across ordering, KDS realtime, menu search, reporting and integration bursts.

**Later behavior:** None beyond M6.

**Prerequisites:** FR-UX-012, FR-RPT-015  
**Journeys:** GJ-12  
**Acceptance tests:** TST-M6-FR-TST-010

### FR-TST-018 - Built production-path tests

**Priority:** P0  
**Owner:** Quality Engineering  
**Lineage:** retained  
**Introduced:** M6  
**Revalidated:** None  
**Required behavior:** Security, readiness, backup, restore, local continuity and route-surface tests execute against built production artifacts and real production roles, not source-only substitutes.

**Gate-local behavior:** All six named test families execute against built production artifacts under real production roles.

**Later behavior:** None beyond M6.

**Prerequisites:** FR-OPS-019, FR-OPS-020  
**Journeys:** GJ-11, GJ-12  
**Acceptance tests:** TST-M6-FR-TST-018
