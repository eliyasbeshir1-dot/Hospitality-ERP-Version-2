-- 0011_the_demonstration_floor_has_node_hardware.sql — the device and the principal
--
-- M5a gives the demonstration floor a continuity node, and it takes three seeds to do it
-- because the rows belong to three different identities. That is not ceremony: the rule
-- tools/seed.py enforces is that seeded content passes the same row level security the
-- running service passes, and only the rows an INSTALLER decides go in privileged.
--
--   0011 (this file, application role)  the device in the org tree, and the principal
--                                       the node's services authenticate as
--   0012 (migration identity)           the deployment profile, the node itself, and the
--                                       wording a restriction is explained in
--   0013 (application role)             the outlet's asset register
--
-- The node cannot be registered before its device and principal exist, and the asset
-- register cannot link to the node before the node exists, so the order is forced by the
-- data rather than chosen.
--
-- WHY THE DEVICE IS AN org.org_node. A POS terminal is already a device in the org tree
-- (pos.terminal keys on one), so an outlet has ONE answer to "what hardware is here"
-- rather than a second register that drifts from the first. The continuity node is
-- hardware in an outlet; it goes where the other hardware is.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set o_h1       '''33330001-0000-4000-8000-000000000001'''
\set o_h2       '''33330002-0000-4000-8000-000000000002'''

-- KAZANCHIS
SELECT set_config('app.tenant_id', :t_habesha, false);
SELECT set_config('app.outlet_id', :o_h1, false);

INSERT INTO org.org_node (id, tenant_id, parent_id, outlet_id, kind, reference_code, display_name)
VALUES ('3333ed01-0000-4000-8000-0000000ed001', :t_habesha::uuid, :o_h1::uuid, :o_h1::uuid,
        'device', 'DEV-NODE-H1', 'Kazanchis continuity node');

INSERT INTO identity.service_principal (id, tenant_id, principal_code, class)
VALUES ('3333ed11-0000-4000-8000-0000000ed011', :t_habesha::uuid, 'SP-NODE-H1', 'edge_node');

INSERT INTO identity.service_principal_scope
    (tenant_id, service_principal_id, outlet_id, action_code)
VALUES (:t_habesha::uuid, '3333ed11-0000-4000-8000-0000000ed011'::uuid, :o_h1::uuid,
        'sync.exchange');

-- SARBET
SELECT set_config('app.outlet_id', :o_h2, false);

INSERT INTO org.org_node (id, tenant_id, parent_id, outlet_id, kind, reference_code, display_name)
VALUES ('3333ed02-0000-4000-8000-0000000ed002', :t_habesha::uuid, :o_h2::uuid, :o_h2::uuid,
        'device', 'DEV-NODE-H2', 'Sarbet continuity node');

INSERT INTO identity.service_principal (id, tenant_id, principal_code, class)
VALUES ('3333ed12-0000-4000-8000-0000000ed012', :t_habesha::uuid, 'SP-NODE-H2', 'edge_node');

INSERT INTO identity.service_principal_scope
    (tenant_id, service_principal_id, outlet_id, action_code)
VALUES (:t_habesha::uuid, '3333ed12-0000-4000-8000-0000000ed012'::uuid, :o_h2::uuid,
        'sync.exchange');

SELECT set_config('app.outlet_id', '', false);
SELECT set_config('app.tenant_id', '', false);
