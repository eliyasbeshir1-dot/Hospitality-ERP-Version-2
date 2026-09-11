-- 0046: a node started at the wrong outlet is told so, rather than told it does not exist
--
-- THE DEFECT, FOUND BY STARTING THE THING.
--
-- 0039 gave edge.authenticate_node() four separate refusals on purpose, and the comment
-- says why: "Unknown, revoked, wrong fingerprint and wrong outlet are four refusals, not
-- one, because an operator should not have to guess which of them happened."
--
-- Three of them were reachable. The fourth was not.
--
-- edge.node carries FORCE row level security scoped by (tenant, outlet), and the node
-- process set its context to the outlet it BELIEVED it served before asking whether that
-- belief was right. So a node booted with the wrong outlet id looked for its own
-- registration in a scope its registration is not in, found nothing, and was told
-- NODE_UNKNOWN: "no node NODE-H2 is registered for this tenant" — a sentence the function
-- had not verified and which was false. The node was registered. It was standing in the
-- wrong room.
--
-- An operator reading that goes and re-registers a node that already exists. The mistyped
-- outlet id survives, because nothing ever mentioned it.
--
-- NODE_OUTLET_MISMATCH was therefore dead code from the moment it was written: a branch
-- that could not be reached, in the function whose entire job is FR-CFG-001E's "prove it
-- starts only with the correct outlet identity". The proof was there and the diagnosis
-- was wrong, which is the harder half to notice — the node did refuse.
--
-- THE FIX IS A POLICY, NOT A WIDENING.
--
-- The tempting repair is to let a node read its tenant's nodes and compare. That hands
-- any outlet's context the fingerprints, endpoints and secret-store references of its
-- siblings, to fix a message.
--
-- What the node actually has at boot is its own fingerprint, and presenting it IS the
-- authentication. So the policy below discloses exactly one row to a caller that already
-- knows that row's fingerprint: no outlet scope, no browsing, nothing gained by a caller
-- who does not already hold the thing being checked. A node can identify itself, and can
-- learn nothing else.
--
-- WHAT THIS DOES NOT CHANGE. The function still refuses a wrong fingerprint, and the
-- fingerprint is still the secret half of the check. The policy makes the ROW visible to
-- somebody holding the fingerprint; edge.authenticate_node() is what decides whether the
-- rest of the claim is true. A caller with a valid fingerprint and a wrong outlet now
-- gets the refusal that names the outlet, which is the whole point.

-- ---------------------------------------------------------------------------
-- 1. A NODE MAY FIND ITSELF, BY PRESENTING WHAT ONLY IT HOLDS
-- ---------------------------------------------------------------------------

CREATE POLICY node_self_identification ON edge.node FOR SELECT
    USING (tenant_id = app.current_tenant_id()
           AND identity_fingerprint
               = nullif(current_setting('app.node_fingerprint', true), ''));

COMMENT ON POLICY node_self_identification ON edge.node IS
    'FR-CFG-001E. Lets a node read its OWN registration by presenting the fingerprint it '
    'holds, without an outlet scope — because the outlet is the thing being checked and a '
    'check that requires the answer cannot detect a wrong one. Permissive and narrow: one '
    'row, to a caller that already knows that row''s fingerprint.';

-- ---------------------------------------------------------------------------
-- 2. THE REFUSALS, ALL FOUR NOW REACHABLE
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION edge.authenticate_node(
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
    -- BY FINGERPRINT FIRST, NOT BY CODE. The fingerprint is what the caller proves; the
    -- code is what it claims. Looking up by the claim and then checking the proof is the
    -- order that made the outlet branch unreachable, because the claim included an outlet
    -- scope the row was not in.
    SELECT * INTO n FROM edge.node
      WHERE tenant_id = p_tenant_id AND identity_fingerprint = p_identity_fingerprint;

    IF NOT FOUND THEN
        -- Everything that is indistinguishable at this point is reported as one thing,
        -- and the message says which things those are rather than picking one and
        -- sounding certain. A caller holding no valid fingerprint is not told whether the
        -- node exists.
        RAISE EXCEPTION
            'NODE_IDENTITY_MISMATCH: no node of this tenant presents the fingerprint '
            'given for %. Either the node is not registered or the fingerprint it holds '
            'is not the one recorded; from here those are the same observation',
            p_node_code
            USING ERRCODE = 'HS403';
    END IF;

    IF n.node_code <> p_node_code THEN
        RAISE EXCEPTION
            'NODE_UNKNOWN: the fingerprint presented belongs to node %, and this process '
            'started as %', n.node_code, p_node_code
            USING ERRCODE = 'HS404';
    END IF;

    IF n.status <> 'active' THEN
        RAISE EXCEPTION 'NODE_REVOKED: node % was revoked at %', p_node_code, n.revoked_at
            USING ERRCODE = 'HS403';
    END IF;

    -- THE ONE THIS MIGRATION EXISTS FOR. A node that starts believing it serves a sibling
    -- outlet is refused and told which outlet it is actually bound to, because correcting
    -- it silently is how one outlet's orders end up under another's roof — and telling it
    -- the node does not exist is how a mistyped outlet id survives a re-registration.
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
    'FR-CFG-001E. Proves a node starts only with the correct outlet identity. Looks up by '
    'the fingerprint the caller PROVES rather than by the code it CLAIMS, which is what '
    'makes the wrong-outlet refusal reachable at all — the first version scoped the lookup '
    'by the outlet it was about to check and could only ever report NODE_UNKNOWN.';
