-- 0005 — the demonstration floor can produce a bill
--
-- WHAT WAS WRONG. Seed 0003 gave Sarbet a menu, tables with QR tokens, stations, routing,
-- staff who can log in, and ordering and service policies. A guest can scan, order, and
-- watch the kitchen work. Then the till stops: billing.issue_bill() refuses with
-- BILL_TAX_UNCONFIGURED, because it reads an OUTLET-scoped 'tax' configuration and Sarbet
-- has none. The demonstration floor could take an order and never take money for it.
--
-- It went unnoticed at OP-A for a reason worth recording: that gate proved the KITCHEN,
-- and a ticket needs no tax. The first thing to ask Sarbet for a bill was OP-B's cashier
-- screen, and it was refused on its first attempt. The first caller finds the defect,
-- again.
--
-- WHY THE TENANT-LEVEL ROW IN 0001 DOES NOT COVER IT. Seed 0001 writes a tenant-scoped
-- 'tax' row shaped {"vat_percentage": ..., "rounding_mode": ...}. billing.issue_bill()
-- reads neither: it selects on outlet_id and reads
-- payload -> 'contexts' -> 'standard' ->> 'percentage'. Two rows, both called tax, in two
-- shapes, for two readers — and the one the bill needs was only ever written by
-- tests/m3a/fixtures.py, for Kazanchis. No seed has ever written one. So the product data
-- has never been able to produce a bill anywhere; only the fixtures could.
--
-- WHY A NEW SEED RATHER THAN AN EDIT TO 0003. Seeds are checksum-locked and 0003 has
-- landed. The same reasoning the ownership map records for migrations applies: a repair to
-- what a landed seed shipped is a further seed, not an edit, because an edit refuses to
-- apply on every database that already ran the original.
--
-- 15% VAT, half-up, matching what the fixtures use for Kazanchis and what 0001 states at
-- the tenant level. This seed does not decide a tax rate; it writes the one already
-- recorded in two other places into the one place the bill actually reads.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set o_h2       '''33330002-0000-4000-8000-000000000002'''
\set u_habesha  '''3333aaaa-0000-4000-8000-000000000001'''
\set cfg_tax    '''33337001-0000-4000-8000-000000000001'''

SELECT set_config('app.tenant_id', :t_habesha, false),
       set_config('app.outlet_id', :o_h2, false);

INSERT INTO config.configuration_version
    (id, tenant_id, outlet_id, scope_kind, scope_node_id, category, version,
     payload, effective_from, actor_id, approved_by_id, approved_at)
VALUES
    (:cfg_tax::uuid, :t_habesha::uuid, :o_h2::uuid, 'outlet', :o_h2::uuid, 'tax', 1,
     '{"contexts": {"standard": {"percentage": "15.0000", "rounding": "half_up"}}}'::jsonb,
     now() - interval '1 day', :u_habesha::uuid, :u_habesha::uuid,
     now() - interval '1 day')
ON CONFLICT (id) DO NOTHING;
