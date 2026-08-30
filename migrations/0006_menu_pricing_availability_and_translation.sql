-- 0006_menu_pricing_availability_and_translation.sql
--
-- Gate:         M2, slice A
-- Requirements: FR-MNU-001 .. FR-MNU-012, FR-I18N-003, FR-I18N-006, FR-I18N-010, FR-I18N-011
--
-- Menu structure, assignment, publication lifecycle, content, variants and modifiers,
-- availability, pricing, dayparts, images, search and translation storage.
--
-- What this migration deliberately does NOT contain, and why the absence is structural
-- rather than a matter of discipline:
--
--   * No recipe or inventory identity. A sellable item carries no recipe reference, no
--     cost, no yield and no quantity on hand. FR-MNU-001 requires menu structure to be
--     independent of those identities, and the M2-A suite proves no column in this schema
--     matches the fenced vocabulary loaded from the pinned package.
--   * No quantity behind availability. FR-MNU-007 requires availability WITHOUT exposing
--     how much is left. There is no numeric column anywhere in this schema that could
--     carry one, so "limited" is a state and not a number.
--   * No customer-segment targeting. Removed at v2.0.9 and fenced: assignment is by
--     outlet, service area, channel, daypart and date range, and by nothing else.
--   * No tables, QR tokens or guest sessions (M2-B); no allergen or dietary catalogue
--     (M2-B); no rendering surface (M2-C); no order, check or payment surface (M3, M4).
--
-- Every tenant-scoped table has row level security ENABLEd and FORCEd on
-- app.row_in_scope() from 0001, unchanged and unweakened.

CREATE SCHEMA menu;

COMMENT ON SCHEMA menu IS
    'Menu structure, pricing, availability and translation storage (M2-A). Independent of '
    'recipe and inventory identities: no column here references either, and the '
    'verification suite proves it against the pinned fenced vocabulary rather than a list '
    'written by hand.';

-- ===========================================================================
-- Enumerations — every one closed, so an unlisted value is a type error
-- ===========================================================================

CREATE TYPE menu.publication_state AS ENUM
    ('draft', 'review', 'scheduled', 'published', 'paused', 'archived');

COMMENT ON TYPE menu.publication_state IS
    'The publication lifecycle of a menu (FR-MNU-003). Publishing writes an immutable '
    'snapshot; M3 orders will reference that snapshot, so a mutable one would make M3''s '
    'price evidence worthless.';

-- Available, limited, temporarily unavailable, scheduled later, hidden — and nothing
-- numeric. "limited" tells a guest to expect scarcity; it does not tell them how many.
CREATE TYPE menu.availability_state AS ENUM
    ('available', 'limited', 'temporarily_unavailable', 'scheduled_later', 'hidden');

COMMENT ON TYPE menu.availability_state IS
    'Availability as a state, never a count (FR-MNU-007). The exact remaining figure is '
    'not modelled anywhere in this schema, which is also how the inventory fence is held: '
    'there is nothing to disclose because there is nothing to store.';

-- Exactly three customer locales (FR-I18N-003). A fourth is a type error, not a row.
CREATE TYPE menu.customer_locale AS ENUM ('en', 'am', 'ar');

COMMENT ON TYPE menu.customer_locale IS
    'The three customer locales Phase 1 supports: English, Amharic, Arabic. Closed, so a '
    'locale nobody has agreed to support cannot be introduced by an INSERT. Rendering '
    'these — including right-to-left — is M2-C; this gate stores and approves only.';

CREATE TYPE menu.translation_state AS ENUM ('draft', 'in_review', 'approved', 'rejected');

CREATE TYPE menu.translation_provenance AS ENUM ('human', 'machine_assisted');

COMMENT ON TYPE menu.translation_provenance IS
    'How a translation was produced (FR-I18N-010). Machine assistance is permitted for a '
    'draft; it is never permitted to approve itself, and never for safety-critical text.';

-- No pickup or delivery value exists here. Both are permanently fenced, so the channel
-- vocabulary cannot express them.
CREATE TYPE menu.sales_channel AS ENUM ('dine_in', 'counter', 'room_service', 'kiosk');

CREATE TYPE menu.variant_axis AS ENUM ('size', 'portion', 'temperature', 'preparation_style');

CREATE TYPE menu.menu_entity AS ENUM
    ('menu', 'category', 'item_group', 'item', 'variant', 'modifier_group', 'modifier', 'image');

CREATE TYPE menu.image_format AS ENUM ('webp', 'avif', 'jpeg', 'png');

-- ===========================================================================
-- Structure (FR-MNU-001)
-- ===========================================================================

CREATE TABLE menu.menu (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid,
    menu_code      text NOT NULL,
    canonical_name text NOT NULL,
    state          menu.publication_state NOT NULL DEFAULT 'draft',
    display_order  integer NOT NULL DEFAULT 0,
    row_version    bigint NOT NULL DEFAULT 1,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT menu_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT menu_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT menu_code_not_blank CHECK (btrim(menu_code) <> ''),
    CONSTRAINT menu_name_not_blank CHECK (btrim(canonical_name) <> ''),
    CONSTRAINT menu_code_unique UNIQUE (tenant_id, outlet_id, menu_code)
);

CREATE TABLE menu.category (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          uuid NOT NULL,
    outlet_id          uuid,
    menu_id            uuid NOT NULL,
    parent_category_id uuid,
    category_code      text NOT NULL,
    canonical_name     text NOT NULL,
    display_order      integer NOT NULL DEFAULT 0,
    status             org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version        bigint NOT NULL DEFAULT 1,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT category_menu_fk FOREIGN KEY (menu_id)
        REFERENCES menu.menu (id) ON DELETE RESTRICT,
    CONSTRAINT category_parent_fk FOREIGN KEY (parent_category_id)
        REFERENCES menu.category (id) ON DELETE RESTRICT,
    CONSTRAINT category_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT category_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT category_code_not_blank CHECK (btrim(category_code) <> ''),
    CONSTRAINT category_code_unique UNIQUE (tenant_id, menu_id, category_code)
);

-- A cross-cutting grouping ("chef's selection"), independent of the category tree.
CREATE TABLE menu.item_group (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid,
    menu_id        uuid NOT NULL,
    group_code     text NOT NULL,
    canonical_name text NOT NULL,
    display_order  integer NOT NULL DEFAULT 0,
    status         org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version    bigint NOT NULL DEFAULT 1,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT item_group_menu_fk FOREIGN KEY (menu_id)
        REFERENCES menu.menu (id) ON DELETE RESTRICT,
    CONSTRAINT item_group_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT item_group_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT item_group_code_unique UNIQUE (tenant_id, menu_id, group_code)
);

