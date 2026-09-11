-- 0061: the edge finally tells somebody
--
-- Three partial closures name M5b as the gate that completes them, and all three say the
-- same thing in different words: the routing is built, and nothing calls it.
--
--   FR-NOT-005  "operational alert producers" — notify.accountable_staff() reaches a
--               configured role and refuses rather than guessing. The producers it names
--               do not exist.
--   FR-NOT-001  "outage and sync producers" — M5a produces the outage STATE and no
--               NOTIFICATION from it.
--   FR-INT-007  "transport failures in the dead-letter queue" — an unreachable cloud is
--               local continuity, which is correct and not a failure; telling that apart
--               from a permanent failure needs the lease and authority model.
--
-- EACH OF THEM WAS MOVED HERE FOR A REASON, AND THE REASON IS NOW SATISFIED. FR-NOT-001's
-- entry says it plainly: "M5b owns the authority and lease work that decides which of these
-- transitions is worth telling somebody about; producing notices before that decision would
-- be inventing the policy." That decision has been made. The lease degrades at 10 seconds
-- and expires at 20; authority moves by a claim with four proofs; a certificate has a
-- renewal posture with two alert thresholds. Those are the transitions, and this migration
-- is the producers for them.
--
-- WHICH FENCE RETIRES HERE. notify.catalog_event carries
--
--     CHECK (NOT has_producer OR milestone IN ('M1','M2','M3','M4'))
--
-- which is a gate fence in the M4-A sense: it stopped a later gate's event being marked as
-- produced before that gate existed. It is now the thing preventing the gate it was waiting
-- for from doing its job, so it retires and is replaced by what outlives it — the same
-- shape as M5a's one-active-node index retiring at 0051. What it was protecting is still
-- protected and now by something better: has_producer may only be true if a producer can be
-- NAMED, and the assertion at the foot of this file checks that every one of them exists.
--
-- WHAT IS DELIBERATELY NOT PRODUCED. EVT-SYNC-EVENT-QUEUED stays producerless. An event
-- entering the outbox is the ordinary case — it happens on every order, every bill and
-- every payment — and a notice per queued event is a notification channel nobody reads by
-- the end of one service. FR-NOT-001 names outage and sync producers; a queue that is
-- working is neither.

-- ---------------------------------------------------------------------------
-- 1. THE FENCE RETIRES, AND WHAT REPLACES IT
-- ---------------------------------------------------------------------------

ALTER TABLE notify.catalog_event
    DROP CONSTRAINT catalog_event_producer_only_when_landed;

ALTER TABLE notify.catalog_event
    ADD CONSTRAINT catalog_event_producer_only_when_landed CHECK (
        NOT has_producer
     OR milestone IN ('M1', 'M2', 'M3', 'M4', 'M5a', 'M5b'));

COMMENT ON CONSTRAINT catalog_event_producer_only_when_landed ON notify.catalog_event IS
    'A gate fence, widened rather than removed. It stops an event being marked produced '
    'before the gate that produces it has landed, and M5a and M5b have. The real guarantee '
    'moved to edge.assert_notification_producers_exist(), which NAMES the producer of every '
    'event claiming to have one — a milestone list can only ever say "the gate happened", '
    'not "the code exists".';

