#!/usr/bin/env python3
"""M1-A verification harness.

Runs against a real PostgreSQL through the actual application role (FR-DAT-017).

Every negative control is proved RED before it is trusted GREEN: the gate is run
against the correct system, a deliberate defect is then injected, the gate is
required to emit its exact registered signature, the defect is reverted, and the
gate is required to pass again. A control that cannot fail is a coverage gap, so a
control that never went red is reported as a failure of this harness.

Usage:
    M1A_ADMIN_DSN=... M1A_MIGRATOR_DSN=... M1A_APP_DSN=... python3 tests/m1a/verify_m1a.py
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gates import (
    FOREIGN_NODE,
    OUTLET_A1, OUTLET_A2, SIBLING_NODE, TENANT_ACME,
    cross_tenant_gate, rls_absent_context_gate, rls_alter_added_outlet_gate,
    rls_sibling_outlet_gate, runtime_role_gate,
)
from fenced import fenced_identifier_pattern  # noqa: E402
from pg import CommandUnreadable, ProbeFailed, count, run, run_command  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "migrations" / "0001_organizational_model_and_rls.sql"
PACKAGE = REPO / "docs" / "Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9"


ADMIN = os.environ["M1A_ADMIN_DSN"]
MIGRATOR = os.environ["M1A_MIGRATOR_DSN"]
APP = os.environ["M1A_APP_DSN"]

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if detail:
        for line in detail.splitlines():
            print(f"         {line}")


def migrate(dsn: str, command: str) -> subprocess.CompletedProcess:
    # run_command guarantees both streams are readable or raises with the reason. The
    # assertions below read proc.stderr for a signature; on Windows that came back as
    # None and this function returned it anyway, so the failure surfaced as a TypeError
    # at the call site rather than as a named fault here.
    return run_command(
        [sys.executable, str(REPO / "tools" / "migrate.py"), "--dsn", dsn,
         "--migrations", str(REPO / "migrations"), command])


# ===========================================================================
# 1. Migration
# ===========================================================================

def section_migration() -> None:
    print("\n--- 1. Migration history (FR-DAT-001, FR-DAT-016) ---")

    applied = count(MIGRATOR, "SELECT count(*) FROM migration.schema_migrations;")
    has_0001 = count(MIGRATOR, "SELECT count(*) FROM migration.schema_migrations WHERE version = 1;")
    on_disk = len(list((REPO / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")))
    record("0001 applied to a database built from empty", has_0001 == 1 and applied == on_disk,
           f"version 0001 recorded; {applied} of {on_disk} migration(s) on disk applied")

    res = run(MIGRATOR, "SELECT version, filename FROM migration.schema_migrations ORDER BY version;")
    first = res.rows[0] if res.rows else ["", ""]
    record("history begins at 0001", first[0] == "1",
           f"first recorded version is {first[0]} ({first[1]})")

    # Checksum lock: edit an applied migration and require preflight to refuse.
    original = MIGRATION.read_bytes()
    try:
        MIGRATION.write_bytes(original + b"\n-- deliberate edit to an applied migration\n")
        proc = migrate(MIGRATOR, "preflight")
        tripped = proc.returncode != 0 and "MIGRATION_CHECKSUM_MISMATCH" in proc.stderr
        record("checksum lock rejects an edited applied migration", tripped,
               proc.stderr.strip().splitlines()[0] if proc.stderr.strip() else "no signature emitted")

        proc = migrate(MIGRATOR, "apply")
        record("apply refuses to proceed while the history is broken",
               proc.returncode != 0 and "MIGRATION_CHECKSUM_MISMATCH" in proc.stderr,
               "preflight runs before any migration is applied")
    finally:
        MIGRATION.write_bytes(original)

    proc = migrate(MIGRATOR, "preflight")
    record("checksum lock passes once the file is restored",
           proc.returncode == 0, proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else "")

    # Forward-only: the runner offers no downgrade path at all.
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "migrate.py"), "--dsn", MIGRATOR, "down"],
        capture_output=True, text=True, encoding="utf-8")
    record("runner exposes no rollback command", proc.returncode != 0,
           "forward-only: recovery is by restore, not reverse migration")

    # The frozen v1.1 history must be absent.
    legacy = count(MIGRATOR, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname IN ('django_migrations','alembic_version','knex_migrations',
                            'schema_version','flyway_schema_history');
    """)
    record("no v1.1 migration history imported (FR-DAT-001, FR-GOV-006)", legacy == 0,
           f"{legacy} legacy history table(s) present")


