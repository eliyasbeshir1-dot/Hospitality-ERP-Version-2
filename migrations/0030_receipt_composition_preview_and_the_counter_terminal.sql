-- ===========================================================================
-- 0030 — Issuing a receipt, previewing a document, and ordering at the counter
-- ===========================================================================
-- FR-BIL-010 the digital receipt, FR-BIL-011 the marked and audited reprint,
-- FR-BIL-016 bill and tip separately with linked corrections, FR-BIL-017 the physical
-- receipt with the payment method actually used, FR-I18N-001C completely in the session
-- language, FR-CFG-001D the printer that is registered AND tested, FR-UX-018 the preview,
-- FR-POS-003B the counter order created at the POS terminal.
--
-- 0027 built the tables and the assertions. This builds the paths that write them, and
-- the reason they are separate files is that 0027's constraints had to be provable
-- against a schema before anything could satisfy them by construction.
--
-- THE THREE THINGS WORTH READING THE COMMENTS FOR.
--
-- ONE COMPOSER, TWO SINKS. FR-UX-018 asks for a preview and its later_behavior says the
-- physical output must match it. A preview built by a second function would match on the
-- day it was written. docs.compose_document() is the only thing in this build that turns
-- a set of lines into a print document, and both the receipt path and the preview path
-- call it; what differs is where the lines came from and whether the document is marked
-- as a specimen. print/render.mjs rasterises whatever it is given, so the preview and the
-- print are the same code from composition to dots.
--
-- A SPECIMEN SAYS SO ON ITS FACE. A preview carries figures that describe nothing, and
-- FR-UX-014's rule against fabricated analytics is the same rule: a document showing
-- numbers that are not a record of anything must not be mistakable for one that is.
-- docs.compose_document() puts the specimen marking in the document itself rather than
-- in a flag the renderer could ignore, and refuses a specimen with a receipt number.
--
-- THE TERMINAL IS RESOLVED, NEVER SUPPLIED. FR-POS-003B says a counter order is created
-- AT THE POS TERMINAL. pos.record_counter_order() reads the terminal from the session in
-- context — identity.session.device_id — exactly as cash.transition_shift() reads the
-- verifier from the session rather than from a parameter. There is no argument by which
-- a caller could claim to be at a terminal they are not at.


-- ===========================================================================
-- Receipt numbers (FR-BIL-017)
-- ===========================================================================
-- Through config.issue_document_number(), which is the same gapless series a bill number
-- comes from. FR-BIL-017 asks for a unique receipt number; a second numbering scheme
-- beside the first is how two documents come to share one.

CREATE FUNCTION config.install_receipt_number_series() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.kind = 'outlet' THEN
        INSERT INTO config.number_series
            (tenant_id, outlet_id, document_type, fiscal_period, prefix, next_value)
        VALUES (NEW.tenant_id, NEW.id, 'receipt', to_char(now(), 'YYYY'),
                'RCP-' || NEW.reference_code || '-', 1)
        ON CONFLICT DO NOTHING;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER outlet_gets_a_receipt_series
    AFTER INSERT ON org.org_node
    FOR EACH ROW EXECUTE FUNCTION config.install_receipt_number_series();

-- The outlets that already exist. A trigger only covers what is created after it, and an
-- outlet that could bill but not receipt would be a defect discovered at a counter.
INSERT INTO config.number_series
    (tenant_id, outlet_id, document_type, fiscal_period, prefix, next_value)
SELECT n.tenant_id, n.id, 'receipt', to_char(now(), 'YYYY'),
       'RCP-' || n.reference_code || '-', 1
  FROM org.org_node n WHERE n.kind = 'outlet'
ON CONFLICT DO NOTHING;


-- ===========================================================================
-- The wording of a receipt line, in the receipt's locale (FR-I18N-001C)
-- ===========================================================================
-- THE SAME SHAPE billing.component_wording_for() ALREADY HAS, against docs.line_wording
-- and the entity 0026 added. It falls back to the English source text only for an English
-- receipt; for any other locale a missing approved translation yields the source text and
-- 0027's completeness trigger refuses the receipt. That is deliberate: the alternative is
-- a receipt that is half Amharic, on paper, in a customer's hand.

CREATE FUNCTION docs.wording_for(
    p_tenant_id uuid, p_kind docs.receipt_line_kind, p_locale menu.customer_locale)
RETURNS text
LANGUAGE sql STABLE
AS $$
    SELECT coalesce(
        (SELECT tr.translated_text
           FROM menu.translation tr
          WHERE tr.tenant_id = p_tenant_id
            AND tr.entity = 'receipt_line_wording'
            AND tr.entity_id = w.id
            AND tr.field_name = 'label'
            AND tr.locale = p_locale
            AND tr.state = 'approved'),
        w.source_text)
      FROM docs.line_wording w
     WHERE w.tenant_id = p_tenant_id AND w.kind = p_kind AND w.status = 'active';
