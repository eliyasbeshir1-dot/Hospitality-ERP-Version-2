-- 0065: an export is a governed action, and somebody finally asks
--
-- THE FOURTH TIME THIS EXACT SHAPE HAS APPEARED, and it is the last of the ones already
-- registered. `report.export` has been in identity.install_governed_actions() since 0002
-- as strong + step-up + a FIFTEEN-MINUTE window — the only action in the registry whose
-- window is not five minutes — carrying `governed_from_gate = 'M6'`.
--
-- NOTHING HAS EVER CALLED IT. /s/v1/reports/exports/metrics.csv asks for a staff session
-- and nothing more, so an action the registry says is governed from M6 has been ungoverned
-- through M4, M5a and M5b. seeds/0010 wrote the pattern down after OP-C found it with
-- table.seat and OP-D with order.accept: the trigger, an installer for tenants that already
-- exist, and THE CALLER. Here the first two have been in place for sixty-three migrations
-- and the third is what was missing.
--
-- WHY AN EXPORT IS GOVERNED AT ALL, since it only reads. Every other governed action
-- changes something. An export changes nothing and removes a whole outlet's trade — every
-- figure, every window — from the system that has the access controls and into a file that
-- has none. The consequence is not to the data; it is that the data leaves. Fifteen minutes
-- rather than five because an operator assembling a period's figures runs several exports
-- in a sitting, and a window that expired between them would teach them to keep a step-up
-- alive rather than to step up.
--
-- AND WHAT IS RECORDED IS THE FACT OF THE EXPORT. FR-RPT-013 built the export; what it did
-- not build is a way to answer "who took the January figures off this system". A row per
-- export, append-only, is that answer.

-- ---------------------------------------------------------------------------
-- 1. THE EXPORT LEAVES A TRACE
-- ---------------------------------------------------------------------------

