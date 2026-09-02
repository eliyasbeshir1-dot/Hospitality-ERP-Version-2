<!-- dated-record -->
# Known Limitations — carried into M0R review

**This is a RECORD, not a description.** It says what was found, when, and against which
state of the repository. It is deliberately NOT generated: deriving it from today's tree
would rewrite a finding made on a date into a claim about now, which destroys the evidence
rather than keeping it fresh. What it owes instead is an anchor on every count and gate it
states — see `tools/check_dated_records.py`, which enforces exactly that and which states
the rule for the next person who writes a document here.

Recorded against `f53c2c7` on 26 August 2026.

Disclosed deliberately. None blocked M0R at that commit.

---

## 1. `validate_package_m0.py` is not portable to POSIX

**Found by:** build lead during independent re-verification, 26 August 2026.

Two Windows assumptions:

- `validated_temp_root()` requires `TEMP`/`TMP` to be at least three path components deep.
  `/tmp` is two, so it raises `TEMP is not a safe directory`.
- `GENERATION_MANIFEST.json` stores projection keys with backslash separators
  (`03_HUMAN_READABLE\01_SOURCE_OF_TRUTH.md`), which do not resolve on POSIX.

**Impact:** the package validator runs on Windows and in Codespaces with a nested `TMPDIR`,
but fails on a default Linux path.

**Verified separately:** all 26 generation projections were confirmed by hand with
separators normalised — 26/26 matched, and the content root reproduced as
`32a5bd80ef18f576ae1e61372236615227d880bcfe30da81bf46c1fa7fd9521b`.

**Not a package defect.** Recorded so it is not discovered later and mistaken for one.

---

## 2. Vocabulary detection remains bounded

The occurrence registry closes the **authorization** problem — every occurrence of the
controlled vocabulary is explicitly classified. It does not close the **detection** problem.

A prohibited concept phrased in unknown vocabulary — "wage run" instead of payroll — may go
undetected.

Vocabulary is generated from the phase-boundary exclusion set plus synonyms, morphological
variants and reviewer discoveries. Completeness remains a matter for human review.

**The automated control must not be described as universal semantic understanding.**

---

## 3. Three `.pyc` files in the tooling successor

The combined review noted three compiled-cache files as nonsemantic packaging debris.
Source-only reruns passed 20/20 and 10/10, proving they neither hide nor cause a pass.

Worth removing during the next tooling revision. Not a defect.

---

## 4. Self-validation is not independent approval

The build lead independently re-verified checksums, ran the occurrence validator and the
28-case mechanism suite, and confirmed both findings closed. That is corroboration, not
approval.

M0R approval is Codex's, and the merge decision is the founder's — as recorded at
`f53c2c7` on 26 August 2026.
