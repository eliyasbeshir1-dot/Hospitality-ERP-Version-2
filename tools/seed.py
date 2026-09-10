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
#
# WHY EACH OF THESE IS CONFIGURATION RATHER THAN CONTENT. The distinction is not "the app
# role cannot write it" — that is the symptom. It is that each row below is decided when an
# outlet is INSTALLED and is then read, not written, by the running service. Nothing here
# is produced by trade. A reader should be able to check that claim table by table:
#
#   fulfillment.station_profile     which stations exist in this kitchen
#   fulfillment.routing_rule        which of them a dish goes to
#   fulfillment.routing_rule_set    the version of that routing, as a set
#   billing.tip_setting             whether this outlet offers a tip at all
#   billing.tip_suggestion          the percentages it offers, if it does
#   payments.payment_adapter        which payment providers this outlet accepts
#   edge.deployment_profile         whether this outlet may run cloud-only, and where
#   edge.plain_language             what a restriction and a sync state are called here
#   edge.outlet_hostname            the public name this outlet's QR carries, answered
#                                   two ways
#   edge.supported_network          the resolver it advertises and whether it blocks DoH
#
# The two M5a added meet the same test, and the first of them is the clearest case in the
# set: edge.deployment_profile decides whether an outlet is production and therefore
# whether FR-EDG-001 compels a continuity node. A screen that could write it could change
# the answer to "is this production", which is not a question trade should be able to
# answer. edge.plain_language is the wording a restriction is explained in — installed,
# revisited by a manager, read by every surface that has to tell somebody why a button did
# nothing.
#
# billing.service_charge_setting was approved for this set and is deliberately NOT in it.
# It requires a configuration_version_id, and a floor with no service charge is correctly
# represented by having no row at all — billing.issue_bill() reads its absence as "none",
# which the demonstration floor's first bill proved before this seed existed. Admitting a
# table to the privileged pass that nothing writes would widen the boundary for nothing,
# which is the opposite of what "narrow" is protecting. Eight, not nine.
#
# THE TWO M5b ADDS PASS THE SAME TEST AND edge.node_certificate DELIBERATELY FAILS IT.
# A person chooses what an outlet is called and a person documents which resolver it hands
# out; both are revisited, and neither is produced by trade. A CERTIFICATE IS NOT DECIDED
# BY ANYBODY — a node generates a key, submits a CSR and a CA answers, and the row records
# that exchange. It is the same shape as a bill, which is SELECT-only to the app role
# because a FUNCTION writes it rather than because it is configuration. 0055 added
# edge.request_certificate() so the seed goes through the state machine instead of around
# it.
#
# edge.lease_policy joins them at M5b for the same test: FR-EDG-023's 5/10/20/3 schedule
# is how long an OUTLET waits before it decides the cloud is gone, and an operator with a
# slow link should be able to change it. GJ-09 found the table empty on a floor with two
# nodes — the schedule existed only as four DEFAULT clauses nobody had inserted against.
# Eleven tables, not ten and not twelve.
#
# Each is a decision an installer makes and a manager revisits; none is a bill, a payment,
# an order or a ticket. The counter-example is the test: a bill IS produced by trade, and
# billing.bill is SELECT-only to the app role too — because a FUNCTION writes it, not
# because it is configuration. Membership here is decided by "who decides this row", never
# by "which grant is in the way".
PROVISIONABLE_TABLES = frozenset({
    "fulfillment.station_profile",
    "fulfillment.routing_rule",
    "fulfillment.routing_rule_set",
    "billing.tip_setting",
    "billing.tip_suggestion",
    "payments.payment_adapter",
    "edge.deployment_profile",
    "edge.plain_language",
    "edge.outlet_hostname",
    "edge.supported_network",
    "edge.lease_policy",
})

# THE SET IS NAMED, AND THE NAMING IS CHECKED. Growing PROVISIONABLE_TABLES without saying
# so here fails, so an eighth table cannot arrive as a one-word diff: somebody has to write
# it down in two places and mean it. This is the condition attached to growing the set
# beyond the three tables it held at OP-A.
PROVISIONABLE_TABLES_DECLARED = (
    "billing.tip_setting",
    "billing.tip_suggestion",
    "edge.deployment_profile",
    "edge.lease_policy",
    "edge.outlet_hostname",
    "edge.plain_language",
    "edge.supported_network",
    "fulfillment.routing_rule",
    "fulfillment.routing_rule_set",
    "fulfillment.station_profile",
    "payments.payment_adapter",
)

