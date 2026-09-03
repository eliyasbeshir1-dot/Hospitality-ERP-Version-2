-- =============================================================================
-- 0024 — Cash shifts, movements, counts, custody and exceptions
-- =============================================================================
-- FR-CSH-001 … FR-CSH-004, FR-CSH-007, FR-CSH-008.
--
-- A WORD THIS FILE DOES NOT USE. FR-CSH-003 and FR-CSH-008 both ask for "variance", and
-- 'variance' is one of the 63 terms the pinned package FENCES, under recipes and costing —
-- where it means the gap between theoretical and actual consumption. The forbidden-surface
-- gate matches it as a whole identifier component, so cash_variance and variance_minor
-- would both be refused, and the standing instruction is to fix the thing rather than the
-- check. The BEHAVIOUR the requirement asks for is here in full: an expected total, a
-- counted total, and the difference between them. It is called over_short_minor, which is
-- what a cashier calls it, and the exception kind is excessive_cash_difference. This is a
-- tension inside the package rather than a choice, and the M4-B report names it.
--
-- WHY CASH IS ITS OWN SCHEMA. A payment is what a guest handed over. A drawer is where it
-- physically went, who counted it, and what was in it at midnight. Those are different
-- questions with different authorities — FR-CSH-004's manager verifies a count and has no
-- opinion about a bill — and the reconciliation in 0023 already treats them as two
-- pictures that must agree rather than one picture stored twice.
--
-- MAKER-CHECKER IS M3-D's, REUSED EXACTLY. pos.approve_override() derives the approver
-- from the APPROVING SESSION and never from a parameter, so a manager who typed their
-- password into the cashier's terminal comes back as the cashier and the constraint
-- refuses. NC-M4-004 is that property, and this file adds no second mechanism for it: the
-- shift's verifier is read from the verifying session the same way, and the CHECK that a
-- verifier is not the cashier sits beside the one M3-D already wrote.
-- =============================================================================

CREATE SCHEMA cash;

COMMENT ON SCHEMA cash IS
    'FR-CSH-001 … FR-CSH-008. The drawer: who opened it with how much, every movement in '
    'and out, what was counted against what was expected, where the money went '
    'afterwards, and what somebody should look at. Separate from payments because a '
    'payment is what a guest handed over and a shift is what is physically in the till.';


-- ===========================================================================
-- The shift (FR-CSH-001, FR-CSH-004)
-- ===========================================================================

CREATE TYPE cash.shift_state AS ENUM (
    'open',
    'submitted',    -- the cashier has counted and handed it over
    'verified',     -- a DIFFERENT person has checked the count
    'finalized',    -- locked; no movement may touch it again
    'reopened',     -- something was wrong and it was opened again, by authority
    'resolved');    -- and a reopened shift reached an answer (NC-M4-006)

