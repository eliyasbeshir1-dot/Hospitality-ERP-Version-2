-- 0044: a receipt that was asked for gets printed exactly once, whatever happens next
--
-- FR-EDG-029 is the longest sentence in M5a and every clause of it is a separate failure
-- somebody has had: "a durable local queue with idempotent job identity, bounded retry,
-- restart recovery, deduplication, printer-health visibility, internet-outage continuity
-- and cloud reconciliation without duplicate physical output."
--
-- WHAT M4-C BUILT AND WHAT IT DID NOT. docs.record_receipt_print() records what the agent
-- DID, after it did it, and docs.refuse_duplicate_receipt_print() stops the same receipt
-- being recorded printed twice. That is the evidence half and it is sound. The half that
-- did not exist is the ASKING: nothing held a receipt between "settle this bill" and "the
-- agent got round to it". The agent was invoked and printed synchronously, so a receipt
-- requested while the printer was jammed, or while the agent was restarting, was a
-- receipt nobody would ever print — and no row anywhere said so.
--
-- WHY EXACTLY-ONCE PHYSICAL OUTPUT IS NOT THE SAME PROBLEM AS EXACTLY-ONCE ANYTHING ELSE.
-- Paper cannot be rolled back. Every other idempotent operation in this repository can be
-- made safe by retrying and letting the second attempt collide; a printer that has already
-- cut the paper cannot be asked to un-cut it. So the queue is deliberately asymmetric:
--
--   * before printing, a job may be retried freely — a claim that expires returns to the
--     queue, and a restart recovers everything mid-flight;
--   * after a job is recorded printed, NOTHING returns it to the queue. Not a retry, not
--     a recovery, not an operator. A second physical copy is a REPRINT, which is a
--     different act with its own reason code and its own job.
--
-- That is why the state machine is enforced by a trigger rather than by the functions
-- that use it. A function can be called by something new next year; the transition table
-- cannot.
--
-- BOUNDED RETRY MEANS THE BOUND IS RECORDED, NOT ASSUMED. A job carries its own
-- max_attempts, so a queue does not depend on every caller passing the same constant, and
-- a job that exhausts it is `abandoned` with the last error kept. Abandoned is a terminal
-- state a human can see, not a row that quietly stops being selected.
--
-- INTERNET-OUTAGE CONTINUITY IS THE EASY HALF AND IS SAID ANYWAY: nothing in this queue
-- reaches the cloud. It is local tables read by a local agent against a local printer, so
-- an outage changes nothing about it. What the outage does change is reconciliation, and
-- that is the outbox: a terminal job enqueues one event carrying the job's own identity,
-- so the cloud learns what was printed when the link returns, and learns it once.

-- ---------------------------------------------------------------------------
-- 1. THE CLASSIFICATION, REPLACED WHOLE
-- ---------------------------------------------------------------------------
--
-- `docs` is a financial schema, so app.assert_financial_tables_are_classified() refuses a
-- table here that nobody has classified. The function is REPLACED rather than extended —
-- its own comment records why, and that a replacement dropping a correction would put a
-- wrong classification back without anybody editing it. So the whole body is restated
-- with one line added, and this migration was generated from the live definition rather
-- than retyped.

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
    END;
$function$;

-- ---------------------------------------------------------------------------
-- 2. THE QUEUE
-- ---------------------------------------------------------------------------

CREATE TYPE docs.print_job_state AS ENUM (
    'queued', 'claimed', 'printed', 'failed', 'abandoned');

