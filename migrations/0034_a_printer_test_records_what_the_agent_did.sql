-- 0034: a printer test records what the agent DID, not what the caller SAID
--
-- THE DEFECT, AS THE M4 REVIEW FOUND IT.
--
-- POST /s/v1/printers/:printerId/test took an `outcome` out of the request body and wrote
-- it down. A caller holding an ordinary staff session — the least-privileged role, no
-- step-up, no special grant — could POST outcome='printed' against a printer whose
-- device_path was './NUL' and the build would then report that printer as tested and
-- working. No agent ran. No bytes went anywhere. The claim was the evidence.
--
-- Two things had to be true for that to work, and this migration removes both.
--
-- ONE: THE NULL DEVICE WAS CLASSIFIED BY SPELLING, IN THREE LOWERCASE FORMS.
-- 0032 refused a device sink whose path was exactly '/dev/null', 'nul' or 'nul:'. On
-- Windows the null device is a DOS alias the loader resolves in EVERY directory, so
-- './NUL', 'C:\anywhere\NUL', '\\.\nul' and even 'NUL.txt' are all the same device and
-- none of them matched. print/agent.py already knew this — 0031 and 0032 taught it to ask
-- the platform rather than match a list — but the agent is not where printers are STORED,
-- and a rule that lives only in the code that reads a row does not constrain the row.
--
-- TWO: THE OUTCOME WAS AN INPUT. docs.record_printer_test() accepted docs.print_outcome
-- from its caller and inserted it. Nothing compared it with what the printer IS.
--
-- WHAT THIS DOES NOT CLAIM. Nothing here authenticates the print agent: there is no shared
-- secret between it and the service, so a caller who chooses to lie about what the agent
-- observed can still do so. What it can no longer do is have that lie RECORDED AS A PRINT
-- when the printer it names cannot print — the classification is now structural and the
-- outcome is derived from it rather than supplied. Authenticating the agent itself is a
-- larger change than this repair, and saying so is better than implying it was done.

