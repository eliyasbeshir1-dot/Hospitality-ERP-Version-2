-- 0002_identity_memberships_and_authentication.sql
--
-- Gate:         M1, slice B
-- Requirements: FR-AUTH-001 FR-AUTH-004 FR-AUTH-005 FR-AUTH-006 FR-AUTH-007
--               FR-AUTH-008 FR-AUTH-009 FR-AUTH-010 FR-SEC-007
--
-- Scope note: identity, memberships, sessions, step-up and service principals only.
-- The configuration store, audit tables and money/quantity types are M1-C and are
-- deliberately absent. Recovery emits a security event; it does not store one.
--
-- Forward-only. Checksum-locked once applied (FR-DAT-016).
--
-- SECRET HANDLING (FR-SEC-007)
-- No plaintext credential, token or one-time code is ever stored, logged or written
-- into a fixture. Every secret column holds a 32-byte digest produced by the caller;
-- a length CHECK makes storing a plaintext string impossible. No error message in
-- this migration interpolates a secret value.

CREATE SCHEMA identity;
COMMENT ON SCHEMA identity IS
    'Identity, memberships, sessions, step-up authentication and service principals.';

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

CREATE TYPE identity.channel_kind    AS ENUM ('phone', 'email');
CREATE TYPE identity.credential_kind AS ENUM ('password', 'otp', 'quick_pin', 'service_secret');

-- How strongly the holder was authenticated. Ordered weakest to strongest; the
-- ordering is what step-up enforcement compares against.
CREATE TYPE identity.auth_strength   AS ENUM ('low', 'standard', 'strong');

-- A simulated provider result is a distinct value, not a flag on a live one, so it
-- can never be silently recorded as a live outcome (FR-AUTH-001).
CREATE TYPE identity.transmission_mode AS ENUM ('simulated', 'live');

CREATE TYPE identity.principal_class AS ENUM ('worker', 'integration', 'edge_node', 'print_agent');

CREATE TYPE identity.revocation_reason AS ENUM (
    'signed_out', 'expired', 'membership_withdrawn', 'security_event',
    'rotated', 'administrator_revoked', 'recovery'
);

-- ---------------------------------------------------------------------------
-- Session context accessors
-- ---------------------------------------------------------------------------
-- app.current_tenant_id() and app.current_outlet_id() come from 0001 and are not
-- redefined here. These add the session and strength that M1-B introduces. Nothing
-- below widens app.row_in_scope(); every new table is governed by it unchanged.

CREATE FUNCTION app.current_session_id() RETURNS uuid
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN nullif(current_setting('app.session_id', true), '')::uuid;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$;

CREATE FUNCTION app.current_auth_strength() RETURNS identity.auth_strength
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN nullif(current_setting('app.auth_strength', true), '')::identity.auth_strength;
EXCEPTION WHEN others THEN
    RETURN NULL;   -- unknown strength is treated as no strength
END;
$$;

-- ---------------------------------------------------------------------------
-- identity.user_account
-- ---------------------------------------------------------------------------

CREATE TABLE identity.user_account (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    staff_number    text NOT NULL,                      -- human number (FR-DAT-003)
    display_name    text NOT NULL,
    status          org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version     bigint NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    deactivated_at  timestamptz,
    archived_at     timestamptz,

    CONSTRAINT user_account_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT user_account_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT user_account_staff_number_unique UNIQUE (tenant_id, staff_number),
    CONSTRAINT user_account_row_version_positive CHECK (row_version > 0),
    CONSTRAINT user_account_lifecycle_consistent CHECK (
        (status = 'active'   AND deactivated_at IS NULL     AND archived_at IS NULL)
     OR (status = 'inactive' AND deactivated_at IS NOT NULL AND archived_at IS NULL)
     OR (status = 'archived' AND archived_at IS NOT NULL)
    )
);

COMMENT ON TABLE identity.user_account IS
    'A staff identity within one tenant. Access is not conferred here — it comes '
    'entirely from identity.membership (FR-AUTH-008).';

CREATE TRIGGER user_account_row_version BEFORE UPDATE ON identity.user_account
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

-- ---------------------------------------------------------------------------
-- identity.identity_channel — verified phone or email (FR-AUTH-001)
-- ---------------------------------------------------------------------------

