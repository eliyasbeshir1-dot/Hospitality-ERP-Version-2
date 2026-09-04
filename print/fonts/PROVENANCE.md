# Where these fonts came from, and what they oblige

## The fonts

| | sha256 | file |
|---|---|---|
| Noto Sans Ethiopic 2.102 | `6d66ffc7a4a33f95d56df3c02417083d14f2bfd1f7b4c50ebcdcda3d3f89ea9c` | `NotoSansEthiopic-Regular.ttf` |
| Noto Sans Arabic 2.012 | `146b2193f4aee343a8da5e2295255b04db547d74339a12be51763b3a0081868d` | `NotoSansArabic-Regular.ttf` |

### Noto Sans Ethiopic

| | |
|---|---|
| Family | Noto Sans Ethiopic |
| Version | 2.102 (as the font's own `name` table declares) |
| Copyright | Copyright 2022 The Noto Project Authors (https://github.com/notofonts/ethiopic) |
| Licence | SIL Open Font License 1.1 — `OFL-1.1.txt` beside this file |
| Licence URL | https://scripts.sil.org/OFL (declared by the font itself, name ID 14) |
| Retrieved from | `https://fonts.gstatic.com/s/notosansethiopic/v50/…` , resolved from the Google Fonts CSS API for `Noto Sans Ethiopic:wght@400` |
| Retrieved on | 2026-09-03 |
| Size | 365364 bytes |

### Noto Sans Arabic

| | |
|---|---|
| Family | Noto Sans Arabic |
| Version | 2.012 (as the font's own `name` table declares) |
| Copyright | Copyright 2022 The Noto Project Authors (https://github.com/notofonts/arabic) |
| Licence | SIL Open Font License 1.1 — `OFL-1.1.txt` beside this file |
| Licence URL | https://scripts.sil.org/OFL (declared by the font itself, name ID 14) |
| Retrieved from | `https://fonts.gstatic.com/s/notosansarabic/v33/…` , resolved from the Google Fonts CSS API for `Noto Sans Arabic:wght@400` |
| Retrieved on | 2026-09-04 |
| Size | 192144 bytes |

## Why fonts are in this repository at all

FR-BIL-017 requires a real physical customer receipt, and FR-I18N-001C requires it to
render COMPLETELY in the session language for all three locales — including Ethiopic and
RTL.

**No Ethiopic font exists in the build container or on either CI runner.** A thermal
printer's own font ROM covers code pages, not Ethiopic, so the host has to rasterise; and
a host that resolves the font from whatever the operating system happens to have installed
makes glyph coverage a property of that machine on that day. The two CI runners already
differ from one another.

A receipt's glyphs must not depend on which machine printed it. So the printer path ships
its own fonts, and these are they.

## Why there are two, which was found rather than planned

The first version of this path shipped Noto Sans Ethiopic alone, on the reasoning that
Ethiopic was the script no machine had. That was half the requirement. **Rendering an
Arabic receipt through the Ethiopic face drew every Arabic codepoint from the platform's
fallback** — the coverage check reported the vendored font as having contributed nothing
for each of them, which is exactly what it exists to report. The Ethiopic face covers
Latin, so English and Amharic receipts were correct and the gap was invisible until the
third locale was rasterised.

`print/render.mjs` therefore takes a SET of fonts, registers each under its own family,
and names all of them in one CSS stack, so the browser picks per character. Coverage asks
whether ANY vendored face drew a character, not whether one particular face did.

`print/agent.py` discovers the set from this directory rather than from a list, and checks
it against this record IN BOTH DIRECTIONS: a font on disk this record does not name is a
binary nobody reviewed or licensed, and a font this record names that is not on disk is a
receipt that will print boxes for one script. Either is a refusal.

## What the licence obliges

OFL-1.1 requires the copyright notice and the licence to be included in all copies of the
font software. `OFL-1.1.txt` sits beside the binaries for that reason, the copyright lines
above are each font's own, and the obligation is stated in the repository README as well —
beside the file is where somebody already looking will find it, and the README is where a
reader meets it without looking.

The licence text was extracted verbatim from the `fontTools` distribution's
`LICENSE.external`, which carries the OFL in full, because `scripts.sil.org` and
`openfontlicense.org` are both unreachable from this build environment. It was not
retyped: reproducing a legal text from memory is how a licence comes to say something its
authors did not write.

## What is checked, and where

`tests/m4c` asserts every `sha256` above against the binary beside it on every run. A
provenance record nothing verifies is a description rather than a lock, and a vendored
binary that changes silently is exactly the drift the migration and seed checksum locks
exist to catch. The suite also proves the printer path REFUSES to render when a font is
absent or altered, rather than falling back to a host font that happens to cover the
script — and NC-M4-005 renders an Arabic receipt through the Ethiopic face alone and
requires the coverage check to go red on the resulting `.notdef`.
