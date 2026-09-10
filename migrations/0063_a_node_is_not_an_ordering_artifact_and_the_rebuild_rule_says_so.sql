-- 0063: a node is not an ordering artifact, and the rebuild rule says so
--
-- 0060 added `node` to ordering.artifact_kind so an edge notice would have something to
-- point at. tests/m4b caught it, and the check that caught it was written for exactly this:
--
--     The kinds are read from the ENUM, so a kind added at M4-C appears here without
--     anybody extending a list, and the assertion is that each one names a rebuild. NULL
--     is the safe answer — an unowned kind is deleted by nobody — but it is not a silent
--     one.
--
-- ordering.correlation_link_rebuilt_by('node') returned NULL, and 0025's own comment says
-- what NULL means there: "nobody thought about this kind, and that is precisely the defect
-- they exist to catch." It was right. A whole gate later, an enum shared between two
-- schemas grew a value for one of them and the other's rule went quietly unowned.
--
-- WHAT THE HONEST ANSWER IS. A node is never in ordering.correlation_link. It is not a
-- thing a guest orders or pays for; it is the machine in the back room. So no rebuild
-- restores its links, because there are none — and `receipt` already established the shape
-- for saying that: a definite sentence rather than a NULL.
--
-- AND IT IS ENFORCED RATHER THAN ASSERTED. A sentence claiming "there are never any" is
-- worth what the writer's discipline is worth. ordering.link_correlation_artifact() now
-- refuses the kind outright, so the claim is a property of the schema. That is the same
-- move 0059 made when NC-M5B-005 showed that a filter is not a refusal.
--
-- THE BOUND THIS LEAVES, recorded in planning/M5B_FINDINGS.md rather than only here.
-- ordering.artifact_kind is now doing double duty: eleven values that mean "a thing a guest
-- orders or pays for" and one that means "the machine serving them". The type belongs to
-- `ordering` and notify is the only user of the twelfth value. The clean answer is a
-- separate notify.subject_kind, and it was not taken HERE because PostgreSQL cannot drop
-- an enum value — undoing 0060 means recreating a type used by three columns and four
-- functions, and a type-recreation migration written at the end of a gate to tidy a naming
-- problem is a larger risk than the problem. It is named as work rather than left as a
-- shape somebody has to rediscover.

CREATE OR REPLACE FUNCTION ordering.correlation_link_rebuilt_by(p_kind ordering.artifact_kind)
RETURNS text
LANGUAGE sql IMMUTABLE
SET search_path TO 'pg_catalog', 'public'
AS $$
    SELECT CASE p_kind
        WHEN 'request'            THEN 'ordering.rebuild_projections'
        WHEN 'cart'               THEN 'ordering.rebuild_projections'
        WHEN 'table_session'      THEN 'ordering.rebuild_projections'
        WHEN 'order'              THEN 'ordering.rebuild_projections'
        WHEN 'fulfillment_ticket' THEN 'ordering.rebuild_projections'
        WHEN 'service_request'    THEN 'ordering.rebuild_projections'
        WHEN 'check'              THEN 'billing.rebuild_projections'
        WHEN 'bill'               THEN 'billing.rebuild_projections'
        WHEN 'tip'                THEN 'billing.rebuild_projections'
        WHEN 'payment'            THEN 'billing.rebuild_projections'
        -- Durable, so no rebuild owns these links. Spelled out rather than left NULL:
        -- NULL is what 0025's DO block and tests/m4b treat as "nobody thought about this
        -- kind", and that is precisely the defect they exist to catch.
        WHEN 'receipt'            THEN '(durable: no rebuild deletes a receipt link)'
        -- Never linked at all, and refused below so that stays true. Same reasoning as
        -- `receipt` and a different fact: a receipt HAS links that no rebuild deletes; a
        -- node has none to delete.
        WHEN 'node'               THEN '(never linked: a node is not an ordering artifact)'
    END;
$$;

-- ---------------------------------------------------------------------------
-- AND THE ONLY WRITER REFUSES IT
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION ordering.link_correlation_artifact(
    p_tenant_id      uuid,
    p_outlet_id      uuid,
    p_correlation_id uuid,
    p_artifact_kind  ordering.artifact_kind,
    p_artifact_id    uuid,
    p_linked_at      timestamptz)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'ordering', 'public'
AS $$
BEGIN
    -- A NODE IS NOT AN ORDERING ARTIFACT. It shares a type with them because
    -- notify.notification needed a subject and 0060 widened the nearest one; it does not
    -- share the meaning. Refusing here is what makes
    -- correlation_link_rebuilt_by('node')'s answer a fact rather than a promise.
    --
    -- BEFORE the applying_event guard, deliberately: that flag tells the append-only
    -- triggers a replay is in progress, and setting it for a call that is about to be
    -- refused would leave it set if the refusal unwound differently than expected.
    IF p_artifact_kind = 'node' THEN
        RAISE EXCEPTION
            'CORRELATION_KIND_IS_NOT_AN_ARTIFACT: a node cannot be correlated to a guest''s '
            'journey. It is the machine serving them, not a thing they ordered, and no '
            'rebuild restores a link that is never written'
            USING ERRCODE = 'HS422';
    END IF;

    PERFORM set_config('ordering.applying_event', 'yes', true);
    INSERT INTO ordering.correlation_link
        (tenant_id, outlet_id, correlation_id, artifact_kind, artifact_id, linked_at)
    VALUES (p_tenant_id, p_outlet_id, p_correlation_id, p_artifact_kind, p_artifact_id,
            p_linked_at)
    ON CONFLICT DO NOTHING;
    PERFORM set_config('ordering.applying_event', '', true);
END;
$$;

-- RUN, NOT MERELY DEFINED. Three migrations in this gate applied cleanly and could never
-- have executed; this one proves both halves before it commits.
DO $$
DECLARE
    v_answer text;
    v_refused boolean := false;
BEGIN
    SELECT ordering.correlation_link_rebuilt_by('node') INTO v_answer;
    IF v_answer IS NULL OR length(trim(v_answer)) = 0 THEN
        RAISE EXCEPTION
            'ARTIFACT_KIND_UNOWNED: node still names no rebuild, which is the state '
            'tests/m4b refuses'
            USING ERRCODE = 'HS500';
    END IF;

    BEGIN
        PERFORM ordering.link_correlation_artifact(
            gen_random_uuid(), gen_random_uuid(), gen_random_uuid(),
            'node', gen_random_uuid(), now());
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM LIKE 'CORRELATION_KIND_IS_NOT_AN_ARTIFACT%' THEN
            v_refused := true;
        ELSE
            RAISE;
        END IF;
    END;

    IF NOT v_refused THEN
        RAISE EXCEPTION
            'CORRELATION_KIND_NOT_REFUSED: a node was accepted as an ordering artifact, so '
            'the answer above is a promise rather than a property'
            USING ERRCODE = 'HS500';
    END IF;
END;
$$;
