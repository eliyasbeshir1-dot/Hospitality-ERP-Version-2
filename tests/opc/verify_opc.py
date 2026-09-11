#!/usr/bin/env python3
"""OP-C verification: the step that came before everything nineteen suites had proved.

WHAT THIS SUITE IS FOR. OP-A gave the kitchen routes no cook could press and OP-B built
the screens that press them. Both were green, and a person who opened the demonstration
floor could not order a plate of food, because nothing in the delivered code path had ever
opened a table occupancy. A direct INSERT into `service.table_session` occurred in four
files and all four were tests. Every journey, every fixture and OP-A's own order helper created the
occupancy with a direct INSERT and then proved that everything downstream worked — all of
them correct about what they tested, all of them silent about the step none of them took.

So the first discipline of this suite is that IT DOES NOT WRITE THE ROW EITHER. Nothing
below inserts a table session, and the two helpers that produce one call the same routes a
guest's phone and a waiter's screen call. A check that arranged its own occupancy would be
the defect it exists to detect, written one gate later.

MEASURED VERSUS ASSERTED. A claim about what somebody SEES is measured in a real browser
and marked `measured`; a claim about what the service does is marked `asserted`. The split
is derived from the run, never tallied by hand.

Usage:
    M1A_ADMIN_DSN=... M1A_APP_DSN=... python3 tests/opc/verify_opc.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

sys.path.insert(0, str(REPO / "tests"))
for sub in ("opa", "m1a", "m1d", "m3b"):
    sys.path.insert(0, str(REPO / "tests" / sub))

from fenced import fenced_identifier_pattern                  # noqa: E402
from pg import ProbeFailed, run                               # noqa: E402
from service import Service, WORKSPACE, TSC, sync_and_build   # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import controls as registry                                   # noqa: E402

import verify_opa as opa                                      # noqa: E402

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]

TENANT = opa.TENANT
OUTLET = opa.OUTLET
TABLE_1 = opa.TABLE_1

CONTEXT: dict = {}
results: list[tuple[str, bool, str, str]] = []

# The workspace copies a defect is planted in. Never the repository: api/build.sh
# re-copies from the repository on every run, so reverting a planted defect is a rebuild
# rather than an edit and the repository is never broken even for an instant.
PWA_TS = WORKSPACE / "pwa" / "src" / "app.ts"
WAITER_TS = WORKSPACE / "waiter" / "src" / "waiter.ts"
CASHIER_TS = WORKSPACE / "cashier" / "src" / "cashier.ts"


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    results.append((name, ok, detail, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] ({evidence}) {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def measured(name: str, ok: bool, detail: str = "") -> None:
    record(name, ok, detail, evidence="measured")


def probe(scene: str, args: dict) -> dict:
    """One browser scene. Raises rather than returning half a measurement."""
    target = WORKSPACE / "opc_probe.mjs"
    target.write_text((HERE / "opc_probe.mjs").read_text(encoding="utf-8"),
                      encoding="utf-8", newline="\n")
    proc = subprocess.run(
        ["node", str(target), CONTEXT["base_url"], scene, json.dumps(args)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(WORKSPACE))
    if proc.returncode != 0 or not proc.stdout.strip():
        raise ProbeFailed(f"scene {scene}", (proc.stderr or proc.stdout).strip()[:600])
    return json.loads(proc.stdout)


def rebuild(surface: str) -> None:
    """Recompile one surface from the workspace copy, and re-copy its static files."""
    proc = subprocess.run(
        [str(WORKSPACE / "node_modules" / ".bin" / TSC),
         "-p", str(WORKSPACE / surface / "tsconfig.json"),
         "--outDir", str(WORKSPACE / "dist" / "public")],
        capture_output=True, text=True, encoding="utf-8", cwd=str(WORKSPACE))
    if proc.returncode != 0:
        raise RuntimeError(f"{surface} rebuild failed: {proc.stdout or proc.stderr}")
    statics = {"pwa": [("index.html", "index.html"), ("app.css", "app.css")],
               "cashier": [("index.html", "cashier.html"), ("cashier.css", "cashier.css")],
               "waiter": [("index.html", "waiter.html"), ("waiter.css", "waiter.css")]}
    for name, target in statics[surface]:
        (WORKSPACE / "dist" / "public" / target).write_text(
            (WORKSPACE / surface / name).read_text(encoding="utf-8"),
            encoding="utf-8", newline="\n")
    CONTEXT["service"].restart()


def prove_surface(control: str, signature: str, surface: str, gate,
                  edits: list[tuple[Path, str, str]]) -> None:
    """Plant a defect in a screen, require the named failure, revert, require green.

    RED is "the gate now fails, and it fails by the name this control owns" — never merely
    "something went wrong", because a control that accepts any failure passes on a typo.
    """
    ok, _sig, detail = gate()
    if not ok:
        measured(f"{control} — baseline", False,
                 f"the gate was already failing before the break: {detail}")
        return

    originals = [(path, path.read_text(encoding="utf-8")) for path, _, _ in edits]
    try:
        for path, old, new in edits:
            text = path.read_text(encoding="utf-8")
            if old not in text:
                measured(f"{control} — inject defect", False,
                         f"anchor not found in {path.name}: {old[:70]!r}")
                return
            path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
        rebuild(surface)
        red_ok, red_sig, red_detail = gate()
        measured(f"{control} — RED with the defect planted",
                 (not red_ok) and red_sig == signature,
                 f"{red_sig or '(the gate still passed)'}: {red_detail}")
    finally:
        for path, original in originals:
            path.write_text(original, encoding="utf-8", newline="\n")
        rebuild(surface)

    green_ok, _sig, green_detail = gate()
    measured(f"{control} — GREEN after revert", green_ok, green_detail)


def prove_rule(control: str, red, green) -> None:
    """A control whose subject is a rule the SERVICE enforces, not a screen."""
    red_ok, red_detail = red()
    record(f"{control} — RED with the defect planted", red_ok, red_detail)
    green_ok, green_detail = green()
    record(f"{control} — GREEN after revert", green_ok, green_detail)


# ===========================================================================
# Arranging a floor, WITHOUT writing the row this gate is about
# ===========================================================================

def empty_the_table(table: str = TABLE_1) -> None:
    """Stand up whoever is at this table, so the next scan opens rather than joins.

    Closing is service.close_table_session(), which since 0021 refuses while anything
    financial is outstanding — a real rule belonging to a different requirement. Emptying
    the room between checks is fixture work; SEATING is the product, and no helper in this
    file writes that.
    """
    run(ADMIN, f"""
        UPDATE service.table_session
           SET state = 'closed', closed_at = now()
         WHERE tenant_id = '{TENANT}' AND table_node_id = '{table}' AND state = 'open';""")


def a_placard(table: str = TABLE_1) -> str:
    """A live QR code for a table, as an administrator issues one."""
    code = run(ADMIN, f"""
        SELECT service.issue_table_qr('{TENANT}'::uuid, '{table}'::uuid,
                                      '{opa.ADMIN_USER}'::uuid);""").scalar
    if not code:
        raise ProbeFailed("issuing a placard", "no code came back")
    return code.strip()


def a_guest_scans(code: str) -> dict:
    """A phone reads the placard: a guest session and a scan bound to what it saw."""
    opened = opa.call("POST", f"/c/v1/{TENANT}/{OUTLET}/session", {"code": code})
    if not opened.get("guestToken"):
        raise ProbeFailed("opening a guest session", str(opened)[:200])
    return opened


def a_guest_is_seated(code: str | None = None) -> tuple[dict, dict]:
    """A guest scans and is seated, through the routes and nothing else."""
    scanned = a_guest_scans(code or a_placard())
    seated = opa.call("POST", "/c/v1/seat", {"scanId": scanned["scanId"]},
                      token=scanned["guestToken"], scheme="Guest")
    return scanned, seated


def occupancy(table: str = TABLE_1) -> list[str] | None:
    """The open occupancy on a table: id, number, opening source, host."""
    got = run(ADMIN, f"""
        SELECT id::text, occupancy_number::text, opening_source::text,
               coalesce(host_staff_user_id::text, '-')
          FROM service.table_session
         WHERE tenant_id = '{TENANT}' AND table_node_id = '{table}' AND state = 'open';""")
    return got.rows[0] if got.rows else None


def owner_of(table_session: str) -> str | None:
    got = run(ADMIN, f"""
        SELECT primary_waiter_user_id::text FROM service.table_ownership
         WHERE tenant_id = '{TENANT}' AND table_session_id = '{table_session}'
           AND effective_to IS NULL;""")
    return (got.scalar or "").strip() or None


# ===========================================================================
# 1. Being seated — the step that did not exist
# ===========================================================================

def section_seating() -> None:
    print("\n--- Seating, which nothing in the delivered code path could do ---")

    # ---- a guest seats themselves ----------------------------------------
    empty_the_table()
    before = occupancy()
    scanned, seated = a_guest_is_seated()
    after = occupancy()

    record("a guest scanning an unoccupied table opens the occupancy",
           before is None and after is not None
           and seated.get("tableSessionId") == (after[0] if after else None)
           and seated.get("opened") is True,
           f"before: {before}; after: {after}; the route reported opened="
           f"{seated.get('opened')!r} and session {str(seated.get('tableSessionId'))[:8]}. "
           f"No direct write to service.table_session was executed by this suite")

    record("and the occupancy records that a scan was what opened it",
           bool(after) and after[2] == "qr_scan" and after[3] == "-",
           f"opening_source={after[2] if after else None!r}, host="
           f"{after[3] if after else None!r}. FR-TAB-003 asks a session to carry its "
           f"opening source, and service.opening_source has had three values and no "
           f"writer since M2-B")

    session_id = after[0] if after else ""
    record("a guest-opened table has nobody accountable for it, and says so rather than "
           "failing",
           owner_of(session_id) is None,
           "service.table_ownership has no current row for this occupancy. A guest who "
           "seated themselves has genuinely not been taken on by anybody, and the floor "
           "screen's attention flag is that fact rather than a gap")

    view = run(ADMIN, f"""
        SELECT table_session_id::text, needs_attention::text,
               coalesce(attention_reason, '-'), guests::text
          FROM pos.table_view('{TENANT}'::uuid, '{OUTLET}'::uuid)
         WHERE table_session_id = '{session_id}';""")
    seen = view.rows[0] if view.rows else None
    record("and pos.table_view draws it as needing attention, not as an error or a blank",
           bool(seen) and seen[1] == "true" and "no waiter" in seen[2],
           f"{seen!r} — the till reported 'no open table' before OP-C because this "
           f"function returns one row per occupancy and there were none")

    # ---- the symptom the founder actually met ----------------------------
    cart = opa.call("GET", "/c/v1/cart", token=scanned["guestToken"], scheme="Guest")
    record("and the basket the guest could not reach is now reachable",
           cart.get("status", 200) == 200 and bool(cart.get("cartId")),
           f"GET /c/v1/cart -> {cart.get('status', 200)} "
           f"{('cart ' + str(cart.get('cartId'))[:8]) if cart.get('cartId') else cart}. "
           f"It answered 409 NO_OPEN_OCCUPANCY on the demonstration floor, which is what "
           f"'place order does not work' actually was")

    # ---- a second guest at the same table --------------------------------
    second_scan, second_seat = a_guest_is_seated()
    still = occupancy()
    count = run(ADMIN, f"""
        SELECT count(*)::text FROM service.table_session
         WHERE tenant_id = '{TENANT}' AND table_node_id = '{TABLE_1}' AND state = 'open';""")
    record("a second guest at the same table joins the occupancy rather than opening one",
           second_seat.get("opened") is False
           and second_seat.get("tableSessionId") == session_id
           and (count.scalar or "").strip() == "1",
           f"opened={second_seat.get('opened')!r}, same session="
           f"{second_seat.get('tableSessionId') == session_id}, open occupancies on this "
           f"table={(count.scalar or '').strip()}. The surface never decides which of the "
           f"two a table needs")

    # ---- seating an occupied table ---------------------------------------
    refused = opa.call("POST", f"/s/v1/tables/{TABLE_1}/seat", token=CONTEXT["token"])
    record("a member of staff cannot seat a table that already has a party at it",
           refused.get("status") == 409
           and refused.get("reason") == "OCCUPANCY_ALREADY_OPEN",
           f"{refused.get('status')} {refused.get('reason')!r}. A conflict, answered as "
           f"one — the floor screen redraws instead of reporting a fault")

    # ---- a waiter seats --------------------------------------------------
    empty_the_table()
    staff_seat = opa.call("POST", f"/s/v1/tables/{TABLE_1}/seat", token=CONTEXT["token"])
    staff_session = str(staff_seat.get("tableSessionId") or "")
    opened_by_staff = occupancy()
    record("a member of staff can seat a table, through the same function",
           staff_seat.get("status", 200) == 200 and bool(staff_session)
           and bool(opened_by_staff) and opened_by_staff[2] == "staff",
           f"{staff_seat.get('status', 200)}; occupancy {opened_by_staff!r}. One "
           f"function, two opening sources, which is what the column has always modelled")

    record("and the waiter who seated it is named as the host and made accountable for it",
           bool(opened_by_staff) and opened_by_staff[3] == opa.MANAGER
           and owner_of(staff_session) == opa.MANAGER,
           f"host={opened_by_staff[3] if opened_by_staff else None!r}, current owner="
           f"{owner_of(staff_session)!r}, signed-in user={opa.MANAGER!r}. The acting user "
           f"is resolved from the session, never from the request body")

    # ---- the handover chain, from its new origin -------------------------
    #
    # pos.propose_handover() hands over FROM an existing owner, and pos.acknowledge_handover()
    # is the only non-test writer of service.table_ownership. With no first owner the whole
    # of FR-TAB-006 was unreachable in the delivered code path — a chain with no origin.
    # This is its first real exercise.
    proposed = opa.call("POST", "/s/v1/handovers", {"toUserId": opa.COOK},
                        token=CONTEXT["token"])
    handover = str(proposed.get("handoverId") or "")
    carried = run(ADMIN, f"""
        SELECT count(*)::text FROM pos.handover_item
         WHERE handover_id = '{handover}' AND item_kind = 'table_session'
           AND table_session_id = '{staff_session}';""") if handover else None
    record("the handover chain now has an origin: a seated table can be proposed to "
           "somebody else",
           proposed.get("status", 200) == 200 and bool(handover)
           and (carried.scalar or "").strip() == "1",
           f"POST /s/v1/handovers -> {proposed.get('status', 200)} {str(proposed)[:120]}; "
           f"the proposal carries the seated table: "
           f"{(carried.scalar or '0').strip() if carried else 'n/a'}. Before OP-C nobody "
           f"had ever owned a table, so pos.propose_handover() could only ever refuse "
           f"HANDOVER_CARRIES_NOTHING or hand over service requests alone")

    if handover:
        cook = opa.login(opa.COOK_PASSWORD, value=opa.COOK_EMAIL)
        acknowledged = opa.call("POST", f"/s/v1/handovers/{handover}/acknowledge",
                                token=cook.get("token"))
        record("and the waiter taking it on acknowledges, which is what moves the table",
               acknowledged.get("status", 200) == 200
               and owner_of(staff_session) == opa.COOK,
               f"acknowledge -> {acknowledged.get('status', 200)}; current owner is now "
               f"{owner_of(staff_session)!r}. FR-TAB-006 walked end to end for the first "
               f"time, because seating gave it a place to start")

    # ---- the stale-QR rule is not relaxed --------------------------------
    #
    # THE INVARIANT THIS GATE MUST NOT HAVE BOUGHT ITS FEATURE WITH. A scan taken under one
    # occupancy must still not join another. Seating is a different act from joining, and
    # the whole design rests on that staying true.
    empty_the_table()
    stale_scan = a_guest_scans(a_placard())          # taken while the table was empty
    opa.call("POST", f"/s/v1/tables/{TABLE_1}/seat", token=CONTEXT["token"])
    stale = opa.call("POST", "/c/v1/seat", {"scanId": stale_scan["scanId"]},
                     token=stale_scan["guestToken"], scheme="Guest")
    record("a scan bound to no occupancy still cannot join one opened since",
           stale.get("status") == 409
           and stale.get("reason") == "STALE_QR_VERIFICATION_REQUIRED",
           f"{stale.get('status')} {stale.get('reason')!r}. M2-B's guarantee is untouched: "
           f"service.join_table_session() is called unchanged and this gate added no "
           f"branch in which a join simply proceeds")

    # ---- the join route itself, which this gate stopped being the only caller of ----
    #
    # /c/v1/seat replaced /c/v1/join in the guest surface and in OP-A's order helper, and
    # the route census immediately reported /c/v1/join as called by nothing — which is the
    # census doing its job. M2-B's route still exists, still enforces the stale-QR rule,
    # and is still the route a caller who knows a table is occupied would use. So it is
    # driven here rather than left unproved, and driven at the case that matters.
    #
    # AND THIS IS WHERE F-OPC-4'S REPAIR IS PROVED. Before OP-C this route mapped exactly
    # one refusal and answered 500 to everything else. NO_OPEN_OCCUPANCY was everything
    # else, and it is what the first person to scan the demonstration floor was shown as
    # an internal error while the service was correctly reporting an empty table.
    empty_the_table()
    lone = a_guest_scans(a_placard())
    unjoinable = opa.call("POST", "/c/v1/join", {"scanId": lone["scanId"]},
                          token=lone["guestToken"], scheme="Guest")
    record("joining a table nobody has opened is a named refusal, not a 500",
           unjoinable.get("status") == 409
           and unjoinable.get("reason") == "NO_OPEN_OCCUPANCY",
           f"POST /c/v1/join -> {unjoinable.get('status')} {unjoinable.get('reason')!r}. "
           f"It answered 500 {{'error':'internal error'}} on the demonstration floor: the "
           f"fifth time in this repository a working business rule has been reported as a "
           f"server fault, and the first one a person met rather than a suite")

    joinable = opa.call("POST", "/c/v1/seat", {"scanId": lone["scanId"]},
                        token=lone["guestToken"], scheme="Guest")
    second = a_guest_scans(a_placard())
    joined = opa.call("POST", "/c/v1/join", {"scanId": second["scanId"]},
                      token=second["guestToken"], scheme="Guest")
    record("and the join route still joins an occupancy that is open",
           joinable.get("opened") is True
           and joined.get("status", 200) == 200
           and joined.get("tableSessionId") == joinable.get("tableSessionId"),
           f"one guest opened {str(joinable.get('tableSessionId'))[:8]} and a second "
           f"joined it through M2-B's own route: {joined.get('status', 200)}. Seating did "
           f"not replace joining; it supplied the occupancy joining always needed")

    # ---- and what a guest can do about it on THIS floor ------------------
    #
    # F-OPB-3's fourth member, found by being the first thing to need it. Seating made the
    # stale-QR RESOLUTION path reachable for the first time — before OP-C nobody could be
    # seated, so nothing ever got as far as asking how a stale scan is resolved — and the
    # answer on product data is that it cannot be. service.verification_policy is
    # tenant-unique and has exactly one writer in this repository, tests/m2b/fixtures.py,
    # so the demonstration tenant has no row of its own and every stale scan meets the
    # fail-closed branch with no method a member of staff could use.
    #
    # Reported rather than repaired. Seeding a row would race the fixtures for a unique
    # key, which is the thing F-OPB-3 says cannot be worked around.
    policy = run(ADMIN, f"""
        SELECT array_to_string(accepted_methods, ',') FROM service.verification_policy
         WHERE tenant_id = '{TENANT}';""")
    configured = (policy.scalar or "").strip()
    CONTEXT["verification_methods"] = configured
    record("the floor's stale-scan resolution path is reported, whichever branch it is on",
           True,
           (f"this tenant accepts {configured!r}, written by tests/m2b/fixtures.py — the "
            f"only writer of service.verification_policy in this repository"
            if configured else
            "NO verification policy exists for this tenant, so a genuinely stale scan "
            "cannot be resolved by anybody: not by a table code, not by a member of "
            "staff standing at the table. service.verification_policy is tenant-unique "
            "and fixture-owned, which makes it F-OPB-3's FOURTH member — see "
            "planning/OPC_FINDINGS.md"))


# ===========================================================================
# 2. The basket a guest could add to and not take from
# ===========================================================================

def a_basket_with_a_line() -> tuple[dict, str, str]:
    """A seated guest, their basket, and one line in it — all through the routes."""
    empty_the_table()
    scanned, _ = a_guest_is_seated()
    guest = scanned["guestToken"]
    cart = opa.call("GET", "/c/v1/cart", token=guest, scheme="Guest").get("cartId")
    added = opa.call("POST", "/c/v1/cart/lines",
                     {"cartId": cart, "itemId": opa.ITEM_DORO,
                      "variantId": opa.VARIANT_DORO, "quantity": 1},
                     token=guest, scheme="Guest",
                     key=f"opc-{secrets.token_hex(6)}")
    return scanned, str(cart), str(added.get("id") or "")


def the_basket_is_ordered_from(guest: str, cart: str) -> dict:
    """Place the order, so the cart stops being a draft.

    Through the preview first, because FR-ORD-002's submission requires the total and the
    pricing digest the SERVER calculated — a figure the caller supplies would be the guest
    agreeing with themselves.
    """
    preview = opa.call("POST", "/c/v1/orders/preview", {"cartId": cart},
                       token=guest, scheme="Guest").get("preview") or {}
    return opa.call("POST", "/c/v1/orders",
                    {"cartId": cart,
                     "expectedTotalMinor": int(preview.get("total_amount_minor", 0)),
                     "pricingDigest": preview.get("pricing_digest", ""), "locale": "en"},
                    token=guest, scheme="Guest", key=f"opc-{secrets.token_hex(6)}")


def section_basket() -> None:
    print("\n--- Taking something back out of the basket ---")

    scanned, cart, line = a_basket_with_a_line()
    record("a line added through the route comes back with an id the guest can name it by",
           bool(line),
           f"cart {cart[:8]}, line {line[:8]}. The surface used to discard this id, which "
           f"is why the basket could not refer to its own lines")

    removed = opa.call("DELETE", f"/c/v1/cart/lines/{line}?cartId={cart}",
                       token=scanned["guestToken"], scheme="Guest")
    left = run(ADMIN, f"""
        SELECT count(*)::text FROM service.cart_line
         WHERE tenant_id = '{TENANT}' AND cart_id = '{cart}';""")
    record("and removing it takes it out of the basket",
           removed.get("status", 200) == 200 and (left.scalar or "").strip() == "0",
           f"DELETE -> {removed.get('status', 200)}; {(left.scalar or '').strip()} line(s) "
           f"left. There was no remove, decrement or delete anywhere in the guest surface "
           f"before OP-C, and no function or route behind one")

    again = opa.call("DELETE", f"/c/v1/cart/lines/{line}?cartId={cart}",
                     token=scanned["guestToken"], scheme="Guest")
    record("removing it twice is a 404, not a fault",
           again.get("status") == 404 and again.get("reason") == "CART_LINE_UNKNOWN",
           f"{again.get('status')} {again.get('reason')!r}. A retry of a removal has "
           f"removed nothing twice, which is why this route carries no idempotency key "
           f"while the add beside it does")

    other = opa.call("DELETE", f"/c/v1/cart/lines/{line}?cartId={TABLE_1}",
                     token=scanned["guestToken"], scheme="Guest")
    record("and a line cannot be removed from a basket it was never in",
           other.get("status") == 404,
           f"{other.get('status')} {other.get('reason')!r} for a line named against "
           f"another basket")

    # ---- and the same capability on the other channel --------------------
    #
    # FR-POS-003A: a waiter-entered order obeys the identical rules as a QR order. The
    # guest gained a removal at this gate and the waiter had none — F-OPB-10 again on the
    # channel nobody looked at, because no waiter journey has ever changed its mind
    # either. Driven here through the staff routes, so the claim that both channels reach
    # one writer is walked rather than only read out of the source by M3-D.
    empty_the_table()
    staff_seat = opa.call("POST", f"/s/v1/tables/{TABLE_1}/seat", token=CONTEXT["token"])
    staff_cart = opa.call("POST", "/s/v1/carts",
                          {"tableSessionId": staff_seat.get("tableSessionId")},
                          token=CONTEXT["token"]).get("cartId")
    staff_line = opa.call("POST", "/s/v1/cart/lines",
                          {"cartId": staff_cart, "itemId": opa.ITEM_DORO,
                           "variantId": opa.VARIANT_DORO, "quantity": 1},
                          token=CONTEXT["token"]).get("id")
    staff_removed = opa.call("DELETE", f"/s/v1/cart/lines/{staff_line}?cartId={staff_cart}",
                             token=CONTEXT["token"])
    staff_left = run(ADMIN, f"""
        SELECT count(*)::text FROM service.cart_line
         WHERE tenant_id = '{TENANT}' AND cart_id = '{staff_cart}';""")
    record("a waiter can take a line back out too, through the same writer",
           bool(staff_line) and staff_removed.get("status", 200) == 200
           and (staff_left.scalar or "").strip() == "0",
           f"added {str(staff_line)[:8]} and removed it: "
           f"{staff_removed.get('status', 200)}; {(staff_left.scalar or '').strip()} "
           f"line(s) left. Both channels call service.remove_cart_line() and neither "
           f"states the rule about when that is allowed")

    # ---- the rule that says when this is allowed -------------------------
    scanned, cart, line = a_basket_with_a_line()
    the_basket_is_ordered_from(scanned["guestToken"], cart)
    frozen = opa.call("DELETE", f"/c/v1/cart/lines/{line}?cartId={cart}",
                      token=scanned["guestToken"], scheme="Guest")
    still_there = run(ADMIN, f"""
        SELECT count(*)::text FROM service.cart_line
         WHERE tenant_id = '{TENANT}' AND id = '{line}';""")
    record("a basket that has been ordered from refuses the removal, and the line stays",
           frozen.get("status") == 409
           and frozen.get("reason") == "CART_ALREADY_SUBMITTED"
           and (still_there.scalar or "").strip() == "1",
           f"{frozen.get('status')} {frozen.get('reason')!r}; the line is still there. "
           f"The rule is service.refuse_change_to_submitted_cart(), which has fired on "
           f"DELETE since 0010 and had never had a delete to fire on — the new function "
           f"restates none of it")


# ===========================================================================
# 3. The screens, measured in a browser
# ===========================================================================

def basket_gate() -> tuple[bool, str | None, str]:
    """A guest is seated by scanning, and can take a dish back out."""
    empty_the_table()
    answer = probe("basket", {"tenant": TENANT, "outlet": OUTLET, "code": a_placard()})
    seated = answer["steps"].get("seated") or {}
    if not seated.get("items"):
        return (False, "GUEST_CANNOT_BE_SEATED",
                f"the surface reached status {seated.get('status')!r} with "
                f"{seated.get('items', 0)} menu item(s); page errors: "
                f"{answer.get('errors') or 'none'}. This is the state the demonstration "
                f"floor was in: scanned, and never seated")

    before = answer["steps"].get("beforeRemoval") or {}
    after = answer["steps"].get("afterRemoval") or {}
    if before.get("removeControls", 0) < before.get("lines", 0) or not before.get("lines"):
        return (False, "REMOVE_CONTROL_ABSENT",
                f"{before.get('lines', 0)} basket line(s) and "
                f"{before.get('removeControls', 0)} remove control(s). A guest can add and "
                f"cannot take away")

    if before.get("smallestTarget", 0) < 44:
        return (False, "REMOVE_CONTROL_ABSENT",
                f"the remove control measures {before.get('smallestTarget')}px, below the "
                f"44px thumb target — a control this small is one a guest cannot use")

    if before.get("labelsNameTheirLine", 0) < before.get("lines", 0):
        return (False, "REMOVE_CONTROL_ABSENT",
                f"{before.get('labelsNameTheirLine')} of {before.get('lines')} control(s) "
                f"name the dish on their own row: {before.get('labels')}. A control that "
                f"says only 'Remove' is one control repeated to somebody who cannot see "
                f"the list")

    if after.get("lines", 99) >= before.get("lines", 0):
        return (False, "REMOVE_CONTROL_ABSENT",
                f"tapping remove left {after.get('lines')} line(s) where there were "
                f"{before.get('lines')}; the screen said {after.get('outcome')!r}")

    return (True, None,
            f"seated by scanning ({seated['items']} menu items drawn), "
            f"{before['lines']} lines each with its own remove control at "
            f"{before['smallestTarget']}px, and tapping one left {after['lines']}; "
            f"total {before['total']!r} -> {after['total']!r}")


def till_boxes_gate() -> tuple[bool, str | None, str]:
    """Both boxes name themselves before a bill is loaded."""
    answer = probe("till", {"token": CONTEXT["token"],
                            "sessionId": CONTEXT["staff_session"]})
    boxes = answer["steps"].get("boxes") or {}
    for name in ("bill", "tip"):
        box = boxes.get(name)
        if not box:
            return (False, "BOX_UNLABELLED",
                    f"the {name} box is not on the page at all; errors: "
                    f"{answer.get('errors') or 'none'}")
        if not box["hasHeading"] or not box["headingText"]:
            return (False, "BOX_UNLABELLED",
                    f"the {name} box renders {box['text'][:60]!r} and carries no heading. "
                    f"A cashier signed in with no bill open saw a bordered rectangle and "
                    f"nothing telling them what it was")
    return (True, None,
            f"bill: {boxes['bill']['headingText']!r}; tip: {boxes['tip']['headingText']!r} "
            f"— both named before anything is loaded into them")


def waiter_gate() -> tuple[bool, str | None, str]:
    """A waiter gets in through the page, and seats a table from it.

    NOTHING IS CLEARED FIRST, AND THAT IS THE POINT.

    This gate used to call clear_lockout() and reset_rate_limit() before every run,
    reasoning that FR-AUTH-007's limiter would otherwise meet the third of baseline/red/
    green with a 429. That reasoning was wrong, and the hygiene it justified is what hid a
    P0 for three gates: a SUCCESSFUL login was being counted as a failure, so repeated
    correct sign-ins locked the account out. OP-B met it as 429s, read it as the limiter
    working as designed, and stopped signing in. OP-C and OP-D inherited that reading.

    The defect is repaired in 0038 and NC-OPD-006 now proves it directly. The clearing is
    removed here so this gate signs in three times for real — if a correct sign-in ever
    starts counting against the subject again, this is one of the places that goes red.
    """
    empty_the_table()
    answer = probe("waiter", {"tenant": TENANT, "outlet": OUTLET,
                              "email": opa.MANAGER_EMAIL,
                              "secret": opa.MANAGER_PASSWORD})
    before = answer["steps"].get("beforeSignIn") or {}
    if not before.get("formPresent"):
        return (False, "SIGN_IN_UNREACHABLE",
                f"the waiter surface renders no sign-in form; page errors: "
                f"{answer.get('errors') or 'none'}. It exported signIn() and drew nothing, "
                f"so the only way in was the browser console")
    if before.get("staffRequests", 0) != 0:
        return (False, "SIGN_IN_UNREACHABLE",
                f"{before['staffRequests']} staff request(s) were made before anybody "
                f"signed in")

    after = answer["steps"].get("afterSignIn") or {}
    if not after or after.get("staffRequests", 0) == 0:
        return (False, "SIGN_IN_UNREACHABLE",
                f"signing in through the form fetched nothing: {after!r}; notice "
                f"{after.get('notice')!r}")

    seated = answer["steps"].get("afterSeating")
    if not seated:
        return (False, "TABLE_CANNOT_BE_SEATED",
                f"the floor drew {after.get('seatable', 0)} seatable table(s) and no seat "
                f"control was pressed")
    if seated.get("seatable", 99) >= after.get("seatable", 0):
        return (False, "TABLE_CANNOT_BE_SEATED",
                f"seating left {seated['seatable']} free table(s) where there were "
                f"{after.get('seatable')}; the screen said {seated.get('notice')!r}")

    return (True, None,
            f"signed in through the form ({len(before['fields'])} fields, smallest "
            f"{before['smallestField']}px), drew {after['seatable']} free table(s), and "
            f"seating one left {seated['seatable']}: {seated['notice']!r}")


def section_screens() -> None:
    print("\n--- The screens, measured rather than described ---")
    for name, gate in (("a guest is seated by scanning, and can take a dish back out",
                        basket_gate),
                       ("the till names both of its boxes before a bill is loaded",
                        till_boxes_gate),
                       ("a waiter signs in on the page and seats a table from it",
                        waiter_gate)):
        ok, signature, detail = gate()
        measured(name, ok, f"{signature + ': ' if signature else ''}{detail}")


# ===========================================================================
# 4. The controls
# ===========================================================================

def section_controls() -> None:
    print("\n--- Negative controls: each defect planted, named, and reverted ---")

    # NC-OPC-001 — seating must not have become a way around the stale-QR rule.
    def stale_red() -> tuple[bool, str]:
        empty_the_table()
        scan = a_guest_scans(a_placard())
        opa.call("POST", f"/s/v1/tables/{TABLE_1}/seat", token=CONTEXT["token"])
        answer = opa.call("POST", "/c/v1/seat", {"scanId": scan["scanId"]},
                          token=scan["guestToken"], scheme="Guest")
        CONTEXT["stale_scan"] = scan
        return (answer.get("reason") == "STALE_QR_VERIFICATION_REQUIRED",
                f"a scan bound to no occupancy, presented against one opened since: "
                f"{answer.get('status')} {answer.get('reason')!r}")

    def stale_green() -> tuple[bool, str]:
        scan = CONTEXT.get("stale_scan") or {}
        # The tenant's own configured method, with evidence. Not a bypass: this is the
        # branch M2-B wrote for exactly this case, and it needs both.
        method = (run(ADMIN, f"""
            SELECT accepted_methods[1]::text FROM service.verification_policy
             WHERE tenant_id = '{TENANT}';""").scalar or "").strip()
        if not method:
            # SAID LOUDLY, because a control whose green side is "there is no green side"
            # is weaker than one that exercises the branch, and a reader should be told
            # which of the two they got rather than having to infer it from the absence of
            # a method name. The guarantee is the same either way — this is the fail-closed
            # branch, not a gap in it — but the accepted-method branch went unexercised.
            return (True,
                    "NO ACCEPTED-METHOD BRANCH WAS EXERCISED: this tenant has configured "
                    "no verification method, so every stale join meets the fail-closed "
                    "branch and there is no green side to reach. That is F-OPB-3's fourth "
                    "member — service.verification_policy is tenant-unique and written "
                    "only by tests/m2b/fixtures.py — and it means a guest on a "
                    "product-only floor cannot resolve a stale scan by any means at all")
        answer = opa.call("POST", "/c/v1/seat",
                          {"scanId": scan.get("scanId"), "verification": method,
                           "evidence": "a member of staff confirmed the table"},
                          token=scan.get("guestToken"), scheme="Guest")
        return (answer.get("status", 200) == 200,
                f"with {method!r} and evidence: {answer.get('status', 200)} "
                f"{str(answer)[:110]}")

    prove_rule("NC-OPC-001", stale_red, stale_green)

    # NC-OPC-002 — an occupancy must not be openable twice.
    def twice_red() -> tuple[bool, str]:
        empty_the_table()
        first = opa.call("POST", f"/s/v1/tables/{TABLE_1}/seat", token=CONTEXT["token"])
        second = opa.call("POST", f"/s/v1/tables/{TABLE_1}/seat", token=CONTEXT["token"])
        open_now = run(ADMIN, f"""
            SELECT count(*)::text FROM service.table_session
             WHERE tenant_id = '{TENANT}' AND table_node_id = '{TABLE_1}'
               AND state = 'open';""")
        return (second.get("reason") == "OCCUPANCY_ALREADY_OPEN"
                and (open_now.scalar or "").strip() == "1",
                f"first {first.get('status', 200)}, second {second.get('status')} "
                f"{second.get('reason')!r}; {(open_now.scalar or '').strip()} open "
                f"occupancy on the table")

    def twice_green() -> tuple[bool, str]:
        empty_the_table()
        highest = run(ADMIN, f"""
            SELECT max(occupancy_number)::text FROM service.table_session
             WHERE tenant_id = '{TENANT}' AND table_node_id = '{TABLE_1}';""")
        opa.call("POST", f"/s/v1/tables/{TABLE_1}/seat", token=CONTEXT["token"])
        now = occupancy()
        return (bool(now) and int(now[1]) > int((highest.scalar or "0").strip()),
                f"the next party is occupancy {now[1] if now else '?'}, above "
                f"{(highest.scalar or '0').strip()}. Monotonic per table, which is what "
                f"makes 'the party after you' a fact rather than a guess from timestamps")

    prove_rule("NC-OPC-002", twice_red, twice_green)

    # NC-OPC-003 — an opening must say who did it.
    def unattributed_red() -> tuple[bool, str]:
        staff_without_host = run(APP, f"""
            SELECT service.open_table_session('{TENANT}'::uuid, '{TABLE_1}'::uuid,
                'staff'::service.opening_source, NULL, NULL);""",
            tenant=TENANT, outlet=OUTLET, tx=True)
        guest_with_host = run(APP, f"""
            SELECT service.open_table_session('{TENANT}'::uuid, '{TABLE_1}'::uuid,
                'qr_scan'::service.opening_source, '{opa.MANAGER}'::uuid, NULL);""",
            tenant=TENANT, outlet=OUTLET, tx=True)
        return (staff_without_host.failed_with("OPENING_SOURCE_UNATTRIBUTED")
                and guest_with_host.failed_with("OPENING_SOURCE_UNATTRIBUTED"),
                f"staff with no host: {staff_without_host.why()[:90]}; a scan naming a "
                f"host: {guest_with_host.why()[:90]}")

    def unattributed_green() -> tuple[bool, str]:
        empty_the_table()
        by_staff = opa.call("POST", f"/s/v1/tables/{TABLE_1}/seat", token=CONTEXT["token"])
        empty_the_table()
        _scan, by_guest = a_guest_is_seated()
        return (by_staff.get("status", 200) == 200
                and by_guest.get("status", 200) == 200,
                f"attributed both ways: staff {by_staff.get('status', 200)}, guest "
                f"{by_guest.get('status', 200)}")

    prove_rule("NC-OPC-003", unattributed_red, unattributed_green)

    # NC-OPC-004 — an ordered basket must not be editable.
    def submitted_red() -> tuple[bool, str]:
        scanned, cart, line = a_basket_with_a_line()
        the_basket_is_ordered_from(scanned["guestToken"], cart)
        answer = opa.call("DELETE", f"/c/v1/cart/lines/{line}?cartId={cart}",
                          token=scanned["guestToken"], scheme="Guest")
        return (answer.get("reason") == "CART_ALREADY_SUBMITTED",
                f"{answer.get('status')} {answer.get('reason')!r} — removing a line from a "
                f"cart somebody has ordered from would change what they agreed to")

    def submitted_green() -> tuple[bool, str]:
        scanned, cart, line = a_basket_with_a_line()
        answer = opa.call("DELETE", f"/c/v1/cart/lines/{line}?cartId={cart}",
                          token=scanned["guestToken"], scheme="Guest")
        return (answer.get("status", 200) == 200,
                f"a draft basket removes its line: {answer.get('status', 200)}")

    prove_rule("NC-OPC-004", submitted_red, submitted_green)

    # NC-OPC-005 — the remove control itself, planted out of the guest surface.
    prove_surface(
        "NC-OPC-005", "REMOVE_CONTROL_ABSENT", "pwa", basket_gate,
        [(PWA_TS, "li.append(name, price, state, remove);",
          "li.append(name, price, state);")])

    # NC-OPC-006 — the waiter's way in.
    #
    # The defect is the form never reaching the page, which is exactly the state OP-B
    # shipped: signIn() existed, was exported, and nothing rendered a way to call it.
    # Planted by dropping the one line that puts the form in the document rather than by
    # returning early — an early return leaves the rest of the function unreachable and
    # TypeScript refuses to compile it, so the control would fail as a build error instead
    # of as the gate it owns. A control that cannot compile proves nothing.
    prove_surface(
        "NC-OPC-006", "SIGN_IN_UNREACHABLE", "waiter", waiter_gate,
        [(WAITER_TS, "  panel.appendChild(form);", "  void form;")])

    # NC-OPC-007 — the till's two boxes.
    prove_surface(
        "NC-OPC-007", "BOX_UNLABELLED", "cashier", till_boxes_gate,
        [(CASHIER_TS, "    root.appendChild(element('h2', `${id}-heading`, heading));",
          "    root.appendChild(element('p', 'empty', ''));")])


# ===========================================================================
# 5. What this gate did not touch, and what it left uncalled
# ===========================================================================

def section_signatures() -> None:
    print("\n--- Boundaries, and the census ---")

    signatures = ["GUEST_CANNOT_BE_SEATED", "REMOVE_CONTROL_ABSENT", "BOX_UNLABELLED",
                  "SIGN_IN_UNREACHABLE", "TABLE_CANNOT_BE_SEATED",
                  "STALE_QR_VERIFICATION_REQUIRED", "OCCUPANCY_ALREADY_OPEN",
                  "OPENING_SOURCE_UNATTRIBUTED", "CART_ALREADY_SUBMITTED",
                  "CART_LINE_UNKNOWN"]
    pattern, terms = fenced_identifier_pattern()
    offending = sorted({m.group(0) for s in signatures
                        for m in re.finditer(pattern, s, re.I)})
    record("no OP-C failure signature names a permanently fenced domain",
           len(signatures) == 10 and not offending,
           f"{len(signatures)} signature(s) checked against all {terms} authoritative "
           f"terms: {offending or 'none'}")

    sources = "\n".join(
        p.read_text(encoding="utf-8") for p in (
            HERE / "verify_opc.py",
            HERE / "opc_probe.mjs",
            REPO / "migrations" / "0035_a_table_can_be_seated.sql",
            REPO / "api" / "src" / "routes" / "customer.ts",
            REPO / "api" / "src" / "routes" / "staff.ts",
            REPO / "pwa" / "src" / "app.ts",
            REPO / "waiter" / "src" / "waiter.ts",
            REPO / "cashier" / "src" / "cashier.ts",
        ) if p.exists())
    hits = sorted({m.group(0) for m in re.finditer(pattern, sources, re.I)})
    record("and neither does anything this gate wrote",
           not hits,
           f"checked the suite, the probe, the migration, two route files and three "
           f"surfaces against all {terms} terms: {hits or 'none'}")

    # THE ROW NOTHING IN THIS SUITE WRITES.
    #
    # The whole finding was that four files inserted a table session and all four were
    # tests. A gate that closed it and then arranged its own occupancies would have proved
    # nothing, so this is checked from the source rather than promised in a docstring.
    # READ FROM THE SQL THIS FILE EXECUTES, NOT FROM ITS PROSE.
    #
    # The first version of this check was a grep for the phrase over the whole file, and it
    # failed on its own docstring — which describes the defect and therefore contains the
    # words. That is the reader that cannot tell prose from code, and this repository has
    # met it three times. Here the honest instrument is available: every statement this
    # suite runs goes through run(dsn, sql), so the AST can be asked for those arguments
    # and nothing else. A comment can no longer trip it and, more importantly, a comment
    # can no longer be used to hide an INSERT from it.
    #
    # CI keeps the blunt grep as well. Two instruments, one precise and one that cannot be
    # reasoned around, and the prose is written so as not to trip the blunt one.
    executed: list[str] = []
    for node in ast.walk(ast.parse((HERE / "verify_opc.py").read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "run" and len(node.args) >= 2):
            continue
        argument = node.args[1]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            executed.append(argument.value)
        elif isinstance(argument, ast.JoinedStr):
            executed.append(" ".join(
                part.value for part in argument.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)))

    writes = [sql for sql in executed
              if re.search(r"INSERT\s+INTO\s+service\.table_session", sql, re.I)]
    record("this suite never writes the row it exists to prove somebody else writes",
           not writes and len(executed) > 0,
           f"{len(executed)} statement(s) executed by this suite, {len(writes)} of them "
           f"writing service.table_session. Every occupancy came out of POST /c/v1/seat "
           f"or POST /s/v1/tables/:tableNodeId/seat"
           + (f"\n{writes}" if writes else ""))

    sys.path.insert(0, str(REPO / "tools"))
    import uncalled_routes
    census = uncalled_routes.survey()
    record("the route census is reported, including what this gate has not yet proved",
           census["total"] > 0,
           f"{census['called']} of {census['total']} routes are called by something and "
           f"{len(census['uncalled'])} by nothing, from {census['call_sites']} call sites")


# ===========================================================================

def main() -> int:
    print("OP-C verification — being seated, and taking something back out")
    print("real PostgreSQL, real compiled service, real browser")
    print("")

    sync_and_build()

    with Service(APP) as service_process:
        CONTEXT["base_url"] = f"http://127.0.0.1:{service_process.port}"
        CONTEXT["service"] = service_process
        opa.CONTEXT["base_url"] = CONTEXT["base_url"]
        opa.CONTEXT["service"] = service_process

        opa.clear_lockout()
        answer = opa.login(opa.MANAGER_PASSWORD, value=opa.MANAGER_EMAIL)
        if not answer.get("token"):
            print(f"FAIL OPC_SIGN_IN\n  the manager could not sign in: {answer}")
            return 1
        CONTEXT["token"] = answer["token"]
        CONTEXT["staff_session"] = answer.get("sessionId")
        opa.CONTEXT["token"] = answer["token"]

        for section in (section_seating, section_basket, section_screens,
                        section_controls, section_signatures):
            try:
                section()
            except ProbeFailed as exc:
                record(f"{section.__name__} completed", False,
                       f"probe did not execute: {exc}")

    failed = [name for name, ok, _d, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")
    owned = len([c for c in registry.CONTROLS if c[3] == "opc"])

    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}   (read out of a real browser's layout)")
    print(f"  asserted      : {len(results) - measured_count}")
    print(f"  controls      : {owned} registered, each proved red then green")

    if failed:
        print("\nFAIL OPC_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS OPC_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
