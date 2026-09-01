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
# NOT M3-C's USER_WAITER_B. That person is M3-C's OUTSIDER: two of its checks — a deep
# link refused and a notification centre that answers nobody — rest on their having no
# membership at this outlet. M3-D borrowed them as the handover recipient and gave them
# one, which made both M3-C checks fail whenever M3-D had run first. The forward order
# never showed it; the reversed run FR-TST-020 requires did.
#
# A handover needs a second waiter who IS a member, and an outsider is the absence of
# exactly that. They cannot be the same person, so they are not.
USER_WAITER_TWO = "3333d009-0000-4000-8000-0000000d0009"   # the handover recipient
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
    _seed_status_wordings()


# What a guest is told when their order reaches a state, in the three launch locales
# (FR-I18N-011). The English is the string M3-A and M3-B already write into the
# projection, character for character: the fallback and the source have to be the same
# sentence or "fell back to English" would be a different message rather than the same
# one in another language.
#
# Amharic and Arabic are seeded here rather than by a migration for the reason 0016
# states: menu.translation records that a HUMAN reviewed and approved a string, and
# menu.enforce_translation_review() refuses an approval nobody reviewed. FR-NOT-003's
# templates arrive the same way, through the same store, reviewed by the same named user.
STATUS_WORDINGS = {
    "submitted": {
        "id": "3333d0a1-0000-4000-8000-0000000da001",
        "en": "Your order was received.",
        "am": "\u1275\u12d5\u12db\u12dd\u12ee \u12f0\u122d\u1236\u1293\u120d\u1362",
        "ar": "\u062a\u0645 \u0627\u0633\u062a\u0644\u0627\u0645 \u0637\u0644\u0628\u0643.",
    },
    "accepted": {
        "id": "3333d0a2-0000-4000-8000-0000000da002",
        "en": "Your order was confirmed.",
        "am": "\u1275\u12d5\u12db\u12dd\u12ee \u1270\u1228\u130b\u130d\u1327\u120d\u1362",
        "ar": "\u062a\u0645 \u062a\u0623\u0643\u064a\u062f \u0637\u0644\u0628\u0643.",
    },
    "rejected": {
        "id": "3333d0a3-0000-4000-8000-0000000da003",
        "en": "Your order could not be confirmed.",
        "am": "\u1275\u12d5\u12db\u12dd\u12ee \u120a\u1228\u130b\u1308\u1325 \u12a0\u120d\u127b\u1208\u121d\u1362",
        "ar": "\u062a\u0639\u0630\u0651\u0631 \u062a\u0623\u0643\u064a\u062f \u0637\u0644\u0628\u0643.",
    },
    "amended": {
        "id": "3333d0a4-0000-4000-8000-0000000da004",
        "en": "Your order was changed.",
        "am": "\u1275\u12d5\u12db\u12dd\u12ee \u1270\u1235\u1270\u12ab\u12ad\u120b\u120d\u1362",
        "ar": "\u062a\u0645 \u062a\u0639\u062f\u064a\u0644 \u0637\u0644\u0628\u0643.",
    },
    "cancelled": {
        "id": "3333d0a5-0000-4000-8000-0000000da005",
        "en": "Your order was cancelled.",
        "am": "\u1275\u12d5\u12db\u12dd\u12ee \u1270\u1230\u122d\u12df\u120d\u1362",
        "ar": "\u062a\u0645 \u0625\u0644\u063a\u0627\u0621 \u0637\u0644\u0628\u0643.",
    },
    "allergy_declared": {
        "id": "3333d0a6-0000-4000-8000-0000000da006",
        "en": "An allergy was recorded for this order.",
        "am": "\u1208\u12da\u1205 \u1275\u12d5\u12db\u12dd \u12e8\u12a0\u1208\u122d\u1305 \u1218\u1228\u1303 \u1270\u1218\u12dd\u130b\u1265\u1362",
        "ar": "\u062a\u0645 \u062a\u0633\u062c\u064a\u0644 \u062d\u0633\u0627\u0633\u064a\u0629 \u0644\u0647\u0630\u0627 \u0627\u0644\u0637\u0644\u0628.",
    },
    "note_added": {
        "id": "3333d0a7-0000-4000-8000-0000000da007",
        "en": "Your note was added to the order.",
        "am": "\u121b\u1235\u1273\u12c8\u123b \u12c8\u12f0 \u1275\u12d5\u12db\u12d1 \u1270\u1328\u121d\u122f\u120d\u1362",
        "ar": "\u062a\u0645\u062a \u0625\u0636\u0627\u0641\u0629 \u0645\u0644\u0627\u062d\u0638\u062a\u0643 \u0625\u0644\u0649 \u0627\u0644\u0637\u0644\u0628.",
    },
    "station_preparing": {
        "id": "3333d0a8-0000-4000-8000-0000000da008",
        "en": "Your order is being prepared.",
        "am": "\u1275\u12d5\u12db\u12dd\u12ee \u1260\u1218\u12d8\u130b\u1300\u1275 \u120b\u12ed \u1290\u12cd\u1362",
        "ar": "\u064a\u062c\u0631\u064a \u062a\u062d\u0636\u064a\u0631 \u0637\u0644\u0628\u0643.",
    },
    "items_served": {
        "id": "3333d0a9-0000-4000-8000-0000000da009",
        "en": "Your order was served.",
        "am": "\u1275\u12d5\u12db\u12dd\u12ee \u1240\u122d\u1265\u12eb\u120d\u1362",
        "ar": "\u062a\u0645 \u062a\u0642\u062f\u064a\u0645 \u0637\u0644\u0628\u0643.",
    },
}


