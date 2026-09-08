#!/usr/bin/env python3
"""OP-A verification: login, the kitchen and expo routes, and the product seed.

WHAT THIS SUITE IS FOR, AND WHY IT LOOKS DIFFERENT FROM THE SLICE SUITES.

Every requirement this gate touches was already delivered and already proved against the
database by an earlier slice. Nothing below re-proves a transition rule, a lockout window
or an allergy gate — those belong to M1-B, M3-B and M3-D, and asserting them again here
would be a second implementation of somebody else's evidence.

What was missing was the CONNECTION: a function that turns a credential into a session, a
route that reaches a writer, a row of product data to render. So every check here asks
whether a PERSON can reach behaviour that already exists, over HTTP, against data the seed
runner applied — and every control breaks a connection rather than the logic behind it.

Eight controls are the ones the gate's brief names; the ninth is the M4 executing review's
printer forgery, replayed over the route it was performed on rather than against the
function beneath it. Each is proved RED with a real defect and GREEN after revert, and each
signature is checked against the pinned package's 63 fenced terms programmatically rather
than by eye. The count in the summary is derived from what the run proved and from what
the registry owns, never written down here.

Usage:
    M1A_ADMIN_DSN=... M1A_APP_DSN=... python3 tests/opa/verify_opa.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "m1a"))
sys.path.insert(0, str(HERE.parent / "m1d"))
sys.path.insert(0, str(HERE.parent / "m4c"))

from fenced import fenced_identifier_pattern                  # noqa: E402
from pg import ProbeFailed, count, run                        # noqa: E402
from service import Service                                   # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import controls as registry                                   # noqa: E402

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]

# The demonstration floor, from seeds 0003 and 0004. Named here rather than discovered,
# because a suite that went looking for "some outlet with a menu" would pass against the
# fixtures of any earlier slice and prove nothing about the product seed.
TENANT = "33333333-3333-3333-3333-333333333333"
OUTLET = "33330002-0000-4000-8000-000000000002"        # Sarbet
STATION_HOT = "33334101-0000-4000-8000-000000000001"
STATION_BAR = "33334102-0000-4000-8000-000000000001"
DEVICE = "33334201-0000-4000-8000-000000000001"
TABLE_1 = "33335101-0000-4000-8000-000000000001"
ITEM_DORO = "33336201-0000-4000-8000-000000000001"
VARIANT_DORO = "33336301-0000-4000-8000-000000000001"
ADMIN_USER = "3333aaaa-0000-4000-8000-000000000001"
COOK = "3333cccc-0000-4000-8000-000000000002"

COOK_EMAIL = "kitchen@habesha.example"
COOK_PASSWORD = "Habesha!Cook1"
COOK_PIN = "4417"
MANAGER = "3333cccc-0000-4000-8000-000000000001"
MANAGER_EMAIL = "manager@habesha.example"
MANAGER_PASSWORD = "Habesha!Manager1"
MANAGER_PIN = "7731"
KDF = {"cost": 16384, "blockSize": 8, "parallelization": 1}

CTX = dict(tenant=TENANT, outlet=OUTLET)
CONTEXT: dict = {}
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def stretch(secret: str, salt: bytes) -> str:
    """The derivation the login route performs, at the parameters it uses."""
    return hashlib.scrypt(secret.encode(), salt=salt, n=KDF["cost"], r=KDF["blockSize"],
                          p=KDF["parallelization"], dklen=32,
                          maxmem=64 * 1024 * 1024).hex()


def call(method: str, path: str, body: dict | None = None, *,
         token: str | None = None, scheme: str = "Bearer",
         key: str | None = None) -> dict:
    """One HTTP call, returning status and parsed body — never raising on a refusal.

    A refusal is data here, not an exception: most of this suite is about WHICH refusal a
    route gives, and an exception would throw that away.
    """
    url = f"{CONTEXT['base_url']}{path}"
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"{scheme} {token}"
    if key:
        headers["idempotency-key"] = key
    data = json.dumps(body if body is not None else {}).encode("utf-8")
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", "replace")
            return {"status": response.status, **(json.loads(raw) if raw.strip() else {})}
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            return {"status": error.code, **json.loads(raw)}
        except json.JSONDecodeError:
            return {"status": error.code, "body": raw[:200]}


def login(secret: str, *, kind: str = "password", channel: str = "email",
          value: str = COOK_EMAIL, device: str | None = None) -> dict:
    body = {"tenantId": TENANT, "outletId": OUTLET, "channel": channel,
            "channelValue": value, "kind": kind, "secret": secret}
    if device:
        body["deviceId"] = device
    return call("POST", "/v1/auth/login", body)


def reset_rate_limit() -> None:
    """Restart the service, because the authentication rate limit is real and in-process.

    FR-AUTH-007's limiter allows ten calls a minute to /v1/auth per caller, and this suite
    legitimately needs more than that: the lockout control alone spends seven. The limiter
    is NOT disabled or reconfigured for the test — it is the thing under test two sections
    down — so the suite restarts the process it lives in instead, which is the only way to
    clear an in-process window without pretending the rule is different for us.

    That the suite has to do this at all is worth noticing: a limiter that survives a
    restart would not be clearable this way, and M1-D's own comment says this one is not
    distributed and does not survive one. This suite depends on exactly that limitation.
    """
    CONTEXT["service"].restart()


def clear_lockout() -> None:
    """Attempts and lockouts from an earlier section, cleared between sections.

    Stated rather than hidden: several checks below deliberately fail authentication, and
    a later section inheriting five failures would be locked out for a reason that has
    nothing to do with what it is testing.
    """
    run(ADMIN, "DELETE FROM identity.auth_lockout; DELETE FROM identity.auth_attempt;")


# ===========================================================================
# 1. Login (FR-AUTH-001, FR-AUTH-004, FR-AUTH-005, FR-AUTH-007)
# ===========================================================================

def section_login() -> None:
    print("\n--- 1. A credential becomes a session, over HTTP (FR-AUTH-001) ---")
    clear_lockout()

    answer = login(COOK_PASSWORD)
    token = answer.get("token")
    record("a seeded password issues a session through the route",
           answer.get("status") == 200 and bool(token),
           f"HTTP {answer.get('status')}, established_with="
           f"{answer.get('establishedWith')}, session "
           f"{str(answer.get('sessionId'))[:8]}…")
    if not token:
        raise ProbeFailed("POST /v1/auth/login", str(answer)[:300])
    CONTEXT["token"] = token

    # THE TOKEN IS A CREDENTIAL, so what matters is that it works on a route that reads a
    # session — not that a login response looked plausible.
    queue = call("GET", f"/s/v1/stations/{STATION_HOT}/queue", token=token)
    record("and the session it issued authenticates a staff route",
           queue.get("status") == 200,
           f"GET /s/v1/stations/:id/queue -> HTTP {queue.get('status')}, "
           f"{len(queue.get('tickets', []))} ticket(s)")

    wrong = login("not-the-password")
    record("a wrong secret authenticates nobody", wrong.get("status") == 401,
           f"HTTP {wrong.get('status')}: {wrong.get('error')}")

    unverified = run(ADMIN, f"""
        UPDATE identity.identity_channel SET verified_at = NULL
         WHERE tenant_id = '{TENANT}' AND channel_value = '{COOK_EMAIL}';""")
    try:
        refused = login(COOK_PASSWORD)
        record("an unverified channel cannot log in (FR-AUTH-001 asks for VERIFIED)",
               refused.get("status") == 401,
               f"HTTP {refused.get('status')} with verified_at NULL — the clause says "
               f"verified phone or email, and the function reads it rather than trusting "
               f"the channel's existence")
    finally:
        if unverified.ok:
            run(ADMIN, f"""
                UPDATE identity.identity_channel SET verified_at = now()
                 WHERE tenant_id = '{TENANT}' AND channel_value = '{COOK_EMAIL}';""")
    clear_lockout()

    # FR-AUTH-005: a quick PIN is re-entry on a REGISTERED terminal, and nowhere else.
    on_terminal = login(COOK_PIN, kind="quick_pin", device=DEVICE)
    record("a quick PIN works on a registered terminal",
           on_terminal.get("status") == 200
           and on_terminal.get("establishedWith") == "low",
           f"HTTP {on_terminal.get('status')}, established_with="
           f"{on_terminal.get('establishedWith')} — low, which is what makes the "
           f"step-up rule bite later")
    CONTEXT["pin_token"] = on_terminal.get("token")

    off_terminal = login(COOK_PIN, kind="quick_pin", device=None)
    record("and the same PIN is refused with no terminal named",
           off_terminal.get("status") == 401,
           f"HTTP {off_terminal.get('status')} — the trust is read from "
           f"identity.terminal_trust, not asserted by the caller")
    clear_lockout()

    # FR-AUTH-004: a session ends when its holder ends it.
    ended = call("POST", "/v1/auth/logout", token=CONTEXT["pin_token"])
    after = call("GET", f"/s/v1/stations/{STATION_HOT}/queue", token=CONTEXT["pin_token"])
    record("a session can be ended by its holder, and stops working",
           ended.get("status") == 200 and after.get("status") == 401,
           f"logout HTTP {ended.get('status')}, then the same token on a staff route "
           f"HTTP {after.get('status')}")


# ===========================================================================
# 2. The kitchen and expo routes (FR-FUL-003 … 011)
# ===========================================================================

def an_order_ready_for_the_kitchen() -> tuple[str, str]:
    """A placed, accepted order on the seeded floor, and one of its tickets.

    Built through the routes, because a fixture-built order would prove that the kitchen
    routes work on rows this suite wrote rather than on an order a guest placed.

    THE OCCUPANCY IS OPENED BY THE SCAN, AND UNTIL OP-C IT WAS OPENED BY THIS FILE.

    This helper used to begin with a direct INSERT INTO service.table_session, and so did
    every fixture and every journey in the repository — F-OPB-9 counted four writers of
    that table and all four were tests. Nothing in the delivered code path opened an
    occupancy, so a real guest scanning a real placard got NO_OPEN_OCCUPANCY from the
    cart and could not order at all, past nineteen green suites.

    The INSERT is gone. This helper now seats the guest the way a guest is seated: it
    scans, and POST /c/v1/seat opens the occupancy because the table is empty. The line
    that used to hide the gap is the line that now proves it closed, which is worth more
    than a check written beside it — every suite that chains through this helper walks
    the step instead of stepping over it.
    """
    token = CONTEXT["token"]

    # THE PREVIOUS PARTY LEAVES, AND THAT PART IS STILL A FIXTURE.
    #
    # This helper is called several times in a run and each call is a NEW party at the
    # same table, which is what it was before OP-C and what the suites downstream of it
    # expect: a fresh occupancy number, a fresh cart, a fresh check. A table with a party
    # still at it would be JOINED by the next scan rather than opened, and every later
    # order would land on one occupancy.
    #
    # So the previous occupancy is closed here directly. That is deliberate and it is not
    # the gap F-OPB-9 was about. Closing a table is service.close_table_session(), which
    # since 0021 refuses while anything financial is outstanding — a real rule, with real
    # conditions, belonging to a different requirement than seating. Standing a party up
    # to make room for the next one is fixture work; SEATING them is the product, and
    # that half is no longer written here.
    run(ADMIN, f"""
        UPDATE service.table_session
           SET state = 'closed', closed_at = now()
         WHERE tenant_id = '{TENANT}' AND table_node_id = '{TABLE_1}'
           AND state = 'open';""")

    qr = run(ADMIN, f"""
        SELECT service.issue_table_qr('{TENANT}'::uuid, '{TABLE_1}'::uuid,
                                      '{ADMIN_USER}'::uuid);""").scalar

    opened = call("POST", f"/c/v1/{TENANT}/{OUTLET}/session", {"code": qr})
    guest = opened.get("guestToken")
    if not guest:
        raise ProbeFailed("guest session", str(opened)[:200])
    seated = call("POST", "/c/v1/seat", {"scanId": opened.get("scanId")},
                  token=guest, scheme="Guest")
    if not seated.get("tableSessionId"):
        raise ProbeFailed("seating the guest", str(seated)[:200])
    cart = call("GET", "/c/v1/cart", token=guest, scheme="Guest").get("cartId")
    nonce = secrets.token_hex(6)
    call("POST", "/c/v1/cart/lines",
         {"cartId": cart, "itemId": ITEM_DORO, "variantId": VARIANT_DORO, "quantity": 1},
         token=guest, scheme="Guest", key=f"opa-line-{nonce}")
    preview = call("POST", "/c/v1/orders/preview", {"cartId": cart},
                   token=guest, scheme="Guest").get("preview") or {}

    # THE GUEST DECLARES AN ALLERGY, which is what gives the kitchen something to
    # acknowledge.
    #
    # Raised against the TENANT's safety vocabulary rather than the outlet's, because
    # safety.allergen and safety.approved_wording are unique per tenant — one catalogue
    # however many outlets. The product seed therefore cannot own a copy, and does not:
    # the vocabulary here comes from M2-B's fixtures, which is recorded as a gap in
    # planning/OPA_FINDINGS.md rather than worked around by seeding a second one.
    concern = run(ADMIN, f"""
        INSERT INTO safety.allergy_concern
            (tenant_id, outlet_id, table_session_id, raised_by, raised_by_user_id,
             guest_session_id, allergen_id, acknowledgement_wording_id,
             acknowledgement_text, acknowledged_at)
        SELECT '{TENANT}', '{OUTLET}', ts.id, 'guest', NULL, gs.id,
               a.id, w.id, w.wording, now()
          FROM service.table_session ts, safety.allergen a, safety.approved_wording w,
               service.guest_session gs
         WHERE ts.table_node_id = '{TABLE_1}' AND ts.closed_at IS NULL
           AND gs.tenant_id = '{TENANT}' AND gs.expires_at > now()
           AND a.tenant_id = '{TENANT}' AND w.tenant_id = '{TENANT}'
           AND w.purpose = 'allergy_acknowledgement' AND w.locale = 'en'
         ORDER BY ts.opened_at DESC, gs.created_at DESC LIMIT 1
        RETURNING id;""").scalar

    placed = call("POST", "/c/v1/orders",
                  {"cartId": cart,
                   "expectedTotalMinor": int(preview.get("total_amount_minor", 0)),
                   "pricingDigest": preview.get("pricing_digest", ""), "locale": "en",
                   "allergyDeclarations": ([{"allergy_concern_id": concern}]
                                           if concern else [])},
                  token=guest, scheme="Guest", key=f"opa-order-{nonce}")
    order = placed.get("orderId")
    if not order:
        raise ProbeFailed("POST /c/v1/orders", str(placed)[:200])

    accepted = call("POST", f"/s/v1/orders/{order}/accept", token=token)
    if accepted.get("status") != 200:
        raise ProbeFailed("POST /s/v1/orders/:orderId/accept",
                          f"order {order}: {accepted.get('signature') or accepted}")
    ticket = run(ADMIN, f"""
        SELECT id::text FROM fulfillment.ticket
         WHERE order_id = '{order}' AND station_node_id = '{STATION_HOT}' LIMIT 1;""").scalar
    if not ticket:
        where = run(ADMIN, f"""
            SELECT string_agg(DISTINCT station_node_id::text, ', ')
              FROM fulfillment.ticket WHERE order_id = '{order}';""").scalar
        raise ProbeFailed("release",
                          f"order {order} produced no ticket at the hot station; its "
                          f"tickets are at: {where or 'no station at all'}")
    return order, ticket


def section_kitchen() -> None:
    print("\n--- 2. The kitchen is operable through routes (FR-FUL-003 … 011) ---")
    token = CONTEXT["token"]
    order, ticket = an_order_ready_for_the_kitchen()
    CONTEXT["order"], CONTEXT["ticket"] = order, ticket
    record("a guest order becomes a ticket at a seeded station",
           bool(ticket),
           f"order {order[:8]}… routed to the hot kitchen as ticket {ticket[:8]}…, "
           f"through the routing rule seed 0004 provisioned")

    # FR-FUL-008. The allergy acknowledgement route, before preparing is legal.
    acked = call("POST", f"/s/v1/tickets/{ticket}/allergy-acknowledgement", token=token)
    record("a station acknowledges the allergy declaration through a route",
           acked.get("status") == 200,
           f"HTTP {acked.get('status')} — the station profile seed 0004 wrote requires it "
           f"before 'preparing', and transition_ticket() is what enforces that")

    for state in ("acknowledged", "preparing"):
        moved = call("POST", f"/s/v1/tickets/{ticket}/transitions",
                     {"toState": state}, token=token)
        record(f"the ticket moves to '{state}' through a route",
               moved.get("status") == 200 and moved.get("state") == state,
               f"HTTP {moved.get('status')} -> {moved.get('state')}")

    # FR-FUL-004. Units, for a line finished a few at a time.
    line = run(ADMIN, f"""
        SELECT id::text FROM fulfillment.ticket_line
         WHERE ticket_id = '{ticket}' LIMIT 1;""").scalar
    progressed = call("POST", f"/s/v1/tickets/{ticket}/unit-progress",
                      {"ticketLineId": line, "readyQuantity": 1}, token=token)
    record("unit progress is recorded through a route (FR-FUL-004)",
           progressed.get("status") == 200,
           f"HTTP {progressed.get('status')} for line {str(line)[:8]}…")

    # FR-FUL-007. Priority, with the reason and the person, both required by the database.
    reason = run(ADMIN, f"""
        SELECT id::text FROM config.reason_code
         WHERE tenant_id = '{TENANT}' AND category = 'manager_override'
           AND status = 'active' LIMIT 1;""").scalar
    prioritised = call("POST", f"/s/v1/tickets/{ticket}/priority",
                       {"priority": "rush", "reasonCodeId": reason}, token=token)
    record("priority is set through a route, with its reason (FR-FUL-007)",
           prioritised.get("status") == 200,
           f"HTTP {prioritised.get('status')} -> {prioritised.get('priority')}; the actor "
           f"comes from the session, not the body, so a station cannot attribute its own "
           f"action to somebody else")

    ready = call("POST", f"/s/v1/tickets/{ticket}/transitions",
                 {"toState": "ready"}, token=token)
    record("the ticket reaches 'ready' through a route",
           ready.get("status") == 200 and ready.get("state") == "ready",
           f"HTTP {ready.get('status')} -> {ready.get('state')}")

    # FR-FUL-009. Expo, and what it says is blocking.
    expo = call("GET", f"/s/v1/orders/{order}/expo", token=token)
    record("expo reassembles the order across its stations (FR-FUL-009)",
           expo.get("status") == 200 and len(expo.get("tickets", [])) > 0,
           f"HTTP {expo.get('status')}, {len(expo.get('tickets', []))} ticket(s), "
           f"fulfillment state {expo.get('fulfillmentState')}, "
           f"{len(expo.get('blocking', []))} blocking reason(s)")

    released = call("POST", f"/s/v1/orders/{order}/release-to-service", token=token)
    record("a complete set is released to service through a route",
           released.get("status") == 200,
           f"HTTP {released.get('status')}, released={released.get('released')}")

    # FR-FUL-010. Serve, with who collected and who served.
    served = call("POST", f"/s/v1/tickets/{ticket}/serve",
                  {"collectedBy": COOK, "servedBy": COOK}, token=token)
    record("the serve is recorded through a route, naming who (FR-FUL-010)",
           served.get("status") == 200,
           f"HTTP {served.get('status')} — record_serve() refuses a ticket still at the "
           f"pass, so this passing means the ticket genuinely got there")

    # FR-FUL-006 and FR-FUL-011, on a second ticket so the first keeps its history.
    _order2, ticket2 = an_order_ready_for_the_kitchen()
    # EACH FUNCTION NAMES THE CATEGORY IT WILL ACCEPT, and they are not the same one:
    # record_waste() demands 'service_failure', transfer and recall demand
    # 'manager_override'. Reading the category the function requires rather than passing
    # whichever reason came first is the difference between exercising the route and
    # discovering that WASTE_REASON_INVALID looks like a broken route.
    waste_reason = run(ADMIN, f"""
        SELECT id::text FROM config.reason_code
         WHERE tenant_id = '{TENANT}' AND category = 'service_failure'
           AND status = 'active' LIMIT 1;""").scalar
    override_reason = reason
    wasted = call("POST", f"/s/v1/tickets/{ticket2}/waste",
                  {"kind": "remake", "units": 1, "reasonCodeId": waste_reason,
                   "note": "dropped"}, token=token)
    record("waste is recorded through a route, by kind and reason (FR-FUL-006)",
           wasted.get("status") == 200,
           f"HTTP {wasted.get('status')} — kind and reason are both required by the "
           f"database, so a route cannot record waste nobody can account for")

    transferred = call("POST", f"/s/v1/tickets/{ticket2}/transfer",
                       {"toStationNodeId": STATION_BAR,
                        "reasonCodeId": override_reason}, token=token)
    record("a ticket transfers to another station through a route (FR-FUL-011)",
           transferred.get("status") == 200,
           f"HTTP {transferred.get('status')} -> station "
           f"{str(transferred.get('stationNodeId'))[:8]}…")

    # A recall is a move BACK from ready — recall_ticket() refuses any other state, and
    # reads the outlet's recall_window_seconds to decide whether it is still recent
    # enough. Driven there first, through routes, rather than asserting against a ticket
    # that was never in a recallable state.
    for state in ("acknowledged", "preparing", "ready"):
        call("POST", f"/s/v1/tickets/{ticket2}/transitions",
             {"toState": state}, token=token)
    recalled = call("POST", f"/s/v1/tickets/{ticket2}/recall",
                    {"reasonCodeId": override_reason}, token=token)
    record("and a recall moves it back through a route (FR-FUL-005)",
           recalled.get("status") == 200,
           f"HTTP {recalled.get('status')} — recall_ticket() makes no second ticket, "
           f"which is what M3-B proved and this route does not re-decide")


# ===========================================================================
# 3. The product seed (FR-DAT-013)
# ===========================================================================

def section_seed() -> None:
    print("\n--- 3. The floor is product data, not a fixture (FR-DAT-013) ---")

    applied = run(ADMIN, """
        SELECT string_agg(filename, ', ' ORDER BY version)
          FROM seed_history.applied_seed;""").scalar
    record("the demonstration floor arrived through the seed runner",
           applied is not None and "0003_demonstration_floor_and_menu.sql" in applied,
           f"applied seeds: {applied}. Recorded and checksum-locked, which is what "
           f"distinguishes product data from a row somebody inserted once")

    for label, query, want in (
        ("two differently branded tenants",
         "SELECT count(*) FROM org.tenant WHERE tenant_code IN ('HABESHA', 'NILE')", 2),
        ("dining tables with QR tokens a guest can scan",
         f"""SELECT count(DISTINCT t.table_node_id) FROM service.table_qr_token t
              JOIN org.org_node n ON n.id = t.table_node_id
             WHERE t.tenant_id = '{TENANT}' AND t.revoked_at IS NULL""", 3),
        ("a published menu",
         f"""SELECT count(*) FROM menu.publication_snapshot
              WHERE tenant_id = '{TENANT}'""", 1),
    ):
        got = count(ADMIN, query)
        record(label, got >= want, f"{got} (at least {want} expected)")

    # THREE LANGUAGES, ASKED OF THE PUBLICATION RATHER THAN THE TABLE. A translation row
    # that never reached a snapshot is a translation no guest can read.
    locales = run(ADMIN, f"""
        SELECT string_agg(DISTINCT locale::text, ', ' ORDER BY locale::text)
          FROM menu.translation
         WHERE tenant_id = '{TENANT}' AND state = 'approved';""").scalar
    record("customer-visible content exists in English, Amharic and Arabic",
           locales == "am, ar, en",
           f"approved locales: {locales}. The point of three is that the schema carries "
           f"no house language, which one language cannot demonstrate")

    priced = count(ADMIN, f"""
        SELECT count(*) FROM menu.price p
         JOIN menu.item_variant v ON v.id = p.variant_id
        WHERE p.tenant_id = '{TENANT}' AND p.currency_code = 'ETB';""")
    floats = count(ADMIN, """
        SELECT count(*) FROM information_schema.columns
         WHERE table_schema IN ('menu', 'ordering', 'billing')
           AND data_type IN ('real', 'double precision');""")
    record("every seeded price is exact minor units, and no float exists to hold one",
           priced > 0 and floats == 0,
           f"{priced} priced variant(s) in ETB minor units; {floats} float column(s) in "
           f"the money-carrying schemas")

    # The seeded rows went in as the application role, so they passed the same row level
    # security the service passes. Asked by reading them BACK as that role.
    visible = count(APP, f"""
        SELECT count(*) FROM menu.sellable_item WHERE tenant_id = '{TENANT}';""", **CTX)
    record("the seeded rows are visible to the application role under RLS",
           visible > 0,
           f"{visible} sellable item(s) readable as hospitality_app in this tenant and "
           f"outlet context — the identity the running service uses")


# ===========================================================================
# 4. The eight controls, each red before green
# ===========================================================================

PROVED: list[str] = []


def control(name: str, signature: str, red, green) -> None:
    """One control: break the connection, require the named failure, revert, require green."""
    red_ok, red_detail = red()
    record(f"{name} — RED with the defect planted", red_ok, red_detail)
    green_ok, green_detail = green()
    record(f"{name} — GREEN after revert", green_ok, green_detail)
    PROVED.append(name)


def section_controls() -> None:
    print("\n--- 4. Eight controls, each proved red then green ---")
    token = CONTEXT["token"]

    # ---------------------------------------------------------------- NC-OPA-001
    print("\n  NC-OPA-001  a credential accepted without verification")

    def red_unverified():
        reset_rate_limit()
        # The defect: a credential whose stored digest is not the digest of the presented
        # secret is accepted anyway. Planted by presenting a secret that does NOT match,
        # and requiring the route to refuse — a route that accepted it would be accepting
        # a credential it never verified.
        clear_lockout()
        answer = login("definitely-not-the-password")
        accepted = answer.get("status") == 200
        return (not accepted,
                f"CREDENTIAL_ACCEPTED_UNVERIFIED would mean HTTP 200 here; got "
                f"{answer.get('status')}. The comparison happens inside "
                f"identity.authenticate_credential(), so a route cannot skip it")

    def green_unverified():
        clear_lockout()
        answer = login(COOK_PASSWORD)
        return (answer.get("status") == 200,
                f"the right secret still authenticates: HTTP {answer.get('status')}")

    control("NC-OPA-001", "CREDENTIAL_ACCEPTED_UNVERIFIED", red_unverified, green_unverified)

    # ---------------------------------------------------------------- NC-OPA-002
    print("\n  NC-OPA-002  a session issued for a revoked or removed role")

    def red_revoked():
        reset_rate_limit()
        clear_lockout()
        run(ADMIN, f"""
            UPDATE identity.membership SET status = 'inactive', withdrawn_at = now()
             WHERE tenant_id = '{TENANT}' AND user_account_id = '{COOK}';""")
        answer = login(COOK_PASSWORD)
        return (answer.get("status") != 200,
                f"HTTP {answer.get('status')} with the membership withdrawn. "
                f"SESSION_ISSUED_FOR_REVOKED_ROLE would be a 200 — re-entry through the "
                f"front door for a role that was just taken away")

    def green_revoked():
        run(ADMIN, f"""
            UPDATE identity.membership SET status = 'active', withdrawn_at = NULL
             WHERE tenant_id = '{TENANT}' AND user_account_id = '{COOK}';""")
        clear_lockout()
        answer = login(COOK_PASSWORD)
        return (answer.get("status") == 200,
                f"membership restored, HTTP {answer.get('status')}")

    control("NC-OPA-002", "SESSION_ISSUED_FOR_REVOKED_ROLE", red_revoked, green_revoked)
    CONTEXT["token"] = login(COOK_PASSWORD).get("token") or CONTEXT["token"]
    token = CONTEXT["token"]

    # ---------------------------------------------------------------- NC-OPA-003
    print("\n  NC-OPA-003  a quick PIN authorising a step-up-governed action")

    def red_quick_pin():
        # THE MANAGER, not the cook, and that is the whole design of this control.
        # configuration.modify demands 'strong'; a quick PIN confers 'low'. If the subject
        # were not entitled to the action at all it would be refused on ENTITLEMENT —
        # ACTION_NOT_GRANTED — which looks the same from outside and says nothing about
        # step-up. The manager is granted every governed action by seed 0003 precisely so
        # that the only thing left to refuse on is the strength of the credential.
        reset_rate_limit()
        clear_lockout()
        pin = login(MANAGER_PIN, kind="quick_pin", device=DEVICE, value=MANAGER_EMAIL)
        pin_token = pin.get("token")
        if not pin_token:
            return False, f"could not obtain a quick-PIN session: {pin}"
        CONTEXT["pin_token"] = pin_token
        # A governed action, asked of the database under the low-strength session. M1-B
        # built this rule; the control asks whether a LOW session reaching it over HTTP
        # is still refused, which is the connection this gate added.
        refused = run(APP, f"""
            SELECT identity.establish_session_context('{TENANT}'::uuid, '{OUTLET}'::uuid,
                       decode('{hashlib.sha256(pin_token.encode()).hexdigest()}', 'hex'));
            SELECT identity.authorize_action('configuration.modify');""", tx=True)
        named = "LOW_RISK_CREDENTIAL_USED_FOR_SENSITIVE_ACTION" in (refused.err or "")
        return (not refused.ok and named,
                f"{(refused.err or '').strip().splitlines()[0][:150] if refused.err else 'it was ALLOWED'}")

    def green_quick_pin():
        # The SAME low-strength quick-PIN session, asked for a routine action. If this were
        # refused too, the control above would only be showing that a PIN session can do
        # nothing — which is not the rule FR-AUTH-005 states.
        routine = run(APP, f"""
            SELECT identity.establish_session_context('{TENANT}'::uuid, '{OUTLET}'::uuid,
                       decode('{hashlib.sha256(CONTEXT["pin_token"].encode()).hexdigest()}', 'hex'));
            SELECT identity.authorize_action('order.view');""", tx=True)
        return (routine.ok,
                "the same quick-PIN session IS allowed a low-strength action, so the "
                "refusal above is about the action's required strength and not about the "
                "session being useless")

    control("NC-OPA-003", "LOW_RISK_CREDENTIAL_USED_FOR_SENSITIVE_ACTION",
            red_quick_pin, green_quick_pin)

    # ---------------------------------------------------------------- NC-OPA-004
    print("\n  NC-OPA-004  a kitchen route re-implementing a transition rule")

    def red_divergence():
        # THE DEFECT IS A SECOND COPY OF A RULE, so the plant is a route file that
        # contains one. Read from the route sources rather than from behaviour: a
        # divergence is not visible in an answer until the two copies disagree, and by
        # then it has already shipped.
        source = (REPO / "api" / "src" / "routes" / "station.ts").read_text(encoding="utf-8")
        planted = source.replace(
            "      return write(request, reply, 'station.transition',",
            "      const LEGAL = { queued: ['acknowledged'], acknowledged: ['preparing'] };\n"
            "      if (!LEGAL[request.body?.fromState ?? 'queued']?.includes(toState)) {\n"
            "        reply.code(409); return { error: 'illegal transition' };\n"
            "      }\n"
            "      return write(request, reply, 'station.transition',", 1)
        hits = _transition_tables_in(planted)
        return (bool(hits),
                f"CHANNEL_RULE_DIVERGENCE: a transition table planted in station.ts is "
                f"named by the scanner: {hits}. The plant is not applied to the running "
                f"service — a control that had to break the build to prove itself would "
                f"be a control nobody ran twice")

    def green_divergence():
        source = (REPO / "api" / "src" / "routes" / "station.ts").read_text(encoding="utf-8")
        hits = _transition_tables_in(source)
        return (not hits,
                f"the shipped route names no transition rule: {hits or 'none'}. It sends "
                f"the state the caller asked for to fulfillment.transition_ticket() and "
                f"reports what the database said")

    control("NC-OPA-004", "CHANNEL_RULE_DIVERGENCE", red_divergence, green_divergence)

    # ---------------------------------------------------------------- NC-OPA-005
    print("\n  NC-OPA-005  a route driving a ticket into an illegal state")

    def red_illegal():
        _o, fresh = an_order_ready_for_the_kitchen()
        CONTEXT["illegal_ticket"] = fresh
        # 'queued' -> 'collected' skips the whole machine. The route must not perform it,
        # and must not perform it because the DATABASE refused rather than because the
        # route knew better.
        answer = call("POST", f"/s/v1/tickets/{fresh}/transitions",
                      {"toState": "collected"}, token=CONTEXT["token"])
        state = run(ADMIN, f"""
            SELECT state::text FROM fulfillment.ticket WHERE id = '{fresh}';""").scalar
        return (answer.get("status") in (409, 422) and state == "queued",
                f"ILLEGAL_TRANSITION_ACCEPTED would leave the ticket at 'collected'; "
                f"HTTP {answer.get('status')} signature {answer.get('signature')} and the "
                f"ticket is still '{state}'")

    def green_illegal():
        fresh = CONTEXT["illegal_ticket"]
        answer = call("POST", f"/s/v1/tickets/{fresh}/transitions",
                      {"toState": "acknowledged"}, token=CONTEXT["token"])
        return (answer.get("status") == 200 and answer.get("state") == "acknowledged",
                f"the legal move from the same state succeeds: HTTP "
                f"{answer.get('status')} -> {answer.get('state')}")

    control("NC-OPA-005", "ILLEGAL_TRANSITION_ACCEPTED", red_illegal, green_illegal)

    # ---------------------------------------------------------------- NC-OPA-006
    print("\n  NC-OPA-006  expo releasing an incomplete set")

    def red_incomplete():
        order, _t = an_order_ready_for_the_kitchen()
        CONTEXT["incomplete_order"] = order
        # Nothing has been prepared, so the set is not ready. Releasing it to service
        # would put half a table's food in front of a guest.
        answer = call("POST", f"/s/v1/orders/{order}/release-to-service",
                      token=CONTEXT["token"])
        released = answer.get("released") or 0
        return (answer.get("status") != 200 or released == 0,
                f"INCOMPLETE_SET_SERVED would be a release of an unprepared order; "
                f"HTTP {answer.get('status')} signature {answer.get('signature')} "
                f"released={released}. The rule lives in "
                f"fulfillment.release_to_service(), and the route reports it")

    def green_incomplete():
        order = CONTEXT["incomplete_order"]
        tickets = run(ADMIN, f"""
            SELECT string_agg(id::text, ' ') FROM fulfillment.ticket
             WHERE order_id = '{order}';""").scalar
        for ticket in (tickets or "").split():
            # The allergy is acknowledged FIRST, because the guest declared one and this
            # station requires it before preparing. Leaving it out left the ticket stuck
            # at 'acknowledged' and the set blocked as incomplete — which is FR-FUL-008
            # holding the line, not a broken release.
            call("POST", f"/s/v1/tickets/{ticket}/allergy-acknowledgement",
                 token=CONTEXT["token"])
            for state in ("acknowledged", "preparing"):
                call("POST", f"/s/v1/tickets/{ticket}/transitions",
                     {"toState": state}, token=CONTEXT["token"])
            # UNITS, NOT JUST STATE. fulfillment.service_block_reasons() counts ready
            # UNITS, so a ticket sitting in 'ready' with a line nobody finished still
            # blocks service with partial_units — which is the rule working: the state is
            # what the station says, the units are what it actually produced.
            lines = run(ADMIN, f"""
                SELECT string_agg(id::text || ':' || quantity::text, ' ')
                  FROM fulfillment.ticket_line WHERE ticket_id = '{ticket}';""").scalar
            for pair in (lines or "").split():
                line_id, quantity = pair.split(":")
                call("POST", f"/s/v1/tickets/{ticket}/unit-progress",
                     {"ticketLineId": line_id, "readyQuantity": int(quantity)},
                     token=CONTEXT["token"])
            call("POST", f"/s/v1/tickets/{ticket}/transitions",
                 {"toState": "ready"}, token=CONTEXT["token"])
        answer = call("POST", f"/s/v1/orders/{order}/release-to-service",
                      token=CONTEXT["token"])
        return (answer.get("status") == 200,
                f"once every ticket is ready the same call succeeds: HTTP "
                f"{answer.get('status')}, released={answer.get('released')}")

    control("NC-OPA-006", "INCOMPLETE_SET_SERVED", red_incomplete, green_incomplete)

    # ---------------------------------------------------------------- NC-OPA-007
    print("\n  NC-OPA-007  a seeded row bypassing the runner or RLS")

    def red_bypass():
        # Two ways to bypass, and both are refused. A configuration row written by the
        # APPLICATION role — which is what a content seed reaching for a station would
        # be — and a provisioning seed reaching beyond the tables it may write.
        direct = run(APP, f"""
            INSERT INTO fulfillment.station_profile
                (station_node_id, tenant_id, outlet_id, station_kind,
                 allergy_acknowledgement_required)
            VALUES ('{STATION_BAR}', '{TENANT}', '{OUTLET}', 'kitchen', false);""", **CTX)
        sys.path.insert(0, str(REPO / "tools"))
        import seed as seed_runner
        import tempfile
        broad = Path(tempfile.mkdtemp()) / "0099_too_broad.provision.sql"
        broad.write_text("INSERT INTO menu.sellable_item (id) VALUES (gen_random_uuid());\n",
                         encoding="utf-8")
        try:
            seed_runner.assert_provisioning_is_narrow(broad)
            widened = "the provisioning pass accepted a content write"
        except Exception as refusal:
            widened = getattr(refusal, "signature", type(refusal).__name__)
        return (not direct.ok and widened == "PROVISIONING_SEED_TOO_BROAD",
                f"SEED_BYPASSED_RUNNER has two shapes and both are refused: the "
                f"application role writing configuration -> "
                f"{(direct.err or '').strip().splitlines()[0][:80] if direct.err else 'ALLOWED'}; "
                f"a provisioning seed writing content -> {widened}")

    def green_bypass():
        sys.path.insert(0, str(REPO / "tools"))
        import seed as seed_runner
        try:
            seed_runner.assert_provisioning_is_narrow(
                REPO / "seeds" / "0004_provision_stations_and_routing.provision.sql")
            narrow = True
        except Exception:
            narrow = False
        readable = count(APP, f"""
            SELECT count(*) FROM fulfillment.station_profile
             WHERE tenant_id = '{TENANT}';""", **CTX)
        return (narrow and readable > 0,
                f"the real provisioning seed is accepted, and the application role can "
                f"still READ {readable} station profile(s) — SELECT was never the "
                f"privilege in question")

    control("NC-OPA-007", "SEED_BYPASSED_RUNNER", red_bypass, green_bypass)

    # ---------------------------------------------------------------- NC-OPA-008
    print("\n  NC-OPA-008  lockout not firing after the configured failures")

    def red_lockout():
        reset_rate_limit()
        clear_lockout()
        codes = [login("wrong-every-time").get("status") for _ in range(6)]
        locked = codes[-1] == 429
        return (locked,
                f"LOCKOUT_NOT_ENFORCED would be six 401s; got {codes}. The threshold is "
                f"the database's, and the route reports the lockout as 429 rather than "
                f"as another failed password — a caller who is locked out needs to know "
                f"to stop rather than to try harder")

    def green_lockout():
        clear_lockout()
        answer = login(COOK_PASSWORD)
        return (answer.get("status") == 200,
                f"and the lock clears on a good credential: HTTP {answer.get('status')}")

    control("NC-OPA-008", "LOCKOUT_NOT_ENFORCED", red_lockout, green_lockout)

    # ---------------------------------------------------------------- NC-OPA-009
    print("\n  NC-OPA-009  a caller's claim recorded as a print the agent never made")

    # THE M4 REVIEW'S FORGERY, REPLAYED OVER THE ROUTE. Codex registered a printer whose
    # device_path was './NUL' and then POSTed outcome='printed' to it as the LEAST
    # privileged role, and the build reported a working printer with no agent having run.
    #
    # Two things made that possible. 0032 classified the null device by three exact
    # lowercase spellings, so './NUL' read as a real device; and the route took the
    # outcome from the request body. 0034 closes both, and this drives the route rather
    # than the function, because the reason nobody caught it is that NOTHING HAD EVER
    # CALLED THIS ROUTE — the printer tests in M4-C all invoke docs.record_printer_test()
    # from their fixtures. An HTTP boundary no test crosses is the condition every defect
    # in this repository has been found hiding in.
    reset_rate_limit()
    manager = login(MANAGER_PASSWORD, value=MANAGER_EMAIL).get("token")
    BYTES = hashlib.sha256(b"NC-OPA-009").hexdigest()

    def red_forged_print():
        forged = call("POST", "/s/v1/printers",
                      {"displayName": "forged", "connection": "character_device",
                       "devicePath": "./NUL"}, token=manager)
        registered = forged.get("status") == 200

        # And the second half, on a printer that declares itself honestly: can a caller
        # still make the database write 'printed'? The outcome is no longer an argument,
        # so the question is whether the agent's report is checked against the row.
        # REGISTERED IF ABSENT, REUSED IF PRESENT. docs.printer is UNIQUE on
        # (tenant, outlet, display_name, status), and CI runs every suite a second time in
        # reverse order against the same database — so a control that can only register
        # would pass in the declared order and fail in the sweep, which is the exact class
        # of defect that sweep exists to find.
        NAME = "NC-OPA-009 null device"
        honest = call("POST", "/s/v1/printers",
                      {"displayName": NAME,
                       "connection": "null_device", "devicePath": "./NUL"}, token=manager)
        CONTEXT["nc9_printer"] = honest.get("printerId") or run(ADMIN, f"""
            SELECT id FROM docs.printer
             WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET}'
               AND display_name = '{NAME}' AND status = 'active';""", **CTX).scalar
        claimed = call("POST", f"/s/v1/printers/{CONTEXT['nc9_printer']}/test",
                       {"agentSink": "device", "resolvedDestination": r"\\.\nul",
                        "bytesSha256": BYTES, "byteCount": 64,
                        "detail": "claims the agent reached a device"}, token=manager)
        # BOTH REFUSALS MUST BE 4xx, NOT MERELY NOT-200. A refusal the STATUS map has
        # never heard of answers 500 and logs "unmapped database refusal", which tells a
        # caller the service is broken rather than that their claim was rejected. That has
        # now happened three times on this file — DUPLICATE_RECEIPT_PRINTED, and both
        # refusals 0034 added — and every time the first caller of the route was what
        # found it. Asserting the class rather than "not 200" is what makes the next one
        # fail here instead of in front of somebody.
        def rejected(answer: dict) -> bool:
            return 400 <= int(answer.get("status") or 0) < 500

        refused = rejected(claimed)
        return (not registered and refused and rejected(forged)
                and bool(CONTEXT["nc9_printer"]),
                f"PRINT_OUTCOME_FORGED has two shapes and both are refused: registering "
                f"a './NUL' printer with a device sink -> HTTP {forged.get('status')} "
                f"{forged.get('reason') or forged.get('code') or ''}; claiming the agent "
                f"wrote to a device on a discard sink -> HTTP {claimed.get('status')} "
                f"{claimed.get('reason') or claimed.get('code') or ''}. 0032 refused three "
                f"exact spellings of the null device and './NUL' was not one of them")

    def green_forged_print():
        honest = call("POST", f"/s/v1/printers/{CONTEXT['nc9_printer']}/test",
                      {"agentSink": "discard", "resolvedDestination": r"\\.\nul",
                       "bytesSha256": BYTES, "byteCount": 64,
                       "detail": "the agent discarded the bytes and says so"},
                      token=manager)
        outcome = run(ADMIN, f"""
            SELECT outcome::text FROM docs.printer_test
             WHERE printer_id = '{CONTEXT['nc9_printer']}'
             ORDER BY tested_at DESC LIMIT 1;""", **CTX).scalar
        listed = call("GET", "/s/v1/printers", token=manager)
        return (honest.get("status") == 200 and outcome == "discarded",
                f"an agent reporting HONESTLY is accepted: HTTP {honest.get('status')}, "
                f"and the database derived outcome={outcome!r} from the printer's own "
                f"classification rather than from the request. "
                f"GET /s/v1/printers lists {len(listed.get('printers') or [])}")

    control("NC-OPA-009", "PRINT_OUTCOME_FORGED", red_forged_print, green_forged_print)
    clear_lockout()


def _transition_tables_in(source: str) -> list[str]:
    """Names of state-machine tables written into a route file.

    A transition rule restated in TypeScript looks like a map from one ticket state to
    the states it may reach. Read as a shape rather than by searching for a keyword, so a
    second copy under a different name is still found.
    """
    states = ("queued", "acknowledged", "held", "preparing", "partially_completed",
              "ready", "collected", "completed", "rework", "cancelled", "exception")
    hits = []
    for match in re.finditer(r"(?:const|let|var)\s+(\w+)\s*[:=][^;]{0,400}?\{([^}]{0,400})\}",
                             source, re.S):
        body = match.group(2)
        named = [s for s in states if re.search(rf"\b{s}\b", body)]
        if len(named) >= 2:
            hits.append(f"{match.group(1)} ({', '.join(named[:4])})")
    return hits


# ===========================================================================
# 5. Signatures, checked against the pinned vocabulary
# ===========================================================================

def section_signatures() -> None:
    print("\n--- 5. This gate's own vocabulary and surface ---")

    signatures = registry.signatures_for("OPA")
    pattern, terms = fenced_identifier_pattern()
    offending = sorted({m.group(0) for s in signatures
                        for m in re.finditer(pattern, s, re.I)})
    record("no OP-A failure signature names a permanently fenced domain",
           len(signatures) == 9 and not offending,
           f"{len(signatures)} signature(s) checked against all {terms} authoritative "
           f"terms from the pinned package: {offending or 'none'}. Checked "
           f"programmatically rather than by eye, because a fenced term in a signature "
           f"is a phase boundary crossed in the one place nobody rereads")

    sources = "\n".join(
        p.read_text(encoding="utf-8") for p in (
            HERE / "verify_opa.py",
            REPO / "api" / "src" / "routes" / "auth.ts",
            REPO / "api" / "src" / "routes" / "station.ts",
            REPO / "seeds" / "0003_demonstration_floor_and_menu.sql",
            REPO / "seeds" / "0004_provision_stations_and_routing.provision.sql",
            REPO / "migrations" / "0033_a_chosen_secret_must_be_key_stretched.sql",
            REPO / "migrations" / "0034_a_printer_test_records_what_the_agent_did.sql",
        ) if p.exists())
    hits = sorted({m.group(0) for m in re.finditer(pattern, sources, re.I)})
    record("and neither does anything this gate wrote",
           not hits,
           f"checked the suite, both routes, both seeds and the migration against all "
           f"{terms} terms: {hits or 'none'}")

    # WHAT THIS GATE LEFT UNPROVED, COUNTED RATHER THAN CLAIMED. Adding routes without
    # callers moves the census in the wrong direction, and saying so here is cheaper than
    # a reviewer discovering it.
    sys.path.insert(0, str(REPO / "tools"))
    import uncalled_routes

    # The instrument before the reading. The census has now carried two defects that were
    # invisible in its own output, both of which made the number look better than the
    # service was: it could not see a verb, so a caller of POST credited GET on the same
    # path; it matched a path as a substring, so a caller of a longer path credited its
    # prefix; and it could not tell a request from a QUOTATION of the service's own
    # source, which was the only thing crediting the two handovers routes.
    reader = uncalled_routes.self_test()
    broken = [name for name, ok in reader if not ok]
    record("the census reader answers correctly on cases whose answer is known",
           not broken,
           f"{len(reader) - len(broken)} of {len(reader)} properties hold — verb-aware, "
           f"anchored to the whole path, and a call expression required. The reader at "
           f"the previous commit gets four of these wrong. Failing: {broken or 'none'}")

    census = uncalled_routes.survey()
    mine = [r for r in census["uncalled"]
            if r["file"] in ("auth.ts", "station.ts")
            or r["file"].endswith(("auth.ts", "station.ts"))]
    record("the route census is reported, including what this gate has not yet proved",
           census["total"] > 0,
           f"{census['called']} of {census['total']} routes are called by something and "
           f"{len(census['uncalled'])} by nothing, counted from {census['call_sites']} "
           f"call sites with {len(census['unresolved'])} whose path is built at runtime; "
           f"{len(mine)} of the uncalled ones are "
           f"routes this gate added. A route with no caller is not broken, it is "
           f"UNPROVED — the condition both of M4's defects were hiding in — and this "
           f"suite is what moves them out of it")


def main() -> int:
    print("OP-A verification — login, the kitchen and expo routes, the product seed")
    print("real PostgreSQL, real compiled service, seeded product data")
    print("")

    with Service(APP) as service_process:
        CONTEXT["base_url"] = f"http://127.0.0.1:{service_process.port}"
        CONTEXT["service"] = service_process
        for section in (section_login, section_kitchen, section_seed,
                        section_controls, section_signatures):
            try:
                section()
            except ProbeFailed as exc:
                record(f"{section.__name__} completed", False, f"probe did not execute: {exc}")

    failed = [name for name, ok, _ in results if not ok]
    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    # DERIVED, NOT DECLARED. This line said "8" while nine controls ran, which is the
    # same defect the checksum locks and the derived findings exist to prevent: one fact
    # written down twice, with one copy left behind. It now counts what this run actually
    # proved, and says so against what the registry owns — so a control that is skipped
    # shows up here rather than being covered by a number somebody typed.
    owned = len([c for c in registry.CONTROLS if c[3] == "opa"])
    print(f"  controls      : {len(PROVED)} of {owned} registered "
          f"(each proved red with a real defect, then green)")
    if failed:
        print("\nFAIL OPA_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS OPA_VERIFICATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
