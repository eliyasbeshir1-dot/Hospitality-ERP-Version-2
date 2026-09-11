-- 0051: a standby may exist, because authority now says who writes
--
-- 0039 put a unique index on edge.node allowing ONE ACTIVE NODE PER OUTLET, and said why:
--
--     ONE ACTIVE NODE PER OUTLET. Two would make "which node is authoritative here" a
--     question with two answers, which is the M5b split-brain this gate must not create.
--
-- That was the right call at M5a and it is the wrong one now, for the reason the comment
-- itself gives. At M5a there was nothing that could answer "which node is authoritative
-- here", so the only way to keep the question from having two answers was to keep there
-- from being two nodes. 0050 answers it properly: edge.authority holds a monotonic
-- sequence, one holder per outlet by unique index, and every writer asks
-- edge.assert_authority() before it writes.
--
-- WHY THIS HAS TO CHANGE RATHER THAN BE WORKED AROUND. FR-EDG-024 is about a REPLACEMENT:
--
--     Before a standby node or standby outlet node becomes writable, record step-up,
--     independent approval, old-node power-off or router/firewall/switch-port/VLAN
--     isolation, and an automated LAN-unreachability probe.
--
-- A standby that cannot be registered until the node it stands by is deactivated is not a
-- standby. It is a spare in a cupboard, and the gap between deactivating one and
-- registering the other is an outlet with no node at all — during which nothing can write
-- and no fence evidence can be recorded, because there is nothing to record it against.
-- The requirement's whole shape assumes both exist at once.
--
-- SO THE FENCE RETIRES AND IS REPLACED BY WHAT OUTLIVES IT, the way M4-A retired six and
-- M5a retired three more. What M5a was protecting is still protected, and now by the
-- mechanism that was always supposed to do it:
--
--   before   at most one node existed, so at most one could write
--   after    any number of nodes may exist, and exactly one holds authority
--
-- The dangerous state — two writers — was never actually prevented by the old index
-- anyway. It prevented two REGISTRATIONS. A single registered node whose process had been
-- started twice, or a node whose replacement had been registered after deactivating it and
-- then found alive on the LAN, would both have passed it. edge.assert_authority() refuses
-- on the write, which is where it matters.

DROP INDEX edge.node_one_active_per_outlet;

-- WHAT REPLACES IT: a node must still be unique BY IDENTITY, which was never in question,
-- and the outlet may now hold a standby beside its holder. The one-holder rule lives in
-- 0050's authority_one_holder_per_outlet and nowhere else, so there is one place to read
-- it rather than two that can disagree.
COMMENT ON TABLE edge.node IS
    'FR-CFG-001E, FR-EDG-018, FR-EDG-024. One or more continuity nodes per outlet — a '
    'holder and its standbys — each bound to one tenant and one outlet, with a device '
    'identity it proves by fingerprint, a scoped service principal, the LAN endpoint it '
    'serves the four screen families at, a reference to where its secrets live (never a '
    'secret), the anchor its signed updates are verified against and what it attested '
    'about its host. WHICH of them may write is edge.authority''s answer, not this '
    'table''s: 0039 allowed only one active node per outlet because nothing could answer '
    'that question yet, and 0050 answers it.';

-- ---------------------------------------------------------------------------
-- REGISTERING A STANDBY
-- ---------------------------------------------------------------------------
--
-- edge.register_node() refused a second node at an outlet only through the index that has
-- just gone, so it needs no change to permit one. What it DOES need is to stop implying
-- that registration confers authority, because now it plainly does not.
COMMENT ON FUNCTION edge.register_node(uuid, uuid, text, uuid, character, uuid, text, text,
                                       character, text, uuid, jsonb) IS
    'FR-CFG-001E, FR-EDG-001, FR-EDG-002A. The only writer of a node. Refuses an outlet '
    'that is not one, an outlet with no declared profile, a profile that says cloud-only, '
    'a principal of the wrong class, and a service inventory short of all five. '
    'REGISTRATION IS NOT AUTHORITY: a registered node may be a standby, and until it holds '
    'a sequence in edge.authority it may not write. That separation is FR-EDG-024''s, and '
    'it is why a second node at an outlet is now permitted.';

-- ---------------------------------------------------------------------------
-- AND A NODE THAT HOLDS NOTHING IS VISIBLY A STANDBY
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.node_role(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (
    node_id     uuid,
    node_code   text,
    role        text,
    sequence    bigint,
    may_write   boolean)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
    SELECT n.id, n.node_code,
           CASE WHEN a.holder_node_id IS NOT NULL THEN 'authority' ELSE 'standby' END,
           a.sequence,
           a.holder_node_id IS NOT NULL
      FROM edge.node n
      LEFT JOIN edge.authority a
             ON a.tenant_id = n.tenant_id
            AND a.holder_node_id = n.id
            AND a.state = 'held'
     WHERE n.tenant_id = p_tenant_id
       AND n.outlet_id = p_outlet_id
       AND n.status = 'active'
     ORDER BY (a.holder_node_id IS NULL), n.node_code;
$$;

COMMENT ON FUNCTION edge.node_role(uuid, uuid) IS
    'FR-EDG-024. Every active node at an outlet and whether it is the authority or a '
    'standby, holder first. An operator about to fence something should be able to see '
    'which is which without reading two tables and joining them by hand.';

GRANT EXECUTE ON FUNCTION edge.node_role(uuid, uuid) TO hospitality_app;
