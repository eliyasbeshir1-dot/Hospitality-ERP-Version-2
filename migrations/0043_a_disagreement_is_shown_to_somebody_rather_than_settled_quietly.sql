-- 0043: a disagreement is shown to somebody, rather than settled quietly
--
-- FR-EDG-008 is one of the shortest requirements in the package and one of the hardest to
-- meet honestly: "never use silent last-write-wins for orders, bills, payments, tips, cash
-- or permissions". The word doing the work is SILENT. Last-write-wins is not forbidden as
-- an outcome — an operator may look at a conflict and decide the later write was right.
-- It is forbidden as a DEFAULT, applied by a machine, leaving no trace that there was ever
-- a disagreement.
--
-- So the resolution columns cannot be filled without a person and a sentence, and there is
-- no function that resolves a conflict on its own. That is the whole mechanism: the
-- absence of an automatic path, made structural rather than promised.
--
-- WHAT "EXPOSE RATHER THAN OVERWRITE" MEANS FOR THE LOCAL ROW. FR-EDG-027 says replayed
-- events must expose conflicts instead of silently overwriting. integration.raise_conflict()
-- therefore does exactly one thing to the business data: nothing. It records both sides
-- with their evidence and returns. A caller that wanted the remote value applied must go
-- through a resolution, and a resolution needs an operator. The local row keeps whatever
-- the outlet decided while it was alone, which is the only defensible default: the outlet
-- was serving customers and the cloud was not.
--
-- WHY DUPLICATES NEED A DECLARED KEY RATHER THAN A CLEVER RULE. FR-EDG-016 requires
-- reconnection to produce no duplicate orders, payments or tips. The obvious constraint —
-- one event per (subject, subject_id, event_kind) — is wrong: an order legitimately emits
-- two line-added events. So the caller declares an idempotency key for the operations that
-- must happen once, and the database enforces it. A rule the schema can enforce beats a
-- rule the schema can only describe, and a key that is stated is a key a reviewer can
-- check.

-- ---------------------------------------------------------------------------
-- 1. THE IDEMPOTENCY KEY (FR-EDG-016)
-- ---------------------------------------------------------------------------

ALTER TABLE integration.outbox
    ADD COLUMN idempotency_key text;

COMMENT ON COLUMN integration.outbox.idempotency_key IS
    'FR-EDG-016. Declared by the caller for operations that must happen once — creating '
    'an order, capturing a payment, recording a tip. Nullable because most events may '
    'legitimately repeat: an order emits two line-added events and a constraint over '
    '(subject, subject_id, event_kind) would refuse the second.';

