-- M1-A verification fixtures.
--
-- Populated deliberately: an empty table passes an isolation test vacuously and
-- proves nothing (FR-SEC-002A). These fixtures create
--   * two tenants, so every cross-tenant assertion has a real foreign row to find
--   * two sibling outlets inside one tenant, so sibling-outlet IDOR has a real target
--   * a branch nested three levels below an outlet, so "configurable depth" is
--     exercised rather than asserted
--
-- Seeded through hospitality_app — the actual runtime role — not through the owner
-- or a superuser (FR-DAT-017). Every insert therefore has to satisfy the same RLS
-- policies the application runs under.

\set ON_ERROR_STOP on

\set t_acme     '''11111111-1111-1111-1111-111111111111'''
\set t_globex   '''22222222-2222-2222-2222-222222222222'''
\set o_a1       '''aaaa0001-0000-4000-8000-000000000001'''
\set o_a2       '''aaaa0002-0000-4000-8000-000000000002'''
\set o_b1       '''bbbb0001-0000-4000-8000-000000000001'''

-- =========================================================================
-- Tenant ACME
-- =========================================================================
SELECT set_config('app.tenant_id', :t_acme, false);
SELECT set_config('app.outlet_id', '', false);

INSERT INTO org.tenant (id, tenant_code, display_name)
VALUES (:t_acme::uuid, 'ACME', 'Acme Hospitality');

-- Above the outlet boundary: tenant context alone is sufficient.
INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('aaaa0100-0000-4000-8000-000000000001'::uuid, :t_acme::uuid, NULL,
        'brand', 'BR-ACME', 'Acme Dining');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('aaaa0200-0000-4000-8000-000000000001'::uuid, :t_acme::uuid,
        'aaaa0100-0000-4000-8000-000000000001'::uuid,
        'legal_entity', 'LE-ACME-01', 'Acme Trading PLC');

-- ---- Outlet A1 -----------------------------------------------------------
-- Creating an outlet requires that outlet's own context: the row is outlet-scoped
-- from the moment it exists, and deny-by-default admits no provisioning bypass.
SELECT set_config('app.outlet_id', :o_a1, false);

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES (:o_a1::uuid, :t_acme::uuid, 'aaaa0200-0000-4000-8000-000000000001'::uuid,
        'outlet', 'OUT-A1', 'Bole Branch');

INSERT INTO org.outlet_profile (outlet_id, tenant_id, timezone)
VALUES (:o_a1::uuid, :t_acme::uuid, 'Africa/Addis_Ababa');

-- Depth 1 below the outlet.
INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('aaaa1101-0000-4000-8000-000000000001'::uuid, :t_acme::uuid, :o_a1::uuid,
        'service_area', 'SA-A1-GF', 'Ground Floor');

-- Depth 2: a service area inside a service area. Nothing in the schema caps this.
INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('aaaa1102-0000-4000-8000-000000000001'::uuid, :t_acme::uuid,
        'aaaa1101-0000-4000-8000-000000000001'::uuid,
        'service_area', 'SA-A1-TER', 'Terrace');

-- Depth 3: a dining table below the nested area.
INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('aaaa1103-0000-4000-8000-000000000001'::uuid, :t_acme::uuid,
        'aaaa1102-0000-4000-8000-000000000001'::uuid,
        'dining_table', 'T-01', 'Terrace Table 01');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('aaaa1104-0000-4000-8000-000000000001'::uuid, :t_acme::uuid, :o_a1::uuid,
        'preparation_station', 'PS-A1-HOT', 'Hot Kitchen');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('aaaa1105-0000-4000-8000-000000000001'::uuid, :t_acme::uuid, :o_a1::uuid,
        'device', 'DEV-A1-POS1', 'Bole POS 1');

INSERT INTO org.device_registration (device_id, tenant_id, outlet_id, registration_code)
VALUES ('aaaa1105-0000-4000-8000-000000000001'::uuid, :t_acme::uuid, :o_a1::uuid, 'REG-A1-0001');

-- ---- Outlet A2 — the sibling ---------------------------------------------
SELECT set_config('app.outlet_id', :o_a2, false);

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES (:o_a2::uuid, :t_acme::uuid, 'aaaa0200-0000-4000-8000-000000000001'::uuid,
        'outlet', 'OUT-A2', 'Piassa Branch');

INSERT INTO org.outlet_profile (outlet_id, tenant_id, timezone)
VALUES (:o_a2::uuid, :t_acme::uuid, 'Africa/Addis_Ababa');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('aaaa2101-0000-4000-8000-000000000002'::uuid, :t_acme::uuid, :o_a2::uuid,
        'service_area', 'SA-A2-MAIN', 'Main Hall');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('aaaa2102-0000-4000-8000-000000000002'::uuid, :t_acme::uuid,
        'aaaa2101-0000-4000-8000-000000000002'::uuid,
        'dining_table', 'T-11', 'Main Hall Table 11');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('aaaa2103-0000-4000-8000-000000000002'::uuid, :t_acme::uuid, :o_a2::uuid,
        'device', 'DEV-A2-POS1', 'Piassa POS 1');

INSERT INTO org.device_registration (device_id, tenant_id, outlet_id, registration_code)
VALUES ('aaaa2103-0000-4000-8000-000000000002'::uuid, :t_acme::uuid, :o_a2::uuid, 'REG-A2-0001');

-- =========================================================================
-- Tenant GLOBEX — the foreign tenant
-- =========================================================================
SELECT set_config('app.tenant_id', :t_globex, false);
SELECT set_config('app.outlet_id', '', false);

INSERT INTO org.tenant (id, tenant_code, display_name)
VALUES (:t_globex::uuid, 'GLOBEX', 'Globex Restaurants');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('bbbb0100-0000-4000-8000-000000000001'::uuid, :t_globex::uuid, NULL,
        'brand', 'BR-GLOBEX', 'Globex Eats');

SELECT set_config('app.outlet_id', :o_b1, false);

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES (:o_b1::uuid, :t_globex::uuid, 'bbbb0100-0000-4000-8000-000000000001'::uuid,
        'outlet', 'OUT-B1', 'Dubai Branch');

INSERT INTO org.outlet_profile (outlet_id, tenant_id, timezone)
VALUES (:o_b1::uuid, :t_globex::uuid, 'Asia/Dubai');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('bbbb1101-0000-4000-8000-000000000001'::uuid, :t_globex::uuid, :o_b1::uuid,
        'service_area', 'SA-B1-MAIN', 'Marina Hall');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('bbbb1102-0000-4000-8000-000000000001'::uuid, :t_globex::uuid,
        'bbbb1101-0000-4000-8000-000000000001'::uuid,
        'dining_table', 'T-99', 'Marina Table 99');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('bbbb1103-0000-4000-8000-000000000001'::uuid, :t_globex::uuid, :o_b1::uuid,
        'device', 'DEV-B1-POS1', 'Dubai POS 1');

INSERT INTO org.device_registration (device_id, tenant_id, outlet_id, registration_code)
VALUES ('bbbb1103-0000-4000-8000-000000000001'::uuid, :t_globex::uuid, :o_b1::uuid, 'REG-B1-0001');

SELECT set_config('app.tenant_id', '', false);
SELECT set_config('app.outlet_id', '', false);
