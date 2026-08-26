# State Machines

**12 canonical machines**

- Package: `Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9`
- Canonical source root: `cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96`
- Status: **Package M0 candidate - M0R and implementation are not authorized**

## SM-TABLE-SESSION - Table Session

**Phase:** Phase 1

**States:** pending, open, service_active, bill_requested, settling, closed, cancelled, transferred

**Transitions**

- pending -> open: valid QR/session creation
- open -> service_active: first accepted order or service request
- service_active -> bill_requested: customer/staff requests bill
- bill_requested -> service_active: bill request withdrawn before presentation
- bill_requested -> settling: check presented
- settling -> closed: all checks settled and service complete
- open/service_active -> transferred: authorized table move
- transferred -> open/service_active: destination confirmed
- pending/open -> cancelled: authorized cancellation without accepted commerce

**Invariants**

- Exactly one tenant and outlet scope.
- Opaque QR never exposes sequential table ID.
- Closing a session does not delete carts, orders, checks or payments.
- Participant tokens cannot cross sessions or outlets.

## SM-CART - Cart

**Phase:** Phase 1

**States:** active, validating, submitted, expired, abandoned

**Transitions**

- active -> validating: submit requested
- validating -> active: validation error
- validating -> submitted: one order created/idempotent prior outcome
- active -> expired: session/policy expiry
- active -> abandoned: customer intentionally abandons

**Invariants**

- Cart ownership is participant/shared-table explicit.
- Submission revalidates price, availability, translations and modifiers.
- A submitted cart maps to exactly one order outcome.
- Language switching does not lose cart identity.

## SM-ORDER - Order

**Phase:** Phase 1

**States:** draft, submitted, awaiting_confirmation, accepted, in_fulfillment, partially_ready, ready, partially_served, served, completed, cancelled, voided, on_hold

**Transitions**

- draft -> submitted: submit
- submitted -> awaiting_confirmation: policy requires staff confirmation
- submitted/awaiting_confirmation -> accepted: accepted
- accepted -> in_fulfillment: tickets released
- in_fulfillment -> partially_ready: some lines ready
- in_fulfillment/partially_ready -> ready: all lines ready
- ready -> partially_served: some lines served
- ready/partially_served -> served: all lines served
- served -> completed: operational and financial conditions satisfied
- submitted/accepted -> cancelled: authorized pre-fulfillment cancellation
- accepted -> on_hold: authorized hold
- on_hold -> accepted: release
- completed -> voided: authorized correction workflow

**Invariants**

- Accepted price/tax/service snapshots are immutable.
- Order, fulfillment, check, payment and tip states are separate.
- Changes preserve an event timeline.
- A local/cloud retry cannot create a second order.

## SM-FULFILLMENT-TICKET - Kitchen/Bar/Expo Ticket

**Phase:** Phase 1

**States:** queued, acknowledged, held, preparing, partially_completed, ready, collected, completed, rework, cancelled, exception

**Transitions**

- queued -> acknowledged: station accepts
- acknowledged -> held: course/capacity hold
- held/acknowledged -> preparing: fire/start
- preparing -> partially_completed: some units ready
- preparing/partially_completed -> ready: all units ready
- ready -> collected: waiter/runner collects
- collected -> completed: served/handoff confirmed
- ready -> rework: quality issue
- rework -> preparing: remake
- queued -> cancelled: upstream cancellation
- preparing -> exception: unavailable/equipment/safety issue

**Invariants**

- Ticket quantities cannot exceed accepted order-line quantities.
- Allergy flags and customer notes persist through routing.
- Rework is reasoned and audited; Phase 1 does not post inventory consumption.
- State transitions are enforced server/database side.

## SM-SERVICE-REQUEST - Customer Service Request

**Phase:** Phase 1

**States:** new, routed, acknowledged, in_progress, completed, cancelled, expired, escalated, unresolved

**Transitions**

- new -> routed: routing rule
- routed -> acknowledged: staff accepts
- acknowledged -> in_progress: work begins
- in_progress -> completed: outcome recorded
- routed -> escalated: SLA exceeded
- escalated -> acknowledged: alternate accepts
- new -> cancelled: customer withdraws
- routed -> expired: session closes/policy
- in_progress -> unresolved: reason recorded

**Invariants**

- Every active request has an accountable queue/assignee.
- Acknowledgement and completion timestamps are retained.
- Duplicate taps are deduplicated without hiding deliberate repeat requests.
- Customer status uses the session language.

## SM-CHECK - Check / Bill

**Phase:** Phase 1

**States:** draft, open, presented, partially_paid, paid, issued, voided, credited, written_off

**Transitions**

- draft -> open: line allocation validated
- open -> presented: bill shown/printed
- presented -> partially_paid: bill allocation below balance
- presented/partially_paid -> paid: bill balance fully settled
- paid -> issued: final receipt/fiscal outcome
- issued -> voided: authorized legal/operational void
- issued -> credited: linked credit/refund correction
- presented -> written_off: authorized disposition

