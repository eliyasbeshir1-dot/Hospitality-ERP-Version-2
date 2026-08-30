"""M2-B fixtures: a table service floor, and a menu that declares what is in it.

Built on the M2-A menu rather than beside it. An allergen declaration is a statement
about an item, and a dietary claim is a statement about a variant, so the safety catalog
has nothing to describe until the menu it describes exists. This module calls the M2-A
fixtures first and then adds:

  * an allergen catalog for the pilot jurisdiction, with warning text in all three locales
  * declarations in all three classes, arranged so a modifier changes the answer
  * dietary claims including fasting, which is a first-class claim in this market
  * a service area, two dining tables, their QR codes, and an occupancy on one of them

Two declarations are deliberately arranged to make change detection provable: the base
dish declares no sesame at all, and the 'Extra hot' modifier CONTAINS it. Choosing that
modifier has to change what a guest is told, and no stored value anywhere is permitted to
remember the old answer.

Everything is written through the application role under ordinary row level security.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "m1a"))

from pg import count, run                    # noqa: E402

# The M2-A fixtures are loaded by path, under a name of their own.
#
# tests/m2a/fixtures.py and this file are both called "fixtures", so a plain import
# resolves to whichever directory sits earlier on sys.path — and inside this module,
# "fixtures" is already half-imported, so `import fixtures` would hand back this very
# module rather than M2-A's. Naming the file explicitly removes the ambiguity instead of
# depending on an ordering that the next suite would silently change.
import importlib.util                        # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "m2a_fixtures", HERE.parent / "m2a" / "fixtures.py")
m2a = importlib.util.module_from_spec(_spec)
sys.modules["m2a_fixtures"] = m2a
_spec.loader.exec_module(m2a)

TENANT = m2a.TENANT
OUTLET_H1 = m2a.OUTLET_H1
OUTLET_H2 = m2a.OUTLET_H2
USER = m2a.USER
CTX = dict(tenant=TENANT, outlet=OUTLET_H1)
ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]

# A second staff identity, so a handover has somebody to hand over to and a supervisor
# who is not either of them.
USER_WAITER_B = "3333aaaa-0000-4000-8000-000000000002"
USER_SUPERVISOR = "3333aaaa-0000-4000-8000-000000000003"

# The service areas already exist: M1-A seeded SA-H1-MAIN and SA-H2-MAIN as org nodes.
# Tables hang under them rather than under a parallel hierarchy this slice invents.
SERVICE_AREA_PARENT = "33331101-0000-4000-8000-000000000001"   # SA-H1-MAIN
SIBLING_AREA = "33332101-0000-4000-8000-000000000002"          # SA-H2-MAIN
TABLE_ONE = "3333b002-0000-4000-8000-0000000b0002"
TABLE_TWO = "3333b003-0000-4000-8000-0000000b0003"

# A table in the sibling outlet. NC-M2-002 needs a code that is genuinely foreign rather
# than merely wrong.
TABLE_SIBLING = "3333b004-0000-4000-8000-0000000b0004"

ALLERGEN_GLUTEN = "3333c001-0000-4000-8000-0000000c0001"
ALLERGEN_PEANUTS = "3333c002-0000-4000-8000-0000000c0002"
ALLERGEN_SESAME = "3333c003-0000-4000-8000-0000000c0003"
ALLERGEN_MILK = "3333c004-0000-4000-8000-0000000c0004"

CLAIM_VEGAN = "3333c101-0000-4000-8000-0000000c0101"
CLAIM_FASTING = "3333c102-0000-4000-8000-0000000c0102"
CLAIM_HALAL = "3333c103-0000-4000-8000-0000000c0103"

WORDING_ACK = "3333c201-0000-4000-8000-0000000c0201"

GUEST_ONE = "3333d001-0000-4000-8000-0000000d0001"
GUEST_TWO = "3333d002-0000-4000-8000-0000000d0002"
GUEST_STALE = "3333d003-0000-4000-8000-0000000d0003"

# Warning text in three scripts. Real words, so a locale that silently falls back to
# English is visible as English rather than as a plausible-looking placeholder.
WARNINGS = {
    ALLERGEN_GLUTEN:  {"en": "Contains gluten",  "am": "ግሉተን ይዟል",   "ar": "يحتوي على الغلوتين"},
    ALLERGEN_PEANUTS: {"en": "Contains peanuts", "am": "ኦቾሎኒ ይዟል",   "ar": "يحتوي على الفول السوداني"},
    ALLERGEN_SESAME:  {"en": "Contains sesame",  "am": "ሰሊጥ ይዟል",    "ar": "يحتوي على السمسم"},
    ALLERGEN_MILK:    {"en": "Contains milk",    "am": "ወተት ይዟል",    "ar": "يحتوي على الحليب"},
}

CLAIM_LABELS = {
    CLAIM_VEGAN:   {"en": "Vegan",   "am": "ቪጋን",   "ar": "نباتي صرف"},
    CLAIM_FASTING: {"en": "Fasting", "am": "የጾም",   "ar": "صيامي"},
    CLAIM_HALAL:   {"en": "Halal",   "am": "ሐላል",   "ar": "حلال"},
}

KITCHEN_CODES = {
    ALLERGEN_GLUTEN: "GLUTEN",
    ALLERGEN_PEANUTS: "PEANUTS",
    ALLERGEN_SESAME: "SESAME",
    ALLERGEN_MILK: "MILK",
}

ICONS = {
    ALLERGEN_GLUTEN: "icon/allergen/gluten",
    ALLERGEN_PEANUTS: "icon/allergen/peanut",
    ALLERGEN_SESAME: "icon/allergen/sesame",
    ALLERGEN_MILK: "icon/allergen/milk",
}

# Populated by seed(): the plaintext codes, which exist nowhere else. The database keeps
# only their hashes, so a test that needs to present a code has to hold the value it was
# given at issue.
TOKENS: dict[str, str] = {}


def _quote(value: str) -> str:
    return value.replace("'", "''")


def seed() -> None:
    """Build the M2-B floor and catalog on top of the M2-A menu.

    Idempotent for the same reason M2-A's is: the order-independence check re-runs every
    suite against one database, and rows referenced by an append-only snapshot cannot be
    removed to make way for a second attempt.
    """
    # build() rather than seed(): it is M2-A's own entry point and it resets first, so a
    # second run in one database starts from the same place the first did. All three
    # locales, because M2-B needs a complete menu before it can test what an INCOMPLETE
    # safety catalog does to publication — the missing locale has to be a safety one.
    m2a.build(locales=("en", "am", "ar"))

    staff = run(APP, f"""
        INSERT INTO identity.user_account (id, tenant_id, staff_number, display_name)
        VALUES ('{USER_WAITER_B}', '{TENANT}', 'W-002', 'Second Waiter'),
               ('{USER_SUPERVISOR}', '{TENANT}', 'S-001', 'Floor Supervisor')
        ON CONFLICT (id) DO NOTHING;
    """, **CTX)
    if not staff.ok:
        raise RuntimeError(f"staff fixture failed: {staff.why()}")

    floor = run(APP, f"""
        INSERT INTO org.org_node (id, tenant_id, parent_id, outlet_id, kind, reference_code, display_name)
        VALUES ('{TABLE_ONE}', '{TENANT}', '{SERVICE_AREA_PARENT}', '{OUTLET_H1}',
                'dining_table', 'T-01', 'Table 1'),
               ('{TABLE_TWO}', '{TENANT}', '{SERVICE_AREA_PARENT}', '{OUTLET_H1}',
                'dining_table', 'T-02', 'Table 2')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO service.table_profile
            (tenant_id, table_node_id, outlet_id, service_area_id, seat_count)
        VALUES ('{TENANT}', '{TABLE_ONE}', '{OUTLET_H1}', '{SERVICE_AREA_PARENT}', 4),
               ('{TENANT}', '{TABLE_TWO}', '{OUTLET_H1}', '{SERVICE_AREA_PARENT}', 2)
        ON CONFLICT (table_node_id) DO NOTHING;

        -- The tenant accepts two of the three methods. NC 'stale session admitted' sweeps
        -- every configured method and requires a refusal under each, so the set has to
        -- have more than one member for the sweep to mean anything.
        INSERT INTO service.verification_policy (tenant_id, accepted_methods)
        VALUES ('{TENANT}', ARRAY['staff_confirmation', 'table_code']::service.verification_method[])
        ON CONFLICT (tenant_id) DO UPDATE
            SET accepted_methods = EXCLUDED.accepted_methods;

        INSERT INTO service.guest_session (id, tenant_id, outlet_id, display_nickname, locale, expires_at)
        VALUES ('{GUEST_ONE}',   '{TENANT}', '{OUTLET_H1}', 'Guest A', 'en', now() + interval '4 hours'),
               ('{GUEST_TWO}',   '{TENANT}', '{OUTLET_H1}', 'Guest B', 'am', now() + interval '4 hours'),
               ('{GUEST_STALE}', '{TENANT}', '{OUTLET_H1}', 'Passer by', 'en', now() + interval '4 hours')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO safety.approved_wording
            (id, tenant_id, outlet_id, purpose, locale, wording, approved_by_user_id)
        VALUES ('{WORDING_ACK}', '{TENANT}', '{OUTLET_H1}', 'allergy_acknowledgement', 'en',
                'We have recorded your allergy and told the kitchen. We take care to '
                'avoid this ingredient, and we cannot rule out cross-contact in a '
                'shared kitchen.', '{USER}')
        ON CONFLICT (id) DO NOTHING;
    """, **CTX)
    if not floor.ok:
        raise RuntimeError(f"floor fixture failed: {floor.why()}")

    sibling = run(APP, f"""
        INSERT INTO org.org_node (id, tenant_id, parent_id, outlet_id, kind, reference_code, display_name)
        VALUES ('{TABLE_SIBLING}', '{TENANT}', '{SIBLING_AREA}', '{OUTLET_H2}',
                'dining_table', 'T-H2-01', 'Sibling Table 1')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO service.table_profile
            (tenant_id, table_node_id, outlet_id, service_area_id, seat_count)
        VALUES ('{TENANT}', '{TABLE_SIBLING}', '{OUTLET_H2}', '{SIBLING_AREA}', 4)
        ON CONFLICT (table_node_id) DO NOTHING;
    """, tenant=TENANT, outlet=OUTLET_H2)
    if not sibling.ok:
        raise RuntimeError(f"sibling table fixture failed: {sibling.why()}")

    _seed_catalog()
    _seed_declarations()
    _issue_tokens()


def _seed_catalog() -> None:
    allergen_rows = ", ".join(
        f"('{a}', '{TENANT}', '{OUTLET_H1}', 'ET', '{KITCHEN_CODES[a]}', '{ICONS[a]}')"
        for a in (ALLERGEN_GLUTEN, ALLERGEN_PEANUTS, ALLERGEN_SESAME, ALLERGEN_MILK))

    claim_rows = ", ".join(
        f"('{c}', '{TENANT}', '{OUTLET_H1}', '{code}', '{_quote(definition)}', "
        f"'{USER}', DATE '2027-01-01')"
        for c, code, definition in (
            (CLAIM_VEGAN, 'VEGAN',
             'No animal product of any kind, including dairy, egg and honey.'),
            (CLAIM_FASTING, 'FASTING',
             'Prepared to Ethiopian Orthodox fasting rules: no meat, dairy or egg, and '
             'cooked in oil rather than butter.'),
            (CLAIM_HALAL, 'HALAL',
             'Meat certified halal at source, with no pork or alcohol in '
             'preparation.')))

    catalog = run(APP, f"""
        INSERT INTO safety.allergen
            (id, tenant_id, outlet_id, jurisdiction_code, kitchen_code, icon_key)
        VALUES {allergen_rows}
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO safety.dietary_claim
            (id, tenant_id, outlet_id, code, definition, evidence_owner_user_id, review_due_on)
        VALUES {claim_rows}
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO safety.dietary_claim_outlet (tenant_id, claim_id, outlet_id)
        VALUES ('{TENANT}', '{CLAIM_VEGAN}', '{OUTLET_H1}'),
               ('{TENANT}', '{CLAIM_FASTING}', '{OUTLET_H1}'),
               ('{TENANT}', '{CLAIM_HALAL}', '{OUTLET_H1}')
        ON CONFLICT (claim_id, outlet_id) DO NOTHING;
    """, **CTX)
    if not catalog.ok:
        raise RuntimeError(f"catalog fixture failed: {catalog.why()}")


def translate_safety(locales=("en", "am", "ar"), *, approve: bool = True,
                     skip: tuple = ()) -> None:
    """Store the customer-facing safety text.

    Separate from the catalog for the same reason M2-A separated its translations: the
    publication block is only testable when a locale can be made genuinely absent, so the
    suite seeds a subset, proves publication is refused, then completes it.
    """
    state = "'approved'" if approve else "'draft'"
    reviewer = f"'{USER}'" if approve else "NULL"
    approved_at = "now()" if approve else "NULL"
    rows: list[str] = []

    for allergen, texts in WARNINGS.items():
        for locale in locales:
            if (allergen, locale) in skip:
                continue
            rows.append(
                f"('{TENANT}', '{OUTLET_H1}', 'allergen', '{allergen}', "
                f"'customer_warning_text', '{locale}', '{_quote(texts[locale])}', "
                f"{state}, 'human', NULL, {reviewer}, {approved_at})")

    for claim, texts in CLAIM_LABELS.items():
        for locale in locales:
            if (claim, locale) in skip:
                continue
            rows.append(
                f"('{TENANT}', '{OUTLET_H1}', 'dietary_claim', '{claim}', "
                f"'customer_label', '{locale}', '{_quote(texts[locale])}', "
                f"{state}, 'human', NULL, {reviewer}, {approved_at})")

    if not rows:
        return

    stored = run(APP, f"""
        INSERT INTO menu.translation
            (tenant_id, outlet_id, entity, entity_id, field_name, locale, translated_text,
             state, provenance, machine_engine, reviewed_by_user_id, approved_at)
        VALUES {", ".join(rows)}
        ON CONFLICT (tenant_id, entity, entity_id, field_name, locale) DO UPDATE
            SET translated_text = EXCLUDED.translated_text,
                state = EXCLUDED.state,
                reviewed_by_user_id = EXCLUDED.reviewed_by_user_id,
                approved_at = EXCLUDED.approved_at,
                row_version = menu.translation.row_version;
    """, **CTX)
    if not stored.ok:
        raise RuntimeError(f"safety translation fixture failed: {stored.why()}")


def _seed_declarations(*, approve: bool = True) -> None:
    """Declarations arranged so a modifier changes the answer.

    The base dish carries gluten and an uncertainty about peanuts. Sesame appears ONLY on
    the 'Extra hot' modifier, so a selection that includes it must gain an allergen that
    the plain dish does not have — and the moment that modifier's declaration is
    corrected, every read has to move with it. No fixture stores the resolved answer.
    """
    state = "'approved'" if approve else "'draft'"
    reviewer = f"'{USER}'" if approve else "NULL"
    reviewed_at = "now()" if approve else "NULL"

    rows = [
        ("item", m2a.ITEM_DORO, ALLERGEN_GLUTEN, "contains"),
        ("item", m2a.ITEM_DORO, ALLERGEN_PEANUTS, "may_contain"),
        ("modifier", m2a.MODIFIER_HOT, ALLERGEN_SESAME, "contains"),
        ("item", m2a.ITEM_COFFEE, ALLERGEN_MILK, "cross_contact"),
        ("item", m2a.ITEM_TIBS, ALLERGEN_GLUTEN, "cross_contact"),
    ]
    values = ", ".join(
        f"('{TENANT}', '{OUTLET_H1}', '{subject}', '{subject_id}', '{allergen}', "
        f"'{klass}', '{USER}', {state}, {reviewer}, {reviewed_at})"
        for subject, subject_id, allergen, klass in rows)

    claims = [
        ("item", m2a.ITEM_COFFEE, CLAIM_VEGAN),
        ("item", m2a.ITEM_COFFEE, CLAIM_FASTING),
        ("item", m2a.ITEM_TIBS, CLAIM_HALAL),
    ]
    claim_values = ", ".join(
        f"('{TENANT}', '{OUTLET_H1}', '{subject}', '{subject_id}', '{claim}', "
        f"'{USER}', {state}, {reviewer}, {reviewed_at})"
        for subject, subject_id, claim in claims)

    # Close whatever a previous run left open on these subjects before writing the
    # baseline. Closing rather than deleting, because safety.declaration_reference pins
    # declarations at publication with ON DELETE RESTRICT — and because the history of
    # what was declared is the point of versioning it. Without this the suite is
    # order-dependent: a second run finds peanuts already corrected to 'contains' and the
    # change-detection check compares a value to itself.
    subjects = ", ".join(
        f"('{s}'::menu.menu_entity, '{i}'::uuid)"
        for s, i, _, _ in rows)
    reset_open = run(APP, f"""
        UPDATE safety.declaration SET effective_to = now()
        WHERE tenant_id = '{TENANT}' AND effective_to IS NULL
          AND (subject, subject_id) IN ({subjects});
        UPDATE safety.item_dietary_claim SET effective_to = now()
        WHERE tenant_id = '{TENANT}' AND effective_to IS NULL;
    """, **CTX)
    if not reset_open.ok:
        raise RuntimeError(f"could not close previous declarations: {reset_open.why()}")

    stored = run(APP, f"""
        INSERT INTO safety.declaration
            (tenant_id, outlet_id, subject, subject_id, allergen_id, declaration_class,
             created_by_user_id, review_state, reviewed_by_user_id, reviewed_at)
        VALUES {values}
        ON CONFLICT (tenant_id, subject, subject_id, allergen_id)
            WHERE effective_to IS NULL DO NOTHING;

        INSERT INTO safety.item_dietary_claim
            (tenant_id, outlet_id, subject, subject_id, claim_id,
             created_by_user_id, review_state, reviewed_by_user_id, reviewed_at)
        VALUES {claim_values}
        ON CONFLICT (tenant_id, subject, subject_id, claim_id)
            WHERE effective_to IS NULL DO NOTHING;
    """, **CTX)
    if not stored.ok:
        raise RuntimeError(f"declaration fixture failed: {stored.why()}")


def _issue_tokens() -> None:
    """Issue a QR code for each table, keeping the plaintext the database does not.

    issue_table_qr() rotates on every call, so calling it twice would revoke the code the
    first call returned. The tokens are issued only when a table has none, which keeps the
    fixture idempotent across a re-run.
    """
    for label, table, outlet in (("one", TABLE_ONE, OUTLET_H1),
                                 ("two", TABLE_TWO, OUTLET_H1),
                                 ("sibling", TABLE_SIBLING, OUTLET_H2)):
        if label in TOKENS:
            continue
        existing = count(APP, f"""
            SELECT count(*) FROM service.table_qr_token
            WHERE table_node_id = '{table}' AND revoked_at IS NULL;
        """, tenant=TENANT, outlet=outlet)
        if existing:
            # A previous run in this database issued a code whose plaintext nobody kept.
            # Rotating is the only way back to a usable one, and is exactly what an
            # operator would do having lost a placard.
            run(APP, f"""
                UPDATE service.table_qr_token SET revoked_at = now(),
                       revoked_by_user_id = '{USER}'
                WHERE table_node_id = '{table}' AND revoked_at IS NULL;
            """, tenant=TENANT, outlet=outlet)

        issued = run(APP, f"""
            SELECT service.issue_table_qr('{TENANT}', '{table}', '{USER}');
        """, tenant=TENANT, outlet=outlet)
        if not issued.ok or not (issued.scalar or "").strip():
            raise RuntimeError(f"QR issue fixture failed for {label}: {issued.why()}")
        TOKENS[label] = issued.scalar.strip()


def open_occupancy(table: str = TABLE_ONE, *, source: str = "staff") -> str:
    """Open a fresh occupancy on a table, closing whatever was open.

    Returns the session id. The occupancy number increments, which is the whole mechanism
    the stale-QR guarantee rests on.
    """
    run(APP, f"""
        UPDATE service.table_session SET state = 'closed', closed_at = now()
        WHERE table_node_id = '{table}' AND state = 'open';
    """, **CTX)
    host = "NULL" if source == "qr_scan" else f"'{USER}'"
    opened = run(APP, f"""
        INSERT INTO service.table_session
            (tenant_id, outlet_id, table_node_id, occupancy_number, opening_source,
             host_staff_user_id)
        SELECT '{TENANT}', '{OUTLET_H1}', '{table}',
               coalesce(max(occupancy_number), 0) + 1, '{source}', {host}
        FROM service.table_session WHERE table_node_id = '{table}'
        RETURNING id;
    """, **CTX)
    if not opened.ok or not (opened.scalar or "").strip():
        raise RuntimeError(f"could not open an occupancy: {opened.why()}")
    return opened.scalar.strip()
