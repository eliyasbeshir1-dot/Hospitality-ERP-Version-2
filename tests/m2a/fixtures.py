"""M2-A fixtures: a small but complete menu, and an outlet that observes daylight saving.

Two things here are deliberate rather than convenient.

The DST outlet. Every seeded Phase 1 outlet sits in Africa/Addis_Ababa or Asia/Dubai, and
neither zone has ever observed daylight saving. FR-MNU-010 asks for dayparts in
outlet-local time and the brief asks for the transition to be tested "if the outlet
timezone has one" — strictly, none does, and the honest reading of that is not "so skip
it" but "so create one". This module adds an outlet in Europe/Berlin whose only purpose is
to make the spring-forward and autumn-back boundaries reachable. It lives in the M2-A
fixtures, not in the shared seeds, so no M1 assertion about seeded row counts moves.

The fixtures are loaded under the application role, through ordinary row level security.
Anything that cannot be written that way is something the application could not do either.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "m1a"))

from pg import ProbeFailed, count, run   # noqa: E402

TENANT = "33333333-3333-3333-3333-333333333333"          # HABESHA, seeded at M1-C
OUTLET_H1 = "33330001-0000-4000-8000-000000000001"       # Kazanchis, Africa/Addis_Ababa
OUTLET_H2 = "33330002-0000-4000-8000-000000000002"       # Sarbet,    Africa/Addis_Ababa
USER = "3333aaaa-0000-4000-8000-000000000001"

# The daylight-saving outlet, created here and nowhere else.
OUTLET_DST = "3333dd01-0000-4000-8000-00000000dd01"
DST_ZONE = "Europe/Berlin"

MENU = "3333e001-0000-4000-8000-0000000000e1"
CATEGORY_MAINS = "3333e002-0000-4000-8000-0000000000e2"
CATEGORY_DRINKS = "3333e003-0000-4000-8000-0000000000e3"
GROUP_CHEF = "3333e004-0000-4000-8000-0000000000e4"

ITEM_DORO = "3333f001-0000-4000-8000-0000000000f1"
ITEM_TIBS = "3333f002-0000-4000-8000-0000000000f2"
ITEM_COFFEE = "3333f003-0000-4000-8000-0000000000f3"

VARIANT_DORO_FULL = "33340001-0000-4000-8000-000000000101"
VARIANT_DORO_HALF = "33340002-0000-4000-8000-000000000102"
VARIANT_TIBS_ONE = "33340003-0000-4000-8000-000000000103"
VARIANT_COFFEE_ONE = "33340004-0000-4000-8000-000000000104"

MODGROUP_SPICE = "33350001-0000-4000-8000-000000000201"
MODIFIER_MILD = "33350002-0000-4000-8000-000000000202"
MODIFIER_HOT = "33350003-0000-4000-8000-000000000203"

DAYPART_BREAKFAST = "33360001-0000-4000-8000-000000000301"
DAYPART_LUNCH = "33360002-0000-4000-8000-000000000302"
DAYPART_LATE = "33360003-0000-4000-8000-000000000303"
DAYPART_DST = "33360004-0000-4000-8000-000000000304"

IMAGE_DORO = "33370001-0000-4000-8000-000000000401"

# Three locales, three scripts. The Arabic and Amharic strings are real words, so a
# normalisation bug that mangles non-Latin text shows up as a failed match rather than as
# a test that never exercised the path.
NAMES = {
    ITEM_DORO:   {"en": "Doro Wot", "am": "ዶሮ ወጥ", "ar": "دورو وات"},
    ITEM_TIBS:   {"en": "Tibs", "am": "ጥብስ", "ar": "طبس"},
    ITEM_COFFEE: {"en": "Buna", "am": "ቡና", "ar": "بونا"},
}
SHORT = {
    ITEM_DORO:   {"en": "Chicken stew", "am": "የዶሮ ወጥ", "ar": "يخنة الدجاج"},
    ITEM_TIBS:   {"en": "Sauteed beef", "am": "የበሬ ጥብስ", "ar": "لحم مقلي"},
    ITEM_COFFEE: {"en": "Roasted coffee", "am": "የተጠበሰ ቡና", "ar": "قهوة محمصة"},
}
INGREDIENTS = {
    ITEM_DORO:   {"en": "Chicken, berbere, onion, egg",
                  "am": "ዶሮ፣ በርበሬ፣ ሽንኩርት፣ እንቁላል",
                  "ar": "دجاج، بربري، بصل، بيض"},
    ITEM_TIBS:   {"en": "Beef, rosemary, onion, chilli",
                  "am": "የበሬ ሥጋ፣ ሮዝመሪ፣ ሽንኩርት፣ ቃሪያ",
                  "ar": "لحم بقري، إكليل الجبل، بصل، فلفل"},
    ITEM_COFFEE: {"en": "Arabica coffee beans", "am": "የአረቢካ ቡና ፍሬ",
                  "ar": "حبوب قهوة عربية"},
}

CTX = dict(tenant=TENANT, outlet=OUTLET_H1)
ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]


def reset() -> None:
    """Remove anything a previous M2-A run left, in dependency order.

    Every statement runs on its own and is checked. An earlier version ran them as one
    script and ignored the result: the menu delete failed because an immutable snapshot
    still referenced a menu, ON_ERROR_STOP abandoned the rest of the script, and the
    daylight-saving outlet survived to collide with the next run. A teardown that fails
    quietly is the same class of defect as a check that passes quietly.

    Published menus are deliberately NOT deleted. A publication snapshot is append-only
    and refuses DELETE whoever asks — that is the property NC-M2A-001 exists to protect,
    and the fixtures do not get an exemption from it. The driver rebuilds the database
    from empty on every run, so nothing accumulates across runs.
    """
    statements = [
        f"DELETE FROM menu.availability_pause       WHERE tenant_id = '{TENANT}'",
        f"DELETE FROM menu.availability             WHERE tenant_id = '{TENANT}'",
        f"DELETE FROM menu.price                    WHERE tenant_id = '{TENANT}'",
        # Scoped to the entities M2-A seeds. It used to delete every translation in the
        # tenant, which reached into rows a later slice owns: once M2-B declared allergens
        # on these items, wiping their warning text made this fixture unable to publish
        # its own menu, and the failure surfaced in M2-A rather than where it came from.
        # A teardown removes what it created.
        f"DELETE FROM menu.translation WHERE tenant_id = '{TENANT}' AND entity IN "
        f"('menu', 'category', 'item_group', 'item', 'variant', 'modifier_group', "
        f"'modifier', 'image')",
        f"DELETE FROM menu.image_derivative         WHERE tenant_id = '{TENANT}'",
        f"DELETE FROM menu.image                    WHERE tenant_id = '{TENANT}'",
        f"DELETE FROM menu.modifier_incompatibility WHERE tenant_id = '{TENANT}'",
        f"DELETE FROM menu.item_modifier_group      WHERE tenant_id = '{TENANT}'",
        f"DELETE FROM menu.modifier                 WHERE tenant_id = '{TENANT}'",
        f"DELETE FROM menu.modifier_group           WHERE tenant_id = '{TENANT}'",
        f"DELETE FROM menu.item_group_member        WHERE tenant_id = '{TENANT}'",
        f"DELETE FROM menu.assignment               WHERE tenant_id = '{TENANT}'",
        f"DELETE FROM menu.daypart                  WHERE tenant_id = '{TENANT}'",
        # The daylight-saving outlet, now that nothing in the menu schema points at it.
        # The order number series goes with it. This fixture creates the outlet, so it
        # owns everything that comes into being because the outlet does — and from 0010
        # an outlet acquires a dine_in_order series by trigger the moment it is inserted.
        # A teardown that removed only what it wrote by hand left a row behind that made
        # the outlet undeletable on the NEXT run, in a suite three slices away.
        f"DELETE FROM config.issued_document_number WHERE tenant_id = '{TENANT}' "
        f"AND outlet_id = '{OUTLET_DST}'",
        f"DELETE FROM config.number_series WHERE tenant_id = '{TENANT}' "
        f"AND outlet_id = '{OUTLET_DST}'",
        f"DELETE FROM org.outlet_profile WHERE outlet_id = '{OUTLET_DST}'",
        f"DELETE FROM org.org_closure    WHERE tenant_id = '{TENANT}' "
        f"AND (ancestor_id = '{OUTLET_DST}' OR descendant_id = '{OUTLET_DST}')",
        f"DELETE FROM org.org_node       WHERE id = '{OUTLET_DST}'",
    ]
    # Items and variants are referenced by snapshot lines, so they go only where nothing
    # published from them.
    tail = [
        f"""DELETE FROM menu.item_variant v WHERE v.tenant_id = '{TENANT}'
             AND NOT EXISTS (SELECT 1 FROM menu.publication_snapshot_line l
                             WHERE l.variant_id = v.id)""",
        f"""DELETE FROM menu.sellable_item i WHERE i.tenant_id = '{TENANT}'
             AND NOT EXISTS (SELECT 1 FROM menu.publication_snapshot_line l
                             WHERE l.item_id = i.id)""",
        f"DELETE FROM menu.item_group WHERE tenant_id = '{TENANT}'",
        # A category or a menu that a surviving published item still hangs from stays too.
        # Everything published is permanent by design; teardown removes what is not.
        f"""DELETE FROM menu.category c WHERE c.tenant_id = '{TENANT}'
             AND NOT EXISTS (SELECT 1 FROM menu.sellable_item i
                             WHERE i.category_id = c.id)""",
        f"""DELETE FROM menu.menu m WHERE m.tenant_id = '{TENANT}'
             AND NOT EXISTS (SELECT 1 FROM menu.publication_snapshot s WHERE s.menu_id = m.id)
             AND NOT EXISTS (SELECT 1 FROM menu.sellable_item i WHERE i.menu_id = m.id)
             AND NOT EXISTS (SELECT 1 FROM menu.category c WHERE c.menu_id = m.id)
             AND NOT EXISTS (SELECT 1 FROM menu.item_group g WHERE g.menu_id = m.id)""",
    ]

    failures: list[str] = []
    for statement in statements + tail:
        res = run(ADMIN, statement + ";")
        if not res.ok:
            failures.append(f"{' '.join(statement.split())[:70]} -> {res.why()}")

    survivors = count(ADMIN, f"SELECT count(*) FROM org.org_node WHERE id = '{OUTLET_DST}';")
    if survivors != 0 or failures:
        raise RuntimeError(
            "M2-A teardown did not complete; the next run would collide.\n  "
            + "\n  ".join(failures or [f"the daylight-saving outlet still exists"]))


def seed_dst_outlet() -> None:
    """An outlet in a zone that actually observes daylight saving.

    Created as the superuser because org.org_node's outlet derivation and closure
    maintenance are M1-A's, and this is fixture construction rather than a claim about
    what the application role may do. Every M2-A assertion that follows runs as the
    application role under ordinary row level security.
    """
    parent = run(ADMIN, f"""
        SELECT id::text FROM org.org_node
        WHERE tenant_id = '{TENANT}' AND kind = 'legal_entity' LIMIT 1;
    """)
    if not parent.ok or not parent.scalar:
        raise RuntimeError(f"no legal entity to hang the DST outlet from: {parent.why()}")

    created = run(ADMIN, f"""
        INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{OUTLET_DST}', '{TENANT}', '{parent.scalar}', 'outlet',
                'OUT-DST', 'Daylight Saving Branch (fixture)')
        ON CONFLICT (id) DO NOTHING;
        INSERT INTO org.outlet_profile (outlet_id, tenant_id, timezone)
        VALUES ('{OUTLET_DST}', '{TENANT}', '{DST_ZONE}')
        ON CONFLICT (outlet_id) DO UPDATE SET timezone = EXCLUDED.timezone;
    """)
    if not created.ok:
        raise RuntimeError(f"could not create the DST outlet: {created.why()}")


def _quote(value: str) -> str:
    return value.replace("'", "''")


def seed() -> None:
    """Ensure the fixture menu exists, as the application role, under row level security.

    Idempotent rather than create-only. Teardown cannot remove a menu, item, variant or
    category that a publication snapshot references, because the snapshot is append-only
    and refuses DELETE whoever asks — the property NC-M2A-001 exists to protect. The
    order-independence check re-runs this suite against the same database, so seeding has
    to tolerate finding its own structural rows already there. The menu is returned to
    'draft' so publication is testable again.
    """
    structure = run(APP, f"""
        INSERT INTO menu.menu (id, tenant_id, outlet_id, menu_code, canonical_name)
        VALUES ('{MENU}', '{TENANT}', '{OUTLET_H1}', 'ALLDAY', 'All Day Menu')
        ON CONFLICT (id) DO UPDATE SET state = 'draft', row_version = menu.menu.row_version;

        INSERT INTO menu.category (id, tenant_id, outlet_id, menu_id, category_code, canonical_name, display_order)
        VALUES ('{CATEGORY_MAINS}', '{TENANT}', '{OUTLET_H1}', '{MENU}', 'MAINS', 'Main Dishes', 1),
               ('{CATEGORY_DRINKS}', '{TENANT}', '{OUTLET_H1}', '{MENU}', 'DRINKS', 'Drinks', 2)
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO menu.item_group (id, tenant_id, outlet_id, menu_id, group_code, canonical_name)
        VALUES ('{GROUP_CHEF}', '{TENANT}', '{OUTLET_H1}', '{MENU}', 'CHEF', 'Chef Selection')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO menu.sellable_item
            (id, tenant_id, outlet_id, menu_id, category_id, item_code, canonical_name,
             canonical_short_description, canonical_long_description,
             customer_visible_ingredients, preparation_minutes, display_order)
        VALUES
          ('{ITEM_DORO}', '{TENANT}', '{OUTLET_H1}', '{MENU}', '{CATEGORY_MAINS}', 'SKU-DORO-01',
           '{_quote(NAMES[ITEM_DORO]["en"])}', '{_quote(SHORT[ITEM_DORO]["en"])}',
           'Slow cooked chicken in berbere sauce, served with injera.',
           '{_quote(INGREDIENTS[ITEM_DORO]["en"])}', 35, 1),
          ('{ITEM_TIBS}', '{TENANT}', '{OUTLET_H1}', '{MENU}', '{CATEGORY_MAINS}', 'SKU-TIBS-02',
           '{_quote(NAMES[ITEM_TIBS]["en"])}', '{_quote(SHORT[ITEM_TIBS]["en"])}',
           'Beef cubes sauteed with rosemary and onion.',
           '{_quote(INGREDIENTS[ITEM_TIBS]["en"])}', 20, 2),
          ('{ITEM_COFFEE}', '{TENANT}', '{OUTLET_H1}', '{MENU}', '{CATEGORY_DRINKS}', 'SKU-BUNA-03',
           '{_quote(NAMES[ITEM_COFFEE]["en"])}', '{_quote(SHORT[ITEM_COFFEE]["en"])}',
           'Traditional coffee, roasted and brewed to order.',
           '{_quote(INGREDIENTS[ITEM_COFFEE]["en"])}', 10, 3)
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO menu.item_group_member (tenant_id, outlet_id, item_group_id, item_id, display_order)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{GROUP_CHEF}', '{ITEM_DORO}', 1)
        ON CONFLICT (item_group_id, item_id) DO NOTHING;

        INSERT INTO menu.item_variant
            (id, tenant_id, outlet_id, item_id, axis, variant_code, canonical_name, is_default, display_order)
        VALUES
          ('{VARIANT_DORO_FULL}', '{TENANT}', '{OUTLET_H1}', '{ITEM_DORO}', 'portion', 'FULL', 'Full portion', true, 1),
          ('{VARIANT_DORO_HALF}', '{TENANT}', '{OUTLET_H1}', '{ITEM_DORO}', 'portion', 'HALF', 'Half portion', false, 2),
          ('{VARIANT_TIBS_ONE}', '{TENANT}', '{OUTLET_H1}', '{ITEM_TIBS}', 'portion', 'STD', 'Standard', true, 1),
          ('{VARIANT_COFFEE_ONE}', '{TENANT}', '{OUTLET_H1}', '{ITEM_COFFEE}', 'size', 'CUP', 'Single cup', true, 1)
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO menu.modifier_group
            (id, tenant_id, outlet_id, group_code, canonical_name, is_required,
             min_selections, max_selections, included_selections)
        VALUES ('{MODGROUP_SPICE}', '{TENANT}', '{OUTLET_H1}', 'SPICE', 'Spice level', true, 1, 1, 1)
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO menu.modifier
            (id, tenant_id, outlet_id, modifier_group_id, modifier_code, canonical_name, is_default, display_order)
        VALUES ('{MODIFIER_MILD}', '{TENANT}', '{OUTLET_H1}', '{MODGROUP_SPICE}', 'MILD', 'Mild', true, 1),
               ('{MODIFIER_HOT}', '{TENANT}', '{OUTLET_H1}', '{MODGROUP_SPICE}', 'HOT', 'Extra hot', false, 2)
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO menu.item_modifier_group (tenant_id, outlet_id, item_id, modifier_group_id)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{ITEM_DORO}', '{MODGROUP_SPICE}')
        ON CONFLICT (item_id, modifier_group_id) DO NOTHING;

        INSERT INTO menu.modifier_incompatibility (tenant_id, outlet_id, modifier_id, incompatible_with_id)
        SELECT '{TENANT}', '{OUTLET_H1}',
               least('{MODIFIER_MILD}'::uuid, '{MODIFIER_HOT}'::uuid),
               greatest('{MODIFIER_MILD}'::uuid, '{MODIFIER_HOT}'::uuid)
        ON CONFLICT (modifier_id, incompatible_with_id) DO NOTHING;
    """, **CTX)
    if not structure.ok:
        raise RuntimeError(f"menu structure fixture failed: {structure.why()}")

    prices = run(APP, f"""
        INSERT INTO menu.price
            (tenant_id, outlet_id, variant_id, channel, currency_code, amount_minor, tax_context)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{VARIANT_DORO_FULL}', NULL, 'ETB', 32000, 'standard'),
               ('{TENANT}', '{OUTLET_H1}', '{VARIANT_DORO_HALF}', NULL, 'ETB', 18000, 'standard'),
               ('{TENANT}', '{OUTLET_H1}', '{VARIANT_TIBS_ONE}',  NULL, 'ETB', 26000, 'standard'),
               ('{TENANT}', '{OUTLET_H1}', '{VARIANT_COFFEE_ONE}', NULL, 'ETB', 4500, 'standard'),
               -- A channel-specific price, so precedence has something to resolve.
               ('{TENANT}', '{OUTLET_H1}', '{VARIANT_DORO_FULL}', 'room_service', 'ETB', 36000, 'standard');

        INSERT INTO menu.availability (tenant_id, outlet_id, variant_id, state)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{VARIANT_DORO_FULL}', 'available'),
               ('{TENANT}', '{OUTLET_H1}', '{VARIANT_DORO_HALF}', 'limited'),
               ('{TENANT}', '{OUTLET_H1}', '{VARIANT_TIBS_ONE}', 'available'),
               ('{TENANT}', '{OUTLET_H1}', '{VARIANT_COFFEE_ONE}', 'available');

        INSERT INTO menu.daypart
            (id, tenant_id, outlet_id, daypart_code, canonical_name, starts_at_local, ends_at_local)
        VALUES ('{DAYPART_BREAKFAST}', '{TENANT}', '{OUTLET_H1}', 'BREAKFAST', 'Breakfast', '06:00', '11:00'),
               ('{DAYPART_LUNCH}', '{TENANT}', '{OUTLET_H1}', 'LUNCH', 'Lunch', '11:00', '16:00'),
               ('{DAYPART_LATE}', '{TENANT}', '{OUTLET_H1}', 'LATE', 'Late night', '22:00', '02:00');

        INSERT INTO menu.assignment
            (tenant_id, outlet_id, menu_id, channel, daypart_id, effective_from)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{MENU}', 'dine_in', '{DAYPART_LUNCH}', DATE '2026-01-01');

        INSERT INTO menu.image
            (id, tenant_id, outlet_id, entity, entity_id, storage_key, canonical_alt_text,
             focal_x, focal_y, source_width_px, source_height_px)
        VALUES ('{IMAGE_DORO}', '{TENANT}', '{OUTLET_H1}', 'item', '{ITEM_DORO}',
                'menu/{TENANT}/doro-source.avif', 'A bowl of chicken stew on injera',
                55.0, 40.0, 3000, 2000)
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO menu.image_derivative
            (tenant_id, outlet_id, image_id, width_px, height_px, format, storage_key)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{IMAGE_DORO}', 320, 213, 'webp', 'menu/{TENANT}/doro-320.webp'),
               ('{TENANT}', '{OUTLET_H1}', '{IMAGE_DORO}', 1280, 853, 'webp', 'menu/{TENANT}/doro-1280.webp'),
               ('{TENANT}', '{OUTLET_H1}', '{IMAGE_DORO}', 1280, 853, 'avif', 'menu/{TENANT}/doro-1280.avif')
        ON CONFLICT (image_id, width_px, format) DO NOTHING;
    """, **CTX)
    if not prices.ok:
        raise RuntimeError(f"pricing fixture failed: {prices.why()}")

    dst = run(APP, f"""
        INSERT INTO menu.daypart
            (id, tenant_id, outlet_id, daypart_code, canonical_name, starts_at_local, ends_at_local)
        VALUES ('{DAYPART_DST}', '{TENANT}', '{OUTLET_DST}', 'BREAKFAST', 'Breakfast', '06:00', '11:00');
    """, tenant=TENANT, outlet=OUTLET_DST)
    if not dst.ok:
        raise RuntimeError(f"daylight-saving daypart fixture failed: {dst.why()}")


def translate(locales=("en", "am", "ar"), *, include_ingredients: bool = True,
              approve: bool = True) -> None:
    """Store translations for the required fields.

    Split out from seed() because publication blocking is only testable when a locale can
    be made genuinely absent — so the suite seeds a subset first, proves publication is
    refused, then completes the set and proves it is allowed.
    """
    rows: list[str] = []
    state = "'approved'" if approve else "'draft'"
    reviewer = f"'{USER}'" if approve else "NULL"
    approved_at = "now()" if approve else "NULL"

    for item in (ITEM_DORO, ITEM_TIBS, ITEM_COFFEE):
        for locale in locales:
            rows.append(f"('{TENANT}', '{OUTLET_H1}', 'item', '{item}', 'canonical_name', "
                        f"'{locale}', '{_quote(NAMES[item][locale])}', {state}, 'human', NULL, "
                        f"'{USER}', {reviewer}, {approved_at})")
            rows.append(f"('{TENANT}', '{OUTLET_H1}', 'item', '{item}', "
                        f"'canonical_short_description', '{locale}', "
                        f"'{_quote(SHORT[item][locale])}', {state}, 'human', NULL, '{USER}', "
                        f"{reviewer}, {approved_at})")
            if include_ingredients:
                rows.append(f"('{TENANT}', '{OUTLET_H1}', 'item', '{item}', "
                            f"'customer_visible_ingredients', '{locale}', "
                            f"'{_quote(INGREDIENTS[item][locale])}', {state}, 'human', NULL, "
                            f"'{USER}', {reviewer}, {approved_at})")

    # Everything else a publish needs: menu, categories, groups, variants, modifiers.
    for entity, ident, name in (
        ("menu", MENU, "All Day Menu"),
        ("category", CATEGORY_MAINS, "Main Dishes"),
        ("category", CATEGORY_DRINKS, "Drinks"),
        ("item_group", GROUP_CHEF, "Chef Selection"),
        ("variant", VARIANT_DORO_FULL, "Full portion"),
        ("variant", VARIANT_DORO_HALF, "Half portion"),
        ("variant", VARIANT_TIBS_ONE, "Standard"),
        ("variant", VARIANT_COFFEE_ONE, "Single cup"),
    ):
        for locale in locales:
            rows.append(f"('{TENANT}', '{OUTLET_H1}', '{entity}', '{ident}', "
                        f"'canonical_name', '{locale}', '{_quote(name)} [{locale}]', {state}, "
                        f"'human', NULL, '{USER}', {reviewer}, {approved_at})")

    inserted = run(APP, f"""
        INSERT INTO menu.translation
            (tenant_id, outlet_id, entity, entity_id, field_name, locale, translated_text,
             state, provenance, machine_engine, translated_by_user_id, reviewed_by_user_id,
             approved_at)
        VALUES {", ".join(rows)}
        ON CONFLICT (tenant_id, entity, entity_id, field_name, locale) DO UPDATE
            SET translated_text = EXCLUDED.translated_text,
                state = EXCLUDED.state,
                reviewed_by_user_id = EXCLUDED.reviewed_by_user_id,
                approved_at = EXCLUDED.approved_at,
                row_version = menu.translation.row_version;
    """, **CTX)
    if not inserted.ok:
        raise RuntimeError(f"translation fixture failed: {inserted.why()}")


def build(locales=("en", "am")) -> None:
    """Full fixture construction: DST outlet, menu, prices, and a PARTIAL locale set."""
    reset()
    seed_dst_outlet()
    seed()
    translate(locales=locales)
