-- 0066: a pilot has a checklist, an owner and a way back
--
-- FR-OPS-011, FR-OPS-012 and FR-OPS-015. Three requirements about the same thing: that
-- going live is a decision somebody makes with their name on it, rather than a deploy that
-- happens.
--
--     FR-OPS-011  runbooks for installation, menu publish, table QR issue, printer setup,
--                 outage, reconnection, backup, restore, update, incident, pilot cutover
--     FR-OPS-012  alert severity, owner, acknowledgement and escalation; NO UNOWNED
--                 DASHBOARDS
--     FR-OPS-015  a controlled go-live checklist, a pilot tenant and outlet, a rollback
--                 plan, a data owner and a named operator. No direct production cutover
--                 from an unaudited branch.
--
-- WHY THE RUNBOOKS ARE ROWS AND THE PROSE IS IN docs/. A runbook is a document; whether
-- one EXISTS for each of the eleven situations FR-OPS-011 names is a fact, and a fact that
-- lives only in a folder is one nobody can query at three in the morning. So the register
-- is here and it points at the file. The check is that all eleven are present and that
-- each names the file it is — not that the prose is good, which no database can know.
--
-- WHY MONITORING OWNERSHIP IS A FOREIGN KEY. FR-OPS-012's phrase is "avoid unowned
-- dashboards", and the only way to make that structural rather than aspirational is for
-- the owner to be NOT NULL and to reference a real person. A dashboard whose owner is a
-- team name in a text column is a dashboard nobody owns the moment that team reorganises.
--
-- AND WHY THE CUTOVER CARRIES A COMMIT. "No direct production cutover from an unaudited
-- branch" is the requirement's own sentence, and the only durable form of it is that the
-- cutover row records WHICH COMMIT went live and whether it was reviewed. A cutover that
-- cannot say what it deployed is one nobody can roll back from with confidence, because
-- rolling back needs to know what to roll back TO.

-- ---------------------------------------------------------------------------
-- 1. THE RUNBOOKS FR-OPS-011 NAMES
-- ---------------------------------------------------------------------------

CREATE TYPE ops.runbook_situation AS ENUM (
    'installation', 'menu_publish', 'table_qr_issue', 'printer_setup',
    'outage', 'reconnection', 'backup', 'restore', 'update', 'incident',
    'pilot_cutover');

CREATE TABLE ops.runbook (
    situation ops.runbook_situation PRIMARY KEY,

    -- The file, relative to the repository root. Not the prose: a runbook copied into a
    -- database is a second copy that drifts from the one people actually read.
    document_path text NOT NULL,

    -- WHO ANSWERS WHEN THIS SITUATION HAPPENS. Not the author — the person on the end of
    -- it. FR-OPS-012's "no unowned dashboards" applied to runbooks: a procedure nobody
    -- owns is a procedure that rots.
    owner_role_code text NOT NULL,

    reviewed_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT runbook_path_is_stated CHECK (
        length(trim(document_path)) > 0 AND document_path LIKE 'docs/runbooks/%'),
    CONSTRAINT runbook_owner_is_stated CHECK (length(trim(owner_role_code)) > 0)
);

COMMENT ON TABLE ops.runbook IS
    'FR-OPS-011. One row per situation the requirement names, pointing at the document '
    'rather than containing it — a runbook copied into a database is a second copy that '
    'drifts from the one people read. Whether one EXISTS for each situation is a fact, and '
    'a fact that lives only in a folder is one nobody can query at three in the morning.';

-- IT IS NOT TENANT-SCOPED, and that is deliberate. A runbook is how THIS SYSTEM is
-- operated, not how one restaurant runs; a per-tenant runbook table would invite eleven
-- rows per tenant that are all the same document.
GRANT SELECT ON ops.runbook TO hospitality_app;

-- ---------------------------------------------------------------------------
-- 2. FR-OPS-012: EVERY ALERT HAS AN OWNER WHO IS A PERSON
-- ---------------------------------------------------------------------------

CREATE TYPE ops.alert_severity AS ENUM ('informational', 'warning', 'critical');

