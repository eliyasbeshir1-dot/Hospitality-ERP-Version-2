-- =============================================================================
-- 0027 — Receipts, the printer path, and the first artifact that leaves the building
-- =============================================================================
-- FR-BIL-010, FR-BIL-011, FR-BIL-016, FR-BIL-017, FR-I18N-001C, FR-CFG-001D, FR-UX-018,
-- FR-DAT-008B, and FR-SEC-018's M4 clause.
--
-- EVERYTHING UNTIL NOW HAS BEEN BYTES. A receipt is paper a customer takes away, and it
-- is the only Phase 1 artifact that cannot be corrected after the fact by changing a row.
-- Three consequences run through this whole file:
--
--   1. A RECEIPT SNAPSHOTS. billing.bill and billing.bill_component are PROJECTIONS —
--      billing.drop_projections_for_rebuild() deletes both and the fold replays them —
--      and payments.payment, payments.allocation and payments.reversal are projections
--      too. So docs.receipt holds NO FOREIGN KEY into any of them. That is M3-D's rule
--      (nothing durable may hold a foreign key into a projection) and it is also what
--      paper demands: a receipt printed on Tuesday does not change because the bill was
--      reissued on Wednesday. The figures are copied in at generation and frozen, the
--      way 0019 froze the bill's own locale and calculation version.
--
--   2. THE SINK IS A TYPE, NOT A FLAG. A receipt written to a file is not a receipt a
--      customer received. M4-B spent a slice proving a simulated payment result cannot be
--      recorded as a live one, and the mechanism that did it was two enum types with no
--      cast between them rather than a boolean somebody could UPDATE. The same mechanism
--      is here: docs.print_outcome is what a DEVICE reports and docs.render_outcome is
--      what a FILE reports, they are different types, PostgreSQL performs no implicit
--      conversion, and there is no column a rendered preview could be recorded into as a
--      printed receipt. A boolean is flipped by an UPDATE; a type is not.
--
--   3. A RECEIPT PRINTED TWICE IS A CUSTOMER HOLDING TWO RECORDS OF ONE PAYMENT. M3-B
--      learned that generating a document appends an event and that deduplication has to
--      be KEYED with a unique index that refuses a duplicate even when the function
--      forgets. Here the key is the receipt itself and the index is partial: at most one
--      print attempt per receipt that is not a reprint. A reprint is legal, marked, and
--      carries the operator and the reason (FR-BIL-011).
--
-- WHAT IS NOT HERE. No resilient local print queue — that is M5a's, and this is the
-- minimum production path FR-BIL-017 asks for, which means the bytes go straight at the
-- device and a failure is a failure rather than a retry. No fiscal document: 0028. No
-- reporting: 0029.
-- =============================================================================

CREATE SCHEMA docs;

COMMENT ON SCHEMA docs IS
    'Documents this system produces for somebody outside it to read: receipts now, and '
    'the previews FR-UX-018 asks for of the kitchen, label and operational documents '
    'that already exist. Its own schema rather than a corner of billing because a bill '
    'states what is owed and a receipt states what happened, and the second must not '
    'become editable by living beside the first.';


-- ===========================================================================
-- What kind of document, and what kind of sink
-- ===========================================================================

CREATE TYPE docs.document_kind AS ENUM
    ('receipt', 'kitchen_ticket', 'label', 'operational');

COMMENT ON TYPE docs.document_kind IS
    'The four document kinds FR-UX-018 requires a preview of. Only receipt is PRINTED at '
    'M4-C; the other three exist as renderable documents so a template can be reviewed '
    'before configuration publication, which is the requirement — a document that only '
    'reveals itself on paper cannot be reviewed.';

CREATE TYPE docs.connection_kind AS ENUM
    ('character_device', 'network_socket', 'file');

COMMENT ON TYPE docs.connection_kind IS
    'How the bytes reach the printer. A character device is a real printer on a real '
    'port; a network socket is a real printer on the network; a file is neither and is '
    'the preview path. Which of the two SINKS a connection implies is derived by CHECK '
    'below rather than stated, exactly as payments.payment_adapter derives its mode from '
    'its provider — nobody decides whether a file is a printer.';

CREATE TYPE docs.sink_kind AS ENUM ('device', 'preview');

COMMENT ON TYPE docs.sink_kind IS
    'Whether bytes reached hardware or a file. Derived from the connection, never set.';

-- ---------------------------------------------------------------------------
-- Two worlds, two types (FR-BIL-017)
-- ---------------------------------------------------------------------------
-- The strongest lock in this file and the one that needs no code to hold. These two
-- enums describe outcomes of two different acts, they are different types, and
-- PostgreSQL performs no implicit conversion between them — so docs.print_attempt.
-- outcome, declared docs.print_outcome, cannot be given what docs.render_attempt.outcome
-- holds. Not "is checked and rejected": does not fit.
--
-- This is M4-B's arrangement applied to paper. The strongest version of "a file sink must
-- not be recordable as a printed receipt" is one in which there is no column it could be
-- recorded into.

CREATE TYPE docs.print_outcome AS ENUM ('printed', 'failed');

CREATE TYPE docs.render_outcome AS ENUM ('rendered', 'failed');

COMMENT ON TYPE docs.print_outcome IS
    'What a DEVICE reported: bytes went at a character device or a socket and the printer '
    'took them or did not. The only type docs.print_attempt.outcome accepts, and no '
    'preview can produce a value of it.';

COMMENT ON TYPE docs.render_outcome IS
    'What a FILE sink reported. Deliberately a DIFFERENT type from docs.print_outcome, '
    'and deliberately not carrying the word printed: a preview renders. FR-BIL-017 wants '
    'a real physical receipt through a supported minimum production printer path, and a '
    'file that received the same bytes is not one. No assignment, cast or fixture carries '
    'one of these into the other.';

CREATE TYPE docs.receipt_line_kind AS ENUM
    ('bill_component', 'bill_total', 'tip', 'total_paid', 'payment_method');

