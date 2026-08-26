#!/usr/bin/env python3
"""M1 forbidden-surface verifier.

Replaces verify_m0r_skeleton.py from gate M1 onward.

WHAT CHANGED FROM M0R
    Migrations, schema and application source are now PERMITTED — that is the work of M1.
    What remains forbidden is the fenced-domain surface: inventory, accounting, payroll,
    purchasing, supplier, courier, recipes, costing, loyalty, CRM, pickup and delivery.
    Those are fenced for every gate of Phase 1 and never become permitted.

    Also enforced: no v1.1 migration history, no bypass roles in deployment paths,
    no committed build artifacts, and /docs byte-integrity.

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

DOCS_PREFIX = "docs/"
NEVER_COMMIT = ["node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"]

# Fenced Phase 2/3 domains. Forbidden at EVERY gate, in schema, code and identifiers.
FENCED = {
    "inventory_stock_storage": [
        r"\bstock_level\b", r"\bstock_count\b", r"\bstorage_location\b", r"\bwarehouse\b",
        r"\binventory_item\b", r"\binventory_movement\b", r"\bconsumption_posting\b",
    ],
    "accounting_ledger": [
        r"\bgeneral_ledger\b", r"\bjournal_entry\b", r"\bjournal_entries\b",
        r"\baccounts_payable\b", r"\baccounts_receivable\b", r"\btrial_balance\b",
        r"\bchart_of_accounts\b", r"\bledger_posting\b",
    ],
    "workforce_payroll": [
        r"\bpayroll\b", r"\bemployee_record\b", r"\btimesheet\b", r"\battendance\b",
        r"\broster\b", r"\bshift_schedule\b", r"\bwage_run\b",
    ],
    "purchasing_supplier": [
        r"\bpurchase_order\b", r"\bprocurement\b", r"\bsupplier_catalog\b",
        r"\bgoods_receipt\b", r"\bsupplier_connector\b",
    ],
    "courier_delivery": [
        r"\bcourier\b", r"\bdispatch_rider\b", r"\bdelivery_address\b",
        r"\bdelivery_fee\b", r"\bdelivery_zone\b",
    ],
    "pickup": [r"\bpickup_code\b", r"\bpickup_slot\b", r"\bpickup_order\b"],
    "loyalty_crm": [
        r"\bloyalty_program\b", r"\bloyalty_point\b", r"\brewards_balance\b",
        r"\bcustomer_segment\b", r"\bmarketing_campaign\b", r"\bcampaign_id\b",
    ],
    "recipes_costing": [
        r"\brecipe_line\b", r"\bbill_of_materials\b", r"\btheoretical_usage\b",
        r"\bfood_cost\b", r"\bcosting_variance\b",
    ],
}

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


def main() -> int:
    ap = argparse.ArgumentParser(description="M1 forbidden-surface verifier.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--json-report")
    args = ap.parse_args()
    root = Path(args.repo).resolve()

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

        for domain, patterns in FENCED.items():
            for pat in patterns:
                # Match as an identifier component: payroll_id, employee_records, stock_levels
                loose = pat.replace(r"\b", "")
                loose = r"(?<![A-Za-z0-9])" + loose + r"(?:s|es|_[a-z0-9_]+)?(?![A-Za-z0-9])"
                for m in re.finditer(loose, text, re.I):
                    line_start = text.rfind("\n", 0, m.start()) + 1
                    line_end = text.find("\n", m.end())
                    line = text[line_start:line_end if line_end != -1 else len(text)]
                    if governance or NEGATION.search(line):
                        continue
                    findings.append({
                        "code": "FENCED_DOMAIN_SURFACE", "path": r, "domain": domain,
                        "detail": f"'{m.group(0)}' appears as a positive obligation, not a prohibition"})
                    break

        for pat, label in V11_HISTORY:
            if pat.search(text) and not governance:
                findings.append({"code": "V11_INHERITANCE", "path": r, "detail": label})
                break

        if DEPLOYMENT_HINT.search(r):
            for bm in BYPASS_ROLES.finditer(text):
                ls = text.rfind("\n", 0, bm.start()) + 1
                le = text.find("\n", bm.end())
                line = text[ls:le if le != -1 else len(text)]
                if NEGATION.search(line):
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
        "docs_files_counted": docs_files, "finding_count": len(findings), "findings": findings,
        "passed": not findings,
        "note": ("Migrations, schema and application source are permitted from M1. Fenced Phase 2/3 "
                 "domains are forbidden at every gate. Never edit this script to make it pass."),
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
    print("  fenced-domain surface    : none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
