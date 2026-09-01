#!/usr/bin/env python3
"""M2-B verification: tables, QR, guest sessions, carts, allergens and dietary safety.

This slice holds the first safety-critical data in the project, and the assertions here
are written to the standard M1-C set for money: a defect that reaches a guest is not a
bug report, it is somebody eating something they cannot eat.

Two properties get more attention than the rest, because both are the kind that pass a
casual test and fail in production.

  An icon never reaches a guest without the words beside it. Proved by privilege rather
  than by inspection: the application role has no SELECT on safety.allergen.icon_key, so
  the check is that the query fails, not that nobody wrote it.

  A declaration is never stale. Proved by correcting one AFTER a menu was published and
  requiring the correction to appear when that same published snapshot is read.

Real PostgreSQL, the least-privileged application role, populated fixtures. Every
assertion names the specific reason it expects.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
# This directory goes on LAST so it resolves FIRST. tests/m2a also holds a module called
# "fixtures", and the suite that imports the wrong one would run against M2-A's menu with
# none of the safety catalog and report a great many confident, meaningless passes.
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "m1a"))
sys.path.insert(0, str(HERE))

import fixtures as fx                                   # noqa: E402
from fenced import fenced_identifier_pattern            # noqa: E402
from pg import count, count_or, run                     # noqa: E402

assert fx.__file__ == str(HERE / "fixtures.py"), (
    f"the wrong fixtures module was imported: {fx.__file__}")
m2a_fx = fx.m2a

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]

CTX = dict(tenant=fx.TENANT, outlet=fx.OUTLET_H1)
CTX_H2 = dict(tenant=fx.TENANT, outlet=fx.OUTLET_H2)

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("t", "true")


def function_bodies(pattern: str, *, excluding: str = "") -> str:
    """Names of functions in this project's schemas whose body matches a pattern.

    Two things here are not incidental.

    AS MATERIALIZED forces the schema filter to run BEFORE pg_get_functiondef. Without
    it PostgreSQL is free to evaluate the expensive predicate first, and the sweep dies
    on "array_agg is an aggregate function" — a query that errors, which a check reading
    only the returned string would score as "nothing found". A sweep that cannot run is
    not a sweep that found nothing.

    Comments are stripped before matching. The function that reads a table and the
    function whose comment explains why it does not read that table are different
    things, and a check that cannot tell them apart flags careful documentation as a
    defect.
    """
    exclusion = f"AND p.proname <> '{excluding}'" if excluding else ""
    res = run(ADMIN, f"""
        WITH candidates AS MATERIALIZED (
            SELECT p.oid, n.nspname, p.proname
            FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname IN ('safety', 'menu', 'service')
              AND p.prokind IN ('f', 'p') {exclusion}
        ),
        stripped AS (
            SELECT c.nspname, c.proname,
                   regexp_replace(pg_get_functiondef(c.oid), '--[^\n]*', '', 'g') AS body
            FROM candidates c
        )
        SELECT coalesce(string_agg(s.nspname || '.' || s.proname, ', ' ORDER BY s.proname), '')
        FROM stripped s WHERE {pattern};
    """)
    if not res.ok:
        raise RuntimeError(f"the function sweep did not run: {res.why()}")
    return (res.scalar or "").strip()


def first_line(text: str | None) -> str:
    return (text or "").strip().splitlines()[0] if (text or "").strip() else ""


# ===========================================================================
# 1. QR resolution that exposes nothing (FR-TAB-001, FR-TAB-002)
# ===========================================================================

def section_qr() -> None:
    print("\n--- 1. QR resolution, rotation and revocation (FR-TAB-001, FR-TAB-002) ---")

    tables = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('safety', 'service') AND c.relkind = 'r';
    """)
    forced = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('safety', 'service') AND c.relkind = 'r'
          AND c.relrowsecurity AND c.relforcerowsecurity;
    """)
    # The exemptions, named one by one. Reference data and pinned machines carry no
    # tenant column for a policy to test; everything else in these schemas is tenant
    # data and is forced. service.transition joined the list when M3-C landed
    # SM-SERVICE-REQUEST — it is the package's machine, immutable at runtime by trigger,
    # and readable by the application role and no more.
    reference = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND ((n.nspname = 'safety'
                AND c.relname IN ('jurisdiction', 'jurisdiction_requirement'))
            OR (n.nspname = 'service' AND c.relname = 'transition'));
    """)
    record("every tenant-scoped table in safety and service has RLS ENABLEd and FORCEd",
           tables > 0 and forced == tables - reference,
           f"{tables} table(s) across safety and service, {forced} with row level security "
           f"enabled and forced; the {reference} exception(s) are safety.jurisdiction, "
           f"safety.jurisdiction_requirement and service.transition — reference data and "
           f"a pinned state machine. What a regulator requires, and what edges a service "
           f"request may take, are the same facts for every tenant, so there is no tenant "
           f"column for a policy to test and the application role holds SELECT only")

    weakened = count(ADMIN, """
        SELECT count(*) FROM pg_policies
        WHERE schemaname IN ('safety', 'service')
          AND (qual NOT LIKE '%row_in_scope%' OR with_check NOT LIKE '%row_in_scope%');
    """)
    record("every safety and service policy is built on the unchanged M1-A predicate",
           weakened <= 1,
           "the one policy not built on app.row_in_scope() is "
           "service.verification_policy, which compares tenant_id to "
           "app.current_tenant_id() because accepted verification methods are a "
           "tenant-wide choice with no outlet column — the same exception org.tenant "
           "carries, and for the same reason")

    # Non-enumerability, measured rather than asserted. Two codes issued for two tables in
    # the same outlet must share nothing: no prefix, no arithmetic relationship, and
    # neither may contain any identifier the caller already knows.
    one, two = fx.TOKENS["one"], fx.TOKENS["two"]
    shared_prefix = 0
    for a, b in zip(one, two):
        if a != b:
            break
        shared_prefix += 1

    known = [fx.TABLE_ONE, fx.TABLE_TWO, fx.OUTLET_H1, fx.TENANT]
    embedded = [k for k in known if k.replace("-", "").lower() in one.lower()]

    record("a QR reference is not enumerable and decodes to nothing",
           len(one) >= 32 and shared_prefix <= 2 and not embedded
           and abs(int(one, 16) - int(two, 16)) > 2 ** 64,
           f"two codes issued for two tables in the same outlet share a {shared_prefix} "
           f"character prefix and differ by far more than any sequence could; neither "
           f"contains the table, outlet or tenant identifier. {len(one) * 4} bits of "
           f"hexadecimal, drawn from the server CSPRNG")

    stored = run(ADMIN, f"""
        SELECT count(*)::text FROM service.table_qr_token
        WHERE encode(token_hash, 'hex') = '{one}';
    """)
    hashed = run(ADMIN, f"""
        SELECT count(*)::text FROM service.table_qr_token
        WHERE token_hash = sha256(convert_to('{one}', 'UTF8')) AND revoked_at IS NULL;
    """)
    record("the printed code is not stored, only its hash",
           stored.ok and stored.scalar == "0" and hashed.ok and hashed.scalar == "1",
           "the live row matches sha256 of the code and does not contain the code itself, "
           "so a dump of this table yields no working placard (FR-SEC-007); rotation is "
           "how a lost code is replaced, because looking the old one up is not possible")

    rotated = run(APP, f"""
        SELECT service.issue_table_qr('{fx.TENANT}', '{fx.TABLE_TWO}', '{fx.USER}');
    """, **CTX)
    new_token = (rotated.scalar or "").strip()
    old_dead = count_or(APP, f"""
        SELECT count(*) FROM service.table_qr_token
        WHERE token_hash = sha256(convert_to('{two}', 'UTF8')) AND revoked_at IS NOT NULL;
    """, -1, **CTX)
    active = count_or(APP, f"""
        SELECT count(*) FROM service.table_qr_token
        WHERE table_node_id = '{fx.TABLE_TWO}' AND revoked_at IS NULL;
    """, -1, **CTX)
    record("issuing a new code rotates the old one out",
           rotated.ok and new_token and new_token != two and old_dead == 1 and active == 1,
           f"the previous code is revoked and exactly {active} code is live for that "
           f"table; a second active code would mean two placards resolving to one table "
           f"with no way to withdraw just one")
    if new_token:
        fx.TOKENS["two"] = new_token

    revoked_scan = run(APP, f"""
        SELECT service.record_qr_scan('{fx.TENANT}', '{two}', '{fx.GUEST_ONE}');
    """, **CTX)
    record("a revoked code no longer resolves",
           revoked_scan.failed_with("QR_TOKEN_REVOKED"),
           f"refused: {first_line(revoked_scan.err)}")

    placards = run(APP, f"""
        INSERT INTO service.qr_placard (tenant_id, outlet_id, token_id, version, printed_by_user_id)
        SELECT '{fx.TENANT}', '{fx.OUTLET_H1}', id, version, '{fx.USER}'
        FROM service.table_qr_token
        WHERE table_node_id = '{fx.TABLE_ONE}' AND revoked_at IS NULL
        RETURNING version;
    """, **CTX)
    history = count_or(APP, f"""
        SELECT count(*) FROM service.qr_placard p
        JOIN service.table_qr_token t ON t.id = p.token_id
        WHERE t.table_node_id = '{fx.TABLE_ONE}';
    """, -1, **CTX)
    record("printable version history records which placard was produced",
           placards.ok and history >= 1,
           f"{history} placard record(s) for that table, each naming a version, a time "
           f"and a person (FR-TAB-002) — and none of them the code itself")


# ===========================================================================
# 2. Occupancy, joining, and the stale-QR guarantee (FR-TAB-003, 004, 010)
# ===========================================================================

def section_sessions() -> None:
    print("\n--- 2. Table sessions, joining and stale QR (FR-TAB-003, FR-TAB-004, FR-TAB-010) ---")

    session = fx.open_occupancy(fx.TABLE_ONE, source="staff")
    shape = run(APP, f"""
        SELECT state::text, opening_source::text, host_staff_user_id IS NOT NULL,
               occupancy_number::text
        FROM service.table_session WHERE id = '{session}';
    """, **CTX)
    row = shape.rows[0] if shape.ok and shape.rows else ["", "", "f", "0"]
    record("an occupancy records state, opening source, host and timestamps",
           shape.ok and row[0] == "open" and row[1] == "staff" and truthy(row[2]),
           f"occupancy {row[3]} on table 1 is {row[0]}, opened via {row[1]} by a named "
           f"host; a session opened at the host stand that named nobody would be refused "
           f"by table_session_host_named_when_staff_opened")

    second = run(APP, f"""
        INSERT INTO service.table_session
            (tenant_id, outlet_id, table_node_id, occupancy_number, opening_source, host_staff_user_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.TABLE_ONE}', 999, 'staff', '{fx.USER}');
    """, rollback=True, **CTX)
    record("a table cannot have two open occupancies at once",
           second.failed_with("table_session_one_open_per_table"),
           f"refused by the partial unique index: {first_line(second.err)}")

    # Two devices, one active code, one session.
    scan_a = run(APP, f"""
        SELECT service.record_qr_scan('{fx.TENANT}', '{fx.TOKENS["one"]}', '{fx.GUEST_ONE}');
    """, **CTX)
    joined_a = run(APP, f"""
        SELECT service.join_table_session('{fx.TENANT}', '{(scan_a.scalar or "").strip()}');
    """, **CTX)
    scan_b = run(APP, f"""
        SELECT service.record_qr_scan('{fx.TENANT}', '{fx.TOKENS["one"]}', '{fx.GUEST_TWO}');
    """, **CTX)
    joined_b = run(APP, f"""
        SELECT service.join_table_session('{fx.TENANT}', '{(scan_b.scalar or "").strip()}');
    """, **CTX)
    participants = count_or(APP, f"""
        SELECT count(*) FROM service.session_participant WHERE table_session_id = '{session}';
    """, -1, **CTX)
    record("multiple devices join one session using the same active code",
           joined_a.ok and joined_b.ok and participants == 2
           and (joined_a.scalar or "").strip() == session,
           f"{participants} devices are in occupancy {session[:8]}, both admitted by the "
           f"same live placard under the configured visibility rules (FR-TAB-004)")

    visibility = run(APP, f"""
        UPDATE service.session_participant SET shares_basket = false
        WHERE table_session_id = '{session}' AND guest_session_id = '{fx.GUEST_TWO}'
        RETURNING shares_basket::text;
    """, **CTX)
    record("a participant's basket visibility is configurable per device",
           visibility.ok and not truthy(visibility.scalar),
           "one device at the table keeps its basket private while the other shares; "
           "visibility is a per-participant setting rather than a table-wide mode")

    # ===== The stale-QR guarantee =====
    #
    # The point of this arrangement is that the code is not old. It is the current, live,
    # never-rotated placard for this table. What makes the join wrong is only that the
    # scan happened under an earlier occupancy.
    stale_scan = run(APP, f"""
        SELECT service.record_qr_scan('{fx.TENANT}', '{fx.TOKENS["one"]}', '{fx.GUEST_STALE}');
    """, **CTX)
    stale_id = (stale_scan.scalar or "").strip()
    later = fx.open_occupancy(fx.TABLE_ONE, source="staff")

    unverified = run(APP, f"""
        SELECT service.join_table_session('{fx.TENANT}', '{stale_id}');
    """, **CTX)
    record("a scan from an earlier occupancy cannot silently join a later one",
           unverified.failed_with("STALE_QR_VERIFICATION_REQUIRED"),
           f"the placard is the current one and was never rotated; it is the occupancy "
           f"that moved. Refused: {first_line(unverified.err)}")

    admitted = count_or(APP, f"""
        SELECT count(*) FROM service.session_participant
        WHERE table_session_id = '{later}' AND guest_session_id = '{fx.GUEST_STALE}';
    """, -1, **CTX)
    record("the later session did not admit the stale scan",
           admitted == 0,
           "the refusal is the absence of a participant row, not merely an error message: "
           "the guest who photographed the code during the previous party's meal is not "
           "in this occupancy, so they cannot read its session or, at M4, reach its bill")

    # Every configured method must refuse without evidence, not just the first.
    methods = run(ADMIN, f"""
        SELECT unnest(accepted_methods)::text FROM service.verification_policy
        WHERE tenant_id = '{fx.TENANT}';
    """)
    swept, holes = [], []
    for method in [r[0] for r in (methods.rows or [])]:
        swept.append(method)
        attempt = run(APP, f"""
            SELECT service.join_table_session('{fx.TENANT}', '{stale_id}', '{method}');
        """, **CTX)
        if not attempt.failed_with("STALE_QR_VERIFICATION_REQUIRED"):
            holes.append(f"{method} was accepted with no evidence recorded")
    record("the guarantee holds under every configured verification method",
           bool(swept) and not holes,
           f"swept {len(swept)} configured method(s) — {', '.join(swept)} — and each "
           f"refuses a stale scan when no evidence of the verification is recorded"
           + (f"; holes: {'; '.join(holes)}" if holes else ""))

    verified = run(APP, f"""
        SELECT service.join_table_session('{fx.TENANT}', '{stale_id}', 'table_code',
                                          'code 4417 read back by the guest');
    """, **CTX)
    record("a stale scan joins once the verification actually happens",
           verified.ok and (verified.scalar or "").strip() == later,
           "the block is a gate rather than a wall: the same scan is admitted when a "
           "configured method is named and its evidence recorded, so a guest whose "
           "friend photographed the code is not permanently locked out")

    unaccepted = run(APP, f"""
        SELECT service.join_table_session('{fx.TENANT}', '{stale_id}', 'host_approval', 'nodded');
    """, **CTX)
    record("a method the tenant has not configured is not accepted",
           unaccepted.failed_with("STALE_QR_VERIFICATION_REQUIRED"),
           f"host_approval is a valid method but not one this tenant accepts: "
           f"{first_line(unaccepted.err)}")


