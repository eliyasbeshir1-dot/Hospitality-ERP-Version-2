-- 0036: seating is an action, and every action on a staff screen carries a grade
--
-- THE DEFECT, AND IT WAS THE FAIL-CLOSED DEFAULT WORKING.
--
-- 0035 gave a waiter a Seat control. The waiter surface routes every action through one
-- path — askThenRun() — which looks the action up in pos.confirmation_requirement and
-- treats an UNGRADED action as `deliberate`, requiring a confirmation and a typed reason.
-- That default is deliberate and it is right: "a new destructive action that nobody
-- remembered to grade would otherwise be confirmed with a single tap."
--
-- `table.seat` was that new action, and nobody had graded it because until 0035 it did not
-- exist. So the first waiter to press Seat got a confirmation panel demanding a written
-- reason for sitting somebody at an empty table, and the seating never happened. The
-- surface was correct at every step; the registry simply had not been told.
--
-- Found by pressing the button. Nothing in the route layer could have caught it — the
-- route works, the function works, and both are proved by checks that pass. What was
-- missing sat between a screen and a configuration table, which is the seam this whole
-- gate exists to walk.
--
-- WHY THE GRADE IS `routine`. A waiter seats tables dozens of times a shift. Seating
-- destroys nothing, charges nothing and is undone by closing the occupancy, and 0015's own
-- comment on the routine tier names the test: "a waiter acknowledging a request or adding
-- a line to an order does it dozens of times an hour; friction here is friction
-- everywhere." Seating belongs in that tier beside them.
--
-- WHY BOTH FUNCTIONS ARE REPLACED. The grades are stated twice in 0015 — once in the
-- AFTER INSERT trigger that installs them for a NEW tenant, and once in
-- pos.install_registries_for() for a tenant that predates the migration adding them. Two
-- statements of one fact, which is the shape this repository keeps finding: the surface
-- list at F-OPB-4, the refusal map at F-OPB-4b, the route census at F-OPB-7. It is not
-- collapsed here, because collapsing it means rewriting a trigger and an installer that
-- eleven grades and four governed actions already depend on, in a migration whose subject
-- is one row. Both are updated together and the duplication is recorded in
-- planning/OPC_FINDINGS.md as the next thing for somebody to derive.
--
-- WHAT THIS MIGRATION CANNOT DO, STATED RATHER THAN QUIETLY OMITTED. It cannot backfill
-- the tenants that already exist. A migration runs with no tenant context, org.tenant is
-- FORCE row-level-secured, and a backfill SELECT over it matches nothing — which 0015's
-- own comment on pos.install_registries_for() records as the reason that function exists
-- at all. So an existing tenant gets this grade when an operator calls
-- pos.install_registries_for() for it; the demonstration floor gets it from seeds/0008,
-- which does exactly that under each tenant's own context.

-- ---------------------------------------------------------------------------
-- 1. A NEW TENANT (FR-UX-015)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION pos.install_confirmation_requirements() RETURNS trigger
-- SECURITY DEFINER so the application role can hold SELECT and nothing more on the
-- grades. A confirmation grade is configuration: the surface reads it, and nothing
-- the surface can do should be able to lower the friction on declaring an allergy.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pos, public
AS $$
BEGIN
    INSERT INTO pos.confirmation_requirement
        (tenant_id, action_code, consequence, requires_reason, graded_from_gate)
    VALUES
        -- Ordinary service. A waiter acknowledging a request or adding a line to an
        -- order does it dozens of times an hour; friction here is friction everywhere.
        (NEW.id, 'order.view',                   'routine',    false, 'M3-D'),
        (NEW.id, 'order.line.add',               'routine',    false, 'M3-D'),
        (NEW.id, 'service_request.acknowledge',  'routine',    false, 'M3-D'),
        (NEW.id, 'service_request.complete',     'routine',    false, 'M3-D'),
        (NEW.id, 'session.resume',               'routine',    false, 'M3-D'),
        -- Seating, added at OP-C when a waiter first had a control that did it. Routine
        -- for the same reason as the four above: it is the ordinary act of the shift, it
        -- destroys nothing, and it is undone by closing the occupancy.
        (NEW.id, 'table.seat',                   'routine',    false, 'OP-C'),
        -- Consequential but recoverable.
        (NEW.id, 'order.submit',                 'elevated',   false, 'M3-D'),
        (NEW.id, 'handover.propose',             'elevated',   false, 'M3-D'),
        (NEW.id, 'session.move',                 'elevated',   false, 'M3-D'),
        -- Deliberate: safety, destruction, and somebody else's authority. Each states a
        -- reason, enforced by the CHECK above rather than by the screen.
        (NEW.id, 'allergy.declare',              'deliberate', true,  'M3-D'),
        (NEW.id, 'order.amend',                  'deliberate', true,  'M3-D'),
        (NEW.id, 'order.cancel',                 'deliberate', true,  'M3-D'),
        (NEW.id, 'order.void',                   'deliberate', true,  'M3-D'),
        (NEW.id, 'terminal.revoke',              'deliberate', true,  'M3-D'),
        (NEW.id, 'session.close_with_exception', 'deliberate', true,  'M3-D'),
        -- Graded now, offered from M4. FR-UX-015 names payment explicitly and the grade
        -- is the same whichever gate builds the screen.
        (NEW.id, 'payment.refund',               'deliberate', true,  'M4'),
        (NEW.id, 'check.void',                   'deliberate', true,  'M4'),
        (NEW.id, 'discount.high',                'deliberate', true,  'M4');
    RETURN NULL;
