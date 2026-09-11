-- 0062: a notice about a node needs words for what a node has
--
-- 0061's producers all refused on their first call with
-- `notification_payload_within_bounds`, and the refusal is correct. notify.payload_within_bounds()
-- is a KEY ALLOWLIST, added when every notice was about an order, a ticket or a service
-- request, and it enforces three things worth keeping exactly as they are:
--
--   every key is named in the list, so a payload cannot carry a field nobody agreed to
--   no value is an object or an array, so nothing can be smuggled one level down
--   no value is longer than 128 characters, so a payload cannot hold a sentence about a
--     person — which is the privacy property, and it is the reason for the other two
--
-- A NOTICE ABOUT A NODE HAS NO WORDS IN THAT LIST. It is not that the fence was wrong; it
-- is that seventeen keys were chosen for a world with no edge notices in it, and 0061 is
-- the first thing to need any. Two of what the producers need are ALREADY THERE — `state`
-- and `previous_state` say exactly what a lease transition says — and the producers below
-- are rewritten to use them rather than to add synonyms. What is left is seven.
--
-- EVERY ONE IS AN IDENTIFIER, A COUNT OR A CODE, which is the test the original seventeen
-- pass and the reason the 128-character limit is enough to hold them. None is free text,
-- none is a name, and none could carry what somebody said or who they are.
--
--   node_code        NODE-H1. Which node, in the words an operator uses on the phone.
--   conflict_id      a uuid.
--   print_job_id     a uuid.
--   sync_subject     'order', 'bill' — one of integration.sync_subject's ten values.
--   attempt_count    how many times a print job has been tried.
--   proof_count      how many consecutive bidirectional proofs a recovery has managed.
--   proofs_required  and how many it needs. Both are small integers.
--
-- The three properties are re-asserted at the foot of this file against a payload that
-- breaks each of them, because a fence widened without checking it still refuses anything
-- is a fence somebody has quietly removed.

CREATE OR REPLACE FUNCTION notify.payload_within_bounds(p_payload jsonb)
RETURNS boolean
LANGUAGE sql IMMUTABLE
SET search_path TO 'pg_catalog', 'public'
AS $$
    SELECT jsonb_typeof(p_payload) = 'object'
       -- Every key is one of these. jsonb minus a key array removes them, so an empty
       -- object left over means there was nothing else in it.
       AND (p_payload - ARRAY[
                'order_id', 'ticket_id', 'service_request_id', 'table_session_id',
                'table_node_id', 'station_node_id', 'order_number', 'request_type_code',
                'state', 'previous_state', 'unit_count', 'ready_unit_count',
                'sla_due_at', 'overdue_seconds', 'repeat_ordinal', 'reason_code',
                'escalation_level',
                -- M5b. What an edge notice is about: which node, which conflict, which
                -- print job, and how far a recovery has got. Identifiers, counts and
                -- codes, which is the test the seventeen above pass.
                'node_code', 'conflict_id', 'print_job_id', 'sync_subject',
                'attempt_count', 'proof_count', 'proofs_required']) = '{}'::jsonb
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

-- ---------------------------------------------------------------------------
-- AND THE PRODUCERS SAY IT IN THE WORDS THAT ALREADY EXISTED WHERE THEY COULD
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION edge.announce_lease_transition(
    p_tenant_id uuid,
    p_node_id   uuid,
    p_was       edge.lease_state,
    p_now       edge.lease_state)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'notify', 'ordering', 'public'
AS $$
DECLARE
    n edge.node%ROWTYPE;
    v_event text;
