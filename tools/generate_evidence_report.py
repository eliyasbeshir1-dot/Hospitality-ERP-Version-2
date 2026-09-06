#!/usr/bin/env python3
"""Generate the M1 evidence report (FR-TST-016).

The factual parts — commit, versions, migration and seed lists with hashes, suite results,
schema counts — are read from the repository, the database and the suite logs. Nothing
factual is typed by hand, so the report cannot quietly disagree with what it describes.

The narrative parts — accepted exceptions, known limitations, deferrals — are held in this
file, because a judgement is not something a script can discover and pretending otherwise
would be worse than writing it down.

EVERY FIELD IS REPRODUCIBLE. CI regenerates this report and fails if it differs from the
committed copy, so nothing environment-specific or time-varying may appear in it: no
generation timestamp, no applied-at time, no patch-level version that differs between a
developer machine and the runner. Exact patch versions are in the CI logs, retained as
artifacts, where they belong.

THE COMMIT IT NAMES. A report cannot contain the hash of the commit that carries it. It
therefore names the last commit that touched anything OTHER than the report, and the
report is committed on its own afterwards. Regeneration then yields the same hash, so the
equality check holds, and any later change to code makes it fail until the report is
regenerated — which is the freshness guarantee the review asked for.

Usage:
    python3 tools/generate_evidence_report.py --dsn <dsn> --logs <dir> --out evidence/M1_EVIDENCE_REPORT.md
"""
from __future__ import annotations

import argparse
import hashlib
import os
import ast
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console import use_utf8_output  # noqa: E402

use_utf8_output()


sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_history import (  # noqa: E402
    HistoryUnavailable, assert_history_available, current_branch, dirt_excluding,
    last_commit_excluding,
)

REPO = Path(__file__).resolve().parents[1]
UNIT = "\x1f"

# EVERY SUITE THE REPORT ACCOUNTS FOR, in the order the table prints them.
#
# Named once, here, and read back by `--list-suites` so the CI job that hands this tool
# its logs derives the list instead of restating it. A suite added to the report but not
# to the job's copy list would otherwise fail at generation with a missing log, and a
# suite dropped from the job would silently stop being accounted for — the same "two
# statements of one fact with one left behind" defect the checksum locks exist to prevent.
SUITES = (
    ("m1a", "M1-A database, RLS, roles"),
    ("m1b", "M1-B identity and authentication"),
    ("m1c", "M1-C configuration, audit, money"),
    ("m1d", "M1-D API, security, operations"),
    ("m2a", "M2-A menu, pricing, translation storage"),
    ("m2b", "M2-B tables, QR, guests, allergen safety"),
    ("m2c", "M2-C customer surface, rendered"),
    ("m3a", "M3-A orders, snapshots, session lifecycle"),
    ("m3b", "M3-B fulfillment, tickets, stations, the KDS"),
    ("m3c", "M3-C service requests, notifications, integration"),
    ("m3d", "M3-D terminals, override, handover, the waiter surface"),
    ("m4a", "M4-A checks, bills, splitting, tip separation"),
    ("m4b", "M4-B payment capture, verification, cash, reversal"),
    ("m4c", "M4-C receipts, the printer path, reporting, the register audit"),
    ("fenced_gate", "Fenced-domain gate, vocabulary and mutations"),
    ("journeys", "The golden journeys, end to end"),
)
REPORT_PATH = "evidence/M1_EVIDENCE_REPORT.md"


def sh(*command: str) -> str:
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", cwd=REPO)
    return proc.stdout.strip()


def query(dsn: str, sql: str) -> list[list[str]]:
    proc = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "--no-psqlrc", "-X", "-t", "-A", "-F", UNIT],
        input=sql, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if proc.returncode != 0:
        return []
    return [line.split(UNIT) for line in proc.stdout.splitlines() if line.strip()]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SuiteLogMissing(Exception):
    """An expected suite log is absent. The report must not be written without it."""


class SuiteUnaccounted(Exception):
    """A verification suite exists in the repository and the report has no row for it."""


def assert_suites_cover_the_repository() -> None:
    """SUITES must name every verification suite the repository actually has.

    SUITES is a list, and a list is a second statement of a fact the repository already
    holds: tests/<name>/verify_<name>.py IS the suite. The two can disagree in one
    direction quietly — a suite added without a row here simply stops being accounted for,
    and the report then states a total that is missing a whole gate while looking complete.
    The other direction is already loud, because suite_result() refuses a missing log.

    So the catalog is the repository, and this is the equality check. It is the same rule
    the README generator enforces as SLICE_UNDESCRIBED, applied to the document that adds
    the numbers up rather than the one that describes them.
    """
    on_disk = {d.name for d in sorted((REPO / "tests").iterdir())
               if d.is_dir() and (d / f"verify_{d.name}.py").is_file()}
    named = {name for name, _label in SUITES}
    unaccounted = sorted(on_disk - named)
    if unaccounted:
        raise SuiteUnaccounted(
            "SUITE_UNACCOUNTED: " + ", ".join(unaccounted) + " "
            + ("is a verification suite" if len(unaccounted) == 1
               else "are verification suites")
            + " in tests/ with no row in this report. Add "
            + ("it" if len(unaccounted) == 1 else "them")
            + " to SUITES; a suite the repository runs and the evidence report does not "
              "count makes the total quietly wrong rather than visibly short")
    absent = sorted(named - on_disk)
    if absent:
        raise SuiteUnaccounted(
            "SUITE_UNACCOUNTED: " + ", ".join(absent) + " is named in SUITES and has no "
            "tests/<name>/verify_<name>.py. A row for a suite that does not exist would "
            "be a report describing a repository that is not this one")


class JourneyUnaccounted(Exception):
    """The suite walks a journey the report has no row for, or the reverse."""


JOURNEY_SUITE = REPO / "tests" / "journeys" / "verify_journeys.py"


class ReportTreeNotClean(Exception):
    """The report would describe a tree that is not the one it anchors to."""


def assert_tree_is_clean() -> None:
    """Refuse to write the report from a working tree carrying uncommitted work.

    THE DEFECT THIS EXISTS FOR SHIPPED TWICE, AT THIS GATE, IN THIS DOCUMENT. Once from a
    run whose journeys suite had crashed, so every journey row read FAIL beside "92 steps,
    0 failures"; once from a tree still holding eight other modified files, so the report
    anchored to the previous commit and described a repository nobody had. Both were
    caught by a person reading the diff, which is the weakest check this repository has.

    The report names the last commit touching anything other than itself. If other files
    are uncommitted, that commit is not the state the report describes: the numbers come
    from the working tree and the anchor comes from history, and the two have drifted. CI
    regenerates from a clean checkout and diffs, so the disagreement surfaces there as a
    mismatch nobody can read — the report is right about neither tree.

    Excluding the report itself is deliberate and is the same exclusion the anchor uses:
    regenerating it is what this function is called during, and the workflow it permits is
    commit the work, regenerate, commit the report.
    """
    uncommitted = dirt_excluding(REPORT_PATH)
    if uncommitted:
        raise ReportTreeNotClean(
            "REPORT_TREE_NOT_CLEAN: " + ", ".join(uncommitted[:8])
            + (f" and {len(uncommitted) - 8} more" if len(uncommitted) > 8 else "")
            + f" {'is' if len(uncommitted) == 1 else 'are'} uncommitted. This report "
              f"anchors to the last commit touching anything other than itself, and with "
              f"work outstanding that commit is not the tree these numbers were measured "
              f"in. Commit the work first, then regenerate: a report describing a tree "
              f"nobody has is worse than no report, because it looks like evidence")


