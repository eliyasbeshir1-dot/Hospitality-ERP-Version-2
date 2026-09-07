-- 0003_demonstration_floor_and_menu.sql — the product seed (FR-DAT-013)
--
-- WHAT WAS MISSING, AND WHY NOTHING CAUGHT IT. 0001 seeds two tenants, four outlets and
-- two service areas, and every slice suite passed against it, because every slice suite
-- brings its own fixtures. Deploy the service against a migrated-and-seeded database and
-- a guest surface renders an empty menu, because there was no menu: zero sellable items,
-- zero dining tables, zero QR tokens, zero preparation stations. The floor existed only
-- inside the tests that built it, so no guest link could be issued against a running
-- instance and no order could reach a kitchen. Found by trying to use the system.
--
-- This file is PRODUCT DATA, not a fixture. It is applied by tools/seed.py, in order,
-- recorded and checksum-locked, and never through psql directly — the bypass that caused
-- the M3-C failure. Content goes in through hospitality_app, so every row below passes
-- the same row level security the running service passes.
--
-- THREE LANGUAGES ON PURPOSE. English, Amharic and Arabic content is carried for every
-- customer-visible name, because a demonstration that ships one language proves the
-- schema can hold that language. The point of the pair of tenants in 0001 was that the
-- system carries no house style; the point of the three locales here is that it carries
-- no house language either.
--
-- THE DEMONSTRATION CREDENTIALS ARE PUBLISHED, DELIBERATELY. The passwords below are
-- printed in this header because they are demonstration data and must never be mistaken
-- for a secret. They are stored scrypt-stretched with a per-credential salt, under the
-- constraint migration 0033 added, so this seed also demonstrates that the storage rule
-- is real: a row here could not be written as a bare sha-256 digest even if it tried.
--
--     kitchen@habesha.example / Habesha!Cook1      (station operator, Sarbet)
--     manager@habesha.example / Habesha!Manager1   (manager, Sarbet)
--     server@habesha.example  / Habesha!Server1    (server, Sarbet)
--     manager@nile.example    / Nile!Manager1      (manager, Nile outlet)
--     quick PIN 4417 for the kitchen account, on the registered Sarbet terminal
--     quick PIN 7731 for the manager account, on the same terminal
--
-- The salts and digests are literals rather than derived at apply time, because a seed
-- must produce the same bytes on every machine that applies it: a random salt chosen
-- during apply would make this file's checksum meaningless.
--
-- WHY SARBET AND NOT KAZANCHIS. The test fixtures build their menu on Kazanchis —
-- tests/m2a/fixtures.py owns 'ALLDAY' there, with SKU-DORO-01 and SKU-TIBS-02 — and
-- seeds and fixtures share one database. The first version of this file put the
-- demonstration menu on the same outlet and the run died on menu_code_unique. Product
-- data and test data are not the same thing and must not compete for one namespace:
-- the demonstration floor is Sarbet, the modifier group is DEMO-SPICE rather than the
-- fixtures' SPICE, and the station and table codes carry H2. Nile is untouched by any
-- fixture, so it needs none of this.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set t_nile     '''44444444-4444-4444-4444-444444444444'''
\set o_h1       '''33330001-0000-4000-8000-000000000001'''
\set o_h2       '''33330002-0000-4000-8000-000000000002'''
\set o_n1       '''44440001-0000-4000-8000-000000000001'''
\set u_habesha  '''3333aaaa-0000-4000-8000-000000000001'''
\set u_nile     '''4444aaaa-0000-4000-8000-000000000001'''

\set sa_h1      '''33331101-0000-4000-8000-000000000001'''
\set sa_h2      '''33332101-0000-4000-8000-000000000002'''

-- Staff
\set u_h1_mgr   '''3333cccc-0000-4000-8000-000000000001'''
\set u_h1_cook  '''3333cccc-0000-4000-8000-000000000002'''
\set u_h1_srv   '''3333cccc-0000-4000-8000-000000000003'''
\set u_n1_mgr   '''4444cccc-0000-4000-8000-000000000001'''
\set r_manager  '''3333dddd-0000-4000-8000-000000000001'''
\set r_cook     '''3333dddd-0000-4000-8000-000000000002'''
\set r_server   '''3333dddd-0000-4000-8000-000000000003'''
\set r_n_mgr    '''4444dddd-0000-4000-8000-000000000001'''

-- The floor
\set st_hot     '''33334101-0000-4000-8000-000000000001'''
\set st_bar     '''33334102-0000-4000-8000-000000000001'''
\set dev_h1     '''33334201-0000-4000-8000-000000000001'''
\set tbl_h1_01  '''33335101-0000-4000-8000-000000000001'''
\set tbl_h1_02  '''33335102-0000-4000-8000-000000000001'''
\set tbl_h1_03  '''33335103-0000-4000-8000-000000000001'''
\set tbl_h2_01  '''33335201-0000-4000-8000-000000000002'''
\set tbl_n1_01  '''44445101-0000-4000-8000-000000000001'''

-- The menu
\set m_h1       '''33336001-0000-4000-8000-000000000001'''
\set c_mains    '''33336101-0000-4000-8000-000000000001'''
\set c_drinks   '''33336102-0000-4000-8000-000000000001'''
\set i_doro     '''33336201-0000-4000-8000-000000000001'''
\set i_tibs     '''33336202-0000-4000-8000-000000000001'''
\set i_shiro    '''33336203-0000-4000-8000-000000000001'''
\set i_coffee   '''33336204-0000-4000-8000-000000000001'''
\set v_doro_f   '''33336301-0000-4000-8000-000000000001'''
\set v_doro_h   '''33336302-0000-4000-8000-000000000001'''
\set v_tibs_f   '''33336303-0000-4000-8000-000000000001'''
\set v_shiro_f  '''33336304-0000-4000-8000-000000000001'''
\set v_coffee_s '''33336305-0000-4000-8000-000000000001'''
\set mg_spice   '''33336401-0000-4000-8000-000000000001'''
\set mo_mild    '''33336402-0000-4000-8000-000000000001'''
\set mo_hot     '''33336403-0000-4000-8000-000000000001'''
\set rs_h1      '''33336501-0000-4000-8000-000000000001'''

