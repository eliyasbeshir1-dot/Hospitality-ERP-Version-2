-- 0040: an outlet knows what hardware it has, and who to call about it
--
-- FR-OPS-018 asks for an outlet inventory of the continuity node, routers, access points,
-- POS terminals, KDS devices and printers, each with an assigned location and a support
-- owner. Six classes, and the gate-local behaviour is that the register lists all six.
--
-- THE TRAP THIS MIGRATION IS BUILT TO AVOID. Three of those six are already registered
-- elsewhere in this database: a printer is a docs.printer, a POS terminal is a
-- pos.terminal, and the continuity node is an edge.node. A register that re-typed them
-- would be a SECOND answer to "what printers does this outlet have", and the first thing
-- that happens to a second answer is that it stops matching the first. This repository has
-- spent four gates removing second answers — the fourth fixture-owned catalogue, the three
-- copies of the route-block reader, the census pooling two questions — so this register
-- POINTS at those rows rather than restating them, and a check refuses an asset whose
-- class has a register and whose link is empty.
--
-- Routers and access points have no register anywhere, because nothing in Phase 1 talks to
-- them. Those two are recorded here directly, and that asymmetry is the honest shape: the
-- register is the union of what other tables already know and what only this table knows.
--
-- WHAT A SUPPORT OWNER IS. Sometimes a member of staff, and sometimes a vendor who has
-- never had an account here. Forcing both through identity.user_account would invent
-- accounts for people outside the business; allowing only free text would lose the link
-- for the ones inside it. So it is one or the other, exactly, and the check says so.

CREATE SCHEMA ops;

COMMENT ON SCHEMA ops IS
    'The outlet''s physical estate: the continuity node, routers, access points, POS '
    'terminals, KDS devices and printers, each with a location and a support owner. '
    'FR-OPS-018.';

-- The six classes FR-OPS-018 names, and no others.
CREATE TYPE ops.asset_class AS ENUM (
    'continuity_node', 'router', 'access_point', 'pos_terminal', 'kds_device', 'printer');

