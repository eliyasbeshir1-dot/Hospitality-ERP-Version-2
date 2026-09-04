<!-- dated-record -->
# What the printer path does not prove — recorded at M4-C

**This is a RECORD, not a description.** It says what was true of the printer path when it
was built, against the commit it was built at. `planning/KNOWN_LIMITATIONS.md` is M0R's
record and is deliberately left alone; re-dating it to cover M4-C would rewrite a finding
made on one date into a claim about another, which is the rule
`tools/check_dated_records.py` exists to enforce.

Recorded against `463dc83` on 3 September 2026.

Disclosed deliberately. None of these was hidden behind a passing check.

---

## 1. No receipt has been printed on paper

Recorded against `463dc83` on 3 September 2026.

FR-BIL-017 asks for a real physical customer receipt through a supported minimum
production printer path. **No printer exists in the build container or on either CI
runner, and no pilot device has been chosen.**

What is proved instead, and it is the larger half:

- the receipt is composed, snapshotted and rendered to a raster by the printer path's own
  rendering engine;
- every character on it was drawn by the font this repository ships, checked per glyph;
- the raster is encoded into ESC/POS commands and written to a sink;
- a device sink refuses anything that is not a character device, so bytes written into a
  file can never be recorded as a print.

What is **not** proved is the last inch: that a physical machine took those bytes and
produced legible paper. That requires hardware, and it is carried as the open half of
FR-BIL-017 against a gate that has one.

## 2. The command set is generic, so no specific device is proved

Recorded against `463dc83` on 3 September 2026.

`print/escpos.py` emits the commands every ESC/POS implementation documents — initialise,
raster bit image, feed, partial cut — and uses no vendor extension. `docs.printer` records
`command_set` per printer so that the day a device is chosen, the column that has to
change is visible.

**What this does not prove is that a specific contracted printer accepts these bytes.**
Vendors differ in buffer sizes, in which cut commands they honour, and in how they behave
when a raster band exceeds what they can hold. The band size here is 128 rows, chosen to
sit inside every documented buffer, and that is a reasoned choice rather than a measured
one.

## 3. The rasteriser is a browser engine, and that is a constraint M5a must resolve

Recorded against `463dc83` on 3 September 2026.

The receipt is rasterised by Chromium, driven headless through `print/render.mjs`. It was
chosen because it is a real, independent rendering engine that this repository already
requires on both CI platforms, and because the bitmap it produces IS the bitmap that
becomes the printed bytes — so the glyph check inspects the artifact rather than reasoning
from a screen.

**This is recorded as a constraint, not as a decision M5a inherits.** An outlet node
carrying a browser engine in order to print a receipt is heavy, and the outlet node is
M5a's to design. M4-C should not choose M5a's rasteriser from inside the receipts slice.

**If M5a selects a different engine, NC-M4-005 must be run against that engine.** Glyph
coverage is a property of the rasteriser and of the font together; it does not transfer.
A different engine may fall back differently, shape Ethiopic differently, or resolve a
missing glyph from a host font where this one refuses — and the control that catches that
is the one that ran against the engine actually doing the work.

## 4. The licence obligation travels with the font

Recorded against `463dc83` on 3 September 2026.

`print/fonts/` holds Noto Sans Ethiopic under the SIL Open Font License 1.1, with the
licence text and a provenance record beside it. OFL-1.1 requires the copyright notice and
the licence to accompany every copy of the font software, which means every distribution
of this repository or of any artifact built from it that contains the font.

The licence text was extracted verbatim from the `fontTools` distribution's
`LICENSE.external`, because `scripts.sil.org` and `openfontlicense.org` are both
unreachable from this build environment. It was not retyped from memory.

## 5. The fiscal port has one implementation, and it is a simulator

Recorded against `463dc83` on 3 September 2026.

FR-BIL-012 asks for a fiscal-document port and reconciliation status without embedding one
provider's schema, and it names its own trap: an abstraction with one implementation has
nothing to prove it is an abstraction.

What is built: `fiscal.document` is a request against a receipt, a lifecycle, and a
reconciliation status. No column names a provider, a device or a signature format;
`provider_reference` and `provider_payload` are opaque and the platform never parses
either. `fiscal.adapter.mode` is **simulated by CHECK**, not by default, so no adapter can
claim to be live while no Ethiopian fiscal integration is contracted — and the day one is,
that CHECK is the line that must change, visibly, in a migration.

**What this does not prove is that any real provider's contract fits this shape.** A
provider that requires the platform to compute a signature over specific fields, or to
submit before the receipt prints rather than after, or to reconcile per shift rather than
per document, would not fit — and no second implementation exists to have found that out.
The port is a commitment about where the seam goes, not evidence that the seam is in the
right place.

`fiscal.reconciliation()` counts by state and never totals, because the question a
reconciliation answers is which documents are stuck; a single number hides the requested
ones that never went anywhere.


## 6. One font was not enough, and the way that was found is the point

Recorded against `1a73b56` on 4 September 2026.

Sections 1 to 4 above were written when `print/fonts/` held one face. It held one because
NC-M4-005 names Ethiopic, and Ethiopic was the script the control was designed around.
**The Arabic receipt printed boxes.** Nothing in the reasoning caught it; the per-glyph
raster check caught it, on a locale the control was not written for, because the check
reads the bitmap rather than the file list.

So the path takes a font SET rather than a font. `print/agent.py` verifies every face in
`print/fonts/` against `PROVENANCE.md` in both directions — a file with no recorded digest
and a recorded digest with no file each raise `RECEIPT_FONT_UNPROVENANCED` — and passes
the whole set to the renderer as one CSS stack. Section 4's obligation therefore covers
both binaries: `OFL-1.1.txt` accompanies the directory, not a single file, and both faces
are Noto under the same licence.

**What this does not prove is that three locales are all the locales.** The set is
complete for the three this phase supports and for nothing else. A fourth locale is a
fourth face, a fourth provenance row and a fourth run of the coverage check — not a
configuration change, and the reason it is not is section 3: coverage is a property of the
rasteriser and the font together.
