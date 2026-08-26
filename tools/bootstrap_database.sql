-- bootstrap_database.sql
--
-- Cluster provisioning for M1-A. Run ONCE by a cluster superuser, before the first
-- migration. This is deliberately NOT a migration: roles are cluster-global, they
-- differ per environment, and they must exist before migration 0001 can grant to
-- them. Keeping them out of the checksum-locked history stops environment drift
-- from invalidating that history (FR-DAT-016).
--
-- Requirements: FR-DAT-017, FR-OPS-020.
--
-- Two identities are created, and neither is a superuser:
--
--   hospitality_migrator  applies migrations; owns the schemas and tables.
--                         Never used at runtime.
--   hospitality_app       the runtime identity. DML only, subject to RLS, with no
--                         DDL right, no ownership and no BYPASSRLS.
--
-- Passwords are placeholders for local verification and are expected to be supplied
-- from the environment's secret store in any real deployment.

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
            NOREPLICATION
            PASSWORD 'migrator_local_only';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hospitality_app') THEN
        CREATE ROLE hospitality_app
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOBYPASSRLS
            NOREPLICATION
            PASSWORD 'app_local_only';
    END IF;
END;
$$;

-- The runtime role must never inherit the migrator's rights.
REVOKE ALL ON DATABASE hospitality_os FROM PUBLIC;
GRANT CONNECT ON DATABASE hospitality_os TO hospitality_migrator, hospitality_app;

-- Only the migrator may create schemas.
GRANT CREATE ON DATABASE hospitality_os TO hospitality_migrator;
