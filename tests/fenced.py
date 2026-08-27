"""The fenced-domain vocabulary, loaded from the pinned package.

Single source for every consumer: the M1 forbidden-surface verifier and each slice's
harness. The vocabulary is never restated in source. A second copy drifts from the
registry the package validates against, and writing the terms out by hand is exactly the
defect that let 46 of 63 authoritative terms pass the gate unnoticed for two slices.

Everything here fails closed. A vocabulary that cannot be loaded, or that loads empty, is
an error — never a fallback to a built-in list, because a silently empty vocabulary passes
everything and reports success while doing so.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

PACKAGE = (Path(__file__).resolve().parents[1]
           / "docs" / "Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9")
RULES_PATH = PACKAGE / "02_MACHINE_READABLE" / "forbidden_surface_rules.json"


class VocabularyUnavailable(Exception):
    """The authoritative vocabulary could not be loaded. Callers must stop, not continue."""


@lru_cache(maxsize=1)
def load_vocabulary() -> dict[str, tuple[str, ...]]:
    """Return {domain: (term, …)} from the pinned package, or raise.

    Raises rather than returning empty so that no caller can mistake "nothing forbidden"
    for "nothing loaded".
    """
    try:
        raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise VocabularyUnavailable(
            f"the pinned package is absent at {RULES_PATH}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise VocabularyUnavailable(
            f"the vocabulary at {RULES_PATH} could not be read: {error}") from error

    groups = raw.get("forbidden_positive_obligations")
    if not isinstance(groups, dict) or not groups:
        raise VocabularyUnavailable(
            "forbidden_positive_obligations is missing or empty in the pinned package")

    vocabulary: dict[str, tuple[str, ...]] = {}
    for domain, terms in groups.items():
        cleaned = tuple(t for t in terms if isinstance(t, str) and t.strip())
        if not cleaned:
            raise VocabularyUnavailable(f"domain {domain!r} carries no usable term")
        vocabulary[domain] = cleaned

    if sum(len(t) for t in vocabulary.values()) == 0:
        raise VocabularyUnavailable("the vocabulary loaded with zero terms")
    return vocabulary


def term_count() -> int:
    return sum(len(terms) for terms in load_vocabulary().values())


def domain_count() -> int:
    return len(load_vocabulary())


def _flexible(term: str) -> str:
    """A term with its word separators made flexible: space, underscore or hyphen."""
    cleaned = "".join(ch for ch in term.lower() if ch.isalnum() or ch in " _-")
    return re.sub(r"[ _-]+", r"[_\\s-]*", re.escape(cleaned.strip()).replace(r"\ ", " "))


def representative_term() -> str:
    """One fenced term, chosen deterministically, for use as a test probe.

    Callers need a real forbidden term to plant. Selecting it by position rather than by
    name keeps every fenced literal — including domain keys, which are themselves built
    from fenced words — out of repository source.
    """
    every = sorted(t for group in load_vocabulary().values() for t in group)
    return every[0]


def representatives() -> list[tuple[str, str]]:
    """(domain, term) — one representative per domain, chosen deterministically."""
    return [(domain, sorted(terms)[0]) for domain, terms in sorted(load_vocabulary().items())]


def fenced_identifier_pattern() -> tuple[str, int]:
    """A POSIX regex matching any fenced term as a whole identifier component.

    Bounded by start, end or an underscore, so a two-letter term cannot false-positive
    on an ordinary word that merely contains those letters. Used against database
    identifiers.
    """
    vocabulary = load_vocabulary()
    terms = sorted({t for group in vocabulary.values() for t in group})
    alternatives = []
    for term in terms:
        cleaned = "".join(ch for ch in term.lower() if ch.isalnum() or ch in " _-")
        alternatives.append(re.sub(r"[ _-]+", "[_ ]*", cleaned.strip()))
    return "(^|_)(" + "|".join(alternatives) + ")(_|$)", len(terms)


def source_patterns() -> list[tuple[str, str, re.Pattern[str]]]:
    """(domain, term, pattern) for scanning source and prose.

    Each pattern matches its term as a whole word, or as the leading component of an
    identifier, or with its word separators varied (a space, an underscore or a hyphen).
    It refuses to match inside a longer word, so a two-letter term does not fire on an
    ordinary English word that merely contains those letters.
    """
    out: list[tuple[str, str, re.Pattern[str]]] = []
    for domain, terms in sorted(load_vocabulary().items()):
        for term in terms:
            body = _flexible(term)
            pattern = re.compile(
                r"(?<![A-Za-z0-9])" + body + r"(?:[_-][A-Za-z0-9_-]+)?(?![A-Za-z0-9])",
                re.IGNORECASE,
            )
            out.append((domain, term, pattern))
    return out
