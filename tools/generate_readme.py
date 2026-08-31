#!/usr/bin/env python3
"""Generate README.md from planning/README_NARRATIVE.md and the repository itself.

The README went stale twice — it claimed only slice A had run, and cited migrations
0001-0003 while 0004 was committed. Both times the stale part was a list that the
repository already knew: which migrations exist, which slices landed, which suites there
are. A hand-maintained copy of a fact the filesystem already holds is a copy that will
diverge, so those lists are now derived and CI fails if the committed README differs from
a fresh generation.

The prose is held here as constants. That part is a judgement, not a fact to discover.

Usage:
    python3 tools/generate_readme.py --out README.md
    python3 tools/generate_readme.py --check README.md
"""
from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console import use_utf8_output  # noqa: E402

use_utf8_output()


sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_history import (  # noqa: E402
    HistoryUnavailable, assert_history_available, commit_for_subject_prefix,
)

REPO = Path(__file__).resolve().parents[1]
PACKAGE_SHA = "b89a2d4211356be5941dc25ff2dc540728c87ed761ffd9894a3f2691ccf5b590"

# What each slice delivered. WHICH slices exist is not written here — it is derived from
# the repository, because a hand-maintained list is exactly what went wrong.
#
# This list stopped at M2-A while M2-B and M2-C were in the tree, so the README said the
# gate was complete through M2-A and that menus and guest sessions were still absent. The
# equality lock in CI passed the whole time, because it compares the artifact to the
# generator and both were stale together: a lock that compares a document to its own
# source of truth goes green on a false document whenever the source of truth is wrong.
#
# Now the slice tags come from the verification suites in tests/, and a tag with no entry
# below stops the generator instead of being quietly omitted. Same shape as the
# SUITE_UNDESCRIBED failure below, and for the same reason.
SLICE_DELIVERS = {
    "M0R":  "repository conformance: docs, plans, CI, no code",
    "M1-A": "PostgreSQL, migration 0001, organizational model, row level security",
    "M1-B": "identity, memberships, sessions, step-up authentication, service principals",
    "M1-C": "configuration, audit, exact money and quantity, numbering, retention",
    "M1-D": "cloud API, security controls, operations, evidence",
    "M2-A": "menu, pricing, availability, dayparts and translation storage",
    "M2-B": "tables, QR resolution, guest sessions, carts, allergens and dietary safety",
    "M2-C": "the customer surface: three locales, Arabic right-to-left, accessibility",
}

# The gates in order, and what each one brings that does not exist yet. Rows are emitted
# only for gates with nothing landed, so "still absent" stops claiming a thing is absent
# the moment its first slice appears in tests/.
GATE_ORDER = ["M0", "M0R", "M1", "M2", "M3", "M4", "M5a", "M5b", "M6"]

GATE_DELIVERS = {
    "M2":  "Menu, translations, QR-bound tables, guest sessions",
    "M3":  "Orders, tickets, service requests",
    "M4":  "Checks, payments, tips, receipts",
    "M5a": "Outlet node, synchronization, printing",
    "M5b": "Same-QR DNS/TLS, authority lease",
    "M6":  "Multi-region distribution",
}

DIRECTORY_PURPOSE = {
    "api": "the cloud API — Fastify and TypeScript, M1 surface only",
    "docs": "the approved v2.0.9 package, byte-identical and verified by its own `SHA256SUMS.txt`",
    "docs-local": "cross-platform command reference",
    "evidence": "`M1_EVIDENCE_REPORT.md`, generated from the repository, database and suite logs",
    "migrations": "ordered, checksum-locked SQL history beginning at `0001`",
    "planning": "architecture conformance, migration ownership, CI matrix, known limitations",
    "schema": "`SCHEMA_CATALOG.md`, generated from the live database, never hand-written",
    "seeds": "demonstration tenants and reason-code sets, with their own ordered record",
    "tests": "verification suites, one per slice, plus the fenced-domain gate suite",
    "tools": "migration and seed runners, generators, and the forbidden-surface verifier",
}

SUITE_PURPOSE = {
    "m1a": "database, organizational model, row level security, production roles",
    "m1b": "identity, memberships, sessions, step-up authentication",
    "m1c": "configuration, audit, money exactness, numbering, retention",
    "m1d": "the running API, security controls, operations, evidence",
    "m2a": "menu structure, pricing, availability, dayparts, translation storage",
    "m2b": "tables, QR, guest sessions, carts, allergens and dietary safety",
    "m2c": "the customer surface rendered in a real browser: three locales, Arabic "
           "right-to-left, accessibility and performance budgets",
    "fenced_gate": "the forbidden-surface gate itself: vocabulary provenance and mutation coverage",
}


