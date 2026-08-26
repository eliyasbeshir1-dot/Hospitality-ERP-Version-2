# Non-Regression Rules

**96 canonical rules**

- Package: `Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9`
- Canonical source root: `cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96`
- Status: **Package M0 candidate - M0R and implementation are not authorized**

Every rule is identified and published. The machine-readable register remains authoritative.

## NR-001

Do not implement future modules as hidden routes, tables, workers or feature-flagged pages.

## NR-002

A clean phase boundary is physical as well as visual.

## NR-003

Build one vertical milestone at a time.

## NR-004

Do not clone the frozen repository.

## NR-005

Reused code is treated as third-party code and reviewed in isolation.

## NR-006

The local node contains only customer service and outlet execution.

## NR-007

Customer-visible ingredients are not operational recipes.

## NR-008

Bill, payment and tip are separate business records.

## NR-009

Missing tenant/outlet context must return zero rows and permit zero writes.

## NR-010

Use populated owner-side fixtures so zero-row tests cannot pass vacuously.

## NR-011

Test sibling outlets inside the same tenant, not only different tenants.

## NR-012

Test SELECT, INSERT, UPDATE and DELETE.

## NR-013

Policies must contain both `USING` and `WITH CHECK` where applicable.

## NR-014

Adding `outlet_id` later must automatically strengthen existing policies.

## NR-015

API, jobs, files, caches, reports and sync paths are part of the isolation boundary.

## NR-016

Production services reject owner, superuser, BYPASSRLS and maintenance database roles.

## NR-017

Do not use binary floating-point for money, percentages or quantity outcomes.

## NR-018

Accepted orders, issued bills, payments, tips and cash movements are immutable or reversal-based.

## NR-019

No tip is selected by default.

## NR-020

Bill allocation and tip allocation are separate.

## NR-021

A tip cannot hide an unpaid bill balance.

## NR-022

Refunds and reversals require purpose-specific step-up, permission, reason and audit.

## NR-023

Quick PIN cannot authorize sensitive financial actions.

## NR-024

Split bill participants may choose different tips.

## NR-025

A protocol document is not a deployable outlet service.

## NR-026

Test the real outlet node, worker, database, print agent and restart behavior.

## NR-027

Cloud must not accept new dine-in writes when it cannot reach the outlet authority.

## NR-028

Use an authority epoch/lease to prevent split brain.

## NR-029

Persist IDs, cursors, dependencies and queues durably.

## NR-030

A bad event must not block unrelated streams forever.

## NR-031

Retries must be idempotent.

## NR-032

Conflicts are explicit; silent last-write-wins is prohibited.

## NR-033

The same QR must work locally with valid TLS, not a raw IP and ignored warning.

## NR-034

Create the empty repository only after Package M0; create PostgreSQL and executable migration `0001` only in M1 after M0R approval or adjudication.

## NR-035

Never edit an applied migration.

## NR-036

Lock migration checksums.

## NR-037

Test clean build and supported upgrade.

## NR-038

Test historical/edge-case fixtures before declaring upgrade safety.

## NR-039

Use real PostgreSQL and exact production roles.

## NR-040

Cross-platform line endings and tool invocation are acceptance concerns.

## NR-041

A source-tree test does not prove the production container.

## NR-042

Production images contain every advertised script, helper and database client.

## NR-043

Containers run as non-root.

## NR-044

Required paths remain usable by the non-root runtime user.

## NR-045

Health/readiness uses least-privileged application roles.

## NR-046

Readiness is unhealthy when an advertised job cannot do real work.

## NR-047

Backup tests use the same binaries, roles and image as production.

## NR-048

Restore is destructive into a clean environment and runs post-restore business journeys.

## NR-049

Missing grants, scripts, policies or binaries must make the drill fail.

## NR-050

Build output is deterministic and independent of command order.

## NR-051

Zero discovered tests is failure.

## NR-052

Any skipped acceptance test is failure.

## NR-053

Empty, unsupported or unknown security-scan coverage is failure.

## NR-054

Every critical gate has a planted negative control.

## NR-055

Tests cannot rely on another test's artifact or environment mutation.

## NR-056

Clear `dist`, `.next`, generated output and test databases before canonical validation.

## NR-057

Ordinary Windows and Linux commands must work without CI-only PATH or `PG_BIN` injection.

## NR-058

Pin the exact commit audited.

## NR-059

Store commands, logs, evidence and verdict on an isolated audit branch.

## NR-060

Do not weaken assertions merely to make CI green.

## NR-061

