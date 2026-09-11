-- 0047: the room is told which way the outlet is running, in its own language
--
-- FR-EDG-009 asks that CUSTOMER AND STAFF be shown whether the outlet is cloud-connected,
-- running on local continuity, or reconciling — "without blocking ordinary local
-- service". 0045 built the states and the wording table; this is the third namespace that
-- table needs and the function a banner reads.
--
-- WHY THE CHECK HAD TO CHANGE, AND WHY THAT IS THE RIGHT KIND OF SMALL. edge.plain_language
-- constrained phrase codes to `restriction.` and `sync_state.`, which were the two things
-- 0045 knew about. A connectivity state is a third, and the honest move is to widen the
-- pattern by one name rather than to smuggle a banner phrase in as a `sync_state.` — which
-- would have worked, needed no migration, and left a reader wondering why the connectivity
-- banner reads its text out of the synchronization states.
--
-- WHY THE BANNER IS A FUNCTION AND NOT A SELECT. The three states are not three rows: two
-- of them come from integration.sync_state and the third — reconciling — is DERIVED from
-- there being an open conflict, which is a rule 0043 states in one place. A surface that
-- assembled the banner from a join would be a second implementation of that rule, and the
-- second implementation is always the one nobody tests.

-- ---------------------------------------------------------------------------
-- 1. A THIRD NAMESPACE
-- ---------------------------------------------------------------------------

ALTER TABLE edge.plain_language
    DROP CONSTRAINT plain_language_code_shape;

ALTER TABLE edge.plain_language
    ADD CONSTRAINT plain_language_code_shape CHECK (
        phrase_code ~ '^(restriction|sync_state|connectivity)\.[a-z][a-z0-9_]*$');

COMMENT ON CONSTRAINT plain_language_code_shape ON edge.plain_language IS
    'Three namespaces, named rather than open. An unconstrained code column becomes a '
    'place to put anything, and the first thing that goes in is a phrase nobody can find '
    'again because no rule says where it should have been.';

-- ---------------------------------------------------------------------------
-- 2. WHAT A BANNER SHOWS (FR-EDG-009)
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.connectivity_banner(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_locale    menu.customer_locale DEFAULT 'en')
RETURNS TABLE (
    state         edge.connectivity_state,
    wording       text,
    paused_reason text,
    open_conflicts integer,
    blocks_service boolean)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'integration', 'public'
AS $$
DECLARE
    v_node  uuid;
    v_state edge.connectivity_state;
    v_paused text;
    v_open  integer;
BEGIN
    -- "I COULD NOT SEE A NODE" IS NOT "THERE IS NO NODE", AND THE DIFFERENCE IS THE WHOLE
    -- VALUE OF THIS FUNCTION.
    --
    -- edge.node carries FORCE row level security scoped by (tenant, outlet). A caller
    -- with tenant context and no outlet context sees nothing — and the first version of
    -- this read that as "this outlet has no node", took the cloud-only branch, and
    -- returned CONNECTED. A banner that says the outlet is fine because it failed to look
    -- is worse than no banner: staff would be reading a reassurance produced by the
    -- absence of information.
    --
    -- So the context is required to match what is being asked about. A caller that cannot
    -- see the outlet gets an error, which a surface can show as "unknown" — and unknown
    -- is a true thing to say.
    IF app.current_tenant_id() IS DISTINCT FROM p_tenant_id
       OR app.current_outlet_id() IS DISTINCT FROM p_outlet_id THEN
        RAISE EXCEPTION
            'CONNECTIVITY_OUT_OF_SCOPE: asked about outlet % under context %/%. This '
            'function reads tables under row level security, and without the matching '
            'context it would report an outlet it cannot see as one that has no node — '
            'which reads as CONNECTED',
            p_outlet_id, app.current_tenant_id(), app.current_outlet_id()
            USING ERRCODE = 'HS403';
    END IF;

    SELECT id INTO v_node FROM edge.node
      WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id AND status = 'active';

    -- AN OUTLET WITH NO NODE IS NOT BROKEN. A cloud-only demonstration outlet is a
    -- permitted deployment (FR-EDG-001 forbids it only in production), and a banner that
    -- reported it as an outage would teach staff to ignore the banner. This branch is now
    -- reachable ONLY when the caller could have seen a node and there was none.
    IF v_node IS NULL THEN
        RETURN QUERY SELECT 'cloud_connected'::edge.connectivity_state,
                            edge.say(p_tenant_id, 'connectivity.cloud_connected', p_locale),
                            NULL::text, 0, false;
        RETURN;
    END IF;

    SELECT s.connectivity, s.paused_reason INTO v_state, v_paused
      FROM integration.sync_state s WHERE s.node_id = v_node;

    SELECT count(*)::integer INTO v_open
      FROM integration.conflict c
     WHERE c.node_id = v_node AND c.resolution IS NULL;

    -- A NODE THAT HAS NEVER REACHED THE CLOUD IS ON LOCAL CONTINUITY, not unknown. There
    -- is no fourth state to show and inventing one — "starting up", "unknown" — would put
    -- a word on a screen that no requirement defines and no staff training covers.
    v_state := COALESCE(v_state, 'local_continuity'::edge.connectivity_state);

    RETURN QUERY
    SELECT v_state,
           edge.say(p_tenant_id, 'connectivity.' || v_state::text, p_locale),
           v_paused,
           v_open,
           -- THE ANSWER IS ALWAYS FALSE, AND IT IS RETURNED ANYWAY.
           --
           -- FR-EDG-009's own words are "without blocking ordinary local service". A
           -- column that says so makes the claim checkable by anything that reads the
           -- banner, and makes a future change that DID block service have to come here
           -- and write true. A guarantee nothing states is a guarantee nothing protects.
           false;
END;
$$;

COMMENT ON FUNCTION edge.connectivity_banner(uuid, uuid, menu.customer_locale) IS
    'FR-EDG-009. The state, the words for it, why synchronization is paused if it is, how '
    'many conflicts are open, and whether any of it blocks service — which is always no, '
    'stated rather than assumed so a change that broke it has to say so here.';

GRANT EXECUTE ON FUNCTION edge.connectivity_banner(uuid, uuid, menu.customer_locale)
    TO hospitality_app;
