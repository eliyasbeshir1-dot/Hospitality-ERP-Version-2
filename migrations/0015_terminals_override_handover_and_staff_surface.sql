-- ===========================================================================
-- 0015 — terminals, manager override, handover, and the staff surface
-- ===========================================================================
--
-- A GUEST ASKS. A WAITER ACTS ON BEHALF OF THE HOUSE. THE RULES ARE THE SAME RULES.
--
-- M3-D adds the staff side of a restaurant that already works: the terminals staff sign
-- in on, the screens they read, the override a supervisor authorizes and the handover
-- that moves responsibility from one person to another. It adds almost no rules, and
-- that is the point of the slice.
--
-- WHAT THIS MIGRATION DELIBERATELY DOES NOT CONTAIN
--
-- There is no second ordering path. FR-POS-003A says a waiter-entered order obeys the
-- identical menu, modifier, price, safety and authorization rules as a QR order, and
-- M3-A built ONE aggregate with a channel dimension precisely so that could be true:
-- ordering.submit_order() already takes ordering.order_origin, and 'waiter_entered' has
-- been a legal value since 0010. So this migration adds no pricing function, no
-- availability check, no allergen resolution and no second submission entry point. The
-- staff route calls what the guest route calls. tests/m3d asserts that from the CATALOG
-- rather than from a list, so a rule added at M4 that the staff side re-implements fails
-- without anybody remembering to extend a check.
--
-- There is no shift, roster or attendance model. FR-POS-007 asks for a handover
-- workflow: responsibility for open tables and open tasks moving from one named person
-- to another named person, acknowledged. That is a transfer, not a schedule. The three
-- words above are fenced and no identifier here names one.
--
-- There is no money. FR-POS-004 wants an unpaid balance on the table view; that figure
-- is M4's and this slice records the SLOT rather than inventing a number. The column
-- exists, is always NULL here, and says so — an invented zero would be a figure somebody
-- could act on, which is the defect the fee decision at M3-A already refused once.
--
-- WHY THE OVERRIDE IS SHAPED THE WAY IT IS
--
-- FR-POS-006 wants supervisor approval without sharing credentials or bypassing audit.
-- The failure mode is concrete: a manager walks over and types their password into the
-- waiter's terminal. Every system that treats that as legitimate has no way to tell it
-- apart from the compliant case afterwards.
--
-- identity.step_up_grant, built at M1-B, has exactly the property that makes the two
-- distinguishable BY CONSTRUCTION. A grant names a SESSION and no user at all; whose
-- authentication it represents is reachable only by following the session. So this
-- migration never takes an approver's identity as an argument — it DERIVES the approver
-- from the grant's session. A manager who authenticates into the waiter's session
-- creates a grant on the waiter's session, the derived approver is the waiter, and the
-- override refuses because approver and actor are the same person. Nothing polices the
-- rule; there is no way to express the violation.
--
-- The grant is also CONSUMED. One authentication authorizes one override, so an approval
-- cannot be replayed against a second action later in the shift.
--
-- Remote approval — a manager approving from their own device, elsewhere in the building
-- — would be a short-lived delegation token. That is a new secret to mint, digest,
-- expire and revoke, and minting secrets for transport is M5a's work. The extension
-- point is recorded here in prose: a delegation token would resolve to an approver
-- session and enter pos.approve_override() through the same door, with no change to the
-- property above.
-- ===========================================================================

CREATE SCHEMA pos;

COMMENT ON SCHEMA pos IS
    'The staff surface: terminals, role home, table view, operational search, manager '
    'override and handover. Ordering is NOT here — a waiter-entered order goes through '
    'ordering.submit_order() exactly as a guest-entered one does (FR-POS-003A).';


-- ===========================================================================
-- Terminals (FR-POS-001)
-- ===========================================================================
-- M1-A registered devices as organizational nodes with a human registration code.
-- M3-D adds the staff-side lifecycle on top: which PROFILE a device is registered as,
-- and how a compromised one is taken out of service.
--
-- Built as a table beside org.device_registration rather than as columns added to it.
-- The registration is M1-A's fact and has been true since 0001; the profile and the
-- revocation are this slice's, and a NOT NULL column added to a populated table needs a
-- default, which is how a device silently becomes a point-of-sale terminal because that
-- was first in the enum.

CREATE TYPE pos.terminal_profile AS ENUM ('point_of_sale', 'waiter_handheld', 'kitchen_display');

COMMENT ON TYPE pos.terminal_profile IS
    'The three profiles FR-POS-001 names. A profile decides which surface a terminal is '
    'allowed to open, so it is a registration fact rather than a preference.';

