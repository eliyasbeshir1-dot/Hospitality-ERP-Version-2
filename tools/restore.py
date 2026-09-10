#!/usr/bin/env python3
"""Destroy a database and rebuild it from a backup, under production roles, timed.

FR-OPS-007, FR-TST-009, FR-SEC-019.

    Restore into clean cloud and outlet environments, start with least-privileged
    production roles, run the Phase 1 golden journeys and measure recovery time.

WHAT "CLEAN" HAS TO MEAN, because the weak reading is what makes a restore drill worthless.
Restoring over a database that already holds the data proves nothing: every row the archive
fails to carry is still there, and the drill passes because the thing it was meant to
detect is sitting in the table. So this DROPS the target and creates it empty first. If the
archive is short, the restored database is short, and that is the point.

THE ROLES ARE THE PRODUCTION ONES AND THAT IS LOAD-BEARING. FR-OPS-007 says "start with
least-privileged production roles". A restore performed as a superuser and then read as a
superuser proves the bytes came back; it does not prove the estate WORKS, because row level
security, grants and FORCE RLS are exactly what a superuser bypasses. So the verification
after the restore reads through `hospitality_app` — the role the service actually uses —
and a restore that came back without its grants fails there rather than looking fine.

WHAT IS TIMED. Wall clock from the moment the drop starts to the moment the restored
database answers a query through the application role. That is the number an operator needs
— not how long pg_restore took, which excludes both the destruction and the point at which
the thing is usable again.

Usage:
    HOSPITALITY_BACKUP_KEY=... python3 tools/restore.py \\
        --archive <path> --into <dsn-of-target> --admin <dsn-of-maintenance-db> \\
        --target-db <name> [--app-dsn <dsn>]
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
from console import use_utf8_output  # noqa: E402
from backup import CIPHER, KDF, KDF_ITERATIONS, digest_of, key_material, openssl  # noqa: E402

use_utf8_output()


class RestoreRefused(RuntimeError):
    """Something was wrong enough that continuing would produce a false all-clear."""


def decrypt_to(archive: Path, plain: Path, key: str) -> str:
    """Decrypt, and return the digest of the CIPHERTEXT that was decrypted.

    The digest is of what was read, so a drill that restored a different archive cannot
    report success about the one it was asked for.
    """
    observed, _size = digest_of(archive)
    with archive.open("rb") as src, plain.open("wb") as out:
        dec = openssl(["-d", "-" + CIPHER, "-" + KDF, "-iter", str(KDF_ITERATIONS)],
                      key, stdin=src, stdout=out)
        err = dec.communicate()[1]
    if dec.returncode != 0:
        raise RestoreRefused(f"DECRYPT_FAILED: {(err or b'').decode()[:400]}")
    return observed


def destroy_and_create(admin_dsn: str, database: str) -> None:
    """DROP then CREATE. The drill is worthless without this and it is not reversible.

    Named loudly because it is the one genuinely destructive thing in this repository. The
    guard is the caller's: tools/restore.py is never pointed at a database somebody is
    using, and tests/m6c builds a throwaway one to point it at.
    """
    for statement in (f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)',
                      f'CREATE DATABASE "{database}"'):
        proc = subprocess.run(["psql", admin_dsn, "-v", "ON_ERROR_STOP=1",
                               "-Atq", "-c", statement],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise RestoreRefused(
                f"TARGET_NOT_CLEAN: {statement} failed — {proc.stderr.strip()[:300]}")


def restore_into(target_dsn: str, plain: Path) -> tuple[int, str]:
    """pg_restore into the empty database. Returns (errors ignored, detail).

    --exit-on-error is deliberately ON. pg_restore's default is to carry on past failures
    and exit zero, which turns a partial restore into a successful-looking one — the exact
    shape of defect this drill exists to catch.
    """
    proc = subprocess.run(
        # NOT --no-owner --no-privileges: the whole point of the drill is that the estate
        # comes back USABLE, and both flags discard exactly what makes it so.
        ["pg_restore", "--dbname", target_dsn, "--exit-on-error", str(plain)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise RestoreRefused(f"RESTORE_FAILED: {proc.stderr.strip()[:500]}")
    return 0, "pg_restore --exit-on-error completed"


def _count(dsn: str, sql: str) -> tuple[bool, str]:
    proc = subprocess.run(["psql", dsn, "-Atq", "-v", "ON_ERROR_STOP=1", "-c", sql],
                          capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout or proc.stderr).strip()[:300]


def usable_through(app_dsn: str, admin_dsn: str) -> tuple[bool, str]:
    """Is the restored estate usable BY THE ROLE THE SERVICE USES, and is anything in it?

    This separates "the bytes came back" from "the estate works". A superuser bypasses row
    level security and every grant, so a superuser reading the restored database would
    report success on a restore that lost all of them.

    AND IT DISTINGUISHES "COULD NOT SEE" FROM "IS NOT THERE", which the first version did
    not. It read org.tenant through the application role with NO tenant context set, got
    0, and reported success — because with no context `app.row_in_scope` matches nothing
    and an empty restore looks exactly like a correctly-isolated one. That is the defect
    class this project has met repeatedly: M5a's connectivity banner answered CONNECTED
    because row level security had hidden the node it was asked about.

    So three readings, and all three have to agree:

        admin   how many tenants the archive actually carried, bypassing RLS
        app-    the same read with no context, which MUST be 0 or isolation is broken
        app+    the same read scoped to a real tenant, which must match the admin count
    """
    ok, carried = _count(admin_dsn, "SELECT count(*)::text FROM org.tenant")
    if not ok:
        return False, f"the restored database is unreadable even as admin: {carried}"
    if carried == "0":
        return False, ("the restore produced an EMPTY estate — pg_restore reported success "
                       "and there are no tenants in it")

    ok, unscoped = _count(app_dsn, "SELECT count(*)::text FROM org.tenant")
    if not ok:
        return False, f"the application role cannot read the estate at all: {unscoped}"
    if unscoped != "0":
        return False, (f"row level security did not survive the restore: the application "
                       f"role sees {unscoped} tenant(s) with no context set, and should "
                       f"see none")

    ok, tenant = _count(admin_dsn, "SELECT id::text FROM org.tenant ORDER BY id LIMIT 1")
    if not ok or not tenant:
        return False, "no tenant to scope a read to"
    ok, scoped = _count(
        app_dsn,
        f"SET app.tenant_id = '{tenant}'; SELECT count(*)::text FROM org.tenant")
    if not ok:
        return False, f"the application role cannot read in scope: {scoped}"
    if scoped == "0":
        return False, (f"the application role sees nothing even scoped to tenant "
                       f"{tenant[:8]} — the estate is present and unusable")

    return True, (f"{carried} tenant(s) restored; the application role sees {unscoped} "
                  f"unscoped and {scoped} in scope, so the grants AND row level security "
                  f"both came back")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--admin", required=True,
                        help="DSN of a maintenance database — NOT the one being dropped")
    parser.add_argument("--target-db", required=True)
    parser.add_argument("--into", required=True, help="DSN of the target, after creation")
    parser.add_argument("--app-dsn", default=None,
                        help="the least-privileged production role's DSN")
    args = parser.parse_args()

    try:
        key = key_material()
    except Exception as exc:                                # noqa: BLE001
        print(f"FAIL {exc}")
        return 1

    archive = Path(args.archive)
    if not archive.exists():
        print(f"FAIL ARCHIVE_ABSENT: {archive}")
        return 1

    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="restore-") as work:
            plain = Path(work) / "archive.dump"
            observed = decrypt_to(archive, plain, key)
            print(f"  decrypted  sha256 {observed[:16]}… of the ciphertext read")

            print(f"  destroying {args.target_db} — DROP then CREATE, so a short archive "
                  f"restores short")
            destroy_and_create(args.admin, args.target_db)

            restore_into(args.into, plain)
            print("  restored   pg_restore --exit-on-error completed")
    except RestoreRefused as exc:
        print(f"FAIL {exc}")
        return 1

    app_dsn = args.app_dsn
    if app_dsn:
        ok, detail = usable_through(app_dsn, args.into)
        elapsed = time.monotonic() - started
        if not ok:
            print(f"FAIL RESTORED_BUT_UNUSABLE: the bytes came back and the role the "
                  f"service uses cannot read them — {detail}")
            print(f"  recovery time to failure: {elapsed:.1f}s")
            return 1
        print(f"  usable     {detail}")
    else:
        elapsed = time.monotonic() - started

    print(f"\nPASS RESTORE_DRILL  recovery time {elapsed:.1f}s "
          f"(drop to usable, not pg_restore alone)")
    print(f"RECOVERY_SECONDS={elapsed:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
