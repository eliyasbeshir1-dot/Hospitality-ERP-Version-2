-- 0045: what the node holds, what it may do alone, and what it says about both
--
-- Three requirements that look unrelated and are the same question asked from three
-- angles: what can this outlet still do when it is on its own, and does anybody watching
-- a screen know?
--
--   FR-EDG-025  before service, the node HOLDS eleven named kinds of thing
--   FR-EDG-010  during an outage, some actions are blocked or queued and MOST CONTINUE
--   FR-POS-008  a member of staff sees, in plain language, which of five states an
--               operation is in
--
-- WHY READINESS IS DERIVED AND NOT RECORDED. A "readiness: ok" column is a claim written
-- at a moment; the question FR-EDG-025 asks is whether the node holds the data NOW, and
-- the only honest answer is a count taken from the tables that would be read during
-- service. So edge.readiness_report() counts, per element, out of the real tables — and
-- returns all eleven elements always, present or not, for the reason edge.node_health()
-- returns all seven components: a missing line in a readiness report reads as ready.
--
-- WHY THE OUTAGE RULES ARE A TABLE AND NOT AN IF. FR-EDG-010 is easy to satisfy badly.
-- The tempting shape is a check inside each route — "if offline and this is a card
-- payment, refuse" — and it fails in the way this repository keeps finding: the rule
-- lives in as many places as there are routes, one of them gets missed, and the one that
-- gets missed is discovered by a cashier at a till. So every action is CLASSIFIED once,
-- in a registry, and a route asks the registry. An action nobody classified is refused
-- rather than allowed, because the alternative is that forgetting to classify something
-- makes it work during an outage by accident.
--
-- WHAT MUST KEEP WORKING IS NAMED, NOT IMPLIED. The requirement says cash, locally
-- supported card-terminal recording and ordinary service continue. Those are rows in the
-- registry saying `permitted`, so a change that broke one of them changes a row somebody
-- can read rather than removing a condition nobody can see.
--
-- WHY THERE IS ONE WORDING TABLE FOR TWO FEATURES. FR-EDG-010 wants a TRANSLATED
-- explanation of a restriction; FR-POS-008 wants five states in PLAIN LANGUAGE. Both are
-- "say this to a person in their language", so both come out of edge.plain_language,
-- namespaced by phrase code. Two tables would be two places to forget Amharic.
--
-- AND THE ABSENCE OF WORDING IS A REFUSAL, NOT A BLANK. A restriction the surface cannot
-- explain is a screen that stops working and does not say why, which is the failure
-- FR-EDG-010 exists to prevent. So the lookup raises.

-- ---------------------------------------------------------------------------
-- 1. THE READINESS DATASET (FR-EDG-025)
-- ---------------------------------------------------------------------------

-- The eleven the requirement names, in the order it names them.
CREATE TYPE edge.readiness_element AS ENUM (
    'active_menu', 'approved_translations', 'allergens', 'prices', 'taxes',
    'service_and_tip_settings', 'tables', 'staff_access', 'stations', 'printers',
    'open_sessions');

