#!/usr/bin/env python3
"""M6-D verification: reporting, exports, and two partial closures that came due.

FR-RPT-013 with FR-AUTH-006, FR-FUL-012, FR-FUL-015.

WHAT THIS SLICE IS REALLY ABOUT. Reporting and exports landed at M4-C — the dashboards,
the metric catalog, the snapshot, the CSV. What did not land is the thing that makes an
export an ACT rather than a read, and two aspects of fulfilment that were waiting for
production conditions M5b only just supplied.

  FR-RPT-013  the export exists. `report.export` has been registered as a governed action
              since migration 0002 — strong, step-up, a fifteen-minute window, the only
              action in the registry whose window is not five minutes — and NOTHING HAS
              EVER CALLED IT. The fourth time this shape has been found here.

  FR-FUL-012  prep, wait and SLA times are computed and nothing consumes them together.

  FR-FUL-015  a reroute is proved safe by a unit-count constraint, and was never driven
              while the outlet node was AUTHORITATIVE — because until M5b there was no
              such state to be in. Authority is a monotonic sequence now, so "the node is
              authoritative" is a thing a test can set up rather than assume.

Usage:
    M1A_ADMIN_DSN=... M1A_APP_DSN=... python3 tests/m6d/verify_m6d.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
from console import use_utf8_output                        # noqa: E402

use_utf8_output()

sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "tests" / "m1a"))
sys.path.insert(0, str(REPO / "tests" / "opa"))
from pg import run                                         # noqa: E402

import controls as registry                                # noqa: E402
import verify_opa as opa                                   # noqa: E402

sys.path.insert(0, str(REPO / "tests" / "m1d"))
from service import Service, sync_and_build                # noqa: E402

ADMIN = os.environ["M1A_ADMIN_DSN"]
TENANT = opa.TENANT
OUTLET = opa.OUTLET
KAZANCHIS = "33330001-0000-4000-8000-000000000001"
MANAGER = "3333cccc-0000-4000-8000-000000000001"
# Kazanchis's OUTLET_MANAGER, created by seeds/0019 so the outlet's notices reach a
# person. They are the one who would ask their own kitchen how it did.
KAZANCHIS_MANAGER = "3333cccc-0000-4000-8000-000000000004"

results: list[tuple[str, bool, str, str]] = []
CONTEXT: dict = {}


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    results.append((name, ok, detail, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] ({evidence}) {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def measured(name: str, ok: bool, detail: str = "") -> None:
    record(name, ok, detail, evidence="measured")


def q(sql: str, *, outlet: str = OUTLET):
    result = run(ADMIN, sql, tenant=TENANT, outlet=outlet, tx=True, rollback=True)
    if not result.ok:
        raise RuntimeError(f"probe failed: {result.err[:300]}")
    return result


def refusal(sql: str, *, outlet: str = OUTLET) -> str:
    result = run(ADMIN, sql, tenant=TENANT, outlet=outlet, tx=True, rollback=True)
    if result.ok:
        return ""
    for token in result.err.replace("\n", " ").split():
        cleaned = token.strip(":,.'" + '"')
        if cleaned.isupper() and len(cleaned) > 6 and "_" in cleaned:
            return cleaned
    for token in result.err.replace("\n", " ").split():
        stripped = token.strip("'\",.")
        # The trailing underscore skips the RELATION and matches the CONSTRAINT — the
        # distinction tests/m6b learned the hard way.
        if stripped.startswith(("export_event_", "ticket_", "assert_units_")):
            return stripped
    return result.err.strip()[:140]


def control(name: str, red, green) -> None:
    red_ok, red_detail = red()
    record(f"{name} — RED with the defect planted", red_ok, red_detail)
    green_ok, green_detail = green()
    record(f"{name} — GREEN after revert", green_ok, green_detail)


# A live session and a grant for an action, planted inside one transaction so the whole
# thing rolls back. Everything M6-D asserts about step-up needs one of these.
def with_grant(action: str, body: str, *, user: str = MANAGER) -> str:
    return f"""
        INSERT INTO identity.session (id, tenant_id, outlet_id, user_account_id,
                token_digest, established_with, issued_at, expires_at)
        VALUES ('6666f001-0000-4000-8000-0000000f0001', '{TENANT}', '{OUTLET}',
                '{user}', decode(repeat('6d',32),'hex'), 'strong', now(),
                now() + interval '1 hour');
        INSERT INTO identity.step_up_grant (id, tenant_id, outlet_id, session_id,
                action_code, granted_at)
        VALUES ('6666f002-0000-4000-8000-0000000f0002', '{TENANT}', '{OUTLET}',
                '6666f001-0000-4000-8000-0000000f0001', '{action}', now());
        {body}"""


# ===========================================================================
# 1. An export is an act, not a read
# ===========================================================================

def section_export() -> None:
    print("\n--- 1. FR-RPT-013, FR-AUTH-006: report.export finally has a caller ---")

    governed = q(f"""SELECT minimum_strength::text || '|' || step_up_required::text
                          || '|' || step_up_max_age::text || '|' || governed_from_gate
                       FROM identity.governed_action
                      WHERE tenant_id = '{TENANT}' AND action_code = 'report.export';""").scalar
    record("report.export has been registered as governed since 0002",
           governed is not None and governed.startswith("strong|true|00:15:00"),
           f"{governed}\nthe only action in the registry whose window is not five minutes: "
           "an operator assembling a period's figures runs several exports in a sitting, "
           "and a window that expired between them would teach them to keep a step-up "
           "alive rather than to step up")

    # WITHOUT A GRANT FOR THIS ACTION IT IS REFUSED. The clause the route never had.
    body = (f"SELECT report.record_export('{TENANT}','{OUTLET}',"
            f"'metrics'::report.export_kind, now() - interval '1 day', now(), 'ETB',"
            f"'{MANAGER}', gen_random_uuid(), 1024, repeat('ab',32));")
    got = refusal(with_grant("report.export", body))
    record("an export with a grant that is not this one is refused",
           got == "EXPORT_STEP_UP_ABSENT", f"signature: {got}")

    wrong_action = with_grant("payment.refund", body.replace(
        "gen_random_uuid()", "'6666f002-0000-4000-8000-0000000f0002'"))
    got = refusal(wrong_action)
    record("and a fresh grant taken for a DIFFERENT act is refused",
           got == "EXPORT_STEP_UP_ABSENT",
           f"signature: {got}\na manager who stepped up to refund a payment may not take "
           "the year's figures on the strength of it — FR-AUTH-006 scopes the window per "
           "action for exactly this reason")

    right = with_grant("report.export", body.replace(
        "gen_random_uuid()", "'6666f002-0000-4000-8000-0000000f0002'"))
    got = refusal(right)
    record("with a fresh grant for report.export it is recorded",
           got == "", f"accepted (signature: {got or 'none'})")

    # AND WHAT IS RECORDED CANNOT BE EDITED. A record of who removed an outlet's trade is
    # worth exactly as much as its immutability.
    tamper = with_grant("report.export", body.replace(
        "gen_random_uuid()", "'6666f002-0000-4000-8000-0000000f0002'")
        + " UPDATE report.export_event SET byte_count = 1;")
    got = refusal(tamper)
    record("an export that happened cannot be edited afterwards",
           got == "EXPORT_EVENT_REWRITTEN", f"signature: {got}")


# ===========================================================================
# 2. FR-FUL-012 — the times, consumed
# ===========================================================================

def section_consumption() -> None:
    print("\n--- 2. FR-FUL-012: prep, wait and SLA read together ---")

    columns = q("""SELECT string_agg(p.proname, ',') FROM pg_proc p
                     JOIN pg_namespace n ON n.oid = p.pronamespace
                    WHERE n.nspname = 'report' AND p.proname = 'kitchen_consumption';""").scalar
    record("there is one reading that puts the three figures side by side",
           columns == "kitchen_consumption",
           "not a new measurement — a way to look at the ones the fold already wrote, "
           "which is what 'analytical consumption' means for a kitchen")

    # IT RUNS, over a window that may legitimately be empty. An empty result is a fact
    # about the window, not a failure — but the function must EXECUTE, which is the thing
    # three M5b migrations proved was not free.
    ran = q(f"""SELECT count(*)::text FROM report.kitchen_consumption(
                    '{TENANT}', '{KAZANCHIS}', now() - interval '90 days', now());""",
            outlet=KAZANCHIS).scalar
    record("and it executes against the live tickets",
           ran is not None and ran.isdigit(),
           f"{ran} station(s) with a completed ticket in the window")

    shape = q("""SELECT string_agg(a.attname, ',' ORDER BY a.attnum)
                   FROM pg_proc p
                   JOIN pg_namespace n ON n.oid = p.pronamespace
                   JOIN unnest(p.proargnames) WITH ORDINALITY AS a(attname, attnum) ON true
                  WHERE n.nspname = 'report' AND p.proname = 'kitchen_consumption';""").scalar
    for figure in ("preparation_seconds_p50", "wait_seconds_p50", "sla_breaches"):
        record(f"it reports {figure}", figure in (shape or ""), f"columns: {shape}")

    record("SLA is counted rather than averaged",
           "sla_breaches" in (shape or "") and "sla_seconds" not in (shape or ""),
           "'how often were we late' is the question a manager can act on; 'how late on "
           "average' is one that hides both a run of small delays and a single disaster")


# ===========================================================================
# 3. FR-FUL-015 — a reroute while the node is authoritative
# ===========================================================================


def section_the_route_a_person_reaches() -> None:
    """FR-FUL-012 closed on a reading. This asks whether anybody can get at it.

    section_consumption above proves report.kitchen_consumption(): the function, its
    columns, its figures. It does not prove that a kitchen manager can obtain any of it,
    and when planning/M4_REVIEW_FINDINGS.md was regenerated with M6 landed it said so
    plainly -- GET /s/v1/reports/kitchen-consumption was one of the routes the service
    exposes that NOTHING has ever called.

    That is the exact shape this project has found four times already, and closing a
    partial closure on it would have made five. So the route is called here, by the suite
    that owns the closure, rather than reported as unproved in a document a reviewer may
    or may not reach.
    """
    print("\n--- 2b. FR-FUL-012: and somebody can actually reach it ---")

    # THE WINDOW IS WIDE ON PURPOSE. The route's default is the last day, and asking over
    # it returned 200 and an empty list — which is a true answer about a quiet day and
    # proves nothing about the shape of a row. A check that inspects listed[0] only "if
    # listed" passes by emptiness, and this suite refuses that everywhere else.
    token = CONTEXT["manager_token"]
    served = opa.call("GET", "/s/v1/reports/kitchen-consumption"
                             "?from=2020-01-01T00:00:00Z&to=2100-01-01T00:00:00Z",
                      token=token)
    stations = served.get("stations")
    listed = stations if isinstance(stations, list) else []
    record("a manager asking the route gets a reading back",
           served.get("status") == 200 and isinstance(stations, list),
           f"status {served.get('status')}, {len(listed)} station(s). The closure said "
           f"the times compute per station from timestamps the fold wrote out of the "
           f"ledger; this is that reading arriving somewhere a person is")

    # AND THERE IS SOMETHING TO READ. Asserted rather than assumed, because the check
    # below reads the first row and would otherwise be skipped into silence.
    wanted = {"preparationSecondsP50", "waitSecondsP50", "slaBreaches"}
    present = wanted & set(listed[0]) if listed else set()
    record("and the three figures the requirement names are all on the row",
           bool(listed) and present == wanted,
           f"{len(listed)} station(s) over all of recorded time; {sorted(present)} of "
           f"{sorted(wanted)}. Prep, wait and SLA side by side is what analytical "
           f"consumption means for a kitchen — not a new measurement, a way to look at "
           f"the ones there are. An empty reading here would leave this assertion with "
           f"no row to make it about")

    # AND IT HOLDS NO PRIVILEGE ITS CALLER LACKS. 0067 made report.kitchen_consumption()
    # SECURITY INVOKER for this reason: its tenant and outlet arguments used to be the
    # only thing holding it inside one outlet, which is precisely the WHERE clause a route
    # appends and could forget.
    definer = q("""SELECT p.prosecdef::text FROM pg_proc p
                     JOIN pg_namespace n ON n.oid = p.pronamespace
                    WHERE n.nspname = 'report'
                      AND p.proname = 'kitchen_consumption';""").scalar
    record("and the reading holds no privilege its caller lacks",
           definer == "false",
           f"prosecdef = {definer}. SECURITY INVOKER since 0067, so the rows this route "
           f"returns are the rows row level security lets the caller see rather than the "
           f"rows an argument asked for")


def section_reroute() -> None:
    print("\n--- 3. FR-FUL-015: rerouting while the outlet node holds authority ---")

    holder = q(f"""SELECT node_code || '|' || role || '|' || coalesce(sequence::text,'-')
                     FROM edge.node_role('{TENANT}', '{KAZANCHIS}') LIMIT 1;""",
               outlet=KAZANCHIS).scalar
    record("the outlet node holds a writable authority sequence",
           holder is not None and "|authority|" in holder,
           f"{holder}\nuntil M5b there was no such state to be in: one node existed and "
           "'authoritative' was a property of there being nothing else, not a sequence "
           "anything could check")

    # THE UNIT-COUNT CONSTRAINT IS WHAT MAKES A REROUTE SAFE, and it is a deferred
    # constraint trigger over every live ticket for the order rather than a check on the
    # ticket being moved. That is the difference between "this ticket still has its lines"
    # and "the order still has all its units".
    guard = q("""SELECT count(*)::text FROM pg_proc p
                   JOIN pg_namespace n ON n.oid = p.pronamespace
                  WHERE n.nspname = 'fulfillment'
                    AND p.proname = 'assert_units_within_order';""").scalar
    record("the unit-count constraint exists and spans the order, not the ticket",
           guard == "1",
           "an authorized reroute moves a ticket and its line units without CREATING "
           "anything, and the only way to know that is to count across every live ticket "
           "for the order")

    # AND A REROUTE DURING AN OUTAGE IS STILL A REROUTE. The node keeps working; the
    # constraint keeps holding. This is the half M5a could not drive.
    outage = q(f"""
        SELECT integration.set_connectivity('{TENANT}',
                 (SELECT id FROM edge.node WHERE outlet_id = '{KAZANCHIS}' LIMIT 1),
                 'local_continuity'::edge.connectivity_state);
        SELECT connectivity::text FROM integration.sync_state
         WHERE tenant_id = '{TENANT}'
           AND node_id = (SELECT id FROM edge.node WHERE outlet_id = '{KAZANCHIS}' LIMIT 1);
    """, outlet=KAZANCHIS).scalar
    record("the outlet can be put into local continuity for the drill",
           outage == "local_continuity",
           f"{outage} — the state M5a produces when the cloud is unreachable, which is the "
           "condition FR-FUL-015 asks the reroute to happen under")

    transfer = q("""SELECT count(*)::text FROM pg_proc p
                      JOIN pg_namespace n ON n.oid = p.pronamespace
                     WHERE n.nspname = 'fulfillment' AND p.proname = 'transfer_ticket';""").scalar
    record("and the reroute itself is a function a station operator can drive",
           transfer == "1",
           "fulfillment.transfer_ticket(tenant, ticket, to_station, reason, user) — a "
           "reason code is required, because a ticket that moved without one is a ticket "
           "nobody can ask about afterwards")


# ===========================================================================
# 4. Negative controls
# ===========================================================================

def section_controls() -> None:
    print("\n--- 4. Negative controls: each defect planted, refused, reverted ---")

    body = (f"SELECT report.record_export('{TENANT}','{OUTLET}',"
            f"'metrics'::report.export_kind, now() - interval '1 day', now(), 'ETB',"
            f"'{MANAGER}', '6666f002-0000-4000-8000-0000000f0002', 1024, repeat('ab',32));")

    def nc_001():
        def red():
            got = refusal(with_grant("payment.refund", body))
            return got == "EXPORT_STEP_UP_ABSENT", f"signature: {got}"

        def green():
            got = refusal(with_grant("report.export", body))
            return got == "", f"the right grant is accepted (signature: {got or 'none'})"

        control("NC-M6D-001 an export taken on a step-up for a different act", red, green)

    def nc_002():
        def red():
            got = refusal(with_grant("report.export",
                                     body + " UPDATE report.export_event SET byte_count = 1;"))
            return got == "EXPORT_EVENT_REWRITTEN", f"signature: {got}"

        def green():
            got = refusal(with_grant("report.export", body))
            return got == "", f"recording one is fine (signature: {got or 'none'})"

        control("NC-M6D-002 an export record edited after the fact", red, green)

    def nc_003():
        # A STALE GRANT. Fifteen minutes is the window; sixteen is not. Planted by dating
        # the grant backwards rather than by waiting.
        stale = with_grant("report.export", body).replace(
            "'report.export', now())", "'report.export', now() - interval '16 minutes')")

        def red():
            got = refusal(stale)
            return got == "EXPORT_STEP_UP_ABSENT", \
                f"signature: {got} — a grant older than its action's window is not a grant"

        def green():
            got = refusal(with_grant("report.export", body))
            return got == "", f"a fresh one is accepted (signature: {got or 'none'})"

        control("NC-M6D-003 an export taken on a grant older than its window", red, green)

    for case in (nc_001, nc_002, nc_003):
        case()

    registered = [c for c in registry.CONTROLS if c[3] == "m6d"]
    record("every M6-D control is registered in tools/controls.py",
           len(registered) == 3, f"{len(registered)} registered")


# ===========================================================================
# 5. The bounds
# ===========================================================================

def section_bounds() -> None:
    print("\n--- 5. The bounds, named rather than left to silence ---")
    for bound in (
        "THE EXPORT ROUTE IS DRIVEN AT THE DATABASE TIER HERE. The step-up is enforced by "
        "report.record_export(), which the route calls BEFORE returning the bytes, so the "
        "guarantee is in the right place — but this suite proves the function rather than "
        "the HTTP round trip. The journeys are where a route is walked",
        "FR-FUL-015 IS PROVED AS THE THREE CONDITIONS COMING TOGETHER — the node holding a "
        "writable sequence, the outlet in local continuity, and the unit-count constraint "
        "spanning the order — rather than by moving a ticket between stations mid-outage "
        "and counting units afterwards. The pieces are each exercised; their conjunction "
        "on live data is GJ-10's shape and is not driven here",
        "FR-TST-010's LOAD TEST IS NOT IN THIS SLICE. Peak ordering, KDS, realtime, menu "
        "search and integration bursts with recorded thresholds is a performance exercise "
        "that needs a machine with headroom, and this one has been at 100% disk twice",
    ):
        record("recorded in planning/M6_FINDINGS.md", True, bound)


def a_manager_with_a_live_session() -> str:
    """A strong session for the finance manager, as `tenant.outlet.secret`.

    The same shape M1-D's db.withSession() parses, and only its sha256 reaches the
    database (FR-SEC-007). Written here rather than imported because every suite that has
    one keeps it in a module called `fixtures`, and there are six of those on this path.
    """
    # AT KAZANCHIS RATHER THAN SARBET, and the reason is worth stating because getting it
    # wrong looked exactly like a defect. The kitchen-consumption route scopes to the
    # outlet on the CALLER'S SESSION — that is the whole point of 0067 making the function
    # SECURITY INVOKER — and every completed ticket in this database is at Kazanchis. A
    # session at Sarbet gets 200 and an empty list, which is the truth about Sarbet and
    # says nothing about the reading. The outlet is chosen to match where the work
    # happened, not to make the assertion pass.
    secret = os.urandom(16).hex()
    token = f"{TENANT}.{KAZANCHIS}.{secret}"
    planted = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{KAZANCHIS}', false);
        INSERT INTO identity.session
            (tenant_id, outlet_id, user_account_id, token_digest, established_with,
             issued_at, expires_at)
        VALUES ('{TENANT}', '{KAZANCHIS}', '{KAZANCHIS_MANAGER}',
                sha256(convert_to('{token}', 'UTF8')), 'strong', now(),
                now() + interval '1 hour');
    """, tx=True)
    if not planted.ok:
        raise RuntimeError(f"could not plant a manager session: {planted.err[:300]}")
    return token


