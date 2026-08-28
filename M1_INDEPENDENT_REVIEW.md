# M1 Independent Review — Resubmission

**Repository:** `Hospitality-ERP-Version-2`
**Reviewed head:** `8e950d96a8dc7f4c61a1cce16ded900dd90548a7` (branch `claude/code-execution-brief-nle2y7`)
**Previous review head:** `f6ee4c0` — returned `M1_FINDINGS_REQUIRE_REPAIR` with three findings
**Reviewer:** independent; did not write this code
**Date:** 2026-08-28

## Verdict: `APPROVE_M1`

All three prior findings are repaired and hold under adversarial testing. The M1 gate as a
whole passes. Unlike the previous review, I was able to **execute** every suite against a
real PostgreSQL 16 instance and drive the live compiled API as a real process, so the
strongest M1 claims are verified by execution, not accepted from the builder's report.

---

## What I executed vs. inspected

**Executed** (local PostgreSQL 16.13 cluster under an unprivileged user, unix socket, trust
auth; Node 22; logs written outside the checkout; tree confirmed clean throughout):

| Suite | Result | Expected | Match |
|---|---|---|---|
| `tools/verify_m1.py` | PASS, 63 terms / 11 domains, 49 files scanned, 92 docs files | PASS 63/11 | ✅ |
| `tests/fenced_gate/verify_fenced_gate.py` | PASS, 33/33 | 33 | ✅ |
| `tests/m1a/verify_m1a.py` | PASS, 36/36 | 36 | ✅ |
| `tests/m1b/verify_m1b.py` | PASS, 33/33 | 33 | ✅ |
| `tests/m1c/verify_m1c.py` | PASS, 53/53 | 53 | ✅ |
| `tests/m1d/verify_m1d.py` | PASS, 45/45 | 45 | ✅ |
| Docs package `sha256sum -c` | 91/91 OK, exactly 92 files | 91/91, 92 files | ✅ |
| Occurrence registry validator | PASS, failure_count 0 | PASS | ✅ |
| Occurrence mechanism suite | 28/28 correct | 28 | ✅ |

**Total: 200 checks across the five M1 suites, 0 failures** — the claimed number is real, and
I counted it from suite output I produced, not from the report. The **19 slice negative
controls** each appear both RED and GREEN in my own logs; the **11 fenced-domain mutations**
each red-then-green. The **63/63 term sweep** passes.

**FR-TST-020 (order independence):** I re-ran all four database suites in reverse order
(`m1d, m1c, m1b, m1a`) on the same database with no rebuild. Identical results — 36/33/53/45,
0 failures each. No suite depends on state another left behind.

**CI run 8:** verified independently through the GitHub API, not the brief. Run
`33048401219` at head `8e950d9`, event `push`, conclusion **success**, **5 jobs all green**,
37 steps in the database job. The four earlier failed runs (4–7) and their progression are
consistent with the repair history described.

**Inspected only:** nothing material was left uninspected. I did not have a Windows machine
(neither did the builder — see deferrals) and Docker was unavailable, but the CI service
container path is exercised by run 8 and my local socket path exercises the same code.

---

## Prior findings — repair verification

### P1-01 — fenced gate now authoritative ✅ REPAIRED

- `tools/verify_m1.py` contains **no fenced literal**. It imports `tests/fenced.py`, which
  loads the 63-term / 11-domain vocabulary from
  `docs/…/02_MACHINE_READABLE/forbidden_surface_rules.json` (the pinned package). Confirmed
  by reading the source and by the gate's own provenance check.
- **`workforce_enabled`** — the exact identifier that leaked before — is now **detected**
  when planted in a migration. I verified this directly.
- I planted terms of **my own** choosing across domains the builder did not pick
  (`payroll_run` in `.ts`, `loyalty-points` in a comment, `goods receipt` in `.py`,
  `stock_level` in a seed). All detected with `FENCED_DOMAIN_SURFACE` findings.
- **Fail-closed under a broken vocabulary source, with a live violation present.** I
  deleted, corrupted (bad JSON), emptied (`{}`), gave the wrong shape (list instead of
  dict), non-string terms, and whitespace-only terms — each while a real
  `workforce_enabled` violation was planted. **Every case refused to scan**
  (`VOCABULARY_UNAVAILABLE` / `VOCABULARY_EMPTY`, exit 1), never passing the violation. This
  is genuinely fail-closed, and it covers more break-shapes than the builder's own suite
  tests.
