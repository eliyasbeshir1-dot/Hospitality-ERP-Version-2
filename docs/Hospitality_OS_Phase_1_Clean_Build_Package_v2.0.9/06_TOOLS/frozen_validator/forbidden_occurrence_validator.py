#!/usr/bin/env python3
"""Hospitality OS forbidden-occurrence validator (fail-closed).

WHAT THIS DOES
    1. Detects occurrences of the controlled vocabulary across the governed fields.
    2. Computes each occurrence's canonical composite key.
    3. Compares the detected set against the approved canonical occurrence registry.
    4. Validates hashes, references, normalization version and exact set equality.

WHAT THIS DELIBERATELY DOES NOT DO
    It never infers whether English wording is permitted. There is no sentence-level
    negation heuristic, no sense-exclusion matching and no adversative clause splitting.
    Authorization comes exclusively from the canonical registry, which can only change
    through a canonical amendment.

    This module must NEVER import classify_occurrences.py or any classification logic.
    That module is enumeration and review evidence only.

Exit 0 = PASS, 1 = FAIL. Standard library only.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import occurrence_mechanism as om  # detection + normalization only

CLASSIFICATION_ENUM = {
    "permitted_operational_sense", "fenced_negative_statement", "deferral_reference",
    "extension_contract_documentation", "vocabulary_definition",
}
AUTH_TYPES = {"requirement", "decision", "non_regression_rule"}


class Result:
    def __init__(self):
        self.failures = []

    def fail(self, code, detail):
        self.failures.append({"code": code, "detail": str(detail)[:400]})

    def check(self, ok, code, detail):
        if not ok:
            self.fail(code, detail)
        return ok


def _load(path, r):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        r.fail("JSON_READ", f"{path}: {e}")
        return None


def validate(root: Path, r: Result):
    machine = root / "02_MACHINE_READABLE"
    rules = _load(machine / "forbidden_surface_rules.json", r)
    spec = _load(machine / "governed_fields.json", r)
    reg = _load(machine / "forbidden_occurrence_registry.json", r)
    reqs = _load(machine / "requirements.json", r)
    decs = _load(machine / "decisions.json", r)
    nrs = _load(machine / "non_regression_rules.json", r)
    amds = _load(machine / "amendment_register.json", r)
    if r.failures:
        return

    # ---------------------------------------------------------------- guards
    # Zero-detection false greens: every count is asserted independently, so a
    # silently empty vocabulary or governed-field list can never pass.
    vocab = om.load_vocabulary(rules)
    r.check(len(vocab) > 0, "VOCABULARY_EMPTY", "no forbidden vocabulary terms loaded")
    governed = spec.get("governed_fields", []) if spec else []
    r.check(len(governed) > 0, "GOVERNED_FIELDS_EMPTY", "no governed fields configured")
    entries = reg.get("occurrences", []) if reg else []
    r.check(len(entries) > 0, "REGISTRY_EMPTY", "occurrence registry has no entries")
    expected = reg.get("expected_occurrence_count") if reg else None
    r.check(isinstance(expected, int) and expected > 0,
            "EXPECTED_COUNT_INVALID", f"expected_occurrence_count={expected}")
    if r.failures:
        return

    # Normalization version must agree everywhere. A bump invalidates the registry.
    rnv = reg.get("normalization_version")
    r.check(rnv == om.NORMALIZATION_VERSION, "NORMALIZATION_VERSION_MISMATCH",
            f"registry={rnv} implementation={om.NORMALIZATION_VERSION}")

    # Governed-field specification must still match the canonical schema.
    try:
        detected = om.detect_all(str(machine), spec, vocab)
    except RuntimeError as e:
        r.fail("GOVERNED_FIELD_SPEC_STALE", e)
        return

    # Detector-alive control: the planted fixtures must always be found.
    r.check(len(detected) > 0, "DETECTOR_SILENT", "zero occurrences detected")
    alive = [d for d in detected if d["record_id"].startswith("NC-M0-")]
    r.check(len(alive) > 0, "DETECTOR_ALIVE_CONTROL_MISSING",
            "planted negative-control occurrences were not detected")
    r.check(len(detected) == expected, "EXPECTED_COUNT_DRIFT",
            f"detected={len(detected)} expected={expected}")

    # ---------------------------------------------------------------- entries
    seen_ids, keyed = set(), {}
    valid_fields = set()
    for g in governed:
        valid_fields.update(g.get("fields", []))
        for s in g.get("subrecords", []):
            valid_fields.update(s.get("fields", []))

    req_ids = {x["id"] for x in reqs.get("active_requirements", [])}
    dec_ids = {x["id"] for x in decs.get("decisions", [])}
    nr_ids = {x["id"] for x in nrs.get("rules", [])}
    amd_ids = set()
    for k, v in (amds or {}).items():
        if isinstance(v, list):
            for a in v:
                if isinstance(a, dict) and ("amendment_id" in a or "id" in a):
                    amd_ids.add(a.get("amendment_id") or a["id"])

    for e in entries:
        oid = e.get("occurrence_id")
        if oid in seen_ids:
            r.fail("OCCURRENCE_ID_DUPLICATE", oid)
        seen_ids.add(oid)

        if e.get("classification") not in CLASSIFICATION_ENUM:
            r.fail("CLASSIFICATION_INVALID", f"{oid}: {e.get('classification')}")
        if e.get("normalization_version") != om.NORMALIZATION_VERSION:
            r.fail("ENTRY_NORMALIZATION_VERSION_MISMATCH", oid)

        base = e.get("field", "").split("[")[0]
        if base not in valid_fields:
            r.fail("ENTRY_FIELD_UNKNOWN", f"{oid}: {e.get('field')}")

        ar = e.get("authorizing_reference") or {}
        if ar.get("type") not in AUTH_TYPES:
            r.fail("AUTHORIZING_REFERENCE_TYPE_INVALID", f"{oid}: {ar.get('type')}")
        aid = ar.get("id")
        if not aid:
            r.fail("AUTHORIZING_REFERENCE_MISSING", oid)
        elif aid not in req_ids | dec_ids | nr_ids:
            r.fail("AUTHORIZING_REFERENCE_NOT_FOUND", f"{oid}: {aid}")

        amd = e.get("introduced_by_amendment")
        if not amd:
            r.fail("AMENDMENT_REFERENCE_MISSING", oid)
        elif amd_ids and amd not in amd_ids:
            r.fail("AMENDMENT_REFERENCE_NOT_FOUND", f"{oid}: {amd}")

        if om.sha256_text(e.get("exact_excerpt", "")) != e.get("excerpt_sha256"):
            r.fail("EXCERPT_HASH_MISMATCH", oid)

        key = (e.get("record_type"), e.get("record_id"), e.get("field"), e.get("term_id"),
               e.get("normalized_sentence_sha256"), e.get("occurrence_ordinal"),
               e.get("excerpt_sha256"))
        if key in keyed:
            r.fail("REGISTRY_DUPLICATE_OCCURRENCE", f"{keyed[key]} and {oid} claim one occurrence")
        keyed[key] = oid

    # ---------------------------------------------------------------- set equality
    detected_keys = {om.occurrence_key(d) for d in detected}
    registry_keys = set(keyed)

    for k in sorted(detected_keys - registry_keys):
        r.fail("OCCURRENCE_UNCLASSIFIED", f"{k[1]}.{k[2]} term={k[3]} ordinal={k[5]}")
    for k in sorted(registry_keys - detected_keys):
        r.fail("REGISTRY_ENTRY_STALE", f"{keyed[k]} -> {k[1]}.{k[2]} term={k[3]}")

    r.check(detected_keys == registry_keys, "OCCURRENCE_SET_NOT_EQUAL",
            f"detected={len(detected_keys)} registry={len(registry_keys)}")
    r.check(len(entries) == len(detected),
            "REGISTRY_COUNT_MISMATCH", f"entries={len(entries)} detected={len(detected)}")


def main():
    ap = argparse.ArgumentParser(description="Fail-closed forbidden-occurrence validator.")
    ap.add_argument("target", nargs="?", default=".")
    ap.add_argument("--json-report")
    args = ap.parse_args()
    r = Result()
    try:
        validate(Path(args.target), r)
    except Exception as e:
        r.fail("VALIDATOR_RUNTIME", e)
    report = {"validator": "forbidden_occurrence_validator", "version": "1.0",
              "normalization_version": om.NORMALIZATION_VERSION,
              "passed": not r.failures, "failure_count": len(r.failures),
              "failures": r.failures}
    if args.json_report:
        Path(args.json_report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if r.failures:
        for f in r.failures[:40]:
            print(f"FAIL {f['code']}: {f['detail']}", file=sys.stderr)
        print(json.dumps({k: v for k, v in report.items() if k != "failures"}, indent=2))
        return 1
    print("PASS FORBIDDEN_OCCURRENCE_REGISTRY_VALID")
    print(json.dumps({k: v for k, v in report.items() if k != "failures"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
