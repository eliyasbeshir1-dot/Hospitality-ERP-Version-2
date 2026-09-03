"""What M4-B needs that no earlier slice built, and nothing it can borrow.

THE TABLES ARE ITS OWN. M4-A discovered why: a later fixture that opened a fresh
occupancy on a shared table closed the one an earlier probe's QR code pointed at, and the
failure surfaced as a browser timing out rather than as a collision. Two tables here, two
tables there, and neither suite can reach into the other's evening.

THE PEOPLE ARE ITS OWN TOO, and for the reason M4-A's fixture records about ITS outsider.
NC-M4-004 is maker-checker, and the whole of it is that the approver is not the actor. If
this suite borrowed M4-A's cashier manager and widened their role to cover refunds, then
every M4-A check resting on what that person may NOT do would become quietly weaker, and
the forward run would never show it. So: a cashier who takes money and may not approve a
refund, and a manager who may approve one and never touches a drawer.

THE ADAPTERS ARE INSTALLED FROM CONFIGURATION, not inserted. FR-CFG-001C says the guided
setup decides which payment methods are permitted and that those settings drive a real
bill, so this fixture publishes an approved payment_method configuration version and lets
payments.install_adapters_from_configuration() build the registry from it. A fixture that
wrote the adapter rows directly would have proved the registry works and left the
requirement's last clause — "and those settings drive a real bill" — untested.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "m1a"))

from pg import ProbeFailed, run  # noqa: E402

# LOADED BY PATH, UNDER ITS OWN NAME. Every slice's fixture module is called "fixtures",
# so an ordinary import here binds whichever one is earliest on sys.path — which, in a
# suite whose own module is also called fixtures, is this file importing itself. M4-A hit
# the same wall against M3-D and solved it the same way; the name m4b_parent_fixtures
# exists only so that the two modules can both be resident.
_spec = importlib.util.spec_from_file_location(
    "m4a_fixtures", HERE.parent / "m4a" / "fixtures.py")
m4a = importlib.util.module_from_spec(_spec)
sys.modules["m4a_fixtures"] = m4a
_spec.loader.exec_module(m4a)

TENANT = m4a.TENANT
OUTLET_H1 = m4a.OUTLET_H1
USER = m4a.USER
USER_MANAGER = m4a.USER_MANAGER

ITEM_DORO = m4a.ITEM_DORO
ITEM_TIBS = m4a.ITEM_TIBS
VARIANT_DORO_FULL = m4a.VARIANT_DORO_FULL      # 32000 minor
VARIANT_TIBS_ONE = m4a.VARIANT_TIBS_ONE        # 26000 minor

CTX = dict(tenant=TENANT, outlet=OUTLET_H1)
APP = os.environ["M1A_APP_DSN"]
ADMIN = os.environ["M1A_ADMIN_DSN"]

# --- identities of this slice's own furniture ------------------------------
PAY_TABLE       = "4444b101-0000-4000-8000-0000000b0101"
CASH_TABLE      = "4444b102-0000-4000-8000-0000000b0102"
TERMINAL_DEVICE = "4444b103-0000-4000-8000-0000000b0103"

ROLE_CASHIER        = "4444b201-0000-4000-8000-0000000b0201"
ROLE_FINANCE_MANAGER = "4444b202-0000-4000-8000-0000000b0202"
USER_CASHIER         = "4444b203-0000-4000-8000-0000000b0203"
USER_FINANCE_MANAGER = "4444b204-0000-4000-8000-0000000b0204"
MEMBERSHIP_CASHIER   = "4444b205-0000-4000-8000-0000000b0205"
MEMBERSHIP_MANAGER   = "4444b206-0000-4000-8000-0000000b0206"

PAYMENT_CONFIG_VERSION = "4444b301-0000-4000-8000-0000000b0301"
CASH_POLICY   = "4444b302-0000-4000-8000-0000000b0302"
REFUND_POLICY = "4444b303-0000-4000-8000-0000000b0303"

# FR-CFG-001C's permitted methods. The two direct-provider adapters are DELIBERATELY
# absent from this list: they exist in the registry and are inactive, which is what lets
# the suite prove that activating one still cannot make it live.
PERMITTED_METHODS = ("cash", "external_terminal", "telebirr_proof", "cbe_birr_proof")

# FR-PAY-009's threshold and FR-CSH-008's two. Chosen so that the suite can sit either
# side of each: a refund below 5000 needs nobody, one at or above it needs a manager.
REFUND_APPROVAL_THRESHOLD_MINOR = 5000
ACCEPTABLE_DIFFERENCE_MINOR = 500
UNUSUAL_MOVEMENT_MINOR = 20000

# The actions a manager may approve. Registered as governed actions requiring step-up,
# because pos.approve_override() refuses to record an approval for an action that does not
# require stronger authentication — an override nobody needed is an audit row that means
# nothing.
MANAGER_ACTIONS = ("payment.refund", "cash.shift.verify")

# Ethiopian notes and coins, in minor units. A real denomination set, because a count
# tallied against invented money would prove the arithmetic and not the count — and it
# reaches down to one santim, because a bill total is whatever tax and a service charge
# make it and a drawer that could only be counted in round birr would be a fixture
# choosing its own arithmetic.
DENOMINATIONS = (20000, 10000, 5000, 1000, 500, 100, 50, 25, 10, 5, 1)


def _fail(label: str, res) -> None:
    if not res.ok:
        raise ProbeFailed(f"m4b fixture: {label}", res.err)


def seed() -> None:
    m4a.seed()
    _seed_own_tables()
    _seed_terminal()
    _seed_people()
    _seed_payment_configuration()
    _seed_cash_and_refund_policy()
    _seed_reason_codes()
    _install_adapters()
    _retire_a_leftover_shift()


def _seed_own_tables() -> None:
    res = run(APP, f"""
        INSERT INTO org.org_node
            (id, tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{PAY_TABLE}', '{TENANT}', '{OUTLET_H1}', 'dining_table',
                'M4B-PAY', 'Table the bill is paid at'),
               ('{CASH_TABLE}', '{TENANT}', '{OUTLET_H1}', 'dining_table',
                'M4B-CASH', 'Table the drawer is counted against')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO service.table_profile
            (tenant_id, table_node_id, outlet_id, seat_count)
        VALUES ('{TENANT}', '{PAY_TABLE}', '{OUTLET_H1}', 4),
               ('{TENANT}', '{CASH_TABLE}', '{OUTLET_H1}', 4)
        ON CONFLICT DO NOTHING;
    """, tx=True, **CTX)
    _fail("m4b tables", res)


def _seed_terminal() -> None:
    """The till FR-CSH-001 assigns a drawer to. M3-D's pos.terminal, not a second one.

    Registered through pos.register_terminal() rather than inserted, for the reason M3-D's
    own fixture gives: a fixture that wrote the row itself would prove the table accepts
    rows and nothing about FR-POS-001. The device node and its registration come first,
    because a terminal is a registered DEVICE — M2-B learned the same lesson from the
    other side when a QR code that resolved to anything the tenant owned would have bound
    a guest to a kitchen.
    """
    res = run(APP, f"""
        INSERT INTO org.org_node
            (id, tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{TERMINAL_DEVICE}', '{TENANT}', '{OUTLET_H1}', 'device',
                'M4B-TILL-1', 'The till the drawer belongs to')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO org.device_registration
            (device_id, tenant_id, outlet_id, registration_code)
        VALUES ('{TERMINAL_DEVICE}', '{TENANT}', '{OUTLET_H1}', 'M4B-REG-1')
        ON CONFLICT (device_id) DO NOTHING;
    """, **CTX)
    _fail("m4b device node", res)

    res = run(APP, f"""
        SELECT pos.register_terminal('{TENANT}', '{OUTLET_H1}', '{TERMINAL_DEVICE}',
                                     'point_of_sale', '{USER_MANAGER}')
        WHERE NOT EXISTS (SELECT 1 FROM pos.terminal
                           WHERE device_id = '{TERMINAL_DEVICE}');
    """, **CTX)
    _fail("m4b terminal", res)


def _seed_people() -> None:
    """A cashier and a manager who are two people, with two roles, and no overlap.

    The cashier holds NO approving action at all. That is the point: NC-M4-004's red leg
    has the cashier attempt to approve their own refund, and if the cashier's role granted
    the action the refusal would come from pos.override_approval's approver-is-not-the-
    actor CHECK — which is the right refusal, but it would leave the permission half
    untested. Both halves have to be able to fail on their own.
    """
    actions = ",\n".join(
        f"('{TENANT}', '{ROLE_FINANCE_MANAGER}', '{code}')" for code in MANAGER_ACTIONS)
    governed = ",\n".join(
        f"('{TENANT}', '{code}', 'strong', true, interval '5 minutes', 'M4')"
        for code in MANAGER_ACTIONS)
    res = run(APP, f"""
        INSERT INTO identity.governed_action
            (tenant_id, action_code, minimum_strength, step_up_required, step_up_max_age,
             governed_from_gate)
        VALUES {governed}
        ON CONFLICT DO NOTHING;

        INSERT INTO identity.role (id, tenant_id, role_code, display_name, status)
        VALUES ('{ROLE_CASHIER}', '{TENANT}', 'M4B_CASHIER', 'Cashier', 'active'),
               ('{ROLE_FINANCE_MANAGER}', '{TENANT}', 'M4B_FINANCE_MANAGER',
                'Finance manager', 'active')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO identity.user_account
            (id, tenant_id, staff_number, display_name, status)
        VALUES ('{USER_CASHIER}', '{TENANT}', 'M4B-CSH', 'Bethlehem Cashier', 'active'),
               ('{USER_FINANCE_MANAGER}', '{TENANT}', 'M4B-FIN', 'Dawit Finance', 'active')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO identity.role_action (tenant_id, role_id, action_code)
        VALUES {actions}
        ON CONFLICT DO NOTHING;

        INSERT INTO identity.membership
            (id, tenant_id, outlet_id, user_account_id, role_id, status)
        SELECT '{MEMBERSHIP_CASHIER}', '{TENANT}', '{OUTLET_H1}',
               '{USER_CASHIER}', '{ROLE_CASHIER}', 'active'
         WHERE NOT EXISTS (SELECT 1 FROM identity.membership
                            WHERE tenant_id = '{TENANT}'
                              AND user_account_id = '{USER_CASHIER}');

        INSERT INTO identity.membership
            (id, tenant_id, outlet_id, user_account_id, role_id, status)
        SELECT '{MEMBERSHIP_MANAGER}', '{TENANT}', '{OUTLET_H1}',
               '{USER_FINANCE_MANAGER}', '{ROLE_FINANCE_MANAGER}', 'active'
         WHERE NOT EXISTS (SELECT 1 FROM identity.membership
                            WHERE tenant_id = '{TENANT}'
                              AND user_account_id = '{USER_FINANCE_MANAGER}');
    """, **CTX)
    _fail("m4b people", res)


def _seed_payment_configuration() -> None:
    """FR-CFG-001C's fourth setting, published the way setup would publish it.

    An APPROVED configuration version under category 'payment_method', with the permitted
    methods in its payload. payments.install_adapters_from_configuration() then builds the
    registry from it, payments.create_intent() takes an intent's permitted providers from
    the registry, and one of them settles a real bill. That chain is what the requirement's
    last clause asks for, and it is why this is a configuration row rather than six INSERTs
    into the adapter table.
    """
    permitted = ", ".join(f'"{m}"' for m in PERMITTED_METHODS)
    res = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{OUTLET_H1}', false);
        INSERT INTO config.configuration_version
            (id, tenant_id, outlet_id, scope_kind, scope_node_id, category, version,
             payload, effective_from, actor_id, approved_by_id, approved_at)
        SELECT '{PAYMENT_CONFIG_VERSION}', '{TENANT}', '{OUTLET_H1}', 'outlet',
               '{OUTLET_H1}', 'payment_method', 1,
               '{{"permitted": [{permitted}]}}'::jsonb,
               now() - interval '1 hour', '{USER_MANAGER}', '{USER_MANAGER}',
               now() - interval '1 hour'
         WHERE NOT EXISTS (SELECT 1 FROM config.configuration_version
                            WHERE id = '{PAYMENT_CONFIG_VERSION}');
    """, tx=True)
    _fail("payment_method configuration", res)


