-- 0059: a revoked session is refused at the node, not merely left out at the cloud
--
-- 0057 protects against handing a node a session the cloud has stopped honouring with a
-- WHERE clause in edge.offer_continuity(): revoked_at IS NULL AND expires_at > now().
-- Writing M5b's negative control for it is what showed that this is not enough, and the
-- registry is what forced the question — NC-M5B-005 names a signature,
-- CONTINUITY_OFFERED_A_REVOKED_SESSION, and there was nothing in the database that could
-- ever raise it.
--
-- A WHERE CLAUSE IS A FILTER AND NOT A REFUSAL, and the difference matters exactly here.
-- A filter protects the ONE path that goes through it. edge.continuity_record is a table:
-- anything holding the privilege to write it can put a row there, and the node applies
-- whatever it finds. So the guarantee "a node never honours a token the cloud has revoked"
-- rested on nobody ever writing that table another way — including a future cloud-to-node
-- transport, which is precisely the thing this record exists to travel on.
--
-- WORSE, A FILTER FAILS SILENTLY AND IN THE WRONG DIRECTION. If the clause were ever wrong
-- — a NULL comparison, an inverted test, a timezone — the symptom is a node quietly
-- honouring a session somebody signed out of, and there is no error anywhere. That is the
-- shape of defect this repository keeps finding, and the answer each time has been to make
-- the wrong state impossible to write rather than merely unlikely to be written.
--
-- So the rule moves to where the row lands. The filter stays: refusing at the boundary and
-- also not offering it is two independent things going wrong before a guest is affected.

-- ---------------------------------------------------------------------------
-- 1. THE ROW ITSELF CANNOT SAY A SESSION IS DEAD AND STILL BE WRITTEN
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.refuse_dead_continuity_session() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.record_kind <> 'session' THEN
        RETURN NEW;
    END IF;

    IF (NEW.payload ? 'revoked_at') AND (NEW.payload ->> 'revoked_at') IS NOT NULL THEN
        RAISE EXCEPTION
            'CONTINUITY_OFFERED_A_REVOKED_SESSION: session % carries a revocation and is '
            'being offered to a node anyway. A node that honoured it would be answering '
            'for a guest the cloud has already signed out, which is two writers '
            'disagreeing about who is at the table',
            NEW.record_key
            USING ERRCODE = 'HS409';
    END IF;

    -- AND IT MUST NOT ALREADY BE OVER. valid_until is checked against produced_at by a
    -- CHECK, which stops a row that was born expired; this stops a row whose session
    -- expiry disagrees with the validity the offer claimed for it.
    IF (NEW.payload ->> 'expires_at')::timestamptz <= now() THEN
        RAISE EXCEPTION
            'CONTINUITY_OFFERED_A_REVOKED_SESSION: session % expired at % and is being '
            'offered to a node as live',
            NEW.record_key, NEW.payload ->> 'expires_at'
            USING ERRCODE = 'HS409';
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION edge.refuse_dead_continuity_session() IS
    'FR-EDG-026, NC-M5B-005. edge.offer_continuity() already filters revoked and expired '
    'sessions out. This refuses them at the row, because a filter protects one path and a '
    'table has as many paths as there are writers — including the cloud-to-node transport '
    'these records exist to travel on. A filter that was wrong would fail silently, with a '
    'node honouring a session somebody signed out of and no error anywhere.';

CREATE TRIGGER continuity_record_session_is_live
    BEFORE INSERT OR UPDATE ON edge.continuity_record
    FOR EACH ROW EXECUTE FUNCTION edge.refuse_dead_continuity_session();

-- ---------------------------------------------------------------------------
-- 2. AND THE OFFER CARRIES THE REVOCATION SO THE TRIGGER CAN SEE IT
-- ---------------------------------------------------------------------------
--
-- 0057's payload omitted revoked_at, because the filter meant it could never be set. With
-- the rule at the row, the row needs the fact: a payload that cannot express a revocation
-- is one the trigger can never refuse, which would make it decoration.

CREATE OR REPLACE FUNCTION edge.offer_continuity(p_tenant_id uuid, p_outlet_id uuid)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'identity', 'service', 'public'
AS $$
DECLARE
    v_written integer := 0;
    v_n       integer;
BEGIN
    INSERT INTO edge.continuity_record
        (tenant_id, outlet_id, record_kind, record_key, payload, valid_until)
    SELECT s.tenant_id, s.outlet_id, 'session', s.id::text,
           jsonb_build_object(
               'session_id',      s.id,
               'token_digest',    encode(s.token_digest, 'hex'),
               'established_with', s.established_with,
               'user_account_id', s.user_account_id,
               'issued_at',       s.issued_at,
               'expires_at',      s.expires_at,
               -- Always present, always null on a live session. Carried so the trigger has
               -- something to test rather than something to assume.
               'revoked_at',      s.revoked_at),
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

-- ---------------------------------------------------------------------------
-- 3. AND IT IS PROVED HERE, BECAUSE APPLYING IS NOT EXERCISING
-- ---------------------------------------------------------------------------
--
-- Twice in this gate a migration applied cleanly and defined something that could never
-- run. This one refuses to be the third: the trigger fires on a planted row before the
-- migration commits, and the migration fails if it does not.
DO $$
DECLARE
    v_tenant uuid;
    v_outlet uuid;
    v_refused boolean := false;
BEGIN
    -- Any outlet will do; this is about the trigger, not about a particular floor. If the
    -- database has no outlet at all there is nothing to prove and nothing to break.
    SELECT tenant_id, id INTO v_tenant, v_outlet
      FROM org.org_node WHERE kind = 'outlet' ORDER BY id LIMIT 1;
    IF v_tenant IS NULL THEN RETURN; END IF;

    BEGIN
        INSERT INTO edge.continuity_record
            (tenant_id, outlet_id, record_kind, record_key, payload, valid_until)
        VALUES (v_tenant, v_outlet, 'session', 'migration-0059-probe',
                jsonb_build_object('session_id', gen_random_uuid(),
                                   'expires_at', now() + interval '1 hour',
                                   'revoked_at', now()),
                now() + interval '1 hour');
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM LIKE 'CONTINUITY_OFFERED_A_REVOKED_SESSION%' THEN
            v_refused := true;
        ELSE
            RAISE;
        END IF;
    END;

    IF NOT v_refused THEN
        RAISE EXCEPTION
            'CONTINUITY_TRIGGER_DOES_NOT_FIRE: a revoked session was written to '
            'edge.continuity_record without complaint, so the rule added by this '
            'migration does not exist in practice'
            USING ERRCODE = 'HS500';
    END IF;
END;
$$;