# The grant that must still hold after seeding. Asserted rather than assumed: a later
# provisioning seed could issue a GRANT and nothing else here would notice.
RUNTIME_SELECT_ONLY = {table: {"SELECT"} for table in PROVISIONABLE_TABLES_DECLARED}


def assert_the_provisionable_set_is_declared() -> None:
    """The set and its written-down twin agree, or seeding stops.

    Two statements of one fact, deliberately, because this is the one place where the
    cost of drift is a privilege boundary rather than a stale document.
    """
    if PROVISIONABLE_TABLES != frozenset(PROVISIONABLE_TABLES_DECLARED):
        difference = PROVISIONABLE_TABLES.symmetric_difference(
            PROVISIONABLE_TABLES_DECLARED)
        raise MigrationFailure(
            "PROVISIONABLE_SET_UNDECLARED",
            f"PROVISIONABLE_TABLES and PROVISIONABLE_TABLES_DECLARED differ on "
            f"{', '.join(sorted(difference))}. The provisioning pass may write "
            f"{len(PROVISIONABLE_TABLES_DECLARED)} named tables; a table added to one "
            f"list and not the other is a privilege boundary moved without anybody "
            f"saying so.")

"""Which FUNCTIONS a provisioning seed may call, and why there is a second list at all.

THE HOLE THIS CLOSES, FOUND BY THE FIRST SEED THAT CALLED ONE.

`written_tables()` below reads INSERT, UPDATE and DELETE statements. A write performed
INSIDE a function is none of those: the seed's text names a function and no table at all,
so the narrowness check saw an empty set and passed. A provisioning seed could therefore
call any SECURITY DEFINER function in the database and write anything it liked, under the
migration identity, and the guard whose whole job is to stop that would have reported
nothing — not a refusal, not a warning, an empty set and a pass.

Nothing exploited it. seeds/0008 is the first provisioning seed to call a function at all,
which is why it had never come up: for as long as every such seed wrote its rows as
literal statements, the statement scanner and the truth were the same thing.

So calls are allowlisted on the same terms as tables. A function here is one whose writes
have been read and found to be within the boundary the table set already declares:

  pos.install_registries_for   writes pos.confirmation_requirement and
                               identity.governed_action — the confirmation grades and
                               governed actions a tenant needs. Both are configuration by
                               the same test the table set uses: decided when a tenant is
                               installed, then read and never written by the running
                               service. Idempotent, and it takes a tenant id rather than
                               a row, so a seed cannot use it to smuggle content in.

The tables it writes are deliberately NOT added to PROVISIONABLE_TABLES. That set names
what a seed may write DIRECTLY, and no seed writes those two directly; admitting a table
no seed writes would widen the boundary for nothing, which is the reasoning that kept
billing.service_charge_setting out of it.
"""
PROVISIONABLE_FUNCTIONS = frozenset({
    "pos.install_registries_for",
    # Writes edge.node, edge.node_service and edge.node_admin_action. Vetted rather than
    # written as statements because the whole point of the function is that a node and its
    # five services arrive together — FR-EDG-002A's "exactly five" is enforced inside it,
    # and a seed that INSERTed the rows itself could write four.
    "edge.register_node",
    # Writes edge.node_certificate, which is NOT in PROVISIONABLE_TABLES and should not be
    # — see the note above the set. These two are the state machine's entrance and its
    # exit, and going through them is what makes the seeded floor demonstrate a state that
    # code actually produces.
    # FR-EDG-023 and FR-EDG-024's rows for the outlets that already existed. Writes
    # edge.authority and edge.node_admin_action; grant_first_authority() is the ONLY way to
    # take a first sequence, and every later one goes through claim_authority() and its
    # four proofs. There is no node to fence when an outlet has never had one, which is why
    # the asymmetry exists and why only this half is provisionable.
    "edge.grant_first_authority",
    "edge.request_certificate",
    "edge.record_certificate_issued",
    "edge.verify_and_install_certificate",
    # Writes identity.governed_action, and only the one row M5b introduces. Vetted rather
    # than written as a statement because the registry is SELECT-only to the application
    # role by design: which acts need stronger authentication is not a screen's business.
    "identity.install_governed_actions_for",
})

