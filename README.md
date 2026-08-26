# Hospitality OS — Phase 1

**Gate:** M0R — Repository Conformance · **awaiting independent review**
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

## There is no application code here, by design

This repository currently contains **documentation and planning artifacts only**. There is:

- no database and no schema
- no migration, including `0001`
- no application route, handler or endpoint
- no worker, job or background process
- no UI component or page
- no `.sql` file and no ORM model

**Their absence is the pass condition of this gate, not a gap.** M0R establishes the clean
baseline before anything can leak into it.

Migration `0001`, PostgreSQL and application code begin at **M1**, and M1 begins only after
independent review approves M0R.

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
| `planning/` | architecture conformance plan, migration and domain ownership map, CI test matrix |
| `tools/` | `verify_m0r_skeleton.py` — forbidden-surface verification |
| `.github/workflows/` | `m0r-conformance.yml` — validators only, no application tests |

Directories that must **not** exist at this gate: `migrations/`, `src/`, `app/`, `db/`,
`database/`, `services/`, `web/`, `pwa/`, `ui/`, and application `tests/`. Creating any of
them at M0R is a P0 finding.

---

## Verification

```bash
python3 tools/verify_m0r_skeleton.py --repo .
cd docs/Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9 && sha256sum -c SHA256SUMS.txt
```

Expected: `PASS M0R_SKELETON` and 91/91 OK.

**If a check fails, remove what it found — never edit the check.** Five review cycles in
this project were lost to validators tuned until they went green.

---

## Gate sequence

M0 → **M0R (here)** → M1 foundation and security → M2 → M3 → M4 → M5a → M5b → M6.

Each gate has its own independent review. A gate closes only on behavior provable at that
gate.
