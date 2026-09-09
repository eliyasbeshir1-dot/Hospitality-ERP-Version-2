-- 0038: a successful login is not a failed one
--
-- THE DEFECT, AND IT LOCKED PEOPLE OUT OF THEIR OWN ACCOUNTS.
--
-- Four consecutive CORRECT manager logins returned 200. The fifth and sixth returned 429.
--
-- identity.authenticate_credential() records the attempt as a FAILURE before it verifies
-- anything, and that is correct and load-bearing: writing the row before verification is
-- what stops an attacker distinguishing "no such user" from "wrong password" by whether a
-- row appears. A lockout that only counted attempts against real accounts would tell an
-- attacker which accounts are real by refusing to lock the others.
--
-- What was missing is the other half. On success the function calls
-- register_auth_attempt(…, true), and that DELETES THE LOCKOUT ROW — but nothing removes
-- the speculative FAILURE ROW. The lockout counter is not the lockout row; it is
--
--     count(*) FROM identity.auth_attempt WHERE NOT succeeded AND attempted_at > now() - window
--
-- so every successful login left a permanent failure inside the window. Four successes,
-- four failures; the fifth login writes its speculative failure, the count reaches the
-- threshold of five, and the lock trips on a person who has typed their password
-- correctly every single time.
--
-- The comment above that call stated the property that was absent, in those words:
-- "this is what clears the counter." It clears the LOCKOUT. It does not clear the
-- COUNTER. The comment was the specification and nothing ever checked it.
--
-- THE WINDOW IS FIFTEEN MINUTES, NOT FOREVER. Proved by ageing the rows past it and
-- watching the counter reset. So this is not "locked out after a week of shifts": it is
-- five correct sign-ins inside fifteen minutes — a shift change, a manager moving between
-- the till and the floor screen, anyone who signs out and back in a few times. That is
-- more likely to be met than the cumulative version, because it needs no elapsed time.
--
-- THE REPAIR. The speculative insert stays exactly where it is. What is added is its
-- resolution: the attempt's OWN row is deleted when that attempt resolves as a success.
--
--   * it exists during verification, so anti-enumeration holds unchanged;
--   * it disappears when the attempt turns out to have been a success, so the count means
--     what it says;
--   * a genuine failure never reaches the delete, so failures accumulate exactly as
--     before and the lockout still fires at five of them.
--
-- ONE ROW, BY ID. Not clear_lockout(), not a DELETE over the subject, not a counter
-- reset — those would erase real failures that happened to precede a success, and an
-- attacker who guesses right on the sixth try should not thereby erase the five wrong
-- guesses before it.

-- ---------------------------------------------------------------------------
-- 1. THE ATTEMPT CAN NOW BE NAMED
-- ---------------------------------------------------------------------------
--
-- register_auth_attempt() returns a boolean and tests/m1b calls it with that signature,
-- so it keeps it. The identity of the row it wrote is what the caller needs, and that is
-- a second function rather than a changed one: the primitive keeps its contract, and the
-- caller that must undo its own speculative write gets the handle to do it.

