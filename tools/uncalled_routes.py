#!/usr/bin/env python3
"""Which routes the service exposes that nothing has ever called.

WHY THIS EXISTS. GJ-01A's lesson was that ordering.preview_cart() and
ordering.submit_order() were both proved against the database while no route called
either and no button reached one: every unit check passed and the feature was
unreachable. M4-A shipped ten billing routes the same way. The first HTTP call ever made
to POST /s/v1/checks — made while repairing the journeys, long after the slice closed —
failed on two production defects at once, because nothing had ever called it.

So the question "which routes has nobody called?" is worth asking of the whole service
rather than one slice at a time, and worth deriving rather than remembering. A route with
no caller is not necessarily broken. It is unproved, which is the condition every one of
those defects was hiding in.

WHAT COUNTS AS A CALLER. Any suite, journey, probe or surface that names the path. The
path is matched with its :params replaced by "one non-slash run", so a caller that
interpolates an id is still recognised however it builds the string.

Usage:
    python3 tools/uncalled_routes.py            # the list, and a count
    python3 tools/uncalled_routes.py --json     # the same, for another tool to render
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Not addressable by a caller: the static surface mounts and the index documents.
NOT_A_CALLABLE_ROUTE = re.compile(r"^/$|^/app/\*$|\.html$|^index")

CALLER_GLOBS = ("tests/**/*.py", "tests/**/*.mjs",
                "pwa/**/*.ts", "waiter/**/*.ts", "station/**/*.ts")


def routes() -> list[tuple[str, str, str]]:
    found = []
    for source in sorted((REPO / "api" / "src" / "routes").glob("*.ts")):
        text = source.read_text(encoding="utf-8")
        for match in re.finditer(
                r"\.(get|post|put|patch|delete)\s*(?:<[^>]*>)?\s*\(\s*\n?\s*['\"`]([^'\"`]+)['\"`]",
                text):
            path = match.group(2)
            if NOT_A_CALLABLE_ROUTE.search(path):
                continue
            found.append((match.group(1).upper(), path, source.name))
    if not found:
        raise SystemExit("FAIL ROUTES_UNREADABLE: no route was found in api/src/routes; "
                         "an empty enumeration would report every route uncalled")
    return found


def callers() -> dict[str, str]:
    text: dict[str, str] = {}
    for pattern in CALLER_GLOBS:
        for path in REPO.glob(pattern):
            text[path.relative_to(REPO).as_posix()] = path.read_text(
                encoding="utf-8", errors="replace")
    return text


def survey() -> dict:
    body = callers()
    uncalled, called = [], {}
    for verb, path, source in routes():
        expression = re.sub(r":[A-Za-z][A-Za-z0-9_]*", r"[^/'\"`\\s?]+", re.escape(path))
        rx = re.compile(expression.replace(r"\:", ":"))
        who = sorted(name for name, content in body.items() if rx.search(content))
        if who:
            called[f"{verb} {path}"] = who
        else:
            uncalled.append({"verb": verb, "path": path, "file": source})
    return {"total": len(called) + len(uncalled), "called": len(called),
            "uncalled": uncalled}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    finding = survey()
    if args.json:
        print(json.dumps(finding, indent=2))
        return 0

    print(f"{finding['total']} addressable route(s); {finding['called']} called; "
          f"{len(finding['uncalled'])} never called by any suite, journey or surface")
    by_file: dict[str, list[str]] = {}
    for route in finding["uncalled"]:
        by_file.setdefault(route["file"], []).append(f"{route['verb']} {route['path']}")
    for source in sorted(by_file):
        print(f"\n  {source}")
        for route in sorted(by_file[source]):
            print(f"      {route}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
