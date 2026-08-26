-- 0001_demonstration_tenants.sql — seed data (FR-DAT-013)
--
-- Two differently branded tenants, one of them with two outlets. The point is to prove
-- the system carries no house style and no single-outlet assumption: nothing in the
-- schema knows either brand's name, and neither outlet can see the other's rows.
--
-- Seeds are NOT migrations. They create data, not structure, they differ per
-- environment, and they must never join the checksum-locked history (FR-DAT-016).
--
-- Applied through hospitality_app, so every insert passes the same RLS the application
-- runs under. Structure only: Amharic and Arabic content arrives at M2 as extra
-- config.reason_code_label rows, with no schema change.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set t_nile     '''44444444-4444-4444-4444-444444444444'''
\set o_h1       '''33330001-0000-4000-8000-000000000001'''
\set o_h2       '''33330002-0000-4000-8000-000000000002'''
\set o_n1       '''44440001-0000-4000-8000-000000000001'''
\set u_habesha  '''3333aaaa-0000-4000-8000-000000000001'''
\set u_nile     '''4444aaaa-0000-4000-8000-000000000001'''

-- =========================================================================
-- Tenant one: Habesha Kitchens — two outlets
-- =========================================================================
SELECT set_config('app.tenant_id', :t_habesha, false);
SELECT set_config('app.outlet_id', '', false);

INSERT INTO org.tenant (id, tenant_code, display_name)
VALUES (:t_habesha::uuid, 'HABESHA', 'Habesha Kitchens');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('33330100-0000-4000-8000-000000000001'::uuid, :t_habesha::uuid, NULL,
        'brand', 'BR-HAB', 'Habesha Kitchens');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('33330200-0000-4000-8000-000000000001'::uuid, :t_habesha::uuid,
        '33330100-0000-4000-8000-000000000001'::uuid,
        'legal_entity', 'LE-HAB-01', 'Habesha Kitchens PLC');

INSERT INTO identity.user_account (id, tenant_id, staff_number, display_name)
VALUES (:u_habesha::uuid, :t_habesha::uuid, 'ADM-0001', 'Habesha Administrator');

SELECT set_config('app.outlet_id', :o_h1, false);
INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES (:o_h1::uuid, :t_habesha::uuid, '33330200-0000-4000-8000-000000000001'::uuid,
        'outlet', 'OUT-H1', 'Kazanchis Branch');
INSERT INTO org.outlet_profile (outlet_id, tenant_id, timezone)
VALUES (:o_h1::uuid, :t_habesha::uuid, 'Africa/Addis_Ababa');
INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('33331101-0000-4000-8000-000000000001'::uuid, :t_habesha::uuid, :o_h1::uuid,
        'service_area', 'SA-H1-MAIN', 'Main Hall');
-- Outlet-scoped rows are written here, under this outlet's own context. Writing them
-- later with the context cleared is refused by RLS, which is the correct behaviour.
INSERT INTO config.number_series (tenant_id, outlet_id, document_type, fiscal_period, prefix)
VALUES (:t_habesha::uuid, :o_h1::uuid, 'check', '2026', 'H1-');

SELECT set_config('app.outlet_id', :o_h2, false);
INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES (:o_h2::uuid, :t_habesha::uuid, '33330200-0000-4000-8000-000000000001'::uuid,
        'outlet', 'OUT-H2', 'Sarbet Branch');
INSERT INTO org.outlet_profile (outlet_id, tenant_id, timezone)
VALUES (:o_h2::uuid, :t_habesha::uuid, 'Africa/Addis_Ababa');
INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('33332101-0000-4000-8000-000000000002'::uuid, :t_habesha::uuid, :o_h2::uuid,
        'service_area', 'SA-H2-MAIN', 'Ground Floor');
INSERT INTO config.number_series (tenant_id, outlet_id, document_type, fiscal_period, prefix)
VALUES (:t_habesha::uuid, :o_h2::uuid, 'check', '2026', 'H2-');
-- This outlet has waiter service switched off, so outlet scope can be seen overriding
-- the tenant-wide grant above.
INSERT INTO config.entitlement (tenant_id, outlet_id, scope_kind, scope_node_id, feature_key, granted)
VALUES (:t_habesha::uuid, :o_h2::uuid, 'outlet', :o_h2::uuid, 'waiter_service', false);

-- Configuration: branding, locale, currency and timezone, all effective-dated and
-- carrying the actor who made the change and the actor who approved it.
SELECT set_config('app.outlet_id', '', false);
INSERT INTO config.configuration_version
    (tenant_id, scope_kind, category, version, payload, effective_from,
     actor_id, approved_by_id, approved_at)
