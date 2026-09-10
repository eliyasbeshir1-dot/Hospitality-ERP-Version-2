#!/usr/bin/env python3
"""M6-E verification: pilot readiness, and the last four partial closures.

FR-OPS-011, FR-OPS-012, FR-OPS-015.

WHAT THIS SLICE IS FOR. Everything before it built mechanisms. This one asks the question a
founder asks before letting a real guest in — is this ready — and requires the answer to
come from rows rather than from anybody's confidence.

  FR-OPS-011  eleven runbooks, one per situation the requirement names. The register is a
              table pointing at documents rather than a folder somebody hopes is complete,
              because whether one EXISTS is a fact and a fact in a folder is one nobody can
              query at three in the morning.

  FR-OPS-012  severity, owner, acknowledgement and escalation for every event that can
              actually be raised. The owner is a FOREIGN KEY to a role, because "avoid
              unowned dashboards" is only structural if an owner has to exist.

  FR-OPS-015  a cutover naming the commit, the operator, the data owner and the way back —
              and unable to reach `live` without a reviewer who is not the operator. "No
              direct production cutover from an unaudited branch" as a CHECK.

AND THE FOUR CLOSURES THAT NAME THIS SLICE. Three of them are one problem wearing three
faces: FR-FUL-008, FR-FUL-014 and FR-BIL-017 all terminate in ink leaving a real printer.
There is no printer on this machine. This suite builds everything up to the last inch and
says so, rather than claiming a physical fact it cannot observe.

Usage:
    M1A_ADMIN_DSN=... python3 tests/m6e/verify_m6e.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
from console import use_utf8_output                        # noqa: E402

use_utf8_output()

sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "tests" / "m1a"))
sys.path.insert(0, str(REPO / "tests" / "opa"))
from pg import run                                         # noqa: E402

import controls as registry                                # noqa: E402
import verify_opa as opa                                   # noqa: E402

ADMIN = os.environ["M1A_ADMIN_DSN"]
TENANT = opa.TENANT
KAZANCHIS = "33330001-0000-4000-8000-000000000001"
ADMINISTRATOR = "3333aaaa-0000-4000-8000-000000000001"
KAZ_MANAGER = "3333cccc-0000-4000-8000-000000000004"

results: list[tuple[str, bool, str, str]] = []


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    results.append((name, ok, detail, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] ({evidence}) {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def measured(name: str, ok: bool, detail: str = "") -> None:
    record(name, ok, detail, evidence="measured")


def q(sql: str, *, outlet: str = KAZANCHIS):
    result = run(ADMIN, sql, tenant=TENANT, outlet=outlet, tx=True, rollback=True)
    if not result.ok:
        raise RuntimeError(f"probe failed: {result.err[:300]}")
    return result


def refusal(sql: str, *, outlet: str = KAZANCHIS) -> str:
    result = run(ADMIN, sql, tenant=TENANT, outlet=outlet, tx=True, rollback=True)
    if result.ok:
        return ""
    # A TOKEN ECHOED FROM THE STATEMENT IS NOT THE SERVER'S SIGNATURE. PostgreSQL quotes
    # the failing statement back in its error, so an uppercase identifier in the SQL —
    # OUTLET_MANAGER, EVT-OUTLET-HEARTBEAT-LOST — looks exactly like a RAISE EXCEPTION
    # signature to a scan that reads the whole message. This suite found that the way they
    # are all found: a control reported `signature: OUTLET_MANAGER` and passed nothing.
    sent = set(sql.replace("\n", " ").replace("'", " ").split())
    for token in result.err.replace("\n", " ").split():
        cleaned = token.strip(":,.'" + '"')
        if (cleaned.isupper() and len(cleaned) > 6 and "_" in cleaned
                and cleaned not in sent and f"'{cleaned}'" not in sql):
            return cleaned
    for token in result.err.replace("\n", " ").split():
        stripped = token.strip("'\",.")
        # Trailing underscore skips the relation and matches the constraint.
        if stripped.startswith(("cutover_", "alert_ownership_", "runbook_")):
            return stripped
    return result.err.strip()[:140]


def control(name: str, red, green) -> None:
    red_ok, red_detail = red()
    record(f"{name} — RED with the defect planted", red_ok, red_detail)
    green_ok, green_detail = green()
    record(f"{name} — GREEN after revert", green_ok, green_detail)


# ===========================================================================
# 1. FR-OPS-011 — eleven runbooks that exist as files
# ===========================================================================

def section_runbooks() -> None:
    print("\n--- 1. FR-OPS-011: a runbook for each of the eleven situations ---")

    registered = q("SELECT count(*)::text FROM ops.runbook;").scalar
    record("all eleven situations are registered",
           registered == "11", f"{registered} of 11")

    # THE REGISTER POINTS AT FILES AND THE FILES EXIST. A register naming documents nobody
    # wrote is the exact shape of a checklist that passes and helps no one.
    rows = q("SELECT string_agg(situation::text || '=' || document_path, ' ' "
             "ORDER BY situation::text) FROM ops.runbook;").scalar
    missing = []
    for pair in (rows or "").split():
        situation, _, path = pair.partition("=")
        if not (REPO / path).is_file():
            missing.append(f"{situation} -> {path}")
    record("and every registered path is a document that exists",
           not missing,
           f"missing: {missing or 'none'}\na register naming documents nobody wrote is a "
           "checklist that passes and helps no one")

    # AND EACH ONE SAYS WHAT TO DO WHEN IT DOES NOT WORK. A runbook without a fallback is a
    # runbook for the case that was never going to need one.
    thin = []
    for pair in (rows or "").split():
        situation, _, path = pair.partition("=")
        text = (REPO / path).read_text(encoding="utf-8")
        if "If it does not work" not in text or len(text) < 500:
            thin.append(situation)
    record("and each says what to do when it does not work",
           not thin,
           f"without a fallback section: {thin or 'none'}. A runbook that only covers the "
           "happy path is a runbook for the case that was never going to need one")


# ===========================================================================
# 2. FR-OPS-012 — no unowned alerts
# ===========================================================================

def section_ownership() -> None:
    print("\n--- 2. FR-OPS-012: severity, owner, acknowledgement, escalation ---")

    unowned = q(f"SELECT count(*)::text FROM ops.unowned_alerts('{TENANT}');").scalar
    record("every event that can actually be raised has an owner",
           unowned == "0",
           f"{unowned} producible event(s) with nobody assigned. Producerless events are "
           "excluded deliberately: an alert nothing emits needs no owner, and demanding "
           "one would be paperwork rather than accountability")

    owned = q(f"""SELECT count(*)::text FROM ops.alert_ownership
                   WHERE tenant_id = '{TENANT}';""").scalar
    record("and the ownership table is not empty",
           (owned or "0") != "0",
           f"{owned} owned. The unowned check must not pass by there being nothing to own")

    # THE OWNER IS A REAL ROLE, enforced by foreign key rather than by spelling.
    fk = q("""SELECT count(*)::text FROM pg_constraint
               WHERE conrelid = 'ops.alert_ownership'::regclass AND contype = 'f'
                 AND confrelid = 'identity.role'::regclass;""").scalar
    record("the owner is a foreign key to a role, not a team name in text",
           (fk or "0") != "0",
           f"{fk} foreign key(s) to identity.role. A text column holding a team name still "
           "says 'Platform' after the platform team is dissolved")

    # ESCALATION AFTER ACKNOWLEDGEMENT, which every threshold pair here ascends for.
    bad = refusal(f"""
        INSERT INTO ops.alert_ownership (tenant_id, event_id, severity, owner_role_id,
                acknowledge_within_minutes, escalate_after_minutes, escalate_to_role_id)
        SELECT '{TENANT}', 'EVT-ORDER-SUBMITTED', 'warning', r.id, 60, 15, r.id
          FROM identity.role r
         WHERE r.tenant_id = '{TENANT}' AND r.role_code = 'OUTLET_MANAGER';""")
    record("an escalation window shorter than the acknowledgement window is refused",
           bad == "alert_ownership_escalation_is_after",
           f"signature: {bad}\nit would escalate every alert the moment it was raised")


# ===========================================================================
# 3. FR-OPS-015 — a cutover somebody signed
# ===========================================================================

def section_cutover() -> None:
    print("\n--- 3. FR-OPS-015: no direct production cutover from an unaudited branch ---")

    live = q(f"""SELECT count(*)::text FROM ops.cutover
                  WHERE tenant_id = '{TENANT}' AND state = 'live';""").scalar
    record("a live cutover is recorded for the pilot outlet",
           (live or "0") != "0", f"{live} live cutover(s)")

    named = q(f"""SELECT (named_operator_user_id <> data_owner_user_id)::text || '|'
                       || (reviewed_by_user_id <> named_operator_user_id)::text
                    FROM ops.cutover WHERE tenant_id = '{TENANT}' AND state = 'live'
                   LIMIT 1;""").scalar
    record("the operator, the data owner and the reviewer are distinct people",
           named == "true|true",
           f"{named}\nthe operator does it and the data owner answers for what happens to "
           "the trade afterwards; a reviewer who is the operator is a person agreeing with "
           "themselves")

    # THE CHECK THE REQUIREMENT IS REALLY ABOUT.
    unaudited = refusal(f"""
        INSERT INTO ops.cutover (tenant_id, outlet_id, state, commit_sha,
                named_operator_user_id, data_owner_user_id, rollback_plan, went_live_at)
        VALUES ('{TENANT}', '{KAZANCHIS}', 'live', repeat('a', 40),
                '{KAZ_MANAGER}', '{ADMINISTRATOR}',
                'restore the last verified backup and re-point the hostname', now());""")
    record("a cutover cannot reach live without a reviewer and a verdict",
           unaudited == "cutover_live_was_audited",
           f"signature: {unaudited}\n'no direct production cutover from an unaudited "
           "branch' as a CHECK rather than a sentence")

    self_reviewed = refusal(f"""
        INSERT INTO ops.cutover (tenant_id, outlet_id, state, commit_sha,
                reviewed_by_user_id, review_verdict,
                named_operator_user_id, data_owner_user_id, rollback_plan, went_live_at)
        VALUES ('{TENANT}', '{KAZANCHIS}', 'live', repeat('b', 40),
                '{KAZ_MANAGER}', 'looks fine to me',
                '{KAZ_MANAGER}', '{ADMINISTRATOR}',
                'restore the last verified backup and re-point the hostname', now());""")
    record("and the operator may not be their own reviewer",
           self_reviewed == "cutover_review_is_independent",
           f"signature: {self_reviewed}")

    no_way_back = refusal(f"""
        INSERT INTO ops.cutover (tenant_id, outlet_id, state, commit_sha,
                named_operator_user_id, data_owner_user_id, rollback_plan)
        VALUES ('{TENANT}', '{KAZANCHIS}', 'planned', repeat('c', 40),
                '{KAZ_MANAGER}', '{ADMINISTRATOR}', 'wing it');""")
    record("a cutover plan without a way back is refused",
           no_way_back == "cutover_rollback_plan_is_stated",
           f"signature: {no_way_back}\na cutover plan without a rollback is a plan to hope")


# ===========================================================================
# 4. Is this outlet ready?
# ===========================================================================

def section_readiness() -> None:
    print("\n--- 4. The question a founder asks before letting a guest in ---")

    rows = q(f"""SELECT string_agg(requirement || '=' || ready::text, ' | '
                          ORDER BY requirement)
                   FROM ops.pilot_readiness('{TENANT}', '{KAZANCHIS}');""").scalar
    clauses = (rows or "").split(" | ")
    not_ready = [c for c in clauses if c.endswith("=false")]
    record("every pilot-readiness clause is ready for the demonstration outlet",
           not not_ready and len(clauses) == 6,
           "\n".join(clauses) + f"\nnot ready: {not_ready or 'none'}")

    record("and readiness is the conjunction of what earlier gates built",
           len(clauses) == 6,
           "runbooks (M6-E), alert ownership (M6-E), a verified backup (M6-B), a hostname "
           "(M5b), one writable authority (M5b), a reviewed cutover (M6-E). Readiness is "
           "not a new mechanism — it is these six holding at once")


# ===========================================================================
# 5. Negative controls
# ===========================================================================

def section_controls() -> None:
    print("\n--- 5. Negative controls: each defect planted, refused, reverted ---")

    def nc_001():
        def red():
            got = refusal(f"""
                DELETE FROM ops.alert_ownership
                 WHERE tenant_id = '{TENANT}'
                   AND event_id = 'EVT-OUTLET-HEARTBEAT-LOST';
                SELECT CASE WHEN (SELECT count(*) FROM ops.unowned_alerts('{TENANT}')) > 0
                       THEN 1 / 0 ELSE 1 END;""")
            return got != "", \
                f"removing one owner makes ops.unowned_alerts() non-empty ({got})"

        def green():
            got = q(f"SELECT count(*)::text FROM ops.unowned_alerts('{TENANT}');").scalar
            return got == "0", "and outside the plant every raisable event is owned"

        control("NC-M6E-001 an alert nobody owns", red, green)

    def nc_002():
        def red():
            got = refusal(f"""
                INSERT INTO ops.cutover (tenant_id, outlet_id, state, commit_sha,
                        named_operator_user_id, data_owner_user_id, rollback_plan,
                        went_live_at)
                VALUES ('{TENANT}', '{KAZANCHIS}', 'live', repeat('d', 40),
                        '{KAZ_MANAGER}', '{ADMINISTRATOR}',
                        'restore the last verified backup and re-point the hostname',
                        now());""")
            return got == "cutover_live_was_audited", f"signature: {got}"

        def green():
            got = refusal(f"""
                INSERT INTO ops.cutover (tenant_id, outlet_id, state, commit_sha,
                        reviewed_by_user_id, review_verdict,
                        named_operator_user_id, data_owner_user_id, rollback_plan,
                        went_live_at)
                VALUES ('{TENANT}', '{KAZANCHIS}', 'live', repeat('d', 40),
                        '{ADMINISTRATOR}', 'APPROVE at that commit',
                        '{KAZ_MANAGER}', '{ADMINISTRATOR}',
                        'restore the last verified backup and re-point the hostname',
                        now());""")
            return got == "", f"a reviewed one is accepted (signature: {got or 'none'})"

        control("NC-M6E-002 a cutover to live from an unaudited branch", red, green)

    def nc_003():
        def red():
            got = refusal("""
                INSERT INTO ops.runbook (situation, document_path, owner_role_code)
                VALUES ('outage', 'notes.txt', 'OUTLET_MANAGER')
                ON CONFLICT (situation) DO UPDATE SET document_path = 'notes.txt';""")
            return got == "runbook_path_is_stated", \
                f"signature: {got} — a runbook must live under docs/runbooks/"

        def green():
            got = q("SELECT count(*)::text FROM ops.runbook "
                    "WHERE document_path LIKE 'docs/runbooks/%';").scalar
            return got == "11", f"all {got} point where runbooks live"

        control("NC-M6E-003 a runbook pointing anywhere it likes", red, green)

    for case in (nc_001, nc_002, nc_003):
        case()

    registered = [c for c in registry.CONTROLS if c[3] == "m6e"]
    record("every M6-E control is registered in tools/controls.py",
           len(registered) == 3, f"{len(registered)} registered")


# ===========================================================================
# 6. The bounds — including the three that need a printer
# ===========================================================================

def section_bounds() -> None:
    print("\n--- 6. The bounds, named rather than left to silence ---")
    for bound in (
        "THREE PARTIAL CLOSURES CANNOT BE CLOSED ON THIS MACHINE AND ARE NOT. FR-FUL-008 "
        "(allergy salience surviving physical printing), FR-FUL-014 (physical printing) "
        "and FR-BIL-017 (paper out of a physical machine) are ONE hardware dependency "
        "wearing three faces: ink leaving a real printer. Everything up to the last inch "
        "is built and proved — the queue, the lease, the retry, the exactly-once "
        "guarantee, the 576-dot rasterisation, the allergy lines first and in words. What "
        "is not proved is the paper. They stay OPEN",
        "FR-TST-005A ALSO STAYS OPEN. It asks for the five settlement journeys at the "
        "BROWSER tier rather than through the HTTP calls a screen would issue. GJ-10 walks "
        "the till in a browser for its first settlement, which is more than the service "
        "tier and still not five journeys",
        "ESCALATION GOES TO THE SAME ROLE ON THE DEMONSTRATION FLOOR. ops.alert_ownership "
        "supports a different escalation role and this estate has one operational role, so "
        "escalating from OUTLET_MANAGER to OUTLET_MANAGER escalates to the same person. "
        "The schema is right and the seeded floor is thin; inventing a second role so the "
        "row looked correct would be worse",
        "FR-TST-010's LOAD TEST IS NOT BUILT. Peak ordering, KDS, realtime, menu search "
        "and integration bursts with recorded thresholds needs a machine with headroom, "
        "and this one has been at 100% disk twice during this gate",
        "THE RUNBOOKS ARE CHECKED FOR EXISTENCE, A FALLBACK SECTION AND LENGTH. Whether "
        "the prose is any good is not something a database can know, and the only honest "
        "test of a runbook is somebody following it under pressure",
    ):
        record("recorded in planning/M6_FINDINGS.md", True, bound)


def main() -> int:
    print("=" * 74)
    print("  M6-E — pilot readiness: runbooks, owners, and a cutover somebody signed")
    print("=" * 74)

    for section in (section_runbooks, section_ownership, section_cutover,
                    section_readiness, section_controls, section_bounds):
        try:
            section()
        except Exception as exc:                            # noqa: BLE001
            record(f"{section.__name__} completed", False,
                   f"{type(exc).__name__}: {str(exc)[:400]}")

    failed = [name for name, ok, _d, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")
    owned = len([c for c in registry.CONTROLS if c[3] == "m6e"])

    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}")
    print(f"  asserted      : {len(results) - measured_count}")
    print(f"  controls      : {owned} registered, each proved red then green")

    if failed:
        print("\nFAIL M6E_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS M6E_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
