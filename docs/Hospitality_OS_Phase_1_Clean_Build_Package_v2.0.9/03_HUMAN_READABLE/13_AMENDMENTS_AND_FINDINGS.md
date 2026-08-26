# Amendments and Findings

- Package: `Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9`
- Canonical source root: `cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96`
- Status: **Package M0 candidate - M0R and implementation are not authorized**

## Amendments

### AMD-REC-001 - Founder Approved Requirement Amendment

**Source:** reconciliation  
**Affected:** FR-GOV-004, D-120

**Old value:** Do not begin a later milestone until the current gate has clean evidence and no unresolved P0/P1 defect. An adverse independent verdict pauses progression; disputes follow builder response, reviewer rebuttal and founder decision. Overrides remain recorded, name the affected requirement/rule and are re-examined at the next audit.

**New value:** Do not begin a later milestone while any P0 remains unresolved, or while any P1 affects product scope, security, money, authority, milestone executability, acceptance completeness or canonical correctness. A P1 limited to publication, projection, wording, identifier or validator coverage may proceed only through recorded founder adjudication when canonical behavior is correct, runtime behavior cannot change, the defect remains visible and repair is scheduled. An adverse independent verdict pauses progression until the builder response, reviewer rebuttal and founder decision are recorded. Overrides name the affected requirement or rule and are re-examined at the next audit.

**Change:** Old: Do not begin a later milestone until the current gate has clean evidence and no unresolved P0/P1 defect. An adverse independent verdict pauses progression; disputes follow builder response, reviewer rebuttal and founder decision. Overrides remain recorded, name the affected requirement/rule and are re-examined at the next audit.
New: Do not begin a later milestone while any P0 remains unresolved, or while any P1 affects product scope, security, money, authority, milestone executability, acceptance completeness or canonical correctness. A P1 limited to publication, projection, wording, identifier or validator coverage may proceed only through recorded founder adjudication when canonical behavior is correct, runtime behavior cannot change, the defect remains visible and repair is scheduled. An adverse independent verdict pauses progression until the builder response, reviewer rebuttal and founder decision are recorded. Overrides name the affected requirement or rule and are re-examined at the next audit.

**Reason:** Align the requirement with the approved stopping rule: substantive P1 remains blocking, bounded publication/projection debt may proceed only through recorded adjudication.

**Verification:** Exact wording is asserted by the standard-library validator.

**Residual risk:** None.

### AMD-REC-002 - Requirement Split

**Source:** reconciliation  
**Affected:** FR-CFG-001, FR-CFG-002, FR-CFG-005, FR-CFG-007, FR-DAT-008, FR-EDG-002, FR-EDG-004, FR-EDG-015, FR-EDG-022, FR-FUL-016, FR-GOV-001, FR-I18N-001, FR-MNU-002, FR-ORD-001, FR-ORD-007, FR-ORD-012, FR-ORD-016, FR-ORD-019, FR-PAY-010, FR-POS-003, FR-POS-010, FR-RCP-008, FR-SEC-002, FR-SEC-010, FR-SRV-007, FR-TAB-007, FR-TEN-002, FR-TEN-009, FR-TST-004, FR-TST-005, FR-TST-007, FR-UX-001

**Old value:** 32 original mixed-behavior requirements.

**New value:** 72 successor requirements with full original lineage.

**Change:** Old: 32 original mixed-behavior requirements.
New: 72 successor requirements with full original lineage.

**Reason:** Different introducing gates, evidence or positive/negative phase-boundary behavior.

**Verification:** Every original is mapped to all successors; active IDs are unique; no successor depends on a later gate.

**Residual risk:** Human semantic coverage remains subject to Codex audit.

### AMD-REC-003 - New Requirements

**Source:** reconciliation  
**Affected:** FR-BIL-017, FR-EDG-029, D-119

**Old value:** No requirement separated minimum M4 physical receipt printing from M5a print resilience.

**New value:** M4 minimum physical receipt path and M5a durable local print resilience are separate requirements.

**Change:** Old: No requirement separated minimum M4 physical receipt printing from M5a print resilience.
New: M4 minimum physical receipt path and M5a durable local print resilience are separate requirements.

**Reason:** Resolve the v2.0.4 P0 milestone dependency.

