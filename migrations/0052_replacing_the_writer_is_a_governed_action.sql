-- 0052: replacing an outlet's writer is a governed action, and it is registered as one
--
-- 0050 requires a live step-up grant belonging to the operator asking for a replacement.
-- It named no action code, so any grant would have done — and "any grant" means a manager
-- who stepped up five minutes ago to change a price could hand authority to a different
-- node on the strength of it. FR-AUTH-006's window is per ACTION for exactly that reason.
--
-- THIS IS THE THIRD TIME THIS SHAPE HAS COME UP AND IT IS WRITTEN DOWN AS A PATTERN NOW.
-- OP-C found it with `table.seat`, OP-D with `order.accept`, and seeds/0010 recorded the
-- cost: a new governed or graded action needs THREE things, and missing any one of them
-- leaves behaviour that looks built and is unreachable.
--
--   1. the action in the trigger that installs it for a NEW tenant        (here)
--   2. a way to install it for tenants that ALREADY EXIST                 (seeds/0015)
--   3. the caller that uses it                                            (0050, done)
--
-- The trigger fires on INSERT and the demonstration tenants were inserted at seeds/0001,
-- so 1 alone reaches nobody who exists today. A migration cannot backfill it either:
-- migrations run with no tenant context and org.tenant carries FORCE row level security,
-- so a backfill SELECT over it matches nothing. That is why installers exist at all.
--
-- THE WINDOW IS FIVE MINUTES, like every other strong action. Not longer because this is
-- the most consequential thing an operator can do to an outlet, and not shorter because
-- fencing a node — walking to a switch, pulling a cable, confirming a link light — takes
-- minutes, and a window that expired mid-fence would push somebody to fence first and
-- authenticate afterwards, which is the opposite of what it is for.

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
        -- Registered now, exercised from M4. No caller exists at M1.
        (NEW.id, 'payment.refund',         'strong', true,  interval '5 minutes',  'M4'),
        (NEW.id, 'check.void',             'strong', true,  interval '5 minutes',  'M4'),
        (NEW.id, 'discount.high',          'strong', true,  interval '5 minutes',  'M4'),
        (NEW.id, 'payout.release',         'strong', true,  interval '5 minutes',  'M4'),
        -- Registered now, exercised from M6.
        (NEW.id, 'report.export',          'strong', true,  interval '15 minutes', 'M6'),
        -- M5b. Handing an outlet's write authority to a different node, which is the most
        -- consequential thing an operator can do to one. Five minutes for the reason the
        -- header gives: fencing takes minutes, and a window that expired mid-fence would
        -- push somebody to fence first and authenticate afterwards.
        (NEW.id, 'node.authority.claim',   'strong', true,  interval '5 minutes',  'M5b'),
        -- Routine actions: no step-up, but a quick PIN is still enough only here.
        (NEW.id, 'order.view',             'low',    false, NULL,                  'M1'),
        (NEW.id, 'session.resume',         'low',    false, NULL,                  'M1');
    RETURN NULL;
END;
$$;

-- ---------------------------------------------------------------------------
-- AND THE INSTALLER FOR TENANTS THAT ALREADY EXIST
-- ---------------------------------------------------------------------------
--
-- Idempotent, so a seed that calls it twice is a seed that called it twice. The same
-- shape as pos.install_registries_for(), and for the same reason.
CREATE FUNCTION identity.install_governed_actions_for(p_tenant_id uuid)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'identity', 'org', 'public'
AS $$
DECLARE
    v_installed integer;
BEGIN
    PERFORM 1 FROM org.tenant WHERE id = p_tenant_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TENANT_UNKNOWN: no tenant %', p_tenant_id USING ERRCODE = 'HS404';
    END IF;

    INSERT INTO identity.governed_action
        (tenant_id, action_code, minimum_strength, step_up_required, step_up_max_age,
         governed_from_gate)
    SELECT p_tenant_id, 'node.authority.claim', 'strong', true, interval '5 minutes', 'M5b'
     WHERE NOT EXISTS (SELECT 1 FROM identity.governed_action
                        WHERE tenant_id = p_tenant_id
                          AND action_code = 'node.authority.claim');
    GET DIAGNOSTICS v_installed = ROW_COUNT;
    RETURN v_installed;
END;
$$;

COMMENT ON FUNCTION identity.install_governed_actions_for(uuid) IS
    'The second of the three things a new governed action needs. The trigger above covers '
    'tenants created from now on; this covers the ones that already exist, because a '
    'migration cannot — org.tenant carries FORCE row level security and a migration runs '
    'with no tenant context, so a backfill would match nothing. OP-C met this with '
    'table.seat and OP-D with order.accept; seeds/0010 records the cost of missing it.';

-- ---------------------------------------------------------------------------
-- AND THE CLAIM MUST CARRY A GRANT FOR *THIS* ACTION
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION edge.claim_authority(
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

    IF NOT p_lan_probe_unreachable THEN
        RAISE EXCEPTION
            'AUTHORITY_FENCE_UNPROVEN: the LAN probe reached the node being replaced. '
            'Whatever else was done, it is still able to write, and two writers is the '
            'one outcome this whole mechanism exists to prevent'
            USING ERRCODE = 'HS409';
    END IF;

    -- THE GRANT MUST BE FOR THIS ACTION, and that clause is what 0050 was missing. Without
    -- it any live grant would do, so a manager who stepped up to change a price could hand
    -- an outlet's authority to a different node on the strength of it. FR-AUTH-006 scopes
    -- the window per action for precisely this reason.
    PERFORM 1
       FROM identity.step_up_grant g
       JOIN identity.session s ON s.tenant_id = g.tenant_id AND s.id = g.session_id
       JOIN identity.governed_action a ON a.tenant_id = g.tenant_id
                                      AND a.action_code = g.action_code
      WHERE g.tenant_id = p_tenant_id
        AND g.id = p_step_up_grant_id
        AND g.action_code = 'node.authority.claim'
        AND s.user_account_id = p_requested_by_user_id
        AND now() - g.granted_at <= a.step_up_max_age;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'AUTHORITY_STEP_UP_ABSENT: step-up grant % is not a fresh node.authority.claim '
            'grant belonging to the operator requesting this replacement. A replacement is '
            'the last thing that should proceed on somebody else''s authentication, on a '
            'stale one, or on one taken for a different act',
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

    IF v_current.holder_node_id IS NOT NULL THEN
        UPDATE edge.authority
           SET state = 'superseded', superseded_at = now()
         WHERE tenant_id = p_tenant_id AND outlet_id = n.outlet_id
           AND sequence = v_current.sequence;

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

GRANT EXECUTE ON FUNCTION identity.install_governed_actions_for(uuid) TO hospitality_app;
