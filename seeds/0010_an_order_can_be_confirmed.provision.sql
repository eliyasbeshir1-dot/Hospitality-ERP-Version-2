-- 0010_an_order_can_be_confirmed.provision.sql — the grade for `order.accept`
--
-- WHAT THIS IS, AND WHY IT IS A SECOND FILE THAT LOOKS LIKE THE FIRST.
--
-- 0037 added `order.accept` to the two places pos states confirmation grades: the trigger
-- that installs them for a NEW tenant, and pos.install_registries_for() for one that
-- already exists. Neither reaches a tenant that was created before the migration ran —
-- the trigger fires on INSERT and the installer has to be CALLED — so the demonstration
-- tenants, created by seeds/0001, still had no grade for it.
--
-- seeds/0008 exists to make that call, and it cannot make it again: seeds are
-- checksum-locked, so an applied seed is applied forever and editing it is refused on
-- every database that already ran it. The installer is idempotent and would have done the
-- right thing; the file that calls it is the part that cannot be re-run.
--
-- THIS IS NOW THE SECOND TIME, AND IT IS A PATTERN RATHER THAN AN ACCIDENT. Every future
-- gate that puts a NEW action on a staff screen needs three things and will need all
-- three again: the action in both lists in a migration, a seed that calls the installer
-- for the tenants that already exist, and the button. Miss the second and the action is
-- graded for nobody; miss the first or the second and the surface's fail-closed default
-- makes the button demand a written reason and then do nothing, which is exactly how
-- `table.seat` behaved at OP-C and how `order.accept` would have behaved here.
--
-- Recorded in planning/OPD_FINDINGS.md as a cost with a name, because the alternative —
-- a migration that backfills — is not available: a migration runs with no tenant context,
-- org.tenant carries FORCE row level security, and a backfill SELECT over it matches
-- nothing. That is the reason pos.install_registries_for() exists at all.
--
-- APPLIED UNDER THE MIGRATION IDENTITY, and the call is vetted. pos.confirmation_requirement
-- is SELECT-only to the application role by design — "nothing the surface can do should be
-- able to lower the friction on declaring an allergy" — and tools/seed.py allowlists
-- pos.install_registries_for by name in PROVISIONABLE_FUNCTIONS, with a note saying which
-- tables it writes.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set t_nile     '''44444444-4444-4444-4444-444444444444'''

SELECT set_config('app.tenant_id', :t_habesha, false);
SELECT pos.install_registries_for(:t_habesha::uuid) AS habesha_rows_installed;

SELECT set_config('app.tenant_id', :t_nile, false);
SELECT pos.install_registries_for(:t_nile::uuid) AS nile_rows_installed;

SELECT set_config('app.tenant_id', '', false);
