-- ===========================================================================
-- 0029 — Reporting: a catalog that is the metrics, and a snapshot recomputation
--        cannot rewrite
-- ===========================================================================
-- FR-RPT-001 role dashboards, FR-RPT-002 source and freshness, FR-RPT-003 sales
-- classified separately, FR-RPT-004 service, FR-RPT-005 kitchen and expo,
-- FR-RPT-013 exports scoped by tenant and outlet, FR-RPT-014 signed-off snapshots,
-- FR-RPT-015 the versioned metric catalog, FR-UX-014 no fabricated analytics.
--
-- THE FOUR DECISIONS IN THIS FILE, stated before the SQL, because each of them is the
-- reason a later reader will find something here shaped oddly.
--
-- ONE. THE CATALOG IS NOT A DOCUMENT ABOUT THE METRICS; IT IS THE LIST OF THEM.
-- report.metric_key is an enum, report.metric has one row per label, and the reading
-- constructor refuses a metric it cannot find. A metric that exists and is not in the
-- catalog cannot be constructed, and a catalog row describing a metric that does not
-- exist cannot be written, because the key is of the enum type. planning/METRIC_CATALOG.md
-- is GENERATED from these rows against a live database; it is a rendering of the catalog
-- and not a second copy of it. FR-RPT-015 asks for a versioned catalog and the version is
-- report.catalog_version(), one function, cited by every snapshot.
--
-- TWO. A READING CARRIES ITS SOURCE AND ITS FRESHNESS OR IT CANNOT BE BUILT.
-- report.reading is a composite type and report.reading() is the only constructor. It
-- refuses a NULL source and a NULL computation time, so FR-RPT-002's labelling is a
-- property of the value rather than a thing the surface is supposed to remember to draw.
-- Freshness is TWO facts, deliberately: computed_at says when the arithmetic ran, and
-- latest_source_row_at says how recent the data under it was. One number cannot say both,
-- and a report computed a second ago over data from yesterday is exactly the case where
-- the difference matters.
--
-- THREE. FR-UX-014 IS ENFORCED AT THE CONSTRUCTOR, AND IT NEEDED A DISTINCTION.
-- "Never display fabricated analytics" is not "never display zero": no orders in a quiet
-- hour is a true count of zero, and reporting it as "no data" would be its own lie. What
-- IS fabricated is a median preparation time over no tickets — zero seconds is not a
-- summary of an empty set, it is an invention. So the catalog declares, per metric,
-- whether an empty window has a defined value, and report.reading() raises
-- FABRICATED_METRIC when a reading disagrees with that declaration in either direction.
-- The surface then renders NULL as the instructive empty state FR-UX-014 asks for.
--
-- FOUR. THE SNAPSHOT IS NOT PROTECTED BY A PROMISE NOT TO RECOMPUTE.
-- FR-RPT-014's sharp clause is that "a recomputation cannot SILENTLY rewrite a signed-off
-- shift result", and the word doing the work is silently. Recomputation is legitimate and
-- must stay possible. What must be impossible is that it lands on top of the signed-off
-- figures. So: the snapshot tables are append-only by trigger and classified as ledgers,
-- there is no UPDATE grant on either of them, the snapshot is written by a trigger at the
-- moment of sign-off rather than by anybody's call, and report.recompute_shift_snapshot()
-- writes into report.recomputation and report.snapshot_divergence — never into the
-- snapshot. A recomputation that disagrees produces a row saying so. It is louder than
-- the original, which is the correct direction for this to fail in.
--
-- WHAT THIS FILE DOES NOT DO. It builds no dashboard rendering, because the dashboard
-- surfaces are the API and PWA layer's; it defines which panels each Phase 1 role has and
-- refuses to define one for a role Phase 1 does not have. The technical-operator dashboard
-- is M5a's — the package says so in FR-RPT-001's later_behavior — and there is no enum
-- label for it here, so it cannot be half-built by accident.

-- ===========================================================================
-- The schema
-- ===========================================================================

CREATE SCHEMA report;

COMMENT ON SCHEMA report IS
    'FR-RPT. Metric definitions, the readings computed from them, the snapshots taken at '
    'shift sign-off, and the exports. It owns no operational fact: every figure here is '
    'derived from a table in another schema, and every reading names the relation it '
    'came from.';


-- ===========================================================================
-- The metric catalog (FR-RPT-015)
-- ===========================================================================

CREATE TYPE report.metric_key AS ENUM (
    -- Sales (FR-RPT-003). Seven classifications, and the eighth label below exists
    -- because a tip that was given back is not a smaller tip.
    'orders_placed',
    'item_sales_minor',
    'discounts_minor',
    'service_charges_minor',
    'taxes_minor',
    'bill_payments_minor',
    'tips_minor',
    'tip_reversals_minor',

    -- Service (FR-RPT-004)
    'service_requests_raised',
    'service_acknowledgement_seconds_p50',
    'service_completion_seconds_p50',
    'table_session_seconds_p50',
    'service_exceptions_unresolved',

    -- Kitchen, bar and expo (FR-RPT-005)
    'kitchen_queue_depth',
    'kitchen_preparation_seconds_p50',
    'kitchen_ready_to_serve_seconds_p50',
    'kitchen_rework_events',
    'kitchen_exceptions'
);

COMMENT ON TYPE report.metric_key IS
    'Every Phase 1 metric, as a closed type. This is what makes FR-RPT-015 a catalog OF '
    'the metrics rather than a document beside them: a reading is typed by this, so a '
    'metric outside the catalog cannot be computed, and a panel naming a metric outside '
    'it cannot be stored. It is also why no fenced domain can reach the reporting '
    'surface through a data row — a panel names a label of this type or nothing.';

CREATE TYPE report.metric_unit AS ENUM ('minor_currency', 'count', 'seconds');

COMMENT ON TYPE report.metric_unit IS
    'What a metric value means. Values are bigint across all three because a metric '
    'value is not always money; the unit says how to read it and, for minor_currency, '
    'a currency sits beside the figure on the row that carries it.';

CREATE TABLE report.metric (
    key   report.metric_key PRIMARY KEY,
    unit  report.metric_unit NOT NULL,
    title text NOT NULL,

    -- FR-RPT-015 names five things a catalog entry must define. They are five columns
    -- rather than one description, so a missing one is a NOT NULL violation instead of
    -- a sentence somebody forgot to write.
    formula        text NOT NULL,
    timezone_rule  text NOT NULL,
    currency_rule  text NOT NULL,
    inclusion_rule text NOT NULL,
    source_relation regclass NOT NULL,

    -- FR-UX-014, declared per metric. TRUE means an empty window has a defined value and
    -- that value is zero — no orders is genuinely zero orders. FALSE means an empty
    -- window has NO value, and reporting one would be an invention: the median
    -- preparation time over no tickets is not zero seconds.
    empty_window_is_zero boolean NOT NULL,
    empty_window_reason  text NOT NULL,

    CONSTRAINT metric_title_not_blank CHECK (btrim(title) <> ''),
    CONSTRAINT metric_formula_not_blank CHECK (btrim(formula) <> ''),
    CONSTRAINT metric_timezone_rule_not_blank CHECK (btrim(timezone_rule) <> ''),
    CONSTRAINT metric_currency_rule_not_blank CHECK (btrim(currency_rule) <> ''),
    CONSTRAINT metric_inclusion_rule_not_blank CHECK (btrim(inclusion_rule) <> ''),
    CONSTRAINT metric_empty_window_reason_not_blank CHECK (btrim(empty_window_reason) <> ''),

    -- NOT A SECOND IDENTITY: key is already the primary key. This adds the unit to it so
    -- a snapshot row can name (metric, unit) as a foreign key and inherit the unit from
    -- the catalog rather than repeating the catalog's judgement.
    CONSTRAINT metric_unit_anchor UNIQUE (key, unit)
);

COMMENT ON TABLE report.metric IS
    'FR-RPT-015. One row per label of report.metric_key, with the formula, timezone rule, '
    'currency rule, inclusion rule and data source the requirement names. The DO block at '
    'the foot of this migration refuses an uncatalogued label, so the two cannot drift.';

CREATE FUNCTION report.catalog_version() RETURNS integer LANGUAGE sql IMMUTABLE
AS $$ SELECT 1; $$;

COMMENT ON FUNCTION report.catalog_version() IS
    'FR-RPT-015''s version, in one place. Every snapshot records the version it was '
    'computed under, so a snapshot taken before a definition changed can be recognised '
    'as answering a different question rather than as disagreeing about the same one. '
    'A gate that changes a formula increments this in a migration, where it is visible.';


-- The catalog rows. TIMEZONE: every metric is bounded by an instant range and the
-- boundaries are timestamptz, so the window is unambiguous regardless of where it is
-- displayed; the outlet's timezone in org.outlet_profile is what a surface renders it in.
-- That is one rule and it is stated once per row because FR-RPT-015 asks for it per
-- metric, and a shared footnote is the shape a rule takes just before it stops applying
-- to one of the rows.

INSERT INTO report.metric
    (key, unit, title, formula, timezone_rule, currency_rule, inclusion_rule,
     source_relation, empty_window_is_zero, empty_window_reason)
