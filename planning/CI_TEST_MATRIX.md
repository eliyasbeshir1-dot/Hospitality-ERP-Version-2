# CI Test Matrix — M0R Planning Artifact

CI at M0R runs **validators only**. There is no application, so there are no application
tests. Adding them now would be scope creep.

---

## What runs at M0R

| Job | Command | Pass condition |
|---|---|---|
| Skeleton conformance | `python3 tools/verify_m0r_skeleton.py --repo .` | PASS, 0 findings |
| Docs package integrity | `sha256sum -c SHA256SUMS.txt` in `/docs/...v2.0.9` | 91/91 OK |
| Occurrence registry | `python3 docs/.../06_TOOLS/frozen_validator/forbidden_occurrence_validator.py docs/...` | PASS |
| Mechanism suite | `python3 docs/.../06_TOOLS/test_occurrence_mechanism.py --package docs/...` | 28/28 |

---

## Fail-closed rules (FR-SEC-015)

The pipeline **fails** on any of:

- zero tests collected
- skipped tests
- empty scan results
- stale artifacts
- unsupported coverage
- unknown result status

A green build with nothing executed is a failure, not a pass. This rule exists because
false-green was the dominant defect class across five review cycles.

---

## The 44 planted negative controls

Frozen at Package M0 and planted per gate. Distribution:

| Gate | Controls |
|---|---:|
| M0 | 8 |
| M1 | 4 |
| M2 | 4 |
| M3 | 4 |
| M4 | 6 |
| M5a | 4 |
| M5b | 9 |
| M6 | 5 |

The 8 M0 controls — package pinning, requirement recount, phase boundary, vocabulary
completeness, accounting/CRM/workforce alias leakage, canonical projection parity — are
already satisfied by the pinned package under `/docs`.

Gate-specific controls are planted as each gate is implemented. **Do not plant M1+ controls
at M0R**; there is nothing for them to break.

---

## Platform note

`validate_package_m0.py` requires a temp path at least three components deep and reads
Windows-style separators from the generation manifest. It runs correctly on Windows and in
Codespaces with `TMPDIR` set to a nested path. See `KNOWN_LIMITATIONS.md`.

---

## What CI must NOT do at M0R

- run application tests (none exist)
- install runtime dependencies for an application
- build or deploy anything
- create a database
