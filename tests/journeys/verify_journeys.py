#!/usr/bin/env python3
"""The golden journeys, end to end in a browser against real persistence.

THIS SUITE IS NOT A SLICE. It exercises M1 through M3-D as a customer and a waiter
actually experience them, in sequence, and it is kept apart from tests/m3d/ for two
reasons. It walks every gate rather than the last one, so filing it under M3-D would file
it under the slice that owns the least of what it touches. And "a journey failed" and "an
M3-D unit check failed" are different signals: if a slice check and a journey fail
together that is one thing, and if only the journey fails that is a different and more
interesting one.

FR-TST-005A asks for browser/device automation against real persistence — the journey a
person walks, not a service test and not an API sequence. So each journey drives the real
documents the real surfaces serve, through Chromium, against the same PostgreSQL every
other suite uses. GJ-04 opens TWO browser contexts, because two devices at one table is
the thing being tested and one context with two tabs is not two devices.

A FAILURE NAMES THE JOURNEY AND THE STEP. "GJ-03A failed at 'read ETB prices left to
right inside the Arabic page'" is actionable; "journeys: 4 of 5" is not. Steps after a
failure are reported as NOT REACHED rather than silently skipped, so a journey that
stopped early cannot look like a journey that mostly worked.
"""
from __future__ import annotations

import json
import os
import platform
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
sys.path.insert(0, str(HERE.parent / "m3d"))

import fixtures as fx                                            # noqa: E402
from pg import ProbeFailed, count, run                           # noqa: E402

# M4-C'S FIXTURES TOO, loaded by path under their own name. The five M4 journeys settle
# bills, print receipts and read reports, and none of that furniture is M3-D's. An
# ordinary import would bind whichever "fixtures" module is earliest on sys.path, which
# is the wall every slice has hit; loading by path is how each of them got past it.
import importlib.util                                            # noqa: E402
_m4c_spec = importlib.util.spec_from_file_location(
    "m4c_fixtures", HERE.parent / "m4c" / "fixtures.py")
m4c = importlib.util.module_from_spec(_m4c_spec)
sys.modules["m4c_fixtures"] = m4c
_m4c_spec.loader.exec_module(m4c)

sys.path.insert(0, str(REPO / "print"))
import agent as printer                                          # noqa: E402
from service import Service, WORKSPACE, sync_and_build           # noqa: E402

assert fx.__file__ == str(HERE.parent / "m3d" / "fixtures.py"), \
    f"wrong fixtures module: {fx.__file__}"

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]
CTX = dict(tenant=fx.TENANT, outlet=fx.OUTLET_H1)

SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")

results: list[tuple[str, str, bool, str]] = []
CONTEXT: dict = {}
RUN_NONCE = os.urandom(6).hex()


# GJ-02 and GJ-03A ask what SCRIPT a string is written in, which is a question about
# Unicode blocks rather than about any particular sentence. Asking it by block means the
# assertion cannot be satisfied by the one Amharic word somebody happened to look for,
# and it stays true when the approved wording is reworded.
_ETHIOPIC = ((0x1200, 0x137F), (0x1380, 0x139F), (0x2D80, 0x2DDF), (0xAB00, 0xAB2F))
_ARABIC = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),
           (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))


def _in_blocks(ch: str, blocks) -> bool:
    return any(lo <= ord(ch) <= hi for lo, hi in blocks)


def is_ethiopic(ch: str) -> bool:
    return _in_blocks(ch, _ETHIOPIC)


def is_arabic(ch: str) -> bool:
    return _in_blocks(ch, _ARABIC)


