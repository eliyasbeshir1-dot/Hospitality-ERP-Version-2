-- =============================================================================
-- 0014 — Service requests, notifications and the integration runtime (M3-C)
-- =============================================================================
-- A TICKET IS WHAT A STATION MUST MAKE. A SERVICE REQUEST IS WHAT A GUEST ASKED FOR.
--
-- M3-B's header drew the first half of that line; this draws the second. A request for
-- water is not an order line, has no price, reaches no station and produces nothing to
-- cook. It belongs to the TABLE SESSION, which is the only thing a guest who has not
-- ordered yet actually has. Where a request does concern an order — a missing item, a
-- bill — it carries the order as a reference and still is not part of it.
--
-- Three things in this file are worth reading before the rest:
--
--   1. THE MACHINE IS SM-SERVICE-REQUEST'S. Nine states and nine edges, copied from the
--      pinned package into service.transition, and tests/m3c reads state_machines.json at
--      run time and requires the schema to equal it in both directions. The enum below is
--      the package's list verbatim, in the package's order.
--
--   2. DEDUPLICATION IS TWO-SIDED AND BOTH SIDES ARE THE REQUIREMENT. FR-SRV-006 asks for
--      accidental repeated taps to collapse AND deliberate repeats to survive. A window
--      that suppressed everything would satisfy the first half and fail the requirement,
--      so the window is short, configured, and carries an explicit deliberate-repeat
--      escape that a guest can take at any time.
--
--   3. PRESENCE IS NOT A WORKFORCE RECORD. service.staff_presence holds one row per
--      member of staff per outlet, holding the CURRENT state and nothing else. There is
--      no transition history, no previous_state column and no closed row: the model has
--      nowhere to put one. FR-SRV-007B's fence is about what exists, not how long it
--      lasts: a retained history of when somebody was available would be no less an
--      attendance record for having a retention window on it, and there is not one.
-- =============================================================================


-- ===========================================================================
-- Schemas
-- ===========================================================================
-- Service requests extend the SERVICE schema M2-B built, because a request belongs to a
-- table session and that is where table sessions live. Notifications and the integration
-- runtime get their own: FR-INT-007's dead-letter queue is explicitly shared with M4's
-- payment adapters and M5a's synchronization, and a queue that lived inside notify would
-- have to be moved to be shared.

CREATE SCHEMA notify;
CREATE SCHEMA integration;

COMMENT ON SCHEMA notify IS
    'FR-NOT-001 … FR-NOT-012. What happened, who should be told, in which language, and '
    'whether they were told. The CHANNEL is not here: outlet-local notice is M5a, and '
    'this gate sends in-app only.';

COMMENT ON SCHEMA integration IS
    'FR-INT-005, FR-INT-007, FR-INT-014. Idempotency, the dead-letter queue and the '
    'correlation chain''s newest link. Its own schema because M4''s payment adapters and '
    'M5a''s synchronization use the same queue, and a queue inside notify would have to '
    'move before they could.';


-- ===========================================================================
-- SM-SERVICE-REQUEST (the pinned machine)
-- ===========================================================================
-- Nine states, in the package's order. tests/m3c reads state_machines.json and requires
-- this type to equal it exactly, counts included, so a tenth state added to the package
-- without extending this fails the build rather than passing on nine.

CREATE TYPE service.request_state AS ENUM (
    'new', 'routed', 'acknowledged', 'in_progress', 'completed',
    'cancelled', 'expired', 'escalated', 'unresolved');

-- Who raised it. FR-SRV-008's internal tasks are the same aggregate raised by staff:
-- a task linked to a table, an order or a customer issue IS a service request whose
-- origin is staff, and giving it a second table would be two models of one thing.
CREATE TYPE service.request_origin AS ENUM ('guest', 'staff');

CREATE TYPE service.request_event_kind AS ENUM (
    'raised', 'routed', 'acknowledged', 'started', 'completed', 'cancelled',
    'expired', 'escalated', 'unresolved', 'reassigned',
    -- FR-TAB-007A. Two tables become one and the requests come with the session they
    -- were raised on. An EVENT rather than an UPDATE, because a projection changed
    -- behind the ledger's back is a projection a rebuild puts back the way it was —
    -- which is precisely how M3-B's correlation link went missing.
    'session_changed');

-- FR-SRV-005. A request cannot close without saying how it went, and 'not_possible'
-- carries a registered reason rather than a shrug.
CREATE TYPE service.completion_status AS ENUM ('done', 'partially_done', 'not_possible');

-- FR-SRV-007A, the package's three words verbatim. There is no fourth, and there is no
-- 'on_break': break is a fenced term, and no workforce model belongs here.
CREATE TYPE service.presence_state AS ENUM (
    'available', 'temporarily_unavailable', 'offline');


CREATE TABLE service.transition (
    from_state service.request_state NOT NULL,
    to_state   service.request_state NOT NULL,
    reason     text NOT NULL,

    PRIMARY KEY (from_state, to_state),
    CONSTRAINT service_transition_is_a_move CHECK (from_state <> to_state),
    CONSTRAINT service_transition_reason_not_blank CHECK (btrim(reason) <> '')
);

COMMENT ON TABLE service.transition IS
    'SM-SERVICE-REQUEST''s nine edges, and the only definition of them in this system. '
    'Not tenant data: no tenant column, no row level security, and immutable at runtime '
    'by the trigger below. tests/m3c derives the same nine from the pinned package and '
    'requires this table to equal them.';

INSERT INTO service.transition (from_state, to_state, reason) VALUES
    ('new',         'routed',       'routing rule'),
    ('routed',      'acknowledged', 'staff accepts'),
    ('acknowledged','in_progress',  'work begins'),
    ('in_progress', 'completed',    'outcome recorded'),
    ('routed',      'escalated',    'SLA exceeded'),
    ('escalated',   'acknowledged', 'alternate accepts'),
    ('new',         'cancelled',    'customer withdraws'),
    ('routed',      'expired',      'session closes/policy'),
    ('in_progress', 'unresolved',   'reason recorded');

CREATE FUNCTION service.refuse_machine_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'STATE_MACHINE_ALTERED_AT_RUNTIME: service.transition is SM-SERVICE-REQUEST and '
        'is not editable while the system is running; % was refused on %',
        TG_OP, TG_TABLE_NAME USING ERRCODE = 'HS403';
END;
$$;

CREATE TRIGGER service_transition_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON service.transition
    FOR EACH ROW EXECUTE FUNCTION service.refuse_machine_mutation();

CREATE TRIGGER service_transition_no_truncate
    BEFORE TRUNCATE ON service.transition
    FOR EACH STATEMENT EXECUTE FUNCTION service.refuse_machine_mutation();


-- ===========================================================================
-- The translated request catalog (FR-SRV-001)
-- ===========================================================================
-- The seven the requirement names are configuration, not code: an outlet that does not
-- serve packaged food should be able to remove that request, and one with a sommelier
-- should be able to add a request this file never heard of. So the catalog is rows, the
-- codes are text, and nothing downstream branches on which code it is.
--
-- The LABEL a guest reads lives in menu.translation under entity 'service_request_type',
-- which is M2-A's approval workflow: a label reaches a guest only in the approved state,
-- with a reviewer and an approval timestamp on the record.

