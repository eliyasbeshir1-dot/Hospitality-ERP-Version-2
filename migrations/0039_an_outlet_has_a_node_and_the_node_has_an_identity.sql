-- 0039: an outlet has a continuity node, and the node has an identity
--
-- M5a is the first gate that builds a SECOND place where this system runs. Everything
-- before it assumed one database and one API, reachable or not. FR-EDG-001 says that
-- assumption is not permitted in production: every production Phase 1 outlet runs the
-- focused Outlet Continuity Node, and cloud-only operation is allowed only for
-- development, demonstration or explicitly non-production evaluation.
--
-- THAT SENTENCE IS A CONSTRAINT, NOT A DEPLOYMENT NOTE, so it is written as one. A
-- profile row that says `production` and `cloud_only` cannot exist — the check refuses it
-- at write time rather than a start-up script noticing later, because a start-up script
-- runs on the machine that is already wrong.
--
-- WHAT A NODE IS BOUND TO, AND WHY IT IS ONE OUTLET. FR-CFG-001E asks that the node be
-- registered, bound to one tenant and one outlet, configured, and proved to start ONLY
-- with the correct outlet identity. A node that could serve two outlets would be a
-- second answer to "whose orders are these", and this repository has spent four gates
-- removing second answers. So the binding is a column pair with a foreign key, one active
-- node per outlet, and edge.authenticate_node() refuses a fingerprint that belongs to
-- another outlet rather than falling back to the tenant.
--
-- THE FIVE SERVICES ARE NAMED IN THE REQUIREMENT, SO THEY ARE NAMED IN AN ENUM.
-- FR-EDG-002A: "the node image contains exactly the five named services". Exactly is two
-- claims, and an enum only makes one of them: it stops a sixth kind, and says nothing
-- about a missing fifth. Both halves are enforced — the enum bounds the set from above,
-- and edge.register_node() writes all five in the same statement while a trigger refuses
-- to let one be deleted afterwards. A node with four services is not a node with a
-- missing feature; it is a node that cannot honestly answer a readiness probe.
--
-- LEAST PRIVILEGE IS CHECKED AGAINST THE SERVER, NOT AGAINST A STRING. Each service
-- records the role it runs as, and a trigger asks PostgreSQL what that role actually is
-- when the role exists there. api/src/env.ts already refuses to start a privileged
-- runtime credential; this is the same refusal expressed where the inventory lives, so a
-- node cannot be REGISTERED with a superuser worker even if nobody ever starts it.
--
-- WHAT THIS MIGRATION DOES NOT DO. It does not synchronize anything, resolve a conflict,
-- queue a receipt or serve a surface. Those are 0040 onward and the node runtime. This
-- one establishes that the node exists, that it belongs to exactly one outlet, that its
-- service inventory is complete, that its identity can be proved, and that its health can
-- be asked for. Nothing here is reachable by a guest or a waiter; every writer is either
-- provisioning or the node's own principal.

CREATE SCHEMA edge;

COMMENT ON SCHEMA edge IS
    'The outlet continuity node: its registration, its binding to one outlet, its service '
    'inventory, its identity and its health. FR-EDG-001, FR-EDG-002A, FR-EDG-017, '
    'FR-EDG-018, FR-CFG-001E.';

-- ---------------------------------------------------------------------------
-- 1. THE VOCABULARY (FR-EDG-001, FR-EDG-002A, FR-EDG-009, FR-EDG-017)
-- ---------------------------------------------------------------------------

-- The environments the requirement distinguishes. `production` is the one that compels a
-- node; the other three are the exhaustive list of what FR-EDG-001 calls development,
-- demonstration and explicitly non-production evaluation. `pilot` is that last one under
-- the name this build has used for it since M4.
CREATE TYPE edge.environment_class AS ENUM (
    'production', 'pilot', 'demonstration', 'development');

CREATE TYPE edge.serving_mode AS ENUM ('continuity_node', 'cloud_only');

-- FR-EDG-002A names these five and no others.
CREATE TYPE edge.node_service_kind AS ENUM (
    'local_api', 'database', 'sync_worker', 'realtime_gateway', 'print_agent');

