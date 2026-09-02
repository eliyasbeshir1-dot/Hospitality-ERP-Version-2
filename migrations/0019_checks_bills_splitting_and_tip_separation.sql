-- =============================================================================
-- 0019 — Checks, bills, splitting, and the separation of a tip from a bill
-- =============================================================================
-- A TIP IS NEVER PART OF A BILL BALANCE. NO TIP IS SELECTED BY DEFAULT. MONEY IS EXACT.
--
-- Three doctrines, all ruled by the specification rather than chosen here, and each is
-- built so that breaking it requires changing the schema rather than changing a line of
-- application code:
--
--   * A tip lives in its own table, with no column anywhere in billing.bill,
--     billing.check_allocation or billing.bill_component that could hold one, and the
--     balance function does not read it. tests/m4a asserts both from the catalog, so
--     "no tip reaches a bill balance" is a property of the model rather than of whoever
--     wrote today's code (FR-BIL-005, FR-BIL-013, FR-BIL-014, NC-M4-002).
--   * The tip settings table cannot express a default. There is no column for one
--     (FR-BIL-013, NC-M4-001).
--   * Every amount is money.amount_minor beside an explicit currency, and
--     money.assert_currency_paired() — which M1-C built and which has had nothing much
--     to say until now — covers every new table (FR-BIL-005).
--
-- WHAT THIS SLICE DOES NOT BUILD. There is no payment here: no capture, no provider, no
-- reconciliation, no cash shift. That is M4-B's, and the closure register names it. A
-- bill therefore reaches a settled balance at this gate only through an AUTHORIZED
-- DISPOSITION — a comp, a write-off, a transfer — which is the second half of FR-BIL-008
-- and the half that does not need a payment to exist. Nothing here pretends to take
-- money, and there is no column into which a payment could be written.
--
-- THE ORDER LEDGER IS NOT TOUCHED. FR-BIL-001 requires checks to be created from
-- accepted or served order lines "without changing order ownership or history". A check
-- REFERENCES order lines; it never writes to ordering. tests/m4a proves that with M3-A's
-- whole-schema differential rather than by reading this comment.
-- =============================================================================

CREATE SCHEMA billing;

COMMENT ON SCHEMA billing IS
    'Checks, bills, splitting and tips (FR-BIL-001 through FR-BIL-016). Separate from '
    'ordering because a bill is a view onto an order rather than a part of one: the order '
    'ledger is append-only and untouched by anything here, which is what FR-BIL-001''s '
    '"without changing order ownership or history" means in practice.';


-- ===========================================================================
-- Configuration a bill is calculated from (FR-CFG-001C)
-- ===========================================================================
-- The tax configuration and the discount policy already exist and already drive an order
-- preview — M3-A built them and tests/m3a exercises both with non-zero values. What has
-- never had a configured source is the FEE component: ordering.charge_kind has carried
-- 'fee' since M3-A and ordering.charge_source_kind has carried 'service_configuration',
-- and no configuration produced one, which is why FR-ORD-003's fee component and
-- FR-ORD-005's fee snapshot have been open in the closure register since that gate.
--
-- This is that source. A service charge is a fee: it is charged by the house, it is not a
-- tip, and conflating the two is the single most common way a tip ends up inside a bill
-- balance. The two are as far apart here as the schema can put them — a service charge is
-- a bill COMPONENT summed into the total, and a tip is a row in another table that the
-- total cannot see.

CREATE TABLE billing.service_charge_setting (
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    configuration_version_id uuid NOT NULL,
    percentage      money.percentage NOT NULL,
    rounding        money.rounding_mode NOT NULL,

    -- Which components it is charged on. A service charge on the tax is a different
    -- number from one on the subtotal, and leaving it implicit is how two systems come to
    -- disagree about the same bill.
    applies_to      ordering.charge_kind[] NOT NULL DEFAULT ARRAY['item_subtotal']::ordering.charge_kind[],

    effective_from  timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (tenant_id, outlet_id),
    CONSTRAINT service_charge_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    -- By id alone, exactly as ordering.charge_rule references it: config.configuration_version
    -- carries no (tenant_id, id) unique key, and adding one to a table applied at M1 to
    -- make this reference prettier would edit an applied migration.
    CONSTRAINT service_charge_version_fk FOREIGN KEY (configuration_version_id)
        REFERENCES config.configuration_version (id) ON DELETE RESTRICT,
    CONSTRAINT service_charge_percentage_sane CHECK (percentage >= 0 AND percentage <= 100),

    -- A service charge that applies to nothing is a setting somebody meant to delete.
    CONSTRAINT service_charge_applies_to_something CHECK (
        array_length(applies_to, 1) >= 1),

    -- AND IT MAY NOT APPLY TO ITSELF. A fee charged on fees compounds, and the amount a
    -- guest is asked for stops being derivable from the menu.
    CONSTRAINT service_charge_not_charged_on_itself CHECK (
        NOT ('fee' = ANY (applies_to)))
);

COMMENT ON TABLE billing.service_charge_setting IS
    'FR-CFG-001C and FR-ORD-003''s fee component. The configured source ''fee'' never had '
    'until now: it points at a config.configuration_version so the value a bill used is '
    'the approved one and stays recoverable, exactly as the tax component does.';


-- ---------------------------------------------------------------------------
-- Tip settings, which CANNOT express a default (FR-BIL-013, NC-M4-001)
-- ---------------------------------------------------------------------------
-- The requirement is that no tip is selected by default, and the way to mean it is to
-- give the model nowhere to put one. There is no is_default column, no default_index, no
-- preselected flag: a suggestion is a number a guest may tap, and the set of suggestions
-- carries no opinion about which. A surface that preselected one would be inventing a
-- fact the configuration cannot state, and tests/m4a measures the rendered page to prove
-- none does.
--
-- The suggestions are ordered so a surface can lay them out predictably. Order is not
-- preference: display_order 1 is the leftmost, not the default.

CREATE TABLE billing.tip_setting (
    tenant_id     uuid NOT NULL,
    outlet_id     uuid NOT NULL,
    offered       boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (tenant_id, outlet_id),
    CONSTRAINT tip_setting_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT
);

CREATE TABLE billing.tip_suggestion (
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,
    -- display_order, not "position": the word position is a reserved keyword PostgreSQL
    -- accepts in a CREATE TABLE and rejects in a RETURNS TABLE, and a column that cannot
    -- be named in a read model is a column with a trap in it. It is also the more honest
    -- name — this is where a suggestion sits on the screen, not which one is preferred.
    display_order integer NOT NULL,
    percentage money.percentage NOT NULL,

    PRIMARY KEY (tenant_id, outlet_id, display_order),
    CONSTRAINT tip_suggestion_setting_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES billing.tip_setting (tenant_id, outlet_id) ON DELETE CASCADE,
    CONSTRAINT tip_suggestion_order_positive CHECK (display_order >= 1),
    CONSTRAINT tip_suggestion_percentage_sane CHECK (percentage > 0 AND percentage <= 100)
);

COMMENT ON TABLE billing.tip_suggestion IS
    'FR-BIL-013. Amounts a guest may tap, in a layout order. THERE IS NO COLUMN FOR A '
    'DEFAULT and that is the requirement: no tip is selected by default, so the model is '
    'given nowhere to say one is. NC-M4-001 plants the defect at the only level left — '
    'the surface preselecting one — and tests/m4a measures the rendered page for it.';


-- ===========================================================================
-- Checks, and the allocation that cannot bill a unit twice (FR-BIL-001, FR-BIL-002)
-- ===========================================================================

CREATE TYPE billing.check_state AS ENUM ('open', 'billed', 'merged', 'void');

