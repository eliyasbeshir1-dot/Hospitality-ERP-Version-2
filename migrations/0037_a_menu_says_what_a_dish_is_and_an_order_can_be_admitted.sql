-- 0037: a menu says what a dish is, and an order can be admitted by somebody
--
-- Three things, all found by opening the floor and using it.
--
-- ONE. THE MENU RETURNED A NAME AND A PRICE AND NOTHING ELSE.
--
-- FR-MNU-004 asks a menu to carry a description, the customer-visible ingredients and a
-- preparation time. seeds/0003 writes all three for every dish on the demonstration floor,
-- and menu.published_menu_for_guest() has never returned any of them — so the data was
-- there, the requirement was met in the schema, and a guest saw "Ethiopian Coffee ETB
-- 60.00". The gap was one function wide.
--
-- WHERE THE DESCRIPTIVE FIELDS COME FROM, AND WHY IT IS NOT THE SNAPSHOT. The commercial
-- terms — price, currency, availability, tax context — are read from
-- menu.publication_snapshot_line, because a guest must be charged what was published and
-- an order references the snapshot to prove it. The PROSE is read from
-- menu.sellable_item, live. A snapshot pins what somebody agreed to pay; a corrected
-- description is not a change to that agreement, and freezing the words would mean a
-- typo in an ingredient list could only be fixed by republishing the menu. The two are
-- joined on the snapshot's own item_id, so a dish that was never published cannot appear
-- by having been edited.
--
-- IMAGES ARE NOT CLOSED HERE AND ARE NOT PRETENDED TO BE. FR-MNU-004 also asks for
-- images and FR-MNU-011 for derivatives with alt text. menu.image and
-- menu.image_derivative exist, carry alt text, and hold ZERO rows on any database this
-- repository builds. That is not the whole of it: menu.image is private by CHECK
-- CONSTRAINT — `image_source_is_private CHECK (is_private)`, with no value that publishes
-- it — and menu.image_derivative's own comment says "none is public. Access to any of
-- them goes through the same signed, expiring, authorized URL path as the source." NO
-- SUCH PATH EXISTS. There is no route in api/src that serves an image or signs a URL for
-- one. So seeding image rows would hand the guest surface a storage key it cannot turn
-- into a src, and rendering an <img> at nothing is worse than rendering none. Images need
-- a serving subsystem — storage, signing, expiry, authorization — which is a gate, not a
-- column. Recorded in planning/OPD_FINDINGS.md rather than half-built.
--
-- TWO. NOTHING COULD ADMIT A GUEST ORDER TO THE KITCHEN.
--
-- The seeded ordering policy makes guest_qr orders staff_confirmed, so a placed order
-- sits in 'submitted' until a person accepts it. POST /s/v1/orders/:orderId/accept exists
-- and works; no surface calls it, and no screen anywhere lists an order awaiting
-- acceptance. The station board shows TICKETS, and a submitted order is not yet a ticket —
-- so the order was invisible on every screen in the system until somebody accepted it, and
-- nobody could accept it because no screen showed it.
--
-- pos.pending_orders() is the list that was missing. It belongs to the WAITER floor and
-- not to the station board: a cook cooks, and gating an order is a host act. The station
-- board is deliberately not given this.
--
-- THREE. AND THE ACCEPT CONTROL NEEDS A GRADE BEFORE IT NEEDS A BUTTON.
--
-- 0036 recorded what happens when a new action reaches a staff screen ungraded: the
-- surface treats it as `deliberate`, demands a written reason, and the action never
-- happens. `order.accept` is a new action on the waiter floor and would meet that
-- default exactly as `table.seat` did. It is graded here, in the same commit that creates
-- the list it will appear on, rather than after somebody presses it and nothing happens.
--
-- `elevated`, not `routine`: admitting an order commits a kitchen to cooking it and a
-- guest to paying for it. It is not destructive and asks for no reason, but it is not the
-- same as glancing at a queue.

-- ---------------------------------------------------------------------------
-- 1. WHAT A MENU SAYS ABOUT A DISH (FR-MNU-004)
-- ---------------------------------------------------------------------------

DROP FUNCTION menu.published_menu_for_guest(uuid, uuid, menu.customer_locale);