**Verification:** M4 journeys require real print; GJ-10 proves M5a recovery and deduplication.

**Residual risk:** Implementation audit required.

### AMD-REC-004 - Gate Reconciliation

**Source:** reconciliation  
**Affected:** FR-EDG-003

**Old value:** M5a local authority with M5b revalidation.

**New value:** M5b introduction with M6 revalidation.

**Change:** Old: M5a local authority with M5b revalidation.
New: M5b introduction with M6 revalidation.

**Reason:** Authoritative write ownership depends on the M5b lease and fencing model; M5a provides local execution only.

**Verification:** No M5a requirement depends on FR-EDG-003.

**Residual risk:** None.

### AMD-REC-005 - Gate Reconciliation

**Source:** reconciliation  
**Affected:** FR-RPT-001, FR-RPT-002, FR-RPT-003, FR-RPT-004, FR-RPT-005, FR-RPT-013, FR-RPT-015

**Old value:** M6 introduction.

**New value:** M4 introduction, with concrete M5a or M6 revalidation where required.

**Change:** Old: M6 introduction.
New: M4 introduction, with concrete M5a or M6 revalidation where required.

**Reason:** Operational reports are a Phase 1 product capability and become executable when M4 completes settlement data; M6 is hardening, not first implementation.

**Verification:** Report prerequisites exist by M4 and no later-gate prerequisite remains.

**Residual risk:** None.

### AMD-REC-006 - Security Contract Amendment

**Source:** reconciliation  
**Affected:** FR-EDG-022A, D-116

**Old value:** Per-outlet key generation and documented custody.

**New value:** Node-generated and retained private key, CSR-only submission, certificate-chain return and no private-key export.

**Change:** Old: Per-outlet key generation and documented custody.
New: Node-generated and retained private key, CSR-only submission, certificate-chain return and no private-key export.

**Reason:** Resolve the v2.0.4 key-custody ambiguity.

**Verification:** Exact phrases are asserted by the validator.

**Residual risk:** Implementation keystore selection remains open.

### AMD-REC-007 - Journey Amendment

**Source:** reconciliation  
**Affected:** GJ-01A, GJ-01B, GJ-02B, GJ-03B, GJ-06, GJ-07, GJ-10

**Old value:** Ambiguous M3 authority wording and incomplete M4/M5a print ownership.

**New value:** Cloud/current authority at M3; real physical print at M4; durable print recovery at M5a.

**Change:** Old: Ambiguous M3 authority wording and incomplete M4/M5a print ownership.
New: Cloud/current authority at M3; real physical print at M4; durable print recovery at M5a.

**Reason:** Align journeys to the reconciled milestone contracts.

**Verification:** Journey text is asserted by the validator.

**Residual risk:** None.

### AMD-008 - Journey and revalidation evidence alignment

**Source:** validator-build pre-freeze audit  
**Affected:** FR-SEC-002A, FR-TST-006, FR-AUTH-003, FR-MNU-012, FR-RPT-001, FR-RPT-004, FR-RPT-005

**Old value:** Not separately recorded.

**New value:** Added missing later-gate revalidation/test evidence where a linked journey occurs after introduction, and removed journey links whose milestone precedes the reporting requirement's introducing gate.

**Change:** Added missing later-gate revalidation/test evidence where a linked journey occurs after introduction, and removed journey links whose milestone precedes the reporting requirement's introducing gate.

**Reason:** A journey may prove a clause only at its introducing or an explicitly listed revalidation gate.

**Verification:** Validator rule JOURNEY_GATE_ALIGNMENT and workbook projection parity.

**Residual risk:** None.

### AMD-009 - Blind Mutation Round 2 validator and projection hardening

**Source:** Blind Mutation Pack Round 2  
**Affected:** canonical/reconciled_requirements.json, canonical/reconciled_decisions.json, Hospitality_OS_Reconciled_Register_v0.1.2.xlsx, validator/validate_hospitality_os.py

**Old value:** Not separately recorded.

**New value:** Added declared-count validation, supersession consistency validation, full decision-register workbook projection, component-path/classification workbook projection, and decision-level tip-separation validation.

**Change:** Added declared-count validation, supersession consistency validation, full decision-register workbook projection, component-path/classification workbook projection, and decision-level tip-separation validation.