CREATE TABLE billing.check (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL,
    outlet_id        uuid NOT NULL,
    table_session_id uuid NOT NULL,
    check_number     text NOT NULL,
    state            billing.check_state NOT NULL DEFAULT 'open',

    -- Where a merged check went, and where a split check came from. Both directions are
    -- recorded because FR-BIL-004 asks for the SOURCE relationships to be preserved and
    -- FR-TAB-007B asks a merged session to split back with a complete audit trail; a
    -- merge that only recorded the survivor would answer the first and not the second.
    merged_into_check_id uuid,
    split_from_check_id  uuid,

    opened_by_user_id uuid NOT NULL,
    opened_at        timestamptz NOT NULL DEFAULT now(),
    closed_at        timestamptz,

    CONSTRAINT check_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT check_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT check_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT check_session_fk FOREIGN KEY (tenant_id, table_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT check_opener_fk FOREIGN KEY (tenant_id, opened_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT check_merged_into_fk FOREIGN KEY (tenant_id, merged_into_check_id)
        REFERENCES billing.check (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT check_split_from_fk FOREIGN KEY (tenant_id, split_from_check_id)
        REFERENCES billing.check (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT check_number_unique UNIQUE (tenant_id, outlet_id, check_number),

    -- A merged check names where it went, and nothing else does.
    CONSTRAINT check_merge_target_only_when_merged CHECK (
        (state = 'merged') = (merged_into_check_id IS NOT NULL)),
    CONSTRAINT check_does_not_merge_into_itself CHECK (
        merged_into_check_id IS DISTINCT FROM id),
    CONSTRAINT check_does_not_split_from_itself CHECK (
        split_from_check_id IS DISTINCT FROM id),
    CONSTRAINT check_closure_consistent CHECK (
        (state IN ('open')) = (closed_at IS NULL))
);

COMMENT ON TABLE billing.check IS
    'FR-BIL-001. What a party is being billed for: an allocation of order lines, created '
    'from accepted or served lines and changing nothing about them. A check may be split '
    'or merged while the money is still undecided; once a bill is issued from it the '
    'money is decided and corrections go through FR-BIL-009''s void, credit and reissue '
    'instead.';

CREATE TABLE billing.check_allocation (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL,
    outlet_id     uuid NOT NULL,
    check_id      uuid NOT NULL,
    order_id      uuid NOT NULL,
    order_line_id uuid NOT NULL,

    -- WHOLE OR PARTIAL. FR-BIL-002 asks for both: three of a party of five sharing a
    -- platter is a partial allocation of one line across two checks, and it is the case
    -- in which double billing actually happens.
    quantity      integer NOT NULL,

    allocated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT check_allocation_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT check_allocation_check_fk FOREIGN KEY (tenant_id, check_id)
        REFERENCES billing.check (tenant_id, id) ON DELETE CASCADE,
    -- NO FOREIGN KEY ONTO THE ORDER OR ITS LINES, and that is the rule M3-D paid for.
    -- ordering.customer_order and ordering.order_line are PROJECTIONS: FR-DAT-010's
    -- rebuild deletes them wholesale and folds them back, and a durable table holding a
    -- key into one makes that rebuild fail on the foreign key rather than succeed.
    -- M3-D shipped exactly this defect — pos.handover_item referenced a projection — and
    -- only a reversed run found it, because the forward order never produces the
    -- reference before the rebuild.
    --
    -- What replaces the key is billing.allocate_to_check(), which resolves the line,
    -- refuses ALLOCATION_LINE_UNKNOWN when there is none, and reads the order's state
    -- before it writes anything. The id here is a reference to a fact in the ledger,
    -- which is the thing that actually endures.
    CONSTRAINT check_allocation_quantity_positive CHECK (quantity >= 1),

    -- One row per line per check. Two rows for the same line on the same check would be
    -- an allocation nobody could reason about, and the double-billing guard below counts
    -- rows across checks rather than within one.
    CONSTRAINT check_allocation_once_per_line UNIQUE (check_id, order_line_id)
);

COMMENT ON TABLE billing.check_allocation IS
    'FR-BIL-002. Which order line units this check bills for. There is no amount column: '
    'an allocation says WHAT is billed and the bill says what it COSTS, so the price a '
    'guest is asked for is calculated once from the order''s own snapshot rather than '
    'copied here where it could drift from it.';


-- ---------------------------------------------------------------------------
-- A unit cannot be billed twice (FR-BIL-002, NC quantity double billed)
-- ---------------------------------------------------------------------------
-- The rule is a statement about a SET of checks, not about one row, so no unique index
-- can express it: two checks may each allocate part of a line, and what must never
-- happen is that the parts sum past the line. A constraint trigger asks the question
-- after the write, against every check that is still live.
--
-- Void and merged checks are excluded, and both exclusions are load-bearing. A voided
-- check bills nothing, so its allocations must not block a replacement. A merged check's
-- allocations have moved to its target, so counting both would double-count the merge
-- itself — which is the shape of the bug this trigger exists to catch, arriving through
-- the mechanism meant to be safe.

CREATE FUNCTION billing.assert_no_unit_billed_twice() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_line   uuid := coalesce(NEW.order_line_id, OLD.order_line_id);
    v_tenant uuid := coalesce(NEW.tenant_id, OLD.tenant_id);
    v_ordered integer;
    v_billed  integer;
BEGIN
    SELECT quantity INTO v_ordered
      FROM ordering.order_line
     WHERE tenant_id = v_tenant AND id = v_line;

    IF v_ordered IS NULL THEN
        RAISE EXCEPTION
            'ALLOCATION_LINE_UNKNOWN: no order line % in scope, so how much of it has '
            'been billed cannot be established', v_line
            USING ERRCODE = 'HS404';
    END IF;

    SELECT coalesce(sum(a.quantity), 0) INTO v_billed
      FROM billing.check_allocation a
      JOIN billing.check c ON c.tenant_id = a.tenant_id AND c.id = a.check_id
     WHERE a.tenant_id = v_tenant
       AND a.order_line_id = v_line
       AND c.state NOT IN ('void', 'merged');

    IF v_billed > v_ordered THEN
        RAISE EXCEPTION
            'QUANTITY_DOUBLE_BILLED: order line % was ordered % time(s) and is allocated '
            'to live checks % time(s). A unit billed twice is money taken twice, and the '
            'guest finds out at the till',
            v_line, v_ordered, v_billed
            USING ERRCODE = 'HS409';
    END IF;

    RETURN NULL;
END;
$$;

-- DEFERRABLE and INITIALLY DEFERRED, because a split moves quantity between two checks
-- and the intermediate state is legitimately over-allocated for the length of one
-- statement. What must hold is the state at COMMIT, which is what a party is actually
-- billed. Same reasoning as M3-D's handover responsibility trigger.
CREATE CONSTRAINT TRIGGER check_allocation_never_bills_a_unit_twice
    AFTER INSERT OR UPDATE ON billing.check_allocation
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION billing.assert_no_unit_billed_twice();

-- The same rule, from the other side: a check leaving 'void' or 'merged' brings its
-- allocations back to life, and that can be the write that pushes a line past its
-- quantity. Without this the guard could be walked around by allocating on a voided
-- check and then reopening it.
CREATE FUNCTION billing.assert_revival_bills_nothing_twice() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_offender record;
BEGIN
    IF OLD.state IN ('void', 'merged') AND NEW.state NOT IN ('void', 'merged') THEN
        SELECT a.order_line_id, l.quantity AS ordered, sum(a2.quantity) AS billed
          INTO v_offender
          FROM billing.check_allocation a
          JOIN ordering.order_line l
            ON l.tenant_id = a.tenant_id AND l.id = a.order_line_id
          JOIN billing.check_allocation a2
            ON a2.tenant_id = a.tenant_id AND a2.order_line_id = a.order_line_id
          JOIN billing.check c2
            ON c2.tenant_id = a2.tenant_id AND c2.id = a2.check_id
           AND c2.state NOT IN ('void', 'merged')
         WHERE a.tenant_id = NEW.tenant_id AND a.check_id = NEW.id
         GROUP BY a.order_line_id, l.quantity
        HAVING sum(a2.quantity) > l.quantity
         LIMIT 1;

        IF FOUND THEN
            RAISE EXCEPTION
                'QUANTITY_DOUBLE_BILLED: reviving check % would bill order line % % '
                'time(s) against % ordered',
                NEW.id, v_offender.order_line_id, v_offender.billed, v_offender.ordered
                USING ERRCODE = 'HS409';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER check_revival_bills_nothing_twice
    BEFORE UPDATE ON billing.check
    FOR EACH ROW EXECUTE FUNCTION billing.assert_revival_bills_nothing_twice();


-- ===========================================================================
-- The bill ledger, and the bill as a fold of it (FR-BIL-009, FR-DAT-008A, FR-DAT-010)
-- ===========================================================================
-- THE SAME ARRANGEMENT AS THE ORDER LEDGER, FOR THE SAME REASON. FR-BIL-009 says an
-- issued bill is corrected through authorized void, credit or reissue rather than
-- deletion, and the way to mean that is to make deletion impossible rather than
-- discouraged: the ledger is append-only by trigger AND by grant, and the bill itself is
-- a projection nothing may write except the fold.
--
-- Two independent locks, as M3-A established: the application role holds no INSERT,
-- UPDATE or DELETE on the projection, and the projection's own trigger refuses any write
-- that does not carry the fold's transaction-local marker. Removing either leaves the
-- other standing.

CREATE TYPE billing.bill_event_kind AS ENUM (
    'issued', 'component_calculated', 'disposition_recorded', 'finalized',
    'voided', 'credited', 'reissued');

CREATE TABLE billing.bill_event (
    id              bigserial PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    bill_id         uuid NOT NULL,
    sequence_number integer NOT NULL,
    kind            billing.bill_event_kind NOT NULL,
    occurred_at     timestamptz NOT NULL DEFAULT now(),

    actor_user_id   uuid,
    override_id     uuid,
    reason_code_id  uuid,
    reason_text     text,

    before          jsonb,
    after           jsonb,
    correlation_id  uuid,

    CONSTRAINT bill_event_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT bill_event_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT bill_event_actor_fk FOREIGN KEY (tenant_id, actor_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT bill_event_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT bill_event_sequence_positive CHECK (sequence_number >= 1),
    CONSTRAINT bill_event_sequence_unique UNIQUE (tenant_id, bill_id, sequence_number),

    -- A correction says why. FR-BIL-009's whole content is that a bill is corrected
    -- ANSWERABLY, and a void with no reason is a deletion with extra steps.
    CONSTRAINT bill_event_correction_states_a_reason CHECK (
        kind NOT IN ('voided', 'credited', 'reissued')
        OR (reason_code_id IS NOT NULL AND btrim(coalesce(reason_text, '')) <> ''))
);

COMMENT ON TABLE billing.bill_event IS
    'FR-BIL-009 and FR-DAT-008A. The authoritative record of everything that happened to '
    'a bill. Append-only by trigger and by grant. Every projection below is folded from '
    'it, so a rebuild reproduces them and a correction is an event rather than an edit.';

CREATE FUNCTION billing.refuse_ledger_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'BILL_DELETED_NOT_CREDITED: billing.bill_event is append-only. An issued bill is '
        'corrected by voiding, crediting or reissuing it — each of which is another event '
        'naming who authorized it and why. Removing the record instead is how a bill that '
        'somebody paid stops existing'
        USING ERRCODE = 'HS409';
END;
$$;

CREATE TRIGGER bill_event_append_only
    BEFORE UPDATE OR DELETE ON billing.bill_event
    FOR EACH ROW EXECUTE FUNCTION billing.refuse_ledger_mutation();


-- ---------------------------------------------------------------------------
-- The bill (projection)
-- ---------------------------------------------------------------------------

CREATE TYPE billing.bill_state AS ENUM (
    'issued', 'finalized', 'voided', 'credited', 'reissued');

CREATE TABLE billing.bill (
    id            uuid PRIMARY KEY,
    tenant_id     uuid NOT NULL,
    outlet_id     uuid NOT NULL,
    check_id      uuid NOT NULL,
    bill_number   text NOT NULL,
    state         billing.bill_state NOT NULL,

    currency_code char(3) NOT NULL,

    -- THE BILL BALANCE. A sum over the components below, asserted by trigger, and there
    -- is no tip in it. FR-BIL-014 makes bill balance, service charge, tax, tip and total
    -- tendered separate values; four of the five are here and the tip is deliberately
    -- somewhere else entirely.
    bill_total_minor money.amount_minor NOT NULL,

    -- What has been disposed of by authority — comped, written off, transferred. At this
    -- gate it is the only route to a settled balance, because M4-A takes no payment.
    disposed_minor   money.amount_minor NOT NULL DEFAULT 0,

    -- THE CALCULATION VERSION (FR-BIL-006). Persisted on the document, so a bill disputed
    -- six months from now is recomputed the way it was computed rather than the way the
    -- code computes today. A rounding change that silently rewrote history is exactly
    -- what this column exists to make impossible.
    calculation_version text NOT NULL,

    locale        menu.customer_locale NOT NULL,
    issued_at     timestamptz NOT NULL,
    finalized_at  timestamptz,

    -- Where a correction went. A voided bill names the reissue that replaced it, so the
    -- chain from the first document to the last is walkable in both directions.
    reissued_as_bill_id uuid,
    supersedes_bill_id  uuid,

    ledger_sequence integer NOT NULL DEFAULT 0,

    CONSTRAINT bill_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT bill_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT bill_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT bill_check_fk FOREIGN KEY (tenant_id, check_id)
        REFERENCES billing.check (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT bill_reissue_fk FOREIGN KEY (tenant_id, reissued_as_bill_id)
        REFERENCES billing.bill (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT bill_supersedes_fk FOREIGN KEY (tenant_id, supersedes_bill_id)
        REFERENCES billing.bill (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT bill_number_unique UNIQUE (tenant_id, outlet_id, bill_number),
    CONSTRAINT bill_currency_is_iso CHECK (currency_code ~ '^[A-Z]{3}$'),
    CONSTRAINT bill_total_not_negative CHECK (bill_total_minor >= 0),
    CONSTRAINT bill_disposed_within_total CHECK (
        disposed_minor >= 0 AND disposed_minor <= bill_total_minor),
    CONSTRAINT bill_calculation_version_stated CHECK (btrim(calculation_version) <> ''),
    CONSTRAINT bill_finalization_consistent CHECK (
        (state = 'finalized') = (finalized_at IS NOT NULL)),
    CONSTRAINT bill_does_not_supersede_itself CHECK (
        supersedes_bill_id IS DISTINCT FROM id
        AND reissued_as_bill_id IS DISTINCT FROM id),
    CONSTRAINT bill_ledger_sequence_not_negative CHECK (ledger_sequence >= 0)
);

COMMENT ON TABLE billing.bill IS
    'FR-BIL-005 through FR-BIL-009. The calculated document issued from a check. A '
    'projection: nothing writes it outside the writers that set the fold''s marker, and '
    'the total is asserted '
    'to equal the sum of its components. THERE IS NO TIP COLUMN — a tip is a separate '
    'value and a separate record (FR-BIL-014), and the absence of a column is what makes '
    'that structural rather than a habit.';

CREATE TABLE billing.bill_component (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL,
    outlet_id     uuid NOT NULL,
    bill_id       uuid NOT NULL,
    kind          ordering.charge_kind NOT NULL,
    source_kind   ordering.charge_source_kind NOT NULL,
    source_id     uuid,

    -- How it was arrived at: the rate, the base, the rounding mode and the stage. A
    -- component that recorded only its amount would make a disputed bill unarguable.
    basis         jsonb NOT NULL,

    currency_code char(3) NOT NULL,
    amount_minor  money.amount_minor NOT NULL,

    CONSTRAINT bill_component_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT bill_component_bill_fk FOREIGN KEY (tenant_id, bill_id)
        REFERENCES billing.bill (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT bill_component_currency_is_iso CHECK (currency_code ~ '^[A-Z]{3}$'),
    CONSTRAINT bill_component_basis_is_an_object CHECK (jsonb_typeof(basis) = 'object'),
    CONSTRAINT bill_component_one_per_kind UNIQUE (bill_id, kind)
);

COMMENT ON TABLE billing.bill_component IS
    'FR-BIL-005. Item subtotal, discount, tax and fee, each computed exactly and each '
    'recording the basis it was computed from. One per kind per bill, so the total is a '
    'sum with no double-counted term.';


-- ===========================================================================
-- Splitting (FR-BIL-003, FR-TAB-007B)
-- ===========================================================================
-- Five modes, and the arithmetic is money.allocate()'s — built at M1-C, corrected at M3
-- to be exact for negatives, and never used in anger until now. Equal share across a
-- party that does not divide the total evenly is precisely what it exists for: the parts
-- sum to the total, and a minor unit is neither lost nor invented.

CREATE TYPE billing.split_mode AS ENUM (
    'by_item', 'by_participant', 'equal_share', 'custom_amount', 'separate_orders');

CREATE TABLE billing.bill_share (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL,
    outlet_id    uuid NOT NULL,
    bill_id      uuid NOT NULL,
    share_number integer NOT NULL,
    mode         billing.split_mode NOT NULL,

    -- Whose share, where the mode knows. by_participant and by_item can name the guest
    -- session; equal_share and custom_amount divide among payers who need not be guests
    -- the system has ever seen.
    participant_guest_session_id uuid,

    currency_code char(3) NOT NULL,
    amount_minor  money.amount_minor NOT NULL,

    CONSTRAINT bill_share_tenant_id_unique UNIQUE (tenant_id, id),
    -- No key onto billing.bill, for the reason billing.check_allocation records: the bill
    -- is a projection and a rebuild deletes it. A share is durable working state — a
    -- party's decision about how to divide what they owe — and outliving a refold is
    -- precisely what it must do.
    CONSTRAINT bill_share_number_unique UNIQUE (bill_id, share_number),
    CONSTRAINT bill_share_number_positive CHECK (share_number >= 1),
    CONSTRAINT bill_share_currency_is_iso CHECK (currency_code ~ '^[A-Z]{3}$'),
    CONSTRAINT bill_share_amount_not_negative CHECK (amount_minor >= 0)
);

COMMENT ON TABLE billing.bill_share IS
    'FR-BIL-003. One payer''s share of a bill. Shares sum to the bill total exactly — '
    'billing.assert_shares_sum_to_the_bill() refuses any set that does not — so a split '
    'can neither lose a minor unit nor create one.';

CREATE FUNCTION billing.assert_shares_sum_to_the_bill() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_bill   uuid := coalesce(NEW.bill_id, OLD.bill_id);
    v_tenant uuid := coalesce(NEW.tenant_id, OLD.tenant_id);
    v_total  bigint;
    v_shares bigint;
BEGIN
    SELECT bill_total_minor INTO v_total
      FROM billing.bill WHERE tenant_id = v_tenant AND id = v_bill;
    SELECT coalesce(sum(amount_minor), 0) INTO v_shares
      FROM billing.bill_share WHERE tenant_id = v_tenant AND bill_id = v_bill;

    IF v_shares <> v_total THEN
        RAISE EXCEPTION
            'SPLIT_NOT_EXACT: the shares of bill % sum to % and the bill total is %. A '
            'split that loses a minor unit shorts the house and one that creates a minor '
            'unit overcharges a guest; money.allocate() exists so that neither can happen',
            v_bill, v_shares, v_total
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NULL;
END;
$$;

-- Deferred: a split writes its shares one row at a time and is only meaningful complete.
CREATE CONSTRAINT TRIGGER bill_share_sums_to_the_bill
    AFTER INSERT OR UPDATE OR DELETE ON billing.bill_share
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION billing.assert_shares_sum_to_the_bill();


-- ===========================================================================
-- Tips (FR-BIL-013, FR-BIL-014, FR-BIL-015, FR-BIL-016)
-- ===========================================================================
-- A TIP IS ATTACHED TO A PAYER, NOT TO A BILL BALANCE.
--
-- Everything about this table's SHAPE is the requirement:
--
--   * it is not billing.bill and it is not billing.bill_component, so no tip is ever
--     summed into bill_total_minor — the total's trigger sums components and this is not
--     one, and nothing can make it one without a migration;
--   * it points at a SHARE, so FR-BIL-015's "each payer may choose their own optional
--     tip" is the ordinary case rather than a special one, and choosing a tip cannot
--     reallocate a bill line because there is no path from here to
--     billing.check_allocation;
--   * corrections are their own rows linked to the original (FR-BIL-016), so a reversal
--     is auditable and never an edit.
--
-- tests/m4a asserts all of that from the catalog rather than from this comment: no tip
-- column outside this schema's tip tables, and no function that computes a bill balance
-- reads them.

CREATE TABLE billing.tip (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL,
    outlet_id     uuid NOT NULL,
    bill_share_id uuid NOT NULL,

    currency_code char(3) NOT NULL,
    amount_minor  money.amount_minor NOT NULL,

    -- How the payer arrived at it. A suggestion they tapped, or an amount they typed.
    -- Recorded because "the guest chose 10%" and "the guest chose 47 birr" are different
    -- facts and only one of them survives a change to the suggestions.
    chosen_from_percentage money.percentage,

    chosen_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT tip_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT tip_share_fk FOREIGN KEY (tenant_id, bill_share_id)
        REFERENCES billing.bill_share (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT tip_currency_is_iso CHECK (currency_code ~ '^[A-Z]{3}$'),

    -- A tip is positive. Zero is not a tip, it is the absence of one, and recording it as
    -- a tip of zero would make "how many guests tipped" unanswerable.
    CONSTRAINT tip_amount_positive CHECK (amount_minor > 0),
    CONSTRAINT tip_one_per_share UNIQUE (bill_share_id)
);

COMMENT ON TABLE billing.tip IS
    'FR-BIL-014 and FR-BIL-015. A tip, attached to one payer''s share. It is in its own '
    'table with its own currency and amount because bill balance and tip are separate '
    'values and separate records; there is no column anywhere in billing.bill that could '
    'hold one, and the total''s trigger sums components rather than tips.';

CREATE TYPE billing.tip_correction_kind AS ENUM ('reversal', 'refund', 'correction');

CREATE TABLE billing.tip_correction (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    tip_id         uuid NOT NULL,
    kind           billing.tip_correction_kind NOT NULL,

    currency_code  char(3) NOT NULL,
    amount_minor   money.amount_minor NOT NULL,

    reason_code_id uuid NOT NULL,
    reason_text    text NOT NULL,
    actor_user_id  uuid NOT NULL,
    override_id    uuid NOT NULL,
    corrected_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT tip_correction_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT tip_correction_tip_fk FOREIGN KEY (tenant_id, tip_id)
        REFERENCES billing.tip (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT tip_correction_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT tip_correction_actor_fk FOREIGN KEY (tenant_id, actor_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT tip_correction_override_fk FOREIGN KEY (tenant_id, override_id)
        REFERENCES pos.override_approval (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT tip_correction_currency_is_iso CHECK (currency_code ~ '^[A-Z]{3}$'),
    CONSTRAINT tip_correction_amount_positive CHECK (amount_minor > 0),
    CONSTRAINT tip_correction_states_a_reason CHECK (btrim(reason_text) <> '')
);

COMMENT ON TABLE billing.tip_correction IS
    'FR-BIL-016. A reversal, refund or correction of a tip, LINKED to the original rather '
    'than replacing it. It carries an override, so M3-D''s rule that an approver is never '
    'the actor applies here without being written a second time — which is NC-M4-004''s '
    'maker-checker for the half of it that exists at this gate.';

CREATE FUNCTION billing.refuse_tip_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'TIP_ALTERED_NOT_CORRECTED: a tip is corrected by a linked reversal, refund or '
        'correction record, never by editing or deleting the original. FR-BIL-016 asks '
        'for corrections to be separate auditable records and an edit is neither'
        USING ERRCODE = 'HS409';
END;
$$;

CREATE TRIGGER tip_append_only
    BEFORE UPDATE OR DELETE ON billing.tip
    FOR EACH ROW EXECUTE FUNCTION billing.refuse_tip_mutation();

CREATE TRIGGER tip_correction_append_only
    BEFORE UPDATE OR DELETE ON billing.tip_correction
    FOR EACH ROW EXECUTE FUNCTION billing.refuse_tip_mutation();


-- ===========================================================================
-- Dispositions: the only route to a settled balance at this gate (FR-BIL-008)
-- ===========================================================================
-- FR-BIL-008 permits finalization when the bill balance is settled OR an authorized
-- disposition exists. M4-A takes no payment, so the first branch is unreachable here and
-- the second is the whole of it. That is not a gap being papered over: a comp, a write-off
-- and a transfer are real dispositions a restaurant makes, they need authority and a
-- reason, and they are exactly the part of FR-BIL-008 that does not depend on M4-B.

CREATE TYPE billing.disposition_kind AS ENUM ('comped', 'written_off', 'transferred');

CREATE TABLE billing.bill_disposition (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    bill_id        uuid NOT NULL,
    kind           billing.disposition_kind NOT NULL,

    currency_code  char(3) NOT NULL,
    amount_minor   money.amount_minor NOT NULL,

    -- Authorized, with a reason, by somebody who is not the person performing it. The
    -- override carries both identities and M3-D's schema makes an approver who is the
    -- actor impossible, so the maker-checker rule is inherited rather than restated.
    override_id    uuid NOT NULL,
    reason_code_id uuid NOT NULL,
    reason_text    text NOT NULL,
    actor_user_id  uuid NOT NULL,
    disposed_at    timestamptz NOT NULL DEFAULT now(),

    -- Where a transfer went. A transferred balance that named no destination would be a
    -- write-off wearing a friendlier word.
    transferred_to_check_id uuid,

    CONSTRAINT bill_disposition_tenant_id_unique UNIQUE (tenant_id, id),
    -- No key onto billing.bill, again. A disposition is an authorized act that HAPPENED;
    -- it is recorded in the ledger as well, and it must survive a refold of the document
    -- it was made against. The key it does keep is the one onto pos.override_approval,
    -- which is durable and is the thing that makes the act answerable.
    CONSTRAINT bill_disposition_override_fk FOREIGN KEY (tenant_id, override_id)
        REFERENCES pos.override_approval (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT bill_disposition_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT bill_disposition_actor_fk FOREIGN KEY (tenant_id, actor_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT bill_disposition_target_fk FOREIGN KEY (tenant_id, transferred_to_check_id)
        REFERENCES billing.check (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT bill_disposition_currency_is_iso CHECK (currency_code ~ '^[A-Z]{3}$'),
    CONSTRAINT bill_disposition_amount_positive CHECK (amount_minor > 0),
    CONSTRAINT bill_disposition_states_a_reason CHECK (btrim(reason_text) <> ''),
    CONSTRAINT bill_disposition_transfer_names_a_destination CHECK (
        (kind = 'transferred') = (transferred_to_check_id IS NOT NULL))
);

COMMENT ON TABLE billing.bill_disposition IS
    'FR-BIL-008''s second branch. At M4-A it is the only branch: nothing here takes money, '
    'so a bill reaches a settled balance by being comped, written off or transferred, each '
    'with an override that names two people and a reason that names why.';


-- ===========================================================================
-- The balance, and what it deliberately cannot see (FR-BIL-008, FR-BIL-014, NC-M4-002)
-- ===========================================================================
-- THE FUNCTION THAT DECIDES WHETHER A BILL IS SETTLED DOES NOT READ A TIP.
--
-- It reads the bill total and the dispositions against it. There is no join to
-- billing.tip, no column it could reach through, and tests/m4a asserts that from the
-- catalog — a tip that never touches the balance because nobody wrote that code today is
-- not the same as one that cannot.
--
-- NC-M4-002 plants the defect at the only level left: adding the tip to the balance here.
-- The control requires TIP_COMMINGLED_WITH_BILL, and the structural assertion catches it
-- whether or not any behaviour changes.

CREATE FUNCTION billing.outstanding_balance(p_tenant_id uuid, p_bill_id uuid)
RETURNS money.amount_minor
LANGUAGE sql STABLE
AS $$
    SELECT b.bill_total_minor
           - coalesce((SELECT sum(d.amount_minor)
                         FROM billing.bill_disposition d
                        WHERE d.tenant_id = b.tenant_id AND d.bill_id = b.id), 0)
      FROM billing.bill b
     WHERE b.tenant_id = p_tenant_id AND b.id = p_bill_id;
$$;

COMMENT ON FUNCTION billing.outstanding_balance(uuid, uuid) IS
    'FR-BIL-008. What is still owed on a bill: its total, less what has been disposed of '
    'by authority. IT DOES NOT READ billing.tip AND MUST NOT — a tip that made a balance '
    'look settled is NC-M4-002, and the requirement that forbids it is the reason bill '
    'and tip are separate records rather than two columns of one.';


-- ===========================================================================
-- The fold (FR-DAT-010)
-- ===========================================================================
-- Projection writes carry a transaction-local marker that only this function sets. The
-- same arrangement as ordering.apply_event() and fulfillment's fold, and for the same
-- reason: the grant stops the application role writing a projection at all, and the
-- trigger stops anyone — the table owner included, under FORCE ROW LEVEL SECURITY —
-- writing one outside the fold. Two locks, either of which survives the other's removal.

CREATE FUNCTION billing.refuse_projection_write() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF coalesce(current_setting('billing.applying_event', true), '') <> 'yes' THEN
        RAISE EXCEPTION
            'BILL_PROJECTION_WRITTEN_DIRECTLY: %.% is folded from billing.bill_event and '
            'may only be written inside a writer that has set billing.applying_event. A '
            'projection written behind its ledger is a projection a rebuild puts back',
            TG_TABLE_SCHEMA, TG_TABLE_NAME
            USING ERRCODE = 'HS409';
    END IF;
    RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER bill_written_only_by_the_fold
    BEFORE INSERT OR UPDATE OR DELETE ON billing.bill
    FOR EACH ROW EXECUTE FUNCTION billing.refuse_projection_write();

CREATE TRIGGER bill_component_written_only_by_the_fold
    BEFORE INSERT OR UPDATE OR DELETE ON billing.bill_component
    FOR EACH ROW EXECUTE FUNCTION billing.refuse_projection_write();

-- The bill total is a sum over components, asserted rather than trusted. M3-A learned
-- this on the order total: a stored total that disagrees with its parts is a number
-- somebody will be charged.
CREATE FUNCTION billing.assert_total_is_the_sum() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_bill   uuid := coalesce(NEW.bill_id, OLD.bill_id);
    v_tenant uuid := coalesce(NEW.tenant_id, OLD.tenant_id);
    v_total  bigint;
    v_sum    bigint;
BEGIN
    SELECT bill_total_minor INTO v_total
      FROM billing.bill WHERE tenant_id = v_tenant AND id = v_bill;
    IF v_total IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT coalesce(sum(amount_minor), 0) INTO v_sum
      FROM billing.bill_component WHERE tenant_id = v_tenant AND bill_id = v_bill;

    IF v_sum <> v_total THEN
        RAISE EXCEPTION
            'BILL_TOTAL_NOT_THE_SUM_OF_ITS_COMPONENTS: bill % stores % and its components '
            'sum to %', v_bill, v_total, v_sum
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER bill_total_is_the_sum_of_its_components
    AFTER INSERT OR UPDATE OR DELETE ON billing.bill_component
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION billing.assert_total_is_the_sum();


-- ===========================================================================
-- Writers
-- ===========================================================================
-- THE CALCULATION VERSION. One string, stated once, persisted on every bill it computed.
-- FR-BIL-006 asks for it because a rounding change six months from now must not silently
-- rewrite what a guest was charged: a disputed bill is recomputed under the version it
-- names, not under today's code. Changing the arithmetic below without changing this
-- string is the defect the control checks for.
CREATE FUNCTION billing.calculation_version() RETURNS text
LANGUAGE sql IMMUTABLE
AS $$ SELECT 'BILL-CALC-1'::text $$;

COMMENT ON FUNCTION billing.calculation_version() IS
    'FR-BIL-006. The identity of the arithmetic below. Persisted on every bill so a '
    'disputed one is recomputed the way it was computed. A function rather than a '
    'constant so there is exactly one place it is stated.';


CREATE FUNCTION billing.append_event(
    p_tenant_id uuid, p_outlet_id uuid, p_bill_id uuid,
    p_kind billing.bill_event_kind,
    p_actor_user_id uuid DEFAULT NULL,
    p_override_id uuid DEFAULT NULL,
    p_reason_code_id uuid DEFAULT NULL,
    p_reason_text text DEFAULT NULL,
    p_before jsonb DEFAULT NULL,
    p_after jsonb DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_sequence integer;
    v_id       bigint;
BEGIN
    SELECT coalesce(max(sequence_number), 0) + 1 INTO v_sequence
      FROM billing.bill_event
     WHERE tenant_id = p_tenant_id AND bill_id = p_bill_id;

    INSERT INTO billing.bill_event
        (tenant_id, outlet_id, bill_id, sequence_number, kind, actor_user_id,
         override_id, reason_code_id, reason_text, before, after)
    VALUES (p_tenant_id, p_outlet_id, p_bill_id, v_sequence, p_kind, p_actor_user_id,
            p_override_id, p_reason_code_id, p_reason_text, p_before, p_after)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION billing.append_event IS
    'Appends one event and returns ITS ID, not its sequence number. The id is what '
    'billing.apply_event() folds, and returning the sequence instead made the ledger '
    'position the only thing a caller could name — which is exactly the value a rebuild '
    'must not need, because a rebuild replays events in the order they were APPENDED '
    'across every bill, not within one.';


-- ---------------------------------------------------------------------------
-- The fold itself (FR-DAT-010)
-- ---------------------------------------------------------------------------
-- ONE FUNCTION WRITES THE PROJECTION, AND A REBUILD IS THE SAME FUNCTION REPLAYED.
--
-- This is the arrangement ordering.apply_event() established at M3-A and fulfillment
-- copied at M3-B, and it is here for the reason FR-DAT-010 gives: a projection that
-- cannot be reproduced from the ledger is not a projection, it is a second copy of the
-- truth that nobody can check. The refusal in billing.refuse_projection_write() says a
-- projection written behind its ledger is one a rebuild puts back, and that sentence has
-- to be true rather than aspirational.
--
-- So EVERY figure the projection carries is in the event that produced it — the bill's
-- number, currency, total, calculation version and locale, and the full list of its
-- components with the basis each was computed from. A writer that computed something and
-- put it only in the table would survive until the first rebuild and no longer.

CREATE FUNCTION billing.apply_event(p_event_id bigint) RETURNS void
-- SECURITY DEFINER because it writes the projection and the application role holds no
-- write grant on it — the point of that revocation. The grant and the marker stay two
-- independent locks; row level security is FORCED and its predicate reads the session
-- context, which the definer switch does not change.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, billing, ordering, config, money, menu, service, public
AS $$
DECLARE
    e         billing.bill_event%ROWTYPE;
    v_after   jsonb;
    v_component jsonb;
BEGIN
    SELECT * INTO e FROM billing.bill_event WHERE id = p_event_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LEDGER_EVENT_ABSENT: no bill event %', p_event_id
            USING ERRCODE = 'HS404';
    END IF;
    v_after := coalesce(e.after, '{}'::jsonb);

    PERFORM set_config('billing.applying_event', 'yes', true);

    IF e.kind = 'issued' THEN
        INSERT INTO billing.bill
            (id, tenant_id, outlet_id, check_id, bill_number, state, currency_code,
             bill_total_minor, calculation_version, locale, issued_at, ledger_sequence)
        VALUES (e.bill_id, e.tenant_id, e.outlet_id,
                (v_after ->> 'check_id')::uuid,
                v_after ->> 'bill_number', 'issued',
                (v_after ->> 'currency_code')::char(3),
                (v_after ->> 'bill_total_minor')::bigint,
                v_after ->> 'calculation_version',
                (v_after ->> 'locale')::menu.customer_locale,
                e.occurred_at, e.sequence_number);

        FOR v_component IN
            SELECT * FROM jsonb_array_elements(coalesce(v_after -> 'components',
                                                        '[]'::jsonb))
        LOOP
            INSERT INTO billing.bill_component
                (tenant_id, outlet_id, bill_id, kind, source_kind, source_id, basis,
                 currency_code, amount_minor)
            VALUES (e.tenant_id, e.outlet_id, e.bill_id,
                    (v_component ->> 'kind')::ordering.charge_kind,
                    (v_component ->> 'source_kind')::ordering.charge_source_kind,
                    (v_component ->> 'source_id')::uuid,
                    v_component -> 'basis',
                    (v_component ->> 'currency_code')::char(3),
                    (v_component ->> 'amount_minor')::bigint);
        END LOOP;

    ELSIF e.kind = 'disposition_recorded' THEN
        UPDATE billing.bill
           SET disposed_minor = disposed_minor + (v_after ->> 'amount_minor')::bigint,
               ledger_sequence = e.sequence_number
         WHERE tenant_id = e.tenant_id AND id = e.bill_id;

    ELSIF e.kind = 'finalized' THEN
        UPDATE billing.bill
           SET state = 'finalized', finalized_at = e.occurred_at,
               ledger_sequence = e.sequence_number
         WHERE tenant_id = e.tenant_id AND id = e.bill_id;

    ELSIF e.kind IN ('voided', 'credited') THEN
        UPDATE billing.bill
           SET state = e.kind::text::billing.bill_state,
               ledger_sequence = e.sequence_number
         WHERE tenant_id = e.tenant_id AND id = e.bill_id;

    ELSIF e.kind = 'reissued' THEN
        -- Both directions of the correction chain, from one event. The replacement names
        -- what it supersedes and the original names its replacement, so a reader who
        -- finds either document can walk to the other — which is what makes a void
        -- answerable rather than merely recorded.
        UPDATE billing.bill
           SET supersedes_bill_id = (v_after ->> 'supersedes')::uuid,
               state = 'reissued',
               ledger_sequence = e.sequence_number
         WHERE tenant_id = e.tenant_id AND id = e.bill_id;
        UPDATE billing.bill
           SET reissued_as_bill_id = e.bill_id
         WHERE tenant_id = e.tenant_id AND id = (v_after ->> 'supersedes')::uuid;
    END IF;

    PERFORM set_config('billing.applying_event', '', true);
END;
$$;

COMMENT ON FUNCTION billing.apply_event(bigint) IS
    'FR-DAT-010. The one writer of billing.bill and billing.bill_component. Every figure '
    'it writes comes out of the event, so replaying the ledger reproduces the projection '
    'exactly — which is what billing.rebuild_projections() does and what makes the '
    'projection guard''s refusal a true statement rather than a hopeful one.';


-- ---------------------------------------------------------------------------
-- Open a check, and allocate to it (FR-BIL-001, FR-BIL-002)
-- ---------------------------------------------------------------------------

CREATE FUNCTION billing.open_check(
    p_tenant_id uuid, p_outlet_id uuid, p_table_session_id uuid, p_user_id uuid
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_id     uuid;
    v_number text;
BEGIN
    -- The document number comes from M1-C's series, which is gapless, per-outlet, audited
    -- and refuses outright when no series is configured. A check numbered by this
    -- function would be a second numbering scheme that could collide with the first.
    v_number := config.issue_document_number(
        p_tenant_id, 'check', to_char(now(), 'YYYY'), NULL, p_outlet_id);

    INSERT INTO billing.check
        (tenant_id, outlet_id, table_session_id, check_number, opened_by_user_id)
    VALUES (p_tenant_id, p_outlet_id, p_table_session_id, v_number, p_user_id)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

CREATE FUNCTION billing.allocate_to_check(
    p_tenant_id uuid, p_outlet_id uuid, p_check_id uuid,
    p_order_line_id uuid, p_quantity integer DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_line ordering.order_line%ROWTYPE;
    v_order ordering.customer_order%ROWTYPE;
    v_id   uuid;
BEGIN
    SELECT * INTO v_line FROM ordering.order_line
     WHERE tenant_id = p_tenant_id AND id = p_order_line_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ALLOCATION_LINE_UNKNOWN: no order line % in scope', p_order_line_id
            USING ERRCODE = 'HS404';
    END IF;

    SELECT * INTO v_order FROM ordering.customer_order
     WHERE tenant_id = p_tenant_id AND id = v_line.order_id;

    -- FR-BIL-001: from ACCEPTED OR SERVED lines. A submitted order has not been agreed to
    -- by the house yet, and billing for something nobody accepted is the commercial
    -- equivalent of cooking it before it was ordered.
    IF v_order.state <> 'accepted' THEN
        RAISE EXCEPTION
            'ALLOCATION_ORDER_NOT_BILLABLE: order % is %; a check is created from '
            'accepted or served lines', v_order.id, v_order.state
            USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO billing.check_allocation
        (tenant_id, outlet_id, check_id, order_id, order_line_id, quantity)
    VALUES (p_tenant_id, p_outlet_id, p_check_id, v_line.order_id, p_order_line_id,
            coalesce(p_quantity, v_line.quantity))
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION billing.allocate_to_check(uuid, uuid, uuid, uuid, integer) IS
    'FR-BIL-002. Allocates whole or partial line quantity to a check. It writes nothing '
    'in ordering — FR-BIL-001''s "without changing order ownership or history" — and the '
    'deferred constraint trigger above refuses any commit in which a unit is billed twice.';


-- ---------------------------------------------------------------------------
-- Issue a bill from a check, calculated exactly (FR-BIL-005, FR-BIL-006)
-- ---------------------------------------------------------------------------
-- The stages are explicit and the order of them is the answer to FR-ORD-003's
-- discount-and-tax question, which M3-A left open because it is a bill-calculation
-- decision and M3-A was not the bill:
--
--   1. item subtotal   the sum of allocated line amounts, from the order's own snapshot
--   2. discount        applied to the subtotal
--   3. tax             on the DISCOUNTED subtotal
--   4. service charge  on what the setting says it applies to, never on itself
--
-- Tax on the discounted subtotal is the reading that makes a discount actually reduce
-- what a guest pays. Taxing first and discounting after would charge tax on money nobody
-- was asked for. Both readings round differently, which is why the stage is recorded in
-- each component's basis and the whole calculation carries a version.

CREATE FUNCTION billing.issue_bill(
    p_tenant_id uuid, p_outlet_id uuid, p_check_id uuid,
    p_user_id uuid, p_locale menu.customer_locale DEFAULT 'en'
) RETURNS uuid
-- SECURITY DEFINER because it writes billing.bill and billing.bill_component, and the
-- application role holds NO write grant on either — which is the point of that
-- revocation. The two locks stay independent: the grant refuses the application writing
-- a projection at all, and billing.refuse_projection_write() refuses anybody, owner
-- included, writing one without the fold's transaction-local marker. Definer rights
-- widen WHAT may be written and never WHICH TENANT'S ROWS ARE VISIBLE: row level
-- security is FORCED on every table this touches and its predicate reads the session
-- context, which the definer switch does not change.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, billing, ordering, config, money, menu, service, public
AS $$
DECLARE
    v_bill      uuid := gen_random_uuid();
    v_number    text;
    v_currency  char(3);
    v_subtotal  bigint := 0;
    v_discount  bigint := 0;
    v_tax       bigint := 0;
    v_fee       bigint := 0;
    v_total     bigint;
    v_service   billing.service_charge_setting%ROWTYPE;
    v_tax_rate  money.percentage;
    v_tax_round money.rounding_mode;
    v_tax_config uuid;
    v_disc_rate money.percentage;
    v_disc_round money.rounding_mode;
    v_disc_policy uuid;
    v_base      bigint;
    v_components jsonb;
    v_event     bigint;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM billing.check
                    WHERE tenant_id = p_tenant_id AND id = p_check_id AND state = 'open') THEN
        RAISE EXCEPTION
            'CHECK_NOT_OPEN: check % is not open, so no bill can be issued from it',
            p_check_id USING ERRCODE = 'HS409';
    END IF;

    -- 1. Item subtotal, from the ORDER's snapshot rather than from today's menu. The
    --    price a guest agreed to is the one M2-A froze and M3-A stored.
    SELECT coalesce(sum(l.unit_amount_minor * a.quantity), 0),
           min(l.currency_code)
      INTO v_subtotal, v_currency
      FROM billing.check_allocation a
      JOIN ordering.order_line l
        ON l.tenant_id = a.tenant_id AND l.id = a.order_line_id
     WHERE a.tenant_id = p_tenant_id AND a.check_id = p_check_id;

    IF v_currency IS NULL THEN
        RAISE EXCEPTION
            'CHECK_ALLOCATES_NOTHING: check % bills no order line, and a bill for nothing '
            'is a document somebody would have to explain', p_check_id
            USING ERRCODE = 'HS409';
    END IF;

    -- 2. Discount, on the subtotal.
    SELECT (payload -> 'table_service' ->> 'percentage')::money.percentage,
           (payload -> 'table_service' ->> 'rounding')::money.rounding_mode,
           id
      INTO v_disc_rate, v_disc_round, v_disc_policy
      FROM config.policy
     WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id AND category = 'discount'
     ORDER BY version DESC LIMIT 1;

    IF v_disc_rate IS NOT NULL THEN
        v_discount := -money.apply_rate(v_subtotal, v_disc_rate, v_disc_round);
    END IF;

    -- 3. Tax, on the DISCOUNTED subtotal.
    SELECT (payload -> 'contexts' -> 'standard' ->> 'percentage')::money.percentage,
           (payload -> 'contexts' -> 'standard' ->> 'rounding')::money.rounding_mode,
           id
      INTO v_tax_rate, v_tax_round, v_tax_config
      FROM config.configuration_version
     WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id AND category = 'tax'
     ORDER BY version DESC LIMIT 1;

    IF v_tax_rate IS NULL THEN
        RAISE EXCEPTION
            'BILL_TAX_UNCONFIGURED: outlet % has no approved tax configuration, and a '
            'bill computed without one would be a guess', p_outlet_id
            USING ERRCODE = 'HS412';
    END IF;
    v_tax := money.apply_rate(v_subtotal + v_discount, v_tax_rate, v_tax_round);

    -- 4. Service charge, on what it is configured to apply to.
    SELECT * INTO v_service FROM billing.service_charge_setting
     WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id;

    IF FOUND THEN
        v_base := 0;
        IF 'item_subtotal' = ANY (v_service.applies_to) THEN v_base := v_base + v_subtotal; END IF;
        IF 'discount'      = ANY (v_service.applies_to) THEN v_base := v_base + v_discount; END IF;
        IF 'tax'           = ANY (v_service.applies_to) THEN v_base := v_base + v_tax; END IF;
        v_fee := money.apply_rate(v_base, v_service.percentage, v_service.rounding);
    END IF;

    v_total := v_subtotal + v_discount + v_tax + v_fee;
    v_number := config.issue_document_number(
        p_tenant_id, 'bill', to_char(now(), 'YYYY'), NULL, p_outlet_id);

    -- THE COMPONENTS ARE BUILT INTO THE EVENT, not into the table. The projection is
    -- folded from what is written here, so anything computed above that did not reach
    -- this payload would survive exactly until the first rebuild (FR-DAT-010). Each one
    -- carries the BASIS it was computed from — the rate, the base and the rounding — so a
    -- disputed bill can be argued about rather than merely re-read.
    v_components := jsonb_build_array(
        jsonb_build_object(
            'kind', 'item_subtotal', 'source_kind', 'menu_price', 'source_id', NULL,
            'currency_code', v_currency, 'amount_minor', v_subtotal,
            'basis', jsonb_build_object(
                'stage', 1,
                'from', 'allocated order lines at their snapshot unit price')));

    IF v_discount <> 0 THEN
        v_components := v_components || jsonb_build_array(jsonb_build_object(
            'kind', 'discount', 'source_kind', 'discount_policy',
            'source_id', v_disc_policy,
            'currency_code', v_currency, 'amount_minor', v_discount,
            'basis', jsonb_build_object('stage', 2, 'percentage', v_disc_rate,
                                        'rounding', v_disc_round,
                                        'base_minor', v_subtotal)));
    END IF;

    v_components := v_components || jsonb_build_array(jsonb_build_object(
        'kind', 'tax', 'source_kind', 'tax_configuration', 'source_id', v_tax_config,
        'currency_code', v_currency, 'amount_minor', v_tax,
        'basis', jsonb_build_object(
            'stage', 3, 'percentage', v_tax_rate, 'rounding', v_tax_round,
            'base_minor', v_subtotal + v_discount,
            'note', 'tax is computed on the DISCOUNTED subtotal')));

    IF v_fee <> 0 THEN
        v_components := v_components || jsonb_build_array(jsonb_build_object(
            'kind', 'fee', 'source_kind', 'service_configuration',
            'source_id', v_service.configuration_version_id,
            'currency_code', v_currency, 'amount_minor', v_fee,
            'basis', jsonb_build_object('stage', 4, 'percentage', v_service.percentage,
                                        'rounding', v_service.rounding,
                                        'base_minor', v_base,
                                        'applies_to', to_jsonb(v_service.applies_to))));
    END IF;

    v_event := billing.append_event(
        p_tenant_id, p_outlet_id, v_bill, 'issued', p_user_id, NULL, NULL, NULL, NULL,
        jsonb_build_object('check_id', p_check_id,
                           'bill_number', v_number,
                           'bill_total_minor', v_total,
                           'currency_code', v_currency,
                           'locale', p_locale,
                           'calculation_version', billing.calculation_version(),
                           'components', v_components));
    PERFORM billing.apply_event(v_event);

    RETURN v_bill;
END;
$$;

COMMENT ON FUNCTION billing.issue_bill(uuid, uuid, uuid, uuid, menu.customer_locale) IS
    'FR-BIL-005 and FR-BIL-006. Four stages in a stated order — subtotal, discount, tax on '
    'the discounted subtotal, service charge on what it is configured to apply to — each '
    'recording its basis, and the whole carrying a calculation version so a disputed bill '
    'is recomputed as it was. It closes FR-ORD-003''s discount-and-tax interaction, which '
    'M3-A left open because the answer belongs to the bill.';


-- ---------------------------------------------------------------------------
-- Splitting, five ways, exactly (FR-BIL-003)
-- ---------------------------------------------------------------------------
-- money.allocate() does the arithmetic for the modes that DIVIDE, and the modes that
-- ENUMERATE — by item, by participant, custom amount — sum what already exists. The
-- deferred trigger above refuses any set of shares that does not sum to the total, so no
-- mode can lose or invent a minor unit whatever it does internally.

CREATE FUNCTION billing.split_equally(
    p_tenant_id uuid, p_bill_id uuid, p_payers integer
) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_bill billing.bill%ROWTYPE;
    v_part record;
    v_written integer := 0;
BEGIN
    SELECT * INTO v_bill FROM billing.bill
     WHERE tenant_id = p_tenant_id AND id = p_bill_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'BILL_NOT_FOUND: no bill % in scope', p_bill_id
            USING ERRCODE = 'HS404';
    END IF;

    DELETE FROM billing.bill_share WHERE tenant_id = p_tenant_id AND bill_id = p_bill_id;

    FOR v_part IN
        SELECT * FROM money.allocate(v_bill.bill_total_minor, p_payers)
    LOOP
        INSERT INTO billing.bill_share
            (tenant_id, outlet_id, bill_id, share_number, mode, currency_code, amount_minor)
        VALUES (p_tenant_id, v_bill.outlet_id, p_bill_id, v_part.part_index,
                'equal_share', v_bill.currency_code, v_part.part_amount);
        v_written := v_written + 1;
    END LOOP;

    RETURN v_written;
END;
$$;

COMMENT ON FUNCTION billing.split_equally(uuid, uuid, integer) IS
    'FR-BIL-003''s equal share. money.allocate() distributes the remainder one minor unit '
    'at a time across the first parts, so three payers on a total that does not divide by '
    'three get parts that sum to the total exactly. tests/m4a proves it across payer '
    'counts that do not divide evenly, which is the only case in which it could be wrong.';

CREATE FUNCTION billing.split_by_participant(p_tenant_id uuid, p_bill_id uuid)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_bill billing.bill%ROWTYPE;
    v_row  record;
    v_n    integer := 0;
    v_assigned bigint := 0;
BEGIN
    SELECT * INTO v_bill FROM billing.bill
     WHERE tenant_id = p_tenant_id AND id = p_bill_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'BILL_NOT_FOUND: no bill % in scope', p_bill_id
            USING ERRCODE = 'HS404';
    END IF;

    DELETE FROM billing.bill_share WHERE tenant_id = p_tenant_id AND bill_id = p_bill_id;

    -- Each participant's share of the SUBTOTAL, then the remainder — tax, discount and
    -- service charge — carried by the last share so the set still sums to the total.
    -- Apportioning the tax proportionally would look fairer and would round five ways;
    -- this rounds once, and the trigger proves the sum.
    FOR v_row IN
        SELECT l.participant_guest_session_id AS payer,
               sum(l.unit_amount_minor * a.quantity) AS amount
          FROM billing.check_allocation a
          JOIN ordering.order_line l
            ON l.tenant_id = a.tenant_id AND l.id = a.order_line_id
         WHERE a.tenant_id = p_tenant_id AND a.check_id = v_bill.check_id
         GROUP BY l.participant_guest_session_id
         ORDER BY l.participant_guest_session_id NULLS LAST
    LOOP
        v_n := v_n + 1;
        INSERT INTO billing.bill_share
            (tenant_id, outlet_id, bill_id, share_number, mode,
             participant_guest_session_id, currency_code, amount_minor)
        VALUES (p_tenant_id, v_bill.outlet_id, p_bill_id, v_n, 'by_participant',
                v_row.payer, v_bill.currency_code, v_row.amount);
        v_assigned := v_assigned + v_row.amount;
    END LOOP;

    IF v_n = 0 THEN
        RAISE EXCEPTION
            'SPLIT_HAS_NO_PARTICIPANT: check % allocates nothing, so there is nobody to '
            'split between', v_bill.check_id USING ERRCODE = 'HS409';
    END IF;

    UPDATE billing.bill_share
       SET amount_minor = amount_minor + (v_bill.bill_total_minor - v_assigned)
     WHERE tenant_id = p_tenant_id AND bill_id = p_bill_id AND share_number = v_n;

    RETURN v_n;
END;
$$;

CREATE FUNCTION billing.split_by_custom_amount(
    p_tenant_id uuid, p_bill_id uuid, p_amounts bigint[]
) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_bill billing.bill%ROWTYPE;
    v_sum  bigint := 0;
    v_i    integer;
BEGIN
    SELECT * INTO v_bill FROM billing.bill
     WHERE tenant_id = p_tenant_id AND id = p_bill_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'BILL_NOT_FOUND: no bill % in scope', p_bill_id
            USING ERRCODE = 'HS404';
    END IF;

    SELECT coalesce(sum(v), 0) INTO v_sum FROM unnest(p_amounts) AS v;
    IF v_sum <> v_bill.bill_total_minor THEN
        RAISE EXCEPTION
            'SPLIT_NOT_EXACT: the custom amounts sum to % and the bill total is %. A '
            'custom split states what each payer owes and the statement has to add up',
            v_sum, v_bill.bill_total_minor
            USING ERRCODE = 'HS409';
    END IF;

    DELETE FROM billing.bill_share WHERE tenant_id = p_tenant_id AND bill_id = p_bill_id;

    FOR v_i IN 1 .. array_length(p_amounts, 1) LOOP
        INSERT INTO billing.bill_share
            (tenant_id, outlet_id, bill_id, share_number, mode, currency_code, amount_minor)
        VALUES (p_tenant_id, v_bill.outlet_id, p_bill_id, v_i, 'custom_amount',
                v_bill.currency_code, p_amounts[v_i]);
    END LOOP;

    RETURN array_length(p_amounts, 1);
END;
$$;


-- ---------------------------------------------------------------------------
-- Disposition and finalization (FR-BIL-008)
-- ---------------------------------------------------------------------------

CREATE FUNCTION billing.record_disposition(
    p_tenant_id uuid, p_outlet_id uuid, p_bill_id uuid,
    p_kind billing.disposition_kind, p_amount_minor bigint,
    p_override_id uuid, p_reason_code_id uuid, p_reason_text text,
    p_actor_user_id uuid, p_transferred_to_check_id uuid DEFAULT NULL
) RETURNS uuid
-- SECURITY DEFINER for the reason billing.issue_bill() records: it writes the bill
-- projection, and the application role holds no write grant on it. The grant and the
-- fold's marker remain two independent locks, and row level security is FORCED and
-- unaffected.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, billing, ordering, config, money, menu, service, public
AS $$
DECLARE
    v_id uuid;
    v_outstanding bigint;
BEGIN
    v_outstanding := billing.outstanding_balance(p_tenant_id, p_bill_id);
    IF p_amount_minor > v_outstanding THEN
        RAISE EXCEPTION
            'DISPOSITION_EXCEEDS_BALANCE: % against an outstanding balance of %. '
            'Disposing of more than is owed writes off money nobody was charged',
            p_amount_minor, v_outstanding USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO billing.bill_disposition
        (tenant_id, outlet_id, bill_id, kind, currency_code, amount_minor, override_id,
         reason_code_id, reason_text, actor_user_id, transferred_to_check_id)
    SELECT p_tenant_id, p_outlet_id, p_bill_id, p_kind, b.currency_code, p_amount_minor,
           p_override_id, p_reason_code_id, p_reason_text, p_actor_user_id,
           p_transferred_to_check_id
      FROM billing.bill b
     WHERE b.tenant_id = p_tenant_id AND b.id = p_bill_id
    RETURNING id INTO v_id;

    PERFORM billing.apply_event(billing.append_event(
        p_tenant_id, p_outlet_id, p_bill_id, 'disposition_recorded', p_actor_user_id,
        p_override_id, p_reason_code_id, p_reason_text, NULL,
        jsonb_build_object('kind', p_kind, 'amount_minor', p_amount_minor)));

    RETURN v_id;
END;
$$;

CREATE FUNCTION billing.finalize_bill(
    p_tenant_id uuid, p_outlet_id uuid, p_bill_id uuid, p_actor_user_id uuid
) RETURNS void
-- SECURITY DEFINER for the reason billing.issue_bill() records: it writes the bill
-- projection, and the application role holds no write grant on it. The grant and the
-- fold's marker remain two independent locks, and row level security is FORCED and
-- unaffected.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, billing, ordering, config, money, menu, service, public
AS $$
DECLARE
    v_outstanding bigint;
    v_tips        bigint;
BEGIN
    v_outstanding := billing.outstanding_balance(p_tenant_id, p_bill_id);
    IF v_outstanding IS NULL THEN
        RAISE EXCEPTION 'BILL_NOT_FOUND: no bill % in scope', p_bill_id
            USING ERRCODE = 'HS404';
    END IF;

    -- THE TIP DOES NOT COUNT. This is FR-BIL-008's second sentence and NC-M4-002: tip
    -- completion is recorded separately and cannot hide an unpaid bill balance. The tips
    -- are read here for one purpose only — to say so in the refusal, so that a cashier
    -- looking at a screen showing money received understands why the bill is still open.
    SELECT coalesce(sum(t.amount_minor), 0) INTO v_tips
      FROM billing.tip t
      JOIN billing.bill_share s ON s.tenant_id = t.tenant_id AND s.id = t.bill_share_id
     WHERE s.tenant_id = p_tenant_id AND s.bill_id = p_bill_id;

    IF v_outstanding > 0 THEN
        RAISE EXCEPTION
            'BILL_FINALIZED_UNSETTLED: bill % still owes % and cannot be finalized. Tips '
            'of % are attached to it and count for nothing here: a tip is not part of the '
            'bill balance, and a bill that looked settled because somebody tipped is the '
            'defect FR-BIL-008 exists to prevent',
            p_bill_id, v_outstanding, v_tips
            USING ERRCODE = 'HS409';
    END IF;

    PERFORM billing.apply_event(billing.append_event(
        p_tenant_id, p_outlet_id, p_bill_id, 'finalized', p_actor_user_id));

    UPDATE billing.check SET state = 'billed', closed_at = now()
     WHERE tenant_id = p_tenant_id
       AND id = (SELECT check_id FROM billing.bill
                  WHERE tenant_id = p_tenant_id AND id = p_bill_id);
END;
$$;

COMMENT ON FUNCTION billing.finalize_bill(uuid, uuid, uuid, uuid) IS
    'FR-BIL-008. Finalizes only when the outstanding balance is nil. It reads the tips '
    'attached to the bill for exactly one reason: to name them in the refusal, so that '
    '"money was received and the bill is still open" reads as the deliberate rule it is '
    'rather than as a bug.';


-- ---------------------------------------------------------------------------
-- Correction: void, credit, reissue — never deletion (FR-BIL-009)
-- ---------------------------------------------------------------------------

CREATE FUNCTION billing.void_bill(
    p_tenant_id uuid, p_outlet_id uuid, p_bill_id uuid,
    p_override_id uuid, p_reason_code_id uuid, p_reason_text text, p_actor_user_id uuid
) RETURNS void
-- SECURITY DEFINER for the reason billing.issue_bill() records: it writes the bill
-- projection, and the application role holds no write grant on it. The grant and the
-- fold's marker remain two independent locks, and row level security is FORCED and
-- unaffected.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, billing, ordering, config, money, menu, service, public
AS $$
BEGIN
    IF btrim(coalesce(p_reason_text, '')) = '' OR p_reason_code_id IS NULL THEN
        RAISE EXCEPTION
            'DESTRUCTIVE_ACTION_WITHOUT_REASON: voiding an issued bill states a reason '
            'code and a reason' USING ERRCODE = 'HS400';
    END IF;

    PERFORM billing.apply_event(billing.append_event(
        p_tenant_id, p_outlet_id, p_bill_id, 'voided',
        p_actor_user_id, p_override_id, p_reason_code_id, p_reason_text));
END;
$$;

CREATE FUNCTION billing.reissue_bill(
    p_tenant_id uuid, p_outlet_id uuid, p_bill_id uuid,
    p_override_id uuid, p_reason_code_id uuid, p_reason_text text, p_actor_user_id uuid
) RETURNS uuid
-- SECURITY DEFINER for the reason billing.issue_bill() records: it writes the bill
-- projection, and the application role holds no write grant on it. The grant and the
-- fold's marker remain two independent locks, and row level security is FORCED and
-- unaffected.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, billing, ordering, config, money, menu, service, public
AS $$
DECLARE
    v_check uuid;
    v_new   uuid;
    v_locale menu.customer_locale;
BEGIN
    SELECT check_id, locale INTO v_check, v_locale FROM billing.bill
     WHERE tenant_id = p_tenant_id AND id = p_bill_id;
    IF v_check IS NULL THEN
        RAISE EXCEPTION 'BILL_NOT_FOUND: no bill % in scope', p_bill_id
            USING ERRCODE = 'HS404';
    END IF;

    PERFORM billing.void_bill(p_tenant_id, p_outlet_id, p_bill_id, p_override_id,
                              p_reason_code_id, p_reason_text, p_actor_user_id);

    -- The check reopens so the replacement can be issued from it. What it may NOT do is
    -- reopen with allocations that would bill a unit twice, and the revival trigger on
    -- billing.check refuses exactly that.
    UPDATE billing.check SET state = 'open', closed_at = NULL
     WHERE tenant_id = p_tenant_id AND id = v_check;

    v_new := billing.issue_bill(p_tenant_id, p_outlet_id, v_check, p_actor_user_id, v_locale);

    PERFORM billing.apply_event(billing.append_event(
        p_tenant_id, p_outlet_id, v_new, 'reissued',
        p_actor_user_id, p_override_id, p_reason_code_id, p_reason_text, NULL,
        jsonb_build_object('supersedes', p_bill_id)));

    RETURN v_new;
END;
$$;

COMMENT ON FUNCTION billing.reissue_bill(uuid, uuid, uuid, uuid, uuid, text, uuid) IS
    'FR-BIL-009. The original is voided and stays, the replacement names what it '
    'supersedes, and the chain is walkable both ways. Nothing is deleted — '
    'billing.bill_event refuses that outright, and the projection cannot be written '
    'except by the fold.';


-- ---------------------------------------------------------------------------
-- Merge and split of checks (FR-BIL-004, FR-TAB-007B)
-- ---------------------------------------------------------------------------

CREATE FUNCTION billing.merge_checks(
    p_tenant_id uuid, p_outlet_id uuid, p_target_check_id uuid, p_source_check_id uuid
) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_moved integer;
BEGIN
    IF p_target_check_id = p_source_check_id THEN
        RAISE EXCEPTION 'CHECK_MERGED_INTO_ITSELF: a check cannot absorb itself'
            USING ERRCODE = 'HS400';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM billing.check
                    WHERE tenant_id = p_tenant_id AND id = p_target_check_id
                      AND state = 'open') THEN
        RAISE EXCEPTION
            'CHECK_NOT_OPEN: a merge target must be open; check % is not',
            p_target_check_id USING ERRCODE = 'HS409';
    END IF;

    UPDATE billing.check_allocation
       SET check_id = p_target_check_id
     WHERE tenant_id = p_tenant_id AND check_id = p_source_check_id;
    GET DIAGNOSTICS v_moved = ROW_COUNT;

    -- The source keeps its identity and records where it went. FR-BIL-004 asks for the
    -- original SOURCE RELATIONSHIPS to be preserved, and a source that vanished would
    -- leave the merged check unable to say what it was made of.
    UPDATE billing.check
       SET state = 'merged', merged_into_check_id = p_target_check_id, closed_at = now()
     WHERE tenant_id = p_tenant_id AND id = p_source_check_id;

    RETURN v_moved;
END;
$$;

CREATE FUNCTION billing.split_check(
    p_tenant_id uuid, p_outlet_id uuid, p_source_check_id uuid,
    p_order_line_ids uuid[], p_user_id uuid
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_session uuid;
    v_new     uuid;
BEGIN
    SELECT table_session_id INTO v_session FROM billing.check
     WHERE tenant_id = p_tenant_id AND id = p_source_check_id;
    IF v_session IS NULL THEN
        RAISE EXCEPTION 'CHECK_NOT_FOUND: no check % in scope', p_source_check_id
            USING ERRCODE = 'HS404';
    END IF;

    v_new := billing.open_check(p_tenant_id, p_outlet_id, v_session, p_user_id);

    UPDATE billing.check SET split_from_check_id = p_source_check_id
     WHERE tenant_id = p_tenant_id AND id = v_new;

    UPDATE billing.check_allocation
       SET check_id = v_new
     WHERE tenant_id = p_tenant_id AND check_id = p_source_check_id
       AND order_line_id = ANY (p_order_line_ids);

    RETURN v_new;
END;
$$;

COMMENT ON FUNCTION billing.split_check(uuid, uuid, uuid, uuid[], uuid) IS
    'FR-TAB-007B. A merged session splits into separate checks with correct allocation '
    'and a complete audit trail: the new check names what it split from, the allocations '
    'MOVE rather than being copied — so no unit is billed twice, which the deferred '
    'trigger proves at commit — and the census of billed units is unchanged.';

CREATE FUNCTION billing.split_by_item(
    p_tenant_id uuid, p_bill_id uuid, p_assignments jsonb
) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_bill     billing.bill%ROWTYPE;
    v_n        integer := 0;
    v_assigned bigint := 0;
    v_amount   bigint;
    v_group    jsonb;
    v_missing  integer;
    v_extra    integer;
BEGIN
    SELECT * INTO v_bill FROM billing.bill
     WHERE tenant_id = p_tenant_id AND id = p_bill_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'BILL_NOT_FOUND: no bill % in scope', p_bill_id
            USING ERRCODE = 'HS404';
    END IF;

    IF jsonb_typeof(p_assignments) <> 'array' THEN
        RAISE EXCEPTION
            'SPLIT_ASSIGNMENT_MALFORMED: by-item assignments are an array of arrays of '
            'order line ids, one array per payer'
            USING ERRCODE = 'HS400';
    END IF;

    -- EVERY allocated line is assigned, and no line is assigned twice. Without this the
    -- last share silently absorbs whatever was left out, so a forgotten line would look
    -- like a rounding remainder and the trigger below would pass. That is the failure a
    -- by-item split is uniquely exposed to: it ENUMERATES rather than divides, and an
    -- enumeration can be incomplete in a way a division cannot.
    WITH allocated AS (
        SELECT order_line_id FROM billing.check_allocation
         WHERE tenant_id = p_tenant_id AND check_id = v_bill.check_id
    ), assigned AS (
        SELECT (line #>> '{}')::uuid AS order_line_id
          FROM jsonb_array_elements(p_assignments) AS grp,
               LATERAL jsonb_array_elements(grp) AS t(line)
    )
    SELECT (SELECT count(*) FROM allocated a
             WHERE NOT EXISTS (SELECT 1 FROM assigned s
                                WHERE s.order_line_id = a.order_line_id)),
           (SELECT count(*) FROM assigned s
             WHERE NOT EXISTS (SELECT 1 FROM allocated a
                                WHERE a.order_line_id = s.order_line_id))
      INTO v_missing, v_extra;

    IF v_missing > 0 OR v_extra > 0 THEN
        RAISE EXCEPTION
            'SPLIT_NOT_EXACT: a by-item split must assign every line the check bills and '
            'nothing else; % allocated line(s) were left unassigned and % assigned line(s) '
            'are not on this check', v_missing, v_extra
            USING ERRCODE = 'HS409';
    END IF;

    DELETE FROM billing.bill_share WHERE tenant_id = p_tenant_id AND bill_id = p_bill_id;

    FOR v_group IN SELECT * FROM jsonb_array_elements(p_assignments) LOOP
        SELECT coalesce(sum(l.unit_amount_minor * a.quantity), 0) INTO v_amount
          FROM billing.check_allocation a
          JOIN ordering.order_line l
            ON l.tenant_id = a.tenant_id AND l.id = a.order_line_id
         WHERE a.tenant_id = p_tenant_id AND a.check_id = v_bill.check_id
           AND a.order_line_id IN (
               SELECT (value #>> '{}')::uuid FROM jsonb_array_elements(v_group));

        v_n := v_n + 1;
        INSERT INTO billing.bill_share
            (tenant_id, outlet_id, bill_id, share_number, mode, currency_code, amount_minor)
        VALUES (p_tenant_id, v_bill.outlet_id, p_bill_id, v_n, 'by_item',
                v_bill.currency_code, v_amount);
        v_assigned := v_assigned + v_amount;
    END LOOP;

    IF v_n = 0 THEN
        RAISE EXCEPTION
            'SPLIT_HAS_NO_PARTICIPANT: a by-item split with no payer divides a bill '
            'between nobody' USING ERRCODE = 'HS409';
    END IF;

    -- The shares above cover the SUBTOTAL. Tax, discount and service charge are computed
    -- once on the whole document, so they are carried by the last share rather than
    -- apportioned and rounded once per payer. One rounding, and the trigger proves the sum.
    UPDATE billing.bill_share
       SET amount_minor = amount_minor + (v_bill.bill_total_minor - v_assigned)
     WHERE tenant_id = p_tenant_id AND bill_id = p_bill_id AND share_number = v_n;

    RETURN v_n;
END;
$$;

COMMENT ON FUNCTION billing.split_by_item(uuid, uuid, jsonb) IS
    'FR-BIL-003''s by-item split. It refuses an assignment that does not cover the '
    'check exactly, because a by-item split enumerates rather than divides and an '
    'enumeration that omitted a line would be absorbed by the remainder and never seen.';

CREATE FUNCTION billing.split_by_separate_orders(p_tenant_id uuid, p_bill_id uuid)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_bill     billing.bill%ROWTYPE;
    v_row      record;
    v_n        integer := 0;
    v_assigned bigint := 0;
BEGIN
    SELECT * INTO v_bill FROM billing.bill
     WHERE tenant_id = p_tenant_id AND id = p_bill_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'BILL_NOT_FOUND: no bill % in scope', p_bill_id
            USING ERRCODE = 'HS404';
    END IF;

    DELETE FROM billing.bill_share WHERE tenant_id = p_tenant_id AND bill_id = p_bill_id;

    FOR v_row IN
        SELECT a.order_id,
               sum(l.unit_amount_minor * a.quantity) AS amount
          FROM billing.check_allocation a
          JOIN ordering.order_line l
            ON l.tenant_id = a.tenant_id AND l.id = a.order_line_id
         WHERE a.tenant_id = p_tenant_id AND a.check_id = v_bill.check_id
         GROUP BY a.order_id
         ORDER BY a.order_id
    LOOP
        v_n := v_n + 1;
        INSERT INTO billing.bill_share
            (tenant_id, outlet_id, bill_id, share_number, mode, currency_code, amount_minor)
        VALUES (p_tenant_id, v_bill.outlet_id, p_bill_id, v_n, 'separate_orders',
                v_bill.currency_code, v_row.amount);
        v_assigned := v_assigned + v_row.amount;
    END LOOP;

    IF v_n = 0 THEN
        RAISE EXCEPTION
            'SPLIT_HAS_NO_PARTICIPANT: check % allocates nothing, so there are no separate '
            'orders to split into', v_bill.check_id USING ERRCODE = 'HS409';
    END IF;

    UPDATE billing.bill_share
       SET amount_minor = amount_minor + (v_bill.bill_total_minor - v_assigned)
     WHERE tenant_id = p_tenant_id AND bill_id = p_bill_id AND share_number = v_n;

    RETURN v_n;
END;
$$;

COMMENT ON FUNCTION billing.split_by_separate_orders(uuid, uuid) IS
    'FR-BIL-003''s separate-orders split. One share per order on the check — the case '
    'where two parties shared a table and each ordered for themselves. The grouping is '
    'the order id the allocation already carries, so nothing has to be re-decided.';


-- ===========================================================================
-- The bill summary a guest reads (FR-BIL-007, FR-I18N-001B)
-- ===========================================================================
-- Identity here, approved bodies in menu.translation under entity
-- 'bill_component_wording'. The same arrangement 0017 took for order status, and for the
-- same reason: a second translation store is a second thing nobody reviews, and a bill
-- is the last document on which an unreviewed sentence should appear.

CREATE TABLE billing.component_wording (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL,

    -- Nullable and NULL in practice, exactly as notify.status_wording carries one: a
    -- tenant-wide row scopes on the tenant because its outlet is NULL, which is the case
    -- app.row_in_scope() accepts, so the isolation policy over this schema stays one
    -- unbranched predicate.
    outlet_id   uuid,

    kind        ordering.charge_kind NOT NULL,
    source_text text NOT NULL,

    status      org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version bigint NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT component_wording_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT component_wording_one_per_kind UNIQUE (tenant_id, kind),
    CONSTRAINT component_wording_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT component_wording_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT component_wording_source_not_blank CHECK (btrim(source_text) <> ''),
    CONSTRAINT component_wording_row_version_positive CHECK (row_version > 0)
);

CREATE TRIGGER component_wording_row_version
    BEFORE UPDATE ON billing.component_wording
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

COMMENT ON TABLE billing.component_wording IS
    'FR-BIL-007. What a bill calls each of its components, in the language the order was '
    'placed in. Identity and the English source only; the Amharic and Arabic live in '
    'menu.translation where a person has to review and approve them. No migration writes '
    'one, because an approved translation asserts that somebody read it.';

CREATE FUNCTION billing.component_wording_for(
    p_tenant_id uuid, p_kind ordering.charge_kind, p_locale menu.customer_locale
) RETURNS text
LANGUAGE sql STABLE
AS $$
    SELECT coalesce(
        (SELECT tr.translated_text
           FROM menu.translation tr
          WHERE tr.tenant_id = p_tenant_id
            AND tr.entity = 'bill_component_wording'
            AND tr.entity_id = w.id
            AND tr.field_name = 'label'
            AND tr.locale = p_locale
            AND tr.state = 'approved'),
        CASE WHEN p_locale = 'en' THEN w.source_text END)
      FROM billing.component_wording w
     WHERE w.tenant_id = p_tenant_id AND w.kind = p_kind AND w.status = 'active';
$$;

-- ---------------------------------------------------------------------------
-- The summary itself
-- ---------------------------------------------------------------------------
-- TWO FUNCTIONS, AND THAT IS THE REQUIREMENT.
--
-- billing.bill_preview_lines() renders the bill: components and the total. It does not
-- read billing.tip, cannot be made to without a migration, and tests/m4a asserts that
-- from pg_proc's source rather than from this sentence.
--
-- billing.tip_options() renders the tip box: suggestions and what each would come to.
-- It takes a SHARE, not a bill, because FR-BIL-015 gives each payer their own optional
-- tip. It returns no selection and there is nowhere for one to come from.
--
-- FR-BIL-007 says the tip box appears only AFTER OR BESIDE the bill summary, never
-- inside it. Two functions with no call between them is what makes a surface that put
-- one inside the other have to construct it deliberately, and NC-M4-002 plants exactly
-- that construction.

CREATE FUNCTION billing.bill_preview_lines(p_tenant_id uuid, p_bill_id uuid)
RETURNS TABLE (
    stage         integer,
    kind          ordering.charge_kind,
    label         text,
    currency_code char(3),
    amount_minor  bigint
)
LANGUAGE sql STABLE
AS $$
    SELECT (c.basis ->> 'stage')::integer,
           c.kind,
           coalesce(billing.component_wording_for(c.tenant_id, c.kind, b.locale),
                    replace(c.kind::text, '_', ' ')),
           c.currency_code,
           c.amount_minor
      FROM billing.bill_component c
      JOIN billing.bill b ON b.tenant_id = c.tenant_id AND b.id = c.bill_id
     WHERE c.tenant_id = p_tenant_id AND c.bill_id = p_bill_id
     ORDER BY (c.basis ->> 'stage')::integer;
$$;

COMMENT ON FUNCTION billing.bill_preview_lines(uuid, uuid) IS
    'FR-BIL-007''s translated bill summary: the components in the order they were '
    'computed, labelled in the language the order was placed in, with the approved '
    'English as the fallback and the kind''s own name as the last resort. IT DOES NOT '
    'READ billing.tip — the tip box is billing.tip_options(), a separate call, so a '
    'surface that put a tip inside the summary would have to write that itself.';

CREATE FUNCTION billing.bill_summary(p_tenant_id uuid, p_bill_id uuid)
RETURNS TABLE (
    bill_number         text,
    state               billing.bill_state,
    currency_code       char(3),
    bill_total_minor    bigint,
    disposed_minor      bigint,
    outstanding_minor   bigint,
    calculation_version text,
    locale              menu.customer_locale,
    issued_at           timestamptz,
    finalized_at        timestamptz
)
LANGUAGE sql STABLE
AS $$
    SELECT b.bill_number, b.state, b.currency_code, b.bill_total_minor,
           b.disposed_minor,
           billing.outstanding_balance(b.tenant_id, b.id),
           b.calculation_version, b.locale, b.issued_at, b.finalized_at
      FROM billing.bill b
     WHERE b.tenant_id = p_tenant_id AND b.id = p_bill_id;
$$;

COMMENT ON FUNCTION billing.bill_summary(uuid, uuid) IS
    'FR-BIL-005 through FR-BIL-008. The header of the document: what it totals, what has '
    'been disposed of, what is still outstanding, and THE CALCULATION VERSION it was '
    'computed under. There is no tip figure and no total-tendered figure here; both are '
    'other records (FR-BIL-014), and M4-B supplies the tender.';

CREATE FUNCTION billing.tip_options(p_tenant_id uuid, p_bill_share_id uuid)
RETURNS TABLE (
    display_order integer,
    percentage    money.percentage,
    currency_code char(3),
    amount_minor  bigint
)
LANGUAGE sql STABLE
AS $$
    SELECT s.display_order, s.percentage, sh.currency_code,
           money.apply_rate(sh.amount_minor, s.percentage, 'half_up')
      FROM billing.bill_share sh
      JOIN billing.tip_setting t
        ON t.tenant_id = sh.tenant_id AND t.outlet_id = sh.outlet_id AND t.offered
      JOIN billing.tip_suggestion s
        ON s.tenant_id = t.tenant_id AND s.outlet_id = t.outlet_id
     WHERE sh.tenant_id = p_tenant_id AND sh.id = p_bill_share_id
     ORDER BY s.display_order;
$$;

COMMENT ON FUNCTION billing.tip_options(uuid, uuid) IS
    'FR-BIL-013 and FR-BIL-015. What one payer may tap, computed on THEIR share rather '
    'than on the bill, so a per-payer tip needs no reallocation of bill lines to exist. '
    'THE RESULT HAS NO SELECTED COLUMN: no tip is selected by default, and there is '
    'nowhere in the model for a default to be stated. NC-M4-001 plants the preselection '
    'on the surface, which is the only place left that could do it.';


-- ===========================================================================
-- What staff see (FR-POS-004, FR-BIL-001)
-- ===========================================================================

CREATE FUNCTION billing.check_view(p_tenant_id uuid, p_outlet_id uuid, p_table_session_id uuid)
RETURNS TABLE (
    check_id        uuid,
    check_number    text,
    state           billing.check_state,
    allocated_lines integer,
    allocated_units integer,
    currency_code   char(3),
    allocated_minor bigint,
    bill_id         uuid,
    bill_state      billing.bill_state,
    outstanding_minor bigint
)
LANGUAGE sql STABLE
AS $$
    SELECT c.id, c.check_number, c.state,
           (SELECT count(*)::integer FROM billing.check_allocation a
             WHERE a.tenant_id = c.tenant_id AND a.check_id = c.id),
           (SELECT coalesce(sum(a.quantity), 0)::integer FROM billing.check_allocation a
             WHERE a.tenant_id = c.tenant_id AND a.check_id = c.id),
           (SELECT min(l.currency_code) FROM billing.check_allocation a
              JOIN ordering.order_line l
                ON l.tenant_id = a.tenant_id AND l.id = a.order_line_id
             WHERE a.tenant_id = c.tenant_id AND a.check_id = c.id),
           (SELECT coalesce(sum(l.unit_amount_minor * a.quantity), 0)
              FROM billing.check_allocation a
              JOIN ordering.order_line l
                ON l.tenant_id = a.tenant_id AND l.id = a.order_line_id
             WHERE a.tenant_id = c.tenant_id AND a.check_id = c.id),
           b.id, b.state,
           CASE WHEN b.id IS NULL THEN NULL
                ELSE billing.outstanding_balance(b.tenant_id, b.id) END
      FROM billing.check c
      LEFT JOIN LATERAL (
           SELECT bb.id, bb.state, bb.tenant_id
             FROM billing.bill bb
            WHERE bb.tenant_id = c.tenant_id AND bb.check_id = c.id
              AND bb.state <> 'voided'
            ORDER BY bb.issued_at DESC LIMIT 1) b ON true
     WHERE c.tenant_id = p_tenant_id
       AND c.outlet_id = p_outlet_id
       AND c.table_session_id = p_table_session_id
     ORDER BY c.check_number;
$$;

COMMENT ON FUNCTION billing.check_view(uuid, uuid, uuid) IS
    'FR-BIL-001. The checks on one table session, what each bills for, and the live bill '
    'if one has been issued. The allocated figure is derived from the order''s own '
    'snapshot every time it is read, so it cannot drift from what the guest agreed to.';

-- The session's unpaid balance, which pos.table_view() has carried a slot for since M3-D.
-- A session owes what its live bills still owe. A voided bill owes nothing — it was
-- replaced — and a check with no bill yet owes nothing either, because nobody has been
-- asked for money. Both exclusions are why this is a function rather than a sum somebody
-- writes inline twice and gets differently the second time.
CREATE FUNCTION billing.session_outstanding(p_tenant_id uuid, p_table_session_id uuid)
RETURNS bigint
LANGUAGE sql STABLE
AS $$
    SELECT coalesce(sum(billing.outstanding_balance(b.tenant_id, b.id)), 0)
      FROM billing.bill b
      JOIN billing.check c ON c.tenant_id = b.tenant_id AND c.id = b.check_id
     WHERE b.tenant_id = p_tenant_id
       AND c.table_session_id = p_table_session_id
       AND b.state IN ('issued', 'finalized', 'reissued');
$$;

COMMENT ON FUNCTION billing.session_outstanding(uuid, uuid) IS
    'FR-POS-004''s unpaid balance for one table session. It is billing.outstanding_balance() '
    'summed over the session''s live bills, so it inherits that function''s one relevant '
    'property: IT DOES NOT READ billing.tip. A tip is not a payment and must not make a '
    'table look settled on the floor plan any more than on the bill.';


-- ===========================================================================
-- Rebuild (FR-DAT-010)
-- ===========================================================================
-- THE PROOF THAT THE LEDGER IS THE TRUTH.
--
-- Every earlier gate that folded a ledger provided this, and for the same reason: a
-- projection nobody can reproduce is a second copy of the truth that nobody can check
-- against the first. Here it is also what makes the projection guard's refusal honest —
-- "a projection written behind its ledger is one a rebuild puts back" is a claim about a
-- mechanism, and this is the mechanism.
--
-- The replay is ordered by EVENT ID across every bill, not by sequence within one. A
-- reissue writes the correction chain across two documents, so the replacement's event
-- has to arrive after both bills exist; a per-bill replay would fold one bill completely
-- and hit a foreign key into a bill that had not been written yet.

CREATE FUNCTION billing.drop_projections_for_rebuild(p_tenant_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, billing, public
AS $$
BEGIN
    PERFORM set_config('billing.applying_event', 'yes', true);
    DELETE FROM billing.bill_component WHERE tenant_id = p_tenant_id;
    -- The links first, then the rows: bill.supersedes_bill_id and reissued_as_bill_id
    -- point INTO this table, so a delete that did not clear them first would be refused
    -- by the very foreign key that makes the correction chain walkable.
    UPDATE billing.bill SET supersedes_bill_id = NULL, reissued_as_bill_id = NULL
     WHERE tenant_id = p_tenant_id;
    DELETE FROM billing.bill WHERE tenant_id = p_tenant_id;
    PERFORM set_config('billing.applying_event', '', true);
END;
$$;

CREATE FUNCTION billing.rebuild_projections(p_tenant_id uuid) RETURNS integer
-- SECURITY DEFINER, and NOT as a convenience: the loop below and billing.apply_event()
-- must run as the SAME role or they see different ledgers. apply_event() is definer
-- because it writes the projection; a caller who is a superuser therefore SELECTs every
-- event and hands ids to a function that, under FORCE ROW LEVEL SECURITY, can see none
-- of them — and the rebuild dies on LEDGER_EVENT_ABSENT for an event that is plainly
-- there. Two roles reading one ledger is the defect; one role reading it is the fix.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, billing, ordering, config, money, menu, service, public
AS $$
DECLARE
    v_event bigint;
    v_count integer := 0;
    v_available integer;
BEGIN
    -- A REBUILD THAT SEES NOTHING IS NOT A REBUILD. Row level security scopes this to
    -- the caller's tenant AND outlet, so a caller who set a tenant and no outlet can see
    -- no outlet-scoped event at all — and would drop the projections, fold nothing, and
    -- report success. A census taken either side of that compares empty with empty and
    -- agrees. So it refuses instead.
    SELECT count(*) INTO v_available FROM billing.bill_event
     WHERE tenant_id = p_tenant_id;
    IF v_available = 0 THEN
        RAISE EXCEPTION
            'REBUILD_SEES_NO_LEDGER: no bill event is in scope for tenant %. A rebuild '
            'that folds nothing looks identical to one that folded everything correctly, '
            'which is the one outcome this operation must not be able to produce. Set the '
            'outlet context, or there is genuinely nothing to rebuild',
            p_tenant_id USING ERRCODE = 'HS409';
    END IF;

    PERFORM billing.drop_projections_for_rebuild(p_tenant_id);

    FOR v_event IN
        SELECT id FROM billing.bill_event
         WHERE tenant_id = p_tenant_id
         ORDER BY id
    LOOP
        PERFORM billing.apply_event(v_event);
        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION billing.rebuild_projections(uuid) IS
    'FR-DAT-010. Drops billing''s projections and folds them back from the ledger. '
    'tests/m4a rebuilds a tenant''s bills and compares the census — every bill, every '
    'component, every amount and every calculation version — before and after, because '
    'a rebuild that produced a DIFFERENT bill would be worse than no rebuild at all.';

-- ===========================================================================
-- Numbering a check and a bill (FR-BIL-001, FR-BIL-005)
-- ===========================================================================
-- One series per outlet per year for each of the two documents, created for the outlets
-- that exist and by trigger for the ones that arrive later — the arrangement 0010 built
-- for the order number, and for the same reason: an outlet must not open its first check
-- and discover it has no way to number it.
--
-- 'check' is not new. M1's seed wrote one for the three outlets it created and nothing
-- has issued from it since except M1-C's gapless-numbering proof. What it never had was
-- the TRIGGER, so every outlet created after that seed — M3-C's district outlet among
-- them — has an order series and no check series. That gap was invisible while nothing
-- opened a check. This slice opens checks.
--
-- The prefix carries the outlet's reference code for the reason 0010 records:
-- config.issued_document_number is unique per tenant with no outlet in the key, so a
-- constant prefix collides on the second outlet's first document.

CREATE FUNCTION config.install_billing_number_series() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.kind = 'outlet' THEN
        INSERT INTO config.number_series
            (tenant_id, outlet_id, document_type, fiscal_period, prefix, next_value)
        VALUES (NEW.tenant_id, NEW.id, 'check', to_char(now(), 'YYYY'),
                'CHK-' || NEW.reference_code || '-', 1),
               (NEW.tenant_id, NEW.id, 'bill', to_char(now(), 'YYYY'),
                'BIL-' || NEW.reference_code || '-', 1)
        ON CONFLICT DO NOTHING;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER outlet_install_billing_number_series
    AFTER INSERT ON org.org_node
    FOR EACH ROW EXECUTE FUNCTION config.install_billing_number_series();

INSERT INTO config.number_series
    (tenant_id, outlet_id, document_type, fiscal_period, prefix, next_value)
SELECT n.tenant_id, n.id, d.document_type, to_char(now(), 'YYYY'),
       d.prefix || n.reference_code || '-', 1
FROM org.org_node n
CROSS JOIN (VALUES ('check', 'CHK-'), ('bill', 'BIL-')) AS d(document_type, prefix)
WHERE n.kind = 'outlet'
  AND NOT EXISTS (
      SELECT 1 FROM config.number_series s
      WHERE s.tenant_id = n.tenant_id AND s.outlet_id = n.id
        AND s.document_type = d.document_type
        AND s.fiscal_period = to_char(now(), 'YYYY'));

GRANT EXECUTE ON FUNCTION config.install_billing_number_series() TO hospitality_migrator;

-- ===========================================================================
-- Row level security
-- ===========================================================================
-- Every table in billing, ENABLED and FORCED, under the one predicate M1-A built and
-- enumerated by query rather than listed — so a table a later slice adds to this schema
-- is covered the moment it exists rather than the moment somebody remembers.
--
-- There is no branch here, unlike the pos loop at M3-D. billing.component_wording is the
-- one tenant-wide table and it carries a NULL outlet_id, which app.row_in_scope() already
-- scopes on the tenant alone. That was the lesson of pos.confirmation_requirement: a
-- table with no outlet COLUMN forces a second policy shape, and a table with a nullable
-- outlet column does not.

DO $$
DECLARE t text;
BEGIN
    FOR t IN
        SELECT format('%I.%I', schemaname, tablename)
        FROM pg_tables WHERE schemaname = 'billing'
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

GRANT USAGE ON SCHEMA billing TO hospitality_app;

-- Read models the surfaces call.
GRANT SELECT ON billing.check              TO hospitality_app;
GRANT SELECT ON billing.check_allocation   TO hospitality_app;
GRANT SELECT ON billing.bill               TO hospitality_app;
GRANT SELECT ON billing.bill_component     TO hospitality_app;
GRANT SELECT ON billing.bill_share         TO hospitality_app;
GRANT SELECT ON billing.bill_event         TO hospitality_app;
GRANT SELECT ON billing.bill_disposition   TO hospitality_app;
GRANT SELECT ON billing.tip                TO hospitality_app;
GRANT SELECT ON billing.tip_correction     TO hospitality_app;
GRANT SELECT ON billing.tip_setting        TO hospitality_app;
GRANT SELECT ON billing.tip_suggestion     TO hospitality_app;
GRANT SELECT ON billing.service_charge_setting TO hospitality_app;
GRANT SELECT ON billing.component_wording  TO hospitality_app;

-- billing.bill and billing.bill_component take NO write grant at all. They are folded,
-- and the fold runs inside functions the application calls rather than in the
-- application. The grant and the projection trigger are two independent locks: remove
-- the trigger and the grant still refuses, remove the grant and the trigger still
-- refuses. NC-M3D-006's lesson, applied to the table where the money is.

-- The ledgers take INSERT and nothing else, and the append-only triggers refuse UPDATE
-- and DELETE independently. An issued bill is corrected by void, credit or reissue
-- (FR-BIL-009) and by nothing else; a tip is corrected by billing.tip_correction
-- (FR-BIL-016) and by nothing else.
GRANT INSERT ON billing.bill_event       TO hospitality_app;
GRANT INSERT ON billing.tip              TO hospitality_app;
GRANT INSERT ON billing.tip_correction   TO hospitality_app;
GRANT INSERT ON billing.bill_disposition TO hospitality_app;

-- Checks, allocations and shares are working state before a bill exists: they are
-- created, moved between checks by a merge or a split, and replaced when a party changes
-- its mind about how to divide. The double-billing trigger and the shares-sum trigger are
-- what make that safe, not the absence of a grant.
GRANT SELECT, INSERT, UPDATE, DELETE ON billing.check            TO hospitality_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON billing.check_allocation TO hospitality_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON billing.bill_share       TO hospitality_app;

GRANT EXECUTE ON FUNCTION billing.open_check(uuid, uuid, uuid, uuid)                 TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.allocate_to_check(uuid, uuid, uuid, uuid, integer) TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.issue_bill(uuid, uuid, uuid, uuid, menu.customer_locale) TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.split_equally(uuid, uuid, integer)                 TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.split_by_participant(uuid, uuid)                   TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.split_by_item(uuid, uuid, jsonb)                   TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.split_by_separate_orders(uuid, uuid)               TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.split_by_custom_amount(uuid, uuid, bigint[])       TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.merge_checks(uuid, uuid, uuid, uuid)               TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.split_check(uuid, uuid, uuid, uuid[], uuid)        TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.record_disposition(uuid, uuid, uuid, billing.disposition_kind, bigint, uuid, uuid, text, uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.finalize_bill(uuid, uuid, uuid, uuid)              TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.void_bill(uuid, uuid, uuid, uuid, uuid, text, uuid)    TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.reissue_bill(uuid, uuid, uuid, uuid, uuid, text, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.append_event(uuid, uuid, uuid, billing.bill_event_kind, uuid, uuid, uuid, text, jsonb, jsonb) TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.outstanding_balance(uuid, uuid)                    TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.session_outstanding(uuid, uuid)                    TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.bill_summary(uuid, uuid)                           TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.bill_preview_lines(uuid, uuid)                     TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.tip_options(uuid, uuid)                            TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.check_view(uuid, uuid, uuid)                       TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.component_wording_for(uuid, ordering.charge_kind, menu.customer_locale) TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.calculation_version()                              TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.apply_event(bigint)                                TO hospitality_app;

-- The REBUILD is an administrator's operation, not the application's. FR-DAT-010 is a
-- recovery procedure; a running surface that could drop and refold every bill in a tenant
-- would be a route to exactly the outage it exists to recover from.
GRANT EXECUTE ON FUNCTION billing.rebuild_projections(uuid)          TO hospitality_migrator;
GRANT EXECUTE ON FUNCTION billing.drop_projections_for_rebuild(uuid) TO hospitality_migrator;

-- Configuration is written by an administrator, not by the application. The application
-- reads a service charge and a tip suggestion; it does not decide them.
GRANT USAGE ON SCHEMA billing TO hospitality_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON billing.service_charge_setting TO hospitality_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON billing.tip_setting            TO hospitality_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON billing.tip_suggestion         TO hospitality_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON billing.component_wording      TO hospitality_migrator;


-- ===========================================================================
-- FR-POS-004's unpaid balance stops being a slot
-- ===========================================================================
-- pos.table_view() has returned NULL::bigint for unpaid_balance_minor since M3-D, with
-- the closure register carrying the entry and the comment saying M4 fills it. This is
-- that. Replaced rather than edited, because 0015 is applied and checksum-locked.
--
-- The figure is billing.session_outstanding(), which does not read billing.tip. A table
-- whose guests have tipped generously still owes what it owes, and a floor plan that
-- showed otherwise would be NC-M4-002 arriving through the one screen a manager trusts.

CREATE OR REPLACE FUNCTION pos.table_view(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (
    table_session_id     uuid,
    table_node_id        uuid,
    table_reference      text,
    opened_at            timestamptz,
    guests               integer,
    assigned_waiter_id   uuid,
    open_requests        integer,
    overdue_requests     integer,
    open_orders          integer,
    order_progress       text,
    unpaid_balance_minor bigint,
    needs_attention      boolean,
    attention_reason     text
)
LANGUAGE sql STABLE
AS $$
    SELECT
        ts.id,
        ts.table_node_id,
        n.reference_code,
        ts.opened_at,
        (SELECT count(*)::integer FROM service.session_participant sp
          WHERE sp.tenant_id = ts.tenant_id AND sp.table_session_id = ts.id
            AND sp.left_at IS NULL),
        own.primary_waiter_user_id,
        (SELECT count(*)::integer FROM service.service_request sr
          WHERE sr.tenant_id = ts.tenant_id AND sr.table_session_id = ts.id
            AND sr.state NOT IN ('completed', 'cancelled', 'expired')),
        (SELECT count(*)::integer FROM service.service_request sr
          WHERE sr.tenant_id = ts.tenant_id AND sr.table_session_id = ts.id
            AND sr.state NOT IN ('completed', 'cancelled', 'expired')
            AND sr.sla_due_at < now()),
        (SELECT count(*)::integer FROM ordering.customer_order o
          WHERE o.tenant_id = ts.tenant_id AND o.table_session_id = ts.id
            AND o.state NOT IN ('cancelled', 'voided')),
        (SELECT string_agg(DISTINCT fulfillment.order_fulfillment_state(o.tenant_id, o.id),
                           ',' ORDER BY fulfillment.order_fulfillment_state(o.tenant_id, o.id))
           FROM ordering.customer_order o
          WHERE o.tenant_id = ts.tenant_id AND o.table_session_id = ts.id
            AND o.state NOT IN ('cancelled', 'voided')),
        -- FR-POS-004's unpaid balance, no longer a slot. Derived on every read from the
        -- session's live bills, less what authority has disposed of, and blind to tips.
        billing.session_outstanding(ts.tenant_id, ts.id),
        own.primary_waiter_user_id IS NULL
            OR EXISTS (SELECT 1 FROM service.service_request sr
                        WHERE sr.tenant_id = ts.tenant_id AND sr.table_session_id = ts.id
                          AND sr.state NOT IN ('completed', 'cancelled', 'expired')
                          AND sr.sla_due_at < now()),
        CASE
            WHEN own.primary_waiter_user_id IS NULL THEN 'no waiter is accountable for this table'
            WHEN EXISTS (SELECT 1 FROM service.service_request sr
                          WHERE sr.tenant_id = ts.tenant_id AND sr.table_session_id = ts.id
                            AND sr.state NOT IN ('completed', 'cancelled', 'expired')
                            AND sr.sla_due_at < now())
                THEN 'a request is past its deadline'
            ELSE NULL
        END
    FROM service.table_session ts
    JOIN org.org_node n ON n.tenant_id = ts.tenant_id AND n.id = ts.table_node_id
    LEFT JOIN service.table_ownership own
           ON own.tenant_id = ts.tenant_id AND own.table_session_id = ts.id
          AND own.effective_to IS NULL
    WHERE ts.tenant_id = p_tenant_id
      AND ts.outlet_id = p_outlet_id
      AND ts.closed_at IS NULL
    ORDER BY n.reference_code;
$$;

COMMENT ON FUNCTION pos.table_view(uuid, uuid) IS
    'FR-POS-004. Live occupancy: assigned waiter, open and overdue requests, order '
    'progress derived from the tickets, attention flags, and the unpaid balance — which '
    'M4-A filled with billing.session_outstanding(). Every figure is derived, so none can '
    'drift from its source.';
