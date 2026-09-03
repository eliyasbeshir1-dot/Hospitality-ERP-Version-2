#!/usr/bin/env python3
"""Generate planning/M4_REVIEW_FINDINGS.md — what the M4 review must be told.

WHY THIS IS A DOCUMENT AND NOT JUST A REGISTER.

planning/requirement_coverage.json holds the FR-GOV-004 audit's findings, and a reviewer
who opens it will find everything. That is the problem: it requires them to open it. The
build lead's instruction was that the reviewer must MEET the disclosure rather than
discover it, so the findings that change what a review is about are stated in a document
the review reads, and stated first.

WHY IT IS GENERATED. Every fact here comes out of the coverage record and the pinned
package — counts, gates, categories, buildability, the reasoning, and which requirements
the audit can prove and how strongly. A hand-written summary of a register is a second
statement of the register, which is the defect class this repository has now fixed five
times: the README's undescribed slice, the CI matrix that said five jobs, the ownership
map that said no migration existed, the evidence step that forgot a suite log, and the
control step that forgot one too. CI regenerates this and fails on any difference.

WHAT IS WRITTEN HERE RATHER THAN DERIVED. The framing sentences — what a category means,
why the reviewer may disagree. A judgement is not something a script discovers, and these
particular judgements are about how to READ the findings, so they stay next to the code
that renders them rather than in a narrative file nothing else would use.

Usage:
    python3 tools/generate_review_findings.py --out planning/M4_REVIEW_FINDINGS.md
    python3 tools/generate_review_findings.py --check planning/M4_REVIEW_FINDINGS.md
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console import use_utf8_output  # noqa: E402
import partial_closures  # noqa: E402
import requirement_coverage as coverage  # noqa: E402

use_utf8_output()

REPO = Path(__file__).resolve().parents[1]
OUTPUT_NAME = "M4_REVIEW_FINDINGS.md"

URGENT = coverage.URGENT


class FindingsUnderivable(RuntimeError):
    """A fact this document states cannot be read out of the repository."""


def build() -> str:
    record = json.loads(coverage.COVERAGE.read_text(encoding="utf-8"))
    gaps = record["gaps"]
    if not gaps:
        raise FindingsUnderivable(
            "the coverage record holds no gaps. Either the audit found none — in which "
            "case this document should say so deliberately rather than be generated empty "
            "— or the record is not being read")

    package = json.loads(partial_closures._requirements_path().read_text(encoding="utf-8"))
    active = package["active_requirements"]
    order = partial_closures.gate_order()
    landed = coverage.landed_gates()

    absent = [g for g in gaps if g["state"] == "absent"]
    uncited = [g for g in gaps if g["state"] == "uncited"]
    urgent = [g for g in absent if g["category"] in URGENT]

    out: list[str] = []
    w = out.append

    w("# M4 review — findings the reviewer must be told")
    w("")
    w("**Generated. Do not edit.** `python3 tools/generate_review_findings.py "
      "--out planning/M4_REVIEW_FINDINGS.md`, and CI fails the build when the committed "
      "copy differs from a fresh generation.")
    w("")
    w("This document exists because a finding a reviewer has to go looking for is a "
      "finding they may not find. Everything below comes from "
      "`planning/requirement_coverage.json`, which the FR-GOV-004 audit validates on "
      "every run.")
    w("")
    w("## The reviewer is free to disagree with all of it")
    w("")
    w("Each finding below carries a **classification** and a **completing gate**, and "
      "both are the builder's judgement, made under the deadline of a closing gate. "
      "That is precisely the condition in which *\"not really a security gap\"* is an "
      "easy sentence to write. **The review may challenge a classification as readily "
      "as a fix.** A gap wrongly called schedulable is worse than one honestly called "
      "urgent, and the reasoning for every one is printed here so it can be argued with "
      "rather than taken on trust.")
    w("")
    w("Completing gates are not chosen. Each is the next gate at which the pinned "
      "package itself revalidates the requirement, read from its own `revalidated_at`, "
      "or the final gate when the package names none. Where this slice delivers the "
      "missing half the gate is overridden to the slice that delivers it, and every such "
      "override is visible in the tables below.")
    w("")

    # ---- the headline ------------------------------------------------------
    w(f"## {len(urgent)} absent requirements in money, security or authority")
    w("")
    w("These are the findings that change what this review is about. **Absent** means "
      "the behaviour genuinely does not exist — not that it exists uncited. Each row "
      "says whether it could be built today, because otherwise *\"not due yet\"* reads "
      "as *\"not possible yet\"*, which is a different and more forgiving claim.")
    w("")
    w("| Requirement | Introduced | Category | Closes at | Buildable now |")
    w("|---|---|---|---|---|")
    for gap in sorted(urgent, key=lambda g: g["requirement"]):
        buildable = {True: "**yes**", False: "no", None: "—"}[gap.get("buildable_now")]
        w(f"| `{gap['requirement']}` {gap['title']} | {gap['introduced_at']} "
          f"| {gap['category']} | **{gap['completing_gate']}** | {buildable} |")
    w("")
    for gap in sorted(urgent, key=lambda g: g["requirement"]):
        w(f"### {gap['requirement']} — {gap['title']}")
        w("")
        w(gap["why"])
        w("")
        w(f"**Buildable now:** {gap['buildable_why']}")
        w("")
        w(f"**This entry closes when:** {gap['closes_when']}")
        w("")
        if gap.get("revalidated_at"):
            w(f"*The package revalidates this at {', '.join(gap['revalidated_at'])}.*")
            w("")

    # ---- the rest of the absences -----------------------------------------
    other = [g for g in absent if g["category"] not in URGENT]
    w(f"## {len(other)} further absences, outside money, security and authority")
    w("")
    w("| Requirement | Introduced | Category | Closes at | Buildable now | What is absent |")
    w("|---|---|---|---|---|---|")
    for gap in sorted(other, key=lambda g: (order.index(g["introduced_at"]),
                                            g["requirement"])):
        buildable = {True: "yes", False: "no", None: "—"}[gap.get("buildable_now")]
        first = gap["why"].split(". ")[0].rstrip(".")
        w(f"| `{gap['requirement']}` {gap['title']} | {gap['introduced_at']} "
          f"| {gap['category']} | {gap['completing_gate']} | {buildable} | {first}. |")
    w("")

    # ---- the governance gaps ----------------------------------------------
    w(f"## {len(uncited)} requirements delivered with nothing naming them")
    w("")
    w("**Uncited** means the behaviour exists, works, and no recorded output names the "
      "requirement — so the audit cannot see a proof that is genuinely there. This is a "
      "governance gap, not a product one, and the checker refuses to let one be filed as "
      "a money, security or authority absence: conflating the two inflates the urgent "
      "list until nobody reads it. Each closes the same way, by a check or a CI step "
      "citing the requirement so the audit can grade it.")
    w("")
    w("| Requirement | Introduced | Closes at |")
    w("|---|---|---|")
    for gap in sorted(uncited, key=lambda g: (order.index(g["introduced_at"]),
                                              g["requirement"])):
        w(f"| `{gap['requirement']}` {gap['title']} | {gap['introduced_at']} "
          f"| {gap['completing_gate']} |")
    w("")

    # ---- how strong the evidence is, for what IS delivered -----------------
    w("## How strongly the delivered requirements are proved")
    w("")
    w("The audit grades its own evidence rather than implying a strength it did not "
      "measure. A reviewer should read the middle row carefully: **it verifies that the "
      "citation runs, and does not establish that the check has ever been shown able to "
      "fail.**")
    w("")
    w("| Grade | What it establishes |")
    w("|---|---|")
    w("| `proved-red` | The citation sits on a negative control that the run showed red "
      "with a real defect planted, then green after revert. The assertion has been "
      "demonstrated capable of failing. |")
    w("| `ran` | The citation sits on a check that executed and reported. **Verifies the "
      "citation runs. Does not establish it can fail.** |")
    w("| `ci-step` | The citation sits in a workflow step, which fails the build on a "
      "non-zero exit. Can fail; cannot show a planted defect. |")
    w("")
    w(f"Gates that have landed: {', '.join(g for g in order if g in landed)}. "
      f"The package carries {len(active)} active requirements and "
      f"{sum(1 for r in active if r['introduced_at'] in landed)} of them belong to a "
      f"landed gate.")
    w("")

    # ---- the package's own gap --------------------------------------------
    package_gaps = [g for g in absent
                    if "amendment_register" in g["closes_when"]
                    or "amendment_register" in g["why"]]
    if package_gaps:
        w("## A requirement the pinned package itself cannot satisfy")
        w("")
        for gap in package_gaps:
            w(f"**{gap['requirement']} — {gap['title']}.** {gap['why']}")
            w("")
            w(f"**Closes when:** {gap['closes_when']}")
            w("")
        w("No change to this repository can close that. It is recorded here because a "
          "package defect found by the build is the reviewer's to adjudicate, not the "
          "builder's to work around.")
        w("")

    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--out", type=Path)
    group.add_argument("--check", type=Path)
    args = parser.parse_args(argv)

    try:
        rendered = build()
    except (FindingsUnderivable, coverage.CoverageUnreadable,
            partial_closures.RegisterUnreadable) as refused:
        print(f"FAIL REVIEW_FINDINGS_UNDERIVABLE: {refused}")
        return 1

    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
        print(f"wrote {args.out} ({len(rendered.splitlines())} lines)")
        return 0

    if args.check.name != OUTPUT_NAME:
        print(f"FAIL REVIEW_FINDINGS_WRONG_TARGET: expected {OUTPUT_NAME}")
        return 1
    committed = args.check.read_text(encoding="utf-8") if args.check.is_file() else ""
    if committed != rendered:
        print("FAIL REVIEW_FINDINGS_STALE: the committed findings differ from a fresh "
              "generation. A summary of a register that has stopped matching it is worse "
              "than no summary, because a reviewer will believe it.")
        sys.stdout.writelines(difflib.unified_diff(
            committed.splitlines(keepends=True), rendered.splitlines(keepends=True),
            fromfile="committed", tofile="regenerated"))
        return 1
    print(f"PASS REVIEW_FINDINGS_MATCH_THE_RECORD\n  "
          f"{len(rendered.splitlines())} lines verified against "
          f"planning/{coverage.COVERAGE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
