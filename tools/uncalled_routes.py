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

WHAT COUNTS AS A CALLER. A call expression that carries both a verb and a path: a
request helper invoked as (method, path), an attribute call whose name is the verb, or a
surface's fetch(). Naming a path in prose, in a comment, or in a string that goes nowhere
is not a call, and a caller of one verb does not credit another verb on the same path.
The route's path must match the caller's in full, not as a prefix.

Usage:
    python3 tools/uncalled_routes.py            # the list, and a count
    python3 tools/uncalled_routes.py --json     # the same, for another tool to render
"""
from __future__ import annotations

import argparse
import ast
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

# Every place a request can come from. The till joined at OP-B, and it had to be added
# here: a surface the census does not read is a surface whose routes read as uncalled,
# which is the census understating coverage rather than overstating it — the safer
# direction, and still wrong.
CALLER_GLOBS = ("tests/**/*.py", "tests/**/*.mjs",
                "pwa/**/*.ts", "waiter/**/*.ts", "station/**/*.ts",
                "cashier/**/*.ts")


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

        # THE DOCUMENT ROUTES ARE REGISTERED FROM A TABLE, AND THE TABLE IS THE CATALOG.
        #
        # surface.ts used to register '/', '/station' and '/waiter' as three literal
        # app.get() calls, which the pattern above reads. OP-B replaced them with a loop
        # over SURFACE_DOCUMENTS so the security layer could derive the same list instead
        # of restating it — and that refactor made this census blind to every one of them.
        # The total stayed at 108 by coincidence, two new billing routes arriving as two
        # document routes disappeared, which is exactly how a miscount hides.
        #
        # So the census reads the table too. One list still: the server registers from it,
        # the content-security-policy is derived from it, and the census counts it.
        for match in re.finditer(r"\[\s*'([^']+)'\s*,\s*'[^']*\.html'\s*\]", text):
            path = match.group(1)
            if not NOT_A_CALLABLE_ROUTE.search(path):
                found.append(("GET", path, source.name))
    if not found:
        raise SystemExit("FAIL ROUTES_UNREADABLE: no route was found in api/src/routes; "
                         "an empty enumeration would report every route uncalled")
    return found


_TS_TOKENS = re.compile(
    r"//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`",
    re.S)

_VERBS = ("GET", "POST", "PUT", "PATCH", "DELETE")

# A helper may carry the verb in its own name rather than in an argument: station_get(),
# guest_post(), staff_get(). The path is then the first argument.
_NAMED_VERB = re.compile(r"^(?:[a-z_]+_)?(get|post|put|patch|delete)$")

# An interpolation stands for one path segment. Both readers below substitute this for
# whatever the caller interpolated, so f"/s/v1/orders/{oid}/accept" and
# `/c/v1/${tenant}/${outlet}/session` stay comparable to a declared route.
PARAM = "\x00PARAM\x00"


class CallSite:
    """One request a caller actually issues: a verb, a path, and where it is written."""

    __slots__ = ("verb", "path", "file", "line")

    def __init__(self, verb: str, path: str, file: str, line: int):
        self.verb, self.path, self.file, self.line = verb, path, file, line

    @property
    def target(self) -> str:
        """The path without the caller's query string or fragment."""
        return self.path.split("?")[0].split("#")[0]