def _seed_status_wordings() -> None:
    """FR-NOT-012's customer half: the approved wording for each status, per locale.

    The identity rows go in as the application, which holds no INSERT on
    notify.status_wording — so they go in as the administrator, exactly as M3-C's
    notification templates do, because approved customer-facing wording is configuration
    a tenant's people sign off, not something a running surface writes.
    """
    wordings = ",\n".join(
        f"('{w['id']}', '{TENANT}', '{kind}', $src${w['en']}$src$)"
        for kind, w in STATUS_WORDINGS.items())
    translations = ",\n".join(
        f"('{TENANT}', 'order_status_wording', '{w['id']}', 'body', '{locale}', "
        f"$t${w[locale]}$t$, 'approved', 'human', '{USER}', now())"
        for w in STATUS_WORDINGS.values()
        for locale in ("am", "ar"))
    res = run(ADMIN, f"""
        INSERT INTO menu.translatable_field
            (entity, field_name, required_for_publication, safety_critical)
        VALUES ('order_status_wording', 'body', false, false)
        ON CONFLICT (entity, field_name) DO NOTHING;

        INSERT INTO notify.status_wording (id, tenant_id, event_kind, source_text)
        VALUES {wordings}
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO menu.translation
            (tenant_id, entity, entity_id, field_name, locale, translated_text, state,
             provenance, reviewed_by_user_id, approved_at)
        VALUES {translations}
        ON CONFLICT (tenant_id, entity, entity_id, field_name, locale) DO NOTHING;
    """)
    _fail("status wordings", res)


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
        VALUES ('{USER_MANAGER}', '{TENANT}', 'M3D-MGR-1', 'Meron Manager', 'active'),
               ('{USER_WAITER_TWO}', '{TENANT}', 'M3D-WTR-2', 'Yonas Waiter', 'active')
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
               '{USER_WAITER_TWO}', '{ROLE_WAITER}', 'active'
         WHERE NOT EXISTS (SELECT 1 FROM identity.membership
                            WHERE tenant_id = '{TENANT}' AND user_account_id = '{USER_WAITER_TWO}'
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
    """The reasons a deliberate action states, WITH their labels.

    ENGLISH ONLY, and both halves of that were learned from the reversed run.

    M3-D's first draft seeded two codes with no label at all, and M1-C asserts that every
    code in the tenant carries at least an English one — so M1-C failed whenever M3-D had
    run before it. The second draft added Amharic and Arabic as well, and M1-C failed
    again on the opposite check: M1 deliberately seeds the reason-code STRUCTURE and
    leaves the content to M2, and it asserts that too.

    Both are the same lesson. A fixture that adds tenant data has to leave the tenant in
    a state every earlier gate still holds true of, and the forward order never shows it
    because the earlier gate has already run. That is the whole content of FR-TST-020,
    and this fixture cost two of its findings.
    """
    res = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{OUTLET_H1}', false);
        INSERT INTO config.reason_code (tenant_id, category, code, status)
        VALUES ('{TENANT}', 'manager_override', 'M3D_SUPERVISOR_APPROVED', 'active'),
               ('{TENANT}', 'manager_override', 'M3D_TERMINAL_COMPROMISED', 'active')
        ON CONFLICT (tenant_id, category, code) DO NOTHING;

        INSERT INTO config.reason_code_label (tenant_id, reason_code_id, locale, label)
        SELECT rc.tenant_id, rc.id, 'en', v.label
        FROM config.reason_code rc
        JOIN (VALUES
            ('M3D_SUPERVISOR_APPROVED', 'Approved by a supervisor'),
            ('M3D_TERMINAL_COMPROMISED', 'The terminal was compromised')
        ) AS v(code, label) ON v.code = rc.code
        WHERE rc.tenant_id = '{TENANT}' AND rc.category = 'manager_override'
        ON CONFLICT DO NOTHING;
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

def register_spare_terminal() -> str:
    """A device node registered for THIS RUN, so the revocation checks can revoke it.

    Revoking is permanent by design — that is the requirement — so a check that revoked a
    fixture device would pass on a fresh database and fail on every re-run. The same
    re-runnability defect M3-C found in its idempotency keys, wearing different clothes.
    """
    # A well-formed uuid: 8-4-4-4-12. The first attempt built '3333d1' + 4 hex digits
    # for the first group, which is ten characters and not a uuid at all.
    device = f"3333d1{os.urandom(1).hex()}-0000-4000-8000-{os.urandom(6).hex()}"
    res = run(APP, f"""
        INSERT INTO org.org_node
            (id, tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{device}', '{TENANT}', '{OUTLET_H1}', 'device',
                'M3D-SPARE-{device[-6:]}', 'Spare handheld');

        INSERT INTO org.device_registration
            (device_id, tenant_id, outlet_id, registration_code)
        VALUES ('{device}', '{TENANT}', '{OUTLET_H1}', 'M3D-SREG-{device[-6:]}');

        SELECT pos.register_terminal('{TENANT}', '{OUTLET_H1}', '{device}',
                                     'point_of_sale', '{USER_MANAGER}');
    """, tx=True, **CTX)
    _fail("spare terminal", res)
    return device


def a_free_table() -> str:
    """A dining table with no occupancy, created for THIS caller.

    GJ-04 moves a party to another table, and service.move_table_session() refuses a
    target that already has an open occupancy — correctly, because two parties at one
    table is what FR-TAB-002 exists to prevent. By the time the journeys have run, every
    seeded table is occupied, so the journey would be testing that refusal instead of the
    move. A restaurant has empty tables; this makes one.
    """
    node = f"3333b1{os.urandom(1).hex()}-0000-4000-8000-{os.urandom(6).hex()}"
    # A node of kind 'dining_table' is not yet a table: service.table_session's foreign
    # key resolves through service.table_profile, which is what makes a node servable.
    # Creating only the node would leave the journey testing a foreign key, not a move.
    res = run(APP, f"""
        INSERT INTO org.org_node
            (id, tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{node}', '{TENANT}', '{OUTLET_H1}', 'dining_table',
                'M3D-FREE-{node[-6:]}', 'Free table {node[-4:]}');
        INSERT INTO service.table_profile
            (tenant_id, table_node_id, outlet_id, seat_count)
        VALUES ('{TENANT}', '{node}', '{OUTLET_H1}', 4);
    """, tx=True, **CTX)
    _fail("free table", res)
    return node


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
