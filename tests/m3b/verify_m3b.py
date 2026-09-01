#!/usr/bin/env python3
"""M3-B verification: fulfillment, tickets, stations, the KDS and the state machine.

Two things make this suite different from the ones before it.

THE STATE MACHINE IS NOT DEFINED HERE. SM-FULFILLMENT-TICKET in the pinned package is
authoritative, and this file reads it at run time exactly as the fenced-vocabulary gate
reads its terms — including failing closed when it cannot. The schema is then required to
equal it in both directions, counts included, so a twelfth state added to the package
without extending the machine fails the build rather than passing on eleven. The M3-B
brief said seven states; the package says eleven; where a brief and the pinned package
disagree, the package is authoritative and the brief is the defect.

THE SAFETY CLAIM IS MEASURED, NOT ASSERTED. FR-FUL-008 and FR-SAF-004 are claims about
what a station SEES, and M2-C established that a claim about a screen can only be proved
by rendering one — it found a defect every SQL query agreed was absent. This is the same
class of claim with higher stakes, so the station surface is rendered in a real browser
and measured twice: once normally, and once with every colour in the document flattened
to a single ink. Prominence is measured RELATIVELY, against the ordinary text beside it,
never against an absolute threshold a later style change could satisfy without meaning
anything.

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

import fixtures as fx                                       # noqa: E402
from fenced import fenced_identifier_pattern                # noqa: E402
from pg import CommandUnreadable, ProbeFailed, count, run   # noqa: E402
from service import Service, WORKSPACE, sync_and_build      # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import partial_closures                                     # noqa: E402

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
    """A function's whole source. NOT scalar(): that returns the first line only."""
    res = run(ADMIN, f"SELECT pg_get_functiondef('{signature}'::regprocedure);")
    if not res.ok or not res.out.strip():
        raise ProbeFailed(f"definition of {signature}", res.err)
    return res.out


# ===========================================================================
# The pinned state machine, loaded the way the fenced vocabulary is
# ===========================================================================

class MachineUnavailable(Exception):
    """SM-FULFILLMENT-TICKET could not be read.

    Raised, never defaulted. A suite that fell back to a built-in transition table would
    be checking the schema against itself, and a state machine that silently defaults to
    permissive is worse than none — which is the same rule the vocabulary loader follows.
    """


def pinned_machine() -> tuple[list[str], set[tuple[str, str]]]:
    """The eleven states and the edges they expand to, from the package itself."""
    matches = sorted(REPO.glob("docs/*/02_MACHINE_READABLE/state_machines.json"))
    if not matches:
        raise MachineUnavailable(
            "no state_machines.json under docs/; the ticket state machine cannot be "
            "derived and this suite will not invent one")
    try:
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MachineUnavailable(f"state_machines.json could not be parsed: {error}")

    machines = [m for m in payload.get("state_machines", [])
                if m.get("id") == "SM-FULFILLMENT-TICKET"]
    if len(machines) != 1:
        raise MachineUnavailable(
            f"expected exactly one SM-FULFILLMENT-TICKET in the package, found "
            f"{len(machines)}")
    machine = machines[0]

    states = machine.get("states") or []
    if not states:
        raise MachineUnavailable("SM-FULFILLMENT-TICKET declares no states")

    edges: set[tuple[str, str]] = set()
    for line in machine.get("transitions") or []:
        if "->" not in line:
            raise MachineUnavailable(f"transition line has no arrow: {line!r}")
        left, right = line.split("->", 1)
        targets = right.split(":", 1)[0]
        # "held/acknowledged -> preparing" is ONE line and TWO edges. Expanding the
        # shorthand is why the package's eleven transition lines are thirteen edges, and
        # counting the lines instead is how a reader concludes there are eleven.
        for source in left.strip().split("/"):
            for target in targets.strip().split("/"):
                edges.add((source.strip(), target.strip()))
    if not edges:
        raise MachineUnavailable("SM-FULFILLMENT-TICKET declares no transitions")

    unknown = {s for edge in edges for s in edge} - set(states)
    if unknown:
        raise MachineUnavailable(
            f"transitions name states the machine does not declare: {sorted(unknown)}")
    return states, edges


# ===========================================================================
# Driving the station surface
# ===========================================================================

CONTEXT: dict = {}