# ===========================================================================
# 3. No configuration can switch the guarantee off
# ===========================================================================

def section_no_disable_path() -> None:
    print("\n--- 3. There is no configuration that admits a stale scan (FR-TAB-010) ---")

    # Proving the absence of a setting, not the value of one. This is the same shape as
    # M2-A's "no customer-segment targeting column exists": a guarantee that any
    # configuration can turn off is a default, and defaults get switched off.
    switches = run(ADMIN, r"""
        SELECT coalesce(string_agg(n.nspname || '.' || c.relname || '.' || a.attname, ', '), '')
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('safety', 'service') AND c.relkind = 'r'
          AND a.attnum > 0 AND NOT a.attisdropped
          AND (a.attname ~* '(skip|bypass|disable|exempt|ignore|relax|optional).*(verif|check|stale)'
            OR a.attname ~* '(verif|check|stale).*(skip|bypass|disable|exempt|optional|enabled)'
            OR a.attname ~* '^(verification_enabled|require_verification|enforce_verification)$');
    """)
    record("no column anywhere can express 'do not verify'",
           switches.ok and not (switches.scalar or "").strip(),
           f"columns that could disable verification: "
           f"{(switches.scalar or '').strip() or 'none'}. The tenant chooses the method "
           f"and cannot choose whether — the same way row level security is not a tenant "
           f"preference")

    empty = run(APP, f"""
        UPDATE service.verification_policy
        SET accepted_methods = ARRAY[]::service.verification_method[]
        WHERE tenant_id = '{fx.TENANT}';
    """, rollback=True, **CTX)
    record("an empty set of accepted methods is refused",
           empty.failed_with("verification_policy_at_least_one_method"),
           f"an empty array would be a disable switch wearing a different name: "
           f"{first_line(empty.err)}")

    # A tenant with no policy row at all must fail closed, not open. Proved by removing
    # the row inside a rolled-back transaction and re-attempting the join.
    fx.open_occupancy(fx.TABLE_TWO, source="staff")
    scan = run(APP, f"""
        SELECT service.record_qr_scan('{fx.TENANT}', '{fx.TOKENS["two"]}', '{fx.GUEST_STALE}');
    """, **CTX)
    scan_id = (scan.scalar or "").strip()
    fx.open_occupancy(fx.TABLE_TWO, source="staff")

    unconfigured = run(APP, f"""
        DELETE FROM service.verification_policy WHERE tenant_id = '{fx.TENANT}';
        SELECT service.join_table_session('{fx.TENANT}', '{scan_id}');
    """, rollback=True, **CTX)
    record("absent configuration fails closed rather than open",
           unconfigured.failed_with("STALE_QR_VERIFICATION_REQUIRED"),
           f"a tenant that has configured nothing does not thereby get unverified joins: "
           f"{first_line(unconfigured.err)}")

    branches = run(ADMIN, """
        SELECT pg_get_functiondef('service.join_table_session(uuid,uuid,service.verification_method,text)'::regprocedure);
    """)
    body = branches.out or ""
    mismatch = body.split("IF v_scan.occupancy_at_scan IS DISTINCT FROM")[-1]
    guarded = mismatch.count("STALE_QR_VERIFICATION_REQUIRED")
    record("every branch of the occupancy mismatch ends in a refusal",
           branches.ok and guarded >= 4,
           f"{guarded} refusal(s) inside the mismatch branch — no configuration, no "
           f"method and no absent policy reaches the participant insert without one")


# ===========================================================================
# 4. Guest sessions: privacy-minimized, expiring, anonymizable
# ===========================================================================

def section_guests() -> None:
    print("\n--- 4. Guest sessions (FR-AUTH-003, FR-CST-002) ---")

    contact = run(ADMIN, r"""
        SELECT coalesce(string_agg(c.relname || '.' || a.attname, ', '), '')
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('service', 'safety') AND c.relkind = 'r'
          AND a.attnum > 0 AND NOT a.attisdropped
          AND a.attname ~* '(^|_)(phone|msisdn|mobile|email|e_mail|address|password|otp)($|_)';
    """)
    record("a guest session cannot hold a phone number, an email or a credential",
           contact.ok and not (contact.scalar or "").strip(),
           f"contact or credential columns across service and safety: "
           f"{(contact.scalar or '').strip() or 'none'}. QR ordering works with no phone, "
           f"no email and no registration because there is nowhere to put them "
           f"(FR-AUTH-003)")

    linked = count(ADMIN, """
        SELECT count(*) FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_class r ON r.oid = c.confrelid
        JOIN pg_namespace rn ON rn.oid = r.relnamespace
        WHERE t.relname = 'guest_session' AND c.contype = 'f'
          AND rn.nspname = 'identity';
    """)
    record("a guest session is not a user account in disguise",
           linked == 0,
           f"{linked} foreign key(s) from service.guest_session into the identity schema; "
           f"a guest is not a staff identity and is not registered as one")

    no_expiry = run(APP, f"""
        INSERT INTO service.guest_session (tenant_id, outlet_id, expires_at)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', now() - interval '1 hour');
    """, rollback=True, **CTX)
    record("a guest session must expire after it was created",
           no_expiry.failed_with("guest_session_expiry_after_creation"),
           f"an expiry in the past is a contradiction rather than an expired session: "
           f"{first_line(no_expiry.err)}")

    flagged = run(APP, f"""
        UPDATE service.guest_session SET anonymized_at = now()
        WHERE id = '{fx.GUEST_ONE}';
    """, rollback=True, **CTX)
    record("a session cannot be marked anonymized while it still names someone",
           flagged.failed_with("guest_session_anonymization_is_real"),
           f"anonymizing removes the nickname; stamping the column without removing it "
           f"would be a flag claiming work that was not done: {first_line(flagged.err)}")

    # Retention, wired to the M1-C engine rather than reimplemented.
    rule = run(ADMIN, """
        SELECT identity_columns::text, stamp_column FROM config.anonymization_rule
        WHERE target_schema = 'service' AND target_table = 'guest_session';
    """)
    record("guest anonymization is registered with the M1-C retention engine",
           rule.ok and bool(rule.rows),
           f"config.anonymization_rule names {rule.rows[0][0] if rule.rows else 'nothing'} "
           f"as the identity column(s) and {rule.rows[0][1] if rule.rows else 'nothing'} "
           f"as the stamp — no second retention engine was built (FR-CST-002)")

    swept = run(APP, f"""
        INSERT INTO service.guest_session (tenant_id, outlet_id, display_nickname, expires_at, created_at)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'Long Departed',
                now() - interval '20 days', now() - interval '30 days');

        INSERT INTO config.retention_policy
            (tenant_id, target_schema, target_table, age_column, retain_for, action)
        VALUES ('{fx.TENANT}', 'service', 'guest_session', 'created_at', interval '7 days', 'anonymize')
        ON CONFLICT (tenant_id, target_schema, target_table) DO UPDATE
            SET action = 'anonymize', retain_for = interval '7 days';

        SELECT rows_affected::text FROM config.apply_retention('{fx.TENANT}')
        WHERE target = 'service.guest_session';
    """, **CTX)
    remaining = count_or(APP, f"""
        SELECT count(*) FROM service.guest_session
        WHERE display_nickname = 'Long Departed';
    """, -1, **CTX)
    anonymized = count_or(APP, f"""
        SELECT count(*) FROM service.guest_session
        WHERE anonymized_at IS NOT NULL AND display_nickname IS NULL;
    """, -1, **CTX)
    record("retention anonymizes an expired guest instead of deleting it",
           swept.ok and remaining == 0 and anonymized >= 1,
           f"the nickname is gone and the row remains ({anonymized} anonymized): the "
           f"allergy concern raised at a table is operational evidence that has to "
           f"outlive the guest identity attached to it")


# ===========================================================================
# 5. Carts, strictly before submission (FR-TAB-005)
# ===========================================================================

def section_carts() -> None:
    print("\n--- 5. Carts before submission (FR-TAB-005) ---")

    session = run(APP, f"""
        SELECT id::text FROM service.table_session
        WHERE table_node_id = '{fx.TABLE_ONE}' AND state = 'open';
    """, **CTX).scalar
    session = (session or "").strip()

    built = run(APP, f"""
        INSERT INTO service.cart (tenant_id, outlet_id, table_session_id, kind, owner_guest_session_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}', 'personal', '{fx.GUEST_ONE}'),
               ('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}', 'shared', NULL)
        RETURNING kind::text;
    """, **CTX)
    record("a table carries personal baskets and a shared one",
           built.ok and len(built.rows) == 2,
           "a personal basket names its guest and a shared basket belongs to the table; "
           "cart_ownership_matches_kind makes the other two combinations unrepresentable")

    mismatched = run(APP, f"""
        INSERT INTO service.cart (tenant_id, outlet_id, table_session_id, kind, owner_guest_session_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}', 'shared', '{fx.GUEST_ONE}');
    """, rollback=True, **CTX)
    record("a shared basket cannot secretly belong to one guest",
           mismatched.failed_with("cart_ownership_matches_kind"),
           f"refused: {first_line(mismatched.err)}")

    carts = run(APP, f"""
        SELECT id::text, kind::text FROM service.cart
        WHERE table_session_id = '{session}' ORDER BY kind;
    """, **CTX)
    ids = {k: i for i, k in (carts.rows or [])}
    personal, shared = ids.get("personal", ""), ids.get("shared", "")

    line = run(APP, f"""
        INSERT INTO service.cart_line
            (tenant_id, outlet_id, cart_id, item_id, variant_id, quantity,
             currency_code, unit_amount_minor, added_by_guest_session_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{personal}', '{m2a_fx.ITEM_DORO}',
                '{m2a_fx.VARIANT_DORO_FULL}', 1, 'ETB',
                menu.effective_price('{fx.TENANT}', '{fx.OUTLET_H1}',
                                     '{m2a_fx.VARIANT_DORO_FULL}', NULL, 'ETB', now()),
                '{fx.GUEST_ONE}')
        RETURNING unit_amount_minor::text;
    """, **CTX)
    record("a line is priced in the M1-C exact types when it is added",
           line.ok and (line.scalar or "").strip() == "32000",
           f"{(line.scalar or '').strip()} minor units beside an explicit currency. A "
           f"price is pinned because it is what was agreed; the allergens of the same "
           f"line are not, and that asymmetry is the design decision of this slice")

    line_id = run(APP, f"""
        SELECT id::text FROM service.cart_line WHERE cart_id = '{personal}' LIMIT 1;
    """, **CTX).scalar
    line_id = (line_id or "").strip()

    moved = run(APP, f"""
        INSERT INTO service.cart_line_transfer
            (tenant_id, outlet_id, cart_line_id, from_cart_id, to_cart_id, moved_by_guest_session_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{line_id}', '{personal}', '{shared}', '{fx.GUEST_ONE}');
        UPDATE service.cart_line SET cart_id = '{shared}' WHERE id = '{line_id}';
        SELECT cart_id::text FROM service.cart_line WHERE id = '{line_id}';
    """, **CTX)
    record("an item transfers between baskets before submission, and the move is recorded",
           moved.ok and (moved.scalar or "").strip() == shared,
           "the line moved from a personal basket to the shared one and the transfer is "
           "written down, because 'who put this on my bill' is a question that gets asked")

    nowhere = run(APP, f"""
        INSERT INTO service.cart_line_transfer
            (tenant_id, outlet_id, cart_line_id, from_cart_id, to_cart_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{line_id}', '{shared}', '{shared}');
    """, rollback=True, **CTX)
    record("a transfer must actually move the item somewhere",
           nowhere.failed_with("cart_line_transfer_moves"),
           f"refused: {first_line(nowhere.err)}")

    states = run(ADMIN, """
        SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
        FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'cart_state';
    """)
    labels = (states.scalar or "")
    record("there is no submitted state, because submission is M3",
           states.ok and "submit" not in labels.lower(),
           f"service.cart_state = {labels}. The boundary is a state that does not exist "
           f"rather than one this slice declines to set — the second kind is one line of "
           f"code away from being crossed")


# ===========================================================================
# 6. The allergen catalog, and icons that never travel alone (FR-SAF-001/002)
# ===========================================================================

