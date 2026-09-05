# M4 review — findings the reviewer must be told

**Generated. Do not edit.** `python3 tools/generate_review_findings.py --out planning/M4_REVIEW_FINDINGS.md`, and CI fails the build when the committed copy differs from a fresh generation.

This document exists because a finding a reviewer has to go looking for is a finding they may not find. Everything below comes from `planning/requirement_coverage.json`, which the FR-GOV-004 audit validates on every run.

## The reviewer is free to disagree with all of it

Each finding below carries a **classification** and a **completing gate**, and both are the builder's judgement, made under the deadline of a closing gate. That is precisely the condition in which *"not really a security gap"* is an easy sentence to write. **The review may challenge a classification as readily as a fix.** A gap wrongly called schedulable is worse than one honestly called urgent, and the reasoning for every one is printed here so it can be argued with rather than taken on trust.

Completing gates are not chosen. Each is the next gate at which the pinned package itself revalidates the requirement, read from its own `revalidated_at`, or the final gate when the package names none. Where this slice delivers the missing half the gate is overridden to the slice that delivers it, and every such override is visible in the tables below.

## 5 absent requirements in money, security or authority

These are the findings that change what this review is about. **Absent** means the behaviour genuinely does not exist — not that it exists uncited. Each row says whether it could be built today, because otherwise *"not due yet"* reads as *"not possible yet"*, which is a different and more forgiving claim.

| Requirement | Introduced | Category | Closes at | Buildable now |
|---|---|---|---|---|
| `FR-SEC-008` Encryption | M1 | security | **M5b** | no |
| `FR-SEC-010A` Customer PII classification | M1 | security | **M6** | **yes** |
| `FR-SEC-012` File security | M1 | security | **M6** | **yes** |
| `FR-SEC-018` Data deletion | M1 | security | **M6** | **yes** |
| `FR-SEC-020` Incident response | M1 | security | **M6** | no |

### FR-SEC-008 — Encryption

Neither half exists in this repository and neither can. TLS in transit is a property of the deployment in front of the process, and encryption at rest is the provider's or the platform's; no migration, route or suite can deliver either. No high-risk field is encrypted at the column level. The package places the revalidation at M5b and M6 — per-outlet public-trust TLS on the local node, and backup encryption proved with backup and restore — so this is honestly not this gate's to close. Recorded as a security absence rather than a governance one because the capability, not its citation, is what is missing.

**Buildable now:** NOT BUILDABLE HERE. TLS terminates in front of the process and encryption at rest belongs to the provider or the platform; no migration, route or suite can deliver either. Column-level encryption of a selected high-risk field is buildable, and is the one part of this clause that is.

**This entry closes when:** Per-outlet public-trust TLS terminates on the outlet node, and backup encryption is proved by a restore rather than asserted.

*The package revalidates this at M5b, M6.*

### FR-SEC-010A — Customer PII classification

There is NO data classification in this build. The word appears twice and neither is this: api/src/logging.ts classifies ERRORS, and 0012 classifies a preparation station. No taxonomy marks a column as customer contact, complaint or PII, and so nothing restricts those fields by role on that basis — what protects them today is the tenant and outlet predicate every table carries, which is a different control answering a different question. Customer contact data exists from M2's guest sessions and M3-C's service requests, so the subject is real.

**Buildable now:** BUILDABLE NOW. A classification taxonomy and a role predicate over the columns holding customer contact data need nothing that does not already exist.

**This entry closes when:** Each column holding customer contact or complaint data is marked by a classification, and a role without the entitlement cannot read it — proved by a planted read that must be refused.

*The package revalidates this at M3.*

### FR-SEC-012 — File security

The convenient reading of this one is wrong, so here is the whole of it. The package expected the first real private-file class at M4 through the Telebirr/CBE payment proof; M4-B made that proof a WRITTEN ATTESTATION — payments.proof_confirmation stores what_the_verifier_saw as text and no file — so the subject the package anticipated at this gate never materialised. But menu.image has carried is_private and storage_key since M2, and that IS a private-file class: nothing validates, scans, hashes, authorizes, signs or expires anything. The absence is real and older than M4. What makes it latent rather than live is that no surface uploads or serves those files — the rows point at keys nothing reads — so there is no exposure today. THIS BECOMES URGENT THE MOMENT A SERVING PATH IS ADDED, and a reviewer should challenge the classification on exactly that ground.

**Buildable now:** BUILDABLE NOW in part: validation and hashing of the image rows that exist need nothing deployed. Signing and expiry need a serving path, and there is none — which is also why nothing is exposed today.

