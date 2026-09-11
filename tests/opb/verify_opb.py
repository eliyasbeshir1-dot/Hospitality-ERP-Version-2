#!/usr/bin/env python3
"""OP-B verification: the three staff screens, over routes that already exist.

WHAT THIS SUITE IS FOR. OP-A gave the kitchen thirteen routes and no cook could press one:
station.ts and waiter.ts contained no fetch at all, and there was no till. Every route this
gate's screens call was delivered and proved by an earlier slice, so nothing here re-proves
a transition rule, a split, a tax or a lockout. Every check asks whether a PERSON can reach
behaviour that already exists, and every control breaks a SCREEN rather than the logic
behind it — because a rule the database enforces perfectly can still be undone by the
surface that draws it.

MEASURED VERSUS ASSERTED. A claim about what somebody SEES is measured in a real browser
and marked `measured`; a claim about what the service does is marked `asserted`. The split
is derived from the run at the end, never tallied by hand, which is M2-C's discipline and
the reason its own split stopped drifting.

Usage:
    M1A_ADMIN_DSN=... M1A_APP_DSN=... python3 tests/opb/verify_opb.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

sys.path.insert(0, str(REPO / "tests"))          # fenced.py lives beside the suites
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

CONTEXT: dict = {}
results: list[tuple[str, bool, str, str]] = []

# The workspace copies a defect is planted in. Never the repository: api/build.sh re-copies
# from the repository on every run, so reverting a planted defect is a rebuild rather than
# an edit and the repository is never broken even for an instant.
STATION_TS = WORKSPACE / "station" / "src" / "station.ts"
STATION_CSS = WORKSPACE / "station" / "station.css"
CASHIER_TS = WORKSPACE / "cashier" / "src" / "cashier.ts"
CASHIER_HTML = WORKSPACE / "cashier" / "index.html"


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    results.append((name, ok, detail, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] ({evidence}) {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def measured(name: str, ok: bool, detail: str = "") -> None:
    record(name, ok, detail, evidence="measured")


def probe(scene: str, args: dict) -> dict:
    """One browser scene. Raises rather than returning half a measurement.

    Copied into the build workspace and run from there, because that is where playwright
    is installed. The repository ships no node_modules, and a probe run from tests/ would
    fail to import the browser rather than fail to measure something — a distinction the
    error message would not have made obvious.
    """
    target = WORKSPACE / "opb_probe.mjs"
    target.write_text((HERE / "opb_probe.mjs").read_text(encoding="utf-8"),
                      encoding="utf-8", newline="\n")
    proc = subprocess.run(
        ["node", str(target), CONTEXT["base_url"], scene, json.dumps(args)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(WORKSPACE))
    if proc.returncode != 0 or not proc.stdout.strip():
        raise ProbeFailed(f"scene {scene}",
                          (proc.stderr or proc.stdout).strip()[:600])
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
    statics = {"station": [("index.html", "station.html"), ("station.css", "station.css")],
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

    The gate returns (ok, signature_or_None, detail). RED is "the gate now fails, and it
    fails by the name this control owns" — not merely "something went wrong", because a
    control that accepts any failure would pass on a typo in the surface.
    """
    ok, _sig, detail = gate()
    if not ok:
        measured(f"{control} — baseline",
                 False, f"the gate was already failing before the break: {detail}")
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


def prove_rule(control: str, signature: str, red, green) -> None:
    """A control whose subject is a rule the SERVICE enforces, not a screen."""
    red_ok, red_detail = red()
    record(f"{control} — RED with the defect planted", red_ok, red_detail)
    green_ok, green_detail = green()
    record(f"{control} — GREEN after revert", green_ok, green_detail)


# ===========================================================================
# The gates the controls break
# ===========================================================================

EMPHASIS = {
    "kitchen_code": "PEANUT",
    "written_warning": "Contains peanuts. Do not substitute the sauce.",
    "acknowledgement_text": "The guest was told and confirmed.",
    "emphasis_rank": 1,
    "emphasis_glyph": "▲",
}


