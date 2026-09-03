-- =============================================================================
-- 0022 — Two labels, and nothing else
-- =============================================================================
-- The fifth migration of this shape, for the fifth time for the same reason: psql runs
-- one file in one transaction, and a label added by ALTER TYPE cannot be USED in the
-- transaction that added it. 0023, 0024 and 0025 use both, so they have to arrive first.
--
-- 'payment' and 'tip' complete ordering.artifact_kind for Phase 1's financial half.
-- 0018 added 'check' and 'bill' and said why they were two artifacts and not one; these
-- two are the other half of the same sentence. FR-INT-014 asks that the correlation chain
-- link every artifact a request produced, and the partial closure opened at M3-C names
-- bill, payment and tip as the three the chain could not yet carry. 0019 supplied the
-- bill. These supply the rest, and the chain then carries eight of the ten artifacts
-- FR-INT-014 names — outlet persistence and the synchronization record remain M5a's, and
-- the register says so in its own entry rather than in a comment here.
--
-- A PAYMENT and a TIP are separate links rather than one 'payment' link carrying both,
-- and that is the whole doctrine of M4-A restated at the level of the chain: a tip is
-- never part of a bill balance, so a chain that reached a tip only THROUGH a payment
-- would make the tip an attribute of money received rather than a record of its own.
-- FR-BIL-015 lets a payer tip without paying anybody's bill and FR-PAY-009 lets a tip be
-- refunded without touching a bill payment; both need the tip to be findable on its own.
-- =============================================================================

ALTER TYPE ordering.artifact_kind ADD VALUE IF NOT EXISTS 'payment';
ALTER TYPE ordering.artifact_kind ADD VALUE IF NOT EXISTS 'tip';

COMMENT ON TYPE ordering.artifact_kind IS
    'What the correlation chain can link (FR-ORD-019A, FR-INT-014). A request, a cart, a '
    'table session, an order, a fulfillment ticket, a service request, a check, a bill, a '
    'payment and a tip. Each is linked BY THE FOLD that creates it rather than by the '
    'caller, so a rebuild restores the chain instead of restoring everything except the '
    'chain. Outlet persistence and the synchronization record are M5a''s and the partial '
    'closure register carries the entry.';
