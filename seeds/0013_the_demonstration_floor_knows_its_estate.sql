-- 0013_the_demonstration_floor_knows_its_estate.sql — the outlet asset register
--
-- FR-OPS-018's register, for the two Habesha outlets. Written as the application role
-- because ops.outlet_asset is a table the service can write: an estate changes when a
-- router is replaced, and that is not an installation-only act.
--
-- IT COMES AFTER 0012 BECAUSE OF THE LINK. Three of the six asset classes are already
-- registered elsewhere — the node is an edge.node, a POS terminal is a pos.terminal, a
-- printer is a docs.printer — and ops.outlet_asset points at those rows rather than
-- restating them. So the node has to exist before the register can name it.
--
-- WHAT IS HERE AND WHAT IS NOT. Four classes are seeded: the continuity node, the router,
-- the access point and the kitchen display. The remaining two are NOT, and the reason is
-- worth stating rather than leaving as a gap somebody finds later:
--
--   printer       the demonstration floor has no seeded docs.printer. M4-C's suites
--                 register their own, and seeding one here would change the counts those
--                 suites assert over — a seed that breaks an earlier gate's evidence to
--                 make a later gate's register look complete is the wrong trade.
--   pos_terminal  the same, for pos.terminal.
--
-- So the seeded register covers four of six, and FR-OPS-018's "all six classes" is proved
-- in tests/m5a, which registers a printer and a terminal of its own and then asserts that
-- ops.asset_register() reports every class covered. That is a real proof over a real
-- outlet; it is simply not this file's job.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set o_h1       '''33330001-0000-4000-8000-000000000001'''
\set o_h2       '''33330002-0000-4000-8000-000000000002'''
\set u_habesha  '''3333aaaa-0000-4000-8000-000000000001'''

-- KAZANCHIS
SELECT set_config('app.tenant_id', :t_habesha, false);
SELECT set_config('app.outlet_id', :o_h1, false);

INSERT INTO ops.outlet_asset
    (tenant_id, outlet_id, asset_class, asset_tag, display_name, location,
     support_owner_user_id, linked_node_id, recorded_by_user_id)
SELECT :t_habesha::uuid, :o_h1::uuid, 'continuity_node', 'AST-H1-NODE',
       'Kazanchis continuity node', 'Back office, upper shelf',
       :u_habesha::uuid, n.id, :u_habesha::uuid
  FROM edge.node n
 WHERE n.tenant_id = :t_habesha::uuid AND n.node_code = 'NODE-H1';

INSERT INTO ops.outlet_asset
    (tenant_id, outlet_id, asset_class, asset_tag, display_name, location,
     support_owner_external, recorded_by_user_id)
VALUES
 (:t_habesha::uuid, :o_h1::uuid, 'router', 'AST-H1-RTR', 'Outlet router',
  'Back office, upper shelf', 'Zerihun Networks PLC', :u_habesha::uuid),
 (:t_habesha::uuid, :o_h1::uuid, 'access_point', 'AST-H1-AP1', 'Dining room access point',
  'Dining room ceiling, above table 4', 'Zerihun Networks PLC', :u_habesha::uuid),
 (:t_habesha::uuid, :o_h1::uuid, 'kds_device', 'AST-H1-KDS', 'Kitchen display',
  'Hot line, above the pass', 'Zerihun Networks PLC', :u_habesha::uuid);

-- SARBET
SELECT set_config('app.outlet_id', :o_h2, false);

INSERT INTO ops.outlet_asset
    (tenant_id, outlet_id, asset_class, asset_tag, display_name, location,
     support_owner_user_id, linked_node_id, recorded_by_user_id)
SELECT :t_habesha::uuid, :o_h2::uuid, 'continuity_node', 'AST-H2-NODE',
       'Sarbet continuity node', 'Manager''s office, wall bracket',
       :u_habesha::uuid, n.id, :u_habesha::uuid
  FROM edge.node n
 WHERE n.tenant_id = :t_habesha::uuid AND n.node_code = 'NODE-H2';

INSERT INTO ops.outlet_asset
    (tenant_id, outlet_id, asset_class, asset_tag, display_name, location,
     support_owner_external, recorded_by_user_id)
VALUES
 (:t_habesha::uuid, :o_h2::uuid, 'router', 'AST-H2-RTR', 'Outlet router',
  'Manager''s office, wall bracket', 'Zerihun Networks PLC', :u_habesha::uuid),
 (:t_habesha::uuid, :o_h2::uuid, 'access_point', 'AST-H2-AP1', 'Dining room access point',
  'Dining room ceiling, centre', 'Zerihun Networks PLC', :u_habesha::uuid),
 (:t_habesha::uuid, :o_h2::uuid, 'kds_device', 'AST-H2-KDS', 'Kitchen display',
  'Hot line, above the pass', 'Zerihun Networks PLC', :u_habesha::uuid);

SELECT set_config('app.outlet_id', '', false);
SELECT set_config('app.tenant_id', '', false);