def allergy_gate() -> tuple[bool, str | None, str]:
    """The words are on the screen, and something other than colour carries them."""
    answer = probe("allergy", {"emphasis": EMPHASIS})
    seen = answer["steps"].get("rendered")
    if not seen:
        return False, "WRITTEN_WARNING_ABSENT_FROM_RENDER", "nothing rendered"

    if not seen["carriesTheWarning"]:
        return (False, "WRITTEN_WARNING_ABSENT_FROM_RENDER",
                f"the block reads {seen['text'][:90]!r} and does not contain the written "
                f"warning. A kitchen code with no sentence behind it is a mark nobody can "
                f"act on")

    # Colour is not measured directly — the point is that removing it changes nothing.
    # So the question asked here is whether ANY non-colour signal separates this block
    # from the text around it.
    louder = float(seen["weight"] or 400) > float(seen["bodyWeight"] or 400)
    bigger = seen["size"] > seen["bodySize"]
    bordered = seen["border"] not in ("", "0px")
    if not (louder or bigger or bordered or seen["glyphPresent"]):
        return (False, "STATE_CONVEYED_BY_COLOUR_ALONE",
                f"weight {seen['weight']} vs {seen['bodyWeight']}, size {seen['size']} vs "
                f"{seen['bodySize']}, border {seen['border']!r}, glyph "
                f"{seen['glyphPresent']} — nothing but colour marks this as a warning")
    return (True, None,
            f"{seen['text'][:70]!r} — weight {seen['weight']}, size {seen['size']}px, "
            f"border {seen['border']}, glyph {seen['glyphPresent']}, role {seen['role']}")


def till_gate() -> tuple[bool, str | None, str]:
    """The tip is beside the bill, and nothing is chosen for the guest."""
    answer = probe("till", {**CONTEXT["staff"], "bill": CONTEXT["bill"],
                            "token": CONTEXT["token"],
                            "sessionId": CONTEXT["staff_session"],
                            "prompts": ["2", "50000"]})
    tip = answer["steps"].get("tip")
    friction = answer["steps"].get("friction")
    if not tip:
        # Say WHICH step the scene stopped at and what the page complained about. "The tip
        # box did not render" was true and useless: it names the last thing that did not
        # happen rather than the first thing that went wrong.
        return (False, "TIP_COMMINGLED_WITH_BILL",
                f"the till scene reached {sorted(answer['steps'])} and stopped; "
                f"page errors: {answer.get('errors') or 'none'}")

    if tip["insideTheBill"] or tip["insideTheSummary"] or tip["tipWordInsideSummary"]:
        return (False, "TIP_COMMINGLED_WITH_BILL",
                f"{tip['insideTheBill']} of {tip['options']} tip option(s) are inside the "
                f"bill element and {tip['insideTheSummary']} inside the summary; the word "
                f"'tip' inside the summary: {tip['tipWordInsideSummary']}. A tip rendered "
                f"in the bill has told the guest it is part of what they owe")

    if tip["preselected"]:
        return (False, "TIP_PRESELECTED",
                f"{tip['preselected']} of {tip['options']} tip option(s) render as chosen. "
                f"Nothing in the configuration says which is preferred, so a chosen one is "
                f"the till deciding for the guest")

    if friction and not (friction["shown"]["panelShown"]
                         and friction["withoutReason"]["ran"] is None
                         and friction["after"]["ran"]):
        return (False, "DESTRUCTIVE_ACTION_WITHOUT_REASON",
                f"a refund: panel shown {friction['shown']['panelShown']}, ran without a "
                f"reason {friction['withoutReason']['ran']!r}, ran with one "
                f"{friction['after']['ran']!r}")

    return (True, None,
            f"{tip['options']} tip option(s), none inside the bill, none preselected; a "
            f"refund refuses an empty reason and proceeds with one")


# ===========================================================================
# Sections
# ===========================================================================