CREATE TABLE report.export_event (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,

    export_kind report.export_kind NOT NULL,

    -- The window that left. Not the rows — the rows are in the ledgers and copying them
    -- here would be a second copy of the thing this row exists to say left.
    window_from timestamptz NOT NULL,
    window_to   timestamptz NOT NULL,
    currency    character(3) NOT NULL,

    -- WHO, AND ON WHAT AUTHORITY. The grant is recorded rather than merely checked, so a
    -- later question — "was that export authorised, and by whom" — is answered by the row
    -- instead of by inference from a session that has since expired.
    taken_by_user_id  uuid NOT NULL,
    step_up_grant_id  uuid NOT NULL,

    -- WHAT LEFT, as a size and a digest of the bytes. Enough to recognise the same file
    -- later without holding a copy of an outlet's trade in a second place.
    byte_count  integer NOT NULL,
    body_sha256 character(64) NOT NULL,

    taken_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT export_event_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT export_event_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT export_event_actor_fk FOREIGN KEY (tenant_id, taken_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT export_event_window_is_a_window CHECK (window_to > window_from),
    CONSTRAINT export_event_has_content CHECK (byte_count > 0)
);

COMMENT ON TABLE report.export_event IS
    'FR-RPT-013, FR-AUTH-006. Who took an outlet''s figures off this system, when, for what '
    'window, and on which step-up grant. An export changes nothing and removes everything: '
    'the consequence is not to the data but that the data leaves, into a file with none of '
    'the access controls it had here.';

CREATE INDEX export_event_recent_idx
    ON report.export_event (tenant_id, outlet_id, taken_at DESC);

ALTER TABLE report.export_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE report.export_event FORCE ROW LEVEL SECURITY;
CREATE POLICY export_event_isolation ON report.export_event FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- AN EXPORT THAT HAPPENED HAPPENED. Same reasoning as ops.backup_run and every ledger
-- here: a record of who removed data that can itself be removed answers nothing.
CREATE FUNCTION report.refuse_export_rewrite() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'EXPORT_EVENT_REWRITTEN: an export that happened cannot be edited or deleted. A '
        'record of who took an outlet''s trade off the system is worth exactly as much as '
        'its immutability'
        USING ERRCODE = 'HS409';
END;
$$;

CREATE TRIGGER export_event_is_append_only
    BEFORE UPDATE OR DELETE ON report.export_event
    FOR EACH ROW EXECUTE FUNCTION report.refuse_export_rewrite();

-- ---------------------------------------------------------------------------
-- 2. AND IT MAY NOT HAPPEN WITHOUT A FRESH STEP-UP FOR THIS ACTION
-- ---------------------------------------------------------------------------

CREATE FUNCTION report.record_export(
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
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'report', 'identity', 'public'
AS $$
DECLARE
    v_id uuid;
BEGIN
    -- THE GRANT MUST BE FOR THIS ACTION AND FOR THIS PERSON, which is the clause the
    -- export route never had. Without it any live grant would do: a manager who stepped up
    -- to refund a payment could take the year's figures on the strength of it. FR-AUTH-006
    -- scopes the window per action for exactly this reason, and 0052 had to add the same
    -- clause to edge.claim_authority() for the same reason one gate ago.
    PERFORM 1
       FROM identity.step_up_grant g
       JOIN identity.session s ON s.tenant_id = g.tenant_id AND s.id = g.session_id
       JOIN identity.governed_action a ON a.tenant_id = g.tenant_id
                                      AND a.action_code = g.action_code
      WHERE g.tenant_id = p_tenant_id
        AND g.id = p_step_up_grant_id
        AND g.action_code = 'report.export'
        AND s.user_account_id = p_user_id
        AND now() - g.granted_at <= a.step_up_max_age;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'EXPORT_STEP_UP_ABSENT: step-up grant % is not a fresh report.export grant '
            'belonging to the person asking. An export removes an outlet''s whole trade '
            'into a file with none of the controls it had here, and that should not '
            'proceed on somebody else''s authentication, on a stale one, or on one taken '
            'for a different act',
            p_step_up_grant_id
            USING ERRCODE = 'HS403';
    END IF;

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
    'FR-RPT-013, FR-AUTH-006. The caller `report.export` has been waiting for since 0002. '
    'Refuses without a fresh grant FOR THIS ACTION and belonging to the person asking — the '
    'fourth time that clause has had to be added after the fact, and the last of the '
    'actions that were registered and never demanded.';

-- ---------------------------------------------------------------------------
-- 3. FR-FUL-012: THE TIMES, CONSUMED AS ANALYTICS RATHER THAN COMPUTED
-- ---------------------------------------------------------------------------
--
-- The partial closure's words: "Prep, wait and SLA times compute per station, item and
-- order from timestamps the fold wrote out of the ledger. Consuming them as analytics is
-- operational reporting at M6."
--
-- So the numbers exist and nothing reads them together. This is the reading: one row per
-- station with the three figures side by side, which is what "analytical consumption"
-- means for a kitchen — not a new measurement, a way to look at the ones there are.

CREATE FUNCTION report.kitchen_consumption(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_from timestamptz,
    p_to   timestamptz)
RETURNS TABLE (
    station_node_id uuid,
    station_name    text,
    tickets         bigint,
    lines           bigint,
    preparation_seconds_p50 numeric,
    wait_seconds_p50        numeric,
    sla_breaches            bigint,
    slowest_seconds         numeric)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'report', 'fulfillment', 'org', 'public'
AS $$
    -- READ FROM THE TICKETS THEMSELVES rather than from a projection of them, because
    -- FR-FUL-012 is about consuming what the fold already wrote and a second fold would be
    -- a second thing to keep in step.
    --
    -- THE THREE FIGURES ARE THE THREE THE REQUIREMENT NAMES, off the columns that exist:
    --   prep   ready_at - preparation_started_at, the time the dish was being cooked
    --   wait   collected_at - ready_at, the time it sat on the pass, which is the number
    --          a kitchen argues with a floor about
    --   SLA    tickets that were ready AFTER sla_due_at, counted rather than averaged,
    --          because "how often were we late" and "how late on average" are different
    --          questions and only the first has an answer a manager can act on
    --
    -- percentile_cont rather than avg for the two durations: a mean is dragged by the one
    -- ticket that sat while somebody went to find an ingredient, which is the number a
    -- kitchen least wants to plan against. The maximum is reported beside it, because the
    -- median alone hides exactly that ticket.
    SELECT s.id,
           s.display_name,
           count(DISTINCT t.id),
           count(tl.id),
           round(percentile_cont(0.5) WITHIN GROUP (
               ORDER BY extract(epoch FROM (t.ready_at - t.preparation_started_at))
           )::numeric, 1),
           round(percentile_cont(0.5) WITHIN GROUP (
               ORDER BY extract(epoch FROM (t.collected_at - t.ready_at))
           )::numeric, 1),
           count(DISTINCT t.id) FILTER (
               WHERE t.sla_due_at IS NOT NULL AND t.ready_at > t.sla_due_at),
           round(max(extract(epoch FROM (t.ready_at - t.preparation_started_at)))::numeric, 1)
      FROM fulfillment.ticket t
      JOIN org.org_node s ON s.tenant_id = t.tenant_id AND s.id = t.station_node_id
      LEFT JOIN fulfillment.ticket_line tl
             ON tl.tenant_id = t.tenant_id AND tl.ticket_id = t.id
     WHERE t.tenant_id = p_tenant_id
       AND t.outlet_id = p_outlet_id
       AND t.released_at >= p_from AND t.released_at < p_to
       AND t.ready_at IS NOT NULL
       AND t.preparation_started_at IS NOT NULL
     GROUP BY s.id, s.display_name
     ORDER BY s.display_name;
$$;

COMMENT ON FUNCTION report.kitchen_consumption(uuid, uuid, timestamptz, timestamptz) IS
    'FR-FUL-012. Prep, wait and SLA per station, read from the tickets the fold already wrote '
    'rather than from a second projection of them. The median rather than the mean, with the '
    'maximum beside it: a mean is dragged by the one ticket that sat while somebody went to '
    'find an ingredient, and a median alone hides that ticket entirely. SLA breaches are '
    'COUNTED rather than averaged, because "how often were we late" is the question a '
    'manager can act on.';

GRANT SELECT ON report.export_event TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.record_export(uuid, uuid, report.export_kind, timestamptz,
        timestamptz, character, uuid, uuid, integer, character) TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.kitchen_consumption(uuid, uuid, timestamptz, timestamptz)
    TO hospitality_app;

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

    SELECT count(*) INTO v_rows FROM report.kitchen_consumption(
        v_tenant, v_outlet, now() - interval '30 days', now());
    IF v_rows IS NULL THEN
        RAISE EXCEPTION 'KITCHEN_CONSUMPTION_UNRUNNABLE' USING ERRCODE = 'HS500';
    END IF;
END;
$$;
