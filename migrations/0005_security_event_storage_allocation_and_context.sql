-- 0005_security_event_storage_allocation_and_context.sql
--
-- Gate:         M1, repair of findings raised by executing independent review
-- Requirements: FR-AUTH-008, FR-AUTH-010, FR-DAT-006, FR-SEC-001
--
-- Four repairs, each to a function that already exists. A new migration rather than an
-- edit, because 0002 and 0003 are applied and checksum-locked; forward-only means the
-- amendment is a new file with its reasoning attached. The superseded comments in 0002
-- and 0003 are left unedited in those files and corrected here with COMMENT ON.
--
--   F5  identity.emit_security_event stored nothing, so FR-AUTH-010 was not met
--   F7  identity.establish_session_context set session-level context that outlived the
--       transaction and returned to the pool with the connection
--   F4  money.allocate lost minor units for negative totals
--   F11 money.rounding_mode did not state which way a tie breaks
--   F6  money.assert_currency_paired is vacuous at M1 and did not say so

-- ===========================================================================
-- F5 — security events are stored, not merely announced (FR-AUTH-010)
-- ===========================================================================
-- The emitter only called pg_notify. A NOTIFY is not durable: no listener means no
-- record, and the requirement asks for an audit trail. The audit table has existed since
-- 0003; nothing ever wrote to it, and the M1-C gate inserted its own row and then
-- asserted the row was there — a test supplying its own evidence.
--
-- The canonical writer now takes its scope explicitly. Deriving tenant from session
-- context is right for a caller that has one, but identity.register_auth_attempt runs at
-- the authentication boundary and knows its tenant as an argument, so the explicit form
-- is the primitive and the context-derived form delegates to it.
--
-- No SECURITY DEFINER. The insert happens as the calling role, under the same row level
-- security policy as every other write, so an event can only be recorded inside the scope
-- that produced it.

CREATE FUNCTION identity.emit_security_event(
    p_tenant_id  uuid,
    p_outlet_id  uuid,
    p_event_code text,
    p_subject_id uuid
) RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_id bigint;
BEGIN
    IF p_tenant_id IS NULL THEN
        RAISE EXCEPTION 'SECURITY_EVENT_UNATTRIBUTED: a security event must name the tenant it belongs to'
            USING ERRCODE = 'HS422';
    END IF;

    INSERT INTO audit.security_event (tenant_id, outlet_id, event_code, subject_id, actor_id)
    VALUES (p_tenant_id, p_outlet_id, p_event_code, p_subject_id,
            nullif(current_setting('app.session_id', true), '')::uuid)
    RETURNING id INTO v_id;

    -- The NOTIFY stays. Storage is the record; the announcement is how a listener learns
    -- about it without polling. The payload carries identifiers only — never a
    -- credential, token or code (FR-SEC-007).
    PERFORM pg_notify('identity_security_event',
                      json_build_object('event', p_event_code,
                                        'tenant_id', p_tenant_id,
                                        'subject_id', p_subject_id,
                                        'audit_id', v_id,
                                        'at', now())::text);
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION identity.emit_security_event(uuid, uuid, text, uuid) IS
    'Records a security event in audit.security_event and announces it (FR-AUTH-010). '
    'Writes as the calling role under ordinary row level security, so an event can only '
    'be recorded inside the scope that produced it.';