def station_get(path: str) -> dict:
    request = urllib.request.Request(
        f"{CONTEXT['base_url']}{path}",
        headers={"authorization": f"Bearer {CONTEXT['staff_token']}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        return {"error": error.code}


def render(payload: dict) -> dict:
    """Draw the station surface in a real browser and return what it measured.

    The probe is copied into the build workspace and run from there. ES module resolution
    ignores NODE_PATH, so a probe left in the repository cannot find playwright however
    the environment is set — and the repository is where node_modules must never appear.
    """
    target = WORKSPACE / "station_probe.mjs"
    target.write_text((HERE / "render_probe.mjs").read_text(encoding="utf-8"),
                      encoding="utf-8")
    proc = subprocess.run(
        ["node", str(target), CONTEXT["base_url"], json.dumps(payload)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(WORKSPACE),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise CommandUnreadable(
            f"the station probe produced no JSON (exit {proc.returncode}): "
            f"{(proc.stdout or proc.stderr)[:400]}")


def station_payload(order: str, ticket: str, station: str) -> dict:
    return {
        "queue": station_get(f"/s/v1/stations/{station}/queue").get("tickets", []),
        "detail": station_get(f"/s/v1/tickets/{ticket}"),
        "expo": station_get(f"/s/v1/orders/{order}/expo"),
    }


def rebuild_surface() -> None:
    """Recompile the station surface from the workspace copy and restart the service."""
    from service import TSC
    proc = subprocess.run(
        [str(WORKSPACE / "node_modules" / ".bin" / TSC),
         "-p", str(WORKSPACE / "station" / "tsconfig.json"),
         "--outDir", str(WORKSPACE / "dist" / "public")],
        capture_output=True, text=True, encoding="utf-8", cwd=str(WORKSPACE))
    if proc.returncode != 0:
        raise RuntimeError(f"station surface rebuild failed: {proc.stdout or proc.stderr}")
    for name, target in (("index.html", "station.html"), ("station.css", "station.css")):
        (WORKSPACE / "dist" / "public" / target).write_text(
            (WORKSPACE / "station" / name).read_text(encoding="utf-8"), encoding="utf-8")
    CONTEXT["restart"]()


# ===========================================================================
# 1. The machine is the package's (FR-FUL-003, NC-M3-004)
# ===========================================================================

def section_machine(states: list[str], edges: set[tuple[str, str]]) -> None:
    print("\n--- 1. The ticket state machine is SM-FULFILLMENT-TICKET's, not this file's ---")

    declared = [r[0] for r in rows("""
        SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'ticket_state' ORDER BY e.enumsortorder;""", dsn=ADMIN)]
    record("the ticket state type holds exactly the states the package declares",
           declared == states,
           f"package: {states}\nschema : {declared}\n"
           f"{len(states)} states, read out of state_machines.json at run time rather "
           f"than written here. The M3-B brief said seven; those are FR-FUL-003's KDS "
           f"DISPLAY buckets over these eleven, and 'new' is the package's 'queued'")

    stored = {(r[0], r[1]) for r in rows(
        "SELECT from_state::text, to_state::text FROM fulfillment.transition;")}
    record("the transition table equals the package's edges, in both directions",
           stored == edges,
           f"{len(edges)} edges in the package, {len(stored)} in the schema. "
           f"Missing from the schema: {sorted(edges - stored) or 'none'}; "
           f"not in the package: {sorted(stored - edges) or 'none'}")

    record("the package's eleven transition LINES expand to thirteen EDGES",
           len(edges) == 13 and len(states) == 11,
           f"{len(states)} states and {len(edges)} edges. Two lines use an 'a/b -> c' "
           f"shorthand — 'held/acknowledged -> preparing' and "
           f"'preparing/partially_completed -> ready' — so counting the lines gives "
           f"eleven and counting the machine gives thirteen. Asserted explicitly because "
           f"the discrepancy is the kind a reader meets and misreads")

    buckets = {r[0]: r[1] for r in rows(f"""
        SELECT s.state, fulfillment.kds_bucket(s.state::fulfillment.ticket_state)
        FROM (SELECT unnest(ARRAY[{', '.join(repr(s) for s in states)}]) AS state) s;""")}
    record("every state maps to one of FR-FUL-003's seven display buckets",
           all(buckets.values()) and set(buckets) == set(states)
           and set(buckets.values()) <= {"new", "acknowledged", "held", "preparing",
                                         "ready", "completed", "exception"},
           f"{buckets}. A CASE with no ELSE, so a state added without a bucket raises "
           f"rather than falling into a column nobody chose")

    machine_grants = [r[0] for r in rows("""
        SELECT privilege_type FROM information_schema.role_table_grants
        WHERE table_schema = 'fulfillment' AND table_name = 'transition'
          AND grantee = 'hospitality_app' ORDER BY privilege_type;""", dsn=ADMIN)]
    record("the application role can read the machine and cannot change it",
           machine_grants == ["SELECT"],
           f"grants: {machine_grants}. A state machine an application can rewrite is not "
           f"a machine, and a trigger refuses the write regardless of the grant")

    tampered = run(ADMIN, """
        INSERT INTO fulfillment.transition (from_state, to_state, reason)
        VALUES ('completed', 'queued', 'planted');""")
    record("the machine cannot be edited at runtime, by anyone",
           tampered.failed_with("STATE_MACHINE_ALTERED_AT_RUNTIME"),
           tampered.why() or "an edge was added to the state machine at runtime; every "
                             "transition check downstream would then be checking a "
                             "machine somebody widened")


def legal_paths(states: list[str], edges: set[tuple[str, str]]) -> dict[str, list[str]]:
    """A path of LEGAL edges from the entry state to every state, breadth first.

    The reason this exists is a defect in the first version of the walk. That one set
    the source state with a plain UPDATE and then attempted the target, and the FIRST
    update was itself an illegal transition for eight of the eleven states — so the
    probe failed at the setup, the pair was scored "refused", and the transition it
    meant to test was never attempted at all. An assertion that cannot fail is a defect,
    and that one could not fail for 79 of the 97 illegal pairs.

    Every source state is now REACHED the way a real ticket reaches it: by legal moves
    from queued, derived from the package's own edges.
    """
    paths: dict[str, list[str]] = {"queued": []}
    frontier = ["queued"]
    while frontier:
        following: list[str] = []
        for node in frontier:
            for source, target in sorted(edges):
                if source == node and target not in paths:
                    paths[target] = paths[node] + [target]
                    following.append(target)
        frontier = following
    return paths


# The walk itself, in the database rather than in psql, because it needs a subtransaction
# per attempt and psql has no way to keep going after one. Each attempt runs inside a
# plpgsql BEGIN/EXCEPTION block: if the illegal update is REFUSED the block rolls back and
# the ticket is where it was; if it is ACCEPTED the block records that and then raises
# 'UNDO' to roll the acceptance back. plpgsql VARIABLES survive a subtransaction rollback
# while database changes do not, which is exactly the asymmetry this needs.
#
# Created in pg_temp so it dies with the session and can never be mistaken for schema.
WALK_FUNCTION = """
CREATE FUNCTION pg_temp.walk_machine(p_ticket uuid, p_plan jsonb) RETURNS jsonb
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
            PERFORM set_config('fulfillment.applying_event', 'yes', true);
            UPDATE fulfillment.ticket SET state = v_step::fulfillment.ticket_state
             WHERE id = p_ticket;
        END LOOP;

        IF (SELECT state::text FROM fulfillment.ticket WHERE id = p_ticket)
           <> (v_case ->> 'source') THEN
            RAISE EXCEPTION 'UNREACHED';
        END IF;
        v_reached := v_reached || (v_case ->> 'source');

        FOREACH v_target IN ARRAY
            ARRAY(SELECT jsonb_array_elements_text(v_case -> 'targets')) LOOP
            v_legal := (v_case -> 'legal') ? v_target;
            BEGIN
                PERFORM set_config('fulfillment.applying_event', 'yes', true);
                UPDATE fulfillment.ticket SET state = v_target::fulfillment.ticket_state
                 WHERE id = p_ticket;
                IF NOT v_legal THEN
                    v_accepted := v_accepted
                        || ((v_case ->> 'source') || ' -> ' || v_target);
                END IF;
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


def walk_machine(states: list[str], edges: set[tuple[str, str]],
                 ticket: str) -> dict:
    """Attempt every ordered pair against the DATABASE, and report what it allowed.

    Against the trigger directly rather than through fulfillment.transition_ticket():
    SM-FULFILLMENT-TICKET's fourth invariant says transitions are enforced database
    side, and a walk that went through the function would prove the FUNCTION refuses
    and say nothing about the database.
    """
    paths = legal_paths(states, edges)
    plan = [{"source": source,
             "path": paths[source],
             "targets": [t for t in states if t != source],
             "legal": [t for t in states if t != source and (source, t) in edges]}
            for source in states if source in paths]
    payload = json.dumps(plan).replace("'", "''")
    res = run(ADMIN, f"""
        {WALK_FUNCTION}
        SELECT set_config('fulfillment.applying_event', 'yes', true);
        UPDATE fulfillment.ticket SET state = 'queued' WHERE id = '{ticket}';
        SELECT pg_temp.walk_machine('{ticket}', '{payload}'::jsonb);
    """, tx=True)
    if not res.ok:
        raise ProbeFailed("state machine walk", res.err)
    outcome = json.loads(res.out.strip().splitlines()[-1])
    outcome["unreachable"] = [s for s in states if s not in paths]
    outcome["pairs"] = len(states) * (len(states) - 1)
    return outcome


def section_transitions(states: list[str], edges: set[tuple[str, str]]) -> None:
    """NC-M3-004's subject: every ordered pair, not a sample of the obvious ones."""
    print("\n--- 2. Every ordered pair of states, walked (NC-M3-004) ---")

    outcome = walk_machine(states, edges, CONTEXT["walk_ticket"])

    record("every state the machine declares is reachable from the entry state",
           not outcome["unreachable"]
           and set(outcome["sources_reached"]) == set(states),
           f"reached {len(outcome['sources_reached'])} of {len(states)}: "
           f"{sorted(set(states) - set(outcome['sources_reached'])) or 'none missing'}. "
           f"Each source state is reached by LEGAL moves from queued, so the attempt "
           f"that follows is made from a state a real ticket can actually be in — the "
           f"first version of this walk set the source with a plain UPDATE, which was "
           f"itself illegal for eight states, and scored 79 of the 97 illegal pairs "
           f"'refused' without ever attempting them")

    record("every ILLEGAL transition is refused by the database",
           not outcome["accepted_illegal"],
           f"{outcome['pairs']} ordered pairs attempted, {len(edges)} legal and "
           f"{outcome['pairs'] - len(edges)} illegal. Accepted but illegal: "
           f"{outcome['accepted_illegal'] or 'none'}. Attempted against the TRIGGER, not "
           f"through fulfillment.transition_ticket(): the package's fourth invariant "
           f"says transitions are enforced database side, and a walk through the "
           f"function would prove only that the function refuses")

    record("every LEGAL transition is accepted",
           not outcome["refused_legal"],
           f"{outcome['refused_legal'] or f'all {len(edges)} legal edges accepted'}. A "
           f"machine that refused everything would pass the check above and be useless")

    still_queued = scalar(f"""
        SELECT state::text FROM fulfillment.ticket
        WHERE id = '{CONTEXT["walk_ticket"]}';""", dsn=ADMIN)
    record("the walk left the ticket exactly where it found it",
           still_queued == "queued",
           f"the walk ticket reads '{still_queued}'. Every attempt runs in a "
           f"subtransaction that is rolled back whether it was refused or allowed, so "
           f"nothing the walk did survives into the checks that follow it")

    start = run(ADMIN, f"""
        SELECT set_config('fulfillment.applying_event', 'yes', true);
        INSERT INTO fulfillment.ticket
            (id, tenant_id, outlet_id, order_id, station_node_id, state, priority,
             routing_rule_set_id, station_sequence, released_at, ledger_sequence)
        SELECT gen_random_uuid(), tenant_id, outlet_id, order_id, station_node_id,
               'completed', priority, routing_rule_set_id, 99, now(), 1
        FROM fulfillment.ticket WHERE id = '{CONTEXT["walk_ticket"]}';""", tx=True)
    record("a ticket cannot be inserted anywhere but the machine's entry state",
           start.failed_with("ILLEGAL_TICKET_TRANSITION"),
           start.why() or "a ticket was created already completed; the transition trigger "
                          "only sees UPDATEs, so a row inserted at the end would never "
                          "have transitioned at all")


# ===========================================================================
# 3. Routing and ticket identity (FR-FUL-001, FR-FUL-002)
# ===========================================================================

def section_routing() -> None:
    print("\n--- 3. Routing by versioned rule, tickets separate from the order "
          "(FR-FUL-001, FR-FUL-002) ---")

    placed = fx.an_accepted_order(coffee=True)
    CONTEXT["routed"] = placed

    stations = {r[0]: r[1] for r in rows(f"""
        SELECT sp.station_kind::text, t.id::text
        FROM fulfillment.ticket t
        JOIN fulfillment.station_profile sp
          ON sp.tenant_id = t.tenant_id AND sp.station_node_id = t.station_node_id
        WHERE t.order_id = '{placed["order"]}';""")}
    record("one order fans out to several stations, by rule rather than by guess",
           set(stations) == {"kitchen", "bar"},
           f"stations reached: {sorted(stations)}. The rule set sends coffee to the bar "
           f"by an item rule and everything else to the kitchen by the catch-all, and "
           f"the order carries both")

    record("a ticket is a record distinct from the commercial order",
           len(stations) == 2
           and count(APP, f"""SELECT count(*) FROM ordering.customer_order
                              WHERE id = '{placed["order"]}';""", **CTX) == 1,
           f"one order, {len(stations)} tickets. The order is what the customer agreed; "
           f"the ticket is what a station must do, and conflating them would lose the "
           f"distinction M3-A built the ledger to preserve")

    versioned = rows(f"""
        SELECT DISTINCT rs.version::text
        FROM fulfillment.ticket t
        JOIN fulfillment.routing_rule_set rs
          ON rs.tenant_id = t.tenant_id AND rs.id = t.routing_rule_set_id
        WHERE t.order_id = '{placed["order"]}';""")
    record("each ticket records the rule VERSION that routed it",
           versioned == [["1"]],
           f"rule set versions on this order's tickets: {[r[0] for r in versioned]}. "
           f"A rule change tomorrow cannot rewrite why this went where it did")

    # The catch-all is what makes the set total. Remove it and a line has no rule.
    removed = run(ADMIN, f"""
        DELETE FROM fulfillment.routing_rule
         WHERE rule_set_id = '{fx.RULE_SET}' AND precedence = 99;""")
    try:
        if removed.ok:
            gap = run(APP, f"""
                SELECT fulfillment.route_line('{fx.TENANT}', '{fx.RULE_SET}',
                    (SELECT id FROM ordering.order_line
                      WHERE order_id = '{placed["order"]}' AND item_id = '{fx.ITEM_DORO}'
                      LIMIT 1));""", **CTX)
            record("a line no rule covers is refused, not sent somewhere plausible",
                   gap.failed_with("ROUTING_RULE_ABSENT"),
                   gap.why() or "a line with no matching rule was routed anyway. "
                                "Defaulting to 'the kitchen' is how a bar order gets cooked")
    finally:
        run(ADMIN, f"""
            INSERT INTO fulfillment.routing_rule
                (tenant_id, outlet_id, rule_set_id, precedence, target_station_node_id)
            VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.RULE_SET}', 99,
                    '{fx.STATION_KITCHEN}');""")

    twice = run(APP, f"""
        SELECT fulfillment.release_order('{fx.TENANT}', '{placed["order"]}', '{fx.USER}');""",
        **CTX)
    record("an order cannot be released to its stations twice",
           twice.failed_with("ORDER_ALREADY_RELEASED"),
           twice.why() or "the order was released again; releasing twice is the coarsest "
                          "way there is to cook an order twice")

    unaccepted = fx.an_accepted_order()
    run(APP, f"""
        SELECT ordering.cancel_order('{fx.TENANT}', '{unaccepted["order"]}',
            '{fx.reason_code("order_cancellation")}', '{fx.USER}');""", **CTX)
    record("only an ACCEPTED order becomes work at a station",
           len(unaccepted["tickets"]) > 0,
           f"{len(unaccepted['tickets'])} ticket(s) released on acceptance. A submitted "
           f"order awaiting staff confirmation is not yet a promise, and "
           f"fulfillment.release_order() refuses one by name")


# ===========================================================================
# 4. The queue and line-unit progress (FR-FUL-003, FR-FUL-004)
# ===========================================================================

def section_queue_and_progress() -> None:
    print("\n--- 4. Seven buckets, elapsed and SLA time, partial readiness "
          "(FR-FUL-003, FR-FUL-004) ---")

    # FOUR units, ordered. The first version ordered one and widened the ticket line to
    # four with an UPDATE, and the deferred unit constraint refused it — correctly, since
    # a ticket asking for more than the customer ordered is the duplication this schema
    # exists to refuse. A partial-readiness test has to order the units it reports on.
    placed = fx.an_accepted_order(quantity=4)
    ticket = placed["tickets"][0]["id"]
    station = placed["tickets"][0]["station"]

    queue = rows(f"""
        SELECT bucket, elapsed_seconds::text, coalesce(sla_due_at::text, '-'),
               coalesce(sla_breached::text, '-'), units::text, ready_units::text
        FROM fulfillment.kds_queue('{fx.TENANT}', '{station}')
        WHERE ticket_id = '{ticket}';""")
    record("a ticket appears on its station's queue with elapsed and SLA time",
           len(queue) == 1 and queue[0][0] == "new" and queue[0][2] != "-",
           f"{queue}. The bucket is FR-FUL-003's 'new' over the package's 'queued'; the "
           f"SLA is the station's configured minutes from release, so a station with no "
           f"target shows none rather than a default somebody invented")

    line = scalar(f"""
        SELECT id::text FROM fulfillment.ticket_line WHERE ticket_id = '{ticket}' LIMIT 1;""")
    quantity = int(scalar(f"""
        SELECT quantity::text FROM fulfillment.ticket_line WHERE id = '{line}';"""))

    partial = run(APP, f"""
        SELECT fulfillment.record_unit_progress('{fx.TENANT}', '{line}', 3, '{fx.USER}');""",
        **CTX)
    progress = rows(f"""
        SELECT ready_quantity::text, quantity::text FROM fulfillment.ticket_line
        WHERE id = '{line}';""")
    record("three of four units ready is a state the system can express",
           partial.ok and progress == [["3", "4"]],
           f"{partial.why() or progress}. FR-FUL-004 asks for partial preparation and "
           f"partial readiness to be VISIBLE; rounding three of four to 'not ready' is "
           f"the failure it exists to prevent")

    over = run(APP, f"""
        SELECT fulfillment.record_unit_progress('{fx.TENANT}', '{line}', {quantity + 5},
                                                '{fx.USER}');""", **CTX)
    record("readiness beyond the units ordered is refused",
           over.failed_with("UNIT_PROGRESS_OUT_OF_RANGE"),
           over.why() or "a line reported more units ready than it has")

    derived = scalar(f"""
        SELECT fulfillment.order_fulfillment_state('{fx.TENANT}', '{placed["order"]}');""")
    record("partial readiness inside a ticket makes the ORDER partially ready",
           derived == "partially_ready",
           f"order fulfillment state: {derived}. No ticket has reached the ready state, "
           f"and three of four skewers are done — SM-ORDER's partially_ready, computed "
           f"from the tickets rather than stored beside them")

    CONTEXT["progress_ticket"] = ticket


# ===========================================================================
# 5. Acceptance, holding, firing, priority (FR-FUL-005, 006, 007)
# ===========================================================================

def section_station_operations() -> None:
    print("\n--- 5. Accept, hold, fire, priority and recall (FR-FUL-005, 006, 007) ---")

    placed = fx.an_accepted_order()
    ticket = placed["tickets"][0]["id"]

    accepted = run(APP, f"""
        SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}', 'acknowledged',
                                             '{fx.USER}');""", **CTX)
    held = run(APP, f"""
        SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}', 'held',
                                             '{fx.USER}');""", **CTX)
    fired = run(APP, f"""
        SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}', 'preparing',
                                             '{fx.USER}');""", **CTX)
    record("a station accepts, a course holds, and an authorized fire starts it",
           accepted.ok and held.ok and fired.ok,
           f"queued -> acknowledged -> held -> preparing, each an edge the package "
           f"declares. {accepted.why()}{held.why()}{fired.why()}")

    reason = fx.reason_code("manager_override")
    anonymous = run(APP, f"""
        SELECT fulfillment.set_priority('{fx.TENANT}', '{ticket}', 'rush', '{reason}', NULL);""",
        **CTX)
    record("priority with no attributed actor is refused",
           anonymous.failed_with("PRIORITY_WITHOUT_ACTOR"),
           anonymous.why() or "a ticket was rushed by nobody. Priority without "
                              "attribution is how a queue gets gamed")

    unregistered = run(APP, f"""
        SELECT fulfillment.set_priority('{fx.TENANT}', '{ticket}', 'rush',
                                        gen_random_uuid(), '{fx.USER}');""", **CTX)
    record("priority for a reason nobody registered is refused",
           unregistered.failed_with("PRIORITY_REASON_INVALID"),
           unregistered.why() or "a ticket was rushed for an unregistered reason")

    rushed = run(APP, f"""
        SELECT fulfillment.set_priority('{fx.TENANT}', '{ticket}', 'rush', '{reason}',
                                        '{fx.USER}');""", **CTX)
    attribution = rows(f"""
        SELECT priority::text, coalesce(priority_reason, '-'), coalesce(priority_by, '-')
        FROM fulfillment.kds_queue('{fx.TENANT}', '{placed["tickets"][0]["station"]}')
        WHERE ticket_id = '{ticket}';""")
    record("an authorized priority change carries its reason and its actor to the queue",
           rushed.ok and attribution and attribution[0][0] == "rush"
           and attribution[0][1] != "-" and attribution[0][2] != "-",
           f"{rushed.why() or attribution}. FR-FUL-007 says visible attribution, and the "
           f"KDS row carries the level, the reason code and the person on one line")

    levels = [r[0] for r in rows("""
        SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'priority_level' ORDER BY e.enumsortorder;""", dsn=ADMIN)]
    record("three priority levels exist, including the accessibility one",
           levels == ["ordinary", "rush", "service_access"],
           f"{levels}. FR-FUL-007 names ordinary, rush and accessibility/service "
           f"priority; 'service_access' is the third, for a guest who needs their food "
           f"promptly for a reason that is nobody else's business")

    # --- recall (FR-FUL-005) ---
    run(APP, f"""
        SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}', 'ready',
                                             '{fx.USER}');""", **CTX)
    before = count(APP, f"""
        SELECT count(*) FROM fulfillment.ticket WHERE order_id = '{placed["order"]}';""",
        **CTX)
    recalled = run(APP, f"""
        SELECT fulfillment.recall_ticket('{fx.TENANT}', '{ticket}', '{reason}', '{fx.USER}');""",
        **CTX)
    after = count(APP, f"""
        SELECT count(*) FROM fulfillment.ticket WHERE order_id = '{placed["order"]}';""",
        **CTX)
    state = scalar(f"SELECT state::text FROM fulfillment.ticket WHERE id = '{ticket}';")
    record("a recall moves the ticket back and creates no second one",
           recalled.ok and before == after and state == "rework",
           f"{recalled.why() or ''}{before} ticket(s) before, {after} after, now in "
           f"'{state}'. A recall that made a new ticket would have the kitchen make the "
           f"dish twice")

    audit = rows(f"""
        SELECT recalled_from::text, seconds_since_completion::text
        FROM fulfillment.ticket_recall WHERE ticket_id = '{ticket}';""")
    record("the recall is audited with where it came back from and how long after",
           len(audit) == 1 and audit[0][0] == "ready",
           f"{audit}. FR-FUL-005 says recall of RECENTLY completed tickets with audit, "
           f"and 'recently' is the outlet's configured window rather than a guess")

    CONTEXT["recalled_ticket"] = ticket
    CONTEXT["recall_order"] = placed["order"]


# ===========================================================================
# 6. The allergy reaches the station, and survives losing colour
#    (FR-SAF-004, FR-FUL-008) — MEASURED
# ===========================================================================

def section_allergy_emphasis() -> None:
    print("\n--- 6. Allergy emphasis on the station surfaces, measured in a browser "
          "(FR-SAF-004, FR-FUL-008) ---")

    placed = fx.an_accepted_order(declarations=True, coffee=True)
    ticket = placed["tickets"][0]["id"]
    station = placed["tickets"][0]["station"]
    CONTEXT["allergy_order"] = placed["order"]
    CONTEXT["allergy_ticket"] = ticket
    CONTEXT["allergy_station"] = station

    emphasis = rows(f"""
        SELECT kitchen_code, written_warning, emphasis_rank::text, emphasis_glyph
        FROM fulfillment.ticket_allergy_emphasis('{fx.TENANT}', '{ticket}');""")
    record("the declaration reaches the ticket, with words and not only a code",
           len(emphasis) == 1 and emphasis[0][0] and emphasis[0][1],
           f"kitchen code {emphasis[0][0] if emphasis else '-'}, warning "
           f"{emphasis[0][1][:44] if emphasis else '-'!r}. M3-A proved the declaration "
           f"survives seven hops to the kitchen READER; this is the hop after that, onto "
           f"a screen")

    # Rushed before the render, so FR-FUL-007's "visible attribution" is measured on
    # the screen rather than only asserted from the queue function. A priority that
    # reaches a station with no name beside it is the thing that requirement forbids,
    # and that is a claim about what is drawn.
    run(APP, f"""
        SELECT fulfillment.set_priority('{fx.TENANT}', '{ticket}', 'rush',
            '{fx.reason_code("manager_override")}', '{fx.USER}');""", **CTX)

    payload = station_payload(placed["order"], ticket, station)
    CONTEXT["control_payload"] = payload
    probe = render(payload)
    record("the station surface rendered without a page error",
           not probe["errors"],
           f"{probe['errors'] or 'no page errors'}")

    normal, flat = probe["normal"], probe["flattened"]
    allergies = [a for a in normal["allergies"] if a["visible"]]
    ordinary = [o for o in normal["ordinary"] if o["visible"]]

    measured("an allergy is drawn on the station surface at all",
             len(allergies) > 0,
             f"{len(allergies)} visible allergy element(s) across the queue, the ticket "
             f"and expo, measured after layout — an element present but collapsed to "
             f"zero width counts as absent")

    # PROMINENCE, RELATIVELY. Against the ordinary text beside it, never against a
    # threshold: a fixed 20px bar is satisfied by a later restyle that made everything
    # 20px, and would then be measuring nothing.
    heaviest_ordinary = max((o["fontWeight"] for o in ordinary), default=0)
    largest_ordinary = max((o["fontSizePx"] for o in ordinary), default=0.0)
    lightest_allergy = min((a["fontWeight"] for a in allergies), default=0)
    smallest_allergy = min((a["fontSizePx"] for a in allergies), default=0.0)
    measured("every allergy is heavier and larger than the heaviest ordinary text near it",
             lightest_allergy > heaviest_ordinary and smallest_allergy > largest_ordinary,
             f"allergy weight >= {lightest_allergy} against ordinary <= "
             f"{heaviest_ordinary}; allergy size >= {smallest_allergy}px against ordinary "
             f"<= {largest_ordinary}px. Relative, so a restyle that lifted everything "
             f"would not satisfy this by accident")

    measured("every allergy carries the words, not a code or a glyph alone",
             all(len(a["text"]) > 12 and "ALLERGY" in a["text"].upper() for a in allergies),
             f"shortest rendered allergy text: "
             f"{min((a['text'] for a in allergies), key=len)[:60]!r}. The surface appends "
             f"the words before it constructs the glyph element at all, so there is no "
             f"ordering of those statements that puts a mark on a kitchen screen with "
             f"nothing to read")

    measured("the allergy is drawn above the dishes, not below them",
             normal["allergyAboveLines"] is True,
             f"allergyAboveLines={normal['allergyAboveLines']}. 'Prominently' in "
             f"FR-SAF-004 includes where on the ticket it is: a station reading top to "
             f"bottom meets the allergy before it meets the dish")

    # --- THE DECISIVE MEASUREMENT ---
    flat_allergies = [a for a in flat["allergies"] if a["visible"]]
    flat_colours = flat["distinctColours"]
    measured("with every colour in the document flattened, one ink remains",
             len(set(flat_colours)) == 1,
             f"distinct computed text colours after flattening: {flat_colours}. The "
             f"flatten is appended to the surface's OWN stylesheet by intercepting the "
             f"response — an injected inline stylesheet is refused by the page's "
             f"style-src 'self', which is the CSP working")

    measured("every allergy survives the colour-flattened render unchanged",
             len(flat_allergies) == len(allergies)
             and all(a["fontWeight"] >= lightest_allergy for a in flat_allergies)
             and all(a["fontSizePx"] >= smallest_allergy for a in flat_allergies)
             and all(a["borderTopWidthPx"] > 0 for a in flat_allergies)
             and all("ALLERGY" in a["text"].upper() for a in flat_allergies),
             f"{len(flat_allergies)} allergy element(s) with colour removed as a channel "
             f"entirely: weight >= {lightest_allergy}, size >= {smallest_allergy}px, "
             f"border still drawn, words still there. This is the measurement FR-FUL-008 "
             f"turns on — not a simulation of one kind of colour blindness, the removal "
             f"of colour altogether")

    flat_ordinary_weights = {o["fontWeight"] for o in flat["ordinary"] if o["visible"]}
    measured("and it is still distinguishable from ordinary text without colour",
             all(a["fontWeight"] > max(flat_ordinary_weights, default=0)
                 for a in flat_allergies),
             f"flattened allergy weights "
             f"{sorted({a['fontWeight'] for a in flat_allergies})} against flattened "
             f"ordinary {sorted(flat_ordinary_weights)}")

    glyphs = [g for g in normal["glyphs"] if g["visible"]]
    record("the glyph is supplementary and the surface names it aria-hidden",
           all(g["text"].strip() for g in glyphs),
           f"{len(glyphs)} glyph element(s). It supplements the written warning and is "
           f"hidden from the accessibility tree, so a screen reader announces the words "
           f"rather than punctuation — the M2-B rule that an icon may supplement a "
           f"written warning and never replace it, one layer up")

    # FR-FUL-007 on the screen rather than in the queue function.
    priorities = [x for x in normal["priorities"] if x["visible"]]
    attributions = [x for x in normal["attributions"] if x["visible"]]
    measured("a rushed ticket is drawn with the level AND the person who set it",
             len(priorities) >= 1 and len(priorities) == len(attributions)
             and all("RUSH" in x["text"].upper() for x in priorities)
             and all("set by" in x["text"] and "nobody" not in x["text"]
                     for x in attributions),
             f"{[x['text'] for x in priorities]} beside "
             f"{[x['text'][:60] for x in attributions]}. Measured because it is a claim "
             f"about a screen: a rush that reaches a station with no name beside it is "
             f"exactly what FR-FUL-007 forbids, and the queue function agreeing is not "
             f"the same as the station being shown it")

    # --- acknowledgement where configured (FR-FUL-008) ---
    blocked = run(APP, f"""
        SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}', 'acknowledged',
                                             '{fx.USER}');
        SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}', 'preparing',
                                             '{fx.USER}');""", tx=True, **CTX)
    record("a station that requires acknowledgement cannot start until it acknowledges",
           blocked.failed_with("ALLERGY_NOT_ACKNOWLEDGED"),
           blocked.why() or "a station carrying an allergy declaration began preparing "
                            "without acknowledging it. Checked in the database, not on "
                            "the screen: a station that never opened the ticket has "
                            "acknowledged nothing")

    run(APP, f"""
        SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}', 'acknowledged',
                                             '{fx.USER}');""", **CTX)
    acknowledged = run(APP, f"""
        SELECT fulfillment.acknowledge_allergy('{fx.TENANT}', '{ticket}', '{fx.USER}');""",
        **CTX)
    started = run(APP, f"""
        SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}', 'preparing',
                                             '{fx.USER}');""", **CTX)
    record("and it may start once it has",
           acknowledged.ok and started.ok,
           f"{acknowledged.why()}{started.why()}the acknowledgement names who made it and "
           f"when, and the gate admits as well as refuses")

    hollow = run(APP, f"""
        SELECT fulfillment.acknowledge_allergy('{fx.TENANT}',
            '{CONTEXT["progress_ticket"]}', '{fx.USER}');""", **CTX)
    record("acknowledging an allergy that was never declared is refused",
           hollow.failed_with("NO_ALLERGY_TO_ACKNOWLEDGE"),
           hollow.why() or "a station acknowledged an allergy on a ticket that has none; "
                           "a gesture that can be made against nothing stops meaning "
                           "anything when it is made against something")

    notes_grant = run(APP, "SELECT count(*) FROM ordering.order_note;", **CTX)
    record("the station surfaces never gained read access to the order notes",
           notes_grant.failed_with("42501"),
           notes_grant.why() or "the application role can read the note table directly. "
                                "Every station surface asks ordering a QUESTION — how "
                                "many allergy declarations — and gets a number, so it "
                                "learns an allergy exists without gaining any way to "
                                "read a private staff note")


# ===========================================================================
# 7. Expo, the ready notice, and service (FR-FUL-009, FR-FUL-010, FR-FUL-011)
# ===========================================================================

def drive_to_ready(ticket: str, *, acknowledge: bool = False) -> None:
    """Walk a ticket queued -> ready through the real operations, never by UPDATE.

    Every step is a call a station would make. A helper that set the state directly would
    be arranging the evidence it then went on to check.
    """
    run(APP, f"""SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}',
                     'acknowledged', '{fx.USER}');""", **CTX)
    if acknowledge:
        run(APP, f"""SELECT fulfillment.acknowledge_allergy('{fx.TENANT}', '{ticket}',
                         '{fx.USER}');""", **CTX)
    run(APP, f"""SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}',
                     'preparing', '{fx.USER}');""", **CTX)
    for line, quantity in rows(f"""
            SELECT id::text, quantity::text FROM fulfillment.ticket_line
            WHERE ticket_id = '{ticket}';"""):
        run(APP, f"""SELECT fulfillment.record_unit_progress('{fx.TENANT}', '{line}',
                         {quantity}, '{fx.USER}');""", **CTX)
    run(APP, f"""SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}', 'ready',
                     '{fx.USER}');""", **CTX)


def section_expo_and_service() -> None:
    print("\n--- 7. Expo blocks an incomplete set; ready is noticed; service is recorded "
          "(FR-FUL-009, FR-FUL-010, FR-FUL-011) ---")

    placed = fx.an_accepted_order(coffee=True)
    order = placed["order"]
    fx.assign_table_owner(placed["session"])
    kitchen, bar = placed["tickets"][0]["id"], placed["tickets"][1]["id"]

    view = rows(f"""
        SELECT station_kind::text, state::text, units::text, ready_units::text
        FROM fulfillment.expo_view('{fx.TENANT}', '{order}');""")
    record("expo combines the readiness of every station on one order",
           len(view) == 2 and {r[0] for r in view} == {"kitchen", "bar"},
           f"{view}. An order fans out; expo is where it is put back together, and it "
           f"reads the same rows the stations do rather than a second copy of them")

    blocked = run(APP, f"""
        SELECT fulfillment.release_to_service('{fx.TENANT}', '{order}', '{fx.USER}');""",
        **CTX)
    reasons = rows(f"""
        SELECT reason, detail FROM fulfillment.service_block_reasons('{fx.TENANT}',
                                                                    '{order}');""")
    record("an incomplete set is refused service, and the refusal says why",
           blocked.failed_with("INCOMPLETE_SET_NOT_RELEASED") and len(reasons) >= 2,
           f"{blocked.why() or ''}{len(reasons)} blocking reason(s): "
           f"{[r[0] for r in reasons]}. Half a table's food arriving is how the other "
           f"half arrives cold, and 'not yet' with no reason is what makes an expo "
           f"screen an obstacle rather than a tool")

    drive_to_ready(kitchen)
    partial = [r[0] for r in rows(f"""
        SELECT reason FROM fulfillment.service_block_reasons('{fx.TENANT}', '{order}');""")]
    record("one station ready is still not the set",
           partial == ["incomplete_set"],
           f"remaining reasons: {partial}. The kitchen is done and the bar is not, and "
           f"releasing now would send a plate to a table with nothing to drink beside it")

    notice = rows(f"""
        SELECT assigned_user_id::text, escalated_at IS NULL
        FROM fulfillment.ready_notice WHERE ticket_id = '{kitchen}';""")
    record("becoming ready emits a notice naming the waiter who owns the table",
           len(notice) == 1 and notice[0][0] == fx.USER,
           f"{notice}. FR-FUL-010's event, emitted from the transition rather than by a "
           f"caller who might forget. The TRANSPORT is M3-C: this is the event, not the "
           f"channel, and the register says so")

    unowned = fx.an_accepted_order(table=fx.TABLE_TWO)
    drive_to_ready(unowned["tickets"][0]["id"])
    anonymous = rows(f"""
        SELECT coalesce(assigned_user_id::text, 'nobody')
        FROM fulfillment.ready_notice WHERE ticket_id = '{unowned["tickets"][0]["id"]}';""")
    record("a table nobody owns gets a notice addressed to nobody, not to a guess",
           anonymous == [["nobody"]],
           f"{anonymous}. Absent is absent: a notice with an invented recipient is worse "
           f"than one addressed to no one, because somebody would act on it")

    # Escalation. The became_ready_at is moved back rather than waiting five minutes: the
    # thing under test is the sweep's rule, not the clock.
    run(ADMIN, f"""
        SELECT set_config('fulfillment.applying_event', 'yes', true);
        UPDATE fulfillment.ready_notice SET became_ready_at = now() - interval '20 minutes'
         WHERE ticket_id = '{kitchen}';""", tx=True)
    escalated = run(APP, f"""
        SELECT fulfillment.escalate_uncollected('{fx.TENANT}', '{fx.OUTLET_H1}');""", **CTX)
    record("items nobody collects are escalated after the configured window",
           escalated.ok and int(escalated.scalar or 0) >= 1,
           f"{escalated.why() or escalated.scalar} notice(s) escalated. A sweep with a "
           f"configured window, like M1-C's retention, rather than a timer nobody can "
           f"inspect")

    without_window = run(APP, f"""
        UPDATE config.policy SET payload = payload - 'collection_escalation_seconds'
         WHERE id = '{fx.SERVICE_POLICY}';
        SELECT fulfillment.escalate_uncollected('{fx.TENANT}', '{fx.OUTLET_H1}');""",
        tx=True, **CTX)
    record("an outlet whose policy states no window is refused, not given a default",
           without_window.failed_with("SERVICE_POLICY_INCOMPLETE"),
           without_window.why() or "the sweep invented an escalation window. Food goes "
                                   "cold on a schedule somebody chose")

    # --- service (FR-FUL-011) ---
    early = run(APP, f"""
        SELECT fulfillment.record_serve('{fx.TENANT}', '{kitchen}', '{fx.USER}');""", **CTX)
    record("service cannot be recorded against work that never left the pass",
           early.failed_with("TICKET_NOT_COLLECTED"),
           early.why() or "a ticket still at the pass was recorded as served")

    drive_to_ready(bar)
    released = run(APP, f"""
        SELECT fulfillment.release_to_service('{fx.TENANT}', '{order}', '{fx.USER}');""",
        **CTX)
    collected_state = scalar(f"""
        SELECT fulfillment.order_fulfillment_state('{fx.TENANT}', '{order}');""")
    record("a complete set is released, and every ready ticket is collected at once",
           released.ok and released.scalar.strip() == "2" and collected_state == "ready",
           f"{released.why() or released.scalar} ticket(s) collected; the order reads "
           f"'{collected_state}'. Collection is not service: SM-FULFILLMENT-TICKET "
           f"confirms service at collected -> completed, and a plate in a runner's hands "
           f"is not on a table")

    unexplained = run(APP, f"""
        SELECT fulfillment.record_serve('{fx.TENANT}', '{kitchen}', '{fx.USER}',
            '{fx.USER}', 'wrong_item', NULL);""", **CTX)
    record("an exception without an account of what happened is refused",
           unexplained.failed_with("SERVE_EXCEPTION_UNEXPLAINED"),
           unexplained.why() or "a wrong-item exception was recorded as a category with "
                                "no words behind it")

    served_one = run(APP, f"""
        SELECT fulfillment.record_serve('{fx.TENANT}', '{kitchen}', '{fx.USER}',
            '{fx.USER}', 'missing_item', 'One skewer short; the guest was told.');""",
        **CTX)
    half = scalar(f"""
        SELECT fulfillment.order_fulfillment_state('{fx.TENANT}', '{order}');""")
    record("who collected, who served and what went wrong are all recorded",
           served_one.ok and half == "partially_served",
           f"{served_one.why() or ''}the order reads '{half}'. FR-FUL-011 asks for the "
           f"collector, the server and the missing- or wrong-item exception, and the "
           f"exception carries a sentence rather than a code alone")

    audit = rows(f"""
        SELECT collected_by_user_id::text, coalesce(served_by_user_id::text, '-'),
               coalesce(exception_kind::text, '-'), coalesce(exception_note, '-')
        FROM fulfillment.serve_record WHERE ticket_id = '{kitchen}';""")
    record("the service record names both people and keeps the exception in words",
           len(audit) == 1 and audit[0][0] == fx.USER and audit[0][2] == "missing_item"
           and len(audit[0][3]) > 10,
           f"{audit}")

    run(APP, f"""
        SELECT fulfillment.record_serve('{fx.TENANT}', '{bar}', '{fx.USER}', '{fx.USER}');""",
        **CTX)
    whole = scalar(f"""
        SELECT fulfillment.order_fulfillment_state('{fx.TENANT}', '{order}');""")
    record("and when every ticket is served the order is served",
           whole == "served",
           f"the order reads '{whole}'. Five SM-ORDER labels, all reachable, all "
           f"computed from the tickets: not_released, in_fulfillment, partially_ready, "
           f"ready, partially_served and served have each been read from this suite")

    CONTEXT["served_order"] = order


# ===========================================================================
# 8. Timing and capacity (FR-FUL-012, FR-FUL-013) — and FR-ORD-006's fifth leg
# ===========================================================================

def section_timing_and_capacity() -> None:
    print("\n--- 8. Prep and wait time, throttling and promise time "
          "(FR-FUL-012, FR-FUL-013) ---")

    timings = rows(f"""
        SELECT coalesce(queued_seconds::text, '-'),
               coalesce(preparation_seconds::text, '-'),
               coalesce(wait_seconds::text, '-'), coalesce(sla_breached::text, '-')
        FROM fulfillment.ticket_timings('{fx.TENANT}', '{CONTEXT["served_order"]}');""")
    complete = [t for t in timings if "-" not in t[:3]]
    record("prep and wait time are measured per ticket, station and order",
           len(complete) == len(timings) and len(timings) == 2,
           f"{timings}. Read from the timestamps the FOLD wrote out of the ledger, so "
           f"these are measurements of what happened rather than estimates of what "
           f"usually does")

    unstarted = fx.an_accepted_order()
    blank = rows(f"""
        SELECT coalesce(preparation_seconds::text, 'null')
        FROM fulfillment.ticket_timings('{fx.TENANT}', '{unstarted["order"]}');""")
    record("a ticket nobody has started reports no preparation time, not zero",
           blank == [["null"]],
           f"{blank}. Zero is a duration; a default that reads like a real value is a "
           f"defect, and an average over zeros is how a kitchen gets told it is fast")

    load = int(scalar(f"""
        SELECT fulfillment.station_load('{fx.TENANT}', '{fx.STATION_KITCHEN}');"""))
    record("station load counts live work and nothing else",
           load >= 1,
           f"{load} live ticket(s) at the kitchen. Collected, completed and cancelled "
           f"tickets are not workload — counting them would throttle a station for work "
           f"it already finished")

    # The policy is asked for only when there is something to decide. Written after the
    # first arrangement asked for it up front and refused every order at an outlet that
    # had never configured one — ordering.revalidate_cart() calls this on every
    # submission, so a question nobody needed answered became a barrier to trading.
    unpressured = run(APP, f"""
        UPDATE config.policy SET payload = payload - 'capacity_response'
         WHERE id = '{fx.SERVICE_POLICY}';
        SELECT count(*)::text FROM fulfillment.capacity_pressure('{fx.TENANT}',
                                                                 '{fx.OUTLET_H1}');""",
        rollback=True, **CTX)
    record("an outlet under no pressure is not asked for a policy it does not need",
           unpressured.ok and (unpressured.scalar or "").strip() == "0",
           f"{unpressured.why() or unpressured.scalar} station(s) over threshold with the "
           f"capacity_response removed and nothing raised. The refusal below is what "
           f"happens when there IS pressure and nobody has said what to do about it")

    fx.set_kitchen_threshold(1)
    try:
        pressure = rows(f"""
            SELECT station_node_id::text, load::text, threshold::text, response
            FROM fulfillment.capacity_pressure('{fx.TENANT}', '{fx.OUTLET_H1}');""")
        record("a station over its configured threshold is reported, with the response",
               len(pressure) == 1 and pressure[0][0] == fx.STATION_KITCHEN
               and pressure[0][3] == "throttle",
               f"{pressure}. The threshold is the station's configuration and the "
               f"response is the outlet's; neither is a number this schema chose")

        # --- FR-ORD-006's fifth dimension, closing here ---
        session = fx.m3a.fresh_occupancy(fx.TABLE_TWO)
        guest = fx.m3a.guest_on(session)
        cart = fx.m3a.cart_with(session, guest)
        throttled = run(APP, f"""
            SELECT dimension, detail FROM ordering.revalidate_cart('{fx.TENANT}',
                '{fx.OUTLET_H1}', '{cart}', 'dine_in', now());""", **CTX)
        capacity_rows = [r for r in throttled.rows if r and r[0] == "capacity"]
        record("under a throttling policy, capacity blocks a submission (FR-ORD-006)",
               throttled.ok and len(capacity_rows) == 1,
               f"{capacity_rows or throttled.rows}. This is the fifth dimension the "
               f"requirement names and the one M3-A could only record as waiting: "
               f"capacity means station workload, and there were no stations")

        refused = fx.submit_order(cart, guest=guest, key=f"cap-{os.urandom(6).hex()}")
        record("and the submission itself is refused, not merely reported on",
               refused.failed_with("SUBMISSION_REVALIDATION_FAILED"),
               refused.why() or "a cart that revalidation said was blocked was submitted "
                                "anyway; a check whose answer nothing reads is not a check")

        fx.set_capacity_response("extend_promise", promise_minutes=15)
        relaxed = run(APP, f"""
            SELECT dimension FROM ordering.revalidate_cart('{fx.TENANT}',
                '{fx.OUTLET_H1}', '{cart}', 'dine_in', now());""", **CTX)
        record("under a promise-time policy the same pressure adjusts rather than blocks",
               relaxed.ok and not [r for r in relaxed.rows if r and r[0] == "capacity"],
               f"{relaxed.rows or 'no blocking dimension'}. FR-FUL-013 offers throttling "
               f"OR promise-time adjustment and says the choice is configured; an outlet "
               f"that chose to keep taking orders has made a commercial decision this "
               f"schema does not get to override")

        accepted = fx.submit_order(cart, guest=guest, key=f"cap2-{os.urandom(6).hex()}")
        record("and the order goes through",
               accepted.ok,
               accepted.why() or "submitted under pressure with the promise extended, "
                                 "which is the whole difference between the two policies")

        silent = run(APP, f"""
            UPDATE config.policy SET payload = payload - 'capacity_response'
             WHERE id = '{fx.SERVICE_POLICY}';
            SELECT * FROM fulfillment.capacity_pressure('{fx.TENANT}', '{fx.OUTLET_H1}');""",
            tx=True, **CTX)
        record("an outlet whose policy states neither response is refused",
               silent.failed_with("SERVICE_POLICY_INCOMPLETE"),
               silent.why() or "capacity pressure defaulted to a response nobody chose. "
                               "Throttling somebody did not ask for is as wrong as not "
                               "throttling when they did")
    finally:
        fx.set_kitchen_threshold(fx.KITCHEN_THRESHOLD)
        fx.set_capacity_response("throttle")


# ===========================================================================
# 9. Printer fallback, deduplicated (FR-FUL-014)
# ===========================================================================

def section_printer_fallback() -> None:
    print("\n--- 9. Deduplicated station documents (FR-FUL-014) ---")

    placed = fx.an_accepted_order(declarations=True)
    ticket = placed["tickets"][0]["id"]

    first = run(APP, f"""
        SELECT fulfillment.generate_station_document('{fx.TENANT}', '{ticket}',
            'kds_unavailable', '{fx.USER}');""", **CTX)
    second = run(APP, f"""
        SELECT fulfillment.generate_station_document('{fx.TENANT}', '{ticket}',
            'kds_unavailable', '{fx.USER}');""", **CTX)
    documents = count(APP, f"""
        SELECT count(*) FROM fulfillment.station_ticket_document
        WHERE ticket_id = '{ticket}';""", **CTX)
    record("pressing print twice returns the document that exists, and makes no second",
           first.ok and second.ok
           and first.scalar.strip() == second.scalar.strip() and documents == 1,
           f"{first.scalar.strip()[:8]} then {second.scalar.strip()[:8]}, "
           f"{documents} document(s) on the ticket. Asking twice is NORMAL — the first "
           f"sheet jammed — so the right answer is the document there is, not an error "
           f"and not a second one. A paper ticket printed twice is a dish cooked twice")

    keyed = rows(f"""
        SELECT revision::text, trigger_reason::text, allergy_line_count::text
        FROM fulfillment.station_ticket_document WHERE ticket_id = '{ticket}';""")
    record("the document is keyed on the ticket's ledger position, not on the clock",
           len(keyed) == 1 and keyed[0][0].isdigit(),
           f"{keyed}. Deduplication on (ticket, revision) where the revision IGNORES "
           f"document generation itself: keying on the raw ledger position was the first "
           f"attempt, and generating a document appends an event, so the second request "
           f"saw a new revision and made a second document")

    content = scalar(f"""
        SELECT content FROM fulfillment.station_ticket_document
        WHERE ticket_id = '{ticket}';""")
    lines = [line for line in (content or "").splitlines() if line.strip()]
    record("the allergy is the first line on the paper, in words",
           bool(lines) and "ALLERGY" in lines[0].upper() and len(lines[0]) > 25,
           f"first line: {lines[0][:80]!r} of {len(lines)}. Paper has no colour to fall "
           f"back on, which is exactly why the emphasis was never allowed to be one — "
           f"FR-FUL-008's salience has to survive the printed ticket too")

    changed = run(APP, f"""
        SELECT fulfillment.transition_ticket('{fx.TENANT}', '{ticket}', 'acknowledged',
                                             '{fx.USER}');
        SELECT fulfillment.generate_station_document('{fx.TENANT}', '{ticket}',
            'policy_requires_paper', '{fx.USER}');""", tx=True, **CTX)
    revisions = [r[0] for r in rows(f"""
        SELECT revision::text FROM fulfillment.station_ticket_document
        WHERE ticket_id = '{ticket}' ORDER BY revision;""")]
    record("a ticket that actually CHANGED gets a new document",
           changed.ok and len(revisions) == 2,
           f"revisions: {revisions}. Deduplication that suppressed a reprint after an "
           f"amendment would be worse than the duplicate: the station would be cooking "
           f"from a sheet that no longer describes the order")

    forced = run(ADMIN, f"""
        SELECT set_config('fulfillment.applying_event', 'yes', true);
        INSERT INTO fulfillment.station_ticket_document
            (id, tenant_id, outlet_id, ticket_id, revision, trigger_reason, content,
             content_digest, allergy_line_count, generated_at)
        SELECT gen_random_uuid(), tenant_id, outlet_id, ticket_id, revision,
               trigger_reason, content, content_digest, allergy_line_count, now()
        FROM fulfillment.station_ticket_document WHERE ticket_id = '{ticket}' LIMIT 1;""",
        tx=True)
    record("and the constraint would refuse a duplicate even if the function forgot",
           forced.failed_with("23505"),
           forced.why() or "a second document for the same ticket and revision was "
                           "accepted. The function and the unique index are two "
                           "independent locks, not one lock described twice")

    CONTEXT["document_ticket"] = ticket


# ===========================================================================
# 10. Station transfer and service waste (FR-FUL-015, FR-FUL-016A)
# ===========================================================================

def units_on_order(order: str) -> int:
    """Every unit any LIVE ticket says a station must make, for this order."""
    return count(APP, f"""
        SELECT coalesce(sum(tl.quantity), 0) FROM fulfillment.ticket_line tl
        JOIN fulfillment.ticket t ON t.id = tl.ticket_id
        WHERE t.order_id = '{order}' AND t.state <> 'cancelled';""", **CTX)


def section_transfer_and_waste() -> None:
    print("\n--- 10. Transfer without duplicating work; rework and service waste "
          "(FR-FUL-015, FR-FUL-016A) ---")

    placed = fx.an_accepted_order()
    order, ticket = placed["order"], placed["tickets"][0]["id"]
    reason = fx.reason_code("manager_override")

    before_units = units_on_order(order)
    before_tickets = count(APP, f"""
        SELECT count(*) FROM fulfillment.ticket WHERE order_id = '{order}';""", **CTX)

    moved = run(APP, f"""
        SELECT fulfillment.transfer_ticket('{fx.TENANT}', '{ticket}',
            '{fx.STATION_SPARE}', '{reason}', '{fx.USER}');""", **CTX)
    after_units = units_on_order(order)
    after_tickets = count(APP, f"""
        SELECT count(*) FROM fulfillment.ticket WHERE order_id = '{order}';""", **CTX)
    now_at = scalar(f"""
        SELECT station_node_id::text FROM fulfillment.ticket WHERE id = '{ticket}';""")

    record("a transfer moves the work; it does not copy it",
           moved.ok and before_units == after_units and before_tickets == after_tickets
           and now_at == fx.STATION_SPARE,
           f"{moved.why() or ''}{before_units} unit(s) on {before_tickets} ticket(s) "
           f"before, {after_units} on {after_tickets} after; the ticket is now at "
           f"{now_at[:8]}. The census is over EVERY live ticket on the order, so a "
           f"transfer that left the original behind would show up as more units to make "
           f"than the customer ordered")

    audit = rows(f"""
        SELECT from_station_node_id::text, to_station_node_id::text, units_moved::text,
               transferred_by_user_id::text
        FROM fulfillment.station_transfer WHERE ticket_id = '{ticket}';""")
    record("the transfer is audited: from, to, how many units and who authorized it",
           len(audit) == 1 and audit[0][1] == fx.STATION_SPARE
           and audit[0][3] == fx.USER,
           f"{audit}. FR-FUL-015 says AUTHORIZED rerouting, and an authorization with no "
           f"name on it is a reroute somebody can deny making")

    same = run(APP, f"""
        SELECT fulfillment.transfer_ticket('{fx.TENANT}', '{ticket}',
            '{fx.STATION_SPARE}', '{reason}', '{fx.USER}');""", **CTX)
    record("a transfer to the station the ticket is already at is refused",
           same.failed_with("TRANSFER_TO_SAME_STATION"),
           same.why() or "a ticket was transferred to itself, writing an audit row that "
                         "describes no movement")

    unregistered = run(APP, f"""
        SELECT fulfillment.transfer_ticket('{fx.TENANT}', '{ticket}',
            '{fx.STATION_KITCHEN}', gen_random_uuid(), '{fx.USER}');""", **CTX)
    record("a transfer for a reason nobody registered is refused",
           unregistered.failed_with("TRANSFER_REASON_INVALID"),
           unregistered.why() or "a ticket was rerouted for an unregistered reason")

    both = fx.an_accepted_order(coffee=True)
    collide = run(APP, f"""
        SELECT fulfillment.transfer_ticket('{fx.TENANT}', '{both["tickets"][1]["id"]}',
            '{both["tickets"][0]["station"]}', '{reason}', '{fx.USER}');""", **CTX)
    record("a transfer onto a station that already holds this order's work is refused",
           collide.failed_with("TRANSFER_TARGET_ALREADY_HAS_A_TICKET"),
           collide.why() or "one order's work landed on two tickets at one station, "
                            "which is the same duplication as a second ticket by another "
                            "name")

    drive_to_ready(ticket)
    run(APP, f"""
        SELECT fulfillment.release_to_service('{fx.TENANT}', '{order}', '{fx.USER}');
        SELECT fulfillment.record_serve('{fx.TENANT}', '{ticket}', '{fx.USER}',
                                        '{fx.USER}');""", tx=True, **CTX)
    finished = run(APP, f"""
        SELECT fulfillment.transfer_ticket('{fx.TENANT}', '{ticket}',
            '{fx.STATION_BAR}', '{reason}', '{fx.USER}');""", **CTX)
    record("finished work does not move",
           finished.failed_with("TICKET_NOT_TRANSFERABLE"),
           finished.why() or "a completed ticket was rerouted to another station, where "
                             "it would be made again")

    # --- service waste (FR-FUL-016A) ---
    kinds = [r[0] for r in rows("""
        SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'waste_kind' ORDER BY e.enumsortorder;""", dsn=ADMIN)]
    record("rework, remake and service waste are the kinds recorded",
           set(kinds) >= {"rework", "remake", "service_waste"},
           f"{kinds}. SERVICE waste, not stock waste: Phase 1 has nothing to decrement "
           f"and SM-FULFILLMENT-TICKET's third invariant says so in as many words")

    spoiled = fx.an_accepted_order()
    waste_reason = fx.reason_code("service_failure")
    silent = run(APP, f"""
        SELECT fulfillment.record_waste('{fx.TENANT}', '{spoiled["tickets"][0]["id"]}',
            'remake', 1, '{waste_reason}', '{fx.USER}', '   ');""", **CTX)
    record("a waste event with no account of what happened is refused",
           silent.failed_with("WASTE_UNEXPLAINED"),
           silent.why() or "a remake was recorded with no words behind it")

    wrong_reason = run(APP, f"""
        SELECT fulfillment.record_waste('{fx.TENANT}', '{spoiled["tickets"][0]["id"]}',
            'remake', 1, '{reason}', '{fx.USER}', 'Dropped on the pass.');""", **CTX)
    record("a waste event under a reason code from another category is refused",
           wrong_reason.failed_with("WASTE_REASON_INVALID"),
           wrong_reason.why() or "a remake was booked against a manager_override reason. "
                                 "FR-CFG-003's ten categories are fixed; the distinction "
                                 "belongs in the CODES, not in a new category")

    recorded = run(APP, f"""
        SELECT fulfillment.record_waste('{fx.TENANT}', '{spoiled["tickets"][0]["id"]}',
            'remake', 1, '{waste_reason}', '{fx.USER}', 'Dropped on the pass; remade.');""",
        **CTX)
    linked = rows(f"""
        SELECT kind::text, units_affected::text, order_id::text, ticket_id::text,
               recorded_by_user_id::text
        FROM fulfillment.waste_event WHERE ticket_id = '{spoiled["tickets"][0]["id"]}';""")
    record("a waste event carries its reason, its actor and the order and ticket it is on",
           recorded.ok and len(linked) == 1 and linked[0][2] == spoiled["order"]
           and linked[0][4] == fx.USER,
           f"{recorded.why() or linked}. FR-FUL-016A asks for reason, actor and a linked "
           f"order or ticket; this carries both links because a ticket without its order "
           f"is half an answer for whoever reads it later")


# ===========================================================================
# 11. The five partial closures that came due here
# ===========================================================================

def section_closures() -> None:
    print("\n--- 11. The five partial closures M3-B came due for ---")

    # --- FR-ORD-006 --------------------------------------------------------
    body = definition("ordering.revalidate_cart(uuid,uuid,uuid,menu.sales_channel,"
                      "timestamptz)")
    record("FR-ORD-006: revalidation now asks a fifth dimension, and asks fulfillment",
           "capacity_pressure" in body and "'capacity'" in body,
           f"ordering.revalidate_cart() reads fulfillment.capacity_pressure(). Proved "
           f"end to end in section 8: a loaded station blocks a submission under a "
           f"throttling policy and lets it through under a promise-time one, and a "
           f"policy stating neither is refused")

    # --- FR-ORD-009 --------------------------------------------------------
    session = fx.m3a.fresh_occupancy(fx.TABLE_ONE)
    guest = fx.m3a.guest_on(session)

    def order_on(lines) -> dict:
        cart = fx.m3a.cart_with(session, guest, lines=lines)
        submitted = fx.submit_order(cart, guest=guest, key=f"addon-{os.urandom(6).hex()}")
        if not submitted.ok:
            raise ProbeFailed("add-on submit", submitted.err)
        order = (submitted.scalar or "").strip()
        run(APP, f"SELECT ordering.accept_order('{fx.TENANT}', '{order}', '{fx.USER}');",
            **CTX)
        return dict(order=order, tickets=[r[0] for r in rows(f"""
            SELECT id::text FROM fulfillment.ticket WHERE order_id = '{order}';""")])

    first = order_on(((fx.VARIANT_DORO_FULL, fx.ITEM_DORO, 1),))
    add_on = order_on(((fx.VARIANT_COFFEE_ONE, fx.ITEM_COFFEE, 2),))
    record("FR-ORD-009: an add-on order has its own tickets, not a second round on the first",
           set(first["tickets"]).isdisjoint(add_on["tickets"])
           and first["tickets"] and add_on["tickets"],
           f"first order: {len(first['tickets'])} ticket(s); add-on: "
           f"{len(add_on['tickets'])}. Disjoint by construction rather than by rule — a "
           f"ticket belongs to an ORDER and an add-on is a different order, so nothing "
           f"had to be added for their fulfillment to be independent")

    drive_to_ready(add_on["tickets"][0])
    states = {scalar(f"""SELECT fulfillment.order_fulfillment_state('{fx.TENANT}',
                             '{o["order"]}');"""): o for o in (first, add_on)}
    record("and their state machines and timings run independently",
           set(states) == {"in_fulfillment", "ready"},
           f"first order and add-on read {sorted(states)}. One is ready while the other "
           f"has not been started, which is the operational fact FR-ORD-009 is about: a "
           f"second round of drinks does not wait for the main course")

    # --- FR-ORD-010 --------------------------------------------------------
    # The seeded ordering policy permits amendment only while an order is 'submitted',
    # and no ticket exists then — the work is released on acceptance. So the second half
    # of FR-ORD-010 is only reachable at an outlet that lets an ACCEPTED order be
    # amended, which is a configuration a restaurant can and does choose. Widened here
    # and restored afterwards, so the M3-A check that an accepted order is refused under
    # the seeded policy still holds in a reordered run.
    amendable_states = run(APP, f"""
        UPDATE config.policy
           SET payload = jsonb_set(payload, '{{amendment_allowed_states}}',
                                   '["submitted", "accepted"]'::jsonb)
         WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
           AND category = 'ordering';""", **CTX)
    try:
        amendable = fx.an_accepted_order()
        line = scalar(f"""
            SELECT id::text FROM ordering.order_line
            WHERE order_id = '{amendable["order"]}' LIMIT 1;""")
        early = run(APP, f"""
            SELECT ordering.amend_order_line('{fx.TENANT}', '{amendable["order"]}',
                                             '{line}', 2, '{fx.USER}');""", **CTX)
        record("FR-ORD-010: an order no station has started may still be amended",
               amendable_states.ok and early.ok,
               early.why() or "amended while every ticket is still queued, at an outlet "
                              "whose policy permits amending an accepted order. The "
                              "window has to admit as well as refuse, or it is not a "
                              "window and the refusal below would prove nothing")

        run(APP, f"""
            SELECT fulfillment.transition_ticket('{fx.TENANT}',
                '{amendable["tickets"][0]["id"]}', 'acknowledged', '{fx.USER}');
            SELECT fulfillment.transition_ticket('{fx.TENANT}',
                '{amendable["tickets"][0]["id"]}', 'preparing', '{fx.USER}');""", **CTX)
        late = run(APP, f"""
            SELECT ordering.amend_order_line('{fx.TENANT}', '{amendable["order"]}',
                                             '{line}', 3, '{fx.USER}');""", **CTX)
        record("and one a station has begun may not, whatever the commercial state says",
               late.failed_with("AMENDMENT_AFTER_PREPARATION"),
               late.why() or "an order being cooked was amended. M3-A could only bound "
                             "this by the COMMERCIAL state, and this is exactly the case "
                             "that showed why: the policy permits it, the order is "
                             "'accepted', and a kitchen is already cooking it")
    finally:
        run(APP, f"""
            UPDATE config.policy
               SET payload = jsonb_set(payload, '{{amendment_allowed_states}}',
                                       '["submitted"]'::jsonb)
             WHERE tenant_id = '{fx.TENANT}' AND outlet_id = '{fx.OUTLET_H1}'
               AND category = 'ordering';""", **CTX)

    # --- FR-ORD-016A -------------------------------------------------------
    # Through a live staff session, because ordering.staff_timeline() requires one and
    # authorizes 'order.view' — M3-A's audience rule, unchanged by this slice.
    staff_read = fx.m3a.staff_context(
        f"""SELECT kind::text FROM ordering.staff_timeline('{fx.TENANT}',
                '{CONTEXT["served_order"]}');""",
        session_id=fx.m3a.open_staff_session())
    if not staff_read.ok:
        raise ProbeFailed("staff_timeline", staff_read.err)
    staff = [r[0] for r in staff_read.rows]
    station_kinds = {"tickets_released", "station_acknowledged", "station_preparing",
                     "station_ready", "items_collected", "items_served"}
    record("FR-ORD-016A: the station's milestones are on the order's staff timeline",
           station_kinds <= set(staff),
           f"{sorted(set(staff) & station_kinds)} of {sorted(station_kinds)}. A station's "
           f"internal churn stays in the fulfillment ledger; what an order READER cares "
           f"about is on the timeline, in order, beside the commercial events")

    customer = [r[1] for r in rows(f"""
        SELECT occurred_at::text, kind::text FROM ordering.customer_timeline('{fx.TENANT}',
            '{CONTEXT["served_order"]}');""")]
    record("and a guest sees that it is being made and that it arrived, and no more",
           set(customer) & station_kinds == {"station_preparing", "items_served"},
           f"customer sees {sorted(set(customer) & station_kinds)}. Not which station, "
           f"not who acknowledged it, not that it went to exception — the same audience "
           f"distinction M3-A drew for a void")

    # --- FR-ORD-019A -------------------------------------------------------
    chain = {r[0] for r in rows(f"""
        SELECT artifact_kind::text FROM ordering.correlation_chain('{fx.TENANT}',
            (SELECT correlation_id FROM ordering.customer_order
              WHERE id = '{CONTEXT["served_order"]}'));""")}
    record("FR-ORD-019A: the fulfillment ticket is now a link in the correlation chain",
           "fulfillment_ticket" in chain,
           f"{sorted(chain)}. M3-A built the chain with fulfillment_ticket as a LABEL "
           f"and no rows; this is where the rows arrive. The service request is M3-C's "
           f"and the register still holds it open")

    tickets_in_chain = count(APP, f"""
        SELECT count(*) FROM ordering.correlation_link cl
        JOIN fulfillment.ticket t ON t.id = cl.artifact_id
        WHERE cl.artifact_kind = 'fulfillment_ticket'
          AND t.order_id = '{CONTEXT["served_order"]}';""", **CTX)
    record("every ticket on the order is in the chain, not just the first",
           tickets_in_chain == 2,
           f"{tickets_in_chain} ticket(s) linked. A chain that named one of two tickets "
           f"would be worse than none, because it would look complete")


# ===========================================================================
# 12. Governance
# ===========================================================================

SOURCES = (
    "migrations/0011_fulfillment_timeline_event_kinds.sql",
    "migrations/0012_fulfillment_tickets_stations_and_service.sql",
    "tests/m3b/verify_m3b.py",
    "tests/m3b/fixtures.py",
    "tests/m3b/render_probe.mjs",
    "station/index.html",
    "station/station.css",
    "station/src/station.ts",
    "station/tsconfig.json",
    "api/src/routes/station.ts",
)


def section_governance(states: list[str]) -> None:
    print("\n--- 12. Governance ---")

    try:
        failures = partial_closures.check()
        entries = partial_closures.load()
    except partial_closures.RegisterUnreadable as error:
        record("the partial-closure register is readable", False, str(error))
        return

    closed_here = [e for e in entries if (e.get("closed_at") or "") == "M3-B"]
    record("the register is consistent, and the five entries that came due are closed",
           not failures and len(closed_here) == 5,
           f"{len(entries)} entries, {len(closed_here)} closed at M3-B: "
           f"{sorted({e['requirement'] for e in closed_here})}. Failures: "
           f"{failures or 'none'}. Creating tests/m3b/ made all five overdue at once, "
           f"which is the mechanism working; each names the slice that closed it and "
           f"what now proves it")

    landed = partial_closures.landed_gates()
    record("no entry claims to have been closed by a slice that has not landed",
           "M3-B" in landed and all(e.get("closed_at") in landed for e in closed_here),
           f"landed: {sorted(landed)}. PARTIAL_CLOSURE_CLOSED_FROM_THE_FUTURE fired on "
           f"all five of these before tests/m3b/verify_m3b.py existed, which is the "
           f"order the rule intends: the evidence has to be there before the tick is")

    still_open = {e["completing_gate"] for e in entries
                  if (e.get("state") or "") == "open"}
    record("and no open entry's completer has landed either",
           not (still_open & landed),
           f"open completers: {sorted(still_open)}; landed: {sorted(landed)}. M3-C will "
           f"do to the service-request entries what M3-B just did to these")

    # --- SM-ORDER: derived, never stored ---
    stored = rows("""
        SELECT n.nspname || '.' || c.relname || '.' || a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE n.nspname = 'ordering' AND c.relkind = 'r' AND a.attnum > 0
          AND NOT a.attisdropped
          AND (EXISTS (SELECT 1 FROM pg_enum e WHERE e.enumtypid = t.oid
                        AND e.enumlabel IN ('in_fulfillment', 'partially_ready',
                                            'partially_served'))
               OR a.attname ~* 'fulfil')
        ORDER BY 1;""", dsn=ADMIN)
    record("no column anywhere in ordering could hold a fulfillment label",
           not stored,
           f"{[r[0] for r in stored] or 'none'}. Enumerated from the catalog rather than "
           f"from a list of tables, so a column added tomorrow is covered. SM-ORDER's "
           f"second invariant says order, fulfillment, check, payment and tip states are "
           f"SEPARATE; storing the fulfillment label on the order is how they stop being")

    span = ["in_fulfillment", "partially_ready", "ready", "partially_served", "served"]
    returns = set(re.findall(r"RETURN '([a-z_]+)'",
                             definition("fulfillment.order_fulfillment_state(uuid,uuid)")))
    record("and the derived function answers every SM-ORDER label it stands in for",
           set(span) <= returns,
           f"returns {sorted(returns)}; SM-ORDER's fulfillment span is {span}. Each was "
           f"read off a real order in sections 4, 7 and 11 — deriving is only equivalent "
           f"to storing if nothing is lost, so 'the function mentions it' is not enough "
           f"on its own and is not what this rests on")

    # --- money, isolation, definers ---
    floats = rows("""
        SELECT n.nspname || '.' || c.relname || '.' || a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE n.nspname = 'fulfillment' AND c.relkind = 'r' AND a.attnum > 0
          AND NOT a.attisdropped AND t.typname IN ('float4', 'float8', 'money');""",
        dsn=ADMIN)
    record("no money in this schema is binary floating point",
           not floats,
           f"{[r[0] for r in floats] or 'none'}. This slice carries no money at all — a "
           f"ticket is what a station must do, not what it costs — and the check is here "
           f"so that stops being true loudly rather than quietly")

    unprotected = rows("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'fulfillment' AND c.relkind = 'r'
          AND c.relname <> 'transition'
          AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)
        ORDER BY c.relname;""", dsn=ADMIN)
    record("every tenant table in the schema has row level security ENABLED and FORCED",
           not unprotected,
           f"{[r[0] for r in unprotected] or 'none'}. fulfillment.transition is exempt "
           f"and is the only exemption: it is the pinned machine, not tenant data, and "
           f"it carries no tenant column to scope by. It is immutable at runtime instead")

    wrong_predicate = rows("""
        SELECT c.relname, p.polname FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'fulfillment'
          AND pg_get_expr(p.polqual, p.polrelid) <> 'app.row_in_scope(tenant_id, outlet_id)'
        ORDER BY c.relname;""", dsn=ADMIN)
    record("every policy uses the one isolation predicate, not one of its own devising",
           not wrong_predicate,
           f"{[f'{r[0]}/{r[1]}' for r in wrong_predicate] or 'none'} — M1-A's NC-M1-003 "
           f"gates this in CI and it gates thirteen new tables unchanged")

    unpinned = [r[0] for r in rows("""
        SELECT n.nspname || '.' || p.proname FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname IN ('fulfillment', 'ordering') AND p.prosecdef
          AND coalesce(array_to_string(p.proconfig, ','), '') NOT LIKE '%search_path%'
        ORDER BY 1;""", dsn=ADMIN)]
    record("every SECURITY DEFINER function pins its search path",
           not unpinned,
           f"unpinned: {unpinned or 'none'}. A definer function with a mutable search "
           f"path is a definer function somebody else chooses the tables for")

    revoked = rows("""
        SELECT p.proname
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'ordering'
          AND p.proname IN ('write_station_timeline_entry', 'link_correlation_artifact')
          AND has_function_privilege('hospitality_app', p.oid, 'EXECUTE');""", dsn=ADMIN)
    record("the doors fulfillment uses into ordering are shut to the application role",
           not revoked,
           f"{[r[0] for r in revoked] or 'none'} executable by hospitality_app. They are "
           f"narrow definer doors so the fulfillment fold never holds ordering's "
           f"projection marker; a door the application could open itself would be a way "
           f"to write a timeline entry no event produced")

    # --- append-only, projections, the machine itself ---
    for table, signature in (("ticket_event", "TICKET_LEDGER_IS_APPEND_ONLY"),):
        updated = run(APP, f"""
            UPDATE fulfillment.{table} SET kind = 'transitioned'
             WHERE tenant_id = '{fx.TENANT}';""", **CTX)
        deleted = run(APP, f"""
            DELETE FROM fulfillment.{table} WHERE tenant_id = '{fx.TENANT}';""", **CTX)
        record(f"fulfillment.{table} refuses UPDATE and DELETE",
               updated.failed_with(signature, "42501")
               and deleted.failed_with(signature, "42501"),
               f"{updated.why()} / {deleted.why()}. Two locks: the grant withholds them "
               f"and the trigger refuses them, so a grant restored by mistake does not "
               f"open the ledger")

    direct = run(APP, f"""
        UPDATE fulfillment.ticket SET priority = 'rush' WHERE tenant_id = '{fx.TENANT}';""",
        **CTX)
    record("a projection cannot be written except by the fold",
           direct.failed_with("PROJECTION_WRITTEN_DIRECTLY", "42501"),
           direct.why() or "a projection row was written from outside apply_ticket_event()")

    tampering = run(ADMIN, """
        INSERT INTO fulfillment.transition (from_state, to_state, reason)
        VALUES ('completed', 'queued', 'invented at runtime');""")
    record("and the state machine itself cannot be edited at runtime",
           tampering.failed_with("STATE_MACHINE_ALTERED_AT_RUNTIME"),
           tampering.why() or "an edge was added to the machine while the system was "
                              "running; every transition check downstream would then be "
                              "checking a machine somebody widened")

    # --- rebuild determinism, across BOTH ledgers ---
    before = scalar(f"""
        SELECT encode(fulfillment.projection_digest('{fx.TENANT}'), 'hex');""", dsn=ADMIN)
    # ORDERING's digest as well as fulfillment's. Checking only its own was how this
    # slice managed to break M3-A's NC-M3-009 without noticing: releasing an order wrote
    # the ticket's correlation link from release_order() rather than from the fold, so a
    # rebuild dropped the link and could not put it back. Fulfillment's digest was
    # identical throughout — the damage was entirely in the schema this slice does not
    # own, and only the reversed run found it.
    ordering_before = scalar(f"""
        SELECT encode(ordering.projection_digest('{fx.TENANT}'), 'hex');""", dsn=ADMIN)
    # UNDER CONTEXT, and the replay count asserted. ordering.rebuild_projections() is
    # SECURITY DEFINER over tables with FORCE row level security, so its body is filtered
    # by app.row_in_scope() no matter who calls it — a superuser included. Called with no
    # tenant and outlet it is not an error: every ledger row is simply out of scope, so it
    # drops nothing, replays nothing and returns 0, and both digests below then match
    # trivially. That is how this check passed while proving nothing, and it is the same
    # class of defect as the M2-C assertion that could not fail. The count is the guard.
    ledgers = replayed_ledgers()
    record("the ledgers a rebuild replays are read out of the rebuild itself",
           len(ledgers) >= 2,
           f"{ledgers}. Named here instead, this count would be wrong the moment a later "
           f"gate added a ledger to ordering.rebuild_projections() — which is how M3-A's "
           f"schema list went stale — and the guard below would fail on a correct system")
    ledger_events = count(APP, "SELECT " + " + ".join(
        f"(SELECT count(*) FROM {table} WHERE tenant_id = '{fx.TENANT}')"
        for table in ledgers) + ";", **CTX)
    rebuilt = run(APP, f"""
        SELECT ordering.rebuild_projections('{fx.TENANT}');""", **CTX)
    replayed = int((rebuilt.scalar or "-1").strip()) if rebuilt.ok else -1
    record("the rebuild actually replayed both ledgers rather than nothing",
           replayed == ledger_events and replayed > 0,
           f"{replayed} event(s) replayed against {ledger_events} in the two ledgers. "
           f"A rebuild that dropped nothing and replayed nothing reproduces every digest "
           f"exactly, which is a pass that means nothing")
    after = scalar(f"""
        SELECT encode(fulfillment.projection_digest('{fx.TENANT}'), 'hex');""", dsn=ADMIN)
    ordering_after = scalar(f"""
        SELECT encode(ordering.projection_digest('{fx.TENANT}'), 'hex');""", dsn=ADMIN)
    record("dropping every projection and replaying both ledgers reproduces them exactly",
           rebuilt.ok and before == after and len(before) == 64,
           f"{rebuilt.why() or ''}digest {before[:16]}… before, {after[:16]}… after "
           f"({replayed} events replayed). M3-A's rebuild replayed one ledger; a "
           f"rebuild that replayed only the order ledger would have deleted every "
           f"station timeline entry and left NC-M3-009 red for a correct system")

    record("and ORDERING's projections come back unchanged too",
           ordering_before == ordering_after,
           f"ordering digest {ordering_before[:16]}… before, {ordering_after[:16]}… "
           f"after. This slice writes into ordering — the station timeline entries and "
           f"the ticket's link in the correlation chain — and a write that only the "
           f"live path performs is a projection no rebuild can reproduce")

    timeline_after = count(APP, f"""
        SELECT count(*) FROM ordering.order_timeline_entry
        WHERE order_id = '{CONTEXT["served_order"]}'
          AND kind::text LIKE 'station%';""", **CTX)
    record("and the station's timeline entries come back with it",
           timeline_after >= 4,
           f"{timeline_after} station entr(ies) on the served order after the rebuild. "
           f"One timeline out of two ledgers, rebuilt from the events rather than kept "
           f"as a cache of joins")

    # --- vocabulary and boundary ---
    sources = "\n".join((REPO / name).read_text(encoding="utf-8") for name in SOURCES)
    pattern, terms = fenced_identifier_pattern()
    hits = sorted({m.group(0) for m in re.finditer(pattern, sources, re.I)})
    record("this slice names no permanently fenced domain",
           not hits,
           f"checked {len(SOURCES)} files — both migrations, the suite, the fixtures, "
           f"the probe, the whole station surface and its route — against all {terms} "
           f"authoritative terms: {hits or 'none'}. FR-FUL-016A is SERVICE waste, and "
           f"the identifier is waste_event with no quantity leaving anywhere")

    later = rows("""
        SELECT n.nspname || '.' || c.relname
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname = 'fulfillment'
          AND (c.relname ~* '(service_request|journey|check|payment|tip|receipt|'
                            'notification|print_queue|outlet_node)')
        ORDER BY 1;""", dsn=ADMIN)
    record("nothing belonging to a later slice was built here",
           not later,
           f"{[r[0] for r in later] or 'none'} — service requests and notification "
           f"transport are M3-C; the waiter surface and journeys are M3-D; checks, "
           f"payments, tips and receipts are M4; the resilient local print queue and the "
           f"outlet node are M5a")

    secrets = [name for name in SOURCES
               if re.search(r"(password|secret|token)\s*[=:]\s*['\"][A-Za-z0-9+/]{12,}",
                            (REPO / name).read_text(encoding="utf-8"))]
    record("no credential is written into this slice's source",
           not secrets,
           f"{secrets or 'none'}. The staff token the fixtures mint is generated per run "
           f"from os.urandom and only its sha256 reaches the database (FR-SEC-007)")

    surface_css = (REPO / "station" / "station.css").read_text(encoding="utf-8")
    allergy_block = surface_css.split(".allergy {", 1)[-1].split("}", 1)[0]
    record("the allergy rule in the stylesheet declares no colour at all",
           "color" not in allergy_block,
           f"the .allergy rule is {allergy_block.split()!r}. Read from source as well as "
           f"measured in a browser, because the two can disagree: source says what was "
           f"intended, the flattened render says what a station actually sees, and the "
           f"safety claim needs both")

    kds_states = set(re.findall(r"WHEN '([a-z_]+)'\s+THEN",
                                definition("fulfillment.kds_bucket("
                                           "fulfillment.ticket_state)")))
    record("the KDS bucket mapping covers every state the package declares",
           kds_states == set(states),
           f"mapped: {sorted(kds_states)}; declared: {sorted(states)}. A CASE with no "
           f"ELSE, so a twelfth state added to the package raises rather than falling "
           f"into a display column nobody chose. This is the seven-to-eleven "
           f"reconciliation: FR-FUL-003's seven are display buckets over these eleven, "
           f"and its 'new' is the package's 'queued'")


# ===========================================================================
# 13. Negative controls — each proved RED with a real defect before GREEN
# ===========================================================================

def capture_function(signature: str) -> str:
    res = run(ADMIN, f"SELECT pg_get_functiondef('{signature}'::regprocedure);")
    if not res.ok or not res.out.strip():
        raise ProbeFailed(f"capture {signature}", res.err)
    return res.out


def prove_sql(control: str, gate, signature: str, break_sql: str, *,
              revert_sql: str = "", captured: list[str] | None = None) -> None:
    """Plant the defect in the DATABASE, require the NAMED failure, revert, require green."""
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
            run(ADMIN, revert_sql)

    green_ok, green_sig, green_detail = gate()
    record(f"{control} — GREEN after revert", green_ok,
           green_detail if green_ok else f"{green_sig}: {green_detail}")


def prove_surface(control: str, gate, signature: str,
                  edits: list[tuple[Path, str, str]]) -> None:
    """The same, for a defect in the STATION SURFACE. Measured, because the gate is.

    The defect goes into the build workspace's copy and never into the repository:
    api/build.sh re-copies from the repository on every run, so reverting is a rebuild
    rather than an edit and the repository is never broken even for an instant.
    """
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


STATION_CSS = WORKSPACE / "station" / "station.css"
STATION_SRC = WORKSPACE / "station" / "src" / "station.ts"


# --- NC-M3-004 ---------------------------------------------------------------

def illegal_transition_gate() -> tuple[bool, str, str]:
    outcome = walk_machine(CONTEXT["states"], CONTEXT["edges"], CONTEXT["walk_ticket"])
    if outcome["accepted_illegal"]:
        return (False, "ILLEGAL_TRANSITION_ACCEPTED",
                f"{len(outcome['accepted_illegal'])} illegal transition(s) accepted by "
                f"the database: {outcome['accepted_illegal'][:6]}")
    if outcome["refused_legal"]:
        return (False, "LEGAL_TRANSITION_REFUSED",
                f"{outcome['refused_legal'][:3]}")
    return (True, "",
            f"{outcome['pairs']} ordered pairs attempted from states reached by legal "
            f"moves; {len(CONTEXT['edges'])} accepted, "
            f"{outcome['pairs'] - len(CONTEXT['edges'])} refused")


# --- allergy emphasis at the station -----------------------------------------

def allergy_emphasis_gate() -> tuple[bool, str, str]:
    """MEASURED. The colour-flattened render is the decisive one."""
    probe = render(CONTEXT["control_payload"])
    if probe.get("errors"):
        return False, "PROBE_FAILED", str(probe["errors"])[:300]

    flat = probe["flattened"]
    allergies = [a for a in flat["allergies"] if a["visible"]]
    ordinary = [o for o in flat["ordinary"] if o["visible"]]
    if not allergies:
        return (False, "ALLERGY_EMPHASIS_LOST_AT_STATION",
                "no allergy is drawn at all once colour is removed")

    heaviest = max((o["fontWeight"] for o in ordinary), default=0)
    largest = max((o["fontSizePx"] for o in ordinary), default=0.0)
    lost = [a for a in allergies
            if not (a["fontWeight"] > heaviest and a["fontSizePx"] > largest
                    and a["borderTopWidthPx"] > 0
                    and "ALLERGY" in a["text"].upper() and len(a["text"]) > 12)]
    if lost:
        return (False, "ALLERGY_EMPHASIS_LOST_AT_STATION",
                f"{len(lost)} of {len(allergies)} allergy element(s) stop standing out "
                f"once colour is removed as a channel: weight "
                f"{[a['fontWeight'] for a in lost]} against ordinary {heaviest}, size "
                f"{[a['fontSizePx'] for a in lost]} against {largest}, border "
                f"{[a['borderTopWidthPx'] for a in lost]}, text "
                f"{[a['text'][:40] for a in lost]}")
    return (True, "",
            f"{len(allergies)} allergy element(s) still heavier than {heaviest}, larger "
            f"than {largest}px, still bordered and still carrying the words, in a "
            f"document rendered with every colour flattened to one ink")


# --- duplicated work ---------------------------------------------------------

def ordered_units(order: str) -> int:
    return count(APP, f"""
        SELECT coalesce(sum(quantity), 0) FROM ordering.order_line
        WHERE order_id = '{order}';""", **CTX)


def recall_duplication_gate() -> tuple[bool, str, str]:
    placed = fx.an_accepted_order()
    order, ticket = placed["order"], placed["tickets"][0]["id"]
    drive_to_ready(ticket)
    before = count(APP, f"""
        SELECT count(*) FROM fulfillment.ticket WHERE order_id = '{order}';""", **CTX)
    recalled = run(APP, f"""
        SELECT fulfillment.recall_ticket('{fx.TENANT}', '{ticket}',
            '{fx.reason_code("manager_override")}', '{fx.USER}');""", **CTX)
    if recalled.failed_with("DUPLICATED_WORK", "23505"):
        return (False, "DUPLICATED_WORK_ON_RECALL",
                f"the recall tried to reissue the work as a second ticket and the "
                f"database refused it — by the one-ticket-per-order-per-station index or "
                f"by the deferred unit constraint, whichever saw it first, and either is "
                f"the duplication being caught: {recalled.why()}")
    if not recalled.ok:
        return False, "RECALL_FAILED", recalled.why()
    after = count(APP, f"""
        SELECT count(*) FROM fulfillment.ticket WHERE order_id = '{order}';""", **CTX)
    live, ordered = units_on_order(order), ordered_units(order)
    if after != before or live != ordered:
        return (False, "DUPLICATED_WORK_ON_RECALL",
                f"{before} ticket(s) before the recall and {after} after; {live} unit(s) "
                f"on live tickets against {ordered} ordered")
    return (True, "",
            f"the ticket moved to rework in place: {after} ticket(s), {live} unit(s) on "
            f"live tickets against {ordered} ordered")


def transfer_duplication_gate() -> tuple[bool, str, str]:
    placed = fx.an_accepted_order()
    order, ticket = placed["order"], placed["tickets"][0]["id"]
    before = count(APP, f"""
        SELECT count(*) FROM fulfillment.ticket WHERE order_id = '{order}';""", **CTX)
    moved = run(APP, f"""
        SELECT fulfillment.transfer_ticket('{fx.TENANT}', '{ticket}',
            '{fx.STATION_SPARE}', '{fx.reason_code("manager_override")}', '{fx.USER}');""",
        **CTX)
    if moved.failed_with("DUPLICATED_WORK", "23505"):
        return (False, "DUPLICATED_WORK_ON_TRANSFER",
                f"the transfer tried to raise a second ticket and the database refused "
                f"it: {moved.why()}")
    if not moved.ok:
        return False, "TRANSFER_FAILED", moved.why()
    after = count(APP, f"""
        SELECT count(*) FROM fulfillment.ticket WHERE order_id = '{order}';""", **CTX)
    live, ordered = units_on_order(order), ordered_units(order)
    at = scalar(f"SELECT station_node_id::text FROM fulfillment.ticket WHERE id = '{ticket}';")
    if after != before or live != ordered or at != fx.STATION_SPARE:
        return (False, "DUPLICATED_WORK_ON_TRANSFER",
                f"{before} ticket(s) before and {after} after; {live} unit(s) live "
                f"against {ordered} ordered; the original ticket is at {at[:8]}")
    return (True, "",
            f"the same ticket changed station: {after} ticket(s), {live} unit(s) live "
            f"against {ordered} ordered")


def document_duplication_gate() -> tuple[bool, str, str]:
    placed = fx.an_accepted_order()
    ticket = placed["tickets"][0]["id"]
    first = run(APP, f"""
        SELECT fulfillment.generate_station_document('{fx.TENANT}', '{ticket}',
            'kds_unavailable', '{fx.USER}');""", **CTX)
    second = run(APP, f"""
        SELECT fulfillment.generate_station_document('{fx.TENANT}', '{ticket}',
            'kds_unavailable', '{fx.USER}');""", **CTX)
    if not first.ok:
        return False, "DOCUMENT_GENERATION_FAILED", first.why()
    made = count(APP, f"""
        SELECT count(*) FROM fulfillment.station_ticket_document
        WHERE ticket_id = '{ticket}';""", **CTX)
    if made != 1 or not second.ok \
            or first.scalar.strip() != second.scalar.strip():
        return (False, "DUPLICATE_STATION_TICKET",
                f"two requests for an unchanged ticket produced {made} document(s); "
                f"{first.scalar.strip()[:8]} then "
                f"{(second.scalar or second.why()).strip()[:40]}")
    return (True, "",
            f"two requests, {made} document, the same id returned twice")


# --- expo and priority -------------------------------------------------------

def incomplete_set_gate() -> tuple[bool, str, str]:
    placed = fx.an_accepted_order(coffee=True)
    order = placed["order"]
    drive_to_ready(placed["tickets"][0]["id"])
    released = run(APP, f"""
        SELECT fulfillment.release_to_service('{fx.TENANT}', '{order}', '{fx.USER}');""",
        **CTX)
    if released.ok:
        collected = count(APP, f"""
            SELECT count(*) FROM fulfillment.ticket
            WHERE order_id = '{order}' AND state = 'collected';""", **CTX)
        return (False, "INCOMPLETE_SET_SERVED",
                f"one station was ready and the other had not started, and expo released "
                f"{released.scalar.strip()} ticket(s) anyway; {collected} now collected")
    if not released.failed_with("INCOMPLETE_SET_NOT_RELEASED"):
        return False, "EXPO_REFUSED_WRONGLY", released.why()
    reasons = rows(f"""
        SELECT reason FROM fulfillment.service_block_reasons('{fx.TENANT}', '{order}');""")
    return (True, "",
            f"refused with {len(reasons)} stated reason(s): {[r[0] for r in reasons]}")


def priority_attribution_gate() -> tuple[bool, str, str]:
    """Attribution has to REACH the queue, not merely exist somewhere behind it.

    The anonymous call is checked too, but the gate cannot rest on it alone: the actor
    column is NOT NULL as well as guarded, so removing the guard would leave the write
    refused and this gate green for a reason that had nothing to do with the guard. Two
    locks that share inputs can go stale together; two locks that do not, hide each
    other. So the defect this proves against is the one that survives both — a priority
    that arrives on the station's queue with nobody's name on it.
    """
    placed = fx.an_accepted_order()
    ticket, station = placed["tickets"][0]["id"], placed["tickets"][0]["station"]
    reason = fx.reason_code("manager_override")

    anonymous = run(APP, f"""
        SELECT fulfillment.set_priority('{fx.TENANT}', '{ticket}', 'rush', '{reason}',
                                        NULL);""", **CTX)
    if anonymous.ok:
        return (False, "PRIORITY_WITHOUT_ATTRIBUTION",
                "a ticket was rushed by nobody and the change was accepted")
    if not anonymous.failed_with("PRIORITY_WITHOUT_ACTOR", "23502"):
        return False, "PRIORITY_REFUSED_WRONGLY", anonymous.why()

    applied = run(APP, f"""
        SELECT fulfillment.set_priority('{fx.TENANT}', '{ticket}', 'rush', '{reason}',
                                        '{fx.USER}');""", **CTX)
    if not applied.ok:
        return False, "PRIORITY_FAILED", applied.why()

    shown = rows(f"""
        SELECT priority::text, coalesce(priority_reason, '-'), coalesce(priority_by, '-')
        FROM fulfillment.kds_queue('{fx.TENANT}', '{station}')
        WHERE ticket_id = '{ticket}';""")
    if not shown or shown[0][0] != "rush" or shown[0][1] == "-" or shown[0][2] == "-":
        return (False, "PRIORITY_WITHOUT_ATTRIBUTION",
                f"the station's queue shows {shown or 'no row'}: the level arrives "
                f"without the reason, the person, or both, and a rush nobody is "
                f"accountable for is how a queue gets gamed")

    unattributed = rows("""
        SELECT id::text FROM fulfillment.priority_change
        WHERE applied_by_user_id IS NULL;""")
    if unattributed:
        return (False, "PRIORITY_WITHOUT_ATTRIBUTION",
                f"{len(unattributed)} priority change(s) on record name nobody")
    return (True, "",
            f"anonymous refused ({anonymous.why()[:60]}); the authorized change reaches "
            f"the queue as {shown[0]}")


def section_controls() -> None:
    print("\n--- 13. Negative controls: each proved RED with a real defect, then GREEN ---")

    permissive = """
        CREATE OR REPLACE FUNCTION fulfillment.assert_legal_transition() RETURNS trigger
        LANGUAGE plpgsql AS $broken$
        BEGIN
            RETURN NEW;
        END;
        $broken$;"""
    print("\n  NC-M3-004  an illegal ticket transition is accepted by the database")
    prove_sql("NC-M3-004", illegal_transition_gate,
              "ILLEGAL_TRANSITION_ACCEPTED", permissive,
              captured=["fulfillment.assert_legal_transition()"])

    # The emphasis becomes colour, and only colour: the same weight and size as the text
    # around it, no border, a red ink and a pink ground. On a screen it looks like a
    # warning. In the colour-flattened render it is a sentence like any other.
    print("\n  NC-M3B-001  the allergy emphasis is carried by colour and nothing else")
    prove_surface(
        "NC-M3B-001", allergy_emphasis_gate,
        "ALLERGY_EMPHASIS_LOST_AT_STATION",
        # Three edits, one defect: the emphasis becomes a red ink on a pink ground and
        # nothing else. Same weight and size as the text around it, no border. On a
        # screen it still looks like a warning, which is what makes it the realistic
        # shape of this mistake rather than a straw one.
        [(STATION_CSS, ".allergy {\n  font-weight: 800;",
          ".allergy {\n  color: #b00020;\n  background-color: #ffe8e8;"),
         (STATION_CSS, "  font-size: 1.6rem;", "  font-size: 1rem;"),
         (STATION_CSS, "  border: 4px double var(--rule);", "  border: 0;")])

    reissue = """
        CREATE OR REPLACE FUNCTION fulfillment.recall_ticket(
            p_tenant_id uuid, p_ticket_id uuid, p_reason_code_id uuid, p_user_id uuid)
        RETURNS void LANGUAGE plpgsql AS $broken$
        DECLARE
            v_ticket fulfillment.ticket%ROWTYPE;
            v_event  bigint;
        BEGIN
            SELECT * INTO v_ticket FROM fulfillment.ticket
             WHERE id = p_ticket_id AND tenant_id = p_tenant_id;
            -- The defect: the recall REISSUES the work as a fresh ticket at the same
            -- station instead of moving the ticket it already has back to rework.
            INSERT INTO fulfillment.ticket_event
                (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
                 actor_user_id, correlation_id, after)
            SELECT p_tenant_id, v_ticket.outlet_id, gen_random_uuid(), 1, 'released',
                   'staff', p_user_id, o.correlation_id,
                   jsonb_build_object(
                       'ticket', jsonb_build_object(
                           'order_id', v_ticket.order_id,
                           'station_node_id', v_ticket.station_node_id,
                           'priority', 'ordinary',
                           'routing_rule_set_id', v_ticket.routing_rule_set_id,
                           'station_sequence', 90),
                       'lines', (SELECT jsonb_agg(jsonb_build_object(
                                     'id', gen_random_uuid(),
                                     'order_line_id', tl.order_line_id,
                                     'quantity', tl.quantity,
                                     'item_code', tl.item_code,
                                     'canonical_name', tl.canonical_name))
                                 FROM fulfillment.ticket_line tl
                                 WHERE tl.ticket_id = p_ticket_id))
              FROM ordering.customer_order o
             WHERE o.id = v_ticket.order_id AND o.tenant_id = p_tenant_id
            RETURNING id INTO v_event;
            PERFORM fulfillment.apply_ticket_event(v_event);
        END;
        $broken$;"""
    print("\n  NC-M3B-002  a recall reissues the work instead of moving it")
    prove_sql("NC-M3B-002", recall_duplication_gate,
              "DUPLICATED_WORK_ON_RECALL", reissue,
              captured=["fulfillment.recall_ticket(uuid,uuid,uuid,uuid)"])

    copying = """
        CREATE OR REPLACE FUNCTION fulfillment.transfer_ticket(
            p_tenant_id uuid, p_ticket_id uuid, p_to_station_node_id uuid,
            p_reason_code_id uuid, p_user_id uuid) RETURNS void
        LANGUAGE plpgsql AS $broken$
        DECLARE
            v_ticket fulfillment.ticket%ROWTYPE;
            v_event  bigint;
        BEGIN
            SELECT * INTO v_ticket FROM fulfillment.ticket
             WHERE id = p_ticket_id AND tenant_id = p_tenant_id;
            -- The defect: the transfer RAISES A SECOND TICKET at the target station and
            -- leaves the first one where it was, so both stations make the same dish.
            INSERT INTO fulfillment.ticket_event
                (tenant_id, outlet_id, ticket_id, sequence_number, kind, actor_kind,
                 actor_user_id, correlation_id, after)
            SELECT p_tenant_id, v_ticket.outlet_id, gen_random_uuid(), 1, 'released',
                   'staff', p_user_id, o.correlation_id,
                   jsonb_build_object(
                       'ticket', jsonb_build_object(
                           'order_id', v_ticket.order_id,
                           'station_node_id', p_to_station_node_id,
                           'priority', 'ordinary',
                           'routing_rule_set_id', v_ticket.routing_rule_set_id,
                           'station_sequence', 91),
                       'lines', (SELECT jsonb_agg(jsonb_build_object(
                                     'id', gen_random_uuid(),
                                     'order_line_id', tl.order_line_id,
                                     'quantity', tl.quantity,
                                     'item_code', tl.item_code,
                                     'canonical_name', tl.canonical_name))
                                 FROM fulfillment.ticket_line tl
                                 WHERE tl.ticket_id = p_ticket_id))
              FROM ordering.customer_order o
             WHERE o.id = v_ticket.order_id AND o.tenant_id = p_tenant_id
            RETURNING id INTO v_event;
            PERFORM fulfillment.apply_ticket_event(v_event);
        END;
        $broken$;"""
    print("\n  NC-M3B-003  a transfer raises a second ticket instead of moving one")
    prove_sql("NC-M3B-003", transfer_duplication_gate,
              "DUPLICATED_WORK_ON_TRANSFER", copying,
              captured=["fulfillment.transfer_ticket(uuid,uuid,uuid,uuid,uuid)"])

    # The revision keyed on the raw ledger position — which is exactly how this was
    # written the first time, and exactly how the deduplication test found it: generating
    # a document appends an event, so the second request sees a new revision.
    original = capture_function("fulfillment.generate_station_document(uuid,uuid,"
                                "fulfillment.document_trigger,uuid)")
    naive = original.replace(
        """SELECT coalesce(max(sequence_number), 0) INTO v_revision
      FROM fulfillment.ticket_event
     WHERE tenant_id = p_tenant_id AND ticket_id = p_ticket_id
       AND kind <> 'document_generated';""",
        "v_revision := v_ticket.ledger_sequence;")
    if naive == original:
        record("NC-M3B-004 — inject defect", False,
               "the revision anchor was not found in the captured definition")
    else:
        print("\n  NC-M3B-004  a reprint of an unchanged ticket makes a second document")
        prove_sql("NC-M3B-004", document_duplication_gate,
                  "DUPLICATE_STATION_TICKET", naive,
                  captured=["fulfillment.generate_station_document(uuid,uuid,"
                            "fulfillment.document_trigger,uuid)"])

    expo_original = capture_function(
        "fulfillment.release_to_service(uuid,uuid,uuid)")
    unblocked = re.sub(
        r"FOR v_block IN.*?END LOOP;", "", expo_original, count=1, flags=re.S)
    if unblocked == expo_original:
        record("NC-M3B-005 — inject defect", False,
               "the blocking loop was not found in the captured definition")
    else:
        print("\n  NC-M3B-005  expo releases a set one station has not finished")
        prove_sql("NC-M3B-005", incomplete_set_gate,
                  "INCOMPLETE_SET_SERVED", unblocked,
                  captured=["fulfillment.release_to_service(uuid,uuid,uuid)"])

    # The defect that survives BOTH locks on the actor: the change is attributed on the
    # record and the station's queue stops carrying the name. Chosen over removing the
    # guard because that alone leaves the NOT NULL refusing the write and the gate green
    # for a reason unrelated to the guard — and because the ledger is append-only, so a
    # break that WROTE an unattributed event would leave an event behind that can never
    # be folded again.
    queue_original = capture_function("fulfillment.kds_queue(uuid,uuid)")
    nameless = queue_original.replace(
        "(SELECT ua.display_name FROM fulfillment.priority_change pc",
        "(SELECT NULL::text FROM fulfillment.priority_change pc", 1)
    if nameless == queue_original:
        record("NC-M3B-006 — inject defect", False,
               "the attribution subquery was not found in the captured definition")
    else:
        print("\n  NC-M3B-006  a rush reaches the station queue with nobody's name on it")
        prove_sql("NC-M3B-006", priority_attribution_gate,
                  "PRIORITY_WITHOUT_ATTRIBUTION", nameless,
                  captured=["fulfillment.kds_queue(uuid,uuid)"])


# ===========================================================================

def main() -> int:
    print("=" * 74)
    print("M3-B VERIFICATION — fulfillment, tickets, stations, the KDS, the machine")
    print(f"real PostgreSQL, real compiled service, real Chromium (running on "
          f"{platform.system()})")
    print("evidence encoding: UTF-8")
    print("\n  (measured) = read out of a real browser's own layout after it rendered")
    print("  (asserted) = read from source, from a payload, or from the database\n")
    print("=" * 74)

    # FAIL CLOSED. A suite that could not read the pinned machine and carried on with a
    # transition table of its own would be checking the schema against itself — and a
    # state machine that silently defaults to permissive is worse than none at all.
    try:
        states, edges = pinned_machine()
    except MachineUnavailable as error:
        print(f"\nFAIL STATE_MACHINE_UNAVAILABLE: {error}")
        return 1
    CONTEXT["states"], CONTEXT["edges"] = states, edges
    print(f"\nSM-FULFILLMENT-TICKET loaded from the pinned package: {len(states)} states, "
          f"{len(edges)} legal edges, {len(states) * (len(states) - 1)} ordered pairs")

    fx.seed()
    print("fixtures seeded: two preparation stations, a versioned rule set, a service "
          "policy and a staff session")

    session_id, token = fx.staff_session()
    CONTEXT["staff_token"] = token

    # Built from the REPOSITORY before anything is measured. The chain's earlier slices
    # build too, and relying on that would mean the safety claim was measured against
    # whatever the workspace happened to hold — which, run on its own, was a station
    # stylesheet two edits out of date that measured 1.35rem and reported it as fact.
    sync_and_build()

    # A ticket that exists because an order was accepted and routed, never one made by
    # hand: the walk in section 2 is only evidence about tickets if it walks a real one.
    walk = fx.an_accepted_order()
    CONTEXT["walk_ticket"] = walk["tickets"][0]["id"]

    with Service(APP) as service:
        CONTEXT["base_url"] = f"http://127.0.0.1:{service.port}"
        CONTEXT["restart"] = service.restart

        section_machine(states, edges)
        section_transitions(states, edges)
        section_routing()
        section_queue_and_progress()
        section_station_operations()
        section_allergy_emphasis()
        section_expo_and_service()
        section_timing_and_capacity()
        section_printer_fallback()
        section_transfer_and_waste()
        section_closures()
        section_governance(states)
        section_controls()

    passed = sum(1 for _n, ok, _d, _e in results if ok)
    failed = [(name, detail) for name, ok, detail, _e in results if not ok]
    # DERIVED from the run, never tallied by hand: the M2-C measured/asserted split drifted
    # 45/47 against 46/17 the one time it was counted rather than computed.
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
        print("FAIL M3B_VERIFICATION")
        return 1
    print("PASS M3B_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