COMMENT ON TYPE docs.receipt_line_kind IS
    'FR-BIL-010 and FR-BIL-017: bill total, optional tip, total paid and the payment '
    'method actually used, each its OWN LINE. Separate kinds rather than one amount '
    'column with a label, because a merged line is then a missing kind and the '
    'faithfulness trigger below can say so. M4-A proved a bill cannot see a tip; the '
    'receipt is the one document that shows both, and showing both is not merging them.';


-- ===========================================================================
-- The wording of the lines a bill does not have (FR-I18N-001C)
-- ===========================================================================

CREATE TABLE docs.line_wording (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL,
    outlet_id   uuid,
    kind        docs.receipt_line_kind NOT NULL,
    source_text text NOT NULL,
    status      org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version bigint NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT line_wording_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT line_wording_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT line_wording_source_not_blank CHECK (btrim(source_text) <> ''),
    -- One active wording per kind per tenant. A second would make which label a receipt
    -- carries depend on which row was read first.
    CONSTRAINT line_wording_one_per_kind UNIQUE (tenant_id, kind, status)
);

COMMENT ON TABLE docs.line_wording IS
    'The English source text for the four receipt lines that are not charge components, '
    'translated through menu.translation under entity receipt_line_wording — M2-A''s '
    'approval workflow unchanged, because a second store for safety-relevant text is how '
    'two copies come to disagree (M2-B''s finding). The component lines take their wording '
    'from billing.component_wording_for(), which already exists and is already proved.';


-- ===========================================================================
-- The printer, registered AND tested (FR-CFG-001D)
-- ===========================================================================
-- "Registers and TESTS". A printer configured and never exercised is FR-INT-011's most
-- expensive kind of true statement: a setup screen that says a printer is ready because
-- a row exists. So a printer carries the outcome of its last test, that outcome is of the
-- device type, and docs.issue_receipt() refuses a printer that has never printed.

