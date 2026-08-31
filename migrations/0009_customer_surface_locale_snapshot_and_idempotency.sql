-- ===========================================================================
-- 0009 — What the customer surface needs from the data layer
-- ===========================================================================
--
-- M2-C. Three things, none of which is a screen.
--
-- 1. A guest session needs a credential. M2-B gave a guest an identity with no phone,
--    no email and no registration, which is right, but a browser still has to prove it is
--    the same browser on the next request. The QR pattern is reused exactly: a token minted
--    once, returned once, and stored only as a hash.
--
-- 2. The locale a customer CHOSE has to outlive the page they chose it on (FR-I18N-005).
--    M3's order communications, M4's receipts and later analytics all read it. It is
--    recorded on the table session, and it is deliberately nullable: a session opened by
--    staff before any guest has chosen a language has no customer locale, and writing 'en'
--    there would be recording a choice nobody made.
--
-- 3. A retry must not commit twice. Nothing is committed at M2-C in the sense M3 and M4
--    mean it — there are no orders and no payments — but the customer writes that DO exist
--    (a cart line, an allergy concern) are the right place to establish the mechanism those
--    gates will inherit. A retry that adds a second cart line is harmless today and is a
--    double charge two gates from now.

-- ---------------------------------------------------------------------------
-- A credential for a guest, minted like a QR code
-- ---------------------------------------------------------------------------

ALTER TABLE service.guest_session
    ADD COLUMN token_hash bytea,
    ADD CONSTRAINT guest_session_token_is_sha256
        CHECK (token_hash IS NULL OR octet_length(token_hash) = 32),
    ADD CONSTRAINT guest_session_token_unique UNIQUE (token_hash);

COMMENT ON COLUMN service.guest_session.token_hash IS
    'SHA-256 of the bearer token the browser holds. The token itself is returned once by '
    'service.mint_guest_session() and stored nowhere, so a dump of this table lets nobody '
    'resume a guest''s session (FR-SEC-007). Nullable because M2-B creates guest sessions '
    'from the staff side too, and those have no browser to hold anything.';

CREATE FUNCTION service.mint_guest_session(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_expires_in interval DEFAULT interval '4 hours'
) RETURNS TABLE (guest_session_id uuid, guest_token text)
LANGUAGE plpgsql
AS $$
DECLARE
    v_token text;
    v_id    uuid;
BEGIN
    -- Same construction as service.issue_table_qr(): randomness only, nothing derived from
    -- the tenant, the outlet or the row, so a token decodes to nothing and neighbouring
    -- guests get unrelated values.
    v_token := replace(gen_random_uuid()::text, '-', '')
            || replace(gen_random_uuid()::text, '-', '');

    INSERT INTO service.guest_session (tenant_id, outlet_id, expires_at, token_hash)
    VALUES (p_tenant_id, p_outlet_id, now() + p_expires_in,
            sha256(convert_to(v_token, 'UTF8')))
    RETURNING id INTO v_id;

    guest_session_id := v_id;
    guest_token := v_token;
    RETURN NEXT;
END;
$$;

CREATE FUNCTION service.guest_session_for_token(p_tenant_id uuid, p_token text)
RETURNS uuid
LANGUAGE sql STABLE
AS $$
    SELECT g.id FROM service.guest_session g
    WHERE g.tenant_id = p_tenant_id
      AND g.token_hash = sha256(convert_to(p_token, 'UTF8'))
      AND g.expires_at > now()
      AND g.anonymized_at IS NULL;
$$;

-- ---------------------------------------------------------------------------
-- Getting in, and staying in
-- ---------------------------------------------------------------------------
--
-- The QR code stays exactly as M2-B made it: 244 bits of randomness with nothing about
-- the tenant, the outlet or the table inside it, because NC-M2-001 requires that and it
-- is right to. The tenant and outlet a guest is entering travel in the URL PATH instead,
-- where they are not secrets — the same arrangement M1-D already uses for staff session
-- tokens, whose first two dot-separated parts are a plain claim the database then checks.
--
-- open_guest_session() is the only door. It establishes context from the claim, looks the
-- code up UNDER that context so a forged claim simply finds no row, and clears the context
-- again before raising if nothing matches. The window in which a tenant context exists
-- without a verified credential is the inside of this one function, which is exactly the
-- shape identity.establish_session_context() already has.