**Reason:** Round 2 exposed five already-approved rules or projection contracts that the validator did not enforce.

**Verification:** Baseline validation plus post-repair diagnostics for R2-BMP-S-12, R2-BMP-S-18, R2-BMP-P-14, R2-BMP-P-16 and R2-BMP-M-24.

**Residual risk:** None.

### AMD-V206-001 - M5a service inventory correction

**Source:** Codex v2.0.5 Package M0 review  
**Affected:** FR-EDG-002A, m5_ownership.json, D-113

**Old value:** M5a listed six services including local_backup_agent.

**New value:** M5a lists exactly five required services; backup scheduling and destructive restore remain M6.

**Change:** M5a lists exactly five required services; backup scheduling and destructive restore remain M6.

**Reason:** Resolve Codex P1-01 and restore the exact five-service edge boundary.

**Verification:** M5 ownership, requirements and publications agree; validator asserts exact service set.

**Residual risk:** None.

### AMD-V206-002 - Lifecycle-state reconciliation

**Source:** Codex v2.0.5 Package M0 review  
**Affected:** residual_issues.json, finding_register.json

**Old value:** Canonical records said blind mutations and validator freeze had not occurred.

**New value:** Canonical lifecycle records show both blind rounds, frozen validator, v2.0.5 Codex review and v2.0.6 repair state.

**Change:** Canonical lifecycle records show both blind rounds, frozen validator, v2.0.5 Codex review and v2.0.6 repair state.

**Reason:** Resolve Codex P1-02.

**Verification:** Lifecycle validator rejects stale next-step wording and unresolved historical states.

**Residual risk:** None.

### AMD-V206-003 - Uniform clause canonical contract

**Source:** Codex v2.0.5 Package M0 review  
**Affected:** reconciled_requirements.json, reconciled_canonical_register.schema.json

**Old value:** Ten clauses used substitute fields instead of exact_clause_text.

**New value:** All 337 clauses use the same required exact_clause_text contract; substitute fields are removed.

**Change:** All 337 clauses use the same required exact_clause_text contract; substitute fields are removed.

**Reason:** Resolve Codex P1-03.

**Verification:** Schema and validator require the uniform clause fields for every clause.

**Residual risk:** None.

### AMD-V206-004 - Lossless generated projections

**Source:** Codex v2.0.5 Package M0 review  
**Affected:** generator, workbooks, human publications

**Old value:** Amendments, findings, split reasons and 96 non-regression rules were incompletely projected.

**New value:** Every canonical field is mapped; all split reasons and all 96 identified rules are published in Markdown and Excel.

**Change:** Every canonical field is mapped; all split reasons and all 96 identified rules are published in Markdown and Excel.

**Reason:** Resolve Codex P1-04.

**Verification:** Field-level projection validator compares all rows and required fields.

**Residual risk:** None.

### AMD-V206-005 - Executable forbidden-surface rules

**Source:** Codex v2.0.5 Package M0 review  
**Affected:** forbidden_surface_rules.json, validator

**Old value:** Validator used hard-coded incomplete vocabulary and sense handling.

**New value:** Validator loads the normative vocabulary, negation markers and sense exclusions; every excluded domain and permitted sense has planted tests.

**Change:** Validator loads the normative vocabulary, negation markers and sense exclusions; every excluded domain and permitted sense has planted tests.

**Reason:** Resolve Codex P1-05.

**Verification:** Internal mutation suite exercises every forbidden domain and every permitted sense.

**Residual risk:** None.

### AMD-V206-006A - D-100 projection-authority provenance

**Source:** Codex v2.0.5 Package M0 review  
**Affected:** D-100, original_decision_dispositions.json

**Old value:** D-100 contained a generated-projection parity clause absent from the v2.0.3 disposition without amendment evidence.

**New value:** The clause is retained and explicitly recorded as AMD-V206-006A.

**Change:** The clause is retained and explicitly recorded as AMD-V206-006A.

**Reason:** Resolve Codex P1-06.

**Verification:** Decision register and amendment register cross-reference D-100.

**Residual risk:** None.

### AMD-V206-006B - D-102 exact pinned-package reuse evidence

**Source:** Codex v2.0.5 Package M0 review  
**Affected:** D-102, FR-GOV-003

