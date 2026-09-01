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
            failures.append((
                "PARTIAL_CLOSURE_NOT_REVISITED",
                f"{label} is still open and its completing gate {completer} has landed: "
                f"tests/{completer.lower().replace('-', '')} exists. The completer "
                f"arrived and the record was never revisited"))

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
