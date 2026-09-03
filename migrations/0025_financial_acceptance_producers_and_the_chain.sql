-- =============================================================================
-- 0025 — Acceptance on a verified outcome, the chain, the producers, the drawer
-- =============================================================================
-- Everything M4-B owes to a domain it does not own. Each change here is a CREATE OR
-- REPLACE of a function some earlier migration created, because those migrations are
-- applied and checksum-locked and this repository does not edit them.
--
-- Five things close here, and every one of them was recorded as open before it was:
--
--   FR-ORD-007B   acceptance on a verified payment outcome. 0020 refused it by name
--                 because nothing could verify one; 0023 is the verifier.
--   FR-ORD-011    the payment dimension of the cancellation policy, which could not be
--                 applied to an empty set.
--   FR-ORD-012A   the unpaid precondition on a void, which at M3-A was true because no
--                 payment artifact existed to make it false.
--   FR-NOT-001    bill, payment and tip producers. The kinds have been in
--                 notify.catalog_event since M3-C with has_producer = false, and
--                 notify.emit() refuses a kind nothing produces — so this gate is the
--                 first at which the flag may honestly change.
--   FR-INT-014    bill, payment and tip in the correlation chain.
-- =============================================================================


-- ===========================================================================
-- A kind may claim a producer once its gate has landed (FR-NOT-001)
-- ===========================================================================
-- The CHECK 0014 wrote said M1, M2 or M3, and it was right on the day: M3 was the gate
-- being built and everything later was a name with nothing behind it. It is now a fence
-- around a gate that has landed, which is the sixth time this repository has met that
-- shape — six of them at M4-A. The rule that outlives every gate is the one underneath:
-- a kind may claim a producer when the gate that produces it EXISTS. Adding M4 keeps that
-- true today and states the general form in the comment for whoever adds M5a.

ALTER TABLE notify.catalog_event
    DROP CONSTRAINT catalog_event_producer_only_when_landed;

ALTER TABLE notify.catalog_event
    ADD CONSTRAINT catalog_event_producer_only_when_landed CHECK (
        NOT has_producer OR milestone IN ('M1', 'M2', 'M3', 'M4'));

COMMENT ON CONSTRAINT catalog_event_producer_only_when_landed ON notify.catalog_event IS
    'A kind cannot claim a producer before the gate that builds one. The list grows by '
    'one milestone per gate, as the gate lands and its producers are actually written — '
    'never in advance. tests/m3c no longer asserts the list is exactly M3: it derives '
    'which gates have landed from the repository and requires every producing kind to '
    'belong to one of them, so this constraint and that check cannot drift apart.';

-- The eight kinds M4 produces. Bill, payment and tip: FR-NOT-001's three remaining
-- classes, and every one of them now has something in this system that raises it. Outage
-- and sync stay false, and the closure register names M5a.
UPDATE notify.catalog_event SET has_producer = true
 WHERE event_id IN ('EVT-CHECK-OPENED', 'EVT-CHECK-PRESENTED', 'EVT-CHECK-PAID',
                    'EVT-PAYMENT-CAPTURED', 'EVT-PAYMENT-FAILED', 'EVT-PAYMENT-REVERSED',
                    'EVT-TIP-RECORDED', 'EVT-TIP-REFUNDED');


-- ===========================================================================
-- The chain, and the producers (FR-INT-014, FR-NOT-001, FR-ORD-019A)
-- ===========================================================================
-- Linked and emitted by TRIGGERS ON THE FOLDED TABLES rather than by callers. M3-B lost a
-- correlation link by having the caller write it, and the lesson recorded then was that a
-- link written outside the fold is one a rebuild does not put back. A trigger on the
-- table the fold writes is inside the fold by construction: billing.rebuild_projections()
-- replays the ledger through billing.apply_event(), the rows are inserted again, and
-- these fire again. The alternative — replacing 0019's hundred-line apply_event() to add
-- two statements — would copy a large function in order to change a small part of it,
-- which is how two versions of one fold come to exist.

CREATE FUNCTION billing.link_check_to_the_chain() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, billing, ordering, service, notify, public
AS $$
DECLARE
    v_correlation uuid;
    v_session uuid;
BEGIN
    SELECT o.correlation_id INTO v_correlation FROM ordering.customer_order o
     WHERE o.tenant_id = NEW.tenant_id AND o.id = NEW.order_id;
    IF v_correlation IS NULL THEN
        RETURN NULL;
    END IF;

    PERFORM ordering.link_correlation_artifact(
        NEW.tenant_id, NEW.outlet_id, v_correlation, 'check', NEW.check_id, now());

    SELECT c.table_session_id INTO v_session FROM billing.check c
     WHERE c.tenant_id = NEW.tenant_id AND c.id = NEW.check_id;

    -- FR-NOT-001's bill class, first kind. notify.emit() deduplicates on
    -- (kind, subject, state), so a check gathering ten allocations raises one notice.
    PERFORM notify.emit(NEW.tenant_id, NEW.outlet_id, 'EVT-CHECK-OPENED', 'check',
                        NEW.check_id, v_correlation, v_session,
                        jsonb_build_object('state', 'open'));
    RETURN NULL;
END;
$$;

CREATE TRIGGER check_joins_the_chain
    AFTER INSERT ON billing.check_allocation
    FOR EACH ROW EXECUTE FUNCTION billing.link_check_to_the_chain();