# ===========================================================================
# 2. Row level security with populated fixtures
# ===========================================================================

def section_rls() -> None:
    print("\n--- 2. Tenant isolation and RLS (FR-TEN-001, FR-SEC-001, FR-SEC-002A) ---")

    populated = count(APP, "SELECT count(*) FROM org.org_node;", tenant=TENANT_ACME, outlet=OUTLET_A1)
    total = count(ADMIN, "SELECT count(*) FROM org.org_node;")
    record("fixtures are populated, so isolation is not vacuous",
           total >= 15 and populated >= 1,
           f"{total} node(s) exist in total; {populated} visible under ACME/A1 context")

    for name, gate, dsn in (
        ("cross-tenant denied for SELECT/INSERT/UPDATE/DELETE", cross_tenant_gate, APP),
        ("sibling-outlet denied for SELECT/INSERT/UPDATE/DELETE", rls_sibling_outlet_gate, APP),
        ("no rows visible or writable without context", rls_absent_context_gate, APP),
        ("every outlet-scoped table has a forced outlet-aware policy", rls_alter_added_outlet_gate, APP),
    ):
        ok, signature, detail = gate(dsn)
        record(name, ok, detail if ok else f"{signature}: {detail}")

    ok, signature, detail = runtime_role_gate(APP)
    record("runtime role is least-privileged", ok, detail if ok else f"{signature}: {detail}")


# ===========================================================================
# 3. Data architecture
# ===========================================================================

