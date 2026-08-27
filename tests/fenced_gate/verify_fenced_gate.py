#!/usr/bin/env python3
"""Mutation coverage for the fenced-domain gate.

Repair P1-01. The gate carried a hardcoded vocabulary for two slices; of the 63
authoritative terms only 17 were detected when used as an identifier, and two domains had
no coverage at all. A gap that survived two slices needs a test of its own, so this suite
plants a real mutation for every authoritative term and requires the verifier to fail.

Nothing here names a fenced term. Every probe is derived from the pinned package at run
time — including the domain representatives, chosen by position rather than by name,
because the domain keys are themselves built from fenced words. Writing any of them here
would reintroduce the exact defect being repaired.

Mutations are planted in a hard-linked copy of the repository under a temporary directory,
never in the repository itself. Files are only ever CREATED in the copy, or removed and
rewritten — never opened for writing in place, which would write through a hard link into
the real repository.

Usage:
    python3 tests/fenced_gate/verify_fenced_gate.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))

from fenced import (  # noqa: E402
    RULES_PATH, domain_count, load_vocabulary, representatives, term_count,
)

ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def make_copy(destination: Path) -> Path:
    """Hard-linked copy of the repository, excluding .git and any build output."""
    destination.mkdir(parents=True, exist_ok=True)
    for entry in REPO.iterdir():
        if entry.name in {".git", "node_modules", "dist", "build", "__pycache__"}:
            continue
        target = destination / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, copy_function=os.link,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            os.link(entry, target)
    return destination


def run_verifier(repo: Path, report: Path | None = None) -> tuple[int, str, str]:
    """Run the COPY's verifier against the copy, so its vocabulary can be broken safely."""
    command = [sys.executable, str(repo / "tools" / "verify_m1.py"), "--repo", str(repo)]
    if report is not None:
        command += ["--json-report", str(report)]
    proc = subprocess.run(command, capture_output=True, text=True, env=ENV)
    return proc.returncode, proc.stdout, proc.stderr


def findings_from(report: Path) -> list[dict]:
    """Structured findings. Read from the report rather than scraped from stderr, so an
    assertion names the domain the verifier actually attributed a hit to."""
    if not report.exists():
        return []
    return json.loads(report.read_text(encoding="utf-8")).get("findings", [])


def replace_file(path: Path, content: str) -> None:
    """Remove then write. Never open a hard-linked file for writing in place."""
    if path.exists():
        path.unlink()
    path.write_text(content, encoding="utf-8")


def identifier(term: str) -> str:
    return term.lower().replace(" ", "_").replace("-", "_")


def mutation_source(term: str, index: int) -> str:
    """A source file that uses a fenced term as a positive obligation."""
    return (f"-- generated mutation {index}\n"
            f"CREATE TABLE probe.{identifier(term)}_enabled (id uuid PRIMARY KEY);\n")


# ===========================================================================

def section_provenance() -> None:
    print("\n--- 1. The gate's vocabulary comes from the pinned package ---")

    terms, domains = term_count(), domain_count()
    raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    from_file = sum(len(v) for v in raw["forbidden_positive_obligations"].values())
    record("the loaded term count equals the package's own count",
           terms == from_file and terms > 0,
           f"{terms} terms across {domains} domains, counted independently from "
           f"{RULES_PATH.name} as {from_file} — not a constant in any source file")

    source = (REPO / "tools" / "verify_m1.py").read_text(encoding="utf-8")
    sys.path.insert(0, str(REPO / "tests"))
    from fenced import source_patterns
    literals = sorted({t for _d, t, p in source_patterns() if p.search(source)})
    record("no fenced literal remains in the verifier", not literals,
           f"found: {literals}" if literals else
           "the verifier names no forbidden term; it loads all of them at run time")

    record("the verifier reports its vocabulary provenance",
           "vocabulary loaded" in run_verifier(REPO)[1],
           "a reader of the output can see how many terms were in force")


