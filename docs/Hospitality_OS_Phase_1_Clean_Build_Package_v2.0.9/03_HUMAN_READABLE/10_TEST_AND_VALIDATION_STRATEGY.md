# Test, Evidence and Validator Strategy

- Package: `Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9`
- Canonical source root: `cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96`
- Status: **Package M0 candidate - M0R and implementation are not authorized**

## Validator status

- Frozen validator script SHA-256: `ee65b8ec3292db19798f785e23a2d54969eadd91f00e98888520d16051c9f7b0`
- Validator package SHA-256: `628ae551120497280a82fdfcf8fd8bd2a69e4c893b400cd94d1914529788cce9`
- Internal planted mutations: **10/10 detected**
- Blind Round 1: **23/24 detected before repair**
- Blind Round 2: **23/28 detected before repair**
- Disclosed Round 2 misses after repair: **5/5 detected diagnostically**

The post-repair reruns are diagnostic, not fresh independent evidence. The agreed two-round cap is closed; Codex receives the limitation explicitly.

## Negative controls

- **NC-M0-001 (M0):** Package pinning - deliberate break: Change one controlled file after checksum generation - expected: `CHECKSUM_MISMATCH`
- **NC-M0-002 (M0):** Requirement recount - deliberate break: Remove or duplicate one requirement row - expected: `REQUIREMENT_COUNT_OR_DUPLICATE`
- **NC-M0-003 (M0):** Phase boundary - deliberate break: Plant one forbidden positive obligation for every excluded domain in the generated vocabulary (pickup, delivery, loyalty, CRM, purchasing/procurement, inventory/storage location, accounting/general ledger, HR/payroll, operational recipes, costing/variance, intelligence/forecasting, supplier runtime and portability product) into a Phase 1 fixture - expected: `FORBIDDEN_PHASE1_SURFACE_PER_DOMAIN`
- **NC-M0-005 (M0):** Forbidden-surface vocabulary completeness - deliberate break: Remove one excluded domain from the generated forbidden-surface vocabulary while leaving it excluded in phase_boundaries - expected: `EXCLUSION_SET_NOT_COVERED`
- **NC-M1-001 (M1):** Fail-closed tenant context - deliberate break: Run production role with tenant/outlet context unset - expected: `VISIBLE_OR_WRITABLE_ROWS_WITHOUT_CONTEXT`
- **NC-M1-002 (M1):** Sibling-outlet isolation - deliberate break: Soften one outlet policy to tenant-only - expected: `SIBLING_OUTLET_ACCESS`
- **NC-M1-003 (M1):** Future schema protection - deliberate break: Add outlet_id to an existing tenant table without policy upgrade - expected: `OUTLET_POLICY_NOT_UPGRADED`
- **NC-M1-004 (M1):** Runtime least privilege - deliberate break: Configure API/worker with owner or BYPASSRLS role - expected: `PRIVILEGED_RUNTIME_ROLE_REJECTED`
- **NC-M2-001 (M2):** Opaque QR - deliberate break: Replace opaque token with enumerable table number - expected: `ENUMERABLE_QR_REFERENCE`
- **NC-M2-002 (M2):** Session scope - deliberate break: Forge participant token for another outlet/table - expected: `FOREIGN_SESSION_ACCEPTED`
- **NC-M2-003 (M2):** Safety translation publication - deliberate break: Remove required Arabic allergen translation - expected: `REQUIRED_SAFETY_TRANSLATION_MISSING`
- **NC-M2-004 (M2):** Arabic RTL depth - deliberate break: Disable dir=rtl/logical CSS or inject mixed Latin SKU string - expected: `RTL_LAYOUT_OR_READING_ORDER_FAILURE`
- **NC-M3-001 (M3):** Order idempotency - deliberate break: Repeat submit with same idempotency key - expected: `DUPLICATE_ORDER_EFFECT`
- **NC-M3-002 (M3):** Price snapshot - deliberate break: Change menu price between display and submit without revalidation - expected: `STALE_PRICE_ACCEPTED`
- **NC-M3-003 (M3):** Allergy propagation - deliberate break: Drop allergy flag before KDS ticket - expected: `ALLERGY_FLAG_LOST`
- **NC-M3-004 (M3):** State enforcement - deliberate break: Jump accepted order directly to served - expected: `ILLEGAL_TRANSITION_ACCEPTED`
- **NC-M4-001 (M4):** No tip default - deliberate break: Preselect a suggested tip - expected: `TIP_PRESELECTED`
- **NC-M4-002 (M4):** Bill/tip separation - deliberate break: Add tip to taxable bill balance - expected: `TIP_COMMINGLED_WITH_BILL`
- **NC-M4-003 (M4):** Payment truth and live/simulated boundary - deliberate break: Mark unverified Telebirr/CBE Birr proof paid or label a direct-provider simulator as live - expected: `UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM`
- **NC-M4-004 (M4):** Maker-checker - deliberate break: Allow cashier to approve own refund/tip reversal - expected: `SELF_APPROVAL_ACCEPTED`
- **NC-M4-005 (M4):** Amharic settlement and receipt coverage - deliberate break: Remove the packaged Ethiopic font from the receipt print path or fall back to a substitute glyph set - expected: `ETHIOPIC_FONT_FALLBACK_ON_RECEIPT`
- **NC-M4-006 (M4):** Reopened cash shift closure - deliberate break: Leave a reopened cash shift with no recount, approval or maker-checker correction path and attempt to report it as closed - expected: `REOPENED_SHIFT_NOT_RESOLVED`
- **NC-M5A-001 (M5a):** Sync dependency order - deliberate break: Upload child before unacknowledged parent - expected: `CHILD_APPLIED_BEFORE_PARENT`
- **NC-M5A-002 (M5a):** Sync idempotency - deliberate break: Replay order/payment/tip event - expected: `DUPLICATE_COMMERCIAL_EFFECT`
- **NC-M5A-003 (M5a):** Print idempotency - deliberate break: Retry acknowledged print job - expected: `DUPLICATE_UNMARKED_PRINT`
- **NC-M5A-004 (M5a):** Durability - deliberate break: Restart browser/node with accepted local order queued - expected: `LOCAL_RECORD_LOST`
- **NC-M5B-001 (M5b):** Public-trust TLS - deliberate break: Use self-signed, wrong-host or expired certificate - expected: `TLS_NOT_PUBLICLY_TRUSTED`
- **NC-M5B-002 (M5b):** Bidirectional cloud forwarding lease - deliberate break: Permit cloud write after 20-second lease expiry or accept a one-way reachability proof - expected: `CLOUD_WRITE_AFTER_LEASE_EXPIRY_OR_ONE_WAY_PROOF`
- **NC-M5B-003 (M5b):** Asymmetric LAN authority - deliberate break: Stop LAN writes merely because the cloud forwarding lease expires - expected: `LAN_AUTHORITY_REVOKED_BY_CLOUD_OUTAGE`
- **NC-M5B-004 (M5b):** Emergency replacement fencing and monotonic sequence - deliberate break: Activate replacement without recorded power/network fence and LAN-unreachability proof, or allow a direct LAN write to the old node after replacement - expected: `OLD_NODE_STILL_WRITABLE_OR_REPLACEMENT_UNFENCED`
- **NC-M5B-005 (M5b):** Cloud-to-node reachability direction - deliberate break: Allow node-to-cloud heartbeat traffic but block cloud challenge delivery while treating the lease as valid - expected: `ONE_WAY_CLOUD_TO_NODE_ACCEPTED`
- **NC-M5B-006 (M5b):** Node-to-cloud reachability direction - deliberate break: Allow cloud challenge delivery but block node acknowledgement while treating the lease as valid - expected: `ONE_WAY_NODE_TO_CLOUD_ACCEPTED`
- **NC-M5B-007 (M5b):** Certificate lifecycle - deliberate break: Allow the per-outlet certificate to pass its renewal threshold without renewal, escalation or installation evidence - expected: `CERTIFICATE_RENEWAL_NOT_ENFORCED`
- **NC-M5B-008 (M5b):** Same-QR resolution under real client conditions - deliberate break: Join outlet Wi-Fi holding a cached public DNS answer, and separately enable encrypted DNS (Private DNS/DoH) that bypasses outlet split DNS - expected: `SAME_QR_RESOLUTION_UNSAFE_OR_UNGUIDED`
- **NC-M5B-009 (M5b):** Replacement activation gate - deliberate break: Attempt to make a standby node writable directly from standby without passing authority_activating readiness and sequence confirmation - expected: `REPLACEMENT_WRITABLE_WITHOUT_ACTIVATION`
- **NC-M6-001 (M6):** Zero-skip CI - deliberate break: Skip one discovered acceptance test - expected: `SKIPPED_TEST_DETECTED`
- **NC-M6-002 (M6):** Clean build - deliberate break: Leave stale route artifact before build - expected: `STALE_ARTIFACT_DETECTED`
- **NC-M6-003 (M6):** Ordinary Windows - deliberate break: Require hidden PG_BIN/PATH injection - expected: `HIDDEN_ENV_DEPENDENCY`
- **NC-M6-004 (M6):** Production image completeness - deliberate break: Remove an advertised runtime script or required PostgreSQL client from the production image - expected: `REQUIRED_ARTIFACT_MISSING`
- **NC-M6-005 (M6):** Restore realism - deliberate break: Run restore smoke with owner instead of production role - expected: `NON_PRODUCTION_ROLE_USED`
- **NC-M0-011 (M0):** Accounting alias leakage - deliberate break: Plant a Phase 1 journal entry or ledger-posting obligation using singular/plural aliases. - expected: `FORBIDDEN_ACCOUNTING_OBLIGATION`
- **NC-M0-012 (M0):** CRM campaign alias leakage - deliberate break: Plant a generic campaign correlation field without the phrase marketing campaign. - expected: `FORBIDDEN_CRM_OBLIGATION`
- **NC-M0-013 (M0):** Workforce alias leakage - deliberate break: Plant roster, attendance, timekeeping or break-record persistence in service presence. - expected: `FORBIDDEN_WORKFORCE_OBLIGATION`
- **NC-M0-014 (M0):** Canonical projection parity - deliberate break: Change a Source of Truth decision cell without changing the canonical decision record. - expected: `CANONICAL_PROJECTION_MISMATCH`

## Package M0 questions

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
