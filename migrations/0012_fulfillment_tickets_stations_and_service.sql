-- ===========================================================================
-- 0012 — Fulfillment: routing, tickets, stations, the state machine, service
-- ===========================================================================
-- Gate M3, slice B. Requirements: FR-FUL-001 … FR-FUL-016A, FR-SAF-004, and the five
-- M3-A partial closures that come due with it: FR-ORD-006, FR-ORD-009, FR-ORD-010,
-- FR-ORD-016A, FR-ORD-019A.
--
-- ---------------------------------------------------------------------------
-- The decision this file rests on
-- ---------------------------------------------------------------------------
--
--   THE ORDER IS WHAT THE CUSTOMER AGREED. THE TICKET IS WHAT A STATION MUST DO.
--
-- FR-FUL-002 asks for tickets separate from the commercial order, and M3-A already made
-- that separation structural: ordering.order_state carries five COMMERCIAL states and
-- migration 0010 records that no label of the fulfillment machine appears on it. This
-- slice keeps that promise. An order does not gain a fulfillment column here — its
-- fulfillment status is DERIVED from its tickets by fulfillment.order_fulfillment_state(),
-- so "is this order ready" has exactly one answer and a ticket transition cannot leave
-- the order stale.
--
-- That is a literal divergence from the pinned SM-ORDER, which lists in_fulfillment,
-- partially_ready, ready, partially_served and served as ORDER states. It preserves that
-- machine's SEMANTICS — every one of those labels is computable, and tests/m3b proves
-- each is reachable and correct — while refusing to store the same fact twice. It is
-- recorded in planning/partial_closures.json as a decision rather than an omission.
--
-- ---------------------------------------------------------------------------
-- The state machine comes from the package, not from this file
-- ---------------------------------------------------------------------------
-- SM-FULFILLMENT-TICKET in 02_MACHINE_READABLE/state_machines.json is authoritative:
-- ELEVEN states and eleven transition lines. Two of those lines use an "a/b -> c"
-- shorthand, so they expand to THIRTEEN edges — worth stating plainly, because counting
-- the lines gives eleven and counting the machine gives thirteen.
--
-- The M3-B brief said seven states. It was reading FR-FUL-003, which lists what the KDS
-- QUEUE DISPLAYS — new, acknowledged, preparing, held, ready, completed, exception — and
-- "new" is the package's "queued". Seven display buckets over eleven states, with
-- partially_completed, collected, rework and cancelled not shown as their own column.
-- Where a brief and the pinned package disagree, the package is authoritative and the
-- brief is the defect.
--
-- fulfillment.transition below therefore has to equal the package exactly, and
-- tests/m3b derives the expected set from state_machines.json and requires equality —
-- including the COUNT, so a twelfth state added to the package without extending this
-- machine fails the build rather than passing on eleven. The suite fails closed if the
-- package cannot be read, exactly as the fenced vocabulary loader does.
--
-- The package's fourth invariant says state transitions are enforced server or database
-- side. They are enforced HERE, by a trigger on the projection that fires for the fold
-- itself — not only in the function that writes events. Same reasoning that put
-- append-only on a trigger rather than a grant at M1-C.
--
-- ---------------------------------------------------------------------------
-- What is deliberately absent
-- ---------------------------------------------------------------------------
-- No service request and no notification transport (M3-C): FR-FUL-010 emits a ready
-- notice as a record and builds no channel. No waiter surface or golden journey (M3-D).
-- No check, payment, tip or receipt (M4). No resilient local print queue, outlet node or
-- sync (M5a): FR-FUL-014 generates a deduplicated station ticket DOCUMENT, and the path
-- that delivers it to paper is M5a's.
--
-- There is no quantity-on-hand anywhere in this file. FR-FUL-016A is SERVICE waste — a
-- dropped plate — and nothing here decrements anything, because there is nothing to
-- decrement.
-- ===========================================================================

CREATE SCHEMA fulfillment;

COMMENT ON SCHEMA fulfillment IS
    'What a station must do, and what it did (FR-FUL-001 … FR-FUL-016A). Separate from '
    'ordering by design: the order is what the customer agreed, the ticket is the work.';


-- ===========================================================================
-- Types
-- ===========================================================================

-- The eleven states of SM-FULFILLMENT-TICKET, in the package's own order.
CREATE TYPE fulfillment.ticket_state AS ENUM (
    'queued', 'acknowledged', 'held', 'preparing', 'partially_completed', 'ready',
    'collected', 'completed', 'rework', 'cancelled', 'exception');

COMMENT ON TYPE fulfillment.ticket_state IS
    'SM-FULFILLMENT-TICKET, verbatim. tests/m3b reads the package and requires this type '
    'to hold exactly these labels and no others, so the schema cannot drift from the '
    'artifact that defines it.';

-- FR-FUL-001 names six destinations and then "or configured stations", so the kind is a
-- classification and the STATION is an org node of kind 'preparation_station' — the node
-- kind M1-A created and M2-B left unused. Tables hang off org nodes the same way.
CREATE TYPE fulfillment.station_kind AS ENUM
    ('kitchen', 'bar', 'coffee', 'bakery', 'dessert', 'expo');

-- FR-FUL-007. Three levels, and 'service_access' is the accessibility/service one: a
-- guest who needs their food promptly for a reason that is nobody else's business.
CREATE TYPE fulfillment.priority_level AS ENUM ('ordinary', 'rush', 'service_access');

CREATE TYPE fulfillment.ticket_event_kind AS ENUM (
    'released', 'transitioned', 'reprioritised', 'transferred', 'recalled',
    'unit_progress', 'acknowledged_allergy', 'document_generated', 'served', 'waste',
    -- FR-ORD-010's other side. An amendment a station has not started is PERMITTED, and
    -- a permitted amendment that left the ticket saying the old quantity would have the
    -- kitchen make what the guest no longer ordered — a quieter defect than refusing it.
    'amended');

-- FR-FUL-011. What went wrong at the handoff, when something did.
CREATE TYPE fulfillment.serve_exception AS ENUM ('missing_item', 'wrong_item');

-- FR-FUL-016A. Named for what they are: not one of these is a stock movement, and
-- Phase 1 has nothing anywhere that one could move.
CREATE TYPE fulfillment.waste_kind AS ENUM ('rework', 'remake', 'service_waste');

-- FR-FUL-014. Why a paper document was generated at all.
CREATE TYPE fulfillment.document_trigger AS ENUM ('kds_unavailable', 'policy_requires_paper');


-- ===========================================================================
-- The legal transitions (SM-FULFILLMENT-TICKET)
-- ===========================================================================
-- Every edge the package permits, and nothing else. The rows below are the package's
-- eleven transition lines with the "a/b -> c" shorthand expanded — which is why there are
-- thirteen of them.
--
-- This table is not a second opinion about the machine. It is the machine, in the only
-- form a trigger can consult, and tests/m3b requires it to equal state_machines.json
-- exactly in both directions: every package edge present here, every row here present in
-- the package, and the counts equal.

CREATE TABLE fulfillment.transition (
    from_state fulfillment.ticket_state NOT NULL,
    to_state   fulfillment.ticket_state NOT NULL,
    reason     text NOT NULL,

    PRIMARY KEY (from_state, to_state),
    CONSTRAINT transition_is_a_move CHECK (from_state <> to_state),
    CONSTRAINT transition_reason_not_blank CHECK (btrim(reason) <> '')
);

INSERT INTO fulfillment.transition (from_state, to_state, reason) VALUES
    ('queued',              'acknowledged',        'station accepts'),
    ('acknowledged',        'held',                'course/capacity hold'),
    ('held',                'preparing',           'fire/start'),
    ('acknowledged',        'preparing',           'fire/start'),
    ('preparing',           'partially_completed', 'some units ready'),
    ('preparing',           'ready',               'all units ready'),
    ('partially_completed', 'ready',               'all units ready'),
    ('ready',               'collected',           'waiter/runner collects'),
    ('collected',           'completed',           'served/handoff confirmed'),
    ('ready',               'rework',              'quality issue'),
    ('rework',              'preparing',           'remake'),
    ('queued',              'cancelled',           'upstream cancellation'),
    ('preparing',           'exception',           'unavailable/equipment/safety issue');

COMMENT ON TABLE fulfillment.transition IS
    'The thirteen edges of SM-FULFILLMENT-TICKET. Consulted by a trigger on every state '
    'change, so an illegal transition is refused by the database and not merely by the '
    'function that meant to write it (the package''s fourth invariant). Read-only to the '
    'application role: a machine an application can rewrite is not a machine.';

-- Immutable in service. The transition table is schema, not data: it changes when the
-- package changes, which is a migration, not an application write.
CREATE FUNCTION fulfillment.refuse_machine_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'STATE_MACHINE_ALTERED_AT_RUNTIME: % on % is refused; the ticket state machine '
        'comes from the pinned package and changes by migration, never by a write',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'HS403';
END;
$$;

CREATE TRIGGER transition_immutable
    AFTER INSERT OR UPDATE OR DELETE ON fulfillment.transition
    FOR EACH ROW EXECUTE FUNCTION fulfillment.refuse_machine_mutation();

CREATE TRIGGER transition_no_truncate
    BEFORE TRUNCATE ON fulfillment.transition
    FOR EACH STATEMENT EXECUTE FUNCTION fulfillment.refuse_machine_mutation();


-- ===========================================================================
-- Stations (FR-FUL-001)
-- ===========================================================================
-- A station is an org node of kind 'preparation_station' — the kind M1-A declared and
-- nothing had used until now — with a profile beside it, exactly as M2-B gave a dining
-- table a service.table_profile. The hierarchy stays in one place.

