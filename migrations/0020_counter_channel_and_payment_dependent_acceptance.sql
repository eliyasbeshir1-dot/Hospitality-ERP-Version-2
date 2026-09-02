-- =============================================================================
-- 0020 — The counter on the same aggregate, and acceptance that waits for a payment
-- =============================================================================
-- FR-ORD-001B: the counter POS channel uses the SAME AGGREGATE AND POLICY MODEL as the
-- dine-in channels, with no divergent order path. FR-ORD-007B: an order configured for
-- payment-dependent acceptance is accepted only after a verified payment outcome.
--
-- WHAT A COUNTER ORDER IS HERE, STATED RATHER THAN INFERRED.
--
-- A counter order is an order whose ORIGIN is 'counter'. It is placed by a member of
-- staff, priced from the same publication snapshot, submitted through
-- ordering.submit_order(), accepted under the same outlet policy, folded by the same
-- ordering.apply_event(), fulfilled by the same tickets and billed by the same check.
-- It sits on a table session like every other order, because service.cart requires one
-- and because a counter IS a service point — an org node a party stands at rather than
-- sits at. Giving the counter its own sessionless path would have been the divergence
-- the requirement forbids, and it would have cost a second cart, a second preview and a
-- second set of rules to keep in step.
--
-- SO ALMOST NOTHING IS ADDED HERE, AND THAT IS THE EVIDENCE.
--
-- ordering.submit_order() needs no change: it already resolves the acceptance mode from
-- the policy by origin name, and already derives the actor kind as staff for every
-- origin that is not the guest's own device. The one thing that stood in the way was a
-- CHECK constraint written when the dimension had two values, which is replaced below
-- with the same rule stated over three.
--
-- tests/m4a extends M3-D's catalog-derived differential from two channels to three
-- rather than writing a second instrument: the same 98 rule functions, the same one
-- name per operation, the same identical-refusal-code census, now over the counter as
-- well. A second differential written for the counter would agree with the first
-- because the same person wrote both, which is exactly what NC-M3D's planted duplicate
-- exists to disprove.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Whoever placed it is named, in terms that match how it was placed
-- ---------------------------------------------------------------------------
-- 0010's constraint enumerated two origins. A counter order is placed by a member of
-- staff — the same shape as a waiter-entered one — so the rule is unchanged and only its
-- statement widens. Dropped and re-added rather than edited in place: 0010 is applied and
-- checksum-locked, and forward-only DDL is how every correction since M2-B has landed.

ALTER TABLE ordering.customer_order
    DROP CONSTRAINT customer_order_origin_consistent;

ALTER TABLE ordering.customer_order
    ADD CONSTRAINT customer_order_origin_consistent CHECK (
        (origin = 'guest_qr'
         AND placed_by_guest_session_id IS NOT NULL AND placed_by_user_id IS NULL)
     OR (origin IN ('waiter_entered', 'counter')
         AND placed_by_user_id IS NOT NULL AND placed_by_guest_session_id IS NULL));


-- ---------------------------------------------------------------------------
-- Acceptance that waits for a verified payment (FR-ORD-007B)
-- ---------------------------------------------------------------------------
-- WHAT THIS DOES AND WHAT IT DELIBERATELY DOES NOT DO.
--
-- It refuses. An order whose outlet policy makes its origin payment-dependent cannot be
-- accepted by a member of staff pressing a button, because the requirement says the
-- acceptance follows a VERIFIED PAYMENT OUTCOME and this gate has no payments and no
-- verification. Both are M4-B's, and the closure register carries the entry.
--
-- Refusing is the correct behaviour of the finished system too, not a placeholder: when
-- M4-B arrives it supplies a verified outcome and a path that consults it, and this
-- refusal remains the answer for everyone who has not got one. What would NOT be correct
-- is accepting such an order today — that is the requirement inverted, and it would be
-- invisible because nothing yet exists to contradict it.
--
-- ordering.submit_order() needs no change for the same reason: it auto-accepts only when
-- the mode is 'automatic', so a payment-dependent order already stays submitted. The
-- fail-closed behaviour is a property of the code that was already there; what was
-- missing was a NAME for the refusal on the staff path, and a name is what makes a
-- control able to assert the reason rather than the failure.

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

    -- The SAME policy, read the SAME way submit_order reads it. Two readings of one
    -- policy is how a channel comes to diverge without anybody deciding that it should.
    v_policy := ordering.require_policy(p_tenant_id, v_order.outlet_id, 'ordering');
    v_mode := v_policy -> 'acceptance' ->> v_order.origin::text;

    IF v_mode = 'payment_dependent' THEN
        RAISE EXCEPTION
            'ACCEPTANCE_AWAITS_PAYMENT_VERIFICATION: outlet % accepts a % order only '
            'after a verified payment outcome, and order % has none. Nothing in this '
            'system can verify one yet',
            v_order.outlet_id, v_order.origin, p_order_id
            USING ERRCODE = 'HS412';
    END IF;

    INSERT INTO ordering.order_event
        (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind, actor_user_id,
         correlation_id, after)
    VALUES (p_tenant_id, v_order.outlet_id, p_order_id,
            ordering.next_sequence(p_tenant_id, p_order_id), 'accepted', 'staff', p_user_id,
            v_order.correlation_id,
            jsonb_build_object('acceptance_mode', 'staff_confirmed',
                               'accepted_by_user_id', p_user_id))
    RETURNING id INTO v_event;
    PERFORM ordering.apply_event(v_event);
END;
$$;

COMMENT ON FUNCTION ordering.accept_order(uuid, uuid, uuid) IS
    'FR-ORD-007A''s staff-confirmed acceptance, and FR-ORD-007B''s refusal to accept '
    'without one. The payment-dependent branch fails closed and names why: M4-B supplies '
    'the verified outcome, and until it does an order in that mode stays submitted.';