def section_data_architecture() -> None:
    print("\n--- 3. Identifiers, timestamps, concurrency, lifecycle, constraints ---")
    ctx = dict(tenant=TENANT_ACME, outlet=OUTLET_A1)

    # FR-DAT-003 — opaque keys, human numbers in separate columns.
    non_uuid_pk = count(ADMIN, """
        SELECT count(*) FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage k ON k.constraint_name = tc.constraint_name
        JOIN information_schema.columns c
          ON c.table_schema = k.table_schema AND c.table_name = k.table_name
         AND c.column_name = k.column_name
        WHERE tc.table_schema = 'org' AND tc.constraint_type = 'PRIMARY KEY'
          AND c.data_type <> 'uuid';
    """)
    record("all primary keys are opaque UUIDs (FR-DAT-003)", non_uuid_pk == 0,
           f"{non_uuid_pk} non-uuid primary key column(s)")

    human = count(ADMIN, """
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'org'
          AND column_name IN ('tenant_code','reference_code','registration_code');
    """)
    record("human numbers live in their own columns (FR-DAT-003)", human >= 3,
           f"{human} human-number column(s), none of them a key")

    # FR-DAT-004 — UTC instants plus outlet timezone context.
    naive = count(ADMIN, """
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'org' AND data_type = 'timestamp without time zone';
    """)
    tz = run(APP, f"""
        SELECT timezone FROM org.outlet_profile WHERE outlet_id = '{OUTLET_A1}';
    """, **ctx)
    record("timestamps are UTC instants with outlet timezone context (FR-DAT-004)",
           naive == 0 and tz.scalar == "Africa/Addis_Ababa",
           f"{naive} naive timestamp column(s); outlet A1 timezone is {tz.scalar}")

    bad_tz = run(APP, f"""
        UPDATE org.outlet_profile SET timezone = 'Mars/Olympus_Mons'
        WHERE outlet_id = '{OUTLET_A1}';
    """, **ctx)
    record("an invalid timezone is rejected", bad_tz.failed_with("INVALID_TIMEZONE"),
           f"refused by INVALID_TIMEZONE: {bad_tz.why()}")

    # FR-DAT-007 — optimistic concurrency.
    version = run(APP, f"SELECT row_version FROM org.org_node WHERE id = '{OUTLET_A1}';", **ctx).scalar
    stale = run(APP, f"""
        UPDATE org.org_node SET display_name = 'Renamed', row_version = {int(version) - 1}
        WHERE id = '{OUTLET_A1}';
    """, **ctx)
    fresh = run(APP, f"""
        UPDATE org.org_node SET display_name = 'Bole Branch (renamed)', row_version = {version}
        WHERE id = '{OUTLET_A1}';
    """, **ctx)
    after = run(APP, f"SELECT row_version FROM org.org_node WHERE id = '{OUTLET_A1}';", **ctx).scalar
    stale_rejected = (not stale.ok) and stale.sqlstate_is("HS409")
    record("a stale expected version raises an explicit conflict (FR-DAT-007)",
           stale_rejected and fresh.ok and after == str(int(version) + 1),
           f"stale update {'rejected with SQLSTATE HS409' if stale_rejected else 'NOT rejected as expected'}; "
           f"correct version {version} {'accepted' if fresh.ok else 'REJECTED'} and row_version is now {after}")

    # FR-DAT-009 — soft lifecycle preserves references.
    child_before = count(APP, f"""
        SELECT count(*) FROM org.org_node WHERE parent_id = 'aaaa1101-0000-4000-8000-000000000001';
    """, **ctx)
    deact = run(APP, """
        UPDATE org.org_node
        SET status = 'inactive', deactivated_at = now(),
            row_version = (SELECT row_version FROM org.org_node
                           WHERE id = 'aaaa1101-0000-4000-8000-000000000001')
        WHERE id = 'aaaa1101-0000-4000-8000-000000000001';
    """, **ctx)
    child_after = count(APP, f"""
        SELECT count(*) FROM org.org_node WHERE parent_id = 'aaaa1101-0000-4000-8000-000000000001';
    """, **ctx)
    record("deactivating master data preserves references (FR-DAT-009)",
           deact.ok and child_before == child_after and child_after > 0,
           f"{child_after} child row(s) still resolve after the parent was deactivated")

    inconsistent = run(APP, """
        UPDATE org.org_node SET status = 'inactive', deactivated_at = NULL,
               row_version = (SELECT row_version FROM org.org_node WHERE id = 'aaaa1104-0000-4000-8000-000000000001')
        WHERE id = 'aaaa1104-0000-4000-8000-000000000001';
    """, **ctx)
    record("an inconsistent lifecycle state is rejected",
           inconsistent.failed_with("23514", "org_node_lifecycle_consistent"),
           f"refused by the status/deactivated_at CHECK: {inconsistent.why()}")

    # FR-DAT-002 — constraints.
    # Rolled back, so a probe that is ABLE to succeed cannot leave a row behind. The
    # cross-tenant probe previously named a SIBLING node as its "cross tenant parent" —
    # same tenant, in scope, so it succeeded, and the assertion quietly dropped it from
    # the detail line instead of failing. It now names a genuinely foreign parent.
    cross = run(APP, f"""
        INSERT INTO org.org_node (tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{TENANT_ACME}', '{FOREIGN_NODE}', 'dining_table', 'T-XT', 'Foreign parent');
    """, tenant=TENANT_ACME, outlet=OUTLET_A2, rollback=True)
    dup = run(APP, """
        INSERT INTO org.org_node (tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('%s', '%s', 'dining_table', 'T-11', 'Duplicate code');
    """ % (TENANT_ACME, OUTLET_A2), tenant=TENANT_ACME, outlet=OUTLET_A2, rollback=True)
    blank = run(APP, f"""
        INSERT INTO org.org_node (tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{TENANT_ACME}', '{OUTLET_A1}', 'dining_table', '  ', 'Blank code');
    """, rollback=True, **ctx)
    record("constraints reject invalid rows (FR-DAT-002)",
           dup.failed_with("23505") and blank.failed_with("23514")
           and cross.failed_with("PARENT_NOT_VISIBLE"),
           f"duplicate reference_code: {dup.why()}; blank reference_code: {blank.why()}; "
           f"foreign-tenant parent: {cross.why()}")

    # Cycles and outlet nesting.
    cycle = run(APP, """
        UPDATE org.org_node SET parent_id = 'aaaa1103-0000-4000-8000-000000000001',
               row_version = (SELECT row_version FROM org.org_node WHERE id = 'aaaa1101-0000-4000-8000-000000000001')
        WHERE id = 'aaaa1101-0000-4000-8000-000000000001';
    """, **ctx)
    record("a hierarchy cycle is refused", cycle.failed_with("ORG_CYCLE"),
           f"refused by ORG_CYCLE: {cycle.why()}")

    # FR-TEN-002A — depth is not fixed.
    depth = run(APP, f"""
        SELECT max(depth) FROM org.org_closure WHERE ancestor_id = '{OUTLET_A1}';
    """, **ctx).scalar
    record("hierarchy depth is configurable, not fixed (FR-TEN-002A)",
           depth is not None and int(depth) >= 3,
           f"outlet A1 has descendants {depth} level(s) deep, reached without a fixed-level join")

    kinds = count(ADMIN, "SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid WHERE t.typname='node_kind';")
    record("all six required entity kinds exist (FR-TEN-002A)", kinds >= 6,
           f"{kinds} node kinds defined")

    # FR-TEN-002B — no fenced-domain entity, at any gate. The vocabulary is loaded from
    # the pinned package rather than restated here: a second copy could drift from the
    # registry the package validates against.
    pattern, term_count = fenced_identifier_pattern()
    forbidden = count(ADMIN, f"""
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
          AND (table_name ~* '{pattern}' OR column_name ~* '{pattern}');
    """)
    record("no fenced-domain table or column exists (FR-TEN-002B)", forbidden == 0,
           f"{forbidden} fenced identifier(s) found; vocabulary of {term_count} terms "
           f"loaded from the pinned package registry")


