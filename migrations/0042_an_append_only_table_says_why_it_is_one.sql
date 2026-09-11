-- 0042: an append-only table says why it is one, and the reason is checked
--
-- THE DEFECT, AND WHERE IT CAME FROM. app.refuse_financial_mutation() carries a comment
-- explaining that an earlier version of it named a cause it had not verified — it said
-- 'a receipt is the record of a document a customer is holding', which was true of the
-- two tables it guarded when it was written and false by the time 0028 attached it to a
-- drawer count. The comment then states the rule the repair followed: "What is true of
-- every table this guards is the sentence below, so that is the sentence."
--
-- The replacement did not follow it. It says:
--
--     It is an append-only financial ledger — app.financial_table_class() says so —
--
-- and app.financial_table_class() says nothing at all about four of the tables the
-- trigger guards. pos.counter_order_entry has been one of them since M4-C: it is in
-- `pos`, which is not a financial schema, so it has no class, and every refusal it has
-- ever raised has cited a classification that does not exist. M5a was about to make it
-- four by attaching the same guard to edge.node_health_sample, edge.node_admin_action and
-- integration.sync_evidence, all of which are append-only for good reasons and none of
-- which is financial.
--
-- The same defect, one revision later, inside the fix for it. That is the finding, and it
-- is worth more than the wrong sentence: a diagnostic is a claim, and a claim in a
-- diagnostic gets believed precisely when somebody is in trouble and reading fast.
--
-- WHY app.assert_financial_tables_are_classified() DID NOT CATCH IT. It asks one
-- question — is every table in a financial schema classified? — and passes. The question
-- it never asks is the converse: does every table CLAIMING a classification actually have
-- one. Same shape as the census pooling "called by a test" with "reachable by a person":
-- one question standing in for two, and the unasked one is where the defect lives.
--
-- WHAT THIS CHANGES. The signature stays. NC-M4C-005 is registered against
-- LEDGER_ROW_DELETED_NOT_REVERSED and a control that stops matching is a control that
-- stops running, so the identifier is untouched and only the unverifiable clause goes.
-- The table is then declared, in both directions, so a fifth cannot be added silently.

-- ---------------------------------------------------------------------------
-- 1. THE MESSAGE, SAYING ONLY WHAT IS TRUE OF EVERY TABLE IT GUARDS
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.refuse_financial_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    -- IT NAMES THE OPERATION IT SAW, AND NOTHING ELSE. Twice now this sentence has
    -- carried a clause that was true of the tables the trigger guarded when it was
    -- written and false of the ones it guarded later — first 'a receipt is the record of
    -- a document a customer is holding', then 'app.financial_table_class() says so',
    -- which says nothing about pos.counter_order_entry, edge.node_health_sample,
    -- edge.node_admin_action or integration.sync_evidence.
    --
    -- So the clause is gone rather than corrected. What remains is true of every table
    -- this guards and stays true of the next one: the row records something that
    -- happened, and the correction for it is another row. Where a table also has a
    -- financial classification, app.financial_table_class() will tell a reader who asks;
    -- the trigger no longer answers a question it was not asked.
    RAISE EXCEPTION
        'LEDGER_ROW_DELETED_NOT_REVERSED: % on %.% was refused. It is append-only, and a '
        'row here is the record of something that happened. Correct it by adding the row '
        'that reverses, supersedes or supplements it, never by changing this one. '
        'FR-DAT-008B: no destructive correction',
        TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME USING ERRCODE = 'HS409';
END;
$$;

-- ---------------------------------------------------------------------------
-- 2. WHICH TABLES ARE APPEND-ONLY, DECLARED
-- ---------------------------------------------------------------------------

-- Two sources, because there are two reasons a table is append-only and conflating them
-- is what produced the wrong message. A financial ledger is append-only because
-- FR-DAT-008B says money is corrected by addition. The others are append-only because
-- they are evidence — of where an order was entered, of what a node reported, of who
-- administered it, of what the synchronization did — and evidence you can edit is not
-- evidence. Both are real; only one of them is financial.
CREATE FUNCTION app.append_only_tables()
RETURNS TABLE (schema_name text, table_name text, reason text)
LANGUAGE sql STABLE
SET search_path TO 'pg_catalog', 'app', 'public'
AS $$
    SELECT n.nspname::text, c.relname::text, 'financial ledger'::text
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relkind = 'r'
       AND app.financial_table_class(n.nspname, c.relname) = 'ledger'
     UNION ALL
    SELECT t.schema_name, t.table_name, t.reason
      FROM (VALUES
        ('pos', 'counter_order_entry',
         'which terminal an order was entered at, and by whom — a fact about what '
         'happened, not a row that is currently true'),
        ('edge', 'node_health_sample',
         'what a node reported about itself; a health history that can be edited is not '
         'evidence'),
        ('edge', 'node_admin_action',
         'administrative access to the node, which must survive the outage that makes '
         'the cloud audit ledger unreachable'),
        ('integration', 'sync_evidence',
         'FR-DAT-008C: append-only across replay and restart, including the deliveries '
         'the synchronization refused')
      ) AS t(schema_name, table_name, reason)
     ORDER BY 1, 2;
