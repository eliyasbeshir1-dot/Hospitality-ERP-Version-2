#!/usr/bin/env python3
"""M0R skeleton verification — forbidden-surface check.

Proves the repository contains documentation and planning artifacts only, with no
database schema, migration, application route, worker or UI.

Governing requirement: FR-GOV-001A.

DO NOT EDIT THIS SCRIPT TO MAKE IT PASS.
If it reports a finding, remove what it found. Five review cycles in this project were
lost to checks that were tuned until they went green. Fix the thing, never the check.

Usage:
    python3 verify_m0r_skeleton.py --repo .
    python3 verify_m0r_skeleton.py --repo . --json-report m0r_verification.json

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


# Everything under this prefix is pinned evidence and is not scanned as repository source.
DOCS_PREFIX = "docs/"
ALLOWED_TOOL_SCRIPTS = {"tools/verify_m0r_skeleton.py"}

FORBIDDEN_DIRS = [
    "migrations", "migration", "db", "database", "src", "app", "apps",
    "services", "service", "web", "pwa", "ui", "frontend", "backend",
    "api", "server", "client", "packages", "lib", "models", "schema", "schemas",
]

FORBIDDEN_EXTENSIONS = {
    ".sql": "database schema or migration",
    ".prisma": "ORM schema",
    ".tsx": "UI component",
    ".jsx": "UI component",
    ".vue": "UI component",
    ".svelte": "UI component",
}

SOURCE_EXTENSIONS = {".ts", ".js", ".mjs", ".cjs", ".py", ".go", ".rs", ".java", ".rb", ".php"}

# Content signatures that indicate application code rather than planning prose.
CODE_SIGNATURES = [
    (re.compile(r"\bCREATE\s+TABLE\b", re.I), "SQL DDL"),
    (re.compile(r"\bALTER\s+TABLE\b", re.I), "SQL DDL"),
    (re.compile(r"\bfastify\s*\(", re.I), "Fastify server bootstrap"),
    (re.compile(r"\bapp\.(get|post|put|patch|delete)\s*\(", re.I), "HTTP route handler"),
    (re.compile(r"\brouter\.(get|post|put|patch|delete)\s*\(", re.I), "HTTP route handler"),
    (re.compile(r"@(Entity|Table|Column)\b"), "ORM entity"),
    (re.compile(r"\bcreateServer\s*\(", re.I), "server bootstrap"),
]

NEVER_COMMIT = ["node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"]


def rel(p: Path, root: Path) -> str:
    return str(p.relative_to(root)).replace("\\", "/")


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify an M0R repository skeleton.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--json-report")
    args = ap.parse_args()
    root = Path(args.repo).resolve()

    findings = []
    scanned = docs_files = 0

    for path in sorted(root.rglob("*")):
        if ".git/" in str(path).replace("\\", "/") + "/":
            continue
        r = rel(path, root)

        if any(part in NEVER_COMMIT for part in path.parts):
            findings.append({"code": "NEVER_COMMIT_PATH", "path": r,
                             "detail": "build artifact or dependency directory must not be committed"})
            continue

        # /docs is pinned evidence — counted, never scanned for forbidden surface.
        if r.startswith(DOCS_PREFIX):
            if path.is_file():
                docs_files += 1
            continue

        if path.is_dir():
            if path.name.lower() in FORBIDDEN_DIRS:
                findings.append({"code": "FORBIDDEN_DIRECTORY", "path": r,
                                 "detail": f"'{path.name}' is not permitted at M0R; first allowed at M1 or later"})
            continue

        scanned += 1
        ext = path.suffix.lower()

        if ext in FORBIDDEN_EXTENSIONS:
            findings.append({"code": "FORBIDDEN_FILE_TYPE", "path": r,
                             "detail": f"{FORBIDDEN_EXTENSIONS[ext]} is not permitted at M0R"})
            continue

        if ext in SOURCE_EXTENSIONS and r not in ALLOWED_TOOL_SCRIPTS:
            findings.append({"code": "APPLICATION_SOURCE", "path": r,
                             "detail": "source file outside the permitted M0R tool set"})
            continue

        if ext in {".md", ".yml", ".yaml", ".json", ".txt"} or r in ALLOWED_TOOL_SCRIPTS:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            # The brief and plans legitimately QUOTE forbidden patterns while prohibiting
            # them. Only flag documents that are not themselves governance artifacts.
            governance = ("/planning/" in "/" + r or r.endswith("README.md")
                          or r in ALLOWED_TOOL_SCRIPTS)
            if not governance:
                for pattern, label in CODE_SIGNATURES:
                    if pattern.search(text):
                        findings.append({"code": "CODE_SIGNATURE", "path": r,
                                         "detail": f"{label} detected in a non-governance file"})
                        break

    # Positive requirements of the gate.
    required = ["README.md", "planning/ARCHITECTURE_CONFORMANCE_PLAN.md",
                "planning/MIGRATION_AND_DOMAIN_OWNERSHIP_MAP.md",
                "planning/CI_TEST_MATRIX.md"]
    for req in required:
        if not (root / req).exists():
            findings.append({"code": "MISSING_REQUIRED_ARTIFACT", "path": req,
                             "detail": "required M0R planning artifact is absent"})

    if docs_files == 0:
        findings.append({"code": "DOCS_PACKAGE_ABSENT", "path": DOCS_PREFIX,
                         "detail": "the approved v2.0.9 package must be present under /docs"})
    elif docs_files < 90:
        findings.append({"code": "DOCS_PACKAGE_INCOMPLETE", "path": DOCS_PREFIX,
                         "detail": f"expected at least 90 files under /docs, found {docs_files}"})

    report = {
        "verification": "m0r_skeleton",
        "gate": "M0R",
        "governing_requirement": "FR-GOV-001A",
        "checked_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "repository": str(root),
        "repository_files_scanned": scanned,
        "docs_files_counted": docs_files,
        "finding_count": len(findings),
        "findings": findings,
        "passed": not findings,
        "note": ("A finding means forbidden surface exists in the repository. Remove it. "
                 "Never edit this script, add exclusions, or suppress the check."),
    }
    if args.json_report:
        Path(args.json_report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if findings:
        print(f"FAIL M0R_SKELETON — {len(findings)} finding(s)\n", file=sys.stderr)
        for f in findings:
            print(f"  {f['code']}: {f['path']}\n      {f['detail']}", file=sys.stderr)
        return 1

    print("PASS M0R_SKELETON")
    print(f"  repository files scanned : {scanned}")
    print(f"  docs package files       : {docs_files}")
    print("  forbidden surface        : none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
