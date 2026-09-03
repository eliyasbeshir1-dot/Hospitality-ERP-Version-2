-- =============================================================================
-- 0023 — Payment capture, verification, dual allocation and reversal
-- =============================================================================
-- M4-A proved a tip cannot reach a bill balance. This decides what counts as money
-- actually received, and the decision is made by constraint rather than by policy in
-- every place it could be made by either.
--
-- THE BOUNDARY THIS FILE EXISTS TO HOLD (FR-PAY-015). The package divides payment into
-- three worlds and the division is a ruling, not a preference:
--
--     live at M4          cash; an external terminal's RESULT, recorded; a Telebirr or
--                         CBE Birr receipt a member of staff VERIFIED in the provider's
--                         own application and then attested to
--     simulated           direct provider APIs, until contracted and credentialed
--     never               raw PAN, CVV, card cryptograms
--
-- NC-M4-003 is the control: a simulated result must never be recordable as a live
-- provider outcome — not by configuration, not by a fixture, not by an operator holding
-- every permission there is. That is proved here in three independent ways, each of
-- which survives the removal of the other two:
--
--   1. THE MODE IS DERIVED FROM THE PROVIDER, NOT CHOSEN. payment_adapter carries a CHECK
--      computing mode from provider. There is no configuration value, no grant and no
--      fixture that makes a direct-provider adapter live, because mode is not an input.
--      A trigger additionally refuses any UPDATE of either column: the pair is identity.
--
--   2. THE TWO WORLDS ARE TWO TYPES. payments.live_outcome and payments.simulated_outcome
--      are distinct enums. PostgreSQL will not convert between them, so the column that
--      records what a live provider did cannot hold what a simulator returned — not
--      because something checks, but because the value does not fit. This is the shape
--      M4-A used for the tip: the absence of a column is the requirement.
--
--   3. THE REFUSAL IS AT THE WRITE. An allocation is the row that reduces a bill balance,
--      and a deferred constraint trigger refuses one whose payment is not live-moded,
--      not approved, or — for a proof-based provider — not verified by a named person.
--      A route check is bypassed by the next caller to appear; a constraint is not.
--
-- WHY PAYMENTS ARE A LEDGER AND A FOLD. FR-DAT-008B says bills, receipts, payments, tips
-- and cash movements are append-only or reversal-based with no destructive correction.
-- This takes the same arrangement billing took at 0019 and ordering at 0010: one event
-- table that is the truth, one function that folds it, a grant and a trigger as two
-- independent locks on the projection. A refund is an event, never an UPDATE, and
-- FR-PAY-009's "separate linked reversal records" is what the ledger already is.
--
-- WHAT IS NOT HERE. No receipt, no printing, no fiscal adapter, no report — M4-C. No
-- outlet node, no synchronization, no resilient print queue — M5a. No consumer for the
-- payment events this file emits: FR-PAY-010A asks for the SHAPE a future accounting
-- consumer could subscribe to, and accounting is fenced, so the shape is documented and
-- nothing subscribes.
-- =============================================================================

CREATE SCHEMA payments;

COMMENT ON SCHEMA payments IS
    'FR-PAY-001 … FR-PAY-017. What was tendered, by whom, through which adapter, verified '
    'how, and allocated separately to the bill balance and to the tip. Its own schema '
    'rather than a corner of billing because a bill is a document that states what is '
    'owed and a payment is an event that says what arrived; M4-A''s doctrine only holds '
    'if the second cannot quietly become part of the first.';


-- ===========================================================================
-- The adapter registry (FR-PAY-015, FR-INT-011)
-- ===========================================================================

CREATE TYPE payments.adapter_mode AS ENUM ('live', 'simulated');

COMMENT ON TYPE payments.adapter_mode IS
    'Whether an adapter records something that really happened or something a simulator '
    'produced. Never a setting: payments.payment_adapter derives it from the provider by '
    'CHECK, so the applicability is an invariant rather than a configuration choice — '
    'M2-B''s stale-QR ruling, applied to money.';

-- The providers Phase 1 knows. A closed list rather than free text, because "which
-- providers exist" is a fact about the package and an adapter naming one nobody ruled on
-- would sit in the registry looking contracted.
CREATE TYPE payments.provider AS ENUM (
    -- Live at M4. Each of these records something a human or a machine in the room did.
    'cash',
    'external_terminal',
    'telebirr_proof',
    'cbe_birr_proof',
    -- Simulated until contracted and credentialed (FR-PAY-015). These are the direct
    -- online APIs. They exist so that the boundary has something on the far side of it:
    -- a fence with nothing behind it is not a fence, it is an assertion over an empty set.
    'telebirr_direct',
    'cbe_birr_direct');

CREATE TABLE payments.payment_adapter (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL,
    outlet_id    uuid NOT NULL,
    provider     payments.provider NOT NULL,
    mode         payments.adapter_mode NOT NULL,

    -- FR-INT-011. Health advertises ACTIVE adapters, and an adapter that cannot work is
    -- not active. Separate from mode: a live adapter can be switched off for an outlet
    -- that has no card terminal, and that is a configuration decision. Whether it is
    -- SIMULATED is not.
    active       boolean NOT NULL DEFAULT true,
    activated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT payment_adapter_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT payment_adapter_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT payment_adapter_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT payment_adapter_one_per_provider UNIQUE (tenant_id, outlet_id, provider),

    -- LOCK ONE. The mode is a function of the provider, evaluated by the database on
    -- every insert and every update. There is no value a caller can pass, no
    -- configuration row to point at and no permission to hold that makes
    -- 'telebirr_direct' live. FR-PAY-015 says the direct APIs remain simulated until
    -- contracted and credentialed; contracting is not something this repository can do,
    -- so the constraint says so rather than a comment saying so.
    CONSTRAINT payment_adapter_mode_is_derived_from_the_provider CHECK (
        mode = CASE
            WHEN provider IN ('cash', 'external_terminal',
                              'telebirr_proof', 'cbe_birr_proof')
                THEN 'live'::payments.adapter_mode
            ELSE 'simulated'::payments.adapter_mode
        END),

    -- The identity a payment points at includes the mode, so a payment cannot reference
    -- an adapter and then disagree with it about which world it is in.
    CONSTRAINT payment_adapter_identity_includes_mode UNIQUE (id, mode)
);

COMMENT ON TABLE payments.payment_adapter IS
    'FR-PAY-015 and FR-INT-011. Which payment adapters this outlet has and which world '
    'each is in. mode is DERIVED from provider by CHECK and neither column may be '
    'updated, so NC-M4-003''s "label a direct-provider simulator as live" has no path '
    'through configuration at all — the promotion it attempts is not a value that exists.';

COMMENT ON COLUMN payments.payment_adapter.active IS
    'Whether this outlet can actually use it (FR-INT-011). Distinct from mode on purpose: '
    'an outlet without a card terminal deactivates the external-terminal adapter, and '
    'that is an operator''s decision. Nobody decides whether a direct API is simulated.';

CREATE FUNCTION payments.refuse_adapter_identity_change() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.provider IS DISTINCT FROM OLD.provider
       OR NEW.mode IS DISTINCT FROM OLD.mode THEN
        RAISE EXCEPTION
            'UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM: an adapter''s provider and mode are '
            'its identity and cannot be changed. Adapter % is %/%; the update asked for '
            '%/%. Promoting a simulator by UPDATE is the quiet form of the claim '
            'NC-M4-003 exists to catch — the CHECK already refuses an inconsistent pair, '
            'and this refuses the consistent pair that is a different adapter wearing the '
            'first one''s id',
            OLD.id, OLD.provider, OLD.mode, NEW.provider, NEW.mode
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER payment_adapter_identity_is_immutable
    BEFORE UPDATE ON payments.payment_adapter
    FOR EACH ROW EXECUTE FUNCTION payments.refuse_adapter_identity_change();


-- ===========================================================================
-- Two worlds, two types (FR-PAY-015, NC-M4-003)
-- ===========================================================================
-- LOCK TWO, and the one that needs no code to hold. These two enums carry the same
-- labels and are different types. PostgreSQL performs no implicit conversion between
-- them, so payments.payment.outcome — declared live_outcome — cannot be given what
-- payments.simulated_attempt.result holds. Not "is checked and rejected": does not fit.
--
-- This is the shape M4-A used to keep a tip out of a bill total. The strongest version of
-- "a simulated result cannot be recorded as live" is one in which there is no column it
-- could be recorded into.

CREATE TYPE payments.live_outcome AS ENUM ('approved', 'declined');

CREATE TYPE payments.simulated_outcome AS ENUM ('approved', 'declined');

COMMENT ON TYPE payments.live_outcome IS
    'What a live adapter reports: cash counted, a terminal''s printed result, or a proof '
    'a member of staff verified in the provider''s application. The only type '
    'payments.payment.outcome accepts.';

COMMENT ON TYPE payments.simulated_outcome IS
    'What a simulator returns. Deliberately a DIFFERENT type from live_outcome carrying '
    'the same labels: the labels are the same because a simulator simulates those '
    'answers, and the types are different because no assignment, cast or fixture may '
    'carry one into the other. FR-PAY-015 — direct provider APIs remain simulated until '
    'contracted, and cannot support a live pilot-readiness claim.';


-- ---------------------------------------------------------------------------
-- The simulated path, which is real and reachable (FR-PAY-015)
-- ---------------------------------------------------------------------------
-- A callable path rather than a registry entry with nothing behind it. NC-M4-003's
-- second half must attempt the forbidden write THROUGH the path a real integration would
-- take; a control fired by a schema assertion proves the schema, not that the system
-- refuses correctly.