VALUES
('orders_placed', 'count', 'Orders placed',
 'count of orders whose submitted_at falls in the window',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'not a monetary metric',
 'every order in scope regardless of state, because a rejected order was still placed',
 'ordering.customer_order', true,
 'a window with no orders had zero orders, and that is an observation rather than an absence'),

('item_sales_minor', 'minor_currency', 'Item sales',
 'sum of billing.bill_component.amount_minor where the component classifies as item_sales',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'minor units of the bill currency; a window is not summed across currencies',
 'components of bills issued in the window; dispositions are reported separately',
 'billing.bill_component', true,
 'no item sales in a window is a sum over an empty set, which is exactly zero'),

('discounts_minor', 'minor_currency', 'Discounts',
 'sum of billing.bill_component.amount_minor where kind is discount',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'minor units of the bill currency; a window is not summed across currencies',
 'components of bills issued in the window',
 'billing.bill_component', true,
 'no discounts in a window is a sum over an empty set, which is exactly zero'),

('service_charges_minor', 'minor_currency', 'Service charges',
 'sum of billing.bill_component.amount_minor where source_kind is service_configuration',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'minor units of the bill currency; a window is not summed across currencies',
 'components of bills issued in the window',
 'billing.bill_component', true,
 'no service charge in a window is a sum over an empty set, which is exactly zero'),

('taxes_minor', 'minor_currency', 'Taxes',
 'sum of billing.bill_component.amount_minor where kind is tax',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'minor units of the bill currency; a window is not summed across currencies',
 'components of bills issued in the window',
 'billing.bill_component', true,
 'no tax in a window is a sum over an empty set, which is exactly zero'),

('bill_payments_minor', 'minor_currency', 'Bill payments',
 'sum of payments.allocation.amount_minor to bill_balance, net of reversals of those allocations',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'minor units of the payment currency; a window is not summed across currencies',
 'allocations made in the window; a reversal reduces the window it was made in',
 'payments.allocation', true,
 'no payment in a window is a sum over an empty set, which is exactly zero'),

('tips_minor', 'minor_currency', 'Tips',
 'sum of billing.tip.amount_minor chosen in the window',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'minor units of the bill currency; a window is not summed across currencies',
 'tips chosen in the window; corrections are the separate tip_reversals_minor metric',
 'billing.tip', true,
 'no tip in a window is a sum over an empty set, which is exactly zero'),

('tip_reversals_minor', 'minor_currency', 'Tips given back',
 'sum of billing.tip_correction.amount_minor recorded in the window',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'minor units of the bill currency; a window is not summed across currencies',
 'every correction kind, because a refund and a reversal both take money back',
 'billing.tip_correction', true,
 'no correction in a window is a sum over an empty set, which is exactly zero'),

('service_requests_raised', 'count', 'Service requests raised',
 'count of service.service_request rows whose raised_at falls in the window',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'not a monetary metric',
 'every request regardless of outcome',
 'service.service_request', true,
 'a window with no requests had zero requests, and that is an observation'),

('service_acknowledgement_seconds_p50', 'seconds', 'Time to acknowledge a request (median)',
 'discrete median of acknowledged_at minus raised_at, in whole seconds',
 'a duration, so the timezone does not enter it; the window that selects the rows is instants',
 'not a monetary metric',
 'only requests raised in the window AND acknowledged; an unacknowledged request has no duration to summarise',
 'service.service_request', false,
 'the median of an empty set is undefined; zero seconds would say every request was acknowledged instantly'),

('service_completion_seconds_p50', 'seconds', 'Time to complete a request (median)',
 'discrete median of completed_at minus raised_at, in whole seconds',
 'a duration, so the timezone does not enter it; the window that selects the rows is instants',
 'not a monetary metric',
 'only requests raised in the window AND completed',
 'service.service_request', false,
 'the median of an empty set is undefined; zero seconds would say every request completed instantly'),

('table_session_seconds_p50', 'seconds', 'Table session duration (median)',
 'discrete median of closed_at minus opened_at, in whole seconds',
 'a duration, so the timezone does not enter it; the window that selects the rows is instants',
 'not a monetary metric',
 'only sessions opened in the window AND closed; an open session has no duration yet',
 'service.table_session', false,
 'the median of an empty set is undefined; zero seconds would say every table turned over instantly'),

('service_exceptions_unresolved', 'count', 'Unresolved service exceptions',
 'count of service.session_closure_exception rows recorded in the window',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'not a monetary metric',
 'every closure exception, because each is a session closed over something outstanding',
 'service.session_closure_exception', true,
 'a window with no exceptions had zero of them, and that is an observation'),

('kitchen_queue_depth', 'count', 'Tickets awaiting a station',
 'count of fulfillment.ticket rows released in the window and still queued or acknowledged',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'not a monetary metric',
 'tickets released in the window whose state has not reached preparing',
 'fulfillment.ticket', true,
 'a window with nothing waiting had zero waiting, and that is an observation'),

('kitchen_preparation_seconds_p50', 'seconds', 'Preparation time (median)',
 'discrete median of ready_at minus preparation_started_at, in whole seconds',
 'a duration, so the timezone does not enter it; the window that selects the rows is instants',
 'not a monetary metric',
 'only tickets released in the window that both started and became ready',
 'fulfillment.ticket', false,
 'the median of an empty set is undefined; zero seconds would say every dish was instant'),

('kitchen_ready_to_serve_seconds_p50', 'seconds', 'Ready to collected (median)',
 'discrete median of collected_at minus ready_at, in whole seconds',
 'a duration, so the timezone does not enter it; the window that selects the rows is instants',
 'not a monetary metric',
 'only tickets released in the window that became ready and were collected',
 'fulfillment.ticket', false,
 'the median of an empty set is undefined; zero seconds would say nothing ever sat under the pass'),

('kitchen_rework_events', 'count', 'Rework',
 'count of fulfillment.ticket_recall rows recorded in the window',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'not a monetary metric',
 'every recall, because each one is a plate that came back',
 'fulfillment.ticket_recall', true,
 'a window with no recalls had zero of them, and that is an observation'),

('kitchen_exceptions', 'count', 'Kitchen exceptions',
 'count of fulfillment.waste_event rows recorded in the window',
 'window boundaries are instants; the outlet timezone in org.outlet_profile renders them',
 'not a monetary metric',
 'every waste event kind',
 'fulfillment.waste_event', true,
 'a window with no exceptions had zero of them, and that is an observation');


-- ===========================================================================
-- A reading, and the only door into one (FR-RPT-002, FR-UX-014)
-- ===========================================================================

CREATE TYPE report.reading AS (
    metric              report.metric_key,
    unit                report.metric_unit,
    value               bigint,
    currency_code       char(3),
    observation_count   bigint,
    source              regclass,
    computed_at         timestamptz,
    latest_source_row_at timestamptz
);

COMMENT ON TYPE report.reading IS
    'One metric value with everything FR-RPT-002 requires attached to it: the relation it '
    'came from and two freshness facts. A composite type rather than loose columns so '
    'that no caller can return a number without them.';

CREATE FUNCTION report.reading(
    p_metric report.metric_key,
    p_value bigint,
    p_currency_code char(3),
    p_observation_count bigint,
    p_latest_source_row_at timestamptz)
RETURNS report.reading
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    m report.metric%ROWTYPE;
    r report.reading;
BEGIN
    SELECT * INTO m FROM report.metric WHERE key = p_metric;
    IF NOT FOUND THEN
        -- Unreachable while the DO block at the foot of this file holds, and written
        -- anyway: the enum and the catalog are two locks, and a lock that is only ever
        -- checked by the other one is a lock nobody has tested.
        RAISE EXCEPTION
            'METRIC_UNCATALOGUED: % has no row in report.metric. A figure whose formula, '
            'timezone, currency rule and source are undefined is a number, not a metric',
            p_metric USING ERRCODE = 'HS422';
    END IF;

    IF p_observation_count IS NULL OR p_observation_count < 0 THEN
        RAISE EXCEPTION
            'FABRICATED_METRIC: % was built without saying how many observations it '
            'summarises. A value whose population is unknown cannot be judged honest or '
            'invented, so it is refused', p_metric USING ERRCODE = 'HS422';
    END IF;

    -- FR-UX-014, in the two directions it can be broken.
    IF p_observation_count = 0 THEN
        IF m.empty_window_is_zero THEN
            IF p_value IS DISTINCT FROM 0 THEN
                RAISE EXCEPTION
                    'FABRICATED_METRIC: % summarises an empty window and the catalog says '
                    'that is exactly zero (%), but the value offered was %',
                    p_metric, m.empty_window_reason, coalesce(p_value::text, 'null')
                    USING ERRCODE = 'HS422';
            END IF;
        ELSIF p_value IS NOT NULL THEN
            RAISE EXCEPTION
                'FABRICATED_METRIC: % summarises an empty window and has no defined value '
                'over one (%), but the value offered was %. A surface showing this figure '
                'would be showing an invention',
                p_metric, m.empty_window_reason, p_value USING ERRCODE = 'HS422';
        END IF;
    ELSIF p_value IS NULL THEN
        RAISE EXCEPTION
            'FABRICATED_METRIC: % observed % row(s) and produced no value. An absent '
            'figure over a non-empty population is a computation that failed, and '
            'rendering it as an empty state would hide that',
            p_metric, p_observation_count USING ERRCODE = 'HS422';
    END IF;

    -- FR-RPT-003's currency rule, carried on the row that carries the figure — the same
    -- correction docs.receipt_line took at this gate. A count of orders has no currency
    -- and a sum of money is unreadable without one.
    IF (m.unit = 'minor_currency') <> (p_currency_code IS NOT NULL) THEN
        RAISE EXCEPTION
            'METRIC_CURRENCY_MISMATCH: % is measured in % and was given currency %. A '
            'monetary figure without a currency beside it is read alone and misread; a '
            'count with one implies an exchange rate that does not exist',
            p_metric, m.unit, coalesce(p_currency_code, 'none') USING ERRCODE = 'HS422';
    END IF;

    r.metric := p_metric;
    r.unit := m.unit;
    r.value := p_value;
    r.currency_code := p_currency_code;
    r.observation_count := p_observation_count;
    r.source := m.source_relation;
    r.computed_at := now();
    r.latest_source_row_at := p_latest_source_row_at;
    RETURN r;
