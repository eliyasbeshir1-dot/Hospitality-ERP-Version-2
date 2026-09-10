#!/usr/bin/env python3
"""Generate planning/MIGRATION_AND_DOMAIN_OWNERSHIP_MAP.md from the repository.

WHY THIS IS GENERATED, AND WHY HALF OF IT MOVED OUT.

This file was written at M0R and never came under a lock. By M4-A it still opened with
"Current state: no migration exists. This repository contains no migration, no `.sql`
file, no schema and no `migrations/` directory. Not even `0001`." — with twenty-one
migrations on disk. Nothing was wrong with the migrations; the document describing them
had simply stopped being true, and no check could notice because no check read it. That
is the same defect class as the README's undescribed slice and the CI matrix that said
five jobs when there were six.

It is fixed the way the build lead ruled: a DESCRIPTION of the present is derived and
locked, and a RECORD of a past event is anchored and left alone. So the ownership map is
generated from the migrations that exist and the package that governs them, and M0R's
"no migration exists yet, and here is the check that enforced it" moved to
planning/M0R_MIGRATION_RECORD.md, where tools/check_dated_records.py requires it to name
the commit and the date it describes.

WHAT IS DERIVED. The gate distribution comes from the package's own requirements.json.
The migration table comes from the filesystem, and each migration's OWNING DOMAIN is read
out of its SQL — the schemas it creates and the schemas it writes tables into — rather
than from a list here that would go stale on the next migration. The fenced domains come
from the package's forbidden-occurrence vocabulary. The prose lives in
planning/OWNERSHIP_NARRATIVE.md, because a judgement is not something a script discovers.

Usage:
    python3 tools/generate_ownership_map.py --out planning/MIGRATION_AND_DOMAIN_OWNERSHIP_MAP.md
    python3 tools/generate_ownership_map.py --check planning/MIGRATION_AND_DOMAIN_OWNERSHIP_MAP.md
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

REPO = Path(__file__).resolve().parents[1]
NARRATIVE = REPO / "planning" / "OWNERSHIP_NARRATIVE.md"
MIGRATIONS = REPO / "migrations"


class MapUnderivable(RuntimeError):
    """A fact this document states cannot be read out of the repository."""


# What each schema is FOR, in one phrase. The schemas themselves are derived from the
# SQL; only the phrase is written here, and a schema with no entry stops the build rather
# than rendering as a blank — the SLICE_UNDESCRIBED lesson, applied to a domain.
DOMAIN_PURPOSE = {
    "app": "context, row-scope predicate and shared triggers",
    "org": "tenants, outlets, the node tree and device registration",
    "identity": "users, roles, memberships, sessions and step-up",
    "config": "policies, configuration versions, numbering and retention",
    "audit": "the append-only audit ledger every governed change is written to",
    "money": "exact amounts, rates, rounding and allocation",
    "quantity": "exact quantities and units",
    "menu": "items, variants, modifiers, prices, dayparts and translation",
    "safety": "allergens, dietary tags and the warnings a guest is shown",
    "service": "tables, QR resolution, guest sessions, carts and service requests",
    "ordering": "the order aggregate, its ledger and its projections",
    "fulfillment": "routing, station tickets and the fulfillment state machine",
    "notify": "notification templates, deliveries and status wording",
    "integration": "outbound integration runtime and the dead-letter queue",
    "edge": "the outlet continuity node: its deployment profile, its binding to one "
            "outlet, its five services, its identity and its health",
    "ops": "the outlet's physical estate — the node, routers, access points, terminals, "
           "KDS devices and printers — with location and support owner",
    "pos": "terminals, override approval, handover and the staff read models",
    "billing": "checks, allocation, bills, splitting, dispositions and tips",
    "docs": "documents somebody outside this system reads: receipts, their revisions and "
            "reprints, the registered printers and what was put on paper",
    "fiscal": "the fiscal-document port: a request against a receipt, its lifecycle and "
              "its reconciliation status, with no provider's schema inside it",
    "payments": "adapters and the live/simulated boundary, intents, capture, "
                "verification, dual allocation and reversal",
    "cash": "drawer shifts, movements, counts, custody and exceptions",
    "report": "the metric catalog, the readings computed from it, the snapshots taken "
              "when a shift is signed off, and the exports",
    "migration": "the migration history table itself",
    "seed_history": "the seed history table itself",
    "security": "security events and storage allocation",
    "storage_meta": "how much storage the objects the surfaces serve are using",
}

# The gates, in order, and what each one's requirements are about. Counts are derived.
GATE_FOCUS = {
    "M0": "package governance",
    "M0R": "repository conformance",
    "M1": "foundation, security, tenancy, identity, data architecture",
    "M2": "menu, localization, safety, tables, QR, sessions",
    "M3": "orders, waiter, fulfillment, KDS, service requests, notifications",
    "M4": "POS, checks, payments, tips, receipts, cash",
    "M5a": "outlet node, sync, local printing",
    "M5b": "same-QR DNS/TLS, reachability lease, authority fencing",
    "M6": "deployment, backup, reporting, hardening",
}

CREATE_SCHEMA = re.compile(r"^\s*CREATE SCHEMA (?:IF NOT EXISTS )?([a-z_]+)\s*;",
                           re.MULTILINE | re.IGNORECASE)
CREATE_TABLE = re.compile(r"^\s*CREATE TABLE (?:IF NOT EXISTS )?([a-z_]+)\.[a-z_]+",
                          re.MULTILINE | re.IGNORECASE)
# What a migration CHANGES without owning: a table it alters, a type it extends, a
# function it creates or replaces. All three are how a later gate corrects something an
# earlier one applied, and none of them is ownership.
CHANGES = re.compile(
    r"^\s*(?:ALTER TABLE (?:IF EXISTS )?|ALTER TYPE |CREATE (?:OR REPLACE )?FUNCTION )"
    r"([a-z_]+)\.[a-z_]+",
    re.MULTILINE | re.IGNORECASE)


def package_dir() -> Path:
    found = sorted(REPO.glob("docs/*/02_MACHINE_READABLE"))
    if len(found) != 1:
        raise MapUnderivable(
            f"expected exactly one pinned package under docs/, found {len(found)}")
    return found[0]


def owning_domains(sql: str) -> list[str]:
    """The schemas a migration BRINGS INTO BEING, in the order it names them.

    Creating a schema, or creating a table in one, is ownership. ALTERing a table in
    another schema is not — 0021 replaces two functions that belong to service and
    fulfillment and owns neither. So an altered-only schema is reported separately, which
    is what makes "no migration spans domains" a statement with content rather than one
    every migration satisfies by touching nothing.
    """
    created = list(dict.fromkeys(
        [m.lower() for m in CREATE_SCHEMA.findall(sql)]
        + [m.lower() for m in CREATE_TABLE.findall(sql)]))
    return created


def touched_domains(sql: str) -> list[str]:
    return list(dict.fromkeys(m.lower() for m in CHANGES.findall(sql)))


def migration_table() -> str:
    files = sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise MapUnderivable(
            "no migration exists. This document describes the migrations this repository "
            "HAS; the record of the gate at which it had none is "
            "planning/M0R_MIGRATION_RECORD.md")
    rows = ["| Migration | Owning domain | Also changes | Slice |",
            "|---|---|---|---|"]
    for path in files:
        sql = path.read_text(encoding="utf-8")
        owned = owning_domains(sql)
        altered = [d for d in touched_domains(sql) if d not in owned]
        unknown = [d for d in owned + altered if d not in DOMAIN_PURPOSE]
        if unknown:
            raise MapUnderivable(
                f"{path.name} touches schema(s) {unknown}, and DOMAIN_PURPOSE says what "
                f"none of them is for. A domain nobody described is a domain nobody "
                f"reviewed: add it, or explain why the migration creates it")
        rows.append(
            f"| `{path.name}` | {' · '.join(owned) or '—'} "
            f"| {' · '.join(altered) or '—'} | {gate_of(path.name)} |")
    return "\n".join(rows)


# WHICH SLICE WROTE EACH MIGRATION. Stated, not scraped.
#
# The first version of this read the gate out of each file's header comment, and it was
# wrong for nine of twenty-one migrations: a header that explains why a label is being
# added at M4-A naturally mentions M3-A, and the first M-token in the prose is not the
# gate that wrote the file. A diagnostic must not name a cause it did not verify, and a
# generator must not either.
#
# There is no reliable derivation. An applied migration is checksum-locked, so a
# machine-readable gate line cannot be added to one afterwards. So it is stated here
# ONCE, and the completeness is checked in both directions: a migration with no entry
# stops the build, and an entry naming a migration that does not exist stops it too.
MIGRATION_SLICE = {
    "0001": "M1-A", "0002": "M1-B", "0003": "M1-C", "0004": "M1-D", "0005": "M1-D",
    "0006": "M2-A", "0007": "M2-B", "0008": "M2-B", "0009": "M2-C",
    "0010": "M3-A", "0011": "M3-B", "0012": "M3-B", "0013": "M3-C", "0014": "M3-C",
    "0015": "M3-D", "0016": "M3-D", "0017": "M3-D",
    "0018": "M4-A", "0019": "M4-A", "0020": "M4-A", "0021": "M4-A",
    "0022": "M4-B", "0023": "M4-B", "0024": "M4-B", "0025": "M4-B",
    "0026": "M4-C", "0027": "M4-C", "0028": "M4-C", "0029": "M4-C", "0030": "M4-C",
    # 0031 and 0032 land at M4-C too, in the repair that followed the first independent
    # review: an applied migration is checksum-locked, so a repair to what M4-C shipped
    # is a further migration at M4-C rather than an edit of 0027.
    "0031": "M4-C", "0032": "M4-C",
    # 0033 and 0034 are the OP-A repair pass, which the M4 executing review's five P0
    # findings turned into M4's repair rather than a gate of its own. 0033 gives the
    # chosen-secret credential a salt and stored KDF parameters, closing FR-AUTH-007's
    # storage limb, which M1-B never met; 0034 makes a printer test record what the agent
    # did rather than what the caller claimed, and classifies the null device where the
    # path is stored. Both are attributed to the slice whose defect they close.
    "0033": "M1-B", "0034": "M4-C",
    # 0035 is OP-C, and it is attributed to M2-B for the same reason 0033 is attributed to
    # M1-B: the slice whose defect it closes. FR-TAB-003 asked for a table session with an
    # opening source and a host, and M2-B built the table, the column and the enum and
    # never a writer — so the requirement was met in shape and unreachable in fact, and a
    # guest scanning a real placard could not order. The ownership half of it repairs
    # M3-D's handover, which had no first owner to hand over FROM; the basket half repairs
    # M2-C's guest surface, which could add and not take away. One migration, three
    # slices' omissions, filed under the earliest.
    "0035": "M2-B",
    # 0036 is OP-C's second migration and belongs to M3-D, the slice that built the
    # confirmation registry and the waiter surface that reads it. A screen gained an action
    # the registry had never been told about, and the ungraded default — deliberate, with a
    # written reason — made seating unusable. The grade is the repair, and it repairs the
    # gate that owns the registry rather than the gate that added the button.
    "0036": "M3-D",
    # 0037 is OP-D and belongs to M2-A, the slice that built the menu and the publication
    # snapshot. FR-MNU-004's description, ingredients and preparation time were written by
    # the seed and returned by nothing, so the requirement was met in the schema and
    # invisible to a guest. The pending-orders half repairs M3-A's acceptance policy, which
    # had a staff_confirmed branch no screen could serve; filed under the earlier slice.
    "0037": "M2-A",
    # 0038 repairs FR-AUTH-007 and belongs to M1-B, the slice that built the lockout. A
    # successful login was being counted as a failed one, because the speculative failure
    # written before verification was never removed when the attempt resolved as a
    # success. Filed under the slice whose requirement it is, not the pass that found it.
    "0038": "M1-B",
    # 0039 is M5a's own, and the first migration since 0001 that brings a whole domain
    # into being rather than correcting an earlier one. Every gate before this assumed the
    # system runs in one place; FR-EDG-001 says a production outlet may not. The schema is
    # the outlet continuity node: what it is bound to, what it is made of, what it proves
    # about itself and what it reports.
    "0039": "M5a",
    # 0040 is M5a's second, and owns `ops` for one table: the outlet's physical estate.
    # It is a separate migration rather than a section of 0039 because the two own
    # different domains, and "no migration spans domains" is a statement this map makes
    # about every row in it.
    "0040": "M5a",
    # 0041 is M5a's synchronization runtime and owns `integration`, the schema M3-C
    # created for the dead-letter queue and left otherwise empty. The outbox, the inbox,
    # the cursors and the evidence ledger are one mechanism and land as one migration.
    "0041": "M5a",
    # 0042 owns nothing: it creates no table and no schema. It repairs
    # app.refuse_financial_mutation(), whose message cited a classification that does not
    # exist for four of the tables it guards — pos.counter_order_entry since M4-C, and the
    # three M5a was about to add. Attributed to M4-C, the slice that attached the guard to
    # a table outside the financial schemas and made the sentence false.
    "0042": "M4-C",
    # 0043 is M5a's conflict policy and reconnection, and owns `integration` alongside
    # 0041 for the same reason: a conflict is a synchronization outcome, and putting it
    # anywhere else would separate the disagreement from the mechanism that found it.
    "0043": "M5a",
    # 0044 is M5a's durable print queue and owns `docs`, the schema M4-C built the
    # receipt and its evidence in. The queue is the half M4-C did not build: it recorded
    # what the agent DID and nothing held a receipt between "settle this bill" and "the
    # agent got round to it".
    "0044": "M5a",
    # 0045 is M5a's third `edge` migration: what the node holds before service, what it
    # may do when it is alone, and what it says about both. Three requirements that look
    # unrelated and are one question asked from three angles.
    "0045": "M5a",
    # 0046 repairs 0039 and is attributed to M5a, the slice that wrote it. The
    # wrong-outlet refusal FR-CFG-001E turns on was unreachable: the lookup was scoped by
    # the outlet it was about to check, so a node at the wrong outlet was told it did not
    # exist. Found by starting the process rather than by reading the function.
    "0046": "M5a",
    # 0047 gives edge.plain_language a third namespace and adds the banner FR-EDG-009's
    # strip reads. Also M5a's, and also a repair: the first connectivity_banner() treated
    # "I could not see a node" as "there is no node" and answered CONNECTED.
    "0047": "M5a",
    # 0048 is FR-OPS-010: signed updates, the database compatibility check, and a rollback
    # that has to prove it did not lose queued work.
    "0048": "M5a",
    # 0049 opens M5b: the bidirectional reachability lease FR-EDG-023 specifies down to
    # the second. It owns `edge` alongside M5a's, because a lease is a fact about a node.
    "0049": "M5b",
    # 0050 is FR-EDG-024: one writer per outlet, as a monotonic sequence, and the four
    # things a replacement must show before it may hold one.
    "0050": "M5b",
    # 0051 retires M5a's one-active-node-per-outlet index. It owns nothing: it drops an
    # index and replaces two comments. Attributed to M5b because M5b is what makes the
    # index wrong — FR-EDG-024 requires a STANDBY, and a standby that cannot exist
    # alongside the node it stands by is a spare in a cupboard.
    "0051": "M5b",
    # 0052 registers node.authority.claim as a governed action. Attributed to M1-B, the
    # slice that owns the step-up registry: 0050 required a grant and named no action, so
    # any live grant would have done. This is the third time a new governed action has
    # needed all three of trigger, installer and caller.
    "0052": "M1-B",
    # 0053 is FR-OPS-017 and FR-EDG-022A/B/C: one hostname per outlet, the certificate's
    # life, and three of the four prohibitions as constraints. The fourth — a manual
    # browser bypass — is a property of a surface and is asserted where surfaces are.
    "0053": "M5b",
    # 0054 is FR-EDG-028: the four ways a real phone resolves a name, both address
    # families on both horizons, and the translated guidance an unsupported one gets.
    "0054": "M5b",
    # 0055 adds the certificate state machine's entrance. Attributed to M5b because 0053
    # is: writing seeds/0016 showed that edge.node_certificate had an install path and no
    # request path, so the only way in was a bare INSERT.
    "0055": "M5b",
    # 0056 repairs 0054's bypass check, which never ran: `~*` and `||` share a precedence
    # class, so the pattern was half a regex with an unclosed parenthesis.
    "0056": "M5b",
    # 0057 is FR-EDG-026: what a node needs to answer for a session the cloud started, so
    # a retry across the cloud-to-LAN transition is absorbed rather than cooked twice.
    "0057": "M5b",
    # 0058 repairs 0057's cast to identity.authentication_strength, a type that has never
    # existed. The second migration in this gate to apply cleanly and be unrunnable.
    "0058": "M5b",
}


def gate_of(filename: str) -> str:
    number = filename[:4]
    if number not in MIGRATION_SLICE:
        raise MapUnderivable(
            f"{filename} has no entry in MIGRATION_SLICE, so which slice wrote it cannot "
            f"be stated. Add one: an applied migration is checksum-locked, so this cannot "
            f"be read out of the file after the fact and has to be recorded when the "
            f"migration lands")
    return MIGRATION_SLICE[number]


def gate_distribution(active: list[dict]) -> str:
    counts: dict[str, int] = {}
    for requirement in active:
        counts[requirement.get("introduced_at", "?")] = \
            counts.get(requirement.get("introduced_at", "?"), 0) + 1
    unknown = sorted(set(counts) - set(GATE_FOCUS))
    if unknown:
        raise MapUnderivable(
            f"the package introduces requirements at gate(s) {unknown}, and GATE_FOCUS "
            f"describes none of them")
    rows = ["| Gate | Requirements | Domain focus |", "|---|---:|---|"]
    for gate in GATE_FOCUS:
        rows.append(f"| {gate} | {counts.get(gate, 0)} | {GATE_FOCUS[gate]} |")
    rows.append(f"| **Total** | **{sum(counts.values())}** | |")
    return "\n".join(rows)


def fenced_domains() -> str:
    from fenced import load_vocabulary
    vocabulary = load_vocabulary()
    return " · ".join(sorted(vocabulary))


def build() -> str:
    machine = package_dir()
    requirements = json.loads((machine / "requirements.json").read_text(encoding="utf-8"))
    active = requirements["active_requirements"]
    from fenced import domain_count, term_count

    files = sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    stale = sorted(set(MIGRATION_SLICE) - {f.name[:4] for f in files})
    if stale:
        raise MapUnderivable(
            f"MIGRATION_SLICE names migration(s) {stale} that do not exist. An entry for "
            f"a file nobody can open is how a table comes to describe a repository that "
            f"is not this one")
    schemas = sorted({d for f in files
                      for d in owning_domains(f.read_text(encoding="utf-8"))})

    substitutions = {
        "{{GATE_DISTRIBUTION}}": gate_distribution(active),
        "{{ACTIVE_REQUIREMENTS}}": str(len(active)),
        "{{MIGRATION_TABLE}}": migration_table(),
        "{{MIGRATION_COUNT}}": str(len(files)),
        "{{FIRST_MIGRATION}}": f"`{files[0].name}`",
        "{{LAST_MIGRATION}}": f"`{files[-1].name}`",
        "{{DOMAIN_COUNT}}": str(len(schemas)),
        "{{DOMAINS}}": "\n".join(
            f"- **`{name}`** — {DOMAIN_PURPOSE[name]}" for name in schemas),
        "{{FENCED_DOMAINS}}": fenced_domains(),
        "{{FENCED_DOMAIN_COUNT}}": str(domain_count()),
        "{{FENCED_TERM_COUNT}}": str(term_count()),
    }

    template = NARRATIVE.read_text(encoding="utf-8")
    for marker, value in substitutions.items():
        if marker not in template:
            raise MapUnderivable(f"marker {marker} is absent from {NARRATIVE.name}")
        template = template.replace(marker, value)
    if "{{" in template:
        raise MapUnderivable("an unsubstituted marker remains in the narrative")
    return template


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the ownership map.")
    ap.add_argument("--out")
    ap.add_argument("--check")
    args = ap.parse_args()
    if not args.out and not args.check:
        ap.error("one of --out or --check is required")

    try:
        generated = build()
    except MapUnderivable as error:
        print("FAIL OWNERSHIP_MAP_UNDERIVABLE", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1

    if args.check:
        path = Path(args.check)
        if not path.exists():
            print(f"FAIL OWNERSHIP_MAP_ABSENT — {path} does not exist", file=sys.stderr)
            return 1
        if path.read_text(encoding="utf-8") != generated:
            print("FAIL OWNERSHIP_MAP_DRIFT — the committed map does not match a fresh "
                  "generation", file=sys.stderr)
            for line in list(difflib.unified_diff(
                    path.read_text(encoding="utf-8").splitlines(), generated.splitlines(),
                    fromfile="committed", tofile="generated", lineterm="", n=1))[:40]:
                print(f"  {line}", file=sys.stderr)
            return 1
        print("PASS OWNERSHIP_MAP_MATCHES_REPOSITORY")
        print(f"  {len(generated.splitlines())} lines verified against the repository")
        return 0

    # LF explicitly: text mode would write CRLF on Windows and LF on Linux, so the
    # artefact would differ by the platform that generated it while --check compares
    # it against one committed copy.
    Path(args.out).write_text(generated, encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(generated.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
