"""M3-D fixtures: a manager who can approve, a terminal, and the roles a floor needs.

Built on M3-C's, which is built on M3-B's, and so on down to M1-A. Nothing here stubs a
staff surface: a waiter is somebody with a membership whose role grants actions, on a
terminal registered to an outlet, and a manager is a DIFFERENT person whose own session
can be stepped up. That separation is the whole security argument of FR-POS-006, so the
fixtures make it real rather than convenient.

What this module adds that no earlier slice needed:

  * A MANAGER, distinct from every waiter, whose role grants the governed actions this
    gate exercises. M3-C's supervisor escalates service requests; approving an override
    is a different authority and gets a different role, because one role that did both
    would make the override controls pass for the wrong reason.
  * A WAITER role that deliberately grants almost nothing, so a waiter cannot authorize
    their own override even by accident.
  * TERMINALS: device nodes registered through pos.register_terminal(), so FR-POS-001's
    lifecycle has something real to revoke.
  * REASON CODES in the manager_override category, because every deliberate action here
    states one.
  * FAST PICKS for the outlet, so FR-POS-005's fast entry has something to draw.

Deliberately NOT here: step-up grants. Every check that needs one mints it for the
session it is testing, because a standing grant on the manager's session would make "the
override required RECENT authentication" untestable — the same lesson as M3-C's presence
and M3-B's station threshold.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "m1a"))

from pg import run  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "m3c_fixtures", HERE.parent / "m3c" / "fixtures.py")
m3c = importlib.util.module_from_spec(_spec)
sys.modules["m3c_fixtures"] = m3c
_spec.loader.exec_module(m3c)

m3b, m3a, m2c, m2b, m2a = m3c.m3b, m3c.m3a, m3c.m2c, m3c.m2b, m3c.m2a

TENANT = m3c.TENANT
OUTLET_H1 = m3c.OUTLET_H1
OUTLET_H2 = m3c.OUTLET_H2
USER = m3c.USER                      # the waiter requests route to
USER_WAITER_B = m3c.USER_WAITER_B    # a second waiter, for handover
USER_SUPERVISOR = m3c.USER_SUPERVISOR
TABLE_ONE = m3c.TABLE_ONE
TABLE_TWO = m3c.TABLE_TWO

CTX = dict(tenant=TENANT, outlet=OUTLET_H1)
APP = os.environ["M1A_APP_DSN"]
ADMIN = os.environ["M1A_ADMIN_DSN"]

ROLE_MANAGER = "3333d001-0000-4000-8000-0000000d0001"
ROLE_WAITER = "3333d002-0000-4000-8000-0000000d0002"
USER_MANAGER = "3333d003-0000-4000-8000-0000000d0003"
DEVICE_HANDHELD = "3333d004-0000-4000-8000-0000000d0004"
DEVICE_SPARE = "3333d005-0000-4000-8000-0000000d0005"

# What the FIXTURE grants. The suite reads what the SYSTEM registered out of the catalog
# and compares, so these two facts cannot quietly become one.
MANAGER_ACTIONS = ("order.void", "order.amend", "terminal.revoke",
                   "session.close_with_exception")
WAITER_ACTIONS = ("order.view", "session.resume")


def _fail(label: str, res) -> None:
    if not res.ok:
        raise RuntimeError(f"m3d fixture {label} failed: {res.err}")


def seed() -> None:
    m3c.seed()
    _seed_roles()
    _seed_terminals()
    _seed_reason_codes()
    _seed_fast_picks()


def _seed_roles() -> None:
    manager_actions = ",\n".join(
        f"('{TENANT}', '{ROLE_MANAGER}', '{code}')" for code in MANAGER_ACTIONS)
    waiter_actions = ",\n".join(
        f"('{TENANT}', '{ROLE_WAITER}', '{code}')" for code in WAITER_ACTIONS)
    res = run(APP, f"""
        INSERT INTO identity.role (id, tenant_id, role_code, display_name, status)
        VALUES ('{ROLE_MANAGER}', '{TENANT}', 'M3D_MANAGER', 'Floor manager', 'active'),
               ('{ROLE_WAITER}', '{TENANT}', 'M3D_WAITER', 'Waiter', 'active')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO identity.user_account
            (id, tenant_id, staff_number, display_name, status)
        VALUES ('{USER_MANAGER}', '{TENANT}', 'M3D-MGR-1', 'Meron Manager', 'active')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO identity.role_action (tenant_id, role_id, action_code)
        VALUES {manager_actions}
        ON CONFLICT DO NOTHING;

        INSERT INTO identity.role_action (tenant_id, role_id, action_code)
        VALUES {waiter_actions}
        ON CONFLICT DO NOTHING;

        INSERT INTO identity.membership
            (id, tenant_id, outlet_id, user_account_id, role_id, status)
        SELECT '3333d006-0000-4000-8000-0000000d0006', '{TENANT}', '{OUTLET_H1}',
               '{USER_MANAGER}', '{ROLE_MANAGER}', 'active'
         WHERE NOT EXISTS (SELECT 1 FROM identity.membership
                            WHERE tenant_id = '{TENANT}' AND user_account_id = '{USER_MANAGER}'
                              AND role_id = '{ROLE_MANAGER}');

        INSERT INTO identity.membership
            (id, tenant_id, outlet_id, user_account_id, role_id, status)
        SELECT '3333d007-0000-4000-8000-0000000d0007', '{TENANT}', '{OUTLET_H1}',
               '{USER}', '{ROLE_WAITER}', 'active'
         WHERE NOT EXISTS (SELECT 1 FROM identity.membership
                            WHERE tenant_id = '{TENANT}' AND user_account_id = '{USER}'
                              AND role_id = '{ROLE_WAITER}');

        INSERT INTO identity.membership
            (id, tenant_id, outlet_id, user_account_id, role_id, status)
        SELECT '3333d008-0000-4000-8000-0000000d0008', '{TENANT}', '{OUTLET_H1}',
               '{USER_WAITER_B}', '{ROLE_WAITER}', 'active'
         WHERE NOT EXISTS (SELECT 1 FROM identity.membership
                            WHERE tenant_id = '{TENANT}' AND user_account_id = '{USER_WAITER_B}'
                              AND role_id = '{ROLE_WAITER}');
    """, **CTX)
    _fail("staff roles", res)


def _seed_terminals() -> None:
    res = run(APP, f"""
        INSERT INTO org.org_node
            (id, tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{DEVICE_HANDHELD}', '{TENANT}', '{OUTLET_H1}', 'device',
                'M3D-DEV-1', 'Handheld one'),
               ('{DEVICE_SPARE}', '{TENANT}', '{OUTLET_H1}', 'device',
                'M3D-DEV-2', 'Handheld two')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO org.device_registration
            (device_id, tenant_id, outlet_id, registration_code)
        VALUES ('{DEVICE_HANDHELD}', '{TENANT}', '{OUTLET_H1}', 'M3D-REG-1'),
               ('{DEVICE_SPARE}', '{TENANT}', '{OUTLET_H1}', 'M3D-REG-2')
        ON CONFLICT (device_id) DO NOTHING;
    """, **CTX)
    _fail("device nodes", res)

    # Registered through the delivered function, not by INSERT. A fixture that wrote the
    # row itself would prove the table accepts rows and nothing about FR-POS-001.
    res = run(APP, f"""
        SELECT pos.register_terminal('{TENANT}', '{OUTLET_H1}', '{DEVICE_HANDHELD}',
                                     'waiter_handheld', '{USER_MANAGER}')
        WHERE NOT EXISTS (SELECT 1 FROM pos.terminal WHERE device_id = '{DEVICE_HANDHELD}');
    """, **CTX)
    _fail("terminal registration", res)


def _seed_reason_codes() -> None:
    res = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{OUTLET_H1}', false);
        INSERT INTO config.reason_code (tenant_id, category, code, status)
        VALUES ('{TENANT}', 'manager_override', 'M3D_SUPERVISOR_APPROVED', 'active'),
               ('{TENANT}', 'manager_override', 'M3D_TERMINAL_COMPROMISED', 'active')
        ON CONFLICT (tenant_id, category, code) DO NOTHING;
    """, tx=True)
    _fail("override reason codes", res)


