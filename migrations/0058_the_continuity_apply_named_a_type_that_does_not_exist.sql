-- 0058: the continuity apply named a type that does not exist
--
-- 0057's edge.apply_continuity() casts the stored authentication strength back to its enum
-- and wrote the cast as `::identity.authentication_strength`. THE TYPE IS CALLED
-- identity.auth_strength. The migration applied without complaint, because creating a
-- PL/pgSQL function only checks that its body PARSES — every name in it is resolved when a
-- statement first executes, not when the function is defined.
--
-- THIS IS THE SECOND TIME IN THIS GATE, and the pair is worth stating together because
-- they are the same mistake wearing different clothes. 0054 shipped a regular expression
-- that could never compile; 0057 shipped a cast to a type that has never existed. Both
-- migrations reported success. Both would have failed on their first real call — 0054's at
-- a manager's screen, 0057's at a guest's phone during the exact outage the function
-- exists to survive.
--
-- WHAT ACTUALLY CATCHES THIS CLASS. Not review, which read past both. Not application,
-- which is the thing that gives false confidence. Only CALLING the function does, which is
-- what turned both of these up within a minute of being written. The M5b suite calls every
-- function this gate adds, and that is the control rather than either of these repairs.
--
-- Nothing else changes. The ON CONFLICT targets were checked at the same time and are
-- correct: identity.session carries a UNIQUE (tenant_id, id) beside its primary key, and
-- service.idempotency_key's primary key is (tenant_id, scope, idem_key).

CREATE OR REPLACE FUNCTION edge.apply_continuity(p_tenant_id uuid, p_outlet_id uuid)
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
           (c.payload ->> 'established_with')::identity.auth_strength,
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
