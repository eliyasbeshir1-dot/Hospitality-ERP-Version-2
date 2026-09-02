#!/usr/bin/env python3
"""M3-D verification: the waiter surface, staff UX, terminals, override and handover.

Three things make this suite different from the ones before it.

THE CENTRAL CLAIM IS A NEGATIVE ONE. FR-POS-003A says a waiter-entered order obeys the
IDENTICAL rules as a QR order and rejects "two implementations that agree today". A
matrix that ran both channels and compared outcomes would prove agreement on the cases it
happened to try, which is exactly the thing the requirement refuses to accept. So the
proof has two independent halves: a STRUCTURAL one, derived from the catalog, that makes
a second implementation impossible rather than merely absent; and a BEHAVIOURAL one that
compares refusal CODES, not just outcomes, because two channels refusing for different
reasons are not identical.

THE OVERRIDE IS PROVED BY CONSTRUCTION, NOT BY POLICY. identity.step_up_grant names a
SESSION and no user, so who authorized something is only ever reachable by following the
session. A manager who authenticates into a waiter's terminal therefore produces a grant
on the WAITER's session, and the derived approver comes back as the waiter. The control
plants exactly that — the real thing a busy floor manager does — rather than a missing
field.

FRICTION IS MEASURED BY DOING IT. FR-UX-015's grading is a claim about what a person has
to do, so the probe presses the buttons: a routine action runs with no panel, a
deliberate one opens a panel, shows a reason field, and refuses while it is empty.

Every check records whether its evidence is MEASURED — read out of Chromium's own layout
— or ASSERTED, meaning read from source, from a payload, or from the database. The split
printed at the end is derived from what actually ran.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
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
    OPERATIONS, RULE_FUNCTION_QUERY, RULE_SCHEMAS,
    handler_block, named_rules, rules_by_surface, strip_comments)
from fenced import fenced_identifier_pattern                     # noqa: E402
from pg import CommandUnreadable, ProbeFailed, count, run        # noqa: E402
from service import Service, WORKSPACE, patch_workspace, sync_and_build   # noqa: E402

import partial_closures                                          # noqa: E402

assert fx.__file__ == str(HERE / "fixtures.py"), f"wrong fixtures module: {fx.__file__}"

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]
CTX = dict(tenant=fx.TENANT, outlet=fx.OUTLET_H1)

results: list[tuple[str, bool, str, str]] = []
CONTEXT: dict = {}

# Run-unique keys, for the reason M3-C learned the hard way: an idempotency key written
# as a literal is the same claim in every run, so a second run against a database the
# first one touched is refused — correctly — and the suite is what is wrong.
RUN_NONCE = os.urandom(6).hex()


def idem(label: str) -> str:
    return f"m3d-{label}-{RUN_NONCE}"


def as_session(session_id: str, sql: str):
    """Run SQL with app.session_id set, and read the ANSWER rather than the context.

    set_config() returns a row of its own, and pg.Result.scalar is rows[0][0] — the
    FIRST row. So reading .scalar after "set the session; do the thing" gives the session
    id back, not the thing's result. Every override probe here did exactly that once and
    passed on a value that was never an override id, while the row it should have
    examined sat in the table unexamined. last_value() reads the last row instead.
    """
    return run(APP, "SELECT set_config('app.session_id', '" + session_id
               + "', false);\n" + sql, tx=True, **CTX)


def last_value(res) -> str:
    return (res.rows[-1][0] if res.rows and res.rows[-1] else "").strip()


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    """`evidence` is 'measured' when the fact came out of a real browser's layout."""
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
    """A function's whole source. NOT scalar(): that returns the first line only."""
    res = run(ADMIN, f"SELECT pg_get_functiondef('{signature}'::regprocedure);")
    if not res.ok or not res.out.strip():
        raise ProbeFailed(f"definition of {signature}", res.err)
    return res.out


def signature(error: str) -> str:
    matched = re.search(r"\b([A-Z][A-Z_]{4,})\b", error or "")
    return matched.group(1) if matched else ""


# ===========================================================================
# HTTP, as the two surfaces reach it
# ===========================================================================

def call(method: str, path: str, token: str, body: dict | None = None,
         key: str | None = None) -> dict:
    """One request, returning the parsed body and the status, never raising on a refusal.

    A refusal IS the evidence in most of this suite — the channel matrix compares the
    reason codes two surfaces give for the same illegal thing — so an exception here
    would throw away the fact being measured.
    """
    url = f"{CONTEXT['base_url']}{path}"
    headers = {"authorization": f"Bearer {token}"}
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


def guest_call(method: str, path: str, token: str, body: dict | None = None,
               key: str | None = None) -> dict:
    url = f"{CONTEXT['base_url']}{path}"
    headers = {"authorization": f"Guest {token}"}
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


# ===========================================================================
# 1. Terminals (FR-POS-001)
# ===========================================================================

def section_terminals() -> None:
    print("\n--- 1. Terminals: registration, profile and revocation (FR-POS-001) ---")

    profiles = [r[0] for r in rows(
        "SELECT unnest(enum_range(NULL::pos.terminal_profile))::text ORDER BY 1;")]
    record("FR-POS-001: the three device profiles the requirement names exist",
           sorted(profiles) == ["kitchen_display", "point_of_sale", "waiter_handheld"],
           f"{sorted(profiles)}. A profile decides which surface a terminal may open, so "
           f"it is a registration fact rather than a preference somebody sets later")

    registered = rows(f"""
        SELECT t.profile::text, t.revoked_at IS NULL, d.registration_code
        FROM pos.terminal t
        JOIN org.device_registration d ON d.device_id = t.device_id
        WHERE t.device_id = '{fx.DEVICE_HANDHELD}';""")
    record("a device is registered to a tenant, an outlet and a profile",
           len(registered) == 1 and registered[0][0] == "waiter_handheld"
           and registered[0][1] in ("t", "true"),
           f"{registered}. Registered through pos.register_terminal(); a fixture that "
           f"wrote the row itself would prove the table accepts rows and nothing else")

    # A profile may only be given to a DEVICE. M2-B learned the same thing from the other
    # side: a QR code resolving to anything a tenant owned would seat a guest in a kitchen.
    not_a_device = run(APP, f"""
        SELECT pos.register_terminal('{fx.TENANT}', '{fx.OUTLET_H1}',
                                     '{fx.TABLE_ONE}', 'point_of_sale',
                                     '{fx.USER_MANAGER}');""", **CTX)
    record("a table cannot be registered as a terminal",
           not_a_device.failed_with("TERMINAL_NOT_REGISTERED"),
           not_a_device.why() or "a dining table was given a terminal profile")

    # --- revocation ---
    # A terminal registered FOR THIS RUN. Revoking is permanent by design, so a suite
    # that revoked a fixture device could only ever pass once — the same re-runnability
    # defect M3-C found in its idempotency keys, wearing different clothes.
    spare = fx.register_spare_terminal()
    session_id, token = fx.staff_session(fx.USER)
    live_before = count(APP, f"""
        SELECT count(*) FROM identity.session
         WHERE device_id = '{spare}' AND revoked_at IS NULL;""", **CTX)
    run(APP, f"""
        UPDATE identity.session SET device_id = '{spare}'
         WHERE id = '{session_id}';""", **CTX)

    no_reason = run(APP, f"""
        SELECT pos.revoke_terminal('{fx.TENANT}', '{spare}',
                                   '{fx.USER_MANAGER}',
                                   (SELECT id FROM config.reason_code
                                     WHERE tenant_id = '{fx.TENANT}'
                                       AND category = 'order_cancellation' LIMIT 1));""",
        **CTX)
    record("revoking with a reason from the wrong category is refused",
           no_reason.failed_with("DESTRUCTIVE_ACTION_WITHOUT_REASON"),
           no_reason.why() or "a cancellation reason was accepted for a revocation. The "
                              "foreign key would catch an invented id; this catches the "
                              "mistake a busy manager actually makes")

    ended = run(APP, f"""
        SELECT pos.revoke_terminal('{fx.TENANT}', '{spare}',
                                   '{fx.USER_MANAGER}',
                                   '{fx.reason_code("M3D_TERMINAL_COMPROMISED")}');""",
        **CTX)
    live_after = count(APP, f"""
        SELECT count(*) FROM identity.session
         WHERE device_id = '{spare}' AND revoked_at IS NULL;""", **CTX)
    record("revoking a compromised terminal ENDS the sessions on it",
           ended.ok and (ended.scalar or "0").strip() != "0" and live_after == 0,
           f"{ended.why() or ended.scalar} session(s) ended, {live_after} live "
           f"afterwards against {live_before + 1} before. A terminal marked revoked whose "
           f"sessions keep taking orders has not been revoked")

    trust_and_record = rows(f"""
        SELECT (t.revoked_at IS NOT NULL)::text,
               (t.revoked_by_user_id IS NOT NULL)::text,
               (t.revocation_reason_code_id IS NOT NULL)::text
        FROM pos.terminal t WHERE t.device_id = '{spare}';""")
    record("and the revocation states who did it and why",
           trust_and_record and all(v in ("t", "true") for v in trust_and_record[0]),
           f"{trust_and_record}. Enforced by a CHECK that moves the three together, so a "
           f"revocation with no reason cannot be stored even by a direct write")

    again = run(APP, f"""
        SELECT pos.revoke_terminal('{fx.TENANT}', '{spare}',
                                   '{fx.USER_MANAGER}',
                                   '{fx.reason_code("M3D_TERMINAL_COMPROMISED")}');""",
        **CTX)
    record("a terminal already out of service cannot be revoked twice",
           again.failed_with("TERMINAL_ALREADY_REVOKED"),
           again.why() or "a second revocation would overwrite who took it out of "
                          "service and when")


# ===========================================================================
# 2. Waiter ordering is the SAME rules, structurally (FR-POS-003A)
# ===========================================================================
# The requirement rejects "two implementations that agree today", so agreement is not
# what is proved here. What is proved is that a second implementation cannot exist.
#
# The universe of rule functions is ENUMERATED FROM THE CATALOG, never listed. A pricing
# or safety rule added at M4 and re-implemented on the staff side fails this without
# anybody remembering to extend anything, which is the same lesson as M3-A's schema list
# going stale the moment fulfillment landed.

# The instrument itself lives in tests/channel_differential.py, because M4-A adds a third
# channel and a second copy of the check that proves there is only one implementation
# would be the joke writing itself. What stays here is this gate's USE of it.


def rule_functions() -> set[str]:
    return {r[0] for r in rows(RULE_FUNCTION_QUERY, dsn=ADMIN)}


