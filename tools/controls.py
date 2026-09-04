#!/usr/bin/env python3
"""The negative controls: what each one is, and what the run says about it.

ONE REGISTRY, AND THE RUN IS THE AUTHORITY OVER IT.

A control is a real defect, planted, required to produce its exact registered signature,
then reverted and required to pass again. Three things need to agree about which controls
exist: the evidence report that tabulates them, the CI step that refuses a build unless
each went red and green, and the CI matrix that says how many there are. Before this
module they were three separate lists, and a fourth number lived in a review brief that
said 62 when the artifact said 76. The artifact was right; the prose had been carried
forward and never re-derived.

So the descriptions live here once, and `check_against_run()` compares them with what the
suites actually printed. A control the suites prove and nobody describes fails the build
by name, exactly as an undescribed slice does — the reverse direction, a control described
and never proved, was already caught by the evidence report's "not proven" row and is
asserted here too. Neither list can drift from the run while both are checked against it.

Anything that STATES a number asks this module for it. There is no second place to count.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console import use_utf8_output  # noqa: E402


class ControlDrift(RuntimeError):
    """The registry and the run disagree about which controls exist."""


# (identifier, what it proves, the signature it must produce, the suite that proves it)
CONTROLS = [
    ("NC-M1-001", "Fail-closed tenant context", "VISIBLE_OR_WRITABLE_ROWS_WITHOUT_CONTEXT", "m1a"),
    ("NC-M1-002", "Sibling-outlet isolation", "SIBLING_OUTLET_ACCESS", "m1a"),
    ("NC-M1-003", "Future schema protection", "OUTLET_POLICY_NOT_UPGRADED", "m1a"),
    ("NC-M1-004", "Runtime least privilege", "PRIVILEGED_RUNTIME_ROLE_REJECTED", "m1a"),
    ("NC-M1B-001", "Session survives role removal", "SESSION_SURVIVED_ROLE_REMOVAL", "m1b"),
    ("NC-M1B-002", "Quick PIN for a governed action", "LOW_RISK_CREDENTIAL_USED_FOR_SENSITIVE_ACTION", "m1b"),
    ("NC-M1B-003", "Step-up recency ignored", "STALE_STEP_UP_ACCEPTED", "m1b"),
    ("NC-M1B-004", "Principal outside its scope", "OUT_OF_SCOPE_PRINCIPAL_ACCEPTED", "m1b"),
    ("NC-M1B-005", "Context outlives its transaction", "CONTEXT_SURVIVED_COMMIT", "m1b"),
    ("NC-M1C-001", "Audit mutated by ordinary role", "AUDIT_MUTATED_BY_ORDINARY_ROLE", "m1c"),
    ("NC-M1C-002", "Inexact money type", "INEXACT_MONEY_TYPE_ACCEPTED", "m1c"),
    ("NC-M1C-003", "Entitlement defaulting open", "UNKNOWN_ENTITLEMENT_DEFAULTED_OPEN", "m1c"),
    ("NC-M1C-004", "Retention deleting audit", "APPEND_ONLY_VIOLATED", "m1c"),
    ("NC-M1C-005", "Numbering collision", "DUPLICATE_DOCUMENT_NUMBER_ISSUED", "m1c"),
    ("NC-M1D-001", "Privileged runtime credential", "PRIVILEGED_RUNTIME_CREDENTIAL_ACCEPTED", "m1d"),
    ("NC-M1D-002", "Readiness green with broken job", "READINESS_GREEN_WITH_BROKEN_JOB", "m1d"),
    ("NC-M1D-003", "Secret emitted in logs", "SECRET_EMITTED_IN_LOGS", "m1d"),
    ("NC-M1D-004", "Required header absent", "REQUIRED_HEADER_ABSENT", "m1d"),
    ("NC-M1D-005", "Seed checksum lock bypassed", "SEED_CHECKSUM_LOCK_BYPASSED", "m1d"),
    ("NC-M1D-006", "Route served without context", "ROUTE_SERVED_WITHOUT_CONTEXT", "m1d"),
    ("NC-M1D-007", "Readiness reads a stale role snapshot", "READINESS_GREEN_WITH_PRIVILEGED_ROLE", "m1d"),
    ("NC-M1D-008", "Readiness discloses deployment detail", "READINESS_DISCLOSES_DEPLOYMENT_DETAIL", "m1d"),
    ("NC-M2A-001", "Snapshot mutated after publish", "IMMUTABLE_SNAPSHOT_ALTERED", "m2a"),
    ("NC-M2A-002", "Inexact or currency-less price", "INEXACT_PRICE_TYPE_ACCEPTED", "m2a"),
    ("NC-M2A-003", "Availability discloses a figure", "EXACT_QUANTITY_DISCLOSED", "m2a"),
    ("NC-M2A-004", "Publish with a locale missing", "REQUIRED_TRANSLATION_MISSING", "m2a"),
    ("NC-M2A-005", "Daypart in server time", "WRONG_DAYPART_AT_BOUNDARY", "m2a"),
    ("NC-M2-001", "QR reference enumerable", "ENUMERABLE_QR_REFERENCE", "m2b"),
    ("NC-M2-002", "Foreign session accepted", "FOREIGN_SESSION_ACCEPTED", "m2b"),
    ("NC-M2-003", "Publish with safety text missing", "REQUIRED_SAFETY_TRANSLATION_MISSING", "m2b"),
    ("NC-M2B-004", "Allergen conveyed by icon alone", "WRITTEN_WARNING_ABSENT", "m2b"),
    ("NC-M2B-005", "Declaration not re-evaluated", "STALE_DECLARATION_SERVED", "m2b"),
    ("NC-M2B-006", "Stale QR joins a later occupancy", "STALE_SESSION_ADMITTED", "m2b"),
    ("NC-M2B-007", "Ownership moved without acknowledgement", "OWNERSHIP_TRANSFERRED_SILENTLY", "m2b"),
    ("NC-M2B-008", "Pinned reference readable by display", "AUDIT_REFERENCE_DISCLOSED_TO_DISPLAY", "m2b"),
    ("NC-M2B-009", "Correction withheld from a published menu", "CORRECTION_WITHHELD_FROM_PUBLISHED_MENU", "m2b"),
    ("NC-M2B-010", "Archive policy deletes instead", "ARCHIVE_POLICY_DELETED_ROWS", "m2b"),
    ("NC-M2-004", "Arabic does not lay out right-to-left", "RTL_LAYOUT_OR_READING_ORDER_FAILURE", "m2c"),
    ("NC-M2C-005", "Icon rendered without its warning", "WRITTEN_WARNING_ABSENT_FROM_RENDER", "m2c"),
    ("NC-M2C-006", "State told by colour alone", "STATE_CONVEYED_BY_COLOUR_ALONE", "m2c"),
    ("NC-M2C-007", "Language change loses the basket", "CART_LOST_ON_LOCALE_CHANGE", "m2c"),
    ("NC-M2C-008", "A locale renders only partly", "INCOMPLETE_LOCALE_RENDER", "m2c"),
    ("NC-M2C-009", "Retry commits a second time", "DUPLICATE_COMMITMENT_ON_RETRY", "m2c"),
    ("NC-M2C-010", "Chosen locale not recorded", "LOCALE_SNAPSHOT_ABSENT", "m2c"),
    ("NC-M3-001", "A retry produces a second effect", "DUPLICATE_ORDER_EFFECT", "m3a"),
    ("NC-M3-002", "Price moved between preview and submission", "STALE_PRICE_ACCEPTED", "m3a"),
    ("NC-M3-003", "Allergy declaration lost on a hop", "ALLERGY_FLAG_LOST", "m3a"),
    ("NC-M3-005", "Client-stated total is stored", "CLIENT_CALCULATED_TOTAL_ACCEPTED", "m3a"),
    ("NC-M3-006", "Accepted order edited destructively", "ACCEPTED_ORDER_MUTATED", "m3a"),
    ("NC-M3-007", "Merge or move loses an order", "ORDER_LOST_ON_SESSION_CHANGE", "m3a"),
    ("NC-M3-008", "Private staff note reaches a customer", "PRIVATE_NOTE_DISCLOSED", "m3a"),
    ("NC-M3-009", "Rebuild diverges from the ledger", "REBUILD_NOT_DETERMINISTIC", "m3a"),
    ("NC-M3-004", "Illegal ticket transition accepted", "ILLEGAL_TRANSITION_ACCEPTED", "m3b"),
    ("NC-M3B-001", "Allergy emphasis lost at a station", "ALLERGY_EMPHASIS_LOST_AT_STATION", "m3b"),
    ("NC-M3B-002", "A recall duplicates completed work", "DUPLICATED_WORK_ON_RECALL", "m3b"),
    ("NC-M3B-003", "A transfer duplicates a ticket", "DUPLICATED_WORK_ON_TRANSFER", "m3b"),
    ("NC-M3B-004", "Printer fallback emits a second ticket", "DUPLICATE_STATION_TICKET", "m3b"),
    ("NC-M3B-005", "Expo releases an incomplete set", "INCOMPLETE_SET_SERVED", "m3b"),
    ("NC-M3B-006", "Priority applied with no attributed actor", "PRIORITY_WITHOUT_ATTRIBUTION", "m3b"),
    ("NC-M3C-001", "Deduplication swallows a deliberate repeat", "DELIBERATE_REPEAT_SUPPRESSED", "m3c"),
    ("NC-M3C-002", "Accidental repeated taps raise a second alert", "DUPLICATE_ALERT_EMITTED", "m3c"),
    ("NC-M3C-003", "Staff identity reaches a customer screen unconfigured", "STAFF_IDENTITY_DISCLOSED", "m3c"),
    ("NC-M3C-004", "Presence survives its retention window", "EPHEMERAL_PRESENCE_RETAINED", "m3c"),
    ("NC-M3C-005", "Sensitive data reaches a notification payload", "SENSITIVE_DATA_IN_NOTIFICATION", "m3c"),
    ("NC-M3C-006", "A deep link resolves for an unauthorized session", "DEEP_LINK_CROSSES_SESSION_SCOPE", "m3c"),
    ("NC-M3C-007", "A dead-letter replay causes a duplicate effect", "DUPLICATE_EFFECT_ON_REPLAY", "m3c"),
    ("NC-M3D-001", "Waiter-entered order bypasses a rule QR ordering enforces", "CHANNEL_RULE_DIVERGENCE", "m3d"),
    ("NC-M3D-002", "Manager override completes without step-up", "OVERRIDE_WITHOUT_STEP_UP", "m3d"),
    ("NC-M3D-003", "Override succeeds by credential sharing, not delegation", "CREDENTIAL_SHARED_FOR_OVERRIDE", "m3d"),
    ("NC-M3D-004", "Staff search returns a row outside the searcher's scope", "STAFF_SEARCH_CROSSES_SCOPE", "m3d"),
    ("NC-M3D-005", "Allergy confirmation carries ordinary friction", "FRICTION_NOT_GRADED_BY_CONSEQUENCE", "m3d"),
    ("NC-M3D-006", "A destructive action proceeds with no reason", "DESTRUCTIVE_ACTION_WITHOUT_REASON", "m3d"),
    ("NC-M3D-007", "Handover leaves a table with no responsible owner", "RESPONSIBILITY_LOST_ON_HANDOVER", "m3d"),
    ("NC-M3D-008", "A landed slice the README describes nowhere", "SLICE_UNDESCRIBED", "m3d"),
    ("NC-M3D-009", "A suite exists and nothing says what it covers", "SUITE_UNDESCRIBED", "m3d"),
    ("NC-M3D-010", "A cross-cutting suite that declares no span", "SUITE_SPAN_UNDECLARED", "m3d"),
    ("NC-M3D-011", "A description states a fact the generator can derive", "DESCRIPTION_NAMES_A_DERIVABLE_FACT", "m3d"),
    ("NC-M3D-012", "The CI matrix stops describing the pipeline", "CI_MATRIX_DRIFT", "m3d"),
    ("NC-M3D-013", "A control the suites prove and no document describes", "CONTROL_UNDESCRIBED", "m3d"),
    ("NC-M4-001", "A tip preselected for the guest", "TIP_PRESELECTED", "m4a"),
    ("NC-M4-002", "A tip counted towards a bill balance", "TIP_COMMINGLED_WITH_BILL", "m4a"),
    ("NC-M4A-001", "A closure completer moved later with no reason", "PARTIAL_CLOSURE_COMPLETER_MOVED_LATER", "m4a"),
    ("NC-M4A-002", "A line quantity billed on two checks", "QUANTITY_DOUBLE_BILLED", "m4a"),
    ("NC-M4A-003", "A split that loses or creates a minor unit", "SPLIT_NOT_EXACT", "m4a"),
    ("NC-M4A-004", "A bill finalized with an unsettled balance", "BILL_FINALIZED_UNSETTLED", "m4a"),
    ("NC-M4A-005", "An issued bill corrected by deletion", "BILL_DELETED_NOT_CREDITED", "m4a"),
    ("NC-M4A-006", "A per-payer tip that reallocates bill lines", "TIP_REALLOCATED_BILL", "m4a"),
    ("NC-M4A-007", "The counter channel on an order path of its own", "CHANNEL_RULE_DIVERGENCE", "m4a"),
    ("NC-M4A-008", "A finalized bill with no calculation version", "CALCULATION_VERSION_MISSING", "m4a"),
    ("NC-M4-003", "A simulated or unverified result recorded as money received", "UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM", "m4b"),
    ("NC-M4-004", "A cashier approving their own refund or their own count", "SELF_APPROVAL_ACCEPTED", "m4b"),
    ("NC-M4-006", "A reopened cash shift closed without being resolved", "REOPENED_SHIFT_NOT_RESOLVED", "m4b"),
    ("NC-M4B-001", "Raw card data reaching storage, a log or analytics", "CARD_DATA_RETAINED", "m4b"),
    ("NC-M4B-002", "A payment allocation recomputed on read", "ALLOCATION_RECOMPUTED_ON_READ", "m4b"),
    ("NC-M4B-003", "A tip merged into sales revenue in reconciliation", "TIP_MERGED_INTO_REVENUE", "m4b"),
    ("NC-M4B-004", "A retry that produces a second payment", "DUPLICATE_PAYMENT_ON_RETRY", "m4b"),
    ("NC-M4B-005", "A finalized cash shift that accepts a movement", "FINALIZED_SHIFT_MUTATED", "m4b"),
    ("NC-M4B-006", "A proof confirmation accepted with no attributor", "VERIFICATION_WITHOUT_ATTRIBUTOR", "m4b"),
    ("NC-M4B-007", "An incompatible peer version silently accepted", "UNKNOWN_SCHEMA_ACCEPTED", "m4b"),
    ("NC-M4B-008", "A closure resting on a completer that is itself incomplete", "PARTIAL_CLOSURE_COMPLETER_INCOMPLETE", "m4b"),
    ("NC-M4B-009", "A verification suite the evidence report does not count", "SUITE_UNACCOUNTED", "m4b"),
    ("NC-M4B-010", "A correlation link kind no rebuild puts back", "CORRELATION_KIND_UNOWNED", "m4b"),
    ("NC-M4B-011", "A suite's controls searched for in logs that cannot contain them", "CONTROL_LOG_ABSENT", "m4b"),
    ("NC-M4-005", "The packaged Ethiopic font gone from the receipt print path", "ETHIOPIC_FONT_FALLBACK_ON_RECEIPT", "m4c"),
    ("NC-M4C-001", "One settlement printed as two original receipts", "RECEIPT_ALREADY_PRINTED", "m4c"),
    ("NC-M4C-002", "A bill total line on a receipt carrying the tip", "TIP_MERGED_ON_RECEIPT", "m4c"),
    ("NC-M4C-003", "A non-English receipt falling back to English on paper", "RECEIPT_INCOMPLETE_IN_LOCALE", "m4c"),
    ("NC-M4C-004", "A summary of an empty window reported as a figure", "FABRICATED_METRIC", "m4c"),
    ("NC-M4C-005", "A recomputation writing over a signed-off shift result", "LEDGER_ROW_DELETED_NOT_REVERSED", "m4c"),
    ("NC-M4C-006", "Money on a bill that no sales classification claims", "SALES_COMPONENT_UNCLASSIFIED", "m4c"),
    ("NC-M4C-007", "A counter order that can name no POS terminal", "COUNTER_ORDER_WITHOUT_A_TERMINAL", "m4c"),
    ("NC-M4C-008", "A customer receipt printed on a printer nobody tested", "PRINTER_NEVER_TESTED", "m4c"),
]


def signatures_for(gate: str) -> list[str]:
    """Every failure signature owned by a gate, from the registry rather than a list.

    Used by tests/m4b to check each signature against the package's fenced vocabulary
    programmatically. Matched on the identifier so that both NC-M4-00n and NC-M4B-00n
    answer to "M4" — the gate owns them, the slice merely proved them.
    """
    prefix = f"NC-{gate.upper()}"
    return sorted({c[2] for c in CONTROLS
                   if c[0].startswith(prefix)
                   and re.fullmatch(rf"{re.escape(prefix)}[A-Z]?-\d+", c[0])})


# A control identifier: the gate that owns it and a three-digit ordinal. Matched against
# the suite logs rather than against the suite SOURCES, because what matters is that the
# control RAN — a control commented out is a control that no longer exists, and its source
# would still name it.
IDENTIFIER = re.compile(r"NC-[A-Z0-9]+-\d+")

_RESULT = re.compile(
    # "[PASS] (asserted) NC-M3D-001  a waiter-entered order … — RED with the defect planted"
    #
    # The evidence prefix is optional because only the rendering suites carry one, and the
    # description between the identifier and the marker is optional because only M3-D
    # writes one. Anchoring on adjacency instead reported ten proved controls as missing.
    r"\[PASS\] (?:\([a-z]+\) )?(NC-[A-Z0-9]+-\d+)[^\n]*? — (RED|GREEN)")


def described() -> dict[str, tuple[str, str, str]]:
    """The registry, keyed by identifier."""
    return {c[0]: (c[1], c[2], c[3]) for c in CONTROLS}


def proved(logs: Path) -> dict[str, dict[str, set[str]]]:
    """What the run says: {identifier: {"RED": {suite…}, "GREEN": {suite…}}}.

    Read from the logs, so this is the controls that actually executed on this run rather
    than the ones somebody wrote down.
    """
    found: dict[str, dict[str, set[str]]] = {}
    for path in sorted(logs.glob("*.log")):
        suite = path.stem
        text = path.read_text(encoding="utf-8", errors="ignore")
        for identifier, marker in _RESULT.findall(text):
            found.setdefault(identifier, {"RED": set(), "GREEN": set()})[marker].add(suite)
    return found


def check_against_run(logs: Path) -> None:
    """Refuse when the registry and the run disagree about which controls exist.

    Raises ControlDrift naming the direction of the disagreement. Both directions matter
    and they fail differently: a control nobody describes is invisible in every document,
    and a control nobody proves is a coverage gap wearing a green badge.
    """
    registry = described()
    run = proved(logs)
    if not run:
        raise ControlDrift(
            f"CONTROL_REGISTRY_UNVERIFIABLE: no control result found in any log under "
            f"{logs}. A registry checked against nothing would agree with anything, so "
            f"this is a failure rather than a silent pass")

    undescribed = sorted(set(run) - set(registry))
    if undescribed:
        raise ControlDrift(
            f"CONTROL_UNDESCRIBED: {undescribed} went red and green in this run and no "
            f"entry in tools/controls.py says what they prove. Add one: every document "
            f"that counts controls counts this registry, so a control missing from it is "
            f"a control missing from the evidence report, from the CI matrix and from the "
            f"step that requires each to have been proved")

    unproved = sorted(set(registry) - set(run))
    if unproved:
        raise ControlDrift(
            f"CONTROL_NOT_IN_THIS_RUN: {unproved} are described and did not appear in "
            f"this run's logs. Either the suite stopped proving them or a log is missing "
            f"from the set handed to this check")

    misattributed = sorted(
        f"{identifier} (registry says {registry[identifier][2]}, "
        f"proved in {sorted(markers['RED'] | markers['GREEN'])})"
        for identifier, markers in run.items()
        if registry[identifier][2] not in (markers["RED"] | markers["GREEN"]))
    if misattributed:
        raise ControlDrift(
            f"CONTROL_SUITE_MISATTRIBUTED: {misattributed}. The registry names the suite "
            f"that proves each control, and the evidence report reads that suite's log to "
            f"decide whether it went red — so a wrong name reports a proved control as "
            f"not proven")


def count() -> int:
    return len(CONTROLS)


def by_gate() -> list[tuple[str, int]]:
    """How many controls each gate owns, derived from the identifiers themselves.

    NC-M1-001 and NC-M1B-001 both belong to M1: the letter is the slice within the gate,
    and a gate's total is what a reader of the matrix wants.
    """
    tally: dict[str, int] = {}
    for identifier, _p, _s, _suite in CONTROLS:
        gate = re.fullmatch(r"NC-(M\d)[A-Z]?-\d+", identifier)
        if not gate:
            raise ControlDrift(
                f"CONTROL_IDENTIFIER_UNPARSEABLE: {identifier} does not name a gate, so "
                f"no distribution can be derived from it")
        tally[gate.group(1)] = tally.get(gate.group(1), 0) + 1
    return sorted(tally.items())


class ControlUnproved(RuntimeError):
    """A registered control did not go red and then green in the run being checked."""


def check_red_then_green(logs: Path) -> int:
    """Every registered control went RED and then GREEN in the log of the suite that owns it.

    CI asserted this in shell, over a hand-written list of log files. The list stopped at
    m4a.log, so the thirteen M4-B controls were searched for in logs that could not contain
    them and every one was reported unproved — and because `grep -c` exits 1 when it
    matches nothing, `pipefail` killed the step before it could print WHICH control was
    missing. The failure was real; the diagnostic was absent and the cause was wrong.

    So it lives here, next to the registry it reads, and CI calls it. One implementation,
    no list, and a suite can plant against it — which is what NC-M4B-011 does.

    Stronger than the shell it replaces in two ways. It requires both markers in the
    OWNING suite's log rather than anywhere in the set, because a control's registry row
    already says which suite proves it and a control proved somewhere else is a
    misattribution the evidence report would render wrongly. And it refuses to run when a
    log it needs is absent, rather than concluding from silence that a control never went
    red: a diagnostic must not name a cause it did not verify.

    Returns the number of controls checked, so a caller can print it rather than restate it.
    """
    registry = described()
    if not registry:
        raise ControlUnproved(
            "CONTROL_REGISTRY_EMPTY: there are no controls to check. A check over an "
            "empty set agrees with everything, so this is a failure rather than a pass")

    owning = sorted({suite for _description, _signature, suite in registry.values()})
    absent = [f"{suite}.log" for suite in owning if not (logs / f"{suite}.log").is_file()]
    if absent:
        raise ControlUnproved(
            f"CONTROL_LOG_ABSENT: the registry says {', '.join(owning)} prove controls "
            f"and {absent} {'is' if len(absent) == 1 else 'are'} not under {logs}. The "
            f"controls those suites own cannot be searched for, and calling them unproved "
            f"would state a cause this check did not establish")

    run = proved(logs)
    unproved = []
    for identifier, (description, _signature, suite) in sorted(registry.items()):
        markers = run.get(identifier, {"RED": set(), "GREEN": set()})
        gaps = [marker for marker in ("RED", "GREEN") if suite not in markers[marker]]
        if gaps:
            elsewhere = sorted((markers["RED"] | markers["GREEN"]) - {suite})
            unproved.append(
                f"{identifier} ({description}): no {' or '.join(gaps)} in {suite}.log"
                + (f", though it appears in {elsewhere}" if elsewhere else ""))
    if unproved:
        raise ControlUnproved(
            "CONTROL_NOT_PROVED_RED_THEN_GREEN: " + "; ".join(unproved)
            + ". A control that never went red is a coverage gap wearing a green badge")
    return len(registry)


def main(argv: list[str] | None = None) -> int:
    # The diagnostics above carry em-dashes and typographic quotes, and a Windows console
    # inherits cp1252 — which is how M1-A's rule came to exist at all: a run died
    # reporting a real finding it could not encode. Called HERE rather than at import,
    # because this module is imported by every suite and by three generators, and a
    # library that reconfigures somebody else's stdout is a library that surprises them.
    use_utf8_output()

    parser = argparse.ArgumentParser(
        description="Every registered control went red and then green in this run.")
    parser.add_argument("--logs", required=True, type=Path,
                        help="directory holding one <suite>.log per suite")
    args = parser.parse_args(argv)
    try:
        checked = check_red_then_green(args.logs)
    except (ControlUnproved, ControlDrift) as refused:
        print(f"FAIL {refused}")
        return 1
    print(f"{checked} controls, each proved red then green in the suite that owns it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
