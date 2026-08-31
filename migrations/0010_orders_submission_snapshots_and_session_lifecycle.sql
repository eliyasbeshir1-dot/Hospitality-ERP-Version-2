-- ===========================================================================
-- 0010 — Orders: submission, snapshots, notes, timeline, session lifecycle
-- ===========================================================================
-- Gate M3, slice A. Requirements: FR-ORD-001A, FR-ORD-002, FR-ORD-003, FR-ORD-004,
-- FR-ORD-005, FR-ORD-006, FR-ORD-007A, FR-ORD-008, FR-ORD-009, FR-ORD-010, FR-ORD-011,
-- FR-ORD-012A, FR-ORD-013, FR-ORD-016A, FR-ORD-017, FR-ORD-019A, FR-DAT-008A,
-- FR-DAT-010, FR-TAB-007A, FR-TAB-008, FR-TAB-009.
--
-- ---------------------------------------------------------------------------
-- The decision this file rests on
-- ---------------------------------------------------------------------------
--
--   THE LEDGER IS THE RECORD. EVERYTHING A READER SEES IS A PROJECTION OF IT.
--
-- Every gate so far stored a fact and read it back from where it was stored. M3 is the
-- first gate that COMMITS: a submitted order is a promise to a customer and, at M4, a
-- charge. Two of this slice's requirements are about that directly — FR-DAT-008A says an
-- accepted order has no destructive edit path, and FR-DAT-010 says key projections
-- rebuild from authoritative events and compare deterministically. Both are satisfied by
-- the same arrangement rather than by two mechanisms that could disagree:
--
--   ordering.order_event      is authoritative and append-only, enforced by a trigger
--                             that refuses UPDATE, DELETE and TRUNCATE whoever asks.
--   everything else in this   is derived from it by ordering.apply_event(), and can be
--   schema                    discarded and rebuilt byte-for-byte from the ledger alone.
--
-- Three consequences worth stating, because they are what make the negative controls of
-- this slice mean something:
--
--   * An order cannot be edited destructively because nothing writes to the projection
--     except the apply function, and the apply function only ever reads the ledger. A
--     hand-written UPDATE against a projection is not a quiet edit — it is a divergence
--     that the rebuild comparison names.
--   * The allergy declaration is a LEDGER EVENT, not a column somebody might forget to
--     copy. Every surface that shows it is a projection of that event, so "does it
--     survive the hop" and "does the projection rebuild" are the same question.
--   * The order total is a SUM OVER COMPONENTS THAT EXIST, never a figure. There is no
--     zero literal for a component whose source has not been built: a component with no
--     configured source produces no row, and the sum is over the rows there are. A
--     deferred constraint trigger refuses to commit an order whose stored total differs
--     from the sum of its components, so the two cannot drift apart.
--
-- ---------------------------------------------------------------------------
-- Carried forward from M2-B: the price/allergen asymmetry
-- ---------------------------------------------------------------------------
-- A PRICE must be what was AGREED, so it is pinned into an immutable snapshot. An
-- ALLERGEN must be what is TRUE, so it is never pinned anywhere. This slice inherits
-- both halves unchanged: ordering.order_line pins the money and the publication snapshot
-- line it came from, and names no allergen at all. The allergy DECLARATION stored here is
-- a statement the guest made — "I am allergic to this" — which is a different kind of
-- fact from "this dish contains that", and it is pinned because what the guest said is
-- history. What the dish contains is still read live from safety.effective_allergens().
--
-- ---------------------------------------------------------------------------
-- What is deliberately absent
-- ---------------------------------------------------------------------------
-- No fulfillment ticket, station, queue or preparation state (M3-B). No service request
-- (M3-C). No waiter screen (M3-D). No check, payment, tip or receipt (M4). No offline
-- queue (M5a). Five rows of this slice can only be half-proved without those artifacts;
-- each is recorded in planning/partial_closures.json with the slice that completes it,
-- and the build refuses to produce a README while that register is inconsistent.
-- ===========================================================================

CREATE SCHEMA ordering;

COMMENT ON SCHEMA ordering IS
    'The commercial order: submission, snapshots, notes, timeline and the append-only '
    'ledger they are all projections of (FR-ORD-001A, FR-DAT-008A, FR-DAT-010).';


-- ===========================================================================
-- Types
-- ===========================================================================

-- FR-ORD-001A: ONE aggregate, with a channel-specific policy dimension. Not two models
-- sharing a name. Both origins are the dine_in sales channel; what differs is who placed
-- the order and therefore which acceptance and cancellation policy applies.
CREATE TYPE ordering.order_origin AS ENUM ('guest_qr', 'waiter_entered');

COMMENT ON TYPE ordering.order_origin IS
    'How an order reached the system (FR-ORD-001A). Counter POS is a third origin that '
    'does not exist until the POS surface is built, and is absent from this type rather '
    'than present and unreachable.';

-- The COMMERCIAL lifecycle of an order. The FULFILLMENT state machine — new,
-- acknowledged, preparing, held, ready, completed — is a separate concern that belongs
-- to M3-B with the tickets it describes, and no label of it appears here.
CREATE TYPE ordering.order_state AS ENUM
    ('submitted', 'accepted', 'rejected', 'cancelled', 'voided');

CREATE TYPE ordering.acceptance_mode AS ENUM ('automatic', 'staff_confirmed');

CREATE TYPE ordering.actor_kind AS ENUM ('guest', 'staff', 'system');

CREATE TYPE ordering.event_kind AS ENUM (
    'submitted', 'accepted', 'rejected', 'amended', 'cancelled', 'voided',
    'note_added', 'allergy_declared', 'session_merged', 'session_moved');

CREATE TYPE ordering.note_kind AS ENUM
    ('customer', 'allergy_declaration', 'kitchen_instruction', 'private_staff');

COMMENT ON TYPE ordering.note_kind IS
    'FR-ORD-013. Four kinds, and each carries a different required shape rather than '
    'only a different label — an allergy declaration must name an allergen and the '
    'wording the guest was shown; a private staff note must name the author. Collapsing '
    'them would lose exactly the distinction the requirement exists for.';

CREATE TYPE ordering.charge_kind AS ENUM ('item_subtotal', 'discount', 'tax', 'fee');

-- Where a charge figure came from. A component may not exist without one: an amount on
-- an order with no traceable source is a number somebody chose.
CREATE TYPE ordering.charge_source_kind AS ENUM
    ('menu_price', 'tax_configuration', 'discount_policy', 'service_configuration');

COMMENT ON TYPE ordering.charge_source_kind IS
    'FR-ORD-003, FR-ORD-005. tax_configuration and discount_policy resolve to M1 '
    'configuration that exists; service_configuration is the source a fee would come '
    'from, and the configuration that populates it is FR-CFG-001C at M4. No delivered '
    'path at M3-A creates a fee rule, and tests/m3a proves both halves: that none does, '
    'and that one would flow into the total with no change to the summation.';

-- The artifacts a correlation chain links (FR-ORD-019A). Six are named by the
-- requirement; two of them are built by later slices of this gate and appear here so the
-- chain has a shape to grow into rather than a shape to be rewritten.
CREATE TYPE ordering.artifact_kind AS ENUM (
    'request', 'cart', 'table_session', 'order', 'fulfillment_ticket', 'service_request');


-- ===========================================================================
-- The ledger (FR-DAT-008A)
-- ===========================================================================
-- Append-only twice over, exactly as M1-C's audit store and M2-A's publication snapshot
-- are: the application role is never granted UPDATE or DELETE, and a trigger refuses both
-- regardless of who is asking. The grant alone is not the enforcement — a role change
-- would undo it, and the brief for this slice is explicit that the proof is by trigger.
--
-- order_id is NOT a foreign key into ordering.customer_order. That is deliberate and it
-- is what makes the rebuild real: the ledger must stand when every projection has been
-- truncated, and a foreign key into a projection would forbid exactly that.

