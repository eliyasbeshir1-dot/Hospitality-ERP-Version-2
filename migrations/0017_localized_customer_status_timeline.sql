-- =============================================================================
-- 0017 — The customer status timeline, in the language the guest chose
-- =============================================================================
-- THE GUEST PICKED A LANGUAGE AND THE TIMELINE ANSWERED IN ENGLISH.
--
-- FR-NOT-012's gate-local behaviour for M3 is "the staff notification center renders in
-- English and the customer status timeline renders in the session language".
-- FR-I18N-001B: "order status and service text render in the session language across the
-- ordering and service journeys", journey-linked to GJ-01A, GJ-02 and GJ-03A.
-- FR-I18N-008: customer status communications use the language snapshotted on the table
-- session or order, with approved fallback rules.
--
-- The SERVICE half was true from M3-C: notify.render_for() resolves an approved body in
-- the recipient's language and falls back to the approved English source. The STATUS
-- half was not. ordering.write_timeline_entry() writes 'Your order was received.' as an
-- English literal, and fulfillment's fold writes 'Your order is being prepared.' the
-- same way. ordering.customer_order.customer_locale — the snapshot FR-I18N-005 requires,
-- taken at M2-C and asserted by every slice since — was written, stored, compared, and
-- never once read by the thing a guest actually reads.
--
-- No slice check found it. Each slice read its own timeline in English and asked whether
-- it said the right thing; none asked what language it said it in. GJ-02 and GJ-03A
-- found it on the first run, because a journey walks the guest's screen in the guest's
-- language and there is no way to walk it without noticing. That is the whole argument
-- for end-to-end journeys, made by the journeys themselves.
--
-- WHAT IS NOT DONE HERE, AND WHY.
--
-- The stored customer_summary is not rewritten and write_timeline_entry() is not
-- replaced. The projection keeps the English it has always kept, because:
--
--   * it is FR-I18N-008's approved fallback, and a fallback that is a real approved
--     sentence beats a key name — the same reasoning notify.render_for() carries;
--   * it is what the projection digest is computed over, so a rebuild written before
--     this migration and one written after still agree;
--   * a locale is snapshotted per ORDER, and the projection is folded from a ledger that
--     knows nothing about who is reading. Baking one reader's language into a projection
--     would make the fold depend on the audience, which is the mistake M3-A avoided when
--     it decided the AUDIENCE of a timeline entry once, at write time, and the WORDING
--     nowhere.
--
-- So the resolution happens where the reader is known: at read time, against the locale
-- the order carries, through the store M2-A already governs.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- The identity of a customer-facing status wording
-- ---------------------------------------------------------------------------
-- Identity only, exactly as notify.template is identity only: the approved BODY in each
-- customer language lives in menu.translation under entity 'order_status_wording', so
-- M2-A's approval workflow governs it unchanged rather than being written a second time.
--
-- One row per (tenant, event kind). The kinds a guest is shown are the ones M3-A and
-- M3-B marked visible_to_customer; a kind with no row here falls back to the English in
-- the projection, so this table can be filled in gradually without a period during which
-- a guest sees nothing.

CREATE TABLE notify.status_wording (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL,

    -- Nullable, and NULL in every row this gate creates: the wording is a tenant's voice
    -- rather than one outlet's, exactly as notify.template carries a nullable outlet_id
    -- it does not yet use. It is here because the isolation predicate is
    -- app.row_in_scope(tenant_id, outlet_id) everywhere in this schema and a second shape
    -- of that predicate is a second thing to get right; a tenant-wide row scopes on the
    -- tenant because its outlet is NULL, which is the case app.row_in_scope() was written
    -- to accept. pos.confirmation_requirement took the other route at M3-D and needed its
    -- own branch in the policy loop to do it.
    outlet_id   uuid,

    event_kind  ordering.event_kind NOT NULL,

    -- The English source. FR-I18N-008's approved fallback when no translation exists in
    -- the session language, and the string a reviewer translates FROM.
    source_text text NOT NULL,

    status      org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version bigint NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT status_wording_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT status_wording_one_per_kind UNIQUE (tenant_id, event_kind),
    CONSTRAINT status_wording_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT status_wording_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT status_wording_source_not_blank CHECK (btrim(source_text) <> ''),
    CONSTRAINT status_wording_row_version_positive CHECK (row_version > 0)
);

CREATE TRIGGER status_wording_row_version
    BEFORE UPDATE ON notify.status_wording
    FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version();