def section_same_rules_structurally() -> None:
    print("\n--- 2. Waiter and QR ordering are one code path, proved structurally "
          "(FR-POS-003A) ---")

    universe = rule_functions()
    record("the rule functions are enumerated from the catalog, not from this file",
           len(universe) > 40,
           f"{len(universe)} rule function(s) enumerated from the catalog across "
           f"{list(RULE_SCHEMAS)}. A named list here "
           f"would stop covering the rule M4 adds, which is exactly how M3-A's schema "
           f"list went stale when fulfillment landed")

    by_surface = rules_by_surface(
        lambda relative: (REPO / relative).read_text(encoding="utf-8"), universe)

    for label in OPERATIONS:
        g = by_surface["guest"][label]
        s = by_surface["staff"][label]
        record(f"{label}: both channels reach the same function, and only that function",
               g == s and len(g) == 1,
               f"guest {g}, staff {s}. Not 'they agree' — the same NAME, so there is no "
               f"second implementation for the two to agree about")

    # The one rule that WAS duplicated. The guest route priced its cart line inline; a
    # staff route written the same way would have been the second copy.
    priced_in_a_route = [
        name for name in ("api/src/routes/customer.ts", "api/src/routes/staff.ts")
        if re.search(r"\bmenu\.effective_price\s*\(",
                     strip_comments((REPO / name).read_text(encoding="utf-8")))]
    record("no route prices anything itself any more",
           priced_in_a_route == [],
           f"routes naming menu.effective_price: {priced_in_a_route or 'none'}. It moved "
           f"into service.add_cart_line() at this gate, so the price a waiter sees and "
           f"the price a guest sees come from one expression rather than two")

    # And in the DATABASE: an order exists because the ledger says so, and the ledger has
    # one writer. Whatever a route does, it cannot make an order another way.
    # The ORDER ITSELF — the projection, not the ledger. Many functions append to
    # ordering.order_event and that is the design: accepting, amending, cancelling and
    # voting are all events. But an order ROW exists because the fold put it there, so
    # whatever a route does, it cannot bring an order into being another way. Read out
    # of the catalog, so a second writer added later is caught whether or not anybody
    # thinks to look for one.
    writers = sorted({r[0] for r in rows("""
        SELECT n.nspname || '.' || p.proname
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE p.prosrc ~ 'INSERT INTO ordering\\.customer_order'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema');""", dsn=ADMIN)})
    record("an order row can only come into existence through the fold",
           writers == ["ordering.apply_event"],
           f"functions writing ordering.customer_order: {writers}. The ledger has many "
           f"appenders by design — accepting, amending and cancelling are all events — "
           f"but the ORDER is written once, by the fold, so no route can make one by "
           f"another path whatever it calls")

    # The staff schema implements no rule of its own. This is the forward-safe half: it
    # is a statement about a SCHEMA, so it covers functions that do not exist yet.
    pos_rule_calls = sorted({r[0] for r in rows("""
        SELECT DISTINCT n.nspname || '.' || p.proname
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'pos'
          AND (p.prosrc ~ 'menu\\.effective_price'
            OR p.prosrc ~ 'INSERT INTO ordering\\.'
            OR p.prosrc ~ 'INSERT INTO menu\\.'
            OR p.prosrc ~ 'safety\\.effective_allergens');""", dsn=ADMIN)})
    record("and the staff schema prices nothing, writes no order and resolves no allergen",
           pos_rule_calls == [],
           f"{pos_rule_calls or 'none'}. pos reads what other schemas own and drives "
           f"their functions; a rule that appeared here would be the staff side growing "
           f"its own opinion about what an order costs or what is in it")


# ===========================================================================
# 3. The same rules, behaviourally, with the REASONS compared (FR-POS-003A)
# ===========================================================================
# The structural half above says a second implementation cannot exist. This half says the
# one implementation behaves the same whichever surface reaches it — and it compares
# REFUSAL CODES, not just outcomes. Two channels that both refuse an over-quantity order
# are not identical if one says the variant is unavailable and the other says the total
# changed: a waiter told the wrong reason goes and finds a manager for a problem they
# could have fixed themselves.


def guest_channel() -> dict:
    """A seated guest with a credential, a cart, and one line in it — over HTTP."""
    seated = fx.a_seated_guest_with_credential(table=fx.TABLE_ONE)
    token = seated["token"]
    cart = guest_call("GET", "/c/v1/cart", token)
    variant = CONTEXT["variant"]
    guest_call("POST", "/c/v1/cart/lines", token,
               {"cartId": cart["cartId"], "itemId": CONTEXT["item"],
                "variantId": variant, "quantity": 1},
               key=idem(f"guest-line-{os.urandom(4).hex()}"))
    return {"token": token, "cartId": cart["cartId"], "session": seated["session"],
            "guest": seated["guest"]}


def staff_channel() -> dict:
    """A waiter with a session, a table, a shared cart, and one line in it — over HTTP."""
    session_id, token = fx.staff_session(fx.USER)
    seated = fx.a_seated_guest(table=fx.TABLE_TWO)
    cart = call("POST", "/s/v1/carts", token, {"tableSessionId": seated["session"]})
    call("POST", "/s/v1/cart/lines", token,
         {"cartId": cart["cartId"], "itemId": CONTEXT["item"],
          "variantId": CONTEXT["variant"], "quantity": 1},
         key=idem(f"staff-line-{os.urandom(4).hex()}"))
    return {"token": token, "cartId": cart["cartId"], "session": seated["session"],
            "sessionId": session_id}


def submit(channel: str, chan: dict, *, total: int | None = None,
           digest: str | None = None, declarations: list | None = None) -> dict:
    path = "/c/v1/orders" if channel == "guest" else "/s/v1/orders"
    preview_path = "/c/v1/orders/preview" if channel == "guest" else "/s/v1/orders/preview"
    caller = guest_call if channel == "guest" else call
    view = caller("POST", preview_path, chan["token"], {"cartId": chan["cartId"]})
    preview = view.get("preview") or {}
    body = {
        "cartId": chan["cartId"],
        "expectedTotalMinor": total if total is not None
                              else int(preview.get("total_amount_minor", 0)),
        "pricingDigest": digest if digest is not None
                         else preview.get("pricing_digest", ""),
        "locale": "en",
        "allergyDeclarations": declarations or [],
    }
    return caller("POST", path, chan["token"], body,
                  key=idem(f"{channel}-submit-{os.urandom(4).hex()}"))


def refusal_matrix(*, record_plant: bool = True) -> list[tuple[str, str, str]]:
    """Three refusals, asked of both channels, compared by CODE rather than by outcome.

    Extracted so NC-M3D-001 can run it a second time against a build with a pricing
    re-implementation planted in the staff route. That is what shows the two halves of
    FR-POS-003A are independent: with the defect in place the STRUCTURAL check goes red
    and this matrix still agrees, which is exactly the "two implementations that agree
    today" the requirement rejects, caught by the half that can see it.
    """
    cases: list[tuple[str, str, str]] = []

    for label, kwargs in (
        ("a total that is not the server's", {"total": 1}),
        ("a pricing digest that is not the server's", {"digest": "00" * 32}),
    ):
        g = submit("guest", guest_channel(), **kwargs)
        s = submit("staff", staff_channel(), **kwargs)
        cases.append((label, g.get("reason", str(g)), s.get("reason", str(s))))

    # An unavailable variant, made unavailable for both at once so neither is being asked
    # a different question.
    # UPDATE, as M3-A does. menu.availability's uniqueness is an EXPRESSION index over
    # coalesced item, variant and modifier ids, so an ON CONFLICT naming plain columns
    # matches no constraint and the statement errors — which the first version of this
    # plant did, silently, leaving both channels asked a question with no defect in it.
    planted = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
        SELECT set_config('app.outlet_id', '{fx.OUTLET_H1}', false);
        UPDATE menu.availability SET state = 'temporarily_unavailable',
               row_version = row_version
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
           AND variant_id = '{CONTEXT["variant"]}';
    """, tx=True)
    if record_plant:
        record("the availability defect the next check needs was actually planted",
               planted.ok and scalar(f"""
                   SELECT state::text FROM menu.availability
                    WHERE outlet_id = '{fx.OUTLET_H1}'
                      AND variant_id = '{CONTEXT["variant"]}';""")
               == "temporarily_unavailable",
               f"{planted.why() or 'variant turned off at this outlet'}. Asserted "
               f"because a plant that failed silently would make the comparison below "
               f"pass with nothing to compare")
    elif not planted.ok:
        raise ProbeFailed("menu.availability", planted.err)
    g_unavailable = submit("guest", guest_channel())
    s_unavailable = submit("staff", staff_channel())
    cases.append(("a variant the kitchen has turned off",
                  g_unavailable.get("reason", str(g_unavailable)),
                  s_unavailable.get("reason", str(s_unavailable))))
    run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
        SELECT set_config('app.outlet_id', '{fx.OUTLET_H1}', false);
        UPDATE menu.availability SET state = 'available', row_version = row_version
         WHERE variant_id = '{CONTEXT["variant"]}' AND outlet_id = '{fx.OUTLET_H1}';
    """, tx=True)

    return cases


def section_same_rules_behaviourally() -> None:
    print("\n--- 3. The same rules refuse for the same REASONS on both channels "
          "(FR-POS-003A) ---")

    # A legal order down each channel. Both succeed, and the ONLY difference between the
    # two orders is the channel dimension M3-A built the aggregate with.
    guest = guest_channel()
    staff = staff_channel()
    CONTEXT["guest_channel"] = guest
    CONTEXT["staff_channel"] = staff

    guest_order = submit("guest", guest)
    staff_order = submit("staff", staff)
    record("a legal order is accepted on both channels",
           "orderId" in guest_order and "orderId" in staff_order,
           f"guest {guest_order.get('orderId', guest_order)}, "
           f"staff {staff_order.get('orderId', staff_order)}")

    CONTEXT["guest_order"] = guest_order.get("orderId")
    CONTEXT["staff_order"] = staff_order.get("orderId")

    shape = rows(f"""
        SELECT origin::text,
               (placed_by_user_id IS NOT NULL)::text,
               (placed_by_guest_session_id IS NOT NULL)::text,
               channel::text, currency_code, coalesce(acceptance_mode::text, '-')
        FROM ordering.customer_order
        WHERE id IN ('{CONTEXT["guest_order"]}', '{CONTEXT["staff_order"]}')
        ORDER BY origin::text;""")
    differ = [i for i in (3, 4) if len({row[i] for row in shape}) > 1] \
        if len(shape) == 2 else [-1]
    record("and the two orders differ only in origin, actor and the configured acceptance",
           len(shape) == 2 and differ == [],
           f"{shape}. Channel and currency identical. The two orders DO reach different "
           f"states, and that is configuration rather than a second implementation: "
           f"ordering.submit_order() reads acceptance -> origin from one policy, so a "
           f"waiter-entered order being already staff-confirmed is the channel dimension "
           f"M3-A built the aggregate with, expressed as data")

    # And the difference really does come from the policy rather than from a branch in
    # the code. Two origins, one lookup, and the modes it returns are what the orders got.
    policy = rows(f"""
        SELECT o.origin::text, o.acceptance_mode::text,
               (ordering.effective_policy('{fx.TENANT}'::uuid, '{fx.OUTLET_H1}'::uuid,
                                          'ordering'::config.policy_category)
                  -> 'acceptance' ->> o.origin::text)
        FROM ordering.customer_order o
        WHERE o.id IN ('{CONTEXT["guest_order"]}', '{CONTEXT["staff_order"]}')
        ORDER BY o.origin::text;""")
    # An order records HOW it was accepted only once it has been: M3-A's
    # customer_order_acceptance_recorded_together CHECK moves accepted_at and
    # acceptance_mode as a pair. So 'automatic' means the policy accepted it on
    # submission, and NULL means the policy asked for a person and no person has come
    # yet. Both are the policy being obeyed, and asserting equality alone would have
    # called the correct guest order a divergence.
    consistent = all(
        (mode == policy_says) if policy_says == "automatic" else (mode == "")
        for _origin, mode, policy_says in policy)
    record("and each order's acceptance is the one the policy names for its origin",
           len(policy) == 2 and consistent,
           f"{policy}. Read back from ordering.effective_policy() rather than asserted "
           f"here. 'automatic' was applied at submission; the guest order records no "
           f"mode because its policy asks for a person and none has confirmed yet — "
           f"which is the same policy, obeyed differently, not a second implementation")

    cases = refusal_matrix()

    mismatched = [(label, g, s) for label, g, s in cases if g != s or not g]
    record("every refusal carries the SAME reason code on both channels",
           mismatched == [],
           "; ".join(f"{label}: {g}" for label, g, _s in cases)
           + (f". MISMATCHED: {mismatched}" if mismatched else "")
           + ". Compared as codes rather than as failures: two channels refusing the "
             "same thing for different stated reasons are not identical, and the waiter "
             "is the one who pays for the difference")


