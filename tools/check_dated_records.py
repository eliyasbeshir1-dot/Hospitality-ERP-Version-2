#!/usr/bin/env python3
"""A DESCRIPTION must be derived. A RECORD must be anchored. Neither may be neither.

THE RULE THIS FILE EXISTS TO STATE, because the next person to write a document in this
repository will meet it here:

  A document that describes the repository AS IT IS must be generated from the
  repository, and locked, so that it fails the build when it stops being true.
  planning/CI_TEST_MATRIX.md, README.md, schema/SCHEMA_CATALOG.md,
  planning/ARCHITECTURE_CONFORMANCE_PLAN.md and evidence/M1_EVIDENCE_REPORT.md are that
  kind. Each has a generator and an equality check in CI.

  A document that RECORDS WHAT HAPPENED — a verification run on a named machine, a
  limitation found on a date — must NOT be derived, because deriving it would rewrite the
  past into the present and destroy the evidence. "Every command was executed on Linux
  6.18.44 with 220 checks" is not a claim that can be regenerated; regenerating it would
  turn a record into a claim about today, which is falsification rather than locking.

  What a record owes instead is an ANCHOR. A number in a record is only honest when it
  says what it is a number ABOUT. "220 checks" reads as a statement about the system and
  goes stale the moment a suite grows. "220 checks at 3758ac3 on 26 August 2026" is a
  fact that stays true forever, because it is pinned to a state anybody can go and fetch.

Three rules, and the third is the one a checksum would not have caught:

  DATED_RECORD_UNANCHORED
      a section of a dated record states a count or names a gate and carries no anchor.
      This is the rule that matters: planning/CI_TEST_MATRIX.md was never edited, it was
      left behind while the world moved, and a hash lock would have passed it every time.

  DATED_RECORD_COMMIT_ABSENT
      a record names a commit that does not resolve in this repository. A record anchored
      to a commit nobody can fetch is not anchored; it only looks it. This has happened
      twice in this project's history.

  DATED_RECORD_UNDECLARED
      a file listed here as a dated record does not declare itself one, or a file that
      declares itself one is not listed. Fail closed both ways: a record that stopped
      declaring itself would leave the checker with nothing to check and report success.

Usage:
    python3 tools/check_dated_records.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

REPO = Path(__file__).resolve().parents[1]

# The dated records this repository holds. Listed, and each must also declare itself, so
# neither the list nor the file can silently stop being a record.
DATED_RECORDS = [
    "planning/KNOWN_LIMITATIONS.md",
    "docs-local/CROSS_PLATFORM_COMMANDS.md",
    "planning/M0R_MIGRATION_RECORD.md",
]

DECLARATION = "<!-- dated-record -->"

# An anchor: a short git object name in backticks, and a date. Both, in one line, so a
# reader never has to go looking for which commit a number belongs to.
ANCHOR = re.compile(r"`([0-9a-f]{7,40})`[^\n]*?\b(\d{1,2} \w+ \d{4})\b")

# What makes a section need one: a count of something this repository can grow, or a gate
# tag. Deliberately narrow — "PostgreSQL 16.13" is a version, not a claim that goes stale
# in the way "60 checks" does, and a rule wide enough to catch it would fire on every
# sentence with a digit in it.
NEEDS_ANCHOR = re.compile(
    r"\b\d+\s+(?:checks?|suites?|jobs?|controls?|steps?|files?|projections?|terms?|"
    r"migrations?|entries|journeys?)\b|\bM0R\b|\bM[1-6][ab]?(?:-[A-Z])?\b")


def git_has(commit: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(REPO), "cat-file", "-e", f"{commit}^{{commit}}"],
        capture_output=True).returncode == 0


def sections(text: str) -> list[tuple[str, str]]:
    """(heading, body) for every heading in the file, plus the preamble under its title."""
    parts: list[tuple[str, str]] = []
    current, buffer = "(preamble)", []
    for line in text.splitlines():
        if re.match(r"^#{1,6} ", line):
            parts.append((current, "\n".join(buffer)))
            current, buffer = line.lstrip("# ").strip(), [line]
        else:
            buffer.append(line)
    parts.append((current, "\n".join(buffer)))
    return parts


def check() -> list[tuple[str, str]]:
    failures: list[tuple[str, str]] = []
    listed = set(DATED_RECORDS)

    declared = set()
    for path in sorted(REPO.glob("**/*.md")):
        if any(part in {"docs", "node_modules", ".git"} for part in path.parts):
            continue
        if DECLARATION in path.read_text(encoding="utf-8"):
            declared.add(path.relative_to(REPO).as_posix())

    for undeclared in sorted(listed - declared):
        failures.append((
            "DATED_RECORD_UNDECLARED",
            f"{undeclared} is listed as a dated record and does not declare itself one. "
            f"Add {DECLARATION} at the top, so a reader meets the distinction before the "
            f"content and this checker cannot be silenced by a rename"))
    for unlisted in sorted(declared - listed):
        failures.append((
            "DATED_RECORD_UNDECLARED",
            f"{unlisted} declares itself a dated record and is not listed in "
            f"{Path(__file__).name}. A record nothing checks is a record that can go "
            f"stale exactly like the documents this rule was written for"))

    for relative in DATED_RECORDS:
        path = REPO / relative
        if not path.exists():
            failures.append((
                "DATED_RECORD_UNDECLARED",
                f"{relative} is listed as a dated record and does not exist"))
            continue
        text = path.read_text(encoding="utf-8")

        for commit in sorted({m.group(1) for m in ANCHOR.finditer(text)}):
            if not git_has(commit):
                failures.append((
                    "DATED_RECORD_COMMIT_ABSENT",
                    f"{relative} anchors to commit {commit}, which does not resolve in "
                    f"this repository. A record anchored to a commit nobody can fetch is "
                    f"not anchored, it only looks it"))

        for heading, body in sections(text):
            stale = NEEDS_ANCHOR.search(body)
            if not stale:
                continue
            if ANCHOR.search(body):
                continue
            failures.append((
                "DATED_RECORD_UNANCHORED",
                f"{relative} — the section {heading!r} says {stale.group(0)!r} and "
                f"carries no anchor. A count or a gate in a record reads as a claim about "
                f"the system unless it says what state it is a count OF. Add the commit "
                f"and the date it describes, in one line, in this section"))

    return failures


def main() -> int:
    failures = check()
    for signature, detail in failures:
        print(f"FAIL {signature}: {detail}")
    if failures:
        return 1
    print(f"PASS DATED_RECORDS — {len(DATED_RECORDS)} record(s): each declares itself, "
          f"each anchors every count and gate it states to a commit that resolves and a "
          f"date. A description is derived; a record is anchored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