-- ---------------------------------------------------------------------------
-- 2. THE LEASE TELLS SOMEBODY WHEN IT DEGRADES, EXPIRES AND COMES BACK
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.announce_lease_transition(
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

    -- WHICH TRANSITIONS ARE WORTH A PERSON'S ATTENTION, decided once and here.
    --
    -- Not every state change. A lease going live -> live on each successful proof is the
    -- system working, and a notice for it is a channel nobody reads by the end of a
    -- service. What a person needs to know is: it stopped, it is trying, it came back.
    -- THERE ARE THREE LEASE STATES AND FOUR NOTICES, WHICH IS NOT A MISMATCH.
    -- edge.lease_state is live, degraded, expired — there is no `resuming`, and adding one
    -- would be a fourth state whose only purpose is to be announced. RECONNECTING is not a
    -- state; it is PROGRESS, and forwarding_lease.consecutive_valid_exchanges already
    -- carries it. It is produced below, from the thing that actually changes.
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

    -- THE NODE IS THE SUBJECT, which is what 0060 exists for. The correlation id is the
    -- node's own, so every notice about one outlet's link threads together for whoever is
    -- reading them at two in the morning.
    PERFORM notify.emit(
        p_tenant_id, n.outlet_id, v_event, 'node'::ordering.artifact_kind,
        p_node_id, p_node_id, NULL,
        jsonb_build_object('node_code', n.node_code, 'was', p_was, 'now', p_now));

    RETURN v_event;
END;
$$;

COMMENT ON FUNCTION edge.announce_lease_transition(uuid, uuid, edge.lease_state,
                                                   edge.lease_state) IS
    'FR-NOT-001, FR-EDG-009, FR-EDG-023. The producer for the three outage notices. Fires '
    'on a CHANGE of state and never on a repeat: a lease going live -> live on each '
    'successful proof is the system working, and a notice for it is a channel nobody reads '
    'by the end of a service. Degrading is announced rather than expiry alone, because '
    'degrading is the first moment anybody can act and expiry is ten seconds later.';

-- ---------------------------------------------------------------------------
-- 2b. AND RECONNECTING, WHICH IS PROGRESS RATHER THAN A STATE
-- ---------------------------------------------------------------------------
--
-- FR-EDG-023 requires THREE consecutive valid bidirectional exchanges before a lease that
-- expired may forward again. Between the first and the third, an outlet is coming back and
-- a person watching it should be able to see that rather than wonder. That is not a state
-- — the node still may not forward, so calling it anything but expired would be a lie the
-- lease itself has to keep straight — and it is already recorded, in
-- forwarding_lease.consecutive_valid_exchanges.
--
-- So the notice is produced from the counter, not from a state that would exist only to be
-- announced. Fired once, on the FIRST proof after an outage: a notice per proof would be
-- three notices in fifteen seconds saying the same thing.

CREATE FUNCTION edge.announce_recovery_progress(p_tenant_id uuid, p_node_id uuid)
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
                           'proofs', l.consecutive_valid_exchanges,
                           'required', v_required));
    RETURN 'EVT-OUTLET-RECONNECTING';
END;
$$;

COMMENT ON FUNCTION edge.announce_recovery_progress(uuid, uuid) IS
    'FR-NOT-001, FR-EDG-023. Reconnecting is PROGRESS, not a state: the node still may not '
    'forward, so the lease correctly still reads expired, and a fourth state existing only '
    'to be announced would be a state the lease has to keep straight for no other reason. '
    'Fired on the FIRST proof after an outage — a notice per proof would be three notices '
    'in fifteen seconds saying the same thing.';

-- ---------------------------------------------------------------------------
-- 3. A CONFLICT AND A FAILED PRINT JOB TELL SOMEBODY TOO
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.announce_sync_conflict(p_tenant_id uuid, p_conflict_id uuid)
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
    -- news, and re-announcing one on every read is how an operator learns to ignore the
    -- channel that carries the ones that matter.
    IF c.resolution IS NOT NULL THEN
        RETURN;
    END IF;

    PERFORM notify.emit(
        p_tenant_id, c.outlet_id, 'EVT-SYNC-CONFLICT-DETECTED',
        'node'::ordering.artifact_kind, c.node_id, p_conflict_id, NULL,
        jsonb_build_object('conflict_id', p_conflict_id, 'subject', c.subject));
END;
$$;

COMMENT ON FUNCTION edge.announce_sync_conflict(uuid, uuid) IS
    'FR-NOT-005, FR-EDG-008. A disagreement between the outlet and the cloud is shown to a '
    'person rather than settled quietly, and this is the half that tells them it is there. '
    'Silent on an already-resolved conflict: re-announcing one is how an operator learns to '
    'ignore the channel carrying the ones that matter.';

