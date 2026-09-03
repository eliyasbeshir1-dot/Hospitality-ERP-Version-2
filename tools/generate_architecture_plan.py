#!/usr/bin/env python3
"""Generate planning/ARCHITECTURE_CONFORMANCE_PLAN.md from the repository and the package.

WHY THIS IS GENERATED. The document said "Gate: M0R" and listed
".github/workflows/m0r-conformance.yml — four validator jobs" through M1, M2 and M3. It
described a repository with "no database, schema, migration, route, worker, ORM model, UI
or application test" while holding seventeen migrations and four surfaces. Nothing caught
it because nothing read it — the same shape as planning/CI_TEST_MATRIX.md, the README's
undescribed slice, and the API described as "M1 surface only".

It is a DESCRIPTION of the present, so it is derived and locked. Its counterpart rule —
that a RECORD of a past event must not be derived, and owes an anchor instead — is stated
in tools/check_dated_records.py, which enforces it.

Usage:
    python3 tools/generate_architecture_plan.py --out planning/ARCHITECTURE_CONFORMANCE_PLAN.md
    python3 tools/generate_architecture_plan.py --check planning/ARCHITECTURE_CONFORMANCE_PLAN.md
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console import use_utf8_output  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

use_utf8_output()

REPO = Path(__file__).resolve().parents[1]
NARRATIVE = REPO / "planning" / "ARCHITECTURE_NARRATIVE.md"
WORKFLOWS = REPO / ".github" / "workflows"
PACKAGE_SHA = "b89a2d4211356be5941dc25ff2dc540728c87ed761ffd9894a3f2691ccf5b590"


class PlanUnderivable(RuntimeError):
    """A fact this document states cannot be read out of the repository or the package."""


# What each top-level entry is for. The ENTRIES are derived from the filesystem; only the
# sentence is written here, and an entry with no sentence stops the build — the
# SUITE_UNDESCRIBED rule, one level up, on the directory listing that went stale first.
ENTRY_PURPOSE = {
    ".gitattributes": "line-ending normalisation, so the same bytes check out on both platforms",
    ".github": "the conformance workflow and nothing else",
    ".gitignore": "caches, dependency directories, generated validator output",
    "README.md": "gate status, prohibitions, lineage — generated",
    "api": "the cloud API: Fastify and TypeScript, two runtime dependencies",
    "docs": "the pinned package, byte-identical, verified by its own SHA256SUMS.txt",
    "docs-local": "cross-platform command reference and its verification record",
    "evidence": "the generated evidence report",
    "migrations": "ordered, checksum-locked SQL history beginning at 0001",
    "planning": "conformance, ownership, the CI matrix, known limitations, the closure register",
    "print": "the print agent: the receipt rasteriser, the ESC/POS encoder, and the "
             "Ethiopic font it ships rather than resolves from the host",
    "pwa": "the customer surface: vanilla TypeScript, no runtime dependency",
    "schema": "the schema catalog, generated from the live database",
    "seeds": "demonstration tenants and reason-code sets, with their own ordered record",
    "station": "the kitchen display surface",
    "tests": "verification suites and the cross-cutting suites",
    "tools": "migration and seed runners, generators, verifiers",
    "waiter": "the staff surface",
}

# The M0R requirement split. The IDS are held here because M0R is closed and can gain no
# more; the COUNTS are derived from these lists and cross-checked against the package's
# own M0R total, so the prose and the package cannot disagree about how many there are.
M0R_FENCED = [
    "FR-CFG-002B", "FR-CFG-005B", "FR-EDG-002B", "FR-FUL-016B", "FR-MNU-002B",
    "FR-ORD-001C", "FR-ORD-012B", "FR-ORD-016B", "FR-ORD-019B", "FR-PAY-010B",
    "FR-POS-003C", "FR-POS-010B", "FR-RCP-008B", "FR-SEC-010B", "FR-SRV-007B",
    "FR-TEN-002B", "FR-TEN-009B", "FR-TST-004B", "FR-TST-005B", "FR-TST-007B",
    "FR-UX-001B", "FR-GOV-002", "FR-GOV-005", "FR-GOV-006",
]
M0R_POSITIVE = ["FR-GOV-001A", "FR-GOV-003", "FR-SEC-015", "FR-TST-013",
                "FR-TST-014", "FR-TST-019"]

# Which gate builds each component, and how the repository shows it has. The PATH is what
# makes "built" a fact rather than a claim.
COMPONENTS = [
    ("Cloud API (Fastify/TypeScript)", "M1",
     "tenancy, identity, configuration, domain services", "api/src/server.ts"),
    ("PostgreSQL", "M1", "single canonical store, row level security forced",
     "migrations/0001_organizational_model_and_rls.sql"),
    ("Customer PWA", "M2", "QR menu, cart, ordering, status — three languages",
     "pwa/src/app.ts"),
    ("KDS surface", "M3", "station tickets, expo, allergy salience", "station/src/station.ts"),
    ("Waiter surface", "M3", "order entry, role home, table view, handover",
     "waiter/src/waiter.ts"),
    ("POS and billing", "M4", "checks, splitting, separate tips, payments, receipts",
     "migrations/0019_checks_bills_splitting_and_tip_separation.sql"),
    ("Outlet Continuity Node", "M5a", "local API, local PostgreSQL, sync worker, print agent",
     None),
    ("Same-QR routing", "M5b", "split-horizon DNS, per-outlet TLS, authority lease", None),
]


def package_dir() -> Path:
    found = sorted(REPO.glob("docs/*/02_MACHINE_READABLE"))
    if not found:
        raise PlanUnderivable("the pinned package is not under docs/, so nothing about it "
                              "can be derived")
    return found[0]


def gate_status() -> str:
    tags = sorted(f"M{m.group(1)}-{m.group(2).upper()}"
                  for m in (re.fullmatch(r"m(\d)([a-z])", p.parent.name)
                            for p in (REPO / "tests").glob("*/verify_*.py")) if m)
    if not tags:
        raise PlanUnderivable("no slice suite exists, so no gate can be named")
    return f"{tags[-1].split('-')[0]} — building, through **{tags[-1]}**"


def repo_tree() -> str:
    # .github is listed and .git is not: one is repository content a reader should know
    # about, the other is machinery. The first draft excluded both by prefix and dropped
    # the workflow directory from a document whose whole subject is what CI enforces.
    entries = sorted(p.name for p in REPO.iterdir() if p.name != ".git")
    undescribed = [e for e in entries if e not in ENTRY_PURPOSE]
    if undescribed:
        raise PlanUnderivable(
            f"{undescribed} exist at the top level and ENTRY_PURPOSE says nothing about "
            f"them. Add a sentence; a listing that renders a bare name is the blank this "
            f"document was rewritten to prevent")
    width = max(len(e) for e in entries) + 2
    lines = ["```"]
    for entry in entries:
        suffix = "/" if (REPO / entry).is_dir() else ""
        lines.append(f"{entry + suffix:<{width}} {ENTRY_PURPOSE[entry]}")
    lines.append("```")
    return "\n".join(lines)


def surface_note() -> str:
    workflows = sorted(p.name for p in WORKFLOWS.glob("*.yml"))
    if len(workflows) != 1:
        raise PlanUnderivable(
            f"expected exactly one workflow and found {workflows}. The sentence below "
            f"names it, and a document that names one of several is worse than one that "
            f"names none")
    text = (WORKFLOWS / workflows[0]).read_text(encoding="utf-8")
    body = text.split("\njobs:\n", 1)
    jobs = re.findall(r"^  ([a-z0-9-]+):\n", body[1], re.M) if len(body) == 2 else []
    if not jobs:
        raise PlanUnderivable(f"no job could be read out of {workflows[0]}")
    # The fenced domains are COUNTED FROM THE PACKAGE, not from a list here. The first
    # draft held twelve names inline and would have said twelve for as long as the file
    # existed, which is the defect this whole document is being generated to fix.
    rules = json.loads(
        (package_dir() / "forbidden_surface_rules.json").read_text(encoding="utf-8"))
    domains = rules["forbidden_positive_obligations"]
    return (
        f"CI is `.github/workflows/{workflows[0]}` — {len(jobs)} jobs, all required, none\n"
        f"permitted to fail soft. There is no directory, table, route, worker or screen for\n"
        f"any of the {len(domains)} permanently fenced domains, however inert:\n"
        f"`tools/verify_m1.py` proves that mechanically on every run, against a vocabulary\n"
        f"it loads from the package rather than one written into it.")


def components_table() -> str:
    rows = ["| Component | Gate | Purpose | Built |", "|---|---|---|---|"]
    for name, gate, purpose, path in COMPONENTS:
        built = "—" if path is None else ("yes" if (REPO / path).exists() else "not yet")
        rows.append(f"| {name} | {gate} | {purpose} | {built} |")
    return "\n".join(rows)


def build() -> str:
    machine = package_dir()
    requirements = json.loads((machine / "requirements.json").read_text(encoding="utf-8"))
    active = requirements["active_requirements"]
    journeys = json.loads((machine / "journeys.json").read_text(encoding="utf-8"))

    m0r = {q["id"] for q in active if q.get("introduced_at") == "M0R"}
    listed = set(M0R_FENCED) | set(M0R_POSITIVE)
    if listed != m0r:
        raise PlanUnderivable(
            f"the M0R split in this file and the package disagree. Only here: "
            f"{sorted(listed - m0r)}; only in the package: {sorted(m0r - listed)}. The "
            f"counts below are derived from the lists, so a list that has drifted would "
            f"render a wrong number that reads as authoritative")

    checksums = (machine.parent / "SHA256SUMS.txt")
    if not checksums.exists():
        raise PlanUnderivable("the package holds no SHA256SUMS.txt")
    lines = [ln for ln in checksums.read_text(encoding="utf-8").splitlines() if ln.strip()]

    from fenced import fenced_identifier_pattern
    _pattern, terms = fenced_identifier_pattern()

    migrations = sorted((REPO / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not migrations:
        raise PlanUnderivable("no migration exists, so the history cannot be described")

    substitutions = {
        "{{GATE_STATUS}}": gate_status(),
        "{{PACKAGE_SHA}}": PACKAGE_SHA,
        "{{REPO_TREE}}": repo_tree(),
        "{{SURFACE_NOTE}}": surface_note(),
        "{{COMPONENTS}}": components_table(),
        "{{ACTIVE_REQUIREMENTS}}": str(len(active)),
        "{{DUAL_GATED}}": str(sum(1 for q in active if q.get("revalidated_at"))),
        "{{JOURNEY_SLICES}}": str(len(journeys["mandatory_journey_slices"])),
        "{{M0R_TOTAL}}": str(len(m0r)),
        "{{M0R_FENCED_COUNT}}": str(len(M0R_FENCED)),
        "{{M0R_POSITIVE_COUNT}}": str(len(M0R_POSITIVE)),
        "{{M0R_FENCED_IDS}}": " · ".join(M0R_FENCED),
        "{{FENCED_TERMS}}": str(terms),
        "{{PACKAGE_CHECKSUMS}}": f"{len(lines)}/{len(lines)}",
        "{{MIGRATION_COUNT}}": (f"{len(migrations)}, `{migrations[0].name[:4]}` through "
                                f"`{migrations[-1].name[:4]}`"),
    }

    template = NARRATIVE.read_text(encoding="utf-8")
    for marker, value in substitutions.items():
        if marker not in template:
            raise PlanUnderivable(f"marker {marker} is absent from {NARRATIVE.name}")
        template = template.replace(marker, value)
    if "{{" in template:
        raise PlanUnderivable("an unsubstituted marker remains in the narrative")
    return template


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the architecture conformance plan.")
    ap.add_argument("--out")
    ap.add_argument("--check")
    args = ap.parse_args()
    if not args.out and not args.check:
        ap.error("one of --out or --check is required")

    try:
        generated = build()
    except PlanUnderivable as error:
        print("FAIL ARCHITECTURE_PLAN_UNDERIVABLE", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1

    if args.check:
        path = Path(args.check)
        if not path.exists():
            print(f"FAIL ARCHITECTURE_PLAN_ABSENT — {path} does not exist", file=sys.stderr)
            return 1
        if path.read_text(encoding="utf-8") != generated:
            print("FAIL ARCHITECTURE_PLAN_DRIFT — the committed plan does not match a "
                  "fresh generation", file=sys.stderr)
            for line in list(difflib.unified_diff(
                    path.read_text(encoding="utf-8").splitlines(), generated.splitlines(),
                    fromfile="committed", tofile="generated", lineterm="", n=1))[:40]:
                print(f"  {line}", file=sys.stderr)
            return 1
        print("PASS ARCHITECTURE_PLAN_MATCHES_REPOSITORY")
        print(f"  {len(generated.splitlines())} lines verified against the repository")
        return 0

    Path(args.out).write_text(generated, encoding="utf-8")
    print(f"wrote {args.out} ({len(generated.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
