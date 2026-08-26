#!/usr/bin/env python3
"""Occurrence-registry mechanism tests.

Twenty-eight cases: 18 mechanism tests that prove the registry design, and 10 Codex
regression probes from the v2.0.8 review.

The 18 are the real proof. The 10 probes fail by construction under fail-closed
enumeration and are retained as regression evidence, not as evidence the mechanism works.

Every case runs on a fresh temporary copy of the package, invokes the validator
unchanged as a subprocess, and deletes its copy. The source tree is never modified.

Standard library only.
"""
from __future__ import annotations
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = "06_TOOLS/frozen_validator/forbidden_occurrence_validator.py"
REG = "02_MACHINE_READABLE/forbidden_occurrence_registry.json"
GOV = "02_MACHINE_READABLE/governed_fields.json"
RULES = "02_MACHINE_READABLE/forbidden_surface_rules.json"
REQ = "02_MACHINE_READABLE/requirements.json"


def rd(root, rel):
    return json.loads((root / rel).read_text(encoding="utf-8"))


def wr(root, rel, obj):
    (root / rel).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def run_validator(root):
    proc = subprocess.run([sys.executable, str(root / VALIDATOR), str(root)],
                          capture_output=True, text=True)
    codes = []
    for line in (proc.stderr or "").splitlines():
        if line.startswith("FAIL "):
            codes.append(line.split(" ", 1)[1].split(":")[0])
    return proc.returncode == 0, sorted(set(codes))


# ------------------------------------------------------------------ mechanism cases
def t01_new_unclassified(root):
    """New unclassified occurrence."""
    d = rd(root, REQ)
    d["active_requirements"][0]["required_behavior"] += " Provide payroll management for staff."
    wr(root, REQ, d)


def t02_stale_sentence_hash(root):
    """Registry entry carrying a stale normalized-sentence hash."""
    r = rd(root, REG)
    r["occurrences"][0]["normalized_sentence_sha256"] = "0" * 64
    wr(root, REG, r)


def t03_wrong_excerpt_hash(root):
    """Registry entry whose excerpt hash does not match its excerpt."""
    r = rd(root, REG)
    r["occurrences"][1]["excerpt_sha256"] = "1" * 64
    wr(root, REG, r)


def t04_deleted_occurrence_stale_entry(root):
    """Canonical text removed, leaving the registry entry stale."""
    r = rd(root, REG)
    victim = next(e for e in r["occurrences"] if e["record_type"] == "requirement"
                  and e["field"] == "required_behavior")
    d = rd(root, REQ)
    for rec in d["active_requirements"]:
        if rec["id"] == victim["record_id"]:
            rec["required_behavior"] = "Behave consistently with the approved configuration."
    wr(root, REQ, d)


def t05_duplicate_entries(root):
    """Two registry entries claiming one occurrence."""
    r = rd(root, REG)
    dup = json.loads(json.dumps(r["occurrences"][2]))
    dup["occurrence_id"] = "FOC-9001"
    r["occurrences"].append(dup)
    wr(root, REG, r)


def t06_one_entry_two_occurrences(root):
    """One entry attempting to cover two occurrences: the second loses its entry."""
    r = rd(root, REG)
    groups = {}
    for e in r["occurrences"]:
        groups.setdefault((e["record_id"], e["field"], e["term_id"]), []).append(e)
    pair = next(v for v in groups.values() if len(v) >= 2)
    r["occurrences"] = [e for e in r["occurrences"] if e is not pair[1]]
    wr(root, REG, r)


def t07_missing_authorizing_reference(root):
    """Entry with no authorizing reference id."""
    r = rd(root, REG)
    r["occurrences"][3]["authorizing_reference"] = {"type": "requirement", "id": ""}
    wr(root, REG, r)


def t08_nonexistent_authorizing_id(root):
    """Entry naming an authorizing id that does not exist."""
    r = rd(root, REG)
    r["occurrences"][4]["authorizing_reference"] = {"type": "requirement", "id": "FR-ZZZ-999"}
    wr(root, REG, r)


def t09_missing_amendment(root):
    """Entry with no amendment reference."""
    r = rd(root, REG)
    r["occurrences"][5]["introduced_by_amendment"] = ""
    wr(root, REG, r)


def t10_invalid_classification(root):
    """Entry using a classification outside the closed enum."""
    r = rd(root, REG)
    r["occurrences"][6]["classification"] = "probably_fine"
    wr(root, REG, r)


def t11_other_governed_field(root):
    """New occurrence introduced in a different governed field."""
    d = rd(root, REQ)
    d["active_requirements"][1]["gate_local_behavior"] += " Maintain supplier procurement records."
    wr(root, REQ, d)


def t12_valid_unchanged(root):
    """Untouched package: must PASS."""
    return


def t13_formatting_only_change(root):
    """Formatting-only change permitted by the normalization policy: must PASS."""
    d = rd(root, REQ)
    rec = d["active_requirements"][0]
    rec["required_behavior"] = "  " + rec["required_behavior"].replace(" ", "  ") + "  "
    wr(root, REQ, d)


def t14_meaningful_reword_no_amendment(root):
    """Meaningful rewording of a classified sentence without a registry amendment."""
    r = rd(root, REG)
    victim = next(e for e in r["occurrences"] if e["record_type"] == "requirement"
                  and e["field"] == "required_behavior")
    d = rd(root, REQ)
    for rec in d["active_requirements"]:
        if rec["id"] == victim["record_id"]:
            rec["required_behavior"] = rec["required_behavior"].replace(
                victim["exact_excerpt"], victim["exact_excerpt"] + " reporting and analysis")
    wr(root, REQ, d)