CREATE FUNCTION billing.link_bill_to_the_chain() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, billing, ordering, service, notify, public
AS $$
DECLARE
    v_correlation uuid;
    v_session uuid;
BEGIN
    SELECT o.correlation_id, c.table_session_id INTO v_correlation, v_session
      FROM billing.check c
      JOIN billing.check_allocation a
        ON a.tenant_id = c.tenant_id AND a.check_id = c.id
      JOIN ordering.customer_order o
        ON o.tenant_id = a.tenant_id AND o.id = a.order_id
     WHERE c.tenant_id = NEW.tenant_id AND c.id = NEW.check_id
     LIMIT 1;

    IF v_correlation IS NULL THEN
        RETURN NULL;
    END IF;

    PERFORM ordering.link_correlation_artifact(
        NEW.tenant_id, NEW.outlet_id, v_correlation, 'bill', NEW.id, now());

    PERFORM notify.emit(NEW.tenant_id, NEW.outlet_id, 'EVT-CHECK-PRESENTED', 'bill',
                        NEW.id, v_correlation, v_session,
                        jsonb_build_object('state', NEW.state::text));
    RETURN NULL;
END;
$$;

CREATE TRIGGER bill_joins_the_chain
    AFTER INSERT ON billing.bill
    FOR EACH ROW EXECUTE FUNCTION billing.link_bill_to_the_chain();


CREATE FUNCTION billing.link_tip_to_the_chain() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, billing, ordering, service, notify, public
AS $$
DECLARE
    v_correlation uuid;
    v_session uuid;
BEGIN
    -- A TIP IS ITS OWN LINK, not an attribute of the payment that carried it. FR-BIL-015
    -- lets a payer tip on their own share and FR-PAY-009 lets that tip be refunded
    -- without touching any bill payment; both need the tip to be findable in the chain on
    -- its own, which is why 0022 added 'tip' beside 'payment' rather than folding one
    -- into the other.
    SELECT o.correlation_id, c.table_session_id INTO v_correlation, v_session
      FROM billing.bill_share s
      JOIN billing.bill b ON b.tenant_id = s.tenant_id AND b.id = s.bill_id
      JOIN billing.check c ON c.tenant_id = b.tenant_id AND c.id = b.check_id
      JOIN billing.check_allocation a
        ON a.tenant_id = c.tenant_id AND a.check_id = c.id
      JOIN ordering.customer_order o
        ON o.tenant_id = a.tenant_id AND o.id = a.order_id
     WHERE s.tenant_id = NEW.tenant_id AND s.id = NEW.bill_share_id
     LIMIT 1;

    IF v_correlation IS NULL THEN
        RETURN NULL;
    END IF;

    PERFORM ordering.link_correlation_artifact(
        NEW.tenant_id, NEW.outlet_id, v_correlation, 'tip', NEW.id, now());

    PERFORM notify.emit(NEW.tenant_id, NEW.outlet_id, 'EVT-TIP-RECORDED', 'tip',
                        NEW.id, v_correlation, v_session,
                        jsonb_build_object('state', 'recorded'));
    RETURN NULL;
END;
$$;

CREATE TRIGGER tip_joins_the_chain
    AFTER INSERT ON billing.tip
    FOR EACH ROW EXECUTE FUNCTION billing.link_tip_to_the_chain();


CREATE FUNCTION payments.announce_payment() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, payments, billing, ordering, service, notify, public
AS $$
DECLARE
    v_session uuid;
    v_bill    uuid;
BEGIN
    IF NEW.correlation_id IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT c.table_session_id, b.id INTO v_session, v_bill
      FROM payments.payment_intent i
      JOIN billing.bill b ON b.tenant_id = i.tenant_id AND b.id = i.bill_id
      JOIN billing.check c ON c.tenant_id = b.tenant_id AND c.id = b.check_id
     WHERE i.tenant_id = NEW.tenant_id AND i.id = NEW.intent_id;

    IF NEW.state = 'captured' THEN
        PERFORM notify.emit(NEW.tenant_id, NEW.outlet_id, 'EVT-PAYMENT-CAPTURED',
                            'payment', NEW.id, NEW.correlation_id, v_session,
                            jsonb_build_object('state', 'captured'));
        -- FR-NOT-001's bill class again, and the kind a guest actually cares about. Only
        -- when the balance is gone: a partial settlement has not paid the check.
        IF v_bill IS NOT NULL AND billing.outstanding_balance(NEW.tenant_id, v_bill) > 0
           AND EXISTS (SELECT 1 FROM payments.allocation a
                        WHERE a.tenant_id = NEW.tenant_id AND a.payment_id = NEW.id
                          AND a.target = 'bill_balance') THEN
            NULL;   -- still owed; nothing to announce yet
        ELSIF v_bill IS NOT NULL THEN
            PERFORM notify.emit(NEW.tenant_id, NEW.outlet_id, 'EVT-CHECK-PAID', 'bill',
                                v_bill, NEW.correlation_id, v_session,
                                jsonb_build_object('state', 'paid'));
        END IF;
    ELSIF NEW.state = 'reversed' THEN
        PERFORM notify.emit(NEW.tenant_id, NEW.outlet_id, 'EVT-PAYMENT-REVERSED',
                            'payment', NEW.id, NEW.correlation_id, v_session,
                            jsonb_build_object('state', 'reversed'));
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER payment_is_announced
    AFTER INSERT OR UPDATE OF state ON payments.payment
    FOR EACH ROW EXECUTE FUNCTION payments.announce_payment();