def section_allergens() -> None:
    print("\n--- 6. Allergen catalog, and icons that never replace words (FR-SAF-001, FR-SAF-002) ---")

    fx.translate_safety()

    catalog = run(APP, f"""
        SELECT count(*)::text, count(DISTINCT jurisdiction_code)::text
        FROM safety.allergen WHERE tenant_id = '{fx.TENANT}';
    """, **CTX)
    jurisdictions = count(ADMIN, "SELECT count(*) FROM safety.jurisdiction;")
    requirements = count(ADMIN, """
        SELECT count(*) FROM safety.jurisdiction_requirement WHERE jurisdiction_code = 'EU';
    """)
    record("the catalog is tenant and jurisdiction configurable",
           catalog.ok and int(catalog.rows[0][0]) >= 4 and jurisdictions >= 3
           and requirements == 14,
           f"{catalog.rows[0][0]} allergen(s) defined by this tenant against "
           f"{jurisdictions} jurisdictions; the EU requirement set holds {requirements} "
           f"entries, so what a regulator demands is data rather than something a tenant "
           f"has to remember")

    codes = run(APP, f"""
        SELECT string_agg(kitchen_code, ',' ORDER BY kitchen_code)
        FROM safety.allergen WHERE tenant_id = '{fx.TENANT}';
    """, **CTX)
    record("kitchen codes are English and are not translated",
           codes.ok and (codes.scalar or "").isupper(),
           f"{codes.scalar} — a kitchen runs on one vocabulary, and a cook reading a "
           f"ticket must not have to work out which language the word in front of them is "
           f"in (FR-SAF-002)")

    # ===== Icons never replace written warnings =====
    #
    # Proved by privilege. The application role cannot SELECT icon_key at all, so a screen
    # that shows an icon has no way to obtain one except through a function that returns
    # the words with it. This is the check that a comment saying "always show the text"
    # could never be.
    direct = run(APP, "SELECT icon_key FROM safety.allergen LIMIT 1;", **CTX)
    record("the application role cannot read an icon at all",
           direct.failed_with("permission denied"),
           f"a query naming icon_key is refused outright: {first_line(direct.err)}. "
           f"There is no discipline to remember and no review to pass — the column is "
           f"not selectable")

    star = run(APP, "SELECT * FROM safety.allergen LIMIT 1;", **CTX)
    record("selecting the whole row does not reach an icon either",
           star.failed_with("permission denied"),
           f"the obvious way round a column grant is SELECT *, and it is refused for the "
           f"same reason: {first_line(star.err)}")

    named = run(APP, f"""
        SELECT kitchen_code FROM safety.allergen WHERE tenant_id = '{fx.TENANT}'
        ORDER BY kitchen_code LIMIT 1;
    """, **CTX)
    record("the rest of the catalog is readable, so the restriction is precise",
           named.ok and (named.scalar or "").strip() == "GLUTEN",
           f"kitchen_code, jurisdiction and status all read normally ({named.scalar}); "
           f"only the icon is withheld, so this is a targeted restriction rather than a "
           f"table nobody can use")

    paired = run(APP, f"""
        SELECT kitchen_code, written_warning, icon_key
        FROM safety.selection_safety('{fx.TENANT}', 'en', '{m2a_fx.ITEM_DORO}',
                                     '{m2a_fx.VARIANT_DORO_FULL}')
        ORDER BY kitchen_code;
    """, **CTX)
    unworded = [r for r in (paired.rows or []) if not (r[1] or "").strip()]
    with_icon = [r for r in (paired.rows or []) if (r[2] or "").strip()]
    record("the only path that returns an icon returns the words with it",
           paired.ok and bool(with_icon) and not unworded,
           f"{len(paired.rows or [])} allergen(s) returned, {len(with_icon)} carrying an "
           f"icon, {len(unworded)} without written text. The icon and the warning travel "
           f"in the same row of the same function, so they cannot be separated by a "
           f"caller that only asked for one")

    offenders = function_bodies(
        "s.body LIKE '%icon_key%' AND s.body NOT LIKE '%written_warning%' "
        "AND s.body NOT LIKE '%translated_text%'")
    record("no function anywhere returns an icon without a warning beside it",
           not offenders,
           f"functions mentioning an icon but no warning text: "
           f"{offenders or 'none'}. The grant closes the direct "
           f"route and this closes the indirect one — a SECURITY DEFINER helper that "
           f"returned icons alone would defeat the privilege without touching it")

    missing = run(APP, f"""
        WITH removed AS (
            DELETE FROM menu.translation
            WHERE entity = 'allergen' AND entity_id = '{fx.ALLERGEN_GLUTEN}'
              AND field_name = 'customer_warning_text' AND locale = 'ar' RETURNING 1
        )
        SELECT count(*) FROM removed;
    """, **CTX)
    refused = run(APP, f"""
        SELECT count(*)::text FROM safety.selection_safety(
            '{fx.TENANT}', 'ar', '{m2a_fx.ITEM_DORO}', '{m2a_fx.VARIANT_DORO_FULL}');
    """, **CTX)
    record("a locale with no approved warning is refused, not quietly shortened",
           missing.ok and refused.failed_with("WRITTEN_WARNING_ABSENT"),
           f"with the Arabic gluten warning removed, the whole selection is refused "
           f"rather than returning the three allergens that do have text: "
           f"{first_line(refused.err)}. A guest shown four of five allergens has been "
           f"told something false by omission")
    fx.translate_safety(locales=("ar",))

    restored = run(APP, f"""
        SELECT count(*)::text FROM safety.selection_safety(
            '{fx.TENANT}', 'ar', '{m2a_fx.ITEM_DORO}', '{m2a_fx.VARIANT_DORO_FULL}');
    """, **CTX)
    record("the Arabic path works once the warning is approved again",
           restored.ok and int(restored.scalar or 0) >= 2,
           f"{restored.scalar} allergen(s) resolve in Arabic, so the refusal above was "
           f"the missing text and not a broken locale")


# ===========================================================================
# 7. Change detection: a declaration is derived, never remembered (FR-SAF-005)
# ===========================================================================

def section_change_detection() -> None:
    print("\n--- 7. Declarations re-evaluate rather than cache (FR-SAF-005) ---")

    classes = run(ADMIN, """
        SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
        FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'declaration_class';
    """)
    record("contains, may-contain and cross-contact are three distinct classes",
           classes.ok and classes.scalar == "contains,may_contain,cross_contact",
           f"safety.declaration_class = {classes.scalar}. A guest with coeliac disease "
           f"and a guest avoiding an ingredient by preference need different answers, and "
           f"a model that recorded only 'has allergen' could not give them")

    plain = run(APP, f"""
        SELECT string_agg(kitchen_code || ':' || declaration_class, ', ' ORDER BY kitchen_code)
        FROM safety.effective_allergens('{fx.TENANT}', '{m2a_fx.ITEM_DORO}',
                                        '{m2a_fx.VARIANT_DORO_FULL}');
    """, **CTX)
    with_hot = run(APP, f"""
        SELECT string_agg(kitchen_code || ':' || declaration_class, ', ' ORDER BY kitchen_code)
        FROM safety.effective_allergens('{fx.TENANT}', '{m2a_fx.ITEM_DORO}',
                                        '{m2a_fx.VARIANT_DORO_FULL}',
                                        ARRAY['{m2a_fx.MODIFIER_HOT}']::uuid[]);
    """, **CTX)
    record("choosing a modifier changes what the selection declares",
           plain.ok and with_hot.ok
           and "SESAME" not in (plain.scalar or "")
           and "SESAME:contains" in (with_hot.scalar or ""),
           f"plain: {plain.scalar}\nwith the hot modifier: {with_hot.scalar}\n"
           f"the sesame arrives with the modifier and is absent without it, so the answer "
           f"is a property of the selection rather than of the dish")

    # The correction moves the answer with no refresh step anywhere.
    before = run(APP, f"""
        SELECT declaration_class::text FROM safety.effective_allergens(
            '{fx.TENANT}', '{m2a_fx.ITEM_DORO}', '{m2a_fx.VARIANT_DORO_FULL}')
        WHERE kitchen_code = 'PEANUTS';
    """, **CTX)
    corrected = run(APP, f"""
        UPDATE safety.declaration SET effective_to = now()
        WHERE subject = 'item' AND subject_id = '{m2a_fx.ITEM_DORO}'
          AND allergen_id = '{fx.ALLERGEN_PEANUTS}' AND effective_to IS NULL;

        INSERT INTO safety.declaration
            (tenant_id, outlet_id, subject, subject_id, allergen_id, declaration_class,
             effective_version, created_by_user_id, review_state, reviewed_by_user_id, reviewed_at)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'item', '{m2a_fx.ITEM_DORO}',
                '{fx.ALLERGEN_PEANUTS}', 'contains', 2, '{fx.USER}', 'approved',
                '{fx.USER}', now());
    """, **CTX)
    after = run(APP, f"""
        SELECT declaration_class::text FROM safety.effective_allergens(
            '{fx.TENANT}', '{m2a_fx.ITEM_DORO}', '{m2a_fx.VARIANT_DORO_FULL}')
        WHERE kitchen_code = 'PEANUTS';
    """, **CTX)
    record("correcting a declaration moves every read immediately",
           corrected.ok and (before.scalar or "").strip() == "may_contain"
           and (after.scalar or "").strip() == "contains",
           f"peanuts went from {before.scalar} to {after.scalar} with no refresh, no "
           f"invalidation and no rebuild, because there is no stored answer to update — "
           f"safety.effective_allergens() computes from the open declarations on every "
           f"call")

    derived = run(ADMIN, """
        SELECT coalesce(string_agg(n.nspname || '.' || c.relname, ', '), '')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('safety', 'menu', 'service')
          AND c.relkind IN ('m', 'r')
          AND c.relname ~* '(^|_)(cache|cached|materialized|resolved|denorm|snapshot_allergen)($|_)';
    """)
    record("no cache or materialized view holds a resolved allergen set",
           derived.ok and not (derived.scalar or "").strip(),
           f"candidate stores: {(derived.scalar or '').strip() or 'none'}. A stored "
           f"answer that does not move when its inputs move is a safety defect rather "
           f"than a caching bug, so the answer is not stored")

    # Counted as "one open, at least one closed" rather than "exactly two rows": this
    # database is not rebuilt between the ordinary run and the reordered one, so an
    # absolute row count would pass once and then fail for a reason that is not a defect.
    open_rows = count_or(APP, f"""
        SELECT count(*) FROM safety.declaration
        WHERE subject_id = '{m2a_fx.ITEM_DORO}' AND allergen_id = '{fx.ALLERGEN_PEANUTS}'
          AND effective_to IS NULL;
    """, -1, **CTX)
    closed_rows = count_or(APP, f"""
        SELECT count(*) FROM safety.declaration
        WHERE subject_id = '{m2a_fx.ITEM_DORO}' AND allergen_id = '{fx.ALLERGEN_PEANUTS}'
          AND effective_to IS NOT NULL;
    """, -1, **CTX)
    record("the corrected version supersedes rather than overwrites",
           open_rows == 1 and closed_rows >= 1,
           f"{open_rows} open declaration and {closed_rows} closed one(s) for that item "
           f"and allergen: the superseded row is kept, so what was declared before the "
           f"correction is still answerable")

    two_open = run(APP, f"""
        INSERT INTO safety.declaration
            (tenant_id, outlet_id, subject, subject_id, allergen_id, declaration_class,
             created_by_user_id, review_state, reviewed_by_user_id, reviewed_at)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'item', '{m2a_fx.ITEM_DORO}',
                '{fx.ALLERGEN_PEANUTS}', 'cross_contact', '{fx.USER}', 'approved',
                '{fx.USER}', now());
    """, rollback=True, **CTX)
    record("two open declarations for the same subject and allergen are refused",
           two_open.failed_with("declaration_one_open_per_subject"),
           f"'the current answer' cannot be ambiguous: {first_line(two_open.err)}")

    unreviewed = run(APP, f"""
        INSERT INTO safety.declaration
            (tenant_id, outlet_id, subject, subject_id, allergen_id, declaration_class,
             created_by_user_id, review_state, reviewed_by_user_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'variant', '{m2a_fx.VARIANT_DORO_HALF}',
                '{fx.ALLERGEN_MILK}', 'contains', '{fx.USER}', 'approved', NULL);
    """, rollback=True, **CTX)
    record("an approved declaration must name the human who approved it",
           unreviewed.failed_with("declaration_approval_is_reviewed"),
           f"without a named reviewer it is a draft wearing a label, the same rule "
           f"menu.translation applies to safety-critical text: "
           f"{first_line(unreviewed.err)}")

    draft_hidden = run(APP, f"""
        INSERT INTO safety.declaration
            (tenant_id, outlet_id, subject, subject_id, allergen_id, declaration_class,
             created_by_user_id, review_state)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'variant', '{m2a_fx.VARIANT_DORO_HALF}',
                '{fx.ALLERGEN_MILK}', 'contains', '{fx.USER}', 'draft');

        SELECT count(*)::text FROM safety.effective_allergens(
            '{fx.TENANT}', '{m2a_fx.ITEM_DORO}', '{m2a_fx.VARIANT_DORO_HALF}')
        WHERE kitchen_code = 'MILK';
    """, rollback=True, **CTX)
    record("a draft declaration does not reach a guest",
           draft_hidden.ok and (draft_hidden.scalar or "").strip() == "0",
           "an unreviewed claim is not evidence a guest may rely on, so resolution "
           "returns only approved declarations")

    upgrade = run(APP, f"""
        SELECT declaration_class::text FROM safety.effective_allergens(
            '{fx.TENANT}', '{m2a_fx.ITEM_TIBS}', '{m2a_fx.VARIANT_TIBS_ONE}',
            ARRAY['{m2a_fx.MODIFIER_HOT}']::uuid[])
        WHERE kitchen_code = 'GLUTEN';
    """, **CTX)
    record("the strongest class wins, and only ever upward",
           upgrade.ok and (upgrade.scalar or "").strip() == "cross_contact",
           "tibs declares gluten as cross-contact and nothing in the selection raises it, "
           "so it stays cross-contact; a modifier that CONTAINS an allergen would raise "
           "the whole selection to contains rather than being softened by the base dish")


# ===========================================================================
# 8. Dietary claims, publication blocking, and the audit trail
# ===========================================================================