CREATE FUNCTION identity.register_auth_attempt_id(
    p_tenant_id      uuid,
    p_subject_digest bytea,
    p_succeeded      boolean,
    p_threshold      integer DEFAULT 5,
    p_window         interval DEFAULT interval '15 minutes',
    p_lock_for       interval DEFAULT interval '15 minutes'
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_locked_until timestamptz;
    v_failures     integer;
    v_attempt      uuid;
BEGIN
    SELECT locked_until INTO v_locked_until FROM identity.auth_lockout
    WHERE tenant_id = p_tenant_id AND subject_digest = p_subject_digest;

    IF v_locked_until IS NOT NULL AND v_locked_until > now() THEN
        RAISE EXCEPTION 'SUBJECT_LOCKED_OUT: further attempts are refused until the lock expires'
            USING ERRCODE = 'HS429';
    END IF;

    INSERT INTO identity.auth_attempt (tenant_id, subject_digest, succeeded)
    VALUES (p_tenant_id, p_subject_digest, p_succeeded)
    RETURNING id INTO v_attempt;

    IF p_succeeded THEN
        DELETE FROM identity.auth_lockout
        WHERE tenant_id = p_tenant_id AND subject_digest = p_subject_digest;
        RETURN v_attempt;
    END IF;

    SELECT count(*) INTO v_failures FROM identity.auth_attempt
    WHERE tenant_id = p_tenant_id AND subject_digest = p_subject_digest
      AND NOT succeeded AND attempted_at > now() - p_window;

    IF v_failures >= p_threshold THEN
        INSERT INTO identity.auth_lockout (tenant_id, subject_digest, locked_until, failure_count)
        VALUES (p_tenant_id, p_subject_digest, now() + p_lock_for, v_failures)
        ON CONFLICT (tenant_id, subject_digest) DO UPDATE
            SET locked_at = now(), locked_until = now() + p_lock_for,
                failure_count = EXCLUDED.failure_count;
        PERFORM identity.emit_security_event('auth.locked_out', NULL);
    END IF;

    RETURN v_attempt;
END;
$$;

COMMENT ON FUNCTION identity.register_auth_attempt_id(uuid, bytea, boolean, integer, interval, interval) IS
    'FR-AUTH-007, returning the identity of the attempt it recorded. The boolean-returning '
    'form below is the same thing for callers that do not need to name the row; a caller '
    'that writes a SPECULATIVE attempt before verifying needs to name it, so that it can '
    'delete that one row — and only that one — when the attempt resolves as a success.';

-- The original contract, unchanged for every existing caller, now expressed once.
CREATE OR REPLACE FUNCTION identity.register_auth_attempt(
    p_tenant_id      uuid,
    p_subject_digest bytea,
    p_succeeded      boolean,
    p_threshold      integer DEFAULT 5,
    p_window         interval DEFAULT interval '15 minutes',
    p_lock_for       interval DEFAULT interval '15 minutes'
) RETURNS boolean
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM identity.register_auth_attempt_id(
        p_tenant_id, p_subject_digest, p_succeeded, p_threshold, p_window, p_lock_for);
    RETURN p_succeeded;
END;
$$;

-- ---------------------------------------------------------------------------
-- 2. THE SPECULATIVE ATTEMPT IS RESOLVED
-- ---------------------------------------------------------------------------

CREATE FUNCTION identity.resolve_attempt_as_success(
    p_tenant_id      uuid,
    p_attempt_id     uuid,
    p_subject_digest bytea,
    p_threshold      integer  DEFAULT 5,
    p_window         interval DEFAULT interval '15 minutes'
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_failures integer;
BEGIN
    -- ONE. THE SPECULATIVE ROW, BY ID, AND ONLY WHILE IT IS STILL A FAILURE.
    -- The `NOT succeeded` test is not decoration: it means this can only ever remove a
    -- row written speculatively and never a recorded success, whatever a caller passes.
    DELETE FROM identity.auth_attempt
     WHERE tenant_id = p_tenant_id AND id = p_attempt_id AND NOT succeeded;

    -- TWO. THE LOCK THAT ROW MAY HAVE CAUSED ON ITS WAY IN.
    --
    -- Found by testing four wrong passwords followed by the right one. The speculative
    -- insert was the fifth failure in the window, so it tripped the lock itself — and the
    -- success then raised SUBJECT_LOCKED_OUT against a lock created by an attempt that
    -- had just proved the credential. That behaviour predates this migration; what is new
    -- is that there is now a place where it can be resolved correctly.
    --
    -- Reaching this function PROVES no lock existed when the attempt began: a pre-existing
    -- lock raises at the top of register_auth_attempt_id() and authentication never gets
    -- here. So any lock present now was created by this attempt's own speculative row, and
    -- lifting it is not forgiveness — it is undoing a count that turned out to be wrong.
    --
    -- Guarded by re-reading the count anyway, rather than deleting unconditionally: if
    -- genuine failures in the window still meet the threshold the lock stands, so a
    -- correct password does not wipe out five real wrong guesses that preceded it.
    SELECT count(*) INTO v_failures FROM identity.auth_attempt
     WHERE tenant_id = p_tenant_id AND subject_digest = p_subject_digest
       AND NOT succeeded AND attempted_at > now() - p_window;

    IF v_failures < p_threshold THEN
        DELETE FROM identity.auth_lockout
         WHERE tenant_id = p_tenant_id AND subject_digest = p_subject_digest;
    END IF;

    -- THREE. THE SUCCESS ITSELF.
    --
    -- Inserted here rather than through register_auth_attempt(), because that function's
    -- first act is to refuse when a lock is present — which is right for an attempt being
    -- EVALUATED and wrong for one already RESOLVED. Recording what happened must not be
    -- able to fail on a lock this same call has just lifted.
    INSERT INTO identity.auth_attempt (tenant_id, subject_digest, succeeded)
    VALUES (p_tenant_id, p_subject_digest, true);
END;
$$;

COMMENT ON FUNCTION identity.resolve_attempt_as_success(uuid, uuid, bytea, integer, interval) IS
    'Resolves an authentication that wrote a speculative failure before verifying and '
    'then succeeded (FR-AUTH-007). Removes that one row by id while it is still marked '
    'failed; lifts a lockout only when the remaining genuine failures in the window no '
    'longer meet the threshold — so guessing right on the sixth try does not erase the '
    'five wrong guesses before it; and records the success. Recording does not go through '
    'register_auth_attempt(), whose first act is to refuse on a lock: that is correct for '
    'an attempt being evaluated and wrong for one already resolved.';

-- ---------------------------------------------------------------------------
-- 3. AUTHENTICATION USES IT
-- ---------------------------------------------------------------------------
--
-- Replaced whole because a CREATE OR REPLACE must carry the entire body. Everything below
-- is 0033's function with three lines changed: the speculative call now names its row,
-- and the success path forgets that row before it records the success.

CREATE OR REPLACE FUNCTION identity.authenticate_credential(
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
    v_attempt        uuid;
BEGIN
    PERFORM set_config('app.tenant_id', coalesce(p_tenant_id::text, ''), true);
    PERFORM set_config('app.outlet_id', coalesce(p_outlet_id::text, ''), true);

    -- THE LOCKOUT IS ASKED FIRST AND ASKED FOR EVERY ATTEMPT, including one against a
    -- channel with no credential. A lockout that only counted attempts against real
    -- accounts would tell an attacker which accounts are real by refusing to lock the
    -- others. register_auth_attempt raises SUBJECT_LOCKED_OUT when the subject is already
    -- locked, and that refusal is allowed to propagate unchanged.
    --
    -- The row's identity is kept. It is written before anything is verified, and if this
    -- attempt turns out to be a SUCCESS it must not be left behind counting against the
    -- person who just proved who they are. Nothing else about the speculative write
    -- changes: it exists for the whole of verification, and it stays for every path that
    -- does not reach the end.
    v_attempt := identity.register_auth_attempt_id(p_tenant_id, v_subject_digest, false);

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
    -- was empty after six failures and the lockout could never fire — the control OP-A
    -- wrote for FR-AUTH-007 is what found it.
    --
    -- So every refusal below returns a NAMED reason with a null session instead. The
    -- caller sees no session and answers 401; the log keeps the name; the attempt stands.
    IF NOT v_verified THEN
        RETURN QUERY SELECT NULL::uuid, NULL::uuid, NULL::uuid,
                            NULL::identity.auth_strength, 'CREDENTIAL_NOT_VERIFIED'::text;
        RETURN;
    END IF;

    v_user   := v_credential.user_account_id;
    v_outlet := coalesce(p_outlet_id, v_credential.outlet_id);

    -- FR-AUTH-004: a session may not issue for a membership that is gone.
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

    -- FR-AUTH-005. A quick PIN is re-entry on a terminal the outlet has registered.
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

    -- THE ATTEMPT RESOLVES, AND ITS SPECULATIVE FAILURE GOES WITH IT.
    --
    -- Only now, and only once the session exists: resolving before the session was issued
    -- would forgive an attempt that had not actually succeeded. One call, so the removal
    -- of the speculative row, the lock it may have caused and the recording of the
    -- success are one indivisible act — and if anything below were ever to fail, the
    -- transaction takes all three back and the attempt is left counted, which is the safe
    -- direction.
    PERFORM identity.resolve_attempt_as_success(p_tenant_id, v_attempt, v_subject_digest);
    PERFORM identity.emit_security_event(p_tenant_id, v_outlet, 'auth.session_issued', v_user);

    RETURN QUERY SELECT v_session, v_user, v_outlet, v_credential.confers_strength,
                        NULL::text;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. PRIVILEGE
-- ---------------------------------------------------------------------------

GRANT EXECUTE ON FUNCTION identity.register_auth_attempt_id(uuid, bytea, boolean, integer, interval, interval)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION identity.resolve_attempt_as_success(uuid, uuid, bytea, integer, interval)
    TO hospitality_app;
