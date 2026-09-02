-- =============================================================================
-- 0018 — Five labels, and nothing else
-- =============================================================================
-- The same shape as 0011, 0013 and 0016, and for the same reason: psql runs one file in
-- one transaction, and a label added by ALTER TYPE cannot be USED in the transaction that
-- added it. 0019 and 0020 use all five, so they have to arrive first.
--
-- 'counter' completes ordering.order_origin. FR-ORD-001B says the counter POS channel
-- uses the SAME aggregate and policy model as the dine-in channels with no divergent
-- order path, and the way to obey that is to make the counter a value of the dimension
-- the aggregate already has rather than a second path that agrees. M3-A built the origin
-- dimension with two values and M3-D proved the two were one implementation; this adds a
-- third to the same dimension. menu.sales_channel has carried 'counter' since M2-A —
-- the CHANNEL was always expressible and the ORIGIN was not.
--
-- 'check' and 'bill' complete ordering.artifact_kind, which is the correlation chain's
-- vocabulary (FR-ORD-019A, FR-INT-014). They are two artifacts and not one: a CHECK is
-- what a party is being billed FOR — an allocation of order lines, which can be split and
-- merged while the money is still undecided — and a BILL is the calculated, versioned
-- document issued from a check, which can be voided, credited and reissued but never
-- edited. Splitting them is what lets FR-BIL-002's allocation and FR-BIL-009's
-- correction be different mechanisms with different rules, and it is what makes "the
-- order ledger is untouched" true: neither of them is an order.
-- =============================================================================

ALTER TYPE ordering.order_origin ADD VALUE IF NOT EXISTS 'counter';

ALTER TYPE ordering.artifact_kind ADD VALUE IF NOT EXISTS 'check';
ALTER TYPE ordering.artifact_kind ADD VALUE IF NOT EXISTS 'bill';

-- 'bill_component_wording' completes menu.menu_entity. FR-BIL-007 asks for a TRANSLATED
-- bill summary, and the only translation store this system has is M2-A's menu.translation
-- with its review-then-approve workflow. A bill that carried its own wording table would
-- be a second translation mechanism nobody reviews — the exact mistake 0017 refused for
-- order status. So a component label is an entity like any other: identity in billing,
-- approved bodies in menu.translation, and no migration writing an approval.
ALTER TYPE menu.menu_entity ADD VALUE IF NOT EXISTS 'bill_component_wording';

-- 'payment_dependent' completes ordering.acceptance_mode. FR-ORD-007B: an order
-- configured this way is accepted ONLY after a verified payment outcome. M4-A has no
-- payment and no verification — both are M4-B — so what this label buys today is a
-- policy value the system UNDERSTANDS and refuses to accept on, rather than a policy
-- value that would fail as an invalid enum literal deep inside submit_order. It fails
-- closed: an order in this mode stays submitted until something can verify a payment.
-- 0020 supplies the refusal; the closure register names M4-B for the acceptance.
ALTER TYPE ordering.acceptance_mode ADD VALUE IF NOT EXISTS 'payment_dependent';

COMMENT ON TYPE ordering.order_origin IS
    'Where an order came from: a guest''s own device, a member of staff on a handheld, or '
    'the counter. One dimension of one aggregate — FR-ORD-001B and FR-POS-003A both say '
    'the channels share an implementation, and tests/m3d asserts from the catalog that no '
    'second implementation of any ordering rule can exist for any of them.';

COMMENT ON TYPE ordering.artifact_kind IS
    'What the correlation chain can link (FR-ORD-019A, FR-INT-014). A check allocates '
    'order lines and may be split or merged; a bill is the calculated document issued '
    'from a check and may be voided, credited or reissued but never edited. Payment and '
    'the synchronization record are M4-B''s and M5a''s, and the closure register names '
    'both.';

COMMENT ON TYPE menu.menu_entity IS
    'What M2-A''s review-and-approve translation workflow governs. A bill component''s '
    'label joins the list rather than getting a translation store of its own, so the '
    'Amharic on a bill is approved by the same person, through the same workflow, as the '
    'Amharic on a menu item.';

COMMENT ON TYPE ordering.acceptance_mode IS
    'How an outlet accepts an order of a given origin (FR-ORD-007A, FR-ORD-007B). '
    'Automatic on submission, confirmed by a member of staff, or dependent on a verified '
    'payment outcome. The third refuses acceptance outright until M4-B can verify one, '
    'which is the fail-closed reading of a requirement whose verifier does not exist yet.';
