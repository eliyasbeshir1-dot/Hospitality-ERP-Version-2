"""M4-A fixtures: what a bill is calculated from, and what a tip may be chosen from.

Built on M3-D's, which is built on M3-C's, and so on down to M1-A. Everything that is
configuration arrives as configuration — approved, versioned, written by an administrator
— because a bill computed from a value the fixture invented would prove the arithmetic
and nothing about where the numbers come from.

What this module adds that no earlier slice needed:

  * A SERVICE CHARGE SETTING, pointing at an approved config.configuration_version of
    category 'service'. This is FR-CFG-001C, and it is the configured source the 'fee'
    charge kind has never had. Written as the administrator, because the application role
    holds SELECT on billing.service_charge_setting and nothing more: deciding a service
    charge is a configuration act.
  * TIP SETTINGS AND SUGGESTIONS, which between them cannot express a default. There is
    no column for one. The fixture could not preselect a tip if it wanted to, which is
    NC-M4-001's structural half stated as a fact about the schema rather than a habit of
    the seeder.
  * COMPONENT WORDING, with Amharic and Arabic approved through menu.translation by a
    named reviewer — the store M2-A governs, not a second one. FR-BIL-007 asks for a
    TRANSLATED bill summary, and an unreviewed sentence on a bill is the last place this
    system should tolerate one.
  * A COUNTER SERVICE POINT: an org node a party stands at rather than sits at, with a
    table profile, so a counter order is an order on the same aggregate rather than a
    second path that agrees with the first (FR-ORD-001B).

Deliberately NOT here: an ordering policy naming the counter. That lives in M3-A's
fixture with the rest of the acceptance block, because there is one policy per outlet and
adding a second version would leave two in force — which M3-A's own "an outlet with no
ordering policy in force accepts no order at all" check would then fail. The reason is
recorded there.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "m1a"))

from pg import run  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "m3d_fixtures", HERE.parent / "m3d" / "fixtures.py")
m3d = importlib.util.module_from_spec(_spec)
sys.modules["m3d_fixtures"] = m3d
_spec.loader.exec_module(m3d)

m3c, m3b, m3a, m2c, m2b, m2a = m3d.m3c, m3d.m3b, m3d.m3a, m3d.m2c, m3d.m2b, m3d.m2a

TENANT = m3d.TENANT
OUTLET_H1 = m3d.OUTLET_H1
OUTLET_H2 = m3d.OUTLET_H2
USER = m3d.USER
USER_MANAGER = m3d.USER_MANAGER
USER_WAITER_TWO = m3d.USER_WAITER_TWO
TABLE_ONE = m3d.TABLE_ONE
TABLE_TWO = m3d.TABLE_TWO

ITEM_DORO = m2a.ITEM_DORO
ITEM_TIBS = m2a.ITEM_TIBS
ITEM_COFFEE = m2a.ITEM_COFFEE
VARIANT_DORO_FULL = m2a.VARIANT_DORO_FULL      # 32000 minor
VARIANT_DORO_HALF = m2a.VARIANT_DORO_HALF      # 18000 minor
VARIANT_TIBS_ONE = m2a.VARIANT_TIBS_ONE        # 26000 minor
VARIANT_COFFEE_ONE = m2a.VARIANT_COFFEE_ONE    #  4500 minor

CTX = dict(tenant=TENANT, outlet=OUTLET_H1)
APP = os.environ["M1A_APP_DSN"]
ADMIN = os.environ["M1A_ADMIN_DSN"]

SERVICE_CONFIG_VERSION = "3333e401-0000-4000-8000-0000000e0401"
COUNTER_NODE = "3333e402-0000-4000-8000-0000000e0402"
ROLE_CASHIER_MANAGER = "3333e403-0000-4000-8000-0000000e0403"
USER_CASHIER_MANAGER = "3333e404-0000-4000-8000-0000000e0404"
MEMBERSHIP_CASHIER_MANAGER = "3333e405-0000-4000-8000-0000000e0405"

# TWO TABLES THIS SLICE OWNS OUTRIGHT, and the reason is a defect this suite hit on its
# first run. fresh_occupancy() CLOSES whatever occupancy is sitting on a table before it
# opens a new one, and pos.table_view(), the guest surface and every QR code resolve
# against the OPEN occupancy. So a check built on a shared table stops being reachable
# the moment a later fixture wants the same table, and the failure looks like a browser
# timing out rather than like a table being cleared underneath it.
# ONE TABLE PER LOCALE for the rendered bill, because a bill is TRANSLATED BY ITS OWN
# LOCALE and not by the reader's. That is 0017's ruling about the customer timeline
# applied to the document: a party that switches the table's language later has not
# retroactively ordered in the new one, and the bill they are handed is the one their
# order was priced and placed in. So proving the summary renders in three languages
# means three orders placed in three languages, not one bill read three ways.
BILL_TABLES = {
    "en": "3333e406-0000-4000-8000-0000000e0406",
    "am": "3333e408-0000-4000-8000-0000000e0408",
    "ar": "3333e409-0000-4000-8000-0000000e0409",
}
TIP_TABLE = "3333e407-0000-4000-8000-0000000e0407"    # the tip the API route writes

# The two governed actions a bill correction goes through. Both were registered by M1-B
# and neither has ever been used: check.void is FR-BIL-009's authority and discount.high
# is what a comp actually is — money given away, which is a discount of a hundred percent
# by another name.
CASHIER_MANAGER_ACTIONS = ("check.void", "discount.high")

# The numbers a bill is made of, stated once here and derived everywhere else. The suite
# recomputes every expected figure from these rather than hardcoding a total, so a change
# to the configuration moves the expectation with it instead of turning the suite red for
# a reason that is not a defect.
TAX_PERCENTAGE = 15          # M3-A's, unchanged
DISCOUNT_PERCENTAGE = 10     # M3-A's, unchanged
SERVICE_CHARGE_PERCENTAGE = 10
SERVICE_CHARGE_APPLIES_TO = ("item_subtotal",)

TIP_SUGGESTIONS = ((1, "5.0000"), (2, "10.0000"), (3, "15.0000"))

# One wording per component kind, in the three launch locales (FR-I18N-011). The English
# is the SOURCE a reviewer translates from and FR-I18N-008's approved fallback; the
# Amharic and Arabic are approved rows in menu.translation, written by a named human,
# because menu.enforce_translation_review() refuses an approval nobody reviewed and a
# migration writing one would be forging that assertion.
COMPONENT_WORDINGS = {
    "item_subtotal": {
        "id": "3333e411-0000-4000-8000-0000000e0411",
        "en": "Items",
        "am": "ዕቃዎች",
        "ar": "الأصناف",
    },
    "discount": {
        "id": "3333e412-0000-4000-8000-0000000e0412",
        "en": "Discount",
        "am": "ቅናሽ",
        "ar": "خصم",
    },
    "tax": {
        "id": "3333e413-0000-4000-8000-0000000e0413",
        "en": "Tax",
        "am": "ግብር",
        "ar": "ضريبة",
    },
    "fee": {
        "id": "3333e414-0000-4000-8000-0000000e0414",
        "en": "Service charge",
        "am": "የአገልግሎት ክፍያ",
        "ar": "رسم الخدمة",
    },
}


def _fail(label: str, res) -> None:
    if not res.ok:
        raise RuntimeError(f"m4a fixture {label} failed: {res.err}")


def seed() -> None:
    m3d.seed()
    _seed_service_charge()
    _seed_tip_configuration()
    _seed_component_wording()
    _seed_counter_service_point()
    _seed_counter_channel()
    _seed_billing_authority()
    _seed_billing_reason_codes()
    _seed_own_tables()


def _seed_service_charge() -> None:
    """FR-CFG-001C. The configured source the 'fee' charge kind has never had.

    The setting POINTS AT an approved configuration version rather than carrying a loose
    number, for the reason the tax component already demonstrates: the value a bill used
    has to stay recoverable after somebody changes their mind about it.
    """
    version = run(APP, f"""
        INSERT INTO config.configuration_version
            (id, tenant_id, outlet_id, scope_kind, scope_node_id, category, version,
             payload, effective_from, actor_id, approved_by_id, approved_at)
        VALUES ('{SERVICE_CONFIG_VERSION}', '{TENANT}', '{OUTLET_H1}', 'outlet',
                '{OUTLET_H1}', 'service', 1,
                '{{"service_charge": {{"percentage": "{SERVICE_CHARGE_PERCENTAGE}.0000",
                   "rounding": "half_up",
                   "applies_to": ["item_subtotal"]}}}}'::jsonb,
                now() - interval '1 day', '{USER}', '{USER}', now() - interval '1 day')
        ON CONFLICT (id) DO NOTHING;
    """, **CTX)
    _fail("service configuration version", version)

    applies = ", ".join(f"'{kind}'" for kind in SERVICE_CHARGE_APPLIES_TO)
    setting = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{OUTLET_H1}', false);
        INSERT INTO billing.service_charge_setting
            (tenant_id, outlet_id, configuration_version_id, percentage, rounding,
             applies_to)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{SERVICE_CONFIG_VERSION}',
                {SERVICE_CHARGE_PERCENTAGE}, 'half_up',
                ARRAY[{applies}]::ordering.charge_kind[])
        ON CONFLICT (tenant_id, outlet_id) DO NOTHING;
    """, tx=True)
    _fail("service charge setting", setting)