def _seed_fast_picks() -> None:
    res = run(APP, f"""
        INSERT INTO pos.fast_pick (tenant_id, outlet_id, user_account_id, item_id, position)
        SELECT * FROM (
            SELECT '{TENANT}'::uuid, '{OUTLET_H1}'::uuid, NULL::uuid, i.id,
                   (row_number() OVER (ORDER BY i.item_code))::integer
            FROM menu.sellable_item i
            WHERE i.tenant_id = '{TENANT}' AND i.status = 'active'
            ORDER BY i.item_code
            LIMIT 4
        ) AS picks
        ON CONFLICT DO NOTHING;
    """, **CTX)
    _fail("fast picks", res)


# ---------------------------------------------------------------------------
# Helpers the suite and the journeys both use
# ---------------------------------------------------------------------------

def staff_session(user_id: str = USER) -> tuple[str, str]:
    """A live strong session for one member of staff: (session_id, bearer token).

    The token is `tenant.outlet.secret`, the shape M1-D's db.withSession() parses, and
    only its sha256 reaches the database (FR-SEC-007).
    """
    secret = os.urandom(16).hex()
    token = f"{TENANT}.{OUTLET_H1}.{secret}"
    res = run(APP, f"""
        INSERT INTO identity.session
            (tenant_id, outlet_id, user_account_id, token_digest, established_with,
             expires_at)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{user_id}',
                sha256(convert_to('{token}', 'UTF8')), 'strong', now() + interval '1 hour')
        RETURNING id;
    """, **CTX)
    _fail("staff session", res)
    return (res.scalar or "").strip(), token


def step_up(session_id: str, action_code: str, age_seconds: int = 0) -> str:
    """Recent stronger authentication on ONE session, for ONE action.

    age_seconds backdates the grant so the recency window can be tested without waiting
    five minutes. It writes what an authentication would have written and nothing else.
    """
    res = run(APP, f"""
        INSERT INTO identity.step_up_grant
            (tenant_id, outlet_id, session_id, action_code, granted_at)
        VALUES ('{TENANT}', '{OUTLET_H1}', '{session_id}', '{action_code}',
                now() - interval '{age_seconds} seconds')
        RETURNING id;
    """, **CTX)
    _fail("step-up grant", res)
    return (res.scalar or "").strip()


def reason_code(code: str = "M3D_SUPERVISOR_APPROVED") -> str:
    res = run(APP, f"""
        SELECT id FROM config.reason_code
         WHERE tenant_id = '{TENANT}' AND category = 'manager_override' AND code = '{code}';
    """, **CTX)
    _fail("reason code lookup", res)
    return (res.scalar or "").strip()


def a_seated_guest(table: str = TABLE_ONE, locale: str = "en") -> dict:
    return m3c.a_seated_guest(table=table, locale=locale)


def a_seated_guest_with_credential(table: str = TABLE_ONE, locale: str = "en") -> dict:
    return m3c.a_seated_guest_with_credential(table=table, locale=locale)


def assign_table_owner(table_session_id: str, user_id: str = USER) -> None:
    m3b.assign_table_owner(table_session_id, user_id)
