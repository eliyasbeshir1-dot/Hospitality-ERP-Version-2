-- 0003_configuration_audit_money_and_quantity.sql
--
-- Gate:         M1, slice C
-- Requirements: FR-TEN-003 FR-TEN-004 FR-TEN-010 FR-CFG-002A FR-CFG-003 FR-CFG-004
--               FR-CFG-005A FR-DAT-005 FR-DAT-006 FR-DAT-013 FR-DAT-015 FR-DAT-018
--               FR-SEC-009
--
-- Scope note: configuration, audit, money and quantity types, numbering, reason codes,
-- entitlements and retention. The HTTP API, security headers, health endpoints and
-- observability are M1-D and are deliberately absent.
--
-- Ownership: identity.governed_action stays in the identity schema and belongs to M1-B.
-- Configuration REFERENCES it by key. This migration creates no second copy of it and
-- migrates none of its rows.
--
-- Forward-only. Checksum-locked once applied (FR-DAT-016).

CREATE SCHEMA money;
CREATE SCHEMA config;
CREATE SCHEMA audit;

COMMENT ON SCHEMA money  IS 'Exact money and quantity types (FR-DAT-005, FR-DAT-006).';
COMMENT ON SCHEMA config IS 'Versioned tenant configuration, policy, numbering, entitlements.';
COMMENT ON SCHEMA audit  IS 'Append-only security and operational audit storage (FR-SEC-009).';

-- ===========================================================================
-- MONEY AND QUANTITY (FR-DAT-005, FR-DAT-006)
-- ===========================================================================
--
-- Money is stored as integer minor units. Not numeric, not decimal — integers.
-- An integer cannot silently lose precision the way a scaled decimal can when it is
-- divided, and there is no representation in which 0.1 + 0.2 fails to equal 0.3.
--
-- Every money column is accompanied by an explicit currency_code. A bare amount is
-- meaningless and the catalog test below refuses to accept one.
--
-- No binary floating point type appears anywhere in this migration, and the
-- verification suite fails if one appears anywhere in the database.

CREATE DOMAIN money.amount_minor AS bigint;

COMMENT ON DOMAIN money.amount_minor IS
    'A monetary amount in integer minor units of an explicit currency (for ETB, cents). '
    'Never a float, never a bare decimal. Any column of this type must sit beside a '
    'currency_code column; money.assert_currency_paired() proves it.';

-- Quantities carry explicit precision and are never negative. Four decimal places is
-- enough for every Phase 1 quantity and is fixed, not inferred.
CREATE DOMAIN money.quantity AS numeric(14, 4)
    CONSTRAINT quantity_is_not_negative CHECK (VALUE >= 0);

-- Percentages are bounded and exact. A tax or service rate outside 0..100 is a defect,
-- not a configuration choice.
CREATE DOMAIN money.percentage AS numeric(7, 4)
    CONSTRAINT percentage_within_bounds CHECK (VALUE >= 0 AND VALUE <= 100);

CREATE TYPE money.rounding_mode AS ENUM ('half_up', 'half_even', 'floor', 'ceiling');

COMMENT ON TYPE money.rounding_mode IS
    'Rounding is always explicit. There is no default mode, because an unstated default '
    'is how two subsystems come to disagree about a half-cent.';

CREATE TABLE money.currency (
    code               char(3) PRIMARY KEY,
    display_name       text NOT NULL,
    minor_unit_digits  smallint NOT NULL,

    CONSTRAINT currency_code_is_uppercase_alpha CHECK (code ~ '^[A-Z]{3}$'),
    CONSTRAINT currency_minor_unit_digits_sane CHECK (minor_unit_digits BETWEEN 0 AND 4)
);

COMMENT ON TABLE money.currency IS
    'ISO 4217 reference data. Deliberately NOT tenant-scoped: a currency is not a '
    'tenant''s property. The application role holds SELECT only and cannot write here, '
    'which the verification suite proves.';

INSERT INTO money.currency (code, display_name, minor_unit_digits) VALUES
    ('ETB', 'Ethiopian Birr', 2),
    ('USD', 'United States Dollar', 2),
    ('EUR', 'Euro', 2),
    ('AED', 'UAE Dirham', 2),
    ('JPY', 'Japanese Yen', 0);