CREATE TABLE payments.simulated_attempt (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL,
    outlet_id    uuid NOT NULL,
    adapter_id   uuid NOT NULL,
    adapter_mode payments.adapter_mode NOT NULL,

    currency_code  char(3) NOT NULL,
    amount_minor   money.amount_minor NOT NULL,
    result         payments.simulated_outcome NOT NULL,
    simulated_at   timestamptz NOT NULL DEFAULT now(),
    requested_by_user_id uuid,

    CONSTRAINT simulated_attempt_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT simulated_attempt_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT simulated_attempt_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT simulated_attempt_actor_fk FOREIGN KEY (tenant_id, requested_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT simulated_attempt_amount_positive CHECK (amount_minor > 0),

    -- The attempt names the mode it ran in, and the FK pins that name to the adapter's
    -- own identity. A simulated attempt cannot claim to have run live even in its own row.
    CONSTRAINT simulated_attempt_adapter_fk FOREIGN KEY (adapter_id, adapter_mode)
        REFERENCES payments.payment_adapter (id, mode) ON DELETE RESTRICT,
    CONSTRAINT simulated_attempt_is_simulated CHECK (adapter_mode = 'simulated')
);

COMMENT ON TABLE payments.simulated_attempt IS
    'What a direct-provider simulator returned (FR-PAY-015). A real record of a real call '
    'to a thing that is not contracted. It carries simulated_outcome and no live_outcome '
    'column exists here, so the row cannot be mistaken for a provider result even by '
    'something reading it carelessly.';

CREATE FUNCTION payments.invoke_direct_provider(
    p_tenant_id  uuid,
    p_outlet_id  uuid,
    p_provider   payments.provider,
    p_currency_code char(3),
    p_amount_minor  money.amount_minor,
    p_actor_user_id uuid DEFAULT NULL
) RETURNS payments.simulated_outcome
LANGUAGE plpgsql
AS $$
DECLARE
    v_adapter payments.payment_adapter%ROWTYPE;
    v_result  payments.simulated_outcome;
BEGIN
    SELECT * INTO v_adapter FROM payments.payment_adapter
     WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id AND provider = p_provider;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'PAYMENT_ADAPTER_NOT_REGISTERED: no % adapter for this outlet', p_provider
            USING ERRCODE = 'HS404';
    END IF;

    -- The function is named for what it does and refuses everything else. Cash, a
    -- terminal result and a verified proof are RECORDED — somebody in the room did
    -- something and we write down what happened. Only a direct API is INVOKED, and
    -- every direct API is simulated by the constraint above. So this branch is not
    -- defensive: it is the sentence "we do not call live providers" made executable.
    IF v_adapter.mode <> 'simulated' THEN
        RAISE EXCEPTION
            'UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM: % is a live adapter and live payment '
            'is RECORDED, never invoked. Cash is counted, a terminal prints its own '
            'result and a proof is verified by a person in the provider''s application. '
            'A live provider call from this system would be a claim about a contract that '
            'does not exist', p_provider
            USING ERRCODE = 'HS501';
    END IF;

    IF NOT v_adapter.active THEN
        RAISE EXCEPTION
            'PAYMENT_ADAPTER_INACTIVE: the % adapter is switched off for this outlet',
            p_provider USING ERRCODE = 'HS409';
    END IF;

    -- The simulation itself. Deterministic on the amount so a test can ask for either
    -- answer, and stated here rather than hidden behind a configuration flag that would
    -- become the thing somebody points at when asking whether this is really simulated.
    v_result := CASE WHEN p_amount_minor % 2 = 0
                     THEN 'approved'::payments.simulated_outcome
                     ELSE 'declined'::payments.simulated_outcome END;

    INSERT INTO payments.simulated_attempt
        (tenant_id, outlet_id, adapter_id, adapter_mode, currency_code, amount_minor,
         result, requested_by_user_id)
    VALUES (p_tenant_id, p_outlet_id, v_adapter.id, v_adapter.mode, p_currency_code,
            p_amount_minor, v_result, p_actor_user_id);

    RETURN v_result;
END;
$$;

COMMENT ON FUNCTION payments.invoke_direct_provider IS
    'The simulated path, callable (FR-PAY-015). It exists so NC-M4-003 can attempt the '
    'forbidden write through a real code path rather than against a table, and so the '
    'registry has something on the far side of the boundary. It returns '
    'simulated_outcome, which no live column accepts, and refuses to be pointed at a '
    'live adapter at all.';


-- ===========================================================================
-- The PCI boundary (FR-PAY-016)
-- ===========================================================================
-- "Keep raw PAN, CVV and card cryptograms outside platform storage, logs and analytics."
--
-- M1-D proved log redaction by planting a secret and asserting zero occurrences. M3-C
-- made payload bounds a CHECK so that absence was a property of the table rather than of
-- the code that filled it. The stronger of the two is the second, so this is that — and
-- it is deliberately GENERIC rather than a list of columns.
--
-- The trigger walks every string value in the row through to_jsonb() instead of naming
-- fields. A column added to a terminal result at M4-C is covered the moment it exists,
-- without anybody remembering to extend anything, which is the same reason M4-A
-- enumerated balance functions from the catalog rather than from a list. A card number in
-- a log is a breach rather than a bug, and a check that only guards the columns somebody
-- thought of on the day is a check that guards yesterday's schema.

CREATE FUNCTION payments.looks_like_card_data(p_value text)
RETURNS boolean
LANGUAGE sql IMMUTABLE
AS $$
    -- A UUID IS NOT A CARD NUMBER, and saying so is the first thing this does.
    --
    -- Every row in this schema carries several, and the ledger's jsonb payloads carry
    -- them by the dozen. A universally unique identifier is hexadecimal in groups
    -- separated by hyphens, which is exactly the shape of a primary account number
    -- somebody typed with spacing — '11111111-2222-3333-4444-555555555555' satisfies
    -- "thirteen to nineteen digits with separators" without being anything of the kind.
    -- The first version of this function refused every payment whose identifiers happened
    -- to be digit-heavy, which is a false positive that would have been read as the
    -- boundary working.
    --
    -- Removing them first is a statement about the VALUE rather than an exemption for a
    -- column: a canonical UUID is not card data, and a card number cannot be written in
    -- UUID form. A sixteen-digit run with no separators still matches, and so does one
    -- grouped in fours the way a card is printed.
    WITH stripped AS (
        SELECT regexp_replace(
                   coalesce(p_value, ''),
                   '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
                   '[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', ' ', 'g') AS v)
    SELECT p_value IS NOT NULL
       AND (
            -- A primary account number: thirteen to nineteen digits, allowing the spaces
            -- and hyphens a person types. Bounded on both sides so an ordinary long
            -- identifier of eight or ten digits does not fire.
            (SELECT v FROM stripped) ~ '(^|[^0-9])([0-9][ -]?){13,19}($|[^0-9])'
            -- A cryptogram or track blob: a long unbroken run of hexadecimal. Sixteen is
            -- the shortest ARQC anybody ships.
         OR (SELECT v FROM stripped) ~* '(^|[^0-9a-fA-F])[0-9a-fA-F]{16,}($|[^0-9a-fA-F])'
       );
$$;

COMMENT ON FUNCTION payments.looks_like_card_data(text) IS
    'FR-PAY-016. Whether a string looks like a primary account number or a card '
    'cryptogram. Used by a generic trigger over every string in a row rather than by '
    'per-column constraints, so a column added later is covered without anybody '
    'extending anything.';

CREATE FUNCTION payments.refuse_card_data() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_key   text;
    v_value text;
BEGIN
    -- Only the columns that could HOLD a card number are examined, and which those are
    -- is read from the catalog for this table rather than listed. A uuid, a timestamp or
    -- a bigint cannot carry a primary account number because its type already refuses
    -- one, and scanning them was not merely wasteful: a uuid rendered as text is a run of
    -- hexadecimal digits and hyphens, which is exactly what a card number looks like.
    -- The first version of this trigger refused every insert in the schema for that
    -- reason. The fix is the narrower question — which columns are textual — asked of
    -- pg_attribute, so a text column added at M4-C is covered the moment it exists and a
    -- uuid column added beside it is not mistaken for a card.
    FOR v_key, v_value IN
        SELECT j.key, j.value
          FROM jsonb_each_text(to_jsonb(NEW)) j
          JOIN pg_attribute a ON a.attrelid = TG_RELID AND a.attname = j.key
          JOIN pg_type t ON t.oid = a.atttypid
         WHERE a.attnum > 0 AND NOT a.attisdropped
           AND t.typname IN ('text', 'varchar', 'bpchar', 'name', 'json', 'jsonb')
    LOOP
        IF payments.looks_like_card_data(v_value) THEN
            -- The diagnostic names the COLUMN and never the value. Reporting what was
            -- refused would put the card number in the error text, and FR-SEC-007 counts
            -- error text as a place a secret must not be.
            RAISE EXCEPTION
                'CARD_DATA_RETAINED: %.%.% was given a value shaped like a primary '
                'account number or a card cryptogram. This platform records what a '
                'terminal DID — a scheme, a masked tail, an approval code — and never '
                'what the card is. The value is not repeated here because an error '
                'message is a log',
                TG_TABLE_SCHEMA, TG_TABLE_NAME, v_key
                USING ERRCODE = 'HS422';
        END IF;
    END LOOP;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION payments.refuse_card_data() IS
    'FR-PAY-016, at the write. Attached to every table in payments that can hold text a '
    'terminal or an operator supplied. tests/m4b asserts from the catalog that the set of '
    'tables carrying this trigger equals the set of tables with a text-typed column, so a '
    'table added later without it fails the build.';


-- ===========================================================================
-- The payment intent (FR-PAY-001)
-- ===========================================================================

CREATE TABLE payments.payment_intent (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL,
    outlet_id    uuid NOT NULL,

    -- For a specific check balance and payer. The bill is the document that states what
    -- is owed; the share is the payer, when the party has split. A NULL share is the
    -- whole bill being paid by one person, which is the ordinary case.
    bill_id       uuid NOT NULL,
    bill_share_id uuid,
    -- Which tip, when there is one. Named rather than looked up: FR-PAY-001 says the
    -- intent carries a separate optional tip allocation, and an intent that found the tip
    -- by searching would allocate to whichever tip existed at capture time rather than to
    -- the one the payer agreed to.
    tip_id        uuid,

    currency_code char(3) NOT NULL,
    -- The two allocations the intent carries. SEPARATE columns, never a total that is
    -- divided later: FR-PAY-017 says a payment records separate allocations to bill
    -- balance and to optional tip, and an intent that carried one number would make the
    -- split a decision taken after the payer had agreed to something else.
    bill_amount_minor money.amount_minor NOT NULL,
    tip_amount_minor  money.amount_minor NOT NULL DEFAULT 0,

    -- FR-PAY-001's permitted tender methods, as an array of providers rather than free
    -- text, so an intent cannot permit something that is not an adapter.
    permitted_providers payments.provider[] NOT NULL,

    idempotency_key text NOT NULL,
    expires_at      timestamptz NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    created_by_user_id uuid NOT NULL,

    CONSTRAINT payment_intent_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT payment_intent_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT payment_intent_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT payment_intent_actor_fk FOREIGN KEY (tenant_id, created_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,

    -- FR-PAY-012. One key, one intent, for ever. A retry presents the same key and gets
    -- the same intent back rather than a second one, which is how "retry without
    -- duplicating the order or payment" is made true rather than attempted.
    CONSTRAINT payment_intent_idempotent UNIQUE (tenant_id, idempotency_key),

    CONSTRAINT payment_intent_bill_amount_not_negative CHECK (bill_amount_minor >= 0),
    CONSTRAINT payment_intent_tip_amount_not_negative CHECK (tip_amount_minor >= 0),
    CONSTRAINT payment_intent_pays_for_something CHECK (
        bill_amount_minor > 0 OR tip_amount_minor > 0),
    -- A tip amount needs a tip to be allocated to, and a named tip needs an amount. The
    -- two halves of "separate optional tip allocation" arrive together or not at all.
    CONSTRAINT payment_intent_tip_amount_names_a_tip CHECK (
        (tip_amount_minor = 0 AND tip_id IS NULL)
     OR (tip_amount_minor > 0 AND tip_id IS NOT NULL)),
    CONSTRAINT payment_intent_permits_a_method CHECK (
        array_length(permitted_providers, 1) >= 1),
    CONSTRAINT payment_intent_expires CHECK (expires_at > created_at)

    -- NO FOREIGN KEY ONTO billing.bill OR billing.bill_share. Both are projections
    -- folded from billing.bill_event, and a rebuild deletes projections wholesale before
    -- replaying. M3-D's rule — nothing durable may hold a foreign key into a projection —
    -- and 0019 removed three of these for the same reason after a rebuild failed on one.
    -- The bill's existence is checked by the writer and asserted by tests/m4b from the
    -- catalog, which is where that rule is enforced for every slice rather than here.
);

COMMENT ON TABLE payments.payment_intent IS
    'FR-PAY-001. What a specific payer is about to pay, for a specific bill balance, with '
    'the tip kept as its own figure from the first record onward. Idempotent by unique '
    'key so FR-PAY-012''s retry cannot produce a second one, and expiring so an '
    'abandoned intent does not authorize a payment tomorrow.';

CREATE INDEX payment_intent_bill_idx
    ON payments.payment_intent (tenant_id, bill_id);

CREATE TRIGGER payment_intent_holds_no_card_data
    BEFORE INSERT OR UPDATE ON payments.payment_intent
    FOR EACH ROW EXECUTE FUNCTION payments.refuse_card_data();


-- ===========================================================================
-- Proof-based mobile money (FR-PAY-014, FR-PAY-015)
-- ===========================================================================
-- "Staff verifies receipt in the provider application, records the actual provider and
-- masked/reference identifier, and leaves unverified proof PENDING rather than paid."
--
-- A human confirming a real transaction and then attesting to it, which makes the
-- attestation itself the audited artifact. So the record is built around the attestation
-- rather than around the money: who verified, what they saw, and when. A verification
-- that cannot be attributed is not a verification, and that sentence is a constraint here
-- rather than a convention.

CREATE TYPE payments.proof_state AS ENUM ('pending', 'verified', 'rejected');

CREATE TABLE payments.proof_confirmation (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,
    provider   payments.provider NOT NULL,
    state      payments.proof_state NOT NULL DEFAULT 'pending',

    currency_code char(3) NOT NULL,
    amount_minor  money.amount_minor NOT NULL,

    -- What the guest showed. A reference, never a credential: FR-SEC-007 and FR-PAY-016
    -- both apply, and the card-data trigger below covers every string on the row.
    provider_reference text NOT NULL,
    masked_identifier  text,

    -- THE ATTESTATION. All four are NULL until somebody verifies, and all four are
    -- required the moment they do — see the CHECK. The SESSION is here as well as the
    -- user for the reason M3-D gave about overrides: a person is who their live session
    -- says they are, and a name typed into a form is not an identity.
    verified_by_user_id    uuid,
    verified_by_session_id uuid,
    verified_at            timestamptz,
    what_the_verifier_saw  text,

    raised_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT proof_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT proof_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT proof_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT proof_verifier_fk FOREIGN KEY (tenant_id, verified_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT proof_verifier_session_fk FOREIGN KEY (tenant_id, verified_by_session_id)
        REFERENCES identity.session (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT proof_amount_positive CHECK (amount_minor > 0),
    CONSTRAINT proof_reference_not_blank CHECK (btrim(provider_reference) <> ''),

    -- Only the two providers the package names take proof. A proof confirmation against
    -- 'cash' would be somebody attesting to having seen their own till.
    CONSTRAINT proof_provider_is_proof_based CHECK (
        provider IN ('telebirr_proof', 'cbe_birr_proof')),

    -- A VERIFICATION THAT CANNOT BE ATTRIBUTED IS NOT A VERIFICATION. Every part of the
    -- attestation arrives together or the row is not verified. This is the constraint
    -- NC-M4-003's first half plants against and the one the "verification without
    -- attributor" break must fail on.
    CONSTRAINT proof_verified_is_attributed CHECK (
        state <> 'verified' OR (
            verified_by_user_id IS NOT NULL
            AND verified_by_session_id IS NOT NULL
            AND verified_at IS NOT NULL
            AND btrim(coalesce(what_the_verifier_saw, '')) <> '')),

    -- And the converse: a pending or rejected proof carries no attestation, so a row
    -- cannot be quietly pre-loaded with a verifier and then flipped.
    CONSTRAINT proof_unverified_carries_no_attestation CHECK (
        state = 'verified' OR (
            verified_by_user_id IS NULL AND verified_by_session_id IS NULL
            AND verified_at IS NULL AND what_the_verifier_saw IS NULL)),

    -- The identity a payment points at includes the state, so an allocation's foreign
    -- key can pin "this proof was verified" rather than reading it and hoping.
    CONSTRAINT proof_identity_includes_state UNIQUE (id, state)
);

COMMENT ON TABLE payments.proof_confirmation IS
    'FR-PAY-014 and FR-PAY-015. A member of staff opened Telebirr or CBE Birr, saw a '
    'receipt, and said so. The attestation is the artifact: who, what they saw, and when, '
    'all four required together by CHECK. An unverified proof stays pending and cannot '
    'settle anything, because payments.assert_allocation_is_earned() reads the state '
    'through a foreign key that pins it.';

CREATE TRIGGER proof_holds_no_card_data
    BEFORE INSERT OR UPDATE ON payments.proof_confirmation
    FOR EACH ROW EXECUTE FUNCTION payments.refuse_card_data();


-- ===========================================================================
-- The external terminal's result (FR-PAY-003, FR-PAY-016)
-- ===========================================================================
-- We record what a terminal did. We are not a terminal. Every column below is something
-- printed on a merchant slip, and there is no column for anything that is not.

CREATE TABLE payments.terminal_result (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,

    terminal_reference text NOT NULL,
    scheme             text NOT NULL,
    masked_tail        text,
    approval_code      text,
    outcome            payments.live_outcome NOT NULL,

    currency_code char(3) NOT NULL,
    amount_minor  money.amount_minor NOT NULL,

    recorded_by_user_id uuid NOT NULL,
    recorded_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT terminal_result_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT terminal_result_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT terminal_result_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT terminal_result_actor_fk FOREIGN KEY (tenant_id, recorded_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT terminal_result_amount_positive CHECK (amount_minor > 0),
    CONSTRAINT terminal_result_scheme_not_blank CHECK (btrim(scheme) <> ''),

    -- A masked tail is at most the last four digits, and nothing else is storable. The
    -- generic card-data trigger would already refuse a full number here; this says the
    -- narrower thing as well, because two locks that can each fail closed are the
    -- arrangement this repository uses everywhere the consequence is serious.
    CONSTRAINT terminal_result_tail_is_at_most_four_digits CHECK (
        masked_tail IS NULL OR masked_tail ~ '^[0-9]{4}$'),
    CONSTRAINT terminal_result_approval_code_is_short CHECK (
        approval_code IS NULL OR approval_code ~ '^[A-Za-z0-9]{1,12}$')
);

COMMENT ON TABLE payments.terminal_result IS
    'FR-PAY-003. What an external card terminal reported, recorded by the person who read '
    'it off the slip. There is no column for a primary account number, a verification '
    'value or a cryptogram, and payments.refuse_card_data() walks every string on the row '
    'in case a later column forgets. During an outage this method stays available exactly '
    'when the terminal itself can complete the payment, which is a fact about the '
    'terminal and is why the record is of a RESULT rather than of a request.';

CREATE TRIGGER terminal_result_holds_no_card_data
    BEFORE INSERT OR UPDATE ON payments.terminal_result
    FOR EACH ROW EXECUTE FUNCTION payments.refuse_card_data();


-- ===========================================================================
-- The ledger (FR-DAT-008B)
-- ===========================================================================

CREATE TYPE payments.payment_event_kind AS ENUM ('captured', 'reversed');

CREATE TABLE payments.payment_event (
    id              bigserial PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    payment_id      uuid NOT NULL,
    sequence_number integer NOT NULL,
    kind            payments.payment_event_kind NOT NULL,
    occurred_at     timestamptz NOT NULL DEFAULT now(),

    actor_user_id   uuid,
    override_id     uuid,
    reason_code_id  uuid,
    reason_text     text,

    before          jsonb,
    after           jsonb,
    correlation_id  uuid,

    CONSTRAINT payment_event_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT payment_event_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT payment_event_actor_fk FOREIGN KEY (tenant_id, actor_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT payment_event_override_fk FOREIGN KEY (tenant_id, override_id)
        REFERENCES pos.override_approval (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT payment_event_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT payment_event_sequence_positive CHECK (sequence_number >= 1),
    CONSTRAINT payment_event_sequence_unique UNIQUE (tenant_id, payment_id, sequence_number),

    -- FR-PAY-009. Money going back says why and who let it. A reversal with no reason is
    -- a refund nobody can answer a question about six weeks later.
    CONSTRAINT payment_event_reversal_states_a_reason CHECK (
        kind <> 'reversed'
        OR (reason_code_id IS NOT NULL AND btrim(coalesce(reason_text, '')) <> ''))
);

COMMENT ON TABLE payments.payment_event IS
    'FR-DAT-008B. Everything that happened to a payment, append-only by trigger and by '
    'grant. The projections below are folded from it, so a correction is another event '
    'rather than an edit and a rebuild reproduces every figure.';

CREATE FUNCTION payments.refuse_ledger_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'PAYMENT_DELETED_NOT_REVERSED: payments.payment_event is append-only. Money that '
        'arrived is returned by a reversal naming who authorized it and why — a separate '
        'linked record, which is what FR-PAY-009 asks for. Removing the row instead is '
        'how a payment somebody made stops having happened'
        USING ERRCODE = 'HS409';
END;
$$;

CREATE TRIGGER payment_event_append_only
    BEFORE UPDATE OR DELETE ON payments.payment_event
    FOR EACH ROW EXECUTE FUNCTION payments.refuse_ledger_mutation();

-- AND THE LEDGER IS GUARDED TOO. This was the one table in the schema the card-data
-- trigger did not cover, and it is the widest hole of the lot: `before` and `after` are
-- jsonb, so a writer that recorded a terminal's whole response would put a card number
-- here rather than in any column anybody thought to constrain. tests/m4b enumerates the
-- tables with textual columns from the catalog and requires each to carry this trigger,
-- which is how the gap was found.
CREATE TRIGGER payment_event_holds_no_card_data
    BEFORE INSERT OR UPDATE ON payments.payment_event
    FOR EACH ROW EXECUTE FUNCTION payments.refuse_card_data();


-- ===========================================================================
-- The payment (projection)
-- ===========================================================================

CREATE TYPE payments.payment_state AS ENUM ('captured', 'reversed');

CREATE TABLE payments.payment (
    id         uuid PRIMARY KEY,
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,
    intent_id  uuid NOT NULL,

    adapter_id   uuid NOT NULL,
    adapter_mode payments.adapter_mode NOT NULL,
    provider     payments.provider NOT NULL,

    -- THE LIVE OUTCOME COLUMN. Typed payments.live_outcome, which no simulator can
    -- produce: payments.invoke_direct_provider() returns simulated_outcome, and the two
    -- are different types between which PostgreSQL performs no conversion. The CHECK
    -- below then says the other half out loud — a simulated payment has no outcome at
    -- all, rather than an outcome that happens to be marked.
    outcome payments.live_outcome,

    state payments.payment_state NOT NULL,

    currency_code  char(3) NOT NULL,
    -- What the payer handed over, and what came back. Both STORED. FR-PAY-002 wants
    -- change as a recorded figure and FR-PAY-017 forbids hidden recomputation; a change
    -- amount derived at read time from today's bill total would disagree with the note
    -- in the drawer the moment the bill was reissued.
    tendered_minor money.amount_minor NOT NULL,
    change_minor   money.amount_minor NOT NULL DEFAULT 0,

    -- The evidence, according to which world the payment came from. Exactly one of these
    -- is set for the providers that have one, by CHECK.
    proof_id           uuid,
    proof_state        payments.proof_state,
    terminal_result_id uuid,

    captured_by_user_id uuid NOT NULL,
    captured_at         timestamptz NOT NULL,
    correlation_id      uuid,
    ledger_sequence     integer NOT NULL,

    CONSTRAINT payment_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT payment_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT payment_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT payment_actor_fk FOREIGN KEY (tenant_id, captured_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT payment_intent_fk FOREIGN KEY (tenant_id, intent_id)
        REFERENCES payments.payment_intent (tenant_id, id) ON DELETE RESTRICT,

    -- The adapter's identity INCLUDES its mode, so the payment cannot name an adapter and
    -- then disagree with it about which world it is in.
    CONSTRAINT payment_adapter_fk FOREIGN KEY (adapter_id, adapter_mode)
        REFERENCES payments.payment_adapter (id, mode) ON DELETE RESTRICT,

    -- And the proof's identity includes its STATE, so a payment that names a proof
    -- carries that proof's verification status as a fact rather than as a lookup. This is
    -- what makes payments.assert_allocation_is_earned() a foreign-key question instead of
    -- a race against somebody else's UPDATE.
    CONSTRAINT payment_proof_fk FOREIGN KEY (proof_id, proof_state)
        REFERENCES payments.proof_confirmation (id, state) ON DELETE RESTRICT,
    CONSTRAINT payment_terminal_result_fk FOREIGN KEY (tenant_id, terminal_result_id)
        REFERENCES payments.terminal_result (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT payment_tendered_positive CHECK (tendered_minor > 0),
    CONSTRAINT payment_change_not_negative CHECK (change_minor >= 0),
    CONSTRAINT payment_ledger_sequence_positive CHECK (ledger_sequence >= 1),

    -- A SIMULATED PAYMENT HAS NO OUTCOME. Not a null flag and not a marked one: the
    -- column that records what a live provider did is empty, and the simulator's answer
    -- lives on payments.simulated_attempt in a type this column cannot hold.
    CONSTRAINT payment_live_outcome_only_when_live CHECK (
        (adapter_mode = 'live' AND outcome IS NOT NULL)
     OR (adapter_mode = 'simulated' AND outcome IS NULL)),

    -- Each world brings its own evidence, and brings no other world's.
    CONSTRAINT payment_evidence_matches_the_provider CHECK (
        CASE provider
            WHEN 'cash' THEN proof_id IS NULL AND terminal_result_id IS NULL
            WHEN 'external_terminal' THEN proof_id IS NULL AND terminal_result_id IS NOT NULL
            WHEN 'telebirr_proof' THEN proof_id IS NOT NULL AND terminal_result_id IS NULL
            WHEN 'cbe_birr_proof' THEN proof_id IS NOT NULL AND terminal_result_id IS NULL
            ELSE proof_id IS NULL AND terminal_result_id IS NULL
        END),

    -- Change is a cash idea. A terminal or a mobile-money transfer that gave change back
    -- would be a transfer nobody can reconcile.
    CONSTRAINT payment_change_is_cash_only CHECK (
        change_minor = 0 OR provider = 'cash')
);

COMMENT ON TABLE payments.payment IS
    'FR-PAY-002, FR-PAY-003, FR-PAY-014. One tender: what arrived, through which adapter, '
    'with which evidence. The figures are STORED — FR-PAY-017 forbids hidden '
    'recomputation, and a payment whose amounts were derived at read time would follow '
    'the bill rather than the drawer. Folded from payments.payment_event and written by '
    'payments.apply_event() alone.';

COMMENT ON COLUMN payments.payment.outcome IS
    'What a LIVE adapter reported. Typed payments.live_outcome, a type no simulator can '
    'produce a value of. NULL exactly when the adapter is simulated, by CHECK — so '
    'NC-M4-003''s claim has neither a column to be written into nor a flag to be flipped.';

CREATE INDEX payment_intent_lookup_idx ON payments.payment (tenant_id, intent_id);

CREATE TRIGGER payment_holds_no_card_data
    BEFORE INSERT OR UPDATE ON payments.payment
    FOR EACH ROW EXECUTE FUNCTION payments.refuse_card_data();


-- ===========================================================================
-- Dual allocation (FR-PAY-017, FR-PAY-006, FR-PAY-007)
-- ===========================================================================
-- "Separate allocations to bill balance and optional tip, with exact arithmetic,
-- independent reversal and no hidden recomputation."
--
-- Separate ROWS rather than two columns, and that is what buys independent reversal:
-- FR-PAY-009 refunds a bill payment and a tip payment through separate linked records,
-- which is only expressible if there are two things to link to.

CREATE TYPE payments.allocation_target AS ENUM ('bill_balance', 'tip');

CREATE TABLE payments.allocation (
    id         uuid PRIMARY KEY,
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,
    payment_id uuid NOT NULL,
    target     payments.allocation_target NOT NULL,

    -- What it was allocated TO. A bill for the balance half, a tip record for the other.
    -- Both are carried as plain ids: billing.bill is a projection and billing.tip is
    -- durable, and a uniform treatment here keeps the rebuild rule easy to state.
    bill_id uuid,
    tip_id  uuid,

    currency_code char(3) NOT NULL,
    amount_minor  money.amount_minor NOT NULL,
    allocated_at  timestamptz NOT NULL,

    CONSTRAINT allocation_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT allocation_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT allocation_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT allocation_payment_fk FOREIGN KEY (tenant_id, payment_id)
        REFERENCES payments.payment (tenant_id, id) ON DELETE CASCADE,

    CONSTRAINT allocation_amount_positive CHECK (amount_minor > 0),
    CONSTRAINT allocation_subject_matches_target CHECK (
        (target = 'bill_balance' AND bill_id IS NOT NULL AND tip_id IS NULL)
     OR (target = 'tip'          AND tip_id  IS NOT NULL AND bill_id IS NULL)),

    -- One payment allocates to a bill once and to a tip once. A payment with two bill
    -- allocations is two payments wearing one id, and the reconciliation below would have
    -- to guess which one a reversal meant.
    CONSTRAINT allocation_one_per_target UNIQUE (payment_id, target)

    -- NO FOREIGN KEY ONTO billing.bill. It is a projection; M3-D's rule holds.
);

COMMENT ON TABLE payments.allocation IS
    'FR-PAY-017. Where one payment went: some to the bill balance, some to a tip, as '
    'separate rows so each can be reversed without the other. The amount is what was '
    'allocated AT CAPTURE and is never recalculated — payments.allocation_view() returns '
    'this column, and tests/m4b proves from the catalog that no function in this schema '
    'derives an allocation figure from a bill instead of reading it.';

CREATE INDEX allocation_bill_idx ON payments.allocation (tenant_id, bill_id)
    WHERE bill_id IS NOT NULL;
CREATE INDEX allocation_tip_idx ON payments.allocation (tenant_id, tip_id)
    WHERE tip_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- LOCK THREE: an allocation must be earned (NC-M4-003)
-- ---------------------------------------------------------------------------
-- An allocation is the row that reduces what a guest owes. Everything above makes a
-- simulated result unrepresentable as a live one; this makes it unusable even if it
-- somehow were. Three conditions, each read from the payment's OWN columns — which are
-- pinned to the adapter and the proof by foreign keys onto identities that include their
-- mode and their state, so none of this is a lookup that could race an UPDATE.

CREATE FUNCTION payments.assert_allocation_is_earned() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    p payments.payment%ROWTYPE;
BEGIN
    SELECT * INTO p FROM payments.payment
     WHERE tenant_id = NEW.tenant_id AND id = NEW.payment_id;

    IF NOT FOUND THEN
        -- Not defensive: the cascade below means a deleted payment takes its allocations
        -- with it, so reaching here means an allocation was written for a payment that
        -- never folded.
        RAISE EXCEPTION
            'PAYMENT_NOT_FOUND: allocation % names payment %, which does not exist',
            NEW.id, NEW.payment_id USING ERRCODE = 'HS404';
    END IF;

    IF p.adapter_mode <> 'live' THEN
        RAISE EXCEPTION
            'UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM: payment % was taken through the % '
            'adapter, which is simulated. A simulated result cannot reduce what a guest '
            'owes, cannot pay a tip, and cannot support a live pilot-readiness claim '
            '(FR-PAY-015). Nothing was received',
            p.id, p.provider USING ERRCODE = 'HS409';
    END IF;

    IF p.outcome <> 'approved' THEN
        RAISE EXCEPTION
            'UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM: payment % came back % and a declined '
            'payment allocates nothing', p.id, p.outcome
            USING ERRCODE = 'HS409';
    END IF;

    -- FR-PAY-014's sharp end. An unverified proof stays PENDING rather than paid, and
    -- pending is the state the payment carries through a foreign key onto
    -- (proof id, proof state) — so this cannot be made true by verifying the proof after
    -- the allocation, either: the payment's own row would still say pending.
    IF p.provider IN ('telebirr_proof', 'cbe_birr_proof')
       AND coalesce(p.proof_state, 'pending') <> 'verified' THEN
        RAISE EXCEPTION
            'UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM: payment % rests on a % proof that is '
            '%, not verified. Somebody must open the provider''s application, see the '
            'receipt and say so before the money is treated as received',
            p.id, p.provider, coalesce(p.proof_state::text, 'absent')
            USING ERRCODE = 'HS409';
    END IF;

    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER allocation_is_earned
    AFTER INSERT OR UPDATE ON payments.allocation
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION payments.assert_allocation_is_earned();

COMMENT ON FUNCTION payments.assert_allocation_is_earned() IS
    'NC-M4-003, at the write rather than at the route. A route check is bypassed by the '
    'next caller to appear; this one is not, and it is the third of three independent '
    'locks — the mode is derived from the provider by CHECK, the two worlds are two '
    'types, and an allocation whose payment is simulated, declined or resting on an '
    'unverified proof is refused here even if the first two were removed.';


-- ---------------------------------------------------------------------------
-- Exact arithmetic (FR-PAY-002, FR-PAY-017)
-- ---------------------------------------------------------------------------

CREATE FUNCTION payments.assert_tender_is_fully_accounted() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_payment uuid := coalesce(NEW.payment_id, OLD.payment_id);
    v_tenant  uuid := coalesce(NEW.tenant_id, OLD.tenant_id);
    p         payments.payment%ROWTYPE;
    v_sum     bigint;
BEGIN
    SELECT * INTO p FROM payments.payment
     WHERE tenant_id = v_tenant AND id = v_payment;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    SELECT coalesce(sum(amount_minor), 0) INTO v_sum
      FROM payments.allocation
     WHERE tenant_id = v_tenant AND payment_id = v_payment;

    IF v_sum + p.change_minor <> p.tendered_minor THEN
        RAISE EXCEPTION
            'PAYMENT_TENDER_NOT_FULLY_ALLOCATED: payment % was tendered %, allocated % '
            'and gave % in change, which leaves % unaccounted for. Money that arrived '
            'and went nowhere is the difference a cash count finds at midnight',
            v_payment, p.tendered_minor, v_sum, p.change_minor,
            p.tendered_minor - v_sum - p.change_minor
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER tender_is_fully_accounted
    AFTER INSERT OR UPDATE OR DELETE ON payments.allocation
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION payments.assert_tender_is_fully_accounted();


-- ===========================================================================
-- Reversal (FR-PAY-009, FR-PAY-010A, NC-M4-004)
-- ===========================================================================
-- One reversal reverses ONE allocation. That is what "separate linked reversal records"
-- buys: a tip refunded without touching the bill payment, and a bill payment refunded
-- without clawing back a tip somebody has already been given.

CREATE TYPE payments.reversal_kind AS ENUM ('refund', 'reversal', 'correction');

CREATE TABLE payments.reversal (
    id            uuid PRIMARY KEY,
    tenant_id     uuid NOT NULL,
    outlet_id     uuid NOT NULL,
    allocation_id uuid NOT NULL,
    kind          payments.reversal_kind NOT NULL,

    currency_code char(3) NOT NULL,
    amount_minor  money.amount_minor NOT NULL,

    -- FR-PAY-009's three named requirements. The override is NULL below the configured
    -- threshold and required above it; payments.assert_reversal_is_authorized() decides
    -- which, from config.policy rather than from a literal here.
    override_id    uuid,
    reason_code_id uuid NOT NULL,
    reason_text    text NOT NULL,

    actor_user_id uuid NOT NULL,
    reversed_at   timestamptz NOT NULL,
    ledger_sequence integer NOT NULL,

    CONSTRAINT reversal_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT reversal_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT reversal_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT reversal_allocation_fk FOREIGN KEY (tenant_id, allocation_id)
        REFERENCES payments.allocation (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT reversal_actor_fk FOREIGN KEY (tenant_id, actor_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT reversal_override_fk FOREIGN KEY (tenant_id, override_id)
        REFERENCES pos.override_approval (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT reversal_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT reversal_amount_positive CHECK (amount_minor > 0),
    CONSTRAINT reversal_reason_not_blank CHECK (btrim(reason_text) <> ''),

    -- One override authorizes one reversal. pos.override_approval already refuses a
    -- second use of a step-up grant; this refuses a second use of the approval itself,
    -- which is the same defect one level up.
    CONSTRAINT reversal_override_used_once UNIQUE (override_id)
);

COMMENT ON TABLE payments.reversal IS
    'FR-PAY-009. Money going back, against ONE allocation, so a tip and a bill payment '
    'are refunded independently. Permissions, reason code and approval threshold are all '
    'required; the threshold is read from config.policy, and the approval reuses M3-D''s '
    'override, whose approver is derived from the approving session rather than supplied.';

CREATE INDEX reversal_allocation_idx ON payments.reversal (tenant_id, allocation_id);

CREATE TRIGGER reversal_holds_no_card_data
    BEFORE INSERT OR UPDATE ON payments.reversal
    FOR EACH ROW EXECUTE FUNCTION payments.refuse_card_data();


CREATE FUNCTION payments.reversal_threshold_minor(p_tenant_id uuid, p_outlet_id uuid)
RETURNS money.amount_minor
LANGUAGE sql STABLE
AS $$
    -- The amount at or above which a refund needs somebody else's approval. Read from
    -- the outlet's refund policy; absent a policy, EVERY refund needs approval, because
    -- an unset threshold must not mean an unlimited one. Fail closed, as everywhere else.
    SELECT coalesce(
        (SELECT (p.payload ->> 'approval_threshold_minor')::bigint
           FROM config.policy p
          WHERE p.tenant_id = p_tenant_id
            AND p.category = 'refund'
            AND (p.outlet_id = p_outlet_id OR p.outlet_id IS NULL)
            AND p.payload ? 'approval_threshold_minor'
            AND p.effective_from <= now()
            AND (p.effective_to IS NULL OR p.effective_to > now())
          ORDER BY (p.outlet_id IS NULL), p.version DESC
          LIMIT 1),
        0)::money.amount_minor;
$$;

COMMENT ON FUNCTION payments.reversal_threshold_minor(uuid, uuid) IS
    'FR-PAY-009''s approval threshold, from the outlet''s refund policy. Zero when no '
    'policy states one, which makes every refund need approval rather than none — an '
    'unset limit is not an infinite limit.';

CREATE FUNCTION payments.assert_reversal_is_authorized() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_threshold bigint;
    v_override  pos.override_approval%ROWTYPE;
BEGIN
    v_threshold := payments.reversal_threshold_minor(NEW.tenant_id, NEW.outlet_id);

    IF NEW.amount_minor < v_threshold THEN
        RETURN NULL;                     -- below the threshold, one person may do it
    END IF;

    IF NEW.override_id IS NULL THEN
        RAISE EXCEPTION
            'SELF_APPROVAL_ACCEPTED: reversal % is % and this outlet requires approval at '
            '% or above, and none was recorded. A refund a cashier can grant themselves '
            'is the whole of what maker-checker exists to prevent',
            NEW.id, NEW.amount_minor, v_threshold
            USING ERRCODE = 'HS403';
    END IF;

    SELECT * INTO v_override FROM pos.override_approval
     WHERE tenant_id = NEW.tenant_id AND id = NEW.override_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'OVERRIDE_NOT_FOUND: no approval % in scope', NEW.override_id
            USING ERRCODE = 'HS404';
    END IF;

    -- THE LINK THAT MAKES IT MAKER-CHECKER RATHER THAN PAPERWORK. pos.override_approval
    -- already refuses an approver who is the actor, and refuses two sessions that are
    -- one — M3-D built that so credential sharing fails as a property of the schema. What
    -- it cannot know is whether the override belongs to THIS reversal by THIS person, and
    -- without that a cashier points at a manager's approval of somebody else's refund.
    IF v_override.actor_user_id <> NEW.actor_user_id THEN
        RAISE EXCEPTION
            'SELF_APPROVAL_ACCEPTED: approval % authorizes % to act, and the reversal is '
            'being made by %. An approval belongs to the person it was granted to',
            NEW.override_id, v_override.actor_user_id, NEW.actor_user_id
            USING ERRCODE = 'HS403';
    END IF;

    IF v_override.subject_kind <> 'payment_allocation'
       OR v_override.subject_id <> NEW.allocation_id THEN
        RAISE EXCEPTION
            'SELF_APPROVAL_ACCEPTED: approval % was granted for %:%, and this reversal is '
            'against allocation %. An approval for one refund is not an approval for the '
            'next one', NEW.override_id, v_override.subject_kind, v_override.subject_id,
            NEW.allocation_id
            USING ERRCODE = 'HS403';
    END IF;

    RETURN NULL;
END;
$$;

-- IMMEDIATE, not deferred, and the reason is about the answer an operator gets rather
-- than about correctness. A deferred constraint fires at COMMIT, and M1-D's
-- withSession() wraps a request in a transaction and turns anything the COMMIT throws
-- into a refused session — so a cashier attempting a refund they may not make would be
-- told "authentication required" instead of being told they need a manager. Nothing here
-- needs deferring: the override and the allocation both exist before the reversal that
-- names them.
CREATE CONSTRAINT TRIGGER reversal_is_authorized
    AFTER INSERT OR UPDATE ON payments.reversal
    FOR EACH ROW EXECUTE FUNCTION payments.assert_reversal_is_authorized();


-- FR-PAY-009. A reversal cannot return more than arrived. Deferred, and by census over
-- every reversal against the allocation rather than over this one, so three partial
-- refunds that together exceed the payment are refused as surely as one that does.
CREATE FUNCTION payments.assert_reversal_within_the_allocation() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_allocated bigint;
    v_reversed  bigint;
BEGIN
    SELECT amount_minor INTO v_allocated FROM payments.allocation
     WHERE tenant_id = NEW.tenant_id AND id = NEW.allocation_id;

    SELECT coalesce(sum(amount_minor), 0) INTO v_reversed FROM payments.reversal
     WHERE tenant_id = NEW.tenant_id AND allocation_id = NEW.allocation_id;

    IF v_reversed > v_allocated THEN
        RAISE EXCEPTION
            'REVERSAL_EXCEEDS_ALLOCATION: allocation % received % and % has been reversed '
            'against it', NEW.allocation_id, v_allocated, v_reversed
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NULL;
END;
$$;

-- Immediate for the same reason. The running total is a census over rows that already
-- exist, so each insert can be judged as it lands.
CREATE CONSTRAINT TRIGGER reversal_within_the_allocation
    AFTER INSERT OR UPDATE ON payments.reversal
    FOR EACH ROW EXECUTE FUNCTION payments.assert_reversal_within_the_allocation();


-- ===========================================================================
-- The fold (FR-DAT-008B, FR-DAT-010)
-- ===========================================================================
-- The arrangement ordering.apply_event() established at M3-A, billing copied at 0019 and
-- this copies again: the application role holds no write grant on a projection, and a
-- trigger refuses a write from anybody — the table owner included, under FORCE ROW LEVEL
-- SECURITY — outside the one function that sets the marker. Two locks, either of which
-- survives the other's removal.

CREATE FUNCTION payments.refuse_projection_write() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF coalesce(current_setting('payments.applying_event', true), '') <> 'yes' THEN
        RAISE EXCEPTION
            'PAYMENT_PROJECTION_WRITTEN_DIRECTLY: %.% is folded from '
            'payments.payment_event and may only be written inside a writer that has set '
            'payments.applying_event. A projection written behind its ledger is a '
            'projection a rebuild puts back',
            TG_TABLE_SCHEMA, TG_TABLE_NAME
            USING ERRCODE = 'HS409';
    END IF;
    RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER payment_written_only_by_the_fold
    BEFORE INSERT OR UPDATE OR DELETE ON payments.payment
    FOR EACH ROW EXECUTE FUNCTION payments.refuse_projection_write();

CREATE TRIGGER allocation_written_only_by_the_fold
    BEFORE INSERT OR UPDATE OR DELETE ON payments.allocation
    FOR EACH ROW EXECUTE FUNCTION payments.refuse_projection_write();

CREATE TRIGGER reversal_written_only_by_the_fold
    BEFORE INSERT OR UPDATE OR DELETE ON payments.reversal
    FOR EACH ROW EXECUTE FUNCTION payments.refuse_projection_write();


CREATE FUNCTION payments.append_event(
    p_tenant_id uuid, p_outlet_id uuid, p_payment_id uuid,
    p_kind payments.payment_event_kind,
    p_actor_user_id uuid DEFAULT NULL,
    p_override_id uuid DEFAULT NULL,
    p_reason_code_id uuid DEFAULT NULL,
    p_reason_text text DEFAULT NULL,
    p_before jsonb DEFAULT NULL,
    p_after jsonb DEFAULT NULL,
    p_correlation_id uuid DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_sequence integer;
    v_id       bigint;
BEGIN
    SELECT coalesce(max(sequence_number), 0) + 1 INTO v_sequence
      FROM payments.payment_event
     WHERE tenant_id = p_tenant_id AND payment_id = p_payment_id;

    INSERT INTO payments.payment_event
        (tenant_id, outlet_id, payment_id, sequence_number, kind, actor_user_id,
         override_id, reason_code_id, reason_text, before, after, correlation_id)
    VALUES (p_tenant_id, p_outlet_id, p_payment_id, v_sequence, p_kind, p_actor_user_id,
            p_override_id, p_reason_code_id, p_reason_text, p_before, p_after,
            p_correlation_id)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION payments.append_event IS
    'Appends one event and returns ITS ID. 0019''s note applies unchanged: the id is what '
    'the fold replays, and a rebuild walks events in the order they were APPENDED across '
    'every payment rather than within one.';


CREATE FUNCTION payments.apply_event(p_event_id bigint) RETURNS void
-- SECURITY DEFINER because it writes projections on which the application role holds no
-- write grant, which is the point of that revocation. Row level security stays FORCED and
-- its predicate reads the session context, which the definer switch does not change.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, payments, billing, ordering, config, money, identity, pos, public
AS $$
DECLARE
    e          payments.payment_event%ROWTYPE;
    v_after    jsonb;
    v_alloc    jsonb;
    v_reversed bigint;
    v_allocated bigint;
BEGIN
    SELECT * INTO e FROM payments.payment_event WHERE id = p_event_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LEDGER_EVENT_ABSENT: no payment event %', p_event_id
            USING ERRCODE = 'HS404';
    END IF;
    v_after := coalesce(e.after, '{}'::jsonb);

    PERFORM set_config('payments.applying_event', 'yes', true);

    IF e.kind = 'captured' THEN
        INSERT INTO payments.payment
            (id, tenant_id, outlet_id, intent_id, adapter_id, adapter_mode, provider,
             outcome, state, currency_code, tendered_minor, change_minor,
             proof_id, proof_state, terminal_result_id,
             captured_by_user_id, captured_at, correlation_id, ledger_sequence)
        VALUES (e.payment_id, e.tenant_id, e.outlet_id,
                (v_after ->> 'intent_id')::uuid,
                (v_after ->> 'adapter_id')::uuid,
                (v_after ->> 'adapter_mode')::payments.adapter_mode,
                (v_after ->> 'provider')::payments.provider,
                (v_after ->> 'outcome')::payments.live_outcome,
                'captured',
                (v_after ->> 'currency_code')::char(3),
                (v_after ->> 'tendered_minor')::bigint,
                (v_after ->> 'change_minor')::bigint,
                (v_after ->> 'proof_id')::uuid,
                (v_after ->> 'proof_state')::payments.proof_state,
                (v_after ->> 'terminal_result_id')::uuid,
                e.actor_user_id, e.occurred_at, e.correlation_id, e.sequence_number);

        FOR v_alloc IN
            SELECT jsonb_array_elements(coalesce(v_after -> 'allocations', '[]'::jsonb))
        LOOP
            INSERT INTO payments.allocation
                (id, tenant_id, outlet_id, payment_id, target, bill_id, tip_id,
                 currency_code, amount_minor, allocated_at)
            VALUES ((v_alloc ->> 'id')::uuid, e.tenant_id, e.outlet_id, e.payment_id,
                    (v_alloc ->> 'target')::payments.allocation_target,
                    (v_alloc ->> 'bill_id')::uuid,
                    (v_alloc ->> 'tip_id')::uuid,
                    (v_after ->> 'currency_code')::char(3),
                    (v_alloc ->> 'amount_minor')::bigint,
                    e.occurred_at);
        END LOOP;

        -- FR-INT-014. Linked by the FOLD, so a rebuild restores the chain rather than
        -- restoring everything except the chain — the lesson M3-B learned the hard way.
        IF e.correlation_id IS NOT NULL THEN
            PERFORM ordering.link_correlation_artifact(
                e.tenant_id, e.outlet_id, e.correlation_id, 'payment',
                e.payment_id, e.occurred_at);
        END IF;

    ELSIF e.kind = 'reversed' THEN
        INSERT INTO payments.reversal
            (id, tenant_id, outlet_id, allocation_id, kind, currency_code, amount_minor,
             override_id, reason_code_id, reason_text, actor_user_id, reversed_at,
             ledger_sequence)
        VALUES ((v_after ->> 'reversal_id')::uuid, e.tenant_id, e.outlet_id,
                (v_after ->> 'allocation_id')::uuid,
                (v_after ->> 'kind')::payments.reversal_kind,
                (v_after ->> 'currency_code')::char(3),
                (v_after ->> 'amount_minor')::bigint,
                e.override_id, e.reason_code_id, e.reason_text,
                e.actor_user_id, e.occurred_at, e.sequence_number);

        -- The payment becomes 'reversed' only when every minor unit that arrived has gone
        -- back. A partial refund leaves it captured, because it is: the guest still paid.
        SELECT coalesce(sum(a.amount_minor), 0) INTO v_allocated
          FROM payments.allocation a
         WHERE a.tenant_id = e.tenant_id AND a.payment_id = e.payment_id;
        SELECT coalesce(sum(r.amount_minor), 0) INTO v_reversed
          FROM payments.reversal r
          JOIN payments.allocation a ON a.tenant_id = r.tenant_id
                                    AND a.id = r.allocation_id
         WHERE r.tenant_id = e.tenant_id AND a.payment_id = e.payment_id;

        IF v_reversed >= v_allocated AND v_allocated > 0 THEN
            UPDATE payments.payment SET state = 'reversed'
             WHERE tenant_id = e.tenant_id AND id = e.payment_id;
        END IF;
    END IF;

    PERFORM set_config('payments.applying_event', '', true);
END;
$$;

COMMENT ON FUNCTION payments.apply_event(bigint) IS
    'The one writer of every payments projection (FR-DAT-010). Every figure the '
    'projection carries is in the event that produced it — the adapter and its mode, the '
    'outcome, what was tendered, what came back as change, and each allocation with its '
    'own id — so a rebuild reproduces the payment rather than an approximation of it.';


-- ===========================================================================
-- Writers
-- ===========================================================================

CREATE FUNCTION payments.create_intent(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_bill_id   uuid,
    p_idempotency_key text,
    p_bill_amount_minor money.amount_minor,
    p_actor_user_id uuid,
    p_tip_amount_minor money.amount_minor DEFAULT 0,
    p_tip_id uuid DEFAULT NULL,
    p_bill_share_id uuid DEFAULT NULL,
    p_permitted_providers payments.provider[] DEFAULT NULL,
    p_expires_in interval DEFAULT interval '30 minutes'
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_bill      billing.bill%ROWTYPE;
    v_existing  uuid;
    v_permitted payments.provider[];
    v_id        uuid;
BEGIN
    -- FR-PAY-012, and the whole of it. A retry presents the same key and receives the
    -- SAME intent — not a new one that happens to look alike. Checked before anything
    -- else so a retry costs nothing and cannot half-succeed.
    SELECT id INTO v_existing FROM payments.payment_intent
     WHERE tenant_id = p_tenant_id AND idempotency_key = p_idempotency_key;
    IF v_existing IS NOT NULL THEN
        RETURN v_existing;
    END IF;

    SELECT * INTO v_bill FROM billing.bill
     WHERE tenant_id = p_tenant_id AND id = p_bill_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'BILL_NOT_FOUND: no bill % in scope', p_bill_id
            USING ERRCODE = 'HS404';
    END IF;
    IF v_bill.state <> 'issued' THEN
        RAISE EXCEPTION
            'BILL_NOT_PAYABLE: bill % is %, and only an issued bill can be paid. A '
            'voided or reissued document is not a thing to take money against',
            p_bill_id, v_bill.state USING ERRCODE = 'HS409';
    END IF;

    -- Permitted tender methods default to whatever this outlet actually has ACTIVE, from
    -- the registry rather than from a list. An intent cannot permit a method the outlet
    -- does not run, and cannot silently omit one it does.
    v_permitted := coalesce(p_permitted_providers, (
        SELECT array_agg(provider ORDER BY provider)
          FROM payments.payment_adapter
         WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id AND active));

    IF v_permitted IS NULL OR array_length(v_permitted, 1) IS NULL THEN
        RAISE EXCEPTION
            'PAYMENT_ADAPTER_NOT_REGISTERED: this outlet has no active payment adapter, '
            'so there is no method by which the bill could be paid'
            USING ERRCODE = 'HS409';
    END IF;

    INSERT INTO payments.payment_intent
        (tenant_id, outlet_id, bill_id, bill_share_id, tip_id, currency_code,
         bill_amount_minor, tip_amount_minor, permitted_providers, idempotency_key,
         expires_at, created_by_user_id)
    VALUES (p_tenant_id, p_outlet_id, p_bill_id, p_bill_share_id, p_tip_id,
            v_bill.currency_code, p_bill_amount_minor, p_tip_amount_minor, v_permitted,
            p_idempotency_key, now() + p_expires_in, p_actor_user_id)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION payments.create_intent IS
    'FR-PAY-001. What a payer is about to pay, for one bill, with the tip as its own '
    'figure. Idempotent by key, so FR-PAY-012''s retry returns the first intent rather '
    'than making a second — the duplicate-payment defect, prevented where it starts.';


-- ---------------------------------------------------------------------------
-- The one capture, which the three live methods share
-- ---------------------------------------------------------------------------
-- One writer rather than three, for the reason M3-D gave about the ordering channels: a
-- second implementation of a rule is a second thing to get wrong, and the differential in
-- tests/channel_differential.py asserts from the catalog that no such second exists.

CREATE FUNCTION payments.capture(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_intent_id uuid,
    p_provider  payments.provider,
    p_tendered_minor money.amount_minor,
    p_actor_user_id uuid,
    p_proof_id uuid DEFAULT NULL,
    p_terminal_result_id uuid DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_intent   payments.payment_intent%ROWTYPE;
    v_adapter  payments.payment_adapter%ROWTYPE;
    v_proof    payments.proof_confirmation%ROWTYPE;
    v_owed     bigint;
    v_change   bigint;
    v_payment  uuid := gen_random_uuid();
    v_allocations jsonb := '[]'::jsonb;
    v_correlation uuid;
    v_event    bigint;
BEGIN
    SELECT * INTO v_intent FROM payments.payment_intent
     WHERE tenant_id = p_tenant_id AND id = p_intent_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PAYMENT_INTENT_NOT_FOUND: no intent % in scope', p_intent_id
            USING ERRCODE = 'HS404';
    END IF;

    IF v_intent.expires_at <= now() THEN
        RAISE EXCEPTION
            'PAYMENT_INTENT_EXPIRED: intent % expired at %. An abandoned intent must not '
            'authorize a payment tomorrow', p_intent_id, v_intent.expires_at
            USING ERRCODE = 'HS409';
    END IF;

    IF NOT (p_provider = ANY (v_intent.permitted_providers)) THEN
        RAISE EXCEPTION
            'PAYMENT_METHOD_NOT_PERMITTED: intent % permits %, and % was offered',
            p_intent_id, v_intent.permitted_providers, p_provider
            USING ERRCODE = 'HS409';
    END IF;

    -- FR-PAY-012 again, at the other end. One intent captures once. A retry that reached
    -- here after a capture already succeeded gets the FIRST payment back rather than a
    -- second one, so a lost response cannot become two charges.
    SELECT id INTO v_payment FROM payments.payment
     WHERE tenant_id = p_tenant_id AND intent_id = p_intent_id;
    IF FOUND THEN
        RETURN v_payment;
    END IF;
    v_payment := gen_random_uuid();

    SELECT * INTO v_adapter FROM payments.payment_adapter
     WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id AND provider = p_provider;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'PAYMENT_ADAPTER_NOT_REGISTERED: no % adapter for this outlet', p_provider
            USING ERRCODE = 'HS404';
    END IF;
    IF NOT v_adapter.active THEN
        RAISE EXCEPTION
            'PAYMENT_ADAPTER_INACTIVE: the % adapter is switched off for this outlet',
            p_provider USING ERRCODE = 'HS409';
    END IF;

    IF p_proof_id IS NOT NULL THEN
        SELECT * INTO v_proof FROM payments.proof_confirmation
         WHERE tenant_id = p_tenant_id AND id = p_proof_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'PROOF_NOT_FOUND: no proof % in scope', p_proof_id
                USING ERRCODE = 'HS404';
        END IF;
    END IF;

    -- EXACT ARITHMETIC, in the database. FR-PAY-002 asks for amount tendered and change;
    -- the surface sends what the guest handed over and nothing else, because a change
    -- amount computed in a browser is a number nobody can reconcile against a drawer.
    v_owed   := v_intent.bill_amount_minor + v_intent.tip_amount_minor;
    v_change := p_tendered_minor - v_owed;

    IF v_change < 0 THEN
        RAISE EXCEPTION
            'PAYMENT_TENDER_INSUFFICIENT: % was tendered against % owed on this intent',
            p_tendered_minor, v_owed USING ERRCODE = 'HS422';
    END IF;
    IF v_change > 0 AND p_provider <> 'cash' THEN
        RAISE EXCEPTION
            'PAYMENT_TENDER_NOT_EXACT: % pays exactly what is owed; % was tendered '
            'against %. Only cash gives change', p_provider, p_tendered_minor, v_owed
            USING ERRCODE = 'HS422';
    END IF;

    IF v_intent.bill_amount_minor > 0 THEN
        v_allocations := v_allocations || jsonb_build_object(
            'id', gen_random_uuid(), 'target', 'bill_balance',
            'bill_id', v_intent.bill_id, 'amount_minor', v_intent.bill_amount_minor);
    END IF;
    IF v_intent.tip_amount_minor > 0 THEN
        v_allocations := v_allocations || jsonb_build_object(
            'id', gen_random_uuid(), 'target', 'tip',
            'tip_id', v_intent.tip_id, 'amount_minor', v_intent.tip_amount_minor);
    END IF;

    -- The correlation the guest's original request carried. A check has none of its own —
    -- it is an allocation OF order lines, and the request that produced them is the
    -- order's. So the chain is followed rather than copied: bill, check, allocation,
    -- order, correlation. FR-INT-014 wants one thread through every artifact of one
    -- request, and a payment that minted a fresh correlation would start a second thread
    -- that looked like a first.
    SELECT o.correlation_id INTO v_correlation
      FROM billing.bill b
      JOIN billing.check_allocation a
        ON a.tenant_id = b.tenant_id AND a.check_id = b.check_id
      JOIN ordering.customer_order o
        ON o.tenant_id = a.tenant_id AND o.id = a.order_id
     WHERE b.tenant_id = p_tenant_id AND b.id = v_intent.bill_id
     LIMIT 1;

    v_event := payments.append_event(
        p_tenant_id, p_outlet_id, v_payment, 'captured', p_actor_user_id,
        NULL, NULL, NULL, NULL,
        jsonb_build_object(
            'intent_id', p_intent_id,
            'adapter_id', v_adapter.id,
            'adapter_mode', v_adapter.mode,
            'provider', p_provider,
            -- A LIVE outcome is written only for a live adapter, and the CHECK on
            -- payments.payment refuses the pair the other way round. A simulated capture
            -- carries no outcome, so there is nothing for NC-M4-003 to relabel.
            'outcome', CASE WHEN v_adapter.mode = 'live' THEN 'approved' END,
            'currency_code', v_intent.currency_code,
            'tendered_minor', p_tendered_minor,
            'change_minor', v_change,
            'proof_id', p_proof_id,
            'proof_state', v_proof.state,
            'terminal_result_id', p_terminal_result_id,
            'allocations', v_allocations),
        v_correlation);

    PERFORM payments.apply_event(v_event);
    RETURN v_payment;
END;
$$;

COMMENT ON FUNCTION payments.capture IS
    'The single capture path every live method shares (FR-PAY-002, FR-PAY-003, '
    'FR-PAY-014). Change is arithmetic here rather than in a surface; the two allocations '
    'are written from the intent and never recalculated; and the outcome column is filled '
    'only for a live adapter, so a simulated capture has no live result to be mistaken '
    'for one.';


-- ---------------------------------------------------------------------------
-- Cash (FR-PAY-002)
-- ---------------------------------------------------------------------------

CREATE FUNCTION payments.record_cash_payment(
    p_tenant_id uuid, p_outlet_id uuid, p_intent_id uuid,
    p_tendered_minor money.amount_minor, p_actor_user_id uuid
) RETURNS uuid
LANGUAGE sql
AS $$
    SELECT payments.capture(p_tenant_id, p_outlet_id, p_intent_id, 'cash',
                            p_tendered_minor, p_actor_user_id);
$$;

COMMENT ON FUNCTION payments.record_cash_payment IS
    'FR-PAY-002. Cash, with exact bill allocation, a separate optional tip, the amount '
    'tendered and the change — all computed and stored here. Cash service continues '
    'during an internet outage because nothing on this path reaches outside the database: '
    'tests/m4b derives the transitive call graph from the catalog and proves it, and the '
    'behavioural half is a partial closure against M5a, which owns the outlet node an '
    'outage could be staged on.';


-- ---------------------------------------------------------------------------
-- The external terminal (FR-PAY-003)
-- ---------------------------------------------------------------------------

CREATE FUNCTION payments.record_terminal_result(
    p_tenant_id uuid, p_outlet_id uuid,
    p_terminal_reference text, p_scheme text,
    p_currency_code char(3), p_amount_minor money.amount_minor,
    p_outcome payments.live_outcome, p_actor_user_id uuid,
    p_masked_tail text DEFAULT NULL, p_approval_code text DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO payments.terminal_result
        (tenant_id, outlet_id, terminal_reference, scheme, masked_tail, approval_code,
         outcome, currency_code, amount_minor, recorded_by_user_id)
    VALUES (p_tenant_id, p_outlet_id, p_terminal_reference, p_scheme, p_masked_tail,
            p_approval_code, p_outcome, p_currency_code, p_amount_minor, p_actor_user_id)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION payments.record_terminal_result IS
    'FR-PAY-003. What the terminal printed, typed in by the person holding the slip. '
    'There is no parameter for a card number because there is no column for one, and '
    'payments.refuse_card_data() walks every string on the row in case a later column '
    'forgets. We record what a terminal did; we are not a terminal.';

CREATE FUNCTION payments.record_terminal_payment(
    p_tenant_id uuid, p_outlet_id uuid, p_intent_id uuid,
    p_terminal_result_id uuid, p_tendered_minor money.amount_minor,
    p_actor_user_id uuid
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_result payments.terminal_result%ROWTYPE;
BEGIN
    SELECT * INTO v_result FROM payments.terminal_result
     WHERE tenant_id = p_tenant_id AND id = p_terminal_result_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TERMINAL_RESULT_NOT_FOUND: no terminal result % in scope',
            p_terminal_result_id USING ERRCODE = 'HS404';
    END IF;

    IF v_result.outcome <> 'approved' THEN
        RAISE EXCEPTION
            'UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM: terminal result % came back % and a '
            'declined card paid nothing', p_terminal_result_id, v_result.outcome
            USING ERRCODE = 'HS409';
    END IF;

    RETURN payments.capture(p_tenant_id, p_outlet_id, p_intent_id, 'external_terminal',
                            p_tendered_minor, p_actor_user_id, NULL, p_terminal_result_id);
END;
$$;


-- ---------------------------------------------------------------------------
-- Proof-based mobile money (FR-PAY-014)
-- ---------------------------------------------------------------------------

CREATE FUNCTION payments.raise_proof(
    p_tenant_id uuid, p_outlet_id uuid, p_provider payments.provider,
    p_currency_code char(3), p_amount_minor money.amount_minor,
    p_provider_reference text, p_masked_identifier text DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_id uuid;
BEGIN
    -- Raised PENDING, always. FR-PAY-014 leaves unverified proof pending rather than
    -- paid, and there is no parameter here by which a caller could raise one already
    -- verified — the attestation is added by payments.verify_proof(), which reads the
    -- verifier from their own live session rather than accepting a name.
    INSERT INTO payments.proof_confirmation
        (tenant_id, outlet_id, provider, state, currency_code, amount_minor,
         provider_reference, masked_identifier)
    VALUES (p_tenant_id, p_outlet_id, p_provider, 'pending', p_currency_code,
            p_amount_minor, p_provider_reference, p_masked_identifier)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

CREATE FUNCTION payments.verify_proof(
    p_tenant_id uuid, p_proof_id uuid, p_what_the_verifier_saw text
) RETURNS void
-- SECURITY DEFINER because the attribution is read from identity.session, on which the
-- application role holds no SELECT. Note what is NOT a parameter: who verified. It comes
-- from the live session in context, so there is no argument by which a caller could
-- attest on somebody else's behalf. M3-D's approve_override() established the shape and
-- the reasoning is identical — a verification that cannot be attributed is not one.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, payments, identity, config, public
AS $$
DECLARE
    v_session identity.session%ROWTYPE;
    v_proof   payments.proof_confirmation%ROWTYPE;
BEGIN
    SELECT * INTO v_session FROM identity.session
     WHERE id = app.current_session_id() AND revoked_at IS NULL AND expires_at > now();
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'SESSION_NOT_LIVE: a proof is verified by a person, and no live session is in '
            'context to say who' USING ERRCODE = 'HS401';
    END IF;

    SELECT * INTO v_proof FROM payments.proof_confirmation
     WHERE tenant_id = p_tenant_id AND id = p_proof_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PROOF_NOT_FOUND: no proof % in scope', p_proof_id
            USING ERRCODE = 'HS404';
    END IF;
    IF v_proof.state <> 'pending' THEN
        RAISE EXCEPTION
            'PROOF_ALREADY_RESOLVED: proof % is %, and a resolved attestation is not '
            'revisited — a second look is a second proof', p_proof_id, v_proof.state
            USING ERRCODE = 'HS409';
    END IF;

    IF btrim(coalesce(p_what_the_verifier_saw, '')) = '' THEN
        RAISE EXCEPTION
            'VERIFICATION_WITHOUT_ATTRIBUTOR: a verification records what the verifier '
            'saw in the provider''s application. An attestation with no content is a '
            'tick-box, and a tick-box is what FR-PAY-014 exists to refuse'
            USING ERRCODE = 'HS422';
    END IF;

    UPDATE payments.proof_confirmation
       SET state = 'verified',
           verified_by_user_id    = v_session.user_account_id,
           verified_by_session_id = v_session.id,
           verified_at            = now(),
           what_the_verifier_saw  = p_what_the_verifier_saw
     WHERE tenant_id = p_tenant_id AND id = p_proof_id;
END;
$$;

COMMENT ON FUNCTION payments.verify_proof(uuid, uuid, text) IS
    'FR-PAY-014. A member of staff opened the provider''s application, saw the receipt, '
    'and says so. The verifier and their session are DERIVED from the session in context '
    'and are never parameters, so there is no argument by which somebody could attest as '
    'somebody else — the same reasoning as M3-D''s override approver.';

CREATE FUNCTION payments.record_proof_payment(
    p_tenant_id uuid, p_outlet_id uuid, p_intent_id uuid, p_proof_id uuid,
    p_tendered_minor money.amount_minor, p_actor_user_id uuid
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_proof payments.proof_confirmation%ROWTYPE;
BEGIN
    SELECT * INTO v_proof FROM payments.proof_confirmation
     WHERE tenant_id = p_tenant_id AND id = p_proof_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PROOF_NOT_FOUND: no proof % in scope', p_proof_id
            USING ERRCODE = 'HS404';
    END IF;

    -- Said here as well as at the write, so an operator gets a sentence rather than a
    -- constraint name. The constraint is what makes it TRUE; this is what makes it
    -- answerable. Removing this leaves the property intact, which is the test of whether
    -- a message is doing the enforcing.
    IF v_proof.state <> 'verified' THEN
        RAISE EXCEPTION
            'UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM: proof % is % — somebody must open %, '
            'find the receipt and record what they saw before this counts as paid',
            p_proof_id, v_proof.state, v_proof.provider
            USING ERRCODE = 'HS409';
    END IF;

    RETURN payments.capture(p_tenant_id, p_outlet_id, p_intent_id, v_proof.provider,
                            p_tendered_minor, p_actor_user_id, p_proof_id);
END;
$$;


-- ---------------------------------------------------------------------------
-- Reversal (FR-PAY-009)
-- ---------------------------------------------------------------------------

CREATE FUNCTION payments.reverse_allocation(
    p_tenant_id uuid, p_outlet_id uuid, p_allocation_id uuid,
    p_kind payments.reversal_kind, p_amount_minor money.amount_minor,
    p_reason_code_id uuid, p_reason_text text, p_actor_user_id uuid,
    p_override_id uuid DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_alloc    payments.allocation%ROWTYPE;
    v_reversal uuid := gen_random_uuid();
    v_event    bigint;
    v_correlation uuid;
BEGIN
    SELECT * INTO v_alloc FROM payments.allocation
     WHERE tenant_id = p_tenant_id AND id = p_allocation_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ALLOCATION_NOT_FOUND: no allocation % in scope', p_allocation_id
            USING ERRCODE = 'HS404';
    END IF;

    SELECT correlation_id INTO v_correlation FROM payments.payment
     WHERE tenant_id = p_tenant_id AND id = v_alloc.payment_id;

    v_event := payments.append_event(
        p_tenant_id, p_outlet_id, v_alloc.payment_id, 'reversed', p_actor_user_id,
        p_override_id, p_reason_code_id, p_reason_text,
        jsonb_build_object('allocation_id', p_allocation_id,
                           'amount_minor', v_alloc.amount_minor),
        jsonb_build_object(
            'reversal_id', v_reversal,
            'allocation_id', p_allocation_id,
            'kind', p_kind,
            'currency_code', v_alloc.currency_code,
            'amount_minor', p_amount_minor),
        v_correlation);

    PERFORM payments.apply_event(v_event);
    RETURN v_reversal;
END;
$$;

COMMENT ON FUNCTION payments.reverse_allocation IS
    'FR-PAY-009. Money back against ONE allocation, so a tip is refunded without touching '
    'the bill payment and a bill payment without clawing back a tip. The approval '
    'threshold, the reason code and the maker-checker link are enforced by '
    'payments.assert_reversal_is_authorized() at the write rather than here, so a second '
    'caller cannot reach the table by another route.';


-- ===========================================================================
-- What "verified" means (FR-ORD-007B)
-- ===========================================================================
-- M4-A recorded this requirement as a DEPENDENCY: ordering.accept_order() refused a
-- payment-dependent order by name because nothing could verify a payment. This is the
-- verifier, and the definition is four conditions, every one of them already true by
-- constraint before this function is reached:
--
--   LIVE       the payment came through an adapter whose mode is derived from its
--              provider by CHECK, so no direct-provider adapter can be behind it
--   APPROVED   the live outcome column — a type no simulator can produce — says approved
--   ATTRIBUTED for a proof-based provider, a named person, on their own live session, at
--              a recorded time, having written down what they saw
--   ALLOCATED  the money reached the bill balance as its own row, which
--              payments.assert_allocation_is_earned() only permits when the three above
--              hold
--
-- So this function does not re-check any of them. It asks the one question the
-- constraints cannot: is the bill this order sits on paid in full? An order accepted on a
-- half-paid bill would be a different requirement.

CREATE FUNCTION payments.order_is_paid(p_tenant_id uuid, p_order_id uuid)
RETURNS boolean
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_bill      uuid;
    v_total     bigint;
    v_allocated bigint;
BEGIN
    -- The bill issued over a check that allocates this order's lines. There may be none,
    -- which is the ordinary state of an order nobody has asked to pay for yet.
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

    -- Allocations to the BILL BALANCE only, net of anything reversed. A tip does not pay
    -- for an order, which is M4-A's doctrine reaching the one place at this gate where
    -- somebody might have been tempted to add it up.
    SELECT coalesce((SELECT sum(a.amount_minor) FROM payments.allocation a
                      WHERE a.tenant_id = p_tenant_id AND a.bill_id = v_bill
                        AND a.target = 'bill_balance'), 0)
         - coalesce((SELECT sum(r.amount_minor)
                       FROM payments.reversal r
                       JOIN payments.allocation a
                         ON a.tenant_id = r.tenant_id AND a.id = r.allocation_id
                      WHERE r.tenant_id = p_tenant_id AND a.bill_id = v_bill
                        AND a.target = 'bill_balance'), 0)
      INTO v_allocated;

    RETURN v_allocated >= v_total;
END;
$$;

COMMENT ON FUNCTION payments.order_is_paid(uuid, uuid) IS
    'FR-ORD-007B. Whether a verified payment outcome covers the bill this order sits on. '
    'It sums BILL BALANCE allocations net of reversals and never tips: a generous table '
    'must not buy acceptance of an order nobody paid for. Every allocation it can see is '
    'already live, approved and — for proof-based providers — attested, because '
    'payments.assert_allocation_is_earned() refuses to write one that is not.';


-- ===========================================================================
-- Read models
-- ===========================================================================
-- FR-PAY-017's "no hidden recomputation" is a property of these functions and not only of
-- the tables. Every figure below is SELECTED from the column it was stored in. None is
-- derived from a bill, a rate or a sum over something else, and tests/m4b asserts that
-- from the catalog rather than from reading them.

CREATE FUNCTION payments.allocation_view(p_tenant_id uuid, p_payment_id uuid)
RETURNS TABLE (
    allocation_id uuid,
    target        text,
    bill_id       uuid,
    tip_id        uuid,
    currency_code char(3),
    amount_minor  bigint,
    reversed_minor bigint,
    net_minor     bigint
)
LANGUAGE sql STABLE
AS $$
    SELECT a.id,
           a.target::text,
           a.bill_id,
           a.tip_id,
           a.currency_code,
           -- WHAT WAS RECORDED. Not the bill's share of anything, not a percentage
           -- reapplied: the number written at capture. A bill reissued tomorrow does not
           -- change what a guest handed over today.
           a.amount_minor::bigint,
           coalesce(r.reversed, 0),
           a.amount_minor::bigint - coalesce(r.reversed, 0)
      FROM payments.allocation a
      LEFT JOIN LATERAL (
           SELECT sum(x.amount_minor)::bigint AS reversed
             FROM payments.reversal x
            WHERE x.tenant_id = a.tenant_id AND x.allocation_id = a.id) r ON true
     WHERE a.tenant_id = p_tenant_id AND a.payment_id = p_payment_id
     ORDER BY a.target;
$$;

COMMENT ON FUNCTION payments.allocation_view(uuid, uuid) IS
    'FR-PAY-017. What one payment allocated, read out of the columns it was written into. '
    'The only arithmetic is subtracting reversals, which are themselves recorded rows — '
    'so the net is a difference between two stored figures rather than a recomputation of '
    'either.';


CREATE FUNCTION payments.reconciliation(
    p_tenant_id uuid, p_outlet_id uuid,
    p_from timestamptz, p_to timestamptz
) RETURNS TABLE (
    provider              text,
    payment_count         bigint,
    tendered_minor        bigint,
    change_minor          bigint,
    bill_allocation_minor bigint,
    tip_allocation_minor  bigint,
    reversed_minor        bigint,
    provider_references   bigint
)
LANGUAGE sql STABLE
AS $$
    -- FR-PAY-013. Bill allocations, tip allocations, tender totals and provider
    -- references, reconciled — AND NEVER ADDED TOGETHER. There is no column here that
    -- combines the two allocation figures, because the merge FR-PAY-013 forbids is the
    -- M4-A doctrine failing at the reporting layer rather than a rounding mistake: a
    -- sales figure inflated by tips is a tax return that is wrong and staff who are owed
    -- money nobody can find.
    SELECT p.provider::text,
           count(*)::bigint,
           sum(p.tendered_minor)::bigint,
           sum(p.change_minor)::bigint,
           coalesce(sum(b.bill_minor), 0)::bigint,
           coalesce(sum(t.tip_minor), 0)::bigint,
           coalesce(sum(v.reversed_minor), 0)::bigint,
           count(*) FILTER (WHERE pc.provider_reference IS NOT NULL)::bigint
      FROM payments.payment p
      LEFT JOIN LATERAL (
           SELECT sum(a.amount_minor) AS bill_minor FROM payments.allocation a
            WHERE a.tenant_id = p.tenant_id AND a.payment_id = p.id
              AND a.target = 'bill_balance') b ON true
      LEFT JOIN LATERAL (
           SELECT sum(a.amount_minor) AS tip_minor FROM payments.allocation a
            WHERE a.tenant_id = p.tenant_id AND a.payment_id = p.id
              AND a.target = 'tip') t ON true
      LEFT JOIN LATERAL (
           SELECT sum(r.amount_minor) AS reversed_minor
             FROM payments.reversal r
             JOIN payments.allocation a ON a.tenant_id = r.tenant_id
                                       AND a.id = r.allocation_id
            WHERE a.tenant_id = p.tenant_id AND a.payment_id = p.id) v ON true
      LEFT JOIN payments.proof_confirmation pc
             ON pc.tenant_id = p.tenant_id AND pc.id = p.proof_id
     WHERE p.tenant_id = p_tenant_id AND p.outlet_id = p_outlet_id
       AND p.captured_at >= p_from AND p.captured_at < p_to
     GROUP BY p.provider
     ORDER BY p.provider;
$$;

COMMENT ON FUNCTION payments.reconciliation(uuid, uuid, timestamptz, timestamptz) IS
    'FR-PAY-013. Bill allocations, tip allocations, tender totals and provider references '
    'side by side, per provider, for a window. bill_allocation_minor and '
    'tip_allocation_minor are SEPARATE columns and no column sums them: tests/m4b derives '
    'the revenue-bearing columns of this function from the catalog and requires that none '
    'of them reads the tip allocation, the same derivation M4-A used on the thirteen '
    'balance functions. Cash shifts join this picture in 0024, which owns them.';


-- ===========================================================================
-- Rebuild (FR-DAT-010)
-- ===========================================================================

CREATE FUNCTION payments.drop_projections_for_rebuild(p_tenant_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, payments, public
AS $$
BEGIN
    PERFORM set_config('payments.applying_event', 'yes', true);
    -- Reversals and allocations cascade from the payment, so this is one statement and
    -- not three that must be kept in the right order.
    DELETE FROM payments.payment WHERE tenant_id = p_tenant_id;
    PERFORM set_config('payments.applying_event', '', true);
END;
$$;

CREATE FUNCTION payments.rebuild_projections(p_tenant_id uuid) RETURNS bigint
-- SECURITY DEFINER for the reason 0019 discovered the hard way: a superuser caller
-- selects events that the definer-owned apply_event(), running under FORCE ROW LEVEL
-- SECURITY, cannot see — so the replay found nothing and reported success. Both halves
-- run as the same role here, and the refusal below makes a rebuild that folded nothing
-- an error rather than a clean run.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, payments, billing, ordering, config, money, identity, pos, public
AS $$
DECLARE
    v_event bigint;
    v_count bigint := 0;
    v_available bigint;
BEGIN
    SELECT count(*) INTO v_available FROM payments.payment_event
     WHERE tenant_id = p_tenant_id;

    PERFORM payments.drop_projections_for_rebuild(p_tenant_id);

    FOR v_event IN
        SELECT id FROM payments.payment_event
         WHERE tenant_id = p_tenant_id ORDER BY id
    LOOP
        PERFORM payments.apply_event(v_event);
        v_count := v_count + 1;
    END LOOP;

    IF v_available > 0 AND v_count = 0 THEN
        RAISE EXCEPTION
            'REBUILD_SEES_NO_LEDGER: % event(s) exist for this tenant and the rebuild '
            'folded none. A rebuild that reads nothing and reports success is how a '
            'projection silently becomes empty', v_available
            USING ERRCODE = 'HS500';
    END IF;

    RETURN v_count;
END;
$$;


-- ===========================================================================
-- Row level security
-- ===========================================================================
-- Enumerated from the catalog rather than listed, exactly as 0019 does, so a table added
-- to this schema by a later slice is enrolled without anybody remembering to enrol it.
-- ENABLE and FORCE both: FORCE is what makes the policy apply to the table's own owner,
-- and every SECURITY DEFINER function above runs as that owner.

DO $$
DECLARE t text;
BEGIN
    FOR t IN
        SELECT format('%I.%I', schemaname, tablename)
        FROM pg_tables WHERE schemaname = 'payments'
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

GRANT USAGE ON SCHEMA payments TO hospitality_app;
-- And USAGE on the sequences behind the bigserial keys. The application role holds INSERT
-- on the ledger deliberately — the grant and the append-only trigger are two independent
-- locks — and an INSERT that cannot draw a key is a grant that does not work. 0019's
-- writers hid this by being SECURITY DEFINER; the ledger here is written by the caller,
-- so the grant has to be real.
GRANT USAGE ON ALL SEQUENCES IN SCHEMA payments TO hospitality_app;

GRANT SELECT ON payments.payment_adapter      TO hospitality_app;
GRANT SELECT ON payments.payment_intent       TO hospitality_app;
GRANT SELECT ON payments.payment              TO hospitality_app;
GRANT SELECT ON payments.allocation           TO hospitality_app;
GRANT SELECT ON payments.reversal             TO hospitality_app;
GRANT SELECT ON payments.payment_event        TO hospitality_app;
GRANT SELECT ON payments.proof_confirmation   TO hospitality_app;
GRANT SELECT ON payments.terminal_result      TO hospitality_app;
GRANT SELECT ON payments.simulated_attempt    TO hospitality_app;

-- The intent is ordinary working state: created, retried against, allowed to expire.
GRANT INSERT ON payments.payment_intent TO hospitality_app;

-- The ledger takes INSERT and nothing else, and the append-only trigger refuses UPDATE
-- and DELETE independently — two locks, either surviving the other's removal.
GRANT INSERT ON payments.payment_event TO hospitality_app;

-- Evidence is written once and never edited. NOTE WHAT IS ABSENT: no UPDATE on
-- payments.proof_confirmation. Verification runs inside payments.verify_proof(), which is
-- SECURITY DEFINER and reads the verifier from the session in context, so an application
-- holding every permission there is still cannot flip a proof from pending to verified by
-- writing to it. The CHECK constraints make an unattributed verification impossible; this
-- grant makes an unattributable one unreachable.
GRANT INSERT ON payments.proof_confirmation TO hospitality_app;
GRANT INSERT ON payments.terminal_result    TO hospitality_app;
GRANT INSERT ON payments.simulated_attempt  TO hospitality_app;

-- payments.payment, payments.allocation and payments.reversal take NO write grant at
-- all. They are folded, and the fold runs in a function the application calls rather than
-- in the application.

GRANT EXECUTE ON FUNCTION payments.create_intent(uuid, uuid, uuid, text, money.amount_minor, uuid, money.amount_minor, uuid, uuid, payments.provider[], interval) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.capture(uuid, uuid, uuid, payments.provider, money.amount_minor, uuid, uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.record_cash_payment(uuid, uuid, uuid, money.amount_minor, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.record_terminal_result(uuid, uuid, text, text, char, money.amount_minor, payments.live_outcome, uuid, text, text) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.record_terminal_payment(uuid, uuid, uuid, uuid, money.amount_minor, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.raise_proof(uuid, uuid, payments.provider, char, money.amount_minor, text, text) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.verify_proof(uuid, uuid, text) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.record_proof_payment(uuid, uuid, uuid, uuid, money.amount_minor, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.reverse_allocation(uuid, uuid, uuid, payments.reversal_kind, money.amount_minor, uuid, text, uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.invoke_direct_provider(uuid, uuid, payments.provider, char, money.amount_minor, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.append_event(uuid, uuid, uuid, payments.payment_event_kind, uuid, uuid, uuid, text, jsonb, jsonb, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.apply_event(bigint) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.allocation_view(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.reconciliation(uuid, uuid, timestamptz, timestamptz) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.order_is_paid(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.reversal_threshold_minor(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION payments.looks_like_card_data(text) TO hospitality_app;

-- A rebuild is an administrator's operation, not the application's — 0019's reasoning,
-- and the consequence here is larger.
GRANT EXECUTE ON FUNCTION payments.rebuild_projections(uuid)          TO hospitality_migrator;
GRANT EXECUTE ON FUNCTION payments.drop_projections_for_rebuild(uuid) TO hospitality_migrator;

-- The adapter registry is an administrator's, and deliberately so: which adapters an
-- outlet runs is a decision, and the application does not get to make it. Whether an
-- adapter is SIMULATED is nobody's decision, which is why that is a CHECK and not a row.
GRANT USAGE ON SCHEMA payments TO hospitality_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON payments.payment_adapter TO hospitality_migrator;
