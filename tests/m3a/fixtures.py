"""M3-A fixtures: a seated table, a priced menu, a policy that says how orders are taken.

Built on M2-C's, which is built on M2-B's, which is built on M2-A's. Nothing here stubs a
price, a translation or an allergen: an order at this gate is M2-A's published snapshot,
M2-B's live safety catalog and M1-C's exact money types arriving at the moment somebody
commits to paying for them.

What this module adds that no earlier slice needed:

  * an ordering policy and a cancellation policy, because FR-ORD-007A and FR-ORD-011
    resolve per channel and outlet and an absent policy is refused rather than defaulted
  * a tax configuration and a discount policy, with a charge rule pointing at each, so
    the preview's tax and discount components have real configured sources and are
    non-zero — a summation exercised only by an item subtotal proves nothing about a sum
  * a staff identity holding a live strong session and a step-up, because a void is a
    governed action and M1-B's registry is what decides it
  * a service window that covers the moment the suite runs, so the hours dimension of
    FR-ORD-006 is exercised through an explicit timestamp rather than by whatever hour
    the CI runner happens to start at

Deliberately NOT here: a fee source. config.configuration_category has no heading a fee
resolves to before FR-CFG-001C at M4, and inventing one would be building M4's model in
M3's slice. The fee seam is exercised by the control that plants one, not by a fixture
that quietly makes one normal.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "m1a"))

from pg import ProbeFailed, count, run  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "m2c_fixtures", HERE.parent / "m2c" / "fixtures.py")
m2c = importlib.util.module_from_spec(_spec)
sys.modules["m2c_fixtures"] = m2c
_spec.loader.exec_module(m2c)

m2b = m2c.m2b
m2a = m2b.m2a

TENANT = m2a.TENANT
OUTLET_H1 = m2a.OUTLET_H1
OUTLET_H2 = m2a.OUTLET_H2
USER = m2a.USER
USER_WAITER_B = m2b.USER_WAITER_B
TABLE_ONE = m2b.TABLE_ONE
TABLE_TWO = m2b.TABLE_TWO
MENU = m2a.MENU
ITEM_DORO = m2a.ITEM_DORO
ITEM_COFFEE = m2a.ITEM_COFFEE
VARIANT_DORO_FULL = m2a.VARIANT_DORO_FULL
VARIANT_COFFEE_ONE = m2a.VARIANT_COFFEE_ONE
MODIFIER_HOT = m2a.MODIFIER_HOT
ALLERGEN_SESAME = m2b.ALLERGEN_SESAME
WORDING_ACK = m2b.WORDING_ACK

CTX = dict(tenant=TENANT, outlet=OUTLET_H1)
APP = os.environ["M1A_APP_DSN"]
ADMIN = os.environ["M1A_ADMIN_DSN"]

# Identifiers this slice owns. Distinct high nibble so a stray row is traceable to the
# slice that wrote it.
ROLE_MANAGER = "3333e301-0000-4000-8000-0000000e0301"
MEMBERSHIP_MANAGER = "3333e302-0000-4000-8000-0000000e0302"
DAYPART_ALL_DAY = "3333e303-0000-4000-8000-0000000e0303"
TAX_CONFIG_VERSION = "3333e304-0000-4000-8000-0000000e0304"
DISCOUNT_POLICY = "3333e305-0000-4000-8000-0000000e0305"
ORDERING_POLICY = "3333e306-0000-4000-8000-0000000e0306"
CANCELLATION_POLICY = "3333e307-0000-4000-8000-0000000e0307"
RULE_TAX = "3333e308-0000-4000-8000-0000000e0308"
RULE_DISCOUNT = "3333e309-0000-4000-8000-0000000e0309"

# The staff bearer token. A test fixture's secret, never a stored one: only its digest
# reaches the database, exactly as a real credential does (FR-SEC-007).
STAFF_TOKEN = "m3a-fixture-manager-token"

# Rates chosen so the arithmetic is checkable by hand and neither component can be
# mistaken for the other: 15% tax and 10% discount on a 32000 minor-unit dish are 4800
# and -3200, which are distinct, non-zero, and not equal to any line amount.
TAX_PERCENTAGE = "15.0000"
DISCOUNT_PERCENTAGE = "10.0000"


def _fail(label: str, res) -> None:
    if not res.ok:
        raise RuntimeError(f"{label} fixture failed: {res.why()}")


def seed() -> None:
    m2c.seed()
    _seed_service_window()
    _seed_policies_and_rules()
    _seed_staff_authority()


def _seed_service_window() -> None:
    """A dine-in window that covers the moment the suite runs, and not the whole day.

    M2-A assigns the menu to LUNCH only, so an M3-A submission would pass or fail on the
    hour the runner started — not a property of the code under test. The obvious fix is an
    assignment with no daypart, meaning "always", and that is WRONG: it covers every hour,
    so the hours dimension of FR-ORD-006 could never be exercised and the check would pass
    by being unfalsifiable. (It was written that way first, and uncovered_local_time()
    caught it by refusing to find a closed hour.)

    So the window is a real daypart derived from the current outlet-local time — three
    hours either side of now — which covers the run and leaves most of the day closed for
    the hours check to find.
    """
    res = run(APP, f"""
        -- An earlier run of the wrong shape may have left an always-on assignment.
        DELETE FROM menu.assignment
         WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET_H1}'
           AND menu_id = '{MENU}' AND channel = 'dine_in' AND daypart_id IS NULL;

        INSERT INTO menu.daypart
            (id, tenant_id, outlet_id, daypart_code, canonical_name,
             starts_at_local, ends_at_local)
        SELECT '{DAYPART_ALL_DAY}', '{TENANT}', '{OUTLET_H1}', 'M3A_SERVICE',
               'M3-A service window',
               make_time(((extract(hour FROM local_now)::int + 21) % 24), 0, 0),
               make_time(((extract(hour FROM local_now)::int + 3)  % 24), 0, 0)
        FROM (SELECT (now() AT TIME ZONE menu.outlet_timezone('{TENANT}', '{OUTLET_H1}'))
                     AS local_now) s
        ON CONFLICT (id) DO UPDATE
           SET starts_at_local = EXCLUDED.starts_at_local,
               ends_at_local   = EXCLUDED.ends_at_local;

        INSERT INTO menu.assignment
            (tenant_id, outlet_id, menu_id, channel, daypart_id, effective_from)
        SELECT '{TENANT}', '{OUTLET_H1}', '{MENU}', 'dine_in', '{DAYPART_ALL_DAY}',
               DATE '2026-01-01'
        WHERE NOT EXISTS (
            SELECT 1 FROM menu.assignment
            WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET_H1}'
              AND menu_id = '{MENU}' AND channel = 'dine_in'
              AND daypart_id = '{DAYPART_ALL_DAY}');
    """, **CTX)
    _fail("service window", res)


def _seed_policies_and_rules() -> None:
    """The policies an order is handled under, and the charge rules with real sources.

    THE ACCEPTANCE BLOCK NAMES ALL THREE ORIGINS, INCLUDING THE COUNTER, AND IT IS
    STATED HERE RATHER THAN ADDED BY M4-A.

    There is one ordering policy per outlet and ordering.submit_order() resolves the mode
    by looking the origin up inside it. A later slice that appended its channel by
    UPDATE-ing an approved policy would be editing a versioned configuration artifact to
    make a test pass, and a later slice that added a SECOND policy version would leave two
    in force — which M3-A's own "an outlet with no ordering policy in force accepts no
    order at all" check would then fail, because expiring the first would no longer leave
    the outlet without one. Both routes make the counter a special case of the thing
    FR-ORD-001B says must not be special.

    So the policy states how this outlet accepts an order of each origin, in one place,
    the way the running system would. Nothing at M3 submits a counter order; the counter
    origin arrives with migration 0018 and tests/m4a is what exercises it.
    """
    res = run(APP, f"""
        INSERT INTO config.configuration_version
            (id, tenant_id, outlet_id, scope_kind, scope_node_id, category, version,
             payload, effective_from, actor_id, approved_by_id, approved_at)
        VALUES ('{TAX_CONFIG_VERSION}', '{TENANT}', '{OUTLET_H1}', 'outlet',
                '{OUTLET_H1}', 'tax', 1,
                '{{"contexts": {{"standard": {{"percentage": "{TAX_PERCENTAGE}",
                   "rounding": "half_up"}}}}}}'::jsonb,
                now() - interval '1 day', '{USER}', '{USER}', now() - interval '1 day')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO config.policy
            (id, tenant_id, outlet_id, category, version, payload, effective_from,
             actor_id, approved_by_id, approved_at)
        VALUES
            ('{ORDERING_POLICY}', '{TENANT}', '{OUTLET_H1}', 'ordering', 1,
             '{{"acceptance": {{"guest_qr": "staff_confirmed",
                                "waiter_entered": "automatic",
                                "counter": "staff_confirmed"}},
                "max_line_quantity": 20,
                "duplicate_window_seconds": 300,
                "amendment_allowed_states": ["submitted"]}}'::jsonb,
             now() - interval '1 day', '{USER}', '{USER}', now() - interval '1 day'),
            ('{CANCELLATION_POLICY}', '{TENANT}', '{OUTLET_H1}', 'cancellation', 1,
             '{{"allowed_states": {{"guest_qr": ["submitted"],
                                    "waiter_entered": ["submitted", "accepted"]}}}}'::jsonb,
             now() - interval '1 day', '{USER}', '{USER}', now() - interval '1 day'),
            ('{DISCOUNT_POLICY}', '{TENANT}', '{OUTLET_H1}', 'discount', 1,
             '{{"table_service": {{"percentage": "{DISCOUNT_PERCENTAGE}",
                "rounding": "half_up"}}}}'::jsonb,
             now() - interval '1 day', '{USER}', '{USER}', now() - interval '1 day')
        ON CONFLICT (id) DO NOTHING;

    """, **CTX)
    _fail("policy", res)

    # The charge rules are written as the administrator, not through the application
    # role. That is not a convenience: 0010 grants the application role SELECT on
    # ordering.charge_rule and nothing more, because installing a tax rule is a
    # configuration act and the configuration surface for it is FR-CFG-001C at M4. A
    # fixture that needed a wider grant to run would have been asking for the schema to
    # be loosened to suit the test.
    rules = run(ADMIN, f"""
        INSERT INTO ordering.charge_rule
            (id, tenant_id, outlet_id, kind, source_kind, source_configuration_id,
             source_policy_id, tax_context, rate_percentage, rounding_mode, effective_from)
        VALUES
            ('{RULE_TAX}', '{TENANT}', '{OUTLET_H1}', 'tax', 'tax_configuration',
             '{TAX_CONFIG_VERSION}', NULL, 'standard', {TAX_PERCENTAGE}, 'half_up',
             now() - interval '1 day'),
            ('{RULE_DISCOUNT}', '{TENANT}', '{OUTLET_H1}', 'discount', 'discount_policy',
             NULL, '{DISCOUNT_POLICY}', NULL, {DISCOUNT_PERCENTAGE}, 'half_up',
             now() - interval '1 day')
        ON CONFLICT (id) DO NOTHING;
    """)
    _fail("charge rule", rules)


def _seed_staff_authority() -> None:
    """A manager who may void, close over an exception, and read an order.

    A live strong session and a fresh step-up, because ordering.void_order() goes through
    identity.authorize_action() rather than checking anything of its own. The step-up is
    inserted here rather than granted by a login flow that does not exist yet; what is
    being proved at this gate is that the void CONSULTS the registry, not that M1-B's
    registry works — M1-B proved that.
    """
    res = run(APP, f"""
        INSERT INTO identity.role (id, tenant_id, role_code, display_name)
        VALUES ('{ROLE_MANAGER}', '{TENANT}', 'M3A_SERVICE_MANAGER', 'Service Manager')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO identity.role_action (tenant_id, role_id, action_code)
        VALUES ('{TENANT}', '{ROLE_MANAGER}', 'order.void'),
               ('{TENANT}', '{ROLE_MANAGER}', 'session.close_with_exception'),
               ('{TENANT}', '{ROLE_MANAGER}', 'order.view')
        ON CONFLICT (role_id, action_code) DO NOTHING;

        INSERT INTO identity.membership
            (id, tenant_id, outlet_id, user_account_id, role_id, status)
        VALUES ('{MEMBERSHIP_MANAGER}', '{TENANT}', '{OUTLET_H1}', '{USER}',
                '{ROLE_MANAGER}', 'active')
        ON CONFLICT (id) DO NOTHING;
    """, **CTX)
    _fail("staff authority", res)


def open_staff_session() -> str:
    """Issue a fresh staff session and step-up, returning the session id.

    Re-issued per call rather than seeded once: identity.session has a unique constraint
    on the token digest, and a suite that reused one session across a control which
    revokes it would be testing the leftovers of the previous run.
    """
    token = f"{STAFF_TOKEN}-{os.urandom(8).hex()}"
    res = run(APP, f"""
        INSERT INTO identity.session
            (tenant_id, outlet_id, user_account_id, token_digest, established_with,
             expires_at)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{USER}',
                sha256(convert_to('{token}', 'UTF8')), 'strong', now() + interval '1 hour')
        RETURNING id;
    """, **CTX)
    _fail("staff session", res)
    session_id = (res.scalar or "").strip()

    grant = run(APP, f"""
        INSERT INTO identity.step_up_grant
            (tenant_id, outlet_id, session_id, action_code)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{session_id}', 'order.void'),
               ('{TENANT}', '{OUTLET_H1}', '{session_id}', 'session.close_with_exception');
    """, **CTX)
    _fail("step-up grant", grant)
    return session_id


def staff_context(sql: str, *, session_id: str, strength: str = "strong") -> object:
    """Run SQL under a live staff session context, in one transaction.

    The context functions M1-C wrote are transaction-local, so establishing context and
    using it have to be one transaction — which is also how the API does it.
    """
    return run(APP, f"""
        SELECT set_config('app.session_id', '{session_id}', true);
        SELECT set_config('app.auth_strength', '{strength}', true);
        {sql}
    """, tx=True, **CTX)


def fresh_occupancy(table: str = TABLE_ONE) -> str:
    """Open a new occupancy on a table, closing whatever sat there before.

    Returns the table_session id. Written as its own step rather than reusing M2-B's
    join path because an M3-A test wants a table it controls, and because closing the
    previous occupancy through service.close_table_session() would need the very
    authority half of these tests are about to plant defects in.
    """
    res = run(APP, f"""
        UPDATE service.table_session
           SET state = 'closed', closed_at = now()
         WHERE tenant_id = '{TENANT}' AND table_node_id = '{table}' AND state = 'open';

        INSERT INTO service.table_session
            (tenant_id, outlet_id, table_node_id, occupancy_number, state, opening_source,
             host_staff_user_id, customer_locale, customer_locale_selected_at)
        SELECT '{TENANT}', '{OUTLET_H1}', '{table}',
               coalesce(max(occupancy_number), 0) + 1, 'open', 'qr_scan', NULL,
               'en', now()
        FROM service.table_session
        WHERE tenant_id = '{TENANT}' AND table_node_id = '{table}'
        RETURNING id;
    """, tx=True, **CTX)
    _fail("occupancy", res)
    return (res.scalar or "").strip()


def guest_on(session_id: str, nickname: str = "Guest") -> str:
    """A guest session joined to an occupancy. No identity, no registration."""
    res = run(APP, f"""
        WITH g AS (
            INSERT INTO service.guest_session
                (tenant_id, outlet_id, display_nickname, locale, expires_at)
            VALUES ('{TENANT}', '{OUTLET_H1}', '{nickname}', 'en', now() + interval '4 hours')
            RETURNING id
        ), p AS (
            INSERT INTO service.session_participant
                (tenant_id, outlet_id, table_session_id, guest_session_id)
            SELECT '{TENANT}', '{OUTLET_H1}', '{session_id}', g.id FROM g
            RETURNING guest_session_id
        )
        SELECT guest_session_id FROM p;
    """, tx=True, **CTX)
    _fail("guest session", res)
    return (res.scalar or "").strip()


def cart_with(session_id: str, guest_id: str,
              lines=((m2a.VARIANT_DORO_FULL, m2a.ITEM_DORO, 1),),
              modifiers=()) -> str:
    """A personal cart holding the given lines. Returns the cart id."""
    res = run(APP, f"""
        INSERT INTO service.cart
            (tenant_id, outlet_id, table_session_id, kind, owner_guest_session_id)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{session_id}', 'personal', '{guest_id}')
        RETURNING id;
    """, **CTX)
    _fail("cart", res)
    cart = (res.scalar or "").strip()

    for variant, item, quantity in lines:
        added = run(APP, f"""
            INSERT INTO service.cart_line
                (tenant_id, outlet_id, cart_id, item_id, variant_id, quantity,
                 currency_code, unit_amount_minor, added_by_guest_session_id)
            SELECT '{TENANT}', '{OUTLET_H1}', '{cart}', '{item}', '{variant}', {quantity},
                   p.currency_code, p.amount_minor, '{guest_id}'
            FROM menu.price p
            WHERE p.tenant_id = '{TENANT}' AND p.variant_id = '{variant}'
              AND p.channel IS NULL AND p.effective_to IS NULL
            RETURNING id;
        """, **CTX)
        _fail("cart line", added)
        line_id = (added.scalar or "").strip()
        for modifier in modifiers:
            mod = run(APP, f"""
                INSERT INTO service.cart_line_modifier
                    (tenant_id, outlet_id, cart_line_id, modifier_id)
                VALUES ('{TENANT}', '{OUTLET_H1}', '{line_id}', '{modifier}');
            """, **CTX)
            _fail("cart line modifier", mod)
    return cart


def allergy_concern(session_id: str, guest_id: str,
                    allergen: str = ALLERGEN_SESAME) -> str:
    """A table-level allergy concern, exactly as M2-B records one.

    The order-level declaration copies its wording from here rather than composing new
    words, which is the first hop of the chain NC-M3-003 follows.
    """
    res = run(APP, f"""
        INSERT INTO safety.allergy_concern
            (tenant_id, outlet_id, table_session_id, raised_by, guest_session_id,
             allergen_id, note, acknowledgement_wording_id, acknowledgement_text)
        SELECT '{TENANT}', '{OUTLET_H1}', '{session_id}', 'guest', '{guest_id}',
               '{allergen}', 'Severe sesame allergy.', w.id, w.wording
        FROM safety.approved_wording w
        WHERE w.tenant_id = '{TENANT}' AND w.id = '{WORDING_ACK}'
        RETURNING id;
    """, **CTX)
    _fail("allergy concern", res)
    return (res.scalar or "").strip()


def uncovered_local_time() -> str:
    """A timestamptz at which NO daypart assigned to this menu covers the outlet.

    Asked of the database rather than chosen, because a hardcoded 04:30 becomes wrong the
    moment somebody adds a late-night window — and it would become wrong SILENTLY, by
    making the hours check pass for the wrong reason.

    Raises rather than returning a sentinel when every hour is covered: an hours control
    that cannot find a closed hour has not proved anything, and must say so.
    """
    res = run(APP, f"""
        WITH tz AS (SELECT menu.outlet_timezone('{TENANT}', '{OUTLET_H1}') AS zone),
        candidate AS (
            SELECT generate_series(0, 23) AS hour
        ),
        covered AS (
            SELECT c.hour
            FROM candidate c
            JOIN menu.assignment a
              ON a.tenant_id = '{TENANT}' AND a.outlet_id = '{OUTLET_H1}'
             AND a.menu_id = '{MENU}' AND a.channel = 'dine_in'
            LEFT JOIN menu.daypart d ON d.id = a.daypart_id
            WHERE a.daypart_id IS NULL
               OR (d.starts_at_local <= d.ends_at_local
                   AND make_time(c.hour, 30, 0) >= d.starts_at_local
                   AND make_time(c.hour, 30, 0) <  d.ends_at_local)
               OR (d.starts_at_local >  d.ends_at_local
                   AND (make_time(c.hour, 30, 0) >= d.starts_at_local
                        OR make_time(c.hour, 30, 0) < d.ends_at_local))
        )
        SELECT to_char(
                 ((current_date + make_time(c.hour, 30, 0))
                   AT TIME ZONE (SELECT zone FROM tz)),
                 'YYYY-MM-DD HH24:MI:SSOF')
        FROM candidate c
        WHERE c.hour NOT IN (SELECT hour FROM covered)
        ORDER BY c.hour
        LIMIT 1;
    """, **CTX)
    if not res.ok:
        raise ProbeFailed("uncovered_local_time", res.err)
    value = (res.scalar or "").strip()
    if not value:
        raise ProbeFailed(
            "uncovered_local_time",
            "every hour of the day is covered by an assignment, so the hours dimension "
            "of FR-ORD-006 cannot be exercised; the fixture, not the code, is wrong")
    return value


def reason_code(category: str) -> str:
    """An active reason code of a category, from M1's seeded registry."""
    res = run(APP, f"""
        SELECT id FROM config.reason_code
        WHERE tenant_id = '{TENANT}' AND category = '{category}' AND status = 'active'
        ORDER BY code LIMIT 1;
    """, **CTX)
    if not res.ok:
        raise ProbeFailed(f"reason_code({category})", res.err)
    value = (res.scalar or "").strip()
    if not value:
        raise ProbeFailed(f"reason_code({category})",
                          f"no active {category} reason code is seeded for this tenant")
    return value