-- The sellable item. Content lives here in its canonical locale; every other locale is a
-- row in menu.translation, stored separately (FR-I18N-003).
--
-- customer_visible_ingredients is exactly that: the sentence a guest reads. It is not a
-- recipe. There is no quantity, no unit, no yield and no cost, and there is no reference
-- to any production record.
CREATE TABLE menu.sellable_item (
    id                            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                     uuid NOT NULL,
    outlet_id                     uuid,
    menu_id                       uuid NOT NULL,
    category_id                   uuid,
    item_code                     text NOT NULL,
    canonical_name                text NOT NULL,
    canonical_short_description   text,
    canonical_long_description    text,
    customer_visible_ingredients  text,
    preparation_minutes           integer,
    display_order                 integer NOT NULL DEFAULT 0,
    status                        org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version                   bigint NOT NULL DEFAULT 1,
    created_at                    timestamptz NOT NULL DEFAULT now(),
    updated_at                    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT sellable_item_menu_fk FOREIGN KEY (menu_id)
        REFERENCES menu.menu (id) ON DELETE RESTRICT,
    CONSTRAINT sellable_item_category_fk FOREIGN KEY (category_id)
        REFERENCES menu.category (id) ON DELETE RESTRICT,
    CONSTRAINT sellable_item_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT sellable_item_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT sellable_item_code_not_blank CHECK (btrim(item_code) <> ''),
    CONSTRAINT sellable_item_name_not_blank CHECK (btrim(canonical_name) <> ''),
    CONSTRAINT sellable_item_preparation_sane
        CHECK (preparation_minutes IS NULL OR (preparation_minutes >= 0 AND preparation_minutes <= 600)),
    CONSTRAINT sellable_item_code_unique UNIQUE (tenant_id, menu_id, item_code)
);

COMMENT ON COLUMN menu.sellable_item.customer_visible_ingredients IS
    'The ingredient sentence a guest reads (FR-MNU-004). Not a recipe: no quantity, no '
    'unit, no yield, no cost and no reference to any production record. Marked '
    'safety-critical in menu.translatable_field, so a machine-assisted translation of it '
    'can never be approved without a human.';

CREATE TABLE menu.item_group_member (
    tenant_id     uuid NOT NULL,
    item_group_id uuid NOT NULL,
    item_id       uuid NOT NULL,
    display_order integer NOT NULL DEFAULT 0,
    outlet_id     uuid,

    PRIMARY KEY (item_group_id, item_id),
    CONSTRAINT item_group_member_group_fk FOREIGN KEY (item_group_id)
        REFERENCES menu.item_group (id) ON DELETE CASCADE,
    CONSTRAINT item_group_member_item_fk FOREIGN KEY (item_id)
        REFERENCES menu.sellable_item (id) ON DELETE CASCADE,
    CONSTRAINT item_group_member_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT
);

-- Variants carry their own prices and their own availability (FR-MNU-005).
CREATE TABLE menu.item_variant (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid,
    item_id        uuid NOT NULL,
    axis           menu.variant_axis NOT NULL,
    variant_code   text NOT NULL,
    canonical_name text NOT NULL,
    is_default     boolean NOT NULL DEFAULT false,
    display_order  integer NOT NULL DEFAULT 0,
    status         org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version    bigint NOT NULL DEFAULT 1,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT item_variant_item_fk FOREIGN KEY (item_id)
        REFERENCES menu.sellable_item (id) ON DELETE RESTRICT,
    CONSTRAINT item_variant_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT item_variant_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT item_variant_code_unique UNIQUE (tenant_id, item_id, variant_code)
);

-- Exactly one default variant per item, enforced structurally rather than by convention.
CREATE UNIQUE INDEX item_variant_single_default
    ON menu.item_variant (tenant_id, item_id) WHERE is_default;

-- ===========================================================================
-- Modifiers (FR-MNU-006)
-- ===========================================================================

CREATE TABLE menu.modifier_group (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          uuid NOT NULL,
    outlet_id          uuid,
    group_code         text NOT NULL,
    canonical_name     text NOT NULL,
    is_required        boolean NOT NULL DEFAULT false,
    min_selections     integer NOT NULL DEFAULT 0,
    max_selections     integer,
    included_selections integer NOT NULL DEFAULT 0,
    display_order      integer NOT NULL DEFAULT 0,
    status             org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version        bigint NOT NULL DEFAULT 1,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT modifier_group_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT modifier_group_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT modifier_group_code_unique UNIQUE (tenant_id, group_code),
    CONSTRAINT modifier_group_selection_bounds
        CHECK (min_selections >= 0
               AND (max_selections IS NULL OR max_selections >= min_selections)
               AND included_selections >= 0
               AND (max_selections IS NULL OR included_selections <= max_selections)),
    -- A required group that permits zero selections is not required.
    CONSTRAINT modifier_group_required_means_one
        CHECK (NOT is_required OR min_selections >= 1)
);

CREATE TABLE menu.modifier (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    outlet_id         uuid,
    modifier_group_id uuid NOT NULL,
    modifier_code     text NOT NULL,
    canonical_name    text NOT NULL,
    is_default        boolean NOT NULL DEFAULT false,
    display_order     integer NOT NULL DEFAULT 0,
    status            org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version       bigint NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT modifier_group_ref_fk FOREIGN KEY (modifier_group_id)
        REFERENCES menu.modifier_group (id) ON DELETE RESTRICT,
    CONSTRAINT modifier_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT modifier_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT modifier_code_unique UNIQUE (tenant_id, modifier_group_id, modifier_code)
);

CREATE TABLE menu.item_modifier_group (
    tenant_id         uuid NOT NULL,
    outlet_id         uuid,
    item_id           uuid NOT NULL,
    modifier_group_id uuid NOT NULL,
    display_order     integer NOT NULL DEFAULT 0,

    PRIMARY KEY (item_id, modifier_group_id),
    CONSTRAINT item_modifier_group_item_fk FOREIGN KEY (item_id)
        REFERENCES menu.sellable_item (id) ON DELETE CASCADE,
    CONSTRAINT item_modifier_group_group_fk FOREIGN KEY (modifier_group_id)
        REFERENCES menu.modifier_group (id) ON DELETE RESTRICT,
    CONSTRAINT item_modifier_group_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT item_modifier_group_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT
);