**This entry closes when:** A private file is served only through a signed, expiring, authorized URL, and its bytes are validated and hashed on the way in — proved against menu.image, the private file class that already exists.

*The package revalidates this at M4.*

### FR-SEC-018 — Data deletion

Half built, and the missing half is named precisely. Anonymization exists: 0007 added anonymize to config.retention_action for exactly this reason, and M1-C's retention sweep applies it. LEGAL HOLD DOES NOT EXIST — no flag, no table, no predicate — so nothing can suspend a retention action for a record under hold. The package revalidates at M4 for ledger-protected financial records and M4-C delivers that half: retention must refuse to target the financial ledgers, exactly as retention_policy_never_targets_audit already refuses the audit tables. The entry stays open past this slice because the legal-hold clause remains, and closing it at M4-C would be a false closure.

**Buildable now:** BUILDABLE NOW. A legal hold is a flag and a predicate the retention sweep already has the shape for. The M4 half is built by this slice.

**This entry closes when:** A legal hold suspends every retention action against the records it names, proved by planting a hold and requiring the sweep to leave them alone. The M4 half — retention refusing to target the financial ledgers — is delivered at M4-C and is not this entry's closing test.

*The package revalidates this at M4, M6.*

### FR-SEC-020 — Incident response

No runbook exists in planning/ or anywhere else, and the clause asks for more than a document: detection, containment, credential rotation, tenant notification and evidence preservation, executable against real capability. Credential rotation and revocation are built and proved; detection depends on production monitoring and tenant notification on a deployed multi-tenant artifact, which is why the package revalidates this at M6. Recorded as a security absence, and one a reviewer should not let M4's review absorb quietly just because its gate is later.

**Buildable now:** Not buildable here beyond a document: detection needs production monitoring and tenant notification needs a deployed multi-tenant artifact. Credential rotation and containment already exist and are proved.

**This entry closes when:** The runbook exists AND its rotation, containment and evidence-preservation steps are executed against the deployed artifact rather than described.

*The package revalidates this at M6.*

## 15 further absences, outside money, security and authority

| Requirement | Introduced | Category | Closes at | Buildable now | What is absent |
|---|---|---|---|---|---|
| `FR-MNU-002B` No customer-segment targeting | M0R | governance | M6 | no | THE SCANNER CANNOT PROVE WHAT THIS REQUIREMENT CREDITS IT WITH. |
| `FR-TST-013` Golden journeys | M0R | governance | M6 | yes | The journeys exist, run in CI on both platforms and fail the build: five golden journeys, 61 steps. |
| `FR-TST-019` Independent milestone audit | M0R | governance | M6 | no | No audit branch exists in this repository, and no immutable command set, evidence bundle or merge decision against an exact commit is stored for any gate. |
| `FR-CFG-006` Branding | M1 | product | M5a | yes | Branding is configurable — config.configuration_version carries a branding category and the API resolves it per tenant rather than from build-time constants — but the clause names receipt and footer text specifically, and the package places its revalidation at M4 because receipt text is only rendered on a real receipt. |
| `FR-CFG-007A` Non-production demo fixtures | M1 | product | M6 | yes | No demo fixture is marked as one, and no reset capability exists to be restricted to non-production. |
| `FR-COM-002` White labeling | M1 | product | M6 | yes | Per-tenant brand and template resolution exists and is consumed from configuration. |
| `FR-COM-009` Version support | M1 | product | M6 | yes | No application, schema, edge or connector version is tracked PER TENANT OR DEPLOYMENT. |
| `FR-TEN-009A` Phase 1 system-of-record registry | M1 | product | M6 | yes | No system-of-record registry exists — no table states, per tenant or legal entity, which system is authoritative for which Phase 1 concern. |
| `FR-TST-003` API tests | M1 | product | M6 | yes | Most of the clause is delivered — validation, auth, idempotency, concurrency and error contracts are all exercised against the built service, and M4-B proved idempotency by key on payment intents. |
| `FR-TST-004A` Phase 1 adapter contract tests | M1 | product | M6 | no | Two ports, and only one exists. |
| `FR-TST-012` Migration and cross-platform upgrade | M1 | product | M6 | no | The fresh half is proved every run: twenty-five migrations applied to a database built from empty, checksum-locked, with M1-A planting an edit and requiring MIGRATION_CHECKSUM_MISMATCH, and line endings asserted pure LF across 42 checksum-locked files so the hashes are platform-independent. |
| `FR-UX-003` Back office desktop first | M1 | product | M6 | yes | There is no back-office surface at all. |
| `FR-UX-007` Loading/offline | M2 | product | M5a | no | Three of the seven states exist and are distinguishable on the customer surface — loading, stale and failed, which is the clause's own gate-local behaviour at M2. |
| `FR-UX-020` Consistent design system | M2 | product | M6 | yes | No shared component or token system exists. |
| `FR-POS-009` Accessibility mode | M3 | product | M6 | yes | Accessibility preferences do not exist on the staff surfaces. |

