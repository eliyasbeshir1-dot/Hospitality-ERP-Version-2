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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

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


def sources_matching(needle: str) -> list[str]:
    """Which files under api/src name a database object, relative to the repository.

    Derived rather than asserted, so a finding that says "no route reads this" stops
    being true the day one does, instead of the day somebody remembers to re-check.
    """
    hits = []
    for source in sorted((REPO / "api" / "src").rglob("*.ts")):
        if needle in source.read_text(encoding="utf-8"):
            hits.append(str(source.relative_to(REPO)))
    return hits


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



# ---------------------------------------------------------------------------
# The other direction: writers no route reaches
# ---------------------------------------------------------------------------
#
# uncalled_routes() asks which doors nobody opens. This asks the sharper question: which
# ROOMS have no door. A delivered writer no route reaches cannot be invoked by any
# surface, any operator or any integration — it exists, it is tested against the
# database, and nothing outside the database can run it.
#
# Read from the migrations rather than from pg_proc so this needs no database: a function
# is VOLATILE unless its own definition says STABLE or IMMUTABLE, which is PostgreSQL's
# rule, and the migrations are the source of truth CI already checksums.

# The whole header, from CREATE FUNCTION to the body marker. VOLATILITY MUST BE READ FROM
# ALL OF IT: PostgreSQL accepts STABLE either before or after LANGUAGE, and a first draft
# stopped at LANGUAGE, called eight readers writers, and disagreed with the catalog it was
# supposed to be a static stand-in for.
_DEFINITION = re.compile(
    r"CREATE(?:\s+OR\s+REPLACE)?\s+FUNCTION\s+([a-z_]+)\.([a-z_][a-z0-9_]*)\s*\("
    r"(.*?)\)\s*RETURNS\s+(.*?)AS\s*\$", re.S | re.I)

# Bodies of triggers and internal assertions are not something an operator calls.
_INTERNAL = re.compile(r"^(assert_|refuse_|apply_[a-z_]*_event$|drop_projections|"
                       r"rebuild_projections|notice_on_|generate_[a-z_]*_document$)")


def unreachable_writers(schema: str) -> dict:
    """Writers in one schema that no route can invoke."""
    routes_text = ""
    for source in sorted((REPO / "api" / "src" / "routes").glob("*.ts")):
        text = source.read_text(encoding="utf-8")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"^\s*\*.*$", "", text, flags=re.M)
        routes_text += re.sub(r"//.*$", "", text, flags=re.M)

    writers: set[str] = set()
    for migration in sorted((REPO / "migrations").glob("*.sql")):
        body = migration.read_text(encoding="utf-8")
        for match in _DEFINITION.finditer(body):
            if match.group(1) != schema:
                continue
            name = match.group(2)
            if _INTERNAL.match(name):
                continue
            # RETURNS trigger is a trigger body; STABLE/IMMUTABLE cannot write.
            declared = match.group(4)
            if re.search(r"\btrigger\b", declared, re.I):
                continue
            if re.search(r"\b(STABLE|IMMUTABLE)\b", declared, re.I):
                writers.discard(name)
                continue
            writers.add(name)

    reachable, unreachable = [], []
    for name in sorted(writers):
        if re.search(r"\b" + schema + r"\." + re.escape(name) + r"\s*\(", routes_text):
            reachable.append(name)
        else:
            unreachable.append(name)
    return {"schema": schema, "reachable": reachable, "unreachable": unreachable}

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