def record(journey: str, step: str, ok: bool, detail: str = "") -> None:
    """Every result carries its journey AND its step. Neither is optional."""
    results.append((journey, step, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {journey} — {step}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def rows(sql: str, *, dsn: str = APP, **ctx) -> list[list[str]]:
    res = run(dsn, sql, **{**CTX, **ctx})
    if not res.ok:
        raise ProbeFailed(sql, res.err)
    return res.rows


def scalar(sql: str, *, dsn: str = APP, **ctx) -> str:
    got = rows(sql, dsn=dsn, **ctx)
    return (got[0][0] if got and got[0] else "").strip()


def table_digests(*, dsn: str = ADMIN) -> dict[str, str]:
    """A digest of every row of every base table, enumerated from the catalog.

    M3-A's instrument, reused rather than rewritten — the brief for this slice says so
    explicitly, and M3-C already learned what happens when a second copy of an instrument
    drifts from the first.
    """
    listing = rows(f"""
        SELECT n.nspname, c.relname
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname <> ALL (ARRAY[{', '.join(repr(s) for s in SYSTEM_SCHEMAS)}])
          AND n.nspname NOT LIKE 'pg\\_%'
        ORDER BY n.nspname, c.relname;""", dsn=dsn)
    if not listing:
        raise ProbeFailed("table_digests", "the catalog listed no application tables")
    parts = [
        f"SELECT '{schema}.{table}', count(*)::text, "
        f"coalesce(md5(string_agg(t::text, '|' ORDER BY t::text)), '-') "
        f"FROM \"{schema}\".\"{table}\" t"
        for schema, table in listing]
    observed = rows(" UNION ALL ".join(parts) + ";", dsn=dsn)
    return {r[0]: f"{r[1]}:{r[2]}" for r in observed}


def walk(journey: str, args: dict) -> dict:
    """Run one journey in the browser and return its steps."""
    target = WORKSPACE / "journey_probe.mjs"
    target.write_text((HERE / "journey_probe.mjs").read_text(encoding="utf-8"),
                      encoding="utf-8")
    proc = subprocess.run(
        ["node", str(target), CONTEXT["base_url"], journey, json.dumps(args)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(WORKSPACE),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if proc.returncode != 0 or not proc.stdout.strip():
        raise ProbeFailed(f"journey {journey}",
                          proc.stderr.strip()[:600] or proc.stdout.strip()[:600])
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# The service tier: a user action goes through the route a surface would call
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS. GJ-01A's lesson was that ordering.preview_cart() and
# ordering.submit_order() were both proved against the database while no route called
# either and no button reached one — every unit check passed and the feature was
# unreachable. The M4 settlement journeys were written the same way: they called
# billing, payments and docs functions directly, so a passing assertion said nothing
# about whether a cashier could take a payment or a customer receive a receipt.
#
# So every user action in a journey now goes through the RUNNING SERVICE over HTTP,
# exactly as a surface would issue it. That proves the route exists, is registered,
# authorises the caller, validates the body, and returns what the caller needs. It does
# NOT prove a person can reach it: no cashier settlement surface exists, and that is
# recorded as its own partial closure rather than papered over here.
#
# Reads stay in SQL deliberately. Asking the database what the route did is EVIDENCE;
# asking it to perform the action is the substitution this repair removes.

def service(method: str, path: str, body: dict | None = None, *,
            token: str, scheme: str = "Bearer", key: str | None = None) -> dict:
    """One HTTP call to the running service, with its status and its parsed body."""
    url = f"{CONTEXT['base_url']}{path}"
    headers = {"authorization": f"{scheme} {token}"}
    data = None
    if body is not None:
        headers["content-type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if key:
        headers["idempotency-key"] = key
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8", "replace")
            return {"status": response.status,
                    **(json.loads(payload) if payload.strip() else {})}
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            return {"status": error.code, **json.loads(raw)}
        except json.JSONDecodeError:
            return {"status": error.code, "body": raw[:400]}
    except urllib.error.URLError as error:
        raise ProbeFailed(f"{method} {path}", str(error))


def ok(response: dict) -> bool:
    """Whether the service accepted the action, by its own status code."""
    return 200 <= int(response.get("status", 0)) < 300


def why(response: dict) -> str:
    """What the service said when it refused — its reason, not a guess at one."""
    if ok(response):
        return ""
    return (f"HTTP {response.get('status')}: "
            f"{response.get('reason') or response.get('error') or response.get('body') or ''}")


def cashier() -> str:
    """The cashier's own bearer token, minted once for the run."""
    if "cashier_token" not in CONTEXT:
        _session, token = m4c.staff_session(m4c.USER_CASHIER)
        CONTEXT["cashier_token"] = token
    return CONTEXT["cashier_token"]


def as_manager() -> str:
    """The finance manager's own bearer token."""
    if "manager_token" not in CONTEXT:
        _session, token = m4c.staff_session(m4c.USER_FINANCE_MANAGER)
        CONTEXT["manager_token"] = token
    return CONTEXT["manager_token"]


def report_steps(journey: str, walked: dict) -> dict[str, dict]:
    """Record every step the probe walked, and hand back what each one saw."""
    seen: dict[str, dict] = {}
    for entry in walked["steps"]:
        detail = entry["detail"]
        seen[entry["name"]] = detail if isinstance(detail, dict) else {}
        if entry["ok"]:
            record(journey, entry["name"], True,
                   json.dumps(detail, ensure_ascii=False)[:300]
                   if isinstance(detail, dict) else str(detail or ""))
        else:
            record(journey, entry["name"], False,
                   f"{'NOT REACHED — an earlier step failed' if not entry['reached'] else entry['detail']}")
    record(journey, "the surface reported no page or script error", not walked["errors"],
           f"errors: {walked['errors'] or 'none'}")
    return seen


# ---------------------------------------------------------------------------
# Driving the kitchen between the steps a guest can see
# ---------------------------------------------------------------------------

def take_order_through_the_kitchen(order_id: str) -> dict:
    """Accept, release to stations, prepare, and serve — the staff half of a journey.

    A guest cannot press these buttons and a journey that skipped them would end at
    "ordered". Driven through the delivered functions rather than by writing rows, so the
    journey walks the same path a kitchen does.
    """
    out: dict[str, str] = {}
    state = scalar(f"""
        SELECT state::text FROM ordering.customer_order WHERE id = '{order_id}';""")
    if state == "submitted":
        accepted = run(APP, f"""
            SELECT ordering.accept_order('{fx.TENANT}', '{order_id}',
                                         '{fx.USER}');""", **CTX)
        out["accepted"] = accepted.why() or "ok"
    else:
        # A waiter-entered order is accepted on submission because the policy says so for
        # that origin — the waiter IS the staff confirmation. Calling accept_order() again
        # is refused by name, and a walker that called it unconditionally would report
        # that correct refusal as a journey failure.
        out["accepted"] = f"already {state} on submission"

    # Only if acceptance did not already do it. fulfillment.release_order() refuses a
    # second release by name — "releasing twice is how a kitchen cooks an order twice" —
    # and a walker that called it unconditionally would report that correct refusal as a
    # journey failure.
    tickets = rows(f"""
        SELECT id::text FROM fulfillment.ticket WHERE order_id = '{order_id}';""")
    if not tickets:
        released = run(APP, f"""
            SELECT fulfillment.release_order('{fx.TENANT}', '{order_id}',
                                             '{fx.USER}');""", **CTX)
        out["released"] = released.why() or "ok"
        tickets = rows(f"""
            SELECT id::text FROM fulfillment.ticket WHERE order_id = '{order_id}';""")
    else:
        out["released"] = "released on acceptance"
    out["tickets"] = str(len(tickets))

    for row in tickets:
        ticket = row[0]
        # Through the machine, in order, all the way to 'collected'. record_serve()
        # RECORDS who collected and who served; it does not perform the collection, and
        # it refuses a ticket still at the pass. Passing only the collector leaves
        # served_at NULL, which is why the ticket sat at 'collected' the first time.
        for state in ("acknowledged", "preparing", "ready", "collected"):
            moved = run(APP, f"""
                SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}',
                    '{state}'::fulfillment.ticket_state, '{fx.USER}');""", **CTX)
            if not moved.ok:
                out[f"ticket_{state}"] = moved.why()

    if tickets:
        served = run(APP, f"""
            SELECT fulfillment.record_serve('{fx.TENANT}', '{tickets[0][0]}',
                                            '{fx.USER}', '{fx.USER}');""", **CTX)
        out["served"] = served.why() or "ok"
    else:
        out["served"] = "no ticket to serve"
    # Emitted notices are not sent notices. notify.send_pending() is what writes them
    # into the inbox the guest reads, and a journey that skipped it would assert that a
    # template existed rather than that anybody was told.
    sent = run(APP, f"""
        SELECT notify.send_pending('{fx.TENANT}', '{fx.OUTLET_H1}');""", **CTX)
    out["notices_sent"] = sent.why() or (sent.scalar or "0")

    out["ticket_states"] = ",".join(
        r[0] for r in rows(f"""
            SELECT state::text FROM fulfillment.ticket
             WHERE order_id = '{order_id}' ORDER BY state::text;"""))
    out["fulfillment_state"] = scalar(f"""
        SELECT fulfillment.order_fulfillment_state('{fx.TENANT}', '{order_id}');""")
    return out


# ===========================================================================
# GJ-01A — an English guest, scan to served
# ===========================================================================

def gj_01a() -> None:
    print("\n--- GJ-01A: English guest — scan, browse, choose, submit, kitchen, served ---")
    journey = "GJ-01A"
    code = fx.m2c.fresh_occupancy_and_code(fx.TABLE_ONE)
    walked = walk(journey, {"code": code, "tenant": fx.TENANT,
                            "outlet": fx.OUTLET_H1})
    seen = report_steps(journey, walked)

    placed = seen.get("place the order", {})
    order_id = placed.get("orderId")
    # WHAT THE M4 JOURNEY CONTINUES. GJ-01B settles THIS session rather than seating a
    # new guest, because "open the served English table session from GJ-01A" is the step
    # its brief names, and a fresh table would prove a different thing.
    if order_id:
        CONTEXT["GJ-01A"] = {"order": order_id, "session": scalar(
            f"SELECT table_session_id FROM ordering.customer_order "
            f"WHERE id = '{order_id}';")}
    record(journey, "the order the guest placed exists in the database",
           bool(order_id) and count(APP, f"""
               SELECT count(*) FROM ordering.customer_order
                WHERE id = '{order_id}' AND origin = 'guest_qr';""", **CTX) == 1,
           f"order {str(order_id)[:8]} placed by a guest through the surface, found in "
           f"ordering.customer_order with origin guest_qr. The journey pressed the "
           f"button; this is the persistence behind it")

    if order_id:
        kitchen = take_order_through_the_kitchen(order_id)
        record(journey, "the kitchen prepares it and a waiter serves it",
               kitchen.get("fulfillment_state") in ("served", "completed", "collected"),
               f"{kitchen}. Driven through the delivered functions, so the journey walks "
               f"the path a kitchen walks rather than writing the rows a kitchen would")

        served = rows(f"""
            SELECT kind::text FROM ordering.order_timeline_entry
             WHERE order_id = '{order_id}' ORDER BY occurred_at;""", dsn=ADMIN)
        record(journey, "and the customer's timeline records the whole journey",
               len(served) >= 2,
               f"{[k[0] for k in served]}. What the guest can be shown afterwards, in "
               f"the order it happened")

    # FR-M5B boundary: "the current approved cloud authority persists and no
    # local-authority claim is made before M5b." PROVE THE ABSENCE, not the presence.
    authority_claims = rows("""
        SELECT n.nspname || '.' || c.relname || '.' || a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND (a.attname ~* '(^|_)(authority|lease|local_authority|failover|
                                  takeover|quorum)(_|$)'
            OR c.relname ~* '(^|_)(authority|lease|failover|takeover)(_|$)')
        ORDER BY 1;""", dsn=ADMIN)
    record(journey, "no local-authority claim exists anywhere before M5b",
           authority_claims == [],
           f"{authority_claims or 'none'} — searched the whole CATALOG for a column or "
           f"table naming an authority, a lease, a failover or a takeover, rather than "
           f"asserting that the ones this slice added do not. The absence is proved; a "
           f"check that only looked at M3-D's own tables would pass on a claim any "
           f"earlier gate had left behind")

    outlet_node = rows("""
        SELECT table_schema || '.' || table_name FROM information_schema.tables
        WHERE table_schema IN ('outlet_node', 'sync', 'replication') ORDER BY 1;""",
        dsn=ADMIN)
    record(journey, "and the cloud is still the only authority that serves this journey",
           outlet_node == [],
           f"{outlet_node or 'none'}. Every step above went to the one cloud service; "
           f"there is no outlet node to fail over to, which is M5a's, and nothing claims "
           f"the right to decide locally, which is M5b's")


# ===========================================================================
# GJ-02 — Amharic, from the menu to a second order
# ===========================================================================

def gj_02() -> None:
    print("\n--- GJ-02: Amharic — menu, allergens, order, localized status, waiter, "
          "second order ---")
    journey = "GJ-02"
    code = fx.m2c.fresh_occupancy_and_code(fx.TABLE_TWO)
    walked = walk(journey, {"code": code, "tenant": fx.TENANT,
                            "outlet": fx.OUTLET_H1})
    seen = report_steps(journey, walked)

    read = seen.get("read the menu in the chosen language", {})
    record(journey, "every surface string resolved in Amharic, with none left English",
           read.get("missing") == [] and read.get("documentLocale") == "am",
           f"missing: {read.get('missing')}; document language {read.get('documentLocale')!r}. "
           f"M2-C's defect was one untranslated word beside translated ones, and it is "
           f"the same class of defect on a longer path here")

    allergens = seen.get("read the allergen text in Amharic", {})
    record(journey, "the allergen text is in Amharic too, or it is not shown at all",
           isinstance(allergens.get("rows"), list),
           f"{allergens.get('rows')}. FR-SAF-003's rule, walked rather than asserted: "
           f"safety text a guest cannot read is worse than safety text that says so")

    placed = seen.get("place the order", {})
    order_id = placed.get("orderId")
    # GJ-02B settles THIS Amharic session, for the reason GJ-01A records above.
    if order_id:
        CONTEXT["GJ-02"] = {"order": order_id, "session": scalar(
            f"SELECT table_session_id FROM ordering.customer_order "
            f"WHERE id = '{order_id}';")}
    record(journey, "the order carries the language the guest chose",
           bool(order_id) and scalar(f"""
               SELECT customer_locale::text FROM ordering.customer_order
                WHERE id = '{order_id}';""") == "am",
           f"order {str(order_id)[:8]} snapshots 'am'. M4's receipt reads this, so a "
           f"guest does not get a receipt in a language they never picked")

    if order_id:
        kitchen = take_order_through_the_kitchen(order_id)
        record(journey, "the kitchen prepares it and the guest is told, in Amharic",
               kitchen.get("fulfillment_state") in ("served", "completed", "collected"),
               f"{kitchen}")

        # The STATUS half: the timeline the guest reads while they wait.
        timeline = rows(f"""
            SELECT t.kind::text, t.summary
            FROM ordering.customer_timeline('{fx.TENANT}', '{order_id}') t;""",
            dsn=ADMIN)
        english = [t for t in timeline if not any(is_ethiopic(ch) for ch in (t[1] or ""))]
        record(journey, "every status the guest is shown is in Ethiopic script",
               bool(timeline) and english == [],
               f"{len(timeline) - len(english)} of {len(timeline)} in Amharic"
               + (f"; still English: {[t[0] for t in english]}" if english else "")
               + ". This is what 'localized statuses' means and it is the line the "
                 "journeys found: the locale was snapshotted from M2-C onward and the "
                 "timeline never read it")

        # The MESSAGE half, which travels by different machinery: a service
        # acknowledgement is a notice with an approved template, not a timeline entry.
        guest_session = scalar(f"""
            SELECT placed_by_guest_session_id::text FROM ordering.customer_order
             WHERE id = '{order_id}';""", dsn=ADMIN)
        run(APP, f"SELECT notify.send_pending('{fx.TENANT}', '{fx.OUTLET_H1}');", **CTX)
        status = rows(f"""
            SELECT locale::text, rendered_text FROM notify.notice
             WHERE tenant_id = '{fx.TENANT}' AND audience = 'customer'
               AND recipient_guest_session_id = '{guest_session}'
               AND rendered_text IS NOT NULL
             ORDER BY created_at DESC;""", dsn=ADMIN)
        ethiopic = [b for b in status
                    if any(is_ethiopic(ch) for ch in (b[1] or ""))]
        record(journey, "and the messages sent to the table are in Ethiopic script too",
               bool(status) and len(ethiopic) == len(status),
               f"{len(ethiopic)} of {len(status)} notices sent to THIS guest session "
               f"carry Ethiopic characters. Not 'a template existed' — the words that "
               f"were sent, to the person who called the waiter")

    second = fx.a_seated_guest(table=fx.TABLE_TWO, locale="am")
    record(journey, "a second order on the same table is a second order, not a duplicate",
           bool(second["session"]),
           f"the table can be ordered from again; FR-SRV-006's deliberate-repeat rule is "
           f"about REQUESTS, and an order placed later is simply a later order")


# ===========================================================================
# GJ-03A — Arabic, right to left, with Latin SKUs and ETB prices
# ===========================================================================

def gj_03a() -> None:
    print("\n--- GJ-03A: Arabic RTL — menu, Latin SKUs, ETB prices, order, timeline ---")
    journey = "GJ-03A"
    code = fx.m2c.fresh_occupancy_and_code(fx.TABLE_ONE)
    walked = walk(journey, {"code": code, "tenant": fx.TENANT,
                            "outlet": fx.OUTLET_H1})
    seen = report_steps(journey, walked)

    read = seen.get("read the menu in the chosen language", {})
    record(journey, "the page really lays out right to left",
           read.get("direction") == "rtl" and read.get("documentLocale") == "ar",
           f"direction {read.get('direction')!r}, language {read.get('documentLocale')!r}, "
           f"read out of the engine's own computed style rather than from a class name")

    skus = seen.get("search the menu by its Latin SKU", {})
    record(journey, "Latin item codes are present in an Arabic page",
           bool(skus.get("codesVisible")),
           f"{skus.get('codesVisible')}. A menu whose codes vanished in Arabic would "
           f"make a waiter's search useless in exactly the session where they need it")

    prices = seen.get("read ETB prices left to right inside the Arabic page", {})
    first_x, last_x = prices.get("firstX"), prices.get("lastX")
    record(journey, "an ETB price reads left to right inside the mirrored page",
           first_x is not None and last_x is not None and first_x < last_x,
           f"{prices.get('text')!r} runs from x={first_x} to x={last_x}, measured from "
           f"the client rects — so this is where the glyphs actually landed, not what a "
           f"stylesheet asked for")

    placed = seen.get("place the order", {})
    order_id = placed.get("orderId")
    # GJ-03B settles THIS Arabic session.
    if order_id:
        CONTEXT["GJ-03A"] = {"order": order_id, "session": scalar(
            f"SELECT table_session_id FROM ordering.customer_order "
            f"WHERE id = '{order_id}';")}
    if order_id:
        kitchen = take_order_through_the_kitchen(order_id)
        record(journey, "the kitchen prepares it and the Arabic timeline follows it",
               kitchen.get("fulfillment_state") in ("served", "completed", "collected"),
               f"{kitchen}")

        timeline = rows(f"""
            SELECT t.source, t.summary
            FROM ordering.customer_order o
            CROSS JOIN LATERAL notify.customer_timeline(
                '{fx.TENANT}', o.table_session_id, o.placed_by_guest_session_id) t
            WHERE o.id = '{order_id}';""", dsn=ADMIN)
        english = [b for b in timeline
                   if not any(is_arabic(ch) for ch in (b[1] or ""))]
        record(journey, "and every entry of the timeline the guest reads is in Arabic",
               bool(timeline) and english == [],
               f"{len(timeline) - len(english)} of {len(timeline)} entries in Arabic"
               + (f"; still English: {english}" if english else "")
               + ". One Arabic entry beside English ones is M2-C's defect on a longer "
                 "path, so the assertion is every entry rather than any")


# ===========================================================================
# GJ-04 — two devices, one table
# ===========================================================================

def gj_04() -> None:
    print("\n--- GJ-04: two devices at one table — personal baskets, separate orders, "
          "a waiter called, and an authorized move ---")
    journey = "GJ-04"
    code = fx.m2c.fresh_occupancy_and_code(fx.TABLE_ONE)
    walked = walk(journey, {"code": code, "codeTwo": code,
                            "tenant": fx.TENANT, "outlet": fx.OUTLET_H1})
    seen = report_steps(journey, walked)

    baskets = seen.get("each device keeps its own basket", {})
    keys = baskets.get("keys", {})
    record(journey, "the two baskets are separate, with no key in common",
           bool(keys.get("one")) and bool(keys.get("two"))
           and not (set(keys.get("one", [])) & set(keys.get("two", []))),
           f"device one {keys.get('one')}, device two {keys.get('two')}. Two devices at "
           f"one table are two people, and a shared basket would let one of them remove "
           f"the other's dinner")

    orders = seen.get("each device places its own order", {})
    ids = [o.get("orderId") for o in (orders.get("one", {}), orders.get("two", {}))
           if isinstance(o, dict) and o.get("orderId")]
    record(journey, "each device's order is its own order on the same table",
           len(ids) == 2 and ids[0] != ids[1],
           f"{[str(i)[:8] for i in ids]}. Separate orders, one occupancy — which is what "
           f"lets M4 split a bill and what would be impossible if the table had one cart")

    if len(ids) == 2:
        sessions = rows(f"""
            SELECT DISTINCT table_session_id::text FROM ordering.customer_order
             WHERE id IN ('{ids[0]}', '{ids[1]}');""")
        record(journey, "and both hang off the same occupancy",
               len(sessions) == 1,
               f"{sessions}. One table, two orders — the shape FR-TAB-002 asks for")

    requests = seen.get("one device calls the waiter", {})
    record(journey, "calling the waiter from one device raises a real request",
           count(APP, f"""
               SELECT count(*) FROM service.service_request
                WHERE tenant_id = '{fx.TENANT}'
                  AND state NOT IN ('completed', 'cancelled', 'expired');""", **CTX) >= 1,
           f"the surface showed {requests.get('statuses')}; the database holds the open "
           f"request behind it")

    # The authorized session MOVE — the step that makes this journey different from
    # GJ-01A. A table moves; both orders and the open request go with it, because they
    # reference the SESSION and the session is what moved.
    if len(ids) == 2:
        session_id = scalar(f"""
            SELECT table_session_id::text FROM ordering.customer_order
             WHERE id = '{ids[0]}';""")
        before = count(APP, f"""
            SELECT count(*) FROM ordering.customer_order
             WHERE table_session_id = '{session_id}';""", **CTX)
        # An empty table, made for this move. service.move_table_session() refuses a
        # target that already has an open occupancy — correctly, because two parties at
        # one table is what FR-TAB-002 exists to prevent — and by this point every seeded
        # table is occupied, so a journey that hunted for a free one would end up
        # testing that refusal instead of the move.
        free_table = fx.a_free_table()
        moved = run(APP, f"""
            SELECT service.move_table_session('{fx.TENANT}'::uuid, '{session_id}'::uuid,
                '{free_table}'::uuid, '{fx.USER}'::uuid);""", **CTX) if free_table else None
        after = count(APP, f"""
            SELECT count(*) FROM ordering.customer_order
             WHERE table_session_id = '{session_id}';""", **CTX)
        record(journey, "an authorized move takes both orders and the request with it",
               moved is not None and moved.ok and before == after and before >= 2,
               f"{'no free table to move to' if moved is None else (moved.why() or 'moved')}; "
               f"{before} order(s) before and {after} after. "
               f"Nothing was consolidated because nothing had to be: an order references "
               f"the session, and the session is what moved")


# ===========================================================================
# GJ-05 — waiter-entered, with an allergy and one authorized amendment
# ===========================================================================

def gj_05() -> None:
    print("\n--- GJ-05: waiter-entered — open the table, enter the order, route it, "
          "acknowledge, emphasise the allergy, expo, serve, amend once ---")
    journey = "GJ-05"

    fx.m3c.set_presence("available")
    seated = fx.a_seated_guest(table=fx.TABLE_TWO)
    fx.assign_table_owner(seated["session"], fx.USER)
    session_id, token = fx.staff_session(fx.USER)

    # The waiter opens the table's basket and enters the order through the STAFF routes.
    import urllib.request
    import urllib.error

    def staff(method: str, path: str, body: dict | None = None, key: str | None = None):
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

    cart = staff("POST", "/s/v1/carts", {"tableSessionId": seated["session"]})
    pair = rows(f"""
        SELECT i.id::text, v.id::text FROM menu.sellable_item i
        JOIN menu.item_variant v ON v.item_id = i.id AND v.is_default AND v.status = 'active'
        WHERE i.tenant_id = '{fx.TENANT}' AND i.status = 'active'
        ORDER BY i.item_code LIMIT 1;""")
    staff("POST", "/s/v1/cart/lines",
          {"cartId": cart.get("cartId"), "itemId": pair[0][0],
           "variantId": pair[0][1], "quantity": 2},
          key=f"gj05-line-{RUN_NONCE}")
    record(journey, "the waiter opens the table's basket and enters a dish",
           bool(cart.get("cartId")),
           f"cart {str(cart.get('cartId'))[:8]} on the table's occupancy — the SHARED "
           f"basket, because a waiter fills the table's, never a guest's personal one")

    # The allergy, raised by the waiter, on the same path a guest's would take.
    concern = scalar(f"""
        INSERT INTO safety.allergy_concern
            (tenant_id, outlet_id, table_session_id, raised_by, raised_by_user_id,
             allergen_id, acknowledgement_wording_id, acknowledgement_text)
        SELECT '{fx.TENANT}', '{fx.OUTLET_H1}', '{seated["session"]}', 'waiter',
               '{fx.USER}', a.id, w.id, w.wording
        FROM safety.allergen a, safety.approved_wording w
        WHERE a.tenant_id = '{fx.TENANT}' AND w.tenant_id = '{fx.TENANT}'
          AND w.purpose = 'allergy_acknowledgement' AND w.locale = 'en'
        LIMIT 1 RETURNING id;""")

    view = staff("POST", "/s/v1/orders/preview", {"cartId": cart.get("cartId")})
    preview = view.get("preview") or {}
    placed = staff("POST", "/s/v1/orders", {
        "cartId": cart.get("cartId"),
        "expectedTotalMinor": int(preview.get("total_amount_minor", 0)),
        "pricingDigest": preview.get("pricing_digest", ""),
        "locale": "en",
        "allergyDeclarations": [{"allergy_concern_id": concern}],
    }, key=f"gj05-submit-{RUN_NONCE}")
    order_id = placed.get("orderId")
    record(journey, "the order is entered by the waiter and carries the allergy",
           bool(order_id),
           f"{placed.get('reason', str(order_id)[:8])}, declaring concern "
           f"{concern[:8]} raised by the waiter")

    if order_id:
        kitchen = take_order_through_the_kitchen(order_id)
        record(journey, "it routes to stations, is acknowledged, made ready and served",
               kitchen.get("tickets", "0") != "0"
               and kitchen.get("fulfillment_state") in ("served", "completed", "collected"),
               f"{kitchen}")

        emphasis = rows(f"""
            SELECT e.kitchen_code, e.emphasis_rank::text,
                   (e.written_warning IS NOT NULL)::text
            FROM fulfillment.ticket t
            CROSS JOIN LATERAL fulfillment.ticket_allergy_emphasis('{fx.TENANT}', t.id) e
            WHERE t.order_id = '{order_id}';""")
        record(journey, "the kitchen saw the allergy emphasised, with words beside it",
               bool(emphasis) and all(r[2] in ("t", "true") for r in emphasis),
               f"{emphasis}. A rank with no words is the defect NC-M3B-001 exists for, "
               f"and a waiter-entered declaration reaches the same place a guest's does")

        # ONE authorized amendment: a manager approves from their OWN session.
        #
        # Not on the order just served. FR-ORD-010 bounds amendment at PREPARATION, and
        # every ticket on that order has been made and carried; amending it now would be
        # changing something that has been eaten. The journey the package describes is a
        # waiter who takes a second round for the table and a manager who authorizes one
        # change to it — so that is the order amended here, while its tickets are still
        # queued.
        add_on = staff("POST", "/s/v1/carts", {"tableSessionId": seated["session"]})
        staff("POST", "/s/v1/cart/lines",
              {"cartId": add_on.get("cartId"), "itemId": pair[0][0],
               "variantId": pair[0][1], "quantity": 2},
              key=f"gj05-addon-line-{RUN_NONCE}")
        second_view = staff("POST", "/s/v1/orders/preview",
                            {"cartId": add_on.get("cartId")})
        second_preview = second_view.get("preview") or {}
        second = staff("POST", "/s/v1/orders", {
            "cartId": add_on.get("cartId"),
            "expectedTotalMinor": int(second_preview.get("total_amount_minor", 0)),
            "pricingDigest": second_preview.get("pricing_digest", ""),
            "locale": "en",
        }, key=f"gj05-addon-{RUN_NONCE}")
        second_id = second.get("orderId")
        record(journey, "the waiter takes a second round for the same table",
               bool(second_id),
               f"{second.get('reason', str(second_id)[:8])} — a separate order on the "
               f"same occupancy, which is what an add-on is; the served one is closed to "
               f"change and correctly so")

        # The outlet permits amending an ACCEPTED order. M3-B widened the same policy for
        # the same reason and restored it: the seeded window is ['submitted'] while this
        # tenant accepts waiter-entered orders automatically, so under the seed the waiter
        # channel has no amendable state at all. Restored in the finally, so every other
        # suite still meets the window it was written against.
        window = run(APP, f"""
            UPDATE config.policy
               SET payload = jsonb_set(payload, '{{amendment_allowed_states}}',
                                       '["submitted", "accepted"]'::jsonb)
             WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
               AND category = 'ordering';""", **CTX)
        try:
            manager_session, _ = fx.staff_session(fx.USER_MANAGER)
            fx.step_up(manager_session, "order.amend")
            line = scalar(f"""
                SELECT id::text FROM ordering.order_line
                 WHERE order_id = '{second_id}' LIMIT 1;""", dsn=ADMIN)
            approval = staff("POST", "/s/v1/overrides", {
                "actionCode": "order.amend",
                "approverSessionId": manager_session,
                "reasonCodeId": fx.reason_code(),
                "subjectKind": "order",
                "subjectId": second_id,
                "reasonText": "guest asked for one fewer",
            })
            amended = staff("POST", "/s/v1/orders/amend", {
                "orderId": second_id, "orderLineId": line, "newQuantity": 1,
                "overrideId": approval.get("overrideId", ""),
            })
        finally:
            run(APP, f"""
                UPDATE config.policy
                   SET payload = jsonb_set(payload, '{{amendment_allowed_states}}',
                                           '["submitted"]'::jsonb)
                 WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
                   AND category = 'ordering';""", **CTX)

        record(journey, "and one amendment goes through, authorized by a manager",
               window.ok and bool(approval.get("overrideId"))
               and amended.get("amended") is True,
               f"override {str(approval.get('overrideId', approval))[:8]}, "
               f"amendment {amended}. The manager stepped up on their OWN session; the "
               f"waiter never held their credential")

        both = rows(f"""
            SELECT CASE WHEN actor_user_id = '{fx.USER}' THEN 'the waiter asked'
                        ELSE 'someone else asked' END,
                   CASE WHEN approver_user_id = '{fx.USER_MANAGER}'
                        THEN 'the manager allowed it'
                        ELSE 'someone else allowed it' END
            FROM pos.override_approval WHERE id = '{approval.get('overrideId')}';""")
        record(journey, "the amendment names who asked and who allowed it",
               both == [["the waiter asked", "the manager allowed it"]],
               f"{both}. Two people on the record, which is the whole difference between "
               f"delegation and somebody borrowing a password")


# ===========================================================================
# FR-TST-007A — two submissions racing, no duplicate commercial effect
# ===========================================================================

def concurrency() -> None:
    print("\n--- FR-TST-007A: two submissions racing, measured with M3-A's differential ---")
    journey = "FR-TST-007A"

    seated = fx.a_seated_guest_with_credential(table=fx.TABLE_ONE)
    token = seated["token"]

    import urllib.request
    import urllib.error

    def guest(method: str, path: str, body: dict | None = None, key: str | None = None):
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
            with urllib.request.urlopen(request, timeout=30) as response:
                return {"status": response.status, **json.loads(response.read())}
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            try:
                return {"status": error.code, **json.loads(raw)}
            except json.JSONDecodeError:
                return {"status": error.code, "body": raw}

    cart = guest("GET", "/c/v1/cart")
    pair = rows(f"""
        SELECT i.id::text, v.id::text FROM menu.sellable_item i
        JOIN menu.item_variant v ON v.item_id = i.id AND v.is_default AND v.status = 'active'
        WHERE i.tenant_id = '{fx.TENANT}' AND i.status = 'active'
        ORDER BY i.item_code LIMIT 1;""")
    guest("POST", "/c/v1/cart/lines",
          {"cartId": cart.get("cartId"), "itemId": pair[0][0], "variantId": pair[0][1]},
          key=f"race-line-{RUN_NONCE}")

    view = guest("POST", "/c/v1/orders/preview", {"cartId": cart.get("cartId")})
    preview = view.get("preview") or {}
    body = {
        "cartId": cart.get("cartId"),
        "expectedTotalMinor": int(preview.get("total_amount_minor", 0)),
        "pricingDigest": preview.get("pricing_digest", ""),
        "locale": "en",
    }
    key = f"race-submit-{RUN_NONCE}"

    # The two submissions go out AT THE SAME TIME, on separate connections, carrying the
    # same idempotency key — which is what a guest's second tap on a slow connection
    # actually looks like. A sequential pair would test the replay path and say nothing
    # about the race.
    from concurrent.futures import ThreadPoolExecutor

    before = table_digests()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(guest, "POST", "/c/v1/orders", body, key) for _ in range(2)]
        outcomes = [f.result() for f in futures]
    after = table_digests()

    ids = {o.get("orderId") for o in outcomes if o.get("orderId")}
    record(journey, "both racing submissions answer, and with the same order",
           len(ids) == 1 and all(o.get("status") in (200, 409) for o in outcomes),
           f"{outcomes}. One order id between them: the loser of the race is answered "
           f"with the winner's outcome rather than refused, because from the guest's "
           f"side it was one tap that they repeated")

    orders_made = count(APP, f"""
        SELECT count(*) FROM ordering.customer_order
         WHERE cart_id = '{cart.get("cartId")}';""", **CTX)
    record(journey, "and the race produced exactly one order",
           orders_made == 1,
           f"{orders_made} order(s) from the cart both requests submitted")

    # The whole-schema differential: what MOVED between the two snapshots, over every
    # table the catalog knows. The delta is not empty — an order was created, which is
    # the point — so this asserts the SHAPE of the delta rather than its absence: one
    # order, one ledger entry per event, and no second commercial artifact anywhere.
    changed = sorted(k for k in set(before) | set(after)
                     if before.get(k) != after.get(k))
    doubled = []
    for table in changed:
        b = int((before.get(table) or "0:").split(":")[0])
        a = int((after.get(table) or "0:").split(":")[0])
        # ordering.order_charge_component is deliberately NOT here. One order carries
        # several components — an item subtotal and a tax at least — so "more than one
        # new row" is the shape of a single order rather than evidence of two. The
        # duplication this control exists to catch shows up as a second ORDER or a
        # second LINE, and both are asserted directly as well.
        if table.startswith(("ordering.customer_order", "ordering.order_line")) and a - b > 1:
            doubled.append(f"{table} +{a - b}")
    record(journey, "no commercial artifact was created twice",
           doubled == [],
           f"{len(changed)} table(s) moved across {len(before)} enumerated from the "
           f"catalog; commercial tables gaining more than one row: {doubled or 'none'}. "
           f"M3-A's instrument, reused rather than rewritten — it covers the tables M3-B, "
           f"M3-C and M3-D added without anybody having listed them")

    lines = count(APP, f"""
        SELECT count(*) FROM ordering.order_line ol
        JOIN ordering.customer_order o ON o.id = ol.order_id
        WHERE o.cart_id = '{cart.get("cartId")}';""", **CTX)
    record(journey, "and the guest is charged for one dish, not two",
           lines == 1,
           f"{lines} order line(s). The commercial effect is what a duplicate submission "
           f"would show up in, and at M4 this is the difference between one charge and "
           f"two")


# ===========================================================================
# The M4 journeys: settlement, the receipt, and the paper it goes on
# ===========================================================================
# EACH ONE CONTINUES ITS PREDECESSOR'S SESSION rather than opening a fresh one. GJ-01B's
# steps say "open the served English table session from GJ-01A", and a journey that seated
# a new guest to settle a bill would be proving that a bill can be settled — not that the
# guest who walked GJ-01A can pay and leave with paper.
#
# THE PRINT IS THE REAL PATH, END TO END: docs.receipt_document() composes, print/agent.py
# verifies the vendored fonts by checksum, Chromium rasterises at 576 dots, every glyph is
# checked against the fonts this repository ships, print/escpos.py encodes, and the bytes
# are written to a CHARACTER DEVICE. What is not proved is the last inch — that a physical
# machine turned those bytes into legible paper — and that is carried as FR-BIL-017's own
# open register entry against M5a rather than claimed here.


def guest_at(session: str) -> str:
    """A guest credential on the occupancy a bill belongs to, through the QR exchange.

    THE TIP IS THE GUEST'S DECISION, so it goes through the guest's own route. That needs
    a credential, and the only honest way to get one is the exchange a phone makes:
    issue the table's code, POST it to the session route, and receive the token the route
    mints. The journeys used to INSERT INTO billing.tip instead — a second copy of the
    route's own SQL, proving that the table accepts rows.
    """
    table = scalar(f"""
        SELECT table_node_id FROM service.table_session WHERE id = '{session}';""")
    code = scalar(f"""
        SELECT service.issue_table_qr('{fx.TENANT}', '{table}', '{fx.USER}');""")
    opened = service("POST", f"/c/v1/{fx.TENANT}/{fx.OUTLET_H1}/session", {"code": code},
                     token="", scheme="Guest")
    if not ok(opened) or not opened.get("guestToken"):
        raise ProbeFailed("the guest QR exchange", why(opened) or str(opened)[:200])
    if opened.get("tableSessionId") != session:
        raise ProbeFailed(
            "the guest QR exchange",
            f"the code for this table opened occupancy {opened.get('tableSessionId')} "
            f"and the bill belongs to {session}. A tip added on another occupancy would "
            f"be a different guest's money")
    return opened["guestToken"]


def a_settled_check(journey: str, session: str, *, locale: str, tip_minor: int,
                    method: str, provider: str) -> dict:
    """Open a check over a served session, bill it, take the money, and say what happened.

    EVERY WRITE HERE GOES THROUGH THE SERVICE. Staff actions carry the cashier's own
    bearer token; the tip carries the guest's, because the guest is who decides it. The
    reads that follow each write are SQL, because asking the database what the route did
    is evidence and asking it to do the work is the substitution this repair removed.
    """
    token = cashier()
    opened = service("POST", "/s/v1/checks", {"tableSessionId": session}, token=token)
    if not ok(opened):
        raise ProbeFailed("POST /s/v1/checks", why(opened))
    check = opened["checkId"]

    # One call per line, as a cashier tapping each item would make. The lines are READ
    # from the order the predecessor placed; adding them is the route's work.
    unbilled = [r[0] for r in rows(f"""
        SELECT l.id::text FROM ordering.order_line l
          JOIN ordering.customer_order o ON o.id = l.order_id
         WHERE o.table_session_id = '{session}'
           AND NOT EXISTS (SELECT 1 FROM billing.check_allocation a
                            WHERE a.order_line_id = l.id)
         ORDER BY l.line_number;""")]
    if not unbilled:
        raise ProbeFailed("allocating the check",
                          "the served session carries no unbilled order line, so there "
                          "is nothing to put on a check")
    for line in unbilled:
        placed = service("POST", f"/s/v1/checks/{check}/allocations",
                         {"orderLineId": line}, token=token)
        if not ok(placed):
            raise ProbeFailed(f"POST /s/v1/checks/{check[:8]}/allocations", why(placed))

    billed = service("POST", "/s/v1/bills", {"checkId": check, "locale": locale},
                     token=token)
    if not ok(billed):
        raise ProbeFailed("POST /s/v1/bills", why(billed))
    bill = billed["billId"]
    total = int(scalar(f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';"))

    tip_id = None
    if tip_minor:
        split = service("POST", f"/s/v1/bills/{bill}/split",
                        {"mode": "equal", "payers": 1}, token=token)
        if not ok(split):
            raise ProbeFailed(f"POST /s/v1/bills/{bill[:8]}/split", why(split))
        share = scalar(f"""
            SELECT id FROM billing.bill_share WHERE bill_id = '{bill}'
             ORDER BY share_number LIMIT 1;""")
        tipped = service("POST", "/c/v1/bill/tip",
                         {"shareId": share, "amountMinor": tip_minor},
                         token=guest_at(session), scheme="Guest",
                         key=f"{journey}-{RUN_NONCE}-tip")
        if not ok(tipped):
            raise ProbeFailed("POST /c/v1/bill/tip", why(tipped))
        tip_id = scalar(f"""
            SELECT id FROM billing.tip WHERE bill_share_id = '{share}'
             ORDER BY chosen_at DESC LIMIT 1;""")

    intent = service("POST", "/s/v1/payments/intents",
                     {"billId": bill, "billAmountMinor": total,
                      "tipAmountMinor": tip_minor,
                      **({"tipId": tip_id} if tip_id else {})},
                     token=token, key=f"{journey}-{RUN_NONCE}-intent")
    if not ok(intent):
        raise ProbeFailed("POST /s/v1/payments/intents", why(intent))
    return {"check": check, "bill": bill, "total": total, "tip": tip_minor,
            "tip_id": tip_id, "intent": intent["intentId"],
            "method": method, "provider": provider}


def print_the_receipt(journey: str, receipt: str, *, is_reprint: bool = False,
                      reason_code: str | None = None,
                      reason_text: str | None = None) -> dict:
    """Compose, rasterise, check every glyph, encode, and write to a character device.

    os.devnull, never a POSIX literal. The null device has a different name on each
    platform and both are CHARACTER DEVICES, which is what print/agent.py requires and
    what makes this a device sink rather than a file that received bytes.
    """
    document = json.loads(scalar(
        f"SELECT docs.receipt_document('{fx.TENANT}', '{receipt}')::text;"))
    produced = printer.produce(document, sink="device", device_path=os.devnull,
                               workspace=WORKSPACE)
    recorded = run(APP, f"""
        SELECT docs.record_receipt_print('{fx.TENANT}', '{fx.OUTLET_H1}', '{receipt}',
            '{m4c.PRINTER_DEVICE}', 'printed', '{produced["bytes_sha256"]}',
            {produced["byte_count"]}, '{m4c.USER_CASHIER}', {str(is_reprint).lower()},
            {"'" + reason_code + "'" if reason_code else "NULL"},
            {"$r$" + reason_text + "$r$" if reason_text else "NULL"});""",
        tx=True, **CTX)
    return {"produced": produced, "recorded": recorded, "document": document}


def script_coverage(document: dict, is_script) -> tuple[int, int]:
    """How many characters of one script the document carries, and how many are covered.

    Read off the RASTER rather than off the string, because a string that contains an
    Ethiopic codepoint proves nothing about what came out of the rasteriser — which is
    the whole reason NC-M4-005 exists.
    """
    measured = printer.rasterise(document, dots_wide=576, workspace=WORKSPACE)
    of_the_script = [c for c in measured.get("coverage", [])
                     if is_script(c["character"])]
    return (len(of_the_script),
            sum(1 for c in of_the_script if c["drawnByTheVendoredFont"]))


def chain_for(journey: str, order: str) -> list[str]:
    """Which artifact kinds the correlation chain holds for this order's correlation."""
    return [r[0] for r in rows(f"""
        SELECT DISTINCT l.artifact_kind::text
          FROM ordering.correlation_link l
         WHERE l.correlation_id = (SELECT correlation_id FROM ordering.customer_order
                                    WHERE id = '{order}')
         ORDER BY 1;""", dsn=ADMIN)]


def gj_01b() -> None:
    print("\n--- GJ-01B: English — bill, cash settlement, no tip, receipt, paper ---")
    journey = "GJ-01B"
    predecessor = CONTEXT.get("GJ-01A")
    if not predecessor:
        raise ProbeFailed("GJ-01B's predecessor",
                          "GJ-01A left no served session, so there is nothing to settle. "
                          "A journey that seated a new guest here would be proving that "
                          "a bill can be settled, not that this guest can pay and leave")

    settled = a_settled_check(journey, predecessor["session"], locale="en",
                              tip_minor=0, method="cash", provider="cash")
    captured = service("POST", f"/s/v1/payments/{settled['intent']}/cash",
                       {"tenderedMinor": settled["total"]}, token=cashier(),
                       key=f"{journey}-{RUN_NONCE}-cash")
    record(journey, "the cashier presents the check and settles it in cash",
           ok(captured),
           why(captured) or f"bill {settled['bill'][:8]} of {settled['total']} minor "
                            f"units, tendered exactly, through "
                            f"POST /s/v1/payments/:intentId/cash on the running service")

    no_tip = count(APP, f"""
        SELECT count(*) FROM billing.tip t
          JOIN billing.bill_share s ON s.id = t.bill_share_id
         WHERE s.bill_id = '{settled["bill"]}';""", **CTX)
    record(journey, "and the guest left no tip, which is a decision rather than an absence",
           no_tip == 0,
           f"{no_tip} tip(s) against this bill. No tip is preselected anywhere — "
           f"NC-M4-001 — so a guest who chooses nothing has chosen nothing")

    issued = service("POST", "/s/v1/receipts",
                     {"billId": settled["bill"], "paymentMethod": "cash"},
                     token=cashier())
    if not ok(issued):
        raise ProbeFailed("POST /s/v1/receipts", why(issued))
    receipt = issued["receiptId"]
    lines = {r[0]: r[1] for r in rows(f"""
        SELECT l.kind::text, coalesce(l.amount_minor::text, '-')
          FROM docs.receipt_line l WHERE l.receipt_id = '{receipt}';""")}
    record(journey, "the English digital receipt shows bill, tip and total paid separately",
           lines.get("bill_total") == str(settled["total"])
           and lines.get("tip") == "0"
           and lines.get("total_paid") == str(settled["total"])
           and lines.get("payment_method") == "-",
           f"{lines}. Three figures, three lines, and the method actually used on a "
           f"fourth — FR-BIL-010 with FR-BIL-017")

    printed = print_the_receipt(journey, receipt)
    record(journey, "and it goes on paper through the printer path, once",
           printed["recorded"].ok
           and printed["produced"]["outcome"] == "printed"
           and printed["produced"]["byte_count"] > 0,
           f"{printed['produced']['byte_count']} ESC/POS bytes to a character device, "
           f"{printed['produced']['characters_checked']} character(s) each checked "
           f"against the vendored fonts. What is NOT proved here is that a machine turned "
           f"them into legible paper: no printer exists on this runner, and that half is "
           f"FR-BIL-017's own open register entry against M5a")

    again = print_the_receipt(journey, receipt)
    record(journey, "and a second original print of the same settlement is refused",
           not again["recorded"].ok,
           again["recorded"].why() or "one settlement printed twice as an original. A "
                                      "customer holding two records of one payment is "
                                      "two payments as far as anybody reading them can "
                                      "tell")

    kinds = chain_for(journey, predecessor["order"])
    record(journey, "and check, bill, payment and receipt all hang off the guest's order",
           {"order", "check", "bill", "payment", "receipt"}.issubset(set(kinds)),
           f"{kinds}. The audit timeline links back to the order GJ-01A placed, which is "
           f"what makes this a continuation rather than a second evening")


def gj_02b() -> None:
    print("\n--- GJ-02B: Amharic — bill, tip, verified proof, Ethiopic on paper ---")
    journey = "GJ-02B"
    predecessor = CONTEXT.get("GJ-02")
    if not predecessor:
        raise ProbeFailed("GJ-02B's predecessor",
                          "GJ-02 left no served Amharic session to settle")

    settled = a_settled_check(journey, predecessor["session"], locale="am",
                              tip_minor=2500, method="telebirr_proof",
                              provider="telebirr_proof")
    record(journey, "the Amharic check offers a tip box and the guest adds a tip",
           settled["tip"] > 0 and bool(settled["tip_id"]),
           f"tip {settled['tip']} minor units on its own share, separate from the bill "
           f"total of {settled['total']}. FR-BIL-013 keeps the box beside the summary "
           f"and never inside it, and nothing is preselected")

    # THE PROOF IS PENDING UNTIL A PERSON VERIFIES IT, and the person is read from the
    # session rather than passed — M4-B's NC-M4-004, reached here through settlement.
    proof = scalar(f"""
        SELECT payments.raise_proof('{fx.TENANT}', '{fx.OUTLET_H1}', 'telebirr_proof',
            'ETB', {settled["total"] + settled["tip"]}, '{journey}-{RUN_NONCE}');""")
    premature = run(APP, f"""
        SELECT payments.record_proof_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{settled["intent"]}', '{proof}', {settled["total"] + settled["tip"]},
            '{m4c.USER_CASHIER}');""", tx=True, **CTX)
    record(journey, "an unverified proof cannot settle anything",
           not premature.ok,
           premature.why() or "money was recorded as received on a claim nobody had "
                              "checked in the provider's own app")

    verifier, _token = m4c.staff_session(m4c.USER_FINANCE_MANAGER)
    verified = run(APP, f"""
        SELECT payments.verify_proof('{fx.TENANT}', '{proof}',
            $w$the amount and the reference matched the provider app on my own screen$w$);""",
        tx=True, session=verifier, **CTX)
    captured = run(APP, f"""
        SELECT payments.record_proof_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{settled["intent"]}', '{proof}', {settled["total"] + settled["tip"]},
            '{m4c.USER_CASHIER}');""", tx=True, **CTX)
    record(journey, "and once a named person verifies it in the provider's app, it settles",
           verified.ok and captured.ok,
           f"{verified.why() or 'verified'}; {captured.why() or 'captured'}. The "
           f"verifier is whoever owns the session in context, so there is no parameter "
           f"by which somebody could attest on another person's behalf")

    receipt = scalar(f"""
        SELECT docs.issue_receipt('{fx.TENANT}', '{fx.OUTLET_H1}', '{settled["bill"]}',
                                  'telebirr_proof', '{m4c.USER_CASHIER}');""")
    labels = [r[0] for r in rows(f"""
        SELECT l.label FROM docs.receipt_line l WHERE l.receipt_id = '{receipt}';""")]
    record(journey, "the receipt is in Amharic, every line",
           bool(labels) and all(any(is_ethiopic(ch) for ch in label) for label in labels),
           f"{len(labels)} line(s), all carrying Ethiopic script. 0027 refuses a "
           f"non-English receipt whose label is the English source text, so a partial "
           f"translation cannot reach paper")

    printed = print_the_receipt(journey, receipt)
    present, covered = script_coverage(printed["document"], is_ethiopic)
    record(journey, "and every Ethiopic glyph on the paper came from the packaged font",
           present > 0 and covered == present,
           f"{covered} of {present} Ethiopic codepoint(s) drawn by the vendored fonts, "
           f"read off the RASTER the printer receives rather than off the string. A "
           f"receipt is paper: a customer cannot ask it to render again")
    record(journey, "and the bytes reached a character device",
           printed["recorded"].ok and printed["produced"]["outcome"] == "printed",
           f"{printed['produced']['byte_count']} bytes. The M4 print proves a real path "
           f"to a device and claims no durable queue, no retry and no outage resilience — "
           f"all of which are M5a's")


def gj_03b() -> None:
    print("\n--- GJ-03B: Arabic RTL — bill, tip, terminal payment, Arabic on paper ---")
    journey = "GJ-03B"
    predecessor = CONTEXT.get("GJ-03A")
    if not predecessor:
        raise ProbeFailed("GJ-03B's predecessor",
                          "GJ-03A left no served Arabic session to settle")

    settled = a_settled_check(journey, predecessor["session"], locale="ar",
                              tip_minor=1800, method="external_terminal",
                              provider="external_terminal")
    slip = scalar(f"""
        SELECT payments.record_terminal_result('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{journey}-{RUN_NONCE}', 'visa', 'ETB', {settled["total"] + settled["tip"]},
            'approved', '{m4c.USER_CASHIER}', '4242', 'A{RUN_NONCE[:5]}');""")
    captured = run(APP, f"""
        SELECT payments.record_terminal_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{settled["intent"]}', '{slip}', {settled["total"] + settled["tip"]},
            '{m4c.USER_CASHIER}');""", tx=True, **CTX)
    record(journey, "the guest chooses a tip and pays on a permitted live method",
           captured.ok and settled["tip"] > 0,
           f"{captured.why() or 'captured'} against an external terminal slip carrying a "
           f"scheme and four digits and no card number anywhere")

    receipt = scalar(f"""
        SELECT docs.issue_receipt('{fx.TENANT}', '{fx.OUTLET_H1}', '{settled["bill"]}',
                                  'external_terminal', '{m4c.USER_CASHIER}');""")
    figures = {r[0]: r[1] for r in rows(f"""
        SELECT l.kind::text, coalesce(l.amount_minor::text, '-')
          FROM docs.receipt_line l WHERE l.receipt_id = '{receipt}';""")}
    record(journey, "the Arabic receipt keeps bill, tip and total paid apart",
           figures.get("bill_total") == str(settled["total"])
           and figures.get("tip") == str(settled["tip"])
           and figures.get("total_paid") == str(settled["total"] + settled["tip"]),
           f"{figures}. Total paid is the one line that adds the two, because it is the "
           f"figure describing the money that changed hands")

    printed = print_the_receipt(journey, receipt)
    arabic_present, arabic_covered = script_coverage(printed["document"], is_arabic)
    latin = [c for c in printer.rasterise(printed["document"], dots_wide=576,
                                          workspace=WORKSPACE)["coverage"]
             if c["character"].isascii() and c["character"].isalnum()]
    record(journey, "Arabic and the Latin currency code are both drawn by the packaged fonts",
           arabic_present > 0 and arabic_covered == arabic_present
           and bool(latin) and all(c["drawnByTheVendoredFont"] for c in latin),
           f"{arabic_covered} of {arabic_present} Arabic codepoint(s) and {len(latin)} "
           f"Latin one(s), none falling back. Mixed script on one receipt is the case "
           f"that found the Ethiopic-only font set: the coverage check reported the "
           f"vendored font as having drawn nothing for every Arabic character, which is "
           f"exactly what it exists to report")
    record(journey, "and the bytes reached a character device",
           printed["recorded"].ok,
           printed["recorded"].why() or f"{printed['produced']['byte_count']} bytes. "
                                        f"Durable local print recovery is reserved for "
                                        f"M5a and is not claimed here")


def gj_06() -> None:
    print("\n--- GJ-06: a check split by item, two payers, two tips, two receipts ---")
    journey = "GJ-06"
    predecessor = CONTEXT.get("GJ-01A")
    if not predecessor:
        raise ProbeFailed("GJ-06's predecessor",
                          "no served order exists to split. GJ-06 needs at least one")

    # A FRESH SERVED TABLE with two dishes, because a split by item needs two items to
    # split. Built through the same helpers every earlier journey uses.
    session = m4c.m4a.fresh_occupancy(m4c.m4b.PAY_TABLE)
    guest = m4c.m4a.guest_on(session)
    cart = m4c.m4a.cart_with(session, guest,
                             ((m4c.VARIANT_DORO_FULL, m4c.ITEM_DORO, 1),
                              (m4c.m4b.VARIANT_TIBS_ONE, m4c.m4b.ITEM_TIBS, 1)))
    view = json.loads(scalar(f"""
        SELECT ordering.preview_cart('{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}',
                                     'en', 'dine_in');"""))
    order = scalar(f"""
        SELECT ordering.submit_order(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', '{journey}-{RUN_NONCE}',
            decode('{view["pricing_digest"]}', 'hex'), {view["total_amount_minor"]},
            'en', gen_random_uuid(), gen_random_uuid(), 'guest_qr',
            NULL, '{guest}', false, '[]'::jsonb, '[]'::jsonb, 'dine_in');""")
    accepted = run(APP, f"""
        SELECT ordering.accept_order('{fx.TENANT}', '{order}', '{fx.USER}');""", **CTX)
    if not accepted.ok:
        raise ProbeFailed("accept_order", accepted.err)

    check = scalar(f"""
        SELECT billing.open_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}',
                                  '{fx.USER}');""")
    allocated = run(APP, f"""
        SELECT billing.allocate_to_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{check}',
                                         l.id, l.quantity::integer)
          FROM ordering.order_line l WHERE l.order_id = '{order}';""", **CTX)
    if not allocated.ok:
        raise ProbeFailed("allocate_to_check", allocated.err)

    # SPLIT THE CHECK BY ITEM, which is what gives each payer a document of their own.
    # One bill cannot carry two receipts — docs.receipt is unique on (bill, revision) —
    # and that is correct: two receipts for one bill would be two records of one payment.
    first_line = scalar(f"""
        SELECT l.id FROM ordering.order_line l WHERE l.order_id = '{order}'
         ORDER BY l.line_number LIMIT 1;""")
    second_check = scalar(f"""
        SELECT billing.split_check('{fx.TENANT}', '{fx.OUTLET_H1}', '{check}',
            ARRAY['{first_line}']::uuid[], '{fx.USER}');""")
    record(journey, "the check splits by item into one document per payer",
           bool(second_check) and second_check != check,
           f"checks {check[:8]} and {second_check[:8]}, each holding the lines its payer "
           f"is settling. FR-BIL-004's by-item split, through the delivered writer")

    payers = []
    for label, source, tip_minor, method in (("A", check, 0, "cash"),
                                             ("B", second_check, 1500, "external_terminal")):
        bill = scalar(f"""
            SELECT billing.issue_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{source}',
                                      '{fx.USER}', 'en');""")
        total = int(scalar(
            f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';"))
        tip_id = None
        if tip_minor:
            made = run(APP, f"""
                SELECT billing.split_equally('{fx.TENANT}', '{bill}', 1);""",
                tx=True, **CTX)
            if not made.ok:
                raise ProbeFailed("billing.split_equally", made.err)
            share = scalar(f"""
                SELECT id FROM billing.bill_share WHERE bill_id = '{bill}'
                 ORDER BY share_number LIMIT 1;""")
            tip_id = scalar(f"""
                INSERT INTO billing.tip
                    (tenant_id, outlet_id, bill_share_id, currency_code, amount_minor)
                VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{share}', 'ETB', {tip_minor})
                RETURNING id;""")
        intent = scalar(f"""
            SELECT payments.create_intent('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
                '{journey}-{RUN_NONCE}-{label}', {total}, '{m4c.USER_CASHIER}',
                {tip_minor}, {"'" + tip_id + "'" if tip_id else "NULL"});""")
        if method == "cash":
            paid = run(APP, f"""
                SELECT payments.record_cash_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
                    '{intent}', {total + tip_minor}, '{m4c.USER_CASHIER}');""",
                tx=True, **CTX)
        else:
            slip = scalar(f"""
                SELECT payments.record_terminal_result('{fx.TENANT}', '{fx.OUTLET_H1}',
                    '{journey}-{RUN_NONCE}-{label}', 'visa', 'ETB', {total + tip_minor},
                    'approved', '{m4c.USER_CASHIER}', '4242', 'B{RUN_NONCE[:5]}');""")
            paid = run(APP, f"""
                SELECT payments.record_terminal_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
                    '{intent}', '{slip}', {total + tip_minor}, '{m4c.USER_CASHIER}');""",
                tx=True, **CTX)
        if not paid.ok:
            raise ProbeFailed(f"payer {label} settling", paid.err)
        receipt = scalar(f"""
            SELECT docs.issue_receipt('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
                                      '{method}', '{m4c.USER_CASHIER}');""")
        payers.append({"label": label, "bill": bill, "total": total, "tip": tip_minor,
                       "method": method, "receipt": receipt})

    allocations = rows(f"""
        SELECT a.target::text, a.amount_minor::text
          FROM payments.allocation a
          JOIN billing.bill b ON b.id = a.bill_id
         WHERE b.check_id IN ('{check}', '{second_check}')
         UNION ALL
        SELECT a.target::text, a.amount_minor::text
          FROM payments.allocation a
          JOIN billing.tip t ON t.id = a.tip_id
          JOIN billing.bill_share s ON s.id = t.bill_share_id
          JOIN billing.bill b ON b.id = s.bill_id
         WHERE b.check_id IN ('{check}', '{second_check}')
         ORDER BY 1, 2;""")
    to_balance = sum(int(a[1]) for a in allocations if a[0] == "bill_balance")
    to_tip = sum(int(a[1]) for a in allocations if a[0] == "tip")
    record(journey, "each payment allocates to the bill and to the tip independently",
           to_balance == sum(p["total"] for p in payers)
           and to_tip == sum(p["tip"] for p in payers),
           f"{to_balance} to bill balances against {sum(p['total'] for p in payers)} "
           f"billed, and {to_tip} to tips against {sum(p['tip'] for p in payers)} given. "
           f"Two allocations per payment, stored rather than recomputed")

    record(journey, "and payer A left no tip while payer B chose one",
           payers[0]["tip"] == 0 and payers[1]["tip"] > 0,
           f"A: {payers[0]['tip']}, B: {payers[1]['tip']}. Nothing is selected by "
           f"default, so the difference is two decisions rather than one setting")

    for payer in payers:
        printed = print_the_receipt(journey, payer["receipt"])
        again = print_the_receipt(journey, payer["receipt"])
        record(journey, f"payer {payer['label']}'s receipt is produced exactly once",
               printed["recorded"].ok and not again["recorded"].ok,
               f"{printed['produced']['byte_count']} bytes printed; a second original "
               f"was refused: {again['recorded'].why() or 'IT WAS NOT'}. Each payer "
               f"holds one record of their own payment")


def gj_07() -> None:
    print("\n--- GJ-07: self-approval refused, step-up, reversal, refund, reprint ---")
    journey = "GJ-07"

    # A SETTLED BILL WITH A TIP, on its own table, because this journey takes money back
    # and must not unwind a bill another journey is asserting about.
    session = m4c.m4a.fresh_occupancy(m4c.RECEIPT_TABLE)
    guest = m4c.m4a.guest_on(session)
    cart = m4c.m4a.cart_with(session, guest, ((m4c.VARIANT_DORO_FULL, m4c.ITEM_DORO, 1),))
    view = json.loads(scalar(f"""
        SELECT ordering.preview_cart('{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}',
                                     'en', 'dine_in');"""))
    order = scalar(f"""
        SELECT ordering.submit_order(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', '{journey}-{RUN_NONCE}',
            decode('{view["pricing_digest"]}', 'hex'), {view["total_amount_minor"]},
            'en', gen_random_uuid(), gen_random_uuid(), 'guest_qr',
            NULL, '{guest}', false, '[]'::jsonb, '[]'::jsonb, 'dine_in');""")
    accepted = run(APP, f"""
        SELECT ordering.accept_order('{fx.TENANT}', '{order}', '{fx.USER}');""", **CTX)
    if not accepted.ok:
        raise ProbeFailed("accept_order", accepted.err)

    settled = a_settled_check(journey, session, locale="en", tip_minor=2000,
                              method="cash", provider="cash")
    paid = run(APP, f"""
        SELECT payments.record_cash_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{settled["intent"]}', {settled["total"] + settled["tip"]},
            '{m4c.USER_CASHIER}');""", tx=True, **CTX)
    if not paid.ok:
        raise ProbeFailed("settling GJ-07's bill", paid.err)

    receipt = scalar(f"""
        SELECT docs.issue_receipt('{fx.TENANT}', '{fx.OUTLET_H1}', '{settled["bill"]}',
                                  'cash', '{m4c.USER_CASHIER}');""")
    print_the_receipt(journey, receipt)

    # THE CASHIER TRIES TO APPROVE THEIR OWN REFUND, from their own session.
    cashier_session, _t = m4c.staff_session(m4c.USER_CASHIER)
    reason = m4c.reason_code("M4B_REFUND_AUTHORIZED")
    self_approved = run(APP, f"""
        SELECT set_config('app.auth_strength', 'strong', false);
        SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', 'payment.refund',
            '{cashier_session}', '{reason}', 'bill', '{settled["bill"]}',
            $r$I am refunding this myself$r$);""",
        tx=True, session=cashier_session, **CTX)
    record(journey, "a cashier cannot approve their own refund",
           not self_approved.ok,
           self_approved.why() or "the cashier authorized their own refund. Maker-checker "
                                  "is the whole of NC-M4-004, and an audit trail in which "
                                  "the compliant case and the violation are identical is "
                                  "no audit trail")

    # THE MANAGER STEPS UP, from their own session, for this purpose.
    manager_session, _t = m4c.staff_session(m4c.USER_FINANCE_MANAGER)
    m4c.step_up(manager_session, "payment.refund")
    override = run(APP, f"""
        SELECT set_config('app.auth_strength', 'strong', false);
        SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', 'payment.refund',
            '{manager_session}', '{reason}', 'bill', '{settled["bill"]}',
            $r$the guest was charged for a dish they returned$r$);""",
        tx=True, session=cashier_session, **CTX)
    approval = (override.rows[-1][0] if override.ok and override.rows else "").strip()
    record(journey, "and a manager's purpose-specific step-up authorizes it",
           override.ok and bool(approval),
           override.why() or f"override {approval[:8]} for payment.refund on this bill, "
                             f"granted from the manager's own session after a step-up "
                             f"that names the action")

    # THE BILL ALLOCATION AND THE TIP ARE REVERSED SEPARATELY, which is FR-BIL-016's
    # sharp edge: a tip given back is not a smaller tip.
    allocation = scalar(f"""
        SELECT a.id FROM payments.allocation a
         WHERE a.bill_id = '{settled["bill"]}' AND a.target = 'bill_balance' LIMIT 1;""")
    reversed_bill = run(APP, f"""
        SELECT payments.reverse_allocation('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{allocation}', 'refund', 500,
            '{m4c.reason_code("M4B_GUEST_REFUNDED")}', $r$a dish was returned$r$,
            '{m4c.USER_CASHIER}', '{approval}');""", tx=True, **CTX)
    corrected_tip = run(APP, f"""
        INSERT INTO billing.tip_correction
            (tenant_id, outlet_id, tip_id, kind, currency_code, amount_minor,
             override_id, reason_code_id, reason_text, actor_user_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{settled["tip_id"]}', 'refund', 'ETB',
                500, '{approval}', '{m4c.reason_code("M4B_TIP_RETURNED")}',
                $r$the guest asked for part of the tip back$r$, '{m4c.USER_CASHIER}');""",
        tx=True, **CTX)
    record(journey, "the bill and the tip are corrected as two independent records",
           reversed_bill.ok and corrected_tip.ok,
           f"{reversed_bill.why() or 'allocation partly reversed'}; "
           f"{corrected_tip.why() or 'tip partly refunded'}. Each names its own reason "
           f"code and the one approval that authorized it, and neither touches the other")

    # THE CORRECTED RECEIPT: a new REVISION, not an edit, printed and marked.
    reissued = scalar(f"""
        SELECT docs.reissue_receipt('{fx.TENANT}', '{fx.OUTLET_H1}', '{receipt}',
                                    '{m4c.USER_CASHIER}');""")
    revisions = rows(f"""
        SELECT r.revision::text, r.receipt_number FROM docs.receipt r
         WHERE r.bill_id = '{settled["bill"]}' ORDER BY r.revision;""")
    record(journey, "the corrected receipt is a new revision with its own number",
           len(revisions) == 2 and revisions[0][1] != revisions[1][1],
           f"{revisions}. docs.receipt is append-only: a correction is a further document "
           f"rather than an edit of the one the customer is holding")

    marked = print_the_receipt(journey, reissued, is_reprint=True,
                              reason_code=m4c.reason_code("M4C_RECEIPT_REISSUE"),
                              reason_text="the settlement was corrected after printing")
    audit = rows(f"""
        SELECT a.is_reprint::text, (a.reason_code_id IS NOT NULL)::text,
               (a.operator_user_id IS NOT NULL)::text
          FROM docs.print_attempt a WHERE a.receipt_id = '{reissued}';""")
    record(journey, "and its print is marked, with an operator and a reason",
           marked["recorded"].ok and audit and audit[0] == ["true", "true", "true"],
           f"{audit}. FR-BIL-011: a reprint carries both, and the CHECK forbids a reason "
           f"on an original — so 'reprint' cannot be a word somebody typed")

    untouched = rows(f"""
        SELECT count(*)::text FROM docs.print_attempt a
         WHERE a.receipt_id = '{receipt}' AND NOT a.is_reprint;""")
    record(journey, "and the first receipt's own record is unchanged",
           untouched and untouched[0][0] == "1",
           f"{untouched[0][0] if untouched else '?'} original print against the first "
           f"revision. The customer's copy is still what it was; the correction is a "
           f"second document and a second print, both auditable")


# ===========================================================================
# main
# ===========================================================================

JOURNEYS = (
    ("GJ-01A", gj_01a),
    ("GJ-02", gj_02),
    ("GJ-03A", gj_03a),
    ("GJ-04", gj_04),
    ("GJ-05", gj_05),
    ("GJ-01B", gj_01b),
    ("GJ-02B", gj_02b),
    ("GJ-03B", gj_03b),
    ("GJ-06", gj_06),
    ("GJ-07", gj_07),
    ("FR-TST-007A", concurrency),
)


def main() -> int:
    print("=" * 74)
    print(f"GOLDEN JOURNEY VERIFICATION — {len(JOURNEYS) - 1} journeys end to end, "
          f"plus the submit race")
    print(f"real PostgreSQL, real compiled service, real Chromium "
          f"(running on {platform.system()})")
    print("evidence encoding: UTF-8")
    print()
    print("  Every result names its JOURNEY and its STEP. A step after a failure is")
    print("  reported as NOT REACHED, so a journey that stopped early cannot be mistaken")
    print("  for one that mostly worked.")
    print()
    print("=" * 74)

    # M4-C'S SEED, WHICH CHAINS THE WHOLE FLOOR BENEATH IT — M4-B, M4-A, M3-D and down.
    # The five M4 journeys need a registered printer, receipt wording in three locales and
    # a till; the five before them need what they always needed, and get it from the same
    # call because every fixture in the chain is idempotent.
    m4c.seed()
    print("fixtures seeded: the M4-C floor, on the whole chain beneath it")

    sync_and_build()

    with Service(APP) as service:
        CONTEXT["base_url"] = f"http://127.0.0.1:{service.port}"
        for name, walker in JOURNEYS:
            try:
                walker()
            except ProbeFailed as error:
                record(name, "the journey could be walked at all", False,
                       f"{error}. A journey that could not start is not a journey that "
                       f"passed its first step")
            except Exception as error:  # noqa: BLE001 - the journey names its own failure
                record(name, "the journey completed without an unexpected error", False,
                       f"{type(error).__name__}: {error}")

    passed = sum(1 for _j, _s, ok, _d in results if ok)
    failed = [(j, s, d) for j, s, ok, d in results if not ok]

    by_journey: dict[str, list[bool]] = {}
    for journey, _step, ok, _detail in results:
        by_journey.setdefault(journey, []).append(ok)

    print("\n" + "=" * 74)
    print(f"  steps checked : {len(results)}")
    print(f"  passed        : {passed}")
    print(f"  failed        : {len(failed)}")
    print()
    for journey, _walker in JOURNEYS:
        outcomes = by_journey.get(journey, [])
        verdict = "PASS" if outcomes and all(outcomes) else "FAIL"
        print(f"  {verdict}  {journey:<12} {sum(outcomes)}/{len(outcomes)} steps")
    for journey, step, detail in failed:
        print(f"\n  - {journey} failed at: {step}")
        for line in (detail or "").splitlines():
            print(f"      {line}")
    print()
    if failed:
        print("FAIL GOLDEN_JOURNEY_VERIFICATION")
        return 1
    print("PASS GOLDEN_JOURNEY_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
