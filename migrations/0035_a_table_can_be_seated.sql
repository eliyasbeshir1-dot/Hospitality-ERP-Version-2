-- 0035: a table can be seated, and a basket can be changed back
--
-- THE DEFECT, AS THE FIRST PERSON TO OPEN THE FLOOR FOUND IT.
--
-- `INSERT INTO service.table_session` occurred in exactly four files in this repository,
-- and all four were tests. No route, no migration and no seed opened a table occupancy.
-- service.join_table_session() JOINS an existing one, and there was never one to join, so
-- a guest who scanned the placard got a guest session, a scan row, and then
-- NO_OPEN_OCCUPANCY from every route that needed a seat. Every journey, every fixture and
-- OP-A's own order helper created the occupancy with a direct INSERT and then proved that
-- everything downstream worked. They were all correct about what they tested and all
-- silent about the step none of them took. Nineteen suites stayed green while the first
-- action a real guest takes was impossible.
--
-- The same shape, one level out, is why nothing here is only about seating. FR-TAB-006's
-- handover moves ownership between waiters; pos.acknowledge_handover() is the sole
-- non-test writer of service.table_ownership, and pos.propose_handover() requires an
-- existing owner to hand over FROM. So the FIRST owner of a table could never be
-- established by the delivered code path either, and pos.table_view() reported 'no waiter
-- is accountable for this table' for every table forever. A chain with no origin is not a
-- chain. Seating by a member of staff is that origin, and it is written here.
--
-- WHAT DECIDES WHO MAY OPEN AN OCCUPANCY. A guest scanning an unoccupied table opens it;
-- that scan is the seating act. A member of staff can open one too. This is one function
-- with two opening sources, because service.table_session.opening_source has recorded
-- which one since M2-B — a column with three values implies more than one writer, and
-- until now it had none. Requiring staff to seat first would defeat QR ordering outright:
-- the guest sits, scans, and waits for somebody to notice them.
--
-- WHAT THIS DOES NOT CHANGE. service.join_table_session() is untouched, and so is the
-- stale-QR guarantee inside it. A scan taken under one occupancy still cannot join
-- another without one of the tenant's configured verification methods and evidence of it,
-- and the absence of configuration still fails closed. Opening is a different act from
-- joining and is not a way around it: the guest who opens is enrolled as a participant of
-- the occupancy they opened, in the same statement, and no qr_scan row is ever rewritten
-- to make a join succeed. service.qr_scan.occupancy_at_scan means what its own comment
-- says it means — the occupancy in force when the code was scanned — and a function that
-- edited it afterwards would make that sentence false for every reader of the column.
--
-- WHAT THIS DOES NOT CLAIM, STATED HERE BECAUSE IT IS A REAL EXPOSURE AND NOT AN EDGE
-- CASE. A placard is a long-lived secret and service.open_guest_session() applies no
-- freshness test to it, so a photographed code can open an occupancy on an EMPTY table
-- from anywhere. The party that later sits at that table scans fresh, matches the
-- occupancy the stranger opened, and joins a session the stranger is already in — able to
-- read what they order, to place orders against the same session, and on a shared bill to
-- be paid for by them. The stale-QR rule does not fire, and the reason is precise: it
-- refuses a scan bound to an occupancy OTHER than the open one, and the stranger's scan
-- was bound to this occupancy at the moment it began rather than after. That is a hole in
-- that guard, not a case outside it. It is recorded in planning/OPC_FINDINGS.md with the
-- options that would close it; none is chosen here, because each is a product decision.

-- ---------------------------------------------------------------------------
-- 1. OPENING AN OCCUPANCY (FR-TAB-003)
-- ---------------------------------------------------------------------------

