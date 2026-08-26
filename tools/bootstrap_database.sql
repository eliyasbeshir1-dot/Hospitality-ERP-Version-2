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

-- The runtime role must never inherit the migrator's rights.
REVOKE ALL ON DATABASE hospitality_os FROM PUBLIC;
GRANT CONNECT ON DATABASE hospitality_os TO hospitality_migrator, hospitality_app;

-- Only the migrator may create schemas.
GRANT CREATE ON DATABASE hospitality_os TO hospitality_migrator;
