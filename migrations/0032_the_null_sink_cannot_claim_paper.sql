-- 0032: the constraints that make 0031's values load-bearing
--
-- Separate from 0031 because PostgreSQL will not let a transaction USE an enum value it
-- added itself. 0031 adds 'null_device', 'discard' and 'discarded'; this file is where
-- they start refusing things.

-- 1. A NULL DEVICE IS ITS OWN CONNECTION, AND ITS OWN SINK.
--    The pairing was already derived rather than accepted; this adds the third row of
--    the derivation instead of letting a null device masquerade as a character device.
ALTER TABLE docs.printer DROP CONSTRAINT printer_sink_is_derived_from_the_connection;
ALTER TABLE docs.printer ADD CONSTRAINT printer_sink_is_derived_from_the_connection CHECK (
        (connection IN ('character_device', 'network_socket') AND sink = 'device')
     OR (connection = 'file' AND sink = 'preview')
     OR (connection = 'null_device' AND sink = 'discard'));

-- 1a. AND ITS DESTINATION IS A PATH, like every other character device.
--     0027 enumerated the connections that carry a device_path and a null device is one,
--     so the destination rule learns the third value at the same time as the sink rule.
ALTER TABLE docs.printer DROP CONSTRAINT printer_destination_matches_the_connection;
ALTER TABLE docs.printer ADD CONSTRAINT printer_destination_matches_the_connection CHECK (
        (connection = 'network_socket' AND host_and_port IS NOT NULL AND device_path IS NULL)
     OR (connection IN ('character_device', 'file', 'null_device')
         AND device_path IS NOT NULL AND host_and_port IS NULL));

-- 1b. THE ROWS THAT WERE ALREADY WRONG.
--     Any printer already pointing at the null device is relabelled to what it is. The
--     identity trigger refuses exactly this kind of UPDATE — promoting or demoting a
--     printer rewrites what every attempt recorded against it meant — and that refusal is
--     right for an application and wrong for a migration, which is the one place a
--     mislabelled row is supposed to be corrected. It is disabled for this statement and
--     put back immediately.
--
--     The print_attempt rows already recorded against these printers are NOT touched.
--     They are an append-only ledger and they say what was recorded; rewriting them would
--     be this migration doing the thing it exists to forbid. History keeps the false
--     claim, and the constraints below stop another being made.
--     Row security comes off with it, and goes straight back on WITH FORCE. Without
--     this the UPDATE matches nothing: migrations run as the migrator with no request
--     context, FORCE RLS applies to the owner too, and a correction that silently
--     touches zero rows would have left the constraint below to fail on data this
--     statement was supposed to have fixed. It did exactly that once.
ALTER TABLE docs.printer DISABLE TRIGGER printer_identity_is_immutable;
ALTER TABLE docs.printer NO FORCE ROW LEVEL SECURITY;
ALTER TABLE docs.printer DISABLE ROW LEVEL SECURITY;
UPDATE docs.printer
   SET connection = 'null_device', sink = 'discard'
 WHERE device_path IS NOT NULL
   AND lower(device_path) IN ('/dev/null', 'nul', 'nul:');
ALTER TABLE docs.printer ENABLE ROW LEVEL SECURITY;
ALTER TABLE docs.printer FORCE ROW LEVEL SECURITY;
ALTER TABLE docs.printer ENABLE TRIGGER printer_identity_is_immutable;

-- 2. AND THE PATH DECIDES, NOT THE LABEL.
--    Both spellings, because the null device is /dev/null on POSIX and NUL on Windows and
--    this repository runs on both. This is the constraint that would have refused the
--    "M4C counter printer" row on the day it was written.
ALTER TABLE docs.printer ADD CONSTRAINT printer_null_device_is_not_a_device_sink CHECK (
    device_path IS NULL
    OR lower(device_path) NOT IN ('/dev/null', 'nul', 'nul:')
    OR sink = 'discard');

COMMENT ON CONSTRAINT printer_null_device_is_not_a_device_sink ON docs.printer IS
    'FR-BIL-017. A printer whose destination is the null device may not call itself a '
    'device sink. The row this refuses existed: a fixture printer named "counter '
    'printer", declaring character_device, pointing at /dev/null, against which every '
    'receipt in the suite and the journeys was recorded as printed.';

-- 3. THE OUTCOME A SINK MAY CARRY.
--    docs.print_outcome is one type across both, because a discard IS an attempt and
--    carries the same operator, reason and deduplication rules — what differs is the
--    claim it makes about paper, and that is what is constrained.
CREATE OR REPLACE FUNCTION docs.assert_outcome_matches_the_sink() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE v_sink docs.sink_kind;
BEGIN
    SELECT p.sink INTO v_sink FROM docs.printer p
     WHERE p.tenant_id = NEW.tenant_id AND p.id = NEW.printer_id;

    IF v_sink = 'discard' AND NEW.outcome <> 'discarded' THEN
        RAISE EXCEPTION
            'NULL_DEVICE_CANNOT_CLAIM_PAPER: printer % discards its bytes, and %.% '
            'records outcome %. A write to the null device is not a print: it proves the '
            'bytes were produced and encoded, and nothing about a machine having turned '
            'them into legible paper. Record it as discarded, which is what happened',
            NEW.printer_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.outcome
            USING ERRCODE = 'HS409';
    END IF;

    IF v_sink = 'device' AND NEW.outcome = 'discarded' THEN
        RAISE EXCEPTION
            'DEVICE_DID_NOT_DISCARD: printer % is a real device sink and %.% records the '
            'bytes as discarded. A discard is what a null device does; a device that '
            'failed records failed',
            NEW.printer_id, TG_TABLE_SCHEMA, TG_TABLE_NAME
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER print_attempt_outcome_matches_the_sink
    BEFORE INSERT ON docs.print_attempt
    FOR EACH ROW EXECUTE FUNCTION docs.assert_outcome_matches_the_sink();

