-- 0004_provision_stations_and_routing.provision.sql — the configuration half (FR-DAT-013)
--
-- APPLIED UNDER THE MIGRATION IDENTITY, AND THAT IS THE POINT OF THE SUFFIX.
--
-- Everything a seed creates goes in through the application role, so every seeded row has
-- to pass the same row level security the running service passes. These rows cannot: 0012
-- grants hospitality_app SELECT and nothing more on fulfillment.station_profile and the
-- routing tables, deliberately, because installing a station is a configuration act and
-- not something the service does while serving. tests/m3b/fixtures.py says so where it
-- writes the same rows as the administrator: "a fixture that needed a wider grant would
-- have been asking for the schema to be loosened."
--
-- So the grant is not loosened. This file runs under the identity that already owns
-- configuration, and tools/seed.py enforces three things about it:
--
--   1. it may write ONLY fulfillment.station_profile, routing_rule and routing_rule_set,
--      so the privileged pass cannot become a general escape hatch for whatever the
--      application role happens not to be allowed to write;
--   2. it may not issue a GRANT, because widening a privilege is a migration;
--   3. after every seed has run, hospitality_app must still hold SELECT and only SELECT
--      on those tables, read back from the catalog rather than assumed.
--
-- WHY THESE ROWS ARE NEEDED AT ALL. Without a station profile the station node seeded in
-- 0003 is inert, and without a routing rule an accepted order routes nowhere — so the
-- order reaches the database and never reaches a kitchen, which is the defect this whole
-- gate exists to close. The floor is product data; the stations that cook from it are
-- configuration; both have to exist before anybody can use the system.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set t_nile     '''44444444-4444-4444-4444-444444444444'''
\set o_h2       '''33330002-0000-4000-8000-000000000002'''
\set o_n1       '''44440001-0000-4000-8000-000000000001'''
\set u_habesha  '''3333aaaa-0000-4000-8000-000000000001'''
\set u_nile     '''4444aaaa-0000-4000-8000-000000000001'''

\set st_hot     '''33334101-0000-4000-8000-000000000001'''
\set st_bar     '''33334102-0000-4000-8000-000000000001'''
\set st_n_hot   '''44444101-0000-4000-8000-000000000001'''
\set c_mains    '''33336101-0000-4000-8000-000000000001'''
\set c_drinks   '''33336102-0000-4000-8000-000000000001'''
\set c_n_mains  '''44446101-0000-4000-8000-000000000001'''
\set rs_h1      '''33336501-0000-4000-8000-000000000001'''
\set rs_n1      '''44446501-0000-4000-8000-000000000001'''

-- =========================================================================
-- Habesha Kitchens, Sarbet: two stations and the rules that reach them
-- =========================================================================
SELECT set_config('app.tenant_id', :t_habesha, false);
SELECT set_config('app.outlet_id', :o_h2, false);

-- The hot kitchen requires an allergy acknowledgement before it may begin preparing; the
-- beverage station does not. Both are the station's own setting rather than a global
-- rule, which is what fulfillment.transition_ticket() reads when it refuses 'preparing'.
INSERT INTO fulfillment.station_profile
    (station_node_id, tenant_id, outlet_id, station_kind, sla_minutes,
     concurrent_ticket_threshold, allergy_acknowledgement_required) VALUES
    (:st_hot::uuid, :t_habesha::uuid, :o_h2::uuid, 'kitchen', 20, 12, true),
    (:st_bar::uuid, :t_habesha::uuid, :o_h2::uuid, 'bar', 8, 20, false);

INSERT INTO fulfillment.routing_rule_set
    (id, tenant_id, outlet_id, version, effective_from, approved_by_user_id)
VALUES (:rs_h1::uuid, :t_habesha::uuid, :o_h2::uuid, 1, now() - interval '1 day', :u_habesha::uuid);

-- Drinks to the bar, mains to the kitchen. Precedence 2 is the catch-all for this menu:
-- a rule set that covers no line refuses it, which is the routing gate working rather
-- than a silent drop.
INSERT INTO fulfillment.routing_rule
    (tenant_id, outlet_id, rule_set_id, precedence, category_id, target_station_node_id) VALUES
    (:t_habesha::uuid, :o_h2::uuid, :rs_h1::uuid, 1, :c_drinks::uuid, :st_bar::uuid),
    (:t_habesha::uuid, :o_h2::uuid, :rs_h1::uuid, 2, :c_mains::uuid,  :st_hot::uuid);

-- =========================================================================
-- Nile: one station, one rule
-- =========================================================================
SELECT set_config('app.tenant_id', :t_nile, false);
SELECT set_config('app.outlet_id', :o_n1, false);

INSERT INTO fulfillment.station_profile
    (station_node_id, tenant_id, outlet_id, station_kind, sla_minutes,
     concurrent_ticket_threshold, allergy_acknowledgement_required)
VALUES (:st_n_hot::uuid, :t_nile::uuid, :o_n1::uuid, 'kitchen', 25, 10, true);

INSERT INTO fulfillment.routing_rule_set
    (id, tenant_id, outlet_id, version, effective_from, approved_by_user_id)
VALUES (:rs_n1::uuid, :t_nile::uuid, :o_n1::uuid, 1, now() - interval '1 day', :u_nile::uuid);

INSERT INTO fulfillment.routing_rule
    (tenant_id, outlet_id, rule_set_id, precedence, category_id, target_station_node_id)
VALUES (:t_nile::uuid, :o_n1::uuid, :rs_n1::uuid, 1, :c_n_mains::uuid, :st_n_hot::uuid);
