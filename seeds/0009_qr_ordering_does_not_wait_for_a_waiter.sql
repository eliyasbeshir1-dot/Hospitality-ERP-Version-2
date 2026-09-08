-- 0009_qr_ordering_does_not_wait_for_a_waiter.sql — the acceptance policy, version 2
--
-- WHY THIS EXISTS. seeds/0003 set the ordering policy with guest_qr acceptance =
-- staff_confirmed. That is a legal value and FR-ORD-007A exists to make it configurable,
-- so nothing was broken — but it is the wrong default for a floor whose whole proposition
-- is that a guest orders without waiting for anybody. A guest scanned, chose, placed the
-- order, and it sat in 'submitted' while the kitchen showed nothing. QR ordering exists to
-- remove the waiter as the bottleneck; requiring a tap to start puts them back in front of
-- it.
--
-- guest_qr becomes 'automatic'. The other two are untouched and deliberately so:
--
--   waiter_entered  automatic        the waiter IS the staff confirmation; asking them to
--                                    confirm their own order is the same tap twice.
--   counter         staff_confirmed  a counter order is taken face to face and may be paid
--                                    before it is cooked; FR-ORD-007B makes some outlets
--                                    accept only after a verified payment, and that path
--                                    runs through staff confirmation.
--
-- STAFF_CONFIRMED IS NOT REMOVED AND MUST KEEP WORKING. It is a policy value, not a
-- mistake, and OP-D builds the waiter floor's pending-orders list precisely so that an
-- outlet which chooses it has somewhere to accept from. Changing the demonstration floor's
-- default does not retire the branch, and tests/opd drives both.
--
-- A NEW VERSION, NOT AN EDIT, AND THAT IS THE POINT OF THE FILE.
--
-- config.policy carries version, effective_from and effective_to, and
-- ordering.effective_policy() reads whichever row is in force. So a policy change is a
-- second row with the first one closed — the history of what an outlet's rule WAS stays
-- readable, and an order placed yesterday can still be explained by the policy that was in
-- force when it was placed. An UPDATE of the 0003 row would have made every past order
-- look as though it had always been automatic, which is the same class of defect as an
-- editable audit trail. config.policy carries an audit trigger, so the closing UPDATE is
-- itself recorded.
--
-- BOTH TENANTS THAT HAVE AN ORDERING POLICY GET THE CHANGE, each under its own context and
-- named by its own administrator. Nile has no floor on this build and gets it anyway, for
-- the reason seeds/0008 gives: the tenants that exist should not differ in rules nobody
-- chose to differ, or the next person to give Nile a floor meets this defect with no clue
-- that it was already met once.
--
-- APPLIED AS THE APPLICATION ROLE. config.policy is content the running service reads and
-- writes through governed paths, and seeds/0003 wrote these rows the same way. This is not
-- a provisioning seed and must not become one.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set t_nile     '''44444444-4444-4444-4444-444444444444'''
\set o_h2       '''33330002-0000-4000-8000-000000000002'''
\set o_n1       '''44440001-0000-4000-8000-000000000001'''
\set u_habesha  '''3333aaaa-0000-4000-8000-000000000001'''
\set u_nile     '''4444aaaa-0000-4000-8000-000000000001'''

-- ---------------------------------------------------------------------------
-- HABESHA — the demonstration floor at Sarbet
-- ---------------------------------------------------------------------------
SELECT set_config('app.tenant_id', :t_habesha, false);
SELECT set_config('app.outlet_id', :o_h2, false);

-- The version in force is closed at the moment the new one begins, so there is never an
-- instant with no ordering policy: ordering.require_policy() refuses an order when it
-- finds none, and a floor that stopped taking orders for the duration of a seed would be
-- this file causing an outage.
UPDATE config.policy
   SET effective_to = now()
 WHERE tenant_id = :t_habesha::uuid
   AND category = 'ordering'
   AND effective_to IS NULL;

INSERT INTO config.policy
    (tenant_id, outlet_id, category, version, payload, effective_from,
     actor_id, approved_by_id, approved_at) VALUES
    (:t_habesha::uuid, :o_h2::uuid, 'ordering', 2,
     '{"acceptance": {"guest_qr": "automatic",
                      "waiter_entered": "automatic",
                      "counter": "staff_confirmed"},
       "max_line_quantity": 20,
       "duplicate_window_seconds": 300,
       "amendment_allowed_states": ["submitted"]}'::jsonb,
     now(), :u_habesha::uuid, :u_habesha::uuid, now());

-- ---------------------------------------------------------------------------
-- NILE — no floor yet, and the same rule anyway
-- ---------------------------------------------------------------------------
SELECT set_config('app.tenant_id', :t_nile, false);
SELECT set_config('app.outlet_id', :o_n1, false);

UPDATE config.policy
   SET effective_to = now()
 WHERE tenant_id = :t_nile::uuid
   AND category = 'ordering'
   AND effective_to IS NULL;

INSERT INTO config.policy
    (tenant_id, outlet_id, category, version, payload, effective_from,
     actor_id, approved_by_id, approved_at) VALUES
    (:t_nile::uuid, :o_n1::uuid, 'ordering', 2,
     '{"acceptance": {"guest_qr": "automatic",
                      "waiter_entered": "automatic",
                      "counter": "staff_confirmed"},
       "max_line_quantity": 20,
       "duplicate_window_seconds": 300,
       "amendment_allowed_states": ["submitted"]}'::jsonb,
     now(), :u_nile::uuid, :u_nile::uuid, now());

SELECT set_config('app.tenant_id', '', false);
SELECT set_config('app.outlet_id', '', false);
