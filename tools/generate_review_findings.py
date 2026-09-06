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
import requirement_coverage as coverage
import uncalled_routes  # noqa: E402

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

        if gap.get("what_would_make_it_buildable"):

            w("")

            w(f"**What would have to be true:** {gap['what_would_make_it_buildable']}")
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

    # THE RE-POINTED ONES ARE ARGUED, NOT LISTED.
    #
    # Five entries were re-pointed away from a landed gate in one pass, and none of them
    # was built. That is the pattern the completer-moved-later control exists to catch, so
    # each says what would have to be true for it to be buildable now — which is what
    # separates a CONSTRAINT from a PREFERENCE. A reviewer can then judge the reason
    # rather than the verdict.
    argued = [g for g in other if g.get("what_would_make_it_buildable")]
    if argued:
        w(f"### Constraint or preference: the {len(argued)} entries re-pointed at M4-C")
        w("")
        w("Each was moved off a gate that has already landed. None was built. The "
          "question a reviewer needs answered is not whether the gap is real — it is "
          "whether the reason for deferring it is a constraint or a preference.")
        w("")
        for gap in sorted(argued, key=lambda g: g["requirement"]):
            w(f"#### {gap['requirement']} — {gap['title']} → {gap['completing_gate']}")
            w("")
            w(gap["buildable_why"])
            w("")
            w(f"**What would have to be true:** {gap['what_would_make_it_buildable']}")
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
    landed_count = sum(1 for r in active if r["introduced_at"] in landed)
    w(f"Gates that have landed: {', '.join(g for g in order if g in landed)}. "
      f"The package carries {len(active)} active requirements and {landed_count} of them "
      f"belong to a landed gate.")
    w("")

    # ---- What "delivered" is worth, in one concrete case ------------------------
    #
    # The section above describes the grades. This one is the case that shows what the
    # strongest-sounding number in this whole audit is actually worth, and it is put
    # immediately after the grades on purpose.
    identity_writers = uncalled_routes.unreachable_writers("identity")
    reads_credential = uncalled_routes.sources_matching("identity.credential")
    w("")
    w("## FR-AUTH-001: the audit reports staff login delivered, and nobody can log in")
    w("")
    w("**This is the strongest concrete evidence in this document that *delivered* is a "
      "weaker word than the count suggests, and it is why the section above matters more "
      "than it reads.** The audit passes only when nothing is unaccounted, and it "
      f"accounts for all {landed_count} requirements belonging to a landed gate. "
      "FR-AUTH-001 — *Staff login*, P0, introduced at M1 — is inside that account, on "
      "the delivered side.")
    w("")
    w("The clause asks for three things: verified phone or email login, secure password "
      "or OTP flows, and a replaceable provider adapter. M1-B built and proved the first "
      "and the third. Its section 1 shows two distinct verified channel kinds and no "
      "provider-specific type reaching the domain model — and **that section heading is "
      "the only citation of FR-AUTH-001 anywhere in the run.** A heading over two "
      "structural checks is what grades a login flow delivered.")
    w("")
    w("The middle limb is the flow, and nothing performs it:")
    w("")
    w(f"- `identity` exposes {len(identity_writers['unreachable']) + len(identity_writers['reachable'])} "
      f"operator-callable writers — "
      + ", ".join(f"`{f}`" for f in sorted(identity_writers['unreachable']
                                           + identity_writers['reachable']))
      + ". **Not one of them turns a presented credential into a session.**")
    w(f"- {'No file' if not reads_credential else str(len(reads_credential)) + ' file(s)'} "
      f"under `api/src` reads `identity.credential`"
      + ("." if not reads_credential
         else ": " + ", ".join(f"`{f}`" for f in sorted(reads_credential)) + "."))
    w("- Every staff bearer token in this build exists because a fixture inserted a row "
      "into `identity.session` directly.")
    w("")
    w("What makes this worth a reviewer's attention is not that a gap exists. It is that "
      "**everything around the gap is real and proved.** `identity.credential` stores "
      "only digests and a CHECK rejects anything that is not one. Five failures inside "
      "the window trip `auth_lockout`. Rotation retires the previous token. "
      "`otp_transmission` refuses to record a simulated result as a live provider "
      "outcome. A failed authentication never echoes the credential presented. All of "
      "that is proved, some of it red-then-green. The one step missing is the step in "
      "the middle — verify, then issue — and its absence is invisible precisely because "
      "the mechanism on either side of it is so thoroughly built.")
    w("")
    w("**So read the delivered count as what it is: a count of requirements that "
      "something in the run names.** It does not assert that a person can perform the "
      "behaviour the clause describes. Recorded in `planning/requirement_coverage.json` "
      "as absent, security, buildable now, closing at M6. It is not built here, and this "
      "brief does not build it: a repair that quietly added an authentication flow would "
      "be a far worse defect than the one it fixed.")
    w("")

    # ---- The routes nobody has ever called -------------------------------------
    survey = uncalled_routes.survey()
    unreached = survey["uncalled"]
    w("")
    w(f"## {len(unreached)} routes the service exposes that nothing has ever called")
    w("")
    w("**This is a finding in its own right, not a footnote.** GJ-01A's lesson was that "
      "`ordering.preview_cart()` and `ordering.submit_order()` were both proved against "
      "the database while no route called either and no button reached one: every unit "
      "check passed and the feature was unreachable. M4-A shipped its billing routes the "
      "same way. The first HTTP call ever made to `POST /s/v1/checks` — made while "
      "repairing the journeys, after the slice had closed — failed on two production "
      "defects at once, because nothing had ever called it.")
    w("")
    w(f"Of {survey['total']} addressable routes, {survey['called']} are called by some "
      f"suite, journey or surface and **{len(unreached)} are called by nothing**. A route "
      "with no caller is not necessarily broken. It is unproved, which is the condition "
      "both of those defects were hiding in.")
    w("")
    w("Derived by `tools/uncalled_routes.py` on every generation, so this list cannot go "
      "stale the way a typed one would.")
    by_file: dict[str, list[str]] = {}
    for route in unreached:
        by_file.setdefault(route["file"], []).append(f"{route['verb']} {route['path']}")
    w("")
    w("| Route file | Never called |")
    w("|---|---|")
    for source in sorted(by_file):
        listed = "<br>".join(f"`{r}`" for r in sorted(by_file[source]))
        w(f"| `{source}` | {listed} |")

    # ---- A check that cannot tell its two failure names apart -------------------
    #
    # POINTER ONLY. The measurements belong to particular runs on particular machines,
    # so they live in an anchored record rather than in this derived document — a number
    # from one run, restated in a document regenerated on every commit, reads as a claim
    # about the system now.
    w("")
    w("## A check that reports a cause it cannot distinguish")
    w("")
    w("**Its own finding, and the repair belongs to M5a.** The M4-A calibration gives "
      "every performance budget in `tests/m2c` two failure names: one for a breach on a "
      "machine inside its normal band, meaning the surface is slow, and one for a breach "
      "on a starved machine, meaning the run is not evidence about the surface. Both are "
      "failures. It was built so that a breach on a starved machine could not be reported "
      "as a regression — a diagnostic naming a cause it did not verify.")
    w("")
    w("**It decides between the two by which starvation its reference happened to "
      "catch**, and that reference is a fixed arithmetic loop. Starvation the loop cannot "
      "see — disk, process launch, a filter driver scanning a freshly written workspace — "
      "leaves the reference unmoved, so the breach is reported as a slow artifact. The "
      "check distinguishes one cause from everything else and gives the remainder the "
      "other cause's name. That is the class of defect the calibration exists to prevent, "
      "inside the calibration.")
    w("")
    w("Observed on the Windows runner while getting this repair green, with the same "
      "commit passing the same budgets on Linux in the same run. The measurements, the "
      "commit they were taken against and what was and was not done about them are in "
      "`planning/M4_PERFORMANCE_CHECK_FINDING.md`, which is an anchored record rather "
      "than a derived document because they describe two runs and not the system.")
    w("")
    w("No budget threshold was changed at this gate.")
    w("")

    # ---- The kitchen the service cannot drive ----------------------------------
    kitchen = uncalled_routes.unreachable_writers("fulfillment")
    w("")
    w("## The KDS cannot be operated through the service")
    w("")
    w("**Its own finding, and it belongs to M3-B rather than to this slice.** M3-B built "
      "the ticket state machine, the station queues and the expo view, and its suite "
      "proves all of it against the database. Not one of its writers can be invoked "
      "through the running service.")
    w("")
    w(f"Of the {len(kitchen['unreachable']) + len(kitchen['reachable'])} operator-callable "
      f"writers in `fulfillment`, **{len(kitchen['unreachable'])} are reachable by no "
      f"route** and "
      f"{len(kitchen['reachable']) or 'none'} "
      f"{'are' if kitchen['reachable'] else 'is'}"
      + (f": {', '.join('`' + n + '`' for n in kitchen['reachable'])}"
         if kitchen['reachable'] else "."))
    w("")
    w("`fulfillment.transition_ticket()` is the single writer that moves a ticket through "
      "every one of its eleven states — queued, acknowledged, held, preparing, "
      "partially_completed, ready, collected, completed, rework, cancelled, exception — "
      "and it has no route. So **acknowledge, hold, fire, mark ready, complete, recall "
      "and transfer are all unreachable**, along with line-level progress, serving, "
      "waste, priority, allergy acknowledgement, release to the stations and release to "
      "service.")
    w("")
    w("`api/src/routes/station.ts` exposes three routes and all three are `GET`: the "
      "station queue, one ticket, and the expo view. `station/src` issues no write of any "
      "kind. **A cook can read the board and change nothing on it.**")
    w("")
    w("| `fulfillment` writer | Reachable through a route |")
    w("|---|---|")
    for name in kitchen["unreachable"]:
        w(f"| `fulfillment.{name}` | **no** |")
    w("")
    w("This is GJ-01A one layer below the defect that opened this repair. There, ten "
      "billing routes existed and nothing had called them; here the routes do not exist "
      "at all, so the KDS M3-B delivered could not function in production. It is recorded "
      "rather than fixed: the fix is M3-B's scope and a station write surface is a "
      "feature, not a repair.")
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