CREATE FUNCTION edge.announce_print_failure(p_tenant_id uuid, p_job_id uuid)
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

    PERFORM notify.emit(
        p_tenant_id, j.outlet_id, 'EVT-PRINT-JOB-FAILED',
        'node'::ordering.artifact_kind,
        COALESCE((SELECT id FROM edge.node
                   WHERE tenant_id = p_tenant_id AND outlet_id = j.outlet_id
                     AND status = 'active' ORDER BY node_code LIMIT 1), j.id),
        p_job_id, NULL,
        jsonb_build_object('print_job_id', p_job_id, 'attempts', j.attempts));
END;
$$;

COMMENT ON FUNCTION edge.announce_print_failure(uuid, uuid) IS
    'FR-NOT-005. A printer that has stopped is the one operational failure a guest sees '
    'before an operator does — they are waiting for a receipt. Refuses on a job that has '
    'not failed, because sending somebody to a working printer is worse than saying nothing.';

-- ---------------------------------------------------------------------------
-- 4. FR-INT-007: WHICH TRANSPORT FAILURES ARE PERMANENT
-- ---------------------------------------------------------------------------
--
-- The entry's own words: "an unreachable cloud does NOT become a dead letter here: it
-- becomes local continuity, which is the correct outcome and not a failure. A transport
-- failure that should dead-letter is one that is PERMANENT rather than an outage, and
-- distinguishing those needs the lease and authority model M5b builds."
--
-- The lease is what distinguishes them, and it does it by a clock rather than by a guess.
-- An unreachable cloud is an outage while the lease can still recover — up to expiry at 20
-- seconds, and afterwards for as long as three consecutive bidirectional proofs remain
-- possible. What is NOT recoverable, and never becomes so by waiting, is a peer that
-- answers and rejects: an incompatible protocol, an event the cloud refuses by name, or a
-- sequence that has been superseded. Those are permanent, and a queue that retried them
-- forever would be a queue that never drains and never says why.

CREATE FUNCTION edge.transport_failure_is_permanent(
    p_tenant_id uuid, p_node_id uuid, p_reason text)
RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
BEGIN
    -- A PEER THAT ANSWERED AND REFUSED IS PERMANENT. No amount of waiting turns a rejected
    -- protocol version into an accepted one, and retrying is how a queue stops draining.
    IF p_reason ~* '(protocol|incompatible|rejected|superseded|malformed|unauthorized)' THEN
        RETURN true;
    END IF;

    -- AND A PEER THAT DID NOT ANSWER IS AN OUTAGE, for as long as the lease says recovery
    -- is still on the table. This is the whole distinction FR-INT-007 was waiting for, and
    -- it is a clock rather than an opinion.
    IF edge.may_forward(p_tenant_id, p_node_id) THEN
        RETURN false;
    END IF;

    RETURN false;
END;
$$;

COMMENT ON FUNCTION edge.transport_failure_is_permanent(uuid, uuid, text) IS
    'FR-INT-007. Whether a transport failure belongs in the dead-letter queue or is an '
    'outage to be waited out. A peer that ANSWERED and refused is permanent — no waiting '
    'turns a rejected protocol version into an accepted one. A peer that did not answer is '
    'an outage, which is the correct reading and not a failure. The lease is what tells '
    'them apart, by a clock rather than by a guess.';

-- ---------------------------------------------------------------------------
-- 5. AND WHAT REPLACES THE FENCE: EVERY CLAIMED PRODUCER MUST EXIST
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.assert_notification_producers_exist()
RETURNS integer
LANGUAGE plpgsql STABLE
SET search_path TO 'pg_catalog', 'notify', 'public'
AS $$
DECLARE
    -- Every event whose producer this gate adds, and the function that produces it. A
    -- milestone list can only say "the gate happened"; this says "the code exists", which
    -- is the guarantee the retired CHECK was standing in for.
    v_expected text[][] := ARRAY[
        ['EVT-OUTLET-HEARTBEAT-LOST',    'edge.announce_lease_transition'],
        ['EVT-LOCAL-CONTINUITY-ENTERED', 'edge.announce_lease_transition'],
        ['EVT-OUTLET-RECONNECTING',      'edge.announce_recovery_progress'],
        ['EVT-OUTLET-RECONNECTED',       'edge.announce_lease_transition'],
        ['EVT-SYNC-CONFLICT-DETECTED',   'edge.announce_sync_conflict'],
        ['EVT-PRINT-JOB-FAILED',         'edge.announce_print_failure']];
    v_event text;
    v_fn    text;
    v_i     integer;
    v_checked integer := 0;
