-- 0050: only one writer, and the old one is fenced before the new one starts
--
-- FR-EDG-024 is the requirement that stops two nodes both believing they are in charge.
-- Everything about it is arranged so that the dangerous thing — a second writer — cannot
-- happen by accident, by timeout, or by somebody being in a hurry at two in the morning.
--
-- THE SEQUENCE IS THE AUTHORITY. Not a flag, not a lease, not a hostname: a number that
-- only ever goes up. Every writer persists the highest it has accepted and refuses
-- anything lower, so a node that was authoritative and then was not cannot come back and
-- be believed by writing an older number. That is what "monotonic" is for, and it is the
-- only part of this that survives a network partition — the two halves cannot both hold
-- the highest number.
--
-- WHY A REPLACEMENT NEEDS FOUR THINGS AND NOT ONE. FR-EDG-024 names them: step-up,
-- independent approval, fence evidence, and an automated LAN-unreachability probe. They
-- are not four ways of saying "be careful". They fail differently:
--
--   step-up               proves the person is who they say, right now
--   independent approval  proves a SECOND person agreed — and it may not be the same
--                         person who stepped up, which is the whole content of the word
--   fence evidence        proves the old node CANNOT write: powered off, or its port or
--                         VLAN isolated. A promise that it is down is not evidence.
--   the probe             proves nobody can reach it on the LAN, which is the thing the
--                         other three are all trying to establish
--
-- An operator who has all four has established that the old node is gone. An operator with
-- three of them has established that they would like it to be.
--
-- WHY STALE EVENTS ARE QUARANTINED RATHER THAN DROPPED. A superseded node may still hold
-- work nobody has seen — orders taken in the minutes before it was fenced. Dropping them
-- loses trade; applying them lets a fenced node write. So they are kept, in a table that
-- is not the outbox, where a person can look at them. That is the only honest third
-- option.

-- ---------------------------------------------------------------------------
-- 1. VOCABULARY
-- ---------------------------------------------------------------------------

-- How the old node was stopped. Every value is something an operator DID and can be asked
-- about afterwards; there is no 'assumed_down'.
CREATE TYPE edge.fence_method AS ENUM (
    'power_off', 'switch_port_disabled', 'vlan_isolated', 'firewall_blocked');

CREATE TYPE edge.authority_state AS ENUM ('held', 'superseded');

-- ---------------------------------------------------------------------------
-- 2. WHO MAY WRITE, AND SINCE WHEN
-- ---------------------------------------------------------------------------

CREATE TABLE edge.authority (
    tenant_id uuid   NOT NULL,
    outlet_id uuid   NOT NULL,
    sequence  bigint NOT NULL,

    holder_node_id uuid NOT NULL,
    state          edge.authority_state NOT NULL DEFAULT 'held',

    -- The keyed digest the holder presents to prove the sequence is the one it was given,
    -- same construction and the same bound as everywhere else in this build.
    attestation_sha256 character(64) NOT NULL,

    granted_at    timestamptz NOT NULL DEFAULT now(),
    superseded_at timestamptz,

    CONSTRAINT authority_pkey PRIMARY KEY (tenant_id, outlet_id, sequence),
    CONSTRAINT authority_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT authority_holder_fk FOREIGN KEY (tenant_id, holder_node_id)
        REFERENCES edge.node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT authority_sequence_positive CHECK (sequence > 0),
    CONSTRAINT authority_supersession_is_timed CHECK (
        (state = 'superseded') = (superseded_at IS NOT NULL))
);

COMMENT ON TABLE edge.authority IS
    'FR-EDG-024. Who may write for this outlet, as a number that only goes up. Not a flag '
    'and not a lease: two halves of a partition cannot both hold the highest number, which '
    'is the only property that survives one.';

-- ONE HOLDER PER OUTLET. The constraint that makes split-brain a database error rather
-- than an operational discovery.
CREATE UNIQUE INDEX authority_one_holder_per_outlet
    ON edge.authority (tenant_id, outlet_id) WHERE state = 'held';

ALTER TABLE edge.authority ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.authority FORCE ROW LEVEL SECURITY;
CREATE POLICY authority_isolation ON edge.authority FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 3. WHAT A REPLACEMENT HAD TO SHOW
-- ---------------------------------------------------------------------------