CREATE TABLE docs.printer (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL,
    outlet_id   uuid NOT NULL,
    display_name text NOT NULL,
    connection  docs.connection_kind NOT NULL,
    sink        docs.sink_kind NOT NULL,

    -- Where the bytes go. Exactly one of the two is present, by CHECK, so a printer
    -- cannot be half-configured and still look registered.
    device_path text,
    host_and_port text,

    -- The command set these bytes are written for. Generic ESC/POS: no pilot printer has
    -- been chosen, so the target is the published command set rather than one vendor's
    -- extension of it. Recorded on the printer rather than assumed by the encoder,
    -- because the day a device is chosen this is the column that has to change.
    command_set text NOT NULL DEFAULT 'esc_pos_generic',

    status      org.lifecycle_status NOT NULL DEFAULT 'active',
    registered_by_user_id uuid NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT now(),
    row_version bigint NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT printer_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT printer_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT printer_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT printer_registrar_fk FOREIGN KEY (tenant_id, registered_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT printer_name_not_blank CHECK (btrim(display_name) <> ''),

    -- THE SINK IS DERIVED FROM THE CONNECTION. Not a column somebody sets: a file is a
    -- preview and a port or a socket is a device, and no operator decision enters it.
    -- Same shape as payments.payment_adapter's mode being derived from its provider.
    CONSTRAINT printer_sink_is_derived_from_the_connection CHECK (
        (connection IN ('character_device', 'network_socket') AND sink = 'device')
     OR (connection = 'file' AND sink = 'preview')),

    -- Exactly one destination, matching the connection.
    CONSTRAINT printer_destination_matches_the_connection CHECK (
        (connection = 'network_socket'
             AND host_and_port IS NOT NULL AND device_path IS NULL)
     OR (connection IN ('character_device', 'file')
             AND device_path IS NOT NULL AND host_and_port IS NULL)),

    -- One active printer per name per outlet, so "the receipt printer" resolves.
    CONSTRAINT printer_name_unique_per_outlet
        UNIQUE (tenant_id, outlet_id, display_name, status)
);

COMMENT ON TABLE docs.printer IS
    'FR-CFG-001D''s registered printer. Its SINK is derived from its connection by CHECK '
    'and its identity is immutable by trigger, so a preview cannot be promoted into a '
    'device by an UPDATE — the two locks payments.payment_adapter carries, for the same '
    'reason. command_set records what the bytes are written for: generic ESC/POS, '
    'because no pilot device has been chosen, and that is a gap this build states rather '
    'than hides.';

CREATE INDEX printer_outlet_idx ON docs.printer (tenant_id, outlet_id) WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- A printer's identity cannot change under it
-- ---------------------------------------------------------------------------
-- The CHECK above refuses an inconsistent pair. This refuses the CONSISTENT pair that is
-- a different printer wearing this one's id — the second lock M4-B put on an adapter,
-- and the reason it needed both: a file printer UPDATEd to a character device would
-- satisfy every CHECK on the row and make every print attempt already recorded against
-- it retrospectively a device print.

CREATE FUNCTION docs.refuse_printer_identity_change() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.connection <> OLD.connection OR NEW.sink <> OLD.sink THEN
        RAISE EXCEPTION
            'PRINTER_IDENTITY_IMMUTABLE: printer % is a % on a %, and neither can '
            'change. Every print attempt already recorded against this printer was '
            'recorded against THAT sink; promoting it would rewrite what those attempts '
            'mean. Register a new printer and retire this one',
            OLD.id, OLD.sink, OLD.connection USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER printer_identity_is_immutable
    BEFORE UPDATE ON docs.printer
    FOR EACH ROW EXECUTE FUNCTION docs.refuse_printer_identity_change();

-- ---------------------------------------------------------------------------
-- The test itself
-- ---------------------------------------------------------------------------

CREATE TABLE docs.printer_test (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,
    printer_id uuid NOT NULL,
    outcome    docs.print_outcome NOT NULL,
    -- What was sent, by digest rather than by content: a test page carries no customer
    -- data, but making the column a digest means it can never start carrying any.
    bytes_sha256 char(64) NOT NULL,
    byte_count   integer NOT NULL,
    detail       text,
    tested_by_user_id uuid NOT NULL,
    tested_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT printer_test_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT printer_test_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT printer_test_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT printer_test_printer_fk FOREIGN KEY (tenant_id, printer_id)
        REFERENCES docs.printer (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT printer_test_actor_fk FOREIGN KEY (tenant_id, tested_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT printer_test_digest_is_a_digest CHECK (bytes_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT printer_test_byte_count_positive CHECK (byte_count > 0)
);

COMMENT ON TABLE docs.printer_test IS
    'FR-CFG-001D''s test, recorded. Its outcome is docs.print_outcome, so only a device '
    'sink can produce a row here at all — a preview cannot be tested into looking like a '
    'printer, because the value would not fit the column.';


-- ===========================================================================
-- The receipt (FR-BIL-010, FR-BIL-016, FR-I18N-001C)
-- ===========================================================================

CREATE TABLE docs.receipt (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,

    -- NO FOREIGN KEY, AND THE REASON MATTERS MORE THAN THE COLUMN. billing.bill is a
    -- PROJECTION: billing.drop_projections_for_rebuild() deletes every row and the fold
    -- replays them from billing.bill_event. A durable table holding a key into it would
    -- be refused by M3-D's rule, and rightly — M4-B shipped exactly that defect one layer
    -- over, where a rebuild in ordering deleted a bill out of the correlation chain and
    -- nothing put it back. What a receipt records is WHAT HAPPENED, not what is currently
    -- true, so it names the bill and copies the figures. docs.issue_receipt() requires
    -- the bill to exist at generation; nothing requires it to still exist afterwards,
    -- which is the correct semantics for paper.
    bill_id uuid NOT NULL,

    receipt_number text NOT NULL,
    revision       integer NOT NULL DEFAULT 1,

    -- SNAPSHOTTED, ALL OF IT. M4-A ruled that a bill translates by ITS OWN locale and not
    -- the reader's, so a bill reprinted for a manager does not change language. A receipt
    -- inherits that rule and hardens it: the locale is copied here, and there is no
    -- parameter anywhere in this file by which a reader's locale could reach a rendering.
    locale        menu.customer_locale NOT NULL,
    currency_code char(3) NOT NULL,

    -- The three figures FR-BIL-010 requires as separate lines, plus the method
    -- FR-BIL-017 adds. Stored, not derived: a receipt that recomputed its total on read
    -- would disagree with the paper in the customer's hand exactly when somebody is
    -- disputing a bill.
    bill_total_minor money.amount_minor NOT NULL,
    tip_total_minor  money.amount_minor NOT NULL DEFAULT 0,
    paid_total_minor money.amount_minor NOT NULL,
    payment_method   text NOT NULL,

    calculation_version text NOT NULL,
    generated_by_user_id uuid NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT receipt_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT receipt_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT receipt_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT receipt_generator_fk FOREIGN KEY (tenant_id, generated_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT receipt_currency_fk FOREIGN KEY (currency_code)
        REFERENCES money.currency (code) ON DELETE RESTRICT,
    CONSTRAINT receipt_number_not_blank CHECK (btrim(receipt_number) <> ''),
    CONSTRAINT receipt_method_not_blank CHECK (btrim(payment_method) <> ''),
    CONSTRAINT receipt_revision_positive CHECK (revision >= 1),
    CONSTRAINT receipt_totals_not_negative CHECK (
        bill_total_minor >= 0 AND tip_total_minor >= 0 AND paid_total_minor >= 0),

    -- KEYED DEDUPLICATION, the first half. One receipt document per bill per revision, so
    -- a generator called twice for one settlement collides instead of producing a second
    -- document. M3-B's lesson: the index refuses the duplicate even when the function
    -- forgets to look.
    CONSTRAINT receipt_one_per_bill_revision UNIQUE (tenant_id, bill_id, revision),
    CONSTRAINT receipt_number_unique UNIQUE (tenant_id, receipt_number)
);

COMMENT ON TABLE docs.receipt IS
    'FR-BIL-010''s digital receipt and the record of FR-BIL-017''s physical one. Durable, '
    'append-only, and snapshotted: it holds no key into billing.bill because that is a '
    'projection, and it stores its own figures because paper does not change when a row '
    'does. Its locale is the BILL''S, never the reader''s — M4-A''s rule, which is why a '
    'reprint for a manager is in the customer''s language.';

CREATE INDEX receipt_bill_idx ON docs.receipt (tenant_id, bill_id);

CREATE TABLE docs.receipt_line (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,
    receipt_id uuid NOT NULL,
    kind       docs.receipt_line_kind NOT NULL,
    display_order integer NOT NULL,

    -- The label AS PRINTED, in the receipt's locale. Snapshotted for the same reason the
    -- figures are: the wording a customer read is the wording the record must show, even
    -- after somebody approves a better translation.
    label text NOT NULL,

    -- NULL only for payment_method, which is a word rather than a figure.
    amount_minor money.amount_minor,

    CONSTRAINT receipt_line_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT receipt_line_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT receipt_line_receipt_fk FOREIGN KEY (tenant_id, receipt_id)
        REFERENCES docs.receipt (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT receipt_line_label_not_blank CHECK (btrim(label) <> ''),
    CONSTRAINT receipt_line_amount_present_unless_method CHECK (
        (kind = 'payment_method' AND amount_minor IS NULL)
     OR (kind <> 'payment_method' AND amount_minor IS NOT NULL)),
    CONSTRAINT receipt_line_order_unique UNIQUE (tenant_id, receipt_id, display_order)
);

-- AT MOST ONE OF EACH SINGLETON KIND. A merged bill-and-tip line would otherwise be
-- indistinguishable from a receipt that simply had no tip: one line of kind bill_total
-- carrying both figures. With the kinds separated and singular, a merge is a bill_total
-- that disagrees with the bill, and the faithfulness trigger below says so by name.
-- A partial unique index because a UNIQUE constraint cannot carry a WHERE clause, and
-- bill_component is the one kind a receipt legitimately repeats.
CREATE UNIQUE INDEX receipt_line_one_of_each_singleton
    ON docs.receipt_line (tenant_id, receipt_id, kind)
    WHERE kind <> 'bill_component';

COMMENT ON TABLE docs.receipt_line IS
    'The receipt as printed, one row per line. FR-BIL-010 requires bill total, optional '
    'tip and total paid to be SEPARATE lines and FR-BIL-017 adds the payment method; the '
    'kinds are separate values and the singleton kinds are unique per receipt, so a '
    'merged line is a structural impossibility rather than a style guideline.';


-- ===========================================================================
-- One implementation of what has been paid onto a bill balance
-- ===========================================================================
-- THIS IS A CONSOLIDATION, NOT A NEW FACT. The expression "allocations to this bill's
-- balance, net of reversals" already existed in three places when this slice began:
-- inside billing.outstanding_balance(), inside payments.order_is_paid(), and inside the
-- capture path in 0023. A receipt needs the same figure, and adding a fourth copy is the
-- defect this repository has now repaired five times — the README's undescribed slice,
-- the CI matrix that said five jobs, the ownership map that said no migration existed,
-- the evidence step that forgot a suite log, and the control step that forgot one too.
--
-- IT LIVES IN billing, DELIBERATELY. tests/m4a enumerates the balance functions from the
-- catalog — by name matching (balance|outstanding|total|settle|finali), or by a body that
-- reads bill_total_minor, WITHIN THE billing SCHEMA — and requires that none of them
-- reads a tip. That fence is source-level and not transitive, so putting this helper in
-- payments would have moved the arithmetic OUTSIDE the fence and left a later edit free
-- to add a tip read where nothing was looking. Named as it is, in the schema it is in, it
-- joins the enumerated set instead: the fence gets one function wider, not one weaker.

CREATE FUNCTION billing.bill_balance_paid_minor(p_tenant_id uuid, p_bill_id uuid)
RETURNS money.amount_minor
LANGUAGE sql STABLE
AS $$
    SELECT coalesce((SELECT sum(a.amount_minor)
                       FROM payments.allocation a
                      WHERE a.tenant_id = p_tenant_id AND a.bill_id = p_bill_id
                        AND a.target = 'bill_balance'), 0)
         - coalesce((SELECT sum(r.amount_minor)
                       FROM payments.reversal r
                       JOIN payments.allocation a
                         ON a.tenant_id = r.tenant_id AND a.id = r.allocation_id
                      WHERE a.tenant_id = p_tenant_id AND a.bill_id = p_bill_id
                        AND a.target = 'bill_balance'), 0);
$$;

COMMENT ON FUNCTION billing.bill_balance_paid_minor(uuid, uuid) IS
    'What has actually been received against this bill''s balance: allocations whose '
    'target is bill_balance, net of reversals. THE ONE implementation — '
    'billing.outstanding_balance() and payments.order_is_paid() both call it rather than '
    'repeating it, and tests/m4c asserts from the catalog that both still do — so the '
    'consolidation cannot silently regress into three copies again. '
    'payments.reconciliation() is NOT a fourth copy and must not be re-pointed here: it '
    'groups by provider over a window, keeps bill and tip allocations in SEPARATE columns '
    'and reports reversals as their own column rather than netting them, which is exactly '
    'what FR-PAY-013 requires and what this function, by netting, does not do. Two '
    'aggregations over the same tables answering different questions is not duplication. '
    'IT DOES NOT READ billing.tip and must not: a tip allocation has target tip, and '
    'there is no branch here by which one could enter the sum.';

-- The two existing callers, re-pointed. Bodies otherwise unchanged, and each keeps every
-- property its own gate proved: outstanding_balance still subtracts dispositions and
-- still reads no tip, order_is_paid still asks only whether the bill is covered in full.

CREATE OR REPLACE FUNCTION billing.outstanding_balance(p_tenant_id uuid, p_bill_id uuid)
RETURNS money.amount_minor
LANGUAGE sql STABLE
AS $$
    SELECT b.bill_total_minor
           - coalesce((SELECT sum(d.amount_minor)
                         FROM billing.bill_disposition d
                        WHERE d.tenant_id = b.tenant_id AND d.bill_id = b.id), 0)
           - billing.bill_balance_paid_minor(b.tenant_id, b.id)
      FROM billing.bill b
     WHERE b.tenant_id = p_tenant_id AND b.id = p_bill_id;
$$;

CREATE OR REPLACE FUNCTION payments.order_is_paid(p_tenant_id uuid, p_order_id uuid)
RETURNS boolean
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_bill      uuid;
    v_total     bigint;
BEGIN
    SELECT b.id, b.bill_total_minor INTO v_bill, v_total
      FROM billing.bill b
      JOIN billing.check c ON c.tenant_id = b.tenant_id AND c.id = b.check_id
     WHERE b.tenant_id = p_tenant_id
       AND b.state = 'issued'
       AND EXISTS (SELECT 1 FROM billing.check_allocation a
                    WHERE a.tenant_id = c.tenant_id AND a.check_id = c.id
                      AND a.order_id = p_order_id)
     ORDER BY b.issued_at DESC
     LIMIT 1;

    IF v_bill IS NULL THEN
        RETURN false;
    END IF;

    -- A tip does not pay for an order, and the function that computes this cannot see
    -- one: billing.bill_balance_paid_minor() filters on target = 'bill_balance'.
    RETURN billing.bill_balance_paid_minor(p_tenant_id, v_bill) >= v_total;
END;
$$;

-- The tip total on a bill, net of corrections. Tips hang off a SHARE (FR-BIL-015 gives
-- each payer their own), so this walks billing.bill_share to reach them.

CREATE FUNCTION docs.tip_total_for_bill(p_tenant_id uuid, p_bill_id uuid)
RETURNS money.amount_minor
LANGUAGE sql STABLE
AS $$
    SELECT coalesce((SELECT sum(t.amount_minor)
                       FROM billing.tip t
                       JOIN billing.bill_share s
                         ON s.tenant_id = t.tenant_id AND s.id = t.bill_share_id
                      WHERE t.tenant_id = p_tenant_id AND s.bill_id = p_bill_id), 0)
         - coalesce((SELECT sum(c.amount_minor)
                       FROM billing.tip_correction c
                       JOIN billing.tip t
                         ON t.tenant_id = c.tenant_id AND t.id = c.tip_id
                       JOIN billing.bill_share s
                         ON s.tenant_id = t.tenant_id AND s.id = t.bill_share_id
                      WHERE c.tenant_id = p_tenant_id AND s.bill_id = p_bill_id), 0);
$$;

COMMENT ON FUNCTION docs.tip_total_for_bill(uuid, uuid) IS
    'What was tipped against this bill, net of FR-BIL-016''s corrections. It lives in '
    'docs and not in billing ON PURPOSE: tests/m4a requires that no billing balance '
    'function reads a tip, and a tip-summing function in that schema whose name contains '
    '"total" would join the enumerated set and fail the rule it is not in breach of. The '
    'receipt is the one document that shows both figures, so the function that fetches '
    'the tip belongs to the document, not to the bill.';


-- ===========================================================================
-- Append-only, by trigger and by grant (FR-DAT-008B)
-- ===========================================================================
-- Two independent locks, the arrangement M1-C used on the audit tables and M3-A on the
-- order ledger. The grant below withholds UPDATE and DELETE from the application role;
-- this trigger refuses them from ANYONE, the table owner included, under FORCE ROW LEVEL
-- SECURITY. Either lock surviving the other's removal is the point.

CREATE FUNCTION app.refuse_financial_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'LEDGER_ROW_DELETED_NOT_REVERSED: %.% is append-only. A receipt is the record of '
        'a document a customer is holding, and it cannot be corrected by changing it — '
        'issue a further revision, or record the reversal that undoes what it says. '
        'FR-DAT-008B: no destructive correction',
        TG_TABLE_SCHEMA, TG_TABLE_NAME USING ERRCODE = 'HS409';
END;
$$;

COMMENT ON FUNCTION app.refuse_financial_mutation() IS
    'FR-DAT-008B at the write. IN app RATHER THAN docs, and generic over TG_TABLE_NAME, '
    'because 0028 attaches it to ledger tables in billing, cash and payments too: a '
    'drawer count refused by a function called refuse_document_mutation would be a '
    'diagnostic naming something the row is not. Which tables must carry it is DECLARED '
    'by app.financial_table_class() in 0028 and asserted from the catalog by tests/m4c, '
    'so a financial table added at a later gate with no classification fails the build '
    'rather than sliding past the audit.';

CREATE TRIGGER receipt_is_append_only
    BEFORE UPDATE OR DELETE ON docs.receipt
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

CREATE TRIGGER receipt_line_is_append_only
    BEFORE UPDATE OR DELETE ON docs.receipt_line
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

CREATE TRIGGER printer_test_is_append_only
    BEFORE UPDATE OR DELETE ON docs.printer_test
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();


-- ===========================================================================
-- The receipt must say what actually happened (FR-BIL-010, NC-M4-002's doctrine)
-- ===========================================================================
-- A deferred constraint trigger, so it fires once the lines are all written rather than
-- after the first. It compares every printed figure with ITS OWN SOURCE, which is what
-- makes a merged line detectable: a bill_total line carrying the bill plus the tip
-- disagrees with the bill.
--
-- AND THE DIAGNOSTIC NAMES ONLY WHAT IT VERIFIED. If the discrepancy is exactly the tip
-- and the tip is not zero, it says the tip was merged, because it checked. Otherwise it
-- says the figure is unfaithful and gives both numbers. M4-A's NC-M4A-006 named a cause
-- it had not established, and this is the shape of not doing that again.

CREATE FUNCTION docs.assert_receipt_is_faithful() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    r docs.receipt%ROWTYPE;
    v_bill_total bigint;
    v_tip        bigint;
    v_paid       bigint;
    v_line       bigint;
BEGIN
    SELECT * INTO r FROM docs.receipt
     WHERE tenant_id = NEW.tenant_id AND id = NEW.receipt_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'RECEIPT_NOT_FOUND: line % names receipt %, which does not exist',
            NEW.id, NEW.receipt_id USING ERRCODE = 'HS404';
    END IF;

    SELECT b.bill_total_minor INTO v_bill_total FROM billing.bill b
     WHERE b.tenant_id = r.tenant_id AND b.id = r.bill_id;
    -- The bill may legitimately be gone: it is a projection and this receipt is durable.
    -- When it is gone there is nothing to compare against and the snapshot stands, which
    -- is the correct semantics for paper. What must never happen is comparing against a
    -- MISSING row and calling that agreement, so the branch is explicit.
    IF v_bill_total IS NULL THEN
        RETURN NULL;
    END IF;

    v_tip  := docs.tip_total_for_bill(r.tenant_id, r.bill_id);
    v_paid := billing.bill_balance_paid_minor(r.tenant_id, r.bill_id);

    IF NEW.kind = 'bill_total' THEN
        v_line := NEW.amount_minor;
        IF v_line <> v_bill_total THEN
            IF v_tip > 0 AND v_line = v_bill_total + v_tip THEN
                RAISE EXCEPTION
                    'TIP_MERGED_ON_RECEIPT: the bill total line on receipt % reads %, '
                    'which is the bill total % plus the tip %. M4-A proved a tip cannot '
                    'reach a bill balance; a receipt that adds them together undoes that '
                    'where the customer is the only person who would notice. FR-BIL-010 '
                    'requires them as separate lines and both lines exist',
                    r.receipt_number, v_line, v_bill_total, v_tip
                    USING ERRCODE = 'HS409';
            END IF;
            RAISE EXCEPTION
                'RECEIPT_FIGURE_UNFAITHFUL: the bill total line on receipt % reads % and '
                'the bill totals %. The difference is not the tip, so this names no '
                'cause beyond the disagreement itself',
                r.receipt_number, v_line, v_bill_total USING ERRCODE = 'HS409';
        END IF;
    ELSIF NEW.kind = 'tip' THEN
        IF NEW.amount_minor <> v_tip THEN
            RAISE EXCEPTION
                'RECEIPT_FIGURE_UNFAITHFUL: the tip line on receipt % reads % and the '
                'tips recorded against the bill, net of corrections, come to %',
                r.receipt_number, NEW.amount_minor, v_tip USING ERRCODE = 'HS409';
        END IF;
    ELSIF NEW.kind = 'total_paid' THEN
        IF NEW.amount_minor <> v_paid + v_tip THEN
            RAISE EXCEPTION
                'RECEIPT_FIGURE_UNFAITHFUL: the total paid line on receipt % reads % and '
                'what was received comes to % — % against the bill balance and % in '
                'tips. Total paid is the only line on which the two are added, because '
                'it is the one figure that describes the money that changed hands',
                r.receipt_number, NEW.amount_minor, v_paid + v_tip, v_paid, v_tip
                USING ERRCODE = 'HS409';
        END IF;
    END IF;

    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER receipt_line_is_faithful
    AFTER INSERT ON docs.receipt_line
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION docs.assert_receipt_is_faithful();

COMMENT ON FUNCTION docs.assert_receipt_is_faithful() IS
    'Every printed figure against its own source, at the write rather than at the route. '
    'TOTAL PAID IS THE ONE LINE THAT ADDS THE TWO, and that is not a merge: FR-BIL-010 '
    'asks for bill total, tip and total paid as three lines, and the third is by '
    'definition the sum of the first two. What is forbidden is the BILL TOTAL carrying a '
    'tip, and that is what TIP_MERGED_ON_RECEIPT names — after verifying that the excess '
    'is exactly the tip, never on the assumption that it must be.';


-- ===========================================================================
-- Completely, in the session language (FR-I18N-001C)
-- ===========================================================================
-- "Completely" is the requirement and a partially translated receipt is the failure mode
-- M2-C found on a screen. On a screen a missing string is a bad afternoon; on paper it is
-- a document the customer cannot read and nobody can re-render.
--
-- The check is that a non-English receipt carries no line whose label is the English
-- source text — because that is what a missing approved translation FALLS BACK TO, and a
-- fallback that reaches paper is the defect. English receipts are exempt for the obvious
-- reason: there the source text is the translation.

CREATE FUNCTION docs.assert_receipt_is_complete_in_its_locale() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    r docs.receipt%ROWTYPE;
    v_fallbacks text[];
BEGIN
    SELECT * INTO r FROM docs.receipt
     WHERE tenant_id = NEW.tenant_id AND id = NEW.receipt_id;
    IF NOT FOUND OR r.locale = 'en' THEN
        RETURN NULL;
    END IF;

    SELECT array_agg(l.kind::text ORDER BY l.display_order) INTO v_fallbacks
      FROM docs.receipt_line l
     WHERE l.tenant_id = r.tenant_id AND l.receipt_id = r.id
       AND EXISTS (SELECT 1 FROM docs.line_wording w
                    WHERE w.tenant_id = r.tenant_id AND w.kind = l.kind
                      AND w.status = 'active' AND w.source_text = l.label);

    IF v_fallbacks IS NOT NULL THEN
        RAISE EXCEPTION
            'RECEIPT_INCOMPLETE_IN_LOCALE: receipt % is in % and % line(s) carry the '
            'English source text because no approved translation was found: %. '
            'FR-I18N-001C says COMPLETELY, and a receipt is paper — a customer cannot '
            'ask it to re-render',
            r.receipt_number, r.locale, array_length(v_fallbacks, 1), v_fallbacks
            USING ERRCODE = 'HS422';
    END IF;

    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER receipt_line_is_complete_in_its_locale
    AFTER INSERT ON docs.receipt_line
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION docs.assert_receipt_is_complete_in_its_locale();


-- ===========================================================================
-- Putting it on paper, once (FR-BIL-011, FR-BIL-017)
-- ===========================================================================

CREATE TABLE docs.print_attempt (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,
    receipt_id uuid NOT NULL,
    printer_id uuid NOT NULL,

    -- THE OUTCOME IS OF THE DEVICE TYPE. A file sink cannot produce a value of it, so
    -- there is no column here a preview could be recorded into.
    outcome docs.print_outcome NOT NULL,

    is_reprint boolean NOT NULL DEFAULT false,
    reason_code_id uuid,
    reason_text    text,
    operator_user_id uuid NOT NULL,

    bytes_sha256 char(64) NOT NULL,
    byte_count   integer NOT NULL,
    detail       text,
    attempted_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT print_attempt_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT print_attempt_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT print_attempt_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT print_attempt_receipt_fk FOREIGN KEY (tenant_id, receipt_id)
        REFERENCES docs.receipt (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT print_attempt_printer_fk FOREIGN KEY (tenant_id, printer_id)
        REFERENCES docs.printer (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT print_attempt_operator_fk FOREIGN KEY (tenant_id, operator_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT print_attempt_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT print_attempt_digest_is_a_digest CHECK (bytes_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT print_attempt_byte_count_positive CHECK (byte_count > 0),

    -- FR-BIL-011: a reprint is MARKED AND AUDITED with operator and reason. The operator
    -- is required on every attempt; the reason is required on a reprint and forbidden on
    -- an original, so "reprint" cannot be a word somebody wrote in a text field.
    CONSTRAINT print_attempt_reprint_carries_its_reason CHECK (
        (is_reprint AND reason_code_id IS NOT NULL AND btrim(coalesce(reason_text, '')) <> '')
     OR (NOT is_reprint AND reason_code_id IS NULL AND reason_text IS NULL))
);

-- KEYED DEDUPLICATION, the second half and the one that matters. At most ONE original
-- print per receipt: a partial unique index, so a second first-print is refused by the
-- index even if the function that should have checked forgets. M3-B's rule, on the
-- artifact where a duplicate is a customer holding two records of one payment. A reprint
-- is deliberately outside the index, because reprinting is legal and audited.
CREATE UNIQUE INDEX print_attempt_one_original_per_receipt
    ON docs.print_attempt (tenant_id, receipt_id) WHERE NOT is_reprint;

COMMENT ON TABLE docs.print_attempt IS
    'FR-BIL-017''s physical print, recorded, and FR-BIL-011''s reprint. Its outcome is '
    'docs.print_outcome so only a device can produce one; a partial unique index permits '
    'exactly one non-reprint per receipt; and a reprint must carry an operator and a '
    'reason code. The bytes are recorded by DIGEST, never stored: a receipt names a '
    'person and what they bought, and a print log is a log.';

CREATE TABLE docs.render_attempt (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,
    kind       docs.document_kind NOT NULL,

    -- A preview may be of a receipt or of a document that has no receipt at all — a
    -- kitchen ticket, a label — so this is nullable and carries no key into a projection.
    receipt_id uuid,
    printer_id uuid NOT NULL,

    -- THE OUTCOME IS OF THE PREVIEW TYPE, and the word is 'rendered'. Nothing here can be
    -- read as a print, and nothing here fits docs.print_attempt.outcome.
    outcome docs.render_outcome NOT NULL,

    bytes_sha256 char(64) NOT NULL,
    byte_count   integer NOT NULL,
    requested_by_user_id uuid NOT NULL,
    rendered_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT render_attempt_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT render_attempt_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT render_attempt_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT render_attempt_receipt_fk FOREIGN KEY (tenant_id, receipt_id)
        REFERENCES docs.receipt (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT render_attempt_printer_fk FOREIGN KEY (tenant_id, printer_id)
        REFERENCES docs.printer (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT render_attempt_actor_fk FOREIGN KEY (tenant_id, requested_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT render_attempt_digest_is_a_digest CHECK (bytes_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT render_attempt_byte_count_positive CHECK (byte_count > 0)
);

COMMENT ON TABLE docs.render_attempt IS
    'FR-UX-018''s preview. Bytes reached a file, and that is all this records — its '
    'outcome type says rendered, not printed, and no value of it fits the column a print '
    'is recorded in. A preview can be taken as often as anybody likes, so nothing here '
    'is unique.';

-- The sink each table accepts, enforced rather than trusted. A print attempt against a
-- preview printer, or a render against a device, would otherwise be recordable — and the
-- type boundary would be doing half its job while the row said something false.

CREATE FUNCTION docs.assert_attempt_matches_the_sink() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_sink docs.sink_kind;
    v_expected docs.sink_kind := CASE TG_TABLE_NAME
        WHEN 'print_attempt'  THEN 'device'::docs.sink_kind
        WHEN 'render_attempt' THEN 'preview'::docs.sink_kind
        WHEN 'printer_test'   THEN 'device'::docs.sink_kind
    END;
BEGIN
    IF v_expected IS NULL THEN
        RAISE EXCEPTION
            'SINK_EXPECTATION_UNKNOWN: %.% carries this trigger and no expected sink is '
            'declared for it. Refusing rather than defaulting: a sink check that passed '
            'a table it had no rule for would be an assertion that cannot fail',
            TG_TABLE_SCHEMA, TG_TABLE_NAME USING ERRCODE = 'HS500';
    END IF;

    SELECT p.sink INTO v_sink FROM docs.printer p
     WHERE p.tenant_id = NEW.tenant_id AND p.id = NEW.printer_id;

    IF v_sink <> v_expected THEN
        RAISE EXCEPTION
            'SINK_MISMATCH: %.% records a % outcome and printer % is a % sink. A file '
            'that received these bytes is not a receipt a customer received, and the '
            'row would say it was',
            TG_TABLE_SCHEMA, TG_TABLE_NAME, v_expected, NEW.printer_id, v_sink
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER print_attempt_needs_a_device
    BEFORE INSERT ON docs.print_attempt
    FOR EACH ROW EXECUTE FUNCTION docs.assert_attempt_matches_the_sink();

CREATE TRIGGER printer_test_needs_a_device
    BEFORE INSERT ON docs.printer_test
    FOR EACH ROW EXECUTE FUNCTION docs.assert_attempt_matches_the_sink();

CREATE TRIGGER render_attempt_needs_a_preview
    BEFORE INSERT ON docs.render_attempt
    FOR EACH ROW EXECUTE FUNCTION docs.assert_attempt_matches_the_sink();

-- The named refusal for a duplicate original print. The partial unique index above
-- already refuses it; this makes the refusal SAY WHAT IT MEANS, because a unique
-- violation naming an index is a diagnostic a cashier cannot act on. Two locks, and the
-- index is the one that survives this function being dropped.

CREATE FUNCTION docs.refuse_duplicate_receipt_print() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing docs.print_attempt%ROWTYPE;
BEGIN
    IF NEW.is_reprint THEN
        RETURN NEW;
    END IF;
    SELECT * INTO v_existing FROM docs.print_attempt a
     WHERE a.tenant_id = NEW.tenant_id AND a.receipt_id = NEW.receipt_id
       AND NOT a.is_reprint;
    IF FOUND THEN
        RAISE EXCEPTION
            'DUPLICATE_RECEIPT_PRINTED: receipt % was already printed at % by attempt %. '
            'A receipt printed twice is a customer holding two records of one payment. A '
            'second copy is legal as a REPRINT, which is marked as one and carries the '
            'operator and the reason (FR-BIL-011)',
            NEW.receipt_id, v_existing.attempted_at, v_existing.id
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER print_attempt_is_not_a_duplicate
    BEFORE INSERT ON docs.print_attempt
    FOR EACH ROW EXECUTE FUNCTION docs.refuse_duplicate_receipt_print();


-- ===========================================================================
-- The receipt joins the correlation chain (FR-INT-014)
-- ===========================================================================
-- 0026 added 'receipt' to ordering.artifact_kind and this names its owner, which 0025's
-- DO block and tests/m4b both require. A receipt is DURABLE — no rebuild deletes it — so
-- no rebuild restores its links either, and the mapping says exactly that rather than
-- naming a function that would never run.

CREATE OR REPLACE FUNCTION ordering.correlation_link_rebuilt_by(p_kind ordering.artifact_kind)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE p_kind
        WHEN 'request'            THEN 'ordering.rebuild_projections'
        WHEN 'cart'               THEN 'ordering.rebuild_projections'
        WHEN 'table_session'      THEN 'ordering.rebuild_projections'
        WHEN 'order'              THEN 'ordering.rebuild_projections'
        WHEN 'fulfillment_ticket' THEN 'ordering.rebuild_projections'
        WHEN 'service_request'    THEN 'ordering.rebuild_projections'
        WHEN 'check'              THEN 'billing.rebuild_projections'
        WHEN 'bill'               THEN 'billing.rebuild_projections'
        WHEN 'tip'                THEN 'billing.rebuild_projections'
        WHEN 'payment'            THEN 'billing.rebuild_projections'
        -- Durable, so no rebuild owns these links. Spelled out rather than left NULL:
        -- NULL is what 0025's DO block and tests/m4b treat as "nobody thought about this
        -- kind", and that is precisely the defect they exist to catch.
        WHEN 'receipt'            THEN '(durable: no rebuild deletes a receipt link)'
    END;
$$;

CREATE FUNCTION docs.link_receipt_to_the_chain() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, docs, ordering, billing, public
AS $$
BEGIN
    -- Through 0010's own helper, not a second INSERT. ordering.link_correlation_artifact()
    -- is what every other producer in the chain calls, and a raw insert here would be a
    -- second implementation of "join the chain" that could drift from it.
    PERFORM ordering.link_correlation_artifact(
        NEW.tenant_id, NEW.outlet_id, l.correlation_id, 'receipt', NEW.id, now())
      FROM ordering.correlation_link l
     WHERE l.tenant_id = NEW.tenant_id
       AND l.artifact_kind = 'bill' AND l.artifact_id = NEW.bill_id
     LIMIT 1;
    RETURN NULL;
END;
$$;

CREATE TRIGGER receipt_joins_the_chain
    AFTER INSERT ON docs.receipt
    FOR EACH ROW EXECUTE FUNCTION docs.link_receipt_to_the_chain();


-- ===========================================================================
-- FR-SEC-018's M4 clause: retention cannot destroy a financial ledger
-- ===========================================================================
-- The audit at M4-C found FR-SEC-018 half built: 0007 added 'anonymize' to
-- config.retention_action for exactly this requirement, and NO LEGAL HOLD EXISTS. The
-- package revalidates the clause at M4 for ledger-protected financial records, and this
-- is that half — the only security clause the package places at this gate.
--
-- 0003 already refuses a retention policy that targets the audit tables
-- (retention_policy_never_targets_audit). The financial ledgers now need the same
-- protection, because FR-DAT-008B makes them append-only and a retention sweep is the one
-- path that deletes rows without going through a trigger on the table it deletes from.
--
-- BY SCHEMA, NOT BY TABLE LIST. A list of table names is a list that goes stale on the
-- next migration; the schemas that hold money are billing, payments, cash and docs, and a
-- new financial table lands inside one of them. What this does NOT protect is a financial
-- table somebody puts in a non-financial schema, and tests/m4c asserts the converse from
-- the catalog: every table carrying the append-only trigger lives in a schema this
-- constraint names.
ALTER TABLE config.retention_policy
    ADD CONSTRAINT retention_policy_never_targets_financial_ledgers
    CHECK (target_schema NOT IN ('billing', 'payments', 'cash', 'docs'));

COMMENT ON CONSTRAINT retention_policy_never_targets_financial_ledgers
    ON config.retention_policy IS
    'FR-SEC-018 at M4, and FR-DAT-008B''s other half. Bills, payments, tips, cash '
    'movements and receipts are append-only or reversal-based, and a retention sweep '
    'would delete them without passing the trigger that refuses a destructive '
    'correction. Anonymization remains available everywhere it belongs — a guest session '
    'in service is exactly what 0007 added it for. THIS DOES NOT CLOSE FR-SEC-018: no '
    'legal hold exists, and its entry in planning/requirement_coverage.json states a '
    'different closing test so that this half cannot close the whole.';


-- ===========================================================================
-- Row level security
-- ===========================================================================

DO $$
DECLARE t text;
BEGIN
    FOR t IN
        SELECT format('%I.%I', schemaname, tablename)
        FROM pg_tables WHERE schemaname = 'docs'
        ORDER BY tablename
    LOOP
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY %I ON %s FOR ALL '
            'USING (app.row_in_scope(tenant_id, outlet_id)) '
            'WITH CHECK (app.row_in_scope(tenant_id, outlet_id))',
            split_part(t, '.', 2) || '_isolation', t);
    END LOOP;
END;
$$;


-- ===========================================================================
-- Grants
-- ===========================================================================

GRANT USAGE ON SCHEMA docs TO hospitality_app;

GRANT SELECT ON docs.line_wording   TO hospitality_app;
GRANT SELECT ON docs.printer        TO hospitality_app;
GRANT SELECT ON docs.printer_test   TO hospitality_app;
GRANT SELECT ON docs.receipt        TO hospitality_app;
GRANT SELECT ON docs.receipt_line   TO hospitality_app;
GRANT SELECT ON docs.print_attempt  TO hospitality_app;
GRANT SELECT ON docs.render_attempt TO hospitality_app;

-- INSERT and nothing else on the append-only tables. The trigger refuses UPDATE and
-- DELETE from everyone including the owner; withholding the grant means the application
-- role cannot even attempt one. Two independent locks, either surviving the other.
GRANT INSERT ON docs.printer_test   TO hospitality_app;
GRANT INSERT ON docs.receipt        TO hospitality_app;
GRANT INSERT ON docs.receipt_line   TO hospitality_app;
GRANT INSERT ON docs.print_attempt  TO hospitality_app;
GRANT INSERT ON docs.render_attempt TO hospitality_app;

-- A printer is configuration, not a ledger: it may be registered and retired.
GRANT INSERT, UPDATE ON docs.printer TO hospitality_app;

GRANT EXECUTE ON FUNCTION docs.tip_total_for_bill(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION billing.bill_balance_paid_minor(uuid, uuid) TO hospitality_app;
