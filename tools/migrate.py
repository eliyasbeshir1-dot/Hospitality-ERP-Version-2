#!/usr/bin/env python3
"""SQL-first migration runner with checksum locking.

Requirements: FR-DAT-001 (ordered SQL history beginning at 0001),
              FR-DAT-016 (checksum lock, preflight, forward-only).

Design notes
------------
SQL-first: every migration is a plain ``.sql`` file. This runner never generates
DDL and never rewrites a migration. It orders them, applies them in a transaction
and records what it applied.

Forward-only: there is no ``down`` command and no rollback of an applied
migration. Recovery is by restore, not by reverse migration.

Checksum locking: the SHA-256 of every applied migration is stored. Preflight
recomputes them and refuses to do anything at all if one has changed, so an edited
migration is caught before the next one is applied, not after.

Never imports the v1.1 prototype history: preflight fails if a legacy history
table is present in the target database (FR-DAT-001, FR-GOV-006).

Usage:
    python3 tools/migrate.py --dsn <dsn> status
    python3 tools/migrate.py --dsn <dsn> preflight
    python3 tools/migrate.py --dsn <dsn> apply

Exit 0 = success. Exit 1 = a failure with a named signature. Standard library only;
psql is the transport, which keeps the tool SQL-first end to end.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

MIGRATION_PATTERN = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
FIRST_VERSION = 1

# A v1.1 artifact in the target database means the frozen prototype's history was
# imported. That is forbidden outright.
LEGACY_HISTORY_TABLES = [
    ("public", "django_migrations"),
    ("public", "alembic_version"),
    ("public", "knex_migrations"),
    ("public", "schema_version"),
    ("public", "flyway_schema_history"),
]

HISTORY_DDL = """
CREATE SCHEMA IF NOT EXISTS migration;

CREATE TABLE IF NOT EXISTS migration.schema_migrations (
    version      integer     PRIMARY KEY,
    filename     text        NOT NULL UNIQUE,
    checksum     text        NOT NULL,
    applied_at   timestamptz NOT NULL DEFAULT now(),
    applied_by   text        NOT NULL DEFAULT current_user,
    duration_ms  integer     NOT NULL
);

COMMENT ON TABLE migration.schema_migrations IS
    'Ordered, checksum-locked migration history (FR-DAT-001, FR-DAT-016). '
    'Forward-only: rows are inserted, never updated or deleted.';