- **Database-layer backstop.** Beyond the source scan, `verify_m1a.py` (FR-TEN-002B) and
  `verify_m1c.py` (FR-CFG-005B) scan live `information_schema` identifiers against the same
  pinned vocabulary. I planted `config.payroll_run` as a real table and the M1-A gate went
  RED with the exact signature; dropping it restored GREEN.

### P1-02 — evidence report fresh and locked ✅ REPAIRED

- I regenerated `evidence/M1_EVIDENCE_REPORT.md` from **my own** suite logs and the live
  database, on the builder branch (same commit). The result is **byte-identical** to the
  committed report (`diff -q` reports no difference).
- The CI equality lock fires: a tampered copy differs and would fail the build.
- The `SUITE_LOG_MISSING` guard fires: with `m1d.log` removed, the generator **refuses**
  (exit 1, writes no report) rather than emitting a "not run" row — the exact defect that
  once produced 167 instead of 200. The committed report totals **200** with no false suite
  rows.

### P2-01 — README generated and locked ✅ REPAIRED

- `tools/generate_readme.py --check` passes on the committed README (136 lines verified
  against repository state).
- The drift lock fires: I mutated the README and `--check` failed with `README_DRIFT` and a
  diff; reverting restored the pass.

---

## Attack results (brief §"Attack these first")

1. **Fenced gate authoritative** — yes (see P1-01). Fail-closed proven under six distinct
   source-break shapes with a live violation present.
2. **30 controls genuinely fail** — I independently planted my own defects, not the
   builder's: a permissive `FOR SELECT USING(true)` policy (→
   `VISIBLE_OR_WRITABLE_ROWS_WITHOUT_CONTEXT`, matched on 6 real seeded rows, not a vacuous
   empty table), a `float8` money column (→ `INEXACT_MONEY_TYPE_ACCEPTED`), and audit
   mutation attempts. Each produced its exact registered signature; revert restored green.
   All 19 controls red-then-green in my run; all 11 fenced mutations too.
3. **RLS at the API layer** — held on the **live compiled API** across every probe:
   - Genuine Habesha token sees **only** Habesha's tenant and **only** outlet OUT-H1 (sibling
     OUT-H2 hidden) — outlet-level scoping confirmed at HTTP.
   - **Forged prefix refused** three ways: Habesha secret + Nile tenant prefix → 401;
     Habesha secret + sibling-outlet H2 prefix → 401; Nile secret + Habesha prefix → 401.
     The token digest binds tenant and outlet, so a re-labelled prefix finds no session.
   - **Cross-tenant on a write verb:** a Habesha token calling
     `DELETE /v1/sessions/{a Nile session id}` returned `{"revoked":0}` and the Nile session
     stayed unrevoked — RLS matched zero rows. Not only GET is protected.
   - **All 8 protected routes** answer 401 with no/malformed context; only `/health`,
     `/ready`, `/metrics` are public. **No context-free fallback** (NC-M1D-006 holds).
4. **Deferrals honest** — `/ready` emits `rateLimiting.scope: "singleInstance"` with a note
   that distributed enforcement is deferred to M6; no check claims distributed enforcement.
   Windows is documented as **"Not verified on Windows"** in both
   `docs-local/CROSS_PLATFORM_COMMANDS.md` and the evidence report; no check asserts a
   Windows run. CSRF is defined but there is **no cookie-auth route** — the guard only
   engages when a cookie is present without an Authorization header, and nothing sets or
   reads an auth cookie.
5. **CI locks fire** — README drift, evidence inequality, and `SUITE_LOG_MISSING` all
   demonstrated above.

---

## Specific items confirmed (brief §"Specific items")

- **Money exactness.** No `float4`/`float8`/`double precision`/`real` column exists in any
  non-system schema (introspected `pg_attribute`), and none appears in migration source.
  `amount_minor` is `bigint`; `money.assert_currency_paired()` structurally requires a
  `currency_code` beside every amount column. `money.allocate(total, n)` returns exact parts:
  I checked `100→[34,33,33]`, `10→[3,3,2,2]`, `1→[1,0,0]`, `10¹²→7 parts` — every case sums
  to **exactly** the total (largest-remainder; no minor unit lost or created). The 2⁵³+1
  case: `9007199254740993` survives a bigint round-trip and fails a float8 round-trip, as
  claimed.