**Old value:** D-102 named v2.0.4 tests as evidence for a later package.

**New value:** Reused code must pass tests written against the exact pinned package.

**Change:** Reused code must pass tests written against the exact pinned package.

**Reason:** Resolve Codex P1-06.

**Verification:** Validator rejects stale package-version test wording in D-102.

**Residual risk:** None.

### AMD-V206-007 - Canonical test-ID namespace

**Source:** Codex v2.0.5 Package M0 review  
**Affected:** 336 requirements, 337 clauses, dependency_graph.json, workbooks

**Old value:** Top-level acceptance IDs and clause engineering-test IDs diverged on 18 requirements.

**New value:** Top-level test IDs equal the ordered clause union; single- and multi-clause formats are explicit.

**Change:** Top-level test IDs equal the ordered clause union; single- and multi-clause formats are explicit.

**Reason:** Resolve Codex P2-01.

**Verification:** Validator enforces exact equality, gate coverage and active-ID prefixes.

**Residual risk:** None.

### AMD-V208-001 - Occurrence-linked forbidden-surface semantics

**Source:** Codex v2.0.7 Package M0 review  
**Affected:** FR-GOV-002, FR-TST-017, D-103, D-115, forbidden_surface_rules.json, validator

**Old value:** Negation and sense exclusions could authorize unrelated forbidden occurrences within a sentence or requirement.

**New value:** Each forbidden occurrence is evaluated in its own adversative clause; negation must govern that occurrence, double-negation fails, and sense exclusions require approved phrase patterns.

**Change:** Replaced sentence-wide and requirement-wide authorization with occurrence-linked negation and exact phrase/sense matching.

**Reason:** Resolve Codex v2.0.7 P1-02.

**Verification:** Mandatory probes include all four Codex bypasses, cross-sentence/adversative variants, double negation, and permitted senses.

**Residual risk:** Automated scanning does not replace independent human semantic review.

### AMD-V208-002 - D-100 JSON projection wording

**Source:** Codex v2.0.7 Package M0 review  
**Affected:** D-100, decision projections

**Old value:** D-100 referred to narrative, YAML and workbook projections although controlled machine-readable projections are JSON.

**New value:** D-100 refers to narrative, JSON and workbook projections.

**Change:** Corrected the projection-format name and regenerated all decision publications.

**Reason:** Resolve Codex v2.0.7 P2-01.

**Verification:** Decision JSON, workbook, Markdown, DOCX and PDF contain identical corrected wording.

**Residual risk:** None.

### AMD-V208-003 - Mandatory outer ZIP pin delivery

**Source:** Codex v2.0.7 Package M0 review  
**Affected:** FR-GOV-004, D-100, D-102, Package M0 delivery

**Old value:** The v2.0.7 review delivery omitted the separate .zip.sha256 publisher pin.

**New value:** The v2.0.8 delivery contains the ZIP and matching .zip.sha256 as two separate artifacts.

**Change:** Locked the final handoff to a two-file delivery and explicit expected hash in the review prompt.

**Reason:** Resolve Codex v2.0.7 P1-01.

**Verification:** Final response exposes both artifacts and the sidecar contains the exact ZIP digest.

**Residual risk:** The sender must attach both files.

## Findings

### V204-P0-01 - M4 mandatory journeys require physical receipts while the first printer capability was owned by M5a.

**Severity:** P0  
**Disposition:** resolved  
**Affected:** FR-CFG-001D, FR-BIL-017, FR-EDG-029, D-119, GJ-01B, GJ-02B, GJ-03B, GJ-06, GJ-07, GJ-10

**Finding:** M4 mandatory journeys require physical receipts while the first printer capability was owned by M5a.

**Verification:** M4 has a minimum real physical-receipt path; M5a separately owns durable queue, retry, restart recovery, deduplication, health, outage continuity and reconciliation.

**Residual risk:** None; v2.0.5 Codex verified M4/M5a print separation.

### V204-P1-02 - Decision D-113 provenance differed between narrative and machine-readable sources.

**Severity:** P1  
**Disposition:** resolved  
**Affected:** D-113

**Finding:** Decision D-113 provenance differed between narrative and machine-readable sources.