-- Nile, second tenant, deliberately smaller: enough to prove nothing here is house style.
\set m_n1       '''44446001-0000-4000-8000-000000000001'''
\set c_n_mains  '''44446101-0000-4000-8000-000000000001'''
\set i_n_fish   '''44446201-0000-4000-8000-000000000001'''
\set v_n_fish   '''44446301-0000-4000-8000-000000000001'''
\set st_n_hot   '''44444101-0000-4000-8000-000000000001'''
\set sa_n1      '''44441101-0000-4000-8000-000000000001'''
\set rs_n1      '''44446501-0000-4000-8000-000000000001'''

-- =========================================================================
-- Tenant one: Habesha Kitchens, SARBET branch
-- =========================================================================
SELECT set_config('app.tenant_id', :t_habesha, false);
SELECT set_config('app.outlet_id', :o_h2, false);

-- ---- Staff who can actually log in -------------------------------------
-- The roles a kitchen needs, and no more. Entitlements are configuration and were seeded
-- at 0001; these are the subjects that carry them.
INSERT INTO identity.role (id, tenant_id, role_code, display_name) VALUES
    (:r_manager::uuid, :t_habesha::uuid, 'OUTLET_MANAGER', 'Outlet Manager'),
    (:r_cook::uuid,    :t_habesha::uuid, 'STATION_OPERATOR', 'Station Operator'),
    (:r_server::uuid,  :t_habesha::uuid, 'SERVER', 'Server');

INSERT INTO identity.user_account (id, tenant_id, staff_number, display_name) VALUES
    (:u_h1_mgr::uuid,  :t_habesha::uuid, 'MGR-0001',  'Sarbet Manager'),
    (:u_h1_cook::uuid, :t_habesha::uuid, 'COOK-0001', 'Sarbet Kitchen'),
    (:u_h1_srv::uuid,  :t_habesha::uuid, 'SRV-0001',  'Sarbet Server');

INSERT INTO identity.membership (tenant_id, outlet_id, user_account_id, role_id) VALUES
    (:t_habesha::uuid, :o_h2::uuid, :u_h1_mgr::uuid,  :r_manager::uuid),
    (:t_habesha::uuid, :o_h2::uuid, :u_h1_cook::uuid, :r_cook::uuid),
    (:t_habesha::uuid, :o_h2::uuid, :u_h1_srv::uuid,  :r_server::uuid);

-- FR-AUTH-001 asks for VERIFIED phone or email. A channel with a null verified_at is
-- exactly what identity.authenticate_credential() refuses, so these carry the moment.
INSERT INTO identity.identity_channel
    (tenant_id, user_account_id, channel, channel_value, verified_at) VALUES
    (:t_habesha::uuid, :u_h1_mgr::uuid,  'email', 'manager@habesha.example', now()),
    (:t_habesha::uuid, :u_h1_cook::uuid, 'email', 'kitchen@habesha.example', now()),
    (:t_habesha::uuid, :u_h1_srv::uuid,  'email', 'server@habesha.example',  now()),
    (:t_habesha::uuid, :u_h1_cook::uuid, 'phone', '+251911000002', now());

-- scrypt, N=16384 r=8 p=1, 32-byte derived key, per-credential salt. The 32 bytes are not
-- a coincidence: credential_digest_is_a_digest has required exactly that since 0004, and
-- scrypt emits a key of the length asked for, so the repair fits the existing guard
-- rather than relaxing it.
INSERT INTO identity.credential
    (tenant_id, outlet_id, user_account_id, kind, secret_digest, digest_algorithm,
     salt, kdf_params, confers_strength) VALUES
    (:t_habesha::uuid, NULL, :u_h1_mgr::uuid, 'password',
     '\x564fec7678c8df144f2b2f9ae72232fef7a43ebfa0f4037e30ab850c4f82a223'::bytea, 'scrypt',
     '\x3572ace006cb617cf8b49d6d013fed1c'::bytea,
     '{"cost":16384,"blockSize":8,"parallelization":1}'::jsonb, 'standard'),
    (:t_habesha::uuid, NULL, :u_h1_cook::uuid, 'password',
     '\xd66eb84e3f446aef7e8b1d58f2197c871e124c58a00309e7cb6be9ea71edbbd0'::bytea, 'scrypt',
     '\xb40b884d29316a097f7d94ee3bd6494c'::bytea,
     '{"cost":16384,"blockSize":8,"parallelization":1}'::jsonb, 'standard'),
    (:t_habesha::uuid, NULL, :u_h1_srv::uuid, 'password',
     '\x1d9a6c46eb2fcd8560cfbd90aa3870d74567cf7e3e55ef9eb19b7a07503e3829'::bytea, 'scrypt',
     '\x6ae6f1f920ef1556c1b4c65d2a5bd071'::bytea,
     '{"cost":16384,"blockSize":8,"parallelization":1}'::jsonb, 'standard');

-- A quick PIN is outlet-scoped and low strength, and the schema has said so since 0004.
-- It is stretched like any other chosen secret: four digits is the WEAKEST thing in this
-- table and therefore the one that most needs it.
INSERT INTO identity.credential
    (tenant_id, outlet_id, user_account_id, kind, secret_digest, digest_algorithm,
     salt, kdf_params, confers_strength) VALUES
    (:t_habesha::uuid, :o_h2::uuid, :u_h1_cook::uuid, 'quick_pin',
     '\xa681ccbc8b80d3be6500955b0e1d9ce43cbf4cd18cc9b99c0ed103b2def53d08'::bytea, 'scrypt',
     '\xb8e9ff69829df1000efe07a034ce6d58'::bytea,
     '{"cost":16384,"blockSize":8,"parallelization":1}'::jsonb, 'low');