$$;

COMMENT ON FUNCTION app.append_only_tables() IS
    'Every table that refuses UPDATE and DELETE, and why. Financial ledgers are derived '
    'from app.financial_table_class(); the rest are named, because a table that is '
    'append-only for a non-financial reason has nowhere else to say so.';

-- ---------------------------------------------------------------------------
-- 3. THE CHECK THAT WOULD HAVE CAUGHT IT, ASKED IN BOTH DIRECTIONS
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.assert_append_only_guards_are_declared()
RETURNS void
LANGUAGE plpgsql
SET search_path TO 'pg_catalog', 'app', 'public'
AS $$
DECLARE
    undeclared text[];
    unguarded  text[];
BEGIN
    -- A table carrying the guard that nobody declared. This is the direction that was
    -- missing, and the one pos.counter_order_entry sat in for four gates.
    SELECT array_agg(DISTINCT n.nspname || '.' || c.relname ORDER BY n.nspname || '.' || c.relname)
      INTO undeclared
      FROM pg_trigger tg
      JOIN pg_class c   ON c.oid = tg.tgrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_proc p    ON p.oid = tg.tgfoid
     WHERE NOT tg.tgisinternal
       AND p.proname = 'refuse_financial_mutation'
       AND NOT EXISTS (SELECT 1 FROM app.append_only_tables() a
                        WHERE a.schema_name = n.nspname AND a.table_name = c.relname);

    -- And a table declared append-only that does not actually refuse anything. A
    -- declaration without a guard is the same failure read from the other end.
    --
    -- GUARDED IS DERIVED FROM WHAT THE TRIGGER DOES, NOT FROM WHAT IT IS CALLED. The
    -- first draft of this asked for app.refuse_financial_mutation() by name and reported
    -- seven ledgers unguarded — billing.bill_event, billing.tip, billing.tip_correction,
    -- cash.movement, cash.shift_transition, payments.payment_event and payments.reversal.
    -- All seven refuse destructive change perfectly well, through four differently-named
    -- functions this repository wrote for them. A check that had shipped would have been
    -- a diagnostic naming a cause it had not verified — the same defect as the message it
    -- exists to repair, in the repair itself, which is how this file came to be written
    -- twice. So the question asked is the one that matters: is there a row-level BEFORE
    -- trigger on this table that fires on both UPDATE and DELETE and raises.
    SELECT array_agg(a.schema_name || '.' || a.table_name ORDER BY 1)
      INTO unguarded
      FROM app.append_only_tables() a
     WHERE NOT EXISTS (
           SELECT 1 FROM pg_trigger tg
             JOIN pg_class c   ON c.oid = tg.tgrelid
             JOIN pg_namespace n ON n.oid = c.relnamespace
             JOIN pg_proc p    ON p.oid = tg.tgfoid
            WHERE NOT tg.tgisinternal
              AND (tg.tgtype &  1) =  1        -- FOR EACH ROW
              AND (tg.tgtype &  2) =  2        -- BEFORE
              AND (tg.tgtype &  8) =  8        -- ... ON DELETE
              AND (tg.tgtype & 16) = 16        -- ... AND ON UPDATE
              AND p.prosrc ILIKE '%RAISE EXCEPTION%'
              AND n.nspname   = a.schema_name
              AND c.relname   = a.table_name);

    IF undeclared IS NOT NULL THEN
        RAISE EXCEPTION
            'APPEND_ONLY_GUARD_UNDECLARED: % refuses destructive change and '
            'app.append_only_tables() does not say why. The trigger''s message speaks for '
            'every table it guards, so a table nobody declared is a table it speaks for '
            'without knowing anything about', undeclared
            USING ERRCODE = 'HS500';
    END IF;
    IF unguarded IS NOT NULL THEN
        RAISE EXCEPTION
            'APPEND_ONLY_TABLE_UNGUARDED: % is declared append-only and carries no '
            'trigger refusing UPDATE or DELETE, so the declaration is a description of '
            'intent rather than a property of the table', unguarded
            USING ERRCODE = 'HS500';
    END IF;
END;
$$;

COMMENT ON FUNCTION app.assert_append_only_guards_are_declared() IS
    'Both directions. app.assert_financial_tables_are_classified() asks whether every '
    'financial table is classified and passes; the question it never asks is whether '
    'every table CLAIMING a classification has one, and that is where the wrong message '
    'lived for four gates.';

-- It has to hold the moment it is written, or it is a rule for the future about a
-- repository that already breaks it.
SELECT app.assert_append_only_guards_are_declared();

GRANT EXECUTE ON FUNCTION app.append_only_tables() TO hospitality_app;
GRANT EXECUTE ON FUNCTION app.assert_append_only_guards_are_declared() TO hospitality_app;
