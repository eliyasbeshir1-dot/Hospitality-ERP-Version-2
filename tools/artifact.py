#!/usr/bin/env python3
"""What a production artifact contains, and what it may not.

FR-OPS-019, FR-CFG-007B, FR-TST-018.

THIS FILE IS THE ONLY DECLARATION. The builder copies what it lists, the Dockerfile is
generated from it, the completeness check runs what it names, and the prohibition scan
reads what it forbids. Four things derived from one, because the alternative is a manifest
in a build script, a COPY list in a Dockerfile and a checklist in a test — three places to
say the same thing and two of them going stale, which is the defect shape this repository
has met in the CI matrix, the README and the schema catalog.

WHAT "ADVERTISED" MEANS, since FR-OPS-019 turns on it. The artifact advertises its entry
points HERE. The check then RUNS every one of them from inside the built tree. An entry
point that is declared and cannot execute is the failure the requirement is about — not a
missing file, which is easy to notice, but a file that is present and does not work because
it needed something the build left behind.

AND WHY THE SEEDS ARE NOT IN IT. Every seed in this repository builds the demonstration
floor: two tenants, an Ethiopian menu, a Sarbet manager, a Kazanchis node. FR-CFG-007B says
the built production image must contain no demo-reset route, job or script, and a loader
that creates demonstration tenants is precisely that — a way to put demonstration data into
production, which is worse than a way to reset it. So the artifact ships MIGRATIONS, which
are the schema, and no seeds at all. A production tenant is provisioned, not seeded.

That leaves a real gap and it is named rather than hidden: nothing in the artifact creates
a first tenant. Provisioning is M6-E's, and planning/M6_FINDINGS.md carries it.
"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class EntryPoint:
    """Something production runs, and how the check proves it runs.

    `probe` is deliberately not the real invocation. Starting the API binds a port and
    waits; running a migration needs a database. What every entry point CAN do without a
    world around it is RESOLVE ITS IMPORTS, and that is the thing a bad build breaks.

      'require'  load the module without running it. api/src/server.ts guards its start
                 with `if (require.main === module)`, so requiring it walks the whole
                 graph — fastify, pg, every route, every surface — and returns. This is
                 the strongest probe available and it needs no argument the source does
                 not already have.
      'help'     run it with --help. A Python entry point that cannot import what it
                 needs fails before it prints usage.
    """

    name: str
    service: str                    # one of edge.node_service_kind's five, or 'operations'
    path: str                       # relative to the artifact root
    runner: str                     # 'node' or 'python'
    probe: str                      # 'require' or 'help'
    why: str


# ---------------------------------------------------------------------------
# 1. WHAT PRODUCTION RUNS
# ---------------------------------------------------------------------------
#
# The five service kinds are edge.node_service_kind's, not a list invented here:
# local_api, database, sync_worker, realtime_gateway, print_agent. Two of them have no
# entry point of their own and that is a fact about the design rather than an omission —
# the sync worker and the realtime gateway are started IN PROCESS by the API, which is why
# api/src/server.ts is the only file in api/src with a listen call. `database` is
# PostgreSQL itself plus the client below.

ENTRY_POINTS: tuple[EntryPoint, ...] = (
    EntryPoint(
        name="api",
        service="local_api",
        path="dist/server.js",
        runner="node",
        probe="require",
        why="The API, the four surfaces it serves, and — on a node deployment — the sync "
            "worker and realtime gateway it starts in process.",
    ),
    EntryPoint(
        name="print-agent",
        service="print_agent",
        path="print/agent.py",
        runner="python",
        probe="help",
        why="FR-EDG-002A's fifth service. Talks to the printer.",
    ),
    EntryPoint(
        name="print-queue-runner",
        service="print_agent",
        path="print/queue_runner.py",
        runner="python",
        probe="help",
        why="Claims and retries print jobs. Separate from the agent because a lease that "
            "expires must not depend on the process that took it still being alive.",
    ),
    EntryPoint(
        name="migrate",
        service="operations",
        path="tools/migrate.py",
        runner="python",
        probe="help",
        why="Applies the schema. In the artifact because a deployment that cannot migrate "
            "is a deployment that cannot start, and reaching for a checkout to do it is "
            "the host development mount FR-OPS-019 forbids.",
    ),
)

# ---------------------------------------------------------------------------
# 2. WHAT IS COPIED IN
# ---------------------------------------------------------------------------
#
# Directories are copied whole; a file is copied alone. Anything not listed is not in the
# artifact, which is the point — an allowlist rather than an exclude list, because an
# exclude list ships whatever nobody thought to exclude.

# EACH ENTRY NAMES ITS ORIGIN, and there are two. `repo` is a file this repository holds;
# `build` is compiled output, which the repository must NEVER hold — tools/verify_m1.py
# treats dist/, node_modules/ and build/ inside the repository as forbidden surface and
# checks the FILESYSTEM rather than the Git index, so a build in the tree fails the gate
# even though .gitignore would keep it out of commits. api/build.sh compiles into a
# workspace outside the repository for exactly that reason.
#
# An artifact assembled from one origin would therefore be either missing the server or
# built in a place the repository forbids. Saying which half comes from where is what makes
# "the artifact needs no host development mount" checkable rather than aspirational: the
# BUILD half is what a container's build stage produces, and the REPO half is what it
# copies in.
INCLUDED_TREES: tuple[tuple[str, str, str], ...] = (
    ("build", "dist", "dist"),
    ("build", "node_modules", "node_modules"),
    ("repo", "print", "print"),
    ("repo", "migrations", "migrations"),
)

INCLUDED_FILES: tuple[tuple[str, str, str], ...] = (
    ("repo", "tools/migrate.py", "tools/migrate.py"),
    ("repo", "tools/console.py", "tools/console.py"),
    ("repo", "api/package.json", "package.json"),
)

# WHAT MAY NOT BE COPIED IN, AND THE SCAN THAT PROVES IT WAS NOT. Named separately from
# "not in the allowlist" because these are the ones a future change would be TEMPTED to
# add — a seed loader to bootstrap an environment, a test helper to debug a deployment.
EXCLUDED_ALWAYS: tuple[tuple[str, str], ...] = (
    ("seeds", "every seed in this repository builds the DEMONSTRATION floor. A loader "
              "that creates demonstration tenants in production is what FR-CFG-007B "
              "forbids, and is worse than a way to reset them"),
    ("tests", "a test harness in production is a set of routes and fixtures nobody "
              "reviewed as product, and several of them plant defects on purpose"),
    ("docs", "not runtime"),
    ("planning", "not runtime"),
    ("evidence", "not runtime"),
)

# ---------------------------------------------------------------------------
# 3. WHAT MAY NOT EXIST ANYWHERE INSIDE IT
# ---------------------------------------------------------------------------
#
# FR-CFG-007B: "Scan of the built production image and database proves no demo-reset route,
# job or script is present." Two halves, and this is the artifact half.
#
# The patterns are deliberately broader than "a route called /reset" and each one is a
# thing somebody would plausibly write. A match is a FAILURE rather than a warning: there
# is no legitimate reason for a production artifact to contain a way to empty itself.

RESET_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?i)\bdemo[_-]?reset\b", "a demonstration reset by name"),
    (r"(?i)\breset[_-]?demo\b", "the same thing said the other way round"),
    (r"(?i)\bfactory[_-]?reset\b", "a factory reset"),
    (r"(?i)\bwipe[_-]?(database|data|tenant|outlet)\b", "a wipe by name"),
    (r"(?i)\bseed[_-]?demo\b", "a demonstration seeder"),
    (r"(?i)TRUNCATE\s+TABLE\b", "an unqualified truncate"),
    (r"(?i)\bDROP\s+DATABASE\b", "dropping a database from inside the thing running on it"),
)

# THE ONE EXCEPTION, AND IT IS JUSTIFIED RATHER THAN ASSUMED. A projection rebuild deletes
# and replays projections; it is not a data reset, because the ledgers it replays FROM are
# append-only and untouched. It is allowed by name, in one place, with the reason attached
# — an allowlist entry without a reason is an allowlist entry nobody can review.
RESET_ALLOWED: tuple[tuple[str, str], ...] = (
    ("rebuild_projections",
     "deletes and replays PROJECTIONS from append-only ledgers it does not touch. The "
     "distinction is the whole of M3-D's rule: nothing durable holds a foreign key into a "
     "projection, precisely so a rebuild is safe. It destroys no trade."),
)


def artifact_root(base: Path) -> Path:
    return base / "hospitality-artifact"


def build(base: Path, workspace: Path, *, quiet: bool = False) -> Path:
    """Produce the artifact tree from the repository and the build workspace.

    Copies exactly what the manifest lists and nothing else. Removes any previous tree
    first: an artifact built on top of an older one contains whatever the older one had,
    which is how a file removed from the manifest keeps shipping.
    """
    origins = {"repo": REPO, "build": workspace}
    root = artifact_root(base)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    for origin, source, target in INCLUDED_TREES:
        src = origins[origin] / source
        if not src.exists():
            raise FileNotFoundError(
                f"{origin}:{source} is in the artifact manifest and is not there. "
                + ("Run api/build.sh first — compiled output lives outside the "
                   "repository by design." if origin == "build" else ""))
        shutil.copytree(src, root / target, symlinks=False)
        if not quiet:
            print(f"  tree  {origin}:{source} -> {target}")

    for origin, source, target in INCLUDED_FILES:
        src = origins[origin] / source
        if not src.exists():
            raise FileNotFoundError(f"{origin}:{source} is in the manifest and is missing")
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, root / target)
        if not quiet:
            print(f"  file  {origin}:{source} -> {target}")

    return root


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="directory to build the artifact in")
    parser.add_argument("--workspace", default=os.environ.get("M1D_WORKSPACE"),
                        help="where api/build.sh compiled to (default: $M1D_WORKSPACE)")
    args = parser.parse_args()

    if not args.workspace:
        print("FAIL ARTIFACT_WORKSPACE_UNKNOWN: pass --workspace or set M1D_WORKSPACE.")
        print("  Compiled output lives outside the repository by design — see api/build.sh.")
        return 1

    root = build(Path(args.out), Path(args.workspace))
    print(f"\nartifact built at {root}")
    print(f"  entry points : {len(ENTRY_POINTS)}")
    print(f"  trees        : {len(INCLUDED_TREES)}")
    print(f"  files        : {len(INCLUDED_FILES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
