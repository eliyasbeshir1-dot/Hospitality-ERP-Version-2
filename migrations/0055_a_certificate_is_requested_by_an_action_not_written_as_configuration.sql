-- 0055: a certificate is requested by an action, not written as configuration
--
-- 0053 gave edge.node_certificate an install path and no request path, so the only way to
-- create one was a bare INSERT. Writing seeds/0016 made that visible, and the question it
-- forced is the useful one: does edge.node_certificate belong in tools/seed.py's
-- PROVISIONABLE_TABLES?
--
-- IT DOES NOT, AND THE TEST THAT SAYS SO IS THE ONE ALREADY WRITTEN DOWN. That set is for
-- "a decision an installer makes and a manager revisits", and its counter-example is
-- exact: a bill is SELECT-only to the app role because a FUNCTION writes it, not because
-- it is configuration. A certificate is the second kind. Nobody DECIDES a certificate —
-- a node generates a key, submits a CSR, and a CA answers. The row is a record of that
-- exchange, and its state machine is the point of it.
--
-- edge.outlet_hostname and edge.supported_network ARE the first kind and go in the set: a
-- person chooses the name, a person documents the resolver, and a person revisits both.
--
-- So this adds the missing half of the pair. edge.request_certificate() is the counterpart
-- to 0053's edge.verify_and_install_certificate(), and with both ends present the state
-- machine has no entrance that skips it — which is what made `requested` a real state
-- rather than a value the schema permits and nothing produces.

CREATE FUNCTION edge.request_certificate(
    p_tenant_id uuid,
    p_node_id   uuid,
    p_csr_sha256 character(64))
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
DECLARE
    n edge.node%ROWTYPE;
    v_id uuid;
BEGIN
    SELECT * INTO n FROM edge.node
      WHERE tenant_id = p_tenant_id AND id = p_node_id AND status = 'active';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'NODE_UNKNOWN: no active node % for this tenant', p_node_id
            USING ERRCODE = 'HS404';
    END IF;

    -- THE OUTLET MUST HAVE A NAME FIRST. A CSR is a request for a certificate FOR a
    -- hostname, and requesting one before the outlet has a name is asking a CA to sign
    -- nothing in particular. It is also the order the failure wants to be found in:
    -- undeclared name is an installer's oversight, and a CA rejection weeks later is not.
    PERFORM 1 FROM edge.outlet_hostname
      WHERE tenant_id = p_tenant_id AND outlet_id = n.outlet_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'OUTLET_HOSTNAME_UNDECLARED: outlet % has no hostname, so there is nothing for '
            'a certificate to be issued FOR', n.outlet_id
            USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO edge.node_certificate (tenant_id, outlet_id, node_id, csr_sha256, state)
    VALUES (p_tenant_id, n.outlet_id, p_node_id, p_csr_sha256, 'requested')
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION edge.request_certificate(uuid, uuid, character) IS
    'FR-EDG-022A/B. The entrance to the certificate state machine, and the counterpart to '
    'edge.verify_and_install_certificate(). Takes a CSR DIGEST and never a key — the node '
    'generates and retains its key, and 0053''s edge.private_key_columns() proves there is '
    'nowhere here to put one. Refuses an outlet with no hostname, because a CSR is a '
    'request for a certificate FOR a name.';

-- ---------------------------------------------------------------------------
-- AND WHAT THE CA ANSWERED
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.record_certificate_issued(
    p_tenant_id uuid,
    p_certificate_id uuid,
    p_certificate_sha256 character(64),
    p_issuer text,
    p_not_before timestamptz,
    p_not_after  timestamptz)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
BEGIN
    UPDATE edge.node_certificate
       SET certificate_sha256 = p_certificate_sha256,
           issuer     = p_issuer,
           not_before = p_not_before,
           not_after  = p_not_after,
           state      = 'issued',
           last_renewal_error = NULL
     WHERE tenant_id = p_tenant_id AND id = p_certificate_id
       AND state IN ('requested', 'renewing');
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'CERTIFICATE_NOT_AWAITING_ISSUE: % is not a certificate that has been requested '
            'and is waiting for an answer. Recording an issue against an installed one '
            'would change what a node is serving without anybody verifying the new thing',
            p_certificate_id
            USING ERRCODE = 'HS409';
    END IF;
END;
$$;

COMMENT ON FUNCTION edge.record_certificate_issued(uuid, uuid, character, text, timestamptz,
                                                   timestamptz) IS
    'FR-EDG-022B. What the CA answered. Only against a certificate that is waiting for an '
    'answer: overwriting an INSTALLED one would change what a node serves without the '
    'LAN verification 0053 requires, which is the check being skipped rather than passed.';

GRANT EXECUTE ON FUNCTION edge.request_certificate(uuid, uuid, character) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.record_certificate_issued(uuid, uuid, character, text,
        timestamptz, timestamptz) TO hospitality_app;