def _seed_tip_configuration() -> None:
    """FR-BIL-013. What a guest may tap, and nothing about which one is chosen.

    Read the INSERT: there is no default column to fill in. That is not an omission in
    the fixture, it is the shape of the table, and it is why NC-M4-001 has to plant its
    defect on the surface — the only level at which a preselection can still be expressed.
    """
    suggestions = ",\n".join(
        f"('{TENANT}', '{OUTLET_H1}', {order}, {percentage})"
        for order, percentage in TIP_SUGGESTIONS)
    res = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{OUTLET_H1}', false);
        INSERT INTO billing.tip_setting (tenant_id, outlet_id, offered)
        VALUES ('{TENANT}', '{OUTLET_H1}', true)
        ON CONFLICT (tenant_id, outlet_id) DO NOTHING;

        INSERT INTO billing.tip_suggestion
            (tenant_id, outlet_id, display_order, percentage)
        VALUES {suggestions}
        ON CONFLICT (tenant_id, outlet_id, display_order) DO NOTHING;
    """, tx=True)
    _fail("tip configuration", res)


def _seed_component_wording() -> None:
    """FR-BIL-007. What a bill calls its components, in the guest's language."""
    wordings = ",\n".join(
        f"('{w['id']}', '{TENANT}', '{kind}', $src${w['en']}$src$)"
        for kind, w in COMPONENT_WORDINGS.items())
    translations = ",\n".join(
        f"('{TENANT}', 'bill_component_wording', '{w['id']}', 'label', '{locale}', "
        f"$t${w[locale]}$t$, 'approved', 'human', '{USER}', now())"
        for w in COMPONENT_WORDINGS.values()
        for locale in ("am", "ar"))
    res = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{OUTLET_H1}', false);

        INSERT INTO menu.translatable_field
            (entity, field_name, required_for_publication, safety_critical)
        VALUES ('bill_component_wording', 'label', false, false)
        ON CONFLICT (entity, field_name) DO NOTHING;

        INSERT INTO billing.component_wording (id, tenant_id, kind, source_text)
        VALUES {wordings}
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO menu.translation
            (tenant_id, entity, entity_id, field_name, locale, translated_text, state,
             provenance, reviewed_by_user_id, approved_at)
        VALUES {translations}
        ON CONFLICT (tenant_id, entity, entity_id, field_name, locale) DO NOTHING;
    """, tx=True)
    _fail("component wording", res)


def _seed_counter_channel() -> None:
    """The counter sells the SAME MENU, in the same service window (FR-ORD-001B).

    A second menu for the counter would be a divergence of exactly the kind the
    requirement forbids, one dimension removed: the aggregate would be shared and the
    thing being sold would not. So this is one more assignment of M2-A's menu, on M3-A's
    service-window daypart, on the counter channel. The counter is open when the dining
    room is open, and an hour that is closed is closed for both — which is what makes
    tests/m4a able to prove that a counter order obeys the hours rule rather than
    bypassing it.
    """
    res = run(APP, f"""
        INSERT INTO menu.assignment
            (tenant_id, outlet_id, menu_id, channel, daypart_id, effective_from)
        SELECT '{TENANT}', '{OUTLET_H1}', '{m3a.MENU}', 'counter',
               '{m3a.DAYPART_ALL_DAY}', DATE '2026-01-01'
        WHERE NOT EXISTS (
            SELECT 1 FROM menu.assignment
            WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET_H1}'
              AND menu_id = '{m3a.MENU}' AND channel = 'counter'
              AND daypart_id = '{m3a.DAYPART_ALL_DAY}');
    """, **CTX)
    _fail("counter channel assignment", res)


def _seed_own_tables() -> None:
    """Two dining tables nothing else in the chain touches.

    A node of kind 'dining_table' is not yet a table: service.table_session's foreign key
    resolves through service.table_profile, which is what makes a node servable. M3-D
    learned that when a journey's "free table" turned out to be a foreign key rather than
    a table.
    """
    nodes = ",\n".join(
        f"('{node}', '{TENANT}', '{OUTLET_H1}', 'dining_table', "
        f"'M4A-BILL-{locale.upper()}', 'Table the {locale} bill is read at')"
        for locale, node in BILL_TABLES.items())
    profiles = ",\n".join(
        f"('{TENANT}', '{node}', '{OUTLET_H1}', 4)" for node in BILL_TABLES.values())
    res = run(APP, f"""
        INSERT INTO org.org_node
            (id, tenant_id, parent_id, kind, reference_code, display_name)
        VALUES {nodes},
               ('{TIP_TABLE}', '{TENANT}', '{OUTLET_H1}', 'dining_table',
                'M4A-TIP', 'Table the tip is chosen at')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO service.table_profile
            (tenant_id, table_node_id, outlet_id, seat_count)
        VALUES {profiles},
               ('{TENANT}', '{TIP_TABLE}', '{OUTLET_H1}', 4)
        ON CONFLICT DO NOTHING;
    """, tx=True, **CTX)
    _fail("m4a tables", res)


def _seed_counter_service_point() -> None:
    """A counter is a service point, not a second order path (FR-ORD-001B).

    service.cart requires a table session and ordering.customer_order carries one, so a
    counter order needs a place to happen. Making one is how the counter stays on the same
    aggregate: a sessionless counter path would have needed a second cart, a second
    preview and a second set of rules to keep in step with these ones.
    """
    res = run(APP, f"""
        INSERT INTO org.org_node
            (id, tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{COUNTER_NODE}', '{TENANT}', '{OUTLET_H1}', 'dining_table',
                'M4A-COUNTER', 'Front counter')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO service.table_profile
            (tenant_id, table_node_id, outlet_id, seat_count)
        VALUES ('{TENANT}', '{COUNTER_NODE}', '{OUTLET_H1}', 1)
        ON CONFLICT DO NOTHING;
    """, tx=True, **CTX)
    _fail("counter service point", res)


def _seed_billing_authority() -> None:
    """Somebody who may authorize a bill correction, and it is NOT M3-D's manager.

    A separate person with a separate role, for the reason M3-D's fixture records about
    its own outsider: borrowing an existing person and widening their authority makes
    every earlier check that rests on what they may NOT do quietly weaker, and the forward
    order never shows it. M3-D's manager may void an ORDER; voiding a BILL is a different
    authority, and giving it to the same role would have made "the waiter cannot authorize
    their own override" pass for a reason nobody chose.
    """
    actions = ",\n".join(
        f"('{TENANT}', '{ROLE_CASHIER_MANAGER}', '{code}')"
        for code in CASHIER_MANAGER_ACTIONS)
    res = run(APP, f"""
        INSERT INTO identity.role (id, tenant_id, role_code, display_name, status)
        VALUES ('{ROLE_CASHIER_MANAGER}', '{TENANT}', 'M4A_CASHIER_MANAGER',
                'Cashier manager', 'active')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO identity.user_account
            (id, tenant_id, staff_number, display_name, status)
        VALUES ('{USER_CASHIER_MANAGER}', '{TENANT}', 'M4A-CSH-1', 'Selam Cashier', 'active')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO identity.role_action (tenant_id, role_id, action_code)
        VALUES {actions}
        ON CONFLICT DO NOTHING;

        INSERT INTO identity.membership
            (id, tenant_id, outlet_id, user_account_id, role_id, status)
        SELECT '{MEMBERSHIP_CASHIER_MANAGER}', '{TENANT}', '{OUTLET_H1}',
               '{USER_CASHIER_MANAGER}', '{ROLE_CASHIER_MANAGER}', 'active'
         WHERE NOT EXISTS (SELECT 1 FROM identity.membership
                            WHERE tenant_id = '{TENANT}'
                              AND user_account_id = '{USER_CASHIER_MANAGER}'
                              AND role_id = '{ROLE_CASHIER_MANAGER}');
    """, **CTX)
    _fail("billing authority", res)


def _seed_billing_reason_codes() -> None:
    """Why a bill was corrected, with ENGLISH labels and no others.

    Both halves are M3-D's lesson, restated because it cost two findings there: M1-C
    asserts that every reason code in the tenant carries at least an English label, and
    it also asserts that M1 seeds the reason-code STRUCTURE and leaves the content to M2.
    A fixture that added no label failed the first; one that added Amharic and Arabic
    failed the second.
    """
    res = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{OUTLET_H1}', false);
        INSERT INTO config.reason_code (tenant_id, category, code, status)
        VALUES ('{TENANT}', 'manager_override', 'M4A_ON_THE_HOUSE', 'active'),
               ('{TENANT}', 'manager_override', 'M4A_BILL_REISSUED', 'active')
        ON CONFLICT (tenant_id, category, code) DO NOTHING;

        INSERT INTO config.reason_code_label (tenant_id, reason_code_id, locale, label)
        SELECT rc.tenant_id, rc.id, 'en', v.label
        FROM config.reason_code rc
        JOIN (VALUES
            ('M4A_ON_THE_HOUSE', 'The house is covering this bill'),
            ('M4A_BILL_REISSUED', 'The bill was issued against the wrong check')
        ) AS v(code, label) ON v.code = rc.code
        WHERE rc.tenant_id = '{TENANT}' AND rc.category = 'manager_override'
        ON CONFLICT DO NOTHING;
    """, tx=True)
    _fail("billing reason codes", res)