**Invariants**

- Order-line quantities cannot be billed twice.
- Bill balance excludes optional tip.
- Issued records are corrected, not overwritten.
- Split/merge preserves original line ownership and audit.

## SM-PAYMENT - Payment

**Phase:** Phase 1

**States:** created, pending, proof_pending, authorized, captured, partially_allocated, allocated, failed, cancelled, reversed, partially_refunded, refunded, reconciliation_required, reconciled

**Transitions**

- created -> pending: tender initiated
- pending -> proof_pending: Telebirr/CBE Birr proof submitted
- proof_pending -> captured: staff verifies provider receipt and records provider/reference evidence
- proof_pending -> failed: proof rejected, expired or cannot be verified
- pending -> authorized: external terminal authorization recorded
- authorized -> captured: terminal completion recorded
- pending -> captured: cash accepted or terminal returns combined success
- pending -> failed: provider or operational failure
- pending/proof_pending/authorized -> cancelled: authorized cancellation before capture
- captured -> partially_allocated: some bill/tip allocation posted
- captured/partially_allocated -> allocated: all exact allocations posted
- captured/partially_allocated/allocated -> reversed: approved full reversal
- allocated -> partially_refunded: approved refund below captured total
- allocated -> refunded: approved full refund
- partially_refunded -> partially_refunded: additional partial refund below captured total
- partially_refunded -> refunded: cumulative refunds equal captured total
- captured/partially_allocated/allocated/reversed/partially_refunded/refunded/failed/cancelled -> reconciliation_required: provider, cash or allocation mismatch detected
- reconciliation_required -> captured: verified missed capture
- reconciliation_required -> allocated: verified allocation correction
- reconciliation_required -> reversed: verified reversal
- reconciliation_required -> refunded: verified full refund
- reconciliation_required -> failed: verified failure
- captured/allocated/reversed/refunded/failed -> reconciled: evidence matches final commercial outcome

**Invariants**

- Bill and tip allocations are separate exact values.
- Raw card data is never stored.
- A payment retry is idempotent and provider/reference uniqueness is enforced.
- Telebirr/CBE Birr remains proof_pending until staff verifies receipt in the provider application.
- Unverified proof, screenshot or customer claim cannot produce a paid check or live receipt.
- Direct provider simulators cannot be labelled or reported as live pilot payments.
- Offline cash/local-terminal/mobile-proof records cannot be falsely labelled online-provider success.
- Every terminal state records actor, method, provider/reference evidence and reason where applicable.

## SM-TIP - Optional Tip

**Phase:** Phase 1

**States:** not_selected, proposed, accepted, payment_pending, recorded, settled, failed, cancelled, partially_refunded, refunded, reversed

**Transitions**

- not_selected -> proposed: customer opens tip choice
- proposed -> not_selected: customer declines or clears selection
- proposed -> accepted: explicit amount or percentage confirmation
- accepted -> payment_pending: linked payment intent created
- payment_pending -> recorded: linked payment captured and separate tip allocation created
- payment_pending -> failed: linked payment fails or proof is rejected
- payment_pending -> cancelled: linked payment is cancelled before capture
- recorded -> settled: linked payment allocations are final
- recorded/settled -> partially_refunded: approved tip refund below recorded tip
- recorded/settled -> refunded: approved full tip refund
- partially_refunded -> partially_refunded: additional partial refund below recorded tip
- partially_refunded -> refunded: cumulative refunds equal recorded tip
- recorded/settled/partially_refunded -> reversed: linked payment is fully reversed before completed refund treatment

**Invariants**

- No tip is selected by default.
- Tip is never required to settle the bill.
- Tip does not change order lines, bill allocation, tax, service-charge presentation or sales totals.
- Every tip is linked to one payer/payment and separately auditable.
- A failed or cancelled linked payment cannot create a recorded or settled tip.
- Payment reversal/refund creates the corresponding tip reversal/refund path; tip outcome cannot remain silently settled.
- Tip refunds and reversals require purpose-specific approval, reason and exact cumulative limits.

## SM-CASH-SHIFT - Cash Shift

**Phase:** Phase 1

**States:** planned, open, counting, submitted, approved, variance_review, closed, reopened

**Transitions**

- planned -> open: float accepted
- open -> counting: close initiated
- counting -> submitted: count submitted
- submitted -> approved: within policy/manager approves
- submitted -> variance_review: variance threshold exceeded
- variance_review -> approved: resolved
- approved -> closed: close posted
- closed -> reopened: exceptional approved correction
- reopened -> counting: corrected recount initiated under linked correction evidence
- reopened -> variance_review: correction requires variance adjudication
- reopened -> closed: authorized correction posted with maker-checker evidence and no recount required

**Invariants**