- **Audit append-only by trigger, not merely grant.** The `refuse_mutation()` trigger on
  `audit.operational_event` / `audit.security_event` refused UPDATE and DELETE even for a
  **superuser** and even after I explicitly `GRANT UPDATE, DELETE … TO hospitality_app`.
  TRUNCATE is refused too (`APPEND_ONLY_VIOLATED`). The grant alone is not the enforcement.
- **Privileged credential refusal at process level.** Starting the compiled service under
  the superuser, the owner (migrator), and the BYPASSRLS role each **exited 78 with no
  listener** (`STARTUP REFUSED — … has BYPASSRLS — refusing to start`). It starts and serves
  only under the least-privileged `hospitality_app` role.
- **Readiness truthfulness.** Revoking `SELECT ON config.retention_policy` from the app role
  flipped `/ready` from 200 to **503** naming `retention-sweep`; restoring the grant flipped
  it back to 200. Readiness does real work, not a static claim.
- **Migration discipline.** History rooted at `0001`; four applied migrations whose stored
  checksums (`5aef8924…`, `51446d59…`, `fe4ef998…`, `1f01ff0d…`) match the on-disk file
  hashes exactly — `0001` is unedited. Editing an applied migration is refused with
  `MIGRATION_CHECKSUM_MISMATCH`. `0004` exists (not an edit to `0001`) precisely because
  `0001` revoked the app role's access to the migration history and readiness could not
  verify provenance; `0004` adds a **SELECT-only** grant, and the app role still cannot
  INSERT/UPDATE/DELETE a migration row (I confirmed `permission denied`), so it cannot forge
  provenance. No v1.1 history references in code.
- **Seed lock.** Seeds are a separate ordered, checksum-locked history under
  `seed_history.applied_seed` run by `tools/seed.py`, distinct from migrations. Editing an
  applied seed is refused (`SEED_CHECKSUM_MISMATCH`, exit 1). NC-M1D-005 additionally proves
  the runner cannot be bypassed.

## Accepted exceptions (confirmed implemented, not re-litigated)

1. `money.currency` has **no RLS** (`relrowsecurity = false`) and the runtime role holds
   **SELECT only** — INSERT is `permission denied`. ✅
2. `money.allocate()` exists at M1 and is exact (above). ✅
3. `identity.governed_action` lives in the `identity` schema, referenced by configuration
   via foreign key. ✅
4. The Node build writes `node_modules/`+`dist/` outside the repository; the tree stayed
   clean at every moment of my run. ✅

## M2+ absence

No menu, order, check, payment, tip, receipt, invoice, or KDS/kitchen tables exist
(introspected). Their absence is correct for M1.

---

## Observations (not findings; nothing blocks approval)

- **Source-scan fenced gate coverage is narrower than the DB-layer gate.** `verify_m1.py`'s
  prose/source scan only covers a fixed extension set (no `.sh`), exempts governance files,
  and — matching whole identifier components — will not flag a fenced term fused in
  camelCase without a separator (`inventoryCount`). This is acceptable because the
  *authoritative* enforcement of "no fenced-domain entity" is the database identifier gate
  (FR-TEN-002B / FR-CFG-005B), which I proved catches a live `payroll_run` table; the source
  scan is a secondary prose check over application surface. Worth keeping in mind if a future
  slice adds shell-based application logic.
- The process-level refusal log line reuses the negative-control signature string
  `PRIVILEGED_RUNTIME_CREDENTIAL_ACCEPTED` inside the *refusal* message, which reads slightly
  oddly (it is the name of the thing being prevented). Behavior is correct; purely cosmetic.

---

## Statement of method

I executed every suite and the live API myself against a real PostgreSQL 16 instance. Where
the brief asked me to attack, I planted my own defects and broke the vocabulary source in
ways the builder's suite does not, and I drove the compiled API as a real process for the
RLS probes rather than reading the harness. CI run 8's green status was verified through the
GitHub API. The working tree was clean before and after; all mutations were reverted or
confined to a scratch directory. Founder adjudication under §9.1 remains available and is
not what this document is.

**Verdict: `APPROVE_M1` — M2 may begin.**