def _literal(node):
    """One string an expression can be, if it is written out."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value if isinstance(part, ast.Constant) and isinstance(part.value, str)
            else PARAM for part in node.values)
    return None


def _bindings(tree: ast.AST) -> dict:
    """Every string a name can hold, for names bound to written-out strings.

    Paths are not always passed inline. m1d holds seven of them in a list and sweeps
    every verb across it; other suites build a path into a local and pass the local. A
    reader that only sees inline arguments calls those routes uncalled, which is the
    error that invents work, so the names are followed one step.

    Deliberately not scope-aware. Over-following can only credit a route that some line
    in the file really does name; under-following reports a called route as uncalled.
    """
    bound: dict = {}
    holds: dict = {}

    def elements(node):
        if isinstance(node, (ast.List, ast.Tuple)):
            return [text for text in (_literal(item) for item in node.elts) if text]
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            items = elements(node.value)
            if items is not None:
                holds.setdefault(target.id, []).extend(items)
            else:
                bound.setdefault(target.id, []).extend(
                    _candidates(node.value, bound))

    # for path in protected:  /  for method in ("GET", "POST"):
    for node in ast.walk(tree):
        if not isinstance(node, ast.For) or not isinstance(node.target, ast.Name):
            continue
        items = elements(node.iter)
        if items is None and isinstance(node.iter, ast.Name):
            items = holds.get(node.iter.id)
        if items:
            bound.setdefault(node.target.id, []).extend(items)
    return bound


def _candidates(node, bound: dict) -> list:
    """Every string this expression could be. Empty when it cannot be read."""
    text = _literal(node)
    if text is not None:
        return [text]
    if isinstance(node, ast.Name):
        return list(dict.fromkeys(bound.get(node.id, [])))
    if isinstance(node, ast.IfExp):
        # "/c/v1/orders" if guest else "/s/v1/orders" -- one caller, two routes, and
        # both are really requested depending on which channel the suite is driving.
        return list(dict.fromkeys(_candidates(node.body, bound)
                                  + _candidates(node.orelse, bound)))
    return []


def _python_call_sites(source: str, name: str):
    """Every HTTP request a Python caller issues, read from its call expressions.

    THE DEFECT THIS CLOSES, the second this census has had. The reader before this one
    kept the contents of every string literal, threw the code away, and asked whether a
    route's PATH appeared anywhere in what was left. That answers a weaker question than
    the census is for, in three ways that all inflate the count:

      * It could not see the verb. GET /s/v1/checks and POST /s/v1/checks are two routes
        with two handlers; a suite calling either credited both. Four paths carry two
        verbs, and GET /s/v1/checks turned out to be one nothing had ever called.
      * It matched a path as a SUBSTRING. Fifteen route paths are a strict prefix of
        another, so every caller of POST /s/v1/receipts/:id/prints also credited
        GET /s/v1/receipts/:id, which nothing had ever called.
      * It could not tell a request from a QUOTATION of the service's own source. M4-A
        asserts on the text of the handovers route, and those two quoted lines were the
        only thing crediting GET and POST /s/v1/handovers.

    A string standing on its own is not evidence of a request; a verb and a path passed
    to a call is. Every request helper here takes (method, path) as its first two
    arguments -- service(), call(), staff(), kitchen(), guest(), guest_call(),
    self.request() -- or carries the verb in its own name, as station_get("/s/v1/...")
    and service.get("/ready") do. All three shapes are read here, and nothing else counts.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []

    bound = _bindings(tree)
    sites, unresolved = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue

        verbs = [v.upper() for v in _candidates(node.args[0], bound)
                 if v.upper() in _VERBS]
        if verbs and len(node.args) >= 2:
            paths = _candidates(node.args[1], bound)
            unreadable = not paths
        else:
            callee = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else "")
            named = _NAMED_VERB.match(callee or "")
            if not named:
                continue
            verbs = [named.group(1).upper()]
            paths = [p for p in _candidates(node.args[0], bound) if p.startswith("/")]
            # answer.get("reason") is not a request. Only a path argument makes it one,
            # so an unreadable argument here is silence rather than a missing caller.
            unreadable = False

        if unreadable:
            unresolved.append(
                f"{name}:{node.lineno} {'|'.join(verbs)} <path built at runtime>")
        for verb in verbs:
            for path in paths:
                if path.startswith("/"):
                    sites.append(CallSite(verb, path, name, node.lineno))
    return sites, unresolved


def _blank_ts_comments(source: str) -> str:
    """The file with comments blanked and offsets preserved; strings left alone."""
    out = list(source)
    for token in _TS_TOKENS.finditer(source):
        if token.group(0)[:2] in ("//", "/*"):
            for i in range(token.start(), token.end()):
                if out[i] != "\n":
                    out[i] = " "
    return "".join(out)


_TS_REQUEST = re.compile(
    r"\b(fetch|goto)\s*\(\s*(['\"`])((?:\\.|(?!\2).)*)\2", re.S)
_TS_LOOSE = re.compile(r"\b(?:fetch|goto)\s*\(\s*([A-Za-z_$][\w$.]*)\s*[,)]")
_TS_METHOD = re.compile(r"\bmethod\s*:\s*['\"`]([A-Za-z]+)['\"`]")