def sh(*command: str) -> str:
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", cwd=REPO).stdout.strip()


def slice_commit(tag: str) -> str:
    """The commit that landed a slice, found by its subject line.

    "unreleased" is only ever a truthful answer about a slice that has not landed. It is
    never a stand-in for a history this process could not read — assert_history_available()
    has already refused in that case.
    """
    return commit_for_subject_prefix(f"{tag}:") or "unreleased"


def slice_tags() -> list[str]:
    """Which slices exist, according to the repository rather than to this file.

    A slice is a thing with a verification suite: tests/m2c/verify_m2c.py means M2-C
    happened, and no amount of forgetting to update a list here can make that untrue.
    M0R is included explicitly because it predates the suite convention — its verifier is
    tools/verify_m0r_skeleton.py, kept as historical evidence — and because a gate that
    produced no code cannot be discovered by looking for code.
    """
    tags = ["M0R"]
    for path in sorted((REPO / "tests").glob("*/verify_*.py")):
        matched = re.fullmatch(r"m(\d)([a-z])", path.parent.name)
        if matched:
            tags.append(f"M{matched.group(1)}-{matched.group(2).upper()}")
    return tags


class SliceUndescribed(RuntimeError):
    """A slice exists in the repository and this generator has nothing to say about it."""


NARRATIVE = REPO / "planning" / "README_NARRATIVE.md"


