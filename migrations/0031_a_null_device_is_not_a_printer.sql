-- 0031: a write to the null device is not a print, and the schema says so
--
-- WHAT WAS WRONG. docs.printer held a row named "M4C counter printer" declaring
-- connection 'character_device' and sink 'device', whose device_path was /dev/null. The
-- database believed it was a printer. Every 'printed' outcome recorded against it — in
-- tests/m4c and in the golden journeys — was a record that bytes reached a printer, and
-- no bytes reached anything. FR-BIL-017 asks for a real physical customer receipt, and a
-- null device answering to the word "printed" is the claim reading as proved.
--
-- M4-B settled the equivalent question for payments: a simulated outcome must not be
-- recordable as a live one, and it is a TYPE that keeps them apart rather than a flag,
-- because a boolean is flipped by an UPDATE and a type is not. The print path had two
-- sinks — device and preview — and no third for the case every runner actually has: a
-- character device that discards. This adds it.
--
-- WHAT IS NOW IMPOSSIBLE, BY CONSTRUCTION RATHER THAN BY CARE:
--   * a printer whose device_path is the null device cannot declare sink 'device';
--   * a discard sink cannot carry the outcome 'printed';
--   * a device sink cannot carry the outcome 'discarded'.
-- So a receipt "printed" on a runner is a statement the schema will not hold.

ALTER TYPE docs.connection_kind ADD VALUE IF NOT EXISTS 'null_device';
ALTER TYPE docs.sink_kind       ADD VALUE IF NOT EXISTS 'discard';
ALTER TYPE docs.print_outcome   ADD VALUE IF NOT EXISTS 'discarded';
