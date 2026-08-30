#!/usr/bin/env python3
"""M1 forbidden-surface verifier.

Replaces verify_m0r_skeleton.py from gate M1 onward.

WHAT CHANGED FROM M0R
    Migrations, schema and application source are now PERMITTED — that is the work of M1.
    What remains forbidden is the fenced-domain surface: the Phase 2/3 domains fenced for
    every gate of Phase 1, which never become permitted.

    Also enforced: no v1.1 migration history, no bypass roles in deployment paths,
    no committed build artifacts, and /docs byte-integrity.

WHERE THE VOCABULARY COMES FROM
    The pinned package, at
    docs/…/02_MACHINE_READABLE/forbidden_surface_rules.json, loaded through
    tests/fenced.py — the same loader every slice harness uses.

    This file contains NO fenced term, deliberately. An earlier revision carried a
    hardcoded list, and an independent review proved the consequence: of 63 authoritative
    terms only 17 were detected when used as an identifier, so a table named after one of
    the fenced domains passed a gate whose entire purpose was to stop it. A hardcoded copy
    of a vocabulary is not a shortcut, it is a second source of truth that diverges from
    the first in silence.

    If the vocabulary cannot be loaded, this verifier FAILS CLOSED. It has no built-in
    list to fall back to, and it refuses to scan with an empty one: a vocabulary of zero
    terms passes everything while reporting success, which is the false green this whole
    mechanism exists to prevent.

DO NOT EDIT THIS SCRIPT TO MAKE IT PASS.
If it reports a finding, remove what it found.

Usage:
    python3 tools/verify_m1.py --repo .
    python3 tools/verify_m1.py --repo . --json-report m1_verification.json

Exit 0 = PASS. Exit 1 = findings. Standard library only.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from datetime import datetime, timezone
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console import use_utf8_output  # noqa: E402

use_utf8_output()


# The shared loader lives beside the harnesses that also consume it. The verifier imports
# it rather than keeping a copy, because a copy is precisely what failed here before.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
try:
    from fenced import (  # noqa: E402
        RULES_PATH, VocabularyUnavailable, domain_count, source_patterns, term_count,
    )
except Exception as _import_error:                                    # pragma: no cover
    print("FAIL VOCABULARY_UNAVAILABLE", file=sys.stderr)
    print(f"  the fenced vocabulary loader could not be imported: {_import_error}",
          file=sys.stderr)
    print("  the verifier has no built-in list and will not scan without one.",
          file=sys.stderr)
    raise SystemExit(1)

DOCS_PREFIX = "docs/"
NEVER_COMMIT = ["node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"]

# Contexts where naming a fenced term is legitimate: prohibitions and documentation.
NEGATION = re.compile(
    r"\b(no|not|never|without|prohibit|forbidden|excluded|deferred|absent|"
    r"phase\s*2|phase\s*3|must\s+not|shall\s+not|is\s+fenced|remains\s+fenced)\b", re.I)

V11_HISTORY = [
    (re.compile(r"hospitality[-_]erp(?![-_]version[-_]2)", re.I), "reference to the frozen v1.1 repository"),
]

# Roles that must never appear in a deployment or bootstrap path.
BYPASS_ROLES = re.compile(r"\b(bypassrls|superuser|rolsuper)\b", re.I)
DEPLOYMENT_HINT = re.compile(r"(bootstrap|deploy|provision|infra|helm|terraform|compose)", re.I)

SCANNABLE = {".sql", ".py", ".ts", ".js", ".mjs", ".cjs", ".go", ".rs", ".java", ".rb",
             ".yml", ".yaml", ".json", ".md", ".toml", ".tf"}


def rel(p: Path, root: Path) -> str:
    return str(p.relative_to(root)).replace("\\", "/")


def line_containing(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    return text[line_start:line_end if line_end != -1 else len(text)]


def main() -> int:
    ap = argparse.ArgumentParser(description="M1 forbidden-surface verifier.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--json-report")
    args = ap.parse_args()
    root = Path(args.repo).resolve()

    # ---- Load the authoritative vocabulary, or stop ----------------------------
    try:
        patterns = source_patterns()
        terms = term_count()
        domains = domain_count()
    except VocabularyUnavailable as error:
        print("FAIL VOCABULARY_UNAVAILABLE", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        print(f"  expected at: {RULES_PATH}", file=sys.stderr)
        print("  the verifier has no built-in list and will not scan without one.",
              file=sys.stderr)
        return 1

    # A vocabulary that loads empty would pass everything and say so cheerfully.
    if terms <= 0 or domains <= 0 or not patterns:
        print("FAIL VOCABULARY_EMPTY", file=sys.stderr)
        print(f"  loaded {terms} term(s) across {domains} domain(s) — refusing to scan.",
              file=sys.stderr)
        return 1

    findings = []
    scanned = docs_files = 0

    for path in sorted(root.rglob("*")):
        if "/.git/" in "/" + str(path).replace("\\", "/") + "/":
            continue
        r = rel(path, root)

        if any(part in NEVER_COMMIT for part in path.parts):
            findings.append({"code": "NEVER_COMMIT_PATH", "path": r,
                             "detail": "build artifact or dependency directory must not be committed"})
            continue

        if r.startswith(DOCS_PREFIX):
            if path.is_file():
                docs_files += 1
            continue

        if not path.is_file() or path.suffix.lower() not in SCANNABLE:
            continue

        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # Governance prose may name fenced domains in order to prohibit them.
        governance = r.startswith("planning/") or r.endswith("README.md") or "/tools/verify_" in "/" + r

        if not governance:
            reported_domains: set[str] = set()
            for domain, term, pattern in patterns:
                if domain in reported_domains:
                    continue
                for match in pattern.finditer(text):
                    if NEGATION.search(line_containing(text, match.start(), match.end())):
                        continue
                    findings.append({
                        "code": "FENCED_DOMAIN_SURFACE", "path": r, "domain": domain,
                        "term": term,
                        "detail": f"'{match.group(0)}' appears as a positive obligation, not a prohibition"})
                    reported_domains.add(domain)
                    break

        for pat, label in V11_HISTORY:
            if pat.search(text) and not governance:
                findings.append({"code": "V11_INHERITANCE", "path": r, "detail": label})
                break

        if DEPLOYMENT_HINT.search(r):
            for bm in BYPASS_ROLES.finditer(text):
                if NEGATION.search(line_containing(text, bm.start(), bm.end())):
                    continue
                findings.append({"code": "BYPASS_ROLE_IN_DEPLOYMENT_PATH", "path": r,
                                 "detail": f"'{bm.group(0)}' appears in a deployment or bootstrap path"})
                break

    if docs_files == 0:
        findings.append({"code": "DOCS_PACKAGE_ABSENT", "path": DOCS_PREFIX,
                         "detail": "the approved v2.0.9 package must remain under /docs"})
    elif docs_files != 92:
        findings.append({"code": "DOCS_PACKAGE_DRIFT", "path": DOCS_PREFIX,
                         "detail": f"expected exactly 92 files under /docs, found {docs_files}"})

    for req in ["README.md", "planning/ARCHITECTURE_CONFORMANCE_PLAN.md",
                "planning/MIGRATION_AND_DOMAIN_OWNERSHIP_MAP.md", "planning/CI_TEST_MATRIX.md"]:
        if not (root / req).exists():
            findings.append({"code": "MISSING_REQUIRED_ARTIFACT", "path": req,
                             "detail": "required planning artifact is absent"})

    mig = root / "migrations"
    if mig.is_dir():
        names = sorted(p.name for p in mig.glob("*.sql"))
        if names and not names[0].startswith("0001"):
            findings.append({"code": "MIGRATION_HISTORY_NOT_FROM_0001", "path": "migrations/",
                             "detail": f"ordered history must begin at 0001; first is {names[0]}"})

    report = {
        "verification": "m1_forbidden_surface", "gate": "M1",
        "checked_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "repository": str(root), "repository_files_scanned": scanned,
        "docs_files_counted": docs_files,
        "vocabulary_source": str(RULES_PATH),
        "vocabulary_terms": terms,
        "vocabulary_domains": domains,
        "finding_count": len(findings), "findings": findings,
        "passed": not findings,
        "note": ("Migrations, schema and application source are permitted from M1. Fenced Phase 2/3 "
                 "domains are forbidden at every gate. The vocabulary is loaded from the pinned "
                 "package and the verifier fails closed without it. Never edit this script to make "
                 "it pass."),
    }
    if args.json_report:
        Path(args.json_report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if findings:
        print(f"FAIL M1_FORBIDDEN_SURFACE — {len(findings)} finding(s)\n", file=sys.stderr)
        for f in findings:
            print(f"  {f['code']}: {f['path']}\n      {f['detail']}", file=sys.stderr)
        return 1

    print("PASS M1_FORBIDDEN_SURFACE")
    print(f"  repository files scanned : {scanned}")
    print(f"  docs package files       : {docs_files}")
    print(f"  vocabulary loaded        : {terms} terms across {domains} domains")
    print(f"  vocabulary source        : {RULES_PATH.relative_to(Path(__file__).resolve().parents[1])}")
    print("  fenced-domain surface    : none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