**Verification:** Canonical decision source is v2.0.3 in the reconciled decision catalog.

**Residual risk:** None.

### V204-P1-03 - Original package assessment counts were stale.

**Severity:** P1  
**Disposition:** resolved  
**Affected:** original_requirement_lineage.json, original_decision_dispositions.json

**Finding:** Original package assessment counts were stale.

**Verification:** The v2.0.6 generator publishes current row-level counts and all projections from canonical records.

**Residual risk:** None.

### V204-P1-04 - Row-level 500 original requirement and 100 original decision dispositions were missing.

**Severity:** P1  
**Disposition:** resolved  
**Affected:** original_requirement_lineage.json

**Finding:** Row-level 500 original requirement and 100 original decision dispositions were missing.

**Verification:** The frozen canonical baseline contains the 500/100 row-level evidence; this package retains the exact source hashes and maps all 294 active originals.

**Residual risk:** None for reconciliation.

### V204-P1-05 - The dependency graph was generic and milestone-wide rather than requirement-specific.

**Severity:** P1  
**Disposition:** resolved  
**Affected:** reconciled_requirements.json

**Finding:** The dependency graph was generic and milestone-wide rather than requirement-specific.

**Verification:** Two independent clause-level reviews were reconciled and the final graph has requirement-specific gates, prerequisites, journeys and tests.

**Residual risk:** Codex remains the independent semantic reviewer.

### V204-P1-06 - The package validator relied on PyYAML and checked structure rather than full semantics.

**Severity:** P1  
**Disposition:** resolved  
**Affected:** tools/validate_reconciled_stdlib.py

**Finding:** The package validator relied on PyYAML and checked structure rather than full semantics.

**Verification:** The standard-library validator was frozen and challenged through two blind mutation rounds; final limitations are disclosed.

**Residual risk:** Post-repair diagnostics are not fresh blind evidence.

### V204-P1-07 - GJ-01A said outlet authority persists at M3, implying local authority before M5b.

**Severity:** P1  
**Disposition:** resolved  
**Affected:** GJ-01A

**Finding:** GJ-01A said outlet authority persists at M3, implying local authority before M5b.

**Verification:** GJ-01A now states that the current approved cloud authority persists and makes no local-authority claim before M5b.

**Residual risk:** None.

### V204-P2-08 - Private-key custody was inconsistent.

**Severity:** P2  
**Disposition:** resolved  
**Affected:** FR-EDG-022A, D-116

**Finding:** Private-key custody was inconsistent.

**Verification:** The node generates and retains the private key, submits only a CSR, receives only the certificate chain, and never exports the private key.

**Residual risk:** Operational HSM/keystore choice remains an implementation decision under this contract.

### V204-P2-09 - FR-EDG-028 test ID used inconsistent M5b casing.

**Severity:** P2  
**Disposition:** resolved  
**Affected:** FR-EDG-028

**Finding:** FR-EDG-028 test ID used inconsistent M5b casing.

**Verification:** Engineering test ID is normalized to TST-M5b-FR-EDG-028.

**Residual risk:** None.

### V204-P2-10 - Amendment and finding logs were not exact enough.

**Severity:** P2  
**Disposition:** resolved  
**Affected:** finding_register.json, amendment_register.json

**Finding:** Amendment and finding logs were not exact enough.

**Verification:** Each prior finding has an ID, severity, disposition, affected IDs, verification and residual risk.

**Residual risk:** Future findings must use the same structure.

### VAL-P1-001 - Journey links were not consistently aligned to introduction/revalidation gates

**Severity:** P1  
**Disposition:** REPAIRED  
**Affected:** FR-SEC-002A, FR-TST-006, FR-AUTH-003, FR-MNU-012, FR-RPT-001, FR-RPT-004, FR-RPT-005

**Finding:** Journey links were not consistently aligned to introduction/revalidation gates

**Verification:** Every journey milestone now equals the requirement introducing gate or a declared revalidation gate.

**Residual risk:** none

### VAL-P1-002 - Round 2 exposed five validator coverage gaps

**Severity:** P1  
**Disposition:** REPAIRED_AND_REFROZEN  
**Affected:** FR-CFG-002B, FR-DAT-003, D-043, canonical count declarations, canonical decision projection

**Finding:** Round 2 exposed five validator coverage gaps