CREATE TABLE identity.identity_channel (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    user_account_id uuid NOT NULL,
    channel         identity.channel_kind NOT NULL,
    channel_value   text NOT NULL,                      -- phone number or email address
    verified_at     timestamptz,
    row_version     bigint NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT identity_channel_user_fk FOREIGN KEY (tenant_id, user_account_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT identity_channel_unique UNIQUE (tenant_id, channel, channel_value),
    CONSTRAINT identity_channel_value_not_blank CHECK (btrim(channel_value) <> ''),
    CONSTRAINT identity_channel_row_version_positive CHECK (row_version > 0)
);

COMMENT ON TABLE identity.identity_channel IS
    'Login channels. Either a verified phone or a verified email is sufficient '
    'to identify a user (FR-AUTH-001); an unverified channel authenticates nobody.';

CREATE TRIGGER identity_channel_row_version BEFORE UPDATE ON identity.identity_channel
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

-- ---------------------------------------------------------------------------
-- identity.auth_provider_binding — the replaceable adapter (FR-AUTH-001)
-- ---------------------------------------------------------------------------
-- The provider is named as free text and its identifier is opaque. No column here
-- has a provider-specific type, and nothing downstream branches on provider_name,
-- so swapping the provider touches this table and nothing in the domain model.

CREATE TABLE identity.auth_provider_binding (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL,
    user_account_id     uuid NOT NULL,
    provider_name       text NOT NULL,
    provider_subject_ref text NOT NULL,                 -- opaque to this system
    bound_at            timestamptz NOT NULL DEFAULT now(),
    row_version         bigint NOT NULL DEFAULT 1,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT auth_provider_binding_user_fk FOREIGN KEY (tenant_id, user_account_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT auth_provider_binding_unique UNIQUE (tenant_id, provider_name, provider_subject_ref),
    CONSTRAINT auth_provider_binding_row_version_positive CHECK (row_version > 0)
);

COMMENT ON COLUMN identity.auth_provider_binding.provider_subject_ref IS
    'Opaque provider-side identifier. Never parsed, never given meaning here.';

-- ---------------------------------------------------------------------------
-- identity.credential — every secret, stored only as a digest (FR-SEC-007)
-- ---------------------------------------------------------------------------

CREATE TABLE identity.credential (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    outlet_id         uuid,                             -- quick PINs are outlet-scoped
    user_account_id   uuid,
    kind              identity.credential_kind NOT NULL,
    secret_digest     bytea NOT NULL,
    digest_algorithm  text NOT NULL,
    confers_strength  identity.auth_strength NOT NULL,
    expires_at        timestamptz,
    rotated_at        timestamptz,
    revoked_at        timestamptz,
    row_version       bigint NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT credential_user_fk FOREIGN KEY (tenant_id, user_account_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT credential_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,

    -- A digest is exactly 32 bytes. A plaintext secret cannot satisfy this.
    CONSTRAINT credential_digest_is_a_digest CHECK (octet_length(secret_digest) = 32),
    CONSTRAINT credential_algorithm_not_blank CHECK (btrim(digest_algorithm) <> ''),

    -- A quick PIN may only ever confer low strength (FR-AUTH-005).
    CONSTRAINT credential_quick_pin_is_low_strength CHECK (
        kind <> 'quick_pin' OR confers_strength = 'low'
    ),
    -- A quick PIN is meaningless away from the terminal it belongs to.
    CONSTRAINT credential_quick_pin_is_outlet_scoped CHECK (
        kind <> 'quick_pin' OR outlet_id IS NOT NULL
    ),
    CONSTRAINT credential_row_version_positive CHECK (row_version > 0)
);

COMMENT ON TABLE identity.credential IS
    'Password, one-time code, quick PIN and service secret digests. Plaintext never '
    'enters this table: the 32-byte length CHECK makes it structurally impossible.';

CREATE INDEX credential_lookup_idx ON identity.credential (tenant_id, user_account_id, kind);

CREATE TRIGGER credential_row_version BEFORE UPDATE ON identity.credential
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

-- ---------------------------------------------------------------------------
-- identity.otp_transmission — simulated provider results (FR-AUTH-001)
-- ---------------------------------------------------------------------------
-- Phase 1 messaging is simulated. The mode is immutable after insert, so a
-- simulated result can never later be presented as a live provider outcome.

CREATE TABLE identity.otp_transmission (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL,
    identity_channel_id uuid NOT NULL,
    mode                identity.transmission_mode NOT NULL,
    provider_name       text NOT NULL,
    provider_result_ref text,
    requested_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT otp_transmission_channel_fk FOREIGN KEY (identity_channel_id)
        REFERENCES identity.identity_channel (id) ON DELETE RESTRICT,
    CONSTRAINT otp_transmission_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    -- A simulated transmission carries no provider result reference. There is
    -- nothing real to reference, and inventing one would make it indistinguishable
    -- from a live outcome.
    CONSTRAINT otp_transmission_simulated_has_no_provider_result CHECK (
        mode <> 'simulated' OR provider_result_ref IS NULL
    )
);

COMMENT ON TABLE identity.otp_transmission IS
    'Record of one-time-code transmissions. Never stores the code itself. The mode '
    'column is immutable (see the trigger below) so a simulated result cannot be '
    'promoted to a live one.';

CREATE FUNCTION identity.forbid_transmission_mode_change() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.mode IS DISTINCT FROM OLD.mode THEN
        RAISE EXCEPTION
            'SIMULATED_RESULT_RECORDED_AS_LIVE: transmission mode is immutable once recorded'
            USING ERRCODE = 'HS403';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER otp_transmission_mode_immutable
    BEFORE UPDATE ON identity.otp_transmission
    FOR EACH ROW EXECUTE FUNCTION identity.forbid_transmission_mode_change();

-- ---------------------------------------------------------------------------
-- identity.role and identity.role_action
-- ---------------------------------------------------------------------------

CREATE TABLE identity.role (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL,
    role_code    text NOT NULL,
    display_name text NOT NULL,
    status       org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version  bigint NOT NULL DEFAULT 1,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT role_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT role_tenant_fk FOREIGN KEY (tenant_id) REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT role_code_unique UNIQUE (tenant_id, role_code),
    CONSTRAINT role_row_version_positive CHECK (row_version > 0)
);

CREATE TABLE identity.role_action (
    tenant_id   uuid NOT NULL,
    role_id     uuid NOT NULL,
    action_code text NOT NULL,
    granted_at  timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (role_id, action_code),
    CONSTRAINT role_action_role_fk FOREIGN KEY (tenant_id, role_id)
        REFERENCES identity.role (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT role_action_code_not_blank CHECK (btrim(action_code) <> '')
);

COMMENT ON TABLE identity.role_action IS
    'Which actions a role may perform. Absence of a row denies the action: there is '
    'no implicit grant.';

-- ---------------------------------------------------------------------------
-- identity.membership — the core of the slice (FR-AUTH-008)
-- ---------------------------------------------------------------------------
-- This is what populates the context app.row_in_scope() reads. A membership with
-- outlet_id NULL is tenant-wide; otherwise it authorizes exactly one outlet.

CREATE TABLE identity.membership (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    outlet_id       uuid,
    user_account_id uuid NOT NULL,
    role_id         uuid NOT NULL,
    status          org.lifecycle_status NOT NULL DEFAULT 'active',
    withdrawn_at    timestamptz,
    row_version     bigint NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT membership_user_fk FOREIGN KEY (tenant_id, user_account_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT membership_role_fk FOREIGN KEY (tenant_id, role_id)
        REFERENCES identity.role (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT membership_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT membership_unique UNIQUE (tenant_id, user_account_id, outlet_id, role_id),
    CONSTRAINT membership_row_version_positive CHECK (row_version > 0),
    CONSTRAINT membership_withdrawal_consistent CHECK (
        (status = 'active' AND withdrawn_at IS NULL) OR (status <> 'active')
    )
);

COMMENT ON TABLE identity.membership IS
    'Explicit tenant/outlet role assignment (FR-AUTH-008). Staff access derives from '
    'these rows and nowhere else. Withdrawing one revokes dependent sessions at once.';

CREATE INDEX membership_user_idx ON identity.membership (tenant_id, user_account_id, status);

CREATE TRIGGER membership_row_version BEFORE UPDATE ON identity.membership
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

-- ---------------------------------------------------------------------------
-- identity.session — sessions and devices (FR-AUTH-004)
-- ---------------------------------------------------------------------------
-- The session token is a bearer secret. Only its digest is stored. The token's
-- non-secret prefix carries the tenant and outlet it belongs to, which is what lets
-- a caller establish context without any policy exception: presenting the wrong
-- tenant or outlet simply finds no row.

CREATE TABLE identity.session (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    outlet_id         uuid,
    user_account_id   uuid,
    service_principal_id uuid,
    device_id         uuid,
    token_digest      bytea NOT NULL,
    established_with  identity.auth_strength NOT NULL,
    issued_at         timestamptz NOT NULL DEFAULT now(),
    expires_at        timestamptz NOT NULL,
    last_rotated_at   timestamptz,
    revoked_at        timestamptz,
    revoked_reason    identity.revocation_reason,
    row_version       bigint NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT session_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT session_user_fk FOREIGN KEY (tenant_id, user_account_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT session_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT session_device_fk FOREIGN KEY (tenant_id, device_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT session_token_digest_unique UNIQUE (token_digest),
    CONSTRAINT session_token_is_a_digest CHECK (octet_length(token_digest) = 32),
    CONSTRAINT session_expires_after_issue CHECK (expires_at > issued_at),
    CONSTRAINT session_revocation_consistent CHECK (
        (revoked_at IS NULL) = (revoked_reason IS NULL)
    ),
    -- A session belongs to a person or to a service principal, never both, never neither.
    CONSTRAINT session_has_exactly_one_subject CHECK (
        (user_account_id IS NOT NULL) <> (service_principal_id IS NOT NULL)
    ),
    CONSTRAINT session_row_version_positive CHECK (row_version > 0)
);

COMMENT ON TABLE identity.session IS
    'Live sessions, listable and revocable per user and per device (FR-AUTH-004). '
    'Stores only the token digest; the token itself never reaches the database.';

CREATE INDEX session_user_idx   ON identity.session (tenant_id, user_account_id);
CREATE INDEX session_device_idx ON identity.session (tenant_id, device_id);

CREATE TRIGGER session_row_version BEFORE UPDATE ON identity.session
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

-- ---------------------------------------------------------------------------
-- identity.terminal_trust — trusted outlet terminals (FR-AUTH-005)
-- ---------------------------------------------------------------------------

CREATE TABLE identity.terminal_trust (
    device_id   uuid PRIMARY KEY,
    tenant_id   uuid NOT NULL,
    outlet_id   uuid NOT NULL,
    trusted_at  timestamptz NOT NULL DEFAULT now(),
    withdrawn_at timestamptz,

    CONSTRAINT terminal_trust_device_fk FOREIGN KEY (tenant_id, device_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT terminal_trust_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT
);

COMMENT ON TABLE identity.terminal_trust IS
    'Terminals at which a quick PIN may be presented. A quick PIN offered anywhere '
    'else authenticates nobody.';

-- ---------------------------------------------------------------------------
-- identity.governed_action — the step-up registry (FR-AUTH-005, FR-AUTH-006)
-- ---------------------------------------------------------------------------
-- The enforcement point is built now and the action list is registered now, so M4
-- and M6 inherit it rather than inventing their own.
--
-- Boundary note: this is an authentication policy registry, not the general
-- configuration store. The configuration and policy store is M1-C.

CREATE TABLE identity.governed_action (
    tenant_id          uuid NOT NULL,
    action_code        text NOT NULL,
    minimum_strength   identity.auth_strength NOT NULL,
    step_up_required   boolean NOT NULL DEFAULT false,
    step_up_max_age    interval,
    governed_from_gate text NOT NULL,

    PRIMARY KEY (tenant_id, action_code),
    CONSTRAINT governed_action_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE CASCADE,
    CONSTRAINT governed_action_code_not_blank CHECK (btrim(action_code) <> ''),
    -- A step-up requirement without a recency window is not a requirement.
    CONSTRAINT governed_action_step_up_has_window CHECK (
        step_up_required = false OR step_up_max_age IS NOT NULL
    )
);

COMMENT ON TABLE identity.governed_action IS
    'Actions requiring more than routine authentication. Registered at M1 for role '
    'and configuration changes; refunds, reversals and payouts are registered for M4 '
    'and exports for M6 so those gates inherit the enforcement point.';

-- Every tenant receives the standard registry when it is created, so enforcement is
-- never absent for a newly provisioned tenant.
CREATE FUNCTION identity.install_governed_actions() RETURNS trigger
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
        -- Routine actions: no step-up, but a quick PIN is still enough only here.
        (NEW.id, 'order.view',             'low',    false, NULL,                  'M1'),
        (NEW.id, 'session.resume',         'low',    false, NULL,                  'M1');
    RETURN NULL;
END;
$$;

CREATE TRIGGER tenant_install_governed_actions
    AFTER INSERT ON org.tenant
    FOR EACH ROW EXECUTE FUNCTION identity.install_governed_actions();

-- ---------------------------------------------------------------------------
-- identity.step_up_grant — recent stronger authentication (FR-AUTH-006)
-- ---------------------------------------------------------------------------

CREATE TABLE identity.step_up_grant (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL,
    outlet_id   uuid,
    session_id  uuid NOT NULL,
    action_code text NOT NULL,
    granted_at  timestamptz NOT NULL DEFAULT now(),
    consumed_at timestamptz,

    CONSTRAINT step_up_grant_session_fk FOREIGN KEY (tenant_id, session_id)
        REFERENCES identity.session (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT step_up_grant_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT
);

COMMENT ON TABLE identity.step_up_grant IS
    'Evidence that stronger authentication happened recently. Age is compared against '
    'the governed action window at the moment of use; a grant is never evergreen.';

CREATE INDEX step_up_grant_lookup_idx
    ON identity.step_up_grant (tenant_id, session_id, action_code, granted_at DESC);

-- ---------------------------------------------------------------------------
-- identity.auth_attempt and identity.auth_lockout (FR-AUTH-007)
-- ---------------------------------------------------------------------------
-- Single-database counters. This is per-node throttling and lockout, NOT distributed
-- production rate limiting; that is M6 infrastructure. Nothing here should be read as
-- proving distributed behaviour.

CREATE TABLE identity.auth_attempt (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL,
    outlet_id     uuid,
    subject_digest bytea NOT NULL,        -- digest of the presented identifier
    succeeded     boolean NOT NULL,
    attempted_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT auth_attempt_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE CASCADE,
    CONSTRAINT auth_attempt_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT auth_attempt_subject_is_a_digest CHECK (octet_length(subject_digest) = 32)
);

COMMENT ON TABLE identity.auth_attempt IS
    'Authentication attempts, keyed by a digest of the identifier so no phone number '
    'or email address is stored here. Per-node counters only.';

CREATE INDEX auth_attempt_window_idx
    ON identity.auth_attempt (tenant_id, subject_digest, attempted_at DESC);

CREATE TABLE identity.auth_lockout (
    tenant_id      uuid NOT NULL,
    subject_digest bytea NOT NULL,
    locked_at      timestamptz NOT NULL DEFAULT now(),
    locked_until   timestamptz NOT NULL,
    failure_count  integer NOT NULL,

    PRIMARY KEY (tenant_id, subject_digest),
    CONSTRAINT auth_lockout_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE CASCADE,
    CONSTRAINT auth_lockout_window_valid CHECK (locked_until > locked_at),
    CONSTRAINT auth_lockout_subject_is_a_digest CHECK (octet_length(subject_digest) = 32),
    CONSTRAINT auth_lockout_failure_count_positive CHECK (failure_count > 0)
);

-- ---------------------------------------------------------------------------
-- identity.service_principal and its scope (FR-AUTH-009)
-- ---------------------------------------------------------------------------
-- The edge_node and print_agent classes are registered so M5a inherits them. No
-- edge-specific behaviour is built here.

CREATE TABLE identity.service_principal (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL,
    principal_code text NOT NULL,
    class         identity.principal_class NOT NULL,
    status        org.lifecycle_status NOT NULL DEFAULT 'active',
    rotated_at    timestamptz,
    revoked_at    timestamptz,
    row_version   bigint NOT NULL DEFAULT 1,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT service_principal_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT service_principal_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT service_principal_code_unique UNIQUE (tenant_id, principal_code),
    CONSTRAINT service_principal_row_version_positive CHECK (row_version > 0)
);

CREATE TABLE identity.service_principal_scope (
    tenant_id            uuid NOT NULL,
    service_principal_id uuid NOT NULL,
    outlet_id            uuid,                 -- NULL means tenant-wide
    action_code          text NOT NULL,
    granted_at           timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (service_principal_id, action_code, outlet_id),
    CONSTRAINT service_principal_scope_principal_fk FOREIGN KEY (tenant_id, service_principal_id)
        REFERENCES identity.service_principal (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT service_principal_scope_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT
);

COMMENT ON TABLE identity.service_principal_scope IS
    'Exhaustive list of what a principal may do and where. Absence denies.';

-- ---------------------------------------------------------------------------
-- identity.recovery_request — administrator-controlled recovery (FR-AUTH-010)
-- ---------------------------------------------------------------------------

CREATE TABLE identity.recovery_request (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL,
    outlet_id           uuid,
    subject_user_id     uuid NOT NULL,
    requested_by_user_id uuid NOT NULL,
    identity_verified_at timestamptz,
    old_factors_revoked_at timestamptz,
    completed_at        timestamptz,
    row_version         bigint NOT NULL DEFAULT 1,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT recovery_subject_fk FOREIGN KEY (tenant_id, subject_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT recovery_requester_fk FOREIGN KEY (tenant_id, requested_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT recovery_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    -- Recovery cannot complete until identity was verified and old factors revoked.
    CONSTRAINT recovery_completion_requires_verification_and_revocation CHECK (
        completed_at IS NULL
        OR (identity_verified_at IS NOT NULL AND old_factors_revoked_at IS NOT NULL)
    ),
    CONSTRAINT recovery_row_version_positive CHECK (row_version > 0)
);

COMMENT ON TABLE identity.recovery_request IS
    'Administrator-controlled recovery. Emits a security event on completion; durable '
    'audit storage is M1-C and is deliberately not built here.';

CREATE TRIGGER recovery_request_row_version BEFORE UPDATE ON identity.recovery_request
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

-- ---------------------------------------------------------------------------
-- Security events, emitted but not stored (FR-AUTH-010)
-- ---------------------------------------------------------------------------
-- Durable audit storage is M1-C. Emitting through NOTIFY keeps the emission point
-- real and testable now, without building the table that M1-C owns. The payload
-- carries identifiers only — never a credential, token or code.

CREATE FUNCTION identity.emit_security_event(p_event_code text, p_subject_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_notify('identity_security_event',
                      json_build_object('event', p_event_code,
                                        'tenant_id', app.current_tenant_id(),
                                        'subject_id', p_subject_id,
                                        'at', now())::text);
END;
$$;

COMMENT ON FUNCTION identity.emit_security_event(text, uuid) IS
    'Emission point for security events. M1-C attaches durable storage; nothing is '
    'persisted here by design.';

-- ---------------------------------------------------------------------------
-- Session revocation cascade (FR-AUTH-004)
-- ---------------------------------------------------------------------------
-- A withdrawn membership must not survive in a live session. This revokes eagerly;
-- identity.establish_session_context re-checks membership on every use as well, so
-- the guarantee does not depend on this trigger alone.

CREATE FUNCTION identity.revoke_sessions_on_membership_change() RETURNS trigger
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
      -- Only revoke sessions this membership was actually supporting.
      AND NOT EXISTS (
            SELECT 1 FROM identity.membership m
            WHERE m.tenant_id       = s.tenant_id
              AND m.user_account_id = s.user_account_id
              AND m.status          = 'active'
              AND m.id             <> NEW.id
              AND (m.outlet_id IS NULL OR m.outlet_id = s.outlet_id)
      );

    PERFORM identity.emit_security_event('membership.withdrawn', NEW.user_account_id);
    RETURN NULL;
END;
$$;

CREATE TRIGGER membership_revocation_cascade
    AFTER UPDATE OF status ON identity.membership
    FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION identity.revoke_sessions_on_membership_change();

-- ---------------------------------------------------------------------------
-- Establishing session context (FR-AUTH-008)
-- ---------------------------------------------------------------------------
-- This is the bridge from M1-B's membership model to M1-A's isolation predicate.
--
-- No policy exception and no SECURITY DEFINER is needed. The caller supplies the
-- tenant and outlet the token claims — these travel in the token's non-secret
-- prefix — and the lookup then runs under ordinary RLS. Claiming the wrong tenant
-- or outlet simply matches no row, because the digest is unique across the table
-- and the policy hides everything outside the claimed scope.
--
-- Context is only left set if a live session AND an active membership are both
-- found. Any failure clears the context, so a failed attempt leaves the caller with
-- strictly less access than before, never more.

CREATE FUNCTION identity.establish_session_context(
    p_tenant_id    uuid,
    p_outlet_id    uuid,
    p_token_digest bytea
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_session   identity.session%ROWTYPE;
    v_has_member boolean;
BEGIN
    PERFORM set_config('app.tenant_id',     coalesce(p_tenant_id::text, ''), false);
    PERFORM set_config('app.outlet_id',     coalesce(p_outlet_id::text, ''), false);
    PERFORM set_config('app.session_id',    '', false);
    PERFORM set_config('app.auth_strength', '', false);

    SELECT * INTO v_session
    FROM identity.session s
    WHERE s.token_digest = p_token_digest
      AND s.revoked_at IS NULL
      AND s.expires_at > now();

    IF NOT FOUND THEN
        PERFORM set_config('app.tenant_id', '', false);
        PERFORM set_config('app.outlet_id', '', false);
        RAISE EXCEPTION 'SESSION_NOT_LIVE: no live session for the presented credential'
            USING ERRCODE = 'HS401';
    END IF;

    -- Re-checked on every use, so withdrawing a membership takes effect at once even
    -- if the eager revocation above did not run.
    SELECT EXISTS (
        SELECT 1 FROM identity.membership m
        WHERE m.tenant_id       = v_session.tenant_id
          AND m.user_account_id = v_session.user_account_id
          AND m.status          = 'active'
          AND (m.outlet_id IS NULL OR m.outlet_id = v_session.outlet_id)
    ) INTO v_has_member;

    IF v_session.user_account_id IS NOT NULL AND NOT v_has_member THEN
        PERFORM set_config('app.tenant_id', '', false);
        PERFORM set_config('app.outlet_id', '', false);
        RAISE EXCEPTION 'NO_ACTIVE_MEMBERSHIP: the session subject holds no active membership here'
            USING ERRCODE = 'HS403';
    END IF;

    PERFORM set_config('app.session_id',    v_session.id::text, false);
    PERFORM set_config('app.auth_strength', v_session.established_with::text, false);
    RETURN v_session.id;
END;
$$;

-- ---------------------------------------------------------------------------
-- Action authorization: strength and step-up (FR-AUTH-005, FR-AUTH-006)
-- ---------------------------------------------------------------------------
-- The single enforcement point. M4 and M6 call this for their own actions rather
-- than writing new checks.

CREATE FUNCTION identity.authorize_action(p_action_code text) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_session  identity.session%ROWTYPE;
    v_action   identity.governed_action%ROWTYPE;
    v_granted  timestamptz;
    v_permitted boolean;
BEGIN
    SELECT * INTO v_session FROM identity.session
    WHERE id = app.current_session_id() AND revoked_at IS NULL AND expires_at > now();

    IF NOT FOUND THEN
        RAISE EXCEPTION 'SESSION_NOT_LIVE: no live session in context'
            USING ERRCODE = 'HS401';
    END IF;

    SELECT * INTO v_action FROM identity.governed_action
    WHERE tenant_id = v_session.tenant_id AND action_code = p_action_code;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'ACTION_NOT_REGISTERED: % is not a registered action', p_action_code
            USING ERRCODE = 'HS403';
    END IF;

    -- The role must actually grant the action. Absence denies.
    SELECT EXISTS (
        SELECT 1
        FROM identity.membership m
        JOIN identity.role_action ra ON ra.role_id = m.role_id AND ra.tenant_id = m.tenant_id
        WHERE m.tenant_id       = v_session.tenant_id
          AND m.user_account_id = v_session.user_account_id
          AND m.status          = 'active'
          AND (m.outlet_id IS NULL OR m.outlet_id = v_session.outlet_id)
          AND ra.action_code    = p_action_code
    ) INTO v_permitted;

    IF NOT v_permitted THEN
        RAISE EXCEPTION 'ACTION_NOT_GRANTED: no active membership grants %', p_action_code
            USING ERRCODE = 'HS403';
    END IF;

    -- A quick PIN confers 'low'. Anything above routine needs more (FR-AUTH-005).
    IF v_session.established_with < v_action.minimum_strength THEN
        RAISE EXCEPTION
            'LOW_RISK_CREDENTIAL_USED_FOR_SENSITIVE_ACTION: % needs % authentication, session holds %',
            p_action_code, v_action.minimum_strength, v_session.established_with
            USING ERRCODE = 'HS403';
    END IF;

    IF v_action.step_up_required THEN
        SELECT max(granted_at) INTO v_granted
        FROM identity.step_up_grant
        WHERE tenant_id = v_session.tenant_id
          AND session_id = v_session.id
          AND action_code = p_action_code;

        IF v_granted IS NULL THEN
            RAISE EXCEPTION 'STEP_UP_REQUIRED: % requires recent stronger authentication', p_action_code
                USING ERRCODE = 'HS403';
        END IF;

        -- The window is evaluated at the moment of use. A grant is never evergreen.
        IF now() - v_granted > v_action.step_up_max_age THEN
            RAISE EXCEPTION
                'STEP_UP_EXPIRED: the step-up for % is older than the % recency window',
                p_action_code, v_action.step_up_max_age
                USING ERRCODE = 'HS403';
        END IF;
    END IF;

    RETURN true;
END;
$$;

-- ---------------------------------------------------------------------------
-- Service principal authorization (FR-AUTH-009)
-- ---------------------------------------------------------------------------

CREATE FUNCTION identity.authorize_service_principal(
    p_principal_id uuid,
    p_action_code  text,
    p_outlet_id    uuid
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_principal identity.service_principal%ROWTYPE;
    v_in_scope  boolean;
BEGIN
    SELECT * INTO v_principal FROM identity.service_principal
    WHERE id = p_principal_id AND status = 'active' AND revoked_at IS NULL;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'PRINCIPAL_NOT_ACTIVE: the service principal is revoked or absent'
            USING ERRCODE = 'HS401';
    END IF;

    -- Scope must be granted explicitly, for this action, at this outlet or tenant-wide.
    SELECT EXISTS (
        SELECT 1 FROM identity.service_principal_scope sc
        WHERE sc.service_principal_id = p_principal_id
          AND sc.action_code = p_action_code
          AND (sc.outlet_id IS NULL OR sc.outlet_id = p_outlet_id)
    ) INTO v_in_scope;

    IF NOT v_in_scope THEN
        RAISE EXCEPTION
            'OUT_OF_SCOPE_PRINCIPAL_ACCEPTED_CHECK: principal is not scoped for % at this outlet',
            p_action_code
            USING ERRCODE = 'HS403';
    END IF;

    RETURN true;
END;
$$;

-- ---------------------------------------------------------------------------
-- Rate limiting and lockout (FR-AUTH-007)
-- ---------------------------------------------------------------------------
-- Per-node counters. NOT distributed production rate limiting, which is M6.

CREATE FUNCTION identity.register_auth_attempt(
    p_tenant_id      uuid,
    p_subject_digest bytea,
    p_succeeded      boolean,
    p_threshold      integer DEFAULT 5,
    p_window         interval DEFAULT interval '15 minutes',
    p_lock_for       interval DEFAULT interval '15 minutes'
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_locked_until timestamptz;
    v_failures     integer;
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
        PERFORM identity.emit_security_event('auth.locked_out', NULL);
    END IF;

    RETURN false;
END;
$$;

COMMENT ON FUNCTION identity.register_auth_attempt(uuid, bytea, boolean, integer, interval, interval) IS
    'Per-node throttling and lockout. This is not distributed production rate '
    'limiting; that is M6 infrastructure and is not claimed here.';

-- ---------------------------------------------------------------------------
-- Row level security — ENABLE and FORCE on every new table
-- ---------------------------------------------------------------------------
-- Each policy uses app.row_in_scope() from 0001 unchanged. Nothing here widens it.

DO $$
DECLARE
    t text;
    outlet_scoped text[] := ARRAY[
        'credential', 'session', 'terminal_trust', 'step_up_grant',
        'membership', 'auth_attempt', 'service_principal_scope', 'recovery_request'
    ];
BEGIN
    FOR t IN
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'identity' AND c.relkind = 'r'
    LOOP
        EXECUTE format('ALTER TABLE identity.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE identity.%I FORCE  ROW LEVEL SECURITY', t);

        IF t = ANY (outlet_scoped) THEN
            EXECUTE format(
                'CREATE POLICY %I ON identity.%I FOR ALL '
                'USING (app.row_in_scope(tenant_id, outlet_id)) '
                'WITH CHECK (app.row_in_scope(tenant_id, outlet_id))',
                t || '_isolation', t);
        ELSE
            -- Tenant-scoped only. The same predicate is used, with no outlet to narrow by.
            EXECUTE format(
                'CREATE POLICY %I ON identity.%I FOR ALL '
                'USING (app.row_in_scope(tenant_id, NULL::uuid)) '
                'WITH CHECK (app.row_in_scope(tenant_id, NULL::uuid))',
                t || '_isolation', t);
        END IF;
    END LOOP;
END;
$$;

-- ---------------------------------------------------------------------------
-- Grants — the runtime role gains DML and the enforcement functions, nothing more
-- ---------------------------------------------------------------------------

GRANT USAGE ON SCHEMA identity TO hospitality_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA identity TO hospitality_app;

GRANT EXECUTE ON FUNCTION
    app.current_session_id(),
    app.current_auth_strength(),
    identity.establish_session_context(uuid, uuid, bytea),
    identity.authorize_action(text),
    identity.authorize_service_principal(uuid, text, uuid),
    identity.register_auth_attempt(uuid, bytea, boolean, integer, interval, interval),
    identity.emit_security_event(text, uuid)
TO hospitality_app;

REVOKE CREATE ON SCHEMA identity FROM hospitality_app;
