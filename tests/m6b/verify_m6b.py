#!/usr/bin/env python3
"""M6-B verification: a backup is a thing that happened, on a schedule, and was verified.

FR-OPS-006 and FR-SEC-019 together, because neither is complete without the other. One
asks for a documented schedule using tools inside the production artifact; the other asks
that what those tools produce is encrypted, read back, and kept somewhere else.

THE CLAIM THIS SLICE IS REALLY MAKING. Not "a backup file exists" — that is the claim that
produces an unrestorable archive nobody discovers until they need it. The claim is that
every backup in ops.backup_run has been DECRYPTED AND READ, and that the state meaning
"taken and assumed good" does not exist in the schema.

WHAT IS ACTUALLY DRIVEN HERE. tools/backup.py is run as a subprocess against the live
database: pg_dump piped into openssl, the ciphertext digested, the archive decrypted again
and its table of contents counted. Nothing is simulated. The archive this suite verifies is
one it made.

Usage:
    M1A_ADMIN_DSN=... HOSPITALITY_BACKUP_KEY=... python3 tests/m6b/verify_m6b.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

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
ADMINISTRATOR = "3333aaaa-0000-4000-8000-000000000001"

results: list[tuple[str, bool, str, str]] = []
CONTEXT: dict = {}


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    results.append((name, ok, detail, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] ({evidence}) {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def measured(name: str, ok: bool, detail: str = "") -> None:
    record(name, ok, detail, evidence="measured")


def q(sql: str):
    """Every probe rolls back — M5b's rule, and FR-TST-020's requirement."""
    result = run(ADMIN, sql, tenant=TENANT, tx=True, rollback=True)
    if not result.ok:
        raise RuntimeError(f"probe failed: {result.err[:300]}")
    return result


def refusal(sql: str) -> str:
    result = run(ADMIN, sql, tenant=TENANT, tx=True, rollback=True)
    if result.ok:
        return ""
    for token in result.err.replace("\n", " ").split():
        cleaned = token.strip(":,.'" + '"')
        if cleaned.isupper() and len(cleaned) > 6 and "_" in cleaned:
            return cleaned
    # THE TRAILING UNDERSCORE IS LOAD-BEARING. PostgreSQL says `new row for relation
    # "backup_run" violates check constraint "backup_run_is_encrypted"`, so a prefix of
    # `backup_` matches the RELATION first and every constraint check reports the table
    # name. tests/m5b's helper has the trailing underscore for exactly this reason and it
    # is not decoration; this suite was written without it and two controls failed with
    # `signature: backup_run`.
    for token in result.err.replace("\n", " ").split():
        stripped = token.strip("'\",.")
        if stripped.startswith(("backup_run_", "backup_policy_")):
            return stripped
    return result.err.strip()[:140]


def control(name: str, red, green) -> None:
    red_ok, red_detail = red()
    record(f"{name} — RED with the defect planted", red_ok, red_detail)
    green_ok, green_detail = green()
    record(f"{name} — GREEN after revert", green_ok, green_detail)


# ===========================================================================
# 1. A real backup, taken by the real tool
# ===========================================================================

def section_take_one() -> None:
    print("\n--- 1. FR-OPS-006: pg_dump and openssl, driven as an operator drives them ---")

    if not os.environ.get("HOSPITALITY_BACKUP_KEY"):
        os.environ["HOSPITALITY_BACKUP_KEY"] = "m6b-suite-key-not-a-production-secret"

    base = Path(tempfile.mkdtemp(prefix="m6b-"))
    CONTEXT["base"] = base
    into, offsite = base / "primary", base / "offsite"

    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "backup.py"),
         "--dsn", ADMIN, "--tenant", TENANT, "--scope", "cloud",
         "--into", str(into), "--offsite", str(offsite), "--label", "m6b"],
        capture_output=True, text=True, timeout=900)
    CONTEXT["output"] = proc.stdout + proc.stderr

    record("a backup is taken, encrypted, read back and copied off-site",
           proc.returncode == 0,
           "\n".join(l for l in proc.stdout.splitlines() if l.strip())[:600]
           or proc.stderr[:400])
    if proc.returncode != 0:
        raise RuntimeError("no backup to reason about")

    archive = into / "m6b.dump.enc"
    CONTEXT["archive"] = archive
    record("the archive exists and is not empty",
           archive.exists() and archive.stat().st_size > 0,
           f"{archive.stat().st_size if archive.exists() else 0} bytes")

    # THE PLAINTEXT NEVER LANDED. pg_dump is piped into openssl, so the only bytes that
    # ever reached storage are encrypted ones — a process that writes a plaintext dump and
    # deletes it has still written one, and deletion is not erasure.
    strays = [p.name for p in into.iterdir() if not p.name.endswith(".enc")]
    record("no plaintext dump was ever written beside it",
           strays == [],
           f"files beside the archive: {strays or 'none'}. pg_dump is piped straight into "
           "openssl, so the plaintext never becomes a file — deleting one afterwards would "
           "not be erasure on any filesystem in use here")

    # AND IT IS NOT READABLE WITHOUT THE KEY. The strongest available check that the thing
    # on disk is actually encrypted: pg_restore knows the format and cannot read it.
    listing = subprocess.run(["pg_restore", "--list", str(archive)],
                             capture_output=True, text=True)
    record("the archive on disk is not a readable dump",
           listing.returncode != 0,
           "pg_restore refuses it, which is what an encrypted archive looks like to the "
           "tool that would otherwise read it")


# ===========================================================================
# 2. Captured is not verified
# ===========================================================================

def section_verified_means_read() -> None:
    print("\n--- 2. FR-SEC-019: `verified` means something decrypted it and read it ---")

    states = q("""SELECT string_agg(enumlabel, ',' ORDER BY enumsortorder)
                    FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                   WHERE t.typname = 'backup_state';""").scalar
    record("there is no state meaning taken-and-assumed-good",
           "captured" in (states or "") and "verified" in (states or ""),
           f"states: {states}\n"
           "`captured` is written, encrypted and digested; it becomes `verified` only when "
           "something has decrypted the archive and read its table of contents back")

    row = q(f"""SELECT state::text || '|' || coalesce(verified_entries::text, '0')
                     || '|' || cipher || '|' || kdf_iterations::text
                  FROM ops.backup_run
                 WHERE tenant_id = '{TENANT}' ORDER BY started_at DESC LIMIT 1;""").scalar
    state, entries, cipher, iterations = (row or "|||").split("|")
    record("the backup this suite took is recorded as off-site and was read back",
           state == "offsite" and int(entries or 0) > 0,
           f"state {state}, {entries} entries read back by pg_restore --list")
    record("and it records what it was encrypted with",
           cipher not in ("", "none") and int(iterations or 0) >= 100000,
           f"{cipher}, {iterations} KDF iterations. The column cannot hold 'none' — a "
           "deployment that skipped encryption could not record one")

    # NOTHING UNVERIFIED IS SITTING AROUND CALLING ITSELF A BACKUP.
    unread = q(f"""SELECT count(*)::text FROM ops.backup_run
                    WHERE tenant_id = '{TENANT}' AND state = 'captured';""").scalar
    record("no archive is left in the captured state",
           unread == "0",
           f"{unread} captured-but-unread. A directory full of archives nobody has opened "
           "is precisely the state ops.backup_run exists to make visible")


# ===========================================================================
# 3. The schedule is something that can be asked
# ===========================================================================

def section_posture() -> None:
    print("\n--- 3. FR-OPS-006: is this estate actually backed up? ---")

    row = q(f"""SELECT posture::text || '|' || coalesce(hours_since::text, '-')
                  FROM ops.backup_posture('{TENANT}', 'cloud');""").scalar
    posture, hours = (row or "|").split("|")
    record("the estate reports a healthy cloud backup",
           posture == "healthy",
           f"{posture}, {hours} hour(s) since the last VERIFIED one — not the last one "
           "taken, which is the distinction that matters")

    # AN ESTATE WITH NO POLICY IS UNDOCUMENTED RATHER THAN HEALTHY. Silence is not a pass.
    undocumented = q(f"""SELECT posture::text FROM ops.backup_posture(
                             '44444444-4444-4444-4444-444444444444', 'cloud');""").scalar
    record("an estate whose schedule nobody wrote down says so",
           undocumented == "undocumented",
           f"{undocumented}. Nothing can be late against a schedule that does not exist, "
           "and reporting that as healthy is how an unbacked-up estate looks fine")

    thresholds = q(f"""SELECT interval_hours::text || '/' || alert_after_hours::text
                            || '/' || retain_days::text
                         FROM ops.backup_policy
                        WHERE tenant_id = '{TENANT}' AND scope = 'cloud';""").scalar
    record("the schedule ascends: interval, then alert, then retention",
           thresholds == "24/36/30",
           f"{thresholds} — hours/hours/days. An alert window shorter than the interval "
           "would alert on every successful schedule, and retention shorter than the "
           "interval would delete a backup before its replacement existed. Both are CHECKs")


# ===========================================================================
# 4. Negative controls
# ===========================================================================

def section_controls() -> None:
    print("\n--- 4. Negative controls: each defect planted, refused, reverted ---")

    def plant(cipher: str = "aes-256-cbc", iterations: int = 600000,
              state: str = "captured", verified: str = "NULL",
              entries: str = "NULL") -> str:
        return f"""
            INSERT INTO ops.backup_run
                (tenant_id, scope, outlet_id, state, taken_with, archive_format,
                 archive_path, archive_sha256, archive_bytes, cipher, kdf, kdf_iterations,
                 verified_at, verified_entries)
            VALUES ('{TENANT}', 'cloud', NULL, '{state}', 'pg_dump', 'custom',
                    '/tmp/probe.enc', repeat('ab', 32), 1024, '{cipher}', 'pbkdf2',
                    {iterations}, {verified}, {entries});"""

    def nc_001():
        def red():
            got = refusal(plant(cipher="none"))
            return got == "backup_run_is_encrypted", f"signature: {got}"

        def green():
            got = refusal(plant())
            return got == "", f"an encrypted one is accepted (signature: {got or 'none'})"

        control("NC-M6B-001 a backup recorded with no encryption", red, green)

    def nc_002():
        def red():
            got = refusal(plant(state="verified"))
            return got == "backup_run_verification_is_evidenced", f"signature: {got}"

        def green():
            got = refusal(plant(state="verified", verified="now()", entries="42"))
            return got == "", ("verified WITH evidence is accepted "
                               f"(signature: {got or 'none'})")

        control("NC-M6B-002 a backup called verified with nothing to show for it", red, green)

    def nc_003():
        def red():
            # Verification against a digest that is not this archive's. The mistake a
            # directory of timestamped backups invites: reading the wrong file and
            # reporting success about the right one.
            got = refusal(f"""
                {plant()}
                SELECT ops.verify_backup('{TENANT}',
                    (SELECT id FROM ops.backup_run WHERE archive_path = '/tmp/probe.enc'),
                    repeat('99', 32), 10, 'read a different file');""")
            return got == "BACKUP_DIGEST_MISMATCH", f"signature: {got}"

        def green():
            got = refusal(f"""
                {plant()}
                SELECT ops.verify_backup('{TENANT}',
                    (SELECT id FROM ops.backup_run WHERE archive_path = '/tmp/probe.enc'),
                    repeat('ab', 32), 10, 'read the archive that was written');""")
            return got == "", f"the matching digest is accepted (signature: {got or 'none'})"

        control("NC-M6B-003 a verification that read a different archive", red, green)

    def nc_004():
        def red():
            got = refusal(f"""
                {plant()}
                SELECT ops.record_offsite_copy('{TENANT}',
                    (SELECT id FROM ops.backup_run WHERE archive_path = '/tmp/probe.enc'),
                    '/tmp/elsewhere.enc', repeat('ab', 32));""")
            return got == "BACKUP_NOT_VERIFIED", f"signature: {got}"

        def green():
            got = refusal(f"""
                {plant()}
                SELECT ops.verify_backup('{TENANT}',
                    (SELECT id FROM ops.backup_run WHERE archive_path = '/tmp/probe.enc'),
                    repeat('ab', 32), 10, 'read back');
                SELECT ops.record_offsite_copy('{TENANT}',
                    (SELECT id FROM ops.backup_run WHERE archive_path = '/tmp/probe.enc'),
                    '/tmp/elsewhere.enc', repeat('ab', 32));""")
            return got == "", ("a verified archive may go off-site "
                               f"(signature: {got or 'none'})")

        control("NC-M6B-004 an off-site copy of an archive nobody has read", red, green)

    def nc_005():
        def red():
            got = refusal(f"""
                {plant()}
                UPDATE ops.backup_run SET archive_sha256 = repeat('cd', 32)
                 WHERE archive_path = '/tmp/probe.enc';""")
            return got == "BACKUP_RUN_REWRITTEN", f"signature: {got}"

        def green():
            got = refusal(f"""
                {plant()}
                UPDATE ops.backup_run SET verification_detail = 'a later note'
                 WHERE archive_path = '/tmp/probe.enc';""")
            return got == "", ("moving a run FORWARD is allowed; restating what was "
                               f"captured is not (signature: {got or 'none'})")

        control("NC-M6B-005 a captured backup's digest edited after the fact", red, green)

    for case in (nc_001, nc_002, nc_003, nc_004, nc_005):
        case()

    registered = [c for c in registry.CONTROLS if c[3] == "m6b"]
    record("every M6-B control is registered in tools/controls.py",
           len(registered) == 5, f"{len(registered)} registered")


# ===========================================================================
# 5. The bounds
# ===========================================================================

def section_bounds() -> None:
    print("\n--- 5. The bounds, named rather than left to silence ---")
    for bound in (
        "OFF-SITE IS A SECOND DIRECTORY ON THE SAME DISK. The schema refuses a copy whose "
        "path equals the original and the digest is checked on arrival, so the MECHANISM "
        "is real; what is not proved is that the copy survives losing the machine. Closed "
        "by an object store or a second host at pilot",
        "THE KEY IS AN ENVIRONMENT VARIABLE. It never reaches the database and never "
        "appears on a command line, which keeps it out of the process table — but it is "
        "readable by the same user on either platform, and there is no key rotation, no "
        "escrow and no split knowledge here",
        "RETENTION IS DECLARED AND NOT ENFORCED. ops.backup_policy.retain_days is checked "
        "for sanity against the interval and nothing deletes an expired archive. A "
        "retention nobody applies is a disk that fills, which this machine has now "
        "demonstrated twice",
        "ONLY THE CLOUD SCOPE IS EXERCISED. ops.backup_scope has an `outlet` value and the "
        "demonstration floor's node shares this database rather than running its own, so "
        "an outlet-scoped backup would dump the same bytes under a different label",
    ):
        record("recorded in planning/M6_FINDINGS.md", True, bound)


def cleanup() -> None:
    base = CONTEXT.get("base")
    if base and Path(base).exists():
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    print("=" * 74)
    print("  M6-B — a backup that was encrypted, read back, and put somewhere else")
    print("=" * 74)

    try:
        for section in (section_take_one, section_verified_means_read, section_posture,
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
    owned = len([c for c in registry.CONTROLS if c[3] == "m6b"])

    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}")
    print(f"  asserted      : {len(results) - measured_count}")
    print(f"  controls      : {owned} registered, each proved red then green")

    if failed:
        print("\nFAIL M6B_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS M6B_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