CREATE TABLE edge.authority_claim (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,

    claimant_node_id uuid   NOT NULL,
    sequence         bigint NOT NULL,
    superseded_node_id uuid,

    -- FR-EDG-024's four, each recorded rather than asserted.
    step_up_grant_id     uuid NOT NULL,
    requested_by_user_id uuid NOT NULL,
    approved_by_user_id  uuid NOT NULL,
    fence_method         edge.fence_method NOT NULL,
    fence_evidence       text NOT NULL,
    lan_probe_at         timestamptz NOT NULL,
    lan_probe_unreachable boolean NOT NULL,

    granted_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT authority_claim_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT authority_claim_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT authority_claim_claimant_fk FOREIGN KEY (tenant_id, claimant_node_id)
        REFERENCES edge.node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT authority_claim_superseded_fk FOREIGN KEY (tenant_id, superseded_node_id)
        REFERENCES edge.node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT authority_claim_requester_fk FOREIGN KEY (tenant_id, requested_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT authority_claim_approver_fk FOREIGN KEY (tenant_id, approved_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    -- Single-column, as pos.override_approval's is: identity.step_up_grant is keyed on
    -- id alone. The tenant is still carried, and the function below checks the grant
    -- belongs to this tenant rather than trusting the key to say so.
    CONSTRAINT authority_claim_grant_fk FOREIGN KEY (step_up_grant_id)
        REFERENCES identity.step_up_grant (id) ON DELETE RESTRICT,

    -- INDEPENDENT MEANS A DIFFERENT PERSON. The word is in the requirement and this is
    -- what it costs: an operator cannot approve their own replacement, however senior.
    -- Without this the four safeguards are three.
    CONSTRAINT authority_claim_approval_is_independent CHECK (
        approved_by_user_id <> requested_by_user_id),

    -- AND THE PROBE HAD TO SAY THE OLD NODE WAS UNREACHABLE. A claim recording a probe
    -- that found the old node alive is a claim recording that the fence did not work.
    CONSTRAINT authority_claim_probe_found_it_gone CHECK (lan_probe_unreachable),

    CONSTRAINT authority_claim_evidence_is_stated CHECK (length(trim(fence_evidence)) > 0),
    CONSTRAINT authority_claim_sequence_positive CHECK (sequence > 0)
);

COMMENT ON TABLE edge.authority_claim IS
    'FR-EDG-024. What a replacement had to show before it could write: a step-up grant, an '
    'INDEPENDENT approver, how the old node was fenced, and a probe that found it '
    'unreachable. An operator with all four has established the old node is gone; an '
    'operator with three has established that they would like it to be.';

CREATE TRIGGER authority_claim_is_append_only
    BEFORE UPDATE OR DELETE ON edge.authority_claim
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

ALTER TABLE edge.authority_claim ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.authority_claim FORCE ROW LEVEL SECURITY;
CREATE POLICY authority_claim_isolation ON edge.authority_claim FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 4. WHAT A SUPERSEDED NODE STILL HOLDS
-- ---------------------------------------------------------------------------

CREATE TABLE edge.quarantined_event (
    id        bigint PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,

    from_node_id uuid   NOT NULL,
    event_id     uuid   NOT NULL,
    at_sequence  bigint NOT NULL,
    current_sequence bigint NOT NULL,

    subject     integration.sync_subject NOT NULL,
    subject_id  uuid NOT NULL,
    event_kind  text NOT NULL,
    payload     jsonb NOT NULL,
    occurred_at timestamptz NOT NULL,

    quarantined_at timestamptz NOT NULL DEFAULT now(),

    released_at    timestamptz,
    released_by_user_id uuid,
    release_reason text,

    CONSTRAINT quarantined_event_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT quarantined_event_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT quarantined_event_node_fk FOREIGN KEY (tenant_id, from_node_id)
        REFERENCES edge.node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT quarantined_event_releaser_fk FOREIGN KEY (tenant_id, released_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT quarantined_event_one_per_event UNIQUE (tenant_id, event_id),
    CONSTRAINT quarantined_event_is_stale CHECK (at_sequence < current_sequence),

    -- RELEASING ONE NEEDS A PERSON AND A SENTENCE, like settling a conflict does. An
    -- event from a fenced node is exactly the thing nobody should be able to wave through.
    CONSTRAINT quarantined_event_release_is_attributed CHECK (
        (released_at IS NULL) = (released_by_user_id IS NULL)
    AND (released_at IS NULL) = (release_reason IS NULL))
);

COMMENT ON TABLE edge.quarantined_event IS
    'FR-EDG-024. Work a superseded node still held — orders taken in the minutes before it '
    'was fenced. Dropping them loses trade and applying them lets a fenced node write, so '
    'they are kept where a person can look at them. That is the only honest third option.';

ALTER TABLE edge.quarantined_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.quarantined_event FORCE ROW LEVEL SECURITY;
CREATE POLICY quarantined_event_isolation ON edge.quarantined_event FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 5. THE FIRST AUTHORITY, AND EVERY ONE AFTER IT
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.grant_first_authority(p_tenant_id uuid, p_node_id uuid)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
DECLARE
    n edge.node%ROWTYPE;
BEGIN
    SELECT * INTO n FROM edge.node
      WHERE tenant_id = p_tenant_id AND id = p_node_id AND status = 'active';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'NODE_UNKNOWN: no active node % for this tenant', p_node_id
            USING ERRCODE = 'HS404';
    END IF;

    -- THE FIRST ONE NEEDS NO FENCE, because there is nothing to fence. Every subsequent
    -- one does, and edge.claim_authority() is the only way to get one.
    PERFORM 1 FROM edge.authority
      WHERE tenant_id = p_tenant_id AND outlet_id = n.outlet_id;
    IF FOUND THEN
        RAISE EXCEPTION
            'AUTHORITY_ALREADY_ESTABLISHED: outlet % has held authority before, so the '
            'next holder is a REPLACEMENT and must be fenced. Use edge.claim_authority()',
            n.outlet_id
            USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO edge.authority (tenant_id, outlet_id, sequence, holder_node_id,
                                attestation_sha256)
    VALUES (p_tenant_id, n.outlet_id, 1, p_node_id,
            edge.update_attestation(lpad('1', 64, '0')::character(64),
                                    n.update_trust_anchor_sha256));
    RETURN 1;
END;
$$;

CREATE FUNCTION edge.claim_authority(
    p_tenant_id uuid,
    p_claimant_node_id uuid,
    p_step_up_grant_id uuid,
    p_requested_by_user_id uuid,
    p_approved_by_user_id  uuid,
    p_fence_method   edge.fence_method,
    p_fence_evidence text,
    p_lan_probe_unreachable boolean)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'integration', 'identity', 'public'
AS $$
DECLARE
    n edge.node%ROWTYPE;
    v_current  edge.authority%ROWTYPE;
    v_next     bigint;
    v_quarantined integer;
BEGIN
    SELECT * INTO n FROM edge.node
      WHERE tenant_id = p_tenant_id AND id = p_claimant_node_id AND status = 'active';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'NODE_UNKNOWN: no active node % for this tenant', p_claimant_node_id
            USING ERRCODE = 'HS404';
    END IF;

    -- THE PROBE IS CHECKED BEFORE ANYTHING ELSE, because it is the one that says whether
    -- the old node is actually gone. Everything else is a record of intent.
    IF NOT p_lan_probe_unreachable THEN
        RAISE EXCEPTION
            'AUTHORITY_FENCE_UNPROVEN: the LAN probe reached the node being replaced. '
            'Whatever else was done, it is still able to write, and two writers is the '
            'one outcome this whole mechanism exists to prevent'
            USING ERRCODE = 'HS409';
    END IF;

    -- THE STEP-UP GRANT MUST BE REAL, FRESH, AND THE REQUESTING OPERATOR'S OWN.
    --
    -- A grant carries a SESSION, not a user, so "belongs to the operator" is a join
    -- through identity.session — and a grant somebody else holds is not this operator
    -- having stepped up. Freshness is judged at the moment of use against the window
    -- identity.governed_action states, which is how M1-B does it: "a grant is never
    -- evergreen".
    PERFORM 1
       FROM identity.step_up_grant g
       JOIN identity.session s ON s.tenant_id = g.tenant_id AND s.id = g.session_id
       JOIN identity.governed_action a ON a.action_code = g.action_code
      WHERE g.tenant_id = p_tenant_id
        AND g.id = p_step_up_grant_id
        AND s.user_account_id = p_requested_by_user_id
        AND now() - g.granted_at <= a.step_up_max_age;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'AUTHORITY_STEP_UP_ABSENT: step-up grant % is not a fresh grant belonging to '
            'the operator requesting this replacement. A replacement is the last thing '
            'that should proceed on somebody else''s authentication, or on a stale one',
            p_step_up_grant_id
            USING ERRCODE = 'HS403';
    END IF;

    SELECT * INTO v_current FROM edge.authority
      WHERE tenant_id = p_tenant_id AND outlet_id = n.outlet_id AND state = 'held';

    SELECT COALESCE(max(sequence), 0) + 1 INTO v_next FROM edge.authority
     WHERE tenant_id = p_tenant_id AND outlet_id = n.outlet_id;

    IF v_current.holder_node_id = p_claimant_node_id THEN
        RAISE EXCEPTION
            'AUTHORITY_ALREADY_HELD: node % already holds authority for this outlet at '
            'sequence %. A replacement replaces something else',
            p_claimant_node_id, v_current.sequence
            USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO edge.authority_claim (
        tenant_id, outlet_id, claimant_node_id, sequence, superseded_node_id,
        step_up_grant_id, requested_by_user_id, approved_by_user_id,
        fence_method, fence_evidence, lan_probe_at, lan_probe_unreachable)
    VALUES (p_tenant_id, n.outlet_id, p_claimant_node_id, v_next,
            v_current.holder_node_id, p_step_up_grant_id, p_requested_by_user_id,
            p_approved_by_user_id, p_fence_method, p_fence_evidence, now(), true);

    -- THE OLD ONE STOPS BEING THE HOLDER IN THE SAME TRANSACTION THE NEW ONE STARTS.
    -- Two statements with a gap between them is a gap in which both are held, and the
    -- unique index would refuse the second anyway — loudly, which is right, but this way
    -- there is never a moment when it could.
    IF v_current.holder_node_id IS NOT NULL THEN
        UPDATE edge.authority
           SET state = 'superseded', superseded_at = now()
         WHERE tenant_id = p_tenant_id AND outlet_id = n.outlet_id
           AND sequence = v_current.sequence;

        -- WHATEVER THE OLD NODE STILL HELD GOES INTO QUARANTINE, not into the outbox and
        -- not into the bin.
        INSERT INTO edge.quarantined_event (
            tenant_id, outlet_id, from_node_id, event_id, at_sequence, current_sequence,
            subject, subject_id, event_kind, payload, occurred_at)
        SELECT o.tenant_id, o.outlet_id, o.node_id, o.event_id, v_current.sequence, v_next,
               o.subject, o.subject_id, o.event_kind, o.payload, o.occurred_at
          FROM integration.outbox o
         WHERE o.tenant_id = p_tenant_id
           AND o.node_id = v_current.holder_node_id
           AND o.state <> 'acknowledged'
        ON CONFLICT (tenant_id, event_id) DO NOTHING;
        GET DIAGNOSTICS v_quarantined = ROW_COUNT;
    END IF;

    INSERT INTO edge.authority (tenant_id, outlet_id, sequence, holder_node_id,
                                attestation_sha256)
    VALUES (p_tenant_id, n.outlet_id, v_next, p_claimant_node_id,
            edge.update_attestation(lpad(v_next::text, 64, '0')::character(64),
                                    n.update_trust_anchor_sha256));

    INSERT INTO edge.node_admin_action (
        tenant_id, outlet_id, node_id, action_code, performed_by_user_id, detail)
    VALUES (p_tenant_id, n.outlet_id, p_claimant_node_id, 'node.authority.claim',
            p_requested_by_user_id,
            format('sequence %s, approved by %s, old node %s by %s, %s event(s) quarantined',
                   v_next, p_approved_by_user_id,
                   COALESCE(v_current.holder_node_id::text, 'none'), p_fence_method,
                   COALESCE(v_quarantined, 0)));

    RETURN v_next;
END;
$$;

COMMENT ON FUNCTION edge.claim_authority(uuid, uuid, uuid, uuid, uuid, edge.fence_method,
                                         text, boolean) IS
    'FR-EDG-024. The only way to become a replacement writer. Checks the LAN probe first, '
    'because it is the one that says whether the old node is actually gone; everything '
    'else is a record of intent. Supersedes and quarantines in the same transaction the '
    'new holder starts, so there is never a moment when both are held.';

-- ---------------------------------------------------------------------------
-- 6. WHAT A WRITER ASKS BEFORE IT WRITES
-- ---------------------------------------------------------------------------

-- Every writer persists the highest sequence it has accepted and refuses anything lower.
-- The refusal is the whole of FR-EDG-024's "rejects rollback": a fenced node that comes
-- back and presents its old number is told no, by the same function the current holder
-- passes.
CREATE FUNCTION edge.assert_authority(
    p_tenant_id uuid, p_node_id uuid, p_sequence bigint)
RETURNS void
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
DECLARE
    a edge.authority%ROWTYPE;
    v_outlet uuid;
BEGIN
    SELECT outlet_id INTO v_outlet FROM edge.node
      WHERE tenant_id = p_tenant_id AND id = p_node_id;
    IF v_outlet IS NULL THEN
        RAISE EXCEPTION 'NODE_UNKNOWN: no node % for this tenant', p_node_id
            USING ERRCODE = 'HS404';
    END IF;

    SELECT * INTO a FROM edge.authority
      WHERE tenant_id = p_tenant_id AND outlet_id = v_outlet AND state = 'held';
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'AUTHORITY_ABSENT: outlet % has no current authority, so nothing may write '
            'for it', v_outlet
            USING ERRCODE = 'HS409';
    END IF;

    IF a.holder_node_id <> p_node_id THEN
        RAISE EXCEPTION
            'AUTHORITY_NOT_HELD: node % is not the authority for outlet %; sequence % is '
            'held by %. A direct LAN write to a superseded node fails here',
            p_node_id, v_outlet, a.sequence, a.holder_node_id
            USING ERRCODE = 'HS403';
    END IF;

    IF p_sequence < a.sequence THEN
        RAISE EXCEPTION
            'AUTHORITY_SEQUENCE_ROLLBACK: % was presented and the outlet is at %. A '
            'sequence only ever goes up, and a writer that accepted an older one would be '
            'a writer a fenced node could talk round', p_sequence, a.sequence
            USING ERRCODE = 'HS409';
    END IF;
END;
$$;

COMMENT ON FUNCTION edge.assert_authority(uuid, uuid, bigint) IS
    'FR-EDG-024. What a writer asks before it writes. Three refusals: no authority at all, '
    'held by somebody else — which is what a direct LAN write to a superseded node meets — '
    'and a sequence lower than the current one, which is the rollback refusal.';

CREATE FUNCTION edge.release_quarantined_event(
    p_tenant_id uuid, p_quarantined_id bigint, p_user_id uuid, p_reason text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'identity', 'public'
AS $$
BEGIN
    IF p_reason IS NULL OR length(trim(p_reason)) = 0 THEN
        RAISE EXCEPTION
            'QUARANTINE_RELEASE_UNEXPLAINED: releasing an event from a fenced node needs a '
            'reason. It is the one thing nobody should be able to wave through'
            USING ERRCODE = 'HS422';
    END IF;
    PERFORM 1 FROM identity.user_account
      WHERE tenant_id = p_tenant_id AND id = p_user_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'QUARANTINE_RELEASER_UNKNOWN: no such user in this tenant'
            USING ERRCODE = 'HS404';
    END IF;

    UPDATE edge.quarantined_event
       SET released_at = now(), released_by_user_id = p_user_id, release_reason = p_reason
     WHERE tenant_id = p_tenant_id AND id = p_quarantined_id AND released_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'QUARANTINE_EVENT_UNKNOWN_OR_RELEASED: no event % is quarantined and unreleased',
            p_quarantined_id
            USING ERRCODE = 'HS404';
    END IF;
END;
$$;

GRANT SELECT ON edge.authority          TO hospitality_app;
GRANT SELECT ON edge.authority_claim    TO hospitality_app;
GRANT SELECT ON edge.quarantined_event  TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.grant_first_authority(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.claim_authority(
    uuid, uuid, uuid, uuid, uuid, edge.fence_method, text, boolean) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.assert_authority(uuid, uuid, bigint) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.release_quarantined_event(uuid, bigint, uuid, text)
    TO hospitality_app;

-- edge.authority_claim carries the append-only guard, so it must be declared.
CREATE OR REPLACE FUNCTION app.append_only_tables()
RETURNS TABLE (schema_name text, table_name text, reason text)
LANGUAGE sql STABLE
SET search_path TO 'pg_catalog', 'app', 'public'
AS $$
    SELECT n.nspname::text, c.relname::text, 'financial ledger'::text
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relkind = 'r'
       AND app.financial_table_class(n.nspname, c.relname) = 'ledger'
     UNION ALL
    SELECT t.schema_name, t.table_name, t.reason
      FROM (VALUES
        ('pos', 'counter_order_entry',
         'which terminal an order was entered at, and by whom — a fact about what '
         'happened, not a row that is currently true'),
        ('edge', 'node_health_sample',
         'what a node reported about itself; a health history that can be edited is not '
         'evidence'),
        ('edge', 'node_admin_action',
         'administrative access to the node, which must survive the outage that makes '
         'the cloud audit ledger unreachable'),
        ('edge', 'reachability_proof',
         'FR-EDG-023: what each side proved about the other and when. This is the table '
         'an operator reads after an outage to find out which direction failed, and a '
         'reachability history that can be rewritten cannot answer that'),
        ('edge', 'authority_claim',
         'FR-EDG-024: what a replacement showed before it was allowed to write. If this '
         'can be edited afterwards then the fence evidence is a story rather than a '
         'record, and the whole safeguard is somebody''s word'),
        ('integration', 'sync_evidence',
         'FR-DAT-008C: append-only across replay and restart, including the deliveries '
         'the synchronization refused')
      ) AS t(schema_name, table_name, reason)
     ORDER BY 1, 2;
$$;

SELECT app.assert_append_only_guards_are_declared();
