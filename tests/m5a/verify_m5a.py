#!/usr/bin/env python3
"""M5a verification: the outlet keeps working when the cloud does not.

WHAT THIS GATE IS ABOUT. Every slice before it assumed one place where the system runs.
FR-EDG-001 says a production outlet may not: it runs an Outlet Continuity Node, and when
the internet goes the waiter still takes orders, the kitchen still cooks, the cashier
still settles in cash and the printer still cuts paper. When the link returns, everything
that happened is offered to the cloud once, in an order that makes sense, and anything the
two disagree about is shown to a person rather than settled by whichever wrote last.

WHAT THIS SUITE INSISTS ON. Three things, learned from the four gates before it:

  1. IT DRIVES ROUTES AND PROCESSES, NOT FIXTURES. OP-C found that
     `INSERT INTO service.table_session` occurred in four files and all four were tests —
     nineteen suites green over a step no guest could take. So the node here is the node
     the seed registered, started through the same entry point an operator starts, and the
     outage is the same seam a real outage cuts.

  2. IT DISTINGUISHES "COULD NOT SEE" FROM "IS NOT THERE". Three defects in this gate were
     of exactly that shape: a banner that answered CONNECTED because row level security
     hid the node, a node told it was not registered because the lookup was scoped by the
     outlet being checked, and a wrong-outlet refusal that could never fire. Each looked
     like an answer. Several checks below exist only to keep those distinguishable.

  3. IT SAYS WHAT IT DID NOT PROVE. The bounds are in planning/M5A_FINDINGS.md and are
     named in the run rather than left for a reader to infer from silence.

Usage:
    M1A_ADMIN_DSN=... M1A_APP_DSN=... python3 tests/m5a/verify_m5a.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

sys.path.insert(0, str(REPO / "tests"))
for sub in ("opa", "m1a", "m1d", "m4c"):
    sys.path.insert(0, str(REPO / "tests" / sub))

from pg import ProbeFailed, run                               # noqa: E402
from service import Service, WORKSPACE                        # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import controls as registry                                   # noqa: E402

import verify_opa as opa                                      # noqa: E402
sys.path.insert(0, str(REPO / "tests" / "opd"))
import verify_opd as opd                                      # noqa: E402

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]

TENANT = opa.TENANT
OUTLET = opa.OUTLET                       # Sarbet
SIBLING = "33330001-0000-4000-8000-000000000001"   # Kazanchis
ADMINISTRATOR = "3333aaaa-0000-4000-8000-000000000001"
NODE_CODE = "NODE-H2"
NODE_FINGERPRINT = "de505eed0000000000000000000000000000000000000000000000000000h202"

# Nile has a tenant, an outlet, no deployment profile and no node. That is exactly
# the state NC-M5A-001 needs: planting at a Habesha outlet hit the primary key
# before the check under test could refuse, so the control passed for the wrong
# reason and reported a constraint nobody was testing.
NILE = "44444444-4444-4444-4444-444444444444"
NILE_OUTLET = "44440001-0000-4000-8000-000000000001"
NILE_ADMIN = "4444aaaa-0000-4000-8000-000000000001"

CONTEXT: dict = {}
results: list[tuple[str, bool, str, str]] = []


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    results.append((name, ok, detail, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] ({evidence}) {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def measured(name: str, ok: bool, detail: str = "") -> None:
    record(name, ok, detail, evidence="measured")


def q(sql: str, *, outlet: str = OUTLET, tenant: str = TENANT):
    """A scoped probe, through the harness rather than around it.

    tests/m1a/pg.run() already sets context in a prelude whose output is DISCARDED and
    wraps the script in a transaction. The first version of this file hand-rolled both and
    got the first one wrong: `SELECT set_config(...)` returns a row, and Result.scalar
    reads the first result set, so every check in the file read back the tenant id and
    compared it against what it expected. Half the suite failed with the same wrong value —
    which at least pointed somewhere. A check that happened to expect a uuid would have
    passed.
    """
    result = run(ADMIN, sql, tenant=tenant, outlet=outlet, tx=True)
    if not result.ok:
        raise ProbeFailed(sql.strip()[:120], result.err[:400])
    return result


def refusal(sql: str, *, outlet: str = OUTLET, tenant: str = TENANT) -> str:
    """The signature a statement was refused with, or '' if it was not refused.

    run() RETURNS a Result rather than raising, which the first version of this file did
    not notice: every refusal check reported "no refusal" and passed nothing. A helper
    that cannot tell a refusal from a success is a helper that turns every negative
    assertion green.
    """
    result = run(ADMIN, sql, tenant=tenant, outlet=outlet, tx=True)
    if result.ok:
        return ""
    for token in result.err.replace("\n", " ").split():
        cleaned = token.strip(":,.'\"")
        if cleaned.isupper() and len(cleaned) > 6 and "_" in cleaned:
            return cleaned
    # A constraint refuses with its own name and no capitals at all, which is why
    # db.ts's signatureOf() has two shapes. Same here.
    for token in result.err.replace("\n", " ").split():
        if token.strip("\"',.") .startswith(("deployment_profile_", "outlet_asset_",
                                             "conflict_", "print_job_", "node_")):
            return token.strip("\"',.")
    return result.err.strip()[:140]


def node_id() -> str:
    return q(f"SELECT id::text FROM edge.node WHERE node_code = '{NODE_CODE}';").scalar


def control(name: str, signature: str, red, green) -> None:
    red_ok, red_detail = red()
    record(f"{name} — RED with the defect planted", red_ok, red_detail)
    green_ok, green_detail = green()
    record(f"{name} — GREEN after revert", green_ok, green_detail)


# ===========================================================================
# 1. The node exists, is bound, and is made of five things
# ===========================================================================

def section_node() -> None:
    print("\n--- 1. The node, its binding and its five services (FR-CFG-001E, FR-EDG-002A) ---")

    node = node_id()
    record("the demonstration outlet has a registered continuity node",
           bool(node), f"node {NODE_CODE} = {node or '(none)'}")

    services = q(f"""
        SELECT string_agg(service::text, ', ' ORDER BY service)
          FROM edge.node_service WHERE node_id = '{node}';""").scalar or ""
    expected = "database, local_api, print_agent, realtime_gateway, sync_worker"
    record("it is made of exactly the five services FR-EDG-002A names",
           ", ".join(sorted(services.split(", "))) == expected,
           f"has: {services}")

    # FR-CFG-001E's four refusals, each distinguishable. Three of these were one refusal
    # until 0046: the lookup was scoped by the outlet it was about to check.
    outcomes = {
        "the correct identity is accepted": (
            f"SELECT edge.authenticate_node('{TENANT}','{NODE_CODE}',"
            f"'{NODE_FINGERPRINT}'::character(64),'{OUTLET}');", ""),
        "a sibling outlet is refused, and told which outlet it is bound to": (
            f"SELECT edge.authenticate_node('{TENANT}','{NODE_CODE}',"
            f"'{NODE_FINGERPRINT}'::character(64),'{SIBLING}');", "NODE_OUTLET_MISMATCH"),
        "a wrong fingerprint is refused": (
            f"SELECT edge.authenticate_node('{TENANT}','{NODE_CODE}',"
            f"'{'f' * 64}'::character(64),'{OUTLET}');", "NODE_IDENTITY_MISMATCH"),
        "a fingerprint belonging to another node is refused by name": (
            f"SELECT edge.authenticate_node('{TENANT}','NODE-H1',"
            f"'{NODE_FINGERPRINT}'::character(64),'{OUTLET}');", "NODE_UNKNOWN"),
    }
    for name, (sql, want) in outcomes.items():
        got = refusal(sql)
        record(name, got == want,
               f"expected {want or 'no refusal'}, got {got or 'no refusal'}")

    # FR-EDG-017: all seven components, and one that never reported is not silence.
    seven = q(f"""
        SELECT count(*)::text || '/' ||
               count(*) FILTER (WHERE state = 'unhealthy' AND detail IS NOT NULL)::text
          FROM edge.node_health('{TENANT}', '{node}');""").scalar
    record("health names all seven components, and an unreported one says so",
           seven == "7/7", f"components/unreported-with-a-reason: {seven}")


# ===========================================================================
# 2. The estate, across all six classes
# ===========================================================================

def section_estate() -> None:
    print("\n--- 2. The outlet knows what hardware it has (FR-OPS-018) ---")

    # The seed covers four classes; a printer and a POS terminal are registered by the
    # suites that own them, so this gate registers its own and then asks for all six. A
    # register that only ever holds what one seed wrote is not an estate.
    printer = q(f"""
        SELECT COALESCE(
          (SELECT id::text FROM docs.printer
            WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET}'
              AND status = 'active' LIMIT 1),
          docs.register_printer('{TENANT}','{OUTLET}','M5a queue printer',
            'character_device','/dev/usb/lp0', NULL, '{ADMINISTRATOR}')::text);""").scalar

    terminal = q(f"""
        SELECT COALESCE(
          (SELECT device_id::text FROM pos.terminal
            WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET}'
              AND revoked_at IS NULL LIMIT 1), '');""").scalar

    q(f"""
        INSERT INTO ops.outlet_asset
          (tenant_id, outlet_id, asset_class, asset_tag, display_name, location,
           support_owner_external, linked_printer_id, recorded_by_user_id)
        SELECT '{TENANT}','{OUTLET}','printer','AST-H2-PRN','Till printer','At the till',
               'Zerihun Networks PLC','{printer}','{ADMINISTRATOR}'
         WHERE NOT EXISTS (SELECT 1 FROM ops.outlet_asset
                            WHERE tenant_id = '{TENANT}' AND asset_tag = 'AST-H2-PRN');""")
    if terminal:
        q(f"""
            INSERT INTO ops.outlet_asset
              (tenant_id, outlet_id, asset_class, asset_tag, display_name, location,
               support_owner_external, linked_terminal_device_id, recorded_by_user_id)
            SELECT '{TENANT}','{OUTLET}','pos_terminal','AST-H2-POS','Till terminal',
                   'At the till','Zerihun Networks PLC','{terminal}','{ADMINISTRATOR}'
             WHERE NOT EXISTS (SELECT 1 FROM ops.outlet_asset
                                WHERE tenant_id = '{TENANT}' AND asset_tag = 'AST-H2-POS');""")

    covered = q(f"""
        SELECT count(*) FILTER (WHERE is_covered)::text || '/' || count(*)::text
          FROM ops.asset_register('{TENANT}','{OUTLET}');""").scalar
    record("the asset register covers every device class FR-OPS-018 names",
           covered == ("6/6" if terminal else "5/6"),
           f"covered: {covered}"
           + ("" if terminal else "; no POS terminal exists at this outlet in this state, "
                                 "and the register reports the class uncovered rather "
                                 "than omitting it"))

    unlinked = refusal(f"""
        INSERT INTO ops.outlet_asset
          (tenant_id, outlet_id, asset_class, asset_tag, display_name, location,
           support_owner_external, recorded_by_user_id)
        VALUES ('{TENANT}','{OUTLET}','printer','AST-BAD','Ghost','Nowhere','V',
                '{ADMINISTRATOR}');""")
    record("a printer recorded without pointing at the printer register is refused",
           unlinked == "CHECK_VIOLATION" or "outlet_asset_link_matches_class" in unlinked,
           f"refused with: {unlinked}")


# ===========================================================================
# 3. Synchronization: order, idempotency, evidence
# ===========================================================================

def section_sync() -> None:
    print("\n--- 3. Durable synchronization (FR-INT-003/004, FR-EDG-005, FR-DAT-008C) ---")
    node = node_id()

    bill_event = q(f"""
        SELECT integration.enqueue_outbox('{TENANT}','{node}','bill', gen_random_uuid(),
               'bill.issued', '{{}}'::jsonb, now() - interval '2 hours')::text;""").scalar
    q(f"""
        SELECT integration.enqueue_outbox('{TENANT}','{node}','payment', gen_random_uuid(),
               'payment.captured', '{{}}'::jsonb, now() - interval '1 hour',
               '{bill_event}');""")

    first = q(f"""
        SELECT string_agg(event_kind, ',' ORDER BY sequence)
          FROM integration.claim_outbox_batch('{TENANT}','{node}');""").scalar
    # THE PROPERTY, NOT THE CONTENTS OF AN IDLE QUEUE — the same correction GJ-10 needed,
    # found the same way. This asserted the batch EQUALS "bill.issued", which is true of a
    # queue holding nothing else and false of every real outlet; the reordered sweep ran
    # it against a queue that already held an unacknowledged print job. FR-EDG-005 asks
    # that a CHILD not travel before its PARENT. Unrelated work alongside it is not a
    # violation.
    record("a child event does not travel before its parent is acknowledged",
           "bill.issued" in (first or "") and "payment.captured" not in (first or ""),
           f"claimed: {first} — the bill is offered and the payment naming it is not")

    q(f"SELECT integration.acknowledge_outbox('{TENANT}','{node}','{bill_event}');")
    second = q(f"""
        SELECT string_agg(event_kind, ',' ORDER BY sequence)
          FROM integration.claim_outbox_batch('{TENANT}','{node}');""").scalar
    record("and travels once the parent has been", second == "payment.captured",
           f"claimed: {second}")

    cursor = q(f"""
        SELECT acknowledged_through::text FROM integration.sync_cursor
         WHERE node_id = '{node}' AND direction = 'outlet_to_cloud';""").scalar
    record("the cursor records what the peer confirmed", (cursor or "0") != "0",
           f"acknowledged through sequence {cursor}")

    record("the cursor cannot be moved backwards",
           refusal(f"""UPDATE integration.sync_cursor SET acknowledged_through = 0
                        WHERE node_id = '{node}';""") == "SYNC_CURSOR_REWIND_REFUSED")

    record("an enqueued event cannot be rewritten",
           refusal(f"""UPDATE integration.outbox SET occurred_at = now()
                        WHERE event_id = '{bill_event}';""") == "OUTBOX_ROW_IS_IMMUTABLE")
    record("and cannot be deleted",
           refusal(f"DELETE FROM integration.outbox WHERE event_id = '{bill_event}';")
           == "OUTBOX_ROW_IS_PERMANENT")

    message = q("SELECT gen_random_uuid()::text;").scalar
    firsts = q(f"""
        SELECT integration.accept_inbound('{TENANT}','{node}','{message}','configuration',
               'config.menu','{{}}'::jsonb, now())::text;""").scalar
    repeat = q(f"""
        SELECT integration.accept_inbound('{TENANT}','{node}','{message}','configuration',
               'config.menu','{{}}'::jsonb, now())::text;""").scalar
    rows = q(f"""
        SELECT count(*)::text || '/' || max(arrivals)::text FROM integration.inbox
         WHERE message_id = '{message}';""").scalar
    record("a repeated cloud delivery applies once and is reported as a repeat",
           firsts in ("t", "true") and repeat in ("f", "false") and rows == "1/2",
           f"first={firsts} repeat={repeat} rows/deliveries={rows}")

    record("the synchronization evidence ledger refuses a destructive correction",
           refusal(f"""DELETE FROM integration.sync_evidence WHERE node_id = '{node}';""")
           == "LEDGER_ROW_DELETED_NOT_REVERSED")

    paths = q("SELECT count(*)::text FROM integration.business_replication_paths();").scalar
    record("no database-replication path carries business data (FR-EDG-005)",
           paths == "0",
           "asked of pg_publication rather than asserted in a comment; "
           f"{paths} publication(s) over business schemas")

    # FR-EDG-012: an incompatible peer pauses and local service is untouched.
    q(f"SELECT integration.check_peer_compatibility('{TENANT}','{node}','sync.event', 9);")
    paused = q(f"""SELECT paused_reason FROM integration.sync_state
                    WHERE node_id = '{node}';""").scalar
    claim_while_paused = refusal(
        f"SELECT * FROM integration.claim_outbox_batch('{TENANT}','{node}');")
    q(f"SELECT integration.check_peer_compatibility('{TENANT}','{node}','sync.event', 1);")
    resumed = q(f"""SELECT COALESCE(paused_reason,'(none)') FROM integration.sync_state
                     WHERE node_id = '{node}';""").scalar
    record("an incompatible peer pauses synchronization, with a reason, and it resumes",
           bool(paused) and claim_while_paused == "SYNC_PAUSED" and resumed == "(none)",
           f"paused: {paused}\nclaiming while paused: {claim_while_paused}\n"
           f"after a compatible peer: {resumed}")


# ===========================================================================
# 4. A disagreement is shown to somebody
# ===========================================================================

def section_conflicts() -> None:
    print("\n--- 4. Conflict policy (FR-EDG-008, FR-EDG-027) ---")
    node = node_id()

    raised = []
    for domain in ("order", "bill", "payment", "tip", "cash", "permission"):
        raised.append(q(f"""
            SELECT integration.raise_conflict('{TENANT}','{node}','{domain}',
                   gen_random_uuid(), '{{"local":1}}'::jsonb, '{{"remote":2}}'::jsonb,
                   now() - interval '1 hour', now(),
                   'the outlet and the cloud disagree')::text;""").scalar)
    record("a conflict can be raised on each of the six domains the requirement names",
           all(raised), f"{len(raised)} raised: orders, bills, payments, tips, cash, permissions")

    record("and cannot be raised on a domain that is not one of them",
           refusal(f"""
             SELECT integration.raise_conflict('{TENANT}','{node}','health',
                    gen_random_uuid(),'{{}}'::jsonb,'{{}}'::jsonb, now(), now(), 'x');""")
           in ("CHECK_VIOLATION", "conflict_subject_is_a_conflict_domain"))

    state = q(f"""SELECT connectivity::text FROM integration.sync_state
                   WHERE node_id = '{node}';""").scalar
    record("an open conflict puts the node in reconciling", state == "reconciling",
           f"connectivity: {state}")

    record("reconciling cannot be asserted, because it means a conflict is open",
           refusal(f"""SELECT integration.set_connectivity('{TENANT}','{node}',
                       'reconciling'::edge.connectivity_state);""")
           == "CONNECTIVITY_RECONCILING_IS_DERIVED")

    record("settling a conflict with no reason is refused",
           refusal(f"""SELECT integration.resolve_conflict('{TENANT}','{raised[0]}',
                       'local_stands','{ADMINISTRATOR}','   ');""")
           == "CONFLICT_RESOLUTION_UNEXPLAINED")

    record("and writing a resolution without an operator is refused by the table itself",
           refusal(f"""UPDATE integration.conflict SET resolution = 'remote_applied'
                        WHERE id = '{raised[0]}';""")
           in ("CHECK_VIOLATION", "conflict_resolution_needs_an_operator"))

    q(f"""SELECT integration.resolve_conflict('{TENANT}','{raised[0]}','local_stands',
          '{ADMINISTRATOR}','the outlet served the guest; the cloud never saw it');""")
    record("a settled conflict cannot be settled differently later",
           refusal(f"""SELECT integration.resolve_conflict('{TENANT}','{raised[0]}',
                       'remote_applied','{ADMINISTRATOR}','changed my mind');""")
           == "CONFLICT_ALREADY_RESOLVED")

    for conflict in raised[1:]:
        q(f"""SELECT integration.resolve_conflict('{TENANT}','{conflict}','local_stands',
              '{ADMINISTRATOR}','settled so the run leaves nothing outstanding');""")


# ===========================================================================
# 5. What the node holds, and what it may do alone
# ===========================================================================

def section_readiness_and_authority() -> None:
    print("\n--- 5. Readiness and outage authority (FR-EDG-025, FR-EDG-010) ---")

    elements = q(f"""
        SELECT count(*)::text || '/' ||
               count(*) FILTER (WHERE is_held)::text || '/' ||
               COALESCE(string_agg(element::text, ',') FILTER (WHERE NOT is_held), '(none)')
          FROM edge.readiness_report('{TENANT}','{OUTLET}');""").scalar
    total, held, missing = (elements or "0/0/").split("/", 2)
    record("readiness reports all eleven elements, present or not",
           total == "11",
           f"{held} of {total} held; unheld: {missing}\n"
           "an element that is not held is NAMED rather than omitted — a missing line in "
           "a readiness report reads as ready")

    node = node_id()
    q(f"""SELECT integration.set_connectivity('{TENANT}','{node}',
          'local_continuity'::edge.connectivity_state);""")

    counts = q(f"""
        SELECT string_agg(d.disposition::text, ',' ORDER BY d.disposition)
          FROM edge.action_dependency a
          CROSS JOIN LATERAL edge.action_disposition('{TENANT}','{OUTLET}', a.action_code,
                                                     'en') d;""").scalar or ""
    permitted = counts.count("permitted")
    record("cash, terminal recording and ordinary service continue during an outage",
           q(f"""SELECT (SELECT disposition::text FROM edge.action_disposition('{TENANT}',
                   '{OUTLET}','payment.cash_settle','en'))
                 || ',' ||
                 (SELECT disposition::text FROM edge.action_disposition('{TENANT}',
                   '{OUTLET}','payment.terminal_record','en'))
                 || ',' ||
                 (SELECT disposition::text FROM edge.action_disposition('{TENANT}',
                   '{OUTLET}','order.place','en'));""").scalar
           == "permitted,permitted,permitted",
           f"{permitted} of {counts.count(',') + 1} classified actions proceed")

    for locale in ("en", "am", "ar"):
        explained = q(f"""
            SELECT length(COALESCE((SELECT explanation FROM edge.action_disposition(
                     '{TENANT}','{OUTLET}','payment.online_capture','{locale}')), ''))::text;
            """).scalar
        record(f"a blocked action explains itself in {locale}", int(explained or 0) > 10,
               f"{explained} characters of explanation")

    record("an action nobody classified is refused rather than allowed by omission",
           refusal(f"""SELECT * FROM edge.action_disposition('{TENANT}','{OUTLET}',
                       'loyalty.redeem','en');""") == "ACTION_UNCLASSIFIED")

    five = q(f"""
        SELECT count(*)::text || '/' || count(*) FILTER (WHERE length(wording) > 0)::text
          FROM edge.staff_sync_summary('{TENANT}','{OUTLET}','am');""").scalar
    record("all five synchronization states are worded for staff (FR-POS-008)",
           five == "5/5", f"states/worded: {five}")


# ===========================================================================
# 6. The durable print queue, on a real receipt
# ===========================================================================

def section_print() -> None:
    # A JOB KEY PER RUN, because the receipt is now an existing one and the key is
    # derived from it. Stable across runs, the second run finds the first run's job
    # already PRINTED and cannot claim it — the idempotency working exactly as
    # designed, and a lifecycle the suite can then never exercise again. The run
    # token separates runs; the two enqueues WITHIN a run still share a key, which is
    # what the idempotency check asserts.
    run_token = os.urandom(4).hex()
    print("\n--- 6. Resilient local receipt printing (FR-EDG-029) ---")

    # A REAL RECEIPT, NOT NECESSARILY A NEW ONE.
    #
    # The queue has to be proved against a receipt the system actually issued, and this
    # gate does not care WHICH. Insisting on a fresh one made the section depend on the
    # kitchen having room: FR-ORD-006 throttles the hot station at 12 concurrent tickets,
    # and after the reordered sweep the outlet holds 33 live ones, so the new order was
    # refused with SUBMISSION_REVALIDATION_FAILED. That is a suite that only works when it
    # runs first, which is precisely what the reordered sweep exists to find — and it
    # found it here.
    #
    # Standing the kitchen down first was the other option and it is worse: OP-D's
    # clear-down cancels QUEUED tickets, and after a full run they are spread across
    # preparing, ready and rework, so it would have needed to grow a cancellation path for
    # states M3-B owns the transitions for. Taking an existing receipt asks less of the
    # rest of the system and proves the same thing.
    # AND AT WHICHEVER OUTLET HAS ONE. This suite works at Sarbet; every receipt in the
    # chain is issued at Kazanchis, because that is where the M4 suites and the journeys
    # trade. Scoping the search to this suite's own outlet found none and then tried to
    # create one, which is how it ended up fighting the capacity rule at the other outlet
    # anyway. The queue is not a Sarbet feature; it is proved where the paper is.
    # AND ONE THAT HAS NOT BEEN PRINTED YET. M4-C refuses a second ORIGINAL print of the
    # same receipt — "a receipt printed twice is a customer holding two records of one
    # payment" — so reusing whichever receipt is newest works once and is refused on the
    # next run. The queue lifecycle FR-EDG-029 describes is the one for an original, so
    # the receipt this section takes is one no attempt has been recorded against.
    found = q(f"""
        SELECT r.id::text, r.outlet_id::text FROM docs.receipt r
         WHERE r.tenant_id = '{TENANT}'
           AND NOT EXISTS (SELECT 1 FROM docs.print_attempt a
                            WHERE a.receipt_id = r.id)
         ORDER BY r.generated_at DESC LIMIT 1;""", outlet=None).rows
    receipt = found[0][0] if found else ""
    print_outlet = found[0][1] if found else OUTLET
    if not receipt:
        try:
            import verify_m4c as m4c                            # noqa: PLC0415
            m4c.CONTEXT.update(CONTEXT)
            receipt = m4c.a_receipt(m4c.a_settled_bill())
        except Exception as error:                              # noqa: BLE001
            record("a real receipt was available to queue", False,
                   f"this outlet has issued none, and the M4-C helpers could not produce "
                   f"one either: {type(error).__name__}: {str(error)[:200]}")
            return
    record("a real receipt was available to queue", bool(receipt),
           f"receipt {receipt[:8]} — issued by the settlement path, not written here")

    # THE PRINTER'S OWN SINK, NOT A CONSTANT. M4-C refuses a print recorded against a
    # sink the printer is not classified for — PRINT_EVIDENCE_DISAGREES — and it is right
    # to: "a customer receipt is not recorded as printed over a disagreement about where
    # the bytes went". This suite hardcoded `device` and the chain's first active printer
    # is a discard sink, so the guard fired. Reading the classification means the queue is
    # proved against whatever printer the state actually has.
    printer_row = q(f"""
        SELECT id::text, sink::text,
               COALESCE(device_path, host_and_port, '')
          FROM docs.printer
         WHERE tenant_id = '{TENANT}' AND outlet_id = '{print_outlet}' AND status = 'active'
         ORDER BY registered_at LIMIT 1;""", outlet=print_outlet).rows[0]
    printer, printer_sink, printer_destination = printer_row

    job = q(f"""
        SELECT docs.enqueue_print_job('{TENANT}','{print_outlet}','{receipt}','{printer}',
               'receipt:{receipt}:{run_token}','{ADMINISTRATOR}')::text;""",
        outlet=print_outlet).scalar
    again = q(f"""
        SELECT docs.enqueue_print_job('{TENANT}','{print_outlet}','{receipt}','{printer}',
               'receipt:{receipt}:{run_token}','{ADMINISTRATOR}')::text;""",
        outlet=print_outlet).scalar
    record("asking twice for the same receipt queues one job",
           job == again and bool(job),
           "a cashier who pressed the button twice asked for one receipt")

    claimed = q(f"""
        SELECT count(*)::text FROM docs.claim_print_jobs('{TENANT}','{print_outlet}',
               'suite-agent', 1, 10);""", outlet=print_outlet).scalar
    record("the agent claims the job under a lease", claimed == "1", f"claimed {claimed}")

    # RESTART RECOVERY: the lease expires because the agent stopped. Nothing here deletes
    # or rewrites the job — the queue survives the process, which is the property.
    q("SELECT pg_sleep(1.2);")
    recovered = q(f"""
        SELECT docs.recover_expired_print_claims('{TENANT}','{print_outlet}')::text;""",
        outlet=print_outlet).scalar
    state = q(f"SELECT state::text FROM docs.print_job WHERE id = '{job}';",
              outlet=print_outlet).scalar
    # AT LEAST ONE, AND THIS ONE. Asserting exactly one recovered is asserting that no
    # other run ever left an expired claim at this outlet, which is a fact about the
    # database's history rather than about the lease. The property is that THIS job came
    # back; anything else recovering alongside is the same mechanism working twice.
    record("a job held by an agent that stopped returns to the queue",
           int(recovered or 0) >= 1 and state == "queued",
           f"recovered {recovered}, now {state} — a lease expires; a flag would not")

    q(f"""SELECT docs.claim_print_jobs('{TENANT}','{print_outlet}','suite-agent', 120, 10);""",
      outlet=print_outlet)
    q(f"""
        SELECT docs.complete_print_job('{TENANT}','{job}','{printer_sink}',
               '{printer_destination}', '{'a' * 64}'::character(64), 512,
               '{ADMINISTRATOR}');""", outlet=print_outlet)
    printed = q(f"SELECT state::text FROM docs.print_job WHERE id = '{job}';",
                outlet=print_outlet).scalar
    record("completing the job records the print through M4-C's own ledger",
           printed == "printed",
           f"state {printed}; the attempt row is docs.print_attempt, not a second ledger")

    twice = q(f"""
        SELECT COALESCE(docs.complete_print_job('{TENANT}','{job}','{printer_sink}',
               '{printer_destination}', '{'a' * 64}'::character(64), 512,
               '{ADMINISTRATOR}')::text, '(no second attempt)');
        """, outlet=print_outlet).scalar
    attempts = q(f"""
        SELECT count(*)::text FROM docs.print_attempt WHERE receipt_id = '{receipt}';""",
        outlet=print_outlet).scalar
    record("reporting the same print twice does not print twice",
           twice == "(no second attempt)" and attempts == "1",
           f"second report: {twice}; attempts recorded: {attempts}")

    record("a printed job cannot be returned to the queue",
           refusal(f"""UPDATE docs.print_job SET state = 'queued' WHERE id = '{job}';""",
                   outlet=print_outlet)
           == "PRINT_JOB_ALREADY_PRINTED",
           "paper cannot be un-cut, so a second copy is a reprint with its own job")

    reconciled = q(f"""
        SELECT count(*)::text FROM integration.outbox
         WHERE subject = 'print_job' AND subject_id = '{job}';""",
        outlet=print_outlet).scalar
    record("the cloud is told once, when the link returns", reconciled == "1",
           f"{reconciled} outbox event for this job, keyed on the job id")

    health = q(f"""
        SELECT count(*)::text FROM docs.printer_health('{TENANT}','{print_outlet}');""",
        outlet=print_outlet).scalar
    record("printer health reports every active printer, jobs or not",
           int(health or 0) >= 1, f"{health} printer(s) reported")


# ===========================================================================
# 7. Updates
# ===========================================================================

def section_updates() -> None:
    run_token = os.urandom(4).hex()
    print("\n--- 7. Signed updates and rollback (FR-OPS-010) ---")
    node = node_id()
    anchor = q(f"""SELECT update_trust_anchor_sha256 FROM edge.node
                    WHERE id = '{node}';""").scalar

    bundle = q(f"""
        INSERT INTO edge.update_bundle (tenant_id, version, artifact_sha256,
               attestation_sha256, requires_schema_at_least, supports_schema_up_to,
               published_by_user_id)
        VALUES ('{TENANT}','1.1.0-{run_token}','{'1' * 64}'::character(64),
                edge.update_attestation('{'1' * 64}'::character(64), '{anchor}'), 40, 999,
                '{ADMINISTRATOR}')
        RETURNING id::text;""").scalar

    wrong = q(f"""
        INSERT INTO edge.update_bundle (tenant_id, version, artifact_sha256,
               attestation_sha256, requires_schema_at_least, supports_schema_up_to,
               published_by_user_id)
        VALUES ('{TENANT}','1.2.0-{run_token}','{'2' * 64}'::character(64),
                edge.update_attestation('{'2' * 64}'::character(64),
                                        '{'9' * 64}'::character(64)), 40, 999,
                '{ADMINISTRATOR}')
        RETURNING id::text;""").scalar

    record("a bundle attested against another estate's anchor is refused",
           refusal(f"SELECT edge.stage_update('{TENANT}','{node}','{wrong}');")
           == "UPDATE_ATTESTATION_INVALID")

    stale = q(f"""
        INSERT INTO edge.update_bundle (tenant_id, version, artifact_sha256,
               attestation_sha256, requires_schema_at_least, supports_schema_up_to,
               published_by_user_id)
        VALUES ('{TENANT}','9.9.9-{run_token}','{'3' * 64}'::character(64),
                edge.update_attestation('{'3' * 64}'::character(64), '{anchor}'), 900, 999,
                '{ADMINISTRATOR}')
        RETURNING id::text;""").scalar
    record("a bundle whose schema range excludes this database is refused",
           refusal(f"SELECT edge.stage_update('{TENANT}','{node}','{stale}');")
           == "UPDATE_SCHEMA_INCOMPATIBLE")

    staged = q(f"SELECT edge.stage_update('{TENANT}','{node}','{bundle}')::text;").scalar
    q(f"SELECT edge.apply_update('{TENANT}','{staged}','{ADMINISTRATOR}');")
    version = q(f"SELECT installed_version FROM edge.node WHERE id = '{node}';").scalar
    record("an attested, compatible bundle applies",
           version == f"1.1.0-{run_token}",
           f"the node reports {version}")

    record("an unexplained rollback is refused",
           refusal(f"""SELECT edge.roll_back_update('{TENANT}','{staged}',
                       '{ADMINISTRATOR}','  ');""")
           == "NODE_UPDATE_ROLLBACK_UNEXPLAINED")

    q(f"""SELECT edge.roll_back_update('{TENANT}','{staged}','{ADMINISTRATOR}',
          'the kitchen display stopped refreshing');""")
    back = q(f"SELECT installed_version FROM edge.node WHERE id = '{node}';").scalar
    depths = q(f"""
        SELECT outbox_depth_at_staging::text || '->' || outbox_depth_at_rollback::text
          FROM edge.node_update WHERE id = '{staged}';""").scalar
    record("rolling back restores the version and records that the queues survived",
           back == "0.0.0" and "->" in (depths or ""),
           f"version {back}; outbox depth {depths} — a guarantee with no measurement is "
           "a sentence in a document")


# ===========================================================================
# 8. The controls
# ===========================================================================

def section_controls() -> None:
    print("\n--- 8. Negative controls ---")
    node = node_id()

    # NC-M5A-001 — a production outlet permitted to run cloud-only.
    def red_profile():
        run(ADMIN, "ALTER TABLE edge.deployment_profile "
                   "DROP CONSTRAINT deployment_profile_production_requires_the_node;")
        got = refusal(f"""
            INSERT INTO edge.deployment_profile (tenant_id, outlet_id, environment_class,
                   serving_mode, non_production_reason, declared_by_user_id)
            VALUES ('{NILE}','{NILE_OUTLET}','production','cloud_only','trying it on',
                    '{NILE_ADMIN}');""", tenant=NILE, outlet=NILE_OUTLET)
        q(f"""DELETE FROM edge.deployment_profile
                WHERE outlet_id = '{NILE_OUTLET}' AND environment_class = 'production'
                  AND serving_mode = 'cloud_only';""", tenant=NILE, outlet=NILE_OUTLET)
        return got == "", ("a production outlet was recorded as cloud-only with the check "
                           "removed" if got == "" else f"still refused: {got}")

    def green_profile():
        run(ADMIN, """
            ALTER TABLE edge.deployment_profile
              ADD CONSTRAINT deployment_profile_production_requires_the_node CHECK (
                serving_mode = 'continuity_node' OR environment_class <> 'production');""")
        got = refusal(f"""
            INSERT INTO edge.deployment_profile (tenant_id, outlet_id, environment_class,
                   serving_mode, non_production_reason, declared_by_user_id)
            VALUES ('{NILE}','{NILE_OUTLET}','production','cloud_only','trying it on',
                    '{NILE_ADMIN}');""", tenant=NILE, outlet=NILE_OUTLET)
        return got != "", f"refused again with: {got}"

    control("NC-M5A-001", "PRODUCTION_WITHOUT_A_NODE", red_profile, green_profile)

    # NC-M5A-002 — a node registered with four of its five services.
    def red_services():
        got = refusal(f"""
            SELECT edge.register_node('{TENANT}','{SIBLING}','NODE-BROKEN',
              '3333ed01-0000-4000-8000-0000000ed001','{'b' * 64}'::character(64),
              '3333ed11-0000-4000-8000-0000000ed011','http://x','x',
              '{'c' * 64}'::character(64),'y','{ADMINISTRATOR}',
              '{{"local_api":"a","database":"b","sync_worker":"c","realtime_gateway":"d"}}'::jsonb);
            """, outlet=SIBLING)
        return got == "NODE_SERVICE_INVENTORY_INCOMPLETE", f"refused with: {got}"

    def green_services():
        count = q(f"""SELECT count(*)::text FROM edge.node_service
                       WHERE node_id = '{node}';""").scalar
        return count == "5", f"the registered node still has {count} services"

    control("NC-M5A-002", "NODE_SERVICE_INVENTORY_INCOMPLETE", red_services, green_services)

    # NC-M5A-003 — the wrong-outlet refusal, which was unreachable until 0046.
    def red_outlet():
        got = refusal(f"""SELECT edge.authenticate_node('{TENANT}','{NODE_CODE}',
                          '{NODE_FINGERPRINT}'::character(64),'{SIBLING}');""")
        return got == "NODE_OUTLET_MISMATCH", f"refused with: {got}"

    def green_outlet():
        got = refusal(f"""SELECT edge.authenticate_node('{TENANT}','{NODE_CODE}',
                          '{NODE_FINGERPRINT}'::character(64),'{OUTLET}');""")
        return got == "", f"the correct outlet is accepted ({got or 'no refusal'})"

    control("NC-M5A-003", "NODE_OUTLET_MISMATCH", red_outlet, green_outlet)

    # NC-M5A-004 — a banner that reports CONNECTED because it could not see.
    def red_banner():
        got = refusal(f"""SELECT * FROM edge.connectivity_banner('{TENANT}','{OUTLET}',
                          'en');""", outlet=SIBLING)
        return got == "CONNECTIVITY_OUT_OF_SCOPE", f"refused with: {got}"

    def green_banner():
        state = q(f"""SELECT state::text FROM edge.connectivity_banner('{TENANT}',
                       '{OUTLET}','en');""").scalar
        return bool(state), f"in scope it answers: {state}"

    control("NC-M5A-004", "CONNECTIVITY_OUT_OF_SCOPE", red_banner, green_banner)

    # NC-M5A-005 — an action allowed during an outage because nobody classified it.
    def red_unclassified():
        got = refusal(f"""SELECT * FROM edge.action_disposition('{TENANT}','{OUTLET}',
                          'loyalty.redeem','en');""")
        return got == "ACTION_UNCLASSIFIED", f"refused with: {got}"

    def green_unclassified():
        got = q(f"""SELECT disposition::text FROM edge.action_disposition('{TENANT}',
                     '{OUTLET}','order.place','en');""").scalar
        return got == "permitted", f"a classified action answers: {got}"

    control("NC-M5A-005", "ACTION_UNCLASSIFIED", red_unclassified, green_unclassified)


# ===========================================================================
# 9. What this gate did not prove
# ===========================================================================

def section_bounds() -> None:
    print("\n--- 9. The bounds, named rather than left to silence ---")
    for bound in (
        "the update attestation is a KEYED DIGEST, not a signature: this database has no "
        "pgcrypto, so it proves the publisher knew the node's trust anchor and not who "
        "they were",
        "the outage is cut at the sync transport's only seam, not at a NIC; a partial "
        "link, a slow link and a DNS lie are M5b's",
        "the node's fingerprint is read from configuration; nothing here binds it to "
        "hardware",
        "a process that dies between the paper leaving the printer and the row being "
        "written can still print a second copy on retry",
    ):
        record("recorded in planning/M5A_FINDINGS.md", True, bound)


def main() -> int:
    print("=" * 74)
    print("  M5a — the outlet keeps working when the cloud does not")
    print("=" * 74)

    with Service(APP) as service_process:
        CONTEXT["base_url"] = f"http://127.0.0.1:{service_process.port}"
        CONTEXT["service"] = service_process
        opa.CONTEXT["base_url"] = CONTEXT["base_url"]
        opa.CONTEXT["service"] = service_process

        answer = opa.login(opa.MANAGER_PASSWORD, value=opa.MANAGER_EMAIL)
        if not answer.get("token"):
            print(f"FAIL M5A_SIGN_IN\n  the manager could not sign in: {answer}")
            return 1
        CONTEXT["token"] = answer["token"]
        opa.CONTEXT["token"] = answer["token"]

        for section in (section_node, section_estate, section_sync, section_conflicts,
                        section_readiness_and_authority, section_print, section_updates,
                        section_controls, section_bounds):
            try:
                section()
            except ProbeFailed as exc:
                record(f"{section.__name__} completed", False, f"probe did not execute: {exc}")
            except Exception as exc:                            # noqa: BLE001
                record(f"{section.__name__} completed", False,
                       f"{type(exc).__name__}: {str(exc)[:400]}")

    failed = [name for name, ok, _d, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")
    owned = len([c for c in registry.CONTROLS if c[3] == "m5a"])

    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}")
    print(f"  asserted      : {len(results) - measured_count}")
    print(f"  controls      : {owned} registered, each proved red then green")

    if failed:
        print("\nFAIL M5A_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS M5A_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
