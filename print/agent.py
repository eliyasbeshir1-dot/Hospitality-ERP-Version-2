#!/usr/bin/env python3
"""The print agent: verify the font, rasterise, encode, and put it on a sink.

FR-BIL-017's minimum production printer path. A separate component rather than a route in
the API because that is what the package anticipates — FR-AUTH-009 names print agents
among the things that authenticate as scoped service principals — and because rasterising
is not work an HTTP handler should be doing between two database calls.

THE ORDER OF OPERATIONS IS THE POINT.

  1. The vendored font is verified BEFORE anything renders, against the checksum
     print/fonts/PROVENANCE.md records. Absent or altered, this refuses. It does not fall
     back to a host font, and the refusal is the whole reason the check is first: a
     fallback would produce a receipt that looks fine on a machine that happens to have an
     Ethiopic font installed and prints boxes on the one in the outlet.

  2. Chromium rasterises, through print/render.mjs, with that font and no other.

  3. EVERY CHARACTER MUST HAVE BEEN DRAWN BY THE VENDORED FONT. render.mjs reports, per
     character, whether the vendored family drew something the platform's fallback did
     not. One character that it did not draw is ETHIOPIC_FONT_FALLBACK_ON_RECEIPT, and
     nothing is printed. This is NC-M4-005.

  4. Only then are the bytes encoded and written.

THE SINK IS DECIDED BY THE PRINTER, NOT BY THIS FILE. A device sink is a character device
or a socket; a preview sink is a file. 0027 derives which from the connection by CHECK and
gives the two outcomes DIFFERENT TYPES in the database, so a preview cannot be recorded as
a print. Here the same boundary is a refusal to write device bytes at a file, and the two
call sites return different shapes so a caller cannot treat one as the other by accident.

WHAT THIS DOES NOT PROVE, stated here because a reader should meet it rather than infer
it: that a specific contracted printer accepts these bytes. No pilot device is chosen, the
command set is generic ESC/POS, and the only physical proof possible is a print on a real
machine. planning/M4C_LIMITATIONS.md carries that — KNOWN_LIMITATIONS.md is M0R's record
and is left alone — and this docstring is not the only place it is said.

Standard library only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
from console import use_utf8_output  # noqa: E402

# THE FONTS ARE A SET, AND THE SET IS DISCOVERED. FR-I18N-001C names three locales and
# the third is Arabic; no single Noto face covers Ethiopic and Arabic, and the Ethiopic
# face alone drew nothing for any Arabic codepoint — the coverage check caught that,
# which is what it is for. A hardcoded list of two would be a list that goes stale on the
# day a fourth locale arrives, so the fonts are every .ttf in print/fonts/ and
# PROVENANCE.md must record a checksum for each of them by name.
FONT_DIRECTORY = HERE / "fonts"
PROVENANCE = FONT_DIRECTORY / "PROVENANCE.md"
RENDERER = HERE / "render.mjs"

# 80mm paper at 203 dots per inch. A whole number of bytes per row, which escpos.encode()
# requires and refuses without.
DEFAULT_DOTS_WIDE = 576


class PrintRefused(RuntimeError):
    """Nothing was printed, and the reason names what was checked."""


def recorded_font_digests() -> dict[str, str]:
    """The sha256 print/fonts/PROVENANCE.md records, keyed by file name.

    Read from the record rather than written here, so that the agent and the provenance
    cannot disagree: if somebody replaces a font and updates the record, tests/m4c still
    fails, because the suite asserts the record against the files independently. Two
    locks on one fact, from opposite directions.
    """
    if not PROVENANCE.is_file():
        raise PrintRefused(
            f"RECEIPT_FONT_UNPROVENANCED: {PROVENANCE} does not exist, so there is no "
            f"recorded checksum to hold the fonts to. A vendored binary nothing verifies "
            f"is a binary that can change without anybody noticing")
    text = PROVENANCE.read_text(encoding="utf-8")
    # A DIGEST BESIDE A FILE NAME, in one row. Keyed by the file rather than by position,
    # because a record that said "the first checksum is the first font" would be a record
    # that broke the day somebody reordered the table.
    digests = {name: digest for digest, name in re.findall(
        r"`([0-9a-f]{64})`\s*\|\s*`([^`]+\.ttf)`", text)}
    if not digests:
        raise PrintRefused(
            f"RECEIPT_FONT_UNPROVENANCED: {PROVENANCE.name} states no sha256 against a "
            f"file name. Refusing rather than printing with a font nothing vouches for")
    return digests


def verified_fonts() -> list[Path]:
    """Every vendored font, or a refusal. Never a host font.

    DISCOVERED FROM THE DIRECTORY AND CHECKED BOTH WAYS. A font on disk the record does
    not name is a binary nobody reviewed or licensed; a font the record names and the
    directory does not have is a receipt that will print boxes for one script. Either is
    a refusal, and neither can be reached by adding a file or by editing the record alone.
    """
    present = sorted(p for p in FONT_DIRECTORY.glob("*.ttf") if p.is_file())
    if not present:
        raise PrintRefused(
            f"RECEIPT_FONT_ABSENT: {FONT_DIRECTORY} holds no font. This path does NOT "
            f"fall back to a font the operating system happens to provide: a receipt's "
            f"glyphs must not depend on which machine printed it, and a fallback would "
            f"print correctly here and print boxes in an outlet")

    expected = recorded_font_digests()
    unrecorded = [p.name for p in present if p.name not in expected]
    missing = sorted(set(expected) - {p.name for p in present})
    if unrecorded or missing:
        raise PrintRefused(
            f"RECEIPT_FONT_UNPROVENANCED: print/fonts/ and PROVENANCE.md disagree about "
            f"which fonts this path ships. On disk and unrecorded: {unrecorded or 'none'}; "
            f"recorded and absent: {missing or 'none'}")

    for path in present:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected[path.name]:
            raise PrintRefused(
                f"RECEIPT_FONT_ALTERED: {path.name} hashes {digest[:16]}… and "
                f"print/fonts/PROVENANCE.md records {expected[path.name][:16]}…. The font "
                f"that would have drawn this receipt is not the font that was reviewed "
                f"and licensed")
    return present


def rasterise(document: dict, *, dots_wide: int, workspace: Path,
              font: str | None = None) -> dict:
    """Drive Chromium through print/render.mjs and return what it measured.

    THE RENDERER IS COPIED INTO THE WORKSPACE, for the reason tests/m2c copies its probe:
    ES module resolution ignores NODE_PATH, so a renderer left in the repository cannot
    find playwright however the environment is set — and node_modules must never appear in
    the repository.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "print_render.mjs"
    target.write_text(RENDERER.read_text(encoding="utf-8"), encoding="utf-8")
    document_path = workspace / "print_document.json"
    document_path.write_text(json.dumps(document), encoding="utf-8")

    proc = subprocess.run(
        ["node", str(target), str(document_path),
         font or ",".join(str(p) for p in verified_fonts()),
         str(dots_wide)],
        cwd=str(workspace), capture_output=True, text=True, encoding="utf-8")
    if proc.stdout is None or proc.stderr is None:
        raise PrintRefused(
            f"RENDERER_UNREADABLE: the renderer's streams could not be captured "
            f"(exit {proc.returncode}). A probe that could not be read is never 'nothing "
            f"found'")
    try:
        measured = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise PrintRefused(
            f"RENDERER_UNREADABLE: the renderer produced no JSON (exit "
            f"{proc.returncode}): {(proc.stdout or proc.stderr)[:400]}")
    if not measured.get("fontLoaded"):
        raise PrintRefused(
            f"RECEIPT_FONT_ABSENT: the renderer could not load a vendored font: "
            f"{measured.get('fontError', 'no reason given')}")
    return measured


