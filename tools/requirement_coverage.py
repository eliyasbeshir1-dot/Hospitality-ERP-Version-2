#!/usr/bin/env python3
"""The wider FR-GOV-004 audit: every landed requirement delivered, or accounted for.

WHY THIS EXISTS, AND WHY IT IS NOT THE PARTIAL-CLOSURE CHECKER.

tools/partial_closures.py polices the register: an entry that names no completer, a
closure resting on an incomplete completer, a completer quietly moved later. Every one of
those rules starts from AN ENTRY. It said so itself, in the boundary paragraph added at
M4-B:

    it checks NAMED COMPLETERS, not every requirement whose gate has landed. A
    requirement that is partly built and that no entry points at is invisible to it.

That is the hole this file closes. It starts from the PACKAGE — all 336 active
requirements, each carrying the gate that introduced it — and asks the opposite question:
of the requirements whose gate has landed, which can this repository show anything for?

WHAT COUNTS AS DELIVERED, AND WHY BOTH HALVES OF THE BAR ARE NEEDED.

A requirement is delivered when it is cited by something that RUNS and CAN FAIL.

  RUNS excludes an identifier written in a comment. A requirement id in a source comment
  is the build asserting its own compliance — a test supplying its own evidence, which is
  the one thing this project refuses everywhere else. So citations are read from the
  RECORDED OUTPUT of executions, not from source: a suite log, a journey log, the fenced
  gate's log. If a check printed the id, the check ran.

  CAN FAIL is what makes the audit non-vacuous. A citation sitting in something that
  always passes is precisely the condition being audited for. This half cannot be proved
  uniformly, and the honest thing is to say so per requirement rather than to imply a
  strength that was not measured, so evidence carries a GRADE:

      proved-red   the citation sits on a negative control, and tools/controls.py knows
                   from this same run that the control was shown red with a real defect
                   planted and green after revert. The strongest grade available: the
                   assertion has been demonstrated capable of failing.
      ran          the citation sits on an ordinary recorded check that executed and
                   reported in this run. THIS GRADE VERIFIES THAT THE CITATION RUNS. It
                   does NOT establish that the check has ever been shown to fail, and the
                   report says that in those words rather than letting a reader assume it.
      ci-step      the citation sits in a step of the workflow. A step that exits non-zero
                   fails the build, so it can fail; what it cannot show is a planted
                   defect. Covers the requirements delivered by CI rather than by a suite
                   — FR-TST-020's reorder sweep and FR-DAT-017's role choice are the two
                   that made option 2 of this design wrong.

WHERE THE CITATION SITES COME FROM. Not from a list in this file. The site kinds are
discovered: every *.log under the evidence directory is a recorded execution, and the
workflow is the set of steps CI runs. A new kind of site at M5a — another suite,
another job, another driver — is covered because it produces one of those two artifacts,
without anybody extending anything here. A migration is deliberately NOT a citation site:
its requirement ids sit in comments, and a comment is the thing the RUNS half excludes. If
a constraint matters, a check must exercise it and cite it.

WHAT THE AUDIT REPORTS. Findings, not a count. Each unaccounted requirement is named with
its gate, its title, and what is missing — because "roughly ninety" is not actionable and
an audit whose output nobody can act on stops being read.

THE TWO KINDS OF GAP, WHICH MUST NOT BE CONFLATED.

  absent    the behaviour genuinely does not exist. A PRODUCT gap. Only this kind can be
            a money, security or authority absence, and only this kind belongs in the
            partial-closure register, because only this kind is a requirement partly done.
  uncited   the behaviour exists and works and nothing checks it by name. A GOVERNANCE
            gap. Recording it as a partial closure would state something false — that the
            requirement is partly built — so it is recorded here instead, with the gate at
            which the citation is owed.

Conflating them inflates the urgent list and buries the real entries in it, so the
classification is data in planning/requirement_coverage.json rather than a judgement this
file makes, and every entry carries the reasoning that justified it. THE M4 REVIEW MAY
CHALLENGE A CLASSIFICATION AS READILY AS A FIX: a gap wrongly called schedulable is worse
than one honestly called urgent, and the register says so in terms.

Standard library only. Fails closed: sets it cannot populate are errors, not empty lists.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console import use_utf8_output  # noqa: E402
import controls as control_registry  # noqa: E402
import partial_closures  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
COVERAGE = REPO / "planning" / "requirement_coverage.json"
WORKFLOW = REPO / ".github" / "workflows" / "m1-conformance.yml"

# A requirement identifier as the package spells it. Matched rather than split on, because
# the trailing letter is part of the id — FR-CFG-001C and FR-CFG-001D are different
# requirements and an audit that treated them as one would report a gap as delivered.
IDENTIFIER = re.compile(r"FR-[A-Z0-9]+-[0-9]+[A-Z]*")

GRADES = ("proved-red", "ran", "ci-step")
STATES = ("absent", "uncited")
CATEGORIES = ("money", "security", "authority", "product", "governance")
URGENT = ("money", "security", "authority")


class CoverageUnreadable(RuntimeError):
    """A source this audit derives from could not be read, so no verdict is possible."""


class RequirementUnaccounted(RuntimeError):
    """A landed requirement is neither delivered, nor in the register, nor classified."""


def landed_requirements() -> list[dict]:
    """Every active requirement whose introducing gate has landed, from the package.

    `introduced_at` is the package's own gate field and its distribution equals the
    package's own gate_counts, which is checked below: if the two ever disagree the
    package is being read wrongly and the audit stops rather than auditing a subset.
    """
    payload = json.loads(partial_closures._requirements_path().read_text(encoding="utf-8"))
    active = payload.get("active_requirements") or []
    if not active:
        raise CoverageUnreadable(
            "the package lists no active requirements, so there is nothing to audit and "
            "an empty audit would agree with any repository")

    declared = payload.get("gate_counts") or {}
    counted: dict[str, int] = {}
    for requirement in active:
        gate = requirement.get("introduced_at")
        if not gate:
            raise CoverageUnreadable(
                f"{requirement.get('id')} names no introducing gate, so whether its gate "
                f"has landed cannot be decided")
        counted[gate] = counted.get(gate, 0) + 1
    if declared and counted != declared:
        raise CoverageUnreadable(
            f"introduced_at counts {counted} disagree with the package's own gate_counts "
            f"{declared}; this audit is reading the package wrongly and will not report "
            f"a subset as if it were the whole")

    return [r for r in active if r["introduced_at"] in landed_gates()]


def landed_gates() -> set[str]:
    """Every gate at or before the furthest one this repository has a suite for.

    partial_closures.landed_gates() reads landing off the tests directory, which is right
    for what it does and wrong here: there is no tests/m0r, so M0R — a gate this project
    passed before the repository had a single migration — was invisible, and with it the
    twenty-four scanner requirements it introduced. The audit reported 256 landed
    requirements when 288 have landed, which is a subset wearing the word "every".

    So landing is closed over the PACKAGE'S OWN GATE ORDER: if M4-B has landed then every
    gate before it has, because a gate cannot be passed before its predecessor. That also
    brings M0 into scope, which matters more than it looks — FR-GOV-004, the requirement
    this whole audit implements, is an M0 requirement, and an audit that excluded the
    clause demanding it would be the funniest possible instance of the defect it hunts.
    """
    order = partial_closures.gate_order()
    if not order:
        raise CoverageUnreadable("the package declares no gate order")
    suite_backed = partial_closures.landed_gates()
    reached = [i for i, gate in enumerate(order) if gate in suite_backed]
    if not reached:
        raise CoverageUnreadable(
            "no gate in the package's order has a verification suite, so nothing can be "
            "shown to have landed and every requirement would be reported unaccounted")
    return set(order[:max(reached) + 1])


def execution_logs(logs: Path) -> list[Path]:
    """Recorded executions: every log the run produced, discovered rather than listed."""
    if not logs.is_dir():
        raise CoverageUnreadable(
            f"{logs} is not a directory. The audit reads citations out of recorded output, "
            f"and with no output it would report every requirement unaccounted — a "
            f"diagnostic naming a cause it had not verified")
    found = sorted(logs.glob("*.log"))
    if not found:
        raise CoverageUnreadable(f"no *.log under {logs}; see above")
    return found


def ci_citations() -> set[str]:
    """Requirements cited by the workflow: the steps CI executes and can fail on.

    THE WHOLE FILE, not the `run:` bodies alone. The first version of this matched blocks
    and scored zero while a plain search of the same file found ten requirements, because
    most of them are cited in a step's `name:` rather than inside its shell. That is not a
    weaker citation: a name labels a step, the step runs, and the step fails the build on a
    non-zero exit. FR-TST-020 is cited by the name of the reorder sweep and FR-DAT-017 by
    the job that chooses the least-privileged role, and both are delivered by CI rather
    than by any suite — which is the reason this site kind exists at all.

    Guarded on the file being a workflow that runs something, so a file that stopped
    containing steps cannot quietly contribute citations for work nobody executes.
    """
    try:
        text = WORKFLOW.read_text(encoding="utf-8")
    except OSError as exc:
        raise CoverageUnreadable(f"{WORKFLOW} could not be read: {exc}") from exc
    if "run: |" not in text:
        raise CoverageUnreadable(
            f"{WORKFLOW.name} contains no run: block, so it is not a workflow that "
            f"executes anything and its citations would stand for nothing")
    return set(IDENTIFIER.findall(text))


def evidence(logs: Path) -> dict[str, str]:
    """{requirement id: grade} for everything this run can show, best grade winning."""
    graded: dict[str, str] = {}

    def offer(identifier: str, grade: str) -> None:
        held = graded.get(identifier)
        if held is None or GRADES.index(grade) < GRADES.index(held):
            graded[identifier] = grade

    for identifier in ci_citations():
        offer(identifier, "ci-step")

    # Which controls this run proved red AND green, from the registry that already
    # verifies exactly that. Asked rather than re-derived: one implementation.
    proved = control_registry.proved(logs)
    red_and_green = {
        identifier for identifier, markers in proved.items()
        if markers["RED"] and markers["GREEN"]}

    for path in execution_logs(logs):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            cited = IDENTIFIER.findall(line)
            if not cited:
                continue
            on_a_proved_control = any(
                control in line for control in red_and_green)
            for identifier in cited:
                offer(identifier, "proved-red" if on_a_proved_control else "ran")
    return graded


def classifications() -> dict[str, dict]:
    """The recorded triage, keyed by requirement, with every field required present."""
    if not COVERAGE.is_file():
        return {}
    try:
        payload = json.loads(COVERAGE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoverageUnreadable(f"{COVERAGE.name} could not be parsed: {exc}") from exc

    entries = payload.get("gaps")
    if entries is None:
        raise CoverageUnreadable(
            f"{COVERAGE.name} has no 'gaps' list. Fail closed: a coverage record this "
            f"audit cannot read must stop the build, not be treated as no gaps")

    keyed: dict[str, dict] = {}
    for entry in entries:
        for field in ("requirement", "state", "category", "completing_gate", "why",
                      "buildable_why", "closes_when"):
            if not entry.get(field):
                raise CoverageUnreadable(
                    f"a coverage gap is missing '{field}': {entry.get('requirement')}. "
                    f"The classification is a judgement and a judgement without its "
                    f"reasoning is not reviewable, which is the whole point of recording it")
        if entry["state"] not in STATES:
            raise CoverageUnreadable(
                f"{entry['requirement']} has state {entry['state']!r}; expected one of "
                f"{STATES}. 'absent' is a product gap and 'uncited' is a governance gap, "
                f"and conflating them inflates the urgent list and buries the real entries")
        if entry["category"] not in CATEGORIES:
            raise CoverageUnreadable(
                f"{entry['requirement']} has category {entry['category']!r}; expected one "
                f"of {CATEGORIES}")
        if entry["state"] == "uncited" and entry["category"] in URGENT:
            raise CoverageUnreadable(
                f"{entry['requirement']} is classified uncited and {entry['category']}. A "
                f"requirement that works and is merely not cited is a governance gap; only "
                f"an ABSENT behaviour can be a money, security or authority absence. This "
                f"pairing is how an urgent list gets inflated until nobody reads it")
        if entry["state"] == "absent" and entry.get("buildable_now") is None:
            raise CoverageUnreadable(
                f"{entry['requirement']} is absent and does not say whether it is "
                f"buildable now. A reviewer weighing a deferral needs that, because "
                f"without it \"not due yet\" reads as \"not possible yet\", which is a "
                f"different and more forgiving claim")
        # A MOVE IS A JUDGEMENT AND CARRIES ITS REASONING, like every other field here.
        # Re-pointing a gap at a later gate is the escape hatch this audit hands whoever
        # cannot build the thing today, and an escape hatch nobody has to justify is how
        # a gap walks forward one gate at a time until it is somebody else's problem.
        move = entry.get("moved_later")
        if move is not None:
            for field in ("from", "why"):
                if not move.get(field):
                    raise CoverageUnreadable(
                        f"{entry['requirement']} records a move with no {field!r}. The "
                        f"gate it moved OFF is what makes the move reviewable")
            if move["from"] == entry["completing_gate"]:
                raise CoverageUnreadable(
                    f"{entry['requirement']} records a move from {move['from']} to the "
                    f"same gate, which is not a move")
        keyed[entry["requirement"]] = entry

    # NOT CLOSABLE AS A BATCH. Five security absences scheduled forward would otherwise be
    # ticked together by whichever gate arrived first, which is how a scheduled gap becomes
    # a disappeared one. Each absent entry states what specifically must become true for IT
    # to close, and two entries at one gate may not state the same thing.
    by_gate: dict[str, dict[str, str]] = {}
    for entry in keyed.values():
        if entry["state"] != "absent":
            continue          # an uncited gap closes uniformly, by being cited
        seen = by_gate.setdefault(entry["completing_gate"], {})
        collision = seen.get(entry["closes_when"])
        if collision:
            raise CoverageUnreadable(
                f"{entry['requirement']} and {collision} are both absent, both close at "
                f"{entry['completing_gate']}, and both state the same closing test. Two "
                f"entries a gate cannot tell apart are two entries that gate will close "
                f"together, and one of them will not have been fixed")
        seen[entry["closes_when"]] = entry["requirement"]
    return keyed


def audit(logs: Path) -> dict:
    """The finding. Every landed requirement is delivered, in the register, or classified."""
    requirements = landed_requirements()
    graded = evidence(logs)
    recorded = classifications()

    register = partial_closures.load()
    open_entried = {e["requirement"] for e in register if e.get("state") == "open"}

    delivered, unaccounted = [], []
    for requirement in sorted(requirements, key=lambda r: r["id"]):
        identifier = requirement["id"]
        grade = graded.get(identifier)
        if grade:
            delivered.append((identifier, grade, requirement))
        elif identifier in open_entried:
            continue                      # the register already says this is part-done
        else:
            unaccounted.append(requirement)

    if not delivered:
        raise CoverageUnreadable(
            "no landed requirement could be shown delivered by this run. An audit that "
            "finds nothing delivered is measuring itself wrongly, not finding a "
            "repository with no work in it")

    missing = [r for r in unaccounted if r["id"] not in recorded]
    return {
        "landed": len(requirements),
        "delivered": delivered,
        "open_entries": sorted(open_entried & {r["id"] for r in requirements}),
        "unaccounted": unaccounted,
        "unclassified": missing,
        "recorded": recorded,
    }


def check(logs: Path) -> list[tuple[str, str]]:
    """Every landed requirement accounted for, and every account still true."""
    finding = audit(logs)
    problems = [("REQUIREMENT_UNACCOUNTED",
                 f"{r['id']} [{r['introduced_at']}] {r['title']} — nothing in this run "
                 f"cites it, no open partial closure covers it, and planning/"
                 f"{COVERAGE.name} does not classify it. Either it is not delivered, or "
                 f"it is delivered and nothing checks it by name; the audit cannot tell "
                 f"which, and guessing would name a cause it did not verify")
                for r in finding["unclassified"]]

    # AND A CLASSIFICATION EXPIRES WHEN ITS GATE LANDS.
    #
    # This audit used to clear a requirement the moment its id appeared in the register,
    # and never asked whether the entry was still true. So five requirements sat ABSENT,
    # buildable_now, against a completing gate that had already landed — and the audit
    # reported zero unaccounted over the top of them. "Absent, due at M4-C" stops being a
    # plan and becomes a false statement the moment M4-C lands.
    #
    # tools/partial_closures.py has enforced the same rule on the register since M4-A
    # (PARTIAL_CLOSURE_CLOSED_FROM_THE_FUTURE: an entry still open after its completer
    # landed is a defect). The coverage audit simply did not honour it. Same rule, second
    # register.
    # partial_closures.landed_gates(), not the one above: entries name a SLICE ("M4-C")
    # and this module's landed_gates() closes over GATES ("M4"), so asking it whether
    # M4-C has landed answers no about a slice that shipped three commits ago. The
    # register's own reader knows both, and it is the reader the sibling rule uses.
    landed = partial_closures.landed_gates()
    for identifier, entry in sorted(finding["recorded"].items()):
        if entry.get("state") != "absent":
            continue
        gate = entry.get("completing_gate")
        if gate in landed:
            problems.append((
                "ABSENT_AT_A_LANDED_GATE",
                f"{identifier} is classified ABSENT with {gate} as its completing gate, "
                f"and {gate} has landed. Either it was built and this entry is stale, or "
                f"it was not built and the gate closed over a hole. Build it, or move it "
                f"to a gate that has not landed and record why — the completer-moved-"
                f"later rule applies to that move"))
    return problems


def report(logs: Path) -> str:
    finding = audit(logs)
    lines: list[str] = []
    graded: dict[str, list[str]] = {}
    for identifier, grade, _requirement in finding["delivered"]:
        graded.setdefault(grade, []).append(identifier)

    lines.append(f"landed requirements   : {finding['landed']}")
    for grade in GRADES:
        held = graded.get(grade, [])
        note = {
            "proved-red": "citation on a control this run showed red, then green",
            "ran": "citation on a check that RAN — not shown able to fail",
            "ci-step": "citation in a workflow step, which fails the build on non-zero",
        }[grade]
        lines.append(f"  delivered, {grade:<10}: {len(held):>3}   ({note})")
    lines.append(f"  covered by an open entry: {len(finding['open_entries']):>3}")
    lines.append(f"  classified gaps        : "
                 f"{len(finding['unaccounted']) - len(finding['unclassified']):>3}")
    lines.append(f"  UNCLASSIFIED           : {len(finding['unclassified']):>3}")

    urgent = [e for e in finding["recorded"].values()
              if e["state"] == "absent" and e["category"] in URGENT]
    if urgent:
        lines.append("")
        lines.append(f"absent in money, security or authority ({len(urgent)}):")
        for entry in sorted(urgent, key=lambda e: e["requirement"]):
            lines.append(f"  {entry['requirement']:<14} -> {entry['completing_gate']:<5} "
                         f"{entry['why'][:96]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(
        description="Every landed requirement is delivered or accounted for (FR-GOV-004).")
    parser.add_argument("--logs", required=True, type=Path,
                        help="directory of recorded suite output from this run")
    parser.add_argument("--report", action="store_true",
                        help="print the coverage summary as well as the verdict")
    args = parser.parse_args(argv)

    try:
        failures = check(args.logs)
        if args.report:
            print(report(args.logs))
    except (CoverageUnreadable, partial_closures.RegisterUnreadable,
            control_registry.ControlDrift) as refused:
        print(f"FAIL {type(refused).__name__}: {refused}")
        return 1

    if failures:
        for signature, detail in failures:
            print(f"FAIL {signature}: {detail}")
        return 1
    print("PASS REQUIREMENT_COVERAGE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
