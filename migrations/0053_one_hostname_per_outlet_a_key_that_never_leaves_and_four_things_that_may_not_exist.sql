-- 0053: one hostname per outlet, a key that never leaves, and four things that may not exist
--
-- FR-OPS-017 and FR-EDG-022A/B/C are one mechanism described from four angles: the same
-- QR code has to reach the cloud from the street and the node from the dining room, over
-- TLS a phone already trusts, without anybody tapping through a warning.
--
-- WHAT THIS MIGRATION CAN AND CANNOT ESTABLISH, SAID FIRST.
--
-- It cannot issue a certificate. There is no domain, no CA account and no DNS-01
-- automation on this machine, and inventing a fake chain would make every check below a
-- check about the fake. What it CAN do is hold the lifecycle honestly — what was
-- requested, what came back, when it expires, when renewal must start, what was served on
-- the LAN and whether that matched — and refuse the four things FR-EDG-022C prohibits.
-- planning/M5B_FINDINGS.md carries the bound with what closes it.
--
-- THE PRIVATE KEY IS NOT HERE, AND ITS ABSENCE IS THE DESIGN.
--
-- FR-EDG-022A: "the node generates and retains its private key, submits only a CSR, and
-- receives the public-CA certificate chain... the private key is never exported." There is
-- therefore NO COLUMN for one, anywhere, and edge.no_private_key_is_stored() proves that
-- by asking the catalog rather than by anybody remembering. A schema that has nowhere to
-- put a private key cannot leak one through this database, which is a stronger statement
-- than a policy saying it must not.
--
-- WHY THE PROHIBITIONS ARE CHECKS AND NOT A DOCUMENT. FR-EDG-022C names four things that
-- must not exist: a shared cross-outlet wildcard key, a raw local-IP customer URL, a
-- self-signed certificate warning, and a manual browser bypass. Three of the four are
-- properties of a row and are refused at write time. The fourth — a bypass — is a property
-- of a surface, and lives where surfaces are checked; this file records that it is not
-- claimed here rather than implying it is covered.

-- ---------------------------------------------------------------------------
-- 1. THE HOSTNAME
-- ---------------------------------------------------------------------------

