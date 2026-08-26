-- 0004_readiness_provenance_grants.sql
--
-- Gate:         M1, slice D
-- Requirements: FR-OPS-002, FR-OPS-005
--
-- Readiness must verify that migrations have been applied (FR-OPS-002). The application
-- role could not do that: migration 0001 revoked all access to the migration history from
-- PUBLIC and granted none back, so readiness reported — truthfully — that it could not
-- read it, and therefore that the service was not ready.
--
-- The right fix is a narrow read grant, not a privileged connection for readiness. This
-- migration exists rather than an edit to 0001 because 0001 is applied and checksum-locked:
-- forward-only means the amendment is a new file with its reasoning attached, which also
-- leaves the decision visible to a reviewer instead of buried in a diff.
--
-- SELECT only. The application role still cannot insert, update or delete a migration
-- record, so it cannot forge provenance for a schema it is running against. The comment in
-- 0001 stating that the role holds "no privilege on the migration history" is superseded by
-- this file and is left in place, unedited, as the lock requires.

GRANT USAGE ON SCHEMA migration TO hospitality_app;
GRANT SELECT ON migration.schema_migrations TO hospitality_app;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON migration.schema_migrations FROM hospitality_app;

COMMENT ON TABLE migration.schema_migrations IS
    'Ordered, checksum-locked migration history (FR-DAT-001, FR-DAT-016). Forward-only: '
    'rows are inserted, never updated or deleted. The application role holds SELECT only, '
    'so readiness can verify provenance without being able to fabricate it (0004).';