-- The two-argument form is kept so existing callers do not change shape, but it now
-- persists through the writer above. It fails closed: an event that cannot be attributed
-- to a tenant is a defect, not something to drop quietly.
CREATE OR REPLACE FUNCTION identity.emit_security_event(p_event_code text, p_subject_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    IF app.current_tenant_id() IS NULL THEN
        RAISE EXCEPTION 'SECURITY_EVENT_UNATTRIBUTED: no tenant context to attribute this event to'
            USING ERRCODE = 'HS422';
    END IF;
    PERFORM identity.emit_security_event(app.current_tenant_id(), app.current_outlet_id(),
                                         p_event_code, p_subject_id);
END;
$$;

COMMENT ON FUNCTION identity.emit_security_event(text, uuid) IS
    'Context-derived form of the security event writer. Supersedes the 0002 comment '
    'stating that nothing is persisted here: as of 0005 the event is stored in '
    'audit.security_event (FR-AUTH-010).';

COMMENT ON TABLE audit.security_event IS
    'Append-only security audit (FR-AUTH-010). identity.emit_security_event writes here; '
    'as of 0005 that is the only way rows arrive, so the store reflects what identity '
    'actually emitted rather than what a caller chose to insert. The 0003 comment saying '
    '"M1-B emits them, M1-C stores them" described an intention that no code implemented; '
    'this supersedes it.';

-- The lockout path knows its tenant as an argument and must not depend on ambient
-- context to record that a subject was locked out.
CREATE OR REPLACE FUNCTION identity.revoke_sessions_on_membership_change() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = 'active' THEN
        RETURN NULL;
    END IF;

    UPDATE identity.session s
    SET revoked_at     = now(),
        revoked_reason = 'membership_withdrawn',
        row_version    = s.row_version
    WHERE s.tenant_id       = NEW.tenant_id
      AND s.user_account_id = NEW.user_account_id
      AND s.revoked_at IS NULL
      AND (NEW.outlet_id IS NULL OR s.outlet_id = NEW.outlet_id)
      AND NOT EXISTS (
            SELECT 1 FROM identity.membership m
            WHERE m.tenant_id       = s.tenant_id
              AND m.user_account_id = s.user_account_id
              AND m.status          = 'active'
              AND m.id             <> NEW.id
              AND (m.outlet_id IS NULL OR m.outlet_id = s.outlet_id)
      );

    PERFORM identity.emit_security_event(NEW.tenant_id, NEW.outlet_id,
                                         'membership.withdrawn', NEW.user_account_id);
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION identity.register_auth_attempt(
    p_tenant_id      uuid,
    p_subject_digest bytea,
    p_succeeded      boolean,
    p_threshold      integer  DEFAULT 5,
    p_window         interval DEFAULT interval '15 minutes',
    p_lock_for       interval DEFAULT interval '15 minutes'
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_failures     integer;
    v_locked_until timestamptz;
BEGIN
    SELECT locked_until INTO v_locked_until FROM identity.auth_lockout
    WHERE tenant_id = p_tenant_id AND subject_digest = p_subject_digest;

    IF v_locked_until IS NOT NULL AND v_locked_until > now() THEN
        RAISE EXCEPTION 'SUBJECT_LOCKED_OUT: further attempts are refused until the lock expires'
            USING ERRCODE = 'HS429';
    END IF;

    INSERT INTO identity.auth_attempt (tenant_id, subject_digest, succeeded)
    VALUES (p_tenant_id, p_subject_digest, p_succeeded);

    IF p_succeeded THEN
        DELETE FROM identity.auth_lockout
        WHERE tenant_id = p_tenant_id AND subject_digest = p_subject_digest;
        RETURN true;
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
        -- Explicit tenant: the lockout is recorded even though this runs at the
        -- authentication boundary, where ambient context may not be established yet.
        PERFORM identity.emit_security_event(p_tenant_id, app.current_outlet_id(),
                                             'auth.locked_out', NULL);
    END IF;

    RETURN false;
END;
$$;

-- ===========================================================================
-- F7 — request context is transaction-local (FR-SEC-001)
-- ===========================================================================
-- set_config(..., false) is a plain SET: it outlives COMMIT and travels back to the
-- connection pool, so the next request to borrow that connection would inherit the
-- previous caller's tenant. api/src/db.ts documented SET LOCAL semantics and this
-- function did not provide them. No M1 route exposed the gap; M2 adds customer-facing
-- routes, so it is closed now rather than then.
--
-- The third argument becomes true throughout: the setting reverts when the surrounding
-- transaction ends. A caller that needs context across statements opens a transaction,
-- which is exactly what api/src/db.ts already does.

CREATE OR REPLACE FUNCTION identity.establish_session_context(
    p_tenant_id    uuid,
    p_outlet_id    uuid,
    p_token_digest bytea
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_session    identity.session%ROWTYPE;
    v_has_member boolean;
BEGIN
    PERFORM set_config('app.tenant_id',     coalesce(p_tenant_id::text, ''), true);
    PERFORM set_config('app.outlet_id',     coalesce(p_outlet_id::text, ''), true);
    PERFORM set_config('app.session_id',    '', true);
    PERFORM set_config('app.auth_strength', '', true);

    SELECT * INTO v_session
    FROM identity.session s
    WHERE s.token_digest = p_token_digest
      AND s.revoked_at IS NULL
      AND s.expires_at > now();

    IF NOT FOUND THEN
        PERFORM set_config('app.tenant_id', '', true);
        PERFORM set_config('app.outlet_id', '', true);
        RAISE EXCEPTION 'SESSION_NOT_LIVE: no live session for the presented credential'
            USING ERRCODE = 'HS401';
    END IF;

    -- Re-checked on every use, so withdrawing a membership takes effect at once even
    -- if the eager revocation did not run.
    SELECT EXISTS (
        SELECT 1 FROM identity.membership m
        WHERE m.tenant_id       = v_session.tenant_id
          AND m.user_account_id = v_session.user_account_id
          AND m.status          = 'active'
          AND (m.outlet_id IS NULL OR m.outlet_id = v_session.outlet_id)
    ) INTO v_has_member;

    IF v_session.user_account_id IS NOT NULL AND NOT v_has_member THEN
        PERFORM set_config('app.tenant_id', '', true);
        PERFORM set_config('app.outlet_id', '', true);
        RAISE EXCEPTION 'NO_ACTIVE_MEMBERSHIP: the session subject holds no active membership here'
            USING ERRCODE = 'HS403';
    END IF;

    PERFORM set_config('app.session_id',    v_session.id::text, true);
    PERFORM set_config('app.auth_strength', v_session.established_with::text, true);
    RETURN v_session.id;
END;
$$;

COMMENT ON FUNCTION identity.establish_session_context(uuid, uuid, bytea) IS
    'Authenticates a session token and establishes TRANSACTION-LOCAL tenant and outlet '
    'context (FR-AUTH-008). The context reverts when the transaction ends, so a pooled '
    'connection cannot hand the next caller someone else''s tenant. Supersedes the '
    'session-level behaviour in 0002.';

-- ===========================================================================
-- F4 — allocation is exact for negative totals as well (FR-DAT-006)
-- ===========================================================================
-- Integer division truncates toward zero and the remainder carries the sign of the
-- dividend, so `i <= v_remainder` was never true for a negative total and the
-- largest-remainder loop never fired: -10000 over 3 parts summed to -9999, and -1 over
-- 3 parts vanished entirely. money.amount_minor is a bare bigint and refunds are
-- negative, so this was reachable.
--
-- The remainder is now distributed in the direction of its own sign. Determinism is
-- unchanged: the first abs(remainder) parts carry the extra unit, in index order.

CREATE OR REPLACE FUNCTION money.allocate(p_total_minor money.amount_minor, p_parts integer)
RETURNS TABLE (part_index integer, part_amount money.amount_minor)
LANGUAGE plpgsql IMMUTABLE
AS $$
DECLARE
    v_base      bigint;
    v_remainder bigint;
    v_extra     bigint;
    v_step      bigint;
BEGIN
    IF p_parts IS NULL OR p_parts < 1 THEN
        RAISE EXCEPTION 'ALLOCATION_PARTS_INVALID: parts must be at least 1'
            USING ERRCODE = 'HS422';
    END IF;

    v_base      := p_total_minor / p_parts;      -- integer division, truncates toward zero
    v_remainder := p_total_minor % p_parts;      -- units that do not divide evenly
    v_extra     := abs(v_remainder);             -- how many parts carry an extra unit
    v_step      := CASE WHEN v_remainder < 0 THEN -1 ELSE 1 END;

    RETURN QUERY
    SELECT i, (v_base + CASE WHEN i <= v_extra THEN v_step ELSE 0 END)::money.amount_minor
    FROM generate_series(1, p_parts) AS i;
END;
$$;

COMMENT ON FUNCTION money.allocate(money.amount_minor, integer) IS
    'Splits an amount into N parts that sum EXACTLY back to the original, for negative '
    'totals as well as positive (FR-DAT-006). Largest-remainder: the first abs(remainder) '
    'parts carry one extra minor unit, in the direction of the total''s sign.';

-- ===========================================================================
-- F11 — the tie-breaking direction of half_up is stated, not inferred
-- ===========================================================================
-- round() on numeric breaks a tie away from zero, so half_up sends -2.5 to -3. That is
-- what HALF_UP means in Java BigDecimal and Python decimal, and it is what this type
-- means. It is NOT "toward positive infinity" — that mode is half_ceiling and does not
-- exist here. Stating it removes the ambiguity that made it worth raising, and the
-- verification suite now proves the direction on negative amounts.

COMMENT ON TYPE money.rounding_mode IS
    'Rounding is always explicit. There is no default mode, because an unstated default '
    'is how two subsystems come to disagree about a half-cent. Tie-breaking is stated '
    'rather than inferred: half_up breaks a tie AWAY FROM ZERO (2.5 to 3, -2.5 to -3), '
    'matching HALF_UP in Java BigDecimal and Python decimal; half_even breaks to the '
    'even neighbour; floor and ceiling are directional and never tie.';

-- ===========================================================================
-- F6 — the currency-pairing check is vacuous at M1 and says so
-- ===========================================================================
-- No column of type money.amount_minor exists anywhere in Phase 1's M1 schema, so this
-- function asserts a property of the empty set. The mechanism is correct and fires when
-- a real column exists; what was wrong is that a reviewer could read a passing check as
-- evidence of a property that nothing had. It now reports the size of the population it
-- checked, so "zero offenders" and "nothing to check" are distinguishable, and the
-- verification suite asserts the vacuity explicitly and proves the mechanism against a
-- real column rather than trusting it.

CREATE FUNCTION money.currency_pairing_population()
RETURNS bigint
LANGUAGE sql STABLE
AS $$
    SELECT count(*)
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_type t ON t.oid = a.atttypid
    WHERE c.relkind = 'r'
      AND a.attnum > 0 AND NOT a.attisdropped
      AND t.typname = 'amount_minor';
$$;

COMMENT ON FUNCTION money.currency_pairing_population() IS
    'How many columns money.assert_currency_paired() actually examined. Zero means the '
    'check is vacuous, which is the true state at M1: no M1 table holds money. Read it '
    'beside assert_currency_paired so an empty result cannot be mistaken for a proof.';

COMMENT ON FUNCTION money.assert_currency_paired() IS
    'Reports any money.amount_minor column with no currency_code beside it (FR-DAT-006). '
    'VACUOUS AT M1: no M1 table holds money, so the population is zero and an empty '
    'result proves nothing on its own. It becomes live at M4, when checks, bills and '
    'payments introduce the first stored amounts. Always read money.currency_pairing_'
    'population() alongside it.';

GRANT EXECUTE ON FUNCTION money.currency_pairing_population() TO hospitality_app;
GRANT EXECUTE ON FUNCTION identity.emit_security_event(uuid, uuid, text, uuid) TO hospitality_app;