-- ---- What each role may do -------------------------------------------
-- Roles without grants are roles that can do nothing, and a demonstration floor whose
-- manager cannot approve anything is not a demonstration. Granted from
-- identity.governed_action rather than typed: the catalog already says which actions
-- exist and what strength each demands, so a grant naming an action nobody governs would
-- be a grant nobody enforces.
--
-- The manager gets the sensitive actions BECAUSE the quick PIN below must be refused for
-- a reason that is about STRENGTH. A role with no grant is refused on entitlement, which
-- looks identical from outside and proves nothing about step-up.
INSERT INTO identity.role_action (tenant_id, role_id, action_code)
SELECT :t_habesha::uuid, :r_manager::uuid, g.action_code
  FROM identity.governed_action g WHERE g.tenant_id = :t_habesha::uuid;

INSERT INTO identity.role_action (tenant_id, role_id, action_code)
SELECT :t_habesha::uuid, r.id, g.action_code
  FROM identity.governed_action g, (VALUES (:r_cook::uuid), (:r_server::uuid)) AS r(id)
 WHERE g.tenant_id = :t_habesha::uuid AND g.minimum_strength = 'low';

-- A quick PIN for the MANAGER as well, on the same registered terminal. This is the one
-- that makes FR-AUTH-005 falsifiable: the holder is entitled to configuration.modify and
-- is still refused, because a PIN confers 'low' and that action demands 'strong'.
INSERT INTO identity.credential
    (tenant_id, outlet_id, user_account_id, kind, secret_digest, digest_algorithm,
     salt, kdf_params, confers_strength) VALUES
    (:t_habesha::uuid, :o_h2::uuid, :u_h1_mgr::uuid, 'quick_pin',
     '\x5d86891adcb7125f4429b7f3a9eb88e851f047ecaccbd9fe4e9d44d83d17da05'::bytea, 'scrypt',
     '\x64616ddd5e49dbc15bff5ee1fbad108e'::bytea,
     '{"cost":16384,"blockSize":8,"parallelization":1}'::jsonb, 'low');

-- ---- The floor ---------------------------------------------------------
INSERT INTO org.org_node (id, tenant_id, parent_id, outlet_id, kind, reference_code, display_name) VALUES
    (:st_hot::uuid, :t_habesha::uuid, :o_h2::uuid, :o_h2::uuid, 'preparation_station', 'ST-H2-HOT', 'Hot Kitchen'),
    (:st_bar::uuid, :t_habesha::uuid, :o_h2::uuid, :o_h2::uuid, 'preparation_station', 'ST-H2-BAR', 'Beverage Station'),
    (:dev_h1::uuid, :t_habesha::uuid, :o_h2::uuid, :o_h2::uuid, 'device', 'DEV-H2-POS1', 'Sarbet Counter Terminal'),
    (:tbl_h1_01::uuid, :t_habesha::uuid, :sa_h2::uuid, :o_h2::uuid, 'dining_table', 'T-H2-11', 'Table 1'),
    (:tbl_h1_02::uuid, :t_habesha::uuid, :sa_h2::uuid, :o_h2::uuid, 'dining_table', 'T-H2-12', 'Table 2'),
    (:tbl_h1_03::uuid, :t_habesha::uuid, :sa_h2::uuid, :o_h2::uuid, 'dining_table', 'T-H2-13', 'Table 3');

-- FR-AUTH-005: a quick PIN is re-entry on a REGISTERED terminal. Without this row the
-- PIN above cannot be used anywhere, which is the rule working rather than a gap.
INSERT INTO identity.terminal_trust (device_id, tenant_id, outlet_id)
VALUES (:dev_h1::uuid, :t_habesha::uuid, :o_h2::uuid);

INSERT INTO service.table_profile
    (tenant_id, table_node_id, outlet_id, service_area_id, seat_count) VALUES
    (:t_habesha::uuid, :tbl_h1_01::uuid, :o_h2::uuid, :sa_h2::uuid, 4),
    (:t_habesha::uuid, :tbl_h1_02::uuid, :o_h2::uuid, :sa_h2::uuid, 2),
    (:t_habesha::uuid, :tbl_h1_03::uuid, :o_h2::uuid, :sa_h2::uuid, 6);

-- The QR token is issued by the function that owns issuance, not written directly: it is
-- what makes a guest link real, and a hand-written token row would not carry whatever
-- service.issue_table_qr() decides about format, uniqueness or supersession.
SELECT service.issue_table_qr(:t_habesha::uuid, :tbl_h1_01::uuid, :u_habesha::uuid);
SELECT service.issue_table_qr(:t_habesha::uuid, :tbl_h1_02::uuid, :u_habesha::uuid);
SELECT service.issue_table_qr(:t_habesha::uuid, :tbl_h1_03::uuid, :u_habesha::uuid);

-- ---- The menu ----------------------------------------------------------
INSERT INTO menu.menu (id, tenant_id, outlet_id, menu_code, canonical_name)
VALUES (:m_h1::uuid, :t_habesha::uuid, :o_h2::uuid, 'ALLDAY', 'All Day Menu');

INSERT INTO menu.category (id, tenant_id, outlet_id, menu_id, category_code, canonical_name, display_order) VALUES
    (:c_mains::uuid,  :t_habesha::uuid, :o_h2::uuid, :m_h1::uuid, 'MAINS',  'Main Dishes', 1),
    (:c_drinks::uuid, :t_habesha::uuid, :o_h2::uuid, :m_h1::uuid, 'DRINKS', 'Drinks',      2);