CREATE FUNCTION service.open_guest_session(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_code      text
) RETURNS TABLE (guest_session_id uuid, guest_token text, scan_id uuid,
                 table_session_id uuid, table_display_name text)
LANGUAGE plpgsql
AS $$
DECLARE
    v_token   record;
    v_guest   record;
    v_scan    uuid;
    v_session record;
BEGIN
    PERFORM set_config('app.tenant_id',     coalesce(p_tenant_id::text, ''), true);
    PERFORM set_config('app.outlet_id',     coalesce(p_outlet_id::text, ''), true);
    PERFORM set_config('app.session_id',    '', true);
    PERFORM set_config('app.auth_strength', '', true);

    SELECT t.* INTO v_token FROM service.table_qr_token t
     WHERE t.token_hash = sha256(convert_to(p_code, 'UTF8'))
       AND t.revoked_at IS NULL;

    IF NOT FOUND THEN
        PERFORM set_config('app.tenant_id', '', true);
        PERFORM set_config('app.outlet_id', '', true);
        RAISE EXCEPTION
            'QR_CODE_NOT_LIVE: no live code for the presented value in the claimed scope'
            USING ERRCODE = 'HS401';
    END IF;

    SELECT * INTO v_session FROM service.table_session s
     WHERE s.table_node_id = v_token.table_node_id AND s.state = 'open';

    SELECT * INTO v_guest FROM service.mint_guest_session(p_tenant_id, v_token.outlet_id);

    INSERT INTO service.qr_scan
        (tenant_id, outlet_id, token_id, guest_session_id, occupancy_at_scan)
    VALUES (p_tenant_id, v_token.outlet_id, v_token.id, v_guest.guest_session_id,
            v_session.occupancy_number)
    RETURNING id INTO v_scan;

    guest_session_id   := v_guest.guest_session_id;
    guest_token        := v_guest.guest_token;
    scan_id            := v_scan;
    table_session_id   := v_session.id;
    SELECT n.display_name INTO table_display_name FROM org.org_node n
     WHERE n.id = v_token.table_node_id;
    RETURN NEXT;
END;
$$;