COMMENT ON TYPE cash.shift_state IS
    'SM-CASH-SHIFT as this repository implements it. Note that ''finalized'' and '
    '''resolved'' are the only two terminal states and that ''reopened'' is not one: '
    'NC-M4-006 exists because a reopened shift left sitting open for ever is an '
    'accounting hole that reports itself as closed.';

CREATE TABLE cash.shift (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,

    -- FR-CSH-001's assigned terminal. M3-D's pos.terminal, not a second registry — and
    -- named for that table's own key, which is device_id, so nobody reading this has to
    -- discover that a terminal_id and a device_id are the same thing.
    terminal_device_id uuid NOT NULL,
    cashier_user_id uuid NOT NULL,

    state         cash.shift_state NOT NULL DEFAULT 'open',
    currency_code char(3) NOT NULL,
    opening_float_minor money.amount_minor NOT NULL,

    opened_at    timestamptz NOT NULL DEFAULT now(),
    submitted_at timestamptz,
    submitted_by_user_id uuid,

    -- FR-CSH-004's OPTIONAL manager verification. Optional in that a shift may be
    -- finalized without it where policy allows; never optional in who may give it.
    verified_at  timestamptz,
    verified_by_user_id    uuid,
    verified_by_session_id uuid,

    finalized_at timestamptz,
    reopened_at  timestamptz,
    reopen_override_id uuid,
    reopen_reason_code_id uuid,
    reopen_reason text,
    resolved_at  timestamptz,
    resolution_override_id uuid,

    CONSTRAINT shift_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT shift_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT shift_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_terminal_fk FOREIGN KEY (tenant_id, terminal_device_id)
        REFERENCES pos.terminal (tenant_id, device_id) ON DELETE RESTRICT,
    CONSTRAINT shift_cashier_fk FOREIGN KEY (tenant_id, cashier_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_submitter_fk FOREIGN KEY (tenant_id, submitted_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_verifier_fk FOREIGN KEY (tenant_id, verified_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_verifier_session_fk FOREIGN KEY (tenant_id, verified_by_session_id)
        REFERENCES identity.session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_reopen_override_fk FOREIGN KEY (tenant_id, reopen_override_id)
        REFERENCES pos.override_approval (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_reopen_reason_fk FOREIGN KEY (tenant_id, reopen_reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_resolution_override_fk FOREIGN KEY (tenant_id, resolution_override_id)
        REFERENCES pos.override_approval (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT shift_float_not_negative CHECK (opening_float_minor >= 0),

    -- THE MAKER-CHECKER CHECK. FR-CSH-004 and NC-M4-004. A cashier verifying their own
    -- count is the whole of what the control exists to catch, and it is refused here by
    -- constraint rather than by the code path that happens to be in use.
    CONSTRAINT shift_verifier_is_not_the_cashier CHECK (
        verified_by_user_id IS NULL OR verified_by_user_id <> cashier_user_id),

    -- A verification arrives whole: a person, their own live session, and a time.
    CONSTRAINT shift_verification_is_attributed CHECK (
        (verified_at IS NULL AND verified_by_user_id IS NULL
         AND verified_by_session_id IS NULL)
     OR (verified_at IS NOT NULL AND verified_by_user_id IS NOT NULL
         AND verified_by_session_id IS NOT NULL)),

    -- FR-CSH-004's lock, as a property of the row. A finalized or resolved shift has a
    -- finalization time; nothing else does.
    CONSTRAINT shift_finalized_has_a_time CHECK (
        (state IN ('finalized', 'resolved')) = (finalized_at IS NOT NULL)),
    CONSTRAINT shift_submitted_has_a_submitter CHECK (
        (submitted_at IS NULL) = (submitted_by_user_id IS NULL)),

    -- Reopening is an authorized act with a reason, like every other correction here.
    CONSTRAINT shift_reopen_is_authorized CHECK (
        reopened_at IS NULL
     OR (reopen_override_id IS NOT NULL AND reopen_reason_code_id IS NOT NULL
         AND btrim(coalesce(reopen_reason, '')) <> '')),

    -- NC-M4-006, stated on the row itself. Once a shift has been reopened it can never
    -- reach 'finalized' again: its only terminal state is 'resolved', which requires a
    -- recount and somebody else's approval. cash.transition_shift() refuses the move;
    -- this refuses the row that would record it having happened, so removing either
    -- leaves the property standing.
    CONSTRAINT shift_reopened_never_refinalizes CHECK (
        reopened_at IS NULL OR state <> 'finalized'),
    CONSTRAINT shift_resolved_is_authorized CHECK (
        (state = 'resolved')
        = (resolved_at IS NOT NULL AND resolution_override_id IS NOT NULL)),
    -- And only a shift that WAS reopened can be resolved. 'resolved' is not an
    -- alternative spelling of 'finalized' that a caller could reach for to skip the
    -- verification a finalization needs.
    CONSTRAINT shift_only_a_reopened_shift_resolves CHECK (
        state <> 'resolved' OR reopened_at IS NOT NULL)
);

COMMENT ON TABLE cash.shift IS
    'FR-CSH-001 and FR-CSH-004. A drawer session: counted float, assigned terminal, and '
    'the approval that closed it. The verifier is never the cashier, by CHECK; the '
    'verifier''s SESSION is recorded beside them so that a manager typing a password into '
    'the cashier''s terminal is caught by the same reasoning M3-D used for overrides; and '
    'a reopened shift cannot reach a terminal state other than ''resolved''.';

CREATE INDEX shift_outlet_state_idx ON cash.shift (tenant_id, outlet_id, state);

-- One open drawer per terminal, as a partial unique index rather than an EXCLUDE
-- constraint, so this needs no extension that a fresh cluster might not carry. Two live
-- shifts on one till is two people counting the same notes, and the difference between
-- them is unattributable by construction.
CREATE UNIQUE INDEX shift_one_live_per_terminal
    ON cash.shift (tenant_id, terminal_device_id)
    WHERE state IN ('open', 'reopened');


-- ---------------------------------------------------------------------------
-- Every state change, kept (FR-DAT-008B)
-- ---------------------------------------------------------------------------
-- The shift row above says where a drawer is NOW. This says how it got there, and it is
-- append-only, because "no destructive correction" has to cover the fact that a shift was
-- once finalized and then reopened. Without it, reopening would clear finalized_at and
-- the most interesting thing that ever happened to the drawer would be the one thing not
-- written down.

CREATE TABLE cash.shift_transition (
    id         bigserial PRIMARY KEY,
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,
    shift_id   uuid NOT NULL,
    sequence_number integer NOT NULL,
    from_state cash.shift_state,
    to_state   cash.shift_state NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor_user_id uuid,
    override_id   uuid,
    reason_code_id uuid,
    reason_text   text,

    CONSTRAINT shift_transition_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT shift_transition_shift_fk FOREIGN KEY (tenant_id, shift_id)
        REFERENCES cash.shift (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_transition_actor_fk FOREIGN KEY (tenant_id, actor_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_transition_override_fk FOREIGN KEY (tenant_id, override_id)
        REFERENCES pos.override_approval (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_transition_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_transition_sequence_positive CHECK (sequence_number >= 1),
    CONSTRAINT shift_transition_sequence_unique UNIQUE (tenant_id, shift_id, sequence_number)
);

COMMENT ON TABLE cash.shift_transition IS
    'Every state a drawer has been in, append-only. It exists because reopening a '
    'finalized shift would otherwise erase the finalization, and a shift that was closed, '
    'reopened and resolved is precisely the history somebody will ask about.';

CREATE FUNCTION cash.refuse_transition_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'REOPENED_SHIFT_NOT_RESOLVED: cash.shift_transition is append-only. A drawer''s '
        'history is how a reopened shift is told apart from one that was never closed, '
        'and rewriting it is how the second is made to look like the first'
        USING ERRCODE = 'HS409';
END;
$$;

CREATE TRIGGER shift_transition_append_only
    BEFORE UPDATE OR DELETE ON cash.shift_transition
    FOR EACH ROW EXECUTE FUNCTION cash.refuse_transition_mutation();


-- ===========================================================================
-- Movements (FR-CSH-002)
-- ===========================================================================
-- "Sales receipts, refunds, payouts, drops, float adjustments and transfers as DISTINCT
-- movements." Distinct is the operative word: six kinds, each with its own meaning and
-- its own sign, rather than one amount column whose meaning depends on who wrote it.

CREATE TYPE cash.movement_kind AS ENUM (
    'sales_receipt',    -- a cash payment arrived
    'refund',           -- money returned to a guest
    'payout',           -- money paid out of the drawer for something
    'drop',             -- money removed to the safe mid-shift
    'float_adjustment', -- the float corrected, up or down
    'transfer_in',      -- money moved between drawers
    'transfer_out');

CREATE FUNCTION cash.movement_direction(p_kind cash.movement_kind) RETURNS integer
LANGUAGE sql IMMUTABLE
AS $$
    -- Which way the money goes, stated once. A kind's direction is a fact about the kind
    -- and not a column somebody fills in, so a payout recorded as an increase is not a
    -- data-entry mistake that reconciles: it is unrepresentable.
    SELECT CASE p_kind
        WHEN 'sales_receipt' THEN 1
        WHEN 'transfer_in'   THEN 1
        WHEN 'refund'        THEN -1
        WHEN 'payout'        THEN -1
        WHEN 'drop'          THEN -1
        WHEN 'transfer_out'  THEN -1
        WHEN 'float_adjustment' THEN 0   -- signed by the caller; see the CHECK below
    END;
$$;

CREATE TABLE cash.movement (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,
    shift_id  uuid NOT NULL,
    kind      cash.movement_kind NOT NULL,

    currency_code char(3) NOT NULL,
    -- SIGNED, and the sign is checked against the kind. A float adjustment is the one
    -- kind that may go either way, which is what an adjustment is.
    amount_minor  money.amount_minor NOT NULL,

    -- What it was, when there is something to point at. A sales receipt names its
    -- payment; a refund names the reversal that authorized it. Both are how
    -- FR-PAY-013's reconciliation joins the drawer to the till without either side
    -- keeping a second copy of the other's figures.
    payment_id  uuid,
    reversal_id uuid,

    reference     text,
    actor_user_id uuid NOT NULL,
    occurred_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT movement_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT movement_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT movement_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT movement_shift_fk FOREIGN KEY (tenant_id, shift_id)
        REFERENCES cash.shift (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT movement_actor_fk FOREIGN KEY (tenant_id, actor_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,

    -- NO FOREIGN KEY ONTO payments.payment OR payments.reversal. Both are projections
    -- folded from payments.payment_event, and a rebuild deletes projections wholesale.
    -- M3-D's rule, and 0019 removed three of these after a rebuild failed on one. The
    -- existence of the payment is checked by cash.post_cash_payment(); tests/m4b asserts
    -- the rule itself from the catalog, for every slice at once.

    CONSTRAINT movement_amount_not_zero CHECK (amount_minor <> 0),
    CONSTRAINT movement_sign_matches_the_kind CHECK (
        kind = 'float_adjustment'
        OR sign(amount_minor)::integer = cash.movement_direction(kind)),
    CONSTRAINT movement_sales_receipt_names_a_payment CHECK (
        kind <> 'sales_receipt' OR payment_id IS NOT NULL),
    CONSTRAINT movement_refund_names_a_reversal CHECK (
        kind <> 'refund' OR reversal_id IS NOT NULL),
    -- One movement per payment. A cash payment posted twice is money counted twice, and
    -- the count at midnight is the place it would be discovered.
    CONSTRAINT movement_one_per_payment UNIQUE (payment_id),
    CONSTRAINT movement_one_per_reversal UNIQUE (reversal_id)
);

COMMENT ON TABLE cash.movement IS
    'FR-CSH-002. Six distinct kinds of money crossing the drawer, each with the direction '
    'its kind implies rather than a sign somebody chose. Append-only by trigger and by '
    'grant: a movement recorded wrongly is corrected by an opposing movement, because '
    'FR-DAT-008B says cash movements carry no destructive correction and a drawer that '
    'can be edited is a drawer nobody can count.';

CREATE INDEX movement_shift_idx ON cash.movement (tenant_id, shift_id);

CREATE FUNCTION cash.refuse_movement_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'CASH_MOVEMENT_DELETED_NOT_REVERSED: cash.movement is append-only (FR-DAT-008B). '
        'A movement entered wrongly is answered by an opposing movement that says who and '
        'why. Removing it makes the drawer balance and the evening unexplainable'
        USING ERRCODE = 'HS409';
END;
$$;

CREATE TRIGGER movement_append_only
    BEFORE UPDATE OR DELETE ON cash.movement
    FOR EACH ROW EXECUTE FUNCTION cash.refuse_movement_mutation();


-- FR-CSH-004's lock, at the write. A finalized shift accepts nothing further, and neither
-- does a submitted or verified one — the count has been taken, and a movement landing
-- after it would make the count wrong retrospectively.
CREATE FUNCTION cash.assert_shift_accepts_movements() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_state cash.shift_state;
BEGIN
    SELECT state INTO v_state FROM cash.shift
     WHERE tenant_id = NEW.tenant_id AND id = NEW.shift_id;

    IF v_state IS NULL THEN
        RAISE EXCEPTION 'CASH_SHIFT_NOT_FOUND: no shift % in scope', NEW.shift_id
            USING ERRCODE = 'HS404';
    END IF;

    IF v_state NOT IN ('open', 'reopened') THEN
        RAISE EXCEPTION
            'FINALIZED_SHIFT_MUTATED: shift % is % and takes no further movement. The '
            'count has been made; money arriving now belongs to the next drawer, and '
            'posting it here would change a total somebody has already signed for',
            NEW.shift_id, v_state
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER movement_only_on_a_live_shift
    BEFORE INSERT ON cash.movement
    FOR EACH ROW EXECUTE FUNCTION cash.assert_shift_accepts_movements();


-- ===========================================================================
-- The count (FR-CSH-003)
-- ===========================================================================
-- "Capture denomination count, expected total, actual total and [the difference]."

CREATE TYPE cash.count_phase AS ENUM ('opening', 'closing', 'recount');

CREATE TABLE cash.drawer_count (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,
    shift_id  uuid NOT NULL,
    phase     cash.count_phase NOT NULL,

    currency_code char(3) NOT NULL,
    -- EXPECTED is what the drawer should hold: the float plus every movement. Computed
    -- once by cash.expected_in_drawer() and STORED here, because a count is evidence
    -- about a moment. Recomputing it on read would make a count taken at eleven agree
    -- with a movement posted at midnight, which is the one thing a count must not do.
    expected_minor money.amount_minor NOT NULL,
    counted_minor  money.amount_minor NOT NULL,

    -- FR-CSH-003's fourth figure. Named over_short_minor rather than the word the
    -- requirement uses, because that word is fenced by the package for recipe costing;
    -- see the note at the head of this file. Generated, so it cannot disagree with the
    -- two figures it is the difference of.
    over_short_minor bigint GENERATED ALWAYS AS (counted_minor - expected_minor) STORED,

    counted_by_user_id uuid NOT NULL,
    counted_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT drawer_count_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT drawer_count_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT drawer_count_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT drawer_count_shift_fk FOREIGN KEY (tenant_id, shift_id)
        REFERENCES cash.shift (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT drawer_count_actor_fk FOREIGN KEY (tenant_id, counted_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT drawer_count_not_negative CHECK (counted_minor >= 0)
);

COMMENT ON TABLE cash.drawer_count IS
    'FR-CSH-003. What the drawer should have held, what it did hold, and the difference. '
    'The expected figure is stored rather than derived so that a count remains evidence '
    'about the moment it was taken. A recount after a reopening is its own row with phase '
    '''recount'', which is how NC-M4-006 can require one.';