def build() -> str:
    """Substitute derived facts into the governance narrative.

    The prose lives in planning/ because it is governance: it names fenced domains in
    order to prohibit them, which is legitimate there and nowhere else. This file holds no
    prose of its own, so it needs no such licence.
    """
    # Ask first whether the question is answerable. Under a shallow checkout every slice
    # would resolve to "unreleased" and the gate would fall back to the earliest one — a
    # plausible document that is entirely wrong.
    assert_history_available()

    template = NARRATIVE.read_text(encoding="utf-8")
    # Strip the maintainer note at the top of the narrative; it explains the file to an
    # editor, not the repository to a reader.
    if template.startswith("<!--"):
        template = template[template.index("-->") + 3:].lstrip("\n")

    migrations = sorted((REPO / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    seeds = sorted((REPO / "seeds").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    suites = sorted(p for p in (REPO / "tests").glob("*/verify_*.py"))

    tags = slice_tags()
    undescribed = [tag for tag in tags if tag not in SLICE_DELIVERS]
    if undescribed:
        # Loud, not silent. The previous shape of this generator simply did not mention a
        # slice it had never heard of, which is how the README came to describe a gate two
        # slices behind the repository while its equality lock stayed green.
        raise SliceUndescribed(
            f"{', '.join(undescribed)} has a verification suite and no entry in "
            f"SLICE_DELIVERS. Add one: the README must say what a slice delivered, and a "
            f"slice the repository knows about cannot be left out of the document that "
            f"describes the repository.")

    landed = [(tag, SLICE_DELIVERS[tag], slice_commit(tag)) for tag in tags]
    if all(commit == "unreleased" for _tag, _note, commit in landed):
        # A full history that resolves no slice at all means the derivation is broken,
        # not that nothing has ever shipped.
        raise HistoryUnavailable(
            "no slice resolved to a commit in a non-shallow history — "
            "the subject-line convention or the history itself has changed")
    current = next((t for t, _n, c in reversed(landed) if c != "unreleased"), "M0R")

    slice_table = ["| Slice | Delivered | Commit |", "|---|---|---|"]
    for tag, note, commit in landed:
        slice_table.append(f"| **{tag}** | {note} | `{commit}` |")

    # Which gates have landed anything, derived from the slice tags above. "M2-C" lands
    # gate "M2"; the sequence and the still-absent table both read this rather than
    # stating it.
    landed_gates = {tag.split("-")[0] for tag, _n, commit in landed if commit != "unreleased"}
    current_gate = current.split("-")[0]

    missing_gate_note = [g for g in GATE_ORDER
                         if g not in landed_gates and g not in ("M0", "M0R")
                         and g not in GATE_DELIVERS]
    if missing_gate_note:
        raise SliceUndescribed(
            f"{', '.join(missing_gate_note)} has not landed and GATE_DELIVERS does not say "
            f"what it brings, so the still-absent table would silently omit it")

    absent_table = ["| Absent | Arrives at |", "|---|---|"]
    for gate in GATE_ORDER:
        if gate in landed_gates or gate in ("M0", "M0R"):
            continue
        absent_table.append(f"| {GATE_DELIVERS[gate]} | {gate} |")

    # The gate sequence, with the frontier marked. A gate BEHIND the current one is shown
    # complete because this project does not begin a gate until the previous one has been
    # independently reviewed and approved — every brief says so, and every slice here
    # started that way. That inference is the only thing in this line the repository
    # cannot show directly, and it is why it is written down.
    sequence = []
    for gate in GATE_ORDER:
        if gate in ("M0", "M0R"):
            sequence.append(gate)
            continue
        letters = sorted(tag.split("-")[1] for tag, _n, c in landed
                         if c != "unreleased" and tag.startswith(f"{gate}-"))
        if gate == current_gate and letters:
            sequence.append(f"**{gate} ({', '.join(letters)} — landed, in review)**")
        elif letters:
            sequence.append(f"**{gate} ({', '.join(letters)} — complete)**")
        else:
            sequence.append(gate)

    layout = ["| Path | Contents |", "|---|---|"]
    for name in sorted(DIRECTORY_PURPOSE):
        if (REPO / name).is_dir():
            layout.append(f"| `{name}/` | {DIRECTORY_PURPOSE[name]} |")

    suite_table = ["| Suite | Covers |", "|---|---|"]
    for path in suites:
        # as_posix(), not str(): this file is checksum-locked and CI regenerates it to
        # compare byte for byte. str() on a Windows Path yields backslashes, so the
        # README a Windows run produced differed from the committed one in every suite
        # row — a generated artefact must not record which platform generated it.
        relative = path.relative_to(REPO).as_posix()
        # A suite with no description used to render as the word "verification", which
        # reads like a description and is not one. M2-A landed and said exactly that for
        # a gate, unnoticed, because a default filled the hole. Missing text is a fault
        # in this generator, not a row.
        if path.parent.name not in SUITE_PURPOSE:
            raise SystemExit(
                f"FAIL SUITE_UNDESCRIBED: {relative} has no entry in SUITE_PURPOSE. Add "
                f"one; the README must say what a suite covers, not that it verifies.")
        suite_table.append(f"| `{relative}` | {SUITE_PURPOSE[path.parent.name]} |")

    substitutions = {
        # The milestone is read from the last slice that landed, not written here. It said
        # "M1" while the table already listed an M2 slice, which is the same shape of
        # defect as a hardcoded schema list: a fact stated in two places, one of which
        # stops being updated.
        "{{GATE_STATUS}}": (f"{current.split('-')[0]} — complete through **{current}**, "
                            f"awaiting independent review as a whole"),
        "{{PACKAGE_SHA}}": PACKAGE_SHA,
        "{{SLICE_TABLE}}": "\n".join(slice_table),
        "{{ABSENT_TABLE}}": "\n".join(absent_table),
        "{{GATE_SEQUENCE}}": " → ".join(sequence) + ".",
        "{{LAYOUT_TABLE}}": "\n".join(layout),
        "{{MIGRATIONS}}": "\n".join(f"- `{p.name}`" for p in migrations),
        "{{SEEDS}}": "\n".join(f"- `{p.name}`" for p in seeds),
        "{{SUITES}}": "\n".join(suite_table),
    }
    for marker, value in substitutions.items():
        if marker not in template:
            raise SystemExit(f"marker {marker} is absent from {NARRATIVE.name}")
        template = template.replace(marker, value)

    if "{{" in template:
        raise SystemExit("an unsubstituted marker remains in the narrative")
    return template


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate README.md from the repository.")
    ap.add_argument("--out")
    ap.add_argument("--check")
    args = ap.parse_args()

    try:
        generated = build()
    except HistoryUnavailable as error:
        print("FAIL GIT_HISTORY_UNAVAILABLE", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1
    except SliceUndescribed as error:
        # A named failure, not a traceback: this is the one a contributor will hit after
        # adding a slice, and it should read like the tool's other refusals.
        print("FAIL SLICE_UNDESCRIBED", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1

    if args.check:
        path = Path(args.check)
        if not path.exists():
            print(f"FAIL README_ABSENT — {path} does not exist", file=sys.stderr)
            return 1
        if path.read_text(encoding="utf-8") != generated:
            print("FAIL README_DRIFT — the committed README does not match a fresh generation",
                  file=sys.stderr)
            diff = list(difflib.unified_diff(
                path.read_text(encoding="utf-8").splitlines(), generated.splitlines(),
                fromfile="committed", tofile="generated", lineterm="", n=1))
            for line in diff[:40]:
                print(f"  {line}", file=sys.stderr)
            if len(diff) > 40:
                print(f"  … {len(diff) - 40} more line(s)", file=sys.stderr)
            return 1
        print("PASS README_MATCHES_REPOSITORY")
        print(f"  {len(generated.splitlines())} lines verified against the repository")
        return 0

    if args.out:
        Path(args.out).write_text(generated, encoding="utf-8")
        print(f"wrote {args.out} ({len(generated.splitlines())} lines)")
        return 0

    sys.stdout.write(generated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