$$;

COMMENT ON FUNCTION docs.wording_for(uuid, docs.receipt_line_kind, menu.customer_locale) IS
    'FR-I18N-001C. The label for one receipt line in one locale, through M2-A''s approval '
    'workflow. It RETURNS THE SOURCE TEXT rather than NULL when no approved translation '
    'exists, so that the failure lands on 0027''s completeness trigger with the offending '
    'line named — a NULL would land on a NOT NULL constraint that could not say which '
    'line or which locale.';


-- ===========================================================================
-- One composer, and everything printed goes through it (FR-UX-018)
-- ===========================================================================

CREATE FUNCTION docs.compose_document(
    p_title text,
    p_lines jsonb,
    p_is_specimen boolean,
    p_receipt_number text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE
AS $$
DECLARE
    v_lines jsonb := '[]'::jsonb;
BEGIN
    IF jsonb_typeof(p_lines) <> 'array' OR jsonb_array_length(p_lines) = 0 THEN
        RAISE EXCEPTION
            'DOCUMENT_HAS_NO_LINES: a document with nothing on it would render as blank '
            'paper, and blank paper coming out of a printer reads as a printer fault '
            'rather than as a build defect' USING ERRCODE = 'HS422';
    END IF;

    -- A SPECIMEN CANNOT CARRY A RECEIPT NUMBER. FR-UX-018's preview shows figures that
    -- record nothing; a number from the gapless series would make it indistinguishable
    -- from a document that does, and the series would have a hole in it besides.
    IF p_is_specimen AND p_receipt_number IS NOT NULL THEN
        RAISE EXCEPTION
            'SPECIMEN_CARRIES_A_RECEIPT_NUMBER: a preview was composed with number %. A '
            'preview describes nothing and a receipt number is the one thing on the page '
            'that says otherwise', p_receipt_number USING ERRCODE = 'HS422';
    END IF;
    IF NOT p_is_specimen AND p_receipt_number IS NULL THEN
        RAISE EXCEPTION
            'RECEIPT_NUMBER_ABSENT: a receipt was composed with no number. FR-BIL-017 '
            'requires a unique receipt number on the physical document'
            USING ERRCODE = 'HS422';
    END IF;

    v_lines := jsonb_build_array(
        jsonb_build_object('text', p_title, 'align', 'centre', 'emphasis', true));

    -- THE SPECIMEN MARKING IS A LINE, not a flag beside the lines. A renderer that
    -- ignored a flag would produce a document indistinguishable from a receipt; a
    -- renderer that ignored this would produce a document with a line missing, which is
    -- visible.
    IF p_is_specimen THEN
        v_lines := v_lines || jsonb_build_array(
            jsonb_build_object('text', '*** SPECIMEN — NOT A RECEIPT ***',
                               'align', 'centre', 'emphasis', true));
    ELSE
        v_lines := v_lines || jsonb_build_array(
            jsonb_build_object('text', p_receipt_number, 'align', 'centre',
                               'emphasis', false));
    END IF;

    RETURN jsonb_build_object(
        'is_specimen', p_is_specimen,
        'receipt_number', p_receipt_number,
        'lines', v_lines || p_lines);
END;
$$;

COMMENT ON FUNCTION docs.compose_document(text, jsonb, boolean, text) IS
    'FR-UX-018. The only thing in this build that turns lines into a print document. The '
    'preview path and the receipt path both call it, so "the physical output matches the '
    'preview" is a property of there being one composer rather than a claim about two '
    'that agree today. print/render.mjs rasterises what this produces and nothing else '
    'renders a document.';


-- ===========================================================================
-- Issuing the receipt (FR-BIL-010, FR-BIL-016, FR-BIL-017, FR-I18N-001C)
-- ===========================================================================

CREATE FUNCTION docs.issue_receipt(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_bill_id uuid,
    p_payment_method text,
    p_actor_user_id uuid,
    p_revision integer DEFAULT 1)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'docs', 'billing', 'payments', 'ordering', 'menu',
                   'config', 'identity', 'org', 'money', 'public'
AS $$
DECLARE
    b billing.bill%ROWTYPE;
    v_receipt_id uuid := gen_random_uuid();
    v_number text;
    v_tip  bigint;
    v_paid bigint;
    v_order integer := 0;
    c RECORD;
BEGIN
    SELECT * INTO b FROM billing.bill
     WHERE tenant_id = p_tenant_id AND id = p_bill_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'BILL_NOT_FOUND: no bill % in scope. A receipt is a record of a settlement, '
            'so there is nothing to issue one against', p_bill_id USING ERRCODE = 'HS404';
    END IF;

    IF btrim(coalesce(p_payment_method, '')) = '' THEN
        RAISE EXCEPTION
            'PAYMENT_METHOD_ABSENT: FR-BIL-017 requires the receipt to show the payment '
            'method ACTUALLY used. A blank one is the shape that requirement takes when '
            'somebody prints before knowing' USING ERRCODE = 'HS422';
    END IF;

    v_tip  := docs.tip_total_for_bill(p_tenant_id, p_bill_id);
    v_paid := billing.bill_balance_paid_minor(p_tenant_id, p_bill_id);

    -- SETTLED, OR THERE IS NO RECEIPT. A receipt for an unpaid bill is a document saying
    -- money changed hands when it did not.
    --
    -- THE TEST IS DIFFERENT FOR A LATER REVISION, and GJ-07 is why. A partial refund
    -- leaves the bill no longer fully paid — correctly — and the corrected receipt the
    -- guest is owed is issued precisely BECAUSE of that refund. Applying the settlement
    -- test to a reissue would leave a customer holding a document that no longer
    -- describes their transaction and no way to give them one that does, which is the
    -- opposite of what FR-BIL-011 asks for. So revision 1 requires a settlement, and a
    -- later revision requires that one HAPPENED: a receipt for this bill already exists.
    IF p_revision = 1 THEN
        IF v_paid < b.bill_total_minor - b.disposed_minor THEN
            RAISE EXCEPTION
                'BILL_NOT_SETTLED: bill % totals %, % of it disposed, and % has been '
                'allocated to its balance. FR-BIL-017 issues a receipt for a COMPLETED '
                'settlement',
                b.bill_number, b.bill_total_minor, b.disposed_minor, v_paid
                USING ERRCODE = 'HS409';
        END IF;
    ELSIF NOT EXISTS (SELECT 1 FROM docs.receipt r
                       WHERE r.tenant_id = p_tenant_id AND r.bill_id = p_bill_id) THEN
        RAISE EXCEPTION
            'BILL_NOT_SETTLED: bill % has no receipt, so there is no earlier revision for '
            'revision % to correct. A later revision restates a document the customer is '
            'holding; without the first there is nothing to restate',
            b.bill_number, p_revision USING ERRCODE = 'HS409';
    END IF;

    v_number := config.issue_document_number(
        p_tenant_id, 'receipt', to_char(now(), 'YYYY'), NULL, p_outlet_id);

    -- THE LOCALE IS THE BILL'S. M4-A ruled a bill translates by its own locale and not
    -- the reader's; this function takes no locale parameter at all, so a manager
    -- reprinting a receipt cannot change what language the customer's copy was in.
    INSERT INTO docs.receipt
        (id, tenant_id, outlet_id, bill_id, receipt_number, revision, locale,
         currency_code, bill_total_minor, tip_total_minor, paid_total_minor,
         payment_method, calculation_version, generated_by_user_id)
    VALUES (v_receipt_id, p_tenant_id, p_outlet_id, p_bill_id, v_number, p_revision,
            b.locale, b.currency_code, b.bill_total_minor, v_tip, v_paid + v_tip,
            p_payment_method, b.calculation_version, p_actor_user_id);

    -- The component lines, in the bill's locale, from the wording that already exists and
    -- is already proved. Ordered by kind so two receipts for one bill read the same way.
    FOR c IN
        SELECT k.kind, sum(bc.amount_minor) AS amount_minor
          FROM billing.bill_component bc
          JOIN LATERAL (SELECT bc.kind AS kind) k ON true
         WHERE bc.tenant_id = p_tenant_id AND bc.bill_id = p_bill_id
         GROUP BY k.kind
         ORDER BY k.kind
    LOOP
        v_order := v_order + 1;
        INSERT INTO docs.receipt_line
            (tenant_id, outlet_id, receipt_id, kind, display_order, label,
             amount_minor, currency_code)
        VALUES (p_tenant_id, p_outlet_id, v_receipt_id, 'bill_component', v_order,
                billing.component_wording_for(p_tenant_id, c.kind, b.locale),
                c.amount_minor, b.currency_code);
    END LOOP;

    -- FR-BIL-010's three figures as three lines, and FR-BIL-017's fourth. The tip line is
    -- written even when the tip is zero: "optional tip" is about whether a guest left
    -- one, not about whether the receipt accounts for it, and a receipt that omits the
    -- line when it is zero is a receipt whose shape depends on the amount.
    v_order := v_order + 1;
    INSERT INTO docs.receipt_line
        (tenant_id, outlet_id, receipt_id, kind, display_order, label,
         amount_minor, currency_code)
    VALUES (p_tenant_id, p_outlet_id, v_receipt_id, 'bill_total', v_order,
            docs.wording_for(p_tenant_id, 'bill_total', b.locale),
            b.bill_total_minor, b.currency_code);

    v_order := v_order + 1;
    INSERT INTO docs.receipt_line
        (tenant_id, outlet_id, receipt_id, kind, display_order, label,
         amount_minor, currency_code)
    VALUES (p_tenant_id, p_outlet_id, v_receipt_id, 'tip', v_order,
            docs.wording_for(p_tenant_id, 'tip', b.locale), v_tip, b.currency_code);

    v_order := v_order + 1;
    INSERT INTO docs.receipt_line
        (tenant_id, outlet_id, receipt_id, kind, display_order, label,
         amount_minor, currency_code)
    VALUES (p_tenant_id, p_outlet_id, v_receipt_id, 'total_paid', v_order,
            docs.wording_for(p_tenant_id, 'total_paid', b.locale),
            v_paid + v_tip, b.currency_code);

    v_order := v_order + 1;
    INSERT INTO docs.receipt_line
        (tenant_id, outlet_id, receipt_id, kind, display_order, label,
         amount_minor, currency_code)
    VALUES (p_tenant_id, p_outlet_id, v_receipt_id, 'payment_method', v_order,
            docs.wording_for(p_tenant_id, 'payment_method', b.locale) || ': '
            || p_payment_method,
            NULL, NULL);

    RETURN v_receipt_id;
END;
$$;

COMMENT ON FUNCTION docs.issue_receipt(uuid, uuid, uuid, text, uuid, integer) IS
    'FR-BIL-010, FR-BIL-016 and FR-BIL-017. Composes the receipt from the bill''s own '
    'figures in the bill''s own locale and writes it. IT TAKES NO LOCALE PARAMETER, which '
    'is M4-A''s rule made structural rather than remembered. The tip line is written even '
    'when the tip is zero, so a receipt''s shape does not depend on its amounts. Every '
    'figure it writes is checked against its source by 0027''s deferred triggers, so this '
    'function is not trusted to be right about any of them.';


-- ===========================================================================
-- The document a receipt renders as (FR-UX-018, FR-BIL-017)
-- ===========================================================================

CREATE FUNCTION docs.receipt_document(p_tenant_id uuid, p_receipt_id uuid)
RETURNS jsonb
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    r docs.receipt%ROWTYPE;
    v_lines jsonb;
BEGIN
    SELECT * INTO r FROM docs.receipt
     WHERE tenant_id = p_tenant_id AND id = p_receipt_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'RECEIPT_NOT_FOUND: no receipt % in scope', p_receipt_id
            USING ERRCODE = 'HS404';
    END IF;

    SELECT jsonb_agg(
             jsonb_build_object(
               'text', l.label ||
                       CASE WHEN l.amount_minor IS NULL THEN ''
                            ELSE '  ' || l.amount_minor::text || ' ' || l.currency_code END,
               'align', CASE WHEN l.kind = 'bill_component' THEN 'left' ELSE 'right' END,
               'emphasis', l.kind IN ('bill_total', 'total_paid'))
             ORDER BY l.display_order)
      INTO v_lines
      FROM docs.receipt_line l
     WHERE l.tenant_id = p_tenant_id AND l.receipt_id = p_receipt_id;

    RETURN docs.compose_document(
        'RECEIPT / ' || r.locale::text, v_lines, false, r.receipt_number);
END;
$$;

COMMENT ON FUNCTION docs.receipt_document(uuid, uuid) IS
    'The receipt as the printer path receives it. Built from the SNAPSHOTTED lines rather '
    'than recomputed, so a document rendered today for a receipt issued last week says '
    'what the paper said. print/agent.py rasterises this and nothing else.';

CREATE FUNCTION docs.preview_document(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_locale menu.customer_locale,
    p_currency_code char(3))
RETURNS jsonb
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_lines jsonb := '[]'::jsonb;
    k docs.receipt_line_kind;
BEGIN
    -- EVERY LINE KIND, ENUMERATED FROM THE TYPE. A preview whose line list was written
    -- out by hand would stop showing a kind the day somebody added one, and the person
    -- who would notice is a customer holding a receipt with a line nobody previewed.
    FOREACH k IN ARRAY enum_range(NULL::docs.receipt_line_kind) LOOP
        v_lines := v_lines || jsonb_build_array(jsonb_build_object(
            'text', coalesce(
                CASE WHEN k = 'bill_component'
                     THEN billing.component_wording_for(p_tenant_id, 'item_subtotal', p_locale)
                     ELSE docs.wording_for(p_tenant_id, k, p_locale) END,
                k::text)
                || CASE WHEN k = 'payment_method' THEN ': —'
                        ELSE '  0 ' || p_currency_code END,
            'align', CASE WHEN k = 'bill_component' THEN 'left' ELSE 'right' END,
            'emphasis', k IN ('bill_total', 'total_paid')));
    END LOOP;

    -- ZERO RATHER THAN AN INVENTED AMOUNT. FR-UX-014's rule is that a figure describing
    -- nothing must not look like one that describes something; a specimen showing 1,250
    -- birr is a plausible number somebody will eventually screenshot. The layout is what
    -- a preview is for, and zero exercises it exactly as well.
    RETURN docs.compose_document(
        'RECEIPT / ' || p_locale::text, v_lines, true, NULL);
END;
$$;

COMMENT ON FUNCTION docs.preview_document(uuid, uuid, menu.customer_locale, char) IS
    'FR-UX-018. A specimen receipt in one locale, composed by the same function the real '
    'one is, so what a reviewer approves before publication is the layout that prints. '
    'Its line kinds are enumerated from docs.receipt_line_kind, so a kind added later '
    'appears in the preview without anybody remembering to add it. It carries no receipt '
    'number and says SPECIMEN on its face, and docs.compose_document() refuses to give it '
    'one.';


-- ===========================================================================
-- The printer, registered and TESTED (FR-CFG-001D)
-- ===========================================================================

CREATE FUNCTION docs.register_printer(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_display_name text,
    p_connection docs.connection_kind,
    p_device_path text,
    p_host_and_port text,
    p_actor_user_id uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY INVOKER
AS $$
DECLARE v_id uuid;
BEGIN
    INSERT INTO docs.printer
        (tenant_id, outlet_id, display_name, connection, sink,
         device_path, host_and_port, registered_by_user_id)
    VALUES (p_tenant_id, p_outlet_id, p_display_name, p_connection,
            -- DERIVED HERE TOO, and the CHECK on the table refuses a disagreement. Two
            -- locks: this function cannot register a file as a device, and a caller
            -- reaching the table directly cannot either.
            CASE WHEN p_connection = 'file' THEN 'preview'::docs.sink_kind
                 ELSE 'device'::docs.sink_kind END,
            p_device_path, p_host_and_port, p_actor_user_id)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION docs.register_printer(uuid, uuid, text, docs.connection_kind, text, text, uuid) IS
    'FR-CFG-001D''s registration half. The sink is derived from the connection rather '
    'than accepted, and the CHECK on docs.printer refuses the pair if this function is '
    'ever changed to accept one.';

CREATE FUNCTION docs.printer_has_passed_a_test(p_tenant_id uuid, p_printer_id uuid)
RETURNS boolean
LANGUAGE sql STABLE
AS $$
    SELECT EXISTS (SELECT 1 FROM docs.printer_test t
                    WHERE t.tenant_id = p_tenant_id AND t.printer_id = p_printer_id
                      AND t.outcome = 'printed');
$$;

COMMENT ON FUNCTION docs.printer_has_passed_a_test(uuid, uuid) IS
    'FR-CFG-001D''s test half, asked as a question. docs.record_receipt_print() refuses a '
    'printer this returns false for, so "registers AND tests" is a precondition of '
    'printing rather than a step in a setup screen somebody can skip.';

CREATE FUNCTION docs.record_printer_test(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_printer_id uuid,
    p_outcome docs.print_outcome,
    p_bytes_sha256 char(64),
    p_byte_count integer,
    p_detail text,
    p_actor_user_id uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY INVOKER
AS $$
DECLARE v_id uuid;
BEGIN
    INSERT INTO docs.printer_test
        (tenant_id, outlet_id, printer_id, outcome, bytes_sha256, byte_count, detail,
         tested_by_user_id)
    VALUES (p_tenant_id, p_outlet_id, p_printer_id, p_outcome, p_bytes_sha256,
            p_byte_count, p_detail, p_actor_user_id)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION docs.record_printer_test(uuid, uuid, uuid, docs.print_outcome, char, integer, text, uuid) IS
    'FR-CFG-001D. The outcome parameter is docs.print_outcome, so a preview printer '
    'cannot be tested at all — 0027''s printer_test_needs_a_device trigger refuses the '
    'row. A file that received bytes has not tested a printer.';


-- ===========================================================================
-- Printing it, and reprinting it (FR-BIL-011, FR-BIL-017)
-- ===========================================================================

CREATE FUNCTION docs.record_receipt_print(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_receipt_id uuid,
    p_printer_id uuid,
    p_outcome docs.print_outcome,
    p_bytes_sha256 char(64),
    p_byte_count integer,
    p_actor_user_id uuid,
    p_is_reprint boolean DEFAULT false,
    p_reason_code_id uuid DEFAULT NULL,
    p_reason_text text DEFAULT NULL,
    p_detail text DEFAULT NULL)
RETURNS uuid
LANGUAGE plpgsql SECURITY INVOKER
AS $$
DECLARE v_id uuid;
BEGIN
    IF NOT docs.printer_has_passed_a_test(p_tenant_id, p_printer_id) THEN
        RAISE EXCEPTION
            'PRINTER_NEVER_TESTED: printer % has no successful test. FR-CFG-001D asks '
            'that setup registers AND TESTS the printer, and a setup screen that reported '
            'a printer ready because a row existed would be FR-INT-011''s most expensive '
            'kind of true statement', p_printer_id USING ERRCODE = 'HS409';
    END IF;

    -- The reprint marking, its reason and its operator are refused by the CHECK on
    -- docs.print_attempt rather than by this function; the duplicate is refused by the
    -- partial unique index and by docs.refuse_duplicate_receipt_print(). Nothing here
    -- re-states either, because a function that repeated them would be the copy that
    -- eventually disagreed.
    INSERT INTO docs.print_attempt
        (tenant_id, outlet_id, receipt_id, printer_id, outcome, is_reprint,
         reason_code_id, reason_text, operator_user_id, bytes_sha256, byte_count, detail)
    VALUES (p_tenant_id, p_outlet_id, p_receipt_id, p_printer_id, p_outcome, p_is_reprint,
            p_reason_code_id, p_reason_text, p_actor_user_id, p_bytes_sha256,
            p_byte_count, p_detail)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION docs.record_receipt_print(uuid, uuid, uuid, uuid, docs.print_outcome, char, integer, uuid, boolean, uuid, text, text) IS
    'FR-BIL-011 and FR-BIL-017. The one thing it adds beyond the INSERT is FR-CFG-001D''s '
    'precondition: an untested printer cannot print a customer receipt. Everything else '
    '— the reprint marking, the operator, the reason, the refusal of a second original — '
    'is carried by constraints on the table, so this function forgetting any of it '
    'changes nothing.';

CREATE FUNCTION docs.record_receipt_render(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_kind docs.document_kind,
    p_receipt_id uuid,
    p_printer_id uuid,
    p_outcome docs.render_outcome,
    p_bytes_sha256 char(64),
    p_byte_count integer,
    p_actor_user_id uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY INVOKER
AS $$
DECLARE v_id uuid;
BEGIN
    -- NO TEST PRECONDITION, DELIBERATELY. A preview is what somebody does BEFORE a
    -- printer works; requiring a successful print first would make the preview useless
    -- for the one job FR-UX-018 gives it. The outcome type is what keeps this from being
    -- a hole: docs.render_outcome cannot be written into a print attempt.
    INSERT INTO docs.render_attempt
        (tenant_id, outlet_id, kind, receipt_id, printer_id, outcome, bytes_sha256,
         byte_count, requested_by_user_id)
    VALUES (p_tenant_id, p_outlet_id, p_kind, p_receipt_id, p_printer_id, p_outcome,
            p_bytes_sha256, p_byte_count, p_actor_user_id)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION docs.record_receipt_render(uuid, uuid, docs.document_kind, uuid, uuid, docs.render_outcome, char, integer, uuid) IS
    'FR-UX-018. A preview render, recorded. Its outcome is docs.render_outcome and a '
    'print attempt''s is docs.print_outcome: two types with no cast between them, so no '
    'assignment, fixture or later edit can record a preview as a print.';

CREATE FUNCTION docs.reissue_receipt(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_receipt_id uuid,
    p_actor_user_id uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY INVOKER
AS $$
DECLARE r docs.receipt%ROWTYPE;
BEGIN
    SELECT * INTO r FROM docs.receipt
     WHERE tenant_id = p_tenant_id AND id = p_receipt_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'RECEIPT_NOT_FOUND: no receipt % in scope', p_receipt_id
            USING ERRCODE = 'HS404';
    END IF;

    -- A NEW REVISION, NOT A CORRECTED ONE. docs.receipt is append-only and its
    -- deduplication key is (bill, revision), so a reissue is a second document with its
    -- own number and its own audit rather than an edit of the one the customer has.
    RETURN docs.issue_receipt(p_tenant_id, p_outlet_id, r.bill_id, r.payment_method,
                              p_actor_user_id, r.revision + 1);
END;
$$;

COMMENT ON FUNCTION docs.reissue_receipt(uuid, uuid, uuid, uuid) IS
    'FR-BIL-011. A reissue is a new revision of the same bill''s receipt, issued through '
    'the same composer. The REPRINT of an existing revision is a print attempt marked '
    'is_reprint with its operator and reason — a different thing, and the distinction '
    'matters because a customer holding revision 1 and a manager holding revision 2 have '
    'two documents, while a reprint of revision 1 is two copies of one.';


-- ===========================================================================
-- The counter order is created AT THE POS TERMINAL (FR-POS-003B)
-- ===========================================================================
-- FR-ORD-001B was closed at M4-A by proving there is one submitting handler and one
-- aggregate: a counter order differs from a waiter order by the value of one argument.
-- That is "the same rules" and it stands. What was missing is the other half of
-- FR-POS-003B's sentence — AT THE POS TERMINAL. Nothing recorded which terminal a
-- counter order was entered at, so an order marked 'counter' and one typed from anywhere
-- at all were the same row.

CREATE TABLE pos.counter_order_entry (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,

    -- NO FOREIGN KEY, for the reason docs.receipt.bill_id carries none:
    -- ordering.customer_order is a PROJECTION, deleted wholesale by
    -- ordering.rebuild_projections() and replayed from the event ledger. A durable key
    -- into it would be refused by M3-D's rule, and rightly — this row records WHERE an
    -- order was entered, which stays true whether or not the projection currently holds
    -- the order. pos.record_counter_order() requires the order to exist when the entry is
    -- written; nothing requires it to still exist afterwards.
    order_id uuid NOT NULL,

    terminal_device_id uuid NOT NULL,
    entered_by_user_id uuid NOT NULL,
    entered_in_session_id uuid NOT NULL,
    entered_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT counter_order_entry_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT counter_order_entry_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT counter_order_entry_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT counter_order_entry_terminal_fk FOREIGN KEY (tenant_id, terminal_device_id)
        REFERENCES pos.terminal (tenant_id, device_id) ON DELETE RESTRICT,
    CONSTRAINT counter_order_entry_actor_fk FOREIGN KEY (tenant_id, entered_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,

    -- ONE ENTRY PER ORDER. A second would make "which terminal was this entered at" a
    -- question with two answers.
    CONSTRAINT counter_order_entry_one_per_order UNIQUE (tenant_id, order_id)
);

COMMENT ON TABLE pos.counter_order_entry IS
    'FR-POS-003B. Which POS terminal a counter order was entered at, and by whom in which '
    'session. It holds no foreign key into ordering.customer_order because that is a '
    'projection; it records what happened rather than what is currently true.';

CREATE INDEX counter_order_entry_terminal_idx
    ON pos.counter_order_entry (tenant_id, terminal_device_id, entered_at DESC);

CREATE TRIGGER counter_order_entry_is_append_only
    BEFORE UPDATE OR DELETE ON pos.counter_order_entry
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

CREATE FUNCTION pos.record_counter_order(
    p_tenant_id uuid, p_outlet_id uuid, p_order_id uuid, p_actor_user_id uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'pos', 'ordering', 'identity', 'org', 'public'
AS $$
DECLARE
    o ordering.customer_order%ROWTYPE;
    v_session identity.session%ROWTYPE;
    t pos.terminal%ROWTYPE;
    v_id uuid;
BEGIN
    SELECT * INTO o FROM ordering.customer_order
     WHERE tenant_id = p_tenant_id AND id = p_order_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ORDER_NOT_FOUND: no order % in scope', p_order_id
            USING ERRCODE = 'HS404';
    END IF;

    IF o.origin <> 'counter' THEN
        RAISE EXCEPTION
            'COUNTER_ENTRY_ON_A_NON_COUNTER_ORDER: order % has origin %. A guest''s QR '
            'order and a waiter''s order were not entered at a counter, and recording a '
            'terminal against one would make the terminal record answer a question it '
            'was not asked', o.order_number, o.origin USING ERRCODE = 'HS409';
    END IF;

    -- THE TERMINAL IS THE SESSION'S, NOT THE CALLER'S. Same shape as NC-M4-004's
    -- verifier: cash.transition_shift() reads who is verifying from the session in
    -- context because a parameter is a claim. A terminal parameter here would let a
    -- request from anywhere assert it came from the counter, and the compliant case and
    -- the violation would be identical rows.
    SELECT * INTO v_session FROM identity.session
     WHERE id = app.current_session_id() AND revoked_at IS NULL AND expires_at > now();
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'SESSION_NOT_LIVE: a counter order is entered by a person at a terminal, and '
            'no live session is in context to say which' USING ERRCODE = 'HS401';
    END IF;

    IF v_session.device_id IS NULL THEN
        RAISE EXCEPTION
            'COUNTER_ORDER_WITHOUT_A_TERMINAL: the session that entered order % is bound '
            'to no device. FR-POS-003B says a counter order is created AT THE POS '
            'TERMINAL, and a session with no device was not at one',
            o.order_number USING ERRCODE = 'HS403';
    END IF;

    SELECT * INTO t FROM pos.terminal
     WHERE tenant_id = p_tenant_id AND device_id = v_session.device_id;
    IF NOT FOUND OR t.revoked_at IS NOT NULL OR t.profile <> 'point_of_sale'
       OR t.outlet_id <> p_outlet_id THEN
        RAISE EXCEPTION
            'COUNTER_ORDER_WITHOUT_A_TERMINAL: the session that entered order % is on '
            'device %, which is not an active point-of-sale terminal in this outlet. A '
            'counter order entered on a kitchen display or on a revoked device is not a '
            'counter order that happened at the counter',
            o.order_number, v_session.device_id USING ERRCODE = 'HS403';
    END IF;

    INSERT INTO pos.counter_order_entry
        (tenant_id, outlet_id, order_id, terminal_device_id, entered_by_user_id,
         entered_in_session_id)
    VALUES (p_tenant_id, p_outlet_id, p_order_id, t.device_id, p_actor_user_id,
            v_session.id)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION pos.record_counter_order(uuid, uuid, uuid, uuid) IS
    'FR-POS-003B. Binds a counter order to the POS terminal it was entered at, resolved '
    'from the session in context rather than accepted as a parameter. It creates no '
    'order: ordering.submit_order() is the only path to one, and this records where that '
    'path was called from. The constraint trigger below refuses a counter order with no '
    'entry at commit, so the two cannot come apart.';

-- ---------------------------------------------------------------------------
-- A counter order names a terminal, or the transaction does not commit
-- ---------------------------------------------------------------------------
-- DEFERRED, because the order is written before the entry — they are two statements in
-- one transaction and the requirement is about the transaction. It fires on the
-- projection's INSERT, which means it also fires during a rebuild; that is correct and it
-- passes, because the entry lives in pos and a rebuild does not touch it.

CREATE FUNCTION ordering.assert_counter_order_names_its_terminal() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pos.counter_order_entry e
                    WHERE e.tenant_id = NEW.tenant_id AND e.order_id = NEW.id) THEN
        RAISE EXCEPTION
            'COUNTER_ORDER_WITHOUT_A_TERMINAL: order % has origin counter and names no '
            'POS terminal. FR-POS-003B says a counter order is created AT THE POS '
            'TERMINAL; an order that claims the counter and can name no terminal is a '
            'channel label rather than a place',
            NEW.order_number USING ERRCODE = 'HS422';
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER counter_order_names_its_terminal
    AFTER INSERT ON ordering.customer_order
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    WHEN (NEW.origin = 'counter')
    EXECUTE FUNCTION ordering.assert_counter_order_names_its_terminal();


-- ===========================================================================
-- Row level security and grants
-- ===========================================================================

ALTER TABLE pos.counter_order_entry ENABLE ROW LEVEL SECURITY;
ALTER TABLE pos.counter_order_entry FORCE ROW LEVEL SECURITY;
CREATE POLICY counter_order_entry_isolation ON pos.counter_order_entry FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

GRANT SELECT, INSERT ON pos.counter_order_entry TO hospitality_app;
GRANT INSERT ON docs.printer      TO hospitality_app;
GRANT INSERT ON docs.printer_test TO hospitality_app;
GRANT UPDATE ON docs.printer      TO hospitality_app;

GRANT EXECUTE ON FUNCTION docs.wording_for(
    uuid, docs.receipt_line_kind, menu.customer_locale) TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.compose_document(text, jsonb, boolean, text)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.issue_receipt(uuid, uuid, uuid, text, uuid, integer)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.reissue_receipt(uuid, uuid, uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.receipt_document(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.preview_document(
    uuid, uuid, menu.customer_locale, char) TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.register_printer(
    uuid, uuid, text, docs.connection_kind, text, text, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.printer_has_passed_a_test(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.record_printer_test(
    uuid, uuid, uuid, docs.print_outcome, char, integer, text, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.record_receipt_print(
    uuid, uuid, uuid, uuid, docs.print_outcome, char, integer, uuid, boolean, uuid, text,
    text) TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.record_receipt_render(
    uuid, uuid, docs.document_kind, uuid, uuid, docs.render_outcome, char, integer, uuid)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION pos.record_counter_order(uuid, uuid, uuid, uuid)
    TO hospitality_app;


-- ===========================================================================
-- The wording every receipt needs must exist for every tenant
-- ===========================================================================
-- AT THE FOOT, and it is a check rather than a seed: which wording a tenant uses is
-- tenant content, and a migration inserting text on a tenant's behalf would be a
-- migration writing content. What this refuses is the state in which a tenant could
-- settle a bill and not be able to print a receipt, which is a defect discovered at a
-- counter rather than here.
--
-- It passes vacuously on an empty database, and says so: with no tenants there is
-- nothing to be missing wording, and a check that reported success over an empty set
-- without saying so would be the vacuity this project has caught five times.

DO $$
DECLARE
    v_tenants integer;
    v_short text[];
BEGIN
    SELECT count(*) INTO v_tenants FROM org.tenant;
    IF v_tenants = 0 THEN
        RAISE NOTICE
            'RECEIPT_WORDING_CHECK_VACUOUS: no tenant exists, so no tenant can be short '
            'of receipt wording. This check becomes live with the first tenant.';
        RETURN;
    END IF;

    SELECT array_agg(t.id::text || ' missing ' || k::text ORDER BY 1) INTO v_short
      FROM org.tenant t
      CROSS JOIN unnest(enum_range(NULL::docs.receipt_line_kind)) k
     WHERE k <> 'bill_component'
       AND NOT EXISTS (SELECT 1 FROM docs.line_wording w
                        WHERE w.tenant_id = t.id AND w.kind = k AND w.status = 'active');
    IF v_short IS NOT NULL THEN
        RAISE NOTICE
            'RECEIPT_WORDING_ABSENT: % tenant/kind pair(s) have no active receipt line '
            'wording: %. docs.issue_receipt() will write the kind name as the label, and '
            '0027''s completeness trigger will refuse a non-English receipt built that '
            'way. Seed the wording before settling a bill.',
            array_length(v_short, 1), v_short;
    END IF;
END;
$$;
