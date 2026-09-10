-- 0018 — Kazanchis can say who is accountable, now that it has something to say
--
-- 0061's edge notices refused on their first call at Kazanchis with ORDER_POLICY_ABSENT.
-- The demonstration floor — the outlet every golden journey runs at, and the one with the
-- node GJ-09 partitions — has never had a 'service' policy, so notify.accountable_staff()
-- had nothing to read and every CRITICAL notice there was unraisable.
--
-- THAT WAS A DECISION, NOT AN OVERSIGHT, AND SEED 0007 WROTE IT DOWN:
--
--     THE ROLE IS THE ONE THIS FLOOR HAS. Kazanchis names M3C_SUPERVISOR, a role invented
--     by M3-C's fixtures... A seed pointing at a fixture's role would be product data
--     depending on test data.
--
-- That reasoning was right and it is still right. What has changed is that Kazanchis now
-- has something critical to say: a node whose lease degrades, an outlet entering local
-- continuity, a sync conflict, a printer that stopped. Before M5b the only critical events
-- at this outlet were allergy alerts and overdue requests, which M3-C's fixtures raised
-- against their own role. Now the PRODUCT raises them, and product data may not depend on
-- whether a test suite has run.
--
-- SO IT NAMES OUTLET_MANAGER, WHICH IS A REAL ROLE. seeds/0003 created it as the role a
-- manager holds, Sarbet's policy already names it, and it is active for this tenant.
--
-- WHAT THIS DELIBERATELY DOES NOT DO IS INVENT A MEMBER. No user account holds
-- OUTLET_MANAGER at Kazanchis, so notify.accountable_staff() will return no rows and no
-- staff notice will be addressed to anybody. That is the honest state of a floor whose
-- manager has not been assigned, and it is an OPERATOR's job rather than a seed's: the
-- notification row is still created and still readable, and FR-NOT-005's guarantee is that
-- who is accountable is configured rather than guessed. A seed that granted somebody the
-- role to make a check pass would be guessing on the operator's behalf, which is the exact
-- thing accountable_staff() refuses to do.
--
-- IT IS A CONTENT SEED AND NOT A PROVISIONING ONE, which tools/seed.py insisted on and
-- was right to. config.policy is not in PROVISIONABLE_TABLES and should not be: it is
-- written through the application role so it passes the same row level security the
-- service passes. seeds/0007 is a content seed for the same reason, and a policy seeded
-- under the migration identity would be a policy nothing had proved the app could read.
--
-- A SUPERSEDING VERSION IS NOT NEEDED HERE — this outlet has no service policy at all, so
-- this is version 1. Sarbet's stays at 2 and is untouched.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set o_h1       '''33330001-0000-4000-8000-000000000001'''
\set u_habesha  '''3333aaaa-0000-4000-8000-000000000001'''

SELECT set_config('app.tenant_id', :t_habesha, false),
       set_config('app.outlet_id', :o_h1, false);

INSERT INTO config.policy
    (tenant_id, outlet_id, category, version, payload, effective_from,
     actor_id, approved_by_id, approved_at) VALUES
    (:t_habesha::uuid, :o_h1::uuid, 'service', 1,
     -- The same six keys Sarbet carries, and for the same reason: five database functions
     -- read this policy and each refuses by name when the key it needs is absent. Seeding
     -- four of six would move the failure rather than remove it, which is what seed 0003
     -- did and seed 0007 had to correct.
     '{"recall_window_seconds": 600,
       "acknowledge_within_seconds": 120,
       "capacity_response": "throttle",
       "collection_escalation_seconds": 300,
       "critical_alert_role_code": "OUTLET_MANAGER",
       "service_escalation_role_code": "OUTLET_MANAGER"}'::jsonb,
     now() - interval '1 day', :u_habesha::uuid, :u_habesha::uuid,
     now() - interval '1 day')
ON CONFLICT DO NOTHING;

SELECT set_config('app.outlet_id', '', false);
SELECT set_config('app.tenant_id', '', false);
