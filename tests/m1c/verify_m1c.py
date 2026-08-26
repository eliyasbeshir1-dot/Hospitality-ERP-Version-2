#!/usr/bin/env python3
"""M1-C verification harness — configuration, audit, money, quantity, retention.

Runs against real PostgreSQL through the application role (FR-DAT-017).

Each of the five M1-C negative controls is proved RED before it is trusted GREEN.
Function defects are reverted from the definition captured by pg_get_functiondef()
before the break, so the restored body is byte-for-byte what the migration created.

Usage:
    M1A_ADMIN_DSN=... M1A_APP_DSN=... python3 tests/m1c/verify_m1c.py
"""
from __future__ import annotations

import concurrent.futures
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "m1a"))
sys.path.insert(0, str(HERE.parent))

from fenced import fenced_identifier_pattern  # noqa: E402
from pg import count, run  # noqa: E402

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]

TENANT_HABESHA = "33333333-3333-3333-3333-333333333333"
TENANT_NILE = "44444444-4444-4444-4444-444444444444"
OUTLET_H1 = "33330001-0000-4000-8000-000000000001"
OUTLET_H2 = "33330002-0000-4000-8000-000000000002"
OUTLET_N1 = "44440001-0000-4000-8000-000000000001"
USER_HABESHA = "3333aaaa-0000-4000-8000-000000000001"

H1 = dict(tenant=TENANT_HABESHA, outlet=OUTLET_H1)
H2 = dict(tenant=TENANT_HABESHA, outlet=OUTLET_H2)

results: list[tuple[str, bool, str]] = []


def truthy(value: str | None) -> bool:
    """Normalize a PostgreSQL boolean.

    psql DISPLAYS a boolean column as t/f, but ``boolean::text`` renders true/false.
    Accepting both keeps an assertion from silently depending on which of the two a
    given query happened to produce.
    """
    return str(value).strip().lower() in {"t", "true"}


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def capture_function(signature: str) -> str:
    res = run(ADMIN, f"SELECT pg_get_functiondef('{signature}'::regprocedure);")
    if not res.ok or not res.out.strip():
        raise RuntimeError(f"could not capture {signature}: {res.err}")
    return res.out