CREATE TABLE service.request_type (
    id            uuid PRIMARY KEY,
    tenant_id     uuid NOT NULL,
    outlet_id     uuid NOT NULL,
    code          text NOT NULL,

    -- The name staff see and the fallback a guest sees when no approved translation
    -- exists in their language. English, because FR-I18N-007 makes English the staff and
    -- fallback language; the guest's own language comes from the translation store.
    canonical_name text NOT NULL,

    -- FR-SRV-004. How long this outlet has to respond, per request type: water is not
    -- an accessibility request and should not share a deadline with one.
    sla_seconds   integer NOT NULL,

    -- FR-SRV-006. The window inside which a repeat is treated as the same tap rather
    -- than a second ask. Per type, because tapping 'water' twice in four seconds is a
    -- double tap and tapping 'assistance' twice in four seconds may not be.
    dedup_window_seconds integer NOT NULL,

    -- FR-SRV-002. Which role should answer this. Referenced, never copied — the same
    -- rule M1-C set for reason codes.
    handled_by_role_id uuid NOT NULL,

    status        org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version   bigint NOT NULL DEFAULT 1,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT request_type_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT request_type_code_unique UNIQUE (tenant_id, outlet_id, code),
    CONSTRAINT request_type_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT request_type_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT request_type_role_fk FOREIGN KEY (tenant_id, handled_by_role_id)
        REFERENCES identity.role (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT request_type_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT request_type_name_not_blank CHECK (btrim(canonical_name) <> ''),
    CONSTRAINT request_type_sla_positive CHECK (sla_seconds > 0),
    -- Zero would mean "never treat a repeat as accidental", which is a choice an outlet
    -- may make; negative would mean nothing at all.
    CONSTRAINT request_type_dedup_window_not_negative CHECK (dedup_window_seconds >= 0)
);

CREATE TRIGGER request_type_row_version
    BEFORE UPDATE ON service.request_type
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

COMMENT ON TABLE service.request_type IS
    'FR-SRV-001. The seven request types the requirement names are seeded rows, not enum '
    'labels: an outlet configures its own. Nothing downstream branches on the code, so '
    'an eighth type needs no code change — which is the test of whether this is really '
    'configuration.';


-- ===========================================================================
-- Ephemeral presence (FR-SRV-007A, FR-SRV-007B)
-- ===========================================================================
-- ONE ROW PER MEMBER OF STAFF PER OUTLET, HOLDING THE CURRENT STATE.
--
-- The primary key is (tenant, outlet, user) rather than a surrogate id, which is the
-- whole design: a second row for the same person cannot exist, so a history cannot
-- accumulate even by accident. There is no previous_state, no ended_at and no
-- superseded_by column — the model has nowhere to record when somebody became available,
-- only that they are. tests/m3c asserts that absence against the CATALOG rather than
-- against this comment.
--
-- It is discarded twice over, and the two paths are independent:
--   * ending the staff session that set it deletes it (service.end_presence_for_session),
--   * and config.retention_policy sweeps it by age through config.apply_retention —
--     M1-C's engine, the only one, with 'purge' meaning DELETE and archive refusing
--     rather than deleting since M2-B.

CREATE TABLE service.staff_presence (
    tenant_id    uuid NOT NULL,
    outlet_id    uuid NOT NULL,
    user_account_id uuid NOT NULL,

    state        service.presence_state NOT NULL,

    -- The age column the retention policy sweeps on. Overwritten in place on every
    -- change, so it is "when this became true", never "when the previous state ended".
    observed_at  timestamptz NOT NULL DEFAULT now(),

    -- The session that asserted it, so ending that session can discard it. Nullable
    -- only because a session can be deleted from under it; the FK is ON DELETE SET NULL
    -- for exactly that, and a presence row with no session is swept by age.
    asserted_by_session_id uuid,

    PRIMARY KEY (tenant_id, outlet_id, user_account_id),
    CONSTRAINT staff_presence_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT staff_presence_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT staff_presence_user_fk FOREIGN KEY (tenant_id, user_account_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT staff_presence_session_fk FOREIGN KEY (asserted_by_session_id)
        REFERENCES identity.session (id) ON DELETE SET NULL
);

COMMENT ON TABLE service.staff_presence IS
    'FR-SRV-007A. Three states, current only. The primary key is the PERSON, so a second '
    'row for the same person cannot exist and a history cannot accumulate: there is no '
    'previous state, no ended_at and no closed row, because FR-SRV-007B''s fence is about '
    'what EXISTS rather than how long it lasts. A retained record of when staff were '
    'available would be no less an attendance record for having a window on it.';

COMMENT ON COLUMN service.staff_presence.observed_at IS
    'When this state became true — overwritten in place, never appended to. It is the '
    'age column config.retention_policy sweeps, which is what gives FR-SRV-007B its '
    'retention bound.';


-- ===========================================================================
-- The service request ledger (FR-DAT-008A, carried forward)
-- ===========================================================================
-- Same arrangement as ordering.order_event and fulfillment.ticket_event, for the same
-- reason: the ledger is the record and every projection below is a fold of it. Two locks
-- again — the application role is never granted UPDATE or DELETE, and the trigger refuses
-- both regardless of what a grant says.

CREATE TABLE service.service_request_event (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    service_request_id uuid NOT NULL,
    sequence_number integer NOT NULL,
    kind           service.request_event_kind NOT NULL,

    actor_kind     ordering.actor_kind NOT NULL,
    actor_user_id  uuid,
    actor_guest_session_id uuid,

    correlation_id uuid NOT NULL,
    reason_code_id uuid,

    before         jsonb,
    after          jsonb NOT NULL,
    occurred_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT service_request_event_sequence_unique
        UNIQUE (tenant_id, service_request_id, sequence_number),
    CONSTRAINT service_request_event_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT service_request_event_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT service_request_event_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT service_request_event_sequence_positive CHECK (sequence_number > 0),
    -- The actor is whoever the kind says it is. A guest raising a request has a guest
    -- session and no user; staff acknowledging one has a user and no guest session.
    CONSTRAINT service_request_event_actor_matches_kind CHECK (
        (actor_kind = 'guest'  AND actor_guest_session_id IS NOT NULL AND actor_user_id IS NULL)
     OR (actor_kind = 'staff'  AND actor_user_id IS NOT NULL AND actor_guest_session_id IS NULL)
     OR (actor_kind = 'system' AND actor_user_id IS NULL AND actor_guest_session_id IS NULL))
);

CREATE INDEX service_request_event_replay_idx
    ON service.service_request_event (tenant_id, service_request_id, sequence_number);
CREATE INDEX service_request_event_correlation_idx
    ON service.service_request_event (tenant_id, correlation_id);

CREATE FUNCTION service.refuse_ledger_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'SERVICE_LEDGER_MUTATION_REFUSED: the service request ledger is append-only; % is '
        'refused on %', TG_OP, TG_TABLE_NAME USING ERRCODE = 'HS403';
END;
$$;

CREATE TRIGGER service_request_event_append_only
    BEFORE UPDATE OR DELETE ON service.service_request_event
    FOR EACH ROW EXECUTE FUNCTION service.refuse_ledger_mutation();

CREATE TRIGGER service_request_event_no_truncate
    BEFORE TRUNCATE ON service.service_request_event
    FOR EACH STATEMENT EXECUTE FUNCTION service.refuse_ledger_mutation();


-- ===========================================================================
-- The service request (FR-SRV-001 … FR-SRV-009)
-- ===========================================================================

CREATE TABLE service.service_request (
    id             uuid PRIMARY KEY,
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,

    -- The session, not the order. A guest who has ordered nothing can still ask for
    -- water, and a request that needed an order would be unraisable for most of a meal.
    table_session_id uuid NOT NULL,
    -- Present when the request concerns one: a missing item, a bill. FR-SRV-008's staff
    -- tasks use the same column for the order they are about.
    order_id       uuid,

    request_type_id uuid NOT NULL,
    origin         service.request_origin NOT NULL,
    state          service.request_state NOT NULL,

    raised_by_guest_session_id uuid,
    raised_by_user_id uuid,
    -- Free text the guest typed, for 'assistance' and 'missing item'. Customer-authored,
    -- so it is customer-visible by construction and carries nothing staff wrote.
    note           text,

    -- FR-SRV-002's outcome: who is accountable. The package's first invariant is that
    -- every ACTIVE request has one, and the CHECK below is that invariant.
    assigned_user_id uuid,
    assigned_role_id uuid,

    -- FR-I18N-008. The language the guest had chosen when they asked, snapshotted here
    -- rather than read live, so a later language change cannot rewrite what they were
    -- told at the time. The same rule M2-C set for the order.
    customer_locale menu.customer_locale NOT NULL,

    -- FR-SRV-006. Requests raised close together on one session for one type share a
    -- group; the ordinal counts the deliberate asks within it, so "the third time I
    -- asked for water" is answerable.
    dedup_group    uuid NOT NULL,
    repeat_ordinal integer NOT NULL DEFAULT 1,

    -- FR-SRV-004
    raised_at      timestamptz NOT NULL,
    sla_due_at     timestamptz NOT NULL,
    acknowledged_at timestamptz,
    started_at     timestamptz,
    completed_at   timestamptz,
    escalated_at   timestamptz,

    -- FR-SRV-005
    completion_status service.completion_status,
    completion_reason_code_id uuid,
    completion_note text,

    correlation_id uuid NOT NULL,
    ledger_sequence integer NOT NULL,

    CONSTRAINT service_request_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT service_request_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT service_request_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT service_request_session_fk FOREIGN KEY (tenant_id, table_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT service_request_order_fk FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.customer_order (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT service_request_type_fk FOREIGN KEY (tenant_id, request_type_id)
        REFERENCES service.request_type (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT service_request_assignee_fk FOREIGN KEY (tenant_id, assigned_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT service_request_role_fk FOREIGN KEY (tenant_id, assigned_role_id)
        REFERENCES identity.role (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT service_request_completion_reason_fk
        FOREIGN KEY (tenant_id, completion_reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT service_request_origin_names_its_actor CHECK (
        (origin = 'guest' AND raised_by_guest_session_id IS NOT NULL AND raised_by_user_id IS NULL)
     OR (origin = 'staff' AND raised_by_user_id IS NOT NULL AND raised_by_guest_session_id IS NULL)),

    -- SM-SERVICE-REQUEST's first invariant, as a constraint rather than a hope: every
    -- request that is still live has somebody accountable for it. 'new' is the one state
    -- that legitimately has nobody — it has not been routed yet — and routing is the very
    -- next edge.
    CONSTRAINT service_request_active_has_an_assignee CHECK (
        state IN ('new', 'cancelled', 'expired') OR assigned_user_id IS NOT NULL),

    -- FR-SRV-005. Closing without saying how it went is the thing the requirement
    -- forbids, and 'not_possible' owes an explanation rather than a shrug.
    CONSTRAINT service_request_completion_is_stated CHECK (
        (state IN ('completed', 'unresolved')) = (completion_status IS NOT NULL)),
    CONSTRAINT service_request_impossible_is_explained CHECK (
        completion_status IS DISTINCT FROM 'not_possible'
        OR completion_reason_code_id IS NOT NULL),

    CONSTRAINT service_request_repeat_ordinal_positive CHECK (repeat_ordinal > 0),
    CONSTRAINT service_request_note_not_blank CHECK (note IS NULL OR btrim(note) <> '')
);

CREATE INDEX service_request_session_idx
    ON service.service_request (tenant_id, table_session_id, raised_at DESC);
CREATE INDEX service_request_assignee_idx
    ON service.service_request (tenant_id, assigned_user_id, state);
CREATE INDEX service_request_dedup_idx
    ON service.service_request (tenant_id, table_session_id, request_type_id, raised_at DESC);

COMMENT ON TABLE service.service_request IS
    'FR-SRV-001 … FR-SRV-009 and FR-SRV-008''s staff tasks, which are the same aggregate '
    'with origin = staff. Bound to the TABLE SESSION rather than the order, because a '
    'guest who has ordered nothing can still need something.';


-- ===========================================================================
-- The transition guard, in the DATABASE
-- ===========================================================================
-- Same reasoning as NC-M3-004 at M3-B: a check that lived only in the service functions
-- would be enforcement by convention. This fires on every UPDATE of the projection
-- including the ones the fold itself makes, so the fold cannot write an illegal state
-- either.

CREATE FUNCTION service.assert_legal_transition() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = OLD.state THEN
        RETURN NEW;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM service.transition
                    WHERE from_state = OLD.state AND to_state = NEW.state) THEN
        RAISE EXCEPTION
            'ILLEGAL_SERVICE_TRANSITION: % -> % is not an edge of SM-SERVICE-REQUEST; '
            'request %', OLD.state, NEW.state, OLD.id USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER service_request_transition_legal
    BEFORE UPDATE OF state ON service.service_request
    FOR EACH ROW EXECUTE FUNCTION service.assert_legal_transition();

-- The trigger above only sees UPDATEs, so a row INSERTED at some later state would never
-- have transitioned at all. Every request starts where the machine starts.
CREATE FUNCTION service.assert_request_starts_new() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state <> 'new' THEN
        RAISE EXCEPTION
            'ILLEGAL_SERVICE_TRANSITION: a request is created in ''new'' and reaches % by '
            'transition; inserting one there would skip the machine entirely', NEW.state
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER service_request_starts_new
    BEFORE INSERT ON service.service_request
    FOR EACH ROW EXECUTE FUNCTION service.assert_request_starts_new();


-- ===========================================================================
-- The projection guard
-- ===========================================================================

CREATE FUNCTION service.refuse_projection_write() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF coalesce(current_setting('service.applying_event', true), '') <> 'yes' THEN
        RAISE EXCEPTION
            'PROJECTION_WRITTEN_DIRECTLY: % on %.% did not come from '
            'service.apply_request_event(); the ledger is the only way to change a request',
            TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME USING ERRCODE = 'HS403';
    END IF;
    RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER service_request_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON service.service_request
    FOR EACH ROW EXECUTE FUNCTION service.refuse_projection_write();


-- ===========================================================================
-- Routing decisions (FR-SRV-002)
-- ===========================================================================
-- Why this request went to this person, kept. "Routed correctly" is not checkable after
-- the fact unless the four inputs the requirement names are on the record beside the
-- outcome, and a routing bug is otherwise indistinguishable from a staffing one.

CREATE TABLE service.request_routing_decision (
    id             uuid PRIMARY KEY,
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    service_request_id uuid NOT NULL,

    -- The four inputs FR-SRV-002 names, as they were at the moment of routing.
    table_node_id  uuid NOT NULL,
    service_area_id uuid,
    required_role_id uuid NOT NULL,
    considered_count integer NOT NULL,

    chosen_user_id uuid,
    basis          text NOT NULL,
    decided_at     timestamptz NOT NULL,

    CONSTRAINT routing_decision_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT routing_decision_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT routing_decision_request_fk FOREIGN KEY (tenant_id, service_request_id)
        REFERENCES service.service_request (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT routing_decision_role_fk FOREIGN KEY (tenant_id, required_role_id)
        REFERENCES identity.role (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT routing_decision_user_fk FOREIGN KEY (tenant_id, chosen_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT routing_decision_basis_not_blank CHECK (btrim(basis) <> ''),
    CONSTRAINT routing_decision_considered_not_negative CHECK (considered_count >= 0),
    CONSTRAINT routing_decision_one_per_request UNIQUE (tenant_id, service_request_id)
);

CREATE TRIGGER routing_decision_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON service.request_routing_decision
    FOR EACH ROW EXECUTE FUNCTION service.refuse_projection_write();

COMMENT ON TABLE service.request_routing_decision IS
    'FR-SRV-002. The table assignment, service area, role and candidate count that '
    'produced an assignment, kept beside the assignment. Without them a routing defect '
    'and a staffing gap look identical afterwards.';


-- ===========================================================================
-- SLA escalation (FR-SRV-004, FR-NOT-011)
-- ===========================================================================

CREATE TABLE service.request_escalation (
    id             uuid PRIMARY KEY,
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    service_request_id uuid NOT NULL,

    from_user_id   uuid,
    to_user_id     uuid NOT NULL,
    sla_due_at     timestamptz NOT NULL,
    escalated_at   timestamptz NOT NULL,
    overdue_seconds integer NOT NULL,
    basis          text NOT NULL,

    CONSTRAINT request_escalation_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT request_escalation_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT request_escalation_request_fk FOREIGN KEY (tenant_id, service_request_id)
        REFERENCES service.service_request (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT request_escalation_from_fk FOREIGN KEY (tenant_id, from_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT request_escalation_to_fk FOREIGN KEY (tenant_id, to_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT request_escalation_basis_not_blank CHECK (btrim(basis) <> ''),
    -- An escalation to the person who was already accountable is not an escalation.
    CONSTRAINT request_escalation_moves_it CHECK (from_user_id IS DISTINCT FROM to_user_id)
);

CREATE TRIGGER request_escalation_projection_guard
    BEFORE INSERT OR UPDATE OR DELETE ON service.request_escalation
    FOR EACH ROW EXECUTE FUNCTION service.refuse_projection_write();


-- ===========================================================================
-- The notification catalog (FR-NOT-001)
-- ===========================================================================
-- FR-NOT-001 names eight classes of event: order, kitchen, service request, bill,
-- payment, tip, outage and synchronization. Five of those have no producer at this gate
-- and will not until M4 and M5a. THE KINDS EXIST ANYWAY, because the brief is right that
-- a notification kind with no producer is honest and a stubbed bill is not: nothing in
-- this file emits a bill notification, and nothing pretends to.
--
-- The catalog is rows rather than an enum, and its ids are the package's own EVT-…
-- identifiers from events.json. tests/m3c reads that file and requires this table to
-- equal the package exactly for the milestones it claims, failing closed if it cannot
-- read it — the same treatment SM-FULFILLMENT-TICKET got at M3-B, and for the same
-- reason: this is a copy, so something has to check it against the original.

CREATE TYPE notify.event_class AS ENUM (
    'order', 'kitchen', 'service_request', 'bill', 'payment', 'tip', 'outage', 'sync');

CREATE TYPE notify.audience AS ENUM ('customer', 'staff');

CREATE TABLE notify.catalog_event (
    event_id     text PRIMARY KEY,
    event_class  notify.event_class NOT NULL,
    milestone    text NOT NULL,
    -- FR-NOT-005. Critical alerts go to accountable staff rather than to whoever the
    -- subject happens to name, and which kinds are critical is a property of the kind.
    severity     text NOT NULL DEFAULT 'informational',
    -- Whether anything in the running system can produce it yet. FALSE is not a defect,
    -- it is the honest state of a kind whose domain arrives at a later gate, and
    -- tests/m3c requires every TRUE one to have actually been emitted by the suite.
    has_producer boolean NOT NULL,

    CONSTRAINT catalog_event_id_shape CHECK (event_id ~ '^EVT-[A-Z0-9-]+$'),
    CONSTRAINT catalog_event_milestone_shape CHECK (milestone ~ '^M[0-9][A-Za-z]?$'),
    -- A kind cannot claim a producer before the gate that builds one. M3 is this gate;
    -- everything later is a name with nothing behind it, by construction.
    CONSTRAINT catalog_event_producer_only_when_landed CHECK (
        NOT has_producer OR milestone IN ('M1', 'M2', 'M3')),
    CONSTRAINT catalog_event_severity_known CHECK (
        severity IN ('informational', 'critical'))
);

COMMENT ON TABLE notify.catalog_event IS
    'The package''s event catalog, for the classes FR-NOT-001 names. has_producer = false '
    'marks a kind whose domain is a later gate: the kind is real and nothing emits it. '
    'tests/m3c requires this table to equal events.json and fails closed if it cannot '
    'read the package.';

INSERT INTO notify.catalog_event
    (event_id, event_class, milestone, has_producer, severity) VALUES
    -- M3, and every one of these has something in this system that emits it.
    ('EVT-ORDER-SUBMITTED', 'order', 'M3', true, 'informational'),
    ('EVT-ORDER-ACCEPTED', 'order', 'M3', true, 'informational'),
    ('EVT-ORDER-AMENDED', 'order', 'M3', true, 'informational'),
    ('EVT-ORDER-CANCELLED', 'order', 'M3', true, 'informational'),
    ('EVT-ORDER-VOIDED', 'order', 'M3', true, 'informational'),
    ('EVT-ORDER-SERVED', 'order', 'M3', true, 'informational'),
    ('EVT-TICKET-QUEUED', 'kitchen', 'M3', true, 'informational'),
    ('EVT-TICKET-ACKNOWLEDGED', 'kitchen', 'M3', true, 'informational'),
    ('EVT-TICKET-PREPARING', 'kitchen', 'M3', true, 'informational'),
    ('EVT-TICKET-READY', 'kitchen', 'M3', true, 'informational'),
    ('EVT-TICKET-REWORK-REQUESTED', 'kitchen', 'M3', true, 'informational'),
    ('EVT-TICKET-COMPLETED', 'kitchen', 'M3', true, 'informational'),
    ('EVT-SERVICE-REQUESTED', 'service_request', 'M3', true, 'informational'),
    ('EVT-SERVICE-ACKNOWLEDGED', 'service_request', 'M3', true, 'informational'),
    ('EVT-SERVICE-ESCALATED', 'service_request', 'M3', true, 'critical'),
    ('EVT-SERVICE-COMPLETED', 'service_request', 'M3', true, 'informational'),
    -- M4. Named because FR-NOT-001 names bill, payment and tip; produced by nothing.
    ('EVT-CHECK-OPENED', 'bill', 'M4', false, 'informational'),
    ('EVT-CHECK-PRESENTED', 'bill', 'M4', false, 'informational'),
    ('EVT-CHECK-PAID', 'bill', 'M4', false, 'informational'),
    ('EVT-PAYMENT-CAPTURED', 'payment', 'M4', false, 'informational'),
    ('EVT-PAYMENT-FAILED', 'payment', 'M4', false, 'critical'),
    ('EVT-PAYMENT-REVERSED', 'payment', 'M4', false, 'critical'),
    ('EVT-TIP-RECORDED', 'tip', 'M4', false, 'informational'),
    ('EVT-TIP-REFUNDED', 'tip', 'M4', false, 'informational'),
    -- M5a and M5b. Outage and synchronization, likewise named and unproduced.
    ('EVT-OUTLET-RECONNECTING', 'outage', 'M5a', false, 'informational'),
    ('EVT-OUTLET-RECONNECTED', 'outage', 'M5a', false, 'informational'),
    ('EVT-PRINT-JOB-FAILED', 'outage', 'M5a', false, 'critical'),
    ('EVT-SYNC-EVENT-QUEUED', 'sync', 'M5a', false, 'informational'),
    ('EVT-SYNC-CONFLICT-DETECTED', 'sync', 'M5a', false, 'critical'),
    ('EVT-SYNC-EVENT-QUARANTINED', 'sync', 'M5a', false, 'critical'),
    ('EVT-OUTLET-HEARTBEAT-LOST', 'outage', 'M5b', false, 'critical'),
    ('EVT-LOCAL-CONTINUITY-ENTERED', 'outage', 'M5b', false, 'critical');


-- ===========================================================================
-- Templates (FR-NOT-003)
-- ===========================================================================
-- The template's IDENTITY is here; its TEXT is in menu.translation under entity
-- 'notification_template', which is M2-A's approval workflow. That is the whole point of
-- reusing it: a template body reaches a guest only in the approved state, with a reviewer
-- and an approval timestamp on the record, and menu.enforce_translation_review() refuses
-- an approval nobody reviewed. A second store would have needed all of that again.

CREATE TABLE notify.template (
    id           uuid PRIMARY KEY,
    tenant_id    uuid NOT NULL,
    outlet_id    uuid,
    event_id     text NOT NULL,
    audience     notify.audience NOT NULL,

    -- The English source. For a staff template this is what staff read (FR-I18N-007
    -- makes staff English); for a customer template it is the fallback FR-I18N-008
    -- permits when no approved translation exists in the session language.
    source_text  text NOT NULL,

    status       org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version  bigint NOT NULL DEFAULT 1,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT template_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT template_one_per_event_audience UNIQUE (tenant_id, event_id, audience),
    CONSTRAINT template_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT template_event_fk FOREIGN KEY (event_id)
        REFERENCES notify.catalog_event (event_id) ON DELETE RESTRICT,
    CONSTRAINT template_source_not_blank CHECK (btrim(source_text) <> '')
);

CREATE TRIGGER template_row_version
    BEFORE UPDATE ON notify.template
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

COMMENT ON TABLE notify.template IS
    'FR-NOT-003. Identity only: the approved BODY in each customer language lives in '
    'menu.translation under entity notification_template, so M2-A''s human approval '
    'workflow governs it unchanged rather than being written a second time.';


-- ===========================================================================
-- Notifications and their notices (FR-NOT-001, FR-NOT-007, FR-NOT-010)
-- ===========================================================================
-- A NOTIFICATION IS WHAT HAPPENED. A NOTICE IS ONE PERSON BEING TOLD.
--
-- Splitting them is what makes FR-NOT-007 expressible: deduplication is "by event and
-- recipient", which is a statement about notices and unsayable if one row were both.
--
-- FR-NOT-010 is enforced on the payload's SHAPE rather than by review. The payload is
-- jsonb and a CHECK constraint refuses any key outside a fixed allowlist of references —
-- identifiers, states, counts and codes. There is no key through which a guest name, a
-- token digest or a pan could travel, so the absence is a property of the table rather
-- than of whoever wrote the emitting function. An empty allowlist that must stay empty
-- beats no allowlist; a small one that must stay small is the same idea.

CREATE TYPE notify.notice_state AS ENUM (
    'pending', 'sent', 'read', 'failed', 'dead_lettered');

-- The three ways an in-app notice genuinely fails. There is no 'transport_error':
-- there is no transport at this gate, and inventing one would be the stub the brief
-- warns against. M5a's adapters add their reasons here when they exist.
CREATE TYPE notify.failure_reason AS ENUM (
    'recipient_not_authorized', 'recipient_out_of_scope', 'template_missing');

-- FR-NOT-010's enforcement, as one immutable predicate the table's CHECK calls.
--
-- Three rules, and the third is the one that took a second attempt. A key allowlist alone
-- lets anything through as the VALUE of an allowed key — 'reason_code' would happily
-- carry a paragraph containing a guest's name — and a nested object under an allowed key
-- would not be inspected at all. So: allowed keys, scalar values only, and each value
-- short enough that it is an identifier or a code rather than prose.
CREATE FUNCTION notify.payload_within_bounds(p_payload jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE
AS $$
    SELECT jsonb_typeof(p_payload) = 'object'
       -- Every key is one of these. jsonb minus a key array removes them, so an empty
       -- object left over means there was nothing else in it.
       AND (p_payload - ARRAY[
                'order_id', 'ticket_id', 'service_request_id', 'table_session_id',
                'table_node_id', 'station_node_id', 'order_number', 'request_type_code',
                'state', 'previous_state', 'unit_count', 'ready_unit_count',
                'sla_due_at', 'overdue_seconds', 'repeat_ordinal', 'reason_code',
                'escalation_level']) = '{}'::jsonb
       -- No value is an object or an array, so nothing can be smuggled one level down.
       AND NOT EXISTS (
                SELECT 1 FROM jsonb_each(p_payload) AS e
                 WHERE jsonb_typeof(e.value) IN ('object', 'array'))
       -- And no value is long enough to be prose. 128 characters holds a uuid, a
       -- timestamp or a reason code and does not hold a sentence about a person.
       AND NOT EXISTS (
                SELECT 1 FROM jsonb_each_text(p_payload) AS e
                 WHERE length(e.value) > 128);
$$;

COMMENT ON FUNCTION notify.payload_within_bounds(jsonb) IS
    'FR-NOT-010. Allowed keys, scalar values only, and none of them long enough to be a '
    'sentence. A key allowlist on its own is not enough: an allowed key with a free-text '
    'value is the same leak by another route.';

CREATE TABLE notify.notification (
    id             uuid PRIMARY KEY,
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    event_id       text NOT NULL,

    -- What it is about, by reference. Never by value: the subject is an id, and whoever
    -- reads it asks the owning schema what it means under their own authorization.
    subject_kind   ordering.artifact_kind NOT NULL,
    subject_id     uuid NOT NULL,

    correlation_id uuid NOT NULL,
    -- FR-NOT-007. Deliveries for one event and recipient collapse onto this key.
    dedup_key      text NOT NULL,
    payload        jsonb NOT NULL DEFAULT '{}'::jsonb,
    emitted_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT notification_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT notification_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT notification_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT notification_event_fk FOREIGN KEY (event_id)
        REFERENCES notify.catalog_event (event_id) ON DELETE RESTRICT,
    CONSTRAINT notification_dedup_key_not_blank CHECK (btrim(dedup_key) <> ''),

    -- FR-NOT-010, as a property of the table rather than of whoever writes the next
    -- emitter.
    CONSTRAINT notification_payload_within_bounds
        CHECK (notify.payload_within_bounds(payload))
);

CREATE INDEX notification_correlation_idx
    ON notify.notification (tenant_id, correlation_id);
CREATE INDEX notification_subject_idx
    ON notify.notification (tenant_id, subject_kind, subject_id);

COMMENT ON CONSTRAINT notification_payload_within_bounds ON notify.notification IS
    'FR-NOT-010. The payload may name things by id, state, count or registered code and '
    'nothing else — there is no key through which a customer name, an authentication '
    'token or a payment figure could travel, and no nesting in which one could hide.';

CREATE TABLE notify.notice (
    id             uuid PRIMARY KEY,
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    notification_id uuid NOT NULL,

    audience       notify.audience NOT NULL,
    recipient_user_id uuid,
    recipient_guest_session_id uuid,

    -- FR-I18N-008. The language this recipient is told in, snapshotted at emission from
    -- the table session, so a later change cannot rewrite what they were shown.
    locale         menu.customer_locale NOT NULL,
    -- Rendered at notice from the approved template. Held so the customer timeline
    -- shows what was actually said rather than what the template says today.
    rendered_text  text,

    state          notify.notice_state NOT NULL DEFAULT 'pending',
    attempts       integer NOT NULL DEFAULT 0,
    last_failure   notify.failure_reason,
    last_failed_at timestamptz,
    sent_at   timestamptz,
    read_at        timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT notice_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT notice_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT notice_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT notice_notification_fk FOREIGN KEY (tenant_id, notification_id)
        REFERENCES notify.notification (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT notice_user_fk FOREIGN KEY (tenant_id, recipient_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT notice_guest_fk FOREIGN KEY (tenant_id, recipient_guest_session_id)
        REFERENCES service.guest_session (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT notice_audience_names_its_recipient CHECK (
        (audience = 'staff' AND recipient_user_id IS NOT NULL
                            AND recipient_guest_session_id IS NULL)
     OR (audience = 'customer' AND recipient_guest_session_id IS NOT NULL
                               AND recipient_user_id IS NULL)),
    CONSTRAINT notice_attempts_not_negative CHECK (attempts >= 0),
    CONSTRAINT notice_failure_is_explained CHECK (
        (state IN ('failed', 'dead_lettered')) = (last_failure IS NOT NULL)),
    CONSTRAINT notice_sent_has_text CHECK (
        state NOT IN ('sent', 'read') OR rendered_text IS NOT NULL),
    CONSTRAINT notice_read_after_sent CHECK (
        read_at IS NULL OR sent_at IS NOT NULL)
);

-- FR-NOT-007, as a constraint rather than as a query somebody remembers to run: one
-- notice per notification per recipient, so a second emission for the same event and
-- person cannot produce a second alert even if the emitter forgets to look.
CREATE UNIQUE INDEX notice_one_per_recipient
    ON notify.notice (tenant_id, notification_id,
                        coalesce(recipient_user_id, recipient_guest_session_id));

CREATE INDEX notice_pending_idx
    ON notify.notice (tenant_id, state, created_at)
    WHERE state IN ('pending', 'failed');

COMMENT ON TABLE notify.notice IS
    'One person being told one thing. FR-NOT-007''s deduplication is a UNIQUE index over '
    '(notification, recipient) rather than a check the emitter performs, because an '
    'emitter that forgot would produce exactly the duplicate alert the requirement '
    'forbids.';


-- ===========================================================================
-- Deep links (FR-NOT-009)
-- ===========================================================================
-- A deep link is a TARGET DESCRIPTOR plus an authorization question, and the two travel
-- together. The screen the link opens is M3-D's for staff and M2-C's for a guest; what
-- this gate owns is that resolving one asks the same question M2-B's session scope asks,
-- because "the link opened for the wrong outlet" is FOREIGN_SESSION_ACCEPTED wearing a
-- different hat.
--
-- The token is opaque and random, not a composed id: a link whose target could be read
-- or edited out of the token would let somebody enumerate other tables' requests without
-- ever failing an authorization check, which is the M2-B lesson about QR references.

CREATE TABLE notify.deep_link (
    id             uuid PRIMARY KEY,
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    notice_id    uuid NOT NULL,

    -- Opaque. Stored as a digest, never as the token itself, so a leaked backup does not
    -- hand out working links — M1-B's rule for session tokens, unchanged.
    token_digest   bytea NOT NULL,

    target_kind    ordering.artifact_kind NOT NULL,
    target_id      uuid NOT NULL,
    -- The scope the resolver must find the caller inside. For a staff link this is the
    -- outlet; for a customer link it is additionally the table session.
    scope_table_session_id uuid,

    expires_at     timestamptz NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT deep_link_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT deep_link_digest_unique UNIQUE (token_digest),
    CONSTRAINT deep_link_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT deep_link_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT deep_link_notice_fk FOREIGN KEY (tenant_id, notice_id)
        REFERENCES notify.notice (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT deep_link_session_fk FOREIGN KEY (tenant_id, scope_table_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT deep_link_digest_is_sha256 CHECK (octet_length(token_digest) = 32)
);

COMMENT ON TABLE notify.deep_link IS
    'FR-NOT-009. An opaque token, a target and the scope a caller must be inside to '
    'follow it. The token is stored as sha256 and never in the clear, and the target is '
    'not derivable from it — a link that could be edited into another table''s request '
    'would fail no authorization check because it would never reach one.';


-- ===========================================================================
-- The dead-letter queue (FR-INT-007)
-- ===========================================================================
-- Repeatedly failing work, visible to an operator, with the reason and a replay that
-- cannot cause the duplicate the original was refused for.
--
-- Its own schema because M4's payment adapters and M5a's synchronization use the same
-- queue. THE EXTENSION POINT IS PROSE, NOT A SEAM: when a transport adapter exists, its
-- failures reach this queue through the same door — integration.dead_letter_job() — and
-- nothing here is built in advance to receive them. An abstraction with one
-- implementation has no second case to prove it right.

CREATE TYPE integration.job_kind AS ENUM ('notification_notice');

CREATE TYPE integration.dead_letter_state AS ENUM ('open', 'replayed', 'abandoned');

CREATE TABLE integration.dead_letter (
    id             uuid PRIMARY KEY,
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,

    job_kind       integration.job_kind NOT NULL,
    -- The work itself, by reference. A dead letter holding a COPY of the work would let
    -- a replay act on a stale copy of something that has since changed.
    subject_id     uuid NOT NULL,

    failure_reason text NOT NULL,
    attempts       integer NOT NULL,
    first_failed_at timestamptz NOT NULL,
    last_failed_at timestamptz NOT NULL,

    state          integration.dead_letter_state NOT NULL DEFAULT 'open',
    resolved_at    timestamptz,
    resolved_by_user_id uuid,
    resolution_note text,

    correlation_id uuid NOT NULL,

    CONSTRAINT dead_letter_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT dead_letter_one_per_subject UNIQUE (tenant_id, job_kind, subject_id),
    CONSTRAINT dead_letter_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT dead_letter_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT dead_letter_resolver_fk FOREIGN KEY (tenant_id, resolved_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT dead_letter_reason_not_blank CHECK (btrim(failure_reason) <> ''),
    CONSTRAINT dead_letter_attempts_positive CHECK (attempts > 0),
    -- A resolved entry names who resolved it and when. "Replayed by nobody" is the same
    -- defect as M3-B's priority with no attributed actor.
    CONSTRAINT dead_letter_resolution_is_attributed CHECK (
        (state = 'open') = (resolved_at IS NULL)
        AND (state = 'open') = (resolved_by_user_id IS NULL))
);

CREATE INDEX dead_letter_open_idx
    ON integration.dead_letter (tenant_id, outlet_id, last_failed_at DESC)
    WHERE state = 'open';

COMMENT ON TABLE integration.dead_letter IS
    'FR-INT-007. Operator-visible, with the reason and the attempt count that got it '
    'here. It holds the work by REFERENCE: a copy would let a replay act on a stale '
    'version of something that has since moved on. M4 and M5a extend job_kind; the '
    'queue, the door and the replay control are these.';


-- ===========================================================================
-- The fold (FR-DAT-010, carried forward)
-- ===========================================================================
-- Pure and total: every value it writes comes out of the event, so a replay is
-- byte-identical rather than merely equivalent. It reads no clock and no random source.

CREATE FUNCTION service.next_sequence(p_tenant_id uuid, p_service_request_id uuid)
RETURNS integer
LANGUAGE sql STABLE
AS $$
    SELECT coalesce(max(sequence_number), 0) + 1
      FROM service.service_request_event
     WHERE tenant_id = p_tenant_id AND service_request_id = p_service_request_id;
$$;

CREATE FUNCTION service.apply_request_event(p_event_id bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, service, ordering, identity, config, notify, public
AS $$
DECLARE
    e       service.service_request_event%ROWTYPE;
    v_after jsonb;
BEGIN
    SELECT * INTO e FROM service.service_request_event WHERE id = p_event_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SERVICE_EVENT_ABSENT: no service request event %', p_event_id
            USING ERRCODE = 'HS404';
    END IF;
    v_after := e.after;

    PERFORM set_config('service.applying_event', 'yes', true);

    IF e.kind = 'raised' THEN
        INSERT INTO service.service_request
            (id, tenant_id, outlet_id, table_session_id, order_id, request_type_id,
             origin, state, raised_by_guest_session_id, raised_by_user_id, note,
             customer_locale, dedup_group, repeat_ordinal, raised_at, sla_due_at,
             correlation_id, ledger_sequence)
        VALUES
            (e.service_request_id, e.tenant_id, e.outlet_id,
             (v_after ->> 'table_session_id')::uuid,
             nullif(v_after ->> 'order_id', '')::uuid,
             (v_after ->> 'request_type_id')::uuid,
             (v_after ->> 'origin')::service.request_origin,
             'new',
             nullif(v_after ->> 'raised_by_guest_session_id', '')::uuid,
             nullif(v_after ->> 'raised_by_user_id', '')::uuid,
             nullif(v_after ->> 'note', ''),
             (v_after ->> 'customer_locale')::menu.customer_locale,
             (v_after ->> 'dedup_group')::uuid,
             (v_after ->> 'repeat_ordinal')::integer,
             e.occurred_at,
             e.occurred_at
                 + make_interval(secs => (v_after ->> 'sla_seconds')::integer),
             e.correlation_id, e.sequence_number);

        -- FR-INT-014. The chain's newest link, written BY THE FOLD. M3-B learned this
        -- the hard way: a correlation link written by the caller is a projection no
        -- rebuild can restore, and the reversed run is what found it.
        PERFORM ordering.link_correlation_artifact(
            e.tenant_id, e.outlet_id, e.correlation_id, 'service_request',
            e.service_request_id, e.occurred_at);

    ELSIF e.kind = 'routed' THEN
        UPDATE service.service_request
           SET state = 'routed',
               assigned_user_id = nullif(v_after ->> 'assigned_user_id', '')::uuid,
               assigned_role_id = (v_after ->> 'assigned_role_id')::uuid,
               ledger_sequence = e.sequence_number
         WHERE id = e.service_request_id;

        INSERT INTO service.request_routing_decision
            (id, tenant_id, outlet_id, service_request_id, table_node_id,
             service_area_id, required_role_id, considered_count, chosen_user_id,
             basis, decided_at)
        VALUES ((v_after ->> 'decision_id')::uuid, e.tenant_id, e.outlet_id,
                e.service_request_id,
                (v_after ->> 'table_node_id')::uuid,
                nullif(v_after ->> 'service_area_id', '')::uuid,
                (v_after ->> 'assigned_role_id')::uuid,
                (v_after ->> 'considered_count')::integer,
                nullif(v_after ->> 'assigned_user_id', '')::uuid,
                v_after ->> 'basis', e.occurred_at);

    ELSIF e.kind = 'acknowledged' THEN
        UPDATE service.service_request
           SET state = 'acknowledged',
               assigned_user_id = e.actor_user_id,
               acknowledged_at = e.occurred_at,
               ledger_sequence = e.sequence_number
         WHERE id = e.service_request_id;

    ELSIF e.kind = 'started' THEN
        UPDATE service.service_request
           SET state = 'in_progress',
               started_at = e.occurred_at,
               ledger_sequence = e.sequence_number
         WHERE id = e.service_request_id;

    ELSIF e.kind = 'completed' THEN
        UPDATE service.service_request
           SET state = 'completed',
               completed_at = e.occurred_at,
               completion_status = (v_after ->> 'completion_status')::service.completion_status,
               completion_reason_code_id = e.reason_code_id,
               completion_note = nullif(v_after ->> 'completion_note', ''),
               ledger_sequence = e.sequence_number
         WHERE id = e.service_request_id;

    ELSIF e.kind = 'unresolved' THEN
        UPDATE service.service_request
           SET state = 'unresolved',
               completed_at = e.occurred_at,
               completion_status = (v_after ->> 'completion_status')::service.completion_status,
               completion_reason_code_id = e.reason_code_id,
               completion_note = nullif(v_after ->> 'completion_note', ''),
               ledger_sequence = e.sequence_number
         WHERE id = e.service_request_id;

    ELSIF e.kind = 'cancelled' THEN
        UPDATE service.service_request
           SET state = 'cancelled', ledger_sequence = e.sequence_number
         WHERE id = e.service_request_id;

    ELSIF e.kind = 'expired' THEN
        UPDATE service.service_request
           SET state = 'expired', ledger_sequence = e.sequence_number
         WHERE id = e.service_request_id;

    ELSIF e.kind = 'escalated' THEN
        UPDATE service.service_request
           SET state = 'escalated',
               assigned_user_id = (v_after ->> 'to_user_id')::uuid,
               escalated_at = e.occurred_at,
               ledger_sequence = e.sequence_number
         WHERE id = e.service_request_id;

        INSERT INTO service.request_escalation
            (id, tenant_id, outlet_id, service_request_id, from_user_id, to_user_id,
             sla_due_at, escalated_at, overdue_seconds, basis)
        VALUES ((v_after ->> 'escalation_id')::uuid, e.tenant_id, e.outlet_id,
                e.service_request_id,
                nullif(v_after ->> 'from_user_id', '')::uuid,
                (v_after ->> 'to_user_id')::uuid,
                (v_after ->> 'sla_due_at')::timestamptz,
                e.occurred_at,
                (v_after ->> 'overdue_seconds')::integer,
                v_after ->> 'basis');

    ELSIF e.kind = 'session_changed' THEN
        UPDATE service.service_request
           SET table_session_id = (v_after ->> 'table_session_id')::uuid,
               ledger_sequence = e.sequence_number
         WHERE id = e.service_request_id;

    ELSIF e.kind = 'reassigned' THEN
        UPDATE service.service_request
           SET assigned_user_id = (v_after ->> 'assigned_user_id')::uuid,
               ledger_sequence = e.sequence_number
         WHERE id = e.service_request_id;

    ELSE
        -- Unreachable while every label above is handled, and tests/m3c proves that by
        -- reading the labels out of the catalog. The branch is here for the day
        -- somebody adds an eleventh.
        RAISE EXCEPTION
            'SERVICE_EVENT_KIND_UNHANDLED: no fold for %', e.kind USING ERRCODE = 'HS500';
    END IF;

    PERFORM set_config('service.applying_event', '', true);
END;
$$;

COMMENT ON FUNCTION service.apply_request_event(bigint) IS
    'The only writer of every service projection. SECURITY DEFINER so the application '
    'role can hold SELECT and nothing more on them, which makes the grant and the '
    'projection guard two independent locks rather than one described twice.';


-- ===========================================================================
-- Presence (FR-SRV-007A) and its two discard paths (FR-SRV-007B)
-- ===========================================================================

CREATE FUNCTION service.set_presence(
    p_tenant_id uuid, p_outlet_id uuid, p_user_id uuid,
    p_state service.presence_state) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    IF app.current_session_id() IS NULL THEN
        RAISE EXCEPTION
            'PRESENCE_REQUIRES_STAFF_SESSION: presence is asserted by somebody who is '
            'here; there is no live staff session in context' USING ERRCODE = 'HS403';
    END IF;

    -- Upsert, never insert. The primary key is the person, so this OVERWRITES: there is
    -- no second row and therefore no history, which is the model's guarantee rather
    -- than this function's.
    INSERT INTO service.staff_presence
        (tenant_id, outlet_id, user_account_id, state, observed_at,
         asserted_by_session_id)
    VALUES (p_tenant_id, p_outlet_id, p_user_id, p_state, now(),
            app.current_session_id())
    ON CONFLICT (tenant_id, outlet_id, user_account_id) DO UPDATE
       SET state = EXCLUDED.state,
           observed_at = EXCLUDED.observed_at,
           asserted_by_session_id = EXCLUDED.asserted_by_session_id;
END;
$$;

-- The first discard path: the session that asserted presence ends, so the presence it
-- asserted ends with it. DELETE, not a flag and not an 'offline' state — a row that said
-- 'offline' since Tuesday is still a record of somebody's Tuesday.
CREATE FUNCTION service.end_presence_for_session(p_session_id uuid) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_count integer;
BEGIN
    DELETE FROM service.staff_presence WHERE asserted_by_session_id = p_session_id;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION service.end_presence_for_session(uuid) IS
    'FR-SRV-007B, discard path one. DELETE rather than a flag: a row saying somebody has '
    'been offline since Tuesday is a record of their Tuesday, and no attendance '
    'record of that kind may exist here. Path two is config.apply_retention(), '
    'which is M1-C''s engine and stays the only sweep.';


-- ===========================================================================
-- Routing (FR-SRV-002)
-- ===========================================================================
-- The four inputs the requirement names, in preference order, with the basis recorded so
-- the choice is answerable afterwards:
--
--   1. the table's assigned waiter, if they hold the role and are available
--   2. anyone in the table's service area who holds the role and is available
--   3. anyone in the outlet who holds the role and is available
--   4. the table's assigned waiter even though they are not available — they are still
--      accountable, and an unanswered request with a name on it beats one with none
--   5. anyone in the outlet who holds the role, available or not
--
-- Only when the outlet has nobody with the role at all does this return no one, and the
-- request stays 'new': the machine has no edge from 'new' to 'escalated', and inventing
-- one so that an unroutable request looked handled would be worse than the truth.

CREATE FUNCTION service.route_request_candidates(
    p_tenant_id uuid, p_outlet_id uuid, p_table_session_id uuid, p_role_id uuid)
RETURNS TABLE (user_account_id uuid, rank integer, basis text)
LANGUAGE sql STABLE
AS $$
    WITH assigned AS (
        SELECT tow.primary_waiter_user_id AS uid
          FROM service.table_ownership tow
         WHERE tow.tenant_id = p_tenant_id
           AND tow.table_session_id = p_table_session_id
           AND tow.effective_to IS NULL
         ORDER BY tow.assigned_at DESC
         LIMIT 1),
    area AS (
        SELECT tp.service_area_id
          FROM service.table_session ts
          JOIN service.table_profile tp
            ON tp.tenant_id = ts.tenant_id AND tp.table_node_id = ts.table_node_id
         WHERE ts.tenant_id = p_tenant_id AND ts.id = p_table_session_id),
    holders AS (
        SELECT m.user_account_id AS uid,
               coalesce(sp.state, 'offline'::service.presence_state) AS presence,
               EXISTS (SELECT 1 FROM service.table_ownership t2
                        JOIN service.table_session ts2
                          ON ts2.tenant_id = t2.tenant_id
                         AND ts2.id = t2.table_session_id
                        JOIN service.table_profile tp2
                          ON tp2.tenant_id = ts2.tenant_id
                         AND tp2.table_node_id = ts2.table_node_id
                       WHERE t2.tenant_id = p_tenant_id
                         AND t2.primary_waiter_user_id = m.user_account_id
                         AND t2.effective_to IS NULL
                         AND tp2.service_area_id IS NOT DISTINCT FROM
                             (SELECT service_area_id FROM area)) AS in_area
          FROM identity.membership m
          LEFT JOIN service.staff_presence sp
                 ON sp.tenant_id = m.tenant_id AND sp.outlet_id = m.outlet_id
                AND sp.user_account_id = m.user_account_id
         WHERE m.tenant_id = p_tenant_id AND m.outlet_id = p_outlet_id
           AND m.role_id = p_role_id AND m.status = 'active')
    SELECT h.uid,
           CASE
               WHEN h.uid = (SELECT uid FROM assigned) AND h.presence = 'available' THEN 1
               WHEN h.in_area AND h.presence = 'available'                          THEN 2
               WHEN h.presence = 'available'                                        THEN 3
               WHEN h.uid = (SELECT uid FROM assigned)                              THEN 4
               ELSE                                                                      5
           END,
           CASE
               WHEN h.uid = (SELECT uid FROM assigned) AND h.presence = 'available'
                    THEN 'assigned waiter, available'
               WHEN h.in_area AND h.presence = 'available'
                    THEN 'available in the table''s service area'
               WHEN h.presence = 'available'
                    THEN 'available in the outlet, holding the role'
               WHEN h.uid = (SELECT uid FROM assigned)
                    THEN 'assigned waiter, not available but still accountable'
               ELSE 'holds the role; nobody with it is available'
           END
      FROM holders h
     -- Deterministic beyond the rank, so two runs of the same fixture route the same way
     -- and a rebuild is comparable.
     ORDER BY 2, 1;
$$;

COMMENT ON FUNCTION service.route_request_candidates(uuid, uuid, uuid, uuid) IS
    'FR-SRV-002''s four inputs — table assignment, service area, role and availability — '
    'as a ranked list with the reason for each rank. Returning the candidates rather '
    'than the winner is what lets the routing decision record how many were considered.';


-- ===========================================================================
-- Raising a request, and FR-SRV-006's two sides
-- ===========================================================================
-- The two sides are different questions and this function answers both:
--
--   AN ACCIDENT is the same ask arriving twice within the type's configured window. It
--   collapses: no second request, no second alert, and the caller gets the id of the one
--   that already exists. Nothing is lost, because the thing they asked for is already
--   on somebody's list.
--
--   A DELIBERATE REPEAT is the guest saying so. p_deliberate is not a hint the client
--   sets by default — the customer surface only sends it after telling the guest that a
--   request of this kind is already open and asking whether they mean to ask again. It
--   ALWAYS raises a new request, inside the window or outside it, and the new request
--   carries the same dedup_group with the next ordinal so "the third time I asked" is
--   answerable.
--
-- A window that collapsed a deliberate repeat would satisfy the first half of FR-SRV-006
-- and fail the requirement; so would one that never collapsed anything. Both directions
-- are negative controls.

CREATE FUNCTION service.raise_request(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_table_session_id uuid,
    p_request_type_id uuid,
    p_idempotency_key text,
    p_guest_session_id uuid DEFAULT NULL,
    p_user_id uuid DEFAULT NULL,
    p_order_id uuid DEFAULT NULL,
    p_note text DEFAULT NULL,
    p_deliberate boolean DEFAULT false
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_session  service.table_session%ROWTYPE;
    v_type     service.request_type%ROWTYPE;
    v_origin   service.request_origin;
    v_open     service.service_request%ROWTYPE;
    v_locale   menu.customer_locale;
    v_group    uuid;
    v_ordinal  integer := 1;
    v_request  uuid;
    v_event    bigint;
    v_corr     uuid;
    v_claim    record;
    v_digest   bytea;
BEGIN
    SELECT * INTO v_session FROM service.table_session
     WHERE id = p_table_session_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TABLE_SESSION_NOT_FOUND: no session % in scope',
            p_table_session_id USING ERRCODE = 'HS404';
    END IF;
    IF v_session.state <> 'open' THEN
        RAISE EXCEPTION
            'TABLE_SESSION_NOT_OPEN: session % is %; a closed table cannot ask for '
            'anything', p_table_session_id, v_session.state USING ERRCODE = 'HS409';
    END IF;

    SELECT * INTO v_type FROM service.request_type
     WHERE id = p_request_type_id AND tenant_id = p_tenant_id AND status = 'active';
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'REQUEST_TYPE_NOT_AVAILABLE: % is not an active request type at this outlet',
            p_request_type_id USING ERRCODE = 'HS404';
    END IF;

    IF (p_guest_session_id IS NULL) = (p_user_id IS NULL) THEN
        RAISE EXCEPTION
            'REQUEST_ACTOR_AMBIGUOUS: a request is raised by a guest or by a member of '
            'staff, and the record has to say which' USING ERRCODE = 'HS400';
    END IF;
    v_origin := CASE WHEN p_guest_session_id IS NOT NULL THEN 'guest' ELSE 'staff' END;

    -- FR-I18N-008. The language snapshotted on the session, not read live. An outlet
    -- with no locale chosen yet falls back to English, which is FR-I18N-007's rule and
    -- is recorded on the request rather than resolved again at read time.
    v_locale := coalesce(v_session.customer_locale, 'en'::menu.customer_locale);

    -- FR-INT-005 and FR-ORD-004's rule, unchanged: the SAME command arriving twice is a
    -- retry and returns the original outcome. This is a different question from
    -- deduplication below — a retry is one ask that arrived twice, a duplicate tap is
    -- two asks that look alike.
    v_digest := sha256(convert_to(
        p_table_session_id::text || '|' || p_request_type_id::text || '|' ||
        coalesce(p_note, '') || '|' || p_deliberate::text, 'UTF8'));

    INSERT INTO service.idempotency_key
        (tenant_id, outlet_id, scope, idem_key, request_digest)
    VALUES (p_tenant_id, p_outlet_id, 'service_request.raise', p_idempotency_key, v_digest)
    ON CONFLICT (tenant_id, scope, idem_key) DO NOTHING;

    SELECT * INTO v_claim FROM service.idempotency_key
     WHERE tenant_id = p_tenant_id
       AND scope = 'service_request.raise' AND idem_key = p_idempotency_key;

    IF v_claim.request_digest <> v_digest THEN
        RAISE EXCEPTION
            'IDEMPOTENCY_KEY_REUSED: key % was already used for a different request; '
            'returning the first outcome would answer a question nobody asked',
            p_idempotency_key USING ERRCODE = 'HS409';
    END IF;
    IF v_claim.result_id IS NOT NULL THEN
        RETURN v_claim.result_id;          -- the original outcome, not a fresh one
    END IF;

    -- FR-SRV-006. The most recent request of this type still open on this session.
    SELECT * INTO v_open FROM service.service_request
     WHERE tenant_id = p_tenant_id AND table_session_id = p_table_session_id
       AND request_type_id = p_request_type_id
       AND state NOT IN ('completed', 'cancelled', 'expired', 'unresolved')
     ORDER BY raised_at DESC
     LIMIT 1;

    IF FOUND THEN
        v_group := v_open.dedup_group;
        IF NOT p_deliberate
           AND now() < v_open.raised_at
                       + make_interval(secs => v_type.dedup_window_seconds) THEN
            -- The accidental side. No new request, no new alert, and the caller is told
            -- which request theirs collapsed into rather than being given an error: the
            -- thing they asked for is already open, and that is a success.
            UPDATE service.idempotency_key SET result_id = v_open.id
             WHERE tenant_id = p_tenant_id
               AND scope = 'service_request.raise' AND idem_key = p_idempotency_key;
            RETURN v_open.id;
        END IF;
        -- The deliberate side, or a repeat outside the window. Same group, next ordinal.
        SELECT max(repeat_ordinal) + 1 INTO v_ordinal
          FROM service.service_request
         WHERE tenant_id = p_tenant_id AND dedup_group = v_group;
    ELSE
        v_group := gen_random_uuid();
    END IF;

    -- FR-INT-014. A request on a session that already has an order joins that order's
    -- chain; one on a session with no order starts its own. Either way it is a chain,
    -- not an orphan.
    SELECT coalesce(
        (SELECT o.correlation_id FROM ordering.customer_order o
          WHERE o.tenant_id = p_tenant_id AND o.id = p_order_id),
        (SELECT o.correlation_id FROM ordering.customer_order o
          WHERE o.tenant_id = p_tenant_id AND o.table_session_id = p_table_session_id
          ORDER BY o.submitted_at DESC LIMIT 1),
        gen_random_uuid())
      INTO v_corr;

    v_request := gen_random_uuid();

    INSERT INTO service.service_request_event
        (tenant_id, outlet_id, service_request_id, sequence_number, kind, actor_kind,
         actor_user_id, actor_guest_session_id, correlation_id, after)
    VALUES (p_tenant_id, p_outlet_id, v_request, 1, 'raised',
            CASE WHEN v_origin = 'guest' THEN 'guest' ELSE 'staff' END::ordering.actor_kind,
            p_user_id, p_guest_session_id, v_corr,
            jsonb_build_object(
                'table_session_id', p_table_session_id,
                'order_id', p_order_id,
                'request_type_id', p_request_type_id,
                'origin', v_origin,
                'raised_by_guest_session_id', p_guest_session_id,
                'raised_by_user_id', p_user_id,
                'note', p_note,
                'customer_locale', v_locale,
                'dedup_group', v_group,
                'repeat_ordinal', v_ordinal,
                'sla_seconds', v_type.sla_seconds))
    RETURNING id INTO v_event;

    PERFORM service.apply_request_event(v_event);

    UPDATE service.idempotency_key SET result_id = v_request
     WHERE tenant_id = p_tenant_id
       AND scope = 'service_request.raise' AND idem_key = p_idempotency_key;

    PERFORM service.route_request(p_tenant_id, v_request);
    RETURN v_request;
END;
$$;


CREATE FUNCTION service.route_request(p_tenant_id uuid, p_request_id uuid)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    r          service.service_request%ROWTYPE;
    v_type     service.request_type%ROWTYPE;
    v_table    uuid;
    v_area     uuid;
    v_chosen   record;
    v_count    integer;
    v_event    bigint;
BEGIN
    SELECT * INTO r FROM service.service_request
     WHERE id = p_request_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SERVICE_REQUEST_NOT_FOUND: no request % in scope', p_request_id
            USING ERRCODE = 'HS404';
    END IF;
    IF r.state <> 'new' THEN
        RAISE EXCEPTION
            'REQUEST_ALREADY_ROUTED: request % is %; routing it again would reassign work '
            'somebody has already taken', p_request_id, r.state USING ERRCODE = 'HS409';
    END IF;

    SELECT * INTO v_type FROM service.request_type WHERE id = r.request_type_id;

    SELECT ts.table_node_id, tp.service_area_id INTO v_table, v_area
      FROM service.table_session ts
      LEFT JOIN service.table_profile tp
             ON tp.tenant_id = ts.tenant_id AND tp.table_node_id = ts.table_node_id
     WHERE ts.tenant_id = p_tenant_id AND ts.id = r.table_session_id;

    SELECT count(*) INTO v_count
      FROM service.route_request_candidates(p_tenant_id, r.outlet_id,
                                            r.table_session_id, v_type.handled_by_role_id);

    SELECT * INTO v_chosen
      FROM service.route_request_candidates(p_tenant_id, r.outlet_id,
                                            r.table_session_id, v_type.handled_by_role_id)
     LIMIT 1;

    IF v_chosen IS NULL THEN
        -- Nobody at this outlet holds the role at all. The machine has no edge from
        -- 'new' to anywhere but 'routed' and 'cancelled', so the request stays where it
        -- is and says so. Inventing a route to nobody would make an unanswerable request
        -- look handled.
        RAISE EXCEPTION
            'NO_ELIGIBLE_STAFF: no active member of staff at outlet % holds the role this '
            'request type is handled by; the request stands unrouted rather than being '
            'assigned to nobody', r.outlet_id USING ERRCODE = 'HS412';
    END IF;

    INSERT INTO service.service_request_event
        (tenant_id, outlet_id, service_request_id, sequence_number, kind, actor_kind,
         correlation_id, before, after)
    VALUES (p_tenant_id, r.outlet_id, p_request_id,
            service.next_sequence(p_tenant_id, p_request_id), 'routed', 'system',
            r.correlation_id,
            jsonb_build_object('state', r.state),
            jsonb_build_object(
                'decision_id', gen_random_uuid(),
                'assigned_user_id', v_chosen.user_account_id,
                'assigned_role_id', v_type.handled_by_role_id,
                'table_node_id', v_table,
                'service_area_id', v_area,
                'considered_count', v_count,
                'basis', v_chosen.basis))
    RETURNING id INTO v_event;

    PERFORM service.apply_request_event(v_event);

    -- FR-NOT-001. The event, and whoever should be told about it.
    PERFORM notify.emit(p_tenant_id, r.outlet_id, 'EVT-SERVICE-REQUESTED',
                        'service_request', p_request_id, r.correlation_id,
                        r.table_session_id,
                        jsonb_build_object('service_request_id', p_request_id,
                                           'request_type_code', v_type.code,
                                           'state', 'routed',
                                           'repeat_ordinal', r.repeat_ordinal));
    RETURN v_chosen.user_account_id;
END;
$$;


-- FR-SRV-003. A member of staff accepts, and the customer is told.
CREATE FUNCTION service.acknowledge_request(
    p_tenant_id uuid, p_request_id uuid, p_user_id uuid) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    r       service.service_request%ROWTYPE;
    v_type  service.request_type%ROWTYPE;
    v_event bigint;
BEGIN
    SELECT * INTO r FROM service.service_request
     WHERE id = p_request_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SERVICE_REQUEST_NOT_FOUND: no request % in scope', p_request_id
            USING ERRCODE = 'HS404';
    END IF;

    -- An escalated request may be accepted by the alternate it went to; a routed one by
    -- the person it was routed to. Anyone else acknowledging work assigned to somebody
    -- else is how a queue stops meaning anything.
    IF r.assigned_user_id IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION
            'REQUEST_NOT_YOURS: request % is assigned to somebody else; acknowledging '
            'another person''s work makes the assignment meaningless',
            p_request_id USING ERRCODE = 'HS403';
    END IF;

    SELECT * INTO v_type FROM service.request_type WHERE id = r.request_type_id;

    INSERT INTO service.service_request_event
        (tenant_id, outlet_id, service_request_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, before, after)
    VALUES (p_tenant_id, r.outlet_id, p_request_id,
            service.next_sequence(p_tenant_id, p_request_id), 'acknowledged', 'staff',
            p_user_id, r.correlation_id,
            jsonb_build_object('state', r.state),
            jsonb_build_object('state', 'acknowledged'))
    RETURNING id INTO v_event;

    PERFORM service.apply_request_event(v_event);

    PERFORM notify.emit(p_tenant_id, r.outlet_id, 'EVT-SERVICE-ACKNOWLEDGED',
                        'service_request', p_request_id, r.correlation_id,
                        r.table_session_id,
                        jsonb_build_object('service_request_id', p_request_id,
                                           'request_type_code', v_type.code,
                                           'previous_state', r.state,
                                           'state', 'acknowledged'));
END;
$$;


CREATE FUNCTION service.start_request(
    p_tenant_id uuid, p_request_id uuid, p_user_id uuid) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    r       service.service_request%ROWTYPE;
    v_event bigint;
BEGIN
    SELECT * INTO r FROM service.service_request
     WHERE id = p_request_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SERVICE_REQUEST_NOT_FOUND: no request % in scope', p_request_id
            USING ERRCODE = 'HS404';
    END IF;
    IF r.assigned_user_id IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION
            'REQUEST_NOT_YOURS: request % is assigned to somebody else', p_request_id
            USING ERRCODE = 'HS403';
    END IF;

    INSERT INTO service.service_request_event
        (tenant_id, outlet_id, service_request_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, before, after)
    VALUES (p_tenant_id, r.outlet_id, p_request_id,
            service.next_sequence(p_tenant_id, p_request_id), 'started', 'staff',
            p_user_id, r.correlation_id,
            jsonb_build_object('state', r.state),
            jsonb_build_object('state', 'in_progress'))
    RETURNING id INTO v_event;

    PERFORM service.apply_request_event(v_event);
END;
$$;


-- FR-SRV-005. Completion says how it went, and 'not_possible' owes a registered reason.
CREATE FUNCTION service.complete_request(
    p_tenant_id uuid, p_request_id uuid, p_user_id uuid,
    p_status service.completion_status,
    p_reason_code_id uuid DEFAULT NULL,
    p_note text DEFAULT NULL) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    r       service.service_request%ROWTYPE;
    v_type  service.request_type%ROWTYPE;
    v_kind  service.request_event_kind;
    v_event bigint;
BEGIN
    SELECT * INTO r FROM service.service_request
     WHERE id = p_request_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SERVICE_REQUEST_NOT_FOUND: no request % in scope', p_request_id
            USING ERRCODE = 'HS404';
    END IF;
    IF r.assigned_user_id IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION
            'REQUEST_NOT_YOURS: request % is assigned to somebody else', p_request_id
            USING ERRCODE = 'HS403';
    END IF;

    IF p_status = 'not_possible' THEN
        IF NOT EXISTS (SELECT 1 FROM config.reason_code
                        WHERE id = p_reason_code_id AND tenant_id = p_tenant_id
                          AND category = 'service_failure' AND status = 'active') THEN
            RAISE EXCEPTION
                'COMPLETION_REASON_INVALID: % is not an active service_failure reason '
                'code, and a request that could not be done owes an account of why',
                p_reason_code_id USING ERRCODE = 'HS400';
        END IF;
    END IF;

    SELECT * INTO v_type FROM service.request_type WHERE id = r.request_type_id;

    -- SM-SERVICE-REQUEST has two ways out of in_progress and they mean different things:
    -- completed is the work being done, unresolved is it being abandoned with a reason.
    v_kind := CASE WHEN p_status = 'not_possible' THEN 'unresolved' ELSE 'completed' END;

    INSERT INTO service.service_request_event
        (tenant_id, outlet_id, service_request_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, reason_code_id, before, after)
    VALUES (p_tenant_id, r.outlet_id, p_request_id,
            service.next_sequence(p_tenant_id, p_request_id), v_kind, 'staff',
            p_user_id, r.correlation_id, p_reason_code_id,
            jsonb_build_object('state', r.state),
            jsonb_build_object('state', v_kind::text,
                               'completion_status', p_status,
                               'completion_note', p_note))
    RETURNING id INTO v_event;

    PERFORM service.apply_request_event(v_event);

    PERFORM notify.emit(p_tenant_id, r.outlet_id, 'EVT-SERVICE-COMPLETED',
                        'service_request', p_request_id, r.correlation_id,
                        r.table_session_id,
                        jsonb_build_object('service_request_id', p_request_id,
                                           'request_type_code', v_type.code,
                                           'state', v_kind::text));
END;
$$;


-- 'new -> cancelled: customer withdraws'. Only from 'new', because that is the only edge
-- the package declares — once somebody has been sent, withdrawing is a completion.
CREATE FUNCTION service.cancel_request(
    p_tenant_id uuid, p_request_id uuid, p_guest_session_id uuid) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    r       service.service_request%ROWTYPE;
    v_event bigint;
BEGIN
    SELECT * INTO r FROM service.service_request
     WHERE id = p_request_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SERVICE_REQUEST_NOT_FOUND: no request % in scope', p_request_id
            USING ERRCODE = 'HS404';
    END IF;
    IF r.raised_by_guest_session_id IS DISTINCT FROM p_guest_session_id THEN
        RAISE EXCEPTION
            'REQUEST_NOT_YOURS: a request is withdrawn by the guest who raised it'
            USING ERRCODE = 'HS403';
    END IF;

    INSERT INTO service.service_request_event
        (tenant_id, outlet_id, service_request_id, sequence_number, kind, actor_kind,
         actor_guest_session_id, correlation_id, before, after)
    VALUES (p_tenant_id, r.outlet_id, p_request_id,
            service.next_sequence(p_tenant_id, p_request_id), 'cancelled', 'guest',
            p_guest_session_id, r.correlation_id,
            jsonb_build_object('state', r.state),
            jsonb_build_object('state', 'cancelled'))
    RETURNING id INTO v_event;

    PERFORM service.apply_request_event(v_event);
END;
$$;


-- 'routed -> expired: session closes/policy'. A sweep, like M1-C's retention and M3-B's
-- uncollected escalation, rather than a timer nobody can inspect.
CREATE FUNCTION service.expire_requests_for_session(
    p_tenant_id uuid, p_table_session_id uuid) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    r       record;
    v_event bigint;
    v_count integer := 0;
BEGIN
    FOR r IN
        SELECT * FROM service.service_request
         WHERE tenant_id = p_tenant_id AND table_session_id = p_table_session_id
           AND state = 'routed'
         ORDER BY raised_at
    LOOP
        INSERT INTO service.service_request_event
            (tenant_id, outlet_id, service_request_id, sequence_number, kind, actor_kind,
             correlation_id, before, after)
        VALUES (p_tenant_id, r.outlet_id, r.id,
                service.next_sequence(p_tenant_id, r.id), 'expired', 'system',
                r.correlation_id,
                jsonb_build_object('state', r.state),
                jsonb_build_object('state', 'expired'))
        RETURNING id INTO v_event;

        PERFORM service.apply_request_event(v_event);
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END;
$$;


-- FR-SRV-004 and FR-NOT-011. Past its deadline and still unacknowledged, a request moves
-- to somebody else and says by how much it was late. The alternate is read from the
-- outlet's service policy: who supervises is a decision an outlet makes, and a default
-- would be this schema choosing an accountable person on a restaurant's behalf.
CREATE FUNCTION service.escalate_overdue_requests(
    p_tenant_id uuid, p_outlet_id uuid) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_policy    jsonb := ordering.require_policy(p_tenant_id, p_outlet_id, 'service');
    v_role_code text;
    v_role_id   uuid;
    r           record;
    v_to        uuid;
    v_event     bigint;
    v_count     integer := 0;
    v_type      service.request_type%ROWTYPE;
BEGIN
    IF NOT (v_policy ? 'service_escalation_role_code') THEN
        RAISE EXCEPTION
            'SERVICE_POLICY_INCOMPLETE: the service policy for outlet % names no '
            'service_escalation_role_code; who an unanswered request escalates TO is a '
            'decision an outlet makes, not a default this schema picks', p_outlet_id
            USING ERRCODE = 'HS412';
    END IF;
    v_role_code := v_policy ->> 'service_escalation_role_code';

    SELECT id INTO v_role_id FROM identity.role
     WHERE tenant_id = p_tenant_id AND role_code = v_role_code AND status = 'active';
    IF v_role_id IS NULL THEN
        RAISE EXCEPTION
            'SERVICE_ESCALATION_ROLE_ABSENT: the service policy names role %, and this '
            'tenant has no active role by that code', v_role_code USING ERRCODE = 'HS412';
    END IF;

    FOR r IN
        SELECT * FROM service.service_request
         WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id
           AND state = 'routed' AND now() > sla_due_at
         ORDER BY sla_due_at
    LOOP
        -- Anyone holding the escalation role who is not already the person who did not
        -- answer. Available first, then anyone: an escalation that found nobody
        -- available would leave the request exactly where it was.
        SELECT m.user_account_id INTO v_to
          FROM identity.membership m
          LEFT JOIN service.staff_presence sp
                 ON sp.tenant_id = m.tenant_id AND sp.outlet_id = m.outlet_id
                AND sp.user_account_id = m.user_account_id
         WHERE m.tenant_id = p_tenant_id AND m.outlet_id = p_outlet_id
           AND m.role_id = v_role_id AND m.status = 'active'
           AND m.user_account_id IS DISTINCT FROM r.assigned_user_id
         ORDER BY (coalesce(sp.state, 'offline') = 'available') DESC,
                  m.user_account_id
         LIMIT 1;

        CONTINUE WHEN v_to IS NULL;

        SELECT * INTO v_type FROM service.request_type WHERE id = r.request_type_id;

        INSERT INTO service.service_request_event
            (tenant_id, outlet_id, service_request_id, sequence_number, kind, actor_kind,
             correlation_id, before, after)
        VALUES (p_tenant_id, r.outlet_id, r.id,
                service.next_sequence(p_tenant_id, r.id), 'escalated', 'system',
                r.correlation_id,
                jsonb_build_object('state', r.state,
                                   'from_user_id', r.assigned_user_id),
                jsonb_build_object(
                    'escalation_id', gen_random_uuid(),
                    'state', 'escalated',
                    'from_user_id', r.assigned_user_id,
                    'to_user_id', v_to,
                    'sla_due_at', r.sla_due_at,
                    'overdue_seconds',
                        floor(extract(epoch FROM now() - r.sla_due_at))::integer,
                    'basis', 'unacknowledged past the configured deadline; escalated to '
                             || v_role_code))
        RETURNING id INTO v_event;

        PERFORM service.apply_request_event(v_event);

        PERFORM notify.emit(p_tenant_id, r.outlet_id, 'EVT-SERVICE-ESCALATED',
                            'service_request', r.id, r.correlation_id,
                            r.table_session_id,
                            jsonb_build_object(
                                'service_request_id', r.id,
                                'request_type_code', v_type.code,
                                'state', 'escalated',
                                'sla_due_at', r.sla_due_at,
                                'overdue_seconds',
                                    floor(extract(epoch FROM now() - r.sla_due_at))::integer));
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END;
$$;


-- ===========================================================================
-- Emission (FR-NOT-001) and recipient resolution (FR-NOT-005)
-- ===========================================================================
-- The emitter resolves its own recipients. Letting a caller pass them would put the
-- decision about who may be told a thing in the hands of whoever emits it, which is the
-- same shape as letting a caller pass an audience to a note reader — the defect M3-A
-- closed by having the reader name its audience instead.

CREATE FUNCTION notify.accountable_staff(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (user_account_id uuid)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_policy jsonb := ordering.require_policy(p_tenant_id, p_outlet_id, 'service');
    v_code   text;
BEGIN
    IF NOT (v_policy ? 'critical_alert_role_code') THEN
        RAISE EXCEPTION
            'SERVICE_POLICY_INCOMPLETE: the service policy for outlet % names no '
            'critical_alert_role_code; FR-NOT-005 asks for accountable staff and who is '
            'accountable is not a default', p_outlet_id USING ERRCODE = 'HS412';
    END IF;
    v_code := v_policy ->> 'critical_alert_role_code';

    RETURN QUERY
    SELECT m.user_account_id
      FROM identity.membership m
      JOIN identity.role ro ON ro.tenant_id = m.tenant_id AND ro.id = m.role_id
     WHERE m.tenant_id = p_tenant_id AND m.outlet_id = p_outlet_id
       AND m.status = 'active' AND ro.role_code = v_code AND ro.status = 'active'
     ORDER BY m.user_account_id;
END;
$$;

COMMENT ON FUNCTION notify.accountable_staff(uuid, uuid) IS
    'FR-NOT-005. A critical alert goes to whoever the outlet says is accountable, and an '
    'outlet that has not said is refused rather than given a guess — the same rule '
    'M3-B applied to the capacity response.';


-- A guest is on a table session through service.session_participant, not by a column on
-- the guest session: M2-B modelled it that way because one device can join, leave and
-- rejoin, and because a table session can be merged into another. "Live" therefore means
-- three things at once — still a participant, not expired, not anonymised — and writing
-- that out at five call sites is how four of them come to disagree.
CREATE FUNCTION service.guest_is_live_on_session(
    p_tenant_id uuid, p_guest_session_id uuid, p_table_session_id uuid)
RETURNS boolean
LANGUAGE sql STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
          FROM service.session_participant sp
          JOIN service.guest_session gs
            ON gs.tenant_id = sp.tenant_id AND gs.id = sp.guest_session_id
         WHERE sp.tenant_id = p_tenant_id
           AND sp.guest_session_id = p_guest_session_id
           AND sp.table_session_id = p_table_session_id
           AND sp.left_at IS NULL
           AND gs.anonymized_at IS NULL
           AND gs.expires_at > now());
$$;

COMMENT ON FUNCTION service.guest_is_live_on_session(uuid, uuid, uuid) IS
    'Still a participant, not anonymised, not expired. One definition, because five '
    'call sites with three conditions each is four chances to drop one.';

CREATE FUNCTION notify.emit(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_event_id text,
    p_subject_kind ordering.artifact_kind,
    p_subject_id uuid,
    p_correlation_id uuid,
    p_table_session_id uuid,
    p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, notify, service, ordering, identity, menu, config, public
AS $$
DECLARE
    v_event    notify.catalog_event%ROWTYPE;
    v_locale   menu.customer_locale;
    v_id       uuid;
    v_dedup    text;
    v_staff    uuid;
    v_guest    uuid;
BEGIN
    SELECT * INTO v_event FROM notify.catalog_event WHERE event_id = p_event_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'NOTIFICATION_KIND_UNKNOWN: % is not in the event catalog', p_event_id
            USING ERRCODE = 'HS404';
    END IF;
    IF NOT v_event.has_producer THEN
        -- The kinds whose domains arrive at M4 and M5a are in the catalog and nothing
        -- emits them. If something tries, that is a domain being stubbed rather than
        -- deferred, and it stops here.
        RAISE EXCEPTION
            'NOTIFICATION_KIND_HAS_NO_PRODUCER: % belongs to % and nothing in this gate '
            'produces it; emitting one would be a stub wearing a real kind''s name',
            p_event_id, v_event.milestone USING ERRCODE = 'HS501';
    END IF;

    SELECT coalesce(ts.customer_locale, 'en'::menu.customer_locale) INTO v_locale
      FROM service.table_session ts
     WHERE ts.tenant_id = p_tenant_id AND ts.id = p_table_session_id;
    v_locale := coalesce(v_locale, 'en'::menu.customer_locale);

    -- FR-NOT-007's key. One event about one subject in one state is one notification,
    -- however many times the producing path runs.
    v_dedup := p_event_id || '|' || p_subject_id::text || '|'
               || coalesce(p_payload ->> 'state', '-');

    SELECT id INTO v_id FROM notify.notification
     WHERE tenant_id = p_tenant_id AND dedup_key = v_dedup;

    IF v_id IS NULL THEN
        v_id := gen_random_uuid();
        INSERT INTO notify.notification
            (id, tenant_id, outlet_id, event_id, subject_kind, subject_id,
             correlation_id, dedup_key, payload)
        VALUES (v_id, p_tenant_id, p_outlet_id, p_event_id, p_subject_kind, p_subject_id,
                p_correlation_id, v_dedup, p_payload);
    END IF;

    -- STAFF recipients. A critical alert goes to accountable staff; an ordinary one to
    -- whoever the subject makes responsible.
    --
    -- Note the asymmetry with the customer block below, which is deliberate. A missing
    -- CUSTOMER template means this kind is not a guest's business — a kitchen exception
    -- is not — so no notice is created. A missing STAFF template is a configuration
    -- defect: FR-NOT-003 requires one for every M3 event, and somebody who should have
    -- been told was not. So the notice IS created, fails with template_missing, and
    -- ends up in the dead-letter queue where an operator can see it. Silence would be
    -- the worse of the two answers.
    IF v_event.severity = 'critical' THEN
        FOR v_staff IN SELECT a.user_account_id
                         FROM notify.accountable_staff(p_tenant_id, p_outlet_id) a
        LOOP
            INSERT INTO notify.notice
                (id, tenant_id, outlet_id, notification_id, audience,
                 recipient_user_id, locale)
            VALUES (gen_random_uuid(), p_tenant_id, p_outlet_id, v_id, 'staff',
                    v_staff, 'en')
            ON CONFLICT DO NOTHING;
        END LOOP;
    ELSE
        FOR v_staff IN
            SELECT sr.assigned_user_id FROM service.service_request sr
             WHERE sr.tenant_id = p_tenant_id AND sr.id = p_subject_id
               AND p_subject_kind = 'service_request' AND sr.assigned_user_id IS NOT NULL
            UNION
            SELECT tow.primary_waiter_user_id FROM service.table_ownership tow
             WHERE tow.tenant_id = p_tenant_id
               AND tow.table_session_id = p_table_session_id
               AND tow.effective_to IS NULL
        LOOP
            CONTINUE WHEN v_staff IS NULL;
            INSERT INTO notify.notice
                (id, tenant_id, outlet_id, notification_id, audience,
                 recipient_user_id, locale)
            VALUES (gen_random_uuid(), p_tenant_id, p_outlet_id, v_id, 'staff',
                    v_staff, 'en')
            ON CONFLICT DO NOTHING;
        END LOOP;
    END IF;

    -- CUSTOMER recipients: the guests on the table session, in the session's language.
    -- Only where a customer template exists for this kind — a kitchen exception is not
    -- a guest's business, and the absence of a template is how that is said.
    IF EXISTS (SELECT 1 FROM notify.template t
                WHERE t.tenant_id = p_tenant_id AND t.event_id = p_event_id
                  AND t.audience = 'customer' AND t.status = 'active') THEN
        FOR v_guest IN
            SELECT sp.guest_session_id FROM service.session_participant sp
             WHERE sp.tenant_id = p_tenant_id
               AND sp.table_session_id = p_table_session_id
               AND service.guest_is_live_on_session(p_tenant_id, sp.guest_session_id,
                                                    p_table_session_id)
             ORDER BY sp.guest_session_id
        LOOP
            INSERT INTO notify.notice
                (id, tenant_id, outlet_id, notification_id, audience,
                 recipient_guest_session_id, locale)
            VALUES (gen_random_uuid(), p_tenant_id, p_outlet_id, v_id, 'customer',
                    v_guest, v_locale)
            ON CONFLICT DO NOTHING;
        END LOOP;
    END IF;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION notify.emit IS
    'FR-NOT-001. Records what happened and who should be told, and sends nothing: '
    'notice is notify.send_pending(), so an emission that cannot reach somebody '
    'does not roll back the thing that happened.';


-- ===========================================================================
-- Notice, and the three ways it genuinely fails (FR-NOT-003, FR-INT-007)
-- ===========================================================================
-- IN-APP NOTICE IS A WRITE TO AN INBOX. There is no channel at this gate: outlet-local
-- notice is M5a's and an adapter invented here would be a stub with nothing behind it.
-- What a write to an inbox can genuinely fail for is a short list, and all three are
-- domain facts rather than injected faults:
--
--   template_missing          — FR-NOT-003 requires an approved template in the
--                               recipient's language. There isn't one.
--   recipient_not_authorized  — a staff recipient whose membership was withdrawn between
--                               emission and notice. In scope when the event happened,
--                               out of scope when it was about to be told.
--   recipient_out_of_scope    — a guest session revoked, or belonging to a table session
--                               that has since closed or moved outlet.
--
-- The second is the sharpest and is a real race rather than a contrivance: an emission
-- resolves recipients from the state at the moment something happened, and notice
-- happens afterwards. It is the same boundary as M2-B's FOREIGN_SESSION_ACCEPTED.
--
-- WHEN M5a ADDS A TRANSPORT, ITS FAILURES REACH THE SAME QUEUE THROUGH THE SAME DOOR —
-- integration.dead_letter_job(). That is written here as prose deliberately: there is no
-- adapter seam in this file, because an abstraction with one implementation has no
-- second case to prove it right.

CREATE FUNCTION notify.render_for(
    p_tenant_id uuid, p_event_id text, p_audience notify.audience,
    p_locale menu.customer_locale) RETURNS text
LANGUAGE sql STABLE
AS $$
    -- The approved translation in the recipient's language, or the English source when
    -- the audience is staff or the language is English. FR-I18N-008's approved fallback:
    -- English is the fallback and it is a real approved string, not a key name.
    SELECT coalesce(
        (SELECT tr.translated_text
           FROM menu.translation tr
          WHERE tr.tenant_id = p_tenant_id
            AND tr.entity = 'notification_template'
            AND tr.entity_id = t.id
            AND tr.field_name = 'body'
            AND tr.locale = p_locale
            AND tr.state = 'approved'),
        CASE WHEN p_locale = 'en' OR p_audience = 'staff' THEN t.source_text END)
      FROM notify.template t
     WHERE t.tenant_id = p_tenant_id AND t.event_id = p_event_id
       AND t.audience = p_audience AND t.status = 'active';
$$;

COMMENT ON FUNCTION notify.render_for IS
    'FR-NOT-003 and FR-I18N-008. The approved body in the recipient''s language, falling '
    'back to the approved English source only where the fallback rules permit it. NULL '
    'means there is nothing approved to say, which is a notice failure rather than a '
    'blank message.';


CREATE FUNCTION notify.send_pending(
    p_tenant_id uuid, p_outlet_id uuid, p_max_attempts integer DEFAULT 3)
RETURNS TABLE (sent integer, failed integer, dead_lettered integer)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, notify, service, identity, ordering, menu, integration, config, public
AS $$
DECLARE
    d          record;
    v_text     text;
    v_reason   notify.failure_reason;
    v_sent integer := 0;
    v_failed    integer := 0;
    v_dead      integer := 0;
BEGIN
    FOR d IN
        SELECT dl.*, n.event_id, n.correlation_id
          FROM notify.notice dl
          JOIN notify.notification n
            ON n.tenant_id = dl.tenant_id AND n.id = dl.notification_id
         WHERE dl.tenant_id = p_tenant_id AND dl.outlet_id = p_outlet_id
           AND dl.state IN ('pending', 'failed')
         ORDER BY dl.created_at, dl.id
    LOOP
        v_reason := NULL;

        -- Authorization, asked NOW rather than at emission. A membership withdrawn in
        -- between is exactly the case this ordering exists to catch.
        IF d.audience = 'staff' THEN
            IF NOT EXISTS (SELECT 1 FROM identity.membership m
                            WHERE m.tenant_id = d.tenant_id AND m.outlet_id = d.outlet_id
                              AND m.user_account_id = d.recipient_user_id
                              AND m.status = 'active') THEN
                v_reason := 'recipient_not_authorized';
            END IF;
        ELSE
            IF NOT EXISTS (
                SELECT 1 FROM service.session_participant sp
                  JOIN service.table_session ts
                    ON ts.tenant_id = sp.tenant_id AND ts.id = sp.table_session_id
                 WHERE sp.tenant_id = d.tenant_id
                   AND sp.guest_session_id = d.recipient_guest_session_id
                   AND ts.state = 'open' AND ts.outlet_id = d.outlet_id
                   AND service.guest_is_live_on_session(
                           sp.tenant_id, sp.guest_session_id, sp.table_session_id)) THEN
                v_reason := 'recipient_out_of_scope';
            END IF;
        END IF;

        IF v_reason IS NULL THEN
            v_text := notify.render_for(d.tenant_id, d.event_id, d.audience, d.locale);
            IF v_text IS NULL THEN
                v_reason := 'template_missing';
            END IF;
        END IF;

        IF v_reason IS NULL THEN
            UPDATE notify.notice
               SET state = 'sent', rendered_text = v_text,
                   sent_at = now(), attempts = attempts + 1,
                   last_failure = NULL, last_failed_at = NULL
             WHERE id = d.id;
            v_sent := v_sent + 1;
        ELSE
            UPDATE notify.notice
               SET state = CASE WHEN attempts + 1 >= p_max_attempts
                                THEN 'dead_lettered'::notify.notice_state
                                ELSE 'failed'::notify.notice_state END,
                   attempts = attempts + 1,
                   last_failure = v_reason, last_failed_at = now()
             WHERE id = d.id;

            IF d.attempts + 1 >= p_max_attempts THEN
                PERFORM integration.dead_letter_job(
                    d.tenant_id, d.outlet_id, 'notification_notice', d.id,
                    d.correlation_id, v_reason::text, d.attempts + 1);
                v_dead := v_dead + 1;
            ELSE
                v_failed := v_failed + 1;
            END IF;
        END IF;
    END LOOP;

    sent := v_sent; failed := v_failed; dead_lettered := v_dead;
    RETURN NEXT;
END;
$$;


-- The one door into the queue. M4's payment adapters and M5a's synchronization call this
-- with their own job_kind when they exist; nothing is built here in advance to receive
-- them.
CREATE FUNCTION integration.dead_letter_job(
    p_tenant_id uuid, p_outlet_id uuid, p_job_kind integration.job_kind,
    p_subject_id uuid, p_correlation_id uuid, p_reason text, p_attempts integer)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, integration, public
AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO integration.dead_letter
        (id, tenant_id, outlet_id, job_kind, subject_id, failure_reason, attempts,
         first_failed_at, last_failed_at, correlation_id)
    VALUES (gen_random_uuid(), p_tenant_id, p_outlet_id, p_job_kind, p_subject_id,
            p_reason, p_attempts, now(), now(), p_correlation_id)
    ON CONFLICT (tenant_id, job_kind, subject_id) DO UPDATE
       SET attempts = EXCLUDED.attempts,
           failure_reason = EXCLUDED.failure_reason,
           last_failed_at = EXCLUDED.last_failed_at,
           state = 'open', resolved_at = NULL, resolved_by_user_id = NULL
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;


-- FR-INT-007's safe replay. SAFE MEANS THE REPLAY CANNOT CAUSE THE DUPLICATE THE
-- ORIGINAL WAS REFUSED FOR — so it does not re-emit anything and does not create a
-- notice. It resets the EXISTING notice to pending and lets the ordinary path run,
-- which is the same path with the same unique index under it. A replay that re-emitted
-- would produce a second notification for one event, which is the FR-NOT-007 duplicate
-- wearing an operator's authorization.
CREATE FUNCTION integration.replay_dead_letter(
    p_tenant_id uuid, p_dead_letter_id uuid, p_user_id uuid, p_note text DEFAULT NULL)
RETURNS boolean
-- SECURITY DEFINER, like every other writer in this slice: the queue and the notices it
-- points at are read-only to the application role, so this function is the only way an
-- entry is ever resolved and the only way a notice ever goes back to pending. An
-- operator control that needed a write grant would have made every other write path
-- possible too.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, integration, notify, public
AS $$
DECLARE
    dl      integration.dead_letter%ROWTYPE;
    v_moved integer;
BEGIN
    SELECT * INTO dl FROM integration.dead_letter
     WHERE id = p_dead_letter_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'DEAD_LETTER_NOT_FOUND: no entry % in scope', p_dead_letter_id
            USING ERRCODE = 'HS404';
    END IF;
    IF dl.state <> 'open' THEN
        RAISE EXCEPTION
            'DEAD_LETTER_NOT_OPEN: entry % is %; replaying a resolved entry would run '
            'work somebody already accounted for', p_dead_letter_id, dl.state
            USING ERRCODE = 'HS409';
    END IF;
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION
            'REPLAY_WITHOUT_ACTOR: a replay names the operator who authorized it'
            USING ERRCODE = 'HS403';
    END IF;

    IF dl.job_kind = 'notification_notice' THEN
        -- The SAME notice row goes back to pending. No new notification, no new
        -- notice: there is nothing here that could produce a second alert.
        UPDATE notify.notice
           SET state = 'pending', last_failure = NULL, last_failed_at = NULL
         WHERE tenant_id = p_tenant_id AND id = dl.subject_id
           AND state = 'dead_lettered';
        GET DIAGNOSTICS v_moved = ROW_COUNT;
    ELSE
        RAISE EXCEPTION
            'DEAD_LETTER_KIND_UNREPLAYABLE: no replay is defined for %', dl.job_kind
            USING ERRCODE = 'HS501';
    END IF;

    UPDATE integration.dead_letter
       SET state = 'replayed', resolved_at = now(), resolved_by_user_id = p_user_id,
           resolution_note = p_note
     WHERE id = p_dead_letter_id;

    RETURN v_moved > 0;
END;
$$;

COMMENT ON FUNCTION integration.replay_dead_letter IS
    'FR-INT-007. Safe means the replay cannot cause the duplicate the original was '
    'refused for: it re-runs the SAME notice rather than re-emitting, so there is no '
    'path here that produces a second notification. tests/m3c proves that against the '
    'whole-schema differential M3-A built rather than by naming the tables it expects to '
    'stay still.';


-- ===========================================================================
-- Deep links (FR-NOT-009)
-- ===========================================================================

CREATE FUNCTION notify.issue_deep_link(
    p_tenant_id uuid, p_notice_id uuid, p_token text,
    p_target_kind ordering.artifact_kind, p_target_id uuid,
    p_scope_table_session_id uuid, p_valid_for interval DEFAULT interval '2 hours')
RETURNS uuid
-- SECURITY DEFINER for the same reason the folds are: notify.deep_link is read-only to
-- the application role, so that the ONLY way a link comes into existence is this
-- function, which stores the digest rather than the token it was handed.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, notify, service, ordering, public
AS $$
DECLARE
    d    notify.notice%ROWTYPE;
    v_id uuid;
BEGIN
    SELECT * INTO d FROM notify.notice
     WHERE id = p_notice_id AND tenant_id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'NOTICE_NOT_FOUND: no notice % in scope', p_notice_id
            USING ERRCODE = 'HS404';
    END IF;

    v_id := gen_random_uuid();
    INSERT INTO notify.deep_link
        (id, tenant_id, outlet_id, notice_id, token_digest, target_kind, target_id,
         scope_table_session_id, expires_at)
    VALUES (v_id, p_tenant_id, d.outlet_id, p_notice_id,
            sha256(convert_to(p_token, 'UTF8')), p_target_kind, p_target_id,
            p_scope_table_session_id, now() + p_valid_for);
    RETURN v_id;
END;
$$;


-- The resolver, and the whole of FR-NOT-009's authorization half. A link resolves only
-- for a caller who is inside the scope it was issued for: the same outlet, and for a
-- customer link the same table session. Every refusal is named, because "not found" for
-- an expired link and "not found" for somebody else's link are different facts and an
-- operator debugging the first should not be told the second.
CREATE FUNCTION notify.resolve_deep_link(
    p_tenant_id uuid, p_token text,
    p_guest_session_id uuid DEFAULT NULL, p_user_id uuid DEFAULT NULL)
RETURNS TABLE (target_kind ordering.artifact_kind, target_id uuid, outlet_id uuid)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, notify, service, identity, ordering, public
AS $$
DECLARE
    l notify.deep_link%ROWTYPE;
BEGIN
    SELECT * INTO l FROM notify.deep_link
     WHERE tenant_id = p_tenant_id
       AND token_digest = sha256(convert_to(p_token, 'UTF8'));
    IF NOT FOUND THEN
        RAISE EXCEPTION 'DEEP_LINK_UNKNOWN: no link matches that token'
            USING ERRCODE = 'HS404';
    END IF;

    IF now() > l.expires_at THEN
        RAISE EXCEPTION 'DEEP_LINK_EXPIRED: that link expired at %', l.expires_at
            USING ERRCODE = 'HS410';
    END IF;

    -- THE OUTLET BOUNDARY IS NOT CHECKED HERE, deliberately, and it is worth saying why
    -- rather than leaving a reader to wonder.
    --
    -- notify.deep_link carries row level security ENABLED and FORCED on the one
    -- isolation predicate, and this function is SECURITY DEFINER owned by the migration
    -- role — which FORCE covers too. A link belonging to another outlet is therefore
    -- invisible to the SELECT above, and the lookup fails with DEEP_LINK_UNKNOWN before
    -- any check written here could run.
    --
    -- An earlier draft compared app.current_outlet_id() to the link's outlet anyway, as
    -- a second lock. It was dead code: no caller exists for whom it can fire, and a
    -- guard that cannot fire is not a lock, it is a comment that looks like one. Outlet
    -- scope belongs to the predicate every table in this system shares. What this
    -- function owns is the SESSION scope, which no row predicate can express: being a
    -- guest somewhere is not being a guest HERE.
    IF l.scope_table_session_id IS NOT NULL THEN
        -- A customer link. The caller must be a live guest on the session it was issued
        -- for — being a guest somewhere is not enough, which is the FOREIGN_SESSION
        -- boundary M2-B drew.
        IF p_guest_session_id IS NULL
           OR NOT service.guest_is_live_on_session(p_tenant_id, p_guest_session_id,
                                                   l.scope_table_session_id) THEN
            RAISE EXCEPTION
                'DEEP_LINK_OUT_OF_SCOPE: that link belongs to another table session'
                USING ERRCODE = 'HS403';
        END IF;
    ELSE
        -- A staff link. The caller must hold an active membership at the outlet.
        IF p_user_id IS NULL
           OR NOT EXISTS (SELECT 1 FROM identity.membership m
                           WHERE m.tenant_id = p_tenant_id AND m.outlet_id = l.outlet_id
                             AND m.user_account_id = p_user_id AND m.status = 'active') THEN
            RAISE EXCEPTION
                'DEEP_LINK_OUT_OF_SCOPE: that link is for staff at this outlet'
                USING ERRCODE = 'HS403';
        END IF;
    END IF;

    RETURN QUERY SELECT l.target_kind, l.target_id, l.outlet_id;
END;
$$;


-- ===========================================================================
-- What a customer sees (FR-SRV-003, FR-SRV-009, FR-NOT-012, FR-I18N-001B/008)
-- ===========================================================================
-- FR-SRV-009: no staff identity unless the outlet has configured it. The default is
-- absence and the absence is fail-closed: a policy that says nothing discloses nothing,
-- rather than a policy that says nothing meaning "sure".

CREATE FUNCTION service.customer_status(
    p_tenant_id uuid, p_table_session_id uuid, p_guest_session_id uuid)
RETURNS TABLE (service_request_id uuid, request_label text, status_code text,
               status_text text, raised_at timestamptz, repeat_ordinal integer,
               handled_by text)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, service, notify, menu, ordering, identity, config, public
AS $$
DECLARE
    v_policy  jsonb;
    v_disclose boolean := false;
    v_locale  menu.customer_locale;
BEGIN
    -- The guest must be on this session. A status reader that took a session id and
    -- answered for anyone would be the M2-B boundary again.
    IF NOT service.guest_is_live_on_session(p_tenant_id, p_guest_session_id,
                                            p_table_session_id) THEN
        RAISE EXCEPTION
            'FOREIGN_SESSION: that guest session is not live on this table session'
            USING ERRCODE = 'HS403';
    END IF;

    SELECT coalesce(ts.customer_locale, 'en') INTO v_locale
      FROM service.table_session ts
     WHERE ts.tenant_id = p_tenant_id AND ts.id = p_table_session_id;

    -- FR-SRV-009. Fail closed: no policy, or no key, means no name.
    BEGIN
        v_policy := ordering.require_policy(
            p_tenant_id,
            (SELECT outlet_id FROM service.table_session
              WHERE tenant_id = p_tenant_id AND id = p_table_session_id),
            'service');
        v_disclose := coalesce((v_policy ->> 'disclose_staff_identity_to_customer')::boolean,
                               false);
    EXCEPTION WHEN others THEN
        v_disclose := false;
    END;

    RETURN QUERY
    SELECT sr.id,
           coalesce(
               (SELECT tr.translated_text FROM menu.translation tr
                 WHERE tr.tenant_id = p_tenant_id
                   AND tr.entity = 'service_request_type'
                   AND tr.entity_id = rt.id AND tr.field_name = 'label'
                   AND tr.locale = v_locale AND tr.state = 'approved'),
               rt.canonical_name),
           -- FR-SRV-003's two customer-visible statuses, plus the ends. The nine states
           -- the machine has are internal; a guest is told 'received' or 'being handled'
           -- because those are the two facts they can act on.
           CASE sr.state
               WHEN 'new'         THEN 'received'
               WHEN 'routed'      THEN 'received'
               WHEN 'acknowledged' THEN 'being_handled'
               WHEN 'in_progress' THEN 'being_handled'
               WHEN 'escalated'   THEN 'being_handled'
               WHEN 'completed'   THEN 'completed'
               WHEN 'cancelled'   THEN 'withdrawn'
               WHEN 'expired'     THEN 'closed'
               WHEN 'unresolved'  THEN 'closed'
           END,
           -- What was actually said to this guest, in the language they were told it in.
           (SELECT dl.rendered_text FROM notify.notice dl
              JOIN notify.notification n
                ON n.tenant_id = dl.tenant_id AND n.id = dl.notification_id
             WHERE dl.tenant_id = p_tenant_id
               AND dl.recipient_guest_session_id = p_guest_session_id
               AND n.subject_kind = 'service_request' AND n.subject_id = sr.id
               AND dl.state IN ('sent', 'read')
             ORDER BY dl.sent_at DESC LIMIT 1),
           sr.raised_at,
           sr.repeat_ordinal,
           CASE WHEN v_disclose AND sr.assigned_user_id IS NOT NULL
                THEN (SELECT ua.display_name FROM identity.user_account ua
                       WHERE ua.tenant_id = p_tenant_id AND ua.id = sr.assigned_user_id)
           END
      FROM service.service_request sr
      JOIN service.request_type rt
        ON rt.tenant_id = sr.tenant_id AND rt.id = sr.request_type_id
     WHERE sr.tenant_id = p_tenant_id AND sr.table_session_id = p_table_session_id
     ORDER BY sr.raised_at;
END;
$$;

COMMENT ON FUNCTION service.customer_status IS
    'FR-SRV-003, FR-SRV-009, FR-I18N-008. The label and the status in the session''s '
    'language, and the handler''s name ONLY where the outlet configured disclosure. The '
    'default is absence and it fails closed: an unreadable or silent policy discloses '
    'nothing rather than everything.';


-- FR-NOT-012's customer half and FR-I18N-001B. One timeline for a table session, in the
-- session's language: the order milestones M3-A and M3-B put on the order timeline, and
-- the service messages this gate sent. Merged at READ time rather than stored twice,
-- for the same reason M3-B derived the order's fulfillment state rather than storing it.
CREATE FUNCTION notify.customer_timeline(
    p_tenant_id uuid, p_table_session_id uuid, p_guest_session_id uuid)
RETURNS TABLE (occurred_at timestamptz, source text, summary text,
               locale menu.customer_locale)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, notify, service, ordering, menu, public
AS $$
DECLARE
    v_locale menu.customer_locale;
BEGIN
    IF NOT service.guest_is_live_on_session(p_tenant_id, p_guest_session_id,
                                            p_table_session_id) THEN
        RAISE EXCEPTION
            'FOREIGN_SESSION: that guest session is not live on this table session'
            USING ERRCODE = 'HS403';
    END IF;

    SELECT coalesce(ts.customer_locale, 'en') INTO v_locale
      FROM service.table_session ts
     WHERE ts.tenant_id = p_tenant_id AND ts.id = p_table_session_id;

    RETURN QUERY
    SELECT t.occurred_at, 'order'::text, t.summary, v_locale
      FROM ordering.customer_order o
      CROSS JOIN LATERAL ordering.customer_timeline(p_tenant_id, o.id) t
     WHERE o.tenant_id = p_tenant_id AND o.table_session_id = p_table_session_id
    UNION ALL
    SELECT dl.sent_at, 'service'::text, dl.rendered_text, dl.locale
      FROM notify.notice dl
     WHERE dl.tenant_id = p_tenant_id
       AND dl.recipient_guest_session_id = p_guest_session_id
       AND dl.state IN ('sent', 'read')
       AND dl.rendered_text IS NOT NULL
    ORDER BY 1;
END;
$$;


-- FR-NOT-012's staff half. THE DATA SURFACE IS COMPLETE HERE; the screen is M3-D's, and
-- the partial-closure register says so with M3-D named. M3-D adds a view over finished
-- data rather than finishing the data.
CREATE FUNCTION notify.staff_notification_center(
    p_tenant_id uuid, p_outlet_id uuid, p_user_id uuid)
RETURNS TABLE (notice_id uuid, event_id text, event_class notify.event_class,
               severity text, subject_kind ordering.artifact_kind, subject_id uuid,
               body text, state notify.notice_state, emitted_at timestamptz,
               sent_at timestamptz, read_at timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, notify, identity, ordering, public
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM identity.membership m
                    WHERE m.tenant_id = p_tenant_id AND m.outlet_id = p_outlet_id
                      AND m.user_account_id = p_user_id AND m.status = 'active') THEN
        RAISE EXCEPTION
            'NOT_A_MEMBER_OF_THIS_OUTLET: a notification centre shows one person their '
            'own notifications at an outlet they work at' USING ERRCODE = 'HS403';
    END IF;

    RETURN QUERY
    SELECT dl.id, n.event_id, ce.event_class, ce.severity, n.subject_kind, n.subject_id,
           dl.rendered_text, dl.state, n.emitted_at, dl.sent_at, dl.read_at
      FROM notify.notice dl
      JOIN notify.notification n
        ON n.tenant_id = dl.tenant_id AND n.id = dl.notification_id
      JOIN notify.catalog_event ce ON ce.event_id = n.event_id
     WHERE dl.tenant_id = p_tenant_id AND dl.outlet_id = p_outlet_id
       AND dl.audience = 'staff' AND dl.recipient_user_id = p_user_id
     ORDER BY n.emitted_at DESC, dl.id;
END;
$$;

COMMENT ON FUNCTION notify.staff_notification_center IS
    'FR-NOT-012, the staff half''s DATA. English, because FR-I18N-007 makes staff '
    'English. The rendering of it is M3-D''s and is recorded as a partial closure with '
    'M3-D named as the completing gate — creating tests/m3d makes this build fail until '
    'somebody goes back to it.';


-- ===========================================================================
-- Rebuild (FR-DAT-010, extended to service requests)
-- ===========================================================================

CREATE FUNCTION service.projection_digest(p_tenant_id uuid) RETURNS bytea
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, service, public
AS $$
    SELECT sha256(convert_to(coalesce(string_agg(part, E'\n' ORDER BY part), ''), 'UTF8'))
    FROM (
        SELECT 'request|' || r.id || '|' || r.table_session_id || '|'
               || coalesce(r.order_id::text, '-') || '|' || r.request_type_id || '|'
               || r.origin || '|' || r.state || '|'
               || coalesce(r.assigned_user_id::text, '-') || '|'
               || coalesce(r.assigned_role_id::text, '-') || '|' || r.customer_locale || '|'
               || r.dedup_group || '|' || r.repeat_ordinal || '|' || r.raised_at || '|'
               || r.sla_due_at || '|' || coalesce(r.acknowledged_at::text, '-') || '|'
               || coalesce(r.started_at::text, '-') || '|'
               || coalesce(r.completed_at::text, '-') || '|'
               || coalesce(r.escalated_at::text, '-') || '|'
               || coalesce(r.completion_status::text, '-') || '|'
               || coalesce(r.completion_reason_code_id::text, '-') || '|'
               || coalesce(r.completion_note, '-') || '|' || r.ledger_sequence AS part
        FROM service.service_request r WHERE r.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'routing|' || d.id || '|' || d.service_request_id || '|' || d.table_node_id
               || '|' || coalesce(d.service_area_id::text, '-') || '|'
               || d.required_role_id || '|' || d.considered_count || '|'
               || coalesce(d.chosen_user_id::text, '-') || '|' || d.basis || '|'
               || d.decided_at
        FROM service.request_routing_decision d WHERE d.tenant_id = p_tenant_id
        UNION ALL
        SELECT 'escalation|' || e.id || '|' || e.service_request_id || '|'
               || coalesce(e.from_user_id::text, '-') || '|' || e.to_user_id || '|'
               || e.sla_due_at || '|' || e.escalated_at || '|' || e.overdue_seconds
               || '|' || e.basis
        FROM service.request_escalation e WHERE e.tenant_id = p_tenant_id
    ) AS rendered;
$$;

CREATE FUNCTION service.drop_projections_for_rebuild(p_tenant_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, service, public
AS $$
BEGIN
    PERFORM set_config('service.applying_event', 'yes', true);
    DELETE FROM service.request_escalation WHERE tenant_id = p_tenant_id;
    DELETE FROM service.request_routing_decision WHERE tenant_id = p_tenant_id;
    DELETE FROM service.service_request WHERE tenant_id = p_tenant_id;
    PERFORM set_config('service.applying_event', '', true);
END;
$$;

CREATE FUNCTION service.rebuild_projections(p_tenant_id uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, service, ordering, public
AS $$
DECLARE
    v_event bigint;
    v_count integer := 0;
BEGIN
    PERFORM service.drop_projections_for_rebuild(p_tenant_id);
    FOR v_event IN
        SELECT id FROM service.service_request_event
         WHERE tenant_id = p_tenant_id ORDER BY id
    LOOP
        PERFORM service.apply_request_event(v_event);
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END;
$$;


-- ===========================================================================
-- One rebuild over THREE ledgers now
-- ===========================================================================
-- M3-B extended this from one ledger to two and learned why it had to: the fulfillment
-- fold writes into ordering — the station timeline and the ticket's correlation link —
-- so a rebuild that replayed only the order ledger left ordering's own digest wrong. The
-- REVERSED run is what found it, and only because M3-B had just landed.
--
-- The service fold writes into ordering too: FR-INT-014's service_request link. So the
-- same repair, one ledger further. Service projections come down before the orders they
-- reference and are replayed after them.
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
    -- Tickets reference order lines and service requests reference orders, so both come
    -- down first and are rebuilt below. The three ledgers are untouched throughout; only
    -- projections move.
    PERFORM fulfillment.drop_projections_for_rebuild(p_tenant_id);
    PERFORM service.drop_projections_for_rebuild(p_tenant_id);
    DELETE FROM ordering.order_line WHERE tenant_id = p_tenant_id;
    DELETE FROM ordering.customer_order WHERE tenant_id = p_tenant_id;

    PERFORM set_config('ordering.applying_event', '', true);

    FOR v_event IN
        SELECT id FROM ordering.order_event WHERE tenant_id = p_tenant_id ORDER BY id
    LOOP
        PERFORM ordering.apply_event(v_event);
        v_count := v_count + 1;
    END LOOP;

    FOR v_event IN
        SELECT id FROM fulfillment.ticket_event WHERE tenant_id = p_tenant_id ORDER BY id
    LOOP
        PERFORM fulfillment.apply_ticket_event(v_event);
        v_count := v_count + 1;
    END LOOP;

    -- And the service ledger, which restores the service_request links in the
    -- correlation chain (FR-INT-014).
    FOR v_event IN
        SELECT id FROM service.service_request_event
         WHERE tenant_id = p_tenant_id ORDER BY id
    LOOP
        PERFORM service.apply_request_event(v_event);
        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$;


-- ===========================================================================
-- A merge takes the requests with it (FR-TAB-007A)
-- ===========================================================================
-- service.merge_table_sessions() was written at M3-A and knows nothing about service
-- requests, because there were none. It is in a checksum-locked migration and it is not
-- replaced here: this hangs off the row it WRITES, so any path that merges two
-- occupancies re-parents the requests whether or not it remembered to.
--
-- A move needs nothing. A move changes which table a session sits at and not which
-- session a request belongs to, so the requests are already where they should be —
-- tests/m3c asserts that rather than assuming it.

CREATE FUNCTION service.reparent_requests_on_merge() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, service, ordering, public
AS $$
DECLARE
    r       record;
    v_event bigint;
BEGIN
    FOR r IN
        SELECT * FROM service.service_request
         WHERE tenant_id = NEW.tenant_id
           AND table_session_id = NEW.absorbed_session_id
         ORDER BY raised_at
    LOOP
        INSERT INTO service.service_request_event
            (tenant_id, outlet_id, service_request_id, sequence_number, kind,
             actor_kind, actor_user_id, correlation_id, before, after)
        VALUES (NEW.tenant_id, r.outlet_id, r.id,
                service.next_sequence(NEW.tenant_id, r.id), 'session_changed',
                'staff', NEW.merged_by_user_id, r.correlation_id,
                jsonb_build_object('table_session_id', r.table_session_id),
                jsonb_build_object('table_session_id', NEW.surviving_session_id))
        RETURNING id INTO v_event;

        PERFORM service.apply_request_event(v_event);
    END LOOP;
    RETURN NULL;
END;
$$;

-- Deferred, for the same reason M3-B's release trigger is: the merge is still moving
-- rows when this row is written, and the requests should be re-parented against the
-- state the transaction ends in.
CREATE CONSTRAINT TRIGGER session_merge_takes_the_requests
    AFTER INSERT ON service.session_merge
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION service.reparent_requests_on_merge();

REVOKE ALL ON FUNCTION service.reparent_requests_on_merge() FROM PUBLIC;


-- ===========================================================================
-- Row level security, on the same predicate as everything else
-- ===========================================================================

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'service.request_type', 'service.staff_presence',
        'service.service_request_event', 'service.service_request',
        'service.request_routing_decision', 'service.request_escalation',
        'notify.template', 'notify.notification', 'notify.notice',
        'notify.deep_link', 'integration.dead_letter']
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

-- service.transition and notify.catalog_event are NOT tenant data. One is
-- SM-SERVICE-REQUEST and the other is the package's event catalog; neither carries a
-- tenant column to scope by, both are readable by the application role and neither is
-- writable by it. service.transition is immutable at runtime by trigger as well.


-- ===========================================================================
-- Grants
-- ===========================================================================

GRANT USAGE ON SCHEMA notify TO hospitality_app;
GRANT USAGE ON SCHEMA integration TO hospitality_app;

-- The ledger: append and read, never UPDATE or DELETE. The trigger refuses those too.
GRANT SELECT, INSERT ON service.service_request_event TO hospitality_app;

-- Projections: READ ONLY. Every write goes through service.apply_request_event(), which
-- is SECURITY DEFINER — so the grant and the projection guard are two independent locks
-- rather than one lock described twice, exactly as at M3-A and M3-B.
GRANT SELECT ON service.service_request            TO hospitality_app;
GRANT SELECT ON service.request_routing_decision   TO hospitality_app;
GRANT SELECT ON service.request_escalation         TO hospitality_app;

-- Configuration the application reads and an administrator writes.
GRANT SELECT ON service.request_type    TO hospitality_app;
GRANT SELECT ON service.transition      TO hospitality_app;
GRANT SELECT ON notify.catalog_event    TO hospitality_app;
GRANT SELECT ON notify.template         TO hospitality_app;

-- Presence is the one table the application writes directly, and deliberately so: it is
-- not ledger-derived, it has no history to protect, and config.apply_retention() must be
-- able to DELETE from it as the application role for FR-SRV-007B's retention bound to
-- mean anything.
GRANT SELECT, INSERT, UPDATE, DELETE ON service.staff_presence TO hospitality_app;

-- Notifications and notices are written by definer functions; the application reads
-- them and marks its own as read.
GRANT SELECT ON notify.notification TO hospitality_app;
GRANT SELECT, UPDATE ON notify.notice TO hospitality_app;
GRANT SELECT ON notify.deep_link TO hospitality_app;
GRANT SELECT ON integration.dead_letter TO hospitality_app;

GRANT EXECUTE ON FUNCTION service.apply_request_event(bigint)      TO hospitality_app;
GRANT EXECUTE ON FUNCTION service.rebuild_projections(uuid)        TO hospitality_app;
GRANT EXECUTE ON FUNCTION service.projection_digest(uuid)          TO hospitality_app;
GRANT EXECUTE ON FUNCTION service.customer_status(uuid, uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION notify.customer_timeline(uuid, uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION notify.staff_notification_center(uuid, uuid, uuid)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION notify.resolve_deep_link(uuid, text, uuid, uuid)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION integration.replay_dead_letter(uuid, uuid, uuid, text)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION notify.send_pending(uuid, uuid, integer) TO hospitality_app;
GRANT EXECUTE ON FUNCTION notify.emit(
    uuid, uuid, text, ordering.artifact_kind, uuid, uuid, uuid, jsonb)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION notify.issue_deep_link(
    uuid, uuid, text, ordering.artifact_kind, uuid, uuid, interval) TO hospitality_app;

-- The helpers the folds use are NOT granted: they take a ledger row or write a
-- projection directly, and a caller holding EXECUTE could write a projection for an
-- event that was never in the ledger.
REVOKE ALL ON FUNCTION service.drop_projections_for_rebuild(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION integration.dead_letter_job(
    uuid, uuid, integration.job_kind, uuid, uuid, text, integer) FROM PUBLIC;