INSERT INTO menu.sellable_item
    (id, tenant_id, outlet_id, menu_id, category_id, item_code, canonical_name,
     canonical_short_description, canonical_long_description,
     customer_visible_ingredients, preparation_minutes, display_order) VALUES
    (:i_doro::uuid, :t_habesha::uuid, :o_h2::uuid, :m_h1::uuid, :c_mains::uuid, 'SKU-DORO-01',
     'Doro Wat', 'Slow cooked chicken in berbere sauce',
     'Chicken legs simmered for hours in spiced berbere with onion and clarified butter, served with injera and a hard boiled egg.',
     'Chicken, berbere, onion, niter kibbeh, egg, injera', 35, 1),
    (:i_tibs::uuid, :t_habesha::uuid, :o_h2::uuid, :m_h1::uuid, :c_mains::uuid, 'SKU-TIBS-02',
     'Beef Tibs', 'Beef cubes sauteed with rosemary',
     'Cubed beef seared quickly with rosemary, onion and green chilli, served sizzling.',
     'Beef, rosemary, onion, green chilli, niter kibbeh', 20, 2),
    (:i_shiro::uuid, :t_habesha::uuid, :o_h2::uuid, :m_h1::uuid, :c_mains::uuid, 'SKU-SHIRO-03',
     'Shiro', 'Ground chickpea stew',
     'Ground chickpea simmered with garlic and berbere until smooth, served with injera.',
     'Chickpea flour, garlic, berbere, onion, injera', 15, 3),
    (:i_coffee::uuid, :t_habesha::uuid, :o_h2::uuid, :m_h1::uuid, :c_drinks::uuid, 'SKU-BUNA-04',
     'Ethiopian Coffee', 'Roasted and brewed to order',
     'Beans roasted at the table, ground and brewed in a jebena.',
     'Coffee', 10, 1);

INSERT INTO menu.item_variant
    (id, tenant_id, outlet_id, item_id, axis, variant_code, canonical_name, is_default, display_order) VALUES
    (:v_doro_f::uuid,   :t_habesha::uuid, :o_h2::uuid, :i_doro::uuid,   'portion', 'FULL',   'Full portion', true,  1),
    (:v_doro_h::uuid,   :t_habesha::uuid, :o_h2::uuid, :i_doro::uuid,   'portion', 'HALF',   'Half portion', false, 2),
    (:v_tibs_f::uuid,   :t_habesha::uuid, :o_h2::uuid, :i_tibs::uuid,   'portion', 'FULL',   'Full portion', true,  1),
    (:v_shiro_f::uuid,  :t_habesha::uuid, :o_h2::uuid, :i_shiro::uuid,  'portion', 'FULL',   'Full portion', true,  1),
    (:v_coffee_s::uuid, :t_habesha::uuid, :o_h2::uuid, :i_coffee::uuid, 'portion', 'SINGLE', 'Single',       true,  1);

-- Prices in minor units of ETB, which is what money.amount_minor is for. No float appears
-- anywhere in this file for the same reason it appears nowhere in the schema.
INSERT INTO menu.price
    (tenant_id, outlet_id, variant_id, channel, currency_code, amount_minor, tax_context) VALUES
    (:t_habesha::uuid, :o_h2::uuid, :v_doro_f::uuid,   NULL, 'ETB', 32000, 'standard'),
    (:t_habesha::uuid, :o_h2::uuid, :v_doro_h::uuid,   NULL, 'ETB', 18000, 'standard'),
    (:t_habesha::uuid, :o_h2::uuid, :v_tibs_f::uuid,   NULL, 'ETB', 36000, 'standard'),
    (:t_habesha::uuid, :o_h2::uuid, :v_shiro_f::uuid,  NULL, 'ETB', 22000, 'standard'),
    (:t_habesha::uuid, :o_h2::uuid, :v_coffee_s::uuid, NULL, 'ETB',  6000, 'standard');

INSERT INTO menu.modifier_group
    (id, tenant_id, outlet_id, group_code, canonical_name, min_selections, max_selections) VALUES
    (:mg_spice::uuid, :t_habesha::uuid, :o_h2::uuid, 'DEMO-SPICE', 'Spice level', 0, 1);

INSERT INTO menu.modifier
    (id, tenant_id, outlet_id, modifier_group_id, modifier_code, canonical_name, display_order) VALUES
    (:mo_mild::uuid, :t_habesha::uuid, :o_h2::uuid, :mg_spice::uuid, 'MILD', 'Mild', 1),
    (:mo_hot::uuid,  :t_habesha::uuid, :o_h2::uuid, :mg_spice::uuid, 'HOT',  'Extra hot', 2);

INSERT INTO menu.item_modifier_group (tenant_id, outlet_id, item_id, modifier_group_id, display_order) VALUES
    (:t_habesha::uuid, :o_h2::uuid, :i_doro::uuid,  :mg_spice::uuid, 1),
    (:t_habesha::uuid, :o_h2::uuid, :i_tibs::uuid,  :mg_spice::uuid, 1),
    (:t_habesha::uuid, :o_h2::uuid, :i_shiro::uuid, :mg_spice::uuid, 1);

-- Availability, so the surface has something to render as orderable rather than as a
-- name with no state.
INSERT INTO menu.availability (tenant_id, outlet_id, item_id, state) VALUES
    (:t_habesha::uuid, :o_h2::uuid, :i_doro::uuid,   'available'),
    (:t_habesha::uuid, :o_h2::uuid, :i_tibs::uuid,   'available'),
    (:t_habesha::uuid, :o_h2::uuid, :i_shiro::uuid,  'available'),
    (:t_habesha::uuid, :o_h2::uuid, :i_coffee::uuid, 'available');