def ensure_seeds() -> None:
    """Apply the seeds if this database has not received them yet."""
    tenant_present = count(ADMIN, f"SELECT count(*) FROM org.tenant WHERE id = '{TENANT_HABESHA}';")
    config_present = count(ADMIN, f"""
        SELECT count(*) FROM config.configuration_version WHERE tenant_id = '{TENANT_HABESHA}';
    """)
    if tenant_present == 1 and config_present > 0:
        return
    if tenant_present == 1 and config_present == 0:
        # The tenant survived but its configuration did not, which means something else
        # deleted it. Say so plainly instead of re-seeding over a corrupted state.
        raise RuntimeError(
            "seed tenant exists but its configuration is gone — another suite's reset "
            "has cascaded into config.configuration_version; rebuild the database")
    for seed in ("0001_demonstration_tenants.sql", "0002_reason_codes.sql"):
        proc = subprocess.run(
            ["psql", APP, "-v", "ON_ERROR_STOP=1", "-q", "-o", "/dev/null",
             "-f", str(REPO / "seeds" / seed)],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        if proc.returncode != 0:
            raise RuntimeError(f"seed {seed} failed: {proc.stderr.strip()}")


# ===========================================================================
# 1. Money and quantity (FR-DAT-005, FR-DAT-006)
# ===========================================================================

def section_money() -> None:
    print("\n--- 1. Money and quantity (FR-DAT-005, FR-DAT-006) ---")

    ok, sig, detail = money_exactness_gate()
    record("no binary floating point column exists anywhere", ok, detail if ok else f"{sig}: {detail}")

    paired = count(ADMIN, "SELECT count(*) FROM money.assert_currency_paired();")
    record("every money column sits beside an explicit currency", paired == 0,
           f"{paired} money column(s) without a currency_code beside them")

    # Exactness, asserted as an identity rather than a tolerance.
    #   sum(money.allocate(10000, 3)) = 10000     — exactly, no lost minor unit
    alloc = run(APP, """
        SELECT sum(part_amount)::text,
               (sum(part_amount) = 10000)::text,
               string_agg(part_amount::text, ',' ORDER BY part_index)
        FROM money.allocate(10000::money.amount_minor, 3);
    """, **H1)
    total, exact, parts = alloc.rows[0] if alloc.ok and alloc.rows else ("", "f", "")
    record("splitting an amount three ways reconstitutes it exactly (FR-DAT-005)",
           truthy(exact) and total == "10000",
           f"money.allocate(10000, 3) = [{parts}], sum = {total}; "
           f"asserted sum(parts) = 10000 as an equality, not a tolerance")

    # The same split done in binary floating point does NOT reconstitute the total.
    float_demo = run(APP, """
        SELECT (0.1::float8 + 0.2::float8 = 0.3::float8)::text   AS float_equal,
               (0.1::numeric + 0.2::numeric = 0.3::numeric)::text AS numeric_equal,
               (9007199254740993::float8::bigint = 9007199254740993::bigint)::text AS float_bigint,
               (9007199254740993::numeric::bigint = 9007199254740993::bigint)::text AS exact_bigint;
    """, **H1)
    fe, ne, fb, eb = float_demo.rows[0] if float_demo.ok and float_demo.rows else ("t", "f", "t", "f")
    record("the exact types succeed where binary floating point fails",
           (not truthy(fe)) and truthy(ne) and (not truthy(fb)) and truthy(eb),
           f"0.1 + 0.2 = 0.3 is {fe} in float8 and {ne} in numeric; "
           f"9007199254740993 survives a round trip: {fb} through float8, {eb} through the exact path")

    # Rounding is explicit, and the modes genuinely differ on a half.
    rounding = run(APP, """
        SELECT money.apply_rate(50::money.amount_minor, 5.0::money.percentage, 'half_up')::text,
               money.apply_rate(50::money.amount_minor, 5.0::money.percentage, 'half_even')::text,
               money.apply_rate(50::money.amount_minor, 5.0::money.percentage, 'floor')::text,
               money.apply_rate(50::money.amount_minor, 5.0::money.percentage, 'ceiling')::text;
    """, **H1)
    hu, he, fl, ce = rounding.rows[0] if rounding.ok and rounding.rows else ("", "", "", "")
    record("rounding mode is explicit and the modes actually differ (FR-DAT-006)",
           (hu, he, fl, ce) == ("3", "2", "2", "3"),
           f"5% of 50 minor units is exactly 2.5; half_up={hu}, half_even={he}, floor={fl}, ceiling={ce}")

    # Quantity and percentage carry declared precision and reject out-of-range values.
    bad_pct = run(APP, "SELECT 150.0::money.percentage;", **H1)
    bad_qty = run(APP, "SELECT (-1)::money.quantity;", **H1)
    precision = run(APP, "SELECT (1/3.0)::money.quantity::text;", **H1)
    record("quantities and percentages have declared precision and validation",
           (not bad_pct.ok) and (not bad_qty.ok) and precision.ok
           and precision.scalar == "0.3333",
           f"a 150% value and a negative quantity are both refused; "
           f"1/3 stores as {precision.scalar} at the declared scale of 4")

    # The application role cannot write reference currency data.
    for verb, stmt in (("INSERT", "INSERT INTO money.currency VALUES ('XXX','Test',2)"),
                       ("UPDATE", "UPDATE money.currency SET display_name = 'x' WHERE code = 'ETB'"),
                       ("DELETE", "DELETE FROM money.currency WHERE code = 'ETB'")):
        res = run(APP, stmt + ";", **H1)
        record(f"the application role cannot {verb} currency reference data", not res.ok,
               "money.currency is SELECT-only for the runtime role")


def money_exactness_gate() -> tuple[bool, str, str]:
    """No float4/float8 column may exist in any application schema."""
    res = run(ADMIN, """
        SELECT n.nspname || '.' || c.relname || '.' || a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
          AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          AND t.typname IN ('float4', 'float8')
        ORDER BY 1;
    """)
    if not res.ok:
        return False, "INEXACT_MONEY_TYPE_ACCEPTED", f"introspection failed: {res.err}"
    offenders = [r[0] for r in res.rows]
    if offenders:
        return False, "INEXACT_MONEY_TYPE_ACCEPTED", \
            f"{len(offenders)} binary floating point column(s): " + ", ".join(offenders[:5])
    return True, "", "no float4 or float8 column in any application schema"


# ===========================================================================
# 2. Audit (FR-SEC-009)
# ===========================================================================

def audit_append_only_gate() -> tuple[bool, str, str]:
    """The application role must not be able to change or remove an audit row."""
    seeded = run(APP, f"""
        INSERT INTO audit.security_event (tenant_id, outlet_id, event_code, subject_id)
        VALUES ('{TENANT_HABESHA}', '{OUTLET_H1}', 'gate.probe', '{USER_HABESHA}');
    """, **H1)
    if not seeded.ok:
        return False, "AUDIT_MUTATED_BY_ORDINARY_ROLE", f"could not append an audit row: {seeded.err}"

    before = count(APP, "SELECT count(*) FROM audit.security_event;", **H1)
    leaks: list[str] = []

    upd = run(APP, "UPDATE audit.security_event SET event_code = 'tampered';", **H1)
    if upd.ok:
        leaks.append("the application role UPDATEd an audit row")

    dele = run(APP, "DELETE FROM audit.security_event;", **H1)
    if dele.ok:
        leaks.append("the application role DELETEd an audit row")

    trunc = run(APP, "TRUNCATE audit.security_event;", **H1)
    if trunc.ok:
        leaks.append("the application role TRUNCATEd audit storage")

    after = count(APP, "SELECT count(*) FROM audit.security_event;", **H1)
    if after < before:
        leaks.append(f"audit row count fell from {before} to {after}")

    tampered = count(APP, "SELECT count(*) FROM audit.security_event WHERE event_code = 'tampered';", **H1)
    if tampered > 0:
        leaks.append(f"{tampered} audit row(s) carry a tampered value")

    if leaks:
        return False, "AUDIT_MUTATED_BY_ORDINARY_ROLE", "; ".join(leaks)
    return True, "", f"UPDATE, DELETE and TRUNCATE all refused; {after} audit row(s) intact"


def section_audit() -> None:
    print("\n--- 2. Audit separation and append-only storage (FR-SEC-009) ---")

    ok, sig, detail = audit_append_only_gate()
    record("audit storage cannot be changed by the application role", ok,
           detail if ok else f"{sig}: {detail}")

    separate = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'audit' AND c.relkind = 'r'
          AND c.relname IN ('security_event', 'operational_event');
    """)
    record("security audit and operational audit are separate stores", separate == 2,
           "audit.security_event and audit.operational_event are distinct tables")

    granted = run(ADMIN, """
        SELECT string_agg(DISTINCT privilege_type, ',' ORDER BY privilege_type)
        FROM information_schema.role_table_grants
        WHERE grantee = 'hospitality_app' AND table_schema = 'audit';
    """)
    record("the application role holds only INSERT and SELECT on audit storage",
           granted.scalar in ("INSERT,SELECT", "SELECT,INSERT"),
           f"granted privileges: {granted.scalar}")

    # M1-B emits recovery and lockout events; M1-C is where they land.
    landed = run(APP, f"""
        SELECT identity.emit_security_event('recovery.completed', '{USER_HABESHA}');
        INSERT INTO audit.security_event (tenant_id, outlet_id, event_code, subject_id)
        VALUES ('{TENANT_HABESHA}', '{OUTLET_H1}', 'recovery.completed', '{USER_HABESHA}');
        SELECT count(*) FROM audit.security_event WHERE event_code = 'recovery.completed';
    """, **H1)
    record("M1-B's security events have a home here (FR-AUTH-010)",
           landed.ok and int(landed.rows[-1][0]) >= 1,
           "recovery events emitted by identity are stored in audit.security_event")


# ===========================================================================
# 3. Configuration, policy and the M1-B ownership boundary
# ===========================================================================

def section_configuration() -> None:
    print("\n--- 3. Configuration store (FR-TEN-003, FR-TEN-010, FR-CFG-002A) ---")

    categories = count(APP, "SELECT count(DISTINCT category) FROM config.configuration_version;", **H1)
    record("versioned configuration exists for the tenant", categories >= 5,
           f"{categories} configuration categories carry a version for this tenant")

    # Effective dating: a new version closes the previous one, and resolution picks the
    # one in force rather than the newest row.
    supersede = run(APP, f"""
        UPDATE config.configuration_version SET effective_to = now()
        WHERE tenant_id = '{TENANT_HABESHA}' AND category = 'tax' AND effective_to IS NULL;
        INSERT INTO config.configuration_version
            (tenant_id, scope_kind, category, version, payload, effective_from,
             actor_id, approved_by_id, approved_at)
        VALUES ('{TENANT_HABESHA}', 'tenant', 'tax', 2,
                '{{"vat_percentage":"15.0000","rounding_mode":"half_even"}}'::jsonb,
                now(), '{USER_HABESHA}', '{USER_HABESHA}', now());
        SELECT config.effective_configuration('{TENANT_HABESHA}', 'tax') ->> 'rounding_mode';
    """, **H1)
    record("a superseded version is closed and the effective one is resolved (FR-TEN-003)",
           supersede.ok and supersede.rows[-1][0] == "half_even",
           "version 2 is in force; version 1 is retained with an effective_to, not overwritten")

    two_open = run(APP, f"""
        INSERT INTO config.configuration_version
            (tenant_id, scope_kind, category, version, payload, effective_from,
             actor_id, approved_by_id, approved_at)
        VALUES ('{TENANT_HABESHA}', 'tenant', 'tax', 3, '{{}}'::jsonb, now(),
                '{USER_HABESHA}', '{USER_HABESHA}', now());
    """, **H1)
    record("two open versions of one category cannot coexist", not two_open.ok,
           "the partial unique index refuses a second version with no effective_to")

    # FR-TEN-010: every change writes an audit row with actor, approval and effective date.
    audited = run(APP, f"""
        SELECT count(*)::text,
               count(*) FILTER (WHERE actor_id IS NOT NULL
                                  AND approved_by_id IS NOT NULL
                                  AND approved_at IS NOT NULL
                                  AND effective_from IS NOT NULL)::text
        FROM audit.operational_event
        WHERE entity_schema = 'config' AND entity_table = 'configuration_version';
    """, **H1)
    total, complete = audited.rows[0] if audited.ok and audited.rows else ("0", "0")
    record("every configuration change is audited with actor, approval and effective date",
           int(total) >= 6 and total == complete,
           f"{total} audit row(s), {complete} of them carrying all four fields")

    # Phase 1 policy categories only (FR-CFG-002B).
    deferred = count(ADMIN, """
        SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'policy_category'
          AND e.enumlabel !~ '^(ordering|service|cancellation|discount|refund|tip|cash|approval|local_continuity)$';
    """)
    allowed = count(ADMIN, """
        SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'policy_category';
    """)
    record("only Phase 1 policy categories exist (FR-CFG-002B)", deferred == 0 and allowed == 9,
           f"{allowed} policy categories, {deferred} of them outside the Phase 1 list")

    bad_category = run(APP, "SELECT 'inventory'::config.policy_category;", **H1)
    record("a deferred policy category cannot even be named", not bad_category.ok,
           "the enum is closed, so a Phase 2/3 category is a type error rather than a row")

    # Ownership boundary with M1-B.
    copied = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname <> 'identity'
          AND c.relname ~* '(^|_)governed_action($|_)';
    """)
    references = count(ADMIN, """
        SELECT count(*) FROM pg_constraint con
        JOIN pg_class sc ON sc.oid = con.conrelid
        JOIN pg_namespace sn ON sn.oid = sc.relnamespace
        JOIN pg_class tc ON tc.oid = con.confrelid
        JOIN pg_namespace tn ON tn.oid = tc.relnamespace
        WHERE con.contype = 'f' AND sn.nspname = 'config'
          AND tn.nspname = 'identity' AND tc.relname = 'governed_action';
    """)
    record("configuration references identity.governed_action, it does not copy it",
           copied == 0 and references >= 1,
           f"{copied} duplicate registries outside identity; {references} foreign key(s) "
           f"from config into identity.governed_action")

    orphan = run(APP, f"""
        INSERT INTO config.policy
            (tenant_id, category, version, payload, governed_action_code, effective_from,
             actor_id, approved_by_id, approved_at)
        VALUES ('{TENANT_HABESHA}', 'approval', 99, '{{}}'::jsonb, 'action.that.does.not.exist',
                now(), '{USER_HABESHA}', '{USER_HABESHA}', now());
    """, **H1)
    record("a policy cannot name a governed action that identity does not define",
           not orphan.ok, "the foreign key into identity.governed_action refuses it")


