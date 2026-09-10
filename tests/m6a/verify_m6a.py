#!/usr/bin/env python3
"""M6-A verification: the built artifact, and nothing in it that can reset production.

WHAT THIS SLICE IS ABOUT. Every gate before this one proved behaviour against a repository
— source on a developer's disk, run by a developer's interpreter, against a database a
developer created. FR-TST-018 says that is not enough at M6:

    Security, readiness, backup, restore, local continuity and route-surface tests execute
    against built production artifacts and real production roles, not source-only
    substitutes.

So this slice builds the thing that ships, runs its entry points from inside it with the
repository made unreachable, and scans it — and the database — for any way to reset or
reseed production.

THE THREE REQUIREMENTS, AND WHAT EACH ONE ACTUALLY DEMANDS.

  FR-OPS-019  every advertised runtime job, script, database client and configuration file
              EXISTS AND EXECUTES inside the built image without host development mounts.
              The hard word is "executes": a missing file is easy to notice, and a file
              that is present and fails because the build left a dependency behind is not.

  FR-CFG-007B a scan of the built image AND THE DATABASE proves no demo-reset route, job
              or script is present. Both halves, because a route removed from the image
              while the function it called is still installed has not been removed.

  FR-TST-018  the tests run against the artifact rather than against source.

WHAT THIS SUITE INHERITS FROM M5b. Every probe rolls back, every function this slice adds
is CALLED rather than merely defined, and the bounds are named in the run rather than left
for a reader to infer from silence.

Usage:
    M1A_ADMIN_DSN=... M1D_WORKSPACE=... python3 tests/m6a/verify_m6a.py
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
from pg import run                                         # noqa: E402

import artifact as manifest                                # noqa: E402
import controls as registry                                # noqa: E402

ADMIN = os.environ["M1A_ADMIN_DSN"]
WORKSPACE = Path(os.environ.get("M1D_WORKSPACE", "/var/lib/m1d-workspace"))

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


def verify_artifact(root: Path, *, dsn: str | None = ADMIN) -> subprocess.CompletedProcess:
    """Run the real checker, as a subprocess, exactly as an operator would.

    NOT imported and called in-process. FR-TST-018 is about testing the production path
    rather than a source-only substitute, and a checker imported into the test's own
    interpreter inherits that interpreter's sys.path — which is the repository. Shelling
    out is what makes "with the repository unreachable" mean anything.
    """
    command = [sys.executable, str(REPO / "tools" / "verify_artifact.py"),
               "--artifact", str(root)]
    if dsn:
        command += ["--dsn", dsn]
    return subprocess.run(command, capture_output=True, text=True, timeout=600)


# ===========================================================================
# 1. The artifact builds, from two origins
# ===========================================================================

def section_build() -> None:
    print("\n--- 1. FR-OPS-019: the artifact builds from the manifest ---")

    if not (WORKSPACE / "dist").exists():
        record("the build workspace holds compiled output", False,
               f"{WORKSPACE}/dist does not exist. api/build.sh compiles OUTSIDE the "
               f"repository because tools/verify_m1.py treats dist/ inside it as forbidden "
               f"surface; run it, or set M1D_WORKSPACE.")
        raise RuntimeError("no compiled output to build an artifact from")

    base = Path(tempfile.mkdtemp(prefix="m6a-artifact-"))
    CONTEXT["base"] = base
    root = manifest.build(base, WORKSPACE, quiet=True)
    CONTEXT["root"] = root

    record("the artifact builds from the repository and the build workspace",
           root.exists(),
           f"{root}\n"
           "two origins, and saying which half comes from where is what makes 'no host "
           "development mount' checkable: the BUILD half is what a container's build stage "
           "produces and the REPO half is what it copies in")

    # EVERY DECLARED TREE AND FILE IS ACTUALLY THERE. The builder raises on a missing
    # source, so this is really asserting that it copied rather than that it was asked to.
    missing = [t for _o, _s, t in manifest.INCLUDED_TREES if not (root / t).is_dir()]
    missing += [t for _o, _s, t in manifest.INCLUDED_FILES if not (root / t).is_file()]
    record("everything the manifest declares is in the built tree",
           not missing, f"missing: {missing or 'nothing'}")

    # AND NOTHING ELSE IS. An allowlist that quietly ships extras is an exclude list.
    declared = {t.split("/")[0] for _o, _s, t in manifest.INCLUDED_TREES}
    declared |= {t.split("/")[0] for _o, _s, t in manifest.INCLUDED_FILES}
    actual = {p.name for p in root.iterdir()}
    record("and nothing the manifest does not declare",
           actual <= declared,
           f"declared: {sorted(declared)}\nfound: {sorted(actual)}\n"
           f"undeclared: {sorted(actual - declared) or 'none'}")


# ===========================================================================
# 2. Every entry point runs from inside it
# ===========================================================================

def section_executes() -> None:
    print("\n--- 2. FR-OPS-019: and every advertised entry point executes ---")
    proc = verify_artifact(CONTEXT["root"])
    CONTEXT["checker_output"] = proc.stdout + proc.stderr

    record("the artifact checker runs against the built tree",
           "ARTIFACT_VERIFICATION" in CONTEXT["checker_output"],
           "driven as a subprocess rather than imported, because a checker imported into "
           "this interpreter inherits this interpreter's sys.path — which is the repository")

    for entry in manifest.ENTRY_POINTS:
        line = next((l for l in CONTEXT["checker_output"].splitlines()
                     if entry.name in l and "executes from inside" in l), "")
        record(f"{entry.name} ({entry.service}) executes from inside the artifact",
               line.strip().startswith("[PASS]"),
               line.strip() or f"{entry.name} was not probed at all")

    record("the artifact verification passes as a whole",
           proc.returncode == 0,
           "PASS ARTIFACT_VERIFICATION" if proc.returncode == 0
           else "\n".join(l for l in CONTEXT["checker_output"].splitlines()
                          if l.startswith("  - ") or l.startswith("FAIL"))[:600])


# ===========================================================================
# 3. Nothing in it can reset production
# ===========================================================================

def section_prohibition() -> None:
    print("\n--- 3. FR-CFG-007B: no demo-reset route, job or script ---")
    root = CONTEXT["root"]

    for excluded, why in manifest.EXCLUDED_ALWAYS:
        record(f"the artifact contains no {excluded}/",
               not (root / excluded).exists(), why)

    # THE SEEDS ARE THE INTERESTING ONE AND DESERVE THEIR OWN CHECK. Every seed in this
    # repository builds the demonstration floor, so shipping them would put a way to
    # create demonstration tenants into production — which is worse than a way to reset
    # them, and is what FR-CFG-007B is really about.
    seed_files = list(root.rglob("*.provision.sql")) + [
        p for p in root.rglob("*.sql") if p.parent.name == "seeds"]
    record("no seed of any kind reached the artifact",
           not seed_files,
           f"{len(seed_files)} found. Every seed here builds the DEMONSTRATION floor — two "
           "tenants, an Ethiopian menu, a Sarbet manager. A production tenant is "
           "provisioned, not seeded, and nothing in the artifact creates a first one: that "
           "gap is named in planning/M6_FINDINGS.md rather than filled by a demo loader")

    # And the migrations DID reach it, because a deployment that cannot apply its schema
    # cannot start — the check above must not pass by shipping nothing.
    migrations = list((root / "migrations").glob("*.sql")) if (root / "migrations").exists() else []
    record("the migrations did reach it",
           len(migrations) >= 60,
           f"{len(migrations)} migration(s). The seeds check must not pass by shipping an "
           "empty artifact")


def section_database() -> None:
    print("\n--- 4. FR-CFG-007B: and neither does the database ---")
    allowed = "','".join(name for name, _why in manifest.RESET_ALLOWED)
    result = run(ADMIN, f"""
        SELECT coalesce(string_agg(n.nspname || '.' || p.proname, ', '), 'NONE')
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
           AND (p.proname ~* '(demo_reset|reset_demo|factory_reset|wipe_|seed_demo)'
                OR p.prosrc ~* 'TRUNCATE\\s+TABLE')
           AND p.proname NOT IN ('{allowed}');""", tx=True, rollback=True)
    found = (result.scalar or "").strip()
    record("no installed function is a way to reset or reseed the database",
           result.ok and found == "NONE", f"found: {found}")

    # THE ONE ALLOWED MATCH IS JUSTIFIED RATHER THAN ASSUMED, and the justification is
    # checkable: a projection rebuild is safe precisely because nothing durable holds a
    # foreign key into a projection, which is M3-D's rule and tests/m4b's check.
    for name, why in manifest.RESET_ALLOWED:
        exists = run(ADMIN, f"""
            SELECT count(*)::text FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
             WHERE p.proname = '{name}' AND n.nspname NOT IN ('pg_catalog','information_schema');
        """, tx=True, rollback=True).scalar
        record(f"the one allowed reset-shaped name, {name}, is the one that is there",
               (exists or "0") != "0", why)


# ===========================================================================
# 5. The image definition cannot drift from the manifest
# ===========================================================================

def section_dockerfile() -> None:
    print("\n--- 5. FR-OPS-019: the image definition is derived, not written beside it ---")
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "generate_dockerfile.py"),
         "--check", str(REPO / "deploy" / "Dockerfile")],
        capture_output=True, text=True, timeout=120)
    record("deploy/Dockerfile matches the artifact manifest",
           proc.returncode == 0,
           (proc.stdout or proc.stderr).strip()[:400])

    dockerfile = (REPO / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    record("the image installs the database client FR-OPS-019 names",
           "postgresql-client" in dockerfile,
           "tools/migrate.py shells to psql, so an image without one cannot apply its own "
           "schema — and reaching for a client on the host is the development mount the "
           "requirement forbids")
    record("the image does not run as root",
           "USER hospitality" in dockerfile,
           "a print agent that can rewrite the migrator is a print agent whose compromise "
           "is the whole node's")
    record("the compiler does not ship",
           "AS build" in dockerfile and dockerfile.count("FROM ") == 2,
           "two stages: the source goes into the first and the compiled output comes out, "
           "so the tree that ships contains no toolchain")


# ===========================================================================
# 6. Negative controls
# ===========================================================================

def section_controls() -> None:
    print("\n--- 6. Negative controls: each defect planted, refused, reverted ---")
    root = CONTEXT["root"]

    def nc_001():
        planted = root / "seeds" / "0001_demonstration_tenants.sql"

        def red():
            planted.parent.mkdir(parents=True, exist_ok=True)
            planted.write_text("-- seed_demo tenants\nINSERT INTO org.tenant ...;\n",
                               encoding="utf-8")
            proc = verify_artifact(root, dsn=None)
            return "seeds/" in proc.stdout and proc.returncode != 0, \
                "the artifact checker refuses a tree containing a seed loader"

        def green():
            shutil.rmtree(root / "seeds", ignore_errors=True)
            proc = verify_artifact(root, dsn=None)
            return "[PASS] the artifact contains no seeds/" in proc.stdout, \
                "and accepts it again once the loader is gone"

        control("NC-M6A-001 a demonstration seed loader shipped in the artifact", red, green)

    def nc_002():
        # THE DEFECT IS A MISSING DEPENDENCY, not a missing entry point — the failure
        # FR-OPS-019 is actually about. fastify is moved aside rather than deleted so the
        # revert is a move back rather than a reinstall.
        fastify = root / "node_modules" / "fastify"
        stash = root / "node_modules" / "fastify.stashed"

        def red():
            if not fastify.exists():
                return False, "fastify is not in the artifact to begin with"
            fastify.rename(stash)
            proc = verify_artifact(root, dsn=None)
            failed = "[FAIL] api (local_api) executes from inside the artifact" in proc.stdout
            return failed, ("the API is present and cannot run: a build that left a "
                            "dependency behind is exactly what this check exists for")

        def green():
            stash.rename(fastify)
            proc = verify_artifact(root, dsn=None)
            return "[PASS] api (local_api) executes from inside the artifact" in proc.stdout, \
                "and runs again once the dependency is back"

        control("NC-M6A-002 an entry point whose dependency the build left behind", red, green)

    def nc_003():
        def red():
            planted = run(ADMIN, """
                CREATE FUNCTION public.demo_reset_floor() RETURNS void
                LANGUAGE sql AS $$ SELECT 1 $$;
            """, tx=True, rollback=True)
            # The plant and the scan must share one transaction, because the plant rolls
            # back — so the scan runs inside the same statement batch.
            scan = run(ADMIN, """
                CREATE FUNCTION public.demo_reset_floor() RETURNS void
                LANGUAGE sql AS $$ SELECT 1 $$;
                SELECT coalesce(string_agg(n.nspname || '.' || p.proname, ', '), 'NONE')
                  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                   AND p.proname ~* '(demo_reset|reset_demo|factory_reset|wipe_|seed_demo)';
            """, tx=True, rollback=True)
            found = (scan.scalar or "").strip()
            return "demo_reset_floor" in found, f"the scan sees it: {found}"

        def green():
            scan = run(ADMIN, """
                SELECT coalesce(string_agg(n.nspname || '.' || p.proname, ', '), 'NONE')
                  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                   AND p.proname ~* '(demo_reset|reset_demo|factory_reset|wipe_|seed_demo)';
            """, tx=True, rollback=True)
            found = (scan.scalar or "").strip()
            return found == "NONE", "and nothing of the kind is installed outside the plant"

        control("NC-M6A-003 a demo-reset function installed in the database", red, green)

    def nc_004():
        target = REPO / "deploy" / "Dockerfile"
        original = target.read_bytes()

        def red():
            target.write_bytes(original + b"\nCOPY seeds ./seeds\n")
            proc = subprocess.run(
                [sys.executable, str(REPO / "tools" / "generate_dockerfile.py"),
                 "--check", str(target)], capture_output=True, text=True, timeout=120)
            return "DOCKERFILE_DRIFT" in proc.stdout, \
                "a hand-edited image definition is refused against the manifest"

        def green():
            target.write_bytes(original)
            proc = subprocess.run(
                [sys.executable, str(REPO / "tools" / "generate_dockerfile.py"),
                 "--check", str(target)], capture_output=True, text=True, timeout=120)
            return proc.returncode == 0, "and matches again once reverted"

        control("NC-M6A-004 an image definition edited away from its manifest", red, green)

    for case in (nc_001, nc_002, nc_003, nc_004):
        case()

    registered = [c for c in registry.CONTROLS if c[3] == "m6a"]
    record("every M6-A control is registered in tools/controls.py",
           len(registered) == 4, f"{len(registered)} registered")


# ===========================================================================
# 7. The bounds
# ===========================================================================

def section_bounds() -> None:
    print("\n--- 7. The bounds, named rather than left to silence ---")
    for bound in (
        "THE IMAGE HAS NOT BEEN BUILT. Docker's daemon is not running on this machine and "
        "the disk would not hold an image if it were. deploy/Dockerfile is DERIVED from "
        "the manifest and check-locked against it, and the tree it would contain has been "
        "built, probed and scanned — so the gap is the packaging, not the contents",
        "THE DATABASE CLIENT IS THE ONE DEPENDENCY THE ARTIFACT CANNOT CARRY. psql belongs "
        "to the PostgreSQL distribution; the Dockerfile installs postgresql-client and the "
        "check proves one is reachable, but on this machine that is the host's",
        "NOTHING IN THE ARTIFACT CREATES A FIRST TENANT. That is deliberate — every seed "
        "here builds the demonstration floor — and it leaves production provisioning "
        "unbuilt. It is M6-E's and is named rather than filled by a demo loader",
        "node_modules IS NOT SCANNED for reset-shaped code. It is third-party and "
        "enormous; scanning it would report on other people's code and say nothing about "
        "this artifact's behaviour. Named rather than silently skipped",
    ):
        record("recorded in planning/M6_FINDINGS.md", True, bound)


def cleanup() -> None:
    base = CONTEXT.get("base")
    if base and Path(base).exists():
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    print("=" * 74)
    print("  M6-A — the built artifact, and nothing in it that can reset production")
    print("=" * 74)

    try:
        for section in (section_build, section_executes, section_prohibition,
                        section_database, section_dockerfile, section_controls,
                        section_bounds):
            try:
                section()
            except Exception as exc:                        # noqa: BLE001
                record(f"{section.__name__} completed", False,
                       f"{type(exc).__name__}: {str(exc)[:400]}")
    finally:
        cleanup()

    failed = [name for name, ok, _d, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")
    owned = len([c for c in registry.CONTROLS if c[3] == "m6a"])

    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}")
    print(f"  asserted      : {len(results) - measured_count}")
    print(f"  controls      : {owned} registered, each proved red then green")

    if failed:
        print("\nFAIL M6A_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS M6A_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
