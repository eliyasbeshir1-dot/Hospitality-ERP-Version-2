#!/usr/bin/env python3
"""M3-C verification: service requests, notifications and the integration runtime.

Three things make this suite different from the ones before it.

THE MACHINE IS NOT DEFINED HERE. SM-SERVICE-REQUEST in the pinned package is
authoritative, and this file reads it at run time exactly as M3-B read
SM-FULFILLMENT-TICKET — including failing closed when it cannot. So is the event
catalog: notify.catalog_event is a copy of the package's events.json, and a copy is only
honest if something checks it against the original on every run.

DEDUPLICATION IS PROVED IN BOTH DIRECTIONS, and neither direction is the requirement on
its own. A window that collapsed everything would pass "no duplicate alerts" and fail
FR-SRV-006; one that collapsed nothing would pass "deliberate repeats survive" and fail
it too. Both are negative controls, and the same control fails in opposite directions.

PRESENCE IS PROVED GONE, NOT FLAGGED. FR-SRV-007B's fence is about what exists rather
than how long it lasts, so the model is asserted against the CATALOG to have nowhere to
put a history, and both discard paths — the session ending and the retention sweep — are
proved independently to DELETE.

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
from fenced import fenced_identifier_pattern                     # noqa: E402
from pg import CommandUnreadable, ProbeFailed, count, run        # noqa: E402
from service import Service, WORKSPACE, sync_and_build           # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import partial_closures                                          # noqa: E402

assert fx.__file__ == str(HERE / "fixtures.py"), f"wrong fixtures module: {fx.__file__}"

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]
CTX = dict(tenant=fx.TENANT, outlet=fx.OUTLET_H1)

results: list[tuple[str, bool, str, str]] = []


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



def replayed_ledgers() -> list[str]:
    """The ledger tables ordering.rebuild_projections() actually loops over.

    Read out of the function's own definition rather than listed here. The rebuild grew
    from one ledger at M3-A to two at M3-B to three at M3-C, and a suite that named them
    would silently be counting the wrong thing the first time a later gate added one —
    the same defect as M3-A's hardcoded schema list, one level down.
    """
    found = re.findall(r"SELECT id FROM ([a-z_]+\.[a-z_]+)",
                       definition("ordering.rebuild_projections(uuid)"))
    if not found:
        raise ProbeFailed("ordering.rebuild_projections(uuid)",
                          "no ledger loop found in the rebuild's definition; a count "
                          "derived from nothing is not a guard")
    return sorted(dict.fromkeys(found))

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


CONTEXT: dict = {}

# An idempotency key is a claim that two calls are the same call. A key written as a
# literal here would be the same claim in every run of this suite, so a second run
# against a database the first one touched is refused by service.claim_idempotency() —
# correctly, because it IS a reused key. The suite is what is wrong in that case, not
# the refusal, so every key it sends carries a nonce minted once per run. Readable
# within a run, distinct across runs, and never the reason a re-run fails.
RUN_NONCE = os.urandom(6).hex()


def idem(label: str) -> str:
    """A run-unique idempotency key that still says what it was for."""
    return f"m3c-{label}-{RUN_NONCE}"


# The same reasoning for the deep-link token: notify.deep_link indexes the DIGEST of a
# token uniquely, so a literal token here would be the same link in every run and the
# second run would collide with the first run's row.
STAFF_LINK_TOKEN = f"m3c-token-staff-{RUN_NONCE}"


# ===========================================================================
# The pinned package, loaded the way the fenced vocabulary is
# ===========================================================================

class PackageUnavailable(Exception):
    """A pinned machine-readable file could not be read.

    Raised, never defaulted. A suite that fell back to a built-in transition table or a
    built-in event list would be checking the schema against itself.
    """


def pinned_machine() -> tuple[list[str], set[tuple[str, str]]]:
    """SM-SERVICE-REQUEST's states and edges, from the package itself."""
    matches = sorted(REPO.glob("docs/*/02_MACHINE_READABLE/state_machines.json"))
    if not matches:
        raise PackageUnavailable(
            "no state_machines.json under docs/; the service request machine cannot be "
            "derived and this suite will not invent one")
    try:
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PackageUnavailable(f"state_machines.json could not be parsed: {error}")

    machines = [m for m in payload.get("state_machines", [])
                if m.get("id") == "SM-SERVICE-REQUEST"]
    if len(machines) != 1:
        raise PackageUnavailable(
            f"expected exactly one SM-SERVICE-REQUEST, found {len(machines)}")
    machine = machines[0]

    states = machine.get("states") or []
    if not states:
        raise PackageUnavailable("SM-SERVICE-REQUEST declares no states")

    edges: set[tuple[str, str]] = set()
    for line in machine.get("transitions") or []:
        head = line.split(":", 1)[0]
        left, _, right = head.partition("->")
        target = right.strip()
        # The package writes 'a/b -> c' where two states share an edge, as
        # SM-FULFILLMENT-TICKET does. Expanded rather than special-cased.
        for source in (part.strip() for part in left.split("/")):
            if source and target:
                edges.add((source, target))
    if not edges:
        raise PackageUnavailable("SM-SERVICE-REQUEST declares no transitions")
    return states, edges


def pinned_events() -> dict[str, str]:
    """Every event id in the package, with the milestone it belongs to."""
    matches = sorted(REPO.glob("docs/*/02_MACHINE_READABLE/events.json"))
    if not matches:
        raise PackageUnavailable(
            "no events.json under docs/; the notification catalog cannot be checked "
            "against the package and this suite will not accept it on trust")
    try:
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PackageUnavailable(f"events.json could not be parsed: {error}")
    catalog = {e["id"]: e["milestone"] for e in payload.get("events", []) if e.get("id")}
    if not catalog:
        raise PackageUnavailable("events.json named no events at all")
    return catalog


# ===========================================================================
# Driving the surface
# ===========================================================================