def _seed_cash_and_refund_policy() -> None:
    """The three thresholds, in config.policy where every other threshold in this system
    lives. None of them is a literal in a migration: FR-CSH-008's "excessive" and
    FR-PAY-009's "approval threshold" are operator decisions, and a number compiled into
    the database would be a decision this repository made on their behalf."""
    res = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{OUTLET_H1}', false);
        INSERT INTO config.policy
            (id, tenant_id, outlet_id, category, version, payload, effective_from,
             actor_id, approved_by_id, approved_at)
        SELECT '{CASH_POLICY}', '{TENANT}', '{OUTLET_H1}', 'cash', 1,
               '{{"acceptable_difference_minor": {ACCEPTABLE_DIFFERENCE_MINOR},
                  "unusual_movement_minor": {UNUSUAL_MOVEMENT_MINOR}}}'::jsonb,
               now() - interval '1 hour', '{USER_MANAGER}', '{USER_MANAGER}',
               now() - interval '1 hour'
         WHERE NOT EXISTS (SELECT 1 FROM config.policy WHERE id = '{CASH_POLICY}');

        INSERT INTO config.policy
            (id, tenant_id, outlet_id, category, version, payload, effective_from,
             actor_id, approved_by_id, approved_at)
        SELECT '{REFUND_POLICY}', '{TENANT}', '{OUTLET_H1}', 'refund', 1,
               '{{"approval_threshold_minor": {REFUND_APPROVAL_THRESHOLD_MINOR}}}'::jsonb,
               now() - interval '1 hour', '{USER_MANAGER}', '{USER_MANAGER}',
               now() - interval '1 hour'
         WHERE NOT EXISTS (SELECT 1 FROM config.policy WHERE id = '{REFUND_POLICY}');
    """, tx=True)
    _fail("cash and refund policy", res)


def _seed_reason_codes() -> None:
    """English labels only. M1-C requires every reason code to carry one and also requires
    that M1 seeds the STRUCTURE and M2 the content; M3-D's fixture cost two findings by
    getting each half wrong in turn."""
    res = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{OUTLET_H1}', false);
        INSERT INTO config.reason_code (tenant_id, category, code, status)
        VALUES ('{TENANT}', 'refund', 'M4B_GUEST_REFUNDED', 'active'),
               ('{TENANT}', 'manager_override', 'M4B_REFUND_AUTHORIZED', 'active'),
               ('{TENANT}', 'payment_reversal', 'M4B_TIP_RETURNED', 'active'),
               ('{TENANT}', 'manager_override', 'M4B_DRAWER_RECOUNTED', 'active')
        ON CONFLICT (tenant_id, category, code) DO NOTHING;

        INSERT INTO config.reason_code_label (tenant_id, reason_code_id, locale, label)
        SELECT rc.tenant_id, rc.id, 'en', v.label
        FROM config.reason_code rc
        JOIN (VALUES
            ('M4B_GUEST_REFUNDED', 'The guest was refunded'),
            ('M4B_REFUND_AUTHORIZED', 'A manager authorized this refund'),
            ('M4B_TIP_RETURNED', 'The tip was returned at the guest''s request'),
            ('M4B_DRAWER_RECOUNTED', 'The drawer was reopened and counted again')
        ) AS v(code, label) ON v.code = rc.code
        WHERE rc.tenant_id = '{TENANT}'
        ON CONFLICT DO NOTHING;
    """, tx=True)
    _fail("m4b reason codes", res)