# A SURFACE'S OWN REQUEST HELPER: helper('VERB', '/path') or helper('VERB', `/path/${x}`).
#
# Not one of the four surfaces calls fetch() with a literal path for its API traffic.
# Every one wraps it — waiterApi('GET', '/s/v1/home'), api('POST', '/s/v1/bills', …),
# stationApi(…), act(…) — and inside the wrapper the argument to fetch() is a VARIABLE,
# which _TS_REQUEST correctly refuses to guess at. So every surface call landed in
# `unresolved` and no route looked reachable from a screen.
#
# That did not matter while "called" pooled suites and surfaces: the Python readers saw
# the suites and the count answered the question being asked. It matters the moment the
# question becomes "can a PERSON reach this" — a reachability number built on a reader
# that cannot see a single surface call would have reported 15 of 117 and been worse than
# no number at all.
#
# The shape read here is the one _python_call_sites() has always read: a call whose first
# two arguments are a verb and a path. Deliberately NOT "any function that eventually
# reaches fetch" — that needs call-graph analysis, and a census that guesses is the defect
# this file has already been repaired for twice.
_TS_HELPER = re.compile(
    r"\b[A-Za-z_$][\w$.]*\s*\(\s*(['\"])([A-Za-z]+)\1\s*,\s*"
    r"(['\"`])((?:\\.|(?!\3).)*)\3", re.S)


def _path_of(url: str) -> str:
    """The path part of a URL a surface names, or "" if it names no path.

    A probe navigates to `${baseUrl}/station`, so the origin has to come off before the
    path can be compared to a route. An interpolation in origin position is one.
    """
    if url.startswith(PARAM):
        url = url[len(PARAM):]
    else:
        scheme = re.match(r"[a-z][a-z0-9+.-]*://[^/]*", url, re.I)
        if scheme:
            url = url[scheme.end():]
        elif ":" in url.split("/")[0]:
            return ""  # about:blank, data:, mailto:
    return url if url.startswith("/") else ""


def _ts_call_sites(source: str, name: str):
    """Every request a browser surface issues: fetch(), and navigation.

    There is no TypeScript parser available, so the verb is read from the options object
    after the URL, brace-matched rather than window-scanned so a nested object cannot
    leak one fetch's method into another's. fetch() with no method is GET, which is the
    web platform's default rather than a guess, and a navigation is always a GET.
    page.route() is Playwright intercepting a request, not issuing one, and route.fetch()
    replays whatever was intercepted; neither names a route here.
    """
    text = _blank_ts_comments(source)
    sites, unresolved = [], []
    for match in _TS_REQUEST.finditer(text):
        path = _path_of(re.sub(r"\$\{[^{}]*\}", PARAM, match.group(3)))
        if not path:
            continue
        verb, depth, i, opts = "GET", 0, match.end(), ""
        if match.group(1) == "fetch":
            while i < len(text):
                char = text[i]
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        opts = text[match.end():i]
                        break
                elif char == ")" and depth == 0:
                    break
                i += 1
            found = _TS_METHOD.search(opts)
            if found:
                verb = found.group(1).upper()
        sites.append(CallSite(verb, path, name, text.count("\n", 0, match.start()) + 1))
    # The surfaces' own request helpers. See the note on _TS_HELPER: this is the only way
    # any of the four screens is visible to this census at all.
    for match in _TS_HELPER.finditer(text):
        verb = match.group(2).upper()
        if verb not in _VERBS:
            continue
        path = _path_of(re.sub(r"\$\{[^{}]*\}", PARAM, match.group(4)))
        if not path:
            continue
        sites.append(CallSite(verb, path, name, text.count("\n", 0, match.start()) + 1))

    for match in _TS_LOOSE.finditer(text):
        unresolved.append(f"{name} {match.group(1)} <path built at runtime>")
    return sites, unresolved


def call_sites():
    """Every request every caller in the repository issues."""
    sites, unresolved = [], []
    for pattern in CALLER_GLOBS:
        for path in sorted(REPO.glob(pattern)):
            name = path.relative_to(REPO).as_posix()
            source = path.read_text(encoding="utf-8", errors="replace")
            read = _python_call_sites if path.suffix == ".py" else _ts_call_sites
            found, missed = read(source, name)
            sites.extend(found)
            unresolved.extend(missed)
    if not sites:
        raise SystemExit("FAIL CALLERS_UNREADABLE: no caller was found; an empty "
                         "enumeration would report every route uncalled")
    return sites, unresolved