-- Every money.amount_minor column must sit beside an explicit currency. A bare amount
-- is not money: it is a number that looks like money, which is how a total in cents ends
-- up added to a total in birr. This reports any column that breaks the rule; the
-- verification suite fails when it returns a row.
CREATE FUNCTION money.assert_currency_paired()
RETURNS TABLE (schema_name text, table_name text, column_name text)
LANGUAGE sql STABLE
AS $$
    SELECT n.nspname::text, c.relname::text, a.attname::text
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_type t ON t.oid = a.atttypid
    WHERE c.relkind = 'r'
      AND a.attnum > 0 AND NOT a.attisdropped
      AND t.typname = 'amount_minor'
      AND NOT EXISTS (
            SELECT 1 FROM pg_attribute cur
            WHERE cur.attrelid = c.oid AND cur.attname = 'currency_code'
              AND cur.attnum > 0 AND NOT cur.attisdropped);
$$;

-- Rounding a rate application to whole minor units, with the mode stated by the caller.
-- Takes and returns exact types throughout; there is no floating point step anywhere in
-- the path.
CREATE FUNCTION money.apply_rate(
    p_amount_minor money.amount_minor,
    p_percentage   money.percentage,
    p_mode         money.rounding_mode
) RETURNS money.amount_minor
LANGUAGE plpgsql IMMUTABLE
AS $$
DECLARE
    v_exact numeric;
BEGIN
    -- numeric throughout: exact rational arithmetic, no binary representation error.
    v_exact := (p_amount_minor::numeric * p_percentage::numeric) / 100::numeric;

    RETURN CASE p_mode
        WHEN 'half_up'   THEN round(v_exact, 0)
        WHEN 'half_even' THEN
            -- PostgreSQL's round() on numeric is half-up, so banker's rounding is done
            -- explicitly rather than assumed.
            CASE WHEN v_exact - floor(v_exact) = 0.5
                 THEN CASE WHEN floor(v_exact)::bigint % 2 = 0
                           THEN floor(v_exact) ELSE ceil(v_exact) END
                 ELSE round(v_exact, 0) END
        WHEN 'floor'     THEN floor(v_exact)
        WHEN 'ceiling'   THEN ceil(v_exact)
    END::bigint;
END;
$$;

-- Split an amount into N parts that sum EXACTLY back to the original.
--
-- This is where money bugs live. Dividing 1000 by 3 and rounding each part gives 333
-- three times, which is 999 — a lost minor unit. The largest-remainder method below
-- distributes the remainder deterministically so the parts always reconstitute the
-- total. The verification suite asserts that property, not an approximation of it.
CREATE FUNCTION money.allocate(p_total_minor money.amount_minor, p_parts integer)
RETURNS TABLE (part_index integer, part_amount money.amount_minor)
LANGUAGE plpgsql IMMUTABLE
AS $$
DECLARE
    v_base      bigint;
    v_remainder bigint;
BEGIN
    IF p_parts IS NULL OR p_parts < 1 THEN
        RAISE EXCEPTION 'ALLOCATION_PARTS_INVALID: parts must be at least 1'
            USING ERRCODE = 'HS422';
    END IF;

    v_base      := p_total_minor / p_parts;      -- integer division, exact
    v_remainder := p_total_minor % p_parts;      -- units that do not divide evenly

    RETURN QUERY
    SELECT i, (v_base + CASE WHEN i <= v_remainder THEN 1 ELSE 0 END)::money.amount_minor
    FROM generate_series(1, p_parts) AS i;
END;
$$;

COMMENT ON FUNCTION money.allocate(money.amount_minor, integer) IS
    'Splits an amount so the parts sum exactly to the total. The remainder is given to '
    'the earliest parts, deterministically, so the same input always produces the same '
    'split.';

