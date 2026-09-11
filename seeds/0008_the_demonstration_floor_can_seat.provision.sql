-- 0008_the_demonstration_floor_can_seat.provision.sql — the grade a new action needed
--
-- APPLIED UNDER THE MIGRATION IDENTITY, AND THE SUFFIX IS WHY.
--
-- pos.confirmation_requirement is SELECT-only to the application role, and deliberately:
-- 0015's comment says "nothing the surface can do should be able to lower the friction on
-- declaring an allergy". A grade is configuration. So this file cannot go in through the
-- application role, and it does not try to.
--
-- WHAT IT IS FOR. 0036 added `table.seat` to the two places grades are stated, and neither
-- reaches a tenant that already exists: the trigger fires on tenant INSERT, and the
-- installer has to be CALLED. The demonstration tenants were created by seed 0001, long
-- before the action existed, so without this file a waiter on the demonstration floor
-- presses Seat and gets a confirmation panel demanding a written reason — the ungraded
-- default, working exactly as designed, on an action nobody had graded yet.
--
-- WHY IT CALLS THE INSTALLER RATHER THAN WRITING THE ROW. pos.install_registries_for() is
-- idempotent and already states which grades a tenant needs. Writing the row here would be
-- a THIRD statement of that list, beside the trigger's and the installer's, and the two
-- that already exist are recorded in planning/OPC_FINDINGS.md as a duplication to derive
-- away rather than to grow.
--
-- CONTEXT IS SET PER TENANT, AND THAT IS NOT CEREMONY. The installer's first act is to
-- check the tenant is visible in the caller's scope, and org.tenant carries FORCE row
-- level security — so without the set_config below it refuses with TENANT_NOT_IN_SCOPE
-- rather than installing into a tenant nobody named. Each tenant is entered explicitly,
-- and the second does not inherit the first's context.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set t_nile     '''44444444-4444-4444-4444-444444444444'''

-- HABESHA, the demonstration floor OP-A seeded and OP-B built screens for.
SELECT set_config('app.tenant_id', :t_habesha, false);
SELECT pos.install_registries_for(:t_habesha::uuid) AS habesha_rows_installed;

-- NILE, the second tenant. It has no floor and no menu, and it gets the grade anyway:
-- the tenants that exist should not differ in which actions are graded, or the next
-- person to give Nile a floor meets this same defect with no clue that it was already
-- met once.
SELECT set_config('app.tenant_id', :t_nile, false);
SELECT pos.install_registries_for(:t_nile::uuid) AS nile_rows_installed;

SELECT set_config('app.tenant_id', '', false);