# ===========================================================================
# 4. The allergy path, hop by hop, on a waiter-entered order (FR-POS-003A, FR-SAF-004)
# ===========================================================================
# The sharpest case in the requirement, and the one where "identical" has to mean every
# hop rather than the end state. M3-A proved a guest-entered declaration reaches the
# order, the ledger, the notes and the kitchen. A waiter-entered one is asserted at each
# of those hops here, because a declaration that arrived at the last hop by a different
# route would look identical and be a different system.

def section_allergy_parity() -> None:
    print("\n--- 4. A waiter-entered allergy declaration survives every hop "
          "(FR-POS-003A, FR-SAF-004) ---")

    staff = staff_channel()
    concern = scalar(f"""
        INSERT INTO safety.allergy_concern
            (tenant_id, outlet_id, table_session_id, raised_by, raised_by_user_id,
             allergen_id, acknowledgement_wording_id, acknowledgement_text)
        SELECT '{fx.TENANT}', '{fx.OUTLET_H1}', '{staff["session"]}', 'waiter',
               '{fx.USER}', a.id, w.id, w.wording
        FROM safety.allergen a, safety.approved_wording w
        WHERE a.tenant_id = '{fx.TENANT}' AND w.tenant_id = '{fx.TENANT}'
          AND w.purpose = 'allergy_acknowledgement' AND w.locale = 'en'
        LIMIT 1
        RETURNING id;""")

    order = submit("staff", staff, declarations=[{"allergy_concern_id": concern}])
    order_id = order.get("orderId", "")
    record("a waiter raises a concern and submits the order carrying it",
           bool(order_id),
           f"{order.get('reason', order_id)}. Raised with raised_by='waiter' and the "
           f"waiter named, which is the attribution safety.allergy_concern's CHECK "
           f"requires and the guest path fills differently")

    hops = {}
    hops["ledger"] = count(APP, f"""
        SELECT count(*) FROM ordering.order_event
         WHERE order_id = '{order_id}' AND kind = 'allergy_declared';""", **CTX)
    hops["note"] = count(ADMIN, f"""
        SELECT count(*) FROM ordering.order_note
         WHERE order_id = '{order_id}' AND kind = 'allergy_declaration';""")
    hops["concern_linked"] = count(ADMIN, f"""
        SELECT count(*) FROM ordering.order_note
         WHERE order_id = '{order_id}' AND kind = 'allergy_declaration'
           AND allergy_concern_id = '{concern}';""")

    run(APP, f"SELECT ordering.accept_order('{fx.TENANT}', '{order_id}', '{fx.USER}');",
        **CTX)
    released = run(APP, f"""
        SELECT fulfillment.release_order('{fx.TENANT}', '{order_id}', '{fx.USER}');""",
        **CTX)
    hops["kitchen"] = count(APP, f"""
        SELECT count(*) FROM fulfillment.ticket t
        CROSS JOIN LATERAL fulfillment.ticket_allergy_emphasis('{fx.TENANT}', t.id) e
        WHERE t.order_id = '{order_id}';""", **CTX)

    record("and it is present at every hop M3-A proved for a guest-entered one",
           all(v >= 1 for v in hops.values()),
           f"{hops}, release {released.why() or 'ok'}. Asserted hop by hop rather than "
           f"only at the kitchen: a declaration that reached the last hop by a different "
           f"route would look identical at the end and be a different system")

    emphasis = rows(f"""
        SELECT e.kitchen_code, (e.written_warning IS NOT NULL)::text
        FROM fulfillment.ticket t
        CROSS JOIN LATERAL fulfillment.ticket_allergy_emphasis('{fx.TENANT}', t.id) e
        WHERE t.order_id = '{order_id}';""")
    record("the kitchen receives the written warning with it, not a code alone",
           emphasis and all(row[1] in ("t", "true") for row in emphasis),
           f"{emphasis}. M3-B's rule, unchanged by the channel: a rank with no words "
           f"beside it is the defect NC-M3B-001 exists for")
    CONTEXT["allergy_order"] = order_id


# ===========================================================================
# 5. Role home, the table view, and operational search (FR-POS-002/004/005/010A)
# ===========================================================================

def section_role_home_and_search() -> None:
    print("\n--- 5. Queues, the table view, fast entry and search "
          "(FR-POS-002, FR-POS-004, FR-POS-005, FR-POS-010A) ---")

    fx.set_presence = getattr(fx.m3c, "set_presence")
    fx.set_presence("available")
    seated = fx.a_seated_guest(table=fx.TABLE_ONE)
    fx.assign_table_owner(seated["session"], fx.USER)
    raised = run(APP, f"""
        SELECT service.raise_request('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{seated["session"]}', '{fx.m3c.request_type("assistance")}',
            '{idem("home")}', '{seated["guest"]}');""", **CTX)
    request_id = (raised.scalar or "").strip()

    home = rows(f"""
        SELECT queue, subject_kind, headline, next_action, overdue::text, elapsed_seconds
        FROM pos.role_home('{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.USER}');""")
    record("FR-POS-002: the home screen is queues and next actions, not a list of things",
           home and all(row[3] not in ("", "view", "browse") for row in home)
           and {row[0] for row in home} <= {"service_requests", "tables", "handovers"},
           f"{len(home)} row(s) across {sorted({r[0] for r in home})}; next actions "
           f"{sorted({r[3] for r in home})}. Every row names a VERB, because a screen "
           f"that offers 'view' has told a waiter carrying two plates nothing")

    # The order is the priority, and it comes from the query rather than from the screen.
    overdue_first = [row[4] in ("t", "true") for row in home]
    record("and it is ordered by what is overdue, then by what has waited longest",
           overdue_first == sorted(overdue_first, reverse=True),
           f"overdue flags in returned order: {overdue_first}. FR-UX-004 asks the screen "
           f"to prioritise the active exception; the ORDER is that priority, decided "
           f"once in SQL rather than again in every surface that renders it")

    view = rows(f"""
        SELECT table_reference, assigned_waiter_id IS NULL, open_requests::text,
               unpaid_balance_minor IS NULL, needs_attention::text,
               coalesce(attention_reason, '-')
        FROM pos.table_view('{fx.TENANT}', '{fx.OUTLET_H1}')
        ORDER BY table_reference;""")
    record("FR-POS-004: occupancy carries the waiter, the requests and the attention flag",
           len(view) >= 1 and any(row[2] != "0" for row in view),
           f"{len(view)} occupied table(s); {[r[0] for r in view]}. Assigned waiter, "
           f"open and overdue requests, order progress derived from the tickets, and why "
           f"a table needs attention — all derived, so none can drift from its source")

    # THE SLOT WAS FILLED AT M4-A, and this check moved with it rather than being
    # deleted. It read "the unpaid balance is a SLOT, not an invented zero" and required
    # the column to be NULL, because at M3-D 'nothing outstanding' and 'we have not built
    # billing' were different sentences and a zero would have said the first. Billing
    # exists now, so requiring NULL would require the slot to stay empty forever.
    #
    # What survives is the property this slice actually owns: the figure is DERIVED. No
    # column in pos holds a balance, and pos.table_view() computes it by calling billing
    # rather than by reading something somebody wrote down — which is what makes every
    # other figure on this screen unable to drift from its source, and this one too.
    stored_balance = [r[0] for r in rows("""
        SELECT c.relname || '.' || a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'pos' AND c.relkind = 'r'
          AND a.attnum > 0 AND NOT a.attisdropped
          AND a.attname ~* '(balance|outstanding|amount|total)'
        ORDER BY 1;""", dsn=ADMIN)]
    computed = "billing.session_outstanding" in definition("pos.table_view(uuid, uuid)")
    record("and the unpaid balance is DERIVED, never a figure this schema stores",
           not stored_balance and computed,
           f"columns in pos that could hold a money figure: {stored_balance or 'none'}; "
           f"pos.table_view() computes the balance by calling billing: {computed}. The "
           f"slot this slice left was filled at M4-A by a function call, not by a column "
           f"somebody has to remember to update")

    # --- search ---
    sku = scalar(f"""
        SELECT item_code FROM menu.sellable_item
         WHERE tenant_id = '{fx.TENANT}' AND status = 'active'
         ORDER BY item_code LIMIT 1;""")
    by_sku = rows(f"""
        SELECT item_code, display_name, matched_field
        FROM pos.staff_search('{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.USER}',
                              '{sku}', NULL, 'ar');""")
    record("FR-POS-010A: a Latin SKU is findable from an Arabic session",
           any(row[0] == sku for row in by_sku),
           f"searching {sku!r} in an Arabic session returned {len(by_sku)} result(s). "
           f"M2-A's normaliser strips the tatweel and the bidirectional marks a paste "
           f"drags in, which is what makes a Latin code findable beside Arabic names")

    record("and it is M2-A's search, not a second one written for staff",
           "menu.search_items" in definition(
               "pos.staff_search(uuid, uuid, uuid, text, uuid, menu.customer_locale)"),
           "pos.staff_search() calls menu.search_items(). A staff search with its own "
           "matching would drift from the guest's the first time either was tuned")

    outsider = run(APP, f"""
        SELECT count(*) FROM pos.staff_search('{fx.TENANT}', '{fx.OUTLET_H1}',
                                              '{fx.USER_WAITER_TWO}', NULL, NULL, 'en');""",
        tenant=fx.TENANT, outlet=fx.OUTLET_H2)
    record("a search from the wrong outlet's context finds nothing of this outlet's",
           outsider.failed_with("STAFF_SEARCH_CROSSES_SCOPE") or outsider.scalar == "0",
           outsider.why() or f"returned {outsider.scalar}. Row level security scopes the "
                             f"tables underneath and the role gate refuses the caller; "
                             f"two locks, and the suite proves the second separately")

    picks = rows(f"""
        SELECT count(*)::text FROM pos.fast_pick
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}';""")
    record("FR-POS-005: the outlet has fast picks a new waiter inherits",
           picks and int(picks[0][0]) >= 1,
           f"{picks[0][0]} pick(s) with no user, so they belong to the floor rather than "
           f"to whoever configured them")
    CONTEXT["home_request"] = request_id


# ===========================================================================
# 6. Manager override (FR-POS-006)
# ===========================================================================
# The security argument in four parts: the approver is DERIVED, the grant is on the
# APPROVER'S OWN session, the grant is RECENT, and it is CONSUMED. Each is proved
# separately, because a single passing case would be satisfied by any one of them.

