-- ===========================================================================
-- 0008 — Tables, QR, guest sessions, carts, allergens and dietary safety
-- ===========================================================================
--
-- M2-B. This migration introduces the first safety-critical data in the project.
-- An allergen declaration that is wrong, stale, or conveyed without words can hurt
-- someone, so the care taken here is the care M1-C took over money.
--
-- The governing design decision, taken deliberately and recorded because M3 and M4 both
-- inherit it:
--
--     A PRICE must be what was AGREED, so it is pinned into an immutable snapshot.
--     An ALLERGEN must be what is TRUE, so it is never pinned anywhere.
--
-- menu.publication_snapshot exists to make a price unarguable after the fact. Extending
-- it to carry allergen text would have been the natural symmetry and it would have been a
-- safety defect: a correction discovered after publication would sit unread until someone
-- happened to republish the menu, while every guest reading the published menu saw the
-- old text from an immutable record that by construction could not be corrected.
--
-- So safety data is resolved live, at read time, from the currently effective
-- declaration. What IS recorded at publication and at cart time is a REFERENCE to the
-- declaration version in force at that moment — safety.declaration_reference — which
-- exists purely so a later dispute can establish what was believed then. That table is
-- deliberately unreadable by the application role: a value that can be read is a value
-- that becomes a cache under deadline, and a cached allergen is the exact defect
-- FR-SAF-005 warns about.
--
-- Two new schemas:
--   safety   the allergen and dietary catalog, declarations, and live resolution
--   service  tables, QR tokens, occupancy, guests, carts and table ownership
--
-- Tables, service areas and preparation stations are NOT introduced here. They are
-- org.org_node rows: M1-A's node_kind already carried 'dining_table', 'service_area' and
-- 'preparation_station', so they inherit app.row_in_scope() isolation unchanged and
-- FR-CFG-001B's guided setup configures organizational nodes rather than a parallel
-- hierarchy that would have to be kept consistent with the first.

CREATE SCHEMA safety;
CREATE SCHEMA service;

COMMENT ON SCHEMA safety IS
    'Allergen and dietary safety: the tenant- and jurisdiction-configurable catalog, '
    'declarations by item, variant and modifier, and live resolution. Nothing here is '
    'cached or pinned into a customer-facing read path.';

COMMENT ON SCHEMA service IS
    'Table service: QR resolution, occupancy, guest sessions, carts before submission, '
    'and table ownership. Submission itself is M3 and has no representation here.';

-- ---------------------------------------------------------------------------
-- Composite key so a child row can require a specific kind of node
-- ---------------------------------------------------------------------------
--
-- org.org_node already guarantees a reference cannot cross tenants. What it cannot
-- express on its own is "this must be a dining table, not a device". Adding (tenant_id,
-- id, kind) as a unique key lets a child carry a fixed kind column and reference it, so
-- the constraint is declarative rather than a trigger that a later migration could drop
-- without anything noticing.

ALTER TABLE org.org_node
    ADD CONSTRAINT org_node_tenant_id_kind_unique UNIQUE (tenant_id, id, kind);

-- ===========================================================================
-- Safety catalog (FR-SAF-001, FR-SAF-002)
-- ===========================================================================

CREATE TYPE safety.declaration_class AS ENUM ('contains', 'may_contain', 'cross_contact');

COMMENT ON TYPE safety.declaration_class IS
    'Three distinct classes, never collapsed into one another. "Contains" is an '
    'ingredient. "May contain" is an uncertainty about what arrived or how it was '
    'prepared. "Cross contact" '
    'is shared equipment or surfaces. A guest with coeliac disease and a guest avoiding '
    'an ingredient by preference need different answers, and a model that stores only '
    '"has allergen" cannot give them.';

CREATE TYPE safety.review_state AS ENUM ('draft', 'in_review', 'approved');

CREATE TYPE safety.reference_context AS ENUM ('publication_snapshot', 'cart_line');

-- Jurisdictions are reference data: the set of allergens a regulator requires is a fact
-- about the jurisdiction, identical for every tenant operating in it. Not tenant-scoped,
-- and the application role reads it and never writes it.
CREATE TABLE safety.jurisdiction (
    code          text PRIMARY KEY,
    display_name  text NOT NULL,

    CONSTRAINT jurisdiction_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT jurisdiction_display_name_not_blank CHECK (btrim(display_name) <> '')
);

INSERT INTO safety.jurisdiction (code, display_name) VALUES
    ('ET', 'Ethiopia'),
    ('EU', 'European Union'),
    ('GB', 'United Kingdom');

CREATE TABLE safety.allergen (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    outlet_id         uuid,
    jurisdiction_code text NOT NULL,

    -- The staff-facing code, deliberately English and deliberately not translated.
    -- A kitchen runs on one vocabulary; a cook reading a ticket must not have to decide
    -- which language the word in front of them is in (FR-SAF-002).
    kitchen_code      text NOT NULL,

    -- The approved universal icon. There is no SELECT grant on this column for the
    -- application role: see the grants section. An icon is reachable only through
    -- safety.allergen_for_display() or safety.allergen_for_management(), both of which
    -- return it beside its written warning or refuse to return it at all.
    icon_key          text,

    status            org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version       bigint NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT allergen_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT allergen_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT allergen_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT allergen_jurisdiction_fk FOREIGN KEY (jurisdiction_code)
        REFERENCES safety.jurisdiction (code) ON DELETE RESTRICT,
    CONSTRAINT allergen_kitchen_code_not_blank CHECK (btrim(kitchen_code) <> ''),
    CONSTRAINT allergen_icon_key_not_blank CHECK (icon_key IS NULL OR btrim(icon_key) <> ''),
    CONSTRAINT allergen_row_version_positive CHECK (row_version > 0),
    CONSTRAINT allergen_unique UNIQUE (tenant_id, jurisdiction_code, kitchen_code)
);

COMMENT ON TABLE safety.allergen IS
    'The tenant and jurisdiction configurable allergen catalog (FR-SAF-001). Customer '
    'text lives in menu.translation as a safety-critical field, so it inherits the '
    'human-reviewer requirement and blocks publication when absent. The icon is stored '
    'here but is not readable by the application role: icons supplement written warnings '
    'and never replace them (FR-SAF-002), which is enforced by there being no query path '
    'that returns one without the other.';

CREATE INDEX allergen_tenant_idx ON safety.allergen (tenant_id, jurisdiction_code);

-- What a jurisdiction requires a tenant to declare on. A tenant operating in the EU
-- cannot quietly omit one of the fourteen; the publication block reads this.
CREATE TABLE safety.jurisdiction_requirement (
    jurisdiction_code text NOT NULL,
    kitchen_code      text NOT NULL,

    PRIMARY KEY (jurisdiction_code, kitchen_code),
    CONSTRAINT jurisdiction_requirement_fk FOREIGN KEY (jurisdiction_code)
        REFERENCES safety.jurisdiction (code) ON DELETE RESTRICT
);

INSERT INTO safety.jurisdiction_requirement (jurisdiction_code, kitchen_code) VALUES
    ('EU', 'GLUTEN'), ('EU', 'CRUSTACEANS'), ('EU', 'EGGS'), ('EU', 'FISH'),
    ('EU', 'PEANUTS'), ('EU', 'SOYBEANS'), ('EU', 'MILK'), ('EU', 'NUTS'),
    ('EU', 'CELERY'), ('EU', 'MUSTARD'), ('EU', 'SESAME'), ('EU', 'SULPHITES'),
    ('EU', 'LUPIN'), ('EU', 'MOLLUSCS'),
    ('GB', 'GLUTEN'), ('GB', 'CRUSTACEANS'), ('GB', 'EGGS'), ('GB', 'FISH'),
    ('GB', 'PEANUTS'), ('GB', 'SOYBEANS'), ('GB', 'MILK'), ('GB', 'NUTS'),
    ('GB', 'CELERY'), ('GB', 'MUSTARD'), ('GB', 'SESAME'), ('GB', 'SULPHITES'),
    ('GB', 'LUPIN'), ('GB', 'MOLLUSCS'),
    ('ET', 'GLUTEN'), ('ET', 'MILK'), ('ET', 'EGGS'), ('ET', 'PEANUTS'),
    ('ET', 'FISH'), ('ET', 'SESAME');

-- ---------------------------------------------------------------------------
-- Declarations (FR-SAF-002), by item, variant and modifier, with effective version
-- ---------------------------------------------------------------------------

