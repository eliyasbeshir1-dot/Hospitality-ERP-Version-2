# CI Test Matrix

**Repository:** `Hospitality-ERP-Version-2`
**Gate:** M1 — complete (slices A, B, C, D)
**Governing requirement:** FR-SEC-015
**Workflow:** `.github/workflows/m1-conformance.yml`

CI ran validators only at M0R. From M1 it also runs the database suites against a real
PostgreSQL service container, because there is now something to test.

The M0R workflow has been retired. Its gate, `tools/verify_m0r_skeleton.py`, forbids
migrations and application source — the legitimate work of M1 — so continuing to run it
would fail the build for doing the assigned work. The script is retained unmodified as
historical evidence and is superseded by `tools/verify_m1.py`.

---

## What runs today

Five jobs, all required, none permitted to fail soft. Each runs on push, on pull request,
and on manual dispatch.

| Job | Command | Pass condition |
|---|---|---|
| `forbidden-surface` | `python3 tools/verify_m1.py --repo . --json-report m1_verification.json` | `PASS M1_FORBIDDEN_SURFACE`, JSON shows `passed: true`, `finding_count: 0`, exactly 92 docs files, and at least one file actually scanned |
| `docs-package-integrity` | `sha256sum -c SHA256SUMS.txt` inside `docs/…v2.0.9/` | exactly 92 files, exactly 91 checksum lines, exactly 91 `OK` results, 0 failures |
| `database-verification` | all four suites run in order against a `postgres:16` service, then again in reverse order; plus independent schema-catalog and evidence-report checks | all four suites report PASS, none reports a failure, each ran at least its expected number of checks, results are identical under reordering (FR-TST-020), the committed catalog matches the live schema, the evidence report lists no unproven control, and all nineteen negative controls were shown red **and** green |
| `occurrence-registry` | `python3 docs/…/06_TOOLS/frozen_validator/forbidden_occurrence_validator.py docs/…v2.0.9` | emits exactly `PASS FORBIDDEN_OCCURRENCE_REGISTRY_VALID`, and its JSON block shows `passed: true`, `failure_count: 0` |
| `mechanism-suite` | `python3 docs/…/06_TOOLS/test_occurrence_mechanism.py --package docs/…v2.0.9` | emits `28/28 correct` |

The database job runs every assertion through `hospitality_app`, the least-privileged
runtime role — never the owner, never a superuser (FR-DAT-017). The service container uses
trust authentication on an ephemeral, job-local database, which is what keeps every
credential out of the repository (FR-SEC-007).

### Negative controls are checked for non-vacuity

A control that never fails is not a control. The database job therefore greps both suite
logs and fails the build unless each of the nineteen controls — `NC-M1-001` to `NC-M1-004`,
`NC-M1B-001` to `NC-M1B-004`, `NC-M1C-001` to `NC-M1C-005` and `NC-M1D-001` to `NC-M1D-006`
— appears **both** as RED with a defect planted and as GREEN after revert. The evidence
report is regenerated in the same job and the build fails if it lists any control as
`not proven`. A control that silently stopped failing is a coverage gap wearing a green
badge, and this is what catches it.

Both success tokens are asserted **exactly**, not as substrings. A bare `PASS` does not
satisfy the occurrence job, and `27/28` or `0/0` does not satisfy the mechanism job. Each
was confirmed against real validator output and against deliberately degraded output before
being pinned.

`forbidden-surface` uploads its JSON report as a build artifact, with
`if-no-files-found: error` so a missing report fails rather than passing quietly.

---

## Fail-closed rules (FR-SEC-015)

The pipeline **fails** on any of:

- zero tests collected
- skipped or deselected tests
- empty scan results
- stale artifacts
- unsupported coverage
- unknown result status

**A green build with nothing executed is a failure, not a pass.** This rule exists because
false-green was the dominant defect class across five review cycles.

How each is enforced in the workflow:

- every step runs under `set -euo pipefail`, so an unnoticed non-zero exit cannot be swallowed
- no step uses `continue-on-error`; no job is optional
- validator output is asserted to be non-empty before it is interpreted
- exit status alone is never trusted — the success token *and* the structured result are
  both checked
- the occurrence job parses the validator's own JSON and fails on `passed != true` or any
  non-zero `failure_count`
- the mechanism job fails on any `skipped`, `deselected` or `no tests ran` marker even if
  the case count line is present
- the docs job counts checksum lines *before* verifying them, so a truncated
  `SHA256SUMS.txt` fails instead of trivially passing

---

## What CI must NOT do at this gate

- test a domain that has not been built yet
- install runtime dependencies beyond a Python interpreter and a PostgreSQL client
- build or deploy anything
- carry any credential, token or secret in the repository
- accept a schema catalog that does not match the live database
- accept results that change when the suites are run in a different order
- build inside the repository: `node_modules/` and `dist/` go to `$M1D_WORKSPACE`

The database created by CI is ephemeral and job-local. Nothing is deployed.

---

## Bytecode hygiene

The workflow sets `PYTHONDONTWRITEBYTECODE=1` globally.

The package validators import modules from inside `docs/`. Without this, Python writes
`__pycache__/` into the pinned package, which is both forbidden surface under
`tools/verify_m0r_skeleton.py` and a break in the package's byte-identity. This was observed
in practice while wiring the pipeline, caught by the verifier, and fixed at the source
rather than by excluding the path. **Do not remove that variable.**

`mechanism_test_results.json`, `m0r_verification.json` and `sha256-check.log` are generated
by these runs and are listed in `.gitignore`. They are build output, never committed.

---

## Platform note

`docs/…/06_TOOLS/validate_package_m0.py` is **not** run in this pipeline. It requires a
temp path at least three components deep and reads Windows-style separators from the
generation manifest, so it does not run on a default Linux path. Its coverage was confirmed
by hand instead — 26/26 generation projections matched with separators normalised, and the
canonical content root reproduced as `32a5bd80…`. See `planning/KNOWN_LIMITATIONS.md`.

The two validator jobs still export a nested `TMPDIR` under the runner temp directory, so
that any tooling with the same assumption behaves predictably.

---

## The 44 planted negative controls

Frozen at Package M0 and enumerated in `docs/…/02_MACHINE_READABLE/negative_controls.json`
(`status: frozen_at_package_m0`). Distribution, re-derived from that file:

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
| **Total** | **44** |

The 8 M0 controls — package pinning, requirement recount, phase boundary, vocabulary
completeness, accounting/CRM/workforce alias leakage and canonical projection parity — are
already satisfied by the pinned package under `/docs`, and the `occurrence-registry` and
`mechanism-suite` jobs exercise that machinery on every run.

Gate-specific controls are planted as each gate is implemented. **Do not plant M1+ controls
at M0R** — there is nothing yet for them to break, and a control that cannot fail is a
false-green by construction.

---

## The rule that governs this file

**When a check fails, fix the thing — never the check.**

If `verify_m0r_skeleton.py` reports a finding, remove what it found. Do not add an
exclusion, do not relax an assertion, do not edit the script. Five review cycles in this
project were lost to validators tuned until they went green.