# ===========================================================================
# 4. Negative controls — each proved red, then green
# ===========================================================================

def prove_control(control: str, gate, dsn_for_gate, break_sql: str, revert_sql: str,
                  signature: str, *, gate_dsn_when_broken=None) -> None:
    """Run gate clean, inject the defect, require the exact signature, revert, re-run."""
    ok, _, detail = gate(dsn_for_gate)
    if not ok:
        record(f"{control} — baseline", False, f"gate already failing before the break: {detail}")
        return

    broke = run(ADMIN, break_sql)
    if not broke.ok:
        record(f"{control} — inject defect", False, f"could not plant the break: {broke.err}")
        return

    try:
        red_ok, red_signature, red_detail = gate(gate_dsn_when_broken or dsn_for_gate)
        went_red = (not red_ok) and red_signature == signature
        record(f"{control} — RED with the defect planted", went_red,
               f"{red_signature or '(gate still passed)'}: {red_detail}")
    finally:
        reverted = run(ADMIN, revert_sql)

    if not reverted.ok:
        record(f"{control} — revert", False, f"could not revert the break: {reverted.err}")
        return

    green_ok, green_signature, green_detail = gate(dsn_for_gate)
    record(f"{control} — GREEN after revert", green_ok,
           green_detail if green_ok else f"{green_signature}: {green_detail}")


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def section_cross_platform() -> None:
    """F2 and F3 — the repository must behave the same on Windows as it does here.

    Neither of these can be fully proved without a Windows machine, and this harness is
    running on Linux. What CAN be proved here is the mechanism: that Git is configured to
    hand a Windows checkout the same bytes it hands this one, and that the harness itself
    contains no path that only resolves on POSIX. Both are asserted, not assumed.
    """
    print("\n--- 5. Cross-platform integrity (F2, F3) ---")

    attributes = REPO / ".gitattributes"
    record("a .gitattributes decides line endings, rather than the cloning machine",
           attributes.is_file(),
           "core.autocrlf=true is the Git-for-Windows default; without this file nothing "
           "overrides it")

    # Checksum-locked and executable files must arrive as LF on every platform.
    lf_required = ["migrations/0001_organizational_model_and_rls.sql",
                   "migrations/0005_security_event_storage_allocation_and_context.sql",
                   "seeds/0001_demonstration_tenants.sql",
                   "tests/m1a/run_verification.sh",
                   "tools/migrate.py"]
    wrong = []
    for relative in lf_required:
        attrs = git("check-attr", "text", "eol", "--", relative).stdout
        if "text: set" not in attrs or "eol: lf" not in attrs:
            wrong.append(f"{relative} -> {' '.join(attrs.split())}")
    record("checksum-locked and executable files are LF on every platform",
           not wrong,
           "; ".join(wrong) if wrong else
           f"{len(lf_required)} representative file(s) resolve to text=set eol=lf, so a "
           f"Windows checkout hashes what Linux hashed and `set -euo pipefail` has no "
           f"trailing CR to make bash continue without -e")

    # The pinned package is exempt from conversion in BOTH directions. 70 of its 92 files
    # are stored WITH CR bytes, so normalising them would change the very bytes the 91
    # recorded sums exist to detect.
    package_relative = ("docs/Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9/"
                        "00_PACKAGE_CONTROL/README.md")
    package_attrs = git("check-attr", "text", "--", package_relative).stdout
    record("the pinned package is exempt from line-ending conversion in both directions",
           "text: unset" in package_attrs,
           f"{package_relative} resolves to {' '.join(package_attrs.split()[-2:])}; its bytes "
           f"are evidence, not source, and Git neither normalises them on the way in nor "
           f"converts them on the way out")

    # The decisive test, stated as the property that actually matters: the bytes on disk
    # must be the bytes that were committed. If any line-ending conversion were active on
    # the package, the checkout would differ from the blob and the 91 recorded sums would
    # stop matching. Comparing worktree bytes to blob bytes measures exactly that, and —
    # unlike a re-normalisation dry run — it cannot be confused by an uncommitted edit.
    package_files = [line for line in
                     git("ls-files", "--", "docs").stdout.splitlines() if line.strip()]
    converted = []
    for relative in package_files:
        blob = subprocess.run(["git", "-C", str(REPO), "cat-file", "blob", f"HEAD:{relative}"],
                              capture_output=True)
        on_disk = (REPO / relative).read_bytes()
        if blob.returncode == 0 and blob.stdout != on_disk:
            converted.append(f"{relative} differs from its committed blob "
                             f"({len(blob.stdout)} bytes committed, {len(on_disk)} on disk)")
    with_cr = sum(1 for relative in package_files
                  if b"\r" in (REPO / relative).read_bytes()[:8192])
    record("the pinned package is checked out byte-identical to what was committed",
           bool(package_files) and not converted,
           "; ".join(converted[:3]) if converted else
           f"{len(package_files)} package file(s) match their committed blobs exactly; "
           f"{with_cr} of them carry CR bytes, which is how they were delivered and hashed "
           f"— normalising those would change the very bytes the 91 sums exist to detect")

    # Checksum-locked and executable files must carry no CR, or their hashes move and
    # `set -euo pipefail` stops meaning what it says.
    locked = [line for line in
              (git("ls-files", "--", "migrations", "seeds").stdout
               + git("ls-files", "--", "*.sh").stdout).splitlines() if line.strip()]
    carrying_cr = [relative for relative in locked
                   if b"\r" in (REPO / relative).read_bytes()]
    record("no checksum-locked or executable file carries a CR byte",
           bool(locked) and not carrying_cr,
           "; ".join(carrying_cr) if carrying_cr else
           f"{len(locked)} migration, seed and shell file(s) are pure LF on disk, so their "
           f"checksums are platform-independent and no shell option string ends in a CR")

    # F3 — no POSIX-only device path in the harness code that has to run on both platforms.
    # The markers are assembled rather than written out, so this scanner does not report
    # itself as an offender — the same trap the fenced-vocabulary work had to avoid.
    #
    # The scan covers Python only, and the check now says so. It used to be titled "no
    # harness file ..." while globbing *.py alone, which claimed coverage it did not have:
    # tests/m1a/run_verification.sh:70 carried a POSIX null-device path throughout, and the
    # check reported clean over it. The bash drivers are excluded deliberately, not
    # accidentally — they are POSIX-only entry points with no Windows equivalent
    # (docs-local/CROSS_PLATFORM_COMMANDS.md), so a POSIX device path is correct in them.
    # They are counted and named below rather than passed over in silence.
    root = "/" + "dev" + "/"
    devices = ("null", "stdout", "stderr", "urandom", "zero", "tty")

    def device_paths(path: Path) -> list[str]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return [f"{root}{device}" for device in devices if root + device in text]

    python_files = (sorted((REPO / "tests").rglob("*.py"))
                    + sorted((REPO / "tools").rglob("*.py")))
    scanned, posix_only = 0, []
    for path in python_files:
        if path.resolve() == Path(__file__).resolve():
            continue
        scanned += 1
        for found in device_paths(path):
            posix_only.append(f"{path.relative_to(REPO)} hardcodes {found}")

    bash_only = [f"{path.relative_to(REPO)} ({', '.join(device_paths(path))})"
                 for path in sorted((REPO / "tests").rglob("*.sh")) if device_paths(path)]

    # The bash drivers were named as UNSCANNED when the Python scan was narrowed, and a
    # POSIX device path survived in one of them until the drivers were first run on
    # Windows. They are scanned now. A redirection bash performs itself is fine on every
    # platform; handing that path as an ARGUMENT to a native program is not, because Git
    # Bash passes arguments through verbatim.
    argument_paths = []
    shell_drivers = (sorted((REPO / "tests").rglob("*.sh"))
                     + sorted((REPO / "api").rglob("*.sh")))
    for path in shell_drivers:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for device in ("null", "stdout", "stderr", "zero"):
                literal = root + device
                for match in re.finditer(re.escape(literal), line):
                    before = line[:match.start()].rstrip()
                    # A redirection bash performs itself is translated on every platform.
                    if before.endswith((">", ">>", "&>")):
                        continue
                    # An ASSIGNMENT is the portability mechanism, not a breach of it: the
                    # POSIX branch of a per-platform selection has to name the POSIX path
                    # somewhere. Flagging it would flag the fix. What must not happen is
                    # the literal reaching a native program as an argument.
                    if re.search(r"[A-Za-z_][A-Za-z0-9_]*=\"?$", before):
                        continue
                    argument_paths.append(
                        f"{path.relative_to(REPO)}:{number} passes {literal} as an argument")
    record("no shell driver passes a POSIX-only device path as an argument (F3)",
           not argument_paths,
           "; ".join(argument_paths) if argument_paths else
           f"{len(shell_drivers)} shell driver(s) scanned; redirections bash performs "
           f"itself are left alone, because bash translates those on every platform")

    record("no cross-platform harness file hardcodes a POSIX-only device path (F3)",
           not posix_only,
           "; ".join(posix_only) if posix_only else
           f"{scanned} Python harness file(s) scanned — the code that runs on both "
           f"platforms; os.devnull is used instead, so psql does not exit on an invalid "
           f"path under Windows and take every context-scoped assertion down with it. "
           f"The bash drivers are NOT scanned and are not claimed: "
           + (f"a POSIX device path appears in {len(bash_only)} of them "
              f"({'; '.join(bash_only)}), which is correct — they are POSIX-only entry "
              f"points with no Windows path." if bash_only else
              "no POSIX device path appears in any of them."))

    # Reading psql with a stated encoding was fixed everywhere; what this process writes
    # to its OWN stdout was not, and Python takes that from the platform. On Windows that
    # is cp1252, which cannot hold Amharic or Arabic: the M2-A suite proved it had stored
    # them and then died reporting it. Every entry point must therefore state its output
    # encoding rather than inherit one, and the guard is only worth anything if a new
    # entry point cannot quietly skip it.
    # Which files must carry the guard is derived from what they do, not from a list
    # somebody maintains: anything that can be run, or that writes to stdout at all. A
    # library that never prints cannot corrupt evidence, and naming exceptions by hand
    # is how a check stops noticing the file that was added last.
    entry_points, unguarded = [], []
    for path in sorted([*(REPO / "tools").glob("*.py"),
                        *(REPO / "tests").glob("*/*.py")]):
        source = path.read_text(encoding="utf-8")
        if "def use_utf8_output" in source:
            continue                      # the guard itself
        if '__main__' not in source and "print(" not in source:
            continue                      # a library that prints nothing
        entry_points.append(path)
        if "use_utf8_output()" not in source:
            unguarded.append(str(path.relative_to(REPO)))
    record("every entry point states the encoding it writes evidence in",
           not unguarded and len(entry_points) > 10,
           f"{len(entry_points)} entry point(s) checked; "
           + ("all call use_utf8_output() before printing, so a locale that cannot hold "
              "Amharic or Arabic cannot destroy or silently alter what a suite reports"
              if not unguarded else
              f"{len(unguarded)} inherit the platform default: {', '.join(unguarded)}"))

    # The mechanisms above hold wherever this runs. The one thing only a real run can
    # establish is which platform it actually executed on, so that is what this reports —
    # read from the interpreter, not written down. The line it replaces said "This harness
    # ran on Linux" unconditionally, and duly passed on Windows while saying so; a check
    # whose text cannot be wrong cannot be evidence either.
    system = platform.system()
    record("the platform this run executed on is identified and recorded",
           bool(system),
           f"executed on {system or 'an unidentified platform'} {platform.release()} "
           f"({platform.machine()}) under Python {platform.python_version()}. F2 and F3 are "
           f"proved as mechanisms wherever this runs; that the suites COMPLETE on any other "
           f"platform is not claimed by this run and stays open until run there.")


