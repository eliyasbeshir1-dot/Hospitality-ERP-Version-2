#!/usr/bin/env python3
"""M4-B verification: payment capture, verification, cash management and reversal.

M4-A proved a tip cannot reach a bill balance. This suite decides what counts as money
actually received, and four things shape how it asks.

THE LIVE/SIMULATED BOUNDARY IS PROVED STRUCTURALLY BEFORE IT IS EXERCISED. NC-M4-003 says
a simulated result must never be recordable as a live provider outcome — not by
configuration, not by a fixture, not by an operator holding every permission. A boundary
that holds because nobody wrote the code to cross it today is not the same as one that
cannot be crossed, so the catalog is asked three questions no behaviour can answer: is
there a value of the adapter mode a caller can supply, is there a column of the live type
that a simulated result would fit, and is there a path to an allocation that does not pass
the earned check. Only then is the crossing attempted, through the real route.

THE REGISTRY IS ASSERTED NON-EMPTY, AND NAMED, BEFORE ANY OF IT RUNS. M4-A's thirteen
balance functions are the model: a fence proved against an empty set passes by having
nothing to examine. If the adapter registry ever loads with no simulated adapter in it,
this suite stops rather than reporting that no simulator could be made live.

THE OUTAGE CLAIM IS A CLAIM ABOUT A CALL GRAPH, NOT ABOUT ONE STAGED OUTAGE. FR-PAY-002
says cash service continues during an internet outage, and the outlet node an outage could
be staged on is M5a's. Staging one outage would prove the path survived that outage;
proving that nothing reachable from the cash path can make an outbound call at all proves
it survives every outage, including the ones nobody thought to stage. The reachable set is
derived transitively from the catalog and "outbound" is defined by CAPABILITY — an
untrusted language, a foreign table, a non-core extension, or a write to the table that
records an adapter call — never by a name pattern the next author routes around by
accident.

NO FIGURE IS READ BACK AND AGREED WITH. Change, allocations, expected drawer contents and
the over/short are recomputed in Python from what was configured and what was tendered,
and the database is required to match.

Every check records whether its evidence is MEASURED — read out of a running browser — or
ASSERTED, meaning read from source, from a payload, or from the database.
"""
from __future__ import annotations

import json
import os
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
    DifferentialUnusable, RULE_FUNCTION_QUERY, strip_comments)
from fenced import fenced_identifier_pattern, source_patterns    # noqa: E402
from pg import CommandUnreadable, ProbeFailed, count, run, run_command   # noqa: E402
from service import Service, WORKSPACE, sync_and_build           # noqa: E402

import controls as registry                                      # noqa: E402
import partial_closures                                          # noqa: E402
import generate_evidence_report as evidence                      # noqa: E402

assert fx.__file__ == str(HERE / "fixtures.py"), f"wrong fixtures module: {fx.__file__}"

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]
CTX = dict(tenant=fx.TENANT, outlet=fx.OUTLET_H1)

results: list[tuple[str, bool, str, str]] = []
CONTEXT: dict = {}
RUN_NONCE = os.urandom(6).hex()


def a_uuid() -> str:
    """A canonical UUID, for use where an opaque value has to pass the card-data rule.

    payments.refuse_card_data() refuses a long unbroken run of hexadecimal, because that
    is what a card cryptogram looks like — and it exempts a canonical UUID, because that
    is not one. An idempotency key of 'm4b-thing-a1b2c3d4e5f60718' is twelve hex
    characters too many and was refused, correctly. A client wanting an opaque key uses a
    UUID; so does this suite.
    """
    raw = os.urandom(16).hex()
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def idem(label: str) -> str:
    return f"m4b-{label}-{a_uuid()}"


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


# Words that appear in every PostgreSQL diagnostic and are not signatures. Without this
# the first match in "ERROR:  HS409: UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM: …" is the word
# ERROR, and a control asserting its own signature would report that it found ERROR — an
# assertion that fails for a reason having nothing to do with the defect.
_NOT_A_SIGNATURE = {"ERROR", "DETAIL", "HINT", "CONTEXT", "STATEMENT", "WARNING",
                    "NOTICE", "LINE", "SCHEMA", "TABLE", "COLUMN", "CONSTRAINT",
                    "LOCATION", "SELECT", "INSERT", "UPDATE", "DELETE", "WHERE", "VALUES"}


def signature_of(error: str) -> str:
    for matched in re.finditer(r"\b([A-Z][A-Z_]{4,})\b", error or ""):
        if matched.group(1) not in _NOT_A_SIGNATURE:
            return matched.group(1)
    return ""


# ===========================================================================
# HTTP, as the staff surface reaches it
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


def a_submitted_order(session: str, guest: str, lines) -> str:
    """One order, through the delivered writer with the digest the preview produced.

    The digest and the total are M3-A's guard against a cart that changed between the
    price a guest was shown and the order they placed; passing them from a fresh preview
    is what makes this a real order rather than a row.
    """
    cart = fx.m4a.cart_with(session, guest, lines)
    view = preview(cart)
    submitted = run(APP, f"""
        SELECT ordering.submit_order(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}',
            '{idem("order-" + a_uuid())}',
            decode('{view["pricing_digest"]}', 'hex'), {view["total_amount_minor"]},
            'en', gen_random_uuid(), gen_random_uuid(), 'guest_qr',
            NULL, '{guest}', false, '[]'::jsonb, '[]'::jsonb, 'dine_in');""", **CTX)
    if not submitted.ok:
        raise ProbeFailed("submit_order", submitted.err)
    return (submitted.scalar or "").strip()


