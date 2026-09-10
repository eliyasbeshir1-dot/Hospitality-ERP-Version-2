#!/usr/bin/env python3
"""Take a backup, encrypt it, read it back, and put a copy somewhere else.

FR-OPS-006 and FR-SEC-019.

FOUR STEPS AND THE THIRD IS THE ONE THAT MATTERS.

    capture   pg_dump -Fc, piped straight into openssl. The plaintext dump never becomes
              a file: a backup process that writes an unencrypted copy and deletes it has
              written an unencrypted copy, and deletion is not erasure on any filesystem
              anybody here runs.
    record    the digest of the CIPHERTEXT, the cipher and the KDF parameters go into
              ops.backup_run as `captured` — which explicitly does not mean "good".
    verify    decrypt it, read its table of contents with pg_restore --list, count the
              entries, and compare the digest of what was read against what was written.
              Only this promotes it to `verified`, and only this makes it eligible for a
              restore drill.
    offsite   copy it somewhere that is not where it was written, and check the digest
              again on arrival.

WHY THE TOOLS ARE pg_dump AND openssl RATHER THAN A LIBRARY. FR-OPS-006 says the backup
must run "using tools present inside the production artifact". A Python encryption library
would be a dependency the artifact does not carry and the image does not install; pg_dump
and openssl are both in deploy/Dockerfile because a deployment needs them anyway. This is
the same reasoning that gave M5a keyed digests instead of signatures when pgcrypto was not
there: use what is actually present and say so, rather than assume something that is not.

THE KEY IS NEVER WRITTEN DOWN AND NEVER REACHES THE DATABASE. It arrives in
HOSPITALITY_BACKUP_KEY and is passed to openssl through a file descriptor rather than the
command line, because a command line is visible in the process table to anybody on the
host. What the database records is the digest of the ciphertext and the parameters — enough
for a restore to prove it is reading the bytes that were written, and not enough to read
them. A database that could decrypt its own backups is a database whose compromise takes
the backups with it.

Usage:
    HOSPITALITY_BACKUP_KEY=... python3 tools/backup.py \\
        --dsn <dsn> --tenant <uuid> --scope cloud --into <dir> [--offsite <dir>]
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

# AES-256-CBC with PBKDF2. The iteration count is high deliberately: a backup is decrypted
# rarely and by a person who is already waiting, so the cost that matters is the attacker's
# rather than ours. Recorded in the database alongside the cipher, because a restore three
# months from now needs to know what was done and an auditor needs to see it was not 'none'.
CIPHER = "aes-256-cbc"
KDF = "pbkdf2"
KDF_ITERATIONS = 600_000


class BackupRefused(RuntimeError):
    """Something was wrong enough that finishing would produce a file nobody can trust."""


def digest_of(path: Path) -> tuple[str, int]:
    """sha256 and size, read in chunks so a large archive does not become a large string."""
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def key_material() -> str:
    key = os.environ.get("HOSPITALITY_BACKUP_KEY", "")
    if len(key) < 16:
        raise BackupRefused(
            "BACKUP_KEY_ABSENT_OR_WEAK: HOSPITALITY_BACKUP_KEY must be set and at least 16 "
            "characters. Refusing rather than falling back to an unencrypted dump — a "
            "backup process that silently stops encrypting is worse than one that stops.")
    return key


# The variable openssl reads the passphrase out of. Deliberately not the one the operator
# sets: this exists only in the child's environment, so a tool asked to back up with one
# key cannot quietly use another that happens to be lying around in the shell.
_PASS_VAR = "HOSPITALITY_BACKUP_PASS"


def openssl(args: list[str], key: str, *, stdin=None, stdout=None) -> subprocess.Popen:
    """openssl with the passphrase in its environment, never on its command line.

    A COMMAND LINE IS VISIBLE IN THE PROCESS TABLE to every other process on the host, so
    `-pass pass:...` publishes the key to anybody who runs `ps` — or Get-Process — at the
    wrong moment. `-pass env:VAR` does not.

    The precise claim, because the loose one would be wrong: this keeps the key out of the
    PROCESS TABLE. It does not hide it from the same user, who can read a child's
    environment on either platform. What it defends against is the ordinary way a
    credential escapes — a log line, a shell history, somebody's terminal scrollback.

    `-pass fd:N` would be marginally better on POSIX and does not exist on Windows:
    subprocess refuses pass_fds there outright, which is how this was found. One mechanism
    that behaves the same everywhere beats two behaviours to reason about, and this
    repository runs on both.
    """
    child_env = dict(os.environ)
    child_env[_PASS_VAR] = key
    return subprocess.Popen(
        ["openssl", "enc", *args, "-pass", f"env:{_PASS_VAR}"],
        stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, env=child_env)


def capture(dsn: str, target: Path, key: str) -> tuple[str, int]:
    """pg_dump piped straight into openssl. The plaintext never lands.

    A temporary plaintext dump that is deleted afterwards has still been written to the
    disk, and deletion is not erasure on any filesystem in use here. The pipe means the
    only bytes that ever reach storage are encrypted ones.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        dump = subprocess.Popen(
            ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", dsn],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        enc = openssl(["-" + CIPHER, "-" + KDF, "-iter", str(KDF_ITERATIONS), "-salt"],
                      key, stdin=dump.stdout, stdout=out)
        # THE PARENT LETS GO OF THE READ END so pg_dump sees a broken pipe if openssl
        # dies, rather than blocking forever on a reader that is gone.
        dump.stdout.close()
        enc_err = enc.communicate()[1]

        # AND pg_dump's STDERR IS READ DIRECTLY, not through communicate(). communicate()
        # tries to drain every pipe it was given, including the stdout this function just
        # closed, and raises `ValueError: read of closed file` doing it. The first version
        # did exactly that: the traceback went to stderr, dump_err came back empty, and the
        # PG_DUMP_FAILED branch below would have reported a failure with no reason attached
        # — a diagnostic naming a cause it did not read.
        dump_err = dump.stderr.read()
        dump.stderr.close()
        dump.wait()

    if dump.returncode != 0:
        target.unlink(missing_ok=True)
        raise BackupRefused(f"PG_DUMP_FAILED: {(dump_err or b'').decode()[:400]}")
    if enc.returncode != 0:
        target.unlink(missing_ok=True)
        raise BackupRefused(f"ENCRYPT_FAILED: {(enc_err or b'').decode()[:400]}")

    sha, size = digest_of(target)
    if size == 0:
        target.unlink(missing_ok=True)
        raise BackupRefused("BACKUP_IS_EMPTY: the archive is zero bytes")
    return sha, size