BEGIN
    IF p_was IS NOT DISTINCT FROM p_now THEN
        RETURN NULL;
    END IF;

    SELECT * INTO n FROM edge.node WHERE tenant_id = p_tenant_id AND id = p_node_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'NODE_UNKNOWN: no node % for this tenant', p_node_id
            USING ERRCODE = 'HS404';
    END IF;

    -- THERE ARE THREE LEASE STATES AND FOUR NOTICES, WHICH IS NOT A MISMATCH.
    -- edge.lease_state is live, degraded, expired — there is no `resuming`, and adding one
    -- would be a fourth state whose only purpose is to be announced. RECONNECTING is
    -- PROGRESS, and edge.announce_recovery_progress() produces it from the counter.
    v_event := CASE
        -- Degrading is the FIRST moment anybody can act. Expiry is ten seconds later, and
        -- announcing only that would tell somebody after the decision was already made.
        WHEN p_now = 'degraded' THEN 'EVT-OUTLET-HEARTBEAT-LOST'
        WHEN p_now = 'expired'  THEN 'EVT-LOCAL-CONTINUITY-ENTERED'
        WHEN p_now = 'live' AND p_was <> 'live' THEN 'EVT-OUTLET-RECONNECTED'
        ELSE NULL
    END;

    IF v_event IS NULL THEN
        RETURN NULL;
    END IF;

    PERFORM notify.emit(
        p_tenant_id, n.outlet_id, v_event, 'node'::ordering.artifact_kind,
        p_node_id, p_node_id, NULL,
        -- `state` and `previous_state` rather than `now` and `was`. The allowlist already
        -- had the words for this, and adding synonyms would mean a reader of two notices
        -- had to know that one gate's `was` is another gate's `previous_state`.
        jsonb_build_object('node_code', n.node_code,
                           'previous_state', p_was::text,
                           'state', p_now::text));

    RETURN v_event;
END;
$$;

CREATE OR REPLACE FUNCTION edge.announce_recovery_progress(p_tenant_id uuid, p_node_id uuid)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'notify', 'ordering', 'public'
AS $$
DECLARE
    l edge.forwarding_lease%ROWTYPE;
    n edge.node%ROWTYPE;
    v_required integer;
BEGIN
    SELECT * INTO l FROM edge.forwarding_lease
      WHERE tenant_id = p_tenant_id AND node_id = p_node_id;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    SELECT proofs_required_to_resume INTO v_required
      FROM edge.lease_policy
     WHERE tenant_id = p_tenant_id AND outlet_id = l.outlet_id;
    IF v_required IS NULL THEN
        RAISE EXCEPTION
            'LEASE_POLICY_ABSENT: outlet % has no lease policy, so how many proofs a '
            'recovery takes is undefined. GJ-09 found this table empty on a floor with '
            'two nodes; seeds/0017 is why it is not', l.outlet_id
            USING ERRCODE = 'HS409';
    END IF;

    -- EXACTLY ONE PROOF IN. Not zero, which is an outage nobody has answered yet, and not
    -- the full count, which is EVT-OUTLET-RECONNECTED's to announce.
    IF l.state = 'live' OR l.consecutive_valid_exchanges <> 1 THEN
        RETURN NULL;
    END IF;

    SELECT * INTO n FROM edge.node WHERE tenant_id = p_tenant_id AND id = p_node_id;

    PERFORM notify.emit(
        p_tenant_id, l.outlet_id, 'EVT-OUTLET-RECONNECTING',
        'node'::ordering.artifact_kind, p_node_id, p_node_id, NULL,
        jsonb_build_object('node_code', n.node_code,
                           'state', l.state::text,
                           'proof_count', l.consecutive_valid_exchanges,
                           'proofs_required', v_required));
    RETURN 'EVT-OUTLET-RECONNECTING';
END;
$$;

CREATE OR REPLACE FUNCTION edge.announce_sync_conflict(p_tenant_id uuid, p_conflict_id uuid)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'integration', 'notify', 'ordering', 'public'
AS $$
DECLARE
    c integration.conflict%ROWTYPE;