def section_negative_controls() -> None:
    print("\n--- 4. The four M1 negative controls ---")

    print("\n  NC-M1-001  fail-closed tenant context  ->  VISIBLE_OR_WRITABLE_ROWS_WITHOUT_CONTEXT")
    prove_control(
        "NC-M1-001", rls_absent_context_gate, APP,
        break_sql="CREATE POLICY nc_m1_001_break ON org.org_node FOR ALL USING (true) WITH CHECK (true);",
        revert_sql="DROP POLICY nc_m1_001_break ON org.org_node;",
        signature="VISIBLE_OR_WRITABLE_ROWS_WITHOUT_CONTEXT",
    )

    print("\n  NC-M1-002  sibling-outlet isolation  ->  SIBLING_OUTLET_ACCESS")
    prove_control(
        "NC-M1-002", rls_sibling_outlet_gate, APP,
        break_sql=("ALTER POLICY org_node_isolation ON org.org_node "
                   "USING (app.current_tenant_id() IS NOT NULL AND tenant_id = app.current_tenant_id()) "
                   "WITH CHECK (app.current_tenant_id() IS NOT NULL AND tenant_id = app.current_tenant_id());"),
        revert_sql=("ALTER POLICY org_node_isolation ON org.org_node "
                    "USING (app.row_in_scope(tenant_id, outlet_id)) "
                    "WITH CHECK (app.row_in_scope(tenant_id, outlet_id));"),
        signature="SIBLING_OUTLET_ACCESS",
    )

    print("\n  NC-M1-003  future schema protection  ->  OUTLET_POLICY_NOT_UPGRADED")
    prove_control(
        "NC-M1-003", rls_alter_added_outlet_gate, APP,
        break_sql="""
            CREATE TABLE org.nc_m1_003_probe (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL REFERENCES org.tenant(id)
            );
            ALTER TABLE org.nc_m1_003_probe ENABLE ROW LEVEL SECURITY;
            ALTER TABLE org.nc_m1_003_probe FORCE  ROW LEVEL SECURITY;
            CREATE POLICY nc_probe_isolation ON org.nc_m1_003_probe FOR ALL
                USING (tenant_id = app.current_tenant_id())
                WITH CHECK (tenant_id = app.current_tenant_id());
            GRANT SELECT ON org.nc_m1_003_probe TO hospitality_app;
            -- the defect: the column arrives, the policy is not upgraded with it
            ALTER TABLE org.nc_m1_003_probe ADD COLUMN outlet_id uuid;
        """,
        revert_sql="DROP TABLE org.nc_m1_003_probe;",
        signature="OUTLET_POLICY_NOT_UPGRADED",
    )

    print("\n  NC-M1-004  runtime least privilege  ->  PRIVILEGED_RUNTIME_ROLE_REJECTED")
    privileged_dsn = os.environ["M1A_PRIVILEGED_DSN"]
    ok, _, detail = runtime_role_gate(APP)
    record("NC-M1-004 — baseline", ok, detail)

    red_ok, red_signature, red_detail = runtime_role_gate(privileged_dsn)
    record("NC-M1-004 — RED when configured with a BYPASSRLS role",
           (not red_ok) and red_signature == "PRIVILEGED_RUNTIME_ROLE_REJECTED",
           f"{red_signature}: {red_detail}")

    owner_ok, owner_signature, owner_detail = runtime_role_gate(MIGRATOR)
    record("NC-M1-004 — RED when configured with the owner role",
           (not owner_ok) and owner_signature == "PRIVILEGED_RUNTIME_ROLE_REJECTED",
           f"{owner_signature}: {owner_detail}")

    super_ok, super_signature, super_detail = runtime_role_gate(ADMIN)
    record("NC-M1-004 — RED when configured with a superuser",
           (not super_ok) and super_signature == "PRIVILEGED_RUNTIME_ROLE_REJECTED",
           f"{super_signature}: {super_detail}")

    green_ok, _, green_detail = runtime_role_gate(APP)
    record("NC-M1-004 — GREEN for the real runtime role", green_ok, green_detail)


def main() -> int:
    print("M1-A verification — real PostgreSQL, application role, populated fixtures")
    # A probe that could not execute raises rather than returning a sentinel that reads
    # as "nothing found". Catching it here records a failure instead of a traceback, so
    # the suite still reports a verdict — a failing one, which is the correct verdict
    # for a section whose evidence could not be gathered.
    for section in (section_migration, section_rls, section_data_architecture,
                    section_cross_platform, section_negative_controls):
        try:
            section()
        except ProbeFailed as exc:
            record(f"{section.__name__} completed", False, f"probe did not execute: {exc}")
        except CommandUnreadable as exc:
            record(f"{section.__name__} completed", False, f"command output unreadable: {exc}")

    failed = [name for name, ok, _ in results if not ok]
    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    if failed:
        print("\nFAIL M1A_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS M1A_VERIFICATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