END;
$$;

COMMENT ON FUNCTION report.reading(report.metric_key, bigint, char, bigint, timestamptz) IS
    'FR-RPT-002 and FR-UX-014. The only constructor for a reading. It refuses a metric '
    'that is not catalogued, a value over an unknown population, a summary of an empty '
    'window the catalog says has no value, a missing value over a non-empty one, and a '
    'monetary figure with no currency. The source and the computation time are taken '
    'from the catalog and the clock rather than from the caller, so neither can be '
    'omitted or invented.';


-- ===========================================================================
-- Classifying a bill component, with nowhere for money to fall out (FR-RPT-003)
-- ===========================================================================

CREATE TYPE report.sales_classification AS ENUM
    ('orders', 'item_sales', 'discounts', 'service_charges', 'taxes',
     'bill_payments', 'tips');

COMMENT ON TYPE report.sales_classification IS
    'FR-RPT-003''s seven classifications, as separate labels. Tips are one of them and '
    'they are never folded into bill_payments: a tip is the guest''s money moving to '
    'staff, and a report that adds it to takings answers a different question than the '
    'one anybody asked.';

CREATE FUNCTION report.classify_component(
    p_kind ordering.charge_kind, p_source_kind ordering.charge_source_kind)
RETURNS report.sales_classification
LANGUAGE plpgsql IMMUTABLE
AS $$
BEGIN
    -- SOURCE FIRST. A service charge is a fee, but not every fee is a service charge, and
    -- the distinction lives in where the rule came from rather than in the kind.
    IF p_source_kind = 'service_configuration' THEN
        RETURN 'service_charges';
    END IF;

    CASE p_kind
        WHEN 'item_subtotal' THEN RETURN 'item_sales';
        WHEN 'discount'      THEN RETURN 'discounts';
        WHEN 'tax'           THEN RETURN 'taxes';
        ELSE
            -- NO 'OTHER' BUCKET, AND NO SILENT DROP. A fee that came from somewhere this
            -- function does not recognise is money that would otherwise disappear between
            -- the bill and the report — the report would balance, and it would be wrong.
            -- A later gate adding a charge source has to come here and say where it goes.
            RAISE EXCEPTION
                'SALES_COMPONENT_UNCLASSIFIED: a component of kind % from source % has no '
                'classification in FR-RPT-003''s seven. Money that no classification '
                'claims is money the report loses quietly',
                p_kind, p_source_kind USING ERRCODE = 'HS422';
    END CASE;
END;
$$;

COMMENT ON FUNCTION report.classify_component(ordering.charge_kind, ordering.charge_source_kind) IS
    'FR-RPT-003. Maps a bill component onto one of the seven classifications and RAISES '
    'rather than defaulting. tests/m4c asserts the total of the classified components '
    'equals the total of all of them, which is the property this raise protects.';


-- ===========================================================================
-- Computing the metrics (FR-RPT-003, FR-RPT-004, FR-RPT-005)
-- ===========================================================================
-- SECURITY INVOKER, and that is the whole of FR-RPT-013's scoping. This function reads
-- billing, payments, service and fulfillment as the caller, so row level security applies
-- to it exactly as it applies to the caller. It does not filter by tenant and outlet
-- INSTEAD of the database doing it; the explicit predicates below are the second lock,
-- and the reason they are written out is that a function which passes only because of
-- RLS would pass just as well after somebody disabled RLS.
--
-- THE CURRENCY IS A PARAMETER, NOT A DISCOVERY. The catalog says a window is not summed
-- across currencies, and a function that discovered one currency in the data would return
-- a different answer when a second appeared. Asking for the currency means a two-currency
-- outlet gets two reports rather than one wrong one, and an empty window still knows what
-- it is denominated in.
--
-- OBSERVATION COUNTS. For a count metric the population and the value are the same
-- number, which is exactly why a count's empty window is a true zero rather than an
-- absence. For a sum, the population is the number of rows summed. For a median, it is
-- the number of durations that existed to be ordered — and it is the number that decides
-- whether reporting anything at all would be an invention.

CREATE FUNCTION report.metric_values(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_from timestamptz,
    p_to timestamptz,
    p_currency_code char(3))
RETURNS SETOF report.reading
LANGUAGE sql STABLE SECURITY INVOKER
AS $$
WITH
orders AS (
    SELECT count(*)::bigint AS n, max(submitted_at) AS latest
      FROM ordering.customer_order
     WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id
       AND submitted_at >= p_from AND submitted_at < p_to),

components AS (
    SELECT report.classify_component(c.kind, c.source_kind) AS classification,
           c.amount_minor, b.issued_at
      FROM billing.bill_component c
      JOIN billing.bill b ON b.tenant_id = c.tenant_id AND b.id = c.bill_id
     WHERE c.tenant_id = p_tenant_id AND c.outlet_id = p_outlet_id
       AND b.currency_code = p_currency_code
       AND b.issued_at >= p_from AND b.issued_at < p_to),

bill_allocations AS (
    SELECT a.amount_minor, a.allocated_at
      FROM payments.allocation a
     WHERE a.tenant_id = p_tenant_id AND a.outlet_id = p_outlet_id
       AND a.target = 'bill_balance' AND a.currency_code = p_currency_code
       AND a.allocated_at >= p_from AND a.allocated_at < p_to),

bill_reversals AS (
    SELECT r.amount_minor, r.reversed_at
      FROM payments.reversal r
      JOIN payments.allocation a
        ON a.tenant_id = r.tenant_id AND a.id = r.allocation_id
     WHERE r.tenant_id = p_tenant_id AND r.outlet_id = p_outlet_id
       AND a.target = 'bill_balance' AND r.currency_code = p_currency_code
       AND r.reversed_at >= p_from AND r.reversed_at < p_to),

requests AS (
    SELECT raised_at, acknowledged_at, completed_at
      FROM service.service_request
     WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id
       AND raised_at >= p_from AND raised_at < p_to),

sessions AS (
    SELECT opened_at, closed_at
      FROM service.table_session
     WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id
       AND opened_at >= p_from AND opened_at < p_to),

tickets AS (
    SELECT state, released_at, preparation_started_at, ready_at, collected_at
      FROM fulfillment.ticket
     WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id
       AND released_at >= p_from AND released_at < p_to)

-- ---- sales -------------------------------------------------------------
SELECT report.reading('orders_placed', n, NULL, n, latest) FROM orders
UNION ALL
SELECT report.reading('item_sales_minor',
       coalesce(sum(amount_minor), 0)::bigint, p_currency_code,
       count(*)::bigint, max(issued_at))
  FROM components WHERE classification = 'item_sales'
UNION ALL
SELECT report.reading('discounts_minor',
       coalesce(sum(amount_minor), 0)::bigint, p_currency_code,
       count(*)::bigint, max(issued_at))
  FROM components WHERE classification = 'discounts'
UNION ALL
SELECT report.reading('service_charges_minor',
       coalesce(sum(amount_minor), 0)::bigint, p_currency_code,
       count(*)::bigint, max(issued_at))
  FROM components WHERE classification = 'service_charges'
UNION ALL
SELECT report.reading('taxes_minor',
       coalesce(sum(amount_minor), 0)::bigint, p_currency_code,
       count(*)::bigint, max(issued_at))
  FROM components WHERE classification = 'taxes'
UNION ALL
-- Net of reversals, because a payment that was given back is not takings. The population
-- is both sides: an outlet that took one payment and reversed it observed two events, and
-- a report claiming one observation would understate how much happened.
SELECT report.reading('bill_payments_minor',
       ((SELECT coalesce(sum(amount_minor), 0) FROM bill_allocations)
      - (SELECT coalesce(sum(amount_minor), 0) FROM bill_reversals))::bigint,
       p_currency_code,
       ((SELECT count(*) FROM bill_allocations)
      + (SELECT count(*) FROM bill_reversals))::bigint,
       greatest((SELECT max(allocated_at) FROM bill_allocations),
                (SELECT max(reversed_at) FROM bill_reversals)))
UNION ALL
SELECT report.reading('tips_minor',
       coalesce(sum(amount_minor), 0)::bigint, p_currency_code,
       count(*)::bigint, max(chosen_at))
  FROM billing.tip
 WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id
   AND currency_code = p_currency_code
   AND chosen_at >= p_from AND chosen_at < p_to
