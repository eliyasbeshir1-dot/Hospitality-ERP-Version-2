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
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE_SHA = "b89a2d4211356be5941dc25ff2dc540728c87ed761ffd9894a3f2691ccf5b590"

# Slice tag -> what it delivered. The commit for each is discovered from git history.
SLICES = [
    ("M0R", "repository conformance: docs, plans, CI, no code"),
    ("M1-A", "PostgreSQL, migration 0001, organizational model, row level security"),
    ("M1-B", "identity, memberships, sessions, step-up authentication, service principals"),
    ("M1-C", "configuration, audit, exact money and quantity, numbering, retention"),
    ("M1-D", "cloud API, security controls, operations, evidence"),
]

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
    "fenced_gate": "the forbidden-surface gate itself: vocabulary provenance and mutation coverage",
}


def sh(*command: str) -> str:
    return subprocess.run(command, capture_output=True, text=True, cwd=REPO).stdout.strip()


def slice_commit(tag: str) -> str:
    """The commit that landed a slice, found by its subject line."""
    out = sh("git", "log", "--format=%h\t%s", "--reverse")
    for line in out.splitlines():
        short, _, subject = line.partition("\t")
        if subject.startswith(f"{tag}:"):
            return short
    return "unreleased"


NARRATIVE = REPO / "planning" / "README_NARRATIVE.md"


def build() -> str:
    """Substitute derived facts into the governance narrative.

    The prose lives in planning/ because it is governance: it names fenced domains in
    order to prohibit them, which is legitimate there and nowhere else. This file holds no
    prose of its own, so it needs no such licence.
    """
    template = NARRATIVE.read_text(encoding="utf-8")
    # Strip the maintainer note at the top of the narrative; it explains the file to an
    # editor, not the repository to a reader.
    if template.startswith("<!--"):
        template = template[template.index("-->") + 3:].lstrip("\n")

    migrations = sorted((REPO / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    seeds = sorted((REPO / "seeds").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    suites = sorted(p for p in (REPO / "tests").glob("*/verify_*.py"))

    landed = [(tag, note, slice_commit(tag)) for tag, note in SLICES]
    current = next((t for t, _n, c in reversed(landed) if c != "unreleased"), "M0R")

    slice_table = ["| Slice | Delivered | Commit |", "|---|---|---|"]
    for tag, note, commit in landed:
        slice_table.append(f"| **{tag}** | {note} | `{commit}` |")

    layout = ["| Path | Contents |", "|---|---|"]
    for name in sorted(DIRECTORY_PURPOSE):
        if (REPO / name).is_dir():
            layout.append(f"| `{name}/` | {DIRECTORY_PURPOSE[name]} |")

    suite_table = ["| Suite | Covers |", "|---|---|"]
    for path in suites:
        suite_table.append(
            f"| `{path.relative_to(REPO)}` | {SUITE_PURPOSE.get(path.parent.name, 'verification')} |")

    substitutions = {
        "{{GATE_STATUS}}": f"M1 — complete through **{current}**, awaiting independent review as a whole",
        "{{PACKAGE_SHA}}": PACKAGE_SHA,
        "{{SLICE_TABLE}}": "\n".join(slice_table),
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

    generated = build()

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