- Opening float, bill cash, tip cash, payouts, expected cash and actual cash are separate values.
- Cashier cannot self-approve restricted variance.
- Corrections use linked movements/reopen evidence.
- Offline shift survives restart and sync.
- reopened is never terminal; every reopened shift returns to closed through recount and approval or an audited maker-checker correction.

## SM-OUTLET-CONNECTIVITY - Outlet Connectivity and Authority

**Phase:** Phase 1

**States:** standby, authority_activating, connected, degraded, local_continuity, reconciling, replacement_pending, fence_verified, blocked, maintenance

**Transitions**

- connected -> degraded: one or more bidirectional reachability proofs fail and 10-second threshold is reached
- degraded -> local_continuity: cloud forwarding lease expires at 20 seconds and local readiness passes
- degraded -> connected: three consecutive valid bidirectional proofs before lease expiry
- local_continuity -> reconciling: three consecutive valid proofs plus protocol/cursor compatibility
- reconciling -> connected: queues acknowledged and highest authority sequence confirmed
- connected/degraded/local_continuity -> replacement_pending: step-up and independent replacement approval recorded
- replacement_pending -> fence_verified: old node power-off or network isolation evidence plus LAN-unreachability probe passes
- replacement_pending -> connected/local_continuity: replacement cancelled before new sequence issuance
- connected/degraded/local_continuity/reconciling/replacement_pending/fence_verified -> blocked: node identity, version, storage, security or authority invalid
- connected/local_continuity/blocked -> maintenance: authorized maintenance
- maintenance -> connected: readiness passes under highest accepted authority sequence
- fence_verified -> blocked: the superseded node instance is fenced and its authority sequence revoked
- standby -> authority_activating: fence evidence for the superseded instance passed, independent approval recorded, and the next durable monotonic signed authority sequence is issued to this instance
- authority_activating -> connected: readiness, identity, storage and protocol checks pass, cloud and local writers confirm the highest accepted sequence, and valid bidirectional proofs resume; EVT-AUTHORITY-REPLACEMENT-ACTIVATED is emitted
- authority_activating -> local_continuity: readiness checks pass while the cloud remains unreachable; this instance becomes the writable LAN authority and EVT-AUTHORITY-REPLACEMENT-ACTIVATED is emitted
- authority_activating -> blocked: readiness, identity, storage, signature or sequence validation fails; the instance never becomes writable

**Invariants**

- A valid reachability proof is a signed bidirectional challenge/acknowledgement confirming both directions, authority sequence, protocol compatibility and cursor posture.
- Cloud blocks new dine-in submissions after lease expiry but never revokes the LAN node local authority.
- Emergency replacement cannot become writable until old-node physical or network fence evidence and an automated LAN-unreachability probe pass.
- Authority sequence is durable, monotonic, signed and anti-rollback; every writer persists and compares the highest accepted sequence.
- After replacement, a direct LAN write to the old node fails and stale events quarantine.
- Transitions, approvals, fence evidence, probes and operator overrides are audited.
- A node instance in standby or authority_activating is never writable.
- At most one node instance per outlet is writable at any time; activation of a replacement requires the superseded instance to be fenced and blocked first.
- EVT-AUTHORITY-REPLACEMENT-ACTIVATED is emitted only on a transition out of authority_activating into a writable state.

## SM-SYNC-EVENT - Local/Cloud Synchronization Event

**Phase:** Phase 1

**States:** pending, sending, acknowledged, retrying, blocked, conflict, quarantined, superseded

**Transitions**

- pending -> sending: worker sends
- sending -> acknowledged: peer accepts/idempotent prior outcome
- sending -> retrying: transient failure
- retrying -> sending: backoff elapsed
- sending -> blocked: dependency/version/authority unavailable
- sending -> conflict: domain/version conflict
- sending -> quarantined: invalid/security/nonrecoverable
- conflict -> superseded: authorized resolution
- blocked -> pending: dependency resolved

**Invariants**

- Event ID and command idempotency prevent duplicate effect.
- Parent/dependency order is explicit.
- No silent last-write-wins for order, bill, payment, tip, cash or permission data.
- A bad event cannot permanently block unrelated streams.

## SM-PRINT-JOB - Local Print Job

**Phase:** Phase 1

**States:** queued, claimed, printing, printed, retrying, failed, cancelled, superseded

**Transitions**

- queued -> claimed: print agent claims
- claimed -> printing: device write begins
- printing -> printed: acknowledgement/evidence
- claimed/printing -> retrying: transient failure
- retrying -> claimed: retry due
- retrying -> failed: limit exceeded
- queued -> cancelled: safe upstream cancellation
- failed -> superseded: authorized replacement/reprint

**Invariants**

- A job has a deterministic deduplication key.
- Reprint is attributed and cannot silently duplicate an original receipt.
- Printer failure is visible to staff.
- Jobs persist through node restart and internet outage.