def section_fail_closed() -> None:
    print("\n--- 2. The gate fails closed without its vocabulary ---")

    before = hashlib.sha256(RULES_PATH.read_bytes()).hexdigest()

    with tempfile.TemporaryDirectory(prefix="fenced-gate-") as tmp:
        copy = make_copy(Path(tmp) / "repo")
        rules = copy / RULES_PATH.relative_to(REPO)

        baseline = run_verifier(copy)
        record("the copy passes before anything is broken", baseline[0] == 0,
               (baseline[1] or baseline[2]).strip().splitlines()[0] if baseline[1] or baseline[2] else "")

        rules.unlink()
        code, out, err = run_verifier(copy)
        record("an absent vocabulary refuses to scan",
               code != 0 and "VOCABULARY_UNAVAILABLE" in err and "PASS" not in out,
               "FAIL VOCABULARY_UNAVAILABLE — it does not fall back to a built-in list")

        replace_file(rules, "{ not valid json")
        code, out, err = run_verifier(copy)
        record("an unreadable vocabulary refuses to scan",
               code != 0 and "VOCABULARY_UNAVAILABLE" in err and "PASS" not in out,
               "a malformed rules file stops the verifier rather than emptying it")

        replace_file(rules, json.dumps({"forbidden_positive_obligations": {}}))
        code, out, err = run_verifier(copy)
        record("an empty vocabulary refuses to scan",
               code != 0 and "PASS" not in out,
               "zero terms would pass everything while reporting success, so it is refused")

        # The decisive case: broken vocabulary AND a real violation present.
        replace_file(copy / "migrations" / "9999_probe.sql",
                     mutation_source(representatives()[0][1], 0))
        code, out, err = run_verifier(copy)
        record("a broken vocabulary never passes a repository that is actually violating",
               code != 0 and "PASS" not in out,
               "the failure is the missing vocabulary, and it is still a failure")

    after = hashlib.sha256(RULES_PATH.read_bytes()).hexdigest()
    record("the real pinned package was never modified", before == after,
           "mutations are confined to a hard-linked copy under a temporary directory")


def section_every_term() -> None:
    print("\n--- 3. Every authoritative term is detected ---")

    vocabulary = load_vocabulary()
    every = sorted({t for group in vocabulary.values() for t in group})

    with tempfile.TemporaryDirectory(prefix="fenced-sweep-") as tmp:
        copy = make_copy(Path(tmp) / "repo")
        probes = copy / "migrations"

        # One file per term, planted together, so a single scan covers all 63.
        planted: dict[str, str] = {}
        for index, term in enumerate(every):
            name = f"9{index:03d}_probe.sql"
            replace_file(probes / name, mutation_source(term, index))
            planted[name] = term

        code, out, err = run_verifier(copy)
        flagged = {line.split(": ", 1)[1].strip()
                   for line in err.splitlines() if "FENCED_DOMAIN_SURFACE:" in line}
        flagged_names = {Path(p).name for p in flagged}
        missed = sorted(term for name, term in planted.items() if name not in flagged_names)

        record(f"all {len(every)} authoritative terms are detected when planted",
               code != 0 and not missed,
               f"{len(planted) - len(missed)} of {len(planted)} planted terms flagged"
               + (f"; UNDETECTED: {missed}" if missed else
                  " — every term in the pinned vocabulary produces a finding"))

        for name in planted:
            (probes / name).unlink()
        code, out, _ = run_verifier(copy)
        record("the copy passes again once every mutation is removed", code == 0,
               "the sweep leaves nothing behind")


def section_domain_mutations() -> None:
    print("\n--- 4. Per-domain mutation, each red before green ---")

    with tempfile.TemporaryDirectory(prefix="fenced-domain-") as tmp:
        copy = make_copy(Path(tmp) / "repo")
        probe = copy / "migrations" / "9999_domain_probe.sql"

        report = Path(tmp) / "report.json"
        for index, (domain, term) in enumerate(representatives()):
            replace_file(probe, mutation_source(term, index))
            red_code, _red_out, _red_err = run_verifier(copy, report)
            hits = [f for f in findings_from(report)
                    if f.get("code") == "FENCED_DOMAIN_SURFACE"
                    and Path(f.get("path", "")).name == probe.name]
            # Attribution is to the DOMAIN, not to the exact term. Several terms in one
            # domain can match the same identifier — a probe built from one term may be
            # reported under a shorter sibling — and either is the gate working.
            went_red = red_code != 0 and any(f.get("domain") == domain for f in hits)
            attributed = sorted({f.get("term") for f in hits})
            record(f"{domain} — RED with a mutation planted", went_red,
                   f"planted {identifier(term)}_enabled; "
                   + (f"flagged under this domain, attributed to {attributed}" if went_red else
                      f"NOT flagged for this domain (exit {red_code}, hits {hits})"))

            probe.unlink()
            green_code, _, green_err = run_verifier(copy)
            record(f"{domain} — GREEN after revert", green_code == 0,
                   "" if green_code == 0 else green_err.strip().splitlines()[0])


def main() -> int:
    print("Fenced-domain gate verification — repair P1-01")
    print("vocabulary loaded from the pinned package; no fenced term appears in this suite\n")

    section_provenance()
    section_fail_closed()
    section_every_term()
    section_domain_mutations()

    failed = [n for n, ok, _ in results if not ok]
    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    if failed:
        print("\nFAIL FENCED_GATE_VERIFICATION")
        for n in failed:
            print(f"  - {n}")
        return 1
    print("\nPASS FENCED_GATE_VERIFICATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