CREATE FUNCTION service.open_table_session(
    p_tenant_id          uuid,
    p_table_node_id      uuid,
    p_opening_source     service.opening_source,
    p_host_staff_user_id uuid DEFAULT NULL,
    p_guest_session_id   uuid DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_outlet uuid;
    v_id     uuid;
BEGIN
    -- The outlet is the TABLE'S, read from its profile, never taken from the caller. A
    -- caller-supplied outlet is an outlet a caller can choose, and row level security
    -- would then be being asked to check a claim against itself.
    SELECT p.outlet_id INTO v_outlet
      FROM service.table_profile p
     WHERE p.tenant_id = p_tenant_id AND p.table_node_id = p_table_node_id;

    IF v_outlet IS NULL THEN
        RAISE EXCEPTION 'TABLE_UNKNOWN: no table % resolves in this scope',
            p_table_node_id USING ERRCODE = 'HS404';
    END IF;

    -- Who opened it, tested per source rather than by one nullable argument that means
    -- something different depending on the other. The CHECK on the table already refuses
    -- a staff opening with no host named; this refuses the three remaining nonsense
    -- combinations by name, so a caller gets a reason instead of a constraint violation.
    IF p_opening_source = 'qr_scan' THEN
        IF p_guest_session_id IS NULL THEN
            RAISE EXCEPTION
                'OPENING_SOURCE_UNATTRIBUTED: a qr_scan opening is a guest seating '
                'themselves and must name the guest session that did it'
                USING ERRCODE = 'HS422';
        END IF;
        IF p_host_staff_user_id IS NOT NULL THEN
            RAISE EXCEPTION
                'OPENING_SOURCE_UNATTRIBUTED: a qr_scan opening names no host; a table '
                'seated by a member of staff is opening_source staff or host_stand'
                USING ERRCODE = 'HS422';
        END IF;
    ELSE
        IF p_host_staff_user_id IS NULL THEN
            RAISE EXCEPTION
                'OPENING_SOURCE_UNATTRIBUTED: a % opening must name the member of staff '
                'who seated the table', p_opening_source USING ERRCODE = 'HS422';
        END IF;
        IF p_guest_session_id IS NOT NULL THEN
            RAISE EXCEPTION
                'OPENING_SOURCE_UNATTRIBUTED: a % opening is a member of staff seating a '
                'table and names no guest session', p_opening_source
                USING ERRCODE = 'HS422';
        END IF;
    END IF;

    BEGIN
        INSERT INTO service.table_session
            (tenant_id, outlet_id, table_node_id, occupancy_number, opening_source,
             host_staff_user_id)
        SELECT p_tenant_id, v_outlet, p_table_node_id,
               -- Monotonic per table, from the table's own history. M2-B made the
               -- occupancy number the thing that distinguishes "the party after you"
               -- from "later than you", and a number taken from a clock or a sequence
               -- would not carry that meaning.
               coalesce(max(s.occupancy_number), 0) + 1,
               p_opening_source, p_host_staff_user_id
          FROM service.table_session s
         WHERE s.tenant_id = p_tenant_id AND s.table_node_id = p_table_node_id
        RETURNING id INTO v_id;
    EXCEPTION WHEN unique_violation THEN
        -- table_session_one_open_per_table and table_session_occupancy_unique. Two
        -- people seating the same table in the same instant is not a fault, and it is
        -- the ordinary case at an empty table where a party of four all scan at once.
        -- The loser is told the table is already occupied, by name, so a caller can join
        -- instead of retrying an open that will never succeed.
        RAISE EXCEPTION
            'OCCUPANCY_ALREADY_OPEN: table % already has an open occupancy',
            p_table_node_id USING ERRCODE = 'HS409';
    END;

    IF p_opening_source = 'qr_scan' THEN
        -- The guest who opened the occupancy is IN it. Enrolled here, in the same
        -- statement that created it, rather than by a follow-on call to
        -- join_table_session() — which would be asked to compare this guest's scan
        -- against an occupancy that did not exist when the scan was taken, and would
        -- correctly refuse. Opening and joining are different acts; this is the first.
        INSERT INTO service.session_participant
            (tenant_id, outlet_id, table_session_id, guest_session_id)
        VALUES (p_tenant_id, v_outlet, v_id, p_guest_session_id)
        ON CONFLICT (table_session_id, guest_session_id) DO NOTHING;
    ELSE
        -- FR-TAB-006's origin. The waiter who seats the table is accountable for it from
        -- that moment, which is both how service works and the only way the handover
        -- chain can ever start: pos.propose_handover() hands over FROM an existing owner,
        -- so with no first owner there was nothing to propose and the whole requirement
        -- was unreachable in the delivered code path.
        --
        -- assigned_by is the same person. Nobody else has decided anything yet, and
        -- naming a supervisor who was not consulted would be a fiction in an audit
        -- column. Whether the waiter who seats is always the waiter accountable — as
        -- against a separate assignment on the floor screen, which is how sections
        -- actually work in a large room — is an open product question recorded in
        -- planning/OPC_FINDINGS.md. It is answerable later without unpicking this,
        -- because moving ownership is exactly what propose_handover() is for.
        INSERT INTO service.table_ownership
            (tenant_id, outlet_id, table_session_id, primary_waiter_user_id,
             assigned_by_user_id)
        VALUES (p_tenant_id, v_outlet, v_id, p_host_staff_user_id, p_host_staff_user_id);
    END IF;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION service.open_table_session(uuid, uuid, service.opening_source, uuid, uuid) IS
    'FR-TAB-003. The only writer of a table occupancy in the delivered code path, with '
    'both of the opening sources service.opening_source has recorded since M2-B: a guest '
    'seating themselves by scanning an unoccupied table, and a member of staff seating '
    'one. A guest opening is enrolled as a participant of the occupancy it opened; a '
    'staff opening additionally establishes the first service.table_ownership row, which '
    'is the origin FR-TAB-006''s handover chain has never had. It does not rewrite any '
    'qr_scan row and it does not relax service.join_table_session().';

-- ---------------------------------------------------------------------------
-- 2. THE ONE DOOR THE GUEST SURFACE USES (FR-TAB-003, FR-TAB-004, FR-TAB-010)
-- ---------------------------------------------------------------------------
--
-- The branch lives here rather than in the surface, for the reason every branch in this
-- repository lives in a function: a surface that decided whether to open or to join would
-- be a second opinion about whether a table is occupied, and the two would disagree the
-- moment a party sits down between the scan and the tap.
--
-- Note which half is which. OPENING is this gate's. JOINING is M2-B's, called unchanged,
-- with the verification arguments passed straight through — so the stale-QR refusal a
-- guest can resolve reaches them exactly as it did before, and this function adds no
-- branch in which a join simply proceeds.

CREATE FUNCTION service.seat_guest_from_scan(
    p_tenant_id    uuid,
    p_scan_id      uuid,
    p_verification service.verification_method DEFAULT NULL,
    p_evidence     text DEFAULT NULL
) RETURNS TABLE (table_session_id uuid, opened boolean)
LANGUAGE plpgsql
AS $$
DECLARE
    v_scan    record;
    v_token   record;
    v_session record;
BEGIN
    SELECT * INTO v_scan FROM service.qr_scan
     WHERE id = p_scan_id AND tenant_id = p_tenant_id;
    IF v_scan.id IS NULL THEN
        RAISE EXCEPTION 'SCAN_UNKNOWN: no scan % in this scope', p_scan_id
            USING ERRCODE = 'HS404';
    END IF;

    SELECT * INTO v_token FROM service.table_qr_token
     WHERE id = v_scan.token_id AND tenant_id = p_tenant_id;
    IF v_token.id IS NULL OR v_token.revoked_at IS NOT NULL THEN
        RAISE EXCEPTION 'QR_TOKEN_REVOKED: this code no longer resolves'
            USING ERRCODE = 'HS403';
    END IF;

    SELECT * INTO v_session FROM service.table_session
     WHERE tenant_id = p_tenant_id AND table_node_id = v_token.table_node_id
       AND state = 'open';

    IF v_session.id IS NOT NULL THEN
        table_session_id := service.join_table_session(
            p_tenant_id, p_scan_id, p_verification, p_evidence);
        opened := false;
        RETURN NEXT;
        RETURN;
    END IF;

    BEGIN
        table_session_id := service.open_table_session(
            p_tenant_id, v_token.table_node_id, 'qr_scan', NULL, v_scan.guest_session_id);
        opened := true;
    EXCEPTION WHEN SQLSTATE 'HS409' THEN
        -- Somebody seated this table between the SELECT above and the INSERT. The scan in
        -- hand was taken when the table was empty, so it is bound to no occupancy and
        -- join_table_session() will refuse it as stale — correctly, and this function
        -- does not talk it out of that. It hands the refusal on. The guest's device
        -- resolves it the way the rule asks anyone to: by presenting the code again,
        -- which produces a scan bound to the occupancy that is actually open.
        table_session_id := service.join_table_session(
            p_tenant_id, p_scan_id, p_verification, p_evidence);
        opened := false;
    END;
    RETURN NEXT;
END;
$$;

COMMENT ON FUNCTION service.seat_guest_from_scan(uuid, uuid, service.verification_method, text) IS
    'The guest surface''s one door after a scan (FR-TAB-003, FR-TAB-004). Opens the '
    'occupancy when the table is unoccupied and joins the open one otherwise, so the '
    'surface never decides which of the two a table needs. The joining half is '
    'service.join_table_session() called unchanged, stale-QR guarantee and all.';

-- ---------------------------------------------------------------------------
-- 3. WHICH TABLES A MEMBER OF STAFF CAN SEAT (FR-POS-004)
-- ---------------------------------------------------------------------------
--
-- pos.table_view() answers "what is happening on the floor" and returns one row per OPEN
-- occupancy, so a table with nobody at it is correctly absent from it. Seating needs the
-- complement, and it is a separate function rather than a nullable column added to that
-- one: "the tables that need attention" and "the tables that are free" are two questions,
-- and a single result set answering both would make every existing caller filter.

CREATE FUNCTION pos.seatable_tables(p_tenant_id uuid, p_outlet_id uuid)
RETURNS TABLE (
    table_node_id   uuid,
    table_reference text,
    display_name    text,
    seat_count      integer
)
LANGUAGE sql STABLE
AS $$
    SELECT p.table_node_id, n.reference_code, n.display_name, p.seat_count
      FROM service.table_profile p
      JOIN org.org_node n ON n.tenant_id = p.tenant_id AND n.id = p.table_node_id
     WHERE p.tenant_id = p_tenant_id
       AND p.outlet_id = p_outlet_id
       AND NOT EXISTS (
             SELECT 1 FROM service.table_session s
              WHERE s.tenant_id = p.tenant_id
                AND s.table_node_id = p.table_node_id
                AND s.state = 'open')
     ORDER BY n.reference_code;
$$;

COMMENT ON FUNCTION pos.seatable_tables(uuid, uuid) IS
    'FR-POS-004''s complement: the tables of this outlet with no open occupancy, which '
    'is the list a waiter seats from. Derived from the occupancies themselves, so it '
    'cannot disagree with pos.table_view() about which tables are busy.';

-- ---------------------------------------------------------------------------
-- 4. TAKING SOMETHING BACK OUT OF THE BASKET (FR-ORD-002)
-- ---------------------------------------------------------------------------
--
-- There was no way to. service.add_cart_line() has existed since M3-D and nothing has
-- ever removed one: not a function, not a route, not a control on any surface. Every
-- golden journey adds items and places the order, and none of them has ever changed its
-- mind, which is how an absence this plain survived M2-B, M2-C and three gates of browser
-- measurement.
--
-- The rule about WHEN this is allowed is not written here and is not repeated here.
-- service.refuse_change_to_submitted_cart() has fired on DELETE since M0's 0010 and has
-- simply never had a delete to fire on: a cart with an order against it is frozen, and
-- removing a line from it would change what somebody agreed to. This function does the
-- deletion and lets that trigger be the only statement of the rule, which is why there is
-- no EXISTS test against ordering.customer_order below. A second copy of that condition
-- is a second answer to "was this ordered", and the two would eventually differ.

CREATE FUNCTION service.remove_cart_line(
    p_tenant_id    uuid,
    p_cart_line_id uuid,
    p_cart_id      uuid DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_line record;
BEGIN
    SELECT * INTO v_line FROM service.cart_line
     WHERE tenant_id = p_tenant_id AND id = p_cart_line_id;

    -- Row level security has already hidden any line outside this caller's tenant and
    -- outlet, so a line belonging to somebody else is not refused here — it was never
    -- visible, and the answer is the same one a line that never existed gets.
    IF v_line.id IS NULL THEN
        RAISE EXCEPTION 'CART_LINE_UNKNOWN: no cart line % in this scope', p_cart_line_id
            USING ERRCODE = 'HS404';
    END IF;

    -- The basket a caller SAYS the line is in, checked against the basket it is in. A
    -- guest surface knows which basket it is holding; passing it means a line id lifted
    -- from somewhere else cannot be removed from a basket it was never part of, even
    -- within one outlet where row level security has nothing to say.
    IF p_cart_id IS NOT NULL AND v_line.cart_id <> p_cart_id THEN
        RAISE EXCEPTION
            'CART_LINE_UNKNOWN: line % is not in basket %', p_cart_line_id, p_cart_id
            USING ERRCODE = 'HS404';
    END IF;

    -- The modifiers first: cart_line_modifier references the line ON DELETE RESTRICT, so
    -- a line chosen with modifiers would otherwise be undeletable and the guest would be
    -- told the server had failed. The restriction is right — a modifier row outliving its
    -- line is an orphan — and clearing them is what removing the line means.
    DELETE FROM service.cart_line_modifier
     WHERE tenant_id = p_tenant_id AND cart_line_id = p_cart_line_id;

    DELETE FROM service.cart_line
     WHERE tenant_id = p_tenant_id AND id = p_cart_line_id;

    RETURN v_line.cart_id;
END;
$$;

COMMENT ON FUNCTION service.remove_cart_line(uuid, uuid, uuid) IS
    'FR-ORD-002 from the guest''s side: taking a line back out of a DRAFT basket. It '
    'states no rule about when that is allowed — service.refuse_change_to_submitted_cart() '
    'has refused a DELETE against an ordered cart since 0010 and is left as the only '
    'statement of it, so the route and the trigger cannot come to disagree about what '
    '"already ordered" means.';

-- ---------------------------------------------------------------------------
-- 5. PRIVILEGE
-- ---------------------------------------------------------------------------
--
-- Every function above is SECURITY INVOKER, so scope is the database's rather than a test
-- written beside the route: a sibling outlet's table and another tenant's waiter are
-- refused by the policy on service.table_session, not by an ownership check in a route
-- that can go stale beside it.

GRANT EXECUTE ON FUNCTION service.open_table_session(uuid, uuid, service.opening_source, uuid, uuid) TO hospitality_app;
GRANT EXECUTE ON FUNCTION service.seat_guest_from_scan(uuid, uuid, service.verification_method, text) TO hospitality_app;
GRANT EXECUTE ON FUNCTION service.remove_cart_line(uuid, uuid, uuid)   TO hospitality_app;
GRANT EXECUTE ON FUNCTION pos.seatable_tables(uuid, uuid)              TO hospitality_app;