def guest_get(path: str, token: str) -> dict:
    request = urllib.request.Request(
        f"{CONTEXT['base_url']}{path}", headers={"authorization": f"Guest {token}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        return {"error": error.code, "body": error.read().decode("utf-8", "replace")}


def guest_post(path: str, token: str, body: dict, key: str) -> dict:
    request = urllib.request.Request(
        f"{CONTEXT['base_url']}{path}", method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers={"authorization": f"Guest {token}", "content-type": "application/json",
                 "idempotency-key": key})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        return {"error": error.code, "body": error.read().decode("utf-8", "replace")}


def staff_get(path: str, token: str) -> dict:
    request = urllib.request.Request(
        f"{CONTEXT['base_url']}{path}", headers={"authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        return {"error": error.code}


def render(payload: dict, code: str, locale: str = "") -> dict:
    """Draw the customer surface's service panel and return what it measured."""
    target = WORKSPACE / "m3c_probe.mjs"
    target.write_text((HERE / "render_probe.mjs").read_text(encoding="utf-8"),
                      encoding="utf-8")
    proc = subprocess.run(
        ["node", str(target), CONTEXT["base_url"], fx.TENANT, fx.OUTLET_H1, code,
         json.dumps(payload), locale],
        capture_output=True, text=True, encoding="utf-8", cwd=str(WORKSPACE),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise CommandUnreadable(
            f"the service probe produced no JSON (exit {proc.returncode}): "
            f"{(proc.stdout or proc.stderr)[:400]}")


def rebuild_surface() -> None:
    """Recompile the customer surface from the workspace copy and restart the service."""
    from service import TSC
    proc = subprocess.run(
        [str(WORKSPACE / "node_modules" / ".bin" / TSC),
         "-p", str(WORKSPACE / "pwa" / "tsconfig.json"),
         "--outDir", str(WORKSPACE / "dist" / "public")],
        capture_output=True, text=True, encoding="utf-8", cwd=str(WORKSPACE))
    if proc.returncode != 0:
        raise RuntimeError(f"surface rebuild failed: {proc.stdout or proc.stderr}")
    for name in ("index.html", "app.css", "manifest.webmanifest"):
        (WORKSPACE / "dist" / "public" / name).write_text(
            (WORKSPACE / "pwa" / name).read_text(encoding="utf-8"), encoding="utf-8")
    CONTEXT["restart"]()


# ===========================================================================
# 1. The machine and the catalog are the package's, not this file's
# ===========================================================================

def section_machine(states: list[str], edges: set[tuple[str, str]],
                    events: dict[str, str]) -> None:
    print("\n--- 1. SM-SERVICE-REQUEST and the event catalog come from the package ---")

    declared = [r[0] for r in rows("""
        SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'service' AND t.typname = 'request_state'
        ORDER BY e.enumsortorder;""", dsn=ADMIN)]
    record("the request state type holds exactly the states the package declares",
           declared == states,
           f"package: {states}\nschema : {declared}\n"
           f"{len(states)} states, read out of state_machines.json at run time rather "
           f"than written here")

    schema_edges = {(r[0], r[1]) for r in rows("""
        SELECT from_state::text, to_state::text FROM service.transition;""", dsn=ADMIN)}
    record("the transition table holds exactly the edges the package declares",
           schema_edges == edges,
           f"{len(edges)} in the package, {len(schema_edges)} in the schema. "
           f"Only in the package: {sorted(edges - schema_edges) or 'none'}. "
           f"Only in the schema: {sorted(schema_edges - edges) or 'none'}")

    tampered = run(ADMIN, """
        INSERT INTO service.transition (from_state, to_state, reason)
        VALUES ('completed', 'new', 'invented at runtime');""")
    record("the machine cannot be edited at runtime, by anyone",
           tampered.failed_with("STATE_MACHINE_ALTERED_AT_RUNTIME"),
           tampered.why() or "an edge was added to the machine while the system was "
                             "running; every transition check downstream would then be "
                             "checking a machine somebody widened")

    # --- the event catalog, both directions ---
    catalog = {r[0]: (r[1], r[2] == "t") for r in rows("""
        SELECT event_id, milestone, has_producer::text FROM notify.catalog_event;""",
        dsn=ADMIN)}
    unknown = sorted(k for k in catalog if k not in events)
    record("every kind in the notification catalog is a kind the package names",
           not unknown,
           f"{len(catalog)} kinds; invented here rather than taken from events.json: "
           f"{unknown or 'none'}. A catalog with a kind the package does not have is a "
           f"copy that has started to drift from its original")

    wrong_milestone = sorted(k for k, (m, _p) in catalog.items()
                             if k in events and events[k] != m)
    record("and each one is recorded at the milestone the package puts it at",
           not wrong_milestone,
           f"{wrong_milestone or 'none'}. The milestone is what decides whether a kind "
           f"may have a producer, so a wrong one would let an M4 kind claim one")

    m3_classes = {k for k, (m, _p) in catalog.items() if m == "M3"}
    producers = {k for k, (_m, p) in catalog.items() if p}
    record("every kind claiming a producer belongs to a gate that has landed",
           producers <= m3_classes,
           f"{len(producers)} kinds claim a producer, all at M3. Claiming one at M4 or "
           f"M5a: {sorted(producers - m3_classes) or 'none'} — that would be a stubbed "
           f"domain wearing a real kind's name")

    classes = {r[0] for r in rows("""
        SELECT DISTINCT event_class::text FROM notify.catalog_event;""", dsn=ADMIN)}
    record("all eight classes FR-NOT-001 names are represented",
           classes == {"order", "kitchen", "service_request", "bill", "payment", "tip",
                       "outage", "sync"},
           f"{sorted(classes)}. Bill, payment and tip arrive at M4 and outage and sync at "
           f"M5a; the KINDS exist here with nothing producing them, which is the honest "
           f"way to name an event whose domain is a later gate")

    stubbed = run(APP, f"""
        SELECT notify.emit('{fx.TENANT}', '{fx.OUTLET_H1}', 'EVT-CHECK-PAID', 'order',
                           gen_random_uuid(), gen_random_uuid(), NULL, '{{}}'::jsonb);""",
        **CTX)
    record("and a kind with no producer cannot be emitted",
           stubbed.failed_with("NOTIFICATION_KIND_HAS_NO_PRODUCER"),
           stubbed.why() or "a bill notification was emitted at a gate with no bills. A "
                            "kind with no producer is honest; one that fires is a stub")


# ===========================================================================
# 2. Every ordered pair of states, walked
# ===========================================================================

def legal_paths(states: list[str], edges: set[tuple[str, str]]) -> dict[str, list[str]]:
    """A path of LEGAL edges from the entry state to every state, breadth first.

    The same instrument M3-B ended up with, and for the same reason: setting the source
    state with a plain UPDATE is itself an illegal transition for most states, so a walk
    that did it would score the pair 'refused' without ever attempting the transition it
    meant to test. Every source is REACHED the way a real request reaches it.
    """
    paths: dict[str, list[str]] = {"new": []}
    frontier = ["new"]
    while frontier:
        following: list[str] = []
        for node in frontier:
            for source, target in sorted(edges):
                if source == node and target not in paths:
                    paths[target] = paths[node] + [target]
                    following.append(target)
        frontier = following
    return paths


WALK_FUNCTION = """
CREATE FUNCTION pg_temp.walk_service(p_request uuid, p_plan jsonb, p_user uuid)
RETURNS jsonb
LANGUAGE plpgsql AS $walk$
DECLARE
    v_case     jsonb;
    v_step     text;
    v_target   text;
    v_legal    boolean;
    v_accepted text[] := '{}';
    v_refused  text[] := '{}';
    v_reached  text[] := '{}';
BEGIN
    FOR v_case IN SELECT * FROM jsonb_array_elements(p_plan) LOOP
      BEGIN
        FOREACH v_step IN ARRAY
            ARRAY(SELECT jsonb_array_elements_text(v_case -> 'path')) LOOP
            PERFORM set_config('service.applying_event', 'yes', true);
            -- The assignee travels with the state. SM-SERVICE-REQUEST's first invariant
            -- is that every ACTIVE request has one, and it is a CHECK on the table — so
            -- a walk that moved the state alone would be refused by the invariant rather
            -- than by the transition guard it is testing.
            UPDATE service.service_request
               SET state = v_step::service.request_state, assigned_user_id = p_user,
                   completion_status = CASE
                       WHEN v_step IN ('completed', 'unresolved')
                       THEN 'done'::service.completion_status END
             WHERE id = p_request;
        END LOOP;

        IF (SELECT state::text FROM service.service_request WHERE id = p_request)
           <> (v_case ->> 'source') THEN
            RAISE EXCEPTION 'UNREACHED';
        END IF;
        v_reached := v_reached || (v_case ->> 'source');

        FOREACH v_target IN ARRAY
            ARRAY(SELECT jsonb_array_elements_text(v_case -> 'targets')) LOOP
            v_legal := (v_case -> 'legal') ? v_target;
            BEGIN
                PERFORM set_config('service.applying_event', 'yes', true);
                UPDATE service.service_request
                   SET state = v_target::service.request_state,
                       assigned_user_id = p_user,
                       -- The other invariant that travels with the state: a request
                       -- cannot BE completed or unresolved without saying how it went.
                       -- Same reasoning as the assignee above — walking the state alone
                       -- would be refused by an invariant rather than by the transition
                       -- guard under test.
                       completion_status = CASE
                           WHEN v_target IN ('completed', 'unresolved')
                           THEN 'done'::service.completion_status END
                 WHERE id = p_request;
                IF NOT v_legal THEN
                    v_accepted := v_accepted
                        || ((v_case ->> 'source') || ' -> ' || v_target);
                END IF;
                -- plpgsql VARIABLES survive a subtransaction rollback while database
                -- changes do not, which is the asymmetry this walk is built on.
                RAISE EXCEPTION 'UNDO';
            EXCEPTION WHEN others THEN
                IF SQLERRM <> 'UNDO' AND v_legal THEN
                    v_refused := v_refused
                        || ((v_case ->> 'source') || ' -> ' || v_target
                            || ': ' || SQLERRM);
                END IF;
            END;
        END LOOP;

        RAISE EXCEPTION 'UNDO';
      EXCEPTION WHEN others THEN
        NULL;
      END;
    END LOOP;

    RETURN jsonb_build_object('accepted_illegal', to_jsonb(v_accepted),
                              'refused_legal', to_jsonb(v_refused),
                              'sources_reached', to_jsonb(v_reached));
END;
$walk$;
"""


def walk_machine(states: list[str], edges: set[tuple[str, str]], request: str) -> dict:
    """Attempt every ordered pair against the DATABASE, and report what it allowed."""
    paths = legal_paths(states, edges)
    plan = [{"source": source,
             "path": paths[source],
             "targets": [t for t in states if t != source],
             "legal": [t for t in states if t != source and (source, t) in edges]}
            for source in states if source in paths]
    payload = json.dumps(plan).replace("'", "''")
    res = run(ADMIN, f"""
        {WALK_FUNCTION}
        SELECT set_config('service.applying_event', 'yes', true);
        UPDATE service.service_request SET state = 'new' WHERE id = '{request}';
        SELECT pg_temp.walk_service('{request}', '{payload}'::jsonb, '{fx.USER}');
    """, tx=True)
    if not res.ok:
        raise ProbeFailed("service state machine walk", res.err)
    outcome = json.loads(res.out.strip().splitlines()[-1])
    outcome["unreachable"] = [s for s in states if s not in paths]
    outcome["pairs"] = len(states) * (len(states) - 1)
    return outcome


def unrouted_request(seated: dict) -> str:
    """A request that exists and has not been routed, for the walk to start from.

    service.raise_request() routes as its last act, which is right: a request nobody is
    accountable for is what the machine's first invariant forbids. The walk needs one in
    the ENTRY state, so this writes the same 'raised' event to the same ledger and
    applies it through the same fold, and simply does not call route_request() after.
    Nothing is stubbed — it is the identical event, one step short.
    """
    res = run(APP, f"""
        WITH t AS (
            SELECT id, sla_seconds FROM service.request_type
             WHERE tenant_id = '{fx.TENANT}' AND code = 'call_waiter'
        ), e AS (
            INSERT INTO service.service_request_event
                (tenant_id, outlet_id, service_request_id, sequence_number, kind,
                 actor_kind, actor_guest_session_id, correlation_id, after)
            SELECT '{fx.TENANT}', '{fx.OUTLET_H1}', gen_random_uuid(), 1, 'raised',
                   'guest', '{seated["guest"]}', gen_random_uuid(),
                   jsonb_build_object(
                       'table_session_id', '{seated["session"]}',
                       'request_type_id', t.id,
                       'origin', 'guest',
                       'raised_by_guest_session_id', '{seated["guest"]}',
                       'customer_locale', 'en',
                       'dedup_group', gen_random_uuid(),
                       'repeat_ordinal', 1,
                       'sla_seconds', t.sla_seconds)
            FROM t
            RETURNING id, service_request_id
        )
        SELECT service.apply_request_event(e.id), e.service_request_id::text FROM e;
    """, tx=True, **CTX)
    if not res.ok:
        raise ProbeFailed("unrouted request", res.err)
    return res.rows[-1][-1].strip()


def section_transitions(states: list[str], edges: set[tuple[str, str]]) -> None:
    print("\n--- 2. Every ordered pair of service request states, walked ---")

    outcome = walk_machine(states, edges, CONTEXT["walk_request"])

    record("every state the machine declares is reachable from the entry state",
           not outcome["unreachable"]
           and set(outcome["sources_reached"]) == set(states),
           f"reached {len(outcome['sources_reached'])} of {len(states)}: missing "
           f"{sorted(set(states) - set(outcome['sources_reached'])) or 'none'}. Each "
           f"source is reached by LEGAL moves from 'new', so the attempt that follows is "
           f"made from a state a real request can be in")

    record("every ILLEGAL transition is refused by the database",
           not outcome["accepted_illegal"],
           f"{outcome['pairs']} ordered pairs attempted, {len(edges)} legal and "
           f"{outcome['pairs'] - len(edges)} illegal. Accepted but illegal: "
           f"{outcome['accepted_illegal'] or 'none'}. Attempted against the TRIGGER, not "
           f"through the service functions: a walk through them would prove the "
           f"functions refuse and say nothing about the database")

    record("every LEGAL transition is accepted",
           not outcome["refused_legal"],
           f"{outcome['refused_legal'] or f'all {len(edges)} legal edges accepted'}. A "
           f"machine that refused everything would pass the check above and be useless")

    still_new = scalar(f"""
        SELECT state::text FROM service.service_request
        WHERE id = '{CONTEXT["walk_request"]}';""")
    record("the walk left the request exactly where it found it",
           still_new == "new",
           f"the walk request reads '{still_new}'. Every attempt runs in a "
           f"subtransaction that is rolled back whether it was refused or allowed")

    start = run(ADMIN, f"""
        SELECT set_config('service.applying_event', 'yes', true);
        INSERT INTO service.service_request
            (id, tenant_id, outlet_id, table_session_id, request_type_id, origin, state,
             raised_by_user_id, customer_locale, dedup_group, repeat_ordinal, raised_at,
             sla_due_at, assigned_user_id, correlation_id, ledger_sequence)
        SELECT gen_random_uuid(), tenant_id, outlet_id, table_session_id, request_type_id,
               'staff', 'completed', '{fx.USER}', customer_locale, gen_random_uuid(), 1,
               now(), now(), '{fx.USER}', correlation_id, 1
        FROM service.service_request WHERE id = '{CONTEXT["walk_request"]}';""", tx=True)
    record("a request cannot be inserted anywhere but the machine's entry state",
           start.failed_with("ILLEGAL_SERVICE_TRANSITION"),
           start.why() or "a request was created already completed; the transition "
                          "trigger only sees UPDATEs, so a row inserted at the end would "
                          "never have transitioned at all")


# ===========================================================================
# 3. The catalog, routing and the lifecycle (FR-SRV-001 … FR-SRV-005, FR-SRV-008)
# ===========================================================================

def raise_request(seated: dict, code: str, *, key: str | None = None,
                  deliberate: bool = False, note: str | None = None,
                  user: str | None = None):
    return run(APP, f"""
        SELECT service.raise_request('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{seated["session"]}', '{fx.request_type(code)}',
            '{key or idem(os.urandom(6).hex())}',
            {"NULL" if user else f"'{seated['guest']}'"},
            {f"'{user}'" if user else "NULL"}, NULL,
            {f"$n${note}$n$" if note else "NULL"}, {str(deliberate).lower()});""", **CTX)


def section_catalog_and_lifecycle() -> None:
    print("\n--- 3. The translated catalog, routing, and the request lifecycle "
          "(FR-SRV-001, 002, 003, 005, 008) ---")

    catalog = rows(f"""
        SELECT code, canonical_name, sla_seconds::text, dedup_window_seconds::text
        FROM service.request_type WHERE tenant_id = '{fx.TENANT}' ORDER BY code;""")
    named = {"call_waiter", "water", "cutlery", "assistance", "missing_item",
             "packaging", "bill"}
    record("FR-SRV-001: every request type the requirement names can be raised",
           {r[0] for r in catalog} == named,
           f"{sorted(r[0] for r in catalog)}. Rows, not enum labels: an outlet that does "
           f"not serve packaged food removes that one and an outlet with a sommelier "
           f"adds a type this schema never heard of, with no code change")

    per_type = {r[0]: (r[2], r[3]) for r in catalog}
    record("and each carries its own deadline and its own deduplication window",
           len({v[0] for v in per_type.values()}) > 1
           and len({v[1] for v in per_type.values()}) > 1,
           f"{per_type}. Water is not an accessibility request and should not share a "
           f"deadline with one; two taps a minute apart for help are two asks")

    labels = rows(f"""
        SELECT tr.locale::text, count(*)::text
        FROM menu.translation tr
        WHERE tr.tenant_id = '{fx.TENANT}' AND tr.entity = 'service_request_type'
          AND tr.state = 'approved'
        GROUP BY 1 ORDER BY 1;""")
    record("the labels are approved through M2-A's workflow, not a second store",
           {r[0] for r in labels} == {"am", "ar"},
           f"{labels} approved translations in menu.translation. English is the source on "
           f"the catalog row itself (FR-I18N-007); the other two go through draft, "
           f"review and approval with a reviewer and a timestamp, because that is the "
           f"workflow M2-A built and a second one would need all of it again")

    unapproved = run(APP, f"""
        UPDATE menu.translation SET state = 'approved', reviewed_by_user_id = NULL,
               approved_at = NULL
         WHERE tenant_id = '{fx.TENANT}' AND entity = 'service_request_type';""",
        rollback=True, **CTX)
    record("and an approval nobody reviewed is refused by that workflow, unchanged",
           not unapproved.ok,
           unapproved.why() or "a service request label was approved with no reviewer "
                               "and no timestamp; reusing M2-A's store is only worth "
                               "anything if its guarantees come with it")

    # --- routing ---
    fx.clear_presence()
    seated = fx.a_seated_guest()
    CONTEXT["seated"] = seated
    fx.set_presence("available")

    raised = raise_request(seated, "water", key=idem("route-1"))
    record("FR-SRV-002: a request raised by a seated guest routes to somebody",
           raised.ok,
           raised.why() or "raised and routed in one call: a request with nobody "
                           "accountable is what SM-SERVICE-REQUEST's first invariant "
                           "forbids")
    request_id = (raised.scalar or "").strip()
    CONTEXT["request"] = request_id

    routed = rows(f"""
        SELECT sr.state::text, sr.assigned_user_id::text, d.basis,
               d.considered_count::text, d.table_node_id::text,
               coalesce(d.service_area_id::text, '-')
        FROM service.service_request sr
        JOIN service.request_routing_decision d
          ON d.tenant_id = sr.tenant_id AND d.service_request_id = sr.id
        WHERE sr.id = '{request_id}';""")
    record("and the four inputs the requirement names are on the record beside the choice",
           len(routed) == 1 and routed[0][0] == "routed" and routed[0][1] == fx.USER
           and routed[0][3].isdigit() and routed[0][4],
           f"{routed}. Table assignment, service area, role and availability, kept — "
           f"without them a routing defect and a staffing gap look identical afterwards")

    # Availability is a real input, not a decoration: with nobody available the same
    # request routes on a different basis.
    fx.clear_presence()
    away = raise_request(seated, "cutlery", key=idem("route-2"))
    basis = scalar(f"""
        SELECT d.basis FROM service.request_routing_decision d
        JOIN service.service_request sr ON sr.id = d.service_request_id
        WHERE sr.request_type_id = '{fx.request_type("cutlery")}'
        ORDER BY d.decided_at DESC LIMIT 1;""")
    record("availability changes the answer, so it is an input rather than a decoration",
           away.ok and "available" in basis
           and basis != "available in the outlet, holding the role",
           f"with nobody available the basis reads {basis!r}. Somebody is still "
           f"accountable — an unanswered request with a name on it beats one with none — "
           f"and the record says the assignment was made without availability")
    fx.set_presence("available")

    # --- acknowledgement, work, completion ---
    stranger = run(APP, f"""
        SELECT service.acknowledge_request('{fx.TENANT}', '{request_id}',
                                           '{fx.USER_SUPERVISOR}');""", **CTX)
    record("FR-SRV-003: somebody else cannot accept work assigned to you",
           stranger.failed_with("REQUEST_NOT_YOURS"),
           stranger.why() or "a request assigned to one person was acknowledged by "
                             "another; an assignment anybody may take is not one")

    acked = run(APP, f"""
        SELECT service.acknowledge_request('{fx.TENANT}', '{request_id}', '{fx.USER}');""",
        **CTX)
    started = run(APP, f"""
        SELECT service.start_request('{fx.TENANT}', '{request_id}', '{fx.USER}');""", **CTX)
    record("the assignee accepts it and begins",
           acked.ok and started.ok,
           f"{acked.why()}{started.why()}routed -> acknowledged -> in_progress, each an "
           f"edge the package declares")

    silent = run(APP, f"""
        SELECT set_config('service.applying_event', 'yes', true);
        UPDATE service.service_request SET state = 'completed'
         WHERE id = '{request_id}';""", tx=True, **CTX)
    record("FR-SRV-005: a request cannot reach completion without saying how it went",
           not silent.ok,
           silent.why() or "a request was completed with no completion status. The "
                           "constraint is on the TABLE, so there is no path — through a "
                           "function or around one — that closes a request silently")

    unexplained = run(APP, f"""
        SELECT service.complete_request('{fx.TENANT}', '{request_id}', '{fx.USER}',
                                        'not_possible', NULL, 'we had none');""", **CTX)
    record("and a request that could not be done owes a registered reason",
           unexplained.failed_with("COMPLETION_REASON_INVALID"),
           unexplained.why() or "a request was abandoned with no registered reason code")

    done = run(APP, f"""
        SELECT service.complete_request('{fx.TENANT}', '{request_id}', '{fx.USER}',
                                        'done', NULL, 'poured');""", **CTX)
    final = rows(f"""
        SELECT state::text, completion_status::text, coalesce(completion_note, '-'),
               (completed_at IS NOT NULL)::text
        FROM service.service_request WHERE id = '{request_id}';""")
    record("a completed request records the outcome and when it happened",
           done.ok and final and final[0][0] == "completed"
           and final[0][1] == "done" and final[0][3] in ("t", "true"),
           f"{done.why() or final}. SM-SERVICE-REQUEST's second invariant asks for the "
           f"acknowledgement and completion timestamps to be retained, and they are")

    # --- FR-SRV-008, staff-raised tasks ---
    task = raise_request(seated, "missing_item", key=idem("task-1"), user=fx.USER,
                         note="table asked about a missing side")
    task_row = rows(f"""
        SELECT origin::text, coalesce(raised_by_user_id::text, '-'),
               coalesce(raised_by_guest_session_id::text, '-')
        FROM service.service_request WHERE id = '{(task.scalar or '').strip()}';""")
    record("FR-SRV-008: a staff task is the same aggregate with a different origin",
           task.ok and task_row and task_row[0] == ["staff", fx.USER, "-"],
           f"{task.why() or task_row}. A second table for internal tasks would be two "
           f"models of one thing — the same routing, the same SLA, the same completion — "
           f"and the two would drift")


# ===========================================================================
# 4. Deduplication, in both directions (FR-SRV-006, FR-NOT-007)
# ===========================================================================

def live_requests(session: str, code: str) -> int:
    return count(APP, f"""
        SELECT count(*) FROM service.service_request
        WHERE table_session_id = '{session}'
          AND request_type_id = '{fx.request_type(code)}';""", **CTX)


def section_deduplication() -> None:
    print("\n--- 4. Deduplication collapses an accident and preserves a deliberate "
          "repeat (FR-SRV-006, FR-NOT-007) ---")

    fx.set_presence("available")
    seated = fx.a_seated_guest(table=fx.TABLE_TWO)
    CONTEXT["dedup_seated"] = seated

    first = raise_request(seated, "water", key=idem("dedup-1"))
    one = (first.scalar or "").strip()
    record("a first ask raises a request",
           first.ok and live_requests(seated["session"], "water") == 1,
           f"{first.why() or one[:8]}, 1 request on the session")

    # --- the accidental side ---
    second = raise_request(seated, "water", key=idem("dedup-2"))
    record("a second tap inside the window collapses into the one already open",
           second.ok and (second.scalar or "").strip() == one
           and live_requests(seated["session"], "water") == 1,
           f"returned {(second.scalar or '').strip()[:8]} against the first {one[:8]}; "
           f"still 1 request. The caller is told which request theirs became rather than "
           f"given an error: the thing they asked for is already open, and that is a "
           f"success")

    alerts = count(APP, f"""
        SELECT count(*) FROM notify.notification n
        WHERE n.subject_kind = 'service_request' AND n.subject_id = '{one}'
          AND n.event_id = 'EVT-SERVICE-REQUESTED';""", **CTX)
    record("and no second alert was raised for it",
           alerts == 1,
           f"{alerts} EVT-SERVICE-REQUESTED notification(s) for that request. This is the "
           f"half FR-SRV-006 shares with FR-NOT-007: uncontrolled duplicate ALERTS are "
           f"what the requirement is about, and the request collapsing is how they are "
           f"avoided")

    # --- the deliberate side, inside the same window ---
    deliberate = raise_request(seated, "water", key=idem("dedup-3"), deliberate=True)
    after = live_requests(seated["session"], "water")
    ordinals = [r[0] for r in rows(f"""
        SELECT repeat_ordinal::text FROM service.service_request
        WHERE table_session_id = '{seated["session"]}'
          AND request_type_id = '{fx.request_type("water")}'
        ORDER BY repeat_ordinal;""")]
    record("a DELIBERATE repeat inside the same window raises a new request",
           deliberate.ok and (deliberate.scalar or "").strip() != one and after == 2,
           f"{after} requests, ordinals {ordinals}. A guest who genuinely needs water "
           f"twice must be able to ask twice — a window that suppressed this would "
           f"satisfy half of FR-SRV-006 and fail the requirement")

    groups = count(APP, f"""
        SELECT count(DISTINCT dedup_group) FROM service.service_request
        WHERE table_session_id = '{seated["session"]}'
          AND request_type_id = '{fx.request_type("water")}';""", **CTX)
    record("and the repeats stay one conversation, numbered",
           groups == 1 and ordinals == ["1", "2"],
           f"{groups} group, ordinals {ordinals}. 'The third time I asked for water' is "
           f"answerable, which it would not be if each repeat were unrelated")

    # --- outside the window, without the flag ---
    run(ADMIN, f"""
        SELECT set_config('service.applying_event', 'yes', true);
        UPDATE service.service_request
           SET raised_at = raised_at - interval '10 minutes'
         WHERE table_session_id = '{seated["session"]}'
           AND request_type_id = '{fx.request_type("water")}';""", tx=True)
    later = raise_request(seated, "water", key=idem("dedup-4"))
    record("an ordinary ask long after the window is a new request too",
           later.ok and live_requests(seated["session"], "water") == 3,
           f"{live_requests(seated['session'], 'water')} requests. 'Rapid repeated taps' "
           f"is the accident the requirement names; asking again ten minutes later is a "
           f"person asking again")

    # --- and a retry is neither ---
    retry_key = idem("dedup-retry")
    retry = raise_request(seated, "cutlery", key=retry_key)
    same = raise_request(seated, "cutlery", key=retry_key)
    record("FR-INT-005: the SAME command arriving twice returns the original outcome",
           retry.ok and same.ok
           and (retry.scalar or "").strip() == (same.scalar or "").strip()
           and live_requests(seated["session"], "cutlery") == 1,
           f"one request under one key, returned twice. A retry is one ask that arrived "
           f"twice; a duplicate tap is two asks that look alike; a deliberate repeat is "
           f"two asks that are meant to be two. Three different questions, and conflating "
           f"any two of them breaks one of the requirements")

    reused = run(APP, f"""
        SELECT service.raise_request('{fx.TENANT}', '{fx.OUTLET_H1}',
            '{seated["session"]}', '{fx.request_type("packaging")}', '{retry_key}',
            '{seated["guest"]}');""", **CTX)
    record("and a key reused for a different command is refused rather than answered",
           reused.failed_with("IDEMPOTENCY_KEY_REUSED"),
           reused.why() or "a key that first raised cutlery answered a packaging request "
                           "with the cutlery outcome, which is an answer to a question "
                           "nobody asked")


# ===========================================================================
# 5. Presence is ephemeral, and provably gone (FR-SRV-007A, FR-SRV-007B)
# ===========================================================================

def section_presence() -> None:
    print("\n--- 5. Three presence states, discarded rather than marked "
          "(FR-SRV-007A, FR-SRV-007B) ---")

    states = [r[0] for r in rows("""
        SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'service' AND t.typname = 'presence_state'
        ORDER BY e.enumsortorder;""")]
    record("exactly the three states the package names, and no fourth",
           states == ["available", "temporarily_unavailable", "offline"],
           f"{states}. There is no 'on_break': break is a fenced term and a break state "
           f"is not a workforce model, which is what FR-SRV-007B exists to prohibit")

    # --- the model has nowhere to put a history ---
    key = rows("""
        SELECT a.attname FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = 'service.staff_presence'::regclass AND i.indisprimary
        ORDER BY a.attnum;""", dsn=ADMIN)
    record("the primary key is the PERSON, so a second row for them cannot exist",
           [r[0] for r in key] == ["tenant_id", "outlet_id", "user_account_id"],
           f"{[r[0] for r in key]}. A history cannot accumulate even by accident: there "
           f"is no key under which a second observation of the same person could be "
           f"stored")

    history = rows("""
        SELECT a.attname FROM pg_attribute a
        WHERE a.attrelid = 'service.staff_presence'::regclass
          AND a.attnum > 0 AND NOT a.attisdropped
          AND a.attname ~* '(previous|prior|ended|closed|superseded|history|from_state|'
                           'until|valid_to|effective_to)'
        ORDER BY a.attname;""", dsn=ADMIN)
    record("and no column anywhere on it could record when a state ENDED",
           not history,
           f"{[r[0] for r in history] or 'none'}. Asserted against the CATALOG rather "
           f"than against a comment, the way M3-A asserted no order carries a table id: "
           f"a property of the model, so there is nothing here for a later change to get "
           f"wrong quietly")

    fx.clear_presence()
    session_id = fx.set_presence("available")
    fx.set_presence("temporarily_unavailable", session_id=session_id)
    fx.set_presence("available", session_id=session_id)
    live = rows(f"""
        SELECT user_account_id::text, state::text FROM service.staff_presence
        WHERE tenant_id = '{fx.TENANT}';""")
    record("three changes in a row leave one row, overwritten in place",
           len(live) == 1 and live[0][1] == "available",
           f"{live}. Not three rows, not one row and two archived ones: one")

    # --- discard path one: the session that asserted it ends ---
    gone = run(APP, f"""
        SELECT service.end_presence_for_session('{session_id}');""", **CTX)
    remaining = count(APP, f"""
        SELECT count(*) FROM service.staff_presence
        WHERE tenant_id = '{fx.TENANT}';""", **CTX)
    record("discard path one: ending the session that asserted it DELETES the row",
           gone.ok and remaining == 0,
           f"{gone.why() or gone.scalar} row(s) discarded, {remaining} left. Deleted, not "
           f"flagged and not set to 'offline': a row saying somebody has been offline "
           f"since Tuesday is a record of their Tuesday")

    # --- discard path two: the retention sweep ---
    session_id = fx.set_presence("available")
    run(ADMIN, f"""
        UPDATE service.staff_presence SET observed_at = now() - interval '3 hours'
        WHERE tenant_id = '{fx.TENANT}';""")
    policy = run(APP, f"""
        INSERT INTO config.retention_policy
            (tenant_id, outlet_id, target_schema, target_table, age_column, retain_for,
             action)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'service', 'staff_presence',
                'observed_at', interval '1 hour', 'purge')
        ON CONFLICT DO NOTHING;""", **CTX)
    swept = rows(f"""
        SELECT target, rows_affected::text FROM config.apply_retention('{fx.TENANT}')
        WHERE target = 'service.staff_presence';""")
    after = count(APP, f"""
        SELECT count(*) FROM service.staff_presence
        WHERE tenant_id = '{fx.TENANT}';""", **CTX)
    record("discard path two: the retention sweep DELETES it, and it is M1-C's sweep",
           policy.ok and swept and swept[0][1] == "1" and after == 0,
           f"{swept}, {after} row(s) left. config.apply_retention() is the engine M1-C "
           f"built and M2-B repaired when an archive policy was silently deleting; a "
           f"second sweep written here would be a second thing to get wrong")

    bound = count(APP, f"""
        SELECT count(*) FROM config.retention_policy
        WHERE tenant_id = '{fx.TENANT}' AND target_schema = 'service'
          AND target_table = 'staff_presence';""", **CTX)
    record("FR-SRV-007B: presence records carry a retention bound",
           bound == 1,
           f"{bound} retention policy targeting service.staff_presence. The requirement "
           f"asks for a bound and this is it — a window an operator set, swept by the "
           f"one engine, deleting rather than marking")


# ===========================================================================
# 6. SLA, escalation and critical alerts (FR-SRV-004, FR-NOT-005, FR-NOT-011)
# ===========================================================================

def section_sla_and_escalation() -> None:
    print("\n--- 6. Deadlines, escalation to an alternate, and who a critical alert "
          "reaches (FR-SRV-004, FR-NOT-005, FR-NOT-011) ---")

    fx.set_presence("available")
    seated = fx.a_seated_guest()
    raised = raise_request(seated, "assistance", key=idem("sla-1"))
    request = (raised.scalar or "").strip()

    deadline = rows(f"""
        SELECT (sla_due_at > raised_at)::text,
               floor(extract(epoch FROM sla_due_at - raised_at))::text
        FROM service.service_request WHERE id = '{request}';""")
    record("FR-SRV-004: a request carries a deadline taken from its own type",
           deadline and deadline[0][0] in ("t", "true")
           and deadline[0][1] == "120",
           f"{deadline}. 120 seconds for assistance against 300 for water — the deadline "
           f"belongs to the kind of ask, not to the system")

    early = run(APP, f"""
        SELECT service.escalate_overdue_requests('{fx.TENANT}', '{fx.OUTLET_H1}');""",
        **CTX)
    # About THIS request, not about the sweep's total. escalate_overdue_requests() sweeps
    # the whole outlet, so on a database this suite has already run against the total also
    # counts requests an earlier run left open and long overdue — a number that says
    # nothing about selectivity and makes the check fail for the wrong reason. A sweep
    # that escalated everything would escalate this one too, which is the property.
    early_state = rows(f"""
        SELECT sr.state::text, count(e.id)::text
        FROM service.service_request sr
        LEFT JOIN service.request_escalation e ON e.service_request_id = sr.id
        WHERE sr.id = '{request}' GROUP BY 1;""")
    record("a request inside its deadline is not escalated",
           early.ok and early_state and early_state[0] == ["routed", "0"],
           f"{early.why() or early_state}, {early.scalar} escalated across the outlet. "
           f"A sweep that escalated everything would have taken this one with it, and "
           f"would then pass the check below and mean nothing")

    run(ADMIN, f"""
        SELECT set_config('service.applying_event', 'yes', true);
        UPDATE service.service_request SET sla_due_at = now() - interval '90 seconds'
         WHERE id = '{request}';""", tx=True)
    late = run(APP, f"""
        SELECT service.escalate_overdue_requests('{fx.TENANT}', '{fx.OUTLET_H1}');""",
        **CTX)
    moved = rows(f"""
        SELECT sr.state::text, sr.assigned_user_id::text, e.from_user_id::text,
               e.to_user_id::text, e.overdue_seconds::text, e.basis
        FROM service.service_request sr
        JOIN service.request_escalation e ON e.service_request_id = sr.id
        WHERE sr.id = '{request}';""")
    record("past its deadline it escalates to an ALTERNATE, with the overdue time",
           late.ok and moved and moved[0][0] == "escalated"
           and moved[0][2] == fx.USER and moved[0][3] == fx.USER_SUPERVISOR
           and int(moved[0][4]) >= 89,
           f"{late.why() or moved}. FR-SRV-004 says supervisor or alternate, and an "
           f"escalation that could land back on the person who did not answer would not "
           f"be one — the constraint on the table refuses that outright")

    alternate = run(APP, f"""
        SELECT service.acknowledge_request('{fx.TENANT}', '{request}',
                                           '{fx.USER_SUPERVISOR}');""", **CTX)
    record("and the alternate can accept it — 'escalated -> acknowledged' is an edge",
           alternate.ok,
           alternate.why() or "the supervisor accepted an escalated request, which is "
                              "the package's own edge and the point of escalating")

    # --- FR-NOT-005 ---
    critical = rows(f"""
        SELECT ce.severity, dl.recipient_user_id::text
        FROM notify.notification n
        JOIN notify.catalog_event ce ON ce.event_id = n.event_id
        JOIN notify.notice dl ON dl.notification_id = n.id
        WHERE n.subject_id = '{request}' AND n.event_id = 'EVT-SERVICE-ESCALATED';""")
    record("FR-NOT-005: a critical alert goes to accountable staff, not to the subject",
           critical and all(r[0] == "critical" for r in critical)
           and {r[1] for r in critical} == {fx.USER_SUPERVISOR},
           f"{critical}. Who is accountable is read from the outlet's service policy: an "
           f"escalation that told only the person who had already missed it would be an "
           f"alert nobody acted on")

    silent = run(APP, f"""
        UPDATE config.policy SET payload = payload - 'critical_alert_role_code'
         WHERE id = '{fx.SERVICE_POLICY}';
        SELECT * FROM notify.accountable_staff('{fx.TENANT}', '{fx.OUTLET_H1}');""",
        rollback=True, **CTX)
    record("and an outlet that has not said who is accountable is refused, not guessed at",
           silent.failed_with("SERVICE_POLICY_INCOMPLETE"),
           silent.why() or "a critical alert picked an accountable person on the "
                           "restaurant's behalf. Same rule M3-B applied to the capacity "
                           "response: a commercial decision is not a default")

    no_role = run(APP, f"""
        UPDATE config.policy SET payload = payload - 'service_escalation_role_code'
         WHERE id = '{fx.SERVICE_POLICY}';
        SELECT service.escalate_overdue_requests('{fx.TENANT}', '{fx.OUTLET_H1}');""",
        rollback=True, **CTX)
    record("FR-NOT-011: escalation without a configured target is refused too",
           no_role.failed_with("SERVICE_POLICY_INCOMPLETE"),
           no_role.why() or "requests escalated to a role nobody named")

    # --- expiry ---
    expiring = fx.a_seated_guest(table=fx.TABLE_TWO)
    fx.set_presence("available")
    raise_request(expiring, "cutlery", key=idem("expire-1"))
    expired = run(APP, f"""
        SELECT service.expire_requests_for_session('{fx.TENANT}',
                                                   '{expiring["session"]}');""", **CTX)
    states = [r[0] for r in rows(f"""
        SELECT state::text FROM service.service_request
        WHERE table_session_id = '{expiring["session"]}';""")]
    record("'routed -> expired' when the session closes, which is the package's own edge",
           expired.ok and states == ["expired"],
           f"{expired.why() or ''}{states}. A request nobody answered before the table "
           f"got up is expired rather than left open forever")


# ===========================================================================
# 7. Notifications: nothing sensitive, in a payload or a log (FR-NOT-010)
# ===========================================================================

# Values planted into every field a notification could conceivably pick up, then hunted
# for in the payloads and the logs. M1-D proved log redaction this way and this is the
# same instrument: a value nobody would type by accident, searched for exhaustively.
CANARIES = {
    "guest nickname": "CANARY-NICKNAME-8f21",
    "customer note": "CANARY-NOTE-4c73",
    "staff display name": "CANARY-STAFF-9a05",
}


def section_no_sensitive_leakage() -> None:
    print("\n--- 7. No customer, payment or authentication data in a payload or a log "
          "(FR-NOT-010) ---")

    fx.set_presence("available")
    seated = fx.a_seated_guest()
    run(APP, f"""
        UPDATE service.guest_session SET display_nickname = '{CANARIES["guest nickname"]}'
         WHERE id = '{seated["guest"]}';""", **CTX)
    raised = raise_request(seated, "assistance", key=idem("leak-1"),
                           note=CANARIES["customer note"])
    request = (raised.scalar or "").strip()
    run(APP, f"""
        SELECT service.acknowledge_request('{fx.TENANT}', '{request}', '{fx.USER}');""",
        **CTX)
    run(APP, f"""
        SELECT notify.send_pending('{fx.TENANT}', '{fx.OUTLET_H1}');""", **CTX)

    payloads = "\n".join(r[0] for r in rows(f"""
        SELECT payload::text FROM notify.notification
        WHERE tenant_id = '{fx.TENANT}';"""))
    leaked = sorted(name for name, value in CANARIES.items() if value in payloads)
    record("no notification payload carries a nickname, a note or a staff name",
           not leaked,
           f"{len(payloads.splitlines())} payload(s) searched for "
           f"{len(CANARIES)} planted values; found: {leaked or 'none'}. The note the "
           f"guest typed is the sharpest of the three — it is customer-authored text "
           f"that a payload could carry innocently and that a notification centre would "
           f"then show to anyone with a badge")

    # The absence is structural, not a habit. Enumerated from the catalog: every key any
    # payload has ever carried, checked against what the constraint permits.
    used = {r[0] for r in rows(f"""
        SELECT DISTINCT k FROM notify.notification n,
             LATERAL jsonb_object_keys(n.payload) AS k
        WHERE n.tenant_id = '{fx.TENANT}';""")}
    refused = run(ADMIN, f"""
        INSERT INTO notify.notification
            (id, tenant_id, outlet_id, event_id, subject_kind, subject_id,
             correlation_id, dedup_key, payload)
        VALUES (gen_random_uuid(), '{fx.TENANT}', '{fx.OUTLET_H1}',
                'EVT-SERVICE-REQUESTED', 'service_request', gen_random_uuid(),
                gen_random_uuid(), 'leak-probe',
                '{{"guest_name": "Abebe"}}'::jsonb);""")
    record("and the table refuses a key that is not on the allowlist at all",
           refused.failed_with("23514"),
           f"{refused.why() or 'a guest name was stored in a payload'}. Keys actually "
           f"used: {sorted(used)}. Enforced by a CHECK, so the absence is a property of "
           f"the table rather than of whoever writes the next emitter")

    prose = run(ADMIN, f"""
        INSERT INTO notify.notification
            (id, tenant_id, outlet_id, event_id, subject_kind, subject_id,
             correlation_id, dedup_key, payload)
        VALUES (gen_random_uuid(), '{fx.TENANT}', '{fx.OUTLET_H1}',
                'EVT-SERVICE-REQUESTED', 'service_request', gen_random_uuid(),
                gen_random_uuid(), 'leak-probe-2',
                jsonb_build_object('reason_code', repeat('x', 200)));""")
    record("an ALLOWED key carrying prose is refused too, which is the same leak",
           prose.failed_with("23514"),
           prose.why() or "a 200-character value travelled under an allowed key. A key "
                          "allowlist on its own is not enough: 'reason_code' would "
                          "happily carry a paragraph naming a guest")

    nested = run(ADMIN, f"""
        INSERT INTO notify.notification
            (id, tenant_id, outlet_id, event_id, subject_kind, subject_id,
             correlation_id, dedup_key, payload)
        VALUES (gen_random_uuid(), '{fx.TENANT}', '{fx.OUTLET_H1}',
                'EVT-SERVICE-REQUESTED', 'service_request', gen_random_uuid(),
                gen_random_uuid(), 'leak-probe-3',
                '{{"state": {{"hidden": "Abebe"}}}}'::jsonb);""")
    record("and so is anything nested one level down, where nobody would look",
           nested.failed_with("23514"),
           nested.why() or "an object travelled under an allowed key")

    # --- and the logs ---
    log = CONTEXT["service_log"]()
    in_log = sorted(name for name, value in CANARIES.items() if value in log)
    record("nor does any of it reach the service log",
           not in_log,
           f"{len(log.splitlines())} log line(s) searched for the same {len(CANARIES)} "
           f"planted values; found: {in_log or 'none'}. FR-NOT-010 says payloads OR "
           f"logs, and M1-D proved the log half by planting a secret and asserting zero "
           f"occurrences — the same method, over the notification paths this gate added")

    rendered = rows(f"""
        SELECT count(*)::text FROM notify.notice
        WHERE tenant_id = '{fx.TENANT}' AND rendered_text LIKE '%CANARY%';""")
    record("and no rendered message carries one either",
           rendered and rendered[0][0] == "0",
           f"{rendered[0][0]} sent message(s) containing a planted value. The "
           f"rendered text comes from an APPROVED template, so there is no path by which "
           f"a guest's own words become a message somebody else is shown")


# ===========================================================================
# 8. Templates, deep links and the notification centre
#    (FR-NOT-003, FR-NOT-009, FR-NOT-012)
# ===========================================================================

def section_templates_and_links() -> None:
    print("\n--- 8. Approved templates, deep links that respect scope, and the "
          "notification centre (FR-NOT-003, 009, 012) ---")

    approved = rows(f"""
        SELECT tr.locale::text, count(*)::text
        FROM menu.translation tr
        WHERE tr.tenant_id = '{fx.TENANT}' AND tr.entity = 'notification_template'
          AND tr.state = 'approved'
        GROUP BY 1 ORDER BY 1;""")
    record("FR-NOT-003: customer templates are approved in Amharic and Arabic",
           {r[0] for r in approved} == {"am", "ar"},
           f"{approved}, plus the English source on the template row itself. The store "
           f"is menu.translation — M2-A's — so approval, review and the machine-"
           f"assistance boundary all apply without being written again")

    staff_only = rows(f"""
        SELECT event_id FROM notify.template
        WHERE tenant_id = '{fx.TENANT}' AND audience = 'staff' ORDER BY event_id;""")
    record("and every M3 kind this gate produces has an English staff template",
           len(staff_only) >= 4,
           f"{[r[0] for r in staff_only]}. FR-I18N-007 makes staff English, so the "
           f"source text IS the staff template rather than a fallback for one")

    # --- deep links ---
    seated = CONTEXT["seated"]
    notice = scalar(f"""
        SELECT dl.id::text FROM notify.notice dl
        WHERE dl.tenant_id = '{fx.TENANT}' AND dl.audience = 'staff' LIMIT 1;""")
    issued = run(APP, f"""
        SELECT notify.issue_deep_link('{fx.TENANT}', '{notice}', '{STAFF_LINK_TOKEN}',
            'service_request', '{CONTEXT["request"]}', NULL);""", **CTX)
    resolved = rows(f"""
        SELECT target_kind::text, target_id::text
        FROM notify.resolve_deep_link('{fx.TENANT}', '{STAFF_LINK_TOKEN}', NULL,
                                      '{fx.USER}');""")
    record("FR-NOT-009: a link resolves for somebody authorized at its outlet",
           issued.ok and resolved and resolved[0][0] == "service_request",
           f"{issued.why() or resolved}. The screen it opens is M3-D's for staff; what "
           f"this gate owns is that following one asks the same question M2-B's session "
           f"scope asks")

    outsider = run(APP, f"""
        SELECT * FROM notify.resolve_deep_link('{fx.TENANT}', '{STAFF_LINK_TOKEN}', NULL,
                                               '{fx.USER_WAITER_B}');""", **CTX)
    record("and refuses somebody who is not a member of that outlet",
           outsider.failed_with("DEEP_LINK_OUT_OF_SCOPE"),
           outsider.why() or "a link opened for a person with no membership at the "
                             "outlet it belongs to")

    stored = rows(f"""
        SELECT (token_digest IS NOT NULL)::text, octet_length(token_digest)::text
        FROM notify.deep_link WHERE tenant_id = '{fx.TENANT}' LIMIT 1;""")
    plaintext = count(APP, f"""
        SELECT count(*) FROM notify.deep_link
        WHERE tenant_id = '{fx.TENANT}'
          AND encode(token_digest, 'escape') LIKE '%{STAFF_LINK_TOKEN}%';""", **CTX)
    record("the token is stored as a digest and never in the clear",
           stored and stored[0][1] == "32" and plaintext == 0,
           f"sha256, {stored[0][1]} bytes, {plaintext} row(s) holding the plaintext. "
           f"M1-B's rule for session tokens, unchanged — and the target is not derivable "
           f"from the token, so a link cannot be edited into another table's request")

    expired = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{fx.TENANT}', false);
        SELECT set_config('app.outlet_id', '{fx.OUTLET_H1}', false);
        UPDATE notify.deep_link SET expires_at = now() - interval '1 minute'
         WHERE tenant_id = '{fx.TENANT}';
        SELECT * FROM notify.resolve_deep_link('{fx.TENANT}', '{STAFF_LINK_TOKEN}', NULL,
                                               '{fx.USER}');""", rollback=True)
    record("an expired link is refused by name, not merely 'not found'",
           expired.failed_with("DEEP_LINK_EXPIRED"),
           expired.why() or "an expired link resolved. 'Not found' for an expired link "
                            "and 'not found' for somebody else's are different facts, "
                            "and an operator debugging the first should not be told the "
                            "second")

    # The outlet boundary has TWO locks and they are proved separately, because under
    # ordinary row level security the second can never fire.
    cross = run(APP, f"""
        SELECT * FROM notify.resolve_deep_link('{fx.TENANT}', '{STAFF_LINK_TOKEN}', NULL,
                                               '{fx.USER}');""",
        tenant=fx.TENANT, outlet=fx.OUTLET_H2)
    record("lock one: from another outlet the link is not even visible",
           cross.failed_with("DEEP_LINK_UNKNOWN"),
           cross.why() or "a link belonging to another outlet was readable. Row level "
                          "security hides it first, which is where isolation belongs")

    guard = definition("notify.resolve_deep_link(uuid,text,uuid,uuid)")
    record("and the resolver does not carry a second outlet check that could never fire",
           "current_outlet_id() IS DISTINCT FROM" not in guard,
           f"outlet scope is the row level security predicate and nothing else. An "
           f"earlier draft compared app.current_outlet_id() to the link's outlet as a "
           f"'second lock' — and it was unreachable: the function is SECURITY DEFINER "
           f"owned by the migration role, FORCE covers the owner, so the row is gone "
           f"before any such line runs. A guard that cannot fire is not a lock, and this "
           f"check is here so one cannot be reintroduced as though it were")

    # --- FR-NOT-012 ---
    centre = rows(f"""
        SELECT event_id, state::text FROM notify.staff_notification_center(
            '{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.USER}') ORDER BY event_id;""")
    record("FR-NOT-012: the staff notification centre serves that person's own list",
           len(centre) > 0,
           f"{len(centre)} notification(s): {sorted({r[0] for r in centre})}. In English, "
           f"because FR-I18N-007 makes staff English. The DATA is complete here; the "
           f"screen is M3-D's and the register says so")

    theirs = run(APP, f"""
        SELECT * FROM notify.staff_notification_center('{fx.TENANT}', '{fx.OUTLET_H1}',
                                                       '{fx.USER_WAITER_B}');""", **CTX)
    record("and somebody with no membership at that outlet gets nothing, by name",
           theirs.failed_with("NOT_A_MEMBER_OF_THIS_OUTLET"),
           theirs.why() or "a notification centre answered for a person who does not "
                           "work at that outlet")


# ===========================================================================
# 9. The dead letter, and a replay that is safe (FR-INT-007, FR-INT-005)
# ===========================================================================

def table_digests() -> dict[str, str]:
    """M3-A's whole-schema differential, imported rather than rewritten.

    The instrument enumerates every base table in every non-system schema from the
    CATALOG and digests whole rows, so it covers the tables this slice added without
    anybody adding them. Importing it rather than copying it is the point: two copies of
    a differential is two chances for one of them to stop covering something, which is
    exactly the defect this instrument had when M3-C picked it up — its schema list was
    hardcoded at M3-A and had silently stopped covering fulfillment.
    """
    module = sys.modules.get("m3a_verifier")
    if module is None:
        import importlib.util
        # M3-A's verifier asserts that the `fixtures` it imported is its OWN — the guard
        # that stops a suite testing another slice's fixtures by accident. This process
        # already has M3-C's under that name, so the name is handed back for the length
        # of the import and restored afterwards. Reaching for the instrument rather than
        # copying it is the point; tiptoeing around that assertion is the price, and the
        # assertion is right to be there.
        borrowed = sys.modules.pop("fixtures", None)
        saved_path = list(sys.path)
        sys.path.insert(0, str(HERE.parent / "m3a"))
        try:
            spec = importlib.util.spec_from_file_location(
                "m3a_verifier", HERE.parent / "m3a" / "verify_m3a.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules["m3a_verifier"] = module
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = saved_path
            if borrowed is not None:
                sys.modules["fixtures"] = borrowed
    return module.table_digests()


def section_dead_letter() -> None:
    print("\n--- 9. Repeatedly failing work, visible, with a replay that cannot "
          "duplicate (FR-INT-007, FR-INT-005) ---")

    fx.set_presence("available")
    seated = fx.a_seated_guest()
    raised = raise_request(seated, "packaging", key=idem("dl-1"))
    request = (raised.scalar or "").strip()

    # FAILURE ONE: the recipient's authorization was withdrawn between the event
    # happening and the notice being attempted. A real race, and the sharpest of the
    # three — in scope at emission, out of scope at notice.
    # EVERY membership, not just the attendant role. Being authorized to be told
    # something is holding an active membership at the outlet at all — the person has a
    # second role here, and withdrawing one of two would have left them authorized while
    # the probe believed otherwise.
    run(APP, f"""
        UPDATE identity.membership SET status = 'inactive', withdrawn_at = now()
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
           AND user_account_id = '{fx.USER}';""", **CTX)
    swept = rows(f"""
        SELECT sent::text, failed::text, dead_lettered::text
        FROM notify.send_pending('{fx.TENANT}', '{fx.OUTLET_H1}', 1);""")
    queued = rows(f"""
        SELECT job_kind::text, failure_reason, attempts::text, state::text
        FROM integration.dead_letter WHERE tenant_id = '{fx.TENANT}'
          AND failure_reason = 'recipient_not_authorized'
        ORDER BY last_failed_at DESC LIMIT 1;""")
    record("FR-INT-007: a recipient authorized at emission and not at notice fails, "
           "by name",
           bool(queued),
           f"{swept}, queue head {queued}. The membership was withdrawn between the two, "
           f"which is a genuine race rather than an injected fault: emission resolves "
           f"recipients from the state when something happened, notice happens "
           f"afterwards. Same boundary as M2-B's FOREIGN_SESSION_ACCEPTED")
    run(APP, f"""
        UPDATE identity.membership SET status = 'active', withdrawn_at = NULL
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
           AND user_account_id = '{fx.USER}';""", **CTX)

    # FAILURE TWO: no approved template in the language the recipient must be told in.
    missing = run(APP, f"""
        SELECT notify.render_for('{fx.TENANT}', 'EVT-SERVICE-COMPLETED', 'customer',
                                 'ar');""", **CTX)
    withdrawn = run(APP, f"""
        UPDATE menu.translation SET state = 'draft', reviewed_by_user_id = NULL,
               approved_at = NULL
         WHERE tenant_id = '{fx.TENANT}' AND entity = 'notification_template'
           AND locale = 'ar';
        SELECT coalesce(notify.render_for('{fx.TENANT}', 'EVT-SERVICE-COMPLETED',
                                          'customer', 'ar'), 'NOTHING-APPROVED');""",
        rollback=True, **CTX)
    record("failure two: an unapproved template renders NOTHING rather than English",
           missing.ok and (missing.scalar or "").strip() != ""
           and "NOTHING-APPROVED" in (withdrawn.out or ""),
           f"approved: {(missing.scalar or '')[:40]!r}; with approval withdrawn the "
           f"renderer returns nothing at all. FR-I18N-008's fallback is English for "
           f"STAFF and for an English session — falling back to English for an Arabic "
           f"guest is the M2-C defect, and a notice that cannot be made in the right "
           f"language fails rather than being made in the wrong one")

    # FAILURE THREE: the guest is no longer live on the session.
    gone_seated = fx.a_seated_guest(table=fx.TABLE_TWO)
    raise_request(gone_seated, "water", key=idem("dl-3"))
    run(APP, f"""
        UPDATE service.session_participant SET left_at = now()
         WHERE table_session_id = '{gone_seated["session"]}';""", **CTX)
    run(APP, f"""
        SELECT notify.send_pending('{fx.TENANT}', '{fx.OUTLET_H1}', 1);""", **CTX)
    out_of_scope = count(APP, f"""
        SELECT count(*) FROM notify.notice dl
        WHERE dl.tenant_id = '{fx.TENANT}'
          AND dl.last_failure = 'recipient_out_of_scope';""", **CTX)
    record("failure three: a guest who has left the table is out of scope, by name",
           out_of_scope > 0,
           f"{out_of_scope} notice/notices. Three reasons, each proved on its own: "
           f"one standing in for the others would mean two of them were never exercised")

    reasons = {r[0] for r in rows("""
        SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'notify' AND t.typname = 'failure_reason';""")}
    record("and there is no 'transport error' among them, because there is no transport",
           reasons == {"recipient_not_authorized", "recipient_out_of_scope",
                       "template_missing"},
           f"{sorted(reasons)}. Outlet-local notice is M5a; an adapter invented here "
           f"would be a stub with nothing behind it, and a failure reason for it would "
           f"be a reason nothing could produce")

    # --- safe replay, against the differential ---
    entry = scalar(f"""
        SELECT coalesce((SELECT id::text FROM integration.dead_letter
                          WHERE tenant_id = '{fx.TENANT}' AND state = 'open'
                            AND failure_reason = 'recipient_not_authorized'
                          LIMIT 1), '');""")
    if not entry:
        record("an entry reached the queue to replay", False,
               "nothing was dead-lettered for recipient_not_authorized, so the replay "
               "checks below would have been testing nothing")
        return

    anonymous = run(APP, f"""
        SELECT integration.replay_dead_letter('{fx.TENANT}', '{entry}', NULL);""", **CTX)
    record("a replay with no operator named is refused",
           anonymous.failed_with("REPLAY_WITHOUT_ACTOR"),
           anonymous.why() or "dead-lettered work was replayed by nobody. 'Replayed by '"
                              "nobody' is the same defect as M3-B's priority with no "
                              "attributed actor")

    before = table_digests()
    replayed = run(APP, f"""
        SELECT integration.replay_dead_letter('{fx.TENANT}', '{entry}', '{fx.USER}',
                                              'membership restored');""", **CTX)
    sent = run(APP, f"""
        SELECT notify.send_pending('{fx.TENANT}', '{fx.OUTLET_H1}');""", **CTX)
    after = table_digests()

    changed = sorted(name for name in set(before) | set(after)
                     if before.get(name) != after.get(name))
    expected = {"notify.notice", "integration.dead_letter"}
    record("FR-INT-007: a replay re-runs the SAME work and creates nothing new",
           replayed.ok and sent.ok and set(changed) <= expected,
           f"tables changed by the replay: {changed}. Measured with M3-A's whole-schema "
           f"differential, enumerated from the catalog over {len(before)} tables — so it "
           f"covers the ones this slice added without anybody listing them. A replay "
           f"that re-EMITTED would have changed notify.notification too, which is the "
           f"FR-NOT-007 duplicate wearing an operator's authorization")

    resolved = rows(f"""
        SELECT state::text, resolved_by_user_id::text, coalesce(resolution_note, '-')
        FROM integration.dead_letter WHERE id = '{entry}';""")
    record("and the entry records who replayed it and why",
           resolved and resolved[0][0] == "replayed" and resolved[0][1] == fx.USER,
           f"{resolved}. An operator-visible queue whose entries resolve themselves "
           f"would not be one")

    twice = run(APP, f"""
        SELECT integration.replay_dead_letter('{fx.TENANT}', '{entry}', '{fx.USER}');""",
        **CTX)
    record("a resolved entry cannot be replayed again",
           twice.failed_with("DEAD_LETTER_NOT_OPEN"),
           twice.why() or "an entry somebody had already accounted for was run again")


# ===========================================================================
# 10. What a customer sees — MEASURED
#     (FR-SRV-003, FR-SRV-009, FR-I18N-001B, FR-I18N-008, FR-NOT-012)
# ===========================================================================
# The claims in this section are claims about a SCREEN, and M2-C settled that a claim
# about a screen can only be proved by rendering one: it found a translated warning
# beside an untranslated dish name that every query agreed was absent. Status and service
# text is the same exposure on a different path.

# The English chrome, so an Amharic or Arabic render can be checked for it leaking
# through. Read out of the surface's own string table rather than written here, so a
# string added tomorrow is covered without anybody remembering to add it.
def english_chrome() -> list[str]:
    source = (REPO / "pwa" / "src" / "app.ts").read_text(encoding="utf-8")
    block = source.split("  en: {", 1)[1].split("  am: {", 1)[0]
    return sorted({value for value in re.findall(r"'((?:[^'\\]|\\.){4,})'", block)
                   if re.fullmatch(r"[A-Za-z][A-Za-z ,.'\-]{3,}", value)},
                  key=len, reverse=True)


def customer_payload(token: str) -> dict:
    return {
        "types": guest_get("/c/v1/service/types", token).get("types", []),
        "status": guest_get("/c/v1/service/status", token).get("requests", []),
        "timeline": guest_get("/c/v1/service/timeline", token).get("entries", []),
    }


def section_customer_surface() -> None:
    print("\n--- 10. The customer's service panel, rendered and measured "
          "(FR-SRV-003, 009, FR-I18N-001B, FR-I18N-008) ---")

    fx.set_presence("available")
    seated = fx.a_seated_guest_with_credential(locale="am")
    CONTEXT["measured_seated"] = seated
    token = seated["token"]

    types = guest_get("/c/v1/service/types", token)
    record("the surface can read the request catalog over HTTP as a guest",
           isinstance(types.get("types"), list) and len(types["types"]) == 7,
           f"{len(types.get('types', []))} type(s): "
           f"{[t.get('code') for t in types.get('types', [])]}")

    labels = {t["code"]: t["label"] for t in types.get("types", [])}
    record("FR-I18N-001B: the labels come back in the session's language, not English",
           labels.get("water") == fx.TYPE_LABELS["water"]["am"],
           f"water renders as {labels.get('water')!r} in an Amharic session. The label a "
           f"guest reads is resolved by the SERVER from the approved translation, so a "
           f"request type an outlet invented is translated too")

    raised = guest_post("/c/v1/service/requests", token,
                        {"requestTypeId": fx.request_type("water")}, idem("surface-1"))
    record("a guest raises a request from their own device",
           raised.get("collapsed") is False and "serviceRequestId" in raised,
           f"{raised}")

    collapsed = guest_post("/c/v1/service/requests", token,
                           {"requestTypeId": fx.request_type("water")}, idem("surface-2"))
    record("and a second tap is reported as collapsed rather than as an error",
           collapsed.get("collapsed") is True
           and collapsed.get("serviceRequestId") == raised.get("serviceRequestId"),
           f"{collapsed}. The surface has to say something different when a tap "
           f"collapsed than when it raised, and 'you have already asked' is not an error")

    run(APP, f"""
        SELECT notify.send_pending('{fx.TENANT}', '{fx.OUTLET_H1}');""", **CTX)

    payload = customer_payload(token)
    CONTEXT["measured_payload"] = payload
    probe = render(payload, CONTEXT["code"], locale="am")
    record("the customer surface rendered without a page error",
           not probe["errors"],
           f"{probe['errors'] or 'no page errors'}")
    view = probe["rendered"]

    types_drawn = [t for t in view["types"] if t["visible"]]
    measured("every request type this outlet offers is drawn and can be tapped",
             len(types_drawn) == 7,
             f"{len(types_drawn)} visible ask button(s): "
             f"{[t['text'] for t in types_drawn][:4]}… and "
             f"{len([a for a in view['askAgain'] if a['visible']])} ask-again "
             f"affordance(s), which are counted apart from them because they are a "
             f"different thing to tap")

    statuses = [s for s in view["statuses"] if s["visible"]]
    measured("FR-SRV-003: the guest is shown a received / being-handled status in words",
             len(statuses) >= 1
             and all(s["word"] for s in statuses)
             and all(s["status"] in ("received", "being_handled", "completed",
                                     "withdrawn", "closed") for s in statuses),
             f"{[(s['status'], s['word'][:36]) for s in statuses]}. A WORD, not a colour "
             f"and not a position — the same rule the rest of this surface follows")

    # THE DECISIVE LANGUAGE MEASUREMENT. Every English chrome string from the surface's
    # own table, hunted for in an Amharic render.
    chrome = english_chrome()
    leaked = [phrase for phrase in chrome if phrase in view["panelText"]]
    measured("FR-I18N-008: no English leaks into an Amharic session's service panel",
             not leaked,
             f"{len(chrome)} English strings from the surface's own table searched for in "
             f"the rendered panel; found: {leaked or 'none'}. This is M2-C's defect on a "
             f"different path — one untranslated word beside translated ones — and it is "
             f"measured rather than asserted because that is the only way it was ever "
             f"going to be seen")

    amharic = re.compile(r"[ሀ-፿]")
    measured("and the panel is actually rendering Amharic script",
             bool(amharic.search(view["panelText"])),
             f"Ethiopic characters present in the rendered panel. Without this the check "
             f"above would pass on an empty panel, which is the shape of assertion that "
             f"cannot fail")

    timeline = [t for t in view["timeline"] if t["visible"]]
    measured("FR-NOT-012: the localized status timeline is drawn",
             len(timeline) >= 1,
             f"{len(timeline)} entr(y/ies), sources "
             f"{sorted({t['source'] for t in timeline})}. One timeline over the order "
             f"milestones and the service messages, merged at read time rather than "
             f"stored twice")

    # --- FR-SRV-009 ---
    named = [s for s in statuses if s["handledBy"]]
    measured("FR-SRV-009: no staff name is drawn when the outlet has not configured it",
             not named,
             f"{len(named)} status row(s) carrying a name. The surface has no branch that "
             f"could add one the server withheld — it renders handled_by only when the "
             f"server sent it, and the server sends it only where the policy says so")

    staff_names = [r[0] for r in rows(f"""
        SELECT display_name FROM identity.user_account
        WHERE tenant_id = '{fx.TENANT}' AND display_name IS NOT NULL;""")]
    present = [name for name in staff_names if name and name in view["documentText"]]
    measured("and no member of staff is named anywhere in the document either",
             not present,
             f"{len(staff_names)} staff name(s) searched for in the whole rendered "
             f"document; found: {present or 'none'}. Searched over the DOCUMENT rather "
             f"than the panel, because a name that reached the page through some other "
             f"route would be just as disclosed")

    # --- and the disclosure switch actually works, or the check above is vacuous ---
    run(APP, f"""
        UPDATE config.policy
           SET payload = payload || '{{"disclose_staff_identity_to_customer": true}}'::jsonb
         WHERE id = '{fx.SERVICE_POLICY}';""", **CTX)
    with_names = customer_payload(token)
    disclosed = [r for r in with_names["status"] if r.get("handled_by")]
    run(APP, f"""
        UPDATE config.policy
           SET payload = payload - 'disclose_staff_identity_to_customer'
         WHERE id = '{fx.SERVICE_POLICY}';""", **CTX)
    record("where the outlet DOES configure disclosure, the name is served",
           len(disclosed) >= 1,
           f"{len(disclosed)} status row(s) named a handler once the policy said to. "
           f"Without this the measurement above would hold for a surface that could "
           f"never show a name at all, which is a check that cannot fail")

    hidden_again = [r for r in customer_payload(token)["status"] if r.get("handled_by")]
    record("and it goes away again when the policy does",
           not hidden_again,
           f"{len(hidden_again)} named row(s) after the key was removed. Fail closed: an "
           f"absent policy discloses nothing rather than everything")


# ===========================================================================
# 11. Correlation and rebuild (FR-INT-014, FR-DAT-010)
# ===========================================================================

def section_correlation_and_rebuild() -> None:
    print("\n--- 11. The chain gains a link, and three ledgers rebuild as one "
           "(FR-INT-014, FR-DAT-010) ---")

    request = CONTEXT["request"]
    chain = {r[0] for r in rows(f"""
        SELECT artifact_kind::text FROM ordering.correlation_chain('{fx.TENANT}',
            (SELECT correlation_id FROM service.service_request WHERE id = '{request}'));""")}
    record("FR-INT-014: the service request is a link in the correlation chain",
           "service_request" in chain,
           f"{sorted(chain)}. M3-A built the chain with service_request as a LABEL and no "
           f"rows; this is where the rows arrive. Bill, payment, tip and sync are later "
           f"gates and stay in the register as partial closures")

    linked = count(APP, f"""
        SELECT count(*) FROM ordering.correlation_link cl
        JOIN service.service_request sr ON sr.id = cl.artifact_id
        WHERE cl.artifact_kind = 'service_request' AND sr.tenant_id = '{fx.TENANT}';""",
        **CTX)
    total = count(APP, f"""
        SELECT count(*) FROM service.service_request WHERE tenant_id = '{fx.TENANT}';""",
        **CTX)
    record("every request is in the chain, not just the first",
           linked == total and total > 1,
           f"{linked} of {total} request(s) linked. A chain that named one of many would "
           f"be worse than none, because it would look complete")

    # --- the rebuild, over all three ledgers ---
    # Three things had to be got right here, and the first two were got wrong first.
    #
    #   * ONE IDENTITY, ONE SCOPE. Reading one digest through the application role and
    #     its pair through the superuser compares an OUTLET's projections against a
    #     TENANT's. They differ for a correct system, which is a failure nobody can act on.
    #   * THE REBUILD MUST ACTUALLY RUN. ordering.rebuild_projections() is SECURITY
    #     DEFINER over tables with FORCE row level security, so its body is filtered by
    #     app.row_in_scope() whoever calls it — a superuser included. Called with no
    #     tenant and outlet it is not an error: every ledger row is out of scope, so it
    #     drops nothing, replays nothing and returns 0, and every digest then matches
    #     trivially. That is an assertion that cannot fail, which is a defect, and it is
    #     how this check first passed. The replay count is the guard.
    #   * THE COMPARISON MUST BE AGAINST THE LEDGER, NOT AGAINST THIS SUITE'S EDITS. Two
    #     earlier sections move a deadline into the past to make a deduplication window
    #     and an overdue request testable without waiting ten minutes for either. Those
    #     are writes to the PROJECTION; the ledger, which is the truth, does not carry
    #     them. A rebuild therefore restores the recorded time and SHOULD differ from the
    #     live row — comparing the two would report a correct rebuild as a defect.
    #
    # So the first rebuild is measured by what it must not lose, and determinism is
    # asserted over the second. Both halves are needed: an identity comparison alone
    # passes for a rebuild that dropped a projection nothing replays, which is the defect
    # M3-B found, and an identity check alone says nothing about the values in the rows.
    def artifact_ids() -> list[str]:
        return sorted(r[0] for r in rows(f"""
            SELECT 'request:'  || id::text FROM service.service_request
             WHERE tenant_id = '{fx.TENANT}'
            UNION ALL
            SELECT 'routing:'  || id::text FROM service.request_routing_decision
             WHERE tenant_id = '{fx.TENANT}'
            UNION ALL
            SELECT 'escal:'    || id::text FROM service.request_escalation
             WHERE tenant_id = '{fx.TENANT}'
            UNION ALL
            SELECT 'order:'    || id::text FROM ordering.customer_order
             WHERE tenant_id = '{fx.TENANT}'
            UNION ALL
            SELECT 'link:'     || artifact_kind::text || ':' || artifact_id::text
              FROM ordering.correlation_link WHERE tenant_id = '{fx.TENANT}'
            UNION ALL
            SELECT 'ticket:'   || id::text FROM fulfillment.ticket
             WHERE tenant_id = '{fx.TENANT}';"""))

    def digests() -> tuple[str, str, str]:
        return (scalar(f"SELECT encode(service.projection_digest('{fx.TENANT}'), 'hex');"),
                scalar(f"SELECT encode(ordering.projection_digest('{fx.TENANT}'), 'hex');"),
                scalar(f"SELECT encode(fulfillment.projection_digest('{fx.TENANT}'), 'hex');"))

    ids_before = artifact_ids()
    ledgers = replayed_ledgers()
    record("the three ledgers a rebuild replays are read out of the rebuild itself",
           len(ledgers) == 3 and "service.service_request_event" in ledgers,
           f"{ledgers}. Named here instead, this count would be wrong the moment M3-D "
           f"added a fourth — the same defect as M3-A's hardcoded schema list, one level "
           f"down — and the guard below would fail on a correct system")
    ledger_events = count(APP, "SELECT " + " + ".join(
        f"(SELECT count(*) FROM {table} WHERE tenant_id = '{fx.TENANT}')"
        for table in ledgers) + ";", **CTX)
    rebuilt = run(APP, f"SELECT ordering.rebuild_projections('{fx.TENANT}');", **CTX)
    replayed = int((rebuilt.scalar or "-1").strip()) if rebuilt.ok else -1
    record("the rebuild actually replayed all three ledgers rather than nothing",
           replayed == ledger_events and replayed > 0,
           f"{replayed} event(s) replayed against {ledger_events} in the three ledgers. "
           f"Without this the comparisons below would pass on a rebuild that dropped "
           f"nothing and replayed nothing, which is what a rebuild called with no tenant "
           f"context does")

    ids_after = artifact_ids()
    lost = [i for i in ids_before if i not in set(ids_after)]
    invented = [i for i in ids_after if i not in set(ids_before)]
    record("dropping every projection and replaying THREE ledgers loses nothing and "
           "invents nothing",
           rebuilt.ok and not lost and not invented and len(ids_before) > 0,
           f"{len(ids_before)} artifact(s) across three schemas; lost "
           f"{lost[:3] or 'none'}, invented {invented[:3] or 'none'}. Requests, routing "
           f"decisions, escalations, orders, tickets and every correlation link, by id. "
           f"A projection the LIVE path writes and the fold does not comes back missing "
           f"here — which is the defect M3-B found in ordering.correlation_link")

    service_first, ordering_first, fulfil_first = digests()
    second = run(APP, f"SELECT ordering.rebuild_projections('{fx.TENANT}');", **CTX)
    replayed_again = int((second.scalar or "-1").strip()) if second.ok else -1
    service_second, ordering_second, fulfil_second = digests()
    drifted = [name for name, (one, two) in {
        "service": (service_first, service_second),
        "ordering": (ordering_first, ordering_second),
        "fulfillment": (fulfil_first, fulfil_second)}.items() if one != two]
    record("and replaying them a second time reproduces every column exactly",
           second.ok and replayed_again == replayed and not drifted
           and len(service_first) == 64,
           f"service {service_first[:12]}…, ordering {ordering_first[:12]}…, "
           f"fulfillment {fulfil_first[:12]}… — "
           f"{'all three unchanged' if not drifted else 'DRIFTED: ' + ', '.join(drifted)} "
           f"over {replayed_again} events replayed again. The digest renders every column "
           f"of every projection in an explicit order, so a value the fold computes from "
           f"the clock rather than from the event changes it")

    restored = count(APP, f"""
        SELECT count(*) FROM ordering.correlation_link
        WHERE artifact_kind = 'service_request';""", **CTX)
    record("and the service links come back with it",
           restored == linked,
           f"{restored} link(s) after the rebuild against {linked} before. A link written "
           f"by the caller rather than the fold is a projection no rebuild can restore, "
           f"which is exactly what M3-B learned")

    # --- FR-TAB-007A and FR-TAB-008, which came due here ---
    # A service request is bound to the TABLE SESSION, so it travels with it. There is no
    # consolidation step to get wrong — which is the claim, and it is only worth anything
    # if somebody checks the set is really unchanged either side.
    fx.set_presence("available")
    left = fx.a_seated_guest(table=fx.TABLE_ONE)
    right = fx.a_seated_guest(table=fx.TABLE_TWO)
    raise_request(left, "water", key=f"merge-l-{os.urandom(4).hex()}")
    raise_request(right, "cutlery", key=f"merge-r-{os.urandom(4).hex()}")

    def request_set(session: str) -> set[str]:
        return {r[0] for r in rows(f"""
            SELECT id::text FROM service.service_request
            WHERE table_session_id = '{session}';""")}

    before = request_set(left["session"]) | request_set(right["session"])
    merged = run(APP, f"""
        SELECT service.merge_table_sessions('{fx.TENANT}', '{left["session"]}',
                                            '{right["session"]}', '{fx.USER}');""", **CTX)
    after = request_set(left["session"])
    record("FR-TAB-007A: a merge consolidates the requests and loses none",
           merged.ok and after == before and len(before) == 2,
           f"{merged.why() or ''}{len(before)} request(s) before, {len(after)} on the "
           f"surviving occupancy after; lost {sorted(before - after) or 'none'}, "
           f"invented {sorted(after - before) or 'none'}. Nothing consolidates them "
           f"because nothing had to: they reference the session, and the merge moves the "
           f"session")

    moved = run(APP, f"""
        SELECT service.move_table_session('{fx.TENANT}', '{left["session"]}',
                                          '{fx.m3b.m3a.TABLE_TWO}', '{fx.USER}');""",
        **CTX)
    after_move = request_set(left["session"])
    record("FR-TAB-008: and a move preserves them unchanged",
           moved.ok and after_move == before,
           f"{moved.why() or ''}{len(after_move)} request(s) after the move against "
           f"{len(before)} before. The same set, on the same session, at a different "
           f"table")

    direct = run(APP, f"""
        UPDATE service.service_request SET state = 'cancelled'
         WHERE tenant_id = '{fx.TENANT}';""", **CTX)
    record("a projection cannot be written except by the fold",
           direct.failed_with("PROJECTION_WRITTEN_DIRECTLY", "42501"),
           direct.why() or "a request was changed from outside apply_request_event()")

    for verb, statement in (
            ("UPDATE", f"UPDATE service.service_request_event SET kind = 'routed' "
                       f"WHERE tenant_id = '{fx.TENANT}';"),
            ("DELETE", f"DELETE FROM service.service_request_event "
                       f"WHERE tenant_id = '{fx.TENANT}';")):
        res = run(APP, statement, **CTX)
        record(f"the service ledger refuses {verb}",
               res.failed_with("SERVICE_LEDGER_MUTATION_REFUSED", "42501"),
               res.why() or f"{verb} succeeded — the ledger is not append-only")


# ===========================================================================
# 12. Governance
# ===========================================================================

SOURCES = (
    "migrations/0013_translatable_service_and_notification_entities.sql",
    "migrations/0014_service_requests_notifications_and_integration_runtime.sql",
    "tests/m3c/verify_m3c.py",
    "tests/m3c/fixtures.py",
    "tests/m3c/render_probe.mjs",
    "api/src/routes/service.ts",
    "pwa/src/app.ts",
    "pwa/index.html",
    "pwa/app.css",
)


def section_governance() -> None:
    print("\n--- 12. Governance ---")

    try:
        failures = partial_closures.check()
        entries = partial_closures.load()
    except partial_closures.RegisterUnreadable as error:
        record("the partial-closure register is readable", False, str(error))
        return

    closed_here = [e for e in entries if (e.get("closed_at") or "") == "M3-C"]
    record("the register is consistent, and the entries that came due are closed",
           not failures,
           f"{len(entries)} entries, {len(closed_here)} closed at M3-C: "
           f"{sorted({e['requirement'] for e in closed_here})}. Failures: "
           f"{failures or 'none'}")

    landed = partial_closures.landed_gates()
    still_open = {e["completing_gate"] for e in entries
                  if (e.get("state") or "") == "open"}
    record("no open entry's completing gate has landed",
           not (still_open & landed),
           f"open completers: {sorted(still_open)}; landed: {sorted(landed)}. M3-D will "
           f"do to the staff-render entry what M3-C just did to the service ones")

    m3c_entries = {e["requirement"] for e in entries if e.get("opened_at") == "M3-C"}
    record("this slice's own half-closed requirements are in the register",
           "FR-NOT-012" in m3c_entries,
           f"opened at M3-C: {sorted(m3c_entries)}. FR-NOT-012's staff RENDER is M3-D's "
           f"and is recorded with M3-D named, so creating tests/m3d/ stops the build "
           f"until somebody goes back to it")

    # --- money, isolation, definers ---
    floats = rows("""
        SELECT n.nspname || '.' || c.relname || '.' || a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE n.nspname IN ('notify', 'integration') AND c.relkind = 'r'
          AND a.attnum > 0 AND NOT a.attisdropped
          AND t.typname IN ('float4', 'float8', 'money');""")
    record("no money in the new schemas is binary floating point",
           not floats,
           f"{[r[0] for r in floats] or 'none'}. This slice carries no money at all — a "
           f"request for water has no price — and the check is here so that stops being "
           f"true loudly rather than quietly")

    unprotected = rows("""
        SELECT n.nspname || '.' || c.relname
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('notify', 'integration') AND c.relkind = 'r'
          AND c.relname <> 'catalog_event'
          AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)
        ORDER BY 1;""", dsn=ADMIN)
    record("every tenant table in the new schemas has row level security ENABLED and FORCED",
           not unprotected,
           f"{[r[0] for r in unprotected] or 'none'}. notify.catalog_event is exempt and "
           f"is the only exemption: it is the package's event catalog, not tenant data, "
           f"and carries no tenant column to scope by")

    service_tables = rows("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'service' AND c.relkind = 'r'
          AND c.relname <> 'transition'
          AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)
        ORDER BY 1;""", dsn=ADMIN)
    record("and so does every table this slice added to the service schema",
           not service_tables,
           f"{[r[0] for r in service_tables] or 'none'}. service.transition is exempt for "
           f"the same reason: it is SM-SERVICE-REQUEST, and it is immutable at runtime "
           f"instead")

    wrong_predicate = rows("""
        SELECT c.relname, p.polname FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE (n.nspname IN ('notify', 'integration')
               OR (n.nspname = 'service' AND c.relname IN (
                     'request_type', 'staff_presence', 'service_request_event',
                     'service_request', 'request_routing_decision',
                     'request_escalation')))
          AND pg_get_expr(p.polqual, p.polrelid) <> 'app.row_in_scope(tenant_id, outlet_id)'
        ORDER BY c.relname;""", dsn=ADMIN)
    record("every policy uses the one isolation predicate",
           not wrong_predicate,
           f"{[f'{r[0]}/{r[1]}' for r in wrong_predicate] or 'none'} — M1-A's NC-M1-003 "
           f"gates this in CI and it gates eleven new tables unchanged")

    unpinned = [r[0] for r in rows("""
        SELECT n.nspname || '.' || p.proname FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname IN ('notify', 'integration', 'service') AND p.prosecdef
          AND coalesce(array_to_string(p.proconfig, ','), '') NOT LIKE '%search_path%'
        ORDER BY 1;""", dsn=ADMIN)]
    record("every SECURITY DEFINER function pins its search path",
           not unpinned,
           f"unpinned: {unpinned or 'none'}")

    # --- the fenced vocabulary, including the three this slice must not use ---
    sources = "\n".join((REPO / name).read_text(encoding="utf-8") for name in SOURCES)
    pattern, terms = fenced_identifier_pattern()
    hits = sorted({m.group(0) for m in re.finditer(pattern, sources, re.I)})
    record("this slice names no permanently fenced domain",
           not hits,
           f"checked {len(SOURCES)} files — both migrations, the suite, the fixtures, "
           f"the probe, the service route and the whole customer surface — against all "
           f"{terms} authoritative terms: {hits or 'none'}")

    # EVERY fenced term, from the pinned vocabulary, against the live catalog — rather
    # than the handful FR-SRV-007B names, written out here. Two reasons. Restating them
    # is the defect tests/fenced.py exists to prevent: 46 of 63 authoritative terms once
    # passed the gate unnoticed because somebody had written a subset by hand. And the
    # broader check is the stronger one — it covers the requirement's list and the other
    # ten domains at the same time, over columns and tables any later migration adds.
    #
    # The pattern is built the same way fenced_identifier_pattern() builds its own:
    # anchored on a component boundary, so a two-letter term cannot match inside an
    # ordinary word.
    pattern_sql, _terms = fenced_identifier_pattern()
    identifiers = rows(f"""
        SELECT n.nspname || '.' || c.relname || '.' || a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('service', 'notify', 'integration') AND c.relkind = 'r'
          AND a.attnum > 0 AND NOT a.attisdropped
          AND (a.attname ~* '{pattern_sql}' OR c.relname ~* '{pattern_sql}')
        ORDER BY 1;""", dsn=ADMIN)
    record("FR-SRV-007B: no identifier in these schemas names a fenced concept",
           not identifiers,
           f"{[r[0] for r in identifiers] or 'none'}, against all {_terms} terms in the "
           f"pinned vocabulary rather than the subset this requirement happens to name. "
           f"Checked against the CATALOG, so a column added by any later migration is "
           f"covered without anybody extending this. Presence is a current state and "
           f"nothing about who worked when.")

    later = rows("""
        SELECT n.nspname || '.' || c.relname
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname IN ('notify', 'integration', 'service')
          AND (c.relname ~* '(^|_)(check|bill|payment|tip|receipt|journey|print_queue|'
                            'outlet_node|sync_event)($|_)')
        ORDER BY 1;""", dsn=ADMIN)
    record("nothing belonging to a later slice was built here",
           not later,
           f"{[r[0] for r in later] or 'none'} — the waiter surface and journeys are "
           f"M3-D; checks, payments, tips and receipts are M4; the outlet node, sync and "
           f"the print queue are M5a")

    secrets = [name for name in SOURCES
               if re.search(r"(password|secret|token)\s*[=:]\s*['\"][A-Za-z0-9+/]{12,}",
                            (REPO / name).read_text(encoding="utf-8"))]
    record("no credential is written into this slice's source",
           not secrets,
           f"{secrets or 'none'}. The guest and staff tokens the fixtures mint are "
           f"generated per run from os.urandom and only their sha256 reaches the "
           f"database (FR-SEC-007)")


# ===========================================================================
# 13. Negative controls — each proved RED with a real defect, then GREEN
# ===========================================================================

def capture_function(signature: str) -> str:
    res = run(ADMIN, f"SELECT pg_get_functiondef('{signature}'::regprocedure);")
    if not res.ok or not res.out.strip():
        raise ProbeFailed(f"capture {signature}", res.err)
    return res.out


def prove_sql(control: str, gate, signature: str, break_sql: str, *,
              revert_sql: str = "", captured: list[str] | None = None) -> None:
    ok, _, detail = gate()
    if not ok:
        record(f"{control} — baseline", False,
               f"the gate was already failing before the break: {detail}")
        return

    originals = [capture_function(sig) for sig in (captured or [])]
    broke = run(ADMIN, break_sql)
    if not broke.ok:
        record(f"{control} — inject defect", False,
               f"could not plant the break: {broke.why()}")
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
            run(APP, revert_sql)

    green_ok, green_sig, green_detail = gate()
    record(f"{control} — GREEN after revert", green_ok,
           green_detail if green_ok else f"{green_sig}: {green_detail}")


def prove_surface(control: str, gate, signature: str,
                  edits: list[tuple[Path, str, str]]) -> None:
    """The same, for a defect in the CUSTOMER SURFACE. Measured, because the gate is."""
    ok, _, detail = gate()
    if not ok:
        record(f"{control} — baseline", False,
               f"the gate was already failing before the break: {detail}",
               evidence="measured")
        return

    originals = [(path, path.read_text(encoding="utf-8")) for path, _, _ in edits]
    try:
        for path, old, new in edits:
            text = path.read_text(encoding="utf-8")
            if old not in text:
                record(f"{control} — inject defect", False,
                       f"anchor not found in {path.name}: {old[:60]!r}",
                       evidence="measured")
                return
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
        rebuild_surface()
        red_ok, red_sig, red_detail = gate()
        record(f"{control} — RED with the defect planted",
               (not red_ok) and red_sig == signature,
               f"{red_sig or '(the gate still passed)'}: {red_detail}",
               evidence="measured")
    finally:
        for path, original in originals:
            path.write_text(original, encoding="utf-8")
        rebuild_surface()

    green_ok, green_sig, green_detail = gate()
    record(f"{control} — GREEN after revert", green_ok,
           green_detail if green_ok else f"{green_sig}: {green_detail}",
           evidence="measured")


SURFACE_SRC = WORKSPACE / "pwa" / "src" / "app.ts"


# --- FR-SRV-006, both directions ---------------------------------------------

def deliberate_repeat_gate() -> tuple[bool, str, str]:
    """A guest who means to ask again must be able to."""
    fx.set_presence("available")
    seated = fx.a_seated_guest(table=fx.TABLE_TWO)
    first = raise_request(seated, "water", key=f"dr-{os.urandom(5).hex()}")
    if not first.ok:
        return False, "RAISE_FAILED", first.why()
    again = raise_request(seated, "water", key=f"dr-{os.urandom(5).hex()}",
                          deliberate=True)
    if not again.ok:
        return False, "DELIBERATE_REPEAT_SUPPRESSED", again.why()
    if (again.scalar or "").strip() == (first.scalar or "").strip():
        return (False, "DELIBERATE_REPEAT_SUPPRESSED",
                "a deliberate repeat inside the window collapsed into the request that "
                "was already open; the guest asked twice and was heard once")
    total = live_requests(seated["session"], "water")
    if total != 2:
        return (False, "DELIBERATE_REPEAT_SUPPRESSED",
                f"{total} request(s) after a first ask and a deliberate repeat")
    return (True, "",
            f"two requests, ordinals 1 and 2, in one deduplication group — the guest "
            f"asked twice and was heard twice")


def accidental_repeat_gate() -> tuple[bool, str, str]:
    """A double tap must not become two alerts."""
    fx.set_presence("available")
    seated = fx.a_seated_guest(table=fx.TABLE_TWO)
    first = raise_request(seated, "water", key=f"ar-{os.urandom(5).hex()}")
    if not first.ok:
        return False, "RAISE_FAILED", first.why()
    one = (first.scalar or "").strip()
    second = raise_request(seated, "water", key=f"ar-{os.urandom(5).hex()}")
    if not second.ok:
        return False, "RAISE_FAILED", second.why()
    total = live_requests(seated["session"], "water")
    alerts = count(APP, f"""
        SELECT count(*) FROM notify.notification
        WHERE subject_kind = 'service_request'
          AND subject_id IN (SELECT id FROM service.service_request
                              WHERE table_session_id = '{seated["session"]}'
                                AND request_type_id = '{fx.request_type("water")}')
          AND event_id = 'EVT-SERVICE-REQUESTED';""", **CTX)
    if total != 1 or alerts != 1:
        return (False, "DUPLICATE_ALERT_EMITTED",
                f"a second tap {(second.scalar or '').strip()[:8]} against the first "
                f"{one[:8]} left {total} request(s) and {alerts} alert(s); rapid "
                f"repeated taps are supposed to collapse into one")
    return (True, "", "one request and one alert after two taps inside the window")


# --- FR-SRV-009 ---------------------------------------------------------------

def staff_identity_gate() -> tuple[bool, str, str]:
    """MEASURED. No staff name on a customer screen unless the outlet configured it.

    Seats its own guest and raises its own request rather than reusing the one section 10
    measured. Every fixture that seats a guest CLOSES whatever occupancy was at that
    table, so a gate holding a session from earlier in the run measures an empty panel —
    and an empty panel names nobody, which would have passed for the wrong reason.
    """
    fx.set_presence("available")
    seated = fx.a_seated_guest_with_credential()
    raised = raise_request(seated, "call_waiter", key=f"si-{os.urandom(5).hex()}")
    if not raised.ok:
        return False, "RAISE_FAILED", raised.why()
    run(APP, f"""
        SELECT service.acknowledge_request('{fx.TENANT}', '{(raised.scalar or '').strip()}',
                                           '{fx.USER}');""", **CTX)
    run(APP, f"SELECT notify.send_pending('{fx.TENANT}', '{fx.OUTLET_H1}');", **CTX)

    payload = customer_payload(seated["token"])
    if not payload["status"]:
        return False, "NOTHING_TO_MEASURE", "the guest has no request to be shown"
    probe = render(payload, CONTEXT["code"], locale="am")
    if probe.get("errors"):
        return False, "PROBE_FAILED", str(probe["errors"])[:300]
    view = probe["rendered"]
    names = [r[0] for r in rows(f"""
        SELECT display_name FROM identity.user_account
        WHERE tenant_id = '{fx.TENANT}' AND display_name IS NOT NULL;""")]
    shown = [n for n in names if n and n in view["documentText"]]
    inline = [s for s in view["statuses"] if s["visible"] and s["handledBy"]]
    if shown or inline:
        return (False, "STAFF_IDENTITY_DISCLOSED",
                f"the rendered document names {shown or [s['handledBy'] for s in inline]} "
                f"with no policy permitting disclosure")
    return (True, "",
            f"{len(view['statuses'])} status row(s) drawn and none names anybody; "
            f"{len(names)} staff names searched for in the whole document")


# --- FR-SRV-007B --------------------------------------------------------------

def presence_discarded_gate() -> tuple[bool, str, str]:
    fx.clear_presence()
    session_id = fx.set_presence("available")
    run(ADMIN, f"""
        UPDATE service.staff_presence SET observed_at = now() - interval '3 hours'
        WHERE tenant_id = '{fx.TENANT}';""")
    swept = run(APP, f"SELECT * FROM config.apply_retention('{fx.TENANT}');", **CTX)
    if not swept.ok:
        return False, "SWEEP_FAILED", swept.why()
    left = count(APP, f"""
        SELECT count(*) FROM service.staff_presence WHERE tenant_id = '{fx.TENANT}';""",
        **CTX)
    if left != 0:
        return (False, "EPHEMERAL_PRESENCE_RETAINED",
                f"{left} presence row(s) survived a retention window they were three "
                f"hours past. Gone means gone: not flagged, not set to offline, not "
                f"archived")
    # And the session path, independently.
    session_id = fx.set_presence("available")
    run(APP, f"SELECT service.end_presence_for_session('{session_id}');", **CTX)
    after_session = count(APP, f"""
        SELECT count(*) FROM service.staff_presence WHERE tenant_id = '{fx.TENANT}';""",
        **CTX)
    if after_session != 0:
        return (False, "EPHEMERAL_PRESENCE_RETAINED",
                f"{after_session} presence row(s) survived the session that asserted them")
    return (True, "", "both discard paths delete the row: the retention sweep and the "
                      "session ending")


# --- FR-NOT-010 ---------------------------------------------------------------

def sensitive_payload_gate() -> tuple[bool, str, str]:
    canary = f"CANARY-{os.urandom(4).hex()}"
    planted = run(ADMIN, f"""
        INSERT INTO notify.notification
            (id, tenant_id, outlet_id, event_id, subject_kind, subject_id,
             correlation_id, dedup_key, payload)
        VALUES (gen_random_uuid(), '{fx.TENANT}', '{fx.OUTLET_H1}',
                'EVT-SERVICE-REQUESTED', 'service_request', gen_random_uuid(),
                gen_random_uuid(), 'canary-{canary}',
                jsonb_build_object('guest_name', '{canary}'));""")
    if planted.ok:
        run(ADMIN, f"DELETE FROM notify.notification WHERE dedup_key = 'canary-{canary}';")
        return (False, "SENSITIVE_DATA_IN_NOTIFICATION",
                "a payload carrying a guest name was stored")
    prose = run(ADMIN, f"""
        INSERT INTO notify.notification
            (id, tenant_id, outlet_id, event_id, subject_kind, subject_id,
             correlation_id, dedup_key, payload)
        VALUES (gen_random_uuid(), '{fx.TENANT}', '{fx.OUTLET_H1}',
                'EVT-SERVICE-REQUESTED', 'service_request', gen_random_uuid(),
                gen_random_uuid(), 'canary2-{canary}',
                jsonb_build_object('reason_code', repeat('{canary}', 20)));""")
    if prose.ok:
        run(ADMIN, f"DELETE FROM notify.notification WHERE dedup_key = 'canary2-{canary}';")
        return (False, "SENSITIVE_DATA_IN_NOTIFICATION",
                "a paragraph travelled under an allowed key")
    return (True, "", f"both refused: {planted.why()[:70]}")


# --- FR-NOT-009 ---------------------------------------------------------------

def deep_link_scope_gate() -> tuple[bool, str, str]:
    """A customer link must resolve only for a guest live on the session it names."""
    seated = fx.a_seated_guest_with_credential()
    other = fx.a_seated_guest_with_credential(table=fx.TABLE_TWO)
    notice = scalar(f"""
        SELECT id::text FROM notify.notice
        WHERE tenant_id = '{fx.TENANT}' AND audience = 'customer' LIMIT 1;""")
    token = f"scope-{os.urandom(5).hex()}"
    issued = run(APP, f"""
        SELECT notify.issue_deep_link('{fx.TENANT}', '{notice}', '{token}',
            'table_session', '{seated["session"]}', '{seated["session"]}');""", **CTX)
    if not issued.ok:
        return False, "ISSUE_FAILED", issued.why()

    mine = run(APP, f"""
        SELECT * FROM notify.resolve_deep_link('{fx.TENANT}', '{token}',
                                               '{seated["guest"]}', NULL);""", **CTX)
    if not mine.ok:
        return False, "OWN_LINK_REFUSED", mine.why()

    theirs = run(APP, f"""
        SELECT * FROM notify.resolve_deep_link('{fx.TENANT}', '{token}',
                                               '{other["guest"]}', NULL);""", **CTX)
    if theirs.ok:
        return (False, "DEEP_LINK_CROSSES_SESSION_SCOPE",
                "a guest at another table followed a link issued for this one — the "
                "same boundary as M2-B's FOREIGN_SESSION_ACCEPTED, on a different path")
    if not theirs.failed_with("DEEP_LINK_OUT_OF_SCOPE"):
        return False, "REFUSED_WRONGLY", theirs.why()
    return (True, "",
            f"the guest it was issued for followed it; a guest at another table was "
            f"refused by name")


# --- FR-INT-007 ---------------------------------------------------------------

def replay_safety_gate() -> tuple[bool, str, str]:
    """A replay must re-run the same work, not produce a second effect."""
    fx.set_presence("available")
    seated = fx.a_seated_guest()
    raised = raise_request(seated, "bill", key=f"rs-{os.urandom(5).hex()}")
    if not raised.ok:
        return False, "RAISE_FAILED", raised.why()

    # Drive it to the queue through a real failure: no staff template for this event
    # would be a configuration defect, so use the authorization race instead.
    run(APP, f"""
        UPDATE identity.membership SET status = 'inactive', withdrawn_at = now()
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
           AND user_account_id = '{fx.USER}';""", **CTX)
    run(APP, f"""
        SELECT notify.send_pending('{fx.TENANT}', '{fx.OUTLET_H1}', 1);""", **CTX)
    run(APP, f"""
        UPDATE identity.membership SET status = 'active', withdrawn_at = NULL
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
           AND user_account_id = '{fx.USER}';""", **CTX)

    entry = scalar(f"""
        SELECT coalesce((SELECT id::text FROM integration.dead_letter
                          WHERE tenant_id = '{fx.TENANT}' AND state = 'open'
                          ORDER BY last_failed_at DESC LIMIT 1), '');""")
    if not entry:
        return False, "NOTHING_DEAD_LETTERED", "no open entry to replay"

    before = table_digests()
    replayed = run(APP, f"""
        SELECT integration.replay_dead_letter('{fx.TENANT}', '{entry}', '{fx.USER}');""",
        **CTX)
    run(APP, f"SELECT notify.send_pending('{fx.TENANT}', '{fx.OUTLET_H1}');", **CTX)
    after = table_digests()

    if not replayed.ok:
        # FR-NOT-007's unique index is the second lock, and it sits UNDER the replay: a
        # replay that tries to raise a second notice for one event and one recipient is
        # refused by it before the differential could see the row. That refusal is the
        # duplication being caught, not an unrelated failure, and naming which lock
        # caught it is the difference between a diagnostic and a shrug.
        if replayed.failed_with("23505"):
            return (False, "DUPLICATE_EFFECT_ON_REPLAY",
                    f"the replay tried to create a second notice for an event and "
                    f"recipient that already had one, and the one-per-recipient index "
                    f"refused it: {replayed.why()}")
        return False, "REPLAY_FAILED", replayed.why()

    changed = sorted(name for name in set(before) | set(after)
                     if before.get(name) != after.get(name))
    allowed = {"notify.notice", "integration.dead_letter"}
    extra = [name for name in changed if name not in allowed]
    if extra:
        return (False, "DUPLICATE_EFFECT_ON_REPLAY",
                f"the replay changed {extra}, which a replay of the same work must not "
                f"touch. Measured with the whole-schema differential over "
                f"{len(before)} tables enumerated from the catalog")
    return (True, "",
            f"only {changed} moved across {len(before)} tables; no second notification, "
            f"no second notice, no second request")


def section_controls() -> None:
    print("\n--- 13. Negative controls: each proved RED with a real defect, then GREEN ---")

    # The same control in two directions. A dedup that never suppresses passes one and
    # fails the other, which is why both are here.
    print("\n  NC-M3C-001  deduplication swallows a deliberate repeat")
    always = capture_function(
        "service.raise_request(uuid,uuid,uuid,uuid,text,uuid,uuid,uuid,text,boolean)")
    prove_sql("NC-M3C-001", deliberate_repeat_gate, "DELIBERATE_REPEAT_SUPPRESSED",
              # The realistic shape: somebody "simplifies" the condition and the flag
              # stops being read at all.
              always.replace("IF NOT p_deliberate\n           AND now()", "IF now()", 1),
              captured=["service.raise_request(uuid,uuid,uuid,uuid,text,uuid,uuid,uuid,"
                        "text,boolean)"])

    print("\n  NC-M3C-002  an accidental double tap raises a second alert")
    prove_sql("NC-M3C-002", accidental_repeat_gate, "DUPLICATE_ALERT_EMITTED",
              always.replace("IF NOT p_deliberate\n           AND now() <",
                             "IF false AND now() <", 1),
              captured=["service.raise_request(uuid,uuid,uuid,uuid,text,uuid,uuid,uuid,"
                        "text,boolean)"])

    print("\n  NC-M3C-003  a staff name reaches a customer screen unconfigured")
    status_fn = capture_function("service.customer_status(uuid,uuid,uuid)")
    prove_sql("NC-M3C-003", staff_identity_gate, "STAFF_IDENTITY_DISCLOSED",
              # Fail OPEN instead of closed: the shape this defect actually takes.
              status_fn.replace("v_disclose := coalesce((v_policy ->> "
                                "'disclose_staff_identity_to_customer')::boolean,\n"
                                "                               false);",
                                "v_disclose := true;", 1),
              captured=["service.customer_status(uuid,uuid,uuid)"])

    print("\n  NC-M3C-004  presence survives its retention window")
    prove_sql("NC-M3C-004", presence_discarded_gate, "EPHEMERAL_PRESENCE_RETAINED",
              # Marked rather than deleted — the defect the requirement is aimed at.
              # The realistic shape: somebody excludes one table from the sweep — "we
              # will tidy those up later" — and its rows quietly become permanent.
              capture_function("config.apply_retention(uuid)").replace(
                  "        IF r.action = 'purge' THEN",
                  "        IF r.target_schema = 'service'\n"
                  "           AND r.target_table = 'staff_presence' THEN\n"
                  "            v_count := 0;\n"
                  "        ELSIF r.action = 'purge' THEN", 1),
              captured=["config.apply_retention(uuid)"])

    print("\n  NC-M3C-005  sensitive data reaches a notification payload")
    prove_sql("NC-M3C-005", sensitive_payload_gate, "SENSITIVE_DATA_IN_NOTIFICATION",
              # The predicate stops looking. Written out rather than cut out of the
              # captured body: surgery on a dollar-quoted function is how a break comes
              # to fail for a syntax error instead of for the reason it was planted.
              """CREATE OR REPLACE FUNCTION notify.payload_within_bounds(p_payload jsonb)
                 RETURNS boolean LANGUAGE sql IMMUTABLE
                 AS $broken$ SELECT jsonb_typeof(p_payload) = 'object'; $broken$;""",
              captured=["notify.payload_within_bounds(jsonb)"])

    print("\n  NC-M3C-006  a deep link resolves for an unauthorized session")
    prove_sql("NC-M3C-006", deep_link_scope_gate, "DEEP_LINK_CROSSES_SESSION_SCOPE",
              capture_function("notify.resolve_deep_link(uuid,text,uuid,uuid)").replace(
                  "OR NOT service.guest_is_live_on_session(p_tenant_id, p_guest_session_id,\n"
                  "                                                   l.scope_table_session_id) THEN",
                  "OR false THEN", 1),
              captured=["notify.resolve_deep_link(uuid,text,uuid,uuid)"])

    print("\n  NC-M3C-007  a dead-letter replay causes a duplicate effect")
    prove_sql("NC-M3C-007", replay_safety_gate, "DUPLICATE_EFFECT_ON_REPLAY",
              # Re-EMIT rather than re-run: the shape a replay defect actually takes, and
              # the one the differential is there to catch.
              capture_function("integration.replay_dead_letter(uuid,uuid,uuid,text)")
              .replace(
                  "UPDATE notify.notice\n           SET state = 'pending', "
                  "last_failure = NULL, last_failed_at = NULL\n         WHERE tenant_id "
                  "= p_tenant_id AND id = dl.subject_id\n           AND state = "
                  "'dead_lettered';",
                  "INSERT INTO notify.notice\n            (id, tenant_id, outlet_id, "
                  "notification_id, audience, recipient_user_id,\n             "
                  "recipient_guest_session_id, locale)\n         "
                  "SELECT gen_random_uuid(), d.tenant_id, d.outlet_id, d.notification_id,"
                  "\n                d.audience, d.recipient_user_id, "
                  "d.recipient_guest_session_id, d.locale\n         "
                  "  FROM notify.notice d WHERE d.id = dl.subject_id;", 1),
              captured=["integration.replay_dead_letter(uuid,uuid,uuid,text)"])


# ===========================================================================

def main() -> int:
    print("=" * 74)
    print("M3-C VERIFICATION — service requests, notifications, integration runtime")
    print(f"real PostgreSQL, real compiled service, real Chromium (running on "
          f"{platform.system()})")
    print("evidence encoding: UTF-8")
    print("\n  (measured) = read out of a real browser's own layout after it rendered")
    print("  (asserted) = read from source, from a payload, or from the database\n")
    print("=" * 74)

    # FAIL CLOSED. A suite that could not read the pinned package and carried on with a
    # transition table or an event list of its own would be checking the schema against
    # itself.
    try:
        states, edges = pinned_machine()
        events = pinned_events()
    except PackageUnavailable as error:
        print(f"\nFAIL PINNED_PACKAGE_UNAVAILABLE: {error}")
        return 1
    CONTEXT["states"], CONTEXT["edges"] = states, edges
    print(f"\nSM-SERVICE-REQUEST loaded from the pinned package: {len(states)} states, "
          f"{len(edges)} legal edges, {len(states) * (len(states) - 1)} ordered pairs")
    print(f"events.json loaded from the pinned package: {len(events)} event kinds")

    fx.seed()
    print("fixtures seeded: seven request types, approved templates in three languages, "
          "an attendant and a supervisor")

    sync_and_build()

    walk = fx.a_seated_guest()
    fx.set_presence("available")
    CONTEXT["walk_request"] = unrouted_request(walk)

    with Service(APP) as service:
        CONTEXT["base_url"] = f"http://127.0.0.1:{service.port}"
        CONTEXT["restart"] = service.restart
        CONTEXT["service_log"] = service.logs
        CONTEXT["code"] = fx.m2c.fresh_occupancy_and_code() \
            if hasattr(fx.m2c, "fresh_occupancy_and_code") else ""

        section_machine(states, edges, events)
        section_transitions(states, edges)
        section_catalog_and_lifecycle()
        section_deduplication()
        section_presence()
        section_sla_and_escalation()
        section_no_sensitive_leakage()
        section_templates_and_links()
        section_dead_letter()
        section_customer_surface()
        section_correlation_and_rebuild()
        section_governance()
        section_controls()

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
        print("FAIL M3C_VERIFICATION")
        return 1
    print("PASS M3C_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