-- Per node, because the key is minted at the outlet and two outlets have no shared
-- namespace to collide in.
CREATE UNIQUE INDEX outbox_idempotency_key_unique
    ON integration.outbox (node_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- The immutability trigger must know about the new column, or the one thing it exists to
-- protect — the identity of a replayed event — would be editable through it.
CREATE OR REPLACE FUNCTION integration.refuse_outbox_rewrite()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'OUTBOX_ROW_IS_PERMANENT: event % is evidence that it was enqueued; a queue '
            'you can delete from cannot show what it failed to send', OLD.event_id
            USING ERRCODE = 'HS409';
    END IF;
    IF NEW.event_id            <> OLD.event_id
       OR NEW.tenant_id        <> OLD.tenant_id
       OR NEW.outlet_id        <> OLD.outlet_id
       OR NEW.node_id          <> OLD.node_id
       OR NEW.subject          <> OLD.subject
       OR NEW.subject_id       <> OLD.subject_id
       OR NEW.event_kind       <> OLD.event_kind
       OR NEW.payload::text    <> OLD.payload::text
       OR NEW.occurred_at      <> OLD.occurred_at
       OR NEW.sequence         <> OLD.sequence
       OR NEW.depends_on_event_id IS DISTINCT FROM OLD.depends_on_event_id
       OR NEW.idempotency_key  IS DISTINCT FROM OLD.idempotency_key THEN
        RAISE EXCEPTION
            'OUTBOX_ROW_IS_IMMUTABLE: event % may change state, attempts and timings and '
            'nothing else. FR-EDG-027 requires a replayed event to keep the id and the '
            'timestamp it was given at the outlet', OLD.event_id
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

-- The enqueue function gains the key. The old signature is dropped rather than left
-- beside the new one: two ways to enqueue, one of which cannot express idempotency, is
-- how a caller ends up creating the duplicate this migration exists to prevent.
DROP FUNCTION integration.enqueue_outbox(uuid, uuid, integration.sync_subject, uuid, text,
                                         jsonb, timestamptz, uuid);

CREATE FUNCTION integration.enqueue_outbox(
    p_tenant_id  uuid,
    p_node_id    uuid,
    p_subject    integration.sync_subject,
    p_subject_id uuid,
    p_event_kind text,
    p_payload    jsonb,
    p_occurred_at timestamptz DEFAULT now(),
    p_depends_on_event_id uuid DEFAULT NULL,
    p_idempotency_key text DEFAULT NULL)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'integration', 'edge', 'public'
AS $$
DECLARE
    v_outlet uuid;
    v_event  uuid;
    v_existing uuid;
BEGIN
    SELECT outlet_id INTO v_outlet FROM edge.node
      WHERE tenant_id = p_tenant_id AND id = p_node_id AND status = 'active';
    IF v_outlet IS NULL THEN
        RAISE EXCEPTION 'NODE_UNKNOWN: no active node % for this tenant', p_node_id
            USING ERRCODE = 'HS404';
    END IF;

    IF p_depends_on_event_id IS NOT NULL THEN
        PERFORM 1 FROM integration.outbox
          WHERE tenant_id = p_tenant_id
            AND event_id  = p_depends_on_event_id
            AND node_id   = p_node_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION
                'OUTBOX_DEPENDENCY_UNKNOWN: event % is not an event of node %',
                p_depends_on_event_id, p_node_id
                USING ERRCODE = 'HS422';
        END IF;
    END IF;

    -- A REPEAT IS NOT AN ERROR AND IS NOT A SECOND EVENT. A waiter whose screen retried
    -- after a dropped connection performed one action, and the honest answer is the event
    -- id the first attempt produced.
    IF p_idempotency_key IS NOT NULL THEN
        SELECT event_id INTO v_existing FROM integration.outbox
          WHERE node_id = p_node_id AND idempotency_key = p_idempotency_key;
        IF v_existing IS NOT NULL THEN
            INSERT INTO integration.sync_evidence (
                tenant_id, outlet_id, node_id, direction, kind, subject_ref, detail)
            VALUES (p_tenant_id, v_outlet, p_node_id, 'outlet_to_cloud',
                    'duplicate_refused', v_existing,
                    format('idempotency key %s was already enqueued as this event',
                           p_idempotency_key));
            RETURN v_existing;
        END IF;
    END IF;

    INSERT INTO integration.outbox (
        tenant_id, outlet_id, node_id, subject, subject_id, event_kind, payload,
        occurred_at, depends_on_event_id, idempotency_key)
    VALUES (p_tenant_id, v_outlet, p_node_id, p_subject, p_subject_id, p_event_kind,
            p_payload, p_occurred_at, p_depends_on_event_id, p_idempotency_key)
    RETURNING event_id INTO v_event;

    INSERT INTO integration.sync_evidence (
        tenant_id, outlet_id, node_id, direction, kind, subject_ref, detail)
    VALUES (p_tenant_id, v_outlet, p_node_id, 'outlet_to_cloud', 'enqueued', v_event,
            format('%s %s', p_subject, p_event_kind));

    RETURN v_event;
END;
$$;

COMMENT ON FUNCTION integration.enqueue_outbox(uuid, uuid, integration.sync_subject, uuid,
                                               text, jsonb, timestamptz, uuid, text) IS
    'FR-INT-003, FR-EDG-016. Enqueues an event inside the transaction that performs the '
    'business write. When an idempotency key is given and already known, returns the '
    'event the first attempt produced rather than creating a second.';

GRANT EXECUTE ON FUNCTION integration.enqueue_outbox(
    uuid, uuid, integration.sync_subject, uuid, text, jsonb, timestamptz, uuid, text)
    TO hospitality_app;

-- ---------------------------------------------------------------------------
-- 2. CONFLICTS (FR-EDG-008, FR-EDG-027)
-- ---------------------------------------------------------------------------

-- Named, so that "resolved" is never a state something drifted into.
CREATE TYPE integration.conflict_resolution AS ENUM (
    'local_stands', 'remote_applied', 'merged', 'both_recorded_separately');

CREATE TABLE integration.conflict (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,
    node_id   uuid NOT NULL,

    subject    integration.sync_subject NOT NULL,
    subject_id uuid NOT NULL,

    -- BOTH SIDES, WITH THEIR EVIDENCE. FR-EDG-008 asks for operator evidence, and an
    -- operator cannot decide between two values they have not been shown.
    local_value  jsonb NOT NULL,
    remote_value jsonb NOT NULL,
    local_occurred_at  timestamptz NOT NULL,
    remote_occurred_at timestamptz NOT NULL,
    detected_at timestamptz NOT NULL DEFAULT now(),
    detail text NOT NULL,

    resolution          integration.conflict_resolution,
    resolved_by_user_id uuid,
    resolution_note     text,
    resolved_at         timestamptz,

    CONSTRAINT conflict_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT conflict_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT conflict_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT conflict_node_fk FOREIGN KEY (tenant_id, node_id)
        REFERENCES edge.node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT conflict_resolver_fk FOREIGN KEY (tenant_id, resolved_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,

    -- THE SIX DOMAINS FR-EDG-008 NAMES. A conflict is only meaningful over data two
    -- places can both change; health and notifications are not among them, and a conflict
    -- row about one would be a category error rather than an incident.
    CONSTRAINT conflict_subject_is_a_conflict_domain CHECK (
        subject IN ('order','bill','payment','tip','cash','permission')),

    CONSTRAINT conflict_detail_is_stated CHECK (length(trim(detail)) > 0),

    -- NO SILENT LAST-WRITE-WINS, AS A CONSTRAINT. A resolution needs a person and a
    -- sentence; all four columns arrive together or none of them do. This is what makes
    -- the prohibition structural rather than a matter of nobody writing the shortcut.
    CONSTRAINT conflict_resolution_needs_an_operator CHECK (
        (resolution IS NULL) = (resolved_by_user_id IS NULL)
    AND (resolution IS NULL) = (resolved_at IS NULL)
    AND (resolution IS NULL) = (resolution_note IS NULL)),
    CONSTRAINT conflict_resolution_note_is_stated CHECK (
        resolution_note IS NULL OR length(trim(resolution_note)) > 0)
);

COMMENT ON TABLE integration.conflict IS
    'FR-EDG-008, FR-EDG-027. A disagreement between what the outlet did while it was '
    'alone and what the cloud holds, over one of the six domains the requirement names. '
    'Both values are recorded with their times. The resolution columns cannot be filled '
    'without a person and a sentence, which is how "never silent last-write-wins" is made '
    'structural: there is no automatic path, rather than a rule nobody has broken yet.';

CREATE INDEX conflict_open_idx
    ON integration.conflict (tenant_id, outlet_id, detected_at DESC)
    WHERE resolution IS NULL;
CREATE INDEX conflict_subject_idx
    ON integration.conflict (tenant_id, subject, subject_id);

ALTER TABLE integration.conflict ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration.conflict FORCE ROW LEVEL SECURITY;
CREATE POLICY conflict_isolation ON integration.conflict FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- A RESOLVED CONFLICT IS NOT RE-OPENED OR RE-DECIDED. The record of what somebody decided
-- and why is the evidence FR-EDG-008 asks for; a second opinion is a second row.
CREATE FUNCTION integration.refuse_conflict_redecision()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'CONFLICT_ROW_IS_PERMANENT: conflict % is the record that a disagreement '
            'happened, which stays true after it is settled', OLD.id
            USING ERRCODE = 'HS409';
    END IF;
    IF OLD.resolution IS NOT NULL THEN
        RAISE EXCEPTION
            'CONFLICT_ALREADY_RESOLVED: conflict % was settled by % at %. A different '
            'decision is a new record, not an edit of this one',
            OLD.id, OLD.resolved_by_user_id, OLD.resolved_at
            USING ERRCODE = 'HS409';
    END IF;
    IF NEW.subject <> OLD.subject OR NEW.subject_id <> OLD.subject_id
       OR NEW.local_value::text  <> OLD.local_value::text
       OR NEW.remote_value::text <> OLD.remote_value::text THEN
        RAISE EXCEPTION
            'CONFLICT_EVIDENCE_IS_IMMUTABLE: the two values an operator is deciding '
            'between cannot change while they decide'
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER conflict_is_decided_once
    BEFORE UPDATE OR DELETE ON integration.conflict
    FOR EACH ROW EXECUTE FUNCTION integration.refuse_conflict_redecision();

-- ---------------------------------------------------------------------------
-- 3. RAISING AND RESOLVING (FR-EDG-008)
-- ---------------------------------------------------------------------------

-- Records the disagreement and touches no business data. That is the requirement: expose
-- rather than overwrite. The local row keeps what the outlet decided while it was alone,
-- because the outlet was serving customers and the cloud was not.
CREATE FUNCTION integration.raise_conflict(
    p_tenant_id  uuid,
    p_node_id    uuid,
    p_subject    integration.sync_subject,
    p_subject_id uuid,
    p_local_value  jsonb,
    p_remote_value jsonb,
    p_local_occurred_at  timestamptz,
    p_remote_occurred_at timestamptz,
    p_detail text)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'integration', 'edge', 'public'
AS $$
DECLARE
    v_outlet uuid;
    v_id     uuid;
BEGIN
    SELECT outlet_id INTO v_outlet FROM edge.node
      WHERE tenant_id = p_tenant_id AND id = p_node_id AND status = 'active';
    IF v_outlet IS NULL THEN
        RAISE EXCEPTION 'NODE_UNKNOWN: no active node % for this tenant', p_node_id
            USING ERRCODE = 'HS404';
    END IF;

    INSERT INTO integration.conflict (
        tenant_id, outlet_id, node_id, subject, subject_id, local_value, remote_value,
        local_occurred_at, remote_occurred_at, detail)
    VALUES (p_tenant_id, v_outlet, p_node_id, p_subject, p_subject_id, p_local_value,
            p_remote_value, p_local_occurred_at, p_remote_occurred_at, p_detail)
    RETURNING id INTO v_id;

    INSERT INTO integration.sync_evidence (
        tenant_id, outlet_id, node_id, direction, kind, subject_ref, detail)
    VALUES (p_tenant_id, v_outlet, p_node_id, 'cloud_to_outlet', 'conflict_raised',
            p_subject_id, format('%s: %s', p_subject, p_detail));

    -- The node is reconciling until somebody has looked. FR-EDG-009's third state exists
    -- for exactly this: not offline, not simply connected, but connected with something
    -- outstanding.
    --
    -- UPSERT, NOT UPDATE. The first draft of this was an UPDATE, and it silently did
    -- nothing for a node that had not yet recorded a synchronization state — which is
    -- every node that has never reached the cloud, and therefore every node in the outage
    -- this whole gate is about. A conflict was raised, correctly, and the surface that
    -- reads connectivity showed nothing at all. An UPDATE that matches no row is not an
    -- error, which is what made it worth catching here rather than on the floor.
    INSERT INTO integration.sync_state (tenant_id, outlet_id, node_id, connectivity)
    VALUES (p_tenant_id, v_outlet, p_node_id, 'reconciling')
    ON CONFLICT (node_id) DO UPDATE
       SET connectivity = CASE WHEN integration.sync_state.paused_reason IS NULL
                               THEN 'reconciling'::edge.connectivity_state
                               ELSE integration.sync_state.connectivity END,
           updated_at = now();

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION integration.raise_conflict(uuid, uuid, integration.sync_subject, uuid,
                                               jsonb, jsonb, timestamptz, timestamptz, text) IS
    'FR-EDG-008, FR-EDG-027. Records a disagreement and changes no business data. A '
    'caller that wants the remote value applied must go through a resolution, and a '
    'resolution needs an operator.';

CREATE FUNCTION integration.resolve_conflict(
    p_tenant_id   uuid,
    p_conflict_id uuid,
    p_resolution  integration.conflict_resolution,
    p_user_id     uuid,
    p_note        text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'integration', 'identity', 'public'
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

    -- THE NOTE IS THE EVIDENCE. A resolution with no reason is last-write-wins performed
    -- by a human being, which is the same loss of information the requirement forbids a
    -- machine.
    IF p_note IS NULL OR length(trim(p_note)) = 0 THEN
        RAISE EXCEPTION
            'CONFLICT_RESOLUTION_UNEXPLAINED: settling a % conflict requires a reason. '
            'FR-EDG-008 asks for operator evidence, and a decision nobody explained is '
            'not evidence', c.subject
            USING ERRCODE = 'HS422';
    END IF;

    PERFORM 1 FROM identity.user_account
      WHERE tenant_id = p_tenant_id AND id = p_user_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'CONFLICT_RESOLVER_UNKNOWN: no such user in this tenant'
            USING ERRCODE = 'HS404';
    END IF;

    UPDATE integration.conflict
       SET resolution = p_resolution, resolved_by_user_id = p_user_id,
           resolution_note = p_note, resolved_at = now()
     WHERE tenant_id = p_tenant_id AND id = p_conflict_id;

    INSERT INTO integration.sync_evidence (
        tenant_id, outlet_id, node_id, direction, kind, subject_ref, detail)
    VALUES (p_tenant_id, c.outlet_id, c.node_id, 'cloud_to_outlet', 'replayed',
            c.subject_id, format('conflict settled as %s: %s', p_resolution, p_note));

    -- Back to connected only when nothing is outstanding.
    UPDATE integration.sync_state s
       SET connectivity = 'cloud_connected', updated_at = now()
     WHERE s.node_id = c.node_id
       AND s.paused_reason IS NULL
       AND NOT EXISTS (SELECT 1 FROM integration.conflict o
                        WHERE o.node_id = c.node_id AND o.resolution IS NULL);
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. RECONNECTION (FR-EDG-016, FR-EDG-027)
-- ---------------------------------------------------------------------------

-- RESTART RECOVERY FOR THE OUTBOX. An event claimed but never acknowledged was in flight
-- when the process died. It is returned to pending rather than assumed delivered: the
-- cloud deduplicates on the event id it already carries, so re-sending is safe and
-- assuming delivery is not.
CREATE FUNCTION integration.recover_in_flight(p_tenant_id uuid, p_node_id uuid)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'integration', 'edge', 'public'
AS $$
DECLARE
    v_outlet uuid;
    v_count  integer;
BEGIN
    SELECT outlet_id INTO v_outlet FROM edge.node
      WHERE tenant_id = p_tenant_id AND id = p_node_id AND status = 'active';
    IF v_outlet IS NULL THEN
        RAISE EXCEPTION 'NODE_UNKNOWN: no active node % for this tenant', p_node_id
            USING ERRCODE = 'HS404';
    END IF;

    WITH recovered AS (
        UPDATE integration.outbox
           SET state = 'pending', claimed_at = NULL
         WHERE tenant_id = p_tenant_id AND node_id = p_node_id AND state = 'in_flight'
        RETURNING event_id
    ), noted AS (
        INSERT INTO integration.sync_evidence (
            tenant_id, outlet_id, node_id, direction, kind, subject_ref, detail)
        SELECT p_tenant_id, v_outlet, p_node_id, 'outlet_to_cloud', 'replayed', r.event_id,
               'in flight when the process stopped; returned to pending, and the cloud '
               'deduplicates on the id it already carries'
          FROM recovered r
        RETURNING 1
    )
    SELECT count(*)::integer INTO v_count FROM noted;

    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION integration.recover_in_flight(uuid, uuid) IS
    'FR-EDG-016. Returns events that were in flight when the process stopped to pending. '
    'Re-sending is safe because the event carries the id the cloud deduplicates on; '
    'assuming delivery is not.';

-- WHETHER RECONNECTION PRODUCED A DUPLICATE. FR-EDG-016 asks for proof, and proof is a
-- query somebody can run rather than an assurance. Returns nothing when the guarantee
-- holds, which is what makes it usable as an assertion.
CREATE FUNCTION integration.duplicate_business_operations(p_tenant_id uuid, p_node_id uuid)
RETURNS TABLE (
    subject     integration.sync_subject,
    subject_id  uuid,
    event_kind  text,
    occurrences integer)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'integration', 'public'
AS $$
    SELECT o.subject, o.subject_id, o.event_kind, count(*)::integer
      FROM integration.outbox o
     WHERE o.tenant_id = p_tenant_id
       AND o.node_id   = p_node_id
       AND o.subject IN ('order','payment','tip')
       AND o.idempotency_key IS NOT NULL
     GROUP BY o.subject, o.subject_id, o.event_kind
    HAVING count(*) > 1
     ORDER BY 1, 2, 3;
$$;

COMMENT ON FUNCTION integration.duplicate_business_operations(uuid, uuid) IS
    'FR-EDG-016. The proof that reconnection produced no duplicate order, payment or '
    'tip, over the operations that declared themselves once-only. Returns nothing when '
    'the guarantee holds.';

-- FR-EDG-009's states, moved deliberately rather than inferred. Reconciling is not
-- settable by hand: it means "there is an open conflict", and letting a caller assert it
-- would make the state a claim rather than a fact.
CREATE FUNCTION integration.set_connectivity(
    p_tenant_id uuid, p_node_id uuid, p_state edge.connectivity_state)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'integration', 'edge', 'public'
AS $$
DECLARE
    v_outlet uuid;
    v_open   integer;
BEGIN
    SELECT outlet_id INTO v_outlet FROM edge.node
      WHERE tenant_id = p_tenant_id AND id = p_node_id AND status = 'active';
    IF v_outlet IS NULL THEN
        RAISE EXCEPTION 'NODE_UNKNOWN: no active node % for this tenant', p_node_id
            USING ERRCODE = 'HS404';
    END IF;

    IF p_state = 'reconciling' THEN
        RAISE EXCEPTION
            'CONNECTIVITY_RECONCILING_IS_DERIVED: a node is reconciling because a '
            'conflict is open, not because something said so. Raise the conflict'
            USING ERRCODE = 'HS422';
    END IF;

    SELECT count(*)::integer INTO v_open FROM integration.conflict
     WHERE node_id = p_node_id AND resolution IS NULL;

    INSERT INTO integration.sync_state (tenant_id, outlet_id, node_id, connectivity,
                                        last_contact_at)
    VALUES (p_tenant_id, v_outlet, p_node_id,
            CASE WHEN p_state = 'cloud_connected' AND v_open > 0
                 THEN 'reconciling'::edge.connectivity_state ELSE p_state END,
            CASE WHEN p_state = 'cloud_connected' THEN now() ELSE NULL END)
    ON CONFLICT (node_id) DO UPDATE
       SET connectivity = EXCLUDED.connectivity,
           last_contact_at = COALESCE(EXCLUDED.last_contact_at,
                                      integration.sync_state.last_contact_at),
           updated_at = now();
END;
$$;

COMMENT ON FUNCTION integration.set_connectivity(uuid, uuid, edge.connectivity_state) IS
    'FR-EDG-009. Moves a node between cloud-connected and local-continuity. Reconciling '
    'cannot be set: it means an open conflict exists, and a settable version of it would '
    'be a claim rather than a fact. Connecting with a conflict open lands in reconciling '
    'for the same reason.';

-- ---------------------------------------------------------------------------
-- 5. THE DECLARATION AND THE GRANTS
-- ---------------------------------------------------------------------------

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
        ('integration', 'sync_evidence',
         'FR-DAT-008C: append-only across replay and restart, including the deliveries '
         'the synchronization refused')
      ) AS t(schema_name, table_name, reason)
     ORDER BY 1, 2;
$$;

-- integration.outbox and integration.conflict refuse DELETE and refuse rewriting their
-- evidence, but both permit the state changes that are their whole purpose, so neither is
-- append-only and neither is declared. The assertion below is what makes that distinction
-- have to be made rather than assumed: it looks for the guard by behaviour, and these two
-- carry their own.
SELECT app.assert_append_only_guards_are_declared();

GRANT SELECT ON integration.conflict TO hospitality_app;
GRANT EXECUTE ON FUNCTION integration.raise_conflict(
    uuid, uuid, integration.sync_subject, uuid, jsonb, jsonb, timestamptz, timestamptz, text)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION integration.resolve_conflict(
    uuid, uuid, integration.conflict_resolution, uuid, text) TO hospitality_app;
GRANT EXECUTE ON FUNCTION integration.recover_in_flight(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION integration.duplicate_business_operations(uuid, uuid)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION integration.set_connectivity(uuid, uuid, edge.connectivity_state)
    TO hospitality_app;