CREATE TABLE ordering.order_event (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    order_id        uuid NOT NULL,

    -- Per aggregate, gapless from 1. The rebuild replays in this order, so a projection
    -- built on one machine and one built on another cannot differ by arrival time.
    sequence_number integer NOT NULL,

    kind            ordering.event_kind NOT NULL,
    occurred_at     timestamptz NOT NULL DEFAULT now(),

    actor_kind      ordering.actor_kind NOT NULL,
    actor_user_id   uuid,
    actor_guest_session_id uuid,

    correlation_id  uuid NOT NULL,
    reason_code_id  uuid,

    -- FR-ORD-010 requires before AND after for an amendment. Storing only the delta
    -- would make "what did it say before" a reconstruction rather than a record.
    before          jsonb,
    after           jsonb NOT NULL,

    CONSTRAINT order_event_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT order_event_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_event_actor_user_fk FOREIGN KEY (tenant_id, actor_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_event_actor_guest_fk FOREIGN KEY (tenant_id, actor_guest_session_id)
        REFERENCES service.guest_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_event_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT order_event_sequence_positive CHECK (sequence_number > 0),
    CONSTRAINT order_event_sequence_unique UNIQUE (tenant_id, order_id, sequence_number),

    -- An actor is named, and named consistently with what kind of actor it was. A guest
    -- carries no user account and a staff member carries no guest session; the system
    -- carries neither, and says so.
    CONSTRAINT order_event_actor_consistent CHECK (
        (actor_kind = 'guest'  AND actor_guest_session_id IS NOT NULL AND actor_user_id IS NULL)
     OR (actor_kind = 'staff'  AND actor_user_id IS NOT NULL AND actor_guest_session_id IS NULL)
     OR (actor_kind = 'system' AND actor_user_id IS NULL AND actor_guest_session_id IS NULL)),

    -- A change to an existing order says what it changed from. A submission has nothing
    -- before it and must not claim to.
    CONSTRAINT order_event_before_required_for_changes CHECK (
        (kind IN ('amended', 'cancelled', 'voided', 'session_merged', 'session_moved')
         AND before IS NOT NULL)
     OR (kind IN ('submitted', 'accepted', 'rejected', 'note_added', 'allergy_declared')
         AND before IS NULL)),

    -- Cancellation and void state a registered reason (FR-CFG-003). Nothing else may
    -- borrow the reason column to mean something of its own.
    CONSTRAINT order_event_reason_required CHECK (
        (kind IN ('cancelled', 'voided')) = (reason_code_id IS NOT NULL))
);

COMMENT ON TABLE ordering.order_event IS
    'The authoritative, append-only order ledger (FR-DAT-008A). Every other table in '
    'this schema is a projection rebuilt from it by ordering.apply_event(), so an order '
    'has no destructive edit path: there is nothing to edit that is not derived. '
    'Enforced twice over — the application role holds INSERT and SELECT only, and '
    'ordering.refuse_ledger_mutation() refuses UPDATE, DELETE and TRUNCATE whoever asks.';

CREATE INDEX order_event_replay_idx
    ON ordering.order_event (tenant_id, order_id, sequence_number);
CREATE INDEX order_event_correlation_idx
    ON ordering.order_event (tenant_id, correlation_id);

CREATE FUNCTION ordering.refuse_ledger_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'ACCEPTED_ORDER_MUTATION_REFUSED: the order ledger is append-only; % is refused on %',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'HS403';
END;
$$;

CREATE TRIGGER order_event_append_only
    BEFORE UPDATE OR DELETE ON ordering.order_event
    FOR EACH ROW EXECUTE FUNCTION ordering.refuse_ledger_mutation();

CREATE TRIGGER order_event_no_truncate
    BEFORE TRUNCATE ON ordering.order_event
    FOR EACH STATEMENT EXECUTE FUNCTION ordering.refuse_ledger_mutation();


-- ===========================================================================
-- The projection guard
-- ===========================================================================
-- Nothing writes a projection except ordering.apply_event(). That is enforced the way
-- the ledger's immutability is — twice, on inputs that do not overlap:
--
--   1. The application role is granted SELECT on every projection and nothing else.
--   2. A trigger on every projection refuses any write not made inside apply_event(),
--      recognised by a transaction-local marker only that function sets.
--
-- The second lock is the one that survives a role change, and the one that catches a
-- privileged identity editing an accepted order by hand — which is the destructive edit
-- path FR-DAT-008A says must not exist.

CREATE FUNCTION ordering.refuse_projection_write() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF coalesce(current_setting('ordering.applying_event', true), '') <> 'yes' THEN
        RAISE EXCEPTION
            'PROJECTION_WRITTEN_DIRECTLY: % on %.% did not come from '
            'ordering.apply_event(); the ledger is the only way to change an order',
            TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME
            USING ERRCODE = 'HS403';
    END IF;
    RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

COMMENT ON FUNCTION ordering.refuse_projection_write() IS
    'FR-DAT-008A. A projection row may only be written while ordering.apply_event() is '
    'running. The marker is transaction-local (set_config with is_local true), so it '
    'cannot leak into a later statement on a pooled connection.';


-- ===========================================================================
-- The order aggregate, as a projection (FR-ORD-001A)
-- ===========================================================================

CREATE TABLE ordering.customer_order (
    id                  uuid PRIMARY KEY,
    tenant_id           uuid NOT NULL,
    outlet_id           uuid NOT NULL,
    table_session_id    uuid NOT NULL,
    cart_id             uuid NOT NULL,

    origin              ordering.order_origin NOT NULL,
    channel             menu.sales_channel NOT NULL,
    state               ordering.order_state NOT NULL,

    -- FR-ORD-008: a line may name a participant, and a participant is a guest session,
    -- which carries no identity and requires no registration. The order itself names
    -- whoever placed it in the same terms.
    placed_by_guest_session_id uuid,
    placed_by_user_id   uuid,

    -- FR-DAT-003: an opaque identifier and a separate human number, never one doing both.
    order_number        text NOT NULL,

    -- FR-ORD-005: the language snapshot. M2-C recorded the customer's choice on the
    -- occupancy; this pins it to the order, because a party that switches language after
    -- ordering has not changed what this order was placed in. M4's receipt reads it.
    customer_locale     menu.customer_locale NOT NULL,

    -- FR-ORD-005: the commercial snapshot's provenance. The prices on the lines came
    -- from this publication, and it is immutable, so what the customer was shown is
    -- recoverable and not merely asserted.
    publication_snapshot_id uuid NOT NULL,

    currency_code       char(3) NOT NULL,
    total_amount_minor  money.amount_minor NOT NULL,

    correlation_id      uuid NOT NULL,
    idempotency_key     text NOT NULL,

    submitted_at        timestamptz NOT NULL,
    acceptance_mode     ordering.acceptance_mode,
    accepted_at         timestamptz,
    accepted_by_user_id uuid,
    resolved_at         timestamptz,

    -- The highest ledger sequence folded into this row. A rebuild that stops short is
    -- then visibly short rather than silently stale.
    ledger_sequence     integer NOT NULL,

    CONSTRAINT customer_order_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT customer_order_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT customer_order_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT customer_order_session_fk FOREIGN KEY (tenant_id, table_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT customer_order_cart_fk FOREIGN KEY (tenant_id, cart_id)
        REFERENCES service.cart (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT customer_order_guest_fk FOREIGN KEY (tenant_id, placed_by_guest_session_id)
        REFERENCES service.guest_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT customer_order_user_fk FOREIGN KEY (tenant_id, placed_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT customer_order_accepter_fk FOREIGN KEY (tenant_id, accepted_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT customer_order_snapshot_fk FOREIGN KEY (publication_snapshot_id)
        REFERENCES menu.publication_snapshot (id) ON DELETE RESTRICT,
    CONSTRAINT customer_order_currency_fk FOREIGN KEY (currency_code)
        REFERENCES money.currency (code) ON DELETE RESTRICT,

    -- FR-ORD-001A: whoever placed it is named, in terms that match how it was placed.
    CONSTRAINT customer_order_origin_consistent CHECK (
        (origin = 'guest_qr'
         AND placed_by_guest_session_id IS NOT NULL AND placed_by_user_id IS NULL)
     OR (origin = 'waiter_entered'
         AND placed_by_user_id IS NOT NULL AND placed_by_guest_session_id IS NULL)),

    -- Whether an order was ever ACCEPTED is a different question from what state it is
    -- in now, and conflating them is wrong in a way a cancellation exposes: a submitted
    -- order that the guest cancels is 'cancelled' and was never accepted. So the two
    -- acceptance columns move together, states that preclude acceptance forbid them, and
    -- a VOID requires them — because FR-ORD-012A is a void AFTER acceptance, and an
    -- order that was never accepted is cancelled rather than voided.
    CONSTRAINT customer_order_acceptance_recorded_together CHECK (
        (accepted_at IS NULL) = (acceptance_mode IS NULL)),
    CONSTRAINT customer_order_unaccepted_states_claim_nothing CHECK (
        state NOT IN ('submitted', 'rejected') OR accepted_at IS NULL),
    CONSTRAINT customer_order_accepted_and_voided_name_the_acceptance CHECK (
        state NOT IN ('accepted', 'voided') OR accepted_at IS NOT NULL),

    -- Staff-confirmed acceptance names the member of staff who confirmed it. Automatic
    -- acceptance names none, and must not borrow one.
    CONSTRAINT customer_order_confirmer_named CHECK (
        acceptance_mode IS DISTINCT FROM 'staff_confirmed' OR accepted_by_user_id IS NOT NULL),
    CONSTRAINT customer_order_automatic_has_no_confirmer CHECK (
        acceptance_mode IS DISTINCT FROM 'automatic' OR accepted_by_user_id IS NULL),

    CONSTRAINT customer_order_resolution_consistent CHECK (
        (state IN ('submitted', 'accepted')) = (resolved_at IS NULL)),

    CONSTRAINT customer_order_idempotency_key_not_blank CHECK (btrim(idempotency_key) <> ''),
    CONSTRAINT customer_order_number_not_blank CHECK (btrim(order_number) <> ''),
    CONSTRAINT customer_order_sequence_positive CHECK (ledger_sequence > 0),

    -- FR-ORD-004, from the other direction: two orders in one outlet cannot share a
    -- submission key. The idempotency ledger refuses the second attempt; this refuses
    -- the second ROW, so even a defective submission path cannot store one.
    CONSTRAINT customer_order_one_per_key UNIQUE (tenant_id, outlet_id, idempotency_key)
);

COMMENT ON TABLE ordering.customer_order IS
    'ONE order aggregate for QR dine-in and waiter-entered dine-in (FR-ORD-001A), with '
    'the origin as the channel-specific policy dimension rather than a second model. A '
    'projection of ordering.order_event: nothing writes here except '
    'ordering.apply_event(), and the whole table can be discarded and rebuilt from the '
    'ledger byte for byte (FR-DAT-010).';

COMMENT ON COLUMN ordering.customer_order.total_amount_minor IS
    'The sum of ordering.order_charge_component for this order, and nothing else. A '
    'deferred constraint trigger refuses to commit a row where it is not, so a total '
    'and its components cannot drift apart. It is never a figure a client supplied '
    '(FR-ORD-003).';

CREATE INDEX customer_order_session_idx
    ON ordering.customer_order (tenant_id, table_session_id, submitted_at);
CREATE INDEX customer_order_correlation_idx
    ON ordering.customer_order (tenant_id, correlation_id);

CREATE TRIGGER customer_order_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON ordering.customer_order
    FOR EACH ROW EXECUTE FUNCTION ordering.refuse_projection_write();


-- ---------------------------------------------------------------------------
-- Lines, modifiers and their commercial snapshot (FR-ORD-005, FR-ORD-008)
-- ---------------------------------------------------------------------------

CREATE TABLE ordering.order_line (
    id                uuid PRIMARY KEY,
    tenant_id         uuid NOT NULL,
    outlet_id         uuid NOT NULL,
    order_id          uuid NOT NULL,
    line_number       integer NOT NULL,

    item_id           uuid NOT NULL,
    variant_id        uuid NOT NULL,
    quantity          integer NOT NULL,

    -- FR-ORD-008: optional, and a guest session — not a registration. A table where
    -- three people order and one of them has an account must work exactly as well as a
    -- table where none of them does.
    participant_guest_session_id uuid,

    -- The snapshot. item_code and canonical_name are copied rather than joined because
    -- the join would follow the item to whatever it says TODAY, and the whole point of
    -- FR-ORD-005 is what it said THEN. snapshot_line_id keeps the immutable original
    -- reachable so the copy can be checked against it.
    snapshot_line_id  bigint NOT NULL,
    item_code         text NOT NULL,
    canonical_name    text NOT NULL,
    display_name      text NOT NULL,
    tax_context       text NOT NULL,

    currency_code     char(3) NOT NULL,
    unit_amount_minor money.amount_minor NOT NULL,
    line_amount_minor money.amount_minor NOT NULL,

    CONSTRAINT order_line_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT order_line_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT order_line_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_line_order_fk FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.customer_order (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_line_item_fk FOREIGN KEY (item_id)
        REFERENCES menu.sellable_item (id) ON DELETE RESTRICT,
    CONSTRAINT order_line_variant_fk FOREIGN KEY (variant_id)
        REFERENCES menu.item_variant (id) ON DELETE RESTRICT,
    CONSTRAINT order_line_participant_fk FOREIGN KEY (tenant_id, participant_guest_session_id)
        REFERENCES service.guest_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_line_snapshot_fk FOREIGN KEY (snapshot_line_id)
        REFERENCES menu.publication_snapshot_line (id) ON DELETE RESTRICT,
    CONSTRAINT order_line_currency_fk FOREIGN KEY (currency_code)
        REFERENCES money.currency (code) ON DELETE RESTRICT,

    CONSTRAINT order_line_quantity_positive CHECK (quantity > 0),
    CONSTRAINT order_line_number_positive CHECK (line_number > 0),
    CONSTRAINT order_line_number_unique UNIQUE (tenant_id, order_id, line_number),
    CONSTRAINT order_line_code_not_blank CHECK (btrim(item_code) <> ''),
    CONSTRAINT order_line_name_not_blank CHECK (btrim(canonical_name) <> ''),
    CONSTRAINT order_line_display_name_not_blank CHECK (btrim(display_name) <> '')
);

COMMENT ON COLUMN ordering.order_line.display_name IS
    'The dish name in the language the order was placed in, resolved from the approved '
    'translation at submission. canonical_name travels beside it unchanged: M2-C found '
    'that showing a translated warning next to an untranslated name is a defect a SQL '
    'suite cannot see, and an order carries both so neither question needs a join.';

CREATE INDEX order_line_order_idx ON ordering.order_line (tenant_id, order_id, line_number);

CREATE TRIGGER order_line_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON ordering.order_line
    FOR EACH ROW EXECUTE FUNCTION ordering.refuse_projection_write();

CREATE TABLE ordering.order_line_modifier (
    id                uuid PRIMARY KEY,
    tenant_id         uuid NOT NULL,
    outlet_id         uuid NOT NULL,
    order_line_id     uuid NOT NULL,
    modifier_id       uuid NOT NULL,
    canonical_name    text NOT NULL,
    display_name      text NOT NULL,
    currency_code     char(3) NOT NULL,
    unit_amount_minor money.amount_minor NOT NULL,

    CONSTRAINT order_line_modifier_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT order_line_modifier_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_line_modifier_line_fk FOREIGN KEY (tenant_id, order_line_id)
        REFERENCES ordering.order_line (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_line_modifier_modifier_fk FOREIGN KEY (modifier_id)
        REFERENCES menu.modifier (id) ON DELETE RESTRICT,
    CONSTRAINT order_line_modifier_currency_fk FOREIGN KEY (currency_code)
        REFERENCES money.currency (code) ON DELETE RESTRICT,
    CONSTRAINT order_line_modifier_unique UNIQUE (order_line_id, modifier_id),
    CONSTRAINT order_line_modifier_name_not_blank CHECK (btrim(canonical_name) <> '')
);

CREATE TRIGGER order_line_modifier_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON ordering.order_line_modifier
    FOR EACH ROW EXECUTE FUNCTION ordering.refuse_projection_write();


-- ===========================================================================
-- Charges: what the total is made of (FR-ORD-003, FR-ORD-005)
-- ===========================================================================
-- The requirement names line prices, modifiers, tax, fees and discounts. Three of those
-- have a configured source that exists: prices and modifiers are M2-A's menu.price, tax
-- is M1's config.configuration_version under category 'tax', and a discount is M1's
-- config.policy under category 'discount'. A FEE does not — the configuration that
-- would define a service charge is FR-CFG-001C, and it belongs to M4 with the check it
-- is charged on.
--
-- The wrong way to hold that gap is a fee column that reads zero. A hardcoded zero
-- survives to M4 unnoticed and looks wired when it is not, which is the vacuity the
-- money.assert_currency_paired() case at M1 is a standing reminder of. So there is no
-- fee column and no fee constant anywhere in this schema. What there is instead:
--
--   * a RULE table, whose rows each name the configuration they came from,
--   * a COMPONENT table, one row per charge that actually applied,
--   * a total that is SUM(component), over the rows there are.
--
-- A fee produces no component at M3-A because no rule of that kind can be created from
-- configuration that exists. When M4 builds FR-CFG-001C, a fee rule becomes creatable
-- and flows into the total with no change to the summation. tests/m3a proves both ends:
-- that no delivered path at this gate creates one, and that one inserted by hand does
-- reach the total while ordering.order_total() is byte-identical.

CREATE TABLE ordering.charge_rule (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid,

    kind           ordering.charge_kind NOT NULL,
    source_kind    ordering.charge_source_kind NOT NULL,
    source_configuration_id uuid,
    source_policy_id        uuid,

    -- NULL matches every tax context. A named context matches menu.price.tax_context on
    -- the line, which is the column M2-A put there for exactly this.
    tax_context    text,

    -- Exactly one of the two. A rule that is both a rate and a fixed amount is a rule
    -- with two answers.
    rate_percentage money.percentage,
    fixed_amount_minor money.amount_minor,
    currency_code  char(3),

    -- Stated, never defaulted. Rounding is a commercial decision and half of a rounding
    -- defect is somebody's silent assumption about which way it went.
    rounding_mode  money.rounding_mode NOT NULL,

    effective_from timestamptz NOT NULL DEFAULT now(),
    effective_to   timestamptz,

    CONSTRAINT charge_rule_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT charge_rule_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT charge_rule_configuration_fk FOREIGN KEY (source_configuration_id)
        REFERENCES config.configuration_version (id) ON DELETE RESTRICT,
    CONSTRAINT charge_rule_policy_fk FOREIGN KEY (source_policy_id)
        REFERENCES config.policy (id) ON DELETE RESTRICT,
    CONSTRAINT charge_rule_currency_fk FOREIGN KEY (currency_code)
        REFERENCES money.currency (code) ON DELETE RESTRICT,

    -- A line price is not a rule; it comes from the menu. Nothing here may claim to be one.
    CONSTRAINT charge_rule_not_a_line_price CHECK (kind <> 'item_subtotal'),

    -- Every kind resolves to exactly one source kind, and that source is named. This is
    -- what makes "no fee source exists at M3-A" a structural fact rather than a habit:
    -- a fee rule requires a service configuration, and config.configuration_category has
    -- no label a Phase 1 gate before M4 writes under that heading.
    CONSTRAINT charge_rule_source_matches_kind CHECK (
        (kind = 'tax'      AND source_kind = 'tax_configuration'
                           AND source_configuration_id IS NOT NULL AND source_policy_id IS NULL)
     OR (kind = 'discount' AND source_kind = 'discount_policy'
                           AND source_policy_id IS NOT NULL AND source_configuration_id IS NULL)
     OR (kind = 'fee'      AND source_kind = 'service_configuration'
                           AND source_configuration_id IS NOT NULL AND source_policy_id IS NULL)),

    CONSTRAINT charge_rule_one_basis CHECK (
        (rate_percentage IS NOT NULL)::int + (fixed_amount_minor IS NOT NULL)::int = 1),
    -- A fixed amount is money, so it names its currency. A rate is a proportion and does
    -- not, because it applies to whatever currency the line was priced in.
    CONSTRAINT charge_rule_fixed_amount_has_currency CHECK (
        (fixed_amount_minor IS NULL) = (currency_code IS NULL)),
    -- A rule states a MAGNITUDE. Which way it moves the total is decided by its kind,
    -- once, where the component is written — not stored twice and left to disagree.
    -- money.percentage already refuses a rate outside 0..100; this is the fixed-amount
    -- half of the same rule.
    CONSTRAINT charge_rule_fixed_amount_is_a_magnitude CHECK (
        fixed_amount_minor IS NULL OR fixed_amount_minor >= 0),
    CONSTRAINT charge_rule_tax_context_not_blank CHECK (
        tax_context IS NULL OR btrim(tax_context) <> ''),
    CONSTRAINT charge_rule_window_valid CHECK (
        effective_to IS NULL OR effective_to > effective_from)
);

COMMENT ON TABLE ordering.charge_rule IS
    'Where a tax, discount or fee figure comes from (FR-ORD-003). Every row names the '
    'M1 configuration or policy it was derived from, so no amount on an order is a '
    'number somebody chose. There is no fee row at M3-A and no path that creates one: '
    'the configuration a fee resolves to is FR-CFG-001C at M4.';

CREATE INDEX charge_rule_lookup_idx
    ON ordering.charge_rule (tenant_id, outlet_id, kind, effective_from DESC);

-- One component per charge that actually applied, with the rule that produced it. An
-- order's total is the sum of these rows and nothing else.
CREATE TABLE ordering.order_charge_component (
    id             uuid PRIMARY KEY,
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    order_id       uuid NOT NULL,

    kind           ordering.charge_kind NOT NULL,
    source_kind    ordering.charge_source_kind NOT NULL,
    charge_rule_id uuid,

    -- What the figure was worked out from, kept so a total can be explained rather than
    -- only recomputed: the base it applied to, the rate, the rounding mode.
    basis          jsonb NOT NULL,

    currency_code  char(3) NOT NULL,
    -- Signed. A discount is negative here so that the total is a plain SUM with no
    -- per-kind sign logic anywhere — the summation cannot get a sign wrong for a kind
    -- it has never seen.
    amount_minor   money.amount_minor NOT NULL,

    CONSTRAINT order_charge_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT order_charge_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_charge_order_fk FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.customer_order (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_charge_rule_fk FOREIGN KEY (charge_rule_id)
        REFERENCES ordering.charge_rule (id) ON DELETE RESTRICT,
    CONSTRAINT order_charge_currency_fk FOREIGN KEY (currency_code)
        REFERENCES money.currency (code) ON DELETE RESTRICT,

    -- The line subtotal comes from the menu and names no rule. Every other kind is
    -- produced by a rule and must name the one that produced it.
    CONSTRAINT order_charge_rule_required CHECK (
        (kind = 'item_subtotal'
         AND source_kind = 'menu_price' AND charge_rule_id IS NULL)
     OR (kind <> 'item_subtotal' AND charge_rule_id IS NOT NULL)),
    CONSTRAINT order_charge_discount_reduces CHECK (
        kind <> 'discount' OR amount_minor <= 0),
    CONSTRAINT order_charge_additions_add CHECK (
        kind = 'discount' OR amount_minor >= 0),
    CONSTRAINT order_charge_one_per_rule UNIQUE (order_id, kind, charge_rule_id)
);

COMMENT ON TABLE ordering.order_charge_component IS
    'One row per charge that applied to an order (FR-ORD-005). The order total is '
    'SUM(amount_minor) over these rows — a component whose source does not exist yet '
    'produces no row, never a zero. Discounts are stored negative so the summation has '
    'no per-kind sign logic and cannot get a new kind''s sign wrong.';

CREATE INDEX order_charge_order_idx ON ordering.order_charge_component (tenant_id, order_id);

CREATE TRIGGER order_charge_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON ordering.order_charge_component
    FOR EACH ROW EXECUTE FUNCTION ordering.refuse_projection_write();

-- The summation. This is the only place an order total is computed, and it is generic
-- over kinds by construction: it names none of them.
CREATE FUNCTION ordering.order_total(p_tenant_id uuid, p_order_id uuid)
RETURNS money.amount_minor
LANGUAGE sql STABLE
AS $$
    SELECT coalesce(sum(c.amount_minor), 0)::money.amount_minor
    FROM ordering.order_charge_component c
    WHERE c.tenant_id = p_tenant_id AND c.order_id = p_order_id;
$$;

COMMENT ON FUNCTION ordering.order_total(uuid, uuid) IS
    'The order total: a sum over the components that exist. It names no charge kind, so '
    'a kind whose configured source arrives at a later gate reaches the total without '
    'this function changing. tests/m3a asserts that by digesting its definition either '
    'side of adding a fee.';

-- A stored total that disagrees with its components cannot be committed. Deferred, so
-- the components may be written after the header inside one apply_event() call — the
-- same ordering menu.publish_menu() uses to digest the rows it actually stored.
CREATE FUNCTION ordering.assert_total_is_the_sum() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_order_id uuid;
    v_order    ordering.customer_order%ROWTYPE;
    v_sum      bigint;
BEGIN
    -- One function, two tables, and the row it fires for is not the same shape in each.
    -- TG_TABLE_NAME rather than a coalesce over columns that only exist on one of them:
    -- a DELETE has no NEW at all, and reading one would abort the transaction with a
    -- runtime error that looks nothing like the reconciliation failure this raises.
    IF TG_TABLE_NAME = 'customer_order' THEN
        v_order_id := NEW.id;
    ELSE
        v_order_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.order_id ELSE NEW.order_id END;
    END IF;

    SELECT * INTO v_order FROM ordering.customer_order WHERE id = v_order_id;
    IF NOT FOUND THEN
        RETURN NULL;              -- the order itself went away; nothing to reconcile
    END IF;

    v_sum := ordering.order_total(v_order.tenant_id, v_order.id);

    IF v_order.total_amount_minor <> v_sum THEN
        RAISE EXCEPTION
            'ORDER_TOTAL_NOT_THE_SUM_OF_ITS_COMPONENTS: order % stores % but its '
            'components sum to %',
            v_order.id, v_order.total_amount_minor, v_sum
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER customer_order_total_reconciles
    AFTER INSERT OR UPDATE ON ordering.customer_order
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION ordering.assert_total_is_the_sum();

CREATE CONSTRAINT TRIGGER order_charge_total_reconciles
    AFTER INSERT OR UPDATE OR DELETE ON ordering.order_charge_component
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION ordering.assert_total_is_the_sum();


-- ===========================================================================
-- Notes: four kinds, four shapes (FR-ORD-013)
-- ===========================================================================
-- The requirement separates customer notes, allergy declarations, kitchen instructions
-- and private staff notes. Stored in one table with one kind column, that separation is
-- a label — and a label is exactly what gets ignored by the next query somebody writes.
-- So each kind carries a DIFFERENT REQUIRED SHAPE, enforced by check constraints:
--
--   customer            written by a guest, no author account
--   allergy_declaration names an allergen AND the tenant-approved wording the guest was
--                       shown, and links the table-level concern M2-B already records
--   kitchen_instruction written by staff, addressed to the kitchen
--   private_staff       written by staff, and never leaves it
--
-- A row cannot be quietly reclassified into a kind whose required columns it does not
-- have, which is what makes the audience functions below safe to reason about.

CREATE TABLE ordering.order_note (
    id             uuid PRIMARY KEY,
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    order_id       uuid NOT NULL,
    order_line_id  uuid,                  -- NULL means the note is about the whole order

    kind           ordering.note_kind NOT NULL,
    body           text NOT NULL,

    author_user_id uuid,
    author_guest_session_id uuid,

    -- Allergy declarations only. The allergen is named as a reference into M2-B's
    -- catalog, never copied — an allergen must be what is TRUE, so it is read live.
    -- What IS pinned is the wording the guest was shown, because what somebody was told
    -- is history and must not change under them.
    allergen_id    uuid,
    allergy_concern_id uuid,
    acknowledgement_wording_id uuid,
    acknowledgement_text text,

    created_at     timestamptz NOT NULL,

    CONSTRAINT order_note_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT order_note_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_note_order_fk FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.customer_order (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_note_line_fk FOREIGN KEY (tenant_id, order_line_id)
        REFERENCES ordering.order_line (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_note_author_fk FOREIGN KEY (tenant_id, author_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_note_guest_fk FOREIGN KEY (tenant_id, author_guest_session_id)
        REFERENCES service.guest_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_note_allergen_fk FOREIGN KEY (tenant_id, allergen_id)
        REFERENCES safety.allergen (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT order_note_concern_fk FOREIGN KEY (allergy_concern_id)
        REFERENCES safety.allergy_concern (id) ON DELETE RESTRICT,
    CONSTRAINT order_note_wording_fk FOREIGN KEY (tenant_id, acknowledgement_wording_id)
        REFERENCES safety.approved_wording (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT order_note_body_not_blank CHECK (btrim(body) <> ''),

    -- An allergy declaration without an allergen is a sentence; with one it is a fact
    -- the kitchen can act on. Both halves are required, and only this kind may carry them.
    CONSTRAINT order_note_allergy_shape CHECK (
        (kind = 'allergy_declaration'
         AND allergen_id IS NOT NULL
         AND allergy_concern_id IS NOT NULL
         AND acknowledgement_wording_id IS NOT NULL
         AND acknowledgement_text IS NOT NULL AND btrim(acknowledgement_text) <> '')
     OR (kind <> 'allergy_declaration'
         AND allergen_id IS NULL
         AND allergy_concern_id IS NULL
         AND acknowledgement_wording_id IS NULL
         AND acknowledgement_text IS NULL)),

    -- A kitchen instruction and a private staff note are written by staff and name the
    -- author. A customer note and an allergy declaration come from the table.
    CONSTRAINT order_note_authorship_matches_kind CHECK (
        (kind IN ('kitchen_instruction', 'private_staff')
         AND author_user_id IS NOT NULL AND author_guest_session_id IS NULL)
     OR (kind IN ('customer', 'allergy_declaration')
         AND (author_guest_session_id IS NOT NULL OR author_user_id IS NOT NULL)))
);

COMMENT ON TABLE ordering.order_note IS
    'Four note kinds with four required shapes (FR-ORD-013), so the distinction is '
    'structural rather than a label. The application role holds NO direct SELECT here: '
    'reads go through the audience functions below, and the one a customer surface can '
    'call takes no audience argument, so it cannot be asked for a private staff note.';

CREATE INDEX order_note_order_idx ON ordering.order_note (tenant_id, order_id, created_at);

CREATE TRIGGER order_note_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON ordering.order_note
    FOR EACH ROW EXECUTE FUNCTION ordering.refuse_projection_write();


-- ===========================================================================
-- Timeline (FR-ORD-016A)
-- ===========================================================================
-- A projection of the ledger in chronological order, with the audience each entry may be
-- shown to decided when it is written rather than by whoever queries it later.
--
-- Station events (M3-B) and service-request events (M3-C) belong on this timeline and
-- cannot be here yet. FR-ORD-016A is recorded as partially closed with both named.

CREATE TABLE ordering.order_timeline_entry (
    id              uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    order_id        uuid NOT NULL,
    sequence_number integer NOT NULL,

    occurred_at     timestamptz NOT NULL,
    kind            ordering.event_kind NOT NULL,

    -- Two booleans rather than one audience enum, because an entry is frequently
    -- visible to both and an enum would force a duplicate row that could then diverge.
    visible_to_customer boolean NOT NULL,
    visible_to_staff    boolean NOT NULL,

    -- What a customer is shown and what staff are shown are different sentences about
    -- the same event, not the same sentence filtered. Storing both is what lets the
    -- customer text omit an internal reason without staff losing it.
    customer_summary text,
    staff_summary    text NOT NULL,

    CONSTRAINT timeline_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT timeline_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT timeline_order_fk FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.customer_order (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT timeline_sequence_unique UNIQUE (tenant_id, order_id, sequence_number),
    CONSTRAINT timeline_staff_summary_not_blank CHECK (btrim(staff_summary) <> ''),
    -- An entry a customer can see says something to them. One they cannot must not
    -- carry customer-facing text at all, so there is nothing to leak by accident.
    CONSTRAINT timeline_customer_text_matches_visibility CHECK (
        visible_to_customer = (customer_summary IS NOT NULL
                               AND btrim(coalesce(customer_summary, '')) <> '')),
    -- Every event is on the staff timeline. An entry visible to nobody is a row that
    -- exists to be forgotten.
    CONSTRAINT timeline_staff_always_see_it CHECK (visible_to_staff)
);

CREATE INDEX timeline_order_idx
    ON ordering.order_timeline_entry (tenant_id, order_id, occurred_at, sequence_number);

CREATE TRIGGER timeline_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON ordering.order_timeline_entry
    FOR EACH ROW EXECUTE FUNCTION ordering.refuse_projection_write();


-- ===========================================================================
-- Correlation chain (FR-ORD-019A)
-- ===========================================================================
-- One row per (chain, artifact). Rebuilt from the ledger like everything else, which is
-- what "survives projection rebuild" means here: the chain is not a cache of joins, it
-- is derived from the events that created the artifacts.
--
-- Two of the six artifacts the requirement names — fulfillment ticket and service
-- request — are built by M3-B and M3-C. They are labels in ordering.artifact_kind with
-- no rows at this gate, so the later slices extend a chain rather than reshape one.

CREATE TABLE ordering.correlation_link (
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    correlation_id uuid NOT NULL,
    artifact_kind  ordering.artifact_kind NOT NULL,
    artifact_id    uuid NOT NULL,
    linked_at      timestamptz NOT NULL,

    PRIMARY KEY (correlation_id, artifact_kind, artifact_id),
    CONSTRAINT correlation_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT correlation_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT
);

COMMENT ON TABLE ordering.correlation_link IS
    'The stable chain linking a request, a cart, a table session and an order '
    '(FR-ORD-019A), rebuilt from ordering.order_event so it survives a projection '
    'rebuild by construction. artifact_id is deliberately not a foreign key: the chain '
    'must be able to name an artifact kind whose table a later slice builds.';

CREATE INDEX correlation_artifact_idx
    ON ordering.correlation_link (tenant_id, artifact_kind, artifact_id);

CREATE TRIGGER correlation_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON ordering.correlation_link
    FOR EACH ROW EXECUTE FUNCTION ordering.refuse_projection_write();


-- ===========================================================================
-- Duplicate detection (FR-ORD-017)
-- ===========================================================================
-- Distinct from idempotency, and the distinction matters. Idempotency is about the SAME
-- submission arriving twice — same key, and the second one must produce no second
-- effect. Duplicate detection is about DIFFERENT submissions that look alike: a guest
-- who taps submit, waits, and taps again with a fresh key.
--
-- A second round of drinks is the normal case and must pass unimpeded, so this FLAGS
-- and never refuses. Two things separate a suspicious duplicate from a legitimate one:
-- the guest declaring repeat intent, and the interval since the last identical order.

CREATE TABLE ordering.duplicate_signal (
    id                 uuid PRIMARY KEY,
    tenant_id          uuid NOT NULL,
    outlet_id          uuid NOT NULL,
    order_id           uuid NOT NULL,
    matched_order_id   uuid NOT NULL,
    content_digest     bytea NOT NULL,
    seconds_apart      integer NOT NULL,
    raised_at          timestamptz NOT NULL,

    CONSTRAINT duplicate_signal_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT duplicate_signal_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT duplicate_signal_order_fk FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.customer_order (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT duplicate_signal_matched_fk FOREIGN KEY (tenant_id, matched_order_id)
        REFERENCES ordering.customer_order (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT duplicate_signal_digest_is_sha256 CHECK (octet_length(content_digest) = 32),
    CONSTRAINT duplicate_signal_distinct_orders CHECK (order_id <> matched_order_id),
    CONSTRAINT duplicate_signal_interval_not_negative CHECK (seconds_apart >= 0)
);

COMMENT ON TABLE ordering.duplicate_signal IS
    'A suspected duplicate order, flagged and never refused (FR-ORD-017). A control that '
    'blocked a legitimate second round of drinks would be wrong in the other direction, '
    'so a declared repeat produces NO ROW here at all. There is deliberately no '
    '"repeat_intent_declared" column: it could only ever hold false, and a column with '
    'one possible value reads like a real value while carrying nothing. The absence of '
    'the row is the record, and tests/m3a asserts the absence rather than a flag.';

CREATE TRIGGER duplicate_signal_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON ordering.duplicate_signal
    FOR EACH ROW EXECUTE FUNCTION ordering.refuse_projection_write();


-- ===========================================================================
-- Session lifecycle: merge, move, close (FR-TAB-007A, FR-TAB-008, FR-TAB-009)
-- ===========================================================================
-- Merge and move are where orders get lost. The two are not symmetric and this schema
-- says so rather than treating them alike:
--
--   MOVE changes which TABLE a session occupies. Orders reference the SESSION, and the
--   session keeps its identity, so nothing is re-parented and nothing can be dropped.
--   That is a property of the model, not of the move function — which is why no order
--   carries a denormalized table_node_id anywhere in this schema. A copy of the table on
--   the order is exactly what would make a move lossy, so there is none.
--
--   MERGE genuinely re-parents: one session absorbs another's orders. That is a real
--   move of real rows and it is done by appending a session_merged event to every
--   affected order, so the before and after are both in the ledger and the projection
--   follows from them.

CREATE TABLE service.session_merge (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL,
    outlet_id           uuid NOT NULL,
    surviving_session_id uuid NOT NULL,
    absorbed_session_id uuid NOT NULL,
    merged_by_user_id   uuid NOT NULL,
    reason_code_id      uuid,
    orders_moved        integer NOT NULL,
    merged_at           timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT session_merge_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT session_merge_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT session_merge_surviving_fk FOREIGN KEY (tenant_id, surviving_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT session_merge_absorbed_fk FOREIGN KEY (tenant_id, absorbed_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT session_merge_actor_fk FOREIGN KEY (tenant_id, merged_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT session_merge_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT session_merge_distinct CHECK (surviving_session_id <> absorbed_session_id),
    CONSTRAINT session_merge_orders_not_negative CHECK (orders_moved >= 0),
    -- An absorbed session is absorbed once. A second merge of the same session would
    -- make "where did that order go" a question with two answers.
    CONSTRAINT session_merge_absorbed_once UNIQUE (tenant_id, absorbed_session_id)
);

COMMENT ON TABLE service.session_merge IS
    'Two physical tables merged into one service session (FR-TAB-007A), audited with the '
    'count of orders consolidated so the record itself states what moved.';

CREATE TABLE service.session_move (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          uuid NOT NULL,
    outlet_id          uuid NOT NULL,
    table_session_id   uuid NOT NULL,
    from_table_node_id uuid NOT NULL,
    to_table_node_id   uuid NOT NULL,
    from_occupancy_number integer NOT NULL,
    to_occupancy_number   integer NOT NULL,
    moved_by_user_id   uuid NOT NULL,
    orders_carried     integer NOT NULL,
    moved_at           timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT session_move_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT session_move_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT session_move_session_fk FOREIGN KEY (tenant_id, table_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT session_move_from_fk FOREIGN KEY (tenant_id, from_table_node_id)
        REFERENCES service.table_profile (tenant_id, table_node_id) ON DELETE RESTRICT,
    CONSTRAINT session_move_to_fk FOREIGN KEY (tenant_id, to_table_node_id)
        REFERENCES service.table_profile (tenant_id, table_node_id) ON DELETE RESTRICT,
    CONSTRAINT session_move_actor_fk FOREIGN KEY (tenant_id, moved_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT session_move_actually_moves CHECK (from_table_node_id <> to_table_node_id),
    CONSTRAINT session_move_orders_not_negative CHECK (orders_carried >= 0)
);

-- FR-TAB-009: a session closes when its obligations are met, or when somebody with the
-- authority to say otherwise records why. The exception is a row, not a flag — "who
-- allowed this and what did they say" is the question that gets asked afterwards.
CREATE TABLE service.session_closure_exception (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          uuid NOT NULL,
    outlet_id          uuid NOT NULL,
    table_session_id   uuid NOT NULL,
    reason_code_id     uuid NOT NULL,
    authorized_by_user_id uuid NOT NULL,
    outstanding_orders integer NOT NULL,
    note               text NOT NULL,
    recorded_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT closure_exception_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT closure_exception_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT closure_exception_session_fk FOREIGN KEY (tenant_id, table_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT closure_exception_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT closure_exception_actor_fk FOREIGN KEY (tenant_id, authorized_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT closure_exception_note_not_blank CHECK (btrim(note) <> ''),
    -- An exception exists because something was outstanding. Recording one for a session
    -- with nothing outstanding would make the register meaningless.
    CONSTRAINT closure_exception_had_something_outstanding CHECK (outstanding_orders > 0)
);


-- ===========================================================================
-- Carts stop being editable once they are submitted (FR-ORD-002)
-- ===========================================================================
-- Derived, not stored. A 'submitted' label on service.cart would be a second answer to
-- "was this ordered", and the two answers would eventually differ. The order referencing
-- the cart IS the fact; this refuses a change to a cart that has one.

CREATE FUNCTION service.refuse_change_to_submitted_cart() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_cart uuid := CASE TG_OP WHEN 'DELETE' THEN OLD.cart_id ELSE NEW.cart_id END;
    v_tenant uuid := CASE TG_OP WHEN 'DELETE' THEN OLD.tenant_id ELSE NEW.tenant_id END;
BEGIN
    IF EXISTS (SELECT 1 FROM ordering.customer_order o
                WHERE o.tenant_id = v_tenant AND o.cart_id = v_cart
                  AND o.state <> 'rejected') THEN
        RAISE EXCEPTION
            'CART_ALREADY_SUBMITTED: cart % has been ordered; changing it now would '
            'change what somebody agreed to', v_cart
            USING ERRCODE = 'HS409';
    END IF;
    RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER cart_line_frozen_after_submission
    BEFORE INSERT OR UPDATE OR DELETE ON service.cart_line
    FOR EACH ROW EXECUTE FUNCTION service.refuse_change_to_submitted_cart();

COMMENT ON FUNCTION service.refuse_change_to_submitted_cart() IS
    'FR-ORD-002 from the far side: a DRAFT cart carries no commitment, and the moment it '
    'does carry one it stops being a draft. Derived from the existence of an order '
    'rather than from a state label on the cart, so there is only ever one answer.';


-- ===========================================================================
-- The fold: ledger -> projections (FR-DAT-010)
-- ===========================================================================
-- One event in, one step of every projection out. Two properties this function is built
-- for, both of which the suite checks rather than assumes:
--
--   PURE. Nothing in here reads now(), a sequence, or gen_random_uuid(). Every value it
--   writes comes out of the event. That is what makes a rebuild BYTE-deterministic
--   rather than merely equivalent — a projection built now and one built in an hour
--   have to be indistinguishable, and a created_at taken from the clock would make them
--   differ in a way that is easy to wave away and impossible to check.
--
--   TOTAL. An event kind this function does not handle raises. Silently ignoring an
--   unknown kind is how a projection comes to be missing an event nobody notices, and
--   the rebuild comparison would then agree with itself while both sides were wrong.

CREATE FUNCTION ordering.apply_event(p_event_id bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, ordering, service, menu, safety, config, public
AS $$
DECLARE
    e         ordering.order_event%ROWTYPE;
    v_order   jsonb;
    v_line    jsonb;
    v_mod     jsonb;
    v_charge  jsonb;
    v_note    jsonb;
    v_link    jsonb;
    v_dup     jsonb;
BEGIN
    SELECT * INTO e FROM ordering.order_event WHERE id = p_event_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LEDGER_EVENT_ABSENT: no order event %', p_event_id
            USING ERRCODE = 'HS404';
    END IF;

    PERFORM set_config('ordering.applying_event', 'yes', true);

    IF e.kind = 'submitted' THEN
        v_order := e.after -> 'order';

        INSERT INTO ordering.customer_order
            (id, tenant_id, outlet_id, table_session_id, cart_id, origin, channel, state,
             placed_by_guest_session_id, placed_by_user_id, order_number, customer_locale,
             publication_snapshot_id, currency_code, total_amount_minor, correlation_id,
             idempotency_key, submitted_at, ledger_sequence)
        VALUES
            (e.order_id, e.tenant_id, e.outlet_id,
             (v_order ->> 'table_session_id')::uuid,
             (v_order ->> 'cart_id')::uuid,
             (v_order ->> 'origin')::ordering.order_origin,
             (v_order ->> 'channel')::menu.sales_channel,
             'submitted',
             nullif(v_order ->> 'placed_by_guest_session_id', '')::uuid,
             nullif(v_order ->> 'placed_by_user_id', '')::uuid,
             v_order ->> 'order_number',
             (v_order ->> 'customer_locale')::menu.customer_locale,
             (v_order ->> 'publication_snapshot_id')::uuid,
             v_order ->> 'currency_code',
             (v_order ->> 'total_amount_minor')::bigint,
             e.correlation_id,
             v_order ->> 'idempotency_key',
             e.occurred_at,
             e.sequence_number);

        FOR v_line IN SELECT * FROM jsonb_array_elements(e.after -> 'lines') LOOP
            INSERT INTO ordering.order_line
                (id, tenant_id, outlet_id, order_id, line_number, item_id, variant_id,
                 quantity, participant_guest_session_id, snapshot_line_id, item_code,
                 canonical_name, display_name, tax_context, currency_code,
                 unit_amount_minor, line_amount_minor)
            VALUES
                ((v_line ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.order_id,
                 (v_line ->> 'line_number')::integer,
                 (v_line ->> 'item_id')::uuid,
                 (v_line ->> 'variant_id')::uuid,
                 (v_line ->> 'quantity')::integer,
                 nullif(v_line ->> 'participant_guest_session_id', '')::uuid,
                 (v_line ->> 'snapshot_line_id')::bigint,
                 v_line ->> 'item_code',
                 v_line ->> 'canonical_name',
                 v_line ->> 'display_name',
                 v_line ->> 'tax_context',
                 v_line ->> 'currency_code',
                 (v_line ->> 'unit_amount_minor')::bigint,
                 (v_line ->> 'line_amount_minor')::bigint);

            FOR v_mod IN SELECT * FROM jsonb_array_elements(coalesce(v_line -> 'modifiers', '[]'::jsonb)) LOOP
                INSERT INTO ordering.order_line_modifier
                    (id, tenant_id, outlet_id, order_line_id, modifier_id, canonical_name,
                     display_name, currency_code, unit_amount_minor)
                VALUES
                    ((v_mod ->> 'id')::uuid, e.tenant_id, e.outlet_id,
                     (v_line ->> 'id')::uuid,
                     (v_mod ->> 'modifier_id')::uuid,
                     v_mod ->> 'canonical_name',
                     v_mod ->> 'display_name',
                     v_mod ->> 'currency_code',
                     (v_mod ->> 'unit_amount_minor')::bigint);
            END LOOP;
        END LOOP;

        PERFORM ordering.write_charge_components(e, e.after -> 'charges');
        PERFORM ordering.write_notes(e, coalesce(e.after -> 'notes', '[]'::jsonb));

        FOR v_link IN SELECT * FROM jsonb_array_elements(e.after -> 'correlation') LOOP
            INSERT INTO ordering.correlation_link
                (tenant_id, outlet_id, correlation_id, artifact_kind, artifact_id, linked_at)
            VALUES (e.tenant_id, e.outlet_id, e.correlation_id,
                    (v_link ->> 'artifact_kind')::ordering.artifact_kind,
                    (v_link ->> 'artifact_id')::uuid, e.occurred_at)
            ON CONFLICT DO NOTHING;
        END LOOP;

        -- FR-ORD-017. Carried in the event rather than recomputed here, so a rebuild
        -- folds the signal that was actually raised instead of re-deciding it against
        -- whatever the neighbouring orders look like today.
        v_dup := e.after -> 'duplicate_signal';
        IF v_dup IS NOT NULL AND jsonb_typeof(v_dup) = 'object' THEN
            INSERT INTO ordering.duplicate_signal
                (id, tenant_id, outlet_id, order_id, matched_order_id, content_digest,
                 seconds_apart, raised_at)
            VALUES ((v_dup ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.order_id,
                    (v_dup ->> 'matched_order_id')::uuid,
                    decode(v_dup ->> 'content_digest', 'hex'),
                    (v_dup ->> 'seconds_apart')::integer, e.occurred_at);
        END IF;

    ELSIF e.kind = 'accepted' THEN
        UPDATE ordering.customer_order
           SET state = 'accepted',
               acceptance_mode = (e.after ->> 'acceptance_mode')::ordering.acceptance_mode,
               accepted_at = e.occurred_at,
               accepted_by_user_id = nullif(e.after ->> 'accepted_by_user_id', '')::uuid,
               ledger_sequence = e.sequence_number
         WHERE id = e.order_id;

    ELSIF e.kind = 'rejected' THEN
        UPDATE ordering.customer_order
           SET state = 'rejected', resolved_at = e.occurred_at,
               ledger_sequence = e.sequence_number
         WHERE id = e.order_id;

    ELSIF e.kind IN ('cancelled', 'voided') THEN
        UPDATE ordering.customer_order
           SET state = (e.kind::text)::ordering.order_state,
               resolved_at = e.occurred_at,
               ledger_sequence = e.sequence_number
         WHERE id = e.order_id;

    ELSIF e.kind = 'amended' THEN
        -- FR-ORD-010. The amendment carries the lines and charges as they now stand, so
        -- the fold replaces rather than patches: a patch would need the projection to
        -- already be right, and the whole point of a rebuild is that it might not be.
        DELETE FROM ordering.order_charge_component WHERE order_id = e.order_id;
        DELETE FROM ordering.order_line_modifier
         WHERE order_line_id IN (SELECT id FROM ordering.order_line WHERE order_id = e.order_id);
        -- Every note, not only the line-scoped ones. The amendment payload carries the
        -- full set as it now stands, so replacing wholesale is what makes the fold a
        -- function of the event rather than of what happened to be there already.
        DELETE FROM ordering.order_note WHERE order_id = e.order_id;
        DELETE FROM ordering.order_line WHERE order_id = e.order_id;

        FOR v_line IN SELECT * FROM jsonb_array_elements(e.after -> 'lines') LOOP
            INSERT INTO ordering.order_line
                (id, tenant_id, outlet_id, order_id, line_number, item_id, variant_id,
                 quantity, participant_guest_session_id, snapshot_line_id, item_code,
                 canonical_name, display_name, tax_context, currency_code,
                 unit_amount_minor, line_amount_minor)
            VALUES
                ((v_line ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.order_id,
                 (v_line ->> 'line_number')::integer,
                 (v_line ->> 'item_id')::uuid,
                 (v_line ->> 'variant_id')::uuid,
                 (v_line ->> 'quantity')::integer,
                 nullif(v_line ->> 'participant_guest_session_id', '')::uuid,
                 (v_line ->> 'snapshot_line_id')::bigint,
                 v_line ->> 'item_code',
                 v_line ->> 'canonical_name',
                 v_line ->> 'display_name',
                 v_line ->> 'tax_context',
                 v_line ->> 'currency_code',
                 (v_line ->> 'unit_amount_minor')::bigint,
                 (v_line ->> 'line_amount_minor')::bigint);

            FOR v_mod IN SELECT * FROM jsonb_array_elements(coalesce(v_line -> 'modifiers', '[]'::jsonb)) LOOP
                INSERT INTO ordering.order_line_modifier
                    (id, tenant_id, outlet_id, order_line_id, modifier_id, canonical_name,
                     display_name, currency_code, unit_amount_minor)
                VALUES
                    ((v_mod ->> 'id')::uuid, e.tenant_id, e.outlet_id,
                     (v_line ->> 'id')::uuid,
                     (v_mod ->> 'modifier_id')::uuid,
                     v_mod ->> 'canonical_name',
                     v_mod ->> 'display_name',
                     v_mod ->> 'currency_code',
                     (v_mod ->> 'unit_amount_minor')::bigint);
            END LOOP;
        END LOOP;

        PERFORM ordering.write_charge_components(e, e.after -> 'charges');
        PERFORM ordering.write_notes(e, coalesce(e.after -> 'notes', '[]'::jsonb));

        UPDATE ordering.customer_order
           SET total_amount_minor = (e.after ->> 'total_amount_minor')::bigint,
               ledger_sequence = e.sequence_number
         WHERE id = e.order_id;

    ELSIF e.kind IN ('note_added', 'allergy_declared') THEN
        PERFORM ordering.write_notes(e, jsonb_build_array(e.after -> 'note'));
        UPDATE ordering.customer_order SET ledger_sequence = e.sequence_number
         WHERE id = e.order_id;

    ELSIF e.kind = 'session_merged' THEN
        UPDATE ordering.customer_order
           SET table_session_id = (e.after ->> 'table_session_id')::uuid,
               ledger_sequence = e.sequence_number
         WHERE id = e.order_id;
        INSERT INTO ordering.correlation_link
            (tenant_id, outlet_id, correlation_id, artifact_kind, artifact_id, linked_at)
        VALUES (e.tenant_id, e.outlet_id, e.correlation_id, 'table_session',
                (e.after ->> 'table_session_id')::uuid, e.occurred_at)
        ON CONFLICT DO NOTHING;

    ELSIF e.kind = 'session_moved' THEN
        -- Nothing on the order changes: an order names its SESSION, and the session kept
        -- its identity. The entry exists so the timeline can say the table changed.
        UPDATE ordering.customer_order SET ledger_sequence = e.sequence_number
         WHERE id = e.order_id;

    ELSE
        -- Unreachable today: every label of ordering.event_kind is folded above, and
        -- tests/m3a proves that by reading the labels out of the catalog and requiring
        -- each to appear in this function's definition. The branch is here for the day
        -- somebody adds an eleventh label — a fold that silently ignored it would
        -- produce a projection that agrees with its own rebuild and is wrong in both.
        RAISE EXCEPTION
            'LEDGER_EVENT_KIND_UNHANDLED: ordering.apply_event() has no fold for %', e.kind
            USING ERRCODE = 'HS500';
    END IF;

    PERFORM ordering.write_timeline_entry(e);

    PERFORM set_config('ordering.applying_event', '', true);
END;
$$;


-- Helpers the fold uses. Separate functions rather than inlined blocks because the
-- submitted and amended branches must write charges, notes and the timeline the SAME
-- way — two copies of this logic would be two places for them to drift apart.

CREATE FUNCTION ordering.write_charge_components(e ordering.order_event, p_charges jsonb)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, ordering, public
AS $$
DECLARE
    v_charge jsonb;
BEGIN
    FOR v_charge IN SELECT * FROM jsonb_array_elements(coalesce(p_charges, '[]'::jsonb)) LOOP
        INSERT INTO ordering.order_charge_component
            (id, tenant_id, outlet_id, order_id, kind, source_kind, charge_rule_id,
             basis, currency_code, amount_minor)
        VALUES
            ((v_charge ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.order_id,
             (v_charge ->> 'kind')::ordering.charge_kind,
             (v_charge ->> 'source_kind')::ordering.charge_source_kind,
             nullif(v_charge ->> 'charge_rule_id', '')::uuid,
             v_charge -> 'basis',
             v_charge ->> 'currency_code',
             (v_charge ->> 'amount_minor')::bigint);
    END LOOP;
END;
$$;

CREATE FUNCTION ordering.write_notes(e ordering.order_event, p_notes jsonb)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, ordering, public
AS $$
DECLARE
    v_note jsonb;
BEGIN
    FOR v_note IN SELECT * FROM jsonb_array_elements(coalesce(p_notes, '[]'::jsonb)) LOOP
        INSERT INTO ordering.order_note
            (id, tenant_id, outlet_id, order_id, order_line_id, kind, body,
             author_user_id, author_guest_session_id, allergen_id, allergy_concern_id,
             acknowledgement_wording_id, acknowledgement_text, created_at)
        VALUES
            ((v_note ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.order_id,
             nullif(v_note ->> 'order_line_id', '')::uuid,
             (v_note ->> 'kind')::ordering.note_kind,
             v_note ->> 'body',
             nullif(v_note ->> 'author_user_id', '')::uuid,
             nullif(v_note ->> 'author_guest_session_id', '')::uuid,
             nullif(v_note ->> 'allergen_id', '')::uuid,
             nullif(v_note ->> 'allergy_concern_id', '')::uuid,
             nullif(v_note ->> 'acknowledgement_wording_id', '')::uuid,
             nullif(v_note ->> 'acknowledgement_text', ''),
             e.occurred_at)
        ON CONFLICT (id) DO NOTHING;
    END LOOP;
END;
$$;

-- FR-ORD-016A. The audience is decided HERE, once, when the entry is written — not by
-- whoever queries it later. A reader that filters is a reader that can forget to.
CREATE FUNCTION ordering.write_timeline_entry(e ordering.order_event) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, ordering, public
AS $$
DECLARE
    v_note_kind ordering.note_kind;
    v_customer  boolean;
    v_customer_text text;
    v_staff_text    text;
BEGIN
    CASE e.kind
        WHEN 'submitted' THEN
            v_customer := true;
            v_customer_text := 'Your order was received.';
            v_staff_text := 'Order submitted.';
        WHEN 'accepted' THEN
            v_customer := true;
            v_customer_text := 'Your order was confirmed.';
            v_staff_text := 'Order accepted ('
                            || coalesce(e.after ->> 'acceptance_mode', 'unknown') || ').';
        WHEN 'rejected' THEN
            v_customer := true;
            v_customer_text := 'Your order could not be confirmed.';
            v_staff_text := 'Order rejected.';
        WHEN 'amended' THEN
            v_customer := true;
            v_customer_text := 'Your order was changed.';
            v_staff_text := 'Order amended.';
        WHEN 'cancelled' THEN
            v_customer := true;
            v_customer_text := 'Your order was cancelled.';
            v_staff_text := 'Order cancelled.';
        WHEN 'voided' THEN
            -- Staff only. A void names an internal reason code and the manager who
            -- authorized it; telling a customer about the register entry rather than the
            -- consequence is not communication. The customer-facing message for a void
            -- is a notification, and notifications are M3-C.
            v_customer := false;
            v_customer_text := NULL;
            v_staff_text := 'Order voided by authorized staff.';
        WHEN 'allergy_declared' THEN
            v_customer := true;
            v_customer_text := 'An allergy was recorded for this order.';
            v_staff_text := 'ALLERGY DECLARED — see the order notes before preparing.';
        WHEN 'note_added' THEN
            v_note_kind := (e.after -> 'note' ->> 'kind')::ordering.note_kind;
            -- A customer sees that their own note was recorded. A kitchen instruction
            -- and a private staff note are internal, and the customer timeline says
            -- nothing at all about them — not a redacted entry, which would disclose
            -- that something was written.
            v_customer := (v_note_kind = 'customer');
            v_customer_text := CASE WHEN v_note_kind = 'customer'
                                    THEN 'Your note was added to the order.' END;
            v_staff_text := 'Note added (' || v_note_kind::text || ').';
        WHEN 'session_merged' THEN
            v_customer := false;
            v_customer_text := NULL;
            v_staff_text := 'Order consolidated into another table session.';
        WHEN 'session_moved' THEN
            v_customer := false;
            v_customer_text := NULL;
            v_staff_text := 'The table session moved to another table.';
    END CASE;

    INSERT INTO ordering.order_timeline_entry
        (id, tenant_id, outlet_id, order_id, sequence_number, occurred_at, kind,
         visible_to_customer, visible_to_staff, customer_summary, staff_summary)
    VALUES
        -- Derived from the ledger identity, never generated: a rebuilt timeline has to
        -- carry the same primary keys as the one it replaced or the comparison is
        -- between two things that were never going to match.
        (uuid_in(md5('timeline' || e.tenant_id::text || e.order_id::text
                     || e.sequence_number::text)::cstring),
         e.tenant_id, e.outlet_id, e.order_id, e.sequence_number, e.occurred_at, e.kind,
         v_customer, true, v_customer_text, v_staff_text);
END;
$$;

COMMENT ON FUNCTION ordering.write_timeline_entry(ordering.order_event) IS
    'FR-ORD-016A. A CASE with no ELSE over ordering.event_kind: PostgreSQL raises '
    'CASE_NOT_FOUND on an unhandled label rather than writing an entry with a NULL '
    'audience, so a new event kind cannot quietly arrive with no decision about who may '
    'see it.';


-- ---------------------------------------------------------------------------
-- Rebuild and compare (FR-DAT-010)
-- ---------------------------------------------------------------------------

-- A canonical rendering of everything projected for one tenant. Ordered explicitly at
-- every level, because a digest over an unordered read is a digest of whatever the
-- planner felt like doing and would differ between two correct rebuilds.
CREATE FUNCTION ordering.projection_digest(p_tenant_id uuid) RETURNS bytea
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, ordering, public
AS $$
    SELECT sha256(convert_to(string_agg(part, E'\n' ORDER BY part), 'UTF8'))
    FROM (
        SELECT 'order|' || o.id || '|' || o.table_session_id || '|' || o.cart_id || '|'
               || o.origin || '|' || o.channel || '|' || o.state || '|'
               || coalesce(o.placed_by_guest_session_id::text, '-') || '|'
               || coalesce(o.placed_by_user_id::text, '-') || '|' || o.order_number || '|'
               || o.customer_locale || '|' || o.publication_snapshot_id || '|'
               || o.currency_code || '|' || o.total_amount_minor || '|'
               || o.correlation_id || '|' || o.idempotency_key || '|'
               || o.submitted_at || '|' || coalesce(o.acceptance_mode::text, '-') || '|'
               || coalesce(o.accepted_at::text, '-') || '|'
               || coalesce(o.accepted_by_user_id::text, '-') || '|'
               || coalesce(o.resolved_at::text, '-') || '|' || o.ledger_sequence AS part
        FROM ordering.customer_order o WHERE o.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'line|' || l.id || '|' || l.order_id || '|' || l.line_number || '|'
               || l.item_id || '|' || l.variant_id || '|' || l.quantity || '|'
               || coalesce(l.participant_guest_session_id::text, '-') || '|'
               || l.snapshot_line_id || '|' || l.item_code || '|' || l.canonical_name || '|'
               || l.display_name || '|' || l.tax_context || '|' || l.currency_code || '|'
               || l.unit_amount_minor || '|' || l.line_amount_minor
        FROM ordering.order_line l WHERE l.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'modifier|' || m.id || '|' || m.order_line_id || '|' || m.modifier_id || '|'
               || m.canonical_name || '|' || m.display_name || '|' || m.currency_code || '|'
               || m.unit_amount_minor
        FROM ordering.order_line_modifier m WHERE m.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'charge|' || c.id || '|' || c.order_id || '|' || c.kind || '|'
               || c.source_kind || '|' || coalesce(c.charge_rule_id::text, '-') || '|'
               || c.currency_code || '|' || c.amount_minor
        FROM ordering.order_charge_component c WHERE c.tenant_id = p_tenant_id
        UNION ALL
        -- The allergy declaration is digested field by field, so a rebuild that dropped
        -- the allergen or the wording changes the digest rather than merely the row count.
        SELECT 'note|' || n.id || '|' || n.order_id || '|'
               || coalesce(n.order_line_id::text, '-') || '|' || n.kind || '|' || n.body || '|'
               || coalesce(n.author_user_id::text, '-') || '|'
               || coalesce(n.author_guest_session_id::text, '-') || '|'
               || coalesce(n.allergen_id::text, '-') || '|'
               || coalesce(n.allergy_concern_id::text, '-') || '|'
               || coalesce(n.acknowledgement_wording_id::text, '-') || '|'
               || coalesce(n.acknowledgement_text, '-') || '|' || n.created_at
        FROM ordering.order_note n WHERE n.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'timeline|' || t.id || '|' || t.order_id || '|' || t.sequence_number || '|'
               || t.occurred_at || '|' || t.kind || '|' || t.visible_to_customer || '|'
               || t.visible_to_staff || '|' || coalesce(t.customer_summary, '-') || '|'
               || t.staff_summary
        FROM ordering.order_timeline_entry t WHERE t.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'correlation|' || k.correlation_id || '|' || k.artifact_kind || '|'
               || k.artifact_id || '|' || k.linked_at
        FROM ordering.correlation_link k WHERE k.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'duplicate|' || d.id || '|' || d.order_id || '|' || d.matched_order_id || '|'
               || encode(d.content_digest, 'hex') || '|' || d.seconds_apart || '|' || d.raised_at
        FROM ordering.duplicate_signal d WHERE d.tenant_id = p_tenant_id
    ) AS rendered;
$$;

COMMENT ON FUNCTION ordering.projection_digest(uuid) IS
    'A deterministic digest of every order projection for a tenant (FR-DAT-010). Ordered '
    'explicitly, so two correct rebuilds cannot differ by plan; every column that a '
    'projection could lose is in the rendering, so a lost allergen changes the digest '
    'rather than hiding inside a row count that still matches.';

-- Discard every projection and rebuild from the ledger alone.
CREATE FUNCTION ordering.rebuild_projections(p_tenant_id uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, ordering, public
AS $$
DECLARE
    v_event bigint;
    v_count integer := 0;
BEGIN
    PERFORM set_config('ordering.applying_event', 'yes', true);

    DELETE FROM ordering.duplicate_signal WHERE tenant_id = p_tenant_id;
    DELETE FROM ordering.order_timeline_entry WHERE tenant_id = p_tenant_id;
    DELETE FROM ordering.correlation_link WHERE tenant_id = p_tenant_id;
    DELETE FROM ordering.order_note WHERE tenant_id = p_tenant_id;
    DELETE FROM ordering.order_charge_component WHERE tenant_id = p_tenant_id;
    DELETE FROM ordering.order_line_modifier WHERE tenant_id = p_tenant_id;
    DELETE FROM ordering.order_line WHERE tenant_id = p_tenant_id;
    DELETE FROM ordering.customer_order WHERE tenant_id = p_tenant_id;

    PERFORM set_config('ordering.applying_event', '', true);

    -- Replayed in ledger order. The identity column is monotonic in insertion order, so
    -- an order that referenced an earlier one — a duplicate signal naming what it
    -- matched — finds it already there.
    FOR v_event IN
        SELECT id FROM ordering.order_event WHERE tenant_id = p_tenant_id ORDER BY id
    LOOP
        PERFORM ordering.apply_event(v_event);
        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION ordering.rebuild_projections(uuid) IS
    'FR-DAT-010. Discards every order projection for a tenant and replays the ledger. '
    'The suite digests before, rebuilds, digests again and requires the two to be equal '
    '— a comparison of counts would pass while a column was being dropped.';


-- ===========================================================================
-- Policy resolution (FR-ORD-007A, FR-ORD-011)
-- ===========================================================================
-- Outlet policy wins over tenant policy; an absent policy is never an implicit default.
-- M1-C's config.effective_configuration() takes the same posture and this follows it:
-- a tenant that has not decided how orders are accepted cannot accept one.

CREATE FUNCTION ordering.effective_policy(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_category  config.policy_category,
    p_at        timestamptz DEFAULT now()
) RETURNS jsonb
LANGUAGE sql STABLE
AS $$
    SELECT p.payload
    FROM config.policy p
    WHERE p.tenant_id = p_tenant_id
      AND p.category = p_category
      AND (p.outlet_id = p_outlet_id OR p.outlet_id IS NULL)
      AND p.effective_from <= p_at
      AND (p.effective_to IS NULL OR p.effective_to > p_at)
    ORDER BY (p.outlet_id IS NOT NULL) DESC, p.version DESC
    LIMIT 1;
$$;

CREATE FUNCTION ordering.require_policy(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_category  config.policy_category
) RETURNS jsonb
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v jsonb := ordering.effective_policy(p_tenant_id, p_outlet_id, p_category);
BEGIN
    IF v IS NULL THEN
        RAISE EXCEPTION
            'ORDER_POLICY_ABSENT: no % policy is in force for outlet %; an order cannot '
            'be handled under a policy nobody set', p_category, p_outlet_id
            USING ERRCODE = 'HS412';
    END IF;
    RETURN v;
END;
$$;


-- ===========================================================================
-- Charges: resolving what applies (FR-ORD-003)
-- ===========================================================================
-- Generic over kinds. This function names 'item_subtotal' once — because a line price
-- comes from the menu and not from a rule — and after that iterates rules without
-- caring what kind they are. That is what lets a fee reach the total when M4 gives fees
-- a configured source, with nothing here changing.
--
-- What is NOT settled at this gate: whether a discount applies before or after tax. At
-- M3-A both are computed on the line subtotal, which is the only reading that does not
-- pre-empt a decision belonging to FR-BIL-005 at M4. It is recorded as a partial closure
-- rather than left as an assumption in a function body.

CREATE FUNCTION ordering.resolve_charges(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_lines     jsonb,
    p_currency  char(3),
    p_at        timestamptz DEFAULT now()
) RETURNS jsonb
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_out      jsonb := '[]'::jsonb;
    v_subtotal bigint := 0;
    v_line     jsonb;
    v_rule     ordering.charge_rule%ROWTYPE;
    v_base     bigint;
    v_amount   bigint;
BEGIN
    FOR v_line IN SELECT * FROM jsonb_array_elements(p_lines) LOOP
        v_subtotal := v_subtotal + (v_line ->> 'line_amount_minor')::bigint;
    END LOOP;

    v_out := v_out || jsonb_build_object(
        'kind', 'item_subtotal',
        'source_kind', 'menu_price',
        'charge_rule_id', NULL,
        'basis', jsonb_build_object('lines', jsonb_array_length(p_lines)),
        'currency_code', p_currency,
        'amount_minor', v_subtotal);

    -- Ordered by kind then id: a deterministic sequence, so two evaluations of the same
    -- order produce components in the same order and therefore the same digest.
    FOR v_rule IN
        SELECT * FROM ordering.charge_rule r
        WHERE r.tenant_id = p_tenant_id
          AND (r.outlet_id = p_outlet_id OR r.outlet_id IS NULL)
          AND r.effective_from <= p_at
          AND (r.effective_to IS NULL OR r.effective_to > p_at)
        ORDER BY r.kind, r.id
    LOOP
        -- A rule naming a tax context applies to the lines carrying it; one naming none
        -- applies to the whole subtotal.
        IF v_rule.tax_context IS NULL THEN
            v_base := v_subtotal;
        ELSE
            v_base := 0;
            FOR v_line IN SELECT * FROM jsonb_array_elements(p_lines) LOOP
                IF v_line ->> 'tax_context' = v_rule.tax_context THEN
                    v_base := v_base + (v_line ->> 'line_amount_minor')::bigint;
                END IF;
            END LOOP;
        END IF;

        IF v_base = 0 AND v_rule.rate_percentage IS NOT NULL THEN
            CONTINUE;             -- a rate on nothing is not a charge, so no row
        END IF;

        IF v_rule.rate_percentage IS NOT NULL THEN
            v_amount := money.apply_rate(v_base, v_rule.rate_percentage, v_rule.rounding_mode);
        ELSE
            v_amount := v_rule.fixed_amount_minor;
        END IF;

        -- The one place a kind decides a sign, and it decides it for the component
        -- rather than for the sum. ordering.order_total() stays a plain SUM.
        IF v_rule.kind = 'discount' THEN
            v_amount := -v_amount;
        END IF;

        v_out := v_out || jsonb_build_object(
            'kind', v_rule.kind,
            'source_kind', v_rule.source_kind,
            'charge_rule_id', v_rule.id,
            'basis', jsonb_build_object(
                'base_amount_minor', v_base,
                'rate_percentage', v_rule.rate_percentage,
                'fixed_amount_minor', v_rule.fixed_amount_minor,
                'rounding_mode', v_rule.rounding_mode,
                'tax_context', v_rule.tax_context),
            'currency_code', p_currency,
            'amount_minor', v_amount);
    END LOOP;

    RETURN v_out;
END;
$$;


-- ===========================================================================
-- Revalidation at submission (FR-ORD-006)
-- ===========================================================================
-- A preview is not a reservation. Everything the preview asserted is checked again here,
-- at the moment the order is actually placed. Returns the reasons it must not proceed;
-- an empty result is the only thing that lets a submission through.
--
-- Station capacity is the one dimension of FR-ORD-006 this cannot check: stations and
-- their workload are M3-B. Recorded as a partial closure naming M3-B, not silently
-- omitted.

CREATE FUNCTION ordering.revalidate_cart(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_cart_id   uuid,
    p_channel   menu.sales_channel,
    p_at        timestamptz DEFAULT now()
) RETURNS TABLE (dimension text, subject_id uuid, detail text)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_policy jsonb := ordering.require_policy(p_tenant_id, p_outlet_id, 'ordering');
    v_max_qty integer;
    v_tz      text := menu.outlet_timezone(p_tenant_id, p_outlet_id);
    v_local   time := (p_at AT TIME ZONE v_tz)::time;
BEGIN
    IF v_policy ? 'max_line_quantity' THEN
        v_max_qty := (v_policy ->> 'max_line_quantity')::integer;
    ELSE
        RAISE EXCEPTION
            'ORDER_POLICY_INCOMPLETE: the ordering policy for outlet % states no '
            'max_line_quantity; a quantity limit that defaults is not a limit',
            p_outlet_id USING ERRCODE = 'HS412';
    END IF;

    RETURN QUERY
    -- Items and variants that are no longer available.
    SELECT 'availability'::text, cl.variant_id,
           'variant ' || cl.variant_id || ' is ' || a.state::text
    FROM service.cart_line cl
    JOIN menu.availability a
      ON a.tenant_id = cl.tenant_id AND a.outlet_id = cl.outlet_id
     AND a.variant_id = cl.variant_id
    WHERE cl.cart_id = p_cart_id AND cl.tenant_id = p_tenant_id
      AND a.state <> 'available'

    UNION ALL
    SELECT 'availability'::text, cl.item_id,
           'item ' || cl.item_id || ' is ' || a.state::text
    FROM service.cart_line cl
    JOIN menu.availability a
      ON a.tenant_id = cl.tenant_id AND a.outlet_id = cl.outlet_id
     AND a.item_id = cl.item_id
    WHERE cl.cart_id = p_cart_id AND cl.tenant_id = p_tenant_id
      AND a.state <> 'available'

    UNION ALL
    -- Modifiers, which have their own availability and are chosen line by line.
    SELECT 'availability'::text, clm.modifier_id,
           'modifier ' || clm.modifier_id || ' is ' || a.state::text
    FROM service.cart_line cl
    JOIN service.cart_line_modifier clm
      ON clm.tenant_id = cl.tenant_id AND clm.cart_line_id = cl.id
    JOIN menu.availability a
      ON a.tenant_id = cl.tenant_id AND a.outlet_id = cl.outlet_id
     AND a.modifier_id = clm.modifier_id
    WHERE cl.cart_id = p_cart_id AND cl.tenant_id = p_tenant_id
      AND a.state <> 'available'

    UNION ALL
    -- Quantity: ordered units, not stock. A cart line asking for two hundred of
    -- something is a mistake or a probe, and either way it is not an order.
    SELECT 'quantity'::text, cl.id,
           'line quantity ' || cl.quantity || ' exceeds the configured maximum of ' || v_max_qty
    FROM service.cart_line cl
    WHERE cl.cart_id = p_cart_id AND cl.tenant_id = p_tenant_id
      AND cl.quantity > v_max_qty

    UNION ALL
    -- Channel and hours, together: a menu reaches this outlet on this channel inside a
    -- daypart, and all three are one assignment. Reported as one dimension because
    -- "the kitchen is closed" and "this menu is not for QR" are the same absence.
    SELECT 'channel_or_hours'::text, cl.item_id,
           'no menu assignment reaches outlet ' || p_outlet_id || ' on channel '
           || p_channel::text || ' at ' || v_local::text || ' ' || v_tz
           || ' for item ' || cl.item_id
    FROM service.cart_line cl
    JOIN menu.sellable_item si ON si.id = cl.item_id
    WHERE cl.cart_id = p_cart_id AND cl.tenant_id = p_tenant_id
      AND NOT EXISTS (
            SELECT 1 FROM menu.assignment asg
            LEFT JOIN menu.daypart dp ON dp.id = asg.daypart_id
            WHERE asg.tenant_id = p_tenant_id
              AND asg.outlet_id = p_outlet_id
              AND asg.menu_id = si.menu_id
              AND asg.channel = p_channel
              AND asg.effective_from <= (p_at AT TIME ZONE v_tz)::date
              AND (asg.effective_to IS NULL OR asg.effective_to >= (p_at AT TIME ZONE v_tz)::date)
              AND (asg.daypart_id IS NULL
                   OR (dp.starts_at_local <= dp.ends_at_local
                       AND v_local >= dp.starts_at_local AND v_local < dp.ends_at_local)
                   -- A window whose end is before its start crosses midnight, exactly as
                   -- menu.daypart says it does.
                   OR (dp.starts_at_local > dp.ends_at_local
                       AND (v_local >= dp.starts_at_local OR v_local < dp.ends_at_local))));
END;
$$;

COMMENT ON FUNCTION ordering.revalidate_cart(uuid, uuid, uuid, menu.sales_channel, timestamptz) IS
    'FR-ORD-006. Availability, hours, channel and quantity re-checked at submission, '
    'because a preview is not a reservation. Station capacity is the fifth dimension the '
    'requirement names and it needs the stations M3-B builds; that half is recorded in '
    'planning/partial_closures.json rather than quietly skipped.';


-- ===========================================================================
-- Preview (FR-ORD-003)
-- ===========================================================================
-- Server-calculated, and the emphasis belongs on CALCULATED. Every figure below is
-- worked out here from the published snapshot and the configured rules. There is no
-- parameter through which a caller can state a price, a component or a total, so a
-- client-computed figure has nowhere to enter — which is a stronger guarantee than
-- validating one after it arrives.
--
-- The pricing_digest is the whole of what was calculated, so that a submission can
-- prove it is submitting the thing that was previewed. It is not a price the client
-- supplies: it is a claim about what the client SAW, and the server recomputes the
-- figures either way.

CREATE FUNCTION ordering.current_snapshot(p_tenant_id uuid, p_menu_id uuid)
RETURNS uuid
LANGUAGE sql STABLE
AS $$
    SELECT s.id FROM menu.publication_snapshot s
    WHERE s.tenant_id = p_tenant_id AND s.menu_id = p_menu_id
    ORDER BY s.published_at DESC, s.id DESC
    LIMIT 1;
$$;

CREATE FUNCTION ordering.preview_cart(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_cart_id   uuid,
    p_locale    menu.customer_locale,
    p_channel   menu.sales_channel DEFAULT 'dine_in',
    p_at        timestamptz DEFAULT now()
) RETURNS jsonb
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_cart        service.cart%ROWTYPE;
    v_menu_id     uuid;
    v_snapshot    uuid;
    v_currency    char(3);
    v_lines       jsonb := '[]'::jsonb;
    v_charges     jsonb;
    v_total       bigint := 0;
    v_line        record;
    v_mods        jsonb;
    v_warnings    jsonb := '[]'::jsonb;
    v_blocks      jsonb := '[]'::jsonb;
    v_prep        integer := 0;
    v_line_number integer := 0;
    v_charge      jsonb;
BEGIN
    SELECT * INTO v_cart FROM service.cart WHERE id = p_cart_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'CART_NOT_FOUND: no cart % in scope', p_cart_id
            USING ERRCODE = 'HS404';
    END IF;

    SELECT DISTINCT si.menu_id INTO v_menu_id
    FROM service.cart_line cl JOIN menu.sellable_item si ON si.id = cl.item_id
    WHERE cl.cart_id = p_cart_id AND cl.tenant_id = p_tenant_id;

    IF v_menu_id IS NULL THEN
        RAISE EXCEPTION 'CART_EMPTY: cart % has no lines to price', p_cart_id
            USING ERRCODE = 'HS409';
    END IF;

    v_snapshot := ordering.current_snapshot(p_tenant_id, v_menu_id);
    IF v_snapshot IS NULL THEN
        RAISE EXCEPTION
            'MENU_NOT_PUBLISHED: menu % has no publication to price against; a price '
            'that is not published is not a price a guest was shown', v_menu_id
            USING ERRCODE = 'HS412';
    END IF;

    -- One cart line resolves to exactly ONE snapshot line. A publication carries a row
    -- per (variant, channel), so a variant with a channel-specific price has more than
    -- one row in the snapshot and a plain join on variant_id returns both — which
    -- priced a single dish twice and produced a subtotal nobody ordered. The precedence
    -- is the one menu.effective_price() already uses: the row for THIS channel if there
    -- is one, otherwise the row that names no channel, and never a row for a different
    -- channel. LATERAL with LIMIT 1 over that ordering picks it; the count check after
    -- the loop refuses a cart where any line resolved to none.
    FOR v_line IN
        SELECT cl.id AS cart_line_id, cl.item_id, cl.variant_id, cl.quantity,
               cl.added_by_guest_session_id,
               psl.id AS snapshot_line_id, psl.item_code, psl.canonical_name,
               psl.currency_code, psl.amount_minor, psl.tax_context,
               si.preparation_minutes,
               coalesce(nullif(tr.translated_text, ''), psl.canonical_name) AS display_name
        FROM service.cart_line cl
        JOIN menu.sellable_item si ON si.id = cl.item_id
        JOIN LATERAL (
            SELECT l.*
            FROM menu.publication_snapshot_line l
            WHERE l.snapshot_id = v_snapshot
              AND l.variant_id = cl.variant_id
              AND (l.channel = p_channel OR l.channel IS NULL)
            ORDER BY (l.channel IS NOT NULL) DESC, l.id
            LIMIT 1
        ) psl ON true
        LEFT JOIN menu.translation tr
          ON tr.tenant_id = cl.tenant_id AND tr.entity = 'item'
         AND tr.entity_id = cl.item_id AND tr.field_name = 'canonical_name'
         AND tr.locale = p_locale AND tr.state = 'approved'
        WHERE cl.cart_id = p_cart_id AND cl.tenant_id = p_tenant_id
        ORDER BY cl.added_at, cl.id
    LOOP
        v_line_number := v_line_number + 1;
        v_currency := v_line.currency_code;

        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'modifier_id', m.id,
                   'canonical_name', m.canonical_name,
                   'display_name', coalesce(nullif(mt.translated_text, ''), m.canonical_name),
                   'currency_code', pr.currency_code,
                   'unit_amount_minor', pr.amount_minor)
                   ORDER BY m.display_order, m.id), '[]'::jsonb)
          INTO v_mods
          FROM service.cart_line_modifier clm
          JOIN menu.modifier m ON m.id = clm.modifier_id
          LEFT JOIN menu.price pr
            ON pr.tenant_id = p_tenant_id AND pr.modifier_id = m.id
           AND pr.effective_from <= p_at
           AND (pr.effective_to IS NULL OR pr.effective_to > p_at)
          LEFT JOIN menu.translation mt
            ON mt.tenant_id = p_tenant_id AND mt.entity = 'modifier'
           AND mt.entity_id = m.id AND mt.field_name = 'canonical_name'
           AND mt.locale = p_locale AND mt.state = 'approved'
         WHERE clm.cart_line_id = v_line.cart_line_id AND clm.tenant_id = p_tenant_id;

        v_lines := v_lines || jsonb_build_object(
            'cart_line_id', v_line.cart_line_id,
            'line_number', v_line_number,
            'item_id', v_line.item_id,
            'variant_id', v_line.variant_id,
            'quantity', v_line.quantity,
            'participant_guest_session_id', v_line.added_by_guest_session_id,
            'snapshot_line_id', v_line.snapshot_line_id,
            'item_code', v_line.item_code,
            'canonical_name', v_line.canonical_name,
            'display_name', v_line.display_name,
            'tax_context', v_line.tax_context,
            'currency_code', v_line.currency_code,
            'unit_amount_minor', v_line.amount_minor,
            'line_amount_minor',
                v_line.amount_minor * v_line.quantity
                + coalesce((SELECT sum((x ->> 'unit_amount_minor')::bigint) * v_line.quantity
                            FROM jsonb_array_elements(v_mods) x), 0),
            'modifiers', v_mods);

        v_prep := greatest(v_prep, coalesce(v_line.preparation_minutes, 0));

        -- FR-SAF-003 carried forward from M2-B, unchanged: the safety sentence is read
        -- LIVE from safety.selection_safety() at the moment of the preview, never from
        -- anything pinned. A correction published this morning reaches this afternoon's
        -- preview because nothing here caches it.
        v_warnings := v_warnings || coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                       'variant_id', v_line.variant_id,
                       'kitchen_code', s.kitchen_code,
                       'declaration_class', s.declaration_class,
                       'written_warning', s.written_warning)
                   ORDER BY s.kitchen_code)
            FROM safety.selection_safety(p_tenant_id, p_locale, v_line.item_id,
                                         v_line.variant_id,
                                         ARRAY(SELECT (x ->> 'modifier_id')::uuid
                                               FROM jsonb_array_elements(v_mods) x)) s),
            '[]'::jsonb);
    END LOOP;

    -- Every cart line must have been priced. A LATERAL that found nothing drops the
    -- line silently, and a guest charged for three of four dishes has been undercharged
    -- for a reason nobody would notice until the kitchen made the fourth.
    IF v_line_number <> (SELECT count(*) FROM service.cart_line
                          WHERE cart_id = p_cart_id AND tenant_id = p_tenant_id) THEN
        RAISE EXCEPTION
            'CART_LINE_NOT_IN_PUBLICATION: % of % cart lines could be priced against '
            'publication %; a line the published menu does not carry cannot be ordered',
            v_line_number,
            (SELECT count(*) FROM service.cart_line
              WHERE cart_id = p_cart_id AND tenant_id = p_tenant_id),
            v_snapshot
            USING ERRCODE = 'HS409';
    END IF;

    v_charges := ordering.resolve_charges(p_tenant_id, p_outlet_id, v_lines, v_currency, p_at);
    FOR v_charge IN SELECT * FROM jsonb_array_elements(v_charges) LOOP
        v_total := v_total + (v_charge ->> 'amount_minor')::bigint;
    END LOOP;

    v_blocks := coalesce((
        SELECT jsonb_agg(jsonb_build_object('dimension', r.dimension,
                                            'subject_id', r.subject_id,
                                            'detail', r.detail))
        FROM ordering.revalidate_cart(p_tenant_id, p_outlet_id, p_cart_id, p_channel, p_at) r
    ), '[]'::jsonb);

    RETURN jsonb_build_object(
        'cart_id', p_cart_id,
        'table_session_id', v_cart.table_session_id,
        'publication_snapshot_id', v_snapshot,
        'locale', p_locale,
        'channel', p_channel,
        'currency_code', v_currency,
        'lines', v_lines,
        'charges', v_charges,
        'total_amount_minor', v_total,
        'preparation_minutes', v_prep,
        'safety_warnings', v_warnings,
        'blocking', v_blocks,
        'pricing_digest', encode(ordering.pricing_digest(v_lines, v_charges, v_total), 'hex'));
END;
$$;

COMMENT ON FUNCTION ordering.preview_cart(uuid, uuid, uuid, menu.customer_locale, menu.sales_channel, timestamptz) IS
    'FR-ORD-003. Line prices, modifiers, tax, fees, discounts, availability, timing and '
    'policy warnings, every one of them calculated here. The function has no parameter '
    'through which a caller could state a figure, so there is nothing to validate away: '
    'a client-computed total has no route in.';

-- What a preview committed to, in a form a submission can compare against. Covers the
-- figures and nothing else: the digest must not change because a translation was
-- approved between preview and submission, only because the MONEY moved.
CREATE FUNCTION ordering.pricing_digest(p_lines jsonb, p_charges jsonb, p_total bigint)
RETURNS bytea
LANGUAGE sql IMMUTABLE
AS $$
    SELECT sha256(convert_to(
        coalesce((SELECT string_agg(
                      (l ->> 'variant_id') || ':' || (l ->> 'quantity') || ':'
                      || (l ->> 'unit_amount_minor') || ':' || (l ->> 'line_amount_minor'),
                      '|' ORDER BY (l ->> 'line_number')::integer)
                  FROM jsonb_array_elements(p_lines) l), '')
        || '#'
        || coalesce((SELECT string_agg(
                        (c ->> 'kind') || ':' || coalesce(c ->> 'charge_rule_id', '-') || ':'
                        || (c ->> 'amount_minor'),
                        '|' ORDER BY (c ->> 'kind'), coalesce(c ->> 'charge_rule_id', '-'))
                     FROM jsonb_array_elements(p_charges) c), '')
        || '#' || p_total::text, 'UTF8'));
$$;


-- ===========================================================================
-- Submission (FR-ORD-004, FR-ORD-005, FR-ORD-006, FR-ORD-007A, FR-ORD-013, FR-ORD-017)
-- ===========================================================================
-- The one door. Everything an order needs to be true is checked here, in the order that
-- makes a failure cheap: the key first, then what was agreed, then whether it can still
-- be made, and only then is anything written.
--
-- On the two client-supplied parameters, because they look like a contradiction of
-- "server-calculated" and are not:
--
--   p_pricing_digest       is a claim about what the guest SAW. The server recomputes
--                          the figures regardless and compares. A wrong digest cannot
--                          produce a wrong price; it can only produce a refusal.
--   p_expected_total_minor is the guest saying "I agree to pay this". It is COMPARED and
--                          never stored. The order's total comes from the components,
--                          and ordering.assert_total_is_the_sum() would refuse the
--                          commit if it did not.
--
-- Both are compare-only, and NC-M3-005 plants the defect of storing the second one to
-- show that the difference is enforced rather than merely intended.

CREATE FUNCTION ordering.submit_order(
    p_tenant_id            uuid,
    p_outlet_id            uuid,
    p_cart_id              uuid,
    p_idempotency_key      text,
    p_pricing_digest       bytea,
    p_expected_total_minor bigint,
    p_locale               menu.customer_locale,
    p_correlation_id       uuid,
    p_request_id           uuid,
    p_origin               ordering.order_origin,
    p_actor_user_id        uuid DEFAULT NULL,
    p_actor_guest_session_id uuid DEFAULT NULL,
    p_repeat_intent        boolean DEFAULT false,
    p_allergy_declarations jsonb DEFAULT '[]'::jsonb,
    p_notes                jsonb DEFAULT '[]'::jsonb,
    p_channel              menu.sales_channel DEFAULT 'dine_in'
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_claim      record;
    v_preview    jsonb;
    v_cart       service.cart%ROWTYPE;
    v_order_id   uuid;
    v_number     text;
    v_total      bigint;
    v_digest     bytea;
    v_block      jsonb;
    v_policy     jsonb;
    v_mode       ordering.acceptance_mode;
    v_seq        integer := 1;
    v_event_id   bigint;
    v_notes      jsonb := '[]'::jsonb;
    v_note       jsonb;
    v_lines      jsonb;
    v_content    bytea;
    v_match      record;
    v_window     integer;
    v_dup        jsonb := NULL;
    v_decl       jsonb;
    v_concern    safety.allergy_concern%ROWTYPE;
    v_actor_kind ordering.actor_kind;
BEGIN
    -- FR-ORD-004: required, not optional and not defaulted. A submission with no key is
    -- a submission that cannot be retried safely, and that is refused before anything
    -- else happens.
    IF p_idempotency_key IS NULL OR btrim(p_idempotency_key) = '' THEN
        RAISE EXCEPTION
            'IDEMPOTENCY_KEY_REQUIRED: an order submission must carry an idempotency key'
            USING ERRCODE = 'HS400';
    END IF;

    v_actor_kind := CASE p_origin WHEN 'guest_qr' THEN 'guest' ELSE 'staff' END;

    SELECT * INTO v_cart FROM service.cart WHERE id = p_cart_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'CART_NOT_FOUND: no cart % in scope', p_cart_id
            USING ERRCODE = 'HS404';
    END IF;

    -- The claim covers what was asked for. A retry with the same key and a different
    -- cart, locale or price is not a retry, and M2-C's ledger refuses it by name.
    SELECT * INTO v_claim FROM service.claim_idempotency(
        p_tenant_id, p_outlet_id, 'order_submission', p_idempotency_key,
        p_cart_id::text || '|' || encode(p_pricing_digest, 'hex') || '|' || p_locale::text
        || '|' || p_origin::text || '|' || coalesce(p_actor_guest_session_id::text, '-')
        || '|' || coalesce(p_actor_user_id::text, '-'));

    IF v_claim.is_replay THEN
        IF v_claim.result_id IS NULL THEN
            -- The first attempt claimed the key and has not finished. Returning success
            -- would be a lie and starting a second attempt would be the duplicate this
            -- whole mechanism exists to prevent.
            RAISE EXCEPTION
                'SUBMISSION_IN_FLIGHT: the first submission under key % has not completed',
                p_idempotency_key USING ERRCODE = 'HS409';
        END IF;
        -- FR-ORD-004: the ORIGINAL outcome. Not a fresh success, not an error.
        RETURN v_claim.result_id;
    END IF;

    v_preview := ordering.preview_cart(p_tenant_id, p_outlet_id, p_cart_id, p_locale,
                                       p_channel);
    v_lines := v_preview -> 'lines';
    v_total := (v_preview ->> 'total_amount_minor')::bigint;
    v_digest := decode(v_preview ->> 'pricing_digest', 'hex');

    -- FR-ORD-005 / NC-M3-002. The order must carry what was shown. A price that moved
    -- between preview and submission is refused rather than absorbed: the guest sees the
    -- new figure and agrees to it, or does not.
    IF v_digest IS DISTINCT FROM p_pricing_digest THEN
        RAISE EXCEPTION
            'PRICE_CHANGED_SINCE_PREVIEW: the priced cart is no longer what was previewed; '
            'submitting it would move the total under the guest'
            USING ERRCODE = 'HS409';
    END IF;

    -- The guest's own arithmetic disagreeing with the server's is worth a refusal too,
    -- and the SERVER figure is the one that would have been stored either way.
    IF p_expected_total_minor IS NOT NULL AND p_expected_total_minor <> v_total THEN
        RAISE EXCEPTION
            'TOTAL_DISAGREEMENT: the submission expected % but the order prices at %',
            p_expected_total_minor, v_total USING ERRCODE = 'HS409';
    END IF;

    -- FR-ORD-006. A preview is not a reservation.
    FOR v_block IN SELECT * FROM jsonb_array_elements(v_preview -> 'blocking') LOOP
        RAISE EXCEPTION
            'SUBMISSION_REVALIDATION_FAILED: % — %',
            v_block ->> 'dimension', v_block ->> 'detail'
            USING ERRCODE = 'HS409';
    END LOOP;

    v_order_id := gen_random_uuid();
    v_number := config.issue_document_number(
        p_tenant_id, 'dine_in_order', to_char(now(), 'YYYY'), NULL, p_outlet_id);

    -- FR-ORD-013: customer notes and kitchen instructions travel with the submission.
    -- Allergy declarations do NOT — they get an event of their own below, so the ledger
    -- and the timeline both name them rather than burying them in a payload.
    FOR v_note IN SELECT * FROM jsonb_array_elements(p_notes) LOOP
        IF (v_note ->> 'kind') = 'allergy_declaration' THEN
            RAISE EXCEPTION
                'ALLERGY_DECLARATION_NOT_A_PLAIN_NOTE: an allergy declaration is raised '
                'through p_allergy_declarations so it carries the wording the guest was '
                'actually shown; it cannot be posted as free text'
                USING ERRCODE = 'HS400';
        END IF;
        IF (v_note ->> 'kind') IN ('kitchen_instruction', 'private_staff')
           AND p_actor_user_id IS NULL THEN
            RAISE EXCEPTION
                'STAFF_NOTE_WITHOUT_STAFF_AUTHOR: a % note names the member of staff who '
                'wrote it, and this submission names none', v_note ->> 'kind'
                USING ERRCODE = 'HS403';
        END IF;
        v_notes := v_notes || jsonb_build_object(
            'id', gen_random_uuid(),
            'order_line_id', NULL,
            'kind', v_note ->> 'kind',
            'body', v_note ->> 'body',
            'author_user_id', p_actor_user_id,
            'author_guest_session_id', p_actor_guest_session_id);
    END LOOP;

    -- FR-ORD-017. Content, not key: two submissions with different keys that ask for the
    -- same things within the configured window are a suspected duplicate. A guest who
    -- says "yes, another round" is not, and produces no signal at all.
    v_policy := ordering.require_policy(p_tenant_id, p_outlet_id, 'ordering');
    IF NOT (v_policy ? 'duplicate_window_seconds') THEN
        RAISE EXCEPTION
            'ORDER_POLICY_INCOMPLETE: the ordering policy for outlet % states no '
            'duplicate_window_seconds', p_outlet_id USING ERRCODE = 'HS412';
    END IF;
    v_window := (v_policy ->> 'duplicate_window_seconds')::integer;

    v_content := sha256(convert_to(coalesce((
        SELECT string_agg((l ->> 'variant_id') || ':' || (l ->> 'quantity'), '|'
                          ORDER BY (l ->> 'variant_id'), (l ->> 'quantity'))
        FROM jsonb_array_elements(v_lines) l), ''), 'UTF8'));

    IF NOT p_repeat_intent THEN
        SELECT o.id, o.submitted_at INTO v_match
        FROM ordering.customer_order o
        JOIN ordering.duplicate_content_digest(o.tenant_id, o.id) d ON true
        WHERE o.tenant_id = p_tenant_id
          AND o.table_session_id = v_cart.table_session_id
          AND o.state <> 'rejected'
          AND o.submitted_at > now() - make_interval(secs => v_window)
          AND d.digest = v_content
        ORDER BY o.submitted_at DESC
        LIMIT 1;

        IF FOUND THEN
            v_dup := jsonb_build_object(
                'id', gen_random_uuid(),
                'matched_order_id', v_match.id,
                'content_digest', encode(v_content, 'hex'),
                'seconds_apart', floor(extract(epoch FROM now() - v_match.submitted_at))::integer);
        END IF;
    END IF;

    INSERT INTO ordering.order_event
        (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind, actor_user_id,
         actor_guest_session_id, correlation_id, after)
    VALUES
        (p_tenant_id, p_outlet_id, v_order_id, v_seq, 'submitted', v_actor_kind,
         p_actor_user_id, p_actor_guest_session_id, p_correlation_id,
         jsonb_build_object(
            'order', jsonb_build_object(
                'table_session_id', v_cart.table_session_id,
                'cart_id', p_cart_id,
                'origin', p_origin,
                'channel', p_channel,
                'placed_by_guest_session_id', p_actor_guest_session_id,
                'placed_by_user_id', p_actor_user_id,
                'order_number', v_number,
                'customer_locale', p_locale,
                'publication_snapshot_id', v_preview ->> 'publication_snapshot_id',
                'currency_code', v_preview ->> 'currency_code',
                'total_amount_minor', v_total,
                'idempotency_key', p_idempotency_key),
            -- WITH ORDINALITY and an explicit ORDER BY: jsonb_agg over an unordered
            -- read is aggregation in whatever order the executor produced, and a ledger
            -- payload that reordered between two runs would make the rebuild comparison
            -- a coin toss rather than a check.
            'lines', (SELECT coalesce(jsonb_agg(l - 'cart_line_id' || jsonb_build_object(
                                 'id', gen_random_uuid()) ORDER BY n), '[]'::jsonb)
                      FROM jsonb_array_elements(v_lines) WITH ORDINALITY AS a(l, n)),
            'charges', (SELECT coalesce(jsonb_agg(c || jsonb_build_object(
                                   'id', gen_random_uuid()) ORDER BY n), '[]'::jsonb)
                        FROM jsonb_array_elements(v_preview -> 'charges')
                             WITH ORDINALITY AS b(c, n)),
            'notes', v_notes,
            'correlation', jsonb_build_array(
                jsonb_build_object('artifact_kind', 'request',       'artifact_id', p_request_id),
                jsonb_build_object('artifact_kind', 'cart',          'artifact_id', p_cart_id),
                jsonb_build_object('artifact_kind', 'table_session', 'artifact_id', v_cart.table_session_id),
                jsonb_build_object('artifact_kind', 'order',         'artifact_id', v_order_id)),
            'duplicate_signal', v_dup))
    RETURNING id INTO v_event_id;

    PERFORM ordering.apply_event(v_event_id);

    -- FR-ORD-013 / NC-M3-003. One event per declaration. The wording is COPIED from the
    -- table-level concern M2-B already recorded, never composed here and never taken
    -- from the caller: what a guest was told is one fact with one source.
    FOR v_decl IN SELECT * FROM jsonb_array_elements(p_allergy_declarations) LOOP
        SELECT * INTO v_concern FROM safety.allergy_concern
         WHERE id = (v_decl ->> 'allergy_concern_id')::uuid AND tenant_id = p_tenant_id;

        IF NOT FOUND OR v_concern.table_session_id <> v_cart.table_session_id THEN
            RAISE EXCEPTION
                'ALLERGY_CONCERN_NOT_FOR_THIS_TABLE: declaration % does not belong to the '
                'occupancy this order is being placed for',
                v_decl ->> 'allergy_concern_id' USING ERRCODE = 'HS409';
        END IF;

        IF v_concern.allergen_id IS NULL THEN
            RAISE EXCEPTION
                'ALLERGY_DECLARATION_NAMES_NO_ALLERGEN: concern % names no allergen, and '
                'a declaration a kitchen cannot act on is not a declaration',
                v_concern.id USING ERRCODE = 'HS409';
        END IF;

        v_seq := v_seq + 1;
        INSERT INTO ordering.order_event
            (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind,
             actor_user_id, actor_guest_session_id, correlation_id, after)
        VALUES
            (p_tenant_id, p_outlet_id, v_order_id, v_seq, 'allergy_declared', v_actor_kind,
             p_actor_user_id, p_actor_guest_session_id, p_correlation_id,
             jsonb_build_object('note', jsonb_build_object(
                'id', gen_random_uuid(),
                'order_line_id', NULL,
                'kind', 'allergy_declaration',
                'body', coalesce(nullif(v_decl ->> 'body', ''), v_concern.note,
                                 'Allergy declared at the table.'),
                'author_user_id', p_actor_user_id,
                'author_guest_session_id', p_actor_guest_session_id,
                'allergen_id', v_concern.allergen_id,
                'allergy_concern_id', v_concern.id,
                'acknowledgement_wording_id', v_concern.acknowledgement_wording_id,
                'acknowledgement_text', v_concern.acknowledgement_text)))
        RETURNING id INTO v_event_id;

        PERFORM ordering.apply_event(v_event_id);
    END LOOP;

    -- FR-ORD-007A. Resolved per channel and outlet policy, and an outlet that has not
    -- said how it accepts orders does not accept one.
    IF NOT (v_policy -> 'acceptance' ? p_origin::text) THEN
        RAISE EXCEPTION
            'ACCEPTANCE_POLICY_ABSENT: the ordering policy for outlet % says nothing '
            'about accepting a % order', p_outlet_id, p_origin
            USING ERRCODE = 'HS412';
    END IF;
    v_mode := (v_policy -> 'acceptance' ->> p_origin::text)::ordering.acceptance_mode;

    IF v_mode = 'automatic' THEN
        v_seq := v_seq + 1;
        INSERT INTO ordering.order_event
            (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind,
             correlation_id, after)
        VALUES
            (p_tenant_id, p_outlet_id, v_order_id, v_seq, 'accepted', 'system',
             p_correlation_id,
             jsonb_build_object('acceptance_mode', 'automatic', 'accepted_by_user_id', NULL))
        RETURNING id INTO v_event_id;
        PERFORM ordering.apply_event(v_event_id);
    END IF;

    PERFORM service.record_idempotent_result(
        p_tenant_id, 'order_submission', p_idempotency_key, v_order_id);

    RETURN v_order_id;
END;
$$;

-- The content of an order, for duplicate detection: what was asked for, not what it
-- cost. A second round at a changed price is still a second round.
CREATE FUNCTION ordering.duplicate_content_digest(p_tenant_id uuid, p_order_id uuid)
RETURNS TABLE (digest bytea)
LANGUAGE sql STABLE
AS $$
    SELECT sha256(convert_to(coalesce(
        string_agg(l.variant_id::text || ':' || l.quantity::text, '|'
                   ORDER BY l.variant_id::text, l.quantity), ''), 'UTF8'))
    FROM ordering.order_line l
    WHERE l.tenant_id = p_tenant_id AND l.order_id = p_order_id;
$$;


-- ===========================================================================
-- Acceptance, amendment, cancellation, void
-- ===========================================================================

CREATE FUNCTION ordering.next_sequence(p_tenant_id uuid, p_order_id uuid)
RETURNS integer
LANGUAGE sql STABLE
AS $$
    SELECT coalesce(max(sequence_number), 0) + 1
    FROM ordering.order_event
    WHERE tenant_id = p_tenant_id AND order_id = p_order_id;
$$;

-- FR-ORD-007A, the staff-confirmed half.
CREATE FUNCTION ordering.accept_order(
    p_tenant_id uuid, p_order_id uuid, p_user_id uuid
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
    IF v_order.state <> 'submitted' THEN
        RAISE EXCEPTION
            'ORDER_NOT_AWAITING_ACCEPTANCE: order % is %, not submitted',
            p_order_id, v_order.state USING ERRCODE = 'HS409';
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

-- FR-ORD-010. An amendment is an EVENT carrying both sides, not an edit. The window is
-- decided by the ordering policy; at M3-A that window can only be expressed in terms of
-- the commercial state, because preparation progress is a fulfillment ticket and those
-- are M3-B. Recorded as a partial closure naming M3-B.
CREATE FUNCTION ordering.amend_order_line(
    p_tenant_id   uuid,
    p_order_id    uuid,
    p_order_line_id uuid,
    p_new_quantity integer,
    p_actor_user_id uuid DEFAULT NULL,
    p_actor_guest_session_id uuid DEFAULT NULL
) RETURNS void
-- SECURITY DEFINER because the amendment payload has to carry the order's NOTES
-- forward, and the application role holds no SELECT on ordering.order_note — which is
-- the point of that revocation. The alternative, a helper that handed the note payload
-- back to the caller, would be a route by which a guest could read a private staff note
-- as JSON. The payload is assembled and consumed inside this function and never
-- returned. Row level security is FORCED on every table it touches and its predicate
-- reads the session context, so the definer rights widen what may be written, never
-- which tenant's rows are visible.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, ordering, config, public
AS $$
DECLARE
    v_order  ordering.customer_order%ROWTYPE;
    v_policy jsonb;
    v_allowed jsonb;
    v_before jsonb;
    v_lines  jsonb;
    v_charges jsonb;
    v_total  bigint := 0;
    v_charge jsonb;
    v_event  bigint;
    v_actor_kind ordering.actor_kind;
BEGIN
    SELECT * INTO v_order FROM ordering.customer_order
     WHERE id = p_order_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ORDER_NOT_FOUND: no order % in scope', p_order_id
            USING ERRCODE = 'HS404';
    END IF;

    v_policy := ordering.require_policy(p_tenant_id, v_order.outlet_id, 'ordering');
    IF NOT (v_policy ? 'amendment_allowed_states') THEN
        RAISE EXCEPTION
            'ORDER_POLICY_INCOMPLETE: the ordering policy states no '
            'amendment_allowed_states' USING ERRCODE = 'HS412';
    END IF;
    v_allowed := v_policy -> 'amendment_allowed_states';

    IF NOT (v_allowed @> to_jsonb(v_order.state::text)) THEN
        RAISE EXCEPTION
            'AMENDMENT_WINDOW_CLOSED: order % is % and the ordering policy permits '
            'amendment only in %', p_order_id, v_order.state, v_allowed
            USING ERRCODE = 'HS409';
    END IF;

    IF p_new_quantity <= 0 THEN
        RAISE EXCEPTION
            'AMENDMENT_QUANTITY_INVALID: an amended line orders at least one; removing a '
            'line is a cancellation and is recorded as one' USING ERRCODE = 'HS400';
    END IF;

    -- Both sides, retained. The BEFORE is captured from the projection as it stands, and
    -- the projection is itself a fold of the ledger, so the two agree by construction.
    SELECT jsonb_build_object(
               'lines', coalesce(jsonb_agg(jsonb_build_object(
                   'id', l.id, 'line_number', l.line_number, 'variant_id', l.variant_id,
                   'quantity', l.quantity, 'line_amount_minor', l.line_amount_minor)
                   ORDER BY l.line_number), '[]'::jsonb),
               'total_amount_minor', v_order.total_amount_minor)
      INTO v_before
      FROM ordering.order_line l
     WHERE l.tenant_id = p_tenant_id AND l.order_id = p_order_id;

    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'id', l.id, 'line_number', l.line_number, 'item_id', l.item_id,
               'variant_id', l.variant_id,
               'quantity', CASE WHEN l.id = p_order_line_id THEN p_new_quantity ELSE l.quantity END,
               'participant_guest_session_id', l.participant_guest_session_id,
               'snapshot_line_id', l.snapshot_line_id, 'item_code', l.item_code,
               'canonical_name', l.canonical_name, 'display_name', l.display_name,
               'tax_context', l.tax_context, 'currency_code', l.currency_code,
               'unit_amount_minor', l.unit_amount_minor,
               'line_amount_minor',
                   (l.line_amount_minor / l.quantity)
                   * CASE WHEN l.id = p_order_line_id THEN p_new_quantity ELSE l.quantity END,
               'modifiers', coalesce((
                   SELECT jsonb_agg(jsonb_build_object(
                              'id', m.id, 'modifier_id', m.modifier_id,
                              'canonical_name', m.canonical_name,
                              'display_name', m.display_name,
                              'currency_code', m.currency_code,
                              'unit_amount_minor', m.unit_amount_minor)
                          ORDER BY m.modifier_id)
                   FROM ordering.order_line_modifier m WHERE m.order_line_id = l.id),
                   '[]'::jsonb))
               ORDER BY l.line_number), '[]'::jsonb)
      INTO v_lines
      FROM ordering.order_line l
     WHERE l.tenant_id = p_tenant_id AND l.order_id = p_order_id;

    IF NOT EXISTS (SELECT 1 FROM ordering.order_line
                    WHERE id = p_order_line_id AND order_id = p_order_id
                      AND tenant_id = p_tenant_id) THEN
        RAISE EXCEPTION 'ORDER_LINE_NOT_FOUND: line % is not on order %',
            p_order_line_id, p_order_id USING ERRCODE = 'HS404';
    END IF;

    -- Repriced through the SAME resolver the preview and the submission used. An
    -- amendment that priced itself would be a third opinion about what things cost.
    v_charges := ordering.resolve_charges(p_tenant_id, v_order.outlet_id, v_lines,
                                          v_order.currency_code);
    v_charges := (SELECT coalesce(jsonb_agg(c || jsonb_build_object('id', gen_random_uuid())
                                            ORDER BY n), '[]'::jsonb)
                  FROM jsonb_array_elements(v_charges) WITH ORDINALITY AS x(c, n));
    FOR v_charge IN SELECT * FROM jsonb_array_elements(v_charges) LOOP
        v_total := v_total + (v_charge ->> 'amount_minor')::bigint;
    END LOOP;

    v_actor_kind := CASE WHEN p_actor_user_id IS NOT NULL THEN 'staff' ELSE 'guest' END;

    INSERT INTO ordering.order_event
        (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind, actor_user_id,
         actor_guest_session_id, correlation_id, before, after)
    VALUES (p_tenant_id, v_order.outlet_id, p_order_id,
            ordering.next_sequence(p_tenant_id, p_order_id), 'amended', v_actor_kind,
            p_actor_user_id, p_actor_guest_session_id, v_order.correlation_id,
            v_before,
            jsonb_build_object(
                'lines', v_lines,
                'charges', v_charges,
                'total_amount_minor', v_total,
                'notes', coalesce((
                    SELECT jsonb_agg(jsonb_build_object(
                               'id', n.id, 'order_line_id', n.order_line_id,
                               'kind', n.kind, 'body', n.body,
                               'author_user_id', n.author_user_id,
                               'author_guest_session_id', n.author_guest_session_id,
                               'allergen_id', n.allergen_id,
                               'allergy_concern_id', n.allergy_concern_id,
                               'acknowledgement_wording_id', n.acknowledgement_wording_id,
                               'acknowledgement_text', n.acknowledgement_text)
                           ORDER BY n.created_at, n.id)
                    FROM ordering.order_note n
                    WHERE n.tenant_id = p_tenant_id AND n.order_id = p_order_id),
                    '[]'::jsonb)))
    RETURNING id INTO v_event;
    PERFORM ordering.apply_event(v_event);
END;
$$;

COMMENT ON FUNCTION ordering.amend_order_line(uuid, uuid, uuid, integer, uuid, uuid) IS
    'FR-ORD-010. The amendment payload carries the NOTES forward as well as the lines, '
    'because ordering.apply_event() replaces rather than patches — and an amendment that '
    'silently dropped an allergy declaration on the way through would be the exact '
    'failure NC-M3-003 exists to catch. tests/m3a amends an order carrying one and '
    'requires the declaration to still be there afterwards.';

-- FR-ORD-013, the other half. Submission carries the notes a guest writes as they
-- order; a kitchen instruction and a private staff note are written by staff AFTERWARDS,
-- and without this there was no path for them at all — which is a gap the suite found by
-- having to reach behind the projection guard to test the audience filters. A projection
-- row that is not in the ledger is destroyed by the next rebuild, and that is the system
-- working: everything a reader sees must be derived from the ledger, staff notes included.
CREATE FUNCTION ordering.add_order_note(
    p_tenant_id uuid,
    p_order_id  uuid,
    p_kind      ordering.note_kind,
    p_body      text,
    p_order_line_id uuid DEFAULT NULL,
    p_actor_user_id uuid DEFAULT NULL,
    p_actor_guest_session_id uuid DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_order ordering.customer_order%ROWTYPE;
    v_note  uuid := gen_random_uuid();
    v_event bigint;
BEGIN
    SELECT * INTO v_order FROM ordering.customer_order
     WHERE id = p_order_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ORDER_NOT_FOUND: no order % in scope', p_order_id
            USING ERRCODE = 'HS404';
    END IF;

    IF p_kind = 'allergy_declaration' THEN
        RAISE EXCEPTION
            'ALLERGY_DECLARATION_NOT_A_PLAIN_NOTE: a declaration carries the wording the '
            'guest was actually shown and is raised against the table-level concern, not '
            'posted as free text' USING ERRCODE = 'HS400';
    END IF;

    IF p_kind IN ('kitchen_instruction', 'private_staff') AND p_actor_user_id IS NULL THEN
        RAISE EXCEPTION
            'STAFF_NOTE_WITHOUT_STAFF_AUTHOR: a % note names the member of staff who '
            'wrote it', p_kind USING ERRCODE = 'HS403';
    END IF;

    IF p_body IS NULL OR btrim(p_body) = '' THEN
        RAISE EXCEPTION 'ORDER_NOTE_EMPTY: a note with no text is not a note'
            USING ERRCODE = 'HS400';
    END IF;

    INSERT INTO ordering.order_event
        (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind, actor_user_id,
         actor_guest_session_id, correlation_id, after)
    VALUES (p_tenant_id, v_order.outlet_id, p_order_id,
            ordering.next_sequence(p_tenant_id, p_order_id), 'note_added',
            (CASE WHEN p_actor_user_id IS NOT NULL THEN 'staff' ELSE 'guest' END)
                ::ordering.actor_kind,
            p_actor_user_id, p_actor_guest_session_id, v_order.correlation_id,
            jsonb_build_object('note', jsonb_build_object(
                'id', v_note,
                'order_line_id', p_order_line_id,
                'kind', p_kind,
                'body', p_body,
                'author_user_id', p_actor_user_id,
                'author_guest_session_id', p_actor_guest_session_id)))
    RETURNING id INTO v_event;

    PERFORM ordering.apply_event(v_event);
    RETURN v_note;
END;
$$;

COMMENT ON FUNCTION ordering.add_order_note(uuid, uuid, ordering.note_kind, text, uuid, uuid, uuid) IS
    'FR-ORD-013. The only way a note reaches an existing order, and it goes through the '
    'ledger like everything else — so a private staff note survives a projection rebuild '
    'and an amendment carries it forward, exactly as an allergy declaration does.';


-- FR-ORD-011. Permitted or refused by state, channel and reason. The payment dimension
-- of the policy needs payments and is M4's; recorded as a partial closure.
CREATE FUNCTION ordering.cancel_order(
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

    INSERT INTO ordering.order_event
        (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind, actor_user_id,
         actor_guest_session_id, correlation_id, reason_code_id, before, after)
    VALUES (p_tenant_id, v_order.outlet_id, p_order_id,
            ordering.next_sequence(p_tenant_id, p_order_id), 'cancelled',
            (CASE WHEN p_actor_user_id IS NOT NULL THEN 'staff' ELSE 'guest' END)
                ::ordering.actor_kind,
            p_actor_user_id, p_actor_guest_session_id, v_order.correlation_id,
            p_reason_code_id,
            jsonb_build_object('state', v_order.state),
            jsonb_build_object('state', 'cancelled'))
    RETURNING id INTO v_event;
    PERFORM ordering.apply_event(v_event);
END;
$$;

-- FR-ORD-012A. Authorized void after acceptance, for an UNPAID order, with the reason
-- and an immutable audit record. "Unpaid" is trivially true at M3-A because no payment
-- exists to make it false — so it is asserted against the registry of payment artifacts
-- rather than assumed, and re-proved at M4.
CREATE FUNCTION ordering.void_order(
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

    -- Authorization first, and through M1-B's registry rather than a check of its own.
    -- authorize_action() raises with its own named signature when the session is absent,
    -- the role does not grant it, the credential is too weak, or the step-up has expired.
    PERFORM identity.authorize_action('order.void');

    IF v_order.state <> 'accepted' THEN
        RAISE EXCEPTION
            'VOID_BEFORE_ACCEPTANCE: order % is %; an order that was never accepted is '
            'cancelled, not voided', p_order_id, v_order.state USING ERRCODE = 'HS409';
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

    -- The immutable audit the requirement asks for is M1-C's append-only store, written
    -- to rather than reimplemented.
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


-- ===========================================================================
-- Audience filtering (FR-ORD-013, FR-ORD-016A)
-- ===========================================================================
-- The application role holds NO direct SELECT on ordering.order_note. Reads go through
-- these functions, and the one a customer surface can call TAKES NO AUDIENCE ARGUMENT.
-- That is the whole design: a customer path cannot ask for a private staff note because
-- there is no parameter with which to ask, and a defect would have to add the kind to
-- this function's own list rather than merely forget a WHERE clause somewhere.

CREATE FUNCTION ordering.customer_visible_notes(p_tenant_id uuid, p_order_id uuid)
RETURNS TABLE (note_id uuid, kind ordering.note_kind, body text,
               acknowledgement_text text, created_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, ordering, public
AS $$
    SELECT n.id, n.kind, n.body, n.acknowledgement_text, n.created_at
    FROM ordering.order_note n
    WHERE n.tenant_id = p_tenant_id AND n.order_id = p_order_id
      AND n.kind IN ('customer', 'allergy_declaration')
    ORDER BY n.created_at, n.id;
$$;

COMMENT ON FUNCTION ordering.customer_visible_notes(uuid, uuid) IS
    'What a guest may read back about their own order (FR-ORD-013): their own notes and '
    'the allergy they declared. A kitchen instruction and a private staff note are not '
    'redacted here, they are absent — a redacted entry would disclose that something was '
    'written. NC-M3-007 plants private_staff into this list and requires the suite to '
    'catch it.';

CREATE FUNCTION ordering.kitchen_notes(p_tenant_id uuid, p_order_id uuid)
RETURNS TABLE (note_id uuid, kind ordering.note_kind, body text,
               allergen_id uuid, kitchen_code text, acknowledgement_text text,
               created_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, ordering, safety, public
AS $$
    -- Allergy declarations first, and by kind rather than by timestamp: the sentence
    -- that matters most is not the one that happened to be typed first.
    SELECT n.id, n.kind, n.body, n.allergen_id, a.kitchen_code, n.acknowledgement_text,
           n.created_at
    FROM ordering.order_note n
    LEFT JOIN safety.allergen a ON a.id = n.allergen_id
    WHERE n.tenant_id = p_tenant_id AND n.order_id = p_order_id
      AND n.kind IN ('allergy_declaration', 'kitchen_instruction')
    ORDER BY (n.kind = 'allergy_declaration') DESC, n.created_at, n.id;
$$;

COMMENT ON FUNCTION ordering.kitchen_notes(uuid, uuid) IS
    'What the kitchen must see before preparing (FR-ORD-013, NC-M3-003). The station '
    'surface that consumes this is M3-B; the guarantee that the declaration REACHES it '
    'is here, where the declaration lives, so the later slice inherits a proved handoff '
    'rather than an obligation.';

CREATE FUNCTION ordering.staff_notes(p_tenant_id uuid, p_order_id uuid)
RETURNS TABLE (note_id uuid, kind ordering.note_kind, body text, author_user_id uuid,
               created_at timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, ordering, public
AS $$
BEGIN
    -- A guest context carries no app.session_id — M2-B's establish_guest_context()
    -- clears it deliberately — so this is not a role check that a guest could pass by
    -- calling from the customer routes. It is the absence of a staff session.
    IF app.current_session_id() IS NULL THEN
        RAISE EXCEPTION
            'PRIVATE_NOTE_REQUIRES_STAFF_SESSION: order notes for staff are readable '
            'only under a live staff session, and none is in context'
            USING ERRCODE = 'HS403';
    END IF;
    PERFORM identity.authorize_action('order.view');

    RETURN QUERY
    SELECT n.id, n.kind, n.body, n.author_user_id, n.created_at
    FROM ordering.order_note n
    WHERE n.tenant_id = p_tenant_id AND n.order_id = p_order_id
    ORDER BY n.created_at, n.id;
END;
$$;

CREATE FUNCTION ordering.customer_timeline(p_tenant_id uuid, p_order_id uuid)
RETURNS TABLE (occurred_at timestamptz, kind ordering.event_kind, summary text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, ordering, public
AS $$
    SELECT t.occurred_at, t.kind, t.customer_summary
    FROM ordering.order_timeline_entry t
    WHERE t.tenant_id = p_tenant_id AND t.order_id = p_order_id
      AND t.visible_to_customer
    ORDER BY t.occurred_at, t.sequence_number;
$$;

CREATE FUNCTION ordering.staff_timeline(p_tenant_id uuid, p_order_id uuid)
RETURNS TABLE (occurred_at timestamptz, kind ordering.event_kind, summary text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, ordering, public
AS $$
BEGIN
    IF app.current_session_id() IS NULL THEN
        RAISE EXCEPTION
            'STAFF_TIMELINE_REQUIRES_STAFF_SESSION: no live staff session in context'
            USING ERRCODE = 'HS403';
    END IF;
    PERFORM identity.authorize_action('order.view');

    RETURN QUERY
    SELECT t.occurred_at, t.kind, t.staff_summary
    FROM ordering.order_timeline_entry t
    WHERE t.tenant_id = p_tenant_id AND t.order_id = p_order_id
    ORDER BY t.occurred_at, t.sequence_number;
END;
$$;


-- ===========================================================================
-- Correlation chain (FR-ORD-019A)
-- ===========================================================================

CREATE FUNCTION ordering.correlation_chain(p_tenant_id uuid, p_correlation_id uuid)
RETURNS TABLE (artifact_kind ordering.artifact_kind, artifact_id uuid, linked_at timestamptz)
LANGUAGE sql STABLE
AS $$
    SELECT k.artifact_kind, k.artifact_id, k.linked_at
    FROM ordering.correlation_link k
    WHERE k.tenant_id = p_tenant_id AND k.correlation_id = p_correlation_id
    ORDER BY k.artifact_kind, k.artifact_id;
$$;

COMMENT ON FUNCTION ordering.correlation_chain(uuid, uuid) IS
    'FR-ORD-019A. Four of the six artifacts the requirement names — request, cart, table '
    'session and order — are linked at this gate. Fulfillment ticket and service request '
    'are labels of ordering.artifact_kind with no rows until M3-B and M3-C, and that is '
    'recorded as a partial closure rather than presented as complete.';


-- ===========================================================================
-- Session lifecycle (FR-TAB-007A, FR-TAB-008, FR-TAB-009)
-- ===========================================================================

-- FR-TAB-007A. Two tables become one service session. Every order on the absorbed
-- session gets an EVENT saying where it went, so "correctly consolidated and audited" is
-- one act rather than an update and a separate log that could disagree.
CREATE FUNCTION service.merge_table_sessions(
    p_tenant_id uuid,
    p_surviving_session_id uuid,
    p_absorbed_session_id  uuid,
    p_user_id   uuid,
    p_reason_code_id uuid DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_survivor service.table_session%ROWTYPE;
    v_absorbed service.table_session%ROWTYPE;
    v_order    ordering.customer_order%ROWTYPE;
    v_event    bigint;
    v_moved    integer := 0;
    v_merge_id uuid;
BEGIN
    SELECT * INTO v_survivor FROM service.table_session
     WHERE id = p_surviving_session_id AND tenant_id = p_tenant_id;
    IF NOT FOUND OR v_survivor.state <> 'open' THEN
        RAISE EXCEPTION
            'MERGE_TARGET_NOT_OPEN: the surviving session % is not an open occupancy',
            p_surviving_session_id USING ERRCODE = 'HS409';
    END IF;

    SELECT * INTO v_absorbed FROM service.table_session
     WHERE id = p_absorbed_session_id AND tenant_id = p_tenant_id;
    IF NOT FOUND OR v_absorbed.state <> 'open' THEN
        RAISE EXCEPTION
            'MERGE_SOURCE_NOT_OPEN: the absorbed session % is not an open occupancy',
            p_absorbed_session_id USING ERRCODE = 'HS409';
    END IF;

    IF v_survivor.outlet_id <> v_absorbed.outlet_id THEN
        RAISE EXCEPTION
            'MERGE_ACROSS_OUTLETS: sessions in different outlets do not merge'
            USING ERRCODE = 'HS409';
    END IF;

    -- Every order, one event each. A bulk UPDATE would move the rows and leave no
    -- account of what moved, which is exactly how an order goes missing at a merge.
    FOR v_order IN
        SELECT * FROM ordering.customer_order
         WHERE tenant_id = p_tenant_id AND table_session_id = p_absorbed_session_id
         ORDER BY submitted_at, id
    LOOP
        INSERT INTO ordering.order_event
            (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind,
             actor_user_id, correlation_id, before, after)
        VALUES (p_tenant_id, v_order.outlet_id, v_order.id,
                ordering.next_sequence(p_tenant_id, v_order.id), 'session_merged', 'staff',
                p_user_id, v_order.correlation_id,
                jsonb_build_object('table_session_id', p_absorbed_session_id),
                jsonb_build_object('table_session_id', p_surviving_session_id))
        RETURNING id INTO v_event;
        PERFORM ordering.apply_event(v_event);
        v_moved := v_moved + 1;
    END LOOP;

    -- Participants and open carts follow the orders. A guest whose basket stayed behind
    -- on a closed occupancy would be holding a cart that can never be submitted.
    UPDATE service.session_participant
       SET table_session_id = p_surviving_session_id
     WHERE tenant_id = p_tenant_id AND table_session_id = p_absorbed_session_id
       AND NOT EXISTS (
            SELECT 1 FROM service.session_participant s
            WHERE s.table_session_id = p_surviving_session_id
              AND s.guest_session_id = service.session_participant.guest_session_id);

    UPDATE service.cart SET table_session_id = p_surviving_session_id
     WHERE tenant_id = p_tenant_id AND table_session_id = p_absorbed_session_id;

    UPDATE safety.allergy_concern SET table_session_id = p_surviving_session_id
     WHERE tenant_id = p_tenant_id AND table_session_id = p_absorbed_session_id;

    UPDATE service.table_session
       SET state = 'closed', closed_at = now()
     WHERE id = p_absorbed_session_id AND tenant_id = p_tenant_id;

    INSERT INTO service.session_merge
        (tenant_id, outlet_id, surviving_session_id, absorbed_session_id,
         merged_by_user_id, reason_code_id, orders_moved)
    VALUES (p_tenant_id, v_survivor.outlet_id, p_surviving_session_id,
            p_absorbed_session_id, p_user_id, p_reason_code_id, v_moved)
    RETURNING id INTO v_merge_id;

    RETURN v_merge_id;
END;
$$;

-- FR-TAB-008. The session keeps its identity and changes table. Orders name the SESSION,
-- so nothing is re-parented — see the note at the head of the session-lifecycle section
-- on why no order carries a table_node_id.
CREATE FUNCTION service.move_table_session(
    p_tenant_id uuid,
    p_session_id uuid,
    p_to_table_node_id uuid,
    p_user_id uuid
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_session service.table_session%ROWTYPE;
    v_next    integer;
    v_orders  integer;
    v_order   ordering.customer_order%ROWTYPE;
    v_event   bigint;
    v_move_id uuid;
BEGIN
    SELECT * INTO v_session FROM service.table_session
     WHERE id = p_session_id AND tenant_id = p_tenant_id;
    IF NOT FOUND OR v_session.state <> 'open' THEN
        RAISE EXCEPTION 'MOVE_SOURCE_NOT_OPEN: session % is not an open occupancy',
            p_session_id USING ERRCODE = 'HS409';
    END IF;

    IF v_session.table_node_id = p_to_table_node_id THEN
        RAISE EXCEPTION 'MOVE_TO_SAME_TABLE: session % is already at table %',
            p_session_id, p_to_table_node_id USING ERRCODE = 'HS409';
    END IF;

    IF EXISTS (SELECT 1 FROM service.table_session
                WHERE tenant_id = p_tenant_id AND table_node_id = p_to_table_node_id
                  AND state = 'open') THEN
        RAISE EXCEPTION
            'MOVE_TARGET_OCCUPIED: table % already has an open occupancy',
            p_to_table_node_id USING ERRCODE = 'HS409';
    END IF;

    -- Occupancy numbers are per table and monotonic. Moving means taking the next number
    -- at the destination rather than carrying one that belongs to another table's
    -- sequence — M2-B's stale-QR guarantee reads that number and must keep reading it.
    SELECT coalesce(max(occupancy_number), 0) + 1 INTO v_next
    FROM service.table_session
    WHERE tenant_id = p_tenant_id AND table_node_id = p_to_table_node_id;

    SELECT count(*) INTO v_orders FROM ordering.customer_order
     WHERE tenant_id = p_tenant_id AND table_session_id = p_session_id;

    UPDATE service.table_session
       SET table_node_id = p_to_table_node_id, occupancy_number = v_next
     WHERE id = p_session_id AND tenant_id = p_tenant_id;

    FOR v_order IN
        SELECT * FROM ordering.customer_order
         WHERE tenant_id = p_tenant_id AND table_session_id = p_session_id
         ORDER BY submitted_at, id
    LOOP
        INSERT INTO ordering.order_event
            (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind,
             actor_user_id, correlation_id, before, after)
        VALUES (p_tenant_id, v_order.outlet_id, v_order.id,
                ordering.next_sequence(p_tenant_id, v_order.id), 'session_moved', 'staff',
                p_user_id, v_order.correlation_id,
                jsonb_build_object('table_node_id', v_session.table_node_id,
                                   'occupancy_number', v_session.occupancy_number),
                jsonb_build_object('table_node_id', p_to_table_node_id,
                                   'occupancy_number', v_next))
        RETURNING id INTO v_event;
        PERFORM ordering.apply_event(v_event);
    END LOOP;

    INSERT INTO service.session_move
        (tenant_id, outlet_id, table_session_id, from_table_node_id, to_table_node_id,
         from_occupancy_number, to_occupancy_number, moved_by_user_id, orders_carried)
    VALUES (p_tenant_id, v_session.outlet_id, p_session_id, v_session.table_node_id,
            p_to_table_node_id, v_session.occupancy_number, v_next, p_user_id, v_orders)
    RETURNING id INTO v_move_id;

    RETURN v_move_id;
END;
$$;

-- FR-TAB-009. Closure needs the service obligations discharged, or somebody with the
-- authority to say otherwise on the record. The FINANCIAL condition cannot be proved
-- before checks exist and is M4's; recorded as a partial closure.
CREATE FUNCTION service.close_table_session(
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

    -- An outstanding obligation at M3-A is an order that has neither been resolved nor
    -- accepted-and-served. Service completion is a fulfillment state and belongs to
    -- M3-B, so what is checkable here is the commercial state.
    SELECT count(*) INTO v_outstanding FROM ordering.customer_order
     WHERE tenant_id = p_tenant_id AND table_session_id = p_session_id
       AND state = 'submitted';

    IF v_outstanding > 0 THEN
        IF p_exception_reason_code_id IS NULL THEN
            RAISE EXCEPTION
                'SESSION_HAS_OUTSTANDING_ORDERS: occupancy % has % order(s) awaiting '
                'acceptance; closing needs an authorized exception on the record',
                p_session_id, v_outstanding USING ERRCODE = 'HS409';
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
             authorized_by_user_id, outstanding_orders, note)
        VALUES (p_tenant_id, v_session.outlet_id, p_session_id,
                p_exception_reason_code_id, p_user_id, v_outstanding, p_exception_note);
    END IF;

    UPDATE service.table_session
       SET state = 'closed', closed_at = now()
     WHERE id = p_session_id AND tenant_id = p_tenant_id;
END;
$$;


-- ===========================================================================
-- Governed actions this gate exercises (FR-AUTH-006, FR-ORD-012A, FR-TAB-009)
-- ===========================================================================
-- M1-B registered the actions M1 and M4 need. Two more are exercised from here, and they
-- are added in BOTH places they have to be: the installer, so a tenant created from now
-- on gets them, and the tenants that already exist, so the ones created before this
-- migration are not left without. Doing only the first is how a check comes to pass on a
-- fresh database and fail on a real one.

CREATE OR REPLACE FUNCTION identity.install_governed_actions() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO identity.governed_action
        (tenant_id, action_code, minimum_strength, step_up_required, step_up_max_age, governed_from_gate)
    VALUES
        -- Governed from M1: role changes and configuration changes.
        (NEW.id, 'membership.assign',      'strong', true,  interval '5 minutes',  'M1'),
        (NEW.id, 'membership.withdraw',    'strong', true,  interval '5 minutes',  'M1'),
        (NEW.id, 'role.modify',            'strong', true,  interval '5 minutes',  'M1'),
        (NEW.id, 'configuration.modify',   'strong', true,  interval '5 minutes',  'M1'),
        (NEW.id, 'credential.reset',       'strong', true,  interval '5 minutes',  'M1'),
        -- Governed from M3: an operational void, and closing a session over an
        -- outstanding obligation. Both are somebody overriding what the system would
        -- otherwise refuse, which is exactly what a governed action is for.
        (NEW.id, 'order.void',             'strong', true,  interval '5 minutes',  'M3'),
        (NEW.id, 'session.close_with_exception',
                                           'strong', true,  interval '5 minutes',  'M3'),
        -- Registered now, exercised from M4. No caller exists at M1.
        (NEW.id, 'payment.refund',         'strong', true,  interval '5 minutes',  'M4'),
        (NEW.id, 'check.void',             'strong', true,  interval '5 minutes',  'M4'),
        (NEW.id, 'discount.high',          'strong', true,  interval '5 minutes',  'M4'),
        (NEW.id, 'payout.release',         'strong', true,  interval '5 minutes',  'M4'),
        -- Registered now, exercised from M6.
        (NEW.id, 'report.export',          'strong', true,  interval '15 minutes', 'M6'),
        -- Routine actions: no step-up, but a quick PIN is still enough only here.
        (NEW.id, 'order.view',             'low',    false, NULL,                  'M1'),
        (NEW.id, 'session.resume',         'low',    false, NULL,                  'M1');
    RETURN NULL;
END;
$$;

INSERT INTO identity.governed_action
    (tenant_id, action_code, minimum_strength, step_up_required, step_up_max_age,
     governed_from_gate)
SELECT t.id, a.code, 'strong', true, interval '5 minutes', 'M3'
FROM org.tenant t
CROSS JOIN (VALUES ('order.void'), ('session.close_with_exception')) AS a(code)
WHERE NOT EXISTS (
    SELECT 1 FROM identity.governed_action g
    WHERE g.tenant_id = t.id AND g.action_code = a.code);


-- ===========================================================================
-- Number series for order numbers (FR-DAT-003)
-- ===========================================================================
-- One series per outlet per year. Created for the outlets that exist and by trigger for
-- the ones that arrive later, so an outlet cannot take its first order and discover it
-- has no way to number it.

CREATE FUNCTION config.install_order_number_series() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.kind = 'outlet' THEN
        INSERT INTO config.number_series
            (tenant_id, outlet_id, document_type, fiscal_period, prefix, next_value)
        VALUES (NEW.tenant_id, NEW.id, 'dine_in_order', to_char(now(), 'YYYY'), 'ORD-', 1)
        ON CONFLICT DO NOTHING;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER outlet_install_order_number_series
    AFTER INSERT ON org.org_node
    FOR EACH ROW EXECUTE FUNCTION config.install_order_number_series();

INSERT INTO config.number_series
    (tenant_id, outlet_id, document_type, fiscal_period, prefix, next_value)
SELECT n.tenant_id, n.id, 'dine_in_order', to_char(now(), 'YYYY'), 'ORD-', 1
FROM org.org_node n
WHERE n.kind = 'outlet'
  AND NOT EXISTS (
      SELECT 1 FROM config.number_series s
      WHERE s.tenant_id = n.tenant_id AND s.outlet_id = n.id
        AND s.document_type = 'dine_in_order'
        AND s.fiscal_period = to_char(now(), 'YYYY'));


-- ===========================================================================
-- Row level security, on the same predicate as everything else
-- ===========================================================================
-- ENABLE and FORCE on every table, and the single app.row_in_scope() predicate. No table
-- in this schema gets a policy of its own devising: M1-A's NC-M1-003 gates that in CI,
-- and it gates this schema too.

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'ordering.order_event', 'ordering.customer_order', 'ordering.order_line',
        'ordering.order_line_modifier', 'ordering.charge_rule',
        'ordering.order_charge_component', 'ordering.order_note',
        'ordering.order_timeline_entry', 'ordering.correlation_link',
        'ordering.duplicate_signal', 'service.session_merge', 'service.session_move',
        'service.session_closure_exception']
    LOOP
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %s FORCE  ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY %I ON %s FOR ALL '
            'USING (app.row_in_scope(tenant_id, outlet_id)) '
            'WITH CHECK (app.row_in_scope(tenant_id, outlet_id))',
            replace(split_part(t, '.', 2), '.', '_') || '_isolation', t);
    END LOOP;
END;
$$;


-- ===========================================================================
-- Grants
-- ===========================================================================

GRANT USAGE ON SCHEMA ordering TO hospitality_app;

-- The ledger: append and read. Never UPDATE, never DELETE. The trigger refuses those
-- too, and the two locks are deliberately independent.
GRANT SELECT, INSERT ON ordering.order_event TO hospitality_app;

-- The projections: READ ONLY. Every write goes through ordering.apply_event(), which
-- runs as the caller and is admitted by the projection guard rather than by a privilege.
-- Granting the application role INSERT here would not make a direct write succeed — the
-- trigger would still refuse it — but it would make the intention ambiguous, and an
-- ambiguous grant is the kind of thing a later migration widens by accident.
GRANT SELECT ON ordering.customer_order          TO hospitality_app;
GRANT SELECT ON ordering.order_line              TO hospitality_app;
GRANT SELECT ON ordering.order_line_modifier     TO hospitality_app;
GRANT SELECT ON ordering.order_charge_component  TO hospitality_app;
GRANT SELECT ON ordering.order_timeline_entry    TO hospitality_app;
GRANT SELECT ON ordering.correlation_link        TO hospitality_app;
GRANT SELECT ON ordering.duplicate_signal        TO hospitality_app;

-- ordering.order_note carries the private staff notes. The application role gets NO
-- direct SELECT at all: reads go through the three audience functions, which is what
-- makes "a customer surface cannot ask for a private note" a fact about the privileges
-- rather than a discipline in the routes.
REVOKE ALL ON ordering.order_note FROM hospitality_app;

-- Rules are configuration, read by the pricing path and written by the configuration
-- path, which is not built at this gate.
GRANT SELECT ON ordering.charge_rule TO hospitality_app;

GRANT SELECT, INSERT ON service.session_merge              TO hospitality_app;
GRANT SELECT, INSERT ON service.session_move               TO hospitality_app;
GRANT SELECT, INSERT ON service.session_closure_exception  TO hospitality_app;

-- The SECURITY DEFINER readers run as the owner, so the application role needs EXECUTE
-- and nothing more. Everything else is invoker-rights and inherits the caller's scope.
GRANT EXECUTE ON FUNCTION ordering.customer_visible_notes(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION ordering.kitchen_notes(uuid, uuid)          TO hospitality_app;
GRANT EXECUTE ON FUNCTION ordering.staff_notes(uuid, uuid)            TO hospitality_app;
GRANT EXECUTE ON FUNCTION ordering.customer_timeline(uuid, uuid)      TO hospitality_app;
GRANT EXECUTE ON FUNCTION ordering.staff_timeline(uuid, uuid)         TO hospitality_app;

-- ordering.apply_event() is SECURITY DEFINER, and that is what makes the two locks on
-- the projections genuinely independent rather than one lock described twice:
--
--   the GRANT stops the application role writing a projection at all, and it is not a
--   grant that a defect could route around, because the role simply does not hold it;
--   the TRIGGER stops anyone — the table owner included, under FORCE ROW LEVEL
--   SECURITY — writing one outside this function.
--
-- Removing either leaves the other standing. If apply_event() ran with the caller's own
-- privileges instead, the application role would need INSERT and UPDATE on every
-- projection to use it, and the grant would stop being a lock at all.
--
-- It is not an escalation. Row level security is FORCED on every projection and the
-- isolation predicate reads session GUCs, not the current role, so a definer call sees
-- exactly the tenant and outlet the caller's context names. What the function can do
-- that its caller cannot is write a projection — and the only thing it will write is
-- what the ledger event already says.
GRANT EXECUTE ON FUNCTION ordering.apply_event(bigint)                TO hospitality_app;
GRANT EXECUTE ON FUNCTION ordering.rebuild_projections(uuid)          TO hospitality_app;

-- Returns a hash and nothing else, so it discloses no note it reads.
GRANT EXECUTE ON FUNCTION ordering.projection_digest(uuid)            TO hospitality_app;
GRANT EXECUTE ON FUNCTION ordering.amend_order_line(uuid, uuid, uuid, integer, uuid, uuid)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION ordering.add_order_note(
    uuid, uuid, ordering.note_kind, text, uuid, uuid, uuid) TO hospitality_app;

-- The fold's helpers are NOT granted. They take an order_event row directly, so a caller
-- holding EXECUTE could write a projection row for an event that was never in the
-- ledger. apply_event() reads the event from the ledger itself and is the only door.
REVOKE ALL ON FUNCTION ordering.write_charge_components(ordering.order_event, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION ordering.write_notes(ordering.order_event, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION ordering.write_timeline_entry(ordering.order_event) FROM PUBLIC;
