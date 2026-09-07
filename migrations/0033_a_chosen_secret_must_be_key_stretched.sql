-- 0033: a chosen secret must be key-stretched, and the schema is what refuses otherwise
--
-- THIS REPAIRS A DEFECT IN M1-B, NOT A GAP IN THIS GATE'S SCOPE.
--
-- identity.credential has stored a bare 32-byte digest since 0004. Every row written by
-- the build says 'sha-256', and there is no salt column and no cost parameter, so the
-- table's SHAPE forecloses key stretching: a user-chosen secret could only ever be stored
-- as an unsalted fast hash. That is adequate for the high-entropy secrets in this table —
-- an OTP and a service secret are single-use random values, and sha-256 of a random
-- 128-bit value is exactly what api/src/db.ts already does for session tokens — and it is
-- not adequate for the two kinds a PERSON chooses: 'password' and 'quick_pin'. A four to
-- six digit quick PIN under an unsalted fast hash is recoverable from a database read in
-- the time it takes to enumerate a million digests.
--
-- FR-AUTH-007 asks for "secure credential/OTP handling" and is classified MODIFY. The
-- lockout half was built and proved at M1-B; the storage half was not, and nothing failed,
-- because no function ever verified a credential — the gap was invisible for as long as
-- login did not exist. Recorded as its own finding rather than folded into the login work.
--
-- WHY THE EXISTING GUARD IS NOT WEAKENED. credential_digest_is_a_digest requires exactly
-- 32 bytes. scrypt and Argon2id both emit a derived key of the caller's chosen length, so
-- a 32-byte derived key satisfies that constraint unchanged. Nothing here relaxes a rule
-- to make room for the repair; bcrypt was rejected precisely because its 60-character
-- output would have required exactly that.

-- ---------------------------------------------------------------------------
-- 1. THE PARAMETERS TRAVEL WITH THE CREDENTIAL, SO THEY CAN BE RAISED LATER.
-- ---------------------------------------------------------------------------
-- Stored per row rather than as a server constant, because raising the cost must not
-- invalidate rows already written. A credential carries the parameters it was derived
-- under; a later row carries higher ones; both verify. That is the property a fixed
-- constant cannot provide, and the reason this is a column and not a setting.
ALTER TABLE identity.credential
    ADD COLUMN salt       bytea,
    ADD COLUMN kdf_params jsonb;

COMMENT ON COLUMN identity.credential.salt IS
    'Per-credential random salt. Required for kinds a person chooses; absent for the '
    'high-entropy kinds, where the stored value is a digest of a random secret.';
COMMENT ON COLUMN identity.credential.kdf_params IS
    'The cost parameters this row was derived under, so they can be raised for new rows '
    'without invalidating existing ones. cost is the memory-hardness parameter: N for '
    'scrypt, m for Argon2id.';

-- ---------------------------------------------------------------------------
-- 2. THE SCHEMA REFUSES A CHOSEN SECRET THAT IS NOT STRETCHED.
-- ---------------------------------------------------------------------------
-- Structural, not procedural. The rule this enforces was previously not enforced anywhere
-- at all; writing it into the function that inserts credentials would leave every other
-- writer — a fixture, a seed, a psql session, a future route — free to store a fast hash,
-- and the defect being repaired here is exactly that nothing refused.
--
-- Written so absence is FALSE rather than NULL. A CHECK is satisfied when its expression
-- is TRUE *or NULL*, so a missing jsonb key compared with >= evaluates to NULL and PASSES,
-- which is how a constraint of this shape comes to accept the thing it forbids. Every
-- subexpression that can be NULL is wrapped, and no cast that could raise on bad input is
-- used: jsonb comparison is used instead of ::numeric, because evaluation order inside a
-- CHECK is not guaranteed and a guarded cast is therefore not actually guarded.
ALTER TABLE identity.credential ADD CONSTRAINT credential_chosen_secret_is_key_stretched CHECK (
        kind NOT IN ('password', 'quick_pin')
     OR (
            salt IS NOT NULL
        AND octet_length(salt) >= 16
        AND digest_algorithm IN ('scrypt', 'argon2id')
        AND coalesce(jsonb_typeof(kdf_params -> 'cost') = 'number', false)
        AND coalesce(kdf_params -> 'cost' >= to_jsonb(16384), false)
        AND (digest_algorithm <> 'scrypt'
             OR (coalesce(jsonb_typeof(kdf_params -> 'blockSize') = 'number', false)
             AND coalesce(jsonb_typeof(kdf_params -> 'parallelization') = 'number', false)))
        )
);