-- Incompatibility is symmetric in meaning, so it is stored once and read both ways. The
-- ordered pair constraint stops the same fact being recorded twice in opposite directions
-- and then disagreeing with itself.
CREATE TABLE menu.modifier_incompatibility (
    tenant_id            uuid NOT NULL,
    outlet_id            uuid,
    modifier_id          uuid NOT NULL,
    incompatible_with_id uuid NOT NULL,
    note                 text,

    PRIMARY KEY (modifier_id, incompatible_with_id),
    CONSTRAINT modifier_incompatibility_left_fk FOREIGN KEY (modifier_id)
        REFERENCES menu.modifier (id) ON DELETE CASCADE,
    CONSTRAINT modifier_incompatibility_right_fk FOREIGN KEY (incompatible_with_id)
        REFERENCES menu.modifier (id) ON DELETE CASCADE,
    CONSTRAINT modifier_incompatibility_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT modifier_incompatibility_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT modifier_incompatibility_not_self CHECK (modifier_id <> incompatible_with_id),
    CONSTRAINT modifier_incompatibility_ordered CHECK (modifier_id < incompatible_with_id)
);

CREATE FUNCTION menu.modifiers_are_incompatible(p_left uuid, p_right uuid)
RETURNS boolean
LANGUAGE sql STABLE
AS $$
    SELECT EXISTS (
        SELECT 1 FROM menu.modifier_incompatibility i
        WHERE (i.modifier_id = least(p_left, p_right)
               AND i.incompatible_with_id = greatest(p_left, p_right))
    );
$$;

COMMENT ON FUNCTION menu.modifiers_are_incompatible(uuid, uuid) IS
    'Reads the incompatibility in either order. The pair is stored once, ordered, so the '
    'same fact cannot be recorded twice and then disagree with itself.';

-- ===========================================================================
-- Dayparts (FR-MNU-010) — evaluated in OUTLET-LOCAL time
-- ===========================================================================
-- The window is a wall-clock time at the outlet, not an instant. Evaluating it in server
-- time gives the wrong answer for every outlet not sitting in the server's zone, and the
-- wrong answer twice a year for any outlet whose zone observes daylight saving. The
-- timezone comes from org.outlet_profile, which M1-A already validates.

CREATE TABLE menu.daypart (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid,
    daypart_code   text NOT NULL,
    canonical_name text NOT NULL,
    starts_at_local time NOT NULL,
    ends_at_local   time NOT NULL,
    status         org.lifecycle_status NOT NULL DEFAULT 'active',
    row_version    bigint NOT NULL DEFAULT 1,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT daypart_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT daypart_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT daypart_code_not_blank CHECK (btrim(daypart_code) <> ''),
    CONSTRAINT daypart_not_empty CHECK (starts_at_local <> ends_at_local),
    CONSTRAINT daypart_code_unique UNIQUE (tenant_id, outlet_id, daypart_code)
);

COMMENT ON TABLE menu.daypart IS
    'Tenant-defined service windows (FR-MNU-010): breakfast, lunch, dinner, late-night and '
    'any window a tenant names. Times are OUTLET-LOCAL wall clock. A window whose end is '
    'before its start crosses midnight and is read that way.';

CREATE FUNCTION menu.outlet_timezone(p_tenant_id uuid, p_outlet_id uuid)
RETURNS text
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_zone text;
BEGIN
    SELECT p.timezone INTO v_zone
    FROM org.outlet_profile p
    WHERE p.tenant_id = p_tenant_id AND p.outlet_id = p_outlet_id;

    IF v_zone IS NULL THEN
        -- Never fall back to the server zone. A missing profile is a fault to report,
        -- not a default to assume: assuming one is how a daypart silently answers in the
        -- wrong zone and nobody finds out until a guest is charged a breakfast price at
        -- dinner.
        RAISE EXCEPTION 'OUTLET_TIMEZONE_UNKNOWN: outlet % has no profile timezone', p_outlet_id
            USING ERRCODE = 'HS404';
    END IF;
    RETURN v_zone;
END;
$$;

CREATE FUNCTION menu.local_wall_clock(p_tenant_id uuid, p_outlet_id uuid, p_at timestamptz)
RETURNS timestamp
LANGUAGE sql STABLE
AS $$
    SELECT p_at AT TIME ZONE menu.outlet_timezone(p_tenant_id, p_outlet_id);
$$;

COMMENT ON FUNCTION menu.local_wall_clock(uuid, uuid, timestamptz) IS
    'The wall-clock reading at the outlet for a given instant. AT TIME ZONE resolves the '
    'offset in force at that instant, so a daylight-saving transition is handled by the '
    'timezone database rather than by arithmetic.';

CREATE FUNCTION menu.is_daypart_active(p_daypart_id uuid, p_at timestamptz)
RETURNS boolean
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    d menu.daypart%ROWTYPE;
    v_local time;
BEGIN
    SELECT * INTO d FROM menu.daypart WHERE id = p_daypart_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'DAYPART_ABSENT: no daypart %', p_daypart_id USING ERRCODE = 'HS404';
    END IF;

    v_local := menu.local_wall_clock(d.tenant_id, d.outlet_id, p_at)::time;

    IF d.starts_at_local < d.ends_at_local THEN
        -- An ordinary window: start inclusive, end exclusive, so two adjacent windows
        -- never both claim the boundary minute.
        RETURN v_local >= d.starts_at_local AND v_local < d.ends_at_local;
    END IF;
    -- Crosses midnight: late-night 22:00 to 02:00 is active on both sides of the day.
    RETURN v_local >= d.starts_at_local OR v_local < d.ends_at_local;
END;
$$;

CREATE FUNCTION menu.active_dayparts(p_tenant_id uuid, p_outlet_id uuid, p_at timestamptz)
RETURNS TABLE (daypart_id uuid, daypart_code text)
LANGUAGE sql STABLE
AS $$
    SELECT d.id, d.daypart_code
    FROM menu.daypart d
    WHERE d.tenant_id = p_tenant_id
      AND (d.outlet_id IS NULL OR d.outlet_id = p_outlet_id)
      AND d.status = 'active'
      AND menu.is_daypart_active(d.id, p_at)
    ORDER BY d.daypart_code;
$$;