def assert_every_glyph_came_from_the_vendored_font(measured: dict) -> None:
    """NC-M4-005. One character the vendored font did not draw and nothing prints."""
    coverage = measured.get("coverage")
    if not coverage:
        raise PrintRefused(
            "RECEIPT_COVERAGE_UNMEASURED: the renderer reported no characters. Refusing "
            "rather than concluding from an empty set that every glyph is fine — that is "
            "an assertion that cannot fail")
    missing = [c for c in coverage if not c["drawnByTheVendoredFont"]]
    if missing:
        raise PrintRefused(
            "ETHIOPIC_FONT_FALLBACK_ON_RECEIPT: "
            + ", ".join(f"U+{c['codepoint']:04X} {c['character']!r}" for c in missing[:8])
            + (f" and {len(missing) - 8} more" if len(missing) > 8 else "")
            + ". The vendored font drew nothing the platform's own fallback did not, so "
              "these characters are either a substitute glyph from another font or the "
              "renderer's box for a glyph nobody has. A receipt is paper: a customer "
              "cannot ask it to render again")


def write_to_device(payload: bytes, *, device_path: str | None,
                    host_and_port: str | None) -> dict:
    """Bytes at hardware. Returns a DEVICE outcome, which the database types separately."""
    if host_and_port:
        host, _, port = host_and_port.partition(":")
        with socket.create_connection((host, int(port)), timeout=10) as s:
            s.sendall(payload)
        return {"sink": "device", "outcome": "printed", "destination": host_and_port}
    if not device_path:
        raise PrintRefused("PRINTER_DESTINATION_ABSENT: a device sink names neither a "
                           "path nor a host, so there is nowhere to print")

    # A DEVICE SINK MUST BE A DEVICE. Without this, --sink device --device-path /tmp/x
    # writes a file and reports "printed", and docs.print_attempt would record a physical
    # print that never happened — the exact claim the two outcome types exist to make
    # unrepresentable. The database cannot catch it because by then the word has already
    # been chosen; it has to be refused where the bytes are written.
    try:
        mode = os.stat(device_path).st_mode
    except OSError as exc:
        raise PrintRefused(
            f"PRINTER_DESTINATION_ABSENT: {device_path} cannot be opened: {exc}")
    if not stat.S_ISCHR(mode):
        raise PrintRefused(
            f"SINK_MISMATCH: {device_path} is not a character device. Writing a receipt "
            f"into a regular file and calling the outcome 'printed' is the claim "
            f"docs.print_outcome and docs.render_outcome are two types in order to make "
            f"unrepresentable, and a file sink is the preview path — use it by name")

    with open(device_path, "wb") as fh:
        fh.write(payload)
    return {"sink": "device", "outcome": "printed", "destination": device_path}