UNION ALL
-- SEPARATE FROM tips_minor AND NEVER NETTED AGAINST IT. FR-BIL-016 made a tip refund a
-- linked record rather than a smaller tip, and a report that subtracted one from the
-- other would put that decision back where it started.
SELECT report.reading('tip_reversals_minor',
       coalesce(sum(amount_minor), 0)::bigint, p_currency_code,
       count(*)::bigint, max(corrected_at))
  FROM billing.tip_correction
 WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id
   AND currency_code = p_currency_code
   AND corrected_at >= p_from AND corrected_at < p_to

-- ---- service -----------------------------------------------------------
UNION ALL
SELECT report.reading('service_requests_raised',
       count(*)::bigint, NULL, count(*)::bigint, max(raised_at)) FROM requests
UNION ALL
SELECT report.reading('service_acknowledgement_seconds_p50',
       percentile_disc(0.5) WITHIN GROUP (
           ORDER BY floor(extract(epoch FROM (acknowledged_at - raised_at)))::bigint),
       NULL, count(*)::bigint, max(acknowledged_at))
  FROM requests WHERE acknowledged_at IS NOT NULL
UNION ALL
SELECT report.reading('service_completion_seconds_p50',
       percentile_disc(0.5) WITHIN GROUP (
           ORDER BY floor(extract(epoch FROM (completed_at - raised_at)))::bigint),
       NULL, count(*)::bigint, max(completed_at))
  FROM requests WHERE completed_at IS NOT NULL
UNION ALL
SELECT report.reading('table_session_seconds_p50',
       percentile_disc(0.5) WITHIN GROUP (
           ORDER BY floor(extract(epoch FROM (closed_at - opened_at)))::bigint),
       NULL, count(*)::bigint, max(closed_at))
  FROM sessions WHERE closed_at IS NOT NULL
UNION ALL
SELECT report.reading('service_exceptions_unresolved',
       count(*)::bigint, NULL, count(*)::bigint, max(recorded_at))
  FROM service.session_closure_exception
 WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id
   AND recorded_at >= p_from AND recorded_at < p_to

-- ---- kitchen, bar and expo ---------------------------------------------
UNION ALL
SELECT report.reading('kitchen_queue_depth',
       count(*)::bigint, NULL, count(*)::bigint, max(released_at))
  FROM tickets WHERE state IN ('queued', 'acknowledged')
UNION ALL
SELECT report.reading('kitchen_preparation_seconds_p50',
       percentile_disc(0.5) WITHIN GROUP (
           ORDER BY floor(extract(epoch FROM (ready_at - preparation_started_at)))::bigint),
       NULL, count(*)::bigint, max(ready_at))
  FROM tickets WHERE preparation_started_at IS NOT NULL AND ready_at IS NOT NULL
UNION ALL
SELECT report.reading('kitchen_ready_to_serve_seconds_p50',
       percentile_disc(0.5) WITHIN GROUP (
           ORDER BY floor(extract(epoch FROM (collected_at - ready_at)))::bigint),
       NULL, count(*)::bigint, max(collected_at))
  FROM tickets WHERE ready_at IS NOT NULL AND collected_at IS NOT NULL
UNION ALL
SELECT report.reading('kitchen_rework_events',
       count(*)::bigint, NULL, count(*)::bigint, max(recalled_at))
  FROM fulfillment.ticket_recall
 WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id
   AND recalled_at >= p_from AND recalled_at < p_to
UNION ALL
SELECT report.reading('kitchen_exceptions',
       count(*)::bigint, NULL, count(*)::bigint, max(recorded_at))
  FROM fulfillment.waste_event
 WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id
   AND recorded_at >= p_from AND recorded_at < p_to;
$$;

COMMENT ON FUNCTION report.metric_values(uuid, uuid, timestamptz, timestamptz, char) IS
    'FR-RPT-003, FR-RPT-004 and FR-RPT-005. Every catalogued metric for one outlet, one '
    'window and one currency. SECURITY INVOKER, so the caller''s row level security '
    'applies; the explicit tenant and outlet predicates are a second lock rather than the '
    'only one. Every row is built by report.reading(), so no figure can leave here '
    'without its source, its freshness and its population.';


-- ===========================================================================
-- Sales, in the shape FR-RPT-003 asks for
-- ===========================================================================
-- ALL SEVEN CLASSIFICATIONS, ALWAYS. Derived from enum_range so the report cannot omit a
-- classification by having no rows for it — an absent line is indistinguishable from a
-- line nobody computed, and "we do not charge tax" and "the tax query broke" must not
-- render the same.

CREATE FUNCTION report.sales_report(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_from timestamptz,
    p_to timestamptz,
    p_currency_code char(3))
RETURNS TABLE (classification report.sales_classification,
               value bigint,
               currency_code char(3),
               observation_count bigint,
               source regclass,
               computed_at timestamptz,
               latest_source_row_at timestamptz)
LANGUAGE sql STABLE SECURITY INVOKER
AS $$
    SELECT c.classification,
           r.value, r.currency_code, r.observation_count,
           r.source, r.computed_at, r.latest_source_row_at
      FROM (SELECT unnest(enum_range(NULL::report.sales_classification)) AS classification) c
      JOIN LATERAL (
            SELECT (v).* FROM report.metric_values(
                       p_tenant_id, p_outlet_id, p_from, p_to, p_currency_code) v
           ) r
        ON r.metric = CASE c.classification
             WHEN 'orders'          THEN 'orders_placed'::report.metric_key
             WHEN 'item_sales'      THEN 'item_sales_minor'
             WHEN 'discounts'       THEN 'discounts_minor'
             WHEN 'service_charges' THEN 'service_charges_minor'
             WHEN 'taxes'           THEN 'taxes_minor'
             WHEN 'bill_payments'   THEN 'bill_payments_minor'
             WHEN 'tips'            THEN 'tips_minor'
           END
     ORDER BY c.classification;
$$;

COMMENT ON FUNCTION report.sales_report(uuid, uuid, timestamptz, timestamptz, char) IS
    'FR-RPT-003. One row per classification, enumerated from the type rather than from '
    'the data, so a classification with nothing in it is a visible zero and not a missing '
    'line. Tips are their own row and are never added into bill_payments.';


-- ===========================================================================
-- The signed-off snapshot (FR-RPT-014)
-- ===========================================================================
-- WRITTEN BY A TRIGGER AT SIGN-OFF, NOT BY A CALL. A shift reaches 'verified' when
-- somebody other than the cashier has checked the drawer — that is the sign-off, and it
-- is the instant the figures stop being provisional. Hanging the snapshot on the state
-- change rather than on an API call means every path that signs a shift off takes one,
-- including a path a later gate adds without reading this file.

