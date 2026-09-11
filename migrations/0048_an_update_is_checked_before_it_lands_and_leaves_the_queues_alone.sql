-- 0048: an update is checked before it lands, and rolling it back leaves the queues alone
--
-- FR-OPS-010: "signed application/node updates, database compatibility checks, staged
-- rollout and rollback without corrupting local queues." The gate-local behaviour is the
-- last three quarters of that sentence — apply with a compatibility check, roll back
-- without corrupting the outbox or inbox.
--
-- WHAT "SIGNED" CAN AND CANNOT MEAN HERE, SAID PLAINLY BEFORE ANYTHING ELSE.
--
-- This database has no pgcrypto. There is no hmac(), no asymmetric verification, and
-- nothing that could check a real detached signature. What core PostgreSQL offers is
-- sha256(), and what can honestly be built with it is a KEYED DIGEST: the publisher
-- presents sha256(artifact_digest || the node's trust anchor), and a publisher who does
-- not know the anchor cannot produce it.
--
-- That is a real check and it is not a signature scheme. It proves the publisher knew a
-- shared secret; it does not prove who they were, it is not resistant to anyone who has
-- ever read the anchor, and it has the length-extension weakness every naive keyed digest
-- has. A production deployment verifies an asymmetric signature over the bundle BEFORE the
-- bytes reach the node at all, and this check is the second of two rather than the only
-- one. planning/M5A_FINDINGS.md carries that bound with the shape of what closes it.
--
-- The alternative was to let a tool verify and have the database record that it did, which
-- is the shape 0034 was written to remove: "record what the agent did rather than what the
-- caller claimed". A refusal the database can make itself is worth more than a claim it
-- stores, even when the refusal is weaker than the one a real deployment makes.
--
-- WHY THE QUEUE DEPTHS ARE RECORDED AT EVERY TRANSITION. "Rollback without corrupting
-- local queues" is a property nobody can check after the fact unless somebody wrote down
-- what was there before. integration.outbox already refuses DELETE by trigger, so the
-- structural half holds; what these columns add is EVIDENCE — an operator asking "did that
-- rollback lose the four orders we took during the outage" gets a number rather than an
-- assurance. A guarantee with no measurement is a sentence in a document.

-- ---------------------------------------------------------------------------
-- 1. WHAT A NODE IS RUNNING
-- ---------------------------------------------------------------------------

ALTER TABLE edge.node
    ADD COLUMN installed_version text NOT NULL DEFAULT '0.0.0';

COMMENT ON COLUMN edge.node.installed_version IS
    'FR-OPS-010. What this node is running now. Defaulted rather than nullable because a '
    'node with no version is a node no rollback has anywhere to go back to.';

CREATE TYPE edge.update_state AS ENUM ('staged', 'applied', 'rolled_back', 'refused');

-- ---------------------------------------------------------------------------
-- 2. THE BUNDLE
-- ---------------------------------------------------------------------------

CREATE TABLE edge.update_bundle (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,

    version         text NOT NULL,
    artifact_sha256 character(64) NOT NULL,

    -- THE KEYED DIGEST, and the column is named for what it is rather than for what a
    -- reader might wish it were. Calling it `signature` would be the first sentence of a
    -- claim this build cannot support.
    attestation_sha256 character(64) NOT NULL,

    -- FR-OPS-010's database compatibility check, as a range rather than a single number:
    -- an update that needs schema 44 and works through 48 is a different thing from one
    -- pinned to exactly 46, and only the range can express both.
    requires_schema_at_least integer NOT NULL,
    supports_schema_up_to    integer NOT NULL,

    published_at         timestamptz NOT NULL DEFAULT now(),
    published_by_user_id uuid NOT NULL,

    CONSTRAINT update_bundle_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT update_bundle_version_unique UNIQUE (tenant_id, version),
    CONSTRAINT update_bundle_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT update_bundle_publisher_fk FOREIGN KEY (tenant_id, published_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT update_bundle_version_is_stated CHECK (length(trim(version)) > 0),
    CONSTRAINT update_bundle_schema_range_is_a_range CHECK (
        supports_schema_up_to >= requires_schema_at_least),
    CONSTRAINT update_bundle_schema_floor_is_positive CHECK (requires_schema_at_least > 0)
);

COMMENT ON TABLE edge.update_bundle IS
    'FR-OPS-010. A published node update: what it is, what it hashes to, the keyed digest '
    'a publisher who knows the node''s trust anchor can produce, and the schema versions '
    'it is prepared to run against.';

ALTER TABLE edge.update_bundle ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.update_bundle FORCE ROW LEVEL SECURITY;
-- Tenant-scoped with no outlet: a bundle is published for a tenant's estate, not for one
-- outlet, and app.row_in_scope() treats a NULL outlet as "any within the tenant".
CREATE POLICY update_bundle_isolation ON edge.update_bundle FOR ALL
    USING (app.row_in_scope(tenant_id, NULL))
    WITH CHECK (app.row_in_scope(tenant_id, NULL));

-- ---------------------------------------------------------------------------
-- 3. WHAT HAPPENED TO ONE NODE
-- ---------------------------------------------------------------------------

CREATE TABLE edge.node_update (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,
    node_id   uuid NOT NULL,
    bundle_id uuid NOT NULL,

    state edge.update_state NOT NULL DEFAULT 'staged',

    from_version text NOT NULL,
    to_version   text NOT NULL,

    -- THE MEASUREMENT THAT MAKES THE GUARANTEE CHECKABLE.
    outbox_depth_at_staging integer NOT NULL,
    inbox_depth_at_staging  integer NOT NULL,
    outbox_depth_at_rollback integer,
    inbox_depth_at_rollback  integer,

    staged_at      timestamptz NOT NULL DEFAULT now(),
    applied_at     timestamptz,
    rolled_back_at timestamptz,
    rollback_reason text,

    CONSTRAINT node_update_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT node_update_node_fk FOREIGN KEY (tenant_id, node_id)
        REFERENCES edge.node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT node_update_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT node_update_bundle_fk FOREIGN KEY (tenant_id, bundle_id)
        REFERENCES edge.update_bundle (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT node_update_application_is_timed CHECK (
        (state IN ('applied', 'rolled_back')) = (applied_at IS NOT NULL)),
    CONSTRAINT node_update_rollback_is_explained CHECK (
        (state = 'rolled_back') = (rolled_back_at IS NOT NULL)
    AND (state = 'rolled_back') = (rollback_reason IS NOT NULL)
    AND (state = 'rolled_back') = (outbox_depth_at_rollback IS NOT NULL)),
    CONSTRAINT node_update_depths_not_negative CHECK (
        outbox_depth_at_staging >= 0 AND inbox_depth_at_staging >= 0)
);

COMMENT ON TABLE edge.node_update IS
    'FR-OPS-010. One node''s passage through one bundle, with the outbox and inbox depths '
    'recorded at staging and at rollback. "Rollback without corrupting local queues" is '
    'not checkable after the fact unless somebody wrote down what was there before.';

CREATE UNIQUE INDEX node_update_one_in_flight_per_node
    ON edge.node_update (node_id) WHERE state = 'staged';

ALTER TABLE edge.node_update ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.node_update FORCE ROW LEVEL SECURITY;
CREATE POLICY node_update_isolation ON edge.node_update FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 4. STAGING: THE TWO CHECKS, BEFORE ANYTHING CHANGES
-- ---------------------------------------------------------------------------

-- What a publisher must present. Exposed so the suite and an operator compute it the same
-- way the check does, rather than a test re-deriving the construction and agreeing with
-- itself.
CREATE FUNCTION edge.update_attestation(p_artifact_sha256 character(64),
                                        p_trust_anchor    character(64))
RETURNS character(64)
LANGUAGE sql IMMUTABLE
SET search_path TO 'pg_catalog', 'public'
AS $$
    SELECT encode(sha256((p_artifact_sha256 || p_trust_anchor)::bytea), 'hex')::character(64);
$$;

COMMENT ON FUNCTION edge.update_attestation(character, character) IS
    'The keyed digest a publisher presents. NOT a signature: it proves the publisher knew '
    'the node''s trust anchor, not who they were. Exposed so one construction is used by '
    'the check, the suite and an operator — a test that re-derived it would be agreeing '
    'with itself.';

CREATE FUNCTION edge.stage_update(
    p_tenant_id uuid,
    p_node_id   uuid,
    p_bundle_id uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'integration', 'migration', 'public'
AS $$
DECLARE
    n edge.node%ROWTYPE;
    b edge.update_bundle%ROWTYPE;
    v_schema  integer;
    v_outbox  integer;
    v_inbox   integer;
    v_id      uuid;
BEGIN
    SELECT * INTO n FROM edge.node
      WHERE tenant_id = p_tenant_id AND id = p_node_id AND status = 'active';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'NODE_UNKNOWN: no active node % for this tenant', p_node_id
            USING ERRCODE = 'HS404';
    END IF;

    SELECT * INTO b FROM edge.update_bundle
      WHERE tenant_id = p_tenant_id AND id = p_bundle_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'UPDATE_BUNDLE_UNKNOWN: no bundle %', p_bundle_id
            USING ERRCODE = 'HS404';
    END IF;

    -- CHECK ONE: the publisher knew this node's trust anchor.
    IF b.attestation_sha256
       <> edge.update_attestation(b.artifact_sha256, n.update_trust_anchor_sha256) THEN
        RAISE EXCEPTION
            'UPDATE_ATTESTATION_INVALID: bundle % does not attest against node %''s trust '
            'anchor. Either it was published for a different estate or it was altered '
            'after publication', b.version, n.node_code
            USING ERRCODE = 'HS403';
    END IF;

    -- CHECK TWO: the database this node runs against is one the bundle can work with.
    SELECT max(version) INTO v_schema FROM migration.schema_migrations;
    IF v_schema IS NULL THEN
        RAISE EXCEPTION
            'UPDATE_SCHEMA_UNKNOWN: no migration has been applied, so no compatibility '
            'claim can be checked'
            USING ERRCODE = 'HS500';
    END IF;
    IF v_schema < b.requires_schema_at_least OR v_schema > b.supports_schema_up_to THEN
        RAISE EXCEPTION
            'UPDATE_SCHEMA_INCOMPATIBLE: bundle % runs against schema %..% and this node''s '
            'database is at %. Applying it would be the update deciding it knows better '
            'than the schema it has to read',
            b.version, b.requires_schema_at_least, b.supports_schema_up_to, v_schema
            USING ERRCODE = 'HS409';
    END IF;

    SELECT count(*)::integer INTO v_outbox FROM integration.outbox
     WHERE node_id = p_node_id AND state <> 'acknowledged';
    SELECT count(*)::integer INTO v_inbox FROM integration.inbox
     WHERE node_id = p_node_id AND state <> 'applied';

    INSERT INTO edge.node_update (
        tenant_id, outlet_id, node_id, bundle_id, from_version, to_version,
        outbox_depth_at_staging, inbox_depth_at_staging)
    VALUES (p_tenant_id, n.outlet_id, p_node_id, p_bundle_id, n.installed_version,
            b.version, v_outbox, v_inbox)
    RETURNING id INTO v_id;

    INSERT INTO edge.node_admin_action (
        tenant_id, outlet_id, node_id, action_code, performed_by_user_id, detail)
    VALUES (p_tenant_id, n.outlet_id, p_node_id, 'node.update.stage', b.published_by_user_id,
            format('%s -> %s against schema %s, %s queued', n.installed_version, b.version,
                   v_schema, v_outbox + v_inbox));

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION edge.stage_update(uuid, uuid, uuid) IS
    'FR-OPS-010. Both checks before anything changes: the publisher knew the node''s trust '
    'anchor, and the bundle can run against the schema this database is actually at. '
    'Records what was queued, so a later rollback can be shown not to have lost it.';

-- ---------------------------------------------------------------------------
-- 5. APPLYING, AND GOING BACK
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.apply_update(p_tenant_id uuid, p_node_update_id uuid,
                                  p_actor_user_id uuid)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
DECLARE
    u edge.node_update%ROWTYPE;
BEGIN
    SELECT * INTO u FROM edge.node_update
      WHERE tenant_id = p_tenant_id AND id = p_node_update_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'NODE_UPDATE_UNKNOWN: no staged update %', p_node_update_id
            USING ERRCODE = 'HS404';
    END IF;
    IF u.state <> 'staged' THEN
        RAISE EXCEPTION
            'NODE_UPDATE_NOT_STAGED: update % is %, and only a staged update can be '
            'applied', p_node_update_id, u.state
            USING ERRCODE = 'HS409';
    END IF;

    UPDATE edge.node_update SET state = 'applied', applied_at = now()
     WHERE tenant_id = p_tenant_id AND id = p_node_update_id;

    -- row_version is NOT touched: app.enforce_row_version() refuses a caller that
    -- changes it and increments it itself. It is an optimistic-concurrency token,
    -- not a counter to bump, and bumping it is how this first failed.
    UPDATE edge.node SET installed_version = u.to_version
     WHERE tenant_id = p_tenant_id AND id = u.node_id;

    INSERT INTO edge.node_admin_action (
        tenant_id, outlet_id, node_id, action_code, performed_by_user_id, detail)
    VALUES (p_tenant_id, u.outlet_id, u.node_id, 'node.update.apply', p_actor_user_id,
            format('%s -> %s', u.from_version, u.to_version));
END;
$$;

-- ROLLING BACK, AND PROVING THE QUEUES SURVIVED IT.
--
-- The version goes back. The queues do not: an outbox row written while the new version
-- was running is work the outlet did, and it is still owed to the cloud whichever build
-- produced it. So this asserts the depths did not FALL, and records what it saw. A
-- rollback that had discarded queued work fails here rather than being discovered when a
-- day's takings do not reconcile.
CREATE FUNCTION edge.roll_back_update(
    p_tenant_id uuid, p_node_update_id uuid, p_actor_user_id uuid, p_reason text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'integration', 'public'
AS $$
DECLARE
    u edge.node_update%ROWTYPE;
    v_outbox integer;
    v_inbox  integer;
BEGIN
    SELECT * INTO u FROM edge.node_update
      WHERE tenant_id = p_tenant_id AND id = p_node_update_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'NODE_UPDATE_UNKNOWN: no update %', p_node_update_id
            USING ERRCODE = 'HS404';
    END IF;
    IF u.state <> 'applied' THEN
        RAISE EXCEPTION
            'NODE_UPDATE_NOT_APPLIED: update % is %, and only an applied update can be '
            'rolled back', p_node_update_id, u.state
            USING ERRCODE = 'HS409';
    END IF;
    IF p_reason IS NULL OR length(trim(p_reason)) = 0 THEN
        RAISE EXCEPTION
            'NODE_UPDATE_ROLLBACK_UNEXPLAINED: going back to % needs a reason. An '
            'unexplained rollback is indistinguishable from a failed upgrade nobody '
            'noticed', u.from_version
            USING ERRCODE = 'HS422';
    END IF;

    SELECT count(*)::integer INTO v_outbox FROM integration.outbox
     WHERE node_id = u.node_id AND state <> 'acknowledged';
    SELECT count(*)::integer INTO v_inbox FROM integration.inbox
     WHERE node_id = u.node_id AND state <> 'applied';

    IF v_outbox < u.outbox_depth_at_staging OR v_inbox < u.inbox_depth_at_staging THEN
        RAISE EXCEPTION
            'NODE_UPDATE_ROLLBACK_WOULD_LOSE_QUEUED_WORK: % outbox and % inbox items were '
            'waiting when this update was staged and only % and % are here now. Work the '
            'outlet did is still owed to the cloud whichever build produced it',
            u.outbox_depth_at_staging, u.inbox_depth_at_staging, v_outbox, v_inbox
            USING ERRCODE = 'HS409';
    END IF;

    UPDATE edge.node_update
       SET state = 'rolled_back', rolled_back_at = now(), rollback_reason = p_reason,
           outbox_depth_at_rollback = v_outbox, inbox_depth_at_rollback = v_inbox
     WHERE tenant_id = p_tenant_id AND id = p_node_update_id;

    UPDATE edge.node SET installed_version = u.from_version
     WHERE tenant_id = p_tenant_id AND id = u.node_id;

    INSERT INTO edge.node_admin_action (
        tenant_id, outlet_id, node_id, action_code, performed_by_user_id, detail)
    VALUES (p_tenant_id, u.outlet_id, u.node_id, 'node.update.roll_back', p_actor_user_id,
            format('%s -> %s: %s; %s outbox and %s inbox items intact',
                   u.to_version, u.from_version, p_reason, v_outbox, v_inbox));
END;
$$;

COMMENT ON FUNCTION edge.roll_back_update(uuid, uuid, uuid, text) IS
    'FR-OPS-010. Puts the version back and refuses to do so if the local queues have '
    'shrunk since staging. An outbox row written while the new build ran is work the '
    'outlet did, and it is still owed to the cloud whichever build produced it.';

GRANT SELECT ON edge.update_bundle TO hospitality_app;
GRANT SELECT ON edge.node_update   TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.update_attestation(character, character) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.stage_update(uuid, uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.apply_update(uuid, uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.roll_back_update(uuid, uuid, uuid, text) TO hospitality_app;

SELECT app.assert_financial_tables_are_classified();
SELECT app.assert_append_only_guards_are_declared();
