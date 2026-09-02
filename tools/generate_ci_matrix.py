#!/usr/bin/env python3
"""Generate planning/CI_TEST_MATRIX.md from the repository (FR-SEC-015).

WHY THIS IS GENERATED. The file was hand-written at M0R and never came under a lock. By
M3-D it still said five jobs, four suites and nineteen controls, when there were six,
thirteen and seventy-six. Nothing was wrong with the pipeline; the document describing it
had simply stopped being true, and no check could notice because no check read it.

That is the third instance of the same defect class in this repository — the README's
undescribed slice and its default suite description were the first two — and each was
fixed the same way: derive the fact, and fail the build when the document disagrees. So
the jobs come from the workflow YAML, the suites from the filesystem, the controls from
the registry that `controls.check_against_run()` validates against the run, and the
package's frozen controls from the pinned package's own JSON. The prose lives in
planning/CI_MATRIX_NARRATIVE.md, because a judgement is not something a script discovers.

Usage:
    python3 tools/generate_ci_matrix.py --out planning/CI_TEST_MATRIX.md
    python3 tools/generate_ci_matrix.py --check planning/CI_TEST_MATRIX.md
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
import controls as control_registry  # noqa: E402

use_utf8_output()

REPO = Path(__file__).resolve().parents[1]
NARRATIVE = REPO / "planning" / "CI_MATRIX_NARRATIVE.md"
WORKFLOW = REPO / ".github" / "workflows" / "m1-conformance.yml"
OUTPUT_NAME = "CI_TEST_MATRIX.md"

_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
          "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
          "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy",
         8: "eighty", 9: "ninety"}


class MatrixUnderivable(RuntimeError):
    """A fact this document states cannot be read out of the repository."""


def word(n: int) -> str:
    """A count in words, because the prose around it reads as prose.

    Spelled out rather than tabulated so the sentence a reviewer reads is a sentence.
    Past ninety-nine it falls back to digits, which is the point at which spelling a
    number out stops helping anybody.
    """
    if n < 0:
        raise MatrixUnderivable(f"a count cannot be negative, and this one is {n}")
    if n < 20:
        return _UNITS[n]
    if n < 100:
        tens, units = divmod(n, 10)
        return _TENS[tens] + ("" if units == 0 else f"-{_UNITS[units]}")
    return str(n)


# What each job is FOR. The job's existence, name and platform are derived from the
# workflow; only the sentence describing its purpose is written here, and a job with no
# entry stops the build rather than rendering as a blank — the SUITE_UNDESCRIBED lesson,
# applied to the thing one level up.
JOB_PURPOSE = {
    "forbidden-surface": "no fenced Phase 2/3 surface, no v1.1 inheritance, no bypass "
                         "role in a deployment path, no drift in `/docs`, and the "
                         "generated README equals a fresh generation",
    "windows-verification": "every suite and every golden journey again on Windows, "
                            "through the same drivers, and the generators must emit "
                            "identical bytes on both platforms",
    "docs-package-integrity": "the pinned package is byte-identical: 92 files, 91 "
                              "checksum lines, 91 `OK` results, 0 failures",
    "database-verification": "every suite in order against a `postgres:16` service and "
                             "again in reverse, then the five golden journeys, then the "
                             "generated artifacts and the negative controls",
    "occurrence-registry": "the package's own frozen validator emits exactly "
                           "`PASS FORBIDDEN_OCCURRENCE_REGISTRY_VALID` with "
                           "`passed: true` and `failure_count: 0`",
    "mechanism-suite": "the package's occurrence mechanism suite emits `28/28 correct`",
}


def jobs() -> list[tuple[str, str, str]]:
    """(id, display name, runner) for every job in the workflow, in file order.

    Parsed as text rather than with a YAML library on purpose: this tool runs in the
    forbidden-surface job, which installs nothing beyond the interpreter, and adding a
    dependency to describe the pipeline would be a worse trade than a six-line parser.
    The shape it depends on — two-space job keys under `jobs:` — is asserted below.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    body = text.split("\njobs:\n", 1)
    if len(body) != 2:
        raise MatrixUnderivable(
            f"{WORKFLOW.name} has no top-level `jobs:` block, so no job can be derived "
            f"from it. A count derived from nothing would agree with any pipeline")
    found = []
    for block in re.finditer(
            r"^  ([a-z0-9-]+):\n((?:.*\n)*?)(?=^  [a-z0-9-]+:\n|\Z)", body[1], re.M):
        identifier, block_text = block.group(1), block.group(2)
        name = re.search(r"^    name:\s*(.+)$", block_text, re.M)
        runner = re.search(r"^    runs-on:\s*(\S+)$", block_text, re.M)
        found.append((identifier,
                      (name.group(1).strip() if name else identifier),
                      (runner.group(1).strip() if runner else "unknown")))
    if not found:
        raise MatrixUnderivable(
            f"no job matched in {WORKFLOW.name}. The workflow's shape changed and this "
            f"parser did not; refusing rather than reporting a pipeline of zero jobs")
    undescribed = [i for i, _n, _r in found if i not in JOB_PURPOSE]
    if undescribed:
        raise MatrixUnderivable(
            f"JOB_UNDESCRIBED: {undescribed} exist in {WORKFLOW.name} and JOB_PURPOSE "
            f"says nothing about them. Add an entry; a matrix that lists a job without "
            f"saying what it is for is the blank this document was rewritten to prevent")
    return found


