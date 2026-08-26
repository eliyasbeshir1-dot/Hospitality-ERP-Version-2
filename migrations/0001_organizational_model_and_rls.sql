-- 0001_organizational_model_and_rls.sql
--
-- Gate:        M1, slice A
-- Requirements: FR-DAT-001 FR-DAT-002 FR-DAT-003 FR-DAT-004 FR-DAT-007 FR-DAT-009
--               FR-TEN-001 FR-TEN-002A FR-SEC-001 FR-SEC-002A FR-DAT-017 FR-OPS-020
--
-- First migration of this repository. No migration history is inherited from the
-- frozen v1.1 prototype (FR-DAT-001, FR-GOV-006).
--
-- Scope note: this slice creates the organizational model and its isolation policy
-- ONLY. Identity, memberships and sessions are M1-B. Configuration, audit and
-- money/quantity types are M1-C. No storage-location entity exists here or at any
-- later gate (FR-TEN-002B).
--
-- Forward-only. Once applied, this file is checksum-locked and must never be edited
-- (FR-DAT-016).

-- ---------------------------------------------------------------------------
-- Schemas
-- ---------------------------------------------------------------------------

CREATE SCHEMA app;      -- context accessors and shared trigger functions
CREATE SCHEMA org;      -- organizational model

COMMENT ON SCHEMA app IS 'Request-context accessors and shared trigger functions.';
COMMENT ON SCHEMA org IS 'Phase 1 organizational model (FR-TEN-002A).';

-- The public schema is not used. Deny object creation there outright.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- Request context (FR-SEC-001 — deny by default)
-- ---------------------------------------------------------------------------
-- Context arrives as session GUCs set by the caller. An unset, empty or malformed
-- value yields NULL, and every policy treats NULL as "no access". Failing to parse
-- is therefore fail-closed, never fail-open.
--
-- At M1-A the context is (tenant, outlet). Session and actor context are added at
-- M1-B, when identity exists; the policies below are written so that adding them
-- narrows access further and can never widen it.

CREATE FUNCTION app.current_tenant_id() RETURNS uuid
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN nullif(current_setting('app.tenant_id', true), '')::uuid;
EXCEPTION WHEN others THEN
    RETURN NULL;   -- malformed context is no context
END;
$$;

CREATE FUNCTION app.current_outlet_id() RETURNS uuid
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN nullif(current_setting('app.outlet_id', true), '')::uuid;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION app.current_tenant_id() IS
    'Tenant context, or NULL when unset/malformed. NULL denies all access.';
COMMENT ON FUNCTION app.current_outlet_id() IS
    'Outlet context, or NULL when unset/malformed. NULL denies all outlet-scoped access.';

-- Single source of truth for the isolation predicate. Every outlet-scoped table
-- uses this function, so an outlet-scoped table cannot silently be given a
-- tenant-only policy (NC-M1-003 gates that in CI).
CREATE FUNCTION app.row_in_scope(row_tenant_id uuid, row_outlet_id uuid)
RETURNS boolean
LANGUAGE sql STABLE
AS $$
    SELECT app.current_tenant_id() IS NOT NULL
       AND row_tenant_id = app.current_tenant_id()
       AND (
             row_outlet_id IS NULL
             OR (app.current_outlet_id() IS NOT NULL
                 AND row_outlet_id = app.current_outlet_id())
           );
$$;

COMMENT ON FUNCTION app.row_in_scope(uuid, uuid) IS
    'Tenant and outlet isolation predicate (FR-TEN-001, FR-SEC-002A). '
    'Rows above the outlet boundary carry NULL outlet_id and need tenant context only.';

-- ---------------------------------------------------------------------------
-- Shared enums
-- ---------------------------------------------------------------------------

CREATE TYPE org.lifecycle_status AS ENUM ('active', 'inactive', 'archived');

COMMENT ON TYPE org.lifecycle_status IS
    'Soft lifecycle (FR-DAT-009). Records are deactivated or archived, never deleted, '
    'so historical references stay resolvable.';

-- Kinds of organizational node. Depth is NOT implied by this list: any node may
-- nest under any other (subject to the outlet-boundary rule below), and queries
-- traverse org.org_closure rather than assuming a fixed number of levels
-- (FR-TEN-002A).
CREATE TYPE org.node_kind AS ENUM (
    'brand',
    'legal_entity',
    'outlet',
    'service_area',
    'preparation_station',
    'dining_table',
    'device'
);

