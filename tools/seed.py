#!/usr/bin/env python3
"""Seed runner — ordered, recorded and checksum-locked, separate from migrations.

Seeds are not migrations. They create data rather than structure, they differ between
environments, and they must never enter the migration history (FR-DAT-016). But an
environment whose seed provenance cannot be established is an environment nobody can
audit, so seeds get the same discipline in their own record: an ordered history, an
applied-at row per seed, and a checksum lock that refuses a seed edited after it ran.

The record lives in schema ``seed_history``, the lock is independent of the migration
lock, and this is a separate tool from tools/migrate.py. The two share only a psql
transport; neither can satisfy the other's lock.

Two identities, deliberately. Bookkeeping runs as the migration role, which owns the
record; seed CONTENT is applied through the least-privileged application role, so every
seeded row has to pass the same row level security the application runs under. The
application role can read the record but cannot write to it, so it cannot forge
provenance for data it inserted.

Usage:
    python3 tools/seed.py --dsn <migrator-dsn> --content-dsn <app-dsn> status
    python3 tools/seed.py --dsn <migrator-dsn> --content-dsn <app-dsn> preflight
    python3 tools/seed.py --dsn <migrator-dsn> --content-dsn <app-dsn> apply

Exit 0 = success. Exit 1 = a failure with a named signature.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate import MigrationFailure, checksum, psql, psql_file, sql_literal  # noqa: E402

SEED_PATTERN = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
FIRST_VERSION = 1

HISTORY_DDL = """
CREATE SCHEMA IF NOT EXISTS seed_history;

CREATE TABLE IF NOT EXISTS seed_history.applied_seed (
    version     integer     PRIMARY KEY,
    filename    text        NOT NULL UNIQUE,
    checksum    text        NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    applied_by  text        NOT NULL DEFAULT current_user
);

COMMENT ON TABLE seed_history.applied_seed IS
    'Ordered, checksum-locked record of applied seeds. Deliberately separate from '
    'migration.schema_migrations: seeds are data, not structure, and the two histories '
    'must not be able to vouch for each other.';

REVOKE ALL ON seed_history.applied_seed FROM PUBLIC;

