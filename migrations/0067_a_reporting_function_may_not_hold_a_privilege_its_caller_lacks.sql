-- 0067 - A REPORTING FUNCTION MAY NOT HOLD A PRIVILEGE ITS CALLER LACKS
--
-- M4-C has asked this since it was written, of every function in schema `report`:
--
--     no reporting function has a privilege its caller lacks
--     Tenant and outlet scoping is the database's, not a WHERE clause a route appends
--     and could forget
--
-- 0065 shipped two functions that answer it wrongly. report.kitchen_consumption() and
-- report.record_export() are both SECURITY DEFINER, and the forward chain caught them the
-- first time it ran with M6 in it. The rule is older than this gate and its reasoning is
-- sound, so the functions change rather than the rule.
--
-- THE INTERESTING ONE IS record_export(), because DEFINER there was load-bearing in a way
-- kitchen_consumption()'s was not. The step-up check lived INSIDE the function, so the
-- function had to be the only way in, so it had to own the INSERT privilege. Dropping to
-- INVOKER without moving that check would have left the demand for a fresh grant sitting
-- in a function that anybody holding INSERT could route around.
--
-- So the check moves to a BEFORE INSERT trigger on the table, which is where it should
-- have been. 0059 learned this one gate ago -- the revoked-session rule moved out of a
-- WHERE clause into a row trigger for the same reason -- and the result is the same here:
-- the rule now holds for EVERY path into report.export_event rather than for the one path
-- that happens to call the function. The function got weaker and the guarantee got
-- stronger, which is why this is a repair rather than a concession.

-- ---------------------------------------------------------------------------
-- 1. THE STEP-UP DEMAND BECOMES A PROPERTY OF THE TABLE
-- ---------------------------------------------------------------------------

CREATE FUNCTION report.export_demands_a_fresh_grant() RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'pg_catalog', 'report', 'identity', 'public'
AS $$
BEGIN
    -- THE GRANT MUST BE FOR THIS ACTION AND FOR THIS PERSON. Without both clauses any
    -- live grant would do: a manager who stepped up to refund a payment could take the
    -- year's figures on the strength of it. FR-AUTH-006 scopes the window per action for
    -- exactly this reason, and 0052 had to add the same clause to edge.claim_authority()
    -- one gate before this.
    PERFORM 1
       FROM identity.step_up_grant g
       JOIN identity.session s ON s.tenant_id = g.tenant_id AND s.id = g.session_id
       JOIN identity.governed_action a ON a.tenant_id = g.tenant_id
                                      AND a.action_code = g.action_code
      WHERE g.tenant_id = NEW.tenant_id
        AND g.id = NEW.step_up_grant_id
        AND g.action_code = 'report.export'
        AND s.user_account_id = NEW.taken_by_user_id
        AND now() - g.granted_at <= a.step_up_max_age;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'EXPORT_STEP_UP_ABSENT: step-up grant % is not a fresh report.export grant '
            'belonging to the person asking. An export removes an outlet''s whole trade '
            'into a file with none of the controls it had here, and that should not '
            'proceed on somebody else''s authentication, on a stale one, or on one taken '
            'for a different act',
            NEW.step_up_grant_id
            USING ERRCODE = 'HS403';
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION report.export_demands_a_fresh_grant() IS
    'FR-AUTH-006. The clause that was inside report.record_export() until 0067. On the '
    'table rather than in the function, so it holds for every writer rather than for '
    'callers of one function.';

CREATE TRIGGER export_event_demands_a_fresh_grant
    BEFORE INSERT ON report.export_event
    FOR EACH ROW EXECUTE FUNCTION report.export_demands_a_fresh_grant();

-- ---------------------------------------------------------------------------
-- 2. AND THE FUNCTION BECOMES AN ORDINARY INSERT UNDER THE CALLER'S OWN RIGHTS
-- ---------------------------------------------------------------------------
--
-- Which also means the row is now written under row level security. The export record can
-- only be written for a tenant and outlet the caller is actually in. Previously the
-- DEFINER wrote whatever scope it was handed, and the only thing between that and a
-- mis-scoped record was the route passing the right arguments.

CREATE OR REPLACE FUNCTION report.record_export(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_kind report.export_kind,
    p_window_from timestamptz,
    p_window_to timestamptz,
    p_currency character(3),
    p_user_id uuid,
    p_step_up_grant_id uuid,
    p_byte_count integer,
    p_body_sha256 character(64))
RETURNS uuid
LANGUAGE plpgsql SECURITY INVOKER
SET search_path TO 'pg_catalog', 'report', 'identity', 'public'
AS $$
DECLARE
    v_id uuid;
