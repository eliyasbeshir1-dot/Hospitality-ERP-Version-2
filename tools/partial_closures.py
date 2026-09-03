#!/usr/bin/env python3
"""The partial-closure register, and the six ways it is allowed to fail the build.

A partial closure is a requirement this repository has closed as far as the artifacts of
its own gate allow, with the gate or slice that completes it named. The mechanism exists
because the alternative — a completion claim that is silent about known gaps — is the
drift class the M2-C README finding was about.

Three rules were enough while every entry was open. M3-B is the first gate at which
entries actually COME DUE, and that exposed a hole: the original checker skipped any
entry whose state was not "open", so writing state: "done" — or "banana" — silenced it
completely. Closing was therefore indistinguishable from suppressing, which is the
failure this register exists to prevent, one level up. A closure is now a claim that has
to be earned: it names the slice that closed it, that slice must have LANDED, and it
carries the evidence. Three more rules, all structural, all derived from sources this
file does not own:

  PARTIAL_CLOSURE_UNCOMPLETED
      an entry that names no completing gate. "Partially closed" without a completer is
      a note to nobody.

  PARTIAL_CLOSURE_GATE_UNKNOWN
      an entry naming a gate the requirements register does not have. Derived from the
      introduced_at and revalidated_at values in the pinned docs package, so a typo or an
      invented milestone stops the build rather than sitting in the file looking official.

  PARTIAL_CLOSURE_NOT_REVISITED
      an entry still marked open whose completing gate HAS LANDED. This is the failure
      that actually happens: the completer arrives, nobody goes back, and the record says
      "partial" forever. Landing is read from the repository — a gate has landed when the
      suite that verifies it exists — so M3-B landing forces FR-ORD-006 to be re-examined
      whether or not anybody remembers.

  PARTIAL_CLOSURE_STATE_UNKNOWN
      an entry whose state is neither "open" nor "closed". Fail closed: the original
      checker treated every unrecognised state as "nothing to see", so a typo was a
      silencer.

  PARTIAL_CLOSURE_CLOSED_WITHOUT_EVIDENCE
      an entry marked closed that does not name the slice which closed it and what now
      proves it. "Closed" with no account of how is the same empty claim as "partial"
      with no completer.

  PARTIAL_CLOSURE_CLOSED_FROM_THE_FUTURE
      an entry closed by a slice that has not landed. Nothing can be closed by work that
      does not exist yet, and this is the shape a premature tick would take.

  PARTIAL_CLOSURE_COMPLETER_INCOMPLETE
      a CLOSED entry resting on a requirement that is itself incomplete. Added at M4-B,
      because M4-A closed FR-ORD-003 and FR-ORD-005 by naming FR-CFG-001C as the thing
      that completed them while FR-CFG-001C's own "permitted payment methods" clause was
      unbuildable and unrecorded. Both closures were honest about themselves and the chain
      underneath them was not: the register said done, and one link down was a requirement
      nobody had finished.

      The completer set is DERIVED — every distinct completed_by in the register — so a
      completer a later gate introduces is covered without anybody extending anything.
      An entry closed by a requirement that carries an open entry of its own must name
      completer_aspect: WHICH part of the completer it rests on. That string is then
      required to differ from every open aspect of that completer. It is not
      self-certification, because the register holds the other half: the writer says which
      part, and the register knows which parts are still missing.

      WHAT THIS RULE DOES NOT COVER, stated here because a reader should meet the boundary
      rather than infer it: it checks NAMED COMPLETERS, not every requirement whose gate
      has landed. A requirement that is partly built and that no entry points at is
      invisible to it. That larger audit — every landed requirement either delivered in
      full or carrying an entry — is the correct rule in general and is recorded as a
      partial closure against M4-C, so it comes due where a gate is closing rather than
      where payment capture is being written.

  PARTIAL_CLOSURE_COMPLETER_MOVED_LATER
      an entry whose completing gate has been moved to a LATER one without a recorded
      reason. Added at M4-A, the first gate at which a completer was edited rather than
      satisfied, and it exists because that is the power somebody would abuse: an entry
      about to come due can be sent to the next gate, and then the next, and it never
      comes due at all. Moving a completer EARLIER is not policed — it brings work
      forward and closes sooner. Moving it later is the direction that hides work, so it
      costs a sentence in the entry saying why.

      The previous value is read from the register's OWN GIT HISTORY, not declared: an
      entry cannot avoid the rule by forgetting to mention that it moved. Gate order
      comes from the pinned package's milestone list, and the slice letter orders within
      a gate, so M4-A precedes M4-B precedes M5a without this file holding an opinion
      about which gate follows which.

Standard library only. Fails closed: a register it cannot read or parse is an error, not
an empty list.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console import use_utf8_output  # noqa: E402

# Stated, not inherited. A Windows console decodes with cp1252 unless told otherwise, and
# this file prints requirement text that contains em dashes — M1-A scans every entry point
# for exactly this and found this one missing it.
use_utf8_output()

REPO = Path(__file__).resolve().parents[1]
REGISTER = REPO / "planning" / "partial_closures.json"
DOCS = REPO / "docs"
TESTS = REPO / "tests"

SLICE_SUFFIX = re.compile(r"^(?P<gate>[A-Za-z0-9]+)(?:-(?P<slice>[A-Z]))?$")


class RegisterUnreadable(Exception):
    """The register or the requirements package could not be read.

    Raised rather than returning an empty list. A checker that treats an unreadable
    register as "no partial closures" reports success for a repository it never looked at.
    """


def _requirements_path() -> Path:
    matches = sorted(DOCS.glob("*/02_MACHINE_READABLE/requirements.json"))
    if not matches:
        raise RegisterUnreadable(
            "no requirements.json under docs/; the gate register cannot be derived and "
            "no completing gate can be validated")
    return matches[0]


def known_gates() -> set[str]:
    """Every gate the pinned requirements package names, from the package itself."""
    try:
        payload = json.loads(_requirements_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegisterUnreadable(f"requirements.json could not be parsed: {exc}") from exc

    gates: set[str] = set()
    for requirement in payload.get("active_requirements", []):
        introduced = requirement.get("introduced_at")
        if introduced:
            gates.add(introduced)
        for gate in requirement.get("revalidated_at") or []:
            gates.add(gate)
    if not gates:
        raise RegisterUnreadable(
            "requirements.json named no gates at all; a register that validated every "
            "completer against an empty set would validate nothing")
    return gates


def landed_gates(gates: set[str] | None = None) -> set[str]:
    """The gates and slices this repository actually has, read off the tests directory.

    A slice has landed when its verification suite exists: tests/m3b/verify_m3b.py means
    M3-B is here. A gate has landed when any of its slices has. Derived rather than
    listed, for the same reason the README slice list is derived — a hardcoded list is a
    list that drifts.

    The one ambiguity is a directory like tests/m5a: "M5a" is itself a milestone in the
    requirements register, while "m2a" is slice A of gate M2. It is resolved by ASKING
    THE REGISTER rather than by a rule invented here — if the whole name is a gate the
    package knows, it is a gate; otherwise the trailing letter is a slice.
    """
    gates = known_gates() if gates is None else gates
    landed: set[str] = set()
    if not TESTS.is_dir():
        raise RegisterUnreadable(f"{TESTS} is not a directory; landing cannot be derived")

    for suite in sorted(TESTS.iterdir()):
        if not suite.is_dir() or not (suite / f"verify_{suite.name}.py").is_file():
            continue
        match = re.fullmatch(r"m([0-9]+)([a-z])?", suite.name)
        if not match:
            continue
        number, letter = match.groups()
        whole = {g for g in gates if g.lower() == suite.name}
        if whole:
            landed |= whole
            continue
        landed.add(f"M{number}")
        if letter:
            landed.add(f"M{number}-{letter.upper()}")
    return landed


def gate_order() -> list[str]:
    """The gates in the order the PINNED PACKAGE lists them.

    Read from the package's milestone list rather than written here, for the same reason
    known_gates() is: an order this file held an opinion about would be a second source
    of truth that could disagree with the package about what follows what.
    """
    path = _requirements_path().parent / "implementation_manifest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegisterUnreadable(
            f"{path.name} could not be parsed, so no gate order can be derived: "
            f"{exc}") from exc
    order = [m["gate"] for m in payload.get("milestones", []) if m.get("gate")]
    if not order:
        raise RegisterUnreadable(
            f"{path.name} lists no milestone, so gate order cannot be derived. An order "
            f"derived from nothing would rank every completer equal and the "
            f"moved-later rule would never fire")
    return order


def completer_rank(completer: str) -> tuple[int, str]:
    """When a completer COMES DUE: its gate's position, then its slice letter.

    A bare gate ranks as that gate's FIRST slice, and the reason is landed_gates(): a
    gate is landed when any of its slices is, so an entry naming the bare gate M4 comes
    due the moment tests/m4a exists. M4 and M4-A therefore come due together and
    refining one to the other moves nothing — which is what makes M4 -> M4-B a genuine
    move later and M4 -> M4-A not a move at all.

    The first draft ranked a bare gate BEFORE its slices, on the reasoning that a gate is
    a wider promise than a slice inside it. That reasoning is about scope and this
    comparison is about time, and it made all eight refinements to M4-A report as moves
    later. Its own red test caught it.
    """
    order = gate_order()
    match = SLICE_SUFFIX.fullmatch(completer)
    gate = match.group("gate") if match else completer
    try:
        position = order.index(gate)
    except ValueError:
        raise RegisterUnreadable(
            f"completer {completer!r} names gate {gate!r}, which the package's milestone "
            f"list does not contain") from None
    letter = (match.group("slice") if match else None) or "A"
    return (position, letter)


def previous_completers() -> dict[tuple[str, str], str] | None:
    """What the register said about each entry at HEAD, keyed by (requirement, aspect).

    Read out of git rather than out of the file, because the whole point is to catch a
    change the file no longer remembers making. Returns None when the register has no
    committed version yet — a first commit has nothing to have moved from.
    """
    import subprocess
    relative = REGISTER.relative_to(REPO).as_posix()
    result = subprocess.run(
        ["git", "-C", str(REPO), "show", f"HEAD:{relative}"],
        capture_output=True, text=True)
    if result.returncode != 0:
        if "exists on disk, but not in" in result.stderr or "does not exist" in result.stderr:
            return None
        raise RegisterUnreadable(
            f"the committed register could not be read, so a moved completer cannot be "
            f"detected: {result.stderr.strip()[:200]}. Refusing rather than reporting "
            f"that nothing moved")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RegisterUnreadable(
            f"the committed register is not valid JSON: {exc}") from exc
    return {(e.get("requirement", ""), e.get("aspect", "")): (e.get("completing_gate") or "")
            for e in payload.get("partial_closures", [])}


def landing_evidence(completer: str) -> list[str]:
    """The suite directories that make `completer` landed, named rather than constructed.

    The path a reader should go and look at, derived from the filesystem the same way
    landed_gates() derives landing — so the message and the decision cannot disagree.
    """
    found = []
    for suite in sorted(TESTS.iterdir()):
        if not suite.is_dir() or not (suite / f"verify_{suite.name}.py").is_file():
            continue
        match = re.fullmatch(r"m([0-9]+)([a-z])?", suite.name)
        if not match:
            continue
        number, letter = match.groups()
        names = {f"M{number}"}
        if letter:
            names.add(f"M{number}-{letter.upper()}")
        names |= {g for g in known_gates() if g.lower() == suite.name}
        if completer in names:
            found.append(f"tests/{suite.name}")
    return found


def load() -> list[dict]:
    try:
        payload = json.loads(REGISTER.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegisterUnreadable(f"{REGISTER} does not exist") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RegisterUnreadable(f"{REGISTER} could not be parsed: {exc}") from exc

    entries = payload.get("partial_closures")
    if not isinstance(entries, list):
        raise RegisterUnreadable(
            f"{REGISTER} has no 'partial_closures' list; a register with no list is not "
            f"an empty register, it is a malformed one")
    return entries


def check(entries: list[dict] | None = None) -> list[tuple[str, str]]:
    """Every way the register is currently wrong, as (signature, detail) pairs.

    An empty list is the only thing that lets the build proceed.
    """
    entries = load() if entries is None else entries
    gates = known_gates()
    landed = landed_gates(gates)
    failures: list[tuple[str, str]] = []

    # What the register said last time, so a completer that moved cannot pretend it did
    # not. None means there is no committed version to compare against.
    previous = previous_completers()

    for index, entry in enumerate(entries):
        label = f"{entry.get('requirement', f'entry {index}')}" \
                f"{'/' + entry['aspect'] if entry.get('aspect') else ''}"
        completer = (entry.get("completing_gate") or "").strip()
        state = (entry.get("state") or "").strip()

        if not completer:
            failures.append((
                "PARTIAL_CLOSURE_UNCOMPLETED",
                f"{label} is recorded as partially closed and names no completing gate"))
            continue

        match = SLICE_SUFFIX.fullmatch(completer)
        gate = match.group("gate") if match else None
        if gate not in gates:
            failures.append((
                "PARTIAL_CLOSURE_GATE_UNKNOWN",
                f"{label} names completing gate {completer!r}, and the requirements "
                f"register has no gate {gate!r}"))
            continue

        # A completer that moved LATER has to say why, in the entry. Checked before the
        # state rules, because a closed entry can have been moved too — and moving one
        # later and closing it at the later slice is exactly the shape this catches.
        if previous is not None:
            was = previous.get((entry.get("requirement", ""), entry.get("aspect", "")))
            if was and was != completer:
                try:
                    moved_later = completer_rank(completer) > completer_rank(was)
                except RegisterUnreadable as exc:
                    failures.append(("PARTIAL_CLOSURE_GATE_UNKNOWN", f"{label}: {exc}"))
                    continue
                recorded = (entry.get("completer_moved") or {})
                stated = (recorded.get("why") or "").strip()
                if moved_later and not stated:
                    failures.append((
                        "PARTIAL_CLOSURE_COMPLETER_MOVED_LATER",
                        f"{label} moved its completer from {was} to {completer}, which is "
                        f"LATER, and records no reason. An entry about to come due can be "
                        f"sent to the next gate and then the next until it never comes due "
                        f"at all; that is the one thing this register cannot survive. Add "
                        f"completer_moved.why saying what makes {completer} the slice that "
                        f"genuinely completes it. Moving a completer EARLIER needs no "
                        f"reason — it brings the work forward."))
                    continue
                if moved_later and recorded.get("from", was) != was:
                    failures.append((
                        "PARTIAL_CLOSURE_COMPLETER_MOVED_LATER",
                        f"{label} records a move from {recorded.get('from')!r}, and the "
                        f"committed register says it was {was!r}. The reason describes a "
                        f"move that did not happen"))
                    continue

        if state not in ("open", "closed"):
            failures.append((
                "PARTIAL_CLOSURE_STATE_UNKNOWN",
                f"{label} has state {state!r}; the only states are 'open' and 'closed', "
                f"and anything else silences the entry rather than describing it"))
            continue

        if state == "closed":
            closed_by = (entry.get("closed_at") or "").strip()
            evidence = (entry.get("closed_by_evidence") or "").strip()
            if not closed_by or not evidence:
                failures.append((
                    "PARTIAL_CLOSURE_CLOSED_WITHOUT_EVIDENCE",
                    f"{label} is marked closed but names "
                    + " and ".join(
                        part for part, missing in
                        (("no closing slice", not closed_by),
                         ("no evidence", not evidence)) if missing)))
                continue

            closing = SLICE_SUFFIX.fullmatch(closed_by)
            if not closing or closing.group("gate") not in gates:
                failures.append((
                    "PARTIAL_CLOSURE_GATE_UNKNOWN",
                    f"{label} says it was closed at {closed_by!r}, and the requirements "
                    f"register has no such gate"))
                continue

            if closed_by not in landed:
                failures.append((
                    "PARTIAL_CLOSURE_CLOSED_FROM_THE_FUTURE",
                    f"{label} is marked closed at {closed_by}, which has not landed: "
                    f"there is no tests/{closed_by.lower().replace('-', '')}"))
            continue

        if completer in landed:
            # Name what ACTUALLY landed. This message used to construct the path from the
            # entry's own text — "its completing gate M4 has landed: tests/m4 exists" —
            # and tests/m4 does not exist and never will: what landed was tests/m4a, and
            # a gate is landed when any of its slices is. A diagnostic must not name a
            # cause it did not verify, and this one sent a reader to look for a directory
            # that was not there.
            evidence = ", ".join(landing_evidence(completer)) or (
                "a suite this check could not name, which is itself a defect")
            failures.append((
                "PARTIAL_CLOSURE_NOT_REVISITED",
                f"{label} is still open and its completing gate {completer} has landed. "
                f"What landed: {evidence}. A gate is landed when ANY of its slices is, "
                f"so an entry naming a bare gate comes due on that gate's first slice. "
                f"The completer arrived and the record was never revisited"))

    failures.extend(completer_completeness(entries))
    return failures


def open_aspects_by_requirement(entries: list[dict]) -> dict[str, set[str]]:
    """{requirement: {aspect, ...}} over the entries still open.

    Derived from the register rather than declared, so a requirement that becomes
    partially closed at M5a joins this map without anybody editing a list.
    """
    out: dict[str, set[str]] = {}
    for entry in entries:
        if (entry.get("state") or "").strip() != "closed":
            requirement = (entry.get("requirement") or "").strip()
            if requirement:
                out.setdefault(requirement, set()).add(
                    (entry.get("aspect") or "").strip())
    return out


def completer_completeness(entries: list[dict]) -> list[tuple[str, str]]:
    """A closed entry may not rest on a requirement that is itself incomplete.

    The completer set is every distinct completed_by in the register — derived, never
    listed — so this covers a completer introduced by a gate that does not exist yet.
    """
    failures: list[tuple[str, str]] = []
    still_open = open_aspects_by_requirement(entries)

    for index, entry in enumerate(entries):
        if (entry.get("state") or "").strip() != "closed":
            continue
        completer = (entry.get("completed_by") or "").strip()
        if not completer:
            continue

        gaps = still_open.get(completer)
        if not gaps:
            continue                      # the completer carries no open entry: complete

        label = f"{entry.get('requirement', f'entry {index}')}" \
                f"{'/' + entry['aspect'] if entry.get('aspect') else ''}"
        rests_on = (entry.get("completer_aspect") or "").strip()

        if not rests_on:
            failures.append((
                "PARTIAL_CLOSURE_COMPLETER_INCOMPLETE",
                f"{label} is closed by {completer}, and {completer} is itself only "
                f"partly delivered — it carries open entr(ies) for "
                f"{sorted(a or '(unnamed)' for a in gaps)}. A closure resting on an "
                f"unfinished requirement makes the register overstate: this entry reads "
                f"done, and one link down is work nobody has finished. Name "
                f"completer_aspect saying WHICH part of {completer} this rests on, and "
                f"it must not be one of the parts still open."))
            continue

        if rests_on in gaps:
            failures.append((
                "PARTIAL_CLOSURE_COMPLETER_INCOMPLETE",
                f"{label} says it rests on {completer}'s {rests_on!r}, and that is "
                f"exactly the aspect of {completer} still recorded as open. The entry "
                f"names the gap it is standing on."))

    return failures


def main() -> int:
    try:
        entries = load()
        failures = check(entries)
    except RegisterUnreadable as exc:
        print(f"FAIL PARTIAL_CLOSURE_REGISTER_UNREADABLE: {exc}")
        return 1

    for signature, detail in failures:
        print(f"FAIL {signature}: {detail}")
    if failures:
        return 1

    closed = [e for e in entries if (e.get("state") or "").strip() == "closed"]
    print(f"PASS PARTIAL_CLOSURES — {len(entries)} entr(ies): "
          f"{len(entries) - len(closed)} open, {len(closed)} closed. Every open entry "
          f"names a completing gate the requirements register has and none has landed; "
          f"every closed entry names the landed slice that closed it and its evidence")
    return 0


if __name__ == "__main__":
    sys.exit(main())
