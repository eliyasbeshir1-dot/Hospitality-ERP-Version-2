#!/usr/bin/env python3
"""Does the built artifact contain what production needs, and nothing that can reset it?

FR-OPS-019, FR-CFG-007B.

TWO CHECKS, AND THEY FAIL FOR OPPOSITE REASONS.

  completeness  every entry point tools/artifact.py advertises EXECUTES from inside the
                built tree, with the repository made unreachable. A file that is present
                and does not run is the failure FR-OPS-019 is about — it is easy to notice
                a missing file and hard to notice one that needed something the build left
                behind.

  prohibition   nothing in the tree is a way to reset or reseed production, and neither is
                anything in the database. FR-CFG-007B asks for both halves and this does
                both, because a route that has been removed from the image while the
                function it called is still installed has not been removed.

WHY "WITH THE REPOSITORY MADE UNREACHABLE" IS THE WHOLE POINT. FR-OPS-019 says the artifact
must work "without host development mounts", and the way that guarantee usually dies is not
a mount — it is a relative import, a PYTHONPATH inherited from a shell, a node_modules one
directory up. So the probes run with cwd inside the artifact, PYTHONPATH cleared, and
NODE_PATH cleared. If an entry point still resolves, it resolved from inside.

Usage:
    python3 tools/verify_artifact.py --artifact <dir> [--dsn <dsn>]
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from artifact import (                                     # noqa: E402
    ENTRY_POINTS, EXCLUDED_ALWAYS, RESET_ALLOWED, RESET_PATTERNS,
)
from console import use_utf8_output                        # noqa: E402

use_utf8_output()

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def sealed_env() -> dict:
    """The environment an artifact runs in: nothing pointing back at a checkout.

    PYTHONPATH and NODE_PATH are cleared rather than merely not set, because the SHELL
    that runs this may have them, and inheriting one is exactly the host development mount
    the requirement forbids. PYTHONDONTWRITEBYTECODE keeps the probe from leaving __pycache__
    inside the artifact it is checking, which would make the tree differ from the one that
    was built.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("NODE_PATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def interpreter(runner: str) -> list[str]:
    if runner == "python":
        return [sys.executable]
    for candidate in ("node", "node.exe"):
        probe = subprocess.run([candidate, "--version"], capture_output=True, text=True)
        if probe.returncode == 0:
            return [candidate]
    raise RuntimeError("no runnable node on PATH; the artifact's API cannot be probed")


# ===========================================================================
# 1. Completeness — every advertised entry point runs from inside
# ===========================================================================

def section_completeness(root: Path) -> None:
    print("\n--- 1. FR-OPS-019: every advertised entry point executes from inside ---")

    for entry in ENTRY_POINTS:
        target = root / entry.path
        if not target.exists():
            record(f"{entry.name} ({entry.service}) is present", False,
                   f"{entry.path} is advertised and is not in the artifact")
            continue

        if entry.probe == "require":
            # Loading the module resolves fastify, pg, every route and every surface.
            # server.ts guards its start with `if (require.main === module)`, so this
            # walks the whole graph and returns rather than binding a port.
            command = interpreter("node") + [
                "-e", f"require({str(target).replace(chr(92), '/')!r}); "
                      "process.stdout.write('loaded')"]
        else:
            command = interpreter(entry.runner) + [str(target), "--help"]

        proc = subprocess.run(command, cwd=str(root), env=sealed_env(),
                              capture_output=True, text=True, timeout=120)
        ok = proc.returncode == 0
        detail = entry.why if ok else (
            f"exit {proc.returncode}\n"
            f"{(proc.stderr or proc.stdout).strip()[:400]}")
        record(f"{entry.name} ({entry.service}) executes from inside the artifact",
               ok, detail)

    # AND THE FIVE SERVICE KINDS ARE ACCOUNTED FOR, each either shipping an entry point or
    # saying why it does not. A service with neither is one nobody has thought about.
    covered = {e.service for e in ENTRY_POINTS}
    explained = {
        "sync_worker": "started in process by the API; api/src/server.ts is the only file "
                       "in api/src with a listen call",
        "realtime_gateway": "started in process by the API, for the same reason",
        "database": "PostgreSQL itself, which the artifact connects to rather than "
                    "contains; the client it needs is checked below",
    }
    for kind in ("local_api", "database", "sync_worker", "realtime_gateway", "print_agent"):
        record(f"the {kind} service is accounted for",
               kind in covered or kind in explained,
               explained.get(kind, f"ships {sorted(e.name for e in ENTRY_POINTS if e.service == kind)}"))

    # THE DATABASE CLIENT. FR-OPS-019 names it explicitly and it is the one dependency the
    # artifact cannot carry as a file: psql is a binary belonging to the PostgreSQL
    # distribution. What CAN be checked is that the artifact's own migration path reaches
    # one, which is what a deployment actually depends on.
    probe = subprocess.run(["psql", "--version"], capture_output=True, text=True)
    record("a database client is reachable from the artifact's environment",
           probe.returncode == 0,
           (probe.stdout or probe.stderr).strip()[:120] + "\n"
           "psql belongs to the PostgreSQL distribution rather than to this repository. "
           "The artifact carries tools/migrate.py, which needs one; the image must provide "
           "it, and deploy/Dockerfile installs it.")


# ===========================================================================
# 2. Prohibition — nothing here can reset or reseed production
# ===========================================================================

def section_prohibition(root: Path) -> None:
    print("\n--- 2. FR-CFG-007B: no demo-reset route, job or script ---")

    for excluded, why in EXCLUDED_ALWAYS:
        present = (root / excluded).exists()
        record(f"the artifact contains no {excluded}/", not present, why)

    allowed = {name for name, _why in RESET_ALLOWED}
    hits: list[str] = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        # node_modules is third-party and enormous; scanning it would report on other
        # people's code and say nothing about this artifact's own behaviour. Named rather
        # than silently skipped.
        if "node_modules" in path.parts:
            continue
        if path.suffix.lower() not in (".js", ".mjs", ".cjs", ".py", ".sql", ".sh", ".json"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for pattern, meaning in RESET_PATTERNS:
            for match in re.finditer(pattern, text):
                line = text[:match.start()].count("\n") + 1
                context = text.splitlines()[line - 1] if line <= len(text.splitlines()) else ""
                if any(name in context for name in allowed):
                    continue
                hits.append(f"{path.relative_to(root)}:{line} — {meaning}: {context.strip()[:90]}")

    record("no file in the artifact is a way to reset or reseed it",
           not hits,
           f"{scanned} runtime file(s) scanned; node_modules excluded as third-party.\n"
           + ("\n".join(hits[:8]) if hits else
              "the one allowed match is a projection rebuild, which deletes and replays "
              "projections from append-only ledgers it does not touch — it destroys no trade"))


def section_database(dsn: str) -> None:
    print("\n--- 3. FR-CFG-007B: and neither does the database ---")
    sys.path.insert(0, str(REPO / "tests" / "m1a"))
    from pg import run                                     # noqa: E402

    allowed = "','".join(name for name, _why in RESET_ALLOWED)
    result = run(dsn, f"""
        SELECT coalesce(string_agg(n.nspname || '.' || p.proname, ', '), 'NONE')
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
           AND (p.proname ~* '(demo_reset|reset_demo|factory_reset|wipe_|seed_demo)'
                OR p.prosrc ~* 'TRUNCATE\\s+TABLE')
           AND p.proname NOT IN ('{allowed}');""")
    found = (result.scalar or "").strip()
    record("no installed function is a way to reset or reseed the database",
           result.ok and found == "NONE",
           f"found: {found}\n"
           "a route removed from the image while the function it called is still installed "
           "has not been removed, which is why FR-CFG-007B asks for both halves")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--dsn", default=os.environ.get("M1A_ADMIN_DSN"))
    args = parser.parse_args()

    root = Path(args.artifact)
    if not root.exists():
        print(f"FAIL ARTIFACT_ABSENT: {root} does not exist. Build it first:")
        print(f"  python3 tools/artifact.py --out <dir>")
        return 1

    print("=" * 74)
    print("  The built production artifact — complete, and unable to reset production")
    print("=" * 74)

    section_completeness(root)
    section_prohibition(root)
    if args.dsn:
        section_database(args.dsn)
    else:
        record("the database half of FR-CFG-007B was checked", False,
               "no --dsn and no M1A_ADMIN_DSN. The requirement asks for the image AND the "
               "database, and half of it is not it")

    failed = [name for name, ok, _d in results if not ok]
    print("\n" + "=" * 74)
    print(f"  checks run : {len(results)}")
    print(f"  failed     : {len(failed)}")
    if failed:
        print("\nFAIL ARTIFACT_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS ARTIFACT_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
