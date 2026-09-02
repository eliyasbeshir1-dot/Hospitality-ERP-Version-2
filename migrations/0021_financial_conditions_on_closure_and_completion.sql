-- =============================================================================
-- 0021 — The financial half of two conditions that have waited since M3
-- =============================================================================
-- Two entries in the partial-closure register have named M4 since M3-A, and both say the
-- same thing: the operational half of a condition was provable then and the FINANCIAL
-- half was not, because there were no checks and no bills. There are now.
--
-- FR-TAB-009 — a session closes only when nothing is outstanding, or an authorized
-- exception is recorded with a reason and an account. At M3-A "outstanding" could only
-- mean an order nobody had accepted. It also means a bill nobody has settled, and a table
-- closed over an unpaid bill is money walking out of the door with a clean screen behind
-- it.
--
-- SM-ORDER — the state machine's last edge is served -> completed on operational AND
-- FINANCIAL conditions. M3-B derived every other label from the tickets and recorded that
-- the last one needed checks. This is that edge: an order is completed when every unit of
-- it has been served AND every unit of it is on a bill that has been finalized.
--
-- BOTH ARE REPLACEMENTS, NOT EDITS. 0010 and 0012 are applied and checksum-locked, and
-- CREATE OR REPLACE is the route every correction since M2-B has taken.
--
-- The dependency direction is worth stating: service and fulfillment now read billing,
-- which arrived after them. That is the right way round — the money is the later fact and
-- the earlier schemas ASK it rather than being told — but it does mean these two
-- functions cannot be created before migration 0019, which is why they are here rather
-- than there.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- FR-TAB-009: an unsettled bill is an outstanding obligation
-- ---------------------------------------------------------------------------

-- Recorded separately from the order count rather than added to it. "Three orders nobody
-- accepted" and "one bill nobody paid" are different facts about why a table was closed
-- early, and a single number would make the exception record unable to say which.
ALTER TABLE service.session_closure_exception
    ADD COLUMN IF NOT EXISTS unsettled_bills integer NOT NULL DEFAULT 0;

COMMENT ON COLUMN service.session_closure_exception.unsettled_bills IS
    'FR-TAB-009''s financial condition: how many live bills on this occupancy still owed '
    'money when it was closed over an exception. Separate from outstanding_orders because '
    'they are different reasons and a manager reading the record needs to know which.';

