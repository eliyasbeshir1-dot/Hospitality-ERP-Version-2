-- =============================================================================
-- 0028 — Which financial tables are ledgers, the fiscal port, and who is of record
-- =============================================================================
-- FR-DAT-008B, FR-BIL-012, FR-TEN-009A, FR-PAY-009.
--
-- THE AUDIT AT M4-C ASKED A QUESTION NOBODY COULD ANSWER FROM THE CATALOG. FR-DAT-008B
-- says bills, receipts, payments, tips and cash movements are append-only or
-- reversal-based with no destructive correction, and 0019, 0023, 0024 and 0027 each
-- guarded the tables their own slice knew about. Asking the live schema which financial
-- tables refuse UPDATE and DELETE turned up ten that do not — and the honest answer for
-- each was different:
--
--   billing.bill_disposition   a void or a comp, authorised, with a reason and an
--                              override. Editing it rewrites who authorised what.  LEDGER
--   cash.drawer_count          a counted drawer, with over_short_minor GENERATED from
--                              the count. Editing it rewrites what the drawer was found
--                              to hold, and a miscount is corrected by counting again,
--                              never by changing the count that was taken.         LEDGER
--   payments.simulated_attempt the record that a simulated attempt happened.       LEDGER
--   docs.print_attempt         the record that paper came out.                     LEDGER
--   docs.render_attempt        the record that a preview was taken.                LEDGER
--
--   billing.service_charge_setting, billing.tip_setting, billing.tip_suggestion,
--   docs.line_wording          settings, which exist in order to be changed.     MUTABLE
--   cash.shift                 a state row whose transitions ARE the ledger, in
--                              cash.shift_transition, which is guarded.          MUTABLE
--
-- WHETHER A TABLE IS A LEDGER IS A JUDGEMENT AND CANNOT BE DERIVED. What can be derived
-- is whether somebody has made it. So the judgement is DECLARED, once, in a function this
-- file cannot avoid keeping complete: a DO block at the FOOT of this file refuses any
-- table in a financial schema that the classification does not name, and tests/m4c asserts from the catalog on
-- every run that every declared ledger carries the trigger. A financial table added at
-- M5a with no classification fails the build. That is the SUITE_UNACCOUNTED shape — the
-- defect is never the table somebody thought about.
--
-- WHAT IS NOT HERE. No provider's schema: FR-BIL-012 asks for a PORT, and the trap it
-- names is an abstraction with one implementation. What this file does about that trap is
-- stated where it is built, and what the port does not prove is in
-- planning/M4C_LIMITATIONS.md rather than a footnote.
-- =============================================================================


-- ===========================================================================
-- Which financial tables are ledgers (FR-DAT-008B)
-- ===========================================================================

CREATE FUNCTION app.financial_table_class(p_schema text, p_table text)
RETURNS text LANGUAGE sql IMMUTABLE
AS $$
    SELECT CASE p_schema || '.' || p_table
        -- Ledgers: what happened, and correcting one means adding a row, never
        -- changing one.
        WHEN 'billing.bill_disposition'   THEN 'ledger'
        WHEN 'billing.bill_event'         THEN 'ledger'
        WHEN 'billing.check'              THEN 'ledger'
        WHEN 'billing.check_allocation'   THEN 'ledger'
        WHEN 'billing.tip'                THEN 'ledger'
        WHEN 'billing.tip_correction'     THEN 'ledger'
        WHEN 'cash.custody_transfer'      THEN 'ledger'
        WHEN 'cash.denomination_tally'    THEN 'ledger'
        WHEN 'cash.drawer_count'          THEN 'ledger'
        WHEN 'cash.movement'              THEN 'ledger'
        WHEN 'cash.shift_transition'      THEN 'ledger'
        WHEN 'docs.print_attempt'         THEN 'ledger'
        WHEN 'docs.printer_test'          THEN 'ledger'
        WHEN 'docs.receipt'               THEN 'ledger'
        WHEN 'docs.receipt_line'          THEN 'ledger'
        WHEN 'docs.render_attempt'        THEN 'ledger'
        WHEN 'payments.payment_event'     THEN 'ledger'
        WHEN 'payments.payment_intent'    THEN 'ledger'
        WHEN 'payments.proof_confirmation' THEN 'ledger'
        WHEN 'payments.reversal'          THEN 'ledger'
        WHEN 'payments.simulated_attempt' THEN 'ledger'
        WHEN 'payments.terminal_result'   THEN 'ledger'

        -- Projections: written only by a fold, and DELETED WHOLESALE by a rebuild. They
        -- refuse ordinary writes for a different reason than a ledger does, and calling
        -- them ledgers would make the append-only assertion below claim something about
        -- them that is not true.
        WHEN 'billing.bill'               THEN 'projection'
        WHEN 'billing.bill_component'     THEN 'projection'
        WHEN 'billing.bill_share'         THEN 'projection'
        WHEN 'payments.payment'           THEN 'projection'
        WHEN 'payments.allocation'        THEN 'projection'

        -- MUTABLE: everything else, and the word is deliberately plain. An earlier
        -- draft of this had 'configuration' and 'lifecycle' as separate classes, which
        -- read well and asserted nothing — cash.shift is not configuration in any
        -- ordinary sense, and 'lifecycle' was a kinder word for 'not append-only'. Only
        -- one property here is checkable, so only one distinction is drawn: a ledger
        -- refuses UPDATE and DELETE, and everything else says why it does not, in the
        -- table at the head of this file rather than in a class name that implies a rule
        -- nothing enforces.
        WHEN 'billing.component_wording'       THEN 'mutable'
        WHEN 'billing.service_charge_setting'  THEN 'mutable'
        WHEN 'billing.tip_setting'             THEN 'mutable'
        WHEN 'billing.tip_suggestion'          THEN 'mutable'
        WHEN 'cash.shift'                      THEN 'mutable'
        WHEN 'docs.line_wording'               THEN 'mutable'
        WHEN 'docs.printer'                    THEN 'mutable'
        WHEN 'payments.payment_adapter'        THEN 'mutable'
        WHEN 'fiscal.adapter'                  THEN 'mutable'
        WHEN 'fiscal.document'                 THEN 'mutable'
    END;