def section_screens() -> None:
    print("\n--- 1. The three screens reach the routes (the premise of this slice) ---")

    board = probe("board", {**CONTEXT["staff"], "station": opa.STATION_HOT,
                            "ticket": CONTEXT["ticket"]})
    before = board["steps"]["beforeSignIn"]
    measured("the station board asks for a sign-in and issues no request until it has one",
             before["signInShown"] and before["staffRequests"] == 0,
             f"sign-in shown {before['signInShown']}, /s/v1 requests before it: "
             f"{before['staffRequests']}. This is also what keeps M3-B honest: it opens "
             f"this page with no service behind it and renders its own payload")

    actions = board["steps"]["actions"]
    measured("a cook opens a ticket and its actions come from the catalog",
             len(actions["labels"]) > 0
             and any("—" in label for label in actions["labels"]),
             f"{actions['labels']}")
    measured("every action is a target a cook can hit at arm's length (FR-UX-002)",
             actions["smallestTarget"] >= 44,
             f"smallest action measures {actions['smallestTarget']:.0f}px on its shorter "
             f"side; 44 is the floor every touch guideline settles on")
    measured("the ticket moves through the screen",
             "done" in (board["steps"]["moved"]["notice"] or ""),
             board["steps"]["moved"]["notice"])

    waiter = probe("waiter", CONTEXT["staff"])
    floor = waiter["steps"]["floor"]
    measured("the waiter floor fetches itself, with the unpaid balance FR-POS-004 carries",
             floor["staffRequests"] > 0 and floor["showsUnpaidBalance"],
             f"{floor['tableRows']} table row(s) from {floor['staffRequests']} request(s); "
             f"the unpaid balance is on the screen: {floor['showsUnpaidBalance']}. "
             f"pos.table_view has returned unpaid_balance_minor since M3-D and nothing "
             f"had ever drawn it")

    till = probe("till", {**CONTEXT["staff"], "bill": CONTEXT["bill"],
                          "prompts": ["2", "50000"]})
    bill = till["steps"]["bill"]
    measured("the till reads a bill nobody handed it, in the bill's own language",
             bill["lines"] > 0 and bill["lang"] == "am",
             f"{bill['billNumber']}, {bill['lines']} line(s), total {bill['total']}, "
             f"lang={bill['lang']!r} — issued in Amharic and read by a cashier whose "
             f"session is not. A document does not change language for its reader")


