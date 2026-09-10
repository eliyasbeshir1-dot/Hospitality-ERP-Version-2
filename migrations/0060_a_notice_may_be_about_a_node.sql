-- 0060: a notice may be about a node
--
-- notify.catalog_event has named eight edge notices since M3-C and M5a, six of them with
-- has_producer = false. Every one is about an OUTLET or the NODE serving it — a heartbeat
-- lost, local continuity entered, a sync conflict, a print job that failed. None of them
-- is about an order, a check or a bill.
--
-- notify.notification.subject_kind is ordering.artifact_kind NOT NULL, and that type has
-- eleven values, all of them things a guest orders or pays for. So there has never been
-- anything for an edge notice to point AT, which is a large part of why the producers were
-- deferred three times: FR-NOT-001, FR-NOT-005 and FR-INT-007 each say the routing is
-- complete and the producers are missing, and this is one of the reasons they were.
--
-- THE ENUM'S NAME NO LONGER QUITE FITS AND THAT IS THE HONEST TRADE. A node is not an
-- ordering artifact. The alternative is a second type and a change to
-- notify.notification's column, its index and every function that reads it — a much larger
-- change to avoid a naming awkwardness. Widening the type keeps one answer to "what is
-- this notice about" instead of two that can disagree, which is the same reasoning 0045
-- gave for keeping restrictions and sync states in one edge.plain_language.
--
-- IT IS ALONE IN THIS MIGRATION BECAUSE POSTGRESQL REQUIRES IT TO BE. A value added to an
-- enum cannot be USED until the transaction that added it has committed, and tools/migrate.py
-- runs each file in its own transaction. 0061 is the one that uses it.

ALTER TYPE ordering.artifact_kind ADD VALUE IF NOT EXISTS 'node';

COMMENT ON TYPE ordering.artifact_kind IS
    'What a notice, an event or a document is ABOUT. Eleven of the twelve are things a '
    'guest orders or pays for; `node` is the outlet''s continuity node, added at M5b '
    'because notify.catalog_event has named edge notices since M3-C and there was nothing '
    'for them to point at. The name is now slightly wrong and the alternative was a second '
    'type, a column change and two answers to the same question.';