$$;

COMMENT ON FUNCTION app.financial_table_class(text, text) IS
    'FR-DAT-008B. Whether a table in a financial schema is a ledger, a projection or '
    'configuration — a JUDGEMENT, declared once, because it cannot be read off the '
    'catalog. Three classes and no more, because only one property is checkable: a LEDGER '
    'refuses UPDATE and DELETE, a PROJECTION is written by a fold and dropped by a '
    'rebuild, and MUTABLE is everything else with its reason recorded at the head of '
    '0028. cash.shift is mutable and not a ledger BECAUSE ITS TRANSITIONS ARE THE '
    'LEDGER, in cash.shift_transition, which is guarded. The DO block at the foot of '
    'this migration refuses any financial table this does not name, and tests/m4c '
    'asserts from the catalog that every declared ledger carries the trigger.';

-- The five ledgers that were not refusing mutation. app.refuse_financial_mutation() is
-- 0027's, named for the job rather than for one schema precisely so that it can be
-- attached here without a drawer count being refused by something called a document.

CREATE TRIGGER bill_disposition_is_append_only
    BEFORE UPDATE OR DELETE ON billing.bill_disposition
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

CREATE TRIGGER drawer_count_is_append_only
    BEFORE UPDATE OR DELETE ON cash.drawer_count
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

CREATE TRIGGER simulated_attempt_is_append_only
    BEFORE UPDATE OR DELETE ON payments.simulated_attempt
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

CREATE TRIGGER print_attempt_is_append_only
    BEFORE UPDATE OR DELETE ON docs.print_attempt
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

CREATE TRIGGER render_attempt_is_append_only
    BEFORE UPDATE OR DELETE ON docs.render_attempt
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();


-- ===========================================================================
-- Who is the system of record (FR-TEN-009A)
-- ===========================================================================
-- The audit found this absent, and the package revalidates it at M4 because the registry
-- governs actual fiscal-document behaviour once fiscal documents exist. They exist below,
-- so it comes due here.
--
-- PHASE 1 ENUMERATION ONLY. The clause's sharp edge is that the registry must not become
-- a place where a deferred domain is named as somebody's system of record — that would be
-- a fenced module arriving through a data table. The concerns are an enum, closed, and
-- the fenced-surface scanner reads this file like any other.

CREATE TYPE org.record_concern AS ENUM
    ('menu', 'orders', 'billing', 'payments', 'cash', 'fiscal_documents', 'identity');

COMMENT ON TYPE org.record_concern IS
    'FR-TEN-009A. The Phase 1 concerns a system can be of record for, closed so that a '
    'deferred domain cannot be named as one. A registry with a free-text concern column '
    'is a registry that would eventually carry a fenced word.';

