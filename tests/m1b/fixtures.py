"""M1-B identity fixtures.

Built in Python rather than as a .sql file for one reason: secrets.

Every credential, one-time code and session token is generated here at run time,
kept only in process memory, and sent to the database as a SHA-256 digest. No
plaintext secret is ever written to a file, so none can leak into the repository,
a diff, a log or a CI artifact (FR-SEC-007). The digest columns carry a 32-byte
length CHECK, so a plaintext value could not be stored even by mistake.

Seeded through hospitality_app — the real runtime role — so every insert passes the
same RLS policies the application runs under (FR-DAT-017).
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field

from pg import run

TENANT_ACME = "11111111-1111-1111-1111-111111111111"
TENANT_GLOBEX = "22222222-2222-2222-2222-222222222222"
OUTLET_A1 = "aaaa0001-0000-4000-8000-000000000001"
OUTLET_A2 = "aaaa0002-0000-4000-8000-000000000002"
DEVICE_A1 = "aaaa1105-0000-4000-8000-000000000001"   # Bole POS 1, from the M1-A fixtures
DEVICE_A2 = "aaaa2103-0000-4000-8000-000000000002"   # Piassa POS 1

# Fixed ids so assertions can name rows; these are identifiers, not secrets.
USER_ALICE = "cccc0001-0000-4000-8000-000000000001"   # manager at outlet A1
USER_BOB = "cccc0002-0000-4000-8000-000000000002"     # server at outlet A1
USER_CAROL = "cccc0003-0000-4000-8000-000000000003"   # server at sibling outlet A2
ROLE_MANAGER = "dddd0001-0000-4000-8000-000000000001"
ROLE_SERVER = "dddd0002-0000-4000-8000-000000000002"
MEMBERSHIP_BOB = "eeee0002-0000-4000-8000-000000000002"
PRINCIPAL_SYNC = "ffff0001-0000-4000-8000-000000000001"


def digest(value: str) -> str:
    """Hex-encoded SHA-256 of a secret. Only this ever reaches the database."""
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass
class SessionToken:
    """A bearer session token.

    The tenant and outlet travel in the token's non-secret prefix. That is what lets
    a holder establish context without any RLS exception: the prefix says which scope
    to claim, and the secret suffix is what proves the claim. Claiming the wrong scope
    finds no row.
    """
    tenant_id: str
    outlet_id: str
    secret: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)

    @property
    def token(self) -> str:
        return f"{self.tenant_id}.{self.outlet_id}.{self.secret}"

    @property
    def digest_hex(self) -> str:
        return digest(self.token)


@dataclass
class Fixtures:
    alice_strong: SessionToken
    alice_standard: SessionToken
    bob_quick_pin: SessionToken
    carol_sibling: SessionToken
    revoked: SessionToken


# Fixture tables cleared on reset. governed_action is deliberately absent: those rows
# are installed by the tenant trigger and are part of the schema's behaviour, not fixture
# data, so clearing them would hide a regression in that trigger.
RESET_TABLES = [
    "identity.step_up_grant", "identity.session", "identity.membership",
    "identity.credential", "identity.otp_transmission", "identity.identity_channel",
    "identity.auth_provider_binding", "identity.role_action", "identity.role",
    "identity.recovery_request", "identity.service_principal_scope",
    "identity.service_principal", "identity.terminal_trust",
    "identity.auth_attempt", "identity.auth_lockout", "identity.user_account",
]


def reset(admin_dsn: str) -> None:
    """Clear M1-B fixture rows so the suite can be run repeatedly on one database."""
    res = run(admin_dsn, "TRUNCATE " + ", ".join(RESET_TABLES) + " CASCADE;")
    if not res.ok:
        raise RuntimeError(f"could not reset identity fixtures: {res.err}")


def seed(app_dsn: str) -> Fixtures:
    """Create the M1-B identity graph. Raises if any statement is refused."""
    f = Fixtures(
        alice_strong=SessionToken(TENANT_ACME, OUTLET_A1),
        alice_standard=SessionToken(TENANT_ACME, OUTLET_A1),
        bob_quick_pin=SessionToken(TENANT_ACME, OUTLET_A1),
        carol_sibling=SessionToken(TENANT_ACME, OUTLET_A2),
        revoked=SessionToken(TENANT_ACME, OUTLET_A1),
    )

    # ---- users, roles and grants (tenant scope is enough for these) ----
    res = run(app_dsn, f"""
        INSERT INTO identity.user_account (id, tenant_id, staff_number, display_name) VALUES
            ('{USER_ALICE}', '{TENANT_ACME}', 'STAFF-0001', 'Alice Manager'),
            ('{USER_BOB}',   '{TENANT_ACME}', 'STAFF-0002', 'Bob Server'),
            ('{USER_CAROL}', '{TENANT_ACME}', 'STAFF-0003', 'Carol Server');

        INSERT INTO identity.identity_channel (tenant_id, user_account_id, channel, channel_value, verified_at) VALUES
            ('{TENANT_ACME}', '{USER_ALICE}', 'email', 'alice@example.test', now()),
            ('{TENANT_ACME}', '{USER_BOB}',   'phone', '+251900000002',     now()),
            ('{TENANT_ACME}', '{USER_CAROL}', 'phone', '+251900000003',     NULL);

        INSERT INTO identity.role (id, tenant_id, role_code, display_name) VALUES
            ('{ROLE_MANAGER}', '{TENANT_ACME}', 'MANAGER', 'Outlet Manager'),
            ('{ROLE_SERVER}',  '{TENANT_ACME}', 'SERVER',  'Waiter');

        INSERT INTO identity.role_action (tenant_id, role_id, action_code) VALUES
            ('{TENANT_ACME}', '{ROLE_MANAGER}', 'order.view'),
            ('{TENANT_ACME}', '{ROLE_MANAGER}', 'session.resume'),
            ('{TENANT_ACME}', '{ROLE_MANAGER}', 'membership.assign'),
            ('{TENANT_ACME}', '{ROLE_MANAGER}', 'membership.withdraw'),
            ('{TENANT_ACME}', '{ROLE_MANAGER}', 'role.modify'),
            ('{TENANT_ACME}', '{ROLE_MANAGER}', 'configuration.modify'),
            ('{TENANT_ACME}', '{ROLE_SERVER}',  'order.view'),
            ('{TENANT_ACME}', '{ROLE_SERVER}',  'session.resume'),
            -- Granted deliberately. The quick-PIN control needs authentication
            -- strength to be the ONLY barrier left: if the role did not grant these,
            -- the refusal would come from the missing grant and the control would
            -- pass for the wrong reason, proving nothing about the PIN.
            ('{TENANT_ACME}', '{ROLE_SERVER}',  'membership.assign'),
            ('{TENANT_ACME}', '{ROLE_SERVER}',  'configuration.modify');
    """, tenant=TENANT_ACME, outlet="")
    if not res.ok:
        raise RuntimeError(f"identity fixtures failed: {res.err}")

    # ---- memberships, credentials and sessions (outlet A1) ----
    pin_secret = secrets.token_hex(16)          # never leaves this process
    password_secret = secrets.token_urlsafe(24)
    res = run(app_dsn, f"""
        INSERT INTO identity.membership (tenant_id, outlet_id, user_account_id, role_id) VALUES
            ('{TENANT_ACME}', '{OUTLET_A1}', '{USER_ALICE}', '{ROLE_MANAGER}');
        INSERT INTO identity.membership (id, tenant_id, outlet_id, user_account_id, role_id) VALUES
            ('{MEMBERSHIP_BOB}', '{TENANT_ACME}', '{OUTLET_A1}', '{USER_BOB}', '{ROLE_SERVER}');

        INSERT INTO identity.terminal_trust (device_id, tenant_id, outlet_id)
        VALUES ('{DEVICE_A1}', '{TENANT_ACME}', '{OUTLET_A1}');

        INSERT INTO identity.credential
            (tenant_id, outlet_id, user_account_id, kind, secret_digest, digest_algorithm, confers_strength)
        VALUES
            ('{TENANT_ACME}', '{OUTLET_A1}', '{USER_BOB}', 'quick_pin',
             decode('{digest(pin_secret)}', 'hex'), 'sha-256', 'low'),
            ('{TENANT_ACME}', NULL, '{USER_ALICE}', 'password',
             decode('{digest(password_secret)}', 'hex'), 'sha-256', 'standard');

        INSERT INTO identity.session
            (tenant_id, outlet_id, user_account_id, device_id, token_digest, established_with, expires_at)
        VALUES
            ('{TENANT_ACME}', '{OUTLET_A1}', '{USER_ALICE}', '{DEVICE_A1}',
             decode('{f.alice_strong.digest_hex}', 'hex'), 'strong',   now() + interval '8 hours'),
            ('{TENANT_ACME}', '{OUTLET_A1}', '{USER_ALICE}', '{DEVICE_A1}',
             decode('{f.alice_standard.digest_hex}', 'hex'), 'standard', now() + interval '8 hours'),
            ('{TENANT_ACME}', '{OUTLET_A1}', '{USER_BOB}', '{DEVICE_A1}',
             decode('{f.bob_quick_pin.digest_hex}', 'hex'), 'low',      now() + interval '8 hours'),
            ('{TENANT_ACME}', '{OUTLET_A1}', '{USER_BOB}', '{DEVICE_A1}',
             decode('{f.revoked.digest_hex}', 'hex'), 'standard', now() + interval '8 hours');

        INSERT INTO identity.service_principal (id, tenant_id, principal_code, class)
        VALUES ('{PRINCIPAL_SYNC}', '{TENANT_ACME}', 'SP-SYNC-01', 'worker');

        INSERT INTO identity.service_principal_scope
            (tenant_id, service_principal_id, outlet_id, action_code)
        VALUES ('{TENANT_ACME}', '{PRINCIPAL_SYNC}', '{OUTLET_A1}', 'order.view');
    """, tenant=TENANT_ACME, outlet=OUTLET_A1)
    if not res.ok:
        raise RuntimeError(f"outlet A1 fixtures failed: {res.err}")

    # ---- sibling outlet A2, so isolation assertions have a real target ----
    res = run(app_dsn, f"""
        INSERT INTO identity.membership (tenant_id, outlet_id, user_account_id, role_id)
        VALUES ('{TENANT_ACME}', '{OUTLET_A2}', '{USER_CAROL}', '{ROLE_SERVER}');

        INSERT INTO identity.session
            (tenant_id, outlet_id, user_account_id, device_id, token_digest, established_with, expires_at)
        VALUES ('{TENANT_ACME}', '{OUTLET_A2}', '{USER_CAROL}', '{DEVICE_A2}',
                decode('{f.carol_sibling.digest_hex}', 'hex'), 'standard', now() + interval '8 hours');
    """, tenant=TENANT_ACME, outlet=OUTLET_A2)
    if not res.ok:
        raise RuntimeError(f"outlet A2 fixtures failed: {res.err}")

    return f