def t15_normalization_version_change(root):
    """Normalization version bumped without re-amending the registry."""
    r = rd(root, REG)
    r["normalization_version"] = "2.0"
    for e in r["occurrences"]:
        e["normalization_version"] = "2.0"
    wr(root, REG, r)


def t16_vocabulary_empty(root):
    """Forbidden vocabulary emptied: detection would silently find nothing."""
    v = rd(root, RULES)
    v["forbidden_positive_obligations"] = {}
    wr(root, RULES, v)


def t17_governed_fields_empty(root):
    """Governed-field list emptied."""
    g = rd(root, GOV)
    g["governed_fields"] = []
    wr(root, GOV, g)


def t18_detector_alive_removed(root):
    """Planted detector-alive controls stripped from the negative-control register."""
    p = "02_MACHINE_READABLE/negative_controls.json"
    d = rd(root, p)
    for c in d["controls"]:
        if c["id"].startswith("NC-M0-"):
            for f in ("property", "deliberate_break", "expected_test"):
                if f in c:
                    c[f] = "redacted control text"
    wr(root, p, d)


MECHANISM = [
    ("MECH-01", t01_new_unclassified, "fail", "New unclassified occurrence"),
    ("MECH-02", t02_stale_sentence_hash, "fail", "Stale normalized-sentence hash"),
    ("MECH-03", t03_wrong_excerpt_hash, "fail", "Wrong excerpt hash"),
    ("MECH-04", t04_deleted_occurrence_stale_entry, "fail", "Deleted occurrence leaves stale entry"),
    ("MECH-05", t05_duplicate_entries, "fail", "Two entries for one occurrence"),
    ("MECH-06", t06_one_entry_two_occurrences, "fail", "One entry covering two occurrences"),
    ("MECH-07", t07_missing_authorizing_reference, "fail", "Missing authorizing reference"),
    ("MECH-08", t08_nonexistent_authorizing_id, "fail", "Nonexistent authorizing id"),
    ("MECH-09", t09_missing_amendment, "fail", "Missing amendment reference"),
    ("MECH-10", t10_invalid_classification, "fail", "Classification outside the closed enum"),
    ("MECH-11", t11_other_governed_field, "fail", "Occurrence added in another governed field"),
    ("MECH-12", t12_valid_unchanged, "pass", "Valid classified package"),
    ("MECH-13", t13_formatting_only_change, "pass", "Formatting-only change under normalization policy"),
    ("MECH-14", t14_meaningful_reword_no_amendment, "fail", "Meaningful rewording without amendment"),
    ("MECH-15", t15_normalization_version_change, "fail", "Normalization version bump without re-amendment"),
    ("MECH-16", t16_vocabulary_empty, "fail", "Vocabulary empty or unavailable"),
    ("MECH-17", t17_governed_fields_empty, "fail", "Governed-field list empty or unavailable"),
    ("MECH-18", t18_detector_alive_removed, "fail", "Detector-alive planted control not detected"),
]

# ------------------------------------------------------------------ Codex probes
PROBES = [
    "No inventory module is present, but provide payroll management for staff.",
    "Do not prevent managers from enabling payroll records.",
    "Provide ingredient variance calculations for kitchen production.",
    "Provide consumable inventory management for the outlet.",
    "No inventory module is present and payroll management is enabled for staff.",
    "Enable payroll management and inventory is not present.",
    "Never disable payroll management for staff.",
    "Cannot prohibit payroll management for staff.",
    "Maintain an equipment inventory and provide consumable inventory management for the outlet.",
    "Record cash variance and provide ingredient variance calculations for kitchen production.",
]


def make_probe(sentence):
    def probe(root):
        d = rd(root, REQ)
        d["active_requirements"][2]["required_behavior"] += " " + sentence
        wr(root, REQ, d)
    return probe


def main():
    ap = argparse.ArgumentParser(description="Run occurrence-registry mechanism tests.")
    ap.add_argument("--package", required=True)
    ap.add_argument("--report", default="mechanism_test_results.json")
    args = ap.parse_args()
    src = Path(args.package).resolve()

    cases = list(MECHANISM) + [
        (f"PROBE-{i:02d}", make_probe(s), "fail", f"Codex regression bypass: {s}")
        for i, s in enumerate(PROBES, 1)]

    results = []
    with tempfile.TemporaryDirectory(prefix="mech-") as td:
        work = Path(td)
        for cid, fn, expect, desc in cases:
            case = work / cid
            shutil.copytree(src, case)
            try:
                fn(case)
                passed, codes = run_validator(case)
                actual = "pass" if passed else "fail"
                ok = actual == expect
                err = None
            except Exception as e:
                actual, codes, ok, err = "error", [], False, f"{type(e).__name__}: {e}"
            finally:
                shutil.rmtree(case, ignore_errors=True)
            results.append({"case_id": cid, "description": desc, "expected": expect,
                            "actual": actual, "validator_failure_codes": codes,
                            "correct": ok, "error": err})
            print(f"{cid:<10} expect={expect:<4} actual={actual:<5} "
                  f"{'OK' if ok else 'WRONG':<5} {','.join(codes[:3]) or '-'}")

    correct = sum(1 for r in results if r["correct"])
    report = {"suite": "occurrence_registry_mechanism_tests", "version": "1.0",
              "total": len(results), "correct": correct,
              "incorrect": [r["case_id"] for r in results if not r["correct"]],
              "mechanism_cases": len(MECHANISM), "codex_regression_probes": len(PROBES),
              "note": ("The 18 mechanism cases are the proof of the registry design. The 10 Codex "
                       "probes fail by construction under fail-closed enumeration and are retained "
                       "as regression evidence only."),
              "results": results}
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\n{correct}/{len(results)} correct -> {args.report}")
    return 0 if correct == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
