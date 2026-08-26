#!/usr/bin/env python3
"""Deterministic workbook projection model shared by the generator and validator."""

from __future__ import annotations

import json
from collections import Counter


def joined(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return value


def structured(value: object) -> str:
    if value in (None, [], {}):
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def unresolved_count(residual: dict) -> int:
    return sum(len(value) for key, value in residual.items() if key.startswith("unresolved_") and isinstance(value, list))


def requirement_workbook_sheets(bundle: dict) -> list[tuple]:
    req = bundle["requirements"]
    rows = req["active_requirements"]
    lineage = bundle["lineage"]
    gate_counts = req["gate_counts"]
    test_mismatches = sum(
        1
        for item in rows
        if set(item.get("acceptance_test_ids", [])) != set(item.get("engineering_test_links", []))
    )
    metrics = [
        ("Active requirements", len(rows)),
        ("Requirement clauses", sum(len(item.get("clauses", [])) for item in rows)),
        ("P0 requirements", sum(item.get("priority") == "P0" for item in rows)),
        ("P1 requirements", sum(item.get("priority") == "P1" for item in rows)),
        ("Original requirements mapped", lineage.get("mapped_count", len(lineage.get("lineage", [])))),
        ("Split originals", len(lineage.get("split_register", []))),
        ("New audit requirements", len(lineage.get("new_requirements", []))),
        ("Test-ID mismatches", test_mismatches),
        ("Unresolved issues", unresolved_count(bundle["residual"])),
    ]
    gates = ["M0", "M0R", "M1", "M2", "M3", "M4", "M5a", "M5b", "M6"]
    dashboard = [[f"Hospitality OS Requirements Traceability Matrix v{bundle['version']}"] + [""] * 7, [""] * 8]
    dashboard += [["Metric", "Value", "", "Gate", "Count", "", "", ""]]
    dashboard += [[label, value, "", gate, gate_counts.get(gate, 0), "", "", ""] for (label, value), gate in zip(metrics, gates)]

    active_headers = [
        "ID", "Lineage Status", "Split From", "Domain", "Priority", "Title", "Introduced At",
        "Revalidated At", "Required Behavior", "Gate-local Behavior", "Later Behavior",
        "Prerequisite IDs", "Prerequisite Components", "Artifacts at Introduction", "Journey Links",
        "Engineering Test Links", "Acceptance Test IDs", "Owner", "Component Path", "Classification",
        "Reconciliation Basis", "Rationale", "Confidence",
    ]
    active = [active_headers]
    for item in rows:
        active.append([
            item.get("id"), item.get("lineage_status"), item.get("split_from"), item.get("domain"),
            item.get("priority"), item.get("title"), item.get("introduced_at"), joined(item.get("revalidated_at")),
            item.get("required_behavior"), item.get("gate_local_behavior"), item.get("later_behavior"),
            joined(item.get("prerequisite_requirement_ids")), joined(item.get("prerequisite_components")),
            joined(item.get("artifacts_available_at_introduction")), joined(item.get("journey_links")),
            joined(item.get("engineering_test_links")), joined(item.get("acceptance_test_ids")), item.get("owner"),
            item.get("component_path"), item.get("classification"), item.get("reconciliation_basis"),
            item.get("reconciliation_rationale"), item.get("review_confidence"),
        ])

    clause_headers = [
        "Requirement ID", "Clause ID", "Exact Clause Text", "Introduced At", "Revalidated At",
        "Prerequisite Components", "Prerequisite Requirement IDs", "Artifacts Available", "Gate-local Behavior",
        "Later Behavior", "Journey Links", "Engineering Test Links", "Deferred Risk", "Deferred Notes",
        "Reviewer Rationale", "Confidence", "Status",
    ]
    clauses = [clause_headers]
    for item in rows:
        for clause in item.get("clauses", []):
            clauses.append([
                item.get("id"), clause.get("clause_id"), clause.get("exact_clause_text"), clause.get("introduced_at"),
                joined(clause.get("revalidated_at")), joined(clause.get("prerequisite_components")),
                joined(clause.get("prerequisite_requirement_ids")), joined(clause.get("artifacts_available_at_introduction")),
                clause.get("gate_local_behavior"), clause.get("later_behavior"), joined(clause.get("journey_links")),
                joined(clause.get("engineering_test_links")), clause.get("deferred_domain_risk"),
                clause.get("deferred_domain_notes"), clause.get("reviewer_rationale"),
                clause.get("reviewer_confidence"), clause.get("review_status"),
            ])

    journey_headers = ["ID", "Name", "Milestone", "Mandatory", "Predecessors", "Personas", "Steps", "Pass"]
    journeys = [journey_headers] + [[item.get("id"), item.get("name"), item.get("milestone"), item.get("mandatory"), item.get("predecessors"), item.get("personas"), item.get("steps"), item.get("pass")] for item in bundle["journeys"]["mandatory_journey_slices"]]
    milestone_headers = ["Gate", "Name", "Purpose", "Depends On", "Requirement Count", "Mandatory Journeys", "Exit Criterion"]
    milestones = [milestone_headers] + [[item.get("gate"), item.get("name"), item.get("purpose"), joined(item.get("depends_on")), item.get("requirement_count"), joined(item.get("journeys")), item.get("exit_criterion")] for item in bundle["implementation"]["milestones"]]
    return [
        ("Dashboard", dashboard, {"header_row": 3, "freeze_row": 3, "title_merge": "A1:H1"}),
        ("Active Requirements", active, {"autofilter": f"A1:W{len(active)}"}),
        ("Clause Evidence", clauses, {"autofilter": f"A1:Q{len(clauses)}"}),
        ("Golden Journeys", journeys, {"autofilter": f"A1:H{len(journeys)}"}),
        ("Milestone Matrix", milestones, {"autofilter": f"A1:G{len(milestones)}"}),
    ]


def decision_workbook_sheets(bundle: dict) -> list[tuple]:
    decisions = bundle["decisions"]["decisions"]
    lineage = bundle["lineage"]
    amendments = bundle["amendments"]["amendments"]
    findings = bundle["findings"]["findings"]
    rules = bundle["non_regression"]["rules"]
    metrics = [
        ("Decisions", len(decisions)),
        ("Original requirements", lineage.get("original_count", len(lineage.get("lineage", [])))),
        ("Mapped originals", lineage.get("mapped_count", len(lineage.get("lineage", [])))),
        ("Split originals", len(lineage.get("split_register", []))),
        ("New audit requirements", len(lineage.get("new_requirements", []))),
        ("Amendments", len(amendments)),
        ("Findings", len(findings)),
        ("Non-regression rules", len(rules)),
        ("Unresolved issues", unresolved_count(bundle["residual"])),
    ]
    dashboard = [[f"Hospitality OS Decision, Lineage and Evidence Register v{bundle['version']}"] + [""] * 7, [""] * 8, ["Metric", "Value"] + [""] * 6]
    dashboard += [[label, value] + [""] * 6 for label, value in metrics]
    decision_rows = [["ID", "Topic", "Decision", "Target", "Classification", "Source"]] + [[item.get("id"), item.get("topic"), item.get("decision"), item.get("target"), item.get("classification"), item.get("source")] for item in decisions]
    original_lineage = [["Original ID", "Original Title", "Disposition", "Active IDs", "Semantic Coverage", "Original Behavior Hash", "Active Behavior Hashes", "Rationale"]]
    original_lineage += [[item.get("original_id"), item.get("original_title"), item.get("disposition"), joined(item.get("active_ids")), item.get("semantic_coverage_attested"), item.get("original_behavior_sha256"), joined(item.get("active_behavior_hashes")), item.get("rationale", "")] for item in lineage.get("lineage", [])]
    split_rows = [["Original ID", "Original Title", "Original Behavior", "Successor IDs", "Successor Gates", "Successor Titles", "Split Reason"]]
    split_rows += [[item.get("original_id"), item.get("original_title"), item.get("original_behavior"), joined(item.get("successor_ids")), joined(item.get("successor_gates")), joined(item.get("successor_titles")), item.get("split_reason")] for item in lineage.get("split_register", [])]
    amendment_rows = [["Amendment ID", "Title", "Source", "Affected IDs", "Old Value", "New Value", "Change", "Reason", "Semantic Change", "Verification", "Residual Risk"]]
    amendment_rows += [[item.get("amendment_id"), item.get("title"), item.get("source"), joined(item.get("affected_ids")), item.get("old_value"), item.get("new_value"), item.get("change"), item.get("reason"), item.get("semantic_behavior_change"), item.get("verification"), item.get("residual_risk")] for item in amendments]
    finding_rows = [["Finding ID", "Severity", "Title", "Finding", "Disposition", "Affected IDs", "Affected Files", "Verification", "Residual Risk"]]
    finding_rows += [[item.get("finding_id"), item.get("severity"), item.get("title"), item.get("finding"), item.get("disposition"), joined(item.get("affected_canonical_ids")), joined(item.get("affected_files")), item.get("verification"), item.get("residual_risk")] for item in findings]
    rule_rows = [["ID", "Rule"]] + [[item.get("id"), item.get("rule")] for item in rules]
    original_decisions = [bundle["original_decisions"]["columns"]] + [[row.get(column) for column in bundle["original_decisions"]["columns"]] for row in bundle["original_decisions"]["rows"]]
    sheets = [
        ("Dashboard", dashboard, {"header_row": 3, "freeze_row": 3, "title_merge": "A1:H1"}),
        ("Decision Register", decision_rows), ("Original Lineage", original_lineage),
        ("Split Register", split_rows), ("Amendments", amendment_rows), ("Findings", finding_rows),
        ("Non-Regression Rules", rule_rows), ("Original Decisions", original_decisions),
    ]
    return [
        sheets[0],
        *[(name, rows, {"autofilter": f"A1:{_column_name(max(len(row) for row in rows))}{len(rows)}"}) for name, rows in sheets[1:]],
    ]


def _column_name(count: int) -> str:
    value = ""
    while count:
        count, remainder = divmod(count - 1, 26)
        value = chr(65 + remainder) + value
    return value


def occurrence_workbook_sheets(bundle: dict) -> list[tuple]:
    registry = bundle["occurrence_registry"]
    occurrences = registry["occurrences"]
    classifications = Counter(item.get("classification", "") for item in occurrences)
    dashboard = [[f"Hospitality OS Canonical Occurrence Registry v{bundle['version']}"] + [""] * 7, [""] * 8, ["Metric", "Value"] + [""] * 6]
    dashboard += [["Occurrences", len(occurrences)] + [""] * 6, ["Registry status", registry.get("status", "")] + [""] * 6, ["Normalization version", registry.get("normalization_version", "")] + [""] * 6]
    for classification in sorted(classifications):
        dashboard.append([f"Classification: {classification}", classifications[classification]] + [""] * 6)
    headers = [
        "Occurrence ID", "Record Type", "Record ID", "Field", "Term ID", "Detected Term", "Exact Excerpt",
        "Occurrence Ordinal", "Normalized Sentence", "Normalized Sentence SHA256", "Excerpt SHA256",
        "Normalization Version", "Classification", "Classification Rationale", "Classification Provenance",
        "Authorizing Reference Status", "Primary Reference Type", "Primary Reference ID", "Primary Reference Title",
        "Primary Reference Locator", "Supporting References", "Reference Rationale", "Reference Decision Provenance",
        "Evidence Locations Consulted", "Complete Authority Text Read", "Registry Status", "Introduced By Amendment",
    ]
    rows = [headers]
    for item in occurrences:
        primary = item.get("authorizing_reference") or {}
        rows.append([
            item.get("occurrence_id"), item.get("record_type"), item.get("record_id"), item.get("field"),
            item.get("term_id"), item.get("detected_term", item.get("term")), item.get("exact_excerpt"),
            item.get("occurrence_ordinal"), item.get("normalized_sentence"), item.get("normalized_sentence_sha256"),
            item.get("excerpt_sha256"), item.get("normalization_version"), item.get("classification"),
            item.get("classification_rationale", item.get("rationale")), item.get("classification_provenance"),
            item.get("authorizing_reference_status"), primary.get("type"), primary.get("id"), primary.get("title"),
            primary.get("canonical_record_locator", primary.get("semantic_authority_locator")),
            structured(item.get("supporting_references")), item.get("reference_rationale"),
            item.get("reference_decision_provenance"), structured(item.get("evidence_locations_consulted")),
            item.get("complete_relied_upon_authority_text_read"), registry.get("status"), item.get("introduced_by_amendment"),
        ])
    return [
        ("Dashboard", dashboard, {"header_row": 3, "freeze_row": 3, "title_merge": "A1:H1"}),
        ("Occurrences", rows, {"autofilter": f"A1:AA{len(rows)}"}),
    ]


def normalized_matrix(rows: list[list[object]]) -> list[list[str]]:
    normalized = []
    for row in rows:
        normalized.append(["" if value is None else "1" if value is True else "0" if value is False else str(value) for value in row])
    return normalized