_COMMENT = re.compile(r"--[^\n]*")
_WRITE_TARGET = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([a-z_]+\.[a-z_]+)", re.IGNORECASE)
# A schema-qualified call. Unqualified builtins (set_config, now) do not match and are not
# the exposure: they write nothing. A qualified call is the shape that can reach a table.
#
# RELATION REFERENCES ARE REMOVED FIRST, and the reason is a defect this pattern had for
# the length of one test run. `INSERT INTO menu.sellable_item (id) VALUES (…)` puts a
# schema-qualified name immediately before an open bracket, so a bare "name followed by a
# bracket" reader calls the column list a function call and refuses the seed by the wrong
# name. NC-OPA-007 caught it within minutes — it plants exactly that statement and requires
# PROVISIONING_SEED_TOO_BROAD, and got PROVISIONING_SEED_CALLS_UNVETTED_FUNCTION instead.
# A control from an earlier gate failing on a new checker is the control working.
_RELATION_REFERENCE = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|FROM|JOIN)\s+[a-z_]+\.[a-z_]+", re.IGNORECASE)
_CALLED_FUNCTION = re.compile(r"\b([a-z_]+\.[a-z_]+)\s*\(", re.IGNORECASE)
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


def called_functions(path: Path) -> set[str]:
    """Every schema-qualified function a seed calls.

    Comments go first, then relation references: a table named in an INSERT, an UPDATE,
    a DELETE, a FROM or a JOIN is a table however closely a bracket follows it, and the
    table check is what reads those.
    """
    text = _COMMENT.sub("", path.read_text(encoding="utf-8"))
    text = _RELATION_REFERENCE.sub(" ", text)
    return {match.group(1).lower() for match in _CALLED_FUNCTION.finditer(text)}


def assert_provisioning_is_narrow(path: Path) -> None:
    """A provisioning seed writes the configuration tables and nothing else.

    Two questions, because a seed can reach a table two ways. WHICH TABLES it writes is
    read from its statements; WHICH FUNCTIONS it calls is read separately, because a write
    performed inside a function appears in neither an INSERT nor an UPDATE nor a DELETE and
    was invisible to the first question until seeds/0008 became the first provisioning seed
    to call one.
    """
    # THE TABLE CHECK RUNS FIRST, and the order is load-bearing rather than incidental.
    # A seed that both writes a forbidden table and calls an unvetted function has done
    # the more concrete wrong thing, and PROVISIONING_SEED_TOO_BROAD is the signature that
    # names it — a signature four gates of controls already assert on. A new check that
    # answered first would rename an existing refusal.
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

    calls = sorted(called_functions(path) - PROVISIONABLE_FUNCTIONS)
    if calls:
        raise MigrationFailure(
            "PROVISIONING_SEED_CALLS_UNVETTED_FUNCTION",
            f"{path.name} calls {', '.join(calls)} under the migration identity. A "
            f"function can write tables this seed never names, so the check above cannot "
            f"see through it: the call has to be vetted instead. The provisioning pass may "
            f"call {', '.join(sorted(PROVISIONABLE_FUNCTIONS))} and nothing else. Add it to "
            f"PROVISIONABLE_FUNCTIONS with a note saying what it writes, or write the rows "
            f"as statements so the table check can read them.")


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
    # Derived from RUNTIME_SELECT_ONLY rather than restating its members. The first
    # version of this named three tables in one schema in a SQL literal, which would have
    # kept passing while saying nothing about the four added later in two other schemas —
    # an assertion that cannot fail for the rows you just wrote.
    wanted = ", ".join(
        f"('{table.split('.')[0]}','{table.split('.')[1]}')"
        for table in sorted(RUNTIME_SELECT_ONLY))
    out = psql(dsn, f"""
        SELECT n.nspname || '.' || c.relname,
               coalesce(string_agg(DISTINCT g.privilege_type, ',' ORDER BY g.privilege_type), '')
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
          LEFT JOIN information_schema.role_table_grants g
                 ON g.table_schema = n.nspname AND g.table_name = c.relname
                AND g.grantee = 'hospitality_app'
         WHERE (n.nspname, c.relname) IN ({wanted})
         GROUP BY 1 ORDER BY 1;
    """)
    seen: dict[str, set[str]] = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        table, privileges = line.split("\x1f")
        seen[table] = {p for p in privileges.split(",") if p}

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
    # Before anything is applied: the privileged set is what this file says it is.
    assert_the_provisionable_set_is_declared()
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
