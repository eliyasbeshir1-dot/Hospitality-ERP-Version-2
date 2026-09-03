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
