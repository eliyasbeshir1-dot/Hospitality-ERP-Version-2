#!/usr/bin/env python3
"""M1-B verification harness — identity, memberships and authentication.

Runs against real PostgreSQL through the application role (FR-DAT-017).

Each of the four M1-B negative controls is proved RED before it is trusted GREEN:
the gate runs clean, a defect is injected into the live enforcement point, the gate
must emit its exact signature, the defect is reverted, and the gate must pass again.

Function defects are reverted from the definition captured by pg_get_functiondef()
before the break, so the restored body is byte-for-byte what the migration created
rather than a hand-retyped approximation.

Usage:
    M1A_ADMIN_DSN=... M1A_APP_DSN=... python3 tests/m1b/verify_m1b.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "m1a"))

import fixtures as fx  # noqa: E402
from pg import count, run  # noqa: E402

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]

results: list[tuple[str, bool, str]] = []


def migration_0002_creates() -> tuple[set[str], set[tuple[str, str]]]:
    """Return the schemas and tables that migration 0002 itself creates.

    Read from the migration text rather than from the live database: the database
    accumulates every slice, so only the migration can say what THIS slice built.
    Comment lines are stripped first so prose naming a table is not mistaken for DDL.
    """
    sql = (Path(__file__).resolve().parents[2] / "migrations"
           / "0002_identity_memberships_and_authentication.sql").read_text(encoding="utf-8")
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    schemas = set(re.findall(r"CREATE\s+SCHEMA\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][\w]*)",
                             code, re.I))
    tables = {(m.group(1).lower(), m.group(2).lower()) for m in re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)", code, re.I)}
    return schemas, tables
F: fx.Fixtures


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def establish(token: fx.SessionToken, extra_sql: str = "") -> "object":
    """Authenticate a session token and optionally run SQL in the resulting context.

    Inside a transaction, because since migration 0005 the context the function
    establishes is transaction-local: it reverts at COMMIT so a pooled connection
    cannot hand the next caller someone else's tenant. In psql's autocommit mode each
    statement is its own transaction, so extra_sql would otherwise run with no context
    at all — and an assertion expecting "no rows" would pass for entirely the wrong
    reason. This is also exactly how api/src/db.ts calls it.
    """
    return run(APP, f"""
        SELECT identity.establish_session_context(
            '{token.tenant_id}'::uuid, '{token.outlet_id}'::uuid,
            decode('{token.digest_hex}', 'hex'));
        {extra_sql}
    """, tx=True)


def capture_function(signature: str) -> str:
    res = run(ADMIN, f"SELECT pg_get_functiondef('{signature}'::regprocedure);")
    if not res.ok or not res.out.strip():
        raise RuntimeError(f"could not capture {signature}: {res.err}")
    return res.out


# ===========================================================================
# Gates
# ===========================================================================

def session_revocation_gate() -> tuple[bool, str, str]:
    """A withdrawn membership must not leave a usable session behind (FR-AUTH-004)."""
    leaks: list[str] = []

    # Withdraw Bob's only membership at outlet A1.
    withdraw = run(APP, f"""
        UPDATE identity.membership
        SET status = 'inactive', withdrawn_at = now(),
            row_version = (SELECT row_version FROM identity.membership WHERE id = '{fx.MEMBERSHIP_BOB}')
        WHERE id = '{fx.MEMBERSHIP_BOB}';
    """, tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)
    if not withdraw.ok:
        return False, "SESSION_SURVIVED_ROLE_REMOVAL", f"could not withdraw the membership: {withdraw.err}"

    try:
        # The session must no longer authenticate.
        after = establish(F.revoked)
        if not after.failed_with("NO_ACTIVE_MEMBERSHIP", "SESSION_NOT_LIVE"):
            leaks.append("a session held by the withdrawn member was not refused on its "
                         f"membership: {after.why() or 'it established context'}")

        # And the row itself must be marked revoked by the eager cascade.
        live = count(APP, f"""
            SELECT count(*) FROM identity.session
            WHERE user_account_id = '{fx.USER_BOB}' AND revoked_at IS NULL;
        """, tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)
        if live != 0:
            leaks.append(f"{live} session(s) for the withdrawn member remain unrevoked")

        # A member whose membership stands must be unaffected.
        alice = establish(F.alice_strong)
        if not alice.ok:
            leaks.append("withdrawing one membership disturbed an unrelated member's session")
    finally:
        run(APP, f"""
            UPDATE identity.membership
            SET status = 'active', withdrawn_at = NULL,
                row_version = (SELECT row_version FROM identity.membership WHERE id = '{fx.MEMBERSHIP_BOB}')
            WHERE id = '{fx.MEMBERSHIP_BOB}';
            UPDATE identity.session
            SET revoked_at = NULL, revoked_reason = NULL,
                row_version = row_version
            WHERE user_account_id = '{fx.USER_BOB}';
        """, tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)

    if leaks:
        return False, "SESSION_SURVIVED_ROLE_REMOVAL", "; ".join(leaks)
    return True, "", "withdrawn membership revoked its sessions and blocked re-establishment"


def quick_pin_scope_gate() -> tuple[bool, str, str]:
    """A quick PIN is for low-risk re-entry only (FR-AUTH-005)."""
    leaks: list[str] = []

    # Routine action under a quick-PIN session must work — otherwise the gate would
    # pass simply by denying everything.
    routine = establish(F.bob_quick_pin, "SELECT identity.authorize_action('order.view');")
    if not routine.ok:
        leaks.append("a quick-PIN session was refused a routine action, so the gate proves nothing")

    for action in ("membership.assign", "configuration.modify"):
        sensitive = establish(F.bob_quick_pin, f"SELECT identity.authorize_action('{action}');")
        if sensitive.ok:
            leaks.append(f"a quick-PIN session was allowed to perform {action}")
        elif "LOW_RISK_CREDENTIAL_USED_FOR_SENSITIVE_ACTION" not in sensitive.err:
            # Refused, but for the wrong reason — that is not the control working.
            leaks.append(f"{action} was refused, but not on authentication strength")

    if leaks:
        return False, "LOW_RISK_CREDENTIAL_USED_FOR_SENSITIVE_ACTION", "; ".join(leaks)
    return True, "", "quick PIN admitted for routine re-entry, refused for both governed actions"


def step_up_recency_gate() -> tuple[bool, str, str]:
    """A step-up is only good inside its recency window (FR-AUTH-006)."""
    leaks: list[str] = []

    session_id = run(APP, f"""
        SELECT identity.establish_session_context(
            '{F.alice_strong.tenant_id}'::uuid, '{F.alice_strong.outlet_id}'::uuid,
            decode('{F.alice_strong.digest_hex}', 'hex'));
    """).scalar

    # No step-up at all: refused.
    none = establish(F.alice_strong, "SELECT identity.authorize_action('role.modify');")
    if none.ok:
        leaks.append("a governed action succeeded with no step-up at all")
    elif "STEP_UP_REQUIRED" not in none.err:
        leaks.append("the action was refused, but not for a missing step-up")

    # A step-up older than the five-minute window: refused.
    run(APP, f"""
        INSERT INTO identity.step_up_grant (tenant_id, outlet_id, session_id, action_code, granted_at)
        VALUES ('{fx.TENANT_ACME}', '{fx.OUTLET_A1}', '{session_id}', 'role.modify',
                now() - interval '1 hour');
    """, tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)

    stale = establish(F.alice_strong, "SELECT identity.authorize_action('role.modify');")
    if stale.ok:
        leaks.append("a step-up older than the recency window was accepted")
    elif "STEP_UP_EXPIRED" not in stale.err:
        leaks.append("the stale step-up was refused, but not on its age")

    # A fresh step-up: accepted. Proves the window admits as well as refuses.
    run(APP, f"""
        INSERT INTO identity.step_up_grant (tenant_id, outlet_id, session_id, action_code)
        VALUES ('{fx.TENANT_ACME}', '{fx.OUTLET_A1}', '{session_id}', 'role.modify');
    """, tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)

    fresh = establish(F.alice_strong, "SELECT identity.authorize_action('role.modify');")
    if not fresh.ok:
        leaks.append(f"a step-up inside the window was refused: {fresh.err.splitlines()[0] if fresh.err else ''}")

    run(APP, f"DELETE FROM identity.step_up_grant WHERE session_id = '{session_id}';",
        tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)

    if leaks:
        return False, "STALE_STEP_UP_ACCEPTED", "; ".join(leaks)
    return True, "", "missing and expired step-ups refused; a step-up inside the window accepted"


def service_principal_scope_gate() -> tuple[bool, str, str]:
    """A service principal may act only where it is scoped (FR-AUTH-009)."""
    ctx = dict(tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)
    leaks: list[str] = []

    inside = run(APP, f"""
        SELECT identity.authorize_service_principal(
            '{fx.PRINCIPAL_SYNC}'::uuid, 'order.view', '{fx.OUTLET_A1}'::uuid);
    """, **ctx)
    if not inside.ok:
        leaks.append("the principal was refused inside its own scope, so the gate proves nothing")

    wrong_action = run(APP, f"""
        SELECT identity.authorize_service_principal(
            '{fx.PRINCIPAL_SYNC}'::uuid, 'payment.refund', '{fx.OUTLET_A1}'::uuid);
    """, **ctx)
    if not wrong_action.failed_with("OUT_OF_SCOPE_PRINCIPAL_ACCEPTED_CHECK"):
        leaks.append("an action outside the principal's grant was not refused on scope: "
                     f"{wrong_action.why() or 'it succeeded'}")

    wrong_outlet = run(APP, f"""
        SELECT identity.authorize_service_principal(
            '{fx.PRINCIPAL_SYNC}'::uuid, 'order.view', '{fx.OUTLET_A2}'::uuid);
    """, **ctx)
    if not wrong_outlet.failed_with("OUT_OF_SCOPE_PRINCIPAL_ACCEPTED_CHECK"):
        leaks.append("an outlet outside the principal's grant was not refused on scope: "
                     f"{wrong_outlet.why() or 'it succeeded'}")

    revoked = run(APP, f"""
        UPDATE identity.service_principal SET revoked_at = now(), status = 'inactive',
            row_version = (SELECT row_version FROM identity.service_principal WHERE id = '{fx.PRINCIPAL_SYNC}')
        WHERE id = '{fx.PRINCIPAL_SYNC}';
        SELECT identity.authorize_service_principal(
            '{fx.PRINCIPAL_SYNC}'::uuid, 'order.view', '{fx.OUTLET_A1}'::uuid);
    """, **ctx)
    if not revoked.failed_with("PRINCIPAL_NOT_ACTIVE"):
        leaks.append("a revoked principal was not refused by PRINCIPAL_NOT_ACTIVE: "
                     f"{revoked.why() or 'it was accepted'}")
    run(APP, f"""
        UPDATE identity.service_principal SET revoked_at = NULL, status = 'active',
            row_version = (SELECT row_version FROM identity.service_principal WHERE id = '{fx.PRINCIPAL_SYNC}')
        WHERE id = '{fx.PRINCIPAL_SYNC}';
    """, **ctx)

    if leaks:
        return False, "OUT_OF_SCOPE_PRINCIPAL_ACCEPTED", "; ".join(leaks)
    return True, "", "in-scope call accepted; wrong action, wrong outlet and revoked principal all refused"


# ===========================================================================
# Requirement coverage beyond the four controls
# ===========================================================================

def section_identity() -> None:
    print("\n--- 1. Identity and the provider adapter (FR-AUTH-001) ---")

    ctx = dict(tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)

    channels = count(APP, """
        SELECT count(DISTINCT channel) FROM identity.identity_channel WHERE verified_at IS NOT NULL;
    """, **ctx)
    record("verified phone and verified email are both usable identifiers", channels == 2,
           f"{channels} distinct verified channel kind(s)")

    # The domain model must not carry a provider-specific type.
    typed = count(ADMIN, """
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'identity' AND column_name LIKE '%provider%'
          AND data_type NOT IN ('text', 'character varying');
    """)
    record("no provider-specific type reaches the domain model", typed == 0,
           f"{typed} provider column(s) with a non-opaque type; the binding is text and never parsed")

    # A simulated result must never become a live one.
    seeded = run(APP, f"""
        INSERT INTO identity.otp_transmission (tenant_id, identity_channel_id, mode, provider_name)
        SELECT '{fx.TENANT_ACME}', id, 'simulated', 'simulated-messaging'
        FROM identity.identity_channel WHERE user_account_id = '{fx.USER_BOB}' LIMIT 1
        RETURNING id;
    """, **ctx)
    promote = run(APP, "UPDATE identity.otp_transmission SET mode = 'live' WHERE mode = 'simulated';", **ctx)
    forged = run(APP, f"""
        INSERT INTO identity.otp_transmission
            (tenant_id, identity_channel_id, mode, provider_name, provider_result_ref)
        SELECT '{fx.TENANT_ACME}', id, 'simulated', 'simulated-messaging', 'provider-ref-1234'
        FROM identity.identity_channel WHERE user_account_id = '{fx.USER_BOB}' LIMIT 1;
    """, **ctx)
    record("a simulated result cannot be recorded as a live provider outcome",
           seeded.ok and promote.failed_with("SIMULATED_RESULT_RECORDED_AS_LIVE")
           and forged.failed_with("otp_transmission_simulated_has_no_provider_result"),
           f"mode is immutable after insert ({promote.why()}); a simulated row may carry no "
           f"provider result reference ({forged.why()})")


def section_secrets() -> None:
    print("\n--- 2. Secret handling (FR-SEC-007) ---")

    ctx = dict(tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)

    plaintext = run(APP, f"""
        INSERT INTO identity.credential
            (tenant_id, outlet_id, user_account_id, kind, secret_digest, digest_algorithm, confers_strength)
        VALUES ('{fx.TENANT_ACME}', '{fx.OUTLET_A1}', '{fx.USER_BOB}', 'password',
                'a-plaintext-password'::bytea, 'none', 'standard');
    """, **ctx)
    record("a plaintext secret cannot be stored", plaintext.failed_with("23514", "22001"),
           "the 32-byte digest CHECK rejects anything that is not a digest")

    non_digest = count(ADMIN, """
        SELECT count(*) FROM identity.credential WHERE octet_length(secret_digest) <> 32;
    """)
    record("every stored credential is a digest", non_digest == 0,
           f"{non_digest} credential row(s) are not 32-byte digests")

    # Nothing secret may sit in the repository. Fixtures generate secrets at run time.
    repo = Path(__file__).resolve().parents[2]
    offenders = []
    for path in list((repo / "tests").rglob("*.py")) + list((repo / "tests").rglob("*.sql")) \
            + list((repo / "migrations").rglob("*.sql")) + list((repo / "tools").rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".sql"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        generated = "token_urlsafe" in text or "token_hex" in text
        for marker in ("password =", "password='", 'password="', "pin = '", "secret = '"):
            if marker in text and not generated:
                offenders.append(f"{path.relative_to(repo)} contains {marker!r}")
        # A SQL credential literal — the PASSWORD keyword followed by a quoted value.
        # Caught separately because it has no '=' and would otherwise slip past the
        # markers above. (Written without an example so this comment is not itself a hit.)
        for m in re.finditer(r"password\s+'[^']*'", text):
            offenders.append(f"{path.relative_to(repo)} contains a SQL credential literal")
            break
    record("no plaintext credential literal in migrations, tools or tests", not offenders,
           "; ".join(offenders) if offenders else
           "secrets are generated at run time and only their digests are sent to the database")

    # An error must never echo a secret.
    err = run(APP, f"""
        SELECT identity.establish_session_context(
            '{fx.TENANT_ACME}'::uuid, '{fx.OUTLET_A1}'::uuid,
            decode('{fx.digest("a-token-that-does-not-exist")}', 'hex'));
    """)
    record("a failed authentication does not echo the presented credential",
           err.failed_with("SESSION_NOT_LIVE") and "does not exist" not in err.err.lower(),
           f"the error names the outcome, never the value presented: {err.why()}")


def section_sessions_and_memberships() -> None:
    print("\n--- 3. Memberships, sessions and devices (FR-AUTH-004, FR-AUTH-008) ---")

    ok_ctx = establish(F.alice_strong)
    record("an active membership establishes tenant and outlet context", ok_ctx.ok,
           "identity.establish_session_context is the bridge to app.row_in_scope()")

    # Context established from a session must match what RLS then enforces. In a
    # transaction, so the count runs under the context rather than after it has reverted
    # — otherwise "0 sibling rows" would be true because there was no context at all.
    scoped = run(APP, f"""
        SELECT identity.establish_session_context(
            '{F.alice_strong.tenant_id}'::uuid, '{F.alice_strong.outlet_id}'::uuid,
            decode('{F.alice_strong.digest_hex}', 'hex'));
        SELECT count(*) FROM org.org_node WHERE outlet_id = '{fx.OUTLET_A1}';
        SELECT count(*) FROM org.org_node WHERE outlet_id = '{fx.OUTLET_A2}';
    """, tx=True)
    own, sibling = (scoped.rows[-2][0], scoped.rows[-1][0]) if scoped.ok and len(scoped.rows) >= 2 else ("0", "-")
    record("context established from a session cannot see the sibling outlet",
           scoped.ok and int(own) > 0 and sibling == "0",
           f"M1-A isolation holds under a context that M1-B produced: "
           f"{own} node(s) visible in the session's own outlet, {sibling} in the sibling")

    # Claiming a scope the token does not belong to must find nothing.
    forged_outlet = run(APP, f"""
        SELECT identity.establish_session_context(
            '{F.alice_strong.tenant_id}'::uuid, '{fx.OUTLET_A2}'::uuid,
            decode('{F.alice_strong.digest_hex}', 'hex'));
    """)
    forged_tenant = run(APP, f"""
        SELECT identity.establish_session_context(
            '{fx.TENANT_GLOBEX}'::uuid, '{fx.OUTLET_A1}'::uuid,
            decode('{F.alice_strong.digest_hex}', 'hex'));
    """)
    record("a token presented under a scope it does not belong to authenticates nobody",
           forged_outlet.failed_with("SESSION_NOT_LIVE")
           and forged_tenant.failed_with("SESSION_NOT_LIVE"),
           f"the claimed scope is checked by RLS, so a forged prefix matches no row "
           f"(outlet: {forged_outlet.why()}; tenant: {forged_tenant.why()})")

    # Sessions are listable and revocable per user and per device.
    listed = count(APP, f"""
        SELECT count(*) FROM identity.session WHERE user_account_id = '{fx.USER_ALICE}';
    """, tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)
    revoke = run(APP, f"""
        UPDATE identity.session SET revoked_at = now(), revoked_reason = 'administrator_revoked',
               row_version = row_version
        WHERE device_id = '{fx.DEVICE_A1}' AND user_account_id = '{fx.USER_ALICE}'
          AND token_digest = decode('{F.alice_standard.digest_hex}', 'hex');
    """, tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)
    after = establish(F.alice_standard)
    still = establish(F.alice_strong)
    record("a session can be listed and revoked per user and per device",
           listed >= 2 and revoke.ok and after.failed_with("SESSION_NOT_LIVE") and still.ok,
           f"{listed} session(s) listed for the user; the revoked one no longer authenticates "
           f"while the other still does")

    # Token rotation replaces the digest and retires the old token.
    rotated = fx.SessionToken(fx.TENANT_ACME, fx.OUTLET_A1)
    rot = run(APP, f"""
        UPDATE identity.session
        SET token_digest = decode('{rotated.digest_hex}', 'hex'), last_rotated_at = now(),
            row_version = row_version
        WHERE token_digest = decode('{F.alice_strong.digest_hex}', 'hex');
    """, tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)
    old_token = establish(F.alice_strong)
    new_token = establish(rotated)
    record("rotating a token retires the previous one",
           rot.ok and old_token.failed_with("SESSION_NOT_LIVE") and new_token.ok,
           "the superseded digest authenticates nobody")
    run(APP, f"""
        UPDATE identity.session SET token_digest = decode('{F.alice_strong.digest_hex}', 'hex'),
               row_version = row_version
        WHERE token_digest = decode('{rotated.digest_hex}', 'hex');
        UPDATE identity.session SET revoked_at = NULL, revoked_reason = NULL, row_version = row_version
        WHERE user_account_id = '{fx.USER_ALICE}';
    """, tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)

    # Sibling-outlet staff must not see this outlet's identity rows.
    cross = count(APP, f"""
        SELECT count(*) FROM identity.membership WHERE outlet_id = '{fx.OUTLET_A1}';
    """, tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A2)
    record("identity rows obey sibling-outlet isolation", cross == 0,
           f"outlet A2 context sees {cross} of outlet A1's membership rows")


def section_rate_limiting() -> None:
    print("\n--- 4. Rate limiting and lockout (FR-AUTH-007) ---")

    subject = fx.digest("subject-under-test")
    for _ in range(5):
        run(APP, f"""
            SELECT identity.register_auth_attempt('{fx.TENANT_ACME}'::uuid,
                decode('{subject}', 'hex'), false);
        """, tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)

    locked = run(APP, f"""
        SELECT identity.register_auth_attempt('{fx.TENANT_ACME}'::uuid,
            decode('{subject}', 'hex'), false);
    """, tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)
    record("repeated failures lock the subject out",
           locked.failed_with("SUBJECT_LOCKED_OUT"),
           "five failures inside the window trip the lock; further attempts are refused")

    stored = count(ADMIN, """
        SELECT count(*) FROM identity.auth_attempt WHERE octet_length(subject_digest) <> 32;
    """)
    record("attempts are keyed by digest, not by phone number or email", stored == 0,
           "no identifier is stored in clear alongside the attempt")

    record("distributed production rate limiting is NOT claimed here", True,
           "these are single-database counters. Distributed enforcement across API "
           "instances is M6 infrastructure and is explicitly not proven by this harness.")


def section_recovery() -> None:
    print("\n--- 5. Administrator-controlled recovery (FR-AUTH-010) ---")

    ctx = dict(tenant=fx.TENANT_ACME, outlet=fx.OUTLET_A1)

    premature = run(APP, f"""
        INSERT INTO identity.recovery_request
            (tenant_id, outlet_id, subject_user_id, requested_by_user_id, completed_at)
        VALUES ('{fx.TENANT_ACME}', '{fx.OUTLET_A1}', '{fx.USER_BOB}', '{fx.USER_ALICE}', now());
    """, **ctx)
    record("recovery cannot complete without identity verification and factor revocation",
           premature.failed_with("23514", "recovery_request_completion_requires_both"),
           f"the CHECK refuses a completed recovery that skipped either step: {premature.why()}")

    proper = run(APP, f"""
        INSERT INTO identity.recovery_request
            (tenant_id, outlet_id, subject_user_id, requested_by_user_id,
             identity_verified_at, old_factors_revoked_at, completed_at)
        VALUES ('{fx.TENANT_ACME}', '{fx.OUTLET_A1}', '{fx.USER_BOB}', '{fx.USER_ALICE}',
                now(), now(), now());
        SELECT identity.emit_security_event('recovery.completed', '{fx.USER_BOB}');
    """, **ctx)
    record("a properly verified recovery completes and emits a security event", proper.ok,
           "the event is emitted, not stored: durable audit storage is M1-C")

    # Again scoped to slice B's migration. M1-C owns audit storage and builds it there.
    _, created_tables = migration_0002_creates()
    audit_built = sorted(f"{s}.{n}" for s, n in created_tables
                         if s == "audit" or re.search(r"(^|_)(audit|audit_log|audit_trail)($|_)", n, re.I))
    record("migration 0002 built no audit storage", not audit_built,
           "; ".join(audit_built) if audit_built else
           "none; M1-B emits security events and M1-C stores them")


def section_scope_boundary() -> None:
    print("\n--- 6. Slice boundary: nothing from M1-C was built ---")

    # Scoped to this slice's own migration, not to the whole database. Later slices
    # legitimately add configuration, audit and money tables; what must stay true
    # forever is that slice B did not build them.
    created_schemas, created_tables = migration_0002_creates()
    out_of_lane = sorted({s for s in created_schemas if s not in {"identity"}}
                         | {f"{s}.{n}" for s, n in created_tables if s != "identity"})
    record("migration 0002 created tables only in the identity schema", not out_of_lane,
           "; ".join(out_of_lane) if out_of_lane else
           f"{len(created_tables)} table(s), all in identity; slice B stayed in its lane")

    m1c_shaped = sorted(f"{s}.{n}" for s, n in created_tables
                        if re.search(r"(^|_)(configuration|config|policy_store|entitlement|"
                                     r"money|quantity|retention|seed)($|_)", n, re.I))
    record("migration 0002 created no configuration, entitlement, money or quantity table",
           not m1c_shaped, "; ".join(m1c_shaped) if m1c_shaped else
           "none; those belong to M1-C and were not built here")

    forced = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'identity' AND c.relkind = 'r'
          AND NOT (c.relrowsecurity AND c.relforcerowsecurity);
    """)
    total = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'identity' AND c.relkind = 'r';
    """)
    record("every new table has row level security ENABLEd and FORCEd", forced == 0,
           f"{total} identity table(s); {forced} without ENABLE+FORCE")

    unscoped = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'identity' AND c.relkind = 'r'
          AND NOT EXISTS (SELECT 1 FROM pg_attribute a
                          WHERE a.attrelid = c.oid AND a.attname = 'tenant_id'
                            AND a.attnum > 0 AND NOT a.attisdropped);
    """)
    record("every new table carries tenant scope", unscoped == 0,
           f"{unscoped} identity table(s) without a tenant_id column")

    # app.row_in_scope() must be exactly what migration 0001 defined.
    definition = run(ADMIN, "SELECT pg_get_functiondef('app.row_in_scope(uuid,uuid)'::regprocedure);")
    weakened = ("current_tenant_id() IS NOT NULL" not in definition.out
                or "current_outlet_id() IS NOT NULL" not in definition.out)
    record("app.row_in_scope() was not weakened by this slice", not weakened,
           "the M1-A isolation predicate is unchanged; M1-B narrows access, never widens it")

    principal_classes = count(ADMIN, """
        SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'principal_class';
    """)
    # THE BOUNDARY MOVED AT M4-C, and it is replaced by the property that outlives the
    # gate rather than deleted — the tenth time this repository has done that.
    #
    # This check used to refuse any table matching sync|outbox|inbox|PRINT|edge, and read
    # as "the print-agent principal class is registered and nothing uses it". That was
    # true from M1-B to M4-B and stopped being the right question at the gate whose whole
    # subject is a printed receipt: FR-BIL-017 requires a real physical receipt at M4 and
    # FR-CFG-001D requires the printer registered and tested, so docs.print_attempt is the
    # requirement rather than a violation of it.
    #
    # What has NOT changed is the M5a boundary, and it is now asserted directly instead of
    # by proxy. M5a owns the outlet node, its synchronization, and the RESILIENT LOCAL
    # PRINT QUEUE. So: no sync, outbox, inbox or edge table at all, and printing exists
    # with NO QUEUE — nothing pending, nothing retried, nothing scheduled for a later
    # attempt. A queue is what makes a print survive an outage, and surviving an outage is
    # exactly what this gate does not build.
    #
    # Strictly stronger than what it replaces: "no printing" was a fence that a correct
    # change had to break, and "no queued printing" is one that stays true through M5a's
    # arrival and fails if the queue lands early.
    outlet_node_behaviour = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND c.relname ~* '(^|_)(sync|outbox|inbox|edge)($|_)';
    """)
    print_queue = count(ADMIN, """
        SELECT count(*) FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND a.attnum > 0 AND NOT a.attisdropped
          AND c.relname ~* '(^|_)print($|_)'
          AND a.attname ~* '(queue|pending|retry|attempts_remaining|next_attempt)';
    """)
    record("the outlet node and its print queue are still M5a's, and printing has no queue",
           principal_classes == 4 and outlet_node_behaviour == 0 and print_queue == 0,
           f"{principal_classes} principal classes registered; "
           f"{outlet_node_behaviour} sync, outbox, inbox or edge table(s); "
           f"{print_queue} queue-shaped column(s) on a print table. FR-BIL-017 makes the "
           f"minimum print path this gate's; the queue that would make it survive an "
           f"outage stays M5a's")


def session_context_leak_gate() -> tuple[bool, str, str]:
    """Request context must not outlive the transaction that established it.

    F7. api/src/db.ts documented SET LOCAL semantics — "context set with a plain SET
    would outlive the request and hand the next caller someone else's tenant" — while
    identity.establish_session_context used set_config(..., false), which is a plain SET.
    The connection returned to the pool with the tenant still set, so the next borrower
    inherited it. No M1 route exposed the gap; M2 adds customer-facing routes.

    This is the proof at the layer the guarantee lives on: one connection, one script.
    Context is established inside a transaction, shown live while that transaction is
    open, and shown gone after COMMIT on the same connection — which is exactly the
    connection Database.withoutContext() borrows next.
    """
    leaks: list[str] = []

    probe = run(APP, f"""
        BEGIN;
        SELECT identity.establish_session_context(
            '{F.alice_strong.tenant_id}'::uuid, '{F.alice_strong.outlet_id}'::uuid,
            decode('{F.alice_strong.digest_hex}', 'hex'));
        SELECT count(*)::text FROM org.org_node;
        COMMIT;
        SELECT count(*)::text FROM org.org_node;
        SELECT coalesce(nullif(current_setting('app.tenant_id', true), ''), '(unset)');
    """)
    if not probe.ok or len(probe.rows) < 3:
        return False, "CONTEXT_SURVIVED_COMMIT", f"the probe did not run: {probe.why()}"

    inside, after, tenant_after = probe.rows[-3][0], probe.rows[-2][0], probe.rows[-1][0]
    if int(inside) <= 0:
        leaks.append(f"context was not live inside the transaction ({inside} row(s) visible), "
                     f"so the rest of this gate would pass vacuously")
    if after != "0":
        leaks.append(f"{after} row(s) still visible on the same connection after COMMIT")
    if tenant_after != "(unset)":
        leaks.append(f"app.tenant_id survived COMMIT as {tenant_after}")

    if leaks:
        return False, "CONTEXT_SURVIVED_COMMIT", "; ".join(leaks)
    return True, "", ("context is live inside the transaction and gone after COMMIT on the "
                      "same connection; app.tenant_id is unset again")


# ===========================================================================
# Negative controls — red before green
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
    print("\n--- 7. M1-B negative controls, each proved red then green ---")

    print("\n  NC-M1B-001  membership withdrawn but session still authorized")
    prove("NC-M1B-001", session_revocation_gate, "SESSION_SURVIVED_ROLE_REMOVAL",
          break_sql="""
              ALTER TABLE identity.membership DISABLE TRIGGER membership_revocation_cascade;
              CREATE OR REPLACE FUNCTION identity.establish_session_context(
                  p_tenant_id uuid, p_outlet_id uuid, p_token_digest bytea) RETURNS uuid
              LANGUAGE plpgsql AS $break$
              DECLARE v_session identity.session%ROWTYPE;
              BEGIN
                  PERFORM set_config('app.tenant_id', coalesce(p_tenant_id::text, ''), false);
                  PERFORM set_config('app.outlet_id', coalesce(p_outlet_id::text, ''), false);
                  SELECT * INTO v_session FROM identity.session s
                  WHERE s.token_digest = p_token_digest AND s.expires_at > now();
                  IF NOT FOUND THEN
                      RAISE EXCEPTION 'SESSION_NOT_LIVE' USING ERRCODE = 'HS401';
                  END IF;
                  PERFORM set_config('app.session_id', v_session.id::text, false);
                  PERFORM set_config('app.auth_strength', v_session.established_with::text, false);
                  RETURN v_session.id;
              END; $break$;
          """,
          revert_sql="ALTER TABLE identity.membership ENABLE TRIGGER membership_revocation_cascade;",
          captured=["identity.establish_session_context(uuid,uuid,bytea)"])

    print("\n  NC-M1B-002  quick PIN accepted for a step-up-governed action")
    prove("NC-M1B-002", quick_pin_scope_gate, "LOW_RISK_CREDENTIAL_USED_FOR_SENSITIVE_ACTION",
          break_sql="""
              CREATE OR REPLACE FUNCTION identity.authorize_action(p_action_code text) RETURNS boolean
              LANGUAGE plpgsql AS $break$
              DECLARE v_session identity.session%ROWTYPE;
              BEGIN
                  SELECT * INTO v_session FROM identity.session
                  WHERE id = app.current_session_id() AND revoked_at IS NULL AND expires_at > now();
                  IF NOT FOUND THEN
                      RAISE EXCEPTION 'SESSION_NOT_LIVE' USING ERRCODE = 'HS401';
                  END IF;
                  RETURN true;   -- strength and step-up checks removed
              END; $break$;
          """,
          revert_sql="",
          captured=["identity.authorize_action(text)"])

    print("\n  NC-M1B-003  step-up recency window ignored")
    prove("NC-M1B-003", step_up_recency_gate, "STALE_STEP_UP_ACCEPTED",
          break_sql="""
              CREATE OR REPLACE FUNCTION identity.authorize_action(p_action_code text) RETURNS boolean
              LANGUAGE plpgsql AS $break$
              DECLARE
                  v_session identity.session%ROWTYPE;
                  v_action  identity.governed_action%ROWTYPE;
                  v_granted timestamptz;
              BEGIN
                  SELECT * INTO v_session FROM identity.session
                  WHERE id = app.current_session_id() AND revoked_at IS NULL AND expires_at > now();
                  IF NOT FOUND THEN RAISE EXCEPTION 'SESSION_NOT_LIVE' USING ERRCODE = 'HS401'; END IF;
                  SELECT * INTO v_action FROM identity.governed_action
                  WHERE tenant_id = v_session.tenant_id AND action_code = p_action_code;
                  IF v_session.established_with < v_action.minimum_strength THEN
                      RAISE EXCEPTION 'LOW_RISK_CREDENTIAL_USED_FOR_SENSITIVE_ACTION'
                          USING ERRCODE = 'HS403';
                  END IF;
                  IF v_action.step_up_required THEN
                      SELECT max(granted_at) INTO v_granted FROM identity.step_up_grant
                      WHERE session_id = v_session.id AND action_code = p_action_code;
                      IF v_granted IS NULL THEN
                          RAISE EXCEPTION 'STEP_UP_REQUIRED' USING ERRCODE = 'HS403';
                      END IF;
                      -- the recency window is no longer checked
                  END IF;
                  RETURN true;
              END; $break$;
          """,
          revert_sql="",
          captured=["identity.authorize_action(text)"])

    print("\n  NC-M1B-004  service principal used outside its scope")
    prove("NC-M1B-004", service_principal_scope_gate, "OUT_OF_SCOPE_PRINCIPAL_ACCEPTED",
          break_sql="""
              CREATE OR REPLACE FUNCTION identity.authorize_service_principal(
                  p_principal_id uuid, p_action_code text, p_outlet_id uuid) RETURNS boolean
              LANGUAGE plpgsql AS $break$
              DECLARE v_principal identity.service_principal%ROWTYPE;
              BEGIN
                  SELECT * INTO v_principal FROM identity.service_principal
                  WHERE id = p_principal_id AND status = 'active' AND revoked_at IS NULL;
                  IF NOT FOUND THEN
                      RAISE EXCEPTION 'PRINCIPAL_NOT_ACTIVE' USING ERRCODE = 'HS401';
                  END IF;
                  RETURN true;   -- scope check removed
              END; $break$;
          """,
          revert_sql="",
          captured=["identity.authorize_service_principal(uuid,text,uuid)"])

    print("\n  NC-M1B-005  request context outlives the transaction that set it")
    prove("NC-M1B-005", session_context_leak_gate, "CONTEXT_SURVIVED_COMMIT",
          break_sql="""
              CREATE OR REPLACE FUNCTION identity.establish_session_context(
                  p_tenant_id uuid, p_outlet_id uuid, p_token_digest bytea
              ) RETURNS uuid LANGUAGE plpgsql AS $break$
              DECLARE
                  v_session identity.session%ROWTYPE;
              BEGIN
                  -- The pre-repair body: session-level, so it outlives COMMIT.
                  PERFORM set_config('app.tenant_id', coalesce(p_tenant_id::text, ''), false);
                  PERFORM set_config('app.outlet_id', coalesce(p_outlet_id::text, ''), false);
                  SELECT * INTO v_session FROM identity.session s
                  WHERE s.token_digest = p_token_digest AND s.revoked_at IS NULL
                    AND s.expires_at > now();
                  IF NOT FOUND THEN
                      PERFORM set_config('app.tenant_id', '', false);
                      PERFORM set_config('app.outlet_id', '', false);
                      RAISE EXCEPTION 'SESSION_NOT_LIVE' USING ERRCODE = 'HS401';
                  END IF;
                  PERFORM set_config('app.session_id', v_session.id::text, false);
                  PERFORM set_config('app.auth_strength', v_session.established_with::text, false);
                  RETURN v_session.id;
              END; $break$;
          """,
          revert_sql="",
          captured=["identity.establish_session_context(uuid,uuid,bytea)"])


def main() -> int:
    global F
    print("M1-B verification — identity, memberships and authentication")
    print("real PostgreSQL, application role, secrets generated at run time\n")
    fx.reset(ADMIN)
    F = fx.seed(APP)
    print("fixtures seeded: 3 users, 2 roles, 4 sessions, 1 service principal")

    section_identity()
    section_secrets()
    section_sessions_and_memberships()
    section_rate_limiting()
    section_recovery()
    section_scope_boundary()
    section_controls()

    failed = [n for n, ok, _ in results if not ok]
    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    if failed:
        print("\nFAIL M1B_VERIFICATION")
        for n in failed:
            print(f"  - {n}")
        return 1
    print("\nPASS M1B_VERIFICATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