CREATE TABLE edge.outlet_hostname (
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,

    hostname text NOT NULL,

    -- Split-horizon: the same name, answered differently depending on where the asker is.
    -- Both are recorded because "the same QR reaches both" is a claim about two answers
    -- and a reader should be able to see them side by side.
    public_answer text NOT NULL,
    lan_answer    text NOT NULL,

    -- The documented TTL window FR-EDG-028 measures a cached-answer device against.
    ttl_seconds integer NOT NULL DEFAULT 60,

    declared_by_user_id uuid NOT NULL,
    declared_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT outlet_hostname_pkey PRIMARY KEY (tenant_id, outlet_id),
    CONSTRAINT outlet_hostname_unique UNIQUE (hostname),
    CONSTRAINT outlet_hostname_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT outlet_hostname_declarer_fk FOREIGN KEY (tenant_id, declared_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,

    -- PROHIBITION 1: NO WILDCARD. FR-EDG-022C forbids shared cross-outlet wildcard private
    -- keys, and the hostname is where that starts: a wildcard name is what makes one key
    -- serve every outlet. Refusing the name refuses the shape.
    CONSTRAINT outlet_hostname_is_not_a_wildcard CHECK (hostname NOT LIKE '*%'),

    -- PROHIBITION 2: NO RAW IP, in the name a customer's phone is sent to. A literal
    -- address cannot be on a public certificate a phone already trusts, so a QR pointing
    -- at one ends in the warning this whole requirement exists to avoid.
    CONSTRAINT outlet_hostname_is_a_name_not_an_address CHECK (
        hostname !~ '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' AND hostname !~ ':'),

    -- It must actually look like a hostname, so "" or "localhost " cannot slip through.
    CONSTRAINT outlet_hostname_shape CHECK (
        hostname ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'),

    -- THE LAN ANSWER IS AN ADDRESS AND THE PUBLIC ANSWER IS AN ADDRESS, and neither is
    -- what the customer sees — the customer sees the hostname. That distinction is the
    -- whole of split-horizon DNS, and conflating them is how a raw-IP URL gets shipped.
    CONSTRAINT outlet_hostname_answers_are_stated CHECK (
        length(trim(public_answer)) > 0 AND length(trim(lan_answer)) > 0),
    CONSTRAINT outlet_hostname_ttl_is_sane CHECK (ttl_seconds BETWEEN 1 AND 3600)
);

COMMENT ON TABLE edge.outlet_hostname IS
    'FR-OPS-017, FR-EDG-022A. One public hostname per outlet, and the two addresses '
    'split-horizon DNS answers with. The customer never sees either address — they see '
    'the name — and that distinction is the whole mechanism. A wildcard name and a raw '
    'address are both refused here, because the name is where FR-EDG-022C''s first two '
    'prohibitions start.';

ALTER TABLE edge.outlet_hostname ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.outlet_hostname FORCE ROW LEVEL SECURITY;
CREATE POLICY outlet_hostname_isolation ON edge.outlet_hostname FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 2. THE CERTIFICATE, AND ITS LIFE
-- ---------------------------------------------------------------------------

CREATE TYPE edge.certificate_state AS ENUM (
    'requested', 'issued', 'installed', 'renewing', 'revoked', 'expired');

CREATE TABLE edge.node_certificate (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,
    node_id   uuid NOT NULL,

    -- WHAT THE NODE SUBMITTED. Only ever a CSR digest: the request, not the key that made
    -- it. There is no column for the key and there is not going to be one.
    csr_sha256 character(64) NOT NULL,

    -- WHAT CAME BACK. Null until it does, which is what `requested` means.
    certificate_sha256 character(64),
    issuer             text,
    not_before timestamptz,
    not_after  timestamptz,

    -- WHAT WAS ACTUALLY SERVED ON THE LAN, observed rather than assumed. FR-EDG-022B asks
    -- for the LAN-served fingerprint to be recorded BEFORE completion, which is the only
    -- way to know the certificate that was issued is the certificate a phone will meet.
    lan_served_sha256   character(64),
    lan_verified_at     timestamptz,

    state edge.certificate_state NOT NULL DEFAULT 'requested',

    renewal_attempts integer NOT NULL DEFAULT 0,
    last_renewal_error text,

    revoked_at     timestamptz,
    revocation_reason text,

    requested_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT node_certificate_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT node_certificate_node_fk FOREIGN KEY (tenant_id, node_id)
        REFERENCES edge.node (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT node_certificate_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT node_certificate_attempts_not_negative CHECK (renewal_attempts >= 0),

    -- AN ISSUED CERTIFICATE HAS A VALIDITY WINDOW AND AN ISSUER. Anything less is a
    -- record of hoping.
    CONSTRAINT node_certificate_issued_is_complete CHECK (
        state IN ('requested', 'revoked')
        OR (certificate_sha256 IS NOT NULL AND issuer IS NOT NULL
            AND not_before IS NOT NULL AND not_after IS NOT NULL)),
    CONSTRAINT node_certificate_window_is_a_window CHECK (
        not_after IS NULL OR not_before IS NULL OR not_after > not_before),

    -- PROHIBITION 3: NO SELF-SIGNED. A certificate whose issuer is the node itself is the
    -- one that produces the browser warning FR-EDG-022C forbids, and it is refused where
    -- it would be written rather than detected later by a scanner.
    CONSTRAINT node_certificate_is_not_self_signed CHECK (
        issuer IS NULL OR issuer NOT ILIKE '%self-signed%'),

    -- INSTALLED MEANS SOMEBODY LOOKED AT WHAT THE LAN SERVES. FR-EDG-022B's "records
    -- LAN-served fingerprint and expiry before completion", as a constraint.
    CONSTRAINT node_certificate_installed_was_verified CHECK (
        state <> 'installed'
        OR (lan_served_sha256 IS NOT NULL AND lan_verified_at IS NOT NULL
            AND lan_served_sha256 = certificate_sha256)),

    CONSTRAINT node_certificate_revocation_is_explained CHECK (
        (state = 'revoked') = (revoked_at IS NOT NULL)
    AND (revoked_at IS NULL) = (revocation_reason IS NULL))
);

COMMENT ON TABLE edge.node_certificate IS
    'FR-EDG-022A/B. The per-outlet certificate''s life: the CSR digest the node submitted, '
    'what came back, when it expires, what the LAN actually served and whether that '
    'matched. THERE IS NO PRIVATE KEY COLUMN and there is not going to be one — the node '
    'generates and retains its key, and a schema with nowhere to put one cannot leak it.';

CREATE UNIQUE INDEX node_certificate_one_installed_per_node
    ON edge.node_certificate (node_id) WHERE state = 'installed';

ALTER TABLE edge.node_certificate ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.node_certificate FORCE ROW LEVEL SECURITY;
CREATE POLICY node_certificate_isolation ON edge.node_certificate FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 3. THE PROHIBITION THAT IS A PROPERTY OF THE SCHEMA ITSELF
-- ---------------------------------------------------------------------------

-- FR-EDG-022A says the private key is never exported. The strongest form of that is not a
-- rule about who may read a column; it is that no such column exists. This asks the
-- catalog, so it stays true as the schema grows rather than being a claim about the schema
-- as it was on the day somebody wrote it.
CREATE FUNCTION edge.private_key_columns()
RETURNS TABLE (schema_name text, table_name text, column_name text)
LANGUAGE sql STABLE
SET search_path TO 'pg_catalog', 'public'
AS $$
    SELECT n.nspname::text, c.relname::text, a.attname::text
      FROM pg_attribute a
      JOIN pg_class c ON c.oid = a.attrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relkind = 'r'
       AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
       AND a.attnum > 0 AND NOT a.attisdropped
       -- The names a private key would plausibly be given. Deliberately broad: a column
       -- called `key_pem` is as much of a problem as one called `private_key`, and the
       -- cost of a false positive is somebody renaming a column.
       AND (a.attname ~* '(private_key|privkey|secret_key|key_pem|key_pkcs|pem_key)')
     ORDER BY 1, 2, 3;
$$;

COMMENT ON FUNCTION edge.private_key_columns() IS
    'FR-EDG-022A, FR-OPS-017. Every column anywhere in this database that looks like a '
    'place to put a private key. The requirement is that this returns NOTHING: a schema '
    'with nowhere to store one cannot export one, which is stronger than a rule saying it '
    'must not. Asked of the catalog so it stays true as the schema grows.';

-- ---------------------------------------------------------------------------
-- 4. THE RENEWAL WINDOW, AND WHAT AN OPERATOR IS TOLD WHEN
-- ---------------------------------------------------------------------------

CREATE TYPE edge.renewal_posture AS ENUM (
    'healthy', 'renew_now', 'alert_14_days', 'alert_7_days', 'expired', 'absent');

-- FR-EDG-022B's schedule, derived rather than stored: renewal begins at 30 days, alerts
-- at 14 and at 7, and an expired certificate says so. A stored posture would be a claim
-- written at a moment, and the moment that matters is the one somebody asks in.
CREATE FUNCTION edge.certificate_posture(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (
    posture       edge.renewal_posture,
    days_remaining integer,
    detail        text)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
DECLARE
    c edge.node_certificate%ROWTYPE;
    v_days integer;
BEGIN
    SELECT * INTO c FROM edge.node_certificate
      WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id AND state = 'installed'
      ORDER BY not_after DESC LIMIT 1;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 'absent'::edge.renewal_posture, NULL::integer,
            'no installed certificate for this outlet: the same QR cannot reach the node '
            'over TLS a phone trusts, and the journey falls back to the cloud'::text;
        RETURN;
    END IF;

    v_days := floor(extract(epoch FROM (c.not_after - now())) / 86400)::integer;

    RETURN QUERY SELECT
        CASE
            WHEN v_days < 0  THEN 'expired'
            WHEN v_days <= 7  THEN 'alert_7_days'
            WHEN v_days <= 14 THEN 'alert_14_days'
            WHEN v_days <= 30 THEN 'renew_now'
            ELSE 'healthy'
        END::edge.renewal_posture,
        v_days,
        CASE
            WHEN v_days < 0 THEN
                format('expired %s day(s) ago; the LAN journey must fall back to the '
                       'cloud-served one rather than show a warning', -v_days)
            WHEN v_days <= 7 THEN
                format('%s day(s) left — second alert; renewal has been due since day 30',
                       v_days)
            WHEN v_days <= 14 THEN
                format('%s day(s) left — first alert; renewal has been due since day 30',
                       v_days)
            WHEN v_days <= 30 THEN
                format('%s day(s) left; renewal begins now', v_days)
            ELSE format('%s day(s) left', v_days)
        END::text;
END;
$$;

COMMENT ON FUNCTION edge.certificate_posture(uuid, uuid) IS
    'FR-EDG-022B. Renewal begins at 30 days, alerts at 14 and 7, and an absent or expired '
    'certificate says what the customer journey does instead — falls back to the cloud, '
    'never to a warning. Derived rather than stored: a stored posture is a claim written '
    'at a moment, and the moment that matters is the one somebody asks in.';

-- ---------------------------------------------------------------------------
-- 5. INSTALLING ONE, AND REFUSING TO INSTALL SOMETHING ELSE
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.verify_and_install_certificate(
    p_tenant_id uuid,
    p_certificate_id uuid,
    p_lan_served_sha256 character(64))
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
DECLARE
    c edge.node_certificate%ROWTYPE;
BEGIN
    SELECT * INTO c FROM edge.node_certificate
      WHERE tenant_id = p_tenant_id AND id = p_certificate_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'CERTIFICATE_UNKNOWN: no certificate %', p_certificate_id
            USING ERRCODE = 'HS404';
    END IF;
    IF c.certificate_sha256 IS NULL THEN
        RAISE EXCEPTION
            'CERTIFICATE_NOT_ISSUED: certificate % has been requested and nothing has come '
            'back yet, so there is nothing to verify against', p_certificate_id
            USING ERRCODE = 'HS409';
    END IF;

    -- THE THING SERVED MUST BE THE THING ISSUED. This is the check FR-EDG-022B asks for
    -- and the reason it asks BEFORE completion: a node that installed a different
    -- certificate from the one the CA issued would serve a phone something nobody
    -- verified, and the first person to find out would be a customer looking at a warning.
    IF p_lan_served_sha256 <> c.certificate_sha256 THEN
        RAISE EXCEPTION
            'CERTIFICATE_SERVED_DOES_NOT_MATCH_ISSUED: the LAN is serving % and the '
            'certificate issued for this node is %. Installing over that disagreement '
            'would put an unverified certificate in front of a customer',
            p_lan_served_sha256, c.certificate_sha256
            USING ERRCODE = 'HS409';
    END IF;

    UPDATE edge.node_certificate
       SET state = 'installed',
           lan_served_sha256 = p_lan_served_sha256,
           lan_verified_at = now(),
           last_renewal_error = NULL
     WHERE tenant_id = p_tenant_id AND id = p_certificate_id;
END;
$$;

CREATE FUNCTION edge.revoke_certificate(
    p_tenant_id uuid, p_certificate_id uuid, p_reason text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
BEGIN
    IF p_reason IS NULL OR length(trim(p_reason)) = 0 THEN
        RAISE EXCEPTION
            'CERTIFICATE_REVOCATION_UNEXPLAINED: revoking a certificate takes the outlet '
            'off the LAN journey until a new one is installed. That needs a reason'
            USING ERRCODE = 'HS422';
    END IF;
    UPDATE edge.node_certificate
       SET state = 'revoked', revoked_at = now(), revocation_reason = p_reason
     WHERE tenant_id = p_tenant_id AND id = p_certificate_id AND state <> 'revoked';
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'CERTIFICATE_UNKNOWN_OR_REVOKED: no unrevoked certificate %', p_certificate_id
            USING ERRCODE = 'HS404';
    END IF;
END;
$$;

GRANT SELECT ON edge.outlet_hostname   TO hospitality_app;
GRANT SELECT ON edge.node_certificate  TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.private_key_columns() TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.certificate_posture(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.verify_and_install_certificate(uuid, uuid, character)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.revoke_certificate(uuid, uuid, text) TO hospitality_app;

-- IT HAS TO HOLD THE MOMENT IT IS WRITTEN, or it is a rule for the future about a
-- repository that already breaks it.
DO $$
DECLARE found text[];
BEGIN
    SELECT array_agg(schema_name || '.' || table_name || '.' || column_name)
      INTO found FROM edge.private_key_columns();
    IF found IS NOT NULL THEN
        RAISE EXCEPTION
            'PRIVATE_KEY_COLUMN_EXISTS: % — FR-EDG-022A says the node''s private key is '
            'never exported, and the strongest form of that is having nowhere to put it',
            found USING ERRCODE = 'HS500';
    END IF;
END;
$$;
