-- =============================================================================
-- 0016 — One more thing that can be translated
-- =============================================================================
-- The same shape as 0011 and 0013, and for the same reason: psql runs one file in one
-- transaction, and a label added by ALTER TYPE cannot be USED in the transaction that
-- added it. 0017 uses this one, so it has to arrive first.
--
-- WHY IT IS NEEDED AT ALL. FR-NOT-012 says the customer status timeline renders in the
-- session language, and FR-I18N-001B says order status text renders in the session
-- language across the ordering journeys. Neither was true. M3-A wrote the customer
-- summary of every timeline entry as an English literal inside
-- ordering.write_timeline_entry(), and M3-B did the same for the two station milestones
-- a guest is shown. The order carries the locale the guest chose — FR-I18N-005's
-- snapshot, taken at M2-C and asserted since — and nothing read it.
--
-- No slice check caught this. Every one of them asked whether the timeline said the
-- right THING; none asked what language it said it in, because each slice was reading
-- its own timeline in English. GJ-02 and GJ-03A asked, because a journey walks the
-- guest's screen in the guest's language, and both failed on the same line.
--
-- The translation store is menu.translation, unchanged: draft -> in_review -> approved,
-- a reviewer and an approval timestamp required by CHECK, and
-- menu.enforce_translation_review() refusing an approval nobody reviewed. That last
-- clause is why the wording is NOT installed by a migration. An approved translation
-- asserts that a person read it; a migration inserting one would be forging that
-- assertion, and FR-I18N-006 forbids exactly the machine-filled safety text this would
-- be a first step toward. So a migration builds the place the wording goes and the
-- resolver that reads it, and the wording itself arrives the way FR-NOT-003's templates
-- do — through the approval workflow, with a human named.
-- =============================================================================

ALTER TYPE menu.menu_entity ADD VALUE IF NOT EXISTS 'order_status_wording';

COMMENT ON TYPE menu.menu_entity IS
    'A kind of thing that has translatable fields, not only a menu one. M3-C added '
    'service_request_type (FR-SRV-001''s translated request catalog) and '
    'notification_template (FR-NOT-003''s approved customer templates); M3-D adds '
    'order_status_wording (FR-NOT-012''s localized customer status timeline). All three '
    'reuse M2-A''s approval workflow rather than getting a second store each.';
