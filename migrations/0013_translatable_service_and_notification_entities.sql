-- =============================================================================
-- 0013 — Two more things that can be translated
-- =============================================================================
-- This migration adds two labels and nothing else, for the same reason 0011 did: psql
-- runs one file in one transaction, and a label added by ALTER TYPE cannot be USED in
-- the transaction that added it. 0014 uses both, so they have to arrive first.
--
-- FR-NOT-003 says the notification templates are human-approved in English, Amharic and
-- Arabic, and the brief is explicit that this must reuse M2-A's translation approval
-- workflow rather than stand up a second store. That workflow is menu.translation:
-- draft -> in_review -> approved, a reviewer and an approval timestamp required by CHECK,
-- the machine-assistance boundary of FR-I18N-010, and menu.enforce_translation_review()
-- refusing an approval nobody reviewed. All of it applies unchanged to a service request
-- label or a notification template body; none of it would be true of a second table.
--
-- The type is called menu.menu_entity and these two are not menu entities. That is a
-- naming debt this migration accepts deliberately: the alternative is a parallel
-- translation store, and M2-B's whole finding was that a second copy of safety-critical
-- text is how the two copies come to disagree. What the type actually means — and has
-- meant since M2-A — is "a kind of thing that has translatable fields".
-- =============================================================================

ALTER TYPE menu.menu_entity ADD VALUE IF NOT EXISTS 'service_request_type';
ALTER TYPE menu.menu_entity ADD VALUE IF NOT EXISTS 'notification_template';

COMMENT ON TYPE menu.menu_entity IS
    'A kind of thing that has translatable fields, not only a menu one. M3-C added '
    'service_request_type (FR-SRV-001''s translated request catalog) and '
    'notification_template (FR-NOT-003''s approved customer templates) so both reuse '
    'M2-A''s approval workflow rather than getting a second store each.';