BEGIN
    SELECT * INTO c FROM integration.conflict
      WHERE tenant_id = p_tenant_id AND id = p_conflict_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'CONFLICT_UNKNOWN: no conflict %', p_conflict_id
            USING ERRCODE = 'HS404';
    END IF;

    -- ONLY WHILE IT IS STILL A QUESTION. A conflict somebody has already settled is not
    -- news, and re-announcing one is how an operator learns to ignore the channel that
    -- carries the ones that matter.
    IF c.resolution IS NOT NULL THEN
        RETURN;
    END IF;

    -- THE CONFLICT'S DETAIL IS NOT CARRIED, deliberately. It is free text a person wrote
    -- about a disagreement, the payload allowlist would refuse it past 128 characters, and
    -- a notice is a pointer to something rather than a copy of it. conflict_id is how a
    -- manager opens the real thing.
    PERFORM notify.emit(
        p_tenant_id, c.outlet_id, 'EVT-SYNC-CONFLICT-DETECTED',
        'node'::ordering.artifact_kind, c.node_id, p_conflict_id, NULL,
        jsonb_build_object('conflict_id', p_conflict_id,
                           'sync_subject', c.subject::text));
END;
$$;

CREATE OR REPLACE FUNCTION edge.announce_print_failure(p_tenant_id uuid, p_job_id uuid)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'docs', 'notify', 'ordering', 'public'
AS $$
DECLARE
    j docs.print_job%ROWTYPE;
BEGIN
    SELECT * INTO j FROM docs.print_job WHERE tenant_id = p_tenant_id AND id = p_job_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PRINT_JOB_UNKNOWN: no print job %', p_job_id USING ERRCODE = 'HS404';
    END IF;

    IF j.state <> 'failed' THEN
        RAISE EXCEPTION
            'PRINT_JOB_NOT_FAILED: job % is %, and announcing a failure that has not '
            'happened would send somebody to a printer that is working',
            p_job_id, j.state
            USING ERRCODE = 'HS409';
    END IF;

    -- last_error IS NOT CARRIED EITHER, for the same reason and one more: it is whatever a
    -- driver said, which is neither bounded nor written for a person to read.
    PERFORM notify.emit(
        p_tenant_id, j.outlet_id, 'EVT-PRINT-JOB-FAILED',
        'node'::ordering.artifact_kind,
        COALESCE((SELECT id FROM edge.node
                   WHERE tenant_id = p_tenant_id AND outlet_id = j.outlet_id
                     AND status = 'active' ORDER BY node_code LIMIT 1), j.id),
        p_job_id, NULL,
        jsonb_build_object('print_job_id', p_job_id,
                           'attempt_count', j.attempts,
                           'state', j.state::text));
END;
$$;

-- ---------------------------------------------------------------------------
-- THE THREE PROPERTIES STILL HOLD, PROVED RATHER THAN ASSERTED
-- ---------------------------------------------------------------------------
--
-- A fence widened without checking that it still refuses anything is a fence somebody has
-- quietly removed. Each of these is a payload that must be refused, and the migration
-- fails now if any of them is admitted.
DO $$
DECLARE
    v_case text;
    v_bad  jsonb;
BEGIN
    FOREACH v_case IN ARRAY ARRAY['unknown key', 'nested object', 'prose'] LOOP
        v_bad := CASE v_case
            WHEN 'unknown key'   THEN jsonb_build_object('guest_name', 'Almaz')
            WHEN 'nested object' THEN jsonb_build_object('node_code',
                                        jsonb_build_object('smuggled', 'yes'))
            ELSE jsonb_build_object('node_code', repeat('x', 129))
        END;
        IF notify.payload_within_bounds(v_bad) THEN
            RAISE EXCEPTION
                'PAYLOAD_BOUNDS_ADMITS_%: widening the allowlist for M5b''s seven keys has '
                'let through a payload it must refuse. The privacy property is that a '
                'notice cannot carry a sentence about a person, and it is the reason the '
                'other two rules exist',
                upper(replace(v_case, ' ', '_'))
                USING ERRCODE = 'HS500';
        END IF;
    END LOOP;

    -- And the shapes the producers actually send are admitted.
    IF NOT notify.payload_within_bounds(
             jsonb_build_object('node_code', 'NODE-H1', 'previous_state', 'live',
                                'state', 'degraded')) THEN
        RAISE EXCEPTION 'PAYLOAD_BOUNDS_REFUSES_ITS_OWN_PRODUCERS'
            USING ERRCODE = 'HS500';
    END IF;
END;
$$;