-- ===========================================================================
-- AUDIT (FR-SEC-009) — append-only, enforced in the database
-- ===========================================================================
-- Two separate stores, as the requirement demands: security audit and operational
-- audit are not the same evidence and are not kept together.
--
-- Append-only is enforced twice over: the application role is never granted UPDATE or
-- DELETE, and a trigger refuses both regardless of who is asking. The grant alone is
-- not the enforcement — a role change would undo it — which is why the trigger exists.

CREATE TABLE audit.security_event (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    uuid NOT NULL,
    outlet_id    uuid,
    event_code   text NOT NULL,
    subject_id   uuid,
    actor_id     uuid,
    occurred_at  timestamptz NOT NULL DEFAULT now(),
    detail       jsonb NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT security_event_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT security_event_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT security_event_code_not_blank CHECK (btrim(event_code) <> '')
);

COMMENT ON TABLE audit.security_event IS
    'Append-only security audit. This is where M1-B''s recovery and lockout events land '
    '(FR-AUTH-010): M1-B emits them, M1-C stores them.';

CREATE TABLE audit.operational_event (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     uuid NOT NULL,
    outlet_id     uuid,
    event_code    text NOT NULL,
    entity_schema text NOT NULL,
    entity_table  text NOT NULL,
    entity_id     text,
    actor_id      uuid,
    approved_by_id uuid,
    approved_at   timestamptz,
    effective_from timestamptz,
    occurred_at   timestamptz NOT NULL DEFAULT now(),
    detail        jsonb NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT operational_event_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT operational_event_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT operational_event_code_not_blank CHECK (btrim(event_code) <> '')
);

COMMENT ON TABLE audit.operational_event IS
    'Append-only operational audit. Every configuration and policy change writes a row '
    'here carrying the actor, the approval and the effective date (FR-TEN-010).';

CREATE INDEX security_event_tenant_idx    ON audit.security_event (tenant_id, occurred_at DESC);
CREATE INDEX operational_event_tenant_idx ON audit.operational_event (tenant_id, occurred_at DESC);
CREATE INDEX operational_event_entity_idx ON audit.operational_event (entity_schema, entity_table, entity_id);

CREATE FUNCTION audit.refuse_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'APPEND_ONLY_VIOLATED: % on %.% is refused; audit storage is append-only',
        TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME
        USING ERRCODE = 'HS403';
END;
$$;

COMMENT ON FUNCTION audit.refuse_mutation() IS
    'Refuses UPDATE and DELETE on audit storage for every caller, including the table '
    'owner. Grants alone would not survive a role change; this does.';

CREATE TRIGGER security_event_append_only
    BEFORE UPDATE OR DELETE ON audit.security_event
    FOR EACH ROW EXECUTE FUNCTION audit.refuse_mutation();

CREATE TRIGGER operational_event_append_only
    BEFORE UPDATE OR DELETE ON audit.operational_event
    FOR EACH ROW EXECUTE FUNCTION audit.refuse_mutation();

-- A statement-level trigger as well, so a TRUNCATE cannot empty the table around the
-- row-level triggers.
CREATE TRIGGER security_event_no_truncate
    BEFORE TRUNCATE ON audit.security_event
    FOR EACH STATEMENT EXECUTE FUNCTION audit.refuse_mutation();

CREATE TRIGGER operational_event_no_truncate
    BEFORE TRUNCATE ON audit.operational_event
    FOR EACH STATEMENT EXECUTE FUNCTION audit.refuse_mutation();

-- ===========================================================================
-- CONFIGURATION (FR-TEN-003, FR-TEN-010, FR-CFG-002A)
-- ===========================================================================

-- Phase 1 configuration categories. This list is closed: adding a Phase 2 or Phase 3
-- category would require altering this type, which the fenced-domain scanner sees.
CREATE TYPE config.configuration_category AS ENUM (
    'branding', 'locale', 'currency', 'timezone', 'tax', 'calendar',
    'numbering', 'payment_method', 'service', 'feature', 'connector'
);

-- Phase 1 policy categories, exactly as the boundary defines them. No Phase 2/3
-- category exists here and none may be added (FR-CFG-002B).
CREATE TYPE config.policy_category AS ENUM (
    'ordering', 'service', 'cancellation', 'discount', 'refund',
    'tip', 'cash', 'approval', 'local_continuity'
);