def section_controls() -> None:
    print(f"\n--- 2. {len(registry.signatures_for('OPB'))} controls, each proved red "
          f"then green ---")

    # ---------------------------------------------------------------- NC-OPB-001
    print("\n  NC-OPB-001  a station renders an allergy without its written warning")
    prove_surface(
        "NC-OPB-001", "WRITTEN_WARNING_ABSENT_FROM_RENDER", "station", allergy_gate,
        # The defect: the block keeps the kitchen code and the glyph and loses the
        # sentence. It still LOOKS like a warning, which is what makes it the realistic
        # shape of this mistake rather than a straw one.
        [(STATION_TS,
          "  block.appendChild(document.createTextNode(\n"
          "    `ALLERGY ${emphasis.kitchen_code} — ${emphasis.written_warning}`));",
          "  block.appendChild(document.createTextNode(\n"
          "    `ALLERGY ${emphasis.kitchen_code}`));")])

    # ---------------------------------------------------------------- NC-OPB-002
    print("\n  NC-OPB-002  the emphasis is carried by colour and nothing else")
    prove_surface(
        "NC-OPB-002", "STATE_CONVEYED_BY_COLOUR_ALONE", "station", allergy_gate,
        # Red ink on a pink ground, at the weight and size of the text around it, with no
        # border and no glyph. On a screen it still reads as a warning; with colour
        # flattened, or to somebody who cannot see red, it is a sentence like any other.
        # APPENDED, not inserted at the top of the rule. The first attempt put these
        # declarations at the START of .allergy, where the real ones that follow simply
        # won on source order — a planted defect that planted nothing, and a control that
        # would have "passed" by failing to break what it claims to break.
        [(STATION_CSS, ".ticket { cursor: pointer; }",
          ".ticket { cursor: pointer; }\n"
          ".allergy { color: #b00020; background-color: #ffe8e8;\n"
          "  font-weight: 400; font-size: 1rem; border: 0; }\n"),
         (STATION_TS,
          "  const glyph = element('span', 'allergy-glyph', emphasis.emphasis_glyph);",
          "  const glyph = element('span', 'allergy-glyph', '');")])

    # ---------------------------------------------------------------- NC-OPB-003
    print("\n  NC-OPB-003  the tip box rendered inside the bill summary")
    prove_surface(
        "NC-OPB-003", "TIP_COMMINGLED_WITH_BILL", "cashier", till_gate,
        # The defect a layout change makes: the tip renders into the bill's own summary
        # element. Every figure stays correct; what changes is what the guest is being
        # told the bill IS.
        [(CASHIER_TS, "  const root = $('tip-box');\n  if (!root) return;",
                      "  const root = document.getElementById('bill-summary');\n"
                      "  if (!root) return;")])

    # ---------------------------------------------------------------- NC-OPB-004
    print("\n  NC-OPB-004  a tip option preselected for the guest")
    prove_surface(
        "NC-OPB-004", "TIP_PRESELECTED", "cashier", till_gate,
        [(CASHIER_TS, "    node.setAttribute('data-tip-percentage', option.percentage);",
                      "    node.setAttribute('data-tip-percentage', option.percentage);\n"
                      "    if (option.display_order === 2) "
                      "node.setAttribute('aria-pressed', 'true');")])

    # ---------------------------------------------------------------- NC-OPB-005
    print("\n  NC-OPB-005  an override accepted without the manager's own session")

    def red_override():
        # THE CASHIER APPROVES THEMSELVES. The screen's override panel signs a manager in
        # and sends THEIR session id; this sends the cashier's own, which is the shape the
        # rule exists to refuse and the shape a screen could offer by accident.
        answer = opa.call("POST", "/s/v1/overrides", {
            "actionCode": "payment.refund",
            "approverSessionId": CONTEXT["staff_session"],
            "reasonCodeId": CONTEXT["reason_code"],
            "subjectKind": "bill", "subjectId": CONTEXT["bill"],
        }, token=CONTEXT["token"])
        return (answer.get("status", 0) >= 400,
                f"OVERRIDE_WITHOUT_STEP_UP would be HTTP 200 here; the session that asked "
                f"for the override offered itself as the approver and got "
                f"HTTP {answer.get('status')} {answer.get('reason') or ''}")

    def green_override():
        source = (REPO / "cashier" / "src" / "cashier.ts").read_text(encoding="utf-8")
        # The screen must not have a way to send its own session as the approver. Read
        # from the source rather than trusted: this is the one place a surface could
        # quietly undo a schema rule by being convenient.
        sends_own = re.search(r"approverSessionId:\s*(session\.sessionId|CONTEXT)", source)
        signs_in = "POST', '/v1/auth/login'" in source.replace('"', "'")
        return (not sends_own and signs_in,
                "the override panel authenticates the manager and sends the session that "
                "answer returned; there is no path in the till that offers the cashier's "
                "own session as the approver")

    prove_rule("NC-OPB-005", "OVERRIDE_WITHOUT_STEP_UP", red_override, green_override)

    # ---------------------------------------------------------------- NC-OPB-006
    print("\n  NC-OPB-006  a destructive action proceeding with no reason")
    prove_surface(
        "NC-OPB-006", "DESTRUCTIVE_ACTION_WITHOUT_REASON", "cashier", till_gate,
        [(CASHIER_TS,
          "    if (need.requires_reason && reason.value.trim() === '') {\n"
          "      report(`${label}: a reason is required`);\n"
          "      return;\n"
          "    }",
          "    // the reason is no longer required")])

    # ---------------------------------------------------------------- NC-OPB-007
    print("\n  NC-OPB-007  the station screen driving a ticket into an illegal state")

    def red_illegal():
        answer = opa.call("POST", f"/s/v1/tickets/{CONTEXT['ticket']}/transitions",
                          {"toState": "served"}, token=CONTEXT["token"])
        return (answer.get("status", 0) >= 400,
                f"ILLEGAL_TRANSITION_ACCEPTED would be HTTP 200; a ticket was driven "
                f"straight to 'served' and got HTTP {answer.get('status')} "
                f"{answer.get('reason') or ''}. The screen can send any state it likes — "
                f"the machine is what refuses")

    def green_illegal():
        detail = opa.call("GET", f"/s/v1/tickets/{CONTEXT['ticket']}",
                          token=CONTEXT["token"])
        offered = [t["to_state"] for t in (detail.get("transitions") or [])]
        legal = [r[0] for r in run(ADMIN, f"""
            SELECT to_state::text FROM fulfillment.transition
             WHERE from_state = '{detail.get('ticket', {}).get('state')}'
             ORDER BY to_state;""").rows]
        return (offered == legal and len(offered) > 0,
                f"the screen is offered exactly the moves the catalog allows from "
                f"{detail.get('ticket', {}).get('state')!r}: {offered} — and "
                f"fulfillment.transition holds {legal}")

    prove_rule("NC-OPB-007", "ILLEGAL_TRANSITION_ACCEPTED", red_illegal, green_illegal)

    # ---------------------------------------------------------------- NC-OPB-008
    print("\n  NC-OPB-008  a screen re-implementing a rule the route enforces")

    def transition_tables_in(source: str) -> list[str]:
        """A state machine written into a surface, found rather than assumed absent."""
        stripped = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        stripped = re.sub(r"^\s*\*.*$", "", stripped, flags=re.M)
        stripped = re.sub(r"//.*$", "", stripped, flags=re.M)
        states = ("queued", "acknowledged", "held", "preparing", "ready", "completed",
                  "served", "cancelled")
        found = []
        # A MACHINE MAPS A STATE TO SOMETHING; A LIST MERELY NAMES STATES.
        #
        # The first version of this flagged two state names on one line, and it flagged
        # the station surface's own Bucket union and BUCKETS array — FR-FUL-003's seven
        # DISPLAY buckets, which share five names with the machine's states and are not a
        # transition table. A scan that cannot tell a list from a mapping would have made
        # this control unpassable while the code was correct.
        #
        # So what is looked for is a state used as a KEY: `'preparing': [...]`,
        # `case 'ready':`, or `'held' =>`. That is the shape of a second opinion about
        # where a ticket may go, and a flat list cannot produce it.
        key_shapes = "|".join(
            rf"['\"]{s}['\"]\s*(?::|=>)|case\s+['\"]{s}['\"]\s*:" for s in states)
        for line in stripped.splitlines():
            if re.search(key_shapes, line):
                found.append(line.strip()[:90])
        return found

    def red_divergence():
        planted = STATION_TS.read_text(encoding="utf-8")
        table = ("const NEXT: Record<string, string[]> = "
                 "{ 'queued': ['acknowledged'], 'acknowledged': ['preparing', 'held'] };\n")
        STATION_TS.write_text(table + planted, encoding="utf-8", newline="\n")
        try:
            found = transition_tables_in(STATION_TS.read_text(encoding="utf-8"))
            return (len(found) > 0,
                    f"CHANNEL_RULE_DIVERGENCE: a transition table planted in the station "
                    f"surface is found by the scan: {found[:1]}")
        finally:
            STATION_TS.write_text(planted, encoding="utf-8", newline="\n")

    def green_divergence():
        offenders = {}
        for name, path in (("station", REPO / "station" / "src" / "station.ts"),
                           ("cashier", REPO / "cashier" / "src" / "cashier.ts"),
                           ("waiter", REPO / "waiter" / "src" / "waiter.ts")):
            found = transition_tables_in(path.read_text(encoding="utf-8"))
            if found:
                offenders[name] = found
        return (not offenders,
                f"no surface names two ticket states on one line: the station board draws "
                f"its buttons from the `transitions` the service reads out of "
                f"fulfillment.transition, so the machine has one statement. "
                f"{offenders or 'none'}")

    prove_rule("NC-OPB-008", "CHANNEL_RULE_DIVERGENCE", red_divergence, green_divergence)