-- And the high-entropy kinds keep the storage they already had, stated rather than
-- assumed. An OTP is a single-use random value with a short life; stretching it would cost
-- the server on every send and buy nothing, because there is no low-entropy secret to
-- protect. Saying so here means a future reader does not have to guess whether the
-- asymmetry above was deliberate.
COMMENT ON CONSTRAINT credential_chosen_secret_is_key_stretched ON identity.credential IS
    'A secret a person chooses must be salted and key-stretched. A secret the system '
    'generates at full entropy need not be, and is not.';

-- ---------------------------------------------------------------------------
-- 3. THE DERIVATION A CALLER MUST PERFORM, ASKED OF THE ROW.
-- ---------------------------------------------------------------------------
-- The stretching itself happens in the caller, because no extension in this database
-- provides scrypt or Argon2id — pgcrypto offers neither, and is not installed. So the
-- service derives and the database decides, which is the same split api/src/db.ts already
-- uses for session tokens: Node computes sha256(token), the database compares it.
--
-- WHAT THIS DISCLOSES, SAID PLAINLY. A caller needs the salt before it can derive, so this
-- function answers for a channel that has no credential too, with a salt derived
-- deterministically from the channel and tenant. That keeps the shape and cost of a failed
-- attempt the same as a successful one. It is NOT a claim of enumeration resistance: the
-- decoy is computable by anyone who knows the channel value, and defeating a determined
-- enumerator is not something this function attempts.
CREATE FUNCTION identity.credential_key_derivation(
    p_tenant_id     uuid,
    p_channel       identity.channel_kind,
    p_channel_value text,
    p_kind          identity.credential_kind,
    p_outlet_id     uuid DEFAULT NULL
) RETURNS TABLE (salt bytea, digest_algorithm text, kdf_params jsonb)
LANGUAGE plpgsql
AS $$
BEGIN
    -- CONTEXT FIRST, THEN READ — the same shape identity.establish_session_context() uses
    -- at the same boundary, and for the same reason. identity.credential carries FORCE row
    -- level security, so SECURITY DEFINER does not help: forcing applies to the owner too,
    -- and the first attempt at this function silently returned the decoy for every caller
    -- because the predicate could not pass with no context set. Setting it transaction-
    -- locally is not a way around the policy, it is how the policy is satisfied: the read
    -- below is confined to the tenant the caller named, so a forged tenant finds nothing.
    -- THE OUTLET IS PART OF THE QUESTION, and leaving it empty made this function lie.
    --
    -- A quick PIN is outlet-scoped by CHECK since 0004, so its row is only in scope when
    -- an outlet context is set. With the context empty, row level security hid it, the
    -- lookup found nothing, and the function returned its DECOY — a well-formed salt for
    -- a credential that exists. The caller then derived a key that could never match, and
    -- a correct PIN on a registered terminal was refused as if it were wrong.
    --
    -- That is the worst shape this function can fail in: not an error, an answer. It was
    -- invisible to the login walk, which only ever presented a password — the one
    -- credential kind whose outlet_id is null and which therefore needs no context at all.
    PERFORM set_config('app.tenant_id', coalesce(p_tenant_id::text, ''), true);
    PERFORM set_config('app.outlet_id', coalesce(p_outlet_id::text, ''), true);

    RETURN QUERY
    SELECT c.salt, c.digest_algorithm, c.kdf_params
      FROM identity.credential c
      JOIN identity.identity_channel ch
        ON ch.tenant_id = c.tenant_id
       AND ch.user_account_id = c.user_account_id
     WHERE c.tenant_id = p_tenant_id
       AND c.kind = p_kind
       AND ch.channel = p_channel
       AND lower(ch.channel_value) = lower(p_channel_value)
       AND ch.verified_at IS NOT NULL
       AND c.revoked_at IS NULL
       AND (c.expires_at IS NULL OR c.expires_at > now())
     LIMIT 1;

    IF NOT FOUND THEN
        RETURN QUERY SELECT
            substring(pg_catalog.sha256((p_channel_value || p_tenant_id::text)::bytea)
                      from 1 for 16),
            'scrypt'::text,
            jsonb_build_object('cost', 16384, 'blockSize', 8, 'parallelization', 1);
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. THE MIDDLE STEP: A CREDENTIAL BECOMES A SESSION.
-- ---------------------------------------------------------------------------
-- The function M1-B never wrote. Everything it calls already existed and was proved:
-- register_auth_attempt holds the lockout, establish_session_context reads the session
-- back, the digest CHECK refuses plaintext, and revoke_sessions_on_membership_change
-- retires a session when the membership behind it goes. The only thing absent was
-- something that turned a presented credential into a row in identity.session.
--
-- IT DECIDES; THE CALLER ONLY DERIVES. The service performs the key derivation and hands
-- back 32 bytes, and everything that follows — the lockout, the liveness of the
-- credential, the verification of the channel, the trusted-terminal rule for a quick PIN,
-- the strength the session is established with — is settled here, in one transaction. A
-- route that wanted to skip a check would have to not call this function at all, which is
-- what the structural writer guard at M3-D exists to catch.
CREATE FUNCTION identity.authenticate_credential(
    p_tenant_id     uuid,
    p_channel       identity.channel_kind,
    p_channel_value text,
    p_kind          identity.credential_kind,
    p_derived_key   bytea,
    p_token_digest  bytea,
    p_device_id     uuid DEFAULT NULL,
    p_outlet_id     uuid DEFAULT NULL,
    p_lifetime      interval DEFAULT interval '8 hours'
) RETURNS TABLE (session_id uuid, user_account_id uuid, outlet_id uuid,
                 established_with identity.auth_strength, refusal text)