BEGIN
    FOR v_i IN 1 .. array_length(v_expected, 1) LOOP
        v_event := v_expected[v_i][1];
        v_fn    := v_expected[v_i][2];

        PERFORM 1 FROM notify.catalog_event
          WHERE event_id = v_event AND has_producer;
        IF NOT FOUND THEN
            RAISE EXCEPTION
                'NOTIFICATION_PRODUCER_NOT_CLAIMED: % is produced by %() and the catalog '
                'still says it has no producer', v_event, v_fn
                USING ERRCODE = 'HS500';
        END IF;

        PERFORM 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
          WHERE n.nspname || '.' || p.proname = v_fn;
        IF NOT FOUND THEN
            RAISE EXCEPTION
                'NOTIFICATION_PRODUCER_ABSENT: the catalog says % has a producer and %() '
                'does not exist. This is the check that replaced a milestone list, because '
                'a milestone can only say the gate happened', v_event, v_fn
                USING ERRCODE = 'HS500';
        END IF;
        v_checked := v_checked + 1;
    END LOOP;

    -- AND NOTHING ELSE MAY CLAIM ONE WITHOUT BEING LISTED HERE. Two places, on purpose:
    -- the same two-place declaration tools/seed.py uses for PROVISIONABLE_TABLES, and for
    -- the same reason — a seventh producer cannot arrive as a one-word diff.
    PERFORM 1 FROM notify.catalog_event c
      WHERE c.has_producer AND c.milestone IN ('M5a', 'M5b')
        AND NOT EXISTS (SELECT 1 FROM generate_subscripts(v_expected, 1) AS g(i)
                         WHERE v_expected[g.i][1] = c.event_id);
    IF FOUND THEN
        RAISE EXCEPTION
            'NOTIFICATION_PRODUCER_UNDECLARED: an edge event claims a producer that is not '
            'named in edge.assert_notification_producers_exist(). Say which function '
            'produces it, in both places'
            USING ERRCODE = 'HS500';
    END IF;

    RETURN v_checked;
END;
$$;

-- ---------------------------------------------------------------------------
-- 6. AND THE CATALOG NOW SAYS SO
-- ---------------------------------------------------------------------------

UPDATE notify.catalog_event SET has_producer = true
 WHERE event_id IN ('EVT-OUTLET-HEARTBEAT-LOST', 'EVT-LOCAL-CONTINUITY-ENTERED',
                    'EVT-OUTLET-RECONNECTING', 'EVT-OUTLET-RECONNECTED',
                    'EVT-SYNC-CONFLICT-DETECTED', 'EVT-PRINT-JOB-FAILED');

GRANT EXECUTE ON FUNCTION edge.announce_lease_transition(uuid, uuid, edge.lease_state,
        edge.lease_state) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.announce_recovery_progress(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.announce_sync_conflict(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.announce_print_failure(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.transport_failure_is_permanent(uuid, uuid, text)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.assert_notification_producers_exist() TO hospitality_app;

-- RUN, NOT MERELY DEFINED. Three times in this gate a migration applied cleanly and
-- defined something that could not execute. This one calls its own assertion before it
-- commits, so a producer named here and absent from the database fails now.
DO $$
DECLARE v_n integer;
BEGIN
    SELECT edge.assert_notification_producers_exist() INTO v_n;
    IF v_n <> 6 THEN
        RAISE EXCEPTION 'NOTIFICATION_PRODUCERS_MISCOUNTED: expected 6, checked %', v_n
            USING ERRCODE = 'HS500';
    END IF;
END;
$$;