def suites() -> list[tuple[str, bool]]:
    """(path, is a slice suite) for every verification suite on disk."""
    found = [(p.relative_to(REPO).as_posix(),
              re.fullmatch(r"m\d[a-z]", p.parent.name) is not None)
             for p in sorted((REPO / "tests").glob("*/verify_*.py"))]
    if not found:
        raise MatrixUnderivable(
            "no verification suite found under tests/. A matrix stating zero suites "
            "would be wrong in a way nobody would read twice")
    return found


def package_controls() -> tuple[list[tuple[str, int]], int]:
    """The gate distribution the PINNED PACKAGE froze, re-derived from its own JSON."""
    candidates = sorted((REPO / "docs").glob("*/02_MACHINE_READABLE/negative_controls.json"))
    if not candidates:
        raise MatrixUnderivable(
            "the pinned package holds no negative_controls.json, so the frozen "
            "distribution cannot be re-derived and must not be typed here instead")
    data = json.loads(candidates[0].read_text(encoding="utf-8"))
    tally: dict[str, int] = {}
    for control in data["controls"]:
        tally[control["milestone"]] = tally.get(control["milestone"], 0) + 1
    order = ["M0", "M1", "M2", "M3", "M4", "M5a", "M5b", "M6"]
    rows = sorted(tally.items(), key=lambda kv: order.index(kv[0])
                  if kv[0] in order else len(order))
    total = sum(tally.values())
    if total != data.get("count", total):
        raise MatrixUnderivable(
            f"the package's own count says {data.get('count')} and its rows sum to "
            f"{total}; the package is authoritative and it disagrees with itself")
    return rows, total


def locked_artifacts() -> list[str]:
    """Which generated files CI regenerates and compares, read from the workflow."""
    text = WORKFLOW.read_text(encoding="utf-8")
    found = sorted({m.group(1) for m in re.finditer(r"--check\s+(\S+)", text)})
    # The evidence report is compared with `diff` rather than a --check flag, so it is
    # matched on the comparison itself. Deriving it from the diff keeps this list a
    # statement about the workflow rather than about what somebody remembered.
    if re.search(r"diff -u evidence/\S+", text):
        found.append(re.search(r"diff -u (evidence/\S+)", text).group(1))
    if not found:
        raise MatrixUnderivable(
            "the workflow compares no generated artifact with a fresh generation. Either "
            "the equality locks are gone or this derivation stopped matching them")
    return sorted(set(found))


def gate_status() -> str:
    """Which gate this pipeline covers, from the slices that have suites."""
    tags = sorted(f"M{m.group(1)}-{m.group(2).upper()}"
                  for m in (re.fullmatch(r"m(\d)([a-z])", p.parent.name)
                            for p in (REPO / "tests").glob("*/verify_*.py"))
                  if m)
    if not tags:
        raise MatrixUnderivable("no slice suite exists, so no gate can be named")
    return f"{tags[-1].split('-')[0]} — complete through **{tags[-1]}**"