def sources_matching(needle: str) -> list:
    """Which files under api/src name a database object, relative to the repository.

    Derived rather than asserted, so a finding that says "no route reads this" stops
    being true the day one does, instead of the day somebody remembers to re-check.
    """
    hits = []
    for source in sorted((REPO / "api" / "src").rglob("*.ts")):
        if needle in source.read_text(encoding="utf-8"):
            # POSIX, ALWAYS. This is rendered into planning/M4_REVIEW_FINDINGS.md, which
            # CI regenerates and diffs against the committed copy, so a Windows separator
            # here is a failure with no defect behind it. It stayed hidden until OP-A
            # added the first file this function has ever matched: for as long as the
            # answer was an empty list, the platform could not show through it.
            hits.append(source.relative_to(REPO).as_posix())
    return hits


def _matcher(path: str):
    """A route path as a pattern a caller's path must match in FULL.

    Anchored, because a substring match credits every route whose path is a prefix of a
    longer one. ":param" matches one segment, and so does the placeholder standing for a
    caller's interpolation: a caller cannot interpolate a slash into a single segment
    without the route being a different route.
    """
    expression = re.escape(path)
    expression = re.sub(r"(?:\\)?:[A-Za-z][A-Za-z0-9_]*", "[^/]+", expression)
    expression = expression.replace(re.escape(PARAM), "[^/]+")
    expression = expression.replace(r"\*", "[^/]*")
    return re.compile(expression + r"/?\Z")


def self_test() -> list:
    """The three properties this reader was repaired to have, proved on known inputs.

    A census is a measuring instrument, and the two defects it has carried were both
    invisible in its own output: the number looked reasonable while it was counting a
    quoted line of the service's own source as a caller. So the instrument is checked
    against cases whose answer is known, and each case is written to FAIL under the
    reader that preceded this one.
    """
    def called(route_verb, route_path, source, suffix=".py"):
        read = _python_call_sites if suffix == ".py" else _ts_call_sites
        sites, _ = read(source, "probe")
        rx = _matcher(route_path)
        return any(s.verb == route_verb and rx.fullmatch(s.target) for s in sites)

    checks = [
        ("a POST caller does not credit the GET on the same path",
         not called("GET", "/x", 'call("POST", "/x")')),
        ("a caller of a longer path does not credit its prefix",
         not called("POST", "/x", 'call("POST", "/x/1/y")')),
        ("quoting the service's own source is not calling it",
         not called("GET", "/x", 'assert lines == ["  app.get(\'/x\', handler)"]')),
        ("a path named only in a comment is not a call",
         not called("GET", "/x", '# the /x route is served by api.ts\npass')),
        ("a helper called as (method, path) is a call",
         called("POST", "/x", 'call("POST", "/x")')),
        ("a helper carrying the verb in its name is a call",
         called("GET", "/x", 'station_get("/x")')),
        ("an interpolated segment still matches its parameter",
         called("POST", "/x/:id/y", 'call("POST", f"/x/{oid}/y")')),
        ("a path held in a list and swept by verb is a call",
         called("GET", "/x", 'P = ["/x"]\nfor p in P:\n    call("GET", p)')),
        ("a surface's fetch is a call, with its declared method",
         called("PUT", "/x", "fetch('/x', { method: 'PUT' })", ".ts")),
        ("a surface's fetch with no method is a GET",
         called("GET", "/x", "fetch('/x')", ".ts")),
        ("a nested object cannot leak its method into the fetch above it",
         not called("POST", "/x", "fetch('/x', { headers: { a: 1 } });"
                                  "\nsend({ method: 'POST' })", ".ts")),
        ("navigating to a surface is a call to it",
         called("GET", "/station", "page.goto(`${baseUrl}/station`)", ".ts")),

        # OP-D. The shape every surface actually uses, and the shape that made the
        # reachability split possible. Each of these was written to FAIL under the reader
        # that preceded it, which saw only fetch() with a literal path.
        ("a surface's request helper is a call, with the verb it names",
         called("GET", "/s/v1/home", "waiterApi('GET', '/s/v1/home')", ".ts")),
        ("and an interpolated segment in a helper call still matches its parameter",
         called("POST", "/s/v1/orders/:orderId/accept",
                "waiterApi('POST', `/s/v1/orders/${id}/accept`, {})", ".ts")),
        ("a helper's verb is read from the argument, not assumed",
         not called("GET", "/s/v1/home", "waiterApi('POST', '/s/v1/home')", ".ts")),
        ("a two-string call whose first argument is not a verb is not a request",
         not called("GET", "/s/v1/home",
                    "translate('label', '/s/v1/home')", ".ts")),
    ]
    return [(name, ok) for name, ok in checks]