### Constraint or preference: the 5 entries re-pointed at M4-C

Each was moved off a gate that has already landed. None was built. The question a reviewer needs answered is not whether the gap is real — it is whether the reason for deferring it is a constraint or a preference.

#### FR-CFG-006 — Branding → M5a

BUILDABLE NOW, AND NOT BUILT. An earlier draft of this entry said 'built by this slice', which was false: no branding is rendered onto a receipt. Tenant branding configuration exists and the receipt composer exists; nothing joins them.

**What would have to be true:** docs.compose_document() would read the tenant's branding category from config.configuration_version and emit it as header and footer wording, and a control would prove one tenant's text appears on its own receipt and never on another's. Nothing blocks that today. Re-pointing this to M5a is a PREFERENCE, not a constraint — M5a is simply where the outlet node makes branding per-outlet.

#### FR-COM-002 — White labeling → M6

BUILDABLE IN PART, AND NOT BUILT. The claim that this slice built it was false. The receipt is the first template this project renders, so the template half has a place to live; the surface half has nowhere to be configured from.

**What would have to be true:** A per-tenant template resolved from configuration and rendered by docs.compose_document() is buildable now — that half is a PREFERENCE. The rest of the clause needs a back-office surface on which a tenant's branding can be set and a customer surface that reads it, and no back-office surface exists: that half is a CONSTRAINT.

#### FR-POS-009 — Accessibility mode → M6

BUILDABLE NOW, AND NOT BUILT. The claim that this slice built it was false. No accessibility preference exists on any staff surface; M2-C proved the CUSTOMER surface against measured layout and neither the waiter nor the station surface has anything equivalent.

**What would have to be true:** A per-user accessibility preference, the waiter and station bundles honouring it, and M2-C's measuring instrument — target sizes, contrast, text scaling, read out of a real browser — pointed at those two surfaces. The instrument already exists and is the expensive half. This is a PREFERENCE.

#### FR-TEN-009A — Phase 1 system-of-record registry → M6

BUILDABLE NOW, AND NOT BUILT. The claim that this slice built it was false. No table states which system is authoritative for which Phase 1 concern, per tenant or legal entity.

**What would have to be true:** A registry table keyed by tenant and concern, a constraint that every fiscal document names the system of record it was issued under, and M4-C's fiscal port reading it rather than assuming. All three are ordinary schema work with nothing missing. This is a PREFERENCE, and a weak one: the fiscal port is the thing that needs it.

#### FR-TST-003 — API tests → M6

PARTLY UNBUILDABLE, AND HONESTLY SO. Validation, authentication, idempotency, concurrency and error contracts are all exercised against the built service. The remaining half is pagination, and NO ROUTE IN THE SERVICE PAGINATES — there is no limit, offset or cursor parameter anywhere in api/src/routes.

**What would have to be true:** A route would have to paginate before a test could prove it does. That makes this a genuine CONSTRAINT rather than a preference: the missing test is missing because the behaviour it would test does not exist, and building the behaviour is a feature this brief does not authorise. The listing routes that would need it — checks, terminals, notifications, the service queue — are named here so the gate that adds paging knows what it owes.

## 51 requirements delivered with nothing naming them

**Uncited** means the behaviour exists, works, and no recorded output names the requirement — so the audit cannot see a proof that is genuinely there. This is a governance gap, not a product one, and the checker refuses to let one be filed as a money, security or authority absence: conflating the two inflates the urgent list until nobody reads it. Each closes the same way, by a check or a CI step citing the requirement so the audit can grade it.