-- FR-EDG-009's three states, which staff and customers are both shown. They live here
-- rather than in the surface because a screen must not be the only place that knows what
-- states exist; 0041 is what moves a node between them.
CREATE TYPE edge.connectivity_state AS ENUM (
    'cloud_connected', 'local_continuity', 'reconciling');

-- FR-EDG-017's seven components, exposed to the outlet operator and to the cloud.
CREATE TYPE edge.health_component AS ENUM (
    'node', 'database', 'worker', 'print', 'storage', 'certificate', 'synchronization');

CREATE TYPE edge.health_state AS ENUM ('healthy', 'degraded', 'unhealthy');

-- ---------------------------------------------------------------------------
-- 2. THE DEPLOYMENT PROFILE (FR-EDG-001)
-- ---------------------------------------------------------------------------

CREATE TABLE edge.deployment_profile (
    tenant_id         uuid NOT NULL,
    outlet_id         uuid NOT NULL,
    environment_class edge.environment_class NOT NULL,
    serving_mode      edge.serving_mode      NOT NULL,

    -- WHY CLOUD-ONLY IS PERMITTED HERE, IN WORDS, WHEN IT IS PERMITTED AT ALL. The
    -- requirement allows the mode only for non-production evaluation, and an allowance
    -- with no stated reason is indistinguishable from an oversight six months later.
    non_production_reason text,

    declared_by_user_id uuid NOT NULL,
    declared_at         timestamptz NOT NULL DEFAULT now(),
    row_version         bigint NOT NULL DEFAULT 1,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT deployment_profile_pkey PRIMARY KEY (tenant_id, outlet_id),
    CONSTRAINT deployment_profile_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT deployment_profile_declarer_fk FOREIGN KEY (tenant_id, declared_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,

    -- THE REQUIREMENT, AS A CHECK. A production outlet running cloud-only cannot be
    -- recorded, so it cannot be deployed by anything that reads this table.
    CONSTRAINT deployment_profile_production_requires_the_node CHECK (
        serving_mode = 'continuity_node' OR environment_class <> 'production'),

    -- And the allowance is never silent.
    CONSTRAINT deployment_profile_cloud_only_is_explained CHECK (
        (serving_mode = 'cloud_only') = (non_production_reason IS NOT NULL)),

    CONSTRAINT deployment_profile_row_version_positive CHECK (row_version > 0)
);

COMMENT ON TABLE edge.deployment_profile IS
    'FR-EDG-001. What an outlet is permitted to run. A production outlet requires the '
    'continuity node; cloud-only exists for development, demonstration and explicitly '
    'non-production evaluation, and states its reason. The rule is a CHECK because a '
    'deployment script that enforced it would run on the machine that is already wrong.';

CREATE TRIGGER deployment_profile_row_version
    BEFORE UPDATE ON edge.deployment_profile
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

ALTER TABLE edge.deployment_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.deployment_profile FORCE ROW LEVEL SECURITY;
CREATE POLICY deployment_profile_isolation ON edge.deployment_profile FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 3. THE NODE (FR-CFG-001E, FR-EDG-018)
-- ---------------------------------------------------------------------------

CREATE TABLE edge.node (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,

    node_code text NOT NULL,

    -- DEVICE IDENTITY (FR-EDG-018). The node is a device in the org tree, the same way a
    -- POS terminal is, so the estate has one answer to "what hardware is at this outlet"
    -- rather than two registers that drift. The fingerprint is what the node PRESENTS;
    -- the private half never comes near this database, which is why the column is a
    -- digest and is named one.
    device_node_id       uuid NOT NULL,
    identity_fingerprint character(64) NOT NULL,

    -- The principal the node's services authenticate as. identity.principal_class already
    -- carries 'edge_node' and 'print_agent'; FR-SEC-014 said those exist only at M5a, and
    -- this is M5a.
    service_principal_id uuid NOT NULL,

    -- FR-EDG-004A's "configured endpoint": where the four screen families are served on
    -- the outlet network. Stored, not guessed, because a surface that has to discover its
    -- own address is a surface that will find the wrong one.
    lan_endpoint text NOT NULL,

    -- FR-EDG-018's encrypted secrets. This column holds a REFERENCE to where the node's
    -- secrets live on its own host, never a secret. A database that can be read is not a
    -- place to put the key that protects it.
    secret_store_reference text NOT NULL,

    -- The trust anchor signed updates are verified against (used by FR-OPS-010).
    update_trust_anchor_sha256 character(64) NOT NULL,

    -- FR-EDG-018's hardened host: what the node attested about itself at registration.
    host_hardening_profile text NOT NULL,

    status org.lifecycle_status NOT NULL DEFAULT 'active',

    registered_by_user_id uuid NOT NULL,
    registered_at         timestamptz NOT NULL DEFAULT now(),
    revoked_at            timestamptz,
    row_version           bigint NOT NULL DEFAULT 1,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT node_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT node_code_unique UNIQUE (tenant_id, node_code),
    CONSTRAINT node_fingerprint_unique UNIQUE (identity_fingerprint),
    CONSTRAINT node_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT node_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT node_device_fk FOREIGN KEY (tenant_id, device_node_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT node_principal_fk FOREIGN KEY (tenant_id, service_principal_id)
        REFERENCES identity.service_principal (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT node_registrar_fk FOREIGN KEY (tenant_id, registered_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT node_lan_endpoint_is_stated CHECK (length(trim(lan_endpoint)) > 0),
    CONSTRAINT node_revocation_matches_status CHECK (
        (revoked_at IS NULL) = (status = 'active')),
    CONSTRAINT node_row_version_positive CHECK (row_version > 0)
);

COMMENT ON TABLE edge.node IS
    'FR-CFG-001E, FR-EDG-018. One continuity node, bound to one tenant and one outlet, '
    'with a device identity it proves by fingerprint, a scoped service principal, the LAN '
    'endpoint it serves the four screen families at, a reference to where its secrets '
    'live (never a secret), the anchor its signed updates are verified against and what '
    'it attested about its host.';

-- ONE ACTIVE NODE PER OUTLET. Two would make "which node is authoritative here" a
-- question with two answers, which is the M5b split-brain this gate must not create.
CREATE UNIQUE INDEX node_one_active_per_outlet
    ON edge.node (tenant_id, outlet_id) WHERE status = 'active';

CREATE TRIGGER node_row_version
    BEFORE UPDATE ON edge.node
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

ALTER TABLE edge.node ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.node FORCE ROW LEVEL SECURITY;
CREATE POLICY node_isolation ON edge.node FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 4. THE SERVICE INVENTORY (FR-EDG-002A)
-- ---------------------------------------------------------------------------

CREATE TABLE edge.node_service (
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,
    node_id   uuid NOT NULL,
    service   edge.node_service_kind NOT NULL,

    -- The identity this service starts as. Checked against the server below.
    runs_as_role text NOT NULL,

    -- What the service listens on, where it listens on anything. The database and the two
    -- workers do not, and a column that forced them to would invite a fiction.
    listens_on text,

    started_under_least_privilege boolean NOT NULL DEFAULT true,
    recorded_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT node_service_pkey PRIMARY KEY (node_id, service),
    CONSTRAINT node_service_node_fk FOREIGN KEY (tenant_id, node_id)
        REFERENCES edge.node (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT node_service_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT node_service_role_is_stated CHECK (length(trim(runs_as_role)) > 0)
);

COMMENT ON TABLE edge.node_service IS
    'FR-EDG-002A. Exactly the five named services, and the role each starts as. The enum '
    'bounds the set from above and edge.register_node() fills it from below; a trigger '
    'refuses to let one be removed, because a node with four services cannot honestly '
    'answer a readiness probe.';

ALTER TABLE edge.node_service ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.node_service FORCE ROW LEVEL SECURITY;
CREATE POLICY node_service_isolation ON edge.node_service FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- LEAST PRIVILEGE, ASKED OF THE SERVER RATHER THAN OF THE CALLER.
--
-- api/src/env.ts refuses to START a privileged runtime credential. This refuses to
-- RECORD one, which closes the window where a node is registered with a superuser worker
-- and nobody notices until it runs. Roles that do not exist in this cluster are the
-- node's own OS accounts and cannot be interrogated here; they are accepted and the
-- claim is recorded as the node's, which is what `started_under_least_privilege` means.
CREATE FUNCTION edge.refuse_privileged_service_role()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
DECLARE
    v_violation text;
BEGIN
    SELECT CASE
             WHEN r.rolsuper      THEN 'is a superuser'
             WHEN r.rolbypassrls  THEN 'has BYPASSRLS'
             WHEN r.rolcreaterole THEN 'has CREATEROLE'
             WHEN r.rolcreatedb   THEN 'has CREATEDB'
           END
      INTO v_violation
      FROM pg_roles r
     WHERE r.rolname = NEW.runs_as_role;

    IF v_violation IS NOT NULL THEN
        RAISE EXCEPTION
            'NODE_SERVICE_ROLE_PRIVILEGED: % runs as %, which %',
            NEW.service, NEW.runs_as_role, v_violation
            USING ERRCODE = 'HS403';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER node_service_role_is_unprivileged
    BEFORE INSERT OR UPDATE ON edge.node_service
    FOR EACH ROW EXECUTE FUNCTION edge.refuse_privileged_service_role();

-- THE INVENTORY IS COMPLETE OR THE NODE IS NOT REGISTERED. Removing one service after
-- registration is refused for the same reason a fifth was required at registration.
CREATE FUNCTION edge.refuse_incomplete_service_inventory()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'NODE_SERVICE_INVENTORY_IMMUTABLE: the five services FR-EDG-002A names are '
        'written once, by edge.register_node(). Removing % would leave a node that '
        'cannot answer a readiness probe honestly', OLD.service
        USING ERRCODE = 'HS409';
END;
$$;

CREATE TRIGGER node_service_inventory_is_complete
    BEFORE DELETE ON edge.node_service
    FOR EACH ROW EXECUTE FUNCTION edge.refuse_incomplete_service_inventory();

-- ---------------------------------------------------------------------------
-- 5. HEALTH (FR-EDG-017)
-- ---------------------------------------------------------------------------

CREATE TABLE edge.node_health_sample (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,
    node_id   uuid NOT NULL,

    component edge.health_component NOT NULL,
    state     edge.health_state     NOT NULL,

    -- WHY IT IS NOT HEALTHY, WHEN IT IS NOT. FR-EDG-017 asks for health to be exposed
    -- TRUTHFULLY, and a state with no detail is a claim a reader cannot check.
    detail text,

    observed_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT node_health_sample_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT node_health_sample_node_fk FOREIGN KEY (tenant_id, node_id)
        REFERENCES edge.node (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT node_health_sample_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT node_health_sample_degradation_is_explained CHECK (
        state = 'healthy' OR detail IS NOT NULL)
);

COMMENT ON TABLE edge.node_health_sample IS
    'FR-EDG-017. What each of the seven components reported and when. Append-only: a '
    'health history that can be edited is not evidence, and the cloud operator reads the '
    'same rows the outlet operator does.';

CREATE INDEX node_health_sample_latest_idx
    ON edge.node_health_sample (tenant_id, node_id, component, observed_at DESC);

CREATE TRIGGER node_health_sample_is_append_only
    BEFORE UPDATE OR DELETE ON edge.node_health_sample
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

ALTER TABLE edge.node_health_sample ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.node_health_sample FORCE ROW LEVEL SECURITY;
CREATE POLICY node_health_sample_isolation ON edge.node_health_sample FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 6. AUDITED ADMINISTRATIVE ACCESS (FR-EDG-018)
-- ---------------------------------------------------------------------------

CREATE TABLE edge.node_admin_action (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,
    node_id   uuid NOT NULL,

    action_code   text NOT NULL,
    performed_by_user_id uuid NOT NULL,
    performed_at  timestamptz NOT NULL DEFAULT now(),
    detail        text,

    CONSTRAINT node_admin_action_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT node_admin_action_node_fk FOREIGN KEY (tenant_id, node_id)
        REFERENCES edge.node (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT node_admin_action_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT node_admin_action_actor_fk FOREIGN KEY (tenant_id, performed_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT node_admin_action_code_is_stated CHECK (length(trim(action_code)) > 0)
);

COMMENT ON TABLE edge.node_admin_action IS
    'FR-EDG-018. Administrative access to the node, named and attributed. Append-only, '
    'and separate from the cloud audit ledger because it must survive an outage that '
    'makes the cloud unreachable — an audit record that only exists when the network '
    'does is not an audit record.';

CREATE TRIGGER node_admin_action_is_append_only
    BEFORE UPDATE OR DELETE ON edge.node_admin_action
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

ALTER TABLE edge.node_admin_action ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.node_admin_action FORCE ROW LEVEL SECURITY;
CREATE POLICY node_admin_action_isolation ON edge.node_admin_action FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 7. REGISTRATION — THE ONLY WRITER OF A NODE (FR-CFG-001E, FR-EDG-001, FR-EDG-002A)
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.register_node(
    p_tenant_id             uuid,
    p_outlet_id             uuid,
    p_node_code             text,
    p_device_node_id        uuid,
    p_identity_fingerprint  character(64),
    p_service_principal_id  uuid,
    p_lan_endpoint          text,
    p_secret_store_reference text,
    p_update_trust_anchor_sha256 character(64),
    p_host_hardening_profile text,
    p_registered_by_user_id uuid,
    p_service_roles         jsonb)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'org', 'identity', 'public'
AS $$
DECLARE
    v_profile edge.deployment_profile%ROWTYPE;
    v_node_id uuid;
    v_class   identity.principal_class;
    v_missing text;
BEGIN
    -- The outlet must be an outlet. A node bound to a dining table is not a
    -- misconfiguration anybody would notice from the node's own logs.
    PERFORM 1 FROM org.org_node
      WHERE tenant_id = p_tenant_id AND id = p_outlet_id AND kind = 'outlet';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'NODE_OUTLET_UNKNOWN: % is not an outlet of this tenant', p_outlet_id
            USING ERRCODE = 'HS404';
    END IF;

    -- FR-EDG-001. A node may only be registered where the profile expects one, and the
    -- profile must exist: an outlet nobody has declared a deployment for is not an outlet
    -- a node should quietly appear at.
    SELECT * INTO v_profile FROM edge.deployment_profile
      WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'DEPLOYMENT_PROFILE_ABSENT: outlet % has no declared deployment profile, so '
            'whether it may run a continuity node is unanswered', p_outlet_id
            USING ERRCODE = 'HS409';
    END IF;
    IF v_profile.serving_mode <> 'continuity_node' THEN
        RAISE EXCEPTION
            'DEPLOYMENT_PROFILE_IS_CLOUD_ONLY: outlet % is declared % / %, and a node '
            'registered against it would contradict the profile it is deployed under',
            p_outlet_id, v_profile.environment_class, v_profile.serving_mode
            USING ERRCODE = 'HS409';
    END IF;

    -- The principal must be the node's own class. FR-SEC-014 scopes principals by class,
    -- and a node authenticating as an integration principal would carry an integration's
    -- grants.
    SELECT class INTO v_class FROM identity.service_principal
      WHERE tenant_id = p_tenant_id AND id = p_service_principal_id;
    IF v_class IS NULL THEN
        RAISE EXCEPTION 'NODE_PRINCIPAL_UNKNOWN: no such service principal'
            USING ERRCODE = 'HS404';
    END IF;
    IF v_class <> 'edge_node' THEN
        RAISE EXCEPTION
            'NODE_PRINCIPAL_WRONG_CLASS: the principal is a %, and a node must '
            'authenticate as an edge_node', v_class
            USING ERRCODE = 'HS403';
    END IF;

    -- FR-EDG-002A. Every one of the five, named, before anything is written. Refusing
    -- here rather than after the node row exists is what stops a half-registered node.
    SELECT string_agg(kind::text, ', ' ORDER BY kind)
      INTO v_missing
      FROM unnest(enum_range(NULL::edge.node_service_kind)) AS kind
     WHERE NOT (p_service_roles ? kind::text);
    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION
            'NODE_SERVICE_INVENTORY_INCOMPLETE: no role given for %. FR-EDG-002A asks for '
            'exactly five services, and four is not five', v_missing
            USING ERRCODE = 'HS422';
    END IF;

    INSERT INTO edge.node (
        tenant_id, outlet_id, node_code, device_node_id, identity_fingerprint,
        service_principal_id, lan_endpoint, secret_store_reference,
        update_trust_anchor_sha256, host_hardening_profile, registered_by_user_id)
    VALUES (
        p_tenant_id, p_outlet_id, p_node_code, p_device_node_id, p_identity_fingerprint,
        p_service_principal_id, p_lan_endpoint, p_secret_store_reference,
        p_update_trust_anchor_sha256, p_host_hardening_profile, p_registered_by_user_id)
    RETURNING id INTO v_node_id;

    -- All five in one statement, so there is no moment at which the inventory is partial.
    INSERT INTO edge.node_service (tenant_id, outlet_id, node_id, service, runs_as_role)
    SELECT p_tenant_id, p_outlet_id, v_node_id, kind,
           p_service_roles ->> kind::text
      FROM unnest(enum_range(NULL::edge.node_service_kind)) AS kind;

    INSERT INTO edge.node_admin_action (
        tenant_id, outlet_id, node_id, action_code, performed_by_user_id, detail)
    VALUES (p_tenant_id, p_outlet_id, v_node_id, 'node.register', p_registered_by_user_id,
            format('bound to outlet %s under %s', p_outlet_id, v_profile.environment_class));

    RETURN v_node_id;
END;
$$;

COMMENT ON FUNCTION edge.register_node(uuid, uuid, text, uuid, character, uuid, text, text,
                                       character, text, uuid, jsonb) IS
    'FR-CFG-001E, FR-EDG-001, FR-EDG-002A. The only writer of a node. Refuses an outlet '
    'that is not one, an outlet with no declared profile, a profile that says cloud-only, '
    'a principal of the wrong class, and a service inventory short of all five.';

-- ---------------------------------------------------------------------------
-- 8. STARTING ONLY WITH THE CORRECT OUTLET IDENTITY (FR-CFG-001E)
-- ---------------------------------------------------------------------------

-- The half of FR-CFG-001E that a registration function cannot prove: that the node
-- STARTS only where it belongs. The node presents its code and fingerprint and names the
-- outlet it believes it serves; this refuses every disagreement separately, because
-- "wrong outlet" and "wrong fingerprint" are different failures and an operator reading
-- one message should not have to guess which happened.
CREATE FUNCTION edge.authenticate_node(
    p_tenant_id            uuid,
    p_node_code            text,
    p_identity_fingerprint character(64),
    p_claimed_outlet_id    uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
DECLARE
    n edge.node%ROWTYPE;
BEGIN
    SELECT * INTO n FROM edge.node
      WHERE tenant_id = p_tenant_id AND node_code = p_node_code;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'NODE_UNKNOWN: no node % is registered for this tenant', p_node_code
            USING ERRCODE = 'HS404';
    END IF;
    IF n.status <> 'active' THEN
        RAISE EXCEPTION 'NODE_REVOKED: node % was revoked at %', p_node_code, n.revoked_at
            USING ERRCODE = 'HS403';
    END IF;
    IF n.identity_fingerprint <> p_identity_fingerprint THEN
        RAISE EXCEPTION
            'NODE_IDENTITY_MISMATCH: the fingerprint presented is not the one registered '
            'for %', p_node_code
            USING ERRCODE = 'HS403';
    END IF;
    -- THE OUTLET BINDING IS NOT A DEFAULT. A node that starts believing it serves a
    -- sibling outlet is refused rather than corrected, because correcting it silently is
    -- how one outlet's orders end up under another's roof.
    IF n.outlet_id <> p_claimed_outlet_id THEN
        RAISE EXCEPTION
            'NODE_OUTLET_MISMATCH: node % is bound to outlet %, and started claiming %',
            p_node_code, n.outlet_id, p_claimed_outlet_id
            USING ERRCODE = 'HS403';
    END IF;
    RETURN n.id;
END;
$$;

COMMENT ON FUNCTION edge.authenticate_node(uuid, text, character, uuid) IS
    'FR-CFG-001E. Proves a node starts only with the correct outlet identity. Unknown, '
    'revoked, wrong fingerprint and wrong outlet are four refusals, not one, because an '
    'operator should not have to guess which of them happened.';

-- ---------------------------------------------------------------------------
-- 9. HEALTH, RECORDED AND READ (FR-EDG-017)
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.record_health(
    p_tenant_id uuid,
    p_node_id   uuid,
    p_component edge.health_component,
    p_state     edge.health_state,
    p_detail    text DEFAULT NULL)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
DECLARE
    v_outlet uuid;
    v_id     uuid;
BEGIN
    SELECT outlet_id INTO v_outlet FROM edge.node
      WHERE tenant_id = p_tenant_id AND id = p_node_id;
    IF v_outlet IS NULL THEN
        RAISE EXCEPTION 'NODE_UNKNOWN: no such node' USING ERRCODE = 'HS404';
    END IF;

    INSERT INTO edge.node_health_sample (
        tenant_id, outlet_id, node_id, component, state, detail)
    VALUES (p_tenant_id, v_outlet, p_node_id, p_component, p_state, p_detail)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

-- WHAT THE OPERATOR SEES. Every one of the seven components, whether or not a sample has
-- ever been taken — a component missing from a health report reads as healthy, and the
-- one that has never reported is exactly the one worth knowing about.
CREATE FUNCTION edge.node_health(p_tenant_id uuid, p_node_id uuid)
RETURNS TABLE (
    component   edge.health_component,
    state       edge.health_state,
    detail      text,
    observed_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
    SELECT c.component,
           COALESCE(s.state, 'unhealthy'::edge.health_state),
           COALESCE(s.detail, 'no sample has ever been recorded for this component'),
           s.observed_at
      FROM unnest(enum_range(NULL::edge.health_component)) AS c(component)
      LEFT JOIN LATERAL (
           SELECT h.state, h.detail, h.observed_at
             FROM edge.node_health_sample h
            WHERE h.tenant_id = p_tenant_id
              AND h.node_id   = p_node_id
              AND h.component = c.component
            ORDER BY h.observed_at DESC
            LIMIT 1) s ON true
     ORDER BY c.component;
$$;

COMMENT ON FUNCTION edge.node_health(uuid, uuid) IS
    'FR-EDG-017. All seven components, always. A component that has never reported is '
    'returned unhealthy and says so, because a missing row in a health report reads as '
    'healthy to every human being who has ever read one.';

-- ---------------------------------------------------------------------------
-- 10. GRANTS
-- ---------------------------------------------------------------------------

GRANT USAGE ON SCHEMA edge TO hospitality_app;

GRANT SELECT ON edge.deployment_profile   TO hospitality_app;
GRANT SELECT ON edge.node                 TO hospitality_app;
GRANT SELECT ON edge.node_service         TO hospitality_app;
GRANT SELECT ON edge.node_health_sample   TO hospitality_app;
GRANT SELECT ON edge.node_admin_action    TO hospitality_app;

-- The application reads the estate and records health; it does not register nodes. A node
-- comes into being through provisioning, the same way a tenant does, because registering
-- one is an act with a signature and an operator behind it rather than a request.
GRANT EXECUTE ON FUNCTION edge.authenticate_node(uuid, text, character, uuid)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.record_health(uuid, uuid, edge.health_component,
                                             edge.health_state, text) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.node_health(uuid, uuid) TO hospitality_app;
