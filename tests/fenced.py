"""The fenced-domain vocabulary, loaded from the pinned package.

Shared by every slice's harness. The vocabulary is never restated in test source:
a second copy could drift from the registry the package validates against, and
writing the terms out by hand puts fenced literals into repository source, which the
M1 forbidden-surface verifier correctly refuses.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PACKAGE = (Path(__file__).resolve().parents[1]
           / "docs" / "Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9")


def fenced_identifier_pattern() -> tuple[str, int]:
    """Build an identifier-matching regex from the package's fenced vocabulary.

    Terms are matched as whole identifier components — bounded by start, end or an
    underscore — so a short term such as "hr" cannot false-positive on "threshold".
    Multi-word terms tolerate either a space or an underscore between words.
    """
    rules = json.loads(
        (PACKAGE / "02_MACHINE_READABLE" / "forbidden_surface_rules.json").read_text(encoding="utf-8")
    )
    terms = sorted({t for group in rules["forbidden_positive_obligations"].values() for t in group})
    alternatives = []
    for term in terms:
        cleaned = "".join(ch for ch in term.lower() if ch.isalnum() or ch in " _-")
        alternatives.append(re.sub(r"[ _-]+", "[_ ]*", cleaned.strip()))
    return "(^|_)(" + "|".join(alternatives) + ")(_|$)", len(terms)
