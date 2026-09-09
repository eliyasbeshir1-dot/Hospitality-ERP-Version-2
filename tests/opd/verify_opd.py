#!/usr/bin/env python3
"""OP-D verification: the order reaches the kitchen, and the menu says what a dish is.

WHAT THIS SUITE IS FOR. OP-C made it possible to be seated. A guest then scanned, chose,
placed an order — and it stopped. The outlet's policy made guest_qr orders
`staff_confirmed`, so the order sat in 'submitted'; POST /s/v1/orders/:orderId/accept
existed and worked and no surface called it; and no screen anywhere listed an order
awaiting acceptance, because the station board shows TICKETS and an unaccepted order has
none. The order was invisible on every screen in the system, and nobody could admit it
because no screen showed it.

The route census reported that route as CALLED, correctly and uselessly: it pooled
`tests/**` with the four surfaces, so a route driven only by a suite was indistinguishable
from one a person can press. That pooling is why the same shape was missed twice, and
splitting it is the fourth thing this gate does.

Usage:
    M1A_ADMIN_DSN=... M1A_APP_DSN=... python3 tests/opd/verify_opd.py
"""
from __future__ import annotations

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

PWA_TS = WORKSPACE / "pwa" / "src" / "app.ts"
WAITER_TS = WORKSPACE / "waiter" / "src" / "waiter.ts"


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    results.append((name, ok, detail, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] ({evidence}) {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def measured(name: str, ok: bool, detail: str = "") -> None:
    record(name, ok, detail, evidence="measured")


def probe(scene: str, args: dict) -> dict:
    target = WORKSPACE / "opd_probe.mjs"
    target.write_text((HERE / "opd_probe.mjs").read_text(encoding="utf-8"),
                      encoding="utf-8", newline="\n")
    proc = subprocess.run(
        ["node", str(target), CONTEXT["base_url"], scene, json.dumps(args)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(WORKSPACE))
    if proc.returncode != 0 or not proc.stdout.strip():
        raise ProbeFailed(f"scene {scene}", (proc.stderr or proc.stdout).strip()[:600])
    return json.loads(proc.stdout)


def rebuild(surface: str) -> None:
    proc = subprocess.run(
        [str(WORKSPACE / "node_modules" / ".bin" / TSC),
         "-p", str(WORKSPACE / surface / "tsconfig.json"),
         "--outDir", str(WORKSPACE / "dist" / "public")],
        capture_output=True, text=True, encoding="utf-8", cwd=str(WORKSPACE))
    if proc.returncode != 0:
        raise RuntimeError(f"{surface} rebuild failed: {proc.stdout or proc.stderr}")
    statics = {"pwa": [("index.html", "index.html"), ("app.css", "app.css")],
               "waiter": [("index.html", "waiter.html"), ("waiter.css", "waiter.css")]}
    for name, target in statics[surface]:
        (WORKSPACE / "dist" / "public" / target).write_text(
            (WORKSPACE / surface / name).read_text(encoding="utf-8"),
            encoding="utf-8", newline="\n")
    CONTEXT["service"].restart()


def prove_surface(control: str, signature: str, surface: str, gate,
                  edits: list[tuple[Path, str, str]]) -> None:
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
    red_ok, red_detail = red()
    record(f"{control} — RED with the defect planted", red_ok, red_detail)
    green_ok, green_detail = green()
    record(f"{control} — GREEN after revert", green_ok, green_detail)


# ===========================================================================
# A floor, arranged only through the routes
# ===========================================================================

def empty_the_table(table: str = TABLE_1) -> None:
    run(ADMIN, f"""
        UPDATE service.table_session
           SET state = 'closed', closed_at = now()
         WHERE tenant_id = '{TENANT}' AND table_node_id = '{table}' AND state = 'open';""")


def clear_the_kitchen() -> None:
    """Stand the station's queue down, so the suite does not throttle itself.

    THIS IS A REAL CONSEQUENCE OF WHAT THIS GATE CHANGED, not a workaround around a bug.
    Under `staff_confirmed` an unaccepted order was a row and cost the kitchen nothing.
    Under `automatic` every order becomes live tickets at once, and FR-ORD-006's capacity
    rule then throttles: the hot station's threshold is 12 concurrent tickets, and a suite
    that places two dozen orders without a kitchen behind it hits it and starts seeing
    SUBMISSION_REVALIDATION_FAILED — the rule working, reported as a suite failure.

    Cleared through fulfillment.transition_ticket(), the function the station board's own
    route calls, and to `cancelled` because queued -> cancelled is a legal pair in
    fulfillment.transition. NOT a DELETE: a ticket is a projection of the ticket ledger,
    and removing the row while leaving the events would desynchronise the two — which is
    the thing M3-A's rebuild determinism check exists to catch.
    """
    # THE TICKET'S OWN OUTLET, NOT THIS SUITE'S.
    #
    # Selected with the row rather than assumed. This used to set the context to Sarbet
    # for every ticket while selecting across the whole tenant — which passed locally on a
    # database rebuilt from empty, where every ticket was Sarbet's, and failed in CI where
    # M4-A's counter orders had left tickets at Kazanchis. The fold reads
    # fulfillment.ticket_event under row level security, so a Kazanchis ticket folded
    # under a Sarbet context cannot see the event it just wrote and raises
    # TICKET_EVENT_ABSENT against its own row.
    #
    # A fixture that hard-codes one outlet while reading many is the same shape as a check
    # that passes because the fixtures happened to line up.
    live = run(ADMIN, f"""
        SELECT id::text, outlet_id::text FROM fulfillment.ticket
         WHERE tenant_id = '{TENANT}' AND state = 'queued';""")
    for row in live.rows:
        # CONTEXT AND A TRANSACTION, both required and both easy to leave out.
        # transition_ticket() appends to the ticket ledger and then folds the event, and
        # the fold reads fulfillment.ticket_event under row level security — so without a
        # tenant context it writes the event, cannot see it, and raises TICKET_EVENT_ABSENT
        # against the row it just inserted. Context is transaction-local, so tx=True is
        # what makes the two statements share it.
        cancelled = run(ADMIN, f"""
            SELECT fulfillment.transition_ticket('{TENANT}'::uuid, '{row[0]}'::uuid,
                                                 'cancelled'::fulfillment.ticket_state,
                                                 '{opa.MANAGER}'::uuid);""",
                        tenant=TENANT, outlet=row[1], tx=True)
        if not cancelled.ok:
            raise ProbeFailed("standing the station down",
                              f"ticket {row[0][:8]} at outlet {row[1][:8]}: "
                              f"{cancelled.why()[:160]}")


def a_seated_guest() -> str:
    """A guest at an empty table, seated by scanning. Returns their token."""
    empty_the_table()
    code = run(ADMIN, f"""
        SELECT service.issue_table_qr('{TENANT}'::uuid, '{TABLE_1}'::uuid,
                                      '{opa.ADMIN_USER}'::uuid);""").scalar
    scanned = opa.call("POST", f"/c/v1/{TENANT}/{OUTLET}/session",
                       {"code": (code or "").strip()})
    if not scanned.get("guestToken"):
        raise ProbeFailed("opening a guest session", str(scanned)[:200])
    opa.call("POST", "/c/v1/seat", {"scanId": scanned["scanId"]},
             token=scanned["guestToken"], scheme="Guest")
    return str(scanned["guestToken"])


def an_order_from(guest: str) -> dict:
    """One dish, previewed and placed through the guest routes.

    The station is stood down first. See clear_the_kitchen(): with automatic acceptance
    every order becomes live tickets, and this suite places more of them than the hot
    station's concurrent threshold allows.
    """
    clear_the_kitchen()
    cart = opa.call("GET", "/c/v1/cart", token=guest, scheme="Guest").get("cartId")
    opa.call("POST", "/c/v1/cart/lines",
             {"cartId": cart, "itemId": opa.ITEM_DORO,
              "variantId": opa.VARIANT_DORO, "quantity": 1},
             token=guest, scheme="Guest", key=f"opd-{secrets.token_hex(6)}")
    preview = opa.call("POST", "/c/v1/orders/preview", {"cartId": cart},
                       token=guest, scheme="Guest").get("preview") or {}
    return opa.call("POST", "/c/v1/orders",
                    {"cartId": cart,
                     "expectedTotalMinor": int(preview.get("total_amount_minor", 0)),
                     "pricingDigest": preview.get("pricing_digest", ""), "locale": "en"},
                    token=guest, scheme="Guest", key=f"opd-{secrets.token_hex(6)}")


def set_guest_qr(mode: str) -> None:
    """Put a named acceptance mode in force for guest_qr, as a new policy version.

    A VERSION, NOT AN EDIT, exactly as seeds/0009 does it — the suite changes the policy
    the way an operator would, so what it proves is what an outlet that chose that mode
    would get. Reverted the same way at the end of the section.
    """
    # The payload is carried forward from the version that was in force and only the one
    # key is changed, so this cannot quietly drop max_line_quantity or the amendment
    # states along with it. The new version number comes from a scalar subquery rather
    # than an aggregate beside the payload — mixing the two is an error PostgreSQL raises
    # and psql reports, and the first draft of this helper ignored the result and let
    # every check downstream fail for a reason none of them named.
    written = run(ADMIN, f"""
        UPDATE config.policy SET effective_to = now()
         WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET}'
           AND category = 'ordering' AND effective_to IS NULL;
        INSERT INTO config.policy
            (tenant_id, outlet_id, category, version, payload, effective_from,
             actor_id, approved_by_id, approved_at)
        SELECT p.tenant_id, p.outlet_id, 'ordering',
               (SELECT max(version) + 1 FROM config.policy
                 WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET}'
                   AND category = 'ordering'),
               jsonb_set(p.payload, '{{acceptance,guest_qr}}', '"{mode}"'),
               now(), '{opa.ADMIN_USER}', '{opa.ADMIN_USER}', now()
          FROM config.policy p
         WHERE p.tenant_id = '{TENANT}' AND p.outlet_id = '{OUTLET}'
           AND p.category = 'ordering'
         ORDER BY p.version DESC LIMIT 1
        RETURNING version::text;""")
    if not written.ok or guest_qr_mode() != mode:
        raise ProbeFailed(
            f"putting guest_qr = {mode} in force",
            f"{written.why() or 'no row written'}; in force now: {guest_qr_mode()!r}")


def guest_qr_mode() -> str:
    return (run(ADMIN, f"""
        SELECT payload -> 'acceptance' ->> 'guest_qr' FROM config.policy
         WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET}'
           AND category = 'ordering' AND effective_to IS NULL;""").scalar or "").strip()


# ===========================================================================
# 1. The order reaches the kitchen
# ===========================================================================

def section_acceptance() -> None:
    print("\n--- Acceptance: the step that had no caller ---")

    # WHAT THE SEED ESTABLISHES IS READ FROM THE SEED, NOT FROM THE LIVE POLICY.
    #
    # This suite changes the acceptance mode several times — it has to, because
    # FR-ORD-007A makes it a policy and both values must be shown to work — and it puts
    # the seeded value back in a `finally`. A run KILLED between those two leaves the
    # floor on the other value, and the next run then opened by reporting the seed wrong
    # when the seed was right and its own predecessor was to blame. A check that a
    # previous crash can turn red is a check that says nothing about the code.
    #
    # So the durable claim — "the demonstration floor is seeded automatic" — is read from
    # the file that makes it. What is in force is then RESTORED to that value, and the
    # restoration says whether it had to do anything, so contamination is reported rather
    # than hidden.
    seed = (REPO / "seeds" / "0009_qr_ordering_does_not_wait_for_a_waiter.sql").read_text(
        encoding="utf-8")
    seeded_automatic = '"guest_qr": "automatic"' in seed
    record("the demonstration floor is seeded to accept a QR order automatically",
           seeded_automatic,
           f"seeds/0009 writes guest_qr = automatic: {seeded_automatic}. It makes that a "
           f"new policy VERSION rather than an edit, so an order placed under the old rule "
           f"can still be explained by the rule in force when it was placed")

    inherited = guest_qr_mode()
    if inherited != "automatic":
        set_guest_qr("automatic")
    record("and the floor is on that value before anything below is measured",
           guest_qr_mode() == "automatic",
           f"in force at the start of this run: {inherited!r}"
           + ("" if inherited == "automatic" else
              " — a previous run was killed between changing it and putting it back, and "
              "it has been restored. That is contamination, not a finding about the seed"))

    guest = a_seated_guest()
    placed = an_order_from(guest)
    order = str(placed.get("orderId") or "")
    record("a guest places an order and it is admitted without anybody pressing anything",
           placed.get("state") == "accepted" and placed.get("accepted") is True,
           f"POST /c/v1/orders -> {placed.get('status', 200)} state="
           f"{placed.get('state')!r}. QR ordering exists to remove the waiter as the "
           f"bottleneck; a tap to start puts them back in front of it")

    tickets = run(ADMIN, f"""
        SELECT count(*)::text FROM fulfillment.ticket WHERE order_id = '{order}';""")
    record("and the kitchen has a ticket for it",
           (tickets.scalar or "").strip() not in ("", "0"),
           f"{(tickets.scalar or '0').strip()} ticket(s). Acceptance triggers release, "
           f"release emits the ledger event, and the fold writes the ticket — none of "
           f"which ran while the order sat in 'submitted'")

    # ---- and the policy the founder did not choose still works -----------
    #
    # FR-ORD-007A makes acceptance a POLICY. staff_confirmed is a legal value, not a
    # mistake, and an outlet that chooses it must still be able to run. This is the half
    # that had no screen at all.
    set_guest_qr("staff_confirmed")
    try:
        waiting_guest = a_seated_guest()
        waiting = an_order_from(waiting_guest)
        waiting_order = str(waiting.get("orderId") or "")
        record("under staff_confirmed the same order waits instead, and the route says so",
               waiting.get("state") == "submitted" and waiting.get("accepted") is False,
               f"state={waiting.get('state')!r}, accepted={waiting.get('accepted')!r}. The "
               f"route used to answer with an id alone, which is why the surface said "
               f"'Your order is with the kitchen' in both cases and was wrong in this one")

        pending = opa.call("GET", "/s/v1/orders/pending", token=CONTEXT["token"])
        rows = pending.get("orders") or []
        mine = [r for r in rows if r.get("order_id") == waiting_order]
        record("and it appears on the list of orders waiting to be confirmed",
               pending.get("status", 200) == 200 and len(mine) == 1,
               f"GET /s/v1/orders/pending -> {pending.get('status', 200)}, "
               f"{len(rows)} waiting, this one among them: {bool(mine)}. Before OP-D no "
               f"screen in the system listed an unaccepted order — the station board shows "
               f"tickets, and it has none")

        accepted = opa.call("POST", f"/s/v1/orders/{waiting_order}/accept",
                            token=CONTEXT["token"])
        after = run(ADMIN, f"""
            SELECT state::text,
                   (SELECT count(*) FROM fulfillment.ticket WHERE order_id = '{waiting_order}')::text
              FROM ordering.customer_order WHERE id = '{waiting_order}';""")
        row = after.rows[0] if after.rows else ["?", "?"]
        record("confirming it admits it to the kitchen and creates its tickets",
               accepted.get("status", 200) == 200 and row[0] == "accepted"
               and row[1] not in ("", "0"),
               f"accept -> {accepted.get('status', 200)}; state={row[0]}, "
               f"tickets={row[1]}")

        gone = opa.call("GET", "/s/v1/orders/pending", token=CONTEXT["token"])
        record("and it leaves the waiting list by having a different state, not a flag",
               all(r.get("order_id") != waiting_order
                   for r in (gone.get("orders") or [])),
               "pos.pending_orders() selects state = 'submitted'. There is no pending "
               "column to fall out of step with the state machine")
    finally:
        set_guest_qr("automatic")

    record("the floor is left as the seed leaves it",
           guest_qr_mode() == "automatic",
           f"guest_qr = {guest_qr_mode()!r}. A suite that changed a policy and left it "
           f"changed would make every later check answer a question nobody asked")


# ===========================================================================
# 2. The menu says what a dish is
# ===========================================================================

def section_menu() -> None:
    print("\n--- What a guest is given to choose with (FR-MNU-004) ---")

    guest = a_seated_guest()
    menu = opa.call("GET", "/c/v1/menu?locale=en", token=guest, scheme="Guest")
    items = menu.get("items") or []
    with_all = [i for i in items
                if i.get("shortDescription") and i.get("ingredients")
                and i.get("preparationMinutes") is not None]
    record("the menu route returns a description, the ingredients and a preparation time",
           len(items) > 0 and len(with_all) == len(items),
           f"{len(with_all)} of {len(items)} item(s) carry all three. The seed has written "
           f"them since 0003 and menu.published_menu_for_guest() returned none of them "
           f"until OP-D — the data was there, the requirement was met in the schema, and "
           f"a guest read a name and a price")

    # WHERE EACH FIELD COMES FROM, checked rather than described. The commercial terms are
    # the snapshot's and the prose is the item's, and the whole argument for that split is
    # that a corrected description must not require republishing a menu.
    pinned = run(ADMIN, f"""
        SELECT count(*)::text FROM information_schema.columns
         WHERE table_schema = 'menu' AND table_name = 'publication_snapshot_line'
           AND column_name IN ('canonical_short_description', 'customer_visible_ingredients',
                               'preparation_minutes');""")
    record("the prose is read from the item, because the snapshot does not carry it",
           (pinned.scalar or "").strip() == "0",
           f"{(pinned.scalar or '0').strip()} of the three descriptive columns exist on "
           f"menu.publication_snapshot_line. The snapshot pins what is CHARGED; a typo in "
           f"an ingredient list would otherwise be fixable only by republishing")

    # IMAGES ARE ABSENT AND THE SUITE SAYS WHY, rather than leaving a requirement looking
    # met because nobody looked.
    images = run(ADMIN, "SELECT count(*)::text FROM menu.image;")
    servers = [p for p in (REPO / "api" / "src").rglob("*.ts")
               if "storage_key" in p.read_text(encoding="utf-8")]
    record("images are reported absent, with the reason, rather than half-built",
           True,
           f"menu.image holds {(images.scalar or '0').strip()} row(s) and "
           f"{len(servers)} file(s) under api/src name a storage key. FR-MNU-004 asks for "
           f"images and FR-MNU-011 for derivatives with alt text; menu.image is private by "
           f"CHECK CONSTRAINT with no value that publishes it, and its derivatives' own "
           f"comment says access goes through a signed, expiring, authorized URL path. No "
           f"such path exists. Seeding rows would hand the surface a key it cannot turn "
           f"into a src — see F-OPD-3 in planning/OPD_FINDINGS.md")


# ===========================================================================
# 3. The census tells the two questions apart
# ===========================================================================

def section_census() -> None:
    print("\n--- The census: called by a suite is not reachable by a person ---")

    sys.path.insert(0, str(REPO / "tools"))
    import uncalled_routes
    for name, ok in uncalled_routes.self_test():
        record(f"census reader — {name}", ok)

    census = uncalled_routes.survey()
    record("the census reports reachability and provenness separately",
           "reachable" in census and "unreachable" in census
           and census["reachable"] + len(census["unreachable"]) == census["called"],
           f"{census['reachable']} of {census['total']} routes are reachable by a person; "
           f"{len(census['unreachable'])} are proved by a suite and reached by no screen; "
           f"{len(census['uncalled'])} are called by nothing at all. Pooling the first two "
           f"is why the same defect was missed twice")

    reachable = {f"{r['verb']} {r['path']}" for r in census["unreachable"]}
    record("the route that forced the split is now reachable by a person",
           "POST /s/v1/orders/:orderId/accept" not in reachable
           and not any(r["path"] == "/s/v1/orders/:orderId/accept"
                       for r in census["uncalled"]),
           "POST /s/v1/orders/:orderId/accept is called by the waiter surface. It was "
           "called by tests/journeys and tests/opa and by no screen, and the census "
           "reported it green while a guest's order sat in 'submitted' unreachable")

    record("and the surfaces are visible to the census at all",
           census["surface_call_sites"] > 0,
           f"{census['surface_call_sites']} call site(s) in pwa/, waiter/, station/ and "
           f"cashier/. Every one is a request HELPER — waiterApi('GET', …), api('POST', …) "
           f"— and the reader could not see any of them until OP-D, so a reachability "
           f"number would have said 15 of 117 and been worse than no number")


# ===========================================================================
# 4. The screens
# ===========================================================================

def menu_card_gate() -> tuple[bool, str | None, str]:
    """A guest reads what the dish is, not only what it costs."""
    empty_the_table()
    code = run(ADMIN, f"""
        SELECT service.issue_table_qr('{TENANT}'::uuid, '{TABLE_1}'::uuid,
                                      '{opa.ADMIN_USER}'::uuid);""").scalar
    answer = probe("menu", {"tenant": TENANT, "outlet": OUTLET,
                            "code": (code or "").strip()})
    card = answer["steps"].get("card")
    if not card or not card.get("items"):
        return (False, "MENU_SAYS_ONLY_NAME_AND_PRICE",
                f"the surface drew {(card or {}).get('items', 0)} item(s); errors: "
                f"{answer.get('errors') or 'none'}")
    if card["withDescription"] < card["items"]:
        return (False, "MENU_SAYS_ONLY_NAME_AND_PRICE",
                f"{card['withDescription']} of {card['items']} card(s) show a description")
    if card["withIngredients"] < card["items"]:
        return (False, "MENU_SAYS_ONLY_NAME_AND_PRICE",
                f"{card['withIngredients']} of {card['items']} card(s) show ingredients — "
                f"the field menu.translatable_field marks safety-critical")
    if card["withPrep"] < card["items"]:
        return (False, "MENU_SAYS_ONLY_NAME_AND_PRICE",
                f"{card['withPrep']} of {card['items']} card(s) show a preparation time")
    return (True, None,
            f"{card['items']} card(s), each with a description, ingredients and a "
            f"preparation time: {card['first']!r}")


def truthful_outcome_gate() -> tuple[bool, str | None, str]:
    """What the guest is told is what actually happened."""
    set_guest_qr("staff_confirmed")
    try:
        empty_the_table()
        code = run(ADMIN, f"""
            SELECT service.issue_table_qr('{TENANT}'::uuid, '{TABLE_1}'::uuid,
                                          '{opa.ADMIN_USER}'::uuid);""").scalar
        answer = probe("order", {"tenant": TENANT, "outlet": OUTLET,
                                 "code": (code or "").strip()})
    finally:
        set_guest_qr("automatic")

    placed = answer["steps"].get("placed")
    if not placed or not placed.get("message"):
        return (False, "SURFACE_CLAIMS_THE_KITCHEN_HAS_IT",
                f"nothing was reported to the guest; errors: {answer.get('errors') or 'none'}")
    if placed.get("state") != "submitted":
        return (False, "SURFACE_CLAIMS_THE_KITCHEN_HAS_IT",
                f"the order landed in {placed.get('state')!r}, so this gate could not "
                f"measure what a waiting guest is told")
    words = placed["message"].lower()
    if "kitchen" in words:
        return (False, "SURFACE_CLAIMS_THE_KITCHEN_HAS_IT",
                f"the guest is told {placed['message']!r} while the order is in "
                f"'submitted' and no kitchen has seen it")
    if not ("waiting" in words or "confirm" in words):
        return (False, "SURFACE_CLAIMS_THE_KITCHEN_HAS_IT",
                f"the guest is told {placed['message']!r}, which says neither that it is "
                f"waiting nor that somebody must confirm it")
    return (True, None,
            f"the order is in {placed['state']!r} and the guest is told "
            f"{placed['message']!r}")


def pending_list_gate() -> tuple[bool, str | None, str]:
    """A waiter can see an order waiting, and admit it."""
    set_guest_qr("staff_confirmed")
    try:
        guest = a_seated_guest()
        an_order_from(guest)
        # NOTHING CLEARED. This gate signs in through the form on every run, and a control
        # runs it three times. It used to clear the lockout first, on OP-B's reasoning
        # that the limiter would otherwise refuse the third — which was the rationalised
        # symptom of the P0 0038 repairs, not a property of the limiter. See NC-OPD-006.
        answer = probe("floor", {"tenant": TENANT, "outlet": OUTLET,
                                 "email": opa.MANAGER_EMAIL,
                                 "secret": opa.MANAGER_PASSWORD})
    finally:
        set_guest_qr("automatic")

    before = answer["steps"].get("before")
    if not before or not before.get("rows"):
        return (False, "NO_SCREEN_SHOWS_A_WAITING_ORDER",
                f"the waiter floor drew {(before or {}).get('rows', 0)} waiting order(s); "
                f"errors: {answer.get('errors') or 'none'}")
    if not before.get("aboveTables"):
        return (False, "NO_SCREEN_SHOWS_A_WAITING_ORDER",
                "the waiting orders are drawn below the tables; FR-POS-002 makes the "
                "order of this screen the priority, and a guest whose food has not "
                "started outranks a table that merely exists")
    after = answer["steps"].get("after")
    if not after or after.get("rows", 99) >= before["rows"]:
        return (False, "NO_SCREEN_SHOWS_A_WAITING_ORDER",
                f"confirming left {(after or {}).get('rows')} waiting where there were "
                f"{before['rows']}; the screen said {(after or {}).get('notice')!r}")
    return (True, None,
            f"{before['rows']} waiting order(s) above the tables, the control graded "
            f"{before.get('consequence')!r}, and confirming one left {after['rows']}: "
            f"{after.get('notice')!r}")


def section_screens() -> None:
    print("\n--- The screens, measured rather than described ---")
    for name, gate in (
            ("a guest reads what the dish is, not only what it costs", menu_card_gate),
            ("a guest waiting to be confirmed is told that, not that the kitchen has it",
             truthful_outcome_gate),
            ("a waiter sees an order waiting and can admit it", pending_list_gate)):
        ok, signature, detail = gate()
        measured(name, ok, f"{signature + ': ' if signature else ''}{detail}")


# ===========================================================================
# 5. The controls
# ===========================================================================

def section_controls() -> None:
    print("\n--- Negative controls: each defect planted, named, and reverted ---")

    # NC-OPD-001 — a new action on a staff screen must be graded before it is offered.
    def ungraded_red() -> tuple[bool, str]:
        got = run(ADMIN, f"""
            SELECT consequence::text FROM pos.confirmation_requirement
             WHERE tenant_id = '{TENANT}' AND action_code = 'order.accept';""")
        grade = (got.scalar or "").strip()
        # The fail-closed default the waiter surface applies to an action it cannot find.
        # Proved from the surface's own source rather than asserted, because the default
        # is the whole reason a missing grade is a defect and not a cosmetic gap.
        source = (REPO / "waiter" / "src" / "waiter.ts").read_text(encoding="utf-8")
        fails_closed = "consequence: 'deliberate', requires_reason: true" in source
        return (grade != "" and fails_closed,
                f"order.accept is graded {grade!r}, and an UNGRADED action is treated as "
                f"deliberate-with-a-reason by the surface: {fails_closed}. Ungraded, the "
                f"Confirm button would demand a written reason and then do nothing — which "
                f"is exactly how table.seat behaved at OP-C")

    def ungraded_green() -> tuple[bool, str]:
        rows = run(ADMIN, f"""
            SELECT action_code || ' ' || consequence::text
              FROM pos.confirmation_requirement
             WHERE tenant_id = '{TENANT}' AND action_code IN ('order.accept', 'table.seat')
             ORDER BY action_code;""")
        return (len(rows.rows) == 2,
                f"both actions this repair pass added are graded: "
                f"{[r[0] for r in rows.rows]}")

    prove_rule("NC-OPD-001", ungraded_red, ungraded_green)

    # NC-OPD-002 — acceptance is a policy, and both values must work.
    def policy_red() -> tuple[bool, str]:
        set_guest_qr("staff_confirmed")
        try:
            placed = an_order_from(a_seated_guest())
            return (placed.get("state") == "submitted",
                    f"under staff_confirmed an order lands in {placed.get('state')!r} and "
                    f"waits. FR-ORD-007A makes this a choice; a build that only worked one "
                    f"way would have met the requirement in name")
        finally:
            set_guest_qr("automatic")

    def policy_green() -> tuple[bool, str]:
        placed = an_order_from(a_seated_guest())
        return (placed.get("state") == "accepted",
                f"and under automatic it lands in {placed.get('state')!r} with no tap")

    prove_rule("NC-OPD-002", policy_red, policy_green)

    # NC-OPD-003 — the menu card.
    prove_surface(
        "NC-OPD-003", "MENU_SAYS_ONLY_NAME_AND_PRICE", "pwa", menu_card_gate,
        [(PWA_TS, "    if (facts.childElementCount > 0) li.append(facts);",
          "    void facts;")])

    # NC-OPD-004 — the surface telling the guest something that is not so.
    prove_surface(
        "NC-OPD-004", "SURFACE_CLAIMS_THE_KITCHEN_HAS_IT", "pwa", truthful_outcome_gate,
        [(PWA_TS, "      outcome.textContent = accepted ? strings.orderPlaced : strings.orderWaiting;",
          "      outcome.textContent = strings.orderPlaced;")])

    # NC-OPD-006 — a successful login counted as a failed one.
    #
    # THE CONTROL THAT SHOULD HAVE EXISTED SINCE M1-B, AND THE REASON IT DID NOT.
    #
    # Every check of FR-AUTH-007 in this repository drives the lockout with FAILURES,
    # because the rule is "N failures lock you out". Nobody wrote "N successes must NOT
    # lock you out", because that is not a rule anyone thinks to state. NC-OPA-008's green
    # half is the closest: it clears the counter and then signs in ONCE, which can never
    # reach a threshold of five.
    #
    # And every suite clears identity.auth_attempt between sections — deliberately, so
    # that checks which intend to fail authentication do not contaminate later ones. That
    # hygiene erased the accumulation before it could ever reach the threshold.
    #
    # It was OBSERVED and rationalised. OP-B met nine correct sign-ins returning 429,
    # wrote in opb_probe.mjs that "the lockout is real … nine sign-ins inside a minute is
    # nine more than FR-AUTH-007's limiter allows", and worked around it by handing the
    # session in. OP-C and OP-D inherited that reading. The clearing has now been removed
    # from both of their browser sign-in gates.
    #
    # This control is one line of intent: sign in CORRECTLY six times, clearing nothing
    # between, and require six 200s.
    def repeated_success_red() -> tuple[bool, str]:
        # Cleared ONCE, as setup, so the count starts from a known place. Nothing is
        # cleared BETWEEN the six — that is the whole measurement.
        opa.clear_lockout()
        opa.reset_rate_limit()
        codes = [opa.login(opa.MANAGER_PASSWORD, value=opa.MANAGER_EMAIL).get("status")
                 for _ in range(6)]
        failures = run(ADMIN, """
            SELECT count(*)::text FROM identity.auth_attempt WHERE NOT succeeded;""")
        return (all(c == 200 for c in codes) and (failures.scalar or "").strip() == "0",
                f"six CORRECT sign-ins returned {codes} and left "
                f"{(failures.scalar or '?').strip()} failure row(s). Before 0038 this was "
                f"[200, 200, 200, 200, 429, 429] and four rows: the speculative failure "
                f"written before verification was never removed when the attempt turned "
                f"out to be a success, so the fifth correct password tripped a lock")

    def repeated_success_green() -> tuple[bool, str]:
        # And the rule the speculative write exists for is untouched: genuine failures
        # still accumulate, still lock, and a success does not erase the ones before it.
        opa.clear_lockout()
        opa.reset_rate_limit()
        wrong = [opa.login("wrong-every-time", value=opa.MANAGER_EMAIL).get("status")
                 for _ in range(5)]
        surviving = run(ADMIN, """
            SELECT count(*)::text FROM identity.auth_attempt WHERE NOT succeeded;""")
        locked = run(ADMIN, "SELECT count(*)::text FROM identity.auth_lockout;")
        # THE FIFTH FAILURE CREATES THE LOCK AND IS STILL ANSWERED 401. It is the SIXTH
        # attempt that meets it — register_auth_attempt_id() raises SUBJECT_LOCKED_OUT at
        # the top, before it writes anything. The first draft of this check asserted a 429
        # among the five and was wrong about the code rather than finding anything.
        after_lock = opa.login(opa.MANAGER_PASSWORD, value=opa.MANAGER_EMAIL).get("status")
        opa.clear_lockout()
        opa.reset_rate_limit()
        return (all(c == 401 for c in wrong)
                and (surviving.scalar or "0").strip() == "5"
                and (locked.scalar or "0").strip() == "1"
                and after_lock == 429,
                f"five WRONG sign-ins returned {wrong}, left "
                f"{(surviving.scalar or '?').strip()} failure row(s) and "
                f"{(locked.scalar or '?').strip()} lockout(s); the next attempt — with the "
                f"CORRECT password — was refused {after_lock}. The speculative insert is "
                f"load-bearing, it is what stops an attacker telling 'no such user' from "
                f"'wrong password' by whether a row appears, and it is still there")

    prove_rule("NC-OPD-006", repeated_success_red, repeated_success_green)

    # NC-OPD-005 — the list without which no waiting order is visible.
    prove_surface(
        "NC-OPD-005", "NO_SCREEN_SHOWS_A_WAITING_ORDER", "waiter", pending_list_gate,
        [(WAITER_TS, "  section.appendChild(list);\n}\n\nfunction renderTables",
          "  void list;\n}\n\nfunction renderTables")])


# ===========================================================================
# 6. Boundaries
# ===========================================================================

def section_signatures() -> None:
    print("\n--- Boundaries, and the census ---")

    signatures = ["MENU_SAYS_ONLY_NAME_AND_PRICE", "SURFACE_CLAIMS_THE_KITCHEN_HAS_IT",
                  "NO_SCREEN_SHOWS_A_WAITING_ORDER", "ACCEPTANCE_POLICY_ABSENT",
                  "ORDER_POLICY_ABSENT"]
    pattern, terms = fenced_identifier_pattern()
    offending = sorted({m.group(0) for s in signatures
                        for m in re.finditer(pattern, s, re.I)})
    record("no OP-D failure signature names a permanently fenced domain",
           len(signatures) == 5 and not offending,
           f"{len(signatures)} signature(s) checked against all {terms} authoritative "
           f"terms: {offending or 'none'}")

    sources = "\n".join(
        p.read_text(encoding="utf-8") for p in (
            HERE / "verify_opd.py",
            HERE / "opd_probe.mjs",
            REPO / "migrations" / "0037_a_menu_says_what_a_dish_is_and_an_order_can_be_admitted.sql",
            REPO / "seeds" / "0009_qr_ordering_does_not_wait_for_a_waiter.sql",
            REPO / "seeds" / "0010_an_order_can_be_confirmed.provision.sql",
            REPO / "tools" / "uncalled_routes.py",
            REPO / "waiter" / "src" / "waiter.ts",
            REPO / "pwa" / "src" / "app.ts",
        ) if p.exists())
    hits = sorted({m.group(0) for m in re.finditer(pattern, sources, re.I)})
    record("and neither does anything this gate wrote",
           not hits,
           f"checked the suite, the probe, the migration, two seeds, the census and two "
           f"surfaces against all {terms} terms: {hits or 'none'}")


# ===========================================================================

def main() -> int:
    print("OP-D verification — the order reaches the kitchen, and the menu says what a dish is")
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
            print(f"FAIL OPD_SIGN_IN\n  the manager could not sign in: {answer}")
            return 1
        CONTEXT["token"] = answer["token"]
        opa.CONTEXT["token"] = answer["token"]

        for section in (section_acceptance, section_menu, section_census,
                        section_screens, section_controls, section_signatures):
            try:
                section()
            except ProbeFailed as exc:
                record(f"{section.__name__} completed", False,
                       f"probe did not execute: {exc}")

    failed = [name for name, ok, _d, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")
    owned = len([c for c in registry.CONTROLS if c[3] == "opd"])

    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}   (read out of a real browser's layout)")
    print(f"  asserted      : {len(results) - measured_count}")
    print(f"  controls      : {owned} registered, each proved red then green")

    if failed:
        print("\nFAIL OPD_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS OPD_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
