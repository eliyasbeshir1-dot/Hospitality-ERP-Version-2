"""M3-B fixtures: a kitchen, a bar, routing rules, and an order on its way to both.

Built on M3-A's, which is built on M2-C's, and so on down to M1-A. Nothing here stubs a
ticket: a ticket exists because an order was accepted and the routing rules in force sent
its lines somewhere, which is the path FR-FUL-001 and FR-FUL-002 describe.

What this module adds that no earlier slice needed:

  * TWO preparation stations, so FR-FUL-002's "multiple stations per order" is a fact
    about a real order rather than an assertion about a schema, and so FR-FUL-009's expo
    has something to reassemble
  * a versioned routing rule set, because FR-FUL-001 says "versioned rules" and a ticket
    records the version that placed it
  * a service policy stating the recall window, the collection escalation window and the
    capacity response — each of them refused rather than defaulted by the functions that
    read them
  * a staff session for the station surface, because the KDS routes authenticate through
    the same db.withSession() M1-D built and a guest credential reaches none of them

Deliberately NOT here: a station whose threshold is already exceeded. Capacity pressure
is created by the checks that need it, so a fixture cannot leave every other check
running against a throttled outlet.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "m1a"))

from pg import ProbeFailed, run  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "m3a_fixtures", HERE.parent / "m3a" / "fixtures.py")
m3a = importlib.util.module_from_spec(_spec)
sys.modules["m3a_fixtures"] = m3a
_spec.loader.exec_module(m3a)

m2c, m2b, m2a = m3a.m2c, m3a.m2b, m3a.m2a

TENANT = m3a.TENANT
OUTLET_H1 = m3a.OUTLET_H1
OUTLET_H2 = m3a.OUTLET_H2
USER = m3a.USER
USER_WAITER_B = m3a.USER_WAITER_B
TABLE_ONE = m3a.TABLE_ONE
TABLE_TWO = m3a.TABLE_TWO
ITEM_DORO = m3a.ITEM_DORO
ITEM_COFFEE = m3a.ITEM_COFFEE
VARIANT_DORO_FULL = m3a.VARIANT_DORO_FULL
VARIANT_COFFEE_ONE = m3a.VARIANT_COFFEE_ONE
ALLERGEN_SESAME = m3a.ALLERGEN_SESAME

CTX = dict(tenant=TENANT, outlet=OUTLET_H1)
APP = os.environ["M1A_APP_DSN"]
ADMIN = os.environ["M1A_ADMIN_DSN"]

# Identifiers this slice owns.
STATION_KITCHEN = "3333f101-0000-4000-8000-0000000f0101"
STATION_BAR = "3333f102-0000-4000-8000-0000000f0102"
STATION_SPARE = "3333f103-0000-4000-8000-0000000f0103"
RULE_SET = "3333f201-0000-4000-8000-0000000f0201"
SERVICE_POLICY = "3333f301-0000-4000-8000-0000000f0301"

# Chosen so a station is never accidentally over threshold during the checks that are not
# about capacity. Set to 2 first, and the capacity control immediately throttled the
# suite's own third order — which was the FR-ORD-006 closure working, and a fixture that
# leaves every later check running against a throttled outlet. Pressure is now something
# a check CREATES, with set_kitchen_threshold(), and puts back afterwards.
KITCHEN_THRESHOLD = 500
KITCHEN_SLA_MINUTES = 20
BAR_SLA_MINUTES = 5


def _fail(label: str, res) -> None:
    if not res.ok:
        raise RuntimeError(f"{label} fixture failed: {res.why()}")


def seed() -> None:
    m3a.seed()
    _seed_stations()
    _seed_routing()
    _seed_service_policy()


def _seed_stations() -> None:
    """Two preparation stations under the outlet, plus a spare for transfer to move to."""
    nodes = run(APP, f"""
        INSERT INTO org.org_node (id, tenant_id, parent_id, kind, reference_code, display_name)
        SELECT v.id::uuid, '{TENANT}', '{OUTLET_H1}', 'preparation_station',
               v.code, v.name
        FROM (VALUES ('{STATION_KITCHEN}', 'ST-H1-KITCHEN', 'Main kitchen'),
                     ('{STATION_BAR}', 'ST-H1-BAR', 'Bar'),
                     ('{STATION_SPARE}', 'ST-H1-PASTRY', 'Pastry')) AS v(id, code, name)
        WHERE NOT EXISTS (SELECT 1 FROM org.org_node n WHERE n.id = v.id::uuid);
    """, **CTX)
    _fail("station nodes", nodes)

    # Written as the administrator: 0012 grants the application role SELECT on
    # fulfillment.station_profile and nothing more, because installing a station is a
    # configuration act and that surface is FR-CFG-001B's, not this gate's. A fixture
    # that needed a wider grant would have been asking for the schema to be loosened.
    profiles = run(ADMIN, f"""
        INSERT INTO fulfillment.station_profile
            (station_node_id, tenant_id, outlet_id, station_kind, sla_minutes,
             concurrent_ticket_threshold, allergy_acknowledgement_required)
        VALUES ('{STATION_KITCHEN}', '{TENANT}', '{OUTLET_H1}', 'kitchen',
                {KITCHEN_SLA_MINUTES}, {KITCHEN_THRESHOLD}, true),
               ('{STATION_BAR}', '{TENANT}', '{OUTLET_H1}', 'bar',
                {BAR_SLA_MINUTES}, NULL, false),
               ('{STATION_SPARE}', '{TENANT}', '{OUTLET_H1}', 'dessert', NULL, NULL, false)
        ON CONFLICT (station_node_id) DO NOTHING;
    """)
    _fail("station profiles", profiles)


def _seed_routing() -> None:
    """One versioned rule set: coffee to the bar, everything else to the kitchen."""
    res = run(ADMIN, f"""
        INSERT INTO fulfillment.routing_rule_set
            (id, tenant_id, outlet_id, version, approved_by_user_id, effective_from)
        VALUES ('{RULE_SET}', '{TENANT}', '{OUTLET_H1}', 1, '{USER}',
                now() - interval '1 day')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO fulfillment.routing_rule
            (tenant_id, outlet_id, rule_set_id, precedence, item_id,
             target_station_node_id)
        SELECT '{TENANT}', '{OUTLET_H1}', '{RULE_SET}', 1, '{ITEM_COFFEE}',
               '{STATION_BAR}'
        WHERE NOT EXISTS (
            SELECT 1 FROM fulfillment.routing_rule
             WHERE rule_set_id = '{RULE_SET}' AND precedence = 1);

        -- The catch-all. A rule set without one refuses lines it does not cover, by
        -- design; this one is total, so the checks that are not about routing gaps do
        -- not trip over one.
        INSERT INTO fulfillment.routing_rule
            (tenant_id, outlet_id, rule_set_id, precedence, target_station_node_id)
        SELECT '{TENANT}', '{OUTLET_H1}', '{RULE_SET}', 99, '{STATION_KITCHEN}'
        WHERE NOT EXISTS (
            SELECT 1 FROM fulfillment.routing_rule
             WHERE rule_set_id = '{RULE_SET}' AND precedence = 99);
    """)
    _fail("routing rules", res)


def _seed_service_policy() -> None:
    """The three windows FR-FUL-005, FR-FUL-010 and FR-FUL-013 refuse to default."""
    res = run(APP, f"""
        INSERT INTO config.policy
            (id, tenant_id, outlet_id, category, version, payload, effective_from,
             actor_id, approved_by_id, approved_at)
        VALUES ('{SERVICE_POLICY}', '{TENANT}', '{OUTLET_H1}', 'service', 1,
                '{{"recall_window_seconds": 900,
                   "collection_escalation_seconds": 300,
                   "capacity_response": "throttle"}}'::jsonb,
                now() - interval '1 day', '{USER}', '{USER}', now() - interval '1 day')
        ON CONFLICT (id) DO NOTHING;
    """, **CTX)
    _fail("service policy", res)


def set_kitchen_threshold(threshold: int | None) -> None:
    """Lower (or lift) the kitchen's concurrent-ticket threshold.

    Written as the administrator for the same reason the profile is: a station's capacity
    is configuration, and the surface that edits it is FR-CFG-001B's.
    """
    value = "NULL" if threshold is None else str(threshold)
    res = run(ADMIN, f"""
        UPDATE fulfillment.station_profile SET concurrent_ticket_threshold = {value}
         WHERE tenant_id = '{TENANT}' AND station_node_id = '{STATION_KITCHEN}';
    """)
    _fail("kitchen threshold", res)


def set_capacity_response(response: str, promise_minutes: int | None = None) -> None:
    """Switch the outlet between throttling and promise-time adjustment.

    FR-FUL-013 offers both and says the choice is configured. The checks exercise each,
    so neither is proved by the fixture happening to pick it.
    """
    extra = (f', "promise_extension_minutes": {promise_minutes}'
             if promise_minutes is not None else "")
    res = run(APP, f"""
        UPDATE config.policy
           SET payload = '{{"recall_window_seconds": 900,
                            "collection_escalation_seconds": 300,
                            "capacity_response": "{response}"{extra}}}'::jsonb
         WHERE id = '{SERVICE_POLICY}';
    """, **CTX)
    _fail("capacity response", res)


def submit_order(cart: str, *, guest: str, key: str, declarations: list | None = None,
                 locale: str = "en"):
    """Price a cart and submit it, exactly as a guest device would.

    Written here rather than imported from tests/m3a/verify_m3a.py: a fixture that reached
    into a verifier for its helpers would make the two files a cycle, and a verifier is
    where assertions live, not where other suites get their tools.
    """
    view = run(APP, f"""
        SELECT ordering.preview_cart('{TENANT}', '{OUTLET_H1}', '{cart}', '{locale}');
    """, **CTX)
    if not view.ok:
        raise ProbeFailed("preview_cart", view.err)
    payload = json.loads(view.scalar)
    return run(APP, f"""
        SELECT ordering.submit_order(
            '{TENANT}', '{OUTLET_H1}', '{cart}', '{key}',
            decode('{payload["pricing_digest"]}', 'hex'),
            {payload["total_amount_minor"]}, '{locale}',
            gen_random_uuid(), gen_random_uuid(), 'guest_qr', NULL, '{guest}',
            false, '{json.dumps(declarations or [])}'::jsonb);
    """, **CTX)


def an_accepted_order(*, declarations: bool = False, coffee: bool = False,
                      table: str = TABLE_ONE, quantity: int = 1) -> dict:
    """An occupancy, a guest, a cart, an accepted order, and the tickets it released.

    Acceptance is what releases the work, so this returns tickets rather than making
    them: nothing in this suite creates a ticket by hand, because a ticket created by
    hand would prove nothing about FR-FUL-001.
    """
    lines = ((VARIANT_DORO_FULL, ITEM_DORO, quantity),)
    if coffee:
        lines = lines + ((VARIANT_COFFEE_ONE, ITEM_COFFEE, 2),)

    session = m3a.fresh_occupancy(table)
    guest = m3a.guest_on(session)
    cart = m3a.cart_with(session, guest, lines=lines)
    concern = m3a.allergy_concern(session, guest) if declarations else None

    submitted = submit_order(
        cart, guest=guest, key=f"m3b-{os.urandom(8).hex()}",
        declarations=[{"allergy_concern_id": concern}] if concern else [])
    if not submitted.ok:
        raise ProbeFailed("submit_order", submitted.err)
    order = (submitted.scalar or "").strip()

    accepted = run(APP, f"SELECT ordering.accept_order('{TENANT}', '{order}', '{USER}');",
                   **CTX)
    if not accepted.ok:
        raise ProbeFailed("accept_order", accepted.err)

    tickets = run(APP, f"""
        SELECT t.id::text, t.station_node_id::text, t.state::text
        FROM fulfillment.ticket t
        WHERE t.tenant_id = '{TENANT}' AND t.order_id = '{order}'
        ORDER BY t.station_sequence;
    """, **CTX)
    if not tickets.ok:
        raise ProbeFailed("tickets", tickets.err)

    return dict(session=session, guest=guest, cart=cart, concern=concern, order=order,
                tickets=[{"id": r[0], "station": r[1], "state": r[2]}
                         for r in tickets.rows])


def reason_code(category: str) -> str:
    return m3a.reason_code(category)


def staff_session() -> tuple[str, str]:
    """A live strong staff session, returning (session_id, bearer_token).

    The token is `tenant.outlet.secret`, the shape M1-D's db.withSession() parses, and the
    database stores only sha256 of the WHOLE token — which is what that function digests.
    M3-A's own helper mints a token of a different shape because nothing at that gate went
    through the HTTP surface; the station routes do, so this one matches.
    """
    secret = os.urandom(16).hex()
    token = f"{TENANT}.{OUTLET_H1}.{secret}"
    res = run(APP, f"""
        INSERT INTO identity.session
            (tenant_id, outlet_id, user_account_id, token_digest, established_with,
             expires_at)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{USER}',
                sha256(convert_to('{token}', 'UTF8')), 'strong', now() + interval '1 hour')
        RETURNING id;
    """, **CTX)
    _fail("staff session", res)
    return (res.scalar or "").strip(), token


def assign_table_owner(table_session_id: str, user_id: str = USER) -> None:
    """Give the occupancy a primary waiter, so a ready notice has somebody to name."""
    res = run(APP, f"""
        INSERT INTO service.table_ownership
            (tenant_id, outlet_id, table_session_id, primary_waiter_user_id,
             assigned_by_user_id)
        SELECT '{TENANT}', '{OUTLET_H1}', '{table_session_id}', '{user_id}', '{USER}'
        WHERE NOT EXISTS (
            SELECT 1 FROM service.table_ownership
             WHERE table_session_id = '{table_session_id}' AND effective_to IS NULL);
    """, **CTX)
    _fail("table ownership", res)
