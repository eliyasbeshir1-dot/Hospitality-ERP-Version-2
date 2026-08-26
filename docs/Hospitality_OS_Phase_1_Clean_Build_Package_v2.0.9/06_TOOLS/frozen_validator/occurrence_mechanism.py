"""Hospitality OS forbidden-occurrence mechanism.

Replaces free-text semantic authorization with exact occurrence classification.

The scanner DETECTS occurrences of the controlled vocabulary across the canonical
governed fields. It does not decide whether English wording is safe. Authorization
comes exclusively from the canonical forbidden occurrence registry, which lives
inside the canonical content root and can only change by canonical amendment.

Every occurrence must have exactly one approved registry entry. Anything unknown,
changed, stale, duplicated or mismatched fails closed.

Standard library only.
"""
from __future__ import annotations
import hashlib, json, re, unicodedata

NORMALIZATION_VERSION = "1.0"

# --------------------------------------------------------------- normalization
# Deliberately conservative. This is a trust boundary: it is the only path by
# which canonical text may change without a registry amendment.
#   - Unicode NFC only (never NFKC: NFKC folds compatibility and presentation
#     forms, which would collapse distinct Amharic and Arabic excerpts).
#   - CRLF/CR to LF.
#   - Runs of whitespace collapse to one space; leading/trailing space stripped.
#   - No punctuation stripping, no case folding, no semantic rewriting.
_WS = re.compile(r"[ \t\u00a0\u2000-\u200a\u202f\u205f\u3000]+")


def normalize(text: str) -> str:
    if text is None:
        return ""
    t = unicodedata.normalize("NFC", str(text))
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = _WS.sub(" ", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    return t.strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------- sentences
# Sentence identity is part of the occurrence key: moving a term into a different
# sentence invalidates its entry.
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")


def sentences(text: str):
    out, pos = [], 0
    norm = normalize(text)
    for part in _SENT.split(norm):
        s = part.strip()
        if s:
            out.append(s)
    return out


# --------------------------------------------------------------- vocabulary
def bounded(term: str) -> re.Pattern:
    """Word-bounded, whitespace-flexible, case-insensitive term matcher."""
    escaped = re.escape(term).replace(r"\ ", r"\s+")
    return re.compile(r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])", re.I)


def term_id(domain: str, term: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", term.upper()).strip("_")
    return f"TERM-{slug}"


def load_vocabulary(rules: dict):
    """Vocabulary is generated from the excluded-domain set. Longest terms first so
    a multi-word term wins over its own substring."""
    vocab = []
    seen = set()
    for domain, terms in sorted(rules.get("forbidden_positive_obligations", {}).items()):
        for term in sorted(set(terms), key=len, reverse=True):
            tid = term_id(domain, term)
            if tid in seen:
                continue
            seen.add(tid)
            vocab.append({"term_id": tid, "term": term, "domain": domain,
                          "pattern": bounded(term)})
    return vocab


# --------------------------------------------------------------- detection
def detect_in_text(record_type, record_id, field, text, vocab):
    """Yield every vocabulary occurrence with its full composite key.

    Overlapping matches are resolved longest-term-first: once a span is claimed by
    a longer term, a shorter term nested inside it is not reported separately.
    """
    found = []
    for sent_index, sentence in enumerate(sentences(text)):
        claimed = []
        sent_hash = sha256_text(sentence)
        per_term = {}
        for v in vocab:
            for m in v["pattern"].finditer(sentence):
                span = (m.start(), m.end())
                if any(span[0] >= c[0] and span[1] <= c[1] for c in claimed):
                    continue
                claimed.append(span)
                per_term.setdefault(v["term_id"], 0)
                per_term[v["term_id"]] += 1
                excerpt = sentence[m.start():m.end()]
                found.append({
                    "record_type": record_type,
                    "record_id": record_id,
                    "field": field,
                    "term_id": v["term_id"],
                    "term": v["term"],
                    "domain": v["domain"],
                    "normalization_version": NORMALIZATION_VERSION,
                    "sentence_index": sent_index,
                    "normalized_sentence": sentence,
                    "normalized_sentence_sha256": sent_hash,
                    "occurrence_ordinal": per_term[v["term_id"]],
                    "exact_excerpt": excerpt,
                    "excerpt_sha256": sha256_text(excerpt),
                    "diagnostic_char_offset": m.start(),
                })
    return found


def occurrence_key(o: dict) -> tuple:
    """Authoritative identity. Character offsets are diagnostics only and are
    deliberately excluded."""
    return (o["record_type"], o["record_id"], o["field"], o["term_id"],
            o["normalized_sentence_sha256"], o["occurrence_ordinal"],
            o["excerpt_sha256"])


# --------------------------------------------------------------- governed fields
def iter_governed_values(machine_dir, governed_spec):
    """Yield (record_type, record_id, field, text) for every governed field.

    Fails loudly if a configured container, id field or governed field has vanished
    from the canonical schema: silence here would mean undetected surface.
    """
    import os
    errors = []
    for entry in governed_spec["governed_fields"]:
        path = os.path.join(machine_dir, entry["file"])
        if not os.path.exists(path):
            errors.append(("GOVERNED_FILE_MISSING", entry["file"]))
            continue
        doc = json.load(open(path, encoding="utf-8"))
        container = doc.get(entry["container"])
        if not isinstance(container, list):
            errors.append(("GOVERNED_CONTAINER_MISSING",
                           f"{entry['file']}:{entry['container']}"))
            continue
        for rec in container:
            rid = rec.get(entry["id_field"])
            if rid is None:
                errors.append(("GOVERNED_ID_FIELD_MISSING",
                               f"{entry['file']}:{entry['id_field']}"))
                continue
            for field in entry["fields"]:
                if field not in rec:
                    continue
                val = rec[field]
                if isinstance(val, str):
                    yield entry["record_type"], rid, field, val
                elif isinstance(val, list):
                    for i, item in enumerate(val):
                        if isinstance(item, str):
                            yield entry["record_type"], rid, f"{field}[{i}]", item
            for sub in entry.get("subrecords", []):
                for child in rec.get(sub["container"], []) or []:
                    cid = child.get(sub["id_field"], rid)
                    for field in sub["fields"]:
                        if field in child and isinstance(child[field], str):
                            yield sub["record_type"], cid, field, child[field]
    if errors:
        raise RuntimeError(f"governed field specification does not match canonical schema: {errors}")


def detect_all(machine_dir, governed_spec, vocab):
    out = []
    for rt, rid, field, text in iter_governed_values(machine_dir, governed_spec):
        out.extend(detect_in_text(rt, rid, field, text, vocab))
    return out
