#!/usr/bin/env python3
"""ESC/POS raster encoding: a bitmap in, printer bytes out.

GENERIC ESC/POS, against the published command set, because no pilot printer has been
chosen. That is a real limitation and it is stated rather than hidden: this encodes the
commands every ESC/POS implementation documents — initialise, raster bit image, feed,
cut — and uses no vendor extension. What it CANNOT prove is that a specific contracted
device accepts these bytes, and planning/KNOWN_LIMITATIONS.md says so in those words.

WHY RASTER MODE AND NOT TEXT MODE. A thermal printer's built-in fonts are code pages:
Latin, a handful of European and Asian sets, and nothing for Ethiopic. An Amharic receipt
sent as text would print as the printer's substitute for characters it does not have —
which is the defect NC-M4-005 exists to catch, arriving from the other direction. So the
host rasterises and sends dots, and the printer's font ROM is never consulted.

Standard library only, and no I/O: this module turns a bitmap into bytes and nothing else.
The sink is print/agent.py's, so that the encoding can be exercised without a device and
so that the two-types boundary between a device and a file lives in one place.
"""
from __future__ import annotations

# The commands, named. A byte string in the middle of a function is a magic number that
# nobody can review; these are what the published command set calls them.
ESC = 0x1B
GS = 0x1D

INITIALISE = bytes([ESC, 0x40])            # ESC @  — reset to a known state
RASTER_BIT_IMAGE = bytes([GS, 0x76, 0x30])  # GS v 0 — raster bit image follows
NORMAL_DENSITY = bytes([0x00])              # m = 0  — no doubling in either axis
PARTIAL_CUT = bytes([GS, 0x56, 0x42, 0x00])  # GS V 66 0 — cut, leaving a tab

# A band is a run of rows sent in one raster command. Real devices have a finite input
# buffer and a tall receipt sent as one command overruns it — the visible symptom is a
# receipt that stops half way, which on paper is indistinguishable from a paper jam. 128
# rows is comfortably inside every documented buffer and is why this loops at all.
BAND_ROWS = 128


class RasterInvalid(ValueError):
    """The bitmap cannot be encoded, so nothing is emitted."""


def encode(bits: bytes, *, width_dots: int, height_dots: int, feed_lines: int = 4,
           cut: bool = True) -> bytes:
    """Wrap a 1-bit-per-dot bitmap in the ESC/POS commands that print it.

    `bits` is row-major, MSB first, each row padded to a whole byte — the order the
    raster command itself defines, which is why print/render.mjs packs it that way rather
    than converting here.
    """
    if width_dots <= 0 or width_dots % 8 != 0:
        raise RasterInvalid(
            f"width {width_dots} is not a positive whole number of bytes. A row that does "
            f"not divide by eight would lose its right-hand edge silently, and a receipt "
            f"missing its last column is a receipt with the total cut off")
    if height_dots <= 0:
        raise RasterInvalid(f"height {height_dots} is not positive; there is nothing to print")

    row_bytes = width_dots // 8
    expected = row_bytes * height_dots
    if len(bits) != expected:
        raise RasterInvalid(
            f"the bitmap is {len(bits)} bytes and {width_dots}x{height_dots} needs "
            f"{expected}. Refusing rather than padding: a short buffer padded with zeroes "
            f"prints a receipt that is silently truncated, and a customer cannot tell "
            f"that from one that ended there")

    out = bytearray(INITIALISE)
    for top in range(0, height_dots, BAND_ROWS):
        rows = min(BAND_ROWS, height_dots - top)
        out += RASTER_BIT_IMAGE
        out += NORMAL_DENSITY
        out += bytes([row_bytes & 0xFF, (row_bytes >> 8) & 0xFF])
        out += bytes([rows & 0xFF, (rows >> 8) & 0xFF])
        out += bits[top * row_bytes:(top + rows) * row_bytes]

    if feed_lines:
        out += bytes([ESC, 0x64, feed_lines & 0xFF])   # ESC d n — feed n lines
    if cut:
        out += PARTIAL_CUT
    return bytes(out)


def describe(payload: bytes) -> dict:
    """What is in an encoded stream, for a diagnostic that names what it saw.

    Used by tests/m4c to assert the shape of the bytes rather than their digest alone: a
    digest proves two runs agree and says nothing about whether either is a receipt.
    """
    return {
        "bytes": len(payload),
        "initialised": payload.startswith(INITIALISE),
        "raster_commands": payload.count(RASTER_BIT_IMAGE),
        "cut": payload.endswith(PARTIAL_CUT),
    }