END;
$$;

-- ---------------------------------------------------------------------------
-- 2. A TENANT THAT ALREADY EXISTS (FR-UX-015)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION pos.install_registries_for(p_tenant_id uuid) RETURNS integer
-- SECURITY DEFINER for the same reason as the trigger above. Row level security is
-- FORCED on both registries and their policies read the session context, so the caller
-- still has to be in the tenant they are naming: definer rights widen what may be
-- written, never whose rows are visible.
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pos, identity, public
AS $$
DECLARE
    v_installed integer := 0;
    v_added     integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM org.tenant WHERE id = p_tenant_id) THEN
        RAISE EXCEPTION
            'TENANT_NOT_IN_SCOPE: tenant % is not visible in this context, so nothing '
            'can be installed for it. Set app.tenant_id first — this is the check the '
            'silent backfill in 0010 never made', p_tenant_id
            USING ERRCODE = 'HS404';
    END IF;

    INSERT INTO identity.governed_action
        (tenant_id, action_code, minimum_strength, step_up_required, step_up_max_age,
         governed_from_gate)
    SELECT p_tenant_id, a.code, 'strong', true, interval '5 minutes', a.gate
    FROM (VALUES
        ('order.void', 'M3'), ('session.close_with_exception', 'M3'),
        ('order.amend', 'M3'), ('terminal.revoke', 'M3')
    ) AS a(code, gate)
    WHERE NOT EXISTS (
        SELECT 1 FROM identity.governed_action g
        WHERE g.tenant_id = p_tenant_id AND g.action_code = a.code);
    GET DIAGNOSTICS v_added = ROW_COUNT;
    v_installed := v_installed + v_added;

    -- Seating is NOT a governed action and is deliberately absent from the list above.
    -- A governed action requires step-up authentication within five minutes; seating an
    -- empty table requires a waiter to be signed in and nothing further. Grading it and
    -- governing it are different questions and this migration answers only the first.
    INSERT INTO pos.confirmation_requirement
        (tenant_id, action_code, consequence, requires_reason, graded_from_gate)
    SELECT p_tenant_id, g.action_code, g.consequence, g.requires_reason, g.gate
    FROM (VALUES
        ('order.view',                   'routine'::pos.consequence,    false, 'M3-D'),
        ('order.line.add',               'routine',                     false, 'M3-D'),
        ('service_request.acknowledge',  'routine',                     false, 'M3-D'),
        ('service_request.complete',     'routine',                     false, 'M3-D'),
        ('session.resume',               'routine',                     false, 'M3-D'),
        ('table.seat',                   'routine',                     false, 'OP-C'),
        ('order.submit',                 'elevated',                    false, 'M3-D'),
        ('handover.propose',             'elevated',                    false, 'M3-D'),
        ('session.move',                 'elevated',                    false, 'M3-D'),
        ('allergy.declare',              'deliberate',                  true,  'M3-D'),
        ('order.amend',                  'deliberate',                  true,  'M3-D'),
        ('order.cancel',                 'deliberate',                  true,  'M3-D'),
        ('order.void',                   'deliberate',                  true,  'M3-D'),
        ('terminal.revoke',              'deliberate',                  true,  'M3-D'),
        ('session.close_with_exception', 'deliberate',                  true,  'M3-D'),
        ('payment.refund',               'deliberate',                  true,  'M4'),
        ('check.void',                   'deliberate',                  true,  'M4'),
        ('discount.high',                'deliberate',                  true,  'M4')
    ) AS g(action_code, consequence, requires_reason, gate)
    WHERE NOT EXISTS (
        SELECT 1 FROM pos.confirmation_requirement c
        WHERE c.tenant_id = p_tenant_id AND c.action_code = g.action_code);
    GET DIAGNOSTICS v_added = ROW_COUNT;
    v_installed := v_installed + v_added;

    RETURN v_installed;
END;
$$;

COMMENT ON FUNCTION pos.install_registries_for(uuid) IS
    'Installs the governed actions and confirmation grades a tenant needs. Idempotent, '
    'and required for tenants that predate the migration that added a grade — the tenant '
    'trigger covers everything created since, and OP-C added table.seat to both. Exists '
    'as a function rather than as a backfill statement because a migration runs with no '
    'tenant context and org.tenant is scoped by row level security, so a backfill SELECT '
    'over it matches nothing.';