VALUES
    (:t_habesha::uuid, 'tenant', 'branding', 1,
     '{"display_name":"Habesha Kitchens","accent":"#7B241C","logo_ref":"brand/habesha"}'::jsonb,
     now(), :u_habesha::uuid, :u_habesha::uuid, now()),
    (:t_habesha::uuid, 'tenant', 'locale', 1,
     '{"default":"en","available":["en","am","ar"]}'::jsonb,
     now(), :u_habesha::uuid, :u_habesha::uuid, now()),
    (:t_habesha::uuid, 'tenant', 'currency', 1,
     '{"code":"ETB"}'::jsonb, now(), :u_habesha::uuid, :u_habesha::uuid, now()),
    (:t_habesha::uuid, 'tenant', 'timezone', 1,
     '{"iana":"Africa/Addis_Ababa"}'::jsonb, now(), :u_habesha::uuid, :u_habesha::uuid, now()),
    (:t_habesha::uuid, 'tenant', 'tax', 1,
     '{"vat_percentage":"15.0000","rounding_mode":"half_up"}'::jsonb,
     now(), :u_habesha::uuid, :u_habesha::uuid, now());

-- A Phase 1 policy, referencing the identity-owned governed action by key.
INSERT INTO config.policy
    (tenant_id, category, version, payload, governed_action_code, effective_from,
     actor_id, approved_by_id, approved_at)
VALUES
    (:t_habesha::uuid, 'discount', 1,
     '{"max_percentage":"20.0000","above_requires_step_up":true}'::jsonb,
     'configuration.modify', now(), :u_habesha::uuid, :u_habesha::uuid, now()),
    (:t_habesha::uuid, 'tip', 1,
     '{"default_selected":false,"separate_from_bill":true}'::jsonb,
     NULL, now(), :u_habesha::uuid, :u_habesha::uuid, now());

-- Entitlements: explicit grants only. Anything not named here is denied.
INSERT INTO config.entitlement (tenant_id, scope_kind, feature_key, granted) VALUES
    (:t_habesha::uuid, 'tenant', 'qr_ordering',      true),
    (:t_habesha::uuid, 'tenant', 'waiter_service',   true),
    (:t_habesha::uuid, 'tenant', 'kitchen_display',  true);
INSERT INTO config.retention_policy
    (tenant_id, target_schema, target_table, age_column, retain_for, action)
VALUES (:t_habesha::uuid, 'identity', 'auth_attempt', 'attempted_at', interval '90 days', 'purge');

-- =========================================================================
-- Tenant two: Nile Coffee House — a different brand entirely
-- =========================================================================
SELECT set_config('app.tenant_id', :t_nile, false);
SELECT set_config('app.outlet_id', '', false);

INSERT INTO org.tenant (id, tenant_code, display_name)
VALUES (:t_nile::uuid, 'NILE', 'Nile Coffee House');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('44440100-0000-4000-8000-000000000001'::uuid, :t_nile::uuid, NULL,
        'brand', 'BR-NILE', 'Nile Coffee House');

INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES ('44440200-0000-4000-8000-000000000001'::uuid, :t_nile::uuid,
        '44440100-0000-4000-8000-000000000001'::uuid,
        'legal_entity', 'LE-NILE-01', 'Nile Hospitality FZE');

INSERT INTO identity.user_account (id, tenant_id, staff_number, display_name)
VALUES (:u_nile::uuid, :t_nile::uuid, 'ADM-0001', 'Nile Administrator');

SELECT set_config('app.outlet_id', :o_n1, false);
INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
VALUES (:o_n1::uuid, :t_nile::uuid, '44440200-0000-4000-8000-000000000001'::uuid,
        'outlet', 'OUT-N1', 'Marina Branch');
INSERT INTO org.outlet_profile (outlet_id, tenant_id, timezone)
VALUES (:o_n1::uuid, :t_nile::uuid, 'Asia/Dubai');
INSERT INTO config.number_series (tenant_id, outlet_id, document_type, fiscal_period, prefix)
VALUES (:t_nile::uuid, :o_n1::uuid, 'check', '2026', 'N1-');
SELECT set_config('app.outlet_id', '', false);
INSERT INTO config.configuration_version
    (tenant_id, scope_kind, category, version, payload, effective_from,
     actor_id, approved_by_id, approved_at)
VALUES
    (:t_nile::uuid, 'tenant', 'branding', 1,
     '{"display_name":"Nile Coffee House","accent":"#1B4F72","logo_ref":"brand/nile"}'::jsonb,
     now(), :u_nile::uuid, :u_nile::uuid, now()),
    (:t_nile::uuid, 'tenant', 'locale', 1,
     '{"default":"ar","available":["ar","en"]}'::jsonb,
     now(), :u_nile::uuid, :u_nile::uuid, now()),
    (:t_nile::uuid, 'tenant', 'currency', 1,
     '{"code":"AED"}'::jsonb, now(), :u_nile::uuid, :u_nile::uuid, now()),
    (:t_nile::uuid, 'tenant', 'timezone', 1,
     '{"iana":"Asia/Dubai"}'::jsonb, now(), :u_nile::uuid, :u_nile::uuid, now());

INSERT INTO config.entitlement (tenant_id, scope_kind, feature_key, granted) VALUES
    (:t_nile::uuid, 'tenant', 'qr_ordering', true);

SELECT set_config('app.tenant_id', '', false);
SELECT set_config('app.outlet_id', '', false);