| Requirement | Introduced | Closes at |
|---|---|---|
| `FR-TST-017` Anti-false-green and frozen negative controls | M0 | M4-C |
| `FR-EDG-002B` No deferred local modules | M0R | M5a |
| `FR-FUL-016B` No inventory or recipe-consumption posting | M0R | M6 |
| `FR-GOV-001A` Empty repository conformance | M0R | M6 |
| `FR-GOV-002` No dormant future modules | M0R | M5a |
| `FR-GOV-003` Controlled code reuse | M0R | M6 |
| `FR-GOV-005` Traceability authority | M0R | M4-C |
| `FR-ORD-001C` No pickup or delivery order domain | M0R | M6 |
| `FR-ORD-012B` No stock or accounting reversal | M0R | M6 |
| `FR-ORD-016B` No delivery, inventory or accounting events | M0R | M6 |
| `FR-ORD-019B` No campaign or CRM correlation | M0R | M6 |
| `FR-PAY-010B` No accounting journal posting | M0R | M6 |
| `FR-POS-003C` No pickup or delivery ordering | M0R | M6 |
| `FR-POS-010B` No pickup or delivery search | M0R | M6 |
| `FR-RCP-008B` No operational recipe module | M0R | M6 |
| `FR-SEC-010B` No employee or payroll data | M0R | M6 |
| `FR-TEN-009B` No later-domain registry entries | M0R | M6 |
| `FR-TST-004B` No supplier or courier contract tests | M0R | M6 |
| `FR-TST-005B` No later-channel or supplier journeys | M0R | M6 |
| `FR-TST-007B` No stock, supplier or delivery races | M0R | M6 |
| `FR-TST-014` Traceability | M0R | M4-C |
| `FR-UX-001B` No pickup or delivery UX | M0R | M6 |
| `FR-AUTH-005` Quick PIN | M1 | M6 |
| `FR-AUTH-006` Step-up authentication | M1 | M6 |
| `FR-AUTH-009` Service accounts | M1 | M5a |
| `FR-CFG-001A` Organizational setup | M1 | M6 |
| `FR-COM-007` Configuration templates | M1 | M6 |
| `FR-GOV-001B` Database and migration start | M1 | M6 |
| `FR-OPS-001` Environment validation | M1 | M5a |
| `FR-OPS-002` Health endpoints | M1 | M5a |
| `FR-OPS-003` Structured logs | M1 | M5a |
| `FR-OPS-005` Background jobs | M1 | M5a |
| `FR-OPS-008` Deployment automation | M1 | M5a |
| `FR-OPS-020` Production-role readiness | M1 | M5a |
| `FR-SEC-005` CSRF/session | M1 | M6 |
| `FR-SEC-006` Rate limiting | M1 | M6 |
| `FR-SEC-011` Payment boundary | M1 | M6 |
| `FR-SEC-013` MFA | M1 | M6 |
| `FR-SEC-014` Device security | M1 | M5a |
| `FR-TEN-005` Second tenant | M1 | M6 |
| `FR-TST-001` Unit tests | M1 | M6 |
| `FR-TST-002` Database integration | M1 | M5a |
| `FR-TST-006` Security tests | M1 | M5a |
| `FR-TST-015` Defect gates | M1 | M6 |
| `FR-I18N-011` Exact launch locale set | M2 | M6 |
| `FR-MNU-004` Item content | M2 | M6 |
| `FR-MNU-005` Variants | M2 | M6 |
| `FR-MNU-006` Modifier sets | M2 | M6 |
| `FR-RCP-008A` Customer ingredient and allergen content | M2 | M6 |
| `FR-SAF-007` Publication block | M2 | M6 |
| `FR-FUL-006` Course firing | M3 | M6 |

## How strongly the delivered requirements are proved

The audit grades its own evidence rather than implying a strength it did not measure. A reviewer should read the middle row carefully: **it verifies that the citation runs, and does not establish that the check has ever been shown able to fail.**

| Grade | What it establishes |
|---|---|
| `proved-red` | The citation sits on a negative control that the run showed red with a real defect planted, then green after revert. The assertion has been demonstrated capable of failing. |
| `ran` | The citation sits on a check that executed and reported. **Verifies the citation runs. Does not establish it can fail.** |
| `ci-step` | The citation sits in a workflow step, which fails the build on a non-zero exit. Can fail; cannot show a planted defect. |

Gates that have landed: M0, M0R, M1, M2, M3, M4. The package carries 336 active requirements and 288 of them belong to a landed gate.


## 25 routes the service exposes that nothing has ever called

**This is a finding in its own right, not a footnote.** GJ-01A's lesson was that `ordering.preview_cart()` and `ordering.submit_order()` were both proved against the database while no route called either and no button reached one: every unit check passed and the feature was unreachable. M4-A shipped its billing routes the same way. The first HTTP call ever made to `POST /s/v1/checks` — made while repairing the journeys, after the slice had closed — failed on two production defects at once, because nothing had ever called it.

Of 95 addressable routes, 70 are called by some suite, journey or surface and **25 are called by nothing**. A route with no caller is not necessarily broken. It is unproved, which is the condition both of those defects were hiding in.

Derived by `tools/uncalled_routes.py` on every generation, so this list cannot go stale the way a typed one would.