CREATE FUNCTION menu.published_menu_for_guest(
    p_tenant_id   uuid,
    p_snapshot_id uuid,
    p_locale      menu.customer_locale
) RETURNS TABLE (item_code text, canonical_name text, display_name text,
                 currency_code char(3), amount_minor money.amount_minor,
                 allergen_kitchen_code text,
                 declaration_class safety.declaration_class,
                 written_warning text, icon_key text,
                 short_description text, long_description text,
                 customer_visible_ingredients text, preparation_minutes integer)
LANGUAGE sql STABLE
AS $$
    SELECT l.item_code,
           l.canonical_name,
           coalesce(t.translated_text, l.canonical_name),
           l.currency_code, l.amount_minor,
           s.kitchen_code, s.declaration_class, s.written_warning, s.icon_key,
           -- The prose, from the item rather than the snapshot. See the head of this
           -- file: the snapshot pins what is charged, not what a dish is described as.
           -- Translated exactly as the name is — same table, same approved state, same
           -- fallback to the canonical text rather than to nothing, because a guest
           -- reading Amharic would rather have an English ingredient list than none.
           -- customer_visible_ingredients is marked safety_critical in
           -- menu.translatable_field, and the fallback is what M2-A already does for the
           -- name: show the canonical words rather than silence.
           coalesce(td.translated_text, i.canonical_short_description),
           coalesce(tl.translated_text, i.canonical_long_description),
           coalesce(tg.translated_text, i.customer_visible_ingredients),
           i.preparation_minutes
    FROM menu.publication_snapshot_line l
    -- INNER, not LEFT. A snapshot line whose item has been deleted is not a dish anybody
    -- can order, and returning it with a null description would put an unnamed row on a
    -- guest's menu. The foreign key makes this unreachable; the join type says so anyway.
    JOIN menu.sellable_item i
      ON i.tenant_id = l.tenant_id AND i.id = l.item_id
    LEFT JOIN menu.translation t
           ON t.tenant_id = l.tenant_id AND t.entity = 'item' AND t.entity_id = l.item_id
          AND t.field_name = 'canonical_name' AND t.locale = p_locale
          AND t.state = 'approved'
    LEFT JOIN menu.translation td
           ON td.tenant_id = l.tenant_id AND td.entity = 'item' AND td.entity_id = l.item_id
          AND td.field_name = 'canonical_short_description' AND td.locale = p_locale
          AND td.state = 'approved'
    LEFT JOIN menu.translation tl
           ON tl.tenant_id = l.tenant_id AND tl.entity = 'item' AND tl.entity_id = l.item_id
          AND tl.field_name = 'canonical_long_description' AND tl.locale = p_locale
          AND tl.state = 'approved'
    LEFT JOIN menu.translation tg
           ON tg.tenant_id = l.tenant_id AND tg.entity = 'item' AND tg.entity_id = l.item_id
          AND tg.field_name = 'customer_visible_ingredients' AND tg.locale = p_locale
          AND tg.state = 'approved'
    LEFT JOIN LATERAL safety.selection_safety(
        p_tenant_id, p_locale, l.item_id, l.variant_id) s ON true
    WHERE l.snapshot_id = p_snapshot_id AND l.tenant_id = p_tenant_id
    ORDER BY l.item_code, s.kitchen_code;
$$;

COMMENT ON FUNCTION menu.published_menu_for_guest(uuid, uuid, menu.customer_locale) IS
    'The published menu a guest reads (FR-MNU-004, FR-I18N-006). Commercial terms come '
    'from the immutable snapshot; the description, ingredients and preparation time come '
    'from the item, translated where an approved translation exists. Images are absent '
    'and deliberately so — there is no path in this build that serves one, and a column '
    'that is always null would claim otherwise.';

-- ---------------------------------------------------------------------------
-- 2. THE ORDERS WAITING FOR SOMEBODY (FR-ORD-004, FR-ORD-007A)
-- ---------------------------------------------------------------------------

