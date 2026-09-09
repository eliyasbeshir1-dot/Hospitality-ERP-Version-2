-- bootstrap_database.sql
--
-- Cluster provisioning for M1-A. Run ONCE by a cluster administrator holding CREATEROLE,
-- before the first migration. No privileged identity is configured for runtime here: this
-- file must not create, grant or reference a BYPASSRLS or superuser role for any
-- application, worker or deployment path. This is deliberately NOT a migration: roles are cluster-global, they
-- differ per environment, and they must exist before migration 0001 can grant to
-- them. Keeping them out of the checksum-locked history stops environment drift
-- from invalidating that history (FR-DAT-016).
--
-- Requirements: FR-DAT-017, FR-OPS-020.
--
-- Two identities are created. Neither is a superuser and no BYPASSRLS attribute is
-- ever granted to either of them:
--
--   hospitality_migrator  applies migrations; owns the schemas and tables.
--                         Never used at runtime.
--   hospitality_app       the runtime identity. DML only, subject to RLS, with no
--                         DDL right, no ownership and no BYPASSRLS.
--
-- No password is set here and none may ever be added: a credential literal in a
-- checked-in file is exactly what FR-SEC-007 forbids. Authentication for these roles
-- is configured by the environment — pg_hba.conf plus the deployment's secret store —
-- and never by this migration-adjacent script.

\set ON_ERROR_STOP on

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hospitality_migrator') THEN
        CREATE ROLE hospitality_migrator
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOBYPASSRLS
            NOREPLICATION;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hospitality_app') THEN
        CREATE ROLE hospitality_app
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOBYPASSRLS
            NOREPLICATION;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- WHICH DATABASE THESE GRANTS ARE FOR, TAKEN RATHER THAN ASSUMED
-- ---------------------------------------------------------------------------
--
-- These three statements named `hospitality_os` literally, while tools/open_the_floor.sh
-- advertises DB as overridable and connects to whatever it is set to. With DB=other the
-- script created `other`, ran this file AGAINST `other`, and then granted CONNECT on
-- `hospitality_os` — so `other` got no grants at all, hospitality_app could not connect,
-- and the failure surfaced much later as a connection error rather than as a bad grant.
-- If `hospitality_os` did not exist the run aborted loudly; if it did, which is the normal
-- case, the grants landed silently on the wrong database. The silent path is both the
-- likely one and the worse one.
--
-- The name is now a psql variable, and it REFUSES rather than proceeds when it is absent.
-- `:'db_name'` would interpolate the literal string ":db_name" if unset, which is exactly
-- the quiet wrong answer this replaces, so the guard is explicit and comes first.
-- REFUSED AS AN ERROR, NOT AS A MESSAGE. The first version of this guard used `\quit 1`,
-- which psql accepts and then reports "extra argument 1 ignored" — it stops the script and
-- exits ZERO. A caller running with ON_ERROR_STOP would have sailed straight past a
-- refusal it never saw, which is the same silence this whole guard exists to end. A RAISE
-- is an error to psql, to the shell, and to CI alike.
\if :{?db_name}
\else
DO $$
BEGIN
    RAISE EXCEPTION
        'BOOTSTRAP_DATABASE_UNNAMED: this file grants CONNECT and CREATE on a NAMED '
        'database and will not guess which. Pass it: '
        'psql "$DSN" -v db_name="$DB" -f tools/bootstrap_database.sql'
        USING ERRCODE = 'HS422';
END;
$$;
\endif

-- The runtime role must never inherit the migrator's rights.
REVOKE ALL ON DATABASE :"db_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db_name" TO hospitality_migrator, hospitality_app;

-- Only the migrator may create schemas.
GRANT CREATE ON DATABASE :"db_name" TO hospitality_migrator;