CREATE TABLE report.shift_snapshot (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL,
    outlet_id  uuid NOT NULL,

    -- The shift this answers for. cash.shift is mutable (its transitions are the ledger),
    -- and this is a key into it rather than a copy of it because the shift's identity does
    -- not change; its figures are copied below precisely because they do.
    shift_id   uuid NOT NULL,

    -- WHICH CATALOG THIS WAS COMPUTED UNDER. Without it, a snapshot that disagrees with
    -- a later recomputation is ambiguous between "the data changed" and "the definition
    -- changed", and those need different answers from a human.
    catalog_version integer NOT NULL,

    currency_code char(3) NOT NULL,
    window_from timestamptz NOT NULL,
    window_to   timestamptz NOT NULL,

    signed_off_by_user_id uuid NOT NULL,
    signed_off_at timestamptz NOT NULL,

    content_digest char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT shift_snapshot_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT shift_snapshot_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT shift_snapshot_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_snapshot_shift_fk FOREIGN KEY (tenant_id, shift_id)
        REFERENCES cash.shift (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_snapshot_signer_fk FOREIGN KEY (tenant_id, signed_off_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_snapshot_currency_fk FOREIGN KEY (currency_code)
        REFERENCES money.currency (code) ON DELETE RESTRICT,
    CONSTRAINT shift_snapshot_window_ordered CHECK (window_to > window_from),
    CONSTRAINT shift_snapshot_digest_is_a_digest CHECK (content_digest ~ '^[0-9a-f]{64}$'),

    -- ONE SNAPSHOT PER SIGN-OFF, NOT PER SHIFT, and the difference is FR-CSH-006's.
    -- A drawer that is reopened is verified AGAIN, by somebody, at a later instant, and
    -- that second verification is a second signed-off answer — it does not overwrite the
    -- first and it is not an error. An earlier version of this made it UNIQUE per shift,
    -- and the reopen-and-resolve path stopped working: the second verification was
    -- refused by the snapshot, which is a reporting table deciding whether a cash shift
    -- may close. NC-M4-006 caught it.
    --
    -- What must be impossible is two signed-off answers with nothing saying which was
    -- signed, and the ordinal is what says: sign-off 1 and sign-off 2, each with its own
    -- signer and its own instant, in order.
    sign_off_number integer NOT NULL,
    CONSTRAINT shift_snapshot_sign_off_positive CHECK (sign_off_number >= 1),
    CONSTRAINT shift_snapshot_one_per_sign_off
        UNIQUE (tenant_id, shift_id, sign_off_number),

    -- The currency anchor a value row keys to, so a value cannot be denominated in a
    -- currency its snapshot is not in. Not a second identity: (tenant_id, id) is unique
    -- above.
    CONSTRAINT shift_snapshot_currency_anchor UNIQUE (tenant_id, id, currency_code)
);

COMMENT ON TABLE report.shift_snapshot IS
    'FR-RPT-014. The operational metrics as they stood when a shift was signed off. '
    'Append-only by trigger, classified as a ledger by app.financial_table_class(), and '
    'granted INSERT and SELECT only — there is no path by which a recomputation reaches '
    'it. report.recompute_shift_snapshot() writes a divergence record instead, which is '
    'the difference between a recomputation that cannot rewrite a result and one that '
    'merely does not.';

CREATE TABLE report.shift_snapshot_value (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL,
    outlet_id   uuid NOT NULL,
    snapshot_id uuid NOT NULL,

    metric report.metric_key NOT NULL,

    -- THE UNIT COMES FROM THE CATALOG THROUGH A KEY, not from a copy of the catalog's
    -- judgement. The foreign key names (metric, unit) against report.metric's anchor, so
    -- a row claiming a metric is measured in something the catalog does not say is
    -- refused by the key rather than by a trigger somebody could forget to write.
    unit report.metric_unit NOT NULL,

    -- bigint and NOT money.amount_minor, deliberately: this column also carries seconds
    -- and counts. The currency sits beside the figure on this row — the rule
    -- docs.receipt_line was corrected for at this gate — and the CHECK below makes its
    -- presence exactly equivalent to the metric being monetary.
    value bigint,
    currency_code char(3),

    observation_count bigint NOT NULL,

    -- TEXT, NOT regclass. A regclass is an object identifier, and an identifier is only
    -- meaningful in the database that issued it; a snapshot outlives a restore. The name
    -- is what a reader needs.
    source_relation text NOT NULL,
    latest_source_row_at timestamptz,

    CONSTRAINT shift_snapshot_value_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT shift_snapshot_value_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT shift_snapshot_value_snapshot_fk FOREIGN KEY (tenant_id, snapshot_id)
        REFERENCES report.shift_snapshot (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT shift_snapshot_value_metric_fk FOREIGN KEY (metric, unit)
        REFERENCES report.metric (key, unit) ON DELETE RESTRICT,
    CONSTRAINT shift_snapshot_value_currency_matches_the_snapshot
        FOREIGN KEY (tenant_id, snapshot_id, currency_code)
        REFERENCES report.shift_snapshot (tenant_id, id, currency_code) ON DELETE RESTRICT,
    CONSTRAINT shift_snapshot_value_currency_iff_monetary CHECK (
        (unit = 'minor_currency') = (currency_code IS NOT NULL)),
    CONSTRAINT shift_snapshot_value_observations_not_negative CHECK (observation_count >= 0),
    CONSTRAINT shift_snapshot_value_source_not_blank CHECK (btrim(source_relation) <> ''),
    CONSTRAINT shift_snapshot_value_one_per_metric UNIQUE (tenant_id, snapshot_id, metric)
);

COMMENT ON TABLE report.shift_snapshot_value IS
    'One catalogued metric as it stood at sign-off. The deferred trigger below refuses a '
    'snapshot that does not carry every metric in the catalog, so a metric added later '
    'cannot make an old snapshot look complete or a new one arrive short.';

CREATE INDEX shift_snapshot_value_snapshot_idx
    ON report.shift_snapshot_value (tenant_id, snapshot_id);


-- ---- append-only ---------------------------------------------------------
-- app.refuse_financial_mutation() is 0027's, named for the job rather than for one
-- schema, which is why a metric snapshot can use it without anything being called a
-- document.

CREATE TRIGGER shift_snapshot_is_append_only
    BEFORE UPDATE OR DELETE ON report.shift_snapshot
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

CREATE TRIGGER shift_snapshot_value_is_append_only
    BEFORE UPDATE OR DELETE ON report.shift_snapshot_value
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();


-- ---- a snapshot is complete or it is not a snapshot -----------------------

CREATE FUNCTION report.assert_snapshot_is_complete() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_have integer;
    v_want integer;
    v_missing text[];
BEGIN
    SELECT count(*) INTO v_have FROM report.shift_snapshot_value
     WHERE tenant_id = NEW.tenant_id AND snapshot_id = NEW.snapshot_id;
    SELECT count(*) INTO v_want FROM report.metric;

    IF v_have <> v_want THEN
        SELECT array_agg(m.key::text ORDER BY m.key) INTO v_missing
          FROM report.metric m
         WHERE NOT EXISTS (SELECT 1 FROM report.shift_snapshot_value v
                            WHERE v.tenant_id = NEW.tenant_id
                              AND v.snapshot_id = NEW.snapshot_id
                              AND v.metric = m.key);
        RAISE EXCEPTION
            'SNAPSHOT_INCOMPLETE: snapshot % carries % of % catalogued metrics; missing '
            '%. A partial snapshot is worse than none: it looks like an answer and it is '
            'an answer to a smaller question',
            NEW.snapshot_id, v_have, v_want, coalesce(v_missing, ARRAY['none']::text[])
            USING ERRCODE = 'HS422';
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER shift_snapshot_is_complete
    AFTER INSERT ON report.shift_snapshot_value
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION report.assert_snapshot_is_complete();


-- ---- the digest, and one implementation of what a figure looks like ------
-- THE SNAPSHOT IS SEALED BY ITS WRITER AND THE SEAL IS CHECKED AGAINST THE ROWS. The
-- digest is computed from the readings before anything is written, stored on the header,
-- and verified at commit against the rows that landed. That ordering is what makes it a
-- seal rather than a summary: a summary computed from the rows would agree with the rows
-- no matter what the rows said.
--
-- ONE FORMAT FUNCTION, used by both sides. A digest computed one way over readings and
-- another way over stored rows would differ for a reason that is not a divergence, and
-- the first person to hit that would fix it by widening the comparison.

CREATE FUNCTION report.figure_line(
    p_metric report.metric_key, p_value bigint,
    p_observation_count bigint, p_currency_code char(3))
RETURNS text LANGUAGE sql IMMUTABLE
AS $$
    SELECT p_metric::text || '=' || coalesce(p_value::text, 'null')
                          || '/' || p_observation_count::text
                          || '/' || coalesce(p_currency_code, '-');
$$;

COMMENT ON FUNCTION report.figure_line(report.metric_key, bigint, bigint, char) IS
    'How one figure is written for hashing. The computation time is deliberately absent: '
    'two computations of the same figures at different instants must digest the same, or '
    'every recomputation would report a divergence and the word would stop meaning '
    'anything.';

CREATE FUNCTION report.digest_of(p_lines text[])
RETURNS char(64) LANGUAGE sql IMMUTABLE
AS $$
    SELECT encode(sha256(convert_to(
        coalesce((SELECT string_agg(l, E'\n' ORDER BY l) FROM unnest(p_lines) l), ''),
        'UTF8')), 'hex')::char(64);
$$;

COMMENT ON FUNCTION report.digest_of(text[]) IS
    'A digest over a set of figure lines, ordered by the line itself. Ordered because a '
    'digest over an unordered set changes when the planner does, and that would look '
    'exactly like a divergence.';

CREATE FUNCTION report.snapshot_digest(p_tenant_id uuid, p_snapshot_id uuid)
RETURNS char(64) LANGUAGE sql STABLE
AS $$
    SELECT report.digest_of(array_agg(
               report.figure_line(v.metric, v.value, v.observation_count, v.currency_code)))
      FROM report.shift_snapshot_value v
     WHERE v.tenant_id = p_tenant_id AND v.snapshot_id = p_snapshot_id;
$$;

COMMENT ON FUNCTION report.snapshot_digest(uuid, uuid) IS
    'FR-RPT-014. The digest of a stored snapshot, over the same format the writer sealed '
    'it with. Verified at commit by the trigger below and recomputed by '
    'report.recompute_shift_snapshot() — one implementation, three readers.';

CREATE FUNCTION report.assert_snapshot_matches_its_seal() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_sealed char(64);
    v_actual char(64);
BEGIN
    SELECT content_digest INTO v_sealed FROM report.shift_snapshot
     WHERE tenant_id = NEW.tenant_id AND id = NEW.snapshot_id;
    v_actual := report.snapshot_digest(NEW.tenant_id, NEW.snapshot_id);
    IF v_sealed IS DISTINCT FROM v_actual THEN
        RAISE EXCEPTION
            'SNAPSHOT_SEAL_BROKEN: snapshot % was sealed as % and its rows digest to %. '
            'The figures signed off and the figures stored are not the same figures',
            NEW.snapshot_id, v_sealed, v_actual USING ERRCODE = 'HS422';
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER shift_snapshot_matches_its_seal
    AFTER INSERT ON report.shift_snapshot_value
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION report.assert_snapshot_matches_its_seal();


-- ---- taking the snapshot at sign-off -------------------------------------

CREATE FUNCTION report.take_shift_snapshot() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot_id uuid := gen_random_uuid();
    v_readings report.reading[];
    v_digest char(64);
    v_sign_off integer;
    r report.reading;
BEGIN
    -- The window is the shift: from when the drawer was opened to the instant it was
    -- signed off. Not "today", and not the calendar day the outlet is in — a shift that
    -- crosses midnight is one shift, and a report bounded by a date would cut it in half.
    SELECT array_agg(v) INTO v_readings
      FROM report.metric_values(
               NEW.tenant_id, NEW.outlet_id, NEW.opened_at, NEW.verified_at,
               NEW.currency_code) v;

    SELECT report.digest_of(array_agg(
               report.figure_line((v).metric, (v).value, (v).observation_count,
                                  (v).currency_code)))
      INTO v_digest
      FROM unnest(v_readings) v;

    SELECT coalesce(max(s.sign_off_number), 0) + 1 INTO v_sign_off
      FROM report.shift_snapshot s
     WHERE s.tenant_id = NEW.tenant_id AND s.shift_id = NEW.id;

    INSERT INTO report.shift_snapshot
        (id, tenant_id, outlet_id, shift_id, sign_off_number, catalog_version,
         currency_code, window_from, window_to, signed_off_by_user_id, signed_off_at,
         content_digest)
    VALUES (v_snapshot_id, NEW.tenant_id, NEW.outlet_id, NEW.id, v_sign_off,
            report.catalog_version(), NEW.currency_code,
            NEW.opened_at, NEW.verified_at,
            NEW.verified_by_user_id, NEW.verified_at, v_digest);

    FOREACH r IN ARRAY v_readings LOOP
        INSERT INTO report.shift_snapshot_value
            (tenant_id, outlet_id, snapshot_id, metric, unit, value, currency_code,
             observation_count, source_relation, latest_source_row_at)
        VALUES (NEW.tenant_id, NEW.outlet_id, v_snapshot_id, r.metric, r.unit, r.value,
                r.currency_code, r.observation_count, r.source::text,
                r.latest_source_row_at);
    END LOOP;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION report.take_shift_snapshot() IS
    'FR-RPT-014. Writes the snapshot at the instant a shift is signed off. A TRIGGER '
    'rather than a step inside cash.transition_shift(), so that a later gate adding '
    'another way to verify a shift cannot add one that forgets to snapshot. It seals the '
    'figures before writing them, and the deferred triggers above refuse a snapshot that '
    'is short a metric or does not match its seal.';

-- WHEN, precisely. Only on the edge INTO 'verified', so a shift that is finalized or
-- resolved afterwards does not take a second one. A REOPENED shift that is verified again
-- DOES take another, numbered one higher: that is a second sign-off by a second person at
-- a second instant, and refusing it would make a reporting table decide whether a cash
-- drawer may close.
CREATE TRIGGER shift_snapshot_taken_at_sign_off
    AFTER UPDATE OF state ON cash.shift
    FOR EACH ROW
    WHEN (NEW.state = 'verified' AND OLD.state IS DISTINCT FROM 'verified')
    EXECUTE FUNCTION report.take_shift_snapshot();


-- ===========================================================================
-- Recomputation, which reports rather than rewrites (FR-RPT-014)
-- ===========================================================================

CREATE TABLE report.recomputation (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL,
    outlet_id   uuid NOT NULL,
    snapshot_id uuid NOT NULL,

    catalog_version integer NOT NULL,
    content_digest  char(64) NOT NULL,
    diverged        boolean NOT NULL,

    recomputed_by_user_id uuid NOT NULL,
    recomputed_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT recomputation_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT recomputation_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT recomputation_snapshot_fk FOREIGN KEY (tenant_id, snapshot_id)
        REFERENCES report.shift_snapshot (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT recomputation_actor_fk FOREIGN KEY (tenant_id, recomputed_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT recomputation_digest_is_a_digest CHECK (content_digest ~ '^[0-9a-f]{64}$')
);

COMMENT ON TABLE report.recomputation IS
    'FR-RPT-014. Every recomputation of a signed-off shift, whether or not it agreed. '
    'The agreeing ones are recorded too: a record only of disagreements cannot '
    'distinguish "checked and fine" from "never checked".';

CREATE INDEX recomputation_snapshot_idx
    ON report.recomputation (tenant_id, snapshot_id, recomputed_at DESC);

CREATE TABLE report.snapshot_divergence (
    id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,
    recomputation_id uuid NOT NULL,

    metric report.metric_key NOT NULL,
    snapshot_value bigint,
    recomputed_value bigint,
    snapshot_observation_count bigint NOT NULL,
    recomputed_observation_count bigint NOT NULL,

    CONSTRAINT snapshot_divergence_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT snapshot_divergence_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT snapshot_divergence_recomputation_fk FOREIGN KEY (tenant_id, recomputation_id)
        REFERENCES report.recomputation (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT snapshot_divergence_metric_fk FOREIGN KEY (metric)
        REFERENCES report.metric (key) ON DELETE RESTRICT,
    CONSTRAINT snapshot_divergence_one_per_metric UNIQUE (tenant_id, recomputation_id, metric),

    -- A divergence row that records no difference is noise that hides the real ones.
    CONSTRAINT snapshot_divergence_actually_diverges CHECK (
        snapshot_value IS DISTINCT FROM recomputed_value
     OR snapshot_observation_count <> recomputed_observation_count)
);

COMMENT ON TABLE report.snapshot_divergence IS
    'FR-RPT-014. One row per metric where a recomputation disagreed with the signed-off '
    'figure, naming both numbers. This is where a recomputation''s answer goes, and it is '
    'the reason the snapshot needs no protection beyond being append-only: there is no '
    'code path that writes a recomputed figure into it.';

CREATE TRIGGER recomputation_is_append_only
    BEFORE UPDATE OR DELETE ON report.recomputation
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

CREATE TRIGGER snapshot_divergence_is_append_only
    BEFORE UPDATE OR DELETE ON report.snapshot_divergence
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

CREATE FUNCTION report.recompute_shift_snapshot(
    p_tenant_id uuid, p_shift_id uuid, p_actor_user_id uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY INVOKER
AS $$
DECLARE
    s report.shift_snapshot%ROWTYPE;
    v_recomputation_id uuid := gen_random_uuid();
    v_digest char(64);
    v_diverged boolean;
    v_readings report.reading[];
BEGIN
    -- THE LATEST SIGN-OFF. A reopened drawer has more than one, and the question
    -- "was this shift's result quietly rewritten" is about the answer that stands.
    SELECT * INTO s FROM report.shift_snapshot
     WHERE tenant_id = p_tenant_id AND shift_id = p_shift_id
     ORDER BY sign_off_number DESC LIMIT 1;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'SNAPSHOT_NOT_FOUND: shift % has no signed-off snapshot to recompute against. '
            'A recomputation with nothing to compare to is just a report',
            p_shift_id USING ERRCODE = 'HS404';
    END IF;

    -- THE SAME WINDOW, THE SAME CURRENCY. A recomputation over a different window would
    -- disagree for a reason that is not a divergence, and the first person to see that
    -- would conclude the snapshot was wrong.
    --
    -- An array rather than a temporary table: this function must be callable twice in one
    -- transaction, and a temporary table is a name that collides with itself.
    SELECT array_agg(v) INTO v_readings
      FROM report.metric_values(
               s.tenant_id, s.outlet_id, s.window_from, s.window_to, s.currency_code) v;

    SELECT report.digest_of(array_agg(
               report.figure_line((v).metric, (v).value, (v).observation_count,
                                  (v).currency_code)))
      INTO v_digest FROM unnest(v_readings) v;

    v_diverged := v_digest IS DISTINCT FROM s.content_digest;

    INSERT INTO report.recomputation
        (id, tenant_id, outlet_id, snapshot_id, catalog_version, content_digest,
         diverged, recomputed_by_user_id)
    VALUES (v_recomputation_id, s.tenant_id, s.outlet_id, s.id,
            report.catalog_version(), v_digest, v_diverged, p_actor_user_id);

    -- FULL OUTER JOIN, not an inner one. A metric the catalog gained since the snapshot
    -- was taken has no signed-off figure, and a metric it lost has no recomputed one;
    -- both are divergences and an inner join would hide exactly those two cases.
    INSERT INTO report.snapshot_divergence
        (tenant_id, outlet_id, recomputation_id, metric,
         snapshot_value, recomputed_value,
         snapshot_observation_count, recomputed_observation_count)
    SELECT s.tenant_id, s.outlet_id, v_recomputation_id,
           coalesce(o.metric, n.metric),
           o.value, n.value,
           coalesce(o.observation_count, -1), coalesce(n.observation_count, -1)
      FROM (SELECT metric, value, observation_count
              FROM report.shift_snapshot_value
             WHERE tenant_id = s.tenant_id AND snapshot_id = s.id) o
      FULL OUTER JOIN (SELECT (v).metric, (v).value, (v).observation_count
                         FROM unnest(v_readings) v) n ON n.metric = o.metric
     WHERE o.value IS DISTINCT FROM n.value
        OR coalesce(o.observation_count, -1) <> coalesce(n.observation_count, -1);

    RETURN v_recomputation_id;
END;
$$;

COMMENT ON FUNCTION report.recompute_shift_snapshot(uuid, uuid, uuid) IS
    'FR-RPT-014. Recomputes a signed-off shift over the snapshot''s own window and '
    'currency and records what it found. It contains no UPDATE and no DELETE against '
    'report.shift_snapshot or report.shift_snapshot_value, and the application role holds '
    'no such grant on either, so the sentence "a recomputation cannot silently rewrite a '
    'signed-off shift result" is true in three independent ways: the trigger refuses it, '
    'the grant is absent, and there is no code that tries. An observation count of -1 in '
    'a divergence row means the metric was absent on that side.';


-- ===========================================================================
-- Role dashboards (FR-RPT-001)
-- ===========================================================================
-- NO DEFERRED MODULE CAN REACH A DASHBOARD, and not because a reviewer reads the panel
-- list. A panel names a label of report.metric_key, every label of which is a Phase 1
-- metric over a Phase 1 table. There is no free-text panel, no panel that names a table,
-- and no panel that names a module. A fenced domain arriving through a data row is the
-- failure this shape forecloses.

CREATE TYPE report.dashboard_role AS ENUM
    ('outlet_manager', 'waiter', 'cashier', 'kitchen_expo');

COMMENT ON TYPE report.dashboard_role IS
    'FR-RPT-001''s Phase 1 dashboards at M4. The technical-operator dashboard is M5a''s — '
    'the package says so in the requirement''s later_behavior, and it covers the local '
    'node, synchronization and the printer, none of which exist at this gate. There is no '
    'label for it here, so it cannot be half-built by accident and then look present.';

CREATE TABLE report.dashboard (
    role  report.dashboard_role PRIMARY KEY,
    title text NOT NULL,
    audience text NOT NULL,
    CONSTRAINT dashboard_title_not_blank CHECK (btrim(title) <> ''),
    CONSTRAINT dashboard_audience_not_blank CHECK (btrim(audience) <> '')
);

COMMENT ON TABLE report.dashboard IS
    'FR-RPT-001. One row per Phase 1 role. Global rather than per tenant: which metrics a '
    'manager sees is a product decision, not a tenant setting, and a per-tenant dashboard '
    'table is where a tenant would eventually be able to add a panel naming anything.';

CREATE TABLE report.dashboard_panel (
    role   report.dashboard_role NOT NULL,
    display_order integer NOT NULL,
    metric report.metric_key NOT NULL,

    PRIMARY KEY (role, display_order),
    CONSTRAINT dashboard_panel_dashboard_fk FOREIGN KEY (role)
        REFERENCES report.dashboard (role) ON DELETE RESTRICT,
    CONSTRAINT dashboard_panel_metric_fk FOREIGN KEY (metric)
        REFERENCES report.metric (key) ON DELETE RESTRICT,
    CONSTRAINT dashboard_panel_one_place_per_metric UNIQUE (role, metric),
    CONSTRAINT dashboard_panel_order_positive CHECK (display_order >= 1)
);

COMMENT ON TABLE report.dashboard_panel IS
    'FR-RPT-001. Which catalogued metrics a role sees, in what order. The foreign key '
    'into report.metric is what makes FR-RPT-015 a prerequisite in fact and not only in '
    'the register: a panel cannot show a figure nobody has defined.';

INSERT INTO report.dashboard (role, title, audience) VALUES
('outlet_manager', 'Outlet', 'the manager, who needs takings and where service is slipping'),
('waiter', 'Service', 'the waiter, whose work is requests and tables rather than money'),
('cashier', 'Till', 'the cashier, who is accountable for what was taken and given back'),
('kitchen_expo', 'Pass', 'the kitchen and expo, whose measure is the queue and the clock');

INSERT INTO report.dashboard_panel (role, display_order, metric) VALUES
-- The manager sees the money and the two service figures that explain it.
('outlet_manager', 1, 'orders_placed'),
('outlet_manager', 2, 'item_sales_minor'),
('outlet_manager', 3, 'discounts_minor'),
('outlet_manager', 4, 'service_charges_minor'),
('outlet_manager', 5, 'taxes_minor'),
('outlet_manager', 6, 'bill_payments_minor'),
('outlet_manager', 7, 'tips_minor'),
('outlet_manager', 8, 'tip_reversals_minor'),
('outlet_manager', 9, 'service_completion_seconds_p50'),
('outlet_manager', 10, 'kitchen_preparation_seconds_p50'),

-- NO MONEY ON THE WAITER'S DASHBOARD. A waiter's accountability is the request and the
-- table, and putting takings in front of somebody who cannot act on them is how a figure
-- becomes decoration.
('waiter', 1, 'service_requests_raised'),
('waiter', 2, 'service_acknowledgement_seconds_p50'),
('waiter', 3, 'service_completion_seconds_p50'),
('waiter', 4, 'table_session_seconds_p50'),
('waiter', 5, 'kitchen_ready_to_serve_seconds_p50'),

('cashier', 1, 'bill_payments_minor'),
('cashier', 2, 'tips_minor'),
('cashier', 3, 'tip_reversals_minor'),
('cashier', 4, 'discounts_minor'),
('cashier', 5, 'orders_placed'),

('kitchen_expo', 1, 'kitchen_queue_depth'),
('kitchen_expo', 2, 'kitchen_preparation_seconds_p50'),
('kitchen_expo', 3, 'kitchen_ready_to_serve_seconds_p50'),
('kitchen_expo', 4, 'kitchen_rework_events'),
('kitchen_expo', 5, 'kitchen_exceptions');

CREATE FUNCTION report.dashboard_for(
    p_role report.dashboard_role,
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_from timestamptz,
    p_to timestamptz,
    p_currency_code char(3))
RETURNS TABLE (display_order integer,
               metric report.metric_key,
               title text,
               unit report.metric_unit,
               value bigint,
               currency_code char(3),
               observation_count bigint,
               source regclass,
               computed_at timestamptz,
               latest_source_row_at timestamptz)
LANGUAGE sql STABLE SECURITY INVOKER
AS $$
    SELECT p.display_order, p.metric, m.title, r.unit, r.value, r.currency_code,
           r.observation_count, r.source, r.computed_at, r.latest_source_row_at
      FROM report.dashboard_panel p
      JOIN report.metric m ON m.key = p.metric
      JOIN (SELECT (v).* FROM report.metric_values(
                p_tenant_id, p_outlet_id, p_from, p_to, p_currency_code) v) r
        ON r.metric = p.metric
     WHERE p.role = p_role
     ORDER BY p.display_order;
$$;

COMMENT ON FUNCTION report.dashboard_for(report.dashboard_role, uuid, uuid, timestamptz, timestamptz, char) IS
    'FR-RPT-001 and FR-RPT-002. A role''s panels with each figure''s source and both '
    'freshness facts attached, because the label is part of the value rather than '
    'something the surface adds. SECURITY INVOKER, so a caller sees their own outlet.';


-- ===========================================================================
-- Exports (FR-RPT-013)
-- ===========================================================================

CREATE TYPE report.export_kind AS ENUM ('metrics', 'sales');

CREATE TABLE report.export (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,
    kind      report.export_kind NOT NULL,

    window_from timestamptz NOT NULL,
    window_to   timestamptz NOT NULL,
    currency_code char(3) NOT NULL,
    catalog_version integer NOT NULL,

    requested_by_user_id uuid NOT NULL,
    row_count integer NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT export_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT export_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT export_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT export_requester_fk FOREIGN KEY (tenant_id, requested_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT export_currency_fk FOREIGN KEY (currency_code)
        REFERENCES money.currency (code) ON DELETE RESTRICT,
    CONSTRAINT export_window_ordered CHECK (window_to > window_from),
    CONSTRAINT export_row_count_not_negative CHECK (row_count >= 0)
);

COMMENT ON TABLE report.export IS
    'FR-RPT-013. Every export, with the scope it was taken at. The tenant and outlet on '
    'this row are the scope the data was read under, not a label somebody chose: the '
    'export functions are SECURITY INVOKER and row level security is what bounded them.';

CREATE TRIGGER export_is_append_only
    BEFORE UPDATE OR DELETE ON report.export
    FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();

CREATE FUNCTION report.csv_field(p_value text) RETURNS text
LANGUAGE sql IMMUTABLE
AS $$
    SELECT CASE WHEN p_value IS NULL THEN ''
                ELSE '"' || replace(p_value, '"', '""') || '"' END;
$$;

COMMENT ON FUNCTION report.csv_field(text) IS
    'One field, quoted per RFC 4180. Every field is quoted rather than only the ones that '
    'need it, because "only when it needs it" is a judgement made in one place and '
    'forgotten in another. NULL renders as an empty unquoted field, which is how a reader '
    'tells an absent figure from an empty string — the FR-UX-014 distinction, surviving '
    'the export.';

CREATE FUNCTION report.export_metrics_csv(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_from timestamptz,
    p_to timestamptz,
    p_currency_code char(3),
    p_actor_user_id uuid)
RETURNS text
LANGUAGE plpgsql SECURITY INVOKER
AS $$
DECLARE
    v_rows text;
    v_count integer;
BEGIN
    SELECT string_agg(line, E'\n' ORDER BY line), count(*)
      INTO v_rows, v_count
      FROM (
        SELECT report.csv_field((v).metric::text) || ',' ||
               report.csv_field((v).unit::text) || ',' ||
               coalesce((v).value::text, '') || ',' ||
               report.csv_field((v).currency_code) || ',' ||
               (v).observation_count::text || ',' ||
               report.csv_field((v).source::text) || ',' ||
               report.csv_field((v).computed_at::text) || ',' ||
               report.csv_field((v).latest_source_row_at::text) AS line
          FROM report.metric_values(
                   p_tenant_id, p_outlet_id, p_from, p_to, p_currency_code) v) s;

    INSERT INTO report.export
        (tenant_id, outlet_id, kind, window_from, window_to, currency_code,
         catalog_version, requested_by_user_id, row_count)
    VALUES (p_tenant_id, p_outlet_id, 'metrics', p_from, p_to, p_currency_code,
            report.catalog_version(), p_actor_user_id, coalesce(v_count, 0));

    RETURN 'metric,unit,value,currency_code,observation_count,source,computed_at,'
           'latest_source_row_at' || E'\n' || coalesce(v_rows, '');
END;
$$;

COMMENT ON FUNCTION report.export_metrics_csv(uuid, uuid, timestamptz, timestamptz, char, uuid) IS
    'FR-RPT-013. RFC 4180 CSV, with a header row naming the eight documented columns. '
    'SECURITY INVOKER, which IS the tenant and outlet scoping: this function has no '
    'privilege its caller lacks, so an export cannot reach a row the caller could not '
    'have selected. The DO block at the foot of this migration refuses any SECURITY '
    'DEFINER function in this schema, so that property cannot be lost by a later edit.';


-- ===========================================================================
-- The reporting tables are financial tables (FR-DAT-008B)
-- ===========================================================================
-- REPLACED, NOT COPIED. app.financial_schemas() and app.financial_table_class() are
-- 0028's, and the completeness assertion is a function there for exactly this reason: a
-- gate that adds a financial schema re-points the list and calls the same check, rather
-- than pasting a second DO block that will one day disagree with the first.

CREATE OR REPLACE FUNCTION app.financial_schemas() RETURNS text[] LANGUAGE sql IMMUTABLE
AS $$ SELECT ARRAY['billing', 'payments', 'cash', 'docs', 'fiscal', 'report']; $$;

CREATE OR REPLACE FUNCTION app.financial_table_class(p_schema text, p_table text)
RETURNS text LANGUAGE sql IMMUTABLE
AS $$
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
        -- read well and asserted nothing — cash.shift is not configuration in any
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
    END;
$$;


-- ===========================================================================
-- Retention cannot destroy a reporting ledger either (FR-SEC-018, FR-DAT-008B)
-- ===========================================================================
-- 0027 added this constraint over four schemas and said in its own comment that a list of
-- schemas is a list that goes stale on the next migration. It went stale on the next
-- migration but one. Re-stated here over the schemas app.financial_schemas() now names,
-- and tests/m4c asserts the two agree by reading both — the constraint keeps a literal
-- list because a CHECK that calls a function is not re-validated when the function
-- changes, which would be a rule that silently stopped applying to the rows already
-- there.
ALTER TABLE config.retention_policy
    DROP CONSTRAINT retention_policy_never_targets_financial_ledgers;

ALTER TABLE config.retention_policy
    ADD CONSTRAINT retention_policy_never_targets_financial_ledgers
    CHECK (target_schema NOT IN
           ('billing', 'payments', 'cash', 'docs', 'fiscal', 'report'));

COMMENT ON CONSTRAINT retention_policy_never_targets_financial_ledgers
    ON config.retention_policy IS
    'FR-SEC-018 at M4, and FR-DAT-008B''s other half. Bills, payments, tips, cash '
    'movements, receipts, fiscal documents and signed-off metric snapshots are '
    'append-only or reversal-based, and a retention sweep would delete them without '
    'passing the trigger that refuses a destructive correction. Anonymization remains '
    'available everywhere it belongs. tests/m4c asserts this list equals '
    'app.financial_schemas(), so the two cannot drift apart unnoticed. THIS DOES NOT '
    'CLOSE FR-SEC-018: no legal hold exists.';


-- ===========================================================================
-- Row level security
-- ===========================================================================
-- ONLY THE TABLES THAT CARRY A TENANT. report.metric, report.dashboard and
-- report.dashboard_panel are global reference data in the same sense money.currency is:
-- there is no tenant column to scope by, and inventing one so that every table in the
-- schema could be looped over would be a policy that asserted nothing.

DO $$
DECLARE t text;
BEGIN
    FOR t IN
        SELECT format('%I.%I', n.nspname, c.relname)
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'report' AND c.relkind = 'r'
           AND EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = c.oid AND a.attname = 'tenant_id'
                          AND a.attnum > 0 AND NOT a.attisdropped)
         ORDER BY c.relname
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
-- THE APPLICATION ROLE CANNOT WRITE A SNAPSHOT AT ALL. Not INSERT, not UPDATE, not
-- DELETE. cash.shift carries no UPDATE grant for hospitality_app either — every shift
-- transition goes through cash.transition_shift(), which is SECURITY DEFINER — so the
-- only path that reaches report.shift_snapshot is the trigger that fires at sign-off.
-- FR-RPT-014 asks that a recomputation cannot silently rewrite a signed-off result; this
-- is the grant that makes it true of the whole application surface rather than of one
-- function.

GRANT USAGE ON SCHEMA report TO hospitality_app;

GRANT SELECT ON report.metric                TO hospitality_app;
GRANT SELECT ON report.dashboard             TO hospitality_app;
GRANT SELECT ON report.dashboard_panel       TO hospitality_app;
GRANT SELECT ON report.shift_snapshot        TO hospitality_app;
GRANT SELECT ON report.shift_snapshot_value  TO hospitality_app;
GRANT SELECT ON report.recomputation         TO hospitality_app;
GRANT SELECT ON report.snapshot_divergence   TO hospitality_app;
GRANT SELECT ON report.export                TO hospitality_app;

-- A recomputation is something an operator asks for, so the application role writes it.
-- A divergence is what a recomputation found, so the same.
GRANT INSERT ON report.recomputation       TO hospitality_app;
GRANT INSERT ON report.snapshot_divergence TO hospitality_app;
GRANT INSERT ON report.export              TO hospitality_app;

GRANT EXECUTE ON FUNCTION report.catalog_version() TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.reading(report.metric_key, bigint, char, bigint, timestamptz)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.classify_component(
    ordering.charge_kind, ordering.charge_source_kind) TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.metric_values(uuid, uuid, timestamptz, timestamptz, char)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.sales_report(uuid, uuid, timestamptz, timestamptz, char)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.dashboard_for(
    report.dashboard_role, uuid, uuid, timestamptz, timestamptz, char) TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.figure_line(report.metric_key, bigint, bigint, char)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.digest_of(text[]) TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.snapshot_digest(uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.recompute_shift_snapshot(uuid, uuid, uuid)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.csv_field(text) TO hospitality_app;
GRANT EXECUTE ON FUNCTION report.export_metrics_csv(
    uuid, uuid, timestamptz, timestamptz, char, uuid) TO hospitality_app;


-- ===========================================================================
-- The catalog is complete, and nothing here escapes the caller's scope
-- ===========================================================================
-- AT THE FOOT, for the reason 0028 states: a completeness check that ran before the
-- objects it checks would pass by not seeing them.

DO $$
DECLARE uncatalogued text[];
BEGIN
    SELECT array_agg(k::text ORDER BY k::text) INTO uncatalogued
      FROM unnest(enum_range(NULL::report.metric_key)) k
     WHERE NOT EXISTS (SELECT 1 FROM report.metric m WHERE m.key = k);
    IF uncatalogued IS NOT NULL THEN
        RAISE EXCEPTION
            'METRIC_UNCATALOGUED: % is a metric this build can compute and FR-RPT-015 '
            'does not define. A figure with no formula, timezone, currency rule, '
            'inclusion rule or named source is a number somebody will act on anyway',
            uncatalogued;
    END IF;
END;
$$;

DO $$
DECLARE bare text[];
BEGIN
    SELECT array_agg(r::text ORDER BY r::text) INTO bare
      FROM unnest(enum_range(NULL::report.dashboard_role)) r
     WHERE NOT EXISTS (SELECT 1 FROM report.dashboard_panel p WHERE p.role = r);
    IF bare IS NOT NULL THEN
        RAISE EXCEPTION
            'DASHBOARD_WITHOUT_PANELS: % is a Phase 1 role with a dashboard and no '
            'panels. An empty dashboard is the shape a role takes when somebody added it '
            'to the enum and stopped', bare;
    END IF;
END;
$$;

DO $$
DECLARE definers text[];
BEGIN
    SELECT array_agg(p.proname ORDER BY p.proname) INTO definers
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'report' AND p.prosecdef;
    IF definers IS NOT NULL THEN
        RAISE EXCEPTION
            'REPORT_FUNCTION_BYPASSES_SCOPE: % in schema report is SECURITY DEFINER. '
            'FR-RPT-013 scopes exports by tenant and outlet, and the way that is true '
            'here is that no function in this schema has a privilege its caller lacks. '
            'A SECURITY DEFINER reporting function would read every outlet in the tenant '
            'and no test of the query would notice', definers;
    END IF;
END;
$$;

DO $$ BEGIN PERFORM app.assert_financial_tables_are_classified(); END; $$;