def section_signatures() -> None:
    print("\n--- 3. This gate's vocabulary and what it left unproved ---")

    signatures = registry.signatures_for("OPB")
    pattern, terms = fenced_identifier_pattern()
    offending = sorted({m.group(0) for s in signatures
                        for m in re.finditer(pattern, s, re.I)})
    record("no OP-B failure signature names a permanently fenced domain",
           len(signatures) == 8 and not offending,
           f"{len(signatures)} signature(s) checked against all {terms} authoritative "
           f"terms: {offending or 'none'}")

    sources = "\n".join(
        p.read_text(encoding="utf-8") for p in (
            HERE / "verify_opb.py",
            REPO / "cashier" / "src" / "cashier.ts",
            REPO / "cashier" / "cashier.css",
            REPO / "station" / "src" / "station.ts",
            REPO / "waiter" / "src" / "waiter.ts",
            REPO / "seeds" / "0005_the_demonstration_floor_can_be_billed.sql",
            REPO / "seeds" / "0006_the_demonstration_floor_can_take_money.provision.sql",
            REPO / "seeds" / "0007_the_demonstration_floor_can_escalate.sql",
        ) if p.exists())
    hits = sorted({m.group(0) for m in re.finditer(pattern, sources, re.I)})
    record("and neither does anything this gate wrote",
           not hits,
           f"checked the suite, three surfaces and three seeds against all {terms} "
           f"terms: {hits or 'none'}")

    sys.path.insert(0, str(REPO / "tools"))
    import uncalled_routes
    census = uncalled_routes.survey()
    record("the route census is reported, including what this gate has not yet proved",
           census["total"] > 0,
           f"{census['called']} of {census['total']} routes are called by something and "
           f"{len(census['uncalled'])} by nothing, from {census['call_sites']} call "
           f"sites. Three screens now call routes that had no caller when OP-A closed")