CREATE TRIGGER printer_test_outcome_matches_the_sink
    BEFORE INSERT ON docs.printer_test
    FOR EACH ROW EXECUTE FUNCTION docs.assert_outcome_matches_the_sink();

-- 4. A DISCARD SINK IS A SINK THE ATTEMPT TABLES ACCEPT.
--    0027's trigger expected 'device' for print_attempt and printer_test and refused
--    everything else, which would now refuse the discard sink outright rather than let
--    it record what it did.
CREATE OR REPLACE FUNCTION docs.assert_attempt_matches_the_sink() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_sink     docs.sink_kind;
    v_accepted docs.sink_kind[] := CASE TG_TABLE_NAME
        WHEN 'print_attempt'  THEN ARRAY['device', 'discard']::docs.sink_kind[]
        WHEN 'printer_test'   THEN ARRAY['device', 'discard']::docs.sink_kind[]
        WHEN 'render_attempt' THEN ARRAY['preview']::docs.sink_kind[]
    END;
BEGIN
    IF v_accepted IS NULL THEN
        RAISE EXCEPTION
            'SINK_EXPECTATION_UNKNOWN: %.% carries this trigger and no expected sink is '
            'declared for it. Refusing rather than defaulting: a sink check that passed '
            'a table it had no rule for would be an assertion that cannot fail',
            TG_TABLE_SCHEMA, TG_TABLE_NAME USING ERRCODE = 'HS500';
    END IF;

    SELECT p.sink INTO v_sink FROM docs.printer p
     WHERE p.tenant_id = NEW.tenant_id AND p.id = NEW.printer_id;

    IF NOT (v_sink = ANY (v_accepted)) THEN
        RAISE EXCEPTION
            'SINK_MISMATCH: %.% accepts % and printer % is a % sink. A file that received '
            'these bytes is not a receipt a customer received, and the row would say it was',
            TG_TABLE_SCHEMA, TG_TABLE_NAME, v_accepted, NEW.printer_id, v_sink
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

-- 5. THE REGISTRAR DERIVES THE THIRD SINK TOO.
CREATE OR REPLACE FUNCTION docs.register_printer(
    p_tenant_id uuid, p_outlet_id uuid, p_display_name text,
    p_connection docs.connection_kind, p_device_path text DEFAULT NULL,
    p_host_and_port text DEFAULT NULL, p_actor_user_id uuid DEFAULT NULL)
RETURNS uuid
LANGUAGE plpgsql SECURITY INVOKER
AS $$
DECLARE v_id uuid;
BEGIN
    INSERT INTO docs.printer
        (tenant_id, outlet_id, display_name, connection, sink, device_path,
         host_and_port, registered_by_user_id)
    VALUES (p_tenant_id, p_outlet_id, p_display_name, p_connection,
            CASE p_connection
                WHEN 'file'        THEN 'preview'::docs.sink_kind
                WHEN 'null_device' THEN 'discard'::docs.sink_kind
                ELSE 'device'::docs.sink_kind
            END,
            p_device_path, p_host_and_port, p_actor_user_id)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

-- 6. AND "TESTED" MEANS EXERCISED, WHICH IS SINK-DEPENDENT.
--
--    docs.printer_has_passed_a_test() asked for the outcome 'printed', which no discard
--    sink can ever carry — so with 0032 in place FR-CFG-001D's precondition became
--    unsatisfiable on every runner and no receipt could be printed at all. The suite
--    caught it on the first clean rebuild.
--
--    The question the precondition is really asking is "has anybody ever driven this
--    printer successfully?", and the answer for a device is 'printed' and for a discard
--    sink is 'discarded'. Both are successful exercises of the path; they differ in what
--    they prove about paper, which is carried by the outcome word itself and by
--    FR-BIL-017's open register entry — not by pretending the test never happened.
--
--    An UNTESTED printer still fails, which is the whole of FR-CFG-001D. A printer with
--    a FAILED test still fails.
CREATE OR REPLACE FUNCTION docs.printer_has_passed_a_test(p_tenant_id uuid, p_printer_id uuid)
RETURNS boolean
LANGUAGE sql STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
          FROM docs.printer_test t
          JOIN docs.printer p ON p.tenant_id = t.tenant_id AND p.id = t.printer_id
         WHERE t.tenant_id = p_tenant_id AND t.printer_id = p_printer_id
           AND t.outcome = CASE p.sink
                               WHEN 'discard' THEN 'discarded'::docs.print_outcome
                               ELSE 'printed'::docs.print_outcome
                           END);
$$;

COMMENT ON FUNCTION docs.printer_has_passed_a_test(uuid, uuid) IS
    'FR-CFG-001D''s test half. "Passed" means the path was driven successfully for the '
    'sink it has: a device printed, a discard sink discarded. A printer nobody has '
    'driven fails either way, which is the precondition''s whole purpose.';