COMMENT ON TABLE notify.status_wording IS
    'FR-NOT-012, FR-I18N-001B, FR-I18N-008. What a guest is told when their order '
    'reaches a state, in the language they chose. Identity and the English source only: '
    'the Amharic and Arabic bodies live in menu.translation under entity '
    'order_status_wording, where a human has to review and approve them and '
    'menu.enforce_translation_review() refuses an approval nobody reviewed. That is also '
    'why no migration installs the wording: an approved translation asserts that a '
    'person read it, and a migration writing one would be forging that assertion.';

ALTER TABLE notify.status_wording ENABLE ROW LEVEL SECURITY;
ALTER TABLE notify.status_wording FORCE ROW LEVEL SECURITY;

-- The one isolation predicate, unchanged and unbranched. A tenant-wide row carries a
-- NULL outlet and scopes on the tenant, which is the case app.row_in_scope() already
-- accepts — so "belongs to the whole tenant" is a property of the ROW rather than a
-- second policy shape somebody has to notice.
CREATE POLICY status_wording_isolation ON notify.status_wording FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));


-- ---------------------------------------------------------------------------
-- The resolver
-- ---------------------------------------------------------------------------
-- Deliberately the same three lines as notify.render_for(), because it is the same rule:
-- the approved translation in the reader's language, or the approved English source
-- where the fallback rules permit it, or NULL meaning there is nothing approved to say.
-- NULL is what lets the caller fall through to the projection's own English rather than
-- rendering a blank.

CREATE FUNCTION notify.status_wording_for(
    p_tenant_id uuid, p_event_kind ordering.event_kind,
    p_locale menu.customer_locale) RETURNS text
LANGUAGE sql STABLE
AS $$
    SELECT coalesce(
        (SELECT tr.translated_text
           FROM menu.translation tr
          WHERE tr.tenant_id = p_tenant_id
            AND tr.entity = 'order_status_wording'
            AND tr.entity_id = w.id
            AND tr.field_name = 'body'
            AND tr.locale = p_locale
            AND tr.state = 'approved'),
        CASE WHEN p_locale = 'en' THEN w.source_text END)
      FROM notify.status_wording w
     WHERE w.tenant_id = p_tenant_id AND w.event_kind = p_event_kind
       AND w.status = 'active';
$$;

COMMENT ON FUNCTION notify.status_wording_for IS
    'FR-I18N-008''s approved fallback, applied to order status. NULL means nothing has '
    'been approved for this kind in this language, and the caller falls back to the '
    'English the projection already holds — which is itself an approved sentence rather '
    'than a key name.';


-- ---------------------------------------------------------------------------
-- The customer timeline, resolved against the locale the ORDER snapshotted
-- ---------------------------------------------------------------------------
-- Replaced rather than edited: 0010 is applied and checksum-locked, and this is the
-- CREATE OR REPLACE that every correction since M2-B has taken.
--
-- The locale comes from the ORDER, not from the session and not from the caller. An
-- order carries the language its guest chose at the moment they chose it (FR-I18N-005),
-- and a party that switches the table's language later has not retroactively ordered in
-- the new one. It is also the locale M4's receipt will read, so the timeline and the
-- receipt cannot disagree about what language this order was placed in.

CREATE OR REPLACE FUNCTION ordering.customer_timeline(p_tenant_id uuid, p_order_id uuid)
RETURNS TABLE (occurred_at timestamptz, kind ordering.event_kind, summary text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, ordering, notify, menu, public
AS $$
    SELECT t.occurred_at, t.kind,
           coalesce(notify.status_wording_for(t.tenant_id, t.kind, o.customer_locale),
                    t.customer_summary)
    FROM ordering.order_timeline_entry t
    JOIN ordering.customer_order o
      ON o.tenant_id = t.tenant_id AND o.id = t.order_id
    WHERE t.tenant_id = p_tenant_id AND t.order_id = p_order_id
      AND t.visible_to_customer
    ORDER BY t.occurred_at, t.sequence_number;
$$;

COMMENT ON FUNCTION ordering.customer_timeline(uuid, uuid) IS
    'FR-ORD-016A and FR-NOT-012. What the guest sees, in the language the order '
    'snapshotted. The AUDIENCE is still decided once, at write time, by M3-A''s '
    'visible_to_customer — this changes the wording and nothing about who may read it. '
    'A kind with no approved wording renders the English the projection holds, which is '
    'FR-I18N-008''s approved fallback and not a blank.';


-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

GRANT SELECT ON notify.status_wording TO hospitality_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON notify.status_wording TO hospitality_migrator;
GRANT EXECUTE ON FUNCTION notify.status_wording_for(uuid, ordering.event_kind,
                                                    menu.customer_locale)
    TO hospitality_app;