CREATE TABLE ops.alert_ownership (
    tenant_id uuid NOT NULL,
    event_id  text NOT NULL,

    severity ops.alert_severity NOT NULL,

    -- THE OWNER IS A ROLE THAT EXISTS, checked by foreign key rather than by spelling. A
    -- text column holding a team name is a column that still says "Platform" after the
    -- platform team is dissolved.
    owner_role_id uuid NOT NULL,

    -- How long before nobody acknowledging it becomes its own problem. FR-OPS-012 asks for
    -- acknowledgement AND escalation, which are two numbers rather than one: an alert
    -- nobody has looked at in five minutes is not yet an incident, and one nobody has
    -- looked at in an hour is.
    acknowledge_within_minutes integer NOT NULL,
    escalate_after_minutes     integer NOT NULL,
    escalate_to_role_id        uuid NOT NULL,

    CONSTRAINT alert_ownership_pkey PRIMARY KEY (tenant_id, event_id),
    CONSTRAINT alert_ownership_event_fk FOREIGN KEY (event_id)
        REFERENCES notify.catalog_event (event_id) ON DELETE RESTRICT,
    CONSTRAINT alert_ownership_owner_fk FOREIGN KEY (tenant_id, owner_role_id)
        REFERENCES identity.role (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT alert_ownership_escalation_fk FOREIGN KEY (tenant_id, escalate_to_role_id)
        REFERENCES identity.role (tenant_id, id) ON DELETE RESTRICT,
    -- ASCENDING, for the reason every threshold pair in this repository ascends: an
    -- escalation that fires before the acknowledgement window closes escalates every alert.
    CONSTRAINT alert_ownership_escalation_is_after CHECK (
        escalate_after_minutes > acknowledge_within_minutes),
    CONSTRAINT alert_ownership_windows_are_sane CHECK (
        acknowledge_within_minutes BETWEEN 1 AND 1440)
);

COMMENT ON TABLE ops.alert_ownership IS
    'FR-OPS-012. Severity, owner, acknowledgement and escalation for every notification '
    'kind that has a producer. The owner is a FOREIGN KEY to a role rather than a team '
    'name in text, because "avoid unowned dashboards" is only structural if an owner has '
    'to exist.';

ALTER TABLE ops.alert_ownership ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.alert_ownership FORCE ROW LEVEL SECURITY;
CREATE POLICY alert_ownership_isolation ON ops.alert_ownership FOR ALL
    USING (app.row_in_scope(tenant_id, NULL))
    WITH CHECK (app.row_in_scope(tenant_id, NULL));

GRANT SELECT ON ops.alert_ownership TO hospitality_app;

-- AND THE CHECK THAT MAKES IT MEAN SOMETHING: every event that can actually be raised has
-- an owner. An ownership table with rows for the easy events and gaps for the hard ones is
-- worse than none, because it looks complete.
CREATE FUNCTION ops.unowned_alerts(p_tenant_id uuid)
RETURNS TABLE (event_id text, milestone text, severity text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'ops', 'notify', 'public'
AS $$
    SELECT c.event_id, c.milestone, c.severity
      FROM notify.catalog_event c
     WHERE c.has_producer
       AND NOT EXISTS (SELECT 1 FROM ops.alert_ownership o
                        WHERE o.tenant_id = p_tenant_id AND o.event_id = c.event_id)
     ORDER BY c.event_id;
$$;

COMMENT ON FUNCTION ops.unowned_alerts(uuid) IS
    'FR-OPS-012. Every event that can actually be raised and has nobody assigned to it. '
    'Producerless events are excluded deliberately: an alert nothing emits needs no owner, '
    'and demanding one would be paperwork rather than accountability.';

GRANT EXECUTE ON FUNCTION ops.unowned_alerts(uuid) TO hospitality_app;

-- ---------------------------------------------------------------------------
-- 3. FR-OPS-015: GOING LIVE IS A DECISION SOMEBODY MAKES
-- ---------------------------------------------------------------------------

CREATE TYPE ops.cutover_state AS ENUM ('planned', 'live', 'rolled_back');

CREATE TABLE ops.cutover (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,

    state ops.cutover_state NOT NULL DEFAULT 'planned',

    -- WHAT WENT LIVE. "No direct production cutover from an unaudited branch" is the
    -- requirement's sentence, and the durable form of it is a commit and a flag saying
    -- whether anybody reviewed it. A cutover that cannot say what it deployed is one
    -- nobody can roll back from, because rolling back needs to know what to roll back TO.
    commit_sha        character(40) NOT NULL,
    reviewed_by_user_id uuid,
    review_verdict    text,

    -- THE TWO PEOPLE FR-OPS-015 NAMES, and they are different columns because they are
    -- different responsibilities: the operator does it, the data owner answers for what
    -- happens to the trade afterwards.
    named_operator_user_id uuid NOT NULL,
    data_owner_user_id     uuid NOT NULL,

    -- THE WAY BACK. Not optional: a cutover plan without one is a plan to hope.
    rollback_plan text NOT NULL,

    planned_at timestamptz NOT NULL DEFAULT now(),
    went_live_at   timestamptz,
    rolled_back_at timestamptz,
    rollback_reason text,

    CONSTRAINT cutover_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT cutover_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cutover_operator_fk FOREIGN KEY (tenant_id, named_operator_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cutover_data_owner_fk FOREIGN KEY (tenant_id, data_owner_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cutover_reviewer_fk FOREIGN KEY (tenant_id, reviewed_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT cutover_commit_is_a_sha CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
    CONSTRAINT cutover_rollback_plan_is_stated CHECK (length(trim(rollback_plan)) > 20),

    -- THE ONE THE REQUIREMENT IS REALLY ABOUT. A cutover may not reach `live` without a
    -- reviewer and a verdict: "no direct production cutover from an unaudited branch",
    -- enforced rather than described.
    CONSTRAINT cutover_live_was_audited CHECK (
        state <> 'live'
        OR (reviewed_by_user_id IS NOT NULL
            AND review_verdict IS NOT NULL
            AND went_live_at IS NOT NULL)),

    -- AND THE OPERATOR MAY NOT BE THEIR OWN REVIEWER. The same reasoning as M5b's
    -- authority claim: without it the audit is a person agreeing with themselves.
    CONSTRAINT cutover_review_is_independent CHECK (
        reviewed_by_user_id IS NULL
        OR reviewed_by_user_id <> named_operator_user_id),

    CONSTRAINT cutover_rollback_is_explained CHECK (
        (state = 'rolled_back') = (rolled_back_at IS NOT NULL)
    AND (rolled_back_at IS NULL) = (rollback_reason IS NULL))
);

COMMENT ON TABLE ops.cutover IS
    'FR-OPS-015. Going live as a decision with names on it: which commit, who reviewed it, '
    'who operated it, who answers for the data, and how to get back. A cutover cannot reach '
    'live without a reviewer who is not the operator — "no direct production cutover from '
    'an unaudited branch", as a CHECK rather than a sentence.';

ALTER TABLE ops.cutover ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.cutover FORCE ROW LEVEL SECURITY;
CREATE POLICY cutover_isolation ON ops.cutover FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

GRANT SELECT ON ops.cutover TO hospitality_app;

-- ---------------------------------------------------------------------------
-- 4. IS THIS OUTLET READY FOR A PILOT?
-- ---------------------------------------------------------------------------
--
-- The question a founder asks before letting a real guest in, answered from the rows
-- rather than from anybody's confidence. Every clause is something an earlier gate built,
-- which is the point: readiness is not a new mechanism, it is the conjunction of the ones
-- that already exist.

CREATE FUNCTION ops.pilot_readiness(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (requirement text, ready boolean, detail text)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'ops', 'edge', 'notify', 'org', 'public'
AS $$
DECLARE
    v_n integer;
    v_text text;
BEGIN
    SELECT count(*) INTO v_n FROM ops.runbook;
    RETURN QUERY SELECT 'runbooks for all eleven situations'::text,
        v_n = 11, format('%s of 11 present', v_n)::text;

    SELECT count(*) INTO v_n FROM ops.unowned_alerts(p_tenant_id);
    RETURN QUERY SELECT 'every raisable alert has an owner'::text,
        v_n = 0, format('%s producible event(s) with nobody assigned', v_n)::text;

    SELECT posture::text INTO v_text FROM ops.backup_posture(p_tenant_id, 'cloud');
    RETURN QUERY SELECT 'the estate has a verified backup'::text,
        v_text IN ('healthy', 'due'), format('backup posture: %s', v_text)::text;

    SELECT count(*) INTO v_n FROM edge.outlet_hostname
     WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id;
    RETURN QUERY SELECT 'the outlet has a name its QR can carry'::text,
        v_n = 1, format('%s hostname(s) declared', v_n)::text;

    SELECT count(*) INTO v_n FROM edge.authority
     WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id AND state = 'held';
    RETURN QUERY SELECT 'exactly one node may write for this outlet'::text,
        v_n = 1, format('%s authority holder(s)', v_n)::text;

    SELECT count(*) INTO v_n FROM ops.cutover
     WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id AND state = 'live';
    RETURN QUERY SELECT 'a reviewed cutover has been recorded'::text,
        v_n >= 1, format('%s live cutover(s), each with a reviewer who is not the '
                         'operator', v_n)::text;
END;
$$;

COMMENT ON FUNCTION ops.pilot_readiness(uuid, uuid) IS
    'FR-OPS-015. Whether a real guest may be let in, answered from rows rather than from '
    'confidence. Every clause is something an earlier gate built — readiness is not a new '
    'mechanism, it is the conjunction of the ones that already exist.';

GRANT EXECUTE ON FUNCTION ops.pilot_readiness(uuid, uuid) TO hospitality_app;

-- RUN, NOT MERELY DEFINED.
DO $$
DECLARE
    v_tenant uuid;
    v_outlet uuid;
    v_rows   integer;
BEGIN
    SELECT tenant_id, id INTO v_tenant, v_outlet
      FROM org.org_node WHERE kind = 'outlet' ORDER BY id LIMIT 1;
    IF v_tenant IS NULL THEN RETURN; END IF;

    SELECT count(*) INTO v_rows FROM ops.pilot_readiness(v_tenant, v_outlet);
    IF v_rows <> 6 THEN
        RAISE EXCEPTION
            'PILOT_READINESS_MISCOUNTED: expected six clauses and got %', v_rows
            USING ERRCODE = 'HS500';
    END IF;
END;
$$;
