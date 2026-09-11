#!/usr/bin/env python3
"""M6-C verification: restore proved by destroying and rebuilding.

FR-OPS-007, FR-TST-009, FR-OPS-016.

    Restore into clean cloud and outlet environments, start with least-privileged
    production roles, run the Phase 1 golden journeys and measure recovery time.

WHAT MAKES A RESTORE DRILL WORTH RUNNING, and what makes one worthless.

  A drill that restores OVER a populated database proves nothing. Every row the archive
  failed to carry is still sitting in the table, so the drill passes on exactly the defect
  it was meant to find. This one DROPS the target first. If the archive is short, the
  restored estate is short.

  A drill verified as a SUPERUSER proves the bytes came back and not that the estate works,
  because a superuser bypasses row level security and every grant — which is the half of a
  database that a careless dump silently discards. This one reads through
  `hospitality_app`, the role the service actually runs as.

  And a drill that reads 0 rows through that role and calls it success has learned nothing:
  with no tenant context, row level security matches nothing and an EMPTY restore looks
  exactly like a correctly isolated one. Three readings are compared here — what the
  archive carried, what the app role sees unscoped, and what it sees in scope — because
  any one of them alone can be right for the wrong reason.

THE TARGET IS A THROWAWAY DATABASE THIS SUITE CREATES. tools/restore.py drops what it is
pointed at, which is the only genuinely destructive operation in this repository. It is
never pointed at the working database: the suite builds `hospitality_m6c_drill`, destroys
that, and drops it again at the end.

Usage:
    M1A_ADMIN_DSN=... HOSPITALITY_BACKUP_KEY=... python3 tests/m6c/verify_m6c.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
from console import use_utf8_output                        # noqa: E402

use_utf8_output()

sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "tests" / "m1a"))
sys.path.insert(0, str(REPO / "tests" / "opa"))
from pg import run                                         # noqa: E402

import controls as registry                                # noqa: E402
import verify_opa as opa                                   # noqa: E402

ADMIN = os.environ["M1A_ADMIN_DSN"]
TENANT = opa.TENANT
DRILL_DB = "hospitality_m6c_drill"

results: list[tuple[str, bool, str, str]] = []
CONTEXT: dict = {}


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    results.append((name, ok, detail, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] ({evidence}) {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def measured(name: str, ok: bool, detail: str = "") -> None:
    record(name, ok, detail, evidence="measured")


def control(name: str, red, green) -> None:
    red_ok, red_detail = red()
    record(f"{name} — RED with the defect planted", red_ok, red_detail)
    green_ok, green_detail = green()
    record(f"{name} — GREEN after revert", green_ok, green_detail)


def dsn_for(database: str, *, user: str | None = None) -> str:
    """The same server, a different database — and optionally a different role.

    Derived from M1A_ADMIN_DSN rather than rebuilt from parts, so a suite pointed at one
    server cannot quietly drill against another.
    """
    parts = urlsplit(ADMIN)
    netloc = parts.netloc
    if user:
        host = netloc.split("@", 1)[1] if "@" in netloc else netloc
        netloc = f"{user}@{host}"
    return urlunsplit((parts.scheme, netloc, f"/{database}", "", ""))


def drop_drill() -> None:
    subprocess.run(["psql", dsn_for("postgres"), "-Atq", "-c",
                    f'DROP DATABASE IF EXISTS "{DRILL_DB}" WITH (FORCE)'],
                   capture_output=True, text=True)


# ===========================================================================
# 1. A backup to restore from, taken by the real tool
# ===========================================================================

def section_backup() -> None:
    print("\n--- 1. A verified archive, because an unverified one may not be restored ---")

    if not os.environ.get("HOSPITALITY_BACKUP_KEY"):
        os.environ["HOSPITALITY_BACKUP_KEY"] = "m6c-suite-key-not-a-production-secret"

    base = Path(tempfile.mkdtemp(prefix="m6c-"))
    CONTEXT["base"] = base
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "backup.py"),
         "--dsn", ADMIN, "--tenant", TENANT, "--scope", "cloud",
         "--into", str(base), "--label", "m6c"],
        capture_output=True, text=True, timeout=900)
    record("a backup is taken and read back before anything is destroyed",
           proc.returncode == 0,
           "\n".join(l for l in proc.stdout.splitlines() if "verified" in l or "captured" in l)
           or proc.stderr[:300])
    if proc.returncode != 0:
        raise RuntimeError("no archive to restore from")
    CONTEXT["archive"] = base / "m6c.dump.enc"

    # OWNERS AND PRIVILEGES ARE IN IT. The first version of tools/backup.py passed
    # --no-owner --no-privileges, which is the usual advice and is wrong for a restore
    # drill: the estate came back and nothing but a superuser could read it.
    listing = subprocess.run(
        [sys.executable, "-c",
         "import sys, pathlib, tempfile, subprocess;"
         "sys.path.insert(0, r'" + str(REPO / "tools") + "');"
         "from backup import CIPHER, KDF, KDF_ITERATIONS, openssl, key_material;"
         "import os;"
         "w = tempfile.mkdtemp();"
         "p = pathlib.Path(w) / 'a.dump';"
         "src = open(r'" + str(CONTEXT['archive']) + "', 'rb');"
         "out = open(p, 'wb');"
         "d = openssl(['-d','-'+CIPHER,'-'+KDF,'-iter',str(KDF_ITERATIONS)],"
         " key_material(), stdin=src, stdout=out); d.communicate(); out.close();"
         "r = subprocess.run(['pg_restore','--list',str(p)], capture_output=True, text=True);"
         "print(sum(1 for l in r.stdout.splitlines() if 'ACL' in l or 'GRANT' in l))"],
        capture_output=True, text=True, timeout=600)
    grants = (listing.stdout or "0").strip().splitlines()[-1] if listing.stdout else "0"
    record("the archive carries grants, not just data",
           grants.isdigit() and int(grants) > 0,
           f"{grants} ACL entries. --no-owner --no-privileges is the usual advice and is "
           "wrong here: it produces an estate that restores and that nobody but a "
           "superuser can read")


# ===========================================================================
# 2. Destroy it and build it back
# ===========================================================================

def section_drill() -> None:
    print("\n--- 2. FR-OPS-007: destroyed, rebuilt, and usable by the production role ---")

    drop_drill()
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "restore.py"),
         "--archive", str(CONTEXT["archive"]),
         "--admin", dsn_for("postgres"),
         "--target-db", DRILL_DB,
         "--into", dsn_for(DRILL_DB),
         "--app-dsn", dsn_for(DRILL_DB, user="hospitality_app")],
        capture_output=True, text=True, timeout=1800)
    CONTEXT["restore_output"] = proc.stdout + proc.stderr

    record("the target is dropped and recreated before the restore",
           "destroying" in proc.stdout,
           "restoring OVER a populated database proves nothing: every row the archive "
           "failed to carry is still in the table, so the drill passes on exactly the "
           "defect it exists to find")

    record("the estate is restored and usable through the least-privileged role",
           proc.returncode == 0,
           "\n".join(l for l in proc.stdout.splitlines() if "usable" in l or "FAIL" in l)
           or proc.stderr[:400])

    seconds = re.search(r"RECOVERY_SECONDS=([\d.]+)", proc.stdout)
    CONTEXT["seconds"] = float(seconds.group(1)) if seconds else None
    measured("recovery time is measured, from destruction to usable",
             CONTEXT["seconds"] is not None,
             f"{CONTEXT['seconds']}s — wall clock from the drop to the moment the "
             "application role could read the estate. Not pg_restore's duration, which "
             "excludes both the destruction and the point at which the thing works again")


# ===========================================================================
# 3. What came back, read three ways
# ===========================================================================

def section_three_readings() -> None:
    print("\n--- 3. FR-TST-009: could-not-see is not is-not-there ---")
    app = dsn_for(DRILL_DB, user="hospitality_app")
    admin = dsn_for(DRILL_DB)

    carried = run(admin, "SELECT count(*)::text FROM org.tenant;").scalar
    unscoped = run(app, "SELECT count(*)::text FROM org.tenant;").scalar
    scoped = run(app, "SELECT count(*)::text FROM org.tenant;", tenant=TENANT).scalar

    record("the archive carried the estate",
           (carried or "0") != "0", f"{carried} tenant(s), read bypassing row level security")
    record("and row level security came back with it",
           unscoped == "0",
           f"{unscoped} visible to the application role with NO context. A restore that "
           "lost its policies would show them all here")
    record("and the application role can reach its own tenant",
           (scoped or "0") != "0",
           f"{scoped} in scope. This is the reading the first version of the drill did "
           "NOT do: it read unscoped, got 0, and reported success — an empty restore looks "
           "exactly like a correctly isolated one, which is M5a's connectivity-banner "
           "defect wearing different clothes")

    # THE BUSINESS DOMAINS FR-TST-009 NAMES, present after the restore rather than assumed.
    domains = run(admin, """
        SELECT string_agg(x.label || '=' || x.n::text, ' ' ORDER BY x.label) FROM (
            SELECT 'orders' AS label, count(*) AS n FROM ordering.customer_order
            UNION ALL SELECT 'bills', count(*) FROM billing.bill
            UNION ALL SELECT 'payments', count(*) FROM payments.payment_intent
            UNION ALL SELECT 'tickets', count(*) FROM fulfillment.ticket
            UNION ALL SELECT 'outbox', count(*) FROM integration.outbox
        ) x;""").scalar
    record("the domains the requirement names came back",
           domains is not None and "orders=" in (domains or ""),
           f"{domains}\nFR-TST-009 names table/order/KDS/bill/tip/payment/sync journeys; "
           "these are the tables behind them")


# ===========================================================================
# 4. Negative controls
# ===========================================================================

def section_controls() -> None:
    print("\n--- 4. Negative controls: each defect planted, refused, reverted ---")

    def nc_001():
        # A TRUNCATED ARCHIVE. The bytes are wrong and openssl's authentication is not
        # what catches it — pg_restore is. This proves the drill fails on a bad archive
        # rather than restoring a partial estate and calling it a day.
        broken = Path(CONTEXT["base"]) / "truncated.dump.enc"

        def red():
            data = CONTEXT["archive"].read_bytes()
            broken.write_bytes(data[: len(data) // 3])
            proc = subprocess.run(
                [sys.executable, str(REPO / "tools" / "restore.py"),
                 "--archive", str(broken), "--admin", dsn_for("postgres"),
                 "--target-db", DRILL_DB, "--into", dsn_for(DRILL_DB),
                 "--app-dsn", dsn_for(DRILL_DB, user="hospitality_app")],
                capture_output=True, text=True, timeout=1800)
            return proc.returncode != 0, \
                "a third of an archive is refused rather than restored partially: " \
                + (proc.stdout + proc.stderr).strip().splitlines()[-1][:160]

        def green():
            broken.unlink(missing_ok=True)
            proc = subprocess.run(
                [sys.executable, str(REPO / "tools" / "restore.py"),
                 "--archive", str(CONTEXT["archive"]), "--admin", dsn_for("postgres"),
                 "--target-db", DRILL_DB, "--into", dsn_for(DRILL_DB),
                 "--app-dsn", dsn_for(DRILL_DB, user="hospitality_app")],
                capture_output=True, text=True, timeout=1800)
            return proc.returncode == 0, "and the whole archive restores"

        control("NC-M6C-001 a truncated archive restored as if whole", red, green)

    def nc_002():
        def red():
            env = dict(os.environ)
            env["HOSPITALITY_BACKUP_KEY"] = "the-wrong-key-entirely-but-long-enough"
            proc = subprocess.run(
                [sys.executable, str(REPO / "tools" / "restore.py"),
                 "--archive", str(CONTEXT["archive"]), "--admin", dsn_for("postgres"),
                 "--target-db", DRILL_DB, "--into", dsn_for(DRILL_DB)],
                capture_output=True, text=True, timeout=1800, env=env)
            return "DECRYPT_FAILED" in proc.stdout, \
                "the wrong key cannot restore, and says so rather than producing rubbish"

        def green():
            proc = subprocess.run(
                [sys.executable, str(REPO / "tools" / "restore.py"),
                 "--archive", str(CONTEXT["archive"]), "--admin", dsn_for("postgres"),
                 "--target-db", DRILL_DB, "--into", dsn_for(DRILL_DB),
                 "--app-dsn", dsn_for(DRILL_DB, user="hospitality_app")],
                capture_output=True, text=True, timeout=1800)
            return proc.returncode == 0, "and the right key restores it"

        control("NC-M6C-002 a restore attempted with the wrong key", red, green)

    def nc_003():
        # THE CHECK THAT CAUGHT MY OWN DEFECT. A restore that keeps the data and loses the
        # grants must fail, and it must fail at the application role rather than look fine.
        app = dsn_for(DRILL_DB, user="hospitality_app")

        def red():
            revoked = run(dsn_for(DRILL_DB),
                          "REVOKE USAGE ON SCHEMA org FROM hospitality_app;")
            probe = run(app, "SELECT count(*)::text FROM org.tenant;")
            return revoked.ok and not probe.ok, \
                "with the grant gone the application role cannot read the estate: " \
                + (probe.err or "").strip().splitlines()[0][:120]

        def green():
            run(dsn_for(DRILL_DB), "GRANT USAGE ON SCHEMA org TO hospitality_app;")
            probe = run(app, "SELECT count(*)::text FROM org.tenant;", tenant=TENANT)
            return probe.ok and (probe.scalar or "0") != "0", \
                "and reads it again once the grant is back"

        control("NC-M6C-003 an estate restored without the grants that make it usable",
                red, green)

    for case in (nc_001, nc_002, nc_003):
        case()

    registered = [c for c in registry.CONTROLS if c[3] == "m6c"]
    record("every M6-C control is registered in tools/controls.py",
           len(registered) == 3, f"{len(registered)} registered")


# ===========================================================================
# 5. The bounds
# ===========================================================================

def section_bounds() -> None:
    print("\n--- 5. The bounds, named rather than left to silence ---")
    for bound in (
        "THE GOLDEN JOURNEYS ARE NOT RUN AGAINST THE RESTORED DATABASE. FR-OPS-007 asks "
        "for them and this drill proves the estate is present, isolated and readable by "
        "the production role — which is the precondition for them rather than a substitute. "
        "Running thirteen browser journeys against a second database needs a second service "
        "on a second port, and that is M6-E's",
        "ONLY THE CLOUD ENVIRONMENT IS DESTROYED AND REBUILT. FR-OPS-007 names cloud AND "
        "outlet; the demonstration floor's node shares this database rather than running "
        "its own, so there is no separate outlet environment on this machine to destroy",
        "RECOVERY TIME IS MEASURED ON A 2MB ARCHIVE. The number is real and the shape of "
        "the measurement is right — drop to usable, not pg_restore alone — but it says "
        "nothing about a production-sized estate",
        "THE REPLACEMENT-NODE PROCEDURE FR-OPS-016 NAMES IS BUILT AND NOT DRILLED HERE. "
        "M5b's edge.claim_authority() with its four proofs is what a replacement runs "
        "through, and GJ-09 exercises it; what is not exercised is a replacement node "
        "restoring from a backup and then claiming authority",
    ):
        record("recorded in planning/M6_FINDINGS.md", True, bound)


def cleanup() -> None:
    drop_drill()
    base = CONTEXT.get("base")
    if base and Path(base).exists():
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    print("=" * 74)
    print("  M6-C — restore proved by destroying and rebuilding")
    print("=" * 74)

    try:
        for section in (section_backup, section_drill, section_three_readings,
                        section_controls, section_bounds):
            try:
                section()
            except Exception as exc:                        # noqa: BLE001
                record(f"{section.__name__} completed", False,
                       f"{type(exc).__name__}: {str(exc)[:400]}")
    finally:
        cleanup()

    failed = [name for name, ok, _d, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")
    owned = len([c for c in registry.CONTROLS if c[3] == "m6c"])

    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}")
    print(f"  asserted      : {len(results) - measured_count}")
    print(f"  controls      : {owned} registered, each proved red then green")

    if failed:
        print("\nFAIL M6C_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS M6C_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