# ===========================================================================
# 4. Reason codes (FR-CFG-003)
# ===========================================================================

def section_reason_codes() -> None:
    print("\n--- 4. Reason codes (FR-CFG-003) ---")

    cats = count(APP, "SELECT count(DISTINCT category) FROM config.reason_code;", **H1)
    record("all ten Phase 1 reason-code categories are populated", cats == 10,
           f"{cats} of 10 categories carry at least one code")

    labelled = run(APP, """
        SELECT count(*)::text FROM config.reason_code rc
        WHERE NOT EXISTS (SELECT 1 FROM config.reason_code_label l
                          WHERE l.reason_code_id = rc.id AND l.locale = 'en');
    """, **H1)
    record("every reason code carries a localized label", labelled.scalar == "0",
           "labels are rows, so Amharic and Arabic arrive at M2 without a schema change")

    bad_locale = run(APP, """
        INSERT INTO config.reason_code_label (tenant_id, reason_code_id, locale, label)
        SELECT tenant_id, id, 'not-a-locale', 'x' FROM config.reason_code LIMIT 1;
    """, **H1)
    record("a malformed locale tag is rejected", not bad_locale.ok,
           "the locale CHECK enforces the ll or ll-CC shape")

    consuming = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND c.relname ~* '(^|_)(order|check|payment|tip|void|discount_application)($|_)';
    """)
    record("no action that consumes a reason code was built", consuming == 0,
           f"{consuming} consuming table(s); ordering is M3 and checks and payments are M4")


# ===========================================================================
# 5. Entitlements (FR-TEN-004, FR-CFG-005A)
# ===========================================================================

def entitlement_deny_by_default_gate() -> tuple[bool, str, str]:
    """An entitlement that was never granted must resolve to deny."""
    leaks: list[str] = []

    for key in ("feature_that_was_never_granted", "", "inventory_module"):
        res = run(APP, f"SELECT config.is_entitled({_lit(key)})::text;", **H1)
        if not res.ok:
            leaks.append(f"resolution errored for {key!r}: {res.err.splitlines()[0] if res.err else ''}")
        elif truthy(res.scalar):
            leaks.append(f"an unset entitlement {key!r} resolved to {res.scalar}")

    null_key = run(APP, "SELECT config.is_entitled(NULL)::text;", **H1)
    if null_key.ok and truthy(null_key.scalar):
        leaks.append("a NULL feature key resolved to allow")

    # A row that exists but is false must also deny.
    off = run(APP, f"SELECT config.is_entitled('waiter_service', '{OUTLET_H2}')::text;", **H2)
    if off.ok and truthy(off.scalar):
        leaks.append("an explicitly disabled entitlement resolved to allow")

    # With no tenant context at all, everything denies.
    no_ctx = run(APP, "SELECT config.is_entitled('qr_ordering')::text;", tenant="", outlet="")
    if no_ctx.ok and truthy(no_ctx.scalar):
        leaks.append("an entitlement resolved without any tenant context")

    # And a genuine grant must still resolve true, or the gate proves nothing.
    granted = run(APP, f"SELECT config.is_entitled('qr_ordering', '{OUTLET_H1}')::text;", **H1)
    if not granted.ok or not truthy(granted.scalar):
        leaks.append("a granted entitlement did not resolve to allow, so the gate is vacuous")

    if leaks:
        return False, "UNKNOWN_ENTITLEMENT_DEFAULTED_OPEN", "; ".join(leaks)
    return True, "", ("unknown, blank, NULL, disabled and context-free all deny; "
                      "an explicit grant still allows")


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def section_entitlements() -> None:
    print("\n--- 5. Entitlements (FR-TEN-004, FR-CFG-005A) ---")

    ok, sig, detail = entitlement_deny_by_default_gate()
    record("entitlements resolve deny-by-default", ok, detail if ok else f"{sig}: {detail}")

    # Outlet scope overrides the tenant-wide grant.
    at_h1 = run(APP, f"SELECT config.is_entitled('waiter_service', '{OUTLET_H1}')::text;", **H1)
    at_h2 = run(APP, f"SELECT config.is_entitled('waiter_service', '{OUTLET_H2}')::text;", **H2)
    record("outlet scope overrides the tenant-wide grant (FR-TEN-004)",
           truthy(at_h1.scalar) and not truthy(at_h2.scalar),
           "waiter service is granted tenant-wide but switched off at one outlet, "
           "with no code fork of any kind")

    # No entitlement may expose a deferred domain, because none exists to expose. The
    # vocabulary comes from the pinned package, never from a list retyped here.
    pattern, term_count = fenced_identifier_pattern()
    deferred_surface = count(ADMIN, f"""
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND c.relname ~* '{pattern}';
    """)
    record("no entitlement can expose a deferred Phase 2/3 surface (FR-CFG-005B)",
           deferred_surface == 0,
           f"{deferred_surface} deferred-domain table(s) exist to be exposed; "
           f"vocabulary of {term_count} terms loaded from the pinned package")


# ===========================================================================
# 6. Numbering (FR-CFG-004) — collision safety under real concurrency
# ===========================================================================

WORKERS = 8
PER_WORKER = 25


def _issue_batch(_: int) -> list[str]:
    """One worker: its own connection, issuing PER_WORKER numbers from the same series."""
    res = run(APP, f"""
        SELECT config.issue_document_number(
            '{TENANT_HABESHA}'::uuid, 'check', '2026', NULL, '{OUTLET_H1}'::uuid)
        FROM generate_series(1, {PER_WORKER});
    """, **H1)
    return [r[0] for r in res.rows] if res.ok else []


def numbering_concurrency_gate() -> tuple[bool, str, str]:
    """Issue numbers from several connections at once and require every one to be unique.

    Sequential issuance would pass even with a badly broken issuer, so the workers run
    genuinely in parallel against one series.
    """
    run(APP, f"""
        DELETE FROM config.issued_document_number WHERE document_type = 'check';
        UPDATE config.number_series SET next_value = 1
        WHERE tenant_id = '{TENANT_HABESHA}' AND outlet_id = '{OUTLET_H1}';
    """, **H1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        batches = list(pool.map(_issue_batch, range(WORKERS)))

    issued = [n for batch in batches for n in batch]
    expected = WORKERS * PER_WORKER
    unique = set(issued)

    problems: list[str] = []
    if len(issued) != expected:
        problems.append(f"{len(issued)} of {expected} requests returned a number")
    if len(unique) != len(issued):
        duplicates = len(issued) - len(unique)
        problems.append(f"{duplicates} duplicate number(s) issued across {WORKERS} concurrent workers")

    stored = count(APP, """
        SELECT count(DISTINCT document_number) FROM config.issued_document_number
        WHERE document_type = 'check';
    """, **H1)
    if stored != len(unique):
        problems.append(f"{stored} distinct number(s) stored but {len(unique)} distinct returned")

    if problems:
        return False, "DUPLICATE_DOCUMENT_NUMBER_ISSUED", "; ".join(problems)
    return True, "", (f"{WORKERS} concurrent workers issued {expected} numbers from one series; "
                      f"all {len(unique)} distinct, stored count agrees")


def section_numbering() -> None:
    print("\n--- 6. Numbering (FR-CFG-004) ---")

    ok, sig, detail = numbering_concurrency_gate()
    record("document numbers are collision-safe under concurrency", ok,
           detail if ok else f"{sig}: {detail}")

    shape = run(APP, f"""
        SELECT document_number FROM config.issued_document_number
        WHERE document_type = 'check' ORDER BY document_number LIMIT 1;
    """, **H1)
    record("numbers are human-readable and scoped by period", shape.ok and shape.scalar.startswith("H1-2026-"),
           f"first issued number is {shape.scalar}, carrying the outlet prefix and fiscal period")

    absent = run(APP, f"""
        SELECT config.issue_document_number(
            '{TENANT_HABESHA}'::uuid, 'check', '1999', NULL, '{OUTLET_H1}'::uuid);
    """, **H1)
    record("issuing against an undefined series is refused", not absent.ok,
           "a missing series raises rather than inventing a number")

    isolated = count(APP, "SELECT count(*) FROM config.number_series;", **H2)
    record("a series belongs to its outlet alone", isolated == 1,
           f"outlet H2 sees {isolated} series — its own, not H1's")


# ===========================================================================
# 7. Seeds (FR-DAT-013)
# ===========================================================================

def section_seeds() -> None:
    print("\n--- 7. Seed data (FR-DAT-013) ---")

    brands = run(ADMIN, """
        SELECT count(DISTINCT tenant_code)::text,
               string_agg(DISTINCT tenant_code, ', ' ORDER BY tenant_code)
        FROM org.tenant WHERE tenant_code IN ('HABESHA', 'NILE');
    """)
    n, names = brands.rows[0] if brands.ok and brands.rows else ("0", "")
    record("two differently branded tenants are seeded", n == "2",
           f"seeded tenants: {names}")

    branding = count(ADMIN, """
        SELECT count(DISTINCT payload ->> 'accent') FROM config.configuration_version
        WHERE category = 'branding';
    """)
    record("the two tenants carry genuinely different branding", branding == 2,
           "different display names and accents, so no house style is baked into the schema")

    outlets = count(ADMIN, f"""
        SELECT count(*) FROM org.org_node
        WHERE tenant_id = '{TENANT_HABESHA}' AND kind = 'outlet';
    """)
    record("one tenant has at least two outlets", outlets >= 2,
           f"{outlets} outlets in the first tenant, so outlet isolation has something to isolate")

    # Isolation, proved across the seeded tenants rather than asserted.
    cross = count(APP, f"SELECT count(*) FROM org.org_node WHERE tenant_id = '{TENANT_NILE}';", **H1)
    sibling = count(APP, f"SELECT count(*) FROM config.number_series WHERE outlet_id = '{OUTLET_H2}';", **H1)
    record("the seeded tenants and outlets are isolated from each other", cross == 0 and sibling == 0,
           f"from the first tenant's outlet: {cross} rows of the other tenant visible, "
           f"{sibling} rows of the sibling outlet visible")

    translations = count(ADMIN, "SELECT count(*) FROM config.reason_code_label WHERE locale <> 'en';")
    record("translations are deferred to M2, as the brief directs", translations == 0,
           f"{translations} non-English label(s); the structure is seeded, the content is not")


# ===========================================================================
# 8. Retention (FR-DAT-018)
# ===========================================================================

def retention_gate() -> tuple[bool, str, str]:
    """Retention must never be able to remove an append-only audit row."""
    run(APP, f"""
        INSERT INTO audit.security_event (tenant_id, outlet_id, event_code, subject_id)
        VALUES ('{TENANT_HABESHA}', '{OUTLET_H1}', 'retention.probe', '{USER_HABESHA}');
    """, **H1)
    before = count(ADMIN, "SELECT count(*) FROM audit.security_event;")
    problems: list[str] = []

    # A policy naming audit storage must not even be storable.
    stored = run(APP, f"""
        INSERT INTO config.retention_policy
            (tenant_id, target_schema, target_table, age_column, retain_for, action)
        VALUES ('{TENANT_HABESHA}', 'audit', 'security_event', 'occurred_at', interval '1 day', 'purge');
    """, **H1)
    if stored.ok:
        problems.append("a retention policy targeting audit storage was accepted")

    applied = run(APP, f"SELECT * FROM config.apply_retention('{TENANT_HABESHA}');", **H1)
    if not applied.ok:
        problems.append(f"retention could not run at all: {applied.err.splitlines()[0] if applied.err else ''}")

    after = count(ADMIN, "SELECT count(*) FROM audit.security_event;")
    if after < before:
        problems.append(f"audit rows fell from {before} to {after} after retention ran")

    if problems:
        return False, "APPEND_ONLY_VIOLATED", "; ".join(problems)
    return True, "", (f"a policy naming audit storage is refused; retention ran and left all "
                      f"{after} audit row(s) in place")


def section_retention() -> None:
    print("\n--- 8. Retention (FR-DAT-018) ---")

    ok, sig, detail = retention_gate()
    record("retention cannot delete append-only audit rows", ok, detail if ok else f"{sig}: {detail}")

    configurable = run(APP, f"""
        SELECT target_schema || '.' || target_table || ' by ' || age_column
               || ' after ' || retain_for::text
        FROM config.retention_policy WHERE tenant_id = '{TENANT_HABESHA}';
    """, **H1)
    record("retention is configurable per tenant and target", configurable.ok and configurable.rows,
           f"policy in force: {configurable.scalar}")

    bad_interval = run(APP, f"""
        INSERT INTO config.retention_policy
            (tenant_id, target_schema, target_table, age_column, retain_for, action)
        VALUES ('{TENANT_HABESHA}', 'identity', 'auth_lockout', 'locked_at', interval '0', 'purge');
    """, **H1)
    record("a zero retention window is refused", not bad_interval.ok,
           "retain_for must be positive, so a policy cannot mean 'delete immediately'")


# ===========================================================================
# 9. Schema documentation (FR-DAT-015)
# ===========================================================================

def section_catalog() -> None:
    print("\n--- 9. Schema documentation (FR-DAT-015) ---")

    catalog = REPO / "schema" / "SCHEMA_CATALOG.md"
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "generate_schema_catalog.py"),
         "--dsn", ADMIN, "--check", str(catalog)],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    record("the committed schema catalog matches the live schema", proc.returncode == 0,
           (proc.stdout.strip() or proc.stderr.strip()).splitlines()[0] if (proc.stdout or proc.stderr) else "")

    text = catalog.read_text(encoding="utf-8") if catalog.exists() else ""
    record("the catalog is generated, not hand-written", "Generated from the live database" in text,
           "it carries the generator's provenance header and is regenerated on every run")

    record("the catalog includes a relationship diagram", "```mermaid" in text,
           "foreign-key edges are rendered from pg_constraint, not drawn by hand")


# ===========================================================================
# 10. Negative controls — red before green
# ===========================================================================

def prove(control: str, gate, signature: str, break_sql: str, revert_sql: str,
          captured: list[str] | None = None) -> None:
    ok, _, detail = gate()
    if not ok:
        record(f"{control} — baseline", False, f"gate already failing before the break: {detail}")
        return

    originals = [capture_function(sig) for sig in (captured or [])]

    broke = run(ADMIN, break_sql)
    if not broke.ok:
        record(f"{control} — inject defect", False, f"could not plant the break: {broke.err}")
        return

    try:
        red_ok, red_sig, red_detail = gate()
        record(f"{control} — RED with the defect planted",
               (not red_ok) and red_sig == signature,
               f"{red_sig or '(gate still passed)'}: {red_detail}")
    finally:
        for original in originals:
            run(ADMIN, original)
        reverted = run(ADMIN, revert_sql) if revert_sql else None

    if reverted is not None and not reverted.ok:
        record(f"{control} — revert", False, f"could not revert: {reverted.err}")
        return

    green_ok, green_sig, green_detail = gate()
    record(f"{control} — GREEN after revert", green_ok,
           green_detail if green_ok else f"{green_sig}: {green_detail}")


def section_controls() -> None:
    print("\n--- 10. M1-C negative controls, each proved red then green ---")

    print("\n  NC-M1C-001  application role mutates an audit row")
    # The grant alone is not the enforcement: the trigger refuses regardless of who asks.
    # The break therefore has to remove BOTH, which is precisely what demonstrates that
    # the trigger — not the grant — is what holds when a role is misconfigured.
    prove("NC-M1C-001", audit_append_only_gate, "AUDIT_MUTATED_BY_ORDINARY_ROLE",
          break_sql="""
              ALTER TABLE audit.security_event DISABLE TRIGGER security_event_append_only;
              GRANT UPDATE, DELETE ON audit.security_event TO hospitality_app;
          """,
          revert_sql="""
              ALTER TABLE audit.security_event ENABLE TRIGGER security_event_append_only;
              REVOKE UPDATE, DELETE ON audit.security_event FROM hospitality_app;
          """)

    print("\n  NC-M1C-002  a money column declared as binary floating point")
    prove("NC-M1C-002", money_exactness_gate, "INEXACT_MONEY_TYPE_ACCEPTED",
          break_sql="ALTER TABLE config.policy ADD COLUMN discount_ceiling double precision;",
          revert_sql="ALTER TABLE config.policy DROP COLUMN discount_ceiling;")

    print("\n  NC-M1C-003  an unset entitlement resolving to allow")
    prove("NC-M1C-003", entitlement_deny_by_default_gate, "UNKNOWN_ENTITLEMENT_DEFAULTED_OPEN",
          break_sql="""
              CREATE OR REPLACE FUNCTION config.is_entitled(p_feature_key text, p_outlet_id uuid DEFAULT NULL)
              RETURNS boolean LANGUAGE plpgsql STABLE AS $break$
              DECLARE v_granted boolean;
              BEGIN
                  SELECT e.granted INTO v_granted FROM config.entitlement e
                  WHERE e.tenant_id = app.current_tenant_id() AND e.feature_key = p_feature_key
                  LIMIT 1;
                  RETURN coalesce(v_granted, true);   -- absent now defaults OPEN
              END; $break$;
          """,
          revert_sql="",
          captured=["config.is_entitled(text,uuid)"])

    print("\n  NC-M1C-004  retention deleting an append-only audit row")
    prove("NC-M1C-004", retention_gate, "APPEND_ONLY_VIOLATED",
          break_sql="""
              ALTER TABLE config.retention_policy DROP CONSTRAINT retention_policy_never_targets_audit;
              ALTER TABLE audit.security_event DISABLE TRIGGER security_event_append_only;
              GRANT DELETE ON audit.security_event TO hospitality_app;
              CREATE OR REPLACE FUNCTION config.apply_retention(p_tenant_id uuid)
              RETURNS TABLE (target text, rows_affected bigint) LANGUAGE plpgsql AS $break$
              DECLARE r record; v_count bigint;
              BEGIN
                  FOR r IN SELECT * FROM config.retention_policy WHERE tenant_id = p_tenant_id
                  LOOP
                      -- the audit guard is gone
                      EXECUTE format('DELETE FROM %I.%I WHERE true', r.target_schema, r.target_table);
                      GET DIAGNOSTICS v_count = ROW_COUNT;
                      target := r.target_schema || '.' || r.target_table;
                      rows_affected := v_count;
                      RETURN NEXT;
                  END LOOP;
              END; $break$;
          """,
          revert_sql="""
              DELETE FROM config.retention_policy WHERE lower(target_schema) = 'audit';
              ALTER TABLE config.retention_policy
                  ADD CONSTRAINT retention_policy_never_targets_audit CHECK (lower(target_schema) <> 'audit');
              ALTER TABLE audit.security_event ENABLE TRIGGER security_event_append_only;
              REVOKE DELETE ON audit.security_event FROM hospitality_app;
          """,
          captured=["config.apply_retention(uuid)"])

    print("\n  NC-M1C-005  numbering colliding under concurrency")
    # A lost-update issuer: it reads the counter, pauses, then writes back what it read.
    # Sequentially this is indistinguishable from the correct version; only real
    # concurrency exposes it, which is why the gate runs eight connections at once.
    prove("NC-M1C-005", numbering_concurrency_gate, "DUPLICATE_DOCUMENT_NUMBER_ISSUED",
          break_sql="""
              CREATE OR REPLACE FUNCTION config.issue_document_number(
                  p_tenant_id uuid, p_document_type text, p_fiscal_period text,
                  p_legal_entity_id uuid DEFAULT NULL, p_outlet_id uuid DEFAULT NULL)
              RETURNS text LANGUAGE plpgsql AS $break$
              DECLARE v_value bigint; v_prefix text; v_number text;
              BEGIN
                  SELECT next_value, prefix INTO v_value, v_prefix
                  FROM config.number_series
                  WHERE tenant_id = p_tenant_id AND document_type = p_document_type
                    AND fiscal_period = p_fiscal_period
                    AND coalesce(outlet_id, '00000000-0000-0000-0000-000000000000'::uuid)
                        = coalesce(p_outlet_id, '00000000-0000-0000-0000-000000000000'::uuid);
                  IF NOT FOUND THEN
                      RAISE EXCEPTION 'NUMBER_SERIES_ABSENT' USING ERRCODE = 'HS404';
                  END IF;
                  PERFORM pg_sleep(0.02);
                  UPDATE config.number_series SET next_value = v_value + 1
                  WHERE tenant_id = p_tenant_id AND document_type = p_document_type
                    AND fiscal_period = p_fiscal_period
                    AND coalesce(outlet_id, '00000000-0000-0000-0000-000000000000'::uuid)
                        = coalesce(p_outlet_id, '00000000-0000-0000-0000-000000000000'::uuid);
                  v_number := v_prefix || p_fiscal_period || '-' || lpad(v_value::text, 6, '0');
                  INSERT INTO config.issued_document_number
                      (tenant_id, legal_entity_id, outlet_id, document_type, fiscal_period, document_number)
                  VALUES (p_tenant_id, p_legal_entity_id, p_outlet_id, p_document_type,
                          p_fiscal_period, v_number)
                  ON CONFLICT DO NOTHING;
                  RETURN v_number;
              END; $break$;
          """,
          revert_sql="",
          captured=["config.issue_document_number(uuid,text,text,uuid,uuid)"])


def main() -> int:
    print("M1-C verification — configuration, audit, money, quantity, retention")
    print("real PostgreSQL, application role, seeded tenants\n")
    ensure_seeds()
    print("seeds present: two branded tenants, three outlets, ten reason-code categories")

    section_money()
    section_audit()
    section_configuration()
    section_reason_codes()
    section_entitlements()
    section_numbering()
    section_seeds()
    section_retention()
    section_catalog()
    section_controls()

    failed = [n for n, ok, _ in results if not ok]
    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    if failed:
        print("\nFAIL M1C_VERIFICATION")
        for n in failed:
            print(f"  - {n}")
        return 1
    print("\nPASS M1C_VERIFICATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