BEGIN
    -- The step-up demand is the trigger's now. What is left here is the insert, and it
    -- runs with the caller's privileges and under the caller's row level security.
    INSERT INTO report.export_event
        (tenant_id, outlet_id, export_kind, window_from, window_to, currency,
         taken_by_user_id, step_up_grant_id, byte_count, body_sha256)
    VALUES (p_tenant_id, p_outlet_id, p_kind, p_window_from, p_window_to, p_currency,
            p_user_id, p_step_up_grant_id, p_byte_count, p_body_sha256)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION report.record_export(uuid, uuid, report.export_kind, timestamptz,
        timestamptz, character, uuid, uuid, integer, character) IS
    'FR-RPT-013, FR-AUTH-006. The caller `report.export` had been waiting for since 0002. '
    'SECURITY INVOKER since 0067: the fresh-grant demand moved to a trigger on '
    'report.export_event, so it holds for every writer and this function holds no '
    'privilege its caller lacks.';

GRANT INSERT ON report.export_event TO hospitality_app;

-- ---------------------------------------------------------------------------
-- 3. AND THE KITCHEN READING IS SCOPED BY RLS RATHER THAN BY ITS ARGUMENTS
-- ---------------------------------------------------------------------------
--
-- This one needed no defence at all. It reads fulfillment tables the application role
-- already selects from for the KDS. As DEFINER its p_tenant_id and p_outlet_id arguments
-- were the ONLY thing keeping it inside one outlet -- precisely the "WHERE clause a route
-- appends and could forget" the rule names. As INVOKER they are a filter on top of a
-- scope the database enforces.

ALTER FUNCTION report.kitchen_consumption(uuid, uuid, timestamptz, timestamptz)
    SECURITY INVOKER;

-- ---------------------------------------------------------------------------
-- 4. AND report.export_event IS SAID TO BE A LEDGER
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.financial_table_class(p_schema text, p_table text)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE
AS $function$
    SELECT CASE p_schema || '.' || p_table
        -- Ledgers: what happened, and correcting one means adding a row, never
        -- changing one.
        WHEN 'billing.bill_disposition'   THEN 'ledger'
        WHEN 'billing.bill_event'         THEN 'ledger'
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
        WHEN 'payments.reversal'          THEN 'ledger'
        WHEN 'payments.simulated_attempt' THEN 'ledger'
        WHEN 'payments.terminal_result'   THEN 'ledger'
        -- A signed-off snapshot is a ledger in the strictest sense in this schema: it is
        -- the record of what the figures WERE when somebody put their name to them, and
        -- the only correct response to a later disagreement is another row saying so.
        WHEN 'report.shift_snapshot'       THEN 'ledger'
        WHEN 'report.shift_snapshot_value' THEN 'ledger'
        WHEN 'report.recomputation'        THEN 'ledger'
        WHEN 'report.snapshot_divergence'  THEN 'ledger'
        WHEN 'report.export'               THEN 'ledger'

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
        -- read well and asserted nothing â€” cash.shift is not configuration in any
        -- ordinary sense, and 'lifecycle' was a kinder word for 'not append-only'. Only
        -- one property here is checkable, so only one distinction is drawn: a ledger
        -- refuses UPDATE and DELETE, and everything else says why it does not, in the
        -- table at the head of 0028 rather than in a class name that implies a rule
        -- nothing enforces.
        -- The three 0028 corrected after tests/m4c asked, of every declared ledger,
        -- whether it actually refuses a destructive correction. A check has a LIFECYCLE
        -- and its append-only record is billing.bill_event; a proof moves from pending to
        -- verified and its record is payments.payment_event. Repeated here because this
        -- function is REPLACED rather than extended, and a replacement that dropped a
        -- correction would put the wrong classification back without anybody editing it.
        WHEN 'billing.check'                   THEN 'mutable'
        WHEN 'billing.check_allocation'        THEN 'mutable'
        WHEN 'payments.proof_confirmation'     THEN 'mutable'
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
        -- Reference data, and the reason it is not a ledger is that it is not a record of
        -- anything: a metric definition is a statement about how to compute, changed by a
        -- migration and versioned by report.catalog_version(). The snapshots that depend
        -- on a version record which one they used, so changing a definition cannot
        -- retroactively alter what a signed-off shift said.
        WHEN 'report.metric'                   THEN 'mutable'
        WHEN 'report.dashboard'                THEN 'mutable'
        WHEN 'report.dashboard_panel'          THEN 'mutable'

        -- M5a. A print job is a state machine — queued, claimed, printed, failed —
        -- so it is mutable, and the append-only record of what actually went to a
        -- machine remains docs.print_attempt, which is a ledger and stays one.
        WHEN 'docs.print_job'                  THEN 'mutable'

        -- ADDED AT M6-D, AND IT IS A LEDGER. report.export_event records that an outlet's
        -- trade left the system: who took it, under which grant, over which window, and
        -- the sha256 of the bytes that went. Correcting one means adding another row --
        -- there is no reading under which an export that happened stops having happened --
        -- and report.refuse_export_rewrite() already refuses UPDATE and DELETE on it. So
        -- the class is not a label chosen to satisfy the check; it is the property the
        -- table already had, finally declared. The check found it because it asks of
        -- every table in a financial schema, and `report` is one.
        WHEN 'report.export_event'             THEN 'ledger'
    END;
$function$;
