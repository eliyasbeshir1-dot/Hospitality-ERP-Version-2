#!/usr/bin/env python3
"""M4-C verification: receipts, the printer path, reporting, and the register audit.

M4-A proved a tip cannot reach a bill balance. M4-B decided what counts as money actually
received. This slice produces the two things that leave the building — a piece of paper a
customer takes away, and a figure a manager acts on — and four decisions shape how it asks.

THE PRINTER IS A DIFFERENT RENDERING ENGINE, SO IT IS ASKED AT THE PRINTER. A receipt that
renders correctly on a screen proves nothing about a raster: the font resolution, the
fallback rules and the glyph coverage are all the rasteriser's, and a thermal head has no
grey. So NC-M4-005 inspects the BITMAP the print path produces, per character, and decides
whether the vendored font drew it by comparing against what the platform does with a font
it does not have. That comparison needs no hardcoded picture of a .notdef box, and it
keeps working when Chromium changes what its last-resort glyph looks like.

WHAT IS PROVED IS THE PATH TO THE BYTES, NOT THE PAPER. No printer exists in the build
container or on either CI runner and no pilot device has been chosen. Composition,
rasterisation, per-glyph coverage, ESC/POS encoding and the refusal of a non-character
device are all proved here; that a physical machine takes those bytes and produces legible
paper is not, and planning/M4C_LIMITATIONS.md records exactly that rather than a footnote.

A SIGNED-OFF FIGURE IS PROVED UNREWRITABLE THREE WAYS, BECAUSE ONE WOULD NOT BE ENOUGH.
FR-RPT-014's word is SILENTLY, and recomputation must stay possible. So the suite asks the
catalog whether a grant exists, asks the source whether a write exists, and then attempts
the write through the real path and requires the refusal. Two locks can hide each other;
three that fail independently cannot.

THE REGISTER AUDIT IS THE HEADLINE, AND ITS FINDINGS ARE FINDINGS. FR-GOV-004 asks that
every requirement whose gate has landed is delivered or carries an entry. This suite runs
that audit and requires it to come out clean at this gate — but the gaps it surfaced across
M1 to M3 are recorded in planning/requirement_coverage.json as classifications a reviewer
may challenge, not as bookkeeping that makes them go away.

Every check records whether its evidence is MEASURED — read out of a running browser or
off a raster — or ASSERTED, meaning read from source, from a payload, or from the database.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
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
from fenced import fenced_identifier_pattern                     # noqa: E402
from pg import CommandUnreadable, ProbeFailed, count, run, run_command   # noqa: E402
from service import Service, sync_and_build                      # noqa: E402

import controls as registry                                      # noqa: E402
import partial_closures                                          # noqa: E402
import requirement_coverage as coverage                           # noqa: E402

sys.path.insert(0, str(REPO / "print"))
import agent as printer                                          # noqa: E402

assert fx.__file__ == str(HERE / "fixtures.py"), f"wrong fixtures module: {fx.__file__}"

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]
CTX = dict(tenant=fx.TENANT, outlet=fx.OUTLET_H1)

results: list[tuple[str, bool, str, str]] = []
CONTEXT: dict = {}
RUN_NONCE = os.urandom(6).hex()

SCRATCH = Path(tempfile.gettempdir()) / f"m4c-{RUN_NONCE}"


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    results.append((name, ok, detail, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] ({evidence}) {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


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


_NOT_A_SIGNATURE = {"ERROR", "DETAIL", "HINT", "CONTEXT", "STATEMENT", "WARNING",
                    "NOTICE", "LINE", "SCHEMA", "TABLE", "COLUMN", "CONSTRAINT",
                    "LOCATION", "SELECT", "INSERT", "UPDATE", "DELETE", "WHERE", "VALUES"}


def signature_of(error: str) -> str:
    for matched in re.finditer(r"\b([A-Z][A-Z_]{4,})\b", error or ""):
        if matched.group(1) not in _NOT_A_SIGNATURE:
            return matched.group(1)
    return ""


def call(method: str, path: str, token: str, body: dict | None = None,
         key: str | None = None) -> dict:
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
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {"status": response.status, "text": raw}
            if isinstance(parsed, dict):
                return {"status": response.status, **parsed}
            return {"status": response.status, "body": parsed}
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            return {"status": error.code, **json.loads(raw)}
        except (json.JSONDecodeError, TypeError):
            return {"status": error.code, "text": raw}


def a_uuid() -> str:
    """A canonical UUID, for the reason M4-B's own helper records: an opaque key made of
    a long unbroken run of hexadecimal looks like a card cryptogram to
    payments.refuse_card_data(), and is refused. A UUID is not one."""
    raw = os.urandom(16).hex()
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def idem(label: str) -> str:
    return f"m4c-{label}-{a_uuid()}"


def preview(cart: str, locale: str = "en", channel: str = "dine_in") -> dict:
    res = run(APP, f"""
        SELECT ordering.preview_cart('{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}',
                                     '{locale}', '{channel}');""", **CTX)
    if not res.ok:
        raise ProbeFailed("preview_cart", res.err)
    return json.loads(res.scalar)


def a_settled_bill(locale: str = "en", *, tip_minor: int = 0,
                   lines=((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 1),)) -> dict:
    """A seated party, an order, a check, a bill, a cash payment and — optionally — a tip.

    EVERY STEP THROUGH THE DELIVERED WRITER. A bill assembled by hand would be a bill no
    earlier slice agrees exists, and a receipt issued against it would prove that
    docs.receipt accepts rows.

    The locale travels from the occupancy through the order to the bill, because M4-A
    ruled that a bill translates by ITS OWN locale — so a receipt in Amharic is one issued
    against a bill that was in Amharic, not one asked for in Amharic.
    """
    session = fx.m4a.fresh_occupancy(fx.RECEIPT_TABLE)
    guest = fx.m4a.guest_on(session)
    cart = fx.m4a.cart_with(session, guest, lines)
    view = preview(cart, locale)

    order = scalar(f"""
        SELECT ordering.submit_order(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', '{idem("order")}',
            decode('{view["pricing_digest"]}', 'hex'), {view["total_amount_minor"]},
            '{locale}', gen_random_uuid(), gen_random_uuid(), 'guest_qr',
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

    bill = scalar(f"""
        SELECT billing.issue_bill('{fx.TENANT}', '{fx.OUTLET_H1}', '{check}',
                                  '{fx.USER}', '{locale}');""")
    total = int(scalar(f"SELECT bill_total_minor FROM billing.bill WHERE id = '{bill}';"))

    tip_id = None
    if tip_minor:
        # ONE SHARE, THROUGH THE SPLITTER. billing.split_equally() returns how many shares
        # it made, not their ids, so the share is read back afterwards — a tip attaches to
        # a SHARE because FR-BIL-015 makes a per-payer tip the ordinary case, and a bill
        # with no share has nowhere for one to hang.
        share = scalar(f"""
            SELECT id FROM billing.bill_share WHERE bill_id = '{bill}'
             ORDER BY share_number LIMIT 1;""")
        if not share:
            made = run(APP, f"""
                SELECT billing.split_equally('{fx.TENANT}', '{bill}', 1);""",
                tx=True, **CTX)
            if not made.ok:
                raise ProbeFailed("billing.split_equally", made.err)
            share = scalar(f"""
                SELECT id FROM billing.bill_share WHERE bill_id = '{bill}'
                 ORDER BY share_number LIMIT 1;""")
        if not share:
            raise ProbeFailed(
                "a bill share to hang a tip on",
                f"bill {bill} has no share after an equal split of one. A tip attaches to "
                f"a share, and a fixture that inserted one directly would be inventing "
                f"the thing M4-A's splitter exists to produce")
        tip_id = scalar(f"""
            INSERT INTO billing.tip
                (tenant_id, outlet_id, bill_share_id, currency_code, amount_minor)
            VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{share}', 'ETB', {tip_minor})
            RETURNING id;""")

    intent = scalar(f"""
        SELECT payments.create_intent('{fx.TENANT}', '{fx.OUTLET_H1}', '{bill}',
            '{idem("intent")}', {total}, '{fx.USER}', {tip_minor},
            {"'" + tip_id + "'" if tip_id else "NULL"});""")
    captured = run(APP, f"""
        SELECT payments.capture('{fx.TENANT}', '{fx.OUTLET_H1}', '{intent}',
            'cash', {total + tip_minor}, '{fx.USER}');""", tx=True, **CTX)
    if not captured.ok:
        raise ProbeFailed("payments.capture", captured.err)

    return {"session": session, "guest": guest, "order": order, "check": check,
            "bill": bill, "total": total, "tip": tip_minor, "tip_id": tip_id,
            "locale": locale}


def an_override(action: str, subject_kind: str, subject: str,
                reason_code: str, reason: str) -> str:
    """A real override: one person acting, a DIFFERENT person authorizing from their own
    session. M3-D's function through M4-A's helper, unchanged, because a tip correction is
    a governed action like any other and a second authority model would be a second thing
    to get wrong. The manager is M4-B's finance manager, who holds payment.refund; the
    actor is M4-B's cashier, who does not."""
    actor_session, _ = fx.staff_session(fx.USER_CASHIER)
    manager_session, _ = fx.staff_session(fx.USER_FINANCE_MANAGER)
    fx.step_up(manager_session, action)
    approved = run(APP, f"""
        SELECT set_config('app.auth_strength', 'strong', false);
        SELECT pos.approve_override('{fx.TENANT}', '{fx.OUTLET_H1}', '{action}',
            '{manager_session}', '{reason_code}', '{subject_kind}', '{subject}',
            $r${reason}$r$);""", tx=True, session=actor_session, **CTX)
    if not approved.ok:
        raise ProbeFailed("approve_override", approved.err)
    return (approved.rows[-1][0] if approved.rows else "").strip()


def a_receipt(settled: dict, method: str = "cash") -> str:
    return scalar(f"""
        SELECT docs.issue_receipt('{fx.TENANT}', '{fx.OUTLET_H1}', '{settled["bill"]}',
                                  '{method}', '{fx.USER_CASHIER}');""")


# ===========================================================================
# 1. The catalog IS the metrics (FR-RPT-015)
# ===========================================================================

def section_catalog() -> None:
    print("\n--- 1. The metric catalog is the list of metrics (FR-RPT-015) ---")

    labels = [r[0] for r in rows("""
        SELECT k::text FROM unnest(enum_range(NULL::report.metric_key)) k ORDER BY 1;""",
        dsn=ADMIN)]
    catalogued = [r[0] for r in rows("SELECT key::text FROM report.metric ORDER BY 1;",
                                     dsn=ADMIN)]

    # THE GUARD FIRST. A catalog proved complete over an empty set is complete by having
    # nothing in it, which is the vacuity this repository has caught six times.
    if not labels:
        raise CommandUnreadable(
            "report.metric_key has no labels. Every check in this section would then be "
            "asserting that an empty catalog covers an empty set of metrics")

    record("every metric this build can compute has a catalog entry",
           sorted(labels) == sorted(catalogued),
           f"{len(labels)} label(s) of report.metric_key, {len(catalogued)} row(s) in "
           f"report.metric. Computable and undefined: "
           f"{sorted(set(labels) - set(catalogued)) or 'none'}; defined and not "
           f"computable: {sorted(set(catalogued) - set(labels)) or 'none'}")

    incomplete = rows("""
        SELECT key::text FROM report.metric
         WHERE btrim(formula) = '' OR btrim(timezone_rule) = ''
            OR btrim(currency_rule) = '' OR btrim(inclusion_rule) = ''
            OR btrim(empty_window_reason) = '';""", dsn=ADMIN)
    record("and each entry defines the five things FR-RPT-015 names",
           not incomplete,
           f"entries missing a formula, timezone, currency rule, inclusion rule or "
           f"empty-window reason: {[r[0] for r in incomplete] or 'none'}. They are five "
           f"NOT NULL columns rather than one description, so a missing one is a "
           f"constraint violation instead of a sentence somebody forgot")

    unreal = rows("""
        SELECT m.key::text, m.source_relation::text FROM report.metric m
         WHERE to_regclass(m.source_relation::text) IS NULL;""", dsn=ADMIN)
    record("and each names a data source that exists",
           not unreal,
           f"{unreal or 'none'}. source_relation is of type regclass, so a source that "
           f"is not a relation cannot be written at all — this asks whether the one that "
           f"was written still resolves")

    # THE DOCUMENT IS A RENDERING OF THE TABLE, and the generator refuses to write while
    # the two disagree. Run in --check mode, so the assertion is that the committed
    # catalog matches a fresh generation from the live database.
    proc = run_command(
        [sys.executable, str(REPO / "tools" / "generate_metric_catalog.py"),
         "--dsn", ADMIN, "--check", str(REPO / "planning" / "METRIC_CATALOG.md")])
    record("the published catalog is a rendering of the live metrics, not a copy",
           proc.returncode == 0,
           (proc.stdout.strip() or proc.stderr.strip()).splitlines()[0]
           if (proc.stdout or proc.stderr) else "")

    version = scalar("SELECT report.catalog_version()::text;", dsn=ADMIN)
    record("and the catalog is versioned in one place",
           version.isdigit() and int(version) >= 1,
           f"report.catalog_version() = {version}. Every snapshot and every export "
           f"records it, so a figure taken before a definition changed can be recognised "
           f"as answering a different question rather than as disagreeing about one")


# ===========================================================================
# 2. A reading carries its source and its freshness (FR-RPT-002, FR-UX-014)
# ===========================================================================

def section_readings() -> None:
    print("\n--- 2. Source, freshness, and no fabricated figure "
          "(FR-RPT-002, FR-UX-014) ---")

    window = ("now() - interval '2 days'", "now() + interval '1 hour'")
    readings = rows(f"""
        SELECT (v).metric::text, (v).unit::text,
               coalesce((v).value::text, 'null'),
               coalesce((v).currency_code, '-'),
               (v).observation_count::text,
               (v).source::text,
               ((v).computed_at IS NOT NULL)::text,
               coalesce((v).latest_source_row_at::text, 'null')
          FROM report.metric_values('{fx.TENANT}', '{fx.OUTLET_H1}',
                 {window[0]}, {window[1]}, 'ETB') v ORDER BY 1;""")

    if not readings:
        raise CommandUnreadable(
            "report.metric_values() returned no rows. Every check below would then be "
            "asserting a property of an empty set of readings")

    record("every reading names the relation it came from",
           all(r[5] for r in readings),
           f"{len(readings)} reading(s), each with a source. The source is taken from "
           f"the catalog by report.reading() rather than from the caller, so it cannot "
           f"be omitted or invented")

    record("and every reading says when it was computed",
           all(r[6] == "true" for r in readings),
           f"computed_at present on {sum(1 for r in readings if r[6] == 'true')} of "
           f"{len(readings)}. Two freshness facts rather than one: this is when the "
           f"arithmetic ran, and latest_source_row_at is how recent the data was")

    # THE FR-UX-014 DISTINCTION, checked against the catalog's own declaration rather
    # than against a rule written twice.
    declared = {r[0]: r[1] == "true" for r in rows(
        "SELECT key::text, empty_window_is_zero::text FROM report.metric;", dsn=ADMIN)}
    wrong = []
    for metric, _unit, value, _cur, observations, _src, _ts, _latest in readings:
        if observations == "0":
            if declared.get(metric) and value != "0":
                wrong.append(f"{metric}: empty window declared zero, reported {value}")
            if not declared.get(metric) and value != "null":
                wrong.append(f"{metric}: empty window has no value, reported {value}")
        elif value == "null":
            wrong.append(f"{metric}: {observations} observation(s) and no value")
    record("an empty window is zero or nothing, exactly as the catalog declares",
           not wrong,
           f"{wrong or 'no disagreement'}. A quiet hour genuinely had zero orders; a "
           f"median preparation time over no tickets has no value at all, and reporting "
           f"zero seconds would say every dish was instant")

    monetary = [r for r in readings if r[1] == "minor_currency"]
    record("a monetary figure carries a currency and a count does not",
           bool(monetary)
           and all(r[3] != "-" for r in monetary)
           and all(r[3] == "-" for r in readings if r[1] != "minor_currency"),
           f"{len(monetary)} monetary reading(s), all with a currency; "
           f"{len(readings) - len(monetary)} non-monetary, none with one. "
           f"report.reading() raises METRIC_CURRENCY_MISMATCH in either direction, "
           f"because 1250 birr and 1250 dollars are the same integer")

    # AND THE CONSTRUCTOR IS THE ONLY DOOR. Asked of the source rather than of behaviour:
    # a second path that happened not to be used today would still be a second path.
    body = definition("report.metric_values(uuid, uuid, timestamptz, timestamptz, char)")
    constructor_calls = body.count("report.reading(")
    record("and every reading in the engine is built by that one constructor",
           constructor_calls >= len(readings)
           and "ROW(" not in body.upper().replace("ROW_NUMBER", ""),
           f"{constructor_calls} call(s) to report.reading() for {len(readings)} "
           f"reading(s), and no composite built by hand. A row assembled directly would "
           f"carry whatever the caller put in it, including nothing")


# ===========================================================================
# 3. Sales, classified separately, tips apart (FR-RPT-003)
# ===========================================================================

def section_sales() -> None:
    print("\n--- 3. Sales as separately classified values (FR-RPT-003) ---")

    classifications = [r[0] for r in rows(
        "SELECT unnest(enum_range(NULL::report.sales_classification))::text ORDER BY 1;",
        dsn=ADMIN)]
    reported = rows(f"""
        SELECT classification::text, coalesce(value::text, 'null')
          FROM report.sales_report('{fx.TENANT}', '{fx.OUTLET_H1}',
                 now() - interval '2 days', now() + interval '1 hour', 'ETB')
         ORDER BY 1;""")

    record("all seven classifications are reported, enumerated from the type",
           sorted(r[0] for r in reported) == sorted(classifications)
           and len(classifications) == 7,
           f"{[r[0] for r in reported]}. Enumerated from the type rather than from the "
           f"data, so 'we take no service charge' and 'the service charge query broke' "
           f"do not render the same")

    record("and tips are a classification of their own",
           "tips" in classifications and "bill_payments" in classifications,
           f"tips and bill_payments are separate labels of "
           f"report.sales_classification. A tip is the guest's money moving to staff, "
           f"and a report that added it to takings would answer a different question "
           f"from the one anybody asked")

    # NO SILENT DROP. Every component the bills in the window carry must classify, and
    # the classified total must equal the unclassified one. This is the property
    # report.classify_component()'s RAISE protects, asked of real rows.
    totals = rows(f"""
        SELECT coalesce(sum(c.amount_minor), 0)::text,
               coalesce(sum(CASE WHEN report.classify_component(c.kind, c.source_kind)
                                      IS NOT NULL THEN c.amount_minor ELSE 0 END), 0)::text,
               count(*)::text
          FROM billing.bill_component c
          JOIN billing.bill b ON b.tenant_id = c.tenant_id AND b.id = c.bill_id
         WHERE c.tenant_id = '{fx.TENANT}' AND c.outlet_id = '{fx.OUTLET_H1}';""")
    every, classified, population = totals[0]
    record("no money on a bill falls outside the seven classifications",
           int(population) > 0 and every == classified,
           f"{population} component(s) summing to {every}, of which {classified} "
           f"classify. report.classify_component() RAISES rather than defaulting, so a "
           f"charge source a later gate adds has to be given a home here — money no "
           f"classification claims is money the report loses quietly")

    if int(population) == 0:
        raise CommandUnreadable(
            "no bill component exists in this outlet, so the classification check "
            "examined nothing. A partition proved complete over an empty set is complete "
            "by having nothing in it")


# ===========================================================================
# 4. The signed-off snapshot (FR-RPT-014)
# ===========================================================================

def section_snapshot() -> None:
    print("\n--- 4. A signed-off shift result recomputation cannot rewrite "
          "(FR-RPT-014) ---")

    shift = CONTEXT["snapshot_shift"]
    snapshot = rows(f"""
        SELECT s.id::text, s.catalog_version::text, s.content_digest,
               s.signed_off_by_user_id::text,
               (SELECT count(*)::text FROM report.shift_snapshot_value v
                 WHERE v.tenant_id = s.tenant_id AND v.snapshot_id = s.id)
          FROM report.shift_snapshot s
         WHERE s.tenant_id = '{fx.TENANT}' AND s.shift_id = '{shift}';""")
    if not snapshot:
        raise CommandUnreadable(
            f"shift {shift} was verified and no snapshot exists. Every check in this "
            f"section would then be asserting a property of a document that was never "
            f"written, and FR-RPT-014's whole content is that it is")

    snapshot_id, version, digest, signer, values = snapshot[0]
    catalogued = scalar("SELECT count(*)::text FROM report.metric;", dsn=ADMIN)

    record("signing a shift off writes the snapshot, without anybody asking",
           values == catalogued and signer != "",
           f"snapshot {snapshot_id[:8]} carries {values} of {catalogued} catalogued "
           f"metrics, signed off by {signer[:8]}, under catalog version {version}. "
           f"Written by a trigger on the state change rather than by a call, so a later "
           f"gate adding another way to verify a shift cannot add one that forgets")

    # LOCK ONE: THE GRANT. Asked of the catalog, because a path that is not taken today
    # is not the same as a path that does not exist.
    grants = rows("""
        SELECT c.relname, privilege_type
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
          JOIN information_schema.table_privileges p
            ON p.table_schema = n.nspname AND p.table_name = c.relname
         WHERE n.nspname = 'report'
           AND c.relname IN ('shift_snapshot', 'shift_snapshot_value')
           AND p.grantee = 'hospitality_app'
           AND p.privilege_type IN ('INSERT', 'UPDATE', 'DELETE')
         ORDER BY 1, 2;""", dsn=ADMIN)
    record("the application role cannot write a snapshot at all",
           not grants,
           f"write grants held by hospitality_app on the snapshot tables: "
           f"{grants or 'none'}. cash.shift carries no UPDATE grant either, so the only "
           f"path that reaches these tables is the trigger that fires at sign-off")

    # LOCK TWO: THE SOURCE. The recomputation function contains no write against them.
    body = definition("report.recompute_shift_snapshot(uuid, uuid, uuid)")
    writes = re.findall(r"(?:UPDATE|DELETE\s+FROM|INSERT\s+INTO)\s+(report\.\w+)",
                        body, re.IGNORECASE)
    record("and the recomputation writes to the divergence record, never the snapshot",
           "report.shift_snapshot" not in writes
           and "report.shift_snapshot_value" not in writes
           and "report.recomputation" in writes,
           f"tables written by report.recompute_shift_snapshot(): {sorted(set(writes))}. "
           f"FR-RPT-014's word is SILENTLY: recomputation stays possible, and what is "
           f"impossible is that it lands on the signed-off figures")

    # LOCK THREE: THE ATTEMPT, through the strongest caller in the system.
    forced = run(ADMIN, f"""
        UPDATE report.shift_snapshot_value SET value = value + 1
         WHERE tenant_id = '{fx.TENANT}' AND snapshot_id = '{snapshot_id}';""", tx=True)
    record("and a superuser rewriting a signed-off figure is refused by name",
           forced.failed_with("LEDGER_ROW_DELETED_NOT_REVERSED"),
           forced.why() or "a signed-off figure was rewritten. Three locks, and this is "
                           "the one that holds when the other two are defeated")

    # AND THE FIGURES ARE UNCHANGED BY CENSUS, not by trusting the refusal.
    after = scalar(f"""
        SELECT report.snapshot_digest('{fx.TENANT}', '{snapshot_id}');""", dsn=ADMIN)
    record("and the snapshot still digests to what was signed",
           after == digest,
           f"sealed {digest[:16]}…, now {after[:16]}…. Compared by digest rather than by "
           f"the absence of an exception, because a control that trusted the refusal "
           f"would not have noticed a partial write")


def section_recomputation() -> None:
    print("\n--- 5. A recomputation reports what it found (FR-RPT-014) ---")

    shift = CONTEXT["snapshot_shift"]

    agreed = scalar(f"""
        SELECT report.recompute_shift_snapshot('{fx.TENANT}', '{shift}',
                                               '{fx.USER_FINANCE_MANAGER}');""")
    state = rows(f"""
        SELECT r.diverged::text,
               (SELECT count(*)::text FROM report.snapshot_divergence d
                 WHERE d.tenant_id = r.tenant_id AND d.recomputation_id = r.id)
          FROM report.recomputation r
         WHERE r.tenant_id = '{fx.TENANT}' AND r.id = '{agreed}';""")
    record("recomputing an untouched shift agrees, and the agreement is recorded",
           state and state[0] == ["false", "0"],
           f"{state}. The agreeing runs are recorded too: a record only of "
           f"disagreements cannot tell 'checked and fine' from 'never checked'")

    # NOW MOVE THE WORLD UNDER IT. A tip corrected after sign-off, for a tip taken DURING
    # the shift, is the case FR-RPT-014 is actually about: a recomputation of that window
    # now produces a different answer, and the question is whether it can quietly become
    # the answer somebody put their name to.
    #
    # THE CORRECTION IS DATED INSIDE THE WINDOW, and that is the point rather than a
    # convenience. A correction stamped now would fall outside the shift entirely and the
    # recomputation would agree — truthfully, and proving nothing. Corrections recorded
    # after the fact for something that happened earlier are ordinary; what must not be
    # ordinary is the signed-off figure moving with them.
    tip = rows(f"""
        SELECT t.id::text FROM billing.tip t
         WHERE t.tenant_id = '{fx.TENANT}' AND t.outlet_id = '{fx.OUTLET_H1}'
         ORDER BY t.chosen_at DESC LIMIT 1;""")
    if not tip:
        raise CommandUnreadable(
            "no tip exists in this outlet, so there is nothing to correct and the "
            "divergence check would report agreement over an empty change")

    override = an_override("payment.refund", "bill",
                           CONTEXT["tipped_settlement"]["bill"],
                           fx.reason_code("M4C_RECEIPT_REISSUE"),
                           "a tip corrected after the drawer was signed off")
    # HALFWAY THROUGH THE WINDOW, computed from its two ends rather than by adding a
    # fixed offset to one of them. A shift in a test can be milliseconds wide, and
    # "window_from plus a second" landed AFTER window_to — the recomputation then agreed,
    # correctly, and the control was measuring nothing.
    window = rows(f"""
        SELECT s.window_from::text, s.window_to::text FROM report.shift_snapshot s
         WHERE s.tenant_id = '{fx.TENANT}' AND s.shift_id = '{shift}';""")
    correction = run(APP, f"""
        INSERT INTO billing.tip_correction
            (tenant_id, outlet_id, tip_id, kind, currency_code, amount_minor,
             override_id, reason_code_id, reason_text, actor_user_id, corrected_at)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{tip[0][0]}', 'correction', 'ETB', 100,
                '{override}', '{fx.reason_code("M4C_RECEIPT_REISSUE")}',
                'a tip corrected after the drawer was signed off',
                '{fx.USER_CASHIER}',
                timestamptz '{window[0][0]}'
                  + (timestamptz '{window[0][1]}' - timestamptz '{window[0][0]}') / 2);""",
        tx=True, **CTX)
    if not correction.ok:
        raise ProbeFailed("a tip correction after sign-off", correction.err)

    diverged = scalar(f"""
        SELECT report.recompute_shift_snapshot('{fx.TENANT}', '{shift}',
                                               '{fx.USER_FINANCE_MANAGER}');""")
    found = rows(f"""
        SELECT r.diverged::text, coalesce(d.metric::text, 'none'),
               coalesce(d.snapshot_value::text, 'null'),
               coalesce(d.recomputed_value::text, 'null')
          FROM report.recomputation r
          LEFT JOIN report.snapshot_divergence d
            ON d.tenant_id = r.tenant_id AND d.recomputation_id = r.id
         WHERE r.tenant_id = '{fx.TENANT}' AND r.id = '{diverged}'
         ORDER BY 2;""")
    record("and a world that moved afterwards produces a divergence, loudly",
           bool(found) and found[0][0] == "true"
           and any(r[1] != "none" for r in found),
           f"{found}. The divergence names both numbers. It is louder than the original, "
           f"which is the correct direction for this to fail in")

    unchanged = rows(f"""
        SELECT v.metric::text, coalesce(v.value::text, 'null')
          FROM report.shift_snapshot_value v
          JOIN report.shift_snapshot s
            ON s.tenant_id = v.tenant_id AND s.id = v.snapshot_id
         WHERE s.tenant_id = '{fx.TENANT}' AND s.shift_id = '{shift}'
           AND v.metric = 'tip_reversals_minor';""")
    record("and the signed-off figure is exactly what it was",
           unchanged and unchanged[0][1] == CONTEXT["signed_tip_reversals"],
           f"tip_reversals_minor signed as {CONTEXT['signed_tip_reversals']}, still "
           f"{unchanged[0][1] if unchanged else 'absent'} after a correction and two "
           f"recomputations")


# ===========================================================================
# 6. Exports and dashboards (FR-RPT-013, FR-RPT-001, FR-UX-014)
# ===========================================================================

def section_exports_and_dashboards() -> None:
    print("\n--- 6. Dashboards and exports (FR-RPT-001, FR-RPT-013, FR-UX-014) ---")

    # NO SECURITY DEFINER IN THE REPORTING SCHEMA. This is FR-RPT-013's scoping: a
    # function with a privilege its caller lacks would read every outlet in the tenant,
    # and no test of the query would notice.
    definers = rows("""
        SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'report' AND p.prosecdef ORDER BY 1;""", dsn=ADMIN)
    record("no reporting function has a privilege its caller lacks",
           not definers,
           f"SECURITY DEFINER functions in schema report: "
           f"{[r[0] for r in definers] or 'none'}. Tenant and outlet scoping is the "
           f"database's, not a WHERE clause a route appends and could forget")

    token = CONTEXT["manager_token"]
    exported = call("GET", "/s/v1/reports/exports/metrics.csv", token)
    body = exported.get("text", "")
    header = body.splitlines()[0] if body else ""
    record("the export is CSV with a documented header",
           exported.get("status") == 200
           and header.startswith("metric,unit,value,currency_code,observation_count"),
           f"status {exported.get('status')}, header {header!r}")

    # THE FR-UX-014 DISTINCTION SURVIVES THE EXPORT. An absent figure is an empty field,
    # not a zero — a reader opening this in a spreadsheet must be able to tell them apart.
    empties = [line for line in body.splitlines()[1:]
               if line.split(",")[2] == "" and '"seconds"' in line]
    zeroes = [line for line in body.splitlines()[1:] if line.split(",")[2] == "0"]
    record("and an absent figure exports as an empty field, not as zero",
           bool(empties) and bool(zeroes),
           f"{len(empties)} line(s) with no value and {len(zeroes)} with a real zero. "
           f"A median over no observations and a count of nothing are different facts, "
           f"and a spreadsheet that showed both as 0 would erase the difference")

    recorded = rows(f"""
        SELECT kind::text, row_count::text, catalog_version::text
          FROM report.export
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
         ORDER BY requested_at DESC LIMIT 1;""")
    record("and the export is recorded with the scope and version it was taken at",
           recorded and recorded[0][0] == "metrics" and int(recorded[0][1]) > 0,
           f"{recorded}. The tenant and outlet on that row are the scope the data was "
           f"read under, because the function is SECURITY INVOKER")

    roles = [r[0] for r in rows(
        "SELECT unnest(enum_range(NULL::report.dashboard_role))::text ORDER BY 1;",
        dsn=ADMIN)]
    bare = rows("""
        SELECT r::text FROM unnest(enum_range(NULL::report.dashboard_role)) r
         WHERE NOT EXISTS (SELECT 1 FROM report.dashboard_panel p WHERE p.role = r);""",
        dsn=ADMIN)
    record("every Phase 1 role has a dashboard with panels on it",
           roles and not bare,
           f"{roles}, none empty. An empty dashboard is the shape a role takes when "
           f"somebody added it to the enum and stopped")

    record("and the technical-operator dashboard is not half-built here",
           "technical_operator" not in roles,
           f"report.dashboard_role has no such label. FR-RPT-001's later_behavior places "
           f"it at M5a and it covers the local node, synchronization and the printer — "
           f"none of which exists at this gate, so a panel for it could only be empty")

    # A PANEL NAMES A CATALOGUED METRIC OR NOTHING, which is how a deferred domain is kept
    # off the reporting surface — not by a reviewer reading the panel list.
    fenced, fenced_terms = fenced_identifier_pattern()
    panels = rows("""
        SELECT p.role::text, p.metric::text FROM report.dashboard_panel p ORDER BY 1, 2;""",
        dsn=ADMIN)
    offending = [f"{role}.{metric}" for role, metric in panels
                 if re.search(fenced, metric)]
    record("and no panel names a fenced domain",
           bool(panels) and not offending,
           f"{len(panels)} panel(s) against {fenced_terms} fenced term(s); "
           f"{offending or 'none'} name one. A panel "
           f"is a label of report.metric_key with a foreign key into report.metric: "
           f"there is no free-text panel for a fenced word to arrive through")

    dashboard = call("GET", "/s/v1/reports/dashboards/outlet_manager", token)
    panels_seen = dashboard.get("panels") or []
    record("and a dashboard answers with the source and freshness on every panel",
           dashboard.get("status") == 200 and panels_seen
           and all(p.get("source") and p.get("computedAt") for p in panels_seen),
           f"status {dashboard.get('status')}, {len(panels_seen)} panel(s). The label is "
           f"part of the value rather than something the surface remembers to draw")


# ===========================================================================
# 7. The receipt (FR-BIL-010, FR-BIL-016, FR-I18N-001C)
# ===========================================================================

def section_receipt() -> None:
    print("\n--- 7. The receipt: three figures, three lines, one language "
          "(FR-BIL-010, FR-BIL-016, FR-I18N-001C) ---")

    settled = CONTEXT["english_settlement"]
    receipt = CONTEXT["english_receipt"]

    lines = rows(f"""
        SELECT l.kind::text, l.label, coalesce(l.amount_minor::text, 'null'),
               coalesce(l.currency_code, '-')
          FROM docs.receipt_line l
         WHERE l.tenant_id = '{fx.TENANT}' AND l.receipt_id = '{receipt}'
         ORDER BY l.display_order;""")
    kinds = [r[0] for r in lines]

    record("bill total, tip and total paid are three separate lines",
           kinds.count("bill_total") == 1 and kinds.count("tip") == 1
           and kinds.count("total_paid") == 1,
           f"{kinds}. Separate KINDS with a unique index per receipt, so a merged line "
           f"is a missing kind rather than a formatting choice")

    record("and the payment method actually used is a line of its own",
           kinds.count("payment_method") == 1,
           f"{[r[1] for r in lines if r[0] == 'payment_method']}. FR-BIL-017 asks for "
           f"the method actually used, and docs.issue_receipt() refuses a blank one")

    record("and every figure sits beside its own currency",
           all(r[3] != "-" for r in lines if r[2] != "null"),
           f"{[(r[0], r[3]) for r in lines]}. The currency is carried by a foreign key "
           f"into the receipt's own currency anchor, so a line denominated in something "
           f"its receipt is not in has no parent row to point at")

    figures = {r[0]: r[2] for r in lines}
    expected_paid = settled["total"] + settled["tip"]
    record("and the three figures are the bill, the tip and their sum",
           figures.get("bill_total") == str(settled["total"])
           and figures.get("tip") == str(settled["tip"])
           and figures.get("total_paid") == str(expected_paid),
           f"bill {figures.get('bill_total')} against {settled['total']}, tip "
           f"{figures.get('tip')} against {settled['tip']}, paid "
           f"{figures.get('total_paid')} against {expected_paid}. Total paid is the one "
           f"line that adds the two, because it is the figure describing the money that "
           f"changed hands")

    # THE TIP LINE EXISTS AT ZERO. A receipt whose shape depended on its amounts would
    # make "no tip" and "a tip we forgot to print" the same document.
    no_tip = CONTEXT["no_tip_receipt"]
    zero = rows(f"""
        SELECT l.kind::text, l.amount_minor::text FROM docs.receipt_line l
         WHERE l.tenant_id = '{fx.TENANT}' AND l.receipt_id = '{no_tip}'
           AND l.kind = 'tip';""")
    record("a receipt with no tip still carries the tip line, reading zero",
           zero and zero[0][1] == "0",
           f"{zero}. 'Optional tip' is about whether a guest left one, not about whether "
           f"the receipt accounts for it — and a document whose shape depends on its "
           f"amounts makes 'none' and 'omitted' the same page")

    # THE LOCALE IS THE BILL'S. Asked of the signature, because a locale parameter that
    # nobody passes today is still a locale parameter.
    signature = rows("""
        SELECT pg_get_function_arguments(p.oid)
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'docs' AND p.proname = 'issue_receipt';""", dsn=ADMIN)
    record("a receipt cannot be asked for in the reader's language",
           signature and "locale" not in signature[0][0],
           f"docs.issue_receipt({signature[0][0] if signature else '?'}). M4-A ruled a "
           f"bill translates by its own locale; there is no argument here by which a "
           f"manager reprinting a customer's receipt could change what language it is in")

    amharic = CONTEXT["amharic_receipt"]
    labels = rows(f"""
        SELECT l.kind::text, l.label FROM docs.receipt_line l
         WHERE l.tenant_id = '{fx.TENANT}' AND l.receipt_id = '{amharic}'
         ORDER BY l.display_order;""")
    ethiopic = [r for r in labels
                if any("ሀ" <= ch <= "፿" for ch in r[1])]
    record("an Amharic bill produces an Amharic receipt, every line",
           len(labels) == len(ethiopic),
           f"{len(ethiopic)} of {len(labels)} line(s) carry Ethiopic script. 0027's "
           f"completeness trigger refuses a non-English receipt whose label is the "
           f"English source text, so a partial translation cannot reach paper")


# ===========================================================================
# 8. The printer path (FR-CFG-001D, FR-BIL-011, FR-BIL-017)
# ===========================================================================

def section_printer() -> None:
    print("\n--- 8. Registered, tested, and printed once "
          "(FR-CFG-001D, FR-BIL-011, FR-BIL-017) ---")

    receipt = CONTEXT["english_receipt"]

    # THE TWO TYPES, ASKED OF THE CATALOG. A print outcome and a render outcome are
    # different types with no cast between them, which is what makes "a file that received
    # the bytes is not a print" a fact about the schema rather than about today's code.
    casts = rows("""
        SELECT count(*)::text FROM pg_cast c
          JOIN pg_type s ON s.oid = c.castsource
          JOIN pg_type t ON t.oid = c.casttarget
         WHERE s.typname IN ('print_outcome', 'render_outcome')
           AND t.typname IN ('print_outcome', 'render_outcome')
           AND s.typname <> t.typname;""", dsn=ADMIN)
    record("a preview outcome and a print outcome are two types with no cast between them",
           casts and casts[0][0] == "0",
           f"{casts[0][0] if casts else '?'} cast(s) between docs.print_outcome and "
           f"docs.render_outcome. A boolean is flipped by an UPDATE; a type is not")

    # AND THE COLUMNS THEY LAND IN ARE OF THOSE TYPES, so the boundary is not merely
    # available — it is the only shape a row can take.
    columns = {f"{r[0]}.{r[1]}": r[2] for r in rows("""
        SELECT c.relname, a.attname, t.typname
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'outcome'
          JOIN pg_type t ON t.oid = a.atttypid
         WHERE n.nspname = 'docs' AND c.relkind = 'r';""", dsn=ADMIN)}
    record("and the tables that record them cannot hold each other's values",
           columns.get("print_attempt.outcome") == "print_outcome"
           and columns.get("render_attempt.outcome") == "render_outcome"
           and columns.get("printer_test.outcome") == "print_outcome",
           f"{columns}. A printer test is of the print type too, so a preview cannot be "
           f"tested into looking like a printer — the value would not fit the column")

    untested = run(APP, f"""
        SELECT docs.record_receipt_print('{fx.TENANT}', '{fx.OUTLET_H1}', '{receipt}',
            '{fx.PRINTER_UNTESTED}', 'printed', repeat('b', 64)::char(64), 64,
            '{fx.USER_CASHIER}');""", tx=True, **CTX)
    record("a customer receipt cannot be printed on a printer nobody tested",
           untested.failed_with("PRINTER_NEVER_TESTED"),
           untested.why() or "an untested printer printed a customer receipt. "
                             "FR-CFG-001D says setup registers AND TESTS")

    printed = scalar(f"""
        SELECT docs.record_receipt_print('{fx.TENANT}', '{fx.OUTLET_H1}', '{receipt}',
            '{fx.PRINTER_DEVICE}', 'printed', repeat('c', 64)::char(64), 512,
            '{fx.USER_CASHIER}');""")
    record("and on a tested one it is printed, once",
           bool(printed),
           f"print attempt {printed[:8]} against a printer with a successful test on "
           f"record. FR-CFG-001D's two halves are one precondition rather than two "
           f"screens")

    again = run(APP, f"""
        SELECT docs.record_receipt_print('{fx.TENANT}', '{fx.OUTLET_H1}', '{receipt}',
            '{fx.PRINTER_DEVICE}', 'printed', repeat('c', 64)::char(64), 512,
            '{fx.USER_CASHIER}');""", tx=True, **CTX)
    record("and a second original print of the same settlement is refused",
           again.failed_with("DUPLICATE_RECEIPT_PRINTED", "print_attempt_one_original"),
           again.why() or "one settlement produced two original receipts. A customer "
                          "holding two records of one payment is two payments as far as "
                          "anyone reading them can tell")

    reprint_without_reason = run(APP, f"""
        SELECT docs.record_receipt_print('{fx.TENANT}', '{fx.OUTLET_H1}', '{receipt}',
            '{fx.PRINTER_DEVICE}', 'printed', repeat('d', 64)::char(64), 512,
            '{fx.USER_CASHIER}', true, NULL, NULL);""", tx=True, **CTX)
    record("a reprint with no reason is refused by constraint",
           not reprint_without_reason.ok,
           reprint_without_reason.why() or "a reprint was recorded with no reason. "
                                           "FR-BIL-011 asks for operator AND reason")

    reprint = scalar(f"""
        SELECT docs.record_receipt_print('{fx.TENANT}', '{fx.OUTLET_H1}', '{receipt}',
            '{fx.PRINTER_DEVICE}', 'printed', repeat('d', 64)::char(64), 512,
            '{fx.USER_CASHIER}', true, '{fx.reason_code("M4C_RECEIPT_REPRINT")}',
            'the customer asked for another copy');""")
    marked = rows(f"""
        SELECT a.is_reprint::text, (a.reason_code_id IS NOT NULL)::text,
               (a.operator_user_id IS NOT NULL)::text
          FROM docs.print_attempt a
         WHERE a.tenant_id = '{fx.TENANT}' AND a.id = '{reprint}';""")
    record("and a marked reprint carries its operator and its reason",
           marked and marked[0] == ["true", "true", "true"],
           f"{marked}. Marked, and audited: the CHECK requires the reason on a reprint "
           f"and FORBIDS one on an original, so 'reprint' cannot be a word somebody typed")

    # A DEVICE SINK REFUSES A FILE, AND A FILE SINK REFUSES A DEVICE. Both directions, so
    # neither is a rule that happens to hold in one of them.
    wrong_sink = run(APP, f"""
        SELECT docs.record_receipt_print('{fx.TENANT}', '{fx.OUTLET_H1}', '{receipt}',
            '{fx.PRINTER_PREVIEW}', 'printed', repeat('e', 64)::char(64), 64,
            '{fx.USER_CASHIER}');""", tx=True, **CTX)
    record("a print cannot be recorded against a preview sink",
           not wrong_sink.ok,
           wrong_sink.why() or "bytes written to a file were recorded as a print")

    wrong_way = run(APP, f"""
        SELECT docs.record_receipt_render('{fx.TENANT}', '{fx.OUTLET_H1}', 'receipt',
            '{receipt}', '{fx.PRINTER_DEVICE}', 'rendered', repeat('f', 64)::char(64),
            64, '{fx.USER_CASHIER}');""", tx=True, **CTX)
    record("and a render cannot be recorded against a device",
           not wrong_way.ok,
           wrong_way.why() or "a preview was recorded against a real printer")

    promoted = run(ADMIN, f"""
        UPDATE docs.printer SET connection = 'character_device', sink = 'device'
         WHERE tenant_id = '{fx.TENANT}' AND id = '{fx.PRINTER_PREVIEW}';""", tx=True)
    record("and a preview printer cannot be promoted into a device",
           promoted.failed_with("PRINTER_IDENTITY_IMMUTABLE"),
           promoted.why() or "a file sink became a character device by UPDATE, which "
                             "would rewrite what every attempt already recorded against "
                             "it means")


# ===========================================================================
# 9. One composer, two sinks (FR-UX-018)
# ===========================================================================

def section_preview() -> None:
    print("\n--- 9. The preview and the receipt are the same composer (FR-UX-018) ---")

    receipt = CONTEXT["english_receipt"]

    document = json.loads(scalar(
        f"SELECT docs.receipt_document('{fx.TENANT}', '{receipt}')::text;"))
    specimen = json.loads(scalar(
        f"SELECT docs.preview_document('{fx.TENANT}', '{fx.OUTLET_H1}', 'en', 'ETB')::text;"))

    record("a receipt and a preview are built by one function",
           "docs.compose_document" in definition("docs.receipt_document(uuid, uuid)")
           and "docs.compose_document" in definition(
               "docs.preview_document(uuid, uuid, menu.customer_locale, char)"),
           "both call docs.compose_document(). FR-UX-018's later_behavior is that the "
           "physical output matches the preview, and one composer is what makes that a "
           "property rather than two implementations that agree today")

    record("and a specimen says so on its face and carries no receipt number",
           specimen.get("is_specimen") is True
           and specimen.get("receipt_number") is None
           and any("SPECIMEN" in (line.get("text") or "")
                   for line in specimen.get("lines", [])),
           f"is_specimen={specimen.get('is_specimen')}, "
           f"receipt_number={specimen.get('receipt_number')}. The marking is a LINE "
           f"rather than a flag, so a renderer that ignored it would produce a document "
           f"with a line missing instead of one indistinguishable from a receipt")

    forced = run(ADMIN, """
        SELECT docs.compose_document('RECEIPT', '[{"text":"x"}]'::jsonb, true, 'RCP-1');""",
        tx=True)
    record("and a specimen cannot be given one",
           forced.failed_with("SPECIMEN_CARRIES_A_RECEIPT_NUMBER"),
           forced.why() or "a preview was composed with a receipt number, which is the "
                           "one thing on the page that says a document records something")

    record("a real receipt carries its number and is not a specimen",
           document.get("is_specimen") is False and document.get("receipt_number"),
           f"receipt_number={document.get('receipt_number')}, "
           f"is_specimen={document.get('is_specimen')}")

    # EVERY LINE KIND APPEARS IN THE PREVIEW, enumerated from the type. A preview whose
    # line list was written by hand would stop showing a kind the day somebody added one.
    kinds = [r[0] for r in rows(
        "SELECT unnest(enum_range(NULL::docs.receipt_line_kind))::text ORDER BY 1;",
        dsn=ADMIN)]
    record("and the preview exercises every line kind the schema has",
           len(specimen.get("lines", [])) >= len(kinds) + 2,
           f"{len(specimen.get('lines', []))} line(s) for {len(kinds)} kind(s) plus a "
           f"title and the specimen marking. Enumerated from docs.receipt_line_kind, so "
           f"a kind added later appears without anybody remembering to add it")


# ===========================================================================
# 10. The counter order, at the terminal (FR-POS-003B)
# ===========================================================================

def section_counter() -> None:
    print("\n--- 10. A counter order is created at the POS terminal (FR-POS-003B) ---")

    # THE SAME AGGREGATE, asked of the source. M4-A proved there is one submitting
    # handler; this asks whether anything else writes a submitted order.
    # THE SUBMITTED EVENT, not every order event. Acceptance, amendment, cancellation and
    # a table move all write to the ledger and should; what must have exactly one writer
    # is the event that BRINGS AN ORDER INTO EXISTENCE, because that is where the rules a
    # counter order must obey are applied.
    writers = rows("""
        SELECT n.nspname || '.' || p.proname
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
           -- prokind 'f', because pg_get_functiondef() refuses an aggregate and the
           -- refusal would stop the scan rather than answer it. A scan that dies is not
           -- "no offenders found".
           AND p.prokind = 'f'
           AND pg_get_functiondef(p.oid) ~
               'INSERT INTO ordering\\.order_event[^;]*''submitted'''
         ORDER BY 1;""", dsn=ADMIN)
    record("a counter order goes through the one function every order goes through",
           [r[0] for r in writers] == ["ordering.submit_order"],
           f"functions that write a SUBMITTED order event: {[r[0] for r in writers]}. "
           f"pos.record_counter_order() is not among them: it records WHERE an order was "
           f"entered and creates none")

    entry = rows(f"""
        SELECT e.order_id::text, e.terminal_device_id::text, t.profile::text,
               (t.revoked_at IS NULL)::text
          FROM pos.counter_order_entry e
          JOIN pos.terminal t ON t.tenant_id = e.tenant_id
                             AND t.device_id = e.terminal_device_id
         WHERE e.tenant_id = '{fx.TENANT}' AND e.order_id = '{CONTEXT["counter_order"]}';""")
    record("and it names the active point-of-sale terminal it was entered at",
           entry and entry[0][2] == "point_of_sale" and entry[0][3] == "true",
           f"{entry}. The terminal is resolved from identity.session.device_id rather "
           f"than passed, so there is no argument by which a request from anywhere could "
           f"assert it came from the counter")

    # NO FOREIGN KEY INTO A PROJECTION. M3-D's rule, and the reason docs.receipt carries
    # none either: ordering.customer_order is deleted wholesale by a rebuild.
    keys = rows("""
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'pos.counter_order_entry'::regclass AND contype = 'f'
           AND confrelid = 'ordering.customer_order'::regclass;""", dsn=ADMIN)
    record("and the record holds no key into the order projection",
           not keys,
           f"foreign keys into ordering.customer_order: {[r[0] for r in keys] or 'none'}. "
           f"A rebuild deletes every order row and replays them; a durable key into that "
           f"is the defect M4-B shipped one layer over")

    entered_elsewhere = run(APP, f"""
        SELECT pos.record_counter_order('{fx.TENANT}', '{fx.OUTLET_H1}',
                                        '{CONTEXT["qr_order"]}', '{fx.USER}');""",
        tx=True, session=CONTEXT["counter_session"], **CTX)
    record("a terminal cannot be recorded against an order that was not a counter order",
           not entered_elsewhere.ok,
           entered_elsewhere.why() or "a guest's QR order was recorded as entered at a "
                                      "till, which would make the terminal record answer "
                                      "a question it was not asked")


# ===========================================================================
# 11. Ethiopic at the printer, measured off the raster (FR-I18N-001C, NC-M4-005)
# ===========================================================================

def rasterise(document: dict, font: str | None = None) -> dict:
    """Run the printer path's own renderer and read what it drew.

    THROUGH print/agent.py, NOT AROUND IT. agent.rasterise() is the production function:
    it copies the renderer into the workspace (ES module resolution ignores NODE_PATH, so
    a renderer left in the repository cannot find playwright, and node_modules must never
    appear in the repository), passes the verified font set, and refuses when a face will
    not load. A second copy of that plumbing here would be a second path, and the one this
    suite measured would not be the one that prints.
    """
    return printer.rasterise(document, dots_wide=576,
                             workspace=CONTEXT["workspace"], font=font)


def section_ethiopic_on_the_printer() -> None:
    print("\n--- 11. Ethiopic on the printer path, read off the raster "
          "(FR-I18N-001C, FR-BIL-017) ---")

    document = json.loads(scalar(
        f"SELECT docs.receipt_document('{fx.TENANT}', '{CONTEXT['amharic_receipt']}')::text;"))

    measured = rasterise(document)
    if not measured.get("fontLoaded"):
        raise ProbeFailed("the vendored font did not load",
                          str(measured.get("fontError")))

    coverage = measured.get("coverage") or []
    ethiopic = [c for c in coverage if 0x1200 <= c["codepoint"] <= 0x137F]
    if not ethiopic:
        raise CommandUnreadable(
            "the Amharic receipt's raster contains no Ethiopic codepoint. NC-M4-005 "
            "would then be measuring font coverage over an alphabet that is not there, "
            "and would pass by having nothing to fail on")

    uncovered = [c for c in ethiopic if not c["drawnByTheVendoredFont"]]
    record("every Ethiopic character on the receipt was drawn by the packaged font",
           not uncovered,
           f"{len(ethiopic)} Ethiopic codepoint(s) in the raster, "
           f"{len(uncovered)} drawn by something else: "
           f"{[hex(c['codepoint']) for c in uncovered] or 'none'}. Measured by drawing "
           f"each character twice — once in the vendored family, once in a family "
           f"nothing can resolve — and comparing the ink. That needs no picture of a "
           f".notdef box and keeps working when the engine changes what its last-resort "
           f"glyph looks like",
           evidence="measured")

    record("and the raster is a whole number of bytes per row, at printer width",
           measured.get("width") == 576 and measured.get("rowBytes") == 72,
           f"{measured.get('width')} dots, {measured.get('rowBytes')} bytes per row, "
           f"{measured.get('height')} rows. A width that was not a whole number of bytes "
           f"would silently drop the right-hand edge of every line",
           evidence="measured")

    # THE FONT IS THE ONE THIS REPOSITORY SHIPS, by checksum, in the suite rather than
    # only in the provenance record. A provenance file is a claim; this is the test.
    font_path = REPO / "print" / "fonts" / "NotoSansEthiopic-Regular.ttf"
    digest = hashlib.sha256(font_path.read_bytes()).hexdigest()
    provenance = (REPO / "print" / "fonts" / "PROVENANCE.md").read_text(encoding="utf-8")
    record("and the font on disk is the font the provenance record names",
           digest in provenance,
           f"sha256 {digest[:16]}… found in PROVENANCE.md: {digest in provenance}. "
           f"Asserted here and not only recorded there, because a record beside a file "
           f"is a claim about it")

    record("and the licence travels with the binary",
           (REPO / "print" / "fonts" / "OFL-1.1.txt").exists()
           and "SIL OPEN FONT LICENSE" in
               (REPO / "print" / "fonts" / "OFL-1.1.txt").read_text(encoding="utf-8").upper(),
           "print/fonts/OFL-1.1.txt is present. OFL-1.1 requires the copyright notice "
           "and the licence to accompany every copy of the font software, which means "
           "every distribution of this repository and of anything built from it")

    # THE SAME BYTES TWICE. A raster that differed between runs would make every claim
    # above a claim about one run.
    again = rasterise(document)
    record("and the same document rasterises to the same bytes twice",
           again.get("bitsBase64") == measured.get("bitsBase64"),
           f"{len(measured.get('bitsBase64') or '')} base64 characters, identical on a "
           f"second run: "
           f"{again.get('bitsBase64') == measured.get('bitsBase64')}. A raster that "
           f"varied would make a print and its reprint two different documents",
           evidence="measured")


# ===========================================================================
# 12. The fiscal port, and what it does not prove (FR-BIL-012)
# ===========================================================================

def section_fiscal() -> None:
    print("\n--- 12. The fiscal document port (FR-BIL-012) ---")

    provider_columns = rows("""
        SELECT c.relname || '.' || a.attname
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
         WHERE n.nspname = 'fiscal' AND c.relkind = 'r'
           AND a.attname ~* '(signature|certificate|device_serial|tin|vat_number|zreport)'
         ORDER BY 1;""", dsn=ADMIN)
    record("no provider's schema is embedded in the domain model",
           not provider_columns,
           f"columns naming a provider concept: "
           f"{[r[0] for r in provider_columns] or 'none'}. provider_reference and "
           f"provider_payload are opaque and the platform parses neither")

    live = run(ADMIN, f"""
        INSERT INTO fiscal.adapter (tenant_id, outlet_id, mode)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'live');""", tx=True)
    record("and no adapter can claim to be live while none is contracted",
           not live.ok,
           live.why() or "a live fiscal adapter was registered. The mode is pinned by "
                         "CHECK rather than defaulted, so the day an integration is "
                         "contracted that CHECK is the line that must change, visibly, "
                         "in a migration")

    reconciliation = rows(f"""
        SELECT state::text, documents::text FROM fiscal.reconciliation(
            '{fx.TENANT}', '{fx.OUTLET_H1}', now() - interval '1 day', now())
         ORDER BY 1;""")
    result = definition("fiscal.reconciliation(uuid, uuid, timestamptz, timestamptz)")
    record("and reconciliation counts by state and never totals",
           "sum(" not in result.lower(),
           f"{reconciliation}. The question a reconciliation answers is which documents "
           f"are stuck, and a single number hides the requested ones that never went "
           f"anywhere")

    limitations = (REPO / "planning" / "M4C_LIMITATIONS.md").read_text(encoding="utf-8")
    record("and what the port does not prove is written down where a reader meets it",
           "one implementation" in limitations and "simulator" in limitations,
           "planning/M4C_LIMITATIONS.md states that no second implementation exists to "
           "have found out whether a real provider's contract fits this shape. The port "
           "is a commitment about where the seam goes, not evidence that the seam is in "
           "the right place")


# ===========================================================================
# 13. Financial ledgers, append-only from the catalog (FR-DAT-008B)
# ===========================================================================

def section_ledgers() -> None:
    print("\n--- 13. Every declared ledger refuses a destructive correction "
          "(FR-DAT-008B) ---")

    declared = rows("""
        SELECT n.nspname || '.' || c.relname
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = ANY (app.financial_schemas()) AND c.relkind = 'r'
           AND app.financial_table_class(n.nspname, c.relname) = 'ledger'
         ORDER BY 1;""", dsn=ADMIN)
    if not declared:
        raise CommandUnreadable(
            "app.financial_table_class() declares no ledger. The check below would then "
            "assert that every member of an empty set carries a trigger")

    # BY THE PROPERTY, NOT BY THE FUNCTION NAME. The first form of this check asked
    # whether each ledger carried app.refuse_financial_mutation() specifically, and
    # reported fourteen of the twenty-seven unguarded — every one of which carries its own
    # refusal, written by the slice that owns it: billing.refuse_ledger_mutation(),
    # cash.refuse_movement_mutation(), and so on. A check that named one implementation
    # was testing which function was used rather than whether the rule holds, and it would
    # have been "fixed" by rewriting five slices to use one function for no reason.
    #
    # What FR-DAT-008B actually requires is that the table REFUSES a destructive
    # correction. So: a row-level BEFORE UPDATE OR DELETE trigger whose function raises.
    # Derived from pg_trigger's own bitmask rather than from a name, so a trigger that
    # fires AFTER, or per statement, or does not raise, does not count.
    unguarded = rows("""
        SELECT n.nspname || '.' || c.relname
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = ANY (app.financial_schemas()) AND c.relkind = 'r'
           AND app.financial_table_class(n.nspname, c.relname) = 'ledger'
           AND NOT EXISTS (
                 SELECT 1 FROM pg_trigger tg
                  JOIN pg_proc f ON f.oid = tg.tgfoid
                  WHERE tg.tgrelid = c.oid AND NOT tg.tgisinternal
                    AND (tg.tgtype & 1) = 1        -- FOR EACH ROW
                    AND (tg.tgtype & 2) = 2        -- BEFORE
                    AND (tg.tgtype & 16) = 16      -- UPDATE
                    AND (tg.tgtype & 8) = 8        -- DELETE
                    AND pg_get_functiondef(f.oid) ~* 'RAISE\\s+EXCEPTION')
         ORDER BY 1;""", dsn=ADMIN)
    record("every table declared a ledger refuses a destructive correction",
           not unguarded,
           f"{len(declared)} declared ledger(s); unguarded: "
           f"{[r[0] for r in unguarded] or 'none'}. Enumerated from the declaration "
           f"rather than from a list, so a financial table a later gate adds fails here "
           f"rather than sliding past — and asked as a property, so a slice that writes "
           f"its own refusal satisfies it")

    # AND NO GRANT MAKES IT MOOT. A trigger that refuses and a grant that never let the
    # caller near it are two locks; either alone is the one somebody removes.
    granted = rows("""
        SELECT c.relname || ' ' || p.privilege_type
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
          JOIN information_schema.table_privileges p
            ON p.table_schema = n.nspname AND p.table_name = c.relname
         WHERE n.nspname = ANY (app.financial_schemas()) AND c.relkind = 'r'
           AND app.financial_table_class(n.nspname, c.relname) = 'ledger'
           AND p.grantee = 'hospitality_app'
           AND p.privilege_type IN ('UPDATE', 'DELETE')
         ORDER BY 1;""", dsn=ADMIN)
    record("and no ledger grants the application role an UPDATE or a DELETE",
           not granted,
           f"{[r[0] for r in granted] or 'none'}. The trigger and the grant fail "
           f"independently, which is what makes removing either one visible")

    unclassified = run(ADMIN, "SELECT app.assert_financial_tables_are_classified();")
    record("and no table in a financial schema is unclassified",
           unclassified.ok,
           unclassified.why() or f"every table in {len(rows('SELECT unnest(app.financial_schemas());', dsn=ADMIN))} "
                                 f"financial schema(s) is a ledger, a projection or "
                                 f"mutable, and somebody has said which")

    # RETENTION CANNOT REACH THEM. Derived from app.financial_schemas() rather than from
    # a list, because 0027's own comment said a list of schemas goes stale on the next
    # migration and it went stale on the next but one.
    schemas = sorted(r[0] for r in rows("SELECT unnest(app.financial_schemas());",
                                        dsn=ADMIN))
    constraint = rows("""
        SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c
         WHERE c.conrelid = 'config.retention_policy'::regclass
           AND c.conname = 'retention_policy_never_targets_financial_ledgers';""",
        dsn=ADMIN)
    expression = constraint[0][0] if constraint else ""
    missing = [s for s in schemas if f"'{s}'" not in expression]
    record("and no retention policy can target a financial schema",
           bool(constraint) and not missing,
           f"schemas app.financial_schemas() names: {schemas}; absent from the "
           f"constraint: {missing or 'none'}. The constraint keeps a literal list "
           f"because a CHECK calling a function is not re-validated when the function "
           f"changes; this is the assertion that keeps the two from drifting")

    swept = run(ADMIN, f"""
        INSERT INTO config.retention_policy
            (tenant_id, target_schema, target_table, action, retain_for)
        VALUES ('{fx.TENANT}', 'report', 'shift_snapshot', 'delete', interval '1 day');""",
        tx=True)
    record("and the refusal is real, not only stated",
           not swept.ok,
           swept.why() or "a retention policy was written against a signed-off metric "
                          "snapshot. A sweep is the one path that deletes rows without "
                          "passing the trigger on the table it deletes from")


# ===========================================================================
# 14. What this slice did NOT build (M5a's boundary)
# ===========================================================================

def section_boundary() -> None:
    print("\n--- 14. No outlet node, no synchronization, no resilient print queue ---")

    queued = rows("""
        SELECT n.nspname || '.' || c.relname || '.' || a.attname
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
         WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
           AND c.relname ~* 'print'
           AND a.attname ~* '(queue|pending|retry|attempts_remaining|next_attempt)'
         ORDER BY 1;""", dsn=ADMIN)
    record("printing has no queue, and that is M5a's to build",
           not queued,
           f"queue-shaped columns on a print table: {[r[0] for r in queued] or 'none'}. "
           f"FR-BIL-017's later_behavior places durable local queueing, retry, restart "
           f"recovery and outage continuity at M5a. What M4-C proves is a print that "
           f"happened, once, and said so")

    sync = rows("""
        SELECT n.nspname || '.' || c.relname
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
           AND c.relname ~* '(^|_)(sync|synchronization|outlet_node|replication)($|_)'
         ORDER BY 1;""", dsn=ADMIN)
    record("and no outlet node or synchronization surface exists",
           not sync,
           f"{[r[0] for r in sync] or 'none'}. FR-RPT-002's later_behavior asks for local "
           f"versus cloud source and staleness at M5a, and a build that showed a "
           f"synchronization status with nothing synchronizing would be showing a "
           f"fabricated one")

    fenced, fenced_terms = fenced_identifier_pattern()
    offending = rows(f"""
        SELECT n.nspname || '.' || c.relname
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind = 'r' AND n.nspname IN ('report', 'docs', 'fiscal')
           AND c.relname ~* '{fenced}'
         ORDER BY 1;""", dsn=ADMIN)
    record("and no table this slice owns names a fenced domain",
           not offending,
           f"{[r[0] for r in offending] or 'none'}. The {fenced_terms} fenced terms "
           f"are read from the package, so a term added to the fence covers this slice "
           f"without anybody editing this file")


# ===========================================================================
# 15. FR-GOV-004: the register audit (the headline of this slice)
# ===========================================================================

def section_register_audit() -> None:
    print("\n--- 15. Every requirement whose gate has landed is delivered or "
          "classified (FR-GOV-004) ---")

    proc = run_command([sys.executable, str(REPO / "tools" / "requirement_coverage.py"),
                        "--logs", str(CONTEXT["log_dir"])], cwd=str(REPO))
    output = proc.stdout + proc.stderr
    record("the register audit runs and accounts for every landed requirement",
           proc.returncode == 0,
           (output.strip().splitlines() or ["(no output)"])[0]
           + ("" if proc.returncode == 0 else
              "\n" + "\n".join(output.strip().splitlines()[-12:])))

    numbers = coverage.audit(CONTEXT["log_dir"])
    record("and its numbers are derived from the package, not typed",
           numbers["landed"] > 0 and not numbers["unclassified"],
           f"{numbers['landed']} requirement(s) whose gate has landed, "
           f"{len(numbers['delivered'])} delivered with evidence, "
           f"{len(numbers['open_entries'])} covered by an open register entry, "
           f"{len(numbers['unaccounted']) - len(numbers['unclassified'])} carrying a "
           f"classification, {len(numbers['unclassified'])} unaccounted: "
           f"{[r['id'] for r in numbers['unclassified']] or 'none'}. The gates come from "
           f"the package's own order and the evidence from this run's logs")

    findings = (REPO / "planning" / "M4_REVIEW_FINDINGS.md")
    record("and what it surfaced across M1 to M3 is published for the review to challenge",
           findings.exists() and "absent" in findings.read_text(encoding="utf-8"),
           f"planning/M4_REVIEW_FINDINGS.md leads with the security requirements the "
           f"audit found ABSENT rather than merely uncited, each with its reasoning, its "
           f"buildability and the test that would close it. A classification is a "
           f"judgement the review may overturn as readily as a fix")

    proc = run_command([sys.executable,
                        str(REPO / "tools" / "generate_review_findings.py"), "--check"],
                       cwd=str(REPO))
    record("and the published findings are a rendering of the audit, not a copy",
           proc.returncode == 0,
           (proc.stdout.strip() or proc.stderr.strip() or "").splitlines()[0]
           if (proc.stdout or proc.stderr) else "")


# ===========================================================================
# 16. The control registry agrees with what this run proved
# ===========================================================================

def section_control_registry() -> None:
    print("\n--- 16. Every control this gate owns is described and proved ---")

    signatures = registry.signatures_for("M4")
    fenced, fenced_terms = fenced_identifier_pattern()
    offending = [s for s in signatures if re.search(fenced, s.lower())]
    record("no M4 failure signature names a fenced domain",
           bool(signatures) and not offending,
           f"{len(signatures)} signature(s) owned by M4; {offending or 'none'} name a "
           f"fenced term. Checked against the package's own {fenced_terms} terms "
           f"programmatically, "
           f"so a term added to the fence covers these without anybody editing a list")

    described = registry.described()
    mine = {k: v for k, v in described.items() if v[2] == "m4c"}
    record("and this slice's controls are in the one registry every document reads from",
           len(mine) == 9,
           f"{sorted(mine)}. NC-M4-005 is the package's; the other eight are this "
           f"slice's own")


# ===========================================================================
# 17. Negative controls: each proved RED with a real defect, then GREEN
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


def section_controls() -> None:
    print("\n--- 17. Negative controls: each proved RED with a real defect, then GREEN ---")

    # ---------------------------------------------------------------- NC-M4-005
    # The packaged font gone from the receipt print path. PLANTED AS THE REAL CASE
    # RATHER THAN AS A BROKEN BINARY: an Arabic receipt rendered through the Ethiopic
    # face alone is a genuine .notdef from a genuine font, and it is the defect this
    # build actually shipped until the third locale was rasterised.
    arabic_document = json.loads(scalar(
        f"SELECT docs.receipt_document('{fx.TENANT}', "
        f"'{CONTEXT['arabic_receipt']}')::text;"))

    def red_font():
        measured = rasterise(
            arabic_document,
            font=str(REPO / "print" / "fonts" / "NotoSansEthiopic-Regular.ttf"))
        uncovered = [c for c in measured.get("coverage", [])
                     if not c["drawnByTheVendoredFont"]]
        return (bool(uncovered),
                f"{len(uncovered)} character(s) the Ethiopic face did not draw: "
                f"{[hex(c['codepoint']) for c in uncovered][:8]}. The check reads the "
                f"BITMAP, per character, and compares against what the platform does "
                f"with a font it cannot find — so this is a real missing glyph and not "
                f"an assertion about a file that is not there")

    def green_font():
        measured = rasterise(arabic_document)
        uncovered = [c for c in measured.get("coverage", [])
                     if not c["drawnByTheVendoredFont"]]
        return (not uncovered,
                f"{len(measured.get('coverage', []))} character(s), none drawn by "
                f"anything but the vendored set. Ethiopic, Arabic and Latin on one "
                f"receipt, each from a face this repository ships and checksums")

    control("NC-M4-005  the packaged Ethiopic font gone from the receipt print path",
            red_font, green_font)

    # ---------------------------------------------------------------- NC-M4C-001
    # One settlement printed as two original receipts. PLANTED ON BOTH LOCKS, because
    # planting on either alone leaves the other holding — and a control that reported red
    # would then be reporting that the lock it did not touch works.
    duplicate_settlement = a_settled_bill()
    duplicate_receipt = a_receipt(duplicate_settlement)
    scalar(f"""
        SELECT docs.record_receipt_print('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{duplicate_receipt}', '{fx.PRINTER_DEVICE}', 'printed',
            repeat('1', 64)::char(64), 256, '{fx.USER_CASHIER}');""")

    trigger_body = definition("docs.refuse_duplicate_receipt_print()")

    def print_it_again():
        return run(APP, f"""
            SELECT docs.record_receipt_print('{fx.TENANT}', '{fx.OUTLET_H1}',
                '{duplicate_receipt}', '{fx.PRINTER_DEVICE}', 'printed',
                repeat('2', 64)::char(64), 256, '{fx.USER_CASHIER}');""",
            tx=True, **CTX)

    def red_duplicate():
        run(ADMIN, "DROP INDEX docs.print_attempt_one_original_per_receipt;")
        replace_function("""
            CREATE OR REPLACE FUNCTION docs.refuse_duplicate_receipt_print()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END; $$;""")
        second = print_it_again()
        return (second.ok,
                "with the unique index dropped and the trigger emptied, a second "
                "ORIGINAL print of one settlement succeeded. That is a customer holding "
                "two records of one payment, and it is two payments as far as anybody "
                "reading them can tell")

    def green_duplicate():
        run(ADMIN, """
            DELETE FROM docs.print_attempt a
             WHERE a.bytes_sha256 = repeat('2', 64)
               AND EXISTS (SELECT 1 FROM docs.printer p
                            WHERE p.id = a.printer_id);""")
        replace_function(trigger_body)
        run(ADMIN, """
            CREATE UNIQUE INDEX print_attempt_one_original_per_receipt
                ON docs.print_attempt (tenant_id, receipt_id) WHERE NOT is_reprint;""")
        second = print_it_again()
        return (second.failed_with("DUPLICATE_RECEIPT_PRINTED",
                                   "print_attempt_one_original_per_receipt"),
                second.why() or "a second original print succeeded after the revert")

    control("NC-M4C-001  one settlement printed as two original receipts",
            red_duplicate, green_duplicate)

    # ---------------------------------------------------------------- NC-M4C-002
    # A bill total line carrying the tip. THE DEFECT IS IN THE COMPOSER, which is where it
    # would really be: docs.issue_receipt() is made to write the bill total as the bill
    # PLUS the tip, exactly as somebody would who thought "total" meant "what they paid".
    # The faithfulness trigger is the lock, so the RED leg removes it too — a control that
    # planted only the composer defect would report red and be reporting that the trigger
    # works, which is not what this control is named for.
    #
    # ITS FIRST FORM INSERTED A SECOND bill_total LINE onto a receipt that did not exist,
    # matched no rows, and reported red for inserting nothing. The run caught it: the red
    # leg passed and the green leg could not fail. Hence the read-back below — a control
    # has to show that its defect did something.
    faithful_body = definition("docs.assert_receipt_is_faithful()")
    issue_body = definition("docs.issue_receipt(uuid, uuid, uuid, text, uuid, integer)")
    MERGED = ("'bill_total', v_order,\n"
              "            docs.wording_for(p_tenant_id, 'bill_total', b.locale),\n"
              "            b.bill_total_minor")
    merging_composer = issue_body.replace(MERGED, MERGED + " + v_tip")
    if merging_composer == issue_body:
        raise CommandUnreadable(
            "the bill_total line could not be found in docs.issue_receipt(). This control "
            "plants its defect in the composer, and a plant that silently changed nothing "
            "would make the control report red for no reason at all")

    def issue_with_a_tip():
        settlement = a_settled_bill(tip_minor=2500)
        issued = run(APP, f"""
            SELECT docs.issue_receipt('{fx.TENANT}', '{fx.OUTLET_H1}',
                '{settlement["bill"]}', 'cash', '{fx.USER_CASHIER}');""",
            tx=True, **CTX)
        return settlement, issued

    def figures_on_the_latest_receipt_for(bill: str) -> list[str]:
        return rows(f"""
            SELECT l.amount_minor::text, r.bill_total_minor::text, r.tip_total_minor::text
              FROM docs.receipt r
              JOIN docs.receipt_line l
                ON l.tenant_id = r.tenant_id AND l.receipt_id = r.id
             WHERE r.tenant_id = '{fx.TENANT}' AND r.bill_id = '{bill}'
               AND l.kind = 'bill_total'
             ORDER BY r.revision DESC LIMIT 1;""")

    def red_merge():
        replace_function(merging_composer)
        replace_function("""
            CREATE OR REPLACE FUNCTION docs.assert_receipt_is_faithful()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END; $$;""")
        settlement, issued = issue_with_a_tip()
        figures = figures_on_the_latest_receipt_for(settlement["bill"])
        line, bill_total, tip_total = figures[0] if figures else ("0", "0", "0")
        return (issued.ok and bool(figures) and int(tip_total) > 0
                and int(line) == int(bill_total) + int(tip_total),
                f"{issued.why() or 'the receipt issued'}; its bill total line reads "
                f"{line} against a bill of {bill_total} and a tip of {tip_total}. On "
                f"paper that is a customer told they owed their own gratuity, and M4-A's "
                f"proof that a tip cannot reach a balance undone where only the customer "
                f"would notice")

    def green_merge():
        # THE COMPOSER IS STILL BROKEN HERE, deliberately. A green leg is not "the defect
        # was removed", it is "the lock catches the defect". Reverting both at once would
        # prove only that correct code passes.
        replace_function(faithful_body)
        _settlement, issued = issue_with_a_tip()
        replace_function(issue_body)
        clean_settlement, clean = issue_with_a_tip()
        clean_figures = figures_on_the_latest_receipt_for(clean_settlement["bill"])
        honest = (bool(clean_figures)
                  and clean_figures[0][0] == clean_figures[0][1])
        return (issued.failed_with("TIP_MERGED_ON_RECEIPT") and clean.ok and honest,
                (issued.why()
                 or f"a merged bill total was accepted with the trigger restored "
                    f"(the issue reported ok={issued.ok})")
                + f". The diagnostic names the tip only after VERIFYING that the excess "
                  f"is exactly the tip, which is the shape M4-A's NC-M4A-006 had to be "
                  f"corrected into. The composer was then reverted and a clean receipt "
                  f"issued: {clean_figures or 'no bill total line'}")

    control("NC-M4C-002  a bill total line on a receipt carrying the tip",
            red_merge, green_merge)

    # ---------------------------------------------------------------- NC-M4C-003
    # A non-English receipt falling back to English on paper. THE DEFECT IS THE ABSENCE
    # OF AN APPROVED TRANSLATION, which is what actually happens: somebody adds a line
    # kind, nobody translates it, and the receipt prints half in English.
    locale_body = definition("docs.assert_receipt_is_complete_in_its_locale()")
    withdrawn = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
        -- WITHDRAWN THE WAY M2-A WITHDRAWS ONE. A draft carries no reviewer and no
        -- approval time — the CHECK on menu.translation says so — and setting only the
        -- state would be asking the schema to hold a row that means two things at once.
        UPDATE menu.translation
           SET state = 'draft', reviewed_by_user_id = NULL, approved_at = NULL
         WHERE tenant_id = '{fx.TENANT}' AND entity = 'receipt_line_wording'
           AND locale = 'am' AND entity_id = '{fx.WORDING_TIP}';""", tx=True)
    if not withdrawn.ok:
        raise ProbeFailed("withdrawing an approved translation", withdrawn.err)

    def issue_an_amharic_receipt():
        settlement = a_settled_bill("am")
        return run(APP, f"""
            SELECT docs.issue_receipt('{fx.TENANT}', '{fx.OUTLET_H1}',
                '{settlement["bill"]}', 'cash', '{fx.USER_CASHIER}');""",
            tx=True, **CTX)

    def red_locale():
        replace_function("""
            CREATE OR REPLACE FUNCTION docs.assert_receipt_is_complete_in_its_locale()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END; $$;""")
        issued = issue_an_amharic_receipt()
        return (issued.ok,
                "with the completeness trigger emptied and one approved Amharic "
                "translation withdrawn, an Amharic receipt was issued carrying the "
                "English source text on its tip line. On a screen a missing string is a "
                "bad afternoon; on paper it is a document the customer cannot read and "
                "nobody can re-render")

    def green_locale():
        replace_function(locale_body)
        issued = issue_an_amharic_receipt()
        restored = run(ADMIN, f"""
            SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
            UPDATE menu.translation
               SET state = 'approved', reviewed_by_user_id = '{fx.USER_MANAGER}',
                   approved_at = now()
             WHERE tenant_id = '{fx.TENANT}' AND entity = 'receipt_line_wording'
               AND locale = 'am' AND entity_id = '{fx.WORDING_TIP}';""", tx=True)
        if not restored.ok:
            raise ProbeFailed("restoring the approved translation", restored.err)
        return (issued.failed_with("RECEIPT_INCOMPLETE_IN_LOCALE"),
                issued.why() or "a half-English Amharic receipt was issued after the "
                                "revert")

    control("NC-M4C-003  a non-English receipt falling back to English on paper",
            red_locale, green_locale)

    # ---------------------------------------------------------------- NC-M4C-004
    # A summary of an empty window reported as a figure. Planted in the CONSTRUCTOR,
    # which is the only door into a reading — a defect in one metric's arithmetic would
    # be caught by the constructor, so the control has to break the constructor to show
    # what it is holding.
    reading_body = definition(
        "report.reading(report.metric_key, bigint, char, bigint, timestamptz)")

    def fabricate():
        return run(APP, """
            SELECT report.reading('kitchen_preparation_seconds_p50', 0, NULL, 0, now());""",
            tx=True, **CTX)

    def red_fabricated():
        replace_function("""
            CREATE OR REPLACE FUNCTION report.reading(
                p_metric report.metric_key, p_value bigint, p_currency_code char(3),
                p_observation_count bigint, p_latest_source_row_at timestamptz)
            RETURNS report.reading LANGUAGE plpgsql STABLE AS $$
            DECLARE r report.reading;
            BEGIN
                r.metric := p_metric;
                r.unit := (SELECT unit FROM report.metric WHERE key = p_metric);
                r.value := p_value;
                r.currency_code := p_currency_code;
                r.observation_count := p_observation_count;
                r.source := (SELECT source_relation FROM report.metric WHERE key = p_metric);
                r.computed_at := now();
                r.latest_source_row_at := p_latest_source_row_at;
                RETURN r;
            END; $$;""")
        offered = fabricate()
        return (offered.ok,
                "with the constructor's honesty checks removed, a median preparation "
                "time over ZERO tickets was reported as 0 seconds. A manager reading "
                "that would conclude the kitchen was instant, and FR-UX-014 is the rule "
                "against exactly this — not against showing zero, but against showing a "
                "figure where there is nothing to summarise")

    def green_fabricated():
        replace_function(reading_body)
        offered = fabricate()
        return (offered.failed_with("FABRICATED_METRIC"),
                offered.why() or "an invented median was accepted after the revert")

    control("NC-M4C-004  a summary of an empty window reported as a figure",
            red_fabricated, green_fabricated)

    # ---------------------------------------------------------------- NC-M4C-005
    # A recomputation writing over a signed-off shift result. PLANTED AS THE REAL DEFECT:
    # the recomputation function is changed to do what a well-meaning author would do —
    # update the snapshot to the current answer — and the ledger trigger is what has to
    # stop it.
    recompute_body = definition("report.recompute_shift_snapshot(uuid, uuid, uuid)")
    shift = CONTEXT["snapshot_shift"]

    def red_rewrite():
        # BOTH LOCKS, because either alone holds and a control that planted one would be
        # reporting that the other works. The trigger comes off and the function is
        # replaced with the one a well-meaning author would write: update the snapshot to
        # today's answer.
        run(ADMIN, "DROP TRIGGER shift_snapshot_value_is_append_only "
                   "ON report.shift_snapshot_value;")
        replace_function("""
            CREATE OR REPLACE FUNCTION report.recompute_shift_snapshot(
                p_tenant_id uuid, p_shift_id uuid, p_actor_user_id uuid)
            RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER AS $$
            DECLARE s report.shift_snapshot%ROWTYPE;
            BEGIN
                SELECT * INTO s FROM report.shift_snapshot
                 WHERE tenant_id = p_tenant_id AND shift_id = p_shift_id;
                UPDATE report.shift_snapshot_value v
                   SET value = n.value, observation_count = n.observations
                  FROM (SELECT (r).metric AS metric, (r).value AS value,
                               (r).observation_count AS observations
                          FROM report.metric_values(s.tenant_id, s.outlet_id,
                                 s.window_from, s.window_to, s.currency_code) r) n
                 WHERE v.tenant_id = s.tenant_id AND v.snapshot_id = s.id
                   AND v.metric = n.metric;
                RETURN s.id;
            END; $$;""")
        before = CONTEXT["signed_tip_reversals"]
        # UNDER THE TENANT'S CONTEXT. The first version of this leg called the planted
        # function with no request context, and FORCE row level security hid the snapshot
        # from it: the UPDATE matched nothing, the figure did not move, and the control
        # reported that a rewrite had failed to happen. A control that plants a defect
        # and then cannot reach the row is not a red leg.
        rewritten = run(ADMIN, f"""
            SELECT report.recompute_shift_snapshot('{fx.TENANT}', '{shift}',
                                                   '{fx.USER_FINANCE_MANAGER}');""",
            **CTX)
        if not rewritten.ok:
            raise ProbeFailed("the planted recomputation", rewritten.err)
        after = scalar(f"""
            SELECT coalesce(v.value::text, 'null') FROM report.shift_snapshot_value v
              JOIN report.shift_snapshot s
                ON s.tenant_id = v.tenant_id AND s.id = v.snapshot_id
             WHERE s.shift_id = '{shift}' AND v.metric = 'tip_reversals_minor';""")
        return (after != before,
                f"with the append-only trigger dropped and the recomputation writing "
                f"back, the signed-off tip_reversals_minor moved from {before} to "
                f"{after}. Nobody was told: the shift still reads as verified, by the "
                f"same person, with a different number under their name — which is what "
                f"the word SILENTLY in FR-RPT-014 is about")

    def green_rewrite():
        # THE FIGURE IS PUT BACK FIRST, while the trigger is still off. A green leg that
        # left the snapshot holding the rewritten number would leave every later check in
        # this suite asserting against a document this control corrupted.
        restored = run(ADMIN, f"""
            UPDATE report.shift_snapshot_value v
               SET value = {CONTEXT["signed_tip_reversals"]}
              FROM report.shift_snapshot s
             WHERE s.tenant_id = v.tenant_id AND s.id = v.snapshot_id
               AND s.shift_id = '{shift}' AND v.metric = 'tip_reversals_minor';""",
            **CTX)
        if not restored.ok:
            raise ProbeFailed("restoring the snapshot after NC-M4C-005", restored.err)
        run(ADMIN, """
            CREATE TRIGGER shift_snapshot_value_is_append_only
                BEFORE UPDATE OR DELETE ON report.shift_snapshot_value
                FOR EACH ROW EXECUTE FUNCTION app.refuse_financial_mutation();""")

        # THE DEFECTIVE FUNCTION IS STILL IN PLACE HERE, deliberately: the green leg is
        # not "the defect was removed", it is "the lock catches the defect".
        blocked = run(ADMIN, f"""
            SELECT report.recompute_shift_snapshot('{fx.TENANT}', '{shift}',
                                                   '{fx.USER_FINANCE_MANAGER}');""",
            tx=True, **CTX)
        replace_function(recompute_body)
        again = scalar(f"""
            SELECT report.recompute_shift_snapshot('{fx.TENANT}', '{shift}',
                                                   '{fx.USER_FINANCE_MANAGER}');""")
        return (blocked.failed_with("LEDGER_ROW_DELETED_NOT_REVERSED") and bool(again),
                (blocked.why() or "the rewriting recomputation succeeded with the "
                                  "trigger restored")
                + f". The real function was then put back and recomputation "
                  f"{again[:8]} recorded what it found instead of writing it over the "
                  f"snapshot")

    control("NC-M4C-005  a recomputation writing over a signed-off shift result",
            red_rewrite, green_rewrite)

    # ---------------------------------------------------------------- NC-M4C-006
    # Money on a bill that no sales classification claims. PLANTED AS THE DEFAULT
    # SOMEBODY WOULD ADD: the classifier is given an ELSE branch returning item_sales,
    # which is what a well-meaning author writes to stop an exception, and the report
    # then balances while being wrong.
    classifier_body = definition(
        "report.classify_component(ordering.charge_kind, ordering.charge_source_kind)")

    def classify_an_unknown_pair():
        return run(APP, """
            SELECT report.classify_component('fee'::ordering.charge_kind,
                                             'menu_price'::ordering.charge_source_kind);""",
            tx=True, **CTX)

    def red_unclassified():
        replace_function("""
            CREATE OR REPLACE FUNCTION report.classify_component(
                p_kind ordering.charge_kind, p_source_kind ordering.charge_source_kind)
            RETURNS report.sales_classification LANGUAGE plpgsql IMMUTABLE AS $$
            BEGIN
                IF p_source_kind = 'service_configuration' THEN RETURN 'service_charges'; END IF;
                CASE p_kind
                    WHEN 'item_subtotal' THEN RETURN 'item_sales';
                    WHEN 'discount'      THEN RETURN 'discounts';
                    WHEN 'tax'           THEN RETURN 'taxes';
                    ELSE RETURN 'item_sales';
                END CASE;
            END; $$;""")
        answered = classify_an_unknown_pair()
        return (answered.ok and (answered.scalar or "").strip() == "item_sales",
                f"with a default branch added, a fee from a source nothing recognises was "
                f"reported as {(answered.scalar or '').strip()!r}. The report would "
                f"BALANCE and be wrong: the money is in a classification it does not "
                f"belong to, and the total nobody would question is the total that hides "
                f"it")

    def green_unclassified():
        replace_function(classifier_body)
        answered = classify_an_unknown_pair()
        return (answered.failed_with("SALES_COMPONENT_UNCLASSIFIED"),
                answered.why() or "an unrecognised charge source was still classified "
                                  "after the revert. A later gate adding one has to come "
                                  "here and say where it goes")

    control("NC-M4C-006  money on a bill that no sales classification claims",
            red_unclassified, green_unclassified)

    # ---------------------------------------------------------------- NC-M4C-007
    # A counter order that can name no POS terminal. Planted on the constraint trigger,
    # which is the lock; the route calling pos.record_counter_order() is the other half,
    # and M4-A's NC-M4A-007 already proves there is no second order path for one to hide
    # behind.
    counter_trigger = definition("ordering.assert_counter_order_names_its_terminal()")

    def a_counter_order_naming_nobody():
        session = fx.m4a.fresh_occupancy(fx.m4a.COUNTER_NODE)
        guest = fx.m4a.guest_on(session)
        cart = fx.m4a.cart_with(session, guest, ((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 1),))
        view = preview(cart, "en", "counter")
        return run(APP, f"""
            SELECT ordering.submit_order(
                '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', '{idem("nc007")}',
                decode('{view["pricing_digest"]}', 'hex'), {view["total_amount_minor"]},
                'en', gen_random_uuid(), gen_random_uuid(), 'counter',
                '{fx.USER}', NULL, false, '[]'::jsonb, '[]'::jsonb, 'counter');""",
            tx=True, **CTX)

    def red_counter():
        replace_function("""
            CREATE OR REPLACE FUNCTION ordering.assert_counter_order_names_its_terminal()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END; $$;""")
        placed = a_counter_order_naming_nobody()
        return (placed.ok,
                "with the constraint trigger emptied, an order marked 'counter' was "
                "accepted from a session on no device at all. FR-POS-003B says a counter "
                "order is created AT THE POS TERMINAL, and an order that claims the "
                "counter and can name no terminal is a channel label rather than a place")

    def green_counter():
        replace_function(counter_trigger)
        placed = a_counter_order_naming_nobody()
        return (placed.failed_with("COUNTER_ORDER_WITHOUT_A_TERMINAL"),
                placed.why() or "a terminal-less counter order was accepted after the "
                                "revert")

    control("NC-M4C-007  a counter order that can name no POS terminal",
            red_counter, green_counter)

    # ---------------------------------------------------------------- NC-M4C-008
    # A customer receipt printed on a printer nobody tested. The precondition lives in
    # docs.record_receipt_print(), and it is the only thing that function adds beyond the
    # INSERT — so removing it is exactly the defect a reviewer would miss.
    print_body = definition(
        "docs.record_receipt_print(uuid, uuid, uuid, uuid, docs.print_outcome, char, "
        "integer, uuid, boolean, uuid, text, text)")

    def print_on_the_untested_one():
        settlement = a_settled_bill()
        receipt = a_receipt(settlement)
        return run(APP, f"""
            SELECT docs.record_receipt_print('{fx.TENANT}', '{fx.OUTLET_H1}',
                '{receipt}', '{fx.PRINTER_UNTESTED}', 'printed',
                repeat('3', 64)::char(64), 128, '{fx.USER_CASHIER}');""",
            tx=True, **CTX)

    def red_untested():
        replace_function(print_body.replace(
            "IF NOT docs.printer_has_passed_a_test(p_tenant_id, p_printer_id) THEN",
            "IF false THEN"))
        printed = print_on_the_untested_one()
        return (printed.ok,
                "with the precondition removed, a customer receipt was printed on a "
                "printer that has never successfully printed anything. FR-CFG-001D says "
                "setup registers AND TESTS, and a setup screen reporting a printer ready "
                "because a row exists is FR-INT-011's most expensive kind of true "
                "statement")

    def green_untested():
        replace_function(print_body)
        printed = print_on_the_untested_one()
        return (printed.failed_with("PRINTER_NEVER_TESTED"),
                printed.why() or "an untested printer printed after the revert")

    control("NC-M4C-008  a customer receipt printed on a printer nobody tested",
            red_untested, green_untested)


# ===========================================================================
# Setting the stage: the settlements, the receipts, and one signed-off shift
# ===========================================================================

def establish() -> None:
    """The facts every section reads. Built once, through the delivered writers.

    THE SHIFT IS SIGNED OFF LAST, and after the receipts, because the snapshot is taken
    at the instant of sign-off and must have something to summarise. A snapshot over an
    empty window would make section 4 assert that nothing was rewritten, truthfully and
    uselessly.
    """
    # THE SHIFT IS OPENED FIRST, and that is not ordering for its own sake: the snapshot
    # summarises the window between opening and sign-off, and a shift opened after the
    # settlements would snapshot an empty evening. A snapshot over nothing would let
    # section 4 report that nothing was rewritten — truthfully, and about no figures.
    shift = scalar(f"""
        SELECT cash.open_shift('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{fx.m4b.TERMINAL_DEVICE}', '{fx.USER_CASHIER}', 'ETB', 100000);""")
    CONTEXT["snapshot_shift"] = shift

    english = a_settled_bill()
    CONTEXT["english_settlement"] = english
    CONTEXT["english_receipt"] = a_receipt(english)

    CONTEXT["no_tip_receipt"] = CONTEXT["english_receipt"]

    tipped = a_settled_bill(tip_minor=3000)
    CONTEXT["tipped_settlement"] = tipped
    CONTEXT["tipped_receipt"] = a_receipt(tipped)

    amharic = a_settled_bill("am", tip_minor=1500)
    CONTEXT["amharic_settlement"] = amharic
    CONTEXT["amharic_receipt"] = a_receipt(amharic)

    arabic = a_settled_bill("ar", tip_minor=1200)
    CONTEXT["arabic_settlement"] = arabic
    CONTEXT["arabic_receipt"] = a_receipt(arabic)

    # A COUNTER ORDER AT A REAL TILL, and a guest's QR order beside it so that section 10
    # can prove the terminal record refuses the one that was not entered at a counter.
    till_session = fx.m4a.session_at_the_counter_terminal()
    CONTEXT["counter_session"] = till_session
    counter_session_id = fx.m4a.fresh_occupancy(fx.m4a.COUNTER_NODE)
    guest = fx.m4a.guest_on(counter_session_id)
    cart = fx.m4a.cart_with(counter_session_id, guest,
                            ((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 1),))
    view = preview(cart, "en", "counter")
    placed = run(APP, f"""
        WITH placed AS (
            SELECT ordering.submit_order(
                '{fx.TENANT}', '{fx.OUTLET_H1}', '{cart}', '{idem("counter")}',
                decode('{view["pricing_digest"]}', 'hex'), {view["total_amount_minor"]},
                'en', gen_random_uuid(), gen_random_uuid(), 'counter',
                '{fx.USER}', NULL, false, '[]'::jsonb, '[]'::jsonb, 'counter') AS id)
        SELECT placed.id
          FROM placed,
               LATERAL (SELECT pos.record_counter_order(
                          '{fx.TENANT}', '{fx.OUTLET_H1}', placed.id, '{fx.USER}')) AS bound;
        """, tx=True, session=till_session, **CTX)
    if not placed.ok:
        raise ProbeFailed("a counter order at the till", placed.err)
    CONTEXT["counter_order"] = (placed.scalar or "").strip()
    CONTEXT["qr_order"] = english["order"]

    # THE DRAWER IS COUNTED, SUBMITTED AND VERIFIED by somebody who is not the cashier —
    # which is the sign-off, and the instant the snapshot is taken.
    #
    # THE SNAKE_CASE KEYS THE FUNCTION READS, not the camelCase the HTTP route accepts.
    # M4-B's tally_for() produces the route's shape because M4-B counts through the route;
    # this suite counts through the function, and the two vocabularies meet at the route
    # rather than in the database.
    tally = [{"denomination_minor": row["denominationMinor"],
              "piece_count": row["pieceCount"]}
             for row in fx.m4b.tally_for(100000)]
    counted = run(APP, f"""
        SELECT cash.record_count('{fx.TENANT}', '{fx.OUTLET_H1}', '{shift}', 'closing',
            '{json.dumps(tally)}'::jsonb, '{fx.USER_CASHIER}');""",
        tx=True, **CTX)
    if not counted.ok:
        raise ProbeFailed("the closing count", counted.err)

    submitted = run(APP, f"""
        SELECT cash.transition_shift('{fx.TENANT}', '{shift}', 'submitted',
                                     '{fx.USER_CASHIER}');""", tx=True, **CTX)
    if not submitted.ok:
        raise ProbeFailed("submitting the shift", submitted.err)

    verifier_session, _token = fx.staff_session(fx.USER_FINANCE_MANAGER)
    verified = run(APP, f"""
        SELECT cash.transition_shift('{fx.TENANT}', '{shift}', 'verified',
                                     '{fx.USER_FINANCE_MANAGER}');""",
        tx=True, session=verifier_session, **CTX)
    if not verified.ok:
        raise ProbeFailed("verifying the shift", verified.err)

    signed = run(APP, f"""
        SELECT coalesce(v.value::text, 'null') FROM report.shift_snapshot_value v
          JOIN report.shift_snapshot s ON s.tenant_id = v.tenant_id AND s.id = v.snapshot_id
         WHERE s.shift_id = '{shift}' AND v.metric = 'tip_reversals_minor';""", **CTX)
    if not signed.ok or not (signed.scalar or "").strip():
        raise ProbeFailed(
            "reading the signed-off figure",
            signed.err or "the snapshot carries no tip_reversals_minor row, so section 5 "
                          "would have nothing to compare a recomputation against")
    CONTEXT["signed_tip_reversals"] = (signed.scalar or "").strip()


def main() -> int:
    print("M4-C verification — receipts, the printer path, reporting, the register audit")
    print("real compiled service, real process, real database, real rasteriser")

    fx.seed()

    sync_and_build()
    service = Service(os.environ["M1A_APP_DSN"])
    if not service.start():
        print(f"FAIL SERVICE_DID_NOT_START\n{service.logs()[-2000:]}")
        return 1

    CONTEXT["service"] = service
    CONTEXT["base_url"] = f"http://127.0.0.1:{service.port}"
    CONTEXT["restart"] = service.restart
    CONTEXT["workspace"] = Path(
        os.environ.get("M1D_WORKSPACE", str(Path(tempfile.gettempdir()) / "m1d-workspace")))
    CONTEXT["log_dir"] = Path(os.environ.get("M4C_LOG_DIR", str(SCRATCH / "logs")))

    try:
        _manager_session, manager_token = fx.staff_session(fx.USER_FINANCE_MANAGER)
        CONTEXT["manager_token"] = manager_token

        establish()

        section_catalog()
        section_readings()
        section_sales()
        section_snapshot()
        section_recomputation()
        section_exports_and_dashboards()
        section_receipt()
        section_printer()
        section_preview()
        section_counter()
        section_ethiopic_on_the_printer()
        section_fiscal()
        section_ledgers()
        section_boundary()
        section_control_registry()
        section_controls()
        section_register_audit()
    except (CommandUnreadable, ProbeFailed, coverage.CoverageUnreadable) as error:
        # FAIL CLOSED, for the reason every suite before this one records: a suite that
        # cannot load its rules, cannot read a definition, or finds the set it was going
        # to assert over empty must STOP rather than continue on a default. A sentinel is
        # not a pass.
        print(f"\nFAIL M4C_VERIFICATION_UNUSABLE: {error}")
        return 1
    finally:
        service.stop()

    failed = [(name, detail) for name, ok, detail, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")

    print("\nM4-C summary")
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}   (read off a raster or a browser)")
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
        print("FAIL M4C_VERIFICATION")
        return 1
    print("PASS M4C_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