CREATE TABLE fulfillment.station_profile (
    station_node_id uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    station_kind    fulfillment.station_kind NOT NULL,

    -- FR-FUL-003 needs an SLA to measure elapsed time against; FR-FUL-013 needs a
    -- threshold to throttle at. Both are stated per station, never defaulted: a station
    -- with no target has no target, and the functions below refuse rather than assume.
    sla_minutes     integer,
    concurrent_ticket_threshold integer,

    -- FR-FUL-008. Where a station must acknowledge an allergy declaration before it may
    -- begin preparing. "Where configured" is the requirement's own wording.
    allergy_acknowledgement_required boolean NOT NULL DEFAULT true,

    status          org.lifecycle_status NOT NULL DEFAULT 'active',
    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT station_profile_tenant_id_unique UNIQUE (tenant_id, station_node_id),
    CONSTRAINT station_profile_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT station_profile_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT station_profile_node_fk FOREIGN KEY (tenant_id, station_node_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT station_profile_sla_sane CHECK (
        sla_minutes IS NULL OR (sla_minutes > 0 AND sla_minutes <= 600)),
    CONSTRAINT station_profile_threshold_positive CHECK (
        concurrent_ticket_threshold IS NULL OR concurrent_ticket_threshold > 0),
    -- One profile per station per outlet, and the station must be in that outlet.
    CONSTRAINT station_profile_one_per_outlet UNIQUE (tenant_id, outlet_id, station_node_id)
);

-- The node must actually BE a preparation station. A profile hung off a dining table
-- would route food to the furniture.
CREATE FUNCTION fulfillment.assert_node_is_a_station() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_kind org.node_kind;
BEGIN
    SELECT kind INTO v_kind FROM org.org_node
     WHERE id = NEW.station_node_id AND tenant_id = NEW.tenant_id;
    IF v_kind IS DISTINCT FROM 'preparation_station' THEN
        RAISE EXCEPTION
            'STATION_NODE_WRONG_KIND: node % is %, not a preparation_station',
            NEW.station_node_id, coalesce(v_kind::text, 'absent')
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER station_profile_node_kind
    BEFORE INSERT OR UPDATE ON fulfillment.station_profile
    FOR EACH ROW EXECUTE FUNCTION fulfillment.assert_node_is_a_station();


-- ---------------------------------------------------------------------------
-- Routing rules, versioned (FR-FUL-001)
-- ---------------------------------------------------------------------------
-- "Using versioned rules" is the part that matters. A rule set that changed in place
-- would make "why did that go to the bar" unanswerable a week later, and the ticket
-- records which rule VERSION routed it — so the answer survives the next rule change.

CREATE TABLE fulfillment.routing_rule_set (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    version        integer NOT NULL,
    effective_from timestamptz NOT NULL DEFAULT now(),
    effective_to   timestamptz,
    approved_by_user_id uuid NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT routing_rule_set_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT routing_rule_set_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT routing_rule_set_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT routing_rule_set_approver_fk FOREIGN KEY (tenant_id, approved_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT routing_rule_set_version_positive CHECK (version > 0),
    CONSTRAINT routing_rule_set_version_unique UNIQUE (tenant_id, outlet_id, version),
    CONSTRAINT routing_rule_set_window_valid CHECK (
        effective_to IS NULL OR effective_to > effective_from)
);

-- At most one open version per outlet. A second would make "the rules" a question with
-- two answers, which is the same defect menu.price has an index against.
CREATE UNIQUE INDEX routing_rule_set_single_open
    ON fulfillment.routing_rule_set (tenant_id, outlet_id)
    WHERE effective_to IS NULL;

CREATE TABLE fulfillment.routing_rule (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    rule_set_id     uuid NOT NULL,

    -- Most specific wins, and precedence is stated rather than inferred from row order:
    -- a rule set whose behaviour depended on insertion order would reroute a kitchen by
    -- being reseeded.
    precedence      integer NOT NULL,

    -- Exactly one subject, like menu.price. NULL on all three is the catch-all, which is
    -- what makes a rule set total — see fulfillment.route_line() below, which refuses to
    -- release a ticket for a line no rule matches rather than silently dropping it.
    item_id         uuid,
    variant_id      uuid,
    category_id     uuid,

    target_station_node_id uuid NOT NULL,

    CONSTRAINT routing_rule_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT routing_rule_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT routing_rule_set_fk FOREIGN KEY (tenant_id, rule_set_id)
        REFERENCES fulfillment.routing_rule_set (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT routing_rule_item_fk FOREIGN KEY (item_id)
        REFERENCES menu.sellable_item (id) ON DELETE RESTRICT,
    CONSTRAINT routing_rule_variant_fk FOREIGN KEY (variant_id)
        REFERENCES menu.item_variant (id) ON DELETE RESTRICT,
    CONSTRAINT routing_rule_category_fk FOREIGN KEY (category_id)
        REFERENCES menu.category (id) ON DELETE RESTRICT,
    CONSTRAINT routing_rule_station_fk FOREIGN KEY (tenant_id, target_station_node_id)
        REFERENCES fulfillment.station_profile (tenant_id, station_node_id) ON DELETE RESTRICT,
    CONSTRAINT routing_rule_at_most_one_subject CHECK (
        (item_id IS NOT NULL)::int + (variant_id IS NOT NULL)::int
      + (category_id IS NOT NULL)::int <= 1),
    CONSTRAINT routing_rule_precedence_positive CHECK (precedence > 0),
    CONSTRAINT routing_rule_precedence_unique UNIQUE (rule_set_id, precedence)
);

CREATE INDEX routing_rule_set_idx ON fulfillment.routing_rule (rule_set_id, precedence);

COMMENT ON TABLE fulfillment.routing_rule IS
    'Where a line unit goes (FR-FUL-001). Rules belong to a VERSIONED set and a ticket '
    'records the version that routed it, so a rule change does not rewrite history. '
    'Precedence is explicit: a rule set whose meaning depended on row order would change '
    'behaviour when it was reseeded.';


-- ===========================================================================
-- The ticket ledger (FR-FUL-002, FR-DAT-008A carried forward)
-- ===========================================================================
-- Same arrangement M3-A built for orders, for the same reason: the ledger is the record
-- and everything a station reads is a projection of it. Append-only twice over — the
-- application role holds INSERT and SELECT, and a trigger refuses UPDATE, DELETE and
-- TRUNCATE whoever asks.

CREATE TABLE fulfillment.ticket_event (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    ticket_id       uuid NOT NULL,
    sequence_number integer NOT NULL,

    kind            fulfillment.ticket_event_kind NOT NULL,
    occurred_at     timestamptz NOT NULL DEFAULT now(),

    actor_kind      ordering.actor_kind NOT NULL,
    actor_user_id   uuid,

    correlation_id  uuid NOT NULL,
    reason_code_id  uuid,

    before          jsonb,
    after           jsonb NOT NULL,

    CONSTRAINT ticket_event_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT ticket_event_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ticket_event_actor_fk FOREIGN KEY (tenant_id, actor_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ticket_event_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ticket_event_sequence_positive CHECK (sequence_number > 0),
    CONSTRAINT ticket_event_sequence_unique UNIQUE (tenant_id, ticket_id, sequence_number),
    -- A station acts as a member of staff, or the system releases work. A guest never
    -- touches a ticket, and there is no column here through which one could.
    CONSTRAINT ticket_event_actor_consistent CHECK (
        (actor_kind = 'staff'  AND actor_user_id IS NOT NULL)
     OR (actor_kind = 'system' AND actor_user_id IS NULL)),
    -- FR-FUL-005, FR-FUL-007, FR-FUL-015, FR-FUL-016A all say "with reason". Each of
    -- those events names one; the rest may not borrow the column for something else.
    CONSTRAINT ticket_event_reason_required CHECK (
        (kind IN ('recalled', 'reprioritised', 'transferred', 'waste'))
        = (reason_code_id IS NOT NULL)),
    CONSTRAINT ticket_event_before_required CHECK (
        (kind = 'released') = (before IS NULL))
);

COMMENT ON TABLE fulfillment.ticket_event IS
    'The authoritative, append-only fulfillment ledger (FR-FUL-002, FR-FUL-005). Every '
    'ticket projection and every station timeline entry is folded out of it, so a '
    'station''s history has no destructive edit path and rebuilds deterministically '
    'alongside the order projections it belongs beside.';

CREATE INDEX ticket_event_replay_idx
    ON fulfillment.ticket_event (tenant_id, ticket_id, sequence_number);
CREATE INDEX ticket_event_correlation_idx
    ON fulfillment.ticket_event (tenant_id, correlation_id);

CREATE FUNCTION fulfillment.refuse_ledger_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'TICKET_LEDGER_MUTATION_REFUSED: the fulfillment ledger is append-only; % is '
        'refused on %', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'HS403';
END;
$$;

CREATE TRIGGER ticket_event_append_only
    BEFORE UPDATE OR DELETE ON fulfillment.ticket_event
    FOR EACH ROW EXECUTE FUNCTION fulfillment.refuse_ledger_mutation();

CREATE TRIGGER ticket_event_no_truncate
    BEFORE TRUNCATE ON fulfillment.ticket_event
    FOR EACH STATEMENT EXECUTE FUNCTION fulfillment.refuse_ledger_mutation();


-- ===========================================================================
-- Tickets and their line units (FR-FUL-002, FR-FUL-004)
-- ===========================================================================

CREATE TABLE fulfillment.ticket (
    id              uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    order_id        uuid NOT NULL,
    station_node_id uuid NOT NULL,

    state           fulfillment.ticket_state NOT NULL,
    priority        fulfillment.priority_level NOT NULL,

    -- FR-FUL-001: which VERSION of the rules put this here. Recorded on the ticket so a
    -- later rule change cannot rewrite why this one went where it did.
    routing_rule_set_id uuid NOT NULL,

    -- FR-FUL-009: an order fans out to several tickets and expo has to reassemble them.
    -- The set is the order; this is the ticket's place in it.
    station_sequence integer NOT NULL,

    -- FR-FUL-003 and FR-FUL-012: elapsed and SLA time. Stated absolutely rather than as
    -- a duration so a rebuild reproduces them exactly.
    released_at     timestamptz NOT NULL,
    sla_due_at      timestamptz,
    acknowledged_at timestamptz,
    preparation_started_at timestamptz,
    ready_at        timestamptz,
    collected_at    timestamptz,
    completed_at    timestamptz,

    -- FR-FUL-008: set when the station acknowledged the allergy declarations on this
    -- ticket. NULL where the station requires it and has not.
    allergy_acknowledged_at timestamptz,
    allergy_acknowledged_by_user_id uuid,

    ledger_sequence integer NOT NULL,

    CONSTRAINT ticket_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT ticket_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT ticket_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ticket_order_fk FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.customer_order (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ticket_station_fk FOREIGN KEY (tenant_id, station_node_id)
        REFERENCES fulfillment.station_profile (tenant_id, station_node_id) ON DELETE RESTRICT,
    CONSTRAINT ticket_rule_set_fk FOREIGN KEY (tenant_id, routing_rule_set_id)
        REFERENCES fulfillment.routing_rule_set (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ticket_ack_user_fk FOREIGN KEY (tenant_id, allergy_acknowledged_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT ticket_sequence_positive CHECK (station_sequence > 0),
    CONSTRAINT ticket_ledger_sequence_positive CHECK (ledger_sequence > 0),
    -- FR-FUL-015 moves a ticket between stations; one order still gets at most one
    -- ticket per station, or a transfer could produce two and duplicate the work.
    CONSTRAINT ticket_one_per_order_station UNIQUE (tenant_id, order_id, station_node_id),
    CONSTRAINT ticket_ack_recorded_together CHECK (
        (allergy_acknowledged_at IS NULL) = (allergy_acknowledged_by_user_id IS NULL)),
    -- Timestamps only appear once the state that sets them has been reached, so a
    -- ticket cannot claim it was ready before it was ever prepared.
    CONSTRAINT ticket_timestamps_ordered CHECK (
        (acknowledged_at IS NULL OR acknowledged_at >= released_at)
    AND (preparation_started_at IS NULL OR acknowledged_at IS NOT NULL)
    AND (ready_at IS NULL OR preparation_started_at IS NOT NULL)
    AND (collected_at IS NULL OR ready_at IS NOT NULL)
    AND (completed_at IS NULL OR collected_at IS NOT NULL))
);

COMMENT ON TABLE fulfillment.ticket IS
    'What one station must do for one order (FR-FUL-002). A projection of '
    'fulfillment.ticket_event: nothing writes here except fulfillment.apply_ticket_event(), '
    'and the state column is additionally guarded by a trigger that consults '
    'fulfillment.transition — so the fold itself cannot write an illegal state.';

CREATE INDEX ticket_order_idx ON fulfillment.ticket (tenant_id, order_id);
CREATE INDEX ticket_station_queue_idx
    ON fulfillment.ticket (tenant_id, station_node_id, state, released_at);

-- FR-FUL-004. Quantities and readiness per line unit, so three of four skewers ready is
-- a state the system can express rather than round to "not ready".
CREATE TABLE fulfillment.ticket_line (
    id              uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    ticket_id       uuid NOT NULL,
    order_line_id   uuid NOT NULL,

    quantity        integer NOT NULL,
    ready_quantity  integer NOT NULL DEFAULT 0,

    -- Copied from the order line at release, like M3-A copies the commercial snapshot,
    -- and for the same reason: a station reads what was ordered, not what the menu says
    -- the dish is called today.
    item_code       text NOT NULL,
    canonical_name  text NOT NULL,

    CONSTRAINT ticket_line_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT ticket_line_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT ticket_line_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ticket_line_ticket_fk FOREIGN KEY (tenant_id, ticket_id)
        REFERENCES fulfillment.ticket (tenant_id, id) ON DELETE RESTRICT,
    -- DEFERRABLE because ordering.apply_event() REPLACES an order's lines rather than
    -- patching them: it deletes and re-inserts the same ids, which an immediate FK sees
    -- as a deletion. Deferred, the rows are back by commit and the reference holds. A
    -- line that genuinely disappeared still fails, at commit, which is the check doing
    -- its job — removing a line is a cancellation, not an amendment.
    -- NO ACTION, not RESTRICT, and the difference is the whole point: RESTRICT is
    -- checked immediately even on a deferrable constraint, so the deferral would have
    -- been decorative. NO ACTION defers, which is what lets the order fold replace a
    -- line in place and still be refused if the line really is gone at commit.
    CONSTRAINT ticket_line_order_line_fk FOREIGN KEY (tenant_id, order_line_id)
        REFERENCES ordering.order_line (tenant_id, id) ON DELETE NO ACTION
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT ticket_line_quantity_positive CHECK (quantity > 0),
    -- The package's first invariant, half of it: readiness cannot exceed the work.
    CONSTRAINT ticket_line_readiness_within_quantity CHECK (
        ready_quantity >= 0 AND ready_quantity <= quantity),
    -- One row per order line per ticket. Two would let a recall or a transfer double the
    -- work by adding rather than moving.
    CONSTRAINT ticket_line_one_per_order_line UNIQUE (ticket_id, order_line_id)
);

CREATE INDEX ticket_line_ticket_idx ON fulfillment.ticket_line (tenant_id, ticket_id);

-- The package's first invariant, the other half: ticket quantities cannot exceed the
-- accepted order-line quantities. Enforced across ALL of an order's tickets, because the
-- way to break it is not one oversized ticket — it is a transfer or a recall that leaves
-- the units on two.
CREATE FUNCTION fulfillment.assert_units_within_order() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_line   uuid := CASE TG_OP WHEN 'DELETE' THEN OLD.order_line_id ELSE NEW.order_line_id END;
    v_tenant uuid := CASE TG_OP WHEN 'DELETE' THEN OLD.tenant_id ELSE NEW.tenant_id END;
    v_ordered integer;
    v_ticketed integer;
BEGIN
    SELECT quantity INTO v_ordered FROM ordering.order_line
     WHERE id = v_line AND tenant_id = v_tenant;

    SELECT coalesce(sum(tl.quantity), 0) INTO v_ticketed
      FROM fulfillment.ticket_line tl
      JOIN fulfillment.ticket t ON t.id = tl.ticket_id
     WHERE tl.order_line_id = v_line AND tl.tenant_id = v_tenant
       AND t.state <> 'cancelled';

    IF v_ordered IS NOT NULL AND v_ticketed > v_ordered THEN
        RAISE EXCEPTION
            'DUPLICATED_WORK: order line % is for % unit(s) and % are on live tickets; '
            'a station would make more than the customer ordered',
            v_line, v_ordered, v_ticketed
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION fulfillment.assert_units_within_order() IS
    'SM-FULFILLMENT-TICKET''s first invariant, enforced across every live ticket for an '
    'order rather than one at a time. Recall (FR-FUL-005), transfer (FR-FUL-015) and the '
    'paper fallback (FR-FUL-014) all fail the same way — by leaving the work on two '
    'tickets instead of moving it — and this is the constraint each of them would break.';

CREATE CONSTRAINT TRIGGER ticket_line_units_within_order
    AFTER INSERT OR UPDATE OR DELETE ON fulfillment.ticket_line
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION fulfillment.assert_units_within_order();


-- ===========================================================================
-- The transition guard (NC-M3-004)
-- ===========================================================================
-- SM-FULFILLMENT-TICKET's fourth invariant: "State transitions are enforced
-- server/database side." Here is the database side. It fires on every UPDATE of
-- fulfillment.ticket including the ones ordering from the fold, so the fold cannot write
-- an illegal state either — a check that lived only in the transition function would be
-- enforcement by convention, which is what "server side" alone would have permitted.
--
-- The projection guard below refuses writes from outside the fold; this refuses ILLEGAL
-- writes from inside it. Two different questions, two triggers.

CREATE FUNCTION fulfillment.assert_legal_transition() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = OLD.state THEN
        RETURN NEW;                    -- not a transition; the row changed some other way
    END IF;

    IF NOT EXISTS (SELECT 1 FROM fulfillment.transition
                    WHERE from_state = OLD.state AND to_state = NEW.state) THEN
        RAISE EXCEPTION
            'ILLEGAL_TICKET_TRANSITION: % -> % is not an edge of SM-FULFILLMENT-TICKET; '
            'ticket %', OLD.state, NEW.state, OLD.id
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER ticket_transition_legal
    BEFORE UPDATE OF state ON fulfillment.ticket
    FOR EACH ROW EXECUTE FUNCTION fulfillment.assert_legal_transition();

COMMENT ON FUNCTION fulfillment.assert_legal_transition() IS
    'Every state change is checked against fulfillment.transition, which equals the '
    'pinned SM-FULFILLMENT-TICKET. NC-M3-004 walks all 110 ordered pairs of the eleven '
    'states — 13 legal edges and 97 refusals — rather than sampling the obvious ones.';

-- A ticket is born queued. The transition trigger only sees UPDATEs, so the starting
-- state is guarded here: a ticket inserted directly as 'completed' would never have
-- transitioned at all.
CREATE FUNCTION fulfillment.assert_ticket_starts_queued() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state <> 'queued' THEN
        RAISE EXCEPTION
            'ILLEGAL_TICKET_TRANSITION: a ticket enters the machine queued, not %; '
            'ticket %', NEW.state, NEW.id
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER ticket_starts_queued
    BEFORE INSERT ON fulfillment.ticket
    FOR EACH ROW EXECUTE FUNCTION fulfillment.assert_ticket_starts_queued();


-- ===========================================================================
-- The projection guard
-- ===========================================================================
-- The same arrangement M3-A uses, and deliberately its own marker: a transaction that is
-- folding an ORDER event has no business writing a ticket projection, and sharing one
-- marker would have let it.

CREATE FUNCTION fulfillment.refuse_projection_write() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF coalesce(current_setting('fulfillment.applying_event', true), '') <> 'yes' THEN
        RAISE EXCEPTION
            'PROJECTION_WRITTEN_DIRECTLY: % on %.% did not come from '
            'fulfillment.apply_ticket_event(); the ledger is the only way to change a ticket',
            TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME
            USING ERRCODE = 'HS403';
    END IF;
    RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER ticket_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON fulfillment.ticket
    FOR EACH ROW EXECUTE FUNCTION fulfillment.refuse_projection_write();

CREATE TRIGGER ticket_line_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON fulfillment.ticket_line
    FOR EACH ROW EXECUTE FUNCTION fulfillment.refuse_projection_write();


-- ===========================================================================
-- Priority, recall, transfer, waste, serving (FR-FUL-005, 007, 011, 015, 016A)
-- ===========================================================================

-- FR-FUL-007. Priority without attribution is how a queue gets gamed, so the actor is
-- NOT NULL and the reason is a registered code. Both are on the record, and the KDS
-- renders them beside the ticket.
CREATE TABLE fulfillment.priority_change (
    id              uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    ticket_id       uuid NOT NULL,
    from_priority   fulfillment.priority_level NOT NULL,
    to_priority     fulfillment.priority_level NOT NULL,
    reason_code_id  uuid NOT NULL,
    applied_by_user_id uuid NOT NULL,
    applied_at      timestamptz NOT NULL,

    CONSTRAINT priority_change_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT priority_change_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT priority_change_ticket_fk FOREIGN KEY (tenant_id, ticket_id)
        REFERENCES fulfillment.ticket (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT priority_change_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT priority_change_actor_fk FOREIGN KEY (tenant_id, applied_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT priority_change_actually_changes CHECK (from_priority <> to_priority)
);

CREATE TRIGGER priority_change_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON fulfillment.priority_change
    FOR EACH ROW EXECUTE FUNCTION fulfillment.refuse_projection_write();

-- FR-FUL-005. A recall pulls a recently completed ticket back for more work. It must not
-- create a second ticket, which is why it is a state change on the SAME ticket recorded
-- here, and why fulfillment.assert_units_within_order() counts across live tickets.
CREATE TABLE fulfillment.ticket_recall (
    id              uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    ticket_id       uuid NOT NULL,
    recalled_from   fulfillment.ticket_state NOT NULL,
    reason_code_id  uuid NOT NULL,
    recalled_by_user_id uuid NOT NULL,
    recalled_at     timestamptz NOT NULL,
    seconds_since_completion integer NOT NULL,

    CONSTRAINT ticket_recall_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT ticket_recall_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ticket_recall_ticket_fk FOREIGN KEY (tenant_id, ticket_id)
        REFERENCES fulfillment.ticket (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ticket_recall_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ticket_recall_actor_fk FOREIGN KEY (tenant_id, recalled_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ticket_recall_window_not_negative CHECK (seconds_since_completion >= 0)
);

CREATE TRIGGER ticket_recall_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON fulfillment.ticket_recall
    FOR EACH ROW EXECUTE FUNCTION fulfillment.refuse_projection_write();

-- FR-FUL-015. Rerouting when a station or device is unavailable. The ticket MOVES: its
-- station_node_id changes and its line units go with it. Nothing is created, which is
-- what "without duplicating work" means and what the units constraint enforces.
CREATE TABLE fulfillment.station_transfer (
    id              uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    ticket_id       uuid NOT NULL,
    from_station_node_id uuid NOT NULL,
    to_station_node_id   uuid NOT NULL,
    reason_code_id  uuid NOT NULL,
    transferred_by_user_id uuid NOT NULL,
    transferred_at  timestamptz NOT NULL,
    units_moved     integer NOT NULL,

    CONSTRAINT station_transfer_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT station_transfer_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT station_transfer_ticket_fk FOREIGN KEY (tenant_id, ticket_id)
        REFERENCES fulfillment.ticket (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT station_transfer_from_fk FOREIGN KEY (tenant_id, from_station_node_id)
        REFERENCES fulfillment.station_profile (tenant_id, station_node_id) ON DELETE RESTRICT,
    CONSTRAINT station_transfer_to_fk FOREIGN KEY (tenant_id, to_station_node_id)
        REFERENCES fulfillment.station_profile (tenant_id, station_node_id) ON DELETE RESTRICT,
    CONSTRAINT station_transfer_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT station_transfer_actor_fk FOREIGN KEY (tenant_id, transferred_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT station_transfer_actually_moves CHECK (
        from_station_node_id <> to_station_node_id),
    CONSTRAINT station_transfer_units_positive CHECK (units_moved > 0)
);

CREATE TRIGGER station_transfer_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON fulfillment.station_transfer
    FOR EACH ROW EXECUTE FUNCTION fulfillment.refuse_projection_write();

-- FR-FUL-011. Who collected and who served, with the exceptions that happen at a pass.
-- Deliberately NOT named collection_order: that exact phrase is one of the 63 fenced
-- terms, a pickup-domain artifact that must not appear here, and an identifier is a
-- surface like any other.
CREATE TABLE fulfillment.serve_record (
    id              uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    ticket_id       uuid NOT NULL,
    collected_by_user_id uuid NOT NULL,
    collected_at    timestamptz NOT NULL,
    served_by_user_id uuid,
    served_at       timestamptz,
    exception_kind  fulfillment.serve_exception,
    exception_note  text,

    CONSTRAINT serve_record_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT serve_record_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT serve_record_ticket_fk FOREIGN KEY (tenant_id, ticket_id)
        REFERENCES fulfillment.ticket (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT serve_record_collector_fk FOREIGN KEY (tenant_id, collected_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT serve_record_server_fk FOREIGN KEY (tenant_id, served_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT serve_record_service_recorded_together CHECK (
        (served_at IS NULL) = (served_by_user_id IS NULL)),
    -- An exception says what went wrong in words. A kind alone is a category, not an
    -- account — the same rule M3-A applied to a session closure exception.
    CONSTRAINT serve_record_exception_explained CHECK (
        (exception_kind IS NULL AND exception_note IS NULL)
     OR (exception_kind IS NOT NULL AND btrim(coalesce(exception_note, '')) <> '')),
    CONSTRAINT serve_record_one_per_ticket UNIQUE (tenant_id, ticket_id)
);

CREATE TRIGGER serve_record_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON fulfillment.serve_record
    FOR EACH ROW EXECUTE FUNCTION fulfillment.refuse_projection_write();

-- FR-FUL-016A. Rework, remake and SERVICE waste. There is no inventory to decrement and
-- no column here that could stand in for one: what is recorded is that work had to be
-- done again and why, which is an operational fact about service.
CREATE TABLE fulfillment.waste_event (
    id              uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    ticket_id       uuid NOT NULL,
    order_id        uuid NOT NULL,
    kind            fulfillment.waste_kind NOT NULL,
    units_affected  integer NOT NULL,
    reason_code_id  uuid NOT NULL,
    recorded_by_user_id uuid NOT NULL,
    recorded_at     timestamptz NOT NULL,
    note            text NOT NULL,

    CONSTRAINT waste_event_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT waste_event_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT waste_event_ticket_fk FOREIGN KEY (tenant_id, ticket_id)
        REFERENCES fulfillment.ticket (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT waste_event_order_fk FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.customer_order (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT waste_event_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT waste_event_actor_fk FOREIGN KEY (tenant_id, recorded_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT waste_event_units_positive CHECK (units_affected > 0),
    CONSTRAINT waste_event_note_not_blank CHECK (btrim(note) <> '')
);

COMMENT ON TABLE fulfillment.waste_event IS
    'FR-FUL-016A. Rework, remake and SERVICE waste, each with reason, actor and the '
    'linked order and ticket. The package''s third invariant is explicit that Phase 1 '
    'posts no consumption against any of this, and there is nothing in this schema it '
    'could post against.';

CREATE TRIGGER waste_event_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON fulfillment.waste_event
    FOR EACH ROW EXECUTE FUNCTION fulfillment.refuse_projection_write();


-- ===========================================================================
-- Station ticket documents (FR-FUL-014)
-- ===========================================================================
-- A paper ticket printed twice is a dish cooked twice, so deduplication is the whole
-- requirement and it is enforced by a UNIQUE KEY rather than by the generator being
-- careful. The key is (ticket, revision): asking again for the same revision returns the
-- document that already exists.
--
-- What this is NOT: a print job, a print queue, a print agent or a spooler. The
-- resilient local print path is M5a and M1-B already guards the identifier space for it
-- — service.qr_placard at M2-B was renamed for exactly that reason. This generates a
-- DOCUMENT and records that it was generated; the path to paper is M5a's.

CREATE TABLE fulfillment.station_ticket_document (
    id              uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    ticket_id       uuid NOT NULL,

    -- A ticket amended after its document was generated needs a new one; the revision is
    -- what makes that a different document rather than a duplicate of the same one.
    revision        integer NOT NULL,
    trigger_reason  fulfillment.document_trigger NOT NULL,

    -- The rendered content, and a digest of it. Two documents for the same ticket
    -- revision cannot exist, and a document whose content changed under its digest is
    -- detectable.
    content         text NOT NULL,
    content_digest  bytea NOT NULL,

    -- FR-FUL-008's later_behavior: "the same salience must survive the printed station
    -- ticket." Recorded so a document with allergy content that lost its emphasis is a
    -- fact the suite can assert on rather than a rendering nobody looked at.
    allergy_line_count integer NOT NULL,

    generated_at    timestamptz NOT NULL,

    CONSTRAINT station_ticket_document_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT station_ticket_document_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT station_ticket_document_ticket_fk FOREIGN KEY (tenant_id, ticket_id)
        REFERENCES fulfillment.ticket (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT station_ticket_document_revision_positive CHECK (revision > 0),
    CONSTRAINT station_ticket_document_digest_is_sha256 CHECK (
        octet_length(content_digest) = 32),
    CONSTRAINT station_ticket_document_content_not_blank CHECK (btrim(content) <> ''),
    CONSTRAINT station_ticket_document_allergy_count_sane CHECK (allergy_line_count >= 0),
    -- THE deduplication. Not a convention in the generator: a constraint.
    CONSTRAINT station_ticket_document_one_per_revision UNIQUE (tenant_id, ticket_id, revision)
);

COMMENT ON TABLE fulfillment.station_ticket_document IS
    'FR-FUL-014. Deduplicated by a unique key on (ticket, revision), so a second request '
    'for the same revision cannot store a second document however many times it is made. '
    'A document, not a print job — the resilient local print path is M5a.';

CREATE TRIGGER station_ticket_document_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON fulfillment.station_ticket_document
    FOR EACH ROW EXECUTE FUNCTION fulfillment.refuse_projection_write();


-- ===========================================================================
-- Ready notices (FR-FUL-010) — the event, not the channel
-- ===========================================================================
-- The requirement says notify the assigned waiter and escalate uncollected items.
-- Notification TRANSPORT is FR-NOT-001 at M3-C, so this emits the fact and builds no
-- channel: a row saying this ticket became ready at this moment for this waiter, and an
-- escalation row when nobody collected it inside the configured window. M3-C picks these
-- up and delivers them; nothing here tries to.

CREATE TABLE fulfillment.ready_notice (
    id              uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    ticket_id       uuid NOT NULL,
    -- The table's owning waiter at the moment the food was ready, from M2-B's ownership
    -- record. NULL where the table has no owner: a notice nobody is addressed to is
    -- still a fact, and inventing a recipient would be worse.
    assigned_user_id uuid,
    became_ready_at timestamptz NOT NULL,
    escalated_at    timestamptz,
    escalation_after_seconds integer,

    CONSTRAINT ready_notice_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT ready_notice_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ready_notice_ticket_fk FOREIGN KEY (tenant_id, ticket_id)
        REFERENCES fulfillment.ticket (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ready_notice_user_fk FOREIGN KEY (tenant_id, assigned_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ready_notice_escalation_recorded_together CHECK (
        (escalated_at IS NULL) = (escalation_after_seconds IS NULL)),
    CONSTRAINT ready_notice_escalation_after_ready CHECK (
        escalated_at IS NULL OR escalated_at >= became_ready_at),
    CONSTRAINT ready_notice_one_per_ticket UNIQUE (tenant_id, ticket_id)
);

COMMENT ON TABLE fulfillment.ready_notice IS
    'FR-FUL-010, the half this gate owns: the EVENT that a ticket is ready and who it is '
    'for. Delivery is FR-NOT-001 at M3-C: there is no channel, transport or template '
    'here, and no delivery-status column for it to be mistaken for.';

CREATE TRIGGER ready_notice_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON fulfillment.ready_notice
    FOR EACH ROW EXECUTE FUNCTION fulfillment.refuse_projection_write();


-- ===========================================================================
-- Asking ordering about allergies, without being able to read the notes
-- ===========================================================================
-- M3-A revokes SELECT on ordering.order_note from the application role outright, so a
-- private staff note cannot be read by anything that has not been handed a door. Every
-- station surface here needs to know whether an order carries an allergy declaration and
-- how many — and needs to know it WITHOUT being able to read note bodies. So ordering
-- answers the question rather than opening the table: a count, not a cursor.

CREATE FUNCTION ordering.order_allergy_declaration_count(
    p_tenant_id uuid, p_order_id uuid) RETURNS integer
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, ordering, public
AS $$
    SELECT count(*)::integer FROM ordering.order_note n
    WHERE n.tenant_id = p_tenant_id AND n.order_id = p_order_id
      AND n.kind = 'allergy_declaration';
$$;

COMMENT ON FUNCTION ordering.order_allergy_declaration_count(uuid, uuid) IS
    'How many allergy declarations an order carries, for the station surfaces that must '
    'react to their presence. Returns a NUMBER: a caller learns that an allergy exists '
    'without gaining any way to read what else was written on the order.';


-- ===========================================================================
-- Routing (FR-FUL-001)
-- ===========================================================================

CREATE FUNCTION fulfillment.effective_rule_set(
    p_tenant_id uuid, p_outlet_id uuid, p_at timestamptz DEFAULT now())
RETURNS uuid
LANGUAGE sql STABLE
AS $$
    SELECT s.id FROM fulfillment.routing_rule_set s
    WHERE s.tenant_id = p_tenant_id AND s.outlet_id = p_outlet_id
      AND s.effective_from <= p_at
      AND (s.effective_to IS NULL OR s.effective_to > p_at)
    ORDER BY s.version DESC
    LIMIT 1;
$$;

-- Where one line goes, under one version of the rules. Most specific first: a rule
-- naming the variant beats one naming the item beats one naming the category beats the
-- catch-all, and precedence breaks ties within a tier.
CREATE FUNCTION fulfillment.route_line(
    p_tenant_id uuid, p_rule_set_id uuid, p_order_line_id uuid)
RETURNS uuid
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_line    ordering.order_line%ROWTYPE;
    v_station uuid;
BEGIN
    SELECT * INTO v_line FROM ordering.order_line
     WHERE id = p_order_line_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ORDER_LINE_NOT_FOUND: no order line % in scope', p_order_line_id
            USING ERRCODE = 'HS404';
    END IF;

    SELECT r.target_station_node_id INTO v_station
      FROM fulfillment.routing_rule r
      LEFT JOIN menu.sellable_item si ON si.id = v_line.item_id
     WHERE r.rule_set_id = p_rule_set_id
       AND (r.variant_id  = v_line.variant_id
         OR r.item_id     = v_line.item_id
         OR r.category_id = si.category_id
         OR (r.variant_id IS NULL AND r.item_id IS NULL AND r.category_id IS NULL))
     ORDER BY (r.variant_id IS NOT NULL) DESC,
              (r.item_id IS NOT NULL) DESC,
              (r.category_id IS NOT NULL) DESC,
              r.precedence
     LIMIT 1;

    IF v_station IS NULL THEN
        -- Refused, never defaulted to "the kitchen". A rule set that does not cover a
        -- line is an incomplete rule set, and silently sending the dish somewhere
        -- plausible is how a bar order gets cooked.
        RAISE EXCEPTION
            'ROUTING_RULE_ABSENT: rule set % routes nothing for order line % (item %); a '
            'line with no rule is not sent to a default station',
            p_rule_set_id, p_order_line_id, v_line.item_id
            USING ERRCODE = 'HS412';
    END IF;
    RETURN v_station;
END;
$$;


-- ===========================================================================
-- The station timeline entry, written by ordering on fulfillment's behalf
-- ===========================================================================
-- FR-ORD-016A wants station events on the ORDER timeline. The obvious way to do that
-- would be for the fulfillment fold to set ordering's projection marker, and that is
-- exactly what it must not do: a transaction folding a TICKET event would then hold the
-- keys to every order projection there is. So ordering exposes one narrow door instead,
-- which sets its own marker, writes one timeline row and clears it again.

CREATE FUNCTION ordering.write_station_timeline_entry(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_order_id  uuid,
    p_sequence  integer,
    p_occurred_at timestamptz,
    p_kind      ordering.event_kind,
    p_visible_to_customer boolean,
    p_customer_summary text,
    p_staff_summary text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, ordering, public
AS $$
BEGIN
    PERFORM set_config('ordering.applying_event', 'yes', true);

    INSERT INTO ordering.order_timeline_entry
        (id, tenant_id, outlet_id, order_id, sequence_number, occurred_at, kind,
         visible_to_customer, visible_to_staff, customer_summary, staff_summary)
    VALUES
        -- Derived from the identity of the fact, exactly as M3-A derives its own, so a
        -- rebuild produces the same primary keys rather than new ones.
        (uuid_in(md5('station' || p_tenant_id::text || p_order_id::text
                     || p_sequence::text || p_kind::text)::cstring),
         p_tenant_id, p_outlet_id, p_order_id, p_sequence, p_occurred_at, p_kind,
         p_visible_to_customer, true, p_customer_summary, p_staff_summary)
    ON CONFLICT (id) DO NOTHING;

    PERFORM set_config('ordering.applying_event', '', true);
END;
$$;

COMMENT ON FUNCTION ordering.write_station_timeline_entry IS
    'The one door through which fulfillment adds to an order timeline (FR-ORD-016A). '
    'Narrow on purpose: it writes a single row of a single table, and it sets and clears '
    'ordering''s projection marker itself so the fulfillment fold never holds it.';

-- Station timeline entries occupy a sequence range of their own, above anything the
-- order ledger will reach, so an order event and a station event can never collide on
-- (order, sequence_number) — which they otherwise would, since the two ledgers number
-- independently.
CREATE FUNCTION ordering.station_timeline_sequence(p_ticket_sequence integer,
                                                   p_station_sequence integer)
RETURNS integer
LANGUAGE sql IMMUTABLE
AS $$
    SELECT 1000000 + p_station_sequence * 1000 + p_ticket_sequence;
$$;


-- ===========================================================================
-- The fold: ticket ledger -> ticket projections and the order timeline
-- ===========================================================================
-- Pure and total, on M3-A's terms. It reads no clock, no sequence and no random source:
-- every value comes out of the event, which is what makes the rebuild byte-deterministic
-- rather than merely equivalent. A kind it does not handle raises.

CREATE FUNCTION fulfillment.apply_ticket_event(p_event_id bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, fulfillment, ordering, service, menu, safety, config, public
AS $$
DECLARE
    e        fulfillment.ticket_event%ROWTYPE;
    v_ticket jsonb;
    v_line   jsonb;
    v_state  fulfillment.ticket_state;
    v_order  uuid;
    v_kind   ordering.event_kind;
    v_customer boolean := false;
    v_customer_text text;
    v_staff_text text;
BEGIN
    SELECT * INTO e FROM fulfillment.ticket_event WHERE id = p_event_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TICKET_EVENT_ABSENT: no ticket event %', p_event_id
            USING ERRCODE = 'HS404';
    END IF;

    PERFORM set_config('fulfillment.applying_event', 'yes', true);

    IF e.kind = 'released' THEN
        v_ticket := e.after -> 'ticket';
        INSERT INTO fulfillment.ticket
            (id, tenant_id, outlet_id, order_id, station_node_id, state, priority,
             routing_rule_set_id, station_sequence, released_at, sla_due_at, ledger_sequence)
        VALUES
            (e.ticket_id, e.tenant_id, e.outlet_id,
             (v_ticket ->> 'order_id')::uuid,
             (v_ticket ->> 'station_node_id')::uuid,
             'queued',
             (v_ticket ->> 'priority')::fulfillment.priority_level,
             (v_ticket ->> 'routing_rule_set_id')::uuid,
             (v_ticket ->> 'station_sequence')::integer,
             e.occurred_at,
             CASE WHEN v_ticket ->> 'sla_minutes' IS NULL THEN NULL
                  ELSE e.occurred_at
                       + make_interval(mins => (v_ticket ->> 'sla_minutes')::integer) END,
             e.sequence_number);

        FOR v_line IN SELECT * FROM jsonb_array_elements(e.after -> 'lines') LOOP
            INSERT INTO fulfillment.ticket_line
                (id, tenant_id, outlet_id, ticket_id, order_line_id, quantity,
                 ready_quantity, item_code, canonical_name)
            VALUES ((v_line ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.ticket_id,
                    (v_line ->> 'order_line_id')::uuid,
                    (v_line ->> 'quantity')::integer, 0,
                    v_line ->> 'item_code', v_line ->> 'canonical_name');
        END LOOP;

        -- FR-ORD-019A's fifth artifact, linked HERE rather than in release_order().
        -- Written by the caller, the link was a projection no ledger produced: a rebuild
        -- dropped every correlation row and the order replay could not put the ticket
        -- ones back, so the ordering digest moved and M3-A's NC-M3-009 went red for a
        -- correct system — but only when M3-B had run first, which is exactly the kind
        -- of order dependence the reversed run exists to find. linked_at is the EVENT's
        -- timestamp, not now(), so the replay is byte-identical rather than merely
        -- equivalent.
        PERFORM ordering.link_correlation_artifact(
            e.tenant_id, e.outlet_id, e.correlation_id, 'fulfillment_ticket',
            e.ticket_id, e.occurred_at);

    ELSIF e.kind = 'transitioned' THEN
        v_state := (e.after ->> 'state')::fulfillment.ticket_state;
        UPDATE fulfillment.ticket
           SET state = v_state,
               acknowledged_at = CASE WHEN v_state = 'acknowledged' THEN e.occurred_at
                                      ELSE acknowledged_at END,
               preparation_started_at = CASE WHEN v_state = 'preparing'
                                                  AND preparation_started_at IS NULL
                                             THEN e.occurred_at
                                             ELSE preparation_started_at END,
               ready_at = CASE WHEN v_state = 'ready' THEN e.occurred_at ELSE ready_at END,
               collected_at = CASE WHEN v_state = 'collected' THEN e.occurred_at
                                   ELSE collected_at END,
               completed_at = CASE WHEN v_state = 'completed' THEN e.occurred_at
                                   ELSE completed_at END,
               ledger_sequence = e.sequence_number
         WHERE id = e.ticket_id;

    ELSIF e.kind = 'unit_progress' THEN
        FOR v_line IN SELECT * FROM jsonb_array_elements(e.after -> 'lines') LOOP
            UPDATE fulfillment.ticket_line
               SET ready_quantity = (v_line ->> 'ready_quantity')::integer
             WHERE id = (v_line ->> 'id')::uuid;
        END LOOP;
        UPDATE fulfillment.ticket SET ledger_sequence = e.sequence_number
         WHERE id = e.ticket_id;

    ELSIF e.kind = 'amended' THEN
        -- Quantities only. Amending a line to zero is a cancellation and ordering
        -- refuses it there, so nothing here has to invent what removing a line means.
        FOR v_line IN SELECT * FROM jsonb_array_elements(e.after -> 'lines') LOOP
            UPDATE fulfillment.ticket_line
               SET quantity = (v_line ->> 'quantity')::integer,
                   -- A station cannot have MORE ready than it now has to make. Reducing
                   -- an order from four to two when three were ready is a real case, and
                   -- the honest answer is two ready of two, not three of two.
                   ready_quantity = least(ready_quantity, (v_line ->> 'quantity')::integer)
             WHERE id = (v_line ->> 'id')::uuid AND ticket_id = e.ticket_id;
        END LOOP;
        UPDATE fulfillment.ticket SET ledger_sequence = e.sequence_number
         WHERE id = e.ticket_id;

    ELSIF e.kind = 'acknowledged_allergy' THEN
        UPDATE fulfillment.ticket
           SET allergy_acknowledged_at = e.occurred_at,
               allergy_acknowledged_by_user_id = e.actor_user_id,
               ledger_sequence = e.sequence_number
         WHERE id = e.ticket_id;

    ELSIF e.kind = 'reprioritised' THEN
        INSERT INTO fulfillment.priority_change
            (id, tenant_id, outlet_id, ticket_id, from_priority, to_priority,
             reason_code_id, applied_by_user_id, applied_at)
        VALUES ((e.after ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.ticket_id,
                (e.before ->> 'priority')::fulfillment.priority_level,
                (e.after ->> 'priority')::fulfillment.priority_level,
                e.reason_code_id, e.actor_user_id, e.occurred_at);
        UPDATE fulfillment.ticket
           SET priority = (e.after ->> 'priority')::fulfillment.priority_level,
               ledger_sequence = e.sequence_number
         WHERE id = e.ticket_id;

    ELSIF e.kind = 'recalled' THEN
        INSERT INTO fulfillment.ticket_recall
            (id, tenant_id, outlet_id, ticket_id, recalled_from, reason_code_id,
             recalled_by_user_id, recalled_at, seconds_since_completion)
        VALUES ((e.after ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.ticket_id,
                (e.before ->> 'state')::fulfillment.ticket_state, e.reason_code_id,
                e.actor_user_id, e.occurred_at,
                (e.after ->> 'seconds_since_completion')::integer);
        -- The recall MOVES the ticket back; it does not create one. That is the whole
        -- difference between a recall and duplicated work.
        UPDATE fulfillment.ticket
           SET state = (e.after ->> 'state')::fulfillment.ticket_state,
               ready_at = NULL, collected_at = NULL, completed_at = NULL,
               ledger_sequence = e.sequence_number
         WHERE id = e.ticket_id;

    ELSIF e.kind = 'transferred' THEN
        INSERT INTO fulfillment.station_transfer
            (id, tenant_id, outlet_id, ticket_id, from_station_node_id,
             to_station_node_id, reason_code_id, transferred_by_user_id, transferred_at,
             units_moved)
        VALUES ((e.after ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.ticket_id,
                (e.before ->> 'station_node_id')::uuid,
                (e.after ->> 'station_node_id')::uuid, e.reason_code_id, e.actor_user_id,
                e.occurred_at, (e.after ->> 'units_moved')::integer);
        -- Again a move, not a copy: the SAME ticket changes station.
        UPDATE fulfillment.ticket
           SET station_node_id = (e.after ->> 'station_node_id')::uuid,
               ledger_sequence = e.sequence_number
         WHERE id = e.ticket_id;

    ELSIF e.kind = 'document_generated' THEN
        INSERT INTO fulfillment.station_ticket_document
            (id, tenant_id, outlet_id, ticket_id, revision, trigger_reason, content,
             content_digest, allergy_line_count, generated_at)
        VALUES ((e.after ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.ticket_id,
                (e.after ->> 'revision')::integer,
                (e.after ->> 'trigger_reason')::fulfillment.document_trigger,
                e.after ->> 'content',
                decode(e.after ->> 'content_digest', 'hex'),
                (e.after ->> 'allergy_line_count')::integer, e.occurred_at)
        ON CONFLICT (tenant_id, ticket_id, revision) DO NOTHING;
        UPDATE fulfillment.ticket SET ledger_sequence = e.sequence_number
         WHERE id = e.ticket_id;

    ELSIF e.kind = 'served' THEN
        INSERT INTO fulfillment.serve_record
            (id, tenant_id, outlet_id, ticket_id, collected_by_user_id, collected_at,
             served_by_user_id, served_at, exception_kind, exception_note)
        VALUES ((e.after ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.ticket_id,
                (e.after ->> 'collected_by_user_id')::uuid,
                (e.after ->> 'collected_at')::timestamptz,
                nullif(e.after ->> 'served_by_user_id', '')::uuid,
                nullif(e.after ->> 'served_at', '')::timestamptz,
                nullif(e.after ->> 'exception_kind', '')::fulfillment.serve_exception,
                nullif(e.after ->> 'exception_note', ''))
        ON CONFLICT (tenant_id, ticket_id) DO UPDATE
           SET served_by_user_id = EXCLUDED.served_by_user_id,
               served_at = EXCLUDED.served_at,
               exception_kind = EXCLUDED.exception_kind,
               exception_note = EXCLUDED.exception_note;
        -- SM-FULFILLMENT-TICKET's 'collected -> completed: served/handoff confirmed'.
        -- A serve that recorded WHO served and left the ticket at 'collected' would put
        -- the machine's own edge out of reach and leave every plate in the building
        -- permanently in transit. Only a serve that names a server confirms the handoff:
        -- a collection logged with a missing-item exception and nobody serving yet is
        -- still on its way. Read from the EVENT, never from now(), so the fold stays
        -- byte-deterministic on replay.
        UPDATE fulfillment.ticket
           SET state = CASE WHEN nullif(e.after ->> 'served_at', '') IS NOT NULL
                                 AND state = 'collected'
                            THEN 'completed'::fulfillment.ticket_state ELSE state END,
               completed_at = CASE WHEN nullif(e.after ->> 'served_at', '') IS NOT NULL
                                   THEN (e.after ->> 'served_at')::timestamptz
                                   ELSE completed_at END,
               ledger_sequence = e.sequence_number
         WHERE id = e.ticket_id;

    ELSIF e.kind = 'waste' THEN
        INSERT INTO fulfillment.waste_event
            (id, tenant_id, outlet_id, ticket_id, order_id, kind, units_affected,
             reason_code_id, recorded_by_user_id, recorded_at, note)
        VALUES ((e.after ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.ticket_id,
                (e.after ->> 'order_id')::uuid,
                (e.after ->> 'kind')::fulfillment.waste_kind,
                (e.after ->> 'units_affected')::integer, e.reason_code_id,
                e.actor_user_id, e.occurred_at, e.after ->> 'note');
        UPDATE fulfillment.ticket SET ledger_sequence = e.sequence_number
         WHERE id = e.ticket_id;

    ELSE
        -- Unreachable today: every label of fulfillment.ticket_event_kind is folded
        -- above, and tests/m3b proves it by reading the labels out of the catalog. The
        -- branch is here for the day somebody adds an eleventh.
        RAISE EXCEPTION
            'TICKET_EVENT_KIND_UNHANDLED: no fold for %', e.kind USING ERRCODE = 'HS500';
    END IF;

    -- The station half of the order timeline (FR-ORD-016A). Only the milestones an order
    -- reader cares about; a station's internal churn stays in the fulfillment ledger.
    SELECT order_id INTO v_order FROM fulfillment.ticket WHERE id = e.ticket_id;
    v_kind := CASE
        WHEN e.kind = 'released' THEN 'tickets_released'::ordering.event_kind
        WHEN e.kind = 'served'   THEN 'items_served'::ordering.event_kind
        WHEN e.kind = 'transitioned' THEN CASE (e.after ->> 'state')
            WHEN 'acknowledged' THEN 'station_acknowledged'::ordering.event_kind
            WHEN 'preparing'    THEN 'station_preparing'::ordering.event_kind
            WHEN 'ready'        THEN 'station_ready'::ordering.event_kind
            WHEN 'collected'    THEN 'items_collected'::ordering.event_kind
            WHEN 'exception'    THEN 'station_exception'::ordering.event_kind
            ELSE NULL END
        ELSE NULL END;

    IF v_kind IS NOT NULL AND v_order IS NOT NULL THEN
        -- A guest may be told their food is being made and that it is on its way. They
        -- are not shown which station, who acknowledged it, or that it went to exception:
        -- that is internal handling, the same distinction M3-A drew for a void.
        v_customer := v_kind IN ('station_preparing', 'items_served');
        v_customer_text := CASE v_kind
            WHEN 'station_preparing' THEN 'Your order is being prepared.'
            WHEN 'items_served'      THEN 'Your order was served.'
            ELSE NULL END;
        v_staff_text := CASE v_kind
            WHEN 'tickets_released'     THEN 'Tickets released to stations.'
            WHEN 'station_acknowledged' THEN 'A station accepted its ticket.'
            WHEN 'station_preparing'    THEN 'A station started preparing.'
            WHEN 'station_ready'        THEN 'A station reported ready.'
            WHEN 'items_collected'      THEN 'Items collected from the pass.'
            WHEN 'items_served'         THEN 'Items served to the table.'
            WHEN 'station_exception'    THEN 'A station raised an exception.'
            END;

        PERFORM ordering.write_station_timeline_entry(
            e.tenant_id, e.outlet_id, v_order,
            ordering.station_timeline_sequence(
                e.sequence_number,
                (SELECT station_sequence FROM fulfillment.ticket WHERE id = e.ticket_id)),
            e.occurred_at, v_kind, v_customer, v_customer_text, v_staff_text);
    END IF;

    PERFORM set_config('fulfillment.applying_event', '', true);
END;
$$;


-- ===========================================================================
-- Releasing an accepted order to its stations (FR-FUL-001, FR-FUL-002, FR-ORD-009)
-- ===========================================================================
-- An order fans out to one ticket per station. FR-ORD-009's add-on orders get their own
-- tickets with their own timings by construction: tickets belong to an ORDER, and an
-- add-on is a different order, so nothing had to be added for them to be independent.

CREATE FUNCTION fulfillment.next_ticket_sequence(p_tenant_id uuid, p_ticket_id uuid)
RETURNS integer
LANGUAGE sql STABLE
AS $$
    SELECT coalesce(max(sequence_number), 0) + 1
    FROM fulfillment.ticket_event
    WHERE tenant_id = p_tenant_id AND ticket_id = p_ticket_id;
$$;

CREATE FUNCTION fulfillment.release_order(
    p_tenant_id uuid,
    p_order_id  uuid,
    p_actor_user_id uuid DEFAULT NULL
) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_order    ordering.customer_order%ROWTYPE;
    v_rule_set uuid;
    v_station  uuid;
    v_line     ordering.order_line%ROWTYPE;
    v_tickets  jsonb := '{}'::jsonb;
    v_key      text;
    v_ticket   uuid;
    v_event    bigint;
    v_seq      integer := 0;
    v_count    integer := 0;
    v_sla      integer;
BEGIN
    SELECT * INTO v_order FROM ordering.customer_order
     WHERE id = p_order_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ORDER_NOT_FOUND: no order % in scope', p_order_id
            USING ERRCODE = 'HS404';
    END IF;

    -- Only an ACCEPTED order becomes work. FR-FUL-001 says "accepted line units", and a
    -- submitted order that a member of staff has not confirmed is not yet a promise.
    IF v_order.state <> 'accepted' THEN
        RAISE EXCEPTION
            'ORDER_NOT_ACCEPTED: order % is %; only an accepted order is released to a '
            'station', p_order_id, v_order.state USING ERRCODE = 'HS409';
    END IF;

    IF EXISTS (SELECT 1 FROM fulfillment.ticket
                WHERE tenant_id = p_tenant_id AND order_id = p_order_id) THEN
        RAISE EXCEPTION
            'ORDER_ALREADY_RELEASED: order % already has tickets; releasing twice is how '
            'a kitchen cooks an order twice', p_order_id USING ERRCODE = 'HS409';
    END IF;

    v_rule_set := fulfillment.effective_rule_set(p_tenant_id, v_order.outlet_id);
    IF v_rule_set IS NULL THEN
        RAISE EXCEPTION
            'ROUTING_RULE_ABSENT: outlet % has no routing rule set in force; an order '
            'cannot be sent to a station nobody chose', v_order.outlet_id
            USING ERRCODE = 'HS412';
    END IF;

    -- Group the lines by the station each routes to, in a deterministic order.
    FOR v_line IN
        SELECT * FROM ordering.order_line
         WHERE tenant_id = p_tenant_id AND order_id = p_order_id
         ORDER BY line_number
    LOOP
        v_station := fulfillment.route_line(p_tenant_id, v_rule_set, v_line.id);
        v_key := v_station::text;
        v_tickets := jsonb_set(
            v_tickets, ARRAY[v_key],
            coalesce(v_tickets -> v_key, '[]'::jsonb) || jsonb_build_object(
                'id', gen_random_uuid(),
                'order_line_id', v_line.id,
                'quantity', v_line.quantity,
                'item_code', v_line.item_code,
                'canonical_name', v_line.canonical_name));
    END LOOP;

    IF v_tickets = '{}'::jsonb THEN
        RAISE EXCEPTION 'ORDER_HAS_NO_LINES: order % has nothing to make', p_order_id
            USING ERRCODE = 'HS409';
    END IF;

    FOR v_key IN SELECT jsonb_object_keys(v_tickets) ORDER BY 1 LOOP
        v_seq := v_seq + 1;
        v_ticket := gen_random_uuid();

        SELECT sla_minutes INTO v_sla FROM fulfillment.station_profile
         WHERE tenant_id = p_tenant_id AND station_node_id = v_key::uuid;

        INSERT INTO fulfillment.ticket_event
            (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
             actor_user_id, correlation_id, after)
        VALUES (p_tenant_id, v_order.outlet_id, v_ticket, 1, 'released',
                CASE WHEN p_actor_user_id IS NOT NULL THEN 'staff' ELSE 'system' END
                    ::ordering.actor_kind,
                p_actor_user_id, v_order.correlation_id,
                jsonb_build_object(
                    'ticket', jsonb_build_object(
                        'order_id', p_order_id,
                        'station_node_id', v_key,
                        'priority', 'ordinary',
                        'routing_rule_set_id', v_rule_set,
                        'station_sequence', v_seq,
                        'sla_minutes', v_sla),
                    'lines', v_tickets -> v_key))
        RETURNING id INTO v_event;

        -- The fold does the linking (FR-ORD-019A), so the chain comes back with a
        -- rebuild rather than only with the release that happened to be running.
        PERFORM fulfillment.apply_ticket_event(v_event);

        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION fulfillment.release_order(uuid, uuid, uuid) IS
    'Fans an accepted order out to one ticket per station (FR-FUL-001, FR-FUL-002). '
    'Refuses a second release outright: releasing twice is the coarsest way to duplicate '
    'work, and the unit constraint would catch it afterwards but this says why.';

-- FR-ORD-019A. ordering owns its own correlation table, so fulfillment asks rather than
-- reaching in — the same narrow door as the timeline entry above.
CREATE FUNCTION ordering.link_correlation_artifact(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_correlation_id uuid,
    p_artifact_kind ordering.artifact_kind,
    p_artifact_id uuid,
    p_linked_at timestamptz
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, ordering, public
AS $$
BEGIN
    PERFORM set_config('ordering.applying_event', 'yes', true);
    INSERT INTO ordering.correlation_link
        (tenant_id, outlet_id, correlation_id, artifact_kind, artifact_id, linked_at)
    VALUES (p_tenant_id, p_outlet_id, p_correlation_id, p_artifact_kind, p_artifact_id,
            p_linked_at)
    ON CONFLICT DO NOTHING;
    PERFORM set_config('ordering.applying_event', '', true);
END;
$$;


-- ===========================================================================
-- Transitions and the operations that drive them
-- ===========================================================================

CREATE FUNCTION fulfillment.transition_ticket(
    p_tenant_id uuid,
    p_ticket_id uuid,
    p_to_state  fulfillment.ticket_state,
    p_actor_user_id uuid DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_ticket fulfillment.ticket%ROWTYPE;
    v_event  bigint;
    v_ack_required boolean;
BEGIN
    SELECT * INTO v_ticket FROM fulfillment.ticket
     WHERE id = p_ticket_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TICKET_NOT_FOUND: no ticket % in scope', p_ticket_id
            USING ERRCODE = 'HS404';
    END IF;

    -- FR-FUL-008. Where the station is configured to require it, an allergy declaration
    -- must be acknowledged BEFORE preparation may begin. Checked here rather than on the
    -- screen: a station that never opened the ticket has not acknowledged anything.
    IF p_to_state = 'preparing' THEN
        SELECT sp.allergy_acknowledgement_required INTO v_ack_required
          FROM fulfillment.station_profile sp
         WHERE sp.tenant_id = p_tenant_id AND sp.station_node_id = v_ticket.station_node_id;

        IF coalesce(v_ack_required, true)
           AND v_ticket.allergy_acknowledged_at IS NULL
           AND ordering.order_allergy_declaration_count(
                   p_tenant_id, v_ticket.order_id) > 0 THEN
            RAISE EXCEPTION
                'ALLERGY_NOT_ACKNOWLEDGED: ticket % carries an allergy declaration and '
                'this station requires acknowledgement before preparing',
                p_ticket_id USING ERRCODE = 'HS412';
        END IF;
    END IF;

    -- The legality check lives on the projection trigger, which fires when the fold
    -- writes. Asking here as well would be a second opinion; the event is written and
    -- the trigger decides, so an illegal transition leaves no ledger row behind.
    INSERT INTO fulfillment.ticket_event
        (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, before, after)
    SELECT p_tenant_id, v_ticket.outlet_id, p_ticket_id,
           fulfillment.next_ticket_sequence(p_tenant_id, p_ticket_id), 'transitioned',
           CASE WHEN p_actor_user_id IS NOT NULL THEN 'staff' ELSE 'system' END
               ::ordering.actor_kind,
           p_actor_user_id, o.correlation_id,
           jsonb_build_object('state', v_ticket.state),
           jsonb_build_object('state', p_to_state)
      FROM ordering.customer_order o
     WHERE o.id = v_ticket.order_id AND o.tenant_id = p_tenant_id
    RETURNING id INTO v_event;

    PERFORM fulfillment.apply_ticket_event(v_event);
END;
$$;

-- FR-FUL-008, the acknowledgement itself.
CREATE FUNCTION fulfillment.acknowledge_allergy(
    p_tenant_id uuid, p_ticket_id uuid, p_user_id uuid) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_ticket fulfillment.ticket%ROWTYPE;
    v_event  bigint;
BEGIN
    SELECT * INTO v_ticket FROM fulfillment.ticket
     WHERE id = p_ticket_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TICKET_NOT_FOUND: no ticket % in scope', p_ticket_id
            USING ERRCODE = 'HS404';
    END IF;

    IF ordering.order_allergy_declaration_count(p_tenant_id, v_ticket.order_id) = 0 THEN
        RAISE EXCEPTION
            'NO_ALLERGY_TO_ACKNOWLEDGE: ticket % carries no allergy declaration; '
            'acknowledging one that does not exist would train the gesture out of meaning '
            'anything', p_ticket_id USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO fulfillment.ticket_event
        (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, before, after)
    SELECT p_tenant_id, v_ticket.outlet_id, p_ticket_id,
           fulfillment.next_ticket_sequence(p_tenant_id, p_ticket_id),
           'acknowledged_allergy', 'staff', p_user_id, o.correlation_id,
           jsonb_build_object('acknowledged', false),
           jsonb_build_object('acknowledged', true)
      FROM ordering.customer_order o
     WHERE o.id = v_ticket.order_id AND o.tenant_id = p_tenant_id
    RETURNING id INTO v_event;

    PERFORM fulfillment.apply_ticket_event(v_event);
END;
$$;

-- FR-FUL-004. Partial readiness is a state the system can express.
CREATE FUNCTION fulfillment.record_unit_progress(
    p_tenant_id uuid, p_ticket_line_id uuid, p_ready_quantity integer, p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_line   fulfillment.ticket_line%ROWTYPE;
    v_ticket fulfillment.ticket%ROWTYPE;
    v_event  bigint;
BEGIN
    SELECT * INTO v_line FROM fulfillment.ticket_line
     WHERE id = p_ticket_line_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TICKET_LINE_NOT_FOUND: no ticket line % in scope', p_ticket_line_id
            USING ERRCODE = 'HS404';
    END IF;

    IF p_ready_quantity < 0 OR p_ready_quantity > v_line.quantity THEN
        RAISE EXCEPTION
            'UNIT_PROGRESS_OUT_OF_RANGE: % of % unit(s) ready is not a quantity this '
            'line can reach', p_ready_quantity, v_line.quantity USING ERRCODE = 'HS400';
    END IF;

    SELECT * INTO v_ticket FROM fulfillment.ticket WHERE id = v_line.ticket_id;

    INSERT INTO fulfillment.ticket_event
        (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, before, after)
    SELECT p_tenant_id, v_ticket.outlet_id, v_ticket.id,
           fulfillment.next_ticket_sequence(p_tenant_id, v_ticket.id), 'unit_progress',
           'staff', p_user_id, o.correlation_id,
           jsonb_build_object('lines', jsonb_build_array(jsonb_build_object(
               'id', v_line.id, 'ready_quantity', v_line.ready_quantity))),
           jsonb_build_object('lines', jsonb_build_array(jsonb_build_object(
               'id', v_line.id, 'ready_quantity', p_ready_quantity)))
      FROM ordering.customer_order o
     WHERE o.id = v_ticket.order_id AND o.tenant_id = p_tenant_id
    RETURNING id INTO v_event;

    PERFORM fulfillment.apply_ticket_event(v_event);
END;
$$;


-- FR-FUL-007. Priority with an authorized reason and an attributed actor. Both are
-- required parameters, so there is no call that applies priority anonymously.
CREATE FUNCTION fulfillment.set_priority(
    p_tenant_id uuid, p_ticket_id uuid, p_priority fulfillment.priority_level,
    p_reason_code_id uuid, p_user_id uuid) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_ticket fulfillment.ticket%ROWTYPE;
    v_event  bigint;
BEGIN
    SELECT * INTO v_ticket FROM fulfillment.ticket
     WHERE id = p_ticket_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TICKET_NOT_FOUND: no ticket % in scope', p_ticket_id
            USING ERRCODE = 'HS404';
    END IF;

    IF p_user_id IS NULL THEN
        RAISE EXCEPTION
            'PRIORITY_WITHOUT_ACTOR: a priority change names the person who made it; '
            'priority nobody is accountable for is how a queue gets gamed'
            USING ERRCODE = 'HS403';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM config.reason_code
                    WHERE id = p_reason_code_id AND tenant_id = p_tenant_id
                      AND category = 'manager_override' AND status = 'active') THEN
        RAISE EXCEPTION
            'PRIORITY_REASON_INVALID: % is not an active manager_override reason code',
            p_reason_code_id USING ERRCODE = 'HS400';
    END IF;

    IF v_ticket.priority = p_priority THEN
        RAISE EXCEPTION
            'PRIORITY_UNCHANGED: ticket % is already %; recording a change that changed '
            'nothing would pad the audit', p_ticket_id, p_priority USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO fulfillment.ticket_event
        (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, reason_code_id, before, after)
    SELECT p_tenant_id, v_ticket.outlet_id, p_ticket_id,
           fulfillment.next_ticket_sequence(p_tenant_id, p_ticket_id), 'reprioritised',
           'staff', p_user_id, o.correlation_id, p_reason_code_id,
           jsonb_build_object('priority', v_ticket.priority),
           jsonb_build_object('id', gen_random_uuid(), 'priority', p_priority)
      FROM ordering.customer_order o
     WHERE o.id = v_ticket.order_id AND o.tenant_id = p_tenant_id
    RETURNING id INTO v_event;

    PERFORM fulfillment.apply_ticket_event(v_event);
END;
$$;

-- FR-FUL-005. A recall pulls a recently completed ticket back to preparing. "Recently"
-- is configured, not assumed, and the ticket MOVES rather than being reissued.
CREATE FUNCTION fulfillment.recall_ticket(
    p_tenant_id uuid, p_ticket_id uuid, p_reason_code_id uuid, p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_ticket fulfillment.ticket%ROWTYPE;
    v_policy jsonb;
    v_window integer;
    v_since  integer;
    v_event  bigint;
BEGIN
    SELECT * INTO v_ticket FROM fulfillment.ticket
     WHERE id = p_ticket_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TICKET_NOT_FOUND: no ticket % in scope', p_ticket_id
            USING ERRCODE = 'HS404';
    END IF;

    IF v_ticket.state <> 'ready' THEN
        RAISE EXCEPTION
            'TICKET_NOT_RECALLABLE: ticket % is %; a recall returns work that was '
            'reported ready', p_ticket_id, v_ticket.state USING ERRCODE = 'HS409';
    END IF;

    v_policy := ordering.require_policy(p_tenant_id, v_ticket.outlet_id, 'service');
    IF NOT (v_policy ? 'recall_window_seconds') THEN
        RAISE EXCEPTION
            'SERVICE_POLICY_INCOMPLETE: the service policy states no recall_window_seconds; '
            'a recall window that defaults is not a window' USING ERRCODE = 'HS412';
    END IF;
    v_window := (v_policy ->> 'recall_window_seconds')::integer;
    v_since := floor(extract(epoch FROM now() - v_ticket.ready_at))::integer;

    IF v_since > v_window THEN
        RAISE EXCEPTION
            'RECALL_WINDOW_CLOSED: ticket % became ready %s ago and the configured window '
            'is %s', p_ticket_id, v_since, v_window USING ERRCODE = 'HS409';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM config.reason_code
                    WHERE id = p_reason_code_id AND tenant_id = p_tenant_id
                      AND category = 'manager_override' AND status = 'active') THEN
        RAISE EXCEPTION
            'RECALL_REASON_INVALID: % is not an active manager_override reason code',
            p_reason_code_id USING ERRCODE = 'HS400';
    END IF;

    INSERT INTO fulfillment.ticket_event
        (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, reason_code_id, before, after)
    SELECT p_tenant_id, v_ticket.outlet_id, p_ticket_id,
           fulfillment.next_ticket_sequence(p_tenant_id, p_ticket_id), 'recalled',
           'staff', p_user_id, o.correlation_id, p_reason_code_id,
           jsonb_build_object('state', v_ticket.state),
           jsonb_build_object('id', gen_random_uuid(), 'state', 'rework',
                              'seconds_since_completion', v_since)
      FROM ordering.customer_order o
     WHERE o.id = v_ticket.order_id AND o.tenant_id = p_tenant_id
    RETURNING id INTO v_event;

    PERFORM fulfillment.apply_ticket_event(v_event);
END;
$$;

-- FR-FUL-015. Reroute without duplicating work: the SAME ticket changes station, its
-- line units travel with it because they belong to the ticket, and nothing new is made.
CREATE FUNCTION fulfillment.transfer_ticket(
    p_tenant_id uuid, p_ticket_id uuid, p_to_station_node_id uuid,
    p_reason_code_id uuid, p_user_id uuid) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_ticket fulfillment.ticket%ROWTYPE;
    v_units  integer;
    v_event  bigint;
BEGIN
    SELECT * INTO v_ticket FROM fulfillment.ticket
     WHERE id = p_ticket_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TICKET_NOT_FOUND: no ticket % in scope', p_ticket_id
            USING ERRCODE = 'HS404';
    END IF;

    IF v_ticket.station_node_id = p_to_station_node_id THEN
        RAISE EXCEPTION 'TRANSFER_TO_SAME_STATION: ticket % is already at station %',
            p_ticket_id, p_to_station_node_id USING ERRCODE = 'HS409';
    END IF;

    IF v_ticket.state IN ('completed', 'cancelled') THEN
        RAISE EXCEPTION
            'TICKET_NOT_TRANSFERABLE: ticket % is %; finished work does not move',
            p_ticket_id, v_ticket.state USING ERRCODE = 'HS409';
    END IF;

    IF EXISTS (SELECT 1 FROM fulfillment.ticket
                WHERE tenant_id = p_tenant_id AND order_id = v_ticket.order_id
                  AND station_node_id = p_to_station_node_id) THEN
        RAISE EXCEPTION
            'TRANSFER_TARGET_ALREADY_HAS_A_TICKET: order % already has a ticket at '
            'station %; moving this one there would put the same order''s work on two '
            'tickets at one station', v_ticket.order_id, p_to_station_node_id
            USING ERRCODE = 'HS409';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM config.reason_code
                    WHERE id = p_reason_code_id AND tenant_id = p_tenant_id
                      AND category = 'manager_override' AND status = 'active') THEN
        RAISE EXCEPTION
            'TRANSFER_REASON_INVALID: % is not an active manager_override reason code',
            p_reason_code_id USING ERRCODE = 'HS400';
    END IF;

    SELECT coalesce(sum(quantity), 0) INTO v_units
      FROM fulfillment.ticket_line WHERE ticket_id = p_ticket_id;

    INSERT INTO fulfillment.ticket_event
        (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, reason_code_id, before, after)
    SELECT p_tenant_id, v_ticket.outlet_id, p_ticket_id,
           fulfillment.next_ticket_sequence(p_tenant_id, p_ticket_id), 'transferred',
           'staff', p_user_id, o.correlation_id, p_reason_code_id,
           jsonb_build_object('station_node_id', v_ticket.station_node_id),
           jsonb_build_object('id', gen_random_uuid(),
                              'station_node_id', p_to_station_node_id,
                              'units_moved', v_units)
      FROM ordering.customer_order o
     WHERE o.id = v_ticket.order_id AND o.tenant_id = p_tenant_id
    RETURNING id INTO v_event;

    PERFORM fulfillment.apply_ticket_event(v_event);
END;
$$;

-- FR-FUL-011. Who collected, who served, and what went wrong if anything did.
CREATE FUNCTION fulfillment.record_serve(
    p_tenant_id uuid, p_ticket_id uuid, p_collected_by uuid,
    p_served_by uuid DEFAULT NULL,
    p_exception fulfillment.serve_exception DEFAULT NULL,
    p_exception_note text DEFAULT NULL) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_ticket fulfillment.ticket%ROWTYPE;
    v_event  bigint;
BEGIN
    SELECT * INTO v_ticket FROM fulfillment.ticket
     WHERE id = p_ticket_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TICKET_NOT_FOUND: no ticket % in scope', p_ticket_id
            USING ERRCODE = 'HS404';
    END IF;

    IF v_ticket.state NOT IN ('collected', 'completed') THEN
        RAISE EXCEPTION
            'TICKET_NOT_COLLECTED: ticket % is %; service is recorded against work that '
            'left the pass', p_ticket_id, v_ticket.state USING ERRCODE = 'HS409';
    END IF;

    IF p_exception IS NOT NULL AND btrim(coalesce(p_exception_note, '')) = '' THEN
        RAISE EXCEPTION
            'SERVE_EXCEPTION_UNEXPLAINED: a % exception says what happened; a kind alone '
            'is a category, not an account', p_exception USING ERRCODE = 'HS400';
    END IF;

    INSERT INTO fulfillment.ticket_event
        (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, before, after)
    SELECT p_tenant_id, v_ticket.outlet_id, p_ticket_id,
           fulfillment.next_ticket_sequence(p_tenant_id, p_ticket_id), 'served',
           'staff', p_collected_by, o.correlation_id,
           jsonb_build_object('served', false),
           jsonb_build_object('id', gen_random_uuid(),
                              'collected_by_user_id', p_collected_by,
                              'collected_at', coalesce(v_ticket.collected_at, now()),
                              'served_by_user_id', p_served_by,
                              'served_at', CASE WHEN p_served_by IS NOT NULL THEN now() END,
                              'exception_kind', p_exception,
                              'exception_note', p_exception_note)
      FROM ordering.customer_order o
     WHERE o.id = v_ticket.order_id AND o.tenant_id = p_tenant_id
    RETURNING id INTO v_event;

    PERFORM fulfillment.apply_ticket_event(v_event);
END;
$$;

-- FR-FUL-016A. Rework, remake and service waste.
CREATE FUNCTION fulfillment.record_waste(
    p_tenant_id uuid, p_ticket_id uuid, p_kind fulfillment.waste_kind,
    p_units integer, p_reason_code_id uuid, p_user_id uuid, p_note text) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_ticket fulfillment.ticket%ROWTYPE;
    v_event  bigint;
BEGIN
    SELECT * INTO v_ticket FROM fulfillment.ticket
     WHERE id = p_ticket_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TICKET_NOT_FOUND: no ticket % in scope', p_ticket_id
            USING ERRCODE = 'HS404';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM config.reason_code
                    WHERE id = p_reason_code_id AND tenant_id = p_tenant_id
                      AND category = 'service_failure' AND status = 'active') THEN
        RAISE EXCEPTION
            'WASTE_REASON_INVALID: % is not an active service_failure reason code',
            p_reason_code_id USING ERRCODE = 'HS400';
    END IF;

    IF btrim(coalesce(p_note, '')) = '' THEN
        RAISE EXCEPTION
            'WASTE_UNEXPLAINED: a % event says what happened in words', p_kind
            USING ERRCODE = 'HS400';
    END IF;

    INSERT INTO fulfillment.ticket_event
        (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, reason_code_id, before, after)
    SELECT p_tenant_id, v_ticket.outlet_id, p_ticket_id,
           fulfillment.next_ticket_sequence(p_tenant_id, p_ticket_id), 'waste',
           'staff', p_user_id, o.correlation_id, p_reason_code_id,
           jsonb_build_object('recorded', false),
           jsonb_build_object('id', gen_random_uuid(), 'order_id', v_ticket.order_id,
                              'kind', p_kind, 'units_affected', p_units, 'note', p_note)
      FROM ordering.customer_order o
     WHERE o.id = v_ticket.order_id AND o.tenant_id = p_tenant_id
    RETURNING id INTO v_event;

    PERFORM fulfillment.apply_ticket_event(v_event);
END;
$$;


-- ===========================================================================
-- Expo (FR-FUL-009) and service readiness
-- ===========================================================================
-- An order fans out; expo puts it back together. The blocking rule is the requirement:
-- an incomplete set does not go to a table, because half a table's food arriving is how
-- the other half arrives cold.

CREATE FUNCTION fulfillment.expo_view(p_tenant_id uuid, p_order_id uuid)
RETURNS TABLE (ticket_id uuid, station_node_id uuid,
               station_kind fulfillment.station_kind,
               state fulfillment.ticket_state, priority fulfillment.priority_level,
               units integer, ready_units integer, sla_due_at timestamptz,
               allergy_declarations integer, allergy_acknowledged boolean)
LANGUAGE sql STABLE
AS $$
    SELECT t.id, t.station_node_id, sp.station_kind, t.state, t.priority,
           coalesce(sum(tl.quantity)::integer, 0),
           coalesce(sum(tl.ready_quantity)::integer, 0),
           t.sla_due_at,
           ordering.order_allergy_declaration_count(t.tenant_id, t.order_id),
           t.allergy_acknowledged_at IS NOT NULL
    FROM fulfillment.ticket t
    JOIN fulfillment.station_profile sp
      ON sp.tenant_id = t.tenant_id AND sp.station_node_id = t.station_node_id
    LEFT JOIN fulfillment.ticket_line tl ON tl.ticket_id = t.id
    WHERE t.tenant_id = p_tenant_id AND t.order_id = p_order_id
    GROUP BY t.id, t.station_node_id, sp.station_kind, t.state, t.priority, t.sla_due_at,
             t.order_id, t.tenant_id, t.allergy_acknowledged_at
    ORDER BY t.station_sequence;
$$;

-- Whether the set may be released to the floor, and if not, why not. Returns a reason
-- rather than a boolean: "not yet" without a reason is what makes an expo screen an
-- obstacle rather than a tool.
CREATE FUNCTION fulfillment.service_block_reasons(p_tenant_id uuid, p_order_id uuid)
RETURNS TABLE (reason text, ticket_id uuid, detail text)
LANGUAGE sql STABLE
AS $$
    SELECT 'incomplete_set', t.id,
           'ticket at station ' || t.station_node_id || ' is ' || t.state::text
    FROM fulfillment.ticket t
    WHERE t.tenant_id = p_tenant_id AND t.order_id = p_order_id
      AND t.state NOT IN ('ready', 'collected', 'completed', 'cancelled')
    UNION ALL
    SELECT 'partial_units', t.id,
           (SELECT sum(tl.ready_quantity)::text || ' of ' || sum(tl.quantity)::text
              || ' unit(s) ready'
            FROM fulfillment.ticket_line tl WHERE tl.ticket_id = t.id)
    FROM fulfillment.ticket t
    WHERE t.tenant_id = p_tenant_id AND t.order_id = p_order_id
      AND t.state = 'ready'
      AND EXISTS (SELECT 1 FROM fulfillment.ticket_line tl
                   WHERE tl.ticket_id = t.id AND tl.ready_quantity < tl.quantity)
    UNION ALL
    -- FR-FUL-008 reaching service: a ticket carrying an allergy declaration that the
    -- station never acknowledged does not go out, where the station requires it.
    SELECT 'allergy_unacknowledged', t.id,
           'the station requires acknowledgement and none is recorded'
    FROM fulfillment.ticket t
    JOIN fulfillment.station_profile sp
      ON sp.tenant_id = t.tenant_id AND sp.station_node_id = t.station_node_id
    WHERE t.tenant_id = p_tenant_id AND t.order_id = p_order_id
      AND t.state <> 'cancelled'
      AND sp.allergy_acknowledgement_required
      AND t.allergy_acknowledged_at IS NULL
      AND ordering.order_allergy_declaration_count(t.tenant_id, t.order_id) > 0
    ORDER BY 1, 2;
$$;

CREATE FUNCTION fulfillment.release_to_service(
    p_tenant_id uuid, p_order_id uuid, p_collected_by uuid) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_block record;
    v_ticket record;
    v_count integer := 0;
BEGIN
    FOR v_block IN
        SELECT * FROM fulfillment.service_block_reasons(p_tenant_id, p_order_id)
    LOOP
        RAISE EXCEPTION
            'INCOMPLETE_SET_NOT_RELEASED: order % is blocked from service — % (%)',
            p_order_id, v_block.reason, v_block.detail USING ERRCODE = 'HS409';
    END LOOP;

    FOR v_ticket IN
        SELECT id FROM fulfillment.ticket
         WHERE tenant_id = p_tenant_id AND order_id = p_order_id AND state = 'ready'
         ORDER BY station_sequence
    LOOP
        PERFORM fulfillment.transition_ticket(p_tenant_id, v_ticket.id, 'collected',
                                              p_collected_by);
        v_count := v_count + 1;
    END LOOP;

    IF v_count = 0 THEN
        RAISE EXCEPTION
            'NOTHING_TO_RELEASE: order % has no ready ticket to collect', p_order_id
            USING ERRCODE = 'HS409';
    END IF;
    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION fulfillment.release_to_service(uuid, uuid, uuid) IS
    'FR-FUL-009. The blocking half: it asks service_block_reasons() first and refuses on '
    'the first reason there is, so an incomplete set cannot leave the pass. The reasons '
    'are a function of their own so the expo SCREEN shows the same answer the refusal '
    'gives, rather than a second opinion about readiness.';


-- ===========================================================================
-- Timing and capacity (FR-FUL-012, FR-FUL-013) — and FR-ORD-006's fifth dimension
-- ===========================================================================

CREATE FUNCTION fulfillment.station_load(p_tenant_id uuid, p_station_node_id uuid)
RETURNS integer
LANGUAGE sql STABLE
AS $$
    SELECT count(*)::integer FROM fulfillment.ticket
    WHERE tenant_id = p_tenant_id AND station_node_id = p_station_node_id
      AND state IN ('queued', 'acknowledged', 'held', 'preparing', 'partially_completed');
$$;

-- FR-FUL-012. Prep and wait time per station, item and order, from the timestamps the
-- fold wrote out of the ledger — so these are measurements, not estimates.
CREATE FUNCTION fulfillment.ticket_timings(p_tenant_id uuid, p_order_id uuid)
RETURNS TABLE (ticket_id uuid, station_node_id uuid,
               queued_seconds integer, preparation_seconds integer,
               wait_seconds integer, sla_breached boolean)
LANGUAGE sql STABLE
AS $$
    SELECT t.id, t.station_node_id,
           CASE WHEN t.acknowledged_at IS NOT NULL
                THEN floor(extract(epoch FROM t.acknowledged_at - t.released_at))::integer END,
           CASE WHEN t.ready_at IS NOT NULL AND t.preparation_started_at IS NOT NULL
                THEN floor(extract(epoch FROM t.ready_at - t.preparation_started_at))::integer END,
           CASE WHEN t.collected_at IS NOT NULL AND t.ready_at IS NOT NULL
                THEN floor(extract(epoch FROM t.collected_at - t.ready_at))::integer END,
           CASE WHEN t.sla_due_at IS NULL THEN NULL
                ELSE coalesce(t.ready_at, now()) > t.sla_due_at END
    FROM fulfillment.ticket t
    WHERE t.tenant_id = p_tenant_id AND t.order_id = p_order_id
    ORDER BY t.station_sequence;
$$;

-- FR-FUL-013, and the dimension FR-ORD-006 has been waiting for since M3-A. Returns the
-- stations that are over their configured threshold, with what the policy says to do
-- about it. An outlet whose service policy says nothing gets a refusal, not a default:
-- throttling somebody did not ask for is as wrong as not throttling when they did.
CREATE FUNCTION fulfillment.capacity_pressure(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (station_node_id uuid, load integer, threshold integer,
               response text, promise_extension_minutes integer)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_policy jsonb;
BEGIN
    -- Asked ONLY when there is pressure to respond to. Requiring the service policy up
    -- front made configuring one a precondition for taking any order at all, because
    -- ordering.revalidate_cart() calls this on every submission: an outlet with no
    -- station thresholds set was refused its own orders. Nothing over threshold means
    -- nothing to decide, and a question nobody needs answered must not be a barrier.
    IF NOT EXISTS (
        SELECT 1 FROM fulfillment.station_profile sp
         WHERE sp.tenant_id = p_tenant_id AND sp.outlet_id = p_outlet_id
           AND sp.status = 'active'
           AND sp.concurrent_ticket_threshold IS NOT NULL
           AND fulfillment.station_load(p_tenant_id, sp.station_node_id)
               >= sp.concurrent_ticket_threshold) THEN
        RETURN;
    END IF;

    -- There IS pressure, so the response is now a decision somebody has to have made.
    v_policy := ordering.require_policy(p_tenant_id, p_outlet_id, 'service');
    IF NOT (v_policy ? 'capacity_response') THEN
        RAISE EXCEPTION
            'SERVICE_POLICY_INCOMPLETE: the service policy for outlet % states no '
            'capacity_response; FR-FUL-013 offers throttling OR promise-time adjustment '
            'and which one is a commercial decision, not a default', p_outlet_id
            USING ERRCODE = 'HS412';
    END IF;

    RETURN QUERY
    SELECT sp.station_node_id,
           fulfillment.station_load(p_tenant_id, sp.station_node_id),
           sp.concurrent_ticket_threshold,
           v_policy ->> 'capacity_response',
           nullif(v_policy ->> 'promise_extension_minutes', '')::integer
    FROM fulfillment.station_profile sp
    WHERE sp.tenant_id = p_tenant_id AND sp.outlet_id = p_outlet_id
      AND sp.status = 'active'
      AND sp.concurrent_ticket_threshold IS NOT NULL
      AND fulfillment.station_load(p_tenant_id, sp.station_node_id)
          >= sp.concurrent_ticket_threshold
    ORDER BY sp.station_node_id;
END;
$$;


-- ===========================================================================
-- The order's fulfillment state, DERIVED (SM-ORDER's semantics)
-- ===========================================================================
-- Every label SM-ORDER names for the fulfillment span of an order's life, computed from
-- the tickets rather than stored beside them. tests/m3b proves each label is reachable
-- and correct, and asserts against the catalog that no column anywhere in ordering could
-- hold one — the same shape of proof M3-A used for the absent table id.

CREATE FUNCTION fulfillment.order_fulfillment_state(p_tenant_id uuid, p_order_id uuid)
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
BEGIN
    SELECT count(*) FILTER (WHERE state <> 'cancelled'),
           count(*) FILTER (WHERE state IN ('queued', 'acknowledged', 'held', 'preparing',
                                            'partially_completed', 'rework', 'exception')),
           -- COLLECTED counts with ready, not with served. A ticket that left the pass is
           -- on its way to the table; SM-FULFILLMENT-TICKET is explicit that service is
           -- confirmed at collected -> completed, so treating collection as service would
           -- report an order served while it was still in somebody's hands. Written the
           -- other way first, and the smoke test said 'served' for a plate in transit.
           count(*) FILTER (WHERE state IN ('ready', 'collected')),
           count(*) FILTER (WHERE state = 'collected'),
           count(*) FILTER (WHERE state = 'completed')
      INTO v_total, v_live, v_ready, v_collected, v_served
      FROM fulfillment.ticket
     WHERE tenant_id = p_tenant_id AND order_id = p_order_id;

    IF v_total IS NULL OR v_total = 0 THEN
        RETURN 'not_released';
    END IF;

    IF v_served = v_total THEN RETURN 'served'; END IF;
    IF v_served > 0 THEN RETURN 'partially_served'; END IF;
    IF v_ready = v_total THEN RETURN 'ready'; END IF;
    IF v_ready > 0 THEN RETURN 'partially_ready'; END IF;

    -- Partial readiness WITHIN a ticket counts too: three of four skewers ready is
    -- partially ready even though no ticket has reached the ready state.
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
    'SM-ORDER''s fulfillment labels — in_fulfillment, partially_ready, ready, '
    'partially_served, served — computed from the order''s tickets. A literal divergence '
    'from that machine''s state LIST, preserving its semantics: the labels are all '
    'answerable, and refusing to store them means a ticket transition cannot leave the '
    'order saying something its tickets contradict.';


-- ===========================================================================
-- What a station reads (FR-FUL-003, FR-FUL-008, FR-SAF-004)
-- ===========================================================================
-- FR-FUL-003's SEVEN display buckets over the package's ELEVEN states. The mapping is
-- here, once, so the KDS screen and any other reader group them the same way — and so
-- the reconciliation between the brief's seven and the package's eleven is a function
-- somebody can read rather than a paragraph somebody has to remember.

CREATE FUNCTION fulfillment.kds_bucket(p_state fulfillment.ticket_state)
RETURNS text
LANGUAGE sql IMMUTABLE
AS $$
    SELECT CASE p_state
        WHEN 'queued'              THEN 'new'
        WHEN 'acknowledged'        THEN 'acknowledged'
        WHEN 'held'                THEN 'held'
        WHEN 'preparing'           THEN 'preparing'
        WHEN 'partially_completed' THEN 'preparing'
        WHEN 'rework'              THEN 'preparing'
        WHEN 'ready'               THEN 'ready'
        WHEN 'collected'           THEN 'completed'
        WHEN 'completed'           THEN 'completed'
        WHEN 'cancelled'           THEN 'completed'
        WHEN 'exception'           THEN 'exception'
    END;
$$;

COMMENT ON FUNCTION fulfillment.kds_bucket(fulfillment.ticket_state) IS
    'FR-FUL-003 lists seven states a KDS shows; SM-FULFILLMENT-TICKET defines eleven the '
    'machine has. These are the seven display buckets over those eleven, and "new" is '
    'the package''s "queued". A CASE with no ELSE, so an unmapped state raises rather '
    'than falling into a column nobody chose.';

-- The queue one station reads. Everything FR-FUL-003 asks for — the bucket, elapsed and
-- SLA time — plus the two things FR-FUL-008 and FR-FUL-007 put on the same screen.
CREATE FUNCTION fulfillment.kds_queue(p_tenant_id uuid, p_station_node_id uuid)
RETURNS TABLE (ticket_id uuid, order_number text, bucket text,
               state fulfillment.ticket_state, priority fulfillment.priority_level,
               priority_reason text, priority_by text,
               elapsed_seconds integer, sla_due_at timestamptz, sla_breached boolean,
               units integer, ready_units integer,
               allergy_count integer, allergy_acknowledged boolean)
LANGUAGE sql STABLE
AS $$
    SELECT t.id, o.order_number, fulfillment.kds_bucket(t.state), t.state, t.priority,
           -- FR-FUL-007: visible attribution, on the same row as the priority it
           -- explains. A rush with no name beside it is the thing the requirement forbids.
           (SELECT rc.code FROM fulfillment.priority_change pc
              JOIN config.reason_code rc ON rc.id = pc.reason_code_id
             WHERE pc.ticket_id = t.id ORDER BY pc.applied_at DESC LIMIT 1),
           (SELECT ua.display_name FROM fulfillment.priority_change pc
              JOIN identity.user_account ua ON ua.id = pc.applied_by_user_id
             WHERE pc.ticket_id = t.id ORDER BY pc.applied_at DESC LIMIT 1),
           floor(extract(epoch FROM now() - t.released_at))::integer,
           t.sla_due_at,
           CASE WHEN t.sla_due_at IS NULL THEN NULL
                ELSE coalesce(t.ready_at, now()) > t.sla_due_at END,
           coalesce((SELECT sum(tl.quantity)::integer FROM fulfillment.ticket_line tl
                      WHERE tl.ticket_id = t.id), 0),
           coalesce((SELECT sum(tl.ready_quantity)::integer FROM fulfillment.ticket_line tl
                      WHERE tl.ticket_id = t.id), 0),
           ordering.order_allergy_declaration_count(t.tenant_id, t.order_id),
           t.allergy_acknowledged_at IS NOT NULL
    FROM fulfillment.ticket t
    JOIN ordering.customer_order o ON o.id = t.order_id AND o.tenant_id = t.tenant_id
    WHERE t.tenant_id = p_tenant_id AND t.station_node_id = p_station_node_id
      AND t.state NOT IN ('completed', 'cancelled')
    -- Priority first, then age. A rush that sorted by age would not be a rush.
    ORDER BY CASE t.priority WHEN 'service_access' THEN 0 WHEN 'rush' THEN 1 ELSE 2 END,
             t.released_at;
$$;

-- FR-SAF-004 and FR-FUL-008: what a station must be shown about an allergy, and how
-- loudly. The EMPHASIS is decided here, in the database, and carried to every surface —
-- so a screen, a document and a handoff cannot each decide for themselves how prominent
-- an allergy is. Every row carries WORDS: there is no representation of an allergy in
-- this system that is a colour, an icon or a rank on its own, which is the guarantee
-- M2-B built by privilege and M2-C proved by rendering.
CREATE FUNCTION fulfillment.ticket_allergy_emphasis(p_tenant_id uuid, p_ticket_id uuid)
RETURNS TABLE (note_id uuid, kitchen_code text, written_warning text,
               acknowledgement_text text, emphasis_rank integer, emphasis_glyph text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, fulfillment, ordering, safety, public
AS $$
    SELECT n.id, a.kitchen_code, n.body, n.acknowledgement_text,
           -- Rank 1 is the top of the ticket. It is an integer AND it travels with the
           -- words; a reader that used the rank alone would be conveying by position,
           -- which is the same defect as conveying by colour.
           1,
           '!!'
    FROM fulfillment.ticket t
    JOIN ordering.order_note n
      ON n.tenant_id = t.tenant_id AND n.order_id = t.order_id
     AND n.kind = 'allergy_declaration'
    JOIN safety.allergen a ON a.id = n.allergen_id
    WHERE t.tenant_id = p_tenant_id AND t.id = p_ticket_id
    ORDER BY a.kitchen_code;
$$;

COMMENT ON FUNCTION fulfillment.ticket_allergy_emphasis(uuid, uuid) IS
    'FR-SAF-004, FR-FUL-008. Every station surface reads its allergy emphasis from here, '
    'so the salience is one decision rather than one per screen. kitchen_code and the '
    'written warning are NOT NULL by the shape of ordering.order_note, so a row can '
    'never reach a surface as a glyph or a rank with no words beside it.';

-- FR-FUL-003 needs the KDS to reach ordering.order_note, on which the application role
-- deliberately holds no SELECT. This is the station's door, and like M3-A's it names its
-- audience rather than taking one as an argument.
CREATE FUNCTION fulfillment.ticket_kitchen_notes(p_tenant_id uuid, p_ticket_id uuid)
RETURNS TABLE (note_id uuid, kind ordering.note_kind, body text, kitchen_code text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, fulfillment, ordering, safety, public
AS $$
    SELECT n.id, n.kind, n.body, a.kitchen_code
    FROM fulfillment.ticket t
    JOIN ordering.order_note n
      ON n.tenant_id = t.tenant_id AND n.order_id = t.order_id
    LEFT JOIN safety.allergen a ON a.id = n.allergen_id
    WHERE t.tenant_id = p_tenant_id AND t.id = p_ticket_id
      AND n.kind IN ('allergy_declaration', 'kitchen_instruction')
    ORDER BY (n.kind = 'allergy_declaration') DESC, n.created_at, n.id;
$$;


-- ===========================================================================
-- The station ticket document (FR-FUL-014)
-- ===========================================================================

CREATE FUNCTION fulfillment.generate_station_document(
    p_tenant_id uuid, p_ticket_id uuid,
    p_trigger fulfillment.document_trigger, p_user_id uuid DEFAULT NULL)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_ticket   fulfillment.ticket%ROWTYPE;
    v_existing fulfillment.station_ticket_document%ROWTYPE;
    v_revision integer;
    v_content  text;
    v_allergy  integer;
    v_id       uuid;
    v_event    bigint;
BEGIN
    SELECT * INTO v_ticket FROM fulfillment.ticket
     WHERE id = p_ticket_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TICKET_NOT_FOUND: no ticket % in scope', p_ticket_id
            USING ERRCODE = 'HS404';
    END IF;

    -- The revision is the ticket's ledger position IGNORING document generation itself.
    -- Using ledger_sequence directly was wrong and the deduplication test caught it in
    -- one line: generating a document appends an event, which bumps ledger_sequence, so
    -- the second request saw a new revision and made a second document. Pressing print
    -- twice is exactly the case FR-FUL-014 exists for.
    SELECT coalesce(max(sequence_number), 0) INTO v_revision
      FROM fulfillment.ticket_event
     WHERE tenant_id = p_tenant_id AND ticket_id = p_ticket_id
       AND kind <> 'document_generated';

    SELECT * INTO v_existing FROM fulfillment.station_ticket_document
     WHERE tenant_id = p_tenant_id AND ticket_id = p_ticket_id AND revision = v_revision;
    IF FOUND THEN
        -- The deduplication, and it RETURNS rather than raising: asking twice is normal
        -- (a station taps print again because the first sheet jammed), and the right
        -- answer is the document that already exists, not a second one and not an error.
        RETURN v_existing.id;
    END IF;

    SELECT count(*)::integer INTO v_allergy
      FROM fulfillment.ticket_allergy_emphasis(p_tenant_id, p_ticket_id);

    -- Allergy lines FIRST and in words, because FR-FUL-008's later_behavior is that the
    -- same salience must survive the printed ticket. Paper has no colour to fall back
    -- on, which is exactly why the emphasis was never allowed to be one.
    SELECT coalesce(string_agg(line, E'\n' ORDER BY ord), '') INTO v_content
    FROM (
        SELECT 0 AS ord, '*** ALLERGY: ' || upper(e.kitchen_code) || ' — '
               || e.written_warning || ' ***' AS line
        FROM fulfillment.ticket_allergy_emphasis(p_tenant_id, p_ticket_id) e
        UNION ALL
        SELECT 1, 'TICKET ' || v_ticket.id::text || '  rev ' || v_revision::text
        UNION ALL
        SELECT 2, 'ORDER ' || o.order_number || '  priority ' || v_ticket.priority::text
        FROM ordering.customer_order o WHERE o.id = v_ticket.order_id
        UNION ALL
        SELECT 3, tl.quantity::text || ' x ' || tl.canonical_name || ' (' || tl.item_code || ')'
        FROM fulfillment.ticket_line tl WHERE tl.ticket_id = p_ticket_id
    ) AS rendered;

    v_id := gen_random_uuid();

    INSERT INTO fulfillment.ticket_event
        (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, before, after)
    SELECT p_tenant_id, v_ticket.outlet_id, p_ticket_id,
           fulfillment.next_ticket_sequence(p_tenant_id, p_ticket_id),
           'document_generated',
           CASE WHEN p_user_id IS NOT NULL THEN 'staff' ELSE 'system' END
               ::ordering.actor_kind,
           p_user_id, o.correlation_id,
           jsonb_build_object('generated', false),
           jsonb_build_object('id', v_id, 'revision', v_revision,
                              'trigger_reason', p_trigger, 'content', v_content,
                              'content_digest',
                              encode(sha256(convert_to(v_content, 'UTF8')), 'hex'),
                              'allergy_line_count', v_allergy)
      FROM ordering.customer_order o
     WHERE o.id = v_ticket.order_id AND o.tenant_id = p_tenant_id
    RETURNING id INTO v_event;

    PERFORM fulfillment.apply_ticket_event(v_event);
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION fulfillment.generate_station_document IS
    'FR-FUL-014. Deduplicated on (ticket, revision): a second request for an unchanged '
    'ticket returns the document that exists rather than making another, and the unique '
    'constraint would refuse one even if this function forgot. A paper ticket printed '
    'twice is a dish cooked twice.';


-- FR-FUL-010's half: the ready notice, emitted when a ticket becomes ready and escalated
-- when nobody collects it. Called from the transition path rather than by a caller who
-- might forget.
CREATE FUNCTION fulfillment.emit_ready_notice(p_tenant_id uuid, p_ticket_id uuid)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, fulfillment, ordering, service, public
AS $$
DECLARE
    v_ticket fulfillment.ticket%ROWTYPE;
    v_owner  uuid;
BEGIN
    SELECT * INTO v_ticket FROM fulfillment.ticket
     WHERE id = p_ticket_id AND tenant_id = p_tenant_id;
    IF NOT FOUND OR v_ticket.ready_at IS NULL THEN
        RETURN;
    END IF;

    -- M2-B's table ownership answers "whose table is this". Absent is absent: a notice
    -- with an invented recipient is worse than one addressed to nobody.
    -- M2-B's ownership record is keyed on the SESSION, not the table, and an open
    -- assignment is one whose effective_to is still NULL. Written against the table as
    -- it is rather than as it was assumed to be: the first attempt joined on a
    -- table_node_id this table does not have.
    SELECT tow.primary_waiter_user_id INTO v_owner
      FROM ordering.customer_order o
      JOIN service.table_ownership tow
        ON tow.tenant_id = o.tenant_id AND tow.table_session_id = o.table_session_id
       AND tow.effective_to IS NULL
     WHERE o.id = v_ticket.order_id AND o.tenant_id = p_tenant_id
     ORDER BY tow.assigned_at DESC
     LIMIT 1;

    PERFORM set_config('fulfillment.applying_event', 'yes', true);
    INSERT INTO fulfillment.ready_notice
        (id, tenant_id, outlet_id, ticket_id, assigned_user_id, became_ready_at)
    VALUES (uuid_in(md5('ready' || p_tenant_id::text || p_ticket_id::text)::cstring),
            p_tenant_id, v_ticket.outlet_id, p_ticket_id, v_owner, v_ticket.ready_at)
    ON CONFLICT (tenant_id, ticket_id) DO NOTHING;
    PERFORM set_config('fulfillment.applying_event', '', true);
END;
$$;

-- Escalation: uncollected past the configured window. A sweep, like M1-C's retention,
-- rather than a timer nobody can inspect.
CREATE FUNCTION fulfillment.escalate_uncollected(p_tenant_id uuid, p_outlet_id uuid)
RETURNS integer
-- SECURITY DEFINER for the same reason emit_ready_notice() is: it writes a PROJECTION,
-- and the application role holds SELECT on projections and nothing more. The projection
-- guard is unaffected — this function sets the marker the same way the fold does, so the
-- write still has to come from code that says it is applying an event.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, fulfillment, ordering, config, public
AS $$
DECLARE
    v_policy jsonb := ordering.require_policy(p_tenant_id, p_outlet_id, 'service');
    v_after  integer;
    v_count  integer := 0;
BEGIN
    IF NOT (v_policy ? 'collection_escalation_seconds') THEN
        RAISE EXCEPTION
            'SERVICE_POLICY_INCOMPLETE: the service policy states no '
            'collection_escalation_seconds; food goes cold on a schedule somebody chose'
            USING ERRCODE = 'HS412';
    END IF;
    v_after := (v_policy ->> 'collection_escalation_seconds')::integer;

    PERFORM set_config('fulfillment.applying_event', 'yes', true);
    WITH escalated AS (
        UPDATE fulfillment.ready_notice rn
           SET escalated_at = now(), escalation_after_seconds = v_after
          FROM fulfillment.ticket t
         WHERE t.id = rn.ticket_id AND rn.tenant_id = p_tenant_id
           AND rn.outlet_id = p_outlet_id
           AND rn.escalated_at IS NULL
           AND t.state = 'ready'
           AND rn.became_ready_at < now() - make_interval(secs => v_after)
        RETURNING rn.id)
    SELECT count(*)::integer INTO v_count FROM escalated;
    PERFORM set_config('fulfillment.applying_event', '', true);

    RETURN v_count;
END;
$$;


-- ===========================================================================
-- Rebuild (FR-DAT-010, extended to fulfillment)
-- ===========================================================================

CREATE FUNCTION fulfillment.projection_digest(p_tenant_id uuid) RETURNS bytea
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, fulfillment, public
AS $$
    SELECT sha256(convert_to(coalesce(string_agg(part, E'\n' ORDER BY part), ''), 'UTF8'))
    FROM (
        SELECT 'ticket|' || t.id || '|' || t.order_id || '|' || t.station_node_id || '|'
               || t.state || '|' || t.priority || '|' || t.routing_rule_set_id || '|'
               || t.station_sequence || '|' || t.released_at || '|'
               || coalesce(t.sla_due_at::text, '-') || '|'
               || coalesce(t.acknowledged_at::text, '-') || '|'
               || coalesce(t.preparation_started_at::text, '-') || '|'
               || coalesce(t.ready_at::text, '-') || '|'
               || coalesce(t.collected_at::text, '-') || '|'
               || coalesce(t.completed_at::text, '-') || '|'
               || coalesce(t.allergy_acknowledged_at::text, '-') || '|'
               || coalesce(t.allergy_acknowledged_by_user_id::text, '-') || '|'
               || t.ledger_sequence AS part
        FROM fulfillment.ticket t WHERE t.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'ticket_line|' || l.id || '|' || l.ticket_id || '|' || l.order_line_id || '|'
               || l.quantity || '|' || l.ready_quantity || '|' || l.item_code || '|'
               || l.canonical_name
        FROM fulfillment.ticket_line l WHERE l.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'priority|' || p.id || '|' || p.ticket_id || '|' || p.from_priority || '|'
               || p.to_priority || '|' || p.reason_code_id || '|' || p.applied_by_user_id
               || '|' || p.applied_at
        FROM fulfillment.priority_change p WHERE p.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'recall|' || r.id || '|' || r.ticket_id || '|' || r.recalled_from || '|'
               || r.reason_code_id || '|' || r.recalled_by_user_id || '|' || r.recalled_at
        FROM fulfillment.ticket_recall r WHERE r.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'transfer|' || x.id || '|' || x.ticket_id || '|' || x.from_station_node_id
               || '|' || x.to_station_node_id || '|' || x.units_moved || '|' || x.transferred_at
        FROM fulfillment.station_transfer x WHERE x.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'serve|' || s.id || '|' || s.ticket_id || '|' || s.collected_by_user_id
               || '|' || s.collected_at || '|' || coalesce(s.served_by_user_id::text, '-')
               || '|' || coalesce(s.served_at::text, '-') || '|'
               || coalesce(s.exception_kind::text, '-') || '|'
               || coalesce(s.exception_note, '-')
        FROM fulfillment.serve_record s WHERE s.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'waste|' || w.id || '|' || w.ticket_id || '|' || w.kind || '|'
               || w.units_affected || '|' || w.reason_code_id || '|' || w.recorded_at
               || '|' || w.note
        FROM fulfillment.waste_event w WHERE w.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'document|' || d.id || '|' || d.ticket_id || '|' || d.revision || '|'
               || d.trigger_reason || '|' || encode(d.content_digest, 'hex') || '|'
               || d.allergy_line_count || '|' || d.generated_at
        FROM fulfillment.station_ticket_document d WHERE d.tenant_id = p_tenant_id
    ) AS rendered;
$$;

CREATE FUNCTION fulfillment.rebuild_projections(p_tenant_id uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, fulfillment, public
AS $$
DECLARE
    v_event bigint;
    v_count integer := 0;
BEGIN
    PERFORM set_config('fulfillment.applying_event', 'yes', true);
    DELETE FROM fulfillment.station_ticket_document WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.waste_event WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.serve_record WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.station_transfer WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.ticket_recall WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.priority_change WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.ready_notice WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.ticket_line WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.ticket WHERE tenant_id = p_tenant_id;
    PERFORM set_config('fulfillment.applying_event', '', true);

    FOR v_event IN
        SELECT id FROM fulfillment.ticket_event WHERE tenant_id = p_tenant_id ORDER BY id
    LOOP
        PERFORM fulfillment.apply_ticket_event(v_event);
        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$;

-- FR-ORD-016A closes here, and the rebuild is why. M3-A's rebuild discards every order
-- timeline entry and replays the ORDER ledger; station entries come from the FULFILLMENT
-- ledger, so without this they would vanish on the first rebuild and NC-M3-009 would go
-- red for a correct system. Replaying both is what makes one timeline out of two ledgers.
CREATE OR REPLACE FUNCTION ordering.rebuild_projections(p_tenant_id uuid) RETURNS integer
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
    -- Tickets reference order lines, so the fulfillment projections come down first and
    -- are rebuilt below. The two ledgers are untouched throughout; only projections move.
    PERFORM fulfillment.drop_projections_for_rebuild(p_tenant_id);
    DELETE FROM ordering.order_line WHERE tenant_id = p_tenant_id;
    DELETE FROM ordering.customer_order WHERE tenant_id = p_tenant_id;

    PERFORM set_config('ordering.applying_event', '', true);

    FOR v_event IN
        SELECT id FROM ordering.order_event WHERE tenant_id = p_tenant_id ORDER BY id
    LOOP
        PERFORM ordering.apply_event(v_event);
        v_count := v_count + 1;
    END LOOP;

    -- Then the fulfillment ledger, which restores the tickets AND the station half of
    -- the order timeline through ordering.write_station_timeline_entry().
    FOR v_event IN
        SELECT id FROM fulfillment.ticket_event WHERE tenant_id = p_tenant_id ORDER BY id
    LOOP
        PERFORM fulfillment.apply_ticket_event(v_event);
        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$;

CREATE FUNCTION fulfillment.drop_projections_for_rebuild(p_tenant_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, fulfillment, public
AS $$
BEGIN
    PERFORM set_config('fulfillment.applying_event', 'yes', true);
    DELETE FROM fulfillment.station_ticket_document WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.waste_event WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.serve_record WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.station_transfer WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.ticket_recall WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.priority_change WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.ready_notice WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.ticket_line WHERE tenant_id = p_tenant_id;
    DELETE FROM fulfillment.ticket WHERE tenant_id = p_tenant_id;
    PERFORM set_config('fulfillment.applying_event', '', true);
END;
$$;


-- ===========================================================================
-- FR-ORD-006 closes: the fifth dimension arrives (partial closure #1)
-- ===========================================================================
-- M3-A revalidated availability, hours, channel and quantity at submission and recorded
-- station capacity as the half it could not check, naming M3-B. Here it is.
--
-- Replaced rather than edited: migration 0010 is checksum-locked and forward-only, so
-- the way to change a function it created is CREATE OR REPLACE in a later migration, not
-- a rewrite of a file the history has already applied.
CREATE OR REPLACE FUNCTION ordering.revalidate_cart(
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
                       AND (v_local >= dp.starts_at_local OR v_local < dp.ends_at_local))))

    UNION ALL
    -- FR-ORD-006's FIFTH dimension, added here at M3-B. Capacity means station workload,
    -- and fulfillment.capacity_pressure() reads the configured threshold and the
    -- configured response, refusing outright when the outlet's service policy states
    -- neither.
    --
    -- Reported as a block ONLY where the policy says to throttle. FR-FUL-013 offers
    -- throttling OR promise-time adjustment, and an outlet that chose to extend its
    -- promise time has chosen to keep taking orders — turning that into a refusal here
    -- would override a commercial decision with an implementation detail.
    SELECT 'capacity'::text, cp.station_node_id,
           'station ' || cp.station_node_id || ' has ' || cp.load
           || ' live ticket(s) against a threshold of ' || cp.threshold
           || '; the service policy says ' || cp.response
    FROM fulfillment.capacity_pressure(p_tenant_id, p_outlet_id) cp
    WHERE cp.response = 'throttle'
      AND EXISTS (SELECT 1 FROM service.cart_line cl
                   WHERE cl.cart_id = p_cart_id AND cl.tenant_id = p_tenant_id);
END;
$$;

COMMENT ON FUNCTION ordering.revalidate_cart(uuid, uuid, uuid, menu.sales_channel, timestamptz) IS
    'FR-ORD-006. Availability, hours, channel, quantity AND station capacity re-checked '
    'at submission, because a preview is not a reservation. Capacity was the fifth '
    'dimension and it waited for the stations M3-B builds; it closed there, and the '
    'register entry that held it open closed with it.';


-- ===========================================================================
-- FR-ORD-010 closes: preparation progress is now askable (partial closure #2)
-- ===========================================================================
-- M3-A emitted amendment events with before and after and bounded the window by the
-- COMMERCIAL state, because that was the only state there was. The requirement says
-- "allowed pre-preparation changes", and preparation is a ticket state — so the window
-- was half-enforced and recorded as such. Replaced, not edited: 0010 is checksum-locked.
CREATE OR REPLACE FUNCTION ordering.amend_order_line(
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

    -- FR-ORD-010's other half, which M3-A recorded as a partial closure because it had no
    -- ticket state to ask. "Allowed PRE-PREPARATION changes" is now checkable against the
    -- thing that actually knows: a station that has started work. The commercial state
    -- alone was never enough — an order can sit in a state the policy permits while a
    -- kitchen is already cooking it.
    IF EXISTS (SELECT 1 FROM fulfillment.ticket t
                WHERE t.tenant_id = p_tenant_id AND t.order_id = p_order_id
                  AND t.state NOT IN ('queued', 'acknowledged', 'held', 'cancelled')) THEN
        RAISE EXCEPTION
            'AMENDMENT_AFTER_PREPARATION: order % has a ticket a station has already '
            'started; changing it now changes something that is being made',
            p_order_id USING ERRCODE = 'HS409';
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
    'because ordering.apply_event() replaces rather than patches — an amendment that '
    'silently dropped an allergy declaration is exactly NC-M3-003. The window is bounded '
    'by the ordering policy AND by whether a station has begun: M3-B closed the second '
    'half, which M3-A could only record as waiting.';


-- ===========================================================================
-- Acceptance releases the work (FR-FUL-001, FR-ORD-007A carried forward)
-- ===========================================================================
-- An accepted order becomes work at a station. Wired to the ledger rather than to the
-- acceptance FUNCTION, because M3-A has two paths to acceptance — automatic inside
-- submit_order() and staff-confirmed through accept_order() — and a hook on one of them
-- would have released half the orders in the building.
--
-- AFTER INSERT on the ledger, so it fires however the acceptance event got there,
-- including during a rebuild. A rebuild must NOT re-release: the tickets come back from
-- the fulfillment ledger, so this checks first.

CREATE FUNCTION ordering.release_accepted_order() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, ordering, fulfillment, public
AS $$
BEGIN
    IF NEW.kind <> 'accepted' THEN
        RETURN NULL;
    END IF;

    -- During a rebuild the tickets are replayed from their own ledger, and re-releasing
    -- would both duplicate the work and write ledger rows a replay must never write.
    IF EXISTS (SELECT 1 FROM fulfillment.ticket_event
                WHERE tenant_id = NEW.tenant_id
                  AND ticket_id IN (SELECT id FROM fulfillment.ticket
                                     WHERE tenant_id = NEW.tenant_id
                                       AND order_id = NEW.order_id))
       OR EXISTS (SELECT 1 FROM fulfillment.ticket_event te
                   WHERE te.tenant_id = NEW.tenant_id
                     AND te.kind = 'released'
                     AND te.after -> 'ticket' ->> 'order_id' = NEW.order_id::text) THEN
        RETURN NULL;
    END IF;

    -- An outlet with no routing rules yet is not an error at acceptance: the order stands
    -- and the work is released when the rules exist. Refusing here would make accepting
    -- an order depend on a configuration the customer has nothing to do with.
    IF fulfillment.effective_rule_set(NEW.tenant_id, NEW.outlet_id) IS NULL THEN
        RETURN NULL;
    END IF;

    PERFORM fulfillment.release_order(NEW.tenant_id, NEW.order_id, NEW.actor_user_id);
    RETURN NULL;
END;
$$;

-- FR-ORD-010's permitted half, reaching the stations. ordering.amend_order_line()
-- refuses outright once a station has started; while every ticket is still queued,
-- acknowledged or held the amendment stands, and the tickets have to say what the guest
-- now ordered. Written as its own function so the trigger below is one line of intent.
CREATE FUNCTION fulfillment.apply_order_amendment(
    p_tenant_id uuid, p_order_id uuid, p_actor_user_id uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, fulfillment, ordering, public
AS $$
DECLARE
    v_ticket record;
    v_lines  jsonb;
    v_event  bigint;
    v_count  integer := 0;
BEGIN
    FOR v_ticket IN
        SELECT t.* FROM fulfillment.ticket t
         WHERE t.tenant_id = p_tenant_id AND t.order_id = p_order_id
           AND t.state NOT IN ('cancelled', 'completed')
         ORDER BY t.station_sequence
    LOOP
        SELECT jsonb_agg(jsonb_build_object('id', tl.id, 'quantity', ol.quantity)
                         ORDER BY tl.id)
          INTO v_lines
          FROM fulfillment.ticket_line tl
          JOIN ordering.order_line ol
            ON ol.tenant_id = tl.tenant_id AND ol.id = tl.order_line_id
         WHERE tl.ticket_id = v_ticket.id AND tl.quantity <> ol.quantity;

        CONTINUE WHEN v_lines IS NULL;

        INSERT INTO fulfillment.ticket_event
            (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
             actor_user_id, correlation_id, before, after)
        SELECT p_tenant_id, v_ticket.outlet_id, v_ticket.id,
               fulfillment.next_ticket_sequence(p_tenant_id, v_ticket.id), 'amended',
               CASE WHEN p_actor_user_id IS NOT NULL THEN 'staff' ELSE 'guest' END
                   ::ordering.actor_kind,
               p_actor_user_id, o.correlation_id,
               jsonb_build_object('lines', (
                   SELECT jsonb_agg(jsonb_build_object('id', tl.id,
                                                       'quantity', tl.quantity)
                                    ORDER BY tl.id)
                   FROM fulfillment.ticket_line tl WHERE tl.ticket_id = v_ticket.id)),
               jsonb_build_object('lines', v_lines)
          FROM ordering.customer_order o
         WHERE o.id = p_order_id AND o.tenant_id = p_tenant_id
        RETURNING id INTO v_event;

        PERFORM fulfillment.apply_ticket_event(v_event);
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END;
$$;

CREATE FUNCTION ordering.amendment_reaches_stations() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, ordering, fulfillment, public
AS $$
BEGIN
    IF NEW.kind = 'amended' THEN
        PERFORM fulfillment.apply_order_amendment(NEW.tenant_id, NEW.order_id,
                                                  NEW.actor_user_id);
    END IF;
    RETURN NULL;
END;
$$;

-- Deferred for the same reason the release trigger is, and for one more: the order fold
-- REPLACES the order's lines, so until the transaction ends the quantities this reads
-- are the ones being replaced.
CREATE CONSTRAINT TRIGGER order_event_amends_tickets
    AFTER INSERT ON ordering.order_event
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION ordering.amendment_reaches_stations();


-- DEFERRED to the end of the transaction. A plain AFTER INSERT fires while the fold has
-- not yet run, so the order still reads 'submitted' in its projection and release_order()
-- correctly refuses it — the trigger would have been asking a question the transaction
-- had not finished answering. At commit the projection is current.
CREATE CONSTRAINT TRIGGER order_event_releases_work
    AFTER INSERT ON ordering.order_event
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION ordering.release_accepted_order();

-- Ready is where FR-FUL-010's notice is emitted, for the same reason: the transition may
-- be reached from several places and the notice must not depend on which.
CREATE FUNCTION fulfillment.notice_on_ready() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'ready' AND OLD.state IS DISTINCT FROM 'ready' THEN
        PERFORM fulfillment.emit_ready_notice(NEW.tenant_id, NEW.id);
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER ticket_ready_emits_notice
    AFTER UPDATE OF state ON fulfillment.ticket
    FOR EACH ROW EXECUTE FUNCTION fulfillment.notice_on_ready();


-- ===========================================================================
-- Row level security, on the same predicate as everything else
-- ===========================================================================

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'fulfillment.station_profile', 'fulfillment.routing_rule_set',
        'fulfillment.routing_rule', 'fulfillment.ticket_event', 'fulfillment.ticket',
        'fulfillment.ticket_line', 'fulfillment.priority_change',
        'fulfillment.ticket_recall', 'fulfillment.station_transfer',
        'fulfillment.serve_record', 'fulfillment.waste_event',
        'fulfillment.station_ticket_document', 'fulfillment.ready_notice']
    LOOP
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %s FORCE  ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY %I ON %s FOR ALL '
            'USING (app.row_in_scope(tenant_id, outlet_id)) '
            'WITH CHECK (app.row_in_scope(tenant_id, outlet_id))',
            split_part(t, '.', 2) || '_isolation', t);
    END LOOP;
END;
$$;

-- fulfillment.station_profile is outlet-scoped and carries outlet_id, so it uses the
-- same predicate. fulfillment.transition is NOT tenant data at all — it is the pinned
-- machine — so it gets no policy and no tenant column, and the application role reads it
-- and nothing more.


-- ===========================================================================
-- Grants
-- ===========================================================================

GRANT USAGE ON SCHEMA fulfillment TO hospitality_app;

-- The ledger: append and read, never UPDATE or DELETE. The trigger refuses those too.
GRANT SELECT, INSERT ON fulfillment.ticket_event TO hospitality_app;

-- Projections: READ ONLY. Every write goes through fulfillment.apply_ticket_event(),
-- which is SECURITY DEFINER — so the grant and the projection guard are two independent
-- locks rather than one lock described twice, exactly as at M3-A.
GRANT SELECT ON fulfillment.ticket                    TO hospitality_app;
GRANT SELECT ON fulfillment.ticket_line               TO hospitality_app;
GRANT SELECT ON fulfillment.priority_change           TO hospitality_app;
GRANT SELECT ON fulfillment.ticket_recall             TO hospitality_app;
GRANT SELECT ON fulfillment.station_transfer          TO hospitality_app;
GRANT SELECT ON fulfillment.serve_record              TO hospitality_app;
GRANT SELECT ON fulfillment.waste_event               TO hospitality_app;
GRANT SELECT ON fulfillment.station_ticket_document   TO hospitality_app;
GRANT SELECT ON fulfillment.ready_notice              TO hospitality_app;

-- Configuration the pricing and routing paths read and the configuration surface writes;
-- that surface is not built at this gate, so the application role reads only.
GRANT SELECT ON fulfillment.station_profile   TO hospitality_app;
GRANT SELECT ON fulfillment.routing_rule_set  TO hospitality_app;
GRANT SELECT ON fulfillment.routing_rule      TO hospitality_app;

-- The machine itself. SELECT only, for anyone: a state machine an application can
-- rewrite is not a machine, and the trigger above refuses the write regardless.
GRANT SELECT ON fulfillment.transition TO hospitality_app;

GRANT EXECUTE ON FUNCTION fulfillment.apply_ticket_event(bigint)        TO hospitality_app;
GRANT EXECUTE ON FUNCTION fulfillment.rebuild_projections(uuid)         TO hospitality_app;
GRANT EXECUTE ON FUNCTION fulfillment.projection_digest(uuid)           TO hospitality_app;
GRANT EXECUTE ON FUNCTION fulfillment.ticket_allergy_emphasis(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION fulfillment.ticket_kitchen_notes(uuid, uuid)  TO hospitality_app;
GRANT EXECUTE ON FUNCTION fulfillment.emit_ready_notice(uuid, uuid)     TO hospitality_app;
GRANT EXECUTE ON FUNCTION ordering.order_allergy_declaration_count(uuid, uuid)
    TO hospitality_app;

-- The helpers the fold uses are NOT granted: they take a ledger row or write a
-- projection directly, and a caller holding EXECUTE could write a projection for an
-- event that was never in the ledger. apply_ticket_event() reads the event itself.
REVOKE ALL ON FUNCTION fulfillment.drop_projections_for_rebuild(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION ordering.write_station_timeline_entry(
    uuid, uuid, uuid, integer, timestamptz, ordering.event_kind, boolean, text, text)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION ordering.link_correlation_artifact(
    uuid, uuid, uuid, ordering.artifact_kind, uuid, timestamptz) FROM PUBLIC;
-- Reached only from the deferred trigger on ordering.order_event. A caller holding
-- EXECUTE could write an 'amended' ticket event for an amendment the order ledger never
-- recorded, which is the same shape of hole as writing a timeline entry by hand.
REVOKE ALL ON FUNCTION fulfillment.apply_order_amendment(uuid, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION ordering.amendment_reaches_stations() FROM PUBLIC;