MIGRATOR = os.environ["M1A_MIGRATOR_DSN"]


def _install_adapters() -> None:
    """Setup installs the registry, as the role that may.

    Through the MIGRATOR rather than the application, because the application holds no
    write grant on payments.payment_adapter and should not: which adapters an outlet runs
    is a configuration decision, and 0019 drew the same line for service charges and tip
    suggestions. A fixture that reached for a wider role to make this work would be
    proving that a superuser can write a table.
    """
    res = run(MIGRATOR, f"""
        SELECT payments.install_adapters_from_configuration('{TENANT}', '{OUTLET_H1}');
    """, tx=True, **CTX)
    _fail("adapter installation", res)


# ---------------------------------------------------------------------------
# Helpers the suite uses
# ---------------------------------------------------------------------------

def staff_session(user_id: str = USER) -> tuple[str, str]:
    return m4a.staff_session(user_id)


def step_up(session_id: str, action_code: str, age_seconds: int = 0) -> str:
    return m4a.step_up(session_id, action_code, age_seconds)


def reason_code(code: str) -> str:
    """A reason code by CODE, whatever its category.

    M3-D's helper filters on category 'manager_override', which was every reason code it
    had. M4-B's refunds carry category 'refund' and its tip reversals 'payment_reversal',
    so a lookup that assumed the category came back empty and the empty string was then
    cast to uuid — the failure surfaced three sections later as a route returning 400.
    A code is unique per tenant per category and the codes here are distinct, so asking by
    code alone is both correct and the question the caller actually has.
    """
    res = run(APP, f"""
        SELECT id FROM config.reason_code
         WHERE tenant_id = '{TENANT}' AND code = '{code}';""", **CTX)
    _fail(f"reason code lookup: {code}", res)
    found = (res.scalar or "").strip()
    if not found:
        raise ProbeFailed("m4b fixture: reason_code",
                          f"no reason code {code!r} for this tenant. An empty id here "
                          f"becomes an invalid-uuid error somewhere else entirely")
    return found