-- ---- Amharic and Arabic, for everything a customer reads ---------------
-- Amharic and Arabic for everything publication requires. Written out rather than
-- generated: these are the words a guest reads, and a placeholder in a demonstration
-- menu is how a build comes to claim three languages while shipping one.
INSERT INTO menu.translation
    (tenant_id, outlet_id, entity, entity_id, field_name, locale, translated_text,
     state, provenance, reviewed_by_user_id, approved_at) VALUES
    (:t_habesha::uuid, :o_h2::uuid, 'menu', '33336001-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'am', 'የቀኑ ሙሉ ምናሌ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'category', '33336101-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'am', 'ዋና ምግቦች', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'category', '33336102-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'am', 'መጠጦች', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336201-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'am', 'ዶሮ ወጥ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336202-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'am', 'የበሬ ጥብስ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336203-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'am', 'ሽሮ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336204-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'am', 'ቡና', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'menu', '33336001-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'ar', 'قائمة اليوم الكامل', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'category', '33336101-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'ar', 'الأطباق الرئيسية', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'category', '33336102-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'ar', 'المشروبات', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336201-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'ar', 'دورو وات', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336202-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'ar', 'تبس لحم البقر', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336203-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'ar', 'شيرو', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336204-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'ar', 'قهوة إثيوبية', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336201-0000-4000-8000-000000000001'::uuid, 'canonical_short_description', 'am', 'በበርበሬ የበሰለ የዶሮ ወጥ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336202-0000-4000-8000-000000000001'::uuid, 'canonical_short_description', 'am', 'በሮዝመሪ የተጠበሰ የበሬ ሥጋ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336203-0000-4000-8000-000000000001'::uuid, 'canonical_short_description', 'am', 'የሽምብራ ወጥ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336204-0000-4000-8000-000000000001'::uuid, 'canonical_short_description', 'am', 'በጀበና የተፈላ ቡና', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336201-0000-4000-8000-000000000001'::uuid, 'canonical_short_description', 'ar', 'دجاج مطهو ببطء في صلصة بربري', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336202-0000-4000-8000-000000000001'::uuid, 'canonical_short_description', 'ar', 'مكعبات لحم بقري مع إكليل الجبل', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336203-0000-4000-8000-000000000001'::uuid, 'canonical_short_description', 'ar', 'يخنة الحمص المطحون', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336204-0000-4000-8000-000000000001'::uuid, 'canonical_short_description', 'ar', 'قهوة محمصة ومخمرة عند الطلب', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336201-0000-4000-8000-000000000001'::uuid, 'customer_visible_ingredients', 'am', 'ዶሮ፣ በርበሬ፣ ሽንኩርት፣ ንጥር ቅቤ፣ እንቁላል፣ እንጀራ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336202-0000-4000-8000-000000000001'::uuid, 'customer_visible_ingredients', 'am', 'የበሬ ሥጋ፣ ሮዝመሪ፣ ሽንኩርት፣ አረንጓዴ ቃሪያ፣ ንጥር ቅቤ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336203-0000-4000-8000-000000000001'::uuid, 'customer_visible_ingredients', 'am', 'የሽምብራ ዱቄት፣ ነጭ ሽንኩርት፣ በርበሬ፣ ሽንኩርት፣ እንጀራ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336204-0000-4000-8000-000000000001'::uuid, 'customer_visible_ingredients', 'am', 'ቡና', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336201-0000-4000-8000-000000000001'::uuid, 'customer_visible_ingredients', 'ar', 'دجاج، بربري، بصل، سمن مصفى، بيض، إنجيرا', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336202-0000-4000-8000-000000000001'::uuid, 'customer_visible_ingredients', 'ar', 'لحم بقري، إكليل الجبل، بصل، فلفل أخضر، سمن مصفى', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336203-0000-4000-8000-000000000001'::uuid, 'customer_visible_ingredients', 'ar', 'دقيق الحمص، ثوم، بربري، بصل، إنجيرا', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'item', '33336204-0000-4000-8000-000000000001'::uuid, 'customer_visible_ingredients', 'ar', 'قهوة', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'variant', '33336301-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'am', 'ሙሉ ድርሻ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'variant', '33336302-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'am', 'ግማሽ ድርሻ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'variant', '33336303-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'am', 'ሙሉ ድርሻ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'variant', '33336304-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'am', 'ሙሉ ድርሻ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'variant', '33336305-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'am', 'አንድ', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'variant', '33336301-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'ar', 'حصة كاملة', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'variant', '33336302-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'ar', 'نصف حصة', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'variant', '33336303-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'ar', 'حصة كاملة', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'variant', '33336304-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'ar', 'حصة كاملة', 'approved', 'human', :u_habesha::uuid, now()),
    (:t_habesha::uuid, :o_h2::uuid, 'variant', '33336305-0000-4000-8000-000000000001'::uuid, 'canonical_name', 'ar', 'مفرد', 'approved', 'human', :u_habesha::uuid, now());

-- English is DERIVED from the canonical columns rather than retyped. The canonical value
-- IS the English text, and a second copy of it in this table could drift from the first;
-- menu.missing_required_translations() requires a row per locale including en, so the row
-- has to exist, but nothing says a human must key it in twice.
INSERT INTO menu.translation
    (tenant_id, outlet_id, entity, entity_id, field_name, locale, translated_text,
     state, provenance, reviewed_by_user_id, approved_at)
SELECT :t_habesha::uuid, :o_h2::uuid, 'menu'::menu.menu_entity, m.id, 'canonical_name', 'en'::menu.customer_locale,
       m.canonical_name, 'approved'::menu.translation_state, 'human'::menu.translation_provenance, :u_habesha::uuid, now()
  FROM menu.menu m WHERE m.id = :m_h1::uuid
