# Codex Package M0 Independent Review Brief

## Artifact to review

`Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9.zip`

The reviewer must receive both the ZIP and its `.zip.sha256` sidecar, independently compute the ZIP hash, compare it with the supplied pin, and run:

```bash
python 06_TOOLS/validate_package_m0.py .
```

The package validator must return `PASS PACKAGE_M0_VALID`. The reviewer must also verify the pinned canonical source ZIP and frozen validator hashes.

## Independence

Review the package independently. Do not rely on prior reviewer dispositions as proof. The historical and reconciliation material may be used only after forming an independent view of the current canonical product, architecture, gates and acceptance evidence.

## Required review questions

1. Can every active requirement be traced to a milestone, journey or explicit engineering test?
2. Are any Phase 2/3 or deferred extension capabilities accidentally required by Phase 1?
3. Can the same table QR safely resolve to cloud or outlet node without browser-security warnings?
4. Is the outlet authority model sufficient to prevent split-brain, including emergency replacement?
5. Are local/cloud identifiers, idempotency, authority sequence and dependency ordering specified clearly?
6. Are bill, tip, payment, service charge and tax structurally separate?
7. Does Arabic RTL receive executable mixed-direction, ETB, numeral and receipt coverage rather than string substitution?
8. Are tenant/outlet boundaries enforceable using exact production roles?
9. Can backup/restore and production images be tested without host-only dependencies?
10. Can every CI job fail honestly when tests are skipped, undiscovered, stale or unsupported?
11. Is the build graph executable milestone-by-milestone using only approved predecessors?
12. Is any v1.1 or deferred-module assumption silently retained?
13. Are 5-second proofs, 10-second degradation, 20-second lease expiry, three-proof recovery and asymmetric LAN service independently specified and testable?
14. Are cash, external-terminal recording and verified Telebirr/CBE Birr proof confirmation live pilot paths while direct provider APIs remain simulator-only?

## Critical semantic areas

- M0R contains no database, executable migration, route, worker, screen or application code.
- Minimum physical receipt printing begins at M4; M5a adds resilience.
- M5a does not claim local authority; M5b owns same-QR DNS/TLS, lease and fencing.
- Bill, payment and tip remain separate; no tip is preselected.
- Direct payment-provider APIs remain simulator-only until contracted.
- Node private keys never leave the outlet node.
- Phase 2/3 surfaces are physically absent.
- Every requirement is executable at its introduction gate with no later-gate prerequisite.

## Verdict required

Return exactly one:

- `APPROVE PACKAGE M0 AND AUTHORIZE M0R`
- `DO NOT AUTHORIZE M0R`

List every P0/P1/P2 finding with affected IDs, evidence, required amendment and gate consequence. A bounded publication/projection P1 may proceed only under FR-GOV-004; substantive P1 findings remain blockers.