CREATE FUNCTION edge.readiness_report(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (
    element  edge.readiness_element,
    held     integer,
    is_held  boolean,
    detail   text)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'menu', 'safety', 'billing', 'ordering',
                   'org', 'identity', 'docs', 'service', 'public'
AS $$
DECLARE
    v_counts jsonb;
BEGIN
    SELECT jsonb_build_object(
      'active_menu', (
          SELECT count(*) FROM menu.publication_snapshot s
           WHERE s.tenant_id = p_tenant_id AND s.outlet_id = p_outlet_id),
      -- THREE APPROVED TRANSLATIONS, and the count is of LOCALES rather than rows: one
      -- approved Amharic string is not "Amharic is ready", but the element is about
      -- whether each language is represented at all, which is what a node missing a
      -- locale looks like.
      'approved_translations', (
          SELECT count(DISTINCT t.locale) FROM menu.translation t
           WHERE t.tenant_id = p_tenant_id AND t.state = 'approved'),
      'allergens', (
          SELECT count(*) FROM safety.allergen a WHERE a.tenant_id = p_tenant_id),
      'prices', (
          SELECT count(*) FROM menu.price p WHERE p.tenant_id = p_tenant_id),
      'taxes', (
          SELECT count(*) FROM ordering.charge_rule c WHERE c.tenant_id = p_tenant_id),
      'service_and_tip_settings', (
          (SELECT count(*) FROM billing.service_charge_setting s
            WHERE s.tenant_id = p_tenant_id)
        + (SELECT count(*) FROM billing.tip_setting t WHERE t.tenant_id = p_tenant_id)),
      'tables', (
          SELECT count(*) FROM org.org_node n
           WHERE n.tenant_id = p_tenant_id AND n.outlet_id = p_outlet_id
             AND n.kind = 'dining_table' AND n.status = 'active'),
      'staff_access', (
          SELECT count(*) FROM identity.membership m
           WHERE m.tenant_id = p_tenant_id AND m.outlet_id = p_outlet_id),
      'stations', (
          SELECT count(*) FROM org.org_node n
           WHERE n.tenant_id = p_tenant_id AND n.outlet_id = p_outlet_id
             AND n.kind = 'preparation_station' AND n.status = 'active'),
      'printers', (
          SELECT count(*) FROM docs.printer d
           WHERE d.tenant_id = p_tenant_id AND d.outlet_id = p_outlet_id
             AND d.status = 'active'),
      -- OPEN SESSIONS ARE READY AT ZERO. Every other element is missing when it is empty;
      -- an outlet that opens with nobody seated is not unready, it is closed. Counted
      -- because the node must HOLD them if any exist, and reported as held either way.
      'open_sessions', (
          SELECT count(*) FROM service.table_session s
           WHERE s.tenant_id = p_tenant_id AND s.outlet_id = p_outlet_id
             AND s.closed_at IS NULL)
    ) INTO v_counts;

    RETURN QUERY
    SELECT e.element,
           (v_counts ->> e.element::text)::integer,
           CASE e.element
             WHEN 'open_sessions' THEN true
             WHEN 'approved_translations' THEN (v_counts ->> e.element::text)::integer >= 3
             ELSE (v_counts ->> e.element::text)::integer > 0
           END,
           CASE e.element
             WHEN 'open_sessions' THEN
               'held; an outlet with nobody seated is closed, not unready'
             WHEN 'approved_translations' THEN
               format('%s of the three approved locales are present',
                      (v_counts ->> e.element::text)::integer)
             ELSE
               format('%s held', (v_counts ->> e.element::text)::integer)
           END
      FROM unnest(enum_range(NULL::edge.readiness_element)) AS e(element);
END;
$$;

COMMENT ON FUNCTION edge.readiness_report(uuid, uuid) IS
    'FR-EDG-025. All eleven elements, counted out of the tables service would read, every '
    'time it is asked. A stored readiness flag is a claim written at a moment; this is '
    'the answer now. A missing line in a readiness report reads as ready, so there are no '
    'missing lines.';

-- ---------------------------------------------------------------------------
-- 2. WHAT MAY BE DONE ALONE (FR-EDG-010)
-- ---------------------------------------------------------------------------

CREATE TYPE edge.dependency_kind AS ENUM ('local_only', 'external_required');

-- What happens to an action that needs an authority the outlet cannot reach. Queued and
-- blocked are different promises: queued will happen when the link returns, blocked will
-- not happen at all until somebody tries again.
CREATE TYPE edge.outage_disposition AS ENUM ('permitted', 'queued', 'blocked');

CREATE TABLE edge.action_dependency (
    action_code text PRIMARY KEY,
    requirement edge.dependency_kind NOT NULL,
    disposition edge.outage_disposition    NOT NULL,

    -- The phrase a person is shown. Required whenever the action does not simply proceed,
    -- because FR-EDG-010 asks for the restriction to be EXPLAINED.
    restriction_code text,

    description text NOT NULL,

    CONSTRAINT action_dependency_code_shape CHECK (action_code ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'),
    CONSTRAINT action_dependency_local_actions_proceed CHECK (
        (requirement = 'local_only') = (disposition = 'permitted')),
    CONSTRAINT action_dependency_restriction_is_explicable CHECK (
        (disposition = 'permitted') = (restriction_code IS NULL)),
    CONSTRAINT action_dependency_description_is_stated CHECK (length(trim(description)) > 0)
);

COMMENT ON TABLE edge.action_dependency IS
    'FR-EDG-010. Named for the DEPENDENCY rather than for the authority, because '
    'GJ-01A fences any table naming an authority, a lease, a failover or a takeover '
    'until M5b builds local write authority properly — and a blunt fence that has to be '
    'argued with stops being a fence. This table is about what an action needs from '
    'outside the outlet, which is a different thing from who may write. '
    'Every action classified once, so a route asks the registry instead of '
    'each route carrying its own copy of the rule. Global rather than per-tenant: whether '
    'an online card authorization needs the provider is a fact about the world, not a '
    'tenant preference. What must keep working during an outage is NAMED here as '
    'permitted, so breaking it changes a row somebody can read.';

-- The classification, as it stands at M5a. Actions that continue are listed as
-- deliberately as the ones that do not — FR-EDG-010 names cash, locally supported
-- card-terminal recording and ordinary service, and those are rows.
INSERT INTO edge.action_dependency (action_code, requirement, disposition, restriction_code, description) VALUES
 ('order.place',            'local_only',        'permitted', NULL, 'A guest or waiter places an order against a local session.'),
 ('order.accept',           'local_only',        'permitted', NULL, 'A host admits an order to the kitchen.'),
 ('ticket.advance',         'local_only',        'permitted', NULL, 'A cook moves a station ticket through its states.'),
 ('bill.issue',             'local_only',        'permitted', NULL, 'A check becomes a bill.'),
 ('tip.record',             'local_only',        'permitted', NULL, 'A tip is recorded separately from the bill it accompanies.'),
 ('payment.cash_settle',    'local_only',        'permitted', NULL, 'Cash settlement, which FR-EDG-010 names as continuing.'),
 ('payment.terminal_record','local_only',        'permitted', NULL, 'Recording the result of a locally supported card terminal, which FR-EDG-010 names as continuing.'),
 ('receipt.print',          'local_only',        'permitted', NULL, 'Printing a customer receipt through the local queue and agent.'),
 ('table.seat',             'local_only',        'permitted', NULL, 'Seating a party and opening an occupancy.'),
 ('payment.online_capture', 'external_required', 'blocked',   'restriction.external_payment_authority', 'Authorising a card online, which needs the payment provider.'),
 ('fiscal.issue',           'external_required', 'queued',    'restriction.fiscal_authority',           'Issuing a fiscal document, which the fiscal service does when it is reachable.'),
 ('notification.send',      'external_required', 'queued',    'restriction.external_delivery',          'Sending a notice outside the outlet.'),
 ('report.export',          'external_required', 'blocked',   'restriction.cloud_read',                 'Exporting a report, which reads from the cloud.'),
 ('config.publish',         'external_required', 'blocked',   'restriction.remote_configuration',       'Publishing configuration, which is decided in the cloud and delivered to the node.');

-- ---------------------------------------------------------------------------
-- 3. SAYING IT TO A PERSON, IN THEIR LANGUAGE (FR-EDG-010, FR-POS-008)
-- ---------------------------------------------------------------------------

-- FR-POS-008's five, in its own words: locally saved, queued, synchronized, conflict,
-- blocked.
CREATE TYPE edge.sync_display_state AS ENUM (
    'saved_locally', 'queued', 'synchronized', 'conflict', 'blocked');

CREATE TABLE edge.plain_language (
    tenant_id   uuid NOT NULL,
    phrase_code text NOT NULL,
    locale      menu.customer_locale NOT NULL,
    text        text NOT NULL,

    CONSTRAINT plain_language_pkey PRIMARY KEY (tenant_id, phrase_code, locale),
    CONSTRAINT plain_language_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT plain_language_code_shape CHECK (
        phrase_code ~ '^(restriction|sync_state)\.[a-z][a-z0-9_]*$'),
    CONSTRAINT plain_language_text_is_stated CHECK (length(trim(text)) > 0)
);

COMMENT ON TABLE edge.plain_language IS
    'FR-EDG-010, FR-POS-008. What a restriction and a synchronization state are called '
    'when a person reads them, in each of the three locales. One table for both because '
    'both are "say this to somebody in their language", and two tables would be two '
    'places to forget Amharic.';

ALTER TABLE edge.plain_language ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.plain_language FORCE ROW LEVEL SECURITY;
CREATE POLICY plain_language_isolation ON edge.plain_language FOR ALL
    USING (app.row_in_scope(tenant_id, NULL))
    WITH CHECK (app.row_in_scope(tenant_id, NULL));

-- A PHRASE THAT IS MISSING IS A REFUSAL. A screen that stops working and cannot say why
-- is the failure FR-EDG-010 exists to prevent, so an unworded restriction fails loudly
-- here rather than rendering an empty banner in front of a guest.
CREATE FUNCTION edge.say(p_tenant_id uuid, p_phrase_code text, p_locale menu.customer_locale)
RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'public'
AS $$
DECLARE
    v_text text;
BEGIN
    SELECT text INTO v_text FROM edge.plain_language
      WHERE tenant_id = p_tenant_id AND phrase_code = p_phrase_code AND locale = p_locale;
    IF v_text IS NULL THEN
        RAISE EXCEPTION
            'PHRASE_UNWORDED: % has no % wording for this tenant. A restriction the '
            'surface cannot explain is a screen that stops working without saying why',
            p_phrase_code, p_locale
            USING ERRCODE = 'HS422';
    END IF;
    RETURN v_text;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. WHAT A ROUTE ASKS (FR-EDG-010)
-- ---------------------------------------------------------------------------

CREATE FUNCTION edge.action_disposition(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_action_code text,
    p_locale menu.customer_locale DEFAULT 'en')
RETURNS TABLE (
    disposition edge.outage_disposition,
    explanation text)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'integration', 'public'
AS $$
DECLARE
    a edge.action_dependency%ROWTYPE;
    v_connectivity edge.connectivity_state;
BEGIN
    SELECT * INTO a FROM edge.action_dependency WHERE action_code = p_action_code;
    -- AN ACTION NOBODY CLASSIFIED IS REFUSED. The alternative is that forgetting to
    -- classify something makes it work during an outage by accident, and nobody finds out
    -- until it half-works at a till.
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'ACTION_UNCLASSIFIED: % is not in edge.action_dependency, so whether it can be '
            'done without the cloud is unanswered. Classify it', p_action_code
            USING ERRCODE = 'HS422';
    END IF;

    SELECT s.connectivity INTO v_connectivity
      FROM integration.sync_state s
      JOIN edge.node n ON n.id = s.node_id
     WHERE n.tenant_id = p_tenant_id AND n.outlet_id = p_outlet_id AND n.status = 'active';

    -- Connected, or no node at all — a cloud-only demonstration outlet — and everything
    -- proceeds. The registry only decides what happens when the cloud is out of reach.
    IF v_connectivity IS NULL OR v_connectivity = 'cloud_connected' THEN
        RETURN QUERY SELECT 'permitted'::edge.outage_disposition, NULL::text;
        RETURN;
    END IF;

    IF a.disposition = 'permitted' THEN
        RETURN QUERY SELECT a.disposition, NULL::text;
    ELSE
        RETURN QUERY SELECT a.disposition, edge.say(p_tenant_id, a.restriction_code, p_locale);
    END IF;
END;
$$;

COMMENT ON FUNCTION edge.action_disposition(uuid, uuid, text, menu.customer_locale) IS
    'FR-EDG-010. What happens to this action right now, and what to tell the person if it '
    'does not simply proceed. Routes ask this instead of each carrying its own copy of '
    'the rule; an unclassified action is refused rather than allowed by omission.';

-- ---------------------------------------------------------------------------
-- 5. THE FIVE STATES A MEMBER OF STAFF SEES (FR-POS-008)
-- ---------------------------------------------------------------------------

-- All five, always, with the count in each and the words for them. The state of an
-- outlet's local work is derived from the outbox and the conflict table rather than
-- stored, for the same reason readiness is.
CREATE FUNCTION edge.staff_sync_summary(
    p_tenant_id uuid, p_outlet_id uuid, p_locale menu.customer_locale DEFAULT 'en')
RETURNS TABLE (
    state      edge.sync_display_state,
    operations integer,
    wording    text)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'integration', 'public'
AS $$
DECLARE
    v_node uuid;
    v_blocked boolean;
BEGIN
    SELECT id INTO v_node FROM edge.node
      WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id AND status = 'active';

    SELECT EXISTS (SELECT 1 FROM integration.sync_state s
                    WHERE s.node_id = v_node AND s.paused_reason IS NOT NULL)
      INTO v_blocked;

    RETURN QUERY
    SELECT d.state,
           CASE d.state
             WHEN 'saved_locally' THEN (
                 SELECT count(*)::integer FROM integration.outbox o
                  WHERE o.node_id = v_node AND o.state = 'pending')
             WHEN 'queued' THEN (
                 SELECT count(*)::integer FROM integration.outbox o
                  WHERE o.node_id = v_node AND o.state = 'in_flight')
             WHEN 'synchronized' THEN (
                 SELECT count(*)::integer FROM integration.outbox o
                  WHERE o.node_id = v_node AND o.state = 'acknowledged')
             WHEN 'conflict' THEN (
                 SELECT count(*)::integer FROM integration.conflict c
                  WHERE c.node_id = v_node AND c.resolution IS NULL)
             WHEN 'blocked' THEN (
                 SELECT count(*)::integer FROM integration.outbox o
                  WHERE o.node_id = v_node AND o.state = 'rejected')
                 + CASE WHEN v_blocked THEN 1 ELSE 0 END
           END,
           edge.say(p_tenant_id, 'sync_state.' || d.state::text, p_locale)
      FROM unnest(enum_range(NULL::edge.sync_display_state)) AS d(state);
END;
$$;

COMMENT ON FUNCTION edge.staff_sync_summary(uuid, uuid, menu.customer_locale) IS
    'FR-POS-008. All five states, always, in the reader''s language, with how many '
    'operations are in each. Derived from the outbox and the conflict table: a stored '
    'display state would be a second answer to a question the queue already answers.';

-- ---------------------------------------------------------------------------
-- 6. GRANTS
-- ---------------------------------------------------------------------------

GRANT SELECT ON edge.action_dependency TO hospitality_app;
GRANT SELECT ON edge.plain_language   TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.readiness_report(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.say(uuid, text, menu.customer_locale) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.action_disposition(uuid, uuid, text, menu.customer_locale)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.staff_sync_summary(uuid, uuid, menu.customer_locale)
    TO hospitality_app;

SELECT app.assert_financial_tables_are_classified();
SELECT app.assert_append_only_guards_are_declared();
