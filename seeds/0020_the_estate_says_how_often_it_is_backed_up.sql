-- 0020 — the estate says how often it is backed up
--
-- FR-OPS-006 asks for a DOCUMENTED schedule. ops.backup_policy is where that is written
-- down, and an empty table is the `undocumented` posture rather than a healthy one — which
-- is deliberate: nothing can be late against a schedule that does not exist, and reporting
-- that as healthy is how an unbacked-up estate looks fine.
--
-- The M5b lesson applied one gate later: FR-EDG-023's lease policy shipped as a schema
-- with four DEFAULT clauses and no rows, and GJ-09 found it empty on a floor with two
-- nodes. A policy table nobody seeds is a policy nobody has.
--
-- TWENTY-FOUR HOURS, ALERT AT THIRTY-SIX, KEEP THIRTY DAYS. Daily because a restaurant's
-- unit of work is a service and losing one is the most a backup should ever cost. The
-- alert window is deliberately NOT the interval: a backup an hour late is not an incident
-- and a backup half a day late is, and a window equal to the interval would alert on every
-- successful schedule. Retention outlives the interval by a wide margin because the
-- failure a backup is for — somebody notices last week — is not discovered in a day.

\set ON_ERROR_STOP on

\set t_habesha '''33333333-3333-3333-3333-333333333333'''
\set u_habesha '''3333aaaa-0000-4000-8000-000000000001'''

SELECT set_config('app.tenant_id', :t_habesha, false);

INSERT INTO ops.backup_policy
    (tenant_id, scope, interval_hours, alert_after_hours, retain_days,
     offsite_required, documented_by_user_id)
VALUES (:t_habesha::uuid, 'cloud', 24, 36, 30, true, :u_habesha::uuid)
ON CONFLICT DO NOTHING;

SELECT set_config('app.tenant_id', '', false);