CREATE TABLE pos.terminal (
    device_id                 uuid PRIMARY KEY,
    tenant_id                 uuid NOT NULL,
    outlet_id                 uuid NOT NULL,
    profile                   pos.terminal_profile NOT NULL,
    registered_by_user_id     uuid NOT NULL,
    registered_at             timestamptz NOT NULL DEFAULT now(),
    revoked_at                timestamptz,
    revoked_by_user_id        uuid,
    revocation_reason_code_id uuid,

    CONSTRAINT terminal_tenant_id_unique UNIQUE (tenant_id, device_id),
    CONSTRAINT terminal_registration_fk FOREIGN KEY (device_id)
        REFERENCES org.device_registration (device_id) ON DELETE RESTRICT,
    CONSTRAINT terminal_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT terminal_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT terminal_registrar_fk FOREIGN KEY (tenant_id, registered_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT terminal_revoker_fk FOREIGN KEY (tenant_id, revoked_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT terminal_revocation_reason_fk FOREIGN KEY (tenant_id, revocation_reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,

    -- Taking a terminal out of service is destructive and states who and why, together.
    -- A revocation with no reason is an outage nobody can explain afterwards, and a
    -- reason with no revocation is a note on a live terminal.
    CONSTRAINT terminal_revocation_is_explained CHECK (
        (revoked_at IS NULL) = (revoked_by_user_id IS NULL)
        AND (revoked_at IS NULL) = (revocation_reason_code_id IS NULL))
);

COMMENT ON TABLE pos.terminal IS
    'FR-POS-001. A registered device bound to a tenant, an outlet and a profile, and the '
    'record of its revocation. Revoking is not a flag: pos.revoke_terminal() also ends '
    'every live session on the device and withdraws its terminal trust, because a '
    'compromised terminal whose sessions keep working has not been revoked.';

CREATE INDEX terminal_outlet_idx ON pos.terminal (tenant_id, outlet_id) WHERE revoked_at IS NULL;


CREATE FUNCTION pos.register_terminal(
    p_tenant_id   uuid,
    p_outlet_id   uuid,
    p_device_id   uuid,
    p_profile     pos.terminal_profile,
    p_actor_user_id uuid
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_node_kind org.node_kind;
BEGIN
    -- The device must be a DEVICE. M2-B learned this on the other side: a QR code that
    -- resolved to anything the tenant owned would have bound a guest to a kitchen.
    SELECT kind INTO v_node_kind FROM org.org_node
     WHERE tenant_id = p_tenant_id AND id = p_device_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'TERMINAL_NOT_REGISTERED: device % is not in scope', p_device_id
            USING ERRCODE = 'HS404';
    END IF;

    IF v_node_kind <> 'device' THEN
        RAISE EXCEPTION
            'TERMINAL_NOT_REGISTERED: % is a % and a terminal profile may only be given '
            'to a device', p_device_id, v_node_kind
            USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO pos.terminal
        (device_id, tenant_id, outlet_id, profile, registered_by_user_id)
    VALUES (p_device_id, p_tenant_id, p_outlet_id, p_profile, p_actor_user_id);

    RETURN p_device_id;
END;
$$;

COMMENT ON FUNCTION pos.register_terminal(uuid, uuid, uuid, pos.terminal_profile, uuid) IS
    'FR-POS-001. Binds a registered device to a profile at an outlet.';


CREATE FUNCTION pos.revoke_terminal(
    p_tenant_id      uuid,
    p_device_id      uuid,
    p_actor_user_id  uuid,
    p_reason_code_id uuid
) RETURNS integer
-- SECURITY DEFINER for one reason: revoking a terminal has to END THE SESSIONS ON IT,
-- and identity.session is not writable by the application role. A revocation that left
-- the sessions alive would be a label on a terminal that still takes orders. Row level
-- security is FORCED on every table this touches, so definer rights widen what may be
-- written and never which tenant's rows are visible.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pos, identity, config, public
AS $$
DECLARE
    v_terminal pos.terminal%ROWTYPE;
    v_sessions integer;
BEGIN
    SELECT * INTO v_terminal FROM pos.terminal
     WHERE tenant_id = p_tenant_id AND device_id = p_device_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'TERMINAL_NOT_REGISTERED: no terminal % in scope', p_device_id
            USING ERRCODE = 'HS404';
    END IF;

    IF v_terminal.revoked_at IS NOT NULL THEN
        RAISE EXCEPTION
            'TERMINAL_ALREADY_REVOKED: terminal % was revoked at %',
            p_device_id, v_terminal.revoked_at
            USING ERRCODE = 'HS409';
    END IF;

    -- A destructive action states a registered reason (FR-CFG-003, FR-UX-015). The FK
    -- would catch an invented id; this catches a reason from the wrong category, which
    -- is the mistake a busy manager actually makes.
    PERFORM 1 FROM config.reason_code
     WHERE tenant_id = p_tenant_id AND id = p_reason_code_id
       AND category = 'manager_override' AND status = 'active';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'DESTRUCTIVE_ACTION_WITHOUT_REASON: revoking a terminal needs an active '
            'manager_override reason code; % is not one', p_reason_code_id
            USING ERRCODE = 'HS422';
    END IF;

    UPDATE pos.terminal
       SET revoked_at = now(),
           revoked_by_user_id = p_actor_user_id,
           revocation_reason_code_id = p_reason_code_id
     WHERE tenant_id = p_tenant_id AND device_id = p_device_id;

    -- Trust withdrawn, so the device cannot be treated as a trusted terminal again
    -- without being re-registered.
    UPDATE identity.terminal_trust
       SET withdrawn_at = now()
     WHERE tenant_id = p_tenant_id AND device_id = p_device_id AND withdrawn_at IS NULL;

    -- And every live session ON the device ends. This is the half that makes the word
    -- "revoke" true.
    --
    -- The REASON travels with it. M1-B's session_revocation_consistent CHECK moves
    -- revoked_at and revoked_reason together, so a session ended with no stated reason
    -- cannot be stored — and 'administrator_revoked' is the truthful one here: a person
    -- took this terminal out of service, which is a different fact from a session that
    -- expired or was signed out.
    UPDATE identity.session
       SET revoked_at = now(),
           revoked_reason = 'administrator_revoked'
     WHERE tenant_id = p_tenant_id AND device_id = p_device_id AND revoked_at IS NULL;
    GET DIAGNOSTICS v_sessions = ROW_COUNT;

    RETURN v_sessions;
END;
$$;

COMMENT ON FUNCTION pos.revoke_terminal(uuid, uuid, uuid, uuid) IS
    'FR-POS-001. Revokes a compromised terminal: records who and why, withdraws its '
    'terminal trust and ends every live session on it, returning how many were ended.';


-- ===========================================================================
-- Manager override (FR-POS-006)
-- ===========================================================================
-- The record of a supervisor authorizing something a waiter could not do alone.
--
-- Both identities are on the row, and neither is optional. The ACTOR is whoever is
-- performing the action; the APPROVER is whoever authorized it. The two constraints
-- below are the whole security argument, and they are constraints rather than checks
-- performed by a function because a function can be called by a route that forgets.

CREATE TABLE pos.override_approval (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL,
    outlet_id           uuid NOT NULL,
    action_code         text NOT NULL,

    actor_user_id       uuid NOT NULL,
    actor_session_id    uuid NOT NULL,

    -- DERIVED from the step-up grant's session inside pos.approve_override(), never
    -- supplied by a caller. See the note at the head of this file.
    approver_user_id    uuid NOT NULL,
    approver_session_id uuid NOT NULL,
    step_up_grant_id    uuid NOT NULL,

    reason_code_id      uuid NOT NULL,
    reason_text         text,
    subject_kind        text NOT NULL,
    subject_id          uuid NOT NULL,
    approved_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT override_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT override_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT override_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT override_actor_fk FOREIGN KEY (tenant_id, actor_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT override_approver_fk FOREIGN KEY (tenant_id, approver_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT override_actor_session_fk FOREIGN KEY (tenant_id, actor_session_id)
        REFERENCES identity.session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT override_approver_session_fk FOREIGN KEY (tenant_id, approver_session_id)
        REFERENCES identity.session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT override_grant_fk FOREIGN KEY (step_up_grant_id)
        REFERENCES identity.step_up_grant (id) ON DELETE RESTRICT,
    CONSTRAINT override_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT override_action_not_blank CHECK (btrim(action_code) <> ''),
    CONSTRAINT override_subject_kind_not_blank CHECK (btrim(subject_kind) <> ''),

    -- A supervisor approving their own action is not an override, and one SESSION
    -- approving its own action is the credential-sharing case: the manager typed their
    -- password into the waiter's terminal, so the grant sits on the waiter's session and
    -- the derived approver comes back as the waiter.
    CONSTRAINT override_approver_is_not_the_actor CHECK (approver_user_id <> actor_user_id),
    CONSTRAINT override_sessions_are_not_the_same CHECK (approver_session_id <> actor_session_id),

    -- One grant authorizes one override. Without this, a legitimate approval earlier in
    -- the evening authorizes a second action later, which is the same defect the
    -- step-up recency window exists to prevent, one step removed.
    CONSTRAINT override_grant_used_once UNIQUE (step_up_grant_id)
);

COMMENT ON TABLE pos.override_approval IS
    'FR-POS-006. Supervisor approval with both identities and the step-up grant it '
    'rested on. approver_user_id is DERIVED from the grant''s session and is never a '
    'parameter, so a manager authenticating into the waiter''s session produces an '
    'approver equal to the actor and is refused by constraint rather than by policy.';

CREATE INDEX override_subject_idx
    ON pos.override_approval (tenant_id, subject_kind, subject_id);


CREATE FUNCTION pos.approve_override(
    p_tenant_id          uuid,
    p_outlet_id          uuid,
    p_action_code        text,
    p_approver_session_id uuid,
    p_reason_code_id     uuid,
    p_subject_kind       text,
    p_subject_id         uuid,
    p_reason_text        text DEFAULT NULL
) RETURNS uuid
-- SECURITY DEFINER because it reads identity.session and identity.step_up_grant to
-- establish who the approver is, and the application role holds no SELECT on either —
-- which is the point of that revocation. Note what is NOT a parameter: the approver's
-- user id. It is read from the grant's session, so there is no argument by which a
-- caller could claim to be somebody.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pos, identity, config, public
AS $$
DECLARE
    v_actor_session   identity.session%ROWTYPE;
    v_approver_session identity.session%ROWTYPE;
    v_action          identity.governed_action%ROWTYPE;
    v_grant           identity.step_up_grant%ROWTYPE;
    v_permitted       boolean;
    v_id              uuid;
BEGIN
    SELECT * INTO v_actor_session FROM identity.session
     WHERE id = app.current_session_id() AND revoked_at IS NULL AND expires_at > now();

    IF NOT FOUND THEN
        RAISE EXCEPTION 'SESSION_NOT_LIVE: no live session in context'
            USING ERRCODE = 'HS401';
    END IF;

    SELECT * INTO v_action FROM identity.governed_action
     WHERE tenant_id = p_tenant_id AND action_code = p_action_code;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'ACTION_NOT_REGISTERED: % is not a registered action', p_action_code
            USING ERRCODE = 'HS403';
    END IF;

    IF NOT v_action.step_up_required THEN
        RAISE EXCEPTION
            'OVERRIDE_WITHOUT_STEP_UP: % is not an action that requires stronger '
            'authentication, so approving it as an override would record an approval '
            'nothing asked for', p_action_code
            USING ERRCODE = 'HS409';
    END IF;

    SELECT * INTO v_approver_session FROM identity.session
     WHERE tenant_id = p_tenant_id AND id = p_approver_session_id
       AND revoked_at IS NULL AND expires_at > now();

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'OVERRIDE_WITHOUT_STEP_UP: the approving session is not live, so nothing '
            'was authorized by anybody'
            USING ERRCODE = 'HS403';
    END IF;

    -- THE PROPERTY. The approver is whoever owns the approving session. A manager who
    -- authenticated into the waiter's terminal is authenticated AS THAT SESSION, so this
    -- resolves to the waiter and the constraint below refuses.
    IF v_approver_session.user_account_id = v_actor_session.user_account_id THEN
        RAISE EXCEPTION
            'CREDENTIAL_SHARED_FOR_OVERRIDE: the approving session belongs to the same '
            'person performing the action. A supervisor authenticating into a waiter''s '
            'terminal is credential sharing, not delegation, and leaves an audit trail '
            'in which the compliant case and the violation are identical'
            USING ERRCODE = 'HS403';
    END IF;

    -- The approver's own role must grant the action. Absence denies, as at M1-B.
    SELECT EXISTS (
        SELECT 1
        FROM identity.membership m
        JOIN identity.role_action ra ON ra.role_id = m.role_id AND ra.tenant_id = m.tenant_id
        WHERE m.tenant_id       = p_tenant_id
          AND m.user_account_id = v_approver_session.user_account_id
          AND m.status          = 'active'
          AND (m.outlet_id IS NULL OR m.outlet_id = p_outlet_id)
          AND ra.action_code    = p_action_code
    ) INTO v_permitted;

    IF NOT v_permitted THEN
        RAISE EXCEPTION
            'ACTION_NOT_GRANTED: no active membership grants % to the approver',
            p_action_code
            USING ERRCODE = 'HS403';
    END IF;

    IF v_approver_session.established_with < v_action.minimum_strength THEN
        RAISE EXCEPTION
            'LOW_RISK_CREDENTIAL_USED_FOR_SENSITIVE_ACTION: % needs % authentication, '
            'the approving session holds %',
            p_action_code, v_action.minimum_strength, v_approver_session.established_with
            USING ERRCODE = 'HS403';
    END IF;

    -- An unconsumed step-up on the APPROVER'S OWN session, for THIS action.
    SELECT * INTO v_grant FROM identity.step_up_grant
     WHERE tenant_id = p_tenant_id
       AND session_id = p_approver_session_id
       AND action_code = p_action_code
       AND consumed_at IS NULL
     ORDER BY granted_at DESC
     LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'OVERRIDE_WITHOUT_STEP_UP: % was approved with no unconsumed step-up on the '
            'approving session', p_action_code
            USING ERRCODE = 'HS403';
    END IF;

    -- M1-B's recency window, evaluated at the moment of use. A stale grant approving a
    -- void is the same defect one step removed, so the same error names it.
    IF now() - v_grant.granted_at > v_action.step_up_max_age THEN
        RAISE EXCEPTION
            'STEP_UP_EXPIRED: the step-up for % is older than the % recency window',
            p_action_code, v_action.step_up_max_age
            USING ERRCODE = 'HS403';
    END IF;

    PERFORM 1 FROM config.reason_code
     WHERE tenant_id = p_tenant_id AND id = p_reason_code_id
       AND category = 'manager_override' AND status = 'active';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'DESTRUCTIVE_ACTION_WITHOUT_REASON: an override states an active '
            'manager_override reason code; % is not one', p_reason_code_id
            USING ERRCODE = 'HS422';
    END IF;

    INSERT INTO pos.override_approval
        (tenant_id, outlet_id, action_code,
         actor_user_id, actor_session_id,
         approver_user_id, approver_session_id, step_up_grant_id,
         reason_code_id, reason_text, subject_kind, subject_id)
    VALUES (p_tenant_id, p_outlet_id, p_action_code,
            v_actor_session.user_account_id, v_actor_session.id,
            v_approver_session.user_account_id, v_approver_session.id, v_grant.id,
            p_reason_code_id, p_reason_text, p_subject_kind, p_subject_id)
    RETURNING id INTO v_id;

    -- Consumed, so this authentication authorizes this override and no other.
    UPDATE identity.step_up_grant SET consumed_at = now() WHERE id = v_grant.id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION pos.approve_override(uuid, uuid, text, uuid, uuid, text, uuid, text) IS
    'FR-POS-006. Records a supervisor approval. The approver is derived from the '
    'approving session and is never an argument; the grant is consumed so one '
    'authentication authorizes one override.';


-- An override record is evidence. Evidence that can be edited afterwards is not
-- evidence, so this is append-only, and the refusal is a TRIGGER rather than only an
-- absent grant — two independent locks, because a grant restored by a later migration
-- would otherwise silently open the table.

CREATE FUNCTION pos.refuse_override_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'OVERRIDE_RECORD_ALTERED: % on pos.override_approval is refused; an approval '
        'is evidence of what somebody authorized and is append-only', TG_OP
        USING ERRCODE = 'HS403';
END;
$$;

CREATE TRIGGER override_approval_append_only
    BEFORE UPDATE OR DELETE ON pos.override_approval
    FOR EACH ROW EXECUTE FUNCTION pos.refuse_override_mutation();


-- And it lands in M1-C's audit storage, which is append-only in its own right. Both
-- identities and the grant travel with it: an audit row naming only the approver would
-- lose who acted, and one naming only the actor would lose that anybody approved.

CREATE FUNCTION pos.record_override_in_audit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pos, audit, public
AS $$
BEGIN
    INSERT INTO audit.security_event
        (tenant_id, outlet_id, event_code, subject_id, actor_id, detail)
    VALUES (NEW.tenant_id, NEW.outlet_id, 'override.approved',
            NEW.approver_user_id, NEW.actor_user_id,
            jsonb_build_object(
                'action_code',      NEW.action_code,
                'override_id',      NEW.id,
                'step_up_grant_id', NEW.step_up_grant_id,
                'subject_kind',     NEW.subject_kind,
                'subject_id',       NEW.subject_id,
                'reason_code_id',   NEW.reason_code_id));
    RETURN NULL;
END;
$$;

CREATE TRIGGER override_approval_audited
    AFTER INSERT ON pos.override_approval
    FOR EACH ROW EXECUTE FUNCTION pos.record_override_in_audit();


-- ===========================================================================
-- Confirmation friction, graded by consequence (FR-UX-015, FR-POS-009)
-- ===========================================================================
-- FR-UX-015 asks for low friction on ordinary service and deliberate friction on
-- allergy, cancellation, override and payment. That grading is a property of the ACTION,
-- not of whichever screen happens to offer it — otherwise two screens offering the same
-- action can disagree, and the one that disagrees is the one nobody tested.
--
-- So the grade lives beside the action, is installed for every tenant by trigger the way
-- M1-B installs governed actions, and the surface READS it rather than deciding it.

CREATE TYPE pos.consequence AS ENUM ('routine', 'elevated', 'deliberate');

COMMENT ON TYPE pos.consequence IS
    'FR-UX-015. routine: a tap. elevated: a confirmation. deliberate: a confirmation '
    'that states a reason. The grade belongs to the action so two screens cannot '
    'disagree about how serious the same thing is.';

CREATE TABLE pos.confirmation_requirement (
    tenant_id       uuid NOT NULL,
    action_code     text NOT NULL,
    consequence     pos.consequence NOT NULL,
    requires_reason boolean NOT NULL,
    graded_from_gate text NOT NULL,

    PRIMARY KEY (tenant_id, action_code),
    CONSTRAINT confirmation_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE CASCADE,
    CONSTRAINT confirmation_action_not_blank CHECK (btrim(action_code) <> ''),

    -- A deliberate action that records no reason is not deliberate, it is an ordinary
    -- action with an extra tap. This is the constraint behind
    -- DESTRUCTIVE_ACTION_WITHOUT_REASON, and it is a property of the model rather than
    -- a rule the surface is trusted to follow.
    CONSTRAINT confirmation_deliberate_states_a_reason CHECK (
        consequence <> 'deliberate' OR requires_reason = true),
    -- And the converse: a routine action that demanded a reason would be friction with
    -- no consequence behind it, which trains people to type anything.
    CONSTRAINT confirmation_routine_asks_for_nothing CHECK (
        consequence <> 'routine' OR requires_reason = false)
);

COMMENT ON TABLE pos.confirmation_requirement IS
    'FR-UX-015, FR-POS-009. How much friction an action carries, graded by its '
    'consequence. Read by the staff surface; never decided by it.';

CREATE FUNCTION pos.install_confirmation_requirements() RETURNS trigger
-- SECURITY DEFINER so the application role can hold SELECT and nothing more on the
-- grades. A confirmation grade is configuration: the surface reads it, and nothing
-- the surface can do should be able to lower the friction on declaring an allergy.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pos, public
AS $$
BEGIN
    INSERT INTO pos.confirmation_requirement
        (tenant_id, action_code, consequence, requires_reason, graded_from_gate)
    VALUES
        -- Ordinary service. A waiter acknowledging a request or adding a line to an
        -- order does it dozens of times an hour; friction here is friction everywhere.
        (NEW.id, 'order.view',                   'routine',    false, 'M3-D'),
        (NEW.id, 'order.line.add',               'routine',    false, 'M3-D'),
        (NEW.id, 'service_request.acknowledge',  'routine',    false, 'M3-D'),
        (NEW.id, 'service_request.complete',     'routine',    false, 'M3-D'),
        (NEW.id, 'session.resume',               'routine',    false, 'M3-D'),
        -- Consequential but recoverable.
        (NEW.id, 'order.submit',                 'elevated',   false, 'M3-D'),
        (NEW.id, 'handover.propose',             'elevated',   false, 'M3-D'),
        (NEW.id, 'session.move',                 'elevated',   false, 'M3-D'),
        -- Deliberate: safety, destruction, and somebody else's authority. Each states a
        -- reason, enforced by the CHECK above rather than by the screen.
        (NEW.id, 'allergy.declare',              'deliberate', true,  'M3-D'),
        (NEW.id, 'order.amend',                  'deliberate', true,  'M3-D'),
        (NEW.id, 'order.cancel',                 'deliberate', true,  'M3-D'),
        (NEW.id, 'order.void',                   'deliberate', true,  'M3-D'),
        (NEW.id, 'terminal.revoke',              'deliberate', true,  'M3-D'),
        (NEW.id, 'session.close_with_exception', 'deliberate', true,  'M3-D'),
        -- Graded now, offered from M4. FR-UX-015 names payment explicitly and the grade
        -- is the same whichever gate builds the screen.
        (NEW.id, 'payment.refund',               'deliberate', true,  'M4'),
        (NEW.id, 'check.void',                   'deliberate', true,  'M4'),
        (NEW.id, 'discount.high',                'deliberate', true,  'M4');
    RETURN NULL;
END;
$$;

CREATE TRIGGER tenant_install_confirmation_requirements
    AFTER INSERT ON org.tenant
    FOR EACH ROW EXECUTE FUNCTION pos.install_confirmation_requirements();

-- ---------------------------------------------------------------------------
-- Installing both registries for a tenant that already exists
-- ---------------------------------------------------------------------------
-- M3-A wrote, correctly, that adding a governed action to the installer alone is how a
-- check comes to pass on a fresh database and fail on a real one, and added a second
-- statement for "the tenants that already exist":
--
--     INSERT INTO identity.governed_action (...)
--     SELECT t.id, ... FROM org.tenant t WHERE NOT EXISTS (...)
--
-- That statement reaches NO TENANT AT ALL, on any database. Migrations run as
-- hospitality_migrator; org.tenant has row level security ENABLED and FORCED and its
-- policy is `id = app.current_tenant_id()`; the migrator is not BYPASSRLS and holds no
-- tenant context. So the SELECT returns zero rows and the backfill is a safety net with
-- nothing behind it — the same defect it was written to prevent, wearing the shape of
-- the fix. It is invisible in the suites because every fixture tenant is created AFTER
-- the migrations, so the trigger has always covered them and the backfill has never been
-- the thing that made a check pass.
--
-- A migration cannot fix this by trying harder: enumerating tenants requires either a
-- context it cannot have for all of them at once, or BYPASSRLS, and that role stays in
-- the test driver and must never enter a deployment path. So the backfill is not
-- repeated here as a statement that quietly matches nothing. It is a FUNCTION an
-- operator calls once per tenant, with that tenant's context, which is the only shape
-- that can work — and it installs what M3-A's dead statement was meant to install as
-- well as this slice's, so calling it repairs the earlier gap too.

CREATE FUNCTION pos.install_registries_for(p_tenant_id uuid) RETURNS integer
-- SECURITY DEFINER for the same reason as the trigger above. Row level security is
-- FORCED on both registries and their policies read the session context, so the caller
-- still has to be in the tenant they are naming: definer rights widen what may be
-- written, never whose rows are visible.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pos, identity, public
AS $$
DECLARE
    v_installed integer := 0;
    v_added     integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM org.tenant WHERE id = p_tenant_id) THEN
        RAISE EXCEPTION
            'TENANT_NOT_IN_SCOPE: tenant % is not visible in this context, so nothing '
            'can be installed for it. Set app.tenant_id first — this is the check the '
            'silent backfill in 0010 never made', p_tenant_id
            USING ERRCODE = 'HS404';
    END IF;

    INSERT INTO identity.governed_action
        (tenant_id, action_code, minimum_strength, step_up_required, step_up_max_age,
         governed_from_gate)
    SELECT p_tenant_id, a.code, 'strong', true, interval '5 minutes', a.gate
    FROM (VALUES
        ('order.void', 'M3'), ('session.close_with_exception', 'M3'),
        ('order.amend', 'M3'), ('terminal.revoke', 'M3')
    ) AS a(code, gate)
    WHERE NOT EXISTS (
        SELECT 1 FROM identity.governed_action g
        WHERE g.tenant_id = p_tenant_id AND g.action_code = a.code);
    GET DIAGNOSTICS v_added = ROW_COUNT;
    v_installed := v_installed + v_added;

    INSERT INTO pos.confirmation_requirement
        (tenant_id, action_code, consequence, requires_reason, graded_from_gate)
    SELECT p_tenant_id, g.action_code, g.consequence, g.requires_reason, g.gate
    FROM (VALUES
        ('order.view',                   'routine'::pos.consequence,    false, 'M3-D'),
        ('order.line.add',               'routine',                     false, 'M3-D'),
        ('service_request.acknowledge',  'routine',                     false, 'M3-D'),
        ('service_request.complete',     'routine',                     false, 'M3-D'),
        ('session.resume',               'routine',                     false, 'M3-D'),
        ('order.submit',                 'elevated',                    false, 'M3-D'),
        ('handover.propose',             'elevated',                    false, 'M3-D'),
        ('session.move',                 'elevated',                    false, 'M3-D'),
        ('allergy.declare',              'deliberate',                  true,  'M3-D'),
        ('order.amend',                  'deliberate',                  true,  'M3-D'),
        ('order.cancel',                 'deliberate',                  true,  'M3-D'),
        ('order.void',                   'deliberate',                  true,  'M3-D'),
        ('terminal.revoke',              'deliberate',                  true,  'M3-D'),
        ('session.close_with_exception', 'deliberate',                  true,  'M3-D'),
        ('payment.refund',               'deliberate',                  true,  'M4'),
        ('check.void',                   'deliberate',                  true,  'M4'),
        ('discount.high',                'deliberate',                  true,  'M4')
    ) AS g(action_code, consequence, requires_reason, gate)
    WHERE NOT EXISTS (
        SELECT 1 FROM pos.confirmation_requirement c
        WHERE c.tenant_id = p_tenant_id AND c.action_code = g.action_code);
    GET DIAGNOSTICS v_added = ROW_COUNT;
    v_installed := v_installed + v_added;

    RETURN v_installed;
END;
$$;

COMMENT ON FUNCTION pos.install_registries_for(uuid) IS
    'Installs the governed actions and confirmation grades a tenant needs. Idempotent, '
    'and required only for tenants that predate the migration that added them — the '
    'tenant triggers cover everything created since. Exists as a function rather than '
    'as a backfill statement because a migration runs with no tenant context and '
    'org.tenant is scoped by row level security, so a backfill SELECT over it matches '
    'nothing.';


-- ===========================================================================
-- Governed actions this gate exercises (FR-AUTH-006, FR-POS-006)
-- ===========================================================================
-- M1-B built identity.assert_can_perform() and registered the action list; M3-A added
-- two more. M3-D is the first slice with a staff surface that actually PERFORMS a
-- governed action, so it is the first to call the enforcement point M1-B built.
--
-- Two actions are added. Both are somebody overriding what the system would otherwise
-- refuse, which is what a governed action is for: amending an order after the kitchen
-- has accepted it, and taking a terminal out of service.
--
-- Registered in BOTH places, as at M3-A: the installer, and the tenants that already
-- exist. The whole list is restated because CREATE OR REPLACE takes the body entire —
-- dropping an earlier gate's rows here would un-govern them silently.

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
        -- Governed from M3-A: an operational void, and closing a session over an
        -- outstanding obligation.
        (NEW.id, 'order.void',             'strong', true,  interval '5 minutes',  'M3'),
        (NEW.id, 'session.close_with_exception',
                                           'strong', true,  interval '5 minutes',  'M3'),
        -- Governed from M3-D: amending an accepted order, and revoking a terminal.
        (NEW.id, 'order.amend',            'strong', true,  interval '5 minutes',  'M3'),
        (NEW.id, 'terminal.revoke',        'strong', true,  interval '5 minutes',  'M3'),
        -- Registered now, exercised from M4. No caller exists yet.
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

-- The tenants that already exist are covered by pos.install_registries_for(), above,
-- for the reason recorded there. A backfill statement here would match no tenant.


-- ===========================================================================
-- Handover (FR-POS-007)
-- ===========================================================================
-- Responsibility for open tables and open tasks moving from one named person to another
-- named person, acknowledged by the person taking it on.
--
-- This is NOT a shift model and adds no schedule. It says nothing about when anybody
-- works, only that these tables and these requests are now that person's. M2-B already
-- built the table half — service.transfer_ownership() moves one table and requires an
-- acknowledgement from the waiter taking it on or a named supervisor — so a handover
-- gathers what is open and drives M2-B's function for each table rather than writing a
-- second way to move one.

CREATE TYPE pos.handover_state AS ENUM ('proposed', 'acknowledged', 'cancelled');

CREATE TYPE pos.handover_item_kind AS ENUM ('table_session', 'service_request');

CREATE TABLE pos.handover (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL,
    outlet_id        uuid NOT NULL,
    from_user_id     uuid NOT NULL,
    to_user_id       uuid NOT NULL,
    state            pos.handover_state NOT NULL DEFAULT 'proposed',
    proposed_at      timestamptz NOT NULL DEFAULT now(),
    proposed_by_user_id uuid NOT NULL,
    acknowledged_at  timestamptz,
    acknowledged_by_user_id uuid,
    cancelled_at     timestamptz,
    note             text,

    CONSTRAINT handover_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT handover_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT handover_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT handover_from_fk FOREIGN KEY (tenant_id, from_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT handover_to_fk FOREIGN KEY (tenant_id, to_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT handover_proposer_fk FOREIGN KEY (tenant_id, proposed_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT handover_acknowledger_fk FOREIGN KEY (tenant_id, acknowledged_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,

    -- Handing over to yourself is not a handover.
    CONSTRAINT handover_moves_between_people CHECK (from_user_id <> to_user_id),
    -- Acknowledgement is by the person TAKING IT ON. M2-B refused this on the single
    -- table transfer for the same reason: somebody else accepting on their behalf is
    -- the silent reassignment the requirement exists to prevent.
    CONSTRAINT handover_acknowledger_is_recipient CHECK (
        acknowledged_by_user_id IS NULL OR acknowledged_by_user_id = to_user_id),
    CONSTRAINT handover_acknowledged_is_stated CHECK (
        (state = 'acknowledged')
            = (acknowledged_at IS NOT NULL AND acknowledged_by_user_id IS NOT NULL)),
    CONSTRAINT handover_cancelled_is_stated CHECK (
        (state = 'cancelled') = (cancelled_at IS NOT NULL))
);

COMMENT ON TABLE pos.handover IS
    'FR-POS-007. Responsibility for open tables and tasks moving between two named '
    'people, acknowledged by the recipient. Not a shift and not a schedule: it records '
    'a transfer that happened, never when anybody is due to work.';

CREATE TABLE pos.handover_item (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          uuid NOT NULL,
    outlet_id          uuid NOT NULL,
    handover_id        uuid NOT NULL,
    item_kind          pos.handover_item_kind NOT NULL,
    table_session_id   uuid,
    service_request_id uuid,

    CONSTRAINT handover_item_handover_fk FOREIGN KEY (tenant_id, handover_id)
        REFERENCES pos.handover (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT handover_item_session_fk FOREIGN KEY (tenant_id, table_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT handover_item_request_fk FOREIGN KEY (tenant_id, service_request_id)
        REFERENCES service.service_request (tenant_id, id) ON DELETE RESTRICT,
    -- Exactly one subject, matching the kind. A row that named both would be two items.
    CONSTRAINT handover_item_names_its_subject CHECK (
        (item_kind = 'table_session'
            AND table_session_id IS NOT NULL AND service_request_id IS NULL)
     OR (item_kind = 'service_request'
            AND service_request_id IS NOT NULL AND table_session_id IS NULL)),
    CONSTRAINT handover_item_once UNIQUE (handover_id, item_kind, table_session_id, service_request_id)
);

COMMENT ON TABLE pos.handover_item IS
    'What a handover carries: the open tables and the open service requests. Captured '
    'when the handover is proposed, so what was accepted is what was offered.';


-- The emitter M3-C left a fold branch for. service.apply_request_event() has handled
-- 'reassigned' since 0014 and nothing produced one, because M3-C had no surface on which
-- a request changed hands. A handover is that surface. Written as an EVENT rather than
-- an UPDATE for the reason 0014 gives: a projection changed behind the ledger's back is
-- a projection a rebuild puts back the way it was.

CREATE FUNCTION service.reassign_request(
    p_tenant_id uuid,
    p_request_id uuid,
    p_to_user_id uuid,
    p_actor_user_id uuid
) RETURNS void
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

    -- A finished request has nobody to reassign it to. SM-SERVICE-REQUEST's first
    -- invariant is about ACTIVE requests having an accountable assignee; moving a
    -- completed one would be rewriting who did work that is already done.
    IF r.state IN ('completed', 'cancelled', 'expired') THEN
        RAISE EXCEPTION
            'REQUEST_NOT_OPEN: request % is % and reassigning it would change who is '
            'recorded as having handled it', p_request_id, r.state
            USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO service.service_request_event
        (tenant_id, outlet_id, service_request_id, sequence_number, kind, actor_kind,
         actor_user_id, correlation_id, before, after)
    VALUES (p_tenant_id, r.outlet_id, p_request_id,
            service.next_sequence(p_tenant_id, p_request_id), 'reassigned', 'staff',
            p_actor_user_id, r.correlation_id,
            jsonb_build_object('assigned_user_id', r.assigned_user_id),
            jsonb_build_object('assigned_user_id', p_to_user_id))
    RETURNING id INTO v_event;

    PERFORM service.apply_request_event(v_event);
END;
$$;

COMMENT ON FUNCTION service.reassign_request(uuid, uuid, uuid, uuid) IS
    'FR-POS-007. Moves an open request to another member of staff through the ledger, '
    'so a rebuild reproduces the reassignment rather than undoing it.';


CREATE FUNCTION pos.propose_handover(
    p_tenant_id     uuid,
    p_outlet_id     uuid,
    p_from_user_id  uuid,
    p_to_user_id    uuid,
    p_actor_user_id uuid,
    p_note          text DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_handover uuid;
    v_items    integer;
BEGIN
    INSERT INTO pos.handover
        (tenant_id, outlet_id, from_user_id, to_user_id, proposed_by_user_id, note)
    VALUES (p_tenant_id, p_outlet_id, p_from_user_id, p_to_user_id, p_actor_user_id, p_note)
    RETURNING id INTO v_handover;

    -- What is open, captured NOW. A handover that recomputed its contents at
    -- acknowledgement would hand over tables the recipient never saw offered.
    INSERT INTO pos.handover_item
        (tenant_id, outlet_id, handover_id, item_kind, table_session_id)
    SELECT p_tenant_id, p_outlet_id, v_handover, 'table_session', o.table_session_id
    FROM service.table_ownership o
    JOIN service.table_session ts
      ON ts.tenant_id = o.tenant_id AND ts.id = o.table_session_id
    WHERE o.tenant_id = p_tenant_id
      AND o.outlet_id = p_outlet_id
      AND o.primary_waiter_user_id = p_from_user_id
      AND o.effective_to IS NULL
      AND ts.closed_at IS NULL;

    INSERT INTO pos.handover_item
        (tenant_id, outlet_id, handover_id, item_kind, service_request_id)
    SELECT p_tenant_id, p_outlet_id, v_handover, 'service_request', sr.id
    FROM service.service_request sr
    WHERE sr.tenant_id = p_tenant_id
      AND sr.outlet_id = p_outlet_id
      AND sr.assigned_user_id = p_from_user_id
      AND sr.state NOT IN ('completed', 'cancelled', 'expired');

    SELECT count(*) INTO v_items FROM pos.handover_item WHERE handover_id = v_handover;

    -- A handover carrying nothing is somebody pressing a button. Refusing it here means
    -- an empty acknowledgement can never be mistaken for responsibility moving.
    IF v_items = 0 THEN
        RAISE EXCEPTION
            'HANDOVER_CARRIES_NOTHING: % holds no open table and no open request, so '
            'there is no responsibility to transfer', p_from_user_id
            USING ERRCODE = 'HS409';
    END IF;

    RETURN v_handover;
END;
$$;

COMMENT ON FUNCTION pos.propose_handover(uuid, uuid, uuid, uuid, uuid, text) IS
    'FR-POS-007. Captures what one person currently holds — open tables and open '
    'requests — and offers it to another. Contents are fixed at proposal, so what is '
    'accepted is what was offered.';


CREATE FUNCTION pos.acknowledge_handover(
    p_tenant_id  uuid,
    p_handover_id uuid,
    p_user_id    uuid
) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    h        pos.handover%ROWTYPE;
    v_item   record;
    v_transfer uuid;
    v_moved  integer := 0;
BEGIN
    SELECT * INTO h FROM pos.handover
     WHERE tenant_id = p_tenant_id AND id = p_handover_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'HANDOVER_UNKNOWN: no handover % in scope', p_handover_id
            USING ERRCODE = 'HS404';
    END IF;

    IF h.state <> 'proposed' THEN
        RAISE EXCEPTION
            'HANDOVER_NOT_OPEN: handover % is %; only a proposed handover can be '
            'acknowledged', p_handover_id, h.state
            USING ERRCODE = 'HS409';
    END IF;

    -- The recipient acknowledges, nobody else. Named here as well as constrained,
    -- because a constraint violation would say which column disagreed and not why.
    IF p_user_id <> h.to_user_id THEN
        RAISE EXCEPTION
            'HANDOVER_NOT_YOURS: handover % was offered to somebody else, and a third '
            'party accepting on their behalf is the silent reassignment FR-POS-007 '
            'exists to prevent', p_handover_id
            USING ERRCODE = 'HS403';
    END IF;

    FOR v_item IN
        SELECT * FROM pos.handover_item
         WHERE tenant_id = p_tenant_id AND handover_id = p_handover_id
         ORDER BY item_kind, id
    LOOP
        IF v_item.item_kind = 'table_session' THEN
            -- Through M2-B's function, not around it. A second way to move a table is a
            -- second place for the acknowledgement rule to be got wrong.
            INSERT INTO service.ownership_transfer
                (tenant_id, outlet_id, table_session_id, from_user_id, to_user_id,
                 proposed_by_user_id)
            VALUES (p_tenant_id, h.outlet_id, v_item.table_session_id,
                    h.from_user_id, h.to_user_id, h.proposed_by_user_id)
            RETURNING id INTO v_transfer;

            UPDATE service.ownership_transfer
               SET state = 'acknowledged',
                   acknowledged_at = now(),
                   acknowledged_by_user_id = h.to_user_id
             WHERE id = v_transfer;

            PERFORM service.transfer_ownership(p_tenant_id, v_transfer);
        ELSE
            PERFORM service.reassign_request(
                p_tenant_id, v_item.service_request_id, h.to_user_id, p_user_id);
        END IF;
        v_moved := v_moved + 1;
    END LOOP;

    UPDATE pos.handover
       SET state = 'acknowledged',
           acknowledged_at = now(),
           acknowledged_by_user_id = p_user_id
     WHERE tenant_id = p_tenant_id AND id = p_handover_id;

    RETURN v_moved;
END;
$$;

COMMENT ON FUNCTION pos.acknowledge_handover(uuid, uuid, uuid) IS
    'FR-POS-007. The recipient takes responsibility. Each table moves through M2-B''s '
    'service.transfer_ownership() and each request through the service ledger, so there '
    'is one implementation of "a table changes hands" and one of "a request does".';


-- The property, checked at COMMIT rather than per statement. A handover moves several
-- tables and several requests, and between the first and the last there are moments when
-- some have moved and some have not — a per-row trigger would refuse a correct handover
-- halfway through. Deferred, it asks the only question worth asking: when this
-- transaction ends, is everything that was handed over somebody's responsibility?
--
-- Same shape as M3-C's reparent_requests_on_merge, and for the same reason.

CREATE FUNCTION pos.assert_responsibility_survived() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_orphan_tables   integer;
    v_orphan_requests integer;
BEGIN
    IF NEW.state <> 'acknowledged' THEN
        RETURN NULL;
    END IF;

    SELECT count(*) INTO v_orphan_tables
    FROM pos.handover_item i
    WHERE i.handover_id = NEW.id AND i.item_kind = 'table_session'
      AND NOT EXISTS (
        SELECT 1 FROM service.table_ownership o
         WHERE o.tenant_id = NEW.tenant_id
           AND o.table_session_id = i.table_session_id
           AND o.effective_to IS NULL
           AND o.primary_waiter_user_id = NEW.to_user_id);

    SELECT count(*) INTO v_orphan_requests
    FROM pos.handover_item i
    JOIN service.service_request sr
      ON sr.tenant_id = i.tenant_id AND sr.id = i.service_request_id
    WHERE i.handover_id = NEW.id AND i.item_kind = 'service_request'
      AND sr.assigned_user_id IS DISTINCT FROM NEW.to_user_id;

    IF v_orphan_tables > 0 OR v_orphan_requests > 0 THEN
        RAISE EXCEPTION
            'RESPONSIBILITY_LOST_ON_HANDOVER: handover % completed with % table(s) and '
            '% request(s) that are not the recipient''s. A handover that leaves a table '
            'with nobody accountable is worse than no handover, because the floor '
            'believes it happened',
            NEW.id, v_orphan_tables, v_orphan_requests
            USING ERRCODE = 'HS409';
    END IF;

    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER handover_responsibility_survives
    AFTER UPDATE ON pos.handover
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION pos.assert_responsibility_survived();


-- ===========================================================================
-- The table view (FR-POS-004)
-- ===========================================================================
-- Occupancy with the assigned waiter, open requests, order progress, unpaid balance and
-- attention flags. Every column is DERIVED from what an earlier gate already owns:
-- ownership from M2-B, requests from M3-C, order progress from M3-B's
-- fulfillment.order_fulfillment_state(). Nothing here is stored, so nothing here can
-- disagree with the thing it describes.
--
-- unpaid_balance_minor is the exception, and it is deliberately NULL. FR-POS-004 names
-- it and M4 owns the figure; a zero would be a number a waiter could act on, and "no
-- outstanding balance" and "we have not built billing" are not the same statement. The
-- slot exists so M4 fills a column rather than changing a shape, and the partial-closure
-- register carries the entry with M4 named.

CREATE FUNCTION pos.table_view(p_tenant_id uuid, p_outlet_id uuid)
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
        -- FR-POS-004's unpaid balance. M4's figure; the slot, not a number.
        NULL::bigint,
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
    'progress derived from the tickets, attention flags, and the unpaid balance SLOT '
    'that M4 fills. Every figure is derived, so none can drift from its source.';


-- ===========================================================================
-- Role home (FR-POS-002)
-- ===========================================================================
-- "Role-specific queues and next actions, not generic CRUD menus." So this returns what
-- the person in front of the terminal should do next, ordered by how long it has been
-- waiting — never a list of tables to browse.
--
-- What a role sees is derived from what its role GRANTS, through identity.role_action,
-- which is the same registry authorization reads. A home screen assembled from a
-- different list than the one that decides permission is a home screen that offers
-- actions the system will refuse.

CREATE FUNCTION pos.role_home(p_tenant_id uuid, p_outlet_id uuid, p_user_id uuid)
RETURNS TABLE (
    queue         text,
    subject_kind  text,
    subject_id    uuid,
    headline      text,
    next_action   text,
    waiting_since timestamptz,
    elapsed_seconds integer,
    overdue       boolean
)
LANGUAGE sql STABLE
AS $$
    -- Requests assigned to this person, oldest first: the queue FR-POS-002 means.
    SELECT 'service_requests'::text,
           'service_request'::text,
           sr.id,
           rt.code || ' at ' || n.reference_code,
           CASE sr.state
               WHEN 'routed'        THEN 'acknowledge'
               WHEN 'acknowledged'  THEN 'start'
               WHEN 'in_progress'   THEN 'complete'
               WHEN 'escalated'     THEN 'acknowledge'
               ELSE 'review'
           END,
           sr.raised_at,
           floor(extract(epoch FROM now() - sr.raised_at))::integer,
           sr.sla_due_at < now()
    FROM service.service_request sr
    JOIN service.request_type rt ON rt.id = sr.request_type_id
    JOIN service.table_session ts ON ts.tenant_id = sr.tenant_id AND ts.id = sr.table_session_id
    JOIN org.org_node n ON n.tenant_id = ts.tenant_id AND n.id = ts.table_node_id
    WHERE sr.tenant_id = p_tenant_id
      AND sr.outlet_id = p_outlet_id
      AND sr.assigned_user_id = p_user_id
      AND sr.state NOT IN ('completed', 'cancelled', 'expired')

    UNION ALL

    -- Tables this person is accountable for that are asking for attention.
    SELECT 'tables'::text,
           'table_session'::text,
           v.table_session_id,
           'table ' || v.table_reference,
           coalesce(v.attention_reason, 'check on the table'),
           v.opened_at,
           floor(extract(epoch FROM now() - v.opened_at))::integer,
           v.needs_attention
    FROM pos.table_view(p_tenant_id, p_outlet_id) v
    WHERE v.assigned_waiter_id = p_user_id
      AND v.needs_attention

    UNION ALL

    -- Handovers waiting on this person to accept.
    SELECT 'handovers'::text,
           'handover'::text,
           h.id,
           'handover offered by a colleague',
           'acknowledge',
           h.proposed_at,
           floor(extract(epoch FROM now() - h.proposed_at))::integer,
           false
    FROM pos.handover h
    WHERE h.tenant_id = p_tenant_id
      AND h.outlet_id = p_outlet_id
      AND h.to_user_id = p_user_id
      AND h.state = 'proposed'

    -- Overdue first, then oldest first within that: column 8 is `overdue` and
    -- column 6 is `waiting_since`. FR-UX-004 asks the screen to prioritise the next
    -- required action and the active exception, and this ordering IS that priority.
    ORDER BY 8 DESC, 6 ASC;
$$;

COMMENT ON FUNCTION pos.role_home(uuid, uuid, uuid) IS
    'FR-POS-002. What this person should do next, overdue first and oldest first within '
    'that. Queues and next actions, never a browsable list of everything.';


-- ===========================================================================
-- One writer for a priced cart line (FR-POS-003A)
-- ===========================================================================
-- FR-POS-003A says a waiter-entered order obeys the IDENTICAL price, menu, modifier,
-- safety and authorization rules as a QR order, and rejects two implementations that
-- agree today. Almost all of that was already true: ordering.submit_order() re-validates
-- and re-prices at submission, so the commercial truth of an order comes from one
-- function whichever channel asked for it.
--
-- One thing was not. The customer route built its cart line with an INSERT that called
-- menu.effective_price() inline. A staff route written the same way would be a second
-- copy of that expression — two call sites that agree until one is edited, which is the
-- shape the requirement names. So the priced line gets one writer, here, and both
-- surfaces call it. Neither route names a pricing function any more, and tests/m3d
-- asserts that from the catalog and from the route sources rather than from a list.
--
-- Attribution is the only thing that differs between the two channels, and it differs
-- the way ordering.customer_order already models it: a guest line names the guest
-- session, a waiter line names neither and is attributed by the ORDER's origin when it
-- is submitted. A cart line has no staff column and does not gain one here — inventing
-- one would be a second place to record who ordered, disagreeing with the first.

CREATE FUNCTION service.add_cart_line(
    p_tenant_id  uuid,
    p_outlet_id  uuid,
    p_cart_id    uuid,
    p_item_id    uuid,
    p_variant_id uuid,
    p_quantity   integer DEFAULT 1,
    p_guest_session_id uuid DEFAULT NULL,
    p_at         timestamptz DEFAULT now()
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_price money.amount_minor;
    v_id    uuid;
BEGIN
    -- The one call to the pricing rule in the cart path. A NULL here would mean the
    -- variant has no price this outlet can charge, and a line priced at nothing is a
    -- line somebody will be billed nothing for.
    v_price := menu.effective_price(p_tenant_id, p_outlet_id, p_variant_id,
                                    NULL::menu.sales_channel, 'ETB'::char(3), p_at);

    IF v_price IS NULL THEN
        RAISE EXCEPTION
            'VARIANT_HAS_NO_PRICE: variant % has no effective price at outlet %',
            p_variant_id, p_outlet_id
            USING ERRCODE = 'HS422';
    END IF;

    INSERT INTO service.cart_line
        (tenant_id, outlet_id, cart_id, item_id, variant_id, quantity,
         currency_code, unit_amount_minor, added_by_guest_session_id)
    VALUES (p_tenant_id, p_outlet_id, p_cart_id, p_item_id, p_variant_id, p_quantity,
            'ETB', v_price, p_guest_session_id)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION service.add_cart_line(uuid, uuid, uuid, uuid, uuid, integer, uuid, timestamptz) IS
    'FR-POS-003A. The only writer of a priced cart line in the delivered code path. '
    'Both the guest surface and the staff surface call it, so the price a waiter sees '
    'and the price a guest sees come from one expression rather than two that agree.';


-- ===========================================================================
-- Fast entry and operational search (FR-POS-005, FR-POS-010A)
-- ===========================================================================
-- The search itself is M2-A's. menu.search_items() already matches the localized name,
-- the description and the Latin item code, and already normalises away the tatweel and
-- bidirectional marks a copy-paste drags in — which is what makes an Arabic session
-- searching a Latin SKU work at all. Re-implementing it here would be a second search
-- that agrees with the first until a menu rule changes.
--
-- So this adds exactly what a STAFF search has that a guest search does not: the
-- requirement that the person searching is a member of staff at this outlet whose role
-- grants them the action. No cross-tenant leakage is not a filter added here — row level
-- security already scopes every table underneath — but the role gate is, and the outlet
-- is passed through rather than trusted from the client.

CREATE FUNCTION pos.staff_search(
    p_tenant_id   uuid,
    p_outlet_id   uuid,
    p_user_id     uuid,
    p_query       text DEFAULT NULL,
    p_category_id uuid DEFAULT NULL,
    p_locale      menu.customer_locale DEFAULT 'en'
) RETURNS TABLE (item_id uuid, item_code text, display_name text, matched_field text,
                 amount_minor money.amount_minor, currency_code char(3),
                 availability menu.availability_state, preparation_minutes integer)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    -- Tenant and outlet: an active membership AT THIS OUTLET, or one that names no
    -- outlet and therefore covers them all. Absence denies.
    IF NOT EXISTS (
        SELECT 1 FROM identity.membership m
         WHERE m.tenant_id = p_tenant_id
           AND m.user_account_id = p_user_id
           AND m.status = 'active'
           AND (m.outlet_id IS NULL OR m.outlet_id = p_outlet_id)
    ) THEN
        RAISE EXCEPTION
            'STAFF_SEARCH_CROSSES_SCOPE: % holds no active membership at outlet %',
            p_user_id, p_outlet_id
            USING ERRCODE = 'HS403';
    END IF;

    -- Role: the same registry authorization reads, so the search cannot offer what the
    -- system would refuse to act on.
    IF NOT EXISTS (
        SELECT 1
        FROM identity.membership m
        JOIN identity.role_action ra ON ra.role_id = m.role_id AND ra.tenant_id = m.tenant_id
        WHERE m.tenant_id = p_tenant_id
          AND m.user_account_id = p_user_id
          AND m.status = 'active'
          AND (m.outlet_id IS NULL OR m.outlet_id = p_outlet_id)
          AND ra.action_code = 'order.view'
    ) THEN
        RAISE EXCEPTION
            'STAFF_SEARCH_CROSSES_SCOPE: no active membership grants order.view to %',
            p_user_id
            USING ERRCODE = 'HS403';
    END IF;

    RETURN QUERY
    SELECT s.item_id, s.item_code, s.display_name, s.matched_field,
           s.amount_minor, s.currency_code, s.availability, s.preparation_minutes
    FROM menu.search_items(p_tenant_id, p_outlet_id, p_locale, p_query, p_category_id) s;
END;
$$;

COMMENT ON FUNCTION pos.staff_search(uuid, uuid, uuid, text, uuid, menu.customer_locale) IS
    'FR-POS-010A. M2-A''s search with the staff gate in front of it: an active '
    'membership at this outlet whose role grants order.view. One search implementation, '
    'so a menu rule cannot mean one thing to a guest and another to a waiter.';


-- Favourites for fast entry (FR-POS-005). A pick with no user is the outlet's, so a
-- waiter on their first shift has the fast picks the floor already uses; a pick with a
-- user is that person's own.

CREATE TABLE pos.fast_pick (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    user_account_id uuid,
    item_id         uuid NOT NULL,
    position        integer NOT NULL,

    CONSTRAINT fast_pick_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT fast_pick_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fast_pick_user_fk FOREIGN KEY (tenant_id, user_account_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE CASCADE,
    -- menu.sellable_item is keyed on id alone, as every reference to it since 0006 has
    -- been. The tenant is carried on this row and scoped by the same policy as the rest
    -- of the schema, so the narrower key costs nothing here.
    CONSTRAINT fast_pick_item_fk FOREIGN KEY (item_id)
        REFERENCES menu.sellable_item (id) ON DELETE CASCADE,
    CONSTRAINT fast_pick_position_positive CHECK (position > 0),
    CONSTRAINT fast_pick_once UNIQUE (tenant_id, outlet_id, user_account_id, item_id)
);

COMMENT ON TABLE pos.fast_pick IS
    'FR-POS-005. Favourites for fast entry. A row with no user is the outlet''s shared '
    'set; a row with one is personal.';

CREATE INDEX fast_pick_lookup_idx ON pos.fast_pick (tenant_id, outlet_id, position);


-- ===========================================================================
-- Row level security
-- ===========================================================================
-- Every tenant table in this schema, ENABLED and FORCED, under the one predicate
-- M1-A built. Enumerated by query rather than listed, so a table added to pos by a
-- later migration is covered the moment it exists.
--
-- pos.confirmation_requirement is the one table with no outlet column: a grade belongs
-- to a tenant's action, not to one of its outlets. It is scoped on tenant alone through
-- the same predicate with a NULL outlet, which app.row_in_scope() already accepts for
-- exactly this case.

DO $$
DECLARE t text;
BEGIN
    FOR t IN
        SELECT format('%I.%I', schemaname, tablename)
        FROM pg_tables WHERE schemaname = 'pos'
        ORDER BY tablename
    LOOP
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', t);
        IF t = 'pos.confirmation_requirement' THEN
            EXECUTE format(
                'CREATE POLICY %I ON %s FOR ALL '
                'USING (app.row_in_scope(tenant_id, NULL::uuid)) '
                'WITH CHECK (app.row_in_scope(tenant_id, NULL::uuid))',
                split_part(t, '.', 2) || '_isolation', t);
        ELSE
            EXECUTE format(
                'CREATE POLICY %I ON %s FOR ALL '
                'USING (app.row_in_scope(tenant_id, outlet_id)) '
                'WITH CHECK (app.row_in_scope(tenant_id, outlet_id))',
                split_part(t, '.', 2) || '_isolation', t);
        END IF;
    END LOOP;
END;
$$;


-- ===========================================================================
-- Grants
-- ===========================================================================

GRANT USAGE ON SCHEMA pos TO hospitality_app;

-- Read models the surface calls.
GRANT SELECT ON pos.terminal                 TO hospitality_app;
GRANT SELECT ON pos.confirmation_requirement TO hospitality_app;
GRANT SELECT ON pos.override_approval        TO hospitality_app;
GRANT SELECT ON pos.handover                 TO hospitality_app;
GRANT SELECT ON pos.handover_item            TO hospitality_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON pos.fast_pick TO hospitality_app;

-- pos.override_approval takes INSERT and nothing else. The append-only trigger refuses
-- UPDATE and DELETE as well, so the grant and the trigger are two independent locks
-- rather than one lock described twice — the same arrangement as every ledger since
-- M3-A. An approval that could be edited afterwards is not evidence of anything.
GRANT INSERT ON pos.override_approval TO hospitality_app;

GRANT SELECT, INSERT, UPDATE ON pos.terminal   TO hospitality_app;
GRANT SELECT, INSERT, UPDATE ON pos.handover   TO hospitality_app;
GRANT SELECT, INSERT          ON pos.handover_item TO hospitality_app;

GRANT EXECUTE ON FUNCTION pos.register_terminal(uuid, uuid, uuid, pos.terminal_profile, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION pos.revoke_terminal(uuid, uuid, uuid, uuid)          TO hospitality_app;
GRANT EXECUTE ON FUNCTION pos.approve_override(uuid, uuid, text, uuid, uuid, text, uuid, text) TO hospitality_app;
GRANT EXECUTE ON FUNCTION pos.propose_handover(uuid, uuid, uuid, uuid, uuid, text) TO hospitality_app;
GRANT EXECUTE ON FUNCTION pos.acknowledge_handover(uuid, uuid, uuid)           TO hospitality_app;
GRANT EXECUTE ON FUNCTION pos.install_registries_for(uuid)                     TO hospitality_migrator;
GRANT EXECUTE ON FUNCTION pos.table_view(uuid, uuid)                           TO hospitality_app;
GRANT EXECUTE ON FUNCTION pos.role_home(uuid, uuid, uuid)                      TO hospitality_app;
GRANT EXECUTE ON FUNCTION pos.staff_search(uuid, uuid, uuid, text, uuid, menu.customer_locale) TO hospitality_app;
GRANT EXECUTE ON FUNCTION service.reassign_request(uuid, uuid, uuid, uuid)     TO hospitality_app;
GRANT EXECUTE ON FUNCTION service.add_cart_line(uuid, uuid, uuid, uuid, uuid, integer, uuid, timestamptz) TO hospitality_app;

-- Configuration this slice adds is written by an administrator, not by the application.
GRANT SELECT, INSERT, UPDATE, DELETE ON pos.confirmation_requirement TO hospitality_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON pos.terminal                 TO hospitality_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON pos.fast_pick                TO hospitality_migrator;
GRANT USAGE ON SCHEMA pos TO hospitality_migrator;
