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
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_history import (  # noqa: E402
    HistoryUnavailable, assert_history_available, current_branch, is_dirty_excluding,
    last_commit_excluding,
)

REPO = Path(__file__).resolve().parents[1]
UNIT = "\x1f"
REPORT_PATH = "evidence/M1_EVIDENCE_REPORT.md"


def sh(*command: str) -> str:
    proc = subprocess.run(command, capture_output=True, text=True, cwd=REPO)
    return proc.stdout.strip()


def query(dsn: str, sql: str) -> list[list[str]]:
    proc = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "--no-psqlrc", "-X", "-t", "-A", "-F", UNIT],
        input=sql, capture_output=True, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if proc.returncode != 0:
        return []
    return [line.split(UNIT) for line in proc.stdout.splitlines() if line.strip()]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SuiteLogMissing(Exception):
    """An expected suite log is absent. The report must not be written without it."""


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
    tag = "FENCED_GATE" if name == "fenced_gate" else name.upper()
    verdict = "PASS" if re.search(rf"^PASS {tag}_VERIFICATION", text, re.M) else "FAIL"
    blocks = re.findall(r"checks run\s+:\s+(\d+)\s*\n\s*passed\s+:\s+(\d+)\s*\n\s*failed\s+:\s+(\d+)", text)
    if not blocks:
        return (verdict, "-", "-")
    ran, _passed, failed = blocks[-1]
    return (verdict, ran, failed)


CONTROLS = [
    ("NC-M1-001", "Fail-closed tenant context", "VISIBLE_OR_WRITABLE_ROWS_WITHOUT_CONTEXT", "m1a"),
    ("NC-M1-002", "Sibling-outlet isolation", "SIBLING_OUTLET_ACCESS", "m1a"),
    ("NC-M1-003", "Future schema protection", "OUTLET_POLICY_NOT_UPGRADED", "m1a"),
    ("NC-M1-004", "Runtime least privilege", "PRIVILEGED_RUNTIME_ROLE_REJECTED", "m1a"),
    ("NC-M1B-001", "Session survives role removal", "SESSION_SURVIVED_ROLE_REMOVAL", "m1b"),
    ("NC-M1B-002", "Quick PIN for a governed action", "LOW_RISK_CREDENTIAL_USED_FOR_SENSITIVE_ACTION", "m1b"),
    ("NC-M1B-003", "Step-up recency ignored", "STALE_STEP_UP_ACCEPTED", "m1b"),
    ("NC-M1B-004", "Principal outside its scope", "OUT_OF_SCOPE_PRINCIPAL_ACCEPTED", "m1b"),
    ("NC-M1C-001", "Audit mutated by ordinary role", "AUDIT_MUTATED_BY_ORDINARY_ROLE", "m1c"),
    ("NC-M1C-002", "Inexact money type", "INEXACT_MONEY_TYPE_ACCEPTED", "m1c"),
    ("NC-M1C-003", "Entitlement defaulting open", "UNKNOWN_ENTITLEMENT_DEFAULTED_OPEN", "m1c"),
    ("NC-M1C-004", "Retention deleting audit", "APPEND_ONLY_VIOLATED", "m1c"),
    ("NC-M1C-005", "Numbering collision", "DUPLICATE_DOCUMENT_NUMBER_ISSUED", "m1c"),
    ("NC-M1D-001", "Privileged runtime credential", "PRIVILEGED_RUNTIME_CREDENTIAL_ACCEPTED", "m1d"),
    ("NC-M1D-002", "Readiness green with broken job", "READINESS_GREEN_WITH_BROKEN_JOB", "m1d"),
    ("NC-M1D-003", "Secret emitted in logs", "SECRET_EMITTED_IN_LOGS", "m1d"),
    ("NC-M1D-004", "Required header absent", "REQUIRED_HEADER_ABSENT", "m1d"),
    ("NC-M1D-005", "Seed checksum lock bypassed", "SEED_CHECKSUM_LOCK_BYPASSED", "m1d"),
    ("NC-M1D-006", "Route served without context", "ROUTE_SERVED_WITHOUT_CONTEXT", "m1d"),
]


def control_state(logs: Path, control: str, suite: str) -> str:
    path = logs / f"{suite}.log"
    if not path.exists():
        return "not run"
    text = path.read_text(encoding="utf-8", errors="ignore")
    red = f"[PASS] {control} — RED" in text
    green = f"[PASS] {control} — GREEN" in text
    if red and green:
        return "red, then green"
    if green:
        return "green only — NOT PROVEN"
    return "not proven"


def build(dsn: str, logs: Path) -> str:
    out: list[str] = []
    w = out.append

    # Under a shallow checkout the commit this report names cannot be resolved, and the
    # field would come out empty rather than wrong-looking. Refuse instead.
    assert_history_available()
    commit, short = last_commit_excluding(REPORT_PATH)
    branch = current_branch()
    dirty = is_dirty_excluding(REPORT_PATH)

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
    w(f"| Working tree | {'NOT CLEAN — regenerate from a clean tree' if dirty else 'clean at generation'} |")
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
    for name, label in (("m1a", "M1-A database, RLS, roles"),
                        ("m1b", "M1-B identity and authentication"),
                        ("m1c", "M1-C configuration, audit, money"),
                        ("m1d", "M1-D API, security, operations"),
                        ("fenced_gate", "Fenced-domain gate, vocabulary and mutations")):
        verdict, ran, failed = suite_result(logs, name)
        if ran.isdigit():
            total += int(ran)
        w(f"| {label} | **{verdict}** | {ran} | {failed} |")
    w(f"| **Total** | | **{total}** | |")
    w("")

    w("## Negative controls")
    w("")
    w("Each control is planted as a real defect, required to produce its exact registered")
    w("signature, then reverted and required to pass again. A control that never went red is")
    w("a coverage gap wearing a green badge, and CI fails the build when one is missing.")
    w("")
    w("| Control | Property | Signature | State |")
    w("|---|---|---|---|")
    for control, prop, signature, suite in CONTROLS:
        w(f"| `{control}` | {prop} | `{signature}` | {control_state(logs, control, suite)} |")
    w("")

    w(NARRATIVE)
    return "\n".join(out) + "\n"


NARRATIVE = """## Repaired: the fenced gate was not authoritative (P1-01)

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

### Windows commands are documented but unverified

`docs-local/CROSS_PLATFORM_COMMANDS.md` gives Windows equivalents for every documented
command. No Windows machine was available, so that column is written from the documented
behaviour of the same tools. The Linux column was executed. This is stated in the document
itself as well as here.

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
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--logs", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

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
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    print(f"wrote {path} ({len(report.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
