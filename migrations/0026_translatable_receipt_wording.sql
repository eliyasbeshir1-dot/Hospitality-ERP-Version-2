-- =============================================================================
-- 0026 — Two labels: one translatable thing, one artifact kind
-- =============================================================================
-- This migration adds two labels and nothing else, for the reason 0011 and 0013 did:
-- psql runs one file in one transaction, and a label added by ALTER TYPE cannot be USED
-- in the transaction that added it. 0027 uses it, so it has to arrive first.
--
-- FR-I18N-001C says the bill and the receipt render COMPLETELY in the session language
-- for all three locales, including Ethiopic and RTL. The bill already does: 0019 gave
-- billing.component_wording its source text and billing.component_wording_for() resolves
-- it through menu.translation, approved, per locale, with English as the only fallback
-- and the charge kind's own name as the last resort.
--
-- A receipt carries four lines a bill does not: the bill total, the optional tip, the
-- total paid, and the payment method actually used. FR-BIL-010 requires the first three
-- as SEPARATE lines and FR-BIL-017 adds the fourth. None of them is a charge kind, so
-- billing.component_wording cannot hold their wording — its key is
-- ordering.charge_kind — and a second translation store for four strings is exactly the
-- thing 0013 refused to build: M2-B's finding was that a second copy of text is how the
-- two copies come to disagree.
--
-- So the receipt's own line wording joins menu.translation like everything else, and
-- reuses M2-A's approval workflow unchanged: draft -> in_review -> approved, a reviewer
-- and an approval timestamp required by CHECK, FR-I18N-010's machine-assistance
-- boundary, and menu.enforce_translation_review() refusing an approval nobody reviewed.
--
-- The type is still called menu.menu_entity and a receipt line is not a menu entity.
-- That is the naming debt 0013 accepted deliberately and this migration accepts on the
-- same terms. What the type means — and has meant since M2-A — is "a kind of thing that
-- has translatable fields".
-- =============================================================================

ALTER TYPE menu.menu_entity ADD VALUE IF NOT EXISTS 'receipt_line_wording';

COMMENT ON TYPE menu.menu_entity IS
    'A kind of thing that has translatable fields, not only a menu one. M3-C added '
    'service_request_type (FR-SRV-001''s translated request catalog) and '
    'notification_template (FR-NOT-003''s approved customer templates) so both reuse '
    'M2-A''s approval workflow rather than getting a second store each. M4-C adds '
    'receipt_line_wording for the four lines a receipt carries that a bill does not — '
    'the bill total, the optional tip, the total paid and the payment method actually '
    'used (FR-BIL-010, FR-BIL-017) — because FR-I18N-001C requires a receipt to render '
    'COMPLETELY in the session language and a line with no approved translation is the '
    'partially translated document M2-C found on a screen, printed onto paper nobody '
    'can re-render.';


-- ---------------------------------------------------------------------------
-- A receipt is an artifact of the correlation chain (FR-INT-014)
-- ---------------------------------------------------------------------------
-- 0025 put check, bill, tip and payment into ordering.artifact_kind so a correlation
-- link could be walked from an order to the money that settled it. A receipt is the last
-- artifact in that chain and the only one a customer takes away, so tracing a receipt
-- back to the order it settles is exactly what somebody holding a disputed slip needs.
--
-- ADDING THIS VALUE HERE, ONE MIGRATION EARLY, IS DELIBERATE AND IT IS ALSO A TEST. 0025
-- built ordering.correlation_link_rebuilt_by() to say which rebuild restores each kind of
-- link, and a DO block that refuses any kind mapping to NULL — because M4-B shipped a
-- defect where a rebuild three schemas away deleted a bill out of the chain and nothing
-- put it back. tests/m4b asserts the same property from pg_enum on every run. So a
-- 'receipt' kind added without an owner turns M4-B red, and 0027 has to name its owner
-- to make it green again. That is the safety net working rather than a sequencing risk.
ALTER TYPE ordering.artifact_kind ADD VALUE IF NOT EXISTS 'receipt';