def build() -> str:
    template = NARRATIVE.read_text(encoding="utf-8")

    job_rows = jobs()
    job_table = ["| Job | Runs on | What it must show |", "|---|---|---|"]
    for identifier, name, runner in job_rows:
        job_table.append(f"| `{identifier}` | `{runner}` | {JOB_PURPOSE[identifier]} |")

    suite_rows = suites()
    slice_suites = [p for p, is_slice in suite_rows if is_slice]
    cross_cutting = [p for p, is_slice in suite_rows if not is_slice]
    suite_table = ["| Suite | Kind |", "|---|---|"]
    for path, is_slice in suite_rows:
        suite_table.append(
            f"| `{path}` | {'one slice' if is_slice else 'cross-cutting'} |")

    distribution = control_registry.by_gate()
    control_table = ["| Gate | Controls proved |", "|---|---:|"]
    for gate, n in distribution:
        control_table.append(f"| {gate} | {n} |")
    control_table.append(f"| **Total** | **{control_registry.count()}** |")

    package_rows, package_total = package_controls()
    package_table = ["| Gate | Controls the package froze |", "|---|---:|"]
    for gate, n in package_rows:
        package_table.append(f"| {gate} | {n} |")
    package_table.append(f"| **Total** | **{package_total}** |")

    substitutions = {
        "{{GATE_STATUS}}": gate_status(),
        "{{JOB_COUNT_WORD}}": word(len(job_rows)),
        "{{JOB_COUNT_SENTENCE}}": (
            f"{word(len(job_rows)).capitalize()} jobs, all required, none permitted to "
            f"fail soft."),
        "{{JOB_TABLE}}": "\n".join(job_table),
        "{{SUITE_COUNT_WORD}}": word(len(suite_rows)),
        "{{SUITE_COUNT_SENTENCE}}": (
            f"{word(len(suite_rows)).capitalize()} suites: {word(len(slice_suites))} "
            f"that each verify one slice, and {word(len(cross_cutting))} that cut across "
            f"gates."),
        "{{SUITE_TABLE}}": "\n".join(suite_table),
        "{{CONTROL_COUNT_WORD}}": word(control_registry.count()),
        "{{CONTROL_COUNT_SENTENCE}}": (
            f"There are {control_registry.count()} of them — "
            + ", ".join(f"{gate} {n}" for gate, n in distribution) + "."),
        "{{CONTROL_TABLE}}": "\n".join(control_table),
        "{{PACKAGE_CONTROL_TABLE}}": "\n".join(package_table),
        "{{LOCKED_ARTIFACTS}}": "\n".join(f"- `{a}`" for a in locked_artifacts()),
    }
    for marker, value in substitutions.items():
        if marker not in template:
            raise MatrixUnderivable(f"marker {marker} is absent from {NARRATIVE.name}")
        template = template.replace(marker, value)
    if "{{" in template:
        raise MatrixUnderivable("an unsubstituted marker remains in the narrative")
    return template


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the CI test matrix.")
    ap.add_argument("--out")
    ap.add_argument("--check")
    args = ap.parse_args()
    if not args.out and not args.check:
        ap.error("one of --out or --check is required")

    try:
        generated = build()
    except MatrixUnderivable as error:
        print("FAIL CI_MATRIX_UNDERIVABLE", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1
    except control_registry.ControlDrift as error:
        print(f"FAIL {str(error).split(':')[0]}", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1

    if args.check:
        path = Path(args.check)
        if not path.exists():
            print(f"FAIL CI_MATRIX_ABSENT — {path} does not exist", file=sys.stderr)
            return 1
        if path.read_text(encoding="utf-8") != generated:
            print("FAIL CI_MATRIX_DRIFT — the committed matrix does not match a fresh "
                  "generation", file=sys.stderr)
            for line in list(difflib.unified_diff(
                    path.read_text(encoding="utf-8").splitlines(),
                    generated.splitlines(), fromfile="committed", tofile="generated",
                    lineterm="", n=1))[:40]:
                print(f"  {line}", file=sys.stderr)
            return 1
        print("PASS CI_MATRIX_MATCHES_REPOSITORY")
        print(f"  {len(generated.splitlines())} lines verified against the repository")
        return 0

    path = Path(args.out)
    path.write_text(generated, encoding="utf-8")
    print(f"wrote {path} ({len(generated.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
