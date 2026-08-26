# Hospitality OS — Phase 1

**Gate:** M1 slice B — Identity, memberships and authentication
**Predecessor:** M1-A — approved at `0d8d580`; M0R approved at `f53c2c7`
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

Present now: PostgreSQL, migrations `0001`–`0002`, the organizational model, row level
security, least-privileged production roles (M1-A), and identity, memberships, sessions,
step-up authentication and service principals (M1-B).

Still absent, by design:

| Absent | Arrives at |
|---|---|
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
| `tests/m1a/` | M1-A verification: fixtures, isolation gates, four negative controls |
| `tests/m1b/` | M1-B verification: identity fixtures, auth gates, four negative controls |
| `planning/` | architecture conformance plan, migration and domain ownership map, CI test matrix, and the known-limitations note that travels with the submission |
| `tools/` | `migrate.py` (SQL-first runner), `bootstrap_database.sql`, `verify_m1.py` (the gate), `verify_m0r_skeleton.py` (superseded, retained as historical evidence) |
| `.github/workflows/` | `m0r-conformance.yml` — validators only, no application tests |

Directories that must **not** exist at this gate: `migrations/`, `src/`, `app/`, `db/`,
`database/`, `services/`, `web/`, `pwa/`, `ui/`, and application `tests/`. Creating any of
them at M0R is a P0 finding.

---

## Verification

```bash
python3 tools/verify_m1.py --repo .        # fenced-domain surface: must be none
bash tests/m1b/run_verification.sh         # rebuilds from empty, runs M1-A then M1-B

# The pinned package must stay byte-identical at every gate
cd docs/Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9 && sha256sum -c SHA256SUMS.txt
```

Expected: `PASS M1_FORBIDDEN_SURFACE`, `PASS M1A_VERIFICATION`, `PASS M1B_VERIFICATION`
and 91/91 OK.

`tools/verify_m0r_skeleton.py` was the M0R gate and is superseded by `tools/verify_m1.py`.
It is kept unmodified as historical evidence and is no longer run: migrations and
application source, which it forbids, are the legitimate work of M1.

**If a check fails, remove what it found — never edit the check.** Five review cycles in
this project were lost to validators tuned until they went green.

---

## Gate sequence

M0 → M0R (approved) → M1-A (approved) → **M1-B (here)** → M1-C → M2 → M3 → M4 → M5a → M5b → M6.

Each gate has its own independent review. A gate closes only on behavior provable at that
gate.
