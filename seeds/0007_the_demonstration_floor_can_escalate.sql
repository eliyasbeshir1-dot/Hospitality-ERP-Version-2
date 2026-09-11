-- 0007 — the demonstration floor's service policy, complete
--
-- WHAT WAS WRONG. Seed 0003 gave Sarbet a 'service' policy carrying two keys:
-- recall_window_seconds and acknowledge_within_seconds. Five database functions read that
-- policy and each refuses with SERVICE_POLICY_INCOMPLETE when the key it needs is absent:
--
--   fulfillment.recall_ticket          recall_window_seconds          (0003 has it)
--   fulfillment.capacity_pressure      capacity_response              (missing)
--   fulfillment.escalate_uncollected   collection_escalation_seconds  (missing)
--   notify.accountable_staff           critical_alert_role_code       (missing)
--   service.escalate_overdue_requests  service_escalation_role_code   (missing)
--
-- The one that bites first is notify.accountable_staff, because placing an order WITH AN
-- ALLERGY DECLARATION notifies the accountable role — so on the demonstration floor a
-- guest declaring an allergy could not place an order at all. OP-A did not meet it: its
-- order helper's declaration resolved to nothing on a floor with no safety vocabulary of
-- its own, so the notification never fired and the missing key never showed. OP-B's till
-- reached it, which is the sixth time in two gates that the first caller found the defect.
--
-- A SUPERSEDING VERSION, NOT AN EDIT. config.policy is versioned and the readers take the
-- highest version, so this adds version 2 and leaves version 1 in place. The history of
-- what the floor's policy WAS stays readable, which is the point of versioning a policy
-- rather than updating it — and seeds are checksum-locked, so editing 0003 would refuse to
-- apply on every database that already ran it.
--
-- THE ROLE IS THE ONE THIS FLOOR HAS. Kazanchis names M3C_SUPERVISOR, a role invented by
-- M3-C's fixtures. Sarbet has OUTLET_MANAGER, seeded by 0003 as the role a manager holds
-- here, and that is who should be told when a critical allergy alert or an overdue request
-- needs somebody accountable. A seed pointing at a fixture's role would be product data
-- depending on test data.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set o_h2       '''33330002-0000-4000-8000-000000000002'''
\set u_habesha  '''3333aaaa-0000-4000-8000-000000000001'''

SELECT set_config('app.tenant_id', :t_habesha, false),
       set_config('app.outlet_id', :o_h2, false);

INSERT INTO config.policy
    (tenant_id, outlet_id, category, version, payload, effective_from,
     actor_id, approved_by_id, approved_at) VALUES
    (:t_habesha::uuid, :o_h2::uuid, 'service', 2,
     '{"recall_window_seconds": 600,
       "acknowledge_within_seconds": 120,
       "capacity_response": "throttle",
       "collection_escalation_seconds": 300,
       "critical_alert_role_code": "OUTLET_MANAGER",
       "service_escalation_role_code": "OUTLET_MANAGER"}'::jsonb,
     now() - interval '1 day', :u_habesha::uuid, :u_habesha::uuid,
     now() - interval '1 day')
ON CONFLICT DO NOTHING;