-- ===========================================================================
-- Assignment (FR-MNU-002A)
-- ===========================================================================
-- By outlet, service area, channel, daypart and date range. There is no customer-segment
-- column, no segment reference and no way to express one: that targeting was removed at
-- v2.0.9 and is fenced, so the schema cannot carry it even by accident.

CREATE TABLE menu.assignment (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    outlet_id       uuid NOT NULL,
    menu_id         uuid NOT NULL,
    service_area_id uuid,
    channel         menu.sales_channel NOT NULL,
    daypart_id      uuid,
    effective_from  date NOT NULL,
    effective_to    date,
    row_version     bigint NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT assignment_menu_fk FOREIGN KEY (menu_id)
        REFERENCES menu.menu (id) ON DELETE RESTRICT,
    CONSTRAINT assignment_daypart_fk FOREIGN KEY (daypart_id)
        REFERENCES menu.daypart (id) ON DELETE RESTRICT,
    CONSTRAINT assignment_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT assignment_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT assignment_service_area_fk FOREIGN KEY (tenant_id, service_area_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT assignment_range_ordered
        CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

COMMENT ON TABLE menu.assignment IS
    'Where and when a menu applies (FR-MNU-002A): outlet, service area, channel, daypart '
    'and date range. Customer-segment targeting is Phase 2 CRM, was removed at v2.0.9 and '
    'is fenced — no column here can express it.';

-- ===========================================================================
-- Pricing (FR-MNU-009) — exact money, never a float
-- ===========================================================================
-- Effective-dated by outlet, channel, variant, currency and tax context. The amount is
-- money.amount_minor from 0003 — integer minor units — and it sits beside an explicit
-- currency_code with a foreign key into money.currency. These are the first columns of
-- that domain type to exist anywhere, which is what makes money.assert_currency_paired()
-- non-vacuous from this migration onward.

CREATE TABLE menu.price (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid,
    item_id        uuid,
    variant_id     uuid,
    modifier_id    uuid,
    channel        menu.sales_channel,
    currency_code  char(3) NOT NULL,
    amount_minor   money.amount_minor NOT NULL,
    tax_context    text NOT NULL DEFAULT 'standard',
    effective_from timestamptz NOT NULL DEFAULT now(),
    effective_to   timestamptz,
    row_version    bigint NOT NULL DEFAULT 1,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT price_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT price_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT price_item_fk FOREIGN KEY (item_id)
        REFERENCES menu.sellable_item (id) ON DELETE RESTRICT,
    CONSTRAINT price_variant_fk FOREIGN KEY (variant_id)
        REFERENCES menu.item_variant (id) ON DELETE RESTRICT,
    CONSTRAINT price_modifier_fk FOREIGN KEY (modifier_id)
        REFERENCES menu.modifier (id) ON DELETE RESTRICT,
    CONSTRAINT price_currency_fk FOREIGN KEY (currency_code)
        REFERENCES money.currency (code) ON DELETE RESTRICT,
    -- Exactly one subject. A price row that priced two things, or nothing, would be
    -- ambiguous at exactly the moment M3 needs it to be exact.
    CONSTRAINT price_one_subject CHECK (
        (item_id IS NOT NULL)::int + (variant_id IS NOT NULL)::int
      + (modifier_id IS NOT NULL)::int = 1),
    CONSTRAINT price_range_ordered
        CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT price_tax_context_not_blank CHECK (btrim(tax_context) <> '')
);

COMMENT ON TABLE menu.price IS
    'Effective-dated prices by outlet, channel, variant, currency and tax context '
    '(FR-MNU-009). amount_minor is money.amount_minor — integer minor units of the '
    'currency named beside it. No floating point type appears in this schema and the '
    'verification suite fails if one ever does.';

COMMENT ON COLUMN menu.price.amount_minor IS
    'Integer minor units. Never a float, never a bare decimal. The currency_code column '
    'beside it is what money.assert_currency_paired() requires, and this is the first '
    'money.amount_minor column in the database — the check was vacuous until now.';

-- One open price per subject, per channel, per currency, per tax context. A second open
-- row would make "the price" a question with two answers.
-- Two indexes rather than one, because casting an enum to text is STABLE and not
-- IMMUTABLE — PostgreSQL refuses it in an index expression, correctly: an enum label can
-- be renamed, which would silently invalidate every entry built from it. Splitting on
-- whether the channel is named indexes the enum column itself.
CREATE UNIQUE INDEX price_single_open_row_for_channel
    ON menu.price (tenant_id,
                   coalesce(outlet_id, '00000000-0000-0000-0000-000000000000'::uuid),
                   coalesce(item_id, '00000000-0000-0000-0000-000000000000'::uuid),
                   coalesce(variant_id, '00000000-0000-0000-0000-000000000000'::uuid),
                   coalesce(modifier_id, '00000000-0000-0000-0000-000000000000'::uuid),
                   channel, currency_code, tax_context)
    WHERE effective_to IS NULL AND channel IS NOT NULL;

CREATE UNIQUE INDEX price_single_open_row_any_channel
    ON menu.price (tenant_id,
                   coalesce(outlet_id, '00000000-0000-0000-0000-000000000000'::uuid),
                   coalesce(item_id, '00000000-0000-0000-0000-000000000000'::uuid),
                   coalesce(variant_id, '00000000-0000-0000-0000-000000000000'::uuid),
                   coalesce(modifier_id, '00000000-0000-0000-0000-000000000000'::uuid),
                   currency_code, tax_context)
    WHERE effective_to IS NULL AND channel IS NULL;

CREATE INDEX price_subject_idx ON menu.price (tenant_id, variant_id, effective_from DESC);

CREATE FUNCTION menu.effective_price(
    p_tenant_id  uuid,
    p_outlet_id  uuid,
    p_variant_id uuid,
    p_channel    menu.sales_channel,
    p_currency   char(3),
    p_at         timestamptz DEFAULT now()
) RETURNS money.amount_minor
LANGUAGE sql STABLE
AS $$
    SELECT p.amount_minor
    FROM menu.price p
    WHERE p.tenant_id  = p_tenant_id
      AND p.variant_id = p_variant_id
      AND p.currency_code = p_currency
      AND (p.outlet_id IS NULL OR p.outlet_id = p_outlet_id)
      AND (p.channel   IS NULL OR p.channel   = p_channel)
      AND p.effective_from <= p_at
      AND (p.effective_to IS NULL OR p.effective_to > p_at)
    -- Most specific wins: an outlet-and-channel price beats an outlet price, which beats
    -- a tenant-wide one. Ordering makes the precedence explicit rather than incidental.
    ORDER BY (p.outlet_id IS NOT NULL) DESC, (p.channel IS NOT NULL) DESC,
             p.effective_from DESC
    LIMIT 1;
$$;

-- ===========================================================================
-- Availability (FR-MNU-007, FR-MNU-008)
-- ===========================================================================

CREATE TABLE menu.availability (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    outlet_id         uuid NOT NULL,
    item_id           uuid,
    variant_id        uuid,
    modifier_id       uuid,
    state             menu.availability_state NOT NULL DEFAULT 'available',
    available_from    timestamptz,
    row_version       bigint NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT availability_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT availability_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT availability_item_fk FOREIGN KEY (item_id)
        REFERENCES menu.sellable_item (id) ON DELETE CASCADE,
    CONSTRAINT availability_variant_fk FOREIGN KEY (variant_id)
        REFERENCES menu.item_variant (id) ON DELETE CASCADE,
    CONSTRAINT availability_modifier_fk FOREIGN KEY (modifier_id)
        REFERENCES menu.modifier (id) ON DELETE CASCADE,
    CONSTRAINT availability_one_subject CHECK (
        (item_id IS NOT NULL)::int + (variant_id IS NOT NULL)::int
      + (modifier_id IS NOT NULL)::int = 1),
    -- "scheduled later" is the only state that may name a time, and it must name one.
    CONSTRAINT availability_scheduled_has_time CHECK (
        (state = 'scheduled_later') = (available_from IS NOT NULL))
);

COMMENT ON TABLE menu.availability IS
    'Availability as a state (FR-MNU-007). There is no numeric column here and none '
    'anywhere else in this schema that could hold a remaining count, so the exact figure '
    'cannot be disclosed by this model — it does not exist in it. "limited" signals '
    'scarcity without quantifying it.';

CREATE UNIQUE INDEX availability_one_row_per_subject
    ON menu.availability (tenant_id, outlet_id,
                          coalesce(item_id, '00000000-0000-0000-0000-000000000000'::uuid),
                          coalesce(variant_id, '00000000-0000-0000-0000-000000000000'::uuid),
                          coalesce(modifier_id, '00000000-0000-0000-0000-000000000000'::uuid));

-- Authorized staff may pause with a reason code and an optional expected return
-- (FR-MNU-008). The reason code is M1-C's registry, referenced and never copied.
CREATE TABLE menu.availability_pause (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          uuid NOT NULL,
    outlet_id          uuid NOT NULL,
    availability_id    uuid NOT NULL,
    reason_code_id     uuid NOT NULL,
    paused_by_user_id  uuid NOT NULL,
    paused_at          timestamptz NOT NULL DEFAULT now(),
    expected_return_at timestamptz,
    released_at        timestamptz,

    CONSTRAINT availability_pause_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT availability_pause_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT availability_pause_availability_fk FOREIGN KEY (availability_id)
        REFERENCES menu.availability (id) ON DELETE CASCADE,
    CONSTRAINT availability_pause_reason_fk FOREIGN KEY (tenant_id, reason_code_id)
        REFERENCES config.reason_code (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT availability_pause_actor_fk FOREIGN KEY (tenant_id, paused_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT availability_pause_return_after_pause
        CHECK (expected_return_at IS NULL OR expected_return_at > paused_at),
    CONSTRAINT availability_pause_release_after_pause
        CHECK (released_at IS NULL OR released_at >= paused_at)
);

-- ===========================================================================
-- Translation storage (FR-I18N-003, FR-I18N-011)
-- ===========================================================================
-- Approved customer translations are stored SEPARATELY from the canonical record. The
-- canonical text stays on menu.sellable_item and its siblings; every other locale is a
-- row here. Nothing overwrites the canonical value, so a translation cannot silently
-- become the record.
--
-- Rendering these — right-to-left, font fallback, digit shaping — is M2-C. This gate
-- stores, reviews and approves, and does nothing at render time.

CREATE TABLE menu.translatable_field (
    entity                  menu.menu_entity NOT NULL,
    field_name              text NOT NULL,
    required_for_publication boolean NOT NULL DEFAULT true,
    safety_critical         boolean NOT NULL DEFAULT false,

    PRIMARY KEY (entity, field_name),
    CONSTRAINT translatable_field_name_not_blank CHECK (btrim(field_name) <> '')
);

COMMENT ON TABLE menu.translatable_field IS
    'The registry of what must be translated before a menu may publish, and which of '
    'those fields is safety-critical. Reference data, not tenant data: the same fields '
    'are required of every tenant, so this table is deliberately not tenant-scoped and '
    'the application role holds SELECT only.';

INSERT INTO menu.translatable_field (entity, field_name, required_for_publication, safety_critical) VALUES
    ('menu',           'canonical_name',               true,  false),
    ('category',       'canonical_name',               true,  false),
    ('item_group',     'canonical_name',               true,  false),
    ('item',           'canonical_name',               true,  false),
    ('item',           'canonical_short_description',  true,  false),
    ('item',           'canonical_long_description',   false, false),
    -- Customer-visible ingredients are what a guest reads before deciding whether they
    -- can eat something. A machine draft is allowed; approving one without a human is not.
    ('item',           'customer_visible_ingredients', true,  true),
    ('variant',        'canonical_name',               true,  false),
    ('modifier_group', 'canonical_name',               true,  false),
    ('modifier',       'canonical_name',               true,  false),
    ('image',          'alt_text',                     true,  false);

CREATE TABLE menu.translation (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    outlet_id         uuid,
    entity            menu.menu_entity NOT NULL,
    entity_id         uuid NOT NULL,
    field_name        text NOT NULL,
    locale            menu.customer_locale NOT NULL,
    translated_text   text NOT NULL,
    state             menu.translation_state NOT NULL DEFAULT 'draft',
    provenance        menu.translation_provenance NOT NULL DEFAULT 'human',
    machine_engine    text,
    translated_by_user_id uuid,
    reviewed_by_user_id   uuid,
    approved_at       timestamptz,
    row_version       bigint NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT translation_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT translation_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT translation_field_fk FOREIGN KEY (entity, field_name)
        REFERENCES menu.translatable_field (entity, field_name) ON DELETE RESTRICT,
    CONSTRAINT translation_translator_fk FOREIGN KEY (tenant_id, translated_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT translation_reviewer_fk FOREIGN KEY (tenant_id, reviewed_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT translation_text_not_blank CHECK (btrim(translated_text) <> ''),
    CONSTRAINT translation_unique UNIQUE (tenant_id, entity, entity_id, field_name, locale),

    -- Provenance is recorded, not implied: a machine-assisted row names its engine, and a
    -- human row does not pretend to have one.
    CONSTRAINT translation_engine_matches_provenance CHECK (
        (provenance = 'machine_assisted') = (machine_engine IS NOT NULL)),

    -- An approved row names its reviewer and the moment. Human review is what "approved"
    -- means (FR-I18N-010); without a named reviewer it is a draft wearing a label.
    CONSTRAINT translation_approval_is_reviewed CHECK (
        (state = 'approved') = (reviewed_by_user_id IS NOT NULL AND approved_at IS NOT NULL))
);

COMMENT ON TABLE menu.translation IS
    'Approved customer translations, stored separately from the canonical record '
    '(FR-I18N-003, FR-I18N-011). Machine assistance is permitted for a draft with its '
    'engine recorded; approval always names a human reviewer. There is no live runtime '
    'translation anywhere in this system — a locale is either stored and approved, or it '
    'is missing and publication is blocked.';

-- Safety-critical text cannot be approved by the same identity that a machine produced it
-- for without a human reviewer, and cannot be approved at all while still machine-owned
-- unless a human is named. Enforced in the database, not in a service that could be
-- bypassed by a direct write.
CREATE FUNCTION menu.enforce_translation_review() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_safety_critical boolean;
BEGIN
    IF NEW.state <> 'approved' THEN
        RETURN NEW;
    END IF;

    SELECT f.safety_critical INTO v_safety_critical
    FROM menu.translatable_field f
    WHERE f.entity = NEW.entity AND f.field_name = NEW.field_name;

    IF coalesce(v_safety_critical, false) AND NEW.provenance = 'machine_assisted'
       AND NEW.reviewed_by_user_id IS NULL THEN
        RAISE EXCEPTION
            'SAFETY_CRITICAL_TEXT_AUTO_APPROVED: % on % may not be approved from a machine draft without a named human reviewer',
            NEW.field_name, NEW.entity
            USING ERRCODE = 'HS403';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER translation_review_required
    BEFORE INSERT OR UPDATE ON menu.translation
    FOR EACH ROW EXECUTE FUNCTION menu.enforce_translation_review();

-- ===========================================================================
-- Images (FR-MNU-011)
-- ===========================================================================
-- Source assets are private. The row carries the storage key and the crop; it never
-- carries a URL, because a URL that could be stored is a URL that could be shared. The
-- API issues a signed, expiring, authorized URL at request time from a key held in the
-- environment — never in the database and never in source (FR-SEC-007).

CREATE TABLE menu.image (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL,
    outlet_id      uuid,
    entity         menu.menu_entity NOT NULL,
    entity_id      uuid NOT NULL,
    storage_key    text NOT NULL,
    canonical_alt_text text NOT NULL,
    focal_x        money.percentage NOT NULL DEFAULT 50,
    focal_y        money.percentage NOT NULL DEFAULT 50,
    source_width_px  integer NOT NULL,
    source_height_px integer NOT NULL,
    is_private     boolean NOT NULL DEFAULT true,
    display_order  integer NOT NULL DEFAULT 0,
    row_version    bigint NOT NULL DEFAULT 1,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT image_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT image_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT image_storage_key_not_blank CHECK (btrim(storage_key) <> ''),
    CONSTRAINT image_alt_text_not_blank CHECK (btrim(canonical_alt_text) <> ''),
    CONSTRAINT image_dimensions_positive
        CHECK (source_width_px > 0 AND source_height_px > 0),
    -- A source asset is private. There is no value of this column that publishes it.
    CONSTRAINT image_source_is_private CHECK (is_private),
    CONSTRAINT image_storage_key_unique UNIQUE (tenant_id, storage_key)
);

COMMENT ON COLUMN menu.image.focal_x IS
    'Focal point as a percentage of width, exact (money.percentage, numeric with declared '
    'scale). A crop that moved because a float drifted would be a visible defect.';

CREATE TABLE menu.image_derivative (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL,
    outlet_id    uuid,
    image_id     uuid NOT NULL,
    width_px     integer NOT NULL,
    height_px    integer NOT NULL,
    format       menu.image_format NOT NULL,
    storage_key  text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT image_derivative_image_fk FOREIGN KEY (image_id)
        REFERENCES menu.image (id) ON DELETE CASCADE,
    CONSTRAINT image_derivative_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT image_derivative_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT image_derivative_dimensions_positive CHECK (width_px > 0 AND height_px > 0),
    CONSTRAINT image_derivative_unique UNIQUE (image_id, width_px, format)
);

COMMENT ON TABLE menu.image_derivative IS
    'Responsive derivatives of a source asset (FR-MNU-011). Each is a stored object with '
    'its own key; none is public. Access to any of them goes through the same signed, '
    'expiring, authorized URL path as the source.';

-- ===========================================================================
-- Publication (FR-MNU-003, FR-I18N-006) — immutable snapshots
-- ===========================================================================
-- An order at M3 will reference a snapshot to prove what a guest was shown and what they
-- were charged. If a snapshot can be edited afterwards, that evidence is worth nothing.
-- Immutability is enforced twice over, exactly as M1-C's audit store is: the application
-- role is never granted UPDATE or DELETE, and a trigger refuses both regardless of who is
-- asking. The grant alone is not the enforcement — a role change would undo it.

CREATE TABLE menu.publication_snapshot (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL,
    outlet_id         uuid,
    menu_id           uuid NOT NULL,
    published_at      timestamptz NOT NULL DEFAULT now(),
    published_by_user_id uuid NOT NULL,
    content_digest    bytea NOT NULL,

    CONSTRAINT publication_snapshot_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT publication_snapshot_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT publication_snapshot_menu_fk FOREIGN KEY (menu_id)
        REFERENCES menu.menu (id) ON DELETE RESTRICT,
    CONSTRAINT publication_snapshot_publisher_fk FOREIGN KEY (tenant_id, published_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT publication_snapshot_digest_length CHECK (octet_length(content_digest) = 32)
);

COMMENT ON TABLE menu.publication_snapshot IS
    'An immutable record of exactly what was published, and when (FR-MNU-003). M3 orders '
    'reference it for price evidence, so it is append-only twice over: the application '
    'role holds INSERT and SELECT only, and a trigger refuses UPDATE, DELETE and TRUNCATE '
    'whoever asks. content_digest covers the lines, so a line changed by a privileged '
    'identity no longer matches the header.';

CREATE TABLE menu.publication_snapshot_line (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     uuid NOT NULL,
    outlet_id     uuid,
    snapshot_id   uuid NOT NULL,
    item_id       uuid NOT NULL,
    variant_id    uuid,
    item_code     text NOT NULL,
    canonical_name text NOT NULL,
    channel       menu.sales_channel,
    currency_code char(3) NOT NULL,
    amount_minor  money.amount_minor NOT NULL,
    tax_context   text NOT NULL,
    availability  menu.availability_state NOT NULL,

    -- Deferred to end of transaction, so the lines can be written before the header.
    -- That ordering is what lets the header carry a digest of the rows that were actually
    -- stored, rather than of a second evaluation of the same query that a concurrent edit
    -- could have moved underneath it.
    CONSTRAINT snapshot_line_snapshot_fk FOREIGN KEY (snapshot_id)
        REFERENCES menu.publication_snapshot (id) ON DELETE RESTRICT
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT snapshot_line_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT snapshot_line_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES org.org_node (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT snapshot_line_currency_fk FOREIGN KEY (currency_code)
        REFERENCES money.currency (code) ON DELETE RESTRICT
);

CREATE INDEX snapshot_line_snapshot_idx ON menu.publication_snapshot_line (snapshot_id);

CREATE FUNCTION menu.refuse_snapshot_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'IMMUTABLE_SNAPSHOT_ALTERED: a publication snapshot is append-only; % is refused on %',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'HS403';
END;
$$;

CREATE TRIGGER publication_snapshot_append_only
    BEFORE UPDATE OR DELETE ON menu.publication_snapshot
    FOR EACH ROW EXECUTE FUNCTION menu.refuse_snapshot_mutation();

CREATE TRIGGER publication_snapshot_no_truncate
    BEFORE TRUNCATE ON menu.publication_snapshot
    FOR EACH STATEMENT EXECUTE FUNCTION menu.refuse_snapshot_mutation();

CREATE TRIGGER snapshot_line_append_only
    BEFORE UPDATE OR DELETE ON menu.publication_snapshot_line
    FOR EACH ROW EXECUTE FUNCTION menu.refuse_snapshot_mutation();

CREATE TRIGGER snapshot_line_no_truncate
    BEFORE TRUNCATE ON menu.publication_snapshot_line
    FOR EACH STATEMENT EXECUTE FUNCTION menu.refuse_snapshot_mutation();

-- What is missing, before anything is published. Returns rows; an empty result is the
-- only thing that permits publication.
CREATE FUNCTION menu.missing_required_translations(p_menu_id uuid)
RETURNS TABLE (entity menu.menu_entity, entity_id uuid, field_name text,
               locale menu.customer_locale)
LANGUAGE sql STABLE
AS $$
    WITH subjects AS (
        SELECT 'menu'::menu.menu_entity AS entity, m.id, m.tenant_id
        FROM menu.menu m WHERE m.id = p_menu_id
        UNION ALL
        SELECT 'category', c.id, c.tenant_id FROM menu.category c
        WHERE c.menu_id = p_menu_id AND c.status = 'active'
        UNION ALL
        SELECT 'item_group', g.id, g.tenant_id FROM menu.item_group g
        WHERE g.menu_id = p_menu_id AND g.status = 'active'
        UNION ALL
        SELECT 'item', i.id, i.tenant_id FROM menu.sellable_item i
        WHERE i.menu_id = p_menu_id AND i.status = 'active'
        UNION ALL
        SELECT 'variant', v.id, v.tenant_id FROM menu.item_variant v
        JOIN menu.sellable_item i ON i.id = v.item_id
        WHERE i.menu_id = p_menu_id AND v.status = 'active'
    ),
    required AS (
        SELECT s.entity, s.id AS entity_id, s.tenant_id, f.field_name, l.locale
        FROM subjects s
        JOIN menu.translatable_field f ON f.entity = s.entity AND f.required_for_publication
        CROSS JOIN (SELECT unnest(enum_range(NULL::menu.customer_locale)) AS locale) l
    )
    SELECT r.entity, r.entity_id, r.field_name, r.locale
    FROM required r
    WHERE NOT EXISTS (
        SELECT 1 FROM menu.translation t
        WHERE t.tenant_id = r.tenant_id
          AND t.entity    = r.entity
          AND t.entity_id = r.entity_id
          AND t.field_name = r.field_name
          AND t.locale    = r.locale
          AND t.state     = 'approved')
    ORDER BY r.entity, r.entity_id, r.field_name, r.locale;
$$;

COMMENT ON FUNCTION menu.missing_required_translations(uuid) IS
    'Every required (field, locale) pair that has no APPROVED translation (FR-I18N-006). '
    'The locale list comes from enum_range over menu.customer_locale, so adding a fourth '
    'locale to the type extends this check automatically rather than leaving it behind.';

-- Publication. Blocked when a required locale is missing (FR-I18N-006) — the block is
-- here, in the only path that can create a snapshot, rather than in a caller that could
-- be bypassed.
CREATE FUNCTION menu.publish_menu(p_menu_id uuid, p_published_by uuid)
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

    -- The block sits here, in the only path that can create a snapshot, so it cannot be
    -- stepped around by a caller that forgot to ask (FR-I18N-006).
    SELECT count(*) INTO v_missing FROM menu.missing_required_translations(p_menu_id);
    IF v_missing > 0 THEN
        SELECT * INTO v_example FROM menu.missing_required_translations(p_menu_id) LIMIT 1;
        RAISE EXCEPTION
            'REQUIRED_TRANSLATION_MISSING: % required translation(s) absent, for example % on % in locale %',
            v_missing, v_example.field_name, v_example.entity, v_example.locale
            USING ERRCODE = 'HS422';
    END IF;

    -- Lines first, header last. The snapshot id is generated up front and the line
    -- foreign key is deferred to commit, so the digest below is taken over the rows that
    -- were actually stored rather than over a second evaluation of the same query — which
    -- a concurrent edit could have moved underneath it. No temporary table is involved:
    -- the application role is not granted TEMPORARY, and a publication path that needed
    -- a privilege the runtime does not hold would not be a publication path at all.
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

    UPDATE menu.menu SET state = 'published', row_version = row_version
    WHERE id = p_menu_id;

    RETURN v_snapshot;
END;
$$;

COMMENT ON FUNCTION menu.publish_menu(uuid, uuid) IS
    'The only path that creates a publication snapshot (FR-MNU-003, FR-I18N-006). Refuses '
    'with REQUIRED_TRANSLATION_MISSING when any required locale is absent, and writes the '
    'header last, already carrying the digest of its own lines — nothing in this function '
    'disables the append-only trigger.';

CREATE FUNCTION menu.snapshot_digest(p_snapshot_id uuid)
RETURNS bytea
LANGUAGE sql STABLE
AS $$
    SELECT sha256(convert_to(coalesce(string_agg(
               l.item_code || '|' || coalesce(l.variant_id::text, '') || '|' ||
               l.currency_code || '|' || l.amount_minor::text || '|' || l.tax_context,
               E'\n' ORDER BY l.id), ''), 'UTF8'))
    FROM menu.publication_snapshot_line l WHERE l.snapshot_id = p_snapshot_id;
$$;

COMMENT ON FUNCTION menu.snapshot_digest(uuid) IS
    'Recomputes a snapshot digest from its lines. Compared against the stored header '
    'digest, this detects a line altered by an identity privileged enough to have gone '
    'round the append-only trigger.';

-- ===========================================================================
-- Search (FR-MNU-012) — PARTIALLY CLOSED AT M2-A
-- ===========================================================================
-- Searches translated names and descriptions, and filters by category, availability,
-- price and preparation time. All four are provable here against data this gate owns.
--
-- Dietary and allergen filtering are NOT here. Their catalogue is M2-B, and building a
-- filter now against a catalogue that does not exist would produce a check that passes
-- because it examined nothing — the vacuity that money.assert_currency_paired() carried
-- through all of M1. FR-MNU-012 is therefore dual-gated, like the 39 other requirements
-- that carry a revalidation gate: M2-A closes four filters, M2-B closes the other two
-- alongside the catalogue they depend on.
--
-- Text matching is unaccented, case-folded and script-agnostic. PostgreSQL ships no
-- stemmer for Amharic or Arabic, so a stemming configuration would silently do nothing
-- for two of the three locales while appearing to work for one. Matching on normalised
-- substrings behaves identically in all three, and handles a mixed-script query — Arabic
-- prose containing a Latin item code — without a tokenizer deciding which script wins.

CREATE FUNCTION menu.normalise_for_search(p_text text)
RETURNS text
LANGUAGE sql IMMUTABLE
AS $$
    -- Arabic tatweel and the bidirectional marks a copy-paste drags in carry no meaning
    -- for matching, and would otherwise make an identical-looking query miss.
    SELECT lower(btrim(regexp_replace(coalesce(p_text, ''),
                                      '[ـ​-‏‪-‮]', '', 'g')));
$$;

CREATE INDEX translation_search_idx
    ON menu.translation (tenant_id, locale, menu.normalise_for_search(translated_text)
                         text_pattern_ops);

CREATE INDEX sellable_item_search_idx
    ON menu.sellable_item (tenant_id, menu.normalise_for_search(canonical_name)
                           text_pattern_ops);

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
    ORDER BY p.display_name;
$$;

COMMENT ON FUNCTION menu.search_items IS
    'Searches approved translated names and short descriptions in a given locale, falling '
    'back to the canonical text where no approved translation exists, and filters by '
    'category, availability, price range and preparation time (FR-MNU-012, PARTIALLY '
    'CLOSED AT M2-A). Dietary and allergen filters arrive at M2-B with the catalogue they '
    'depend on; they are absent here rather than present and vacuous.';

-- ===========================================================================
-- Row level security — ENABLE and FORCE on every tenant-scoped table
-- ===========================================================================

DO $$
DECLARE
    t record;
    -- Reference data, identical for every tenant, carrying no tenant column.
    reference_only text[] := ARRAY['translatable_field'];
BEGIN
    FOR t IN
        SELECT c.relname AS table_name
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'menu' AND c.relkind = 'r'
    LOOP
        IF t.table_name = ANY (reference_only) THEN
            CONTINUE;
        END IF;

        EXECUTE format('ALTER TABLE menu.%I ENABLE ROW LEVEL SECURITY', t.table_name);
        EXECUTE format('ALTER TABLE menu.%I FORCE  ROW LEVEL SECURITY', t.table_name);
        EXECUTE format(
            'CREATE POLICY %I ON menu.%I FOR ALL '
            'USING (app.row_in_scope(tenant_id, outlet_id)) '
            'WITH CHECK (app.row_in_scope(tenant_id, outlet_id))',
            t.table_name || '_isolation', t.table_name);
    END LOOP;
END;
$$;

-- ===========================================================================
-- Row version enforcement, where a row is edited rather than appended
-- ===========================================================================

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['menu', 'category', 'item_group', 'sellable_item',
                             'item_variant', 'modifier_group', 'modifier', 'daypart',
                             'assignment', 'price', 'availability', 'image', 'translation']
    LOOP
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE ON menu.%I '
            'FOR EACH ROW EXECUTE FUNCTION app.enforce_row_version()',
            t || '_row_version', t);
    END LOOP;
END;
$$;

-- ===========================================================================
-- Grants
-- ===========================================================================

GRANT USAGE ON SCHEMA menu TO hospitality_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    menu.menu, menu.category, menu.item_group, menu.item_group_member,
    menu.sellable_item, menu.item_variant, menu.modifier_group, menu.modifier,
    menu.item_modifier_group, menu.modifier_incompatibility, menu.daypart,
    menu.assignment, menu.price, menu.availability, menu.availability_pause,
    menu.image, menu.image_derivative, menu.translation
TO hospitality_app;

-- The field registry is reference data: read, never written by the runtime.
GRANT SELECT ON menu.translatable_field TO hospitality_app;

-- Publication snapshots are append-only for the application, exactly as audit storage is.
-- The trigger refuses mutation regardless; the grant makes the intent visible without
-- reading the trigger.
GRANT SELECT, INSERT ON menu.publication_snapshot, menu.publication_snapshot_line
TO hospitality_app;
REVOKE UPDATE, DELETE, TRUNCATE ON menu.publication_snapshot, menu.publication_snapshot_line
FROM hospitality_app;

GRANT USAGE ON ALL SEQUENCES IN SCHEMA menu TO hospitality_app;

REVOKE CREATE ON SCHEMA menu FROM hospitality_app;