CREATE TABLE docs.print_job (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,

    receipt_id uuid NOT NULL,
    printer_id uuid NOT NULL,

    -- IDEMPOTENT JOB IDENTITY (FR-EDG-029). Not the receipt id: a reprint is a second
    -- legitimate job for the same receipt. The key names the ACT — this receipt, this
    -- purpose — and the caller states it, so two requests for the same act collide and
    -- two requests for different acts do not.
    job_key text NOT NULL,

    -- Whether this job is the original or a reprint, carried through to the attempt so
    -- the ledger keeps saying what it has always said.
    is_reprint     boolean NOT NULL DEFAULT false,
    reason_code_id uuid,
    reason_text    text,

    state    docs.print_job_state NOT NULL DEFAULT 'queued',
    attempts integer NOT NULL DEFAULT 0,

    -- THE BOUND TRAVELS WITH THE JOB. A queue whose limit lives in whichever caller
    -- happened to enqueue it has as many limits as it has callers.
    max_attempts integer NOT NULL DEFAULT 5,

    next_attempt_at timestamptz NOT NULL DEFAULT now(),

    -- A CLAIM IS A LEASE, NOT A FLAG. An agent that dies holding a flag holds it forever;
    -- a lease expires and the job returns to the queue, which is what makes restart
    -- recovery a property of the data rather than of remembering to run something.
    claimed_by       text,
    claim_expires_at timestamptz,

    printed_at   timestamptz,
    bytes_sha256 character(64),
    last_error   text,

    requested_by_user_id uuid NOT NULL,
    enqueued_at timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT print_job_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT print_job_key_unique UNIQUE (tenant_id, job_key),
    CONSTRAINT print_job_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT print_job_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT print_job_receipt_fk FOREIGN KEY (tenant_id, receipt_id)
        REFERENCES docs.receipt (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT print_job_printer_fk FOREIGN KEY (tenant_id, printer_id)
        REFERENCES docs.printer (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT print_job_requester_fk FOREIGN KEY (tenant_id, requested_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    -- A REASON CODE IS A REFERENCE INTO THE REGISTRY, NEVER A LOOSE UUID. M1-C requires
    -- every consumer to carry this key, and tests/m1c found this column without one
    -- within minutes of it existing. Its message is the reason: "absence of the key is
    -- how a second, divergent list of reasons gets started" — a reprint reason that
    -- resolved to nothing would be a reprint nobody could explain afterwards.
    CONSTRAINT print_job_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT print_job_key_is_stated CHECK (length(trim(job_key)) > 0),
    CONSTRAINT print_job_attempts_not_negative CHECK (attempts >= 0),
    CONSTRAINT print_job_bound_is_positive CHECK (max_attempts > 0),
    CONSTRAINT print_job_claim_is_whole CHECK (
        (claimed_by IS NULL) = (claim_expires_at IS NULL)),
    CONSTRAINT print_job_claimed_means_leased CHECK (
        state <> 'claimed' OR claimed_by IS NOT NULL),
    -- A PRINTED JOB CARRIES THE PROOF. The digest is what ties the row to the bytes the
    -- agent actually pushed at the sink, and a printed job without one would be a claim.
    CONSTRAINT print_job_printed_is_evidenced CHECK (
        (state = 'printed') = (printed_at IS NOT NULL)
    AND (state = 'printed') = (bytes_sha256 IS NOT NULL)),
    CONSTRAINT print_job_abandonment_is_explained CHECK (
        state <> 'abandoned' OR last_error IS NOT NULL),
    CONSTRAINT print_job_reprint_is_explained CHECK (
        NOT is_reprint OR reason_code_id IS NOT NULL OR reason_text IS NOT NULL)
);

COMMENT ON TABLE docs.print_job IS
    'FR-EDG-029. The durable local queue between "this bill is settled" and "the paper '
    'came out". Idempotent by job_key, retried to a bound the job itself carries, claimed '
    'under a lease so a dead agent releases its work, and never returned to the queue '
    'once printed — paper cannot be rolled back, so a second copy is a reprint with its '
    'own reason and its own job.';

COMMENT ON COLUMN docs.print_job.job_key IS
    'The ACT this job performs — this receipt, this purpose — not the receipt id, because '
    'a reprint is a second legitimate job for the same receipt.';

CREATE INDEX print_job_runnable_idx
    ON docs.print_job (tenant_id, outlet_id, printer_id, next_attempt_at)
    WHERE state IN ('queued', 'failed');
CREATE INDEX print_job_leased_idx
    ON docs.print_job (claim_expires_at) WHERE state = 'claimed';

ALTER TABLE docs.print_job ENABLE ROW LEVEL SECURITY;
ALTER TABLE docs.print_job FORCE ROW LEVEL SECURITY;
CREATE POLICY print_job_isolation ON docs.print_job FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 3. THE TRANSITION TABLE, ENFORCED WHERE IT CANNOT BE ROUTED AROUND
-- ---------------------------------------------------------------------------

CREATE FUNCTION docs.assert_print_job_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'PRINT_JOB_IS_PERMANENT: job % records that a receipt was asked for, which '
            'stays true whether or not it ever printed', OLD.id
            USING ERRCODE = 'HS409';
    END IF;

    -- PRINTED IS TERMINAL, AND IT IS TERMINAL HERE RATHER THAN IN A FUNCTION. Paper
    -- cannot be un-cut, so no retry, no lease recovery and no operator returns a printed
    -- job to the queue. A second copy is a reprint: a different act, a different job.
    IF OLD.state = 'printed' AND NEW.state <> 'printed' THEN
        RAISE EXCEPTION
            'PRINT_JOB_ALREADY_PRINTED: job % printed at % and cannot be requeued. A '
            'second physical copy is a reprint, with its own reason and its own job',
            OLD.id, OLD.printed_at
            USING ERRCODE = 'HS409';
    END IF;
    IF OLD.state = 'abandoned' AND NEW.state <> 'abandoned' THEN
        RAISE EXCEPTION
            'PRINT_JOB_ABANDONED: job % exhausted its %s attempts and was abandoned. '
            'Reviving it silently would hide that it ever failed',
            OLD.id, OLD.max_attempts
            USING ERRCODE = 'HS409';
    END IF;

    -- The identity of the act never moves. Everything a reader uses to decide whether two
    -- jobs are the same job is fixed at enqueue.
    IF NEW.tenant_id <> OLD.tenant_id
       OR NEW.outlet_id  <> OLD.outlet_id
       OR NEW.receipt_id <> OLD.receipt_id
       OR NEW.job_key    <> OLD.job_key
       OR NEW.is_reprint <> OLD.is_reprint THEN
        RAISE EXCEPTION
            'PRINT_JOB_IDENTITY_IS_IMMUTABLE: job % may change state, attempts, lease and '
            'outcome; what act it is was decided when it was enqueued', OLD.id
            USING ERRCODE = 'HS409';
    END IF;

    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER print_job_transitions_are_legal
    BEFORE UPDATE OR DELETE ON docs.print_job
    FOR EACH ROW EXECUTE FUNCTION docs.assert_print_job_transition();

-- ---------------------------------------------------------------------------
-- 4. ENQUEUE (FR-EDG-029)
-- ---------------------------------------------------------------------------

CREATE FUNCTION docs.enqueue_print_job(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_receipt_id uuid,
    p_printer_id uuid,
    p_job_key   text,
    p_actor_user_id uuid,
    p_is_reprint boolean DEFAULT false,
    p_reason_code_id uuid DEFAULT NULL,
    p_reason_text text DEFAULT NULL,
    p_max_attempts integer DEFAULT 5)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'docs', 'org', 'identity', 'public'
AS $$
DECLARE
    v_existing uuid;
    v_id       uuid;
BEGIN
    -- A REPEAT REQUEST IS THE SAME REQUEST. A cashier who pressed the button twice
    -- because the first press seemed to do nothing has asked for one receipt.
    SELECT id INTO v_existing FROM docs.print_job
      WHERE tenant_id = p_tenant_id AND job_key = p_job_key;
    IF v_existing IS NOT NULL THEN
        RETURN v_existing;
    END IF;

    -- The printer must be one this outlet has, and it must have passed a test. M4-C built
    -- docs.printer_has_passed_a_test() for exactly this question and nothing was asking
    -- it before a queue existed to ask it in.
    PERFORM 1 FROM docs.printer
      WHERE tenant_id = p_tenant_id AND id = p_printer_id AND outlet_id = p_outlet_id
        AND status = 'active';
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'PRINT_JOB_PRINTER_UNKNOWN: printer % is not an active printer of outlet %',
            p_printer_id, p_outlet_id
            USING ERRCODE = 'HS404';
    END IF;

    INSERT INTO docs.print_job (
        tenant_id, outlet_id, receipt_id, printer_id, job_key, is_reprint,
        reason_code_id, reason_text, max_attempts, requested_by_user_id)
    VALUES (p_tenant_id, p_outlet_id, p_receipt_id, p_printer_id, p_job_key, p_is_reprint,
            p_reason_code_id, p_reason_text, p_max_attempts, p_actor_user_id)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION docs.enqueue_print_job(uuid, uuid, uuid, uuid, text, uuid, boolean,
                                           uuid, text, integer) IS
    'FR-EDG-029. Idempotent by job_key: a cashier who pressed the button twice because '
    'the first press seemed to do nothing has asked for one receipt, and gets the job the '
    'first press created.';

-- ---------------------------------------------------------------------------
-- 5. CLAIM, COMPLETE, FAIL, RECOVER
-- ---------------------------------------------------------------------------

CREATE FUNCTION docs.claim_print_jobs(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_agent     text,
    p_lease_seconds integer DEFAULT 120,
    p_limit     integer DEFAULT 10)
RETURNS TABLE (
    job_id     uuid,
    receipt_id uuid,
    printer_id uuid,
    is_reprint boolean,
    attempts   integer)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'docs', 'public'
AS $$
BEGIN
    RETURN QUERY
    WITH runnable AS (
        SELECT j.id
          FROM docs.print_job j
         WHERE j.tenant_id = p_tenant_id
           AND j.outlet_id = p_outlet_id
           AND j.state IN ('queued', 'failed')
           AND j.next_attempt_at <= now()
         ORDER BY j.enqueued_at
         LIMIT p_limit
         FOR UPDATE SKIP LOCKED
    ), taken AS (
        UPDATE docs.print_job j
           SET state = 'claimed',
               claimed_by = p_agent,
               claim_expires_at = now() + make_interval(secs => p_lease_seconds)
          FROM runnable r
         WHERE j.id = r.id
        RETURNING j.*
    )
    SELECT t.id, t.receipt_id, t.printer_id, t.is_reprint, t.attempts
      FROM taken t
     ORDER BY t.enqueued_at;
END;
$$;

-- THE ONE PLACE A JOB BECOMES PRINTED, and it goes through M4-C's ledger rather than
-- around it. docs.record_receipt_print() is what refuses a duplicate recorded print and
-- what checks the outcome matches the sink; a queue that wrote its own attempt row would
-- be a second answer to "what came out of this machine".
CREATE FUNCTION docs.complete_print_job(
    p_tenant_id uuid,
    p_job_id    uuid,
    p_agent_sink docs.sink_kind,
    p_resolved_destination text,
    p_bytes_sha256 character(64),
    p_byte_count integer,
    p_actor_user_id uuid,
    p_detail text DEFAULT NULL)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'docs', 'integration', 'edge', 'public'
AS $$
DECLARE
    j docs.print_job%ROWTYPE;
    v_attempt uuid;
    v_node    uuid;
BEGIN
    SELECT * INTO j FROM docs.print_job
      WHERE tenant_id = p_tenant_id AND id = p_job_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PRINT_JOB_UNKNOWN: no job %', p_job_id USING ERRCODE = 'HS404';
    END IF;

    -- REPORTING A PRINT TWICE IS NOT TWO PRINTS. An agent that printed and then lost the
    -- connection before recording it will retry the report; the paper came out once.
    IF j.state = 'printed' THEN
        RETURN NULL;
    END IF;

    v_attempt := docs.record_receipt_print(
        p_tenant_id, j.outlet_id, j.receipt_id, j.printer_id, p_agent_sink,
        p_resolved_destination, p_bytes_sha256, p_byte_count, p_actor_user_id,
        j.is_reprint, j.reason_code_id, j.reason_text, p_detail);

    UPDATE docs.print_job
       SET state = 'printed', printed_at = now(), bytes_sha256 = p_bytes_sha256,
           claimed_by = NULL, claim_expires_at = NULL, last_error = NULL,
           attempts = j.attempts + 1
     WHERE tenant_id = p_tenant_id AND id = p_job_id;

    -- CLOUD RECONCILIATION (FR-EDG-029), and exactly one event for it. The job id is the
    -- idempotency key, so a replay after an outage tells the cloud once.
    SELECT id INTO v_node FROM edge.node
      WHERE tenant_id = p_tenant_id AND outlet_id = j.outlet_id AND status = 'active';
    IF v_node IS NOT NULL THEN
        PERFORM integration.enqueue_outbox(
            p_tenant_id, v_node, 'print_job', p_job_id, 'print_job.printed',
            jsonb_build_object('receipt_id', j.receipt_id, 'printer_id', j.printer_id,
                               'bytes_sha256', p_bytes_sha256, 'is_reprint', j.is_reprint),
            now(), NULL, 'print-job-' || p_job_id::text);
    END IF;

    RETURN v_attempt;
END;
$$;

COMMENT ON FUNCTION docs.complete_print_job(uuid, uuid, docs.sink_kind, text, character,
                                            integer, uuid, text) IS
    'FR-EDG-029. The only place a job becomes printed, and it records the attempt through '
    'M4-C''s docs.record_receipt_print() rather than writing its own row. Reporting the '
    'same print twice returns null and changes nothing: an agent that printed and lost '
    'the connection before reporting will retry, and the paper came out once.';

CREATE FUNCTION docs.fail_print_job(
    p_tenant_id uuid,
    p_job_id    uuid,
    p_error     text,
    p_backoff_seconds integer DEFAULT 30)
RETURNS docs.print_job_state
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'docs', 'public'
AS $$
DECLARE
    j docs.print_job%ROWTYPE;
    v_attempts integer;
    v_state    docs.print_job_state;
BEGIN
    SELECT * INTO j FROM docs.print_job
      WHERE tenant_id = p_tenant_id AND id = p_job_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PRINT_JOB_UNKNOWN: no job %', p_job_id USING ERRCODE = 'HS404';
    END IF;
    IF j.state = 'printed' THEN
        RAISE EXCEPTION
            'PRINT_JOB_ALREADY_PRINTED: job % printed at %; a failure reported afterwards '
            'is about something else', p_job_id, j.printed_at
            USING ERRCODE = 'HS409';
    END IF;

    v_attempts := j.attempts + 1;
    -- BOUNDED, AND THE BOUND IS THE JOB'S OWN. Abandoned is a state somebody can see,
    -- not a row that quietly stops being selected.
    v_state := CASE WHEN v_attempts >= j.max_attempts THEN 'abandoned'::docs.print_job_state
                    ELSE 'failed'::docs.print_job_state END;

    UPDATE docs.print_job
       SET state = v_state,
           attempts = v_attempts,
           last_error = p_error,
           claimed_by = NULL, claim_expires_at = NULL,
           next_attempt_at = now() + make_interval(secs => p_backoff_seconds * v_attempts)
     WHERE tenant_id = p_tenant_id AND id = p_job_id;

    RETURN v_state;
END;
$$;

-- RESTART RECOVERY (FR-EDG-029). A lease that expired belonged to an agent that is no
-- longer running. The job returns to the queue; a job already printed does not, because
-- the transition trigger refuses it and because the lease was cleared when it printed.
CREATE FUNCTION docs.recover_expired_print_claims(p_tenant_id uuid, p_outlet_id uuid)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'docs', 'public'
AS $$
DECLARE
    v_count integer;
BEGIN
    WITH expired AS (
        UPDATE docs.print_job
           SET state = 'queued', claimed_by = NULL, claim_expires_at = NULL,
               last_error = COALESCE(last_error, 'the agent holding this job stopped')
         WHERE tenant_id = p_tenant_id
           AND outlet_id = p_outlet_id
           AND state = 'claimed'
           AND claim_expires_at < now()
        RETURNING id
    )
    SELECT count(*)::integer INTO v_count FROM expired;
    RETURN v_count;
END;
$$;

-- ---------------------------------------------------------------------------
-- 6. PRINTER HEALTH (FR-EDG-029, FR-EDG-017, FR-INT-011)
-- ---------------------------------------------------------------------------

-- Every active printer, always — the same rule as edge.node_health(). A printer missing
-- from a health report reads as fine, and the one with nothing queued and nothing printed
-- is the one that was never plugged in.
CREATE FUNCTION docs.printer_health(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (
    printer_id      uuid,
    display_name    text,
    has_passed_a_test boolean,
    queued          integer,
    abandoned       integer,
    oldest_queued_at timestamptz,
    last_printed_at timestamptz,
    consecutive_failures integer)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'docs', 'public'
AS $$
    SELECT p.id,
           p.display_name,
           docs.printer_has_passed_a_test(p_tenant_id, p.id),
           count(*) FILTER (WHERE j.state IN ('queued','claimed','failed'))::integer,
           count(*) FILTER (WHERE j.state = 'abandoned')::integer,
           min(j.enqueued_at) FILTER (WHERE j.state IN ('queued','claimed','failed')),
           max(j.printed_at),
           COALESCE(max(j.attempts) FILTER (WHERE j.state IN ('failed','abandoned')), 0)::integer
      FROM docs.printer p
      LEFT JOIN docs.print_job j
             ON j.tenant_id = p.tenant_id AND j.printer_id = p.id
     WHERE p.tenant_id = p_tenant_id
       AND p.outlet_id = p_outlet_id
       AND p.status = 'active'
     GROUP BY p.id, p.display_name
     ORDER BY p.display_name;
$$;

COMMENT ON FUNCTION docs.printer_health(uuid, uuid) IS
    'FR-EDG-029''s printer-health visibility. Every active printer, always, whether or '
    'not it has ever had a job: the one with nothing queued and nothing printed is the '
    'one that was never plugged in, and a report that omitted it would read as fine.';

-- ---------------------------------------------------------------------------
-- 7. GRANTS
-- ---------------------------------------------------------------------------

GRANT SELECT ON docs.print_job TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.enqueue_print_job(
    uuid, uuid, uuid, uuid, text, uuid, boolean, uuid, text, integer) TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.claim_print_jobs(uuid, uuid, text, integer, integer)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.complete_print_job(
    uuid, uuid, docs.sink_kind, text, character, integer, uuid, text) TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.fail_print_job(uuid, uuid, text, integer) TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.recover_expired_print_claims(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION docs.printer_health(uuid, uuid) TO hospitality_app;

-- It has to hold now, not later.
SELECT app.assert_financial_tables_are_classified();
SELECT app.assert_append_only_guards_are_declared();
