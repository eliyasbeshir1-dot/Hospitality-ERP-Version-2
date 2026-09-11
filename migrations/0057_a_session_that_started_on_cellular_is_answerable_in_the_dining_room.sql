-- 0057: a session that started on cellular is answerable in the dining room
--
-- FR-EDG-026: "An active table session and its participant tokens remain valid when a
-- customer moves from cloud access to local Wi-Fi, without duplicate orders or loss of
-- cart ownership."
--
-- WHAT WAS ACTUALLY MISSING, FOUND BY LOOKING RATHER THAN BY ASSUMING. The node runs its
-- own database. integration.sync_direction has had a `cloud_to_outlet` value since 0041
-- and nothing has ever produced one: the sync worker pushes the outbox up and
-- acknowledges, and that is all it does. So a guest session created at the cloud exists
-- only at the cloud, and when their phone starts talking to the node instead:
--
--   the session token is unknown            -> they are asked to start again at the table
--   the idempotency key is unknown          -> a RETRY BECOMES A SECOND ORDER
--
-- The second is the one FR-EDG-026 names, and it is the expensive one. A guest whose
-- "Place order" request was answered by a cloud that then became unreachable retries — the
-- browser retries, or they press it again — and the node, which has never heard of the
-- key, takes it as a new order. The kitchen makes two. Nobody finds out until the bill.
--
-- WHY THIS IS NARROW ON PURPOSE. The general answer is bidirectional replication, and that
-- is a much larger thing than this requirement asks for and than this gate should build.
-- FR-EDG-026 names exactly three properties — tokens still valid, no duplicate order, cart
-- ownership intact — and all three are answered by the node holding two kinds of row for
-- its OWN outlet's live sessions. So this replicates two tables' worth of state and calls
-- itself what it is.
--
-- IT MOVES DIGESTS, NOT TOKENS. identity.session stores token_digest and so does this. The
-- node can verify a token a guest presents; it cannot mint one and there is nothing here
-- to steal that the node's own database did not already have to hold.

-- ---------------------------------------------------------------------------
-- 1. WHAT THE CLOUD OFFERS THE NODE
-- ---------------------------------------------------------------------------

CREATE TABLE edge.continuity_record (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,

    -- 'session' or 'idempotency'. Deliberately a small CHECK rather than an enum: this is
    -- the complete list FR-EDG-026 needs and a third kind should be an argument, not a
    -- one-word addition to a type nobody reads.
    record_kind text NOT NULL,

    -- The natural key at the far end, so applying twice is applying once.
    record_key text NOT NULL,

    payload jsonb NOT NULL,

    -- WHEN THE THING THIS DESCRIBES STOPS MATTERING. A session that has expired and an
    -- idempotency key whose window has passed are both dead weight, and a continuity
    -- table that only grows is a table somebody eventually truncates in a hurry.
    valid_until timestamptz NOT NULL,

    produced_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT continuity_record_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT continuity_record_identity UNIQUE (tenant_id, outlet_id, record_kind, record_key),
    CONSTRAINT continuity_record_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT continuity_record_kind_is_known CHECK (
        record_kind IN ('session', 'idempotency')),
    CONSTRAINT continuity_record_key_is_stated CHECK (length(trim(record_key)) > 0),
    CONSTRAINT continuity_record_expires CHECK (valid_until > produced_at)
);

COMMENT ON TABLE edge.continuity_record IS
    'FR-EDG-026. The two kinds of row a node needs to answer for a session the cloud '
    'started: the session itself and the idempotency keys spent against it. Digests only — '
    'a node can VERIFY a token a guest presents and cannot mint one. Narrow on purpose: '
    'the general answer is bidirectional replication and that is not what this requirement '
    'asks for.';

CREATE INDEX continuity_record_pending_idx
    ON edge.continuity_record (tenant_id, outlet_id, produced_at)
    WHERE valid_until > produced_at;

ALTER TABLE edge.continuity_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.continuity_record FORCE ROW LEVEL SECURITY;
CREATE POLICY continuity_record_isolation ON edge.continuity_record FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 2. PRODUCING THEM, AT THE CLOUD
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.offer_continuity(p_tenant_id uuid, p_outlet_id uuid)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'identity', 'service', 'public'
AS $$
DECLARE
    v_written integer := 0;
    v_n       integer;