CREATE FUNCTION payments.announce_reversal() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, payments, billing, ordering, service, notify, public
AS $$
DECLARE
    v_target payments.allocation_target;
    v_tip    uuid;
    v_correlation uuid;
    v_session uuid;
BEGIN
    SELECT a.target, a.tip_id, p.correlation_id INTO v_target, v_tip, v_correlation
      FROM payments.allocation a
      JOIN payments.payment p ON p.tenant_id = a.tenant_id AND p.id = a.payment_id
     WHERE a.tenant_id = NEW.tenant_id AND a.id = NEW.allocation_id;

    IF v_target <> 'tip' OR v_tip IS NULL OR v_correlation IS NULL THEN
        RETURN NULL;   -- a bill reversal is announced by payments.announce_payment()
    END IF;

    SELECT c.table_session_id INTO v_session
      FROM billing.tip t
      JOIN billing.bill_share s ON s.tenant_id = t.tenant_id AND s.id = t.bill_share_id
      JOIN billing.bill b ON b.tenant_id = s.tenant_id AND b.id = s.bill_id
      JOIN billing.check c ON c.tenant_id = b.tenant_id AND c.id = b.check_id
     WHERE t.tenant_id = NEW.tenant_id AND t.id = v_tip;

    PERFORM notify.emit(NEW.tenant_id, NEW.outlet_id, 'EVT-TIP-REFUNDED', 'tip',
                        v_tip, v_correlation, v_session,
                        jsonb_build_object('state', 'refunded'));
    RETURN NULL;
END;
$$;

CREATE TRIGGER reversal_is_announced
    AFTER INSERT ON payments.reversal
    FOR EACH ROW EXECUTE FUNCTION payments.announce_reversal();


CREATE FUNCTION payments.announce_failure() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, payments, notify, public
AS $$
BEGIN
    -- FR-PAY-012's failure, raised where the failure actually IS. A declined terminal
    -- result is the event: no payment row was ever created, because nothing was received.
    -- Emitting from the capture path instead would have meant raising a notification and
    -- then rolling it back with the exception that refused the capture — a notice about a
    -- failure that the failure itself deletes.
    IF NEW.outcome = 'declined' THEN
        PERFORM notify.emit(NEW.tenant_id, NEW.outlet_id, 'EVT-PAYMENT-FAILED', 'payment',
                            NEW.id, gen_random_uuid(), NULL,
                            jsonb_build_object('state', 'declined',
                                               'scheme', NEW.scheme));
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER terminal_failure_is_announced
    AFTER INSERT ON payments.terminal_result
    FOR EACH ROW EXECUTE FUNCTION payments.announce_failure();


-- ===========================================================================
-- FR-ORD-007B — acceptance on a verified payment outcome
-- ===========================================================================
-- 0020's refusal said: "M4-B supplies the verified outcome, and until it does an order in
-- that mode stays submitted." This is that. The refusal does not disappear — it remains
-- the answer for every payment-dependent order that has not been paid for, which is the
-- larger half of the requirement. What changes is that there is now a way through it.