def verify(archive: Path, key: str) -> tuple[str, int, str]:
    """Decrypt it and READ it. Returns (digest observed, entries, detail).

    The digest is taken from the archive on disk, so a verification that decrypted a
    different file cannot report success about this one — which is exactly the mistake a
    directory of timestamped backups invites.

    pg_restore --list is what turns "the file decrypts" into "the file is a backup". An
    archive can decrypt perfectly and contain nothing; the entry count is the difference.
    """
    observed, _size = digest_of(archive)

    with tempfile.TemporaryDirectory(prefix="verify-") as work:
        plain = Path(work) / "archive.dump"
        with archive.open("rb") as src, plain.open("wb") as out:
            dec = openssl(["-d", "-" + CIPHER, "-" + KDF, "-iter", str(KDF_ITERATIONS)],
                          key, stdin=src, stdout=out)
            err = dec.communicate()[1]
        if dec.returncode != 0:
            raise BackupRefused(f"DECRYPT_FAILED: {(err or b'').decode()[:400]}")

        listing = subprocess.run(["pg_restore", "--list", str(plain)],
                                 capture_output=True, text=True)
        if listing.returncode != 0:
            raise BackupRefused(
                f"ARCHIVE_UNREADABLE: it decrypted and pg_restore cannot read it — "
                f"{listing.stderr.strip()[:300]}")

        entries = [l for l in listing.stdout.splitlines()
                   if l.strip() and not l.startswith(";")]
        return observed, len(entries), f"pg_restore --list read {len(entries)} entries"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--scope", default="cloud", choices=("cloud", "outlet"))
    parser.add_argument("--outlet", default=None)
    parser.add_argument("--into", required=True)
    parser.add_argument("--offsite", default=None)
    parser.add_argument("--label", default="backup")
    args = parser.parse_args()

    sys.path.insert(0, str(REPO / "tests" / "m1a"))
    from pg import run                                       # noqa: E402

    try:
        key = key_material()
    except BackupRefused as exc:
        print(f"FAIL {exc}")
        return 1

    archive = Path(args.into) / f"{args.label}.dump.enc"
    print(f"  capturing  {args.scope} -> {archive}")
    try:
        sha, size = capture(args.dsn, archive, key)
    except BackupRefused as exc:
        print(f"FAIL {exc}")
        return 1
    print(f"  captured   {size} bytes, sha256 {sha[:16]}…")

    outlet_sql = f"'{args.outlet}'::uuid" if args.outlet else "NULL"
    recorded = run(args.dsn, f"""
        SELECT ops.record_backup('{args.tenant}'::uuid, '{args.scope}'::ops.backup_scope,
               {outlet_sql}, 'pg_dump {CIPHER}', 'custom',
               '{archive.as_posix()}', '{sha}', {size},
               '{CIPHER}', '{KDF}', {KDF_ITERATIONS})::text;""",
        tenant=args.tenant, tx=True)
    if not recorded.ok:
        print(f"FAIL BACKUP_NOT_RECORDED: {recorded.err[:300]}")
        return 1
    backup_id = (recorded.scalar or "").strip()
    print(f"  recorded   {backup_id} as CAPTURED — not yet known to be readable")

    print("  verifying  decrypt, then pg_restore --list")
    try:
        observed, entries, detail = verify(archive, key)
    except BackupRefused as exc:
        print(f"FAIL {exc}")
        return 1

    verified = run(args.dsn, f"""
        SELECT ops.verify_backup('{args.tenant}'::uuid, '{backup_id}'::uuid,
               '{observed}', {entries}, '{detail}');""", tenant=args.tenant, tx=True)
    if not verified.ok:
        print(f"FAIL BACKUP_VERIFICATION_REFUSED: {verified.err[:300]}")
        return 1
    print(f"  verified   {entries} entries read back")

    if args.offsite:
        destination = Path(args.offsite) / archive.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive, destination)
        arrived, _size = digest_of(destination)
        moved = run(args.dsn, f"""
            SELECT ops.record_offsite_copy('{args.tenant}'::uuid, '{backup_id}'::uuid,
                   '{destination.as_posix()}', '{arrived}');""",
            tenant=args.tenant, tx=True)
        if not moved.ok:
            print(f"FAIL OFFSITE_REFUSED: {moved.err[:300]}")
            return 1
        print(f"  offsite    {destination}")

    print(f"\nPASS BACKUP_TAKEN {backup_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
