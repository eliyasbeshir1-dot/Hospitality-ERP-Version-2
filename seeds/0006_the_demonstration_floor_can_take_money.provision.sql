-- 0006 — the demonstration floor can take money (provisioning)
--
-- WHAT WAS WRONG. After 0005 gave Sarbet a tax configuration, a bill could be issued
-- there and still not paid: billing.tip_options() returns nothing without a tip_setting
-- and its suggestions, and payments refuses every method — including CASH — without a
-- payments.payment_adapter row for the outlet. The demonstration floor could seat a
-- guest, take an order, cook it and hand over a bill, and then had no way to be paid.
--
-- OP-A proved the kitchen and stopped exactly where money starts, so nothing had asked
-- this floor for a payment until OP-B's till did. Same shape as the tax configuration in
-- 0005 and as the printer-test forgery before it: the first caller finds the defect.
--
-- WHY THIS IS A PROVISIONING SEED. hospitality_app holds SELECT and nothing more on all
-- three tables below, because each is decided when an outlet is INSTALLED and is then read,
-- not written, by the running service:
--
--   billing.tip_setting             whether this outlet offers a tip at all
--   billing.tip_suggestion          the percentages it offers, if it does
--   payments.payment_adapter        which payment providers this outlet accepts
--
-- None is produced by trade. The contrast that makes the boundary checkable is
-- billing.bill: also SELECT-only to the app role, and NOT provisionable, because a
-- function writes it in the course of business. Membership in the provisioning set is
-- decided by who decides the row, never by which grant happens to be in the way.
--
-- A SERVICE CHARGE IS NOT SEEDED, AND THE TABLE IS NOT IN THE SET. It was approved for
-- the pass, and then turned out not to be needed: billing.service_charge_setting requires
-- a configuration_version_id, and a floor with no service charge is correctly represented
-- by no row — billing.issue_bill() reads absence as "none", which Sarbet's first bill
-- proved before this seed existed. Putting a table in the privileged set that nothing
-- writes widens the boundary for nothing, so the set grew by three rather than four.
--
-- The set grew from three tables to six to admit these, and tools/seed.py now carries the
-- six written down twice so a seventh cannot arrive as a one-word diff. The three guards
-- OP-A attached to the pass are unchanged: this file may write only the named tables, it
-- may not issue a GRANT, and the runner re-reads the catalog afterwards and refuses if
-- hospitality_app holds anything beyond SELECT on any of the six.
--
-- THE VALUES ARE THE ONES ALREADY IN USE. 15% tax is in 0005; 5/10/15% tip suggestions and
-- the adapter set mirror what tests/m4a and tests/m4b configure for Kazanchis. This seed
-- decides no rates; it writes the demonstration floor's counterpart of a configuration
-- that already exists next door.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set o_h2       '''33330002-0000-4000-8000-000000000002'''
\set u_habesha  '''3333aaaa-0000-4000-8000-000000000001'''

-- THE CONTEXT IS SET EVEN THOUGH THIS RUNS AS THE MIGRATOR. The migration role does not
-- escape row level security, and these tables carry RLS FORCE, so a privileged identity is
-- still subject to the policy — which is the point: the provisioning pass widens WHO may
-- write, not WHAT the rules are. Without this the first INSERT below is refused, as it was.
--
-- The role that DOES escape it is deliberately not named here, even in prose. A file whose
-- name ends .provision.sql is a deployment path, and tools/verify_m1.py refuses that role's
-- name anywhere in one — comment or code, because a scanner that trusted itself to tell
-- them apart is a scanner that can be talked round. It flagged this comment on its first
-- run, which is the rule working rather than a false positive to be tuned away.
SELECT set_config('app.tenant_id', :t_habesha, false);
SELECT set_config('app.outlet_id', :o_h2, false);

-- A tip is OFFERED here, and no suggestion is marked preferred. FR-BIL-015 is a rule about
-- what a surface may render, and it starts with the data: there is no column here for
-- "selected", so a till cannot read a preference out of the configuration and call it the
-- outlet's choice.
INSERT INTO billing.tip_setting (tenant_id, outlet_id, offered)
VALUES (:t_habesha::uuid, :o_h2::uuid, true)
ON CONFLICT (tenant_id, outlet_id) DO NOTHING;

INSERT INTO billing.tip_suggestion (tenant_id, outlet_id, display_order, percentage)
VALUES
    (:t_habesha::uuid, :o_h2::uuid, 1,  '5.0000'),
    (:t_habesha::uuid, :o_h2::uuid, 2, '10.0000'),
    (:t_habesha::uuid, :o_h2::uuid, 3, '15.0000')
ON CONFLICT (tenant_id, outlet_id, display_order) DO NOTHING;

-- The methods this outlet accepts. Cash is here because cash is not the absence of an
-- adapter: FR-PAY-002 asks which methods an outlet takes, and a floor that has never said
-- it takes cash has not said it.
INSERT INTO payments.payment_adapter (tenant_id, outlet_id, provider, mode, active)
VALUES
    (:t_habesha::uuid, :o_h2::uuid, 'cash',              'live', true),
    (:t_habesha::uuid, :o_h2::uuid, 'external_terminal', 'live', true),
    (:t_habesha::uuid, :o_h2::uuid, 'telebirr_proof',    'live', true),
    (:t_habesha::uuid, :o_h2::uuid, 'cbe_birr_proof',    'live', true)
ON CONFLICT (tenant_id, outlet_id, provider) DO NOTHING;