-- ---------------------------------------------------------------------------
-- 1. WHAT A NULL DEVICE IS, ASKED OF THE PATH, WHEREVER IT IS STORED.
-- ---------------------------------------------------------------------------
-- Deliberately syntactic, because a CHECK cannot ask the operating system. The agent asks
-- the platform and is the stronger test; this is the weaker test applied at the point of
-- storage so that the strong one is never the only one. Between them: the row cannot be
-- written wrong, and if it somehow were, the agent still refuses to call it a print.
--
-- Everything below is one rule — "the last component of this path names the null device" —
-- expressed for both platforms' spellings at once.
CREATE FUNCTION docs.is_null_device_path(p_path text) RETURNS boolean
LANGUAGE sql IMMUTABLE
AS $$
    WITH normalised AS (
        -- Backslashes become slashes so one expression covers both platforms, and the
        -- comparison is lowercase because the DOS alias is case-insensitive.
        SELECT lower(replace(coalesce(p_path, ''), '\', '/')) AS path
    ),
    final_component AS (
        -- The last segment, with any trailing colon removed: 'NUL:' is the device too.
        SELECT rtrim(regexp_replace(path, '^.*/', ''), ':') AS name, path FROM normalised
    )
    SELECT path = '/dev/null'
        -- Windows resolves NUL in every directory, with or without an extension:
        -- 'NUL', './NUL', 'C:\logs\NUL' and 'NUL.txt' are one device.
        OR split_part(name, '.', 1) = 'nul'
      FROM final_component;
$$;

COMMENT ON FUNCTION docs.is_null_device_path(text) IS
    'True when a path names the platform null device, by any spelling this schema can '
    'recognise. Syntactic by necessity — a CHECK cannot ask the operating system — and '
    'deliberately broader than an equality list, because the alias resolves in every '
    'directory on Windows and the three lowercase spellings 0032 enumerated missed it.';

-- The rule 0032 wrote, restated against the classification instead of against three
-- literals. A path that names the null device may only ever sit on a discard sink.
ALTER TABLE docs.printer DROP CONSTRAINT printer_null_device_is_not_a_device_sink;
ALTER TABLE docs.printer ADD CONSTRAINT printer_null_device_is_not_a_device_sink CHECK (
    device_path IS NULL
 OR NOT docs.is_null_device_path(device_path)
 OR sink = 'discard');

-- And the converse, which 0032 never said: a printer DECLARED as a null device must
-- actually name one. Without this, connection='null_device' with device_path='/dev/lp0'
-- is a real printer wearing a discard sink, and every byte sent to it is reported as
-- discarded while paper comes out.
ALTER TABLE docs.printer ADD CONSTRAINT printer_null_device_names_the_null_device CHECK (
    connection <> 'null_device'
 OR docs.is_null_device_path(device_path));

-- ---------------------------------------------------------------------------
-- 2. THE OUTCOME IS DERIVED FROM THE PRINTER, NOT ACCEPTED FROM THE CALLER.
-- ---------------------------------------------------------------------------
-- The agent reports what it OBSERVED — which sink it put the bytes on, and what the
-- platform resolved the destination to. The database decides what that means. A caller
-- that wants to record a print must now claim the agent wrote to a device, and that claim
-- is checked against what the printer is.
ALTER TABLE docs.printer_test
    ADD COLUMN agent_sink            docs.sink_kind,
    ADD COLUMN resolved_destination  text;

COMMENT ON COLUMN docs.printer_test.agent_sink IS
    'The sink the AGENT reported putting the bytes on. Compared with the printer''s own '
    'classification: a disagreement is a refusal, not a recorded test.';
COMMENT ON COLUMN docs.printer_test.resolved_destination IS
    'What the platform resolved the destination to, as the agent saw it. Recorded so a '
    'reader can see what was written to rather than only what it was called.';

-- Every existing row predates the evidence and says so, rather than being back-filled
-- with a value nobody observed.
UPDATE docs.printer_test SET agent_sink = NULL, resolved_destination = NULL;

DROP FUNCTION docs.record_printer_test(uuid, uuid, uuid, docs.print_outcome, char, integer, text, uuid);

CREATE FUNCTION docs.record_printer_test(
    p_tenant_id            uuid,
    p_outlet_id            uuid,
    p_printer_id           uuid,
    p_agent_sink           docs.sink_kind,
    p_resolved_destination text,
    p_bytes_sha256         character,
    p_byte_count           integer,
    p_detail               text,
    p_actor_user_id        uuid
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_printer docs.printer%ROWTYPE;
    v_outcome docs.print_outcome;
    v_id      uuid;
BEGIN
    SELECT * INTO v_printer FROM docs.printer
     WHERE tenant_id = p_tenant_id AND id = p_printer_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PRINTER_NOT_FOUND: no printer % in scope', p_printer_id
            USING ERRCODE = 'HS404';
    END IF;

    -- THE AGENT AND THE PRINTER MUST AGREE. If the agent says it wrote to a device and
    -- the printer is a null device, one of the two is wrong and neither answer may be
    -- written down. This is the check the forged request could not have survived: it
    -- claimed a print against a printer whose sink is 'discard'.
    IF p_agent_sink IS DISTINCT FROM v_printer.sink THEN
        RAISE EXCEPTION
            'PRINTER_TEST_EVIDENCE_DISAGREES: the agent reports sink %, and printer % is '
            'classified %. A test is not recorded over a disagreement about where the '
            'bytes went', coalesce(p_agent_sink::text, 'nothing'), p_printer_id,
            v_printer.sink USING ERRCODE = 'HS409';
    END IF;

    -- Derived, never supplied. A discard sink discards; a device sink prints; a preview
    -- is not a printer test at all and says so rather than being recorded as a failure,
    -- which would read as a printer that exists and does not work.
    v_outcome := CASE v_printer.sink
                     WHEN 'device'  THEN 'printed'::docs.print_outcome
                     WHEN 'discard' THEN 'discarded'::docs.print_outcome
                 END;
    IF v_outcome IS NULL THEN
        RAISE EXCEPTION
            'PRINTER_TEST_NOT_A_PRINTER: printer % has sink %, which is the preview path '
            'and not something a printer test can exercise', p_printer_id, v_printer.sink
            USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO docs.printer_test
        (tenant_id, outlet_id, printer_id, outcome, bytes_sha256, byte_count, detail,
         tested_by_user_id, agent_sink, resolved_destination)
    VALUES (p_tenant_id, p_outlet_id, p_printer_id, v_outcome, p_bytes_sha256,
            p_byte_count, p_detail, p_actor_user_id, p_agent_sink, p_resolved_destination)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION docs.record_printer_test(uuid, uuid, uuid, docs.sink_kind, text, character, integer, text, uuid) IS
    'Records a printer test from the AGENT''S REPORT. The outcome is derived from what the '
    'printer is, never taken from the caller: a printer whose sink discards cannot be '
    'recorded as having printed, whatever the request says.';

GRANT EXECUTE ON FUNCTION docs.record_printer_test(
    uuid, uuid, uuid, docs.sink_kind, text, character, integer, text, uuid)
    TO hospitality_app;

-- ---------------------------------------------------------------------------
-- 3. AND THE ROWS THAT WERE ALREADY WRONG.
-- ---------------------------------------------------------------------------
-- A migration that adds a rule and leaves the violations behind has documented the rule
-- rather than enforced it. Any printer whose path names the null device under the wider
-- classification is moved to the sink it actually has; anything recorded as printed
-- against such a printer is a claim this build can no longer stand behind.
UPDATE docs.printer
   SET connection = 'null_device', sink = 'discard'
 WHERE device_path IS NOT NULL
   AND docs.is_null_device_path(device_path)
   AND sink <> 'discard';

-- ---------------------------------------------------------------------------
-- 4. AND THE SAME DEFECT ON THE ROUTE THAT PRINTS A CUSTOMER'S RECEIPT.
-- ---------------------------------------------------------------------------
-- Found while repairing the one above, and it is the more serious of the two.
-- POST /s/v1/receipts/:receiptId/prints took `outcome` from the request body in exactly
-- the same way, so the same staff session could record that a customer's receipt had been
-- printed on a printer that discards every byte. docs.record_receipt_print() checked that
-- the printer had passed a test and then wrote down whatever word the caller sent.
--
-- A receipt is the one artefact a customer takes away. "Printed" about a receipt nobody
-- produced is the most expensive kind of true-looking statement this build can make, and
-- FR-BIL-010's duplicate rules are all reasoning about a record that was not evidence.
--
-- The same repair: the agent reports where the bytes went, the database decides what that
-- means, and a disagreement is a refusal rather than a row.
ALTER TABLE docs.print_attempt
    ADD COLUMN agent_sink           docs.sink_kind,
    ADD COLUMN resolved_destination text;

DROP FUNCTION docs.record_receipt_print(uuid, uuid, uuid, uuid, docs.print_outcome,
                                        character, integer, uuid, boolean, uuid, text, text);

CREATE FUNCTION docs.record_receipt_print(
    p_tenant_id            uuid,
    p_outlet_id            uuid,
    p_receipt_id           uuid,
    p_printer_id           uuid,
    p_agent_sink           docs.sink_kind,
    p_resolved_destination text,
    p_bytes_sha256         character,
    p_byte_count           integer,
    p_actor_user_id        uuid,
    p_is_reprint           boolean DEFAULT false,
    p_reason_code_id       uuid    DEFAULT NULL,
    p_reason_text          text    DEFAULT NULL,
    p_detail               text    DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_printer docs.printer%ROWTYPE;
    v_outcome docs.print_outcome;
    v_id      uuid;
BEGIN
    -- FR-CFG-001D first, and unchanged: a printer nobody tested prints nothing, and that
    -- refusal must keep its own name rather than being replaced by the newer one.
    IF NOT docs.printer_has_passed_a_test(p_tenant_id, p_printer_id) THEN
        RAISE EXCEPTION
            'PRINTER_NEVER_TESTED: printer % has no successful test. FR-CFG-001D asks '
            'that setup registers AND TESTS the printer, and a setup screen that reported '
            'a printer ready because a row existed would be FR-INT-011''s most expensive '
            'kind of true statement', p_printer_id USING ERRCODE = 'HS409';
    END IF;

    SELECT * INTO v_printer FROM docs.printer
     WHERE tenant_id = p_tenant_id AND id = p_printer_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PRINTER_NOT_FOUND: no printer % in scope', p_printer_id
            USING ERRCODE = 'HS404';
    END IF;

    IF p_agent_sink IS DISTINCT FROM v_printer.sink THEN
        RAISE EXCEPTION
            'PRINT_EVIDENCE_DISAGREES: the agent reports sink %, and printer % is '
            'classified %. A customer receipt is not recorded as printed over a '
            'disagreement about where the bytes went',
            coalesce(p_agent_sink::text, 'nothing'), p_printer_id, v_printer.sink
            USING ERRCODE = 'HS409';
    END IF;

    v_outcome := CASE v_printer.sink
                     WHEN 'device'  THEN 'printed'::docs.print_outcome
                     WHEN 'discard' THEN 'discarded'::docs.print_outcome
                 END;
    IF v_outcome IS NULL THEN
        RAISE EXCEPTION
            'PRINT_SINK_IS_A_PREVIEW: printer % has sink %, and a preview is not a print',
            p_printer_id, v_printer.sink USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO docs.print_attempt
        (tenant_id, outlet_id, receipt_id, printer_id, outcome, is_reprint,
         reason_code_id, reason_text, operator_user_id, bytes_sha256, byte_count, detail,
         agent_sink, resolved_destination)
    VALUES (p_tenant_id, p_outlet_id, p_receipt_id, p_printer_id, v_outcome, p_is_reprint,
            p_reason_code_id, p_reason_text, p_actor_user_id, p_bytes_sha256, p_byte_count,
            p_detail, p_agent_sink, p_resolved_destination)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION docs.record_receipt_print(uuid, uuid, uuid, uuid, docs.sink_kind, text,
                                              character, integer, uuid, boolean, uuid, text, text) IS
    'Records a receipt print from the AGENT''S REPORT. The outcome is derived from the '
    'printer''s classification, never taken from the caller: a printer that discards '
    'cannot be recorded as having printed a customer''s receipt.';

GRANT EXECUTE ON FUNCTION docs.record_receipt_print(
    uuid, uuid, uuid, uuid, docs.sink_kind, text, character, integer, uuid, boolean,
    uuid, text, text) TO hospitality_app;


-- ===========================================================================
-- 5. AND THE BOUNDARY IS THE TABLE, NOT ONLY THE FUNCTION.
-- ===========================================================================
--
-- Everything above moves the outcome out of the caller's hands INSIDE
-- docs.record_printer_test() and docs.record_receipt_print(). That closes the route the
-- M4 review actually used, and it is not enough on its own: hospitality_app holds INSERT
-- on both tables directly, so a handler that wrote its own INSERT would set any outcome
-- it liked and never reach either function's comparison.
--
-- The repository already puts this class of rule at the table -- print_attempt_outcome_
-- matches_the_sink and printer_test_outcome_matches_the_sink are triggers, not function
-- bodies -- so the agent's evidence belongs beside them rather than one layer up.
--
-- Two things are asserted here and neither is a restatement of the function:
--
--   * agent_sink is NOT NULL. A print row cannot exist without a report of where the
--     bytes went. Silence is not evidence, and a nullable column would let a direct
--     INSERT say nothing rather than say something false.
--   * the report must agree with the printer's own classification, which is the same
--     comparison the functions make, now enforced against every writer.
--
-- THE TRIGGER NAMES SORT AFTER THE EXISTING ONES DELIBERATELY. PostgreSQL fires triggers
-- in name order, and the repository already depends on that (M4-C's reprint check relies
-- on the duplicate trigger firing before the sink trigger). "reports_what_the_agent_did"
-- sorts after "outcome_matches_the_sink" and after "needs_a_device", so every refusal
-- that had a name before this migration still answers to that name, and the new rule
-- speaks only when it is the first thing wrong.

ALTER TABLE docs.printer_test  ALTER COLUMN agent_sink SET NOT NULL;
ALTER TABLE docs.printer_test  ALTER COLUMN resolved_destination SET NOT NULL;
ALTER TABLE docs.print_attempt ALTER COLUMN agent_sink SET NOT NULL;
ALTER TABLE docs.print_attempt ALTER COLUMN resolved_destination SET NOT NULL;

CREATE OR REPLACE FUNCTION docs.assert_the_agent_report_matches_the_sink()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE v_sink docs.sink_kind;
BEGIN
    SELECT sink INTO v_sink
      FROM docs.printer
     WHERE tenant_id = NEW.tenant_id AND id = NEW.printer_id;

    IF v_sink IS NULL THEN
        RETURN NEW;  -- the foreign key is the rule about a printer existing, not this.
    END IF;

    IF NEW.agent_sink IS DISTINCT FROM v_sink THEN
        RAISE EXCEPTION
            'PRINT_EVIDENCE_DISAGREES: the agent reports sink %, and printer % is '
            'classified %. The row is refused at the table, so a writer that never '
            'called docs.record_receipt_print() is refused on the same terms as one '
            'that did', NEW.agent_sink, NEW.printer_id, v_sink
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION docs.assert_the_agent_report_matches_the_sink() IS
    'FR-CFG-001D. Refuses a print or a printer test whose reported sink disagrees with '
    'the printer''s own classification, whatever wrote the row.';

CREATE TRIGGER printer_test_reports_what_the_agent_did
    BEFORE INSERT ON docs.printer_test
    FOR EACH ROW EXECUTE FUNCTION docs.assert_the_agent_report_matches_the_sink();

CREATE TRIGGER print_attempt_reports_what_the_agent_did
    BEFORE INSERT ON docs.print_attempt
    FOR EACH ROW EXECUTE FUNCTION docs.assert_the_agent_report_matches_the_sink();