def tally_for(total_minor: int) -> list[dict]:
    """A denomination breakdown that adds to exactly total_minor.

    Greedy over the real note and coin set, and it asserts its own arithmetic before
    returning: a tally that did not add up would make cash.assert_tally_equals_the_count()
    fire, and the suite would report a fixture defect as a database one.
    """
    remaining = total_minor
    tally: list[dict] = []
    for note in DENOMINATIONS:
        pieces, remaining = divmod(remaining, note)
        if pieces:
            tally.append({"denominationMinor": note, "pieceCount": pieces})
    if remaining != 0:
        raise ProbeFailed(
            "m4b fixture: tally_for",
            f"{total_minor} cannot be made from {DENOMINATIONS}; {remaining} left over. "
            f"A count the notes cannot express is a fixture defect, not a database one")
    return tally


def _retire_a_leftover_shift() -> None:
    """Leave the till with no live drawer on it.

    A partial run that stopped between opening a shift and finalizing it leaves one open,
    and the partial unique index then refuses the next run's shift with a bare 23505.
    That index is doing exactly its job — two live drawers on one till is two people
    counting the same notes — so the answer is for seeding to establish a known starting
    state rather than for the suite to tolerate an unknown one. CI always starts from an
    empty database and never reaches this; a developer re-running locally does.
    """
    # SUBMITTED, not deleted. The first version of this deleted the leftover shift and its
    # transitions, and cash.refuse_transition_mutation() refused — correctly: a drawer's
    # history is how a reopened shift is told apart from one that was never closed, and
    # erasing it is how the second is made to look like the first. Submission is a legal
    # edge that needs no verifier, and it takes the drawer out of the live set the partial
    # unique index guards without pretending the evening never happened.
    res = run(APP, f"""
        SELECT cash.transition_shift('{TENANT}', s.id, 'submitted', '{USER_CASHIER}')
          FROM cash.shift s
         WHERE s.tenant_id = '{TENANT}' AND s.terminal_device_id = '{TERMINAL_DEVICE}'
           AND s.state IN ('open', 'reopened');
    """, tx=True, **CTX)
    _fail("retiring a leftover shift", res)