| Route file | Never called |
|---|---|
| `billing.ts` | `POST /s/v1/bills/:billId/corrections`<br>`POST /s/v1/bills/:billId/dispositions`<br>`POST /s/v1/bills/:billId/finalize`<br>`POST /s/v1/checks/merge` |
| `customer.ts` | `POST /c/v1/allergy-concerns` |
| `documents.ts` | `GET /s/v1/documents/preview`<br>`GET /s/v1/fiscal/reconciliation`<br>`GET /s/v1/printers`<br>`POST /s/v1/printers`<br>`POST /s/v1/printers/:printerId/test`<br>`POST /s/v1/receipts/:receiptId/prints`<br>`POST /s/v1/receipts/:receiptId/renders` |
| `payments.ts` | `GET /s/v1/cash/shifts/:shiftId/reconciliation`<br>`GET /s/v1/payments/:paymentId/allocations` |
| `reports.ts` | `GET /s/v1/reports/catalog`<br>`GET /s/v1/reports/metrics`<br>`GET /s/v1/reports/sales`<br>`GET /s/v1/reports/shifts/:shiftId/snapshot`<br>`POST /s/v1/reports/shifts/:shiftId/recomputations` |
| `service.ts` | `GET /s/v1/service/queue` |
| `staff.ts` | `GET /s/v1/fast-picks`<br>`GET /s/v1/terminals`<br>`POST /s/v1/handovers/:handoverId/acknowledge`<br>`POST /s/v1/terminals`<br>`POST /s/v1/terminals/:deviceId/revoke` |

## The KDS cannot be operated through the service

**Its own finding, and it belongs to M3-B rather than to this slice.** M3-B built the ticket state machine, the station queues and the expo view, and its suite proves all of it against the database. Not one of its writers can be invoked through the running service.

Of the 13 operator-callable writers in `fulfillment`, **13 are reachable by no route** and none is.

`fulfillment.transition_ticket()` is the single writer that moves a ticket through every one of its eleven states — queued, acknowledged, held, preparing, partially_completed, ready, collected, completed, rework, cancelled, exception — and it has no route. So **acknowledge, hold, fire, mark ready, complete, recall and transfer are all unreachable**, along with line-level progress, serving, waste, priority, allergy acknowledgement, release to the stations and release to service.

`api/src/routes/station.ts` exposes three routes and all three are `GET`: the station queue, one ticket, and the expo view. `station/src` issues no write of any kind. **A cook can read the board and change nothing on it.**

| `fulfillment` writer | Reachable through a route |
|---|---|
| `fulfillment.acknowledge_allergy` | **no** |
| `fulfillment.apply_order_amendment` | **no** |
| `fulfillment.emit_ready_notice` | **no** |
| `fulfillment.escalate_uncollected` | **no** |
| `fulfillment.recall_ticket` | **no** |
| `fulfillment.record_serve` | **no** |
| `fulfillment.record_unit_progress` | **no** |
| `fulfillment.record_waste` | **no** |
| `fulfillment.release_order` | **no** |
| `fulfillment.release_to_service` | **no** |
| `fulfillment.set_priority` | **no** |
| `fulfillment.transfer_ticket` | **no** |
| `fulfillment.transition_ticket` | **no** |

This is GJ-01A one layer below the defect that opened this repair. There, ten billing routes existed and nothing had called them; here the routes do not exist at all, so the KDS M3-B delivered could not function in production. It is recorded rather than fixed: the fix is M3-B's scope and a station write surface is a feature, not a repair.

## A requirement the pinned package itself cannot satisfy

**FR-MNU-002B — No customer-segment targeting.** THE SCANNER CANNOT PROVE WHAT THIS REQUIREMENT CREDITS IT WITH. The clause demands a scan for a customer-segment field, assignment rule or screen, and no term for it exists among the 63 in the package's forbidden_surface_rules.json — loyalty_crm_promotions carries loyalty, reward, loyalty points, crm, campaign, promotion and marketing campaign, and none of them matches the word this requirement is about. No such field exists in the build, so the property holds; nothing proves it, and nothing in the repository can, because the vocabulary is the pinned package's and the build may not edit it. The correct disposition is a package amendment through amendment_register.json, not a build change, which is why this is recorded as absent rather than uncited: the scanning behaviour genuinely does not exist.

**Closes when:** The package carries a customer-segment term, through amendment_register.json, and the fenced gate proves the scanner detects it by planting it.

No change to this repository can close that. It is recorded here because a package defect found by the build is the reviewer's to adjudicate, not the builder's to work around.