def a_bill_at(table: str, lines=((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 1),)) -> dict:
    """A seated party, an accepted order, a check over it and an issued bill.

    Built through M2-B's, M3-A's and M4-A's own functions rather than by inserting rows,
    because a bill assembled by hand would be a bill no earlier slice agrees exists.
    """
    session = fx.m4a.fresh_occupancy(table)
    guest = fx.m4a.guest_on(session)
    order = a_submitted_order(session, guest, lines)

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

    bill = scalar(f"""
        SELECT billing.issue_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{check}',
                                  '{fx.USER}', 'en');""")
    total = int(scalar(
        f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';"))
    return {"session": session, "guest": guest, "order": order, "check": check,
            "bill": bill, "total": total}


def an_intent(bill: str, amount: int, label: str, **extra) -> str:
    tip_id = extra.get("tip_id")
    share = extra.get("share")
    return scalar(f"""
        SELECT payments.create_intent('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
            '{idem(label)}', {amount}, '{fx.USER}', {extra.get('tip', 0)},
            {f"'{tip_id}'" if tip_id else 'NULL'},
            {f"'{share}'" if share else 'NULL'});""")


def an_override(action: str, subject_kind: str, subject_id: str, reason: str,
                text: str) -> str:
    """A real override: the cashier acting, the finance manager authorizing from their own
    session. Both identities and the step-up grant, exactly as M3-D built it.

    NOTE the reason parameter is ignored in favour of a manager_override one.
    pos.approve_override() requires that category and says why: an override states an
    active manager_override reason. The REVERSAL carries its own reason from category
    'refund', which is a different question — why the money went back, rather than why
    somebody was allowed to send it. Two reasons because they are two facts."""
    reason = fx.reason_code("M4B_REFUND_AUTHORIZED") if subject_kind != "cash_shift" \
        else fx.reason_code("M4B_DRAWER_RECOUNTED")
    actor_session, _ = fx.staff_session(fx.USER_CASHIER)
    approver_session, _ = fx.staff_session(fx.USER_FINANCE_MANAGER)
    fx.step_up(approver_session, action)
    approved = run(APP, f"""
        SELECT set_config('app.session_id', '{actor_session}', false);
        SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', '{action}',
            '{approver_session}', '{reason}', '{subject_kind}', '{subject_id}',
            $r${text}$r$);""", tx=True, **CTX)
    if not approved.ok:
        raise ProbeFailed("approve_override", approved.err)
    # THE LAST ROW, not the scalar. The statement before this one is the set_config that
    # puts the actor's session in context, and .scalar returns the first result — so this
    # returned a SESSION id, which then failed a foreign key three sections later as
    # "23503" with no signature to read. M4-A's helper takes rows[-1][0] and says why.
    override = (approved.rows[-1][0] if approved.rows else "").strip()
    if not override:
        raise ProbeFailed("approve_override", "no override id came back")
    return override


# ===========================================================================
# 1. The registry, built by setup, and non-empty before anything rests on it
# ===========================================================================

def section_registry() -> None:
    print("\n--- 1. The adapter registry, installed from configuration "
          "(FR-CFG-001C, FR-PAY-015) ---")

    # active::text, and a boolean cast to text renders as 'true' — not the 't' psql prints
    # for a bare boolean column. m3c compared against "t" for two gates and its producer
    # set was silently always empty as a result; that is fixed there and this is written
    # the right way round from the start.
    adapters = {r[0]: (r[1], r[2] == "true") for r in rows(f"""
        SELECT provider::text, mode::text, active::text
          FROM payments.payment_adapter
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
         ORDER BY provider;""")}

    simulated = sorted(p for p, (m, _a) in adapters.items() if m == "simulated")
    live = sorted(p for p, (m, _a) in adapters.items() if m == "live")

    # THE GUARD, before anything below it. M4-A's thirteen balance functions are the
    # model: a boundary proved against an empty set passes by having nothing to examine.
    # If the registry ever loads with no simulated adapter, every check in section 2 would
    # report that no simulator could be made live — truthfully, and uselessly.
    if not simulated or not live:
        raise CommandUnreadable(
            f"the adapter registry has {len(live)} live and {len(simulated)} simulated "
            f"adapter(s). NC-M4-003 needs both to exist: with no simulated adapter there "
            f"is nothing to attempt the forbidden claim FROM, and the whole of section 2 "
            f"would "
            f"pass by emptiness. Registry as loaded: {adapters}")

    record("the registry is non-empty and both worlds are in it",
           len(simulated) >= 2 and len(live) >= 4,
           f"live: {live}; simulated: {simulated}. Named rather than counted, so a "
           f"registry that silently emptied cannot make section 2 pass by having nothing "
           f"to make live")

    # FR-CFG-001C. The registry is not hand-written: it follows the approved
    # payment_method configuration version, and the ACTIVE set equals what setup permitted.
    permitted = {r[0] for r in rows(f"""
        SELECT jsonb_array_elements_text(cv.payload -> 'permitted')
          FROM config.configuration_version cv
         WHERE cv.tenant_id = '{fx.TENANT}' AND cv.category = 'payment_method'
           AND cv.effective_from <= now()
           AND (cv.effective_to IS NULL OR cv.effective_to > now());""")}
    active = {p for p, (_m, a) in adapters.items() if a}
    record("and the active adapters are exactly the methods setup permitted",
           active == permitted and permitted,
           f"configuration permits {sorted(permitted)}; active adapters {sorted(active)}. "
           f"The registry is installed FROM the approved configuration version, so "
           f"FR-CFG-001C's last clause — and those settings drive a real bill — is a "
           f"chain this suite can walk rather than a claim")

    record("a direct-provider adapter exists and is not permitted",
           all(p not in permitted for p in simulated),
           f"{simulated} are registered and inactive. They exist so the boundary has "
           f"something on the far side of it; NC-M4-003 activates one below and proves "
           f"that changes nothing about what it can settle")


# ===========================================================================
# 2. A simulated result cannot become a live one — from the catalog
# ===========================================================================

def section_boundary_structurally() -> None:
    print("\n--- 2. The live/simulated boundary, proved from the catalog "
          "(FR-PAY-015, NC-M4-003) ---")

    # LOCK ONE. The mode is not an input. There is a CHECK that computes it from the
    # provider, so no value a caller supplies, no configuration payload and no fixture can
    # produce a live direct-provider adapter.
    derived = rows("""
        SELECT pg_get_constraintdef(c.oid)
          FROM pg_constraint c
         WHERE c.conrelid = 'payments.payment_adapter'::regclass
           AND c.contype = 'c'
           AND pg_get_constraintdef(c.oid) LIKE '%mode%'
           AND pg_get_constraintdef(c.oid) LIKE '%provider%';""", dsn=ADMIN)
    record("the adapter's mode is computed from its provider by constraint",
           len(derived) >= 1,
           f"{len(derived)} CHECK constraint(s) relate mode to provider. The mode is not "
           f"a column somebody fills in, so 'label a direct-provider simulator as live' "
           f"has no value to be given")

    planted = run(ADMIN, f"""
        INSERT INTO payments.payment_adapter (tenant_id, outlet_id, provider, mode)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'telebirr_direct', 'live');""", tx=True)
    record("and a direct-provider adapter cannot be inserted as live, by anyone",
           not planted.ok and "mode_is_derived_from_the_provider" in (planted.err or ""),
           planted.why() or "a superuser inserted a live telebirr_direct adapter. The "
                            "constraint is the whole of NC-M4-003's first half")

    promoted = run(ADMIN, f"""
        UPDATE payments.payment_adapter SET mode = 'live'
         WHERE tenant_id = '{fx.TENANT}' AND provider = 'telebirr_direct';""", tx=True)
    record("and an existing one cannot be promoted by UPDATE either",
           not promoted.ok,
           promoted.why() or "a simulated adapter was promoted in place. Two constraints "
                             "stand here — the derived CHECK refuses the inconsistent "
                             "pair, and the immutability trigger refuses the consistent "
                             "pair that is a different adapter wearing this one's id")
    record("and the refusal names the control rather than a constraint",
           signature_of(promoted.err or "") in
           ("UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM", "PAYMENT_ADAPTER_MODE_IS_DERIVED_FROM_THE_PROVIDER"),
           f"signature: {signature_of(promoted.err or '') or 'none'}. A control must "
           f"assert the specific reason, and a bare constraint name would leave it "
           f"asserting that something went wrong")

    # LOCK TWO. Two types, and no cast between them. This is the strongest of the three
    # because it needs no code to hold: the value does not fit.
    outcome_type = scalar("""
        SELECT format_type(a.atttypid, NULL) FROM pg_attribute a
         WHERE a.attrelid = 'payments.payment'::regclass AND a.attname = 'outcome';""",
        dsn=ADMIN)
    record("the live outcome column is of a type a simulator cannot produce a value of",
           outcome_type == "payments.live_outcome",
           f"payments.payment.outcome is {outcome_type}, and "
           f"payments.invoke_direct_provider() returns payments.simulated_outcome. The "
           f"absence of a shared type is the requirement, the way the absence of a tip "
           f"column was at M4-A")

    casts = count(ADMIN, """
        SELECT count(*) FROM pg_cast c
         WHERE (c.castsource = 'payments.simulated_outcome'::regtype
                AND c.casttarget = 'payments.live_outcome'::regtype)
            OR (c.castsource = 'payments.live_outcome'::regtype
                AND c.casttarget = 'payments.simulated_outcome'::regtype);""")
    record("and no cast exists between the two, in either direction",
           casts == 0,
           f"{casts} cast(s). A cast either way would make the type boundary a formality: "
           f"one assignment with a :: on it and a simulated answer is a live one")

    holders = [r[0] for r in rows("""
        SELECT n.nspname || '.' || c.relname || '.' || a.attname
          FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE a.atttypid = 'payments.simulated_outcome'::regtype
           AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
         ORDER BY 1;""", dsn=ADMIN)]
    record("a simulated result is storable in exactly one place, and it settles nothing",
           holders == ["payments.simulated_attempt.result"],
           f"{holders}. Enumerated from pg_attribute, so a column of this type added to a "
           f"payment at M4-C fails here without anybody remembering to look")

    # LOCK THREE. The write refuses. Derived from the catalog rather than named, so a
    # second table that reduced a balance would have to carry it too.
    guards = [r[0] for r in rows("""
        SELECT t.tgname FROM pg_trigger t
         WHERE t.tgrelid = 'payments.allocation'::regclass
           AND NOT t.tgisinternal
           AND t.tgconstraint <> 0
         ORDER BY 1;""", dsn=ADMIN)]
    record("and an allocation is guarded by a constraint trigger, not by a route",
           "allocation_is_earned" in guards,
           f"{guards}. A route check is bypassed by the next caller to appear. This one "
           f"fires however the row arrives, including from a superuser")

    # A CENSUS OF THE PATHS TO AN ALLOCATION. If a second writer existed, the trigger
    # would still fire — but the differential this repository keeps is about SECOND
    # IMPLEMENTATIONS, and one writer is what makes the earned check the only gate.
    writers = [r[0] for r in rows("""
        SELECT n.nspname || '.' || p.proname
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE p.prosrc ~ 'INSERT INTO payments\\.allocation'
         ORDER BY 1;""", dsn=ADMIN)]
    record("exactly one function writes an allocation, and it is the fold",
           writers == ["payments.apply_event"],
           f"{writers}. M3-D proved the ordering channels were one implementation; this "
           f"is the same question asked of the row that reduces what a guest owes")


# ===========================================================================
# 3. And behaviourally, through the route a real integration would take
# ===========================================================================

def section_boundary_behaviourally() -> None:
    print("\n--- 3. The simulator is reachable, and settles nothing "
          "(FR-PAY-015, NC-M4-003) ---")

    token = CONTEXT["cashier_token"]

    # ACTIVATE the simulated adapter first. NC-M4-003's break is "label a direct-provider
    # simulator as live", and the nearest thing to that an operator can actually do is
    # switch it on. Doing it here means everything below is proved against an adapter that
    # is advertised and reachable rather than one that is off.
    switched = run(ADMIN, f"""
        UPDATE payments.payment_adapter SET active = true
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
           AND provider = 'telebirr_direct';""")
    if not switched.ok:
        raise ProbeFailed("activating the simulated adapter", switched.err)

    answer = call("POST", "/s/v1/payments/simulate", token,
                  {"provider": "telebirr_direct", "currencyCode": "ETB",
                   "amountMinor": 5000})
    record("the simulated path is callable, and says what it is",
           answer.get("status") == 200 and answer.get("simulated") is True
           and answer.get("result") == "approved",
           f"{answer}. It answers 'approved' exactly as a live adapter would, which is the "
           f"point: a simulator that announced itself in its RESULT would be refused by "
           f"the reader rather than by the system")

    attempt = rows("""
        SELECT result::text, adapter_mode::text FROM payments.simulated_attempt
         ORDER BY simulated_at DESC LIMIT 1;""")
    record("and the attempt is recorded as a simulation, in its own table",
           attempt and attempt[0] == ["approved", "simulated"],
           f"{attempt}. The row cannot claim to have run live: its adapter_mode is bound "
           f"to the adapter's identity by foreign key and pinned by CHECK")

    # THE CROSSING, attempted through the real capture path.
    bill = a_bill_at(fx.CASH_TABLE)
    intent = an_intent(bill["bill"], bill["total"], "simulated-capture")
    crossed = run(APP, f"""
        SELECT payments.capture('{fx.TENANT}', '{fx.OUTLET_H1}', '{intent}',
            'telebirr_direct', {bill["total"]}, '{fx.USER}');""", tx=True, **CTX)
    record("a simulated capture cannot allocate anything to a bill balance",
           crossed.failed_with("UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM"),
           crossed.why() or "a simulated result reduced what a guest owed. This is "
                            "NC-M4-003's second half and it travelled the same path a "
                            "real integration would")

    still_owed = int(scalar(
        f"SELECT billing.outstanding_balance('{fx.TENANT}', '{bill['bill']}');"))
    record("and the bill is untouched, by census rather than by the refusal",
           still_owed == bill["total"],
           f"{still_owed} against {bill['total']} before the attempt. A control that "
           f"trusted the exception would not have noticed a partial write")

    # AND NO PERMISSION HELPS. The strongest caller in the system, with the marker the
    # fold itself uses, still cannot write the allocation.
    forced = run(ADMIN, f"""
        SELECT set_config('payments.applying_event', 'yes', true);
        INSERT INTO payments.payment
            (id, tenant_id, outlet_id, intent_id, adapter_id, adapter_mode, provider,
             outcome, state, currency_code, tendered_minor, captured_by_user_id,
             captured_at, ledger_sequence)
        SELECT gen_random_uuid(), '{fx.TENANT}', '{fx.OUTLET_H1}', '{intent}', a.id,
               a.mode, a.provider, 'approved', 'captured', 'ETB', 1000, '{fx.USER}',
               now(), 1
          FROM payments.payment_adapter a
         WHERE a.tenant_id = '{fx.TENANT}' AND a.provider = 'telebirr_direct';""", tx=True)
    record("and a superuser cannot give a simulated payment a live outcome",
           not forced.ok,
           forced.why() or "a live outcome was written against a simulated adapter by a "
                           "superuser holding the fold's own marker. FR-PAY-015 is not a "
                           "permission and cannot be held")

    switched_back = run(ADMIN, f"""
        UPDATE payments.payment_adapter SET active = false
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
           AND provider = 'telebirr_direct';""")
    if not switched_back.ok:
        raise ProbeFailed("deactivating the simulated adapter", switched_back.err)

    CONTEXT["untouched_bill"] = bill


# ===========================================================================
# 4. The intent, and a retry that does not become a second payment
# ===========================================================================

def section_intent() -> None:
    print("\n--- 4. Payment intent, expiry and idempotency (FR-PAY-001, FR-PAY-012) ---")

    token = CONTEXT["cashier_token"]
    bill = a_bill_at(fx.PAY_TABLE)
    CONTEXT["pay_bill"] = bill

    key = idem("intent-retry")
    first = call("POST", "/s/v1/payments/intents", token,
                 {"billId": bill["bill"], "billAmountMinor": bill["total"]}, key)
    again = call("POST", "/s/v1/payments/intents", token,
                 {"billId": bill["bill"], "billAmountMinor": bill["total"]}, key)
    record("the same idempotency key returns the same intent, never a second",
           first.get("status") == 201 and first.get("intentId") == again.get("intentId"),
           f"{first.get('intentId')} then {again.get('intentId')}. FR-PAY-012's retry is "
           f"prevented where it starts rather than reconciled afterwards")

    census = count(APP, f"""
        SELECT count(*) FROM payments.payment_intent
         WHERE tenant_id = '{fx.TENANT}' AND bill_id = '{bill['bill']}';""", **CTX)
    record("and the census agrees: one intent exists, not two that look alike",
           census == 1,
           f"{census} intent(s) for this bill. Asserted by counting rather than by "
           f"comparing the two answers, because two calls that both returned the first id "
           f"would look identical to a check that only compared them")

    unkeyed = call("POST", "/s/v1/payments/intents", token,
                   {"billId": bill["bill"], "billAmountMinor": bill["total"]})
    record("an intent without an idempotency key is refused rather than guessed at",
           unkeyed.get("status") == 400 and unkeyed.get("reason") == "IDEMPOTENCY_KEY_ABSENT",
           f"{unkeyed}. A generated key would make every request its own retry-of-nothing")

    permitted = rows(f"""
        SELECT unnest(permitted_providers)::text FROM payments.payment_intent
         WHERE id = '{first["intentId"]}' ORDER BY 1;""")
    record("the permitted methods come from the registry, not from the request",
           sorted(r[0] for r in permitted) == sorted(fx.PERMITTED_METHODS),
           f"{sorted(r[0] for r in permitted)}. The body named none, and the intent "
           f"permits exactly the adapters setup activated — which is FR-CFG-001C reaching "
           f"the moment money is taken")

    refused = run(APP, f"""
        SELECT payments.capture('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{first["intentId"]}', 'cbe_birr_direct', {bill["total"]}, '{fx.USER}');""",
        tx=True, **CTX)
    record("and a method the intent does not permit is refused by name",
           refused.failed_with("PAYMENT_METHOD_NOT_PERMITTED"),
           refused.why() or "a method nobody permitted took the money")

    expired = run(APP, f"""
        SELECT payments.create_intent('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill["bill"]}',
            '{idem("expired")}', {bill["total"]}, '{fx.USER}', 0, NULL, NULL, NULL,
            interval '-1 minute');""", tx=True, **CTX)
    record("an intent cannot be created already expired",
           not expired.ok,
           expired.why() or "an intent expired before it existed, which would authorize "
                            "nothing and look like an authorization")

    CONTEXT["pay_intent"] = first["intentId"]


# ===========================================================================
# 5. Cash: exact allocation, a separate tip, and change computed here
# ===========================================================================

def section_cash_payment() -> None:
    print("\n--- 5. Cash, change and exact arithmetic (FR-PAY-002, FR-PAY-017) ---")

    token = CONTEXT["cashier_token"]
    bill = CONTEXT["pay_bill"]
    intent = CONTEXT["pay_intent"]

    # A tender that does NOT divide evenly into the amount owed, so the change is a real
    # figure rather than zero. Recomputed in Python and required to match.
    owed = bill["total"]
    tendered = owed + 1737
    expected_change = tendered - owed

    paid = call("POST", f"/s/v1/payments/{intent}/cash", token,
                {"tenderedMinor": tendered})
    record("a cash payment is captured through the route",
           paid.get("status") == 201 and paid.get("paymentId"),
           f"{paid}")
    payment = paid["paymentId"]
    CONTEXT["cash_payment"] = payment

    figures = rows(f"""
        SELECT tendered_minor::text, change_minor::text, outcome::text, provider::text
          FROM payments.payment WHERE id = '{payment}';""")
    record("the change is what arithmetic on the two stored figures says it is",
           figures and figures[0][0] == str(tendered)
           and figures[0][1] == str(expected_change),
           f"tendered {figures[0][0] if figures else '?'}, change "
           f"{figures[0][1] if figures else '?'}; Python computed {tendered} - {owed} = "
           f"{expected_change}. Recomputed rather than read back and agreed with")

    surface_arithmetic = []
    for bundle in ("pwa", "station", "waiter"):
        for source in sorted((REPO / bundle).rglob("*.ts")):
            body = strip_comments(source.read_text(encoding="utf-8"))
            if re.search(r"\btendered\w*\s*[-+]\s*\w", body) or \
               re.search(r"\bchange\w*\s*=\s*[^;]*[-+]", body):
                surface_arithmetic.append(str(source.relative_to(REPO)))
    record("and no surface computes it (FR-PAY-002)",
           not surface_arithmetic,
           f"{surface_arithmetic or 'none'}. The route sends what the guest handed over "
           f"and nothing else; there is no change field in the request body to send. A "
           f"change amount computed in a browser is a number nobody can reconcile against "
           f"a drawer")

    # ITS OWN INTENT. Against the captured one this would return the first payment — the
    # correct answer to a retry, and the reason it is asserted separately below — and the
    # check would have passed without ever reaching the arithmetic it is about.
    other = a_bill_at(fx.PAY_TABLE)
    short_intent = an_intent(other["bill"], other["total"], "short-tender")
    short = run(APP, f"""
        SELECT payments.record_cash_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{short_intent}', {other["total"] - 1}, '{fx.USER}');""", tx=True, **CTX)
    record("a tender that does not cover what is owed is refused",
           short.failed_with("PAYMENT_TENDER_INSUFFICIENT"),
           short.why() or "less than the amount owed settled the bill")

    allocations = {r[1]: int(r[5]) for r in rows(f"""
        SELECT allocation_id::text, target, bill_id::text, tip_id::text, currency_code,
               amount_minor::text
          FROM payments.allocation_view('{fx.TENANT}', '{payment}');""")}
    record("the payment allocates to the bill balance and to nothing else",
           allocations == {"bill_balance": owed},
           f"{allocations}. The intent carried no tip, so there is no tip allocation — "
           f"not a tip allocation of zero, which would be a row saying a payer tipped")

    outstanding = int(scalar(
        f"SELECT billing.outstanding_balance('{fx.TENANT}', '{bill['bill']}');"))
    record("and what the guest owes is exactly what the allocation did not cover",
           outstanding == 0,
           f"{outstanding} outstanding after allocating {owed} against {bill['total']}")

    # FR-PAY-012's other half, at the capture end. A retry that reached the writer twice
    # returns the FIRST payment rather than making a second.
    retried = scalar(f"""
        SELECT payments.record_cash_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{intent}', {tendered}, '{fx.USER}');""")
    payments_for_intent = count(APP, f"""
        SELECT count(*) FROM payments.payment WHERE intent_id = '{intent}';""", **CTX)
    record("a retry against a captured intent returns the first payment, not a second",
           retried == payment and payments_for_intent == 1,
           f"returned {retried}, first was {payment}; {payments_for_intent} payment(s) "
           f"exist for the intent. Asserted by census as well as by identity, because two "
           f"rows one of which was returned would look the same from the return value")


# ===========================================================================
# 6. The external terminal, and the PCI boundary
# ===========================================================================

# A number that is shaped like a primary account number and is not one: the standard test
# value every card scheme publishes for exactly this purpose. It never leaves this file
# except into a request that must be refused.
PAN_SHAPED = "4111111111111111"
CRYPTOGRAM_SHAPED = "A1B2C3D4E5F60718"


def section_terminal_and_pci() -> None:
    print("\n--- 6. The terminal's result, and no card data anywhere "
          "(FR-PAY-003, FR-PAY-016) ---")

    token = CONTEXT["cashier_token"]

    columns = [r[0] for r in rows("""
        SELECT a.attname FROM pg_attribute a
         WHERE a.attrelid = 'payments.terminal_result'::regclass
           AND a.attnum > 0 AND NOT a.attisdropped ORDER BY 1;""", dsn=ADMIN)]
    record("there is no column a card number could be stored in",
           not any(re.search(r"(^|_)(pan|cvv|cvc|cryptogram|track|number)(_|$)", c)
                   for c in columns),
           f"{columns}. What is here is what is printed on a merchant slip: a scheme, a "
           f"four-digit tail, an approval code. We record what a terminal DID")

    # THE STRONGER OF THE TWO LOCKS. M3-C made payload bounds a CHECK so absence was a
    # property of the table; this is that, generalised — the trigger walks every TEXTUAL
    # column through the catalog rather than a list, so a column added at M4-C is covered
    # the moment it exists.
    guarded = {r[0] for r in rows("""
        SELECT c.relname FROM pg_trigger t
          JOIN pg_class c ON c.oid = t.tgrelid
          JOIN pg_proc p ON p.oid = t.tgfoid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'payments' AND p.proname = 'refuse_card_data'
           AND NOT t.tgisinternal;""", dsn=ADMIN)}
    textual = {r[0] for r in rows("""
        SELECT c.relname FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
          JOIN pg_attribute a ON a.attrelid = c.oid
          JOIN pg_type ty ON ty.oid = a.atttypid
         WHERE n.nspname = 'payments' AND c.relkind = 'r'
           AND a.attnum > 0 AND NOT a.attisdropped
           AND ty.typname IN ('text', 'varchar', 'bpchar', 'json', 'jsonb')
           AND a.attname <> 'currency_code';""", dsn=ADMIN)}
    record("every table that could hold text is guarded, derived from the catalog",
           textual <= guarded,
           f"guarded: {sorted(guarded)}; could hold text: {sorted(textual)}. Unguarded: "
           f"{sorted(textual - guarded) or 'none'}. Enumerated both ways, so a table added "
           f"with a text column and no trigger fails here rather than at the breach")

    refused = call("POST", "/s/v1/terminal-results", token,
                   {"terminalReference": "M4B-TERM-1", "scheme": PAN_SHAPED,
                    "currencyCode": "ETB", "amountMinor": 5000, "outcome": "approved"})
    record("a card number in a field that takes text is refused at the write",
           refused.get("status") in (400, 422),
           f"{refused.get('status')} {refused.get('reason') or refused.get('message', '')}. "
           f"Refused whether it arrives as a scheme, a reference or a column invented "
           f"tomorrow — the trigger asks the catalog which columns are textual")

    stored = count(ADMIN, f"""
        SELECT count(*) FROM payments.terminal_result
         WHERE scheme = '{PAN_SHAPED}' OR terminal_reference = '{PAN_SHAPED}';""")
    record("and nothing was stored",
           stored == 0,
           f"{stored} row(s). Asserted by census against the table rather than inferred "
           f"from the refusal")

    cryptogram = call("POST", "/s/v1/terminal-results", token,
                      {"terminalReference": CRYPTOGRAM_SHAPED, "scheme": "visa",
                       "currencyCode": "ETB", "amountMinor": 5000, "outcome": "approved"})
    record("a cryptogram-shaped value is refused too",
           cryptogram.get("status") in (400, 422),
           f"{cryptogram.get('status')} {cryptogram.get('reason', '')}. Sixteen "
           f"hexadecimal digits is the shortest ARQC anybody ships")

    accepted = call("POST", "/s/v1/terminal-results", token,
                    {"terminalReference": "M4B-TERM-1", "scheme": "visa",
                     "currencyCode": "ETB", "amountMinor": 5000, "outcome": "approved",
                     "maskedTail": "4242", "approvalCode": "A1B2C3"})
    record("and a real slip — scheme, masked tail, approval code — is accepted",
           accepted.get("status") == 201,
           f"{accepted}. The check refuses card data and not card PAYMENTS; a control "
           f"whose green leg never ran would be proving that the route is broken")
    CONTEXT["terminal_result"] = accepted.get("terminalResultId")

    # LOGS AND ANALYTICS, which the requirement names beside storage. M1-D proved
    # redaction by planting a secret and asserting zero occurrences; the same method, with
    # the card number planted through a real request that was refused — because a refused
    # request is precisely the one whose body an error log is most likely to echo.
    log_text = CONTEXT["service"].logs()
    record("and no card-shaped value reaches the service log (FR-PAY-016)",
           PAN_SHAPED not in log_text and CRYPTOGRAM_SHAPED not in log_text,
           f"{len(log_text)} characters of structured log searched for the two planted "
           f"values; {log_text.count(PAN_SHAPED)} and {log_text.count(CRYPTOGRAM_SHAPED)} "
           f"occurrence(s). A card number in a log is a breach rather than a bug, and a "
           f"REFUSED request is the one whose body a log most wants to echo")

    reflected = [k for k, v in ((k, str(v)) for k, v in refused.items())
                 if PAN_SHAPED in v]
    record("and the refusal itself does not repeat what it refused",
           not reflected,
           f"{reflected or 'none'}. The diagnostic names the COLUMN and never the value: "
           f"FR-SEC-007 counts error text as a place a secret must not be, and an error "
           f"message is a log with extra steps")


# ===========================================================================
# 7. Proof-based mobile money, and an attestation that names somebody
# ===========================================================================

def section_proof() -> None:
    print("\n--- 7. Proof confirmation, verified by a named person "
          "(FR-PAY-014, FR-PAY-015) ---")

    token = CONTEXT["cashier_token"]
    bill = a_bill_at(fx.PAY_TABLE)

    raised = call("POST", "/s/v1/proofs", token,
                  {"provider": "telebirr_proof", "currencyCode": "ETB",
                   "amountMinor": bill["total"], "providerReference": "TB-4471902",
                   "maskedIdentifier": "•••1902"})
    record("a proof is raised PENDING, and there is no way to raise it verified",
           raised.get("status") == 201 and raised.get("state") == "pending",
           f"{raised}. FR-PAY-014 leaves unverified proof pending rather than paid, and "
           f"payments.raise_proof() has no parameter with which to claim otherwise")
    proof = raised["proofId"]

    intent = an_intent(bill["bill"], bill["total"], "proof-unverified")
    early = call("POST", f"/s/v1/payments/{intent}/proof", token,
                 {"proofId": proof, "tenderedMinor": bill["total"]})
    record("an unverified proof cannot pay a bill",
           early.get("status") == 402
           and early.get("reason") == "UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM",
           f"{early}. 402 rather than 400 or 403: this is not a malformed request and not "
           f"a permission problem — it is a statement that the money is not there")

    # AND NOT BY PRE-LOADING THE ATTESTATION EITHER. The row cannot carry a verifier while
    # pending, so there is nothing to flip.
    preloaded = run(ADMIN, f"""
        UPDATE payments.proof_confirmation
           SET verified_by_user_id = '{fx.USER}', verified_at = now()
         WHERE id = '{proof}';""", tx=True)
    record("and a pending proof cannot be quietly pre-loaded with a verifier",
           not preloaded.ok,
           preloaded.why() or "a pending proof was given a verifier, leaving only the "
                              "state to change. Both halves of the attestation are "
                              "constrained together, so there is no half-verified row")

    blank = run(APP, f"""
        SELECT set_config('app.session_id', '{CONTEXT["cashier_session"]}', false);
        SELECT payments.verify_proof('{fx.TENANT}', '{proof}', '   ');""",
        tx=True, **CTX)
    record("a verification with nothing in it is refused",
           blank.failed_with("VERIFICATION_WITHOUT_ATTRIBUTOR"),
           blank.why() or "an empty attestation was accepted. A tick-box is what "
                          "FR-PAY-014 exists to refuse — the requirement asks what the "
                          "verifier SAW")

    verified = call("POST", f"/s/v1/proofs/{proof}/verify", token,
                    {"whatYouSaw": "Telebirr shows ETB 368.00 received from 09••••1902 "
                                   "at 20:14, reference TB-4471902"})
    record("and a verification by a live session is recorded whole",
           verified.get("state") == "verified",
           f"{verified}")

    attestation = rows(f"""
        SELECT verified_by_user_id::text, verified_by_session_id::text,
               (verified_at IS NOT NULL)::text, length(what_the_verifier_saw)::text
          FROM payments.proof_confirmation WHERE id = '{proof}';""")
    record("who verified is the session's owner, and was never a parameter",
           attestation and attestation[0][0] == CONTEXT["cashier_user"]
           and attestation[0][1] == CONTEXT["cashier_session"]
           and attestation[0][2] == "true" and int(attestation[0][3]) > 20,
           f"{attestation}. The route body carries only what they saw; the person and "
           f"their session come from identity.session, so there is no argument by which "
           f"somebody could attest on another's behalf. M3-D's override approver, again")

    paid = call("POST", f"/s/v1/payments/{intent}/proof", token,
                {"proofId": proof, "tenderedMinor": bill["total"]})
    record("and once verified it settles the bill",
           paid.get("status") == 201,
           f"{paid}")

    twice = run(APP, f"""
        SELECT set_config('app.session_id', '{CONTEXT["cashier_session"]}', false);
        SELECT payments.verify_proof('{fx.TENANT}', '{proof}', 'looked again');""",
        tx=True, **CTX)
    record("a resolved attestation is not revisited",
           twice.failed_with("PROOF_ALREADY_RESOLVED"),
           twice.why() or "a proof was verified twice. A second look is a second proof, "
                          "and overwriting the first loses who said what")


# ===========================================================================
# 8. Dual allocation, and figures that are read rather than recomputed
# ===========================================================================

def section_allocation() -> None:
    print("\n--- 8. Separate allocations, stored and never recomputed "
          "(FR-PAY-017, FR-PAY-006, FR-PAY-007) ---")

    token = CONTEXT["cashier_token"]
    bill = a_bill_at(fx.PAY_TABLE)

    # A share and a tip, so the payment carries BOTH allocations. FR-BIL-015's per-payer
    # tip is M4-A's; what is new is that a payment now carries it as its own row.
    split = run(APP, f"""
        SELECT billing.split_equally('{fx.TENANT}', '{bill["bill"]}', 1);""",
        tx=True, **CTX)
    if not split.ok:
        raise ProbeFailed("split_equally", split.err)
    share = scalar(f"""
        SELECT id FROM billing.bill_share WHERE bill_id = '{bill["bill"]}'
         ORDER BY share_number LIMIT 1;""")
    tip_amount = 4300
    tip = scalar(f"""
        INSERT INTO billing.tip (tenant_id, outlet_id, bill_share_id, currency_code,
                                 amount_minor)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{share}', 'ETB', {tip_amount})
        RETURNING id;""")

    intent = an_intent(bill["bill"], bill["total"], "dual", tip=tip_amount, tip_id=tip,
                       share=share)
    owed = bill["total"] + tip_amount
    paid = call("POST", f"/s/v1/payments/{intent}/cash", token,
                {"tenderedMinor": owed})
    payment = paid["paymentId"]

    view = {r[1]: (int(r[5]), r[2] or None, r[3] or None) for r in rows(f"""
        SELECT allocation_id::text, target, bill_id::text, tip_id::text, currency_code,
               amount_minor::text
          FROM payments.allocation_view('{fx.TENANT}', '{payment}');""")}
    record("one payment, two allocations, each naming what it went to",
           view.get("bill_balance", (0, None, None))[0] == bill["total"]
           and view.get("tip", (0, None, None))[0] == tip_amount
           and view["bill_balance"][1] == bill["bill"]
           and view["tip"][2] == tip,
           f"{view}. Separate ROWS rather than two columns, which is what buys the "
           f"independent reversal FR-PAY-009 asks for: there are two things to link to")

    balance_after = int(scalar(
        f"SELECT billing.outstanding_balance('{fx.TENANT}', '{bill['bill']}');"))
    record("and the tip allocation reduced no balance",
           balance_after == 0,
           f"{balance_after} outstanding. The bill allocation was {bill['total']} against "
           f"a total of {bill['total']}; the {tip_amount} tip settled nothing because a "
           f"tip is not part of a bill balance — M4-A's doctrine, on the other side of "
           f"the counter")

    # NO HIDDEN RECOMPUTATION, proved by moving the thing a recomputation would follow.
    # The bill is reissued at a different total; if the allocation were derived rather
    # than stored, it would follow the new document.
    before = view["bill_balance"][0]
    reason = fx.reason_code("M4A_BILL_REISSUED")
    override = an_override("payment.refund", "payment_allocation",
                           scalar(f"""SELECT id FROM payments.allocation
                                       WHERE payment_id = '{payment}'
                                         AND target = 'bill_balance';"""),
                           reason, "reissued to prove the allocation does not follow it")
    # THE ARGUMENT ORDER IS THE FUNCTION'S, not the one a reader would guess:
    # (tenant, outlet, bill, override, reason_code, reason_text, actor). Passing the actor
    # fourth put the reason code where the actor belongs and failed on a foreign key — and
    # the check below still passed, because a bill that was never reissued cannot have
    # moved an allocation. A probe whose setup failed silently proves nothing, so the
    # reissue is now required to succeed before the comparison is believed.
    reissued = run(APP, f"""
        SELECT billing.reissue_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill["bill"]}',
            '{override}', '{reason}', 'reissued to a corrected check', '{fx.USER}');""",
        tx=True, **CTX)
    if not reissued.ok:
        raise ProbeFailed("reissue_bill", reissued.err)
    after = int(scalar(f"""
        SELECT amount_minor FROM payments.allocation
         WHERE payment_id = '{payment}' AND target = 'bill_balance';"""))
    record("an allocation does not follow the bill it was made against",
           before == after,
           f"{before} before the bill was reissued and {after} after, and the reissue "
           f"is required to have succeeded before this is believed. This is what "
           f"'no hidden recomputation' means in practice: a figure derived at read time "
           f"would agree with today's document rather than with what the guest handed "
           f"over, and the two differ exactly when somebody is disputing a bill")

    derived_readers = [r[0] for r in rows("""
        SELECT n.nspname || '.' || p.proname
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'payments'
           AND p.prosrc ~ 'bill_total_minor'
         ORDER BY 1;""", dsn=ADMIN)]
    record("and no function in payments derives an allocation from a bill total",
           derived_readers == ["payments.order_is_paid"],
           f"{derived_readers}. payments.order_is_paid() is the one deliberate reader and "
           f"it COMPARES rather than derives: it asks whether the allocations reach the "
           f"total, and writes nothing. Enumerated from the catalog, so a reader added "
           f"later appears here without anybody extending a list")

    CONTEXT["dual_payment"] = payment
    CONTEXT["dual_tip"] = tip


# ===========================================================================
# 9. Reversal: independent, authorized, and never self-approved
# ===========================================================================

def section_reversal() -> None:
    print("\n--- 9. Refund and reversal, with maker-checker (FR-PAY-009, NC-M4-004) ---")

    token = CONTEXT["cashier_token"]
    payment = CONTEXT["dual_payment"]
    reason = fx.reason_code("M4B_GUEST_REFUNDED")

    allocations = {r[0]: r[1] for r in rows(f"""
        SELECT target::text, id::text FROM payments.allocation
         WHERE payment_id = '{payment}';""")}
    tip_allocation = allocations["tip"]
    bill_allocation = allocations["bill_balance"]

    threshold = int(scalar(f"""
        SELECT payments.reversal_threshold_minor('{fx.TENANT}', '{fx.OUTLET_H1}');"""))
    record("the approval threshold comes from the outlet's refund policy",
           threshold == fx.REFUND_APPROVAL_THRESHOLD_MINOR,
           f"{threshold}, and config.policy says {fx.REFUND_APPROVAL_THRESHOLD_MINOR}. "
           f"Not a literal in a migration: 'how much needs a manager' is an operator's "
           f"decision, and an unset threshold means EVERY refund needs one rather than "
           f"none")

    # A PART of the tip, and deliberately small: the amounts here have to sit either side
    # of the threshold AND inside the allocations they reverse, and an amount that broke
    # the second rule would fail with REVERSAL_EXCEEDS_ALLOCATION while appearing to prove
    # something about approval.
    tip_reversed = 1000
    small = call("POST", f"/s/v1/allocations/{tip_allocation}/reversal", token,
                 {"kind": "reversal", "amountMinor": tip_reversed,
                  "reasonCodeId": reason, "reasonText": "guest asked for the tip back"})
    record("below the threshold one person may act alone",
           small.get("status") == 201,
           f"{small}. A control whose green leg never ran would be proving the route is "
           f"broken rather than that the rule works")

    large = call("POST", f"/s/v1/allocations/{bill_allocation}/reversal", token,
                 {"kind": "refund", "amountMinor": threshold + 1,
                  "reasonCodeId": reason, "reasonText": "the whole order was wrong"})
    record("at or above it, an unapproved refund is refused by name",
           large.get("status") == 403 and large.get("reason") == "SELF_APPROVAL_ACCEPTED",
           f"{large}. A refund a cashier can grant themselves is the whole of what "
           f"maker-checker exists to prevent")

    # THE CREDENTIAL-SHARING CASE, which is the one that looks compliant. M3-D built
    # pos.approve_override() so the approver is DERIVED from the approving session; a
    # manager who typed their password into the cashier's terminal is authenticated AS
    # that session and comes back as the cashier.
    cashier_session = CONTEXT["cashier_session"]
    fx.step_up(cashier_session, "payment.refund")
    shared = run(APP, f"""
        SELECT set_config('app.session_id', '{cashier_session}', false);
        SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', 'payment.refund',
            '{cashier_session}', '{reason}', 'payment_allocation', '{bill_allocation}',
            'approving my own refund');""", tx=True, **CTX)
    record("and a cashier cannot approve their own refund from their own terminal",
           not shared.ok,
           shared.why() or "one session approved its own action. The compliant case and "
                           "the violation would be identical in the audit trail, which is "
                           "why M3-D made the approver derived rather than named")

    override = an_override("payment.refund", "payment_allocation", bill_allocation,
                           reason, "the whole order was wrong")
    approved = call("POST", f"/s/v1/allocations/{bill_allocation}/reversal", token,
                    {"kind": "refund", "amountMinor": threshold + 1,
                     "reasonCodeId": reason, "reasonText": "the whole order was wrong",
                     "overrideId": override})
    record("with two people it goes through",
           approved.get("status") == 201,
           f"{approved}")

    borrowed = an_override("payment.refund", "payment_allocation", tip_allocation,
                           reason, "an approval for a different allocation")
    misused = call("POST", f"/s/v1/allocations/{bill_allocation}/reversal", token,
                   {"kind": "refund", "amountMinor": threshold + 1,
                    "reasonCodeId": reason, "reasonText": "reusing somebody else's paper",
                    "overrideId": borrowed})
    record("and an approval for one refund does not authorize the next",
           misused.get("status") == 403
           and misused.get("reason") == "SELF_APPROVAL_ACCEPTED",
           f"{misused}. pos.override_approval already refuses an approver who is the "
           f"actor; what it cannot know is whether the approval belongs to THIS refund, "
           f"and without that a cashier points at a manager's approval of something else")

    # INDEPENDENT REVERSAL, which is what separate rows were for.
    figures = {r[0]: (int(r[1]), int(r[2])) for r in rows(f"""
        SELECT target, amount_minor::text, reversed_minor::text
          FROM payments.allocation_view('{fx.TENANT}', '{payment}');""")}
    record("the tip was reversed and the bill payment separately, neither touching the other",
           figures["tip"][1] == tip_reversed
           and figures["bill_balance"][1] == threshold + 1,
           f"{figures}. FR-PAY-009's 'separate linked reversal records' is only "
           f"expressible because there are two allocations to link to")

    # BELOW the threshold, so this cannot be refused for needing an approval, and ABOVE
    # what is left of the tip once 1000 has already gone back. The two rules have to be
    # separable or neither is proved.
    remaining = view_tip_allocation = figures["tip"][0] - figures["tip"][1]
    excessive = call("POST", f"/s/v1/allocations/{tip_allocation}/reversal", token,
                     {"kind": "reversal", "amountMinor": remaining + 1,
                      "reasonCodeId": reason,
                      "reasonText": "one minor unit more than is left"})
    record("and a reversal cannot return more than arrived",
           excessive.get("status") == 409
           and excessive.get("reason") == "REVERSAL_EXCEEDS_ALLOCATION",
           f"{excessive}; {remaining} was left of a {figures['tip'][0]} tip and "
           f"{remaining + 1} was asked for, below the {threshold} approval threshold so "
           f"the refusal can only be about the amount. Asserted by census over every "
           f"reversal against the allocation, "
           f"so three partial refunds that together exceed it are refused as surely as "
           f"one that does")


# ===========================================================================
# 10. FR-ORD-007B: what "verified" means, in the code
# ===========================================================================

def section_payment_dependent_acceptance() -> None:
    print("\n--- 10. Acceptance on a verified payment outcome "
          "(FR-ORD-007B, FR-ORD-011, FR-ORD-012A) ---")

    outlet = fx.OUTLET_H1

    # READ IT FIRST. The restore below used to write 'automatic', which is a GUESS about
    # what was there — and it was wrong: M3-A configures guest_qr as staff_confirmed, so
    # the "restore" left every later order auto-accepting and the next section's helper
    # failed with "the order is accepted, not submitted". A cleanup that does not restore
    # what it found is a fixture writing configuration.
    was = scalar(f"""
        SELECT p.payload -> 'acceptance' ->> 'guest_qr' FROM config.policy p
         WHERE p.tenant_id = '{fx.TENANT}' AND p.category = 'ordering'
           AND (p.outlet_id = '{outlet}' OR p.outlet_id IS NULL)
           AND p.effective_to IS NULL LIMIT 1;""", dsn=ADMIN)
    if not was:
        raise CommandUnreadable(
            "the outlet's ordering policy names no acceptance mode for guest_qr, so this "
            "section would change a setting it cannot put back")

    policy = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
        SELECT set_config('app.outlet_id', '{outlet}', false);
        UPDATE config.policy
           SET payload = jsonb_set(payload, '{{acceptance,guest_qr}}',
                                   '"payment_dependent"')
         WHERE tenant_id = '{fx.TENANT}' AND category = 'ordering'
           AND (outlet_id = '{outlet}' OR outlet_id IS NULL)
           AND effective_to IS NULL;""")
    if not policy.ok:
        raise ProbeFailed("making the outlet payment-dependent", policy.err)

    try:
        session = fx.m4a.fresh_occupancy(fx.PAY_TABLE)
        guest = fx.m4a.guest_on(session)
        order = a_submitted_order(session, guest,
                                  ((fx.VARIANT_TIBS_ONE, fx.ITEM_TIBS, 1),))

        state = scalar(f"""
            SELECT state::text FROM ordering.customer_order WHERE id = '{order}';""")
        record("a payment-dependent order stays submitted rather than auto-accepting",
               state == "submitted",
               f"{state}. ordering.submit_order() auto-accepts only 'automatic', so this "
               f"has been true since M3-A; what M4-B adds is a way THROUGH the refusal "
               f"rather than the refusal itself")

        unpaid = run(APP, f"""
            SELECT ordering.accept_order('{fx.TENANT}', '{order}', '{fx.USER}');""",
            tx=True, **CTX)
        record("and staff cannot accept it while the bill is unpaid",
               unpaid.failed_with("ACCEPTANCE_AWAITS_PAYMENT_VERIFICATION"),
               unpaid.why() or "an unpaid payment-dependent order was accepted. 0020's "
                               "refusal is still the answer for everyone without a "
                               "verified outcome, which is the larger half of FR-ORD-007B")

        check = scalar(f"""
            SELECT billing.open_check('{fx.TENANT}', '{outlet}', '{session}',
                                      '{fx.USER}');""")
        allocated = run(APP, f"""
            SELECT billing.allocate_to_check('{fx.TENANT}', '{outlet}', '{check}',
                                             l.id, l.quantity::integer)
              FROM ordering.order_line l WHERE l.order_id = '{order}';""", **CTX)
        if not allocated.ok:
            raise ProbeFailed("allocate_to_check", allocated.err)
        bill = scalar(f"""
            SELECT billing.issue_bill('{fx.TENANT}', '{outlet}', '{check}',
                                      '{fx.USER}', 'en');""")
        total = int(scalar(
            f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';"))

        # A TIP DOES NOT BUY ACCEPTANCE. The one place at this gate where somebody might
        # have been tempted to add it up.
        share_made = run(APP, f"""
            SELECT billing.split_equally('{fx.TENANT}', '{bill}', 1);""", tx=True, **CTX)
        if not share_made.ok:
            raise ProbeFailed("split_equally", share_made.err)
        share = scalar(f"""
            SELECT id FROM billing.bill_share WHERE bill_id = '{bill}' LIMIT 1;""")
        tip = scalar(f"""
            INSERT INTO billing.tip (tenant_id, outlet_id, bill_share_id, currency_code,
                                     amount_minor)
            VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{share}', 'ETB', {total})
            RETURNING id;""")
        tip_intent = an_intent(bill, 0, "tip-only", tip=total, tip_id=tip, share=share)
        tip_paid = scalar(f"""
            SELECT payments.record_cash_payment('{fx.TENANT}', '{outlet}',
                '{tip_intent}', {total}, '{fx.USER}');""")
        tipped_only = run(APP, f"""
            SELECT ordering.accept_order('{fx.TENANT}', '{order}', '{fx.USER}');""",
            tx=True, **CTX)
        record("a generous tip does not buy acceptance of an unpaid order",
               tipped_only.failed_with("ACCEPTANCE_AWAITS_PAYMENT_VERIFICATION"),
               f"{tipped_only.why() or 'accepted on a tip alone'}; {total} was paid "
               f"entirely to the tip and payments.order_is_paid() sums BILL BALANCE "
               f"allocations only. Payment {tip_paid} exists and settles nothing")

        intent = an_intent(bill, total, "payment-dependent")
        run(APP, f"""
            SELECT payments.record_cash_payment('{fx.TENANT}', '{outlet}', '{intent}',
                {total}, '{fx.USER}');""", tx=True, **CTX)

        accepted = run(APP, f"""
            SELECT ordering.accept_order('{fx.TENANT}', '{order}', '{fx.USER}');""",
            tx=True, **CTX)
        record("and once the bill balance is settled, the order is accepted",
               accepted.ok,
               accepted.why() or "accepted after a live, approved, attributed payment "
                                 "covered the bill")

        mode = scalar(f"""
            SELECT e.after ->> 'acceptance_mode' FROM ordering.order_event e
             WHERE e.order_id = '{order}' AND e.kind = 'accepted';""")
        record("and the event records that it was accepted BECAUSE it was paid",
               mode == "payment_dependent",
               f"acceptance_mode: {mode!r}. An order accepted because money arrived is "
               f"distinguishable afterwards from one a member of staff waved through, "
               f"which is the difference somebody will ask about")

        # M3-D's manager, whose role grants order.void. M4-B's finance manager may
        # approve a refund and verify a drawer and nothing else — which is the point of
        # giving this slice its own people rather than widening somebody else's role.
        void_session, _ = fx.staff_session(fx.USER_MANAGER)
        fx.step_up(void_session, "order.void")
        voided = run(APP, f"""
            SELECT set_config('app.session_id', '{void_session}', false);
            SELECT ordering.void_order('{fx.TENANT}', '{order}',
                (SELECT id FROM config.reason_code WHERE tenant_id = '{fx.TENANT}'
                  AND category = 'void' LIMIT 1), '{fx.USER}');""", tx=True, **CTX)
        record("a PAID order cannot be voided (FR-ORD-012A)",
               voided.failed_with("VOID_OF_PAID_ORDER"),
               voided.why() or "a paid order was voided and the money stayed. At M3-A "
                               "this precondition was asserted against an empty set "
                               "because no payment artifact existed to make it false; it "
                               "can be false now, and is")

        cancelled = run(APP, f"""
            SELECT ordering.cancel_order('{fx.TENANT}', '{order}',
                (SELECT id FROM config.reason_code WHERE tenant_id = '{fx.TENANT}'
                  AND category = 'order_cancellation' AND status = 'active' LIMIT 1),
                '{fx.USER}');""", tx=True, **CTX)
        record("and the cancellation policy now has its payment dimension (FR-ORD-011)",
               cancelled.failed_with("CANCELLATION_REFUSED_BY_POLICY"),
               cancelled.why() or "a paid order was cancelled without returning the "
                                  "money. State, channel, reason and preparation progress "
                                  "have decided since M3-A; payment is the fifth")
    finally:
        restored = run(ADMIN, f"""
            SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
            SELECT set_config('app.outlet_id', '{outlet}', false);
            UPDATE config.policy
               SET payload = jsonb_set(payload, '{{acceptance,guest_qr}}',
                                       to_jsonb('{was}'::text))
             WHERE tenant_id = '{fx.TENANT}' AND category = 'ordering'
               AND (outlet_id = '{outlet}' OR outlet_id IS NULL)
               AND effective_to IS NULL;""")
        if not restored.ok:
            raise ProbeFailed("restoring the acceptance policy", restored.err)


# ===========================================================================
# 11. The drawer (FR-CSH-001 … FR-CSH-004, FR-CSH-007)
# ===========================================================================

def section_cash_shift() -> None:
    print("\n--- 11. Cash shifts, movements, counts and custody (FR-CSH-001 … 007) ---")

    token = CONTEXT["cashier_token"]
    float_minor = 50000

    opened = call("POST", "/s/v1/cash/shifts", token,
                  {"terminalDeviceId": fx.TERMINAL_DEVICE, "currencyCode": "ETB",
                   "openingFloatMinor": float_minor})
    record("a drawer opens with a counted float on an assigned terminal (FR-CSH-001)",
           opened.get("status") == 201 and opened.get("state") == "open",
           f"{opened}")
    shift = opened["shiftId"]
    CONTEXT["shift"] = shift

    second = call("POST", "/s/v1/cash/shifts", token,
                  {"terminalDeviceId": fx.TERMINAL_DEVICE, "currencyCode": "ETB",
                   "openingFloatMinor": 1000})
    record("and a second live drawer on the same till is refused",
           second.get("status") in (409, 500) and second.get("shiftId") is None,
           f"{second}. Two shifts on one till is two people counting the same notes, and "
           f"the difference between them is unattributable by construction")

    # A CASH PAYMENT REACHES THE DRAWER, in the same transaction that captured it.
    bill = a_bill_at(fx.CASH_TABLE)
    intent = an_intent(bill["bill"], bill["total"], "drawer")
    tendered = bill["total"] + 2000
    paid = scalar(f"""
        SELECT payments.record_cash_payment('{fx.TENANT}', '{fx.OUTLET_H1}', '{intent}',
            {tendered}, '{fx.USER_CASHIER}');""")
    movement = rows(f"""
        SELECT kind::text, amount_minor::text FROM cash.movement
         WHERE payment_id = '{paid}';""")
    record("a cash payment becomes a sales receipt in the drawer (FR-CSH-002)",
           movement and movement[0][0] == "sales_receipt"
           and movement[0][1] == str(tendered - 2000),
           f"{movement}. The till gains what was tendered LESS the change, because the "
           f"guest took the change away with them. Both figures are read from the "
           f"payment's stored columns rather than from the bill")

    kinds = {r[0] for r in rows("""
        SELECT unnest(enum_range(NULL::cash.movement_kind))::text;""")}
    record("and all six kinds FR-CSH-002 names exist as distinct movements",
           kinds == {"sales_receipt", "refund", "payout", "drop", "float_adjustment",
                     "transfer_in", "transfer_out"},
           f"{sorted(kinds)}. Transfers are two kinds because a transfer has a direction "
           f"and a single 'transfer' would need a sign somebody chose")

    wrong_way = run(APP, f"""
        INSERT INTO cash.movement
            (tenant_id, outlet_id, shift_id, kind, currency_code, amount_minor,
             actor_user_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{shift}', 'payout', 'ETB', 5000,
                '{fx.USER_CASHIER}');""", tx=True, **CTX)
    record("a payout cannot be recorded as money coming in",
           not wrong_way.ok,
           wrong_way.why() or "a payout increased the drawer. The direction is a fact "
                              "about the KIND rather than a sign somebody fills in, so a "
                              "payout entered as an increase is unrepresentable")

    duplicate = run(APP, f"""
        SELECT cash.post_cash_payment('{fx.TENANT}', '{fx.OUTLET_H1}', '{shift}',
                                      '{paid}');""", tx=True, **CTX)
    record("and one payment cannot be counted into the drawer twice",
           not duplicate.ok,
           duplicate.why() or "the same notes were counted twice. UNIQUE (payment_id) is "
                              "what makes FR-PAY-012's retry safe on this side too")

    # THE COUNT (FR-CSH-003), recomputed in Python.
    expected = int(scalar(
        f"SELECT cash.expected_in_drawer('{fx.TENANT}', '{shift}');"))
    python_expected = float_minor + (tendered - 2000)
    record("the expected drawer contents are the float plus every signed movement",
           expected == python_expected,
           f"database says {expected}; Python computed {float_minor} + "
           f"{tendered - 2000} = {python_expected}. Recomputed rather than read back")

    short_by = 700
    counted = expected - short_by
    count_answer = call("POST", f"/s/v1/cash/shifts/{shift}/count", token,
                        {"phase": "closing", "tally": fx.tally_for(counted)})
    record("a count records expected, counted and the difference (FR-CSH-003)",
           count_answer.get("status") == 201
           and count_answer.get("expected_minor") == str(expected)
           and count_answer.get("counted_minor") == str(counted)
           and count_answer.get("over_short_minor") == str(-short_by),
           f"{count_answer}. The counted total is the SUM OF THE DENOMINATIONS and not a "
           f"number the cashier types beside them: a count whose total and breakdown are "
           f"two independent inputs is one in which either can be adjusted until the "
           f"evening balances")

    tallied = int(scalar(f"""
        SELECT sum(subtotal_minor) FROM cash.denomination_tally
         WHERE count_id = '{count_answer["countId"]}';"""))
    record("and the denominations add up to the counted total",
           tallied == counted,
           f"{tallied} against {counted}. Enforced by a deferred constraint trigger as "
           f"well as computed by the writer, so a tally inserted around the writer fails "
           f"too")

    # CUSTODY (FR-CSH-007)
    custody = call("POST", f"/s/v1/cash/shifts/{shift}/custody", token,
                   {"destination": "safe", "sealedBagReference": f"BAG-{RUN_NONCE[:6]}",
                    "amountMinor": 10000,
                    "acceptedByUserId": fx.USER_FINANCE_MANAGER})
    record("cash to the safe records a sealed bag and both people (FR-CSH-007)",
           custody.get("status") == 201,
           f"{custody}. Two names, because a chain of custody with one link in it is not "
           f"a chain")

    same_bag = call("POST", f"/s/v1/cash/shifts/{shift}/custody", token,
                    {"destination": "safe",
                     "sealedBagReference": f"BAG-{RUN_NONCE[:6]}",
                     "amountMinor": 5000,
                     "acceptedByUserId": fx.USER_FINANCE_MANAGER})
    record("and a seal number cannot be reused",
           same_bag.get("status") in (409, 500) and same_bag.get("custodyId") is None,
           f"{same_bag}. A reused reference makes two transfers indistinguishable in "
           f"exactly the circumstances somebody would want them to be")


# ===========================================================================
# 12. Closing, verifying, and the shift nobody may reopen and forget
# ===========================================================================

def section_shift_closure() -> None:
    print("\n--- 12. Submission, verification, the lock, and NC-M4-006 ---")

    token = CONTEXT["cashier_token"]
    manager_token = CONTEXT["manager_token"]
    shift = CONTEXT["shift"]

    submitted = call("POST", f"/s/v1/cash/shifts/{shift}/transition", token,
                     {"toState": "submitted"})
    record("the cashier submits the drawer (FR-CSH-004)",
           submitted.get("state") == "submitted", f"{submitted}")

    # NC-M4-004 on the drawer. The cashier's own session cannot verify the count they
    # made, and the refusal comes from the session rather than from a name in a body.
    self_verified = call("POST", f"/s/v1/cash/shifts/{shift}/transition", token,
                         {"toState": "verified"})
    record("the cashier cannot verify their own count",
           self_verified.get("status") == 403
           and self_verified.get("reason") == "SELF_APPROVAL_ACCEPTED",
           f"{self_verified}. The verifier is read from the live session, so a manager "
           f"who typed their password into the cashier's terminal resolves to the cashier "
           f"— the credential-sharing case, refused by the same reasoning M3-D used")

    verified = call("POST", f"/s/v1/cash/shifts/{shift}/transition", manager_token,
                    {"toState": "verified"})
    record("and a different person, on their own session, can",
           verified.get("state") == "verified", f"{verified}")

    attribution = rows(f"""
        SELECT verified_by_user_id::text, verified_by_session_id::text
          FROM cash.shift WHERE id = '{shift}';""")
    record("the verifier and their session are both recorded",
           attribution and attribution[0][0] == fx.USER_FINANCE_MANAGER
           and attribution[0][1] == CONTEXT["manager_session"],
           f"{attribution}. Recording the session as well as the person is what makes the "
           f"credential-sharing case detectable at all")

    finalized = call("POST", f"/s/v1/cash/shifts/{shift}/transition", manager_token,
                     {"toState": "finalized"})
    record("a verified drawer can be finalized", finalized.get("state") == "finalized",
           f"{finalized}")

    locked = run(APP, f"""
        INSERT INTO cash.movement
            (tenant_id, outlet_id, shift_id, kind, currency_code, amount_minor,
             actor_user_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{shift}', 'sales_receipt', 'ETB',
                1000, '{fx.USER_CASHIER}');""", tx=True, **CTX)
    record("and a finalized drawer takes no further movement (FR-CSH-004)",
           locked.failed_with("FINALIZED_SHIFT_MUTATED"),
           locked.why() or "money landed in a drawer somebody had already signed for. "
                           "The count has been made; a movement arriving now would change "
                           "a total retrospectively")

    # NC-M4-006. Reopening is authorized, and the way OUT is narrower than the way in.
    reason = fx.reason_code("M4B_DRAWER_RECOUNTED")
    override = an_override("cash.shift.verify", "cash_shift", shift, reason,
                           "the count was 700 short and needs looking at")
    reopened = call("POST", f"/s/v1/cash/shifts/{shift}/transition", manager_token,
                    {"toState": "reopened", "overrideId": override,
                     "reasonCodeId": reason,
                     "reasonText": "the count was 700 short and needs looking at"})
    record("a finalized drawer can be reopened, by authority and with a reason",
           reopened.get("state") == "reopened", f"{reopened}")

    straight_back = call("POST", f"/s/v1/cash/shifts/{shift}/transition", manager_token,
                         {"toState": "finalized"})
    record("but a reopened drawer can never be finalized again (NC-M4-006)",
           straight_back.get("status") == 409
           and straight_back.get("reason") == "CASH_SHIFT_TRANSITION_INVALID",
           f"{straight_back}. There is no edge from 'reopened' to 'finalized'. Its only "
           f"terminal state is 'resolved', and that costs a recount and an approval")

    resubmitted = call("POST", f"/s/v1/cash/shifts/{shift}/transition", token,
                       {"toState": "submitted"})
    reverified = call("POST", f"/s/v1/cash/shifts/{shift}/transition", manager_token,
                      {"toState": "verified"})
    unresolved = call("POST", f"/s/v1/cash/shifts/{shift}/transition", manager_token,
                      {"toState": "resolved",
                       "overrideId": an_override("cash.shift.verify", "cash_shift", shift,
                                                 reason, "resolving without a recount")})
    record("and resolving without a recount is refused by name",
           unresolved.get("status") == 409
           and unresolved.get("reason") == "REOPENED_SHIFT_NOT_RESOLVED",
           f"{resubmitted.get('state')} then {reverified.get('state')} then "
           f"{unresolved}. Closing a hole in the record by declaring it shut is the "
           f"failure "
           f"the control is named for")

    exceptions = call("GET", "/s/v1/cash/exceptions", manager_token)
    kinds = {e["kind"] for e in exceptions.get("exceptions", [])}
    record("while unresolved, the drawer appears in the exception report (FR-CSH-008)",
           "reopened_not_resolved" in kinds,
           f"{sorted(kinds)}. Every row is a query over recorded facts rather than a flag, "
           f"so an exception cannot be cleared by forgetting to raise it")

    recount = call("POST", f"/s/v1/cash/shifts/{shift}/count", token,
                   {"phase": "recount",
                    "tally": fx.tally_for(int(scalar(
                        f"SELECT cash.expected_in_drawer('{fx.TENANT}', '{shift}');")))})
    resolved = call("POST", f"/s/v1/cash/shifts/{shift}/transition", manager_token,
                    {"toState": "resolved",
                     "overrideId": an_override("cash.shift.verify", "cash_shift", shift,
                                               reason, "recounted and reconciled")})
    record("and with a recount and an approval it reaches a resolved state",
           recount.get("status") == 201 and resolved.get("state") == "resolved",
           f"recount {recount.get('countId')}, {resolved}")

    # coalesce in SQL rather than in Python: the first transition has no from_state, and a
    # NULL rendered by psql is an empty field the row splitter drops — so the row came
    # back with one column and the index error blamed the probe rather than the data.
    history = [f"{r[0]}→{r[1]}" for r in rows(f"""
        SELECT coalesce(from_state::text, '-'), to_state::text
          FROM cash.shift_transition
         WHERE shift_id = '{shift}' ORDER BY sequence_number;""")]
    record("and the whole life of the drawer is kept, including the finalization it lost",
           "finalized→reopened" in history and history[0] == "-→open",
           f"{history}. cash.shift_transition is append-only, so a drawer that was closed, "
           f"reopened and resolved cannot come to look like one that never closed — which "
           f"is the record somebody will actually ask for")

    after = call("GET", "/s/v1/cash/exceptions", manager_token)
    # THIS drawer, not the report as a whole. The controls below deliberately leave other
    # shifts reopened, and a check over every row would report their exceptions as this
    # one's failure to clear — which is a check that answers a question nobody asked.
    mine = {e["kind"] for e in after.get("exceptions", []) if e["shift_id"] == shift}
    record("and it leaves the exception report once it is resolved",
           "reopened_not_resolved" not in mine,
           f"{sorted(mine)} for shift {shift[:8]}, out of "
           f"{len(after.get('exceptions', []))} exception(s) in the outlet. An exception "
           f"that never cleared would be as useless as one that never fired")


# ===========================================================================
# 13. Reconciliation, with the tip kept out of the takings
# ===========================================================================

def section_reconciliation() -> None:
    print("\n--- 13. Reconciliation without merging tips into revenue (FR-PAY-013) ---")

    token = CONTEXT["manager_token"]
    answer = call("GET", "/s/v1/payments/reconciliation?from=2000-01-01&to=2100-01-01",
                  token)
    providers = {p["provider"]: p for p in answer.get("providers", [])}
    record("the reconciliation reports each provider with its own figures",
           "cash" in providers and int(providers["cash"]["payment_count"]) >= 1,
           f"{sorted(providers)}. Bill allocations, tip allocations, tender totals and "
           f"provider references, side by side")

    fields = set(providers.get("cash", {}))
    record("and bill and tip allocations are separate fields with no field summing them",
           {"bill_allocation_minor", "tip_allocation_minor"} <= fields
           and not any("revenue" in f or "sales_total" in f for f in fields),
           f"{sorted(fields)}. FR-PAY-013 forbids merging tips into sales revenue, and "
           f"this is the layer at which that merge would happen")

    # DERIVED, the way M4-A derived its thirteen balance functions. Any function in either
    # schema whose name or body suggests it reports revenue must not read a tip.
    # BY OID. Resolving a name to a regprocedure needs an argument list, and the catalog's
    # identity arguments carry parameter NAMES a type parser rejects; selecting prosrc
    # alongside the name does not work either, because a function body has newlines in it
    # and a row of psql output does not. The oid is one token, and the body is fetched one
    # at a time as a whole result.
    reporting = [(r[0], r[1]) for r in rows("""
        SELECT n.nspname || '.' || p.proname, p.oid::text
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname IN ('payments', 'cash')
           AND (p.proname ~ '(reconcil|revenue|sales|takings|report)'
             OR p.prosrc ~ 'sales_receipt')
         ORDER BY 1;""", dsn=ADMIN)]
    revenue_functions = [name for name, _oid in reporting]
    if len(revenue_functions) < 2:
        raise CommandUnreadable(
            f"only {len(revenue_functions)} reporting function(s) derived from the "
            f"catalog. A short list here would make the check below pass by having "
            f"nothing to examine, which is the vacuity this project has caught four times")
    record("the reporting functions are enumerated from the catalog, not from this file",
           len(revenue_functions) >= 2,
           f"{revenue_functions}. Matched by name AND by whether the body reads a sales "
           f"receipt, so a report a later slice adds is covered without anybody extending "
           f"anything")

    merged = []
    for name, oid in reporting:
        fetched = run(ADMIN, f"SELECT pg_get_functiondef({oid});")
        if not fetched.ok or not fetched.out.strip():
            raise ProbeFailed(f"definition of {name}", fetched.err)
        body = strip_comments(fetched.out)
        # A revenue column that reads a tip allocation would have to name the target.
        for match in re.finditer(r"(?is)(sales|revenue|takings|receipt)[a-z_]*"
                                 r"[^,;]{0,200}?target\s*=\s*'tip'", body):
            merged.append((name, match.group(0)[:80]))
    record("and no revenue-bearing expression reads the tip allocation",
           not merged,
           f"{merged or 'none'}. cash.shift_reconciliation() reports a tip column, which "
           f"it must — a cash tip is money in the same drawer — but no SALES figure adds "
           f"it in. A sales total inflated by tips is a tax return that is wrong and "
           f"staff who are owed money nobody can find")

    shift_view = call("GET", f"/s/v1/cash/shifts/{CONTEXT['shift']}/reconciliation", token)
    record("and the drawer's own picture keeps the two apart as well",
           "tip_allocation_minor" in shift_view and "sales_receipt_minor" in shift_view,
           f"sales {shift_view.get('sales_receipt_minor')}, tips "
           f"{shift_view.get('tip_allocation_minor')}, over/short "
           f"{shift_view.get('over_short_minor')}. Two pictures of one evening, side by "
           f"side, so they can DISAGREE — a single figure computed from one of them would "
           f"always reconcile")


# ===========================================================================
# 14. Cash survives an outage because nothing on its path can reach outside
# ===========================================================================

# The entry points FR-PAY-002, FR-PAY-003 and FR-PAY-014 say must keep working. Named
# because they ARE the requirement; everything reachable from them is derived.
OUTAGE_ENTRY_POINTS = (
    "payments.record_cash_payment",
    "payments.record_terminal_result",
    "payments.record_terminal_payment",
    "payments.raise_proof",
    "payments.verify_proof",
    "payments.record_proof_payment",
    "cash.post_cash_payment",
    "cash.record_count",
    "cash.transition_shift",
)

REACHABLE_FROM = """
WITH RECURSIVE ours AS (
    SELECT p.oid, n.nspname || '.' || p.proname AS name, p.prosrc, p.prolang
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
), reach AS (
    SELECT o.oid, o.name FROM ours o WHERE o.name = ANY (%(entries)s)
    UNION
    SELECT callee.oid, callee.name
      FROM reach r
      JOIN ours caller ON caller.oid = r.oid
      JOIN ours callee ON caller.prosrc ~ ('(^|[^a-zA-Z0-9_.])'
                                           || replace(callee.name, '.', '\\.')
                                           || '($|[^a-zA-Z0-9_])')
     WHERE callee.oid <> caller.oid
)
SELECT DISTINCT name FROM reach ORDER BY 1;"""


def reachable_from(entries: tuple[str, ...]) -> list[str]:
    array = "ARRAY[" + ", ".join(f"'{e}'" for e in entries) + "]::text[]"
    return [r[0] for r in rows(REACHABLE_FROM.replace("%(entries)s", array), dsn=ADMIN)]


def outbound_capable() -> list[str]:
    """Functions that CAN reach outside this database, defined by capability.

    Four capabilities, none of them a name pattern — a pattern is what the next author
    routes around by accident:

      1. a language other than sql or plpgsql, which can execute arbitrary code
      2. a reference to a foreign table, which is a remote read wearing a local name
      3. membership of an extension, since an extension is how network access arrives
      4. a write to payments.simulated_attempt, which IS the record of an adapter call —
         defined by its effect rather than by being named 'invoke' something
    """
    return [r[0] for r in rows("""
        SELECT DISTINCT n.nspname || '.' || p.proname
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
          JOIN pg_language l ON l.oid = p.prolang
         WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
           AND (
                l.lanname NOT IN ('sql', 'plpgsql')
             OR EXISTS (SELECT 1 FROM pg_foreign_table ft
                          JOIN pg_class fc ON fc.oid = ft.ftrelid
                          JOIN pg_namespace fn ON fn.oid = fc.relnamespace
                         WHERE p.prosrc ~ (fn.nspname || '\\.' || fc.relname))
             OR EXISTS (SELECT 1 FROM pg_depend d
                         WHERE d.objid = p.oid AND d.deptype = 'e')
             OR p.prosrc ~ 'INSERT INTO payments\\.simulated_attempt'
           )
         ORDER BY 1;""", dsn=ADMIN)]


def section_outage() -> None:
    print("\n--- 14. Cash and proof survive an outage, proved on the call graph "
          "(FR-PAY-002, FR-PAY-015) ---")

    reachable = reachable_from(OUTAGE_ENTRY_POINTS)
    if len(reachable) <= len(OUTAGE_ENTRY_POINTS):
        raise CommandUnreadable(
            f"the transitive closure of {len(OUTAGE_ENTRY_POINTS)} entry points came back "
            f"as {len(reachable)} function(s), which means the recursion found no calls "
            f"at all. Every check below would then be asserting over the entry points "
            f"alone — the emptiness this suite refuses to run on")

    record("the cash and proof paths are derived transitively from the catalog",
           len(reachable) > len(OUTAGE_ENTRY_POINTS),
           f"{len(OUTAGE_ENTRY_POINTS)} entry points reach {len(reachable)} functions. "
           f"Derived, not listed: a helper added at M4-C that makes an outbound call is "
           f"caught without anybody extending anything")

    capable = outbound_capable()
    record("and 'outbound' is defined by capability rather than by name",
           True,
           f"{len(capable)} function(s) in this database can reach outside it: "
           f"{capable or 'none'}. An untrusted language, a foreign table, an extension, "
           f"or a write to the table that records an adapter call. A name pattern would "
           f"be routed around by the next author by accident")

    crossing = sorted(set(reachable) & set(capable))
    record("no function reachable from cash, terminal recording or proof can reach outside",
           not crossing,
           f"{crossing or 'none'}. Staging one outage would prove the path survived THAT "
           f"outage; this proves it survives every outage, including the ones nobody "
           f"thought to stage. The behavioural half needs an outlet node to switch off "
           f"and is a partial closure against M5a, recorded separately from M3-B's "
           f"routing entry")

    # AND THE CHECK CAN FAIL. Plant an adapter call on the cash path and require it red.
    original = definition("cash.post_cash_payment(uuid, uuid, uuid, uuid)")
    poisoned = original.replace(
        "    RETURN v_id;",
        "    PERFORM payments.invoke_direct_provider(p_tenant_id, p_outlet_id,\n"
        "        'telebirr_direct', p.currency_code, 2, p.captured_by_user_id);\n"
        "    RETURN v_id;", 1)
    if poisoned == original:
        raise CommandUnreadable(
            "could not plant an adapter call in cash.post_cash_payment(); the anchor this "
            "check edits has moved, and a plant that changed nothing would make the "
            "assertion below pass for the wrong reason")

    planted = run(ADMIN, poisoned, tx=False)
    if not planted.ok:
        raise ProbeFailed("planting an outbound call on the cash path", planted.err)
    try:
        with_defect = sorted(set(reachable_from(OUTAGE_ENTRY_POINTS)) & set(capable))
        record("and the check goes red when an outbound call is planted on the cash path",
               with_defect,
               f"{with_defect}. Planted a payments.invoke_direct_provider() call inside "
               f"cash.post_cash_payment() and the transitive closure found it. Without "
               f"this the assertion above would be one over a set nobody had shown was "
               f"reachable")
    finally:
        reverted = run(ADMIN, original, tx=False)
        if not reverted.ok:
            raise ProbeFailed("reverting cash.post_cash_payment", reverted.err)

    after = sorted(set(reachable_from(OUTAGE_ENTRY_POINTS)) & set(capable))
    record("and green again once it is reverted",
           not after,
           f"{after or 'none'}. The revert is the original definition read out of the "
           f"catalog before the plant, so it restores what was there rather than what "
           f"this file thinks was there")


# ===========================================================================
# 15. Truthful health, and a peer that stops safely
# ===========================================================================

def section_health_and_versions() -> None:
    print("\n--- 15. Health and protocol version (FR-INT-011, FR-INT-013) ---")

    token = CONTEXT["manager_token"]
    answer = call("GET", "/s/v1/payments/adapters", token)
    adapters = {a["provider"]: a for a in answer.get("adapters", [])}
    record("health reports the payment adapters that exist",
           len(adapters) == 6 and answer.get("ready") is True,
           f"{ {k: (v['mode'], v['active'], v['healthy']) for k, v in adapters.items()} }; "
           f"ready={answer.get('ready')}")

    absent = [k for k in ("outletNode", "syncLag", "printer", "printerStatus")
              if k in json.dumps(answer)]
    record("and advertises nothing it does not have (M1-D's rule)",
           not absent,
           f"{absent or 'none'}. FR-INT-011 also names outlet-node connectivity, "
           f"synchronization lag and printer status; none exists at this gate, so none is "
           f"reported. A health endpoint that called a printer healthy because no printer "
           f"existed would be the most expensive kind of true statement — the partial "
           f"closure register names M4-C and M5a")

    # AN ADVERTISED ADAPTER THAT CANNOT WORK MAKES READINESS UNHEALTHY. The uncomfortable
    # answer, which is the test of whether health is truthful.
    switched = run(ADMIN, f"""
        UPDATE payments.payment_adapter SET active = true
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
           AND provider = 'cbe_birr_direct';""")
    if not switched.ok:
        raise ProbeFailed("advertising a simulated adapter", switched.err)
    try:
        unhealthy = call("GET", "/s/v1/payments/adapters", token)
        record("advertising a simulated adapter makes readiness unhealthy",
               unhealthy.get("status") == 503 and unhealthy.get("ready") is False,
               f"ready={unhealthy.get('ready')}, status {unhealthy.get('status')}. An "
               f"active simulated adapter is reachable and settles nothing, so a "
               f"deployment that advertised one would fail readiness rather than look "
               f"ready — which is what FR-INT-011's 'truthful' costs")
    finally:
        run(ADMIN, f"""
            UPDATE payments.payment_adapter SET active = false
             WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
               AND provider = 'cbe_birr_direct';""")

    protocols = {r[0]: (int(r[1]), int(r[2])) for r in rows("""
        SELECT protocol, current_version::text, minimum_supported_version::text
          FROM integration.protocol ORDER BY protocol;""")}
    record("the protocols this deployment speaks are declared with a version range",
           len(protocols) >= 3 and all(c >= m for c, m in protocols.values()),
           f"{protocols}. Only the protocols that EXIST: the outlet-node synchronization "
           f"protocol is M5a's and is absent rather than declared at version zero")

    agreed = int(scalar("SELECT integration.negotiate('adapter.payment', 1);"))
    record("a peer speaking a version in range is agreed with",
           agreed == 1, f"negotiated version {agreed}")

    for label, sql in (
        ("an unknown protocol", "SELECT integration.negotiate('adapter.unknown', 1);"),
        ("a version out of range", "SELECT integration.negotiate('adapter.payment', 99);"),
        ("no version at all", "SELECT integration.negotiate('adapter.payment', NULL);"),
    ):
        refused = run(APP, sql, **CTX)
        record(f"and {label} stops safely rather than being accepted",
               refused.failed_with("UNKNOWN_SCHEMA_ACCEPTED"),
               refused.why() or f"{label} was accepted. From the far side these are the "
                                f"same mistake, which is why they carry one signature")


# ===========================================================================
# 16. Governance: the register, the catalog rules, the closures
# ===========================================================================

def section_governance() -> None:
    print("\n--- 16. Governance ---")

    entries = partial_closures.load()
    failures = partial_closures.check(entries)
    closed_here = sorted({e["requirement"] for e in entries
                          if e.get("closed_at") == "M4-B"})
    record("the register is consistent, and the entries that came due are closed",
           not failures,
           f"{len(entries)} entries, {len(closed_here)} requirement(s) closed at M4-B: "
           f"{closed_here}. Failures: {failures or 'none'}")

    # THE NEW RULE, and its stated boundary. The user's condition was that a reader should
    # meet the boundary rather than infer it, so it is asserted here as well as written in
    # the rule's own docstring.
    completers = {e["completed_by"] for e in entries if e.get("completed_by")}
    record("every named completer is checked for being complete itself",
           len(completers) >= 15,
           f"{len(completers)} distinct completers are named across the register, and "
           f"PARTIAL_CLOSURE_COMPLETER_INCOMPLETE checks each closed entry against the "
           f"open entries of the requirement it rests on. The set is DERIVED from "
           f"completed_by, so a completer a later gate introduces is covered without "
           f"anybody extending anything")
    record("and the rule states what it does not yet cover",
           "not every requirement whose gate" in
           (partial_closures.__doc__ or "").replace("\n", " ").replace("  ", " ")
           or "NAMED COMPLETERS, not every requirement" in (partial_closures.__doc__ or ""),
           "the docstring names the boundary: it checks named completers, not every "
           "landed requirement. The larger audit is a partial closure against M4-C, so it "
           "comes due where a gate is closing rather than where payment capture is being "
           "written")

    # NOTHING DURABLE HOLDS A FOREIGN KEY INTO A PROJECTION. M3-D's rule, asserted from
    # the catalog for the two schemas this slice added.
    projections = {"payments.payment", "payments.allocation", "payments.reversal",
                   "billing.bill", "billing.bill_component", "ordering.customer_order"}
    offenders = [r[0] for r in rows("""
        SELECT format('%s.%s -> %s.%s',
                      sn.nspname, sc.relname, tn.nspname, tc.relname)
          FROM pg_constraint k
          JOIN pg_class sc ON sc.oid = k.conrelid
          JOIN pg_namespace sn ON sn.oid = sc.relnamespace
          JOIN pg_class tc ON tc.oid = k.confrelid
          JOIN pg_namespace tn ON tn.oid = tc.relnamespace
         WHERE k.contype = 'f' AND sn.nspname IN ('payments', 'cash')
         ORDER BY 1;""", dsn=ADMIN)]
    into_projections = [o for o in offenders
                        if o.split(" -> ")[1] in projections
                        and o.split(" -> ")[0] not in projections]
    record("nothing durable holds a foreign key into a projection (M3-D's rule)",
           not into_projections,
           f"{into_projections or 'none'} out of {len(offenders)} foreign key(s) from the "
           f"two new schemas. A rebuild deletes projections wholesale before replaying, "
           f"and 0019 lost three of these before the rule was written down")

    # ROW LEVEL SECURITY, enumerated from the catalog rather than from a list.
    unprotected = [r[0] for r in rows("""
        SELECT n.nspname || '.' || c.relname
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname IN ('payments', 'cash') AND c.relkind = 'r'
           AND EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = c.oid AND a.attname = 'tenant_id'
                          AND a.attnum > 0 AND NOT a.attisdropped)
           AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)
         ORDER BY 1;""", dsn=ADMIN)]
    record("every tenant table in the new schemas has row level security ENABLED and FORCED",
           not unprotected,
           f"{unprotected or 'none'}. FORCE is what makes the policy apply to the table's "
           f"own owner, and every SECURITY DEFINER function in these schemas runs as that "
           f"owner")

    floats = [r[0] for r in rows("""
        SELECT n.nspname || '.' || c.relname || '.' || a.attname
          FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
          JOIN pg_type t ON t.oid = a.atttypid
         WHERE n.nspname IN ('payments', 'cash') AND c.relkind = 'r'
           AND a.attnum > 0 AND NOT a.attisdropped
           AND t.typname IN ('float4', 'float8', 'money');""", dsn=ADMIN)]
    record("no money in the two new schemas is binary floating point",
           not floats,
           f"{floats or 'none'}. This is the gate that takes money; a float here would be "
           f"a rounding error somebody is charged")

    fenced_pattern, term_count = fenced_identifier_pattern()
    intruders = [r[0] for r in rows(f"""
        SELECT n.nspname || '.' || c.relname
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname IN ('payments', 'cash') AND c.relkind IN ('r', 'v')
           AND c.relname ~* '{fenced_pattern}'
        UNION ALL
        SELECT n.nspname || '.' || c.relname || '.' || a.attname
          FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname IN ('payments', 'cash') AND c.relkind = 'r'
           AND a.attnum > 0 AND NOT a.attisdropped
           AND a.attname ~* '{fenced_pattern}'
         ORDER BY 1;""", dsn=ADMIN)]
    record("no fenced term reaches the schema these slices added",
           not intruders,
           f"{intruders or 'none'}, against {term_count} authoritative terms loaded from "
           f"the package. FR-CSH-003 and FR-CSH-008 both ask for a word this build may "
           f"not use — it is one of the 63, reserved for a fenced domain — so the FIGURE "
           f"is here in full as over_short_minor and the word is not. That is a tension "
           f"inside the package rather than a choice, and the M4-B report names it")

    signatures = registry.signatures_for("M4")
    colliding = [s for s in signatures
                 for _d, _t, pattern in source_patterns() if pattern.search(s)]
    record("and no control signature collides with a fenced term",
           not colliding,
           f"{colliding or 'none'} out of {len(signatures)} M4 signature(s), checked "
           f"programmatically against every term rather than by reading them")


# ===========================================================================
# 17. Negative controls
# ===========================================================================

def a_fresh_drawer(float_minor: int = 1000) -> str:
    """A live shift on the till, having first moved any existing one on.

    The partial unique index permits ONE live drawer per terminal, which is right — two
    shifts on one till is two people counting the same notes. The control gates below each
    open a drawer and several deliberately leave theirs reopened, so without this the
    second gate collides with the first's leftovers and reports a unique violation as its
    own defect. Submission is a legal edge that needs no verifier and erases nothing.
    """
    moved = run(APP, f"""
        SELECT cash.transition_shift('{fx.TENANT}', s.id, 'submitted',
                                     '{fx.USER_CASHIER}')
          FROM cash.shift s
         WHERE s.tenant_id = '{fx.TENANT}'
           AND s.terminal_device_id = '{fx.TERMINAL_DEVICE}'
           AND s.state IN ('open', 'reopened');""", tx=True, **CTX)
    if not moved.ok:
        raise ProbeFailed("retiring a live drawer", moved.err)
    return scalar(f"""
        SELECT cash.open_shift('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{fx.TERMINAL_DEVICE}', '{fx.USER_CASHIER}', 'ETB', {float_minor});""")


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


def section_controls() -> None:
    print("\n--- 17. Negative controls: each proved RED with a real defect, then GREEN ---")

    token = CONTEXT["cashier_token"]
    manager_token = CONTEXT["manager_token"]

    # ---------------------------------------------------------------- NC-M4-003
    # A simulated result recorded as money received. Planted in the ONE PLACE the three
    # locks could still be defeated from inside: the earned check itself. The mode CHECK
    # and the two types are schema and cannot be edited at runtime; the constraint trigger
    # is a function, and a function is what somebody would loosen. Two locks can hide each
    # other — this plants the defect that survives the other two.
    def simulated_gate() -> tuple[bool, str, str]:
        bill = a_bill_at(fx.CASH_TABLE)
        # ACTIVATED FIRST, and the intent permits it explicitly. An intent takes its
        # permitted methods from the ACTIVE adapters at the moment it is created, so an
        # intent made before the simulator was switched on refuses the capture with
        # PAYMENT_METHOD_NOT_PERMITTED — a real refusal, from a different rule, that would
        # have let this control report red without the lock under test ever running.
        run(ADMIN, f"""
            UPDATE payments.payment_adapter SET active = true
             WHERE tenant_id = '{fx.TENANT}' AND provider = 'telebirr_direct';""")
        intent = scalar(f"""
            SELECT payments.create_intent('{fx.TENANT}', '{fx.OUTLET_H1}',
                '{bill["bill"]}', '{idem("nc003-" + a_uuid())}',
                {bill["total"]}, '{fx.USER}', 0, NULL, NULL,
                ARRAY['telebirr_direct']::payments.provider[]);""")
        attempt = run(APP, f"""
            SELECT payments.capture('{fx.TENANT}', '{fx.OUTLET_H1}', '{intent}',
                'telebirr_direct', {bill["total"]}, '{fx.USER}');""", tx=True, **CTX)
        run(ADMIN, f"""
            UPDATE payments.payment_adapter SET active = false
             WHERE tenant_id = '{fx.TENANT}' AND provider = 'telebirr_direct';""")
        # THE GATE DECIDES ON THE CENSUS, not on the exception. M4-A's NC-M4A-006 named a
        # cause it had not verified; this asks the bill whether anything reached it.
        owed = int(scalar(
            f"SELECT billing.outstanding_balance('{fx.TENANT}', '{bill['bill']}');"))
        allocated = count(ADMIN, f"""
            SELECT count(*) FROM payments.allocation WHERE bill_id = '{bill["bill"]}';""")
        if allocated > 0 or owed < bill["total"]:
            return (False, "UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM",
                    f"{allocated} allocation(s) reached the bill and {owed} of "
                    f"{bill['total']} remains owed after a SIMULATED capture")
        return (True, "", f"nothing allocated; {owed} of {bill['total']} still owed. "
                          f"The refusal said: {signature_of(attempt.err or '') or 'none'}")

    def red_simulated():
        original = definition("payments.assert_allocation_is_earned()")
        CONTEXT["nc003_original"] = original
        loosened = original.replace(
            "IF p.adapter_mode <> 'live' THEN", "IF false THEN", 1)
        if loosened == original:
            raise CommandUnreadable(
                "could not loosen payments.assert_allocation_is_earned(); the anchor has "
                "moved and a plant that changed nothing would pass for the wrong reason")
        replace_function(loosened)
        ok, sig, detail = simulated_gate()
        return (not ok and sig == "UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM",
                f"{sig}: {detail}")

    def green_simulated():
        replace_function(CONTEXT["nc003_original"])
        ok, _sig, detail = simulated_gate()
        return (ok, detail)

    control("NC-M4-003  a simulated result recorded as money received",
            red_simulated, green_simulated)

    # ---------------------------------------------------------------- NC-M4-004
    # A cashier approving their own refund. Planted on the LINK between the override and
    # the reversal, because pos.override_approval's own CHECK is M3-D's and is proved
    # there; what M4-B adds is that the approval must belong to THIS refund by THIS
    # person, and that is the half a payment slice can get wrong.
    def maker_checker_gate() -> tuple[bool, str, str]:
        bill = a_bill_at(fx.CASH_TABLE)
        intent = an_intent(bill["bill"], bill["total"], f"nc004-{a_uuid()}")
        payment = scalar(f"""
            SELECT payments.record_cash_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
                '{intent}', {bill["total"]}, '{fx.USER_CASHIER}');""")
        allocation = scalar(f"""
            SELECT id FROM payments.allocation WHERE payment_id = '{payment}'
               AND target = 'bill_balance';""")
        reason = fx.reason_code("M4B_GUEST_REFUNDED")
        # An approval granted to somebody ELSE, pointed at this refund by the cashier.
        borrowed = an_override("payment.refund", "payment_allocation", allocation, reason,
                               "an approval granted to a different actor")
        # THROUGH THE DELIVERED WRITER. A direct INSERT is refused by the grant and by the
        # projection trigger before the maker-checker rule is ever consulted — two other
        # locks answering for the one under test, which would make this control report a
        # refusal it had not caused. The override here belongs to the CASHIER; the person
        # making the reversal is the finance manager, so the approval is not theirs.
        stolen = run(APP, f"""
            SELECT payments.reverse_allocation('{fx.TENANT}', '{fx.OUTLET_H1}',
                '{allocation}', 'refund',
                {fx.REFUND_APPROVAL_THRESHOLD_MINOR + 1}, '{reason}',
                'refunding on somebody else''s approval',
                '{fx.USER_FINANCE_MANAGER}', '{borrowed}');""", tx=True, **CTX)
        reversed_rows = count(ADMIN, f"""
            SELECT count(*) FROM payments.reversal WHERE allocation_id = '{allocation}';""")
        if reversed_rows > 0:
            return (False, "SELF_APPROVAL_ACCEPTED",
                    f"{reversed_rows} reversal(s) landed against allocation {allocation} "
                    f"on an approval granted to somebody else")
        return (True, "", f"refused: {signature_of(stolen.err or '') or 'no signature'}; "
                          f"{reversed_rows} reversal(s) exist")

    def red_maker_checker():
        original = definition("payments.assert_reversal_is_authorized()")
        CONTEXT["nc004_original"] = original
        loosened = original.replace(
            "IF v_override.actor_user_id <> NEW.actor_user_id THEN", "IF false THEN", 1)
        if loosened == original:
            raise CommandUnreadable(
                "could not loosen payments.assert_reversal_is_authorized(); the anchor "
                "has moved")
        replace_function(loosened)
        ok, sig, detail = maker_checker_gate()
        return (not ok and sig == "SELF_APPROVAL_ACCEPTED", f"{sig}: {detail}")

    def green_maker_checker():
        replace_function(CONTEXT["nc004_original"])
        ok, _sig, detail = maker_checker_gate()
        return (ok, detail)

    control("NC-M4-004  an approval that does not belong to the person using it",
            red_maker_checker, green_maker_checker)

    # ---------------------------------------------------------------- NC-M4-006
    # A reopened drawer reported as closed. Planted on the transition function, which is
    # where somebody in a hurry would add the missing edge.
    def reopened_gate() -> tuple[bool, str, str]:
        shift = a_fresh_drawer()
        reason = fx.reason_code("M4B_DRAWER_RECOUNTED")
        for state in ("submitted",):
            run(APP, f"""
                SELECT cash.transition_shift('{fx.TENANT}', '{shift}', '{state}',
                    '{fx.USER_CASHIER}');""", tx=True, **CTX)
        run(APP, f"""
            SELECT set_config('app.session_id', '{CONTEXT["manager_session"]}', false);
            SELECT cash.transition_shift('{fx.TENANT}', '{shift}', 'verified',
                '{fx.USER_FINANCE_MANAGER}');""", tx=True, **CTX)
        run(APP, f"""
            SELECT cash.transition_shift('{fx.TENANT}', '{shift}', 'finalized',
                '{fx.USER_FINANCE_MANAGER}');""", tx=True, **CTX)
        override = an_override("cash.shift.verify", "cash_shift", shift, reason,
                               "reopened to prove it cannot be closed again")
        run(APP, f"""
            SELECT cash.transition_shift('{fx.TENANT}', '{shift}', 'reopened',
                '{fx.USER_FINANCE_MANAGER}', '{override}', '{reason}', 'recount needed');""",
            tx=True, **CTX)

        closed = run(APP, f"""
            SELECT cash.transition_shift('{fx.TENANT}', '{shift}', 'finalized',
                '{fx.USER_FINANCE_MANAGER}');""", tx=True, **CTX)
        state = scalar(f"SELECT state::text FROM cash.shift WHERE id = '{shift}';")
        listed = count(APP, f"""
            SELECT count(*) FROM cash.exception_report('{fx.TENANT}', '{fx.OUTLET_H1}')
             WHERE shift_id = '{shift}' AND kind = 'reopened_not_resolved';""", **CTX)
        if state == "finalized" or listed == 0:
            return (False, "REOPENED_SHIFT_NOT_RESOLVED",
                    f"the reopened drawer is now {state!r} and appears {listed} time(s) "
                    f"in the exception report. A hole closed by declaring it shut")
        return (True, "", f"still {state!r}; refused with "
                          f"{signature_of(closed.err or '') or 'no signature'}; listed "
                          f"{listed} time(s) as unresolved")

    def red_reopened():
        original = definition(
            "cash.transition_shift(uuid, uuid, cash.shift_state, uuid, uuid, uuid, text)")
        CONTEXT["nc006_original"] = original
        loosened = original.replace(
            "     OR (s.state = 'finalized' AND p_to_state = 'reopened')",
            "     OR (s.state = 'finalized' AND p_to_state = 'reopened')\n"
            "     OR (s.state = 'reopened'  AND p_to_state = 'finalized')", 1)
        if loosened == original:
            raise CommandUnreadable(
                "could not add the reopened→finalized edge; the anchor has moved")
        replace_function(loosened)
        # TWO LOCKS CAN HIDE EACH OTHER, so the plant defeats both. The missing edge is
        # one; cash.shift's own CHECK that a reopened drawer never returns to 'finalized'
        # is the other, and with only the edge added the CHECK refused — truthfully, and
        # for a reason that had nothing to do with the state machine this control is
        # about. A control that stopped there would have proved the constraint and left
        # the transition function untested.
        dropped = run(ADMIN, """
            ALTER TABLE cash.shift DROP CONSTRAINT shift_reopened_never_refinalizes;""")
        if not dropped.ok:
            raise ProbeFailed("dropping the re-finalization constraint", dropped.err)
        ok, sig, detail = reopened_gate()
        return (not ok and sig == "REOPENED_SHIFT_NOT_RESOLVED", f"{sig}: {detail}")

    def green_reopened():
        replace_function(CONTEXT["nc006_original"])
        restored = run(ADMIN, """
            UPDATE cash.shift SET state = 'reopened', finalized_at = NULL
             WHERE reopened_at IS NOT NULL AND state = 'finalized';
            ALTER TABLE cash.shift ADD CONSTRAINT shift_reopened_never_refinalizes
                CHECK (reopened_at IS NULL OR state <> 'finalized');""")
        if not restored.ok:
            raise ProbeFailed("restoring the re-finalization constraint", restored.err)
        ok, _sig, detail = reopened_gate()
        return (ok, detail)

    control("NC-M4-006  a reopened cash shift closed without being resolved",
            red_reopened, green_reopened)

    # ---------------------------------------------------------------- NC-M4B-001
    # Raw card data reaching storage. Planted on the trigger function's own predicate,
    # because the CHECK on masked_tail and the JSON schema in the route are narrower locks
    # that would each still catch a PAN in THEIR field — and the defect that matters is
    # one in a field nobody thought about.
    def card_gate() -> tuple[bool, str, str]:
        planted_pan = "5555444433332222"
        attempt = run(APP, f"""
            INSERT INTO payments.terminal_result
                (tenant_id, outlet_id, terminal_reference, scheme, currency_code,
                 amount_minor, outcome, recorded_by_user_id)
            VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{planted_pan}', 'visa', 'ETB',
                    1000, 'approved', '{fx.USER}');""", tx=True, **CTX)
        stored = count(ADMIN, f"""
            SELECT count(*) FROM payments.terminal_result
             WHERE terminal_reference = '{planted_pan}';""")
        if stored > 0:
            return (False, "CARD_DATA_RETAINED",
                    f"{stored} row(s) hold a sixteen-digit account number in a field "
                    f"that takes free text")
        return (True, "", f"refused with "
                          f"{signature_of(attempt.err or '') or 'no signature'}; "
                          f"{stored} row(s) stored")

    def red_card():
        original = definition("payments.looks_like_card_data(text)")
        CONTEXT["nc4b001_original"] = original
        loosened = re.sub(r"SELECT p_value IS NOT NULL", "SELECT false AND p_value IS NOT NULL",
                          original, count=1)
        if loosened == original:
            raise CommandUnreadable(
                "could not loosen payments.looks_like_card_data(); the anchor has moved")
        replace_function(loosened)
        ok, sig, detail = card_gate()
        return (not ok and sig == "CARD_DATA_RETAINED", f"{sig}: {detail}")

    def green_card():
        replace_function(CONTEXT["nc4b001_original"])
        run(ADMIN, "DELETE FROM payments.terminal_result "
                   "WHERE terminal_reference = '5555444433332222';")
        ok, _sig, detail = card_gate()
        return (ok, detail)

    control("NC-M4B-001  raw card data reaching storage", red_card, green_card)

    # ---------------------------------------------------------------- NC-M4B-002
    # A payment allocation recomputed on read. Planted in the read model, which is exactly
    # where it would happen: somebody "fixing" a stale-looking figure by deriving it from
    # today's bill. The gate reissues the bill and requires the two answers to agree.
    def recompute_gate() -> tuple[bool, str, str]:
        # A PARTIAL payment, so the stored allocation and the bill total are different
        # numbers. Against a fully paid bill the two agree, and a read model that derived
        # its figure from the bill would return the right answer for the wrong reason —
        # the control would pass with the defect in place.
        payment = CONTEXT.setdefault("nc4b002_payment", None)
        if payment is None:
            bill = a_bill_at(fx.PAY_TABLE)
            part = bill["total"] // 3
            intent = an_intent(bill["bill"], part, f"nc4b002-{a_uuid()}")
            payment = scalar(f"""
                SELECT payments.record_cash_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
                    '{intent}', {part}, '{fx.USER}');""")
            CONTEXT["nc4b002_payment"] = payment
        stored = int(scalar(f"""
            SELECT amount_minor FROM payments.allocation
             WHERE payment_id = '{payment}' AND target = 'bill_balance';"""))
        served = int(scalar(f"""
            SELECT amount_minor FROM payments.allocation_view('{fx.TENANT}', '{payment}')
             WHERE target = 'bill_balance';"""))
        if stored != served:
            return (False, "ALLOCATION_RECOMPUTED_ON_READ",
                    f"the column holds {stored} and the read model answers {served}. A "
                    f"figure recalculated on read disagrees with what was recorded "
                    f"exactly when somebody is disputing a bill")
        return (True, "", f"stored {stored}, served {served}; the read model returns the "
                          f"column")

    def red_recompute():
        original = definition("payments.allocation_view(uuid, uuid)")
        CONTEXT["nc4b002_original"] = original
        loosened = original.replace(
            "           a.amount_minor::bigint,",
            "           coalesce((SELECT b.bill_total_minor FROM billing.bill b\n"
            "                      WHERE b.tenant_id = a.tenant_id AND b.id = a.bill_id),\n"
            "                    a.amount_minor)::bigint,", 1)
        if loosened == original:
            raise CommandUnreadable(
                "could not make payments.allocation_view() derive its figure; the anchor "
                "has moved")
        replace_function(loosened)
        ok, sig, detail = recompute_gate()
        return (not ok and sig == "ALLOCATION_RECOMPUTED_ON_READ", f"{sig}: {detail}")

    def green_recompute():
        replace_function(CONTEXT["nc4b002_original"])
        ok, _sig, detail = recompute_gate()
        return (ok, detail)

    control("NC-M4B-002  a payment allocation recomputed on read",
            red_recompute, green_recompute)

    # ---------------------------------------------------------------- NC-M4B-003
    # A tip merged into sales revenue. Planted in the drawer's reconciliation, because a
    # cash tip is money in the same till and adding it to takings is the mistake that
    # looks like tidiness.
    def revenue_gate() -> tuple[bool, str, str]:
        # A DRAWER WITH A TIP IN IT. The shift from section 11 took a cash payment that
        # carried no tip, so folding tips into sales would have changed nothing and the
        # red leg would have reported green. Built once and reused across both legs.
        shift = CONTEXT.get("nc4b003_shift")
        if shift is None:
            shift = a_fresh_drawer(5000)
            bill = a_bill_at(fx.CASH_TABLE)
            made = run(APP, f"""
                SELECT billing.split_equally('{fx.TENANT}', '{bill["bill"]}', 1);""",
                tx=True, **CTX)
            if not made.ok:
                raise ProbeFailed("split_equally", made.err)
            share = scalar(f"""
                SELECT id FROM billing.bill_share WHERE bill_id = '{bill["bill"]}'
                 LIMIT 1;""")
            tip = scalar(f"""
                INSERT INTO billing.tip (tenant_id, outlet_id, bill_share_id,
                                         currency_code, amount_minor)
                VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{share}', 'ETB', 2500)
                RETURNING id;""")
            intent = an_intent(bill["bill"], bill["total"], f"nc4b003-{a_uuid()}",
                               tip=2500, tip_id=tip, share=share)
            scalar(f"""
                SELECT payments.record_cash_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
                    '{intent}', {bill["total"] + 2500}, '{fx.USER_CASHIER}');""")
            CONTEXT["nc4b003_shift"] = shift
        row = rows(f"""
            SELECT sales_receipt_minor::text, tip_allocation_minor::text
              FROM cash.shift_reconciliation('{fx.TENANT}', '{shift}');""")
        if not row:
            raise CommandUnreadable(
                f"the drawer reconciliation returned nothing for shift {shift}, so this "
                f"control would compare two absent figures")
        sales, tips = int(row[0][0]), int(row[0][1])
        movements = int(scalar(f"""
            SELECT coalesce(sum(amount_minor), 0) FROM cash.movement
             WHERE shift_id = '{shift}' AND kind = 'sales_receipt';"""))
        if sales != movements:
            return (False, "TIP_MERGED_INTO_REVENUE",
                    f"the sales figure is {sales} and the sales-receipt movements add to "
                    f"{movements}; the difference is the {tips} of tips that were folded "
                    f"in. A sales total inflated by tips is a tax return that is wrong")
        return (True, "", f"sales {sales} equals the sales-receipt movements {movements}; "
                          f"tips {tips} reported separately and added to nothing")

    def red_revenue():
        original = definition("cash.shift_reconciliation(uuid, uuid)")
        CONTEXT["nc4b003_original"] = original
        loosened = original.replace(
            "           coalesce(sum(m.amount_minor) FILTER (WHERE m.kind = 'sales_receipt'), 0)::bigint,",
            "           (coalesce(sum(m.amount_minor) FILTER (WHERE m.kind = 'sales_receipt'), 0)\n"
            "            + coalesce((SELECT sum(a.amount_minor)\n"
            "                          FROM cash.movement m3\n"
            "                          JOIN payments.allocation a\n"
            "                            ON a.tenant_id = m3.tenant_id\n"
            "                           AND a.payment_id = m3.payment_id\n"
            "                         WHERE m3.tenant_id = s.tenant_id\n"
            "                           AND m3.shift_id = s.id\n"
            "                           AND a.target = 'tip'), 0))::bigint,", 1)
        if loosened == original:
            raise CommandUnreadable(
                "could not fold tips into the sales figure; the anchor has moved")
        replace_function(loosened)
        ok, sig, detail = revenue_gate()
        return (not ok and sig == "TIP_MERGED_INTO_REVENUE", f"{sig}: {detail}")

    def green_revenue():
        replace_function(CONTEXT["nc4b003_original"])
        ok, _sig, detail = revenue_gate()
        return (ok, detail)

    control("NC-M4B-003  a tip merged into sales revenue", red_revenue, green_revenue)

    # ---------------------------------------------------------------- NC-M4B-004
    # A retry that produces a second payment. Planted on the capture writer's own
    # short-circuit, because the intent's unique key protects the INTENT and this protects
    # the payment — two different retries, and a control that only proved the first would
    # leave the expensive one untested.
    def duplicate_gate() -> tuple[bool, str, str]:
        bill = a_bill_at(fx.CASH_TABLE)
        intent = an_intent(bill["bill"], bill["total"], f"nc4b004-{a_uuid()}")
        first = run(APP, f"""
            SELECT payments.record_cash_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
                '{intent}', {bill["total"]}, '{fx.USER_CASHIER}');""", tx=True, **CTX)
        second = run(APP, f"""
            SELECT payments.record_cash_payment('{fx.TENANT}', '{fx.OUTLET_H1}',
                '{intent}', {bill["total"]}, '{fx.USER_CASHIER}');""", tx=True, **CTX)
        made = count(ADMIN, f"""
            SELECT count(*) FROM payments.payment WHERE intent_id = '{intent}';""")
        taken = int(scalar(f"""
            SELECT coalesce(sum(amount_minor), 0) FROM payments.allocation
             WHERE bill_id = '{bill["bill"]}' AND target = 'bill_balance';"""))
        if made != 1 or taken != bill["total"]:
            return (False, "DUPLICATE_PAYMENT_ON_RETRY",
                    f"{made} payment(s) for one intent and {taken} allocated against a "
                    f"bill of {bill['total']}. The guest was charged twice")
        return (True, "",
                f"{made} payment; {taken} of {bill['total']} allocated. First returned "
                f"{(first.scalar or '').strip()[:8]}, retry returned "
                f"{(second.scalar or '').strip()[:8]}")

    def red_duplicate():
        original = definition(
            "payments.capture(uuid, uuid, uuid, payments.provider, money.amount_minor, "
            "uuid, uuid, uuid)")
        CONTEXT["nc4b004_original"] = original
        loosened = original.replace("    IF FOUND THEN\n        RETURN v_payment;\n    END IF;",
                                    "    IF false THEN\n        RETURN v_payment;\n    END IF;", 1)
        if loosened == original:
            raise CommandUnreadable(
                "could not remove the capture short-circuit; the anchor has moved")
        replace_function(loosened)
        ok, sig, detail = duplicate_gate()
        return (not ok and sig == "DUPLICATE_PAYMENT_ON_RETRY", f"{sig}: {detail}")

    def green_duplicate():
        replace_function(CONTEXT["nc4b004_original"])
        ok, _sig, detail = duplicate_gate()
        return (ok, detail)

    control("NC-M4B-004  a retry that produces a second payment",
            red_duplicate, green_duplicate)

    # ---------------------------------------------------------------- NC-M4B-005
    # A finalized drawer that accepts a movement. Planted on the guard trigger, which is
    # the only lock: there is no grant that stops a movement, deliberately, because a
    # cashier must be able to post one all evening.
    def finalized_gate() -> tuple[bool, str, str]:
        shift = a_fresh_drawer()
        run(APP, f"""
            SELECT cash.transition_shift('{fx.TENANT}', '{shift}', 'submitted',
                '{fx.USER_CASHIER}');""", tx=True, **CTX)
        run(APP, f"""
            SELECT set_config('app.session_id', '{CONTEXT["manager_session"]}', false);
            SELECT cash.transition_shift('{fx.TENANT}', '{shift}', 'verified',
                '{fx.USER_FINANCE_MANAGER}');""", tx=True, **CTX)
        run(APP, f"""
            SELECT cash.transition_shift('{fx.TENANT}', '{shift}', 'finalized',
                '{fx.USER_FINANCE_MANAGER}');""", tx=True, **CTX)

        late = run(APP, f"""
            INSERT INTO cash.movement
                (tenant_id, outlet_id, shift_id, kind, currency_code, amount_minor,
                 actor_user_id)
            VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{shift}', 'payout', 'ETB', -500,
                    '{fx.USER_CASHIER}');""", tx=True, **CTX)
        landed = count(ADMIN, f"""
            SELECT count(*) FROM cash.movement WHERE shift_id = '{shift}';""")
        if landed > 0:
            return (False, "FINALIZED_SHIFT_MUTATED",
                    f"{landed} movement(s) landed in a drawer somebody had already "
                    f"signed for, changing a total retrospectively")
        return (True, "", f"refused with "
                          f"{signature_of(late.err or '') or 'no signature'}; "
                          f"{landed} movement(s) in the finalized drawer")

    def red_finalized():
        original = definition("cash.assert_shift_accepts_movements()")
        CONTEXT["nc4b005_original"] = original
        loosened = original.replace(
            "IF v_state NOT IN ('open', 'reopened') THEN", "IF false THEN", 1)
        if loosened == original:
            raise CommandUnreadable(
                "could not loosen cash.assert_shift_accepts_movements(); anchor moved")
        replace_function(loosened)
        ok, sig, detail = finalized_gate()
        return (not ok and sig == "FINALIZED_SHIFT_MUTATED", f"{sig}: {detail}")

    def green_finalized():
        replace_function(CONTEXT["nc4b005_original"])
        ok, _sig, detail = finalized_gate()
        return (ok, detail)

    control("NC-M4B-005  a finalized cash shift that accepts a movement",
            red_finalized, green_finalized)

    # ---------------------------------------------------------------- NC-M4B-006
    # A proof confirmation with no attributor. Planted on the CHECK constraint, because
    # that is the lock — the route cannot express an unattributed verification at all, and
    # a control that only proved the route would be proving a schema it never touched.
    def attribution_gate() -> tuple[bool, str, str]:
        proof = scalar(f"""
            SELECT payments.raise_proof('{fx.TENANT}', '{fx.OUTLET_H1}',
                'cbe_birr_proof', 'ETB', 9900, 'CBE-{a_uuid()}');""")
        forced = run(ADMIN, f"""
            UPDATE payments.proof_confirmation
               SET state = 'verified', what_the_verifier_saw = 'looked fine'
             WHERE id = '{proof}';""", tx=True)
        state = scalar(f"""
            SELECT state::text FROM payments.proof_confirmation WHERE id = '{proof}';""")
        if state == "verified":
            return (False, "VERIFICATION_WITHOUT_ATTRIBUTOR",
                    f"proof {proof} is verified and names nobody. An attestation is the "
                    f"audited artifact; one with no attributor is a tick-box")
        return (True, "", f"still {state!r}; refused with "
                          f"{signature_of(forced.err or '') or 'a CHECK constraint'}")

    def red_attribution():
        dropped = run(ADMIN, """
            ALTER TABLE payments.proof_confirmation
                DROP CONSTRAINT proof_verified_is_attributed;""")
        if not dropped.ok:
            raise ProbeFailed("dropping the attribution constraint", dropped.err)
        ok, sig, detail = attribution_gate()
        return (not ok and sig == "VERIFICATION_WITHOUT_ATTRIBUTOR", f"{sig}: {detail}")

    def green_attribution():
        restored = run(ADMIN, """
            DELETE FROM payments.proof_confirmation
             WHERE state = 'verified' AND verified_by_user_id IS NULL;
            ALTER TABLE payments.proof_confirmation
                ADD CONSTRAINT proof_verified_is_attributed CHECK (
                    state <> 'verified' OR (
                        verified_by_user_id IS NOT NULL
                        AND verified_by_session_id IS NOT NULL
                        AND verified_at IS NOT NULL
                        AND btrim(coalesce(what_the_verifier_saw, '')) <> ''));""")
        if not restored.ok:
            raise ProbeFailed("restoring the attribution constraint", restored.err)
        ok, _sig, detail = attribution_gate()
        return (ok, detail)

    control("NC-M4B-006  a proof confirmation accepted with no attributor",
            red_attribution, green_attribution)

    # ---------------------------------------------------------------- NC-M4B-007
    # An incompatible peer accepted. Planted on the range comparison, which is the shape
    # of the real defect: somebody widening a bound to make a peer work today.
    def version_gate() -> tuple[bool, str, str]:
        loose = run(APP, "SELECT integration.negotiate('adapter.payment', 99);", **CTX)
        unknown = run(APP, "SELECT integration.negotiate('adapter.nonexistent', 1);",
                      **CTX)
        accepted = [label for label, res in (("a version out of range", loose),
                                             ("an unknown protocol", unknown)) if res.ok]
        if accepted:
            return (False, "UNKNOWN_SCHEMA_ACCEPTED",
                    f"{accepted} was agreed with. A peer whose shape is unknown is one "
                    f"whose messages cannot be checked, and accepting them moves the "
                    f"failure somewhere it looks like a data problem")
        return (True, "", f"both refused: "
                          f"{signature_of(loose.err or '')}, "
                          f"{signature_of(unknown.err or '')}")

    def red_version():
        original = definition("integration.negotiate(text, integer)")
        CONTEXT["nc4b007_original"] = original
        loosened = original.replace(
            "    IF p_peer_version < p.minimum_supported_version\n"
            "       OR p_peer_version > p.current_version THEN", "    IF false THEN", 1)
        loosened = loosened.replace("    IF NOT FOUND THEN", "    IF false THEN", 1)
        if loosened == original:
            raise CommandUnreadable(
                "could not widen integration.negotiate(); the anchor has moved")
        replace_function(loosened)
        ok, sig, detail = version_gate()
        return (not ok and sig == "UNKNOWN_SCHEMA_ACCEPTED", f"{sig}: {detail}")

    def green_version():
        replace_function(CONTEXT["nc4b007_original"])
        ok, _sig, detail = version_gate()
        return (ok, detail)

    control("NC-M4B-007  an incompatible peer version silently accepted",
            red_version, green_version)

    # ---------------------------------------------------------------- NC-M4B-008
    # A closure resting on a completer that is itself incomplete. Planted in the REGISTER,
    # on a real entry, by naming as its completer aspect exactly the part of that completer
    # that is still open — which is the shape the defect actually took at M4-A, where
    # FR-ORD-003 was closed by FR-CFG-001C while FR-CFG-001C's own clause was unbuilt.
    def register_gate() -> tuple[bool, str, str]:
        failures = partial_closures.check()
        named = [d for s, d in failures if s == "PARTIAL_CLOSURE_COMPLETER_INCOMPLETE"]
        if named:
            return (False, "PARTIAL_CLOSURE_COMPLETER_INCOMPLETE", named[0][:220])
        return (True, "", f"{len(partial_closures.load())} entries; no closure rests on an "
                          f"unfinished completer")

    register_path = REPO / "planning" / "partial_closures.json"

    def red_register():
        CONTEXT["nc4b008_original"] = register_path.read_text(encoding="utf-8")
        payload = json.loads(CONTEXT["nc4b008_original"])
        # Find a CLOSED entry whose completer still carries an open entry, and make it
        # claim to rest on the gap. Chosen from the register rather than hard-coded, so
        # the control survives the entries being renamed.
        still_open: dict[str, set[str]] = {}
        for entry in payload["partial_closures"]:
            if entry.get("state") != "closed":
                still_open.setdefault(entry["requirement"], set()).add(entry.get("aspect", ""))
        target = next((e for e in payload["partial_closures"]
                       if e.get("state") == "closed"
                       and e.get("completed_by") in still_open), None)
        if target is None:
            raise CommandUnreadable(
                "no closed entry rests on a completer with an open entry, so this control "
                "has nothing to plant on and would pass by emptiness")
        target["completer_aspect"] = sorted(still_open[target["completed_by"]])[0]
        register_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
        ok, sig, detail = register_gate()
        return (not ok and sig == "PARTIAL_CLOSURE_COMPLETER_INCOMPLETE",
                f"{sig}: {detail}")

    def green_register():
        register_path.write_text(CONTEXT["nc4b008_original"], encoding="utf-8")
        ok, _sig, detail = register_gate()
        return (ok, detail)

    control("NC-M4B-008  a closure resting on a completer that is itself incomplete",
            red_register, green_register)

    # ---------------------------------------------------------------- NC-M4B-009
    # A verification suite the evidence report does not count. This is the defect this
    # slice actually shipped: tests/m4b existed, CI ran it, and the job that regenerates
    # the evidence report handed the generator every log EXCEPT m4b.log, because the copy
    # list was a second statement of a fact the generator already owned. The generator
    # refused, correctly — but only because a missing log is loud. The quiet direction is
    # the one this control holds: a suite with no ROW is simply not added up, and the
    # report then states a total that is short by a whole gate while looking complete.
    #
    # Planted as a REAL directory, like NC-M3D-009, because the rule compares the report's
    # list against the filesystem; mutating the list instead would prove a different rule.
    def suite_gate() -> tuple[bool, str, str]:
        try:
            evidence.assert_suites_cover_the_repository()
        except evidence.SuiteUnaccounted as refused:
            return (False, "SUITE_UNACCOUNTED", str(refused)[:240])
        return (True, "",
                f"{len(evidence.SUITES)} suite(s) named, and tests/ holds exactly those")

    planted_suite = REPO / "tests" / "zz_evidence_unaccounted"

    def red_suite():
        planted_suite.mkdir(exist_ok=True)
        (planted_suite / "verify_zz_evidence_unaccounted.py").write_text(
            "# Planted by NC-M4B-009 and removed by it. If this file is in a commit, the\n"
            "# control crashed between planting and cleanup and the tree is not clean.\n",
            encoding="utf-8")
        ok, sig, detail = suite_gate()
        return (not ok and sig == "SUITE_UNACCOUNTED", f"{sig}: {detail}")

    def green_suite():
        (planted_suite / "verify_zz_evidence_unaccounted.py").unlink(missing_ok=True)
        planted_suite.rmdir()
        ok, _sig, detail = suite_gate()
        return (ok and not planted_suite.exists(),
                f"{detail}; the planted directory is gone, so the tree this control ran "
                f"in is the tree it leaves behind")

    control("NC-M4B-009  a verification suite the evidence report does not count",
            red_suite, green_suite)


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> int:
    print("M4-B verification — payment capture, verification, cash and reversal")
    print("real compiled service, real process, real database, least-privileged role")

    fx.seed()

    sync_and_build()
    service = Service(os.environ["M1A_APP_DSN"])
    if not service.start():
        print(f"FAIL SERVICE_DID_NOT_START\n{service.logs()[-2000:]}")
        return 1

    CONTEXT["service"] = service
    CONTEXT["base_url"] = f"http://127.0.0.1:{service.port}"
    CONTEXT["restart"] = service.restart

    try:
        cashier_session, cashier_token = fx.staff_session(fx.USER_CASHIER)
        manager_session, manager_token = fx.staff_session(fx.USER_FINANCE_MANAGER)
        CONTEXT.update(cashier_session=cashier_session, cashier_token=cashier_token,
                       cashier_user=fx.USER_CASHIER,
                       manager_session=manager_session, manager_token=manager_token)

        section_registry()
        section_boundary_structurally()
        section_boundary_behaviourally()
        section_intent()
        section_cash_payment()
        section_terminal_and_pci()
        section_proof()
        section_allocation()
        section_reversal()
        section_payment_dependent_acceptance()
        section_cash_shift()
        section_shift_closure()
        section_reconciliation()
        section_outage()
        section_health_and_versions()
        section_governance()
        section_controls()
    except (CommandUnreadable, DifferentialUnusable, ProbeFailed) as error:
        # FAIL CLOSED. A suite that cannot load its rules, cannot read a definition or
        # finds the set it was going to assert over empty must STOP rather than continue
        # on a default — a sentinel is not a pass.
        print(f"\nFAIL M4B_VERIFICATION_UNUSABLE: {error}")
        return 1
    finally:
        service.stop()

    failed = [(name, detail) for name, ok, detail, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")

    # The same shape M4-A prints, so the CI step that reads a suite's numbers reads them
    # the same way for every suite rather than once per slice.
    print(f"\nM4-B summary")
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}   (read out of a real browser's layout)")
    print(f"  asserted      : {len(results) - measured_count}   (source, payload, or "
          f"database)")
    print(f"  controls      : "
          f"{sum(1 for n, _o, _d, _e in results if ' — RED' in n)}   "
          f"(each proved red with a real defect, then green after revert)")
    for name, detail in failed:
        print(f"  - {name}")
        for line in (detail or "").splitlines():
            print(f"      {line}")
    print()
    if failed:
        print("FAIL M4B_VERIFICATION")
        return 1
    print("PASS M4B_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