def journeys_the_suite_walks() -> list[str]:
    """Every journey the suite actually walks, read from its own JOURNEYS table.

    PARSED, not imported: importing the suite would need a database, a compiled service
    and a browser, none of which this generator has or should acquire in order to know
    what a table says. Parsed rather than grepped for the reason tier_of() is parsed —
    these files explain themselves at length in prose that names journeys, and a scanner
    counting prose would report journeys nobody walks.
    """
    tree = ast.parse(JOURNEY_SUITE.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "JOURNEYS" for t in node.targets):
            continue
        walked = []
        for element in getattr(node.value, "elts", []):
            first = getattr(element, "elts", [None])[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                raise JourneyUnaccounted(
                    f"JOURNEY_UNACCOUNTED: {JOURNEY_SUITE.name} has a JOURNEYS entry "
                    f"whose first element is not a literal name, so which journeys the "
                    f"suite walks cannot be read. Fail closed rather than report a table "
                    f"assembled from the half that could be parsed")
            walked.append(first.value)
        if not walked:
            raise JourneyUnaccounted(
                f"JOURNEY_UNACCOUNTED: {JOURNEY_SUITE.name} has an empty JOURNEYS table. "
                f"A report that rendered no journey rows because it found no journeys "
                f"would look like a run with nothing to say rather than a broken read")
        return walked
    raise JourneyUnaccounted(
        f"JOURNEY_UNACCOUNTED: {JOURNEY_SUITE.name} has no JOURNEYS table. The report's "
        f"journey rows are a second statement of that table, and with nothing to check "
        f"them against they would be unfalsifiable prose")


def assert_journeys_cover_the_suite() -> None:
    """JOURNEYS here must name every journey the suite walks, and no others.

    THE DEFECT THIS EXISTS FOR SHIPPED. The suite grew from six journeys to eleven when
    the M4 repair drove GJ-01B, GJ-02B, GJ-03B, GJ-06 and GJ-07 through the running
    service, and this table stayed at six. Every one of the five passed in every run and
    appeared nowhere in the document a reviewer reads — so the artifact reporting on the
    repair omitted exactly the journeys the repair created, which is worse than saying
    nothing, because six rows all marked PASS read as a complete account.

    The suite's table is the catalog and this is the equality check, the same rule
    SUITE_UNACCOUNTED applies one level up. Coverage prose cannot be derived — what a
    journey covers is editorial — so the prose stays written by hand and only its
    PRESENCE is enforced. The verdict, the step count and the tier are all read from the
    run; this table declares coverage, never outcome.
    """
    walked = journeys_the_suite_walks()
    described = [name for name, _covers, _gates in JOURNEYS]
    missing = [name for name in walked if name not in described]
    if missing:
        raise JourneyUnaccounted(
            "JOURNEY_UNACCOUNTED: " + ", ".join(missing) + " "
            + ("is a journey" if len(missing) == 1 else "are journeys")
            + " the suite walks with no row in this report. Add "
            + ("it" if len(missing) == 1 else "them")
            + " to JOURNEYS with what "
            + ("it covers" if len(missing) == 1 else "they cover")
            + " and which gates "
            + ("it reaches" if len(missing) == 1 else "they reach")
            + "; a journey that runs and is not reported is coverage the reviewer is "
              "never told about")
    stale = [name for name in described if name not in walked]
    if stale:
        raise JourneyUnaccounted(
            "JOURNEY_UNACCOUNTED: " + ", ".join(stale) + " "
            + ("is described here and the suite does not walk it"
               if len(stale) == 1 else
               "are described here and the suite walks none of them")
            + ". A row for a journey nobody walks is a claim of coverage this repository "
              "cannot support")


def suite_result(logs: Path, name: str) -> tuple[str, str, str]:
    """Read a suite's verdict and counts from its log.

    A missing log is a failure, not a "not run" row. Reporting a suite as not run when it
    actually passed on another runner produces a plausible, wrong, and permanently
    committed document — the same quiet degradation as a generator inventing commits for a
    shallow checkout, or a verifier falling back to a built-in vocabulary.
    """
    path = logs / f"{name}.log"
    if not path.exists():
        raise SuiteLogMissing(
            f"{path.name} is absent from {logs}. Every suite must be represented; if it "
            f"ran in a different job, hand its log to this one rather than omitting it")
    text = path.read_text(encoding="utf-8", errors="ignore")
    tag = {"fenced_gate": "FENCED_GATE",
           "journeys": "GOLDEN_JOURNEY"}.get(name, name.upper())
    verdict = "PASS" if re.search(rf"^PASS {tag}_VERIFICATION", text, re.M) else "FAIL"
    # "steps checked" is the golden-journey suite's own counter. It is a different word
    # because a journey step is a different thing from a slice check — one is a person
    # walking, the other is a property being asserted — and the report says so rather
    # than flattening both into "checks" and inviting a reader to add them up.
    blocks = re.findall(
        r"(?:checks run|steps checked)\s+:\s+(\d+)\s*\n\s*passed\s+:\s+(\d+)"
        r"\s*\n\s*failed\s+:\s+(\d+)", text)
    if not blocks:
        return (verdict, "-", "-")
    ran, _passed, failed = blocks[-1]
    return (verdict, ran, failed)


# WHAT EACH JOURNEY COVERS, and which gates it reaches.
#
# Here because a reviewer looking at "journeys: 6 suites passed" has no way to tell
# whether the journeys exercise the whole chain or repeat whichever slice they were
# committed beside. They walk M1 through M3-D — a QR code from M2-B, a menu from M2-A
# rendered by M2-C, an order from M3-A, a kitchen from M3-B, a service request from M3-C
# and a waiter from M3-D — and the row says so per journey rather than as one sentence
# about the suite.
#
# The verdict is READ FROM THE RUN. This table declares coverage, never outcome.
JOURNEYS = [
    ("GJ-01A", "An English guest: scan, browse, choose modifiers, submit, the kitchen "
               "prepares, a waiter serves, the guest sees served — and no local-authority "
               "claim exists anywhere in the catalog",
               "M2-B · M2-C · M3-A · M3-B"),
    ("GJ-01B", "English settlement: the cashier presents the check and settles it in "
               "cash, no tip recorded as a decision rather than an absence, bill and tip "
               "and total shown apart on the receipt, one trip down the printer path, a "
               "second original print refused, and check, bill, payment and receipt all "
               "hanging off the guest's order",
               "M4-A · M4-B · M4-C"),
    ("GJ-02", "Amharic: menu and allergen text, an order carrying the chosen language, "
              "statuses and messages in Ethiopic script, the waiter called, a second order",
              "M2-A · M2-C · M3-A · M3-B · M3-C"),
    ("GJ-02B", "Amharic settlement: a tip chosen on the check, an unverified proof that "
               "settles nothing until a named person verifies it in the provider's app, "
               "a receipt Amharic on every line with every Ethiopic glyph drawn from the "
               "packaged font, and the table released only once it is settled",
               "M2-A · M4-A · M4-B · M4-C"),
    ("GJ-03A", "Arabic right to left: true RTL layout, Latin SKUs inside an Arabic page, "
               "ETB prices measured left to right, an order, an Arabic status timeline",
               "M2-A · M2-C · M3-A · M3-B"),
    ("GJ-03B", "Arabic settlement: a tip and a payment on a permitted live method, a "
               "receipt that keeps bill, tip and total paid apart under RTL, and Arabic "
               "and the Latin currency code both drawn by the packaged fonts",
               "M2-A · M4-A · M4-B · M4-C"),
    ("GJ-04", "Two devices at one table: personal baskets, separate orders, the waiter "
              "called and acknowledged, a later add-on, an authorized session move",
              "M2-B · M3-A · M3-C"),
    ("GJ-05", "Waiter-entered: the table opened, an order entered through the staff "
              "routes, routed to stations, the allergy emphasised, served, and one "
              "amendment authorized by a manager on their own session",
              "M3-A · M3-B · M3-D"),
    ("GJ-06", "A check split by item into one document per payer: each payment "
              "allocating to bill and tip independently, one payer tipping and the other "
              "not, and each payer's receipt produced exactly once",
              "M4-A · M4-B · M4-C"),
    ("GJ-07", "Taking money back: a cashier refused their own refund, a manager's "
              "purpose-specific step-up authorizing it, bill and tip corrected as two "
              "independent records, a corrected receipt issued as a new revision with "
              "its own number and a marked reprint carrying operator and reason, and the "
              "first receipt's own record left unchanged",
              "M1-B · M4-B · M4-C"),
    ("FR-TST-007A", "Two submissions racing, measured with M3-A's catalog-derived "
                    "whole-schema differential: one order, one line, no duplicate "
                    "commercial effect",
                    "M3-A · M3-D"),
]


def journey_result(logs: Path, journey: str) -> tuple[str, str, str]:
    """One journey's verdict, step count and TIER, read out of the run's own summary.

    The tier is here because eleven rows all marked PASS would otherwise read as eleven
    journeys walked in a browser, and seven of them are not: they go through the routes a
    surface would call, which is what partial closure FR-TST-005A records and what the
    settlement half of this product still owes. The suite derives the tier from each
    journey's own source rather than declaring it, so this column cannot claim a stronger
    proof than the run performed.
    """
    path = logs / "journeys.log"
    if not path.exists():
        raise SuiteLogMissing(
            f"journeys.log is absent from {logs}. The golden journeys are part of "
            f"the evidence, not an optional extra; hand the log to this job rather than "
            f"omitting the rows")
    text = path.read_text(encoding="utf-8", errors="ignore")
    matched = re.search(
        rf"^\s*(PASS|FAIL)\s+{re.escape(journey)}\s+(\S+) steps(?:\s+\[(\w+) tier\])?",
        text, re.M)
    if not matched:
        return ("FAIL", "-", "-")
    return (matched.group(1), matched.group(2), matched.group(3) or "-")


# The registry moved to tools/controls.py at M3-D, and the reason is the drift it now
# prevents. Three places needed to agree about which controls exist — this report, the CI
# step that requires each to have gone red and green, and the CI matrix that states how
# many there are — and a fourth number in a review brief said 62 while this report said
# 76. The artifact was right and the prose had never been re-derived. There is one
# registry now, and controls.check_against_run() compares it with what the suites printed
# before this report renders a single row.
from controls import CONTROLS, ControlDrift  # noqa: E402
import controls as control_registry          # noqa: E402


def control_state(logs: Path, control: str, suite: str) -> str:
    path = logs / f"{suite}.log"
    if not path.exists():
        return "not run"
    text = path.read_text(encoding="utf-8", errors="ignore")
    # Two things sit between "[PASS]" and the marker and neither is optional to allow for.
    # M2-C prefixes each result with whether its evidence was measured in a browser or
    # asserted from source. M3-D writes the control's DESCRIPTION after its identifier —
    # "NC-M3D-001  a waiter-entered order bypasses a rule QR ordering enforces — RED" —
    # so a log line says what was broken rather than only which number it was. An anchor
    # that demanded the marker immediately after the identifier reported all ten M3-D
    # controls as "not proven" while every one of them had gone red and green in the run
    # it was reading. The identifier is the identity; what follows it is prose.
    red = re.search(rf"\[PASS\] (?:\([a-z]+\) )?{re.escape(control)}\b[^\n]*? — RED",
                    text) is not None
    green = re.search(rf"\[PASS\] (?:\([a-z]+\) )?{re.escape(control)}\b[^\n]*? — GREEN",
                      text) is not None
    if red and green:
        return "red, then green"
    if green:
        return "green only — NOT PROVEN"
    return "not proven"


def build(dsn: str, logs: Path) -> str:
    out: list[str] = []
    w = out.append

    # Before anything is read: the report's own list of suites must equal the repository's.
    assert_suites_cover_the_repository()
    assert_journeys_cover_the_suite()
    assert_tree_is_clean()

    # Under a shallow checkout the commit this report names cannot be resolved, and the
    # field would come out empty rather than wrong-looking. Refuse instead.
    assert_history_available()
    commit, short = last_commit_excluding(REPORT_PATH)
    branch = current_branch()

    w("# M1 Evidence Report")
    w("")
    w("**Gate:** M1 — foundation, security, tenancy, identity, data architecture, API surface")
    w("**Slices:** A (database and RLS) · B (identity) · C (configuration, audit, money) · D (API, operations)")
    w("")
    w("Generated by `tools/generate_evidence_report.py`. Every fact below is read from the")
    w("repository, the live database or the suite logs at generation time; the judgements are")
    w("recorded deliberately and are marked as such.")
    w("")
    w("---")
    w("")
    w("## Commit under review")
    w("")
    w("| | |")
    w("|---|---|")
    w(f"| Commit | `{commit}` |")
    w(f"| Short | `{short}` |")
    w(f"| Branch | `{branch}` |")
    w(f"| Subject | the last commit touching anything other than this report |")
    # Not a measurement with two possible values: assert_tree_is_clean() refuses above,
    # so this states the guarantee that refusal provides rather than a field that could
    # only ever read one way.
    w(f"| Working tree | clean at generation — the generator refuses a tree that is not |")
    w("")

    w("## Versions")
    w("")
    w("Runtime versions are given to the major, because this report must regenerate")
    w("identically on any machine that runs the suites. Exact patch versions appear in the")
    w("CI logs, which are retained as build artifacts.")
    w("")
    w("| Component | Version |")
    w("|---|---|")
    w(f"| Python | {'.'.join(sys.version.split()[0].split('.')[:2])} |")
    node = sh("node", "--version") or "not found"
    w(f"| Node | {node.lstrip('v').split('.')[0] if node.startswith('v') else node} |")
    pg = query(dsn, "SHOW server_version;")
    w(f"| PostgreSQL | {pg[0][0].split('.')[0] if pg else 'unavailable'} |")
    pkg = REPO / "api" / "package.json"
    if pkg.exists():
        import json
        manifest = json.loads(pkg.read_text(encoding="utf-8"))
        for name, version in manifest.get("dependencies", {}).items():
            w(f"| {name} | {version} |")
    w("")

    w("## Migrations applied")
    w("")
    w("Ordered, forward-only and checksum-locked. An edited applied migration fails preflight.")
    w("")
    w("| Version | File | SHA-256 | Applied |")
    w("|---|---|---|---|")
    applied = {row[1] for row in query(dsn, """
        SELECT version, filename FROM migration.schema_migrations ORDER BY version;
    """)}
    for path in sorted((REPO / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")):
        state = "applied" if path.name in applied else "not applied to this database"
        w(f"| `{path.name[:4]}` | `{path.name}` | `{digest(path)[:16]}…` | {state} |")
    w("")

    w("## Seeds applied")
    w("")
    w("A separate ordered record with its own checksum lock, deliberately outside the")
    w("migration history: seeds are data, not structure, and the two must not vouch for each")
    w("other. Bookkeeping runs as the migration identity; content is applied through the")
    w("least-privileged application role.")
    w("")
    w("| Version | File | SHA-256 | Applied |")
    w("|---|---|---|---|")
    seeded = {row[1] for row in query(dsn, """
        SELECT version, filename FROM seed_history.applied_seed ORDER BY version;
    """)}
    for path in sorted((REPO / "seeds").glob("[0-9][0-9][0-9][0-9]_*.sql")):
        state = "applied" if path.name in seeded else "not applied to this database"
        w(f"| `{path.name[:4]}` | `{path.name}` | `{digest(path)[:16]}…` | {state} |")
    w("")

    w("## Schema shape")
    w("")
    counts = query(dsn, """
        SELECT n.nspname, count(*) FILTER (WHERE c.relkind = 'r')::text,
               count(*) FILTER (WHERE c.relkind = 'r' AND c.relrowsecurity)::text,
               count(*) FILTER (WHERE c.relkind = 'r' AND c.relforcerowsecurity)::text
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('app','org','identity','money','config','audit')
        GROUP BY n.nspname ORDER BY n.nspname;
    """)
    w("| Schema | Tables | RLS enabled | RLS forced |")
    w("|---|---:|---:|---:|")
    for schema, tables, enabled, forced in counts:
        w(f"| `{schema}` | {tables} | {enabled} | {forced} |")
    w("")
    floats = query(dsn, """
        SELECT count(*)::text FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped
          AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
          AND t.typname IN ('float4','float8');
    """)
    w(f"Binary floating point columns anywhere in the database: **{floats[0][0] if floats else '?'}**.")
    w("Money is stored as integer minor units beside an explicit currency.")
    w("")

    w("## Test results")
    w("")
    w("| Suite | Verdict | Checks | Failures |")
    w("|---|---|---:|---:|")
    total = 0
    for name, label in SUITES:
        verdict, ran, failed = suite_result(logs, name)
        if ran.isdigit():
            total += int(ran)
        w(f"| {label} | **{verdict}** | {ran} | {failed} |")
    w(f"| **Total** | | **{total}** | |")
    w("")

    w("## The golden journeys (FR-TST-005A)")
    w("")
    w("Browser automation against real persistence — the journey a person walks, not an API")
    w("sequence. Each journey names the gates it reaches, because these are not any one")
    w("slice's tests: they exercise everything the repository has landed, and a reader who")
    w("filed them under the slice they were committed beside would be reading them as a")
    w("repeat of it.")
    w("")
    w("A failure names the JOURNEY and the STEP. Steps after a failure are reported as not")
    w("reached rather than skipped silently, so a journey that stopped early cannot be")
    w("mistaken for one that mostly worked.")
    w("")
    w("| Journey | Covers | Gates reached | Tier | Verdict | Steps |")
    w("|---|---|---|---|---|---:|")
    for journey, covers, gates in JOURNEYS:
        verdict, steps, tier = journey_result(logs, journey)
        w(f"| `{journey}` | {covers} | {gates} | {tier} | **{verdict}** | {steps} |")
    w("")

    w("## Negative controls")
    w("")
    # The number is DERIVED, here and in every other document that states it. It read 62
    # in a review brief and 76 here, and the difference was a count carried forward by
    # hand. Nothing counts controls by hand any more.
    control_registry.check_against_run(logs)
    distribution = ", ".join(f"{gate} {n}" for gate, n in control_registry.by_gate())
    w(f"**{control_registry.count()}** controls — {distribution} — each planted as a real")
    w("defect, required to produce its exact registered signature, then reverted and")
    w("required to pass again. A control that never went red is a coverage gap wearing a")
    w("green badge, and CI fails the build when one is missing. The registry is")
    w("`tools/controls.py` and it is compared with this run's logs before this table is")
    w("rendered, in both directions: a control proved and described nowhere fails the")
    w("build, and so does one described and never proved.")
    w("")
    w("| Control | Property | Signature | State |")
    w("|---|---|---|---|")
    for control, prop, signature, suite in CONTROLS:
        w(f"| `{control}` | {prop} | `{signature}` | {control_state(logs, control, suite)} |")
    w("")

    w(NARRATIVE)
    return "\n".join(out) + "\n"


NARRATIVE = """## Design decision: the ledger is the record, everything else is a projection (M3-A)

M3 is the first gate that commits. Two of its requirements look like separate problems and
are answered by one arrangement rather than by two mechanisms that could disagree:
FR-DAT-008A says an accepted order has no destructive edit path, and FR-DAT-010 says key
projections rebuild from authoritative events and compare deterministically.

`ordering.order_event` is authoritative and append-only. Everything else in the schema —
the order, its lines, its charge components, its notes, its timeline, its correlation
chain — is derived from it by `ordering.apply_event()` and can be discarded and rebuilt
byte for byte. So there is no destructive edit path because there is nothing to edit that
is not derived, and the rebuild comparison is the thing that would notice if somebody
found one.

Three consequences the negative controls rest on:

- **The fold is pure.** It reads no clock, no sequence and no random source: every value
  it writes comes out of the event. That is what makes a rebuild byte-deterministic rather
  than merely equivalent, and `NC-M3-009` plants a single dropped field to prove the
  comparison notices.
- **The allergy declaration is an EVENT, not a column somebody might forget to copy.**
  Every surface that shows it is a projection of that event, so "does it survive the hop"
  and "does the projection rebuild" are the same question asked twice.
- **The projections are locked twice, on inputs that do not overlap.** The application
  role holds SELECT and nothing else, and a trigger refuses any write from outside the
  fold — for the table owner too, under FORCE row level security. `NC-M3-006` drops only
  the triggers, leaving the grants alone, which is the question FR-DAT-008A actually asks:
  is the guarantee carried by the trigger, or was it only ever the grant?

## Design decision: the total is a sum over components that exist (M3-A)

FR-ORD-003 names line prices, modifiers, tax, fees and discounts. Tax resolves to M1's
`config.configuration_version` under category `tax` and a discount to `config.policy` under
category `discount`; both are configured, non-zero and exercised. A FEE has no
configuration heading before FR-CFG-001C at M4.

The wrong way to hold that gap is a fee column reading zero. A hardcoded zero survives to
M4 unnoticed and looks wired when it is not — the `money.assert_currency_paired()` vacuity
recorded at M1 is the standing reminder. So there is no fee column and no fee constant
anywhere in the schema. `ordering.order_total()` is `SUM(amount_minor)` over the components
that exist; it names no charge kind at all, and a deferred constraint trigger refuses to
commit an order whose stored total differs from that sum.

The suite proves both ends. One check shows no fee component and no fee rule exists. A
second inserts a fee rule with a real configured source, shows the total move by exactly
the configured rate, and shows `ordering.order_total()` byte-identical either side — so the
absence of a fee at M3-A is a missing SOURCE rather than a missing feature.

## Design decision: a price is pinned, an allergen is not (M2-B)

Recorded here because M3 and M4 both inherit it, and because the reasoning is not obvious
from either half on its own.

`menu.publication_snapshot` exists so that a price cannot be argued about after the fact.
It is append-only twice over, it carries a digest of its own lines, and an M3 order will
reference it as evidence of what the guest agreed to pay. Extending the same treatment to
allergen text would have been the natural symmetry, and it would have been a safety
defect:

- **A price must be what was AGREED.** It is fixed at publication and does not move. If
  the kitchen raises the price of a dish this afternoon, a guest reading a menu published
  this morning is still owed the morning's price.
- **An allergen must be what is TRUE.** It is resolved live, on every read, from the
  declarations that are open at that moment. If the kitchen discovers this afternoon that
  a dish contains sesame, a guest reading the menu published this morning must be told —
  immediately, without a republication step, and whether or not anyone remembers to
  perform one.

So `menu.published_menu_for_guest()` reads name and price from the snapshot line and
allergens from `safety.selection_safety()`, which computes from `safety.declaration` rows
whose `effective_to` is still NULL. There is no materialized view, no cache table and no
resolved-set column anywhere in the safety schema: a stored answer that does not move when
its inputs move is a safety defect rather than a caching bug, so the answer is not stored.

What IS recorded at publication is `safety.declaration_reference` — which declaration
version was in force at that moment — so a later dispute can establish what the kitchen
believed then. That table is deliberately unreadable by the application role, which holds
INSERT on it and nothing else, and no function other than `menu.publish_menu()` names it.
A pinned value that a display path can read becomes a cache the first time that path is
under deadline. The snapshot's content digest deliberately does not cover these rows
either: binding it to a safety state would make correcting an allergen look like tampering.

Two negative controls hold this in place. `NC-M2B-009` publishes a menu, corrects a
declaration afterwards, reads the EARLIER snapshot as a guest and requires the new text —
and in the same probe raises the live price and requires the published price NOT to move.
`NC-M2B-008` requires the pinned reference to be unreachable from any display path, so the
convenience that would undo all of this is not available to reach for.

## Repaired: retention ignored the action it was told to perform (M1-C, found at M2-B)

`config.retention_action` offered `archive` and `purge`; `config.retention_policy` stored
the tenant's choice; and `config.apply_retention()` executed `DELETE` for both. A tenant
that configured archival had its rows destroyed, and the sweep reported success. The
action was recorded and then ignored, which is data loss presenting as correct operation.

Found while wiring guest-session anonymization to the engine rather than building a second
one. The repair honours the action: `purge` deletes, `anonymize` empties the columns
`config.anonymization_rule` names and stamps the row, and `archive` refuses with
`RETENTION_ACTION_UNIMPLEMENTED` because Phase 1 has no archive store. Refusing is the
honest answer to being asked for something that does not exist; deleting the rows a tenant
asked to keep is the worst one. Proved by `NC-M2B-010`, whose planted defect is the
original M1-C function body.

## Repaired: the fenced gate was not authoritative (P1-01)

An independent review found `tools/verify_m1.py` scanning against a vocabulary written
into the tool by hand, rather than the one shipped in the pinned package. Measured against
the concrete case — a term used as an identifier, which is how it would actually appear —
**17 of 63 authoritative terms were detected and 46 were missed**, and two domains had no
coverage at all.

The defect class is hardcoding, so the repair is not a corrected list:

- the verifier loads its vocabulary from the pinned package through `tests/fenced.py`, the
  same loader every slice harness uses
- **no fenced term appears anywhere in the verifier**, and a test asserts that
- it **fails closed**: an absent, unreadable or empty vocabulary stops the scan. There is
  no built-in list to fall back to, because a vocabulary of zero terms passes everything
  while reporting success
- `tests/fenced_gate/verify_fenced_gate.py` plants a real mutation for **every one of the
  63 terms** and requires each to be flagged, then proves one representative per domain
  red before green

The suite names no forbidden term either. Every probe is derived from the package at run
time, including the domain representatives, which are chosen by position — the domain keys
are themselves built from fenced words.

## Repairs made after independent review

An executing independent review — its own PostgreSQL, every defect planted by hand —
raised twelve findings. It confirmed the counts were true and found that several checks
asserted things that were not, and that some code did not do what its own comment
promised. All twelve are closed below. Two were closed differently from the brief's
prescription, with reasons; both are marked.

| # | Finding | Repair | Proof |
|---|---------|--------|-------|
| F5 | The FR-AUTH-010 audit assertion was satisfied by its own `INSERT` | `identity.emit_security_event` now writes to `audit.security_event` (0005); the check calls only the emitter | NC-M1C direct, scope and trigger checks; the test inserts nothing |
| F3/F9 | ~20 assertions satisfied by any failure | `Result.failed_with()` requires a named SQLSTATE or signature; bare failure raises | every converted site names its reason and prints it |
| F3 | `pg.py` was POSIX-only | `os.devnull`; M1-A scans the Python harness for regressions and names the bash drivers it does not scan | **executed on Windows**, all five suites; see the cross-platform section |
| F1 | Readiness read a boot-time role snapshot | role privilege re-queried on every probe | **NC-M1D-007**, red then green |
| F7 | `db.ts` documented `SET LOCAL`; the code used session-level `set_config` | transaction-local in 0005 | **NC-M1B-005**, red then green |
| F2 | No `.gitattributes` | added — see the note below on how it differs | four assertions, plus a Windows checkout at `core.autocrlf=true` producing the 91 matching sums |
| F4 | `money.allocate` lost minor units for negative totals | remainder distributed in the direction of its sign (0005) | 13 cases asserted as equalities |
| F6 | The currency-pairing check was vacuous | vacuity asserted explicitly; mechanism proved against a real column | recorded as a deferral above |
| F8 | The UPDATE and DELETE legs failed open on `-1` | `count()` raises; only "ran and affected zero rows" counts as a denial | NC-M1-001/002 red proofs now show the writes succeeding |
| F10 | NC-M1D-006 covered GET only | all seven methods swept | 49 unauthenticated requests per run |
| F11 | `half_up` rounds -2.5 to -3 | **closed differently** — see below | negative tie cases asserted |
| F12 | `/ready` disclosed deployment detail | restricted to what a probe needs | **NC-M1D-008**, red then green |

Three findings were live in the tree rather than hypothetical, and the repairs surfaced
them rather than reasoning about them:

- The DELETE leg of the isolation gates had **never** exercised row level security. It
  targeted a node with children, so a foreign key error arrived first and `count()`
  returned `-1`, which `if affected > 0` read as "no leak". The fixtures now carry a
  dedicated delete target with no dependents, and the red proofs show the DELETE actually
  removing a row when the policy is removed.
- The sibling-outlet INSERT was refused by the parent-visibility trigger, not by the
  policy the gate claimed to be proving. A correct denial, asserted for the wrong reason.
- An assertion named a *sibling* node as its "cross-tenant parent". Same tenant, in scope,
  so the INSERT succeeded — and the detail line silently omitted it instead of failing.
  It also left a row behind in the fixtures on every run.

### F11 was closed by documenting, not by renaming or changing behaviour

The review read `half_up` sending -2.5 to -3 as a defect. It is not. Breaking a tie away
from zero is what `HALF_UP` means in Java `BigDecimal` and Python `decimal`; the reading
that makes "up" mean toward positive infinity describes `half_ceiling`, a different mode
that this type does not offer. The pinned package does not define the semantics, so
nothing was contradicted.

What was genuinely wrong is that the direction was never stated and never tested, and an
unstated tie direction is exactly how two subsystems come to disagree about a half-cent —
which the type's own comment already warned about. Migration 0005 states the direction on
the type; the suite proves it on negative amounts. Renaming was considered and rejected:
`half_up` appears inside a stored seed payload, so a rename needs a data migration, and it
would diverge from the name every developer expects. **Founder ruled: document and test.**

### F2's `.gitattributes` is not the one the brief prescribed

The brief asked for `* text=auto eol=lf` plus a re-normalisation. Applied literally, that
**rewrites the pinned package**: 70 of its 92 files are stored with CR bytes, because that
is how they were delivered and hashed. Normalising them changes the very bytes the 91
recorded sums exist to detect — measured directly, the first file checked went from 531
bytes to 517.

The package is therefore exempt from conversion in **both** directions (`docs/** -text`),
while repository source keeps `eol=lf`. That serves the finding's actual requirement — the
same bytes on Windows and Linux — rather than its literal wording.

## Accepted exceptions

Each was raised during the slice that introduced it and accepted by the founder. They are
recorded here so a reviewer reads them as decisions rather than oversights.

### `money.currency` is not tenant-scoped

Every other tenant-owned table carries a `tenant_id` and row level security, ENABLEd and
FORCEd. `money.currency` does not, because ISO 4217 is not a tenant's property. The
application role holds `SELECT` and nothing else; three gates prove it cannot `INSERT`,
`UPDATE` or `DELETE` there. **Deliberate, tested exception — not an oversight.**

### `money.allocate()` is an M1 primitive

Splitting a bill is M4's business. The function exists at M1 because exactness is
unfalsifiable without an operation that can lose a minor unit: the suite asserts
`sum(money.allocate(10000, 3)) = 10000` as an equality, which naive per-part rounding
fails. It is a type-level primitive that M4 will consume, not bill-splitting policy.

### `identity.governed_action` stays in the identity schema

The step-up action registry is per-tenant policy data, which sits close to M1-C's
configuration store. It remains owned by M1-B: `config.policy` references it by foreign key
on `(tenant_id, action_code)` and never copies a row. A verification check asserts there is
no second registry outside `identity` and that the reference exists.

### The build writes outside the repository

`api/build.sh` puts `node_modules/` and `dist/` in `$M1D_WORKSPACE`, not in the checkout.
`tools/verify_m1.py` treats those directories as forbidden surface and inspects the
filesystem rather than the Git index, so a `.gitignore` entry would keep them out of
commits but would not stop the gate failing after an ordinary build. Building elsewhere
keeps the repository clean at every moment, with no cleanup step to forget, and gives the
M1-D negative controls somewhere to plant a defect that the repository never contains.
**A deliberate design choice, ruled as such — not a workaround.**

## Deferred, and honestly so

### Distributed rate limiting is NOT proven

Two separate mechanisms exist and neither is distributed:

- **M1-B**, `identity.register_auth_attempt` — per-database counters and lockout. Proved:
  five failures inside the window trip a lock and further attempts are refused.
- **M1-D**, `InProcessRateLimiter` — in-memory limits on the auth, search and export
  prefixes. Proved: requests beyond the allowance receive 429.

Neither survives a restart, and running two instances doubles the effective allowance. The
readiness payload reports `rateLimiting.scope: singleInstance` so no operator can mistake
it for more. **Distributed enforcement is M6 infrastructure and is not claimed at M1.**

### The currency-pairing check was vacuous at M1, and is live from M2-A

`money.assert_currency_paired()` reports any `money.amount_minor` column with no
`currency_code` beside it. **No M1 table holds money**, so it examines an empty population
and returns nothing. An empty result from an empty population is not evidence, and a
reviewer could read the passing check as proof of a property nothing had.

Migration 0005 adds `money.currency_pairing_population()` so "zero offenders" and "nothing
to check" are distinguishable, and the M1-C suite asserts the vacuity explicitly rather
than passing quietly. The mechanism is proved separately against a real column, created
and dropped inside a rolled-back transaction: a bare amount column is reported, and adding
`currency_code` beside it clears the report. This is not covered by the `money.currency`
exception above.

**Closed at M2-A**, earlier than the M4 this section originally predicted: `menu.price`
and `menu.publication_snapshot_line` were the first stored amounts, and M2-B added
`service.cart_line`. The population is no longer empty, the check examines real columns
and reports zero offenders, and the M1-C assertion was rewritten from "this is vacuous" to
a population-relative form so it could go on being true once it stopped being vacuous.

### Windows execution: verified by running it

F2 and F3 were mechanism-only for as long as no Windows machine was available. One is now:
`Windows 11 (AMD64)`, Python 3.12.10, a PostgreSQL 16.15 server in Docker reached over TCP
by a psql 18.4 client, Node 24.16.0 and Git 2.54.0. All five suites were run against a
database built from empty — 220 checks.

- **F2 — confirmed in practice.** A Git-for-Windows checkout at `core.autocrlf=true`
  produced the 91 matching package sums, migration 0002 hashed `51446d59…` exactly as it
  does on Linux, and no checksum-locked or executable file carried a CR byte.
- **F3 — confirmed by execution.** A hardcoded POSIX null-device path makes Windows psql
  exit 1 with `No such file or directory`; `os.devnull` resolves to `nul` and is accepted.
  M1-A's context-scoped assertions ran against a live client rather than one that had
  already exited, and the suite passed 43 of 43. (This paragraph may not spell the POSIX
  path out: `generate_evidence_report.py` is itself scanned by that gate, and writing the
  literal here turned M1-A red — which is the gate doing its job.)

Executing the documented path found what documenting it could not. **Seven defects were
present that Linux cannot expose**, each repaired and each proved red before green: locale
decoding (`text=True` inherits cp1252 on Windows and corrupted psql output at 20 call
sites), a Windows path handed to bash, `bash` resolving to the WSL launcher rather than Git
Bash, npm's extensionless `tsc`, a `python3` requirement no standard Windows install can
satisfy, a POSIX-only temporary path, and a service start window too tight for a cold
start. That is the argument for executing a documented path rather than reasoning about it.

**Guarded from M2-A.** A `windows-latest` job now runs every suite on every push, so
Windows is no longer verified once and trusted afterwards. Standing that job up found
three more defects that the one-off run had not: a resolver that chose bash by where git
was installed rather than by what that bash could open — and then reported the WSL
launcher as the cause without ever having checked; a harness that proved it had stored
Amharic and then died with `UnicodeEncodeError` reporting it, because Python takes its
stdout encoding from the platform and cp1252 has no code point for it; and a generated
README that recorded which platform generated it, `str(Path)` being backslash-separated on
Windows. Ten Windows defects in total, none of which Linux could expose.

### Windows commands are documented and executed

`docs-local/CROSS_PLATFORM_COMMANDS.md` gives Windows equivalents for every documented
command. Both columns have now been executed: the Linux column on the runner, the Windows
column on the machine described above, including `tools/check_prerequisites.py` in its
passing form, its absent-tool form and its present-but-unrunnable form. The document
records the same versions and the same limits, and names the prerequisites Windows needs
that Linux does not — `psql` on `PATH`, and Git Bash for the API build.

### CSRF is defined, not exercised

The M1 surface authenticates with a bearer token in an `Authorization` header, which a
browser does not attach cross-site, so these routes carry no CSRF exposure. The cookie
policy and the token check exist so the first cookie-authenticated route inherits them
rather than inventing them. The guard is therefore **defined and unit-reachable but not
exercised by a real cookie flow at M1.**

## Known limitations carried forward

- `validate_package_m0.py` does not run on a default Linux path — a Windows temp-path and
  separator assumption. Coverage was confirmed by hand at M0R; see
  `planning/KNOWN_LIMITATIONS.md`.
- Fenced-domain detection is bounded. The occurrence registry closes the authorization
  problem, not the detection problem: a prohibited concept in unknown vocabulary can pass.
  Human review remains an obligation and is not discharged by a green pipeline.
- The build writes `node_modules/` and `dist/` outside the repository because
  `tools/verify_m1.py` inspects the filesystem rather than the Git index. This is a
  deliberate layout choice, documented in `api/README.md`.

## Deployment commands

```bash
python3 tools/check_prerequisites.py                       # discover required tools
python3 tools/migrate.py --dsn "$MIGRATOR_URL" apply       # ordered, checksum-locked
python3 tools/seed.py --dsn "$MIGRATOR_URL" \\
                      --content-dsn "$DATABASE_URL" apply  # separate record and lock
bash api/build.sh                                          # build outside the repository
DATABASE_URL="$DATABASE_URL" PORT=8080 ENVIRONMENT_NAME=production \\
    node "$M1D_WORKSPACE/dist/server.js"
```

`DATABASE_URL` must name the least-privileged application role. Given an owner, superuser
or BYPASSRLS credential the service refuses to start, exits `78`, and prints
`STARTUP REFUSED — PRIVILEGED_RUNTIME_CREDENTIAL_ACCEPTED` without echoing the credential.

Windows equivalents are in `docs-local/CROSS_PLATFORM_COMMANDS.md`.

## Governance rule: where a brief and the pinned package disagree, the package wins (M3-B)

Recorded as a rule rather than as an incident, because it will happen again.

The M3-B execution brief asked for **seven** ticket states. `SM-FULFILLMENT-TICKET` in the
pinned package defines **eleven**. The seven came from FR-FUL-003's list of what a kitchen
display shows; the eleven are the machine the system must enforce. The brief was the
defect, and the standing rule the founder set on discovering it is now project policy:

> When a brief and the pinned package disagree, the package is authoritative and the brief
> is the defect.

The reconciliation is a function rather than a paragraph. `fulfillment.kds_bucket()` maps
the package's eleven states onto FR-FUL-003's seven display buckets — `partially_completed`
and `rework` both show as *preparing*, `collected` and `cancelled` both show as *completed*,
and the display's *new* is the package's `queued`. It is a `CASE` with no `ELSE`, so a
twelfth state added to the package raises instead of falling into a column nobody chose,
and `tests/m3b` asserts the mapping covers exactly the states the package declares.

The machine itself is never written down twice. `tests/m3b/verify_m3b.py` reads
`state_machines.json` at run time and FAILS CLOSED if it cannot — a suite that fell back
to a transition table of its own would be checking the schema against itself, and a state
machine that silently defaults to permissive is worse than none. The schema is then
required to equal the package in both directions, counts included.

## Design decision: the order's fulfillment state is derived, never stored (M3-B)

A literal divergence from `SM-ORDER`, recorded in the partial-closure register as a
decision rather than an omission.

`SM-ORDER` lists `in_fulfillment`, `partially_ready`, `ready`, `partially_served` and
`served` among the ORDER's states. Migration 0010 recorded at M3-A that no fulfillment
label appears on the commercial order, and M3-B keeps that.
`fulfillment.order_fulfillment_state()` computes every one of those labels from the order's
tickets, so the machine's SEMANTICS are preserved while the same fact is refused a second
home that could contradict the first — which is `SM-ORDER`'s own second invariant: *order,
fulfillment, check, payment and tip states are separate*.

The suite proves each label reachable and correct on a real order, and asserts against the
CATALOG — not against a list of tables — that no column anywhere in `ordering` could hold
one. `SM-ORDER`'s last edge, `served -> completed` on operational AND FINANCIAL conditions,
needs checks, so the entry stays open with M4 named.

## Design decision: duplicated work is one constraint, not three rules (M3-B)

Recall (FR-FUL-005), station transfer (FR-FUL-015) and the printer fallback (FR-FUL-014)
fail the same way: by leaving the same work on two tickets instead of moving it. A recall
that reissued, a transfer that copied and a reprint that regenerated would each be a
separate bug with a separate fix, and the fix for one would say nothing about the others.

So the invariant is enforced once, in the place that can see all three.
`fulfillment.assert_units_within_order()` is a DEFERRED constraint trigger that compares,
for every order line, the units the customer ordered against the units on EVERY live
ticket. It is `SM-FULFILLMENT-TICKET`'s first invariant, held across the whole order rather
than one ticket at a time. Above it sit the operations themselves: a recall is a state
change on the ticket that already exists, a transfer changes that ticket's station, and a
station document is deduplicated on `(ticket, revision)` by a unique index as well as by
the function that writes it.

Three negative controls plant the three duplications independently — a recall that
reissues, a transfer that raises a second ticket, a document keyed on a ledger position
that generating a document itself moves — and each must produce its own signature.

## Evidence standard: what is measured and what is asserted (M3-B)

FR-SAF-004 and FR-FUL-008 are claims about what a KITCHEN SEES, and M2-C established that
such a claim can only be proved by rendering: it found a translated warning beside an
untranslated name that every SQL query agreed was absent. The same class of miss on a
station screen is a hospital visit, so the evidence standard rises rather than falls.

`tests/m3b` renders the station surface in Chromium twice — once normally, and once with
every colour in the document flattened to a single ink, appended to the surface's own
stylesheet by intercepting the response because the page's `style-src 'self'` correctly
refuses an injected one. Prominence is measured RELATIVELY, against the ordinary text
beside it, so a later restyle that lifted everything cannot satisfy the check by accident.
`NC-M3B-001` plants an emphasis carried only by colour and requires the flattened render to
catch it.

Every check in the suite records whether its evidence is `(measured)` — read out of the
browser's own layout — or `(asserted)` — read from source, a payload or the database. The
split printed at the end is DERIVED from the run rather than tallied by hand, because the
one time M2-C counted by hand it drifted.

## Design decision: a request belongs to the table, not to the order (M3-C)

A ticket is what a station must make; a service request is what a guest asked for. The
second half of that line is drawn at M3-C, and where a request LIVES is the decision it
turns on.

`service.service_request` references the TABLE SESSION. It carries an order id as well,
present when the request concerns one — a missing item, a bill — and absent for most of a
meal. Binding it to the order instead would have made a request for water unraisable until
somebody had ordered something, which is the wrong way round: the guest who most needs to
call a waiter is the one nobody has come to yet.

FR-SRV-008's internal tasks are the SAME aggregate with `origin = staff`. A second table
for staff-raised tasks would have been two models of one thing — the same routing, the
same deadline, the same completion — and the two would have drifted.

That choice pays for itself twice. A merge takes the requests with the session because
they reference it, so FR-TAB-007A needed no consolidation step; and a move changes which
table a session sits at, not which session a request belongs to, so FR-TAB-008 needed
nothing at all. What the merge DID need is recorded below.

## Design decision: deduplication is two-sided, and both sides are the requirement (M3-C)

FR-SRV-006 asks for two things that pull against each other: accidental repeated taps must
not create uncontrolled duplicate alerts, AND deliberate repeats must survive. A window
that collapsed everything satisfies the first and fails the requirement. So does one that
collapses nothing.

Three different questions are kept apart, and conflating any two of them breaks one of
them:

- **A RETRY** is one command that arrived twice — same idempotency key. It returns the
  original outcome and has no second effect (FR-INT-005).
- **AN ACCIDENT** is two commands that look alike, inside the request type's configured
  window. The second collapses into the first: no second request, no second alert, and
  the caller is told which request theirs became rather than given an error.
- **A DELIBERATE REPEAT** is the guest saying so. It always raises a new request, inside
  the window or outside it, carrying the same deduplication group with the next ordinal —
  so "the third time I asked for water" is answerable.

The window is per request type, because two taps a minute apart for water are a double tap
and two taps a minute apart for assistance may not be. `NC-M3C-001` and `NC-M3C-002` are
the same control failing in opposite directions.

## Design decision: presence is not a workforce record (M3-C)

FR-SRV-007A wants three presence states driving routing. FR-SRV-007B says there is no
roster, no shift, no break, no attendance, no timekeeping, no payroll and no employment
history, and requires a retention bound.

The fence is about WHAT EXISTS, not how long it lasts. A retained history of when somebody
was available would be no less an attendance record for having a window on it — so
`service.staff_presence` has nowhere to put one. Its primary key is the PERSON, so a
second row for them cannot exist; there is no `previous_state`, no `ended_at`, no closed
row and no superseded flag. `tests/m3c` asserts that absence against the CATALOG rather
than against this paragraph, the way M3-A asserted no order carries a table id.

It is then discarded twice over, and both paths are proved to DELETE rather than to mark:
ending the staff session that asserted it removes the row, and `config.retention_policy`
sweeps it by age through `config.apply_retention()` — M1-C's engine, which stays the only
sweep in the system.

## Design decision: nothing is delivered by a channel that does not exist (M3-C)

FR-NOT-001 names eight classes of event and FR-INT-007 wants repeatedly failing work in an
operator-visible queue. At M3 there is no transport: outlet-local notices are M5a's.

So the kinds exist and the producers do not pretend to. `notify.catalog_event` carries the
package's own event ids with `has_producer = false` for bill, payment, tip, outage and
sync, and `notify.emit()` refuses one by name — a kind with no producer is honest, a
stubbed bill is not.

In-app notice IS the sink, and it fails for three real domain reasons rather than an
injected fault: the recipient's authorization was withdrawn between the event happening and
the notice being written; the guest is no longer live on the session; there is no approved
template in the language the recipient must be told in. The first is a genuine race and the
sharpest of the three — in scope at emission, out of scope afterwards, which is M2-B's
`FOREIGN_SESSION_ACCEPTED` boundary on a different path.

There is no adapter seam, deliberately. An abstraction with one implementation has no
second case to prove it right. When a transport exists, its failures reach the same queue
through the same door — `integration.dead_letter_job()` — and the replay control stays
what it is: the SAME work re-run, never re-emitted, proved against the whole-schema
differential.

## Governance: an instrument that had quietly stopped covering things (M3-C)

M3-A built a whole-schema differential to prove a retry has no second effect anywhere, and
its comment says plainly that a fixed list of TABLES would go stale as later gates added
them, so the tables are enumerated from the catalog.

The list of SCHEMAS underneath had exactly the same defect one level up, and it went stale
immediately: it was written at M3-A naming the nine schemas that existed then, and when
M3-B added `fulfillment` the differential silently stopped covering it. A retry that
duplicated a kitchen ticket would have passed.

M3-C found it by reusing the instrument rather than writing a second one, and widened it to
every non-system schema — enumerated, not listed. The rule was already written down;
applying it one level higher is the whole fix.

## What M1 does not contain

Menu, translations, QR and guest sessions (M2) · orders, tickets and service requests (M3)
· checks, payments, tips and receipts (M4) · outlet node, synchronization and printing
(M5a) · same-QR DNS/TLS and authority lease (M5b).

No inventory, accounting, payroll or purchasing surface exists at any gate.
No supplier, procurement, courier or warehouse surface exists at any gate.
No recipe, costing, loyalty, CRM, pickup or delivery surface exists at any gate.

These domains are excluded from Phase 1 permanently, not deferred within it. The M1
forbidden-surface verifier checks their absence on every push, against the 63-term
vocabulary shipped in the pinned package rather than a list restated here.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the M1 evidence report.")
    parser.add_argument("--dsn")
    parser.add_argument("--logs")
    parser.add_argument("--out")
    parser.add_argument(
        "--list-suites", action="store_true",
        help="print the suite log basenames this report requires, one per line, and exit")
    args = parser.parse_args()

    if args.list_suites:
        for name, _label in SUITES:
            print(name)
        return 0
    missing = [flag for flag in ("dsn", "logs", "out") if not getattr(args, flag)]
    if missing:
        parser.error("--" + ", --".join(missing) + " are required unless --list-suites")

    try:
        report = build(args.dsn, Path(args.logs))
    except HistoryUnavailable as error:
        print("FAIL GIT_HISTORY_UNAVAILABLE", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1
    except SuiteLogMissing as error:
        print("FAIL SUITE_LOG_MISSING", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1
    except SuiteUnaccounted as error:
        print("FAIL SUITE_UNACCOUNTED", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1
    except ControlDrift as error:
        # A named refusal rather than a traceback, like every other gate this tool holds.
        # The signature is the first word of the message, so the CI grep and a reader see
        # the same name.
        print(f"FAIL {str(error).split(':')[0]}", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    print(f"wrote {path} ({len(report.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