CREATE TABLE ops.outlet_asset (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,

    asset_class ops.asset_class NOT NULL,
    asset_tag   text NOT NULL,
    display_name text NOT NULL,

    -- FR-OPS-018's "assigned location". Free text on purpose: an outlet describes where a
    -- router is in the words its own staff use, and an enum of rooms would be wrong at the
    -- second outlet.
    location text NOT NULL,

    -- The support owner: a member of staff, or somebody outside the business. Exactly one.
    support_owner_user_id uuid,
    support_owner_external text,

    -- WHERE THE ASSET IS ALREADY REGISTERED, IT IS REGISTERED THERE. These are the link,
    -- not a copy: no display name, connection or serial is restated from the register that
    -- owns it.
    linked_node_id            uuid,
    linked_terminal_device_id uuid,
    linked_printer_id         uuid,

    status org.lifecycle_status NOT NULL DEFAULT 'active',
    recorded_by_user_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    row_version bigint NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT outlet_asset_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT outlet_asset_tag_unique UNIQUE (tenant_id, outlet_id, asset_tag),
    CONSTRAINT outlet_asset_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT outlet_asset_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT outlet_asset_recorder_fk FOREIGN KEY (tenant_id, recorded_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT outlet_asset_node_fk FOREIGN KEY (tenant_id, linked_node_id)
        REFERENCES edge.node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT outlet_asset_terminal_fk FOREIGN KEY (tenant_id, linked_terminal_device_id)
        REFERENCES pos.terminal (tenant_id, device_id) ON DELETE RESTRICT,
    CONSTRAINT outlet_asset_printer_fk FOREIGN KEY (tenant_id, linked_printer_id)
        REFERENCES docs.printer (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT outlet_asset_location_is_stated CHECK (length(trim(location)) > 0),
    CONSTRAINT outlet_asset_tag_is_stated CHECK (length(trim(asset_tag)) > 0),

    -- Exactly one support owner, named one way or the other.
    CONSTRAINT outlet_asset_has_one_support_owner CHECK (
        (support_owner_user_id IS NOT NULL)::int
      + (support_owner_external IS NOT NULL AND length(trim(support_owner_external)) > 0)::int = 1),

    -- A CLASS THAT HAS A REGISTER MUST POINT AT IT, and a class that has none must point
    -- at nothing. Both halves, because either alone permits the drift this table exists to
    -- avoid: the first stops a re-typed printer, the second stops a router pretending to
    -- be one.
    CONSTRAINT outlet_asset_link_matches_class CHECK (
        CASE asset_class
          WHEN 'continuity_node' THEN linked_node_id IS NOT NULL
                                  AND linked_terminal_device_id IS NULL
                                  AND linked_printer_id IS NULL
          WHEN 'pos_terminal'    THEN linked_terminal_device_id IS NOT NULL
                                  AND linked_node_id IS NULL
                                  AND linked_printer_id IS NULL
          WHEN 'printer'         THEN linked_printer_id IS NOT NULL
                                  AND linked_node_id IS NULL
                                  AND linked_terminal_device_id IS NULL
          ELSE linked_node_id IS NULL
           AND linked_terminal_device_id IS NULL
           AND linked_printer_id IS NULL
        END),

    CONSTRAINT outlet_asset_row_version_positive CHECK (row_version > 0)
);

COMMENT ON TABLE ops.outlet_asset IS
    'FR-OPS-018. The outlet''s physical estate across the six named classes, each with a '
    'location and exactly one support owner. Classes that are already registered '
    'elsewhere — the node, POS terminals, printers — are LINKED rather than restated, so '
    'this register cannot drift from the tables that own those rows.';

COMMENT ON COLUMN ops.outlet_asset.support_owner_external IS
    'The support owner when they are not a user of this system — a vendor, a landlord''s '
    'contractor. Free text because inventing an account for them would be worse.';

CREATE INDEX outlet_asset_class_idx
    ON ops.outlet_asset (tenant_id, outlet_id, asset_class) WHERE status = 'active';

CREATE TRIGGER outlet_asset_row_version
    BEFORE UPDATE ON ops.outlet_asset
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

ALTER TABLE ops.outlet_asset ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.outlet_asset FORCE ROW LEVEL SECURITY;
CREATE POLICY outlet_asset_isolation ON ops.outlet_asset FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- WHAT THE REGISTER IS MISSING (FR-OPS-018)
-- ---------------------------------------------------------------------------

-- The gate-local behaviour is that the register LISTS ALL SIX CLASSES, which is a claim
-- about absence — and absence is what a SELECT over a table cannot show you. An operator
-- reading six rows cannot tell whether the seventh class is missing or whether there are
-- only six; a reader that starts from the enum can.
--
-- The same shape as edge.node_health(): every class always, and the one nobody has
-- recorded is named rather than silently absent.
CREATE FUNCTION ops.asset_register(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (
    asset_class ops.asset_class,
    recorded    integer,
    is_covered  boolean)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'ops', 'public'
AS $$
    SELECT c.asset_class,
           count(a.id)::integer,
           count(a.id) > 0
      FROM unnest(enum_range(NULL::ops.asset_class)) AS c(asset_class)
      LEFT JOIN ops.outlet_asset a
             ON a.tenant_id   = p_tenant_id
            AND a.outlet_id   = p_outlet_id
            AND a.asset_class = c.asset_class
            AND a.status      = 'active'
     GROUP BY c.asset_class
     ORDER BY c.asset_class;
$$;

COMMENT ON FUNCTION ops.asset_register(uuid, uuid) IS
    'FR-OPS-018. All six classes, always, with how many of each the outlet has recorded '
    'and whether the class is covered at all. A register read as rows can only show what '
    'is there; this shows what is not.';

GRANT USAGE ON SCHEMA ops TO hospitality_app;
GRANT SELECT, INSERT, UPDATE ON ops.outlet_asset TO hospitality_app;
GRANT EXECUTE ON FUNCTION ops.asset_register(uuid, uuid) TO hospitality_app;
