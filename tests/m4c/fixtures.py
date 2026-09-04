"""What M4-C needs that no earlier slice built.

THE PRINTER IS TWO PRINTERS, and that is the point rather than a convenience. 0027 makes
a printer's SINK derive from its connection and its identity immutable, so a preview and
a device are different things that cannot become each other. A suite with one printer
could only ever prove the type boundary by argument; with a character device and a file
side by side, every claim about what a preview cannot be recorded as is a claim about two
rows that actually exist.

THE WORDING IS SEEDED WITH TRANSLATIONS FOR TWO LOCALES AND NOT THE THIRD FOR ONE KIND.
FR-I18N-001C says a receipt renders COMPLETELY in the session language, and 0027 refuses a
non-English receipt carrying English source text. A fixture that translated everything
would leave that refusal unfalsifiable from inside this suite, so NC-M4C-003 withdraws one
approved translation and requires the refusal — which means the seeding has to be complete
first, or the control's red leg would pass for the wrong reason.

THE PEOPLE ARE M4-B'S. A receipt is issued by whoever settled the bill and a reprint is
authorized by a manager, and M4-B already has a cashier who may not approve and a manager
who may. Inventing a third pair here would create an identity whose permissions no earlier
suite constrains, and every M4-B check about what a cashier may not do would keep passing
while a person who can do it exists two tables away.

THE COUNTER TERMINAL IS ITS OWN, because FR-POS-003B's whole content is that the terminal
is real: the session that enters a counter order must be bound to an active point-of-sale
device in this outlet. M4-B's till is bound to a drawer, and a counter order entered at it
would make the two requirements share one piece of furniture — so when one broke, both
would.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "m1a"))

from pg import ProbeFailed, run  # noqa: E402

# LOADED BY PATH, UNDER ITS OWN NAME, for the reason M4-A and M4-B both record: every
# slice's fixture module is called "fixtures", so an ordinary import binds whichever is
# earliest on sys.path — which here would be this file importing itself.
_spec = importlib.util.spec_from_file_location(
    "m4b_fixtures", HERE.parent / "m4b" / "fixtures.py")
m4b = importlib.util.module_from_spec(_spec)
sys.modules["m4b_fixtures"] = m4b
_spec.loader.exec_module(m4b)

m4a = m4b.m4a

TENANT = m4b.TENANT
OUTLET_H1 = m4b.OUTLET_H1
USER = m4b.USER
USER_MANAGER = m4b.USER_MANAGER
USER_CASHIER = m4b.USER_CASHIER
USER_FINANCE_MANAGER = m4b.USER_FINANCE_MANAGER

ITEM_DORO = m4b.ITEM_DORO
VARIANT_DORO_FULL = m4b.VARIANT_DORO_FULL

CTX = dict(tenant=TENANT, outlet=OUTLET_H1)
APP = os.environ["M1A_APP_DSN"]
ADMIN = os.environ["M1A_ADMIN_DSN"]

# --- this slice's own furniture --------------------------------------------
RECEIPT_TABLE   = "4444c101-0000-4000-8000-0000000c0101"
COUNTER_DEVICE  = "4444c102-0000-4000-8000-0000000c0102"

PRINTER_DEVICE  = "4444c201-0000-4000-8000-0000000c0201"
PRINTER_PREVIEW = "4444c202-0000-4000-8000-0000000c0202"
PRINTER_UNTESTED = "4444c203-0000-4000-8000-0000000c0203"

WORDING_BILL_TOTAL     = "4444c301-0000-4000-8000-0000000c0301"
WORDING_TIP            = "4444c302-0000-4000-8000-0000000c0302"
WORDING_TOTAL_PAID     = "4444c303-0000-4000-8000-0000000c0303"
WORDING_PAYMENT_METHOD = "4444c304-0000-4000-8000-0000000c0304"
WORDING_BILL_COMPONENT = "4444c305-0000-4000-8000-0000000c0305"

# os.devnull, NEVER a POSIX literal. M1-A's rule, and it caught this file: the null
# device is /dev/null on Linux and NUL on Windows, and a hardcoded POSIX path makes a
# suite that cannot run on the other platform. It is a CHARACTER DEVICE on Linux, which
# is what print/agent.py's stat() check requires — a regular file here would make every
# device-sink assertion in this suite pass for the wrong reason.
DEVICE_PATH = os.environ.get("M4C_DEVICE_PATH", os.devnull)

# FR-BIL-011's reprint needs a reason with an author. Category 'manager_override' because
# a reprint of a customer's receipt is a deliberate act somebody authorizes.
REASON_CODES = (
    ("M4C_RECEIPT_REPRINT", "manager_override", "Customer asked for another copy"),
    ("M4C_RECEIPT_REISSUE", "manager_override", "Receipt corrected after settlement"),
)

# The four line kinds that are not charge components, with their approved translations.
# Amharic is Ethiopic script and Arabic is RTL, which is what makes FR-I18N-001C's "all
# three locales" a real test rather than three copies of one alphabet.
LINE_WORDINGS = {
    "bill_total": {
        "id": WORDING_BILL_TOTAL,
        "en": "Bill total", "am": "የሂሳብ ድምር", "ar": "إجمالي الفاتورة"},
    "tip": {
        "id": WORDING_TIP,
        "en": "Tip", "am": "ጉርሻ", "ar": "إكرامية"},
    "total_paid": {
        "id": WORDING_TOTAL_PAID,
        "en": "Total paid", "am": "ጠቅላላ የተከፈለ", "ar": "المجموع المدفوع"},
    "payment_method": {
        "id": WORDING_PAYMENT_METHOD,
        "en": "Paid by", "am": "የክፍያ ዘዴ", "ar": "طريقة الدفع"},
    "bill_component": {
        "id": WORDING_BILL_COMPONENT,
        "en": "Items", "am": "ንጥሎች", "ar": "الأصناف"},
}


def _fail(label: str, res) -> None:
    if not res.ok:
        raise ProbeFailed(f"m4c fixture: {label}", res.err)


def seed() -> None:
    m4b.seed()
    _seed_own_table()
    _seed_counter_terminal()
    _seed_line_wording()
    _seed_reason_codes()
    _seed_printers()


def _seed_own_table() -> None:
    res = run(APP, f"""
        INSERT INTO org.org_node
            (id, tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{RECEIPT_TABLE}', '{TENANT}', '{OUTLET_H1}', 'dining_table',
                'M4C-RCP', 'Table the receipt is issued against')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO service.table_profile
            (tenant_id, table_node_id, outlet_id, seat_count)
        VALUES ('{TENANT}', '{RECEIPT_TABLE}', '{OUTLET_H1}', 4)
        ON CONFLICT DO NOTHING;
    """, tx=True, **CTX)
    _fail("m4c table", res)


def _seed_counter_terminal() -> None:
    """FR-POS-003B's till, registered through pos.register_terminal().

    A fixture that inserted the pos.terminal row directly would prove the table accepts
    rows and nothing about FR-POS-001, which is the lesson M3-D's own fixture records and
    M4-B repeats. The device node and its registration come first, because a terminal is a
    registered DEVICE.
    """
    res = run(APP, f"""
        INSERT INTO org.org_node
            (id, tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{COUNTER_DEVICE}', '{TENANT}', '{OUTLET_H1}', 'device',
                'M4C-TILL-2', 'The counter terminal orders are entered at')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO org.device_registration
            (device_id, tenant_id, outlet_id, registration_code)
        VALUES ('{COUNTER_DEVICE}', '{TENANT}', '{OUTLET_H1}', 'M4C-REG-2')
        ON CONFLICT (device_id) DO NOTHING;
    """, **CTX)
    _fail("m4c counter device node", res)

    res = run(APP, f"""
        SELECT pos.register_terminal('{TENANT}', '{OUTLET_H1}', '{COUNTER_DEVICE}',
                                     'point_of_sale', '{USER_MANAGER}')
        WHERE NOT EXISTS (SELECT 1 FROM pos.terminal
                           WHERE device_id = '{COUNTER_DEVICE}');
    """, **CTX)
    _fail("m4c counter terminal", res)


def _seed_line_wording() -> None:
    """FR-I18N-001C. What a receipt calls its lines, in all three locales.

    Through menu.translation and menu.translatable_field — M2-A's approval workflow
    unchanged — because a second store for text a customer reads is how two copies come to
    disagree, which is the finding M2-B made and 0027's comment records.
    """
    wordings = ",\n".join(
        f"('{w['id']}', '{TENANT}', '{kind}', $src${w['en']}$src$)"
        for kind, w in LINE_WORDINGS.items())
    translations = ",\n".join(
        f"('{TENANT}', 'receipt_line_wording', '{w['id']}', 'label', '{locale}', "
        f"$t${w[locale]}$t$, 'approved', 'human', '{USER_MANAGER}', now())"
        for w in LINE_WORDINGS.values()
        for locale in ("am", "ar"))
    res = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{OUTLET_H1}', false);

        INSERT INTO menu.translatable_field
            (entity, field_name, required_for_publication, safety_critical)
        VALUES ('receipt_line_wording', 'label', false, false)
        ON CONFLICT (entity, field_name) DO NOTHING;

        INSERT INTO docs.line_wording (id, tenant_id, kind, source_text)
        VALUES {wordings}
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO menu.translation
            (tenant_id, entity, entity_id, field_name, locale, translated_text, state,
             provenance, reviewed_by_user_id, approved_at)
        VALUES {translations}
        ON CONFLICT (tenant_id, entity, entity_id, field_name, locale) DO NOTHING;
    """, tx=True)
    _fail("m4c receipt line wording", res)