# ---------------------------------------------------------------------------
# Helpers the suite uses
# ---------------------------------------------------------------------------

def staff_session(user_id: str = USER) -> tuple[str, str]:
    return m3d.staff_session(user_id)


def step_up(session_id: str, action_code: str, age_seconds: int = 0) -> str:
    return m3d.step_up(session_id, action_code, age_seconds)


def reason_code(code: str = "M3D_SUPERVISOR_APPROVED") -> str:
    return m3d.reason_code(code)


def fresh_occupancy(table: str = TABLE_ONE) -> str:
    return m3a.fresh_occupancy(table)


def guest_on(session_id: str, nickname: str = "Guest") -> str:
    return m3a.guest_on(session_id, nickname)


def cart_with(session_id: str, guest_id: str, lines, modifiers=()) -> str:
    return m3a.cart_with(session_id, guest_id, lines, modifiers)


def expected_components(subtotal: int) -> dict:
    """What billing.issue_bill() must produce for a given item subtotal.

    Recomputed in Python from the configured rates, in the stated stage order, with the
    same half-up rule money.apply_rate() applies. Written out rather than read back from
    the database, because a test that asked the system what it computed and then agreed
    with it would be supplying its own evidence.
    """
    discount = -_half_up(subtotal * DISCOUNT_PERCENTAGE, 100)
    tax = _half_up((subtotal + discount) * TAX_PERCENTAGE, 100)
    base = subtotal if "item_subtotal" in SERVICE_CHARGE_APPLIES_TO else 0
    fee = _half_up(base * SERVICE_CHARGE_PERCENTAGE, 100)
    return {"item_subtotal": subtotal, "discount": discount, "tax": tax, "fee": fee,
            "total": subtotal + discount + tax + fee}


def _half_up(numerator: int, denominator: int) -> int:
    """Half away from zero, which is what money.rounding_mode 'half_up' means here.

    Python's round() is half-to-even and its // is floor, and both are wrong for money in
    a way that only shows on the .5 cases — so neither is used.
    """
    sign = -1 if numerator < 0 else 1
    magnitude = abs(numerator)
    return sign * ((2 * magnitude + denominator) // (2 * denominator))