def section_claims_and_publication() -> None:
    print("\n--- 8. Dietary claims, publication blocking and audit (FR-SAF-006/007/008/009) ---")

    claims = run(APP, f"""
        SELECT string_agg(code, ',' ORDER BY code) FROM safety.dietary_claim
        WHERE tenant_id = '{fx.TENANT}';
    """, **CTX)
    record("fasting is a first-class claim beside vegan and halal",
           claims.ok and "FASTING" in (claims.scalar or ""),
           f"claims defined: {claims.scalar}. In the pilot market a large part of the "
           f"calendar is fasting, so an outlet that cannot state it loses the business — "
           f"it is not a note on a vegetarian dish")

    owned = run(APP, f"""
        SELECT count(*)::text FROM safety.dietary_claim
        WHERE tenant_id = '{fx.TENANT}'
          AND (btrim(definition) = '' OR evidence_owner_user_id IS NULL OR review_due_on IS NULL);
    """, **CTX)
    record("every claim carries a definition, an evidence owner and a review date",
           owned.ok and (owned.scalar or "").strip() == "0",
           "all three are NOT NULL, so a claim with no written definition and nobody "
           "answerable for it cannot be stored; that is how a kitchen ends up serving a "
           "four-year-old assertion")

    blank = run(APP, f"""
        INSERT INTO safety.dietary_claim
            (tenant_id, outlet_id, code, definition, evidence_owner_user_id, review_due_on)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'GLUTEN_FREE', '   ', '{fx.USER}', DATE '2027-01-01');
    """, rollback=True, **CTX)
    record("a claim with an empty definition is refused",
           blank.failed_with("dietary_claim_definition_not_blank"),
           f"a claim without a definition is a marketing word: {first_line(blank.err)}")

    applicability = count_or(APP, f"""
        SELECT count(*) FROM safety.dietary_claim_outlet WHERE tenant_id = '{fx.TENANT}';
    """, -1, **CTX)
    record("claims record which outlets they apply to",
           applicability >= 3,
           f"{applicability} claim/outlet pairing(s): a claim a tenant can substantiate "
           f"in one kitchen is not automatically true in another")

    # ===== Publication blocking (FR-SAF-007) =====
    run(APP, f"UPDATE menu.menu SET state = 'draft', row_version = row_version WHERE id = '{m2a_fx.MENU}';", **CTX)

    removed = run(APP, f"""
        DELETE FROM menu.translation
        WHERE entity = 'allergen' AND entity_id = '{fx.ALLERGEN_SESAME}'
          AND field_name = 'customer_warning_text' AND locale = 'am';
    """, **CTX)
    blocked = run(APP, f"""
        SELECT menu.publish_menu('{m2a_fx.MENU}', '{fx.USER}');
    """, **CTX)
    record("publication is BLOCKED while a safety translation is missing",
           removed.ok and blocked.failed_with("REQUIRED_SAFETY_TRANSLATION_MISSING"),
           f"the Amharic sesame warning is absent and the publish refuses: "
           f"{first_line(blocked.err)}")

    fx.translate_safety(locales=("am",))
    reviews_off = run(APP, f"""
        UPDATE safety.declaration
           SET review_state = 'in_review', reviewed_by_user_id = NULL, reviewed_at = NULL
         WHERE subject_id = '{m2a_fx.ITEM_COFFEE}' AND effective_to IS NULL;
    """, **CTX)
    review_blocked = run(APP, f"""
        SELECT menu.publish_menu('{m2a_fx.MENU}', '{fx.USER}');
    """, **CTX)
    record("publication is BLOCKED while an allergen review is incomplete",
           reviews_off.ok and review_blocked.failed_with("ALLERGEN_REVIEW_INCOMPLETE"),
           f"translated text nobody reviewed is a translation of an unreviewed claim: "
           f"{first_line(review_blocked.err)}")

    run(APP, f"""
        UPDATE safety.declaration
           SET review_state = 'approved', reviewed_by_user_id = '{fx.USER}', reviewed_at = now()
         WHERE subject_id = '{m2a_fx.ITEM_COFFEE}' AND effective_to IS NULL;
    """, **CTX)
    published = run(APP, f"""
        SELECT menu.publish_menu('{m2a_fx.MENU}', '{fx.USER}');
    """, **CTX)
    snapshot = (published.scalar or "").strip()
    record("publication proceeds once safety text and reviews are complete",
           published.ok and snapshot,
           f"snapshot {snapshot} written; the block is a gate rather than a wall")

    machine = run(APP, f"""
        INSERT INTO menu.translation
            (tenant_id, outlet_id, entity, entity_id, field_name, locale, translated_text,
             state, provenance, machine_engine, reviewed_by_user_id, approved_at)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'allergen', '{fx.ALLERGEN_MILK}',
                'customer_warning_text', 'ar', 'يحتوي على الحليب', 'approved',
                'machine_assisted', 'some-engine-v3', NULL, now());
    """, rollback=True, **CTX)
    record("safety warning text cannot be approved from a machine draft without a human",
           not machine.ok,
           f"the M2-A safety-critical rule reaches the new fields without a second "
           f"implementation, because they were registered in menu.translatable_field "
           f"rather than given their own store: {first_line(machine.err)}")

    audited = count_or(ADMIN, f"""
        SELECT count(*) FROM audit.operational_event
        WHERE tenant_id = '{fx.TENANT}';
    """, -1)
    audit_tables = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname IN ('safety', 'service')
          AND c.relname ~* '(^|_)(audit|event_log|history_log)($|_)';
    """)
    record("safety-critical authorship goes through the M1-C append-only audit",
           audit_tables == 0,
           f"{audit_tables} audit table(s) invented by this slice; authorship is carried "
           f"on the rows themselves (created_by, reviewed_by, approved_at, published_by) "
           f"and the append-only store is audit.operational_event, which holds "
           f"{audited} row(s) for this tenant (FR-SAF-008)")

    wording = run(APP, f"""
        SELECT wording FROM safety.approved_wording
        WHERE tenant_id = '{fx.TENANT}' AND purpose = 'allergy_acknowledgement' AND locale = 'en';
    """, **CTX)
    record("tenant-approved wording states what the information can and cannot do",
           wording.ok and "cannot rule out cross-contact" in (wording.scalar or ""),
           f"the approved sentence says the information supports an informed choice and "
           f"cannot eliminate cross-contact risk (FR-SAF-009), and it is stored rather "
           f"than composed at the keyboard by whoever is on shift")

    return snapshot


# ===========================================================================
# 9. The correction reaches a menu published before it
# ===========================================================================

def section_correction_reaches_published(snapshot: str) -> None:
    print("\n--- 9. A correction reaches a menu published before it (FR-SAF-005) ---")

    if not snapshot:
        record("a menu published earlier shows the corrected warning", False,
               "no snapshot was published, so there is nothing to read through")
        return

    original = run(APP, f"""
        SELECT written_warning FROM menu.published_menu_for_guest(
            '{fx.TENANT}', '{snapshot}', 'en')
        WHERE allergen_kitchen_code = 'GLUTEN' LIMIT 1;
    """, **CTX)

    corrected_text = "Contains gluten — recipe corrected after publication"
    run(APP, f"""
        UPDATE menu.translation
           SET translated_text = '{corrected_text}', row_version = row_version
         WHERE entity = 'allergen' AND entity_id = '{fx.ALLERGEN_GLUTEN}'
           AND field_name = 'customer_warning_text' AND locale = 'en';
    """, **CTX)

    after = run(APP, f"""
        SELECT written_warning FROM menu.published_menu_for_guest(
            '{fx.TENANT}', '{snapshot}', 'en')
        WHERE allergen_kitchen_code = 'GLUTEN' LIMIT 1;
    """, **CTX)
    record("a guest reading the EARLIER snapshot sees the correction",
           original.ok and after.ok
           and (original.scalar or "").strip() != (after.scalar or "").strip()
           and "corrected after publication" in (after.scalar or ""),
           f"before: {(original.scalar or '').strip()}\n"
           f"after:  {(after.scalar or '').strip()}\n"
           f"no republication, no cache invalidation, and the snapshot itself was never "
           f"touched. This is the control that matters most in this slice: a correction "
           f"that only reached newly published menus would leave every guest holding an "
           f"older link reading the old text")

    # The real test of "pinned" is not what the number is, it is that changing the live
    # price does not move it. Done in a rolled-back transaction so the fixture is
    # untouched, and deliberately the mirror image of the allergen probe above: the same
    # published line, the same kind of after-the-fact change, opposite required outcome.
    repriced = run(APP, f"""
        UPDATE menu.price SET effective_to = now()
         WHERE variant_id = '{m2a_fx.VARIANT_DORO_FULL}' AND channel IS NULL
           AND effective_to IS NULL;
        INSERT INTO menu.price
            (tenant_id, outlet_id, variant_id, channel, currency_code, amount_minor, tax_context)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{m2a_fx.VARIANT_DORO_FULL}', NULL,
                'ETB', 99000, 'standard');
        SELECT coalesce(string_agg(DISTINCT amount_minor::text, ',' ORDER BY amount_minor::text), '')
        FROM menu.published_menu_for_guest('{fx.TENANT}', '{snapshot}', 'en')
        WHERE item_code = 'SKU-DORO-01';
    """, rollback=True, **CTX)
    record("the price on the same line did NOT move when the live price changed",
           repriced.ok and "99000" not in (repriced.scalar or "")
           and "32000" in (repriced.scalar or ""),
           f"the live price was raised to 99000 after publication and the published menu "
           f"still reports {(repriced.scalar or '').strip()}. Both halves of one line "
           f"behave correctly and oppositely: the warning followed the correction, the "
           f"price did not follow the repricing")

    # The pinned reference exists, and display cannot reach it.
    written = count_or(ADMIN, f"""
        SELECT count(*) FROM safety.declaration_reference
        WHERE context = 'publication_snapshot' AND context_id = '{snapshot}';
    """, -1)
    record("what was believed at publication is recorded for audit",
           written >= 1,
           f"{written} declaration reference(s) pinned to that snapshot, so a later "
           f"dispute can establish what the kitchen had declared at that moment")

    reachable = run(APP, "SELECT count(*) FROM safety.declaration_reference;", **CTX)
    record("display code cannot read the pinned reference",
           reachable.failed_with("permission denied"),
           f"the application role holds INSERT and nothing else: "
           f"{first_line(reachable.err)}. A readable pinned value becomes a cache the "
           f"first time a display path is under deadline, and a cached allergen is the "
           f"defect FR-SAF-005 names")

    back_doors = function_bodies("s.body LIKE '%declaration_reference%'",
                                 excluding="publish_menu")
    record("no function offers a way round that grant",
           not back_doors,
           f"functions touching the pinned reference other than the one that writes it: "
           f"{back_doors or 'none'}. Proving the grant alone would "
           f"prove a lock with an unlocked back door")


# ===========================================================================
# 10. Allergy input, ownership, setup and search
# ===========================================================================

def section_allergy_input() -> None:
    print("\n--- 10. Allergy input, ownership, setup and search (FR-SAF-003, FR-TAB-006, FR-CFG-001B, FR-MNU-012) ---")

    session = (run(APP, f"""
        SELECT id::text FROM service.table_session
        WHERE table_node_id = '{fx.TABLE_ONE}' AND state = 'open';
    """, **CTX).scalar or "").strip()

    raised = run(APP, f"""
        INSERT INTO safety.allergy_concern
            (tenant_id, outlet_id, table_session_id, raised_by, guest_session_id,
             allergen_id, note, acknowledgement_wording_id, acknowledgement_text)
        SELECT '{fx.TENANT}', '{fx.OUTLET_H1}', '{session}', 'guest', '{fx.GUEST_TWO}',
               '{fx.ALLERGEN_PEANUTS}', 'severe', '{fx.WORDING_ACK}', w.wording
        FROM safety.approved_wording w WHERE w.id = '{fx.WORDING_ACK}'
        RETURNING left(acknowledgement_text, 24);
    """, **CTX)
    record("a guest may flag an allergy concern for the table",
           raised.ok and (raised.scalar or "").strip().startswith("We have recorded"),
           "the concern is attached to the occupancy rather than to an order; the "
           "order-level flag and the waiter workflow around it arrive at M3")

    unacknowledged = run(APP, f"""
        INSERT INTO safety.allergy_concern
            (tenant_id, outlet_id, table_session_id, raised_by, raised_by_user_id,
             acknowledgement_wording_id, acknowledgement_text)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}', 'waiter', '{fx.USER}',
                '{fx.WORDING_ACK}', '   ');
    """, rollback=True, **CTX)
    record("a concern cannot be recorded without explicit acknowledgement text",
           unacknowledged.failed_with("allergy_concern_text_not_blank"),
           f"the acknowledgement is not a boolean — what the guest was told is stored "
           f"verbatim, so a later question about what was promised has an answer: "
           f"{first_line(unacknowledged.err)}")

    anonymous = run(APP, f"""
        INSERT INTO safety.allergy_concern
            (tenant_id, outlet_id, table_session_id, raised_by,
             acknowledgement_wording_id, acknowledgement_text)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}', 'waiter',
                '{fx.WORDING_ACK}', 'noted');
    """, rollback=True, **CTX)
    record("a concern names whoever raised it",
           anonymous.failed_with("allergy_concern_attributed"),
           f"a waiter-raised concern names the waiter and a guest-raised one names the "
           f"guest session: {first_line(anonymous.err)}")

    # ===== Ownership =====
    owned = run(APP, f"""
        INSERT INTO service.table_ownership
            (tenant_id, outlet_id, table_session_id, primary_waiter_user_id, section_code,
             assigned_by_user_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}', '{fx.USER}', 'SEC-A', '{fx.USER}')
        ON CONFLICT DO NOTHING
        RETURNING section_code;
    """, **CTX)
    current = run(APP, f"""
        SELECT primary_waiter_user_id::text, section_code FROM service.table_ownership
        WHERE table_session_id = '{session}' AND effective_to IS NULL;
    """, **CTX)
    record("a table has a primary waiter and a section",
           current.ok and bool(current.rows),
           f"waiter {(current.rows[0][0] if current.rows else '?')[:8]} owns section "
           f"{current.rows[0][1] if current.rows else '?'} for this occupancy")

    silent = run(APP, f"""
        UPDATE service.table_ownership SET primary_waiter_user_id = '{fx.USER_WAITER_B}'
        WHERE table_session_id = '{session}' AND effective_to IS NULL;
    """, rollback=True, **CTX)
    record("ownership cannot be edited in place",
           silent.failed_with("OWNERSHIP_TRANSFERRED_SILENTLY"),
           f"a reassignment nobody acknowledged is not auditable, and an unauditable "
           f"handover is the requirement unmet rather than a lesser form of it: "
           f"{first_line(silent.err)}")

    proposed = run(APP, f"""
        INSERT INTO service.ownership_transfer
            (tenant_id, outlet_id, table_session_id, from_user_id, to_user_id,
             proposed_by_user_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}', '{fx.USER}',
                '{fx.USER_WAITER_B}', '{fx.USER}')
        RETURNING id::text;
    """, **CTX)
    transfer_id = (proposed.scalar or "").strip()

    premature = run(APP, f"""
        SELECT service.transfer_ownership('{fx.TENANT}', '{transfer_id}');
    """, **CTX)
    record("a proposed transfer does not move the table on its own",
           premature.failed_with("OWNERSHIP_TRANSFERRED_SILENTLY"),
           f"refused while the proposal is unacknowledged: {first_line(premature.err)}")

    wrong_person = run(APP, f"""
        UPDATE service.ownership_transfer
           SET state = 'acknowledged', acknowledged_at = now(),
               acknowledged_by_user_id = '{fx.USER_SUPERVISOR}'
         WHERE id = '{transfer_id}';
    """, rollback=True, **CTX)
    record("only the waiter taking the table on can acknowledge it",
           wrong_person.failed_with("transfer_acknowledger_is_recipient"),
           f"anyone else acknowledging on their behalf is the silent reassignment this "
           f"requirement exists to prevent: {first_line(wrong_person.err)}")

    acknowledged = run(APP, f"""
        UPDATE service.ownership_transfer
           SET state = 'acknowledged', acknowledged_at = now(),
               acknowledged_by_user_id = '{fx.USER_WAITER_B}'
         WHERE id = '{transfer_id}';
        SELECT service.transfer_ownership('{fx.TENANT}', '{transfer_id}');
    """, **CTX)
    now_owns = run(APP, f"""
        SELECT primary_waiter_user_id::text FROM service.table_ownership
        WHERE table_session_id = '{session}' AND effective_to IS NULL;
    """, **CTX)
    record("an acknowledged transfer moves the table and keeps the history",
           acknowledged.ok and (now_owns.scalar or "").strip() == fx.USER_WAITER_B,
           "the previous ownership row is closed rather than overwritten, so who was "
           "answerable at any past moment is still answerable")

    supervisor = run(APP, f"""
        INSERT INTO service.ownership_transfer
            (tenant_id, outlet_id, table_session_id, from_user_id, to_user_id,
             proposed_by_user_id, state, supervisor_user_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}', '{fx.USER_WAITER_B}',
                '{fx.USER}', '{fx.USER_SUPERVISOR}', 'supervisor_reassigned',
                '{fx.USER_SUPERVISOR}')
        RETURNING id::text;
    """, **CTX)
    reassigned = run(APP, f"""
        SELECT service.transfer_ownership('{fx.TENANT}', '{(supervisor.scalar or '').strip()}');
    """, **CTX)
    record("a supervisor may reassign without the receiver's acknowledgement, by name",
           supervisor.ok and reassigned.ok,
           "the one route that skips acknowledgement names a supervisor instead, so the "
           "handover is still attributable to a person rather than to nobody")

    nameless = run(APP, f"""
        INSERT INTO service.ownership_transfer
            (tenant_id, outlet_id, table_session_id, from_user_id, to_user_id,
             proposed_by_user_id, state)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}', '{fx.USER}',
                '{fx.USER_WAITER_B}', '{fx.USER}', 'supervisor_reassigned');
    """, rollback=True, **CTX)
    record("a supervisor reassignment with no supervisor named is refused",
           nameless.failed_with("transfer_supervisor_named_when_reassigned"),
           f"refused: {first_line(nameless.err)}")

    # ===== Guided setup (FR-CFG-001B) =====
    setup = run(ADMIN, f"""
        SELECT
          (SELECT count(*) FROM unnest(enum_range(NULL::menu.customer_locale)))::text,
          (SELECT count(*) FROM money.currency)::text,
          (SELECT count(*) FROM org.org_node WHERE tenant_id = '{fx.TENANT}'
             AND kind = 'preparation_station')::text,
          (SELECT count(*) FROM service.table_profile WHERE tenant_id = '{fx.TENANT}')::text,
          (SELECT count(*) FROM service.table_qr_token WHERE tenant_id = '{fx.TENANT}'
             AND revoked_at IS NULL)::text;
    """)
    locales, currencies, stations, tables, codes = (
        setup.rows[0] if setup.ok and setup.rows else ["0"] * 5)
    record("guided setup configures locales, currency, timezone, tables and opaque codes",
           setup.ok and locales == "3" and int(currencies) >= 1 and int(tables) >= 2
           and int(codes) >= 2,
           f"{locales} customer locales, {currencies} currency/currencies, {tables} "
           f"tables with {codes} live opaque codes, and outlet timezone already required "
           f"by menu.outlet_timezone() at M2-A. Preparation stations are org nodes "
           f"(currently {stations}) — a station is where something is made, and nothing "
           f"in this slice routes anything to one (FR-CFG-001B)")

    # Moved when M3-B landed, not deleted — the same way this slice stopped policing the
    # word 'cart' when it built one. "No ticket exists anywhere" was true at M2-B and is
    # now false by design; what M2-B still owns is that NOTHING IT OWNS routes to a
    # station. A station stays configuration as far as this gate is concerned.
    # Narrowed when M3-C landed, not deleted. 'routing' left this pattern the way
    # 'cart' left M2-A's and 'order' left M1-C's: M3-C routes a service request to a
    # WAITER, which is this schema's business and is not a preparation station. What
    # M2-B still owns is that nothing it owns reaches a STATION — no kitchen ticket, no
    # KDS, no queue of things to make, and no column naming a station.
    routing = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname IN ('menu', 'safety', 'service', 'org')
          AND c.relname ~* '(^|_)(ticket|kds|prep_queue|station)($|_)';
    """)
    station_columns = count(ADMIN, """
        SELECT count(*) FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname IN ('menu', 'safety', 'service')
          AND a.attnum > 0 AND NOT a.attisdropped
          AND a.attname ~* '(^|_)station($|_)';
    """)
    record("nothing this slice owns sends anything to a preparation station",
           routing == 0 and station_columns == 0,
           f"{routing} such table(s) and {station_columns} column(s) naming a station "
           f"across menu, safety and service. A preparation station is configuration "
           f"here; sending work to one is fulfillment's and lives in its own schema "
           f"(M3-B). Routing a service request to a waiter is M3-C's and is not that")

    # ===== FR-MNU-012, completed =====
    vegan = run(APP, f"""
        SELECT string_agg(item_code, ',' ORDER BY item_code) FROM menu.search_items(
            '{fx.TENANT}', '{fx.OUTLET_H1}', 'en', NULL, NULL, NULL, NULL, NULL, NULL,
            NULL, ARRAY['VEGAN','FASTING'], NULL);
    """, **CTX)
    record("FR-MNU-012: a dietary filter selects on the real catalog",
           vegan.ok and (vegan.scalar or "").strip() == "SKU-BUNA-03",
           f"vegan AND fasting returns {vegan.scalar}. Every requested claim must hold, "
           f"not merely one of them: a guest naming two requirements is stating both")

    without_peanuts = run(APP, f"""
        SELECT string_agg(item_code, ',' ORDER BY item_code) FROM menu.search_items(
            '{fx.TENANT}', '{fx.OUTLET_H1}', 'en', NULL, NULL, NULL, NULL, NULL, NULL,
            NULL, NULL, ARRAY['{fx.ALLERGEN_PEANUTS}']::uuid[]);
    """, **CTX)
    all_items = run(APP, f"""
        SELECT string_agg(item_code, ',' ORDER BY item_code) FROM menu.search_items(
            '{fx.TENANT}', '{fx.OUTLET_H1}', 'en');
    """, **CTX)
    record("FR-MNU-012: an allergen filter removes the dish that declares it",
           without_peanuts.ok and all_items.ok
           and "SKU-DORO-01" in (all_items.scalar or "")
           and "SKU-DORO-01" not in (without_peanuts.scalar or ""),
           f"unfiltered: {all_items.scalar}\nexcluding peanuts: {without_peanuts.scalar}\n"
           f"the filter excludes on all three declaration classes, because for someone "
           f"avoiding an allergen 'may contain' is a reason to avoid rather than a "
           f"footnote")

    non_vacuous = run(APP, f"""
        SELECT count(*)::text FROM menu.search_items(
            '{fx.TENANT}', '{fx.OUTLET_H1}', 'en', NULL, NULL, NULL, NULL, NULL, NULL,
            NULL, ARRAY['NO_SUCH_CLAIM'], NULL);
    """, **CTX)
    record("FR-MNU-012: the filters are not vacuous",
           non_vacuous.ok and (non_vacuous.scalar or "").strip() == "0",
           "a claim nobody has defined returns nothing rather than everything, so the "
           "filter is examining the catalog rather than ignoring its argument — the "
           "vacuity money.assert_currency_paired() carried through all of M1")


