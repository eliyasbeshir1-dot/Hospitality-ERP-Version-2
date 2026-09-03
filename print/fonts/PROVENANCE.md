# Where this font came from, and what it obliges

## The font

| | |
|---|---|
| File | `NotoSansEthiopic-Regular.ttf` |
| Family | Noto Sans Ethiopic |
| Version | 2.102 (as the font's own `name` table declares) |
| Copyright | Copyright 2022 The Noto Project Authors (https://github.com/notofonts/ethiopic) |
| Licence | SIL Open Font License 1.1 — `OFL-1.1.txt` beside this file |
| Licence URL | https://scripts.sil.org/OFL (declared by the font itself, name ID 14) |
| Retrieved from | `https://fonts.gstatic.com/s/notosansethiopic/v50/…` , resolved from the Google Fonts CSS API for `Noto Sans Ethiopic:wght@400` |
| Retrieved on | 2026-09-03 |
| Size | 365364 bytes |
| sha256 | `6d66ffc7a4a33f95d56df3c02417083d14f2bfd1f7b4c50ebcdcda3d3f89ea9c` |

## Why a font is in this repository at all

FR-BIL-017 requires a real physical customer receipt, and FR-I18N-001C requires it to
render COMPLETELY in the session language for all three locales — including Ethiopic.

**No Ethiopic font exists in the build container or on either CI runner.** A thermal
printer's own font ROM covers code pages, not Ethiopic, so the host has to rasterise; and
a host that resolves the font from whatever the operating system happens to have installed
makes glyph coverage a property of that machine on that day. The two CI runners already
differ from one another.

A receipt's glyphs must not depend on which machine printed it. So the printer path ships
its own font, and this is it.

## What the licence obliges

OFL-1.1 requires the copyright notice and the licence to be included in all copies of the
font software. `OFL-1.1.txt` sits beside the binary for that reason, the copyright line
above is the font's own, and the obligation is stated in the repository README as well —
beside the file is where somebody already looking will find it, and the README is where a
reader meets it without looking.

The licence text was extracted verbatim from the `fontTools` distribution's
`LICENSE.external`, which carries the OFL in full, because `scripts.sil.org` and
`openfontlicense.org` are both unreachable from this build environment. It was not
retyped: reproducing a legal text from memory is how a licence comes to say something its
authors did not write.

## What is checked, and where

`tests/m4c` asserts this file's `sha256` against the binary on every run. A provenance
record nothing verifies is a description rather than a lock, and a vendored binary that
changes silently is exactly the drift the migration and seed checksum locks exist to
catch. The suite also proves the printer path REFUSES to render when this file is absent
or altered, rather than falling back to a host font that happens to cover Ethiopic.