When an inherited gate becomes logically invalid after a repair, replace it with a stronger audit-only control and prove both repaired and deliberately broken cases.

## NR-062

Compilation, page scaffolding and green unit tests are not completion.

## NR-063

Production-path evidence takes precedence over claims.

## NR-064

Every active requirement maps to code, tests and evidence.

## NR-065

Every deferred requirement is absent from the production artifact.

## NR-066

A milestone or repository gate cannot proceed while its P0/P1 defects remain unresolved or unadjudicated under Source of Truth Section 9.1.

## NR-067

Final merge requires an independent staging verdict plus either reviewer approval or documented founder adjudication under Source of Truth Section 9.1; founder adjudication is never represented as reviewer approval.

## NR-068

An adverse reviewer verdict pauses progression but does not create an unrecorded permanent veto; disputes follow written founder adjudication.

## NR-069

Every founder risk acceptance names the affected requirement or non-regression rule and is re-examined at the next milestone.

## NR-070

M5a and M5b have separate executable exit journeys, ownership registers and audit gates.

## NR-071

Same-QR local service uses a per-outlet public hostname and public-trust certificate; self-signed bypass is prohibited.

## NR-072

Cloud lease expiry blocks cloud writes but never revokes LAN authority; reachability must be proved bidirectionally.

## NR-073

Only cash, external-terminal recording and verified Telebirr/CBE Birr proof confirmation are live pilot payment paths until a provider API is contracted.

## NR-074

A simulator cannot be represented as a live payment result or printed as a real provider receipt.

## NR-075

Negative controls are enumerated, identical across narrative/YAML/workbook and frozen at Package M0, not improvised after implementation.

## NR-076

Every milestone journey uses only capabilities owned by that milestone and approved predecessors; M3 cannot require M4 settlement or receipt behavior.

## NR-077

Deferred loyalty, pickup, delivery, supplier, inventory, accounting and data-portability behavior cannot remain as active Phase 1 requirements, tests, screens or prompt obligations.

## NR-078

Package M0 occurs before repository creation; Repository Conformance M0R occurs after the empty repository plan and before any M1 application code.

## NR-079

Emergency authority replacement cannot become writable until documented old-node power-off or network isolation and an automated LAN-unreachability probe are recorded.

## NR-080

Authority sequence is durable, monotonic, signed and anti-rollback; every writer persists the highest accepted sequence.

## NR-081

Reachability is a signed bidirectional challenge/acknowledgement; failure of either direction expires the cloud forwarding lease.

## NR-082

The canonical Package M0 review register contains exactly 14 questions and every review response answers all 14.

## NR-083

Normative M5 ownership is generated from one source and must match requirements, journeys, screens, events, risks and negative controls.

## NR-084

No gate is closed using behavior owned by a later gate; every requirement declares its introducing gate, gate-local scope and revalidation gates.

## NR-085

Excluded-domain capability appears in Phase 1 only as a deferral statement or extension-contract documentation, never as an entity, field, enumeration value, route, screen, registry entry or positive test.

## NR-086

The forbidden-surface vocabulary is generated from the phase-boundary exclusion set and every excluded domain carries a planted negative control.

## NR-087

A per-outlet certificate renewal is complete only when installation evidence is verified from the LAN; failed renewal fails safe to the cloud journey, never to a browser warning or bypass prompt.

## NR-088

Same-QR acceptance includes cached-DNS, encrypted-DNS and dual-stack client conditions with a safe documented failure mode.

## NR-089

A replacement node becomes writable only through the explicit activation state after the superseded instance is fenced and blocked; at most one node instance per outlet is writable.

## NR-090

A reopened cash shift is never terminal and returns to closed through recount and approval or an audited maker-checker correction.

## NR-091

Source of Truth, YAML, workbooks and combined publications are generated from canonical structured records and must pass exact parity checks.

## NR-092

Every active requirement receives a human-semantic introducing-gate and revalidation-gate disposition.

## NR-093

A generic journal, campaign, roster, attendance, timekeeping or break-record obligation is a forbidden future-domain leak unless explicitly negated or historical.

## NR-094

GJ-02B is mandatory at M4 and reverse-linked to localization, bill, payment, tip, receipt, print and testing requirements.

## NR-095

The cloud is never a writable emergency dine-in authority in Phase 1; only a physically or network-fenced standby outlet node may replace authority.

## NR-096

Same-QR acceptance uses a 30-second DNS TTL and maximum 60-second cloud-to-LAN transition, with captive-portal and staff guidance for unsupported encrypted DNS.
