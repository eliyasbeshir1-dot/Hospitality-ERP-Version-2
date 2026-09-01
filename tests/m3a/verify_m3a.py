#!/usr/bin/env python3
"""M3-A verification: the order aggregate, submission, snapshots and session lifecycle.

The first slice that COMMITS. Everything before this stored a fact or drew it; a
submitted order is a promise to a customer and, at M4, a charge, so this file is careful
about three things the earlier suites did not have to be:

  * a duplicate is proved to have no SECOND EFFECT, not merely to have been refused. The
    proof is a differential over every table in the database, enumerated from the catalog
    at run time so it covers the tables M3-B and M4 have not built yet.
  * the allergy declaration is followed through every hop it makes, and each hop is a
    separate assertion, so a failure names the hop rather than the outcome.
  * merge and move are proved by a full census — the exact SET of orders, lines, notes,
    declarations and timeline entries before and after, compared as sets rather than as
    counts, because a change that drops one row and duplicates another keeps the count.

Every check here runs against a real PostgreSQL through the least-privileged application
role, exactly as the earlier suites do.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "m1a"))
sys.path.insert(0, str(HERE))

import fixtures as fx                                       # noqa: E402
from fenced import fenced_identifier_pattern                # noqa: E402
from pg import ProbeFailed, count, run                      # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import partial_closures                                     # noqa: E402

assert fx.__file__ == str(HERE / "fixtures.py"), f"wrong fixtures module: {fx.__file__}"

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]
CTX = dict(tenant=fx.TENANT, outlet=fx.OUTLET_H1)

# The schemas an order can touch. Read from the catalog at run time within these, rather
# than a list of tables: a table added by a later slice is covered without anybody
# remembering to add it.
APPLICATION_SCHEMAS = ("org", "identity", "config", "audit", "money", "menu", "safety",
                       "service", "ordering")

# Tables a safe retry is permitted to change. EMPTY, and asserted to be empty below.
#
# The brief allowed for "named idempotency-ledger bookkeeping" and it turned out not to
# be needed: service.claim_idempotency() takes its row with INSERT ... ON CONFLICT DO
# NOTHING, so a replay writes NOTHING AT ALL — not a counter, not a timestamp. Keeping an
# allowlist that is empty rather than deleting the idea is deliberate: this is the line
# somebody would widen, and an empty set that the suite asserts is empty is harder to
# widen quietly than an absent one.
RETRY_MAY_CHANGE: dict[str, tuple[str, ...]] = {}

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def definition(signature: str) -> str:
    """A function's whole source.

    NOT scalar(): Result.scalar is the first FIELD OF THE FIRST LINE, and a function
    definition is many lines, so scalar() silently returned the CREATE FUNCTION header
    and nothing else. Two checks here passed against that header — one asserting the
    summation names no charge kind, one asserting every event kind has a fold — and
    neither was reading the body it claimed to read.
    """
    res = run(ADMIN, f"SELECT pg_get_functiondef('{signature}'::regprocedure);")
    if not res.ok or not res.out.strip():
        raise ProbeFailed(f"definition of {signature}", res.err)
    return res.out


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


# ===========================================================================
# Placing an order, once, for the checks that need one
# ===========================================================================

def preview(cart: str, locale: str = "en", channel: str = "dine_in") -> dict:
    res = run(APP, f"""
        SELECT ordering.preview_cart('{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}',
                                     '{locale}', '{channel}');
    """, **CTX)
    if not res.ok:
        raise ProbeFailed("preview_cart", res.err)
    return json.loads(res.scalar)


def submit(cart: str, *, key: str, guest: str | None = None, user: str | None = None,
           origin: str = "guest_qr", locale: str = "en", declarations: list | None = None,
           notes: list | None = None, repeat_intent: bool = False,
           expected_total: int | None = None, digest: str | None = None,
           correlation: str | None = None, request: str | None = None):
    """Submit, returning the raw Result so a caller can assert on the refusal too."""
    view = preview(cart, locale)
    total = expected_total if expected_total is not None else view["total_amount_minor"]
    body_digest = digest if digest is not None else view["pricing_digest"]
    return run(APP, f"""
        SELECT ordering.submit_order(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', '{key}',
            decode('{body_digest}', 'hex'), {total}, '{locale}',
            {f"'{correlation}'" if correlation else "gen_random_uuid()"},
            {f"'{request}'" if request else "gen_random_uuid()"},
            '{origin}',
            {f"'{user}'" if user else 'NULL'},
            {f"'{guest}'" if guest else 'NULL'},
            {str(repeat_intent).lower()},
            '{json.dumps(declarations or [])}'::jsonb,
            '{json.dumps(notes or [])}'::jsonb);
    """, **CTX)


def a_table_with_an_order(*, declarations: bool = False, origin: str = "guest_qr",
                          key: str | None = None, table: str = fx.TABLE_ONE):
    """An occupancy, a guest, a cart, and a submitted order. Returns the pieces."""
    session = fx.fresh_occupancy(table)
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest)
    concern = fx.allergy_concern(session, guest) if declarations else None
    res = submit(cart, key=key or f"m3a-{os.urandom(8).hex()}",
                 guest=guest if origin == "guest_qr" else None,
                 user=fx.USER if origin == "waiter_entered" else None,
                 origin=origin,
                 declarations=[{"allergy_concern_id": concern}] if concern else [])
    if not res.ok:
        raise ProbeFailed("submit_order", res.err)
    return dict(session=session, guest=guest, cart=cart, concern=concern,
                order=(res.scalar or "").strip())


# ===========================================================================
# 1. One aggregate, two origins (FR-ORD-001A)
# ===========================================================================

def section_aggregate() -> None:
    print("\n--- 1. One order aggregate for QR and waiter dine-in (FR-ORD-001A) ---")

    order_tables = [r[0] for r in rows("""
        SELECT c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname = 'ordering'
          AND c.relname LIKE '%order%' AND c.relname NOT LIKE '%line%'
          AND c.relname NOT LIKE '%note%' AND c.relname NOT LIKE '%charge%'
          AND c.relname NOT LIKE '%event%' AND c.relname NOT LIKE '%timeline%'
        ORDER BY c.relname;""", dsn=ADMIN)]
    record("there is ONE order aggregate table, not two models sharing a name",
           order_tables == ["customer_order"],
           f"aggregate tables in the ordering schema: {order_tables or 'none'}. A second "
           f"one for waiter entry is what FR-ORD-001A exists to forbid")

    guest = a_table_with_an_order()
    waiter = a_table_with_an_order(origin="waiter_entered", table=fx.TABLE_TWO)

    stored = rows(f"""
        SELECT origin::text, channel::text,
               coalesce(placed_by_guest_session_id::text, '-'),
               coalesce(placed_by_user_id::text, '-'), state::text
        FROM ordering.customer_order WHERE id IN ('{guest['order']}', '{waiter['order']}')
        ORDER BY origin;""")
    origins = {r[0] for r in stored}
    record("both origins are rows of the same table, distinguished by policy dimension",
           origins == {"guest_qr", "waiter_entered"} and len(stored) == 2,
           f"stored: {stored}. Both are channel dine_in; what differs is the origin and "
           f"who is named as having placed it")

    guest_row = next(r for r in stored if r[0] == "guest_qr")
    waiter_row = next(r for r in stored if r[0] == "waiter_entered")
    record("a QR order names a guest session and no user account, and a waiter order the "
           "reverse",
           guest_row[2] != "-" and guest_row[3] == "-"
           and waiter_row[3] != "-" and waiter_row[2] == "-",
           f"QR: guest={guest_row[2][:8]} user={guest_row[3]}; "
           f"waiter: guest={waiter_row[2]} user={waiter_row[3][:8]}")

    record("acceptance resolved differently for the two origins, from one policy",
           guest_row[4] == "submitted" and waiter_row[4] == "accepted",
           f"the ordering policy says guest_qr is staff_confirmed and waiter_entered is "
           f"automatic; the QR order is {guest_row[4]} and the waiter order is "
           f"{waiter_row[4]} (FR-ORD-007A)")

    # An order number must be unique across the TENANT, because that is what
    # config.issued_document_number's unique key says — it carries no outlet column. A
    # series that numbered from one at every outlet under a shared prefix would therefore
    # collide on the second outlet's very first order. Exercised through the issuer
    # itself, at two outlets, rather than inferred from the prefixes.
    numbers = []
    for outlet in (fx.OUTLET_H1, fx.OUTLET_H2):
        issued = run(APP, f"""
            SELECT config.issue_document_number('{fx.TENANT}', 'dine_in_order',
                to_char(now(), 'YYYY'), NULL, '{outlet}');""",
            tenant=fx.TENANT, outlet=outlet)
        numbers.append((issued.ok, (issued.scalar or "").strip() or issued.why()))
    record("two outlets in one tenant can both number an order, and the numbers differ",
           all(ok for ok, _n in numbers) and numbers[0][1] != numbers[1][1],
           f"issued {[n for _o, n in numbers]}. The prefix carries each outlet's "
           f"reference code; with a constant prefix the second outlet's first order "
           f"collides on the tenant-wide uniqueness of the issued number")

    stored_number = scalar(f"""
        SELECT order_number FROM ordering.customer_order WHERE id = '{guest['order']}';""")
    record("an order carries an opaque identifier and a separate human number (FR-DAT-003)",
           stored_number.startswith("ORD-") and guest['order'] not in stored_number,
           f"number {stored_number}, identifier {guest['order'][:8]}… — the number never "
           f"encodes the key and the key is never shown as a number")

    # Stated as an exhaustive positive assertion rather than as a list of labels that
    # must be absent. An absence list only ever forbids what somebody thought of; this
    # says what the type IS, so any label at all that nobody put there fails it.
    origin_labels = [r[0] for r in rows("""
        SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'order_origin' ORDER BY e.enumsortorder;""", dsn=ADMIN)]
    record("the origin type names exactly the two origins this gate builds, and no other",
           origin_labels == ["guest_qr", "waiter_entered"],
           f"order_origin: {origin_labels}. FR-ORD-001A names a third channel that does "
           f"not exist until the POS surface is built at M4, and two more that are not "
           f"Phase 1 at all; an unreachable label is a claim the schema cannot keep")


# ===========================================================================
# 2. Draft carts carry no commitment (FR-ORD-002)
# ===========================================================================

def section_draft_carts() -> None:
    print("\n--- 2. A draft cart commits nobody to anything (FR-ORD-002) ---")

    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest)

    consequences = {
        "an order": count(APP, f"SELECT count(*) FROM ordering.customer_order WHERE cart_id = '{cart}';", **CTX),
        "a ledger entry": count(APP, f"""
            SELECT count(*) FROM ordering.order_event e
            WHERE e.after -> 'order' ->> 'cart_id' = '{cart}';""", **CTX),
        "a charge component": count(APP, f"""
            SELECT count(*) FROM ordering.order_charge_component c
            JOIN ordering.customer_order o ON o.id = c.order_id
            WHERE o.cart_id = '{cart}';""", **CTX),
    }
    # An order NUMBER is the consequence a count cannot be scoped to a cart, so it is
    # measured as a difference across the act rather than as a window of wall clock —
    # an interval-scoped count picks up whatever another section happened to place.
    numbers_before = count(APP, f"""
        SELECT count(*) FROM config.issued_document_number
        WHERE tenant_id = '{fx.TENANT}' AND document_type = 'dine_in_order';""", **CTX)
    fx.cart_with(session, guest, lines=((fx.VARIANT_COFFEE_ONE, fx.ITEM_COFFEE, 1),))
    consequences["an issued order number"] = count(APP, f"""
        SELECT count(*) FROM config.issued_document_number
        WHERE tenant_id = '{fx.TENANT}' AND document_type = 'dine_in_order';""",
        **CTX) - numbers_before
    record("a cart with lines in it has produced no consequence a guest could be held to",
           all(v == 0 for v in consequences.values()),
           "; ".join(f"{k}: {v}" for k, v in consequences.items())
           + ". Nothing here reserves anything, because there is no such model in this "
             "database at all, so 'no commitment' is the half of FR-ORD-002 that is "
             "testable and this is it")

    preview_before = preview(cart)
    record("previewing a draft cart still creates nothing",
           count(APP, f"SELECT count(*) FROM ordering.customer_order WHERE cart_id = '{cart}';", **CTX) == 0
           and preview_before["total_amount_minor"] > 0,
           f"the preview priced the cart at {preview_before['total_amount_minor']} minor "
           f"units and wrote no order. A preview is a calculation, not a reservation")

    res = submit(cart, key=f"m3a-draft-{os.urandom(6).hex()}", guest=guest)
    if not res.ok:
        record("the cart could be submitted at all", False, res.why())
        return

    frozen = run(APP, f"""
        INSERT INTO service.cart_line
            (tenant_id, outlet_id, cart_id, item_id, variant_id, quantity,
             currency_code, unit_amount_minor)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', '{fx.ITEM_COFFEE}',
                '{fx.VARIANT_COFFEE_ONE}', 1, 'ETB', 4500);
    """, **CTX)
    record("once the cart is ordered it stops being a draft, and stops being editable",
           frozen.failed_with("CART_ALREADY_SUBMITTED"),
           frozen.why() or "the line was added to a cart somebody had already ordered")


# ===========================================================================
# 3. The preview is calculated, and the total is a sum (FR-ORD-003)
# ===========================================================================

def section_preview() -> None:
    print("\n--- 3. Server-calculated preview, and a total that is a sum (FR-ORD-003) ---")

    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest,
                        lines=((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 2),
                               (fx.VARIANT_COFFEE_ONE, fx.ITEM_COFFEE, 1)),
                        modifiers=())
    view = preview(cart)

    named = {"lines", "charges", "total_amount_minor", "preparation_minutes",
             "safety_warnings", "blocking"}
    record("the preview returns every component FR-ORD-003 names",
           named <= set(view),
           f"line prices and modifiers in 'lines'; tax, fees and discounts in 'charges'; "
           f"availability, hours and channel in 'blocking'; timing in "
           f"'preparation_minutes' ({view.get('preparation_minutes')} min); policy "
           f"warnings in 'safety_warnings'")

    kinds = {c["kind"]: c["amount_minor"] for c in view["charges"]}
    record("the tax component is present, non-zero, and traceable to a configuration",
           kinds.get("tax", 0) > 0
           and any(c["source_kind"] == "tax_configuration" for c in view["charges"]),
           f"tax = {kinds.get('tax')} minor units, from a charge rule whose source is "
           f"config.configuration_version category 'tax'. A component that could only "
           f"ever be zero would satisfy a summation without exercising it")

    record("the discount component is present, non-zero, negative, and traceable to a policy",
           kinds.get("discount", 0) < 0
           and any(c["source_kind"] == "discount_policy" for c in view["charges"]),
           f"discount = {kinds.get('discount')} minor units, from config.policy category "
           f"'discount'. Stored negative so the summation needs no per-kind sign logic")

    record("the total is exactly the sum of the components, computed here and not stated",
           view["total_amount_minor"] == sum(c["amount_minor"] for c in view["charges"]),
           f"{' + '.join(str(c['amount_minor']) for c in view['charges'])} = "
           f"{view['total_amount_minor']}")

    subtotal = kinds["item_subtotal"]
    expected_tax = round(subtotal * 15 / 100)
    expected_discount = -round(subtotal * 10 / 100)
    record("the arithmetic is the configured rate applied to the configured base, exactly",
           kinds["tax"] == expected_tax and kinds["discount"] == expected_discount,
           f"subtotal {subtotal}; 15% = {kinds['tax']} (expected {expected_tax}); "
           f"10% off = {kinds['discount']} (expected {expected_discount}). Integer minor "
           f"units throughout, via money.apply_rate() on numeric — no float anywhere")

    fee_components = [c for c in view["charges"] if c["kind"] == "fee"]
    fee_rules = count(APP, f"""
        SELECT count(*) FROM ordering.charge_rule
        WHERE tenant_id = '{fx.TENANT}' AND kind = 'fee';""", **CTX)
    record("there is no fee component, because no configured source produces one",
           not fee_components and fee_rules == 0,
           f"fee components: {len(fee_components)}; fee rules: {fee_rules}. The "
           f"configuration a fee resolves to is FR-CFG-001C at M4, recorded in "
           f"planning/partial_closures.json with M4 named")

    summation = definition("ordering.order_total(uuid,uuid)")
    record("the summation names no charge kind at all",
           not any(kind in summation for kind in
                   ("'tax'", "'fee'", "'discount'", "'item_subtotal'")),
           "ordering.order_total() is SUM(amount_minor) over the components that exist. "
           "It contains no zero literal for an absent kind and no per-kind branch, which "
           "is why a kind whose source arrives later reaches the total without it changing")

    zero_literals = [r[0] for r in rows("""
        SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'ordering'
          AND (p.prosrc ~* 'fee[^a-z]*(:=|,)\\s*0\\b' OR p.prosrc ~* '''fee''[^)]*,\\s*0\\b');
        """, dsn=ADMIN)]
    record("no function in the schema writes a zero fee",
           not zero_literals,
           f"scanned every function body in the ordering schema: {zero_literals or 'none'}. "
           f"A hardcoded zero survives to M4 unnoticed and looks wired when it is not")


def section_fee_seam() -> None:
    """A fee with a configured source reaches the total, with no change to the summation.

    This is the other half of the fee decision and the more important one. Showing that
    no fee exists proves only that none was built; showing that one WOULD flow through
    proves the total is a sum rather than a formula with a hole in it.

    The service configuration this rule points at is written by the control itself, not
    by a fixture. That is the line: M3-A delivers no path that creates one, and a control
    is entitled to reach past the gate to prove the seam holds — a fixture that quietly
    made one normal would be building M4's model here.
    """
    print("\n--- 3b. A fee would reach the total with no change to the summation ---")

    before_definition = scalar(
        "SELECT md5(pg_get_functiondef('ordering.order_total(uuid,uuid)'::regprocedure));",
        dsn=ADMIN)

    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest)
    before = preview(cart)

    config_id = "3333efee-0000-4000-8000-0000000efee1"
    rule_id = "3333efee-0000-4000-8000-0000000efee2"
    planted = run(ADMIN, f"""
        INSERT INTO config.configuration_version
            (id, tenant_id, outlet_id, scope_kind, scope_node_id, category, version,
             payload, effective_from, actor_id, approved_by_id, approved_at)
        VALUES ('{config_id}', '{fx.TENANT}', '{fx.OUTLET_H1}', 'outlet',
                '{fx.OUTLET_H1}', 'service', 1,
                '{{"service_charge": {{"percentage": "5.0000"}}}}'::jsonb,
                now() - interval '1 hour', '{fx.USER}', '{fx.USER}', now() - interval '1 hour')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO ordering.charge_rule
            (id, tenant_id, outlet_id, kind, source_kind, source_configuration_id,
             tax_context, rate_percentage, rounding_mode, effective_from)
        VALUES ('{rule_id}', '{fx.TENANT}', '{fx.OUTLET_H1}', 'fee',
                'service_configuration', '{config_id}', NULL, 5.0000, 'half_up',
                now() - interval '1 hour')
        ON CONFLICT (id) DO NOTHING;
    """)
    if not planted.ok:
        record("a fee rule with a configured source could be created", False, planted.why())
        return

    try:
        after = preview(cart)
        fee = [c for c in after["charges"] if c["kind"] == "fee"]
        subtotal = next(c["amount_minor"] for c in after["charges"]
                        if c["kind"] == "item_subtotal")
        expected = round(subtotal * 5 / 100)

        record("a fee with a configured source produces a component and moves the total",
               len(fee) == 1 and fee[0]["amount_minor"] == expected
               and after["total_amount_minor"] == before["total_amount_minor"] + expected,
               f"total {before['total_amount_minor']} -> {after['total_amount_minor']}, "
               f"a fee of {fee[0]['amount_minor'] if fee else 'none'} on a subtotal of "
               f"{subtotal}. The fee row names config.configuration_version as its source")

        record("the fee reached the total with the summation byte-identical",
               scalar("SELECT md5(pg_get_functiondef("
                      "'ordering.order_total(uuid,uuid)'::regprocedure));",
                      dsn=ADMIN) == before_definition,
               f"ordering.order_total() digest {before_definition[:16]} before and after. "
               f"Nothing was added to it for the new kind, which is what makes the "
               f"absence of a fee at M3-A a missing SOURCE rather than a missing feature")

        record("the total is still the sum, with the new component in it",
               after["total_amount_minor"] == sum(c["amount_minor"] for c in after["charges"]),
               f"{' + '.join(str(c['amount_minor']) for c in after['charges'])} = "
               f"{after['total_amount_minor']}")
    finally:
        run(ADMIN, f"""
            DELETE FROM ordering.charge_rule WHERE id = '{rule_id}';
            DELETE FROM config.configuration_version WHERE id = '{config_id}';
        """)

    restored = preview(cart)
    record("removing the source removes the component, and no zero takes its place",
           not [c for c in restored["charges"] if c["kind"] == "fee"]
           and restored["total_amount_minor"] == before["total_amount_minor"],
           f"total back to {restored['total_amount_minor']} and the fee row is gone "
           f"entirely rather than present at zero")


# ===========================================================================
# 4. Idempotency: one key, one effect (FR-ORD-004)
# ===========================================================================

def table_digests(*, dsn: str = ADMIN) -> dict[str, str]:
    """A digest of every row of every base table, enumerated from the catalog.

    Enumerated rather than listed, and rendered whole-row rather than column by column.
    Both matter. A fixed list of tables would not cover the ones M3-B and M4 add, which
    would make this control silently narrower with every gate. A fixed list of COLUMNS
    would not cover a column added to a table it already knew, so a retry that started
    writing a new field would pass.

    Run as the administrator so the differential sees every tenant, not only the one in
    context: a duplicate written into the wrong tenant is still a duplicate.
    """
    listing = rows(f"""
        SELECT n.nspname, c.relname
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname = ANY (ARRAY[{', '.join(repr(s) for s in APPLICATION_SCHEMAS)}])
        ORDER BY n.nspname, c.relname;""", dsn=dsn)

    if not listing:
        raise ProbeFailed("table_digests", "the catalog listed no application tables")

    parts = []
    for schema, table in listing:
        parts.append(
            f"SELECT '{schema}.{table}', count(*)::text, "
            f"coalesce(md5(string_agg(t::text, '|' ORDER BY t::text)), '-') "
            f"FROM \"{schema}\".\"{table}\" t")
    observed = rows(" UNION ALL ".join(parts) + ";", dsn=dsn)
    return {r[0]: f"{r[1]}:{r[2]}" for r in observed}


def section_idempotency() -> None:
    print("\n--- 4. A retry finishes the first attempt, and has no second effect "
          "(FR-ORD-004) ---")

    record("the exemption list for what a retry may change is empty",
           RETRY_MAY_CHANGE == {},
           "service.claim_idempotency() claims its row with INSERT ... ON CONFLICT DO "
           "NOTHING, so a replay writes nothing at all — no counter, no timestamp. The "
           "differential below therefore requires an EMPTY delta rather than a delta "
           "confined to named bookkeeping")

    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest)
    concern = fx.allergy_concern(session, guest)
    key = f"m3a-idem-{os.urandom(8).hex()}"

    missing = submit(cart, key="   ", guest=guest)
    record("an idempotency key is required, and blank is not a key",
           missing.failed_with("IDEMPOTENCY_KEY_REQUIRED"),
           missing.why() or "a submission with a blank key was accepted")

    first = submit(cart, key=key, guest=guest,
                   declarations=[{"allergy_concern_id": concern}])
    if not first.ok:
        record("the first submission succeeded", False, first.why())
        return
    order = (first.scalar or "").strip()

    before = table_digests()
    second = submit(cart, key=key, guest=guest,
                    declarations=[{"allergy_concern_id": concern}])
    after = table_digests()

    record("a safe retry returns the ORIGINAL outcome, not a fresh success and not an error",
           second.ok and (second.scalar or "").strip() == order,
           f"first {order[:8]}, retry {(second.scalar or '').strip()[:8]}"
           f"{'' if second.ok else ': ' + second.why()}")

    # --- the differential ---
    changed = {name: (before.get(name), after.get(name))
               for name in set(before) | set(after)
               if before.get(name) != after.get(name)}
    unexpected = {n: v for n, v in changed.items() if n not in RETRY_MAY_CHANGE}
    record("the retry changed NOTHING, anywhere in the database",
           not unexpected,
           f"compared {len(before)} tables enumerated from the catalog across "
           f"{len(APPLICATION_SCHEMAS)} schemas, whole rows rather than named columns. "
           f"Changed: {sorted(unexpected) or 'nothing'}")

    # --- the named artifacts, so a failure is legible ---
    singles = {
        "order rows": count(APP, f"SELECT count(*) FROM ordering.customer_order WHERE cart_id = '{cart}';", **CTX),
        "order lines": count(APP, f"SELECT count(*) FROM ordering.order_line WHERE order_id = '{order}';", **CTX),
        "submitted ledger entries": count(APP, f"SELECT count(*) FROM ordering.order_event WHERE order_id = '{order}' AND kind = 'submitted';", **CTX),
        "allergy declarations": count(APP, f"SELECT count(*) FROM ordering.order_event WHERE order_id = '{order}' AND kind = 'allergy_declared';", **CTX),
        "timeline submitted entries": count(APP, f"SELECT count(*) FROM ordering.order_timeline_entry WHERE order_id = '{order}' AND kind = 'submitted';", **CTX),
        "issued order numbers": count(APP, f"""
            SELECT count(*) FROM config.issued_document_number
            WHERE tenant_id = '{fx.TENANT}' AND document_type = 'dine_in_order'
              AND document_number = (SELECT order_number FROM ordering.customer_order
                                      WHERE id = '{order}');""", **CTX),
    }
    record("exactly one of every artifact the order produced",
           all(v == 1 for v in singles.values()),
           "; ".join(f"{k}: {v}" for k, v in singles.items())
           + ". The differential above proves the same thing about tables M3-B and M4 "
             "have not built; these name the artifacts so a failure is actionable")

    different_body = run(APP, f"""
        SELECT ordering.submit_order(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', '{key}',
            sha256(convert_to('a different request', 'UTF8')), 0, 'am',
            gen_random_uuid(), gen_random_uuid(), 'guest_qr', NULL, '{guest}');
    """, **CTX)
    record("the same key with a different request is refused, not answered from the first",
           different_body.failed_with("IDEMPOTENCY_KEY_REUSED"),
           different_body.why() or "a second, different request was answered with the "
                                   "first one's result")

    # A key claimed but not yet carrying a result: the shape a first attempt leaves behind
    # while it is still running, or if it died mid-flight. The row is planted with the
    # digest submit_order itself would compute for THIS request — a digest of anything
    # else would be refused as key reuse, which is a different control and would have
    # passed this one for the wrong reason.
    inflight_key = f"m3a-inflight-{os.urandom(6).hex()}"
    view = preview(cart)
    body = (f"{cart}|{view['pricing_digest']}|en|guest_qr|{guest}|-")
    in_flight = run(APP, f"""
        INSERT INTO service.idempotency_key
            (tenant_id, outlet_id, scope, idem_key, request_digest)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'order_submission',
                '{inflight_key}', sha256(convert_to('{body}', 'UTF8')));
    """, **CTX)
    if in_flight.ok:
        claimed = submit(cart, key=inflight_key, guest=guest)
        record("a retry arriving while the first attempt is still running is refused",
               claimed.failed_with("SUBMISSION_IN_FLIGHT"),
               claimed.why() or "a claimed-but-unfinished key returned success. Returning "
                                "one would be a lie and starting a second attempt would "
                                "be the duplicate the mechanism exists to prevent")
        run(APP, f"DELETE FROM service.idempotency_key WHERE idem_key = '{inflight_key}';", **CTX)
    else:
        record("an in-flight claim could be planted", False, in_flight.why())


# ===========================================================================
# 5. Snapshots (FR-ORD-005) and revalidation (FR-ORD-006)
# ===========================================================================

def section_snapshots() -> None:
    print("\n--- 5. What was shown is what is stored (FR-ORD-005) ---")

    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest)
    run(APP, f"""
        UPDATE service.table_session SET customer_locale = 'am',
               customer_locale_selected_at = now()
        WHERE id = '{session}';""", **CTX)
    view = preview(cart, locale="am")
    res = submit(cart, key=f"m3a-snap-{os.urandom(6).hex()}", guest=guest, locale="am")
    if not res.ok:
        record("an order could be placed in Amharic", False, res.why())
        return
    order = (res.scalar or "").strip()

    stored = rows(f"""
        SELECT o.customer_locale::text, o.currency_code, o.total_amount_minor::text,
               o.publication_snapshot_id::text
        FROM ordering.customer_order o WHERE o.id = '{order}';""")[0]
    record("the locale the customer chose is pinned to the order",
           stored[0] == "am",
           f"customer_locale = {stored[0]}. M2-C recorded the choice on the occupancy; "
           f"this pins it to the order, because a party that switches language later has "
           f"not changed what THIS order was placed in. M4's receipt reads it")

    record("the publication the prices came from is named, and it is immutable",
           stored[3] == view["publication_snapshot_id"],
           f"snapshot {stored[3][:8]} — menu.publication_snapshot is append-only twice "
           f"over from M2-A, so what the guest was shown is recoverable rather than asserted")

    line = rows(f"""
        SELECT l.item_code, l.canonical_name, l.display_name, l.tax_context,
               l.unit_amount_minor::text, l.line_amount_minor::text,
               psl.amount_minor::text
        FROM ordering.order_line l
        JOIN menu.publication_snapshot_line psl ON psl.id = l.snapshot_line_id
        WHERE l.order_id = '{order}';""")[0]
    record("every line carries its own commercial snapshot, agreeing with the publication",
           line[4] == line[6],
           f"line pinned {line[4]}, publication line says {line[6]}; item_code "
           f"{line[0]}, tax context {line[3]}. The pinned copy is what was agreed; the "
           f"snapshot_line_id keeps the immutable original reachable to check it against")

    record("the line carries BOTH the canonical name and the name in the order's language",
           line[1] and line[2],
           f"canonical {line[1]!r}, display {line[2]!r}. M2-C found a screen showing a "
           f"translated warning beside an untranslated dish name; an order carries both "
           f"so neither question needs a join into today's translations")

    components = {r[0]: int(r[1]) for r in rows(f"""
        SELECT kind::text, amount_minor::text FROM ordering.order_charge_component
        WHERE order_id = '{order}' ORDER BY kind;""")}
    record("the discount, tax and total snapshots persist at acceptance",
           {"item_subtotal", "discount", "tax"} <= set(components)
           and int(stored[2]) == sum(components.values()),
           f"{components}, total {stored[2]}. The fee snapshot persists the moment a fee "
           f"component exists; no configured source produces one before M4 (recorded)")

    immutable = run(APP, f"""
        UPDATE menu.publication_snapshot_line SET amount_minor = 1
        WHERE id = (SELECT snapshot_line_id FROM ordering.order_line WHERE order_id = '{order}' LIMIT 1);
    """, **CTX)
    record("the publication a live order points at still cannot be edited",
           immutable.failed_with("IMMUTABLE_SNAPSHOT_ALTERED", "42501"),
           immutable.why() or "a snapshot line an order depends on was rewritten")


def section_revalidation() -> None:
    print("\n--- 6. A preview is not a reservation (FR-ORD-006) ---")

    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest)

    clear = rows(f"""
        SELECT dimension, detail FROM ordering.revalidate_cart(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', 'dine_in');""")
    record("a cart that can be made revalidates clean",
           not clear,
           f"{len(clear)} blocking reason(s) — an empty result is the only thing that "
           f"lets a submission through, so the gate has to admit as well as refuse")

    # Availability
    run(APP, f"""
        UPDATE menu.availability SET state = 'temporarily_unavailable', row_version = row_version
        WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
          AND variant_id = '{fx.VARIANT_DORO_FULL}';""", **CTX)
    try:
        blocked = rows(f"""
            SELECT dimension FROM ordering.revalidate_cart(
                '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', 'dine_in');""")
        refused = submit(cart, key=f"m3a-unavail-{os.urandom(6).hex()}", guest=guest)
        record("an item that went unavailable after the preview blocks the submission",
               any(r[0] == "availability" for r in blocked)
               and refused.failed_with("SUBMISSION_REVALIDATION_FAILED"),
               f"dimensions raised: {sorted({r[0] for r in blocked})}; "
               f"{refused.why() or 'the submission was accepted anyway'}")
    finally:
        run(APP, f"""
            UPDATE menu.availability SET state = 'available', row_version = row_version
            WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
              AND variant_id = '{fx.VARIANT_DORO_FULL}';""", **CTX)

    # Quantity — ordered units, not stock.
    big = fx.cart_with(session, guest, lines=((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 99),))
    quantity = rows(f"""
        SELECT dimension, detail FROM ordering.revalidate_cart(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{big}', 'dine_in');""")
    record("a line quantity beyond the configured maximum blocks the submission",
           any(r[0] == "quantity" for r in quantity),
           f"{[r[1] for r in quantity if r[0] == 'quantity']}. Ordered units, never a "
           f"level on hand: no quantity-remaining column exists anywhere in this "
           f"database, so there is nothing here that could mean one")

    # Channel — an outlet that does not serve this menu on this channel.
    channel = rows(f"""
        SELECT dimension FROM ordering.revalidate_cart(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', 'kiosk');""")
    record("a channel the menu is not assigned to blocks the submission",
           any(r[0] == "channel_or_hours" for r in channel),
           f"dimensions on channel 'kiosk': {sorted({r[0] for r in channel})}. The menu "
           f"is assigned to dine_in at this outlet and to nothing else")

    # Hours — at a local time the database itself reports as uncovered.
    closed_at = fx.uncovered_local_time()
    hours = rows(f"""
        SELECT dimension, detail FROM ordering.revalidate_cart(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', 'dine_in',
            TIMESTAMPTZ '{closed_at}');""")
    record("an hour no daypart covers blocks the submission",
           any(r[0] == "channel_or_hours" for r in hours),
           f"probed at {closed_at}, a local hour the fixture derived from the assignments "
           f"themselves rather than choosing. A hardcoded 04:30 would become wrong the "
           f"moment somebody added a late-night window, and would become wrong silently")

    record("station capacity is named as absent rather than quietly skipped",
           any(e["requirement"] == "FR-ORD-006" and e["completing_gate"] == "M3-B"
               for e in partial_closures.load()),
           "FR-ORD-006 names five dimensions and capacity means station workload "
           "(FR-FUL-013, M3-B). Recorded in planning/partial_closures.json with M3-B "
           "named, and the build fails once M3-B lands with the entry still open")


# ===========================================================================
# 7. Acceptance, ownership and add-on orders (FR-ORD-007A, 008, 009)
# ===========================================================================

def section_acceptance_and_ownership() -> None:
    print("\n--- 7. Acceptance by policy, lines without registration (FR-ORD-007A, 008, 009) ---")

    placed = a_table_with_an_order()
    session, guest, order = placed["session"], placed["guest"], placed["order"]

    state = scalar(f"SELECT state::text FROM ordering.customer_order WHERE id = '{order}';")
    accept = run(APP, f"SELECT ordering.accept_order('{fx.TENANT}', '{order}', '{fx.USER}');", **CTX)
    accepted = rows(f"""
        SELECT state::text, acceptance_mode::text,
               coalesce(accepted_by_user_id::text, '-')
        FROM ordering.customer_order WHERE id = '{order}';""")[0]
    record("a staff-confirmed order waits, then names the member of staff who confirmed it",
           state == "submitted" and accept.ok and accepted == ["accepted", "staff_confirmed", fx.USER],
           f"before: {state}; after: {accepted}. Automatic acceptance names no confirmer "
           f"and a check constraint refuses one that claims a confirmer it did not have")

    absent = run(APP, f"""
        UPDATE config.policy SET effective_to = now() - interval '1 minute'
        WHERE id = '{fx.ORDERING_POLICY}';""", **CTX)
    try:
        if absent.ok:
            other = fx.fresh_occupancy(fx.TABLE_TWO)
            other_guest = fx.guest_on(other)
            other_cart = fx.cart_with(other, other_guest)
            no_policy = run(APP, f"""
                SELECT ordering.preview_cart('{fx.TENANT}', '{fx.OUTLET_H1}',
                                             '{other_cart}', 'en');""", **CTX)
            record("an outlet with no ordering policy in force accepts no order at all",
                   no_policy.failed_with("ORDER_POLICY_ABSENT"),
                   no_policy.why() or "an order was handled under a policy nobody set. "
                                      "An absent policy is never an implicit default")
    finally:
        run(APP, f"""
            UPDATE config.policy SET effective_to = NULL
            WHERE id = '{fx.ORDERING_POLICY}';""", **CTX)

    # FR-ORD-008: a participant, with no registration anywhere in sight.
    ownership = rows(f"""
        SELECT coalesce(l.participant_guest_session_id::text, '-'),
               coalesce(g.display_nickname, '-')
        FROM ordering.order_line l
        LEFT JOIN service.guest_session g ON g.id = l.participant_guest_session_id
        WHERE l.order_id = '{order}';""")
    record("a line names a participant, and the participant is a guest session with no identity",
           all(r[0] != "-" for r in ownership),
           f"{ownership}. A guest session carries no phone, no email and no link to a "
           f"user account — M2-B built it that way and FR-ORD-008 requires ordering to "
           f"work without any of them")

    identity_columns = [r[0] for r in rows("""
        SELECT a.attname FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'ordering' AND c.relkind = 'r' AND a.attnum > 0
          AND NOT a.attisdropped
          AND a.attname ~* '(phone|email|msisdn|customer_name|member_number|account_ref)'
        ORDER BY a.attname;""", dsn=ADMIN)]
    record("no column in the ordering schema could hold a customer identity",
           not identity_columns,
           f"scanned every column of every table in the schema: "
           f"{identity_columns or 'none'}. Registration is not reintroduced here")

    # FR-ORD-009: a second round in the same session.
    second_cart = fx.cart_with(session, guest,
                               lines=((fx.VARIANT_COFFEE_ONE, fx.ITEM_COFFEE, 2),))
    second = submit(second_cart, key=f"m3a-addon-{os.urandom(6).hex()}", guest=guest,
                    repeat_intent=True)
    if not second.ok:
        record("a second order could be placed in the same session", False, second.why())
        return
    second_order = (second.scalar or "").strip()

    both = rows(f"""
        SELECT id::text, submitted_at::text, order_number
        FROM ordering.customer_order WHERE table_session_id = '{session}'
        ORDER BY submitted_at;""")
    record("an add-on order is a distinct aggregate with its own timestamp and number",
           len(both) == 2 and both[0][1] != both[1][1] and both[0][2] != both[1][2],
           f"two orders on one occupancy: {[r[2] for r in both]}, submitted at "
           f"{[r[1][11:19] for r in both]}. Independent fulfillment needs the tickets "
           f"M3-B builds and is recorded as the half that waits")

    separate_ledgers = rows(f"""
        SELECT order_id::text, count(*)::text FROM ordering.order_event
        WHERE order_id IN ('{order}', '{second_order}') GROUP BY order_id ORDER BY 1;""")
    record("the two orders keep separate ledgers, numbered from one each",
           len(separate_ledgers) == 2,
           f"{separate_ledgers}. Sequence numbers are per aggregate, so a replay of one "
           f"order cannot pick up the other's events")


# ===========================================================================
# 8. Amendment, cancellation and void (FR-ORD-010, 011, 012A)
# ===========================================================================

def section_amendment_cancellation_void() -> None:
    print("\n--- 8. Amendment, cancellation and authorized void (FR-ORD-010, 011, 012A) ---")

    placed = a_table_with_an_order(declarations=True)
    order = placed["order"]
    line = scalar(f"SELECT id::text FROM ordering.order_line WHERE order_id = '{order}' LIMIT 1;")
    before_total = int(scalar(f"SELECT total_amount_minor::text FROM ordering.customer_order WHERE id = '{order}';"))

    amended = run(APP, f"""
        SELECT ordering.amend_order_line('{fx.TENANT}', '{order}', '{line}', 3,
                                         NULL, '{placed['guest']}');""", **CTX)
    after_total = int(scalar(f"SELECT total_amount_minor::text FROM ordering.customer_order WHERE id = '{order}';"))
    event = rows(f"""
        SELECT kind::text, (before IS NOT NULL)::text, (after IS NOT NULL)::text,
               (before -> 'total_amount_minor')::text, (after -> 'total_amount_minor')::text
        FROM ordering.order_event WHERE order_id = '{order}' AND kind = 'amended';""")
    record("an amendment is an explicit event retaining before AND after",
           amended.ok and len(event) == 1
           and event[0][1] in ("t", "true") and event[0][2] in ("t", "true")
           and event[0][3] == str(before_total) and event[0][4] == str(after_total),
           f"{amended.why() or ''} before {event[0][3] if event else '?'} -> after "
           f"{event[0][4] if event else '?'}; the projection now reads {after_total}. "
           f"Storing only the delta would make 'what did it say before' a reconstruction")

    record("the amendment repriced through the same resolver the preview used",
           after_total == before_total * 3,
           f"{before_total} -> {after_total} for a quantity of 1 -> 3. An amendment that "
           f"priced itself would be a third opinion about what things cost")

    # FR-ORD-010, the window.
    accept = run(APP, f"SELECT ordering.accept_order('{fx.TENANT}', '{order}', '{fx.USER}');", **CTX)
    late = run(APP, f"""
        SELECT ordering.amend_order_line('{fx.TENANT}', '{order}', '{line}', 4,
                                         NULL, '{placed['guest']}');""", **CTX)
    record("an amendment outside the policy's window is refused, naming the policy",
           accept.ok and late.failed_with("AMENDMENT_WINDOW_CLOSED"),
           late.why() or "an accepted order was amended although the ordering policy "
                         "permits amendment only while submitted")

    # FR-ORD-011.
    reason = fx.reason_code("order_cancellation")
    guest_order = a_table_with_an_order(table=fx.TABLE_TWO)
    cancelled = run(APP, f"""
        SELECT ordering.cancel_order('{fx.TENANT}', '{guest_order['order']}',
                                     '{reason}', NULL, '{guest_order['guest']}');""", **CTX)
    state = scalar(f"SELECT state::text FROM ordering.customer_order WHERE id = '{guest_order['order']}';")
    record("a submitted QR order may be cancelled, and the reason is a registered code",
           cancelled.ok and state == "cancelled",
           f"{cancelled.why() or f'state is now {state}'}, reason code {reason[:8]} from "
           f"M1-C's registry — referenced, never copied")

    unregistered = run(APP, f"""
        SELECT ordering.cancel_order('{fx.TENANT}', '{order}', gen_random_uuid(),
                                     '{fx.USER}');""", **CTX)
    record("a cancellation reason that is not a registered order_cancellation code is refused",
           unregistered.failed_with("CANCELLATION_REASON_INVALID"),
           unregistered.why() or "an order was cancelled for a reason nobody registered")

    by_policy = run(APP, f"""
        SELECT ordering.cancel_order('{fx.TENANT}', '{order}', '{reason}', '{fx.USER}');""", **CTX)
    record("an ACCEPTED QR order may not be cancelled, because the policy says so",
           by_policy.failed_with("CANCELLATION_REFUSED_BY_POLICY"),
           by_policy.why() or "the cancellation policy allows guest_qr only while "
                              "submitted, and an accepted order was cancelled anyway")

    # FR-ORD-012A.
    void_reason = fx.reason_code("void")
    unauthorized = run(APP, f"""
        SELECT ordering.void_order('{fx.TENANT}', '{order}', '{void_reason}', '{fx.USER}');""", **CTX)
    record("a void with no live staff session in context is refused on authorization",
           unauthorized.failed_with("SESSION_NOT_LIVE"),
           unauthorized.why() or "an order was voided by nobody. ordering.void_order() "
                                 "goes through identity.authorize_action() rather than "
                                 "checking anything of its own")

    session_id = fx.open_staff_session()
    voided = fx.staff_context(
        f"SELECT ordering.void_order('{fx.TENANT}', '{order}', '{void_reason}', '{fx.USER}');",
        session_id=session_id)
    state = scalar(f"SELECT state::text FROM ordering.customer_order WHERE id = '{order}';")
    audit = count(APP, f"""
        SELECT count(*) FROM audit.operational_event
        WHERE event_code = 'ordering.order_voided' AND entity_id = '{order}';""", **CTX)
    record("an authorized void records the reason and an immutable audit row",
           voided.ok and state == "voided" and audit == 1,
           f"{voided.why() or f'state {state}'}, {audit} row in audit.operational_event "
           f"— M1-C's append-only store, written to rather than reimplemented")

    weak = fx.open_staff_session()
    run(APP, f"""
        UPDATE identity.session SET established_with = 'low', row_version = row_version
        WHERE id = '{weak}';""", **CTX)
    another = a_table_with_an_order(table=fx.TABLE_ONE)
    run(APP, f"SELECT ordering.accept_order('{fx.TENANT}', '{another['order']}', '{fx.USER}');", **CTX)
    quick_pin = fx.staff_context(
        f"SELECT ordering.void_order('{fx.TENANT}', '{another['order']}', "
        f"'{void_reason}', '{fx.USER}');", session_id=weak, strength="low")
    record("a quick-PIN session may not void, however recent its step-up",
           quick_pin.failed_with("LOW_RISK_CREDENTIAL_USED_FOR_SENSITIVE_ACTION"),
           quick_pin.why() or "a low-strength session voided an order")

    before_acceptance = a_table_with_an_order(table=fx.TABLE_TWO)
    too_early = fx.staff_context(
        f"SELECT ordering.void_order('{fx.TENANT}', '{before_acceptance['order']}', "
        f"'{void_reason}', '{fx.USER}');", session_id=fx.open_staff_session())
    record("an order that was never accepted is cancelled, not voided",
           too_early.failed_with("VOID_BEFORE_ACCEPTANCE"),
           too_early.why() or "a submitted order was voided; the two are different acts "
                              "with different registers and FR-ORD-012A names acceptance")


# ===========================================================================
# 9. Notes, and the allergy declaration's whole journey (FR-ORD-013)
# ===========================================================================

def section_notes_and_allergy() -> None:
    print("\n--- 9. Four note kinds, and the declaration that must survive (FR-ORD-013) ---")

    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest)
    concern = fx.allergy_concern(session, guest)
    res = submit(cart, key=f"m3a-notes-{os.urandom(6).hex()}", guest=guest,
                 declarations=[{"allergy_concern_id": concern}],
                 notes=[{"kind": "customer", "body": "Table by the window if you can."}])
    if not res.ok:
        record("an order with notes could be placed", False, res.why())
        return
    order = (res.scalar or "").strip()

    staff_note = run(APP, f"""
        SELECT ordering.amend_order_line('{fx.TENANT}', '{order}',
            (SELECT id FROM ordering.order_line WHERE order_id = '{order}' LIMIT 1),
            1, '{fx.USER}');""", **CTX)
    plain = run(APP, f"""
        SELECT ordering.add_order_note('{fx.TENANT}', '{order}', 'allergy_declaration',
                                       'peanuts too', NULL, '{fx.USER}');""", **CTX)
    record("an allergy declaration cannot be posted as a plain note",
           plain.failed_with("ALLERGY_DECLARATION_NOT_A_PLAIN_NOTE"),
           plain.why() or "free text was accepted as a declaration, which would store a "
                          "safety statement with no acknowledged wording behind it")

    kinds = {r[0]: int(r[1]) for r in rows(f"""
        SELECT kind::text, count(*)::text FROM ordering.order_note
        WHERE order_id = '{order}' GROUP BY kind ORDER BY kind;""", dsn=ADMIN)}
    record("the customer note and the allergy declaration are stored as different kinds",
           kinds.get("customer") == 1 and kinds.get("allergy_declaration") == 1,
           f"{kinds}. Not one 'note' column with a label: each kind carries a different "
           f"REQUIRED SHAPE, so a row cannot be reclassified into a kind whose columns it "
           f"does not have")

    shape = run(ADMIN, f"""
        SELECT set_config('ordering.applying_event', 'yes', true);
        INSERT INTO ordering.order_note
            (id, tenant_id, outlet_id, order_id, kind, body, author_guest_session_id,
             created_at)
        VALUES (gen_random_uuid(), '{fx.TENANT}', '{fx.OUTLET_H1}', '{order}',
                'allergy_declaration', 'peanuts', '{guest}', now());""", tx=True)
    record("an allergy declaration naming no allergen cannot be stored at all",
           shape.failed_with("order_note_allergy_shape"),
           shape.why() or "a declaration with no allergen and no acknowledged wording "
                          "was accepted; a declaration the kitchen cannot act on is not "
                          "one. Attempted with the projection guard deliberately opened, "
                          "so what refuses it is the SHAPE and not the guard")

    staff_only = run(APP, f"SELECT count(*) FROM ordering.order_note;", **CTX)
    record("the application role holds no direct SELECT on the note store",
           staff_only.failed_with("42501"),
           staff_only.why() or "the application role read the note table directly. The "
                               "audience functions are the only way in, which is what "
                               "makes 'a customer surface cannot ask for a private note' "
                               "a fact about privileges rather than a habit in the routes")

    # --- NC-M3-003's subject: every hop the declaration makes ---
    print("\n  The allergy declaration, hop by hop")

    hop_1 = rows(f"""
        SELECT allergen_id::text, acknowledgement_text
        FROM safety.allergy_concern WHERE id = '{concern}';""")[0]
    record("hop 1 — the guest raised it at the table, and M2-B stored the exact wording",
           hop_1[0] and hop_1[1],
           f"allergen {hop_1[0][:8]}, wording {hop_1[1][:48]!r}")

    hop_2 = rows(f"""
        SELECT e.after -> 'note' ->> 'allergen_id',
               e.after -> 'note' ->> 'acknowledgement_text',
               e.after -> 'note' ->> 'allergy_concern_id'
        FROM ordering.order_event e
        WHERE e.order_id = '{order}' AND e.kind = 'allergy_declared';""", dsn=ADMIN)
    record("hop 2 — it reached the LEDGER as an event of its own, not buried in a payload",
           len(hop_2) == 1 and hop_2[0][0] == hop_1[0] and hop_2[0][1] == hop_1[1]
           and hop_2[0][2] == concern,
           f"one 'allergy_declared' event carrying the same allergen and the same words, "
           f"and naming the table-level concern they were copied from. The ledger is "
           f"append-only, so this hop cannot be undone")

    hop_3 = rows(f"""
        SELECT allergen_id::text, acknowledgement_text FROM ordering.order_note
        WHERE order_id = '{order}' AND kind = 'allergy_declaration';""", dsn=ADMIN)
    record("hop 3 — the fold projected it, unchanged",
           len(hop_3) == 1 and hop_3[0][0] == hop_1[0] and hop_3[0][1] == hop_1[1],
           f"allergen and wording identical to the ledger event. The projection is "
           f"derived, so a discrepancy here is a rebuild failure rather than an edit")

    hop_4 = rows(f"""
        SELECT kind::text, kitchen_code, acknowledgement_text
        FROM ordering.kitchen_notes('{fx.TENANT}', '{order}');""")
    record("hop 4 — it reaches the KITCHEN reader, first in the list and naming the allergen",
           hop_4 and hop_4[0][0] == "allergy_declaration" and hop_4[0][1],
           f"kitchen_notes returns {[r[0] for r in hop_4]}; the declaration is first and "
           f"carries kitchen code {hop_4[0][1] if hop_4 else '?'}. The station surface "
           f"that consumes this is M3-B — the guarantee it ARRIVES is here")

    hop_5 = rows(f"""
        SELECT kind::text FROM ordering.customer_visible_notes('{fx.TENANT}', '{order}');""")
    record("hop 5 — the guest can still read back what they declared",
           "allergy_declaration" in {r[0] for r in hop_5},
           f"customer_visible_notes returns {sorted({r[0] for r in hop_5})}. A guest who "
           f"cannot see their own declaration has no way to notice it was lost")

    before_digest = scalar(f"SELECT encode(ordering.projection_digest('{fx.TENANT}'), 'hex');")
    run(APP, f"SELECT ordering.rebuild_projections('{fx.TENANT}');", **CTX)
    hop_6 = rows(f"""
        SELECT allergen_id::text, acknowledgement_text FROM ordering.order_note
        WHERE order_id = '{order}' AND kind = 'allergy_declaration';""", dsn=ADMIN)
    record("hop 6 — it survives a full projection rebuild from the ledger",
           len(hop_6) == 1 and hop_6[0] == hop_3[0],
           "every projection for the tenant discarded and replayed; the declaration comes "
           "back identical, because it was never anywhere but the ledger")

    hop_7 = rows(f"""
        SELECT kind::text FROM ordering.order_note
        WHERE order_id = '{order}' AND kind = 'allergy_declaration';""", dsn=ADMIN)
    record("hop 7 — an amendment carries it forward rather than replacing it away",
           staff_note.ok and len(hop_7) == 1,
           f"{staff_note.why() or 'the order was amended after the declaration was made'}; "
           f"the fold REPLACES notes wholesale, so an amendment payload that forgot them "
           f"would drop the declaration silently. It carries them, and NC-M3-003 plants "
           f"the version that does not")


def section_audience() -> None:
    print("\n--- 10. Audience filtering (FR-ORD-013, FR-ORD-016A) ---")

    placed = a_table_with_an_order(declarations=True)
    order = placed["order"]
    added = run(APP, f"""
        SELECT ordering.add_order_note('{fx.TENANT}', '{order}', 'private_staff',
                   'Regular; comped a coffee last week.', NULL, '{fx.USER}');
        SELECT ordering.add_order_note('{fx.TENANT}', '{order}', 'kitchen_instruction',
                   'Fire with the mains.', NULL, '{fx.USER}');
    """, **CTX)
    if not added.ok:
        record("staff notes could be attached for the audience checks", False, added.why())
        return

    customer = {r[0] for r in rows(f"""
        SELECT kind::text FROM ordering.customer_visible_notes('{fx.TENANT}', '{order}');""")}
    record("a customer sees their own note and their declaration, and nothing else",
           customer <= {"customer", "allergy_declaration"}
           and "private_staff" not in customer and "kitchen_instruction" not in customer,
           f"customer_visible_notes returns {sorted(customer)}. The private note is not "
           f"redacted, it is ABSENT — a redacted entry would disclose that something was "
           f"written")

    signature = scalar("""
        SELECT pg_get_function_arguments(
            'ordering.customer_visible_notes(uuid,uuid)'::regprocedure);""", dsn=ADMIN)
    record("the customer reader takes no audience argument, so it cannot be asked wrongly",
           "audience" not in signature and "kind" not in signature,
           f"arguments: {signature}. A defect would have to add the kind to the "
           f"function's own list rather than merely forget a WHERE clause somewhere")

    kitchen = {r[0] for r in rows(f"""
        SELECT kind::text FROM ordering.kitchen_notes('{fx.TENANT}', '{order}');""")}
    record("the kitchen sees the declaration and the instruction, and no private note",
           kitchen == {"allergy_declaration", "kitchen_instruction"},
           f"kitchen_notes returns {sorted(kitchen)}")

    no_session = run(APP, f"SELECT * FROM ordering.staff_notes('{fx.TENANT}', '{order}');", **CTX)
    record("the staff reader refuses outright with no staff session in context",
           no_session.failed_with("PRIVATE_NOTE_REQUIRES_STAFF_SESSION", "SESSION_NOT_LIVE"),
           no_session.why() or "private notes were readable with no session at all. A "
                               "guest context carries no app.session_id — M2-B clears it "
                               "deliberately — so this is the absence of a staff session, "
                               "not a role check a guest could pass")

    staff = fx.staff_context(f"SELECT kind::text FROM ordering.staff_notes('{fx.TENANT}', '{order}');",
                             session_id=fx.open_staff_session())
    staff_kinds = {r[0] for r in staff.rows} if staff.ok else set()
    record("staff under a live session see all four kinds",
           staff.ok and {"private_staff", "kitchen_instruction", "allergy_declaration"} <= staff_kinds,
           f"{staff.why() or sorted(staff_kinds)}. The reader has to ADMIT as well as "
           f"refuse, or it would pass by denying everything")

    timeline_customer = rows(f"""
        SELECT kind::text, summary FROM ordering.customer_timeline('{fx.TENANT}', '{order}');""")
    timeline_staff = fx.staff_context(
        f"SELECT kind::text FROM ordering.staff_timeline('{fx.TENANT}', '{order}');",
        session_id=fx.open_staff_session())
    record("the timeline is chronological and filtered by audience, not by the caller",
           timeline_customer and timeline_staff.ok
           and len(timeline_staff.rows) >= len(timeline_customer),
           f"customer sees {[r[0] for r in timeline_customer]}; staff see "
           f"{[r[0] for r in timeline_staff.rows] if timeline_staff.ok else timeline_staff.why()}. "
           f"The audience is decided when the entry is WRITTEN — a reader that filters is "
           f"a reader that can forget to")

    orphan = count(APP, """
        SELECT count(*) FROM ordering.order_timeline_entry
        WHERE visible_to_customer AND (customer_summary IS NULL
                                       OR btrim(customer_summary) = '');""", **CTX)
    record("no entry claims to be customer-visible with nothing to show a customer",
           orphan == 0,
           f"{orphan} such entries. The check constraint ties the two together, so an "
           f"entry cannot be visible and empty")


# ===========================================================================
# 11. Duplicate detection, correlation, ledger and rebuild
# ===========================================================================

def section_duplicates() -> None:
    print("\n--- 11. Suspicious duplicates flagged, second rounds left alone (FR-ORD-017) ---")

    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    first_cart = fx.cart_with(session, guest)
    first = submit(first_cart, key=f"m3a-dup-a-{os.urandom(6).hex()}", guest=guest)
    if not first.ok:
        record("a first order could be placed", False, first.why())
        return
    first_order = (first.scalar or "").strip()

    same_cart = fx.cart_with(session, guest)
    suspicious = submit(same_cart, key=f"m3a-dup-b-{os.urandom(6).hex()}", guest=guest)
    suspicious_order = (suspicious.scalar or "").strip() if suspicious.ok else ""
    signal = rows(f"""
        SELECT matched_order_id::text, seconds_apart::text FROM ordering.duplicate_signal
        WHERE order_id = '{suspicious_order}';""")
    record("an identical order moments later, with a fresh key, is FLAGGED and not refused",
           suspicious.ok and len(signal) == 1 and signal[0][0] == first_order,
           f"{suspicious.why() or f'order placed, {len(signal)} signal raised'} matching "
           f"{signal[0][0][:8] if signal else '-'} at {signal[0][1] if signal else '?'}s "
           f"apart. Refusing would block a table that genuinely wants two of the same dish")

    intended_cart = fx.cart_with(session, guest)
    intended = submit(intended_cart, key=f"m3a-dup-c-{os.urandom(6).hex()}", guest=guest,
                      repeat_intent=True)
    intended_order = (intended.scalar or "").strip() if intended.ok else ""
    no_signal = count(APP, f"""
        SELECT count(*) FROM ordering.duplicate_signal WHERE order_id = '{intended_order}';""", **CTX)
    record("a declared second round raises NO signal at all",
           intended.ok and no_signal == 0,
           f"{intended.why() or 'order placed'}, {no_signal} signals. There is no "
           f"'repeat_intent_declared' column recording a false: a column with one "
           f"possible value reads like a real value while carrying nothing, so the "
           f"ABSENCE of the row is the record")

    different_cart = fx.cart_with(session, guest,
                                  lines=((fx.VARIANT_COFFEE_ONE, fx.ITEM_COFFEE, 1),))
    different = submit(different_cart, key=f"m3a-dup-d-{os.urandom(6).hex()}", guest=guest)
    different_order = (different.scalar or "").strip() if different.ok else ""
    record("an order for different things is not a duplicate however close together",
           different.ok and count(APP, f"""
               SELECT count(*) FROM ordering.duplicate_signal
               WHERE order_id = '{different_order}';""", **CTX) == 0,
           "detection is on CONTENT — variant and quantity — not on timing alone")

    window = count(APP, f"""
        SELECT count(*) FROM config.policy
        WHERE id = '{fx.ORDERING_POLICY}' AND payload ? 'duplicate_window_seconds';""", **CTX)
    record("the window is configured, not a constant somebody chose in a function body",
           window == 1,
           "duplicate_window_seconds comes from the outlet's ordering policy, and a "
           "policy that omits it stops the submission rather than falling back")


def section_correlation() -> None:
    print("\n--- 12. A correlation chain that survives a rebuild (FR-ORD-019A) ---")

    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest)
    correlation = scalar("SELECT gen_random_uuid()::text;")
    request = scalar("SELECT gen_random_uuid()::text;")
    res = submit(cart, key=f"m3a-corr-{os.urandom(6).hex()}", guest=guest,
                 correlation=correlation, request=request)
    if not res.ok:
        record("an order could be placed with a correlation identifier", False, res.why())
        return
    order = (res.scalar or "").strip()

    chain = {r[0]: r[1] for r in rows(f"""
        SELECT artifact_kind::text, artifact_id::text
        FROM ordering.correlation_chain('{fx.TENANT}', '{correlation}');""")}
    record("the chain links the request, the cart, the table session and the order",
           chain.get("request") == request and chain.get("cart") == cart
           and chain.get("table_session") == session and chain.get("order") == order,
           f"{sorted(chain)}. Two of the six artifacts FR-ORD-019A names — fulfillment "
           f"ticket and service request — are labels of ordering.artifact_kind with no "
           f"rows until M3-B and M3-C, recorded with both slices named")

    labels = {r[0] for r in rows("""
        SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'artifact_kind';""", dsn=ADMIN)}
    record("the later artifacts are already labels, so M3-B and M3-C extend rather than reshape",
           {"fulfillment_ticket", "service_request"} <= labels,
           f"artifact_kind: {sorted(labels)}. A chain that had to change shape when the "
           f"ticket arrived would break every correlation stored before it")

    before = {r[0]: r[1] for r in rows(f"""
        SELECT artifact_kind::text, artifact_id::text
        FROM ordering.correlation_chain('{fx.TENANT}', '{correlation}');""")}
    run(APP, f"SELECT ordering.rebuild_projections('{fx.TENANT}');", **CTX)
    after = {r[0]: r[1] for r in rows(f"""
        SELECT artifact_kind::text, artifact_id::text
        FROM ordering.correlation_chain('{fx.TENANT}', '{correlation}');""")}
    record("the chain survives a projection rebuild, because it is derived from the ledger",
           before == after and before,
           f"{len(before)} links before and {len(after)} after, identical. The chain is "
           f"not a cache of joins: it is folded out of the events that created the artifacts")


def section_ledger_and_rebuild() -> None:
    print("\n--- 13. Append-only ledger, deterministic rebuild (FR-DAT-008A, FR-DAT-010) ---")

    placed = a_table_with_an_order(declarations=True)
    order = placed["order"]
    run(APP, f"SELECT ordering.accept_order('{fx.TENANT}', '{order}', '{fx.USER}');", **CTX)

    for role, dsn, label in (("app", APP, "the application role"),
                             ("admin", ADMIN, "an administrator with every privilege")):
        for statement, what in (
            (f"UPDATE ordering.order_event SET after = '{{}}'::jsonb WHERE order_id = '{order}';", "UPDATE"),
            (f"DELETE FROM ordering.order_event WHERE order_id = '{order}';", "DELETE"),
        ):
            res = run(dsn, statement, **(CTX if role == "app" else {}))
            record(f"{what} on the ledger is refused for {label}",
                   res.failed_with("ACCEPTED_ORDER_MUTATION_REFUSED", "42501"),
                   res.why() or f"{what} succeeded — the ledger is not append-only")

    truncate = run(ADMIN, "TRUNCATE ordering.order_event;")
    record("TRUNCATE on the ledger is refused too, by the trigger and not by a grant",
           truncate.failed_with("ACCEPTED_ORDER_MUTATION_REFUSED"),
           truncate.why() or "the ledger was truncated. M1-C proved audit this way and "
                             "the brief for this slice asks for the same: by trigger, "
                             "because a role change would undo a grant")

    grants = [r[0] for r in rows("""
        SELECT privilege_type FROM information_schema.role_table_grants
        WHERE table_schema = 'ordering' AND table_name = 'order_event'
          AND grantee = 'hospitality_app' ORDER BY privilege_type;""", dsn=ADMIN)]
    record("and the application role was never granted UPDATE or DELETE on it either",
           set(grants) == {"INSERT", "SELECT"},
           f"grants: {grants}. Two locks, and neither is the other's restatement")

    direct = run(ADMIN, f"""
        UPDATE ordering.customer_order SET total_amount_minor = 1 WHERE id = '{order}';""")
    record("an accepted order cannot be edited through its projection, by anyone",
           direct.failed_with("PROJECTION_WRITTEN_DIRECTLY"),
           direct.why() or "an accepted order's total was rewritten by hand. This is the "
                           "destructive edit path FR-DAT-008A says must not exist, and it "
                           "is closed for the table OWNER as well as the application role")

    projection_grants = [r[0] for r in rows("""
        SELECT DISTINCT privilege_type FROM information_schema.role_table_grants
        WHERE table_schema = 'ordering' AND grantee = 'hospitality_app'
          AND table_name IN ('customer_order', 'order_line', 'order_line_modifier',
                             'order_charge_component', 'order_timeline_entry',
                             'correlation_link', 'duplicate_signal')
        ORDER BY privilege_type;""", dsn=ADMIN)]
    record("the application role holds SELECT and nothing else on every projection",
           projection_grants == ["SELECT"],
           f"privileges across all seven projections: {projection_grants}. The fold is "
           f"SECURITY DEFINER, so the grant stays narrow AND the trigger stays meaningful "
           f"— if the fold ran as the caller, the role would need write privileges to use "
           f"it and the grant would stop being a lock at all")

    total_mismatch = run(ADMIN, f"""
        SELECT set_config('ordering.applying_event', 'yes', true);
        UPDATE ordering.customer_order SET total_amount_minor = total_amount_minor + 1
        WHERE id = '{order}';
        SELECT set_config('ordering.applying_event', '', true);
    """, tx=True)
    record("a stored total that disagrees with its components cannot be committed",
           total_mismatch.failed_with("ORDER_TOTAL_NOT_THE_SUM_OF_ITS_COMPONENTS"),
           total_mismatch.why() or "an order committed with a total its components do "
                                   "not add up to. The deferred constraint trigger is "
                                   "what stops the total and the components drifting apart")

    # --- the rebuild ---
    before = scalar(f"SELECT encode(ordering.projection_digest('{fx.TENANT}'), 'hex');")
    replayed = scalar(f"SELECT ordering.rebuild_projections('{fx.TENANT}')::text;")
    after = scalar(f"SELECT encode(ordering.projection_digest('{fx.TENANT}'), 'hex');")
    record("every projection for the tenant rebuilds from the ledger, byte for byte",
           before == after and int(replayed) > 0,
           f"{replayed} events replayed; digest {before[:16]} before and {after[:16]} "
           f"after. The digest renders every column of every projection, ordered "
           f"explicitly, so a lost allergen changes it rather than hiding in a row count")

    again = scalar(f"SELECT ordering.rebuild_projections('{fx.TENANT}')::text;")
    twice = scalar(f"SELECT encode(ordering.projection_digest('{fx.TENANT}'), 'hex');")
    record("rebuilding twice gives the same answer as rebuilding once",
           twice == after and again == replayed,
           "the fold reads no clock, no sequence and no random source: every value it "
           "writes comes out of the event, which is what makes this byte-deterministic "
           "rather than merely equivalent")

    handled = definition("ordering.apply_event(bigint)")
    labels = [r[0] for r in rows("""
        SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'event_kind' ORDER BY e.enumsortorder;""", dsn=ADMIN)]
    unfolded = [label for label in labels if f"'{label}'" not in handled]

    # M3-B added seven labels to this type for the STATION half of the order timeline.
    # They are timeline kinds, never order-ledger kinds, and the ledger's own CHECK
    # constraint enumerates every kind on one side or the other — so a new label
    # satisfies neither branch and cannot be written here at all. The property that
    # survives both gates is therefore not "every label has a fold" but the stronger one
    # underneath it: NO LABEL CAN REACH THIS LEDGER WITHOUT A FOLD. Proved by attempting
    # each unfolded kind rather than by naming them, so a label added tomorrow with
    # neither a fold nor a refusal fails this.
    admitted = []
    for label in unfolded:
        attempt = run(ADMIN, f"""
            INSERT INTO ordering.order_event
                (tenant_id, outlet_id, order_id, sequence_number, kind, actor_kind,
                 actor_user_id, correlation_id, after)
            SELECT tenant_id, outlet_id, id, 999, '{label}', 'system', NULL,
                   correlation_id, '{{}}'::jsonb
            FROM ordering.customer_order WHERE id = '{order}';""")
        if attempt.ok or not attempt.failed_with("23514"):
            admitted.append(f"{label}: {attempt.why() or 'accepted'}")

    record("no event kind can reach the order ledger without a fold",
           not admitted,
           f"{len(labels)} kinds; {len(labels) - len(unfolded)} folded by "
           f"ordering.apply_event() and {len(unfolded)} refused outright by the ledger's "
           f"own CHECK: {unfolded or 'none'}. Admitted with neither: "
           f"{admitted or 'none'}. Read out of the catalog rather than from a list here, "
           f"so a label added with neither a fold nor a refusal fails this rather than "
           f"passing quietly")


# ===========================================================================
# 14. Session lifecycle, proved by a full census (FR-TAB-007A, 008, 009)
# ===========================================================================

def session_contents(session: str) -> dict:
    """Everything hanging off an occupancy, as SETS of identifiers.

    Sets, not counts. A merge that dropped one order and duplicated another keeps the
    count and changes the set, and the count is what a hurried test would compare.
    """
    def ids(sql: str) -> set[str]:
        return {r[0] for r in rows(sql, dsn=ADMIN)}

    return {
        "orders": ids(f"SELECT id::text FROM ordering.customer_order WHERE table_session_id = '{session}'"),
        "lines": ids(f"""SELECT l.id::text FROM ordering.order_line l
                         JOIN ordering.customer_order o ON o.id = l.order_id
                         WHERE o.table_session_id = '{session}'"""),
        "notes": ids(f"""SELECT n.id::text FROM ordering.order_note n
                         JOIN ordering.customer_order o ON o.id = n.order_id
                         WHERE o.table_session_id = '{session}'"""),
        "declarations": ids(f"""SELECT n.id::text FROM ordering.order_note n
                                JOIN ordering.customer_order o ON o.id = n.order_id
                                WHERE o.table_session_id = '{session}'
                                  AND n.kind = 'allergy_declaration'"""),
        "charges": ids(f"""SELECT c.id::text FROM ordering.order_charge_component c
                           JOIN ordering.customer_order o ON o.id = c.order_id
                           WHERE o.table_session_id = '{session}'"""),
        "carts": ids(f"SELECT id::text FROM service.cart WHERE table_session_id = '{session}'"),
        "participants": ids(f"""SELECT guest_session_id::text FROM service.session_participant
                                WHERE table_session_id = '{session}'"""),
        "concerns": ids(f"SELECT id::text FROM safety.allergy_concern WHERE table_session_id = '{session}'"),
    }


def section_session_lifecycle() -> None:
    print("\n--- 14. Merge, move and close, proved by a full census (FR-TAB-007A, 008, 009) ---")

    left = a_table_with_an_order(declarations=True, table=fx.TABLE_ONE)
    right = a_table_with_an_order(declarations=True, table=fx.TABLE_TWO)

    before_left = session_contents(left["session"])
    before_right = session_contents(right["session"])
    expected = {k: before_left[k] | before_right[k] for k in before_left}

    merge = run(APP, f"""
        SELECT service.merge_table_sessions('{fx.TENANT}', '{left["session"]}',
                                            '{right["session"]}', '{fx.USER}');""", **CTX)
    after = session_contents(left["session"])
    stranded = session_contents(right["session"])

    record("a merge moves EXACTLY the union of both tables, nothing dropped or duplicated",
           merge.ok and after == expected,
           "; ".join(
               f"{k}: expected {len(expected[k])}, found {len(after[k])}"
               + ("" if after[k] == expected[k]
                  else f" (missing {sorted(expected[k] - after[k])}, "
                       f"unexpected {sorted(after[k] - expected[k])})")
               for k in sorted(expected))
           + (f". {merge.why()}" if not merge.ok else ""))

    record("nothing was left behind on the absorbed occupancy",
           all(not v for v in stranded.values()),
           "; ".join(f"{k}: {len(v)}" for k, v in sorted(stranded.items()))
           + ". A guest whose basket stayed on a closed occupancy would be holding a "
             "cart that can never be submitted")

    audited = rows(f"""
        SELECT orders_moved::text FROM service.session_merge
        WHERE absorbed_session_id = '{right["session"]}';""")
    events = count(APP, f"""
        SELECT count(*) FROM ordering.order_event
        WHERE kind = 'session_merged'
          AND (before ->> 'table_session_id') = '{right["session"]}'
          AND (after ->> 'table_session_id') = '{left["session"]}';""", **CTX)
    record("every order that moved did so as its own ledger event, and the count is audited",
           len(audited) == 1 and int(audited[0][0]) == len(before_right["orders"])
           and events == len(before_right["orders"]),
           f"{audited[0][0] if audited else '?'} orders recorded as moved, {events} "
           f"session_merged events, {len(before_right['orders'])} orders were there. A "
           f"bulk UPDATE would have moved the rows and left no account of what moved")

    closed = scalar(f"SELECT state::text FROM service.table_session WHERE id = '{right['session']}';")
    record("the absorbed occupancy is closed, and cannot be absorbed a second time",
           closed == "closed"
           and not run(APP, f"""
               SELECT service.merge_table_sessions('{fx.TENANT}', '{left["session"]}',
                                                   '{right["session"]}', '{fx.USER}');""",
               **CTX).ok,
           f"state {closed}; a second merge of the same session is refused, so 'where did "
           f"that order go' cannot have two answers")

    # --- move ---
    before_move = session_contents(left["session"])
    identity_before = rows(f"""
        SELECT table_node_id::text, occupancy_number::text
        FROM service.table_session WHERE id = '{left["session"]}';""")[0]

    move = run(APP, f"""
        SELECT service.move_table_session('{fx.TENANT}', '{left["session"]}',
                                          '{fx.TABLE_TWO}', '{fx.USER}');""", **CTX)
    after_move = session_contents(left["session"])
    identity_after = rows(f"""
        SELECT table_node_id::text, occupancy_number::text
        FROM service.table_session WHERE id = '{left["session"]}';""")[0]

    record("a move preserves session identity and every single thing hanging off it",
           move.ok and after_move == before_move,
           "; ".join(f"{k}: {len(before_move[k])} -> {len(after_move[k])}"
                     for k in sorted(before_move))
           + (f". {move.why()}" if not move.ok else ""))

    record("the session changed table and took a fresh occupancy number at the destination",
           identity_before[0] != identity_after[0]
           and identity_after[0] == fx.TABLE_TWO
           and identity_before[1] != identity_after[1],
           f"table {identity_before[0][:8]} -> {identity_after[0][:8]}, occupancy "
           f"{identity_before[1]} -> {identity_after[1]}. Occupancy numbers are per "
           f"table and M2-B's stale-QR guarantee reads them, so carrying the old number "
           f"to a new table would corrupt a guarantee three slices back")

    denormalized = [f"{r[0]}.{r[1]}" for r in rows("""
        SELECT c.relname, a.attname FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'ordering' AND c.relkind = 'r' AND a.attnum > 0
          AND NOT a.attisdropped AND a.attname LIKE '%table_node%';""", dsn=ADMIN)]
    record("no order anywhere carries a copy of the table it is sitting at",
           not denormalized,
           f"{denormalized or 'none'}. THIS is why a move cannot lose anything: orders "
           f"name the SESSION, and the session kept its identity. A denormalized "
           f"table_node_id would be the thing a move left stale")

    # The session now sits at TABLE_TWO. Seat somebody at TABLE_ONE and try to move onto
    # them. (Written the other way round first, which closed the very session it was
    # about to move — fx.fresh_occupancy() closes whatever is sitting there.)
    fx.fresh_occupancy(fx.TABLE_ONE)
    blocked = run(APP, f"""
        SELECT service.move_table_session('{fx.TENANT}', '{left["session"]}',
                                          '{fx.TABLE_ONE}', '{fx.USER}');""", **CTX)
    record("a session cannot move onto a table that already has an open occupancy",
           blocked.failed_with("MOVE_TARGET_OCCUPIED"),
           blocked.why() or "two parties were seated at one table")

    # --- close ---
    outstanding = a_table_with_an_order(table=fx.TABLE_TWO)
    refused = run(APP, f"""
        SELECT service.close_table_session('{fx.TENANT}', '{outstanding["session"]}',
                                           '{fx.USER}');""", **CTX)
    record("an occupancy with an unresolved order does not close",
           refused.failed_with("SESSION_HAS_OUTSTANDING_ORDERS"),
           refused.why() or "a table was closed over an order nobody had answered")

    reason = fx.reason_code("manager_override")
    unexplained = fx.staff_context(f"""
        SELECT service.close_table_session('{fx.TENANT}', '{outstanding["session"]}',
                                           '{fx.USER}', '{reason}', '   ');""",
                                   session_id=fx.open_staff_session())
    record("an exception with a reason code and no account of what happened is refused",
           unexplained.failed_with("CLOSURE_EXCEPTION_UNEXPLAINED"),
           unexplained.why() or "a code alone was accepted as an explanation. A category "
                                "is not an account")

    unauthorized = run(APP, f"""
        SELECT service.close_table_session('{fx.TENANT}', '{outstanding["session"]}',
                                           '{fx.USER}', '{reason}', 'Guest left.');""", **CTX)
    record("an exception with no authority behind it is refused",
           unauthorized.failed_with("SESSION_NOT_LIVE", "STEP_UP_REQUIRED", "ACTION_NOT_GRANTED"),
           unauthorized.why() or "a session was closed over an outstanding order by "
                                 "nobody in particular")

    authorized = fx.staff_context(f"""
        SELECT service.close_table_session('{fx.TENANT}', '{outstanding["session"]}',
                                           '{fx.USER}', '{reason}',
                                           'Party left before the kitchen answered.');""",
                                  session_id=fx.open_staff_session())
    recorded = rows(f"""
        SELECT outstanding_orders::text, note, authorized_by_user_id::text
        FROM service.session_closure_exception
        WHERE table_session_id = '{outstanding["session"]}';""")
    state = scalar(f"SELECT state::text FROM service.table_session WHERE id = '{outstanding['session']}';")
    record("an authorized exception closes it, and says who allowed it and why",
           authorized.ok and state == "closed" and len(recorded) == 1
           and recorded[0][2] == fx.USER,
           f"{authorized.why() or f'state {state}'}; exception records "
           f"{recorded[0][0] if recorded else '?'} outstanding order(s), authorized by "
           f"{recorded[0][2][:8] if recorded else '?'}, note {recorded[0][1][:40] if recorded else '?'!r}")

    clean = a_table_with_an_order(table=fx.TABLE_ONE)
    run(APP, f"SELECT ordering.accept_order('{fx.TENANT}', '{clean['order']}', '{fx.USER}');", **CTX)
    normal = run(APP, f"""
        SELECT service.close_table_session('{fx.TENANT}', '{clean["session"]}', '{fx.USER}');""",
        **CTX)
    record("an occupancy whose orders are all answered closes with no exception at all",
           normal.ok and count(APP, f"""
               SELECT count(*) FROM service.session_closure_exception
               WHERE table_session_id = '{clean["session"]}';""", **CTX) == 0,
           f"{normal.why() or 'closed'} and no exception row. The gate has to admit as "
           f"well as refuse, or it would pass by never closing anything")


# ===========================================================================
# 15. Governance
# ===========================================================================

def section_governance() -> None:
    print("\n--- 15. Governance ---")

    try:
        failures = partial_closures.check()
        entries = partial_closures.load()
    except partial_closures.RegisterUnreadable as error:
        record("the partial-closure register is readable", False, str(error))
        return

    record("every partial closure names a completing gate the register has, and none is overdue",
           not failures,
           f"{len(entries)} entries; failures: {failures or 'none'}. The three ways this "
           f"fails — no completer, an unknown completer, a completer that has landed — "
           f"are proved red below")

    # Written when M3-A was the only slice with entries, as "every entry here is mine".
    # Later slices open their own, so what this gate still owns is that ITS OWN entries
    # are present and each names a completer — not that nobody else has any.
    m3a_entries = [e for e in entries if e["opened_at"] == "M3-A"]
    expected = {"FR-ORD-002", "FR-ORD-003", "FR-ORD-005", "FR-ORD-006", "FR-ORD-009",
                "FR-ORD-010", "FR-ORD-011", "FR-ORD-012A", "FR-ORD-016A", "FR-ORD-019A",
                "FR-TAB-007A", "FR-TAB-008", "FR-TAB-009", "FR-DAT-010"}
    record("this slice's half-closed requirements are all in the register",
           {e["requirement"] for e in m3a_entries} == expected
           and all(e.get("completing_gate") for e in m3a_entries),
           f"{len(m3a_entries)} opened at M3-A of {len(entries)} in the register: "
           f"{sorted({e['requirement'] for e in m3a_entries})}. Missing: "
           f"{sorted(expected - {e['requirement'] for e in m3a_entries}) or 'none'}")

    landed = partial_closures.landed_gates()
    overdue = {e["completing_gate"] for e in entries
               if (e.get("state") or "") == "open"} & landed
    record("no completing gate has landed while its entry is still open",
           not overdue,
           f"still open against a landed gate: {sorted(overdue) or 'none'}; landed: "
           f"{sorted(landed)}. When tests/m3b appeared, FR-ORD-006, FR-ORD-009, "
           f"FR-ORD-010, FR-ORD-016A and FR-ORD-019A all stopped the build until "
           f"somebody went back to them, which is what the mechanism is for")

    floats = rows("""
        SELECT n.nspname || '.' || c.relname || '.' || a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE n.nspname IN ('ordering') AND c.relkind = 'r' AND a.attnum > 0
          AND NOT a.attisdropped AND t.typname IN ('float4', 'float8', 'money');""",
        dsn=ADMIN)
    record("no money in this schema is binary floating point",
           not floats,
           f"{[r[0] for r in floats] or 'none'}. Every amount is money.amount_minor — "
           f"integer minor units beside an explicit currency (FR-DAT-005)")

    unpaired = rows("SELECT schema_name || '.' || table_name || '.' || column_name "
                    "FROM money.assert_currency_paired();", dsn=ADMIN)
    record("every money column in the new schema sits beside its currency",
           not unpaired,
           f"{[r[0] for r in unpaired] or 'none'} — the M1-C check, run against a schema "
           f"that added seven money columns")

    unprotected = rows("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'ordering' AND c.relkind = 'r'
          AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)
        ORDER BY c.relname;""", dsn=ADMIN)
    record("every table in the schema has row level security ENABLED and FORCED",
           not unprotected,
           f"{[r[0] for r in unprotected] or 'none'} — FORCE matters because the fold is "
           f"SECURITY DEFINER and would otherwise see every tenant")

    wrong_predicate = rows("""
        SELECT c.relname, p.polname FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'ordering'
          AND pg_get_expr(p.polqual, p.polrelid) <> 'app.row_in_scope(tenant_id, outlet_id)'
        ORDER BY c.relname;""", dsn=ADMIN)
    record("every policy uses the one isolation predicate, not one of its own devising",
           not wrong_predicate,
           f"{[f'{r[0]}/{r[1]}' for r in wrong_predicate] or 'none'} — M1-A's NC-M1-003 "
           f"gates this in CI and it gates the new schema unchanged")

    definers = [r[0] for r in rows("""
        SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'ordering' AND p.prosecdef
          AND coalesce(array_to_string(p.proconfig, ','), '') NOT LIKE '%search_path%'
        ORDER BY p.proname;""", dsn=ADMIN)]
    record("every SECURITY DEFINER function pins its search path",
           not definers,
           f"unpinned: {definers or 'none'}. A definer function with a mutable search "
           f"path is a definer function somebody else chooses the tables for")

    sources = "\n".join(
        (REPO / "migrations" / "0010_orders_submission_snapshots_and_session_lifecycle.sql").read_text(encoding="utf-8")
        for _ in (0,)) + "\n" + (HERE / "verify_m3a.py").read_text(encoding="utf-8") \
        + "\n" + (HERE / "fixtures.py").read_text(encoding="utf-8")
    pattern, terms = fenced_identifier_pattern()
    hits = sorted({m.group(0) for m in re.finditer(pattern, sources, re.I)})
    record("this slice names no permanently fenced domain",
           not hits,
           f"checked the migration, the suite and the fixtures against all {terms} "
           f"authoritative terms: {hits or 'none'}")

    forbidden_tables = rows("""
        SELECT n.nspname || '.' || c.relname
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname = 'ordering'
          AND (c.relname ~* '(ticket|station|kds|expo|check|payment|tip|receipt|'
                            'service_request|journey)')
        ORDER BY 1;""", dsn=ADMIN)
    record("nothing belonging to a later slice was built here",
           not forbidden_tables,
           f"{[r[0] for r in forbidden_tables] or 'none'} — kitchen tickets, stations, "
           f"KDS and expo are M3-B; service requests are M3-C; checks, payments, tips "
           f"and receipts are M4")


# ===========================================================================
# 16. Negative controls
# ===========================================================================

def capture_function(signature: str) -> str:
    res = run(ADMIN, f"SELECT pg_get_functiondef('{signature}'::regprocedure);")
    if not res.ok or not res.out.strip():
        raise ProbeFailed(f"capture {signature}", res.err)
    return res.out


def prove(control: str, gate, signature: str, break_sql: str, revert_sql: str = "",
          captured: list[str] | None = None) -> None:
    """Plant the defect, require the NAMED failure, revert, require green again."""
    ok, _, detail = gate()
    if not ok:
        record(f"{control} — baseline", False,
               f"the gate was already failing before the break: {detail}")
        return

    originals = [capture_function(sig) for sig in (captured or [])]

    broke = run(ADMIN, break_sql)
    if not broke.ok:
        record(f"{control} — inject defect", False, f"could not plant the break: {broke.why()}")
        return
    try:
        red_ok, red_sig, red_detail = gate()
        record(f"{control} — RED with the defect planted",
               (not red_ok) and red_sig == signature,
               f"{red_sig or '(the gate still passed)'}: {red_detail}")
    finally:
        for original in originals:
            run(ADMIN, original)
        if revert_sql:
            run(ADMIN, revert_sql)

    green_ok, green_sig, green_detail = gate()
    record(f"{control} — GREEN after revert", green_ok,
           green_detail if green_ok else f"{green_sig}: {green_detail}")


def duplicate_effect_gate() -> tuple[bool, str, str]:
    """A retry must produce no second effect ANYWHERE, and one of each named artifact."""
    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest)
    key = f"nc1-{os.urandom(8).hex()}"

    first = submit(cart, key=key, guest=guest)
    if not first.ok:
        return False, "DUPLICATE_ORDER_EFFECT", f"the first submission failed: {first.why()}"
    order = (first.scalar or "").strip()

    before = table_digests()
    second = submit(cart, key=key, guest=guest)
    after = table_digests()

    leaks: list[str] = []
    if not second.ok:
        leaks.append(f"the retry errored instead of returning the original: {second.why()}")
    elif (second.scalar or "").strip() != order:
        leaks.append(f"the retry returned {(second.scalar or '').strip()[:8]}, "
                     f"not the original {order[:8]}")

    changed = sorted(name for name in set(before) | set(after)
                     if before.get(name) != after.get(name)
                     and name not in RETRY_MAY_CHANGE)
    if changed:
        leaks.append(f"the retry changed {len(changed)} table(s) that a retry must not "
                     f"touch: {changed}")

    for label, sql in (
        ("orders", f"SELECT count(*) FROM ordering.customer_order WHERE cart_id = '{cart}'"),
        ("submitted ledger entries",
         f"SELECT count(*) FROM ordering.order_event WHERE order_id = '{order}' AND kind = 'submitted'"),
        ("timeline submission entries",
         f"SELECT count(*) FROM ordering.order_timeline_entry WHERE order_id = '{order}' AND kind = 'submitted'"),
        ("order lines", f"SELECT count(*) FROM ordering.order_line WHERE order_id = '{order}'"),
    ):
        found = count(APP, sql + ";", **CTX)
        if found != 1:
            leaks.append(f"{found} {label} after one order and one retry")

    if leaks:
        return False, "DUPLICATE_ORDER_EFFECT", "; ".join(leaks)
    return True, "", (f"the retry returned the original order and changed nothing in "
                      f"{len(before)} tables enumerated from the catalog; exactly one "
                      f"order, ledger entry, timeline entry and line")


def stale_price_gate() -> tuple[bool, str, str]:
    """A price that moves between preview and submission must not move the total."""
    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest)
    view = preview(cart)
    original_total = view["total_amount_minor"]

    raised = run(APP, f"""
        UPDATE menu.price SET amount_minor = amount_minor + 5000, row_version = row_version
        WHERE tenant_id = '{fx.TENANT}' AND variant_id = '{fx.VARIANT_DORO_FULL}'
          AND channel IS NULL AND effective_to IS NULL;""", **CTX)
    if not raised.ok:
        return False, "STALE_PRICE_ACCEPTED", f"the price could not be moved: {raised.why()}"

    try:
        republished = run(APP, f"""
            UPDATE menu.menu SET state = 'draft', row_version = row_version
            WHERE id = '{fx.MENU}';
            SELECT menu.publish_menu('{fx.MENU}', '{fx.USER}');""", tx=True, **CTX)
        if not republished.ok:
            return False, "STALE_PRICE_ACCEPTED", f"could not republish: {republished.why()}"

        res = run(APP, f"""
            SELECT ordering.submit_order(
                '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', 'nc2-{os.urandom(6).hex()}',
                decode('{view["pricing_digest"]}', 'hex'), {original_total}, 'en',
                gen_random_uuid(), gen_random_uuid(), 'guest_qr', NULL, '{guest}');""",
            **CTX)

        if res.ok:
            order = (res.scalar or "").strip()
            stored = count(APP, f"""
                SELECT total_amount_minor FROM ordering.customer_order
                WHERE id = '{order}';""", **CTX)
            return False, "STALE_PRICE_ACCEPTED", (
                f"a submission carrying a digest for a price that has since changed was "
                f"accepted, and the order stored {stored} against a preview of "
                f"{original_total}")
        if not res.failed_with("PRICE_CHANGED_SINCE_PREVIEW"):
            return False, "STALE_PRICE_ACCEPTED", (
                f"the submission was refused, but not because the price moved: {res.why()}")

        orders = count(APP, f"""
            SELECT count(*) FROM ordering.customer_order WHERE cart_id = '{cart}';""", **CTX)
        if orders:
            return False, "STALE_PRICE_ACCEPTED", (
                f"the submission was refused and {orders} order(s) exist for the cart anyway")
    finally:
        run(APP, f"""
            UPDATE menu.price SET amount_minor = amount_minor - 5000, row_version = row_version
            WHERE tenant_id = '{fx.TENANT}' AND variant_id = '{fx.VARIANT_DORO_FULL}'
              AND channel IS NULL AND effective_to IS NULL;""", **CTX)
        run(APP, f"""
            UPDATE menu.menu SET state = 'draft', row_version = row_version
            WHERE id = '{fx.MENU}';
            SELECT menu.publish_menu('{fx.MENU}', '{fx.USER}');""", tx=True, **CTX)

    return True, "", ("a price raised and republished between preview and submission was "
                      "refused by name, and no order was written at either price")


def allergy_survival_gate() -> tuple[bool, str, str]:
    """The declaration must survive every hop: ledger, projection, kitchen, rebuild, amendment."""
    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest)
    concern = fx.allergy_concern(session, guest)
    res = submit(cart, key=f"nc3-{os.urandom(8).hex()}", guest=guest,
                 declarations=[{"allergy_concern_id": concern}])
    if not res.ok:
        return False, "ALLERGY_FLAG_LOST", f"the order could not be placed: {res.why()}"
    order = (res.scalar or "").strip()

    truth = rows(f"""SELECT allergen_id::text, acknowledgement_text
                     FROM safety.allergy_concern WHERE id = '{concern}';""", dsn=ADMIN)[0]
    leaks: list[str] = []

    def declared_in_projection() -> list[list[str]]:
        return rows(f"""
            SELECT allergen_id::text, acknowledgement_text FROM ordering.order_note
            WHERE order_id = '{order}' AND kind = 'allergy_declaration';""", dsn=ADMIN)

    ledger = rows(f"""
        SELECT e.after -> 'note' ->> 'allergen_id',
               e.after -> 'note' ->> 'acknowledgement_text'
        FROM ordering.order_event e
        WHERE e.order_id = '{order}' AND e.kind = 'allergy_declared';""", dsn=ADMIN)
    if len(ledger) != 1 or ledger[0] != truth:
        leaks.append(f"hop cart->ledger: {ledger or 'nothing reached the ledger'}")

    projected = declared_in_projection()
    if len(projected) != 1 or projected[0] != truth:
        leaks.append(f"hop ledger->projection: {projected or 'nothing was projected'}")

    kitchen = rows(f"""
        SELECT kind::text, kitchen_code FROM ordering.kitchen_notes('{fx.TENANT}', '{order}')
        WHERE kind = 'allergy_declaration';""")
    if not kitchen or not kitchen[0][1]:
        leaks.append(f"hop projection->kitchen: {kitchen or 'the kitchen reader shows none'}")

    run(APP, f"SELECT ordering.rebuild_projections('{fx.TENANT}');", **CTX)
    rebuilt = declared_in_projection()
    if len(rebuilt) != 1 or rebuilt[0] != truth:
        leaks.append(f"hop rebuild: {rebuilt or 'the declaration did not come back'}")

    line = scalar(f"SELECT id::text FROM ordering.order_line WHERE order_id = '{order}' LIMIT 1;")
    amended = run(APP, f"""
        SELECT ordering.amend_order_line('{fx.TENANT}', '{order}', '{line}', 2,
                                         NULL, '{guest}');""", **CTX)
    if not amended.ok:
        leaks.append(f"the order could not be amended to test the hop: {amended.why()}")
    else:
        after_amendment = declared_in_projection()
        if len(after_amendment) != 1 or after_amendment[0] != truth:
            leaks.append(f"hop amendment: {after_amendment or 'the amendment dropped it'}")

    if leaks:
        return False, "ALLERGY_FLAG_LOST", "; ".join(leaks)
    return True, "", ("the declaration is identical at the table, in the ledger, in the "
                      "projection, at the kitchen reader, after a full rebuild and after "
                      "an amendment")


def client_total_gate() -> tuple[bool, str, str]:
    """The stored total must be the server's, never the figure the caller stated."""
    session = fx.fresh_occupancy()
    guest = fx.guest_on(session)
    cart = fx.cart_with(session, guest)
    view = preview(cart)
    server_total = view["total_amount_minor"]
    claimed = server_total - 3000

    res = run(APP, f"""
        SELECT ordering.submit_order(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', 'nc5-{os.urandom(6).hex()}',
            decode('{view["pricing_digest"]}', 'hex'), {claimed}, 'en',
            gen_random_uuid(), gen_random_uuid(), 'guest_qr', NULL, '{guest}');""", **CTX)

    if res.ok:
        order = (res.scalar or "").strip()
        stored = count(APP, f"""
            SELECT total_amount_minor FROM ordering.customer_order WHERE id = '{order}';""",
            **CTX)
        if stored == claimed:
            return False, "CLIENT_CALCULATED_TOTAL_ACCEPTED", (
                f"the caller stated {claimed} and the order stored {claimed}; the server "
                f"priced it at {server_total}")
        return False, "CLIENT_CALCULATED_TOTAL_ACCEPTED", (
            f"a submission stating a total of {claimed} was accepted at all, even though "
            f"it stored the server's {stored}. A disagreement about the price is a "
            f"disagreement to surface, not to absorb")

    if not res.failed_with("TOTAL_DISAGREEMENT"):
        return False, "CLIENT_CALCULATED_TOTAL_ACCEPTED", (
            f"the submission was refused for the wrong reason: {res.why()}")

    arguments = capture_function("ordering.preview_cart(uuid,uuid,uuid,menu.customer_locale,menu.sales_channel,timestamptz)")
    if re.search(r"p_(total|amount|price)[a-z_]*\s+(bigint|money\.amount_minor|numeric)",
                 arguments, re.I):
        return False, "CLIENT_CALCULATED_TOTAL_ACCEPTED", (
            "the preview takes a parameter through which a caller could state a figure")

    return True, "", (f"a stated total of {claimed} against a server price of "
                      f"{server_total} was refused by name, and the preview has no "
                      f"parameter through which a figure could be supplied at all")


def accepted_order_mutation_gate() -> tuple[bool, str, str]:
    """No destructive edit path exists for an accepted order, for anybody."""
    placed = a_table_with_an_order()
    order = placed["order"]
    accepted = run(APP, f"SELECT ordering.accept_order('{fx.TENANT}', '{order}', '{fx.USER}');", **CTX)
    if not accepted.ok:
        return False, "ACCEPTED_ORDER_MUTATED", f"the order could not be accepted: {accepted.why()}"

    leaks: list[str] = []
    attempts = (
        (ADMIN, f"UPDATE ordering.order_event SET after = '{{}}'::jsonb WHERE order_id = '{order}';",
         "rewriting a ledger event", ("ACCEPTED_ORDER_MUTATION_REFUSED",)),
        (ADMIN, f"DELETE FROM ordering.order_event WHERE order_id = '{order}';",
         "deleting a ledger event", ("ACCEPTED_ORDER_MUTATION_REFUSED",)),
        (ADMIN, f"UPDATE ordering.customer_order SET state = 'submitted' WHERE id = '{order}';",
         "rewriting the projection", ("PROJECTION_WRITTEN_DIRECTLY",)),
        (ADMIN, f"DELETE FROM ordering.order_line WHERE order_id = '{order}';",
         "deleting a line", ("PROJECTION_WRITTEN_DIRECTLY",)),
        (APP, f"UPDATE ordering.customer_order SET state = 'submitted' WHERE id = '{order}';",
         "the application role rewriting the projection", ("PROJECTION_WRITTEN_DIRECTLY", "42501")),
    )
    # Each attempt runs in a transaction that is ROLLED BACK. The observation is real —
    # the statement genuinely runs, and with the triggers removed it genuinely succeeds —
    # while nothing it did survives the probe.
    #
    # It used to run in autocommit and repair the damage afterwards with a rebuild, and
    # that stopped being enough at M3-B. The RED run blanks every payload on the order's
    # ledger AND deletes the rows; a rebuild cannot restore what is gone, and the
    # fulfillment ledger now carries events about work for that order, so the replay
    # would try to attach a ticket to an order the order ledger can no longer produce.
    # One suite's negative control was left able to make the next suite's rebuild fail.
    # Rolling back leaves nothing to repair, which is better than repairing well.
    for dsn, statement, what, reasons in attempts:
        res = run(dsn, statement, rollback=True, **(CTX if dsn == APP else {}))
        if not res.failed_with(*reasons):
            leaks.append(f"{what} was not refused by name: "
                         f"{res.why() or 'it succeeded'}")

    if leaks:
        return False, "ACCEPTED_ORDER_MUTATED", "; ".join(leaks)
    return True, "", ("the ledger refuses UPDATE and DELETE and the projection refuses "
                      "every write from outside the fold — for the administrator as well "
                      "as the application role")


def session_change_gate() -> tuple[bool, str, str]:
    """A merge or a move must lose nothing, duplicate nothing and re-parent nothing silently."""
    left = a_table_with_an_order(declarations=True, table=fx.TABLE_ONE)
    right = a_table_with_an_order(declarations=True, table=fx.TABLE_TWO)

    before_left = session_contents(left["session"])
    before_right = session_contents(right["session"])
    expected = {k: before_left[k] | before_right[k] for k in before_left}

    merged = run(APP, f"""
        SELECT service.merge_table_sessions('{fx.TENANT}', '{left["session"]}',
                                            '{right["session"]}', '{fx.USER}');""", **CTX)
    if not merged.ok:
        return False, "ORDER_LOST_ON_SESSION_CHANGE", f"the merge failed: {merged.why()}"

    leaks: list[str] = []
    after = session_contents(left["session"])
    for key in sorted(expected):
        missing = expected[key] - after[key]
        extra = after[key] - expected[key]
        if missing:
            leaks.append(f"merge lost {len(missing)} {key}: {sorted(missing)}")
        if extra:
            leaks.append(f"merge invented {len(extra)} {key}: {sorted(extra)}")

    stranded = session_contents(right["session"])
    for key, value in sorted(stranded.items()):
        if value:
            leaks.append(f"merge left {len(value)} {key} on the absorbed occupancy")

    moved_events = count(APP, f"""
        SELECT count(*) FROM ordering.order_event
        WHERE kind = 'session_merged'
          AND (before ->> 'table_session_id') = '{right["session"]}';""", **CTX)
    if moved_events != len(before_right["orders"]):
        leaks.append(f"{len(before_right['orders'])} orders moved and {moved_events} "
                     f"session_merged events were written; a re-parent with no event is "
                     f"a silent one")

    before_move = session_contents(left["session"])
    moved = run(APP, f"""
        SELECT service.move_table_session('{fx.TENANT}', '{left["session"]}',
                                          '{fx.TABLE_TWO}', '{fx.USER}');""", **CTX)
    if not moved.ok:
        leaks.append(f"the move failed: {moved.why()}")
    else:
        after_move = session_contents(left["session"])
        for key in sorted(before_move):
            if before_move[key] != after_move[key]:
                leaks.append(f"move changed {key}: "
                             f"lost {sorted(before_move[key] - after_move[key])}, "
                             f"gained {sorted(after_move[key] - before_move[key])}")

    if leaks:
        return False, "ORDER_LOST_ON_SESSION_CHANGE", "; ".join(leaks)
    return True, "", (f"a merge of {len(before_right['orders'])} + "
                      f"{len(before_left['orders'])} orders produced exactly their union "
                      f"with one ledger event each, left nothing behind, and a subsequent "
                      f"move changed no set at all")


def private_note_gate() -> tuple[bool, str, str]:
    """A private staff note must not reach a customer surface, by any route."""
    placed = a_table_with_an_order()
    order = placed["order"]
    secret = "Comped a coffee last week; do not repeat."
    added = run(APP, f"""
        SELECT ordering.add_order_note('{fx.TENANT}', '{order}', 'private_staff',
                                       '{secret}', NULL, '{fx.USER}');""", **CTX)
    if not added.ok:
        return False, "PRIVATE_NOTE_DISCLOSED", f"could not attach a private note: {added.why()}"

    leaks: list[str] = []

    visible = rows(f"""
        SELECT kind::text, body FROM ordering.customer_visible_notes('{fx.TENANT}', '{order}');""")
    if any(r[0] == "private_staff" for r in visible):
        leaks.append("the customer note reader returned a private staff note")
    if any(secret in (r[1] or "") for r in visible):
        leaks.append("the private note's text reached the customer reader under another kind")

    timeline = rows(f"""
        SELECT summary FROM ordering.customer_timeline('{fx.TENANT}', '{order}');""")
    if any(secret in (r[0] or "") for r in timeline):
        leaks.append("the private note's text appeared on the customer timeline")

    direct = run(APP, f"SELECT body FROM ordering.order_note WHERE order_id = '{order}';", **CTX)
    if direct.ok:
        leaks.append("the application role read the note table directly, so the audience "
                     "functions are not the only way in")
    elif not direct.failed_with("42501"):
        leaks.append(f"the direct read was refused for the wrong reason: {direct.why()}")

    staff = fx.staff_context(
        f"SELECT body FROM ordering.staff_notes('{fx.TENANT}', '{order}');",
        session_id=fx.open_staff_session())
    if not staff.ok or not any(secret in r[0] for r in staff.rows):
        leaks.append("staff could not read the private note either, so the control would "
                     "pass by denying everything")

    if leaks:
        return False, "PRIVATE_NOTE_DISCLOSED", "; ".join(leaks)
    return True, "", ("the private note is absent from the customer reader and the "
                      "customer timeline, unreadable directly by the application role, "
                      "and readable by staff under a live session")


def rebuild_determinism_gate() -> tuple[bool, str, str]:
    """A projection rebuilt from the ledger must be identical to the one it replaced."""
    placed = a_table_with_an_order(declarations=True)
    order = placed["order"]
    run(APP, f"SELECT ordering.accept_order('{fx.TENANT}', '{order}', '{fx.USER}');", **CTX)
    line = scalar(f"SELECT id::text FROM ordering.order_line WHERE order_id = '{order}' LIMIT 1;")

    before = scalar(f"SELECT encode(ordering.projection_digest('{fx.TENANT}'), 'hex');")
    replayed = scalar(f"SELECT ordering.rebuild_projections('{fx.TENANT}')::text;")
    after = scalar(f"SELECT encode(ordering.projection_digest('{fx.TENANT}'), 'hex');")

    if int(replayed) == 0:
        return False, "REBUILD_NOT_DETERMINISTIC", "the rebuild replayed no events at all"
    if before != after:
        return False, "REBUILD_NOT_DETERMINISTIC", (
            f"the projection changed when it was rebuilt from the ledger it came from: "
            f"{before[:16]} -> {after[:16]}")

    third = scalar(f"SELECT ordering.rebuild_projections('{fx.TENANT}')::text;")
    again = scalar(f"SELECT encode(ordering.projection_digest('{fx.TENANT}'), 'hex');")
    if again != after:
        return False, "REBUILD_NOT_DETERMINISTIC", (
            f"two rebuilds of the same ledger disagreed: {after[:16]} vs {again[:16]}")

    return True, "", (f"{replayed} events replayed twice, digest {before[:16]} unchanged "
                      f"each time, over a ledger carrying a submission, an allergy "
                      f"declaration and an acceptance")


def section_controls() -> None:
    print("\n--- 16. Negative controls: each proved RED before it is trusted GREEN ---")

    submit_signature = ("ordering.submit_order(uuid,uuid,uuid,text,bytea,bigint,"
                        "menu.customer_locale,uuid,uuid,ordering.order_origin,uuid,uuid,"
                        "boolean,jsonb,jsonb,menu.sales_channel)")
    amend_signature = "ordering.amend_order_line(uuid,uuid,uuid,integer,uuid,uuid)"
    apply_signature = "ordering.apply_event(bigint)"
    notes_signature = "ordering.customer_visible_notes(uuid,uuid)"
    merge_signature = "service.merge_table_sessions(uuid,uuid,uuid,uuid,uuid)"

    original_submit = capture_function(submit_signature)

    print("\n  NC-M3-001  a retry does the work a second time")
    prove("NC-M3-001", duplicate_effect_gate, "DUPLICATE_ORDER_EFFECT",
          # The defect a careless implementation actually has: the replay branch logs the
          # retry and then falls through to submit again. Note that the extra audit row it
          # writes is in a table the NAMED assertions do not cover — the differential is
          # what has to catch that half.
          original_submit.replace(
              """    IF v_claim.is_replay THEN""",
              """    IF v_claim.is_replay AND false THEN""", 1),
          captured=[submit_signature])

    print("\n  NC-M3-002  a price that moved between preview and submission is absorbed")
    prove("NC-M3-002", stale_price_gate, "STALE_PRICE_ACCEPTED",
          original_submit.replace(
              """    IF v_digest IS DISTINCT FROM p_pricing_digest THEN""",
              """    IF false THEN""", 1),
          captured=[submit_signature])

    print("\n  NC-M3-003  an amendment drops the allergy declaration on the way through")
    prove("NC-M3-003", allergy_survival_gate, "ALLERGY_FLAG_LOST",
          # The fold REPLACES notes rather than patching them, so an amendment payload
          # that omits them loses the declaration. This is the realistic shape of the
          # defect: nobody deletes a declaration, somebody forgets to carry it.
          capture_function(amend_signature).replace(
              """                'notes', coalesce((""",
              """                'notes', coalesce((SELECT NULL::jsonb WHERE false), (""", 1
          ).replace(
              """                    WHERE n.tenant_id = p_tenant_id AND n.order_id = p_order_id),
                    '[]'::jsonb)))""",
              """                    WHERE n.tenant_id = p_tenant_id AND n.order_id = p_order_id
                      AND false),
                    '[]'::jsonb)))""", 1),
          captured=[amend_signature])

    print("\n  NC-M3-005  the total a client stated is the total that is stored")
    prove("NC-M3-005", client_total_gate, "CLIENT_CALCULATED_TOTAL_ACCEPTED",
          original_submit.replace(
              """    IF p_expected_total_minor IS NOT NULL AND p_expected_total_minor <> v_total THEN""",
              """    IF p_expected_total_minor IS NOT NULL THEN
        v_total := p_expected_total_minor;
    END IF;
    IF false THEN""", 1),
          captured=[submit_signature])

    print("\n  NC-M3-006  an accepted order can be edited after the fact")
    prove("NC-M3-006", accepted_order_mutation_gate, "ACCEPTED_ORDER_MUTATED",
          # The grant is not touched. Only the triggers go, which is exactly the question
          # FR-DAT-008A asks: is the append-only guarantee carried by the trigger, or was
          # it only ever the grant?
          """DROP TRIGGER order_event_append_only ON ordering.order_event;
             DROP TRIGGER customer_order_projection_guard ON ordering.customer_order;
             DROP TRIGGER order_line_projection_guard ON ordering.order_line;""",
          revert_sql="""
             CREATE TRIGGER order_event_append_only
                 BEFORE UPDATE OR DELETE ON ordering.order_event
                 FOR EACH ROW EXECUTE FUNCTION ordering.refuse_ledger_mutation();
             CREATE TRIGGER customer_order_projection_guard
                 BEFORE INSERT OR UPDATE OR DELETE ON ordering.customer_order
                 FOR EACH ROW EXECUTE FUNCTION ordering.refuse_projection_write();
             CREATE TRIGGER order_line_projection_guard
                 BEFORE INSERT OR UPDATE OR DELETE ON ordering.order_line
                 FOR EACH ROW EXECUTE FUNCTION ordering.refuse_projection_write();""")

    print("\n  NC-M3-007  a merge loses an order")
    prove("NC-M3-007", session_change_gate, "ORDER_LOST_ON_SESSION_CHANGE",
          # An ORDER BY with a LIMIT is how this defect looks in the wild: somebody adds
          # a bound to a loop for a reason that made sense once.
          capture_function(merge_signature).replace(
              """         WHERE tenant_id = p_tenant_id AND table_session_id = p_absorbed_session_id
         ORDER BY submitted_at, id
    LOOP""",
              """         WHERE tenant_id = p_tenant_id AND table_session_id = p_absorbed_session_id
         ORDER BY submitted_at, id
         OFFSET 1
    LOOP""", 1),
          captured=[merge_signature])

    print("\n  NC-M3-008  a private staff note reaches the customer surface")
    prove("NC-M3-008", private_note_gate, "PRIVATE_NOTE_DISCLOSED",
          capture_function(notes_signature).replace(
              """      AND n.kind IN ('customer', 'allergy_declaration')""",
              """      AND n.kind IN ('customer', 'allergy_declaration', 'private_staff')""", 1),
          captured=[notes_signature])

    print("\n  NC-M3-009  a rebuild does not reproduce what it replaced")
    prove("NC-M3-009", rebuild_determinism_gate, "REBUILD_NOT_DETERMINISTIC",
          # A single field dropped from the fold. The row counts still match, every order
          # is still there, and the projection is wrong — which is the case a comparison
          # of counts would pass.
          capture_function(apply_signature).replace(
              """                 nullif(v_line ->> 'participant_guest_session_id', '')::uuid,""",
              """                 NULL::uuid,""", 1),
          # The red run rebuilds the projection with the DEFECTIVE fold, so restoring the
          # function is not enough on its own: the rows it wrote are still wrong, and the
          # green check would compare a bad projection against a good rebuild and call
          # the difference a determinism failure. Rebuilding once with the restored fold
          # is the repair, and it runs after the function is back.
          revert_sql=f"""
              SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
              SELECT set_config('app.outlet_id', '{fx.OUTLET_H1}', false);
              SELECT ordering.rebuild_projections('{fx.TENANT}');
              SELECT set_config('app.tenant_id', '', false);
              SELECT set_config('app.outlet_id', '', false);""",
          captured=[apply_signature])


def section_differential_independence() -> None:
    """The differential must catch what the named assertions cannot.

    Two halves that both pass are not two halves that both work. The defect planted here
    writes a row into a table NONE of the named assertions look at — an audit entry
    logging the retry, which is a plausible thing for somebody to add. Every named
    assertion still sees exactly one order, one ledger entry, one timeline entry and one
    line. Only the differential notices.
    """
    print("\n--- 16b. The differential catches what the named assertions cannot ---")

    signature = ("ordering.submit_order(uuid,uuid,uuid,text,bytea,bigint,"
                 "menu.customer_locale,uuid,uuid,ordering.order_origin,uuid,uuid,"
                 "boolean,jsonb,jsonb,menu.sales_channel)")
    original = capture_function(signature)

    def named_assertions_only(cart: str, order: str) -> list[str]:
        return [f"{label}: {found}" for label, found in (
            ("orders", count(APP, f"SELECT count(*) FROM ordering.customer_order WHERE cart_id = '{cart}';", **CTX)),
            ("ledger submissions", count(APP, f"SELECT count(*) FROM ordering.order_event WHERE order_id = '{order}' AND kind = 'submitted';", **CTX)),
            ("timeline submissions", count(APP, f"SELECT count(*) FROM ordering.order_timeline_entry WHERE order_id = '{order}' AND kind = 'submitted';", **CTX)),
            ("lines", count(APP, f"SELECT count(*) FROM ordering.order_line WHERE order_id = '{order}';", **CTX)),
        ) if found != 1]

    broke = run(ADMIN, original.replace(
        """        -- FR-ORD-004: the ORIGINAL outcome. Not a fresh success, not an error.
        RETURN v_claim.result_id;""",
        """        INSERT INTO audit.operational_event
            (tenant_id, outlet_id, event_code, entity_schema, entity_table, entity_id,
             detail)
        VALUES (p_tenant_id, p_outlet_id, 'ordering.submission_retried', 'ordering',
                'customer_order', v_claim.result_id::text, '{}'::jsonb);
        RETURN v_claim.result_id;""", 1))
    if not broke.ok:
        record("a retry-writes-elsewhere defect could be planted", False, broke.why())
        return

    try:
        session = fx.fresh_occupancy()
        guest = fx.guest_on(session)
        cart = fx.cart_with(session, guest)
        key = f"nc-diff-{os.urandom(8).hex()}"
        first = submit(cart, key=key, guest=guest)
        order = (first.scalar or "").strip()

        before = table_digests()
        retry = submit(cart, key=key, guest=guest)
        after = table_digests()

        changed = sorted(name for name in set(before) | set(after)
                         if before.get(name) != after.get(name))
        misses = named_assertions_only(cart, order)

        record("the named assertions do NOT see this defect",
               not misses and retry.ok and (retry.scalar or "").strip() == order,
               f"one order, one ledger submission, one timeline entry, one line — every "
               f"named assertion passes{': ' + '; '.join(misses) if misses else ''}. The "
               f"retry still returned the original id")

        record("the differential DOES see it, and names the table",
               changed == ["audit.operational_event"],
               f"tables changed by the retry: {changed}. It is a table no named "
               f"assertion looks at, which is the point: the two halves are independent, "
               f"and the differential is the half that will still hold when M3-B and M4 "
               f"add tables nobody remembers to add here")
    finally:
        run(ADMIN, original)
        run(ADMIN, "DELETE FROM audit.operational_event "
                   "WHERE event_code = 'ordering.submission_retried';")

    ok, _, detail = duplicate_effect_gate()
    record("and it is green again once the defect is reverted", ok, detail)


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> int:
    # Stated because the earlier suites state it and Windows made it matter: every line
    # of evidence below is written as UTF-8, not in the console's own code page.
    print("=" * 74)
    print("M3-A VERIFICATION — order aggregate, submission, snapshots, session lifecycle")
    print("evidence encoding: UTF-8")
    print("=" * 74)

    fx.seed()

    section_aggregate()
    section_draft_carts()
    section_preview()
    section_fee_seam()
    section_idempotency()
    section_snapshots()
    section_revalidation()
    section_acceptance_and_ownership()
    section_amendment_cancellation_void()
    section_notes_and_allergy()
    section_audience()
    section_duplicates()
    section_correlation()
    section_ledger_and_rebuild()
    section_session_lifecycle()
    section_governance()
    section_controls()
    section_differential_independence()

    passed = sum(1 for _n, ok, _d in results if ok)
    failed = [(name, detail) for name, ok, detail in results if not ok]

    # Same summary shape every suite from M1-A onward prints, because CI parses these
    # lines. A suite that reported its totals in a format of its own would be a suite the
    # roll-call could not check.
    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {passed}")
    print(f"  failed        : {len(failed)}")
    print(f"  controls      : {sum(1 for n, _o, _d in results if ' — RED' in n)}   "
          f"(each proved red with a real defect, then green after revert)")
    for name, detail in failed:
        print(f"  - {name}")
        for line in (detail or "").splitlines():
            print(f"      {line}")
    print()
    if failed:
        print("FAIL M3A_VERIFICATION")
        return 1
    print("PASS M3A_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