CREATE TABLE org.system_of_record (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL,
    -- The legal entity, not the outlet: which system is authoritative is a commercial and
    -- regulatory fact about the entity that files, and fiscal documents belong to it.
    legal_entity_id uuid NOT NULL,
    concern    org.record_concern NOT NULL,
    -- 'this_platform' or the name of an external system. Free text for the external case
    -- because naming somebody else's product is not this build's to enumerate.
    system_name text NOT NULL,
    is_this_platform boolean NOT NULL,
    effective_from timestamptz NOT NULL DEFAULT now(),
    recorded_by_user_id uuid NOT NULL,
    row_version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT system_of_record_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT system_of_record_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT system_of_record_entity_fk FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT system_of_record_actor_fk FOREIGN KEY (tenant_id, recorded_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT system_of_record_name_not_blank CHECK (btrim(system_name) <> ''),
    CONSTRAINT system_of_record_platform_names_itself CHECK (
        is_this_platform = (system_name = 'this_platform')),
    -- One answer per concern per entity. Two would make "which system is of record"
    -- depend on which row was read first, which is the question this table exists to
    -- settle.
    CONSTRAINT system_of_record_one_per_concern
        UNIQUE (tenant_id, legal_entity_id, concern)
);

COMMENT ON TABLE org.system_of_record IS
    'FR-TEN-009A. Which system is authoritative for each Phase 1 concern, per tenant and '
    'legal entity. The fiscal port below READS it: a fiscal document may only be issued '
    'by the platform for an entity that says this platform is of record for '
    'fiscal_documents, so the registry governs behaviour rather than describing it.';


-- ===========================================================================
-- The fiscal document port (FR-BIL-012)
-- ===========================================================================
-- "Expose a fiscal-document port and reconciliation status without embedding one
-- provider's schema."
--
-- THE TRAP THIS REQUIREMENT NAMES IS THE ONE IT CREATES: an abstraction with one
-- implementation, and no second case to prove it is an abstraction at all. Ethiopian
-- fiscal requirements arrive as a contracted integration that does not exist. So what is
-- built here is the PORT — the shape of a fiscal document request, its lifecycle, and its
-- reconciliation status — and the provider is a row, not a schema.
--
-- What keeps this honest rather than decorative:
--
--   * No column here is named for a provider, a device, or a signature format. A fiscal
--     document carries an OPAQUE provider reference and an opaque payload, and the
--     platform never parses either.
--   * The adapter is registered exactly as a payment adapter is, and its mode is derived
--     from its provider by CHECK, so a simulated fiscal adapter cannot report a live
--     document — M4-B's boundary, reused rather than reinvented.
--   * planning/M4C_LIMITATIONS.md states what this does not prove: that any real
--     provider's contract fits this shape. One implementation is one implementation.

CREATE SCHEMA fiscal;

COMMENT ON SCHEMA fiscal IS
    'FR-BIL-012''s port. What a fiscal document IS to this platform — a request, an '
    'outcome and a reconciliation status — with no provider''s schema inside it. The '
    'provider is configuration.';

CREATE TYPE fiscal.adapter_mode AS ENUM ('live', 'simulated');

CREATE TYPE fiscal.document_state AS ENUM
    ('requested', 'submitted', 'accepted', 'rejected', 'reconciled');

COMMENT ON TYPE fiscal.document_state IS
    'The lifecycle of a fiscal document. reconciled is DISTINCT from accepted: a provider '
    'accepting a submission and the platform having agreed its records with the '
    'provider''s are two different facts, and FR-BIL-012 asks for the second.';

CREATE TABLE fiscal.adapter (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid,
    provider  text NOT NULL,
    mode      fiscal.adapter_mode NOT NULL,
    status    org.lifecycle_status NOT NULL DEFAULT 'active',
    registered_by_user_id uuid NOT NULL,
    row_version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT fiscal_adapter_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT fiscal_adapter_mode_unique UNIQUE (id, mode),
    CONSTRAINT fiscal_adapter_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT fiscal_adapter_actor_fk FOREIGN KEY (tenant_id, registered_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fiscal_adapter_provider_shape CHECK (provider ~ '^[a-z][a-z0-9_]*$'),

    -- DERIVED, NOT DECLARED. Every provider in Phase 1 is simulated, because none is
    -- contracted. Making that a CHECK rather than a default means a live fiscal adapter
    -- cannot be created by an INSERT that simply says so — the same arrangement
    -- payments.payment_adapter carries, and for the same reason: nobody decides whether
    -- an uncontracted integration is live.
    CONSTRAINT fiscal_adapter_mode_is_derived CHECK (mode = 'simulated'),
    CONSTRAINT fiscal_adapter_one_per_provider UNIQUE (tenant_id, provider, status)
);

COMMENT ON TABLE fiscal.adapter IS
    'A fiscal provider, as configuration. Its mode is simulated BY CHECK and not by '
    'default: no Ethiopian fiscal integration is contracted, so no adapter may claim to '
    'be live, and the day one is contracted that CHECK is the line that has to change — '
    'visibly, in a migration, rather than in a row.';

CREATE TABLE fiscal.document (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    adapter_id uuid NOT NULL,
    adapter_mode fiscal.adapter_mode NOT NULL,

    -- The receipt this document is for. A durable table, so a real foreign key: unlike
    -- billing.bill, docs.receipt is never deleted and refolded.
    receipt_id uuid NOT NULL,

    state fiscal.document_state NOT NULL DEFAULT 'requested',

    -- OPAQUE, BOTH OF THEM. The platform does not parse a provider's reference and does
    -- not model its payload. That is what "without embedding one provider's schema"
    -- means in a table definition: there is nowhere here for a provider's field to go.
    provider_reference text,
    provider_payload   jsonb,

    requested_at  timestamptz NOT NULL DEFAULT now(),
    submitted_at  timestamptz,
    settled_at    timestamptz,
    reconciled_at timestamptz,
    rejection_reason text,

    CONSTRAINT fiscal_document_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT fiscal_document_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT fiscal_document_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fiscal_document_entity_fk FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fiscal_document_receipt_fk FOREIGN KEY (tenant_id, receipt_id)
        REFERENCES docs.receipt (tenant_id, id) ON DELETE RESTRICT,
    -- The adapter AND its mode, so a document cannot outlive the mode it was issued
    -- under. M4-B's arrangement on payments.payment.
    CONSTRAINT fiscal_document_adapter_fk FOREIGN KEY (adapter_id, adapter_mode)
        REFERENCES fiscal.adapter (id, mode) ON DELETE RESTRICT,

    CONSTRAINT fiscal_document_one_per_receipt UNIQUE (tenant_id, receipt_id),
    CONSTRAINT fiscal_document_states_carry_their_times CHECK (
        (state = 'requested'  AND submitted_at IS NULL AND settled_at IS NULL)
     OR (state = 'submitted'  AND submitted_at IS NOT NULL AND settled_at IS NULL)
     OR (state = 'accepted'   AND submitted_at IS NOT NULL AND settled_at IS NOT NULL)
     OR (state = 'rejected'   AND submitted_at IS NOT NULL AND settled_at IS NOT NULL
                              AND btrim(coalesce(rejection_reason, '')) <> '')
     OR (state = 'reconciled' AND submitted_at IS NOT NULL AND settled_at IS NOT NULL
                              AND reconciled_at IS NOT NULL))
);

COMMENT ON TABLE fiscal.document IS
    'FR-BIL-012''s port. A fiscal document is a request against a receipt, an outcome, '
    'and a reconciliation status — and nothing in this table names a provider''s field. '
    'provider_reference and provider_payload are opaque and the platform never parses '
    'them. One document per receipt, because two would make the fiscal record of a sale '
    'ambiguous.';

CREATE INDEX fiscal_document_state_idx
    ON fiscal.document (tenant_id, outlet_id, state, requested_at);

-- A fiscal document may only be issued where the registry says this platform is of
-- record. This is the clause that makes FR-TEN-009A govern rather than describe.

CREATE FUNCTION fiscal.assert_this_platform_is_of_record() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE v_of_record boolean;
BEGIN
    SELECT s.is_this_platform INTO v_of_record
      FROM org.system_of_record s
     WHERE s.tenant_id = NEW.tenant_id
       AND s.legal_entity_id = NEW.legal_entity_id
       AND s.concern = 'fiscal_documents';

    IF v_of_record IS NULL THEN
        RAISE EXCEPTION
            'SYSTEM_OF_RECORD_UNDECLARED: no entry says which system is of record for '
            'fiscal documents at legal entity %. A fiscal document is a filing, and '
            'issuing one from a system nobody has declared authoritative is how two '
            'systems come to file the same sale', NEW.legal_entity_id
            USING ERRCODE = 'HS409';
    END IF;
    IF NOT v_of_record THEN
        RAISE EXCEPTION
            'SYSTEM_OF_RECORD_IS_ELSEWHERE: legal entity % records another system as of '
            'record for fiscal documents, so this platform must not issue one',
            NEW.legal_entity_id USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER fiscal_document_needs_the_record
    BEFORE INSERT ON fiscal.document
    FOR EACH ROW EXECUTE FUNCTION fiscal.assert_this_platform_is_of_record();

-- Reconciliation status, per outlet and window. Counts by state and nothing else: what a
-- reconciliation view is FOR is finding the documents that did not arrive, and a figure
-- summed across states hides exactly those.

CREATE FUNCTION fiscal.reconciliation(
    p_tenant_id uuid, p_outlet_id uuid, p_from timestamptz, p_to timestamptz)
RETURNS TABLE (state fiscal.document_state, documents bigint, oldest timestamptz)
LANGUAGE sql STABLE
AS $$
    SELECT d.state, count(*)::bigint, min(d.requested_at)
      FROM fiscal.document d
     WHERE d.tenant_id = p_tenant_id AND d.outlet_id = p_outlet_id
       AND d.requested_at >= p_from AND d.requested_at < p_to
     GROUP BY d.state
     ORDER BY d.state;
$$;

COMMENT ON FUNCTION fiscal.reconciliation(uuid, uuid, timestamptz, timestamptz) IS
    'FR-BIL-012''s reconciliation status. Counts BY STATE, never a total: the question a '
    'reconciliation answers is which documents are stuck, and a single number hides the '
    'requested ones that never went anywhere. `oldest` is there for the same reason — a '
    'backlog is a date, not a count.';


-- ===========================================================================
-- Row level security
-- ===========================================================================

ALTER TABLE org.system_of_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE org.system_of_record FORCE ROW LEVEL SECURITY;
-- Scoped by tenant alone: a system-of-record entry belongs to a legal entity, which sits
-- ABOVE the outlet boundary, so an outlet predicate would hide an entity's own record
-- from every outlet under it. org.tenant carries the same shape for the same reason.
CREATE POLICY system_of_record_isolation ON org.system_of_record FOR ALL
    USING (app.row_in_scope(tenant_id, NULL))
    WITH CHECK (app.row_in_scope(tenant_id, NULL));

DO $$
DECLARE t text;
BEGIN
    FOR t IN
        SELECT format('%I.%I', schemaname, tablename)
        FROM pg_tables WHERE schemaname = 'fiscal'
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

GRANT USAGE ON SCHEMA fiscal TO hospitality_app;

GRANT SELECT ON org.system_of_record TO hospitality_app;
GRANT INSERT, UPDATE ON org.system_of_record TO hospitality_app;

GRANT SELECT ON fiscal.adapter  TO hospitality_app;
GRANT SELECT ON fiscal.document TO hospitality_app;
GRANT INSERT, UPDATE ON fiscal.adapter TO hospitality_app;
-- A fiscal document moves through its lifecycle, so UPDATE is real here. What it may not
-- do is vanish: DELETE is withheld, and app.financial_table_class() does not call this a
-- ledger precisely because its states are a lifecycle rather than an append-only chain.
GRANT INSERT, UPDATE ON fiscal.document TO hospitality_app;

GRANT EXECUTE ON FUNCTION fiscal.reconciliation(uuid, uuid, timestamptz, timestamptz)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION app.financial_table_class(text, text) TO hospitality_app;


-- ===========================================================================
-- The classification must be complete (FR-DAT-008B)
-- ===========================================================================
-- AT THE FOOT OF THE FILE, and that is not tidiness: the fiscal tables are created above
-- and a completeness check that ran before them would have passed by not seeing them,
-- which is the vacuity this project has caught four times.
--
-- Complete, or this migration does not apply. The same shape 0025 used on
-- ordering.correlation_link_rebuilt_by(): a classification with a hole in it is a
-- classification nobody can rely on, and the hole is always the table somebody forgot.
DO $$
DECLARE unclassified text[];
BEGIN
    SELECT array_agg(n.nspname || '.' || c.relname ORDER BY 1) INTO unclassified
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname IN ('billing', 'payments', 'cash', 'docs', 'fiscal')
       AND c.relkind = 'r'
       AND app.financial_table_class(n.nspname, c.relname) IS NULL;
    IF unclassified IS NOT NULL THEN
        RAISE EXCEPTION
            'FINANCIAL_TABLE_UNCLASSIFIED: % is in a financial schema and '
            'app.financial_table_class() does not say what it is. Every table that holds '
            'money must be a ledger, a projection or configuration, and somebody has to '
            'say which — the append-only rule cannot be enforced over a table nobody has '
            'classified', unclassified;
    END IF;
END;
$$;
