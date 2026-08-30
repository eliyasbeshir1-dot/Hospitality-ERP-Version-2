-- ===========================================================================
-- 0007 — Enum extensions for M2-B
-- ===========================================================================
--
-- This migration does nothing but widen three enumerated types, and it exists as its
-- own file for a reason that is not stylistic.
--
-- tools/migrate.py applies each migration through psql --single-transaction, so one
-- file is one transaction. PostgreSQL permits ALTER TYPE ... ADD VALUE inside a
-- transaction block, but it does not permit the new value to be USED in that same
-- transaction: the label is not visible to the snapshot that added it. Every statement
-- in 0008 that inserts an 'allergen' translatable field, or registers an 'anonymize'
-- retention policy, would fail with "unsafe use of new value of enum type".
--
-- The alternative was to avoid the enums — a parallel safety translation store with its
-- own entity type, and a second retention engine that understood anonymization. Both
-- would have duplicated machinery M1 already proved, which is exactly what the M2-B
-- brief says not to do. A separate migration is the smaller price.
--
-- Forward-only, like every migration here. IF NOT EXISTS makes re-application a no-op
-- rather than an error, though the checksum ledger already prevents that.

-- ---------------------------------------------------------------------------
-- Safety content is translated through the machinery M2-A already built
-- ---------------------------------------------------------------------------
--
-- menu.translation carries approved customer text, keyed by (entity, field_name), and
-- menu.translatable_field records which of those fields are required for publication and
-- which are safety-critical. Allergen warnings and dietary claim labels are both: a guest
-- reads them before deciding whether they can eat something.
--
-- Registering them as menu entities means the approval workflow, the human-reviewer
-- requirement for safety-critical text, and the publication block all apply to them
-- without a second implementation that could drift from the first.

ALTER TYPE menu.menu_entity ADD VALUE IF NOT EXISTS 'allergen';
ALTER TYPE menu.menu_entity ADD VALUE IF NOT EXISTS 'dietary_claim';

-- ---------------------------------------------------------------------------
-- Retention learns to anonymize
-- ---------------------------------------------------------------------------
--
-- A guest session is privacy-minimized but not empty: it carries a chosen nickname and a
-- locale, and it is linked to the allergy concerns raised at a table. FR-CST-002 requires
-- expiry and an anonymization policy, and the M2-B brief is explicit that the M1-C
-- retention engine is the one to wire to.
--
-- config.retention_action offered only 'archive' and 'purge'. Deleting a guest session
-- outright would take the allergy concern with it, and an allergy concern is operational
-- evidence that outlives the guest identity attached to it. Anonymizing severs the
-- identity and keeps the record.

ALTER TYPE config.retention_action ADD VALUE IF NOT EXISTS 'anonymize';