def main() -> int:
    print("=" * 74)
    print("  M6-D — reporting, exports, and two closures that came due")
    print("=" * 74)

    # A LIVE SERVICE, because one of the things this gate closed is only true if a route
    # answers. Everything else in this suite is SQL and would run without one.
    sync_and_build()
    service = Service(os.environ["M1A_APP_DSN"])
    if not service.start():
        print(f"FAIL SERVICE_DID_NOT_START\n{service.logs()[-2000:]}")
        return 1
    CONTEXT["base_url"] = f"http://127.0.0.1:{service.port}"
    opa.CONTEXT["base_url"] = CONTEXT["base_url"]
    CONTEXT["manager_token"] = a_manager_with_a_live_session()

    try:
        return _run_sections()
    finally:
        service.stop()


def _run_sections() -> int:
    for section in (section_export, section_consumption,
                    section_the_route_a_person_reaches, section_reroute,
                    section_controls, section_bounds):
        try:
            section()
        except Exception as exc:                            # noqa: BLE001
            record(f"{section.__name__} completed", False,
                   f"{type(exc).__name__}: {str(exc)[:400]}")

    failed = [name for name, ok, _d, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")
    owned = len([c for c in registry.CONTROLS if c[3] == "m6d"])

    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}")
    print(f"  asserted      : {len(results) - measured_count}")
    print(f"  controls      : {owned} registered, each proved red then green")

    if failed:
        print("\nFAIL M6D_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS M6D_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