-- ---------------------------------------------------------------------------
-- Shared trigger functions
-- ---------------------------------------------------------------------------

-- Optimistic concurrency (FR-DAT-007). The caller supplies the version it expects
-- in the UPDATE; a mismatch raises an explicit, distinguishable conflict rather
-- than silently overwriting.
CREATE FUNCTION app.enforce_row_version() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.row_version IS DISTINCT FROM OLD.row_version THEN
        RAISE EXCEPTION
            'VERSION_CONFLICT on %.% id=%: caller expected version %, current version is %',
            TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id, NEW.row_version, OLD.row_version
            USING ERRCODE = 'HS409';
    END IF;
    NEW.row_version := OLD.row_version + 1;
    NEW.updated_at  := now();          -- server time is authoritative (FR-DAT-004)
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION app.enforce_row_version() IS
    'FR-DAT-007. Raises SQLSTATE HS409 (VERSION_CONFLICT) on a stale expected version.';

-- Timezone validation. Expressed as a trigger rather than a CHECK because
-- pg_timezone_names is not immutable and must not be frozen into a constraint.
CREATE FUNCTION app.assert_valid_timezone() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_timezone_names WHERE name = NEW.timezone) THEN
        RAISE EXCEPTION 'INVALID_TIMEZONE: % is not a recognised IANA timezone', NEW.timezone
            USING ERRCODE = 'HS422';
    END IF;
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- org.tenant — the isolation root
-- ---------------------------------------------------------------------------

CREATE TABLE org.tenant (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),   -- opaque (FR-DAT-003)
    tenant_code     text NOT NULL,                                -- human number, separate column
    display_name    text NOT NULL,
    status          org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version     bigint NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),           -- UTC instant (FR-DAT-004)
    updated_at      timestamptz NOT NULL DEFAULT now(),
    deactivated_at  timestamptz,
    archived_at     timestamptz,

    CONSTRAINT tenant_code_unique UNIQUE (tenant_code),
    CONSTRAINT tenant_code_not_blank CHECK (btrim(tenant_code) <> ''),
    CONSTRAINT tenant_display_name_not_blank CHECK (btrim(display_name) <> ''),
    CONSTRAINT tenant_row_version_positive CHECK (row_version > 0),
    CONSTRAINT tenant_lifecycle_consistent CHECK (
        (status = 'active'   AND deactivated_at IS NULL     AND archived_at IS NULL)
     OR (status = 'inactive' AND deactivated_at IS NOT NULL AND archived_at IS NULL)
     OR (status = 'archived' AND archived_at IS NOT NULL)
    )
);

COMMENT ON TABLE org.tenant IS
    'Isolation root. Every tenant-owned row references exactly one tenant (FR-TEN-001).';
COMMENT ON COLUMN org.tenant.tenant_code IS
    'Human-facing code. Never used as a key; the opaque id is (FR-DAT-003).';

CREATE TRIGGER tenant_row_version
    BEFORE UPDATE ON org.tenant
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

-- ---------------------------------------------------------------------------
-- org.org_node — brands, legal entities, outlets, service areas,
--                preparation stations, dining tables and devices
-- ---------------------------------------------------------------------------
-- One table, self-referencing, arbitrary depth (FR-TEN-002A). There is no level
-- column and no query in this migration assumes a number of levels.
--
-- outlet_id is the nearest ancestor-or-self of kind 'outlet', or NULL for nodes
-- that sit above the outlet boundary (brands, legal entities). It is derived by
-- trigger, never supplied by the caller.

