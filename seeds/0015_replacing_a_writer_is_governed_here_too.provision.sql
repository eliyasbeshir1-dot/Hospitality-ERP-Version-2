-- 0015_replacing_a_writer_is_governed_here_too.provision.sql — the second of the three
--
-- 0052 adds `node.authority.claim` to the trigger that installs governed actions for a NEW
-- tenant. The demonstration tenants were created at seeds/0001, so the trigger never fires
-- for them and they would carry every governed action except the one M5b introduces —
-- which means edge.claim_authority() would refuse every replacement at this floor with
-- AUTHORITY_STEP_UP_ABSENT, for a grant nobody could ever have obtained.
--
-- This is the third time: OP-C met it with `table.seat`, OP-D with `order.accept`, and
-- seeds/0010's header wrote the pattern down. A new governed action needs the trigger, an
-- installer call for the tenants that already exist, and the caller. This file is the
-- second one, and it exists because a migration cannot do it: migrations run with no
-- tenant context and org.tenant carries FORCE row level security, so a backfill matches
-- nothing.
--
-- APPLIED UNDER THE MIGRATION IDENTITY, and the call is vetted in tools/seed.py's
-- PROVISIONABLE_FUNCTIONS. identity.governed_action is SELECT-only to the application role
-- by design — the registry that decides which acts need stronger authentication is not
-- something a screen may edit.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set t_nile     '''44444444-4444-4444-4444-444444444444'''

SELECT set_config('app.tenant_id', :t_habesha, false);
SELECT identity.install_governed_actions_for(:t_habesha::uuid) AS habesha_installed;

-- Nile has no floor and no node, and gets the action anyway, for the reason seeds/0008
-- gives: the tenants that exist should not differ in which acts are governed, or the next
-- person to give Nile a node meets this same refusal with no clue it was already met.
SELECT set_config('app.tenant_id', :t_nile, false);
SELECT identity.install_governed_actions_for(:t_nile::uuid) AS nile_installed;

SELECT set_config('app.tenant_id', '', false);
