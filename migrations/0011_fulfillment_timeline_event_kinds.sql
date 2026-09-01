-- ===========================================================================
-- 0011 — Timeline event kinds for fulfillment
-- ===========================================================================
-- Gate M3, slice B. Stands alone for the same reason 0007 does: psql applies each
-- migration in one transaction, and PostgreSQL forbids USING an enum label in the
-- transaction that added it. Everything that uses these labels is in 0012.
--
-- ---------------------------------------------------------------------------
-- Why the ORDER timeline gets fulfillment labels at all
-- ---------------------------------------------------------------------------
-- FR-ORD-016A asks for a timeline of order, station and service events. M3-A built the
-- order half and recorded the station half as a partial closure against this slice. The
-- alternative to extending this type would be a second timeline that the reader has to
-- merge, and two timelines are two chronologies that can disagree about what happened
-- first.
--
-- These labels are for TIMELINE ENTRIES, not for the order ledger. A ticket's own
-- history lives in fulfillment.ticket_event, and ordering.order_event must never carry
-- one of these. That is already enforced without a new constraint:
-- order_event_before_required_for_changes enumerates every kind on one side or the
-- other, so a label in neither list satisfies neither branch and the row is refused.
-- 0012 asserts that, and tests/m3b proves it by attempting the insert.
--
-- What is NOT added here: no reason-code category. FR-CFG-003 enumerates exactly ten and
-- M1-C implemented exactly those ten, so rework, remake, service waste and serve
-- exceptions are CODES under 'service_failure', recall, transfer and priority overrides
-- are codes under 'manager_override', and the paper fallback is 'printer_failure'. The
-- governed set is the category; the operational distinction is the code within it.
-- ===========================================================================

ALTER TYPE ordering.event_kind ADD VALUE IF NOT EXISTS 'tickets_released';
ALTER TYPE ordering.event_kind ADD VALUE IF NOT EXISTS 'station_acknowledged';
ALTER TYPE ordering.event_kind ADD VALUE IF NOT EXISTS 'station_preparing';
ALTER TYPE ordering.event_kind ADD VALUE IF NOT EXISTS 'station_ready';
ALTER TYPE ordering.event_kind ADD VALUE IF NOT EXISTS 'items_collected';
ALTER TYPE ordering.event_kind ADD VALUE IF NOT EXISTS 'items_served';
ALTER TYPE ordering.event_kind ADD VALUE IF NOT EXISTS 'station_exception';