CREATE TABLE org.org_node (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    parent_id       uuid,
    outlet_id       uuid,
    kind            org.node_kind NOT NULL,
    reference_code  text NOT NULL,                                -- human number
    display_name    text NOT NULL,
    status          org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version     bigint NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    deactivated_at  timestamptz,
    archived_at     timestamptz,

    -- Composite uniqueness so tenant-qualified foreign keys are possible.
    CONSTRAINT org_node_tenant_id_unique UNIQUE (tenant_id, id),

    CONSTRAINT org_node_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,

    -- A child can never point at a parent in another tenant (FR-DAT-002).
    CONSTRAINT org_node_parent_fk FOREIGN KEY (tenant_id, parent_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,

    -- An outlet reference can never cross tenants either.
    CONSTRAINT org_node_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT org_node_not_own_parent CHECK (parent_id IS DISTINCT FROM id),
    CONSTRAINT org_node_outlet_is_self CHECK (kind <> 'outlet' OR outlet_id = id),
    CONSTRAINT org_node_reference_code_not_blank CHECK (btrim(reference_code) <> ''),
    CONSTRAINT org_node_display_name_not_blank CHECK (btrim(display_name) <> ''),
    CONSTRAINT org_node_row_version_positive CHECK (row_version > 0),
    CONSTRAINT org_node_lifecycle_consistent CHECK (
        (status = 'active'   AND deactivated_at IS NULL     AND archived_at IS NULL)
     OR (status = 'inactive' AND deactivated_at IS NOT NULL AND archived_at IS NULL)
     OR (status = 'archived' AND archived_at IS NOT NULL)
    ),
    CONSTRAINT org_node_reference_code_unique UNIQUE (tenant_id, kind, reference_code)
);

COMMENT ON TABLE org.org_node IS
    'Organizational hierarchy of configurable depth (FR-TEN-002A). No fixed-level '
    'assumption: traverse org.org_closure rather than joining a fixed number of parents.';
COMMENT ON COLUMN org.org_node.outlet_id IS
    'Nearest ancestor-or-self outlet; NULL above the outlet boundary. Derived by trigger. '
    'Presence of this column obliges the table to carry an outlet-aware policy (NC-M1-003).';

CREATE INDEX org_node_tenant_kind_idx   ON org.org_node (tenant_id, kind);
CREATE INDEX org_node_parent_idx        ON org.org_node (tenant_id, parent_id);
CREATE INDEX org_node_outlet_idx        ON org.org_node (tenant_id, outlet_id);

-- ---------------------------------------------------------------------------
-- org.org_closure — ancestor/descendant pairs at every depth
-- ---------------------------------------------------------------------------
-- Lets a query reach any ancestor or descendant without knowing how deep the
-- hierarchy is. This is what makes "configurable depth" true of queries and not
-- only of the schema.

CREATE TABLE org.org_closure (
    tenant_id     uuid NOT NULL,
    ancestor_id   uuid NOT NULL,
    descendant_id uuid NOT NULL,
    outlet_id     uuid,                 -- descendant's outlet; mirrors org_node
    depth         integer NOT NULL,

    PRIMARY KEY (ancestor_id, descendant_id),

    CONSTRAINT org_closure_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT org_closure_ancestor_fk FOREIGN KEY (tenant_id, ancestor_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT org_closure_descendant_fk FOREIGN KEY (tenant_id, descendant_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT org_closure_depth_non_negative CHECK (depth >= 0),
    CONSTRAINT org_closure_self_is_depth_zero CHECK (
        (ancestor_id = descendant_id) = (depth = 0)
    )
);

COMMENT ON TABLE org.org_closure IS
    'Transitive closure of org.org_node, maintained by trigger. Depth 0 is the self row.';

CREATE INDEX org_closure_descendant_idx ON org.org_closure (tenant_id, descendant_id);
CREATE INDEX org_closure_outlet_idx     ON org.org_closure (tenant_id, outlet_id);

-- ---------------------------------------------------------------------------
-- org.outlet_profile — outlet timezone context (FR-DAT-004)
-- ---------------------------------------------------------------------------

CREATE TABLE org.outlet_profile (
    outlet_id     uuid PRIMARY KEY,
    tenant_id     uuid NOT NULL,
    timezone      text NOT NULL,
    row_version   bigint NOT NULL DEFAULT 1,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT outlet_profile_node_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT outlet_profile_row_version_positive CHECK (row_version > 0),
    CONSTRAINT outlet_profile_timezone_not_blank CHECK (btrim(timezone) <> '')
);

COMMENT ON TABLE org.outlet_profile IS
    'Outlet timezone context. Instants are stored UTC; this supplies the local '
    'rendering context required by FR-DAT-004.';

CREATE TRIGGER outlet_profile_timezone_valid
    BEFORE INSERT OR UPDATE ON org.outlet_profile
    FOR EACH ROW EXECUTE FUNCTION app.assert_valid_timezone();

-- ---------------------------------------------------------------------------
-- org.device_registration — registered device attributes
-- ---------------------------------------------------------------------------
-- The device itself is an org_node of kind 'device'; this carries its
-- registration attributes. No credential, secret or principal is stored here —
-- device identity and authentication are M1-B.

CREATE TABLE org.device_registration (
    device_id        uuid PRIMARY KEY,
    tenant_id        uuid NOT NULL,
    outlet_id        uuid NOT NULL,
    registration_code text NOT NULL,          -- human number
    registered_at    timestamptz NOT NULL DEFAULT now(),
    row_version      bigint NOT NULL DEFAULT 1,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT device_registration_node_fk FOREIGN KEY (tenant_id, device_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT device_registration_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT device_registration_code_unique UNIQUE (tenant_id, registration_code),
    CONSTRAINT device_registration_row_version_positive CHECK (row_version > 0)
);

COMMENT ON TABLE org.device_registration IS
    'Registered device attributes. Device authentication and service principals are M1-B.';

-- ---------------------------------------------------------------------------
-- Hierarchy maintenance
-- ---------------------------------------------------------------------------

-- Derive outlet_id and reject an outlet nested inside another outlet.
--
-- The outlet is the isolation boundary for the whole RLS model, so it must be
-- unambiguous. This is a containment rule, not a depth rule: any kind may still
-- nest under any other, to any depth.
CREATE FUNCTION org.derive_outlet_id() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    ancestor_outlet uuid;
BEGIN
    IF NEW.parent_id IS NULL THEN
        ancestor_outlet := NULL;
    ELSE
        SELECT p.outlet_id INTO ancestor_outlet
        FROM org.org_node p
        WHERE p.id = NEW.parent_id AND p.tenant_id = NEW.tenant_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'PARENT_NOT_VISIBLE: parent % is not visible in this context',
                NEW.parent_id USING ERRCODE = 'HS404';
        END IF;
    END IF;

    IF NEW.kind = 'outlet' THEN
        IF ancestor_outlet IS NOT NULL THEN
            RAISE EXCEPTION
                'OUTLET_NESTED_IN_OUTLET: an outlet may not be nested inside outlet %',
                ancestor_outlet USING ERRCODE = 'HS409';
        END IF;
        NEW.outlet_id := NEW.id;
    ELSE
        NEW.outlet_id := ancestor_outlet;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER org_node_derive_outlet
    BEFORE INSERT OR UPDATE OF parent_id, kind ON org.org_node
    FOR EACH ROW EXECUTE FUNCTION org.derive_outlet_id();

CREATE TRIGGER org_node_row_version
    BEFORE UPDATE ON org.org_node
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

-- Maintain the closure on insert.
CREATE FUNCTION org.maintain_closure_insert() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO org.org_closure (tenant_id, ancestor_id, descendant_id, outlet_id, depth)
    VALUES (NEW.tenant_id, NEW.id, NEW.id, NEW.outlet_id, 0);

    IF NEW.parent_id IS NOT NULL THEN
        INSERT INTO org.org_closure (tenant_id, ancestor_id, descendant_id, outlet_id, depth)
        SELECT NEW.tenant_id, c.ancestor_id, NEW.id, NEW.outlet_id, c.depth + 1
        FROM org.org_closure c
        WHERE c.descendant_id = NEW.parent_id AND c.tenant_id = NEW.tenant_id;
    END IF;

    RETURN NULL;
END;
$$;

CREATE TRIGGER org_node_closure_insert
    AFTER INSERT ON org.org_node
    FOR EACH ROW EXECUTE FUNCTION org.maintain_closure_insert();

-- Maintain the closure when a node is reparented, and refuse to create a cycle.
CREATE FUNCTION org.maintain_closure_reparent() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.parent_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM org.org_closure
        WHERE ancestor_id = NEW.id AND descendant_id = NEW.parent_id
    ) THEN
        RAISE EXCEPTION 'ORG_CYCLE: node % may not be reparented beneath its own descendant %',
            NEW.id, NEW.parent_id USING ERRCODE = 'HS409';
    END IF;

    -- Detach the moved subtree from its former ancestors.
    DELETE FROM org.org_closure
    WHERE descendant_id IN (SELECT descendant_id FROM org.org_closure WHERE ancestor_id = NEW.id)
      AND ancestor_id NOT IN (SELECT descendant_id FROM org.org_closure WHERE ancestor_id = NEW.id);

    -- Reattach it beneath the new parent, at every depth.
    IF NEW.parent_id IS NOT NULL THEN
        INSERT INTO org.org_closure (tenant_id, ancestor_id, descendant_id, outlet_id, depth)
        SELECT NEW.tenant_id, sup.ancestor_id, sub.descendant_id, sub.outlet_id,
               sup.depth + sub.depth + 1
        FROM org.org_closure sup
        CROSS JOIN org.org_closure sub
        WHERE sup.descendant_id = NEW.parent_id
          AND sub.ancestor_id   = NEW.id;
    END IF;

    -- The moved subtree may have crossed an outlet boundary.
    UPDATE org.org_closure c
    SET outlet_id = n.outlet_id
    FROM org.org_node n
    WHERE c.descendant_id = n.id
      AND c.descendant_id IN (SELECT descendant_id FROM org.org_closure WHERE ancestor_id = NEW.id);

    RETURN NULL;
END;
$$;

CREATE TRIGGER org_node_closure_reparent
    AFTER UPDATE OF parent_id ON org.org_node
    FOR EACH ROW WHEN (OLD.parent_id IS DISTINCT FROM NEW.parent_id)
    EXECUTE FUNCTION org.maintain_closure_reparent();

-- ---------------------------------------------------------------------------
-- Row level security (FR-TEN-001, FR-SEC-001, FR-SEC-002A)
-- ---------------------------------------------------------------------------
-- ENABLE turns policies on. FORCE applies them to the table owner too, so the
-- migration role gets no implicit read path either. Every policy is FOR ALL with
-- both USING and WITH CHECK, so SELECT, INSERT, UPDATE and DELETE are all covered
-- by the same predicate — there is no verb left open.

ALTER TABLE org.tenant              ENABLE ROW LEVEL SECURITY;
ALTER TABLE org.tenant              FORCE  ROW LEVEL SECURITY;
ALTER TABLE org.org_node            ENABLE ROW LEVEL SECURITY;
ALTER TABLE org.org_node            FORCE  ROW LEVEL SECURITY;
ALTER TABLE org.org_closure         ENABLE ROW LEVEL SECURITY;
ALTER TABLE org.org_closure         FORCE  ROW LEVEL SECURITY;
ALTER TABLE org.outlet_profile      ENABLE ROW LEVEL SECURITY;
ALTER TABLE org.outlet_profile      FORCE  ROW LEVEL SECURITY;
ALTER TABLE org.device_registration ENABLE ROW LEVEL SECURITY;
ALTER TABLE org.device_registration FORCE  ROW LEVEL SECURITY;

-- The tenant row itself is visible only to its own tenant context.
CREATE POLICY tenant_isolation ON org.tenant
    FOR ALL
    USING      (app.current_tenant_id() IS NOT NULL AND id = app.current_tenant_id())
    WITH CHECK (app.current_tenant_id() IS NOT NULL AND id = app.current_tenant_id());

CREATE POLICY org_node_isolation ON org.org_node
    FOR ALL
    USING      (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

CREATE POLICY org_closure_isolation ON org.org_closure
    FOR ALL
    USING      (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

CREATE POLICY outlet_profile_isolation ON org.outlet_profile
    FOR ALL
    USING      (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

CREATE POLICY device_registration_isolation ON org.device_registration
    FOR ALL
    USING      (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- Grants (FR-DAT-017, FR-OPS-020)
-- ---------------------------------------------------------------------------
-- hospitality_app is the runtime identity: DML on the model, nothing else. It
-- holds no DDL right, no ownership, no BYPASSRLS and no privilege on the
-- migration history.

GRANT USAGE ON SCHEMA app, org TO hospitality_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    org.tenant,
    org.org_node,
    org.org_closure,
    org.outlet_profile,
    org.device_registration
TO hospitality_app;

GRANT EXECUTE ON FUNCTION
    app.current_tenant_id(),
    app.current_outlet_id(),
    app.row_in_scope(uuid, uuid)
TO hospitality_app;

-- Explicitly withheld: CREATE on either schema, and any access to the migration
-- history in schema migration.
REVOKE CREATE ON SCHEMA app, org FROM hospitality_app;