CREATE OR REPLACE FUNCTION ordering.accept_order(
    p_tenant_id uuid, p_order_id uuid, p_user_id uuid
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_order  ordering.customer_order%ROWTYPE;
    v_policy jsonb;
    v_mode   text;
    v_event  bigint;
    v_acceptance text := 'staff_confirmed';
BEGIN
    SELECT * INTO v_order FROM ordering.customer_order
     WHERE id = p_order_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ORDER_NOT_FOUND: no order % in scope', p_order_id
            USING ERRCODE = 'HS404';
    END IF;
    IF v_order.state <> 'submitted' THEN
        RAISE EXCEPTION
            'ORDER_NOT_AWAITING_ACCEPTANCE: order % is %, not submitted',
            p_order_id, v_order.state USING ERRCODE = 'HS409';
    END IF;

    v_policy := ordering.require_policy(p_tenant_id, v_order.outlet_id, 'ordering');
    v_mode := v_policy -> 'acceptance' ->> v_order.origin::text;

    IF v_mode = 'payment_dependent' THEN
        -- WHAT "VERIFIED" MEANS, in one call. payments.order_is_paid() sums BILL BALANCE
        -- allocations net of reversals against the bill this order sits on, and every
        -- allocation it can see was already refused unless the payment behind it was
        -- live-typed, approved, and — for a proof-based provider — attested by a named
        -- person on their own session. So there is no second definition of verified here
        -- to drift from the first: the constraints decided, and this asks the one
        -- question they cannot, which is whether enough of it arrived.
        IF NOT payments.order_is_paid(p_tenant_id, p_order_id) THEN
            RAISE EXCEPTION
                'ACCEPTANCE_AWAITS_PAYMENT_VERIFICATION: outlet % accepts a % order only '
                'after a verified payment outcome, and the bill for order % is not '
                'settled. A tip does not settle it and a simulated result never could',
                v_order.outlet_id, v_order.origin, p_order_id
                USING ERRCODE = 'HS412';
        END IF;
        v_acceptance := 'payment_dependent';
    END IF;

    INSERT INTO ordering.order_event
        (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind, actor_user_id,
         correlation_id, after)
    VALUES (p_tenant_id, v_order.outlet_id, p_order_id,
            ordering.next_sequence(p_tenant_id, p_order_id), 'accepted', 'staff', p_user_id,
            v_order.correlation_id,
            jsonb_build_object('acceptance_mode', v_acceptance,
                               'accepted_by_user_id', p_user_id))
    RETURNING id INTO v_event;
    PERFORM ordering.apply_event(v_event);
END;
$$;

COMMENT ON FUNCTION ordering.accept_order(uuid, uuid, uuid) IS
    'FR-ORD-007A''s staff-confirmed acceptance and FR-ORD-007B''s payment-dependent one. '
    'The refusal 0020 introduced is still here and still the answer for an unpaid order; '
    'what M4-B adds is the verified outcome that gets past it. The acceptance mode is '
    'recorded on the event, so an order accepted because it was paid for is '
    'distinguishable afterwards from one a member of staff waved through.';


-- ===========================================================================
-- FR-ORD-011 — the payment dimension of the cancellation policy
-- ===========================================================================

CREATE OR REPLACE FUNCTION ordering.cancel_order(
    p_tenant_id uuid,
    p_order_id  uuid,
    p_reason_code_id uuid,
    p_actor_user_id uuid DEFAULT NULL,
    p_actor_guest_session_id uuid DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_order  ordering.customer_order%ROWTYPE;
    v_policy jsonb;
    v_allowed jsonb;
    v_event  bigint;
    v_paid   boolean;
BEGIN
    SELECT * INTO v_order FROM ordering.customer_order
     WHERE id = p_order_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ORDER_NOT_FOUND: no order % in scope', p_order_id
            USING ERRCODE = 'HS404';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM config.reason_code
                    WHERE id = p_reason_code_id AND tenant_id = p_tenant_id
                      AND category = 'order_cancellation' AND status = 'active') THEN
        RAISE EXCEPTION
            'CANCELLATION_REASON_INVALID: % is not an active order_cancellation reason '
            'code for this tenant', p_reason_code_id USING ERRCODE = 'HS400';
    END IF;

    v_policy := ordering.require_policy(p_tenant_id, v_order.outlet_id, 'cancellation');
    IF NOT (v_policy -> 'allowed_states' ? v_order.origin::text) THEN
        RAISE EXCEPTION
            'CANCELLATION_POLICY_ABSENT: the cancellation policy says nothing about a % '
            'order', v_order.origin USING ERRCODE = 'HS412';
    END IF;
    v_allowed := v_policy -> 'allowed_states' -> v_order.origin::text;

    IF NOT (v_allowed @> to_jsonb(v_order.state::text)) THEN
        RAISE EXCEPTION
            'CANCELLATION_REFUSED_BY_POLICY: a % order may be cancelled in %, and this '
            'one is %', v_order.origin, v_allowed, v_order.state USING ERRCODE = 'HS409';
    END IF;

    -- THE PAYMENT DIMENSION. FR-ORD-011 resolves cancellation by state, channel, reason,
    -- payment AND preparation progress. Four of the five have applied since M3-A; the
    -- fifth could not, because "paid" was a property no order could have. It can now.
    --
    -- A paid order is cancellable only where the policy says so explicitly. Absent
    -- permission it is refused, because cancelling an order somebody has paid for without
    -- returning the money is the failure mode, and the refund is FR-PAY-009's separate
    -- authorized act rather than a side effect of pressing cancel.
    v_paid := payments.order_is_paid(p_tenant_id, p_order_id);
    IF v_paid AND NOT coalesce((v_policy ->> 'paid_orders_cancellable')::boolean, false) THEN
        RAISE EXCEPTION
            'CANCELLATION_REFUSED_BY_POLICY: order % has been paid for, and this outlet '
            'does not permit cancelling a paid order. Refund the payment first — a '
            'reversal names who authorized it and why, and cancelling around it would '
            'leave money received against an order that no longer exists', p_order_id
            USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO ordering.order_event
        (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind, actor_user_id,
         actor_guest_session_id, correlation_id, reason_code_id, before, after)
    VALUES (p_tenant_id, v_order.outlet_id, p_order_id,
            ordering.next_sequence(p_tenant_id, p_order_id), 'cancelled',
            (CASE WHEN p_actor_user_id IS NOT NULL THEN 'staff' ELSE 'guest' END)
                ::ordering.actor_kind,
            p_actor_user_id, p_actor_guest_session_id, v_order.correlation_id,
            p_reason_code_id,
            jsonb_build_object('state', v_order.state, 'paid', v_paid),
            jsonb_build_object('state', 'cancelled'))
    RETURNING id INTO v_event;
    PERFORM ordering.apply_event(v_event);
END;
$$;

COMMENT ON FUNCTION ordering.cancel_order IS
    'FR-ORD-011, complete. State, channel, reason and preparation progress have decided '
    'since M3-A; payment joins them here, and whether the order had been paid for is '
    'recorded on the event rather than only consulted, so the decision is answerable '
    'afterwards.';


-- ===========================================================================
-- FR-ORD-012A — the unpaid precondition, now falsifiable
-- ===========================================================================

CREATE OR REPLACE FUNCTION ordering.void_order(
    p_tenant_id uuid,
    p_order_id  uuid,
    p_reason_code_id uuid,
    p_user_id   uuid
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_order ordering.customer_order%ROWTYPE;
    v_event bigint;
BEGIN
    SELECT * INTO v_order FROM ordering.customer_order
     WHERE id = p_order_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ORDER_NOT_FOUND: no order % in scope', p_order_id
            USING ERRCODE = 'HS404';
    END IF;

    PERFORM identity.authorize_action('order.void');

    IF v_order.state <> 'accepted' THEN
        RAISE EXCEPTION
            'VOID_BEFORE_ACCEPTANCE: order % is %; an order that was never accepted is '
            'cancelled, not voided', p_order_id, v_order.state USING ERRCODE = 'HS409';
    END IF;

    -- "FOR AN UNPAID ORDER", and at last a condition that can be false. At M3-A this was
    -- asserted against a registry of payment artifacts that was empty by construction —
    -- the suite said so, and the closure register recorded that it had to be re-proved
    -- when payments existed. They exist.
    IF payments.order_is_paid(p_tenant_id, p_order_id) THEN
        RAISE EXCEPTION
            'VOID_OF_PAID_ORDER: order % has been paid for. FR-ORD-012A voids an UNPAID '
            'order; money that arrived is returned by a reversal naming who authorized it '
            'and why, and a void that silently kept it would be the same act with the '
            'audit trail removed', p_order_id
            USING ERRCODE = 'HS409';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM config.reason_code
                    WHERE id = p_reason_code_id AND tenant_id = p_tenant_id
                      AND category = 'void' AND status = 'active') THEN
        RAISE EXCEPTION
            'VOID_REASON_INVALID: % is not an active void reason code for this tenant',
            p_reason_code_id USING ERRCODE = 'HS400';
    END IF;

    INSERT INTO ordering.order_event
        (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind, actor_user_id,
         correlation_id, reason_code_id, before, after)
    VALUES (p_tenant_id, v_order.outlet_id, p_order_id,
            ordering.next_sequence(p_tenant_id, p_order_id), 'voided', 'staff', p_user_id,
            v_order.correlation_id, p_reason_code_id,
            jsonb_build_object('state', v_order.state,
                               'total_amount_minor', v_order.total_amount_minor),
            jsonb_build_object('state', 'voided'))
    RETURNING id INTO v_event;
    PERFORM ordering.apply_event(v_event);

    INSERT INTO audit.operational_event
        (tenant_id, outlet_id, event_code, entity_schema, entity_table, entity_id,
         actor_id, approved_by_id, approved_at, effective_from, detail)
    VALUES (p_tenant_id, v_order.outlet_id, 'ordering.order_voided', 'ordering',
            'customer_order', p_order_id::text, p_user_id, p_user_id, now(), now(),
            jsonb_build_object('reason_code_id', p_reason_code_id,
                               'order_number', v_order.order_number,
                               'total_amount_minor', v_order.total_amount_minor));
END;
$$;

COMMENT ON FUNCTION ordering.void_order IS
    'FR-ORD-012A. Authorized void after acceptance, for an UNPAID order, with the reason '
    'and an immutable audit row. The unpaid precondition became falsifiable at M4-B and '
    'is now enforced rather than asserted against an empty set.';


-- ===========================================================================
-- Cash reaches the drawer (FR-CSH-002)
-- ===========================================================================
-- 0023 wrote payments.record_cash_payment() as a thin call to payments.capture(), and
-- said nothing about a till because 0024 did not exist yet. It does now, and a cash
-- payment that never became a movement is money the midnight count cannot explain. So the
-- capture and the movement are ONE transaction: either both happened or neither did.

-- The signature is unchanged from 0023's on purpose. Adding a shift parameter would have
-- created a second overload rather than replacing the first, and two functions of one
-- name is how a caller comes to use the version that does not post to the drawer.
CREATE OR REPLACE FUNCTION payments.record_cash_payment(
    p_tenant_id uuid, p_outlet_id uuid, p_intent_id uuid,
    p_tendered_minor money.amount_minor, p_actor_user_id uuid
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_payment uuid;
    v_shift   uuid;
BEGIN
    v_payment := payments.capture(p_tenant_id, p_outlet_id, p_intent_id, 'cash',
                                  p_tendered_minor, p_actor_user_id);

    BEGIN
        -- The live drawer this cashier is working. Absent one, the
        -- payment stands and the drawer is untouched: an outlet that takes cash without
        -- running shifts is a configuration this system does not forbid, and inventing a
        -- shift to post into would be worse than not posting.
        SELECT s.id INTO v_shift FROM cash.shift s
         WHERE s.tenant_id = p_tenant_id AND s.outlet_id = p_outlet_id
           AND s.state IN ('open', 'reopened')
           AND s.cashier_user_id = p_actor_user_id
         ORDER BY s.opened_at DESC LIMIT 1;
    END;

    IF v_shift IS NOT NULL THEN
        PERFORM cash.post_cash_payment(p_tenant_id, p_outlet_id, v_shift, v_payment);
    END IF;

    RETURN v_payment;
END;
$$;

COMMENT ON FUNCTION payments.record_cash_payment IS
    'FR-PAY-002 and FR-CSH-002 in one transaction. The drawer gains what was tendered '
    'less the change; cash.movement takes UNIQUE (payment_id), so a retry that reached '
    'here twice cannot count the same notes twice. Nothing on this path makes an outbound '
    'call, which is why cash service continues during an outage — tests/m4b derives the '
    'transitive call graph from the catalog and proves it rather than asserting it.';


-- ===========================================================================
-- FR-CFG-001C — and those settings drive a real bill
-- ===========================================================================
-- The requirement's sting is in its last clause. A guided setup that stored taxes,
-- service charges, tip settings and permitted payment methods in a form nothing read
-- would satisfy every word except the one that matters.
--
-- Three of the four already drive a bill: 0019's billing.issue_bill() reads the tax
-- configuration and the service-charge setting and computes components from them, and
-- billing.tip_options() reads the tip suggestions. The fourth arrives here. The adapter
-- registry is not filled in by hand — it is INSTALLED FROM the approved configuration
-- version of category 'payment_method', so the permitted methods on a payment intent, and
-- therefore which tenders can settle a real bill, follow what setup published.

CREATE FUNCTION payments.install_adapters_from_configuration(
    p_tenant_id uuid, p_outlet_id uuid
) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_payload jsonb;
    v_named   text[];
    v_provider payments.provider;
    v_count   integer := 0;
BEGIN
    SELECT cv.payload INTO v_payload
      FROM config.configuration_version cv
     WHERE cv.tenant_id = p_tenant_id
       AND cv.category = 'payment_method'
       AND (cv.outlet_id = p_outlet_id OR cv.outlet_id IS NULL)
       AND cv.effective_from <= now()
       AND (cv.effective_to IS NULL OR cv.effective_to > now())
     ORDER BY (cv.outlet_id IS NULL), cv.version DESC
     LIMIT 1;

    IF v_payload IS NULL THEN
        RAISE EXCEPTION
            'PAYMENT_CONFIGURATION_ABSENT: no approved payment_method configuration for '
            'this outlet. FR-CFG-001C says the guided setup decides which methods are '
            'permitted, and an empty registry means setup has not run rather than that '
            'every method is allowed' USING ERRCODE = 'HS412';
    END IF;

    SELECT array_agg(value) INTO v_named
      FROM jsonb_array_elements_text(coalesce(v_payload -> 'permitted', '[]'::jsonb));

    IF v_named IS NULL OR array_length(v_named, 1) IS NULL THEN
        RAISE EXCEPTION
            'PAYMENT_CONFIGURATION_EMPTY: the payment_method configuration permits no '
            'method, so no bill at this outlet could ever be settled'
            USING ERRCODE = 'HS422';
    END IF;

    -- Every provider the system knows gets a row. The ones setup permitted are active;
    -- the rest are present and inactive, so health can say truthfully which adapters
    -- exist and which are usable. The MODE is not read from the payload and cannot be:
    -- it is derived from the provider by CHECK, so a configuration file claiming that
    -- telebirr_direct is live changes nothing.
    FOR v_provider IN SELECT unnest(enum_range(NULL::payments.provider))
    LOOP
        INSERT INTO payments.payment_adapter
            (tenant_id, outlet_id, provider, mode, active)
        VALUES (p_tenant_id, p_outlet_id, v_provider,
                CASE WHEN v_provider IN ('cash', 'external_terminal',
                                         'telebirr_proof', 'cbe_birr_proof')
                     THEN 'live'::payments.adapter_mode ELSE 'simulated' END,
                v_provider::text = ANY (v_named))
        ON CONFLICT (tenant_id, outlet_id, provider)
            DO UPDATE SET active = EXCLUDED.active;
        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION payments.install_adapters_from_configuration(uuid, uuid) IS
    'FR-CFG-001C''s fourth setting, and the clause that makes it real. The permitted '
    'payment methods come from the approved payment_method configuration version, the '
    'adapter registry follows it, payments.create_intent() takes its permitted providers '
    'from the registry, and a bill is settled by one of them. Note what the payload '
    'cannot say: whether an adapter is simulated. That is derived from the provider by '
    'CHECK, so a configuration is not a route to NC-M4-003.';

-- THE MIGRATOR ONLY, and deliberately. The application role holds no write grant on
-- payments.payment_adapter — 0019's reasoning about configuration, applied here — so an
-- EXECUTE grant to it would be a permission that fails at the first statement. Guided
-- setup is an administrator's act, and this is the function it calls.
GRANT EXECUTE ON FUNCTION payments.install_adapters_from_configuration(uuid, uuid)
    TO hospitality_migrator;



-- ===========================================================================
-- FR-INT-013 — protocol versions, and a peer that stops safely
-- ===========================================================================
-- "Version local/cloud protocols and Phase 1 adapter messages; incompatible peers stop
-- safely instead of silently accepting unknown shapes."
--
-- The silence is the defect, not the incompatibility. A peer speaking a version this
-- system does not know is an ordinary event; accepting its message anyway, and finding
-- out later which fields it did not have, is not.

CREATE TABLE integration.protocol (
    protocol   text PRIMARY KEY,
    -- The version this system speaks, and the oldest it still understands. Two numbers
    -- rather than a list, because a range is what a compatibility claim actually is.
    current_version integer NOT NULL,
    minimum_supported_version integer NOT NULL,
    description text NOT NULL,

    CONSTRAINT protocol_name_shape CHECK (protocol ~ '^[a-z][a-z0-9_.]*$'),
    CONSTRAINT protocol_versions_positive CHECK (minimum_supported_version >= 1),
    CONSTRAINT protocol_range_is_a_range CHECK (
        current_version >= minimum_supported_version)
);

COMMENT ON TABLE integration.protocol IS
    'FR-INT-013. Which protocols this system speaks and the version range it understands '
    'for each. Only the protocols that EXIST are here: the outlet-node synchronization '
    'protocol is M5a''s and is absent rather than declared at version zero, because '
    'M1-D''s rule is that health and capability advertise what exists.';

INSERT INTO integration.protocol
    (protocol, current_version, minimum_supported_version, description) VALUES
    ('adapter.payment', 1, 1,
     'Messages exchanged with a payment adapter. Version 1 is the shape M4-B records: an '
     'outcome, an amount, a reference, and nothing resembling card data.'),
    ('api.staff', 1, 1,
     'The staff surface protocol served by this deployment.'),
    ('api.customer', 1, 1,
     'The customer surface protocol served by this deployment.');

CREATE FUNCTION integration.negotiate(
    p_protocol text, p_peer_version integer
) RETURNS integer
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    p integration.protocol%ROWTYPE;
BEGIN
    SELECT * INTO p FROM integration.protocol WHERE protocol = p_protocol;

    IF NOT FOUND THEN
        -- Fail closed. An unknown PROTOCOL is more dangerous than an unknown version,
        -- because there is nothing at all to compare against, and returning a version
        -- here would be inventing agreement.
        RAISE EXCEPTION
            'UNKNOWN_SCHEMA_ACCEPTED: % is not a protocol this system speaks. Refusing '
            'is the whole of FR-INT-013: a peer whose shape is unknown is one whose '
            'messages cannot be checked, and accepting them would move the failure from '
            'here to somewhere it looks like a data problem', p_protocol
            USING ERRCODE = 'HS505';
    END IF;

    IF p_peer_version IS NULL THEN
        RAISE EXCEPTION
            'UNKNOWN_SCHEMA_ACCEPTED: a peer offering protocol % named no version. An '
            'unversioned message is an unknown shape wearing a known name', p_protocol
            USING ERRCODE = 'HS505';
    END IF;

    IF p_peer_version < p.minimum_supported_version
       OR p_peer_version > p.current_version THEN
        RAISE EXCEPTION
            'UNKNOWN_SCHEMA_ACCEPTED: a peer offered % version %, and this system speaks '
            '% to %. Stopping here rather than reading the fields that happen to match',
            p_protocol, p_peer_version, p.minimum_supported_version, p.current_version
            USING ERRCODE = 'HS505';
    END IF;

    RETURN p_peer_version;
END;
$$;

COMMENT ON FUNCTION integration.negotiate(text, integer) IS
    'FR-INT-013. Returns the agreed version or refuses. There is no third answer and no '
    'default: an unknown protocol, an absent version and an out-of-range version all stop '
    'with the same named signature, because from the far side they are the same mistake.';


-- ===========================================================================
-- FR-INT-011 — truthful health, including the payment adapters
-- ===========================================================================
-- "Expose truthful health for the narrow Phase 1 integration surface, including outlet-
-- node connectivity, sync lag, printer status and active payment adapters."
--
-- Three of those four do not exist at this gate. M1-D's rule is that a deployment
-- advertises what it HAS and lets readiness go unhealthy when something advertised cannot
-- work — so this reports the payment adapters, which exist, and says nothing about node
-- connectivity, sync lag or printer status, which do not. The partial closure register
-- carries the entry naming M4-C and M5a. A health endpoint that reported a printer as
-- healthy because no printer existed would be the most expensive kind of true statement.

CREATE FUNCTION integration.payment_adapter_health(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (
    provider  text,
    mode      text,
    active    boolean,
    healthy   boolean,
    detail    text
)
LANGUAGE sql STABLE
AS $$
    SELECT a.provider::text,
           a.mode::text,
           a.active,
           -- An ADVERTISED adapter is healthy when it can do what advertising it implies.
           -- A live adapter that is active can take money. A simulated adapter that is
           -- active cannot — it is reachable and it settles nothing — so it reports
           -- unhealthy, and readiness follows. That is the honest answer and it is also
           -- the uncomfortable one, which is the test of whether health is truthful.
           CASE WHEN NOT a.active THEN true
                WHEN a.mode = 'live' THEN true
                ELSE false END,
           CASE WHEN NOT a.active THEN 'not advertised'
                WHEN a.mode = 'live' THEN 'live'
                ELSE 'simulated until contracted and credentialed (FR-PAY-015); it is '
                     'advertised as active and cannot settle a bill' END
      FROM payments.payment_adapter a
     WHERE a.tenant_id = p_tenant_id AND a.outlet_id = p_outlet_id
     ORDER BY a.provider;
$$;

COMMENT ON FUNCTION integration.payment_adapter_health(uuid, uuid) IS
    'FR-INT-011''s active payment adapters. Node connectivity, synchronization lag and '
    'printer status are deliberately absent: they belong to M5a and M4-C, and the partial '
    'closure register says so rather than this function reporting a healthy printer '
    'nobody has. An ACTIVE SIMULATED adapter reports unhealthy, so a deployment that '
    'advertised a direct provider would fail readiness rather than look ready.';

GRANT USAGE ON SCHEMA integration TO hospitality_app;
GRANT SELECT ON integration.protocol TO hospitality_app;
GRANT EXECUTE ON FUNCTION integration.negotiate(text, integer) TO hospitality_app;
GRANT EXECUTE ON FUNCTION integration.payment_adapter_health(uuid, uuid) TO hospitality_app;


-- ===========================================================================
-- FR-BIL-008 — a bill balance is settled by a tender, not only by a disposition
-- ===========================================================================
-- 0019's billing.outstanding_balance() subtracted authorized DISPOSITIONS and nothing
-- else, and the partial closure said why: "the settled-by-payment branch is unreachable
-- until there is a tender". There is a tender. Without this a guest could pay a bill in
-- full and still owe every birr of it, which is how the M4-B suite found this — the
-- allocation was exact, the arithmetic was right, and the balance did not move.
--
-- WHAT IT STILL DOES NOT READ IS billing.tip, AND THAT IS THE POINT. It now subtracts
-- allocations whose target is 'bill_balance', net of reversals, and there is no branch
-- by which a tip allocation could enter the sum. NC-M4-002 is the control and tests/m4a
-- derives the balance functions from the catalog and requires that none of them reads a
-- tip; this function stays inside that rule while ceasing to be blind to money.

CREATE OR REPLACE FUNCTION billing.outstanding_balance(p_tenant_id uuid, p_bill_id uuid)
RETURNS money.amount_minor
LANGUAGE sql STABLE
AS $$
    SELECT b.bill_total_minor
           - coalesce((SELECT sum(d.amount_minor)
                         FROM billing.bill_disposition d
                        WHERE d.tenant_id = b.tenant_id AND d.bill_id = b.id), 0)
           - coalesce((SELECT sum(a.amount_minor)
                         FROM payments.allocation a
                        WHERE a.tenant_id = b.tenant_id AND a.bill_id = b.id
                          AND a.target = 'bill_balance'), 0)
           + coalesce((SELECT sum(r.amount_minor)
                         FROM payments.reversal r
                         JOIN payments.allocation a
                           ON a.tenant_id = r.tenant_id AND a.id = r.allocation_id
                        WHERE a.tenant_id = b.tenant_id AND a.bill_id = b.id
                          AND a.target = 'bill_balance'), 0)
      FROM billing.bill b
     WHERE b.tenant_id = p_tenant_id AND b.id = p_bill_id;
$$;

COMMENT ON FUNCTION billing.outstanding_balance(uuid, uuid) IS
    'FR-BIL-008, complete. What is still owed: the total, less what authority disposed of, '
    'less what was actually paid to the BILL BALANCE, plus anything refunded back. IT '
    'STILL DOES NOT READ billing.tip AND MUST NOT — a tip that made a balance look '
    'settled is NC-M4-002, and every allocation it can see was refused unless the payment '
    'behind it was live, approved and, for a proof provider, attested by a named person.';


-- ===========================================================================
-- The circularity FR-ORD-007B creates, and the one place it may be opened
-- ===========================================================================
-- 0019 refused to allocate a submitted order to a check, and gave the reason: "a
-- submitted order has not been agreed to by the house yet, and billing for something
-- nobody accepted is the commercial equivalent of cooking it before it was ordered."
-- That is right for every channel M3 had.
--
-- FR-ORD-007B makes it circular. An order in payment_dependent mode is accepted ONLY
-- after a verified payment outcome; a payment is against a bill; a bill is issued from a
-- check; and a check could not be opened over an order that was not accepted. Nothing
-- could ever be paid for, so nothing could ever be accepted. The M4-B suite found this by
-- walking the requirement end to end rather than by testing the pieces.
--
-- The opening is exactly as wide as the requirement and no wider: a SUBMITTED order may
-- be allocated when its outlet's policy makes that order's origin payment-dependent —
-- which is to say, when the house has said in advance that it agrees to this order once
-- the money arrives. The policy IS the agreement, given ahead of time; that is what
-- prepayment means. For every other mode 0019's refusal stands unchanged, and the same
-- policy is read the same way ordering.accept_order() reads it, because two readings of
-- one policy is how a channel diverges without anybody deciding that it should.

CREATE OR REPLACE FUNCTION billing.allocate_to_check(
    p_tenant_id uuid, p_outlet_id uuid, p_check_id uuid,
    p_order_line_id uuid, p_quantity integer DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_line  ordering.order_line%ROWTYPE;
    v_order ordering.customer_order%ROWTYPE;
    v_mode  text;
    v_id    uuid;
BEGIN
    SELECT * INTO v_line FROM ordering.order_line
     WHERE tenant_id = p_tenant_id AND id = p_order_line_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ALLOCATION_LINE_UNKNOWN: no order line % in scope', p_order_line_id
            USING ERRCODE = 'HS404';
    END IF;

    SELECT * INTO v_order FROM ordering.customer_order
     WHERE tenant_id = p_tenant_id AND id = v_line.order_id;

    IF v_order.state <> 'accepted' THEN
        v_mode := ordering.require_policy(p_tenant_id, v_order.outlet_id, 'ordering')
                  -> 'acceptance' ->> v_order.origin::text;

        IF NOT (v_order.state = 'submitted' AND v_mode = 'payment_dependent') THEN
            RAISE EXCEPTION
                'ALLOCATION_ORDER_NOT_BILLABLE: order % is %; a check is created from '
                'accepted or served lines, or from a submitted order whose outlet accepts '
                'that origin only on a verified payment', v_order.id, v_order.state
                USING ERRCODE = 'HS409';
        END IF;
    END IF;

    INSERT INTO billing.check_allocation
        (tenant_id, outlet_id, check_id, order_id, order_line_id, quantity)
    VALUES (p_tenant_id, p_outlet_id, p_check_id, v_line.order_id, p_order_line_id,
            coalesce(p_quantity, v_line.quantity))
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION billing.allocate_to_check IS
    'FR-BIL-001 and FR-ORD-007B together. A check is allocated from accepted lines — and '
    'from a SUBMITTED order at an outlet whose policy accepts that origin only on a '
    'verified payment, because otherwise nothing in that mode could ever be paid for and '
    'therefore nothing could ever be accepted. The policy is the house agreeing in '
    'advance, which is what prepayment is.';
