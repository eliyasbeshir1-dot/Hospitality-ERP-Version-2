# Hospitality OS — Phase 1

**Gate:** M1 slice A — Database foundation, migration `0001`, RLS
**Predecessor:** M0R — **approved** by independent review at `f53c2c7`
**Pinned package:** `b89a2d4211356be5941dc25ff2dc540728c87ed761ffd9894a3f2691ccf5b590` (v2.0.9 candidate)
**Governing requirement:** FR-GOV-001A

---

## This is not an ERP

The repository is named `Hospitality-ERP-Version-2`, but **Phase 1 is not an ERP.**

Phase 1 is QR dine-in ordering, waiter service, KDS, POS, billing, payments, receipts and
outlet continuity during an internet outage — in English, Amharic and Arabic.

ERP scope — inventory, accounting, purchasing, payroll, recipes, costing, loyalty and CRM —
is explicitly fenced into Phase 2 and Phase 3 by 24 M0R requirements. The repository name
does not widen the scope.

---

## What exists, and what deliberately does not

M0R established a clean baseline and was approved. M1 is sliced into three parts, and only
**slice A** has been executed.

Present now (M1-A): PostgreSQL, migration `0001`, the organizational model, row level
security, and least-privileged production roles.

Still absent, by design:

| Absent | Arrives at |
|---|---|
| Identity, login, sessions, memberships, service principals | M1-B |
| Configuration store, policy store, entitlements | M1-C |
| Audit tables, money and quantity types, seeds, retention | M1-C |
| Menu, QR-bound tables, guest sessions | M2 |
| Orders, tickets, service requests | M3 |
| Checks, payments, tips, receipts | M4 |
| Application routes, workers and UI | M1-B onward |

Permanently absent at every gate: storage locations, inventory, accounting, payroll,
purchasing, supplier, courier, recipes, costing, loyalty, CRM, pickup and delivery.

---

## Repository lineage

| Repository | Role |
|---|---|
| `Hospitality-ERP` | v1.1 — **FROZEN** research and architecture prototype |
| `Hospitality-ERP-Version-2` | v2 — this repository; the M0R target |

The predecessor is frozen. Under **FR-GOV-006** no Phase 1 release is ever cut from its
branches, and under **FR-DAT-001** its migration history is never imported. Any reuse of a
unit from it requires isolated review, dependency analysis, provenance recording and fresh
tests under **FR-GOV-003**. The default position is to write fresh.

---

## Layout

| Path | Contents |
|---|---|
| `docs/` | the approved v2.0.9 package, byte-identical and verified by its own `SHA256SUMS.txt` |
| `migrations/` | ordered, checksum-locked SQL history beginning at `0001` |
| `tests/m1a/` | M1-A verification: fixtures, isolation gates, the four negative controls |
| `planning/` | architecture conformance plan, migration and domain ownership map, CI test matrix, and the known-limitations note that travels with the submission |
| `tools/` | `migrate.py` (SQL-first runner), `bootstrap_database.sql`, `verify_m0r_skeleton.py` |
| `.github/workflows/` | `m0r-conformance.yml` — validators only, no application tests |

Directories that must **not** exist at this gate: `migrations/`, `src/`, `app/`, `db/`,
`database/`, `services/`, `web/`, `pwa/`, `ui/`, and application `tests/`. Creating any of
them at M0R is a P0 finding.

---

## Verification

```bash
# M1-A: rebuilds from an empty database, seeds populated fixtures, runs every gate
bash tests/m1a/run_verification.sh

# The pinned package must stay byte-identical at every gate
cd docs/Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9 && sha256sum -c SHA256SUMS.txt
```

Expected: `PASS M1A_VERIFICATION` and 91/91 OK.

`tools/verify_m0r_skeleton.py` is scoped to M0R and now reports findings for `migrations/`
and the M1 tooling. Those artifacts are legitimate at M1; the script is kept unmodified and
is superseded by an M1 verifier.

**If a check fails, remove what it found — never edit the check.** Five review cycles in
this project were lost to validators tuned until they went green.

---

## Gate sequence

M0 → M0R (approved) → **M1-A (here)** → M1-B → M1-C → M2 → M3 → M4 → M5a → M5b → M6.

Each gate has its own independent review. A gate closes only on behavior provable at that
gate.
