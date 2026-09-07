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
from console import use_utf8_output  # noqa: E402

use_utf8_output()


sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate import MigrationFailure, checksum, psql, psql_file, sql_literal  # noqa: E402

SEED_PATTERN = re.compile(r"^(\d{4})_([a-z0-9_]+?)(\.provision)?\.sql$")
FIRST_VERSION = 1

# ---------------------------------------------------------------------------
# THE PROVISIONING CLASS, AND WHY IT IS NARROW.
# ---------------------------------------------------------------------------
# Seed content runs as the application role so every row passes the row level security
# the service passes. Two tables cannot be written that way and must not become writable:
# migration 0012 grants hospitality_app SELECT and nothing more on
# fulfillment.station_profile and the routing tables, because installing a station is a
# configuration act rather than something the running service does. Widening that grant to
# make seeding easier is the move the standing rule forbids.
#
# So a seed named *.provision.sql is applied under the MIGRATION identity instead. That is
# the same split this runner already makes for its own bookkeeping, and the same one every
# fixture makes when it writes a station profile as the administrator.
#
# It is deliberately not a general escape hatch. A provisioning seed may write these
# tables and no others; the set is checked before the file is applied, and a seed that
# reaches for anything else is refused by name. Without that, "the app role cannot write
# it" becomes a reason to move any inconvenient row into the privileged pass, and the
# guarantee that seeded content passes real RLS quietly stops being true.
PROVISIONABLE_TABLES = frozenset({
    "fulfillment.station_profile",
    "fulfillment.routing_rule",
    "fulfillment.routing_rule_set",
})

# The grant that must still hold after seeding. Asserted rather than assumed: a later
# provisioning seed could issue a GRANT and nothing else here would notice.
RUNTIME_SELECT_ONLY = {
    "fulfillment.station_profile": {"SELECT"},
    "fulfillment.routing_rule": {"SELECT"},
    "fulfillment.routing_rule_set": {"SELECT"},
}

_COMMENT = re.compile(r"--[^\n]*")
_WRITE_TARGET = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([a-z_]+\.[a-z_]+)", re.IGNORECASE)
_GRANT = re.compile(r"\bGRANT\b", re.IGNORECASE)


def is_provisioning(path: Path) -> bool:
    return path.name.endswith(".provision.sql")


def written_tables(path: Path) -> set[str]:
    """Which tables a seed writes, read from the statements rather than from the bytes.

    Line comments are stripped first. A sentence in a header describing a table this seed
    must not touch is prose, not a write, and a scanner that could not tell the difference
    would be the defect this repository has already had to repair twice — once in the
    route census, once in a guard that matched its own explanatory comment.
    """
    text = _COMMENT.sub("", path.read_text(encoding="utf-8"))
    return {match.group(1).lower() for match in _WRITE_TARGET.finditer(text)}


def assert_provisioning_is_narrow(path: Path) -> None:
    """A provisioning seed writes the configuration tables and nothing else."""
    reached = written_tables(path)
    beyond = sorted(reached - PROVISIONABLE_TABLES)
    if beyond:
        raise MigrationFailure(
            "PROVISIONING_SEED_TOO_BROAD",
            f"{path.name} writes {', '.join(beyond)} under the migration identity. The "
            f"provisioning pass exists for {', '.join(sorted(PROVISIONABLE_TABLES))} and "
            f"nothing else — every other seeded row goes in as the application role so it "
            f"passes the row level security the service passes. Move these rows to a "
            f"content seed, or say why the set should grow.")
    if _GRANT.search(_COMMENT.sub("", path.read_text(encoding="utf-8"))):
        raise MigrationFailure(
            "PROVISIONING_SEED_GRANTS_PRIVILEGE",
            f"{path.name} issues a GRANT. A provisioning seed provisions data; widening a "
            f"privilege is a migration, and doing it here would defeat the check that the "
            f"runtime grant is unchanged.")