# ===========================================================================

def main() -> int:
    print("OP-B verification — the station board, the till and the waiter floor")
    print("real PostgreSQL, real compiled service, real browser")
    print("")

    # BUILT FROM THE REPOSITORY BEFORE ANYTHING IS MEASURED. The chain's earlier slices
    # build too, and relying on that would mean measuring a surface some other suite left
    # in the workspace — which is how M3-B once measured a stylesheet two edits out of date.
    sync_and_build()

    with Service(APP) as service_process:
        CONTEXT["base_url"] = f"http://127.0.0.1:{service_process.port}"
        CONTEXT["service"] = service_process
        opa.CONTEXT["base_url"] = CONTEXT["base_url"]
        opa.CONTEXT["service"] = service_process

        opa.clear_lockout()
        answer = opa.login(opa.MANAGER_PASSWORD, value=opa.MANAGER_EMAIL)
        if not answer.get("token"):
            print(f"FAIL OPB_SIGN_IN\n  the manager could not sign in: {answer}")
            return 1
        CONTEXT["token"] = answer["token"]
        CONTEXT["staff_session"] = answer.get("sessionId")
        opa.CONTEXT["token"] = answer["token"]
        CONTEXT["staff"] = {"tenant": opa.TENANT, "outlet": opa.OUTLET,
                            "email": opa.MANAGER_EMAIL, "secret": opa.MANAGER_PASSWORD}

        try:
            order, ticket = opa.an_order_ready_for_the_kitchen()
            CONTEXT["ticket"] = ticket
            session_id = run(ADMIN, f"""
                SELECT table_session_id::text FROM ordering.customer_order
                 WHERE id = '{order}';""").scalar
            check = opa.call("POST", "/s/v1/checks", {"tableSessionId": session_id},
                             token=CONTEXT["token"]).get("checkId")
            for line in [r[0] for r in run(ADMIN, f"""
                    SELECT id::text FROM ordering.order_line
                     WHERE order_id = '{order}' ORDER BY line_number;""").rows]:
                opa.call("POST", f"/s/v1/checks/{check}/allocations",
                         {"orderLineId": line}, token=CONTEXT["token"])
            CONTEXT["bill"] = opa.call(
                "POST", "/s/v1/bills", {"checkId": check, "locale": "am"},
                token=CONTEXT["token"]).get("billId")
            # A tip is offered on ONE PAYER'S SHARE, and billing.issue_bill() creates no
            # share. Without a split there are no tip options, and the three controls
            # about the tip box would each fail their baseline for a reason that has
            # nothing to do with what they test.
            opa.call("POST", f"/s/v1/bills/{CONTEXT['bill']}/split",
                     {"mode": "equal_share", "payers": 2}, token=CONTEXT["token"])
            CONTEXT["reason_code"] = run(ADMIN, f"""
                SELECT id::text FROM config.reason_code
                 WHERE tenant_id = '{opa.TENANT}' LIMIT 1;""").scalar

            for section in (section_screens, section_controls, section_signatures):
                try:
                    section()
                except ProbeFailed as exc:
                    record(f"{section.__name__} completed", False,
                           f"probe did not execute: {exc}")
        except ProbeFailed as exc:
            record("the floor this gate measures could be set up", False, str(exc))

    failed = [name for name, ok, _d, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")
    owned = len([c for c in registry.CONTROLS if c[3] == "opb"])

    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    # DERIVED FROM THE RUN. A split written by hand is a claim about evidence, and this
    # repository has already had one drift.
    print(f"  measured      : {measured_count}   (read out of a real browser's layout)")
    print(f"  asserted      : {len(results) - measured_count}")
    print(f"  controls      : {owned} registered, each proved red then green")

    if failed:
        print("\nFAIL OPB_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS OPB_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