def _seed_reason_codes() -> None:
    """The reasons a reprint or a reissue names, with their English labels.

    A code and a label are separate rows because M1-C requires every reason code to carry
    a localized label and to keep the structure and the content apart — the lesson M3-D's
    fixture cost two findings to learn, once in each direction.
    """
    codes = ",\n".join(
        f"('{TENANT}', '{category}', '{code}', 'active')"
        for code, category, _label in REASON_CODES)
    labels = ",\n".join(
        f"('{code}', $l${label}$l$)" for code, _category, label in REASON_CODES)
    res = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{OUTLET_H1}', false);
        INSERT INTO config.reason_code (tenant_id, category, code, status)
        VALUES {codes}
        ON CONFLICT (tenant_id, category, code) DO NOTHING;

        INSERT INTO config.reason_code_label (tenant_id, reason_code_id, locale, label)
        SELECT rc.tenant_id, rc.id, 'en', v.label
        FROM config.reason_code rc
        JOIN (VALUES {labels}) AS v(code, label) ON v.code = rc.code
        WHERE rc.tenant_id = '{TENANT}'
        ON CONFLICT DO NOTHING;
    """, tx=True)
    _fail("m4c reason codes", res)


def _seed_printers() -> None:
    """One device, one preview, one device nobody tested.

    THE THIRD IS THE INTERESTING ONE. FR-CFG-001D says setup registers AND TESTS, and a
    build with only tested printers cannot show what an untested one is refused for.
    NC-M4C-008 prints a customer receipt at it and requires PRINTER_NEVER_TESTED.
    """
    global PRINTER_PREVIEW

    res = run(APP, f"""
        INSERT INTO docs.printer
            (id, tenant_id, outlet_id, display_name, connection, sink, device_path,
             registered_by_user_id)
        VALUES ('{PRINTER_DEVICE}', '{TENANT}', '{OUTLET_H1}', 'M4C counter printer',
                'character_device', 'device', '{DEVICE_PATH}', '{USER_MANAGER}'),
               ('{PRINTER_UNTESTED}', '{TENANT}', '{OUTLET_H1}', 'M4C printer untested',
                'character_device', 'device', '{DEVICE_PATH}', '{USER_MANAGER}')
        ON CONFLICT (id) DO NOTHING;
    """, **CTX)
    _fail("m4c device printers", res)

    # THE PREVIEW PRINTER GOES IN THROUGH docs.register_printer(), which derives the sink
    # from the connection. Registered by the path an operator would use, because the claim
    # being made about it is that a file cannot become a device — and a row inserted by
    # hand would prove the CHECK on the table and nothing about the function.
    #
    # Its identity is DISCOVERED rather than chosen: the function allocates the uuid and
    # 0027's immutability trigger means the row cannot be moved to one this file picked.
    # A fixture insisting on its own id would be asking the schema to relax the rule this
    # suite exists to prove.
    res = run(APP, f"""
        SELECT docs.register_printer('{TENANT}', '{OUTLET_H1}', 'M4C preview sink',
                                     'file', '{_preview_path()}', NULL, '{USER_MANAGER}')
        WHERE NOT EXISTS (
            SELECT 1 FROM docs.printer
             WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET_H1}'
               AND display_name = 'M4C preview sink' AND status = 'active');
    """, **CTX)
    _fail("m4c preview printer", res)

    found = run(APP, f"""
        SELECT id FROM docs.printer
         WHERE tenant_id = '{TENANT}' AND outlet_id = '{OUTLET_H1}'
           AND display_name = 'M4C preview sink' AND status = 'active';""", **CTX)
    _fail("m4c preview printer lookup", found)
    PRINTER_PREVIEW = (found.scalar or "").strip()
    if not PRINTER_PREVIEW:
        raise ProbeFailed(
            "m4c fixture: preview printer",
            "docs.register_printer() returned no row for the preview sink. An empty id "
            "here becomes an invalid-uuid error in a different section entirely")

    # THE TESTED PRINTER IS TESTED, through docs.record_printer_test(). A printer marked
    # ready by a fixture writing a row would be exactly the setup screen FR-CFG-001D
    # exists to refuse.
    res = run(APP, f"""
        SELECT docs.record_printer_test(
                 '{TENANT}', '{OUTLET_H1}', '{PRINTER_DEVICE}', 'printed',
                 repeat('a', 64)::char(64), 128, 'fixture test page', '{USER_MANAGER}')
        WHERE NOT docs.printer_has_passed_a_test('{TENANT}', '{PRINTER_DEVICE}');
    """, **CTX)
    _fail("m4c printer test", res)


def _preview_path() -> str:
    """Where a preview render is written. Under the scratch directory, never the repo.

    tempfile.gettempdir() rather than a POSIX literal, because M1-A's rule is that a path
    written for one platform is a test that does not run on the other, and this suite runs
    on both.
    """
    return str(Path(tempfile.gettempdir()) / "m4c-preview.bin")


def staff_session(user_id: str = USER) -> tuple[str, str]:
    return m4b.staff_session(user_id)


def step_up(session_id: str, action_code: str, age_seconds: int = 0) -> str:
    return m4b.step_up(session_id, action_code, age_seconds)


def reason_code(code: str) -> str:
    return m4b.reason_code(code)


def bind_session_to(session_id: str, device_id: str) -> None:
    """Put a live staff session on a device, so a counter order has a terminal.

    FR-POS-003B resolves the terminal from identity.session.device_id rather than from a
    parameter, which is the whole of what makes it a place rather than a claim. A fixture
    therefore cannot hand the terminal to the route; it has to put the session on the
    device, exactly as an operator authenticating at the till does.
    """
    res = run(ADMIN, f"""
        SELECT set_config('app.tenant_id', '{TENANT}', false);
        SELECT set_config('app.outlet_id', '{OUTLET_H1}', false);
        UPDATE identity.session SET device_id = '{device_id}'
         WHERE id = '{session_id}' AND tenant_id = '{TENANT}';
    """, tx=True)
    _fail("binding a session to a device", res)