def assert_content_is_unprivileged(path: Path) -> None:
    """A CONTENT seed may not write the tables only provisioning may write.

    The split is enforced in both directions on purpose. Checking only that provisioning
    stays narrow would leave the other half — a content seed reaching for a configuration
    table — to fail with a bare permission error, which reads as a broken seed rather than
    as a rule. Naming it here means the next author is told which pass the row belongs in.
    """
    overreach = sorted(written_tables(path) & PROVISIONABLE_TABLES)
    if overreach:
        raise MigrationFailure(
            "CONTENT_SEED_WRITES_CONFIGURATION",
            f"{path.name} writes {', '.join(overreach)} as the application role, which "
            f"holds SELECT on it and will refuse. These are configuration and belong in a "
            f"*.provision.sql seed, applied under the migration identity.")


def assert_runtime_grant_unchanged(dsn: str) -> None:
    """The application role still holds SELECT and only SELECT, after everything ran.

    The point of the privileged pass is that it does NOT widen what the running service
    can do. That is a claim about the database after seeding, so it is read back from the
    catalog rather than argued from the fact that no seed said GRANT.
    """
    out = psql(dsn, """
        SELECT c.relname, coalesce(string_agg(DISTINCT g.privilege_type, ',' ORDER BY g.privilege_type), '')
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
          LEFT JOIN information_schema.role_table_grants g
                 ON g.table_schema = n.nspname AND g.table_name = c.relname
                AND g.grantee = 'hospitality_app'
         WHERE n.nspname = 'fulfillment'
           AND c.relname IN ('station_profile', 'routing_rule', 'routing_rule_set')
         GROUP BY c.relname ORDER BY c.relname;
    """)
    seen: dict[str, set[str]] = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        relname, privileges = line.split("\x1f")
        seen[f"fulfillment.{relname}"] = {p for p in privileges.split(",") if p}

    for table, expected in sorted(RUNTIME_SELECT_ONLY.items()):
        actual = seen.get(table)
        if actual is None:
            raise MigrationFailure(
                "RUNTIME_GRANT_UNREADABLE",
                f"{table} was not found in the catalog, so the claim that the application "
                f"role's privileges are unchanged could not be checked. Refusing to report "
                f"a grant this runner has not read.")
        if actual != expected:
            raise MigrationFailure(
                "RUNTIME_GRANT_WIDENED",
                f"hospitality_app now holds {','.join(sorted(actual)) or 'nothing'} on "
                f"{table}, and the provisioning pass exists precisely so that it should "
                f"still hold {','.join(sorted(expected))}. Seeding must not change what "
                f"the running service is allowed to do.")

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
        provisioning = is_provisioning(path)

        # Which identity a seed runs under is decided HERE, from the file's own name, and
        # the decision is checked before anything is applied. A provisioning seed that
        # reached beyond the configuration tables, or a content seed that reached into
        # them, is refused by name rather than by a permission error nobody can read.
        if provisioning:
            assert_provisioning_is_narrow(path)
        else:
            assert_content_is_unprivileged(path)

        print(f"applying {path.name} …"
              f"{'   [provisioning: migration identity]' if provisioning else ''}", flush=True)
        try:
            # Content goes in as the application role, so every seeded row passes the row
            # level security the service passes. Provisioning goes in as the migration
            # identity, because the two configuration tables are SELECT-only to the
            # application role by an M1 decision this runner must not undo.
            psql_file(dsn if provisioning else content_dsn, path)
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

    # AND THE RUNNING SERVICE CAN DO NO MORE THAN IT COULD BEFORE. Read from the catalog
    # after everything has been applied, because that is the only moment the claim is
    # about: a provisioning seed that widened a grant would otherwise leave the privilege
    # behind and nothing here would ever look.
    assert_runtime_grant_unchanged(dsn)

    print("PASS SEEDS_APPLIED")
    print(f"  newly applied : {len(pending)}")
    print(f"  total applied : {len(state) + len(pending)}")
    print(f"  runtime grant : hospitality_app still holds SELECT only on "
          f"{len(RUNTIME_SELECT_ONLY)} configuration table(s)")
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