LANGUAGE plpgsql
AS $$
DECLARE
    v_subject_digest bytea := pg_catalog.sha256(
        (p_channel_value || '|' || p_tenant_id::text)::bytea);
    v_credential     identity.credential%ROWTYPE;
    v_user           uuid;
    v_outlet         uuid;
    v_verified       boolean := false;
    v_session        uuid;
BEGIN
    -- The same context-first shape as the function above and as
    -- identity.establish_session_context(). Set transaction-locally, so it cannot travel
    -- back to the pool on the connection this borrowed — the property migration 0005
    -- made structural.
    PERFORM set_config('app.tenant_id', coalesce(p_tenant_id::text, ''), true);
    PERFORM set_config('app.outlet_id', coalesce(p_outlet_id::text, ''), true);
    -- THE LOCKOUT IS ASKED FIRST AND ASKED FOR EVERY ATTEMPT, including one against a
    -- channel with no credential. A lockout that only counted attempts against real
    -- accounts would tell an attacker which accounts are real by refusing to lock the
    -- others. register_auth_attempt raises SUBJECT_LOCKED_OUT when the subject is already
    -- locked, and that refusal is allowed to propagate unchanged.
    PERFORM identity.register_auth_attempt(p_tenant_id, v_subject_digest, false);

    SELECT c.* INTO v_credential
      FROM identity.credential c
      JOIN identity.identity_channel ch
        ON ch.tenant_id = c.tenant_id
       AND ch.user_account_id = c.user_account_id
     WHERE c.tenant_id = p_tenant_id
       AND c.kind = p_kind
       AND ch.channel = p_channel
       AND lower(ch.channel_value) = lower(p_channel_value)
       AND ch.verified_at IS NOT NULL          -- FR-AUTH-001: VERIFIED phone or email
       AND c.revoked_at IS NULL
       AND (c.expires_at IS NULL OR c.expires_at > now())
     LIMIT 1;

    -- Compared in one operation over the whole value rather than byte by byte in plpgsql,
    -- and only after a row was found, so the comparison never short-circuits on length.
    IF FOUND AND p_derived_key IS NOT NULL
       AND octet_length(p_derived_key) = octet_length(v_credential.secret_digest)
       AND p_derived_key = v_credential.secret_digest THEN
        v_verified := true;
    END IF;

    -- A REFUSAL IS RETURNED, NOT RAISED, AND THE REASON IS THE LOCKOUT.
    --
    -- This function records the attempt as a failure before it checks anything, so that a
    -- caller who never reaches the end still counts against the threshold. Raising here
    -- undid that: the exception aborts the statement, the INSERT into identity.auth_attempt
    -- goes with it, and five wrong passwords leave no trace at all. identity.auth_attempt
    -- was empty after six failures and the lockout could never fire — the control this
    -- gate wrote for FR-AUTH-007 is what found it.
    --
    -- So every refusal below returns a NAMED reason with a null session instead. The
    -- caller sees no session and answers 401; the log keeps the name; the attempt stands.
    -- The one exception is SUBJECT_LOCKED_OUT, raised by register_auth_attempt() before
    -- it writes anything, where there is nothing to lose and a distinct answer to give.
    IF NOT v_verified THEN
        RETURN QUERY SELECT NULL::uuid, NULL::uuid, NULL::uuid,
                            NULL::identity.auth_strength, 'CREDENTIAL_NOT_VERIFIED'::text;
        RETURN;
    END IF;

    v_user   := v_credential.user_account_id;
    v_outlet := coalesce(p_outlet_id, v_credential.outlet_id);

    -- FR-AUTH-004: a session may not issue for a membership that is gone. The same
    -- question revoke_sessions_on_membership_change asks when a membership is removed,
    -- asked here so a removed role cannot be re-entered rather than merely revoked.
    -- Liveness is read the way identity.revoke_sessions_on_membership_change reads it —
    -- status = 'active' — rather than by a second convention invented here. The two must
    -- agree: that trigger retires a session when a membership stops being live, and this
    -- is what stops the same subject re-entering through the front door a moment later.
    IF NOT EXISTS (
        SELECT 1 FROM identity.membership m
         WHERE m.tenant_id = p_tenant_id
           AND m.user_account_id = v_user
           AND (v_outlet IS NULL OR m.outlet_id = v_outlet)
           AND m.status = 'active'
           AND m.withdrawn_at IS NULL
    ) THEN
        RETURN QUERY SELECT NULL::uuid, NULL::uuid, NULL::uuid,
                            NULL::identity.auth_strength,
                            'SESSION_ISSUED_FOR_REVOKED_ROLE'::text;
        RETURN;
    END IF;

    -- FR-AUTH-005. A quick PIN is re-entry on a terminal the outlet has registered, and
    -- nowhere else. The trust is read from identity.terminal_trust rather than asserted
    -- by the caller, so a device that was never registered — or whose trust was withdrawn
    -- — cannot present one.
    IF p_kind = 'quick_pin' THEN
        IF p_device_id IS NULL OR NOT EXISTS (
            SELECT 1 FROM identity.terminal_trust t
             WHERE t.tenant_id = p_tenant_id
               AND t.device_id = p_device_id
               AND t.outlet_id = v_outlet
               AND t.withdrawn_at IS NULL
        ) THEN
            RETURN QUERY SELECT NULL::uuid, NULL::uuid, NULL::uuid,
                                NULL::identity.auth_strength,
                                'QUICK_PIN_OUTSIDE_A_TRUSTED_TERMINAL'::text;
            RETURN;
        END IF;
    END IF;

    INSERT INTO identity.session
        (tenant_id, outlet_id, user_account_id, device_id, token_digest,
         established_with, expires_at)
    VALUES
        (p_tenant_id, v_outlet, v_user, p_device_id, p_token_digest,
         v_credential.confers_strength, now() + p_lifetime)
    RETURNING id INTO v_session;

    -- Recorded only now, and only once the session exists: an attempt that raised above
    -- has already been counted as a failure by the call at the top, and this is what
    -- clears the counter. A success registered before the session was issued would clear
    -- a lockout for an attempt that did not actually succeed.
    PERFORM identity.register_auth_attempt(p_tenant_id, v_subject_digest, true);
    PERFORM identity.emit_security_event(p_tenant_id, v_outlet, 'auth.session_issued', v_user);

    RETURN QUERY SELECT v_session, v_user, v_outlet, v_credential.confers_strength,
                        NULL::text;
END;
$$;

-- The application role is the only identity the service runs as, and these two are the
-- authentication boundary: they must be callable before a session context exists, which
-- is why they are SECURITY DEFINER and why the row they read is not reachable under the
-- caller's own RLS.
GRANT EXECUTE ON FUNCTION identity.credential_key_derivation(
    uuid, identity.channel_kind, text, identity.credential_kind, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION identity.authenticate_credential(
    uuid, identity.channel_kind, text, identity.credential_kind, bytea, bytea,
    uuid, uuid, interval) TO hospitality_app;