def section_override() -> None:
    print("\n--- 6. Supervisor approval without shared credentials (FR-POS-006) ---")

    waiter_session, waiter_token = fx.staff_session(fx.USER)
    manager_session, manager_token = fx.staff_session(fx.USER_MANAGER)
    reason = fx.reason_code()
    order = CONTEXT.get("staff_order") or CONTEXT.get("guest_order")
    CONTEXT["waiter_token"] = waiter_token
    CONTEXT["manager_session"] = manager_session

    # THE PROPERTY, stated against the catalog. A grant names a SESSION and no user, so
    # whose authentication it represents is reachable only by following the session.
    # Forward-safe: M4 adds refund and payout overrides and cannot express it differently.
    grant_columns = sorted(r[0] for r in rows("""
        SELECT column_name FROM information_schema.columns
         WHERE table_schema = 'identity' AND table_name = 'step_up_grant';""", dsn=ADMIN))
    names_a_user = [c for c in grant_columns if "user" in c or "account" in c]
    record("a step-up grant names a session and cannot name a user",
           names_a_user == [],
           f"{grant_columns}; columns naming a user: {names_a_user or 'none'}. This is "
           f"why an approver can only ever be DERIVED. There is no argument and no "
           f"column by which one session's grant could claim to be somebody else's")

    approver_is_a_parameter = re.search(
        r"p_approver_user_id|p_approver_id",
        definition("pos.approve_override(uuid, uuid, text, uuid, uuid, text, uuid, text)"))
    record("and pos.approve_override() takes no approver identity as an argument",
           approver_is_a_parameter is None,
           "the signature names an approving SESSION and derives the person from it. A "
           "parameter here would be a field a caller could fill in with a name")

    # 1. No step-up at all.
    nothing = as_session(waiter_session, f"""
        SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', 'order.void',
            '{manager_session}', '{reason}', 'order', '{order}');""")
    record("an override with no recent authentication is refused",
           nothing.failed_with("OVERRIDE_WITHOUT_STEP_UP"),
           nothing.why() or "an override completed with nothing behind it")

    # 2. CREDENTIAL SHARING: the manager types their password into the waiter's terminal.
    # The real thing a busy floor manager does, not a missing field.
    fx.step_up(waiter_session, "order.void")
    shared = as_session(waiter_session, f"""
        SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', 'order.void',
            '{waiter_session}', '{reason}', 'order', '{order}');""")
    record("a manager authenticating into the WAITER's session is refused by name",
           shared.failed_with("CREDENTIAL_SHARED_FOR_OVERRIDE"),
           shared.why() or "the waiter's own session approved the waiter's action. The "
                           "grant sits on the waiter's session, so the derived approver "
                           "comes back as the waiter — refused by construction rather "
                           "than by a rule somebody has to remember")

    # 3. A stale grant. M1-B's recency window, reused rather than reinvented.
    stale = fx.step_up(manager_session, "order.void", age_seconds=600)
    expired = as_session(waiter_session, f"""
        SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', 'order.void',
            '{manager_session}', '{reason}', 'order', '{order}');""")
    record("a step-up older than the window approves nothing",
           expired.failed_with("STEP_UP_EXPIRED"),
           expired.why() or "a ten-minute-old authentication approved a void against a "
                            "five-minute window. A stale grant approving a void is the "
                            "same defect as no grant, one step removed")
    run(APP, f"DELETE FROM identity.step_up_grant WHERE id = '{stale}';", **CTX)

    # 4. DELEGATION: the manager steps up on their OWN session.
    grant = fx.step_up(manager_session, "order.void")
    approved = as_session(waiter_session, f"""
        SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', 'order.void',
            '{manager_session}', '{reason}', 'order', '{order}');""")
    override_id = last_value(approved)
    record("a manager stepping up on their OWN session authorizes the waiter's action",
           approved.ok and override_id,
           f"{approved.why() or override_id[:8]}. The delegation case: two people, two "
           f"sessions, both named")
    CONTEXT["override"] = override_id

    both = rows(f"""
        SELECT (actor_user_id = '{fx.USER}')::text,
               (approver_user_id = '{fx.USER_MANAGER}')::text,
               (step_up_grant_id = '{grant}')::text
        FROM pos.override_approval WHERE id = '{override_id}';""")
    record("the record names the waiter, the manager and the grant it rested on",
           both and all(v in ("t", "true") for v in both[0]),
           f"{both}. All three, because a record naming only the approver loses who "
           f"acted and one naming only the actor loses that anybody approved")

    audit = rows(f"""
        SELECT (actor_id = '{fx.USER}')::text,
               (subject_id = '{fx.USER_MANAGER}')::text,
               detail ->> 'step_up_grant_id'
        FROM audit.security_event
        WHERE event_code = 'override.approved'
          AND detail ->> 'override_id' = '{override_id}';""", dsn=ADMIN)
    record("and it lands in M1-C's append-only audit with both identities",
           audit and audit[0][0] in ("t", "true") and audit[0][1] in ("t", "true")
           and audit[0][2] == grant,
           f"{audit}. Written by TRIGGER, so an override recorded by any future path "
           f"lands there too rather than only the ones somebody remembered to log")

    consumed = scalar(f"""
        SELECT (consumed_at IS NOT NULL)::text FROM identity.step_up_grant
         WHERE id = '{grant}';""")
    reused = as_session(waiter_session, f"""
        SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', 'order.void',
            '{manager_session}', '{reason}', 'order', '{order}');""")
    record("one authentication authorizes ONE override",
           consumed in ("t", "true") and reused.failed_with("OVERRIDE_WITHOUT_STEP_UP"),
           f"consumed={consumed}; {reused.why()}. Without this, an approval given at "
           f"seven o'clock authorizes something else at eleven, which is the recency "
           f"window defeated by patience")

    tamper = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
        SELECT set_config('app.outlet_id', '{fx.OUTLET_H1}', false);
        UPDATE pos.override_approval SET action_code = 'order.view'
         WHERE id = '{override_id}';""", tx=True, rollback=True)
    record("and an approval cannot be edited afterwards, by anybody",
           tamper.failed_with("OVERRIDE_RECORD_ALTERED"),
           tamper.why() or "an approval was edited. Proved as the SUPERUSER, so the "
                           "absent grant cannot hide the trigger: two locks, and this "
                           "check reaches past the first to test the second")


# ===========================================================================
# 7. Handover (FR-POS-007)
# ===========================================================================

def section_handover() -> None:
    print("\n--- 7. Responsibility moves, and is never lost on the way (FR-POS-007) ---")

    fx.m3c.set_presence("available")
    seated = fx.a_seated_guest(table=fx.TABLE_ONE)
    fx.assign_table_owner(seated["session"], fx.USER)
    raised = run(APP, f"""
        SELECT service.raise_request('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{seated["session"]}', '{fx.m3c.request_type("water")}',
            '{idem("handover")}', '{seated["guest"]}');""", **CTX)
    request_id = (raised.scalar or "").strip()

    empty = run(APP, f"""
        SELECT pos.propose_handover('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{fx.USER_MANAGER}', '{fx.USER_WAITER_TWO}', '{fx.USER_MANAGER}');""", **CTX)
    record("a handover carrying nothing is refused",
           empty.failed_with("HANDOVER_CARRIES_NOTHING"),
           empty.why() or "somebody pressed a button and the floor believed "
                          "responsibility had moved")

    proposed = run(APP, f"""
        SELECT pos.propose_handover('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{fx.USER}', '{fx.USER_WAITER_TWO}', '{fx.USER}', 'end of the evening');""",
        **CTX)
    handover = (proposed.scalar or "").strip()
    carried = rows(f"""
        SELECT item_kind::text, count(*)::text FROM pos.handover_item
         WHERE handover_id = '{handover}' GROUP BY 1 ORDER BY 1;""")
    record("FR-POS-007: a handover carries the open tables AND the open tasks",
           proposed.ok and {row[0] for row in carried} == {"service_request", "table_session"},
           f"{carried}. Contents captured at proposal, so what is accepted is what was "
           f"offered — a handover that recomputed itself at acknowledgement would move "
           f"tables the recipient never saw")

    not_yours = run(APP, f"""
        SELECT pos.acknowledge_handover('{fx.TENANT}', '{handover}', '{fx.USER_MANAGER}');""",
        **CTX)
    record("a third party cannot accept it on the recipient's behalf",
           not_yours.failed_with("HANDOVER_NOT_YOURS"),
           not_yours.why() or "somebody else accepted responsibility for a colleague, "
                              "which is the silent reassignment M2-B refused on a single "
                              "table and this refuses on a whole section")

    owner_before = scalar(f"""
        SELECT primary_waiter_user_id::text FROM service.table_ownership
         WHERE table_session_id = '{seated["session"]}' AND effective_to IS NULL;""")
    assignee_before = scalar(f"""
        SELECT assigned_user_id::text FROM service.service_request
         WHERE id = '{request_id}';""")

    moved = run(APP, f"""
        SELECT pos.acknowledge_handover('{fx.TENANT}', '{handover}', '{fx.USER_WAITER_TWO}');""",
        **CTX)
    owner_after = scalar(f"""
        SELECT primary_waiter_user_id::text FROM service.table_ownership
         WHERE table_session_id = '{seated["session"]}' AND effective_to IS NULL;""")
    assignee_after = scalar(f"""
        SELECT assigned_user_id::text FROM service.service_request
         WHERE id = '{request_id}';""")

    record("the recipient acknowledges and both the table and the task change hands",
           moved.ok and owner_before == fx.USER and owner_after == fx.USER_WAITER_TWO
           and assignee_before == fx.USER and assignee_after == fx.USER_WAITER_TWO,
           f"{moved.why() or moved.scalar} item(s); table {owner_before[:8]} -> "
           f"{owner_after[:8]}, request {assignee_before[:8]} -> {assignee_after[:8]}")

    through_m2b = definition("pos.acknowledge_handover(uuid, uuid, uuid)")
    record("and each table moves through M2-B's function rather than around it",
           "service.transfer_ownership" in through_m2b
           and "service.reassign_request" in through_m2b
           and "UPDATE service.table_ownership" not in through_m2b,
           "pos.acknowledge_handover() drives service.transfer_ownership() and "
           "service.reassign_request(). A second way to move a table would be a second "
           "place for the acknowledgement rule to be got wrong")

    # The reassignment goes through the LEDGER, so a rebuild reproduces it. M3-C left the
    # fold branch for exactly this and nothing produced one until now.
    reassigned = count(APP, f"""
        SELECT count(*) FROM service.service_request_event
         WHERE service_request_id = '{request_id}' AND kind = 'reassigned';""", **CTX)
    record("the task moved through the ledger, so a rebuild reproduces it",
           reassigned >= 1,
           f"{reassigned} 'reassigned' event(s). M3-C wrote the fold branch and nothing "
           f"emitted one until a surface existed where a request changes hands; an "
           f"UPDATE instead would be a projection a rebuild puts back the way it was")
    CONTEXT["handover_session"] = seated["session"]
    CONTEXT["handover_request"] = request_id


# ===========================================================================
# 8. The staff surface, rendered and measured (FR-UX-002/004/008/015, FR-NOT-012)
# ===========================================================================

def probe(payload: dict) -> dict:
    # Copied INTO the workspace before running, as M3-C's is. Node resolves an import
    # from the SCRIPT's directory, not from the working directory, so a probe left in
    # tests/ cannot find playwright however the process was launched.
    target = WORKSPACE / "m3d_probe.mjs"
    target.write_text((HERE / "render_probe.mjs").read_text(encoding="utf-8"),
                      encoding="utf-8")
    proc = subprocess.run(
        ["node", str(target), CONTEXT["base_url"], json.dumps(payload)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(WORKSPACE),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if proc.returncode != 0 or not proc.stdout.strip():
        raise ProbeFailed("render_probe", proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


def section_staff_surface() -> None:
    print("\n--- 8. The staff surface, rendered and measured "
          "(FR-UX-002, FR-UX-004, FR-UX-008, FR-UX-015, FR-NOT-012) ---")

    session_id, token = fx.staff_session(fx.USER)

    # This section raises its OWN request. Depending on what earlier sections left in the
    # queue is how M3-C's NC-M3C-003 came to measure an empty panel: a later fixture
    # closed the table it was relying on, and the check passed on nothing.
    fx.m3c.set_presence("available")
    own = fx.a_seated_guest(table=fx.TABLE_ONE)
    fx.assign_table_owner(own["session"], fx.USER)
    run(APP, f"""
        SELECT service.raise_request('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{own["session"]}', '{fx.m3c.request_type("call_waiter")}',
            '{idem("surface")}', '{own["guest"]}');""", **CTX)

    home = call("GET", "/s/v1/home", token).get("queues", [])
    tables = call("GET", "/s/v1/tables", token).get("tables", [])
    requirements = call("GET", "/s/v1/confirmation-requirements", token) \
        .get("requirements", [])
    notifications = call("GET", "/s/v1/notifications", token).get("notifications", [])
    results = call("GET", "/s/v1/search?q=", token).get("results", [])

    record("the staff surface reads its own screens over HTTP as a staff session",
           isinstance(home, list) and len(home) > 0 and isinstance(tables, list)
           and len(requirements) > 0,
           f"{len(home)} queue row(s), {len(tables)} table(s), {len(requirements)} "
           f"confirmation grade(s), {len(notifications)} notification(s), "
           f"{len(results)} search result(s)")

    measurement = probe({
        "requirements": requirements, "home": home, "tables": tables,
        "notifications": notifications, "results": results[:5],
    })
    CONTEXT["measurement"] = measurement

    measured("the staff surface rendered with no page or script error",
             measurement["errors"] == [],
             f"errors: {measurement['errors'] or 'none'}")

    normal = measurement["normal"]

    # FR-UX-002. Measured over EVERY control, not the ones this file happened to name.
    small = [c for c in normal["controls"]
             if c["visible"] and (c["height"] < 44 or c["width"] < 44)]
    measured("FR-UX-002: every touch target is big enough to hit while carrying plates",
             small == [],
             f"{len([c for c in normal['controls'] if c['visible']])} visible control(s) "
             f"measured after layout; below 44px: {len(small)}. Measured over all of "
             f"them, so a control added later without a size is caught")

    # FR-UX-004. The next required action is measurably the most prominent thing.
    actions = [r["action"] for r in normal["rows"] if r["action"]]
    siblings = [c for c in normal["controls"] if c["visible"]
                and c not in actions]
    measured("FR-UX-004: the next required action is larger than what surrounds it",
             bool(actions) and all(
                 a["fontSize"] >= max([s["fontSize"] for s in siblings] or [0])
                 and a["height"] >= max([s["height"] for s in siblings] or [0])
                 for a in actions),
             f"{len(actions)} next-action button(s) at "
             f"{sorted({a['fontSize'] for a in actions})}px against siblings at "
             f"{sorted({s['fontSize'] for s in siblings})}px. Prominence measured "
             f"RELATIVELY, as M3-B measured allergy salience — an absolute size proves "
             f"nothing about what stands out")

    measured("and every waiting row states how long it has been waiting, in words",
             bool(normal["rows"]) and all("waiting" in r["elapsed"] for r in normal["rows"]),
             f"{len(normal['rows'])} row(s), each carrying elapsed time. A timestamp is "
             f"not elapsed time to somebody holding two plates")

    # Without colour. Inherited from M3-B: if overdue is only a colour, this is where it
    # stops being visible.
    flattened = measurement["flattened"]
    overdue_rows = [r for r in flattened["rows"] if r["overdue"]]
    measured("an overdue row is still distinguishable with every colour flattened",
             all("overdue" in r["words"] for r in overdue_rows),
             f"{len(overdue_rows)} overdue row(s) in the colour-flattened render, "
             f"{sum(1 for r in overdue_rows if 'overdue' in r['words'])} carrying the "
             f"word. Remove every colour and the distinction survives, or it was never "
             f"a distinction a colour-blind waiter could act on")

    # FR-UX-008.
    accessible = measurement["accessible"]
    bigger = (accessible["bodyFontSize"] > normal["bodyFontSize"]
              and min([c["height"] for c in accessible["controls"] if c["visible"]] or [0])
              > min([c["height"] for c in normal["controls"] if c["visible"]] or [0]))
    measured("FR-UX-008: accessibility mode enlarges the text AND the targets",
             bigger,
             f"body text {normal['bodyFontSize']}px -> {accessible['bodyFontSize']}px; "
             f"smallest control {min([c['height'] for c in normal['controls'] if c['visible']], default=0)}px "
             f"-> {min([c['height'] for c in accessible['controls'] if c['visible']], default=0)}px. "
             f"Measured on the same render rather than read out of a stylesheet, because "
             f"a rule a later selector overrides is a rule that is not in force")

    # FR-UX-015, measured by DOING it.
    confirm = measurement["confirm"]
    measured("FR-UX-015: an ordinary action takes one tap and opens no panel",
             confirm["routine"]["ranWithoutConfirming"] is True
             and confirm["routine"]["panelShown"] is False,
             f"{confirm['routine']}. Friction on ordinary service is friction everywhere, "
             f"dozens of times an hour")

    deliberate = confirm["deliberate"]
    measured("and a deliberate one asks, states the consequence, and demands a reason",
             deliberate["before"]["ranImmediately"] is False
             and deliberate["before"]["panelShown"] is True
             and deliberate["before"]["reasonShown"] is True
             and deliberate["before"]["consequence"] == "deliberate"
             and deliberate["emptyRefused"]["ran"] is False
             and deliberate["withReason"]["ran"] is True,
             f"pressed with an empty reason and it did not run "
             f"({deliberate['emptyRefused']['questionWords']!r}); pressed with a reason "
             f"and it did. The grade came from pos.confirmation_requirement, so the "
             f"surface reads the consequence rather than deciding it")

    # FR-NOT-012's staff half — the partial closure M3-C recorded with M3-D named.
    measured("FR-NOT-012: the staff notification centre renders, in English",
             len(normal["notifications"]) == len(notifications),
             f"{len(normal['notifications'])} notice(s) drawn from "
             f"{len(notifications)} returned by notify.staff_notification_center(). "
             f"M3-C finished the data and named M3-D; this is the screen over it")

    measured("and each one states its severity in words rather than as a colour",
             all(n["severity"] and n["severity"] in n["words"]
                 for n in normal["notifications"]),
             f"{[n['severity'] for n in normal['notifications']]}. A red dot is a "
             f"severity nobody can read aloud")


# ===========================================================================
# 9. Governance
# ===========================================================================

def section_governance() -> None:
    print("\n--- 9. Governance ---")

    failures = partial_closures.check()
    entries = partial_closures.load()
    closed_here = sorted(e["requirement"] for e in entries
                         if e.get("closed_at") == "M3-D")
    record("the register is consistent, and the entry that came due is closed",
           not failures and "FR-NOT-012" in closed_here,
           f"{len(entries)} entries, closed at M3-D: {closed_here}. "
           f"Failures: {failures or 'none'}. Creating tests/m3d/ made FR-NOT-012 come "
           f"due and it was closed rather than silenced")

    opened_here = sorted(e["requirement"] for e in entries
                         if e.get("opened_at") == "M3-D")
    record("and this slice's own half-closed requirements are in the register",
           opened_here,
           f"opened at M3-D: {opened_here}. FR-POS-004's unpaid balance is M4's figure "
           f"and the slot is recorded rather than filled with a zero")

    # NOTHING MAY POINT A FOREIGN KEY AT A PROJECTION.
    #
    # This slice did, and the reversed run found it. pos.handover_item referenced
    # service.service_request, which is folded from a ledger and DELETED wholesale by
    # service.drop_projections_for_rebuild(); the first handover in a tenant's life made
    # FR-DAT-010's rebuild fail with a foreign key violation, and only a reversed run
    # produces a handover before a rebuild. The forward order never did.
    #
    # So the rule is asserted here rather than the instance fixed quietly. Both sides are
    # DERIVED: the projections from the bodies of every drop-for-rebuild function the
    # catalog holds, and the references from pg_constraint. A projection added at M4 is
    # covered the day its drop function is written, and nobody has to remember to extend
    # a list — the same forward-safety the channel differential and M3-A's whole-schema
    # instrument were built for.
    # The extraction is done IN SQL. A function body is multi-line and the probe returns
    # rows as lines, so pulling prosrc back into Python and matching it here silently
    # tore every definition into fragments — the first draft of this check crashed on
    # exactly that, which is the good outcome; the bad one is a regex that matches a
    # fragment and quietly derives a shorter list.
    # Matched on '(rebuild|drop)_projections', not on 'drop_projections'. The first draft
    # used the narrower pattern and derived twelve projections instead of twenty: M3-B and
    # M3-C put their DELETEs in a separate drop function, and M3-A's rebuild does them
    # inline, so every ordering projection fell outside the rule. A derivation that
    # quietly covers less is the failure mode the derivation was supposed to prevent.
    #
    # A projection may reference ANOTHER projection: the rebuild deletes both in one
    # statement, in dependency order, so nothing is left dangling. What breaks is a
    # DURABLE table referencing one, which is why the source side is excluded here rather
    # than the rule being relaxed for the pair that happens to exist today.
    projection_sql = """
        SELECT DISTINCT m[1]
        FROM pg_proc p
        CROSS JOIN LATERAL regexp_matches(
            p.prosrc, 'DELETE FROM ([a-z_]+\.[a-z_]+)', 'g') AS m
        WHERE p.proname ~ '(rebuild|drop)_projections'"""
    projections = sorted({r[0] for r in rows(projection_sql + " ORDER BY 1;", dsn=ADMIN)})
    if len(projections) < 15:
        raise ProbeFailed(
            "(rebuild|drop)_projections",
            f"only {len(projections)} projection(s) derived from the catalog. Three "
            f"schemas rebuild and each has several; a short list here means the "
            f"derivation stopped matching and the rule below is quietly narrower than "
            f"it reads")
    pointed_at = rows(f"""
        SELECT sn.nspname || '.' || sc.relname || '.' || c.conname,
               tn.nspname || '.' || tc.relname
        FROM pg_constraint c
        JOIN pg_class sc ON sc.oid = c.conrelid
        JOIN pg_namespace sn ON sn.oid = sc.relnamespace
        JOIN pg_class tc ON tc.oid = c.confrelid
        JOIN pg_namespace tn ON tn.oid = tc.relnamespace
        WHERE c.contype = 'f'
          AND tn.nspname || '.' || tc.relname IN ({projection_sql})
          AND sn.nspname || '.' || sc.relname NOT IN ({projection_sql})
        ORDER BY 1;""", dsn=ADMIN)
    record("no durable table anywhere points a foreign key at a projection",
           pointed_at == [],
           f"{len(projections)} projection(s) derived from the catalog across three "
           f"schemas. Durable tables referencing one: {pointed_at or 'none'}. A reference "
           f"onto a table a rebuild deletes turns FR-DAT-010 into a constraint "
           f"violation, and pos.handover_item was exactly that until the reversed run "
           f"said so")

    # The fenced vocabulary, over everything this slice added, from the package.
    pattern, terms = fenced_identifier_pattern()
    files = [REPO / "migrations/0015_terminals_override_handover_and_staff_surface.sql",
             REPO / "migrations/0016_translatable_order_status_wording.sql",
             REPO / "migrations/0017_localized_customer_status_timeline.sql",
             REPO / "api/src/routes/staff.ts",
             REPO / "waiter/src/waiter.ts", REPO / "waiter/index.html",
             REPO / "waiter/waiter.css",
             HERE / "verify_m3d.py", HERE / "fixtures.py", HERE / "render_probe.mjs"]
    sources = "\n".join(path.read_text(encoding="utf-8") for path in files)
    hits = sorted({m.group(0) for m in re.finditer(pattern, sources, re.I)})
    record("this slice names no permanently fenced domain",
           hits == [],
           f"checked {len(files)} files — the migration, the staff route, the whole "
           f"waiter surface, the suite, the fixtures and the probe — against all "
           f"{terms} authoritative terms: {hits or 'none'}")

    fenced_columns = rows(f"""
        SELECT c.table_schema || '.' || c.table_name || '.' || c.column_name
        FROM information_schema.columns c
        WHERE c.table_schema = 'pos'
          AND c.column_name ~* '{pattern}';""", dsn=ADMIN)
    record("FR-POS-007: no identifier in the staff schema names a shift or a roster",
           fenced_columns == [],
           f"{fenced_columns or 'none'}, against all {terms} terms in the pinned "
           f"vocabulary rather than "
           f"the three words the requirement happens to name. Checked against the "
           f"CATALOG, so a column a later migration adds is covered without anybody "
           f"extending this. A handover is a transfer that happened, never a schedule")

    unforced = rows("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'pos' AND c.relkind = 'r'
          AND NOT (c.relrowsecurity AND c.relforcerowsecurity);""", dsn=ADMIN)
    pos_tables = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'pos' AND c.relkind = 'r';""")
    record("every table in the staff schema has row level security ENABLED and FORCED",
           unforced == [] and pos_tables > 0,
           f"{unforced or 'none'} unforced across {pos_tables} table(s) — M1-A's "
           f"NC-M1-003 gates this in CI and it gates them unchanged")

    wrong_predicate = rows("""
        SELECT c.relname, p.polname
        FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'pos'
          AND pg_get_expr(p.polqual, p.polrelid) NOT LIKE '%row_in_scope%';""", dsn=ADMIN)
    record("and every policy uses the one isolation predicate",
           wrong_predicate == [],
           f"{wrong_predicate or 'none'} — one predicate, so there is one thing to get "
           f"right rather than one per table")

    unpinned = rows("""
        SELECT n.nspname || '.' || p.proname
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'pos' AND p.prosecdef
          AND NOT EXISTS (SELECT 1 FROM unnest(coalesce(p.proconfig, '{}'))
                          AS cfg WHERE cfg LIKE 'search_path=%');""", dsn=ADMIN)
    record("every SECURITY DEFINER function in the staff schema pins its search path",
           unpinned == [],
           f"unpinned: {unpinned or 'none'}")

    # The finding this slice made about migration-time backfills.
    visible = count(os.environ["M1A_MIGRATOR_DSN"], "SELECT count(*) FROM org.tenant;")
    record("a migration cannot enumerate tenants, which is why the installer is a function",
           visible == 0,
           f"the migration identity sees {visible} tenant(s) with no context, because "
           f"org.tenant is scoped by row level security and hospitality_migrator is not "
           f"BYPASSRLS. Any backfill written as INSERT ... SELECT ... FROM org.tenant "
           f"matches nothing — 0010 contains one — so this slice ships "
           f"pos.install_registries_for() instead, which an operator calls per tenant "
           f"with that tenant's context")

    installer = run(APP, f"""
        SELECT pos.install_registries_for('{fx.TENANT}');""", **CTX)
    record("and that installer is idempotent for a tenant that already has everything",
           installer.ok and (installer.scalar or "").strip() == "0",
           f"installed {installer.why() or installer.scalar} additional row(s) for a "
           f"tenant the trigger already covered")

    # 'billing' left this list at M4-A, which built it, the same way every earlier gate
    # left the equivalent list in the suite below it. What remains is what has genuinely
    # not been built: payment capture is M4-B, receipts are M4-C, and the outlet node,
    # synchronization and the print queue are M5a. tests/m4a took over proving where the
    # money vocabulary is allowed to live.
    later = rows("""
        SELECT c.table_schema || '.' || c.table_name
        FROM information_schema.tables c
        WHERE c.table_schema IN ('payment', 'receipt', 'sync', 'outlet_node')
        ORDER BY 1;""", dsn=ADMIN)
    record("nothing belonging to a later slice was built here",
           later == [],
           f"{later or 'none'} — payment capture is M4-B and receipts M4-C; the outlet "
           f"node, synchronization and the print queue are M5a. Billing landed at M4-A "
           f"and left this list, as the order surface left M2-A's when M3-A built it")

    secrets = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(?i)(password|secret|api[_-]?key)\s*=\s*['\"][^'\"]{6,}",
                                 text):
            secrets.append(f"{path.name}:{match.group(0)[:40]}")
    record("no credential is written into this slice's source",
           secrets == [],
           f"{secrets or 'none'}. Every staff token the fixtures mint is generated per "
           f"run from os.urandom and only its sha256 reaches the database (FR-SEC-007)")


# ===========================================================================
# 10. Negative controls
# ===========================================================================
# Each plants a REAL defect — in the delivered SQL, the delivered route or the delivered
# surface — requires the registered signature, then reverts and requires green again. A
# control that never went red is a coverage gap wearing a green badge.


def replace_function(signature_name: str, old: str, new: str) -> None:
    """Rewrite one delivered function in place, keeping everything else about it."""
    body = definition(signature_name)
    if old not in body:
        raise ProbeFailed(signature_name, f"cannot plant: anchor absent from {signature_name}")
    res = run(ADMIN, body.replace(old, new, 1) + ";")
    if not res.ok:
        raise ProbeFailed(f"planting into {signature_name}", res.err)


def restore_function(signature_name: str, body: str) -> None:
    res = run(ADMIN, body + ";")
    if not res.ok:
        raise ProbeFailed(f"restoring {signature_name}", res.err)


def control(name: str, signature_name: str, red, green) -> None:
    print(f"\n  {name}")
    ok, detail = red()
    record(f"{name} — RED with the defect planted", ok, detail)
    ok, detail = green()
    record(f"{name} — GREEN after revert", ok, detail)


def section_controls() -> None:
    print("\n--- 10. Negative controls: each proved RED with a real defect, then GREEN ---")

    reason = fx.reason_code()

    # NC-M3D-001 — a waiter-entered order bypasses a rule QR ordering enforces.
    # Planted in the STAFF ROUTE: it stops calling the shared writer and prices the line
    # itself, which is precisely the "two implementations that agree today" shape.
    def red_channel():
        # A CORRECT second implementation, not a broken one. The first version of this
        # plant wrote a line at a made-up price and the staff cart came out empty, so the
        # behavioural matrix went red too — which proves nothing about independence,
        # because a defect both halves catch is not the defect FR-POS-003A is about. This
        # one re-implements service.add_cart_line() faithfully: it calls the same pricing
        # rule, refuses the same way when there is no price, and inserts the same row. It
        # is a second expression of the same rule that AGREES TODAY, which is precisely
        # what the requirement rejects and precisely what behaviour cannot see.
        patch_workspace(
            "routes/staff.ts",
            "SELECT service.add_cart_line($1::uuid, $2::uuid, $3::uuid, $4::uuid,\n"
            "                                          $5::uuid, $6::integer, NULL::uuid) AS id",
            "INSERT INTO service.cart_line (tenant_id, outlet_id, cart_id, item_id, "
            "variant_id, quantity, currency_code, unit_amount_minor, "
            "added_by_guest_session_id) "
            "SELECT $1::uuid, $2::uuid, $3::uuid, $4::uuid, $5::uuid, $6::integer, "
            "'ETB', menu.effective_price($1::uuid, $2::uuid, $5::uuid, "
            "NULL::menu.sales_channel, 'ETB'::char(3), now()), NULL::uuid RETURNING id")
        guest = strip_comments(
            (WORKSPACE / "src/routes/customer.ts").read_text(encoding="utf-8"))
        staff = strip_comments(
            (WORKSPACE / "src/routes/staff.ts").read_text(encoding="utf-8"))
        universe = rule_functions()
        g = named_rules(handler_block(guest, "/c/v1/cart/lines"), universe)
        s = named_rules(handler_block(staff, "/s/v1/cart/lines"), universe)
        prices_itself = bool(re.search(r"unit_amount_minor", staff))

        # AND THE BEHAVIOURAL HALF STILL AGREES. The founder's condition on the two-part
        # proof was that each half can fail without the other, and this is the case that
        # shows it: with a second pricing implementation compiled into the staff route,
        # the refusal matrix asks both channels the same three questions and gets the
        # same three codes. A slice that had only the behavioural half would report this
        # system as correct. The matrix runs against a SECOND service process started on
        # the patched build, because the one serving the rest of the suite loaded the
        # code before the defect existed and would answer for a system that is not the
        # one under test.
        agreed, detail = [], "not run"
        try:
            with Service(APP) as planted_service:
                was = CONTEXT["base_url"]
                CONTEXT["base_url"] = f"http://127.0.0.1:{planted_service.port}"
                try:
                    matrix = refusal_matrix(record_plant=False)
                finally:
                    CONTEXT["base_url"] = was
            agreed = [c for c in matrix if c[1] == c[2] and c[1]]
            detail = f"{len(agreed)} of {len(matrix)} refusals still identical: {matrix}"
        except Exception as error:                       # noqa: BLE001
            detail = f"the planted build could not be exercised: {error}"

        return (g != s and prices_itself
                and len(agreed) == len(matrix) and len(matrix) == 3,
                f"CHANNEL_RULE_DIVERGENCE: the staff route prices its own line "
                f"(guest {g}, staff {s}); the price a waiter sees and the price a guest "
                f"sees now come from two expressions — while the behavioural matrix is "
                f"still green ({detail}). Two implementations that agree today is what "
                f"FR-POS-003A rejects, and only the structural half can see it")

    def green_channel():
        sync_and_build()
        guest = strip_comments(
            (WORKSPACE / "src/routes/customer.ts").read_text(encoding="utf-8"))
        staff = strip_comments(
            (WORKSPACE / "src/routes/staff.ts").read_text(encoding="utf-8"))
        universe = rule_functions()
        g = named_rules(handler_block(guest, "/c/v1/cart/lines"), universe)
        s = named_rules(handler_block(staff, "/s/v1/cart/lines"), universe)
        return g == s == ["service.add_cart_line"], f"guest {g}, staff {s} — one writer again"

    control("NC-M3D-001  a waiter-entered order bypasses a rule QR ordering enforces",
            "", red_channel, green_channel)

    # NC-M3D-002 — a manager override completes without step-up.
    body = definition("pos.approve_override(uuid, uuid, text, uuid, uuid, text, uuid, text)")

    def red_no_step_up():
        replace_function(
            "pos.approve_override(uuid, uuid, text, uuid, uuid, text, uuid, text)",
            "IF NOT FOUND THEN\n        RAISE EXCEPTION\n            'OVERRIDE_WITHOUT_STEP_UP: % was approved with no unconsumed step-up on the '\n            'approving session', p_action_code",
            "IF FALSE THEN\n        RAISE EXCEPTION\n            'OVERRIDE_WITHOUT_STEP_UP: % was approved with no unconsumed step-up on the '\n            'approving session', p_action_code")
        w_session, _ = fx.staff_session(fx.USER)
        m_session, _ = fx.staff_session(fx.USER_MANAGER)
        res = as_session(w_session, f"""
            SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', 'order.void',
                '{m_session}', '{reason}', 'order',
                '{CONTEXT.get("staff_order") or CONTEXT.get("guest_order")}');""")
        # With the guard removed the grant lookup finds nothing and the INSERT fails on
        # the NOT NULL, which is the defect surfacing rather than being caught by name.
        return (not res.failed_with("OVERRIDE_WITHOUT_STEP_UP"),
                f"OVERRIDE_WITHOUT_STEP_UP: the check that refuses an unauthorized "
                f"override no longer refuses it: {res.why() or 'it completed'}")

    def green_no_step_up():
        restore_function("pos.approve_override", body)
        w_session, _ = fx.staff_session(fx.USER)
        m_session, _ = fx.staff_session(fx.USER_MANAGER)
        res = as_session(w_session, f"""
            SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', 'order.void',
                '{m_session}', '{reason}', 'order',
                '{CONTEXT.get("staff_order") or CONTEXT.get("guest_order")}');""")
        return res.failed_with("OVERRIDE_WITHOUT_STEP_UP"), res.why()

    control("NC-M3D-002  a manager override completes without step-up",
            "pos.approve_override", red_no_step_up, green_no_step_up)

    # NC-M3D-003 — the override succeeds by credential sharing rather than delegation.
    # The defect planted is the REAL one: the guard that compares the two people is
    # removed, so a manager who typed their password into the waiter's terminal is
    # accepted. Not a missing field — the thing a busy floor manager actually does.
    def red_sharing():
        replace_function(
            "pos.approve_override(uuid, uuid, text, uuid, uuid, text, uuid, text)",
            "IF v_approver_session.user_account_id = v_actor_session.user_account_id THEN",
            "IF FALSE THEN")
        w_session, _ = fx.staff_session(fx.USER)
        fx.step_up(w_session, "order.void")
        res = as_session(w_session, f"""
            SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', 'order.void',
                '{w_session}', '{reason}', 'order',
                '{CONTEXT.get("staff_order") or CONTEXT.get("guest_order")}');""")
        # The CHECK constraint is the second lock and catches it even with the guard
        # gone, so the control asserts the SIGNATURE is no longer the named one.
        return (not res.failed_with("CREDENTIAL_SHARED_FOR_OVERRIDE"),
                f"CREDENTIAL_SHARED_FOR_OVERRIDE: a manager authenticating into the "
                f"waiter's session is no longer refused by name — "
                f"{res.why() or 'it was accepted'}")

    def green_sharing():
        restore_function("pos.approve_override", body)
        w_session, _ = fx.staff_session(fx.USER)
        fx.step_up(w_session, "order.void")
        res = as_session(w_session, f"""
            SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', 'order.void',
                '{w_session}', '{reason}', 'order',
                '{CONTEXT.get("staff_order") or CONTEXT.get("guest_order")}');""")
        return res.failed_with("CREDENTIAL_SHARED_FOR_OVERRIDE"), res.why()

    control("NC-M3D-003  an override succeeds by credential sharing rather than delegation",
            "pos.approve_override", red_sharing, green_sharing)

    # NC-M3D-004 — staff search returns a row the searcher has no business seeing.
    #
    # Re-targeted after the first version could not be made to go red, which was worth
    # more than the control. pos.staff_search() gates TWICE: an active membership at this
    # outlet, and a role that grants order.view. Breaking either outlet comparison
    # changes nothing observable, because ROW LEVEL SECURITY refuses first — a waiter
    # whose context is outlet H2 cannot see their own H1 memberships, so the EXISTS finds
    # nothing whatever the predicate says. Cross-OUTLET leakage in search is therefore
    # structurally impossible rather than merely checked, which is the stronger position
    # and is asserted separately in section 5.
    #
    # What CAN fail is the ROLE gate, which is this slice's own. The manager holds an
    # active membership at this outlet and a role that grants voids, amendments and
    # revocations — and not order.view. Without the gate they can search the menu.
    search_body = definition(
        "pos.staff_search(uuid, uuid, uuid, text, uuid, menu.customer_locale)")

    def red_search():
        broken = search_body.replace("AND ra.action_code = 'order.view'",
                                     "AND ra.action_code IS NOT NULL")
        planted = run(ADMIN, broken + ";")
        if not planted.ok:
            return False, f"could not plant: {planted.err}"
        crossed = run(APP, f"""
            SELECT count(*) FROM pos.staff_search('{fx.TENANT}', '{fx.OUTLET_H1}',
                                                  '{fx.USER_MANAGER}', NULL, NULL, 'en');""",
            **CTX)
        return (crossed.ok,
                f"STAFF_SEARCH_CROSSES_SCOPE: a manager whose role grants no order.view "
                f"searched the menu anyway and reached {crossed.scalar} row(s); any "
                f"active membership now opens the search")

    def green_search():
        restore_function("pos.staff_search", search_body)
        crossed = run(APP, f"""
            SELECT count(*) FROM pos.staff_search('{fx.TENANT}', '{fx.OUTLET_H1}',
                                                  '{fx.USER_MANAGER}', NULL, NULL, 'en');""",
            **CTX)
        allowed = run(APP, f"""
            SELECT count(*) FROM pos.staff_search('{fx.TENANT}', '{fx.OUTLET_H1}',
                                                  '{fx.USER}', NULL, NULL, 'en');""",
            **CTX)
        return (crossed.failed_with("STAFF_SEARCH_CROSSES_SCOPE") and allowed.ok,
                f"{crossed.why()}; and the waiter, whose role does grant it, still "
                f"reaches {allowed.scalar} row(s) — a gate that refused everybody would "
                f"pass this check and be useless")

    control("NC-M3D-004  staff search returns a row the searcher has no business seeing",
            "pos.staff_search", red_search, green_search)

    # NC-M3D-005 — allergy confirmation carries the same friction as an ordinary action.
    # Planted in the GRADE, which is where the requirement lives, and measured in the
    # BROWSER, because FR-UX-015 is a claim about what a person has to do.
    def red_friction():
        res = run(ADMIN, f"""
            SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
            UPDATE pos.confirmation_requirement
               SET consequence = 'routine', requires_reason = false
             WHERE tenant_id = '{fx.TENANT}' AND action_code = 'allergy.declare';""",
            tx=True)
        if not res.ok:
            return False, f"could not plant: {res.err}"
        _sid, token = fx.staff_session(fx.USER)
        requirements = call("GET", "/s/v1/confirmation-requirements", token) \
            .get("requirements", [])
        out = probe({"requirements": requirements, "home": [], "tables": [],
                     "notifications": [], "results": []})
        deliberate = out["confirm"]["deliberate"]["before"]
        return (deliberate["ranImmediately"] is True,
                f"FRICTION_NOT_GRADED_BY_CONSEQUENCE: declaring an allergy ran on one "
                f"tap with no confirmation and no reason "
                f"(panel shown: {deliberate['panelShown']})")

    def green_friction():
        res = run(ADMIN, f"""
            SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
            UPDATE pos.confirmation_requirement
               SET consequence = 'deliberate', requires_reason = true
             WHERE tenant_id = '{fx.TENANT}' AND action_code = 'allergy.declare';""",
            tx=True)
        _sid, token = fx.staff_session(fx.USER)
        requirements = call("GET", "/s/v1/confirmation-requirements", token) \
            .get("requirements", [])
        out = probe({"requirements": requirements, "home": [], "tables": [],
                     "notifications": [], "results": []})
        deliberate = out["confirm"]["deliberate"]
        return (res.ok and deliberate["before"]["ranImmediately"] is False
                and deliberate["emptyRefused"]["ran"] is False,
                "declaring an allergy asks, states the consequence and refuses without "
                "a reason, measured in the browser")

    control("NC-M3D-005  allergy confirmation carries the same friction as an ordinary action",
            "", red_friction, green_friction)

    # NC-M3D-006 — a destructive action proceeds with no reason recorded.
    def red_reason():
        res = run(ADMIN, f"""
            SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
            SELECT set_config('app.outlet_id', '{fx.OUTLET_H1}', false);
            ALTER TABLE pos.confirmation_requirement
                DROP CONSTRAINT confirmation_deliberate_states_a_reason;
            UPDATE pos.confirmation_requirement SET requires_reason = false
             WHERE tenant_id = '{fx.TENANT}' AND action_code = 'terminal.revoke';""",
            tx=True)
        if not res.ok:
            return False, f"could not plant: {res.err}"
        stated = rows(f"""
            SELECT consequence::text, requires_reason::text
            FROM pos.confirmation_requirement
             WHERE tenant_id = '{fx.TENANT}' AND action_code = 'terminal.revoke';""")
        return (stated and stated[0][0] == "deliberate"
                and stated[0][1] in ("f", "false"),
                f"DESTRUCTIVE_ACTION_WITHOUT_REASON: revoking a terminal is graded "
                f"{stated} — deliberate, and recording no reason. A deliberate action "
                f"that states nothing is an ordinary action with an extra tap")

    def green_reason():
        res = run(ADMIN, f"""
            SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
            UPDATE pos.confirmation_requirement SET requires_reason = true
             WHERE tenant_id = '{fx.TENANT}' AND action_code = 'terminal.revoke';
            ALTER TABLE pos.confirmation_requirement
                ADD CONSTRAINT confirmation_deliberate_states_a_reason
                CHECK (consequence <> 'deliberate' OR requires_reason = true);""", tx=True)
        broken = run(ADMIN, f"""
            SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
            UPDATE pos.confirmation_requirement SET requires_reason = false
             WHERE tenant_id = '{fx.TENANT}' AND action_code = 'terminal.revoke';""",
            tx=True, rollback=True)
        return (res.ok and not broken.ok,
                f"the CHECK is back and refuses the grade: {broken.why()}")

    control("NC-M3D-006  a destructive action proceeds with no reason recorded",
            "", red_reason, green_reason)

    # NC-M3D-007 — a handover leaves a table with no responsible owner.
    ack_body = definition("pos.acknowledge_handover(uuid, uuid, uuid)")

    def red_handover():
        replace_function(
            "pos.acknowledge_handover(uuid, uuid, uuid)",
            "PERFORM service.transfer_ownership(p_tenant_id, v_transfer);",
            "NULL;")
        fx.m3c.set_presence("available")
        seated = fx.a_seated_guest(table=fx.TABLE_TWO)
        fx.assign_table_owner(seated["session"], fx.USER)
        proposed = run(APP, f"""
            SELECT pos.propose_handover('{fx.TENANT}', '{fx.OUTLET_H1}',
                '{fx.USER}', '{fx.USER_WAITER_TWO}', '{fx.USER}');""", **CTX)
        handover = (proposed.scalar or "").strip()
        res = run(APP, f"""
            SELECT pos.acknowledge_handover('{fx.TENANT}', '{handover}',
                                            '{fx.USER_WAITER_TWO}');""", **CTX)
        return (res.failed_with("RESPONSIBILITY_LOST_ON_HANDOVER"),
                res.why() or "a handover completed with tables that moved to nobody")

    def green_handover():
        restore_function("pos.acknowledge_handover", ack_body)
        fx.m3c.set_presence("available")
        seated = fx.a_seated_guest(table=fx.TABLE_TWO)
        fx.assign_table_owner(seated["session"], fx.USER)
        proposed = run(APP, f"""
            SELECT pos.propose_handover('{fx.TENANT}', '{fx.OUTLET_H1}',
                '{fx.USER}', '{fx.USER_WAITER_TWO}', '{fx.USER}');""", **CTX)
        handover = (proposed.scalar or "").strip()
        res = run(APP, f"""
            SELECT pos.acknowledge_handover('{fx.TENANT}', '{handover}',
                                            '{fx.USER_WAITER_TWO}');""", **CTX)
        orphans = count(APP, f"""
            SELECT count(*) FROM pos.handover_item i
            WHERE i.handover_id = '{handover}' AND i.item_kind = 'table_session'
              AND NOT EXISTS (SELECT 1 FROM service.table_ownership o
                               WHERE o.table_session_id = i.table_session_id
                                 AND o.effective_to IS NULL
                                 AND o.primary_waiter_user_id = '{fx.USER_WAITER_TWO}');""",
            **CTX)
        return (res.ok and orphans == 0,
                f"{res.why() or res.scalar} item(s) moved, {orphans} left with nobody "
                f"accountable. Checked at COMMIT by a deferred constraint trigger, so a "
                f"correct handover is not refused halfway through")

    control("NC-M3D-007  a handover leaves a table with no responsible owner",
            "pos.acknowledge_handover", red_handover, green_handover)


# ===========================================================================
# 11. The README generator's own refusals, proved red then green
# ===========================================================================
# NOT A DATABASE CONTROL, and it belongs here anyway. M3-D is the slice that taught the
# generator a suite need not be a slice, and a rule added without a red is a rule nobody
# has seen work. The three refusals are proved by planting the real defect each one
# exists for — a slice nobody described, a suite nobody described, a cross-cutting suite
# that says nothing about its reach — and then by putting it back.
#
# The defect is planted in the generator's own module-level state, or as a real directory
# under tests/, never by editing tools/generate_readme.py. Same discipline as the route
# controls above, which patch the WORKSPACE copy and leave the repository alone: a
# control that edited the tool it was proving would leave the repository one crash away
# from a silently weakened generator.

def _readme_generator():
    """The generator, imported as a module so its refusals can be provoked in process."""
    import importlib.util
    # Importing a tool writes tools/__pycache__ unless this is off, and that directory is
    # forbidden surface: tools/verify_m1.py fails the build on it. The drivers and CI both
    # export PYTHONDONTWRITEBYTECODE, and this does not rely on their having done so —
    # a control that left a forbidden directory behind would fail a different gate and
    # look like an unrelated defect.
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(
        "m3d_generate_readme", REPO / "tools" / "generate_readme.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _generator_refusal(module) -> str:
    """Run the generator and return the refusal it printed, or '' if it produced a README.

    SystemExit is the generator's own refusal channel for the two suite rules and
    SliceUndescribed for the slice one, so both are caught and reduced to the signature
    the control asserts. Any other exception is a defect in this control and propagates.
    """
    try:
        module.build()
    except SystemExit as refused:
        return str(refused)
    except module.SliceUndescribed as refused:
        return f"FAIL SLICE_UNDESCRIBED: {refused}"
    except module.DescriptionNamesADerivableFact as refused:
        return f"FAIL DESCRIPTION_NAMES_A_DERIVABLE_FACT: {refused}"
    return ""


def section_generator_controls() -> None:
    print("\n--- 11. The README generator refuses what it is supposed to refuse ---")

    import shutil

    module = _readme_generator()

    # NC-M3D-008 — a slice landed and the README says nothing about it.
    landed = sorted(module.SLICE_DELIVERS)[-1]

    def red_slice():
        module.SLICE_DELIVERS.pop(landed)
        signature = _generator_refusal(module)
        return ("SLICE_UNDESCRIBED" in signature,
                f"{signature.splitlines()[0] if signature else 'the README generated anyway'} "
                f"— {landed} is in the repository and the generator has nothing to say "
                f"about it")

    def green_slice():
        module.SLICE_DELIVERS[landed] = _SLICE_DELIVERS_BACKUP[landed]
        signature = _generator_refusal(module)
        return (signature == "",
                f"the README generates again with {landed} described")

    _SLICE_DELIVERS_BACKUP = dict(module.SLICE_DELIVERS)
    control("NC-M3D-008  a landed slice that the README describes nowhere",
            "", red_slice, green_slice)

    # NC-M3D-009 — a suite exists and nothing says what it covers.
    # A REAL directory, because the generator discovers suites from the filesystem and a
    # control that mutated its list instead would be proving a different rule.
    planted = REPO / "tests" / "zz_control_undescribed"

    def red_suite():
        planted.mkdir(exist_ok=True)
        (planted / "verify_zz_control_undescribed.py").write_text(
            "# Planted by NC-M3D-009 and removed by it. If this file is in a commit, the\n"
            "# control crashed between planting and cleanup and the tree is not clean.\n",
            encoding="utf-8")
        signature = _generator_refusal(module)
        return ("SUITE_UNDESCRIBED" in signature,
                f"{signature.splitlines()[0] if signature else 'the README generated anyway'} "
                f"— a suite that would have rendered as the word 'verification', which "
                f"reads like a description and is not one")

    def green_suite():
        shutil.rmtree(planted, ignore_errors=True)
        signature = _generator_refusal(module)
        return (signature == "" and not planted.exists(),
                "the planted suite is gone and the README generates again")

    try:
        control("NC-M3D-009  a suite exists and nothing says what it covers",
                "", red_suite, green_suite)
    finally:
        shutil.rmtree(planted, ignore_errors=True)

    # NC-M3D-010 — the rule M3-D added: a cross-cutting suite that declares no span.
    # This is the one the founder asked to see red before green, and the reason is that
    # the generator could not previously MODEL the distinction: a suite escaped the slice
    # rule by not matching a regex, and was then described as though it were a slice
    # sitting beside one. Two defects, both planted.
    def red_span():
        module.SUITE_SPANS.pop("journeys")
        missing = _generator_refusal(module)
        module.SUITE_SPANS["journeys"] = ["M1", "M2", "M3", "M9"]
        wishful = _generator_refusal(module)
        return ("SUITE_SPAN_UNDECLARED" in missing and "SUITE_SPAN_UNDECLARED" in wishful,
                f"undeclared: {missing.splitlines()[0] if missing else 'generated anyway'} "
                f"| unlanded gate: "
                f"{wishful.splitlines()[0] if wishful else 'generated anyway'} — both "
                f"refused, so the rule catches a suite that says nothing AND one that "
                f"claims a gate the repository has not landed")

    def green_span():
        module.SUITE_SPANS["journeys"] = ["M1", "M2", "M3"]
        signature = _generator_refusal(module)
        rendered = module.build()
        return (signature == "" and "spans M1 · M2 · M3" in rendered,
                "the journeys row renders its span again, so a reviewer reads a suite "
                "that crosses gates as one rather than as a repeat of the slice beside it")

    control("NC-M3D-010  a cross-cutting suite that declares no span",
            "", red_span, green_span)

    # NC-M3D-011 — a description states a fact the generator can derive.
    #
    # The instance: DIRECTORY_PURPOSE said the API was "M1 surface only" for three gates
    # of API work, and no check could see it because a literal cannot go stale visibly.
    # Planted as the exact sentence that was there, so this control fails the day somebody
    # writes it again.
    def red_derivable():
        was = module.DIRECTORY_PURPOSE["api"]
        module.DIRECTORY_PURPOSE["api"] = (
            "the cloud API — Fastify and TypeScript, M1 surface only")
        named = _generator_refusal(module)
        module.DIRECTORY_PURPOSE["api"] = "the cloud API — serving {no_such_fact}"
        unknown = _generator_refusal(module)
        module.DIRECTORY_PURPOSE["api"] = was
        return ("DESCRIPTION_NAMES_A_DERIVABLE_FACT" in named
                and "DESCRIPTION_NAMES_A_DERIVABLE_FACT" in unknown,
                f"the sentence that was actually there: "
                f"{named.splitlines()[0] if named else 'generated anyway'} | a token "
                f"nothing derives: "
                f"{unknown.splitlines()[0] if unknown else 'generated anyway'} — both "
                f"refused, so neither a hardcoded gate nor a description that would "
                f"render a brace can reach the README")

    def green_derivable():
        signature = _generator_refusal(module)
        rendered = module.build()
        return (signature == "" and "M1 surface only" not in rendered,
                "the API row states what it serves, derived from the route modules on "
                "disk, so it cannot name a gate it has outgrown")

    control("NC-M3D-011  a directory description states a fact the generator can derive",
            "", red_derivable, green_derivable)

    # NC-M3D-012 — the CI matrix stops describing the pipeline.
    #
    # This document was hand-written at M0R and never locked. It said five jobs, four
    # suites and nineteen controls when there were six, thirteen and seventy-six, and
    # nothing failed because nothing read it.
    matrix_path = REPO / "planning" / "CI_TEST_MATRIX.md"
    matrix_was = matrix_path.read_text(encoding="utf-8")

    def _matrix_check() -> str:
        result = subprocess.run(
            [sys.executable, str(REPO / "tools" / "generate_ci_matrix.py"),
             "--check", str(matrix_path)],
            capture_output=True, text=True, cwd=str(REPO),
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        return (result.stdout + result.stderr).strip()

    def red_matrix():
        matrix_path.write_text(
            matrix_was.replace("Six jobs", "Five jobs", 1), encoding="utf-8")
        drifted = _matrix_check()
        return ("CI_MATRIX_DRIFT" in drifted,
                f"{drifted.splitlines()[0] if drifted else 'the matrix checked out clean'} "
                f"— one word changed in a document nobody was checking is exactly how it "
                f"came to claim five jobs through three gates of pipeline work")

    def green_matrix():
        matrix_path.write_text(matrix_was, encoding="utf-8")
        restored = _matrix_check()
        return ("PASS CI_MATRIX_MATCHES_REPOSITORY" in restored,
                f"{restored.splitlines()[0] if restored else 'no verdict'} — the "
                f"committed matrix equals a fresh generation, and every count in it is "
                f"derived rather than typed")

    try:
        control("NC-M3D-012  the CI matrix stops describing the pipeline",
                "", red_matrix, green_matrix)
    finally:
        matrix_path.write_text(matrix_was, encoding="utf-8")

    # NC-M3D-013 — a control the suites prove and no document describes.
    #
    # The reverse direction was already caught: a control described and never proved shows
    # as "not proven" in the evidence report and fails the build. A control PROVED and
    # described nowhere was invisible, and it is the direction that makes a stated count
    # wrong — the count comes from the registry, so a control outside it is a control the
    # evidence report, the CI matrix and the red-before-green step all fail to mention.
    sys.path.insert(0, str(REPO / "tools"))
    import controls as registry                                   # noqa: PLC0415

    def red_undescribed():
        planted = Path(CONTEXT["control_log_dir"])
        (planted / "m3d.log").write_text(
            "  [PASS] (asserted) NC-M9Z-001  a control nobody wrote down — RED with the "
            "defect planted\n"
            "  [PASS] (asserted) NC-M9Z-001  a control nobody wrote down — GREEN after "
            "revert\n", encoding="utf-8")
        try:
            registry.check_against_run(planted)
            return (False, "the registry accepted a control it has never heard of")
        except registry.ControlDrift as refused:
            return ("CONTROL_UNDESCRIBED" in str(refused),
                    f"{str(refused).splitlines()[0][:200]} — the run proved it and every "
                    f"document that counts controls counts the registry, so it would "
                    f"have gone unmentioned everywhere")

    def green_undescribed():
        planted = Path(CONTEXT["control_log_dir"])
        (planted / "m3d.log").write_text(
            "".join(f"  [PASS] (asserted) {identifier}  described — {marker} here\n"
                    for identifier, _p, _s, suite in registry.CONTROLS if suite == "m3d"
                    for marker in ("RED", "GREEN")), encoding="utf-8")
        for suite in {c[3] for c in registry.CONTROLS} - {"m3d"}:
            (planted / f"{suite}.log").write_text(
                "".join(f"  [PASS] {identifier}  described — {marker} here\n"
                        for identifier, _p, _s, owner in registry.CONTROLS
                        if owner == suite for marker in ("RED", "GREEN")),
                encoding="utf-8")
        try:
            registry.check_against_run(planted)
            return (True, f"all {registry.count()} registered controls accounted for, "
                          f"and no identifier in the logs that the registry cannot name")
        except registry.ControlDrift as refused:
            return (False, str(refused)[:200])

    import tempfile
    with tempfile.TemporaryDirectory(prefix="m3d-controls-") as tmp:
        CONTEXT["control_log_dir"] = tmp
        control("NC-M3D-013  a control the suites prove and no document describes",
                "", red_undescribed, green_undescribed)



# ===========================================================================
# main
# ===========================================================================

def main() -> int:
    print("=" * 74)
    print("M3-D VERIFICATION — the waiter surface, terminals, override and handover")
    print(f"real PostgreSQL, real compiled service, real Chromium "
          f"(running on {platform.system()})")
    print("evidence encoding: UTF-8")
    print()
    print("  (measured) = read out of a real browser's own layout after it rendered")
    print("  (asserted) = read from source, from a payload, or from the database")
    print()
    print("=" * 74)

    fx.seed()
    print("fixtures seeded: a manager who can approve, a waiter who cannot, two "
          "terminals and the outlet's fast picks")

    # One item and variant both channels order, so the matrix asks both the same question.
    pair = rows(f"""
        SELECT i.id::text, v.id::text
        FROM menu.sellable_item i
        JOIN menu.item_variant v ON v.item_id = i.id AND v.is_default AND v.status = 'active'
        WHERE i.tenant_id = '{fx.TENANT}' AND i.status = 'active'
        ORDER BY i.item_code LIMIT 1;""")
    if not pair:
        print("FAIL PREREQUISITE_ABSENT: no sellable item to order", file=sys.stderr)
        return 1
    CONTEXT["item"], CONTEXT["variant"] = pair[0][0], pair[0][1]

    sync_and_build()

    with Service(APP) as service:
        CONTEXT["base_url"] = f"http://127.0.0.1:{service.port}"
        CONTEXT["service_log"] = service.logs

        section_terminals()
        section_same_rules_structurally()
        section_same_rules_behaviourally()
        section_allergy_parity()
        section_role_home_and_search()
        section_override()
        section_handover()
        section_staff_surface()
        section_governance()
        section_controls()
        section_generator_controls()

    passed = sum(1 for _n, ok, _d, _e in results if ok)
    failed = [(name, detail) for name, ok, detail, _e in results if not ok]
    # DERIVED from the run, never tallied by hand.
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
        print("FAIL M3D_VERIFICATION")
        return 1
    print("PASS M3D_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