CREATE TYPE config.scope_kind AS ENUM ('tenant', 'legal_entity', 'outlet');

CREATE TABLE config.configuration_version (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid,
    scope_kind     config.scope_kind NOT NULL,
    scope_node_id  uuid,
    category       config.configuration_category NOT NULL,
    version        integer NOT NULL,
    payload        jsonb NOT NULL,
    effective_from timestamptz NOT NULL,
    effective_to   timestamptz,
    actor_id       uuid NOT NULL,
    approved_by_id uuid NOT NULL,
    approved_at    timestamptz NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT configuration_version_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT configuration_version_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT configuration_version_scope_fk FOREIGN KEY (tenant_id, scope_node_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT configuration_version_actor_fk FOREIGN KEY (tenant_id, actor_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT configuration_version_approver_fk FOREIGN KEY (tenant_id, approved_by_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT configuration_version_number_positive CHECK (version > 0),
    CONSTRAINT configuration_version_window_valid CHECK (
        effective_to IS NULL OR effective_to > effective_from
    ),
    -- Tenant scope has no node; entity and outlet scope must name one.
    CONSTRAINT configuration_version_scope_consistent CHECK (
        (scope_kind = 'tenant' AND scope_node_id IS NULL)
     OR (scope_kind <> 'tenant' AND scope_node_id IS NOT NULL)
    ),
    CONSTRAINT configuration_version_unique UNIQUE (tenant_id, scope_kind, scope_node_id, category, version)
);

COMMENT ON TABLE config.configuration_version IS
    'Versioned, effective-dated tenant configuration (FR-TEN-003). A change never edits '
    'a row: it closes the open version and inserts the next one, so history is intact.';

-- At most one open version per scope and category. coalesce() is used because a NULL
-- scope_node_id would otherwise defeat the uniqueness it is meant to enforce.
CREATE UNIQUE INDEX configuration_version_single_open
    ON config.configuration_version (
        tenant_id, category, scope_kind,
        coalesce(scope_node_id, '00000000-0000-0000-0000-000000000000'::uuid))
    WHERE effective_to IS NULL;

CREATE TABLE config.policy (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid,
    category       config.policy_category NOT NULL,
    version        integer NOT NULL,
    payload        jsonb NOT NULL,
    -- Where a policy governs an action requiring step-up, it names the identity row by
    -- key. It does not copy it. identity.governed_action remains M1-B's (see header).
    governed_action_code text,
    effective_from timestamptz NOT NULL,
    effective_to   timestamptz,
    actor_id       uuid NOT NULL,
    approved_by_id uuid NOT NULL,
    approved_at    timestamptz NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT policy_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT policy_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT policy_actor_fk FOREIGN KEY (tenant_id, actor_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT policy_approver_fk FOREIGN KEY (tenant_id, approved_by_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    -- Reference by key into the identity-owned registry, never a copy of its rows.
    CONSTRAINT policy_governed_action_fk FOREIGN KEY (tenant_id, governed_action_code)
        REFERENCES identity.governed_action (tenant_id, action_code) ON DELETE RESTRICT,

    CONSTRAINT policy_version_positive CHECK (version > 0),
    CONSTRAINT policy_window_valid CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT policy_unique UNIQUE (tenant_id, outlet_id, category, version)
);

COMMENT ON COLUMN config.policy.governed_action_code IS
    'Foreign key into identity.governed_action. Configuration reads that registry; it '
    'never creates a second source of truth for it.';

-- Every configuration and policy change writes an append-only audit row carrying the
-- actor, the approval and the effective date (FR-TEN-010).
CREATE FUNCTION config.audit_configuration_change() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO audit.operational_event
        (tenant_id, outlet_id, event_code, entity_schema, entity_table, entity_id,
         actor_id, approved_by_id, approved_at, effective_from, detail)
    VALUES
        (NEW.tenant_id, NEW.outlet_id,
         TG_TABLE_NAME || '.' || lower(TG_OP), TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.id::text,
         NEW.actor_id, NEW.approved_by_id, NEW.approved_at, NEW.effective_from,
         jsonb_build_object('category', NEW.category, 'version', NEW.version));
    RETURN NULL;
END;
$$;

CREATE TRIGGER configuration_version_audited
    AFTER INSERT OR UPDATE ON config.configuration_version
    FOR EACH ROW EXECUTE FUNCTION config.audit_configuration_change();

CREATE TRIGGER policy_audited
    AFTER INSERT OR UPDATE ON config.policy
    FOR EACH ROW EXECUTE FUNCTION config.audit_configuration_change();

-- Resolve the configuration in force at a moment. Returns nothing when none applies;
-- an absent configuration is never an implicit default.
CREATE FUNCTION config.effective_configuration(
    p_tenant_id uuid,
    p_category  config.configuration_category,
    p_at        timestamptz DEFAULT now()
) RETURNS jsonb
LANGUAGE sql STABLE
AS $$
    SELECT payload FROM config.configuration_version
    WHERE tenant_id = p_tenant_id AND category = p_category
      AND effective_from <= p_at
      AND (effective_to IS NULL OR effective_to > p_at)
    ORDER BY version DESC
    LIMIT 1;
$$;

-- ===========================================================================
-- REASON CODES (FR-CFG-003)
-- ===========================================================================
-- Seedable configuration data. The actions that consume these codes arrive at M3, M4
-- and M5a; nothing here consumes them.

CREATE TYPE config.reason_code_category AS ENUM (
    'order_cancellation', 'void', 'refund', 'discount', 'complimentary_item',
    'payment_reversal', 'tip_correction', 'service_failure', 'printer_failure',
    'manager_override'
);

CREATE TABLE config.reason_code (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL,
    category    config.reason_code_category NOT NULL,
    code        text NOT NULL,
    requires_approval boolean NOT NULL DEFAULT false,
    status      org.lifecycle_status NOT NULL DEFAULT 'active',
    created_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT reason_code_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT reason_code_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT reason_code_unique UNIQUE (tenant_id, category, code),
    CONSTRAINT reason_code_not_blank CHECK (btrim(code) <> '')
);

-- The localized label is a separate row per locale, so adding Amharic and Arabic at M2
-- adds rows and changes no schema. M1 seeds structure only.
CREATE TABLE config.reason_code_label (
    tenant_id      uuid NOT NULL,
    reason_code_id uuid NOT NULL,
    locale         text NOT NULL,
    label          text NOT NULL,

    PRIMARY KEY (reason_code_id, locale),
    CONSTRAINT reason_code_label_code_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT reason_code_label_locale_valid CHECK (locale ~ '^[a-z]{2}(-[A-Z]{2})?$'),
    CONSTRAINT reason_code_label_not_blank CHECK (btrim(label) <> '')
);

COMMENT ON TABLE config.reason_code_label IS
    'One row per locale. M1 seeds the structure; Amharic and Arabic content arrives at '
    'M2 as additional rows, with no schema change.';

-- ===========================================================================
-- ENTITLEMENTS (FR-TEN-004, FR-CFG-005A) — deny by default
-- ===========================================================================

CREATE TABLE config.entitlement (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL,
    outlet_id     uuid,
    scope_kind    config.scope_kind NOT NULL,
    scope_node_id uuid,
    feature_key   text NOT NULL,
    granted       boolean NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT entitlement_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT entitlement_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT entitlement_scope_fk FOREIGN KEY (tenant_id, scope_node_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT entitlement_scope_consistent CHECK (
        (scope_kind = 'tenant' AND scope_node_id IS NULL)
     OR (scope_kind <> 'tenant' AND scope_node_id IS NOT NULL)
    ),
    CONSTRAINT entitlement_feature_key_not_blank CHECK (btrim(feature_key) <> ''),
    CONSTRAINT entitlement_unique UNIQUE (tenant_id, scope_kind, scope_node_id, feature_key)
);

COMMENT ON TABLE config.entitlement IS
    'Module and feature entitlements per tenant, legal entity or outlet (FR-TEN-004). '
    'A missing row is a denial, never an implicit grant.';

-- Resolve an entitlement most-specific-first: outlet, then its ancestors, then tenant.
--
-- Deny by default is the whole point (FR-CFG-005A). Every path that does not find an
-- explicit grant returns false: no row, an unknown key, a NULL, a disabled row, or a
-- scope that does not exist. There is no branch that returns true without a row saying so.
CREATE FUNCTION config.is_entitled(
    p_feature_key text,
    p_outlet_id   uuid DEFAULT NULL
) RETURNS boolean
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_tenant_id uuid := app.current_tenant_id();
    v_granted   boolean;
BEGIN
    IF v_tenant_id IS NULL OR p_feature_key IS NULL OR btrim(p_feature_key) = '' THEN
        RETURN false;          -- no context, or nothing named: deny
    END IF;

    -- Most specific scope wins: the outlet itself, then any ancestor of it, then the
    -- tenant. org.org_closure gives the ancestor set at any depth.
    SELECT e.granted INTO v_granted
    FROM config.entitlement e
    WHERE e.tenant_id = v_tenant_id
      AND e.feature_key = p_feature_key
      AND (
            (e.scope_kind = 'outlet'       AND e.scope_node_id = p_outlet_id)
         OR (e.scope_kind = 'legal_entity' AND p_outlet_id IS NOT NULL AND EXISTS (
                SELECT 1 FROM org.org_closure c
                WHERE c.descendant_id = p_outlet_id AND c.ancestor_id = e.scope_node_id))
         OR (e.scope_kind = 'tenant')
          )
    ORDER BY CASE e.scope_kind WHEN 'outlet' THEN 0 WHEN 'legal_entity' THEN 1 ELSE 2 END
    LIMIT 1;

    RETURN coalesce(v_granted, false);   -- absent or NULL both deny
END;
$$;

COMMENT ON FUNCTION config.is_entitled(text, uuid) IS
    'Deny-by-default entitlement resolution (FR-CFG-005A). Returns false for an unknown '
    'key, an absent row, a NULL value and a missing context alike.';

-- ===========================================================================
-- NUMBERING (FR-CFG-004) — collision-safe under concurrency
-- ===========================================================================

CREATE TABLE config.number_series (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL,
    legal_entity_id  uuid,
    outlet_id        uuid,
    document_type    text NOT NULL,
    fiscal_period    text NOT NULL,
    prefix           text NOT NULL DEFAULT '',
    next_value       bigint NOT NULL DEFAULT 1,

    CONSTRAINT number_series_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT number_series_entity_fk FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT number_series_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT number_series_next_value_positive CHECK (next_value > 0),
    CONSTRAINT number_series_document_type_not_blank CHECK (btrim(document_type) <> ''),
    CONSTRAINT number_series_fiscal_period_not_blank CHECK (btrim(fiscal_period) <> '')
);

-- Every issued number is recorded, and the unique constraint makes a duplicate
-- impossible to store rather than merely unlikely.
CREATE TABLE config.issued_document_number (
    tenant_id       uuid NOT NULL,
    legal_entity_id uuid,
    outlet_id       uuid,
    document_type   text NOT NULL,
    fiscal_period   text NOT NULL,
    document_number text NOT NULL,
    issued_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT issued_document_number_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT issued_document_number_unique
        UNIQUE (tenant_id, document_type, fiscal_period, document_number)
);

-- One series per scope. Expressed as a unique index rather than a key because the
-- optional legal-entity and outlet columns are nullable, and NULLs would otherwise
-- defeat the uniqueness this is meant to guarantee.
CREATE UNIQUE INDEX number_series_scope_unique
    ON config.number_series (
        tenant_id, document_type, fiscal_period,
        coalesce(legal_entity_id, '00000000-0000-0000-0000-000000000000'::uuid),
        coalesce(outlet_id,       '00000000-0000-0000-0000-000000000000'::uuid));

COMMENT ON TABLE config.issued_document_number IS
    'Ledger of issued human document numbers. The unique constraint is the last line of '
    'defence: even a defective issuer cannot persist a duplicate.';

-- Issue the next number for a scope.
--
-- Collision safety comes from a single atomic UPDATE ... RETURNING. That statement takes
-- a row lock; a concurrent caller blocks and then re-reads the committed value, so two
-- sessions cannot both observe the same next_value. A read-then-write implementation
-- would lose updates under concurrency, which is exactly what the negative control plants.
CREATE FUNCTION config.issue_document_number(
    p_tenant_id       uuid,
    p_document_type   text,
    p_fiscal_period   text,
    p_legal_entity_id uuid DEFAULT NULL,
    p_outlet_id       uuid DEFAULT NULL
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_value  bigint;
    v_prefix text;
    v_number text;
BEGIN
    UPDATE config.number_series
    SET next_value = next_value + 1
    WHERE tenant_id = p_tenant_id
      AND document_type = p_document_type
      AND fiscal_period = p_fiscal_period
      AND coalesce(legal_entity_id, '00000000-0000-0000-0000-000000000000'::uuid)
          = coalesce(p_legal_entity_id, '00000000-0000-0000-0000-000000000000'::uuid)
      AND coalesce(outlet_id, '00000000-0000-0000-0000-000000000000'::uuid)
          = coalesce(p_outlet_id, '00000000-0000-0000-0000-000000000000'::uuid)
    RETURNING next_value - 1, prefix INTO v_value, v_prefix;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'NUMBER_SERIES_ABSENT: no series for % in %', p_document_type, p_fiscal_period
            USING ERRCODE = 'HS404';
    END IF;

    v_number := v_prefix || p_fiscal_period || '-' || lpad(v_value::text, 6, '0');

    INSERT INTO config.issued_document_number
        (tenant_id, legal_entity_id, outlet_id, document_type, fiscal_period, document_number)
    VALUES (p_tenant_id, p_legal_entity_id, p_outlet_id, p_document_type, p_fiscal_period, v_number);

    RETURN v_number;
END;
$$;

-- ===========================================================================
-- RETENTION (FR-DAT-018)
-- ===========================================================================

CREATE TYPE config.retention_action AS ENUM ('archive', 'purge');

CREATE TABLE config.retention_policy (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL,
    outlet_id     uuid,
    target_schema text NOT NULL,
    target_table  text NOT NULL,
    -- The column rows are aged by. Named explicitly rather than assumed: tables date
    -- their rows with whatever column suits them, and a hardcoded created_at would
    -- silently skip every table that does not have one.
    age_column    text NOT NULL,
    retain_for    interval NOT NULL,
    action        config.retention_action NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT retention_policy_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT retention_policy_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT retention_policy_retain_for_positive CHECK (retain_for > interval '0'),
    CONSTRAINT retention_policy_age_column_not_blank CHECK (btrim(age_column) <> ''),
    -- A retention policy may not name append-only storage at all. This is the first of
    -- three independent guards; the trigger on the audit tables is the last.
    CONSTRAINT retention_policy_never_targets_audit CHECK (lower(target_schema) <> 'audit'),
    CONSTRAINT retention_policy_unique UNIQUE (tenant_id, target_schema, target_table)
);

COMMENT ON CONSTRAINT retention_policy_never_targets_audit ON config.retention_policy IS
    'Audit storage is append-only and outside retention entirely (FR-DAT-018). A policy '
    'that names it cannot be stored, so it cannot be applied.';

-- A policy naming a table or column that does not exist would fail only when it next
-- ran, which could be months later. Validate it at the moment it is written.
CREATE FUNCTION config.assert_retention_target_exists() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF to_regclass(format('%I.%I', NEW.target_schema, NEW.target_table)) IS NULL THEN
        RAISE EXCEPTION 'RETENTION_TARGET_ABSENT: %.% does not exist',
            NEW.target_schema, NEW.target_table USING ERRCODE = 'HS404';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_attribute a
        WHERE a.attrelid = to_regclass(format('%I.%I', NEW.target_schema, NEW.target_table))
          AND a.attname = NEW.age_column AND a.attnum > 0 AND NOT a.attisdropped
    ) THEN
        RAISE EXCEPTION 'RETENTION_AGE_COLUMN_ABSENT: %.% has no column %',
            NEW.target_schema, NEW.target_table, NEW.age_column USING ERRCODE = 'HS404';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER retention_policy_target_valid
    BEFORE INSERT OR UPDATE ON config.retention_policy
    FOR EACH ROW EXECUTE FUNCTION config.assert_retention_target_exists();

CREATE FUNCTION config.apply_retention(p_tenant_id uuid)
RETURNS TABLE (target text, rows_affected bigint)
LANGUAGE plpgsql
AS $$
DECLARE
    r        record;
    v_count  bigint;
BEGIN
    FOR r IN
        SELECT * FROM config.retention_policy
        WHERE tenant_id = p_tenant_id
    LOOP
        -- Second guard. The CHECK above should make this unreachable; it is here because
        -- a guard that exists only in a constraint is one migration away from being gone.
        IF lower(r.target_schema) = 'audit' THEN
            RAISE EXCEPTION
                'APPEND_ONLY_VIOLATED: retention may not act on audit storage (%.%)',
                r.target_schema, r.target_table
                USING ERRCODE = 'HS403';
        END IF;

        EXECUTE format(
            'DELETE FROM %I.%I WHERE %I < now() - $1',
            r.target_schema, r.target_table, r.age_column) USING r.retain_for;
        GET DIAGNOSTICS v_count = ROW_COUNT;

        target := r.target_schema || '.' || r.target_table;
        rows_affected := v_count;
        RETURN NEXT;
    END LOOP;
END;
$$;

-- ===========================================================================
-- Row level security — ENABLE and FORCE on every tenant-scoped table
-- ===========================================================================

DO $$
DECLARE
    t record;
    outlet_scoped text[] := ARRAY[
        'configuration_version', 'policy', 'entitlement', 'retention_policy',
        'number_series', 'issued_document_number', 'security_event', 'operational_event'
    ];
BEGIN
    FOR t IN
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('config', 'audit') AND c.relkind = 'r'
    LOOP
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', t.schema_name, t.table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE  ROW LEVEL SECURITY', t.schema_name, t.table_name);

        IF t.table_name = ANY (outlet_scoped) THEN
            EXECUTE format(
                'CREATE POLICY %I ON %I.%I FOR ALL '
                'USING (app.row_in_scope(tenant_id, outlet_id)) '
                'WITH CHECK (app.row_in_scope(tenant_id, outlet_id))',
                t.table_name || '_isolation', t.schema_name, t.table_name);
        ELSE
            EXECUTE format(
                'CREATE POLICY %I ON %I.%I FOR ALL '
                'USING (app.row_in_scope(tenant_id, NULL::uuid)) '
                'WITH CHECK (app.row_in_scope(tenant_id, NULL::uuid))',
                t.table_name || '_isolation', t.schema_name, t.table_name);
        END IF;
    END LOOP;
END;
$$;

-- ===========================================================================
-- Grants
-- ===========================================================================

GRANT USAGE ON SCHEMA money, config, audit TO hospitality_app;

-- Configuration is read and written by the application.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA config TO hospitality_app;

-- Currency is immutable reference data: SELECT only. No INSERT, no UPDATE, no DELETE.
GRANT SELECT ON money.currency TO hospitality_app;

-- Audit is append-only for the application: INSERT and SELECT, never UPDATE or DELETE.
-- The triggers refuse mutation regardless; this makes the intent explicit in the grant
-- itself so a reviewer sees it without reading the trigger.
GRANT SELECT, INSERT ON audit.security_event, audit.operational_event TO hospitality_app;
REVOKE UPDATE, DELETE, TRUNCATE ON audit.security_event, audit.operational_event FROM hospitality_app;

GRANT USAGE ON ALL SEQUENCES IN SCHEMA audit TO hospitality_app;

GRANT EXECUTE ON FUNCTION
    money.apply_rate(money.amount_minor, money.percentage, money.rounding_mode),
    money.assert_currency_paired(),
    money.allocate(money.amount_minor, integer),
    config.effective_configuration(uuid, config.configuration_category, timestamptz),
    config.is_entitled(text, uuid),
    config.issue_document_number(uuid, text, text, uuid, uuid),
    config.apply_retention(uuid)
TO hospitality_app;

REVOKE CREATE ON SCHEMA money, config, audit FROM hospitality_app;