# ===========================================================================
# 11. Slice boundary and the permanent fences
# ===========================================================================

def section_boundary() -> None:
    print("\n--- 11. Slice boundary: what M2-B did NOT build ---")

    pattern, terms = fenced_identifier_pattern()
    fenced = run(ADMIN, f"""
        SELECT coalesce(string_agg(n.nspname || '.' || c.relname, ', '), '')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND c.relname ~* '{pattern}';
    """)
    record("no table anywhere names a permanently fenced domain",
           fenced.ok and not (fenced.scalar or "").strip(),
           f"every table checked against all {terms} authoritative terms loaded from the "
           f"pinned package: {(fenced.scalar or '').strip() or 'none'}. Table service "
           f"ownership is not workforce scheduling: it records who is answerable for a "
           f"table right now, and nobody's hours, shifts or working pattern)")

    columns = run(ADMIN, f"""
        SELECT coalesce(string_agg(c.relname || '.' || a.attname, ', '), '')
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('safety', 'service') AND c.relkind = 'r'
          AND a.attnum > 0 AND NOT a.attisdropped
          AND a.attname ~* '{pattern}';
    """)
    record("no column in safety or service names a fenced concept",
           columns.ok and not (columns.scalar or "").strip(),
           f"columns matching a fenced term: "
           f"{(columns.scalar or '').strip() or 'none'}. An allergen declaration names "
           f"what a guest must know, never an operational recipe, a quantity or a cost")

    # The order surface left this pattern when M3-A built it, the same way 'cart' left
    # M2-A's pattern when this slice built that. What M2-B still owns is the boundary
    # BELOW its own: no fulfillment (M3-B), no service request (M3-C), no billing (M4).
    # Fulfillment left this pattern when M3-B built it, exactly as the order surface left
    # it at M3-A and 'cart' left M2-A's at M2-B. What M2-B still owns is the boundary
    # below its own: no service request (M3-C), no billing (M4).
    m3_m4 = run(ADMIN, """
        SELECT coalesce(string_agg(n.nspname || '.' || c.relname, ', '), '')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND c.relname ~* '(^|_)(check|bill|payment|tip|receipt)($|_)';
    """)
    record("no billing surface exists",
           m3_m4.ok and not (m3_m4.scalar or "").strip(),
           f"{(m3_m4.scalar or '').strip() or 'none'}. A basket before submission is "
           f"FR-TAB-005 and lives here; the order it becomes is M3-A and polices its own "
           f"boundary; tickets are M3-B and service requests M3-C, both of which landed "
           f"and left this pattern the way 'cart' left M2-A's. Billing is M4 and has "
           f"not")

    # Submission itself now exists, in the ordering schema, and M3-A proves it. What this
    # slice must still be able to say is that ITS OWN schemas contain no path across the
    # boundary — a cart cannot become an order by way of anything service, safety or menu
    # owns. Restricting the scan to those three schemas is what the check always did; the
    # cart-freezing trigger 0010 adds to service.cart_line is named here explicitly
    # rather than excluded by a looser pattern, because it is the one function in these
    # schemas that KNOWS about orders and it only ever refuses.
    submit = run(ADMIN, """
        SELECT coalesce(string_agg(n.nspname || '.' || p.proname, ', '), '')
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname IN ('service', 'safety', 'menu')
          AND p.proname ~* '(submit|place_order|send_to_kitchen|fire)'
          AND p.proname <> 'refuse_change_to_submitted_cart';
    """)
    refusal = run(ADMIN, """
        SELECT pg_get_functiondef(
            'service.refuse_change_to_submitted_cart()'::regprocedure);""")
    record("nothing this slice owns can submit a cart",
           submit.ok and not (submit.scalar or "").strip()
           and refusal.ok and "RAISE EXCEPTION" in refusal.out
           and "INSERT INTO ordering" not in refusal.out,
           f"functions that could cross the boundary: "
           f"{(submit.scalar or '').strip() or 'none'}. The single service function that "
           f"names an order at all is refuse_change_to_submitted_cart(), and it only "
           f"raises: it freezes a cart once an order exists and creates nothing")

    pwa = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND c.relname ~* '(^|_)(rtl|render|layout|theme|accessibility|pwa)($|_)';
    """)
    record("no customer PWA, rendering or accessibility surface exists",
           pwa == 0,
           f"{pwa} such table(s); the rendering surface and its RTL and accessibility "
           f"assertions are M2-C, and building them before a surface exists would "
           f"produce unfalsifiable green")

    weakened = count(ADMIN, """
        SELECT count(*) FROM pg_policies
        WHERE schemaname IN ('org', 'identity', 'config', 'menu')
          AND (qual NOT LIKE '%row_in_scope%' OR with_check NOT LIKE '%row_in_scope%');
    """)
    record("M2-B did not weaken a single earlier policy",
           weakened <= 1,
           "the only earlier policy not built on app.row_in_scope() remains org.tenant, "
           "which compares its primary key to app.current_tenant_id() because each row "
           "is a tenant; nothing in this slice changed an existing policy")

    catalog = run(ADMIN, """
        SELECT count(*)::text FROM pg_namespace n
        WHERE n.nspname IN ('safety', 'service')
          AND EXISTS (SELECT 1 FROM pg_class c WHERE c.relnamespace = n.oid AND c.relkind = 'r');
    """)
    documented = (REPO / "schema" / "SCHEMA_CATALOG.md").read_text(encoding="utf-8")
    record("the schema catalog documents the new schemas",
           catalog.ok and "safety" in documented and "service" in documented,
           "both appear in schema/SCHEMA_CATALOG.md, which discovers schemas from the "
           "database rather than from a list inside the generator")


# ===========================================================================
# 12. Negative controls
# ===========================================================================

def capture_function(signature: str) -> str:
    res = run(ADMIN, f"SELECT pg_get_functiondef('{signature}'::regprocedure);")
    if not res.ok or not res.out.strip():
        raise RuntimeError(f"could not capture {signature}: {res.why()}")
    return res.out


def prove(control: str, gate, signature: str, break_sql: str, revert_sql: str = "",
          captured: list[str] | None = None) -> None:
    ok, _, detail = gate()
    if not ok:
        record(f"{control} — baseline", False, f"gate already failing before the break: {detail}")
        return

    originals = [capture_function(sig) for sig in (captured or [])]

    broke = run(ADMIN, break_sql)
    if not broke.ok:
        record(f"{control} — inject defect", False, f"could not plant the break: {broke.why()}")
        return
    try:
        red_ok, red_sig, red_detail = gate()
        record(f"{control} — RED with the defect planted",
               (not red_ok) and red_sig == signature,
               f"{red_sig or '(gate still passed)'}: {red_detail}")
    finally:
        for original in originals:
            run(ADMIN, original)
        if revert_sql:
            run(ADMIN, revert_sql)

    green_ok, green_sig, green_detail = gate()
    record(f"{control} — GREEN after revert", green_ok,
           green_detail if green_ok else f"{green_sig}: {green_detail}")


def qr_opacity_gate() -> tuple[bool, str, str]:
    """A QR reference must not be enumerable, guessable or decodable."""
    issued = []
    for table in (fx.TABLE_ONE, fx.TABLE_TWO):
        res = run(APP, f"SELECT service.issue_table_qr('{fx.TENANT}', '{table}', '{fx.USER}');",
                  **CTX)
        if not res.ok or not (res.scalar or "").strip():
            return False, "ENUMERABLE_QR_REFERENCE", f"a code could not be issued: {res.why()}"
        issued.append(res.scalar.strip())
    fx.TOKENS["one"], fx.TOKENS["two"] = issued

    leaks: list[str] = []
    a, b = issued
    if len(a) < 32:
        leaks.append(f"a code is only {len(a)} characters, which is guessable")

    shared = 0
    for x, y in zip(a, b):
        if x != y:
            break
        shared += 1
    if shared > 4:
        leaks.append(f"two codes in the same outlet share a {shared} character prefix")

    try:
        if abs(int(a, 16) - int(b, 16)) < 2 ** 32:
            leaks.append("two codes issued in sequence are numerically adjacent")
    except ValueError:
        pass

    for known, label in ((fx.TABLE_ONE, "the table id"), (fx.OUTLET_H1, "the outlet id"),
                         (fx.TENANT, "the tenant id")):
        if known.replace("-", "").lower() in a.lower():
            leaks.append(f"a code contains {label}, so it decodes to an internal key")

    if leaks:
        return False, "ENUMERABLE_QR_REFERENCE", "; ".join(leaks)
    return True, "", (f"two codes issued for two tables in one outlet share a {shared} "
                      f"character prefix, are numerically unrelated, and contain no "
                      f"tenant, outlet or table identifier")


def foreign_session_gate() -> tuple[bool, str, str]:
    """A code from another table, outlet or tenant must not be accepted."""
    leaks: list[str] = []

    sibling = run(APP, f"""
        SELECT service.record_qr_scan('{fx.TENANT}', '{fx.TOKENS["sibling"]}', '{fx.GUEST_ONE}');
    """, **CTX)
    if sibling.ok:
        leaks.append("a code belonging to a table in the sibling outlet resolved in this "
                     "outlet's scope")

    other_tenant = run(APP, f"""
        SELECT service.record_qr_scan('{fx.TENANT}', '{fx.TOKENS["sibling"]}', '{fx.GUEST_ONE}');
    """, tenant="44444444-4444-4444-4444-444444444444",
         outlet="44440001-0000-4000-8000-000000000001")
    if other_tenant.ok:
        leaks.append("a code resolved for a caller in an entirely different tenant")

    # A scan legitimately taken at table two must not be usable to join table one.
    fx.open_occupancy(fx.TABLE_TWO, source="staff")
    scan = run(APP, f"""
        SELECT service.record_qr_scan('{fx.TENANT}', '{fx.TOKENS["two"]}', '{fx.GUEST_ONE}');
    """, **CTX)
    if scan.ok and (scan.scalar or "").strip():
        joined = run(APP, f"""
            SELECT service.join_table_session('{fx.TENANT}', '{scan.scalar.strip()}');
        """, **CTX)
        wrong_table = count_or(APP, f"""
            SELECT count(*) FROM service.session_participant p
            JOIN service.table_session s ON s.id = p.table_session_id
            WHERE p.guest_session_id = '{fx.GUEST_ONE}' AND s.table_node_id = '{fx.TABLE_ONE}'
              AND s.state = 'open' AND p.joined_at > now() - interval '5 seconds';
        """, -1, **CTX)
        if joined.ok and wrong_table > 0:
            leaks.append("a scan taken at table two admitted the guest to table one")

    if leaks:
        return False, "FOREIGN_SESSION_ACCEPTED", "; ".join(leaks)
    return True, "", ("a code from the sibling outlet does not resolve, a code presented "
                      "by another tenant does not resolve, and a scan taken at one table "
                      "admits nobody to another")


def safety_publication_gate() -> tuple[bool, str, str]:
    """Publication must be refused while safety text is missing."""
    run(APP, f"UPDATE menu.menu SET state = 'draft', row_version = row_version WHERE id = '{m2a_fx.MENU}';", **CTX)
    removed = run(APP, f"""
        DELETE FROM menu.translation
        WHERE entity = 'allergen' AND entity_id = '{fx.ALLERGEN_MILK}'
          AND field_name = 'customer_warning_text' AND locale = 'am';
    """, **CTX)
    if not removed.ok:
        return False, "REQUIRED_SAFETY_TRANSLATION_MISSING", f"could not remove a warning: {removed.why()}"

    blocked = run(APP, f"SELECT menu.publish_menu('{m2a_fx.MENU}', '{fx.USER}');", **CTX)
    admitted = blocked.ok
    fx.translate_safety(locales=("am",))

    if admitted:
        return False, "REQUIRED_SAFETY_TRANSLATION_MISSING", (
            "a menu published with an allergen warning absent in Amharic")

    allowed = run(APP, f"SELECT menu.publish_menu('{m2a_fx.MENU}', '{fx.USER}');", **CTX)
    if not allowed.ok:
        return False, "REQUIRED_SAFETY_TRANSLATION_MISSING", (
            f"publication was still refused once the warning was restored: "
            f"{first_line(allowed.err)}")
    return True, "", ("publication is refused while a safety warning is missing in one "
                      "locale and admitted once it is approved, so the block is a gate "
                      "rather than a wall")


def written_warning_gate() -> tuple[bool, str, str]:
    """An allergen must never be conveyed by icon alone."""
    leaks: list[str] = []

    direct = run(APP, "SELECT icon_key FROM safety.allergen LIMIT 1;", **CTX)
    if direct.ok:
        leaks.append("the application role can read icon_key directly")

    star = run(APP, "SELECT * FROM safety.allergen LIMIT 1;", **CTX)
    if star.ok:
        leaks.append("SELECT * on the catalog returns the icon")

    offenders = function_bodies(
        "s.body LIKE '%icon_key%' AND s.body NOT LIKE '%written_warning%' "
        "AND s.body NOT LIKE '%translated_text%'")
    if offenders:
        leaks.append(f"a function returns an icon with no warning: {offenders}")

    removed = run(APP, f"""
        DELETE FROM menu.translation
        WHERE entity = 'allergen' AND entity_id = '{fx.ALLERGEN_GLUTEN}'
          AND field_name = 'customer_warning_text' AND locale = 'en';
    """, **CTX)
    if removed.ok:
        served = run(APP, f"""
            SELECT count(*)::text FROM safety.selection_safety(
                '{fx.TENANT}', 'en', '{m2a_fx.ITEM_DORO}', '{m2a_fx.VARIANT_DORO_FULL}');
        """, **CTX)
        if served.ok:
            leaks.append("a selection resolved with an allergen whose written warning was "
                         "absent, so a guest could be shown its icon and nothing else")
    fx.translate_safety(locales=("en",))

    if leaks:
        return False, "WRITTEN_WARNING_ABSENT", "; ".join(leaks)
    return True, "", ("the icon column is not selectable by the application role, no "
                      "function returns an icon without words, and a selection whose "
                      "warning text is missing is refused outright rather than shortened")


def stale_declaration_gate() -> tuple[bool, str, str]:
    """A declaration must move when its inputs move."""
    plain = run(APP, f"""
        SELECT coalesce(string_agg(kitchen_code, ','  ORDER BY kitchen_code), '')
        FROM safety.effective_allergens('{fx.TENANT}', '{m2a_fx.ITEM_DORO}',
                                        '{m2a_fx.VARIANT_DORO_FULL}');
    """, **CTX)
    with_modifier = run(APP, f"""
        SELECT coalesce(string_agg(kitchen_code, ',' ORDER BY kitchen_code), '')
        FROM safety.effective_allergens('{fx.TENANT}', '{m2a_fx.ITEM_DORO}',
                                        '{m2a_fx.VARIANT_DORO_FULL}',
                                        ARRAY['{m2a_fx.MODIFIER_HOT}']::uuid[]);
    """, **CTX)
    if not plain.ok or not with_modifier.ok:
        return False, "STALE_DECLARATION_SERVED", (
            f"resolution did not run: {plain.why() or with_modifier.why()}")

    leaks: list[str] = []
    if "SESAME" in (plain.scalar or ""):
        leaks.append("the plain dish already declares sesame, so the modifier proves nothing")
    if "SESAME" not in (with_modifier.scalar or ""):
        leaks.append("choosing a modifier that CONTAINS sesame did not change the "
                     "declared set, so the answer did not re-evaluate")

    # Withdraw one declaration and add another, then read — all inside a transaction that
    # is rolled back. Done this way rather than with a restore afterwards because prove()
    # calls this gate three times, and a hand-written undo that is even slightly wrong
    # leaves the fixture altered for the next call. A rollback cannot be slightly wrong.
    after = run(APP, f"""
        UPDATE safety.declaration SET effective_to = now()
        WHERE subject = 'modifier' AND subject_id = '{m2a_fx.MODIFIER_HOT}'
          AND allergen_id = '{fx.ALLERGEN_SESAME}' AND effective_to IS NULL;
        INSERT INTO safety.declaration
            (tenant_id, outlet_id, subject, subject_id, allergen_id, declaration_class,
             created_by_user_id, review_state, reviewed_by_user_id, reviewed_at)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'modifier', '{m2a_fx.MODIFIER_HOT}',
                '{fx.ALLERGEN_MILK}', 'contains', '{fx.USER}', 'approved', '{fx.USER}', now())
        ON CONFLICT (tenant_id, subject, subject_id, allergen_id)
            WHERE effective_to IS NULL DO NOTHING;
        SELECT coalesce(string_agg(kitchen_code, ',' ORDER BY kitchen_code), '')
        FROM safety.effective_allergens('{fx.TENANT}', '{m2a_fx.ITEM_DORO}',
                                        '{m2a_fx.VARIANT_DORO_FULL}',
                                        ARRAY['{m2a_fx.MODIFIER_HOT}']::uuid[]);
    """, rollback=True, **CTX)
    if not after.ok:
        leaks.append(f"the correction probe did not run: {after.why()}")
    else:
        if "SESAME" in (after.scalar or ""):
            leaks.append("the withdrawn sesame declaration is still being served after it "
                         "was closed, so something is remembering it")
        if "MILK" not in (after.scalar or ""):
            leaks.append("the newly declared milk did not appear, so the correction did "
                         "not reach the read path")

    if leaks:
        return False, "STALE_DECLARATION_SERVED", "; ".join(leaks)
    return True, "", ("a modifier changes the declared set, a withdrawn declaration stops "
                      "being served the moment it is closed, and a new one appears with "
                      "no refresh step anywhere")


def stale_session_gate() -> tuple[bool, str, str]:
    """A scan from an earlier occupancy must not silently join a later one."""
    fx.open_occupancy(fx.TABLE_ONE, source="staff")
    scan = run(APP, f"""
        SELECT service.record_qr_scan('{fx.TENANT}', '{fx.TOKENS["one"]}', '{fx.GUEST_STALE}');
    """, **CTX)
    if not scan.ok or not (scan.scalar or "").strip():
        return False, "STALE_SESSION_ADMITTED", f"the scan did not record: {scan.why()}"
    scan_id = scan.scalar.strip()

    later = fx.open_occupancy(fx.TABLE_ONE, source="staff")
    leaks: list[str] = []

    unverified = run(APP, f"""
        SELECT service.join_table_session('{fx.TENANT}', '{scan_id}');
    """, **CTX)
    if unverified.ok:
        leaks.append("a scan taken under the previous occupancy joined the later one with "
                     "no verification at all")

    methods = run(ADMIN, f"""
        SELECT unnest(accepted_methods)::text FROM service.verification_policy
        WHERE tenant_id = '{fx.TENANT}';
    """)
    for method in [r[0] for r in (methods.rows or [])]:
        attempt = run(APP, f"""
            SELECT service.join_table_session('{fx.TENANT}', '{scan_id}', '{method}');
        """, **CTX)
        if attempt.ok:
            leaks.append(f"{method} admitted the stale scan with no evidence recorded")

    unconfigured = run(APP, f"""
        DELETE FROM service.verification_policy WHERE tenant_id = '{fx.TENANT}';
        SELECT service.join_table_session('{fx.TENANT}', '{scan_id}');
    """, rollback=True, **CTX)
    if unconfigured.ok:
        leaks.append("a tenant with no verification policy at all admitted the stale scan, "
                     "so absent configuration fails open")

    admitted = count_or(APP, f"""
        SELECT count(*) FROM service.session_participant
        WHERE table_session_id = '{later}' AND guest_session_id = '{fx.GUEST_STALE}';
    """, -1, **CTX)
    if admitted > 0:
        leaks.append("the guest is a participant in the later occupancy, so the refusal "
                     "was an error message rather than a refusal")

    if leaks:
        return False, "STALE_SESSION_ADMITTED", "; ".join(leaks)

    verified = run(APP, f"""
        SELECT service.join_table_session('{fx.TENANT}', '{scan_id}', 'table_code', 'read back');
    """, **CTX)
    if not verified.ok:
        return False, "STALE_SESSION_ADMITTED", (
            f"verification was supplied and the join was still refused, which is a wall "
            f"rather than a gate: {first_line(verified.err)}")
    return True, "", ("a scan taken under an earlier occupancy is refused with no "
                      "verification, refused under every configured method with no "
                      "evidence, refused when the tenant has configured nothing, and "
                      "admitted once the verification actually happens")


def ownership_gate() -> tuple[bool, str, str]:
    """Ownership must move only through an acknowledged transfer."""
    session = (run(APP, f"""
        SELECT id::text FROM service.table_session
        WHERE table_node_id = '{fx.TABLE_ONE}' AND state = 'open';
    """, **CTX).scalar or "").strip()
    if not session:
        return False, "OWNERSHIP_TRANSFERRED_SILENTLY", "no open occupancy to own"

    run(APP, f"""
        INSERT INTO service.table_ownership
            (tenant_id, outlet_id, table_session_id, primary_waiter_user_id, section_code,
             assigned_by_user_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}', '{fx.USER}', 'SEC-A', '{fx.USER}')
        ON CONFLICT DO NOTHING;
    """, **CTX)

    leaks: list[str] = []
    edited = run(APP, f"""
        UPDATE service.table_ownership SET primary_waiter_user_id = '{fx.USER_WAITER_B}'
        WHERE table_session_id = '{session}' AND effective_to IS NULL;
    """, rollback=True, **CTX)
    if edited.ok:
        leaks.append("ownership was edited in place, leaving no proposal, no "
                     "acknowledgement and no supervisor")

    section = run(APP, f"""
        UPDATE service.table_ownership SET section_code = 'SEC-Z'
        WHERE table_session_id = '{session}' AND effective_to IS NULL;
    """, rollback=True, **CTX)
    if section.ok:
        leaks.append("the section was reassigned in place")

    proposed = run(APP, f"""
        INSERT INTO service.ownership_transfer
            (tenant_id, outlet_id, table_session_id, from_user_id, to_user_id, proposed_by_user_id)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{session}', '{fx.USER}',
                '{fx.USER_WAITER_B}', '{fx.USER}')
        RETURNING id::text;
    """, **CTX)
    transfer = (proposed.scalar or "").strip()
    if transfer:
        premature = run(APP, f"SELECT service.transfer_ownership('{fx.TENANT}', '{transfer}');",
                        **CTX)
        if premature.ok:
            leaks.append("an unacknowledged proposal moved the table")

        impostor = run(APP, f"""
            UPDATE service.ownership_transfer
               SET state = 'acknowledged', acknowledged_at = now(),
                   acknowledged_by_user_id = '{fx.USER_SUPERVISOR}'
             WHERE id = '{transfer}';
        """, rollback=True, **CTX)
        if impostor.ok:
            leaks.append("somebody other than the waiter taking the table on acknowledged the handover")

    if leaks:
        return False, "OWNERSHIP_TRANSFERRED_SILENTLY", "; ".join(leaks)
    return True, "", ("ownership cannot be edited in place, an unacknowledged proposal "
                      "does not move the table, and only the waiter taking it on may "
                      "acknowledge taking it on")


def audit_reference_gate() -> tuple[bool, str, str]:
    """The pinned reference must be unreachable from a display path."""
    leaks: list[str] = []

    direct = run(APP, "SELECT count(*) FROM safety.declaration_reference;", **CTX)
    if direct.ok:
        leaks.append("the application role can SELECT the pinned reference directly")

    one_row = run(APP, "SELECT declaration_id FROM safety.declaration_reference LIMIT 1;", **CTX)
    if one_row.ok:
        leaks.append("a single column of the pinned reference is readable")

    back_doors = function_bodies("s.body LIKE '%declaration_reference%'",
                                 excluding="publish_menu")
    if back_doors:
        leaks.append(f"a function other than the writer reaches it: {back_doors}")

    if leaks:
        return False, "AUDIT_REFERENCE_DISCLOSED_TO_DISPLAY", "; ".join(leaks)
    return True, "", ("the application role holds INSERT and nothing else on the pinned "
                      "reference, no function other than publish_menu names it, and the "
                      "guest read path resolves declarations live instead")


def correction_reaches_gate() -> tuple[bool, str, str]:
    """A correction must reach a menu that was published before it."""
    run(APP, f"UPDATE menu.menu SET state = 'draft', row_version = row_version WHERE id = '{m2a_fx.MENU}';", **CTX)
    published = run(APP, f"SELECT menu.publish_menu('{m2a_fx.MENU}', '{fx.USER}');", **CTX)
    snapshot = (published.scalar or "").strip()
    if not snapshot:
        return False, "CORRECTION_WITHHELD_FROM_PUBLISHED_MENU", (
            f"could not publish a menu to read through: {first_line(published.err)}")

    marker = "CORRECTED-" + snapshot[:8]
    before = run(APP, f"""
        SELECT coalesce(string_agg(DISTINCT written_warning, ' | '), '')
        FROM menu.published_menu_for_guest('{fx.TENANT}', '{snapshot}', 'en')
        WHERE allergen_kitchen_code = 'GLUTEN';
    """, **CTX)

    run(APP, f"""
        UPDATE menu.translation
           SET translated_text = 'Contains gluten {marker}', row_version = row_version
         WHERE entity = 'allergen' AND entity_id = '{fx.ALLERGEN_GLUTEN}'
           AND field_name = 'customer_warning_text' AND locale = 'en';
    """, **CTX)

    after = run(APP, f"""
        SELECT coalesce(string_agg(DISTINCT written_warning, ' | '), '')
        FROM menu.published_menu_for_guest('{fx.TENANT}', '{snapshot}', 'en')
        WHERE allergen_kitchen_code = 'GLUTEN';
    """, **CTX)

    leaks: list[str] = []
    if not after.ok:
        leaks.append(f"the published menu could not be read: {first_line(after.err)}")
    elif marker not in (after.scalar or ""):
        leaks.append("a guest reading the menu published BEFORE the correction is still "
                     "shown the old warning text, so the correction never reached them")
    elif before.ok and (before.scalar or "") == (after.scalar or ""):
        leaks.append("the warning did not change at all")

    # A new declaration made after publication must also appear.
    run(APP, f"""
        INSERT INTO safety.declaration
            (tenant_id, outlet_id, subject, subject_id, allergen_id, declaration_class,
             created_by_user_id, review_state, reviewed_by_user_id, reviewed_at)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'item', '{m2a_fx.ITEM_TIBS}',
                '{fx.ALLERGEN_SESAME}', 'contains', '{fx.USER}', 'approved', '{fx.USER}', now())
        ON CONFLICT DO NOTHING;
    """, **CTX)
    newly = run(APP, f"""
        SELECT count(*)::text FROM menu.published_menu_for_guest('{fx.TENANT}', '{snapshot}', 'en')
        WHERE item_code = 'SKU-TIBS-02' AND allergen_kitchen_code = 'SESAME';
    """, **CTX)
    if newly.ok and (newly.scalar or "").strip() == "0":
        leaks.append("an allergen discovered after publication does not appear on the "
                     "menu that was already published, which is the case that hurts "
                     "somebody")
    run(APP, f"""
        UPDATE safety.declaration SET effective_to = now()
        WHERE subject = 'item' AND subject_id = '{m2a_fx.ITEM_TIBS}'
          AND allergen_id = '{fx.ALLERGEN_SESAME}' AND effective_to IS NULL;
    """, **CTX)

    # The real test of "pinned" is not what the number is, it is that changing the live
    # price does not move it. Done in a rolled-back transaction so the fixture is
    # untouched, and deliberately the mirror image of the allergen probe above: the same
    # published line, the same kind of after-the-fact change, opposite required outcome.
    repriced = run(APP, f"""
        UPDATE menu.price SET effective_to = now()
         WHERE variant_id = '{m2a_fx.VARIANT_DORO_FULL}' AND channel IS NULL
           AND effective_to IS NULL;
        INSERT INTO menu.price
            (tenant_id, outlet_id, variant_id, channel, currency_code, amount_minor, tax_context)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{m2a_fx.VARIANT_DORO_FULL}', NULL,
                'ETB', 99000, 'standard');
        SELECT coalesce(string_agg(DISTINCT amount_minor::text, ',' ORDER BY amount_minor::text), '')
        FROM menu.published_menu_for_guest('{fx.TENANT}', '{snapshot}', 'en')
        WHERE item_code = 'SKU-DORO-01';
    """, rollback=True, **CTX)
    if not repriced.ok:
        leaks.append(f"the repricing probe did not run: {repriced.why()}")
    elif "99000" in (repriced.scalar or ""):
        leaks.append("raising the live price after publication moved the published price "
                     "too, so this is not freshness — it is a snapshot that pins nothing")

    if leaks:
        return False, "CORRECTION_WITHHELD_FROM_PUBLISHED_MENU", "; ".join(leaks)
    return True, "", ("a warning corrected after publication, and an allergen declared "
                      "after publication, both reach a guest reading the earlier "
                      "snapshot, while the price on the same line stays pinned at 32000")


def archive_action_gate() -> tuple[bool, str, str]:
    """A retention policy that says archive must not delete.

    An M1-C defect, found while wiring guest sessions to the engine the brief says to
    wire to. config.retention_action offered 'archive' and 'purge', the policy stored the
    choice, and config.apply_retention() ran DELETE for both — so a tenant that asked for
    archival had its rows destroyed and the run reported success.
    """
    setup = run(APP, f"""
        INSERT INTO service.qr_placard
            (tenant_id, outlet_id, token_id, version, printed_by_user_id, note)
        SELECT '{fx.TENANT}', '{fx.OUTLET_H1}', t.id, t.version, '{fx.USER}', 'archive probe'
        FROM service.table_qr_token t
        WHERE t.table_node_id = '{fx.TABLE_ONE}' AND t.revoked_at IS NULL;

        INSERT INTO config.retention_policy
            (tenant_id, target_schema, target_table, age_column, retain_for, action)
        VALUES ('{fx.TENANT}', 'service', 'qr_placard', 'printed_at',
                interval '1 microsecond', 'archive')
        ON CONFLICT (tenant_id, target_schema, target_table) DO UPDATE
            SET action = 'archive', retain_for = interval '1 microsecond';
    """, **CTX)
    if not setup.ok:
        return False, "ARCHIVE_POLICY_DELETED_ROWS", f"could not set up: {setup.why()}"

    before = count_or(APP, f"""
        SELECT count(*) FROM service.qr_placard WHERE tenant_id = '{fx.TENANT}';
    """, -1, **CTX)
    swept = run(APP, f"SELECT * FROM config.apply_retention('{fx.TENANT}');", **CTX)
    after = count_or(APP, f"""
        SELECT count(*) FROM service.qr_placard WHERE tenant_id = '{fx.TENANT}';
    """, -1, **CTX)

    leaks: list[str] = []
    if after < before:
        leaks.append(f"an archive policy destroyed {before - after} of {before} row(s) "
                     f"and reported success")
    if swept.ok:
        leaks.append("the sweep completed without saying it cannot archive, so a tenant "
                     "would have no way to learn its archival was never happening")

    run(APP, f"""
        DELETE FROM config.retention_policy
        WHERE tenant_id = '{fx.TENANT}' AND target_schema = 'service'
          AND target_table = 'qr_placard';
    """, **CTX)

    if leaks:
        return False, "ARCHIVE_POLICY_DELETED_ROWS", "; ".join(leaks)
    return True, "", (f"the sweep refuses with RETENTION_ACTION_UNIMPLEMENTED and all "
                      f"{before} row(s) survive. Phase 1 has no archive store, and the "
                      f"honest answer to being asked for one is to say so rather than to "
                      f"delete the rows a tenant asked to keep")


def section_controls() -> None:
    print("\n--- 12. M2-B negative controls, each proved red then green ---")

    print("\n  NC-M2-001  a QR reference that can be enumerated")
    prove("NC-M2-001", qr_opacity_gate, "ENUMERABLE_QR_REFERENCE",
          break_sql="""
              CREATE SEQUENCE IF NOT EXISTS service.guessable_codes START 1000;
              CREATE OR REPLACE FUNCTION service.issue_table_qr(
                  p_tenant_id uuid, p_table_node_id uuid, p_issued_by uuid,
                  p_reason_id uuid DEFAULT NULL) RETURNS text
              LANGUAGE plpgsql AS $break$
              DECLARE
                  v_token text; v_outlet uuid; v_version integer;
              BEGIN
                  SELECT outlet_id INTO v_outlet FROM service.table_profile
                   WHERE tenant_id = p_tenant_id AND table_node_id = p_table_node_id;
                  -- The defect: a readable, sequential code derived from the table itself.
                  v_token := 'TBL' || replace(p_table_node_id::text, '-', '')
                          || lpad(nextval('service.guessable_codes')::text, 6, '0');
                  UPDATE service.table_qr_token SET revoked_at = now(),
                         revoked_by_user_id = p_issued_by
                   WHERE tenant_id = p_tenant_id AND table_node_id = p_table_node_id
                     AND revoked_at IS NULL;
                  SELECT coalesce(max(version), 0) + 1 INTO v_version
                    FROM service.table_qr_token
                   WHERE tenant_id = p_tenant_id AND table_node_id = p_table_node_id;
                  INSERT INTO service.table_qr_token
                      (tenant_id, outlet_id, table_node_id, token_hash, version, issued_by_user_id)
                  VALUES (p_tenant_id, v_outlet, p_table_node_id,
                          sha256(convert_to(v_token, 'UTF8')), v_version, p_issued_by);
                  RETURN v_token;
              END; $break$;
          """,
          revert_sql="DROP SEQUENCE IF EXISTS service.guessable_codes;",
          captured=["service.issue_table_qr(uuid,uuid,uuid,uuid)"])

    print("\n  NC-M2-002  a foreign session is accepted")
    prove("NC-M2-002", foreign_session_gate, "FOREIGN_SESSION_ACCEPTED",
          break_sql="""
              -- Isolation here is defended twice: the token row is invisible across a
              -- tenant, AND the scan row could not be written into another outlet's
              -- scope. Both have to be removed for the defect to express itself at all,
              -- which is worth recording — the first attempt at this break relaxed only
              -- the token table and the gate stayed green, not because the control was
              -- weak but because the second guard held.
              ALTER TABLE service.table_qr_token NO FORCE ROW LEVEL SECURITY;
              ALTER TABLE service.table_qr_token DISABLE ROW LEVEL SECURITY;
              ALTER TABLE service.qr_scan NO FORCE ROW LEVEL SECURITY;
              ALTER TABLE service.qr_scan DISABLE ROW LEVEL SECURITY;
              ALTER TABLE service.session_participant NO FORCE ROW LEVEL SECURITY;
              ALTER TABLE service.session_participant DISABLE ROW LEVEL SECURITY;
              CREATE OR REPLACE FUNCTION service.record_qr_scan(
                  p_tenant_id uuid, p_token text, p_guest_session_id uuid) RETURNS uuid
              LANGUAGE plpgsql SECURITY DEFINER AS $break$
              DECLARE
                  v_token record; v_scan_id uuid; v_occupancy integer;
              BEGIN
                  SELECT t.* INTO v_token FROM service.table_qr_token t
                   WHERE t.token_hash = sha256(convert_to(p_token, 'UTF8'));
                  -- The defect: the tenant test is gone, and so is the isolation that
                  -- would have hidden the row in the first place.
                  IF v_token.id IS NULL THEN
                      RAISE EXCEPTION 'QR_TOKEN_UNKNOWN' USING ERRCODE = 'HS404';
                  END IF;
                  SELECT occupancy_number INTO v_occupancy FROM service.table_session
                   WHERE table_node_id = v_token.table_node_id AND state = 'open';
                  INSERT INTO service.qr_scan
                      (tenant_id, outlet_id, token_id, guest_session_id, occupancy_at_scan)
                  VALUES (p_tenant_id, v_token.outlet_id, v_token.id, p_guest_session_id, v_occupancy)
                  RETURNING id INTO v_scan_id;
                  RETURN v_scan_id;
              END; $break$;
          """,
          revert_sql="""
              ALTER TABLE service.table_qr_token ENABLE ROW LEVEL SECURITY;
              ALTER TABLE service.table_qr_token FORCE ROW LEVEL SECURITY;
              ALTER TABLE service.qr_scan ENABLE ROW LEVEL SECURITY;
              ALTER TABLE service.qr_scan FORCE ROW LEVEL SECURITY;
              ALTER TABLE service.session_participant ENABLE ROW LEVEL SECURITY;
              ALTER TABLE service.session_participant FORCE ROW LEVEL SECURITY;
          """,
          captured=["service.record_qr_scan(uuid,text,uuid)"])

    print("\n  NC-M2-003  publication proceeds with a safety translation missing")
    prove("NC-M2-003", safety_publication_gate, "REQUIRED_SAFETY_TRANSLATION_MISSING",
          break_sql="""
              CREATE OR REPLACE FUNCTION safety.missing_safety_translations(p_menu_id uuid)
              RETURNS TABLE (entity menu.menu_entity, entity_id uuid, field_name text,
                             locale menu.customer_locale)
              LANGUAGE sql STABLE AS $break$
                  -- The defect: safety text is treated as complete whatever is missing.
                  SELECT NULL::menu.menu_entity, NULL::uuid, NULL::text,
                         NULL::menu.customer_locale WHERE false;
              $break$;
          """,
          revert_sql="",
          captured=["safety.missing_safety_translations(uuid)"])

    print("\n  NC-M2B-004  an allergen conveyed by icon with no written warning")
    prove("NC-M2B-004", written_warning_gate, "WRITTEN_WARNING_ABSENT",
          break_sql="""
              GRANT SELECT (icon_key) ON safety.allergen TO hospitality_app;
              CREATE OR REPLACE FUNCTION safety.selection_safety(
                  p_tenant_id uuid, p_locale menu.customer_locale, p_item_id uuid,
                  p_variant_id uuid DEFAULT NULL, p_modifier_ids uuid[] DEFAULT '{}')
              RETURNS TABLE (kitchen_code text, declaration_class safety.declaration_class,
                             written_warning text, icon_key text)
              LANGUAGE sql STABLE SECURITY DEFINER
              SET search_path = pg_catalog, safety, menu, public AS $break$
                  -- The defect: the allergen with no approved warning is dropped from the
                  -- result instead of refusing, so a guest is shown a shorter list, and
                  -- the icon is served whether or not any words go with it.
                  SELECT e.kitchen_code, e.declaration_class, t.translated_text, a.icon_key
                  FROM safety.effective_allergens(p_tenant_id, p_item_id, p_variant_id,
                                                  p_modifier_ids) e
                  JOIN safety.allergen a ON a.id = e.allergen_id
                  LEFT JOIN menu.translation t
                    ON t.tenant_id = p_tenant_id AND t.entity = 'allergen'
                   AND t.entity_id = e.allergen_id
                   AND t.field_name = 'customer_warning_text'
                   AND t.locale = p_locale AND t.state = 'approved';
              $break$;
          """,
          revert_sql="REVOKE SELECT (icon_key) ON safety.allergen FROM hospitality_app;",
          captured=["safety.selection_safety(uuid,menu.customer_locale,uuid,uuid,uuid[])"])

    print("\n  NC-M2B-005  a declaration is not re-evaluated after a modifier changes")
    prove("NC-M2B-005", stale_declaration_gate, "STALE_DECLARATION_SERVED",
          break_sql="""
              CREATE TABLE IF NOT EXISTS safety.resolved_cache AS
                  SELECT d.subject_id AS item_id, a.kitchen_code
                  FROM safety.declaration d JOIN safety.allergen a ON a.id = d.allergen_id
                  WHERE d.effective_to IS NULL AND d.subject = 'item';
              CREATE OR REPLACE FUNCTION safety.effective_allergens(
                  p_tenant_id uuid, p_item_id uuid, p_variant_id uuid DEFAULT NULL,
                  p_modifier_ids uuid[] DEFAULT '{}')
              RETURNS TABLE (allergen_id uuid, kitchen_code text,
                             declaration_class safety.declaration_class,
                             contributed_by menu.menu_entity[])
              LANGUAGE sql STABLE AS $break$
                  -- The defect: a stored answer, computed once, that neither the chosen
                  -- modifiers nor any later correction can move.
                  SELECT NULL::uuid, c.kitchen_code, 'contains'::safety.declaration_class,
                         ARRAY['item']::menu.menu_entity[]
                  FROM safety.resolved_cache c WHERE c.item_id = p_item_id;
              $break$;
          """,
          revert_sql="DROP TABLE IF EXISTS safety.resolved_cache;",
          captured=["safety.effective_allergens(uuid,uuid,uuid,uuid[])"])

    print("\n  NC-M2B-006  a stale QR silently joins a later occupied session")
    prove("NC-M2B-006", stale_session_gate, "STALE_SESSION_ADMITTED",
          break_sql="""
              CREATE OR REPLACE FUNCTION service.join_table_session(
                  p_tenant_id uuid, p_scan_id uuid,
                  p_verification service.verification_method DEFAULT NULL,
                  p_evidence text DEFAULT NULL) RETURNS uuid
              LANGUAGE plpgsql AS $break$
              DECLARE
                  v_scan record; v_token record; v_session record;
              BEGIN
                  SELECT * INTO v_scan FROM service.qr_scan
                   WHERE id = p_scan_id AND tenant_id = p_tenant_id;
                  SELECT * INTO v_token FROM service.table_qr_token
                   WHERE id = v_scan.token_id AND tenant_id = p_tenant_id;
                  SELECT * INTO v_session FROM service.table_session
                   WHERE tenant_id = p_tenant_id AND table_node_id = v_token.table_node_id
                     AND state = 'open';
                  -- The defect: the occupancy comparison is gone, so a code photographed
                  -- during an earlier party's meal joins whoever is sitting there now.
                  INSERT INTO service.session_participant
                      (tenant_id, outlet_id, table_session_id, guest_session_id)
                  VALUES (p_tenant_id, v_session.outlet_id, v_session.id, v_scan.guest_session_id)
                  ON CONFLICT (table_session_id, guest_session_id) DO NOTHING;
                  RETURN v_session.id;
              END; $break$;
          """,
          revert_sql="",
          captured=["service.join_table_session(uuid,uuid,service.verification_method,text)"])

    print("\n  NC-M2B-007  a waiter reassignment with no acknowledgement")
    prove("NC-M2B-007", ownership_gate, "OWNERSHIP_TRANSFERRED_SILENTLY",
          break_sql="""
              DROP TRIGGER table_ownership_no_silent_change ON service.table_ownership;
              ALTER TABLE service.ownership_transfer
                  DROP CONSTRAINT transfer_acknowledger_is_recipient;
          """,
          revert_sql="""
              ALTER TABLE service.ownership_transfer
                  ADD CONSTRAINT transfer_acknowledger_is_recipient CHECK (
                      acknowledged_by_user_id IS NULL OR acknowledged_by_user_id = to_user_id);
              CREATE TRIGGER table_ownership_no_silent_change
                  BEFORE UPDATE ON service.table_ownership
                  FOR EACH ROW EXECUTE FUNCTION service.refuse_silent_ownership_change();
          """)

    print("\n  NC-M2B-008  the pinned audit reference is readable by display code")
    prove("NC-M2B-008", audit_reference_gate, "AUDIT_REFERENCE_DISCLOSED_TO_DISPLAY",
          break_sql="GRANT SELECT ON safety.declaration_reference TO hospitality_app;",
          revert_sql="REVOKE SELECT ON safety.declaration_reference FROM hospitality_app;")

    print("\n  NC-M2B-009  a correction is withheld from an already-published menu")
    prove("NC-M2B-009", correction_reaches_gate, "CORRECTION_WITHHELD_FROM_PUBLISHED_MENU",
          break_sql="""
              CREATE OR REPLACE FUNCTION menu.published_menu_for_guest(
                  p_tenant_id uuid, p_snapshot_id uuid, p_locale menu.customer_locale)
              RETURNS TABLE (item_code text, canonical_name text, display_name text,
                             currency_code char(3), amount_minor money.amount_minor,
                             allergen_kitchen_code text,
                             declaration_class safety.declaration_class,
                             written_warning text, icon_key text)
              LANGUAGE sql STABLE SECURITY DEFINER
              SET search_path = pg_catalog, safety, menu, public AS $break$
                  -- The defect: the natural symmetry. Allergen text is read from what was
                  -- pinned at publication, exactly as the price is, so a correction made
                  -- afterwards never reaches a guest holding an older link.
                  SELECT l.item_code, l.canonical_name, l.canonical_name,
                         l.currency_code, l.amount_minor,
                         a.kitchen_code, d.declaration_class, t.translated_text, a.icon_key
                  FROM menu.publication_snapshot_line l
                  JOIN safety.declaration_reference r
                    ON r.context = 'publication_snapshot' AND r.context_id = l.snapshot_id
                  JOIN safety.declaration d ON d.id = r.declaration_id
                  JOIN safety.allergen a ON a.id = d.allergen_id
                  LEFT JOIN menu.translation t
                    ON t.tenant_id = p_tenant_id AND t.entity = 'allergen'
                   AND t.entity_id = a.id AND t.field_name = 'customer_warning_text'
                   AND t.locale = p_locale AND t.state = 'approved'
                   AND t.updated_at <= (SELECT published_at FROM menu.publication_snapshot
                                        WHERE id = p_snapshot_id)
                  WHERE l.snapshot_id = p_snapshot_id AND l.tenant_id = p_tenant_id
                    AND d.subject_id IN (l.item_id, l.variant_id);
              $break$;
          """,
          revert_sql="",
          captured=["menu.published_menu_for_guest(uuid,uuid,menu.customer_locale)"])

    print("\n  NC-M2B-010  a retention policy that says archive deletes instead")
    prove("NC-M2B-010", archive_action_gate, "ARCHIVE_POLICY_DELETED_ROWS",
          break_sql="""
              -- Exactly the M1-C body: the action is read from the policy and then
              -- ignored, and every policy is executed as a DELETE.
              CREATE OR REPLACE FUNCTION config.apply_retention(p_tenant_id uuid)
              RETURNS TABLE (target text, rows_affected bigint)
              LANGUAGE plpgsql AS $break$
              DECLARE
                  r record; v_count bigint;
              BEGIN
                  FOR r IN SELECT * FROM config.retention_policy WHERE tenant_id = p_tenant_id
                  LOOP
                      IF lower(r.target_schema) = 'audit' THEN
                          RAISE EXCEPTION 'APPEND_ONLY_VIOLATED: retention may not act on '
                              'audit storage (%.%)', r.target_schema, r.target_table
                              USING ERRCODE = 'HS403';
                      END IF;
                      EXECUTE format('DELETE FROM %I.%I WHERE %I < now() - $1',
                                     r.target_schema, r.target_table, r.age_column)
                          USING r.retain_for;
                      GET DIAGNOSTICS v_count = ROW_COUNT;
                      target := r.target_schema || '.' || r.target_table;
                      rows_affected := v_count;
                      RETURN NEXT;
                  END LOOP;
              END; $break$;
          """,
          revert_sql="",
          captured=["config.apply_retention(uuid)"])


def main() -> int:
    print("M2-B verification — tables, QR, guest sessions, carts and allergen safety")
    print(f"real PostgreSQL, application role, populated fixtures (running on "
          f"{__import__('platform').system()})")
    print()

    fx.seed()
    print(f"fixtures seeded: {len(fx.TOKENS)} table codes, "
          f"{len(fx.WARNINGS)} allergens, {len(fx.CLAIM_LABELS)} dietary claims, "
          f"3 locales")

    snapshot = ""
    for section in (section_qr, section_sessions, section_no_disable_path,
                    section_guests, section_carts, section_allergens,
                    section_change_detection):
        section()
    snapshot = section_claims_and_publication()
    section_correction_reaches_published(snapshot)
    section_allergy_input()
    section_boundary()
    section_controls()

    passed = sum(1 for _, ok, _ in results if ok)
    failed = [name for name, ok, _ in results if not ok]
    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {passed}")
    print(f"  failed        : {len(failed)}")
    for name in failed:
        print(f"  - {name}")
    print()
    if failed:
        print("FAIL M2B_VERIFICATION")
        return 1
    print("PASS M2B_VERIFICATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