-- The application role may read seed provenance — readiness reports it — but may not
-- write it. Recording a seed is the runner's job, under the migration identity.
GRANT USAGE ON SCHEMA seed_history TO hospitality_app;
GRANT SELECT ON seed_history.applied_seed TO hospitality_app;
"""


def discover(seeds_dir: Path) -> list[tuple[int, Path]]:
    if not seeds_dir.is_dir():
        raise MigrationFailure("SEEDS_DIR_ABSENT", str(seeds_dir))

    found: dict[int, Path] = {}
    for entry in sorted(seeds_dir.iterdir()):
        if entry.name.startswith(".") or not entry.is_file():
            continue
        match = SEED_PATTERN.match(entry.name)
        if not match:
            raise MigrationFailure(
                "MALFORMED_SEED_NAME", f"{entry.name} does not match NNNN_lower_snake_case.sql")
        version = int(match.group(1))
        if version in found:
            raise MigrationFailure(
                "DUPLICATE_SEED_VERSION",
                f"version {version:04d} appears as both {found[version].name} and {entry.name}")
        found[version] = entry

    if not found:
        raise MigrationFailure("NO_SEEDS", f"no seed files in {seeds_dir}")

    ordered = sorted(found.items())
    if ordered[0][0] != FIRST_VERSION:
        raise MigrationFailure(
            "SEED_HISTORY_DOES_NOT_START_AT_0001",
            f"first seed is {ordered[0][0]:04d}; the history must begin at 0001")
    for index, (version, path) in enumerate(ordered, start=FIRST_VERSION):
        if version != index:
            raise MigrationFailure(
                "SEED_SEQUENCE_GAP", f"expected {index:04d}, found {version:04d} ({path.name})")
    return ordered


def ensure_history(dsn: str) -> None:
    psql(dsn, HISTORY_DDL, tuples_only=False)


def applied_state(dsn: str) -> dict[int, tuple[str, str]]:
    out = psql(dsn, "SELECT version, filename, checksum FROM seed_history.applied_seed ORDER BY version;")
    state: dict[int, tuple[str, str]] = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        version, filename, digest = line.split("\x1f")
        state[int(version)] = (filename, digest)
    return state


def preflight(dsn: str, seeds_dir: Path) -> list[tuple[int, Path]]:
    ordered = discover(seeds_dir)
    ensure_history(dsn)
    state = applied_state(dsn)
    on_disk = dict(ordered)

    for version, (filename, recorded) in sorted(state.items()):
        path = on_disk.get(version)
        if path is None:
            raise MigrationFailure(
                "APPLIED_SEED_MISSING",
                f"{filename} (version {version:04d}) is recorded as applied but absent from disk")
        if path.name != filename:
            raise MigrationFailure(
                "APPLIED_SEED_RENAMED",
                f"version {version:04d} was applied as {filename} but is now {path.name}")
        current = checksum(path)
        if current != recorded:
            raise MigrationFailure(
                "SEED_CHECKSUM_MISMATCH",
                f"{filename} changed after it was applied "
                f"(applied {recorded[:16]}…, on disk {current[:16]}…). "
                f"Write a new seed rather than editing one that has already run.")
    return ordered


def cmd_apply(dsn: str, seeds_dir: Path, content_dsn: str) -> int:
    ordered = preflight(dsn, seeds_dir)
    state = applied_state(dsn)
    pending = [(v, p) for v, p in ordered if v not in state]

    if not pending:
        print("PASS SEEDS_UP_TO_DATE")
        print(f"  applied seeds : {len(state)}")
        return 0

    for version, path in pending:
        digest = checksum(path)
        print(f"applying {path.name} …", flush=True)
        try:
            psql_file(content_dsn, path)  # content goes in as the application role
        except MigrationFailure as failure:
            # The shared transport speaks in migration terms; a seed failure must not be
            # reported as a migration failure, or an operator looks in the wrong history.
            raise MigrationFailure(
                "SEED_APPLY_FAILED",
                f"{path.name}: {failure.detail}\n"
                f"  If this reports a duplicate key, the data is already present while "
                f"this seed is unrecorded — seeds were applied around the runner, which "
                f"leaves the environment with no provenance. Rebuild, or apply through "
                f"this runner from the start.") from failure
        psql(dsn, f"""
            INSERT INTO seed_history.applied_seed (version, filename, checksum)
            VALUES ({version}, {sql_literal(path.name)}, {sql_literal(digest)});
        """, tuples_only=False)
        print(f"  applied {path.name}  sha256={digest[:16]}…")

    print("PASS SEEDS_APPLIED")
    print(f"  newly applied : {len(pending)}")
    print(f"  total applied : {len(state) + len(pending)}")
    return 0


def cmd_preflight(dsn: str, seeds_dir: Path, content_dsn: str) -> int:
    ordered = preflight(dsn, seeds_dir)
    state = applied_state(dsn)
    print("PASS SEED_PREFLIGHT")
    print(f"  seeds on disk  : {len(ordered)}")
    print(f"  already applied: {len(state)}")
    print("  checksum lock  : intact")
    return 0


def cmd_status(dsn: str, seeds_dir: Path, content_dsn: str) -> int:
    ordered = discover(seeds_dir)
    ensure_history(dsn)
    state = applied_state(dsn)
    print(f"{'version':>7}  {'status':<9}  {'checksum':<18}  filename")
    for version, path in ordered:
        if version in state:
            status = "applied" if state[version][1] == checksum(path) else "EDITED"
        else:
            status = "pending"
        print(f"{version:>7}  {status:<9}  {checksum(path)[:16]}…  {path.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ordered, checksum-locked seed runner.")
    parser.add_argument("command", choices=["apply", "preflight", "status"])
    parser.add_argument("--dsn", required=True,
                        help="migration identity; owns and writes the seed record")
    parser.add_argument("--content-dsn",
                        help="application identity; applies seed content under RLS. "
                             "Defaults to --dsn, which is correct only for a local probe.")
    parser.add_argument("--seeds", default="seeds")
    args = parser.parse_args()

    handler = {"apply": cmd_apply, "preflight": cmd_preflight, "status": cmd_status}[args.command]
    try:
        return handler(args.dsn, Path(args.seeds), args.content_dsn or args.dsn)
    except MigrationFailure as failure:
        print(f"FAIL {failure.signature}", file=sys.stderr)
        print(f"  {failure.detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