def write_to_preview(payload: bytes, *, device_path: str) -> dict:
    """Bytes at a file. Returns a PREVIEW outcome — deliberately a different word.

    Nothing here says 'printed', and the database will not accept one of these where a
    print goes: docs.print_outcome and docs.render_outcome are different types with no
    cast between them. This function exists so that the preview path is real and
    exercisable, not so that it can stand in for a print.
    """
    Path(device_path).parent.mkdir(parents=True, exist_ok=True)
    Path(device_path).write_bytes(payload)
    return {"sink": "preview", "outcome": "rendered", "destination": device_path}


def produce(document: dict, *, sink: str, device_path: str | None = None,
            host_and_port: str | None = None, dots_wide: int = DEFAULT_DOTS_WIDE,
            workspace: Path | None = None, font: str | None = None) -> dict:
    """The whole path: verify, rasterise, check coverage, encode, write."""
    from escpos import encode  # noqa: PLC0415 — same directory, imported once used

    workspace = workspace or Path(os.environ.get("M1D_WORKSPACE", "/var/lib/m1d-workspace"))
    verified = font or ",".join(str(p) for p in verified_fonts())
    measured = rasterise(document, dots_wide=dots_wide, workspace=workspace, font=verified)
    assert_every_glyph_came_from_the_vendored_font(measured)

    bits = base64.b64decode(measured["bitsBase64"])
    payload = encode(bits, width_dots=measured["width"], height_dots=measured["height"])

    if sink == "device":
        result = write_to_device(payload, device_path=device_path,
                                 host_and_port=host_and_port)
    elif sink == "preview":
        result = write_to_preview(payload, device_path=device_path or "")
    else:
        raise PrintRefused(
            f"PRINTER_SINK_UNKNOWN: {sink!r}. The two sinks are device and preview and "
            f"there is no third; refusing rather than defaulting to one of them")

    result.update({
        "bytes_sha256": hashlib.sha256(payload).hexdigest(),
        "byte_count": len(payload),
        "width_dots": measured["width"],
        "height_dots": measured["height"],
        "characters_checked": len(measured["coverage"]),
        # ONE DIGEST OVER THE WHOLE SET, in the order the paths were given. Two receipts
        # printed with different fonts must not be able to record the same font digest,
        # and a per-file list would make the record's shape depend on how many locales
        # the build happens to ship.
        "font_set_sha256": hashlib.sha256(
            "\n".join(
                hashlib.sha256(Path(p).read_bytes()).hexdigest()
                for p in verified.split(",")).encode("utf-8")).hexdigest(),
        "fonts": [Path(p).name for p in verified.split(",")],
    })
    return result


def main(argv: list[str] | None = None) -> int:
    use_utf8_output()
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description="Rasterise and print a receipt (FR-BIL-017).")
    parser.add_argument("--document", required=True, type=Path,
                        help="JSON: {\"lines\": [{\"text\": …, \"align\": …}]}")
    parser.add_argument("--sink", required=True, choices=("device", "preview"))
    parser.add_argument("--device-path")
    parser.add_argument("--host-and-port")
    parser.add_argument("--dots-wide", type=int, default=DEFAULT_DOTS_WIDE)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--font-set-under-test", dest="font",
                        help="RENDER WITH A DIFFERENT FONT SET AND SKIP THE CHECKSUM. A "
                             "comma-separated list of paths. Exists for NC-M4-005, which "
                             "proves the coverage check goes red on a real missing glyph "
                             "by rendering an Arabic receipt through the Ethiopic face "
                             "alone — a real .notdef from a real font, needing no planted "
                             "binary and no host path. Named at length so that nothing "
                             "reaches for it by accident: the production path takes no "
                             "font argument and always verifies the vendored set")
    args = parser.parse_args(argv)

    try:
        result = produce(json.loads(args.document.read_text(encoding="utf-8")),
                         sink=args.sink, device_path=args.device_path,
                         host_and_port=args.host_and_port, dots_wide=args.dots_wide,
                         workspace=args.workspace, font=args.font)
    except PrintRefused as refused:
        print(json.dumps({"refused": str(refused)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