# WHICH CALLERS ARE A PERSON, AND WHICH ARE A SUITE.
#
# THIS SPLIT IS THE POINT OF THE INSTRUMENT AND IT DID NOT EXIST FOR THREE GATES.
#
# The census pooled its callers: tests/** and the four surfaces went into one "called"
# count, so it answered "does anything call this route" and never "can a person reach it".
# A route driven only by a suite was indistinguishable from one a cook presses.
#
# Twice that hid the same defect, and the second time it hid it in plain sight.
# POST /s/v1/orders/:orderId/accept — the step without which no guest order reaches a
# kitchen under staff_confirmed — was called by tests/journeys and tests/opa and by NO
# SURFACE AT ALL, and the census reported it green. F-OPB-9 had already named the shape:
# "no amount of adding tests of this shape would have caught it." The instrument that was
# supposed to find such things was averaging them away.
#
# So a route is now REACHABLE when a surface calls it and PROVED when a suite does, and
# the two numbers are reported separately. A route that is proved and unreachable is the
# interesting one: it works, it is tested, and nobody can get to it.
SURFACE_ROOTS = ("pwa/", "waiter/", "station/", "cashier/")


def _is_surface(relative_path: str) -> bool:
    """Whether a call site is a screen a person uses, rather than a suite."""
    return relative_path.startswith(SURFACE_ROOTS)


def survey() -> dict:
    sites, unresolved = call_sites()
    uncalled, called = [], {}
    unreachable = []
    reachable = 0
    for verb, path, source in routes():
        rx = _matcher(path)
        who = sorted({site.file for site in sites
                      if site.verb == verb and rx.fullmatch(site.target)})
        surfaces = [f for f in who if _is_surface(f)]
        if who:
            called[f"{verb} {path}"] = who
        else:
            uncalled.append({"verb": verb, "path": path, "file": source})
        if surfaces:
            reachable += 1
        elif who:
            # Called by a suite and by no screen. Not a defect on its own — an operator
            # route or an integration endpoint has no surface by design — but it is the
            # set every "the tests pass and a person cannot" finding has come out of, so
            # it is named rather than counted.
            unreachable.append({"verb": verb, "path": path, "file": source,
                                "proved_by": who})
    return {"total": len(called) + len(uncalled), "called": len(called),
            "uncalled": uncalled, "unresolved": sorted(set(unresolved)),
            "call_sites": len(sites),
            # Reachable: at least one of the four surfaces calls it.
            # Unreachable-but-proved: a suite calls it and no surface does.
            "reachable": reachable, "unreachable": unreachable,
            "surface_call_sites": len([s for s in sites if _is_surface(s.file)])}


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
    parser.add_argument("--self-test", action="store_true",
                        help="check the reader against cases whose answer is known")
    args = parser.parse_args()

    if args.self_test:
        wrong = 0
        for name, ok in self_test():
            print(f"  {'PASS' if ok else 'FAIL'}  {name}")
            wrong += not ok
        print(f"\n{'FAIL' if wrong else 'PASS'} census reader: {wrong} wrong")
        return 1 if wrong else 0

    finding = survey()
    if args.json:
        print(json.dumps(finding, indent=2))
        return 0

    print(f"{finding['total']} addressable route(s); "
          f"{finding['reachable']} REACHABLE BY A PERSON (a surface calls them); "
          f"{len(finding['unreachable'])} proved by a suite and reachable by nobody; "
          f"{len(finding['uncalled'])} called by nothing at all")

    def by_source(routes: list) -> dict:
        out: dict[str, list[str]] = {}
        for route in routes:
            out.setdefault(route["file"], []).append(f"{route['verb']} {route['path']}")
        return out

    # THE MIDDLE COLUMN IS PRINTED FIRST, because it is the one that has hidden two
    # findings. A route with no caller at all is obvious and was always reported; a route
    # a suite drives and no screen reaches looks green from every angle and is where
    # "the tests pass and a person cannot" lives.
    if finding["unreachable"]:
        print("\n  PROVED BY A SUITE, REACHABLE BY NO SURFACE")
        print("  (not a defect on its own — an operator or integration route has no "
              "screen by design)")
        for source, routes in sorted(by_source(finding["unreachable"]).items()):
            print(f"\n  {source}")
            for route in sorted(routes):
                print(f"      {route}")

    if finding["uncalled"]:
        print("\n  CALLED BY NOTHING")
        for source, routes in sorted(by_source(finding["uncalled"]).items()):
            print(f"\n  {source}")
            for route in sorted(routes):
                print(f"      {route}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