REVOKE ALL ON migration.schema_migrations FROM PUBLIC;
"""


class MigrationFailure(Exception):
    """A failure carrying a stable signature for the verification harness."""

    def __init__(self, signature: str, detail: str) -> None:
        super().__init__(f"{signature}: {detail}")
        self.signature = signature
        self.detail = detail


# --------------------------------------------------------------------------
# psql transport
# --------------------------------------------------------------------------

def psql(dsn: str, sql: str, *, tuples_only: bool = True) -> str:
    """Run SQL through psql and return stdout, aborting on the first error."""
    cmd = ["psql", dsn, "-v", "ON_ERROR_STOP=1", "--no-psqlrc", "-X"]
    if tuples_only:
        cmd += ["-t", "-A", "-F", "\x1f"]
    result = subprocess.run(
        cmd, input=sql, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode != 0:
        raise MigrationFailure("SQL_ERROR", result.stderr.strip() or result.stdout.strip())
    return result.stdout


def psql_file(dsn: str, path: Path) -> None:
    """Apply one migration file in a single transaction."""
    cmd = ["psql", dsn, "-v", "ON_ERROR_STOP=1", "--no-psqlrc", "-X",
           "--single-transaction", "-f", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise MigrationFailure(
            "MIGRATION_FAILED", f"{path.name}: {result.stderr.strip() or result.stdout.strip()}"
        )


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


# --------------------------------------------------------------------------
# Migration discovery
# --------------------------------------------------------------------------

def checksum(path: Path) -> str:
    """SHA-256 of the file's bytes.

    Read as bytes from disk, never as decoded text, so a checkout that rewrote
    line endings is reported as the mismatch it is rather than silently normalised.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover(migrations_dir: Path) -> list[tuple[int, Path]]:
    """Return the ordered migration history, rejecting any malformed sequence."""
    if not migrations_dir.is_dir():
        raise MigrationFailure("MIGRATIONS_DIR_ABSENT", str(migrations_dir))

    found: dict[int, Path] = {}
    for entry in sorted(migrations_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if not entry.is_file():
            raise MigrationFailure("UNEXPECTED_ENTRY", f"{entry.name} is not a file")
        match = MIGRATION_PATTERN.match(entry.name)
        if not match:
            raise MigrationFailure(
                "MALFORMED_MIGRATION_NAME",
                f"{entry.name} does not match NNNN_lower_snake_case.sql",
            )
        version = int(match.group(1))
        if version in found:
            raise MigrationFailure(
                "DUPLICATE_MIGRATION_VERSION",
                f"version {version:04d} appears as both {found[version].name} and {entry.name}",
            )
        found[version] = entry

    if not found:
        raise MigrationFailure("NO_MIGRATIONS", f"no migration files in {migrations_dir}")

    ordered = sorted(found.items())
    if ordered[0][0] != FIRST_VERSION:
        raise MigrationFailure(
            "HISTORY_DOES_NOT_START_AT_0001",
            f"first migration is {ordered[0][0]:04d}; the history must begin at 0001",
        )
    for index, (version, path) in enumerate(ordered, start=FIRST_VERSION):
        if version != index:
            raise MigrationFailure(
                "MIGRATION_SEQUENCE_GAP",
                f"expected {index:04d}, found {version:04d} ({path.name})",
            )
    return ordered


# --------------------------------------------------------------------------
# History state
# --------------------------------------------------------------------------

def ensure_history(dsn: str) -> None:
    psql(dsn, HISTORY_DDL, tuples_only=False)


def applied_state(dsn: str) -> dict[int, tuple[str, str]]:
    out = psql(dsn, """
        SELECT version, filename, checksum
        FROM migration.schema_migrations
        ORDER BY version;
    """)
    state: dict[int, tuple[str, str]] = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        version, filename, digest = line.split("\x1f")
        state[int(version)] = (filename, digest)
    return state


def assert_no_legacy_history(dsn: str) -> None:
    """FR-DAT-001 / FR-GOV-006 — the v1.1 history is never imported."""
    checks = " UNION ALL ".join(
        f"SELECT {sql_literal(f'{s}.{t}')} AS name WHERE to_regclass({sql_literal(f'{s}.{t}')}) IS NOT NULL"
        for s, t in LEGACY_HISTORY_TABLES
    )
    out = psql(dsn, f"SELECT name FROM ({checks}) found;").strip()
    if out:
        raise MigrationFailure(
            "LEGACY_MIGRATION_HISTORY_PRESENT",
            "the frozen v1.1 history must never be imported; found " + ", ".join(out.split("\n")),
        )


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def preflight(dsn: str, migrations_dir: Path) -> list[tuple[int, Path]]:
    """Verify the history is intact. Refuses to proceed on any discrepancy."""
    ordered = discover(migrations_dir)
    ensure_history(dsn)
    assert_no_legacy_history(dsn)
    state = applied_state(dsn)
    on_disk = dict(ordered)

    for version, (filename, recorded) in sorted(state.items()):
        path = on_disk.get(version)
        if path is None:
            raise MigrationFailure(
                "APPLIED_MIGRATION_MISSING",
                f"{filename} (version {version:04d}) is recorded as applied but absent from disk",
            )
        if path.name != filename:
            raise MigrationFailure(
                "APPLIED_MIGRATION_RENAMED",
                f"version {version:04d} was applied as {filename} but is now {path.name}",
            )
        current = checksum(path)
        if current != recorded:
            raise MigrationFailure(
                "MIGRATION_CHECKSUM_MISMATCH",
                f"{filename} changed after it was applied "
                f"(applied {recorded[:16]}…, on disk {current[:16]}…). "
                f"Migrations are forward-only; write a new migration instead of editing this one.",
            )
    return ordered


def cmd_apply(dsn: str, migrations_dir: Path) -> int:
    ordered = preflight(dsn, migrations_dir)
    state = applied_state(dsn)
    pending = [(v, p) for v, p in ordered if v not in state]

    if not pending:
        print("PASS MIGRATIONS_UP_TO_DATE")
        print(f"  applied migrations : {len(state)}")
        return 0

    for version, path in pending:
        digest = checksum(path)
        print(f"applying {path.name} …", flush=True)
        started = psql(dsn, "SELECT clock_timestamp();").strip()
        psql_file(dsn, path)
        psql(dsn, f"""
            INSERT INTO migration.schema_migrations
                (version, filename, checksum, duration_ms)
            VALUES ({version}, {sql_literal(path.name)}, {sql_literal(digest)},
                    GREATEST(0, EXTRACT(MILLISECONDS FROM
                        clock_timestamp() - {sql_literal(started)}::timestamptz)::integer));
        """, tuples_only=False)
        print(f"  applied {path.name}  sha256={digest[:16]}…")

    print("PASS MIGRATIONS_APPLIED")
    print(f"  newly applied      : {len(pending)}")
    print(f"  total applied      : {len(state) + len(pending)}")
    return 0


def cmd_preflight(dsn: str, migrations_dir: Path) -> int:
    ordered = preflight(dsn, migrations_dir)
    state = applied_state(dsn)
    print("PASS MIGRATION_PREFLIGHT")
    print(f"  migrations on disk : {len(ordered)}")
    print(f"  already applied    : {len(state)}")
    print(f"  checksum lock      : intact")
    return 0


def cmd_status(dsn: str, migrations_dir: Path) -> int:
    ordered = discover(migrations_dir)
    ensure_history(dsn)
    state = applied_state(dsn)
    print(f"{'version':>7}  {'status':<9}  {'checksum':<18}  filename")
    for version, path in ordered:
        if version in state:
            recorded = state[version][1]
            status = "applied" if recorded == checksum(path) else "EDITED"
        else:
            status = "pending"
        print(f"{version:>7}  {status:<9}  {checksum(path)[:16]}…  {path.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SQL-first, forward-only migration runner.")
    parser.add_argument("command", choices=["apply", "preflight", "status"])
    parser.add_argument("--dsn", required=True, help="PostgreSQL connection string")
    parser.add_argument("--migrations", default="migrations", help="migrations directory")
    args = parser.parse_args()

    handler = {"apply": cmd_apply, "preflight": cmd_preflight, "status": cmd_status}[args.command]
    try:
        return handler(args.dsn, Path(args.migrations))
    except MigrationFailure as failure:
        print(f"FAIL {failure.signature}", file=sys.stderr)
        print(f"  {failure.detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