**Verification:** All five disclosed Round 2 misses are detected after repair. No Round 3 is required under the agreed two-round cap unless Codex later identifies a P0 validator defect.

**Residual risk:** The post-repair rerun is diagnostic rather than fresh independent evidence. This limitation is disclosed to Codex.

### V205-P1-01 - M5a service boundary contradiction

**Severity:** P1  
**Disposition:** resolved  
**Affected:** FR-EDG-002A, FR-OPS-006, FR-OPS-007, FR-SEC-019, FR-TST-009, D-113, GJ-10, GJ-11

**Finding:** m5_ownership.json listed local_backup_agent although FR-EDG-002A requires exactly five services.

**Verification:** M5a now lists exactly five services; backup scheduling and restore remain M6.

**Residual risk:** None.

### V205-P1-02 - Stale canonical governance state

**Severity:** P1  
**Disposition:** resolved  
**Affected:** residual_issues.json, finding_register.json

**Finding:** Residual/finding records described validator and blind rounds as future work.

**Verification:** Lifecycle state is current and projections are regenerated.

**Residual risk:** None.

### V205-P1-03 - Non-uniform clause schema

**Severity:** P1  
**Disposition:** resolved  
**Affected:** reconciled_requirements.json, reconciled_canonical_register.schema.json

**Finding:** Ten clauses omitted exact_clause_text and used substitute fields.

**Verification:** All 337 clauses share one enforced contract.

**Residual risk:** None.

### V205-P1-04 - Projection content loss

**Severity:** P1  
**Disposition:** resolved  
**Affected:** amendment_register.json, finding_register.json, original_requirement_lineage.json, non_regression_rules.json

**Finding:** Amendments, findings, split reasons and non-regression rules were incompletely published.

**Verification:** All canonical fields and all 96 rules are projected and field-compared.

**Residual risk:** None.

### V205-P1-05 - Forbidden-surface rules not executable

**Severity:** P1  
**Disposition:** resolved  
**Affected:** forbidden_surface_rules.json, validator

**Finding:** Validator did not load the normative vocabulary and sense exclusions.

**Verification:** Validator executes the normative rule file and planted tests cover every domain and permitted sense.

**Residual risk:** None.

### V205-P1-06 - Decision provenance and stale reuse evidence

**Severity:** P1  
**Disposition:** resolved  
**Affected:** D-100, D-102, FR-GOV-003

**Finding:** D-100 lacked amendment evidence and D-102 named v2.0.4 tests.

**Verification:** D-100 amendment is explicit and D-102 requires exact pinned-package tests.

**Residual risk:** None.

### V205-P2-01 - Divergent test-ID namespaces

**Severity:** P2  
**Disposition:** resolved  
**Affected:** requirements.json, dependency_graph.json

**Finding:** Top-level and clause-level test IDs diverged on 18 requirements.

**Verification:** One canonical test-ID policy is enforced across all projections.

**Residual risk:** None.

### V207-P1-01 - Required outer artifact pin was not delivered

**Severity:** P1  
**Disposition:** resolved_by_v2.0.8_delivery  
**Affected:** FR-GOV-004, D-100, D-102

**Finding:** The Package M0 review received the ZIP without the separately supplied .zip.sha256 publisher pin.

**Verification:** The v2.0.8 ZIP and matching sidecar are delivered together and the prompt states the expected digest.

**Residual risk:** External delivery must include both files.

### V207-P1-02 - Forbidden-surface validator admitted coherent deferred-domain obligations

**Severity:** P1  
**Disposition:** resolved  
**Affected:** FR-GOV-002, FR-TST-017, D-103, D-115

**Finding:** Sentence-wide negation and requirement-wide sense allowances could permit unrelated positive payroll, inventory or variance obligations.

**Verification:** Occurrence-linked parser rejects all four Codex examples and targeted variants while preserving approved senses.

**Residual risk:** Human semantic review remains required for novel wording.

### V207-P2-01 - D-100 referred to nonexistent YAML projections

**Severity:** P2  
**Disposition:** resolved  
**Affected:** D-100

**Finding:** The package uses JSON as its controlled machine-readable projection, not YAML.

**Verification:** All decision projections use the corrected JSON wording.

**Residual risk:** None.