CREATE OR REPLACE FUNCTION service.close_table_session(
    p_tenant_id uuid,
    p_session_id uuid,
    p_user_id uuid,
    p_exception_reason_code_id uuid DEFAULT NULL,
    p_exception_note text DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_session     service.table_session%ROWTYPE;
    v_outstanding integer;
    v_unsettled   integer;
BEGIN
    SELECT * INTO v_session FROM service.table_session
     WHERE id = p_session_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SESSION_NOT_FOUND: no occupancy % in scope', p_session_id
            USING ERRCODE = 'HS404';
    END IF;
    IF v_session.state <> 'open' THEN
        RAISE EXCEPTION 'SESSION_ALREADY_CLOSED: occupancy % is already closed',
            p_session_id USING ERRCODE = 'HS409';
    END IF;

    -- The COMMERCIAL condition, unchanged from M3-A: an order neither resolved nor
    -- accepted-and-served.
    SELECT count(*) INTO v_outstanding FROM ordering.customer_order
     WHERE tenant_id = p_tenant_id AND table_session_id = p_session_id
       AND state = 'submitted';

    -- The FINANCIAL condition, which is what this migration adds. A bill that has been
    -- issued and still owes money is an outstanding obligation whatever the orders say,
    -- and billing.outstanding_balance() is the one function that decides what is owed —
    -- so this inherits its one relevant property: it does not read a tip.
    SELECT count(*) INTO v_unsettled
      FROM billing.bill b
      JOIN billing.check c ON c.tenant_id = b.tenant_id AND c.id = b.check_id
     WHERE b.tenant_id = p_tenant_id
       AND c.table_session_id = p_session_id
       AND b.state IN ('issued', 'reissued')
       AND billing.outstanding_balance(b.tenant_id, b.id) > 0;

    IF v_outstanding > 0 OR v_unsettled > 0 THEN
        IF p_exception_reason_code_id IS NULL THEN
            RAISE EXCEPTION
                'SESSION_HAS_OUTSTANDING_ORDERS: occupancy % has % order(s) awaiting '
                'acceptance and % unsettled bill(s); closing needs an authorized '
                'exception on the record',
                p_session_id, v_outstanding, v_unsettled USING ERRCODE = 'HS409';
        END IF;

        PERFORM identity.authorize_action('session.close_with_exception');

        IF p_exception_note IS NULL OR btrim(p_exception_note) = '' THEN
            RAISE EXCEPTION
                'CLOSURE_EXCEPTION_UNEXPLAINED: an exception names a reason code AND says '
                'what happened; a code alone is a category, not an account'
                USING ERRCODE = 'HS400';
        END IF;

        INSERT INTO service.session_closure_exception
            (tenant_id, outlet_id, table_session_id, reason_code_id,
             authorized_by_user_id, outstanding_orders, unsettled_bills, note)
        VALUES (p_tenant_id, v_session.outlet_id, p_session_id,
                p_exception_reason_code_id, p_user_id, v_outstanding, v_unsettled,
                p_exception_note);
    END IF;

    UPDATE service.table_session
       SET state = 'closed', closed_at = now()
     WHERE id = p_session_id AND tenant_id = p_tenant_id;
END;
$$;

COMMENT ON FUNCTION service.close_table_session(uuid, uuid, uuid, uuid, text) IS
    'FR-TAB-009. A table closes when nothing is outstanding — no order awaiting '
    'acceptance AND no bill still owing — or when somebody with the authority to say so '
    'records an exception naming a reason code and what actually happened. The financial '
    'half arrived at M4-A with the bills; the register carried the entry from M3-A.';


-- ---------------------------------------------------------------------------
-- SM-ORDER's last edge: served -> completed
-- ---------------------------------------------------------------------------
-- Every other label this function returns is derived from the tickets and nothing else,
-- which is M3-B's recorded decision: no fulfillment label has a second home on the
-- commercial order where it could contradict the first. 'completed' is derived the same
-- way and simply has one more input.
--
-- The financial condition is stated exactly: every UNIT of the order is allocated to a
-- check whose bill has been FINALIZED. Not "a bill exists", which would call an unpaid
-- order complete; not "the session owes nothing", which would call an order complete
-- because a different party at the same table settled up.

CREATE OR REPLACE FUNCTION fulfillment.order_fulfillment_state(
    p_tenant_id uuid, p_order_id uuid)
RETURNS text
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_total    integer;
    v_live     integer;
    v_ready    integer;
    v_collected integer;
    v_served   integer;
    v_progress integer;
    v_unbilled integer;
BEGIN
    SELECT count(*) FILTER (WHERE state <> 'cancelled'),
           count(*) FILTER (WHERE state IN ('queued', 'acknowledged', 'held', 'preparing',
                                            'partially_completed', 'rework', 'exception')),
           count(*) FILTER (WHERE state IN ('ready', 'collected')),
           count(*) FILTER (WHERE state = 'collected'),
           count(*) FILTER (WHERE state = 'completed')
      INTO v_total, v_live, v_ready, v_collected, v_served
      FROM fulfillment.ticket
     WHERE tenant_id = p_tenant_id AND order_id = p_order_id;

    IF v_total IS NULL OR v_total = 0 THEN
        RETURN 'not_released';
    END IF;

    IF v_served = v_total THEN
        -- SM-ORDER's served -> completed edge, on operational AND financial conditions.
        -- Counted as the units NOT yet on a finalized bill, so an order that is half
        -- billed reads as served rather than as complete.
        SELECT count(*) INTO v_unbilled
          FROM ordering.order_line l
         WHERE l.tenant_id = p_tenant_id AND l.order_id = p_order_id
           AND coalesce((SELECT sum(a.quantity)
                           FROM billing.check_allocation a
                           JOIN billing.bill b
                             ON b.tenant_id = a.tenant_id AND b.check_id = a.check_id
                          WHERE a.tenant_id = l.tenant_id
                            AND a.order_line_id = l.id
                            AND b.state = 'finalized'), 0) < l.quantity;
        IF v_unbilled = 0 THEN RETURN 'completed'; END IF;
        RETURN 'served';
    END IF;
    IF v_served > 0 THEN RETURN 'partially_served'; END IF;
    IF v_ready = v_total THEN RETURN 'ready'; END IF;
    IF v_ready > 0 THEN RETURN 'partially_ready'; END IF;

    SELECT count(*) INTO v_progress
      FROM fulfillment.ticket_line tl
      JOIN fulfillment.ticket t ON t.id = tl.ticket_id
     WHERE t.tenant_id = p_tenant_id AND t.order_id = p_order_id
       AND tl.ready_quantity > 0;
    IF v_progress > 0 THEN RETURN 'partially_ready'; END IF;

    RETURN 'in_fulfillment';
END;
$$;

COMMENT ON FUNCTION fulfillment.order_fulfillment_state(uuid, uuid) IS
    'SM-ORDER, derived rather than stored. Every label the machine names is computed from '
    'the order''s tickets, and the last edge — served to completed — adds the financial '
    'condition the machine states: every unit served AND every unit on a finalized bill. '
    'No fulfillment label has a home on the commercial order where it could contradict '
    'this, which is the divergence M3-B recorded and this keeps.';