CREATE FUNCTION service.establish_guest_context(
    p_tenant_id    uuid,
    p_outlet_id    uuid,
    p_token_digest bytea
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_guest service.guest_session%ROWTYPE;
BEGIN
    PERFORM set_config('app.tenant_id',     coalesce(p_tenant_id::text, ''), true);
    PERFORM set_config('app.outlet_id',     coalesce(p_outlet_id::text, ''), true);
    PERFORM set_config('app.session_id',    '', true);
    PERFORM set_config('app.auth_strength', '', true);

    SELECT * INTO v_guest FROM service.guest_session g
     WHERE g.token_hash = p_token_digest
       AND g.expires_at > now()
       AND g.anonymized_at IS NULL;

    IF NOT FOUND THEN
        PERFORM set_config('app.tenant_id', '', true);
        PERFORM set_config('app.outlet_id', '', true);
        RAISE EXCEPTION
            'GUEST_SESSION_NOT_LIVE: no live guest session for the presented credential'
            USING ERRCODE = 'HS401';
    END IF;

    -- Row level security has already hidden any guest session outside the claimed scope,
    -- so this cannot fail. It is the second guard, for the same reason M1-C guards
    -- retention twice: the first one is one migration away from being gone.
    IF v_guest.tenant_id <> p_tenant_id OR v_guest.outlet_id <> p_outlet_id THEN
        PERFORM set_config('app.tenant_id', '', true);
        PERFORM set_config('app.outlet_id', '', true);
        RAISE EXCEPTION
            'GUEST_SESSION_NOT_LIVE: the credential does not belong to the claimed scope'
            USING ERRCODE = 'HS401';
    END IF;

    RETURN v_guest.id;
END;
$$;

COMMENT ON FUNCTION service.establish_guest_context(uuid, uuid, bytea) IS
    'Authenticates a guest bearer token and establishes TRANSACTION-LOCAL tenant and '
    'outlet context, exactly as identity.establish_session_context() does for staff. A '
    'guest holds no membership and no staff session: the context it establishes carries '
    'no app.session_id and no auth_strength, so nothing that requires either will run '
    'under it.';

-- ---------------------------------------------------------------------------
-- The locale snapshot (FR-I18N-005)
-- ---------------------------------------------------------------------------

ALTER TABLE service.table_session
    ADD COLUMN customer_locale menu.customer_locale,
    ADD COLUMN customer_locale_selected_at timestamptz,
    -- A locale with no moment attached is a value somebody defaulted rather than a choice
    -- somebody made. Both or neither.
    ADD CONSTRAINT table_session_locale_snapshot_is_a_choice CHECK (
        (customer_locale IS NULL) = (customer_locale_selected_at IS NULL));

COMMENT ON COLUMN service.table_session.customer_locale IS
    'The language the customer explicitly chose, snapshotted for M3''s order '
    'communications and M4''s receipts (FR-I18N-005). Nullable on purpose: no default is '
    'written, because a customer who has not chosen has not chosen English.';

CREATE FUNCTION service.record_locale_choice(
    p_tenant_id  uuid,
    p_session_id uuid,
    p_locale     menu.customer_locale
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE service.table_session
       SET customer_locale = p_locale, customer_locale_selected_at = now()
     WHERE tenant_id = p_tenant_id AND id = p_session_id AND state = 'open';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'LOCALE_SNAPSHOT_ABSENT: no open occupancy % to record a locale choice on',
            p_session_id USING ERRCODE = 'HS404';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Idempotency: a retry finishes the first attempt rather than starting a second
-- ---------------------------------------------------------------------------

CREATE TABLE service.idempotency_key (
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    scope          text NOT NULL,
    idem_key       text NOT NULL,

    -- What was asked for, the first time. A second call with the same key and a DIFFERENT
    -- body is a client defect, and returning the first result would quietly answer a
    -- question nobody asked. It is refused instead.
    request_digest bytea NOT NULL,

    result_id      uuid,
    created_at     timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (tenant_id, scope, idem_key),
    CONSTRAINT idempotency_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT idempotency_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT idempotency_scope_not_blank CHECK (btrim(scope) <> ''),
    CONSTRAINT idempotency_key_not_blank CHECK (btrim(idem_key) <> ''),
    CONSTRAINT idempotency_digest_is_sha256 CHECK (octet_length(request_digest) = 32)
);

COMMENT ON TABLE service.idempotency_key IS
    'One row per customer write that a browser may retry. The row is claimed BEFORE the '
    'work is done and carries the result afterwards, so a retry arriving while the first '
    'attempt is still in flight is refused rather than racing it. Nothing at M2-C is '
    'committed in the sense M3 and M4 mean, which is exactly why this is the cheap moment '
    'to build it: a duplicate cart line is an annoyance and a duplicate payment is not.';

CREATE FUNCTION service.claim_idempotency(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_scope     text,
    p_key       text,
    p_body      text
) RETURNS TABLE (is_replay boolean, result_id uuid)
LANGUAGE plpgsql
AS $$
DECLARE
    v_digest   bytea := sha256(convert_to(p_body, 'UTF8'));
    v_existing record;
BEGIN
    INSERT INTO service.idempotency_key
        (tenant_id, outlet_id, scope, idem_key, request_digest)
    VALUES (p_tenant_id, p_outlet_id, p_scope, p_key, v_digest)
    ON CONFLICT (tenant_id, scope, idem_key) DO NOTHING;

    IF FOUND THEN
        -- First arrival. The caller does the work and calls record_idempotent_result().
        is_replay := false;
        result_id := NULL;
        RETURN NEXT;
        RETURN;
    END IF;

    SELECT * INTO v_existing FROM service.idempotency_key k
     WHERE k.tenant_id = p_tenant_id AND k.scope = p_scope AND k.idem_key = p_key;

    IF v_existing.request_digest <> v_digest THEN
        RAISE EXCEPTION
            'IDEMPOTENCY_KEY_REUSED: key % was already used for a different request in '
            'scope %; returning the earlier result would answer a question nobody asked',
            p_key, p_scope USING ERRCODE = 'HS409';
    END IF;

    is_replay := true;
    result_id := v_existing.result_id;
    RETURN NEXT;
END;
$$;

CREATE FUNCTION service.record_idempotent_result(
    p_tenant_id uuid,
    p_scope     text,
    p_key       text,
    p_result_id uuid
) RETURNS void
LANGUAGE sql
AS $$
    UPDATE service.idempotency_key
       SET result_id = p_result_id
     WHERE tenant_id = p_tenant_id AND scope = p_scope AND idem_key = p_key;
$$;

-- ---------------------------------------------------------------------------
-- Row level security and grants, on the same predicate as everything else
-- ---------------------------------------------------------------------------

ALTER TABLE service.idempotency_key ENABLE ROW LEVEL SECURITY;
ALTER TABLE service.idempotency_key FORCE  ROW LEVEL SECURITY;
CREATE POLICY idempotency_key_isolation ON service.idempotency_key FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

GRANT SELECT, INSERT, UPDATE ON service.idempotency_key TO hospitality_app;


-- ---------------------------------------------------------------------------
-- A published menu, in the language the guest is reading
-- ---------------------------------------------------------------------------
--
-- M2-B's version returned the snapshot line's canonical_name, which is English, in every
-- locale. The allergen warnings beside it were correctly translated, so an Amharic guest
-- was shown a warning they could read attached to a dish name they could not. Found by
-- rendering it: the SQL was self-consistent and the screen was not.
--
-- The pinned canonical name STAYS — it is what was published, and M3 will reference it.
-- What is added is the display name, resolved from the approved translation for the
-- requested locale, falling back to the canonical text where a menu is being read in a
-- locale that was not required at publication.
--
-- This does not disturb the price/allergen asymmetry recorded at M2-B. A name is content,
-- like an allergen: showing a guest the current approved translation is right. The
-- canonical name travelling beside it is the evidence, and it is unchanged.

DROP FUNCTION menu.published_menu_for_guest(uuid, uuid, menu.customer_locale);

CREATE FUNCTION menu.published_menu_for_guest(
    p_tenant_id   uuid,
    p_snapshot_id uuid,
    p_locale      menu.customer_locale
) RETURNS TABLE (item_code text, canonical_name text, display_name text,
                 currency_code char(3), amount_minor money.amount_minor,
                 allergen_kitchen_code text,
                 declaration_class safety.declaration_class,
                 written_warning text, icon_key text)
LANGUAGE sql STABLE
AS $$
    SELECT l.item_code,
           l.canonical_name,
           coalesce(t.translated_text, l.canonical_name),
           l.currency_code, l.amount_minor,
           s.kitchen_code, s.declaration_class, s.written_warning, s.icon_key
    FROM menu.publication_snapshot_line l
    LEFT JOIN menu.translation t
           ON t.tenant_id = l.tenant_id AND t.entity = 'item' AND t.entity_id = l.item_id
          AND t.field_name = 'canonical_name' AND t.locale = p_locale
          AND t.state = 'approved'
    LEFT JOIN LATERAL safety.selection_safety(
        p_tenant_id, p_locale, l.item_id, l.variant_id) s ON true
    WHERE l.snapshot_id = p_snapshot_id AND l.tenant_id = p_tenant_id
    ORDER BY l.item_code, s.kitchen_code;
$$;

COMMENT ON FUNCTION menu.published_menu_for_guest IS
    'A published menu as a guest sees it. The price is the pinned one; the allergens and '
    'the display name are the current approved ones. That asymmetry is the central design '
    'decision of M2-B: a price must be what was agreed, and everything a guest reads to '
    'decide with must be what is true. canonical_name travels beside display_name because '
    'it is what was published and M3 will reference it.';