CREATE FUNCTION pos.pending_orders(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (
    order_id          uuid,
    order_number      text,
    table_session_id  uuid,
    table_reference   text,
    origin            text,
    submitted_at      timestamptz,
    waiting_seconds   integer,
    lines             integer,
    total_amount_minor bigint,
    currency_code     char(3)
)
LANGUAGE sql STABLE
AS $$
    SELECT o.id,
           o.order_number,
           o.table_session_id,
           n.reference_code,
           o.origin::text,
           o.submitted_at,
           -- Elapsed, not a timestamp. The screen that reads this answers "what has been
           -- waiting longest", and a clock time is not an elapsed time to somebody
           -- deciding what to do next.
           extract(epoch FROM (now() - o.submitted_at))::integer,
           (SELECT count(*)::integer FROM ordering.order_line ol
             WHERE ol.tenant_id = o.tenant_id AND ol.order_id = o.id),
           o.total_amount_minor,
           o.currency_code
      FROM ordering.customer_order o
      LEFT JOIN service.table_session ts
             ON ts.tenant_id = o.tenant_id AND ts.id = o.table_session_id
      LEFT JOIN org.org_node n
             ON n.tenant_id = ts.tenant_id AND n.id = ts.table_node_id
     WHERE o.tenant_id = p_tenant_id
       AND o.outlet_id = p_outlet_id
       -- 'submitted' is the whole of the condition, and it is derived rather than
       -- configured: an order that has been accepted has left this list by having a
       -- different state, and one that was rejected or cancelled never appears. There is
       -- no "pending" flag to fall out of step with the state machine.
       AND o.state = 'submitted'
     ORDER BY o.submitted_at;
$$;

COMMENT ON FUNCTION pos.pending_orders(uuid, uuid) IS
    'FR-ORD-004. The orders a member of staff has still to admit to the kitchen, oldest '
    'first. Exists because a staff_confirmed order was invisible on every screen in the '
    'system: the station board shows tickets, and an unaccepted order has none. This is '
    'the waiter floor''s list, not the station board''s — a cook cooks, and gating an '
    'order is a host act.';

-- ---------------------------------------------------------------------------
-- 3. THE GRADE THAT MUST EXIST BEFORE THE BUTTON DOES (FR-UX-015)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION pos.install_confirmation_requirements() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pos, public
AS $$
BEGIN
    INSERT INTO pos.confirmation_requirement
        (tenant_id, action_code, consequence, requires_reason, graded_from_gate)
    VALUES
        (NEW.id, 'order.view',                   'routine',    false, 'M3-D'),
        (NEW.id, 'order.line.add',               'routine',    false, 'M3-D'),
        (NEW.id, 'service_request.acknowledge',  'routine',    false, 'M3-D'),
        (NEW.id, 'service_request.complete',     'routine',    false, 'M3-D'),
        (NEW.id, 'session.resume',               'routine',    false, 'M3-D'),
        (NEW.id, 'table.seat',                   'routine',    false, 'OP-C'),
        (NEW.id, 'order.submit',                 'elevated',   false, 'M3-D'),
        (NEW.id, 'handover.propose',             'elevated',   false, 'M3-D'),
        (NEW.id, 'session.move',                 'elevated',   false, 'M3-D'),
        -- Admitting an order commits a kitchen to cooking it and a guest to paying for
        -- it. Not destructive and asking no reason, but not a glance either.
        (NEW.id, 'order.accept',                 'elevated',   false, 'OP-D'),
        (NEW.id, 'allergy.declare',              'deliberate', true,  'M3-D'),
        (NEW.id, 'order.amend',                  'deliberate', true,  'M3-D'),
        (NEW.id, 'order.cancel',                 'deliberate', true,  'M3-D'),
        (NEW.id, 'order.void',                   'deliberate', true,  'M3-D'),
        (NEW.id, 'terminal.revoke',              'deliberate', true,  'M3-D'),
        (NEW.id, 'session.close_with_exception', 'deliberate', true,  'M3-D'),
        (NEW.id, 'payment.refund',               'deliberate', true,  'M4'),
        (NEW.id, 'check.void',                   'deliberate', true,  'M4'),
        (NEW.id, 'discount.high',                'deliberate', true,  'M4');
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION pos.install_registries_for(p_tenant_id uuid) RETURNS integer
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

    -- Neither seating nor accepting is a GOVERNED action, and both are deliberately
    -- absent from the list above. A governed action requires step-up authentication
    -- within five minutes; admitting an order requires a signed-in member of staff and
    -- nothing further. Grading an action and governing it are different questions.
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
        ('order.accept',                 'elevated',                    false, 'OP-D'),
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

-- ---------------------------------------------------------------------------
-- 4. PRIVILEGE
-- ---------------------------------------------------------------------------

GRANT EXECUTE ON FUNCTION menu.published_menu_for_guest(uuid, uuid, menu.customer_locale)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION pos.pending_orders(uuid, uuid) TO hospitality_app;
