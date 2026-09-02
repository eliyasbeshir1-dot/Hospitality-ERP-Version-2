#!/usr/bin/env python3
"""M2-C verification: the customer surface, three languages, Arabic RTL, accessibility.

The first slice whose subject is a rendered page, so this file is careful about what it
is entitled to claim. Every check below records whether its evidence is MEASURED — read
out of Chromium's own layout after it rendered the page — or ASSERTED, meaning read from
source, from the DOM as served, or from the database. Both are legitimate; conflating
them is not, and a `dir="rtl"` attribute in the markup is not evidence that anything
moved.

The render probe (tests/m2c/render_probe.mjs) decides nothing. It drives the browser and
prints numbers; every judgement about those numbers is here.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "m1a"))
sys.path.insert(0, str(HERE.parent / "m1d"))
sys.path.insert(0, str(HERE))

import fixtures as fx                                   # noqa: E402
from fenced import fenced_identifier_pattern            # noqa: E402
from pg import (  # noqa: E402
    CommandUnreadable, ProbeFailed, count, count_or, run, run_command,
)
from service import Service, TSC, WORKSPACE             # noqa: E402

assert fx.__file__ == str(HERE / "fixtures.py"), f"wrong fixtures module: {fx.__file__}"

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]
CTX = dict(tenant=fx.TENANT, outlet=fx.OUTLET_H1)

LOCALES = ("en", "am", "ar")

# The device and network the performance budgets are measured against. Emulated through
# the DevTools protocol on a desktop, not a handset on a real network — stated here and
# in the report because a budget met on localhost is not evidence for a phone in Addis.
CPU_THROTTLE = "4"
DOWNLOAD_KBPS = "1600"
LATENCY_MS = "300"

# Budgets, chosen before the first measurement rather than fitted to it.
# THE REFERENCE OPERATION, AND WHY THE BUDGETS ARE NOT LOOSENED.
#
# FR-UX-012's budgets are statements about what a guest on a mid-range phone experiences.
# The CI runner is the proxy for that phone, and on Windows the proxy has been observed at
# 1332, 1912, 2188, 5448 and 21432ms of first contentful paint for a BYTE-IDENTICAL
# bundle. An eleven-fold spread on identical bytes is not a fact about the artifact, and
# reporting it as a budget breach is a diagnostic naming a cause it did not verify.
#
# So the probe measures a reference operation in the same run under the same CPU throttle:
# a fixed arithmetic loop that touches no network, no DOM and none of the bundle. A slow
# surface cannot slow it. The ratio between what it cost and what it costs on a healthy
# machine is the machine's factor, and it separates the two failures that used to look
# identical:
#
#   the surface is slow          factor near one, budget exceeded  -> a regression
#   the machine is starved       factor large                      -> not measurable
#
# NOT MEASURABLE IS STILL A FAILURE. It is a different failure with a different name, and
# that is the whole gain: the one permitted CI re-run is then justified by evidence in the
# log rather than by somebody's judgement that it "looked like a flake". The absolute
# numbers below have not moved and must not: a budget adjusted to accommodate a flake
# stops being a budget and devalues every red it reports afterwards.
#
# The baseline is a RECORD, so it is anchored the way tools/check_dated_records.py
# requires of one: measured at 04d0c62 on 2 September 2026, on the Linux development
# machine this project builds on, under the same 4x CPU throttle the probe applies.
REFERENCE_BASELINE_MS = 195
REFERENCE_TOLERANCE = 4.0          # a healthy runner varies; eleven-fold is not variance

BUDGET_FIRST_CONTENTFUL_PAINT_MS = 2500
BUDGET_MENU_VISIBLE_MS = 5000
BUDGET_INTERACTION_MS = 500
BUDGET_TRANSFER_BYTES = 150 * 1024

results: list[tuple[str, bool, str, str]] = []


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    """`evidence` is 'measured' when the fact came out of a real browser's layout.

    Recorded on the result, not only printed, so the summary can report the split from
    what actually ran. Counting the printed lines by hand is how a figure drifts.
    """
    results.append((name, ok, detail, evidence))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] ({evidence}) {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def measured(name: str, ok: bool, detail: str = "") -> None:
    record(name, ok, detail, evidence="measured")


def first_line(text: str | None) -> str:
    stripped = (text or "").strip()
    return stripped.splitlines()[0] if stripped else ""


# ===========================================================================
# Running the browser
# ===========================================================================

PROBE = HERE / "render_probe.mjs"


def render(base_url: str, code: str, *, extra_env: dict[str, str] | None = None) -> dict:
    """Drive the surface in a real browser and return what it measured.

    The probe is copied into the build workspace and run from there. ES module resolution
    ignores NODE_PATH, so a probe left in the repository cannot find playwright however
    the environment is set — and the repository is where node_modules must never appear.
    """
    target = WORKSPACE / "render_probe.mjs"
    target.write_text(PROBE.read_text(encoding="utf-8"), encoding="utf-8")

    proc = run_command(
        ["node", str(target), base_url, fx.TENANT, fx.OUTLET_H1, code,
         CPU_THROTTLE, DOWNLOAD_KBPS, LATENCY_MS],
        cwd=str(WORKSPACE), extra_env=extra_env)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise CommandUnreadable(
            f"the render probe produced no JSON (exit {proc.returncode}): "
            f"{(proc.stdout or proc.stderr)[:400]}")
    return payload


# ===========================================================================
# 1. The surface loads, and loads its own assets
# ===========================================================================

def section_surface(probe: dict, service: Service) -> None:
    print("\n--- 1. The customer surface (FR-UX-001A) ---")

    measured("the surface rendered a menu from the real database",
             probe.get("locales", {}).get("en", {}).get("itemCount", 0) > 0
             and not probe.get("probeFailed"),
             f"{probe['locales']['en']['itemCount']} item(s) drawn in a real browser. The "
             f"names, prices and allergen warnings came through the customer routes from "
             f"menu.published_menu_for_guest() and safety.selection_safety() — a surface "
             f"fed by a fixture could not discharge what M2-B handed this slice")

    # Errors seen BEFORE the retry journey, which deliberately aborts a request to make
    # the first attempt fail. Counting that abort would be counting the probe's own
    # instrument, and excluding errors wholesale would hide real ones — so the probe
    # records the boundary and this reads the earlier half.
    early = probe.get("errorsBeforeRetry", probe.get("errors", []))
    measured("no script or resource error occurred while rendering",
             not early,
             f"console and page errors before the retry journey: {early or 'none'}. The "
             f"retry journey aborts one request on purpose, and the "
             f"{len(probe.get('errors', [])) - len(early)} error(s) after this point are "
             f"that abort")

    index = (WORKSPACE / "dist" / "public" / "index.html").read_text(encoding="utf-8")
    # Comments stripped first. The document's own commentary explains why an injected
    # <script> tag cannot run, and a check that searched the raw text found that sentence
    # and called it a defect — the same way the fenced gate once flagged its own prose.
    import re as _re
    markup = _re.sub(r"<!--.*?-->", "", index, flags=_re.S)
    record("the surface carries no inline script and no inline style",
           "<script>" not in markup and " onclick" not in markup and "style=" not in markup,
           "the content security policy this page is served with permits neither, so an "
           "injected script tag on the one surface an untrusted device loads does not "
           "execute. Written this way rather than relying on the header alone")

    response = service.get("/", token=None)
    csp = response.headers.get("content-security-policy", "")
    record("the surface has its own tightened policy, and the API keeps its own",
           "script-src 'self'" in csp and "default-src 'none'" in csp
           and "unsafe-inline" not in csp and "unsafe-eval" not in csp,
           f"surface policy: {csp[:120]}…\nthe M1 header set is untouched and every "
           f"response still carries all six")

    mandatory = index.count("<input") + index.count("<form")
    record("the surface asks for nothing a guest does not have to give",
           mandatory == 0,
           f"{mandatory} input or form element(s) on the entry surface. M2-B built a guest "
           f"session with no phone, no email and no registration; a surface that "
           f"reintroduced a mandatory field would undo that at the only layer a customer "
           f"sees (FR-UX-001A)")


# ===========================================================================
# 2. Three locales, completely (FR-I18N-001A, FR-I18N-011)
# ===========================================================================

def section_locales(probe: dict) -> None:
    print("\n--- 2. Three locales, rendered completely (FR-I18N-001A, FR-I18N-004) ---")

    for locale in LOCALES:
        seen = probe["locales"][locale]
        measured(f"the surface renders completely in {locale}",
                 not seen["missingStrings"] and seen["itemCount"] > 0,
                 f"lang={seen['lang']}, {seen['itemCount']} item(s), "
                 f"{len(seen['chrome'])} chrome string(s) drawn; strings still showing "
                 f"English: {seen['missingStrings'] or 'none'}. Completeness rather than "
                 f"presence: a screen half in Amharic is the failure mode")

    english_names = probe["locales"]["en"]["itemNames"]
    amharic_names = probe["locales"]["am"]["itemNames"]
    measured("menu CONTENT changes with the locale, not only the chrome",
             english_names != amharic_names and len(amharic_names) > 0,
             f"en: {english_names[:2]}\nam: {amharic_names[:2]}\nthe dish names come from "
             f"menu.translation through the snapshot read, so this is the database's "
             f"translation reaching the screen rather than a bundled string table")

    buttons = probe["locales"]["ar"]["localeButtons"]
    offered = sorted(b["locale"] for b in buttons)
    pressed = [b["locale"] for b in buttons if b["pressed"]]
    too_small = [b["locale"] for b in buttons if b["height"] < 44 or not b["visible"]]
    measured("the three locales are offered explicitly",
             offered == ["am", "ar", "en"] and pressed == ["ar"] and not too_small,
             f"{len(buttons)} chooser button(s) rendered — {', '.join(offered)} — each "
             f"visible at a thumb-sized target, with {pressed} marked pressed while "
             f"Arabic is showing. The chooser is the first thing after the skip link and "
             f"is always reachable; the browser's preferred language is shown beside it "
             f"as a suggestion and applied to nothing (FR-I18N-001A)"
             + (f". Undersized or invisible: {too_small}" if too_small else ""))

    source = (REPO / "pwa" / "src" / "app.ts").read_text(encoding="utf-8")
    record("browser language is a suggestion in the code, not a setting",
           "suggestedLocale()" in source
           and "hint.textContent = STRINGS[suggestion].localeHint" in source
           and "app.locale = suggestion" not in source,
           "suggestedLocale() reaches only the hint text; there is no assignment from it "
           "to the active locale anywhere in the surface")


# ===========================================================================
# 3. Arabic right-to-left, measured (FR-I18N-002)
# ===========================================================================

def section_rtl(probe: dict) -> None:
    print("\n--- 3. Arabic right-to-left (FR-I18N-002) ---")

    arabic = probe["locales"]["ar"]
    english = probe["locales"]["en"]

    measured("Arabic renders right-to-left in the browser's own layout",
             arabic["computedDirection"] == "rtl" and english["computedDirection"] == "ltr",
             f"getComputedStyle(html).direction is {arabic['computedDirection']} in "
             f"Arabic and {english['computedDirection']} in English. The attribute says "
             f"what was asked for; this is what the engine did with it")

    # The skip link and the language buttons sit on opposite sides in the two directions.
    # Their measured x positions are what makes "mirrored navigation" a fact.
    ar_skip, en_skip = arabic["skipLinkLeft"], english["skipLinkLeft"]
    width = arabic["bodyWidth"]
    measured("navigation mirrors: the same elements move to the other side",
             ar_skip is not None and en_skip is not None and ar_skip > width / 2 > en_skip,
             f"the skip link is at x={en_skip:.0f} in English and x={ar_skip:.0f} in "
             f"Arabic, in a {width:.0f}px viewport — it crossed the midline. Logical "
             f"properties throughout the stylesheet, so the mirror is the engine's work "
             f"and not a second set of rules to keep in step")

    # Mixed script: an Arabic page containing a Latin currency code and Latin digits.
    problems = []
    for locale in LOCALES:
        for price in probe["locales"][locale]["prices"]:
            if price["computedDirection"] != "ltr":
                problems.append(f"{locale}: a price rendered {price['computedDirection']}")
            if price["readsLeftToRight"] is not True:
                problems.append(f"{locale}: {price['text']!r} did not read left to right")
    sample = probe["locales"]["ar"]["prices"][0] if probe["locales"]["ar"]["prices"] else {}
    measured("a price keeps its reading order inside an Arabic paragraph",
             not problems,
             f"Arabic sample: {sample.get('text')!r}, first glyph at "
             f"x={sample.get('firstGlyphX')}, last at x={sample.get('lastGlyphX')} — "
             f"measured from client rects, so this is where the glyphs actually landed. "
             f"Every price in all three locales reads left to right"
             + (f"; problems: {problems}" if problems else ""))

    latin_in_arabic = [n for n in probe["locales"]["ar"]["itemNames"]]
    measured("mixed script does not break the item rows",
             probe["locales"]["ar"]["itemCount"] == probe["locales"]["en"]["itemCount"]
             and not probe["locales"]["ar"]["clipped"],
             f"the same {probe['locales']['ar']['itemCount']} items render in Arabic with "
             f"nothing clipped, each carrying a Latin currency code and Latin digits "
             f"beside Arabic text")


# ===========================================================================
# 4. The M2-B handoff: an icon never reaches a guest alone
# ===========================================================================

def section_icon_handoff(probe: dict) -> None:
    print("\n--- 4. M2-B's handoff: no icon without its words, as RENDERED ---")

    for locale in LOCALES:
        allergens = probe["locales"][locale]["allergens"]
        alone = [a for a in allergens
                 if a["glyphVisible"] and (a["textLength"] == 0 or not a["textVisible"])]
        measured(f"no allergen is drawn as an icon alone in {locale}",
                 not alone and len(allergens) > 0,
                 f"{len(allergens)} allergen row(s) rendered, "
                 f"{sum(1 for a in allergens if a['glyphVisible'])} carrying a visible "
                 f"glyph, {len(alone)} with a glyph and no visible words. Both boxes were "
                 f"measured after layout, so an element present but collapsed to zero "
                 f"width counts as absent"
                 + (f"; offenders: {alone}" if alone else ""))

    source = (REPO / "pwa" / "src" / "app.ts").read_text(encoding="utf-8")
    text_first = source.index("row.append(text);")
    glyph_guard = source.index("if (warning.length > 0 && allergen.iconKey)")
    record("the words are appended before the glyph is even created",
           text_first < glyph_guard,
           "the icon element is not constructed in the branch where the warning is "
           "missing, so there is no ordering of these statements — and no later edit to "
           "them — that produces a glyph on its own. M2-B closed this by privilege one "
           "layer down; this is the other half")


# ===========================================================================
# 5. Status without colour, and the seven states (FR-UX-005, FR-UX-006)
# ===========================================================================

def section_states(probe: dict) -> None:
    print("\n--- 5. Seven states, none of them told by colour (FR-UX-005, FR-UX-006) ---")

    rendered = probe["states"]["rendered"]
    measured("all seven states exist and render",
             len(rendered) == 7 and all(v["glyphVisible"] and v["textVisible"]
                                        for v in rendered.values()),
             f"{', '.join(rendered)} — seven distinct states, not three with overlap. "
             f"'Saved on this device' and 'waiting to send' are different promises, and "
             f"'out of date' is data that arrived and aged, not data that never came")

    glyphs = [v["glyph"] for v in rendered.values()]
    texts = [v["text"] for v in rendered.values()]
    measured("every state is distinguishable without colour",
             len(set(glyphs)) == 7 and len(set(texts)) == 7
             and all(g.strip() for g in glyphs) and all(t.strip() for t in texts),
             f"{len(set(glyphs))} distinct glyphs and {len(set(texts))} distinct words "
             f"across seven states, all measured as visible. Remove every colour from "
             f"this interface and the seven remain seven")

    times = [v["dateTime"] for v in rendered.values()]
    measured("every state carries a machine-readable timestamp",
             all(t for t in times),
             "each status renders a <time datetime=…> alongside the word and the glyph, "
             "so 'when did this happen' is answerable from the page (FR-UX-005)")

    transitions = probe["states"]["transitions"]
    declared = [t for t in transitions if t.get("declared")]
    undeclared = [t for t in transitions if t.get("declared") is False]
    measured("every declared transition was walked and accepted",
             len(declared) >= 18 and all(t["accepted"] for t in declared),
             f"{len(declared)} declared edge(s) exercised in the browser, "
             f"{sum(1 for t in declared if t['accepted'])} accepted. The controls walk "
             f"the machine rather than trusting it")

    measured("an undeclared transition is refused from every state",
             len(undeclared) == 7 and all(t["refused"] for t in undeclared),
             f"{len(undeclared)} undeclared edge(s) attempted, all refused with "
             f"UNDECLARED_TRANSITION. A table that permits everything is not a table")


# ===========================================================================
# 6. Localization fit and the locale snapshot
# ===========================================================================

def section_fit_and_snapshot(probe: dict, session_id: str) -> None:
    print("\n--- 6. Localization fit and the locale snapshot (FR-UX-013, FR-I18N-005) ---")

    for locale in LOCALES:
        seen = probe["locales"][locale]
        overflow = seen["documentScrollWidth"] - seen["viewportWidth"]
        measured(f"nothing clips or overflows in {locale}",
                 not seen["clipped"] and overflow <= 1,
                 f"{len(seen['clipped'])} clipped element(s); the document is "
                 f"{seen['documentScrollWidth']}px wide in a {seen['viewportWidth']}px "
                 f"viewport. Measured with the real Amharic and Arabic fixture content, "
                 f"which runs considerably longer than the English")

    zoomed = probe["journeys"]["zoomed"]
    measured("nothing clips at 200% zoom either",
             not zoomed["clipped"]
             and zoomed["documentScrollWidth"] - zoomed["viewportWidth"] <= 1,
             f"at a {zoomed['viewportWidth']}px viewport — the 390px design width at 200% "
             f"— the document is {zoomed['documentScrollWidth']}px and "
             f"{len(zoomed['clipped'])} element(s) clip. No horizontal scrolling, which is "
             f"what WCAG asks for")

    css = (REPO / "pwa" / "app.css").read_text(encoding="utf-8")
    fixed = [line.strip() for line in css.splitlines()
             if ("width:" in line and "px" in line and "max-inline-size" not in line
                 and "min-inline-size" not in line and "--" not in line)]
    record("no hard-coded width holds text",
           not fixed,
           f"declarations fixing a width in pixels: {fixed or 'none'}. Sizes are logical "
           f"and content-driven, so a longer translation grows its container instead of "
           f"being cut off (FR-UX-013)")

    snapshot = run(APP, f"""
        SELECT customer_locale::text, customer_locale_selected_at IS NOT NULL
        FROM service.table_session WHERE id = '{session_id}';
    """, **CTX)
    row = snapshot.rows[0] if snapshot.ok and snapshot.rows else ["", "f"]
    record("the chosen locale is snapshotted on the table session",
           snapshot.ok and row[0] in LOCALES and row[1].strip().lower() in ("t", "true"),
           f"service.table_session.customer_locale is {row[0]!r} with the moment it was "
           f"chosen. M3's order communications and M4's receipts read it, so a customer "
           f"does not receive a receipt in a language they did not choose (FR-I18N-005)")

    nulled = run(APP, f"""
        UPDATE service.table_session SET customer_locale = NULL
        WHERE id = '{session_id}';
    """, rollback=True, **CTX)
    record("a locale without the moment it was chosen cannot be stored",
           nulled.failed_with("table_session_locale_snapshot_is_a_choice"),
           f"both columns or neither: a language recorded with no moment attached is a "
           f"value somebody defaulted rather than a choice somebody made — and no default "
           f"is written, because a customer who has not chosen has not chosen English. "
           f"{first_line(nulled.err)}")


# ===========================================================================
# 7. Accessibility (FR-UX-011, FR-TST-011)
# ===========================================================================

def section_accessibility(probe: dict) -> None:
    print("\n--- 7. Accessibility (FR-UX-011, FR-TST-011) ---")

    for locale in LOCALES:
        found = probe["axe"][locale]["violations"]
        measured(f"axe-core finds no WCAG A or AA violation in {locale}",
                 not found,
                 f"{len(found)} violation(s) against wcag2a, wcag2aa, wcag21a and "
                 f"wcag21aa, run against the live rendered page"
                 + (f": {found}" if found else
                    ". Automated coverage is a floor, not a ceiling — what it does not "
                    "reach is listed in the report"))

    for label, walk in (("English", probe["journeys"]["keyboardEnglish"]),
                        ("Arabic", probe["journeys"]["keyboardArabic"])):
        classes = [step["className"] or step["tag"] for step in walk]
        measured(f"the keyboard reaches the surface in a sensible order in {label}",
                 len(walk) >= 5 and "skip-link" in (classes[0] or "")
                 and all("locale" in (c or "") for c in classes[1:4]),
                 f"tabbing from the top of the document: {classes[:5]}. The skip link is "
                 f"first, then the three languages, then the menu — read from "
                 f"document.activeElement after each real Tab keypress")

    outlines = [step["outlineStyle"] for step in probe["journeys"]["keyboardEnglish"]]
    measured("every focused element shows a visible focus indicator",
             all(style not in ("none", "") for style in outlines),
             f"computed outline-style at each stop: {sorted(set(outlines))}. Measured "
             f"while focused, so this is the indicator a keyboard user actually sees")

    ar_x = [step["x"] for step in probe["journeys"]["keyboardArabic"][1:4]]
    en_x = [step["x"] for step in probe["journeys"]["keyboardEnglish"][1:4]]
    measured("tab order follows the mirrored layout in Arabic",
             len(ar_x) == 3 and len(en_x) == 3
             and en_x == sorted(en_x) and ar_x == sorted(ar_x, reverse=True),
             f"the three language buttons are reached at x={[round(x) for x in en_x]} in "
             f"English and x={[round(x) for x in ar_x]} in Arabic — left to right in one, "
             f"right to left in the other, with the DOM order unchanged")


# ===========================================================================
# 8. Empty states, no fabricated data, and the slice boundary
# ===========================================================================

def _strip_ts_comments(text: str) -> str:
    """TypeScript source with its comments removed, so a scan reads code only.

    Deliberately simple and deliberately conservative: it does not try to understand
    strings containing // or /*, so at worst it removes slightly more than a comment and
    a forbidden identifier hiding inside a string literal would still be caught by the
    scan of the rendered document beside it.
    """
    import re as _re
    text = _re.sub(r"/\*[\s\S]*?\*/", " ", text)
    return "\n".join(_re.sub(r"//.*$", " ", line) for line in text.splitlines())


def section_boundary(probe: dict) -> None:
    print("\n--- 8. Empty states, honest data, and what M2-C did NOT build ---")

    index = (WORKSPACE / "dist" / "public" / "index.html").read_text(encoding="utf-8")
    source = (REPO / "pwa" / "src" / "app.ts").read_text(encoding="utf-8")

    record("the empty state says what to do next",
           "noMenu" in source and "Please ask a member of staff" in source,
           "an unpublished menu renders a sentence naming the next action, not a spinner "
           "that never resolves and not a blank page (FR-UX-014)")

    fabricated = [word for word in ("chart", "sparkline", "sampleData", "placeholderData",
                                    "demoRevenue", "fakeTotal", "lorem")
                  if word.lower() in source.lower() or word.lower() in index.lower()]
    record("nothing fabricated is ever displayed",
           not fabricated,
           f"terms suggesting invented data in the surface: {fabricated or 'none'}. There "
           f"is no chart, no placeholder figure and no sample number anywhere: every "
           f"value on the screen came from the database this run (FR-UX-014)")

    # The `or len(...) > 0` this check used to carry made it pass on any menu at all,
    # including an English one — an assertion about real Amharic content that could not
    # fail. Both halves are required now: the drawn names must differ from the English
    # ones AND carry Ethiopic script.
    amharic = probe["locales"]["am"]["itemNames"]
    english = probe["locales"]["en"]["itemNames"]
    ethiopic = [name for name in amharic if any("\u1200" <= ch <= "\u137f" for ch in name)]
    measured("the fixture content is real, not lorem ipsum",
             bool(amharic) and amharic != english and len(ethiopic) == len(amharic),
             f"the Amharic render drew {amharic[:2]}, all {len(ethiopic)} of "
             f"{len(amharic)} in Ethiopic script and none of them the English "
             f"{english[:2]}. Real fixture content, which is what FR-UX-013 asks to be "
             f"measured against")

    # THIS CHECK WAS RE-TARGETED AT M3-D, AND THE ONE BELOW WAS BROKEN.
    #
    # It read "the surface cannot submit an order, pay, or open a check", and it named
    # three gates at once: orders are M3, payments and checks are M4. M3-A built ordering
    # and M3-D put a submit button on this surface, so the ORDER half is now asserting
    # the absence of something a later gate delivered on purpose. A gate-local boundary
    # that outlives its gate stops being a boundary and becomes a check that fails when
    # the plan is followed.
    #
    # The MONEY half has not moved and is not softened: checkout, payment, tip, check and
    # receipt are M4's, and a customer surface that named any of them at M3 would be the
    # scope creep this check exists to catch. kitchenTicket stays too — the KDS is M3-B's
    # own surface and a guest's phone must never render one.
    # Scanned over the CODE, with comments removed. The first version of this edit put
    # 'receipt' on the list and it went red on a comment that says M4 will have receipts
    # — prose about a later gate, which is the opposite of scope creep. A check that
    # cannot tell a payment button from a sentence about payments is a check that
    # punishes people for writing down why something is absent.
    code = _strip_ts_comments(source)
    settlement = [word for word in ("checkout", "payment", "tip", "receipt",
                                    "kitchenTicket", "openCheck")
                  if word.lower() in code.lower()]
    record("the surface still cannot pay, tip, or open a check",
           not settlement,
           f"settlement terms in the surface: {settlement or 'none'}. Ordering arrived at "
           f"M3 and this surface submits one; money is M4's and none of it is here")

    # The route check below asserted the same boundary and could not fail. It read the
    # file line by line and kept the lines containing `app.post` — but every route in
    # customer.ts declares its generic type parameters on that line and its PATH on the
    # next one, so the strings it searched never contained a path at all. It passed on
    # M3-A's ordering routes, which are exactly what it was written to catch, and it
    # would have passed on a payment route on the day it was written. An assertion that
    # cannot fail is a defect; this one is repaired and re-targeted in the same edit, so
    # the repair is visible rather than hidden inside a boundary change.
    import re as _re
    routes = (REPO / "api" / "src" / "routes" / "customer.ts").read_text(encoding="utf-8")
    declared = sorted({m.group(1) for m in _re.finditer(
        r"app\.(?:post|put|get|delete|patch)\s*(?:<[\s\S]*?>)?\s*\(\s*'([^']+)'",
        routes)})
    money = [path for path in declared
             if any(word in path.lower()
                    for word in ("check", "payment", "receipt", "tip", "settle"))]
    record("the customer API still adds no check, payment or receipt route",
           bool(declared) and not money,
           f"customer routes read out of the source: {declared}. Money routes among "
           f"them: {money or 'none'}. The list is non-empty by assertion, because a "
           f"regex that matched nothing would make this pass for the second time")

    sync = [word for word in ("serviceWorker", "backgroundSync", "syncQueue", "flushQueue")
            if word.lower() in source.lower()]
    record("the offline STATES exist and the offline SYNC does not",
           not sync,
           f"sync machinery in the surface: {sync or 'none'}. M5a owns the queue that "
           f"actually drains; the seven states a guest is shown are this slice's, and "
           f"they are all reachable without one")

    pattern, terms = fenced_identifier_pattern()
    import re as _re
    fenced = sorted({m.group(0) for m in _re.finditer(pattern, source, _re.I)}
                    | {m.group(0) for m in _re.finditer(pattern, index, _re.I)})
    record("the surface names no permanently fenced domain",
           not fenced,
           f"checked the surface source and document against all {terms} authoritative "
           f"terms: {fenced or 'none'}")


# ===========================================================================
# 9. Negative controls
# ===========================================================================

def capture(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def prove(control: str, gate, signature: str, edits: list[tuple[Path, str, str]],
          *, evidence: str = "measured") -> None:
    """Plant a defect in the SURFACE SOURCE, rebuild it, and require the named failure.

    The defect goes into the build workspace's copy, never the repository: api/build.sh
    re-copies from the repository on every run, so reverting is a rebuild rather than an
    edit and the repository is never broken even for an instant. Same arrangement M1-D
    uses for the service.
    """
    ok, _, detail = gate()
    if not ok:
        record(f"{control} — baseline", False,
               f"gate already failing before the break: {detail}", evidence=evidence)
        return

    originals = [(path, capture(path)) for path, _, _ in edits]
    try:
        for path, old, new in edits:
            text = path.read_text(encoding="utf-8")
            if old not in text:
                record(f"{control} — inject defect", False,
                       f"anchor not found in {path.name}: {old[:60]!r}", evidence=evidence)
                return
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
        rebuild_surface()

        red_ok, red_sig, red_detail = gate()
        record(f"{control} — RED with the defect planted",
               (not red_ok) and red_sig == signature,
               f"{red_sig or '(gate still passed)'}: {red_detail}", evidence=evidence)
    finally:
        for path, original in originals:
            path.write_text(original, encoding="utf-8")
        rebuild_surface()

    green_ok, green_sig, green_detail = gate()
    record(f"{control} — GREEN after revert", green_ok,
           green_detail if green_ok else f"{green_sig}: {green_detail}", evidence=evidence)


SURFACE_SRC = WORKSPACE / "pwa" / "src" / "app.ts"
SURFACE_CSS = WORKSPACE / "pwa" / "app.css"

# Set by main() so the gates can re-render and re-query without threading them through.
CONTEXT: dict = {}


def rebuild_surface() -> None:
    """Recompile the surface from the workspace copy and restart the service.

    The service loads its files once at startup — which is what a server should do — so a
    rebuilt bundle only reaches a browser after a restart. Doing it here rather than
    serving from disk per request keeps the thing under test the thing that ships.
    """
    # TSC, not the literal "tsc". npm publishes two entry points in .bin: an extensionless
    # shell script for POSIX and a .cmd shim for Windows, and only the shim is a valid
    # Win32 executable — handing CreateProcess the other one fails with WinError 193,
    # which is not a compile error and would be reported as one. M1-D learned this and
    # exports the resolved name; this file was written after it and hardcoded the POSIX
    # one anyway, and Windows CI caught it on the first run that had a browser.
    proc = run_command([str(WORKSPACE / "node_modules" / ".bin" / TSC),
                        "-p", str(WORKSPACE / "pwa" / "tsconfig.json"),
                        "--outDir", str(WORKSPACE / "dist" / "public")],
                       cwd=str(WORKSPACE))
    if proc.returncode != 0:
        raise RuntimeError(f"surface rebuild failed: {proc.stdout or proc.stderr}")
    for name in ("index.html", "app.css", "manifest.webmanifest"):
        (WORKSPACE / "dist" / "public" / name).write_text(
            (WORKSPACE / "pwa" / name).read_text(encoding="utf-8"), encoding="utf-8")
    CONTEXT["restart"]()


def quick() -> dict:
    """One render, in the two locales every control needs, on a fresh occupancy."""
    return _quick_render(fx.fresh_occupancy_and_code())


def _quick_render(code: str) -> dict:
    target = WORKSPACE / "render_probe.mjs"
    target.write_text(PROBE.read_text(encoding="utf-8"), encoding="utf-8")
    proc = run_command(["node", str(target), CONTEXT["base_url"], fx.TENANT, fx.OUTLET_H1,
                        code, CPU_THROTTLE, DOWNLOAD_KBPS, LATENCY_MS, "quick"],
                       cwd=str(WORKSPACE))
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise CommandUnreadable(
            f"the render probe produced no JSON (exit {proc.returncode}): "
            f"{(proc.stdout or proc.stderr)[:400]}")


def rtl_gate() -> tuple[bool, str, str]:
    """Arabic must lay out right-to-left, and a price must keep its reading order."""
    probe = quick()
    if probe.get("probeFailed"):
        return False, "RTL_LAYOUT_OR_READING_ORDER_FAILURE", probe["probeFailed"][:200]
    arabic = probe["locales"].get("ar", {})
    english = probe["locales"].get("en", {})
    leaks: list[str] = []

    if arabic.get("computedDirection") != "rtl":
        leaks.append(f"Arabic laid out {arabic.get('computedDirection')}, not rtl")
    width = arabic.get("bodyWidth") or 0
    ar_skip, en_skip = arabic.get("skipLinkLeft"), english.get("skipLinkLeft")
    if ar_skip is None or en_skip is None or not (ar_skip > width / 2 > en_skip):
        leaks.append(f"navigation did not mirror: skip link at x={en_skip} in English and "
                     f"x={ar_skip} in Arabic across {width}px")
    for price in arabic.get("prices", []):
        if price["readsLeftToRight"] is not True:
            leaks.append(f"a price rendered {price['text']!r} out of reading order")
            break

    if leaks:
        return False, "RTL_LAYOUT_OR_READING_ORDER_FAILURE", "; ".join(leaks)
    return True, "", ("Arabic lays out rtl in the engine's own computed style, the skip "
                      "link crosses the midline, and every price still reads left to "
                      "right inside the mirrored page")


def icon_render_gate() -> tuple[bool, str, str]:
    """No allergen may reach a guest as a glyph with no words."""
    probe = quick()
    if probe.get("probeFailed"):
        return False, "WRITTEN_WARNING_ABSENT_FROM_RENDER", probe["probeFailed"][:200]
    leaks: list[str] = []
    total = 0
    for locale in ("en", "ar"):
        allergens = probe["locales"].get(locale, {}).get("allergens", [])
        total += len(allergens)
        for row in allergens:
            if row["glyphVisible"] and (row["textLength"] == 0 or not row["textVisible"]):
                leaks.append(f"{locale}: {row['kitchenCode']} drew a glyph with no words")
    if total == 0:
        leaks.append("no allergen rendered at all, so nothing was tested")
    if leaks:
        return False, "WRITTEN_WARNING_ABSENT_FROM_RENDER", "; ".join(leaks[:4])
    return True, "", (f"{total} allergen row(s) across two locales, every visible glyph "
                      f"beside visible words, measured after layout")


def colour_only_gate() -> tuple[bool, str, str]:
    """Every state must differ by something other than its colour."""
    probe = quick()
    if probe.get("probeFailed"):
        return False, "STATE_CONVEYED_BY_COLOUR_ALONE", probe["probeFailed"][:200]
    rendered = probe["states"]["rendered"]
    glyphs = [v["glyph"].strip() for v in rendered.values()]
    texts = [v["text"].strip() for v in rendered.values()]
    leaks: list[str] = []
    if len(rendered) != 7:
        leaks.append(f"{len(rendered)} states rendered, not seven")
    if len(set(texts)) != len(texts) or not all(texts):
        leaks.append(f"{len(texts) - len(set(texts))} state(s) share a word, or have none")
    if len(set(glyphs)) != len(glyphs) or not all(glyphs):
        leaks.append(f"{len(glyphs) - len(set(glyphs))} state(s) share a glyph, or have none")
    invisible = [k for k, v in rendered.items() if not (v["glyphVisible"] and v["textVisible"])]
    if invisible:
        leaks.append(f"state(s) whose word or glyph is not visible: {invisible}")
    if leaks:
        return False, "STATE_CONVEYED_BY_COLOUR_ALONE", "; ".join(leaks)
    return True, "", ("seven states, seven distinct words, seven distinct glyphs, all "
                      "measured visible — remove every colour and the seven remain seven")


def cart_gate() -> tuple[bool, str, str]:
    """Switching language must not lose what the guest already chose."""
    probe = quick()
    if probe.get("probeFailed"):
        return False, "CART_LOST_ON_LOCALE_CHANGE", probe["probeFailed"][:200]
    journey = probe["journeys"]["cartAcrossLocale"]
    before, after = journey["before"], journey["after"]
    if not before:
        return False, "CART_LOST_ON_LOCALE_CHANGE", "nothing was in the basket to lose"
    if len(after) != len(before):
        return False, "CART_LOST_ON_LOCALE_CHANGE", (
            f"{len(before)} line(s) before the language change and {len(after)} after")
    if [line["key"] for line in before] != [line["key"] for line in after]:
        return False, "CART_LOST_ON_LOCALE_CHANGE", "the basket was rebuilt, not kept"
    if [line["amountMinor"] for line in before] != [line["amountMinor"] for line in after]:
        return False, "CART_LOST_ON_LOCALE_CHANGE", (
            "the stored amount changed when the language did, so the basket was re-priced")
    rendered = journey["renderedAfter"]
    if len(rendered) != len(after):
        return False, "CART_LOST_ON_LOCALE_CHANGE", (
            f"{len(after)} line(s) held but {len(rendered)} drawn after the change")
    return True, "", (f"{len(before)} line(s) kept across a language change, same keys and "
                      f"the same canonical amounts, redrawn as {rendered[0]['price']!r} — "
                      f"the language is a rendering concern and the basket is state")


def locale_completeness_gate() -> tuple[bool, str, str]:
    """A required locale must render completely, not mostly."""
    probe = quick()
    if probe.get("probeFailed"):
        return False, "INCOMPLETE_LOCALE_RENDER", probe["probeFailed"][:200]
    leaks: list[str] = []
    for locale in ("en", "ar"):
        seen = probe["locales"].get(locale, {})
        missing = seen.get("missingStrings", ["(locale not rendered)"])
        if missing:
            leaks.append(f"{locale}: {len(missing)} string(s) still English: {missing[:4]}")
        if not seen.get("itemCount"):
            leaks.append(f"{locale}: no menu content rendered")
    if leaks:
        return False, "INCOMPLETE_LOCALE_RENDER", "; ".join(leaks)
    return True, "", ("every surface string resolves in its own language in both locales "
                      "checked, and the menu content renders with them")


def duplicate_commitment_gate() -> tuple[bool, str, str]:
    """A retry must finish the first attempt, never start a second.

    Two independent halves. The browser half: the first request is made to fail at the
    network, the guest presses "try again", and both requests' Idempotency-Key headers are
    compared. The server half: the same key sent twice must produce one row, whatever the
    client does.
    """
    before = count_or(APP, "SELECT count(*) FROM service.cart_line;", -1, **CTX)
    probe = quick()
    if probe.get("probeFailed"):
        return False, "DUPLICATE_COMMITMENT_ON_RETRY", probe["probeFailed"][:200]
    after = count_or(APP, "SELECT count(*) FROM service.cart_line;", -1, **CTX)

    journey = probe["journeys"].get("retry", {})
    leaks: list[str] = []

    if not journey.get("retryOffered"):
        leaks.append(
            "a failed write left the guest a retry they could not take — the control was "
            "drawn and then withdrawn before it could be used"
            if journey.get("retryShown")
            else "a failed write offered the guest no way to try again")
    if len(journey.get("keysSeen", [])) < 2:
        leaks.append(f"only {len(journey.get('keysSeen', []))} attempt(s) were made, so a "
                     f"retry was never exercised")
    elif not journey.get("sameKeyOnRetry"):
        leaks.append(f"the retry carried a different key: {journey['keysSeen']}")

    # The probe adds one line in the cart-across-locale journey and one in the retry
    # journey. A duplicate on retry shows up as a third.
    if after - before > 2:
        leaks.append(f"{after - before} cart line(s) were created by a run that asked for "
                     f"two, so a retry committed twice")

    if leaks:
        return False, "DUPLICATE_COMMITMENT_ON_RETRY", "; ".join(leaks)
    return True, "", (f"the first attempt failed at the network, the guest retried, and "
                      f"both requests carried the same key "
                      f"{(journey['keysSeen'][0] or '')[:8]}…; {after - before} line(s) "
                      f"exist where two were asked for, so the retry finished the first "
                      f"attempt rather than starting a second")


def locale_snapshot_gate() -> tuple[bool, str, str]:
    """The locale a customer chose must be recorded on the occupancy they chose it in."""
    probe = quick()
    if probe.get("probeFailed"):
        return False, "LOCALE_SNAPSHOT_ABSENT", probe["probeFailed"][:200]

    # The probe's last locale change in quick mode is to Arabic, on the occupancy the
    # fixture opened for it. Read the most recent open occupancy back.
    # coalesce on both columns: an absent locale is exactly the case this control is
    # about, and a NULL that renders as an empty field made the row come back with fewer
    # values than it had columns — which is a crash rather than a finding.
    snapshot = run(APP, f"""
        SELECT coalesce(customer_locale::text, 'none'),
               coalesce((customer_locale_selected_at IS NOT NULL)::text, 'false')
        FROM service.table_session
        WHERE tenant_id = '{fx.TENANT}' AND state = 'open'
        ORDER BY opened_at DESC LIMIT 1;
    """, **CTX)
    if not snapshot.ok or not snapshot.rows or len(snapshot.rows[0]) < 2:
        return False, "LOCALE_SNAPSHOT_ABSENT", (
            f"could not read the occupancy: {snapshot.why() or snapshot.rows}")

    locale, stamped = snapshot.rows[0][0], snapshot.rows[0][1]
    leaks: list[str] = []
    if locale.strip() in ("", "none", "NULL"):
        leaks.append("the occupancy carries no customer locale after a guest chose one")
    elif locale.strip() not in LOCALES:
        leaks.append(f"the occupancy carries {locale!r}, which is not one of the three")
    if stamped.strip().lower() not in ("t", "true"):
        leaks.append("the locale was recorded with no moment attached, so nothing "
                     "distinguishes a choice from a default")

    if leaks:
        return False, "LOCALE_SNAPSHOT_ABSENT", "; ".join(leaks)
    return True, "", (f"the occupancy carries customer_locale={locale!r} with the moment "
                      f"it was chosen. M3's order communications and M4's receipts read "
                      f"it, so a guest does not receive a receipt in a language they did "
                      f"not pick")


def section_controls() -> None:
    print("\n--- 9. M2-C negative controls, each proved red then green ---")

    print("\n  NC-M2-004  Arabic does not lay out right-to-left")
    prove("NC-M2-004", rtl_gate, "RTL_LAYOUT_OR_READING_ORDER_FAILURE",
          [(SURFACE_SRC,
            "  document.documentElement.dir = app.locale === 'ar' ? 'rtl' : 'ltr';",
            "  document.documentElement.dir = 'ltr';  // the defect: direction never changes")])

    print("\n  NC-M2C-005  the surface draws an allergen icon with no written warning")
    prove("NC-M2C-005", icon_render_gate, "WRITTEN_WARNING_ABSENT_FROM_RENDER",
          [(SURFACE_SRC,
            """        text.textContent = warning.length > 0
          ? `${strings[allergen.declarationClass]}: ${warning}`
          : strings.warningUnavailable;
        row.append(text);

        if (warning.length > 0 && allergen.iconKey) {""",
            """        text.textContent = warning.length > 0
          ? `${strings[allergen.declarationClass]}: ${warning}`
          : '';
        row.append(text);

        // The defect: the icon is drawn whether or not there are words beside it, which
        // is the shape a surface takes when somebody moves the glyph out of the guarded
        // branch to simplify it.
        if (allergen.iconKey) {"""),
           (SURFACE_CSS, ".allergen-text { min-inline-size: 0; }",
            ".allergen-text { min-inline-size: 0; display: none; }")])

    print("\n  NC-M2C-006  a critical state is distinguishable only by colour")
    prove("NC-M2C-006", colour_only_gate, "STATE_CONVEYED_BY_COLOUR_ALONE",
          [(SURFACE_SRC,
            """  $('status-glyph').textContent = GLYPH[app.state];
  $('status-text').textContent = strings[app.state];""",
            """  // The defect: every state says the same word and shows the same glyph, and only
  // the colour the stylesheet applies from data-state tells them apart.
  $('status-glyph').textContent = '\\u25cf';
  $('status-text').textContent = strings.synchronized;""")])

    print("\n  NC-M2C-007  switching language loses the basket")
    prove("NC-M2C-007", cart_gate, "CART_LOST_ON_LOCALE_CHANGE",
          [(SURFACE_SRC,
            """async function chooseLocale(locale: Locale): Promise<void> {
  app.locale = locale;""",
            """async function chooseLocale(locale: Locale): Promise<void> {
  app.locale = locale;
  // The defect: the basket is cleared on a language change, which is what happens when
  // the surface treats a locale switch as a fresh start rather than a re-render.
  app.cart = [];""")])

    print("\n  NC-M2C-008  a required locale renders only partly")
    prove("NC-M2C-008", locale_completeness_gate, "INCOMPLETE_LOCALE_RENDER",
          [(SURFACE_SRC,
            "    total: 'الإجمالي', warningUnavailable:",
            "    total: 'Total', warningUnavailable:")])

    print("\n  NC-M2C-009  a retry commits a second time")
    prove("NC-M2C-009", duplicate_commitment_gate, "DUPLICATE_COMMITMENT_ON_RETRY",
          [(SURFACE_SRC,
            """  // Deliberately the same `pending` object, carrying the same key.
  const work = pending;""",
            """  // The defect: a fresh key on every attempt, which is the natural thing to write
  // and turns one order into two.
  const work = { ...pending, key: newIdempotencyKey() };""")])

    print("\n  NC-M2C-010  the locale a customer chose is not recorded")
    # The only control here whose evidence is a database row rather than a rendered
    # pixel: what the surface did is observed by what it wrote, not by what it drew.
    prove("NC-M2C-010", locale_snapshot_gate, "LOCALE_SNAPSHOT_ABSENT", evidence="asserted",
          edits=
          [(SURFACE_SRC,
            """  if (credentials) {
    void fetch('/c/v1/locale', {
      method: 'PUT',
      headers: { 'content-type': 'application/json', authorization: `Guest ${credentials.guestToken}` },
      body: JSON.stringify({ tableSessionId: credentials.tableSessionId, locale }),
    }).catch(() => undefined);
  }""",
            """  // The defect: the surface switches language and tells nobody, so the occupancy
  // carries no customer locale and M3's order communications and M4's receipts have
  // nothing to read. This is the shape the code takes when the snapshot is treated as a
  // nice-to-have rather than as the thing two later gates depend on.
  void 0;""")])


# ===========================================================================
# 10. Performance budgets (FR-UX-012)
# ===========================================================================

def section_performance(probe: dict) -> None:
    print("\n--- 10. Performance budgets (FR-UX-012) ---")

    perf = probe["performance"]
    device = probe["device"]
    print(f"         profile: {device['name']}, {device['viewport']['width']}x"
          f"{device['viewport']['height']} at {device['deviceScaleFactor']}x, CPU "
          f"throttled {device['cpuThrottlingRate']}x, network {device['downloadKbps']} "
          f"kbps down with {device['latencyMs']}ms latency")

    reference = perf.get("referenceMs")
    if not reference:
        raise ProbeFailed(
            "the reference operation",
            "the probe reported no reference measurement, so a budget breach could not "
            "be told from a starved runner. Refusing rather than reporting an absolute "
            "number whose meaning is unknown")
    factor = reference / REFERENCE_BASELINE_MS
    print(f"         reference: {reference}ms for a fixed arithmetic loop under the same "
          f"throttle, against a {REFERENCE_BASELINE_MS}ms baseline — this machine is "
          f"{factor:.2f}x")
    measurable = factor <= REFERENCE_TOLERANCE

    def budget(name: str, observed, limit: int, detail: str) -> None:
        """One budget, reported as a regression or as an unmeasurable machine, never both.

        A breach on a machine the reference says is starved is not evidence about the
        surface, and calling it one would be a diagnostic naming a cause it did not
        verify. It is still a FAILURE — a measurement that did not happen cannot be a
        pass — but a differently named one, so the single permitted re-run rests on
        evidence in the log rather than on somebody's impression that it looked flaky.
        """
        if observed is None:
            measured(name, False, f"the probe reported nothing for {name}")
            return
        within = observed <= limit
        if within:
            measured(name, True, f"{observed}ms against a {limit}ms budget. {detail}")
        elif measurable:
            measured(name, False,
                     f"PERFORMANCE_BUDGET_EXCEEDED: {observed}ms against a {limit}ms "
                     f"budget, and the reference says this machine is {factor:.2f}x — "
                     f"within its normal band, so the surface is what is slow. {detail}")
        else:
            measured(name, False,
                     f"PERFORMANCE_NOT_MEASURABLE: {observed}ms against a {limit}ms "
                     f"budget on a machine the reference puts at {factor:.2f}x, past the "
                     f"{REFERENCE_TOLERANCE}x band. Everything here is slow together, so "
                     f"this run is not evidence about the surface. The budget has not "
                     f"moved and this is still a failure; what it is not is a regression")

    budget("first contentful paint is within budget",
           perf["firstContentfulPaintMs"], BUDGET_FIRST_CONTENTFUL_PAINT_MS,
           "From the browser's own paint timing under the throttle above")

    budget("the menu is on screen within budget",
           perf["menuVisibleMs"] if perf["menuArrived"] else None,
           BUDGET_MENU_VISIBLE_MS,
           f"This is the whole journey: entry, QR exchange, join, basket and menu read, "
           f"four round trips at {device['latencyMs']}ms each")

    measured("an interaction responds within budget",
             perf["interactionMs"] <= BUDGET_INTERACTION_MS,
             f"{perf['interactionMs']}ms from tapping Add to the basket line appearing, "
             f"against {BUDGET_INTERACTION_MS}ms, with the CPU still throttled "
             f"{device['cpuThrottlingRate']}x. The line is drawn from local state before "
             f"anything leaves the device, which is why this is not a network number")

    measured("the surface stays inside its transfer budget",
             perf["transferredBytes"] <= BUDGET_TRANSFER_BYTES,
             f"{perf['transferredBytes']} bytes over {perf['requestCount']} requests, "
             f"against {BUDGET_TRANSFER_BYTES}. No framework and no runtime dependency: "
             f"the bundle is one compiled file and one stylesheet")


def main() -> int:
    print("M2-C verification — customer surface, three languages, Arabic RTL, accessibility")
    print(f"real PostgreSQL, real compiled service, real Chromium (running on "
          f"{platform.system()})")
    print("\n  (measured) = read out of the browser's own layout after it rendered")
    print("  (asserted) = read from source, from the served DOM, or from the database\n")

    fx.seed()
    print("fixtures seeded: a published menu, a seated guest and a live code")

    # Service.__enter__ raises if the service does not start, naming why and quoting the
    # log. A suite that caught that and reported "0 checks, 0 failures" would be green
    # for having tested nothing.
    with Service(APP) as service:
        CONTEXT["base_url"] = f"http://127.0.0.1:{service.port}"
        CONTEXT["restart"] = service.restart

        code = fx.fresh_occupancy_and_code()
        probe = render(CONTEXT["base_url"], code)
        if probe.get("probeFailed"):
            record("the render probe completed", False, probe["probeFailed"][:400])
        else:
            session_id = (run(APP, f"""
                SELECT id::text FROM service.table_session
                WHERE tenant_id = '{fx.TENANT}' AND state = 'open'
                ORDER BY opened_at DESC LIMIT 1;
            """, **CTX).scalar or "").strip()

            section_surface(probe, service)
            section_locales(probe)
            section_rtl(probe)
            section_icon_handoff(probe)
            section_states(probe)
            section_fit_and_snapshot(probe, session_id)
            section_accessibility(probe)
            section_boundary(probe)
            section_performance(probe)
            section_controls()

    passed = sum(1 for _n, ok, _d, _e in results if ok)
    failed = [name for name, ok, _d, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")
    asserted_count = len(results) - measured_count
    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {passed}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}   (read out of a real browser's layout)")
    print(f"  asserted      : {asserted_count}   (source, served DOM, or database)")
    for name in failed:
        print(f"  - {name}")
    print()
    if failed:
        print("FAIL M2C_VERIFICATION")
        return 1
    print("PASS M2C_VERIFICATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