UNION ALL SELECT :t_habesha::uuid, :o_h2::uuid, 'category'::menu.menu_entity, c.id, 'canonical_name', 'en'::menu.customer_locale,
       c.canonical_name, 'approved'::menu.translation_state, 'human'::menu.translation_provenance, :u_habesha::uuid, now()
  FROM menu.category c WHERE c.menu_id = :m_h1::uuid
UNION ALL SELECT :t_habesha::uuid, :o_h2::uuid, 'item'::menu.menu_entity, i.id, 'canonical_name', 'en'::menu.customer_locale,
       i.canonical_name, 'approved'::menu.translation_state, 'human'::menu.translation_provenance, :u_habesha::uuid, now()
  FROM menu.sellable_item i WHERE i.menu_id = :m_h1::uuid
UNION ALL SELECT :t_habesha::uuid, :o_h2::uuid, 'item'::menu.menu_entity, i.id, 'canonical_short_description', 'en'::menu.customer_locale,
       i.canonical_short_description, 'approved'::menu.translation_state, 'human'::menu.translation_provenance, :u_habesha::uuid, now()
  FROM menu.sellable_item i WHERE i.menu_id = :m_h1::uuid
UNION ALL SELECT :t_habesha::uuid, :o_h2::uuid, 'item'::menu.menu_entity, i.id, 'customer_visible_ingredients', 'en'::menu.customer_locale,
       i.customer_visible_ingredients, 'approved'::menu.translation_state, 'human'::menu.translation_provenance, :u_habesha::uuid, now()
  FROM menu.sellable_item i WHERE i.menu_id = :m_h1::uuid
UNION ALL SELECT :t_habesha::uuid, :o_h2::uuid, 'variant'::menu.menu_entity, v.id, 'canonical_name', 'en'::menu.customer_locale,
       v.canonical_name, 'approved'::menu.translation_state, 'human'::menu.translation_provenance, :u_habesha::uuid, now()
  FROM menu.item_variant v JOIN menu.sellable_item i ON i.id = v.item_id
 WHERE i.menu_id = :m_h1::uuid;


-- ---- Allergen safety is NOT seeded here, and that is a finding ---------
-- The demonstration menu carries no allergen declaration, and it cannot: safety.allergen
-- is unique on (tenant_id, jurisdiction_code, kitchen_code) and safety.approved_wording on
-- (tenant_id, purpose, locale), so the safety VOCABULARY is one per tenant however many
-- outlets a tenant has. A first version of this seed wrote its own SESAME allergen and its
-- own acknowledgement wording, and M2-B's fixtures — which create the same vocabulary for
-- the same tenant — then failed on both uniques.
--
-- The vocabulary is therefore not product data this seed may own. It is configuration, and
-- nothing seeds it: it exists only inside tests/m2b's fixtures. A deployed instance built
-- from migrations and seeds alone has a menu, a floor, staff and stations, and no allergen
-- catalogue at all — which is the same shape as the four gaps this gate was called to
-- close, found the same way, and recorded in planning/OPA_FINDINGS.md rather than papered
-- over by giving this seed a second copy that the schema forbids.

-- ---- The menu reaches the floor ----------------------------------------
-- A published menu nobody assigned is a menu no guest can see: ordering.preview_cart()
-- blocks with "no menu assignment reaches outlet … on channel dine_in". The menu, the
-- prices and the translations were all present and this one row was not — the same shape
-- as everything else this gate is repairing, found the same way, by trying to order.
-- No daypart, so it applies all day; effective_from in the past so it is in force now.
INSERT INTO menu.assignment
    (tenant_id, outlet_id, menu_id, channel, effective_from)
VALUES (:t_habesha::uuid, :o_h2::uuid, :m_h1::uuid, 'dine_in', DATE '2026-01-01');

-- ---- The policies an order is handled under ----------------------------
-- ordering.require_policy() refuses an order when no policy is in force — "an order
-- cannot be handled under a policy nobody set" — so a floor without these is a floor
-- that takes no orders. 0001 seeds the tenant-wide discount and tip policies; these are
-- the outlet-scoped ones an order actually needs.
INSERT INTO config.policy
    (tenant_id, outlet_id, category, version, payload, effective_from,
     actor_id, approved_by_id, approved_at) VALUES
    (:t_habesha::uuid, :o_h2::uuid, 'ordering', 1,
     '{"acceptance": {"guest_qr": "staff_confirmed",
                      "waiter_entered": "automatic",
                      "counter": "staff_confirmed"},
       "max_line_quantity": 20,
       "duplicate_window_seconds": 300,
       "amendment_allowed_states": ["submitted"]}'::jsonb,
     now() - interval '1 day', :u_habesha::uuid, :u_habesha::uuid, now() - interval '1 day'),
    (:t_habesha::uuid, :o_h2::uuid, 'cancellation', 1,
     '{"allowed_states": {"guest_qr": ["submitted"],
                          "waiter_entered": ["submitted", "accepted"]}}'::jsonb,
     now() - interval '1 day', :u_habesha::uuid, :u_habesha::uuid, now() - interval '1 day'),
    (:t_habesha::uuid, :o_h2::uuid, 'service', 1,
     '{"acknowledge_within_seconds": 120, "recall_window_seconds": 600}'::jsonb,
     now() - interval '1 day', :u_habesha::uuid, :u_habesha::uuid, now() - interval '1 day');

-- ---- Publish -----------------------------------------------------------
-- Through the function that owns publication, so the snapshot carries whatever
-- publish_menu decides about completeness. A directly written snapshot row would be a
-- claim that the menu was publishable rather than a demonstration that it is.
SELECT menu.publish_menu(:m_h1::uuid, :u_habesha::uuid);

-- =========================================================================
-- Tenant two: Nile — a different brand, a different language mix, one outlet
-- =========================================================================
SELECT set_config('app.tenant_id', :t_nile, false);
SELECT set_config('app.outlet_id', :o_n1, false);

