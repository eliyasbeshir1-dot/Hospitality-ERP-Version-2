-- 0002_reason_codes.sql — localized reason-code sets (FR-CFG-003)
--
-- All ten Phase 1 categories, seeded for every tenant that exists. These are
-- configuration data. The actions that consume them — cancelling an order, voiding a
-- check, reversing a payment — arrive at M3, M4 and M5a and are not built here.
--
-- English labels only. Amharic and Arabic are M2 and land as additional
-- config.reason_code_label rows against these same codes, with no schema change.

\set ON_ERROR_STOP on

DO $$
DECLARE
    v_tenant  uuid;
    v_code_id uuid;
    r         record;
BEGIN
    -- The tenant list is explicit. A seed cannot discover tenants by querying
    -- org.tenant: without a tenant context that query correctly returns nothing, which
    -- is deny-by-default doing its job rather than a fault to work around.
    FOREACH v_tenant IN ARRAY ARRAY[
        '33333333-3333-3333-3333-333333333333'::uuid,   -- Habesha Kitchens
        '44444444-4444-4444-4444-444444444444'::uuid    -- Nile Coffee House
    ]
    LOOP
        PERFORM set_config('app.tenant_id', v_tenant::text, false);
        PERFORM set_config('app.outlet_id', '', false);

        FOR r IN
            SELECT * FROM (VALUES
                ('order_cancellation'::config.reason_code_category, 'GUEST_CHANGED_MIND', 'Guest changed their mind',      false),
                ('order_cancellation', 'ITEM_UNAVAILABLE',   'Item unavailable',                 false),
                ('order_cancellation', 'ORDERED_IN_ERROR',   'Ordered in error',                 false),
                ('void',               'WRONG_ITEM_ENTERED', 'Wrong item entered',               true),
                ('void',               'DUPLICATE_ENTRY',    'Duplicate entry',                  true),
                ('refund',             'QUALITY_COMPLAINT',  'Quality complaint',                true),
                ('refund',             'OVERCHARGED',        'Guest was overcharged',            true),
                ('discount',           'STAFF_MEAL',         'Staff meal',                       true),
                ('discount',           'GOODWILL',           'Goodwill gesture',                 true),
                ('complimentary_item', 'SERVICE_RECOVERY',   'Service recovery',                 true),
                ('complimentary_item', 'HOUSE_OFFER',        'On the house',                     true),
                ('payment_reversal',   'INCORRECT_TENDER',   'Incorrect tender recorded',        true),
                ('payment_reversal',   'PROOF_NOT_VERIFIED', 'Payment proof could not be verified', true),
                ('tip_correction',     'TIP_ENTERED_IN_ERROR', 'Tip entered in error',           true),
                ('tip_correction',     'GUEST_REQUESTED_CHANGE', 'Guest asked to change the tip', true),
                ('service_failure',    'LONG_WAIT',          'Excessive wait',                   false),
                ('service_failure',    'ORDER_NOT_DELIVERED_TO_TABLE', 'Order did not reach the table', false),
                ('printer_failure',    'OUT_OF_PAPER',       'Printer out of paper',             false),
                ('printer_failure',    'PRINTER_OFFLINE',    'Printer offline',                  false),
                ('manager_override',   'POLICY_EXCEPTION',   'Approved policy exception',        true),
                ('manager_override',   'SYSTEM_CORRECTION',  'System correction',                true)
            ) AS t(category, code, label, requires_approval)
        LOOP
            INSERT INTO config.reason_code (tenant_id, category, code, requires_approval)
            VALUES (v_tenant, r.category, r.code, r.requires_approval)
            ON CONFLICT (tenant_id, category, code) DO NOTHING
            RETURNING id INTO v_code_id;

            IF v_code_id IS NOT NULL THEN
                INSERT INTO config.reason_code_label (tenant_id, reason_code_id, locale, label)
                VALUES (v_tenant, v_code_id, 'en', r.label);
            END IF;
        END LOOP;
    END LOOP;

    PERFORM set_config('app.tenant_id', '', false);
END;
$$;
