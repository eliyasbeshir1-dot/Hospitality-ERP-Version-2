"""M3-C fixtures: a request catalog, approved templates, presence and a supervisor.

Built on M3-B's, which is built on M3-A's, and so on down to M1-A. Nothing here stubs a
service request: a request exists because a seated guest asked for something a configured
catalog offers, and it reaches somebody because the routing rules FR-SRV-002 names found
them — which is the path the requirement describes.

What this module adds that no earlier slice needed:

  * a REQUEST CATALOG with the seven types FR-SRV-001 names, each with its own SLA and
    its own deduplication window, because water and accessibility should not share either
  * APPROVED TEMPLATES in all three customer languages plus English staff templates,
    written through M2-A's approval workflow rather than beside it — draft, reviewed,
    approved, with a reviewer and a timestamp on every row
  * a SUPERVISOR who is not the person requests route to, so escalation has somewhere to
    go that is not where it came from
  * the two service-policy keys this slice reads and refuses to default: who an
    unanswered request escalates to, and who is accountable for a critical alert

Deliberately NOT here: presence. Every check that needs somebody available sets it, and
a fixture that left the whole outlet permanently available would make FR-SRV-002's
availability leg untestable — the same lesson as M3-B's station threshold.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "m1a"))

from pg import ProbeFailed, run  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "m3b_fixtures", HERE.parent / "m3b" / "fixtures.py")
m3b = importlib.util.module_from_spec(_spec)
sys.modules["m3b_fixtures"] = m3b
_spec.loader.exec_module(m3b)

m3a, m2c, m2b, m2a = m3b.m3a, m3b.m2c, m3b.m2b, m3b.m2a

TENANT = m3b.TENANT
OUTLET_H1 = m3b.OUTLET_H1
OUTLET_H2 = m3b.OUTLET_H2
USER = m3b.USER
USER_WAITER_B = m3b.USER_WAITER_B
TABLE_ONE = m3b.TABLE_ONE
TABLE_TWO = m3b.TABLE_TWO
SERVICE_POLICY = m3b.SERVICE_POLICY

CTX = dict(tenant=TENANT, outlet=OUTLET_H1)
APP = os.environ["M1A_APP_DSN"]
ADMIN = os.environ["M1A_ADMIN_DSN"]

# Identifiers this slice owns.
ROLE_ATTENDANT = "3333c001-0000-4000-8000-0000000c0001"
ROLE_SUPERVISOR = "3333c002-0000-4000-8000-0000000c0002"
USER_SUPERVISOR = "3333c003-0000-4000-8000-0000000c0003"

# FR-SRV-001's seven, with the SLA and the deduplication window each one deserves.
# 'assistance' has a long window on purpose: two taps a minute apart for help are two
# asks, and collapsing them is the failure that matters most in this list.
REQUEST_TYPES = [
    # code,           label,            sla, dedup window
    ("call_waiter",   "Call the waiter", 300,  45),
    ("water",         "Water",           300,  45),
    ("cutlery",       "Cutlery",         300,  45),
    ("assistance",    "Assistance",      120,   5),
    ("missing_item",  "A missing item",  300,  30),
    ("packaging",     "Packaging",       600,  60),
    ("bill",          "The bill",        300,  60),
]

TYPE_IDS = {code: f"3333c1{index:02d}-0000-4000-8000-0000000c1{index:03d}"
            for index, (code, _l, _s, _d) in enumerate(REQUEST_TYPES, start=1)}

# The M3 kinds this slice actually produces, with the audiences each reaches. A staff
# template for every one of them, because a missing staff template is a configuration
# defect that dead-letters rather than a silence.
TEMPLATES = {
    "EVT-SERVICE-REQUESTED": {
        "staff": "A guest has asked for something.",
        "customer": "We have your request. Someone is on their way.",
    },
    "EVT-SERVICE-ACKNOWLEDGED": {
        "staff": "A request was accepted.",
        "customer": "Your request is being handled.",
    },
    "EVT-SERVICE-COMPLETED": {
        "staff": "A request was closed.",
        "customer": "Your request is done.",
    },
    "EVT-SERVICE-ESCALATED": {
        "staff": "A request passed its deadline and was escalated.",
    },
}

TEMPLATE_IDS = {f"{event}|{audience}":
                f"3333c2{index:02d}-0000-4000-8000-0000000c2{index:03d}"
                for index, (event, audience) in enumerate(
                    ((e, a) for e in TEMPLATES for a in TEMPLATES[e]), start=1)}

# The approved bodies a guest reads. Amharic and Arabic, because FR-NOT-003 asks for
# three customer languages and FR-I18N-008 is measured on a rendered screen.
CUSTOMER_BODIES = {
    "EVT-SERVICE-REQUESTED": {
        "am": "ጥያቄዎን ተቀብለናል። አንድ ሰው በመንገድ ላይ ነው።",
        "ar": "لقد تلقينا طلبك. أحدهم في الطريق.",
    },
    "EVT-SERVICE-ACKNOWLEDGED": {
        "am": "ጥያቄዎ እየተስተናገደ ነው።",
        "ar": "طلبك قيد المعالجة.",
    },
    "EVT-SERVICE-COMPLETED": {
        "am": "ጥያቄዎ ተጠናቋል።",
        "ar": "طلبك تم إنجازه.",
    },
}

# The request-type labels in the two non-English languages, through the same approval
# workflow. A label a guest reads is a translation like any other.
TYPE_LABELS = {
    "call_waiter":  {"am": "አስተናጋጅ ይጠሩ",   "ar": "استدعاء النادل"},
    "water":        {"am": "ውሃ",            "ar": "ماء"},
    "cutlery":      {"am": "ማንኪያና ሹካ",     "ar": "أدوات المائدة"},
    "assistance":   {"am": "እርዳታ",          "ar": "مساعدة"},
    "missing_item": {"am": "የጎደለ ነገር",      "ar": "صنف ناقص"},
    "packaging":    {"am": "ማሸጊያ",          "ar": "تغليف"},
    "bill":         {"am": "ሂሳብ",           "ar": "الفاتورة"},
}


def _fail(label: str, res) -> None:
    if not res.ok:
        raise ProbeFailed(label, res.err)


def seed() -> None:
    m3b.seed()
    _seed_roles()
    _seed_request_types()
    _seed_templates()
    _seed_service_policy()


def _seed_roles() -> None:
    """An attendant role requests route to, and a supervisor they escalate to.

    Two roles rather than one, because FR-SRV-004 says escalation goes to a SUPERVISOR or
    an alternate, and an escalation that could land on the person who did not answer
    would not be one.
    """
    res = run(APP, f"""
        INSERT INTO identity.role (id, tenant_id, role_code, display_name, status)
        VALUES ('{ROLE_ATTENDANT}', '{TENANT}', 'M3C_ATTENDANT', 'Service attendant',
                'active'),
               ('{ROLE_SUPERVISOR}', '{TENANT}', 'M3C_SUPERVISOR', 'Service supervisor',
                'active')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO identity.user_account
            (id, tenant_id, staff_number, display_name, status)
        VALUES ('{USER_SUPERVISOR}', '{TENANT}', 'M3C-SUP-1', 'Selam Supervisor', 'active')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO identity.membership
            (id, tenant_id, outlet_id, user_account_id, role_id, status)
        SELECT '3333c004-0000-4000-8000-0000000c0004', '{TENANT}', '{OUTLET_H1}',
               '{USER}', '{ROLE_ATTENDANT}', 'active'
         WHERE NOT EXISTS (SELECT 1 FROM identity.membership
                            WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET_H1}'
                              AND user_account_id = '{USER}'
                              AND role_id = '{ROLE_ATTENDANT}');

        INSERT INTO identity.membership
            (id, tenant_id, outlet_id, user_account_id, role_id, status)
        SELECT '3333c005-0000-4000-8000-0000000c0005', '{TENANT}', '{OUTLET_H1}',
               '{USER_SUPERVISOR}', '{ROLE_SUPERVISOR}', 'active'
         WHERE NOT EXISTS (SELECT 1 FROM identity.membership
                            WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET_H1}'
                              AND user_account_id = '{USER_SUPERVISOR}'
                              AND role_id = '{ROLE_SUPERVISOR}');
    """, **CTX)
    _fail("service roles", res)


def _seed_request_types() -> None:
    values = ",\n".join(
        f"('{TYPE_IDS[code]}', '{TENANT}', '{OUTLET_H1}', '{code}', "
        f"$lbl${label}$lbl$, {sla}, {window}, '{ROLE_ATTENDANT}')"
        for code, label, sla, window in REQUEST_TYPES)
    # Written as the administrator: 0014 grants the application role SELECT on
    # service.request_type and nothing more, because configuring what an outlet can be
    # asked for is a configuration act and that surface is FR-CFG-001B's, not this
    # gate's. A fixture that needed a wider grant would have been asking for the schema
    # to be loosened to suit the test.
    res = run(ADMIN, f"""
        INSERT INTO service.request_type
            (id, tenant_id, outlet_id, code, canonical_name, sla_seconds,
             dedup_window_seconds, handled_by_role_id)
        VALUES {values}
        ON CONFLICT (id) DO NOTHING;
    """)
    _fail("request types", res)

    # The labels, through M2-A's workflow: approved, with a reviewer and a timestamp.
    rows = []
    for code, labels in TYPE_LABELS.items():
        for locale, text in labels.items():
            rows.append(
                f"('{TENANT}', 'service_request_type', '{TYPE_IDS[code]}', 'label', "
                f"'{locale}', $t${text}$t$, 'approved', 'human', '{USER}', now())")
    # menu.translatable_field is M2-A's registry of what has translatable fields, and it
    # is administrator-owned for the same reason: adding a field is a schema-level act.
    res = run(ADMIN, f"""
        INSERT INTO menu.translatable_field
            (entity, field_name, required_for_publication, safety_critical)
        VALUES ('service_request_type', 'label', false, false),
               ('notification_template', 'body', false, false)
        ON CONFLICT (entity, field_name) DO NOTHING;

        INSERT INTO menu.translation
            (tenant_id, entity, entity_id, field_name, locale, translated_text, state,
             provenance, reviewed_by_user_id, approved_at)
        VALUES {",".join(rows)}
        ON CONFLICT (tenant_id, entity, entity_id, field_name, locale) DO NOTHING;
    """)
    _fail("request type labels", res)


def _seed_templates() -> None:
    values = ",\n".join(
        f"('{TEMPLATE_IDS[f'{event}|{audience}']}', '{TENANT}', '{event}', "
        f"'{audience}', $src${text}$src$)"
        for event, audiences in TEMPLATES.items()
        for audience, text in audiences.items())
    res = run(ADMIN, f"""
        INSERT INTO notify.template (id, tenant_id, event_id, audience, source_text)
        VALUES {values}
        ON CONFLICT (id) DO NOTHING;
    """)
    _fail("templates", res)

    rows = []
    for event, bodies in CUSTOMER_BODIES.items():
        template = TEMPLATE_IDS[f"{event}|customer"]
        for locale, text in bodies.items():
            rows.append(
                f"('{TENANT}', 'notification_template', '{template}', 'body', "
                f"'{locale}', $t${text}$t$, 'approved', 'human', '{USER}', now())")
    res = run(ADMIN, f"""
        INSERT INTO menu.translation
            (tenant_id, entity, entity_id, field_name, locale, translated_text, state,
             provenance, reviewed_by_user_id, approved_at)
        VALUES {",".join(rows)}
        ON CONFLICT (tenant_id, entity, entity_id, field_name, locale) DO NOTHING;
    """)
    _fail("template bodies", res)


def _seed_service_policy() -> None:
    """The two keys this slice reads, added to the policy M3-B seeded.

    Both are refused rather than defaulted by the functions that read them, so a policy
    missing either is a named failure and not a guess.
    """
    res = run(APP, f"""
        UPDATE config.policy
           SET payload = payload || '{{"service_escalation_role_code": "M3C_SUPERVISOR",
                                       "critical_alert_role_code": "M3C_SUPERVISOR"}}'::jsonb
         WHERE id = '{SERVICE_POLICY}';
    """, **CTX)
    _fail("service policy keys", res)


def set_presence(state: str, user: str = USER, session_id: str | None = None) -> None:
    """Assert presence for somebody, through a live staff session.

    Written as its own step rather than seeded once, because FR-SRV-002 routes by
    AVAILABILITY and an outlet that is permanently available cannot show that.
    """
    sid = session_id or m3b.staff_session()[0]
    res = run(APP, f"""
        SELECT set_config('app.session_id', '{sid}', true);
        SELECT service.set_presence('{TENANT}', '{OUTLET_H1}', '{user}', '{state}');
    """, tx=True, **CTX)
    _fail(f"presence {state}", res)
    return sid


def clear_presence() -> None:
    res = run(ADMIN, f"DELETE FROM service.staff_presence WHERE tenant_id = '{TENANT}';")
    _fail("clear presence", res)


def a_seated_guest(table: str = TABLE_ONE, locale: str = "en") -> dict:
    """An open occupancy with one live guest on it, in the language named.

    Returns the table session and the guest session, which is what every check in this
    suite starts from: a request needs somebody sitting down.
    """
    session = m3a.fresh_occupancy(table)
    guest = m3a.guest_on(session)
    res = run(APP, f"""
        UPDATE service.table_session
           SET customer_locale = '{locale}', customer_locale_selected_at = now()
         WHERE id = '{session}' AND tenant_id = '{TENANT}';
    """, **CTX)
    _fail("session locale", res)
    return dict(session=session, guest=guest, locale=locale)


def request_type(code: str) -> str:
    return TYPE_IDS[code]


def reason_code(category: str) -> str:
    return m3a.reason_code(category)


def staff_session() -> tuple[str, str]:
    return m3b.staff_session()


def a_seated_guest_with_credential(table: str = TABLE_ONE, locale: str = "en") -> dict:
    """A seated guest AND the bearer credential the HTTP surface will accept from them.

    M3-A's guest_on() mints a guest session with no token digest, because nothing at that
    gate went through HTTP. The service routes do, so this mints one that carries a
    digest — and only the digest reaches the database, exactly as M1-B stores staff
    tokens. The plaintext exists in this process and nowhere else (FR-SEC-007).
    """
    session = m3a.fresh_occupancy(table)
    res = run(APP, f"""
        UPDATE service.table_session
           SET customer_locale = '{locale}', customer_locale_selected_at = now()
         WHERE id = '{session}' AND tenant_id = '{TENANT}';
    """, **CTX)
    _fail("session locale", res)

    secret = os.urandom(16).hex()
    res = run(APP, f"""
        WITH g AS (
            INSERT INTO service.guest_session
                (tenant_id, outlet_id, display_nickname, locale, expires_at, token_hash)
            VALUES ('{TENANT}', '{OUTLET_H1}', 'Guest', '{locale}',
                    now() + interval '4 hours',
                    sha256(convert_to('{secret}', 'UTF8')))
            RETURNING id
        ), p AS (
            INSERT INTO service.session_participant
                (tenant_id, outlet_id, table_session_id, guest_session_id)
            SELECT '{TENANT}', '{OUTLET_H1}', '{session}', g.id FROM g
            RETURNING guest_session_id
        )
        SELECT guest_session_id FROM p;
    """, tx=True, **CTX)
    _fail("guest credential", res)
    guest = (res.scalar or "").strip()
    return dict(session=session, guest=guest, locale=locale,
                token=f"{TENANT}.{OUTLET_H1}.{secret}")