BEGIN
    -- LIVE SESSIONS ONLY. A revoked or expired session is one the node should refuse too,
    -- and offering it would hand the node a token to honour that the cloud has stopped
    -- honouring — the exact disagreement between two writers this gate exists to prevent.
    INSERT INTO edge.continuity_record
        (tenant_id, outlet_id, record_kind, record_key, payload, valid_until)
    SELECT s.tenant_id, s.outlet_id, 'session', s.id::text,
           jsonb_build_object(
               'session_id',      s.id,
               'token_digest',    encode(s.token_digest, 'hex'),
               'established_with', s.established_with,
               'user_account_id', s.user_account_id,
               'issued_at',       s.issued_at,
               'expires_at',      s.expires_at),
           s.expires_at
      FROM identity.session s
     WHERE s.tenant_id = p_tenant_id
       AND s.outlet_id = p_outlet_id
       AND s.revoked_at IS NULL
       AND s.expires_at > now()
        ON CONFLICT (tenant_id, outlet_id, record_kind, record_key) DO UPDATE
           SET payload = EXCLUDED.payload,
               valid_until = EXCLUDED.valid_until,
               produced_at = now();
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_written := v_written + v_n;

    -- AND THE KEYS ALREADY SPENT. This is the half that stops a retry becoming a second
    -- order, and it is the reason the whole table exists.
    --
    -- The window is 24 hours because a guest retry happens in seconds and a service takes
    -- an evening; anything shorter risks the transition itself falling outside it, and
    -- anything longer keeps keys past the point where re-sending the same request means
    -- the same thing.
    INSERT INTO edge.continuity_record
        (tenant_id, outlet_id, record_kind, record_key, payload, valid_until)
    SELECT k.tenant_id, k.outlet_id, 'idempotency', k.scope || '|' || k.idem_key,
           jsonb_build_object(
               'scope',          k.scope,
               'idem_key',       k.idem_key,
               'request_digest', encode(k.request_digest, 'hex'),
               'result_id',      k.result_id),
           k.created_at + interval '24 hours'
      FROM service.idempotency_key k
     WHERE k.tenant_id = p_tenant_id
       AND k.outlet_id = p_outlet_id
       AND k.created_at + interval '24 hours' > now()
        ON CONFLICT (tenant_id, outlet_id, record_kind, record_key) DO UPDATE
           SET payload = EXCLUDED.payload,
               produced_at = now();
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_written := v_written + v_n;

    RETURN v_written;
END;
$$;

COMMENT ON FUNCTION edge.offer_continuity(uuid, uuid) IS
    'FR-EDG-026. What the cloud offers a node so the node can answer for a session the '
    'cloud started. Live sessions only: offering a revoked one would hand the node a token '
    'to honour that the cloud has stopped honouring, which is two writers disagreeing about '
    'who is logged in.';

-- ---------------------------------------------------------------------------
-- 3. APPLYING THEM, AT THE NODE
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.apply_continuity(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (sessions_applied integer, keys_applied integer)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'identity', 'service', 'public'
AS $$
DECLARE
    v_sessions integer := 0;
    v_keys     integer := 0;
BEGIN
    INSERT INTO identity.session
        (id, tenant_id, outlet_id, user_account_id, token_digest,
         established_with, issued_at, expires_at)
    SELECT (c.payload ->> 'session_id')::uuid, c.tenant_id, c.outlet_id,
           NULLIF(c.payload ->> 'user_account_id', '')::uuid,
           decode(c.payload ->> 'token_digest', 'hex'),
           (c.payload ->> 'established_with')::identity.authentication_strength,
           (c.payload ->> 'issued_at')::timestamptz,
           (c.payload ->> 'expires_at')::timestamptz
      FROM edge.continuity_record c
     WHERE c.tenant_id = p_tenant_id AND c.outlet_id = p_outlet_id
       AND c.record_kind = 'session'
       AND c.valid_until > now()
        -- ALREADY HERE MEANS ALREADY HERE. A session the node knows about is one it has
        -- possibly already advanced — rotated, revoked at the table — and overwriting it
        -- with the cloud's older copy would undo a decision made where the guest is. The
        -- cloud is not more authoritative about a session than the outlet holding it.
        ON CONFLICT (tenant_id, id) DO NOTHING;
    GET DIAGNOSTICS v_sessions = ROW_COUNT;

    INSERT INTO service.idempotency_key
        (tenant_id, outlet_id, scope, idem_key, request_digest, result_id, created_at)
    SELECT c.tenant_id, c.outlet_id,
           c.payload ->> 'scope',
           c.payload ->> 'idem_key',
           decode(c.payload ->> 'request_digest', 'hex'),
           NULLIF(c.payload ->> 'result_id', '')::uuid,
           c.produced_at
      FROM edge.continuity_record c
     WHERE c.tenant_id = p_tenant_id AND c.outlet_id = p_outlet_id
       AND c.record_kind = 'idempotency'
       AND c.valid_until > now()
        ON CONFLICT (tenant_id, scope, idem_key) DO NOTHING;
    GET DIAGNOSTICS v_keys = ROW_COUNT;

    RETURN QUERY SELECT v_sessions, v_keys;
END;
$$;

COMMENT ON FUNCTION edge.apply_continuity(uuid, uuid) IS
    'FR-EDG-026. The node taking up what the cloud offered. DO NOTHING on conflict in both '
    'halves, and for opposite reasons: a session the node already holds may have been '
    'advanced where the guest is and the cloud''s older copy must not undo that, and an '
    'idempotency key that is already spent is the whole point — the second write is the '
    'retry this exists to absorb.';

GRANT SELECT ON edge.continuity_record TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.offer_continuity(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.apply_continuity(uuid, uuid) TO hospitality_app;