INSERT INTO identity.role (id, tenant_id, role_code, display_name)
VALUES (:r_n_mgr::uuid, :t_nile::uuid, 'OUTLET_MANAGER', 'Outlet Manager');

INSERT INTO identity.user_account (id, tenant_id, staff_number, display_name)
VALUES (:u_n1_mgr::uuid, :t_nile::uuid, 'MGR-0001', 'Nile Manager');

INSERT INTO identity.membership (tenant_id, outlet_id, user_account_id, role_id)
VALUES (:t_nile::uuid, :o_n1::uuid, :u_n1_mgr::uuid, :r_n_mgr::uuid);

INSERT INTO identity.identity_channel
    (tenant_id, user_account_id, channel, channel_value, verified_at)
VALUES (:t_nile::uuid, :u_n1_mgr::uuid, 'email', 'manager@nile.example', now());

INSERT INTO identity.credential
    (tenant_id, outlet_id, user_account_id, kind, secret_digest, digest_algorithm,
     salt, kdf_params, confers_strength)
VALUES (:t_nile::uuid, NULL, :u_n1_mgr::uuid, 'password',
        '\xac2f9b14896bc793c0c401ec930044dff715e9f11df241e28b504a129e96e89f'::bytea, 'scrypt',
        '\xbf02fd9fe5a8ce732b6772c044fd1d15'::bytea,
        '{"cost":16384,"blockSize":8,"parallelization":1}'::jsonb, 'standard');

-- 0001 gave Nile an outlet and no service area, and a dining table hangs from one.
INSERT INTO org.org_node (id, tenant_id, parent_id, outlet_id, kind, reference_code, display_name) VALUES
    (:sa_n1::uuid,     :t_nile::uuid, :o_n1::uuid,  :o_n1::uuid, 'service_area', 'SA-N1-MAIN', 'Dining Room'),
    (:st_n_hot::uuid,  :t_nile::uuid, :o_n1::uuid,  :o_n1::uuid, 'preparation_station', 'ST-N1-HOT', 'Kitchen'),
    (:tbl_n1_01::uuid, :t_nile::uuid, :sa_n1::uuid, :o_n1::uuid, 'dining_table', 'T-N1-01', 'Table 1');

INSERT INTO service.table_profile
    (tenant_id, table_node_id, outlet_id, service_area_id, seat_count)
VALUES (:t_nile::uuid, :tbl_n1_01::uuid, :o_n1::uuid, :sa_n1::uuid, 4);

SELECT service.issue_table_qr(:t_nile::uuid, :tbl_n1_01::uuid, :u_nile::uuid);

INSERT INTO menu.menu (id, tenant_id, outlet_id, menu_code, canonical_name)
VALUES (:m_n1::uuid, :t_nile::uuid, :o_n1::uuid, 'MAIN', 'Main Menu');

INSERT INTO menu.category (id, tenant_id, outlet_id, menu_id, category_code, canonical_name, display_order)
VALUES (:c_n_mains::uuid, :t_nile::uuid, :o_n1::uuid, :m_n1::uuid, 'MAINS', 'Mains', 1);

INSERT INTO menu.sellable_item
    (id, tenant_id, outlet_id, menu_id, category_id, item_code, canonical_name,
     canonical_short_description, canonical_long_description,
     customer_visible_ingredients, preparation_minutes, display_order)
VALUES (:i_n_fish::uuid, :t_nile::uuid, :o_n1::uuid, :m_n1::uuid, :c_n_mains::uuid, 'SKU-FISH-01',
        'Grilled Nile Perch', 'Whole perch over charcoal',
        'Whole Nile perch scored, salted and grilled over charcoal, served with lemon.',
        'Nile perch, lemon, salt, oil', 30, 1);

INSERT INTO menu.item_variant
    (id, tenant_id, outlet_id, item_id, axis, variant_code, canonical_name, is_default, display_order)
VALUES (:v_n_fish::uuid, :t_nile::uuid, :o_n1::uuid, :i_n_fish::uuid, 'portion', 'WHOLE', 'Whole', true, 1);

INSERT INTO menu.price (tenant_id, outlet_id, variant_id, channel, currency_code, amount_minor, tax_context)
VALUES (:t_nile::uuid, :o_n1::uuid, :v_n_fish::uuid, NULL, 'ETB', 48000, 'standard');

INSERT INTO menu.availability (tenant_id, outlet_id, item_id, state)
VALUES (:t_nile::uuid, :o_n1::uuid, :i_n_fish::uuid, 'available');