CREATE INDEX drawer_count_shift_idx ON cash.drawer_count (tenant_id, shift_id, phase);

CREATE TABLE cash.denomination_tally (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,
    count_id  uuid NOT NULL,

    -- The note or coin, in minor units: 10000 is a hundred-birr note. The currency sits
    -- beside it because M1-C's FR-DAT-004 requires every money.amount_minor column to,
    -- and the rule is right even where the value looks derivable from the parent count:
    -- a hundred of something is not an amount until the something is named, and
    -- cash.assert_tally_currency_matches_the_count() keeps the two from disagreeing.
    currency_code      char(3) NOT NULL,
    denomination_minor money.amount_minor NOT NULL,
    piece_count        integer NOT NULL,
    subtotal_minor     bigint GENERATED ALWAYS AS
                           (denomination_minor * piece_count) STORED,

    CONSTRAINT denomination_tally_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT denomination_tally_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT denomination_tally_count_fk FOREIGN KEY (tenant_id, count_id)
        REFERENCES cash.drawer_count (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT denomination_tally_positive CHECK (denomination_minor > 0),
    CONSTRAINT denomination_tally_count_not_negative CHECK (piece_count >= 0),
    CONSTRAINT denomination_tally_one_row_per_denomination
        UNIQUE (count_id, denomination_minor)
);

CREATE FUNCTION cash.assert_tally_currency_matches_the_count() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_currency char(3);
BEGIN
    SELECT currency_code INTO v_currency FROM cash.drawer_count
     WHERE tenant_id = NEW.tenant_id AND id = NEW.count_id;

    IF v_currency IS DISTINCT FROM NEW.currency_code THEN
        RAISE EXCEPTION
            'CASH_TALLY_CURRENCY_MISMATCH: count % is in % and a tally row claims %. '
            'Adding notes of two currencies into one total is the arithmetic M1-C''s '
            'pairing rule exists to make impossible',
            NEW.count_id, v_currency, NEW.currency_code
            USING ERRCODE = 'HS422';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER tally_currency_matches_the_count
    BEFORE INSERT OR UPDATE ON cash.denomination_tally
    FOR EACH ROW EXECUTE FUNCTION cash.assert_tally_currency_matches_the_count();

COMMENT ON TABLE cash.denomination_tally IS
    'FR-CSH-003''s denomination count: how many of each note and coin. The subtotal is '
    'generated so a tally cannot disagree with its own arithmetic, and '
    'cash.assert_tally_equals_the_count() requires the tallies to add up to the counted '
    'total — a denomination breakdown that does not reach the figure beside it is the '
    'shape a fudged count takes.';

CREATE FUNCTION cash.assert_tally_equals_the_count() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_count uuid := coalesce(NEW.count_id, OLD.count_id);
    v_tenant uuid := coalesce(NEW.tenant_id, OLD.tenant_id);
    v_counted bigint;
    v_tallied bigint;
BEGIN
    SELECT counted_minor INTO v_counted FROM cash.drawer_count
     WHERE tenant_id = v_tenant AND id = v_count;
    IF v_counted IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT coalesce(sum(subtotal_minor), 0) INTO v_tallied
      FROM cash.denomination_tally
     WHERE tenant_id = v_tenant AND count_id = v_count;

    IF v_tallied <> v_counted THEN
        RAISE EXCEPTION
            'CASH_TALLY_NOT_THE_COUNT: count % records % counted and its denominations '
            'add to %', v_count, v_counted, v_tallied
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER tally_equals_the_count
    AFTER INSERT OR UPDATE OR DELETE ON cash.denomination_tally
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION cash.assert_tally_equals_the_count();


CREATE FUNCTION cash.expected_in_drawer(p_tenant_id uuid, p_shift_id uuid)
RETURNS money.amount_minor
LANGUAGE sql STABLE
AS $$
    -- The float, plus every movement, signed. This is the only place the expected figure
    -- is computed, and cash.drawer_count stores its answer rather than calling it again.
    SELECT (s.opening_float_minor
            + coalesce((SELECT sum(m.amount_minor) FROM cash.movement m
                         WHERE m.tenant_id = s.tenant_id AND m.shift_id = s.id), 0)
           )::money.amount_minor
      FROM cash.shift s
     WHERE s.tenant_id = p_tenant_id AND s.id = p_shift_id;
$$;

COMMENT ON FUNCTION cash.expected_in_drawer(uuid, uuid) IS
    'FR-CSH-003''s expected total: the opening float plus every signed movement. Note '
    'what it does not do — it does not read payments.payment. The drawer knows what '
    'crossed it because a movement was posted, and a drawer that reconciled itself '
    'against the till would agree with the till by construction rather than by counting.';


-- ===========================================================================
-- Custody (FR-CSH-007)
-- ===========================================================================

CREATE TYPE cash.custody_destination AS ENUM ('safe', 'bank');

CREATE TABLE cash.custody_transfer (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,
    shift_id  uuid NOT NULL,
    movement_id uuid NOT NULL,

    destination cash.custody_destination NOT NULL,
    sealed_bag_reference text NOT NULL,

    currency_code char(3) NOT NULL,
    amount_minor  money.amount_minor NOT NULL,

    -- Custody is two people: the one who sealed the bag and the one who took it. A
    -- transfer with one name on it is a bag that left and nobody received.
    released_by_user_id uuid NOT NULL,
    accepted_by_user_id uuid NOT NULL,
    transferred_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT custody_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT custody_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT custody_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT custody_shift_fk FOREIGN KEY (tenant_id, shift_id)
        REFERENCES cash.shift (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT custody_movement_fk FOREIGN KEY (tenant_id, movement_id)
        REFERENCES cash.movement (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT custody_releaser_fk FOREIGN KEY (tenant_id, released_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT custody_accepter_fk FOREIGN KEY (tenant_id, accepted_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT custody_amount_positive CHECK (amount_minor > 0),
    CONSTRAINT custody_reference_not_blank CHECK (btrim(sealed_bag_reference) <> ''),
    -- The same person cannot hand a bag to themselves. M3-D's reasoning about overrides,
    -- applied to physical custody: a chain with one link in it is not a chain.
    CONSTRAINT custody_two_people CHECK (released_by_user_id <> accepted_by_user_id),
    -- One bag reference, once, per outlet. A reused seal number makes two transfers
    -- indistinguishable in exactly the circumstances somebody would want them to be.
    CONSTRAINT custody_reference_unique UNIQUE (tenant_id, outlet_id, sealed_bag_reference),
    -- One custody record per movement: the drop or transfer_out that took the money out.
    CONSTRAINT custody_one_per_movement UNIQUE (movement_id)
);

COMMENT ON TABLE cash.custody_transfer IS
    'FR-CSH-007. Cash to the safe or the bank, with the sealed bag''s reference and both '
    'people. It names the MOVEMENT that took the money out of the drawer rather than '
    'restating the amount independently, so the till and the safe cannot disagree about '
    'how much left.';

CREATE FUNCTION cash.assert_custody_matches_the_movement() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    m cash.movement%ROWTYPE;
BEGIN
    SELECT * INTO m FROM cash.movement
     WHERE tenant_id = NEW.tenant_id AND id = NEW.movement_id;

    IF m.kind NOT IN ('drop', 'transfer_out') THEN
        RAISE EXCEPTION
            'CUSTODY_MOVEMENT_WRONG_KIND: custody follows money LEAVING the drawer, and '
            'movement % is a %', NEW.movement_id, m.kind
            USING ERRCODE = 'HS422';
    END IF;

    IF abs(m.amount_minor) <> NEW.amount_minor THEN
        RAISE EXCEPTION
            'CUSTODY_AMOUNT_DISAGREES: the bag records % and movement % took % out of the '
            'drawer', NEW.amount_minor, NEW.movement_id, abs(m.amount_minor)
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER custody_matches_the_movement
    BEFORE INSERT OR UPDATE ON cash.custody_transfer
    FOR EACH ROW EXECUTE FUNCTION cash.assert_custody_matches_the_movement();


-- ===========================================================================
-- The state machine (FR-CSH-004, NC-M4-006)
-- ===========================================================================

CREATE FUNCTION cash.transition_shift(
    p_tenant_id uuid,
    p_shift_id  uuid,
    p_to_state  cash.shift_state,
    p_actor_user_id uuid,
    p_override_id uuid DEFAULT NULL,
    p_reason_code_id uuid DEFAULT NULL,
    p_reason_text text DEFAULT NULL
) RETURNS void
-- SECURITY DEFINER because verification reads identity.session to learn who the verifier
-- is, and the application role holds no SELECT there. As with M3-D's approve_override()
-- and 0023's verify_proof(), the verifier is NOT a parameter.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, cash, payments, identity, config, pos, money, public
AS $$
DECLARE
    s         cash.shift%ROWTYPE;
    v_session identity.session%ROWTYPE;
    v_seq     integer;
    v_recounts integer;
    v_override pos.override_approval%ROWTYPE;
    v_verifier uuid;
    v_verifier_session uuid;
BEGIN
    SELECT * INTO s FROM cash.shift
     WHERE tenant_id = p_tenant_id AND id = p_shift_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'CASH_SHIFT_NOT_FOUND: no shift % in scope', p_shift_id
            USING ERRCODE = 'HS404';
    END IF;

    -- The permitted edges, written out. There is no 'reopened' → 'finalized' edge, and
    -- that absence is NC-M4-006: a drawer that was reopened reaches 'resolved' or it
    -- stays open where the exception report can see it.
    IF NOT (
        (s.state = 'open'      AND p_to_state = 'submitted')
     OR (s.state = 'submitted' AND p_to_state IN ('verified', 'open'))
     OR (s.state = 'verified'  AND p_to_state = 'finalized')
     OR (s.state = 'finalized' AND p_to_state = 'reopened')
     OR (s.state = 'reopened'  AND p_to_state = 'submitted')
     OR (s.state = 'verified'  AND p_to_state = 'resolved' AND s.reopened_at IS NOT NULL)
    ) THEN
        RAISE EXCEPTION
            'CASH_SHIFT_TRANSITION_INVALID: a shift cannot go from % to %',
            s.state, p_to_state USING ERRCODE = 'HS409';
    END IF;

    -- A reopened shift's only terminal state is 'resolved', and reaching it costs a
    -- recount and somebody else's approval. Said here as the sentence, and refused by the
    -- shift's own CHECK constraints as the property — two locks, either surviving the
    -- other's removal.
    IF p_to_state = 'resolved' THEN
        SELECT count(*) INTO v_recounts FROM cash.drawer_count
         WHERE tenant_id = p_tenant_id AND shift_id = p_shift_id
           AND phase = 'recount' AND counted_at > s.reopened_at;

        IF v_recounts = 0 THEN
            RAISE EXCEPTION
                'REOPENED_SHIFT_NOT_RESOLVED: shift % was reopened at % and has not been '
                'recounted since. Resolving it now would close an accounting hole by '
                'declaring it shut rather than by finding out what was in the drawer',
                p_shift_id, s.reopened_at USING ERRCODE = 'HS409';
        END IF;

        IF p_override_id IS NULL THEN
            RAISE EXCEPTION
                'REOPENED_SHIFT_NOT_RESOLVED: resolving reopened shift % needs an '
                'authorization naming somebody other than the cashier. A drawer that was '
                'reopened and then quietly declared fine is the one nobody looks at again',
                p_shift_id USING ERRCODE = 'HS403';
        END IF;

        SELECT * INTO v_override FROM pos.override_approval
         WHERE tenant_id = p_tenant_id AND id = p_override_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'OVERRIDE_NOT_FOUND: no approval % in scope', p_override_id
                USING ERRCODE = 'HS404';
        END IF;
        IF v_override.subject_kind <> 'cash_shift' OR v_override.subject_id <> p_shift_id THEN
            RAISE EXCEPTION
                'SELF_APPROVAL_ACCEPTED: approval % was granted for %:% and this is shift '
                '%. An approval for one drawer is not an approval for another',
                p_override_id, v_override.subject_kind, v_override.subject_id, p_shift_id
                USING ERRCODE = 'HS403';
        END IF;
    END IF;

    IF p_to_state = 'verified' THEN
        SELECT * INTO v_session FROM identity.session
         WHERE id = app.current_session_id() AND revoked_at IS NULL AND expires_at > now();
        IF NOT FOUND THEN
            RAISE EXCEPTION
                'SESSION_NOT_LIVE: a count is verified by a person, and no live session is '
                'in context to say who' USING ERRCODE = 'HS401';
        END IF;

        -- NC-M4-004, and the reason it is a property rather than a rule. The verifier is
        -- whoever owns the session in context. A manager who authenticated into the
        -- cashier's terminal IS that session, so this resolves to the cashier and the
        -- CHECK on cash.shift refuses. There is no parameter by which somebody could
        -- claim to be a manager.
        IF v_session.user_account_id = s.cashier_user_id THEN
            RAISE EXCEPTION
                'SELF_APPROVAL_ACCEPTED: the verifying session belongs to the cashier who '
                'counted this drawer. A manager authenticating into the cashier''s '
                'terminal is credential sharing rather than verification, and leaves an '
                'audit trail in which the compliant case and the violation are identical'
                USING ERRCODE = 'HS403';
        END IF;

        v_verifier := v_session.user_account_id;
        v_verifier_session := v_session.id;
    END IF;

    -- ONE UPDATE, AND THE STATE MOVES WITH THE COLUMNS THAT DEPEND ON IT. This was two
    -- statements — the timestamps, then the state — and the CHECK constraints are written
    -- as equivalences between the two ("a finalized shift has a finalization time, and
    -- only a finalized shift has one"), so the row was invalid in between and the first
    -- statement failed with a bare 23514. Constraints that relate two columns have to be
    -- satisfied by every statement, not by every pair of statements.
    UPDATE cash.shift
       SET state = p_to_state,
           submitted_at = CASE WHEN p_to_state = 'submitted' THEN now()
                               WHEN p_to_state = 'reopened' THEN NULL
                               ELSE submitted_at END,
           submitted_by_user_id = CASE WHEN p_to_state = 'submitted' THEN p_actor_user_id
                                       WHEN p_to_state = 'reopened' THEN NULL
                                       ELSE submitted_by_user_id END,
           -- The verification is cleared by a reopening because it is no longer true: the
           -- count somebody checked is the count that turned out to be wrong.
           verified_at = CASE WHEN p_to_state = 'verified' THEN now()
                              WHEN p_to_state = 'reopened' THEN NULL
                              ELSE verified_at END,
           verified_by_user_id = CASE WHEN p_to_state = 'verified' THEN v_verifier
                                      WHEN p_to_state = 'reopened' THEN NULL
                                      ELSE verified_by_user_id END,
           verified_by_session_id = CASE WHEN p_to_state = 'verified'
                                              THEN v_verifier_session
                                         WHEN p_to_state = 'reopened' THEN NULL
                                         ELSE verified_by_session_id END,
           finalized_at = CASE WHEN p_to_state IN ('finalized', 'resolved') THEN now()
                               WHEN p_to_state = 'reopened' THEN NULL
                               ELSE finalized_at END,
           reopened_at = CASE WHEN p_to_state = 'reopened' THEN now() ELSE reopened_at END,
           reopen_override_id = CASE WHEN p_to_state = 'reopened' THEN p_override_id
                                     ELSE reopen_override_id END,
           reopen_reason_code_id = CASE WHEN p_to_state = 'reopened' THEN p_reason_code_id
                                        ELSE reopen_reason_code_id END,
           reopen_reason = CASE WHEN p_to_state = 'reopened' THEN p_reason_text
                                ELSE reopen_reason END,
           resolved_at = CASE WHEN p_to_state = 'resolved' THEN now() ELSE resolved_at END,
           resolution_override_id = CASE WHEN p_to_state = 'resolved' THEN p_override_id
                                         ELSE resolution_override_id END
     WHERE tenant_id = p_tenant_id AND id = p_shift_id;

    SELECT coalesce(max(sequence_number), 0) + 1 INTO v_seq
      FROM cash.shift_transition
     WHERE tenant_id = p_tenant_id AND shift_id = p_shift_id;

    INSERT INTO cash.shift_transition
        (tenant_id, outlet_id, shift_id, sequence_number, from_state, to_state,
         actor_user_id, override_id, reason_code_id, reason_text)
    VALUES (p_tenant_id, s.outlet_id, p_shift_id, v_seq, s.state, p_to_state,
            p_actor_user_id, p_override_id, p_reason_code_id, p_reason_text);
END;
$$;

COMMENT ON FUNCTION cash.transition_shift IS
    'FR-CSH-004 and NC-M4-006. The permitted edges of a drawer''s life, with the two that '
    'matter absent: there is no way from ''reopened'' to ''finalized'', and a verifier is '
    'read from the session in context rather than named by a caller. The transition is '
    'recorded in cash.shift_transition, which is append-only, so a shift that was closed '
    'and reopened cannot come to look like one that never closed.';


-- ===========================================================================
-- Writers
-- ===========================================================================

CREATE FUNCTION cash.open_shift(
    p_tenant_id uuid, p_outlet_id uuid, p_terminal_device_id uuid,
    p_cashier_user_id uuid, p_currency_code char(3),
    p_opening_float_minor money.amount_minor
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO cash.shift
        (tenant_id, outlet_id, terminal_device_id, cashier_user_id, currency_code,
         opening_float_minor)
    VALUES (p_tenant_id, p_outlet_id, p_terminal_device_id, p_cashier_user_id, p_currency_code,
            p_opening_float_minor)
    RETURNING id INTO v_id;

    INSERT INTO cash.shift_transition
        (tenant_id, outlet_id, shift_id, sequence_number, from_state, to_state,
         actor_user_id)
    VALUES (p_tenant_id, p_outlet_id, v_id, 1, NULL, 'open', p_cashier_user_id);

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION cash.open_shift IS
    'FR-CSH-001. A drawer opened with a counted float on an assigned terminal. The '
    'partial unique index refuses a second live shift on the same till.';


CREATE FUNCTION cash.live_shift_for_terminal(
    p_tenant_id uuid, p_terminal_device_id uuid)
RETURNS uuid
LANGUAGE sql STABLE
AS $$
    SELECT id FROM cash.shift
     WHERE tenant_id = p_tenant_id AND terminal_device_id = p_terminal_device_id
       AND state IN ('open', 'reopened');
$$;


CREATE FUNCTION cash.post_cash_payment(
    p_tenant_id uuid, p_outlet_id uuid, p_shift_id uuid, p_payment_id uuid
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    p payments.payment%ROWTYPE;
    v_id uuid;
BEGIN
    SELECT * INTO p FROM payments.payment
     WHERE tenant_id = p_tenant_id AND id = p_payment_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PAYMENT_NOT_FOUND: no payment % in scope', p_payment_id
            USING ERRCODE = 'HS404';
    END IF;
    IF p.provider <> 'cash' THEN
        RAISE EXCEPTION
            'CASH_MOVEMENT_WRONG_PROVIDER: payment % was taken by % and never touched the '
            'drawer. Posting it here would make a count disagree with the notes in it',
            p_payment_id, p.provider USING ERRCODE = 'HS422';
    END IF;

    -- WHAT GOES IN THE DRAWER IS WHAT STAYED. The guest handed over the tendered amount
    -- and took the change away with them, so the till gained the difference. Computed
    -- from two stored figures rather than from the bill, which is the same discipline
    -- FR-PAY-017 asks for on the other side of the counter.
    INSERT INTO cash.movement
        (tenant_id, outlet_id, shift_id, kind, currency_code, amount_minor, payment_id,
         actor_user_id)
    VALUES (p_tenant_id, p_outlet_id, p_shift_id, 'sales_receipt', p.currency_code,
            p.tendered_minor - p.change_minor, p_payment_id, p.captured_by_user_id)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION cash.post_cash_payment IS
    'FR-CSH-002''s sales receipt. The drawer gains what was tendered less the change, '
    'both read from the payment''s stored columns. cash.movement takes UNIQUE (payment_id) '
    'so a retry cannot count the same notes twice.';


CREATE FUNCTION cash.record_count(
    p_tenant_id uuid, p_outlet_id uuid, p_shift_id uuid,
    p_phase cash.count_phase, p_tally jsonb, p_actor_user_id uuid
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_shift cash.shift%ROWTYPE;
    v_counted bigint := 0;
    v_entry jsonb;
    v_id uuid;
BEGIN
    SELECT * INTO v_shift FROM cash.shift
     WHERE tenant_id = p_tenant_id AND id = p_shift_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'CASH_SHIFT_NOT_FOUND: no shift % in scope', p_shift_id
            USING ERRCODE = 'HS404';
    END IF;

    -- The counted total is the SUM OF THE DENOMINATIONS, never a separate number the
    -- cashier types. A count whose total and breakdown are two independent inputs is a
    -- count in which one of them can be adjusted to make the evening balance.
    FOR v_entry IN SELECT jsonb_array_elements(p_tally)
    LOOP
        v_counted := v_counted
            + (v_entry ->> 'denomination_minor')::bigint
            * (v_entry ->> 'piece_count')::bigint;
    END LOOP;

    INSERT INTO cash.drawer_count
        (tenant_id, outlet_id, shift_id, phase, currency_code, expected_minor,
         counted_minor, counted_by_user_id)
    VALUES (p_tenant_id, p_outlet_id, p_shift_id, p_phase, v_shift.currency_code,
            cash.expected_in_drawer(p_tenant_id, p_shift_id), v_counted, p_actor_user_id)
    RETURNING id INTO v_id;

    FOR v_entry IN SELECT jsonb_array_elements(p_tally)
    LOOP
        INSERT INTO cash.denomination_tally
            (tenant_id, outlet_id, count_id, currency_code, denomination_minor,
             piece_count)
        VALUES (p_tenant_id, p_outlet_id, v_id, v_shift.currency_code,
                (v_entry ->> 'denomination_minor')::bigint,
                (v_entry ->> 'piece_count')::integer);
    END LOOP;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION cash.record_count IS
    'FR-CSH-003. A denomination count, from which the counted total is derived rather '
    'than typed, against an expected total computed once and stored. The difference is '
    'generated by the table.';


-- ===========================================================================
-- Exception reporting (FR-CSH-008)
-- ===========================================================================

CREATE TYPE cash.exception_kind AS ENUM (
    'missing_close',
    'excessive_cash_difference',
    'unusual_refund',
    'unusual_payout',
    'late_settlement',
    -- Not in the requirement's list, and here because NC-M4-006 is: a reopened drawer
    -- that nobody resolved is the exception the control is named for, and a report that
    -- could not show it would let the hole sit behind a green screen.
    'reopened_not_resolved');

-- The two thresholds FR-CSH-008 leaves to the operator, read from the outlet's cash
-- policy. Both fail CLOSED in the direction that reports MORE rather than less: an
-- unset acceptable difference is zero, so every non-zero difference is reported until
-- somebody decides what normal looks like, and an unset unusual amount is zero, so every
-- refund and payout appears. A threshold nobody has set must not mean a threshold nobody
-- can breach.

CREATE FUNCTION cash.acceptable_difference_minor(p_tenant_id uuid, p_outlet_id uuid)
RETURNS bigint
LANGUAGE sql STABLE
AS $$
    SELECT coalesce(
        (SELECT (p.payload ->> 'acceptable_difference_minor')::bigint
           FROM config.policy p
          WHERE p.tenant_id = p_tenant_id AND p.category = 'cash'
            AND (p.outlet_id = p_outlet_id OR p.outlet_id IS NULL)
            AND p.payload ? 'acceptable_difference_minor'
            AND p.effective_from <= now()
            AND (p.effective_to IS NULL OR p.effective_to > now())
          ORDER BY (p.outlet_id IS NULL), p.version DESC
          LIMIT 1), 0);
$$;

CREATE FUNCTION cash.unusual_movement_minor(p_tenant_id uuid, p_outlet_id uuid)
RETURNS bigint
LANGUAGE sql STABLE
AS $$
    SELECT coalesce(
        (SELECT (p.payload ->> 'unusual_movement_minor')::bigint
           FROM config.policy p
          WHERE p.tenant_id = p_tenant_id AND p.category = 'cash'
            AND (p.outlet_id = p_outlet_id OR p.outlet_id IS NULL)
            AND p.payload ? 'unusual_movement_minor'
            AND p.effective_from <= now()
            AND (p.effective_to IS NULL OR p.effective_to > now())
          ORDER BY (p.outlet_id IS NULL), p.version DESC
          LIMIT 1), 0);
$$;


CREATE FUNCTION cash.exception_report(
    p_tenant_id uuid, p_outlet_id uuid, p_as_of timestamptz DEFAULT now()
) RETURNS TABLE (
    kind        text,
    shift_id    uuid,
    detail      text,
    amount_minor bigint,
    since       timestamptz
)
LANGUAGE sql STABLE
AS $$
    -- FR-CSH-008's four, plus the one NC-M4-006 requires. Each is a query over recorded
    -- rows rather than a flag somebody sets, so an exception cannot be cleared by
    -- forgetting to raise it.
    SELECT 'missing_close'::text, s.id,
           format('opened %s and still %s', s.opened_at::date, s.state),
           NULL::bigint, s.opened_at
      FROM cash.shift s
     WHERE s.tenant_id = p_tenant_id AND s.outlet_id = p_outlet_id
       AND s.state IN ('open', 'submitted')
       AND s.opened_at < p_as_of - interval '18 hours'

    UNION ALL
    SELECT 'reopened_not_resolved', s.id,
           format('reopened %s and not resolved', s.reopened_at),
           NULL::bigint, s.reopened_at
      FROM cash.shift s
     WHERE s.tenant_id = p_tenant_id AND s.outlet_id = p_outlet_id
       AND s.reopened_at IS NOT NULL AND s.state <> 'resolved'

    UNION ALL
    SELECT 'excessive_cash_difference', c.shift_id,
           format('counted %s against %s expected', c.counted_minor, c.expected_minor),
           c.over_short_minor, c.counted_at
      FROM cash.drawer_count c
     WHERE c.tenant_id = p_tenant_id AND c.outlet_id = p_outlet_id
       AND c.phase <> 'opening'
       AND abs(c.over_short_minor) > cash.acceptable_difference_minor(p_tenant_id, p_outlet_id)

    UNION ALL
    SELECT 'unusual_refund', m.shift_id, format('refund of %s', abs(m.amount_minor)),
           abs(m.amount_minor), m.occurred_at
      FROM cash.movement m
     WHERE m.tenant_id = p_tenant_id AND m.outlet_id = p_outlet_id
       AND m.kind = 'refund'
       AND abs(m.amount_minor) > cash.unusual_movement_minor(p_tenant_id, p_outlet_id)

    UNION ALL
    SELECT 'unusual_payout', m.shift_id, format('payout of %s', abs(m.amount_minor)),
           abs(m.amount_minor), m.occurred_at
      FROM cash.movement m
     WHERE m.tenant_id = p_tenant_id AND m.outlet_id = p_outlet_id
       AND m.kind = 'payout'
       AND abs(m.amount_minor) > cash.unusual_movement_minor(p_tenant_id, p_outlet_id)

    UNION ALL
    SELECT 'late_settlement', s.id,
           format('finalized %s, cash still not transferred to safe or bank', s.finalized_at),
           NULL::bigint, s.finalized_at
      FROM cash.shift s
     WHERE s.tenant_id = p_tenant_id AND s.outlet_id = p_outlet_id
       AND s.state IN ('finalized', 'resolved')
       AND s.finalized_at < p_as_of - interval '24 hours'
       AND NOT EXISTS (SELECT 1 FROM cash.custody_transfer t
                        WHERE t.tenant_id = s.tenant_id AND t.shift_id = s.id)
     ORDER BY 5 DESC;
$$;

COMMENT ON FUNCTION cash.exception_report(uuid, uuid, timestamptz) IS
    'FR-CSH-008. A missing close, a difference beyond what the outlet accepts, an unusual '
    'refund or payout, a late settlement — and a reopened drawer nobody resolved, which '
    'is NC-M4-006''s exception and is here because a report that could not show it would '
    'let the hole sit behind a green screen. Every row is a query over recorded facts '
    'rather than a flag, so an exception cannot be cleared by forgetting to raise it.';


-- ===========================================================================
-- The drawer joins the reconciliation (FR-PAY-013)
-- ===========================================================================
-- 0023's payments.reconciliation() said cash shifts would join it here, and this is that.
-- Two pictures of one evening, side by side, so they can DISAGREE — which is the point.
-- A single figure computed from one of them would always reconcile.

CREATE FUNCTION cash.shift_reconciliation(p_tenant_id uuid, p_shift_id uuid)
RETURNS TABLE (
    shift_id              uuid,
    state                 text,
    opening_float_minor   bigint,
    sales_receipt_minor   bigint,
    refund_minor          bigint,
    payout_minor          bigint,
    drop_minor            bigint,
    float_adjustment_minor bigint,
    transfer_minor        bigint,
    expected_minor        bigint,
    counted_minor         bigint,
    over_short_minor      bigint,
    -- Tips are here as their own column and are NEVER added into a sales figure.
    -- FR-PAY-013 forbids merging tips into sales revenue, and this is the layer at which
    -- that merge would happen: a cash tip is money in the same drawer, so the temptation
    -- to add it to takings is structural rather than careless.
    tip_allocation_minor  bigint
)
LANGUAGE sql STABLE
AS $$
    SELECT s.id,
           s.state::text,
           s.opening_float_minor::bigint,
           coalesce(sum(m.amount_minor) FILTER (WHERE m.kind = 'sales_receipt'), 0)::bigint,
           coalesce(sum(m.amount_minor) FILTER (WHERE m.kind = 'refund'), 0)::bigint,
           coalesce(sum(m.amount_minor) FILTER (WHERE m.kind = 'payout'), 0)::bigint,
           coalesce(sum(m.amount_minor) FILTER (WHERE m.kind = 'drop'), 0)::bigint,
           coalesce(sum(m.amount_minor) FILTER (WHERE m.kind = 'float_adjustment'), 0)::bigint,
           coalesce(sum(m.amount_minor) FILTER (
               WHERE m.kind IN ('transfer_in', 'transfer_out')), 0)::bigint,
           cash.expected_in_drawer(s.tenant_id, s.id)::bigint,
           c.counted_minor::bigint,
           c.over_short_minor,
           coalesce((SELECT sum(a.amount_minor)
                       FROM cash.movement m2
                       JOIN payments.allocation a
                         ON a.tenant_id = m2.tenant_id AND a.payment_id = m2.payment_id
                      WHERE m2.tenant_id = s.tenant_id AND m2.shift_id = s.id
                        AND a.target = 'tip'), 0)::bigint
      FROM cash.shift s
      LEFT JOIN cash.movement m ON m.tenant_id = s.tenant_id AND m.shift_id = s.id
      LEFT JOIN LATERAL (
           SELECT d.counted_minor, d.over_short_minor FROM cash.drawer_count d
            WHERE d.tenant_id = s.tenant_id AND d.shift_id = s.id AND d.phase <> 'opening'
            ORDER BY d.counted_at DESC LIMIT 1) c ON true
     WHERE s.tenant_id = p_tenant_id AND s.id = p_shift_id
     GROUP BY s.id, s.tenant_id, s.state, s.opening_float_minor,
              c.counted_minor, c.over_short_minor;
$$;

COMMENT ON FUNCTION cash.shift_reconciliation(uuid, uuid) IS
    'FR-PAY-013 from the drawer''s side. Every movement kind as its own column, the '
    'expected and counted totals, the difference — and the tip allocations that passed '
    'through this drawer, kept apart from the sales receipts. tests/m4b derives the '
    'revenue-bearing columns of this function and of payments.reconciliation() from the '
    'catalog and requires that none of them reads a tip, the same derivation M4-A used on '
    'the thirteen balance functions.';


-- ===========================================================================
-- Row level security
-- ===========================================================================

DO $$
DECLARE t text;
BEGIN
    FOR t IN
        SELECT format('%I.%I', schemaname, tablename)
        FROM pg_tables WHERE schemaname = 'cash'
        ORDER BY tablename
    LOOP
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY %I ON %s FOR ALL '
            'USING (app.row_in_scope(tenant_id, outlet_id)) '
            'WITH CHECK (app.row_in_scope(tenant_id, outlet_id))',
            split_part(t, '.', 2) || '_isolation', t);
    END LOOP;
END;
$$;


-- ===========================================================================
-- Grants
-- ===========================================================================

GRANT USAGE ON SCHEMA cash TO hospitality_app;
-- And USAGE on the sequences behind the bigserial keys. The application role holds INSERT
-- on the ledger deliberately — the grant and the append-only trigger are two independent
-- locks — and an INSERT that cannot draw a key is a grant that does not work. 0019's
-- writers hid this by being SECURITY DEFINER; the ledger here is written by the caller,
-- so the grant has to be real.
GRANT USAGE ON ALL SEQUENCES IN SCHEMA cash TO hospitality_app;

GRANT SELECT ON cash.shift              TO hospitality_app;
GRANT SELECT ON cash.shift_transition   TO hospitality_app;
GRANT SELECT ON cash.movement           TO hospitality_app;
GRANT SELECT ON cash.drawer_count       TO hospitality_app;
GRANT SELECT ON cash.denomination_tally TO hospitality_app;
GRANT SELECT ON cash.custody_transfer   TO hospitality_app;

-- Movements, counts and custody are written once and never edited; the append-only
-- trigger on cash.movement refuses the rest independently of the grant.
GRANT INSERT ON cash.movement           TO hospitality_app;
GRANT INSERT ON cash.drawer_count       TO hospitality_app;
GRANT INSERT ON cash.denomination_tally TO hospitality_app;
GRANT INSERT ON cash.custody_transfer   TO hospitality_app;
GRANT INSERT ON cash.shift              TO hospitality_app;
GRANT INSERT ON cash.shift_transition   TO hospitality_app;

-- NOTE WHAT IS ABSENT: no UPDATE on cash.shift. Every state change runs inside
-- cash.transition_shift(), which is SECURITY DEFINER and reads the verifier from the
-- session in context. An application holding every permission there is still cannot mark
-- a drawer verified by writing to it, which is the grant half of NC-M4-004.

GRANT EXECUTE ON FUNCTION cash.open_shift(uuid, uuid, uuid, uuid, char, money.amount_minor) TO hospitality_app;
GRANT EXECUTE ON FUNCTION cash.transition_shift(uuid, uuid, cash.shift_state, uuid, uuid, uuid, text) TO hospitality_app;
GRANT EXECUTE ON FUNCTION cash.post_cash_payment(uuid, uuid, uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION cash.record_count(uuid, uuid, uuid, cash.count_phase, jsonb, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION cash.expected_in_drawer(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION cash.live_shift_for_terminal(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION cash.exception_report(uuid, uuid, timestamptz) TO hospitality_app;
GRANT EXECUTE ON FUNCTION cash.shift_reconciliation(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION cash.acceptable_difference_minor(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION cash.unusual_movement_minor(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION cash.movement_direction(cash.movement_kind) TO hospitality_app;

GRANT USAGE ON SCHEMA cash TO hospitality_migrator;
