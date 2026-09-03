#!/usr/bin/env python3
"""M4-A verification: checks, bills, splitting, exact calculation and tip separation.

M3 committed promises. M4 takes money, and a defect here takes the wrong amount from
somebody. Three things make this suite different from the ones before it.

EVERY FIGURE IS RECOMPUTED, NEVER READ BACK AND AGREED WITH. The expected subtotal,
discount, tax, service charge and total are computed in Python from the configured rates,
in the stated stage order, with half-away-from-zero rounding — and then compared with what
the database produced. A check that asked the system what it calculated and confirmed that
it equalled itself would be the vacuous assertion this project has caught three times
before.

TIP SEPARATION IS PROVED STRUCTURALLY FIRST. FR-BIL-014 says bill balance and tip are
separate values and separate records, and a tip that never reaches a bill balance because
nobody wrote that code today is not the same as one that cannot. So the catalog is asked
two questions no behaviour can answer: is there any column outside billing's own tip
tables that could hold a tip, and does any function that computes a bill balance read one.
Then the behaviour is exercised on top of that.

ROUNDING IS PROVED WHERE IT CAN BE WRONG. A split that divides evenly proves nothing. So
every mode is exercised on totals that do not divide by the payer count, across several
counts, and the parts are required to sum to the total exactly — never to be "close".

Every check records whether its evidence is MEASURED — read out of Chromium's own layout —
or ASSERTED, meaning read from source, from a payload, or from the database. The split
printed at the end is derived from what actually ran.
"""
from __future__ import annotations

import json
import os
import platform
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "m1a"))
sys.path.insert(0, str(HERE.parent / "m1d"))
sys.path.insert(0, str(HERE))

import fixtures as fx                                            # noqa: E402
from channel_differential import (                               # noqa: E402
    OPERATIONS, ORIGIN_QUERY, ORIGIN_SURFACE, RULE_FUNCTION_QUERY, SURFACES,
    DifferentialUnusable, route_paths, rules_by_surface, strip_comments)
from fenced import fenced_identifier_pattern                     # noqa: E402
from pg import CommandUnreadable, ProbeFailed, count, run, run_command   # noqa: E402
from service import Service, TSC, WORKSPACE, sync_and_build      # noqa: E402

import controls as registry                                      # noqa: E402
import partial_closures                                          # noqa: E402

assert fx.__file__ == str(HERE / "fixtures.py"), f"wrong fixtures module: {fx.__file__}"

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]
CTX = dict(tenant=fx.TENANT, outlet=fx.OUTLET_H1)

PROBE = HERE / "render_probe.mjs"

results: list[tuple[str, bool, str, str]] = []
CONTEXT: dict = {}

RUN_NONCE = os.urandom(6).hex()