CREATE TABLE safety.declaration (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    outlet_id         uuid,

    -- Reusing menu.menu_entity rather than inventing a second vocabulary for the same
    -- three things. Constrained to the three that can carry ingredients: a category or a
    -- daypart cannot.
    subject           menu.menu_entity NOT NULL,
    subject_id        uuid NOT NULL,

    allergen_id       uuid NOT NULL,
    declaration_class safety.declaration_class NOT NULL,

    -- Versioning is by supersession, not by editing. A correction inserts a new row and
    -- closes the old one, so the history of what was declared is intact and the current
    -- answer is always the open row. Nothing reads a version number to decide what to
    -- serve; the open row IS the answer.
    effective_version integer NOT NULL DEFAULT 1,
    effective_from    timestamptz NOT NULL DEFAULT now(),
    effective_to      timestamptz,

    review_state          safety.review_state NOT NULL DEFAULT 'draft',
    created_by_user_id    uuid NOT NULL,
    reviewed_by_user_id   uuid,
    reviewed_at           timestamptz,

    created_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT declaration_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT declaration_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT declaration_allergen_fk FOREIGN KEY (tenant_id, allergen_id)
        REFERENCES safety.allergen (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT declaration_author_fk FOREIGN KEY (tenant_id, created_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT declaration_reviewer_fk FOREIGN KEY (tenant_id, reviewed_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,

    CONSTRAINT declaration_subject_can_carry_ingredients CHECK (
        subject IN ('item', 'variant', 'modifier')),
    CONSTRAINT declaration_version_positive CHECK (effective_version > 0),
    CONSTRAINT declaration_range_ordered CHECK (
        effective_to IS NULL OR effective_to > effective_from),

    -- An approved declaration names the human who approved it and when. Same rule
    -- menu.translation applies to safety-critical text: without a named reviewer it is a
    -- draft wearing a label.
    CONSTRAINT declaration_approval_is_reviewed CHECK (
        (review_state = 'approved') = (reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL))
);

COMMENT ON TABLE safety.declaration IS
    'What an item, variant or modifier declares about an allergen, in one of three '
    'classes, with the version history intact (FR-SAF-002). The currently effective row '
    'is the one with effective_to IS NULL. There is no derived or cached table beside '
    'this one: safety.effective_allergens() computes from these rows on every call, '
    'because a stored answer that does not move when its inputs move is a safety defect '
    'rather than a caching bug (FR-SAF-005).';

-- One open declaration per subject and allergen. A correction must close the old row
-- before opening a new one, so "the current answer" cannot be ambiguous.
CREATE UNIQUE INDEX declaration_one_open_per_subject
    ON safety.declaration (tenant_id, subject, subject_id, allergen_id)
    WHERE effective_to IS NULL;

CREATE INDEX declaration_subject_idx ON safety.declaration (tenant_id, subject, subject_id);

-- ---------------------------------------------------------------------------
-- Dietary claims (FR-SAF-006)
-- ---------------------------------------------------------------------------

CREATE TABLE safety.dietary_claim (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             uuid NOT NULL,
    outlet_id             uuid,
    code                  text NOT NULL,

    -- A claim without a written definition is a marketing word. "Vegetarian" means
    -- different things to different kitchens, and the tenant has to say which it means
    -- before anyone can be held to it.
    definition            text NOT NULL,

    -- The person answerable for the evidence behind the claim, and the date the claim
    -- must be looked at again. Both required: an unowned claim with no review date is how
    -- a kitchen ends up serving a four-year-old assertion.
    evidence_owner_user_id uuid NOT NULL,
    review_due_on         date NOT NULL,

    status                org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version           bigint NOT NULL DEFAULT 1,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT dietary_claim_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT dietary_claim_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT dietary_claim_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT dietary_claim_owner_fk FOREIGN KEY (tenant_id, evidence_owner_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT dietary_claim_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT dietary_claim_definition_not_blank CHECK (btrim(definition) <> ''),
    CONSTRAINT dietary_claim_row_version_positive CHECK (row_version > 0),
    CONSTRAINT dietary_claim_unique UNIQUE (tenant_id, code)
);

COMMENT ON TABLE safety.dietary_claim IS
    'Vegetarian, vegan, fasting, halal and whatever else a tenant defines (FR-SAF-006). '
    'Fasting is a first-class claim rather than a note: in the pilot market a large share '
    'of the calendar is fasting, and an outlet that cannot state it loses the business.';

-- Outlet applicability. A claim a tenant can substantiate in one kitchen is not
-- automatically true in another, so applicability is recorded per outlet rather than
-- assumed tenant-wide.
CREATE TABLE safety.dietary_claim_outlet (
    tenant_id  uuid NOT NULL,
    claim_id   uuid NOT NULL,
    outlet_id  uuid NOT NULL,

    PRIMARY KEY (claim_id, outlet_id),
    CONSTRAINT dietary_claim_outlet_claim_fk FOREIGN KEY (tenant_id, claim_id)
        REFERENCES safety.dietary_claim (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT dietary_claim_outlet_node_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT
);

CREATE TABLE safety.item_dietary_claim (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    outlet_id         uuid,
    subject           menu.menu_entity NOT NULL,
    subject_id        uuid NOT NULL,
    claim_id          uuid NOT NULL,

    effective_version integer NOT NULL DEFAULT 1,
    effective_from    timestamptz NOT NULL DEFAULT now(),
    effective_to      timestamptz,

    review_state          safety.review_state NOT NULL DEFAULT 'draft',
    created_by_user_id    uuid NOT NULL,
    reviewed_by_user_id   uuid,
    reviewed_at           timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT item_dietary_claim_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT item_dietary_claim_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT item_dietary_claim_claim_fk FOREIGN KEY (tenant_id, claim_id)
        REFERENCES safety.dietary_claim (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT item_dietary_claim_author_fk FOREIGN KEY (tenant_id, created_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT item_dietary_claim_reviewer_fk FOREIGN KEY (tenant_id, reviewed_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT item_dietary_claim_subject CHECK (subject IN ('item', 'variant', 'modifier')),
    CONSTRAINT item_dietary_claim_version_positive CHECK (effective_version > 0),
    CONSTRAINT item_dietary_claim_approval_is_reviewed CHECK (
        (review_state = 'approved') = (reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL))
);

CREATE UNIQUE INDEX item_dietary_claim_one_open
    ON safety.item_dietary_claim (tenant_id, subject, subject_id, claim_id)
    WHERE effective_to IS NULL;

-- ---------------------------------------------------------------------------
-- The pinned reference: recorded for audit, unreadable by the application
-- ---------------------------------------------------------------------------

CREATE TABLE safety.declaration_reference (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         uuid NOT NULL,
    outlet_id         uuid,
    context           safety.reference_context NOT NULL,
    context_id        uuid NOT NULL,
    declaration_id    uuid NOT NULL,
    effective_version integer NOT NULL,
    recorded_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT declaration_reference_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT declaration_reference_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT declaration_reference_declaration_fk FOREIGN KEY (declaration_id)
        REFERENCES safety.declaration (id) ON DELETE RESTRICT
);

COMMENT ON TABLE safety.declaration_reference IS
    'What was believed at publication, or when a line was added to a cart. It exists so a '
    'later dispute can establish what the kitchen had declared at that moment, and for no '
    'other purpose. The application role holds INSERT and nothing else: it cannot SELECT '
    'these rows, and no function it may execute returns them. That is deliberate and it '
    'is the point — a readable pinned value becomes a cache the first time a display path '
    'is under deadline, and a cached allergen is exactly the defect FR-SAF-005 names. '
    'Reading this table is an audit activity performed by an identity that is not serving '
    'a guest.';

CREATE INDEX declaration_reference_context_idx
    ON safety.declaration_reference (tenant_id, context, context_id);

-- ---------------------------------------------------------------------------
-- Live resolution (FR-SAF-005)
-- ---------------------------------------------------------------------------

CREATE FUNCTION safety.effective_allergens(
    p_tenant_id    uuid,
    p_item_id      uuid,
    p_variant_id   uuid DEFAULT NULL,
    p_modifier_ids uuid[] DEFAULT '{}'
) RETURNS TABLE (allergen_id uuid,
                 kitchen_code text,
                 declaration_class safety.declaration_class,
                 contributed_by menu.menu_entity[])
LANGUAGE sql STABLE
AS $$
    -- Every selection is resolved from the open declarations at the instant of the call.
    -- There is no materialized table to refresh and no cache to invalidate, so a
    -- correction to a modifier's declaration is visible to the next read with no step in
    -- between. That is the whole of FR-SAF-005's change detection: nothing to detect,
    -- because nothing was stored.
    WITH subjects (subject, subject_id) AS (
        SELECT 'item'::menu.menu_entity, p_item_id
        UNION ALL
        SELECT 'variant'::menu.menu_entity, p_variant_id WHERE p_variant_id IS NOT NULL
        UNION ALL
        SELECT 'modifier'::menu.menu_entity, m FROM unnest(p_modifier_ids) AS m
    ),
    open_rows AS (
        SELECT d.allergen_id, a.kitchen_code, d.declaration_class, d.subject
        FROM safety.declaration d
        JOIN subjects s ON s.subject = d.subject AND s.subject_id = d.subject_id
        JOIN safety.allergen a ON a.id = d.allergen_id
        WHERE d.tenant_id = p_tenant_id
          AND d.effective_to IS NULL
          AND d.review_state = 'approved'
    )
    SELECT o.allergen_id,
           o.kitchen_code,
           -- The strongest class wins, and only ever upward. A modifier that CONTAINS an
           -- allergen must not be softened to "may contain" because the base item was
           -- only uncertain; the guest is eating the modifier too. Ordering is explicit
           -- rather than relying on the enum's declaration order, which a later ALTER
           -- could reorder without anyone reading this function.
           (ARRAY_AGG(o.declaration_class ORDER BY
                CASE o.declaration_class
                    WHEN 'contains'      THEN 1
                    WHEN 'may_contain'   THEN 2
                    WHEN 'cross_contact' THEN 3
                END))[1],
           -- Which parts of the selection contributed. The distinction the three classes
           -- carry is preserved rather than collapsed: a guest can be told the allergen
           -- arrives with a modifier they chose and could drop.
           ARRAY_AGG(DISTINCT o.subject)
    FROM open_rows o
    GROUP BY o.allergen_id, o.kitchen_code;
$$;

COMMENT ON FUNCTION safety.effective_allergens IS
    'The allergens of a selection, computed live from the open declarations of the item, '
    'its variant and every chosen modifier (FR-SAF-005). Only approved declarations are '
    'returned; a draft has not been through human review and must not reach a guest.';

-- ---------------------------------------------------------------------------
-- Display: an icon is never returned without the words beside it (FR-SAF-002)
-- ---------------------------------------------------------------------------

CREATE FUNCTION safety.selection_safety(
    p_tenant_id    uuid,
    p_locale       menu.customer_locale,
    p_item_id      uuid,
    p_variant_id   uuid DEFAULT NULL,
    p_modifier_ids uuid[] DEFAULT '{}'
) RETURNS TABLE (kitchen_code text,
                 declaration_class safety.declaration_class,
                 written_warning text,
                 icon_key text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, safety, menu, public
AS $$
DECLARE
    v_missing text;
BEGIN
    -- Refuse before returning anything, rather than returning the rows that do have text
    -- and quietly dropping the one that does not. A guest shown four of five allergens
    -- has been told something false by omission.
    SELECT string_agg(e.kitchen_code, ', ' ORDER BY e.kitchen_code) INTO v_missing
    FROM safety.effective_allergens(p_tenant_id, p_item_id, p_variant_id, p_modifier_ids) e
    WHERE NOT EXISTS (
        SELECT 1 FROM menu.translation t
        WHERE t.tenant_id = p_tenant_id
          AND t.entity = 'allergen' AND t.entity_id = e.allergen_id
          AND t.field_name = 'customer_warning_text'
          AND t.locale = p_locale AND t.state = 'approved'
          AND btrim(t.translated_text) <> '');

    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION
            'WRITTEN_WARNING_ABSENT: no approved % warning text for %; an icon may '
            'supplement a written warning but never replace it',
            p_locale, v_missing
            USING ERRCODE = 'HS422';
    END IF;

    RETURN QUERY
    SELECT e.kitchen_code,
           e.declaration_class,
           t.translated_text,
           -- The icon travels in the same row as the words, and this is the only
           -- customer-facing path that reads icon_key at all. The application role has no
           -- SELECT privilege on that column, so "convey the icon alone" is not a
           -- discipline anyone has to remember — it is a query that does not compile.
           a.icon_key
    FROM safety.effective_allergens(p_tenant_id, p_item_id, p_variant_id, p_modifier_ids) e
    JOIN safety.allergen a ON a.id = e.allergen_id
    JOIN menu.translation t
      ON t.tenant_id = p_tenant_id AND t.entity = 'allergen' AND t.entity_id = e.allergen_id
     AND t.field_name = 'customer_warning_text'
     AND t.locale = p_locale AND t.state = 'approved';
END;
$$;

COMMENT ON FUNCTION safety.selection_safety IS
    'What a guest is shown about a selection, in their locale (FR-SAF-002). Resolves live '
    'and refuses outright when any allergen in the selection has no approved written '
    'warning in that locale, so there is no path by which an icon reaches a guest without '
    'the words. Reads nothing from safety.declaration_reference.';

CREATE FUNCTION safety.allergen_for_management(
    p_tenant_id uuid,
    p_locale    menu.customer_locale
) RETURNS TABLE (allergen_id uuid,
                 kitchen_code text,
                 icon_key text,
                 written_warning text,
                 warning_state text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, safety, menu, public
AS $$
    -- The staff path. It also pairs icon with words, because a manager looking at a
    -- catalog screen is exactly who needs to see that an icon has been set and its
    -- warning has not. Rather than refusing, it names the gap.
    SELECT a.id, a.kitchen_code, a.icon_key, t.translated_text,
           coalesce(t.state::text, 'absent')
    FROM safety.allergen a
    LEFT JOIN menu.translation t
           ON t.tenant_id = a.tenant_id AND t.entity = 'allergen' AND t.entity_id = a.id
          AND t.field_name = 'customer_warning_text' AND t.locale = p_locale
    WHERE a.tenant_id = p_tenant_id AND a.status = 'active';
$$;

-- ---------------------------------------------------------------------------
-- Safety text joins the fields that block publication
-- ---------------------------------------------------------------------------
--
-- Both are safety_critical, so menu.enforce_translation_review() already refuses to
-- approve either from a machine draft without a named human, and
-- menu.missing_required_translations() already blocks publication while one is absent.
-- No new mechanism; the same one, told about two more fields.

INSERT INTO menu.translatable_field (entity, field_name, required_for_publication, safety_critical)
VALUES ('allergen',      'customer_warning_text', true, true),
       ('dietary_claim', 'customer_label',        true, true);

-- ===========================================================================
-- Service: tables, QR, occupancy, guests, carts, ownership
-- ===========================================================================

CREATE TYPE service.occupancy_state AS ENUM ('open', 'closed');
CREATE TYPE service.opening_source AS ENUM ('qr_scan', 'staff', 'host_stand');
CREATE TYPE service.cart_kind AS ENUM ('personal', 'shared');

-- Deliberately no 'submitted'. Submission creates an order, and orders are M3. The
-- boundary is expressed as a state that does not exist rather than a state this slice
-- declines to set, because the second kind is one line of code away from being crossed.
CREATE TYPE service.cart_state AS ENUM ('open', 'abandoned', 'expired');

CREATE TYPE service.verification_method AS ENUM
    ('staff_confirmation', 'table_code', 'host_approval');

CREATE TYPE service.transfer_state AS ENUM
    ('proposed', 'acknowledged', 'supervisor_reassigned', 'declined');

CREATE TYPE service.concern_source AS ENUM ('guest', 'waiter');

-- ---------------------------------------------------------------------------
-- Table profile — service attributes of a node that is already a dining table
-- ---------------------------------------------------------------------------

CREATE TABLE service.table_profile (
    tenant_id       uuid NOT NULL,
    table_node_id   uuid NOT NULL,

    -- Fixed by CHECK and carried into the foreign key, so the reference can only ever
    -- resolve to a node of kind 'dining_table'. A device or a preparation station cannot
    -- be given a table profile even by a direct write.
    node_kind       org.node_kind NOT NULL DEFAULT 'dining_table',

    outlet_id       uuid NOT NULL,
    service_area_id uuid,
    seat_count      integer,
    row_version     bigint NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (table_node_id),
    CONSTRAINT table_profile_tenant_id_unique UNIQUE (tenant_id, table_node_id),
    CONSTRAINT table_profile_node_fk FOREIGN KEY (tenant_id, table_node_id, node_kind)
        REFERENCES org.org_node (tenant_id, id, kind) ON DELETE RESTRICT,
    CONSTRAINT table_profile_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT table_profile_area_fk FOREIGN KEY (tenant_id, service_area_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT table_profile_is_a_table CHECK (node_kind = 'dining_table'),
    CONSTRAINT table_profile_seats_positive CHECK (seat_count IS NULL OR seat_count > 0),
    CONSTRAINT table_profile_row_version_positive CHECK (row_version > 0)
);

-- ---------------------------------------------------------------------------
-- QR tokens (FR-TAB-001, FR-TAB-002, FR-TAB-010)
-- ---------------------------------------------------------------------------

CREATE TABLE service.table_qr_token (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          uuid NOT NULL,
    outlet_id          uuid NOT NULL,
    table_node_id      uuid NOT NULL,

    -- The printed token is never stored. What is stored is its SHA-256, which is what
    -- resolution matches against. A dump of this table yields no working QR code, and
    -- the plaintext exists only in the return value of service.issue_table_qr() and on
    -- the placard somebody printed from it (FR-SEC-007).
    token_hash         bytea NOT NULL,

    version            integer NOT NULL,
    issued_at          timestamptz NOT NULL DEFAULT now(),
    issued_by_user_id  uuid NOT NULL,
    revoked_at         timestamptz,
    revoked_by_user_id uuid,
    revoke_reason_id   uuid,

    CONSTRAINT qr_token_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT qr_token_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT qr_token_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT qr_token_table_fk FOREIGN KEY (tenant_id, table_node_id)
        REFERENCES service.table_profile (tenant_id, table_node_id) ON DELETE RESTRICT,
    CONSTRAINT qr_token_issuer_fk FOREIGN KEY (tenant_id, issued_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT qr_token_revoker_fk FOREIGN KEY (tenant_id, revoked_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT qr_token_revoke_reason_fk FOREIGN KEY (tenant_id, revoke_reason_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT qr_token_hash_is_sha256 CHECK (octet_length(token_hash) = 32),
    CONSTRAINT qr_token_hash_unique UNIQUE (token_hash),
    CONSTRAINT qr_token_version_positive CHECK (version > 0),
    CONSTRAINT qr_token_version_unique UNIQUE (tenant_id, table_node_id, version),

    -- Revocation names who and why, so a rotation is answerable.
    CONSTRAINT qr_token_revocation_is_attributed CHECK (
        (revoked_at IS NULL) = (revoked_by_user_id IS NULL))
);

COMMENT ON TABLE service.table_qr_token IS
    'The signed reference a QR encodes (FR-TAB-001). The reference carries no internal '
    'identifier: it is 244 bits drawn from the server CSPRNG, so it is not sequential, '
    'not guessable from a neighbouring table''s code, and does not decode to a primary '
    'key. '
    'Only its hash is stored. Tokens rotate by issuing a new version and revoking the '
    'old, and every version printed is recorded so staff can tell which placard is '
    'current (FR-TAB-002).';

-- One live token per table. A second active token would mean two placards resolving to
-- the same table with no way to revoke just one of them.
CREATE UNIQUE INDEX qr_token_one_active_per_table
    ON service.table_qr_token (tenant_id, table_node_id)
    WHERE revoked_at IS NULL;

CREATE TABLE service.qr_placard (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    outlet_id         uuid NOT NULL,
    token_id          uuid NOT NULL,
    version           integer NOT NULL,
    printed_at        timestamptz NOT NULL DEFAULT now(),
    printed_by_user_id uuid NOT NULL,
    note              text,

    CONSTRAINT qr_placard_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT qr_placard_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT qr_placard_token_fk FOREIGN KEY (tenant_id, token_id)
        REFERENCES service.table_qr_token (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT qr_placard_printer_fk FOREIGN KEY (tenant_id, printed_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT
);

COMMENT ON TABLE service.qr_placard IS
    'Printable version history (FR-TAB-002): which version of a table''s code was put on a '
    'placard, when and by whom. It records that a placard was produced, never the code on '
    'it. Named for the placard rather than the printing because M1-B guards against any '
    'table whose name reads as print-agent or edge behaviour, and it was right to: that '
    'is M5a''s, and this is a history of physical signs.';

-- ---------------------------------------------------------------------------
-- Occupancy (FR-TAB-003, FR-TAB-004)
-- ---------------------------------------------------------------------------

CREATE TABLE service.table_session (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          uuid NOT NULL,
    outlet_id          uuid NOT NULL,
    table_node_id      uuid NOT NULL,

    -- Monotonic per table. This is what makes "a later occupancy" a fact rather than a
    -- guess from timestamps: the party that sat down after you has a higher number, and
    -- a code scanned during yours carries the number it was scanned under.
    occupancy_number   integer NOT NULL,

    state              service.occupancy_state NOT NULL DEFAULT 'open',
    opening_source     service.opening_source NOT NULL,
    host_staff_user_id uuid,
    opened_at          timestamptz NOT NULL DEFAULT now(),
    closed_at          timestamptz,

    CONSTRAINT table_session_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT table_session_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT table_session_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT table_session_table_fk FOREIGN KEY (tenant_id, table_node_id)
        REFERENCES service.table_profile (tenant_id, table_node_id) ON DELETE RESTRICT,
    CONSTRAINT table_session_host_fk FOREIGN KEY (tenant_id, host_staff_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT table_session_occupancy_positive CHECK (occupancy_number > 0),
    CONSTRAINT table_session_occupancy_unique UNIQUE (tenant_id, table_node_id, occupancy_number),
    CONSTRAINT table_session_closure_consistent CHECK (
        (state = 'open' AND closed_at IS NULL) OR (state = 'closed' AND closed_at IS NOT NULL)),
    -- A session opened at the host stand names the host who opened it.
    CONSTRAINT table_session_host_named_when_staff_opened CHECK (
        opening_source = 'qr_scan' OR host_staff_user_id IS NOT NULL)
);

CREATE UNIQUE INDEX table_session_one_open_per_table
    ON service.table_session (tenant_id, table_node_id)
    WHERE state = 'open';

-- ---------------------------------------------------------------------------
-- Guest sessions (FR-AUTH-003, FR-CST-002)
-- ---------------------------------------------------------------------------

CREATE TABLE service.guest_session (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL,
    outlet_id        uuid NOT NULL,

    -- Everything a guest session may hold. There is no phone column, no email column, no
    -- reference to identity.user_account and no registration step, because FR-AUTH-003
    -- requires ordering to work without any of them. A nickname is what other people at
    -- the table see; it is optional and it is not an identifier.
    display_nickname text,
    locale           menu.customer_locale NOT NULL DEFAULT 'en',

    created_at       timestamptz NOT NULL DEFAULT now(),
    expires_at       timestamptz NOT NULL,
    anonymized_at    timestamptz,

    CONSTRAINT guest_session_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT guest_session_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT guest_session_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT guest_session_expiry_after_creation CHECK (expires_at > created_at),
    -- An anonymized session has had its nickname removed, not merely been flagged.
    CONSTRAINT guest_session_anonymization_is_real CHECK (
        anonymized_at IS NULL OR display_nickname IS NULL)
);

COMMENT ON TABLE service.guest_session IS
    'A privacy-minimized guest session for QR ordering (FR-AUTH-003): no phone, no email, '
    'no registration, no link to a user account. It expires on a date it carries, and '
    'config.apply_retention anonymizes it under an "anonymize" policy rather than '
    'deleting it, because the allergy concerns raised at a table outlive the identity '
    'that raised them (FR-CST-002).';

CREATE TABLE service.session_participant (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL,
    outlet_id        uuid NOT NULL,
    table_session_id uuid NOT NULL,
    guest_session_id uuid NOT NULL,
    joined_at        timestamptz NOT NULL DEFAULT now(),
    left_at          timestamptz,

    -- Configured visibility (FR-TAB-004): whether this device's basket is visible to the
    -- rest of the table.
    shares_basket    boolean NOT NULL DEFAULT true,

    CONSTRAINT participant_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT participant_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT participant_session_fk FOREIGN KEY (tenant_id, table_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT participant_guest_fk FOREIGN KEY (tenant_id, guest_session_id)
        REFERENCES service.guest_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT participant_unique UNIQUE (table_session_id, guest_session_id)
);

-- ---------------------------------------------------------------------------
-- Scanning, and the stale-QR guarantee (FR-TAB-010)
-- ---------------------------------------------------------------------------

CREATE TABLE service.qr_scan (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL,
    outlet_id           uuid NOT NULL,
    token_id            uuid NOT NULL,
    guest_session_id    uuid NOT NULL,
    scanned_at          timestamptz NOT NULL DEFAULT now(),

    -- The occupancy in force when the code was scanned. A photograph taken during that
    -- occupancy carries this number with it forever, which is how a later join is
    -- recognised as a later join rather than merely an old one.
    occupancy_at_scan   integer,

    CONSTRAINT qr_scan_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT qr_scan_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT qr_scan_token_fk FOREIGN KEY (tenant_id, token_id)
        REFERENCES service.table_qr_token (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT qr_scan_guest_fk FOREIGN KEY (tenant_id, guest_session_id)
        REFERENCES service.guest_session (tenant_id, id) ON DELETE RESTRICT
);

-- The tenant chooses HOW a stale scan is verified. It cannot choose whether.
--
-- There is no enabled flag, no exemption list and no threshold, and the set of accepted
-- methods cannot be empty — an empty set would be a disable switch wearing a different
-- name. A tenant with no row here does not get an unverified join; it gets a refusal,
-- because absent configuration must fail closed and not open.
CREATE TABLE service.verification_policy (
    tenant_id        uuid PRIMARY KEY,
    accepted_methods service.verification_method[] NOT NULL,
    updated_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT verification_policy_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT verification_policy_at_least_one_method CHECK (
        cardinality(accepted_methods) >= 1)
);

COMMENT ON TABLE service.verification_policy IS
    'Which verification methods a tenant accepts when a scan from an earlier occupancy is '
    'presented against a later one (FR-TAB-010). Method only. Nothing in this schema can '
    'express "do not verify": the array cannot be empty, there is no boolean beside it, '
    'and service.join_table_session() refuses when no policy row exists at all. The '
    'guarantee is an invariant rather than a default, for the same reason row level '
    'security is not a tenant preference.';

-- ---------------------------------------------------------------------------
-- Table ownership and acknowledged transfer (FR-TAB-006)
-- ---------------------------------------------------------------------------

CREATE TABLE service.table_ownership (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              uuid NOT NULL,
    outlet_id              uuid NOT NULL,
    table_session_id       uuid NOT NULL,
    primary_waiter_user_id uuid NOT NULL,
    section_code           text,
    assigned_at            timestamptz NOT NULL DEFAULT now(),
    assigned_by_user_id    uuid NOT NULL,
    effective_to           timestamptz,

    CONSTRAINT ownership_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT ownership_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT ownership_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ownership_session_fk FOREIGN KEY (tenant_id, table_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ownership_waiter_fk FOREIGN KEY (tenant_id, primary_waiter_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ownership_assigner_fk FOREIGN KEY (tenant_id, assigned_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT
);

COMMENT ON TABLE service.table_ownership IS
    'Who is answerable for a table, right now and historically (FR-TAB-006). Rows are '
    'superseded, never edited: a trigger refuses any UPDATE that changes the waiter or '
    'the section, so ownership can only move through service.transfer_ownership(), which '
    'requires an acknowledgement or a named supervisor. A reassignment nobody '
    'acknowledged is not auditable, and an unauditable handover is the requirement '
    'unmet rather than a lesser form of it.';

CREATE UNIQUE INDEX ownership_one_current_per_session
    ON service.table_ownership (tenant_id, table_session_id)
    WHERE effective_to IS NULL;

CREATE TABLE service.ownership_transfer (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             uuid NOT NULL,
    outlet_id             uuid NOT NULL,
    table_session_id      uuid NOT NULL,
    from_user_id          uuid NOT NULL,
    to_user_id            uuid NOT NULL,
    state                 service.transfer_state NOT NULL DEFAULT 'proposed',
    reason_code_id        uuid,
    proposed_at           timestamptz NOT NULL DEFAULT now(),
    proposed_by_user_id   uuid NOT NULL,
    acknowledged_at       timestamptz,
    acknowledged_by_user_id uuid,
    supervisor_user_id    uuid,

    CONSTRAINT transfer_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT transfer_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT transfer_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT transfer_session_fk FOREIGN KEY (tenant_id, table_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT transfer_from_fk FOREIGN KEY (tenant_id, from_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT transfer_to_fk FOREIGN KEY (tenant_id, to_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT transfer_proposer_fk FOREIGN KEY (tenant_id, proposed_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT transfer_acknowledger_fk FOREIGN KEY (tenant_id, acknowledged_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT transfer_supervisor_fk FOREIGN KEY (tenant_id, supervisor_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT transfer_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT transfer_not_to_self CHECK (from_user_id <> to_user_id),

    -- An acknowledged transfer names who acknowledged it and when, and the acknowledger
    -- is the waiter taking the table on. Anyone else acknowledging on their behalf is
    -- the silent reassignment this requirement exists to prevent.
    CONSTRAINT transfer_acknowledgement_is_by_the_receiver CHECK (
        (state = 'acknowledged') =
        (acknowledged_at IS NOT NULL AND acknowledged_by_user_id IS NOT NULL)),
    CONSTRAINT transfer_acknowledger_is_recipient CHECK (
        acknowledged_by_user_id IS NULL OR acknowledged_by_user_id = to_user_id),

    -- The one route that does not need the receiver's acknowledgement names a supervisor
    -- instead, so the handover is still attributable to a person.
    CONSTRAINT transfer_supervisor_named_when_reassigned CHECK (
        (state = 'supervisor_reassigned') = (supervisor_user_id IS NOT NULL))
);

-- ---------------------------------------------------------------------------
-- Carts, strictly before submission (FR-TAB-005)
-- ---------------------------------------------------------------------------

CREATE TABLE service.cart (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              uuid NOT NULL,
    outlet_id              uuid NOT NULL,
    table_session_id       uuid NOT NULL,
    kind                   service.cart_kind NOT NULL,
    owner_guest_session_id uuid,
    state                  service.cart_state NOT NULL DEFAULT 'open',
    created_at             timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT cart_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT cart_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT cart_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cart_session_fk FOREIGN KEY (tenant_id, table_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cart_owner_fk FOREIGN KEY (tenant_id, owner_guest_session_id)
        REFERENCES service.guest_session (tenant_id, id) ON DELETE RESTRICT,
    -- A personal basket belongs to exactly one guest; a shared one belongs to the table.
    CONSTRAINT cart_ownership_matches_kind CHECK (
        (kind = 'personal') = (owner_guest_session_id IS NOT NULL))
);

CREATE TABLE service.cart_line (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL,
    outlet_id        uuid NOT NULL,
    cart_id          uuid NOT NULL,
    item_id          uuid NOT NULL,
    variant_id       uuid NOT NULL,
    quantity         integer NOT NULL DEFAULT 1,

    -- Priced at the moment it was added, in the M1-C exact types. This is a price, so it
    -- is pinned; the allergens of the same line are not, and that asymmetry is the
    -- decision recorded at the head of this file.
    currency_code    char(3) NOT NULL,
    unit_amount_minor money.amount_minor NOT NULL,

    added_at         timestamptz NOT NULL DEFAULT now(),
    added_by_guest_session_id uuid,

    CONSTRAINT cart_line_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT cart_line_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_cart_fk FOREIGN KEY (tenant_id, cart_id)
        REFERENCES service.cart (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_currency_fk FOREIGN KEY (currency_code)
        REFERENCES money.currency (code) ON DELETE RESTRICT,
    CONSTRAINT cart_line_item_fk FOREIGN KEY (item_id)
        REFERENCES menu.sellable_item (id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_variant_fk FOREIGN KEY (variant_id)
        REFERENCES menu.item_variant (id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_guest_fk FOREIGN KEY (tenant_id, added_by_guest_session_id)
        REFERENCES service.guest_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_quantity_positive CHECK (quantity > 0)
);

CREATE TABLE service.cart_line_modifier (
    cart_line_id uuid NOT NULL,
    tenant_id    uuid NOT NULL,
    outlet_id    uuid NOT NULL,
    modifier_id  uuid NOT NULL,

    PRIMARY KEY (cart_line_id, modifier_id),
    CONSTRAINT cart_line_modifier_line_fk FOREIGN KEY (tenant_id, cart_line_id)
        REFERENCES service.cart_line (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_modifier_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_modifier_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_modifier_modifier_fk FOREIGN KEY (modifier_id)
        REFERENCES menu.modifier (id) ON DELETE RESTRICT
);

-- Moving an item between baskets before submission (FR-TAB-005). Recorded rather than
-- performed silently, because "who put this on my bill" is a question that gets asked.
CREATE TABLE service.cart_line_transfer (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid NOT NULL,
    cart_line_id   uuid NOT NULL,
    from_cart_id   uuid NOT NULL,
    to_cart_id     uuid NOT NULL,
    moved_at       timestamptz NOT NULL DEFAULT now(),
    moved_by_guest_session_id uuid,

    CONSTRAINT cart_line_transfer_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_transfer_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_transfer_line_fk FOREIGN KEY (tenant_id, cart_line_id)
        REFERENCES service.cart_line (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_transfer_from_fk FOREIGN KEY (tenant_id, from_cart_id)
        REFERENCES service.cart (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_transfer_to_fk FOREIGN KEY (tenant_id, to_cart_id)
        REFERENCES service.cart (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT cart_line_transfer_moves CHECK (from_cart_id <> to_cart_id)
);

-- ---------------------------------------------------------------------------
-- Allergy concern raised at a table (FR-SAF-003)
-- ---------------------------------------------------------------------------

-- Tenant-approved wording (FR-SAF-009). The sentence a guest is shown is not composed at
-- the keyboard by whoever is on shift; it is drawn from wording the tenant approved, in
-- the guest's locale.
CREATE TABLE safety.approved_wording (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL,
    outlet_id   uuid,
    purpose     text NOT NULL,
    locale      menu.customer_locale NOT NULL,
    wording     text NOT NULL,
    approved_by_user_id uuid NOT NULL,
    approved_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT approved_wording_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT approved_wording_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT approved_wording_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT approved_wording_approver_fk FOREIGN KEY (tenant_id, approved_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT approved_wording_not_blank CHECK (btrim(wording) <> ''),
    CONSTRAINT approved_wording_purpose_not_blank CHECK (btrim(purpose) <> ''),
    CONSTRAINT approved_wording_unique UNIQUE (tenant_id, purpose, locale)
);

CREATE TABLE safety.allergy_concern (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL,
    outlet_id           uuid NOT NULL,
    table_session_id    uuid NOT NULL,
    raised_by           service.concern_source NOT NULL,
    guest_session_id    uuid,
    raised_by_user_id   uuid,
    allergen_id         uuid,
    note                text,

    -- The acknowledgement is not a boolean. What the guest was told is stored verbatim,
    -- drawn from tenant-approved wording, so a later question about what was promised has
    -- an answer rather than a flag.
    acknowledgement_wording_id uuid NOT NULL,
    acknowledgement_text text NOT NULL,
    acknowledged_at     timestamptz NOT NULL DEFAULT now(),
    acknowledged_by_user_id uuid,

    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT allergy_concern_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT allergy_concern_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT allergy_concern_session_fk FOREIGN KEY (tenant_id, table_session_id)
        REFERENCES service.table_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT allergy_concern_guest_fk FOREIGN KEY (tenant_id, guest_session_id)
        REFERENCES service.guest_session (tenant_id, id) ON DELETE SET NULL,
    CONSTRAINT allergy_concern_user_fk FOREIGN KEY (tenant_id, raised_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT allergy_concern_allergen_fk FOREIGN KEY (tenant_id, allergen_id)
        REFERENCES safety.allergen (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT allergy_concern_wording_fk FOREIGN KEY (tenant_id, acknowledgement_wording_id)
        REFERENCES safety.approved_wording (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT allergy_concern_text_not_blank CHECK (btrim(acknowledgement_text) <> ''),
    -- A concern raised by a waiter names the waiter; one raised by a guest names the
    -- guest session. Neither may be anonymous at the moment it is raised.
    CONSTRAINT allergy_concern_attributed CHECK (
        (raised_by = 'waiter' AND raised_by_user_id IS NOT NULL)
     OR (raised_by = 'guest'  AND guest_session_id IS NOT NULL))
);

COMMENT ON TABLE safety.allergy_concern IS
    'An allergy concern flagged for a table by a guest or a waiter (FR-SAF-003), with the '
    'exact acknowledgement wording the guest was shown. The order-level flag and the '
    'waiter workflow around it arrive at M3; the table-level record is this. '
    'guest_session_id is ON DELETE SET NULL so anonymizing a guest severs the identity '
    'and leaves the concern, which is operational evidence rather than personal data.';

-- ===========================================================================
-- Behaviour
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- Issuing and rotating a table's QR reference
-- ---------------------------------------------------------------------------

CREATE FUNCTION service.issue_table_qr(
    p_tenant_id     uuid,
    p_table_node_id uuid,
    p_issued_by     uuid,
    p_reason_id     uuid DEFAULT NULL
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_token   text;
    v_outlet  uuid;
    v_version integer;
BEGIN
    SELECT outlet_id INTO v_outlet
    FROM service.table_profile
    WHERE tenant_id = p_tenant_id AND table_node_id = p_table_node_id;

    IF v_outlet IS NULL THEN
        RAISE EXCEPTION 'TABLE_UNKNOWN: no table profile for % in this scope', p_table_node_id
            USING ERRCODE = 'HS404';
    END IF;

    -- Two draws from the server CSPRNG, 244 bits of randomness in total. Deliberately
    -- built from randomness alone: nothing about the table, the outlet or the tenant
    -- enters the value, so there is nothing in a code to decode and nothing to increment
    -- to reach the table next to it. pgcrypto is not installed anywhere in this stack, so
    -- gen_random_uuid() is the strong source that is actually present rather than one
    -- this migration would have to add.
    v_token := replace(gen_random_uuid()::text, '-', '')
            || replace(gen_random_uuid()::text, '-', '');

    -- Rotation: the previous code stops resolving the moment the new one is issued.
    UPDATE service.table_qr_token
       SET revoked_at = now(), revoked_by_user_id = p_issued_by, revoke_reason_id = p_reason_id
     WHERE tenant_id = p_tenant_id AND table_node_id = p_table_node_id AND revoked_at IS NULL;

    SELECT coalesce(max(version), 0) + 1 INTO v_version
    FROM service.table_qr_token
    WHERE tenant_id = p_tenant_id AND table_node_id = p_table_node_id;

    INSERT INTO service.table_qr_token
        (tenant_id, outlet_id, table_node_id, token_hash, version, issued_by_user_id)
    VALUES (p_tenant_id, v_outlet, p_table_node_id,
            sha256(convert_to(v_token, 'UTF8')), v_version, p_issued_by);

    -- Returned once, to be printed. The row keeps only the hash, so this value cannot be
    -- recovered from the database afterwards (FR-SEC-007) — rotating is how a lost code
    -- is replaced, not looking the old one up.
    RETURN v_token;
END;
$$;

-- ---------------------------------------------------------------------------
-- Scanning a code
-- ---------------------------------------------------------------------------

CREATE FUNCTION service.record_qr_scan(
    p_tenant_id        uuid,
    p_token            text,
    p_guest_session_id uuid
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_token   record;
    v_scan_id uuid;
    v_occupancy integer;
BEGIN
    SELECT t.* INTO v_token
    FROM service.table_qr_token t
    WHERE t.token_hash = sha256(convert_to(p_token, 'UTF8'));

    -- Row level security has already removed any token outside this caller's tenant and
    -- outlet, so a code belonging to another tenant is not "refused" here — it was never
    -- visible. The explicit tenant test below is the second guard, for the same reason
    -- M1-C guards retention twice.
    IF v_token.id IS NULL OR v_token.tenant_id <> p_tenant_id THEN
        RAISE EXCEPTION 'FOREIGN_SESSION_ACCEPTED_PREVENTED: this code does not resolve '
                        'in the current scope'
            USING ERRCODE = 'HS403';
    END IF;

    IF v_token.revoked_at IS NOT NULL THEN
        RAISE EXCEPTION 'QR_TOKEN_REVOKED: version % of this table''s code was withdrawn',
            v_token.version USING ERRCODE = 'HS403';
    END IF;

    SELECT occupancy_number INTO v_occupancy
    FROM service.table_session
    WHERE tenant_id = p_tenant_id AND table_node_id = v_token.table_node_id AND state = 'open';

    INSERT INTO service.qr_scan
        (tenant_id, outlet_id, token_id, guest_session_id, occupancy_at_scan)
    VALUES (p_tenant_id, v_token.outlet_id, v_token.id, p_guest_session_id, v_occupancy)
    RETURNING id INTO v_scan_id;

    RETURN v_scan_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- Joining a session, with the stale-QR guarantee (FR-TAB-010, FR-TAB-004)
-- ---------------------------------------------------------------------------

CREATE FUNCTION service.join_table_session(
    p_tenant_id    uuid,
    p_scan_id      uuid,
    p_verification service.verification_method DEFAULT NULL,
    p_evidence     text DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_scan     record;
    v_token    record;
    v_session  record;
    v_accepted service.verification_method[];
BEGIN
    SELECT * INTO v_scan FROM service.qr_scan WHERE id = p_scan_id AND tenant_id = p_tenant_id;
    IF v_scan.id IS NULL THEN
        RAISE EXCEPTION 'SCAN_UNKNOWN: no scan % in this scope', p_scan_id
            USING ERRCODE = 'HS404';
    END IF;

    SELECT * INTO v_token FROM service.table_qr_token
     WHERE id = v_scan.token_id AND tenant_id = p_tenant_id;

    -- A code withdrawn between the scan and the join must not still let anyone in.
    IF v_token.id IS NULL OR v_token.revoked_at IS NOT NULL THEN
        RAISE EXCEPTION 'QR_TOKEN_REVOKED: this code no longer resolves'
            USING ERRCODE = 'HS403';
    END IF;

    SELECT * INTO v_session FROM service.table_session
     WHERE tenant_id = p_tenant_id AND table_node_id = v_token.table_node_id AND state = 'open';

    IF v_session.id IS NULL THEN
        RAISE EXCEPTION 'NO_OPEN_OCCUPANCY: this table has no open session to join'
            USING ERRCODE = 'HS409';
    END IF;

    -- ===== The stale-QR guarantee =====
    --
    -- The test is on the OCCUPANCY, not on the age of the token. A code photographed
    -- during the previous party's meal is not old — the placard is the same placard, and
    -- it may have been printed that morning. What makes the join wrong is that the scan
    -- was taken under a different occupancy than the one now open, and admitting it would
    -- let a stranger read this table's session and, at M4, attach orders to its bill.
    --
    -- v_scan.occupancy_at_scan IS NULL means the table was empty when the code was
    -- scanned, and a session has opened since. That is the same situation and is treated
    -- the same way; a null is not a licence.
    IF v_scan.occupancy_at_scan IS DISTINCT FROM v_session.occupancy_number THEN

        SELECT accepted_methods INTO v_accepted
        FROM service.verification_policy WHERE tenant_id = p_tenant_id;

        -- Absent configuration fails closed. A tenant that has configured nothing does
        -- not thereby get unverified joins; it gets a refusal until somebody chooses a
        -- method. There is no third branch here in which the join simply proceeds.
        IF v_accepted IS NULL THEN
            RAISE EXCEPTION
                'STALE_QR_VERIFICATION_REQUIRED: scan was taken under occupancy %, the '
                'open occupancy is %, and this tenant has configured no verification '
                'method', v_scan.occupancy_at_scan, v_session.occupancy_number
                USING ERRCODE = 'HS403';
        END IF;

        IF p_verification IS NULL THEN
            RAISE EXCEPTION
                'STALE_QR_VERIFICATION_REQUIRED: scan was taken under occupancy %, the '
                'open occupancy is %; one of % is required',
                v_scan.occupancy_at_scan, v_session.occupancy_number, v_accepted
                USING ERRCODE = 'HS403';
        END IF;

        IF NOT (p_verification = ANY (v_accepted)) THEN
            RAISE EXCEPTION
                'STALE_QR_VERIFICATION_REQUIRED: % is not a method this tenant accepts; '
                'one of % is required', p_verification, v_accepted
                USING ERRCODE = 'HS403';
        END IF;

        IF p_evidence IS NULL OR btrim(p_evidence) = '' THEN
            RAISE EXCEPTION
                'STALE_QR_VERIFICATION_REQUIRED: % was named but no evidence of it was '
                'recorded', p_verification
                USING ERRCODE = 'HS403';
        END IF;
    END IF;

    INSERT INTO service.session_participant
        (tenant_id, outlet_id, table_session_id, guest_session_id)
    VALUES (p_tenant_id, v_session.outlet_id, v_session.id, v_scan.guest_session_id)
    ON CONFLICT (table_session_id, guest_session_id) DO NOTHING;

    RETURN v_session.id;
END;
$$;

COMMENT ON FUNCTION service.join_table_session IS
    'Joins a guest to the occupancy their code resolves to (FR-TAB-004), refusing when '
    'the scan was taken under a different occupancy unless one of the tenant''s '
    'configured verification methods is supplied with evidence (FR-TAB-010). Every branch '
    'of the occupancy mismatch ends in a refusal; there is no configuration, including '
    'the absence of configuration, under which it admits silently.';

-- ---------------------------------------------------------------------------
-- Ownership moves only through an acknowledged transfer (FR-TAB-006)
-- ---------------------------------------------------------------------------

CREATE FUNCTION service.refuse_silent_ownership_change() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    -- Closing a row is how supersession works and is allowed. Changing who owns the
    -- table in place is not: it would move a table between waiters leaving no proposal,
    -- no acknowledgement and no supervisor, which is precisely the handover FR-TAB-006
    -- exists to make auditable.
    IF NEW.primary_waiter_user_id IS DISTINCT FROM OLD.primary_waiter_user_id
       OR NEW.section_code IS DISTINCT FROM OLD.section_code THEN
        RAISE EXCEPTION
            'OWNERSHIP_TRANSFERRED_SILENTLY: table ownership cannot be edited in place; '
            'use service.transfer_ownership(), which requires an acknowledgement from '
            'the waiter taking the table on, or a named supervisor'
            USING ERRCODE = 'HS403';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER table_ownership_no_silent_change
    BEFORE UPDATE ON service.table_ownership
    FOR EACH ROW EXECUTE FUNCTION service.refuse_silent_ownership_change();

CREATE FUNCTION service.transfer_ownership(
    p_tenant_id  uuid,
    p_transfer_id uuid
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    t         record;
    v_current record;
    v_new     uuid;
BEGIN
    SELECT * INTO t FROM service.ownership_transfer
     WHERE id = p_transfer_id AND tenant_id = p_tenant_id;
    IF t.id IS NULL THEN
        RAISE EXCEPTION 'TRANSFER_UNKNOWN: no transfer % in this scope', p_transfer_id
            USING ERRCODE = 'HS404';
    END IF;

    -- The whole of the requirement is in this one test. A proposal that the waiter taking the
    -- waiter has not acknowledged, and that no supervisor has taken responsibility for,
    -- does not move the table.
    IF t.state NOT IN ('acknowledged', 'supervisor_reassigned') THEN
        RAISE EXCEPTION
            'OWNERSHIP_TRANSFERRED_SILENTLY: transfer % is in state % — a handover moves '
            'the table only once the waiter taking it on acknowledges, or a supervisor '
            'reassigns it by name', p_transfer_id, t.state
            USING ERRCODE = 'HS403';
    END IF;

    SELECT * INTO v_current FROM service.table_ownership
     WHERE tenant_id = p_tenant_id AND table_session_id = t.table_session_id
       AND effective_to IS NULL;

    IF v_current.id IS NOT NULL THEN
        UPDATE service.table_ownership SET effective_to = now() WHERE id = v_current.id;
    END IF;

    INSERT INTO service.table_ownership
        (tenant_id, outlet_id, table_session_id, primary_waiter_user_id, section_code,
         assigned_by_user_id)
    VALUES (p_tenant_id, t.outlet_id, t.table_session_id, t.to_user_id,
            v_current.section_code,
            coalesce(t.supervisor_user_id, t.acknowledged_by_user_id))
    RETURNING id INTO v_new;

    RETURN v_new;
END;
$$;

-- ---------------------------------------------------------------------------
-- Publication blocks on safety (FR-SAF-007)
-- ---------------------------------------------------------------------------

CREATE FUNCTION safety.missing_safety_translations(p_menu_id uuid)
RETURNS TABLE (entity menu.menu_entity, entity_id uuid, field_name text,
               locale menu.customer_locale)
LANGUAGE sql STABLE
AS $$
    -- Which allergens and claims a menu actually reaches, rather than the whole catalog:
    -- a tenant that has defined an allergen it does not use on this menu is not thereby
    -- prevented from publishing it.
    WITH menu_subjects AS (
        SELECT 'item'::menu.menu_entity AS subject, i.id AS subject_id, i.tenant_id
        FROM menu.sellable_item i WHERE i.menu_id = p_menu_id AND i.status = 'active'
        UNION ALL
        SELECT 'variant', v.id, v.tenant_id FROM menu.item_variant v
        JOIN menu.sellable_item i ON i.id = v.item_id
        WHERE i.menu_id = p_menu_id AND v.status = 'active'
        UNION ALL
        SELECT 'modifier', mo.id, mo.tenant_id FROM menu.modifier mo
        JOIN menu.item_modifier_group img ON img.modifier_group_id = mo.modifier_group_id
        JOIN menu.sellable_item i ON i.id = img.item_id
        WHERE i.menu_id = p_menu_id AND i.status = 'active'
    ),
    reached AS (
        SELECT DISTINCT 'allergen'::menu.menu_entity AS entity, d.allergen_id AS entity_id,
               d.tenant_id
        FROM safety.declaration d
        JOIN menu_subjects s ON s.subject = d.subject AND s.subject_id = d.subject_id
        WHERE d.effective_to IS NULL
        UNION
        SELECT DISTINCT 'dietary_claim'::menu.menu_entity, c.claim_id, c.tenant_id
        FROM safety.item_dietary_claim c
        JOIN menu_subjects s ON s.subject = c.subject AND s.subject_id = c.subject_id
        WHERE c.effective_to IS NULL
    ),
    required AS (
        SELECT r.entity, r.entity_id, r.tenant_id, f.field_name, l.locale
        FROM reached r
        JOIN menu.translatable_field f ON f.entity = r.entity AND f.required_for_publication
        CROSS JOIN (SELECT unnest(enum_range(NULL::menu.customer_locale)) AS locale) l
    )
    SELECT q.entity, q.entity_id, q.field_name, q.locale
    FROM required q
    WHERE NOT EXISTS (
        SELECT 1 FROM menu.translation t
        WHERE t.tenant_id = q.tenant_id AND t.entity = q.entity
          AND t.entity_id = q.entity_id AND t.field_name = q.field_name
          AND t.locale = q.locale AND t.state = 'approved')
    ORDER BY q.entity, q.entity_id, q.field_name, q.locale;
$$;

CREATE FUNCTION safety.incomplete_allergen_reviews(p_menu_id uuid)
RETURNS TABLE (subject menu.menu_entity, subject_id uuid, allergen_id uuid,
               kitchen_code text, review_state safety.review_state)
LANGUAGE sql STABLE
AS $$
    -- An open declaration that no human has approved is not evidence a guest may rely
    -- on. Publication waits for the review, exactly as it waits for the translation.
    SELECT d.subject, d.subject_id, d.allergen_id, a.kitchen_code, d.review_state
    FROM safety.declaration d
    JOIN safety.allergen a ON a.id = d.allergen_id
    WHERE d.effective_to IS NULL
      AND d.review_state <> 'approved'
      AND (
        (d.subject = 'item' AND EXISTS (
            SELECT 1 FROM menu.sellable_item i
            WHERE i.id = d.subject_id AND i.menu_id = p_menu_id AND i.status = 'active'))
     OR (d.subject = 'variant' AND EXISTS (
            SELECT 1 FROM menu.item_variant v JOIN menu.sellable_item i ON i.id = v.item_id
            WHERE v.id = d.subject_id AND i.menu_id = p_menu_id AND v.status = 'active'))
     OR (d.subject = 'modifier' AND EXISTS (
            SELECT 1 FROM menu.modifier mo
            JOIN menu.item_modifier_group img ON img.modifier_group_id = mo.modifier_group_id
            JOIN menu.sellable_item i ON i.id = img.item_id
            WHERE mo.id = d.subject_id AND i.menu_id = p_menu_id AND i.status = 'active')))
    ORDER BY d.subject, d.subject_id, a.kitchen_code;
$$;

-- Publication, extended. Same body M2-A proved, with two safety gates ahead of the write
-- and the declaration references recorded after it.
CREATE OR REPLACE FUNCTION menu.publish_menu(p_menu_id uuid, p_published_by uuid)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    m          menu.menu%ROWTYPE;
    v_missing  integer;
    v_example  record;
    v_snapshot uuid := gen_random_uuid();
    v_digest   bytea;
BEGIN
    SELECT * INTO m FROM menu.menu WHERE id = p_menu_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'MENU_ABSENT: no menu %', p_menu_id USING ERRCODE = 'HS404';
    END IF;

    IF m.state NOT IN ('draft', 'review', 'scheduled', 'paused') THEN
        RAISE EXCEPTION 'MENU_NOT_PUBLISHABLE: a menu in state % cannot be published', m.state
            USING ERRCODE = 'HS409';
    END IF;

    SELECT count(*) INTO v_missing FROM menu.missing_required_translations(p_menu_id);
    IF v_missing > 0 THEN
        SELECT * INTO v_example FROM menu.missing_required_translations(p_menu_id) LIMIT 1;
        RAISE EXCEPTION
            'REQUIRED_TRANSLATION_MISSING: % required translation(s) absent, for example % on % in locale %',
            v_missing, v_example.field_name, v_example.entity, v_example.locale
            USING ERRCODE = 'HS422';
    END IF;

    -- FR-SAF-007, first half. Safety text is not merely a required translation among
    -- others: publishing a menu whose allergen warning has no Arabic is publishing a menu
    -- an Arabic-reading guest cannot use safely, so it is named separately and refused
    -- under its own signature.
    SELECT count(*) INTO v_missing FROM safety.missing_safety_translations(p_menu_id);
    IF v_missing > 0 THEN
        SELECT * INTO v_example FROM safety.missing_safety_translations(p_menu_id) LIMIT 1;
        RAISE EXCEPTION
            'REQUIRED_SAFETY_TRANSLATION_MISSING: % safety translation(s) absent, for '
            'example % on % in locale %',
            v_missing, v_example.field_name, v_example.entity, v_example.locale
            USING ERRCODE = 'HS422';
    END IF;

    -- FR-SAF-007, second half. Translated text nobody reviewed is a translation of an
    -- unreviewed claim.
    SELECT count(*) INTO v_missing FROM safety.incomplete_allergen_reviews(p_menu_id);
    IF v_missing > 0 THEN
        SELECT * INTO v_example FROM safety.incomplete_allergen_reviews(p_menu_id) LIMIT 1;
        RAISE EXCEPTION
            'ALLERGEN_REVIEW_INCOMPLETE: % declaration(s) not through review, for example '
            '% on a %', v_missing, v_example.kitchen_code, v_example.subject
            USING ERRCODE = 'HS422';
    END IF;

    INSERT INTO menu.publication_snapshot_line
        (tenant_id, outlet_id, snapshot_id, item_id, variant_id, item_code, canonical_name,
         channel, currency_code, amount_minor, tax_context, availability)
    SELECT i.tenant_id, i.outlet_id, v_snapshot, i.id, v.id, i.item_code, i.canonical_name,
           p.channel, p.currency_code, p.amount_minor, p.tax_context,
           coalesce(a.state, 'available'::menu.availability_state)
    FROM menu.sellable_item i
    JOIN menu.item_variant v ON v.item_id = i.id AND v.status = 'active'
    JOIN menu.price p ON p.variant_id = v.id AND p.effective_to IS NULL
    LEFT JOIN menu.availability a ON a.variant_id = v.id
    WHERE i.menu_id = p_menu_id AND i.status = 'active'
    ORDER BY i.item_code, v.variant_code;

    SELECT sha256(convert_to(coalesce(string_agg(
               l.item_code || '|' || coalesce(l.variant_id::text, '') || '|' ||
               l.currency_code || '|' || l.amount_minor::text || '|' || l.tax_context,
               E'\n' ORDER BY l.id), ''), 'UTF8'))
    INTO v_digest
    FROM menu.publication_snapshot_line l WHERE l.snapshot_id = v_snapshot;

    INSERT INTO menu.publication_snapshot
        (id, tenant_id, outlet_id, menu_id, published_by_user_id, content_digest)
    VALUES (v_snapshot, m.tenant_id, m.outlet_id, p_menu_id, p_published_by, v_digest);

    -- What was believed at this moment, recorded for audit and for nothing else. The
    -- digest above deliberately does NOT cover these rows: the snapshot's integrity is
    -- about the prices it fixed, and binding it to a safety state would turn a later
    -- correction into a digest mismatch — which is to say, would make correcting an
    -- allergen look like tampering.
    INSERT INTO safety.declaration_reference
        (tenant_id, outlet_id, context, context_id, declaration_id, effective_version)
    SELECT DISTINCT d.tenant_id, d.outlet_id,
           'publication_snapshot'::safety.reference_context, v_snapshot,
           d.id, d.effective_version
    FROM safety.declaration d
    JOIN menu.publication_snapshot_line l ON l.snapshot_id = v_snapshot
    WHERE d.effective_to IS NULL
      AND ((d.subject = 'item' AND d.subject_id = l.item_id)
        OR (d.subject = 'variant' AND d.subject_id = l.variant_id));

    UPDATE menu.menu SET state = 'published', row_version = row_version
    WHERE id = p_menu_id;

    RETURN v_snapshot;
END;
$$;

-- ---------------------------------------------------------------------------
-- Reading a published menu as a guest
-- ---------------------------------------------------------------------------

CREATE FUNCTION menu.published_menu_for_guest(
    p_tenant_id   uuid,
    p_snapshot_id uuid,
    p_locale      menu.customer_locale
) RETURNS TABLE (item_code text, canonical_name text,
                 currency_code char(3), amount_minor money.amount_minor,
                 allergen_kitchen_code text,
                 declaration_class safety.declaration_class,
                 written_warning text, icon_key text)
LANGUAGE sql STABLE
AS $$
    -- The two halves of a published line, from two different places on purpose.
    --
    -- Name and price come from the snapshot, because they are what was agreed and must
    -- not move afterwards. The allergens come from safety.selection_safety(), which
    -- resolves the declarations that are open right now — so a correction made after this
    -- menu was published reaches a guest reading THIS snapshot, with no republication and
    -- no cache to invalidate.
    --
    -- safety.declaration_reference is not read here, and could not be: the application
    -- role has no SELECT on it.
    SELECT l.item_code, l.canonical_name, l.currency_code, l.amount_minor,
           s.kitchen_code, s.declaration_class, s.written_warning, s.icon_key
    FROM menu.publication_snapshot_line l
    LEFT JOIN LATERAL safety.selection_safety(
        p_tenant_id, p_locale, l.item_id, l.variant_id) s ON true
    WHERE l.snapshot_id = p_snapshot_id AND l.tenant_id = p_tenant_id
    ORDER BY l.item_code, s.kitchen_code;
$$;

COMMENT ON FUNCTION menu.published_menu_for_guest IS
    'A published menu as a guest sees it. The price is the pinned one; the allergens are '
    'the current ones. That asymmetry is the central design decision of M2-B: a price '
    'must be what was agreed, an allergen must be what is true.';

-- ===========================================================================
-- Retention learns to anonymize, and stops ignoring what it was told to do
-- ===========================================================================
--
-- A defect in M1-C, found while wiring guest sessions to the engine the M2-B brief says
-- to wire to rather than duplicate.
--
-- config.retention_action offered 'archive' and 'purge', config.retention_policy stored
-- the choice, and config.apply_retention() executed DELETE for both. A tenant that
-- configured archival had its rows deleted, and nothing anywhere reported the
-- difference — the action was recorded and then ignored. That is data loss presenting as
-- correct operation, which is worse than an unimplemented feature that says so.
--
-- Repaired here rather than left for a later gate because M2-B has to add a third action
-- and could not honestly add one to an engine that does not honour the first two.

CREATE TABLE config.anonymization_rule (
    target_schema text NOT NULL,
    target_table  text NOT NULL,

    -- The columns that carry identity and must be emptied, and the column that records
    -- that it happened. Named per table rather than guessed: a sweep that assumed a
    -- column name would silently skip every table not following the convention, which is
    -- the same failure the age_column comment on retention_policy describes.
    identity_columns text[] NOT NULL,
    stamp_column     text NOT NULL,

    PRIMARY KEY (target_schema, target_table),
    CONSTRAINT anonymization_rule_never_targets_audit CHECK (lower(target_schema) <> 'audit'),
    CONSTRAINT anonymization_rule_has_columns CHECK (cardinality(identity_columns) >= 1),
    CONSTRAINT anonymization_rule_stamp_not_blank CHECK (btrim(stamp_column) <> '')
);

COMMENT ON TABLE config.anonymization_rule IS
    'Which columns an "anonymize" retention policy empties, and where it records having '
    'done so. Anonymizing severs the identity and keeps the row, which is what a guest '
    'session needs: the allergy concern raised at a table is operational evidence that '
    'must outlive the guest identity attached to it (FR-CST-002).';

INSERT INTO config.anonymization_rule (target_schema, target_table, identity_columns, stamp_column)
VALUES ('service', 'guest_session', ARRAY['display_nickname'], 'anonymized_at');

CREATE OR REPLACE FUNCTION config.apply_retention(p_tenant_id uuid)
RETURNS TABLE (target text, rows_affected bigint)
LANGUAGE plpgsql
AS $$
DECLARE
    r        record;
    rule     record;
    v_count  bigint;
    v_sets   text;
BEGIN
    FOR r IN
        SELECT * FROM config.retention_policy
        WHERE tenant_id = p_tenant_id
    LOOP
        -- Unchanged from M1-C, and still the second of three guards. The CHECK on the
        -- table should make this unreachable; it is here because a guard that exists only
        -- in a constraint is one migration away from being gone.
        IF lower(r.target_schema) = 'audit' THEN
            RAISE EXCEPTION
                'APPEND_ONLY_VIOLATED: retention may not act on audit storage (%.%)',
                r.target_schema, r.target_table
                USING ERRCODE = 'HS403';
        END IF;

        IF r.action = 'purge' THEN
            EXECUTE format(
                'DELETE FROM %I.%I WHERE %I < now() - $1',
                r.target_schema, r.target_table, r.age_column) USING r.retain_for;
            GET DIAGNOSTICS v_count = ROW_COUNT;

        ELSIF r.action = 'anonymize' THEN
            SELECT * INTO rule FROM config.anonymization_rule
             WHERE target_schema = r.target_schema AND target_table = r.target_table;

            IF rule IS NULL THEN
                RAISE EXCEPTION
                    'RETENTION_RULE_ABSENT: %.% is configured to anonymize but no '
                    'anonymization rule says which columns carry identity',
                    r.target_schema, r.target_table
                    USING ERRCODE = 'HS422';
            END IF;

            SELECT string_agg(format('%I = NULL', c), ', ')
              INTO v_sets FROM unnest(rule.identity_columns) AS c;

            EXECUTE format(
                'UPDATE %I.%I SET %s, %I = now() WHERE %I < now() - $1 AND %I IS NULL',
                r.target_schema, r.target_table, v_sets, rule.stamp_column,
                r.age_column, rule.stamp_column) USING r.retain_for;
            GET DIAGNOSTICS v_count = ROW_COUNT;

        ELSE
            -- 'archive'. There is no archive store in Phase 1, and the honest response to
            -- being asked for one is to say so. Deleting instead — which is what this
            -- function did for every archive policy until now — is the worst available
            -- answer: it destroys exactly the rows the tenant asked to keep, and reports
            -- success.
            RAISE EXCEPTION
                'RETENTION_ACTION_UNIMPLEMENTED: %.% is configured to archive, and there '
                'is no archive store in this phase. Refusing rather than deleting rows a '
                'tenant asked to keep', r.target_schema, r.target_table
                USING ERRCODE = 'HS501';
        END IF;

        target := r.target_schema || '.' || r.target_table;
        rows_affected := v_count;
        RETURN NEXT;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION config.apply_retention(uuid) IS
    'Applies each tenant retention policy according to the action it actually names '
    '(FR-DAT-018). Purge deletes, anonymize empties the columns config.anonymization_rule '
    'names and stamps the row, and archive refuses because Phase 1 has no archive store. '
    'Audit storage is refused before any of that.';

-- ===========================================================================
-- Row level security — the same predicate M1-A proved, unchanged
-- ===========================================================================

DO $$
DECLARE
    t record;
BEGIN
    FOR t IN
        SELECT c.table_schema, c.table_name
        FROM information_schema.tables c
        WHERE c.table_schema IN ('safety', 'service')
          AND c.table_type = 'BASE TABLE'
          -- Reference data, not tenant data: the jurisdictions a regulator defines and
          -- the allergens it requires are the same facts for every tenant. They carry no
          -- tenant_id, so app.row_in_scope() has nothing to test, and the application
          -- role holds SELECT only.
          AND c.table_name NOT IN ('jurisdiction', 'jurisdiction_requirement',
                                   -- Tenant-scoped but outlet-free; its policy is
                                   -- written separately, just below.
                                   'verification_policy')
    LOOP
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',
                       t.table_schema, t.table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE  ROW LEVEL SECURITY',
                       t.table_schema, t.table_name);
        EXECUTE format(
            'CREATE POLICY %I ON %I.%I FOR ALL '
            'USING (app.row_in_scope(tenant_id, outlet_id)) '
            'WITH CHECK (app.row_in_scope(tenant_id, outlet_id))',
            t.table_name || '_isolation', t.table_schema, t.table_name);
    END LOOP;
END;
$$;

-- verification_policy is tenant-scoped but has no outlet column: a tenant's accepted
-- verification methods are a tenant-wide choice. Its policy tests the tenant alone,
-- which is the same exception org.tenant carries and for the same reason.
ALTER TABLE service.verification_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE service.verification_policy FORCE  ROW LEVEL SECURITY;
CREATE POLICY verification_policy_isolation ON service.verification_policy FOR ALL
    USING (tenant_id = app.current_tenant_id())
    WITH CHECK (tenant_id = app.current_tenant_id());

DO $$
DECLARE
    spec text;
    parts text[];
BEGIN
    FOREACH spec IN ARRAY ARRAY['safety.allergen', 'safety.dietary_claim',
                                'service.table_profile']
    LOOP
        parts := string_to_array(spec, '.');
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE ON %I.%I '
            'FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version()',
            parts[2] || '_row_version', parts[1], parts[2]);
    END LOOP;
END;
$$;

-- ===========================================================================
-- Grants
-- ===========================================================================

GRANT USAGE ON SCHEMA safety, service TO hospitality_app;

-- ---------------------------------------------------------------------------
-- The allergen catalog, one column at a time
-- ---------------------------------------------------------------------------
--
-- "Icons supplement but never replace written warnings" (FR-SAF-002) is enforced by
-- privilege, not by convention. The application role may write icon_key and may never
-- read it: a SELECT naming that column is refused, so a screen that shows an icon has no
-- way to obtain one except through safety.selection_safety(), which returns it beside the
-- written warning or refuses to return anything at all.
--
-- Column-level grants are unusual and that is the point. A comment saying "always show
-- the text with the icon" is a discipline somebody drops under deadline; a privilege that
-- does not exist is not.
GRANT SELECT (id, tenant_id, outlet_id, jurisdiction_code, kitchen_code, status,
              row_version, created_at, updated_at)
    ON safety.allergen TO hospitality_app;
GRANT INSERT, UPDATE, DELETE ON safety.allergen TO hospitality_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    safety.declaration, safety.dietary_claim, safety.dietary_claim_outlet,
    safety.item_dietary_claim, safety.approved_wording, safety.allergy_concern
TO hospitality_app;

GRANT SELECT ON safety.jurisdiction, safety.jurisdiction_requirement TO hospitality_app;

-- The pinned reference: written, never read. See the comment on the table — a value the
-- display path can read is a value the display path will eventually cache.
GRANT INSERT ON safety.declaration_reference TO hospitality_app;
REVOKE SELECT, UPDATE, DELETE, TRUNCATE ON safety.declaration_reference FROM hospitality_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    service.table_profile, service.table_qr_token, service.qr_placard,
    service.table_session, service.guest_session, service.session_participant,
    service.qr_scan, service.verification_policy, service.table_ownership,
    service.ownership_transfer, service.cart, service.cart_line,
    service.cart_line_modifier, service.cart_line_transfer
TO hospitality_app;

-- Which columns carry identity is a property of the schema, not a tenant choice. The
-- runtime reads it so retention can act; it does not get to rewrite the definition of
-- what anonymizing a guest session means.
GRANT SELECT ON config.anonymization_rule TO hospitality_app;

GRANT USAGE ON ALL SEQUENCES IN SCHEMA safety, service TO hospitality_app;

REVOKE CREATE ON SCHEMA safety, service FROM hospitality_app;

-- SECURITY DEFINER functions run as their owner, so EXECUTE is granted explicitly rather
-- than inherited from PUBLIC. Both pair an icon with its words; neither reads the pinned
-- reference.
GRANT EXECUTE ON FUNCTION safety.selection_safety(uuid, menu.customer_locale, uuid, uuid, uuid[])
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION safety.allergen_for_management(uuid, menu.customer_locale)
    TO hospitality_app;

-- ===========================================================================
-- FR-MNU-012 completed: dietary and allergen filters, against a real catalog
-- ===========================================================================
--
-- M2-A closed category, availability, price and preparation time, and deliberately left
-- these two absent rather than present and vacuous — a filter over an empty catalog would
-- have passed every test while examining nothing, which is the vacuity
-- money.assert_currency_paired() carried through the whole of M1.
--
-- The catalog now exists, so the filters can be built and can fail. Dropping first
-- because adding defaulted parameters to an existing function creates an overload rather
-- than replacing it, and every call with the old argument count would then be ambiguous.

DROP FUNCTION menu.search_items(uuid, uuid, menu.customer_locale, text, uuid,
                                menu.availability_state, char, money.amount_minor,
                                money.amount_minor, integer, timestamptz);

CREATE FUNCTION menu.search_items(
    p_tenant_id       uuid,
    p_outlet_id       uuid,
    p_locale          menu.customer_locale,
    p_query           text DEFAULT NULL,
    p_category_id     uuid DEFAULT NULL,
    p_availability    menu.availability_state DEFAULT NULL,
    p_currency        char(3) DEFAULT NULL,
    p_min_minor       money.amount_minor DEFAULT NULL,
    p_max_minor       money.amount_minor DEFAULT NULL,
    p_max_preparation_minutes integer DEFAULT NULL,
    p_dietary_claim_codes text[] DEFAULT NULL,
    p_exclude_allergen_ids uuid[] DEFAULT NULL,
    p_at              timestamptz DEFAULT now()
) RETURNS TABLE (item_id uuid, item_code text, display_name text,
                 matched_field text, amount_minor money.amount_minor,
                 currency_code char(3), availability menu.availability_state,
                 preparation_minutes integer)
LANGUAGE sql STABLE
AS $$
    WITH needle AS (SELECT menu.normalise_for_search(p_query) AS q),
    localized AS (
        SELECT i.id, i.item_code, i.category_id, i.preparation_minutes,
               coalesce(nm.translated_text, i.canonical_name) AS display_name,
               coalesce(sd.translated_text, i.canonical_short_description) AS short_description
        FROM menu.sellable_item i
        LEFT JOIN menu.translation nm
               ON nm.tenant_id = i.tenant_id AND nm.entity = 'item' AND nm.entity_id = i.id
              AND nm.field_name = 'canonical_name' AND nm.locale = p_locale
              AND nm.state = 'approved'
        LEFT JOIN menu.translation sd
               ON sd.tenant_id = i.tenant_id AND sd.entity = 'item' AND sd.entity_id = i.id
              AND sd.field_name = 'canonical_short_description' AND sd.locale = p_locale
              AND sd.state = 'approved'
        WHERE i.tenant_id = p_tenant_id AND i.status = 'active'
    ),
    priced AS (
        SELECT l.*, v.id AS variant_id,
               menu.effective_price(p_tenant_id, p_outlet_id, v.id, NULL::menu.sales_channel,
                                    coalesce(p_currency, 'ETB'::char(3)), p_at) AS amount_minor,
               coalesce(p_currency, 'ETB'::char(3)) AS currency_code,
               coalesce(a.state, 'available'::menu.availability_state) AS availability
        FROM localized l
        JOIN menu.item_variant v ON v.item_id = l.id AND v.is_default AND v.status = 'active'
        LEFT JOIN menu.availability a
               ON a.variant_id = v.id AND a.outlet_id = p_outlet_id
    )
    SELECT p.id, p.item_code, p.display_name,
           CASE WHEN (SELECT q FROM needle) = '' THEN 'all'
                WHEN menu.normalise_for_search(p.display_name)
                     LIKE '%' || (SELECT q FROM needle) || '%' THEN 'name'
                ELSE 'short_description' END,
           p.amount_minor, p.currency_code, p.availability, p.preparation_minutes
    FROM priced p
    WHERE (p_query IS NULL OR (SELECT q FROM needle) = ''
           OR menu.normalise_for_search(p.display_name)
              LIKE '%' || (SELECT q FROM needle) || '%'
           OR menu.normalise_for_search(p.short_description)
              LIKE '%' || (SELECT q FROM needle) || '%'
           OR menu.normalise_for_search(p.item_code)
              LIKE '%' || (SELECT q FROM needle) || '%')
      AND (p_category_id IS NULL OR p.category_id = p_category_id)
      AND (p_availability IS NULL OR p.availability = p_availability)
      AND (p_min_minor IS NULL OR p.amount_minor >= p_min_minor)
      AND (p_max_minor IS NULL OR p.amount_minor <= p_max_minor)
      AND (p_max_preparation_minutes IS NULL
           OR (p.preparation_minutes IS NOT NULL
               AND p.preparation_minutes <= p_max_preparation_minutes))

      -- Every requested claim must hold, not merely one of them: a guest filtering for
      -- vegan AND fasting is stating two requirements, and returning a dish that
      -- satisfies one of them is worse than returning nothing.
      AND (p_dietary_claim_codes IS NULL OR NOT EXISTS (
            SELECT 1 FROM unnest(p_dietary_claim_codes) AS wanted(code)
            WHERE NOT EXISTS (
                SELECT 1
                FROM safety.item_dietary_claim ic
                JOIN safety.dietary_claim dc ON dc.id = ic.claim_id
                WHERE ic.tenant_id = p_tenant_id
                  AND ic.effective_to IS NULL
                  AND ic.review_state = 'approved'
                  AND dc.code = wanted.code
                  AND ((ic.subject = 'item' AND ic.subject_id = p.id)
                    OR (ic.subject = 'variant' AND ic.subject_id = p.variant_id)))))

      -- Exclusion is by the resolved set of the default variant, and it excludes on ALL
      -- THREE classes. A guest who asks not to see peanuts is not asking to be shown the
      -- dishes that merely MAY contain them: for an allergy, "may contain" and
      -- "cross contact" are reasons to avoid a dish, not footnotes to it. The three
      -- classes stay distinct in the model and in what is displayed; it is only this
      -- filter that treats them alike, and deliberately.
      AND (p_exclude_allergen_ids IS NULL OR NOT EXISTS (
            SELECT 1 FROM safety.effective_allergens(p_tenant_id, p.id, p.variant_id) ea
            WHERE ea.allergen_id = ANY (p_exclude_allergen_ids)))
    ORDER BY p.display_name;
$$;

COMMENT ON FUNCTION menu.search_items IS
    'Searches approved translated names and short descriptions in a given locale, falling '
    'back to the canonical text where no approved translation exists, and filters by '
    'category, availability, price range, preparation time, dietary claim and allergen '
    '(FR-MNU-012, CLOSED AT M2-B). Dietary and allergen filtering reads the catalog M2-B '
    'built; the allergen filter excludes on all three declaration classes, because for '
    'someone avoiding an allergen "may contain" is a reason to avoid.';