-- An approved translation names its reviewer and the moment it was approved, because
-- translation_approval_is_reviewed requires both: approval is an act by somebody, not a
-- flag. The demonstration administrator is that somebody here.
-- Nile, the same discipline on a smaller menu.
INSERT INTO menu.translation
    (tenant_id, outlet_id, entity, entity_id, field_name, locale, translated_text,
     state, provenance, reviewed_by_user_id, approved_at) VALUES
    (:t_nile::uuid, :o_n1::uuid, 'menu',     :m_n1::uuid,      'canonical_name', 'am', 'ዋና ምናሌ', 'approved', 'human', :u_nile::uuid, now()),
    (:t_nile::uuid, :o_n1::uuid, 'menu',     :m_n1::uuid,      'canonical_name', 'ar', 'القائمة الرئيسية', 'approved', 'human', :u_nile::uuid, now()),
    (:t_nile::uuid, :o_n1::uuid, 'category', :c_n_mains::uuid, 'canonical_name', 'am', 'ዋና ምግቦች', 'approved', 'human', :u_nile::uuid, now()),
    (:t_nile::uuid, :o_n1::uuid, 'category', :c_n_mains::uuid, 'canonical_name', 'ar', 'الأطباق الرئيسية', 'approved', 'human', :u_nile::uuid, now()),
    (:t_nile::uuid, :o_n1::uuid, 'item',     :i_n_fish::uuid,  'canonical_name', 'am', 'የተጠበሰ የናይል አሳ', 'approved', 'human', :u_nile::uuid, now()),
    (:t_nile::uuid, :o_n1::uuid, 'item',     :i_n_fish::uuid,  'canonical_name', 'ar', 'سمك نهر النيل المشوي', 'approved', 'human', :u_nile::uuid, now()),
    (:t_nile::uuid, :o_n1::uuid, 'item',     :i_n_fish::uuid,  'canonical_short_description', 'am', 'ሙሉ አሳ በከሰል የተጠበሰ', 'approved', 'human', :u_nile::uuid, now()),
    (:t_nile::uuid, :o_n1::uuid, 'item',     :i_n_fish::uuid,  'canonical_short_description', 'ar', 'سمكة كاملة على الفحم', 'approved', 'human', :u_nile::uuid, now()),
    (:t_nile::uuid, :o_n1::uuid, 'item',     :i_n_fish::uuid,  'customer_visible_ingredients', 'am', 'የናይል አሳ፣ ሎሚ፣ ጨው፣ ዘይት', 'approved', 'human', :u_nile::uuid, now()),
    (:t_nile::uuid, :o_n1::uuid, 'item',     :i_n_fish::uuid,  'customer_visible_ingredients', 'ar', 'سمك نهر النيل، ليمون، ملح، زيت', 'approved', 'human', :u_nile::uuid, now()),
    (:t_nile::uuid, :o_n1::uuid, 'variant',  :v_n_fish::uuid,  'canonical_name', 'am', 'ሙሉ', 'approved', 'human', :u_nile::uuid, now()),
    (:t_nile::uuid, :o_n1::uuid, 'variant',  :v_n_fish::uuid,  'canonical_name', 'ar', 'كاملة', 'approved', 'human', :u_nile::uuid, now());

INSERT INTO menu.translation
    (tenant_id, outlet_id, entity, entity_id, field_name, locale, translated_text,
     state, provenance, reviewed_by_user_id, approved_at)
SELECT :t_nile::uuid, :o_n1::uuid, 'menu'::menu.menu_entity, m.id, 'canonical_name', 'en'::menu.customer_locale,
       m.canonical_name, 'approved'::menu.translation_state, 'human'::menu.translation_provenance, :u_nile::uuid, now()
  FROM menu.menu m WHERE m.id = :m_n1::uuid
UNION ALL SELECT :t_nile::uuid, :o_n1::uuid, 'category'::menu.menu_entity, c.id, 'canonical_name', 'en'::menu.customer_locale,
       c.canonical_name, 'approved'::menu.translation_state, 'human'::menu.translation_provenance, :u_nile::uuid, now()
  FROM menu.category c WHERE c.menu_id = :m_n1::uuid
UNION ALL SELECT :t_nile::uuid, :o_n1::uuid, 'item'::menu.menu_entity, i.id, 'canonical_name', 'en'::menu.customer_locale,
       i.canonical_name, 'approved'::menu.translation_state, 'human'::menu.translation_provenance, :u_nile::uuid, now()
  FROM menu.sellable_item i WHERE i.menu_id = :m_n1::uuid
UNION ALL SELECT :t_nile::uuid, :o_n1::uuid, 'item'::menu.menu_entity, i.id, 'canonical_short_description', 'en'::menu.customer_locale,
       i.canonical_short_description, 'approved'::menu.translation_state, 'human'::menu.translation_provenance, :u_nile::uuid, now()
  FROM menu.sellable_item i WHERE i.menu_id = :m_n1::uuid
UNION ALL SELECT :t_nile::uuid, :o_n1::uuid, 'item'::menu.menu_entity, i.id, 'customer_visible_ingredients', 'en'::menu.customer_locale,
       i.customer_visible_ingredients, 'approved'::menu.translation_state, 'human'::menu.translation_provenance, :u_nile::uuid, now()
  FROM menu.sellable_item i WHERE i.menu_id = :m_n1::uuid
UNION ALL SELECT :t_nile::uuid, :o_n1::uuid, 'variant'::menu.menu_entity, v.id, 'canonical_name', 'en'::menu.customer_locale,
       v.canonical_name, 'approved'::menu.translation_state, 'human'::menu.translation_provenance, :u_nile::uuid, now()
  FROM menu.item_variant v JOIN menu.sellable_item i ON i.id = v.item_id
 WHERE i.menu_id = :m_n1::uuid;


INSERT INTO config.policy
    (tenant_id, outlet_id, category, version, payload, effective_from,
     actor_id, approved_by_id, approved_at) VALUES
    (:t_nile::uuid, :o_n1::uuid, 'ordering', 1,
     '{"acceptance": {"guest_qr": "staff_confirmed",
                      "waiter_entered": "automatic",
                      "counter": "staff_confirmed"},
       "max_line_quantity": 20,
       "duplicate_window_seconds": 300,
       "amendment_allowed_states": ["submitted"]}'::jsonb,
     now() - interval '1 day', :u_nile::uuid, :u_nile::uuid, now() - interval '1 day'),
    (:t_nile::uuid, :o_n1::uuid, 'cancellation', 1,
     '{"allowed_states": {"guest_qr": ["submitted"]}}'::jsonb,
     now() - interval '1 day', :u_nile::uuid, :u_nile::uuid, now() - interval '1 day');

INSERT INTO menu.assignment
    (tenant_id, outlet_id, menu_id, channel, effective_from)
VALUES (:t_nile::uuid, :o_n1::uuid, :m_n1::uuid, 'dine_in', DATE '2026-01-01');

SELECT menu.publish_menu(:m_n1::uuid, :u_nile::uuid);