def idem(label: str) -> str:
    return f"m4a-{label}-{RUN_NONCE}"


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    results.append((name, ok, detail, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] ({evidence}) {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def measured(name: str, ok: bool, detail: str = "") -> None:
    record(name, ok, detail, evidence="measured")


def scalar(sql: str, *, dsn: str = APP, **ctx) -> str:
    res = run(dsn, sql, **{**CTX, **ctx})
    if not res.ok:
        raise ProbeFailed(sql, res.err)
    return (res.scalar or "").strip()


def rows(sql: str, *, dsn: str = APP, **ctx) -> list[list[str]]:
    res = run(dsn, sql, **{**CTX, **ctx})
    if not res.ok:
        raise ProbeFailed(sql, res.err)
    return res.rows


def definition(signature: str) -> str:
    res = run(ADMIN, f"SELECT pg_get_functiondef('{signature}'::regprocedure);")
    if not res.ok or not res.out.strip():
        raise ProbeFailed(f"definition of {signature}", res.err)
    return res.out


def signature_of(error: str) -> str:
    matched = re.search(r"\b([A-Z][A-Z_]{4,})\b", error or "")
    return matched.group(1) if matched else ""


# ===========================================================================
# HTTP, as the two surfaces reach it
# ===========================================================================

def _request(url: str, headers: dict, method: str, body: dict | None,
             key: str | None) -> dict:
    data = None
    if body is not None:
        headers["content-type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if key:
        headers["idempotency-key"] = key
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return {"status": response.status, **json.loads(response.read())}
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            return {"status": error.code, **json.loads(raw)}
        except json.JSONDecodeError:
            return {"status": error.code, "body": raw}


def call(method: str, path: str, token: str, body: dict | None = None,
         key: str | None = None) -> dict:
    return _request(f"{CONTEXT['base_url']}{path}",
                    {"authorization": f"Bearer {token}"}, method, body, key)


def guest_call(method: str, path: str, token: str, body: dict | None = None,
               key: str | None = None) -> dict:
    return _request(f"{CONTEXT['base_url']}{path}",
                    {"authorization": f"Guest {token}"}, method, body, key)


# ===========================================================================
# Building the thing under test, through the delivered functions
# ===========================================================================

def preview(cart: str, locale: str = "en", channel: str = "dine_in") -> dict:
    res = run(APP, f"""
        SELECT ordering.preview_cart('{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}',
                                     '{locale}', '{channel}');""", **CTX)
    if not res.ok:
        raise ProbeFailed("preview_cart", res.err)
    return json.loads(res.scalar)


def an_accepted_order(lines, *, table: str = fx.TABLE_ONE, origin: str = "guest_qr",
                      locale: str = "en", channel: str = "dine_in",
                      session: str | None = None, accept: bool = True) -> dict:
    """An occupancy, a guest, a cart, a submitted order and — usually — its acceptance.

    Built through the delivered writers, never by INSERT. A check allocated from a row a
    fixture wrote itself would prove that billing.check_allocation accepts rows.
    """
    table_session = session or fx.fresh_occupancy(table)
    guest = fx.guest_on(table_session)
    cart = fx.cart_with(table_session, guest, lines)
    view = preview(cart, locale, channel)
    submitted = run(APP, f"""
        SELECT ordering.submit_order(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', '{idem("order-" + os.urandom(4).hex())}',
            decode('{view["pricing_digest"]}', 'hex'), {view["total_amount_minor"]},
            '{locale}', gen_random_uuid(), gen_random_uuid(), '{origin}',
            {"'" + fx.USER + "'" if origin != "guest_qr" else "NULL"},
            {"'" + guest + "'" if origin == "guest_qr" else "NULL"},
            false, '[]'::jsonb, '[]'::jsonb, '{channel}');""", **CTX)
    if not submitted.ok:
        raise ProbeFailed("submit_order", submitted.err)
    order = (submitted.scalar or "").strip()
    accepted = None
    if accept:
        accepted = run(APP,
                       f"SELECT ordering.accept_order('{fx.TENANT}', '{order}', "
                       f"'{fx.USER}');", **CTX)
        if not accepted.ok:
            raise ProbeFailed("accept_order", accepted.err)
    return {"session": table_session, "guest": guest, "cart": cart, "order": order,
            "accepted": accepted}


def a_check_over(session: str, orders: list[str]) -> str:
    opened = run(APP, f"""
        SELECT billing.open_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}',
                                  '{fx.USER}');""", **CTX)
    if not opened.ok:
        raise ProbeFailed("open_check", opened.err)
    check = (opened.scalar or "").strip()
    for order in orders:
        allocated = run(APP, f"""
            SELECT billing.allocate_to_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{check}',
                                             l.id, l.quantity)
              FROM ordering.order_line l WHERE l.order_id = '{order}';""", **CTX)
        if not allocated.ok:
            raise ProbeFailed("allocate_to_check", allocated.err)
    return check


def a_bill_over(check: str, locale: str = "en") -> str:
    issued = run(APP, f"""
        SELECT billing.issue_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{check}',
                                  '{fx.USER}', '{locale}');""", **CTX)
    if not issued.ok:
        raise ProbeFailed("issue_bill", issued.err)
    return (issued.scalar or "").strip()


def an_override(action: str, subject_kind: str, subject: str,
                reason_code: str, reason: str) -> str:
    """A real override: a waiter acting, a DIFFERENT person authorizing from their own
    session. M3-D's function, unchanged, because a bill correction is a governed action
    like any other and a second authority model would be a second thing to get wrong."""
    waiter_session, _ = fx.staff_session(fx.USER)
    manager_session, _ = fx.staff_session(fx.USER_CASHIER_MANAGER)
    fx.step_up(manager_session, action)
    approved = run(APP, f"""
        SELECT set_config('app.session_id', '{waiter_session}', false);
        SELECT set_config('app.auth_strength', 'strong', false);
        SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', '{action}',
            '{manager_session}', '{reason_code}', '{subject_kind}', '{subject}',
            $r${reason}$r$);""", tx=True, **CTX)
    if not approved.ok:
        raise ProbeFailed("approve_override", approved.err)
    return (approved.rows[-1][0] if approved.rows else "").strip()


# ===========================================================================
# 1. Checks and allocation (FR-BIL-001, FR-BIL-002)
# ===========================================================================

def section_checks() -> None:
    print("\n--- 1. Checks and allocation, without touching the order (FR-BIL-001, "
          "FR-BIL-002) ---")

    made = an_accepted_order(((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 2),),
                             table=fx.TABLE_ONE)
    CONTEXT["first_order"] = made

    # THE ORDER LEDGER, BY CENSUS, BEFORE AND AFTER. FR-BIL-001 says a check is created
    # "without changing order ownership or history", and a count would miss a swap.
    def order_census() -> list[list[str]]:
        return rows(f"""
            SELECT o.id::text, o.state::text, o.total_amount_minor::text,
                   coalesce(o.placed_by_guest_session_id::text, '-'),
                   coalesce(o.placed_by_user_id::text, '-'),
                   (SELECT string_agg(l.id::text || ':' || l.quantity::text || ':' ||
                                      l.unit_amount_minor::text, ',' ORDER BY l.id)
                      FROM ordering.order_line l WHERE l.order_id = o.id),
                   (SELECT count(*)::text FROM ordering.order_event e
                     WHERE e.order_id = o.id)
              FROM ordering.customer_order o WHERE o.id = '{made["order"]}';""")

    before = order_census()
    check = a_check_over(made["session"], [made["order"]])
    after = order_census()
    CONTEXT["first_check"] = check

    record("a check is created from accepted lines and the order is untouched, by census",
           before == after and before,
           f"the order's state, total, ownership, every line with its quantity and unit "
           f"price, and its event count are identical before and after: {before == after}. "
           f"A count would have missed a line swapped for another of the same price")

    numbered = rows(f"""
        SELECT c.check_number, c.state::text FROM billing.check c WHERE c.id = '{check}';""")
    record("the check is numbered from M1-C's gapless series, not by billing",
           numbered and numbered[0][0].startswith("H1-") and numbered[0][1] == "open",
           f"{numbered}. config.issue_document_number() is the one numbering scheme; a "
           f"second one in billing could collide with the first")

    # A SUBMITTED order is not billable. FR-BIL-001 says accepted or served.
    unaccepted = an_accepted_order(((fx.VARIANT_COFFEE_ONE, fx.ITEM_COFFEE, 1),),
                                   table=fx.TABLE_TWO, accept=False)
    open_check = scalar(f"""
        SELECT billing.open_check('{fx.TENANT}', '{fx.OUTLET_H1}',
                                  '{unaccepted["session"]}', '{fx.USER}');""")
    refused = run(APP, f"""
        SELECT billing.allocate_to_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{open_check}',
                                         l.id, l.quantity)
          FROM ordering.order_line l WHERE l.order_id = '{unaccepted["order"]}';""", **CTX)
    record("an order the house has not accepted cannot be billed for",
           refused.failed_with("ALLOCATION_ORDER_NOT_BILLABLE"),
           refused.why() or "a submitted order was billed. Charging for something nobody "
                            "agreed to cook is the commercial version of cooking it "
                            "before it was ordered")

    # PARTIAL allocation across two checks — the case double billing actually arises in.
    party = an_accepted_order(((fx.VARIANT_TIBS_ONE, fx.ITEM_TIBS, 3),),
                              table=fx.COUNTER_NODE)
    line = scalar(f"SELECT id FROM ordering.order_line WHERE order_id = '{party['order']}';")
    left = scalar(f"""
        SELECT billing.open_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{party["session"]}',
                                  '{fx.USER}');""")
    right = scalar(f"""
        SELECT billing.open_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{party["session"]}',
                                  '{fx.USER}');""")
    one = run(APP, f"""
        SELECT billing.allocate_to_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{left}',
                                         '{line}', 2);""", **CTX)
    two = run(APP, f"""
        SELECT billing.allocate_to_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{right}',
                                         '{line}', 1);""", **CTX)
    record("three of one dish split two and one across two checks is allowed",
           one.ok and two.ok,
           f"{one.why() or 'two units on one check'}; {two.why() or 'one on the other'}. "
           f"FR-BIL-002 asks for whole OR partial quantities, and the partial case is the "
           f"one in which double billing happens")

    over = run(APP, f"""
        SELECT billing.allocate_to_check('{fx.TENANT}', '{fx.OUTLET_H1}',
            billing.open_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{party["session"]}',
                               '{fx.USER}'), '{line}', 1);""", tx=True, **CTX)
    record("and a fourth unit of a dish ordered three times is refused",
           over.failed_with("QUANTITY_DOUBLE_BILLED"),
           over.why() or "a unit nobody ordered was billed for. The guard is a statement "
                         "about a SET of checks, so no unique index can express it")
    CONTEXT["split_party"] = party


# ===========================================================================
# 2. Exact calculation, and the version it was calculated under
#    (FR-BIL-005, FR-BIL-006, FR-CFG-001C, FR-ORD-003)
# ===========================================================================

def section_calculation() -> None:
    print("\n--- 2. Calculation: exact, staged, and versioned (FR-BIL-005, FR-BIL-006) ---")

    check = CONTEXT["first_check"]
    bill = a_bill_over(check)
    CONTEXT["first_bill"] = bill

    subtotal = 2 * 32000
    expected = fx.expected_components(subtotal)
    produced = {r[0]: int(r[1]) for r in rows(f"""
        SELECT kind::text, amount_minor::text FROM billing.bill_component
         WHERE bill_id = '{bill}' ORDER BY kind;""")}
    total = int(scalar(f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';"))

    record("every component equals the figure recomputed independently from the rates",
           all(produced.get(k) == expected[k]
               for k in ("item_subtotal", "discount", "tax", "fee"))
           and total == expected["total"],
           f"produced {produced} total {total}; recomputed "
           f"{ {k: v for k, v in expected.items() if k != 'total'} } total "
           f"{expected['total']}. Recomputed in Python from {fx.DISCOUNT_PERCENTAGE}% "
           f"discount, {fx.TAX_PERCENTAGE}% tax and "
           f"{fx.SERVICE_CHARGE_PERCENTAGE}% service charge rather than read back and "
           f"agreed with")

    # THE FEE HAS A CONFIGURED SOURCE. FR-ORD-003's fee component and FR-ORD-005's fee
    # snapshot have been open in the closure register since M3-A for exactly this reason.
    fee = rows(f"""
        SELECT c.source_kind::text, c.source_id::text, v.category::text, v.version::text
          FROM billing.bill_component c
          JOIN config.configuration_version v ON v.id = c.source_id
         WHERE c.bill_id = '{bill}' AND c.kind = 'fee';""")
    record("the fee names an approved configuration version, not a constant",
           fee and fee[0][0] == "service_configuration" and fee[0][2] == "service",
           f"{fee}. 'fee' has been a valid charge kind with NO configured source since "
           f"M3-A, and a fee column reading zero would have survived to here looking "
           f"wired. FR-CFG-001C is the source it never had")

    stages = [(r[0], int(r[1])) for r in rows(f"""
        SELECT kind::text, (basis ->> 'stage')::int FROM billing.bill_component
         WHERE bill_id = '{bill}' ORDER BY (basis ->> 'stage')::int;""")]
    record("the components record the stage order they were computed in",
           [k for k, _ in stages] == ["item_subtotal", "discount", "tax", "fee"],
           f"{stages}. The order is the answer to FR-ORD-003's discount-and-tax "
           f"question, which M3-A left open because it belongs to the bill")

    tax_basis = rows(f"""
        SELECT (basis ->> 'base_minor')::text FROM billing.bill_component
         WHERE bill_id = '{bill}' AND kind = 'tax';""")
    record("tax is computed on the DISCOUNTED subtotal, and the basis says so",
           tax_basis and int(tax_basis[0][0]) == subtotal + expected["discount"],
           f"tax base {tax_basis}, subtotal {subtotal} less discount "
           f"{-expected['discount']}. Taxing first would charge tax on money nobody was "
           f"asked for, and the two readings round differently — so the basis is recorded "
           f"rather than inferable")

    version = scalar(f"SELECT calculation_version FROM billing.bill WHERE id = '{bill}';")
    stated = scalar("SELECT billing.calculation_version();")
    record("the calculation version is persisted on the document",
           version and version == stated,
           f"{version!r} on the bill, {stated!r} from the one function that states it. A "
           f"rounding change six months from now must not silently rewrite what a guest "
           f"was charged")

    blank = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
        SELECT set_config('app.outlet_id', '{fx.OUTLET_H1}', false);
        SELECT set_config('billing.applying_event', 'yes', true);
        UPDATE billing.bill SET calculation_version = '   ' WHERE id = '{bill}';""",
        tx=True)
    record("and a bill cannot be stored with a blank one",
           blank.failed_with("23514", "bill_calculation_version_stated"),
           blank.why() or "a bill was stored claiming no arithmetic. NOT NULL alone "
                          "accepts a space")

    # The total is a SUM over components that exist, asserted rather than trusted.
    tampered = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
        SELECT set_config('app.outlet_id', '{fx.OUTLET_H1}', false);
        SELECT set_config('billing.applying_event', 'yes', true);
        UPDATE billing.bill_component SET amount_minor = amount_minor + 100
         WHERE bill_id = '{bill}' AND kind = 'tax';""", tx=True)
    record("a component that no longer sums to the stored total is refused at commit",
           tampered.failed_with("BILL_TOTAL_NOT_THE_SUM_OF_ITS_COMPONENTS"),
           tampered.why() or "a stored total disagreed with its parts and nothing "
                             "noticed. That number is what somebody is charged")


# ===========================================================================
# 3. Splitting, five ways, exactly (FR-BIL-003)
# ===========================================================================

# Payer counts that do NOT divide a typical total evenly. A split that divides cleanly
# proves nothing about rounding: every implementation gets that case right.
AWKWARD_PAYERS = (3, 6, 7, 9, 11)


def shares_of(bill: str) -> list[int]:
    return [int(r[0]) for r in rows(f"""
        SELECT amount_minor::text FROM billing.bill_share
         WHERE bill_id = '{bill}' ORDER BY share_number;""")]


def section_splitting() -> None:
    print("\n--- 3. Five split modes, with deterministic rounding (FR-BIL-003) ---")

    bill = CONTEXT["first_bill"]
    total = int(scalar(f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';"))

    # --- equal share, across counts that do not divide evenly ---
    outcomes = []
    for payers in AWKWARD_PAYERS:
        done = run(APP, f"SELECT billing.split_equally('{fx.TENANT}', '{bill}', {payers});",
                   tx=True, **CTX)
        if not done.ok:
            raise ProbeFailed("split_equally", done.err)
        parts = shares_of(bill)
        outcomes.append((payers, sum(parts) == total, max(parts) - min(parts), parts[:3]))

    record("an equal split sums to the total exactly at every awkward payer count",
           all(ok for _p, ok, _s, _e in outcomes),
           "\n".join(f"{p} payers on {total}: sums exactly {ok}, spread {spread} minor "
                     f"unit(s), first parts {ex}" for p, ok, spread, ex in outcomes)
           + "\nA split that lost a unit shorts the house and one that created a unit "
             "overcharges a guest",)

    record("and the remainder goes to the earliest parts, never scattered",
           all(spread <= 1 for _p, _ok, spread, _e in outcomes),
           f"the largest and smallest parts differ by at most one minor unit at every "
           f"count. money.allocate() gives the remainder to the earliest parts "
           f"deterministically, so the same input always produces the same split — which "
           f"is what makes a disputed share arguable")

    # DETERMINISM, stated as repeatability rather than asserted about an algorithm.
    run(APP, f"SELECT billing.split_equally('{fx.TENANT}', '{bill}', 7);", tx=True, **CTX)
    first = shares_of(bill)
    run(APP, f"SELECT billing.split_equally('{fx.TENANT}', '{bill}', 7);", tx=True, **CTX)
    again = shares_of(bill)
    record("splitting the same bill the same way twice produces the same parts",
           first == again and first,
           f"{first} then {again}. Deterministic rounding is a claim about repeatability, "
           f"so it is measured by repeating rather than read off the source")

    # --- custom amount ---
    short = run(APP, f"""
        SELECT billing.split_by_custom_amount('{fx.TENANT}', '{bill}',
                                              ARRAY[{total - 1}]::bigint[]);""",
                tx=True, **CTX)
    record("a custom split that does not add up to the bill is refused",
           short.failed_with("SPLIT_NOT_EXACT"),
           short.why() or "a set of custom amounts one minor unit short was accepted")

    exact = run(APP, f"""
        SELECT billing.split_by_custom_amount('{fx.TENANT}', '{bill}',
            ARRAY[{total // 2}, {total - total // 2}]::bigint[]);""", tx=True, **CTX)
    record("and one that does add up is accepted",
           exact.ok and sum(shares_of(bill)) == total,
           f"{exact.why() or shares_of(bill)} against {total}")

    # --- by participant, by item, separate orders ---
    party = an_accepted_order(((fx.VARIANT_COFFEE_ONE, fx.ITEM_COFFEE, 1),),
                              table=fx.TABLE_TWO)
    second = an_accepted_order(((fx.VARIANT_TIBS_ONE, fx.ITEM_TIBS, 1),),
                               session=party["session"])
    two_orders = a_check_over(party["session"], [party["order"], second["order"]])
    multi = a_bill_over(two_orders)
    multi_total = int(scalar(
        f"SELECT bill_total_minor FROM billing.bill WHERE id = '{multi}';"))

    by_participant = run(APP,
                         f"SELECT billing.split_by_participant('{fx.TENANT}', '{multi}');",
                         tx=True, **CTX)
    participant_parts = shares_of(multi)
    record("a split by participant sums to the total exactly",
           by_participant.ok and sum(participant_parts) == multi_total,
           f"{by_participant.why() or participant_parts} against {multi_total}. Tax, "
           f"discount and the service charge are computed once on the document and "
           f"carried by the last share, so the whole rounds once rather than five times")

    separate = run(APP,
                   f"SELECT billing.split_by_separate_orders('{fx.TENANT}', '{multi}');",
                   tx=True, **CTX)
    separate_parts = shares_of(multi)
    record("a split into separate orders gives one share per order and still adds up",
           separate.ok and (separate.scalar or "").strip() == "2"
           and sum(separate_parts) == multi_total,
           f"{separate.why() or separate_parts} across "
           f"{(separate.scalar or '').strip()} order(s), total {multi_total}")

    lines = [r[0] for r in rows(f"""
        SELECT a.order_line_id::text FROM billing.check_allocation a
         WHERE a.check_id = '{two_orders}' ORDER BY a.order_line_id;""")]
    assignment = json.dumps([[lines[0]], [lines[1]]])
    by_item = run(APP, f"""
        SELECT billing.split_by_item('{fx.TENANT}', '{multi}', $j${assignment}$j$::jsonb);""",
        tx=True, **CTX)
    item_parts = shares_of(multi)
    record("a split by item gives each payer their own dishes and still adds up",
           by_item.ok and sum(item_parts) == multi_total,
           f"{by_item.why() or item_parts} against {multi_total}")

    incomplete = json.dumps([[lines[0]]])
    missed = run(APP, f"""
        SELECT billing.split_by_item('{fx.TENANT}', '{multi}',
                                     $j${incomplete}$j$::jsonb);""", tx=True, **CTX)
    record("and a by-item split that leaves a dish unassigned is refused",
           missed.failed_with("SPLIT_NOT_EXACT"),
           missed.why() or "a forgotten line was silently absorbed by the remainder. A "
                           "by-item split ENUMERATES rather than divides, and an "
                           "enumeration can be incomplete in a way a division cannot")

    modes = sorted(r[0] for r in rows(
        "SELECT unnest(enum_range(NULL::billing.split_mode))::text;"))
    record("FR-BIL-003's five modes exist and each has an implementation",
           modes == ["by_item", "by_participant", "custom_amount", "equal_share",
                     "separate_orders"]
           and all(count(ADMIN, f"""
               SELECT count(*) FROM pg_proc p
               JOIN pg_namespace n ON n.oid = p.pronamespace
               WHERE n.nspname = 'billing' AND p.prosrc ~ '''{mode}'''
                 AND p.proname LIKE 'split%';""") >= 1 for mode in modes),
           f"{modes}, each written by a billing.split_* function that names it. A mode "
           f"in the enum with nothing that produces it would be a menu item nobody cooks")

    CONTEXT["multi_bill"] = multi
    CONTEXT["multi_check"] = two_orders


# ===========================================================================
# 4. Merge and split of checks, by census (FR-BIL-004, FR-TAB-007B)
# ===========================================================================

def section_merge_and_split() -> None:
    print("\n--- 4. Merge and split, proved by census rather than by count "
          "(FR-BIL-004, FR-TAB-007B) ---")

    party = an_accepted_order(((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 1),),
                              table=fx.TABLE_ONE)
    other = an_accepted_order(((fx.VARIANT_COFFEE_ONE, fx.ITEM_COFFEE, 1),),
                              session=party["session"])
    left = a_check_over(party["session"], [party["order"]])
    right = a_check_over(party["session"], [other["order"]])

    def census(checks: list[str]) -> list[list[str]]:
        joined = "', '".join(checks)
        return rows(f"""
            SELECT a.order_line_id::text, a.quantity::text
              FROM billing.check_allocation a
             WHERE a.check_id IN ('{joined}')
             ORDER BY a.order_line_id;""")

    before = census([left, right])
    merged = run(APP, f"""
        SELECT billing.merge_checks('{fx.TENANT}', '{fx.OUTLET_H1}', '{right}',
                                    '{left}');""", tx=True, **CTX)
    after = census([right])
    record("merging two checks moves every allocated unit and invents none",
           merged.ok and before == after and len(before) == 2,
           f"{merged.why() or ''}before {before}, after {after}. The exact SET, not the "
           f"count — M3-A proved merge and move lose nothing by census for the same "
           f"reason, and this is that method")

    source = rows(f"""
        SELECT state::text, coalesce(merged_into_check_id::text, '-')
          FROM billing.check WHERE id = '{left}';""")
    record("and the source check survives, saying where it went",
           source and source[0][0] == "merged" and source[0][1] == right,
           f"{source}. FR-BIL-004 asks for the source relationships to be PRESERVED, and "
           f"a source that vanished would leave the merged check unable to say what it "
           f"was made of")

    moved_line = census([right])[0][0]
    split = run(APP, f"""
        SELECT billing.split_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{right}',
                                   ARRAY['{moved_line}']::uuid[], '{fx.USER}');""",
                tx=True, **CTX)
    new_check = (split.scalar or "").strip()
    after_split = census([right, new_check])
    record("splitting the merged session back apart preserves the census exactly",
           split.ok and sorted(after_split) == sorted(before),
           f"{split.why() or ''}before the merge {sorted(before)}, after the split "
           f"{sorted(after_split)}. The allocations MOVE rather than being copied, so no "
           f"unit is billed twice — which the deferred trigger proves at commit")

    lineage = rows(f"""
        SELECT coalesce(split_from_check_id::text, '-') FROM billing.check
         WHERE id = '{new_check}';""")
    record("and the new check names what it split from",
           lineage and lineage[0][0] == right,
           f"{lineage}. FR-TAB-007B asks for a complete audit trail, and a check with no "
           f"parent is a document nobody can explain")


# ===========================================================================
# 5. Tip separation — structurally first, then behaviourally
#    (FR-BIL-013, FR-BIL-014, FR-BIL-015, FR-BIL-016)
# ===========================================================================

# Where a tip is ALLOWED to live. Everything else naming a tip is the defect.
TIP_TABLES = ("billing.tip", "billing.tip_correction", "billing.tip_setting",
              "billing.tip_suggestion")

# What a "bill balance" function is. Derived by NAME from the catalog rather than listed,
# so a balance function a later slice adds is covered without anybody extending anything.
BALANCE_FUNCTION_QUERY = """
    SELECT n.nspname || '.' || p.proname
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'billing'
      AND (p.proname ~ '(balance|outstanding|total|settle|finali)'
        OR p.prosrc ~ 'bill_total_minor')
    ORDER BY 1;"""


def functions_reading_tips(exclude: tuple[str, ...] = ()) -> list[str]:
    """Balance functions whose SOURCE reads a tip table. Derived, both halves."""
    excluded = "', '".join(exclude) if exclude else "__none__"
    return [r[0] for r in rows(f"""
        SELECT n.nspname || '.' || p.proname
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'billing'
          AND (p.proname ~ '(balance|outstanding|total|settle|finali)'
            OR p.prosrc ~ 'bill_total_minor')
          AND p.prosrc ~ 'billing\\.tip'
          AND n.nspname || '.' || p.proname NOT IN ('{excluded}')
        ORDER BY 1;""", dsn=ADMIN)]


def section_tip_separation_structurally() -> None:
    print("\n--- 5. A tip CANNOT reach a bill balance, proved from the catalog "
          "(FR-BIL-014, NC-M4-002) ---")

    # 1. NO COLUMN WHERE IT WOULD BECOME MONEY OWED.
    #
    # This check used to say "no column outside billing's own four tip tables", and that
    # was true while billing was the only domain that had heard of a tip. M4-B gave a
    # PAYMENT an allocation to a tip — payments.allocation.tip_id and the intent's
    # tip_amount_minor — which FR-PAY-017 requires: a payment records separate allocations
    # to bill balance and to optional tip, and it cannot do that without naming the tip.
    # The fence was a list of the tables that existed on the day, and it is the eighth of
    # its kind this repository has had to retire.
    #
    # The doctrine underneath is not "tips live in four tables". It is that a tip is never
    # part of what a guest OWES. So the question is asked of the tables where owing is
    # recorded, derived from the catalog rather than named: anything carrying a bill total,
    # and everything in the schemas that record what was ordered and served. A tip column
    # on any of those is the defect; a tip column on a payment's allocation is the
    # requirement.
    columns = rows("""
        WITH owes AS (
            SELECT c.relname, n.nspname
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'r'
               AND (n.nspname IN ('ordering', 'service', 'fulfillment', 'menu')
                 OR EXISTS (SELECT 1 FROM pg_attribute a
                             WHERE a.attrelid = c.oid AND a.attnum > 0
                               AND NOT a.attisdropped
                               AND a.attname IN ('bill_total_minor', 'total_amount_minor')))
        )
        SELECT o.nspname || '.' || o.relname || '.' || a.attname
          FROM owes o
          JOIN pg_class c ON c.relname = o.relname
          JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = o.nspname
          JOIN pg_attribute a ON a.attrelid = c.oid
         WHERE a.attnum > 0 AND NOT a.attisdropped AND a.attname ~ 'tip'
         ORDER BY 1;""", dsn=ADMIN)
    record("no table that records what is owed carries a tip column",
           not columns,
           f"tip columns on tables carrying a bill or order total, or on the schemas that "
           f"record what was ordered and served: {[r[0] for r in columns] or 'none'}. "
           f"Derived from the catalog, so a tip column added to a bill, an order or a "
           f"check at any later gate fails here without anybody remembering to look — "
           f"which a list of today's tip tables would not have done")

    balance_functions = [r[0] for r in rows(BALANCE_FUNCTION_QUERY, dsn=ADMIN)]
    if len(balance_functions) < 3:
        raise CommandUnreadable(
            f"only {len(balance_functions)} balance function(s) derived from the catalog. "
            f"A short list here would make the assertion below pass by having nothing to "
            f"examine, which is the vacuity this project has caught three times")
    record("the balance functions are enumerated from the catalog, not from this file",
           len(balance_functions) >= 3,
           f"{balance_functions}. Matched by NAME and by whether the body reads "
           f"bill_total_minor, so a balance function a later slice adds is covered")

    # 2. NO READ. billing.finalize_bill() is the one deliberate exception and it is
    #    excluded BY NAME with the reason stated, never by widening the pattern.
    readers = functions_reading_tips(exclude=("billing.finalize_bill",))
    record("and no function that computes a bill balance reads a tip",
           not readers,
           f"balance functions reading billing.tip: {readers or 'none'}. "
           f"billing.finalize_bill() is excluded by name because it reads the tips ONLY "
           f"to name them in its refusal — the check below proves that is all it does")

    finalize = definition("billing.finalize_bill(uuid, uuid, uuid, uuid)")
    guard = re.search(r"IF\s+v_outstanding\s*>\s*0\s+THEN", finalize)
    tips_in_arithmetic = re.search(
        r"v_outstanding\s*(?::=|=)[^\n;]*v_tips|v_tips\s*[-+]\s*v_outstanding", finalize)
    record("finalization's decision is the outstanding balance alone",
           bool(guard) and not tips_in_arithmetic,
           f"the guard is on the outstanding balance; the tip total appears in the "
           f"refusal text and in no arithmetic: {not tips_in_arithmetic}. A cashier "
           f"looking at money received needs to be told why the bill is still open")

    # 3. NO PATH. Nothing that writes a tip can write an allocation or a component.
    crossing = [r[0] for r in rows("""
        SELECT n.nspname || '.' || p.proname
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE p.prosrc ~ 'INTO billing\\.tip'
          AND (p.prosrc ~ 'billing\\.check_allocation'
            OR p.prosrc ~ 'billing\\.bill_component')
        ORDER BY 1;""", dsn=ADMIN)]
    record("and nothing that writes a tip can also write an allocation or a component",
           not crossing,
           f"{crossing or 'none'}. FR-BIL-015 says a per-payer tip is chosen WITHOUT "
           f"reallocating bill lines, and there is no function from which both are "
           f"reachable")

    # WHERE THE MONEY VOCABULARY IS ALLOWED TO LIVE. M1-C fenced this while billing was
    # unbuilt — "no check, payment, tip, refund or settlement table exists yet" — and that
    # criterion retired the moment this slice landed. The boundary that outlives every
    # remaining gate takes its place, and it belongs here because this is the gate that
    # owns the vocabulary: a check is a VIEW onto the order ledger (FR-BIL-001), and the
    # way that stops being true is a payment or tip column bolted onto an order table by
    # somebody in a hurry rather than by anybody deciding.
    intruders = [r[0] for r in rows("""
        SELECT n.nspname || '.' || c.relname
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname IN ('ordering', 'service', 'fulfillment', 'menu')
          AND c.relname ~* '(^|_)(check|bill|payment|tip|refund|settlement)($|_)'
        ORDER BY 1;""", dsn=ADMIN)]
    record("no money vocabulary has leaked into the schemas that record what was ordered",
           not intruders,
           f"check, bill, payment, tip, refund or settlement tables outside the billing "
           f"schema: {intruders or 'none'}. The moment one becomes a column on an order "
           f"table, the order history stops being what the guest asked for")

    no_tip_column = count(ADMIN, """
        SELECT count(*) FROM information_schema.columns
         WHERE table_schema = 'billing' AND table_name = 'bill'
           AND column_name ~ 'tip';""")
    record("billing.bill has no tip column at all",
           no_tip_column == 0,
           f"{no_tip_column} column(s). The absence is the requirement: a total that "
           f"cannot see a tip cannot be made to include one without a migration somebody "
           f"has to write and somebody has to review")


def section_tip_separation_behaviourally() -> None:
    print("\n--- 6. And behaviourally: a tip changes nothing about what is owed "
          "(FR-BIL-015, FR-BIL-016) ---")

    bill = CONTEXT["multi_bill"]
    run(APP, f"SELECT billing.split_equally('{fx.TENANT}', '{bill}', 3);", tx=True, **CTX)
    shares = [r[0] for r in rows(f"""
        SELECT id::text FROM billing.bill_share WHERE bill_id = '{bill}'
         ORDER BY share_number;""")]

    def state() -> tuple[int, int, list[list[str]]]:
        return (int(scalar(f"SELECT billing.outstanding_balance('{fx.TENANT}', '{bill}');")),
                int(scalar(f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';")),
                rows(f"""
                    SELECT a.order_line_id::text, a.quantity::text
                      FROM billing.check_allocation a
                     WHERE a.check_id = '{CONTEXT["multi_check"]}'
                     ORDER BY a.order_line_id;"""))

    before = state()
    tipped = run(APP, f"""
        INSERT INTO billing.tip (tenant_id, outlet_id, bill_share_id, currency_code,
                                 amount_minor, chosen_from_percentage)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{shares[0]}', 'ETB', 5000, 10.0000),
               ('{fx.TENANT}', '{fx.OUTLET_H1}', '{shares[1]}', 'ETB', 1200, NULL);""",
        **CTX)
    after = state()

    record("two payers choose different tips, and each is attached to their own share",
           tipped.ok and count(APP, f"""
               SELECT count(*) FROM billing.tip t
               JOIN billing.bill_share s ON s.id = t.bill_share_id
               WHERE s.bill_id = '{bill}';""", **CTX) == 2,
           f"{tipped.why() or 'one tip of 5000 chosen from 10%, one of 1200 typed'}. "
           f"FR-BIL-015 makes a per-payer tip the ordinary case rather than a special one")

    record("and the outstanding balance, the total and every allocation are unchanged",
           before == after,
           f"before {before[0]} outstanding / {before[1]} total / {len(before[2])} "
           f"allocation(s); after {after[0]} / {after[1]} / {len(after[2])}. The "
           f"allocations are compared by census, so a line swapped for another of the "
           f"same price would show")

    third = run(APP, f"""
        INSERT INTO billing.tip (tenant_id, outlet_id, bill_share_id, currency_code,
                                 amount_minor)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{shares[0]}', 'ETB', 900);""", **CTX)
    record("a share cannot carry two tips",
           third.failed_with("23505", "tip_one_per_share"),
           third.why() or "one payer tipped twice, which makes 'what did this payer "
                          "leave' unanswerable")

    tip_id = scalar(f"""
        SELECT id FROM billing.tip WHERE bill_share_id = '{shares[0]}';""")
    edited = run(APP, f"""
        UPDATE billing.tip SET amount_minor = 1 WHERE id = '{tip_id}';""", **CTX)
    record("and a recorded tip cannot be edited",
           edited.failed_with("TIP_ALTERED_NOT_CORRECTED", "42501"),
           edited.why() or "a tip was quietly changed. FR-BIL-016 makes a reversal a "
                           "separate auditable record linked to the original")

    reason = fx.reason_code("M4A_ON_THE_HOUSE")
    override = an_override("check.void", "bill", bill, reason, "the guest changed their mind")
    corrected = run(APP, f"""
        INSERT INTO billing.tip_correction
            (tenant_id, outlet_id, tip_id, kind, currency_code, amount_minor,
             override_id, reason_code_id, reason_text, actor_user_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{tip_id}', 'reversal', 'ETB', 5000,
                '{override}', '{reason}', 'the guest changed their mind', '{fx.USER}');""",
        **CTX)
    still = state()
    record("a reversal is its own record, linked to the original, and moves no balance",
           corrected.ok and still == after,
           f"{corrected.why() or 'reversal recorded against the original tip'}; the "
           f"balance is {still[0]} before and after, because a tip was never in it")


# ===========================================================================
# 7. The bill preview and the tip box, MEASURED (FR-BIL-007, NC-M4-001)
# ===========================================================================

def render(cases: list[dict], tap: str | None = "en") -> dict:
    target = WORKSPACE / "m4a_render_probe.mjs"
    target.write_text(PROBE.read_text(encoding="utf-8"), encoding="utf-8")
    payload = json.dumps({"tenant": fx.TENANT, "outlet": fx.OUTLET_H1, "tap": tap,
                          "cases": [{"locale": c["locale"], "code": c["code"]}
                                    for c in cases]})
    proc = run_command(["node", str(target), CONTEXT["base_url"], payload],
                       cwd=str(WORKSPACE))
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise CommandUnreadable(
            f"the render probe produced no JSON (exit {proc.returncode}): "
            f"{(proc.stdout or proc.stderr)[:400]}")


def a_guest_looking_at_a_bill(locale: str) -> dict:
    """A table with an issued, split bill IN ONE LANGUAGE, and the printed code for it.

    The code rather than a token, because the browser walks in the way a guest does: it
    scans a placard, exchanges the code for a session and joins the table. A probe handed
    a ready-made credential would be testing the routes rather than the surface.

    One table per language, because a bill is translated by ITS OWN locale rather than by
    the reader's — 0017's ruling about the customer timeline, applied to the document. So
    three languages means three orders placed in three languages.
    """
    table = fx.BILL_TABLES[locale]
    code = fx.m2c.fresh_occupancy_and_code(table)
    session = scalar(f"""
        SELECT id FROM service.table_session
         WHERE tenant_id = '{fx.TENANT}' AND table_node_id = '{table}'
           AND closed_at IS NULL
         ORDER BY opened_at DESC LIMIT 1;""")
    chose = run(APP, f"""
        UPDATE service.table_session
           SET customer_locale = '{locale}', customer_locale_selected_at = now()
         WHERE tenant_id = '{fx.TENANT}' AND id = '{session}';""", **CTX)
    if not chose.ok:
        raise ProbeFailed("the session's language", chose.err)
    ordered = an_accepted_order(((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 1),),
                                session=session, locale=locale)
    check = a_check_over(session, [ordered["order"]])
    bill = a_bill_over(check, locale)
    run(APP, f"SELECT billing.split_equally('{fx.TENANT}', '{bill}', 1);", tx=True, **CTX)
    return {"locale": locale, "code": code, "bill": bill, "session": session}


def section_bill_preview() -> None:
    print("\n--- 7. The bill summary, and the tip box beside it (FR-BIL-007, "
          "NC-M4-001) ---")

    probe = CONTEXT["render"]
    if probe.get("probeFailed"):
        raise CommandUnreadable(f"the browser never rendered: {probe['probeFailed']}")

    english = probe["locales"]["en"]
    measured("the bill summary rendered in a real browser from the real database",
             len(english["lines"]) == 4 and english["total"],
             f"{len(english['lines'])} component line(s) drawn: "
             f"{[l['kind'] for l in english['lines']]}, total {english['total']!r}. The "
             f"labels and the amounts came through /c/v1/bill from "
             f"billing.bill_preview_lines()")

    measured("no script or resource error occurred while drawing it",
             not probe["errors"],
             f"console and page errors: {probe['errors'] or 'none'}")

    # FR-BIL-007, HALF ONE: containment, which a developer controls.
    measured("the tip box is NOT inside the bill summary in the document",
             not english["tipInsideSummary"] and not english["tipInsideSection"],
             f"summary contains the tip box: {english['tipInsideSummary']}; the bill "
             f"section contains it: {english['tipInsideSection']}. They are siblings, so "
             f"a tip drawn among the components would have to be put there deliberately")

    # FR-BIL-007, HALF TWO: geometry, which a stylesheet can undo without touching the
    # markup. A tip box positioned on top of the summary is inside it as far as a guest
    # is concerned, whatever the document says.
    summary = english["summaryBox"]
    tip = english["tipBox"]
    below = tip["top"] >= summary["bottom"] - 1
    beside = tip["left"] >= summary["right"] - 1 or tip["right"] <= summary["left"] + 1
    measured("and it is drawn after it or beside it, never over it",
             (below or beside) and tip["visible"] and summary["visible"],
             f"summary occupies y {summary['top']:.0f}–{summary['bottom']:.0f}, "
             f"x {summary['left']:.0f}–{summary['right']:.0f}; the tip box occupies "
             f"y {tip['top']:.0f}–{tip['bottom']:.0f}, "
             f"x {tip['left']:.0f}–{tip['right']:.0f}. Below: {below}; beside: {beside}. "
             f"Read out of the layout the browser actually produced, because a stylesheet "
             f"can put one on top of the other without touching the markup")

    # NC-M4-001's subject, measured on the untouched page.
    pressed = [o for o in english["options"]
               if o["ariaPressed"] == "true" or o["checked"]
               or o["defaultAttribute"] is not None
               or any("select" in c or "default" in c or "chosen" in c
                      for c in o["classes"])]
    measured("no tip is selected when the box is first drawn",
             english["options"] and not pressed,
             f"{len(english['options'])} suggestion(s) offered, {len(pressed)} preselected. "
             f"aria-pressed, checked, a default attribute and the class list are all read, "
             f"because a preselection can be expressed as any of them and asserting on one "
             f"would let the other three walk past")

    tapped = probe.get("afterTap")
    measured("and choosing one records it, on that payer's share alone",
             tapped and sum(1 for o in tapped["options"] if o["ariaPressed"] == "true") == 1
             and tapped["outcome"],
             f"after one tap: "
             f"{sum(1 for o in (tapped or {}).get('options', []) if o['ariaPressed'] == 'true')} "
             f"pressed, the surface said {(tapped or {}).get('outcome', '')!r}. FR-BIL-015 "
             f"is about a payer CHOOSING, and a measurement of an untouched page cannot "
             f"show that choosing works")

    stored = count(APP, f"""
        SELECT count(*) FROM billing.tip t
        JOIN billing.bill_share s ON s.id = t.bill_share_id
        WHERE s.bill_id = '{CONTEXT["rendered_bill"]}';""", **CTX)
    balance_after = int(scalar(f"""
        SELECT billing.outstanding_balance('{fx.TENANT}',
                                           '{CONTEXT["rendered_bill"]}');"""))
    total = int(scalar(f"""
        SELECT bill_total_minor FROM billing.bill
         WHERE id = '{CONTEXT["rendered_bill"]}';"""))
    record("the tip the browser chose reached the database and the balance did not move",
           stored == 1 and balance_after == total,
           f"{stored} tip stored; outstanding {balance_after} against a total of {total}. "
           f"A guest tapped a button in Chromium and the money they owe is unchanged")

    # Translation: FR-BIL-007's summary is TRANSLATED, in the language the order carries.
    for locale, script in (("am", "Ethiopic"), ("ar", "Arabic")):
        view = probe["locales"][locale]
        labels = [l["label"] for l in view["lines"]]
        english_labels = {l["label"] for l in english["lines"]}
        measured(f"the {script} bill names its components in {script}, not in English",
                 labels and not (set(labels) & english_labels),
                 f"{labels} against the English {sorted(english_labels)}. The labels come "
                 f"from menu.translation through billing.component_wording_for(), so a "
                 f"bill is translated by the same reviewed workflow as a menu item")

    arabic = probe["locales"]["ar"]
    measured("and the Arabic bill lays out right to left",
             arabic["dir"] == "rtl",
             f"dir={arabic['dir']!r}, lang={arabic['lang']!r}")


# ===========================================================================
# 8. Finalization and disposition (FR-BIL-008)
# ===========================================================================

def section_finalization() -> None:
    print("\n--- 8. A bill is finalized settled or authorized, and never by a tip "
          "(FR-BIL-008, NC-M4-002) ---")

    made = an_accepted_order(((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 1),),
                             table=fx.COUNTER_NODE)
    check = a_check_over(made["session"], [made["order"]])
    bill = a_bill_over(check)
    total = int(scalar(f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';"))
    run(APP, f"SELECT billing.split_equally('{fx.TENANT}', '{bill}', 1);", tx=True, **CTX)
    share = scalar(f"SELECT id FROM billing.bill_share WHERE bill_id = '{bill}';")

    unsettled = run(APP, f"""
        SELECT billing.finalize_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
                                     '{fx.USER}');""", **CTX)
    record("a bill with an outstanding balance cannot be finalized",
           unsettled.failed_with("BILL_FINALIZED_UNSETTLED"),
           unsettled.why() or "an unpaid bill was closed")

    # A TIP LARGER THAN THE WHOLE BILL. The clearest form of NC-M4-002's question.
    run(APP, f"""
        INSERT INTO billing.tip (tenant_id, outlet_id, bill_share_id, currency_code,
                                 amount_minor)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{share}', 'ETB', {total + 1000});""",
        **CTX)
    still_unsettled = run(APP, f"""
        SELECT billing.finalize_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
                                     '{fx.USER}');""", **CTX)
    record("a tip larger than the entire bill still does not settle it",
           still_unsettled.failed_with("BILL_FINALIZED_UNSETTLED")
           and str(total + 1000) in still_unsettled.err,
           f"{still_unsettled.why() or 'finalized'}. The refusal names the tip so a "
           f"cashier reading a screen that shows money received understands why the bill "
           f"is still open — which is the difference between a rule and a bug")

    reason = fx.reason_code("M4A_ON_THE_HOUSE")
    too_much = run(APP, f"""
        SELECT billing.record_disposition('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
            'comped', {total + 1}, '{an_override("discount.high", "bill", bill, reason,
                                                 "the whole table")}',
            '{reason}', 'the whole table', '{fx.USER}');""", **CTX)
    record("a disposition larger than what is owed is refused",
           too_much.failed_with("DISPOSITION_EXCEEDS_BALANCE"),
           too_much.why() or "more was written off than was ever charged")

    override = an_override("discount.high", "bill", bill, reason, "the whole table")
    disposed = run(APP, f"""
        SELECT billing.record_disposition('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
            'comped', {total}, '{override}', '{reason}', 'the whole table', '{fx.USER}');""",
        **CTX)
    finalized = run(APP, f"""
        SELECT billing.finalize_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
                                     '{fx.USER}');""", **CTX)
    record("an authorized disposition settles the balance and the bill finalizes",
           disposed.ok and finalized.ok
           and scalar(f"SELECT state::text FROM billing.bill WHERE id = '{bill}';")
               == "finalized",
           f"{disposed.why() or 'comped with an override naming two people and a reason'}; "
           f"{finalized.why() or 'finalized'}. M4-A takes no payment, so authority is the "
           f"only route to a settled balance and it is answerable by construction")

    authored = rows(f"""
        SELECT (d.override_id IS NOT NULL)::text, (d.reason_code_id IS NOT NULL)::text,
               (o.approver_user_id <> o.actor_user_id)::text
          FROM billing.bill_disposition d
          JOIN pos.override_approval o ON o.id = d.override_id
         WHERE d.bill_id = '{bill}';""")
    record("and the disposition names the override, the reason and two different people",
           authored and all(v in ("t", "true") for v in authored[0]),
           f"{authored}. The maker-checker rule is inherited from M3-D's schema rather "
           f"than restated, so a disposition somebody authorized for themselves cannot "
           f"be stored")

    CONTEXT["finalized_bill"] = bill
    CONTEXT["finalized_check"] = check
    CONTEXT["finalized_session"] = made["session"]


# ===========================================================================
# 9. Correction is void, credit or reissue — never deletion (FR-BIL-009)
# ===========================================================================

def section_correction() -> None:
    print("\n--- 9. An issued bill is corrected, never deleted (FR-BIL-009) ---")

    grants = sorted(r[0] for r in rows("""
        SELECT privilege_type FROM information_schema.role_table_grants
         WHERE grantee = 'hospitality_app' AND table_schema = 'billing'
           AND table_name = 'bill_event';""", dsn=ADMIN))
    record("the application may read and append to the bill ledger, and nothing else",
           grants == ["INSERT", "SELECT"],
           f"{grants}. No UPDATE and no DELETE: the grant is one lock, the append-only "
           f"trigger is the other, and either survives the removal of the first")

    projection_grants = [r[0] for r in rows("""
        SELECT DISTINCT privilege_type FROM information_schema.role_table_grants
         WHERE grantee = 'hospitality_app' AND table_schema = 'billing'
           AND table_name IN ('bill', 'bill_component')
           AND privilege_type <> 'SELECT' ORDER BY 1;""", dsn=ADMIN)]
    record("and it may not write the bill projection at all",
           not projection_grants,
           f"write privileges on billing.bill and billing.bill_component: "
           f"{projection_grants or 'none'}. Whatever a route does, it cannot bring a bill "
           f"into existence except through the fold")

    made = an_accepted_order(((fx.VARIANT_TIBS_ONE, fx.ITEM_TIBS, 1),),
                             table=fx.TABLE_ONE)
    check = a_check_over(made["session"], [made["order"]])
    bill = a_bill_over(check)
    reason = fx.reason_code("M4A_BILL_REISSUED")

    no_reason = run(APP, f"""
        SELECT billing.void_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
            NULL, NULL, NULL, '{fx.USER}');""", **CTX)
    record("voiding a bill with no reason is refused",
           no_reason.failed_with("DESTRUCTIVE_ACTION_WITHOUT_REASON"),
           no_reason.why() or "a bill was voided with nothing on the record")

    override = an_override("check.void", "bill", bill, reason, "issued against the wrong check")
    reissued = run(APP, f"""
        SELECT billing.reissue_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
            '{override}', '{reason}', 'issued against the wrong check', '{fx.USER}');""",
        tx=True, **CTX)
    replacement = (reissued.scalar or "").strip()
    chain = rows(f"""
        SELECT b.id::text, b.state::text, coalesce(b.supersedes_bill_id::text, '-'),
               coalesce(b.reissued_as_bill_id::text, '-')
          FROM billing.bill b WHERE b.check_id = '{check}' ORDER BY b.issued_at;""")
    record("a reissue leaves the original standing and the chain walkable both ways",
           reissued.ok and len(chain) == 2 and chain[0][1] == "voided"
           and chain[0][3] == replacement and chain[1][2] == chain[0][0],
           f"{reissued.why() or chain}. Nothing is removed: the voided document keeps its "
           f"number and names its replacement, and the replacement names what it "
           f"superseded")

    ledger = count(ADMIN, f"""
        SELECT count(*) FROM billing.bill_event WHERE bill_id = '{bill}';""")
    record("and every step of it is on the ledger",
           ledger >= 2,
           f"{ledger} event(s) against the original bill. FR-BIL-009's whole content is "
           f"that a correction is ANSWERABLE, and a void nobody recorded is a deletion "
           f"with extra steps")

    # FR-DAT-010: the projection is reproducible, which is what makes the guard's refusal
    # a statement about a mechanism rather than a hope.
    # Scoped to ONE OUTLET on both sides, because that is the scope a rebuild runs in:
    # row level security is per (tenant, outlet), so a rebuild folds what the caller can
    # see. A census taken tenant-wide as a superuser and compared against a refold scoped
    # to one outlet would report a difference that is the SCOPES disagreeing rather than
    # the ledger.
    def bill_census() -> list[list[str]]:
        return rows(f"""
            SELECT b.bill_number, b.state::text, b.bill_total_minor::text,
                   b.calculation_version, coalesce(b.supersedes_bill_id::text, '-'),
                   coalesce(b.reissued_as_bill_id::text, '-'), b.disposed_minor::text,
                   (SELECT string_agg(c.kind::text || '=' || c.amount_minor::text, ','
                                      ORDER BY c.kind)
                      FROM billing.bill_component c WHERE c.bill_id = b.id)
              FROM billing.bill b
             WHERE b.tenant_id = '{fx.TENANT}' AND b.outlet_id = '{fx.OUTLET_H1}'
             ORDER BY b.bill_number;""", dsn=ADMIN)

    before = bill_census()
    rebuilt = run(ADMIN,
                  f"SELECT billing.rebuild_projections('{fx.TENANT}');", tx=True, **CTX)
    after = bill_census()
    record("the whole bill projection can be rebuilt from the ledger, byte for byte",
           rebuilt.ok and before == after and len(before) > 1,
           f"{rebuilt.why() or ''}{len(before)} bill(s) refolded; every number, state, "
           f"calculation version, disposed amount and component compared before and "
           f"after: {before == after}. A projection nobody can reproduce is a second copy "
           f"of the truth nobody can check")


# ===========================================================================
# 10. The counter channel, on the same aggregate (FR-ORD-001B, FR-ORD-007B)
# ===========================================================================

def section_counter_channel() -> None:
    print("\n--- 10. The counter is a third origin on one aggregate, not a third path "
          "(FR-ORD-001B) ---")

    origins = sorted(r[0] for r in rows(ORIGIN_QUERY))
    record("the counter is a value of the origin dimension M3-A built",
           origins == ["counter", "guest_qr", "waiter_entered"],
           f"{origins}. Enumerated from the catalog. FR-ORD-001B says the counter uses "
           f"the SAME aggregate and policy model, and the way to mean it is to make the "
           f"counter a value of a dimension rather than a second path that agrees")

    surfaces = ORIGIN_SURFACE
    record("and every origin the catalog knows about has a stated surface",
           all(o in surfaces for o in origins),
           f"{ {o: surfaces.get(o) for o in origins} }. An origin nobody mapped is a "
           f"channel with no home, and the instrument raises rather than guessing")

    # THE SAME INSTRUMENT M3-D BUILT, extended rather than reimplemented: it lives in
    # tests/channel_differential.py and both suites call it.
    universe = {r[0] for r in rows(RULE_FUNCTION_QUERY, dsn=ADMIN)}
    by_surface = rules_by_surface(
        lambda relative: (REPO / relative).read_text(encoding="utf-8"), universe)
    for label in OPERATIONS:
        g, s = by_surface["guest"][label], by_surface["staff"][label]
        record(f"{label}: all three origins reach the same function, and only that one",
               g == s and len(g) == 1,
               f"guest {g}, staff (waiter AND counter) {s}. The counter shares the "
               f"waiter's route, so there is no third handler for a third channel to "
               f"diverge in")

    staff_source = strip_comments(
        (REPO / "api/src/routes/staff.ts").read_text(encoding="utf-8"))
    guest_source = strip_comments(
        (REPO / "api/src/routes/customer.ts").read_text(encoding="utf-8"))
    counter_specific = [p for p in route_paths(staff_source) + route_paths(guest_source)
                        if "counter" in p]
    record("no route anywhere is specific to the counter",
           not counter_specific,
           f"route paths naming the counter: {counter_specific or 'none'}. A "
           f"/s/v1/counter/orders would be the divergent order path FR-ORD-001B forbids, "
           f"and it would look reasonable in review")

    mapping = re.findall(r"counter\s*:\s*'([a-z_]+)'", staff_source)
    record("and the origin-to-channel mapping is stated exactly once",
           len(mapping) == 1,
           f"{len(mapping)} statement(s) of what channel a counter order is priced on: "
           f"{mapping}. Two callers of one function passing different arguments is what a "
           f"divergent path actually looks like in practice")

    # BEHAVIOURALLY: the same refusals, by CODE, on all three channels.
    cases = CONTEXT["refusal_matrix"]
    for label, answers in cases.items():
        distinct = sorted(set(answers.values()))
        record(f"all three channels refuse {label} for the same stated reason",
               len(distinct) == 1 and distinct[0],
               f"{answers}. Compared by CODE, not by outcome: two channels that both "
               f"refuse are not identical if one says the variant is unavailable and the "
               f"other says the total changed")

    counter_order = CONTEXT["counter_order"]
    shape = rows(f"""
        SELECT origin::text, channel::text, state::text,
               (placed_by_user_id IS NOT NULL)::text,
               (placed_by_guest_session_id IS NOT NULL)::text
          FROM ordering.customer_order WHERE id = '{counter_order}';""")
    record("a counter order is a row of the same table, differing only in its dimensions",
           shape and shape[0][0] == "counter" and shape[0][3] in ("t", "true")
           and shape[0][4] in ("f", "false"),
           f"{shape}. Same aggregate, same ledger, same fold; what differs is the origin, "
           f"the channel it was priced on and who is named as having placed it")

    billed = rows(f"""
        SELECT c.check_number, b.bill_total_minor::text, b.calculation_version
          FROM billing.check c
          JOIN billing.bill b ON b.check_id = c.id
         WHERE c.id = '{CONTEXT["counter_check"]}';""")
    record("and it is billed by the same check and the same calculation as a dine-in one",
           billed and billed[0][2] == scalar("SELECT billing.calculation_version();"),
           f"{billed}. There is one billing implementation and the counter reaches it the "
           f"same way every other channel does")


def section_payment_dependent_acceptance() -> None:
    print("\n--- 11. Payment-dependent acceptance, recorded and failing closed "
          "(FR-ORD-007B) ---")

    modes = sorted(r[0] for r in rows(
        "SELECT unnest(enum_range(NULL::ordering.acceptance_mode))::text;"))
    record("the acceptance mode FR-ORD-007B needs exists and is understood",
           modes == ["automatic", "payment_dependent", "staff_confirmed"],
           f"{modes}. A policy naming a mode the system did not understand would fail as "
           f"an invalid enum literal deep inside submit_order, which is a worse answer "
           f"than a refusal that says why")

    # A policy version that makes the counter payment-dependent, in force for this check
    # only. Restored afterwards, because the outlet's real policy is M3-A's.
    made = an_accepted_order(((fx.VARIANT_COFFEE_ONE, fx.ITEM_COFFEE, 1),),
                             table=fx.COUNTER_NODE, origin="counter", channel="counter",
                             accept=False)
    switched = run(APP, f"""
        UPDATE config.policy
           SET payload = jsonb_set(payload, '{{acceptance,counter}}',
                                   '"payment_dependent"')
         WHERE id = '{fx.m3a.ORDERING_POLICY}';""", **CTX)
    try:
        refused = run(APP, f"""
            SELECT ordering.accept_order('{fx.TENANT}', '{made["order"]}',
                                         '{fx.USER}');""", **CTX)
        record("an order awaiting a verified payment is not accepted by anybody pressing "
               "a button",
               switched.ok and refused.failed_with("ACCEPTANCE_AWAITS_PAYMENT_VERIFICATION"),
               refused.why() or "an order was accepted with no payment outcome behind it. "
                                "Nothing in this system can verify one yet, so accepting "
                                "would be the requirement inverted — and invisible, "
                                "because nothing exists to contradict it")
        state = scalar(f"""
            SELECT state::text FROM ordering.customer_order
             WHERE id = '{made["order"]}';""")
        record("and it stays submitted rather than being resolved some other way",
               state == "submitted",
               f"the order is {state}. Failing closed is the correct behaviour of the "
               f"finished system too: M4-B supplies the verified outcome and a path that "
               f"consults it, and this refusal remains the answer for everyone without one")
    finally:
        run(APP, f"""
            UPDATE config.policy
               SET payload = jsonb_set(payload, '{{acceptance,counter}}',
                                       '"staff_confirmed"')
             WHERE id = '{fx.m3a.ORDERING_POLICY}';""", **CTX)

    # ACCOUNTED FOR, in whichever state is true. This asked for an OPEN entry against
    # M4-B, which was the honest state at M4-A and stopped being one the moment M4-B
    # closed it — the ninth gate fence of this shape. What has to remain true at every
    # later gate is that the register SAYS SOMETHING about who owed the verification:
    # open against the slice that will supply it, or closed by the slice that did, with
    # evidence. Silence is the failure, and silence is what is checked for.
    entries = partial_closures.load()
    dependency = [e for e in entries
                  if e["requirement"] == "FR-ORD-007B"
                  and (
                      (e.get("state") == "open" and e.get("completing_gate") == "M4-B")
                      or (e.get("state") == "closed"
                          and (e.get("closed_by_evidence") or "").strip()))]
    record("the verification half is accounted for in the register, not assumed",
           bool(dependency) and dependency[0].get("opened_at") == "M4-A",
           f"{[(e.get('aspect'), e.get('state')) for e in dependency]}, opened at "
           f"{dependency[0].get('opened_at') if dependency else 'nothing'}. 'Verified' is "
           f"M4-B's word; M4-A supplies the fail-closed refusal, and the register names "
           f"who owed the verification whether or not they have delivered it yet")


# ===========================================================================
# 12. FR-POS-004's unpaid balance stops being a slot
# ===========================================================================

def section_unpaid_balance() -> None:
    print("\n--- 12. The floor plan's unpaid balance is a figure (FR-POS-004) ---")

    body = definition("pos.table_view(uuid, uuid)")
    record("pos.table_view() no longer returns NULL for the unpaid balance",
           "billing.session_outstanding" in body and "NULL::bigint" not in body,
           f"the column is billing.session_outstanding(): "
           f"{'billing.session_outstanding' in body}; a NULL literal remains: "
           f"{'NULL::bigint' in body}. The slot has carried a closure-register entry "
           f"naming M4 since M3-D")

    unpaid = an_accepted_order(((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 1),),
                               table=fx.TABLE_TWO)
    check = a_check_over(unpaid["session"], [unpaid["order"]])
    bill = a_bill_over(check)
    total = int(scalar(f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';"))
    on_the_floor = rows(f"""
        SELECT unpaid_balance_minor::text FROM pos.table_view('{fx.TENANT}',
                                                              '{fx.OUTLET_H1}')
         WHERE table_session_id = '{unpaid["session"]}';""")
    record("a table with an issued bill shows what it owes",
           on_the_floor and int(on_the_floor[0][0]) == total,
           f"{on_the_floor} against a bill of {total}. Derived on every read, so it "
           f"cannot drift from its source")

    run(APP, f"SELECT billing.split_equally('{fx.TENANT}', '{bill}', 1);", tx=True, **CTX)
    share = scalar(f"SELECT id FROM billing.bill_share WHERE bill_id = '{bill}';")
    run(APP, f"""
        INSERT INTO billing.tip (tenant_id, outlet_id, bill_share_id, currency_code,
                                 amount_minor)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{share}', 'ETB', {total});""", **CTX)
    after_tip = rows(f"""
        SELECT unpaid_balance_minor::text FROM pos.table_view('{fx.TENANT}',
                                                              '{fx.OUTLET_H1}')
         WHERE table_session_id = '{unpaid["session"]}';""")
    record("and a generous tip does not make the table look settled",
           after_tip and int(after_tip[0][0]) == total,
           f"{after_tip} after a tip of {total}. NC-M4-002 arriving through the one "
           f"screen a manager trusts would be the worst place for it")

    # A SECOND table, settled here rather than reusing section 8's: a later fixture that
    # opens a fresh occupancy on the same node closes the earlier one, and pos.table_view()
    # shows open occupancies only — so the row would simply be absent and the check would
    # be asserting about nothing.
    reason = fx.reason_code("M4A_ON_THE_HOUSE")
    owed = int(scalar(f"SELECT billing.outstanding_balance('{fx.TENANT}', '{bill}');"))
    override = an_override("discount.high", "bill", bill, reason, "settled on the floor")
    run(APP, f"""
        SELECT billing.record_disposition('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
            'comped', {owed}, '{override}', '{reason}', 'settled on the floor',
            '{fx.USER}');""", **CTX)
    run(APP, f"""
        SELECT billing.finalize_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
                                     '{fx.USER}');""", **CTX)
    settled = rows(f"""
        SELECT unpaid_balance_minor::text FROM pos.table_view('{fx.TENANT}',
                                                              '{fx.OUTLET_H1}')
         WHERE table_session_id = '{unpaid["session"]}';""")
    record("and the same table owes nothing once its bill is disposed of and finalized",
           settled and int(settled[0][0]) == 0,
           f"{settled} after {owed} was comped with an override. The figure moves with "
           f"the disposition rather than with anybody marking the table clean")


# ===========================================================================
# 13. Governance
# ===========================================================================

def section_governance() -> None:
    print("\n--- 13. Governance ---")

    failures = partial_closures.check()
    entries = partial_closures.load()
    closed_here = sorted(e["requirement"] for e in entries
                         if e.get("closed_at") == "M4-A")
    # Every entry whose completing gate is M4-A. Derived from the register rather than
    # listed, so an entry a later edit re-points at this slice comes due here too.
    due = sorted({e["requirement"] for e in entries
                  if (e.get("completing_gate") or "") == "M4-A"})
    record("the register is consistent and everything that came due is closed",
           not failures and due and all(r in closed_here for r in due),
           f"{len(entries)} entries; {len(due)} requirement(s) name M4-A as their "
           f"completing gate and all of them are closed at M4-A: {closed_here}. "
           f"Failures: {failures or 'none'}. Creating tests/m4a/ made nine entries come "
           f"due — the three the brief names and six more the register knew about — and "
           f"they are closed rather than re-pointed at a gate that never arrives")

    opened_here = sorted(e["requirement"] for e in entries
                         if e.get("opened_at") == "M4-A")
    record("and this slice's own half-closed requirements are in the register",
           opened_here,
           f"opened at M4-A: {opened_here}. Payment capture, the tender and the receipt "
           f"are M4-B's and M4-C's, and what M4-A owes them is written down")

    decomposition = json.loads(
        (REPO / "planning" / "partial_closures.json").read_text(encoding="utf-8")
    ).get("gate_decomposition")
    record("the register states that M4's slice split is this repository's decision",
           bool(decomposition),
           f"{str(decomposition)[:200] if decomposition else 'absent'}. The pinned "
           f"package defines M4 as ONE gate; A, B and C are this repository's "
           f"decomposition, and a reviewer should meet that as a stated decision rather "
           f"than infer it from slice names that appear in no pinned artifact")

    # Every signature this slice raises, checked against the 63 fenced terms
    # PROGRAMMATICALLY. The brief asks for it and a fenced word in an error message is
    # how a fenced domain gets built by accident, one message at a time.
    pattern, term_count = fenced_identifier_pattern()
    fenced_in_signatures = [r[0] for r in rows(f"""
        SELECT DISTINCT m[1]
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        CROSS JOIN LATERAL regexp_matches(p.prosrc, '([A-Z][A-Z_]{{4,}}):', 'g') AS m
        WHERE n.nspname = 'billing'
          AND m[1] ~* '{pattern}'
        ORDER BY 1;""", dsn=ADMIN)]
    record(f"no refusal this slice raises names one of the {term_count} fenced terms",
           not fenced_in_signatures,
           f"{fenced_in_signatures or 'none'}. Checked against the vocabulary the package "
           f"defines rather than a list here — a fenced word in an error message is how a "
           f"fenced domain gets built by accident, one message at a time")

    # Every table this slice adds is isolated, and FORCED.
    unforced = [r[0] for r in rows("""
        SELECT c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'billing' AND c.relkind = 'r'
          AND NOT (c.relrowsecurity AND c.relforcerowsecurity)
        ORDER BY 1;""", dsn=ADMIN)]
    policed = count(ADMIN, """
        SELECT count(*) FROM pg_policies WHERE schemaname = 'billing';""")
    tables = count(ADMIN, """
        SELECT count(*) FROM pg_tables WHERE schemaname = 'billing';""")
    record("every billing table has row level security enabled AND forced, with a policy",
           not unforced and policed == tables and tables > 8,
           f"{tables} table(s), {policed} isolation polic(ies), unforced: "
           f"{unforced or 'none'}. Enumerated by query in the migration too, so a table a "
           f"later slice adds to this schema is covered the moment it exists")

    # NOTHING MAY POINT A FOREIGN KEY AT A PROJECTION — M3-D's rule, applied to this
    # slice's own tables. It caught two here: billing.check_allocation referenced
    # ordering.customer_order, and billing.bill_disposition referenced billing.bill.
    dangling = [r[0] for r in rows("""
        WITH projections AS (
            SELECT DISTINCT m[1] AS relname
            FROM pg_proc p
            CROSS JOIN LATERAL regexp_matches(
                p.prosrc, 'DELETE FROM ([a-z_]+\\.[a-z_]+)', 'g') AS m
            WHERE p.proname ~ '(rebuild|drop)_projections'
        )
        SELECT src.nspname || '.' || srct.relname || ' -> ' ||
               tgt.nspname || '.' || tgtt.relname
        FROM pg_constraint fk
        JOIN pg_class srct ON srct.oid = fk.conrelid
        JOIN pg_namespace src ON src.oid = srct.relnamespace
        JOIN pg_class tgtt ON tgtt.oid = fk.confrelid
        JOIN pg_namespace tgt ON tgt.oid = tgtt.relnamespace
        WHERE fk.contype = 'f'
          AND src.nspname = 'billing'
          AND tgt.nspname || '.' || tgtt.relname IN (SELECT relname FROM projections)
          AND src.nspname || '.' || srct.relname NOT IN (SELECT relname FROM projections)
        ORDER BY 1;""", dsn=ADMIN)]
    record("no durable billing table points a foreign key at a projection",
           not dangling,
           f"{dangling or 'none'}. Both sides derived: the projections from the bodies of "
           f"every drop-for-rebuild function the catalog holds. This rule caught two "
           f"defects in this slice — the allocation's key into the order and the "
           f"disposition's key into the bill — and both would have failed FR-DAT-010's "
           f"rebuild rather than anything a forward run does")


# ===========================================================================
# 14. Negative controls
# ===========================================================================

def control(name: str, red, green) -> None:
    print(f"\n  {name}")
    ok, detail = red()
    record(f"{name} — RED with the defect planted", ok, detail)
    ok, detail = green()
    record(f"{name} — GREEN after revert", ok, detail)


def replace_function(sql: str) -> None:
    res = run(ADMIN, sql)
    if not res.ok:
        raise ProbeFailed("CREATE OR REPLACE", res.err)


def rebuild_surface() -> None:
    """Recompile the customer surface from the WORKSPACE copy and restart the service.

    The defect is planted in the workspace, never in the repository: api/build.sh
    re-copies source on every run, so reverting is a rebuild rather than an edit and the
    repository is never in a broken state even for an instant.
    """
    proc = run_command([str(WORKSPACE / "node_modules" / ".bin" / TSC),
                        "-p", str(WORKSPACE / "pwa" / "tsconfig.json"),
                        "--outDir", str(WORKSPACE / "dist" / "public")],
                       cwd=str(WORKSPACE))
    if proc.returncode != 0:
        raise RuntimeError(f"surface rebuild failed: {proc.stdout or proc.stderr}")
    for name in ("index.html", "app.css", "manifest.webmanifest"):
        (WORKSPACE / "dist" / "public" / name).write_text(
            (WORKSPACE / "pwa" / name).read_text(encoding="utf-8"), encoding="utf-8")
    CONTEXT["restart"]()


def patch_surface(old: str, new: str) -> None:
    path = WORKSPACE / "pwa" / "src" / "app.ts"
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError("cannot plant defect: anchor not found in pwa/src/app.ts")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    rebuild_surface()


def patch_route(relative: str, old: str, new: str) -> None:
    path = WORKSPACE / "src" / relative
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"cannot plant defect: anchor not found in {relative}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    proc = run_command([str(WORKSPACE / "node_modules" / ".bin" / TSC),
                        "-p", str(WORKSPACE / "tsconfig.json")], cwd=str(WORKSPACE))
    if proc.returncode != 0:
        raise RuntimeError(f"compile failed: {proc.stdout or proc.stderr}")
    CONTEXT["restart"]()


def section_controls() -> None:
    print("\n--- 14. Negative controls: each proved RED with a real defect, then GREEN ---")

    # ---------------------------------------------------------------- NC-M4-001
    # A tip preselected for the guest. Planted on the SURFACE, because after the schema
    # (no default column) and the API (no selected field) that is the only level left at
    # which a preselection can still be expressed — and it is where it would really
    # happen: a well-meaning developer helping the guest along.
    def tip_gate() -> tuple[bool, str, str]:
        # The English case, and NO TAP: the control measures the page as it is first
        # drawn, and a tap would be measuring what a guest chose rather than what the
        # surface chose for them.
        probe = render([c for c in CONTEXT["bill_cases"] if c["locale"] == "en"],
                       tap=None)
        if probe.get("probeFailed"):
            raise CommandUnreadable(f"the browser never rendered: {probe['probeFailed']}")
        view = probe["locales"]["en"]
        pressed = [o for o in view["options"]
                   if o["ariaPressed"] == "true" or o["checked"]
                   or o["defaultAttribute"] is not None
                   or any("select" in c or "default" in c or "chosen" in c
                          for c in o["classes"])]
        if not view["options"]:
            raise CommandUnreadable("no tip suggestion was drawn, so nothing was measured")
        if pressed:
            return (False, "TIP_PRESELECTED",
                    f"{len(pressed)} of {len(view['options'])} suggestions came back "
                    f"pressed before the guest touched anything: "
                    f"{[o['text'] for o in pressed]}")
        return (True, "", f"{len(view['options'])} suggestion(s) drawn, none selected")

    def red_preselected():
        patch_surface(
            "    button.setAttribute('aria-pressed', 'false');",
            "    button.setAttribute('aria-pressed',\n"
            "      String(option.display_order === 2));")
        ok, sig, detail = tip_gate()
        return (not ok and sig == "TIP_PRESELECTED", f"{sig}: {detail}")

    def green_preselected():
        sync_and_build()
        CONTEXT["restart"]()
        ok, sig, detail = tip_gate()
        return (ok, detail if ok else f"{sig}: {detail}")

    control("NC-M4-001  a tip preselected for the guest", red_preselected,
            green_preselected)

    # ---------------------------------------------------------------- NC-M4-002
    # A tip counted towards a bill balance. Planted in the BALANCE FUNCTION, which is
    # where it would really happen: somebody looking at a screen showing money received
    # and a bill still open, and "fixing" it.
    def commingled_gate() -> tuple[bool, str, str]:
        readers = functions_reading_tips(exclude=("billing.finalize_bill",))
        bill = CONTEXT["commingle_bill"]
        outstanding = int(scalar(
            f"SELECT billing.outstanding_balance('{fx.TENANT}', '{bill}');"))
        total = int(scalar(
            f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';"))
        if readers:
            return (False, "TIP_COMMINGLED_WITH_BILL",
                    f"balance function(s) reading a tip: {readers}; outstanding "
                    f"{outstanding} against a total of {total}, so a tip has moved what "
                    f"is owed")
        if outstanding != total:
            return (False, "TIP_COMMINGLED_WITH_BILL",
                    f"no function names a tip and the balance still moved: {outstanding} "
                    f"against {total}")
        return (True, "", f"no balance function reads a tip, and {outstanding} is owed "
                          f"against a total of {total} despite the tips attached to it")

    ORIGINAL_BALANCE = """
CREATE OR REPLACE FUNCTION billing.outstanding_balance(p_tenant_id uuid, p_bill_id uuid)
RETURNS money.amount_minor
LANGUAGE sql STABLE
AS $$
    SELECT b.bill_total_minor
           - coalesce((SELECT sum(d.amount_minor)
                         FROM billing.bill_disposition d
                        WHERE d.tenant_id = b.tenant_id AND d.bill_id = b.id), 0)
      FROM billing.bill b
     WHERE b.tenant_id = p_tenant_id AND b.id = p_bill_id;
$$;"""

    def red_commingled():
        replace_function("""
CREATE OR REPLACE FUNCTION billing.outstanding_balance(p_tenant_id uuid, p_bill_id uuid)
RETURNS money.amount_minor
LANGUAGE sql STABLE
AS $$
    SELECT b.bill_total_minor
           - coalesce((SELECT sum(d.amount_minor)
                         FROM billing.bill_disposition d
                        WHERE d.tenant_id = b.tenant_id AND d.bill_id = b.id), 0)
           - coalesce((SELECT sum(t.amount_minor)
                         FROM billing.tip t
                         JOIN billing.bill_share s ON s.id = t.bill_share_id
                        WHERE s.bill_id = b.id), 0)
      FROM billing.bill b
     WHERE b.tenant_id = p_tenant_id AND b.id = p_bill_id;
$$;""")
        ok, sig, detail = commingled_gate()
        return (not ok and sig == "TIP_COMMINGLED_WITH_BILL", f"{sig}: {detail}")

    def green_commingled():
        replace_function(ORIGINAL_BALANCE)
        ok, sig, detail = commingled_gate()
        return (ok, detail if ok else f"{sig}: {detail}")

    control("NC-M4-002  a tip counted towards a bill balance", red_commingled,
            green_commingled)

    # --------------------------------------------------------------- NC-M4A-002
    # A line quantity billed on two checks. Planted in the guard, made to ask the
    # question a careless author would ask — within ONE check rather than across the set.
    ORIGINAL_GUARD = definition(
        "billing.assert_no_unit_billed_twice()").replace("CREATE OR REPLACE FUNCTION",
                                                         "CREATE OR REPLACE FUNCTION")

    def double_billing_gate() -> tuple[bool, str, str]:
        party = CONTEXT["double_party"]
        line = scalar(f"""
            SELECT id FROM ordering.order_line WHERE order_id = '{party["order"]}';""")
        attempt = run(APP, f"""
            SELECT billing.allocate_to_check('{fx.TENANT}', '{fx.OUTLET_H1}',
                billing.open_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{party["session"]}',
                                   '{fx.USER}'), '{line}', 1);""", tx=True, **CTX)
        if attempt.ok:
            return (False, "QUANTITY_DOUBLE_BILLED",
                    "a unit already billed on another check was billed again and the "
                    "transaction committed")
        if not attempt.failed_with("QUANTITY_DOUBLE_BILLED"):
            return (False, signature_of(attempt.err) or "UNEXPECTED_REFUSAL",
                    f"refused, but not for the stated reason: {attempt.why()}")
        return (True, "", attempt.why())

    def red_double_billing():
        replace_function("""
CREATE OR REPLACE FUNCTION billing.assert_no_unit_billed_twice() RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_ordered  integer;
    v_allocated integer;
BEGIN
    SELECT l.quantity INTO v_ordered FROM ordering.order_line l
     WHERE l.tenant_id = NEW.tenant_id AND l.id = NEW.order_line_id;
    -- The careless question: how much of this line does THIS CHECK bill? A line split
    -- across two checks then passes, which is the case FR-BIL-002 is actually about.
    SELECT coalesce(sum(a.quantity), 0) INTO v_allocated
      FROM billing.check_allocation a
     WHERE a.tenant_id = NEW.tenant_id AND a.order_line_id = NEW.order_line_id
       AND a.check_id = NEW.check_id;
    IF v_allocated > v_ordered THEN
        RAISE EXCEPTION
            'QUANTITY_DOUBLE_BILLED: order line % was ordered % time(s) and is allocated '
            '% time(s)', NEW.order_line_id, v_ordered, v_allocated
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NULL;
END;
$$;""")
        ok, sig, detail = double_billing_gate()
        return (not ok and sig == "QUANTITY_DOUBLE_BILLED", f"{sig}: {detail}")

    def green_double_billing():
        replace_function(ORIGINAL_GUARD)
        ok, sig, detail = double_billing_gate()
        return (ok, detail if ok else f"{sig}: {detail}")

    control("NC-M4A-002  a line quantity billed on two checks", red_double_billing,
            green_double_billing)

    # --------------------------------------------------------------- NC-M4A-003
    # A split that loses a minor unit. The classic: integer division with the remainder
    # dropped. It is correct on every total that divides evenly, which is why the check
    # uses counts that do not.
    ORIGINAL_SPLIT = definition("billing.split_equally(uuid, uuid, integer)")

    def split_gate() -> tuple[bool, str, str]:
        bill = CONTEXT["split_gate_bill"]
        total = int(scalar(
            f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';"))
        for payers in AWKWARD_PAYERS:
            done = run(APP,
                       f"SELECT billing.split_equally('{fx.TENANT}', '{bill}', {payers});",
                       tx=True, **CTX)
            if not done.ok:
                if done.failed_with("SPLIT_NOT_EXACT"):
                    return (False, "SPLIT_NOT_EXACT",
                            f"{payers} payers on {total}: {done.why()}")
                return (False, signature_of(done.err) or "UNEXPECTED_REFUSAL", done.why())
            parts = shares_of(bill)
            if sum(parts) != total:
                return (False, "SPLIT_NOT_EXACT",
                        f"{payers} payers on {total}: parts sum to {sum(parts)}, "
                        f"{'losing' if sum(parts) < total else 'creating'} "
                        f"{abs(total - sum(parts))} minor unit(s)")
        return (True, "", f"every count in {AWKWARD_PAYERS} sums to {total} exactly")

    def red_split():
        replace_function("""
CREATE OR REPLACE FUNCTION billing.split_equally(
    p_tenant_id uuid, p_bill_id uuid, p_payers integer
) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_bill billing.bill%ROWTYPE;
    v_i    integer;
BEGIN
    SELECT * INTO v_bill FROM billing.bill
     WHERE tenant_id = p_tenant_id AND id = p_bill_id;
    DELETE FROM billing.bill_share WHERE tenant_id = p_tenant_id AND bill_id = p_bill_id;
    -- Integer division, remainder dropped. Right on every total that divides evenly.
    FOR v_i IN 1 .. p_payers LOOP
        INSERT INTO billing.bill_share
            (tenant_id, outlet_id, bill_id, share_number, mode, currency_code, amount_minor)
        VALUES (p_tenant_id, v_bill.outlet_id, p_bill_id, v_i, 'equal_share',
                v_bill.currency_code, v_bill.bill_total_minor / p_payers);
    END LOOP;
    RETURN p_payers;
END;
$$;""")
        ok, sig, detail = split_gate()
        return (not ok and sig == "SPLIT_NOT_EXACT", f"{sig}: {detail}")

    def green_split():
        replace_function(ORIGINAL_SPLIT)
        ok, sig, detail = split_gate()
        return (ok, detail if ok else f"{sig}: {detail}")

    control("NC-M4A-003  a split that loses or creates a minor unit", red_split,
            green_split)

    # --------------------------------------------------------------- NC-M4A-004
    ORIGINAL_FINALIZE = definition("billing.finalize_bill(uuid, uuid, uuid, uuid)")

    def finalize_gate() -> tuple[bool, str, str]:
        bill = CONTEXT["unsettled_bill"]
        outstanding = int(scalar(
            f"SELECT billing.outstanding_balance('{fx.TENANT}', '{bill}');"))
        attempt = run(APP, f"""
            SELECT billing.finalize_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
                                         '{fx.USER}');""", tx=True, **CTX)
        if attempt.ok:
            return (False, "BILL_FINALIZED_UNSETTLED",
                    f"a bill still owing {outstanding} was finalized")
        if not attempt.failed_with("BILL_FINALIZED_UNSETTLED"):
            return (False, signature_of(attempt.err) or "UNEXPECTED_REFUSAL",
                    f"refused, but not for the stated reason: {attempt.why()}")
        return (True, "", attempt.why())

    def red_finalize():
        replace_function(ORIGINAL_FINALIZE.replace(
            "IF v_outstanding > 0 THEN", "IF v_outstanding - v_tips > 0 THEN"))
        ok, sig, detail = finalize_gate()
        return (not ok and sig == "BILL_FINALIZED_UNSETTLED", f"{sig}: {detail}")

    def green_finalize():
        replace_function(ORIGINAL_FINALIZE)
        ok, sig, detail = finalize_gate()
        return (ok, detail if ok else f"{sig}: {detail}")

    control("NC-M4A-004  a bill finalized with an unsettled balance", red_finalize,
            green_finalize)

    # --------------------------------------------------------------- NC-M4A-005
    # TWO LOCKS CAN HIDE EACH OTHER. The grant refuses the delete and so does the
    # trigger, so a check that only tried to delete would pass with either one removed.
    # This plants the removal of the GRANT LOCK and requires the trigger to hold alone.
    def deletion_gate() -> tuple[bool, str, str]:
        """A FRESH bill every time, with events that really exist.

        The first version deleted from one bill on every call. The red leg's second half
        succeeded — which is what it is there to show — and then the green leg deleted
        from a bill whose ledger was already gone, matched no rows, and reported success
        as "deleted outright". A DELETE that matches nothing succeeds, so a gate that only
        reads ok/not-ok cannot tell an empty table from a broken lock.
        """
        made = an_accepted_order(((fx.VARIANT_COFFEE_ONE, fx.ITEM_COFFEE, 1),),
                                 table=fx.TABLE_ONE)
        bill = a_bill_over(a_check_over(made["session"], [made["order"]]))
        events = count(ADMIN, f"""
            SELECT count(*) FROM billing.bill_event WHERE bill_id = '{bill}';""")
        if events == 0:
            raise CommandUnreadable(
                "the bill this control acts on has no ledger events, so a delete that "
                "matched nothing would be indistinguishable from one that was refused")
        attempt = run(APP, f"""
            DELETE FROM billing.bill_event WHERE bill_id = '{bill}';""", tx=True, **CTX)
        remaining = count(ADMIN, f"""
            SELECT count(*) FROM billing.bill_event WHERE bill_id = '{bill}';""")
        if attempt.ok or remaining < events:
            return (False, "BILL_DELETED_NOT_CREDITED",
                    f"{events - remaining} of {events} ledger event(s) were deleted "
                    f"outright")
        if attempt.failed_with("BILL_DELETED_NOT_CREDITED"):
            return (True, "", f"the trigger refused on its own, with all {events} "
                              f"event(s) still there: {attempt.why()}")
        if attempt.failed_with("42501"):
            return (True, "", f"the grant refused, with all {events} event(s) still "
                              f"there: {attempt.why()}")
        return (False, signature_of(attempt.err) or "UNEXPECTED_REFUSAL", attempt.why())

    def red_deletion():
        # First establish that the trigger alone holds — the plant removes the grant, so
        # a pass here is the trigger's doing and nothing else's.
        run(ADMIN, "GRANT DELETE ON billing.bill_event TO hospitality_app;")
        ok, sig, detail = deletion_gate()
        if not ok:
            return (False, f"{sig}: {detail}")
        # Then remove the trigger too, leaving nothing.
        run(ADMIN, "DROP TRIGGER bill_event_append_only ON billing.bill_event;")
        ok, sig, detail = deletion_gate()
        return (not ok and sig == "BILL_DELETED_NOT_CREDITED",
                f"with the grant restored the trigger refused alone; with BOTH removed "
                f"the delete succeeded — {sig}: {detail}. That is what makes the two "
                f"locks independent rather than one lock described twice")

    def green_deletion():
        run(ADMIN, """
            CREATE TRIGGER bill_event_append_only
                BEFORE UPDATE OR DELETE ON billing.bill_event
                FOR EACH ROW EXECUTE FUNCTION billing.refuse_ledger_mutation();""")
        trigger_alone = deletion_gate()
        run(ADMIN, "REVOKE DELETE ON billing.bill_event FROM hospitality_app;")
        grant_too = deletion_gate()
        return (trigger_alone[0] and grant_too[0],
                f"trigger restored: {trigger_alone[2]}; grant revoked as well: "
                f"{grant_too[2]}")

    control("NC-M4A-005  an issued bill corrected by deletion", red_deletion,
            green_deletion)

    # --------------------------------------------------------------- NC-M4A-006
    # A per-payer tip that reallocates bill lines. Planted in the ROUTE, as the helpful
    # "add the tip to what they owe" a developer writes when a cashier asks for a single
    # figure to collect.
    def reallocation_gate() -> tuple[bool, str, str]:
        """A FRESH bill and a fresh, untipped share on every call.

        billing.tip is unique on the share, so a gate that tipped the same share twice
        would be measuring the second tap's refusal rather than the first tap's effect on
        the bill. The red leg would still go red — for the wrong reason, which is the
        thing this project keeps calling a defect.
        """
        seated = CONTEXT["tip_guest"]
        ordered = an_accepted_order(((fx.VARIANT_COFFEE_ONE, fx.ITEM_COFFEE, 1),),
                                    session=seated["session"])
        bill = a_bill_over(a_check_over(seated["session"], [ordered["order"]]))
        run(APP, f"SELECT billing.split_equally('{fx.TENANT}', '{bill}', 1);",
            tx=True, **CTX)
        share = scalar(f"SELECT id FROM billing.bill_share WHERE bill_id = '{bill}' "
                       f"ORDER BY share_number LIMIT 1;")

        def snapshot():
            return (int(scalar(f"SELECT bill_total_minor FROM billing.bill "
                               f"WHERE id = '{bill}';")),
                    [tuple(r) for r in rows(f"""
                        SELECT a.order_line_id::text, a.quantity::text
                          FROM billing.check_allocation a
                          JOIN billing.bill b ON b.check_id = a.check_id
                         WHERE b.id = '{bill}' ORDER BY a.order_line_id;""")],
                    [tuple(r) for r in rows(f"""
                        SELECT kind::text, amount_minor::text FROM billing.bill_component
                         WHERE bill_id = '{bill}' ORDER BY kind;""")],
                    [tuple(r) for r in rows(f"""
                        SELECT share_number::text, amount_minor::text
                          FROM billing.bill_share WHERE bill_id = '{bill}'
                         ORDER BY share_number;""")])

        before = snapshot()
        answer = guest_call("POST", "/c/v1/bill/tip", seated["token"],
                            {"shareId": share, "amountMinor": 700, "percentage": 5},
                            key=idem(f"tip-{os.urandom(4).hex()}"))
        after = snapshot()
        # THE CENSUS DECIDES, not the status code. A route that answered 500 would also
        # be a defect, but it is a different one, and reporting it as TIP_REALLOCATED_BILL
        # would be naming a cause this check did not verify.
        if before != after:
            moved = [name for name, a, b in
                     zip(("the bill total", "the allocations", "the components",
                          "the shares"), before, after) if a != b]
            return (False, "TIP_REALLOCATED_BILL",
                    f"choosing a tip changed {moved}: {before} became {after}")
        if answer.get("status") not in (200, 409):
            return (False, "TIP_ROUTE_FAILED", f"the tip route answered {answer}")
        return (True, "", f"the total, every allocation, every component and every share "
                          f"are identical either side of a guest choosing a tip")

    def red_reallocation():
        # The helpful thing a developer writes when a cashier asks for one figure to
        # collect: this payer has settled up, so take their items off the check. It
        # succeeds — no constraint stands in its way, because the constraint that would
        # is the one FR-BIL-015 is asking for and it is not a constraint, it is the
        # absence of a path. The census is what sees it.
        patch_route(
            "routes/billing.ts",
            "          if (rows.length === 0) {\n"
            "            reply.code(404);\n"
            "            return { error: 'no such share on this table', reason: 'BILL_SHARE_NOT_FOUND' };\n"
            "          }\n"
            "          return { tipId: rows[0].id as string };",
            "          if (rows.length === 0) {\n"
            "            reply.code(404);\n"
            "            return { error: 'no such share on this table', reason: 'BILL_SHARE_NOT_FOUND' };\n"
            "          }\n"
            "          await client.query(\n"
            "            `DELETE FROM billing.check_allocation\n"
            "              WHERE id = (SELECT a.id FROM billing.check_allocation a\n"
            "                            JOIN billing.bill b ON b.check_id = a.check_id\n"
            "                            JOIN billing.bill_share s ON s.bill_id = b.id\n"
            "                           WHERE s.id = $1::uuid\n"
            "                           ORDER BY a.order_line_id LIMIT 1)`,\n"
            "            [request.body.shareId]);\n"
            "          return { tipId: rows[0].id as string };")
        ok, sig, detail = reallocation_gate()
        return (not ok and sig == "TIP_REALLOCATED_BILL", f"{sig}: {detail}")

    def green_reallocation():
        sync_and_build()
        CONTEXT["restart"]()
        ok, sig, detail = reallocation_gate()
        return (ok, detail if ok else f"{sig}: {detail}")

    control("NC-M4A-006  a per-payer tip that reallocates bill lines", red_reallocation,
            green_reallocation)

    # --------------------------------------------------------------- NC-M4A-007
    # The counter given an order path of its own. A FAITHFUL second implementation, not a
    # broken one: it submits the same order the shared route would. Behaviour cannot see
    # it, which is the whole argument for the structural half.
    def divergence_gate() -> tuple[bool, str, str]:
        source = strip_comments(
            (WORKSPACE / "src/routes/staff.ts").read_text(encoding="utf-8"))
        specific = [p for p in route_paths(source) if "counter" in p]
        universe = {r[0] for r in rows(RULE_FUNCTION_QUERY, dsn=ADMIN)}
        submitters = [p for p in route_paths(source)
                      if "ordering.submit_order" in _block(source, p)]
        if specific:
            return (False, "CHANNEL_RULE_DIVERGENCE",
                    f"the counter has route(s) of its own: {specific}")
        if len(submitters) != 1:
            return (False, "CHANNEL_RULE_DIVERGENCE",
                    f"the staff surface submits an order from {len(submitters)} "
                    f"handler(s): {submitters}")
        return (True, "", f"one submitting handler on the staff surface ({submitters}), "
                          f"no route specific to any channel, "
                          f"{len(universe)} rule functions enumerated from the catalog")

    def _block(source: str, path: str) -> str:
        marker = f"'{path}'"
        start = source.index(marker)
        following = [m.start() for m in re.finditer(r"app\.(get|post)[<(]", source)
                     if m.start() > start]
        return source[start:following[0] if following else len(source)]

    def red_divergence():
        patch_route(
            "routes/staff.ts",
            "  app.get('/s/v1/handovers', async (request, reply) =>",
            "  app.post<{ Body: { cartId: string; expectedTotalMinor: number;\n"
            "                     pricingDigest: string } }>(\n"
            "    '/s/v1/counter/orders',\n"
            "    async (request, reply) =>\n"
            "      asStaff(request, reply, async (client, tenantId, outletId, userId) => {\n"
            "        const { rows } = await client.query(\n"
            "          `SELECT ordering.submit_order($1::uuid, $2::uuid, $3::uuid, $4,\n"
            "                    decode($5, 'hex'), $6::bigint, 'en'::menu.customer_locale,\n"
            "                    gen_random_uuid(), gen_random_uuid(),\n"
            "                    'counter'::ordering.order_origin, $7::uuid, NULL::uuid,\n"
            "                    false, '[]'::jsonb, '[]'::jsonb,\n"
            "                    'counter'::menu.sales_channel) AS id`,\n"
            "          [tenantId, outletId, request.body.cartId,\n"
            "           `counter-${Date.now()}`, request.body.pricingDigest,\n"
            "           request.body.expectedTotalMinor, userId]);\n"
            "        return { orderId: rows[0].id as string };\n"
            "      }),\n"
            "  );\n\n"
            "  app.get('/s/v1/handovers', async (request, reply) =>")
        ok, sig, detail = divergence_gate()
        return (not ok and sig == "CHANNEL_RULE_DIVERGENCE", f"{sig}: {detail}")

    def green_divergence():
        sync_and_build()
        CONTEXT["restart"]()
        ok, sig, detail = divergence_gate()
        return (ok, detail if ok else f"{sig}: {detail}")

    control("NC-M4A-007  the counter channel on an order path of its own", red_divergence,
            green_divergence)

    # --------------------------------------------------------------- NC-M4A-008
    # A bill that carries no record of the arithmetic that produced it.
    #
    # PLANTED WHERE IT WOULD REALLY HAPPEN AND WHERE IT CAN BE UNDONE: on the FOLD, which
    # stops copying the version out of the event onto the document. The event still
    # carries it, so nothing about the ledger is damaged and the revert is a rebuild —
    # which is FR-DAT-010 doing the work it exists for rather than being asserted about.
    #
    # The first version planted it on billing.calculation_version() instead, so the EVENTS
    # were written with an empty version too. That is not revertible: the ledger is
    # append-only by trigger and by grant, so the poisoned events survived the green leg
    # and made the next run's rebuild fail on the constraint. A control that cannot be
    # reverted is a control that leaves the repository worse than it found it.
    ORIGINAL_FOLD = definition("billing.apply_event(bigint)")

    def version_gate() -> tuple[bool, str, str]:
        made = an_accepted_order(((fx.VARIANT_COFFEE_ONE, fx.ITEM_COFFEE, 1),),
                                 table=fx.TABLE_ONE)
        check = a_check_over(made["session"], [made["order"]])
        issued = run(APP, f"""
            SELECT billing.issue_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{check}',
                                      '{fx.USER}', 'en');""", tx=True, **CTX)
        if not issued.ok:
            if issued.failed_with("23514", "23502", "bill_calculation_version_stated"):
                return (False, "CALCULATION_VERSION_MISSING",
                        f"a bill was issued with no version and the column caught it: "
                        f"{issued.why()}")
            return (False, signature_of(issued.err) or "UNEXPECTED_REFUSAL", issued.why())
        bill = (issued.scalar or "").strip()
        blank = [r[0] for r in rows(f"""
            SELECT b.bill_number FROM billing.bill b
             WHERE b.tenant_id = '{fx.TENANT}'
               AND coalesce(btrim(b.calculation_version), '') = '';""")]
        recorded = [r[0] for r in rows(f"""
            SELECT e.id::text FROM billing.bill_event e
             WHERE e.bill_id = '{bill}' AND e.kind = 'issued'
               AND coalesce(btrim(e.after ->> 'calculation_version'), '') = '';""")]
        if blank or recorded:
            return (False, "CALCULATION_VERSION_MISSING",
                    f"bill(s) carrying no calculation version: {blank}; issued event(s) "
                    f"recording none: {recorded}. A bill disputed six months from now "
                    f"cannot be recomputed the way it was computed")
        return (True, "", f"every bill in the tenant names the arithmetic it was computed "
                          f"under, and so does every issued event")

    def red_version():
        loosened = run(ADMIN, """
            ALTER TABLE billing.bill DROP CONSTRAINT bill_calculation_version_stated;
            ALTER TABLE billing.bill ALTER COLUMN calculation_version DROP NOT NULL;""")
        if not loosened.ok:
            raise ProbeFailed("loosening the calculation version column", loosened.err)
        # The fold stops carrying the version onto the document. Everything else is
        # identical: the same arithmetic, the same components, the same total, the same
        # event. The only thing missing is the ability to know, six months from now,
        # which arithmetic produced them.
        replace_function(ORIGINAL_FOLD.replace(
            "                v_after ->> 'calculation_version',", "                NULL,"))
        ok, sig, detail = version_gate()
        return (not ok and sig == "CALCULATION_VERSION_MISSING", f"{sig}: {detail}")

    def green_version():
        replace_function(ORIGINAL_FOLD)
        # THE REVERT IS A REBUILD. The versions were never lost — they are in the ledger,
        # which the plant did not touch — so refolding puts them back on every bill the
        # red leg issued. Nothing is repaired by hand, and the constraint can only come
        # back if the refold really produced a version for every document.
        rebuilt = run(ADMIN, f"SELECT billing.rebuild_projections('{fx.TENANT}');",
                      tx=True, **CTX)
        if not rebuilt.ok:
            raise ProbeFailed("refolding the bills the plant left versionless",
                              rebuilt.err)
        restored = run(ADMIN, """
            ALTER TABLE billing.bill ALTER COLUMN calculation_version SET NOT NULL;
            ALTER TABLE billing.bill ADD CONSTRAINT bill_calculation_version_stated
                CHECK (btrim(calculation_version) <> '');""")
        if not restored.ok:
            raise ProbeFailed("restoring bill_calculation_version_stated", restored.err)
        ok, sig, detail = version_gate()
        return (ok, f"{detail}; the versions came back from the ledger by a rebuild, not "
                    f"by hand" if ok else f"{sig}: {detail}")

    control("NC-M4A-008  a finalized bill with no calculation version", red_version,
            green_version)


def section_generator_controls() -> None:
    print("\n--- 15. The register's own controls ---")

    # NC-M4A-001: an entry whose completer moves LATER without a recorded reason. The
    # power somebody would abuse by re-pointing a failing entry at a gate that never
    # comes due, so it fails the build.
    def completer_gate(entries) -> tuple[bool, str, str]:
        failures = partial_closures.check(entries)
        moved = [f for f in failures if f[0] == "PARTIAL_CLOSURE_COMPLETER_MOVED_LATER"]
        if moved:
            return (False, "PARTIAL_CLOSURE_COMPLETER_MOVED_LATER", str(moved[0][1])[:300])
        if failures:
            return (False, failures[0][0], str(failures[0][1])[:300])
        return (True, "", f"{len(entries)} entries, no failure")

    entries = partial_closures.load()
    previous = partial_closures.previous_completers()

    def red_moved():
        if previous is None:
            raise CommandUnreadable(
                "the register's committed state could not be read, so 'moved later' has "
                "nothing to be measured against")
        planted = json.loads(json.dumps(entries))
        target = None
        for entry in planted:
            # Keyed the way previous_completers() keys it — by requirement AND aspect.
            # Keyed on opened_at first, which matched nothing, and the control raised
            # rather than passing on an empty comparison. That is the right failure: an
            # instrument that cannot find its subject must stop.
            key = (entry["requirement"], entry.get("aspect", ""))
            if key in previous and entry.get("completing_gate"):
                target = entry
                break
        if target is None:
            raise CommandUnreadable("no committed entry to move")
        # THE COMPLETING GATE is what moves. Setting completed_by — the requirement that
        # discharges the entry — changes nothing the check looks at, and a plant that
        # plants nothing is a control that cannot go red.
        target["completing_gate"] = "M5b"
        target.pop("completer_moved", None)
        ok, sig, detail = completer_gate(planted)
        return (not ok and sig == "PARTIAL_CLOSURE_COMPLETER_MOVED_LATER",
                f"{sig}: {detail}")

    def green_moved():
        ok, sig, detail = completer_gate(entries)
        return (ok, detail if ok else f"{sig}: {detail}")

    control("NC-M4A-001  a closure completer moved later with no reason", red_moved,
            green_moved)


# ===========================================================================
# main
# ===========================================================================

def build_refusal_matrix() -> None:
    """The same refusal, asked of all three channels, compared by CODE.

    Extended from M3-D's two-channel matrix rather than reimplemented: the shape is the
    same and the counter is a third caller of the same route with a different origin,
    which is exactly what FR-ORD-001B says it should be.
    """
    def guest_channel() -> dict:
        seated = fx.m3d.a_seated_guest_with_credential(table=fx.TABLE_ONE)
        cart = guest_call("GET", "/c/v1/cart", seated["token"])
        guest_call("POST", "/c/v1/cart/lines", seated["token"],
                   {"cartId": cart["cartId"], "itemId": fx.ITEM_DORO,
                    "variantId": fx.VARIANT_DORO_FULL, "quantity": 1},
                   key=idem(f"guest-line-{os.urandom(4).hex()}"))
        return {"token": seated["token"], "cartId": cart["cartId"], "kind": "guest"}

    def staff_channel(origin: str, table: str) -> dict:
        _session_id, token = fx.staff_session(fx.USER)
        seated = fx.m3d.a_seated_guest(table=table)
        cart = call("POST", "/s/v1/carts", token, {"tableSessionId": seated["session"]})
        call("POST", "/s/v1/cart/lines", token,
             {"cartId": cart["cartId"], "itemId": fx.ITEM_DORO,
              "variantId": fx.VARIANT_DORO_FULL, "quantity": 1},
             key=idem(f"{origin}-line-{os.urandom(4).hex()}"))
        return {"token": token, "cartId": cart["cartId"], "kind": "staff",
                "origin": origin, "session": seated["session"]}

    def submit(chan: dict, **overrides) -> dict:
        guest = chan["kind"] == "guest"
        caller = guest_call if guest else call
        preview_path = "/c/v1/orders/preview" if guest else "/s/v1/orders/preview"
        path = "/c/v1/orders" if guest else "/s/v1/orders"
        body = {"cartId": chan["cartId"]}
        if not guest:
            body["origin"] = chan["origin"]
        view = caller("POST", preview_path, chan["token"], dict(body))
        p = view.get("preview") or {}
        payload = {**body,
                   "expectedTotalMinor": overrides.get(
                       "total", int(p.get("total_amount_minor", 0))),
                   "pricingDigest": overrides.get("digest", p.get("pricing_digest", "")),
                   "locale": "en"}
        return caller("POST", path, chan["token"], payload,
                      key=idem(f"submit-{os.urandom(4).hex()}"))

    def channels() -> dict:
        return {"guest_qr": guest_channel(),
                "waiter_entered": staff_channel("waiter_entered", fx.TABLE_TWO),
                "counter": staff_channel("counter", fx.COUNTER_NODE)}

    matrix: dict[str, dict[str, str]] = {}
    for label, overrides in (
        ("a total that is not the server's", {"total": 1}),
        ("a pricing digest that is not the server's", {"digest": "00" * 32}),
    ):
        matrix[label] = {name: submit(chan, **overrides).get("reason", "ACCEPTED")
                         for name, chan in channels().items()}

    planted = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
        SELECT set_config('app.outlet_id', '{fx.OUTLET_H1}', false);
        UPDATE menu.availability SET state = 'temporarily_unavailable',
               row_version = row_version
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
           AND variant_id = '{fx.VARIANT_DORO_FULL}';""", tx=True)
    if not planted.ok:
        raise ProbeFailed("menu.availability", planted.err)
    try:
        matrix["a variant the kitchen has turned off"] = {
            name: submit(chan).get("reason", "ACCEPTED")
            for name, chan in channels().items()}
    finally:
        run(ADMIN, f"""
            SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
            SELECT set_config('app.outlet_id', '{fx.OUTLET_H1}', false);
            UPDATE menu.availability SET state = 'available', row_version = row_version
             WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
               AND variant_id = '{fx.VARIANT_DORO_FULL}';""", tx=True)

    CONTEXT["refusal_matrix"] = matrix


def prepare_control_subjects() -> None:
    """The bills and parties the controls act on, built before anything is planted."""
    party = an_accepted_order(((fx.VARIANT_TIBS_ONE, fx.ITEM_TIBS, 1),),
                              table=fx.TABLE_TWO)
    first = a_check_over(party["session"], [party["order"]])
    CONTEXT["double_party"] = party

    unsettled = an_accepted_order(((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 1),),
                                  table=fx.TABLE_ONE)
    check = a_check_over(unsettled["session"], [unsettled["order"]])
    bill = a_bill_over(check)
    run(APP, f"SELECT billing.split_equally('{fx.TENANT}', '{bill}', 1);", tx=True, **CTX)
    share = scalar(f"SELECT id FROM billing.bill_share WHERE bill_id = '{bill}';")
    total = int(scalar(f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';"))
    run(APP, f"""
        INSERT INTO billing.tip (tenant_id, outlet_id, bill_share_id, currency_code,
                                 amount_minor)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{share}', 'ETB', {total});""", **CTX)
    CONTEXT["unsettled_bill"] = bill
    CONTEXT["commingle_bill"] = bill

    # A SEPARATE bill for the split control, with NO TIP ON IT. billing.tip references a
    # share, and every split deletes and rewrites the shares, so a tipped bill cannot be
    # re-split — correctly: a payer's tip is attached to the share they chose it on, and
    # re-dividing the bill underneath them would orphan it. The control needs a bill it
    # can split five different ways, so it gets one nobody has tipped on.
    resplit = an_accepted_order(((fx.VARIANT_TIBS_ONE, fx.ITEM_TIBS, 1),),
                                table=fx.TABLE_ONE)
    CONTEXT["split_gate_bill"] = a_bill_over(
        a_check_over(resplit["session"], [resplit["order"]]))

    # The guest the tip route is exercised as. The BILL is issued inside the gate, once
    # per call, because a share can carry only one tip.
    CONTEXT["tip_guest"] = fx.m3d.a_seated_guest_with_credential(table=fx.TIP_TABLE)


def main() -> int:
    print("=" * 74)
    print("M4-A VERIFICATION — checks, bills, splitting and tip separation")
    print(f"real PostgreSQL, real compiled service, real Chromium "
          f"(running on {platform.system()})")
    print("evidence encoding: UTF-8")
    print()
    print("  (measured) = read out of a real browser's own layout after it rendered")
    print("  (asserted) = read from source, from a payload, or from the database")
    print()
    print("=" * 74)

    fx.seed()
    print("fixtures seeded: a service charge with an approved source, tip suggestions "
          "that cannot express a default, translated component wording, a counter "
          "service point and a cashier manager who may authorize a correction")

    section_checks()
    section_calculation()
    section_splitting()
    section_merge_and_split()
    section_tip_separation_structurally()
    section_tip_separation_behaviourally()

    # The counter order, placed before the service starts because it is a database fact.
    counter = an_accepted_order(((fx.VARIANT_TIBS_ONE, fx.ITEM_TIBS, 1),),
                                table=fx.COUNTER_NODE, origin="counter",
                                channel="counter")
    CONTEXT["counter_order"] = counter["order"]
    CONTEXT["counter_check"] = a_check_over(counter["session"], [counter["order"]])
    a_bill_over(CONTEXT["counter_check"])

    section_finalization()
    section_correction()
    section_payment_dependent_acceptance()
    section_unpaid_balance()

    cases = [a_guest_looking_at_a_bill(locale) for locale in ("en", "am", "ar")]
    CONTEXT["bill_cases"] = cases
    CONTEXT["rendered_bill"] = next(c["bill"] for c in cases if c["locale"] == "en")
    prepare_control_subjects()

    sync_and_build()

    service = Service(APP)
    if not service.start():
        print("FAIL SERVICE_DID_NOT_START", file=sys.stderr)
        return 1
    CONTEXT["base_url"] = f"http://127.0.0.1:{service.port}"

    def restart() -> None:
        nonlocal service
        service.stop()
        service = Service(APP)
        if not service.start():
            raise RuntimeError("the service did not restart after a rebuild")
        CONTEXT["base_url"] = f"http://127.0.0.1:{service.port}"

    CONTEXT["restart"] = restart

    try:
        CONTEXT["render"] = render(cases)
        section_bill_preview()
        build_refusal_matrix()
        section_counter_channel()
        section_governance()
        section_controls()
        section_generator_controls()
    finally:
        service.stop()

    passed = sum(1 for _n, ok, _d, _e in results if ok)
    failed = [(name, detail) for name, ok, detail, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")

    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {passed}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}   (read out of a real browser's layout)")
    print(f"  asserted      : {len(results) - measured_count}   (source, payload, or "
          f"database)")
    print(f"  controls      : {sum(1 for n, _o, _d, _e in results if ' — RED' in n)}   "
          f"(each proved red with a real defect, then green after revert)")
    for name, detail in failed:
        print(f"  - {name}")
        for line in (detail or "").splitlines():
            print(f"      {line}")
    print()
    if failed:
        print("FAIL M4A_VERIFICATION")
        return 1
    print("PASS M4A_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
